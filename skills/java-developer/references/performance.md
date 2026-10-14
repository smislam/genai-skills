# Performance and scaling

Read this before optimising anything, choosing JVM flags, or answering "why is this slow". The order of this document is the order of the work: measure, then fix the thing the measurement found.

## Contents
- [Method](#method)
- [Where the time actually goes](#where-the-time-actually-goes)
- [Profiling](#profiling)
- [JMH microbenchmarks](#jmh-microbenchmarks)
- [Garbage collection](#garbage-collection)
- [Heap, memory and containers](#heap-memory-and-containers)
- [Allocation and data structures](#allocation-and-data-structures)
- [Database performance](#database-performance)
- [Connection pool sizing](#connection-pool-sizing)
- [Caching](#caching)
- [Concurrency and throughput](#concurrency-and-throughput)
- [Startup time and footprint](#startup-time-and-footprint)
- [Scaling out](#scaling-out)
- [Anti-patterns with real cost](#anti-patterns-with-real-cost)
- [What to measure in production](#what-to-measure-in-production)

## Method

Performance work without measurement is guessing, and guessing in Java is unusually unreliable because the JIT, the GC, and the memory hierarchy all defeat intuition.

1. **Define the goal numerically.** "p99 under 200 ms at 500 rps", not "faster". Without a target you cannot tell when to stop, and you will optimise something that did not matter.
2. **Measure the real thing.** Profile the application under representative load, not a microbenchmark of the code you suspect.
3. **Find the actual bottleneck.** Usually it is I/O, a query, a lock, or allocation pressure — rarely the arithmetic someone wants to hand-optimise.
4. **Change one thing, re-measure.** Batched changes make attribution impossible.
5. **Keep the fix if the number moved and the code is still clear.** Revert clever code that bought 2%.

Two framing points worth stating to a user who asks for optimisation: **the biggest wins are almost always algorithmic or architectural** — an N+1 query, a missing index, a missing cache, an O(n²) loop over a growing collection — and **clear code is fast enough almost everywhere**. Reserve micro-optimisation for the few paths a profiler proved hot.

## Where the time actually goes

In a typical Spring Boot service, ranked by how often each is the real answer:

1. **Database** — N+1 queries, missing index, fetching whole entity graphs for a list view, unnecessary round trips.
2. **Remote calls** — serial calls that could be concurrent, missing timeouts, no caching, chatty APIs.
3. **Serialization** — oversized payloads, rendering fields nobody reads, repeated mapping layers.
4. **Allocation pressure** — not individual allocations, but churn driving GC frequency.
5. **Lock contention** — a synchronized block on a hot path, an undersized pool, a shared mutable cache.
6. **Actual computation** — last, and usually only in genuine data processing.

Check them in roughly that order before touching the JVM. JVM tuning that is not responding to a measured GC or memory problem is almost always wasted effort.

## Profiling

**Java Flight Recorder** is the default tool: built in, low overhead, safe to run continuously.

```bash
java -XX:StartFlightRecording=duration=120s,filename=app.jfr,settings=profile -jar app.jar
jcmd <pid> JFR.start name=diag settings=profile duration=120s filename=/tmp/diag.jfr   # on a running JVM
```

Open in JDK Mission Control and look at: hot methods, allocation by site and by class, GC pauses and their causes, lock contention (`jdk.JavaMonitorEnter`), thread states, exception rate, and — for virtual threads — `jdk.VirtualThreadPinned` and `jdk.VirtualThreadSubmitFailed`.

**async-profiler** complements it: a low-overhead sampling profiler that avoids safepoint bias (older Java profilers systematically mis-attribute time because they can only sample at safepoints), and can see native and kernel frames plus non-Java threads such as GC and JIT.

```bash
asprof -d 30 -f flame.html <pid>          # 30s CPU flame graph
asprof -e alloc -d 30 -f alloc.html <pid> # allocation profile
asprof -e lock -d 30 -f lock.html <pid>   # contention
```

Read flame graphs by width, not by depth: a wide frame is where the time is. Allocation profiles are the fastest route to GC problems — they name the line producing the garbage.

Also keep in the toolkit: `jcmd <pid> Thread.print` for a thread dump when something hangs (look for `BLOCKED` threads and a common lock owner), `jcmd <pid> GC.heap_info`, **Native Memory Tracking** (`-XX:NativeMemoryTracking=summary`) when RSS exceeds heap, and GC logging (`-Xlog:gc*:file=gc.log:time,uptime:filecount=5,filesize=20M`) which is cheap enough to leave on in production.

## JMH microbenchmarks

Use JMH when you genuinely need to compare two implementations of a hot method. Never hand-roll a benchmark with `System.nanoTime()` around a loop — the JIT will optimise away work, and you will measure warmup.

```java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@State(Scope.Benchmark)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 10, time = 1)
@Fork(2)
public class ParseBenchmark {

    private String input;

    @Setup public void setup() { input = "2026-10-13T12:00:00Z"; }

    @Benchmark
    public Instant parse() {
        return Instant.parse(input);     // RETURN the result — see below
    }

    @Benchmark
    public void parseAndConsume(Blackhole bh) {
        bh.consume(Instant.parse(input));
    }
}
```

The correctness rules, in order of how often they are violated:

- **Return the result, or `Blackhole.consume` it.** A benchmark that discards its result lets the JIT delete the computation entirely — this is the cause of nearly every "impossibly fast" microbenchmark.
- **Warm up.** The first thousands of invocations run interpreted or in C1; steady-state numbers require `@Warmup` and `@Fork`.
- **Avoid constant folding.** Inputs must come from `@State` fields, not literals the compiler can evaluate.
- **Fork more than once** — JIT compilation plans vary run to run, and a single fork can give a confidently wrong answer.
- **Interpret with suspicion.** A microbenchmark isolates code from the cache pressure, allocation rate, and contention of a real service. A method that is 30% faster in JMH can be slower in production if it allocates more. Validate against an end-to-end measurement before believing it.

## Garbage collection

Default to the collector the JDK gives you and change it only in response to a measurement.

| Collector | Use when | Notes |
|---|---|---|
| **G1** (default) | Almost everything; balanced throughput and pause times | Set `-XX:MaxGCPauseMillis` as a *goal*, and otherwise leave it alone |
| **Generational ZGC** | Low, predictable pause times matter (sub-millisecond), or the heap is very large | `-XX:+UseZGC`. Generational mode has been the default since JDK 23 and the only mode since 24. Trades some throughput and a little extra footprint for pause times |
| **Parallel** | Batch jobs maximising throughput where pauses are irrelevant | `-XX:+UseParallelGC` |
| **Shenandoah** | Low-pause alternative where your JDK distribution supports it well | Generational mode available in recent releases; check your vendor's support |
| **Serial** | Tiny heaps, single-core containers, short-lived CLI processes | Lowest overhead |

**What not to tune.** Modern collectors are explicitly designed to be self-sizing — leave generation sizes, region counts, and GC thread counts alone unless a GC log analysis says otherwise. Copying a list of flags from a blog post is the most common way to make a service slower. The levers that genuinely matter are: which collector, how much heap, and — far more effective than either — **how much garbage the application produces**.

Read GC logs for three things: pause duration distribution, pause frequency, and whether the live set is growing (a leak) or the heap is simply too small (frequent full collections with high post-collection occupancy).

## Heap, memory and containers

Heap is not the whole footprint. RSS also includes metaspace, code cache, thread stacks (~1 MB per platform thread), direct/mapped byte buffers, GC structures, and native allocations. A container OOM-kill with plenty of free heap is almost always one of those.

```bash
-XX:MaxRAMPercentage=70        # scales with the container limit; better than a fixed -Xmx
-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/app
-XX:NativeMemoryTracking=summary
```

- The JVM is container-aware and reads cgroup limits, so **set the container memory limit and use `MaxRAMPercentage`** rather than hard-coding `-Xmx` per environment.
- **Leave 25–30% headroom** for non-heap memory. Tight limits plus a large heap percentage is the classic recipe for mysterious kills.
- `-Xms` equal to `-Xmx` avoids heap resizing pauses in long-running services.
- **Diagnose leaks from a heap dump**, not by guessing: dominator tree in Eclipse MAT or JMC, and look for the usual suspects — an unbounded cache or `Map`, a growing static collection, `ThreadLocal`s never cleared on pooled threads, unclosed resources, and listeners never deregistered.
- On JDK 25+, `-XX:+UseCompactObjectHeaders` shrinks per-object overhead and can reduce heap use meaningfully on object-heavy workloads.

## Allocation and data structures

Allocation in the JVM is cheap individually; **allocation *rate* is what costs you**, because it drives GC frequency. The target for optimisation is garbage volume, not object count.

- Size collections when you know the size (`new ArrayList<>(expected)`, `HashMap` with capacity) to avoid repeated resize-and-copy.
- Use primitive arrays and `IntStream`/`LongStream` on hot paths; boxing allocates and destroys cache locality.
- `EnumMap`/`EnumSet` over `HashMap`/`HashSet` for enum keys — array-backed, dramatically faster.
- `ArrayDeque` over `LinkedList` for queues and stacks; `LinkedList` allocates a node per element and has terrible locality. It is almost never the right choice.
- Reuse immutable constants (`BigDecimal.ZERO`, interned enum values, precompiled `Pattern`s — never compile a regex inside a loop).
- `StringBuilder` for loop concatenation; plain `+` is fine for a fixed number of operands.
- Streams are usually fine; in genuinely hot inner loops a plain `for` loop can win because lambda pipelines do not always inline away. Measure before rewriting — for ordinary business logic the difference is noise next to one database round trip.
- Avoid `Optional` allocation and exception construction in hot paths. **Exceptions are expensive mainly because of stack-trace capture** — using them for expected outcomes (not-found in a tight lookup loop) is both slow and a design smell (`design.md`).
- Watch out for accidentally quadratic code: `list.contains()` inside a loop over the same list, string concatenation in a loop, repeated `List.remove(0)` on an `ArrayList`, nested loops over a collection that grew.

## Database performance

This is where most "slow application" tickets actually live.

- **Find N+1 first.** The default `FetchType.EAGER` on `@ManyToOne`/`@OneToOne` and lazy access in a loop are the two causes. Fix with `JOIN FETCH` or `@EntityGraph`, or use `hibernate.default_batch_fetch_size` to batch lazy loads when a join is impractical. Note that slow-query logs will *not* find this — each query is fast; the problem is the count. Use datasource-proxy or Hibernate statistics to count queries, and assert the count in a test so it cannot regress.
- **Project, do not hydrate.** For list and report views, select a DTO or interface projection instead of full entities. Fetching entity graphs to render a table is the most common avoidable cost in a JPA application.
- **Index for your actual queries** — the columns in `WHERE`, `JOIN`, and `ORDER BY`, with composite-index column order matching the query. Read `EXPLAIN (ANALYZE)` output rather than assuming; a function on an indexed column (`WHERE lower(email) = ?`) disables the index unless you created a matching expression index.
- **Paginate everything,** and prefer keyset ("seek") pagination over large `OFFSET`s, which scan and discard rows. Be aware that `JOIN FETCH` on a collection plus `Pageable` forces in-memory paging — split into an id query and a fetch query.
- **Batch writes:** `hibernate.jdbc.batch_size`, `order_inserts`, `order_updates`, and avoid `GenerationType.IDENTITY`, which disables insert batching. For bulk loads, use `JdbcClient`/`JdbcTemplate` batch updates or the database's native bulk path; JPA is the wrong tool.
- **Keep transactions short and I/O-free** — a remote call inside a transaction holds a connection for the duration (`spring-boot.md`).
- **Only the queries you need:** `readOnly = true` on query methods, `select` only required columns on wide tables, and no `COUNT(*)` on every page request if an approximate or cached count will do (`Slice` instead of `Page` avoids the count query entirely).

## Connection pool sizing

Smaller pools are usually faster — this surprises people. The starting formula (HikariCP's own guidance, derived from PostgreSQL work):

```
connections = (physical_core_count * 2) + effective_spindle_count
```

Count physical cores, not hyperthreads; `effective_spindle_count` tends toward 0 when the working set is cached in RAM. A 4-core box with one disk gives `(4*2)+1 = 9`, round to 10.

The principle behind it: **you want a small pool saturated with threads waiting for it.** Beyond the core count, concurrent database work is just time-sliced, and context switching plus lock contention costs more than it gains — executing A then B is faster than fake-parallel A and B. Treat the formula as a load-test starting point, not gospel.

Also: set `connectionTimeout` so an exhausted pool fails fast instead of hanging; make sure `maximumPoolSize` × instance count stays within the database's `max_connections` (a cluster that autoscales to 50 pods with a 20-connection pool will exhaust the server); and if one logical operation needs two connections concurrently, that is usually a design smell and a deadlock risk.

With virtual threads enabled, the pool becomes your real concurrency limit — which is fine and intended, but know that it is the bound, and monitor pool wait time (`hikaricp.connections.pending`) as a first-class metric.

## Caching

The cheapest query is the one you never make, and the hardest bug is a stale or cross-tenant cache. Decide these explicitly:

- **TTL** — always finite. "Cache forever" means "serve stale forever".
- **Key** — must include everything that affects the result: tenant, user, locale, permissions, version. A cache key that omits the user is a data-leak bug, not a performance bug.
- **Size bound and eviction** — unbounded caches are the most common Java memory leak. Caffeine with `maximumSize` or `maximumWeight`.
- **Invalidation on write** — and accept that distributed invalidation is eventually consistent.
- **Stampede protection** — `refreshAfterWrite` or request coalescing, so expiry of a hot key does not send a thundering herd at the database.

Layers, cheapest first: in-process (Caffeine) for small hot data with tolerable staleness; distributed (Redis) when instances must agree or the data is large; HTTP caching (`ETag`, `Cache-Control`) to avoid the request entirely; CDN for static and public content. Measure hit rate — a cache below ~80% hit rate on a hot path is often adding latency and complexity rather than removing it.

## Concurrency and throughput

Full detail in `concurrency.md`; the performance-relevant summary:

- **Parallelise independent remote calls.** Three serial 100 ms calls become one 100 ms wait. This is frequently the largest single win in a service that aggregates data, and with virtual threads it costs almost nothing in complexity.
- **Virtual threads remove thread-pool sizing as a bottleneck for blocking I/O** — but they do not add parallelism for CPU-bound work, and they move your concurrency limit to the scarce resource (connection pool, downstream rate limit). On JDK 21–23, `synchronized` held across blocking I/O pins a carrier and can collapse throughput; JEP 491 fixed that in JDK 24.
- **Lock contention shows up as low CPU with poor throughput.** Find it with a lock profile, then shrink the critical section, switch to an immutable snapshot, or partition the data.
- **Bound queues and shed load** — unbounded queueing converts an overload into unbounded latency and then an OOM. Fast rejection is better behaviour.
- **Watch the common `ForkJoinPool`** — blocking work there stalls every parallel stream in the process.

## Startup time and footprint

Relevant when you scale rapidly, run serverless, or deploy frequently.

- **Measure first:** `-Xlog:class+load` plus Boot's own startup logging will tell you whether time goes to classloading, bean creation, or a slow connection check at boot. Often it is one eager bean doing network I/O.
- **CDS / AppCDS** — share and pre-parse class metadata. Cheap, no code change.
- **AOT class loading and linking** (JDK 24+, JEP 483) goes further: a training run records class loading behaviour into an AOT cache, and production runs skip loading and linking rather than merely re-reading. JDK 25 adds one-command ergonomics (`-XX:AOTCacheOutput`, JEP 514) and cached method profiles so the JIT does not re-profile from scratch (JEP 515). This is the shipped part of Project Leyden and the best startup-per-effort ratio available today.
- **Spring AOT** processing turns `@Configuration` into generated bean-definition code, cutting reflection at startup — useful on the JVM and required for native images.
- **GraalVM native image** gives very fast startup and a small footprint, at real cost: long builds, closed-world analysis, and explicit hints for reflection, proxies, and resources. Choose it when cold-start latency or memory density is a hard requirement — serverless, scale-to-zero, many small instances. Avoid it for reflection-heavy applications, anything needing runtime reconfiguration, or sustained-throughput compute where the JIT eventually beats AOT-compiled code.
- Trim the image: `jlink` a custom runtime or use a JRE base, and layer the container so dependency layers cache.

## Scaling out

Vertical scaling buys time; horizontal scaling needs the application to cooperate.

- **Stateless instances.** No in-memory session state, no local file state, no "the scheduler runs on instance 1". Externalise session state or use tokens.
- **Idempotent operations.** Retries, at-least-once message delivery, and duplicate submissions are facts of distributed life. Use idempotency keys and unique constraints so a duplicate is a no-op rather than a double charge.
- **The database is the usual scaling limit.** Read replicas for read-heavy loads (accepting replication lag), connection pooling per instance sized for the aggregate, partitioning or sharding only when simpler options are exhausted.
- **Singleton work needs coordination.** `@Scheduled` fires on every instance — use a distributed lock (ShedLock) or leader election.
- **Asynchronous work for anything slow.** Accept, enqueue, return 202, process in a consumer you can scale independently. This is also what makes bursts survivable.
- **Cross-service consistency:** the outbox pattern or sagas, not distributed transactions.
- **Protect yourself and your dependencies** — timeouts, circuit breakers, retry with jitter, bulkheads, and rate limits at the edge. A retry storm without jitter turns a blip into an outage.
- **Graceful shutdown** (`server.shutdown=graceful`) plus readiness probes, so rolling deploys do not drop in-flight requests.

## Anti-patterns with real cost

| Anti-pattern | Why it costs | Fix |
|---|---|---|
| N+1 queries | 1 + N round trips, each with latency | `JOIN FETCH` / `@EntityGraph` / batch size |
| Fetching entities for list views | Hydrates whole graphs to render three columns | DTO projections |
| `findAll()` unpaginated | Memory and latency grow with the table | `Pageable`, keyset pagination |
| Large `OFFSET` pagination | Scans and discards rows | Keyset pagination |
| Missing or unusable index | Full scans; function on indexed column | `EXPLAIN`, expression index |
| Remote calls in series | Latency adds up | Fan out concurrently |
| No timeouts | One slow dependency exhausts capacity | Connect + read timeouts everywhere |
| Unbounded cache or queue | Leak, then OOM | Size bound + eviction |
| Cache key missing a dimension | Wrong data served (correctness, not just perf) | Include tenant/user/locale |
| String concat in a loop | O(n²) copying | One `StringBuilder` |
| Boxing in hot loops | Allocation churn, poor locality | Primitive streams/arrays |
| Regex compiled per call | Recompiles a state machine every invocation | `static final Pattern` |
| `log.debug("x=" + x)` | Builds the string even when disabled | `log.debug("x={}", x)` |
| Exceptions as control flow | Stack-trace capture per occurrence | Return a result type |
| Blocking the common ForkJoinPool | Stalls all parallel streams | Explicit executor |
| Oversized connection pool | Context switching and contention beat the gain | `(cores × 2) + spindles`, then load-test |
| JVM flags copied from a blog | Fights a self-tuning collector | Collector + heap size; measure |
| `synchronized` around I/O on JDK 21–23 | Pins virtual-thread carriers | JDK 24+ (the 25 baseline is unaffected); on 21, `ReentrantLock` |
| Serializing huge payloads | CPU and bandwidth on fields nobody reads | Shape the response; paginate; compress |

## What to measure in production

Averages hide the problems that page people. Track:

- **Latency percentiles** — p50, p95, **p99**, and max, per endpoint. An average of 40 ms with a p99 of 4 s is a broken service.
- **Throughput and error rate**, per endpoint and per dependency.
- **Saturation**: thread pool and connection pool utilisation and *wait time*, queue depth.
- **GC**: pause time distribution, frequency, and **allocation rate** — the best leading indicator of GC pressure.
- **Memory**: heap after collection (a rising floor is a leak), RSS versus the container limit.
- **Database**: query count per request, slow queries, pool wait time, replication lag.
- **Cache hit rate.**

Micrometer exposes most of this with no custom code (`spring-boot.md`). Keep metric tag cardinality low — ids or raw paths as tags will take down the metrics backend, which is its own availability incident.
