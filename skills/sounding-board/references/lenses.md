# Lenses

Read the universal probes, then the section for the idea's type. Mixed ideas (a technical product, a career move into a startup) take from more than one section.

Each lens lists the questions worth asking, the ways this kind of idea usually dies, and the facts worth checking with tools. Use what bites on the idea in front of you. An unused lens costs nothing; a lens applied for show adds noise.

## Contents
- [Universal probes](#universal-probes)
- [Product and startup](#product-and-startup)
- [Technical and architecture](#technical-and-architecture)
- [Engineering and coding](#engineering-and-coding)
- [Organizational and process](#organizational-and-process)
- [Buying a tool or choosing a vendor](#buying-a-tool-or-choosing-a-vendor)
- [Go-to-market, marketing, and content](#go-to-market-marketing-and-content)
- [Money decisions](#money-decisions)
- [Personal and career](#personal-and-career)
- [Bias checks](#bias-checks)

## Universal probes

- **Pre-mortem.** It is a year from now and this failed. Write the most likely one-paragraph explanation. Then the second most likely. These are usually the real top risks, and they are often different from the ones the user is worried about.
- **Reference class.** What usually happens to attempts like this? Find the base rate — how often similar products find customers, how often rewrites ship on time, how often reorganizations deliver the promised gain — and ask what makes this case different. "We're different" needs a reason.
- **Inversion.** What would you do if you wanted this to fail? Check whether the plan currently does any of those things.
- **Why hasn't this been done?** If the idea is obvious and valuable, either someone has done it (find them), someone tried and failed (find out why), or there is a non-obvious obstacle. Occasionally the answer really is "nobody bothered", but that should be the conclusion, not the assumption.
- **Second-order effects.** If it works, what else changes? Who reacts — competitors, other teams, users, regulators — and how?
- **Incentives.** Who has to change their behavior for this to work, and what do they get out of it? Ideas that need people to act against their own interest fail quietly.
- **Reversibility.** If it is wrong, how expensive is it to undo? A cheap, reversible idea needs much less certainty than an expensive, permanent one, and the review should say so.
- **Opportunity cost.** What does this displace? The alternative is rarely "nothing"; it is the next-best use of the same time, money, or people.
- **The do-nothing option.** How bad is the status quo, really? A solution to a problem nobody feels urgently is a hard sell regardless of quality.

## Product and startup

**Questions**
- Who exactly has this problem, how often, and what do they do about it today? The current workaround — a spreadsheet, a person, ignoring it — is the real competitor.
- Is the pain strong enough that they will pay, switch, or change a habit? Interest is not demand; "that's cool" is not a purchase.
- Who pays, and is it the same person who uses it? Buyer and user mismatches kill a lot of B2B products.
- How do customers find it? A product with no plausible channel to its first hundred customers is a product nobody sees.
- Do the unit economics close? Acquisition cost against lifetime value, gross margin after hosting and support, payback period.
- What stops a larger player from copying it in a quarter once it works?
- Why now? What changed — technology, regulation, behavior — that makes this possible or necessary today?

**Usual killers**: no urgent pain; a free or "good enough" alternative; no distribution channel; acquisition cost above lifetime value; a market too small to support the founder's goals; dependency on a platform that can change its rules.

**Worth checking**: existing competitors and their pricing; how similar startups fared; market size from a credible source; platform terms the idea depends on (app store, API, marketplace policies); regulation in the target industry.

## Technical and architecture

For architecture ideas at the thinking stage, before there is a design to review: a move to microservices or events, a new datastore, a platform migration, a build-or-buy choice.

**Questions**
- What problem does this design solve that the current one doesn't, and is that problem measured or assumed? "It won't scale" needs numbers: current load, growth rate, where it breaks.
- What are the failure modes? What happens when each dependency is slow, down, or returns garbage? Where is the single point of failure?
- For reliability mechanisms (retries, timeouts, circuit breakers, queues, caches), how do they interact? Retries stacked across layers multiply. A retry schedule longer than the caller's deadline is wasted work. A retry that fires against an open breaker defeats it. A retried write that isn't idempotent, or that regenerates its idempotency key on each attempt, is a duplicate.
- What does the data model do over its whole life, not just at launch? Think about growth two or three years out, deletion requests (tenant offboarding, privacy law), backfills, and schema changes.
- What does it cost to run — infrastructure, on-call load, and the operational expertise the team needs and may not have?
- What does it do to the team? More services, more repositories, and more deploy pipelines all need owners. Distributed systems trade code complexity for operational complexity.
- How does data move, and where does consistency matter? Many designs are elegant until two services need to agree on the same record.
- What is the migration path from today, and can it be done incrementally? A design that needs a big-bang cutover carries the risk of the cutover.
- Is there a boring alternative — a bigger instance, an index, a cache, a queue — that gets most of the benefit?

**Usual killers**: solving a scale problem that doesn't exist; operational load beyond the team's capacity; distributed consistency underestimated; a migration plan that is really a rewrite; picking a technology for its novelty; vendor lock-in that wasn't priced.

**Worth checking**: the current system's actual metrics if available; vendor pricing and limits; the documented guarantees of the chosen technology (consistency model, throughput limits, quotas); known production issues with it; the existing codebase and infrastructure configuration.

## Engineering and coding

For code-level ideas: a refactor, a rewrite, adopting a library or framework, a new tool, a testing strategy, a coding convention.

**Questions**
- What is concretely wrong with the current code — defect rate, change cost, performance, onboarding time — and is it measured or felt? Discomfort with unfamiliar code is not the same as bad code.
- Rewrite or refactor? Rewrites discard the bug fixes and edge cases embedded in old code, and they usually take far longer than estimated. What makes this one different?
- How well is the area tested? Changing untested code safely needs characterization tests first; that cost belongs in the plan.
- For a library or framework: is it maintained, how many maintainers does it have, what is its release and security history, what is the license, and how hard is it to remove later? What does it pull in transitively?
- Does the team know it? A technically better tool that only one person understands is a bus-factor risk.
- Can it be done incrementally behind a seam or flag, or does it need a long-lived branch? Long branches rot.
- What is the payoff, and when does it arrive? Refactors that pay back "eventually" lose to feature work every planning cycle.

**Usual killers**: rewriting working code that only looks messy; underestimating the edge cases hidden in old code; adopting a dependency that becomes abandoned; a migration that stalls halfway, leaving two systems; no tests, so no way to prove the change preserved behavior.

**Worth checking**: read the code in question before judging it; test coverage of the affected area; the library's repository activity, issue backlog, releases, and license; known vulnerabilities; how the codebase already solves the same problem elsewhere.

## Organizational and process

For changes to how a team or company works: a reorganization, a new process, a tool rollout, a policy, a hiring plan.

**Questions**
- What problem does this solve, and who feels it? Process changes championed by someone who doesn't do the work tend to add overhead to people who do.
- Who has to change their behavior, and what do they gain? If the answer is "more reporting so leadership gets visibility", expect quiet non-compliance.
- What is the adoption path? Pilot with one team, or mandate for all? Mandates without a pilot discover the problems at full scale.
- What does it cost in time per person per week? Multiply by headcount. Small overheads across a large team are large.
- How will you know it worked? What metric moves, and what was its value before? Without a baseline, every process change looks like a success to its sponsor.
- What happens to the existing way of working? Unretired old processes run in parallel with new ones and double the load.
- Does it survive the departure of its champion?

**Usual killers**: no buy-in from the people doing the work; overhead that outweighs the benefit; no success measure, so it neither proves itself nor gets retired; a change in structure that leaves the incentives untouched; rolling out to everyone before testing on anyone.

**Worth checking**: evidence on similar changes elsewhere (case studies, research on the practice); the tool's pricing per seat; the team's actual current metrics if the user can provide them.

## Buying a tool or choosing a vendor

For buying software or services, picking a vendor or platform, or signing a contract: a SaaS tool, a cloud service, an agency, an outsourcing partner.

**Questions**
- What problem does it solve, measured how? "Better collaboration" is not a requirement; "cut release approval from three days to one" is.
- What does it really cost over three years: licenses at the expected seat count and tier, implementation, migration, training, integration upkeep, and the renewal price after the discount ends?
- How hard is it to leave? Data export (format and completeness), contract term and notice period, proprietary formats or workflows that spread through the organization.
- Who owns it after purchase: administration, access reviews, renewals, the vendor relationship? Unowned tools become shelfware or a security gap.
- Does it pass the organization's gates: security review, data residency and privacy (where the data goes, which sub-processors), single sign-on and provisioning, accessibility, procurement rules?
- How healthy is the vendor: funding or profitability, customer references at your size, roadmap dependence, what happens to your data if they're acquired or shut down?
- Is there a cheaper path: a feature of something already owned, an open-source option, a manual process that's good enough for now?

**Usual killers**: costs that balloon at renewal or with growth in seats or usage; lock-in that wasn't priced; nobody owning it; a security or privacy review that fails after the decision; buying for a hypothetical future need.

**Worth checking**: the vendor's published pricing and its terms (renewal, price increases, termination); the security and compliance documentation they publish (SOC 2, ISO 27001, data-processing terms); independent reviews and references from similar customers; the export and API documentation.

## Go-to-market, marketing, and content

For launching or positioning something, a campaign, a channel, a pricing page, a content program, or a community.

**Questions**
- Who exactly is the audience, and where are they already paying attention? A message nobody encounters is not a message.
- What should they do afterwards, and how will you know they did? Define the measurable outcome (sign-ups, qualified leads, activation), not reach or impressions.
- Why would this cut through? What do competitors already say, and what's different, believable, and provable about this?
- Is the channel matched to the buyer? Self-serve products and enterprise sales need different paths; a channel that worked elsewhere may not fit this audience.
- What does it cost per outcome, and does that fit the economics of a customer (`Product and startup`)?
- Can it be tested small first: one segment, one channel, one landing page, a pilot campaign with a fixed budget and pass line?

**Usual killers**: no defined audience or outcome; vanity metrics mistaken for traction; a message about features instead of the customer's problem; a channel too expensive per outcome for the price point; one big launch with no way to learn and adjust.

**Worth checking**: what competitors actually say (their sites, pricing pages, ads); benchmark conversion and cost figures for the channel from credible sources; the audience's own words (reviews, forums, support tickets); legal constraints on claims, testimonials, and data use (consent, privacy rules).

## Money decisions

For deciding about money directly: an investment, a pricing change, a budget request, a large purchase, a hire's cost, a loan. **This is analysis of the user's reasoning, not financial, investment, or tax advice.** For large or regulated decisions, say a qualified professional should check it (SKILL.md, "Situations that need care").

**Questions**
- What are the numbers, written down: the cost, the expected return, the timeline, and the assumptions behind each? Most money decisions fail on an assumption no one wrote down.
- What's the downside case, and can it be absorbed? Model the bad case, not just the expected one: lower demand, higher cost, slower timeline.
- What's the opportunity cost: what else could the same money or budget do?
- How reversible is it, and what does exiting cost (penalties, lock-in periods, sunk spend)?
- For a pricing change: which customers move, which leave, and what happens to revenue at realistic (not hoped-for) churn and conversion?
- For a budget request: what's the measurable outcome, by when, and what's the plan if it isn't reached?

**Usual killers**: an optimistic single-scenario model; ignoring the downside or liquidity needs; costs that recur but were treated as one-off; a return that depends on one unverified assumption; mistaking a sunk cost for a reason to spend more.

**Worth checking**: the actual terms (fees, rates, penalties, lock-ins) from the source documents; base rates for similar decisions; the tax or regulatory treatment from an official source, flagged for professional confirmation.

## Personal and career

For decisions about a job, a career change, education, a relocation, a major purchase, or starting something on the side.

**Questions**
- What is the goal underneath the decision? "Quit my job to start a company" might really be "more autonomy" or "more money" or "escape a bad manager" — each has other routes, some cheaper.
- What is the downside, and can the user absorb it? How many months of runway, who depends on their income, what happens to health insurance or visa status?
- How reversible is it? Many career moves are more reversible than they feel; some (visa status, certain credentials, burned bridges) are less.
- Can it be tested before committing — part-time, a sabbatical, a contract, a short course, a conversation with people who made the same move?
- What does the user know about the destination versus what they imagine? Talking to three people who did it is worth more than any amount of reading.
- What would they regret more in five years: trying and failing, or not trying?

**Usual killers**: runway shorter than the time to income; romanticizing the destination; solving the wrong underlying problem; an irreversible step taken where a reversible test was available.

**Worth checking**: typical salaries or rates in the target field from credible sources; realistic timelines (how long similar transitions take); requirements such as licenses, certifications, or visas. Treat the user's personal circumstances as theirs to supply — ask rather than assume.

## Bias checks

Use these on the user's framing (SKILL.md step 1), and on your own review before ranking problems (SKILL.md step 6). Name a bias only when it's actually shaping the decision, and say it about the plan, not the person.

**In the user's framing:**
- **Only one option.** "Should we do X?" without a "versus what". Add the obvious alternative and the do-nothing option.
- **Sunk cost.** Past spending argued as a reason to continue. What matters is the cost and value from here.
- **Planning fallacy.** Timelines and budgets set by how this effort should go, not by how similar efforts went. Use the reference class (universal probes).
- **Confirmation bias.** Only supporting evidence cited. Ask what evidence would change the user's mind, and whether anyone has looked for it.
- **Survivorship.** Learning only from the ones that worked ("Company X did this and succeeded"). How many tried it and failed?
- **Anchoring on the first number.** An early estimate, price, or offer treated as the baseline. Where did that number come from?
- **Commitment and identity.** An idea defended because it's been announced, or because it's tied to someone's role. Separate the idea from the person.

**In your own review:**
- **Anchoring on the first problem found.** List the candidate problems, and ask which would hurt most if true.
- **Agreeing with enthusiasm.** The user's excitement isn't evidence (SKILL.md, "Stance").
- **Performing rigor.** Inventing problems to look thorough (the swap test).
- **Recency or familiarity.** Over-weighting a failure mode because you saw it recently, or under-weighting a domain you know less well. Use the lens for the idea type.

