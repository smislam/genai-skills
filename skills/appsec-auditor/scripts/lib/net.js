'use strict';
// All network access for appsec-auditor goes through curl, which ships with macOS, Linux,
// Git Bash, and Windows 10+, and handles corporate networks better than Node's HTTP stack:
// HTTPS_PROXY/NO_PROXY, authenticated proxies (NTLM/Kerberos via the logged-in user),
// and the OS certificate store on Windows (TLS inspection).
//
// Settings (environment variables; all optional):
//   HTTPS_PROXY, HTTP_PROXY, NO_PROXY   standard proxy variables, honored by curl itself
//   APPSEC_PROXY                        explicit proxy URL (overrides HTTPS_PROXY)
//   APPSEC_PROXY_AUTH                   negotiate | ntlm | basic | none (default: none)
//   APPSEC_CA_BUNDLE                    PEM file with the corporate root CA (TLS inspection)
//   APPSEC_SSL_REVOKE_BEST_EFFORT=1     Windows only: tolerate unreachable revocation servers
//   APPSEC_OSV_URL, APPSEC_KEV_URL, APPSEC_EPSS_URL, APPSEC_MAVEN_URL   internal mirrors

const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ENDPOINTS = {
  osv: process.env.APPSEC_OSV_URL || 'https://api.osv.dev/v1',
  kev: process.env.APPSEC_KEV_URL || 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json',
  epss: process.env.APPSEC_EPSS_URL || 'https://api.first.org/data/v1/epss',
  maven: process.env.APPSEC_MAVEN_URL || 'https://repo1.maven.org/maven2',
};

// Never print proxy credentials.
function redactUrl(url) {
  return String(url || '').replace(/\/\/([^/@\s]+)@/, '//****@');
}

function proxySetting() {
  return process.env.APPSEC_PROXY || process.env.HTTPS_PROXY || process.env.https_proxy || '';
}

function describeConfig() {
  return {
    proxy: redactUrl(proxySetting()) || '(none)',
    proxySource: process.env.APPSEC_PROXY ? 'APPSEC_PROXY' : proxySetting() ? 'HTTPS_PROXY' : '',
    noProxy: process.env.NO_PROXY || process.env.no_proxy || '',
    proxyAuth: process.env.APPSEC_PROXY_AUTH || 'none',
    caBundle: process.env.APPSEC_CA_BUNDLE || '(system default)',
    endpoints: Object.fromEntries(Object.entries(ENDPOINTS).map(([k, v]) => [k, redactUrl(v)])),
  };
}

function baseArgs() {
  const args = ['-sS', '-L', '--connect-timeout', '20', '--max-time', '180', '--retry', '2', '--retry-delay', '2'];
  if (process.env.APPSEC_PROXY) args.push('--proxy', process.env.APPSEC_PROXY);
  const auth = (process.env.APPSEC_PROXY_AUTH || 'none').toLowerCase();
  // "-U :" makes curl use the logged-in user's credentials (SSPI on Windows, Kerberos ticket elsewhere).
  if (auth === 'negotiate') args.push('--proxy-negotiate', '--proxy-user', ':');
  else if (auth === 'ntlm') args.push('--proxy-ntlm', '--proxy-user', ':');
  else if (auth === 'basic') args.push('--proxy-basic');
  if (process.env.APPSEC_CA_BUNDLE) args.push('--cacert', process.env.APPSEC_CA_BUNDLE);
  if (process.env.APPSEC_SSL_REVOKE_BEST_EFFORT === '1') args.push('--ssl-revoke-best-effort');
  args.push('-w', '\n__APPSEC_HTTP_STATUS__%{http_code}');
  return args;
}

// curl exit codes and HTTP statuses mapped to what a user behind a firewall needs to fix.
function diagnose(exitCode, status, stderr) {
  const s = String(stderr || '');
  const viaProxy = Boolean(proxySetting());
  if (exitCode === 5) return ['proxy-dns', 'The proxy host name could not be resolved. Check APPSEC_PROXY / HTTPS_PROXY.'];
  if (exitCode === 6) return ['dns', 'The host name could not be resolved. Behind a firewall, set HTTPS_PROXY or APPSEC_PROXY, or point APPSEC_*_URL at an internal mirror.'];
  if (exitCode === 7) {
    return viaProxy
      ? ['proxy-connect', 'Could not connect to the configured proxy. Check its host and port in APPSEC_PROXY / HTTPS_PROXY.']
      : ['connect', 'Connection refused or blocked. A proxy is probably required: set HTTPS_PROXY or APPSEC_PROXY.'];
  }
  if (exitCode === 28) {
    return viaProxy
      ? ['timeout', 'The request timed out through the proxy. The proxy may be blocking the destination.']
      : ['timeout', 'The request timed out. A firewall may be silently dropping traffic: set HTTPS_PROXY or APPSEC_PROXY.'];
  }
  if (exitCode === 56 && /407/.test(s)) return ['proxy-auth', 'The proxy requires authentication. Set APPSEC_PROXY_AUTH=negotiate (or ntlm) to use your Windows login, or basic with credentials in the proxy URL.'];
  if (exitCode === 35 || exitCode === 60 || exitCode === 77 || /certificate|SEC_E_UNTRUSTED_ROOT|self.signed/i.test(s)) {
    return ['tls', 'TLS certificate not trusted, usually corporate TLS inspection. Set APPSEC_CA_BUNDLE to the corporate root CA (PEM).'];
  }
  if (/CRYPT_E_NO_REVOCATION_CHECK|CRYPT_E_REVOCATION_OFFLINE/i.test(s)) {
    return ['revocation', 'Windows could not check certificate revocation through the proxy. Set APPSEC_SSL_REVOKE_BEST_EFFORT=1.'];
  }
  if (status === 407) return ['proxy-auth', 'The proxy requires authentication. Set APPSEC_PROXY_AUTH=negotiate (or ntlm) to use your Windows login, or basic with credentials in the proxy URL.'];
  if (status === 403) return ['blocked', 'Forbidden (403). The URL may be blocked by policy; ask for it to be allowed, or use an internal mirror via APPSEC_*_URL.'];
  if (status === 429) return ['rate-limit', 'Rate limited (429). Wait and retry.'];
  if (status >= 500) return ['server', `The server returned ${status}. Retry later.`];
  if (status >= 400) return ['http', `HTTP ${status}.`];
  return ['curl', `curl failed with exit code ${exitCode}: ${s.trim().split('\n').pop()}`];
}

function request({ url, method = 'GET', json }) {
  const args = baseArgs();
  let tmp = null;
  if (json !== undefined) {
    tmp = path.join(os.tmpdir(), `appsec-body-${process.pid}-${Date.now()}.json`);
    fs.writeFileSync(tmp, JSON.stringify(json));
    args.push('-X', method === 'GET' ? 'POST' : method, '-H', 'Content-Type: application/json', '--data-binary', `@${tmp}`);
  }
  args.push(url);
  const r = spawnSync('curl', args, { encoding: 'utf8', maxBuffer: 1024 * 1024 * 512, env: process.env, windowsHide: true });
  if (tmp) fs.rmSync(tmp, { force: true });
  if (r.error) {
    return { ok: false, status: 0, category: 'no-curl', hint: 'curl was not found on PATH. It ships with macOS, Linux, Git Bash, and Windows 10+.', url: redactUrl(url) };
  }
  const out = r.stdout || '';
  const marker = out.lastIndexOf('\n__APPSEC_HTTP_STATUS__');
  const status = marker >= 0 ? Number(out.slice(marker + 23)) : 0;
  const body = marker >= 0 ? out.slice(0, marker) : out;
  if (r.status === 0 && status >= 200 && status < 300) return { ok: true, status, body };
  const [category, hint] = diagnose(r.status, status, r.stderr);
  return { ok: false, status, category, hint, url: redactUrl(url) };
}

function getText(url) {
  const r = request({ url });
  return r.ok ? r.body : null;
}

function getJSON(url) {
  const r = request({ url });
  if (!r.ok) return r;
  try {
    return { ok: true, status: r.status, data: JSON.parse(r.body) };
  } catch {
    return { ok: false, status: r.status, category: 'not-json', hint: 'The response was not JSON; a proxy may have returned a block or login page.', url: redactUrl(url) };
  }
}

function postJSON(url, body) {
  const r = request({ url, method: 'POST', json: body });
  if (!r.ok) return r;
  try {
    return { ok: true, status: r.status, data: JSON.parse(r.body) };
  } catch {
    return { ok: false, status: r.status, category: 'not-json', hint: 'The response was not JSON; a proxy may have returned a block or login page.', url: redactUrl(url) };
  }
}

module.exports = { ENDPOINTS, describeConfig, redactUrl, request, getText, getJSON, postJSON };
