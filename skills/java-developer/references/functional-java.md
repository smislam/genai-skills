# Functional Java

Read this when composing behaviour out of functions, designing an API that takes a lambda, or deciding whether a functional style actually helps. Streams, `Optional`, and the language-level basics are in `modern-java.md`; this file is about using functions *as values*.

## Contents
- [The premise](#the-premise)
- [The standard functional interfaces](#the-standard-functional-interfaces)
- [Composition](#composition)
- [Method references](#method-references)
- [Writing your own functional interfaces](#writing-your-own-functional-interfaces)
- [The checked exception problem](#the-checked-exception-problem)
- [Higher-order functions](#higher-order-functions)
- [Purity and side effects](#purity-and-side-effects)
- [Functional error handling](#functional-error-handling)
- [Laziness and memoisation](#laziness-and-memoisation)
- [Recursion](#recursion)
- [Collectors and gatherers](#collectors-and-gatherers)
- [Vavr and friends](#vavr-and-friends)
- [When functional style hurts](#when-functional-style-hurts)
- [Decision table](#decision-table)

## The premise

Java is not a functional language and pretending otherwise produces code your team cannot read. But three functional ideas pay for themselves in ordinary Java, and they are the reason this file exists:

1. **Immutable data** removes whole bug classes — concurrency races, action at a distance, defensive copying (`design.md`).
2. **Pure functions** are trivially testable: no setup, no mocks, no order dependence. Any logic you can push into a pure function gets cheaper to verify.
3. **Behaviour as a parameter** removes the inheritance ceremony that Java used to demand — a lambda replaces a Strategy class, a Comparator replaces a subclass.

What does *not* pay in Java: currying, point-free style, monad stacks, and deep `Function` composition chains. The JVM has no tail-call elimination, the type system cannot express higher-kinded types, and stack traces through composed lambdas are genuinely hard to read. Take the three ideas above; leave the rest to languages built for it.

## The standard functional interfaces

Almost every lambda you write targets one of these. Use the standard ones rather than inventing equivalents — every API in the JDK already speaks them.

| Interface | Shape | Method | Use for |
|---|---|---|---|
| `Function<T,R>` | T → R | `apply` | Mapping, transformation |
| `BiFunction<T,U,R>` | (T,U) → R | `apply` | Two-argument mapping, `Map.merge` |
| `UnaryOperator<T>` | T → T | `apply` | `List.replaceAll`, same-type transforms |
| `BinaryOperator<T>` | (T,T) → T | `apply` | Reductions, `Map.merge`, `Stream.reduce` |
| `Predicate<T>` | T → boolean | `test` | Filtering, validation |
| `BiPredicate<T,U>` | (T,U) → boolean | `test` | Two-argument conditions |
| `Supplier<T>` | () → T | `get` | Deferred/lazy values, factories |
| `Consumer<T>` | T → void | `accept` | Side effects at the edge |
| `BiConsumer<T,U>` | (T,U) → void | `accept` | `Map.forEach` |
| `Runnable` | () → void | `run` | Deferred action, no value |
| `Callable<T>` | () → T throws | `call` | Task that may throw — executors take these |

**Primitive specialisations exist and matter on hot paths**: `IntPredicate`, `ToIntFunction`, `IntUnaryOperator`, `LongSupplier`, `DoubleBinaryOperator`, and so on. A `Function<Integer,Integer>` boxes on every call; an `IntUnaryOperator` does not. Use the primitive form when the code is hot or the volume is large, and the generic form when clarity matters more (`performance.md`).

## Composition

This is where functions-as-values earn their keep: small named pieces combined at the call site, instead of one long method.

```java
Function<String, String> trim = String::strip;
Function<String, String> lower = String::toLowerCase;

Function<String, String> normalise = trim.andThen(lower);   // trim first, then lower
Function<String, String> same      = lower.compose(trim);   // identical: compose runs the argument first
```

`andThen` reads left-to-right and is almost always the clearer choice. `compose` reads inside-out; reach for it only when the surrounding code already reads that way.

**Predicate combinators** are the most practically useful of the lot, because validation rules compose naturally:

```java
Predicate<Order> isPaid     = o -> o.status() == PAID;
Predicate<Order> isRecent   = o -> o.createdAt().isAfter(cutoff);
Predicate<Order> isDomestic = o -> o.country().equals("DE");

var needsInvoice = isPaid.and(isRecent).and(isDomestic.negate());
orders.stream().filter(needsInvoice).toList();

// Static helper for negating a method reference, which `!` cannot do inline:
import static java.util.function.Predicate.not;
names.stream().filter(not(String::isBlank)).toList();
```

Naming each rule is the real win — `isPaid.and(isRecent)` survives code review in a way that a four-clause boolean expression does not. `Predicate.isEqual(target)` and `Predicate.not(...)` round out the set.

**Comparators compose the same way**, and this is the single most common place composition appears in real code:

```java
var byDueThenTotal = comparing(Invoice::dueDate)
        .thenComparing(Invoice::total, reverseOrder())
        .thenComparing(Invoice::id);          // tie-breaker keeps the sort stable and deterministic
```

`Consumer.andThen` chains side effects, and `Function.identity()` is the no-op you need for `Collectors.toMap(Invoice::id, identity())`.

## Method references

Four forms, and knowing which one you're writing prevents most "cannot resolve" confusion:

```java
String::strip               // unbound instance method — receiver becomes the first argument
invoice::total              // bound to a specific instance
Invoice::new                // constructor reference
Integer::parseInt           // static method
InvoiceEntity::setStatus    // unbound, two-arg: (entity, status) -> entity.setStatus(status)
```

Prefer a method reference to a lambda when it is a straight delegation (`x -> x.strip()` → `String::strip`); prefer an explicit lambda when you need to name the parameter for readability or add a null guard. A method reference to a method that does three things is not clearer than a lambda — it just hides where to look.

## Writing your own functional interfaces

Only when none of the standard ones fits — usually because you want a *domain-meaningful name* or more than two arguments.

```java
@FunctionalInterface
public interface PricingRule {
    Money apply(Order order, Customer customer, Instant at);

    // Default methods let your own interface compose, just like the JDK's.
    default PricingRule andThenCapAt(Money ceiling) {
        return (order, customer, at) -> {
            var price = apply(order, customer, at);
            return price.compareTo(ceiling) > 0 ? ceiling : price;
        };
    }
}
```

`@FunctionalInterface` is not required for a lambda to work, but add it: it makes the compiler reject a second abstract method, so nobody breaks every call site by "just adding one more method".

A named domain interface beats `TriFunction<Order, Customer, Instant, Money>` because the parameter meanings are visible at the declaration rather than inferred at each use. This is the functional equivalent of Introduce Parameter Object.

## The checked exception problem

This is the sharpest edge in functional Java. None of the standard interfaces declare checked exceptions, so this does not compile:

```java
paths.stream().map(Files::readString).toList();   // readString throws IOException
```

Three honest options, in order of preference:

```java
// 1. Handle it inside the lambda and return a value that models failure.
paths.stream().map(p -> {
    try { return Files.readString(p, UTF_8); }
    catch (IOException e) { return null; }        // or a sealed Result — see below
}).filter(Objects::nonNull).toList();

// 2. Don't use a stream. A plain for-loop handles checked exceptions natively
//    and is the right answer more often than people admit.
var contents = new ArrayList<String>();
for (var p : paths) {
    contents.add(Files.readString(p, UTF_8));     // throws IOException — propagate it
}

// 3. A throwing-functional-interface adapter, when the pipeline is genuinely worth keeping.
@FunctionalInterface
interface ThrowingFunction<T, R> { R apply(T t) throws Exception; }

static <T, R> Function<T, R> unchecked(ThrowingFunction<T, R> f) {
    return t -> {
        try { return f.apply(t); }
        catch (RuntimeException e) { throw e; }
        catch (Exception e) { throw new UncheckedIOException_or_DomainException(e); }
    };
}
```

Option 2 is underrated. If making code functional requires an exception-laundering helper, the loop was clearer. Whatever you do, **never swallow the exception to make the stream compile** — that is how data loss becomes silent.

## Higher-order functions

Functions that take or return functions. Taking one is routine; returning one is occasionally excellent and frequently overused.

```java
// Returning a function: a configured, reusable validator.
static Predicate<String> maxLength(int max) {
    return s -> s != null && s.length() <= max;
}
var validSku = maxLength(32).and(s -> s.matches("[A-Z0-9-]+"));

// Taking a function: the template-method pattern without inheritance.
<T> T inTransaction(Function<Session, T> work) {
    try (var session = factory.open()) {
        var tx = session.beginTransaction();
        try {
            var result = work.apply(session);
            tx.commit();
            return result;
        } catch (RuntimeException e) {
            tx.rollback();
            throw e;
        }
    }
}
```

That second shape — pass the varying step as a function, keep the invariant resource handling in one place — is the most valuable higher-order pattern in Java. It replaces Template Method inheritance (`design.md`) and guarantees cleanup.

**Currying and partial application** are expressible (`Function<A, Function<B, C>>`) and almost always a mistake in Java: the types get unreadable and no Java developer expects them. A two-argument method with a sensible default overload communicates the same thing.

## Purity and side effects

A pure function returns the same output for the same input and changes nothing observable. Push logic toward purity and the test suite gets dramatically cheaper — no mocks, no clock, no database.

The practical discipline: **keep I/O at the edges, keep decisions in the middle.**

```java
// Impure shell: fetches, calls the pure core, writes.
void settleInvoices(Instant now) {
    var open = repository.findOpen();
    var decisions = decideSettlements(open, now);    // pure, exhaustively testable
    decisions.forEach(this::apply);                   // effects, thin and dumb
}

// Pure core: no repository, no clock call, no logging. Just data in, data out.
static List<SettlementDecision> decideSettlements(List<Invoice> invoices, Instant now) { ... }
```

Inside streams specifically: `map` and `filter` must be side-effect-free. A lambda that mutates an external collection, increments a counter, or writes to a field is a bug waiting for someone to add `.parallel()`. Use a collector to build results, and reserve `forEach` for genuine terminal effects. Never mutate the source collection during a stream over it.

## Functional error handling

The JDK has no `Either` or `Try`, and `Optional` deliberately carries no failure reason. For expected business outcomes, model them with a **sealed interface** — this is the idiomatic Java answer and it gets you exhaustive `switch` checking (full treatment in `design.md`):

```java
sealed interface ParseResult<T> {
    record Ok<T>(T value) implements ParseResult<T> {}
    record Invalid<T>(String field, String reason) implements ParseResult<T> {}
}
```

Use `Optional` for "absent, and the reason doesn't matter" (a lookup miss). Use a sealed result for "failed, and the caller needs to know why". Use exceptions for genuinely exceptional conditions. Choosing exceptions for routine outcomes is both slow — stack-trace capture — and makes the control flow invisible.

`Optional` chaining is still the cleanest way to express a conditional pipeline:

```java
repository.findByEmail(email)
    .filter(Customer::isActive)
    .map(Customer::preferredName)
    .or(() -> fallbackName(email))     // lazy alternative Optional
    .orElseThrow(() -> new CustomerNotFoundException(email));
```

Note `or` takes a `Supplier<Optional<T>>` and `orElseGet` takes a `Supplier<T>` — both lazy. `orElse` evaluates eagerly, so `orElse(expensiveCall())` runs the call even on the happy path.

## Laziness and memoisation

`Supplier<T>` is deferred computation. The two patterns worth knowing:

```java
// Deferred: the message is only built if the condition fails.
require(amount.isPositive(), () -> "Amount must be positive but was " + amount);

// Memoised: computed at most once, thread-safe, no synchronisation on the hot path.
static <T> Supplier<T> memoise(Supplier<T> delegate) {
    var cache = new AtomicReference<T>();
    return () -> {
        var v = cache.get();
        if (v == null) {
            v = delegate.get();                       // may run twice under race; fine if pure
            cache.compareAndSet(null, v);
            v = cache.get();
        }
        return v;
    };
}
```

Memoising a *pure* function is safe and is the main legitimate use of a cache without eviction — the value cannot go stale. Memoising an impure one is a bug. For keyed memoisation use a real cache (Caffeine), and never put a blocking call inside `ConcurrentHashMap.computeIfAbsent` (`concurrency.md`).

Java 25 previews *Lazy Constants* (formerly Stable Values) for exactly this, but it is still preview at JDK 27 — do not ship it.

## Recursion

**The JVM has no tail-call elimination.** A recursive function over a list of ten thousand elements will throw `StackOverflowError`, no matter how you shape it. Default stack depth is a few thousand frames.

So: use recursion for genuinely tree-shaped problems of bounded depth — parsing, directory walks, composite structures — and iterate for anything linear or unbounded. If a recursive algorithm is the clearest expression but depth is a risk, convert it to an explicit `ArrayDeque` as the stack.

`Stream.iterate` with a predicate, `Stream.generate` with `limit`, and `IntStream.range` cover most of what people reach for recursion to express.

## Collectors and gatherers

Collectors are the composable part of streams people under-use:

```java
groupingBy(Invoice::status, counting())
groupingBy(Invoice::customerId, mapping(Invoice::id, toUnmodifiableList()))
groupingBy(Invoice::status, reducing(Money.ZERO, Invoice::total, Money::plus))
partitioningBy(Invoice::isOverdue)
toMap(Invoice::id, identity(), (a, b) -> a)        // merge function avoids a duplicate-key throw
teeing(counting(), summingLong(Invoice::cents), InvoiceSummary::new)   // two aggregations, one pass
collectingAndThen(toList(), List::copyOf)
```

`teeing` and `collectingAndThen` are the two that remove the most awkward code. Write a custom `Collector` only when nothing composes — it needs supplier, accumulator, combiner, and finisher to be mutually consistent, and getting the combiner wrong breaks only under `.parallel()`.

**Stream gatherers** (final in Java 24) add the intermediate operations `Collectors` never could — `windowFixed`, `windowSliding`, `fold`, `scan`. If you are on 24+ and currently chunking a stream by hand with an index, that is what they are for.

## Vavr and friends

Vavr brings persistent collections, `Either`, `Try`, `Option`, and pattern matching to Java. It is well made, and it is a significant decision: a second collections vocabulary in the codebase, conversion at every JDK boundary, and a dependency on every team member learning it.

Add it when the domain is genuinely functional — heavy pipelines of fallible transformations where `Either` chaining removes real noise — and the whole team is in. Otherwise sealed interfaces plus records give you the safety that matters with zero dependency and no translation layer. A codebase with Vavr in three classes and plain Java in three hundred has the costs of both and the benefits of neither.

## When functional style hurts

Be willing to say this out loud when reviewing:

- **Stack traces through composed lambdas are nearly unreadable.** Five chained `Function`s produce frames that name none of your methods. A named private method appears in the trace.
- **Debugging a pipeline is harder than debugging a loop** — you cannot easily set a breakpoint "on the third element" or inspect an intermediate list.
- **Checked exceptions do not fit**, as above, and the workarounds are uglier than the loop.
- **Deeply generic signatures** (`Function<? super T, ? extends Stream<? extends R>>`) are a readability tax paid by every future reader.
- **Hot loops**: lambda pipelines do not always inline away, and boxing through generic functional interfaces allocates. Measure before rewriting a loop as a stream for style (`performance.md`).
- **Three or more nested `flatMap`s** almost always means a loop with early return was the clearer code.

The test is whether a competent colleague reads it faster. If the functional version needs explaining, write the imperative one.

## Decision table

| Situation | Reach for |
|---|---|
| Transform a collection | Stream `map`/`filter`/`collect` |
| Several named validation rules | `Predicate` combinators (`and`/`or`/`not`) |
| Multi-key sort | `Comparator.comparing().thenComparing()` |
| Swap an algorithm at runtime | A lambda or `Map<Key, Function>` — not a Strategy class hierarchy |
| Invariant resource handling, varying body | Higher-order method taking a `Function` |
| Deferred or expensive default | `Supplier` + `orElseGet` |
| Compute once, pure, immutable | Memoised `Supplier` |
| Absent value, reason irrelevant | `Optional` return type |
| Expected failure with a reason | Sealed result interface |
| Truly exceptional condition | Exception |
| Checked exception inside a pipeline | A plain `for` loop |
| Chunking, sliding windows, running totals | Gatherers (24+), else a loop |
| Two aggregations in one pass | `Collectors.teeing` |
| Tree-shaped traversal, bounded depth | Recursion |
| Linear or unbounded traversal | Iteration — no TCO on the JVM |
