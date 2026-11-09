"""Small helpers shared by the command-line scripts.

API:
    configure_streams()              UTF-8 stdout/stderr with plain "\\n" line ends
    arg_value(argv, name, default)   value after the first ``name`` in argv; None when none follows
    read_json(path)                  parsed JSON file, or None when it is missing or invalid
    utc_now_iso()                    current UTC time as ``YYYY-MM-DDTHH:MM:SS.mmmZ``
    sha1_hex(text), sha256_hex(text) hex digests of the UTF-8 text
    natural_key(text)                sort key that orders ``F-2`` before ``F-10``
    run_git(root, args, timeout)     (exit code or None, stdout text); never raises
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    'arg_value', 'configure_streams', 'natural_key', 'read_json', 'run_git', 'sha1_hex', 'sha256_hex',
    'utc_now_iso',
]

DIGITS = re.compile(r'(\d+)', re.ASCII)
# Options that stop a hostile repository's own configuration from running programs.
GIT_SAFE_OPTIONS = ['-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=']


def configure_streams() -> None:
    """Write UTF-8 with "\\n" line ends on stdout and stderr, on every platform."""
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='\n')  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace', newline='\n')  # type: ignore[union-attr]


def arg_value(argv: list[str], name: str, default: str | None = None) -> str | None:
    """Return the argument after the first ``name``: ``default`` if absent, None if nothing follows."""
    if name not in argv:
        return default
    i = argv.index(name)
    return argv[i + 1] if i + 1 < len(argv) else None


def read_json(path: str | Path) -> Any:
    """Parse a UTF-8 JSON file; None when it is missing or invalid."""
    try:
        with open(path, encoding='utf-8', errors='replace', newline='') as handle:
            return json.loads(handle.read())
    except (OSError, ValueError, RecursionError):
        return None


def utc_now_iso() -> str:
    """The current UTC time with millisecond precision, e.g. 2026-01-02T03:04:05.678Z."""
    now = datetime.now(timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}Z'


def sha1_hex(text: str) -> str:
    """Hex SHA-1 of the UTF-8 text."""
    return hashlib.sha1(text.encode('utf-8', 'replace')).hexdigest()


def sha256_hex(text: str) -> str:
    """Hex SHA-256 of the UTF-8 text."""
    return hashlib.sha256(text.encode('utf-8', 'replace')).hexdigest()


def natural_key(text: str) -> list[tuple[int, int, str]]:
    """Sort key for IDs such as ``F-2`` and ``F-10``: digit runs compare as numbers, text ignores case."""
    key = []
    for part in DIGITS.split(text):
        key.append((0, int(part), '') if part.isdigit() else (1, 0, part.casefold()))
    return key


def run_git(root: str, args: list[str], timeout: int = 900) -> tuple[int | None, str]:
    """Run ``git -C root ...``; return (exit code or None if git cannot run, decoded stdout)."""
    try:
        proc = subprocess.run(
            ['git', *GIT_SAFE_OPTIONS, '-C', root, *args],
            capture_output=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None, ''
    return proc.returncode, proc.stdout.decode('utf-8', 'replace')
