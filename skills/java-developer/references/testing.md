# Testing

Read this before writing or reviewing tests. The goal is tests that catch regressions, survive refactoring, and fail with a message that tells you what broke.

## Contents
- [What makes a test worth having](#what-makes-a-test-worth-having)
- [The test pyramid, concretely](#the-test-pyramid-concretely)
- [Structure and naming](#structure-and-naming)
- [JUnit 5 essentials](#junit-5-essentials)
- [AssertJ](#assertj)
- [Mockito: and when not to mock](#mockito-and-when-not-to-mock)
- [Spring Boot test slices](#spring-boot-test-slices)
- [Testcontainers](#testcontainers)
- [Testing concurrency](#testing-concurrency)
- [Testing time and randomness](#testing-time-and-randomness)
- [ArchUnit: enforcing architecture](#archunit-enforcing-architecture)
- [Property-based and mutation testing](#property-based-and-mutation-testing)
- [Coverage: what the number means](#coverage-what-the-number-means)
- [TDD when it pays](#tdd-when-it-pays)
- [Flakiness](#flakiness)

## What makes a test worth having

A good test has four properties, and they trade off against each other:

1. **It fails when behavior breaks** (protection against regression).
2. **It does not fail when behavior is preserved** (resistance to refactoring).
3. **It tells you what is wrong from the failure message alone** (fast feedback).
4. **It is cheap to maintain.**

Property 2 is the one most often sacrificed, and it is the one that decides whether a suite is an asset or a tax. A test that asserts *how* the code works — which collaborator was called in which order, with mocks for every class — breaks on every refactor and passes when the logic is wrong. Test at the **seam**: public behavior, observable outcome.

The practical rule: assert on **return values and state changes you could observe from outside the unit**. Reach for `verify()` only when the interaction *is* the behavior (an email was sent, a message was published, nothing was charged twice).

## The test pyramid, concretely

| Level | What it covers | Speed | How many |
|---|---|---|---|
| **Unit** | A class or small cluster, no framework, no I/O | < 10 ms | The large majority |
| **Integration (slice)** | One technical concern wired for real — persistence, web layer, serialization | 100 ms–1 s | Dozens |
| **Integration (system)** | Real DB/broker via Testcontainers, app context up | 1–30 s | Tens, on the critical paths |
| **End-to-end** | Whole deployed system | Minutes | A handful of smoke journeys |

Push tests down the pyramid wherever you can without losing the thing you are actually trying to verify. Domain logic belongs in unit tests — if you need a Spring context to test a pricing rule, the rule is in the wrong place, and *that* is the finding.

Push them up when the risk is in the integration: a JPA mapping, a native query, a transaction boundary, a serialization contract. Those are untestable in a unit test and routinely broken in production. A mocked repository proves nothing about whether your query compiles.

## Structure and naming

Three parts, visually separated. Blank lines are enough; comments are optional:

```java
@Test
void rejectsTransferWhenBalanceInsufficient() {
    // given
    var account = Account.opened(AccountId.of("A-1"), Money.usd("100.00"));

    // when
    var result = account.withdraw(Money.usd("150.00"));

    // then
    assertThat(result).isInstanceOf(Withdrawal.Rejected.class);
    assertThat(account.balance()).isEqualTo(Money.usd("100.00"));
}
```

Name the test after the **behavior and the condition**, not the method. `rejectsTransferWhenBalanceInsufficient` tells you what broke from the CI log alone; `testWithdraw2` requires opening the file. Use `@DisplayName` for prose when the name gets unwieldy, and `@Nested` classes to group by scenario:

```java
@Nested
class WhenAccountIsFrozen {
    @Test void rejectsWithdrawals() { ... }
    @Test void stillAllowsDeposits() { ... }
}
```

One logical assertion per test. "One assertion" does not mean one `assertThat` — asserting three fields of one returned object is one logical assertion. Use `assertAll` or AssertJ soft assertions when you want all failures reported at once rather than stopping at the first.

Keep setup visible. A fixture built in a distant `@BeforeEach` with fields mutated across tests makes failures unreadable. Prefer **test data builders** or static factories so each test states exactly what matters:

```java
// Object Mother / builder: defaults that don't matter, overrides that do.
var order = anOrder().withStatus(PAID).withLines(2).build();
```

This is the single highest-leverage investment in a test suite — it keeps tests short and makes the relevant difference between two tests obvious.

## JUnit 5 essentials

A note on versions: JUnit has unified Jupiter and Platform onto a single **JUnit 6** version line (no more 5.x-Jupiter / 1.x-Platform split). The `org.junit.jupiter` package names and the annotations below are unchanged, so everything in this section applies to both — but let the project's Spring Boot BOM manage the version rather than pinning one yourself, and do not assume which line a project is on.

```java
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.*;
import static org.assertj.core.api.Assertions.*;
```

**Lifecycle:** `@BeforeEach`/`@AfterEach` per test, `@BeforeAll`/`@AfterAll` static per class. A new instance per test method is the default — rely on it rather than resetting state manually.

**Parameterized tests** replace copy-pasted near-duplicates, and the `name` attribute keeps failures identifiable:

```java
@ParameterizedTest(name = "{0} VAT → {1}")
@CsvSource({"DE, 0.19", "FR, 0.20", "LU, 0.17"})
void appliesCountryVatRate(String country, BigDecimal expected) {
    assertThat(VatRates.forCountry(country)).isEqualByComparingTo(expected);
}

@ParameterizedTest
@MethodSource("invalidIbans")   // static Stream<Arguments> / Stream<String>
void rejectsInvalidIban(String iban) {
    assertThatThrownBy(() -> Iban.parse(iban)).isInstanceOf(IllegalArgumentException.class);
}

@ParameterizedTest
@EnumSource(value = OrderStatus.class, names = {"SHIPPED", "DELIVERED"})
void cannotCancelOnceDispatched(OrderStatus status) { ... }

@ParameterizedTest
@NullAndEmptySource @ValueSource(strings = {" ", "\t"})
void rejectsBlankName(String name) { ... }
```

**Exceptions** — assert the type *and* something about the message or state, otherwise the test passes on the wrong failure:

```java
assertThatThrownBy(() -> service.transfer(from, to, amount))
    .isInstanceOf(InsufficientFundsException.class)
    .hasMessageContaining("A-1")
    .hasNoCause();
```

**Other tools worth knowing:** `@Timeout` for runaway tests, `@Tag("slow")` plus build-level filtering to keep the fast suite fast, `@TempDir` for filesystem work (auto-cleaned), `@DisabledOnOs`/`@EnabledIfSystemProperty` for environment-specific cases, and `@RepeatedTest` for smoking out flakiness. Avoid `@Disabled` without a linked issue — a permanently disabled test is a lie about coverage.

**Custom extensions** (`BeforeEachCallback`, `ParameterResolver`) are the right tool when several test classes need the same non-trivial setup; they beat an abstract base test class, which quickly accumulates unrelated machinery.

## AssertJ

Prefer AssertJ over raw JUnit assertions: the fluent API is discoverable and, more importantly, its failure messages show the actual value and the diff.

```java
assertThat(order.total()).isEqualByComparingTo("119.00");   // BigDecimal: never isEqualTo
assertThat(names).containsExactly("ana", "bo");             // order matters
assertThat(names).containsExactlyInAnyOrder("bo", "ana");   // order doesn't
assertThat(maybeUser).contains(expectedUser);               // Optional
assertThat(result).hasSize(3).extracting(Line::sku).containsExactly("A", "B", "C");
assertThat(invoice)
    .usingRecursiveComparison()
    .ignoringFields("id", "createdAt")
    .isEqualTo(expected);                                   // whole-object compare
assertThat(instant).isCloseTo(expected, within(1, ChronoUnit.SECONDS));
```

`usingRecursiveComparison()` with ignored volatile fields is the cleanest way to assert a whole object without fifteen separate field assertions that drift out of date.

When a domain assertion repeats across tests, write a custom assert (`assertThat(invoice).isSettled()`) — it reads like the domain and centralizes the failure message.

Use `SoftAssertions` / `assertSoftly` when several independent properties should all be reported:

```java
assertSoftly(softly -> {
    softly.assertThat(resp.status()).isEqualTo(201);
    softly.assertThat(resp.body().id()).isNotBlank();
    softly.assertThat(resp.headers().firstValue("Location")).isPresent();
});
```

## Mockito: and when not to mock

Mock **what you own and what crosses a boundary you cannot cheaply run**: a payment gateway, an SMTP client, a clock. Do not mock value objects, collections, the thing under test, or types you do not own (mocking a third-party library's API encodes your *assumption* about its behavior and passes happily when the assumption is wrong — wrap it in your own interface and mock that).

```java
@ExtendWith(MockitoExtension.class)
class IssueInvoiceUseCaseTest {

    @Mock InvoiceRepository repository;
    @Mock PaymentGateway gateway;
    @InjectMocks IssueInvoiceUseCase useCase;      // or construct explicitly — often clearer

    @Test
    void publishesReceiptAfterSuccessfulCharge() {
        when(gateway.charge(any(), any())).thenReturn(new PaymentResult.Settled("r-1", Money.usd("10.00")));

        useCase.handle(new IssueInvoiceCommand("A-1", Money.usd("10.00")));

        var saved = ArgumentCaptor.forClass(Invoice.class);
        verify(repository).save(saved.capture());
        assertThat(saved.getValue().status()).isEqualTo(SETTLED);
    }
}
```

Notes that prevent the common mistakes:
- `MockitoExtension` is strict by default — unused stubs fail the test. Keep that on; it catches tests that silently stopped exercising what they claim to.
- Prefer `ArgumentCaptor` or an argument matcher over `verify(mock).method(any())`, which asserts almost nothing.
- Use `verifyNoInteractions` / `verifyNoMoreInteractions` deliberately, for "we must not charge twice" — not reflexively, since it makes tests brittle.
- `@Spy` and `doReturn().when(spy)` on the class under test are a design smell: you are stubbing the thing you are testing. Extract the collaborator instead.
- Mocking statics (`mockStatic`) or final methods is possible but is a signal that a static dependency should have been injected. Fix the design when you can.

**A hand-written fake often beats a mock.** An in-memory `Map`-backed `InvoiceRepository` implementing the port makes tests read as behavior rather than call sequences, supports the whole suite, and doubles as a check that the port is actually implementable.

## Spring Boot test slices

Loading the full context for every test is the main reason Java test suites are slow. Load the smallest slice that exercises the risk.

**No Spring at all** — for domain and application logic. Construct the class with fakes. This should be most of your tests.

**`@WebMvcTest`** — one controller, the full MVC machinery (validation, serialization, exception handlers, security filters), service layer mocked:

```java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {
    @Autowired MockMvcTester mvc;            // fluent AssertJ-based API
    @MockitoBean IssueInvoiceUseCase useCase;

    @Test
    void returns400WhenAmountNegative() {
        assertThat(mvc.post().uri("/invoices")
                .contentType(APPLICATION_JSON)
                .content("""
                    {"accountId":"A-1","amount":-5}
                    """))
            .hasStatus(HttpStatus.BAD_REQUEST)
            .bodyJson().extractingPath("$.errors[0].field").isEqualTo("amount");
    }
}
```

This is where you test status codes, validation messages, JSON shape, and error mapping — the wire contract. (`MockMvcTester` and `@MockitoBean` are the current API; Boot 4 removed `@MockBean`. On Boot 3.3 or earlier, use `MockMvc` with `mockMvc.perform(...)` and `@MockBean`. Boot 4 also splits test slices into technology-specific modules, so check that the matching test starter is on the classpath.)

**`@DataJpaTest`** — repositories, entity mappings, and queries against a real database via Testcontainers. This is where `@Query` typos, missing cascades, and N+1 problems surface. Point it at the real engine, not H2: H2 accepts SQL Postgres rejects and vice versa, so an H2-green suite proves little.

**`@JsonTest`** — serialization contracts, for when the API shape matters and you don't want a web test for it.

**`@SpringBootTest`** — full context, for wiring and cross-cutting behavior. Use sparingly and keep the configuration identical across these tests so Spring's context cache is actually hit; every distinct combination of properties, mocked beans, or active profiles builds and caches a *new* context, which is the usual cause of a suite that takes ten minutes. `@DirtiesContext` discards the cache — treat each use as a deliberate cost.

Use `@ServiceConnection` on a Testcontainer to wire datasource properties automatically instead of hand-written `@DynamicPropertySource`.

## Testcontainers

Real dependencies in Docker, started per suite. The pattern that keeps them fast — one shared container for the whole run:

```java
@Testcontainers
@SpringBootTest
abstract class IntegrationTestBase {

    @Container @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    // static → started once per JVM, reused by every subclass
}
```

Guidance that matters in practice:
- **`static` containers, not instance** — an instance container restarts per test method and will dominate your build time.
- **Pin image tags** (`postgres:16-alpine`, not `latest`) so the build is reproducible.
- **Reset state between tests**, not the container: `@Sql` scripts, truncation, or `@Transactional` rollback on the test. Restarting containers for isolation is the slow way.
- **Use the module for the real technology** — Kafka, LocalStack (S3/SQS), Redis, MongoDB, WireMock for HTTP dependencies. Testing against a mock when a container is available trades a 2-second test for a production incident.
- Enable **reuse** (`testcontainers.reuse.enable=true`) locally for fast feedback; leave it off in CI.

## Testing concurrency

Concurrency bugs do not reproduce on demand, so test for them structurally rather than by hoping.

- **Never `Thread.sleep`.** Use `CountDownLatch`/`CyclicBarrier` to force the interleaving you want to test, or Awaitility (`await().atMost(2, SECONDS).untilAsserted(...)`) when you must wait for an outcome.
- **Force contention deliberately:** run N tasks against the shared object on a virtual-thread executor, join, and assert the final invariant (total is exact, no lost updates).
- **Prefer making concurrency untestable-by-irrelevance** — immutable data and single-writer designs remove the bug class instead of testing for it.
- For lock-free or algorithmically tricky code, use **jcstress**; ordinary tests cannot explore memory-model interleavings.
- Assert on **idempotency and at-least-once delivery** for message handlers — that is the real-world failure, and it is deterministically testable.

## Testing time and randomness

Hidden non-determinism is the most common cause of a test that fails at midnight or in another timezone. Inject it:

```java
// Production wiring: Clock.systemUTC(); tests: Clock.fixed(...)
record SubscriptionService(Clock clock, SubscriptionRepository repo) {
    boolean isExpired(Subscription s) { return s.expiresAt().isBefore(clock.instant()); }
}

var clock = Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);
```

`java.time.Clock` exists precisely for this. The same applies to `Random` (inject a seeded instance), UUID generation (inject a supplier), and anything environment-dependent. Any `LocalDate.now()` or `new Random()` inside business logic is a latent flaky test.

## ArchUnit: enforcing architecture

Architecture rules that are not executable are suggestions. ArchUnit turns them into failing tests:

```java
@AnalyzeClasses(packages = "com.acme.billing", importOptions = DoNotIncludeTests.class)
class ArchitectureTest {

    @ArchTest
    static final ArchRule domainIsFrameworkFree = noClasses()
        .that().resideInAPackage("..domain..")
        .should().dependOnClassesThat().resideInAnyPackage(
            "org.springframework..", "jakarta.persistence..", "tools.jackson..", "com.fasterxml.jackson..");

    @ArchTest
    static final ArchRule layersRespected = layeredArchitecture().consideringOnlyDependenciesInLayers()
        .layer("Domain").definedBy("..domain..")
        .layer("Application").definedBy("..application..")
        .layer("Infrastructure").definedBy("..infrastructure..")
        .whereLayer("Infrastructure").mayNotBeAccessedByAnyLayer()
        .whereLayer("Application").mayOnlyBeAccessedByLayers("Infrastructure");

    @ArchTest
    static final ArchRule noFieldInjection = noFields()
        .should().beAnnotatedWith("org.springframework.beans.factory.annotation.Autowired");

    // Catches the leak a signature check misses: a controller whose method returns a DTO
    // but that still imports the entity and maps it on the last line. The entity type has
    // crossed the boundary, so schema changes still break the web layer.
    @ArchTest
    static final ArchRule entitiesStayOutOfTheWebLayer = noClasses()
        .that().resideInAPackage("..web..")
        .should().dependOnClassesThat().areAnnotatedWith("jakarta.persistence.Entity");

    @ArchTest
    static final ArchRule noCycles = slices()
        .matching("com.acme.(*)..").should().beFreeOfCycles();
}
```

Add these early. Retrofitting them onto a codebase that has already drifted means a hundred violations and a disabled test.

## Property-based and mutation testing

**Property-based testing** (jqwik) checks invariants across generated inputs instead of hand-picked examples, and shrinks failures to a minimal case. It earns its keep for parsers, serializers, encoders, money and date arithmetic, and anything with an algebraic property:

```java
@Property
void parsingAFormattedIbanRoundTrips(@ForAll("validIbans") String iban) {
    assertThat(Iban.parse(iban).formatted()).isEqualTo(iban);
}
```

Good properties to look for: round-trip (`parse(format(x)) == x`), invariance (sorting preserves size and multiset), idempotency, commutativity, and comparison against a slow-but-obviously-correct reference implementation.

**Mutation testing** (PIT) answers the question coverage cannot: do your tests actually *detect* broken code? It mutates bytecode and reports which mutants survived. Run it on the modules with real logic — a high line coverage with a low mutation score means the tests execute the code without checking it. Treat the surviving mutants as a to-do list, not a metric to maximize.

## Coverage: what the number means

Coverage tells you what was **executed**, not what was **verified** — a suite with no assertions can hit 100%. So:

- Use it to find *untested* code, which it does well, not to prove code is tested.
- Enforce a floor (JaCoCo `check` with ~80% line / 70% branch on new code) so coverage cannot silently collapse, and exclude generated code, DTOs, and config classes so the number is about logic.
- Branch coverage is the more informative number; aim your attention at uncovered branches in business logic.
- Never write a test purely to raise coverage. A test with no assertion that calls a getter is worse than no test: it costs maintenance and reports safety that does not exist.

## TDD when it pays

Red → green → refactor is most valuable when the specification is clear and the logic is intricate: parsers, calculations, state machines, bug fixes. Writing the failing test first is the fastest way to pin a reported bug, and it guarantees the test actually fails without the fix — a step people skip, which is how no-op tests get committed.

It pays less when you are exploring an unfamiliar API or an unclear design; there, spike first, then delete the spike and build it test-first with what you learned.

Either way, **write the test for a bug before the fix**. It proves the diagnosis and prevents the regression.

## Flakiness

A flaky test is worse than no test, because it trains the team to re-run CI instead of reading failures. The causes, in rough order of frequency:

1. **Time** — `now()` in logic, timezone assumptions, DST, test running at a boundary. Fix: inject `Clock`.
2. **Shared mutable state between tests** — static caches, singletons, a database row left behind. Fix: reset in `@AfterEach`, or make the test independent of ordering.
3. **Sleeps and races** — fixed waits for async work. Fix: Awaitility or latches.
4. **Ordering assumptions** — `HashMap`/`HashSet` iteration order, unordered SQL results without `ORDER BY`. Fix: assert order-insensitively or order explicitly.
5. **External network calls** — fix: WireMock or Testcontainers, never the live service.
6. **Port collisions / parallel execution** — fix: random ports (`webEnvironment = RANDOM_PORT`), and declare JUnit parallel-execution safety honestly.

When a test is flaky, fix or delete it. Do not retry it — a retry annotation hides the signal, and the underlying race is frequently a real production bug reporting itself for free.
