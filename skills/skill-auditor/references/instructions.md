# Instruction quality

Contents: what belongs in a skill · skill, CLAUDE.md, or hook · sizing and loading · writing the instructions · asking the user · plans and approval · verification · degrees of freedom · common faults

## What belongs in a skill

A skill is for knowledge and procedure the model cannot get from the repository or already know: how this team cuts a release, what the incident runbook says, which checks a review must make, what a good report looks like. Everything else is cost. Every line is read in every run that loads the skill.

For each paragraph, ask: would a capable model do this without being told? If yes, cut it. "Write clean code", "be careful", "consider edge cases", and "you are a senior engineer" all fail that test.

Keep:

- decisions the model would get wrong without guidance (a threshold, a house rule, a non-obvious order of steps)
- facts it cannot discover (an internal URL, a naming convention, a regulation)
- the quality bar: what a finished result looks like and how to tell
- known failure modes, stated as the mistake and the correction

## Skill, CLAUDE.md, or hook

Choose by how the instruction must be followed.

| Need | Right home |
|---|---|
| A guideline that applies to nearly every task in a project | `CLAUDE.md` (short) |
| A procedure or body of knowledge needed only sometimes | A skill, so it costs nothing until used |
| A rule that cannot have exceptions ("never edit migrations", "always run the formatter") | A hook or deny rule. The harness runs these every time; text instructions are followed almost always, not always. |
| An action with side effects that only a person should start | A skill with `disable-model-invocation: true` |

A finding: a skill that states a must-never rule only in prose when it could ship a hook. The other direction is also a finding: a hook that enforces what is only a preference, which will fire when it should not.

If a skill keeps escalating emphasis on a line ("IMPORTANT", "NEVER", "ALWAYS"), the line either needs a hook or needs rewording. Shouted rules also get over-applied.

## Sizing and loading

- `SKILL.md` carries the procedure and the decisions. Under about 500 lines, usually much less.
- Detail loaded only when needed goes in `references/`, each file named for what it holds, each pointed to from `SKILL.md` with a sentence on when to read it.
- References link one level deep from `SKILL.md`. A reference that points to another that points to a third is read partially or not at all.
- A reference over 300 lines starts with a contents list.
- After context compaction only the start of each skill is kept, so the most important rules go near the top, not in the last section.
- No reference is orphaned, and no `SKILL.md` section duplicates a reference.

Estimate cost as characters divided by four. Report the tokens loaded on every trigger (`SKILL.md`) separately from the tokens loaded on demand (references).

## Writing the instructions

- **Imperative and specific.** "Run `npm test` and show the last 20 lines" beats "make sure the tests pass".
- **Order follows the work.** Steps in the order they happen, each with its output.
- **Explain the why for rules that look arbitrary**, in one clause. A model that knows the reason applies it correctly at the edges.
- **One term per concept.** If the skill says "finding" in one place and "issue" and "defect" in others, the model will treat them as different things.
- **Say what to do, not only what to avoid.** A list of prohibitions leaves the model guessing the replacement.
- **Defaults over menus.** Name the default and the one exception, not five equal options.
- **Decide the format once.** If the output has a template, put it in a reference and say when to use it.
- **No stale facts.** Versions, prices, and dates are named with where to check them, or removed.
- **Keep the voice neutral.** Persona text ("you are a world-class...") adds tokens and no capability.

## Asking the user

A skill that interviews the user should do it well:

- Ask only when the answer would change the outcome, and only up front. A question whose answer is in the repository, or which has a sensible default, is noise.
- Batch the questions: up to four at a time with selectable answers, the best guess first, instead of a stream of single questions. When the host cannot show selectable questions, fall back to at most two plain ones.
- Skip the interview entirely for a trivial request.
- State every assumption that was not asked, and ask the user to correct them.

Findings: questions asked one at a time; questions the model could answer by reading a file; an interview before a trivial task; no fallback when the question tool is missing.

## Plans and approval

Work that touches many files, or cannot be undone, should show a written plan and wait for approval before changing anything. Check that the skill:

- separates reading and planning from editing,
- names which steps are reversible and which are not,
- stops for approval before the irreversible ones (deletes, pushes, deploys, outward messages),
- says what to do when the user does not approve.

A skill that edits first and explains afterward is a finding. So is one that asks for approval on every trivial step, which trains the user to click through.

## Verification

The strongest lever on quality is giving the model a way to check its own work. Look for it, and require it to produce evidence:

- a command and its output (tests, build, typecheck, linter, a script's exit code),
- a before-and-after comparison,
- a second pass in a fresh context (a subagent that has not seen the first pass's conclusions) for the claims that matter most,
- a stop condition: the list of things that must be true before the skill says it is done.

Findings:

- no verification step at all (QLT03),
- "verify the result" with no method, so nothing can fail,
- a check the same pass both defines and grades,
- a claim of success that does not require showing the output,
- a verification that cannot fail (it only confirms).

The best skills let a hook enforce the check, so that "done" cannot be declared until it passes. If the skill ships one, review it with `hooks.md`.

## Degrees of freedom

Match how tightly the instruction is written to how fragile the task is.

- **Fragile and exact** (a migration, a release, a file format): give the exact command or template, and say "do not change the order".
- **Judgment with a clear bar** (a review, an analysis): give the criteria, the output shape, and the evidence required, and leave the path open.
- **Open-ended** (brainstorming, drafting): give the goal and the constraint, little else.

A fragile task described loosely is a finding, and so is an open-ended task wrapped in rigid steps.

## Common faults

- A description that promises more than the body does.
- Background the model already knows (what a SQL injection is, how REST works).
- Two skills' worth of content in one folder.
- Steps that depend on tools the skill never checks for.
- Examples that are the only valid shape, so the model copies them literally.
- A checklist with no way to tell an item is done.
- Instructions addressed to a human reader ("you may want to consider") rather than to the agent.
- Output requirements stated in three places that disagree.
- No behavior defined for the failure path: what to do when a tool is missing, a file is absent, the user says no.
