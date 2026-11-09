"""Binary and container inspection.

File type from magic bytes, ZIP-compatible archives (including Office files and jars) with bomb
limits, PNG/JPEG/GIF/WebP structure and hidden text, PDF active content. Everything is read in
memory. Nothing is extracted to disk and nothing is executed.
"""

from __future__ import annotations

import ntpath
import re
import struct
import time
import zlib
from collections.abc import Callable
from typing import Any

__all__ = [
    'BINARY_TYPES', 'EXEC_EXT', 'LIMITS', 'TEXTISH', 'ZIP_EXT',
    'crc32', 'detect', 'inspect', 'list_zip', 'read_entry', 'readable', 'strings',
]

LIMITS: dict[str, int] = {
    'depth': 3, 'members': 4096, 'expandedBytes': 25 * 1024 * 1024,
    'memberBytes': 1000000, 'ratio': 100, 'ms': 5000,
}

_RA: int = re.ASCII
_RAI: int = re.ASCII | re.IGNORECASE

Finder = Callable[..., None]
Result = dict[str, Any]

BINARY_TYPES: set[str] = {
    'elf', 'pe', 'macho', 'class-or-macho', 'wasm', 'sqlite', 'ole', '7z', 'rar',
}
EXPECT: dict[str, str] = {
    '.png': 'png', '.jpg': 'jpeg', '.jpeg': 'jpeg', '.gif': 'gif', '.webp': 'webp',
    '.pdf': 'pdf', '.gz': 'gzip', '.tgz': 'gzip', '.bmp': 'bmp',
}
ZIP_EXT: set[str] = {
    '.zip', '.jar', '.war', '.whl', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.epub',
    '.vsix', '.nupkg', '.egg', '.apk', '.xpi', '.crx', '.skill', '.docm', '.xlsm', '.pptm',
}
OFFICE_EXT: set[str] = {
    '.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm', '.odt', '.ods', '.odp',
}
EXEC_EXT: set[str] = {
    '.sh', '.bash', '.bat', '.cmd', '.ps1', '.psm1', '.py', '.pl', '.rb', '.js', '.mjs', '.vbs',
    '.vbe', '.wsf', '.hta', '.exe', '.dll', '.so', '.dylib', '.jar', '.class', '.scr', '.com',
    '.msi', '.lnk', '.jse', '.pyc', '.node',
}
TEXTISH: set[str] = {
    '.md', '.txt', '.json', '.yml', '.yaml', '.toml', '.xml', '.html', '.htm', '.css', '.csv',
    '.ini', '.cfg', '.rels', '.svg', '.sh', '.bash', '.bat', '.cmd', '.ps1', '.psm1', '.py',
    '.pl', '.rb', '.js', '.mjs', '.cjs', '.ts', '.vbs', '.wsf', '.hta', '.rtf', '.tex',
}

_GIF_RE = re.compile(r'GIF8[79]a', _RA)
_XMP_RE = re.compile(r'xap|xmp', _RAI)
_TAG_RE = re.compile(r'<[^>]+>', _RA)
_PATH_SEP_RE = re.compile(r'[\\/]', _RA)
_PDF_FLAGS: list[tuple[str, str]] = [
    ('/JavaScript', 'high'), ('/JS', 'high'), ('/OpenAction', 'high'), ('/Launch', 'high'),
    ('/EmbeddedFile', 'high'), ('/AA', 'medium'), ('/SubmitForm', 'medium'),
    ('/RichMedia', 'high'), ('/XFA', 'medium'),
]
# Each marker must not be followed by a letter (so /JS does not match /JavaScript).
_PDF_FLAG_RES: list[tuple[str, str, re.Pattern[str]]] = [
    (k, sev, re.compile(re.escape(k) + r'(?![A-Za-z])', _RA)) for k, sev in _PDF_FLAGS
]
# Lazy match of a PDF stream body between "stream" and "endstream".
_PDF_STREAM_RE = re.compile(r'stream\r?\n([\s\S]*?)\r?\nendstream', _RA)
# Parenthesized PDF text strings of 6+ characters (a string never spans a line break).
_PDF_TEXT_RE = re.compile(r'\(((?:\\[^\n\r]|[^\\)]){6,})\)', _RA)
# Zip slip: absolute path or drive letter at the start.
_SLIP_START_RE = re.compile(r'^([\\/]|[A-Za-z]:)', _RA)
_MACRO_RE = re.compile(r'vbaProject\.bin\Z|ActiveX|oleObject\d*\.bin|/macros?/', _RAI)
_RELS_RE = re.compile(r'\.rels\Z', _RAI)
_REL_TAG_RE = re.compile(r'<Relationship\b[^>]*>', _RA)
_EXT_MODE_RE = re.compile(r'TargetMode="External"', _RAI)
_EXT_KIND_RE = re.compile(
    r'(attachedTemplate|oleObject|externalLink|frame|subDocument|package|externalData)', _RAI)
_TARGET_RE = re.compile(r'Target="([^"]+)"', _RA)


def _byte_at(b: bytes, i: int) -> int:
    """b[i], or 0 when i is outside the buffer (truncated input must not raise)."""
    return b[i] if 0 <= i < len(b) else 0


def _latin1_before(data: bytes, end: int) -> str:
    """data[:end] decoded as Latin-1; empty when end is not past the start."""
    return data[:end].decode('latin1') if end > 0 else ''


def crc32(buf: bytes) -> int:
    """Return the CRC-32 (PNG/zip polynomial) of buf as an unsigned integer."""
    return zlib.crc32(buf) & 0xFFFFFFFF


def _u32be(b: bytes, i: int) -> int:
    """Big-endian unsigned 32-bit integer at offset i."""
    return int(struct.unpack_from('>I', b, i)[0])


def _u32le(b: bytes, i: int) -> int:
    """Little-endian unsigned 32-bit integer at offset i."""
    return int(struct.unpack_from('<I', b, i)[0])


def _u16le(b: bytes, i: int) -> int:
    """Little-endian unsigned 16-bit integer at offset i."""
    return int(struct.unpack_from('<H', b, i)[0])


def _u16be(b: bytes, i: int) -> int:
    """Big-endian unsigned 16-bit integer at offset i."""
    return int(struct.unpack_from('>H', b, i)[0])


def _inflate(raw: bytes, max_len: int, wbits: int) -> bytes | None:
    """Return the decompressed bytes, or None when corrupt, truncated, or longer than max_len."""
    try:
        d = zlib.decompressobj(wbits)
        out = d.decompress(raw, max_len + 1)
    except zlib.error:
        return None
    if len(out) > max_len or not d.eof:
        return None
    return out


def detect(buf: bytes) -> str | None:
    """Return the file type from magic bytes, or None when unknown."""
    b = buf
    n = len(b)
    if n >= 8 and b[0] == 0x89 and b[1:4] == b'PNG':
        return 'png'
    if n >= 3 and b[0] == 0xFF and b[1] == 0xD8 and b[2] == 0xFF:
        return 'jpeg'
    if n >= 6 and _GIF_RE.match(b[0:6].decode('latin1')):
        return 'gif'
    if n >= 12 and b[0:4] == b'RIFF' and b[8:12] == b'WEBP':
        return 'webp'
    if n >= 5 and b[0:5] == b'%PDF-':
        return 'pdf'
    if n >= 4 and b[0] == 0x50 and b[1] == 0x4B and b[2] in (3, 5):
        return 'zip'
    if n >= 4 and b[0] == 0x7F and b[1:4] == b'ELF':
        return 'elf'
    if n >= 2 and b[0] == 0x4D and b[1] == 0x5A:
        return 'pe'
    if n >= 4:
        m = _u32be(b, 0)
        if m == 0xCAFEBABE:
            return 'class-or-macho'
        if m in (0xFEEDFACE, 0xFEEDFACF, 0xCEFAEDFE, 0xCFFAEDFE):
            return 'macho'
    if n >= 4 and b[0] == 0 and b[1:4] == b'asm':
        return 'wasm'
    if n >= 2 and b[0] == 0x1F and b[1] == 0x8B:
        return 'gzip'
    if n >= 6 and b[0:6] == b'7z\xbc\xaf\x27\x1c':
        return '7z'
    if n >= 4 and b[0:4] == b'Rar!':
        return 'rar'
    if n >= 16 and b[0:15] == b'SQLite format 3':
        return 'sqlite'
    if n >= 8 and b[0] == 0xD0 and b[1] == 0xCF and b[2] == 0x11 and b[3] == 0xE0:
        return 'ole'
    if n >= 262 and b[257:262] == b'ustar':
        return 'tar'
    if n >= 2 and b[0:2] == b'BM':
        return 'bmp'
    return None


def _extname(path: str) -> str:
    """The file extension of a path, treating both / and \\ as separators."""
    return ntpath.splitext(path)[1]


def _mismatch(rel: str, type_: str | None) -> str | None:
    """Describe an extension/content mismatch, or return None."""
    ext = _extname(rel).lower()
    if type_ is None:
        return None
    if ext in EXPECT:
        return None if EXPECT[ext] == type_ else f'extension {ext} but content is {type_}'
    if ext in ZIP_EXT:
        return None if type_ == 'zip' else f'extension {ext} but content is {type_}'
    if ext in TEXTISH or ext == '':
        return f"extension {ext or '(none)'} but content is {type_}"
    return None


def readable(buf: bytes) -> bool:
    """Return True when the first 4 KiB is printable enough to treat as text."""
    head = buf[:4096]
    n = len(head)
    ok = sum(1 for c in head if c in (9, 10, 13) or 32 <= c < 127 or c >= 128)
    return n == 0 or ok / n > 0.95


def strings(buf: bytes, min_len: int) -> list[str]:
    """Return runs of printable ASCII at least min_len long."""
    out: list[str] = []
    cur: list[str] = []
    for c in buf:
        if 32 <= c < 127:
            cur.append(chr(c))
        else:
            if len(cur) >= min_len:
                out.append(''.join(cur))
            cur = []
    if len(cur) >= min_len:
        out.append(''.join(cur))
    return out


# ---------- ZIP ----------
def list_zip(buf: bytes) -> Result:
    """Read the central directory by hand and return {'entries', ...} or {'entries', 'error'}."""
    n = len(buf)
    lo = max(0, n - 65557)
    eocd = buf.rfind(b'PK\x05\x06', lo, n - 22 + 4) if n - 22 >= lo else -1
    if eocd < 0:
        return {'entries': [], 'error': 'no end-of-central-directory record'}
    total = _u16le(buf, eocd + 10)
    cd_off = _u32le(buf, eocd + 16)
    if total == 0xFFFF or cd_off == 0xFFFFFFFF:
        return {'entries': [], 'error': 'zip64 archive (not supported)'}
    entries: list[dict[str, Any]] = []
    p = cd_off
    for _ in range(total):
        if p + 46 > n or _u32le(buf, p) != 0x02014b50:
            break
        flags, method = struct.unpack_from('<HH', buf, p + 8)
        csize, usize = struct.unpack_from('<II', buf, p + 20)
        nl, el, cl = struct.unpack_from('<HHH', buf, p + 28)
        off = _u32le(buf, p + 42)
        entries.append({
            'name': buf[p + 46:p + 46 + nl].decode('utf-8', errors='replace'), 'flags': flags,
            'method': method,
            'csize': csize, 'usize': usize, 'off': off,
        })
        p += 46 + nl + el + cl
    trailing = n - (eocd + 22 + _u16le(buf, eocd + 20))
    return {'entries': entries, 'trailing': trailing, 'declared': total}


def read_entry(buf: bytes, e: dict[str, Any], max_len: int) -> bytes | None:
    """Return one entry's bytes (stored or deflated, capped at max_len), or None."""
    if e['off'] + 30 > len(buf) or _u32le(buf, e['off']) != 0x04034b50:
        return None
    nl, el = struct.unpack_from('<HH', buf, e['off'] + 26)
    start = e['off'] + 30 + nl + el
    raw = buf[start:start + e['csize']]
    if e['method'] == 0:
        return raw
    if e['method'] == 8:
        return _inflate(raw, max_len, -15)
    return None


def inspect(
    buf: bytes, rel: str, budget: dict[str, Any] | None = None, depth: int | None = None,
) -> Result:
    """Inspect buf and return {'type', 'findings', 'members', 'partial', 'notes'}."""
    if budget is None:
        budget = {'members': 0, 'bytes': 0, 'start': time.time() * 1000}
    depth = depth or 0
    res: Result = {
        'type': detect(buf), 'findings': [], 'members': [], 'partial': False, 'notes': [],
    }

    def f(
        id_: str, severity: str, message: str, evidence: str | None = None,
        conf: float | None = None,
    ) -> None:
        """Record one finding."""
        res['findings'].append({
            'id': id_, 'severity': severity, 'message': message,
            'evidence': evidence or '', 'confidence': conf or 0.85,
        })

    ext = _extname(rel).lower()
    t = res['type']

    mm = _mismatch(rel, t)
    if mm and not (t == 'zip' and ext in ZIP_EXT):
        f('ART01', 'high' if (t in BINARY_TYPES or t == 'zip') else 'medium',
          'File content does not match its extension', mm, 0.9)

    if t == 'png':
        _inspect_png(buf, rel, res, f)
    elif t == 'jpeg':
        _inspect_jpeg(buf, rel, res, f)
    elif t == 'gif':
        _inspect_gif(buf, rel, res, f)
    elif t == 'webp':
        _inspect_webp(buf, rel, res, f)
    elif t == 'pdf':
        _inspect_pdf(buf, rel, res, f)
    elif t == 'zip':
        _inspect_zip(buf, rel, res, f, budget, depth)
    elif t in ('gzip', 'tar', '7z', 'rar'):
        res['partial'] = True
        res['notes'].append(f'{t} archive contents were not opened')
        f(
            'ART06', 'medium',
            'Archive type that this auditor does not open; its contents are not inspected', t, 0.7,
        )
    elif t in BINARY_TYPES:
        f('ART11', 'high', 'Executable or binary file; its behavior cannot be reviewed', t, 0.95)
        res['partial'] = True
    elif t == 'bmp':
        res['partial'] = True
        res['notes'].append('bmp: structure not validated')
    return res


def _trailing_check(buf: bytes, end: int, res: Result, f: Finder, label: str) -> None:
    """Report data that follows the logical end of a file."""
    extra = len(buf) - end
    if extra <= 0:
        return
    tail = buf[end:min(len(buf), end + 8)]
    sig = detect(buf[end:end + 512])
    if sig and sig not in ('png', 'jpeg'):
        f(
            'ART09', 'high', f'Data after the end of the {label}: a hidden {sig} file',
            f'{extra} trailing bytes', 0.9,
        )
    elif tail.decode('latin1').startswith('#!'):
        f('ART09', 'high', f'Script after the end of the {label}', f'{extra} trailing bytes', 0.9)
    elif extra > 16:
        f(
            'ART07', 'medium', f'Unexplained data after the end of the {label}',
            f'{extra} trailing bytes', 0.7,
        )


def _push_text(res: Result, vpath: str, text: str, kind: str | None = None) -> None:
    """Add a text member unless it is blank."""
    if text and text.strip():
        res['members'].append({'path': vpath, 'text': text, 'kind': kind or 'meta'})


def _text_len(res: Result) -> int:
    """Return the total length of the collected member text."""
    return sum(len(m['text']) for m in res['members'])


def _png_itxt(data: bytes) -> tuple[str, str]:
    """Return (keyword, text) of an iTXt chunk."""
    z = data.find(b'\x00')
    z2 = data.find(b'\x00', z + 3)
    z3 = data.find(b'\x00', z2 + 1)
    txt = data[z3 + 1:]
    if _byte_at(data, z + 1) == 1:
        out = _inflate(txt, 200000, 15)
        txt = out if out is not None else b''
    return data[:z].decode('utf-8', errors='replace') if z > 0 else '', txt.decode(
        'utf-8', errors='replace',
    )


def _inspect_png(buf: bytes, rel: str, res: Result, f: Finder) -> None:
    """Walk PNG chunks, collecting hidden text and structural problems."""
    p = 8
    saw_end = False
    saw_ihdr = False
    n = len(buf)
    while p + 12 <= n:
        ln = _u32be(buf, p)
        type_ = buf[p + 4:p + 8].decode('latin1')
        if p + 12 + ln > n:
            f(
                'ART07', 'medium',
                'PNG chunk runs past the end of the file (truncated or malformed)', type_, 0.7,
            )
            return
        data = buf[p + 8:p + 8 + ln]
        crc = _u32be(buf, p + 8 + ln)
        if crc32(buf[p + 4:p + 8 + ln]) != crc:
            f('ART07', 'medium', 'PNG chunk fails its checksum (tampered or malformed)', type_, 0.8)
        if type_ == 'IHDR':
            saw_ihdr = True
        if type_ == 'tEXt':
            z = data.find(b'\x00')
            _push_text(res, f'{rel}#tEXt:{_latin1_before(data, z)}', data[z + 1:].decode('latin1'))
        elif type_ == 'zTXt':
            z = data.find(b'\x00')
            out = _inflate(data[z + 2:], 200000, 15)
            if out is not None:
                _push_text(res, f'{rel}#zTXt:{_latin1_before(data, z)}', out.decode('latin1'))
            else:
                f('ART07', 'low', 'Unreadable compressed PNG text chunk', 'zTXt', 0.5)
        elif type_ == 'iTXt':
            key, txt = _png_itxt(data)
            _push_text(res, f'{rel}#iTXt:{key}', txt)
        elif type_ == 'eXIf':
            for i, s in enumerate(strings(data, 24)):
                _push_text(res, f'{rel}#eXIf:{i}', s)
        p += 12 + ln
        if type_ == 'IEND':
            saw_end = True
            break
    if not saw_ihdr:
        f('ART07', 'medium', 'PNG has no header chunk', '', 0.7)
    if not saw_end:
        f('ART07', 'medium', 'PNG has no end chunk', '', 0.6)
    else:
        _trailing_check(buf, p, res, f, 'PNG')
    text_len = _text_len(res)
    if text_len >= 60:
        f('ART07', 'medium',
          'PNG carries text metadata that an image viewer never shows but a model could read',
          f'{text_len} characters', 0.7)


def _inspect_jpeg(buf: bytes, rel: str, res: Result, f: Finder) -> None:
    """Walk JPEG segments, collecting comments, EXIF and XMP text."""
    p = 2
    saw_eoi = False
    n = len(buf)
    while p + 4 <= n:
        if buf[p] != 0xFF:
            f('ART07', 'medium', 'JPEG marker structure is broken', f'offset {p}', 0.6)
            return
        m = buf[p + 1]
        while m == 0xFF and p + 2 < n:
            p += 1
            m = buf[p + 1]
        if m == 0xFF:  # fill bytes run to the end of the file: no marker follows
            break
        if m == 0xD9:
            saw_eoi = True
            p += 2
            break
        if m == 0x01 or 0xD0 <= m <= 0xD8:
            p += 2
            continue
        if p + 4 > n:  # the segment header is cut off
            break
        ln = _u16be(buf, p + 2)
        seg = buf[p + 4:p + 2 + ln]
        if m == 0xFE:
            _push_text(res, f'{rel}#COM', seg.decode('latin1'))
        elif m == 0xE1:
            if seg[0:4].decode('latin1') == 'Exif':
                for i, s in enumerate(strings(seg, 24)):
                    _push_text(res, f'{rel}#EXIF:{i}', s)
            elif _XMP_RE.search(seg[0:30].decode('latin1')):
                _push_text(
                    res, f'{rel}#XMP', _TAG_RE.sub(' ', seg.decode('utf-8', errors='replace')),
                )
        p += 2 + ln
        if m == 0xDA:  # scan data until the next real marker
            while p + 1 < n and not (
                buf[p] == 0xFF and buf[p + 1] != 0x00 and not 0xD0 <= buf[p + 1] <= 0xD7
            ):
                p += 1
    if not saw_eoi:
        f('ART07', 'low', 'JPEG has no end marker', '', 0.5)
    else:
        _trailing_check(buf, p, res, f, 'JPEG')
    text_len = _text_len(res)
    if text_len >= 60:
        f('ART07', 'medium',
          'JPEG carries comment or metadata text that an image viewer never shows',
          f'{text_len} characters', 0.7)


def _gif_skip_sub(buf: bytes, p: int) -> int:
    """Skip GIF data sub-blocks starting at p and return the new offset."""
    n = len(buf)
    while p < n and buf[p] != 0:
        p += buf[p] + 1
    return p + 1


def _inspect_gif(buf: bytes, rel: str, res: Result, f: Finder) -> None:
    """Walk GIF blocks, collecting comment extensions."""
    n = len(buf)
    p = 13
    flags = _byte_at(buf, 10)
    if flags & 0x80:
        p += 3 * (1 << ((flags & 7) + 1))
    ended = False
    while p < n:
        b = buf[p]
        p += 1
        if b == 0x3B:
            ended = True
            break
        if b == 0x21:
            label = _byte_at(buf, p)
            p += 1
            if label == 0xFE:
                parts: list[str] = []
                while p < n and buf[p] != 0:
                    parts.append(buf[p + 1:p + 1 + buf[p]].decode('latin1'))
                    p += buf[p] + 1
                p += 1
                _push_text(res, f'{rel}#comment', ''.join(parts))
            else:
                p = _gif_skip_sub(buf, p)
        elif b == 0x2C:
            lf = _byte_at(buf, p + 8)
            p += 9
            if lf & 0x80:
                p += 3 * (1 << ((lf & 7) + 1))
            p = _gif_skip_sub(buf, p + 1)
        else:
            break
    if not ended:
        f('ART07', 'low', 'GIF has no trailer', '', 0.5)
    else:
        _trailing_check(buf, p, res, f, 'GIF')
    text_len = _text_len(res)
    if text_len >= 60:
        f('ART07', 'medium', 'GIF carries comment text that an image viewer never shows',
          f'{text_len} characters', 0.7)


def _inspect_webp(buf: bytes, rel: str, res: Result, f: Finder) -> None:
    """Walk WebP chunks, collecting EXIF and XMP strings."""
    size = _u32le(buf, 4) + 8
    if size < len(buf):
        _trailing_check(buf, size, res, f, 'WebP')
    p = 12
    while p + 8 <= min(size, len(buf)):
        type_ = buf[p:p + 4].decode('latin1')
        ln = _u32le(buf, p + 4)
        if type_ in ('EXIF', 'XMP '):
            for i, s in enumerate(strings(buf[p + 8:p + 8 + ln], 24)):
                _push_text(res, f'{rel}#{type_.strip()}:{i}', s)
        p += 8 + ln + (ln & 1)


def _inspect_pdf(buf: bytes, rel: str, res: Result, f: Finder) -> None:
    """Check a PDF for active-content markers, flate text streams, and readable strings."""
    s = buf.decode('latin1')
    for k, sev, rx in _PDF_FLAG_RES:
        if rx.search(s):
            f('ART08', sev, f'PDF contains {k} (active or embedded content)', k, 0.8)
    eof = s.rfind('%%EOF')
    if eof >= 0 and len(buf) - (eof + 5) > 64:
        _trailing_check(buf, eof + 5, res, f, 'PDF')
    n = 0
    pos = 0
    while n < 20:
        m = _PDF_STREAM_RE.search(s, pos)
        if not m:
            break
        pos = m.end()
        n += 1
        out = _inflate(m.group(1).encode('latin1'), 400000, 15)
        if out is not None:
            txt = ' '.join(x.group(1) for x in _PDF_TEXT_RE.finditer(out.decode('latin1')))
            if len(txt) > 20:
                _push_text(res, f'{rel}#stream:{n}', txt)
    for i, x in enumerate(strings(buf, 40)[:20]):
        _push_text(res, f'{rel}#str:{i}', x)
    res['partial'] = True
    res['notes'].append(
        'pdf: text extraction is partial; active-content markers and readable strings were checked'
    )


def _check_rels(data: bytes, f: Finder) -> None:
    """Flag Office relationships that load external templates or objects."""
    txt = data.decode('utf-8', errors='replace')
    for m in _REL_TAG_RE.finditer(txt):
        tag = m.group(0)
        if _EXT_MODE_RE.search(tag) and _EXT_KIND_RE.search(tag):
            tm = _TARGET_RE.search(tag)
            f('ART08', 'high',
              'Office relationship loads external content (template or object injection)',
              (tm.group(1) if tm else None) or tag[:100], 0.85)


def _merge_inner(res: Result, inner: Result) -> None:
    """Fold a nested inspection result into the parent result."""
    res['findings'].extend(inner['findings'])
    res['members'].extend(inner['members'])
    if inner['partial']:
        res['partial'] = True


def _member_budget(res: Result, f: Finder, budget: dict[str, Any]) -> bool:
    """Count one more archive member against the shared budget; True when inspection must stop."""
    budget['members'] += 1
    if budget['members'] - 1 >= LIMITS['members']:
        res['partial'] = True
        f(
            'ART06', 'high',
            f"Archive has more than {LIMITS['members']} members; the rest were not opened", '',
            0.85,
        )
        return True
    if time.time() * 1000 - budget['start'] > LIMITS['ms']:
        res['partial'] = True
        f('ART06', 'medium', 'Archive inspection ran out of time; the rest was not opened', '', 0.7)
        return True
    return False


def _member_precheck(e: dict[str, Any], res: Result, f: Finder, budget: dict[str, Any]) -> str:
    """Decide whether a member can be read: 'read', 'skip' (go on with the next), or 'stop'."""
    name = e['name']
    if _SLIP_START_RE.search(name) or '..' in _PATH_SEP_RE.split(name) or '\x00' in name:
        f('ART13', 'high', 'Archive member path escapes its folder (zip slip)', name, 0.9)
    if e['flags'] & 1:
        f('ART06', 'high', 'Encrypted archive member cannot be inspected', name, 0.9)
        res['partial'] = True
        return 'skip'
    if name.endswith('/'):
        return 'skip'
    if e['csize'] > 0 and e['usize'] / e['csize'] > LIMITS['ratio'] and e['usize'] > 1024 * 1024:
        f(
            'ART06', 'high', f"Compression ratio over {LIMITS['ratio']}:1 (possible zip bomb)",
            name, 0.9,
        )
        res['partial'] = True
        return 'skip'
    if e['usize'] > LIMITS['memberBytes']:
        f(
            'ART06', 'low', 'Archive member too large to inspect', f"{name} ({e['usize']} bytes)",
            0.6,
        )
        res['partial'] = True
        return 'skip'
    if budget['bytes'] + e['usize'] > LIMITS['expandedBytes']:
        f('ART06', 'high', 'Archive expands past the total inspection budget', name, 0.8)
        res['partial'] = True
        return 'stop'
    return 'read'


def _scan_member(name: str, data: bytes, vpath: str, res: Result, f: Finder, budget: dict[str, Any],
                 depth: int) -> bool:
    """Classify a member's bytes and collect its text; True when it looks executable."""
    mext = _extname(name).lower()
    mtype = detect(data)
    is_script_text = data[0:2] == b'#!'
    is_exec = mext in EXEC_EXT or mtype in BINARY_TYPES or is_script_text
    if _MACRO_RE.search(name):
        f('ART08', 'high', 'Office file contains macros or embedded OLE/ActiveX objects', name, 0.9)
    if mtype == 'zip' or mext in ZIP_EXT:
        _merge_inner(res, inspect(data, vpath, budget, depth + 1))
    elif mtype in BINARY_TYPES:
        f('ART11', 'high', 'Compiled binary inside an archive', name, 0.9)
        res['partial'] = True
    elif mtype in ('png', 'jpeg', 'gif', 'webp', 'pdf'):
        _merge_inner(res, inspect(data, vpath, budget, depth + 1))
    else:
        if _RELS_RE.search(name):
            _check_rels(data, f)
        if readable(data):
            res['members'].append({
                'path': vpath, 'text': data.decode('utf-8', errors='replace'),
                'kind': 'code' if (mext in EXEC_EXT or is_script_text) else 'md',
            })
        else:
            res['partial'] = True
    return is_exec


def _inspect_zip(
    buf: bytes, rel: str, res: Result, f: Finder, budget: dict[str, Any], depth: int,
) -> None:
    """Inspect a ZIP-compatible archive in memory under the bomb limits."""
    is_office = _extname(rel).lower() in OFFICE_EXT
    if depth >= LIMITS['depth']:
        res['partial'] = True
        f('ART06', 'high', 'Archive nested deeper than the inspection limit', f'depth {depth}', 0.8)
        return
    z = list_zip(buf)
    if z.get('error'):
        res['partial'] = True
        f('ART06', 'medium', 'Archive could not be listed: ' + z['error'], '', 0.7)
        return
    if z['trailing'] > 16:
        _trailing_check(buf, len(buf) - z['trailing'], res, f, 'archive')
    exec_members: list[str] = []
    for e in z['entries']:
        if _member_budget(res, f, budget):
            break
        verdict = _member_precheck(e, res, f, budget)
        if verdict == 'stop':
            break
        if verdict == 'skip':
            continue
        data = read_entry(buf, e, LIMITS['memberBytes'] + 1)
        if data is None:
            res['partial'] = True
            f(
                'ART06', 'low', 'Archive member could not be read (unsupported compression)',
                e['name'], 0.5,
            )
            continue
        budget['bytes'] += len(data)
        if _scan_member(e['name'], data, f"{rel}!/{e['name']}", res, f, budget, depth):
            exec_members.append(e['name'])
    if exec_members:
        f('SUP09', 'high' if is_office else 'medium',
          'Executable content hidden inside an Office document' if is_office
          else 'Archive contains executable or script members',
          ', '.join(exec_members[:6]), 0.9 if is_office else 0.7)
