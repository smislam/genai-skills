"""All network access for appsec-auditor goes through curl.

curl ships with macOS, Linux, Git Bash, and Windows 10+, and handles corporate networks better
than a language-level HTTP stack: HTTPS_PROXY/NO_PROXY, authenticated proxies (NTLM/Kerberos via
the logged-in user), and the OS certificate store on Windows (TLS inspection).

Settings (environment variables; all optional):
  HTTPS_PROXY, HTTP_PROXY, NO_PROXY   standard proxy variables, honored by curl itself
  APPSEC_PROXY                        explicit proxy URL (overrides HTTPS_PROXY)
  APPSEC_PROXY_AUTH                   negotiate | ntlm | basic | none (default: none)
  APPSEC_CA_BUNDLE                    PEM file with the corporate root CA (TLS inspection)
  APPSEC_SSL_REVOKE_BEST_EFFORT=1     Windows only: tolerate unreachable revocation servers
  APPSEC_OSV_URL, APPSEC_KEV_URL, APPSEC_EPSS_URL, APPSEC_MAVEN_URL   internal mirrors

The curl executable is resolved once with shutil.which, which follows PATH order exactly as the
user's shell does. (On Windows, CreateProcess would search C:\\Windows\\System32 first and could
pick a different curl.exe, for example one built without NTLM support.)

Public API (result dicts use camelCase keys where they are printed or consumed as JSON):
    ENDPOINTS: dict[str, str]                       keys osv, kev, epss, maven
    redact_url(url) -> str
    describe_config() -> dict[str, Any]             proxy, proxySource, noProxy, proxyAuth,
                                                    caBundle, endpoints
    request(url, method='GET', body=NO_BODY) -> dict[str, Any]
        url may also be a dict {'url': ..., 'method': ..., 'json': ...};
        success {'ok': True, 'status', 'body'}; failure {'ok': False, 'status', 'category',
        'hint', 'url'}
    get_text(url) -> str | None
    get_json(url) -> dict[str, Any]                 success {'ok': True, 'status', 'data'}
    post_json(url, body) -> dict[str, Any]
Internal (used by tests): proxy_setting(), base_args(), diagnose(exit_code, status, stderr).
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

__all__ = [
    'ENDPOINTS', 'NO_BODY', 'describe_config', 'get_json', 'get_text', 'post_json', 'redact_url',
    'request',
]

# Safety net above curl's own limits (--max-time 180 with 2 retries).
CURL_TIMEOUT_SECONDS: int = 900
NEWLINE: str = '\n'
STATUS_MARKER: str = NEWLINE + '__APPSEC_HTTP_STATUS__'
NOT_JSON_HINT: str = (
    'The response was not JSON; a proxy may have returned a block or login page.'
)
PROXY_AUTH_HINT: str = (
    'The proxy requires authentication. Set APPSEC_PROXY_AUTH=negotiate (or ntlm) to use your '
    'Windows login, or basic with credentials in the proxy URL.'
)

# Credentials in a URL authority: //user:pass@host (first occurrence only).
RE_URL_CREDENTIALS: re.Pattern[str] = re.compile(r'//([^/@\s]+)@', re.ASCII)
RE_TLS: re.Pattern[str] = re.compile(
    r'certificate|SEC_E_UNTRUSTED_ROOT|self.signed', re.ASCII | re.IGNORECASE)
RE_REVOCATION: re.Pattern[str] = re.compile(
    r'CRYPT_E_NO_REVOCATION_CHECK|CRYPT_E_REVOCATION_OFFLINE', re.ASCII | re.IGNORECASE)

# Marker meaning "no JSON request body was given" (distinct from a JSON null body).
NO_BODY: Any = object()

ENDPOINTS: dict[str, str] = {
    'osv': os.environ.get('APPSEC_OSV_URL') or 'https://api.osv.dev/v1',
    'kev': os.environ.get('APPSEC_KEV_URL') or (
        'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'),
    'epss': os.environ.get('APPSEC_EPSS_URL') or 'https://api.first.org/data/v1/epss',
    'maven': os.environ.get('APPSEC_MAVEN_URL') or 'https://repo1.maven.org/maven2',
}


def redact_url(url: object) -> str:
    """Never print proxy credentials."""
    return RE_URL_CREDENTIALS.sub('//****@', str(url) if url else '', count=1)


def proxy_setting() -> str:
    """The proxy URL in effect: APPSEC_PROXY, then HTTPS_PROXY, then https_proxy."""
    env = os.environ
    return env.get('APPSEC_PROXY') or env.get('HTTPS_PROXY') or env.get('https_proxy') or ''


def describe_config() -> dict[str, Any]:
    """Network settings in effect, safe to print (credentials redacted)."""
    env = os.environ
    proxy = proxy_setting()
    if env.get('APPSEC_PROXY'):
        source = 'APPSEC_PROXY'
    else:
        source = 'HTTPS_PROXY' if proxy else ''
    return {
        'proxy': redact_url(proxy) or '(none)',
        'proxySource': source,
        'noProxy': env.get('NO_PROXY') or env.get('no_proxy') or '',
        'proxyAuth': env.get('APPSEC_PROXY_AUTH') or 'none',
        'caBundle': env.get('APPSEC_CA_BUNDLE') or '(system default)',
        'endpoints': {k: redact_url(v) for k, v in ENDPOINTS.items()},
    }


def base_args() -> list[str]:
    """curl arguments shared by every request, built from the environment."""
    env = os.environ
    args = ['-sS', '-L', '--connect-timeout', '20', '--max-time', '180', '--retry', '2',
            '--retry-delay', '2']
    if env.get('APPSEC_PROXY'):
        args += ['--proxy', env['APPSEC_PROXY']]
    auth = (env.get('APPSEC_PROXY_AUTH') or 'none').lower()
    # "-U :" makes curl use the logged-in user's credentials (SSPI on Windows, Kerberos elsewhere).
    if auth == 'negotiate':
        args += ['--proxy-negotiate', '--proxy-user', ':']
    elif auth == 'ntlm':
        args += ['--proxy-ntlm', '--proxy-user', ':']
    elif auth == 'basic':
        args.append('--proxy-basic')
    if env.get('APPSEC_CA_BUNDLE'):
        args += ['--cacert', env['APPSEC_CA_BUNDLE']]
    if env.get('APPSEC_SSL_REVOKE_BEST_EFFORT') == '1':
        args.append('--ssl-revoke-best-effort')
    args += ['-w', STATUS_MARKER + '%{http_code}']
    return args


@functools.cache
def curl_path() -> str:
    """The curl executable, resolved once in PATH order (plain 'curl' if not found)."""
    return shutil.which('curl') or 'curl'


def diagnose_exit(exit_code: int | None, via_proxy: bool) -> tuple[str, str] | None:
    """Category and hint for curl exit codes that identify the problem on their own."""
    if exit_code == 5:
        return ('proxy-dns',
                'The proxy host name could not be resolved. Check APPSEC_PROXY / HTTPS_PROXY.')
    if exit_code == 6:
        return ('dns',
                'The host name could not be resolved. Behind a firewall, set HTTPS_PROXY or '
                'APPSEC_PROXY, or point APPSEC_*_URL at an internal mirror.')
    if exit_code == 7:
        if via_proxy:
            return ('proxy-connect',
                    'Could not connect to the configured proxy. Check its host and port in '
                    'APPSEC_PROXY / HTTPS_PROXY.')
        return ('connect',
                'Connection refused or blocked. A proxy is probably required: set HTTPS_PROXY '
                'or APPSEC_PROXY.')
    if exit_code == 28:
        if via_proxy:
            return ('timeout',
                    'The request timed out through the proxy. The proxy may be blocking the '
                    'destination.')
        return ('timeout',
                'The request timed out. A firewall may be silently dropping traffic: set '
                'HTTPS_PROXY or APPSEC_PROXY.')
    return None


def diagnose(exit_code: int | None, status: int, stderr: str | None) -> tuple[str, str]:
    """Map curl exit codes and HTTP statuses to what a user behind a firewall needs to fix."""
    text = stderr or ''
    found = diagnose_exit(exit_code, bool(proxy_setting()))
    if found:
        return found
    if exit_code == 56 and '407' in text:
        return ('proxy-auth', PROXY_AUTH_HINT)
    if exit_code in (35, 60, 77) or RE_TLS.search(text):
        return ('tls',
                'TLS certificate not trusted, usually corporate TLS inspection. Set '
                'APPSEC_CA_BUNDLE to the corporate root CA (PEM).')
    if RE_REVOCATION.search(text):
        return ('revocation',
                'Windows could not check certificate revocation through the proxy. Set '
                'APPSEC_SSL_REVOKE_BEST_EFFORT=1.')
    if status == 407:
        return ('proxy-auth', PROXY_AUTH_HINT)
    if status == 403:
        return ('blocked',
                'Forbidden (403). The URL may be blocked by policy; ask for it to be allowed, '
                'or use an internal mirror via APPSEC_*_URL.')
    if status == 429:
        return ('rate-limit', 'Rate limited (429). Wait and retry.')
    if status >= 500:
        return ('server', f'The server returned {status}. Retry later.')
    if status >= 400:
        return ('http', f'HTTP {status}.')
    return ('curl', f'curl failed with exit code {exit_code}: {text.strip().split(NEWLINE)[-1]}')


def parse_status(text: str) -> int:
    """The HTTP status curl printed after the marker (0 if it is not a number)."""
    try:
        return int(text.strip())
    except ValueError:
        return 0


def write_body(body: Any) -> str:
    """Write the JSON request body to a private temp file and return its path."""
    # ensure_ascii keeps the file pure ASCII (non-ASCII and lone surrogates become \\u escapes).
    text = json.dumps(body, separators=(',', ':'))
    fd, path = tempfile.mkstemp(prefix=f'appsec-body-{os.getpid()}-', suffix='.json')
    with os.fdopen(fd, 'w', encoding='ascii') as handle:
        handle.write(text)
    return path


def failure(status: int, category: str, hint: str, url: str) -> dict[str, Any]:
    """Result dict for a failed request."""
    return {'ok': False, 'status': status, 'category': category, 'hint': hint,
            'url': redact_url(url)}


def run_curl(args: list[str]) -> tuple[int, str, str] | None:
    """Run curl; None when it cannot be started. Raises subprocess.TimeoutExpired on timeout."""
    try:
        proc = subprocess.run([curl_path(), *args], capture_output=True, check=False,
                              timeout=CURL_TIMEOUT_SECONDS,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError:
        return None
    return (proc.returncode, proc.stdout.decode('utf-8', errors='replace'),
            proc.stderr.decode('utf-8', errors='replace'))


def remove_quietly(path: str) -> None:
    """Delete a temp file, reporting (but not raising) a failure."""
    try:
        os.remove(path)
    except OSError as exc:
        print(f'appsec-auditor: could not remove {path}: {exc}', file=sys.stderr)


def execute(url: str, method: str, body: Any) -> dict[str, Any]:
    """Build the curl command, run it, and interpret the outcome."""
    args = base_args()
    tmp: str | None = None
    if body is not NO_BODY:
        tmp = write_body(body)
        args += ['-X', 'POST' if method == 'GET' else method, '-H',
                 'Content-Type: application/json', '--data-binary', f'@{tmp}']
    args.append(url)
    try:
        result = run_curl(args)
    except subprocess.TimeoutExpired:
        category, hint = diagnose(28, 0, '')
        return failure(0, category, hint, url)
    finally:
        if tmp:
            remove_quietly(tmp)
    if result is None:
        return failure(0, 'no-curl', 'curl was not found on PATH. It ships with macOS, Linux, '
                       'Git Bash, and Windows 10+.', url)
    code, out, err = result
    marker = out.rfind(STATUS_MARKER)
    status = parse_status(out[marker + len(STATUS_MARKER):]) if marker >= 0 else 0
    text = out[:marker] if marker >= 0 else out
    if code == 0 and 200 <= status < 300:
        return {'ok': True, 'status': status, 'body': text}
    category, hint = diagnose(code, status, err)
    return failure(status, category, hint, url)


def request(url: Any, method: str = 'GET', body: Any = NO_BODY) -> dict[str, Any]:
    """GET (or POST when a JSON body is given) through curl and classify the outcome."""
    if isinstance(url, dict):
        return execute(url['url'], url.get('method', 'GET'), url.get('json', NO_BODY))
    return execute(url, method, body)


def get_text(url: str) -> str | None:
    """Response body of a successful GET, otherwise None."""
    r = request(url)
    return r['body'] if r['ok'] else None


def json_result(r: dict[str, Any], url: str) -> dict[str, Any]:
    """Turn a successful text response into a parsed-JSON result, or a not-json failure."""
    if not r['ok']:
        return r
    try:
        data = json.loads(r['body'])
    except (ValueError, RecursionError):
        return failure(r['status'], 'not-json', NOT_JSON_HINT, url)
    return {'ok': True, 'status': r['status'], 'data': data}


def get_json(url: str) -> dict[str, Any]:
    """GET a URL and parse the body as JSON."""
    return json_result(request(url), url)


def post_json(url: str, body: Any) -> dict[str, Any]:
    """POST a JSON body and parse the response as JSON."""
    return json_result(request(url, method='POST', body=body), url)
