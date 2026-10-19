# Output templates

Lead with the call. Use these structures, but drop a section that has nothing real to say rather than filling it — an empty "Strengths" section is better left out than padded.

## Contents
- [Quick take](#quick-take)
- [Full review](#full-review)
- [Call: <Go | Go, with conditions | Test first | Reshape | Drop> (confidence <high | medium | low>)](#call-go--go-with-conditions--test-first--reshape--drop-confidence-high--medium--low)
- [Assumptions to confirm](#assumptions-to-confirm)
- [The idea, at its best](#the-idea-at-its-best)
- [What it rests on](#what-it-rests-on)
- [Problems, ranked](#problems-ranked)
- [Tests to run before committing](#tests-to-run-before-committing)
- [Stop signals](#stop-signals)
- [Scorecard](#scorecard)
- [What would change the call](#what-would-change-the-call)
- [After pushback](#after-pushback)


Tag factual claims inline with **[checked]**, **[reasoned]**, or **[unknown]** as described in SKILL.md step 5. Tag the claims that carry weight; you don't need to tag every sentence.

Every response, quick or full, includes the assumptions you made and ends by asking the user to confirm or correct them.

## Quick take

Plain prose, no tables. It should read like a direct message from a sharp colleague, not a report. Roughly:

```markdown
**Call: <Go | Go, with conditions | Test first | Reshape | Drop>** (confidence <high | medium | low>). <One or two sentences: the single most important reason.>

**Assumptions to confirm:** <the one to three assumptions the call depends on most, each with what changes if it's wrong. Example: "I'm assuming you'd build this yourself; if you'd need to hire a developer, the runway problem gets much worse.">

<A short paragraph on what's genuinely strong, only if it's true.>

<A short paragraph per problem, most severe first, at most three. Name the severity in the first words ("The fatal problem is…", "A serious but fixable one…") and keep the reasoning specific.>

**Test this first:** <the one cheapest decisive test>. It passes if <result fixed in advance>; if it doesn't, <what to do>.

<For Go / Go with conditions / Test first: one sentence with the stop signal: threshold, checkpoint, action.>

<Close: ask them to confirm or correct the assumptions, naming the one that matters most. Offer a full review if the stakes justify it.>
```

## Full review

```markdown
## Call: <Go | Go, with conditions | Test first | Reshape | Drop> (confidence <high | medium | low>)

<Two or three sentences: the verdict, the main reason, and what would change it.>

## Assumptions to confirm

| # | Assumption | If it's wrong |
|---|---|---|
| 1 | <assumption about the user's situation, goals, or context> | <which problem, severity, or call moves, and which way> |

<Ordered by how much the call depends on each.>

## The idea, at its best
<The strongest honest version. If it differs from how the user framed it, say how.>

## What it rests on

| # | Belief | Impact if wrong | Confidence | Basis |
|---|---|---|---|---|
| 1 | <belief> | fatal / serious / minor | backed / plausible / guess | [checked: source] / [reasoned] / [unknown] |

<One sentence naming the belief or two that matter most — high impact, low confidence.>

## Problems, ranked

### 1. <Problem> — <fatal | serious | fixable>
<Why it matters for this idea specifically. Evidence, tagged.>
**Fix:** <remedy, if one exists, or "none known">

### 2. ...

## Tests to run before committing

| Test | Cost | Pass line | If it fails |
|---|---|---|---|
| <concrete experiment> | <time / money> | <result fixed in advance> | <what to do next> |

## Stop signals
<For Go / Go with conditions / Test first only.>

| Signal | Threshold | Check at | If it trips |
|---|---|---|---|
| <early sign of failure> | <measurable line> | <date or milestone> | <stop, pivot, or re-test> |

## Scorecard

| Dimension | Score | Why |
|---|---|---|
| Problem | n/5 | <one line> |
| Fit | n/5 | |
| Feasibility | n/5 | |
| Edge | n/5 | |
| Downside | n/5 | |
| Evidence | n/5 | |

<Which decision rule produced the call.>

## What would change the call
- **Toward Go:** <evidence>
- **Toward Drop:** <evidence>

---
<Close: ask the user to confirm or correct the assumptions above, naming the one or two that would move the call most.>
```

## After pushback

When the user defends the idea or corrects an assumption, respond with what moved and what didn't. The first line is still the call, with its confidence, so the user gets the answer to "so can I?" before the reasoning:

```markdown
**Updated call: <call>** (was <previous call>), confidence <high | medium | low> — or **Call unchanged: <call>**, confidence <level>
<One sentence: what moved it, or why nothing did.>

| Belief or assumption | Before | After | Why |
|---|---|---|---|
| <belief> | guess | backed | <the new evidence they gave> |
| <assumption> | assumed X | corrected to Y | <which problems this affects, and how> |
| <belief> | plausible | plausible | <restated, not new evidence — here is what would move it> |

<Short explanation, then any revised tests or stop signals.>
```
