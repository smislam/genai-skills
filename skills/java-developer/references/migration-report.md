# The migration report

Every upgrade or migration ends with a written report, kept in the repository as `docs/migration/<YYYY-MM-DD>-<from>-to-<to>.md`, or as the project's existing equivalent. It's the record of what changed and why, the evidence that behavior was preserved, and the list of what's left. A reviewer, an auditor, or the next engineer should understand the migration from this document without reading the diff.

Update it as you go, not at the end. For a multi-step migration, add a section per completed step, so the report is accurate at every release.

## Template

```markdown
# Migration: <project> — <from> → <to>

## Synopsis
<Five lines at most: what was migrated, the final state (all tests green? released?), the most important behavior change, the biggest remaining risk, and what's still open.>

## Scope and versions

| Component | Before | After |
|---|---|---|
| Java (release level / runtime) | 8 / 8 | 21 / 21 |
| Spring Boot | 2.7.18 | 3.5.x |
| Build tool and key plugins | Maven 3.6, surefire 2.22 | Maven 3.9, surefire 3.x |
| UI | Thymeleaf 3.0 | Angular <major> (or "unchanged") |
| Container base image / CI JDK | … | … |

Out of scope: <what was deliberately not done, and why>.

## Assessment (before any change)

**Tests:** <n> test classes / <n> tests; <passed/failed/skipped> on the old version; line <x>% / branch <y>% coverage.

| Test class (or area) | Kind | What it actually verifies | Concerns |
|---|---|---|---|
| OwnerControllerTests | Slice (@WebMvcTest) | Validation errors and redirects for owner create/update; persistence mocked | Doesn't check what's saved |

Critical paths with no or weak coverage: <list>. Characterization tests added for them: <list, with locations>.

**Dead and unused code:**

| Item | Kind | Evidence | Confidence | Action |
|---|---|---|---|---|
| `com.acme.legacy.FaxExporter` | Class | No references; no Spring wiring; zero hits in staging JaCoCo over 30 days | Dead | Removed in commit abc123 (approved) |
| `/reports/annual` | Endpoint | Wired; zero requests in 60 days of access logs; runs yearly? | Probably dead (seasonal?) | Flagged, kept |
| `commons-beanutils` | Dependency | `dependency:analyze` unused; verified no reflective use | Dead | Removed |

## Code quality
<The quality snapshot from code-quality.md, with Before and After columns: complexity, god classes, duplication, package cycles, coverage, high-severity static-analysis findings, the hotspots, and Clean Code observations. "After" is measured when the migration is done.>

## What was done
<One entry per step or commit, in order. Steps:>
1. <Build toolchain upgraded: Maven 3.9.x, surefire 3.x, Lombok 1.18.x. Commit …>
2. <OpenRewrite `UpgradeToJava21` applied; diff reviewed; commit …>
3. <javax → jakarta via OpenRewrite `…`; 212 files; commit …>
4. <Manual changes: …, with the reason each was needed>

## Dependency changes

| Dependency | Before | After | Why / notes |
|---|---|---|---|
| hibernate-core | 5.6 | 6.6 | Required by Boot 3; id-generator default changed (verified) |
| some-old-lib | 1.2 | removed | No Jakarta version; replaced by … |

## Behavior changes and risks
<Every user-, client-, or operator-visible difference, and how it was verified or mitigated. Examples: trailing-slash URLs no longer match; JSON dates now ISO-8601; changed SQL for a query; new JVM flags; Actuator paths.>

## UI migration (Thymeleaf → Angular)
<If in scope: the page map from thymeleaf-to-angular.md, with each page's status (migrated / parity tests passing / old template removed), plus the Thymeleaf artifacts removed at the end.>

| Old template / route | New Angular route / component | API endpoints | Parity tests | Status |
|---|---|---|---|---|

## Verification
<Commands run and their results: `mvn verify` (n tests, all green), integration tests (Testcontainers, database version), parity E2E tests, load test before/after (p95 latency, GC), canary or staging deploy. Say honestly what wasn't run.>

| Check | Before | After |
|---|---|---|
| Tests (total / failed / skipped) | 412 / 3 / 7 | 455 / 0 / 2 |
| Line / branch coverage | 41% / 30% | 58% / 44% |

## Defects found
<Bugs noticed along the way, including ones the migration fixed incidentally and ones characterization tests pinned, each with its status.>

## Not done and follow-ups
<Deprecations left, "probably dead" code awaiting a decision, modernization steps deferred, `--add-opens` flags still needed (each with an owner and a removal plan).>

## Rollback
<How to return to the previous version: the release or tag to redeploy, data or schema changes that make rollback harder (and how they're handled), and the config to restore.>
```

## Rules for the report

- **Evidence, not claims.** "Tests pass" names the command and the count. "Dead" names the evidence (`legacy-assessment.md`).
- **Report every behavior change,** including ones you believe are improvements. Clients may depend on the old behavior.
- **Report defects you found, even if fixed.** Silently fixed bugs leave the user unable to find the same bug elsewhere (SKILL.md, "Report every defect you notice").
- **Be honest about what wasn't verified:** no load test, no production-like database, no canary. Say so, and say what it risks.
- **Keep it current** through each step, so a partial migration still has an accurate record.
