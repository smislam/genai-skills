# Migration and upgrades

Read this when moving a codebase to a newer Java or Spring Boot version, or when asked whether an upgrade is feasible. The goal is a sequence of small, verifiable steps — never one heroic branch.

## Contents
- [Strategy](#strategy)
- [The procedure](#the-procedure)
- [Tooling](#tooling)
- [Java 8 → 11](#java-8--11)
- [Java 11 → 17](#java-11--17)
- [Java 17 → 21](#java-17--21)
- [Java 21 → 25](#java-21--25)
- [Spring Boot 2.x → 3.x](#spring-boot-2x--3x)
- [Spring Boot 3.x → 4.x](#spring-boot-3x--4x)
- [Modernising code after the upgrade](#modernising-code-after-the-upgrade)
- [Common blockers](#common-blockers)
- [Checklist](#checklist)

## Strategy

Three principles decide whether an upgrade succeeds.

**Go one step at a time, in order.** 8 → 11 → 17 → 21, and 2.7 → 3.0 → 3.5 → 4.x. Each hop has a known, documented set of breaking changes and a matching OpenRewrite recipe; jumping two hops means debugging an undifferentiated pile of failures with no way to attribute them.

**Separate "it compiles and runs on the new version" from "it uses the new version's features."** These are different projects with different risk profiles. Get to green on the new runtime with minimal code change first, release that, then modernise idioms incrementally. Mixing them means a huge diff where a behavioural regression cannot be isolated.

**Dependencies before code.** Most upgrade pain is third-party: a library that does not support the new bytecode level, or that needs the `jakarta` namespace. Audit dependency compatibility *first* — a single unmaintained library can decide the whole plan, and finding that out on day one is much cheaper than on day twenty.

Worth saying plainly to a user weighing the cost: the strongest argument for upgrading is usually **support lifecycle, not features**. JDK 17's premier support window has closed, and running on an unsupported runtime means no security patches. That reframes the upgrade from optional modernisation to maintenance.

## The procedure

1. **Inventory.** Current Java and framework versions, every direct dependency and its latest version supporting the target, build plugin versions, and anything using JDK internals, `javax.*`, or bytecode manipulation (agents, Lombok, Mockito inline, ByteBuddy, ASM, cglib — these are version-sensitive and break loudly).
2. **Baseline the tests.** You cannot upgrade safely without a suite you trust. If coverage on critical paths is thin, add tests *before* the upgrade — they are the only thing that will tell you the migration preserved behaviour. This is often the real first task.
3. **Upgrade the build toolchain** — Maven/Gradle, compiler, surefire/failsafe, and the agent-dependent plugins — while still on the old Java. Old plugin versions fail on new JDKs in confusing ways, so eliminate that variable first.
4. **Run the old build on the new JDK** without changing `release`. This surfaces agent, reflection, and plugin problems in isolation.
5. **Raise `release`/`sourceCompatibility`** to the target and fix compilation.
6. **Update dependencies** to versions that support the target, ideally through a BOM.
7. **Apply automated migration** (OpenRewrite) for the mechanical parts, review the diff carefully, commit it separately from hand-written changes.
8. **Fix tests, then run the application.** Many breakages are runtime-only: reflection, serialization, classpath scanning, resource loading.
9. **Verify beyond the unit suite** — integration tests, a load test (GC and thread behaviour change between versions), and a canary deploy.
10. **Then modernise** idioms, in separate reviewable commits.

Keep each step a commit that compiles and passes tests. When something breaks three weeks later, `git bisect` has to be able to help.

## Tooling

- **OpenRewrite** is the highest-leverage tool for this work: deterministic, type-aware refactoring recipes for Java version migrations, the `javax` → `jakarta` rename, Spring Boot upgrades, test framework migrations, and static-analysis fixes. It does the mechanical 80% correctly and leaves the judgement calls to you.

```bash
# Java version migration
mvn org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.activeRecipes=org.openrewrite.java.migrate.UpgradeToJava21 \
  -Drewrite.exportDatatables=true

# Spring Boot 3.x
mvn org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.activeRecipes=org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_5
```

Always run it on a clean branch, read the entire diff, and keep it in its own commit. Treat the output as a very good first draft, not as correct by construction — recipe names and availability also change, so check the catalogue for the current recipe id rather than trusting a remembered one.

- **`jdeps --jdk-internals`** finds dependencies on JDK internal APIs that strong encapsulation will reject.
- **`jdeprscan --release <N>`** finds use of deprecated and removed APIs.
- **`mvn versions:display-dependency-updates`** / Gradle `dependencyUpdates`, plus Dependabot or Renovate to keep the problem from recurring.
- **`mvn dependency:tree`** to resolve conflicts and find who drags in an incompatible transitive version.
- **`spring-boot-properties-migrator`** — add it as a temporary runtime dependency during a Boot upgrade and it logs every renamed or removed property you are still using, then remove it.
- **Maven Enforcer / Gradle dependency locking** to prevent silent version drift after the work is done.

## Java 8 → 11

The largest single hop, because the module system landed in between.

- **Removed Java EE and CORBA modules.** `java.xml.bind` (JAXB), `java.activation`, `java.xml.ws`, `java.transaction`, `java.corba`, and friends are gone from the JDK. Add the standalone artifacts explicitly (`jakarta.xml.bind-api` plus an implementation, `jakarta.activation`). This is the most common 8 → 11 compile failure.
- **Nashorn (JavaScript engine) deprecated** — removed later. Any server-side scripting needs a replacement.
- **Illegal reflective access warnings.** Code reaching into JDK internals still works on 11 but warns; it will *fail* on 17. Fix it now rather than deferring, and use `jdeps --jdk-internals` to find it.
- **`sun.misc.Unsafe`, `sun.security.*`, internal classes** — find alternatives. Usually the real fix is upgrading the library that uses them.
- **Removed GC flags and options.** Many `-XX` flags were removed or renamed; an unrecognised flag prevents the JVM from starting. Audit your launch command, not just your code.
- **Version string format changed** (`9`, `11` not `1.8`). Code parsing `java.version` by prefix breaks.
- **Build config:** replace `source`/`target` with **`release`**, which also checks you are not using APIs absent from the target.
- **Do not adopt JPMS** as part of this migration. The classpath continues to work; modularising at the same time multiplies the risk for little benefit in an application (`modern-java.md`).

## Java 11 → 17

Mostly mechanical, with one hard edge.

- **Strong encapsulation is now enforced** (JEP 403). Reflective access to JDK internals that merely warned on 11 now throws. Fix the cause where you can; `--add-opens`/`--add-exports` are an escape hatch to unblock a release, not a solution — record each one with a reason and a removal plan, and remember they must be set for tests too (surefire `argLine`).
- **Removals:** Nashorn, RMI activation, the experimental AOT/JIT compiler (JEP 410), and CMS garbage collector (removed in 14 — if your flags mention `UseConcMarkSweepGC`, the JVM will not start). Move to G1 or ZGC.
- **Security Manager deprecated for removal** (JEP 411). Start planning the replacement now (`security.md`).
- **Default charset is not yet UTF-8** on 17 (that lands in 18), so explicit charsets remain essential — and are good practice regardless.
- **Agent and bytecode library versions matter:** Lombok, Mockito, ByteBuddy, ASM, cglib, JaCoCo, and anything doing instrumentation must be on a version that knows the new class-file format. Upgrade these before raising `release`.
- Records, sealed classes, text blocks, and switch expressions all become available — but defer adopting them to the modernisation phase.

## Java 17 → 21

The easiest recent hop, and the one with the biggest payoff.

- Few breaking changes for ordinary application code. The usual work is dependency and plugin version bumps.
- **Finalization is deprecated for removal** (JEP 421) and disabled by default in later versions — any `finalize()` method must become try-with-resources or a `Cleaner`.
- **Thread class changes:** `Thread.stop`, `suspend`, and `resume` are removed or permanently throw.
- **Virtual threads arrive** (`concurrency.md`). Enabling them is a separate, deliberate step after the upgrade, and needs an audit for `synchronized` around blocking I/O (which pins carriers on 21–23) and for `ThreadLocal`-heavy libraries.
- **Pattern matching for switch and record patterns go final**, which is where most of the code-quality upgrade comes from afterwards.
- **Generational ZGC** becomes available (`-XX:+UseZGC`) if you have latency requirements.
- Re-run your load tests: GC defaults and JIT behaviour shift between major versions, usually favourably, occasionally not.

## Java 21 → 25

Both are LTS, and the hop is small for application code — but the platform is actively closing off unsafe access, which is what tends to break.

- **The Security Manager is permanently disabled** (JEP 486, JDK 24): `System.setSecurityManager` throws, and `-Djava.security.manager` stops the JVM from starting. Anything depending on it must be redesigned around OS/container sandboxing, serialization filters, and JAXP secure processing.
- **Non-generational ZGC was removed** (JDK 24). If your flags contain `-XX:-ZGenerational`, remove it.
- **JNI use now warns by default** (JEP 472) and can be denied; `sun.misc.Unsafe` memory-access methods are deprecated for removal. Grant `--enable-native-access` to the specific module that needs it rather than `ALL-UNNAMED`, and plan a move to the Foreign Function & Memory API.
- **`synchronized` no longer pins virtual threads** (JEP 491, JDK 24) — if you worked around pinning with `ReentrantLock`, the workaround is now unnecessary, though harmless.
- **Gains worth taking:** `ScopedValue` final, generational Shenandoah, compact object headers (`-XX:+UseCompactObjectHeaders`), AOT caching for startup, and flexible constructor bodies.
- Check that your build toolchain, IDE, and any instrumentation agents support the target before starting; agents are the usual blocker.

## Spring Boot 2.x → 3.x

A genuinely large migration. Budget for it properly and do `2.7 → 3.0` as its own step.

- **Java 17 is the minimum.** Do the Java upgrade first, separately, and release it.
- **`javax.*` → `jakarta.*`.** Jakarta EE 9+ renamed the namespace: `javax.persistence`, `javax.servlet`, `javax.validation`, `javax.annotation` all move. This touches nearly every file, which is exactly why you should let OpenRewrite do it in one reviewable commit. Any dependency still shipping `javax.*` must be upgraded or replaced — this is the hard dependency gate.
- **Spring Security 6:** the lambda DSL becomes mandatory (`.and()` chaining is gone), `WebSecurityConfigurerAdapter` is removed in favour of a `SecurityFilterChain` bean, `antMatchers` becomes `requestMatchers`, and authorities handling changed (`ROLE_` prefixes and the `SCOPE_` convention for JWTs). Re-test authorisation thoroughly — this is the step most likely to silently open or close access.
- **Hibernate 6.** Different SQL generation, stricter type handling, changed id-generator defaults for `GenerationType.AUTO`, and `@Type` annotations replaced. Expect query behaviour to need verification against the real database, not H2.
- **Trailing-slash matching is no longer automatic** — `/invoices/` stops matching `/invoices`. A silent 404 for existing clients; decide whether to restore it at the gateway or fix the clients.
- **Auto-configuration registration moved** from `META-INF/spring.factories` to `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Affects your own starters.
- **Actuator changes:** endpoint paths and sanitisation defaults changed; `/actuator/health` detail exposure is more restricted (a good thing — verify your probes still work).
- **Observability replaced the old metrics/tracing stack** — Micrometer Observation and Micrometer Tracing instead of Spring Cloud Sleuth, which is discontinued.
- **Property renames** — add `spring-boot-properties-migrator` temporarily and clear every warning it logs.
- **Many config and API deprecations were removed outright.** Upgrade to the latest 2.7.x first, fix every deprecation warning there, and only then go to 3.0. This single ordering decision removes most of the pain.

## Spring Boot 3.x → 4.x

Structural rather than language-level. Notably, **the Java minimum did not move — 4.0 still requires only Java 17** — so do not assume a 4.x codebase is on 21.

- **Module and package reorganisation.** Boot ships as many smaller modules under `org.springframework.boot.<module>` packages, with technology-specific starters replacing some broader ones. This is the bulk of the diff: imports and dependency coordinates.
- **Jackson 3:** group id moves from `com.fasterxml.jackson` to `tools.jackson`, with class renames. Custom serializers, modules, and `ObjectMapper` setup all need review.
- **Baselines:** Spring Framework 7, Spring Security 7, Spring Data 4. Upgrade the portfolio together, and check the Spring Cloud compatibility matrix — the matching release train usually trails Boot's GA.
- **JSpecify nullability annotations** replace `org.springframework.lang` equivalents. Expect new warnings; most are real latent bugs.
- **`@MockBean`/`@SpyBean` are removed** → `@MockitoBean`/`@MockitoSpyBean`. These exist from Boot 3.4, so migrate your tests *before* the upgrade to shrink the diff.
- **Removals:** the Undertow starter (Servlet 6.1 baseline), Spock test integration, some Spring Session auto-configurations, and the classic uber-jar loader.
- **Property renames**, including `spring.dao.exceptiontranslation.enabled` → `spring.persistence.exceptiontranslation.enabled` and `management.tracing.enabled` → `management.tracing.export.enabled`.
- The items above are specific enough to plan against — use them. Read the official 4.0 migration guide for the exhaustive list, and double-check an individual property or class name at the moment you write it into code, since those shift across point releases. "Confirm against the guide" is a footnote to an answer, not a substitute for giving one.

## Modernising code after the upgrade

Once you are green on the new version, improve idioms in small, separately reviewable commits — one pattern per commit, so a regression is attributable:

1. **`Date`/`Calendar`/`SimpleDateFormat` → `java.time`.** Highest bug-reduction value: the old types are mutable and thread-unsafe, and shared `SimpleDateFormat` instances corrupt data under load.
2. **DTOs and value objects → records.** Mechanical, large, and immediately reduces `equals`/`hashCode` defects.
3. **Field injection → constructor injection.** Enables real unit tests, which unlocks everything else.
4. **`instanceof` ladders and type codes → sealed interfaces with exhaustive switch.** Converts runtime surprises into compile errors.
5. **Thread pools for blocking I/O → virtual threads** (`concurrency.md`), after auditing for pinning and `ThreadLocal` use.
6. **`RestTemplate` → `RestClient` or declarative HTTP interfaces.**
7. **String-concatenated SQL → bound parameters.** Do this one as a security fix, not a style fix.
8. **Add the quality gate** (`build-quality.md`) — with a baseline so existing violations do not block the build, and a rule that new code must be clean. A gate that fails on day one gets disabled on day two.

Let test coverage lead: refactor the areas you have tests for, and add tests before refactoring the areas you do not. `refactoring.md` has the mechanics — characterisation tests for code with no coverage, how to find a seam, and the expand/migrate/contract sequence for changes too big for one commit.

## Common blockers

| Blocker | Why | Resolution |
|---|---|---|
| Unmaintained library with `javax.*` | Cannot coexist with Jakarta EE 9+ | Find a maintained fork, replace it, or shim — decide before committing to a date |
| Agent/bytecode library too old | Does not understand the new class-file version | Upgrade Lombok, Mockito, ByteBuddy, JaCoCo, cglib *first* |
| Reflective access to JDK internals | Strongly encapsulated from 17 | Fix the code; `--add-opens` only as a temporary unblock, with an owner |
| Removed JVM flags (e.g. CMS) | JVM refuses to start on an unknown flag | Audit the launch command; move to G1/ZGC |
| `SecurityManager` dependency | Permanently disabled from 24 | Redesign around container/OS sandboxing |
| H2 in tests, Postgres in prod | Hibernate 6 SQL changes do not show up | Move integration tests to Testcontainers before upgrading |
| Thin test coverage | No way to detect behavioural regression | Add tests on critical paths first — this is the migration's real first task |
| Hand-written `spring.factories` | No longer read in Boot 3 | Move to `AutoConfiguration.imports` |
| Big-bang branch | Weeks of unmergeable work, unattributable failures | One version hop per branch, each releasable |
