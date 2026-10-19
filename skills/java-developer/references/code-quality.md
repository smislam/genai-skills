# Code review and quality assessment

Read this when asked to review code, to judge the quality of a codebase, or to report on quality during a migration. The standard is `clean-code.md` and the quality bar in `SKILL.md`; the tools are in `build-quality.md`. This file is the procedure, the thresholds, and the output.

## Contents
- [Reviewing a change](#reviewing-a-change)
- [Metrics and thresholds](#metrics-and-thresholds)
- [Assessing a codebase](#assessing-a-codebase)
- [SonarQube and SonarCloud](#sonarqube-and-sonarcloud)

## Reviewing a change

**Order of attention.** Spend review effort where defects are most costly:
1. **Correctness:** does it do what it claims, including edge cases, nulls, empty collections, boundaries, time zones, and concurrency?
2. **Security:** input validation, injection, authorization, secrets, logging of sensitive data (`security.md`).
3. **Tests:** do they verify the behavior, including the failure paths, and would they fail if the code were wrong (`testing.md`)?
4. **Design:** responsibilities, boundaries, coupling, and whether the change fits the existing architecture (`design.md`).
5. **Clean code:** names, function size and abstraction level, error handling, comments (`clean-code.md`).
6. **Style:** only what the formatter and linters don't already enforce. If you find yourself commenting on formatting, the gate is missing (`build-quality.md`).

**Read it in this order:**
- the description and the linked issue (what is it *supposed* to do?);
- the tests (do they state that behavior?);
- the production code;
- the build and configuration changes.

Run it, or at least run the tests, when you can. Say so when you couldn't.

**Each finding:**
- **Location:** `file:line`.
- **Severity:**
  - **blocker:** a defect, security issue, or data risk;
  - **should fix:** a maintainability or design problem that will cost later;
  - **nit:** optional polish.
- **Fact or opinion:** say which.
- **What's wrong, and why it matters,** in a sentence. "This name is unclear" isn't enough; say what a reader would wrongly assume.
- **A concrete suggestion,** as code where it helps.

**Review output:**

```markdown
**Verdict:** approve | approve with changes | request changes — <one sentence why>

**Blockers**
1. `OrderService.java:88` — <defect, why it matters> → <fix>

**Should fix**
1. …

**Nits** (optional)
- …

**Good** — <specific things done well, briefly; reviewers who only criticize get ignored>

**Not checked** — <what you couldn't verify: didn't run tests, no DB, etc.>
```

**Rules:**
- **Review the change, not the author;** phrase findings about the code.
- **Don't expand scope.** Problems in untouched code go under "found but out of scope", not as blockers (`refactoring.md`).
- **One concern per comment,** so each can be resolved.
- **Approve when the remaining issues are nits.** Perfect isn't the bar; better than before, and safe, is.

## Metrics and thresholds

Metrics point at where to look; they don't replace reading the code. Treat a threshold as "this needs a reason", not "this is wrong". Measure with the tools the project already has (PMD, JaCoCo, ArchUnit, Sonar), and report the numbers in assessments and migration reports.

| Metric | Measures | Investigate when | Tool |
|---|---|---|---|
| Cognitive complexity per method | How hard the control flow is to follow (nesting, breaks in flow) | Over 15 | PMD `CognitiveComplexity`; Sonar's cognitive complexity rule |
| Cyclomatic complexity per method | The number of independent paths, which is the minimum number of tests for full branch coverage | Over 10 | PMD `CyclomaticComplexity` |
| Method length (non-comment statements) | Doing more than one thing | Over about 30 statements | PMD `NcssCount` |
| Parameters per method | A missing concept | More than 3 (`clean-code.md`, "Functions") | PMD `ExcessiveParameterList` (set its minimum to 4) |
| Class size and responsibilities | Too many reasons to change | Over about 500 lines or 20 public methods, or PMD flags a god class | PMD `GodClass`, `TooManyMethods`, `NcssCount` (class level) |
| Coupling between classes | How many types a class depends on | Unusually high for the layer | PMD `CouplingBetweenObjects` |
| Duplication | Copy-pasted logic | Over 3% of lines, or any duplicated block of business logic | PMD CPD; Sonar duplications |
| Package cycles and layer violations | Architecture drift | Any | ArchUnit (`testing.md`) |
| Line and branch coverage | What the tests execute | Below the gate on new code (`build-quality.md`) | JaCoCo |
| Mutation score | What the tests actually *verify* | Low on modules with business logic | PIT |
| Static-analysis findings | Known bug patterns | Any high-severity finding | Error Prone, NullAway, SpotBugs |

**How to read them:**
- A high-complexity method in a parser or a rules engine may be the clearest form; a high-complexity controller method almost never is.
- Trends matter more than snapshots. Gate *new* code on the thresholds, and fix old code as you touch it (`build-quality.md`, "Adopting gates on an existing codebase"; the Boy Scout Rule in `clean-code.md`).
- Exclude generated code, DTOs and records, and configuration classes from the numbers, so they reflect logic.

## Assessing a codebase

For an inherited or legacy codebase, or as part of the migration report (`migration-report.md`, "Code quality"), produce a quality snapshot:

1. **Measure.** Run the existing build and analysis tools. Where the project has none, run PMD (with the metrics rules above), CPD, and JaCoCo without changing the build permanently: a one-off command, or a temporary profile you don't commit, unless the user wants the gate added. Record the tool versions.
2. **Summarize the numbers:**
   - lines of code (production and test);
   - methods over each threshold (count, and the worst ten);
   - classes flagged as god classes;
   - duplication percentage;
   - package cycles;
   - coverage (line and branch);
   - high-severity static-analysis findings.
3. **Read the hotspots.** The worst methods and classes, and the files that change most often (`git log --format= --name-only | sort | uniq -c | sort -rn | head`). Complexity in frequently changed code costs the most; complexity in stable code that nobody touches costs little.
4. **Judge against `clean-code.md`:** naming, function design, error handling, test quality, and boundaries. Give one or two concrete examples each, with file:line.
5. **Recommend,** ranked by risk and payoff:
   - the quality gate to add, with a baseline;
   - the hotspots to refactor first, under characterization tests if needed (`refactoring.md`);
   - the conventions to enforce.

**Snapshot format** (also the "Code quality" section of a migration report, with a before and an after column):

```markdown
## Code quality

| Measure | Before | After |
|---|---|---|
| Production / test LOC | 48,200 / 9,100 | 44,900 / 12,600 |
| Methods with cognitive complexity > 15 | 87 | 61 |
| Classes flagged as god classes | 12 | 9 |
| Duplicated lines | 6.8% | 4.1% |
| Package cycles | 5 | 2 |
| Line / branch coverage | 41% / 30% | 58% / 44% |
| High-severity static-analysis findings | 23 | 0 |

**Hotspots:** <the worst 5–10 methods or classes, with file, metric, change frequency, and a one-line note>
**Clean Code observations:** <naming, functions, error handling, tests: one or two examples each, with file:line>
**Recommendations:** <ranked; what to gate, what to refactor first, what to leave>
```

Don't refactor for quality inside a migration's version-upgrade commits. Quality improvements are separate, reviewable commits (`migration.md`, "Modernizing code after the upgrade").

## SonarQube and SonarCloud

If the organization runs SonarQube or SonarCloud, use its quality gate as the shared definition of "done" rather than inventing a parallel one:
- Run the analysis in CI (the Sonar Maven or Gradle plugin), with JaCoCo's XML report passed in for coverage.
- Gate on **new code**, the "clean as you code" approach Sonar's default gate takes, so legacy debt doesn't block delivery but doesn't grow either.
- Map Sonar's measures to the table above when reporting: cognitive complexity, duplication, coverage, and its reliability, security, and maintainability ratings.
- Don't suppress issues to pass the gate. Mark genuine false positives as such in Sonar, with a reason, so the decision is reviewable.

Where there's no Sonar, the build-level gate in `build-quality.md` provides the same protection with the tools already in the build.
