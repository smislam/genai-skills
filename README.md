# genai-skills

A collection of [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) for everyday engineering work. Each skill gives an AI coding agent the procedure, quality bar, and reference material for one kind of task, so you don't have to re-explain it every session.

## Skills

| Skill | What it covers |
| --- | --- |
| [`architect-judge`](skills/architect-judge/SKILL.md) | A blind, independent architecture review board. It judges a design, pattern, strategy, or analysis only on what the artifact contains, scores it across Architecture Alignment, the AWS Well-Architected pillars (security included), Architecture Quality, Data Management, Governance, and Compliance, and issues a final approval status. The report includes evidence-cited findings, strengths, critical issues and gaps, and concrete remediations. |
| [`java-developer`](skills/java-developer/SKILL.md) | Production Java and Spring Boot: clean architecture, SOLID and design patterns, concurrency and virtual threads, JVM performance and GC tuning, security hardening, JUnit 5 testing, and migrating legacy Java (8/11/17) to modern Java (21/25) and Spring Boot 4. |
| [`second-opinion`](skills/second-opinion/SKILL.md) | A blunt, fair second opinion on an idea, plan, or decision, covering products and startups, code changes, org and process changes, and career moves. It makes the best case first, maps what the idea depends on, checks facts instead of guessing, and ends with a clear call and the cheapest tests to settle what's still unknown. |

## Installation

Clone the repository:

```bash
git clone https://github.com/smislam/genai-skills.git
```

Then copy the skills you want into Claude Code.

**For all your projects:**

```bash
cp -r genai-skills/skills/java-developer ~/.claude/skills/
```

**For one project (commit it to share with your team):**

```bash
mkdir -p .claude/skills
cp -r /path/to/genai-skills/skills/java-developer .claude/skills/
```

To get updates with `git pull`, symlink the skill directory instead of copying it.

## Usage

You don't need to invoke a skill. Once it's installed, Claude Code loads it automatically when your request matches what it covers, such as "add a test for this service" or "upgrade us to Spring Boot 4".

## License

[MIT](LICENSE) © 2026 Shafiq Islam
