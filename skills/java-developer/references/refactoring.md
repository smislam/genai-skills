# Refactoring

Read this before changing the shape of existing code — especially code without tests. `design.md` tells you *what* structure to aim for and names the Fowler moves; this file is about how to get there safely on code you did not write and cannot fully trust.

## Contents
- [The one rule](#the-one-rule)
- [Before you start](#before-you-start)
- [No tests? Characterization tests first](#no-tests-characterization-tests-first)
- [Seams](#seams)
- [Breaking dependencies](#breaking-dependencies)
- [Getting legacy code under test](#getting-legacy-code-under-test)
- [The safe loop](#the-safe-loop)
- [Large-scale change](#large-scale-change)
- [Changing a published API](#changing-a-published-api)
- [Changing a database schema](#changing-a-database-schema)
- [Order of attack on a legacy Java service](#order-of-attack-on-a-legacy-java-service)
- [Reporting what you find](#reporting-what-you-find)
- [When not to refactor](#when-not-to-refactor)
- [Anti-patterns](#anti-patterns)

## The one rule

**Refactoring preserves behavior. If behavior changes, it is not a refactor** — it is a change, and it belongs in a different commit.

This sounds pedantic until the first production incident after a large "cleanup" PR, when nobody can tell which hunk altered the output. Keeping the two separate is what makes a refactor reviewable at a glance and revertable without losing the fix:

```
commit 1: extract SettlementCalculator from InvoiceService   (no behavior change)
commit 2: fix rounding in SettlementCalculator               (behavior change, with a test)
```

A reviewer can read commit 1 quickly because they only have to ask "is this the same?", and read commit 2 carefully because it is three lines.

## Before you start

Three questions, in order:

1. **Why am I refactoring?** Valid answers: I need to add a feature and the current shape blocks it; there is a bug I cannot find in this mess; this code changes often and costs too much each time. Invalid answer: it is not how I would have written it. Refactoring uncoupled from a real need is unpaid risk.
2. **What is my safety net?** Tests you have actually run, not tests that exist. If the answer is "none", that is your first task — see below.
3. **How do I keep this small?** A refactor you cannot finish and merge this week will be abandoned half-done, which leaves the codebase worse than when you started: two conventions instead of one.

Scope it to the code you need to change, plus the minimum around it. Leaving the rest alone is a feature.

## No tests? Characterization tests first

A characterization test does not assert what the code *should* do — it pins down what it *currently* does, including the bugs. It is a vice, not a specification. Michael Feathers' technique, and the only honest way to refactor untested code:

```java
@Test
void characterise_discountedTotal_goldTier() {
    var orders = List.of(order("A", "100.00"), order("B", "50.00"));

    var actual = service.calculateDiscountedTotal(orders, "GOLD");

    // Not "the right answer" — the answer it gives today. Verified by running it.
    assertThat(actual).isEqualByComparingTo("135.00");
}
```

How to write them when you have no idea what the code does:

1. Write the test with a deliberately wrong expectation.
2. Run it. The failure message tells you the actual value.
3. Paste the actual value in as the expectation.
4. Repeat for each interesting input class — boundaries, nulls, empty collections, the weird enum value.

Then label them clearly (`CharacterizationTest`, or a comment) so nobody later mistakes a pinned bug for intended behavior. **If a characterization test captures something clearly wrong, say so in your summary** — do not silently fix it inside a refactor, and do not silently preserve it without mentioning it.

Aim coverage at the *seams you are about to move*, not at a percentage. Five tests around the method you are extracting are worth more than sixty on getters.

## Seams

A seam is a place you can change behavior without editing the code at that location. You need one to get a test around legacy code, and finding it is the whole skill.

In Java the practical seams are:

- **Object seam (by far the most useful):** the code calls a method on an object you can substitute. Created by taking the collaborator as a constructor parameter instead of constructing it inline, or by extracting an interface over a concrete dependency.
- **Parameter seam:** the value is passed in, so a test can pass something else. `Clock`, `Random`, and `Supplier<Instant>` are the common wins.
- **Subclass-and-override seam:** make the awkward method `protected`, subclass it in the test, and override it. Ugly, effective, and temporary — use it to get the test green, then do the real extraction.
- **Build/classpath seam:** a different implementation on the test classpath. A last resort; it hides what is happening.

```java
// No seam: the dependency is welded in, and the clock makes the result untestable.
public class ReportService {
    private final SmtpMailer mailer = new SmtpMailer("smtp.prod.internal");
    public Report run() { ... LocalDate.now() ... }
}

// Object seam + parameter seam, and the class is now testable without changing a line of its logic.
public class ReportService {
    private final Mailer mailer;      // interface extracted over SmtpMailer
    private final Clock clock;
    public ReportService(Mailer mailer, Clock clock) { ... }
    public Report run() { ... LocalDate.now(clock) ... }
}
```

Note that the first move in almost every legacy Java cleanup is the same: **turn `new` in a field initializer into a constructor parameter.** It unlocks everything else.

## Breaking dependencies

The specific things that make Java classes untestable, and the fix for each:

| Blocker | Why it blocks | Fix |
|---|---|---|
| `new Dependency()` inside the class | Cannot substitute | Constructor parameter |
| `static` utility doing I/O | Cannot stub | Wrap in an instance method behind an interface, inject it |
| Hidden singleton (`Registry.getInstance()`) | Global state leaks between tests | Inject the instance; add a package-private reset only as a stopgap |
| `LocalDate.now()` / `new Random()` | Non-deterministic | Inject `Clock` / seeded `Random` |
| Work in the constructor (I/O, thread start) | Cannot construct in a test | Move to an `init`/factory method; never start threads in a constructor |
| Static initializer with side effects | Runs on class load, unavoidable | Move into a method; this one often forces the extraction |
| `final` class / `private` method you must stub | Cannot subclass | Extract the logic into a new injectable collaborator |
| God class with 40 fields | Cannot construct without everything | Sprout the new logic into its own class instead (below) |

Reach for `mockStatic` or deep reflection only to get an initial test green, and treat it as debt with a removal plan — a test that needs bytecode tricks is telling you about the design (`testing.md`).

## Getting legacy code under test

Feathers' moves, in the order you will actually want them:

- **Sprout Method** — new behavior goes into a new, well-named, testable method called from the old mess. The old code stays ugly; the new code is clean and tested. This is the highest-value move in the catalog and the right default when you are adding a feature under deadline.
- **Sprout Class** — same idea when the new logic needs its own state or the host class is already a god class. Lets you write proper unit tests immediately without untangling anything.
- **Wrap Method** — rename the original, create a new method with the old name that calls it plus your addition. Adds behavior without touching the original body.
- **Wrap Class** (decorator) — put the new behavior in a class implementing the same interface and delegate. Good for logging, metrics, retries, authorization.
- **Extract and Override Call** — replace a hard-coded call with a `protected` method, override it in a test subclass. Scaffolding, not a destination.
- **Parameterize Constructor** — add a constructor that takes the dependency, keep the old one delegating with the production default. Zero call-site churn, instant testability.
- **Extract Interface** — over a concrete third-party or infrastructure class, so you can substitute it and so the dependency arrow points the right way (`design.md`).

The common thread: **do not untangle the whole class to add one feature.** Carve out a tested island, then grow it on subsequent visits.

## The safe loop

1. **Run the tests.** Green before you start, or you will not know what you broke.
2. **One mechanical move.** Rename, extract, inline — one kind at a time.
3. **Prefer the IDE's automated refactoring** over hand-editing. Extract Method, Rename, Change Signature, Introduce Parameter are behavior-preserving by construction; a manual version of the same edit is where typos and missed call sites live.
4. **Compile and run the tests.** Immediately.
5. **Commit.** Small enough that the message is one clause.
6. Repeat.

If step 4 goes red and you cannot see why within a couple of minutes, **revert and take a smaller step.** Debugging a half-finished refactor is the most expensive state to be in, and the sunk cost is one commit.

Keep formatting changes in their own commit (`build-quality.md`). A reformat mixed into a logic change makes the diff unreadable and hides the actual edit.

## Large-scale change

For anything too big for one commit, these four patterns keep the codebase working the whole way through:

**Parallel Change (expand → migrate → contract)** — the workhorse:
1. *Expand*: add the new thing alongside the old. Nothing uses it yet.
2. *Migrate*: move callers over one at a time, each its own commit.
3. *Contract*: delete the old thing once nothing references it.

Every step is independently releasable, which is what makes it safe. The failure mode is stopping after step 2 — track the contract step as real work, or you accumulate two of everything forever.

**Branch by Abstraction** — introduce an interface over the thing you are replacing, add the new implementation behind it, switch by configuration, remove the old one. Lets a months-long replacement live on the main branch instead of a doomed long-lived feature branch.

**Strangler Fig** — for replacing a whole subsystem or service. Put a facade in front, route one capability at a time to the new implementation, let the old one shrink until it is empty. Preferable to a rewrite because every increment delivers and you can stop at any point with value banked.

**Feature toggles** — decouple deploy from release so partially-migrated code can ship dark. Keep the number small and delete each toggle as soon as it has served; stale toggles multiply the paths you must reason about and are their own class of incident.

Avoid long-lived refactoring branches entirely. A branch that diverges for three weeks will cost more in merge conflicts than the refactor saved.

## Changing a published API

If anything outside your module calls it, you cannot just change it:

```java
@Deprecated(since = "2.4", forRemoval = true)
public List<Order> findOrders(String customerId, String fromDate) {
    return findOrders(customerId, LocalDate.parse(fromDate));   // delegate, do not duplicate
}

public List<Order> findOrders(String customerId, LocalDate from) { ... }
```

Overload, delegate, deprecate with `since` and `forRemoval`, and point at the replacement in Javadoc (`@deprecated use {@link #findOrders(String, LocalDate)}`). Remove it a release later, once you can show nothing calls it.

**When a signature change is unavoidable, say so explicitly in your summary** — list the call-site changes consumers must make. A silently breaking change in a "refactor" commit is how downstream teams lose a morning.

## Changing a database schema

Schema changes follow the same expand/contract shape, and the constraint is that old and new application versions run simultaneously during a rolling deploy:

1. **Expand**: add the new nullable column or new table. Deploy. Old code ignores it.
2. **Backfill**: populate it, in batches, idempotently.
3. **Dual-write**: new code writes both old and new. Deploy.
4. **Switch reads** to the new column. Deploy.
5. **Contract**: stop writing the old column, then drop it. Separate migration, separate deploy.

Never rename or drop a column in the same release that stops using it, and never make a column `NOT NULL` in the same migration that adds it to a populated table. All of it goes through Flyway/Liquibase with `ddl-auto=validate` (`spring-boot.md`). Test migrations against the real engine via Testcontainers — H2 will accept DDL that Postgres rejects (`testing.md`).

## Order of attack on a legacy Java service

When handed something old and asked to modernize it, this sequence gets value early and keeps risk low. It assumes you are already running on a supported Java version (`migration.md` handles the version hops, which come first):

1. **Characterization tests** on the paths you are about to touch. Everything below depends on this.
2. **Constructor injection** — mechanical, enables all later testing.
3. **`Date`/`Calendar`/`SimpleDateFormat` → `java.time`**, injecting `Clock`. Highest bug-reduction per line, and shared `SimpleDateFormat` is an active data-corruption risk.
4. **String-concatenated SQL → bound parameters.** Do this as a security fix with its own commit and ticket, not folded into a cleanup (`security.md`).
5. **`double` money → `BigDecimal`** or minor-unit longs.
6. **Mutable POJOs → records** for data carriers.
7. **Exception handling**: remove swallowed exceptions and null-on-error returns. This changes behavior — separate commits, and tell the user that callers who relied on `null` must change.
8. **Stringly-typed values → enums or sealed types.**
9. **`instanceof` ladders → sealed interface + exhaustive switch.**
10. **Raw threads/pools → virtual threads**, after auditing for pinning (`concurrency.md`).
11. **Add the static-analysis gate**, baselined so existing violations do not block the build (`build-quality.md`).

Let test coverage lead: refactor what you have tests for, add tests before refactoring what you do not.

## Reporting what you find

A refactor is also a review. While you are in there you will notice defects you did not set out to fix — a resource leak, a missing `setScale`, an unguarded cache. **Name every one of them in your summary, even the ones your rewrite incidentally fixes.**

This matters more than it sounds. If your new `JdbcClient` code happens to close resources that the old code leaked, and you never mention the leak, the user learns nothing: they cannot check whether the same bug exists in the other six classes written in that style, and they cannot judge the severity of what was happening in production. Silently fixing a bug is strictly worse than reporting it and fixing it.

Separate the list into *fixed by this change*, *found but out of scope* (with a one-line risk note), and *behavior that deliberately changed*. That is what makes the PR reviewable and the handover honest.

## When not to refactor

- **Code that works and nobody touches.** Churn risk with no payoff. Ugly and stable beats clean and freshly broken.
- **Right before a release.** Land it after the cut.
- **With no tests and no time to write them.** Sprout the new behavior instead and leave the mess alone.
- **As a side effect of a bug fix.** The fix should be reviewable in isolation, and reverting it should not revert a restructuring.
- **Because of a style disagreement.** Match the local convention; raise the convention separately (`SKILL.md`).

And the rewrite question: a full rewrite is almost always the wrong call, because the old system encodes years of undocumented edge cases you will rediscover in production. Strangler Fig gets you the same destination with working software at every step. Reserve rewrites for genuinely small components, or a platform change that makes incremental migration impossible — and say plainly what will be lost.

## Anti-patterns

| Anti-pattern | Why it hurts |
|---|---|
| Behavior change inside a "refactor" commit | Nobody can tell which hunk broke production |
| Reformat mixed with logic change | The real edit is invisible in the diff |
| Refactoring without running tests | You are editing blind and will not find out for weeks |
| Big-bang rewrite on a long-lived branch | Merge hell; usually abandoned |
| Expand and migrate, never contract | Two of everything, permanently |
| Extracting an abstraction for one caller | Speculative generality; a wrong abstraction costs more than a missing one (`design.md`) |
| Chasing a coverage number instead of the seams | Tested getters, untested branches |
| Characterization test mistaken for a spec | Pinned bugs become "intended behavior" |
| Silently preserving a bug you noticed | The user cannot assess or find the others |
| Silently fixing a bug you noticed | Same problem, plus an unexplained behavior change |
| Renaming across a whole module in one commit | Unreviewable; conflicts with everyone |
| `mockStatic` as a permanent solution | Freezes the untestable design in place |
