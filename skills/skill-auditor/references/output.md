# Output templates

Contents: audit report · fix plan · after the fixes · quick answer · several skills at once

Use plain sentences first. Tables only for the scoreboard, the trigger test, and findings. Write the report to the file the user chose; if they did not choose, default to `skill-audit-<name>.md` in the current folder, and say where it is.

## Audit report

```markdown
# Skill audit: <name>

**Result:** Safety: <verdict>. Quality: <grade> (<score>/100).
**Mechanical:** risk <score>/100 (<SAFE / CAUTION / DO_NOT_INSTALL>) before review, <score>/100 after review | coverage <percent>% (<n> partial, <n> not inspected)
**Target:** <path> | **Source/trust level:** <own / team / public / unknown> | **Depth:** <quick / standard / deep>
**Covered:** <N> of <N> files read; images viewed <n of n>; scripts <read only / not read>; mechanical pass <script / by hand>; dependency lookup <done / not requested / failed>; independent check <subagent / self>.
**Review:** <n> findings: <n> confirmed, <n> dismissed, <n> low-confidence, <n> needs you, <n> added by me; <n> unreviewed.

## Summary
Three to five sentences: what the skill does, the one most important problem, the one thing it does well, and what to do next.

## Assumptions to confirm
- <assumption> - if wrong: <what changes>

## Scoreboard
| Dimension | Weight | Rating (0-4) | Evidence |
|---|---:|---:|---|

## Safety
Verdict and the reasoning, then each safety finding with file, line, quoted text, what it can do, and whether it fits the stated purpose.

## Trigger test
| # | Prompt | Should load? | Result | Why |
|---|---|---|---|---|
Misses in both directions, and the description rewrite that fixes them. State whether the test was blind (subagent) or self-judged.

## Findings
Ranked critical first. For each:

### <ID> <short title> - <severity>
- **Where:** `<file>:<line>`
- **Evidence:** "<quoted text or code>"
- **Why it matters:** <one or two sentences that pass the swap test: would not fit any other skill unchanged>
- **Fix:** <the change, concrete enough to apply>
- **Status:** confirmed / needs your input

## Dismissed leads
Mechanical findings you checked and ruled out, one line each with the reason. Include every suppressed finding with its audit-ignore marker and your judgment of it.

## Changes since the last audit
Only when you compared against an earlier report: files added, removed, and changed; permissions, hooks, and hosts added; whether the description still matches.

## Artifacts
Where the JSON report, SARIF file, and review file are, so the audit can be repeated and compared.

## Strengths
What to keep, with the evidence. Three at most.

## Not covered
Files or behaviors not examined, and why.

## Next steps
Ordered, smallest effective set first.
```

Rules:

- Every finding quotes evidence. No quote, no finding.
- Findings are ranked by consequence, not by the order found. A few real findings beat a long list; the script's counts are not the report.
- Do not pad. A strong skill gets a short report that says it is strong.
- Include a mechanical finding only if confirmed. The rest go under "Dismissed leads".
- Strengths are real, not a compliment before the criticism.

## Fix plan

Offer it after the report, and wait for approval before editing anything.

```markdown
## Fix plan for <name>

| # | Finding | Change | Files | Reversible | Risk |
|---|---|---|---|---|---|

Order: safety first, then triggering, then structure, then polish.
Not fixing, and why: <items that need the author's decision or change behavior>.
Check afterward: re-run the mechanical pass, re-run the trigger test, and show the before and after counts.
```

State plainly which changes alter the skill's behavior (rewriting instructions) and which are mechanical (fixing a link). Never edit the skill's safety-relevant text (hooks, scripts, permission fields) as a side effect of a style fix.

## After the fixes

Show evidence: the command run, the new finding counts beside the old ones, and the trigger-test table again if the description changed. Report anything left open. Do not claim a skill is fixed because edits were made; claim it when the re-run shows it.

## Quick answer

For a small question ("is this description good?", "can I install this?") skip the template: give the verdict, the two or three reasons with quoted evidence, and the one change that matters most. Say what was not checked.

## Several skills at once

Open with a comparison table (skill, safety verdict, grade, top issue), then one section per skill using the template above in short form. Add an **Overlap** section listing prompts that more than one skill would claim, and the fix.
