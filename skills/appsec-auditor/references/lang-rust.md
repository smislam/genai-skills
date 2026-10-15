# Rust: security review guide

Covers Rust services built on Axum, Actix Web, Rocket, Warp, and Hyper, with sqlx, Diesel, and SeaORM, serde-based input handling, and `unsafe` or FFI code anywhere in the crate. Memory safety is the default in Rust, so review attention goes to `unsafe` blocks, logic flaws, panics as denial of service, and the same injection classes as any language. Tool commands are in `tools.md`; triage rules in `triage.md`.

## Sources

- **Axum:** extractors `Query<T>`, `Path<T>`, `Json<T>`, `Form<T>`, `HeaderMap`, `TypedHeader` (in `axum-extra` from axum 0.7), `Multipart`, `RawQuery`, `Bytes`, `String` bodies, cookies from `axum-extra`.
- **Actix Web:** `web::Query`, `web::Path`, `web::Json`, `web::Form`, `web::Bytes`, `HttpRequest` headers and `match_info`, `actix-multipart`.
- **Rocket:** route parameters and segments, `Form<T>`, `Json<T>`, request guards that read headers or cookies, `Data` streams.
- **Other inputs:** message consumers (`rdkafka`, `lapin`, `aws-sdk-sqs`), gRPC (`tonic`) request messages, CLI arguments (`clap`) in tools run on others' input, files, environment variables, and LLM output.
- **Typed extraction:** extraction into strongly typed structs rejects malformed input, which is a mitigation for format errors. It doesn't sanitize string content.

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| SQL injection (CWE-89) | `format!` building SQL passed to `sqlx::query(&sql)`, `sqlx::query_as`, `sqlx::raw_sql`, `conn.execute(&sql)`; Diesel `sql_query(format!(...))`; Diesel `sql()` fragments with interpolated input; SeaORM `Statement::from_string` with input | `sqlx::query!` / `query_as!` macros or `.bind(value)`; Diesel query DSL or `sql_query(...).bind::<Type, _>(v)`; allow-list identifiers |
| OS command injection (CWE-78) | `Command::new("sh").arg("-c").arg(user)`, `Command::new("cmd").args(["/C", ...])`; user-controlled program name | `Command::new(fixed).arg(input)` with input as separate arguments; reject leading `-` |
| XSS / template injection (CWE-79) | Returning `Html(format!("...{}", input))` in Axum or `HttpResponse` with an HTML content type and interpolated input; Tera with autoescape disabled or the `\|safe` filter; `PreEscaped` in Maud; `Markup` built from input | Askama, Tera, or Handlebars with autoescape on; never mark untrusted input as safe |
| Path traversal (CWE-22) | `std::fs::File::open`, `fs::read`, `fs::write`, `tokio::fs::*`, `NamedFile::open` with paths built by `Path::join` or `format!` from input. `Path::join` with an absolute component *replaces* the base | Reject components other than `Component::Normal`; canonicalize, then check `starts_with(base)`; serve static files with `tower_http::services::ServeDir` |
| Zip Slip (CWE-22) | `zip` or `tar` crate extraction using entry names directly | `ZipFile::enclosed_name()` (the `zip` crate); validate tar entry paths |
| SSRF (CWE-918) | `reqwest::get(user_url)`, `Client::get(user_url)`, `hyper` clients to user-controlled hosts; default redirect following | Allow-list hosts; resolve and reject private and link-local ranges (custom resolver or connector); `redirect::Policy::none()` or a limited policy |
| Open redirect (CWE-601) | `Redirect::to(&next)` (Axum), `HttpResponse::Found().insert_header((LOCATION, next))` | Allow-list, or relative paths only |
| Deserialization (CWE-502, CWE-915) | serde into structs whose privileged fields (`role`, `is_admin`, `tenant_id`) the client can set; `bincode` or `rmp-serde` from untrusted sources without size limits; `serde_yaml` with unbounded anchors and aliases | Separate input DTOs; `#[serde(deny_unknown_fields)]`; size-limited deserializers (bincode options with a limit) |
| XXE (CWE-611) | `quick-xml` and `roxmltree` don't fetch external entities by default. Risk exists in libxml bindings (`libxml` crate) with entity loading | Pure-Rust parsers; confirm settings on bindings |
| Weak randomness (CWE-338) | `rand::thread_rng()` / `rand::rng()` is a CSPRNG; the risk is seeded or non-crypto generators (`SmallRng`, `StdRng::seed_from_u64`, `fastrand`) used for tokens | `rand::rngs::OsRng`, `getrandom`, or `rand::rng()` for secrets |
| TLS misuse (CWE-295) | `reqwest::ClientBuilder::danger_accept_invalid_certs(true)`, `danger_accept_invalid_hostnames(true)`; a custom rustls `ServerCertVerifier` that accepts all | Default verification; rustls with webpki roots |
| Weak crypto (CWE-327, CWE-916) | `md5` or `sha1` crates for passwords or signatures; a single fast hash for passwords; ECB modes; nonce reuse with `aes-gcm` | `argon2`, `bcrypt`, `scrypt` crates; `aes-gcm` or `chacha20poly1305` with random nonces; the `ring` or `aws-lc-rs` APIs |
| Timing comparison (CWE-208) | `==` on secrets or MACs | `subtle::ConstantTimeEq`; `ring::constant_time` (deprecated in newer ring, so check the version); `hmac`'s `verify_slice` |
| ReDoS (CWE-1333) | The `regex` crate is linear time. `fancy-regex` (backtracking) on untrusted input is not | Use `regex`; size limits with `RegexBuilder::size_limit` for user-supplied patterns |
| Unbounded input / decompression bomb (CWE-400, CWE-409) | No body size limit (Axum defaults to a 2 MB limit for some extractors, which can be disabled with `DefaultBodyLimit::disable()`); `flate2` or `zip` decompression without a cap; `Vec::with_capacity(len_from_input)` | `DefaultBodyLimit::max`, `RequestBodyLimitLayer`, Actix `PayloadConfig`/`JsonConfig` limits; `Read::take` on decompressors |
| File upload (CWE-434) | Saving `Multipart` fields under the client filename or in a served directory | Generated names, content-type allow-list, storage outside the web root |
| Log injection (CWE-117) | Unstructured logging of raw input | `tracing` with structured fields |

## Authentication, authorization, and session

- **Route coverage:**
  - Axum: auth layers applied with `.route_layer` or `.layer` must cover every sensitive route. Routes added *after* the `.layer(...)` call aren't wrapped.
  - Actix: check `wrap()` placement per `scope`.
  - Rocket: sensitive handlers need a request guard that enforces auth.
- **Object-level authorization (CWE-639):** handlers that look up rows by a path ID without filtering by the authenticated principal.
- **JWT** (`jsonwebtoken` crate):
  - `Validation::new(Algorithm::...)` must pin the algorithm.
  - Check `validate_exp`, and set `set_audience` and `set_issuer`.
  - `insecure_disable_signature_validation()` is a finding.
  - The decoding key must not be a literal.
- **Cookies:** sessions (`tower-sessions`, `actix-session`) should use a key from a secret store, with `Secure`, `HttpOnly`, and `SameSite` set.
- **CORS:** `tower_http::cors::CorsLayer::very_permissive()`, or `AllowOrigin::mirror_request()` (or an allow-all predicate) with `allow_credentials(true)`, is a finding in production. `permissive()` sends no credentials, so it's lower risk. Combining `Any` with credentials panics at startup, so it won't appear in working code.
- **Login throttling:** password and OTP endpoints need it (CWE-307).

## Language-specific issues

- **`unsafe` review checklist (CWE-119, CWE-787, CWE-416).** For every `unsafe` block and `unsafe fn`:
  - Is there a `// SAFETY:` comment stating the invariant?
  - Can input influence the pointer, length, or index? Pay particular attention to `get_unchecked`, `from_raw_parts`, `set_len`, `ptr::copy_nonoverlapping`, and `MaybeUninit::assume_init`.
  - Is a `&mut` aliased?
  - Is a value used after `drop` or `Box::from_raw`?
  - Are `Send` and `Sync` implemented manually (`unsafe impl Send`) for types that aren't thread-safe?
- **`transmute` (CWE-843):** between types with different layouts or validity invariants, including `bool`, `char`, enums, and references with changed lifetimes.
- **FFI (CWE-119, CWE-120):** `extern "C"` calls with buffer lengths taken from input; `CStr::from_ptr` on non-NUL-terminated data; ownership of foreign pointers freed on the wrong side.
- **Panics as denial of service (CWE-248, CWE-400):**
  - `unwrap()`, `expect()`, indexing (`v[i]`), slicing (`&s[a..b]`, which panics on a non-char boundary), `.parse().unwrap()`, and division by zero on input-derived values.
  - Async frameworks catch panics per task in many setups, but a panic in a shared task, while holding a `Mutex` (poisoning), or with `panic = "abort"` in the release profile can take the service down.
- **Integer overflow (CWE-190):** wraps silently in release builds unless `overflow-checks = true`. Review arithmetic on lengths, prices, and quotas from input; prefer `checked_*`, `saturating_*`, or `try_from`. `as` casts truncate silently (`u64 as u32`, `i64 as usize`).
- **Concurrency (CWE-362):** check-then-act on shared state across `.await` points, where a lock is dropped between the check and the act. Holding a `std::sync::Mutex` guard across `.await` risks deadlocks.
- **Unsoundness in dependencies:** RustSec advisories marked `unsound` and `cargo-geiger` counts point at risky crates. Treat unsound advisories as findings when the affected API is used.

## Configuration

- **Secrets:** `include_str!` or `env!` (compile-time) embedding secrets into the binary; `dotenvy` loading `.env` in production with committed values.
- **Debug output:** backtraces or `{:?}` of internal errors returned in HTTP responses (CWE-209). Tracing at `debug` level logging request bodies with credentials.
- **Release profile:** check `Cargo.toml` `[profile.release]` for `overflow-checks` and `panic` settings, and `debug-assertions` disabled where safety checks rely on `debug_assert!`.

## Dependencies and build

- **Manifests:** `Cargo.toml` declares dependencies; `Cargo.lock` should be committed for binaries. Check `[patch]` and `[replace]` sections, `git =` dependencies without a pinned `rev`, and path dependencies to vendored code.
- **Supply-chain policy:** `cargo-deny` can enforce advisory, license, ban, and source policy if a `deny.toml` exists. `cargo-vet` audits may be recorded in `supply-chain/`.
- **Code execution:**
  - `build.rs` scripts and procedural macros run arbitrary code at compile time, including `cargo check`, `cargo build`, `cargo test`, and IDE analysis.
  - Some reachability analyses (for example OSV-Scanner's Rust call analysis) build the project.
  - **Ask before running anything that compiles.** Lockfile-only tools such as `cargo audit` on `Cargo.lock` don't compile the project.

## Quick search patterns

Candidates only; each hit still goes through `triage.md`.

```
unsafe\s*(\{|fn|impl)
transmute|from_raw_parts|get_unchecked|set_len|assume_init|Box::from_raw
extern\s+"C"
format!\([^)]*(SELECT|INSERT|UPDATE|DELETE|WHERE)
sql_query\(\s*format!|raw_sql\(|query\(\s*&format!
Command::new\(\s*"(sh|bash|cmd|powershell)"
danger_accept_invalid_(certs|hostnames)
insecure_disable_signature_validation
CorsLayer::(permissive|very_permissive)
DefaultBodyLimit::disable
\.unwrap\(\)|\.expect\(
\bas\s+(u8|u16|u32|i32|usize)\b
Redirect::(to|temporary|permanent)\(
\|\s*safe|PreEscaped
SmallRng|seed_from_u64|fastrand
```
