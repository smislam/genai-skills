"""Shared helpers: JSON access, hashing, paths, audited-file access, deterministic ordering."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

__all__ = [
    'RE_LINE_SPLIT',
    'as_list',
    'as_text',
    'audited_size',
    'dump_json',
    'error_text',
    'get_key',
    'is_absolute_path',
    'iter_items',
    'name_sort_key',
    'now_iso',
    'parse_json',
    'read_audited_bytes',
    'read_json_file',
    'relative_to',
    'round_half_up',
    'sha256_hex',
]

RE_LINE_SPLIT: re.Pattern[str] = re.compile(r'\r?\n')


def error_text(exc: BaseException) -> str:
    """One-line description of an exception: its type name and message."""
    return f'{type(exc).__name__}: {exc}'


def round_half_up(x: float) -> int:
    """Round halves up. Python's round() rounds halves to even, which would shift scores at ties."""
    return math.floor(x + 0.5)


def sha256_hex(buf: bytes) -> str:
    """Hex SHA-256 of a byte string."""
    return hashlib.sha256(buf).hexdigest()


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def name_sort_key(name: str) -> tuple[str, str]:
    """Deterministic, case-insensitive order for file and directory names (casefold, then exact)."""
    return name.casefold(), name


# --------------------------------------------------------------------------------------------------
# Parsed-JSON access. Audited files can hold JSON of any shape; these never raise on a wrong shape.
# --------------------------------------------------------------------------------------------------


def get_key(obj: Any, key: str) -> Any:
    """obj[key] when obj is a JSON object, otherwise None."""
    return obj.get(key) if isinstance(obj, dict) else None


def iter_items(obj: Any) -> list[tuple[str, Any]]:
    """(key, value) pairs of an object; an array yields (index, element); else nothing."""
    if isinstance(obj, dict):
        return list(obj.items())
    if isinstance(obj, list):
        return [(str(i), v) for i, v in enumerate(obj)]
    return []


def as_list(obj: Any) -> list[Any]:
    """The list itself, or an empty list when the value is not an array."""
    return obj if isinstance(obj, list) else []


def as_text(value: Any) -> str:
    """Display text for a JSON value: strings as they are, everything else as compact JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _reject_json_constant(name: str) -> NoReturn:
    """Refuse NaN and Infinity, which are not valid JSON and which real JSON consumers reject."""
    raise ValueError(f'invalid JSON constant {name}')


def parse_json(text: str) -> Any:
    """Parse strict JSON text; raises ValueError (with the parser's message) when it is invalid."""
    try:
        return json.loads(text, parse_constant=_reject_json_constant)
    except RecursionError as exc:
        raise ValueError('JSON nested too deeply') from exc


def read_json_file(path: str | Path) -> Any:
    """Read and parse a UTF-8 JSON file given by the caller; raises ValueError when it cannot."""
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        raise ValueError(f'cannot read {path}: {error_text(exc)}') from exc
    try:
        return parse_json(text)
    except ValueError as exc:
        raise ValueError(f'{path} is not valid JSON: {exc}') from exc


def dump_json(obj: Any, pretty: bool) -> str:
    """Serialize to JSON text, indented when pretty is set."""
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


# --------------------------------------------------------------------------------------------------
# Paths and audited files
# --------------------------------------------------------------------------------------------------


def is_absolute_path(path: str) -> bool:
    """True for an absolute path in the style of the platform the audit runs on."""
    if os.name == 'nt':
        return bool(re.match(r'^([\\/]|[A-Za-z]:[\\/])', path))
    return path.startswith('/')


def relative_to(root: str, target: str) -> str:
    """target relative to root; across Windows drives the absolute target is returned unchanged."""
    try:
        return os.path.relpath(target, root)
    except ValueError:
        return target


def _extended_path(path: str | Path) -> str:
    """The path to hand to the OS for an audited file.

    A hostile skill can ship a file named like a Windows device (nul, con, aux, com1, ...). Opened
    by its plain path, Windows treats it as the device and the read returns nothing, so the file's
    content would silently escape review. The extended-length prefix makes Windows treat the name
    as an ordinary file. Other platforms need no change.
    """
    text = str(path)
    if os.name == 'nt' and re.match(r'^[A-Za-z]:[\\/]', text):
        return '\\\\?\\' + os.path.normpath(text)
    return text


def read_audited_bytes(path: str | Path) -> bytes:
    """Read an audited file completely (the one way the auditor reads files of the audited tree)."""
    with open(_extended_path(path), 'rb') as handle:
        return handle.read()


def audited_size(path: str | Path) -> int:
    """Size in bytes of an audited file (same device-name-safe path as read_audited_bytes)."""
    return os.stat(_extended_path(path)).st_size
