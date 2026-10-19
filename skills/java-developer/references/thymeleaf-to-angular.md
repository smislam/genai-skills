# Converting Thymeleaf views to Angular

Read this when migrating a legacy Spring MVC application whose UI is server-rendered with Thymeleaf. When modernizing such a project, the UI moves to an Angular single-page application backed by a JSON REST API. Do this as its **own phase**, after the Java and Spring Boot upgrade is green and released (`migration.md`). Never mix it into the same commits as the runtime upgrade: a UI rewrite and a framework upgrade in one diff make every regression unattributable. If the user explicitly wants to keep Thymeleaf, skip this phase and say so in the migration report.

Use the current Angular major release, and check angular.dev for it and for the Node.js versions it supports, rather than relying on a remembered version. Write to its current defaults:
- standalone components (no NgModules);
- signals for component state;
- the built-in control flow (`@if`, `@for`, `@switch`);
- typed reactive forms;
- `HttpClient` with functional interceptors.

## Contents
- [1. Inventory the UI](#1-inventory-the-ui)
- [2. Target architecture](#2-target-architecture)
- [3. Backend: from views to a REST API](#3-backend-from-views-to-a-rest-api)
- [4. Thymeleaf to Angular, construct by construct](#4-thymeleaf-to-angular-construct-by-construct)
- [5. Forms and validation](#5-forms-and-validation)
- [6. Internationalization](#6-internationalization)
- [7. Security: sessions, CSRF, authorization](#7-security-sessions-csrf-authorization)
- [8. Static assets and styles](#8-static-assets-and-styles)
- [9. Migrating page by page](#9-migrating-page-by-page)
- [10. Testing for parity](#10-testing-for-parity)
- [11. Pitfalls](#11-pitfalls)

## 1. Inventory the UI

Before writing Angular code, build a page map; it goes into the migration report. For every Thymeleaf template, record:

| Column | What to record |
|---|---|
| Template | `templates/owners/createOrUpdateOwnerForm.html` |
| Served by | The controller handler(s) returning that view, with the HTTP method and path (`GET`/`POST /owners/new`) |
| Model | The model attributes it reads (`owner`, `types`), and where each comes from |
| Forms | Each `th:object` form: fields, validation, submit target, and the redirect after success |
| Fragments and layout | `th:fragment`, `th:replace`, `th:insert`, and layout-dialect decorators it uses or provides |
| Messages | `#{…}` message keys |
| Scripts | Inline or linked JavaScript, and jQuery plugins |
| Access | Who can see it (`sec:authorize`, URL security rules) |
| Usage | Request counts, if available (`legacy-assessment.md`). A template with no traffic may be dead: confirm before converting it |

Templates that no handler returns are candidates for dead code. Report them rather than converting them.

## 2. Target architecture

- **Backend:** Spring Boot `@RestController`s under a distinct prefix (`/api/...`), returning DTOs as records, and documented with OpenAPI (springdoc), so the Angular client can be typed from the contract.
- **Frontend:** an Angular application in its own folder in the same repository (for example `frontend/`), with routes mirroring the old URLs where possible, so bookmarks keep working.
- **Serving.** Two options:
  - **One deployable (the default for a legacy migration):** the build compiles the Angular app (frontend-maven-plugin, or the Gradle Node plugin) and copies the output into Spring Boot's static resources. One origin means session cookies and CSRF work without CORS, and deployment doesn't change.
  - **Separate hosting** (a CDN or another server): only when the organization standard requires it. It needs CORS, or a backend-for-frontend, and changes how authentication works.
- **SPA fallback (one deployable).** Unknown non-API, non-file paths must return `index.html`, so deep links and browser refreshes work. Use a controller forwarding to `/index.html` for paths without a file extension, excluding `/api/**` and `/actuator/**`.

## 3. Backend: from views to a REST API

| Thymeleaf-era Spring MVC | REST API |
|---|---|
| `@Controller` method returning a view name and filling `Model` | `@RestController` method returning a DTO (`record OwnerView(...)`) |
| Entities passed to the template | DTOs. Never serialize JPA entities: that leaks fields, triggers lazy loading, and can recurse |
| `POST` form, then `redirect:/owners/{id}` (post/redirect/get) | `POST /api/owners` returns `201 Created` with `Location` and the created DTO; the client navigates |
| `BindingResult` errors re-rendered in the form | `400` with an RFC 9457 `ProblemDetail` listing field errors (section 5) |
| `RedirectAttributes` flash messages | The client shows the message after a successful response |
| `@ModelAttribute` methods filling dropdowns | A small endpoint (`GET /api/pet-types`), cached client-side |
| `setDisallowedFields` in `@InitBinder` | Request DTOs that don't contain the field at all. This is safer than a deny-list |
| Paging via `Page<T>` in the model | A page DTO (`content`, `page`, `size`, `totalElements`), or Spring Data's paged-model JSON |
| Error pages (`error.html`) | `ProblemDetail` responses; the client renders error states |

Keep the old view endpoints working until each page is cut over (section 9). The API is added alongside them, not in their place.

## 4. Thymeleaf to Angular, construct by construct

| Thymeleaf | Angular |
|---|---|
| `th:text="${owner.lastName}"` | `{{ owner().lastName }}`. Interpolation is escaped, like `th:text` |
| `th:utext="${html}"` | `[innerHTML]="html"`, which Angular sanitizes. Treat every `th:utext` as an XSS review point: is the content trusted, and does it need HTML at all? |
| `th:if` / `th:unless` | `@if (cond) { … } @else { … }` |
| `th:each="o : ${owners}"` | `@for (o of owners(); track o.id) { … } @empty { … }` |
| `th:switch` / `th:case` | `@switch` / `@case` |
| `th:href="@{/owners/{id}(id=${o.id})}"` | `[routerLink]="['/owners', o.id]"` |
| `th:action` / `th:object` / `th:field` | A reactive form: `FormGroup` with `formControlName`; submit through a service (section 5) |
| `th:classappend`, `th:attr`, `th:attrappend` | `[class.active]="…"`, `[attr.aria-label]="…"` |
| `th:fragment` + `th:replace` / `th:insert` | A child component (`<app-owner-card [owner]="o" />`) |
| Layout dialect `layout:decorate` / `layout:fragment` | A shell component with `<router-outlet />`; the navigation and footer become components |
| `#{key(${arg})}` messages | i18n (section 6) |
| `#temporals.format(...)`, `#numbers.formatDecimal(...)` | `DatePipe`, `DecimalPipe`, `CurrencyPipe`, with the locale configured |
| `sec:authorize="hasRole('ADMIN')"` | Hide it with an `@if` on the user's roles from the API. **The UI check is cosmetic; the server must still enforce it** (section 7) |
| Inline `<script>` and jQuery | Component logic, or a directive. Remove jQuery |

## 5. Forms and validation

- **Server-side Bean Validation stays the source of truth.** Keep `@Valid` on request DTOs. Return field errors as a `ProblemDetail` with an `errors` array of `{ field, message }`. For example, a `@RestControllerAdvice` handling `MethodArgumentNotValidException` with a 400 response.
- **Mirror the obvious rules client-side** (`Validators.required`, `maxLength`, `pattern`) for fast feedback, but never rely on them alone.
- **Map server field errors onto the form** (`control.setErrors({ server: message })`), so the user sees the same messages the Thymeleaf form showed.
- **Preserve the old behaviors:** which fields are required, the formats accepted (dates, phone numbers), the text of error messages, what happens on success, and duplicate-submit protection (disable the button while a request is pending).

## 6. Internationalization

Thymeleaf reads `messages*.properties` through Spring's `MessageSource`. Choose the Angular side by how the application switches language:
- **The language is fixed per deployment, or chosen at build time:** Angular's built-in i18n (`@angular/localize`). It produces one build per locale, and the translations come from the properties files, converted by a script.
- **Users switch language at runtime** (a `?lang=` parameter, a menu, Spring's `LocaleChangeInterceptor`): a runtime translation library loading JSON per locale. Convert the properties files to JSON in the build, so they stay the single source.

Either way, convert the keys mechanically, keep a check that every key the templates used still exists, and keep the server's `MessageSource` for messages generated on the server (validation messages, emails).

## 7. Security: sessions, CSRF, authorization

- **Sessions (one deployable):** keep Spring Security's session cookie. Same origin means the browser sends it automatically.
- **CSRF.** Thymeleaf added the CSRF token to forms automatically. Angular's `HttpClient` reads a cookie named `XSRF-TOKEN`, and sends it back as the `X-XSRF-TOKEN` header on mutating requests to relative URLs. Configure Spring Security to issue that cookie: `CookieCsrfTokenRepository.withHttpOnlyFalse()`. Since Spring Security 6, also use a token request handler that works for single-page apps, as described in the Spring Security reference's "Single-Page Applications" section. Don't disable CSRF because "it's an API now": with cookie authentication it's still needed.
- **Login.** Keep form login (Angular posts to it, or redirects to a server login page), or move to OIDC. Moving to OIDC is a separate decision, so don't bundle it in.
- **Authorization stays on the server.** Every `/api/**` endpoint needs the same rules the old view endpoints had. Route guards and hidden buttons are UX only. Compare the old `SecurityFilterChain` URL rules with the new API paths explicitly, because the paths changed.
- **Unauthenticated API calls** should get `401`/`403`, not a redirect to a login page. An `HttpClient` interceptor then handles them.

## 8. Static assets and styles

- **WebJars** (`org.webjars:bootstrap`, jQuery, Font Awesome) → npm packages in the Angular app. Remove the WebJars dependencies, and `webjars-locator`, after cutover.
- **SCSS and CSS** move into the Angular project: global styles in `styles.scss`, component styles alongside components.
- **Images and fonts** move to Angular's `public/` (or `assets/`) folder. Update every reference.

## 9. Migrating page by page

Strangler-style: both UIs run side by side until every page has moved.

1. **Set up the Angular app, the build integration, and the SPA fallback,** with no pages yet. Release it.
2. **Order the pages:** read-only pages first (lists, details), then simple forms, then complex flows (multi-step forms, uploads). Take the most-used pages early, so problems surface quickly.
3. **For each page:**
   1. add the API endpoint;
   2. write the parity tests (section 10) against the *old* page;
   3. build the Angular page;
   4. route the URL to Angular;
   5. run the parity tests against the new page;
   6. remove the template and the old handler in a follow-up commit.
4. **Navigation between old and new pages** works through ordinary links during the transition. Angular routes for migrated pages; server URLs for the rest.
5. **After the last page:** remove `spring-boot-starter-thymeleaf`, the layout dialect, the Thymeleaf security extras, the WebJars, and the empty `templates/` folder. Record each removal in the report.

## 10. Testing for parity

- **End-to-end parity tests** are the characterization tests of a UI migration. Write them with Playwright (or the project's existing E2E tool) against the Thymeleaf UI *before* converting each page. Cover:
  - what's shown for known data;
  - each form's validation messages;
  - success redirects;
  - access control (a user who shouldn't see the page doesn't).

  Run the same tests against the Angular page; they must pass unchanged, apart from selectors.
- **API tests:** `@WebMvcTest` or `@SpringBootTest` with MockMvc for each new endpoint, covering status codes, the JSON shape, validation errors as `ProblemDetail`, and authorization (an anonymous call is rejected).
- **Angular unit tests** for components with logic, and for services, using the project's Angular test setup (the CLI default unless the project already uses something else).
- **Accessibility:** the old pages' labels, headings, and keyboard behavior shouldn't regress. Add an automated accessibility check (for example axe) to the E2E run.

## 11. Pitfalls

| Pitfall | Consequence | Avoid it by |
|---|---|---|
| Serializing JPA entities | Data leaks, lazy-loading exceptions, infinite recursion | DTO records per endpoint |
| Authorization only in Angular | Anyone can call the API directly | Server rules for every `/api/**` path, with tests |
| CSRF disabled for the API | Cross-site request forgery with cookie sessions | `CookieCsrfTokenRepository` and Angular's XSRF support |
| No SPA fallback | 404 on refresh or deep link | A forwarding controller for non-file paths |
| `th:utext` converted to `[innerHTML]` without review | Stored XSS | Review each case; sanitize or render as text |
| Server-side validation dropped | Invalid data accepted | Keep `@Valid`; return `ProblemDetail` field errors |
| Public pages that need search indexing | Search engines see an empty shell | Angular server-side rendering for those routes, or keep them server-rendered |
| Dates and numbers formatted differently | Users see different values | Locale-aware pipes; compare against the parity tests |
| Big-bang rewrite | Months without a releasable state | Page-by-page migration (section 9) |
