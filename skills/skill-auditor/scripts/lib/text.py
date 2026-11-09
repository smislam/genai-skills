"""Text helpers: anti-obfuscation normalization, context classification, encoded-payload decoding.

Rule patterns are compiled through ``scan_re``, which hardens them against look-alike evasion:
``\\w \\d \\b`` stay ASCII-only, ``\\s`` matches every Unicode space (so a no-break space or a
zero-width no-break space cannot split a phrase), ``.`` stops at every line terminator, and ``$``
means end of input.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from typing import Any

__all__ = [
    'INVISIBLE',
    'BIDI',
    'TAGS',
    'LOOKS_EXECUTABLE',
    'scan_re',
    'in_regex_literal',
    'strip_regex_literals',
    'regex_literal_spans',
    'is_pattern_def_line',
    'strip_invisible',
    'has_invisible',
    'has_bidi',
    'decode_tags',
    'map_homoglyphs',
    'homoglyph_words',
    'collapse_spacing',
    'normalize_for_scan',
    'classify',
    'decode_candidates',
    'printable_ratio',
]

# What \s matches in scan patterns: ASCII whitespace plus the Unicode space separators, line
# separators
# and the BOM.
_UNICODE_SPACE: str = r' \t\n\v\f\r\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
# What "." matches in scan patterns (without the s flag): anything but the four line terminators.
_NOT_LINE_BREAK: str = r'[^\n\r\u2028\u2029]'


def scan_re(pattern: str, flags: str = '') -> re.Pattern[str]:
    """Compile a scan pattern (flags among i, s, m) with the hardened semantics described above.

    The expanded ``\\s`` and the ASCII-only ``\\w \\d \\b`` are intentional: they stop a hostile
    file from hiding a phrase behind a no-break space or a look-alike digit or letter.
    """
    out: list[str] = []
    in_class = False
    dotall = 's' in flags
    multiline = 'm' in flags
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == '\\':
            d = pattern[i + 1] if i + 1 < n else ''
            if d == 's':
                out.append(_UNICODE_SPACE if in_class else '[' + _UNICODE_SPACE + ']')
            elif d == 'S':
                if in_class:
                    raise ValueError('\\S inside a character class is not supported')
                out.append('[^' + _UNICODE_SPACE + ']')
            else:
                out.append(c + d)
            i += 2
            continue
        if in_class:
            if c == ']':
                in_class = False
            out.append(c)
        elif c == '[':
            in_class = True
            out.append(c)
            if pattern[i + 1:i + 2] == '^':
                out.append('^')
                i += 1
        elif c == '.' and not dotall:
            out.append(_NOT_LINE_BREAK)
        elif c == '$' and not multiline:
            out.append(r'\Z')
        else:
            out.append(c)
        i += 1
    opts = re.ASCII
    if 'i' in flags:
        opts |= re.IGNORECASE
    if dotall:
        opts |= re.DOTALL
    if multiline:
        opts |= re.MULTILINE
    return re.compile(''.join(out), opts)


# Characters that render as nothing: soft hyphen, joiners, bidi controls, variation selectors, tag
# block.
INVISIBLE: re.Pattern[str] = re.compile(
    r'[\u00ad\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180e\u200b-\u200f\u202a-\u202e'
    r'\u2060-\u2064\u2066-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0]'
    r'|[\U000E0000-\U000E007F]|[\U000E0100-\U000E01EF]'
)
BIDI: re.Pattern[str] = re.compile(r'[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]')
TAGS: re.Pattern[str] = re.compile(r'[\U000E0020-\U000E007E]')

# Common Cyrillic and Greek look-alikes mapped to Latin.
HOMOGLYPH: dict[str, str] = {
    '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p', '\u0441': 'c', '\u0445': 'x',
    '\u0443': 'y', '\u0456': 'i', '\u0458': 'j', '\u0455': 's', '\u04bb': 'h', '\u0501': 'd',
    '\u04cf': 'l', '\u051b': 'q', '\u051d': 'w',
    '\u0410': 'A', '\u0412': 'B', '\u0415': 'E', '\u041a': 'K', '\u041c': 'M', '\u041d': 'H',
    '\u041e': 'O', '\u0420': 'P', '\u0421': 'C', '\u0422': 'T', '\u0425': 'X', '\u0406': 'I',
    '\u0408': 'J', '\u0405': 'S', '\u0423': 'Y',
    '\u03b1': 'a', '\u03bf': 'o', '\u03c1': 'p', '\u03bd': 'v', '\u03b9': 'i', '\u03ba': 'k',
    '\u03c4': 't', '\u03c5': 'u', '\u03c7': 'x', '\u03b5': 'e',
    '\u0391': 'A', '\u0392': 'B', '\u0395': 'E', '\u0396': 'Z', '\u0397': 'H', '\u0399': 'I',
    '\u039a': 'K', '\u039c': 'M', '\u039d': 'N', '\u039f': 'O', '\u03a1': 'P', '\u03a4': 'T',
    '\u03a5': 'Y', '\u03a7': 'X',
}

_LATIN_CHAR = re.compile(r'[A-Za-z]')
_ASCII_LETTERS = scan_re(r'^[A-Za-z]+$')
# Letter-spaced runs: "i g n o r e" (spaces or tabs) and "i.g.n.o.r.e" (. - _ * | / separators).
_SPACED_LETTERS = scan_re(r'\b(?:[A-Za-z][ \t]){5,}[A-Za-z]\b')
_SPACED_SEPARATORS = scan_re(r'\b(?:[A-Za-z][.\-_*|\/]){5,}[A-Za-z]\b')
_SPACE_TAB = re.compile(r'[ \t]')
_SEPARATOR_CHARS = re.compile(r'[.\-_*|\/]')


def strip_invisible(s: str) -> str:
    """Remove invisible and tag-block characters."""
    return INVISIBLE.sub('', s)


def has_invisible(s: str) -> bool:
    """Return True if s contains an invisible character."""
    return INVISIBLE.search(s) is not None


def has_bidi(s: str) -> bool:
    """Return True if s contains a bidirectional control character."""
    return BIDI.search(s) is not None


def decode_tags(s: str) -> str:
    """Decode hidden ASCII 'smuggling' text carried in the Unicode tag block."""
    return ''.join(chr(ord(ch) - 0xE0000) for ch in s if 0xE0020 <= ord(ch) <= 0xE007E)


def map_homoglyphs(s: str) -> str:
    """Map Cyrillic and Greek look-alikes to their Latin letters."""
    return ''.join(HOMOGLYPH.get(ch) or ch for ch in s)


def _scripts_in(word: str) -> set[str]:
    """Return which of latin, cyrillic, greek appear in word."""
    scripts: set[str] = set()
    for ch in word:
        if _LATIN_CHAR.match(ch):
            scripts.add('latin')
        elif '\u0400' <= ch <= '\u04ff':
            scripts.add('cyrillic')
        elif '\u0370' <= ch <= '\u03ff':
            scripts.add('greek')
    return scripts


def _split_words(line: str) -> list[str]:
    """Split on runs of characters that are not letters, numbers or underscore."""
    words: list[str] = []
    current: list[str] = []
    for ch in line:
        if ch == '_' or unicodedata.category(ch)[0] in ('L', 'N'):
            current.append(ch)
        elif current:
            words.append(''.join(current))
            current = []
    if current:
        words.append(''.join(current))
    return words


def homoglyph_words(line: str) -> list[dict[str, str]]:
    """Find words that mix Latin with Cyrillic/Greek, or that are made only of look-alikes."""
    out: list[dict[str, str]] = []
    if line.isascii():  # no Cyrillic or Greek letters can be present
        return out
    for w in _split_words(line):
        if len(w) < 3:
            continue
        scripts = _scripts_in(w)
        if len(scripts) > 1:
            out.append({'word': w, 'kind': 'mixed-script'})
        elif 'cyrillic' in scripts or 'greek' in scripts:
            mapped = map_homoglyphs(w)
            if _ASCII_LETTERS.search(mapped) is not None and len(mapped) >= 4:
                out.append({'word': w, 'kind': 'look-alike', 'as': mapped})
    return out


def collapse_spacing(s: str) -> str:
    """Collapse "i g n o r e", "i.g.n.o.r.e", "i-g-n-o-r-e" runs."""
    s = _SPACED_LETTERS.sub(lambda m: _SPACE_TAB.sub('', m.group(0)), s)
    return _SPACED_SEPARATORS.sub(lambda m: _SEPARATOR_CHARS.sub('', m.group(0)), s)


def normalize_for_scan(line: str) -> str:
    """NFKC-normalize, drop invisibles, map look-alikes, and collapse letter spacing."""
    return collapse_spacing(map_homoglyphs(strip_invisible(unicodedata.normalize('NFKC', line))))


# ---------- context ----------
PROHIBIT_CUE: re.Pattern[str] = scan_re(
    r'\b(no|check\s+for|scan\s+for|grep\s+for|risks?|confusion|compromise|rce|do\s+not|don\'t|never'
    r'|must\s+not|shall\s+not|should\s+not|cannot|can\'t|avoid|reject|refuse\s+to|flag|detect'
    r'|watch\s+for|look\s+for|treat\s+as|attack|malicious|hostile|untrusted|suspicious|example'
    r'|e\.g\.|such\s+as|for\s+instance|phrases?\s+like|patterns?\s+like|prompt\s+injection'
    r'|jailbreak|payload|red\s+flag|signs?\s+of|indicators?|anti-?pattern|insecure|vulnerab\w+)\b',
    'i',
)
EXCEPTION: re.Pattern[str] = scan_re(r'\b(however|but|instead|unless|except)\b', 'i')
BAD_HEADING: re.Pattern[str] = scan_re(
    r'\b(bad|avoid|don\'t|do not|wrong|vulnerable|insecure|attack|anti-?pattern|malicious'
    r'|example attack|red flags?|threats?|detect|signs?)\b',
    'i',
)
IMPERATIVE_BEFORE_QUOTE: re.Pattern[str] = scan_re(
    r'\b(run|execute|invoke|type|paste|pipe|issue|enter|call|use)\s*:?\s*$', 'i'
)
_TABLE_LINE = scan_re(r'^\s*\|')
_SINGLE_QUOTE_OPEN = scan_re(r'(^|[\s(])\'')


def _in_quotes(line: str, idx: int) -> bool:
    """Return True if position idx sits inside an open backtick, double-quote or single-quote."""
    before = line[:idx]
    backticks = before.count('`')
    double = before.count('"')
    single = len(_SINGLE_QUOTE_OPEN.findall(before))
    return backticks % 2 == 1 or double % 2 == 1 or single % 2 == 1


# ---------- pattern definitions and regex literals in code ----------
# Lines that define a pattern (regex literal, re.compile, raw-string regex) mention dangerous text
# without running it.
_PATTERN_DEF_RES: tuple[re.Pattern[str], ...] = (
    # const NAME = /.../flags;  (optionally with a trailing line comment)
    scan_re(
        r'^\s*(?:(?:export\s+)?(?:const|let|var)\s+)?[\w$.\[\]\'"]+\s*[:=]\s*\/(?![\/*]).*\/[gimsuyd]*'
        r'\s*[;,)]?\s*(\/\/.*)?$'
    ),
    # a bare /.../flags, array element
    scan_re(r'^\s*\/(?![\/*]).*\/[gimsuyd]*\s*,\s*$'),
    # Python re.compile(r'...') and friends
    scan_re(r'\bre\.(compile|search|match|findall|sub)\s*\(\s*r?[\'"]'),
    # PATTERN_NAME = r'...' or PATTERN_NAME: re.Pattern[str] = scan_re(r'...'). Only names that look
    # like pattern constants count: a raw string in an ordinary variable could be a command that runs
    # later, so it must not be excused.
    scan_re(
        r'^\s*(?:[A-Z_][A-Z0-9_]*|(?i:\w*(?:_re|_pat|_pattern|_regex|_rx)))\s*(?::[^=]+?)?='
        r'\s*(?:scan_re\(\s*)?r[\'"]'
    ),
    # a line that is only a raw string (one piece of a long pattern split across lines)
    scan_re(r'^\s*[rR][\'"].*[\'"]\s*[,)\]}]*\s*(#.*)?$'),
    scan_re(r'\bnew\s+RegExp\s*\('),
    # rule-table rows such as R('INJ01', ...), ID01: ['... and "ID01": ["... and {'id': 'ID01', ...
    scan_re(r'^\s*R\(\s*[\'"][A-Z]{2,5}\d'),
    scan_re(r'^\s*[A-Z]{2,5}\d{2}\s*:\s*\[\s*[\'"]'),
    scan_re(r'^\s*[\'"][A-Z]{2,5}\d{2}[\'"]\s*:\s*\['),
    scan_re(r'^\s*\{\s*[\'"]id[\'"]\s*:\s*[\'"][A-Z]{2,5}\d'),
)

# A raw string passed straight to a regex function. Compiling or searching with it runs nothing, so a
# dangerous-looking string inside it is pattern data.
_PY_PATTERN_ARG = scan_re(
    r'\b(?:scan_re|_?rx|re\.(?:compile|search|match|fullmatch|findall|finditer|sub|subn|split))\(\s*'
    r'([rR][bB]?)([\'"])'
)

# A regex literal: preceded by start of line or an operator/punctuation, no leading // or /*.
_REGEX_LITERAL = scan_re(
    r'(^|[=(,:;!&|?{\[\s])'
    r'(\/(?![\/*])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^\/\\\n\[])+\/[gimsuyd]*)'
)


def is_pattern_def_line(ln: str) -> bool:
    """Return True if the line defines a pattern rather than running it."""
    return any(pat.search(ln) is not None for pat in _PATTERN_DEF_RES)


def _python_pattern_spans(ln: str) -> list[tuple[int, int]]:
    """Spans of raw string literals passed directly to a regex function (Python code)."""
    spans: list[tuple[int, int]] = []
    for m in _PY_PATTERN_ARG.finditer(ln):
        quote = m.group(2)
        i = m.end()
        while i < len(ln):
            if ln[i] == '\\':
                i += 2
            elif ln[i] == quote:
                i += 1
                break
            else:
                i += 1
        spans.append((m.start(1), min(i, len(ln))))
    return spans


def regex_literal_spans(ln: str) -> list[tuple[int, int]]:
    """Spans (start, end) of regex literals in a code line. A match inside one is pattern data.

    Covers JavaScript-style /.../flags literals and Python raw strings handed to a regex function.
    """
    spans: list[tuple[int, int]] = []
    for m in _REGEX_LITERAL.finditer(ln):
        start = m.start() + len(m.group(1))
        spans.append((start, start + len(m.group(2))))
    spans.extend(_python_pattern_spans(ln))
    return sorted(spans)


def in_regex_literal(ln: str, idx: int) -> bool:
    """Return True if position idx falls inside a regex literal."""
    return any(a <= idx < b for a, b in regex_literal_spans(ln))


def strip_regex_literals(ln: str) -> str:
    """Replace every regex literal with the placeholder RE."""
    pieces: list[str] = []
    pos = 0
    for a, b in regex_literal_spans(ln):
        if a < pos:  # overlaps a span already replaced
            continue
        pieces.append(ln[pos:a])
        pieces.append('RE')
        pos = b
    pieces.append(ln[pos:])
    return ''.join(pieces)


def classify(line: str, idx: int, state: dict[str, Any]) -> str:
    """Classify a match at idx in a line.

    state is {inFence, fenceBad, heading}, maintained by the caller per line.
    Returns 'fence-bad' | 'table' | 'quote' | 'prohibited' | 'fence' | 'prose'.
    """
    in_fence = bool(state.get('inFence'))
    if in_fence and state.get('fenceBad'):
        return 'fence-bad'
    if _TABLE_LINE.search(line) is not None:
        return 'table'
    sentence_start = max(line.rfind('. ', 0, idx + 2), line.rfind('; ', 0, idx + 2), 0)
    lead = line[sentence_start:idx]
    cue = PROHIBIT_CUE.search(lead)
    if cue is not None and EXCEPTION.search(lead[cue.start():]) is None:
        return 'prohibited'
    heading = state.get('heading')
    if heading and BAD_HEADING.search(heading) is not None:
        return 'prohibited'
    if not in_fence and _in_quotes(line, idx):
        q = max(line.rfind('`', 0, idx + 1), line.rfind('"', 0, idx + 1))
        if q >= 0 and IMPERATIVE_BEFORE_QUOTE.search(line[max(0, q - 25):q]) is not None:
            return 'prose'
        return 'quote'
    if in_fence:
        return 'fence'
    return 'prose'


# ---------- encoded payloads ----------
_B64_TOKEN = scan_re(r'(?<![A-Za-z0-9+\/_-])[A-Za-z0-9+\/_-]{32,}={0,2}(?![A-Za-z0-9+\/_-])')
_HEX_ONLY = scan_re(r'^[0-9a-f]+$', 'i')
_HEX_RUN = scan_re(r'(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}){24,}(?![0-9A-Fa-f])')
_HEX_ESCAPES = scan_re(r'(?:\\x[0-9A-Fa-f]{2}){12,}')

LOOKS_EXECUTABLE: re.Pattern[str] = scan_re(
    r'^(#!|https?:\/\/|curl\s|wget\s|powershell|pwsh|cmd(\.exe)?\s|bash\s|sh\s|python3?\s|node\s'
    r'|import\s|eval|exec|<script)',
    'i',
)


def printable_ratio(buf: bytes) -> float:
    """Fraction of bytes that are printable ASCII, tab, LF or CR."""
    if not buf:
        return 0
    ok = sum(1 for b in buf if 32 <= b < 127 or b in (9, 10, 13))
    return ok / len(buf)


def _b64_decode_lenient(token: str) -> bytes:
    """Decode base64, tolerating missing padding and one dangling character."""
    data = token.rstrip('=')
    if len(data) % 4 == 1:
        data = data[:-1]
    data += '=' * (-len(data) % 4)
    return base64.b64decode(data)


def _decoded(kind: str, buf: bytes) -> dict[str, str]:
    """Build a candidate record from decoded bytes."""
    return {'kind': kind, 'text': buf.decode('utf-8', errors='replace')}


def decode_candidates(line: str) -> list[dict[str, str]]:
    """Decode base64, hex and \\x-escape runs in a line that look like printable text."""
    out: list[dict[str, str]] = []
    for m in _B64_TOKEN.finditer(line):
        if len(out) >= 4:
            break
        raw = m.group(0)
        if _HEX_ONLY.search(raw) is not None:
            continue
        tok = raw.replace('-', '+').replace('_', '/')
        try:
            buf = _b64_decode_lenient(tok)
        except (binascii.Error, ValueError):
            continue
        if len(buf) >= 16 and printable_ratio(buf) >= 0.92:
            out.append(_decoded('base64', buf))
    for m in _HEX_RUN.finditer(line):
        if len(out) >= 6:
            break
        buf = bytes.fromhex(m.group(0))
        if printable_ratio(buf) >= 0.92:
            out.append(_decoded('hex', buf))
    esc = _HEX_ESCAPES.search(line)
    if esc is not None:
        buf = bytes.fromhex(esc.group(0).replace('\\x', ''))
        if printable_ratio(buf) >= 0.92:
            out.append(_decoded('hex-escape', buf))
    return out
