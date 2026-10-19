# Rubric

Score six dimensions from 1 to 5 using the anchors below. Then apply the decision rules — **do not average the scores into a verdict**. An idea with five excellent dimensions and one fatal one is a failed idea, and an average would hide that.

Score from evidence, not optimism. If a dimension rests on [unknown] beliefs, score what is known and let the evidence dimension carry the uncertainty.

## Dimensions

### Problem — is the need real and does it matter?
- **5** — Urgent, frequent, and felt by the people who would act. Evidence that they already spend money or effort on it.
- **3** — Real but tolerable. People complain but get by.
- **1** — Assumed, not observed. Or a problem only the author has.

### Fit — does this approach actually solve it?
- **5** — Directly removes the pain; clearly better than the current workaround for the people who matter.
- **3** — Helps, but only partially, or only for some of the people.
- **1** — Solves an adjacent problem, or adds as much friction as it removes.

### Feasibility — can this person or team actually do it with what they have?
- **5** — Within their skills, budget, and timeline, with margin to spare.
- **3** — Possible, but needs a skill, hire, or resource they don't yet have, or the timeline is tight.
- **1** — Needs something they cannot plausibly get, or a technical breakthrough.

### Edge — why this, why them, why now, over the alternatives (including doing nothing)?
- **5** — A clear, durable reason this wins: unique access, expertise, timing, or a cost advantage others cannot easily copy.
- **3** — Some advantage, but easily matched once it is proven.
- **1** — No reason this beats existing options or the status quo.

### Downside — what happens if it is wrong?
- **5** — Cheap and reversible; failure costs little and teaches a lot.
- **3** — Meaningful cost, but recoverable.
- **1** — Expensive and hard to reverse: savings, a career, a migration with no rollback, the team's trust.

### Evidence — how much of the above is known rather than hoped?
- **5** — The critical beliefs are backed by data, tests, or direct observation.
- **3** — A mix; some critical beliefs are still plausible guesses.
- **1** — Mostly conviction. The fatal-if-wrong beliefs are untested.

## How the dimensions read by idea type

| Dimension | Product/startup | Technical/architecture | Engineering/coding | Organizational/process | Personal/career |
|---|---|---|---|---|---|
| Problem | Customer pain | Measured system limit | Measured code cost | Pain felt by the people doing the work | The real goal underneath |
| Fit | Better than the workaround | Removes the limit | Lowers the cost | Changes the outcome, not just the ritual | Actually serves that goal |
| Feasibility | Build + reach customers | Team can build *and run* it | Team can finish it incrementally | Adoption is achievable | Skills, money, and time available |
| Edge | Moat, timing, access | Beats the boring alternative | Beats leaving it alone | Beats the current process | Beats cheaper routes to the same goal |
| Downside | Money and time burned | Outage, lock-in, migration risk | Half-finished migration, regressions | Overhead and lost trust | Runway, reversibility, dependents |
| Evidence | Customer behavior, not opinions | Metrics, load tests, prototypes | Coverage, profiling, spikes | Pilot results, baselines | Conversations with people who did it |

For the other idea types:

| Dimension | Buying a tool or vendor | Go-to-market / content | Money decision |
|---|---|---|---|
| Problem | A measured need the tool meets | A defined audience with a real problem | A clear purpose for the money |
| Fit | Meets the need better than what's already owned | Message and channel reach that audience | The return matches the goal and the timeline |
| Feasibility | Implementation, integration, and ownership are realistic | Budget and skills to execute and measure | Affordable in the bad case, not just the expected one |
| Edge | Beats cheaper options, including "use what we have" | A believable reason to choose this over competitors | Beats the alternative uses of the money |
| Downside | Lock-in, renewal cost, a failed security review | Spend without learning; brand damage | Loss the user can't absorb; illiquidity; penalties |
| Evidence | References, trials, documented terms | Pilot results, real conversion data | The source terms, base rates, a modeled downside |

## Decision rules

Apply in order and stop at the first that matches:

1. **Any fatal problem with no known fix** → **Drop**, or **Reshape** if the goal is sound and a different approach avoids the problem.
2. **Problem or Fit at 1** → **Reshape**. The work is aimed at the wrong target.
3. **Evidence at 1–2, and a fatal-if-wrong belief is untested** → **Test first**. Name the test.
4. **Downside at 1 and Evidence below 4** → **Test first**. Irreversible bets need evidence, not conviction.
5. **Any serious problems open** → **Go, with conditions**. List them.
6. **Otherwise** → **Go**.

## Confidence

- **High** — the call rests mostly on [checked] and [reasoned] claims, and plausible new information is unlikely to change it.
- **Medium** — one important belief is [unknown]; the call could move if it resolves the other way.
- **Low** — the call depends on beliefs neither of you can currently verify. Say so, and make the tests the main deliverable.

Always state what would change the call: "This moves to Go if the pilot hits the pass line; to Drop if more than half of the interviewees already use a free tool for this."
