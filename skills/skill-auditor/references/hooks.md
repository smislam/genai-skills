# Hooks review

Contents: why hooks matter · what to read · event and matcher checks · exit codes and decisions · loop guards · fail open or closed · handler types · portability · trust · is a hook the right tool

## Why hooks matter

A hook is the one place a skill can make something certain. Instructions in prose are followed almost always; a hook runs every time, whatever the model decides. That makes hooks the right tool for rules with no exceptions, and the riskiest part of a skill, because they run without a prompt and with the user's permissions.

## What to read

Find hooks in three places and read all of them:

- `hooks/hooks.json` or any `*hooks*.json` shipped in the folder (plugin hooks)
- a `hooks:` block in `SKILL.md` frontmatter (the script flags it as HKS10; read it by hand)
- instructions in the skill that tell the user or agent to add hooks to `settings.json` (a tampering finding; see `safety.md`)

Then read every script a hook runs, in full. A hook config is harmless text; the script is the behavior.

## Event and matcher checks

- The event name must be one the host knows. A misspelled event never fires, and nothing reports it.
- A matcher with only letters, digits, underscores, hyphens, and `|` is an exact or alternation match on the tool name. Anything else is a regular expression; check it compiles and that it matches what the author means (`Edit|Write`, `mcp__server__.*`).
- A matcher that is missing or `*` fires on every call. For a hook that runs a slow or noisy script, narrow it, or add an `if` condition.
- Check the event fits the goal. To stop a bad action, use `PreToolUse`. To react to a finished action (format, lint), use `PostToolUse`. To refuse to end the turn until a check passes, use `Stop`. A guard on `PostToolUse` is too late to block anything.

## Exit codes and decisions

For command hooks:

| Exit | Effect |
|---|---|
| 0 | Success. If the script printed JSON, its fields apply; otherwise proceed |
| 2 | Block. Stops the action; stderr is shown to the model as the reason |
| anything else | Non-blocking error: the action goes ahead (unless the config sets a block-on-failure option) |

A very common fault: a guard script that exits 1 on failure and believes it has blocked something. It has not. Check each guard's exit paths:

- every path that should block exits 2 or prints a block/deny decision,
- the stderr message tells the model what to do next, not just "blocked",
- unexpected errors (bad JSON input, missing file) are handled on purpose, either block or allow, never by crashing into a non-blocking code by accident.

For `PreToolUse`, a decision of deny blocks, allow skips the prompt, and ask prompts. Check that a hook returning "allow" cannot approve something the user never meant to approve; an allow-everything hook removes the permission system.

## Loop guards

A `Stop` hook that blocks makes the model keep working, then the model tries to stop again and the hook runs again. If the check can never pass (a missing tool, a flaky test, a wrong path), the loop never ends. Look for one of:

- a check of the input's `stop_hook_active` field so the hook stands down on a retry,
- a counter or marker file that caps the number of blocks,
- a check that is guaranteed to be satisfiable.

A blocking `Stop` hook with none of these is a finding (HKS03). Also check the escape: when the hook can't run (its runtime is missing, no network), does it allow the stop and say why, rather than trapping the session?

## Fail open or fail closed

Decide per hook, and look for the decision in the code:

- **Safety guards** (block a dangerous command, protect a file) should fail closed: if the script cannot decide, it blocks, with a message.
- **Convenience hooks** (formatter, notifier) should fail open: if the script breaks, the work continues.

A guard that fails open when its parser throws can be bypassed with unusual input. A formatter that fails closed stops all editing when the formatter is not installed.

## Handler types

| Type | Deterministic? | Review |
|---|---|---|
| `command` | Yes | Read the script. Check arguments are quoted and that nothing from the event input reaches a shell unescaped. |
| `http` | Yes, but sends data out | Read the URL and what is in the body: tool input and prompts can contain secrets. Check the allowed-variable list for headers. |
| `mcp_tool` | Depends on the tool | Read the tool. |
| `prompt`, `agent` | No, a model decides | Fine for advisory checks. A finding if the skill presents it as enforcement. |

For command hooks that read the event from stdin, check the script treats it as untrusted: a file path or command string in the input must not be spliced into a shell command, a `path.join` without a containment check, or an `eval`.

## Portability

- Hook commands should locate scripts through the plugin or skill root variable (`${CLAUDE_PLUGIN_ROOT}` for plugins), never an absolute path, and never the project directory when the script ships with the skill (HKS05).
- Every script the hook names must exist inside the folder (HKS04).
- Runtime: a hook that needs Node.js, Python, or `jq` fails silently on a machine without it. The skill should say so, and the hook should degrade on purpose (see fail open or closed).
- Windows and Linux: path separators, `bash` versus PowerShell, line endings (PRT04), executable bits.
- Every hook has a timeout (HKS06). The default is generous; a script that waits on the network can freeze every tool call.

## Trust

Hooks run on every matching event, silently, and see everything that passes through that event: commands, file paths, file contents, prompts.

- A hook that logs or sends event data must say where.
- A hook that edits files, settings, or other hooks is a persistence finding.
- Project-level hooks in a shared repo run for everyone who trusts the folder.
- Count the hooks. Every one fires wrongly sometimes and someone has to maintain it; a skill shipping a dozen has probably turned preferences into enforcement.

## Is a hook the right tool

Ask for each hook: is this a rule with no exceptions, and is it checked mechanically?

- Yes to both: a hook is right.
- A preference, or a judgment call: leave it as an instruction. A hook that is wrong 1 time in 20 trains users to disable all hooks.
- A check that costs minutes: run it at `Stop`, not on every edit.

Also look for the missing hook: a skill whose most important rule is "never X" or "always run Y before finishing", with nothing enforcing it.
