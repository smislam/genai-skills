# Build and quality gates

Read this when setting up a project, adding static analysis, or wiring CI.

The snippets here are the parts people get wrong — the ones that are invisible until a build actually runs. They were verified by building a real project with every gate active (`mvn verify` and `gradle build`, both green), so the wiring is correct even though the **version numbers are not pinned here on purpose**: they drift within months, and a stale pinned version that fails the build is worse than no starting point. Resolve current versions as described in [Version management](#version-management), then wire them up as below.

## Contents
- [Why gates instead of guidelines](#why-gates-instead-of-guidelines)
- [Adopting gates on an existing codebase](#adopting-gates-on-an-existing-codebase)
- [What each tool catches](#what-each-tool-catches)
- [Compiler settings](#compiler-settings)
- [Error Prone and NullAway](#error-prone-and-nullaway)
- [Test layout and speed](#test-layout-and-speed)
- [Coverage](#coverage)
- [Formatting](#formatting)
- [Dependency hygiene](#dependency-hygiene)
- [Maven vs Gradle](#maven-vs-gradle)
- [CI pipeline shape](#ci-pipeline-shape)
- [Version management](#version-management)

## Why gates instead of guidelines

A convention that lives in a wiki decays; a convention the build enforces does not. The gate also removes a whole category of review comment — nobody should spend review attention on formatting, unused imports, or a missing `hashCode` when a tool finds those for free. That attention is better spent on correctness and design.

The corollary is that **a gate must be fast and must not produce false alarms**, or people will route around it. A build that takes fifteen minutes gets skipped locally; a check that flags fifty non-issues gets suppressed wholesale. Tune for signal.

## Adopting gates on an existing codebase

The failure mode is predictable: enable everything at full strictness, get 900 violations, and the gate is deleted by Friday. Instead:

1. **Add the tool in report-only mode** (`failOnViolation=false`, `-Werror` off) and look at what it finds.
2. **Baseline the existing violations.** SpotBugs and PMD take exclusion files; Spotless can be applied in one mechanical commit; Error Prone severities can be downgraded per-check. Record the baseline as "known debt", not as "acceptable".
3. **Make the gate fail for new code only** — most teams do this by fixing one module or package at a time and narrowing the exclusions as they go.
4. **Fix the baseline incrementally**, highest-severity first, and shrink the exclusion file in small reviewable commits.
5. **Then turn on failure.**

Do formatting (Spotless) first and in its own commit: it is purely mechanical, it makes every later diff smaller, and it has zero behavioural risk. Never mix a format-everything commit with a logic change — the real change becomes invisible.

## What each tool catches

They overlap a little but each finds things the others miss, which is why the set is worth the build time.

| Tool | Finds | Runs |
|---|---|---|
| **javac `-Xlint:all -Werror`** | Unchecked generics, deprecation, fall-through, missing overrides | Every compile; free |
| **Error Prone** | Real bug patterns at compile time: `equals` on incompatible types, format-string mismatches, ignored return values, misused `Optional`, mutable statics | Every compile; small cost |
| **NullAway** | Null dereferences, via Error Prone, with near-zero false positives on annotated packages | Every compile |
| **SpotBugs + FindSecBugs** | Bytecode-level bug patterns and ~130 security detectors: injection, weak crypto, path traversal, unsafe deserialization | `verify`/`check` |
| **PMD** | Code smells, complexity, multithreading and performance rules, plus copy-paste detection (CPD) | `verify`/`check` |
| **ArchUnit** | Architecture violations: layer breaches, framework imports in the domain, field injection, package cycles (`testing.md`) | As a unit test |
| **JaCoCo** | What the tests never executed | `verify`/`check` |
| **Spotless** | Formatting and import order — and fixes them | `validate`, plus `apply` locally |
| **dependency-check / OSS Index** | Dependencies with known CVEs | CI, scheduled |
| **CycloneDX** | SBOM for the shipped artifact | `package` |
| **Maven Enforcer / Gradle locking** | Version ranges, convergence conflicts, duplicate classes | `validate` |
| **PIT** | Tests that execute code without verifying it (`testing.md`) | On demand, per module |

ArchUnit deserves special mention because it is the only one that enforces *your* design rather than generic rules. Add it on day one of a new project — retrofitting it onto a drifted codebase means a hundred violations and a disabled test.

## Compiler settings

```xml
<release>25</release>                     <!-- not source/target: release also checks the API surface -->
<compilerArgs>
  <arg>-Xlint:all,-serial,-processing</arg>
  <arg>-Werror</arg>                      <!-- warnings are bugs you have not met yet -->
  <arg>-parameters</arg>                  <!-- keeps parameter names for Spring/Jackson binding -->
</compilerArgs>
```

Use **`release`**, not `source`+`target`: `release` also verifies that you are not calling APIs absent from the target version, which `target` alone will happily let through and fail at runtime on an older JVM.

`-Werror` is worth the friction. The warnings javac emits — unchecked casts, deprecation, missing `serialVersionUID`, fall-through — are a list of latent bugs. Suppress individual categories deliberately (`-serial` and `-processing` are usually noise) rather than turning the flag off.

`-parameters` matters in Spring: without it, constructor parameter name binding for `@ConfigurationProperties` and some Jackson paths falls back to reflection guesswork.

## Error Prone and NullAway

Error Prone hooks into javac and finds bug patterns with a very low false-positive rate — it is the highest-value static analysis available for Java, and it runs for free on every compile.

NullAway builds on it to do practical null checking: you annotate packages as `@NullMarked` (or list them in `NullAway:AnnotatedPackages`), mark the exceptions `@Nullable`, and it flags dereferences that can be null. Unlike full null-checking systems it is fast and quiet enough to run in CI as an error.

### The wiring, and the four things that break it

Every item below was found by running a build, not by reading config. Each one is build-fatal or CI-breaking.

**1. Error Prone needs javac internals exported on JDK 16+.** For Maven, the flags go in `.mvn/jvm.config` — one per line, and **they cannot go in a pom comment**, because an XML comment may not contain a double hyphen (a POM with `--add-exports` in a comment is unparseable, full stop):

```
--add-exports jdk.compiler/com.sun.tools.javac.api=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.file=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.main=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.model=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.parser=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.processing=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED
--add-exports jdk.compiler/com.sun.tools.javac.util=ALL-UNNAMED
--add-opens jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED
--add-opens jdk.compiler/com.sun.tools.javac.comp=ALL-UNNAMED
```

For **Gradle**, add this import at the very top of `build.gradle.kts` or the `options.errorprone { }` block fails to resolve and the build will not even configure:

```kotlin
import net.ltgt.gradle.errorprone.errorprone
```

**2. Exclude test sources from NullAway.** Tests legitimately pass `null` to assert a constructor rejects it; without this the gate fails on exactly the test you want to keep.

```xml
<!-- maven-compiler-plugin: annotationProcessorPaths get error_prone_core + nullaway -->
<compilerArgs>
  <arg>-Xlint:all,-serial,-processing</arg>
  <arg>-Werror</arg>
  <arg>-parameters</arg>
  <arg>-XDcompilePolicy=simple</arg>
  <arg>--should-stop=ifError=FLOW</arg>
  <arg>-Xplugin:ErrorProne -XepOpt:NullAway:AnnotatedPackages=com.acme -Xep:NullAway:ERROR -XepExcludedPaths:.*/(src/test/java|generated-sources)/.*</arg>
</compilerArgs>
```

```kotlin
options.errorprone {
    disableWarningsInGeneratedCode = true
    error("NullAway")
    option("NullAway:AnnotatedPackages", "com.acme")
    excludedPaths = ".*/(src/test/java|generated)/.*"
}
```

**3. Pin Spotless line endings** — `<lineEndings>UNIX</lineEndings>` in Maven, `lineEndings = com.diffplug.spotless.LineEnding.UNIX` in Gradle. The default derives them from the platform, so a repo formatted on Linux fails the check on Windows and vice versa. If you also enable `kotlinGradle { ktlint() }`, expect it to reformat your own build script: trailing commas and wrapped arguments.

**4. Testcontainers 2.x renamed every module** to a `testcontainers-` prefix (`testcontainers-postgresql`, not `postgresql`), so a 2.x BOM will not manage the 1.x coordinates and you get "version is missing" errors. Spring Boot's BOM manages the 1.x line — either stay on 1.x or rename every artifact id.

Finally, introduce NullAway **package by package** on an existing codebase. `NullAway:AnnotatedPackages` scoped to one package lets you convert gradually instead of facing every null at once.

Spring Framework 7 and Boot 4 adopt **JSpecify** annotations, which align with this tooling — on the default Boot 4 baseline, use `org.jspecify.annotations.Nullable` for consistency.

## Test layout and speed

Separate fast tests from slow ones so the fast suite can run constantly:

- **Maven:** Surefire runs `*Test` in `test`; Failsafe runs `*IT` in `verify` (bind its `integration-test` and `verify` goals). Tag slow tests (`@Tag("slow")`) and exclude them from Surefire with `<excludedGroups>slow</excludedGroups>`.
- **Gradle:** a separate `integrationTest` JVM test suite, wired into `check` but ordered after `test`:

```kotlin
testing {
    suites {
        val integrationTest by registering(JvmTestSuite::class) {
            useJUnitJupiter()
            dependencies { implementation(project()) /* + assertj, testcontainers */ }
            targets.all { testTask.configure { shouldRunAfter(tasks.test) } }
        }
    }
}
tasks.check { dependsOn(tasks.named("integrationTest"), tasks.jacocoTestCoverageVerification) }
```

Why this matters: the value of a test suite is proportional to how often it runs. A suite that takes 90 seconds gets run before every commit; one that takes 20 minutes gets run by CI only, which means defects are found an hour later by someone else.

Enable JUnit parallel execution at class level (`parallel.mode.classes.default=concurrent`, methods same-thread) as a safe default — it usually halves wall-clock time, and it will surface tests that share state, which is a finding, not a problem.

## Coverage

Set a floor, exclude the code where coverage is meaningless, and understand what the number does not tell you.

```xml
<!-- jacoco-maven-plugin: three executions — prepare-agent (initialize),
     report (verify), check (verify). The check rule shape: -->
<rules>
  <rule>
    <element>BUNDLE</element>
    <limits>
      <limit><counter>LINE</counter><value>COVEREDRATIO</value><minimum>0.80</minimum></limit>
      <limit><counter>BRANCH</counter><value>COVEREDRATIO</value><minimum>0.70</minimum></limit>
    </limits>
  </rule>
</rules>
<excludes>
  <exclude>**/*Application.class</exclude>
  <exclude>**/config/**</exclude>
  <exclude>**/dto/**</exclude>
  <exclude>**/generated/**</exclude>
</excludes>
```

```kotlin
// Gradle: exclusions must be applied to classDirectories, not to the rule.
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit { counter = "LINE";   value = "COVEREDRATIO"; minimum = "0.80".toBigDecimal() }
            limit { counter = "BRANCH"; value = "COVEREDRATIO"; minimum = "0.70".toBigDecimal() }
        }
    }
    classDirectories.setFrom(
        files(
            classDirectories.files.map {
                fileTree(it) { exclude("**/config/**", "**/dto/**", "**/*Application.class", "**/generated/**") }
            },
        ),
    )
}
```

The floor exists to stop coverage silently collapsing, not to prove quality — a suite with no assertions can hit 100%. Branch coverage is the more informative number. If you want to know whether the tests actually *verify* behaviour, run mutation testing (PIT) on the modules with real logic; a high line coverage with a low mutation score is a clear signal the tests execute without checking. Never write a test purely to move the number (`testing.md`).

## Formatting

Pick one formatter, apply it to everything, and never discuss it again. Spotless with `palantirJavaFormat` or `googleJavaFormat` is the common choice; which one matters far less than having one.

Run `spotless:apply` / `spotlessApply` locally — ideally from a pre-commit hook or IDE save action — and `check` in CI so a misformatted file cannot merge. Import order should put `java`, `javax`/`jakarta`, third-party, then static imports last.

## Dependency hygiene

- **Manage versions centrally** — the Spring Boot BOM, or a `dependencyManagement` block / Gradle platform. Never let two modules disagree about a version.
- **No version ranges.** They make builds non-reproducible and open a supply-chain path.
- **Enforce convergence** (`dependencyConvergence`, `requireUpperBoundDeps`) so a transitive downgrade cannot sneak in a vulnerable or incompatible version.
- **Correct scopes:** `provided`/`compileOnly` for things the runtime supplies, `test` for test-only, `runtimeOnly` for drivers and bindings. A test library leaking into `implementation` ships Mockito to production.
- **`optional`/`api` vs `implementation`** in Gradle: use `api` only for types that appear in your public signatures, otherwise `implementation` so consumers do not inherit your internals.
- **Automate updates** with Dependabot or Renovate, grouped and on a schedule. Small, frequent upgrades are vastly cheaper than an annual big-bang (`migration.md`).
- **Publish an SBOM** and scan dependencies in CI (`security.md`).

## Maven vs Gradle

Both are fine; the project's existing choice almost always wins. If you are genuinely choosing:

- **Maven** — declarative, predictable, trivially readable by anyone, excellent for standard applications. The XML is verbose; that is the whole downside. Maven 4 is in release-candidate stage, so 3.9/3.10 remains the production choice.
- **Gradle (Kotlin DSL)** — faster incremental builds, configuration cache, far better for multi-module and custom build logic, with real IDE completion in the Kotlin DSL. The cost is that a build script is a program, and programs rot. Keep logic in convention plugins, not in ad-hoc script blocks.

Either way: use the **wrapper** (`mvnw`/`gradlew`), commit it, and pin a **toolchain** so the JDK used to compile does not depend on what happens to be on the machine.

## CI pipeline shape

Order stages so the fastest feedback comes first and the expensive stages only run on code that already passed:

1. **Compile + format check** — seconds. Catches the trivial.
2. **Unit tests + Error Prone/NullAway** — a minute or two.
3. **Static analysis** (SpotBugs, PMD) + **ArchUnit** — runs in `verify`/`check`.
4. **Integration tests** (Testcontainers) — needs Docker; the slowest routine stage.
5. **Coverage verification.**
6. **Dependency vulnerability scan + SBOM** — on main, release builds, and a nightly schedule. It is too slow and too network-dependent for every push.
7. **Build and publish the artifact/image.**

Practical details that keep this usable: cache the dependency directory (`~/.m2`, Gradle cache) or CI time triples; make the build deterministic so a rerun gives the same result; publish test and coverage reports as artifacts so a failure can be diagnosed without re-running; and fail fast — a broken format check should not wait for integration tests.

Run the same commands locally that CI runs (`mvn verify`, `./gradlew build`). A pipeline with steps that cannot be reproduced locally turns every failure into a guessing game.

## Version management

Every version in the templates was current when they were written, and **they will be stale.** Treat them as a starting point:

```bash
mvn versions:display-dependency-updates versions:display-plugin-updates
./gradlew dependencyUpdates
```

When a version matters to the answer you are giving — "does this project support virtual threads?", "is this dependency vulnerable?" — read it from the build file rather than recalling it. Stating a version you have not checked is the easiest way to be confidently wrong, and the user has no way to tell the difference until it breaks.
