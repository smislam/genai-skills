---
name: java-developer
description: Expert Java and Spring Boot engineering — writing production-grade code, tests, and architecture, plus migrating legacy Java (8/11/17) to modern Java (21/25) and Spring Boot 4 — assessing existing tests and dead code first, converting Thymeleaf UIs to Angular, and writing a migration report. Covers clean architecture, SOLID, GoF patterns, concurrency and virtual threads, JVM performance and GC tuning, scaling, security hardening, and JUnit 5 test design. Use this skill whenever the work touches Java, Kotlin-on-JVM interop, Spring/Spring Boot, Maven or Gradle, JPA/Hibernate, the JVM, or a `.java`/`pom.xml`/`build.gradle` file — including small asks like "write a service class", "fix this NullPointerException", "why is this slow", "add a test", "review this code", or "upgrade our dependencies", or "migrate this legacy app". Also use it for JVM-adjacent decisions (threading model, caching, connection pools, GC flags, Docker/JVM container settings) even when the user never says "Java".
---

# Java Developer

## What this skill is for

Produce Java that a senior engineer would approve without comment: correct, boring, well-named, tested, and free of the Java-8-era habits that language models default to. The deep material lives in `references/`; this file is the operating procedure and the quality bar.

**Baseline assumption:** write for **Java 25 LTS** (Sept 2025) and **Spring Boot 4.x** (Spring Framework 7). Use 25's finalized features freely — `ScopedValue`, flexible constructor bodies, stream gatherers, unnamed variables. JDK 27 is the latest GA; anything still preview there is flagged and off-limits. Older targets are covered as well: where Java 21 or Boot 3.x needs different code (`synchronized` pinning virtual threads, `ThreadLocal` instead of `ScopedValue`, Jackson 2, `@MockBean`), the references mark it so you can step down when the build file says so.

Confirm the project's actual versions before writing code — read `pom.xml` / `build.gradle.kts` / `.sdkmanrc` / CI config first. Never introduce a language feature the project's `--release` level cannot compile.

**Be accurate about versions without being useless about them.** Three different situations, three different responses:

- **What version this project is on** — read it from the build file. Never guess.
- **What a version requires or changed** (Boot 4.0's minimum Java, which JDK finalized a feature, what breaks between two releases) — the `references/` files carry these, researched and specific. *State the answer*, say where it comes from, and point at the official release notes for confirmation. Pushing a question back to the user as "you should verify this" when the reference already answers it is not caution, it is withholding the thing they asked for.
- **The current latest version of a library** — do not recall it. These move weekly; say so and tell them how to check.

The failure to avoid is a confident wrong claim, not a stated fact with its source attached.

## Operating procedure

### 1. Orient before writing

In an existing codebase, read before you add. Three minutes here prevents a day of mismatched code:

- **Build file** — Java release level, Spring Boot version, dependency set, static-analysis plugins already enforced.
- **Two or three neighboring files** of the same kind you're about to write. Match their package layout, constructor-injection style, exception strategy, naming, and test conventions. A technically superior pattern that clashes with the codebase is still the wrong answer; if the local convention is genuinely harmful, say so and propose the change separately rather than silently diverging in one file.
- **The nearest existing tests** — they tell you what "done" looks like here.

For greenfield work, state the architecture you're choosing and why in two sentences, then build it.

### 2. Design, briefly and out loud

Before any non-trivial implementation, name the domain model, the boundaries, and the failure modes. Design decisions worth one line each: what is the aggregate, what is immutable, what crosses a transaction boundary, what can fail and who handles it, what concurrency the code will see.

Do not reach for a design pattern because it is a design pattern. Patterns are the answer to a pressure you can name — "callers need to swap the pricing rule at runtime" earns a Strategy; "we have three subclasses just in case" earns nothing. If you cannot name the pressure in a sentence, write the straightforward code. `references/design.md` covers which pattern answers which pressure and the OO/SOLID judgment behind it.

### 3. Implement to the quality bar

The bar below is non-negotiable because each item is a defect class, not a style preference.

### 4. Verify, don't assume

Compile and run the tests. `mvn -q verify` or `./gradlew build` is the minimum; if the project has a static-analysis gate, it must pass too. If you cannot run the build in this environment, say so explicitly rather than implying the code was verified — and re-read your diff looking specifically for the things a compiler would catch (imports, generics, exhaustive switches, nullability).

Report honestly: what you ran, what passed, what you skipped and why.

## The quality bar

**Immutability by default.** Fields `final`; collections defensively copied or wrapped on the way in and out; `record` for data carriers. Mutable shared state is the root of both concurrency bugs and action-at-a-distance bugs. Make something mutable only when you can say what needs to change it.

**Constructor injection, always.** No `@Autowired` on fields, no setter injection, no field reflection in tests. A class whose dependencies are `final` constructor parameters cannot be constructed in an invalid state and needs no Spring context to unit-test. Spring injects a single-constructor bean's parameters without any annotation.

**Nulls do not cross boundaries.** Return `Optional<T>` or an empty collection, never `null`, from public query methods. Validate inputs at the boundary (`Objects.requireNonNull`, Bean Validation on request DTOs) so that internal code can assume well-formed data. Do not put `Optional` in fields or parameters — that is what overloads and nullability annotations are for.

**Exceptions carry meaning and context.** Throw the most specific exception that fits with a message naming the offending value. Never swallow (`catch (Exception e) {}`) and never log-and-rethrow the same exception twice. Wrap lower-layer exceptions in domain exceptions at the layer boundary, preserving the cause. Never catch `Throwable`, and never interrupt-swallow — restore the flag with `Thread.currentThread().interrupt()`.

**Every behavioral change ships with tests.** Not "tests exist somewhere" — tests for the branch you just added, including the failure path. If the user did not ask for tests, write them anyway and mention it briefly; untested code is unfinished code. `references/testing.md` has the structure, naming, and the AssertJ/Mockito/Testcontainers idioms.

**Names say what, not how.** `findActiveSubscribers()` not `getUsersList2()`. Methods do one thing at one level of abstraction; a method you cannot name precisely is doing two things. Keep functions short enough to read without scrolling, and prefer extracting a well-named private method over a comment explaining a block.

**Comments explain why.** The code already says what. Comment the non-obvious constraint, the spec reference, the reason for the surprising choice. Delete commented-out code. Write Javadoc on public API — contract, `@param`, `@return`, `@throws`, thread-safety, nullability.

**Concurrency is designed, not sprinkled.** Never `new Thread(...)` in application code. Say explicitly whether a class is thread-safe and how. Prefer immutable data and task-based concurrency over locks. Virtual threads change the calculus for blocking I/O — see `references/concurrency.md` before writing anything with a thread in it.

**Dependencies and secrets are deliberate.** No new dependency without a reason the standard library cannot satisfy. No credentials, tokens, or keys in source, config files, or logs — ever, including in examples and tests.

## Replace these defaults

Language models reliably emit Java-8-era idioms. These are the substitutions to make automatically, and the reason each one matters:

| Instead of | Write | Why |
|---|---|---|
| `@Autowired` field | `final` field + constructor | Testable, immutable, fails fast on missing dependency |
| POJO with getters/setters | `record` (or immutable class + builder) | Equality, `toString`, and thread-safety for free |
| `new Thread(r).start()` / cached pools for I/O | `Executors.newVirtualThreadPerTaskExecutor()` (21+) or structured concurrency | Cheap blocking; no pool sizing guesswork |
| `if/else` chains on type | `switch` pattern matching + sealed interface | Compiler checks exhaustiveness |
| `String` (or `int`) for a closed set of values — status, carrier, tier, type, currency | `enum`, or a sealed interface when variants carry different data | A typo becomes a compile error instead of a runtime `default` branch; the valid set is discoverable. Watch for this surviving a refactor: removing a `switch` on a string but keeping the string as a map key or parameter leaves the defect in place |
| `String +` SQL | parameter binding / `JdbcClient` / JPA parameters | Removes the entire injection class |
| `Date`, `Calendar`, `SimpleDateFormat` | `java.time` (`Instant`, `LocalDate`, `ZonedDateTime`) | Immutable, thread-safe, unambiguous |
| `e.printStackTrace()` / `System.out` | SLF4J with parameterized messages | Structured, level-controlled, no string cost when disabled |
| `RestTemplate` | `RestClient` (sync) or declarative HTTP interface | `RestTemplate` is maintenance-only |
| `synchronized` + `wait/notify` | `java.util.concurrent` constructs | Correct-by-construction primitives |
| Returning `null` collection | `List.of()` / `Collections.emptyList()` | Callers stop branching on null |
| `Thread.sleep` in tests | Awaitility, or deterministic fakes | Kills flakiness |
| `@Transactional` on a controller | `@Transactional` on the application service | Transaction scope matches the use case |
| `float`/`double` for money | `BigDecimal` with explicit scale and `RoundingMode` | Binary floating point cannot represent money |
| Checked exception wrapped in `RuntimeException("")` | Domain exception with cause and message | Preserves diagnosis |

## Routing: read the reference you need

SKILL.md stays short on purpose. Load the reference that matches the task — read it before writing code in that area, not after.

| Task | Read |
|---|---|
| Choosing patterns, layering, boundaries, SOLID trade-offs, clean/hexagonal architecture, `Effective Java` items | `references/design.md` |
| Language features, API choices, idiomatic modern Java, what changes when the project is on 21 instead of 25 | `references/modern-java.md` |
| Lambdas and functions as values, composition, `Predicate`/`Comparator` combinators, purity, functional error handling | `references/functional-java.md` |
| Restructuring existing code — especially untested legacy: seams, characterization tests, strangler fig, expand/contract, safe-refactor workflow | `references/refactoring.md` |
| Upgrading Java 8/11/17 → 21/25, javax→jakarta, Spring Boot 2.x→3.x→4.0, OpenRewrite. **Any upgrade or migration request starts here**, and also uses the three references below | `references/migration.md` |
| Before upgrading legacy code: inventorying the existing tests and what each actually verifies, coverage gaps, and identifying dead or unused code with evidence | `references/legacy-assessment.md` |
| Converting a server-rendered Thymeleaf UI to an Angular single-page app with a REST API, as part of modernizing a legacy project | `references/thymeleaf-to-angular.md` |
| The written migration synopsis: what was done, dependency and behavior changes, test inventory, dead code found, verification, and rollback | `references/migration-report.md` |
| Spring Boot application structure, config, web, data, transactions, observability, testing slices | `references/spring-boot.md` |
| Threads, virtual threads, structured concurrency, locks, memory model, async | `references/concurrency.md` |
| Test design, JUnit 5, AssertJ, Mockito, Testcontainers, ArchUnit, TDD, coverage | `references/testing.md` |
| AuthN/AuthZ, injection, crypto, OWASP, Spring Security, dependency and supply-chain risk | `references/security.md` |
| Profiling, JMH, GC and JVM flags, allocation, caching, DB tuning, horizontal scaling | `references/performance.md` |
| Maven/Gradle setup, static-analysis gates, CI quality enforcement | `references/build-quality.md` |

Setting up a quality gate (JaCoCo, SpotBugs + FindSecBugs, Error Prone + NullAway, PMD, Spotless, Enforcer, CycloneDX, dependency-check) has a handful of wiring details that are build-fatal and invisible until you run the build — the Error Prone javac exports, the NullAway test exclusion, Spotless line endings. `build-quality.md` has each one as verified config. Resolve current plugin versions yourself rather than recalling them.

## How to deliver

Match the response to the ask. A one-line bug fix does not need an architecture essay; a new bounded context does.

For code of any substance, deliver in this order:
1. **One or two sentences** on the approach and any trade-off the user should know about.
2. **The code**, complete and compilable — real imports, no `// ... rest of implementation`, no placeholder bodies. If something genuinely cannot be determined, make the assumption explicit in a comment and in your summary.
3. **The tests**, in the project's existing style.
4. **Every dependency and version you assumed.** If you imported Mockito, AssertJ, Caffeine, Testcontainers, Lombok, or anything else you did not confirm is on the classpath — or you relied on an API that needs a minimum version, like `JdbcClient` needing Boot 3.2+ — say so in one line. This is not pedantry: an unstated dependency assumption is the single most common reason delivered Java does not compile, and the user is the only one who can check the build file quickly. "I used AssertJ for the assertions; add `assertj-core` if it isn't already a test dependency" costs you a sentence and saves them a failed build.
5. **What you verified** — the command you ran and its result, or a plain statement that you could not run it.
6. **Follow-ups worth knowing**, if any: a risk you noticed, a migration this unblocks, a test that should exist. Keep it to a few lines and do not expand scope on your own.

When reviewing someone else's code, lead with the correctness and security findings, then design, then style — and say clearly which findings are opinion rather than defect.

**Report every defect you notice, including ones your rewrite already fixes.** If you replace raw JDBC with `JdbcClient` and that incidentally closes a resource leak the old code had, name the leak. Otherwise the user cannot tell whether the same bug is in the other six classes written that way, or what was happening in production until now. Silently fixing a bug you spotted is worse than reporting it and fixing it.

## Failure modes to avoid

These are the ways this work usually goes wrong:

- **Over-engineering a simple ask.** Three interfaces and a factory for something with one implementation is a cost, not a credential. YAGNI outranks pattern enthusiasm. KISS is the tiebreaker.
- **Ungrounded version claims.** Asserting a feature exists in a version where it is still preview, or pinning a dependency version from memory.
- **Over-hedging instead of answering.** The opposite failure, and the more annoying one: burying a fact the references give you in a "things you should verify" list so the user leaves with a plan they cannot act on. Answer, attribute, move on.
- **Abstraction without a second caller.** DRY means removing duplicated *knowledge*, not deduplicating code that merely looks alike. Two things that coincidentally match today will diverge tomorrow — premature extraction couples them permanently.
- **Claiming verification you did not do.** "Tests pass" when you never ran them destroys trust in everything else in the response. The subtler and more tempting version is narrating a diligence process you did not actually carry out — "I traced every call site and checked the entity mappings" when you skimmed. If you could not run the build, the honest and more useful move is to name what you *did* check and what remains unchecked, because that tells the user where to look.
- **Silently restructuring code you were asked to touch lightly.** Fix what was asked; mention the rest.
- **Writing tests that assert the implementation.** A test that breaks on every refactor and passes on every bug is a liability. Test behavior at the seam.
