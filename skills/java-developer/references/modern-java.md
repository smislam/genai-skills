# Modern Java: language and API

Read this when choosing language features or standard-library APIs. The default target is **Java 25 LTS**. Features finalised after 21 are marked with their version, so you can tell what to avoid if a project is still on 21.

Verify the project's actual level before using anything here — `maven.compiler.release`, `<java.version>`, or `languageVersion` in the Gradle toolchain. A feature that does not compile is worse than an old idiom.

## Contents
- [Availability at a glance](#availability-at-a-glance)
- [Records](#records)
- [Sealed types and exhaustive switch](#sealed-types-and-exhaustive-switch)
- [Pattern matching](#pattern-matching)
- [Text blocks and string APIs](#text-blocks-and-string-apis)
- [var: where it helps and where it hurts](#var-where-it-helps-and-where-it-hurts)
- [Optional, used correctly](#optional-used-correctly)
- [Streams and collections](#streams-and-collections)
- [java.time](#javatime)
- [Numbers and money](#numbers-and-money)
- [Exceptions](#exceptions)
- [Equality, hashing, comparison](#equality-hashing-comparison)
- [Files and I/O](#files-and-io)
- [HTTP client](#http-client)
- [Java 22–25: what the baseline adds over 21, and what is still preview](#java-2225-what-the-baseline-adds-over-21-and-what-is-still-preview)
- [Logging](#logging)
- [Modules](#modules)
- [Idiom upgrade table](#idiom-upgrade-table)

## Availability at a glance

LTS versions are **8, 11, 17, 21, 25**. **25 is the default for new work.** 21 is the floor for existing code you maintain: JDK 17's premier support window closed in late 2026. The latest GA release line is JDK 27.

| Feature | Final in | Notes |
|---|---|---|
| `var` local inference | 10 | |
| Switch expressions | 14 | |
| Text blocks | 15 | |
| Records (JEP 395) | 16 | |
| `instanceof` pattern (JEP 394) | 16 | |
| Sealed classes (JEP 409) | 17 | |
| Pattern matching for `switch` (JEP 441) | **21** | Type patterns, guards, exhaustiveness |
| Record patterns (JEP 440) | **21** | Destructuring, nestable |
| Virtual threads (JEP 444) | **21** | See `concurrency.md` |
| Sequenced collections (JEP 431) | **21** | `getFirst()`, `getLast()`, `reversed()` |
| Generational ZGC (JEP 439) | 21 | Default mode from 23; non-generational removed in 24 |
| Foreign Function & Memory API (JEP 454) | 22 | Supported replacement for JNI / `sun.misc.Unsafe` |
| Unnamed variables and patterns `_` | 22 | |
| Stream gatherers (JEP 485) | 24 | Custom intermediate stream ops |
| Class-file API | 24 | |
| AOT class loading & linking (JEP 483) | 24 | Startup; see `performance.md` |
| `ScopedValue` (JEP 506) | **25** | `ThreadLocal` replacement |
| Module import declarations (JEP 511) | 25 | `import module java.base;` |
| Compact source files + instance `main` (JEP 512) | 25 | Scripts/teaching, not services |
| Flexible constructor bodies (JEP 513) | 25 | Statements before `super()` |
| Generational Shenandoah (JEP 521) | 25 | |
| Compact object headers (JEP 519) | 25 | Opt-in flag; real heap savings |
| AOT command-line ergonomics + method profiling | 25 | JEP 514 / 515 |

Still **not** final as of JDK 27 — do not ship these:

| Feature | Status |
|---|---|
| Structured concurrency | Preview since 21; **7th preview in 27** (JEP 533), API reshaped repeatedly |
| Primitive types in patterns / `instanceof` / `switch` | 5th preview in 27 (JEP 532) |
| Lazy Constants (was "Stable Values") | 3rd preview in 27 (JEP 531); renamed mid-flight |
| Vector API | Still incubating (`jdk.incubator.vector`), 12th round |
| String templates | **Withdrawn.** Previewed in 21–22, the third preview was pulled before 23 and no successor has shipped. `STR."..."` does not exist — use `formatted()` |

Treat anything marked preview or incubator as off-limits for production unless the team has explicitly accepted `--enable-preview`, which pins the bytecode to that exact JDK version and forces a code change at every upgrade.

## Records

A record is the right default for any data carrier: DTOs, value objects, command/query objects, projections, composite map keys, multi-value returns. You get a canonical constructor, accessors, `equals`, `hashCode`, and `toString` with no room for them to drift out of sync.

```java
public record InvoiceLine(String sku, int quantity, Money unitPrice) {

    // Compact constructor: validation and normalisation, once, unbypassable.
    public InvoiceLine {
        Objects.requireNonNull(sku, "sku");
        if (quantity <= 0) throw new IllegalArgumentException("quantity must be positive: " + quantity);
    }

    // Derived values are methods, not fields.
    public Money total() { return unitPrice.multiply(quantity); }

    // Static factory for the common case.
    public static InvoiceLine single(String sku, Money price) { return new InvoiceLine(sku, 1, price); }
}
```

Things worth knowing:
- Records are **shallowly** immutable. A `record Order(List<Line> lines)` can still have its list mutated by whoever passed it. Defensively copy in the compact constructor (`lines = List.copyOf(lines)`) when the record must be a real value.
- Records can implement interfaces and be nested inside a sealed interface — that combination is the workhorse of modern domain modelling (see `design.md`).
- A record with a mutable field, a setter, or framework-required no-arg constructor is not a record use case. JPA entities in particular cannot be records.
- For many optional components, add a builder or static factories; records do not have optional parameters.
- "Withers": write explicit `withQuantity(int)` methods returning a new instance. There is no language support yet.
- Local records inside a method are excellent for intermediate stream shapes — far better than `Object[]` or `Map<String, Object>`.

## Sealed types and exhaustive switch

```java
public sealed interface Shape permits Circle, Rectangle, Triangle {}
public record Circle(double radius) implements Shape {}
public record Rectangle(double w, double h) implements Shape {}
public record Triangle(double base, double height) implements Shape {}

double area(Shape shape) {
    return switch (shape) {
        case Circle c    -> Math.PI * c.radius() * c.radius();
        case Rectangle r -> r.w() * r.h();
        case Triangle t  -> t.base() * t.height() / 2;
    };                      // exhaustive: no default, and adding a variant breaks compilation
}
```

The value is in what *fails to compile*. A `default` branch in a switch over a sealed type throws that away — you get a runtime surprise instead of a build error. Omit `default` deliberately.

`permits` can be inferred when all implementations are in the same file; listing them explicitly is clearer for multi-file hierarchies. Implementations must be in the same module (or same package, if unnamed module).

## Pattern matching

```java
// instanceof pattern — no cast, scoped binding
if (event instanceof PaymentSettled settled && settled.amount().isPositive()) {
    record(settled.receiptId());
}

// Record deconstruction, nested, with guards
String describe(Object o) {
    return switch (o) {
        case null                               -> "nothing";
        case Point(int x, int y) when x == y    -> "diagonal at " + x;
        case Point(int x, int y)                -> "point %d,%d".formatted(x, y);
        case Line(Point(var x1, var y1), Point p2) -> "from %d,%d to %s".formatted(x1, y1, p2);
        case String s                           -> "string of length " + s.length();
        default                                 -> "unknown: " + o.getClass().getSimpleName();
    };
}
```

- `case null` is now expressible; without it, `switch` on a null selector throws NPE as before.
- Guards use `when`, and ordering matters — the first matching case wins, so put specific patterns before general ones (the compiler rejects an unreachable case where it can prove dominance).
- Nested record patterns replace chains of accessor calls and null checks, which is where most of the readability gain comes from.

This combination — sealed interface + records + exhaustive switch with deconstruction — is the single biggest change in how good Java is written since Java 8. Prefer it over visitor hierarchies, `instanceof` ladders, and type-code fields.

## Text blocks and string APIs

```java
var query = """
    SELECT i.id, i.total
      FROM invoice i
     WHERE i.status = ?
       AND i.created_at > ?
    """;                                  // incidental indentation stripped to the closing delimiter

var json = """
    {"sku":"%s","qty":%d}""".formatted(sku, qty);
```

Use text blocks for SQL, JSON, XML, and multi-line messages — they remove escaping and concatenation noise. Trailing `\` suppresses the newline; `\s` keeps a trailing space.

Useful string methods beyond the basics: `isBlank()`, `strip()` (Unicode-aware, unlike `trim()`), `lines()`, `repeat(n)`, `formatted(...)`, `chars()`, and `String.join`. For building strings in a loop use `StringBuilder`; outside loops, `+` compiles to efficient code and is clearer.

Never build SQL by concatenation or `formatted()` with user input — see `security.md`.

## var: where it helps and where it hurts

Use `var` when the right-hand side already names the type:

```java
var invoices = new ArrayList<Invoice>();                       // clear
var entry = iterator.next();                                   // fine, type is obvious in context
for (var line : invoice.lines()) { ... }                        // good
```

Avoid it when it erases information the reader needs:

```java
var result = service.process(input);   // what is result? now the reader must go look
var x = 0;                             // int or long? matters for arithmetic
var list = getItems();                 // List? Set? mutable?
```

The test is whether a reviewer can tell the type from the same screen. `var` with a diamond (`var x = new HashMap<>()`) infers `HashMap<Object,Object>` — a real bug source. Never use `var` for a lambda target or where an interface type is the point (`List<X> l = new ArrayList<>()` deliberately programs to the interface).

## Optional, used correctly

`Optional` exists to make "may be absent" visible in a **return type**. That is its whole job.

```java
// Good
Optional<Customer> findByEmail(String email);

repository.findByEmail(email)
    .map(Customer::preferredName)
    .filter(not(String::isBlank))
    .orElseGet(() -> defaultGreeting(email));

repository.findById(id)
    .orElseThrow(() -> new CustomerNotFoundException(id));
```

```java
// Bad
record Customer(Optional<String> phone) {}        // field: use nullable + documented, or absent-as-empty
void notify(Optional<String> address) {}          // parameter: use overloads
if (opt.isPresent()) { use(opt.get()); }          // use ifPresent / map / orElse
opt.orElse(expensiveDefault())                    // eagerly evaluated — use orElseGet
Optional<List<X>>                                 // return an empty list instead
```

Never return `Optional` from a collection-returning method, never put it in a DTO you serialise, and prefer `orElseThrow()` over `get()` (which is deprecated-in-spirit and reads like it cannot fail).

## Streams and collections

Streams are for expressing a transformation pipeline clearly. If a loop is clearer, write the loop — a stream with a stateful lambda, a side effect, or three nested `flatMap`s is worse than the loop it replaced.

```java
Map<Status, List<Invoice>> byStatus = invoices.stream()
    .filter(Invoice::isOpen)
    .collect(groupingBy(Invoice::status));

Map<String, BigDecimal> totalBySku = lines.stream()
    .collect(groupingBy(Line::sku, reducing(BigDecimal.ZERO, Line::total, BigDecimal::add)));

Optional<Invoice> largest = invoices.stream().max(comparing(Invoice::total));

var summary = invoices.stream().mapToLong(Invoice::cents).summaryStatistics();
```

Practical guidance:
- `toList()` (Java 16+) returns an unmodifiable list — prefer it to `collect(Collectors.toList())` unless you need mutability.
- `List.of()` / `Map.of()` / `Set.of()` for immutable literals; they reject nulls and duplicate keys, which catches bugs. `Map.of()` is limited to 10 pairs — use `Map.ofEntries`.
- `List.copyOf(x)` for defensive copies.
- Never mutate the source collection inside a stream operation, and never rely on side effects in `map`/`filter`. Use `forEach` only for genuine terminal effects, and know it does not guarantee order on parallel streams (`forEachOrdered` does).
- `Collectors.teeing` for two aggregations in one pass; `mapMulti` for one-to-many without stream allocation in hot paths. `functional-java.md` covers collector composition, `Predicate`/`Comparator` combinators, and the checked-exception problem in pipelines.
- Prefer `IntStream`/`LongStream` for primitive work to avoid boxing.
- `parallelStream()` only for large, CPU-bound, independent work — see `concurrency.md` for why it is usually a mistake.

**Sequenced collections (21)** fix a long-standing gap:

```java
list.getFirst(); list.getLast(); list.reversed();
linkedHashMap.firstEntry(); linkedHashMap.pollLastEntry();
new LinkedHashSet<>(x).reversed();
```

Choosing a collection: `ArrayList` unless you have a measured reason; `ArrayDeque` instead of `Stack` or `LinkedList`; `HashMap` unless you need ordering (`LinkedHashMap`) or sorting (`TreeMap`); `EnumMap`/`EnumSet` for enum keys (they are array-backed and much faster); `ConcurrentHashMap` for shared mutation. `LinkedList` is almost never the right answer.

## java.time

Never use `Date`, `Calendar`, `SimpleDateFormat`, or `Timestamp` in new code.

- **`Instant`** — a point on the timeline, UTC. Use for timestamps, events, created/updated fields, and anything stored or transmitted.
- **`LocalDate`** — a date with no time or zone. Birthdays, invoice dates, "the 1st of the month".
- **`LocalDateTime`** — date and time with **no zone**. Usually the wrong choice: it does not identify a moment. Use it only for wall-clock concepts like "the shop opens at 09:00".
- **`ZonedDateTime`** — a moment in a named zone, DST-aware. Use for user-facing scheduling ("09:00 in Europe/Berlin, whatever the offset").
- **`OffsetDateTime`** — a moment with a fixed offset. Good for wire formats and DB columns with time zone.
- **`Duration`** (time-based) vs **`Period`** (date-based) — adding one month is not adding 30 days, and DST makes "one day" ≠ 24 hours.

```java
var expiry = created.plus(Duration.ofDays(30));
var renewal = startDate.plusMonths(1);                        // calendar-aware
var fmt = DateTimeFormatter.ISO_INSTANT;                      // thread-safe, unlike SimpleDateFormat
var berlin = instant.atZone(ZoneId.of("Europe/Berlin"));
```

Store and compute in UTC (`Instant`), convert to a zone only for display. Inject a `Clock` instead of calling `Instant.now()` directly so the behaviour is testable (`testing.md`). Use IANA zone IDs, never three-letter abbreviations.

## Numbers and money

- **Money is `BigDecimal`** with an explicit scale and `RoundingMode`, or a `long` of minor units wrapped in a value object. `double` cannot represent 0.1, and the error compounds.
- `new BigDecimal("0.1")` — from a **String**, never `new BigDecimal(0.1)`, which captures the binary error.
- Compare with `compareTo` (or AssertJ's `isEqualByComparingTo`); `equals` on `BigDecimal` considers scale, so `2.0 != 2.00`.
- Every division needs a scale and rounding mode or it throws on a non-terminating result.
- Use `Math.addExact`/`multiplyExact` when silent overflow would be a correctness bug; `Math.floorMod` for correct modulo of negatives (`%` returns negative).
- Do not use `Double.equals` or `==` on floating point; compare with a tolerance.

## Exceptions

- **Unchecked for programming errors and unrecoverable conditions** (`IllegalArgumentException`, `IllegalStateException`, your own domain `RuntimeException`s). **Checked only when the caller can realistically recover** and you want to force the decision. Modern Java leans heavily unchecked, especially in Spring applications where checked exceptions do not compose with lambdas or streams.
- Prefer a **sealed result type over exceptions for expected business outcomes** (declined, not-found-as-normal-flow). Exceptions for control flow are slow and hide the paths.
- Messages must include the offending values: `"No invoice with id " + id`, not `"Not found"`.
- Always chain the cause: `new DomainException("...", e)`. Dropping the cause destroys the diagnosis.
- Use try-with-resources for everything closeable; it handles suppressed exceptions correctly, which hand-written `finally` almost never does.
- Do not use exceptions to return values, do not catch `Exception` broadly except at a top-level boundary (where you log once with context), and never catch `Error`/`Throwable`.
- Custom exceptions: extend `RuntimeException`, provide `(String)` and `(String, Throwable)` constructors, and carry structured fields (the id, the status) rather than only a formatted string.

## Equality, hashing, comparison

Let `record` generate `equals`/`hashCode` wherever possible. When you write them by hand: consistent with each other, based on the same immutable fields, and never on mutable state (a mutated key is lost in a `HashMap` forever). Use `Objects.equals` and `Objects.hash`.

For entities with database identity, equality on the **business/natural key or the assigned id**, not on all fields — and be careful with JPA: entity equality based on a generated id is broken before the flush that assigns it.

`Comparable` must be consistent with `equals` if the type goes in a `TreeSet`/`TreeMap`. Build comparators declaratively:

```java
invoices.sort(comparing(Invoice::dueDate).thenComparing(Invoice::total, reverseOrder()));
comparing(Invoice::customerName, nullsLast(String.CASE_INSENSITIVE_ORDER));
```

Never implement `compare` as `a.value - b.value` — it overflows.

## Files and I/O

```java
Path path = Path.of("data", "invoices.csv");                 // not new File(...)
String content = Files.readString(path, UTF_8);               // always specify the charset
Files.writeString(out, content, UTF_8, CREATE, TRUNCATE_EXISTING);

try (var lines = Files.lines(path, UTF_8)) {                  // lazy; MUST be closed
    return lines.filter(not(String::isBlank)).count();
}

try (var walk = Files.walk(dir)) { ... }                      // also closeable
```

Always specify a charset — platform default is a portability bug (it is UTF-8 by default since Java 18, but explicit beats implicit and older targets differ). Use `Files.createTempFile` with restrictive permissions rather than predictable paths in `/tmp`. Validate and normalise any path built from user input (`security.md`).

## HTTP client

`java.net.http.HttpClient` (Java 11+) replaces `HttpURLConnection` and removes the need for a third-party client in simple cases:

```java
var client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(Redirect.NORMAL)
    .build();                                  // thread-safe; create once and reuse

var request = HttpRequest.newBuilder(URI.create(url))
    .timeout(Duration.ofSeconds(5))            // per-request timeout: always set one
    .header("Accept", "application/json")
    .POST(BodyPublishers.ofString(body, UTF_8))
    .build();

var response = client.send(request, BodyHandlers.ofString());
```

In a Spring application, prefer `RestClient` or a declarative HTTP interface instead (`spring-boot.md`) so you get observability, error handling, and converters for free. Whatever client you use: set both connect and read timeouts, and reuse the client instance.

## Java 22–25: what the baseline adds over 21, and what is still preview

Everything finalised here is part of the default Java 25 baseline, so use it. If the project is on 21, none of it compiles; stick to the 21 idiom.

- **Unnamed variables and patterns `_` (22)** — `catch (IOException _)`, `case Point(int x, _)`. Small readability win that documents an intentionally unused binding.
- **Foreign Function & Memory API (22)** — `MemorySegment`, `Arena`, `Linker`, `SymbolLookup`: the supported replacement for JNI and `sun.misc.Unsafe`, both of which are being restricted and removed. Restricted calls warn on stderr unless you pass `--enable-native-access=<module>|ALL-UNNAMED` (or set the `Enable-Native-Access` manifest attribute); the warning is slated to become an `IllegalCallerException`.
- **Stream gatherers (24)** — custom intermediate operations (`windowFixed`, `windowSliding`, `fold`, `scan`) that `Collectors` could never express. Genuinely useful for chunking and sliding-window logic.
- **AOT class loading and linking (24), plus command-line ergonomics and method profiling (25)** — the shipped parts of Project Leyden. Meaningful startup wins for short-lived or rapidly scaled processes; see `performance.md`.
- **`ScopedValue` (25)** — the `ThreadLocal` replacement for virtual threads; see `concurrency.md`.
- **Flexible constructor bodies (25)** — validate arguments before `super()`, removing a class of awkward static-helper workarounds.
- **Compact object headers (25, opt-in)** — `-XX:+UseCompactObjectHeaders` shrinks object headers and can cut heap use measurably on allocation-heavy workloads.
- **Module import declarations and compact source files (25)** — for scripts and teaching. Not for application code.
- **Still preview or incubating at JDK 27:** structured concurrency, primitive types in patterns, Lazy Constants, Vector API. Do not ship them. String templates were withdrawn entirely — `STR."..."` does not exist.
- **Security Manager is permanently disabled** (JEP 411 deprecated it in 17; **JEP 486 in 24** makes `System.setSecurityManager` throw and the JVM refuse to start with `-Djava.security.manager`). Code relying on `SecurityManager`, `AccessController`, or policy files must be redesigned — see `migration.md` and `security.md`.
- **JNI is being restricted** (JEP 472): `System.loadLibrary` and native method declarations warn by default and can be denied with `--illegal-native-access=deny`. Part of the broader "integrity by default" direction, which is progressively closing off deep reflection and `Unsafe`.

## Logging

SLF4J API, with Logback or Log4j2 as the binding. In Spring Boot, use the bundled setup rather than adding your own.

```java
private static final Logger log = LoggerFactory.getLogger(InvoiceService.class);

log.info("Issued invoice {} for account {} totalling {}", invoiceId, accountId, total);
log.atDebug().addKeyValue("invoiceId", invoiceId).log("Recalculated totals");   // fluent, structured
log.error("Failed to settle invoice {}", invoiceId, e);                         // exception LAST, no placeholder
```

- **Parameterized messages, never concatenation.** `log.debug("x " + expensive())` evaluates the argument even when debug is off.
- The throwable goes as the final argument with **no** `{}` for it; otherwise you lose the stack trace.
- Levels: ERROR = someone must act; WARN = suspicious but handled; INFO = business events worth keeping; DEBUG = developer detail; TRACE = firehose. Logging at INFO inside a per-row loop is how log bills and incidents happen.
- Never log credentials, tokens, full card numbers, or personal data. Never log a whole request body blindly.
- Log once per failure, at the boundary that handles it. Log-and-rethrow produces the same stack trace three times and makes incidents harder to read.
- Put request/trace ids in MDC (or `ScopedValue`) and let the pattern emit them, instead of threading ids through log messages by hand.
- Prefer structured (JSON) output in production so logs are queryable.

## Modules

JPMS (`module-info.java`) is worth it for libraries and for `jlink`-ed runtimes, where a small, well-defined surface and a trimmed image pay off. For a typical Spring Boot service it adds friction — reflection-heavy frameworks need `opens` directives, and the classpath works fine. Most applications should use the classpath and spend the effort on package-private visibility and ArchUnit rules instead, which deliver most of the encapsulation benefit without the build complexity.

If you do modularise: one module per published artifact, `exports` only the API packages, `requires transitive` sparingly, and `opens ... to` the specific framework module rather than `open module`.

## Idiom upgrade table

| Legacy | Modern |
|---|---|
| `new File(path)` | `Path.of(path)` + `Files.*` |
| `SimpleDateFormat` | `DateTimeFormatter` |
| `Date`/`Calendar` | `Instant`/`LocalDate`/`ZonedDateTime` |
| `Collections.unmodifiableList(new ArrayList<>(x))` | `List.copyOf(x)` |
| `Arrays.asList(1,2,3)` (fixed-size, nulls allowed) | `List.of(1,2,3)` |
| `collect(Collectors.toList())` | `toList()` |
| Anonymous single-method class | Lambda / method reference |
| `StringBuilder` for a fixed multi-line literal | Text block |
| POJO + getters/setters | `record` |
| `instanceof` + cast | `instanceof` pattern |
| `if/else` type dispatch | `switch` over a sealed type |
| `HttpURLConnection` | `HttpClient` / `RestClient` |
| `Vector`, `Hashtable`, `Stack` | `ArrayList`, `HashMap`, `ArrayDeque` |
| `Integer.valueOf(s)` + try/catch for validation | `Integer.parseInt` with a guard, or a validating parse |
| `System.out.println` | SLF4J |
| `e.printStackTrace()` | `log.error("context {}", id, e)` |
| `new Random()` shared | `ThreadLocalRandom.current()` (or `SecureRandom` for anything security-relevant) |
| `clone()` | Copy constructor / static factory / record wither |
| `finalize()` | try-with-resources, `Cleaner` |
| Raw `List` | `List<T>` |
| `assert` for argument validation | `Objects.requireNonNull` / explicit throw (asserts are off at runtime) |
