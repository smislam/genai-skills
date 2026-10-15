# Java and Kotlin: security review guide

Covers server-side Java and Kotlin on the JVM: Spring Boot, Spring MVC/WebFlux, Spring Security, Jakarta EE (Servlets, JAX-RS, JSF), JPA/Hibernate, and JDBC. Android gets a short section at the end. Tool commands are in `tools.md`; triage rules in `triage.md`.

## Sources

| Entry point | Concrete APIs and annotations |
|---|---|
| Spring MVC / WebFlux | `@RequestParam`, `@PathVariable`, `@RequestBody`, `@RequestHeader`, `@CookieValue`, `@ModelAttribute`, `@MatrixVariable`, `MultipartFile`, `ServerRequest` (functional routes) |
| Servlet API | `HttpServletRequest.getParameter`, `getHeader`, `getCookies`, `getInputStream`, `getReader`, `getPart`, `getQueryString`, `getRequestURI` |
| JAX-RS | `@QueryParam`, `@PathParam`, `@FormParam`, `@HeaderParam`, `@CookieParam`, entity parameters |
| Messaging | `@KafkaListener`, `@RabbitListener`, `@JmsListener`, `@SqsListener` payloads; Spring Cloud Stream functions |
| Scheduled and batch | Files read by Spring Batch readers; data loaded from shared buckets or databases that users write to |
| Other | `@Value`-injected config from environment, JNDI lookups, WebSocket `@MessageMapping` payloads, GraphQL `@Argument` |

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| SQL injection (CWE-89) | `Statement.execute*` with concatenation; `JdbcTemplate.query("..." + x)`; `EntityManager.createQuery` or `createNativeQuery` with concatenated JPQL/SQL; Hibernate `session.createQuery(String)` built from input; `@Query` with SpEL that concatenates; dynamic `ORDER BY` from input | `PreparedStatement` with `?`; named parameters (`:id`, `setParameter`); Spring Data derived queries; Criteria API; allow-list for sort columns and directions |
| NoSQL injection (CWE-943) | `MongoTemplate` with `BasicQuery`/`Document` built from JSON strings; `$where` with input | `Criteria.where(...).is(value)`; typed repository methods |
| OS command (CWE-78) | `Runtime.getRuntime().exec(String)`; `ProcessBuilder` with `"sh", "-c", input` | `ProcessBuilder` with a fixed binary and argument list; allow-list arguments; avoid shells |
| Expression injection (CWE-917) | `SpelExpressionParser.parseExpression(input)` with `StandardEvaluationContext`; OGNL in Struts 2; Jakarta EL `ELProcessor.eval(input)`; MVEL | Never evaluate input as an expression; if unavoidable, `SimpleEvaluationContext` with read-only data binding |
| Template injection (CWE-1336) | Thymeleaf template names or fragment selectors built from input (`return "page/" + name`); Freemarker or Velocity templates loaded from user content | Fixed view names; allow-list; Freemarker `TemplateClassResolver.SAFER_RESOLVER` or `ALLOWS_NOTHING_RESOLVER` |
| XSS (CWE-79) | Thymeleaf `th:utext`; JSP `<%= %>` and `${}` without `<c:out>` or `fn:escapeXml`; JSF `escape="false"`; writing to `HttpServletResponse.getWriter()` directly; `@ResponseBody` returning HTML strings | `th:text`; `<c:out>`; OWASP Java Encoder (`Encode.forHtml`); return JSON with the correct content type |
| Path traversal (CWE-22) | `new File(base, input)`; `Paths.get(base, input)`; `Files.newInputStream(Path.of(input))`; `ResourceLoader.getResource(input)`; `MultipartFile.getOriginalFilename()` used as a path; zip entries extracted without checks (Zip Slip) | `base.resolve(input).normalize()` then check `startsWith(base)`; generated file names; reject `..` and absolute paths |
| SSRF (CWE-918) | `RestTemplate`, `WebClient`, `HttpClient`, `URL.openConnection`, `OkHttp` with a URL from input; image or webhook fetchers | Allow-list of hosts; resolve the host and block private, loopback, and link-local ranges (including `169.254.169.254`); disable redirects or re-check after each one |
| Open redirect (CWE-601) | `return "redirect:" + url`; `response.sendRedirect(input)`; `RedirectView(input)` | Relative paths only, or an allow-list of destinations |
| Deserialization (CWE-502) | `ObjectInputStream.readObject` on untrusted data; XStream without an allow-list; Jackson default typing (`enableDefaultTyping`, `activateDefaultTyping` with a permissive validator, `@JsonTypeInfo(use = Id.CLASS)`); SnakeYAML `new Yaml().load` before 2.0; Hessian, Kryo with registration off | JSON to explicit DTOs; `ObjectInputFilter` (JEP 290) allow-lists; XStream `allowTypes`; SnakeYAML 2.x (global tags are rejected by default through `LoaderOptions`' tag inspector), or `new Yaml(new SafeConstructor(new LoaderOptions()))` |
| XXE (CWE-611) | `DocumentBuilderFactory`, `SAXParserFactory`, `XMLInputFactory`, `TransformerFactory`, `SchemaFactory`, `Unmarshaller` (JAXB) with default settings on untrusted XML | Set `disallow-doctype-decl` to true, or disable external entities and DTDs per the OWASP XXE cheat sheet |
| LDAP and XPath injection (CWE-90, CWE-643) | `DirContext.search` with a filter built from input; `XPath.evaluate("..." + input)` | Spring LDAP `LdapQueryBuilder` or encoding (`LdapEncoder.filterEncode`); XPath variables via `XPathVariableResolver` |
| Log injection (CWE-117) | Logging raw input containing CR/LF; Log4j 2 lookups in versions before 2.17.1 (CVE-2021-44228 family) | Encode or strip CR/LF; structured logging; current Log4j 2 |
| Crypto misuse (CWE-327, CWE-329, CWE-330, CWE-916) | `Cipher.getInstance("AES")` (defaults to ECB); `"DES"`, `"RC4"`, `"AES/ECB/..."`; a static or zero IV with CBC or GCM; `new Random()` or `Math.random()` for tokens; `MessageDigest` MD5 or SHA-1 for passwords; `TrustManager` accepting all certificates; `HostnameVerifier` returning true | `AES/GCM/NoPadding` with a unique 12-byte IV per message; `SecureRandom`; `BCryptPasswordEncoder`, `Argon2PasswordEncoder`, or `DelegatingPasswordEncoder`; default trust stores |
| ReDoS (CWE-1333) | `Pattern.compile` of user-supplied regexes; nested quantifiers like `(a+)+` applied to input | Don't compile user regexes; use simple patterns; limit input length |
| File upload (CWE-434) | Storing `MultipartFile` under the web root; trusting `getContentType()` or the extension | Store outside the web root with generated names; check content by magic bytes; enforce size limits (`spring.servlet.multipart.max-file-size`) |

## Authentication, authorization, and session

- **Spring Security matcher order.** In `SecurityFilterChain`, `authorizeHttpRequests` rules are evaluated in order. A broad `requestMatchers("/**").permitAll()` or `anyRequest().permitAll()` before specific rules opens everything. Check that the last rule is `anyRequest().authenticated()` or `denyAll()`.
- **Path matching mismatches.** A matcher on `/admin` doesn't cover `/admin/` or `/admin.json` in some configurations. Spring Framework 6 (Spring Boot 3) turned off MVC trailing-slash matching by default (suffix-pattern matching was already off from 5.3). The risk is a mismatch between what MVC routes and what Security matchers cover; check the versions and the actual matchers.
- **Method security not enabled.** `@PreAuthorize` and `@PostAuthorize` do nothing without `@EnableMethodSecurity` (or the older `@EnableGlobalMethodSecurity`). `@Secured` additionally needs `securedEnabled = true`, and `@RolesAllowed` needs `jsr250Enabled = true`; without the flag they are silently ignored. Check the flags, not just the annotations.
- **Self-invocation.** Spring AOP proxies skip security annotations on calls from inside the same class.
- **Object-level authorization.** Repository calls like `findById(id)` with a path variable and no ownership or tenant check (CWE-639). Look for `@PostAuthorize`, `@PreAuthorize("@guard.canRead(#id)")`, or query filters that include the principal.
- **CSRF disabled.** `csrf().disable()` (or `csrf(AbstractHttpConfigurer::disable)`) is fine for stateless token APIs, and a finding for cookie-session apps.
- **CORS.** `allowedOrigins("*")` with `allowCredentials(true)` is rejected by Spring, but `allowedOriginPatterns("*")` with credentials is accepted and dangerous.
- **Mass assignment (CWE-915).** `@ModelAttribute` or `@RequestBody` bound directly to JPA entities exposes fields like `role`, `enabled`, and `tenantId`. Use DTOs, or `WebDataBinder.setAllowedFields`.
- **JWT.** Check signature verification is on (jjwt `parseSignedClaims` or `parseClaimsJws`, never `parse` on unsigned tokens), algorithms are pinned, `exp`, `aud`, and `iss` are validated, and signing keys aren't hard-coded.
- **Sessions.** Session fixation protection is on by default in Spring Security; check it isn't set to `none()`. Check that cookies set `Secure`, `HttpOnly`, and `SameSite`.

## Language-specific issues

- **Deserialization gadgets.** Any `ObjectInputStream` on network or user data, combined with gadget libraries on the classpath (Commons Collections, Spring, Groovy), is a likely RCE. Check the dependency list during chain analysis.
- **XXE by default.** Most JDK XML factories allow DTDs unless configured. Every parser of untrusted XML needs explicit hardening.
- **JNDI and remote class loading.** `InitialContext.lookup(input)` enables JNDI injection.
- **Reflection from input.** `Class.forName(input)` and `Method.invoke` with names from requests.
- **Kotlin.** `!!` and Java platform types can turn a missing header or claim into an exception path that skips a check. This matters when exception handlers fail open (OWASP A10:2025). Kotlin string templates in SQL (`"... $id"`) are concatenation.
- **Actuator.** Exposed `/actuator/env`, `/heapdump`, `/threaddump`, `/jolokia`, `/gateway` endpoints leak secrets or allow changes.

## Configuration

- `application.yml` / `application.properties` and profile variants (`-prod`, `-dev`):
  - `management.endpoints.web.exposure.include` (avoid `*` in production)
  - `server.error.include-stacktrace` and `server.error.include-message`
  - `spring.h2.console.enabled`
  - `server.ssl.*`
  - `server.servlet.session.cookie.secure`, `http-only`, and `same-site`
  - Credentials in `spring.datasource.password`
- `web.xml`: `security-constraint`, `<http-only>`, `<secure>`, error pages.
- `logback.xml` / `log4j2.xml`: logging of request bodies or tokens.
- Debug flags: `debug=true`, `spring.devtools.*` in production builds.

## Dependencies and build

- Read `pom.xml`, `build.gradle(.kts)`, `gradle/libs.versions.toml`, lockfiles (`gradle.lockfile`), and dependency trees if already generated.
- **Builds run project code.** Maven and Gradle builds execute plugins and build scripts (`build.gradle.kts` is code). SpotBugs and Find Security Bugs need compiled classes, which means running the build. Ask before running `mvn`, `gradle`, or the wrappers (`mvnw`, `gradlew`). Wrappers also download distributions from the URL in `gradle-wrapper.properties` or `maven-wrapper.properties`, so check those URLs.
- Check for dependencies resolved from untrusted or HTTP repositories (`repositories { maven { url "http://..." } }`).

## Android (brief)

Exported components without permissions (`android:exported="true"`), `WebView.addJavascriptInterface` with `setJavaScriptEnabled(true)` on untrusted content, `MODE_WORLD_READABLE` files, and cleartext traffic (`usesCleartextTraffic`, network security config). Tag findings with the OWASP Mobile Top 10.
