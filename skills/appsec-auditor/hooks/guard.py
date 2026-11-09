#!/usr/bin/env python3
"""appsec-auditor guardrails: a Claude Code PreToolUse hook.

Inert unless an audit is running, marked by .appsec-audit/.active at the repository root (created
and removed by the skill; ignored after 24 hours). While active it enforces the SKILL.md rules
mechanically:
  - rule 3: commands and scripts that execute project code need the user's approval ("ask")
  - rule 6: piping a remote script into a shell is blocked ("deny")
  - rule 4: secret verification or code-upload scanners need approval ("ask")
  - rule 8: edits outside .appsec-audit/ need approval ("ask")
  - rule 7: writing an unredacted secret into .appsec-audit/ is blocked ("deny")
Every decision is printed as JSON and the exit code is 0; a missing or too old Python lets the work
continue. Requires Python 3.12+, standard library only.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
if sys.version_info < (3, 12):
    sys.stderr.write("appsec-auditor guard: Python 3.12 or newer is required; hook skipped.\n")
    raise SystemExit(0)

import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import json  # noqa: E402
import re  # noqa: E402

import common  # noqa: E402
from common import is_under  # noqa: E402

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

__all__ = ["main"]


def _rx(pattern: str, flags: int = 0) -> re.Pattern[str]:
    """Compile with ASCII \\w, \\d, \\s and \\b, as the JavaScript original treated them."""
    return re.compile(pattern, flags | re.ASCII)


# A permission decision for the tool call: ("ask" | "deny", reason shown to the user).
Decision = tuple[str, str]


def decide(kind: str, reason: str) -> Decision:
    """Build a permission decision."""
    return (kind, reason)


# Commands that run code from the repository or its dependencies.
EXECUTES_PROJECT_CODE: list[tuple[re.Pattern[str], str]] = [
    (_rx(r"\b(npm|pnpm|yarn|bun)\s+(install|i|ci|add|run|run-script|test|exec|rebuild|start|build)\b"), "installs packages or runs package scripts (lifecycle scripts execute dependency code)"),
    (_rx(r"\bnpx\s+(?!--no-install\b)"), "npx can download and run packages"),
    (_rx(r"\b(mvn|mvnw|gradle|gradlew)(\.cmd|\.bat)?\b"), "Maven and Gradle builds run project build logic and plugins"),
    (_rx(r"\bdotnet\s+(build|restore|test|run|publish|pack|msbuild)\b"), ".NET restore and build run MSBuild logic from packages"),
    (_rx(r"\bdotnet\s+(list\s+package|package\s+list)\b(?![^\n]*--no-restore)"), "on .NET 10 this restores automatically, which runs MSBuild logic"),
    (_rx(r"\bcargo\s+(build|test|run|check|clippy|bench|install|doc|update|fetch)\b"), "cargo runs build.rs scripts and proc macros"),
    (_rx(r"\bcargo\s+geiger\b(?![^\n]*--forbid-only)"), "cargo-geiger builds the crate unless --forbid-only is set"),
    (_rx(r"\b(cdk|npx\s+cdk)\s+(synth|deploy|diff|bootstrap|watch)\b"), "cdk synth executes the CDK app"),
    (_rx(r"\bterraform\s+(init|plan|apply|destroy|refresh|import|console)\b"), "terraform downloads and runs provider binaries and may use cloud credentials"),
    (_rx(r"\btofu\s+(init|plan|apply)\b"), "OpenTofu downloads and runs provider binaries"),
    (_rx(r"\btflint\s+--init\b"), "tflint --init downloads plugin binaries"),
    (_rx(r"\bpip3?\s+install\b|\bpython3?\s+-m\s+pip\s+install\b|\buv\s+(pip\s+install|sync|run)\b|\bpoetry\s+(install|run)\b|\bpipenv\s+(install|run)\b"), "installing Python packages can run setup code"),
    (_rx(r"\bpython3?\s+(setup\.py|manage\.py)\b"), "runs project Python code"),
    (_rx(r"\b(pytest|tox|nox)\b"), "runs the project test suite"),
    (_rx(r"\bgo\s+(build|test|run|generate|install)\b"), "go generate and go test run project code"),
    (_rx(r"\bmake\b|\bcmake\s+--build\b|\bninja\b"), "build tools run project build logic"),
    (_rx(r"\bdocker\s+(build|run|compose)\b|\bdocker-compose\b|\bpodman\s+(build|run)\b"), "container builds run Dockerfile RUN steps"),
    (_rx(r"\bpip-audit\s+(\.|--path)\b"), "auditing a project directory can build packages"),
    (_rx(r"\bosv-scanner\b[^\n]*--call-analysis=rust\b"), "Rust call analysis runs build.rs"),
]

# Off-machine data flows that need explicit opt-in (rule 4).
SENDS_DATA: list[tuple[re.Pattern[str], str]] = [
    (_rx(r"\btrufflehog\b(?![^\n]*--no-verification)"), "TruffleHog verification sends secrets to their providers; add --no-verification unless the user opted in"),
    (_rx(r"\bsemgrep\b[^\n]*--config(=|\s+)auto\b"), "semgrep --config auto sends the project URL to the Semgrep Registry"),
    (_rx(r"\bopengrep\s+scan\b(?![^\n]*\s(-f|--config)[=\s])"), "opengrep without -f falls back to auto config and sends the project URL"),
    (_rx(r"\bsemgrep\s+(login|ci)\b|\bsnyk\s+(code|auth|monitor)\b"), "uploads code or authenticates to a cloud scanner"),
    (_rx(r"\bbetterleaks\b[^\n]*--validation\b"), "secret validation sends secrets to their providers"),
]

# Reporting findings to anyone outside the machine (rule 10).
EXTERNAL_REPORTING: list[re.Pattern[str]] = [
    _rx(r"\bgh\s+(issue|pr)\s+(create|comment)\b"),
    _rx(r"\bgh\s+api\b[^\n]*\b(issues|pulls|security-advisories|comments)\b"),
    _rx(r"\bglab\s+(issue|mr)\s+(create|note)\b|\bglab\s+api\b[^\n]*\b(issues|merge_requests|notes)\b"),
    _rx(r"(?:^|[;&|(]\s*)(?:mail|mailx|sendmail|msmtp)\s|\bSend-MailMessage\b"),
    _rx(r"\bcurl\b[^\n]*\b(api\.github\.com|gitlab\.com\/api)\b[^\n]*\b(issues|pulls|merge_requests|security-advisories|notes|comments)\b"),
]
GIT_PUSH = _rx(r"\bgit\s+push\b")

# Remote script piped into a shell (rule 6).
PIPE_TO_SHELL = _rx(
    r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b"
    r"|\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^\n|]*\|\s*(iex|Invoke-Expression)\b",
    re.IGNORECASE,
)

# Secret shapes that must never appear unredacted in audit output (rule 7).
SECRET_SHAPES: list[re.Pattern[str]] = [
    _rx(r"\bAKIA[0-9A-Z]{16}\b"),
    _rx(r"\bASIA[0-9A-Z]{16}\b"),
    _rx(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    _rx(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    _rx(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    _rx(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    _rx(r"\bsk_live_[A-Za-z0-9]{20,}\b"),
    _rx(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    _rx(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
]
KNOWN_EXAMPLES = _rx(r"AKIAIOSFODNN7EXAMPLE|wJalrXUtnFEMI\/K7MDENG")

# Scripts run by path: `bash x.sh`, `node x.js`, `python x.py`, `python3.12 x.py`, `py -3 x.py`,
# `./run`, `& .\build.ps1`, `powershell -File x.ps1`. The skill's own scripts and files in the audit
# directory are fine. Flags may start with a digit (`py -3`), and a version suffix is part of the name.
INTERPRETER = _rx(
    r"""(?:^|[;&|(]\s*|\s)(bash|sh|zsh|dash|node|deno\s+run|bun\s+run|ts-node|tsx|python[\d.]*|py[\d.]*|ruby|perl|php)"""
    r"""((?:\s+-{1,2}[A-Za-z0-9][\w.-]*(?:=\S+)?)*)\s+("[^"]+"|'[^']+'|[^\s;&|<>]+)"""
)
POWERSHELL_FILE = _rx(
    r"""\b(?:pwsh|powershell)(?:\.exe)?\b[^\n;|]*?\s-File\s+("[^"]+"|'[^']+'|[^\s;&|]+)""",
    re.IGNORECASE,
)
DIRECT_EXEC = _rx(r"""(?:^|[;&|(]\s*)(?:&\s*)?("?\.{1,2}[\\/][^\s;&|"]+"?)""")
INLINE_CODE_FLAGS = _rx(r"(^|\s)-(c|e|m|-eval|-print|Command)\b")
PROTECTED_WORDS = _rx(r"\b(coverage\.json|deps\.json|reads\.jsonl)\b")
MODIFIES_FILES = _rx(
    r"(>|\bmv\b|\bcp\b|\brm\b|\bsed\b|Set-Content|Out-File|Remove-Item|Move-Item|Copy-Item|\btee\b|\btruncate\b)",
    re.IGNORECASE,
)
QUOTE_ENDS = re.compile(r"""^["']|["']\Z""")

# Written only by the skill's scripts and hooks; the coverage gate depends on them.

PROTECTED_FILES = ("coverage.json", "deps.json", "reads.jsonl")


def script_targets(command: str) -> list[str]:
    """Paths of the scripts a command runs by path (inline code and modules are handled elsewhere)."""
    targets: list[str] = []
    for m in INTERPRETER.finditer(command):
        # `python -c "..."`, `node -e "..."`, `python -m module`: inline or module code.
        if not INLINE_CODE_FLAGS.search(m.group(2)):
            targets.append(m.group(3))
    for pattern in (POWERSHELL_FILE, DIRECT_EXEC):
        targets.extend(m.group(1) for m in pattern.finditer(command))
    stripped = (QUOTE_ENDS.sub("", t) for t in targets)
    return [t for t in stripped if t and not t.startswith("-")]


def check_scripts(command: str, data: dict[str, Any], audit_dirs: list[str]) -> Decision | None:
    """Ask before running a script by path that is neither the skill's own nor in the audit dir."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    allowed_roots = ([plugin_root] if plugin_root else []) + audit_dirs
    cwd = data.get("cwd")
    base = cwd if isinstance(cwd, str) and cwd else (os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    for target in script_targets(command):
        resolved = os.path.abspath(os.path.join(base, target))
        if any(is_under(resolved, root) for root in allowed_roots):
            continue
        return decide("ask", f"This runs a script by path ({target}), which may be code from the repository under audit. Approve only if you trust it to run here.")
    return None


def check_command(command: str, data: dict[str, Any], audit_dirs: list[str]) -> Decision | None:
    """Apply the shell-command rules; the first rule that matches decides."""
    # Shell commands may not touch the gate's inputs, except the skill's own scripts.
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    skill_script = bool(plugin_root) and (
        plugin_root.replace("\\", "/").lower() + "/scripts/"
    ) in command.replace("\\", "/").lower()
    if PROTECTED_WORDS.search(command) and not skill_script and MODIFIES_FILES.search(command):
        return decide("deny", "The coverage files (coverage.json, deps.json, reads.jsonl) are written only by the skill's scripts and hooks. Re-run inventory.py or deps.py instead.")
    if PIPE_TO_SHELL.search(command):
        return decide("deny", "Piping a downloaded script into a shell is not allowed during an audit. Download, verify the checksum or signature, then run (see README.md).")
    if any(pattern.search(command) for pattern in EXTERNAL_REPORTING):
        return decide("deny", "Findings are never reported outside the machine during an audit: no issues, pull requests, advisories, comments, or email (SKILL.md rule 10). The report goes to the user only.")
    if GIT_PUSH.search(command):
        return decide("ask", "Pushing during an audit sends commits to a remote. Approve only if the user asked for it (SKILL.md rule 10).")
    for pattern, why in SENDS_DATA:
        if pattern.search(command):
            return decide("ask", f"This sends data off the machine: {why}. Approve only if the user opted in.")
    for pattern, why in EXECUTES_PROJECT_CODE:
        if pattern.search(command):
            return decide("ask", f"This executes code from the repository under audit: {why}. Approve only if you trust it to run here.")
    return check_scripts(command, data, audit_dirs)


def check_write(data: dict[str, Any], audit_dirs: list[str]) -> Decision | None:
    """Apply the file-write rules (protected files, secrets in audit output, edits outside it)."""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    for directory in audit_dirs:
        if any(is_under(file_path, os.path.join(directory, name)) for name in PROTECTED_FILES):
            name = file_path.rstrip("\\/").replace("\\", "/").rsplit("/", 1)[-1]
            return decide("deny", f"{name} is generated by the skill's scripts and checked by the coverage gate; it can't be edited. Re-run the script instead (inventory.py, deps.py).")
    if any(is_under(file_path, directory) for directory in audit_dirs):
        pieces = [tool_input.get(k) for k in ("content", "new_string", "new_source")]
        edits = tool_input.get("edits")
        if isinstance(edits, list):
            pieces.extend(e.get("new_string") for e in edits if isinstance(e, dict))
        text = "\n".join(p for p in pieces if isinstance(p, str))
        if KNOWN_EXAMPLES.search(text):
            return None
        if any(shape.search(text) for shape in SECRET_SHAPES):
            return decide("deny", "Audit output must not contain unredacted secrets (SKILL.md rule 7). Show the type, location, and at most the first 4 characters.")
        return None
    return decide("ask", f"Modifying a project file during an audit: {file_path}. Approve only fixes or proof tests the user has accepted (SKILL.md rule 8).")


def emit(decision: Decision) -> None:
    """Print the permission decision the way Claude Code expects it (no trailing newline)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision[0],
            "permissionDecisionReason": f"[appsec-auditor] {decision[1]}",
        },
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.flush()


def main() -> int:
    """Run the guard for one tool call; always exits 0 (the decision travels in the JSON)."""
    common.configure_streams()
    data = common.read_input()
    if data is None:
        return 0
    audit_dirs = common.active_audit_dirs(data)
    if not audit_dirs:
        return 0
    tool = data.get("tool_name")
    tool_input = data.get("tool_input")
    decision: Decision | None = None
    if tool in ("Bash", "PowerShell"):
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        decision = check_command(command if isinstance(command, str) else "", data, audit_dirs)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        decision = check_write(data, audit_dirs)
    if decision is not None:
        emit(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
