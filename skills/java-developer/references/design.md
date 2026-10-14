# Design: OO, SOLID, patterns, architecture

Read this when deciding how to structure code — classes, boundaries, layering, or whether a pattern is warranted.

## Contents
- [The decision order](#the-decision-order)
- [SOLID with judgement](#solid-with-judgement)
- [DRY, KISS, YAGNI and how they conflict](#dry-kiss-yagni-and-how-they-conflict)
- [Patterns by the pressure they relieve](#patterns-by-the-pressure-they-relieve)
- [Effective Java: the items that change code most](#effective-java-the-items-that-change-code-most)
- [Clean / hexagonal architecture in a Java project](#clean--hexagonal-architecture-in-a-java-project)
- [Domain modelling with records and sealed types](#domain-modelling-with-records-and-sealed-types)
- [Refactoring moves worth knowing by name](#refactoring-moves-worth-knowing-by-name)
- [Smells and what they actually indicate](#smells-and-what-they-actually-indicate)

## The decision order

Work outside-in, and stop as soon as the code is clear:

1. **What is the domain concept?** Name it in the language the business uses. If you cannot name it, you do not understand the requirement yet.
2. **What is the boundary?** What does this code depend on, and which direction should that dependency point? Dependencies point toward stable things — the domain — not toward frameworks or databases.
3. **What is the simplest thing that expresses it?** Usually a record, a small class, or a method. Most code needs no pattern at all.
4. **What pressure will change this?** Only now consider a pattern, and only if you can name the pressure.

Reversing this order is how codebases end up with `AbstractSingletonProxyFactoryBean`.

## SOLID with judgement

SOLID is five heuristics, not five laws. Each has a failure mode when applied without thought.

**Single Responsibility** — a class should have one reason to change, where "reason" means one stakeholder or one axis of volatility. Pricing rules change when finance changes its mind; PDF layout changes when marketing does. Those belong in different classes.
*Failure mode:* reading "responsibility" as "one method" and producing a cloud of single-method classes with no cohesive concept. Cohesion is the point, not smallness.

**Open/Closed** — you should be able to add behaviour by adding code, not editing existing code. Achieved in Java with polymorphism, strategies, or sealed hierarchies plus exhaustive switch.
*Failure mode:* extension points nobody uses. Every unused hook is dead weight and a false constraint. Add the seam when the second case arrives — the second case teaches you where the seam actually belongs.

**Liskov Substitution** — a subtype must honour the supertype's contract: no strengthened preconditions, no weakened postconditions, no new exceptions callers cannot anticipate. The classic violation is `Square extends Rectangle` with independent width/height setters, and the common real one is an override that throws `UnsupportedOperationException`.
*Practical consequence:* prefer composition. In Java, `sealed` interfaces let you model a closed set of variants without inheritance of behaviour at all.

**Interface Segregation** — clients should not be forced to depend on methods they do not use. A fat interface forces every implementor and every test double to deal with irrelevant methods.
*Practical consequence:* define the interface from the **client's** need and name it accordingly. `OrderRepository` with the three methods the order service actually uses beats a generic `Dao<T>` with twenty.

**Dependency Inversion** — high-level policy should not depend on low-level detail; both depend on an abstraction owned by the policy side. The interface belongs in the domain package, the implementation in the infrastructure package.
*Failure mode:* an interface per class, mechanically, with one implementation and the same name plus `Impl`. That is not inversion — it is indirection. Invert where the dependency actually crosses a boundary you want to protect or substitute (database, HTTP client, clock, message broker).

```java
// Domain owns the contract (domain/port package)
public interface PaymentGateway {
    PaymentReceipt charge(Money amount, CardToken token) throws PaymentDeclinedException;
}

// Infrastructure implements it (infrastructure/stripe package)
final class StripePaymentGateway implements PaymentGateway { /* ... */ }
```

The arrow now points from Stripe toward your domain. You can test the use case with a fake and swap providers without touching policy.

## DRY, KISS, YAGNI and how they conflict

**DRY** is about knowledge, not characters. Two methods with identical bodies that encode *different rules* must stay separate; they will diverge, and a shared helper will acquire a boolean parameter, then two, then a flag enum. Before extracting, ask: "if one caller's rule changes, should the other change too?" Only "yes" justifies sharing.

**KISS** is the tiebreaker when two designs are both defensible: pick the one a new team member understands faster. Clever outranks nothing.

**YAGNI** beats speculative generality. Build for the requirement in front of you, keep the code easy to change, and let the second requirement tell you where the abstraction goes. The cost of a missing abstraction is one refactor; the cost of a wrong abstraction is every future change fighting it.

When they conflict, the resolution is almost always: duplicate now, extract on the third occurrence, and only when the three share a reason to change.

## Patterns by the pressure they relieve

Look up the pressure, not the pattern. If no row describes your situation, you do not need a pattern.

### Creation

| Pressure | Pattern | Java-specific note |
|---|---|---|
| Constructor has many optional parameters | **Builder** | Prefer a `record` + static factories first; builder past ~4 optional params. Make the built object immutable. |
| Caller must not know which concrete type it gets | **Factory Method / Static Factory** | `static of(...)`, `from(...)`, `valueOf(...)`. Lets you cache, return a subtype, or change the type later. |
| Related objects must be created as a consistent family | **Abstract Factory** | Rare in Spring apps — configuration classes usually serve this role. |
| Exactly one instance, globally | **Singleton** | Use a Spring bean or an `enum` singleton. Never a lazily-initialised mutable static — it is a testability and concurrency trap. |
| Copying an object with small variations | **Prototype / wither** | Records: add `withX()` methods returning a new instance. |

### Structure

| Pressure | Pattern | Java-specific note |
|---|---|---|
| Third-party API's shape is wrong for your domain | **Adapter** | The core of hexagonal architecture — one adapter per external system. |
| Need to add behaviour to objects without subclass explosion | **Decorator** | Caching, retry, metrics, auth wrappers. Compose at wiring time. |
| Expensive or remote resource, want transparent access control | **Proxy** | Spring AOP is proxy-based — this is why `@Transactional` self-invocation silently does nothing. |
| Subsystem is too fine-grained for callers | **Facade** | An application service is a facade over domain objects. |
| Part/whole hierarchies treated uniformly | **Composite** | Permission trees, nested validation rules, expression trees. |
| Abstraction and implementation must vary independently | **Bridge** | Uncommon; usually over-applied. SLF4J is the canonical real example. |

### Behaviour

| Pressure | Pattern | Java-specific note |
|---|---|---|
| Algorithm must be chosen at runtime | **Strategy** | A lambda or a `Map<Key, Strategy>` is usually enough. Spring: inject `List<Strategy>` and dispatch on a `supports()` method. |
| Invariant steps with varying details | **Template Method** | Prefer composition — pass the varying step as a function. Inheritance-based template methods resist testing. |
| Interested parties must react to a state change | **Observer** | Spring `ApplicationEventPublisher` + `@EventListener` / `@TransactionalEventListener`. Watch ordering and transaction semantics. |
| Behaviour depends on a state machine with legal transitions | **State** | Model states as a sealed interface; transitions return the next state. Make illegal transitions uncompilable or explicit failures. |
| Request must be queued, logged, undone, or retried | **Command** | Pairs naturally with CQRS-style application services. |
| New operation needed over a closed type hierarchy | **Visitor** — or, in modern Java, **pattern matching over a sealed interface** | Sealed + exhaustive `switch` gives the same safety with far less ceremony. Prefer it. |
| Traversal independent of structure | **Iterator** | Already in the language. Implement `Iterable`; do not reinvent. |
| Several handlers, first applicable one wins | **Chain of Responsibility** | Servlet filters, Spring Security filter chain. |

Two notes on applying GoF in modern Java: lambdas and method references collapse most single-method pattern classes (Strategy, Command, Template Method, Observer) into functions — use them. And sealed interfaces plus pattern matching have made Visitor and much of State far cheaper than the 1994 formulations.

## Effective Java: the items that change code most

Joshua Bloch's items, condensed to the ones that most often improve real code:

- **Static factories over constructors** — they can be named, can cache, and can return subtypes.
- **Builder for many parameters** — telescoping constructors and `setX()`-then-use are both worse.
- **Prefer dependency injection to hardwiring resources** — the testability argument in one item.
- **Minimise mutability** — make the class immutable unless you have a reason; then make fields `final` and don't publish internal references.
- **Favour composition over inheritance** — inheritance across package boundaries is fragile; `extends` is a promise about the superclass's internals.
- **Design for inheritance or prohibit it** — classes are `final` by default unless you documented self-use patterns.
- **Prefer interfaces to abstract classes** — with default methods, the reasons to use abstract classes have narrowed to shared state.
- **Use generics; don't use raw types** — and prefer `List<? extends T>` parameters (PECS: producer-extends, consumer-super).
- **Return empty collections, not null.**
- **Use `Optional` as a return type sparingly and never as a field or parameter.**
- **Obey the `equals`/`hashCode` contract** — or let `record` do it. Never write `equals` without `hashCode`.
- **Override `toString`** — it goes in every log line and failure message.
- **Prefer try-with-resources to try-finally** — correct suppression handling, no leaked close.
- **Use exceptions only for exceptional conditions**; prefer standard exceptions; include failure-capture information in the message.
- **Prefer `java.util.concurrent` to `wait`/`notify`**; document thread safety; avoid excessive synchronisation.
- **Prefer enums to int constants**; use `EnumMap`/`EnumSet` over ordinals.
- **Avoid unnecessary object creation** — but do not sacrifice clarity for allocation you have not measured.
- **Minimise the accessibility of classes and members** — package-private is underused in Java; most implementation classes should not be `public`.

## Clean / hexagonal architecture in a Java project

The one rule that matters: **source-code dependencies point inward, toward policy.** The domain knows nothing about Spring, JPA, HTTP, or Kafka.

A layout that holds up in practice — package by feature at the top level, by layer underneath:

```
com.acme.billing                  ← feature / bounded context
├── domain/                        ← no framework imports at all
│   ├── Invoice.java               (aggregate; invariants enforced in constructor)
│   ├── Money.java                 (value object)
│   ├── InvoiceStatus.java         (sealed interface or enum)
│   └── port/
│       ├── InvoiceRepository.java (interface, defined by domain's needs)
│       └── PaymentGateway.java
├── application/                   ← use cases; orchestration; @Transactional lives here
│   ├── IssueInvoiceUseCase.java
│   └── command/IssueInvoiceCommand.java
└── infrastructure/                ← everything framework-shaped
    ├── web/InvoiceController.java      (DTOs + mapping, no business logic)
    ├── persistence/JpaInvoiceRepository.java + InvoiceEntity.java
    └── messaging/KafkaInvoiceEventPublisher.java
```

Why package-by-feature on the outside: changes arrive by feature, not by layer. A `controllers/` package containing forty unrelated controllers means every feature change touches four distant directories, and nothing can ever be package-private.

Rules that keep this honest:
- **The domain has no framework imports.** Enforce it with ArchUnit (`references/testing.md`) rather than discipline — discipline erodes.
- **Keep persistence entities separate from domain aggregates** when the domain has real invariants. JPA's demands (no-arg constructor, mutable fields, lazy proxies) corrupt a domain model. For CRUD-shaped features with no invariants, one class is fine and the mapping layer is pure cost — be honest about which kind of feature you have.
- **DTOs at the edge, always.** Never serialise a domain object or an entity straight to JSON: it couples your wire contract to your schema and silently leaks fields.
- **Transactions belong to the use case.** One transaction per use case, started in the application layer.

### When not to do this

A three-endpoint CRUD service does not need ports, adapters, and a mapping layer; it needs a controller, a repository, and tests. Apply the full structure when there is real domain logic, multiple integrations, or a long-lived codebase with many hands. Say which situation you think you are in when you choose.

## Domain modelling with records and sealed types

Make illegal states unrepresentable — the cheapest correctness technique in Java.

```java
// Value object: validated once, immutable forever.
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        if (amount.scale() > currency.getDefaultFractionDigits()) {
            throw new IllegalArgumentException("Scale exceeds currency precision: " + amount);
        }
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch: %s vs %s".formatted(currency, other.currency));
        }
    }
}
```

The compact constructor is the single place validation can be bypassed — there isn't one. Every `Money` in the system is valid by construction.

```java
// Closed set of outcomes: the compiler enforces that callers handle every case.
public sealed interface PaymentResult {
    record Settled(String receiptId, Money charged) implements PaymentResult {}
    record Declined(DeclineReason reason) implements PaymentResult {}
    record RequiresAction(URI challengeUrl) implements PaymentResult {}
}

String describe(PaymentResult result) {
    return switch (result) {                       // no default needed — exhaustive
        case Settled(var id, var charged) -> "Charged %s, receipt %s".formatted(charged, id);
        case Declined(var reason)         -> "Declined: " + reason;
        case RequiresAction(var url)      -> "Action required at " + url;
    };
}
```

Adding a fourth variant breaks every `switch` at compile time — which is exactly what you want, instead of a silent `default` branch doing the wrong thing in production. This is the modern replacement for both Visitor and result-code-plus-nullable-fields designs.

Use a sealed result type instead of exceptions when the alternative outcomes are **expected business outcomes** (declined, out of stock, needs 2FA). Keep exceptions for genuinely exceptional conditions. Encoding expected outcomes as exceptions makes control flow invisible and slow.

## Refactoring moves worth knowing by name

Fowler's catalogue, as applied to the situations that come up constantly. Naming the move makes the change reviewable:

- **Extract Method / Extract Class** — the two workhorses. Extract when a block has a name.
- **Replace Conditional with Polymorphism** — or, in modern Java, with a sealed hierarchy and exhaustive switch.
- **Introduce Parameter Object** — three parameters that always travel together are a concept you have not named. Make it a record.
- **Replace Primitive with Value Object** — `String customerId` everywhere invites passing an order ID. `record CustomerId(String value)` makes that a compile error.
- **Replace Temp with Query**, **Inline Variable**, **Rename** — cheap, high-yield, do them constantly.
- **Encapsulate Collection** — expose `List<Item> items()` as unmodifiable plus `addItem()`, so invariants can be enforced.
- **Replace Nested Conditional with Guard Clauses** — early return flattens code and removes the `else` cliff.
- **Separate Query from Modifier** — a method that both returns data and mutates state cannot be reasoned about or safely retried.

Refactor under green tests, in small commits, one move at a time. Behaviour-preserving changes and behaviour changes do not belong in the same commit — when something breaks, nobody can tell which half did it.

If the code you need to restructure has no tests, or the change is too large for one commit, that is a different problem: see `refactoring.md` for seams, characterisation tests, and the expand/migrate/contract and strangler-fig patterns.

## Smells and what they actually indicate

| Smell | What it usually means |
|---|---|
| Long method | Multiple levels of abstraction mixed; extract named steps |
| Long parameter list | A missing parameter object, or the method does too much |
| Feature envy (method uses another object's data constantly) | Behaviour is on the wrong class — move it to the data |
| Anemic domain model (all getters/setters, logic in services) | Procedural code wearing OO clothes; push invariants into the aggregate |
| Primitive obsession (`String`, `long` for domain concepts) | Missing value objects |
| Shotgun surgery (one change touches many files) | Wrong seams; knowledge is scattered |
| Divergent change (one file changes for many reasons) | SRP violation; split by axis of change |
| `instanceof` chains | Missing polymorphism or a sealed hierarchy |
| Boolean parameter | The method is two methods |
| Static utility holding mutable state | Hidden global; a testability and concurrency bug waiting |
| `Util`/`Helper`/`Manager` class names | No identified concept — the name admits it |
| Deep inheritance (3+ levels) | Composition was the answer |
| Comment explaining what the code does | The code needs renaming, not annotating |
