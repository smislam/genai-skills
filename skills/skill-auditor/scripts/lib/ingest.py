"""Reading a skill: directory walk, size limits, coverage ledger, and routing of each file."""

from __future__ import annotations

import os
import re
from typing import Any

from . import archive, report
from .model import CODE_EXT, Ctx, FileItem, LIM, MD_EXT, base_of, ext_of, kind_of, surface_of
from .text import scan_re
from .textscan import analyze_text
from .util import (
    audited_size,
    error_text,
    is_absolute_path,
    name_sort_key,
    read_audited_bytes,
    relative_to,
    sha256_hex,
)

__all__ = [
    'SKIP_DIRS',
    'decode_text',
    'ingest_dir',
    'process_file',
    'sorted_entries',
]


SKIP_DIRS: frozenset[str] = frozenset(
    {'node_modules', '.git', '__pycache__', '.venv', 'venv', '.tox', '.mypy_cache'}
)

CFG_EXT: frozenset[str] = frozenset({
    '.json', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf', '.xml', '.csv', '.env',
    '.properties', '.gradle',
    '.lock', '.rels',
})

IMAGE_TYPES: tuple[str, ...] = ('png', 'jpeg', 'gif', 'webp')

NATIVE_BINARY_TYPES: tuple[str, ...] = ('elf', 'pe', 'macho', 'class-or-macho', 'wasm')

COMPILED_EXT: tuple[str, ...] = (
    '.pyc', '.pyo', '.class', '.exe', '.dll', '.so', '.dylib', '.node', '.jar', '.wasm',
)

# Files and kinds.
RE_DOT_FILE_OK: re.Pattern[str] = scan_re(
    r'^\.(claude-plugin|gitignore|gitattributes|editorconfig|npmrc|nvmrc|prettierrc.*|eslintrc.*|env\.example'
    r'|dockerignore|mcp\.json)$', 'i')

RE_CLAUDE_PLUGIN_DIR: re.Pattern[str] = scan_re(r'(^|\/)\.claude-plugin\/')

RE_CLAUDE_DIR: re.Pattern[str] = scan_re(r'(^|\/)\.claude\/')

RE_META_INSTRUCTION: re.Pattern[str] = scan_re(r'(^|[^a-z])(ignore|disregard|system prompt|instructions?)', 'i')

RE_FILE_START_OK: re.Pattern[str] = scan_re(r'^\s*(#!|<|\{|\[|---)')

RE_READABLE_CHAR: re.Pattern[str] = scan_re(r'[\x20-\x7E\s]')


def sorted_entries(directory: str) -> list[os.DirEntry[str]]:
    """Directory entries in a deterministic order (case-insensitive, then exact name)."""
    with os.scandir(directory) as it:
        return sorted(it, key=lambda e: name_sort_key(e.name))


def ingest_dir(ctx: Ctx, root: str) -> list[FileItem]:
    """Walk a skill folder and return the files to inspect, applying exclusions and limits."""
    items: list[FileItem] = []
    excl = [report.glob_to_re(g) for g in ctx.opts.get('exclude') or []]
    baseline = ctx.opts.get('baseline')
    baseline_abs = os.path.abspath(baseline) if baseline else None
    state = {'bytes': 0}

    def walk(directory: str, prefix: str) -> None:
        """Visit one directory (sorted), recording files and recursing into folders."""
        try:
            ents = sorted_entries(directory)
        except OSError as e:
            ctx.add({'id': 'COV01', 'file': prefix.rstrip('/') or '.', 'evidence': error_text(e)})
            return
        for e in ents:
            full = os.path.join(directory, e.name)
            rel = prefix + e.name
            if baseline_abs and os.path.abspath(full) == baseline_abs:
                continue
            if any(g.search(rel) or g.search(e.name) for g in excl):
                ctx.ledger.append(
                    {'file': rel, 'status': 'excluded', 'reason': 'matched --exclude'}
                )
                continue
            if os.path.islink(full):
                record_symlink(ctx, root, full, rel)
                continue
            if e.is_dir(follow_symlinks=False):
                if e.name not in SKIP_DIRS:
                    walk(full, rel + '/')
                continue
            if not e.is_file(follow_symlinks=False):
                continue
            add_file_item(ctx, items, state, full, rel)

    walk(root, '')
    return items


def record_symlink(ctx: Ctx, root: str, full: str, rel: str) -> None:
    """Symlinks are never followed; they are listed and flagged."""
    try:
        target = os.path.realpath(full, strict=True)
    except OSError:
        target = '(broken)'
    inside = False
    if target != '(broken)':
        r = relative_to(root, target)
        inside = not r.startswith('..') and not is_absolute_path(r)
    ctx.ledger.append({'file': rel, 'status': 'uninspected', 'reason': 'symlink to ' + target})
    ctx.add({'id': 'ART15', 'severity': 'low' if inside else 'high', 'file': rel, 'surface': 'code',
             'confidence': 0.9, 'evidence': target})


def add_file_item(
    ctx: Ctx, items: list[FileItem], state: dict[str, int], full: str, rel: str,
) -> None:
    """Add one file to the work list unless an ingest limit has been reached."""
    if len(items) >= LIM['ingestFiles']:
        if 'files' not in ctx.notes:
            ctx.notes.append('files')
            ctx.add({'id': 'COV02', 'file': '(folder)',
                     'evidence': f"more than {LIM['ingestFiles']} files; the rest were not read"})
        return
    try:
        size = audited_size(full)
    except OSError as exc:  # the file vanished or cannot be examined: record it, keep going
        reason = f'unreadable: {error_text(exc)}'
        ctx.ledger.append({'file': rel, 'status': 'uninspected', 'reason': reason})
        ctx.add({'id': 'COV01', 'file': rel, 'evidence': error_text(exc)})
        return
    state['bytes'] += size
    if state['bytes'] > LIM['ingestBytes']:
        if 'bytes' not in ctx.notes:
            ctx.notes.append('bytes')
            ctx.add(
                {
                    'id': 'COV02', 'file': '(folder)',
                    'evidence': 'more than 100 MiB; the rest were not read',
                }
            )
        ctx.ledger.append({'file': rel, 'status': 'uninspected', 'reason': 'ingest size limit'})
        return
    items.append(FileItem(rel=rel, size=size, read=lambda p=full: read_audited_bytes(p)))


def text_ok(rel: str) -> bool:
    """True for extensions whose content is expected to be text."""
    e = ext_of(rel)
    return e in MD_EXT or e in CODE_EXT or e in CFG_EXT or e == ''


def readable_text(t: str) -> bool:
    """True when at least 90 percent of the first 2000 characters are printable."""
    s = t[:2000]
    return not s or len(RE_READABLE_CHAR.findall(s)) / len(s) > 0.9


def process_file(ctx: Ctx, item: FileItem) -> None:
    """Read one file, record coverage, and route it; one failing file never aborts the audit."""
    st: dict[str, Any] = {'file': item.rel, 'status': 'inspected', 'reason': ''}
    ctx.ledger.append(st)
    try:
        inspect_file(ctx, item, st)
    except Exception as exc:  # noqa: BLE001 - a hostile or malformed file must not abort the audit
        reason = f'inspection failed: {type(exc).__name__}'
        st['status'] = 'uninspected'
        st['reason'] = reason
        ctx.add({'id': 'COV01', 'file': item.rel, 'evidence': reason})


def inspect_file(ctx: Ctx, item: FileItem, st: dict[str, Any]) -> None:
    """Read the file and send it to container inspection, the binary checks, or text analysis."""
    rel = item.rel
    if item.size > LIM['binaryRead']:
        st['status'] = 'uninspected'
        st['reason'] = 'over 16 MiB'
        ctx.add({'id': 'COV01', 'file': rel, 'evidence': 'over 16 MiB'})
        return
    try:
        buf = item.read()
    except OSError as exc:
        st['status'] = 'uninspected'
        st['reason'] = f'unreadable: {error_text(exc)}'
        ctx.add({'id': 'COV01', 'file': rel, 'evidence': error_text(exc)})
        return
    ctx.hashes[rel] = sha256_hex(buf)
    ftype = archive.detect(buf)
    base = base_of(rel)
    expected_dot_file = (RE_DOT_FILE_OK.search(base) or RE_CLAUDE_PLUGIN_DIR.search(rel)
                         or RE_CLAUDE_DIR.search(rel))
    if base.startswith('.') and not expected_dot_file:
        ctx.add({'id': 'ART14', 'file': rel, 'surface': 'code', 'evidence': base})
    if ftype:
        process_container(ctx, rel, buf, ftype, st)
    elif b'\x00' in buf:
        st['status'] = 'uninspected'
        st['reason'] = 'NUL bytes (binary content)'
        ctx.add({'id': 'ART02', 'file': rel, 'surface': 'code', 'confidence': 0.9,
                 'evidence': f'NUL byte at offset {buf.index(0)}'})
    elif ext_of(rel) in COMPILED_EXT:
        st['status'] = 'uninspected'
        st['reason'] = 'compiled artifact'
        ctx.add(
            {
                'id': 'SUP08', 'file': rel, 'surface': 'code', 'confidence': 0.95,
                'evidence': ext_of(rel),
            }
        )
    else:
        process_text_file(ctx, rel, kind_of(rel), buf, st)


def decode_text(buf: bytes) -> str | None:
    """Strict UTF-8 decode that drops a leading BOM; None when the bytes are not valid UTF-8."""
    try:
        return buf.decode('utf-8-sig')
    except UnicodeDecodeError:
        return None


def process_text_file(ctx: Ctx, rel: str, kind: str, buf: bytes, st: dict[str, Any]) -> None:
    """Decode a text file (Latin-1 fallback), apply the size cap, and analyze it."""
    text = decode_text(buf)
    if text is None:
        text = buf.decode('latin-1')
        st['status'] = 'partial'
        st['reason'] = 'not valid UTF-8'
        if kind == 'skillmd':
            ctx.add({'id': 'COV03', 'file': rel, 'evidence': 'SKILL.md is not valid UTF-8'})
        else:
            ctx.add(
                {
                    'id': 'COV01', 'severity': 'low', 'file': rel,
                    'evidence': 'not valid UTF-8; read as Latin-1',
                }
            )
    ctx.texts[rel] = text
    if len(buf) > LIM['fileBytes']:
        st['status'] = 'partial'
        st['reason'] = 'over 1 MiB; only the first 1 MiB was analyzed'
        ctx.add({'id': 'ART04' if (ext_of(rel) in MD_EXT or kind == 'skillmd') else 'COV01',
                 'severity': 'high' if ext_of(rel) in MD_EXT else 'medium', 'file': rel,
                 'surface': 'instructions', 'evidence': f'{len(buf)} bytes'})
        text = text[:LIM['fileBytes']]
    if not text_ok(rel) and not RE_FILE_START_OK.search(text[:200]) and not readable_text(text):
        st['status'] = 'partial'
        st['reason'] = 'unrecognized content'
    analyze_text(ctx, rel, text, {'kind': kind, 'surface': surface_of(kind)})


def process_container(ctx: Ctx, rel: str, buf: bytes, ftype: str, st: dict[str, Any]) -> None:
    """Inspect an archive, image, PDF, or binary and analyze any text it exposes."""
    res = archive.inspect(buf, rel, ctx.zip_budget, 0)
    for f in res['findings']:
        ctx.add({'file': rel, 'surface': 'code', **f})
    if res['partial']:
        st['status'] = 'partial'
        st['reason'] = '; '.join(res['notes']) or 'contents only partly inspected'
    if not res['findings'] and ftype in IMAGE_TYPES:
        st['reason'] = 'structure and metadata checked; pixels need a visual check'
    for m in res['members']:
        member_kind = 'script' if m['kind'] == 'code' else kind_of(
            m['path'].split('!/')[-1].split('#')[0]
        )
        mk = 'md' if member_kind == 'skillmd' else member_kind
        mi = {'kind': mk, 'surface': 'md' if m['kind'] == 'meta' else surface_of(mk)}
        ctx.texts[m['path']] = m['text']
        analyze_text(ctx, m['path'], m['text'][:LIM['fileBytes']], mi)
        if m['kind'] == 'meta' and RE_META_INSTRUCTION.search(m['text']):
            ctx.add({'id': 'SEM11', 'severity': 'medium', 'file': m['path'], 'confidence': 0.5,
                     'surface': 'instructions', 'evidence': m['text'][:100],
                     'message': 'Image metadata contains instruction-like text'})
    if ftype in IMAGE_TYPES or (ftype in ('zip', 'pdf') and ext_of(rel) == '.svg'):
        ctx.images.append(rel)
    if ftype in NATIVE_BINARY_TYPES or ftype in archive.BINARY_TYPES:
        st['status'] = 'uninspected'
        st['reason'] = 'compiled binary'
