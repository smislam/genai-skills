# Clean Code

Robert C. Martin's *Clean Code: A Handbook of Agile Software Craftsmanship* (2008) is the reference for this file: what makes code easy to read, change, and trust. Apply these principles to every piece of code you write or review in this skill, alongside the quality bar in `SKILL.md`.

The book's examples are Java from 2008. Apply its *principles* with modern Java: records, `Optional`, sealed types, streams, `java.time`. Where its advice conflicts with this skill's other guidance or current tooling, "Applying it with judgment" (the last section) says which wins.

Martin's working definition of clean code: it reads like well-written prose, does one thing well, has no surprises, and looks like it was written by someone who cared. The practical test: **could a competent teammate change this code safely next month without asking you?**

## Contents
- [Meaningful names](#meaningful-names)
- [Functions](#functions)
- [Comments](#comments)
- [Formatting](#formatting)
- [Objects and data structures](#objects-and-data-structures)
- [Error handling](#error-handling)
- [Boundaries](#boundaries)
- [Unit tests](#unit-tests)
- [Classes](#classes)
- [Emergent design: the four rules of simple design](#emergent-design-the-four-rules-of-simple-design)
- [Concurrency](#concurrency)
- [Smells and heuristics](#smells-and-heuristics)
- [The Boy Scout Rule](#the-boy-scout-rule)
- [Applying it with judgment](#applying-it-with-judgment)

## Meaningful names

- **Reveal intent.** A name says why something exists, what it does, and how it's used. If a name needs a comment, it's the wrong name: `int d; // elapsed days` → `int elapsedDays`.
- **Avoid disinformation.** Don't call something `accountList` unless it's a `List`; don't use names that differ only slightly (`XYZControllerForEfficientHandlingOfStrings` vs `XYZControllerForEfficientStorageOfStrings`); avoid `l` and `O` as names.
- **Make meaningful distinctions.** `getActiveAccount()`, `getActiveAccounts()`, and `getActiveAccountInfo()` side by side tell the reader nothing. Noise words (`Info`, `Data`, `Object`, `Manager`, `Processor`) usually mean the concept hasn't been named yet.
- **Pronounceable and searchable.** `generationTimestamp`, not `genymdhms`. Single-letter names only for tiny scopes (a loop index in a three-line loop); the length of a name should match the size of its scope.
- **No encodings.** No Hungarian notation, no `m_` prefixes, and no `I` prefix on interfaces (`OrderRepository`, with an implementation named for how it differs: `JdbcOrderRepository`).
- **Classes are nouns, methods are verbs:** `Invoice`, `PaymentPolicy`; `calculateTotal()`, `cancel()`, `isOverdue()`. Use the JavaBean `get`/`set`/`is` conventions only where a framework needs them; records already give `total()`.
- **One word per concept.** Don't mix `fetch`, `retrieve`, and `get` for the same idea across classes.
- **Use the domain's language** (ubiquitous language): if the business says "policy holder", the code says `PolicyHolder`, not `Customer2`. Use solution-domain names (`Visitor`, `Queue`) for technical concepts.
- **Add context through structure,** not prefixes: `Address.state` beats a loose `addrState`.

## Functions

- **Small, and doing one thing.** A function does one thing if you can't meaningfully extract another function from it with a name that isn't a restatement of its implementation. Size follows: most functions fit on a screen with room to spare.
- **One level of abstraction per function.** Don't mix `orderService.place(order)` with string manipulation on the next line. Read top-down, like a newspaper: high-level steps first, details in the functions below (the step-down rule).
- **Switch statements** belong in one place, typically a factory or a sealed hierarchy handled with an exhaustive `switch` expression, not repeated across the codebase. Modern Java's sealed interfaces with pattern-matching `switch` make this safe (`design.md`).
- **Few arguments.** Zero is ideal, one or two are fine, three need a reason, and more mean a missing concept: introduce a parameter object (often a record). Arguments make functions harder to read and to test.
- **No flag arguments.** `render(true)` says nothing at the call site. Split it into `renderForPrint()` and `renderForScreen()`.
- **No output arguments.** A function that changes its argument surprises the caller. Change the object's own state (`report.appendFooter()`), or return a new value.
- **No hidden side effects.** `checkPassword()` must not also start a session. Name the side effect, or move it.
- **Command–query separation.** A function either changes state or answers a question, not both. `if (set("username", "bob"))` is ambiguous; separate `exists()` from `set()`.
- **Prefer exceptions to error codes,** and extract `try`/`catch` bodies into their own functions: error handling is "one thing".
- **Don't repeat yourself.** Duplication is the root of many maintenance bugs. Remove duplicated *knowledge*, though, not code that merely looks alike (`design.md`, "DRY, KISS, YAGNI").

## Comments

The best comment is the one you didn't need, because the code says it. Comments lie as code changes around them. But some comments are essential.

**Good comments:**
- **Why, not what:** the business reason, the constraint, the decision. "Sorted by ID because the downstream report relies on stable order."
- **Warnings of consequences:** "Not thread-safe: `SimpleDateFormat` is shared."
- **Legal headers** where required.
- **Clarification of something you can't change** (an odd third-party API, a regulatory rule).
- **`TODO`s with a ticket reference.** A `TODO` without one is a wish.
- **Javadoc on public APIs** (published libraries, module boundaries): contracts, units, nullability, thread safety.

**Bad comments:**
- **Redundant ones** that restate the code (`// increment i`).
- **Misleading or obsolete ones.**
- **Mandated Javadoc on every getter.**
- **Journal comments, change logs, and attributions in the file:** git has the history.
- **Position markers and closing-brace comments:** a sign the function is too long.
- **Commented-out code.** Delete it; git remembers. Nobody dares remove it later, so it rots.
- **HTML in comments, and non-local information** (describing code somewhere else).

## Formatting

- **Formatting is communication,** and the team's rules beat personal style. Enforce them with the formatter (Spotless with google-java-format or Palantir, per `build-quality.md`), so formatting is never a review topic.
- **Vertical openness:** blank lines separate concepts; related lines stay together.
- **Vertical density and distance:**
  - declare variables close to their use;
  - put instance variables at the top of the class;
  - keep a caller above its callee;
  - keep conceptually related functions near each other.
- **Horizontal:** short lines (the formatter's limit), with spacing that shows precedence. Don't align declarations in columns; it highlights the wrong thing and breaks on every change.
- **Files:** small enough to understand; the class name says what's inside.

## Objects and data structures

- **Objects hide their data and expose behavior; data structures expose data and have no behavior.** Choose deliberately:
  - objects make adding new types easy;
  - data structures, with functions over them, make adding new operations easy.
- **In modern Java,** records are data structures, and that's fine for DTOs, events, and value objects. Domain entities with invariants are objects: no public setters that let callers break the rules.
- **Law of Demeter:** a method talks to its friends, not strangers. `order.getCustomer().getAddress().getCity()` (a "train wreck") couples you to three classes' internals. Ask the object to do the work (`order.shippingCity()`), or pass what's actually needed. Fluent builders and stream pipelines aren't violations: they return the same kind of object, not strangers.
- **No hybrids:** half object, half data structure (public fields *and* business methods) is the worst of both.

## Error handling

- **Use exceptions, not return codes.** Error codes force immediate checks and clutter the happy path.
- **Write the `try`/`catch`/`finally` first** when code can fail. It defines the scope, and what state remains after a failure.
- **Use unchecked exceptions** for most application code. Checked exceptions break encapsulation up the call chain. (This matches `SKILL.md`: domain exceptions, with the cause preserved.)
- **Give context:** the operation that failed, and the offending value.
- **Define exception classes by how callers handle them,** not by where they came from. Wrap a third-party API's exceptions in one domain exception at the boundary.
- **The special case pattern:** return an object that handles the special case (an empty list, a `NullObject`, `Optional.empty()`) instead of forcing callers to check.
- **Don't return null; don't pass null.** Return `Optional` or an empty collection; validate inputs at the boundary (`SKILL.md`).

## Boundaries

- **Wrap third-party APIs** that you use in a limited way, behind your own interface. Don't pass `Map<String, Object>` or a vendor SDK type around the codebase. This keeps the dependency replaceable and its quirks in one place (`design.md`, ports and adapters).
- **Learning tests:** when adopting a third-party library, write small tests that pin how you use it. They document it, and tell you immediately when an upgrade changes its behavior.
- **Code against an interface for things that don't exist yet** (an API another team is still building), and adapt it when the real thing arrives.

## Unit tests

- **The three laws of TDD:**
  1. write no production code until you have a failing test;
  2. write only enough of a test to fail;
  3. write only enough production code to pass.

  Use TDD where it fits (`testing.md`); the point is that tests and code grow together.
- **Keep tests as clean as production code.** Dirty tests are a liability: they slow every change, and get deleted.
- **One concept per test,** with an arrange / act / assert structure and a name that states the behavior (`rejectsTransferWhenBalanceIsInsufficient`).
- **F.I.R.S.T.:**
  - **Fast:** slow tests don't get run.
  - **Independent:** no test depends on another's state or order.
  - **Repeatable:** the same result in any environment (no wall clock, no shared external state).
  - **Self-validating:** pass or fail, with no reading of logs.
  - **Timely:** written with the code, not afterwards.
- **A domain-specific testing language:** builders and helpers (`anOrder().withItems(3).build()`) make tests read like the specification.

## Classes

- **Organization:** constants, then fields, then constructors, then public methods, each followed by the private helpers it uses.
- **Small, measured by responsibilities, not lines.** You should be able to describe a class in about 25 words without "and", "or", "but", or "if". The name says it: a vague name (`Manager`, `Processor`, `Super…`) suggests too many responsibilities.
- **Single Responsibility Principle:** one reason to change (`design.md`).
- **Cohesion:** methods use most of the class's fields. When a subset of fields serves a subset of methods, there's a class trying to get out.
- **Organize for change** (the Open/Closed Principle): new behavior arrives as new classes, not edits spread across many.
- **Depend on abstractions at boundaries** (Dependency Inversion), with constructor injection (`SKILL.md`).

## Emergent design: the four rules of simple design

Kent Beck's rules, in priority order, as Martin presents them. Code is simple when it:
1. **Runs all the tests:** it's verifiably correct, and the design is testable.
2. **Contains no duplication.**
3. **Expresses the programmer's intent:** good names, small functions, standard patterns named as such.
4. **Minimizes the number of classes and methods.** This is the lowest priority, as a check against dogmatism: don't create an interface for every class.

## Concurrency

- **Keep concurrency code separate** from business logic (Single Responsibility).
- **Limit the scope of shared data;** prefer copies and immutable values.
- **Keep threads as independent as possible.**
- **Know the library:** `java.util.concurrent`, executors, virtual threads, and structured concurrency (`concurrency.md`).
- **Keep synchronized sections small.**
- **Test concurrency deliberately:**
  - make the threading configurable;
  - run with more threads than processors;
  - treat spurious failures as real bugs, not "one-offs".

## Smells and heuristics

The book's final chapter catalogs smells. These are the ones that matter most in review, grouped by its categories:

| Category | Smell | Fix |
|---|---|---|
| Comments | Obsolete, redundant, or commented-out code | Delete; let names and git carry the information |
| Environment | Building or testing needs more than one step | One command: `mvn verify` or `./gradlew build` |
| Functions | Too many arguments, output arguments, flag arguments, dead functions | Parameter objects; return values; split by flag; delete |
| General | Duplication | Extract the shared knowledge (template method, strategy, or a function) |
| General | Code at the wrong level of abstraction | Move details down; keep high-level policy free of low-level detail |
| General | Feature envy (a method more interested in another class's data) | Move the method to the data |
| General | Magic numbers and strings | Named constants, or enums |
| General | Hidden temporal coupling (calls that must happen in an order the API doesn't enforce) | Make each step return what the next needs |
| General | Inconsistency, and clutter (unused variables, empty constructors, meaningless comments) | Follow one convention; remove clutter |
| General | Selector arguments, obscured intent, misplaced responsibility | Split functions; name things; move code to where readers expect it |
| General | Encapsulate conditionals | `if (shouldBeDeleted(timer))`, not `if (timer.hasExpired() && !timer.isRecurrent())` |
| General | Avoid negative conditionals | `if (buffer.shouldCompact())`, not `if (!buffer.shouldNotCompact())` |
| General | Functions should do one thing; descend only one level of abstraction | Extract |
| Java | Long import lists; inheriting constants; constants vs enums | The formatter's import rule; constants in a holder or enum, not via an interface; enums for fixed sets |
| Names | Non-descriptive names, names at the wrong level, unambiguous names, side effects hidden by names | Rename to match the abstraction and effects |
| Tests | Insufficient tests; skipped trivial tests; untested boundaries; ignored failing tests; slow tests | Test boundary conditions exhaustively; fix or delete ignored tests; keep the suite fast |

`design.md`, "Smells and what they actually indicate", covers the design-level smells (shotgun surgery, divergent change, primitive obsession) and the refactorings that fix them.

## The Boy Scout Rule

"Leave the campground cleaner than you found it." Each change leaves the code it touches a little better: a clearer name, a smaller function, a removed duplicate.

Keep it small and in scope: improvements to the code you're already changing, in separate commits from behavior changes (`refactoring.md`). Not a drive-by rewrite of the module.

## Applying it with judgment

The principles hold; some of the book's specifics are dated or conflict with this skill's guidance. Where they do, follow this list:

| Book's advice | In this skill |
|---|---|
| Functions of a handful of lines | Aim for one thing at one level of abstraction. Don't fragment a clear 25-line function into ten single-use helpers that the reader must jump between |
| Use wildcard imports to shorten import lists | Follow the project formatter (google-java-format and Palantir forbid wildcards). Never argue imports in review |
| Avoid comments | Avoid redundant comments, but keep Javadoc on public contracts, and comments explaining *why* |
| Getters and setters on data classes | Use records for data carriers. Entities expose behavior, not setters |
| Inheritance-based examples (the Template Method everywhere) | Prefer composition, and sealed interfaces where variation is closed (`design.md`) |
| Checked-exception discussions | Unchecked domain exceptions with the cause preserved, as `SKILL.md` says |
| Concurrency built on raw threads | `java.util.concurrent`, virtual threads, structured concurrency (`concurrency.md`) |

When clean-code advice and a project's established conventions conflict, follow the project. Raise the conflict separately, as `SKILL.md` says, rather than diverging silently in one file.
