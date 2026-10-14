# Security

Read this before writing anything that handles untrusted input, authentication, authorisation, crypto, or outbound requests — and when reviewing code for security. Security findings outrank style findings; report them first and be specific about the exploit path.

## Contents
- [Threat priorities](#threat-priorities)
- [Access control](#access-control)
- [Injection](#injection)
- [SSRF](#ssrf)
- [Path traversal and file uploads](#path-traversal-and-file-uploads)
- [XML and XXE](#xml-and-xxe)
- [Deserialization](#deserialization)
- [Expression injection](#expression-injection)
- [Spring Security configuration](#spring-security-configuration)
- [Authentication and tokens](#authentication-and-tokens)
- [Password storage](#password-storage)
- [Cryptography](#cryptography)
- [Secrets](#secrets)
- [Supply chain](#supply-chain)
- [Logging and error handling](#logging-and-error-handling)
- [JVM and runtime hardening](#jvm-and-runtime-hardening)
- [Review checklist](#review-checklist)

## Threat priorities

The OWASP Top 10 was refreshed in 2025. The current categories, in order:

1. **Broken Access Control** — still number one, and the one most often introduced by ordinary feature work.
2. **Security Misconfiguration**
3. **Software Supply Chain Failures** — broadened from the old "vulnerable and outdated components".
4. **Cryptographic Failures**
5. **Injection**
6. **Insecure Design**
7. **Authentication Failures**
8. **Software or Data Integrity Failures**
9. **Security Logging and Alerting Failures**
10. **Mishandling of Exceptional Conditions** — new; error paths that leak information, fail open, or skip cleanup.

Two implications for how you work. First, **access control is where the bugs are** — not exotic crypto. Every new endpoint and every new query is an access-control decision, and the most common vulnerability in a Spring application is an endpoint that authenticates the caller but never checks that the requested resource belongs to them. Second, **error paths are now explicitly in scope**: a `catch` block that swallows a failure and continues, or returns a default that happens to mean "allowed", is a security defect.

## Access control

```java
// Authorise on the DATA, not just the route.
@PreAuthorize("hasRole('ADMIN')")
public void deleteAccount(UUID accountId) { ... }

public Invoice get(UUID invoiceId, UUID callerId) {
    var invoice = repository.findById(invoiceId).orElseThrow(() -> new InvoiceNotFoundException(invoiceId));
    if (!invoice.belongsTo(callerId)) {
        throw new InvoiceNotFoundException(invoiceId);   // 404, not 403 — do not confirm existence
    }
    return invoice;
}
```

- **Deny by default.** Configure `anyRequest().authenticated()` and open specific paths, never the reverse. A new endpoint should be unreachable until someone deliberately permits it.
- **Check ownership on every read and write, including the "boring" ones.** `GET /invoices/{id}` with no ownership check is IDOR, and it is the single most common real vulnerability in CRUD services. Scoping the query itself (`findByIdAndAccountId`) is more robust than fetching then checking, because it cannot be forgotten in one branch.
- **Never trust a client-supplied identity.** The user id comes from the authenticated principal, never from a request body, path, or header the client controls.
- **Mass assignment:** binding a request directly onto an entity lets a caller set `role`, `balance`, or `ownerId`. Use DTOs with exactly the fields the caller may set — this is one of the strongest arguments for DTOs at the boundary.
- **Protect every surface**, not just REST: Actuator endpoints, GraphQL resolvers, message consumers, scheduled admin jobs, and anything reachable through a service mesh.
- **Test authorisation explicitly.** A test that asserts user B gets 404 for user A's resource is cheap and catches the regression that a code review will not.

## Injection

The fix is always the same shape: **never let data become code.** Bind parameters; do not build statements from strings.

```java
// Safe — bound parameters
jdbcClient.sql("SELECT * FROM invoice WHERE status = :status")
          .param("status", status.name()).query(Invoice.class).list();

em.createQuery("select i from Invoice i where i.accountId = :acct", Invoice.class)
  .setParameter("acct", accountId);

// Unsafe — concatenation, in any form
"SELECT * FROM invoice WHERE account_id = '" + accountId + "'"
String.format("... WHERE name LIKE '%%%s%%'", userInput)
"""
SELECT * FROM invoice WHERE status = '%s'""".formatted(status)
```

Specifics that catch people out:

- **Identifiers cannot be parameterised.** Table names, column names, and `ORDER BY` directions must come from an **allowlist** (map the request value to an enum or a known constant), never from input.
- **Spring Data `Sort`/`Pageable` injection.** A controller that accepts `Sort` straight from query parameters and feeds it to a **native query** passes attacker-controlled property names into the generated SQL — Spring Data does not validate them against anything. Map the incoming sort field through an allowlist before constructing `Sort`, and treat `JpaSort.unsafe()` as something you only use on input you validated yourself.
- **`@Query` with SpEL** (`?#{...}`) evaluates an expression; user input must never reach the SpEL-evaluated portion.
- **Least privilege for the database account** — the application should not own its schema or hold DBA rights. Migrations can run under a different account.
- The same rule governs **LDAP filters, OS commands (prefer `ProcessBuilder` with an argument list, never a shell string), NoSQL queries, and template engines**.
- For **XSS**, the server-side responsibilities are: set `Content-Type: application/json` on APIs so responses are not sniffed as HTML, escape by default in any server-side template (Thymeleaf does; `th:utext` opts out — justify every use), and send a restrictive `Content-Security-Policy`. Never reflect raw input into HTML.

## SSRF

Any feature that fetches a user-supplied URL — webhooks, image imports, "verify my endpoint" — is an SSRF risk, and cloud metadata services make it severe.

- **Allowlist destinations** by host; blocklists get bypassed.
- **Resolve, validate, then connect to the resolved IP.** Validating a hostname and then letting the client re-resolve it leaves a DNS-rebinding race where the second lookup returns an internal address.
- **Disable redirect following** (`HttpClient.Redirect.NEVER`), or re-validate the target of every redirect — a redirect to `169.254.169.254` bypasses a check done only on the original URL.
- **Reject internal ranges** explicitly: the cloud metadata address `169.254.169.254`, link-local, loopback (`127.0.0.0/8`, `::1`), and RFC1918 (`10/8`, `172.16/12`, `192.168/16`). Enforce at the network layer too — egress rules are the control that survives an application bug.
- Restrict the **scheme** to `https` (no `file:`, `gopher:`, `jar:`), set tight timeouts, and cap response size.

## Path traversal and file uploads

```java
Path base = Path.of("/srv/uploads").toAbsolutePath().normalize();
Path target = base.resolve(userSuppliedName).normalize();
if (!target.startsWith(base)) {
    throw new IllegalArgumentException("Path escapes upload directory");
}
```

Normalise and then verify containment — checking for `".."` in the string is defeated by encoding and by symlinks. Better still: **do not use client-supplied names as paths at all.** Generate a server-side identifier, store the original name as metadata.

For uploads: enforce a size limit (`spring.servlet.multipart.max-file-size` *and* a reverse-proxy limit), validate the content type by inspecting the bytes rather than trusting the header or extension, store outside the web root, never serve uploads from a path where they could be executed, and set `Content-Disposition: attachment` plus `X-Content-Type-Options: nosniff` when serving them back.

## XML and XXE

XML parsers are unsafe by default. Harden every factory you create — and prefer JSON when you have the choice.

```java
// DOM
var dbf = DocumentBuilderFactory.newDefaultInstance();
dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

// SAX
var spf = SAXParserFactory.newDefaultInstance();
spf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
spf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);

// StAX
var xif = XMLInputFactory.newDefaultFactory();
xif.setProperty(XMLInputFactory.SUPPORT_DTD, false);
xif.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);

// XSLT
var tf = TransformerFactory.newDefaultInstance();
tf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

// Schema validation
var sf = SchemaFactory.newDefaultInstance();
sf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
sf.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
sf.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
```

`disallow-doctype-decl` is the strongest single setting because it also stops billion-laughs entity-expansion DoS. Wrap this configuration in one factory method so no call site can forget it.

## Deserialization

**Never deserialize untrusted data with Java serialization.** Gadget chains in common libraries turn `readObject` into remote code execution, and no amount of input validation fixes it. Use JSON (or protobuf) with explicit types.

Where Java serialization is unavoidable (legacy RMI, a session store, a cache):

- Apply a **serialization filter** — `ObjectInputFilter` with an explicit allowlist, plus `maxdepth`, `maxrefs`, `maxbytes`, and `maxarray` limits (JEP 290). Pattern syntax: `example.Allowed;example.data.*;!*` — allow the specific classes you need, then reject everything else.
- Set it globally via the `jdk.serialFilter` property, or per-stream. Since JDK 17, a **filter factory** (`ObjectInputFilter.Config.setSerialFilterFactory`, JEP 415) lets different contexts apply different filters.
- The belt-and-braces version is overriding `resolveClass` with an allowlist check.

**Jackson:** the danger is polymorphic deserialization against attacker-controlled type names.

- Never call the legacy global default typing (`enableDefaultTyping()`).
- If you need polymorphism, use `@JsonTypeInfo(use = Id.NAME)` with an explicit `@JsonSubTypes` registry, so only types you listed can be instantiated. `Id.CLASS` with no validator lets the attacker name the class.
- If you must enable default typing, do it with a `PolymorphicTypeValidator` restricted to your own base types.
- Keep `jackson-databind` current; a long tail of gadget CVEs has been fixed by version, and the maintained blocklist only helps if you are on a recent release. Check the project's actual version against the current advisories rather than assuming.
- Also avoid `XMLDecoder` and old XStream on untrusted input entirely.

## Expression injection

Spring's expression language is powerful enough to be an RCE primitive. Two real precedents are worth remembering as the shape of the bug: a SpEL expression taken from a request header and evaluated (Spring Cloud Function, CVE-2022-22963), and data binding reaching a `ClassLoader` property path on a WAR-deployed app ("Spring4Shell", CVE-2022-22965).

Rules:
- **Never evaluate an expression built from user input.** If you genuinely need user-authored expressions, use `SimpleEvaluationContext` (data access only — no method or constructor invocation) rather than `StandardEvaluationContext`, and sandbox the root object.
- The same applies to template engines, rule engines, and anything that compiles input.
- Keep framework versions current; expression-layer vulnerabilities are patched by upgrade, not by application code.

## Spring Security configuration

The lambda DSL is the only supported style — the old `.and()` chaining has been removed, not merely deprecated.

```java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity                                   // enables @PreAuthorize
class SecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health/**").permitAll()
                .requestMatchers("/actuator/**").hasRole("OPS")
                .requestMatchers(HttpMethod.POST, "/api/invoices").hasAuthority("SCOPE_invoice.write")
                .anyRequest().authenticated())           // deny by default
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .sessionManagement(s -> s.sessionCreationPolicy(STATELESS))
            .csrf(AbstractHttpConfigurer::disable)       // correct ONLY for a stateless, token-auth API
            .cors(Customizer.withDefaults())             // picks up the CorsConfigurationSource bean
            .headers(h -> h
                .contentSecurityPolicy(csp -> csp.policyDirectives("default-src 'self'; frame-ancestors 'none'"))
                .httpStrictTransportSecurity(hsts -> hsts.includeSubDomains(true)))
            .build();
    }
}
```

- **CSRF:** disable it only when the session is truly stateless and credentials are not sent automatically by the browser. If the app is a cookie-session SPA, keep CSRF on — recent Spring Security versions offer `csrf(csrf -> csrf.spa())`, which wires a JS-readable cookie repository plus a BREACH-safe deferred token handler and refreshes the token on login/logout. Verify the method exists in the project's version before using it; otherwise configure `CookieCsrfTokenRepository.withHttpOnlyFalse()` and `XorCsrfTokenRequestAttributeHandler` by hand.
- **CORS** must be configured as a `UrlBasedCorsConfigurationSource` bean so Spring Security picks it up; preflight `OPTIONS` requests carry no credentials, so CORS has to be evaluated ahead of authentication. Never use `allowedOrigins("*")` together with `allowCredentials(true)` — Spring rejects it, and for good reason.
- **Method security** (`@PreAuthorize`) complements URL rules and is where ownership expressions belong. It is proxy-based: self-invocation bypasses it, exactly like `@Transactional`.
- **Never disable security by profile.** A `@Profile("!prod")` permit-all chain becomes a production incident the first time someone's deployment misses an environment variable.
- Set security headers, enforce HTTPS (HSTS plus a redirect at the edge), and mark session cookies `Secure`, `HttpOnly`, `SameSite=Lax` or stricter.

## Authentication and tokens

For a JWT resource server, configuring the issuer is not enough:

- **Validate `iss` and `aud`.** Issuer-only validation means a token minted for service A is accepted by service B when both trust the same identity provider. Spring Boot exposes an audiences property; otherwise compose `JwtValidators.createDefaultWithIssuer(issuer)` with a `JwtClaimValidator<List<String>>(AUD, aud -> aud.contains(expected))` through a `DelegatingOAuth2TokenValidator` and set it on the decoder.
- **Verify the signature against JWKS fetched over HTTPS**, pin the expected algorithm, and reject `alg: none` and HMAC tokens where you expect RSA/EC (algorithm confusion).
- **Check expiry with a small clock skew**, and keep token lifetimes short.
- **Do not put secrets or authorisation decisions you cannot revoke in the token.** A JWT is a bearer credential: anyone holding it is the user until it expires. Scope it narrowly, transmit over TLS only, and never log it or put it in a URL.
- For sessions: regenerate the session id on login (Spring Security does this by default — do not disable it), invalidate on logout, and set an idle timeout.
- Rate-limit and lock out on authentication endpoints; return the same generic message and similar timing for "unknown user" and "wrong password" so the endpoint is not a user enumeration oracle. Apply the same reasoning to password reset and registration.
- Prefer an identity provider over hand-rolled authentication. If you do implement it, use Spring Security's building blocks rather than writing filters from scratch.

## Password storage

Use `DelegatingPasswordEncoder` so hashes carry their algorithm (`{bcrypt}$2a$...`) and can be upgraded in place:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();   // bcrypt by default
}
```

Current OWASP minimum parameters — tune upward so verification takes roughly **one second on your production hardware**, which is the actual rule:

| Algorithm | Minimum parameters | Notes |
|---|---|---|
| **Argon2id** (preferred) | m = 19456 KiB (19 MiB), t = 2, p = 1 | `Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()` |
| **scrypt** | N = 2^17, r = 8, p = 1 | ~128 MiB of memory |
| **bcrypt** | cost ≥ 10 | **Truncates input at 72 bytes** — pre-hash with SHA-256 if you allow long passphrases |
| **PBKDF2** | 600,000 iterations (HMAC-SHA256) / 220,000 (SHA512) | Use when FIPS compliance requires it |

Never use MD5, SHA-1, SHA-256, or any unsalted fast hash for passwords. Never implement your own. Never log or store the plaintext, even transiently, and do not put it in an exception message.

## Cryptography

Use vetted primitives through a high-level library wherever possible; hand-assembled crypto fails in ways tests do not reveal.

- **AES-256-GCM** for symmetric encryption — it authenticates as well as encrypts. ECB is never acceptable; CBC needs a separate MAC and careful padding handling, so prefer GCM.
- **Never reuse a (key, nonce) pair under GCM.** A repeated nonce destroys both confidentiality and authenticity. Generate a fresh 12-byte nonce from `SecureRandom` per encryption, store it alongside the ciphertext, and rotate keys before approaching the data-volume limits in NIST SP 800-38D.
- **`SecureRandom` for anything security-relevant** — keys, nonces, tokens, password-reset codes, session ids. `Math.random()`, `java.util.Random`, and `ThreadLocalRandom` are predictable and must never be used here, however convenient.
- **Derive keys properly** (HKDF/PBKDF2/Argon2 as appropriate); never use a password directly as an AES key.
- **Verify TLS certificates.** A custom `TrustManager` that accepts everything, or a hostname verifier that returns true, is a complete defeat of transport security — and it shows up in codebases as a "temporary" fix. Fix the trust store instead.
- Keep secrets out of `String` where you can: strings are immutable, interned, and visible in heap dumps. Use `char[]`/`byte[]` and zero them after use.
- Prefer the platform providers; add BouncyCastle only for algorithms the JDK lacks.

## Secrets

- **Never in source control**, including tests, fixtures, docs, and example config. A committed secret is compromised even after the commit is reverted — rotate it.
- **Never in `application.yaml`** that ships in the artifact. Supply configuration from the environment or, better, a secret manager (Vault, cloud KMS/secret services) with short-lived dynamic credentials and automated rotation. Environment variables are the common baseline but are visible via `/proc`, inherited by child processes, and can appear in crash dumps — a vault is the stronger option.
- **Never in logs or error responses.** Scrub tokens, keys, and `Authorization` headers from any diagnostic output, and be careful with libraries that log request details at DEBUG.
- Add a **secret scanner** to CI so this is enforced rather than remembered.

## Supply chain

Now a top-three OWASP category, and the risk is not only known CVEs but also compromised releases.

- **Pin and manage versions centrally** — the Spring Boot BOM plus a dependency-management block. Avoid version ranges, which make builds non-reproducible.
- **Scan continuously**, not once: OWASP dependency-check (CPE/NVD-based; needs an NVD API key and produces some false positives for Java artifacts) or a coordinate-based scanner such as Sonatype OSS Index (generally fewer false positives for Maven coordinates). Running one in CI with a build-failing threshold is the point; which one matters less.
- **Generate an SBOM** in CycloneDX format (now an Ecma standard, with good Maven/Gradle plugin support) and publish it with the artifact so vulnerabilities can be matched to deployments later.
- **Verify provenance** where your platform supports it — signed artifacts and transparency-log attestation (Sigstore/SLSA) defend against a tampered release that a CVE scanner cannot see.
- **Review new dependencies** before adding them: maintenance activity, transitive weight, licence, and whether the JDK already does the job. Every dependency is code you ship and must patch.
- **Keep the JDK and framework patched.** Most exploited Java vulnerabilities are old and fixed; the gap is upgrade latency, not unknown bugs.

## Logging and error handling

- **Never log credentials, tokens, keys, full card numbers, or personal data.** Log identifiers, not payloads.
- **Sanitise untrusted data before logging it** — strip CR/LF so an attacker cannot forge log lines, and be aware that log viewers interpret some content.
- **Never return stack traces, SQL, or internal class names to clients** (`server.error.include-stacktrace=never`). Return a correlation id and log the detail server-side.
- **Log security events** — authentication failures, authorisation denials, privilege changes, token issuance — with enough context to investigate, and make sure they reach somewhere that alerts. "Logging and alerting failures" is in the Top 10 because an undetected breach lasts longer.
- **Fail closed.** An exception in an authorisation path must deny, never fall through to allow. Audit `catch` blocks on security paths specifically — the new "mishandling of exceptional conditions" category is about exactly this.
- Historical note worth internalising: Log4Shell was a logging library evaluating lookups inside message content. Keep logging dependencies patched, and never pass untrusted input as a *format/pattern* rather than as an argument.

## JVM and runtime hardening

- **The Security Manager is gone.** JEP 411 deprecated it, and from JDK 24 (JEP 486) `System.setSecurityManager` throws and the JVM refuses to start with `-Djava.security.manager`. Sandboxing now belongs to the container and OS: non-root user, read-only root filesystem, dropped capabilities, seccomp, network egress policy. In-JVM, the replacements for specific concerns are serialization filters, JAXP secure processing, FFM instead of JNI, and JFR for monitoring.
- **Native access is being restricted.** FFM and JNI calls warn by default and can be denied (`--illegal-native-access=deny`); grant `--enable-native-access` narrowly to the module that needs it rather than `ALL-UNNAMED`.
- Run with a **JRE or `jlink`ed runtime**, not a full JDK, in production images.
- **Lock down Actuator**: expose only `health` publicly, require a role for the rest, and never expose `env`, `heapdump`, `threaddump`, or `loggers` unauthenticated — `heapdump` hands over every secret in memory.
- Disable directory listing and default error pages, remove sample/debug endpoints, and keep debug ports closed.
- Use static analysis as a gate: SpotBugs with the FindSecBugs plugin, Error Prone, and the dependency scanner (`build-quality.md`).

## Review checklist

Work through this when writing or reviewing anything that touches untrusted input:

- [ ] Every endpoint authenticates **and** authorises the specific resource, not just the route
- [ ] Ownership checks are in the query (`findByIdAndOwnerId`), not bolted on afterwards
- [ ] Request bodies bind to DTOs with only client-settable fields; no entity binding
- [ ] All input validated at the boundary; identifiers and sort fields come from an allowlist
- [ ] Every query uses bound parameters; no string-built SQL/JPQL anywhere, including `ORDER BY`
- [ ] Outbound URLs from user input are allowlisted, redirect-restricted, and blocked from internal ranges
- [ ] File paths normalised and verified inside the base directory; upload names not used as paths
- [ ] XML parsers hardened; no Java deserialization of untrusted data; Jackson polymorphism restricted to a named registry
- [ ] No user input reaches SpEL, a template, or any evaluator
- [ ] Passwords hashed with Argon2id/bcrypt at current parameters; tokens validated for issuer, audience, signature, algorithm, and expiry
- [ ] Secrets come from the environment or a vault; none in source, config, logs, or responses
- [ ] Errors return no internals; security events are logged; failures deny rather than allow
- [ ] Dependencies scanned and current; SBOM produced
- [ ] Authorisation, rejection, and failure paths have tests — not just the happy path
