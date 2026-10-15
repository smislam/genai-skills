# AI review checklist

Scanners are good at known patterns: injection sinks, dangerous APIs, vulnerable versions, secret formats. They are weak at authorization, authentication logic, business rules, and crypto design, which OWASP calls out as hard to automate. This checklist is for the AI review pass, and it concentrates there. Use it alongside the language guide for each stack (`lang-*.md`, `iac-*.md`, `pipelines-containers.md`).

Work from the attack-surface map built in SKILL.md step 3. For each entry point, walk the request through the code: who is the caller, what are they allowed to do, and what does the code actually check?

## Access control (A01, API1, API3, API5; CWE-862, 863, 639, 284, 915)

- **Every entry point has an authorization decision.** List routes, RPC methods, GraphQL resolvers, queue consumers, and scheduled jobs. Mark which ones enforce authentication and authorization, and where. Missing checks are often the ones added last or behind a "temporary" flag.
- **Object-level checks (BOLA/IDOR).** When a handler loads a record by an ID from the request, does it verify the caller owns it or may access it? A check on the *route* (role) is not a check on the *object*. Look for `findById(requestId)` with no owner or tenant filter.
- **Property-level checks.** Can the caller read fields they shouldn't (password hashes, internal notes, other users' emails in nested objects)? Can they write fields they shouldn't (mass assignment of `role`, `tenantId`, `price`, `status`)?
- **Function-level checks.** Are admin functions protected by role on the server, not just hidden in the UI? Look for HTTP method gaps, where GET is protected but POST to the same path isn't.
- **Tenant isolation.** In multi-tenant code, where does the tenant ID come from? It must come from the authenticated principal, never from a request parameter or header the client controls. Check that every query includes it, including in background jobs and caches.
- **Default deny.** Is access granted by an allow-list, or denied by a block-list that new routes silently escape?
- **SSRF (now under A01).** Is any server-side fetch of a URL, hostname, or IP influenced by the user? Check webhooks, URL previews, PDF and image renderers, import-from-URL features, and XML external entities.

## Authentication and session (A07; CWE-287, 306, 384, 521, 798, 613)

- **Login, registration, reset, MFA, and remember-me flows.** Account enumeration through different responses or timing; reset tokens that are predictable, reusable, or never expire; MFA that can be skipped by calling the next step directly.
- **Credential storage.** Passwords hashed with a slow, salted algorithm (Argon2id, scrypt, bcrypt, or PBKDF2 with a high iteration count). No reversible encryption, no fast hashes.
- **Tokens.** JWTs: the algorithm is pinned server-side, the signature is verified, and `exp`, `aud`, and `iss` are checked. Signing keys are not hard-coded. Revocation exists where sessions must be killable.
- **Sessions.** The session ID is regenerated on login (fixation). Cookies are `Secure`, `HttpOnly`, and `SameSite` as appropriate. Sessions time out, and logout invalidates them on the server.
- **Missing authentication for critical functions** (CWE-306): health and debug endpoints, metrics, admin consoles, internal APIs exposed on the same listener.
- **OAuth and OIDC.** Exact `redirect_uri` matching; `state` and PKCE used; `nonce` checked for OIDC; no tokens in URLs where avoidable.

## Business logic (A06; API6; CWE-840, 362, 367, 841)

These have no generic signature. Reason about what the feature is *for* and how it could be abused.

- **Workflow order.** Can a step be skipped (pay before ship, verify before activate) by calling a later endpoint directly?
- **Limits and quantities.** Negative or zero quantities, integer overflow on totals, discounts applied more than once, currency rounding.
- **Races.** Check-then-act on balances, inventory, coupon redemption, or unique usernames without a transaction, row lock, or idempotency key. Look for read-modify-write across two requests.
- **Abuse of sensitive flows** (API6): sign-up, voting, ticket purchase, or messaging with no rate or volume control, where automation creates real harm.
- **Trust in client-side state**: prices, roles, or approval flags sent back from the client and trusted.

## Cryptography (A04; CWE-327, 328, 329, 330, 338, 321, 295)

- **Algorithms and modes.** No DES, 3DES, RC4, MD5, or SHA-1 for security. No ECB. AEAD (AES-GCM, ChaCha20-Poly1305) preferred over CBC without a MAC.
- **IVs and nonces.** Random, unique per message, never static or reused with the same key (fatal for GCM).
- **Randomness.** A cryptographically secure generator for tokens, IDs, reset codes, and keys.
- **Keys.** Not in source, config, or images; loaded from a KMS or secrets manager; rotated; scoped per environment.
- **TLS.** Certificate validation never disabled (`verify=False`, `InsecureSkipVerify`, trust-all managers), including in "temporary" or test-path code that ships.
- **Homegrown crypto.** Custom encryption schemes, home-made signatures, or "encoding" used as encryption. Report them and recommend a vetted library primitive.

## Injection beyond the obvious (A05)

Scanners catch direct sinks. The AI pass should look for:

- **Second-order injection.** Data stored safely, then later read back and used unsafely, for example in a report query, an admin view, or a log viewer.
- **Injection through less-watched channels**: headers, filenames, message-queue payloads, CSV and Excel exports (formula injection, CWE-1236), email headers, LDAP, XPath, GraphQL queries built from strings.
- **Template and expression injection** where user input becomes part of a template or expression, not just a template variable.
- **Prompt injection** where untrusted text reaches an LLM prompt; see the LLM section below.

## Exceptional conditions (A10; CWE-703, 754, 755, 209, 248)

- **Fail open.** Exceptions in authorization, validation, or payment checks that fall through to "allow" or "continue".
- **Swallowed errors.** Empty catch blocks around security-relevant calls; ignored return values (Go `err`, C return codes).
- **Error detail.** Stack traces, SQL errors, or internal paths returned to clients (CWE-209).
- **Resource cleanup.** Locks, transactions, or temporary files left in an unsafe state after an error.
- **Panics or crashes on input**, giving remote denial of service.

## Resource exhaustion and denial of service (API4; CWE-400, 770, 1333, 409, 674, 834, 1050)

Performance problems an attacker can trigger on purpose. Rate them with the `triage.md` matrix; most are Moderate impact, and they're higher when one cheap request takes down a shared component or runs up cloud cost. General inefficiency that an attacker can't drive goes in the performance section instead (`performance.md`).

- **Unbounded input.** No request body, upload, field, or array size limits; no limit on items per batch request (CWE-770).
- **Unbounded work per request.** User-controlled page sizes, `limit` parameters without a maximum, or "export all" endpoints that query or render everything (CWE-834). Search or filter operations without timeouts.
- **Regular expressions.** User input matched against backtracking-prone patterns, or users supplying the pattern (CWE-1333).
- **Parsers.** XML entity expansion ("billion laughs"), YAML aliases, deeply nested JSON, and zip or decompression bombs without size and ratio limits (CWE-409, CWE-776).
- **GraphQL.** No depth, complexity, or alias limits; batching that multiplies work; introspection-driven expensive queries.
- **Recursion** on attacker-controlled structure depth (CWE-674).
- **Amplification.** One request that fans out into many downstream calls, emails, webhooks, or LLM calls. Expensive operations (password hashing, PDF rendering, image processing, LLM calls) reachable without authentication or rate limiting.
- **Missing timeouts** on outbound calls, database queries, and locks, so a slow dependency ties up every worker (CWE-1088).
- **Missing rate limits** on authentication, password reset, OTP verification, and costly endpoints (also API4 and API6).
- **Cloud cost.** Auto-scaling or pay-per-use resources (Lambda, LLM tokens, egress) that a single unauthenticated client can drive without quotas: denial of wallet.

## Logging and monitoring (A09; CWE-778, 117, 532)

- Security events logged: login success and failure, access denials, privilege changes, and admin actions.
- No secrets, tokens, passwords, or full card numbers in logs (CWE-532).
- Log injection: user input written to logs without neutralizing newlines and control characters (CWE-117).

## Supply chain and integrity (A03, A08; CWE-494, 829, 1357)

- Dependencies pinned by lockfile; no install-time fetches of unpinned scripts (`curl | sh` in builds).
- Packages from private registries protected against dependency confusion (scoped names, registry pinning).
- Unsigned or unverified updates, plugins, or downloaded artifacts loaded at runtime.
- Deserialization of data from caches, queues, or cookies that an attacker could influence (also A08).

## LLM and agent code (LLM Top 10 2025, Agentic Top 10 2026)

Apply this when the code calls a model API, builds prompts, runs retrieval, or gives a model tools.

- **Prompt injection (LLM01, ASI01).** Untrusted content (user input, retrieved documents, web pages, emails, tool results) mixed into prompts. Look for clear separation, and for defenses that don't rely only on "ignore previous instructions" phrasing in the system prompt.
- **Output handling (LLM05).** Model output used as code, SQL, shell, HTML, file paths, or URLs without validation. Treat it as untrusted input.
- **Excessive agency (LLM06, ASI02, ASI03).** Tools with broader permissions than the feature needs; destructive actions without human confirmation; agent credentials with wide scope.
- **Sensitive data (LLM02, LLM07).** Secrets or personal data placed in prompts or system prompts; system prompts treated as confidential when they can be extracted.
- **Retrieval stores (LLM08).** Vector stores without per-user or per-tenant access filtering at query time.
- **Unbounded consumption (LLM10).** No limits on tokens, request rate, or recursive tool or agent loops.
- **Code execution (ASI05).** Model-generated code executed without a sandbox.
- **Memory poisoning (ASI06).** Persistent agent memory writable from untrusted input.

## Data protection (ASVS V14; CWE-200, 312, 359)

- Sensitive data (personal, health, payment, credentials) identified, and minimized in storage, responses, and caches.
- Encryption at rest for sensitive fields where the threat model calls for it; never sensitive data in URLs.
- API responses that return whole entities, leaking fields the UI doesn't show.
