# Spring Boot

Read this before writing or restructuring Spring Boot code. Default target: **Spring Boot 4.x on Java 25**. Where Boot 3.x needs different code, it is marked. Check the project's actual version in `pom.xml`/`build.gradle.kts` first.

## Contents
- [Application structure](#application-structure)
- [Beans and configuration classes](#beans-and-configuration-classes)
- [Configuration properties](#configuration-properties)
- [Profiles and environments](#profiles-and-environments)
- [Web layer](#web-layer)
- [Validation](#validation)
- [Error handling](#error-handling)
- [HTTP clients](#http-clients)
- [Persistence with JPA](#persistence-with-jpa)
- [Transactions](#transactions)
- [Spring Data query choices](#spring-data-query-choices)
- [JdbcClient for SQL-first code](#jdbcclient-for-sql-first-code)
- [Caching](#caching)
- [Events](#events)
- [Scheduling and async](#scheduling-and-async)
- [Observability](#observability)
- [Actuator and health](#actuator-and-health)
- [Testing](#testing)
- [Packaging and containers](#packaging-and-containers)
- [Boot 4 baseline, and differences from 3.x](#boot-4-baseline-and-differences-from-3x)
- [Anti-patterns](#anti-patterns)

## Application structure

Package by feature, layer inside the feature (full rationale in `design.md`):

```
com.acme.billing.invoice/
├── InvoiceController.java      (web: DTOs in, DTOs out)
├── InvoiceService.java         (use case; @Transactional lives here)
├── Invoice.java                (domain or entity, depending on complexity)
├── InvoiceRepository.java      (Spring Data interface)
└── dto/IssueInvoiceRequest.java, InvoiceResponse.java
```

The `@SpringBootApplication` class sits in the root package and should contain nothing but `main`. Component scanning starts there — classes outside that package tree are invisible, which is the usual cause of "my bean isn't found".

Keep the layers honest: controllers do HTTP (parse, validate, map, status codes), services do business logic and own the transaction, repositories do data access. A controller that calls a repository directly, or a repository that contains business rules, is the thing to fix.

## Beans and configuration classes

**Constructor injection, no annotation needed** for a single-constructor bean:

```java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final PaymentGateway gateway;
    private final Clock clock;

    public InvoiceService(InvoiceRepository repository, PaymentGateway gateway, Clock clock) {
        this.repository = repository;
        this.gateway = gateway;
        this.clock = clock;
    }
}
```

Why not `@Autowired` on fields: the object can exist in an invalid state, the fields cannot be `final`, and unit tests need reflection or a context to construct it. Constructor injection also surfaces circular dependencies at startup instead of hiding them — if you hit a cycle, that is a design signal, not something to paper over with `@Lazy`.

- **`@Component`/`@Service`/`@Repository`** for your own classes; **`@Bean` methods in a `@Configuration` class** for third-party types you do not own.
- Inject a `Clock` bean (`Clock.systemUTC()`) rather than calling `Instant.now()` — it makes time testable.
- **Avoid `@Primary` + many candidates**; prefer `@Qualifier` with an explicit name, or inject `List<T>`/`Map<String,T>` when you genuinely want all implementations (the Strategy pattern in Spring form).
- Use `@ConditionalOnProperty`/`@ConditionalOnMissingBean` in library/starter code, not routinely in application code where profiles are clearer.
- Prefer `ObjectProvider<T>` to `@Lazy` when a dependency is genuinely optional.
- Bean scope is singleton by default: **a singleton bean must be stateless or thread-safe.** A mutable field on a `@Service` is a race condition under concurrent requests.

## Configuration properties

Typed, validated, immutable configuration beats scattered `@Value`:

```java
@ConfigurationProperties(prefix = "billing.payment")
@Validated
public record PaymentProperties(
        @NotBlank String apiKey,
        @DefaultValue("5s") Duration timeout,
        @Min(0) @Max(10) int maxRetries,
        @NotNull URI endpoint) {}
```

Enable with `@EnableConfigurationProperties(PaymentProperties.class)` or `@ConfigurationPropertiesScan`. Records bind constructor-style, which keeps the config immutable.

Why this over `@Value("${...}")`: the failure happens at startup with a precise message instead of at first use; the values are discoverable and documented; relaxed binding handles `BILLING_PAYMENT_API_KEY` from the environment; and `Duration`/`DataSize` types parse `5s`/`10MB` for you.

Use `application.yaml` for structure, environment variables for anything environment-specific, and **never commit secrets** — pull them from the environment or a secret manager (`security.md`).

## Profiles and environments

Keep profiles few and meaningful (`local`, `test`, `prod`) and avoid profile-specific code paths in business logic — that is how "works on my machine" happens. Put differences in configuration, not in `@Profile`-annotated beans, except for genuine infrastructure substitutions (an in-memory queue locally, a real broker in prod).

`spring.config.import` handles layered config files and secret backends. `spring.profiles.group` composes profiles. Avoid `@Profile("!prod")` guards around security — a disabled security filter in a profile that someone accidentally activates in production is a real incident pattern.

## Web layer

```java
@RestController
@RequestMapping("/api/invoices")
class InvoiceController {

    private final InvoiceService service;

    InvoiceController(InvoiceService service) { this.service = service; }

    @PostMapping
    ResponseEntity<InvoiceResponse> issue(@Valid @RequestBody IssueInvoiceRequest request) {
        var invoice = service.issue(request.toCommand());
        return ResponseEntity
                .created(URI.create("/api/invoices/" + invoice.id()))
                .body(InvoiceResponse.from(invoice));
    }

    @GetMapping("/{id}")
    InvoiceResponse get(@PathVariable UUID id) {
        return service.findById(id).map(InvoiceResponse::from)
                .orElseThrow(() -> new InvoiceNotFoundException(id));
    }

    @GetMapping
    Page<InvoiceResponse> list(@RequestParam Optional<Status> status, Pageable pageable) {
        return service.search(status, pageable).map(InvoiceResponse::from);
    }
}
```

- **DTOs at the boundary, always** — records are ideal. Never accept or return an entity: it couples your API to your schema, leaks fields, and enables mass-assignment attacks.
- **Controller classes and methods can be package-private.** Public is not required and `public` on everything weakens encapsulation.
- **Return the right status**: 201 + `Location` for creation, 204 for a successful delete, 200 with a body otherwise. `ResponseEntity` only when you need to control status or headers; otherwise return the body type.
- **Always paginate collection endpoints.** An unpaginated `findAll` is a latent outage.
- Keep controllers free of business logic and of `@Transactional`.
- For blocking controllers, set `spring.threads.virtual.enabled=true` rather than tuning Tomcat's thread pool (`concurrency.md`).

## Validation

Bean Validation on the request DTO, invariants in the domain. The two are complementary: the DTO rejects malformed input at the edge with a good error message; the domain constructor guarantees nothing invalid exists even if a caller bypasses the web layer.

```java
public record IssueInvoiceRequest(
        @NotBlank @Size(max = 64) String accountId,
        @NotNull @DecimalMin("0.01") @Digits(integer = 10, fraction = 2) BigDecimal amount,
        @NotNull @Valid List<@Valid LineRequest> lines,
        @Email String notifyEmail) {}
```

`@Valid` on the parameter triggers it; nested objects need `@Valid` on the field too. For cross-field rules write a custom `ConstraintValidator` rather than checking in the controller. `@Validated` on a bean class enables method-level validation for service parameters.

Reject unknown JSON fields (`spring.jackson.deserialization.fail-on-unknown-properties=true`) so a typo in a client's payload is an error rather than a silently ignored field.

## Error handling

One global handler producing a consistent, machine-readable body. Prefer RFC 9457 `ProblemDetail`, which Spring supports natively:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(InvoiceNotFoundException.class)
    ProblemDetail handleNotFound(InvoiceNotFoundException e) {
        var problem = ProblemDetail.forStatusAndDetail(NOT_FOUND, e.getMessage());
        problem.setType(URI.create("https://api.acme.com/problems/invoice-not-found"));
        problem.setTitle("Invoice not found");
        return problem;                                   // expected outcome: no stack trace logged
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleValidation(MethodArgumentNotValidException e) {
        var problem = ProblemDetail.forStatus(BAD_REQUEST);
        problem.setTitle("Validation failed");
        problem.setProperty("errors", e.getFieldErrors().stream()
                .map(f -> Map.of("field", f.getField(), "message", f.getDefaultMessage()))
                .toList());
        return problem;
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception e) {
        log.error("Unhandled exception", e);              // log once, here, with the stack trace
        return ProblemDetail.forStatusAndDetail(INTERNAL_SERVER_ERROR, "Unexpected error");
    }
}
```

Two rules that matter more than the format: **never leak internals** — no stack traces, SQL, or class names in responses (`server.error.include-stacktrace=never`); and **log unexpected errors once, where you handle them**, with enough context (ids, not the whole payload) to diagnose.

Map domain exceptions to status codes in the advice, not by annotating exceptions with `@ResponseStatus` — keeping HTTP concerns out of the domain is the point.

## HTTP clients

`RestTemplate` is maintenance-only. Use `RestClient` for synchronous calls:

```java
@Bean
RestClient paymentClient(RestClient.Builder builder, PaymentProperties props) {
    return builder
            .baseUrl(props.endpoint().toString())
            .requestFactory(ClientHttpRequestFactoryBuilder.detect()
                    .build(ClientHttpRequestFactorySettings.defaults()
                            .withConnectTimeout(Duration.ofSeconds(2))
                            .withReadTimeout(props.timeout())))
            .defaultStatusHandler(HttpStatusCode::isError, (req, res) -> {
                throw new PaymentGatewayException("Gateway returned " + res.getStatusCode());
            })
            .build();
}
```

Inject the auto-configured `RestClient.Builder` (not a bare `RestClient.create()`) so you inherit observability, message converters, and tracing. **Set both timeouts on every client** — the default is often infinite, and one unresponsive dependency with no read timeout will exhaust your capacity.

For a declarative client, define an HTTP interface and back it with the client — it keeps the call site clean and is easy to stub in tests:

```java
interface PaymentApi {
    @PostExchange("/charges")
    ChargeResponse charge(@RequestBody ChargeRequest request);
}
```

Wrap external calls behind a domain port (`design.md`) so retries, circuit breakers (Resilience4j), and error translation live in one adapter rather than scattered through services.

## Persistence with JPA

JPA is powerful and leaky. The rules below prevent the overwhelming majority of real production problems.

```java
@Entity
@Table(name = "invoice")
public class InvoiceEntity {

    @Id @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false) private String accountId;

    @Enumerated(EnumType.STRING)                 // never ORDINAL — reordering the enum corrupts data
    @Column(nullable = false) private Status status;

    @OneToMany(mappedBy = "invoice", cascade = ALL, orphanRemoval = true)
    private List<InvoiceLineEntity> lines = new ArrayList<>();

    @Version private long version;               // optimistic locking

    protected InvoiceEntity() { }                // JPA requires it; keep it non-public
}
```

- **`FetchType.LAZY` everywhere.** `@ManyToOne` and `@OneToOne` default to EAGER, which silently loads half your graph on every query. Set it explicitly.
- **Fix N+1 deliberately**, with `JOIN FETCH` or an `@EntityGraph` on the query — not by making relations eager. Detect it in tests by asserting query counts; `spring.jpa.properties.hibernate.generate_statistics` and a logged SQL count make it visible.
- **`@Version` for optimistic locking** on anything concurrently editable. Without it, last-write-wins silently loses updates. Use `@Lock(PESSIMISTIC_WRITE)` only for short, contended critical sections.
- **`EnumType.STRING`**, always.
- **Paginate.** `findAll()` on a real table is an outage. Note that pagination combined with `JOIN FETCH` of a collection forces in-memory paging — use a two-query approach (ids first, then fetch) for that case.
- **Never expose entities over HTTP.** Lazy proxies serialize unpredictably and you leak schema.
- **Beware `@Data`/Lombok on entities** — generated `equals`/`hashCode`/`toString` touch lazy collections, triggering loads and `StackOverflowError` on bidirectional relations.
- **Use DTO projections for reads** (`interface InvoiceSummary { UUID getId(); BigDecimal getTotal(); }` or a constructor expression) — fetching whole entity graphs to render a list is the most common avoidable cost.
- **Schema is managed by migrations** (Flyway or Liquibase). Set `spring.jpa.hibernate.ddl-auto=validate` in every real environment; `update` is a data-loss mechanism and `create-drop` belongs only in throwaway tests.
- **Batch writes** need `hibernate.jdbc.batch_size`, ordered inserts/updates, and a non-identity id strategy (`IDENTITY` disables insert batching).
- **Client-assigned ids make every `save()` an update-or-insert guess.** Spring Data decides between `persist` and `merge` by asking "is this entity new?", and with a generated id the answer is "the id is null, so yes". Assign the id yourself — a UUID created in the constructor — and the id is never null, so it calls `merge()`, which issues a **SELECT before every insert**. That is a silent per-row cost that no test will fail on. Fix it by implementing `Persistable<ID>` with an explicit `isNew()` flag, or by adding a `@Version` field (Spring Data treats a null/zero version as new). This bites hardest on exactly the entities you are most likely to hand-assign — events, refunds, outbox rows — so check it whenever you write `@Id` without `@GeneratedValue`.

## Transactions

```java
@Service
public class InvoiceService {

    @Transactional                                     // write: default propagation REQUIRED
    public Invoice issue(IssueInvoiceCommand command) { ... }

    @Transactional(readOnly = true)                    // read: skips dirty checking, hints the driver
    public Optional<Invoice> findById(UUID id) { ... }
}
```

The traps, all of which are common in real codebases:

- **Self-invocation does nothing.** `@Transactional` is proxy-based; calling `this.otherTransactionalMethod()` bypasses the proxy entirely and runs with no transaction. Move the method to another bean or inject self via `ObjectProvider`.
- **Only public methods are advised** by the default proxying. A `@Transactional` private or package-private method is silently ignored (unless AspectJ weaving is configured).
- **Rollback is only automatic for unchecked exceptions.** A checked exception commits by default — declare `@Transactional(rollbackFor = ...)` if you throw one.
- **Keep transactions short and free of I/O.** An HTTP call inside a transaction holds a database connection for the duration of someone else's outage. Do remote work before or after, and use `@TransactionalEventListener(AFTER_COMMIT)` for post-commit side effects.
- **`@Transactional` on a controller** stretches the transaction over serialization. Put it on the application service, one transaction per use case.
- **`readOnly = true` for queries** — measurable benefit at scale, and it documents intent.
- **Transaction ≠ distributed transaction.** For cross-service consistency use the outbox pattern or sagas; `@Transactional` will not help you.

## Spring Data query choices

In increasing order of control:

1. **Derived query methods** — `findByStatusAndCreatedAtAfter(...)`. Great up to about three conditions; beyond that the name becomes unreadable and you should move on.
2. **`@Query` with JPQL** — named parameters (`:status`), explicit and refactor-visible. Validated at startup, which catches typos.
3. **`@Query(nativeQuery = true)`** — for database-specific SQL. Not portable, not validated; cover it with an integration test against the real engine.
4. **Specifications / Criteria API** — for dynamic filters. Powerful, verbose; wrap in well-named static factories so call sites stay readable.
5. **`JdbcClient` or jOOQ** — when the work is fundamentally SQL (reporting, bulk, complex joins). Using JPA for these is fighting the tool.

Never build a query string by concatenating user input — including into `Sort` or dynamic `ORDER BY` fragments, which is a real injection vector in Spring Data (validate the sort field against an allowlist).

## JdbcClient for SQL-first code

For reads that do not need an object graph, `JdbcClient` (Boot 3.2+) is simpler, faster, and completely explicit:

```java
List<InvoiceSummary> open = jdbcClient
        .sql("""
            SELECT id, total FROM invoice
             WHERE status = :status AND created_at > :since
             ORDER BY created_at DESC
             LIMIT :limit
            """)
        .param("status", Status.OPEN.name())
        .param("since", since)
        .param("limit", limit)
        .query(InvoiceSummary.class)
        .list();
```

Named parameters are bound, so this is injection-safe by construction. Mixing JPA for writes with `JdbcClient` for reads is a legitimate and often excellent design — just be aware of the JPA first-level cache: a `JdbcClient` write inside a JPA transaction will not be visible to already-loaded entities, and vice versa, so do not interleave them on the same data in one transaction.

## Caching

```java
@Cacheable(cacheNames = "invoices", key = "#id")
public Invoice findById(UUID id) { ... }

@CacheEvict(cacheNames = "invoices", key = "#invoice.id()")
public void update(Invoice invoice) { ... }
```

Use Caffeine for local caching, Redis when the cache must be shared. Decide three things explicitly or the cache will cause an incident: **TTL** (never cache forever), **key** (include everything that affects the result — tenant, locale, permissions), and **eviction on write**.

Also: `@Cacheable` is proxy-based (self-invocation does not cache); caching a mutable object hands callers a shared reference they can corrupt; and cache stampede on expiry needs `refreshAfterWrite` or a lock. Never cache per-user data under a key that omits the user.

## Events

```java
// Publish from the aggregate's service
publisher.publishEvent(new InvoiceSettled(invoice.id(), clock.instant()));

// React only if the transaction committed
@TransactionalEventListener(phase = AFTER_COMMIT)
void onSettled(InvoiceSettled event) { notifier.send(event.invoiceId()); }
```

Events decouple modules inside one application — useful for keeping a bounded context from depending on another. Keep payloads immutable records carrying ids, not entities (a detached entity on another thread is a `LazyInitializationException`). Default listeners are **synchronous and inside the publisher's transaction**, which surprises people: a throwing listener rolls back the publisher's work. Use `AFTER_COMMIT` for side effects and `@Async` (plus explicit error handling) when you want real decoupling. For cross-service events, use a broker with an outbox — in-process events are not durable.

## Scheduling and async

**`@Scheduled`** (with `@EnableScheduling`):
- **Pick the right timing.** `fixedDelay` waits after each run finishes; `fixedRate` starts on a fixed beat whether or not the last run finished. Use `cron` with an explicit `zone` for calendar times, so daylight-saving changes and server time zones don't move the job.
- **The default scheduler has one thread,** so one slow job delays every other job. Size it (`spring.task.scheduling.pool.size`), or keep jobs short and hand the work off.
- **Every instance runs every job.** With three replicas, a nightly job runs three times. Use a distributed lock (ShedLock with the database you already have), run the job somewhere that has exactly one instance (a Kubernetes `CronJob`, a dedicated worker), or make the job idempotent. Usually do both: the lock and idempotency.
- **Make jobs observable:** log the start, the end, the duration, and the outcome, and alert when a job hasn't succeeded within its expected window. A silently failing scheduled job is invisible until someone needs its output.
- **Externalize schedules** to configuration (`@Scheduled(cron = "${billing.cron}")`), so they change without a rebuild, and so tests can disable them.

**`@Async`** (with `@EnableAsync`):
- **It works through a proxy:** calling an `@Async` method from the same class runs it synchronously, exactly like `@Transactional` self-invocation.
- **Return `CompletableFuture<T>`** when the caller needs the result or the failure. Exceptions from a `void` `@Async` method go only to the `AsyncUncaughtExceptionHandler`, so configure one, or they disappear.
- **Bound the executor.** Size the pool and the queue (`spring.task.execution.pool.*`), or use virtual threads (`spring.threads.virtual.enabled=true`) with a semaphore for whatever the work calls. An unbounded queue is a memory leak under load (see "Anti-patterns").
- **Context doesn't follow the thread.** MDC, the security context, and the tracing context are thread-bound. Propagate them with a `TaskDecorator` (`ContextPropagatingTaskDecorator` with Micrometer context propagation), or pass what the task needs explicitly.
- **Transactions don't cross threads.** The async method starts its own transaction, if any, and can't see the caller's uncommitted data. Publish an event after commit instead (see "Events").

## Observability

Micrometer is built in. The three things worth doing on every service:

```java
// 1. Meaningful metrics — Timer/Counter with low-cardinality tags
Timer.builder("invoice.settlement")
     .tag("gateway", gatewayName)       // NEVER tag with user id, invoice id, or URL path params
     .register(registry);

// 2. Tracing: propagate context across service calls (micrometer-tracing + an exporter)
// 3. Structured JSON logs with trace id in MDC
```

Cardinality is the one trap that bites hard: a tag with unbounded values (ids, emails, raw paths) creates a time series per value and will take down your metrics backend. Use `@Observed` or `ObservationRegistry` for spans that matter. Export the standard JVM, HTTP, datasource, and HikariCP metrics — they answer most production questions without custom instrumentation.

## Actuator and health

Actuator is an operational API. Treat it with the same care as a public one:

- **Expose only what operations needs over HTTP:** typically `health`, `info`, and the metrics endpoint your monitoring scrapes (`management.endpoints.web.exposure.include=health,info,prometheus`). **Never `*`:** `heapdump`, `env`, `threaddump`, `configprops`, `loggers`, and `mappings` leak credentials, memory contents, and internals, or allow runtime changes.
- **Separate the port where you can** (`management.server.port`), so the management endpoints aren't reachable through the public ingress. And secure them with Spring Security either way: the health endpoint open (probes need it), everything else behind authentication.
- **Control access deliberately.**
  - **Boot 3.4 and later** configure endpoint access with `management.endpoints.access.default` and per-endpoint `management.endpoint.<id>.access` (`none`, `read-only`, `unrestricted`). These replace `management.endpoints.enabled-by-default` and `management.endpoint.<id>.enabled`, deprecated in 3.4, so update them during an upgrade.
  - **To cap access application-wide,** use `management.endpoints.access.max-permitted`, which overrides both the default and per-endpoint settings. For example, `read-only` for every endpoint in production.
  - **Defaults:** `shutdown` is inaccessible by default. **Since Boot 3.5, `heapdump` is too** (`access=none`): using it needs both exposure *and* `management.endpoint.heapdump.access`, whereas on 3.4 and earlier, exposing it was enough. On an older Boot, `exposure.include=*` exposes heap dumps.
  - Keep both off unless you have a reason.
- **Health detail:** `management.endpoint.health.show-details=when-authorized`, so anonymous callers see only `UP` or `DOWN`, not your database host and version.
- **Liveness is not readiness:**
  - **Liveness** says "this process is broken; restart it". Keep it to the application's own state. **Never include downstream dependencies in liveness:** a database outage would make Kubernetes restart every pod at once, turning an outage into a restart storm.
  - **Readiness** says "don't send me traffic right now". This is where critical dependencies belong, through health groups (`management.endpoint.health.group.readiness.include=readinessState,db`).
  - Wire them to the probes as described in "Packaging and containers".
- **Custom `HealthIndicator`s** must be fast and must time out. A health check that hangs on a slow dependency hangs the probe.
- **`info`:** add build and git information (the `spring-boot-maven-plugin` `build-info` goal, `git-commit-id-maven-plugin`), so you can tell which version is running. Don't put secrets or environment details there.

## Testing

Covered in depth in `testing.md`. The Spring-specific summary: unit-test domain and services with plain constructors and fakes; `@WebMvcTest` for the HTTP contract; `@DataJpaTest` + Testcontainers against the real database engine for mappings and queries; `@SpringBootTest` sparingly, with identical configuration so the context cache is reused. Use `@ServiceConnection` to wire containers, and keep H2 out of tests whose point is SQL behavior.

## Packaging and containers

- Build layered images (`spring-boot-maven-plugin` layertools or buildpacks) so dependency layers cache between deploys.
- **Run as a non-root user**, on a JRE base image (or a `jlink`ed runtime), with a read-only filesystem where possible.
- **Set container-aware memory limits**: the JVM reads cgroup limits, and `-XX:MaxRAMPercentage=70` is a better lever than a fixed `-Xmx` because it adapts to the container size. Leave headroom for metaspace, thread stacks, and direct buffers — heap is not the whole footprint.
- Wire `readiness` to `/actuator/health/readiness` and `liveness` to `/actuator/health/liveness`, and enable graceful shutdown (`server.shutdown=graceful`) so in-flight requests finish during a rolling deploy.
- Use CDS/AOT cache for startup time if it matters; GraalVM native image only if you have measured that you need sub-100ms starts and accepted the build-time and reflection-configuration cost (`performance.md`).

## Boot 4 baseline, and differences from 3.x

Boot 4.x (on Spring Framework 7) is the default here. Its differences from 3.x are mostly *structural* rather than language-level. One thing that surprises people: **the minimum Java version did not change — 4.0 still requires Java 17**, same as the 3.x line. So do not assume a 4.x project is on Java 25, or even 21; check the build file.

Write new code the Boot 4 way. On a 3.x project, these are the places the code differs:

- **Jar and package reorganization.** Boot now ships as many smaller modules under dedicated `org.springframework.boot.<module>` packages, with technology-specific starters replacing some broad ones. This changes imports and dependency coordinates across the board — it is the bulk of the migration diff.
- **Jackson 3.** The group id moves from `com.fasterxml.jackson` to `tools.jackson`, with class renames. Jackson 2 support remains only in deprecated form. Write custom serializers, modules, and mapper configuration against Jackson 3; on 3.x, use the `com.fasterxml.jackson` equivalents.
- **JSpecify nullability annotations** replace `org.springframework.lang.@Nullable`/`@NonNull` throughout the framework. Use `org.jspecify.annotations` in your own code too. Combined with a null checker, this surfaces warnings in previously quiet code — usually real latent bugs.
- **`@MockBean` and `@SpyBean` are removed.** Use `@MockitoBean` / `@MockitoSpyBean` (also available from Boot 3.4, so prefer them there too).
- **Undertow support is gone** — Tomcat, Jetty, or Reactor Netty only. Spock test integration and some Spring Session auto-configurations were also removed.
- **Config property renames**, including `spring.dao.exceptiontranslation.enabled` → `spring.persistence.exceptiontranslation.enabled` and `management.tracing.enabled` → `management.tracing.export.enabled`.
- **New capabilities worth using:** auto-configured HTTP service clients for annotated interfaces, API versioning for MVC/WebFlux (`spring.mvc.apiversion.*`), an OpenTelemetry starter, and `JmsClient`.
- **Upgrade the portfolio together.** Spring Framework 7, Spring Security 7, and Spring Data 4 are the matching baselines, and the compatible Spring Cloud release train typically lags Boot's GA — check Spring Cloud's compatibility matrix before committing to a date.

Read the official Boot 4.0 migration guide for the authoritative list; the details shift across point releases, so do not rely on memory (or on this file) for a specific property name you are about to write. `migration.md` has the upgrade procedure.

## Anti-patterns

| Anti-pattern | Why it hurts | Instead |
|---|---|---|
| `@Autowired` fields | Untestable, non-final, hides cycles | Constructor injection |
| Entity anywhere in the web layer | Couples API to schema; mass assignment; lazy-proxy serialization. A DTO-only method signature is not enough — if the controller imports the entity and maps it on the last line, the coupling is still there | DTO records, mapped in the service; enforce with the ArchUnit rule in `testing.md` |
| `@Transactional` on controllers | Transaction spans serialization and HTTP | On the application service |
| Business logic in controllers | Untestable without MVC; unreusable | Application service |
| `findAll()` on a real table | Unbounded memory and latency | `Pageable` |
| EAGER relations to "fix" N+1 | Loads the world on every query | `JOIN FETCH` / `@EntityGraph` / projections |
| `ddl-auto=update` in production | Silent, unreviewed, irreversible schema change | Flyway/Liquibase + `validate` |
| Mutable field on a singleton bean | Data races between requests | Stateless beans; pass state as parameters |
| Secrets in `application.yaml` | Leaked in git, images, and logs | Env vars / secret manager |
| Stack traces in HTTP responses | Information disclosure | `ProblemDetail` + `include-stacktrace=never` |
| H2 in tests for a Postgres app | Different SQL dialect; green tests, broken prod | Testcontainers |
| `@SpringBootTest` for everything | Minutes-long suites, context thrash | Test slices |
| Catch-and-log in every layer | Triplicated stack traces, no single source of truth | Handle once at the boundary |
| No timeouts on outbound calls | One slow dependency exhausts all capacity | Explicit connect + read timeouts, circuit breaker |
| Unbounded `@Async` executor | Memory growth under load | Bounded executor or virtual threads with a semaphore |
| High-cardinality metric tags | Melts the metrics backend | Low-cardinality tags only |
