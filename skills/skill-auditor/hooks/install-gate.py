#!/usr/bin/env python3
"""Optional install gate for skill-auditor. Inert unless SKILL_AUDITOR_GATE is set.

Environment:
    SKILL_AUDITOR_GATE=advise   after a skill file is written or edited, audit that skill and tell
                                the model what it found (never blocks)
    SKILL_AUDITOR_GATE=strict   same, and block the edit's follow-up when the mechanical
                                recommendation is DO_NOT_INSTALL (exit code 2, reason on stderr)

It also reminds the model to audit before enabling a skill when a command installs one (git clone
of a skills repo, a plugin install, copying into a skills folder). It only reads the skill; it
never runs it.
Any failure here lets the work continue (fail open, exit 0).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import os  # noqa: E402

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import json  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from typing import Any  # noqa: E402

DEBOUNCE_SECONDS = 4
MAX_ROOT_LEVELS = 6
BLOCK_EXIT_CODE = 2

# \s here also matches the non-ASCII spaces, and \b stays ASCII-only (hence re.ASCII below).
_WS = "[\\s\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
INSTALL_RE = re.compile(
    r"\bgit" + _WS + r"+clone\b[^\n]*skill"
    r"|\bclaude" + _WS + r"+plugin" + _WS + r"+(install|add)\b"
    r"|\bnpx" + _WS + r"+[^\n]*skills?" + _WS + r"+(add|install)\b"
    r"|\b(cp|copy|xcopy|robocopy|mv|ln)\b[^\n]*[\\/]\.?claude[\\/]skills\b"
    r"|/plugin" + _WS + r"+install\b",
    re.IGNORECASE | re.ASCII,
)
SKILL_PATH_RE = re.compile(r"([\\/]skills[\\/]|SKILL\.md\Z|hooks\.json\Z|plugin\.json\Z)", re.IGNORECASE | re.ASCII)
SHELL_TOOLS_RE = re.compile(r"Bash|PowerShell")
EDIT_TOOLS_RE = re.compile(r"Write|Edit|MultiEdit")

INSTALL_REMINDER = (
    "skill-auditor: this command brings a skill onto the machine. Audit it before enabling it: "
    "run the skill-auditor skill on the downloaded folder (read only; do not run its scripts "
    "first)."
)


def read_input() -> dict[str, Any]:
    """Read the hook JSON from stdin; return {} when it is missing or malformed."""
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def emit(event: str, text: str) -> None:
    """Print the hook response that adds context for the model."""
    payload = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def skill_root_for(file: str) -> str | None:
    """Walk up from a file to the nearest folder holding SKILL.md (at most six levels)."""
    folder = os.path.dirname(os.path.abspath(file))
    for _ in range(MAX_ROOT_LEVELS):
        if os.path.exists(os.path.join(folder, "SKILL.md")):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return None


def debounced(root: str) -> bool:
    """Return True when this skill was audited in the last few seconds; otherwise stamp it."""
    stamp = os.path.join(
        tempfile.gettempdir(), "skill-auditor-gate-" + root.encode("utf-8").hex()[-24:],
    )
    try:
        if time.time() - os.stat(stamp).st_mtime < DEBOUNCE_SECONDS:
            return True
    except OSError:
        pass  # first run
    try:
        with open(stamp, "w", encoding="utf-8") as handle:
            handle.write(str(int(time.time() * 1000)))
    except OSError:
        pass  # a missing stamp only disables debouncing
    return False


def describe(finding: dict[str, Any]) -> str:
    """Format one serious finding as a bullet line."""
    evidence = finding.get("evidence")
    tail = " | " + str(evidence)[:80] if evidence else ""
    return (f'- {finding["severity"]} {finding["id"]} {finding["file"]}:{finding["line"]} '
            f'{finding.get("name")}{tail}')


def handle_shell(data: dict[str, Any]) -> None:
    """PreToolUse on a shell tool: remind the model to audit when the command installs a skill."""
    tool_input = data.get("tool_input")
    command = str(tool_input.get("command") or "") if isinstance(tool_input, dict) else ""
    if INSTALL_RE.search(command):
        emit("PreToolUse", INSTALL_REMINDER)


def handle_edit(mode: str, data: dict[str, Any]) -> int:
    """PostToolUse on a file edit: audit the touched skill; return the exit code."""
    tool_input = data.get("tool_input")
    file = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(file, str) or not file or not SKILL_PATH_RE.search(file):
        return 0
    root = skill_root_for(file)
    if not root or debounced(root):
        return 0

    from lint import audit_path

    skill = audit_path(root, {})["skills"][0]
    serious = [f for f in skill["findings"] if f["severity"] in ("critical", "high")]
    recommendation = skill["risk"]["recommendation"]
    if recommendation == "SAFE" and not serious:
        return 0
    top = "\n".join(describe(f) for f in serious[:5])
    message = (
        f"skill-auditor (mechanical pass) on {skill['name']}: risk {skill['risk']['score']}/100, "
        f"{recommendation}, coverage {skill['coverage']['percent']}%.\n"
        f"{top or '(no high findings)'}\n"
        "Run the skill-auditor skill for a full review before relying on this skill."
    )
    if mode == "strict" and recommendation == "DO_NOT_INSTALL":
        sys.stderr.write(
            message + "\nBlocked by SKILL_AUDITOR_GATE=strict. "
            "Fix the findings or review them with the skill-auditor skill.\n")
        sys.stderr.flush()
        return BLOCK_EXIT_CODE
    emit("PostToolUse", message)
    return 0


def run() -> int:
    """Dispatch on the hook event; return the process exit code."""
    mode = (os.environ.get("SKILL_AUDITOR_GATE") or "").lower()
    if mode not in ("advise", "strict"):
        return 0
    data = read_input()
    event = data.get("hook_event_name")
    tool = data.get("tool_name")
    tool = tool if isinstance(tool, str) else ""
    if event == "PreToolUse" and SHELL_TOOLS_RE.fullmatch(tool):
        handle_shell(data)
        return 0
    if event == "PostToolUse" and EDIT_TOOLS_RE.fullmatch(tool):
        return handle_edit(mode, data)
    return 0


def main() -> int:
    """Run the gate; any unexpected error is reported on stderr and lets the work continue."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        return run()
    except Exception as exc:  # fail open by design: the gate must never break the session
        sys.stderr.write(f"skill-auditor gate: {exc}\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
