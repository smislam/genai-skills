# Front-end and UI frameworks: security review guide

Covers browser-side code in Angular, React, Vue, Svelte, legacy AngularJS and jQuery, and the client and server halves of meta-frameworks (Next.js, Nuxt, SvelteKit, Remix, Astro). Electron desktop apps are covered briefly. Server-side Node frameworks (Express, NestJS, Fastify, Koa) and Next.js server code are in `lang-javascript-typescript.md`; read both for full-stack apps. Tool commands are in `tools.md`; triage rules in `triage.md`.

**The core rule: nothing in the browser is a security control.** Route guards, hidden buttons, disabled fields, client-side validation, and role checks in components improve the user experience; they don't enforce anything. Every authorization decision must be re-made on the server. A front-end finding is usually either a real client-side vulnerability (XSS, token theft, leaked secrets) or evidence of a missing *server* check. Trace it to the API it calls.

## Sources

| Entry point | Concrete APIs |
|---|---|
| URL | `location.hash`, `location.search`, `location.href`, `URLSearchParams`; router params (Angular `ActivatedRoute.snapshot.params` / `queryParams`, React Router `useParams` / `useSearchParams`, Vue Router `route.params` / `route.query`, Next.js `useSearchParams`) |
| Cross-window | `window.addEventListener('message', ...)` (`postMessage`), `window.name`, `document.referrer`, `window.opener` |
| Storage | `localStorage`, `sessionStorage`, `IndexedDB`, cookies readable by script (other code, or an earlier XSS, may have written them) |
| API responses | Data from your own API is untrusted when it contains user-generated content (comments, profile fields, file names) |
| Other | WebSocket messages, `BroadcastChannel`, service worker messages, clipboard and drag-and-drop data, third-party widget callbacks, LLM output rendered in chat UIs |

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| XSS in Angular (CWE-79) | `DomSanitizer.bypassSecurityTrustHtml` / `Script` / `Style` / `Url` / `ResourceUrl` on input; `ElementRef.nativeElement.innerHTML = ...`; `Renderer2.setProperty(el, 'innerHTML', ...)`; building component templates at runtime from input (template injection) | Angular's built-in sanitization of `[innerHTML]`, `[href]`, and `[src]`; never bypass it for input; DOMPurify before any bypass that is truly required; AOT templates only |
| XSS in React (CWE-79) | `dangerouslySetInnerHTML={{ __html: input }}`; `href={input}` or `src={input}` (`javascript:` URLs; some React versions only warn); `ref.current.innerHTML = ...`; Markdown renderers with raw HTML enabled (for example `react-markdown` with `rehype-raw`) | JSX text escaping; DOMPurify for required markup; a URL scheme allow-list (`https:`, `mailto:`); Markdown without raw HTML |
| XSS in Vue (CWE-79) | `v-html` with input; `:href` / `:src` bound to input (not sanitized); render functions using `innerHTML` in `domProps`; templates compiled at runtime from input (client-side template injection) | Mustache interpolation (escaped); DOMPurify for required markup; a URL scheme allow-list; precompiled templates |
| XSS in Svelte (CWE-79) | `{@html input}`; `href={input}` | Default escaping; DOMPurify; a URL scheme allow-list |
| XSS in AngularJS 1.x (CWE-79, CWE-1336) | Any user input that reaches a template (`{{ }}` evaluated in server-rendered HTML gives client-side template injection, a known path to script execution); `ng-bind-html` with `$sce.trustAsHtml(input)` | Treat AngularJS as end-of-life (support ended January 2022) and flag it as a dependency risk; `ng-non-bindable` on server-rendered user content; migrate |
| XSS in jQuery and DOM (CWE-79) | `$(input)` with HTML strings; `.html(input)`, `.append(input)`, `$.parseHTML(input)`; `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`; `setAttribute('href'/'src'/'on*', input)`; old jQuery versions with known XSS advisories | `.text()`, `textContent`; DOM APIs building elements; current jQuery |
| DOM-based open redirect (CWE-601) | `window.location = input`, `location.assign(input)`, `router.navigateByUrl(input)`, `router.push(input)` with a `returnUrl` or `next` from the URL | Relative paths only, starting with `/` and not `//`; an allow-list |
| `postMessage` (CWE-345, CWE-346) | `message` handlers that don't check `event.origin`, or check it with `includes`/`startsWith`; acting on `event.data` as HTML or a URL; `postMessage(secret, '*')` | An exact origin match against an allow-list; validate the message schema; specify the target origin when sending |
| Reverse tabnabbing (CWE-1022) | `window.open(url)` or `target="_blank"` to untrusted URLs without `noopener` | `rel="noopener noreferrer"`; `window.open(url, '_blank', 'noopener')`. Modern browsers imply `noopener` for `target="_blank"` links, so the real risk is `window.open` without `noopener`, or old-browser support |
| DOM clobbering (CWE-79 family) | Code reading globals or `document.<name>` that injected HTML with `id`/`name` attributes can override (for example `window.config ?? defaults`) | Explicit variable declarations; don't read config from DOM-named globals; sanitize with DOMPurify, which removes clobbering vectors |
| Prototype pollution, client side (CWE-1321) | Parsing query strings or `postMessage` data into objects with deep merge (`?__proto__[x]=y`); vulnerable query-string or merge libraries | `Object.create(null)` maps; block `__proto__`, `constructor`, and `prototype` keys; current libraries |

## Authentication, authorization, and session

- **Client-side guards are not authorization.** Angular `canActivate`/`CanActivateFn`, React Router loaders and protected-route wrappers, Vue Router `beforeEach`, and conditionally rendered admin UI all need a matching server-side check on every API they call. When you find a guarded route, find its API calls and verify the server enforces the same rule. A missing server check is the real finding (CWE-602, CWE-862).
- **Token storage.** Access or refresh tokens in `localStorage` or `sessionStorage` can be read by any XSS. Prefer `HttpOnly`, `Secure`, `SameSite` cookies, or keep tokens in memory with short lifetimes. Flag long-lived refresh tokens in web storage as High when XSS exists anywhere in the app (it's a chain; see `exploit-chains.md`).
- **OAuth in single-page apps.** Use the authorization code flow with PKCE. The implicit flow (tokens in the URL fragment) is deprecated by current OAuth guidance. Check that `state` is generated and verified, and that no client secret is embedded in the bundle.
- **CSRF with cookies.** Angular `HttpClient` sends the XSRF token only for mutating requests to relative URLs. Check for `withNoXsrfProtection()`, custom header or cookie names that don't match the server, and requests to absolute URLs. React and Vue apps using cookie authentication need an explicit CSRF strategy (`SameSite` cookies plus a token or custom header that the server checks).
- **Logout and session expiry** must clear tokens and server sessions, not just reset UI state.

## Secrets and data exposure in the bundle

Everything shipped to the browser is public, including minified code and source maps.

- **Public environment prefixes** are compiled into the bundle: `NEXT_PUBLIC_*`, `VITE_*`, `REACT_APP_*`, Nuxt `runtimeConfig.public`, SvelteKit `$env/static/public` and `$env/dynamic/public`, Astro `PUBLIC_*`, and Angular `environment.ts` / `environment.prod.ts`. Any secret there (API keys with write scope, database URLs, private keys, signing secrets) is a finding. Publishable keys meant for browsers (such as Stripe publishable keys or Firebase web config) are not secrets. Check the key type before reporting.
- **Source maps** published in production expose the original source. They're a finding only if the source contains secrets or internal endpoints, or when policy forbids them.
- **Hidden endpoints.** Admin or internal API URLs in the bundle aren't a vulnerability by themselves. Verify each one is protected on the server.
- **Sensitive data in client state**: full user records, other users' data, or feature flags that encode authorization, delivered to the browser and merely hidden by the UI.

## Meta-frameworks: server code inside the front end

Next.js, Nuxt, SvelteKit, Remix, and Astro mix server and client code in one project. Server-side pieces are API endpoints even when they look like UI code:

| Framework | Server entry points to review as public APIs |
|---|---|
| Next.js | Route handlers (`app/**/route.ts`), `pages/api/*`, server actions (`'use server'`), middleware; see `lang-javascript-typescript.md` |
| Nuxt | `server/api/*`, `server/routes/*`, `server/middleware/*` |
| SvelteKit | `+server.ts` endpoints, `+page.server.ts` `load` functions and form `actions`, `hooks.server.ts` |
| Remix / React Router framework mode | `loader` and `action` exports |
| Astro | API endpoints under `src/pages` exporting HTTP-method handlers, server islands, actions |

Each needs its own authentication, authorization, and input validation. Data returned from server `load`/`loader` functions is serialized to the client. Check that it doesn't include fields the user shouldn't see.

## Browser security headers and policies

Usually set in server config, a CDN, or the meta-framework's config (`next.config.js` `headers()`, `nuxt.config` `routeRules`, `angular.json` dev-server only). Missing headers are typically Low unless they're what makes another finding exploitable:

- **Content Security Policy.** No `unsafe-inline` or `unsafe-eval` for scripts where avoidable; nonces or hashes. Consider `require-trusted-types-for 'script'` (Trusted Types) for apps with heavy DOM manipulation.
- **Clickjacking.** `frame-ancestors` in the CSP, or `X-Frame-Options`, on pages with sensitive actions.
- **Third-party scripts.** Scripts loaded from CDNs without Subresource Integrity (`integrity=` plus `crossorigin`), and tag managers that can inject arbitrary script. On payment pages these fall under PCI DSS v4.0.1's payment-page script requirements.
- **HSTS, `Referrer-Policy`, and `Permissions-Policy`** where relevant.

## Electron (desktop apps built with web technology)

- `nodeIntegration: true`, `contextIsolation: false`, `sandbox: false`, or `webSecurity: false` in `BrowserWindow` `webPreferences` turn any XSS into code execution on the user's machine (High or Critical).
- `shell.openExternal(input)` with untrusted URLs; navigation and `window.open` not restricted (`will-navigate`, `setWindowOpenHandler`).
- Preload scripts exposing powerful APIs through `contextBridge` without validating arguments.
- Loading remote content into windows that have privileged preloads.

## Dependencies and build

- Front-end dependencies ship to every user. Prioritize advisories for libraries that render or parse untrusted content: sanitizers, Markdown renderers, rich-text editors, and query-string parsers.
- Flag end-of-life frameworks (AngularJS 1.x, old jQuery) as dependency findings with a migration path.
- Build tools (`ng build`, `vite build`, `next build`, `npm install`) run project and dependency code. Ask before running them; see `lang-javascript-typescript.md`.
