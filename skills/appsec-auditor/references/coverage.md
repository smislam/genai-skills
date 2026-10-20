# Deterministic coverage

The AI's judgment varies between runs, but *what gets examined* doesn't. Scripts build a fixed checklist from the repository, the AI records a decision for every item, and a Stop hook won't let the audit finish until every item is decided and the evidence is in place. The same commit, rules version, and depth always give the same checklist, so two audits can be compared item by item.

Requires Node.js 18 or later (not installed by the skill). Without it, run the audit by instruction alone, and label the report **non-deterministic: coverage not enforced** at the top.

## Files

All in `.appsec-audit/` at the repository root:

| File | Written by | Contents |
|---|---|---|
| `coverage.json` | `inventory.js` | The checklist: files scanned, every rule hit (`items`), packages, and unresolved dependencies |
| `files.txt` | `inventory.js` | The exact list of files scanned |
| `deps.json` | `deps.js` | OSV, KEV, and EPSS results, plus one `dependency` item per package advisory |
| `reads.jsonl` | the `track` hook | Every file the AI opened with the Read tool |
| `ledger.json` | **the AI** | One decision per checklist item |
| `findings.json` | **the AI** | Every finding in structured form (`output.md`); the source for the SARIF |
| `results.sarif` | `sarif.js` | Rendered from `findings.json`; never edited by hand |
| `state.json` | **the AI** | `running`, `paused`, or `done`; plus `"hooks": false` when the guardrail hooks didn't load, which turns the entry-point read check into a disclosed "not enforced" line instead of a gap |
| `report.md` | **the AI** | The report (`output.md`) |

The guard hook blocks edits to `coverage.json`, `deps.json`, and `reads.jsonl`, so the checklist can't be shrunk to pass the gate. To change them, re-run the script.

## The checklist

`node ${CLAUDE_SKILL_DIR}/scripts/inventory.js --root <repo> --depth <quick|standard|deep>` writes `coverage.json`. Each item has a stable ID that survives line shifts:

| Kind | ID | From | What a decision means |
|---|---|---|---|
| `entrypoint` | `C-…` | Entry-point rules: routes, handlers, listeners, jobs | You traced this entry point's input to its sinks, and its authentication and authorization |
| `pattern` | `C-…` | Sink and misconfiguration rules | The hit is a vulnerability, or isn't, and why |
| `secret` | `C-…` | Secret rules over the working tree | A real credential or not; the excerpt is redacted |
| `secret-history` | `H-…` | Secret rules over every commit (Standard and Deep) | Same, for secrets added anywhere in history |
| `dependency` | `D-…` | `deps.js`: one per package, version, and advisory | Affected and reachable, not affected, or needs review |

The rules live in `rules/rules.json`; its `version` is recorded in the report. Each item names its `rule`, `cwe`, `file`, `line`, an `excerpt`, and the `guide` to read when deciding it.

## The ledger

`ledger.json` is written by you, the AI:

```json
{
  "entries": [
    { "id": "C-3f9a1c2b4d5e", "status": "finding", "finding": "F-02" },
    { "id": "C-8b7e6d5c4a3f", "status": "false_positive", "reason": "Parameterized: the concatenated part is the fixed column list from ALLOWED_SORT (OwnerRepository.java:41)." },
    { "id": "C-1a2b3c4d5e6f", "status": "reviewed", "reason": "GET /owners/{id}: id bound as Integer, repository lookup only; no auth exists app-wide (see F-01)." },
    { "id": "D-eba23c1bbf21", "status": "finding", "finding": "F-05" },
    { "match": { "rule": "generic.secret.assignment", "path": "src/test/" }, "status": "false_positive", "reason": "Test fixtures with dummy values (e.g. 'test-password'); not used outside tests." }
  ]
}
```

| Status | Use for | Needs |
|---|---|---|
| `finding` | A verified vulnerability (`triage.md`), or a chain | `finding`: the report's ID (`F-07`, or `C-1` for a chain). Several items can share one finding |
| `false_positive` | Disproved | `reason` (10+ characters) saying what stops it, with file:line |
| `needs_review` | Can't be decided from the repository | `reason`; also list it in the report's "Needs human review" section |
| `reviewed` | Entry points: traced, and this entry point has no flaw of its own | `reason`: what was checked. If an app-wide finding also applies (for example, no authentication anywhere), still use `reviewed` and cite it in the reason; use `finding` only for a flaw specific to this entry point. That keeps the per-kind counts comparable between runs |
| `not_applicable` | Out of scope (for example, a dev-only dependency that never ships, for license or reachability purposes) | `reason` |

**Group entries** (`"match"` with `rule`, `kind`, and/or `path`) decide many items at once, such as all hits of one rule in test code. They can't be findings, and they can't cover entry points, which must each be decided by ID. An ID entry overrides a group entry for that item. Use groups sparingly, and only when the reason is true for every item they match.

**Findings beyond the checklist.** The AI review will find issues no rule matched (authorization logic, business-logic flaws). Report them as findings in the usual way. They don't need ledger entries, but the report should say which findings came from AI review beyond the checklist.

## The gate

`node ${CLAUDE_SKILL_DIR}/scripts/coverage-check.js --root <repo>` reports exactly what's left. Add `--list` (optionally `--undecided` or `--kind <kind>`) for a compact view of the checklist itself: ID, kind, location, and excerpt, one per line. The Stop hook runs the same check, and blocks the end of the turn until it passes. The audit is complete when:

1. `coverage.json` exists and matches the current commit (re-run `inventory.js` if the code changed).
2. `deps.json` exists whenever there are packages. If OSV.dev couldn't be reached, the report says dependency results are "not checked".
3. Every ledger entry is valid, and refers to an item in the current checklist.
4. Every checklist item has a decision.
5. Every entry-point file was opened with the **Read** tool. Read it through the tool, not with `cat`, so the read log records it.
6. `report.md` exists, contains every finding ID used in the ledger, and contains the **current** coverage summary: run `coverage-check.js --summary` and paste its output into the Coverage section. The summary carries a fingerprint of the checklist and the decisions, so re-paste it after any ledger change.
7. `findings.json` exists, contains every finding ID used in the ledger, and every finding has an ID, title, severity, confidence, and location.
8. `results.sarif` is exactly what `sarif.js` renders from the current `findings.json`.

**Pausing.** Ask mid-audit questions with the AskUserQuestion tool, which doesn't end the turn. If you must end the turn to wait for the user, first write `state.json` as `{"status": "paused", "reason": "<what you're waiting for>", "updatedAt": "<ISO time>"}`, and set it back to `"running"` when the audit resumes. A paused audit older than 24 hours is treated as running again.

**Finishing.** When the check passes, write `state.json` as `"done"` and remove `.appsec-audit/.active`.

## Comparing runs

Because IDs are stable, two audits of the same commit can be compared directly. Same checklist, then diff the two `ledger.json` files: every difference is a recorded judgment that changed, item by item. Across commits, items with the same ID are the same code.
