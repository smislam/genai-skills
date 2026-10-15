# C# and .NET: security review guide

Covers ASP.NET Core (MVC, Razor Pages, minimal APIs, Blazor Server), Entity Framework Core and ADO.NET, and background workers. Legacy ASP.NET (System.Web) issues are noted where they still appear. Tool commands are in `tools.md`; triage rules in `triage.md`.

## Sources

| Entry point | Concrete APIs and attributes |
|---|---|
| MVC and API controllers | Action parameters bound with `[FromQuery]`, `[FromRoute]`, `[FromBody]`, `[FromForm]`, `[FromHeader]`; complex model binding; `IFormFile` |
| Minimal APIs | Lambda parameters in `app.MapGet/MapPost/...`, `[AsParameters]`, `HttpContext.Request` |
| Raw request | `HttpContext.Request.Query`, `Form`, `Headers`, `Cookies`, `Body`, `Path`, `RouteValues` |
| Razor Pages | `[BindProperty]` properties, handler method parameters |
| Blazor | Component parameters from the query string (`[SupplyParameterFromQuery]`), JS interop callbacks |
| Messaging and jobs | Azure Service Bus, RabbitMQ, Kafka, and SQS handler payloads; Hangfire job arguments |
| Other | SignalR hub method arguments, gRPC request messages, configuration from environment variables, files from shared storage |

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| SQL injection (CWE-89) | `SqlCommand` with concatenated `CommandText`; `FromSqlRaw` or `ExecuteSqlRaw` with string concatenation or `string.Format`; Dapper `Query` with concatenated SQL; dynamic `OrderBy` strings from input (System.Linq.Dynamic.Core) | `SqlParameter`; `FromSql` or `FromSqlInterpolated` (they parameterize interpolated values); Dapper parameters (`new { id }`); LINQ; an allow-list for sort fields |
| NoSQL injection (CWE-943) | MongoDB `BsonDocument.Parse(input)` or JSON filter strings from input | `Builders<T>.Filter.Eq(...)` |
| OS command (CWE-78) | `Process.Start(input)`; `ProcessStartInfo` with `FileName = "cmd.exe"` or `"/bin/sh"` and arguments built from input | A fixed `FileName`, `ArgumentList` (not `Arguments`), `UseShellExecute = false`, allow-listed values |
| Code and template injection (CWE-94, CWE-1336) | Roslyn `CSharpScript.EvaluateAsync(input)`; compiling Razor templates from user content (RazorEngine, RazorLight); `DataTable.Compute(input)` | Never compile or evaluate input; a sandboxed template language with fixed templates |
| XSS (CWE-79) | `@Html.Raw(input)`; `new HtmlString(input)`; `MarkupString` in Blazor; returning `Content(html, "text/html")` built from input; `innerHTML` via JS interop | Razor's default `@` encoding; `HtmlEncoder.Default.Encode`; an HTML sanitizer (for example HtmlSanitizer) when markup is required |
| Path traversal (CWE-22) | `Path.Combine(root, input)` (an absolute `input` replaces `root`); `File.ReadAllBytes(input)`; `PhysicalFile(input)`; `IFormFile.FileName` used as a path; `ZipArchive` extraction without checks | `Path.GetFullPath(Path.Combine(root, name))` then check it starts with the full root path; `Path.GetFileName` plus generated names |
| SSRF (CWE-918) | `HttpClient.GetAsync(input)`; `WebRequest.Create(input)`; webhook or image fetchers | An allow-list of hosts; block private and link-local ranges after DNS resolution; `SocketsHttpHandler.ConnectCallback` for enforcement |
| Open redirect (CWE-601) | `Redirect(returnUrl)`; `Response.Redirect(input)` | `LocalRedirect(returnUrl)` or `Url.IsLocalUrl(returnUrl)` |
| Deserialization (CWE-502) | `BinaryFormatter` (obsolete; removed from .NET 9's default runtime); `NetDataContractSerializer`; `SoapFormatter`; `LosFormatter`; `ObjectStateFormatter`; Json.NET with `TypeNameHandling` other than `None`; `JavaScriptSerializer` with a type resolver; `XmlSerializer` with a type from input; `DataSet`/`DataTable` from untrusted XML | `System.Text.Json` to explicit DTOs; Json.NET with `TypeNameHandling.None`, or a strict `SerializationBinder` |
| XXE (CWE-611) | `XmlDocument` with `XmlResolver` set to a non-null resolver (default in old .NET Framework); `XmlReaderSettings` with `DtdProcessing.Parse` and a resolver | Modern .NET defaults are safe; check explicit overrides. `DtdProcessing.Prohibit`, `XmlResolver = null` |
| LDAP and XPath injection (CWE-90, CWE-643) | `DirectorySearcher.Filter` built from input; `XPathNavigator.Select("..." + input)` | Escape LDAP filter characters; parameterize XPath with a custom `XsltContext` (implementing `IXsltContextVariable`) set through `XPathExpression.SetContext`, or validate strictly |
| Log injection (CWE-117) | String-concatenated log messages with raw input | Message templates (`_logger.LogInformation("User {User}", name)`); strip CR/LF |
| Crypto misuse (CWE-327, CWE-329, CWE-330, CWE-916) | `DES`, `TripleDES`, `RC2`, `MD5`, `SHA1` for security; `CipherMode.ECB`; a static IV; `System.Random` for tokens; `Rfc2898DeriveBytes` with low iteration counts or SHA-1; `ServerCertificateCustomValidationCallback` returning true | `AesGcm` with a unique nonce; `RandomNumberGenerator`; ASP.NET Core Identity `PasswordHasher<T>` or `Rfc2898DeriveBytes.Pbkdf2` with SHA-256 and high iterations; default certificate validation |
| ReDoS (CWE-1333) | `new Regex(userPattern)`; vulnerable patterns on input without a timeout | `RegexOptions.NonBacktracking` (.NET 7+); a `matchTimeout`; don't accept user patterns |
| File upload (CWE-434) | Saving `IFormFile` under `wwwroot` with its original name; trusting `ContentType` | Store outside `wwwroot` with generated names; validate signatures; enforce `[RequestSizeLimit]` and `FormOptions` limits |

## Authentication, authorization, and session

- **`[AllowAnonymous]` overrides `[Authorize]`.** On an action, it defeats a controller-level or global policy. Search for it on sensitive actions.
- **No fallback policy.** Without `options.FallbackPolicy` (or a global `AuthorizeFilter`), any endpoint missing `[Authorize]` is public. In minimal APIs, check every `Map*` call for `.RequireAuthorization()`, or a group with it.
- **Middleware order.** `UseAuthentication()` and `UseAuthorization()` must come after `UseRouting()` and before the endpoints. A wrong order silently skips checks.
- **Object-level authorization.** `_db.Orders.FindAsync(id)` with a route ID and no ownership or tenant filter (CWE-639). Look for `IAuthorizationService.AuthorizeAsync(User, resource, policy)` or global query filters.
- **Over-posting (CWE-915).** Binding EF entities directly in actions or `[BindProperty]` exposes properties like `IsAdmin` and `TenantId`. Use view models or DTOs; `[Bind("...")]` is the legacy mitigation.
- **Antiforgery.** Razor Pages validate form posts by default. MVC controllers don't: check for `[ValidateAntiForgeryToken]` or `[AutoValidateAntiforgeryToken]` on controllers, or a global `AutoValidateAntiforgeryTokenAttribute` filter. Check `[IgnoreAntiforgeryToken]` and cookie-authenticated APIs that accept form posts. For minimal APIs with forms, check `.DisableAntiforgery()`.
- **CORS.** `AllowAnyOrigin()` cannot be combined with `AllowCredentials()`. `SetIsOriginAllowed(_ => true)` with `AllowCredentials()` can, and is dangerous.
- **JWT bearer.** `TokenValidationParameters` with `ValidateIssuer`, `ValidateAudience`, `ValidateLifetime`, or `ValidateIssuerSigningKey` set to false; `RequireHttpsMetadata = false` in production; symmetric keys hard-coded in `appsettings.json`.
- **Cookies.** `CookieAuthenticationOptions`: `Cookie.SecurePolicy = Always`, `HttpOnly`, `SameSite`; sliding expiration; a reasonable `ExpireTimeSpan`.

## Language-specific issues

- **Insecure deserializers.** `BinaryFormatter` and its relatives, plus Json.NET `TypeNameHandling.All`/`Auto`, are classic RCE paths. Flag any use on data that crosses a trust boundary, including cache, queue, and session data.
- **Legacy ASP.NET ViewState and machineKey.** A `machineKey` in `web.config` committed to the repo, or `enableViewStateMac="false"`, enables ViewState deserialization RCE.
- **Data Protection keys.** ASP.NET Core Data Protection keys stored in a world-readable location or committed to the repo allow forged cookies and antiforgery tokens.
- **Reflection from input.** `Type.GetType(input)`, `Activator.CreateInstance` with names from requests.
- **Unhandled exceptions failing open** in custom middleware or authorization handlers (OWASP A10:2025). Check that catch blocks don't call `context.Succeed` or continue the pipeline.

## Configuration

- `appsettings.json` and `appsettings.{Environment}.json`:
  - Connection strings and secrets (they belong in user-secrets, Key Vault, or Secrets Manager)
  - `DetailedErrors`
  - Logging levels that log request bodies
- `Program.cs` / `Startup.cs`:
  - `UseDeveloperExceptionPage()` outside Development
  - `UseHsts()` and `UseHttpsRedirection()`
  - Swagger UI exposed in production
  - Health checks that reveal details
- `launchSettings.json` and `web.config`: `customErrors mode="Off"`, `debug="true"` in compilation, `machineKey`, `httpCookies`.

## Dependencies and build

- Read `*.csproj`, `Directory.Packages.props`, `Directory.Build.props`, `packages.lock.json`, `nuget.config` (package sources, and whether a public feed can override private package names), and `global.json`.
- **Builds run project code.** `dotnet build` and `dotnet restore` can execute MSBuild targets and source generators from packages, and `dotnet restore` reaches out to configured feeds. Ask before running them. NuGet audit warnings appear during restore.
- Check for package sources over HTTP, and for packages pinned below the versions in their advisories.
