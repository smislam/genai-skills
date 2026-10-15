# Performance review

Performance problems are reported in their own section, after security, and never counted as security findings or included in SARIF or GitLab reports. Two kinds of performance problem *are* security issues: ones an attacker can trigger to exhaust resources (denial of service) and amplification. Those are covered under "Resource exhaustion" in `vuln-classes.md` and are reported as security findings.

Only report what the code shows. Don't guess at runtime behavior you can't see, such as data sizes, traffic, and hardware. When the impact depends on data volume, state the assumption ("if `orders` grows beyond a few thousand rows per customer…").

## What to look for

Concentrate on hot paths: request handlers, message consumers, loops over request or database data, and code called from them. Skip one-off scripts, migrations, and test code.

| Problem | Patterns | Typical fix |
|---|---|---|
| **N+1 queries** | Loading a list, then querying per item inside a loop: JPA/Hibernate lazy collections accessed in a loop, Django `for o in qs: o.related.x`, Entity Framework navigation properties in a loop, an ORM call in a GraphQL field resolver | Eager loading (`JOIN FETCH` / `@EntityGraph`, `select_related` / `prefetch_related`, `.Include()`), batching (DataLoader), one query with `IN (...)` |
| **Unbounded queries and results** | `findAll()`, `.all()`, `SELECT *` without `LIMIT` on user-facing endpoints; loading a whole table into memory; no pagination | Pagination with a maximum page size; streaming; projections of only the needed columns |
| **Missing indexes** | Filters, joins, or sorts on columns with no index in the schema or migrations (visible in migration files, `@Index`, `db_index=True`, Prisma `@@index`) | Add the index; verify with the database's query plan |
| **Blocking calls in async code** | Synchronous I/O, `time.sleep`, `requests` inside `async def`; `fs.readFileSync` or CPU-heavy work on Node's event loop; `.Result` / `.Wait()` on tasks in ASP.NET; blocking calls inside Rust async tasks without `spawn_blocking` | Async clients; `asyncio.to_thread` or `run_in_executor`; worker threads; `await`; `tokio::task::spawn_blocking` |
| **Chatty remote calls** | HTTP or database calls inside loops; sequential calls that could run concurrently; no connection reuse (a new client per request) | Batch APIs; concurrent calls with a limit; one shared client or connection pool |
| **Connection and pool misuse** | Connections or clients created per request; pools sized at the default under obvious concurrency; connections not returned on error paths | Shared pooled clients; `try`-with-resources, `using`, `with`, `defer`; explicit pool sizing |
| **Inefficient algorithms on hot paths** | Nested loops over request-sized collections (O(n²) lookups that a map would make O(n)); repeated sorting; regex compiled inside loops; string concatenation in loops in Java or C# | Hash maps or sets; precompiled regex; `StringBuilder` / `strings.Builder` / `join` |
| **Memory growth** | Caches with no size or time bound (static maps, `lru_cache` with `maxsize=None` on unbounded keys); event listeners or subscriptions added per request and never removed; large files read fully into memory | Bounded caches (size and TTL); unsubscribe or dispose; streaming |
| **Missing caching of expensive, stable results** | Recomputing or refetching the same expensive data on every request (configuration, reference data, remote lookups) | A bounded cache with a TTL. Check that cached data can't leak between users or tenants: that would be a security finding |
| **Oversized payloads** | Returning whole entities with large fields; no response compression for large JSON; images or files served through the application instead of a CDN or object storage | Projections or DTOs; compression; pre-signed URLs or a CDN |
| **Logging overhead** | Debug logging of large objects on hot paths; string formatting done before checking the log level | Log-level guards or lazy formatting; structured logging |

Language specifics, briefly:
- **Java:** `synchronized` around blocking I/O on virtual threads (pinning in Java 21–23); `parallelStream()` on request threads; `String.format` in tight loops.
- **.NET:** sync-over-async (`.Result`); `HttpClient` created per request instead of `IHttpClientFactory`; LINQ queries enumerated several times.
- **Node and front end:** synchronous `fs`, `crypto.pbkdf2Sync`, or large `JSON.parse` on the event loop. In the front end: re-renders caused by new object or function props on every render, missing `key` props, very large bundles from unused dependencies, and unvirtualized long lists.
- **Python:** pandas row iteration (`iterrows`) on large frames; `requests` inside `async` code; the GIL making threads ineffective for CPU-bound work.
- **Go:** goroutines started per item without a limit; `defer` inside long loops; unbuffered channels causing lock-step stalls; `regexp.MustCompile` inside functions on hot paths.
- **Rust:** `.clone()` of large values in loops; `Mutex` held across `.await`; blocking calls in async tasks.

## Rating

Use **High**, **Medium**, or **Low** impact:

| Impact | Meaning |
|---|---|
| **High** | Likely to cause timeouts, outages, or runaway cost at realistic load: N+1 or unbounded queries on main endpoints, blocking the event loop, unbounded memory growth |
| **Medium** | Noticeable latency or resource waste at realistic load |
| **Low** | A minor inefficiency, or only matters at unusual scale |

Every performance finding needs file:line evidence and the reason it's on a hot path, the same as a security finding. If something an attacker can trigger repeatedly makes the problem worse (an unauthenticated endpoint that runs an unbounded query, for example), it's also a resource-exhaustion security finding. Report it there, and cross-reference it.

## Report section

```markdown
## Performance

| Impact | Where | Problem | Fix |
|---|---|---|---|
| High | `OrderService.java:142` | N+1: loads each order's items in a loop for `GET /orders` (one query per order) | `@EntityGraph(attributePaths = "items")` on `findByCustomerId` |
```

Offer fixes as diffs, the same as security fixes: proposed only, and applied with approval.
