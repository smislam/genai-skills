# Concurrency and threading

Read this before writing anything that involves a thread, an executor, shared mutable state, or async work. Concurrency defects are the most expensive class of bug in Java: they pass review, pass tests, and surface under production load.

## Contents
- [Decide the model first](#decide-the-model-first)
- [The Java memory model in practical terms](#the-java-memory-model-in-practical-terms)
- [Virtual threads](#virtual-threads)
- [Structured concurrency](#structured-concurrency)
- [ScopedValue vs ThreadLocal](#scopedvalue-vs-threadlocal)
- [Platform thread pools: sizing and shutdown](#platform-thread-pools-sizing-and-shutdown)
- [CompletableFuture](#completablefuture)
- [Choosing a synchronizer](#choosing-a-synchronizer)
- [Concurrent collections](#concurrent-collections)
- [Atomics and lock-free](#atomics-and-lock-free)
- [Interruption and cancellation](#interruption-and-cancellation)
- [Spring and async](#spring-and-async)
- [Reactive: when it is still the right call](#reactive-when-it-is-still-the-right-call)
- [Backpressure, rate limiting, bulkheads](#backpressure-rate-limiting-bulkheads)
- [The bug catalogue](#the-bug-catalogue)
- [Documenting thread safety](#documenting-thread-safety)

## Decide the model first

Most "concurrency bugs" are really a missing decision. Pick one of these per component and write it down:

1. **No shared mutable state.** Immutable values passed between tasks. This is the default and the goal — it removes the bug class entirely rather than managing it.
2. **Single-writer.** One thread owns the state; others send it messages (a queue, an actor, a single-threaded executor). Removes locks without removing mutation.
3. **Confinement.** State lives inside one request/task and never escapes. Thread-per-request with virtual threads makes this natural.
4. **Guarded shared state.** Explicit locking with a documented lock order. Only when the above do not fit, and only with the smallest possible critical section.

Escalating from 1 to 4 should feel like a cost. If a code review cannot tell which model a class uses, that is the finding.

## The Java memory model in practical terms

You do not need the formal spec, but you do need these facts:

- **Without synchronisation, there is no guarantee another thread ever sees your write.** Not "it's delayed" — the JIT may hoist a non-volatile read out of a loop and spin forever on a stale value. This is why the "stop flag" bug below is real.
- **`volatile` gives visibility and ordering, not atomicity.** `volatile int i; i++` is still a lost-update race, because that is read-modify-write. Use `AtomicInteger`.
- **`final` fields are safe to publish** once the constructor completes, provided `this` did not escape during construction. Never start a thread or register a listener from a constructor — the object can be observed half-built.
- **Safe publication** requires one of: static initialiser, `volatile`/`AtomicReference` write, `final` field, or writes guarded by the same lock that readers acquire. Putting an object into a `ConcurrentHashMap` publishes it safely; putting it into a plain `HashMap` does not.
- **Double-checked locking without `volatile` is broken.** Just use a static holder class or an enum singleton.
- **64-bit non-volatile `long`/`double` reads can tear** on some platforms — another reason not to share unsynchronised primitives.

```java
// Broken: may never terminate, regardless of what the other thread writes.
private boolean running = true;
public void stop() { running = false; }
public void run() { while (running) { work(); } }   // read can be hoisted out of the loop

// Correct:
private volatile boolean running = true;
```

## Virtual threads

Final in **Java 21** (JEP 444). A virtual thread is a `Thread` scheduled by the JVM onto a small pool of carrier platform threads. When it blocks on most JDK I/O, it *unmounts* and frees the carrier. The consequence: blocking is no longer expensive, so you can write straightforward sequential code and still handle enormous concurrency.

```java
// One virtual thread per task. Unbounded in count, cheap to create.
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<Price>> futures = suppliers.stream()
        .map(s -> executor.submit(() -> s.fetchPrice(sku)))   // blocking HTTP, and that's fine
        .toList();
    // close() waits for all submitted tasks (ExecutorService is AutoCloseable since 19)
}
```

### What actually changes

- **Stop pooling threads for I/O.** A virtual thread is the task. Pooling them defeats the point and reintroduces the pool-size bottleneck. Create one per task.
- **Do keep bounding the *resource*, not the thread.** Unbounded virtual threads hitting a database with a 20-connection pool just moves the queue. Limit with a `Semaphore` around the scarce resource, or let the connection pool do it — but know where the bound is, because without one, overload moves from "requests queue" to "heap exhausts".
- **Thread-per-request frameworks become competitive with reactive again** for I/O-bound workloads, with far better debuggability: real stack traces, working step debuggers, meaningful thread dumps.

### The pitfalls that still bite

- **Pinning.** A virtual thread that cannot unmount blocks its carrier. Through Java 21–23, a `synchronized` block held across a blocking call pinned the carrier; **JEP 491 (Java 24) fixed `synchronized` pinning**. Two consequences: on the **Java 25** baseline, `synchronized` around blocking I/O no longer pins, so you do not need to rewrite it for virtual threads; but if the project is **on Java 21, replace `synchronized` with `ReentrantLock` around blocking I/O** — the single most important virtual-thread gotcha there. Native frames (JNI, some native-backed calls) still pin on every version. Diagnose with the `jdk.VirtualThreadPinned` JFR event (or `-Djdk.tracePinnedThreads=full` on 21).
- **Do not stop at "pinning" when the lock itself is the bottleneck.** A `synchronized` *instance method* on a singleton bean serialises on one monitor, so true concurrency through it is **1**, application-wide — queueing starts at the second concurrent request, regardless of how many carriers exist. Pinning compounds that but is not the whole story, and prescribing `ReentrantLock` while keeping one global lock around a network call fixes the carrier starvation and leaves the serialisation. Diagnose the lock scope first: what is actually being protected, and does it need to be held across the I/O at all? Usually the answer is a `ConcurrentHashMap` or a cache that needs no outer lock.
- **Enabling virtual threads removes backpressure you were relying on without knowing it.** A bounded Tomcat worker pool silently capped how many requests could pile onto a contended lock, a slow dependency, or an unbounded queue. Switch to virtual threads and that cap disappears, so latent contention that was invisible at 200 concurrent workers surfaces immediately at 20,000. A latency cliff right after enabling virtual threads is usually a pre-existing bottleneck being exposed, not a new one being created — look for the narrowest shared resource on the path and give it an explicit bound.
- **`ThreadLocal` becomes expensive at scale.** Fine for a few hundred platform threads; a million virtual threads each holding a cached buffer is a heap problem. Prefer `ScopedValue`. Also note thread-local-backed caches and pools (e.g. some `SimpleDateFormat` or buffer caches) lose their point entirely.
- **CPU-bound work does not benefit.** Virtual threads solve *blocking*, not throughput. For compute, use a bounded pool sized near `availableProcessors()`, or a `ForkJoinPool`. Running CPU-heavy tasks on virtual threads just starves carriers.
- **Monitoring changes.** Virtual threads are not in `ThreadMXBean`; thread-count dashboards go quiet. Use JFR events (`jdk.VirtualThreadStart`, `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed`).
- **`synchronized` for *short, non-blocking* critical sections is still fine** and cheap — do not rewrite every `synchronized` counter.

### Enabling in Spring Boot

```properties
spring.threads.virtual.enabled=true
```

That switches the web server's request handling, `@Async`, and scheduled tasks to virtual threads. Before enabling, audit for `ThreadLocal`-heavy libraries, `synchronized`-around-I/O (only if on Java 21–23), and thread-pool-based rate limiting that you were implicitly relying on for backpressure.

## Structured concurrency

The principle: if a task splits into subtasks, all subtasks must complete or be cancelled before the parent returns. This makes concurrent code behave like a single unit of work — errors propagate, cancellation propagates, and nothing leaks.

Status: still a **preview API** through Java 25 (JEP 505), and the API shape changed across versions — in Java 25 it is `StructuredTaskScope.open(...)` with joiners, not the earlier `new StructuredTaskScope.ShutdownOnFailure()`. Because of that churn, **do not use it in production code** on any version unless the team has accepted `--enable-preview`. Use the virtual-thread executor pattern above, which is final API and gives you most of the benefit.

```java
// Java 25 preview shape — fail-fast fan-out, both subtasks cancelled if either fails.
try (var scope = StructuredTaskScope.open(Joiner.<Object>allSuccessfulOrThrow())) {
    var user  = scope.fork(() -> userService.find(id));
    var order = scope.fork(() -> orderService.latestFor(id));
    scope.join();
    return new Dashboard(user.get(), order.get());
}
```

The pattern to carry away even without the API: **scope your fan-out**, propagate the first failure, cancel the rest, and never let a subtask outlive the request that started it. A `CompletableFuture` fan-out that keeps running after the caller gave up is the anti-pattern this exists to kill.

## ScopedValue vs ThreadLocal

`ScopedValue` (finalised in **Java 25**, JEP 506; preview before that) gives immutable, bounded-lifetime context that child structured tasks inherit — the right replacement for `ThreadLocal` in a virtual-thread world, because there is nothing to leak and nothing to clean up.

```java
private static final ScopedValue<TenantId> TENANT = ScopedValue.newInstance();

ScopedValue.where(TENANT, tenantId).run(() -> handleRequest(req));   // visible to callees, then gone
```

On the Java 25 baseline, use `ScopedValue` for new request-scoped context. On Java 21, `ThreadLocal` remains the practical choice — but always clear it in a `finally`. Either way, be aware that MDC/security-context propagation across threads needs explicit handling (`TaskDecorator` in Spring, `DelegatingSecurityContextExecutor`, Micrometer's `ContextSnapshot`).

## Platform thread pools: sizing and shutdown

Still relevant for CPU-bound work and when you deliberately want a bound.

```java
var executor = new ThreadPoolExecutor(
    cores, cores,                                  // CPU-bound: ~availableProcessors()
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(1_000),                // BOUNDED — see below
    Thread.ofPlatform().name("pricing-", 0).factory(),
    new ThreadPoolExecutor.AbortPolicy());          // fail fast rather than silently drop
```

- **Sizing:** CPU-bound ≈ number of cores. Blocking work on platform threads ≈ `cores × (1 + wait/compute)` — but if you are computing that ratio, virtual threads are the better answer.
- **Always bound the queue.** `Executors.newFixedThreadPool` uses an unbounded `LinkedBlockingQueue`: under overload it accumulates tasks until the heap dies, and latency grows without limit. A bounded queue plus an explicit rejection policy converts a slow death into a fast, visible failure.
- **Name your threads.** An unnamed `pool-3-thread-7` in a stack trace costs you minutes in an incident.
- **Shut down properly:** `shutdown()`, then `awaitTermination(timeout)`, then `shutdownNow()`, and re-interrupt if interrupted. Non-daemon pool threads keep the JVM alive on exit.
- **Watch out for `ForkJoinPool.commonPool()`** — parallel streams and the default `CompletableFuture.supplyAsync` share it. One blocking task in there stalls every parallel stream in the process. Never run blocking I/O on the common pool; pass an explicit executor.
- **Parallel streams** are only worth it for large, CPU-bound, splittable, side-effect-free work. For anything else they add overhead and hide the executor.

## CompletableFuture

Composable async without the callback nesting. Correctness depends on getting a few details right:

```java
CompletableFuture<Quote> quote = CompletableFuture
    .supplyAsync(() -> priceService.fetch(sku), ioExecutor)       // always pass an executor
    .thenApplyAsync(this::applyDiscount, cpuExecutor)
    .orTimeout(2, TimeUnit.SECONDS)                               // or completeOnTimeout(fallback, …)
    .exceptionally(ex -> Quote.unavailable(sku));                 // ex is a CompletionException — unwrap getCause()

CompletableFuture.allOf(a, b, c).join();                          // then read each; allOf returns Void
```

- Never call `get()`/`join()` on the thread that the stage will complete on — classic self-deadlock.
- `thenApply` may run on the completing thread; `thenApplyAsync` moves it. Be deliberate, especially where thread-locals or security context matter.
- An exception in a stage with no `exceptionally`/`handle`/`whenComplete` is **silently swallowed** until someone joins. Always terminate chains with error handling.
- `allOf` fails only when you inspect; `anyOf` gives no cancellation of the losers.
- With virtual threads available, a plain blocking call inside a virtual thread is usually simpler and more debuggable than a `CompletableFuture` chain. Reach for `CompletableFuture` when you need composition or timeouts across many stages.

## Choosing a synchronizer

| Need | Use |
|---|---|
| Mutual exclusion, short non-blocking section | `synchronized` |
| Mutual exclusion with timeout, tryLock, or fairness — or across blocking I/O if on Java 21 | `ReentrantLock` |
| Many readers, rare writers, contention measured | `ReadWriteLock` / `StampedLock` (optimistic reads; not reentrant) |
| Limit concurrent access to a scarce resource | `Semaphore` |
| Wait for N events to finish | `CountDownLatch` (one-shot) / `Phaser` (reusable) |
| All threads reach a point together | `CyclicBarrier` |
| Producer/consumer handoff | `BlockingQueue` (bounded!) / `TransferQueue` |
| Wait for a condition on guarded state | `Condition.await/signalAll` in a `while` loop |
| One-time initialisation | static holder class, or `enum` singleton |

Rules that prevent most locking bugs: hold locks for the shortest possible time; **never make a blocking or remote call while holding a lock**; acquire multiple locks in a globally consistent order (this is the entirety of deadlock avoidance); do not call out to unknown code (listeners, overridable methods) while holding a lock; and always wait in a `while (!condition)` loop because spurious wakeups are permitted.

## Concurrent collections

| Instead of | Use | Note |
|---|---|---|
| `Collections.synchronizedMap` | `ConcurrentHashMap` | Lock striping; `compute`/`merge`/`computeIfAbsent` are atomic |
| `synchronized` list of listeners | `CopyOnWriteArrayList` | Read-dominated only; every write copies |
| Hand-rolled wait/notify queue | `ArrayBlockingQueue` / `LinkedBlockingQueue(capacity)` | Bound it |
| Priority queue across threads | `PriorityBlockingQueue` | |
| Sorted concurrent map | `ConcurrentSkipListMap` | |
| Hand-rolled cache | Caffeine | Correct eviction, refresh, and stats; `ConcurrentHashMap` is not a cache |

Two traps. First, **compound operations are not atomic even on concurrent collections** — `if (!map.containsKey(k)) map.put(k, v)` is a race; use `putIfAbsent` or `computeIfAbsent`.

Second, and more dangerous because it looks like the idiomatic answer: **never put a blocking call inside `computeIfAbsent`.** It holds the map's per-bin lock for the entire duration of the mapping function, so a cache-miss that performs HTTP or JDBC I/O is *the same bug as `synchronized` around I/O*, just with a narrower scope — and on Java 21–23 it pins the carrier exactly the same way. This is the single most common way a correct-looking cache fix reintroduces the problem it was meant to solve. Noticing the hazard and shipping it anyway with a comment is not a trade-off; it is the bug.

```java
// WRONG: holds a bin lock across a network call.
return cache.computeIfAbsent(key, k -> client.fetch(k));

// Fine: lock is never held during I/O. Two threads may both fetch a cold key —
// usually acceptable, and the cost is one duplicate request, not a stalled carrier.
var hit = cache.get(key);
if (hit != null) return hit;
var fetched = client.fetch(key);
var existing = cache.putIfAbsent(key, fetched);
return existing != null ? existing : fetched;

// When duplicate fetches are genuinely unacceptable, make the VALUE the future and
// let late arrivals join the in-flight call. The mapping function returns immediately,
// so no lock is held during the fetch.
return cache.computeIfAbsent(key, k -> CompletableFuture.supplyAsync(() -> client.fetch(k), executor)).join();
```

Caffeine's `get(key, loader)` handles this correctly for you with per-key coalescing, which is one of the better reasons to use a real cache library rather than a `Map`.

Iteration semantics differ: `ConcurrentHashMap` iterators are weakly consistent (no `ConcurrentModificationException`, may miss concurrent updates), while a plain `HashMap` iterated during mutation can corrupt or loop forever.

## Atomics and lock-free

`AtomicInteger`/`AtomicLong`/`AtomicReference` for single-variable updates, using the CAS loop idiom:

```java
counter.updateAndGet(v -> Math.min(v + 1, max));          // retries internally
cache.compareAndSet(expected, replacement);
```

For high-contention counters use `LongAdder`/`DoubleAdder` — they trade read cost for striped writes and are dramatically faster than `AtomicLong` under contention. For a complex object that must change atomically, the easiest correct approach is an immutable object in an `AtomicReference` updated with `updateAndGet`.

Do not hand-write lock-free data structures. The existing ones are written by people who test with jcstress; yours will be subtly wrong under a memory model you did not fully internalise. `VarHandle` exists for the cases that genuinely need it, and those cases are rare.

## Interruption and cancellation

Interruption is cooperative. Code that ignores it produces tasks that cannot be cancelled and shutdowns that hang.

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();   // restore the flag you just cleared
    throw new TaskAbortedException("Aborted while awaiting work", e);
    // or: return, having restored the flag
}
```

- Catching `InterruptedException` **clears** the flag. Either propagate the exception or restore the flag — swallowing it breaks every cancellation path above you.
- In long loops, check `Thread.currentThread().isInterrupted()` and exit promptly.
- `Future.cancel(true)` interrupts; it does nothing for a task stuck in a non-interruptible call (a socket read without a timeout, a blocking native call). **Set timeouts on every network and database call** — a hung connection with no timeout is an unkillable thread.
- Never use `Thread.stop()` (removed) or `Thread.suspend()` (removed).

## Spring and async

- **`@Async`** returns `void` or `CompletableFuture`. It is proxy-based, so calling an `@Async` method from inside the same bean runs it synchronously — the same self-invocation trap as `@Transactional`. Configure an explicit `AsyncTaskExecutor`; the default on older versions was effectively unbounded.
- **`@Async` and transactions do not compose.** The new thread gets no transaction and no security context. Publish an event or pass the data, not an entity — a detached lazy proxy on another thread is a `LazyInitializationException` waiting to happen.
- **`@TransactionalEventListener(phase = AFTER_COMMIT)`** is the correct way to trigger side effects only if the transaction committed. A plain `@EventListener` runs inside the transaction, so an email gets sent and then the transaction rolls back.
- **Context propagation:** MDC, `SecurityContext`, and tracing do not cross threads automatically. Use a `TaskDecorator`, Micrometer's context propagation, or pass values explicitly.
- **`@Scheduled`** runs on a single-threaded scheduler by default — one slow job delays every other job. Configure a pool or virtual threads. In a multi-instance deployment, `@Scheduled` fires on every instance; use a distributed lock (ShedLock) or a leader election if the job must run once.

## Reactive: when it is still the right call

With virtual threads, the "concurrency" argument for WebFlux is largely gone for ordinary request/response services, and imperative code is far easier to debug and profile. Reactive still wins when you need:

- **Streaming and backpressure as first-class semantics** — server-sent events, long-lived streams, large result sets where the consumer must throttle the producer.
- **Rich operator composition over event streams** — windowing, buffering, debouncing, retry-with-backoff over a stream.
- **An existing fully reactive stack** — mixing paradigms is worse than either one. One blocking call in a reactive chain stalls an event-loop thread and degrades the whole service; if you must, isolate it on `Schedulers.boundedElastic()`.

Do not migrate a working reactive codebase on principle, and do not start a new one for throughput alone. Choose on semantics.

## Backpressure, rate limiting, bulkheads

Scaling concurrency without limiting it moves the failure instead of preventing it. Every system needs an answer to "what happens when demand exceeds capacity":

- **Bound every queue** so overload is visible as rejection, not as unbounded latency and heap growth.
- **Limit concurrency at the scarce resource** — a `Semaphore` sized to the downstream's capacity, or a connection pool. Let the limit be explicit and monitored.
- **Bulkhead** independent dependencies so a slow one cannot consume all capacity: separate pools/semaphores per downstream.
- **Timeouts everywhere**, shorter as you go deeper, so a caller's budget is never exceeded by a callee's retry.
- **Circuit breakers and retry with jitter** (Resilience4j). Retry without backoff and jitter turns a blip into a self-inflicted stampede; retry without idempotency turns it into duplicate charges.
- **Shed load deliberately** — returning 429/503 quickly is better behaviour than accepting work you cannot finish.

## The bug catalogue

| Bug | How it appears | Fix |
|---|---|---|
| Missing visibility | Loop never sees the stop flag; stale read | `volatile`, atomic, or lock |
| Lost update | Counter drifts low under load | `AtomicInteger` / `LongAdder` / lock |
| Check-then-act race | Duplicate inserts, double-charge | Atomic compound op, DB unique constraint, `putIfAbsent` |
| Deadlock | Threads parked forever; app wedges | Consistent lock order; `tryLock` with timeout; no I/O under lock |
| Livelock / starvation | High CPU, no progress; one thread never runs | Backoff with jitter; fair locks if needed |
| `this` escaping in constructor | Half-built object observed | Factory method; start threads after construction |
| Unbounded queue | OOM or latency climbing without limit | Bounded queue + rejection policy |
| Blocking the common pool | Unrelated parallel streams stall | Explicit executor |
| Pinned carrier (Java 21–23, or native frames on any version) | Virtual-thread throughput collapses | JDK 24+; on 21, `ReentrantLock` instead of `synchronized` around I/O |
| Swallowed `InterruptedException` | Shutdown hangs; cancel does nothing | Restore flag or propagate |
| `ThreadLocal` leak | Classloader/memory leak in app servers | Clear in `finally`; prefer `ScopedValue` |
| Non-reentrant assumption | Self-deadlock with `StampedLock`/`ReadWriteLock` | Know the reentrancy of what you use |
| Double-checked locking w/o volatile | Rare NPE on a half-published object | Static holder idiom |
| Shared `SimpleDateFormat`/`Random` | Corrupt parse results, duplicate values | `java.time`; `ThreadLocalRandom` |

## Documenting thread safety

Say it explicitly, in Javadoc, because the next reader cannot infer it:

```java
/**
 * Thread-safe. All state is immutable; instances may be shared freely and cached.
 */

/**
 * NOT thread-safe. Confine one instance per request; do not store in a singleton bean.
 */

/**
 * Thread-safe for concurrent reads; writes must be externally serialised by the caller.
 * All access to {@code #entries} is guarded by {@code lock}.
 */
```

Pair the statement with a `@GuardedBy`-style note naming the lock for each piece of mutable state. A class whose thread-safety you cannot state in one sentence is a class whose concurrency model has not been designed yet — go back to [Decide the model first](#decide-the-model-first).
