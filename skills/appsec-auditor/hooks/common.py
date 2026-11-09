"""Shared by the appsec-auditor hooks: finding the active audit, comparing paths, reading hook input.

Python 3.12+, standard library only. Nothing runs at import time except constants.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

__all__ = [
    "AUDIT_DIR",
    "MARKER_MAX_AGE_SECONDS",
    "active_audit_dirs",
    "configure_streams",
    "is_under",
    "normalize_path",
    "read_input",
]

AUDIT_DIR = ".appsec-audit"

# A marker older than this is treated as left over from an interrupted audit.
MARKER_MAX_AGE_SECONDS = 24 * 60 * 60

_TRAILING_SLASHES_RE = re.compile(r"/+\Z")
_LINE_SPLIT_RE = re.compile(r"\r?\n")


def configure_streams() -> None:
    """Make stdout and stderr UTF-8 with plain newlines (no CRLF translation on Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
        except (AttributeError, ValueError):
            pass  # a stream without reconfigure keeps its defaults


def read_input() -> dict[str, Any] | None:
    """Read the hook JSON object from stdin; None when it is missing, malformed, or not an object."""
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def normalize_path(path: str) -> str:
    """Forward slashes everywhere; lowercase on Windows, where paths are case-insensitive."""
    forward = path.replace("\\", "/")
    return forward.lower() if sys.platform == "win32" else forward


def is_under(file_path: str, directory: str) -> bool:
    """True when file_path is the directory or inside it (a textual comparison, no file access)."""
    f = normalize_path(file_path)
    d = _TRAILING_SLASHES_RE.sub("", normalize_path(directory))
    return f == d or f.startswith(d + "/")


def active_audit_dirs(data: dict[str, Any]) -> list[str]:
    """Every audit directory with a fresh marker, searching upward from the project dir and cwd.

    The audit directory sits at the repository root, which may be above the session's project
    directory or cwd (for example, a session started in a subfolder). An empty marker means "this
    repository is being audited"; a marker that lists absolute paths points to audits elsewhere.
    """
    found: dict[str, None] = {}
    cwd = data.get("cwd")
    for start in (os.environ.get("CLAUDE_PROJECT_DIR"), cwd if isinstance(cwd, str) else None):
        if not start:
            continue
        directory = os.path.abspath(start)
        while True:
            marker = os.path.join(directory, AUDIT_DIR, ".active")
            try:
                if time.time() - os.stat(marker).st_mtime <= MARKER_MAX_AGE_SECONDS:
                    with open(marker, encoding="utf-8", errors="replace", newline="") as handle:
                        lines = [line.strip() for line in _LINE_SPLIT_RE.split(handle.read())]
                    targets = [line for line in lines if line and os.path.isabs(line)]
                    for root in targets or [directory]:
                        found[os.path.normpath(os.path.join(root, AUDIT_DIR))] = None
            except (OSError, ValueError):
                pass  # no marker here (missing, unreadable, or a directory)
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
    return list(found)
