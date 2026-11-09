"""Lightweight taint tracking for scripts (Python, JavaScript, shell, PowerShell).

Not a real data-flow engine: it follows variable assignments for three hops inside one file and
links a source to a sink. Every result names both lines so the reviewer can check it by eye.
"""

from __future__ import annotations

import re
from typing import Any

from . import text

__all__ = ['SINKS', 'SKIP_NAMES', 'SOURCES', 'analyze', 'assigned_name']

def _rx(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    """Compile a taint pattern with the hardened scan semantics from ``text.scan_re``.

    ASCII ``\\w \\d \\b`` and Unicode-aware ``\\s`` (so a no-break space cannot split a token).
    Case-insensitive by default; pass ``re.ASCII`` to match case-sensitively.
    """
    return text.scan_re(pattern, 'i' if flags & re.IGNORECASE else '')


SOURCES: list[dict[str, Any]] = [
    {'kind': 'cred', 're': _rx(
        r'\.ssh[\\/]|id_rsa|id_ed25519|\.aws[\\/]credentials|\.kube[\\/]config|\.netrc|\.npmrc'
        r'|\.git-credentials|\.docker[\\/]config|\.pypirc|Login Data|logins\.json|\.vault-token'
        r'|\bgh\s+auth\s+token\b|get-access-token|print-access-token')},
    {'kind': 'env', 're': _rx(
        r'os\.environ\b|os\.getenv\s*\(|process\.env\b|\$env:\w+|\$\{?ENV\b|System\.getenv'
        r'|Environment\.GetEnvironmentVariable|\bprintenv\b')},
    {'kind': 'ctx', 're': _rx(
        r'transcript_path|\.claude[\\/]projects|history\.jsonl|conversation[_-]?history')},
    {'kind': 'file', 're': _rx(
        r'\b(open|readFileSync|readFile|read_text|read_bytes|Get-Content|File\.ReadAll\w*|cat)'
        r'\s*\(?\s*[^\n]*?(\.env\b|\.pem\b|\.key\b|\.p12\b|\.pfx\b|secrets?\b|passwd|shadow|\.git[\\/]config)')},
    {'kind': 'input', 're': _rx(
        r'sys\.stdin|input\s*\(|sys\.argv|process\.argv|process\.stdin|readFileSync\(\s*0\s*\)'
        r'|\$\{?[1-9@*]\}?(?![\w])|\$args\b|\$_POST|\$_GET|request\.(args|form|json|body|params|query)'
        r'|req\.(body|query|params)|tool_input|tool_response')},
    {'kind': 'net', 're': _rx(
        r'\brequests\.(get|post)\([^)]*\)\.(text|json|content)|\burlopen\([^)]*\)\.read'
        r'|await\s+fetch\([^)]*\)|\bcurl\s+[^|;\n]*\$\('
        r'|\.then\(\s*\(?\w+\)?\s*=>\s*\w+\.(text|json)\(\)|Invoke-(WebRequest|RestMethod)')},
]

SINKS: list[dict[str, Any]] = [
    {'kind': 'send', 're': _rx(
        r'\b(requests|httpx|session)\.(post|put|patch)\s*\('
        r'''|\bfetch\s*\([^)]*method\s*:\s*['"](POST|PUT|PATCH)'''
        r'|\baxios\.(post|put|patch)\b'
        r'|\bcurl\b[^\n]*\s(-d|--data(-\w+)?|-F|--form|-T|--upload-file)\b'
        r'|\bwget\b[^\n]*--post-(data|file)'
        r'|\bInvoke-(WebRequest|RestMethod)\b[^\n]*-(Body|InFile|Uri)\b'
        r'|\burlopen\([^)]*data\s*=|\bsocket\.(send|sendall|sendto)\s*\(|\.write\(\s*req'
        r'|\bnc\s+\S+\s+\d+|\bscp\s|\bsmtplib\b|\bhttps?\.request\b|\.send\s*\(')},
    {'kind': 'exec', 're': _rx(
        r'(?<![.\w$])(eval|exec)\s*\(|\bos\.system\s*\(|\bsubprocess\.\w+\s*\(|\bchild_process\b'
        r'|\b(execSync|spawnSync|execFileSync|execFile|spawn)\s*\(|\bInvoke-Expression\b|\biex\b'
        r'|\bbash\s+-c\b|\bsh\s+-c\b|\bshell_exec\s*\(|\bnew\s+Function\s*\(')},
    {'kind': 'deser', 're': _rx(
        r'\bpickle\.loads?\s*\(|\bmarshal\.loads?\s*\(|\byaml\.load\s*\((?![^)]*Safe)|\bunserialize\s*\('
        r'|\bMarshal\.load\b|\bBinaryFormatter\b|\bObjectInputStream\b|\bImport-Clixml\b')},
]

SKIP_NAMES: set[str] = {
    'if', 'for', 'in', 'of', 'let', 'var', 'const', 'def', 'return', 'self', 'this', 'None', 'null',
    'true', 'false', 'True', 'False', 'else', 'then', 'do', 'done', 'fi', 'set', 'new', 'not',
    'and',
    'or', 'is', 'as', 'with', 'from', 'import', 'export', 'local', 'param', 'args', 'argv', 'data',
    'text', 'path', 'name', 'out', 'err', 'res', 'tmp',
}

_ASSIGN_RE = _rx(
    r'^\s*(?:export\s+|local\s+|const\s+|let\s+|var\s+|\$)?([A-Za-z_][\w]*)\s*(?::=|\+=|=)(?!=)',
    re.ASCII)
_ASSIGN_PS_RE = _rx(r'^\s*\$([A-Za-z_]\w*)\s*=', re.ASCII)
_NEWLINE_RE = re.compile(r'\r?\n')
_COMMENT_RE = _rx(r'^\s*(#|//|\*|<!--)', re.ASCII)
# A fixed program with an argument array does not go through a shell.
_NO_SHELL_JS_RE = _rx(
    r'''\b(spawnSync|spawn|execFileSync|execFile)\s*\(\s*['"][\w.\/-]+['"]\s*,\s*\[''', re.ASCII)
_SHELL_NAME_RE = _rx(r'''['"](sh|bash|zsh|cmd|cmd\.exe|powershell|pwsh)['"]''', re.ASCII)
_NO_SHELL_PY_RE = _rx(r'\bsubprocess\.\w+\s*\(\s*\[', re.ASCII)
_SHELL_TRUE_RE = _rx(r'shell\s*=\s*True', re.ASCII)

_SEND_SOURCES = ('cred', 'env', 'file', 'ctx')
_EXEC_SOURCES = ('input', 'net', 'file')
_NAME_RES: dict[str, re.Pattern[str]] = {}


def _name_re(name: str) -> re.Pattern[str]:
    """Return the regex that finds a variable reference (plain, $name, or ${name})."""
    rx = _NAME_RES.get(name)
    if rx is None:
        # Not preceded by a word character; optional $ and { before the name; word boundary after.
        rx = re.compile(r'(?<![A-Za-z0-9_])\$?\{?' + re.escape(name) + r'\b', re.ASCII)
        _NAME_RES[name] = rx
    return rx


def assigned_name(line: str) -> str | None:
    """Return the variable assigned on this line, or None."""
    m = _ASSIGN_RE.match(line)
    if m:
        return m.group(1)
    m = _ASSIGN_PS_RE.match(line)
    return m.group(1) if m else None


def _sink_allowed(source_kind: str, sink_kind: str) -> bool:
    """Return True when a source kind reaching a sink kind is worth reporting."""
    if sink_kind == 'send':
        return source_kind in _SEND_SOURCES
    if sink_kind in ('exec', 'deser'):
        return source_kind in _EXEC_SOURCES
    return False


def _is_comment(ln: str) -> bool:
    """Return True for comment-only lines."""
    return _COMMENT_RE.match(ln) is not None


def _propagate(lines: list[str], line_kinds: list[str | None]) -> dict[str, dict[str, Any]]:
    """Follow assignments for three passes and return name -> {kind, line}."""
    tainted: dict[str, dict[str, Any]] = {}
    for _ in range(3):
        for i, ln in enumerate(lines):
            if _is_comment(ln):
                continue
            name = assigned_name(ln)
            if not name or len(name) <= 1 or name in SKIP_NAMES:
                continue
            kind = line_kinds[i]
            from_line = i + 1
            if not kind:
                rhs = ln[ln.find('=') + 1:]
                for n, t in tainted.items():
                    if n != name and _name_re(n).search(rhs):
                        kind = t['kind']
                        from_line = t['line']
                        break
            if kind and name not in tainted:
                tainted[name] = {'kind': kind, 'line': from_line}
    return tainted


def _no_shell(ln: str) -> bool:
    """Return True when an exec call passes an argument array and so skips the shell."""
    no_shell_js = _NO_SHELL_JS_RE.search(ln) is not None and _SHELL_NAME_RE.search(ln) is None
    no_shell_py = _NO_SHELL_PY_RE.search(ln) is not None and _SHELL_TRUE_RE.search(ln) is None
    return no_shell_js or no_shell_py


def analyze(source: str, lang: str | None = None) -> list[dict[str, Any]]:
    """Link sources to sinks in one file and return [{'id','line','evidence','confidence'}]."""
    lines = [text.strip_regex_literals(ln) for ln in _NEWLINE_RE.split(source)[:6000]]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def line_kind(ln: str) -> str | None:
        """The source kind a line introduces, or None."""
        if text.is_pattern_def_line(ln):
            return None
        for s in SOURCES:
            if s['re'].search(ln):
                return str(s['kind'])
        return None

    line_kinds = [line_kind(ln) for ln in lines]
    tainted = _propagate(lines, line_kinds)

    def add(src_line: int, sink_line: int, sk: str, k: str, via: str | None, ln: str) -> None:
        """Record one source-to-sink flow once."""
        key = f'{src_line}:{sink_line}:{sk}{k}'
        if key in seen:
            return
        seen.add(key)
        if k == 'send':
            id_ = 'FLW04' if sk in ('file', 'ctx') else 'FLW03'
        elif k == 'exec':
            id_ = 'FLW05'
        else:
            id_ = 'FLW06'
        via_txt = f' via "{via}"' if via else ''
        out.append({
            'id': id_, 'line': sink_line,
            'evidence': f'{sk} (line {src_line}){via_txt} -> {k}: {ln.strip()[:100]}',
            'confidence': 0.6 if via else 0.75,
        })

    for i, ln in enumerate(lines):
        if _is_comment(ln) or text.is_pattern_def_line(ln):
            continue
        for sink in SINKS:
            if not sink['re'].search(ln):
                continue
            if sink['kind'] == 'exec' and _no_shell(ln):
                continue
            # direct: a source and a sink on the same statement
            lk = line_kinds[i]
            if lk and _sink_allowed(lk, sink['kind']):
                add(i + 1, i + 1, lk, sink['kind'], None, ln)
            for n, t in tainted.items():
                if not _name_re(n).search(ln):
                    continue
                if assigned_name(ln) == n and not sink['re'].search(ln):
                    continue
                if _sink_allowed(t['kind'], sink['kind']):
                    add(t['line'], i + 1, t['kind'], sink['kind'], n, ln)
    return out
