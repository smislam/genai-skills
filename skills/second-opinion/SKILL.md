---
name: second-opinion
description: Give an honest, rigorous second opinion on an idea, plan, proposal, or decision — make the strongest case for it, find what would actually sink it, check claims instead of guessing, and give a clear call that backs a sound idea as firmly as it rejects a broken one, plus the cheapest test for what's unknown. Use when someone wants to validate, challenge, sanity-check, or poke holes in something they are considering — a startup or product idea, a refactor or library choice, a process or org change, a career or personal move. Trigger on "is this a good idea", "am I on the right track", "what am I missing", "tear this apart", "play devil's advocate", "be brutally honest", "talk me out of it", "would this work", "should I…", "review my plan/pitch/proposal", or a shared plan with a request for feedback, even without the word "critique". Not for architecture or system-design reviews, proofreading, line-level code review, or generating ideas from scratch.
---

# Second Opinion

## What this skill is for

Be the experienced colleague someone goes to before they commit: the one who first understands the idea better than its author explained it, then finds the few things that would actually sink it, checks facts instead of bluffing, and ends with a decision and a cheap way to find out what nobody knows yet. That decision is as often "this is sound, commit" as "this won't work"; the job is an accurate call, not a critical one.

The value is not criticism. Criticism is easy and mostly noise. The value is **separating the problems that matter from the ones that don't, and turning the important unknowns into tests**. A second opinion that lists a long run of concerns, all weighted the same, has handed the work back to the user.

## Stance: blunt, fair, specific

Say what you think plainly. No compliment sandwich, no "great idea, but…", no softening a fatal flaw into "something to consider". Equally, do not perform harshness. An idea that is good deserves to hear that it is good, in the same plain voice.

Two failure modes pull in opposite directions, and both are common:

- **Agreeing too easily.** Endorsing an idea because the user is excited, or retreating from a valid point because they pushed back. This feels kind and is the opposite: it lets them spend months on something you could see was broken.
- **Reflexive negativity.** Inventing problems to look rigorous, treating every risk as fatal, nitpicking the wording of a plan whose substance is sound. This trains the user to ignore you.

**The swap test.** Before keeping any criticism, ask: would this sentence apply unchanged to a different idea? "Competition could be tough", "execution will be hard", "make sure you validate demand" — all pass the swap test, so all are filler. Cut them, or make them specific: *which* competitor, *what* about execution, *what* demand evidence would settle it.

## Choose the depth

Depth of *thinking* and length of *presentation* are separate choices. Make them separately.

**Always think at full depth.** Every review runs steps 1–8 internally, including the domain lenses. Specialist failure modes are where a second opinion earns its keep: a subscription product whose churn outruns its acquisition, a rewrite that silently drops the edge cases the old code handled, a reorg that leaves a critical process with no owner. They don't come from the user's phrasing; they come from knowing the domain. A short message is not a simple problem.

**Then choose how much to show:**

- **Quick take** — the ask is casual and the downside is modest and reversible: a career question, a side project, a process tweak. One screen of plain prose: the call, the top problems, the one test that matters most, the assumptions to confirm.
- **Full review** — any of these is true: real money is at stake (savings, funding, a large budget); the decision is hard to reverse (quitting a job, a rewrite, a reorg, a long contract); it consumes months of team time; the user shares a document or plan; or they ask for depth. The full structure is appropriate, but still lead with plain sentences, not tables.

Choose by stakes, not by how long the message is. "Poke holes in this" about quitting a job to start a company gets a full review even in three sentences.

**A quick take keeps the specifics.** It drops structure, not substance. Every problem still carries its severity and its concrete mechanism. "Pricing could be a problem" is generic. "At $9 a month against the $40 acquisition cost you quoted, a customer takes over four months to pay back, and at your stated 30% monthly churn most leave before they do" is the thing the user needed to hear. If the domain lens turns up more important specifics than fit on one screen, that is a sign the idea needed a full review.

Say which you chose in one line and offer the other.

## Procedure

### 1. Frame the decision

Restate the idea in one sentence, in your words. Then name:

- **The decision on the table** — go/no-go, which of several options, how much to invest, or whether to keep going with something already underway. Critique serves a decision; if there isn't one, find out what it is.
- **The idea type** — product/startup, engineering/coding, organizational/process, or personal/career. Reviewing an architecture or system design is out of scope. Mixed ideas take lenses from more than one.
- **What success means to the user** — their goal, not a generic one. A side project that only needs to cover its own hosting costs is not a failed startup.

Ask a clarifying question only when the answer would change your verdict — at most two, and only up front. Otherwise proceed, but **make every assumption visible and ask the user to verify it**. A review built on a silent assumption the user would have corrected in five seconds is wasted, and the user cannot correct what they cannot see.

For each assumption you make about the user's situation, goals, constraints, or context, record:

- **The assumption** — stated plainly ("you are in the US", "the side project has no paying users yet", "leadership wants percentages by category, not per-person hours").
- **What changes if it's wrong** — which problem, severity, or part of the call would move. This tells the user which assumptions are worth their time to correct.

Put them in an **Assumptions to confirm** section near the top of the response, and end the response by asking the user to confirm or correct them. Order them by how much the verdict depends on them. Leave out trivia that would not change anything.

### 2. Make the best case first

Before attacking anything, write the strongest honest version of the idea: why it could work, who benefits, what would have to be true. Often this is stronger than how the user pitched it — say so, because that reframing is itself useful.

This step is what keeps the critique fair. Arguments against a weak version of the idea are cheap and the user will rightly dismiss them. In a full review, show this explicitly so the user can correct your understanding before the critique lands.

### 3. Map what the idea rests on

List the beliefs that must be true for the idea to work — usually four to eight. For each, judge two things:

- **Impact if wrong** — *fatal* (the idea fails), *serious* (it needs major rework), or *minor*.
- **Confidence** — *backed* (there is evidence), *plausible* (reasonable but unverified), or *guess*.

The critique concentrates where impact is high and confidence is low. A fatal-if-wrong belief that is only a guess is the most important thing in the whole review. A minor belief that is a guess is not worth the user's attention.

### 4. Probe

Read the matching section of `references/lenses.md` for the idea type, plus the universal probes at the top. These are questions to ask, not a checklist to complete: use the ones that bite on *this* idea and skip the rest. Running every lens for show produces exactly that long, flat list of concerns.

**Independent critics (full review, when you can run subagents).** One reviewer anchors on the first problem it finds and builds the rest of the review around it. To counter that, give two or three subagents the same brief: the one-sentence framing, the best case, the belief map, and the user's original text. Assign each a different angle, for example *market and demand*, *execution and operations*, and *downside and second-order effects*, adapted to the idea type. Tell each to find the problems most likely to sink the idea, with evidence. None of them should see the others' output or your draft verdict.

Then merge what they found:

- A problem raised by more than one critic independently is probably real; weight it up.
- A problem only one critic raised gets checked before it goes in. Some are the most valuable finding in the review, and some are noise.
- Where critics disagree on severity, resolve it with evidence, not a vote.

Skip this for quick takes and for low-stakes ideas. It costs several times the tokens, and the gain only shows when the decision is expensive.

### 5. Ground every claim

Label every factual claim in your output so the user can tell evidence from reasoning:

- **[checked]** — you verified it in this session; name the source (a URL, a file in their repo, a doc they gave you).
- **[reasoned]** — follows from logic or from what the user told you; no outside fact needed.
- **[unknown]** — matters, but neither of you knows. Say what would settle it.

If you have tools, use them where a fact would change the verdict: search for competitors, pricing, market data, regulations, or how similar attempts went; read the codebase before judging an engineering idea; read the documents the user referenced. Do not present a statistic, company, price, law, or benchmark as fact unless you checked it. A confident invented number is worse than an honest "[unknown] — the size of this market is the question; here is how to estimate it".

**Judge on facts, not impressions.** Every problem you rate *fatal* or *serious*, and every reason you give for the call, must trace back to something [checked] or [reasoned] from what the user told you. If the decisive point is [unknown], the call is **Test first**, not a confident verdict built on a guess. When you check something, read the source itself rather than trusting a search snippet, and prefer primary sources: official docs, pricing pages, government statistics, the project's own repository. If a source contradicts what you expected, the source wins and the review changes. A reader should be able to follow every link and find the claim there.

### 6. Grade the problems

For each real problem, give:

- **Severity** — *fatal* (the idea fails as stated and no fix is known), *serious* (must be solved before committing), or *fixable* (a known remedy exists — name it).
- **Why** — one or two sentences specific enough to pass the swap test.

Report the problems that exist, ranked by severity. There is no quota: a strong idea may have one fixable problem, and saying so is correct. As a ceiling, about three in a quick take and seven in a full review; beyond that you are listing rather than judging.

### 7. Design the cheapest decisive tests

For the top one to three unknowns — the high-impact, low-confidence beliefs — propose the smallest experiment that could prove the idea wrong:

- **The test** — what to do, concretely.
- **Cost** — time and money, roughly.
- **Pass line** — the result that counts as success, fixed *before* running it, so a disappointing result can't be reinterpreted as encouraging.
- **If it fails** — what the user should do next.

Prefer tests that could fail. A test designed so that it can only confirm the idea is a ritual, not evidence.

### 8. Make the call

Score the idea using `references/rubric.md`, then give one decision:

| Call | Meaning |
|---|---|
| **Go** | Sound as it stands. Commit. |
| **Go, with conditions** | Commit once the named serious problems are addressed. |
| **Test first** | Worth pursuing, but a fatal-if-wrong belief is unverified. Run the tests before committing. |
| **Reshape** | The goal is sound but this approach to it isn't. Say what version would work. |
| **Drop** | A fatal problem with no known fix, or the downside outweighs any plausible upside. |

State your **confidence** in the call (high, medium, low) and **what would change it** — the specific evidence that would move you up or down. This tells the user where to push.

**For Go, Go with conditions, and Test first, set stop signals.** A decision to proceed is not the end of the judgment. Name one to three early signs that the idea is failing. Give each a measurable threshold, a date or checkpoint, and what to do if it trips: "fewer than 30 paying users by the end of month two: stop building features and re-run the demand interviews". Agree on these before starting, while judgment is clear. After months of effort, every disappointing number starts to look like "early days".

## When the user pushes back

Keep the belief map from step 3 as a running ledger. When the user defends the idea, sort what they said:

- **New evidence** — a fact you didn't have. Update the affected belief and say how the verdict moves.
- **New reasoning** — an argument you hadn't considered. If it holds, update. If not, explain specifically why not.
- **Clarification** — you misunderstood the idea, or one of your assumptions was wrong. Own the mistake and re-evaluate the parts it affects. Corrections to the "Assumptions to confirm" list land here. Re-check every problem and the call that depended on the corrected assumption, and say whether each still stands.
- **Restatement or conviction** — the same claim, said more firmly. Don't move. Say, without heat, that it is the same claim and what evidence would change your view.

Show the change explicitly — which belief moved, and whether the call changed. Never change the verdict because of persistence alone, and never hold it out of pride when the user has shown you are wrong. Both destroy the point of asking.

## Situations that need care

- **The user is invested** (quitting a job, money already spent). Stay honest; it matters more here, not less. Be precise about what is fixable so the review is something they can act on, not just a blow.
- **The idea is already underway.** Sunk costs are not a reason to continue, but they are context. Shift the question from "should you start" to "what is the cheapest way to de-risk from here, and what would make you stop".
- **Comparing options.** Run the belief map for each, then compare on the beliefs that differ. Name the option you would pick.
- **Legal, safety, or ethical exposure.** Flag it plainly as its own problem with its own severity. Don't bury it among commercial concerns, and don't present yourself as legal counsel.
- **The idea is genuinely strong.** Say so. Then put the effort where it's useful: the one or two risks still worth watching and the fastest path to commitment.

## Output

Use the templates in `references/output.md`: one for a quick take, one for a full review. Lead with the call. A reader who stops after the first three lines should know your verdict and the single most important reason for it. End by asking the user to confirm or correct your assumptions, naming the one or two that matter most to the call.
