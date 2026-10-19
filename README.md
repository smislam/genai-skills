# genai-skills

A collection of [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills) for everyday engineering work. Each skill gives an AI coding agent the procedure, quality bar, and reference material for one kind of task, so you don't have to re-explain it every session.

## Skills

| Skill | What it covers |
| --- | --- |
| [`appsec-auditor`](skills/appsec-auditor/SKILL.md) | A full-repository application security audit done by the AI, with nothing to install and deterministic coverage. Scripts build a fixed checklist (rule hits, entry points, secrets in git history, dependencies checked against live OSV.dev and CISA KEV data, through corporate proxies), the AI proves or dismisses every item, and a hook blocks completion until all are decided. It also shows how findings chain into real exploits. Output is a Markdown report, SARIF 2.1.0, optional GitLab reports, and proposed fixes. For reviewing just a branch's pending changes, use Claude Code's built-in `/security-review`. Needs Node.js 18+; see its [README](skills/appsec-auditor/README.md). |
| [`architect-judge`](skills/architect-judge/SKILL.md) | A blind, independent architecture review board for architectures that already exist. It judges a design, pattern, strategy, or analysis only on what the artifact contains, scores it across Architecture Alignment, a full question-level AWS Well-Architected review (all six pillars, security included, plus matching lenses), Architecture Quality, Data Management, Governance, and Compliance, and issues a final approval status. The report includes evidence-cited findings, strengths, critical issues and gaps, and concrete remediations. |
| [`java-developer`](skills/java-developer/SKILL.md) | Production Java and Spring Boot: clean architecture, SOLID and design patterns, concurrency and virtual threads, JVM performance and GC tuning, security hardening, JUnit 5 testing, and migrating legacy Java (8/11/17) to modern Java (21/25) and Spring Boot 4. Migrations start by inventorying what the existing tests actually verify and identifying dead code, convert Thymeleaf UIs to Angular page by page, and end with a written migration report. |
| [`sounding-board`](skills/sounding-board/SKILL.md) | A blunt, fair sounding board for an idea, plan, or decision at any stage, including work not yet started: products and startups, early architecture ideas, code changes, org and process changes, and career moves. It makes the best case first, maps what the idea depends on, checks facts instead of guessing, and ends with a clear call, backing sound ideas as plainly as it rejects broken ones, plus the cheapest tests to settle what's still unknown. |

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

Copy a skill's whole folder, not just `SKILL.md`. `appsec-auditor` also ships scripts and optional guardrail hooks; see its [README](skills/appsec-auditor/README.md).

## Usage

You don't need to invoke a skill. Once it's installed, Claude Code loads it automatically when your request matches what it covers, such as "add a test for this service" or "upgrade us to Spring Boot 4".

## License

[MIT](LICENSE) © 2026 Shafiq Islam
