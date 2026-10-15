# JavaScript and TypeScript: security review guide

Covers server-side Node.js (Express, Fastify, NestJS, Koa) and Next.js server code (API routes, route handlers, server actions, middleware). Browser-side code in Angular, React, Vue, Svelte, AngularJS, jQuery, and Electron is in `lang-frontend.md`; read both for full-stack apps. Tool commands are in `tools.md`; triage rules in `triage.md`.

## Sources

| Entry point | Concrete APIs |
|---|---|
| Express / Koa | `req.query`, `req.params`, `req.body`, `req.headers`, `req.cookies`, `req.files` (multer), `ctx.request.*` |
| Fastify | `request.query`, `request.params`, `request.body`, `request.headers` |
| NestJS | `@Query()`, `@Param()`, `@Body()`, `@Headers()`, `@UploadedFile()`, WebSocket `@MessageBody()` |
| Next.js | Route handler `request.nextUrl.searchParams`, `await request.json()`, `formData()`; server action arguments (callable from any client); `params` and `searchParams` props; `cookies()` and `headers()`; middleware `request` |
| Client side | `location.*` (`hash`, `search`, `href`), `document.referrer`, `window.name`, `postMessage` events, `localStorage`/`sessionStorage`, URL router params |
| Other | Queue consumers (SQS, Kafka, BullMQ jobs), GraphQL resolver args, WebSocket messages, `process.env` from untrusted sources, LLM output |

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| SQL injection (CWE-89) | Template literals or concatenation in `db.query`, `pool.query`, `connection.execute`; Sequelize `sequelize.query` with interpolation; TypeORM `query()`, or `createQueryBuilder().where()` with an interpolated string; Knex `knex.raw` with interpolation; Prisma `$queryRawUnsafe` or `$executeRawUnsafe` | Placeholders (`$1`, `?`) with value arrays; query builder bindings (`where("id = :id", { id })`); Prisma `$queryRaw` tagged templates; ORM methods |
| NoSQL injection (CWE-943) | Mongo or Mongoose queries passed `req.body` or `req.query` objects directly (`{ password: { $ne: null } }`); `$where` with input | Cast to the expected primitive type; schema validation (zod, Joi, class-validator); `sanitizeFilter` in Mongoose |
| OS command (CWE-78) | `child_process.exec` and `execSync` with input; `spawn(..., { shell: true })`; template strings passed to a shell | `execFile` or `spawn` with an argument array and no shell; allow-listed arguments |
| Code injection (CWE-94) | `eval`, `new Function(input)`, `setTimeout(string)`, `setInterval(string)`, `vm.runInNewContext` (not a security boundary), dynamic `require(input)` or `import(input)` | Never evaluate input; a JSON parse; fixed module maps |
| Template injection (CWE-1336) | Server-side templates compiled from input (`ejs.render(input)`, `pug.compile(input)`, `Handlebars.compile(input)`); EJS `<%-` with input; Handlebars triple-stash `{{{ }}}` | Fixed templates; escaped output (`<%=`, `{{ }}`) |
| XSS (CWE-79) | React `dangerouslySetInnerHTML`; Vue `v-html`; Angular `bypassSecurityTrustHtml`/`Url`/`ResourceUrl`/`Script`, and `[innerHTML]` with bypassed values; `element.innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`; `href`/`src` from input (`javascript:` URLs); `res.send(html)` built from input | Framework escaping; DOMPurify when markup is required; URL scheme allow-list; Content Security Policy |
| Path traversal (CWE-22) | `fs.readFile`, `createReadStream`, `res.sendFile` with `path.join(base, input)` (`..` survives `join`); `express.static` over sensitive roots; archive extraction without checks | `path.resolve(base, input)` then check it starts with `base + path.sep`; `res.sendFile(name, { root })` with validated names |
| SSRF (CWE-918) | `fetch`, `axios`, `got`, `http.get`, `node-fetch` with a URL from input; Next.js image optimization `remotePatterns` set too broad; webhook and URL-preview features | A host allow-list; resolve and block private and link-local ranges; disable redirects or re-validate |
| Open redirect (CWE-601) | `res.redirect(req.query.next)`; Next.js `redirect(input)` or `NextResponse.redirect(new URL(input))`; `window.location = input` | Relative paths only, with a leading `/` and not `//`; an allow-list |
| Deserialization (CWE-502) | `node-serialize`; `serialize-javascript` output passed to `eval`; `js-yaml` `load` with an unsafe schema in older versions; `v8.deserialize` on untrusted data | `JSON.parse` plus schema validation; `js-yaml` 4.x `load` (safe by default) |
| XXE (CWE-611) | `libxmljs` with `noent: true`; XML parsers on untrusted XML with entity expansion enabled | Keep entity expansion off; prefer JSON |
| LDAP injection (CWE-90) | `ldapjs` filter strings built from input | Escape filter values, or build filters with the library's filter objects |
| Log injection (CWE-117) | Logging raw input with CR/LF in plain-text logs | Structured logging (pino, winston JSON) |
| Crypto misuse (CWE-327, CWE-329, CWE-330, CWE-916) | `crypto.createCipher` (deprecated, no IV); `aes-*-ecb`; a fixed IV with `createCipheriv`; `Math.random()` for tokens or IDs; `md5`/`sha1` for passwords; `rejectUnauthorized: false`; `NODE_TLS_REJECT_UNAUTHORIZED=0` | `createCipheriv('aes-256-gcm', key, randomIV)`; `crypto.randomBytes` or `crypto.randomUUID`; `bcrypt`, `argon2`, or `crypto.scrypt`; default TLS verification |
| ReDoS (CWE-1333) | `new RegExp(input)`; catastrophic patterns (`(a+)+`, `(.*a){n}`) on input; vulnerable validator versions | Avoid user regexes; linear-time patterns; input length limits; the `re2` binding for user patterns |
| File upload (CWE-434) | multer `dest` under a static directory; trusting `originalname` or `mimetype` | Store outside served directories with generated names; content sniffing; `limits` |

## Authentication, authorization, and session

- **Missing route middleware.** Express protects routes only where middleware is attached. Look for routers mounted before `app.use(authenticate)`, and admin routes without a role check.
- **Object-level authorization.** Handlers doing `Model.findById(req.params.id)` without filtering by `req.user.id` or tenant (CWE-639, API1).
- **Next.js server actions are public endpoints.** Every `'use server'` function can be called directly by any client. Each needs its own authentication and authorization check; hiding the button isn't a check.
- **Next.js middleware as the only guard.** Middleware matchers can miss paths. Re-check authorization in route handlers and server components that read data. Also check the Next.js version against known middleware-bypass advisories, such as the `x-middleware-subrequest` header issue (CVE-2025-29927).
- **NestJS guards.** Check `@UseGuards` coverage, or a global guard via `APP_GUARD`, and look for `@Public()`-style decorators that skip it.
- **Mass assignment (CWE-915).** `Object.assign(user, req.body)`, spread (`{...req.body}`) into ORM `create` or `update`, Mongoose `new Model(req.body)`. Use explicit field picking or DTO validation (`class-validator` with `whitelist: true` and `forbidNonWhitelisted`).
- **JWT.** `jsonwebtoken` `verify` without the `algorithms` option, use of `decode` instead of `verify`, hard-coded secrets, no `audience` or `issuer` checks.
- **Sessions and cookies.** `express-session` with a hard-coded `secret`, `cookie.secure: false` in production, missing `httpOnly` and `sameSite`; tokens in `localStorage` (readable by any XSS).
- **CORS.** `cors({ origin: true, credentials: true })` or reflecting `req.headers.origin` with credentials.
- **CSRF.** Cookie-authenticated, state-changing routes without CSRF protection or `SameSite` cookies. `csurf` is deprecated; check what replaced it.

## Language-specific issues

- **Prototype pollution (CWE-1321).** Recursive merge, clone, or set-by-path of user JSON (`lodash.merge`, `_.set`, `defaultsDeep` in vulnerable versions, hand-written deep merges) allowing `__proto__`, `constructor`, or `prototype` keys. Downstream gadgets include template engine options, `child_process` options, and authorization checks reading inherited properties.
- **Type confusion.** `req.query.x` can be a string, an array, or an object (`?x[a]=1`). Comparisons and NoSQL queries break without type checks.
- **SSR injection.** Serializing state into HTML (`window.__INITIAL_STATE__ = ${JSON.stringify(data)}`) without escaping `</script>`.
- **Dependency confusion and install scripts.** Unscoped internal package names that could be claimed on the public registry; `preinstall` and `postinstall` scripts in dependencies.
- **Unhandled promise rejections and error middleware** that leak stack traces, or continue after a failed authorization check.

## Configuration

- `next.config.js` / `next.config.mjs`: `images.remotePatterns` and `domains`, `headers()` for CSP and HSTS, `rewrites` to internal hosts, `experimental.serverActions.allowedOrigins`.
- `.env`, `.env.local`, `.env.production`: secrets committed; `NEXT_PUBLIC_*` variables holding secrets (these ship to the browser).
- Express setup: `helmet()` missing; `app.set('trust proxy', ...)` too broad; error handlers sending `err.stack`; `x-powered-by` enabled.
- `angular.json`, `vite.config.*`, `webpack.config.*`: source maps published in production; dev-server settings in production.

## Dependencies and build

- Read `package.json`, the lockfile (`package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`), `.npmrc` (registries, tokens), and workspace configs.
- **Installs and builds run code.** `npm install`, `npm ci`, `yarn`, and `pnpm install` run lifecycle scripts (`preinstall`, `install`, `postinstall`) from every dependency. `npm run build` runs project code. Ask before running them; `npm ci --ignore-scripts` reduces the risk for an audit-only install. `npm audit` needs a lockfile but no install.
- Check for registry URLs over HTTP, auth tokens committed in `.npmrc`, and git or tarball dependencies from unpinned URLs.

## Quick search patterns

These find candidates only; every hit still goes through `triage.md`.

```
\.query\(\s*`[^`]*\$\{|\.raw\(\s*`[^`]*\$\{|\$queryRawUnsafe|\$executeRawUnsafe
child_process|\bexec(Sync)?\(|shell:\s*true
\beval\(|new Function\(|setTimeout\(\s*['"`]|vm\.run
dangerouslySetInnerHTML|v-html|bypassSecurityTrust|\.innerHTML\s*=|insertAdjacentHTML|document\.write
res\.redirect\(\s*req\.|NextResponse\.redirect\(|window\.location\s*=
res\.sendFile\(|fs\.(readFile|createReadStream)\(.*req\.
createCipher\(|-ecb|Math\.random\(|rejectUnauthorized:\s*false|NODE_TLS_REJECT_UNAUTHORIZED
jwt\.decode\(|\.verify\(
Object\.assign\([^,]+,\s*req\.body|\.\.\.req\.body|__proto__|_\.merge\(|_\.set\(
'use server'|"use server"
new RegExp\(
```
