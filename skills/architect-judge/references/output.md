# Report template

Lead with the verdict. Keep the language plain and declarative. Drop a section only when it has nothing real in it, never to soften the report. Cite artifact locations as `[§3.2]`, `[diagram: Ingestion flow]`, or `[main.tf:42]`, and criterion IDs from `dimensions.md` as `SEC-5`. Mark unverified external facts **[unverified]**.

Do not include author, team, or reviewer names anywhere in the report.

```markdown
# Architecture Review: <artifact title, version, date>

## Verdict: <Approved | Approved with Conditions | Revise and Resubmit | Rejected>

**Overall score: <NN>/100**. <Deciding gate, if any, e.g. "Gate 1 applies: SEC-5 is Critical.">. Confidence: <high | medium | low>.

<Two or three sentences: why this status, the single most important issue to fix, and the single most important strength.>

<If applicable: "Reviewed in a session with prior context; judged on the artifact alone.">

## 1. Initial assessment

- **Artifact:** <type; files or sections reviewed>
- **Scope:** <in scope> · **Out of scope:** <...>
- **Stated intent:** <goals and key requirements as the artifact states them, with citations>
- **System profile:** <workload, platform, data classes, users, geography → applicable regimes and Well-Architected lenses>
- **Review readiness:** <n of 9 minimum content items present; list the missing ones>
- **First read:** <2–3 sentences on the overall shape and where risk concentrates>

## 2. Scorecard

| Dimension | Weight | Score (0–5) | Weighted | Headline |
|---|---|---|---|---|
| Architecture Alignment | 15 | x.x | xx.x | <one line> |
| AWS Well-Architected | 35 | x.x | xx.x | <one line> |
| Architecture Quality | 15 | x.x | xx.x | <one line> |
| Data Management | 15 | x.x | xx.x | <one line> |
| Architecture Governance | 10 | x.x | xx.x | <one line> |
| Compliance | 10 | x.x | xx.x | <one line> |
| **Overall** | **100** | | **NN** | |

**Well-Architected pillars:** Security x.x (counted twice) · Operational Excellence x.x · Reliability x.x · Performance Efficiency x.x · Cost Optimization x.x · Sustainability x.x

<If weights were rescaled for scope, show the rescaled weights and why.>

<details><summary>Criterion scores</summary>

| ID | Criterion | Score | Evidence |
|---|---|---|---|
| ALN-1 | ... | 3 | [§2.1] goals traced to decisions D1–D4; D5 untraced |

</details>

## 3. Synthesis

<A short paragraph per root cause: the underlying cause, the findings it explains (by ID), and the dimensions it pulls down. This is the "why" behind the scorecard.>

## 4. Strengths

- **<strength>** — <evidence and the standard it satisfies> [citation]

## 5. Critical issues and gaps

Ranked most severe first.

### C1. <title> — Critical · <criterion ID(s)>
- **Finding:** <what is wrong, specifically> [citation]
- **Standard:** <principle, framework best practice, or regulation clause it violates>
- **Impact:** <what happens, under what conditions>
- **Remediation:** <the concrete change>
- **Acceptance criterion:** <the evidence that closes it>
- **Effort:** <S | M | L> — <one line>

### H1. <title> — High · <criterion ID(s)>
<same fields>

**Gaps** (not addressed in the artifact, scored 0):
| ID | Missing | Severity | Required content |
|---|---|---|---|

## 6. Recommendations

Prioritized. Root-cause fixes first, because they close several findings at once.

| # | Recommendation | Closes | Effort | Priority |
|---|---|---|---|---|
| 1 | <concrete action> | C1, H2, H4 | M | Before resubmission |

**Improvements (Medium / Low):**
- <M1: one line, with ID and citation>

## 7. Approval status

**<Status>**

<For Approved with Conditions: a conditions table.>
| # | Condition | Acceptance criterion | Must close by |
|---|---|---|---|

<For Revise and Resubmit: "A resubmission must include:", followed by an exact list.>
<For Rejected: why the approach can't be fixed in place, and the direction that would be viable.>

**What would change this verdict:** <the specific evidence, in a revised artifact, that would move the status up>.

## Out-of-scope observations

<Issues seen outside the declared scope. Not scored. Any Critical security or compliance issue must appear here.>
```

## Style rules

- **One finding, one place.** File each finding under its primary dimension and refer to it by ID elsewhere.
- **Pass the swap test.** If a finding would read the same for a different architecture ("ensure security best practices are followed"), cut it or make it specific.
- **No hedging verbs on Critical and High findings.** Write "The design stores PAN unencrypted in the staging bucket [§5.3]", not "There may be concerns around encryption."
- **Strengths are specific, too.** "Uses the transactional outbox for order events [§4.2], removing the dual-write risk" is a strength. "Good use of AWS services" isn't.
- **Remediations are decisions.** Recommend one option and say why. If a trade-off really is the author's call, state the criterion that should decide it.
