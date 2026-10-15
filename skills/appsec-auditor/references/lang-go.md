# Go: security review guide

Covers Go services built on `net/http`, Gin, Echo, Chi, and Fiber, with `database/sql`, sqlx, GORM, and the standard template packages. Tool commands are in `tools.md`; triage rules in `triage.md`.

## Sources

Attacker-influenced data enters through:

- **`net/http`:** `r.URL.Query()`, `r.FormValue`, `r.PostFormValue`, `r.Form`, `r.MultipartForm`, `r.Header.Get`, `r.Cookie`, `r.Body`, `r.URL.Path`, `r.Host`, `r.RemoteAddr` (spoofable behind a proxy if trusted from `X-Forwarded-For`), and `r.PathValue` (Go 1.22+ patterns).
- **Gin:** `c.Query`, `c.Param`, `c.PostForm`, `c.GetHeader`, `c.Cookie`, `c.ShouldBind*` / `c.Bind*`, `c.FormFile`, `c.Request`.
- **Echo:** `c.QueryParam`, `c.Param`, `c.FormValue`, `c.Bind`, `c.FormFile`, `c.Request()`.
- **Chi:** `chi.URLParam(r, ...)`, plus the `net/http` sources.
- **Other inputs:** message consumers (Kafka, SQS, NATS payloads), gRPC request messages, environment variables and flags in multi-tenant tooling, files read from user-controlled paths, and LLM output.

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| SQL injection (CWE-89) | `db.Query`, `db.Exec`, `db.QueryRow`, `sqlx.Select`/`Get` with `fmt.Sprintf` or `+` building SQL; GORM `db.Raw`, `db.Exec`, and string arguments to `Where`, `Order`, `Group`, `Select`, `Joins` built from input | Placeholders (`?` or `$1`) with arguments; GORM `Where("name = ?", v)`; allow-list for column and sort names |
| OS command injection (CWE-78) | `exec.Command("sh", "-c", userString)`, `exec.Command("bash", "-c", ...)`; user-controlled program name; user input as the first argument | `exec.Command(fixedBinary, args...)` with input only as separate arguments; reject leading `-`; prefer a library over shelling out |
| Template injection / XSS (CWE-79, CWE-1336) | `text/template` rendering HTML; `template.HTML(userInput)`, `template.JS`, `template.URL` conversions; `w.Write` of unescaped input with an HTML content type; parsing a template *from* user input | `html/template` (context-aware escaping); never convert untrusted input to `template.HTML`; set `Content-Type` explicitly |
| Path traversal (CWE-22) | `os.Open`, `os.ReadFile`, `os.Create`, `http.ServeFile`, `c.File` with a path built from input. `filepath.Join` is **not** a guard: it cleans `..` but still escapes the base | `os.Root` (Go 1.24+) to confine access; or `filepath.Clean`, then `filepath.Rel` or a prefix check against the absolute base; `filepath.IsLocal` (Go 1.20+); `http.FileServer` with `http.Dir` for static content |
| Zip Slip (CWE-22) | `archive/zip` and `archive/tar` entry names joined to a destination without validation | Reject entries where `filepath.IsLocal(name)` is false, or that resolve outside the destination |
| SSRF (CWE-918) | `http.Get(userURL)`, `http.NewRequest` with a user-controlled URL or host, `net.Dial` to user input; redirects followed by default | Allow-list hosts; resolve and reject private, loopback, and link-local ranges (169.254.169.254) in a custom `DialContext`, checked *after* DNS resolution; set `CheckRedirect` |
| Open redirect (CWE-601) | `http.Redirect(w, r, userURL, ...)`, `c.Redirect` with `next` or `return_to` parameters | Allow-list targets, or relative paths only (reject `//host` and `/\host`) |
| Deserialization (CWE-502) | `encoding/gob` from untrusted sources; YAML decoding into `interface{}` or `map[string]interface{}` that drives behavior; JSON into structs that include privileged fields (mass assignment, CWE-915) | Decode into narrow DTOs; `json.Decoder.DisallowUnknownFields`; separate input structs from persistence models |
| XXE (CWE-611) | Go's `encoding/xml` doesn't resolve external entities. The risk is cgo bindings to libxml2 with entity loading enabled | Stay on `encoding/xml`; for libxml bindings, confirm entity loading is disabled |
| Weak randomness (CWE-338) | `math/rand` or `math/rand/v2` for tokens, session IDs, password resets, nonces | `crypto/rand` (`rand.Read`, or `rand.Text` in Go 1.24+) |
| TLS misuse (CWE-295) | `tls.Config{InsecureSkipVerify: true}`; custom `VerifyPeerCertificate` that accepts all; `MinVersion` below TLS 1.2 | Default verification; `MinVersion: tls.VersionTLS12` or 1.3 |
| Weak crypto (CWE-327, CWE-916) | `crypto/md5` or `crypto/sha1` for passwords or signatures; unsalted SHA-256 for passwords; `crypto/des`, `crypto/rc4`; AES-ECB built by hand; GCM with a reused nonce | `golang.org/x/crypto/argon2`, `bcrypt`, or `scrypt` for passwords; AES-GCM or ChaCha20-Poly1305 with a random nonce; `crypto/hmac` with `hmac.Equal` |
| Timing comparison (CWE-208) | `==` or `bytes.Equal` on secrets, tokens, HMACs | `subtle.ConstantTimeCompare`, `hmac.Equal` |
| ReDoS (CWE-1333) | Go's `regexp` is RE2 (linear time), so classic catastrophic backtracking doesn't apply. Third-party backtracking engines (for example `dlclark/regexp2`) on untrusted input still do | Stay on `regexp`; set timeouts on backtracking engines |
| File upload (CWE-434) | `c.SaveUploadedFile` or `os.Create` with the client filename; type trusted from `Content-Type` or the extension; files saved under a served directory | Generate server-side names; detect type from content (`http.DetectContentType`) plus an allow-list; store outside the web root |
| Unbounded input / decompression bomb (CWE-400, CWE-409) | `io.ReadAll(r.Body)` without a limit; `gzip.NewReader` or `zip` extraction without a size cap; no `MaxBytesReader` | `http.MaxBytesReader`, `io.LimitReader`; cap the decompressed size and the entry count |
| Log injection (CWE-117) | Logging raw input with `log.Printf("%s", input)` into line-based logs | Structured logging (`log/slog`) with fields; strip CR/LF |
| Header injection (CWE-113) | Setting headers from input. `net/http` rejects CR/LF in header values, but a custom writer may not | Validate; rely on `net/http` validation |

## Authentication, authorization, and session

- **Route coverage:** check that every route is behind the auth middleware. Look for routes registered before `router.Use(auth)` in Gin or Echo, or on a router group without it. With Chi, check each `r.Group` and `r.Route` that registers sensitive routes.
- **Object-level authorization (CWE-639):** handlers that load by ID (`db.First(&order, id)`) without scoping to the caller (`WHERE user_id = ?`) are IDOR candidates.
- **JWT** (`golang-jwt/jwt/v5`):
  - The `Keyfunc` must check `token.Method` against the expected algorithm, or use `jwt.WithValidMethods`.
  - Validate `exp`, `aud`, and `iss` (`jwt.WithAudience`, `jwt.WithIssuer`).
  - The signing key must not be hard-coded.
- **Cookies:** set `HttpOnly`, `Secure`, and `SameSite` on session cookies. With `gorilla/sessions`, the session key must come from a secret store.
- **CSRF:** use `gorilla/csrf` or the framework middleware for cookie-authenticated, state-changing routes. Go 1.25 adds `http.CrossOriginProtection`.
- **CORS:** `AllowOrigins: ["*"]` together with `AllowCredentials: true`, or reflecting `Origin` without an allow-list, is a finding.
- **Rate limiting:** login, password reset, and OTP endpoints need it (CWE-307).

## Language-specific issues

- **Data races (CWE-362):**
  - Maps and slices shared across goroutines without a `sync.Mutex`; concurrent map writes crash the process.
  - Handler-scoped state stored in package-level variables.
  - Check-then-act on balances or quotas without a transaction or row lock.
- **Goroutine leaks and unbounded concurrency (CWE-400):** a goroutine per request with no cancellation (`context`) or bound, or channels that are never drained.
- **Integer conversion (CWE-190, CWE-681):**
  - `strconv.Atoi` into `int`, then a cast to `int32`, `uint`, or `uint16` without range checks.
  - Lengths from input used for `make([]byte, n)` without a cap.
- **Ignored errors (CWE-252, CWE-754):** `_ = ...` or unchecked errors from auth, crypto, `rows.Err()`, `tx.Commit()`, and `Close` on writers. These fail open.
- **`unsafe` and cgo (CWE-119):** `unsafe.Pointer` arithmetic, `unsafe.Slice` and `unsafe.String` on input-derived lengths, and cgo buffers. Review these like C.
- **`defer` in loops:** `defer f.Close()` inside a loop over user-supplied files exhausts file descriptors (CWE-775).
- **Panics:** a `recover`-less goroutine panicking on malformed input crashes the whole service. `net/http` recovers handler panics, but goroutines a handler spawns are not covered.
- **Server timeouts:** `http.ListenAndServe` with the default `http.Server` has no `ReadHeaderTimeout`, `ReadTimeout`, or `WriteTimeout`, which exposes the service to Slowloris (CWE-400).

## Configuration

- **Debug endpoints:** `net/http/pprof` imported (`_ "net/http/pprof"`) and reachable on a public listener. `expvar` exposed. Gin left in `gin.DebugMode` in production.
- **Secrets:** read from environment variables or flags. Check that defaults aren't real secrets (`os.Getenv("KEY")` falling back to a literal).
- **TLS:** check `tls.Config` for weak cipher suites or `MinVersion`, and certificate verification turned off for internal calls.
- **Errors:** responses returning `err.Error()` from database or internal calls expose internals (CWE-209).

## Dependencies and build

- **Manifests:** `go.mod` declares the dependencies; `go.sum` must be committed. Check `replace` directives that point to forks or local paths, and `GOSUMDB=off`, `GONOSUMDB`, `GOPRIVATE`, or `GOINSECURE` settings that bypass the checksum database (and `-mod=mod` in CI, which lets `go.mod` change during the build).
- **Reachability:** `govulncheck` reports whether vulnerable symbols are called. Use that in triage.
- **Code execution:**
  - `go generate` runs arbitrary commands listed in `//go:generate` comments.
  - cgo builds compile C code.
  - Tests and `init()` functions execute on `go test` and `go run`.
  - Running `go build` or `go vet` on the module may download modules.
  - **Ask before running any of these.** Reading the source is always safe.

## Quick search patterns

Candidates only; each hit still goes through `triage.md`.

```
fmt\.Sprintf\([^)]*(SELECT|INSERT|UPDATE|DELETE|WHERE|ORDER BY)
\.(Raw|Exec|Query|QueryRow|Where|Order)\(\s*(fmt\.Sprintf|"[^"]*"\s*\+)
exec\.Command(Context)?\(\s*"(sh|bash|cmd|powershell)"
text/template
template\.(HTML|JS|URL|CSS)\(
InsecureSkipVerify:\s*true
"math/rand
crypto/(md5|sha1|des|rc4)
http\.(Get|Post|Head)\(\s*[a-zA-Z_]
http\.Redirect\(
filepath\.Join\([^)]*(Param|Query|FormValue|PathValue)
io\.ReadAll\(\s*(r|c\.Request)\.Body
_ "net/http/pprof"
encoding/gob
unsafe\.
jwt\.Parse(WithClaims)?\(
AllowOrigins|AllowAllOrigins
```
