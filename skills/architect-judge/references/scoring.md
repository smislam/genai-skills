# Scoring and verdict

Score from evidence in the artifact, never from intent or likelihood. When in doubt between two anchors, take the lower one and say what evidence would justify the higher.

## Criterion scale (0–5)

| Score | Anchor | Meaning |
|---|---|---|
| **0** | Absent | Not addressed anywhere in the artifact. |
| **1** | Inadequate | Mentioned, but wrong, contradictory, or materially deficient against the standard. |
| **2** | Weak | Partially addressed; significant gaps a reviewer could not sign off on. |
| **3** | Adequate | The essentials are addressed correctly; gaps are minor or non-blocking. |
| **4** | Strong | Well addressed and justified, with measurable targets; only cosmetic gaps. |
| **5** | Exemplary | Fully addressed, quantified, and *verified* (tests, evidence, automation), with trade-offs explicit. Rare. |

A score of 4 or 5 requires evidence beyond assertion. "Will be multi-AZ" earns at most 3; a deployment view showing multi-AZ placement with a tested failover earns 4–5.

**N/A** is allowed only for a criterion outside the declared scope, or one that doesn't apply to the artifact type (see the adaptation table in `dimensions.md`). Every N/A needs a one-line justification. "Not addressed" is a 0, never an N/A.

## Dimension score

Dimension score = the mean of its in-scope criterion scores, to one decimal. For Well-Architected, each pillar is scored 0–5 against its checks (the Security pillar is the mean of its `SEC` criteria), and the dimension score is the weighted mean of the in-scope pillars, with Security counted twice (see `dimensions.md` §2).

## Weights and overall score

| Dimension | Weight |
|---|---|
| Architecture Alignment | 15 |
| AWS Well-Architected | 35 |
| Architecture Quality | 15 |
| Data Management | 15 |
| Architecture Governance | 10 |
| Compliance | 10 |
| **Total** | **100** |

Overall score (0–100) = Σ (weight × dimension score ÷ 5).

If a whole dimension is out of scope, drop it and rescale the remaining weights to total 100. Show the rescaled weights in the report. The Well-Architected Security pillar and Compliance can only be scoped out when the requester explicitly says so. Even then, any Critical security or compliance issue noticed is still reported under "Out-of-scope observations", because silence on a known breach path is not acceptable.

## Severity

| Severity | Definition | Effect |
|---|---|---|
| **Critical** | Under expected conditions, will cause a security breach, loss or corruption of data, a regulatory violation, or failure to meet a core requirement. Or the artifact is missing something without which it can't be judged safe at all. | Blocks approval. |
| **High** | Material risk under plausible conditions, or a significant standards violation without sanctioned exception. | Must be closed before production; becomes a condition. |
| **Medium** | Degrades quality, operability, cost, or maintainability; no immediate risk. | Fix within an agreed timeframe; tracked. |
| **Low** | An improvement or best-practice refinement. | Advisory. |

Severity follows impact and likelihood, not how easy the fix is. An easy fix to a Critical issue is still Critical until fixed.

## Gates

Gates override the arithmetic. Apply them before the score bands.

1. **Any open Critical finding** → the status cannot be Approved or Approved with Conditions.
2. **A Critical finding that the chosen approach can't fix**, because closing it requires a fundamentally different architecture → **Rejected**.
3. **Any in-scope dimension below 2.0** → the status cannot be better than Revise and Resubmit.
4. **Well-Architected Security pillar or Compliance below 3.0** (when in scope) → the status cannot be Approved.
5. **Review readiness**: if more than half of the minimum reviewable content is absent → the status cannot be better than Revise and Resubmit, whatever the score.

## Approval status

After the gates, apply the first band that matches:

| Status | Requires |
|---|---|
| **Approved** | Overall ≥ 85, every in-scope dimension ≥ 3.0, no open Critical or High findings. |
| **Approved with Conditions** | Overall ≥ 75, every in-scope dimension ≥ 2.0, no open Critical findings. This includes a score of 85 or more that misses Approved only because of open High findings or a dimension below 3.0. Each High finding becomes a condition with an acceptance criterion and a closing milestone. |
| **Revise and Resubmit** | Overall < 75, or a gate blocks a better status, and the approach is fundamentally sound. |
| **Rejected** | Gate 2 applies, whatever the score. The approach should not proceed in its current form; say what direction would be viable. |

Report the status, the overall score, the gate that decided it (if any), and the band. If a gate overrode the score, say so in the first lines: "Overall 78, but gate 1 applies (SEC-5 Critical): Revise and Resubmit."

## Confidence in the verdict

- **High** — scores rest on explicit artifact content and verified standards; no Critical finding depends on [unverified] facts.
- **Medium** — some scores depend on ambiguous artifact content or unverified specifics. Name them.
- **Low** — the artifact is too incomplete or ambiguous to judge some dimensions reliably. The verdict stands, but say which resubmitted evidence would most change it.

Confidence describes the judge's certainty. It never softens the status.
