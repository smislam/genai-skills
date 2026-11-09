#!/usr/bin/env python3
"""appsec-auditor coverage gate: a Claude Code Stop hook.

While an audit is running, Claude can't finish until scripts/coverage-check.py reports the audit
complete: every checklist item decided, every entry-point file read, report and SARIF written. To
wait for the user mid-audit, the skill sets .appsec-audit/state.json to {"status": "paused"}; the
gate then lets the turn end. Claude Code's own cap on consecutive stop-hook continuations prevents
an endless loop. A bug in the gate itself, or a missing or too old Python, lets the turn end
(fail open, exit 0). Requires Python 3.12+, standard library only.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
if sys.version_info < (3, 12):
    sys.stderr.write("appsec-auditor gate: Python 3.12 or newer is required; hook skipped.\n")
    raise SystemExit(0)

import os  # noqa: E402

HOOK_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HOOK_DIR)

import json  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import common  # noqa: E402

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

__all__ = ["main"]

SCRIPT_NAMES = ("coverage-check.py", "coverage_check.py")
MAX_GAPS_SHOWN = 12
MAX_SAMPLES_SHOWN = 3


def parse_time(value: object) -> float:
    """Seconds since the epoch for an ISO 8601 timestamp; NaN when it is missing or unreadable.

    A date and time without an offset is local time; a bare date is UTC.
    """
    if not isinstance(value, str):
        return float("nan")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return float("nan")
    if stamp.tzinfo is None and len(value) <= 10:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def read_state(audit_dir: str) -> tuple[object, bool]:
    """Return (status, fresh) from state.json; a missing or unreadable file means running."""
    try:
        with open(os.path.join(audit_dir, "state.json"), encoding="utf-8", errors="replace") as handle:
            state = json.load(handle)
    except (OSError, ValueError, RecursionError):
        return "running", True
    if not isinstance(state, dict):
        return "running", True
    age = time.time() - parse_time(state.get("updatedAt"))
    return state.get("status"), 0 <= age <= common.MARKER_MAX_AGE_SECONDS


def load_check() -> Any:
    """Import check() from the sibling scripts folder by path, without touching sys.path."""
    import importlib.util

    scripts = os.path.join(os.path.dirname(HOOK_DIR), "scripts")
    for name in SCRIPT_NAMES:
        path = os.path.join(scripts, name)
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("appsec_coverage_check", path)
            if spec is None or spec.loader is None:
                break
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.check
    raise FileNotFoundError(f"coverage check script not found in {scripts}")


def describe_gap(gap: dict[str, Any]) -> str:
    """Format one gap as a bullet line, with up to three samples."""
    sample = gap.get("sample") or []
    tail = f" e.g. {'; '.join(str(s) for s in sample[:MAX_SAMPLES_SHOWN])}" if sample else ""
    return f"- [{gap['type']}] {gap['message']}{tail}"


def run() -> None:
    """Block the stop with a list of gaps when an active audit is not complete."""
    data = common.read_input()
    if data is None:
        return
    # Work still running in the background (for example, the audit itself in a subagent) will
    # wake the session when it finishes, so ending this turn isn't finishing the audit.
    if data.get("background_tasks"):
        return
    check = load_check()
    blocking: list[str] = []
    for audit_dir in common.active_audit_dirs(data):
        status, fresh = read_state(audit_dir)
        if status == "paused" and fresh:
            continue
        root = os.path.dirname(audit_dir)
        result = check(root)
        if result["complete"]:
            continue
        lines = "\n".join(describe_gap(g) for g in result["gaps"][:MAX_GAPS_SHOWN])
        blocking.append(f"Audit of {root} is not complete:\n{lines}")
    if not blocking:
        return
    reason = "[appsec-auditor coverage gate] " + "\n\n".join(blocking) + (
        "\n\nContinue the audit until `python3 scripts/coverage-check.py` reports complete. If you must stop "
        "to wait for the user, write .appsec-audit/state.json as "
        '{"status": "paused", "reason": "...", "updatedAt": "<ISO time>"} first, and set it back to '
        '"running" when you resume.'
    )
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()


def main() -> int:
    """Run the gate; always exits 0, because a failing gate must not trap the session."""
    common.configure_streams()
    try:
        run()
    except Exception as exc:  # fail open on a bug in the gate itself, but say so
        sys.stderr.write(f"appsec-auditor gate error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
