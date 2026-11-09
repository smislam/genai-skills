# Triggering: will the skill load when it should?

Contents: what the model sees · what a good description does · the trigger test · overlap between skills · invocation control

## What the model sees

For a skill the model can start on its own, the name and description sit in context in every session. The body loads only after the model decides the description matches. So the description is the entire trigger: a skill with an excellent body and a vague description never runs, and a skill with a broad description runs when nobody wanted it.

The listing truncates long text (description plus `when_to_use` is capped at 1,536 characters), so the first sentences carry the weight. Put the "use when" part early, not last.

## What a good description does

A description answers three questions in the first 600 characters or so:

1. **What does it do?** One concrete sentence with a verb and an object, not "helps with code".
2. **When should it run?** Situations and the phrases a person would actually type. "Use when the user asks to audit dependencies, find leaked secrets, or review a repository for security."
3. **When should it not run?** One line that names the neighbor it must not steal from. "Not for reviewing a single pull request."

Signs of a weak description:

- It names a topic ("Java development") instead of tasks ("write, review, and migrate Java").
- It lists features the user will never type.
- It is so broad that it fits half of all requests ("helps with coding tasks").
- It is so narrow that natural phrasing misses it (only one exact command).
- It opens with "I can" or "You can". Descriptions are read as a list; third person keeps the list consistent.
- It hides the trigger at the end, past the point the listing cuts off.

## The trigger test

Judge the description alone, as the model would, without looking at the body.

1. Write **six prompts that should trigger the skill**: two plain, two oblique (the user never names the topic), two terse or sloppy.
2. Write **six prompts that should not**: three near-misses that share vocabulary but need something else, three clearly unrelated.
3. For each prompt, read only the description and say "load" or "skip", with a one-line reason.
4. Count the misses in both directions. One miss in either list is a finding. Two or more is a rewrite.

If subagents are available, make the test blind: give a fresh subagent only the skill's name and description (plus the descriptions of its sibling skills, if any) and the twelve prompts, and ask it to choose which skill, if any, to load for each. Compare its answers with your expectations. Without subagents, do the test yourself and label it "self-judged" in the report, because you know what the skill is for and will read the description charitably.

Report the table, not just the count: prompt, expected, got, why.

## Overlap between skills

When the target holds more than one skill, or the user names the skills installed alongside it, list for each pair the prompts that both descriptions would match. Overlap is a finding when:

- two skills would both load for a common request and give conflicting instructions, or
- one skill's description is a superset of another's, so the narrower one never gets picked.

The fix is almost always to add "not for X" to one description or to narrow the broader one.

## Invocation control

Match the invocation setting to the consequences:

| Skill does | Setting |
|---|---|
| Reads, explains, reviews, produces a report | Default. The model may start it. |
| Commits, pushes, deploys, deletes, sends messages, spends money | `disable-model-invocation: true`, so only the user starts it |
| Background knowledge the model should apply but the user would never type | `user-invocable: false` |

A skill that changes outside state and can start itself is a finding (AGY06), whatever its description says.

Other fields to check when present:

- `allowed-tools` pre-approves tools for one turn. Broad grants such as bare `Bash` remove the prompt for every command. Scope them.
- `paths` limits automatic activation to matching files. A wrong glob makes the skill never trigger.
- `context: fork` runs the skill in a subagent with no conversation history, so the body must carry everything it needs.
- `model` and `effort` override the session. Check they are intended and available to the people who will install the skill.
