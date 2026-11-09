#!/usr/bin/env python3
"""appsec-auditor read tracker: a Claude Code PostToolUse hook for the Read tool.

During an audit, records each file the AI reads in <audit dir>/reads.jsonl, so the coverage gate
can check that every entry-point file was actually reviewed. Inert unless an audit is running.
Always exits 0; a missing or too old Python lets the work continue.
Requires Python 3.12+, standard library only.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
if sys.version_info < (3, 12):
    sys.stderr.write("appsec-auditor track: Python 3.12 or newer is required; hook skipped.\n")
    raise SystemExit(0)

import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import json  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import common  # noqa: E402
from common import is_under  # noqa: E402

__all__ = ["main"]


def main() -> int:
    """Log the Read call against the audit whose repository contains the file."""
    common.configure_streams()
    data = common.read_input()
    if data is None or data.get("tool_name") != "Read":
        return 0
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return 0
    # Log against the audit whose repository contains the file.
    owners = [d for d in common.active_audit_dirs(data) if is_under(file_path, os.path.dirname(d))]
    entry = json.dumps({
        "path": os.path.abspath(file_path),
        "offset": tool_input.get("offset") or None,
        "limit": tool_input.get("limit") or None,
        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }, ensure_ascii=False, separators=(",", ":")) + "\n"
    for directory in owners:
        try:
            with open(os.path.join(directory, "reads.jsonl"), "a", encoding="utf-8", errors="replace", newline="") as handle:
                handle.write(entry)
        except OSError:
            pass  # audit directory not created yet
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
