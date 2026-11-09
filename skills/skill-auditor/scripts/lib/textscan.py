"""Per-text rule application: fences, rule loop, hidden-text, URL, and whole-file checks."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import taint, text as textrules
from .catalog import FAMILY_INSTR, LINE_RULES, NORMALIZED_FAMILIES
from .model import (
    Ctx,
    Finding,
    LIM,
    Rule,
    add_host,
    base_of,
    ext_of,
    family_of,
    inspect_kind_label,
    is_test_path,
    step_down,
)
from .text import scan_re
from .util import RE_LINE_SPLIT, round_half_up

__all__ = [
    'TextScan',
    'analyze_text',
]


LANG_BY_EXT: dict[str, str] = {
    '.py': 'py', '.js': 'js', '.mjs': 'js', '.cjs': 'js', '.ts': 'js', '.sh': 'sh', '.bash': 'sh',
    '.zsh': 'sh',
    '.ps1': 'ps', '.psm1': 'ps',
}

# A suppression is a marker inside a comment. A sentence that merely mentions the word does not
# suppress anything.
RE_SUPPRESS_MARK: re.Pattern[str] = scan_re(r'(<!--\s*|#\s*|\/\/\s*|\/\*\s*|--\s+)audit-ignore\b', 'i')

RE_NAME_STRIP: re.Pattern[str] = scan_re(r'[^\w-]')

RE_CATALOG_MARK: re.Pattern[str] = scan_re(r'skill-auditor:\s*catalog', 'i')

RE_WS_RUN: re.Pattern[str] = scan_re(r'\s+')

# Markdown structure.
RE_FENCE_LINE: re.Pattern[str] = scan_re(r'^\s*(```|~~~)(.*)$')

RE_FENCE_BAD_INFO: re.Pattern[str] = scan_re(r'bad|vulnerable|insecure|malicious|attack|wrong|avoid|anti', 'i')

RE_FENCE_BAD_PREV: re.Pattern[str] = scan_re(
    r"\b(bad|avoid|don't|do not|wrong|vulnerable|insecure|attack|anti-?pattern|malicious)\b", 'i')

RE_HEADING: re.Pattern[str] = scan_re(r'^\s{0,3}#{1,6}\s')

RE_PAD_HIT: re.Pattern[str] = scan_re(r'ignore|disregard|system|secret|do not tell', 'i')

RE_LEAD_SPACES: re.Pattern[str] = scan_re(r'^[ \t]{200,}\S')

RE_INNER_SPACES: re.Pattern[str] = scan_re(r'\S[ \t]{200,}\S')

RE_COMMENT_LINE: re.Pattern[str] = scan_re(r'^\s*(#|\/\/|--|\/\*|\*|<!--|REM\b)')

RE_CFG_DATA_FIELD: re.Pattern[str] = scan_re(
    r'^\s*["\']?(title|descriptions?|messages?|patterns?|regex|examples?|names?|rules?|text|summary|remediation'
    r'|fix|help|details?|note|reason|evidence)s?["\']?\s*[:=]', 'i')

RE_CRED_RULE_ID: re.Pattern[str] = scan_re(r'^(CRD01|CRD04)$')

RE_BIDI_OVERRIDE: re.Pattern[str] = scan_re(r'[\u202a-\u202e\u2066-\u2069]')

RE_NON_LATIN: re.Pattern[str] = scan_re(r'[\u0400-\u04ff\u0370-\u03ff]')

RE_FEFF_START: re.Pattern[str] = scan_re(r'^\ufeff')

RE_JOINERS: re.Pattern[str] = re.compile('[\u200d\ufe0f\ufe0e]')

# Approximation of \p{Extended_Pictographic} (Python's re has no Unicode property classes).
RE_PICTOGRAPHIC: re.Pattern[str] = re.compile(
    '[\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u231a-\u23ff\u24c2\u25aa-\u25fe\u2600-\u27bf'
    '\u2934\u2935\u2b05-\u2b55\u3030\u303d\u3297\u3299\U0001f000-\U0001faff]')

RE_HIDDEN_STYLE: re.Pattern[str] = scan_re(
    r'style\s*=\s*["\'][^"\']*(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0'
    r'|color\s*:\s*(#fff(fff)?|white)\b)|<[a-z]+[^>]*\bhidden\b[^>]*>|<(div|span|p)[^>]*aria-hidden', 'i')

RE_MD_COMMENT_LINE: re.Pattern[str] = scan_re(r'^\s*\[\/\/\]:\s*#\s*[("\']')

RE_ENCODED_SKIP: re.Pattern[str] = scan_re(r'integrity|sha(256|384|512)-|"hash"|checksum', 'i')

RE_COMMENT_FAMILY: re.Pattern[str] = scan_re(r'^(SUP02|EXF|CRD)')

RE_DECODE_FAMILY: re.Pattern[str] = scan_re(r'^INJ|^REF|^LEAK')

RE_DECODE_EXEC: re.Pattern[str] = scan_re(r'^(SUP02|SUP03|EXE01|EXE07|SIG0[123]|EXF06|CRD04)$')

RE_FENCE_BLOCK: re.Pattern[str] = scan_re(r'^[ \t]*(```|~~~)[^\n]*\n[\x00-\U0010ffff]*?^[ \t]*\1[^\n]*$', 'm')

RE_NON_NEWLINE: re.Pattern[str] = re.compile(r'[^\n]')

RE_HTML_COMMENT: re.Pattern[str] = scan_re(r'<!--([\x00-\U0010ffff]*?)-->')

RE_AUDIT_IGNORE_START: re.Pattern[str] = scan_re(r'^\s*audit-ignore\b', 'i')

RE_SHEBANG: re.Pattern[str] = scan_re(r'^#!')

RE_CRLF: re.Pattern[str] = scan_re(r'\r\n')

# URLs and hosts.
RE_HTTP: re.Pattern[str] = scan_re(r'https?:\/\/', 'i')

RE_URL: re.Pattern[str] = scan_re(r'''\bhttps?:\/\/([^\s/"'<>)\]\\`]+)([^\s"'<>)\]\\`]*)''', 'i')

RE_URL_AUTH: re.Pattern[str] = scan_re(r'^([^@]+)@')

RE_USERINFO_PREFIX: re.Pattern[str] = scan_re(r'^[^@]*@')

RE_PORT_SUFFIX: re.Pattern[str] = scan_re(r':\d+$')

RE_PLACEHOLDER_HOST: re.Pattern[str] = scan_re(
    r'^(example\.(com|org|net)|localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0|host|hostname|your-?\w*|\$.*|\{.*|<.*'
    r'|x+|foo|bar|test|some\w*\.\w+)$')

RE_LOOPBACK: re.Pattern[str] = scan_re(r'^(localhost|127\.0\.0\.1|\[::1\])$')

RE_HAS_DOT: re.Pattern[str] = scan_re(r'\.')

RE_IP_LITERAL: re.Pattern[str] = scan_re(r'^\d+\.\d+\.\d+\.\d+$')

RE_PLAIN_HTTP: re.Pattern[str] = scan_re(r'^http:', 'i')

RE_SHORTENER: re.Pattern[str] = scan_re(r'^(bit\.ly|tinyurl\.com|t\.co|goo\.gl|is\.gd|cutt\.ly|rb\.gy|ow\.ly|buff\.ly)$')

RE_CAPTURE_HOST: re.Pattern[str] = scan_re(
    r'webhook\.site|requestbin|pipedream\.net|ngrok|trycloudflare|loca\.lt|serveo|pastebin|paste\.ee|transfer\.sh'
    r'|file\.io|0x0\.st|discord(app)?\.com|hooks\.slack\.com|api\.telegram\.org|interact\.sh|oast\.', 'i')

RE_MUTABLE_HOST: re.Pattern[str] = scan_re(r'^(raw|gist)\.githubusercontent\.com$')

RE_URL_CREDENTIALS: re.Pattern[str] = scan_re(r'\/\/[^@/]+@')


def active_rules(custom: list[Rule] | None) -> list[Rule]:
    """Built-in line rules plus any custom ones."""
    return LINE_RULES + custom if custom else LINE_RULES


def analyze_text(ctx: Ctx, rel: str, text: str, info: dict[str, Any]) -> None:
    """Run all text checks on one file's (or archive member's) content."""
    TextScan(ctx, rel, text, info).run()


RE_NON_BLANK: re.Pattern[str] = scan_re(r'\S')


def is_blank(ln: str) -> bool:
    """True for a line with no visible characters (Unicode spaces and a BOM count as blank)."""
    return RE_NON_BLANK.search(ln) is None


def rules_match(rules: list[Rule], haystack: str, predicate: Callable[[Rule], bool]) -> bool:
    """True when some rule accepted by predicate matches the haystack."""
    return any(predicate(r) and r['re'].search(haystack) for r in rules)


@dataclass
class FenceState:
    """Code-fence and heading tracking for markdown."""

    in_fence: bool = False
    fence_bad: bool = False
    heading: str = ''
    prev_text: str = ''

    def update(self, ln: str) -> None:
        """Advance over one markdown line."""
        fm = RE_FENCE_LINE.search(ln)
        if fm:
            self.in_fence = not self.in_fence
            if self.in_fence:
                bad_info = RE_FENCE_BAD_INFO.search(fm.group(2))
                self.fence_bad = bool(bad_info or RE_FENCE_BAD_PREV.search(self.prev_text))
        elif RE_HEADING.search(ln):
            self.heading = ln
        if not fm and ln.strip():
            self.prev_text = ln

    def as_state(self) -> dict[str, Any]:
        """The state dictionary understood by text.classify."""
        return {'inFence': self.in_fence, 'fenceBad': self.fence_bad, 'heading': self.heading}


class PaddingTracker:
    """Detects runs of blank lines and extreme whitespace that push text out of view."""

    def __init__(self, surface: str, rules: list[Rule]) -> None:
        """Start with no blank run."""
        self.surface = surface
        self.rules = rules
        self.blank_run = 0
        self.blank_start = 0
        self.pending: int | None = None

    def feed(self, ln: str, n: int) -> list[Finding]:
        """Process line n; return the INJ06 findings it completes."""
        if is_blank(ln):
            if self.blank_run == 0:
                self.blank_start = n
            self.blank_run += 1
            if self.blank_run == 10 and self.surface == 'md':
                self.pending = self.blank_start
            return []
        out: list[Finding] = []
        if self.pending is not None and self.surface == 'md':
            hit = (rules_match(self.rules, ln, lambda r: r['id'] in NORMALIZED_FAMILIES)
                   or bool(RE_PAD_HIT.search(ln)))
            out.append({
                'id': 'INJ06', 'severity': 'high' if hit else 'medium', 'line': self.pending,
                'message': 'Run of blank lines hides the text that follows',
                'evidence': f'{self.blank_run} blank lines, then: {ln.strip()[:80]}',
                'confidence': 0.85 if hit else 0.5,
            })
            self.pending = None
        self.blank_run = 0
        if RE_LEAD_SPACES.search(ln):
            out.append({'id': 'INJ06', 'severity': 'medium',
                        'message': 'Hundreds of leading spaces push text off screen',
                        'evidence': ln.strip()[:80], 'confidence': 0.6})
        if RE_INNER_SPACES.search(ln):
            out.append({'id': 'INJ06', 'severity': 'medium',
                        'message': 'Hundreds of spaces inside a line hide text to the right',
                        'evidence': ln.strip()[:80], 'confidence': 0.6})
        return out


class RuleRunner:
    """Applies the line rules for one surface and softens results by where the match sits."""

    def __init__(self, rules: list[Rule], surface: str, rel: str, skill_name: str,
                 surf_label: str, catalog: bool) -> None:
        """Remember the per-text facts the context adjustment needs."""
        self.surface = surface
        self.surf_label = surf_label
        self.catalog = catalog
        self.base = base_of(rel)
        self.is_test = is_test_path(rel)
        own_name = RE_NAME_STRIP.sub('', skill_name)
        self.own = re.compile(r'\b' + re.escape(own_name).replace('\\-', '-') + r'\b',
                              re.ASCII | re.IGNORECASE)
        # Rules that can fire in this text, resolved once: (rule, bound search, base severity).
        self.active = [(r, r['re'].search, sev) for r in rules
                       if not (r.get('skipFiles') and r['skipFiles'].search(self.base))
                       and (sev := self.severity_on_surface(r))]

    def severity_on_surface(self, r: Rule) -> str | None:
        """The rule's severity on this surface, or None when it does not apply here."""
        rsev = r['sev']
        return rsev if isinstance(rsev, str) else rsev.get(self.surface)

    def run(self, ln: str, state: dict[str, Any], is_comment: bool) -> list[Finding]:
        """Match one line against every rule for this surface; return the findings."""
        out: list[Finding] = []
        for r, search, base_sev in self.active:
            m = search(ln)
            if not m:
                continue
            skip_if = r.get('skipIf')
            if skip_if and skip_if.search(m.group(0)):
                continue
            if r['id'] == 'SNP03' and self.own.search(m.group(0) + ' ' + ln):
                continue
            sev, conf, context = self.adjust_for_context(r, ln, m, state, base_sev, is_comment)
            if self.is_test:
                conf *= 0.8  # labeled, not excused: a script in tests/ can still be run
            out.append({'id': r['id'], 'severity': sev, 'confidence': conf, 'context': context,
                        'evidence': ln.strip(), 'message': r.get('message')})
        return out

    def adjust_for_context(self, r: Rule, ln: str, m: re.Match[str], state: dict[str, Any],
                           sev: str, is_comment: bool) -> tuple[str, float, str]:
        """Soften severity and confidence by where the match sits (prose, quote, comment, ...)."""
        conf: float = r['conf']
        context = 'code'
        if self.surface == 'md':
            context = textrules.classify(ln, m.start(), state)
            if family_of(r['id']) in FAMILY_INSTR:
                soft = context != 'prose'  # prose aimed at the model: any other context softens it
            else:
                soft = context in ('fence-bad', 'prohibited', 'table', 'quote')  # real blocks stay
            if soft:
                sev = step_down(sev)
                conf *= 0.5
            if self.catalog:
                sev = step_down(step_down(sev))
                conf *= 0.5
                context = 'catalog'
            if self.surf_label == 'docs':
                sev = step_down(sev)
                conf *= 0.7
        elif self.surface == 'code' and (
            textrules.is_pattern_def_line(ln) or textrules.in_regex_literal(ln, m.start())
        ):
            sev = step_down(step_down(sev))
            conf *= 0.3
            context = 'pattern-definition'
        elif is_comment:
            # A comment cannot run, so a command or API named in one is not a capability. Text aimed
            # at the model keeps its weight, because an AI reading the file still follows it.
            if family_of(r['id']) not in FAMILY_INSTR:
                sev = step_down(step_down(sev))
                conf *= 0.5
            else:
                conf *= 0.7
            context = 'comment'
        elif self.surface == 'cfg':
            if RE_CFG_DATA_FIELD.search(ln):
                sev = step_down(step_down(sev))
                conf *= 0.4
                context = 'data-field'
            if self.catalog:
                sev = step_down(step_down(sev))
                conf *= 0.5
                context = 'catalog'
        return sev, conf, context


def normalized_finding(ln: str, norm_rules: list[Rule]) -> list[Finding]:
    """Re-run injection families on normalized text (invisible characters, look-alikes, spacing)."""
    norm = textrules.normalize_for_scan(ln)
    if norm == ln or not norm:
        return []
    for r in norm_rules:
        if r['re'].search(norm) and not r['re'].search(ln):
            return [{
                'id': 'INJ07', 'severity': 'high', 'confidence': 0.85, 'context': 'prose',
                'message': ('Instruction text is disguised (invisible characters, look-alikes, '
                            'or letter spacing) and reads as an attack once cleaned'),
                'evidence': '[cleaned] ' + norm.strip()[:140],
            }]
    return []


def invisible_findings(ln: str, n: int, surface: str, rules: list[Rule]) -> list[Finding]:
    """Report tag-block smuggling, bidirectional overrides, and invisible characters."""
    if not (textrules.has_invisible(ln) or textrules.has_bidi(ln)):
        return []
    hidden = textrules.decode_tags(ln)
    if len(hidden) >= 4:
        hit = rules_match(rules, hidden, lambda r: family_of(r['id']) in FAMILY_INSTR)
        return [{
            'id': 'INJ02', 'severity': 'critical' if hit else 'high', 'confidence': 0.95,
            'message': 'Text hidden in invisible Unicode tag characters (ASCII smuggling)',
            'evidence': 'decoded: ' + hidden[:140],
        }]
    stripped = RE_JOINERS.sub('', ln) if RE_PICTOGRAPHIC.search(ln) else ln
    override = RE_BIDI_OVERRIDE.search(ln)
    if override:
        return [{
            'id': 'INJ02', 'severity': 'high', 'confidence': 0.9,
            'message': ('Bidirectional override characters can reorder text so code or '
                        'instructions read differently than they run'),
            'evidence': 'U+' + format(ord(override.group(0)), 'X'),
        }]
    only_bom = n == 1 and RE_FEFF_START.search(ln) and not textrules.has_invisible(ln[1:])
    if textrules.has_invisible(stripped) and not only_bom:
        first = textrules.INVISIBLE.search(stripped)
        code = format(ord(first.group(0)[0]), 'X') if first else ''
        return [{
            'id': 'INJ02', 'severity': 'high' if surface == 'md' else 'medium', 'confidence': 0.75,
            'message': 'Invisible characters inside text',
            'evidence': f'U+{code} near: {textrules.strip_invisible(ln).strip()[:60]}',
        }]
    return []


def homoglyph_finding(ln: str) -> list[Finding]:
    """Report words that mix Latin with Cyrillic/Greek or are made only of look-alikes."""
    hw = textrules.homoglyph_words(ln)
    if not hw:
        return []
    non_latin = len(RE_NON_LATIN.findall(ln))
    w = next((x for x in hw if x['kind'] == 'mixed-script'), None)
    if w is None and non_latin <= len(hw[0]['word']) * len(hw) + 2:
        w = hw[0]
    if w is None:
        return []
    mixed = w['kind'] == 'mixed-script'
    as_word = w.get('as')
    return [{
        'id': 'INJ09', 'severity': 'medium', 'confidence': 0.8 if mixed else 0.55,
        'message': ('Word mixes Latin letters with Cyrillic or Greek look-alikes' if mixed
                    else 'Word is made of Cyrillic or Greek look-alikes of Latin letters'),
        'evidence': f'"{w["word"]}"' + (f' reads as "{as_word}"' if as_word else ''),
    }]


def hidden_markup_findings(ln: str, in_fence: bool, rules: list[Rule]) -> list[Finding]:
    """Report HTML styled to be invisible and markdown link-reference comments."""
    out: list[Finding] = []
    if RE_HIDDEN_STYLE.search(ln) and not in_fence:
        out.append({'id': 'INJ02', 'severity': 'medium', 'confidence': 0.6,
                    'message': ('HTML styled to be invisible when rendered but still read by the '
                                'model'),
                    'evidence': ln.strip()[:120]})
    if RE_MD_COMMENT_LINE.search(ln) and len(ln) > 60:
        body = RE_MD_COMMENT_LINE.sub('', ln, count=1)
        hit = rules_match(rules, body, lambda r: r['id'] in NORMALIZED_FAMILIES)
        out.append({'id': 'INJ02', 'severity': 'high' if hit else 'medium',
                    'confidence': 0.9 if hit else 0.5,
                    'message': 'Markdown comment: invisible when rendered but read by the model',
                    'evidence': body.strip()[:120]})
    return out


class EncodedScanner:
    """Decodes base64/hex payloads and reports those that read as instructions or commands."""

    def __init__(self, all_rules: list[Rule]) -> None:
        """Allow up to 40 decode attempts per text."""
        self.all_rules = all_rules
        self.budget = 40

    def is_instruction(self, dec: str) -> bool:
        """True when decoded text trips an instruction-family or a command/exfiltration rule."""
        for r in self.all_rules:
            in_family = 'md' in r['on'] and (
                family_of(r['id']) in FAMILY_INSTR or RE_DECODE_FAMILY.search(r['id'])
            )
            if in_family and r['re'].search(dec):
                return True
        return any(RE_DECODE_EXEC.search(r['id']) and r['re'].search(dec) for r in self.all_rules)

    def scan(self, ln: str) -> list[Finding]:
        """Findings for the encoded payloads on one line."""
        if self.budget <= 0 or RE_ENCODED_SKIP.search(ln):
            return []
        out: list[Finding] = []
        for d in textrules.decode_candidates(ln):
            self.budget -= 1
            dec = d['text'][:600]
            shown = f"{d['kind']} -> {RE_WS_RUN.sub(' ', dec[:120])}"
            if self.is_instruction(dec):
                out.append({'id': 'INJ08', 'severity': 'high', 'confidence': 0.9,
                            'message': 'Encoded text decodes to an instruction or command',
                            'evidence': shown})
            elif textrules.LOOKS_EXECUTABLE.search(dec.strip()):
                out.append({'id': 'INJ08', 'severity': 'medium', 'confidence': 0.7,
                            'message': 'Encoded text decodes to a command or URL',
                            'evidence': shown})
        return out


def host_flags(host: str, m: re.Match[str], has_auth: bool) -> list[str]:
    """Risk flags for a URL host."""
    flags: list[str] = []
    if RE_IP_LITERAL.search(host):
        flags.append('ip-literal')
    if RE_PLAIN_HTTP.search(m.group(0)):
        flags.append('plain-http')
    if RE_SHORTENER.search(host):
        flags.append('url-shortener')
    if RE_CAPTURE_HOST.search(host + m.group(2)):
        flags.append('capture-or-tunnel')
    if RE_MUTABLE_HOST.search(host):
        flags.append('mutable-remote-content')
    if has_auth:
        flags.append('credentials-in-url')
    return flags


class UrlScanner:
    """Collects hosts from URLs into the context and flags risky targets in code and config."""

    def __init__(self, ctx: Ctx, rel: str, surface: str, kind: str) -> None:
        """Allow up to 400 URLs per text."""
        self.ctx = ctx
        self.rel = rel
        self.surface = surface
        self.kind = kind
        self.budget = 400

    def scan(self, ln: str, n: int) -> list[Finding]:
        """Record the hosts on one line; return findings for risky URL flags."""
        if self.budget <= 0 or not RE_HTTP.search(ln):
            return []
        out: list[Finding] = []
        for m in RE_URL.finditer(ln):
            old = self.budget
            self.budget -= 1
            if old <= 0:
                break
            authority = m.group(1)
            has_auth = RE_URL_AUTH.search(authority) is not None
            host = RE_PORT_SUFFIX.sub('', RE_USERINFO_PREFIX.sub('', authority)).lower()
            if not host or (RE_PLACEHOLDER_HOST.search(host) and not has_auth):
                if RE_LOOPBACK.search(host):
                    add_host(self.ctx, host, self.rel, n, ['loopback'])
                continue
            if not RE_HAS_DOT.search(host):
                continue
            flags = host_flags(host, m, has_auth)
            add_host(self.ctx, host, self.rel, n, flags)
            if self.surface != 'md':
                out.extend(self.flag_findings(m, flags))
        return out

    def flag_findings(self, m: re.Match[str], flags: list[str]) -> list[Finding]:
        """Findings for URL flags in code and config files."""
        out: list[Finding] = []
        if 'credentials-in-url' in flags:
            out.append({'id': 'CRD01', 'severity': 'high', 'confidence': 0.85,
                        'message': 'URL contains embedded credentials',
                        'evidence': RE_URL_CREDENTIALS.sub('//***@', m.group(0), count=1)})
        if any(f in flags for f in ('plain-http', 'ip-literal', 'url-shortener')):
            shown = ', '.join(f for f in flags if f != 'mutable-remote-content').replace(
                ',', ' and',
            )
            out.append({'id': 'NET01', 'severity': 'medium', 'confidence': 0.6,
                        'message': 'Network target is ' + shown, 'evidence': m.group(0)[:100]})
        if 'mutable-remote-content' in flags and self.kind != 'cfg':
            out.append({'id': 'SUP02', 'severity': 'medium', 'confidence': 0.55,
                        'message': 'Script depends on content fetched from a mutable raw-file URL',
                        'evidence': m.group(0)[:100]})
        return out


def repeated_line_findings(rel: str, label: str, repeat: dict[str, int]) -> list[Finding]:
    """Context stuffing: the same long line repeated many times."""
    for line, count in repeat.items():
        if count >= 20:
            return [{'id': 'MEM02', 'severity': 'medium', 'file': rel, 'line': 1, 'confidence': 0.6,
                     'surface': label,
                     'message': 'The same line repeats many times (context stuffing)',
                     'evidence': f'{count}x: {line[:60]}'}]
    return []


def html_comment_findings(rel: str, label: str, text: str, rules: list[Rule]) -> list[Finding]:
    """Long HTML comments outside code fences: invisible when rendered but read by the model."""
    out: list[Finding] = []
    body = RE_FENCE_BLOCK.sub(lambda b: RE_NON_NEWLINE.sub(' ', b.group(0)), text)
    for m in RE_HTML_COMMENT.finditer(body):
        inner = m.group(1)
        if len(inner.split()) < 12 or RE_AUDIT_IGNORE_START.search(inner):
            continue
        line = len(RE_LINE_SPLIT.split(body[:m.start()]))
        hit = any((r['id'] in NORMALIZED_FAMILIES or RE_COMMENT_FAMILY.search(r['id']))
                  and r['re'].search(inner) for r in rules)
        out.append({'id': 'INJ02', 'severity': 'high' if hit else 'medium', 'file': rel,
                    'line': line, 'confidence': 0.9 if hit else 0.55, 'surface': label,
                    'message': 'HTML comment: invisible when rendered but read by the model',
                    'evidence': RE_WS_RUN.sub(' ', inner.strip())[:140]})
    return out


def minified_findings(rel: str, label: str, text: str, lines: list[str],
                      long_lines: int) -> list[Finding]:
    """Minified or packed code that a reviewer cannot read."""
    avg = len(text) / max(1, len(lines))
    if long_lines > 0 and (avg > 200 or long_lines >= 3 or any(len(x) > 5000 for x in lines)):
        return [{'id': 'ART12', 'severity': 'medium', 'file': rel, 'line': 1, 'confidence': 0.7,
                 'surface': label, 'message': 'Minified or packed code that a reviewer cannot read',
                 'evidence': (f"{long_lines} line(s) over {LIM['lineScan']} characters; "
                              f'average {round_half_up(avg)}')}]
    return []


def flow_findings(rel: str, label: str, text: str) -> list[Finding]:
    """Taint flows from sensitive sources to network or execution sinks."""
    lang = LANG_BY_EXT.get(ext_of(rel))
    if not lang:
        return []
    return [{'id': f['id'], 'severity': None, 'file': rel, 'line': f['line'],
             'confidence': f['confidence'], 'surface': label, 'context': 'flow',
             'evidence': f['evidence']}
            for f in taint.analyze(text, lang)]


def shell_portability_findings(rel: str, label: str, text: str) -> list[Finding]:
    """Shell-script portability: CRLF line endings and a missing shebang."""
    if ext_of(rel) not in ('.sh', '.bash'):
        return []
    out: list[Finding] = []
    if RE_CRLF.search(text):
        out.append({'id': 'PRT04', 'file': rel, 'line': 1, 'surface': label, 'confidence': 0.9,
                    'evidence': 'CRLF line endings'})
    if not RE_SHEBANG.search(text):
        out.append({'id': 'PRT04', 'severity': 'low', 'file': rel, 'line': 1, 'surface': label,
                    'confidence': 0.8, 'evidence': 'no shebang'})
    return out


class TextScan:
    """Scans one text (a file or an archive member) and reports findings into a Ctx."""

    def __init__(self, ctx: Ctx, rel: str, text: str, info: dict[str, Any]) -> None:
        """Prepare the rule lists, scanners, and per-text state."""
        self.ctx = ctx
        self.rel = rel
        self.text = text
        self.surface: str = info['surface']
        self.kind: str = info['kind']
        self.lines = RE_LINE_SPLIT.split(text)
        self.all_rules = active_rules(ctx.opts.get('customRules'))
        self.rules = [r for r in self.all_rules if self.surface in r['on']]
        norm_rules = [
            r for r in self.all_rules if 'md' in r['on'] and r['id'] in NORMALIZED_FAMILIES
        ]
        self.norm_rules = norm_rules
        self.surf_label = 'tests' if is_test_path(rel) else inspect_kind_label(self.kind, rel)
        self.catalog = self.declares_catalog()
        self.runner = RuleRunner(
            self.rules, self.surface, rel, ctx.skill_name, self.surf_label, self.catalog,
        )
        self.fences = FenceState()
        self.padding = PaddingTracker(self.surface, self.rules)
        self.encoded = EncodedScanner(self.all_rules)
        self.urls = UrlScanner(ctx, rel, self.surface, self.kind)
        self.caps = ctx.caps.setdefault(rel, {})
        self.repeat: dict[str, int] = {}
        self.long_lines = 0
        self.n = 0
        self.suppressed = False

    def declares_catalog(self) -> bool:
        """A reference or data file may declare that it lists attack patterns as data."""
        if self.surface == 'code' or self.kind == 'skillmd':
            return False
        if not RE_CATALOG_MARK.search(self.text[:2000]):
            return False
        self.ctx.add({
            'id': 'STR13', 'severity': 'low', 'file': self.rel, 'line': 1, 'confidence': 0.9,
            'surface': self.surf_label,
            'evidence': ('file declares itself a pattern catalog; its findings are downgraded '
                         'and still listed'),
        })
        return True

    def push(self, f: Finding) -> None:
        """Report a finding located on the current line."""
        self.ctx.add({
            'file': self.rel, 'line': self.n, 'surface': self.surf_label,
            '_suppress': self.suppressed, **f,
        })

    def run(self) -> None:
        """Scan every line, then run the whole-file checks."""
        for i, raw in enumerate(self.lines):
            self.scan_line(i, raw)
        whole: list[Finding] = []
        if self.surface == 'md':
            whole += repeated_line_findings(self.rel, self.surf_label, self.repeat)
            whole += html_comment_findings(self.rel, self.surf_label, self.text, self.rules)
        elif self.surface == 'code':
            whole += minified_findings(
                self.rel, self.surf_label, self.text, self.lines, self.long_lines,
            )
            whole += flow_findings(self.rel, self.surf_label, self.text)
            whole += shell_portability_findings(self.rel, self.surf_label, self.text)
        for f in whole:
            self.ctx.add(f)

    def scan_line(self, i: int, raw: str) -> None:
        """Run every per-line check on one line."""
        self.n = i + 1
        ln = raw
        if len(ln) > LIM['lineScan']:
            self.long_lines += 1
            ln = ln[:LIM['lineScan']]
        self.suppressed = bool(
            RE_SUPPRESS_MARK.search(raw) or (i > 0 and RE_SUPPRESS_MARK.search(self.lines[i - 1]))
        )
        md = self.surface == 'md'
        if md:
            self.fences.update(ln)
        for f in self.padding.feed(ln, self.n):
            self.push(f)
        stripped = ln.strip()
        if md and len(stripped) > 12:
            self.repeat[stripped] = self.repeat.get(stripped, 0) + 1
        is_comment = self.surface == 'code' and bool(RE_COMMENT_LINE.search(ln))
        for f in self.runner.run(ln, self.fences.as_state(), is_comment):
            self.push(f)
            self.count_capability(f)
        if md or is_comment or self.surface == 'cfg':
            for f in normalized_finding(ln, self.norm_rules):
                self.push(f)
        for f in invisible_findings(ln, self.n, self.surface, self.rules):
            self.push(f)
        for f in homoglyph_finding(ln):
            self.push(f)
        if md:
            for f in hidden_markup_findings(ln, self.fences.in_fence, self.rules):
                self.push(f)
        for f in self.encoded.scan(ln):
            self.push(f)
        for f in self.urls.scan(ln, self.n):
            self.push(f)

    def count_capability(self, f: Finding) -> None:
        """Count network and credential rule hits per file (to correlate sources with sinks)."""
        if f['context'] in ('pattern-definition', 'catalog', 'data-field'):
            return
        if f['id'] in ('EXF01', 'NET01'):
            self.caps['net'] = self.caps.get('net', 0) + 1
        if RE_CRED_RULE_ID.search(f['id']):
            self.caps['cred'] = self.caps.get('cred', 0) + 1
