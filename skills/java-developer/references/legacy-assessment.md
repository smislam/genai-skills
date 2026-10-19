# Assessing a legacy codebase before migration

Read this before upgrading or migrating a legacy project. Before changing anything, establish two facts, because they decide the whole plan:
- **What do the existing tests actually verify?** They're the only evidence a migration preserved behavior, and legacy suites often verify much less than their size suggests.
- **What code is actually used?** Every dead class migrated is wasted effort and an extra place for a regression to hide.

Both results go into the migration report (`migration-report.md`). Take a code-quality snapshot at the same time (`code-quality.md`, "Assessing a codebase"), so the report can show quality before and after.

## Contents
- [1. Inventory the existing tests](#1-inventory-the-existing-tests)
- [2. Explain what each test verifies](#2-explain-what-each-test-verifies)
- [3. Find the gaps on critical paths](#3-find-the-gaps-on-critical-paths)
- [4. Identify dead and unused code](#4-identify-dead-and-unused-code)
- [5. Decide what to do with dead code](#5-decide-what-to-do-with-dead-code)

## 1. Inventory the existing tests

Run the suite as it stands, before any change: `mvn verify` or `./gradlew build`, with JaCoCo coverage enabled if the build supports it (`build-quality.md`). Record the result exactly as it is:
- tests run, passed, failed, and skipped;
- the line and branch coverage;
- how long the suite takes.

A suite that's already red is a finding, not something to fix silently. Note which tests fail on the *old* version, so their failures aren't blamed on the migration.

Then list every test class and classify it:

| Kind | How to recognize it | What it can tell you about a migration |
|---|---|---|
| Unit | No Spring context; plain JUnit with mocks or fakes | Logic still computes the same results |
| Slice | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` | One layer still behaves: web binding, queries, JSON shape |
| Full context | `@SpringBootTest` | Wiring and configuration still start and fit together |
| Integration | Testcontainers, a real database, or an embedded broker | Behavior against real infrastructure. **The most valuable kind for a Hibernate or Boot upgrade** |
| End-to-end / UI | Selenium, Playwright, HtmlUnit, REST Assured against a running app | User-visible behavior, and the only kind that covers templates |

## 2. Explain what each test verifies

For each test class, read the tests and write down, in plain language, what behavior they pin. Not their names: names lie. For example: "`OwnerControllerTests` checks that creating an owner with a missing telephone number returns the form with a field error, and that a valid owner redirects to its detail page. It doesn't check persistence, because the repository is mocked."

While reading, flag the tests that give false confidence:
- **No assertions,** or assertions only on mocks (`verify(repo).save(any())`) without checking what was saved.
- **`@Disabled` or `@Ignore` without a linked issue,** or commented-out tests.
- **Tests that assert implementation details** (private method calls, exact log messages), which a correct migration will break.
- **Tests that can't fail,** such as a `try`/`catch` that swallows the assertion error, or an expected exception that nothing throws.
- **H2 standing in for the production database,** which hides SQL and dialect changes, exactly what Hibernate upgrades alter.
- **Time, ordering, or sleep dependence:** `Thread.sleep`, wall-clock dates, `HashMap` iteration order. These go flaky on a new JDK.
- **Tests no longer run:** excluded by surefire `<excludes>`, the wrong naming pattern (`*Tests` vs `*Test`), or a missing JUnit 5 engine on a JUnit 4 suite.

Where the suite is large, summarize by package or feature, and go into detail only for the critical paths.

## 3. Find the gaps on critical paths

Map tests to what the application does. Use the entry points (controllers, listeners, scheduled jobs), and the business rules a user or the domain experts call critical: money, permissions, data that must not be lost. Mark each entry point **covered**, **weakly covered** (executed but not asserted), or **not covered**.

Line coverage says what ran, not what was checked (`testing.md`). Where the gap matters, PIT mutation testing on the critical modules shows which logic the tests would let break.

The gaps on critical paths become the migration's real first task: **characterization tests** that pin current behavior before anything changes (`refactoring.md`). Write them on the old version and run them green there, so the same tests prove the new version behaves the same.

## 4. Identify dead and unused code

Classify every candidate with its evidence. "Unused" in Java is easy to get wrong, because Spring and other frameworks call code that nothing references in the source.

**Static evidence** (no references in the code):
- **IDE inspections:** IntelliJ's "Unused declaration" inspection (also runnable headless with `inspect.sh`), and Eclipse's unused-member warnings.
- **Compiler and static analysis:** PMD (`UnusedPrivateMethod`, `UnusedPrivateField`, `UnusedLocalVariable`) and SpotBugs.
- **Unused dependencies:** `mvn dependency:analyze` reports "declared but unused" and "used but undeclared". It works from bytecode, so it can't see runtime-only dependencies: JDBC drivers, starters, logging back ends, anything loaded reflectively. Verify each one before removing it.
- **Unreferenced resources:**
  - templates no controller returns (search for each view name);
  - message keys nobody looks up;
  - static files nothing links to;
  - configuration properties nothing binds;
  - feature flags that are always off.
- **Database objects:** tables and columns no entity or query maps. Never drop them as part of a migration; flag them.

**Things that look dead but aren't.** Check each candidate against all of these before calling it dead:
- **Spring wiring:** component-scanned `@Component`, `@Service`, and `@Controller` classes; `@Bean` methods; `@Configuration` classes; and auto-configuration listed in `spring.factories` or `AutoConfiguration.imports`.
- **Framework callbacks:** `@EventListener`, `@Scheduled`, `@KafkaListener`, `@JmsListener`, `@RabbitListener`, `@PostConstruct`, `@PreDestroy`, `@ExceptionHandler`, `@InitBinder`, and `@ModelAttribute` methods.
- **Request handlers:** reached by URL, not by a Java call. Check `/actuator/mappings` or the controller annotations.
- **Persistence:** JPA entities, converters, and listeners; Spring Data repository methods, which are derived from their names; and Hibernate callbacks.
- **Serialization:** Jackson, JAXB, and Java serialization (`readObject`, `writeReplace`), where fields and setters are used reflectively.
- **Lookup by name:** `ServiceLoader` (`META-INF/services`), `Class.forName("…")` strings, XML bean definitions, JNDI, JMX MBeans, and reflection in tests.
- **Templates:** Thymeleaf, JSP, or Freemarker expressions calling getters and helper beans.
- **Callers outside the repository:** public methods of a library other projects use, `main` methods called by scripts or cron, and endpoints called by other systems.

**Runtime evidence** (whether code actually runs in production) is the strongest proof, and is often available:
- **Request counts per endpoint:** Actuator's `http.server.requests` metric by `uri`, access logs, or the API gateway's logs, over a long enough period.
- **Production coverage:** the JaCoCo agent attached to a staging or production-like environment for a representative period. Code with zero hits there is unused in practice.
- **Logs and traces** for jobs and listeners: when did each last run?

Watch for **seasonal code**: year-end processing, annual reports, and recovery paths run rarely. "No hits in two weeks" isn't "dead".

**Confidence levels.** Record one for each candidate:

| Confidence | Evidence |
|---|---|
| **Dead** | No static references, *and* none of the framework entry points above apply, *and* (where available) no runtime hits |
| **Probably dead** | No static references, but a reflective or external entry point can't be ruled out; or reachable, but no runtime hits over a meaningful period |
| **Unused feature** | Reachable and wired, but switched off (a feature flag, a disabled profile, a menu link removed) |

## 5. Decide what to do with dead code

- **Never delete code silently inside a migration commit.** A deletion hidden in a 400-file OpenRewrite diff can't be reviewed or reverted on its own.
- **Report it first** in the migration report, with the evidence and confidence for each item. Removal is the user's decision.
- **Remove "dead" code before the migration where you can,** in its own commits, with the user's approval: there's less to migrate and less to test. Run the full suite after each removal.
- **Leave "probably dead" code in place, and flag it.** Or, with approval, add a deprecation log line or metric so production use shows up before you remove it later.
- **Dead code that blocks the migration** is the strongest case for removal. An example: an unused class that's the only user of a `javax` library with no Jakarta version. Say so explicitly.
