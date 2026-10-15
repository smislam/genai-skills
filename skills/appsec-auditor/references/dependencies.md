# Dependency audit

Known vulnerabilities in third-party packages come from **live data only** (SKILL.md rule 9). You can't know them from memory. The scripts collect the data deterministically; you judge reachability and decide each item.

1. `inventory.js` parses lockfiles and manifests into `coverage.json` → `packages` (and `unresolved`).
2. `deps.js` queries OSV.dev for every package, downloads the current CISA KEV catalog, scores CVEs with EPSS, and writes `deps.json` with one `dependency` item per package advisory.
3. You decide each item: affected and reachable (`finding`), not affected (`false_positive` with the evidence), or `needs_review`.

Only package names, versions, CVE IDs, and Maven coordinates leave the machine (rule 4).

## What the inventory parses

| Ecosystem | Files | Transitive dependencies |
|---|---|---|
| npm | `package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock` (v1 and Berry), `pnpm-lock.yaml` | Yes |
| PyPI | `poetry.lock`, `uv.lock`, `Pipfile.lock`, `requirements*.txt` (exact `==` pins only) | From lockfiles |
| Maven | `pom.xml`, with parent and imported-BOM versions resolved from Maven Central | **No**: needs a build or a lockfile |
| Gradle | `gradle.lockfile` (preferred), `gradle/libs.versions.toml`, literal declarations in `build.gradle(.kts)` | Only from `gradle.lockfile` |
| Go | `go.mod` (including `// indirect`) | Yes, as listed in `go.mod` |
| crates.io | `Cargo.lock` | Yes |
| NuGet | `packages.lock.json`, `*.csproj` `PackageReference`, `Directory.Packages.props` | From `packages.lock.json` |
| RubyGems | `Gemfile.lock` | Yes |
| Packagist | `composer.lock` | Yes |

Whatever can't be resolved goes to `coverage.json` → `unresolved`, with the reason. Report it in the coverage section as **not checked**. Common reasons:
- version ranges without a lockfile;
- versions managed by the Spring Boot Gradle plugin;
- MSBuild property versions;
- Maven and Gradle transitive dependencies.

For Maven and Gradle transitive dependencies, offer one of these:
- **With the user's approval** (rule 3: these run build plugins), `mvn dependency:tree` or `gradle dependencies` lists them. You can then check the extra packages with the manual OSV procedure below.
- **Otherwise,** recommend the team commit a lockfile (`gradle dependencies --write-locks`) or produce an SBOM in CI, so the next audit covers them deterministically.

## Proxies and firewalls

All the scripts' network calls go through `curl`, which ships with macOS, Linux, Git Bash, and Windows 10+. Run `node ${CLAUDE_SKILL_DIR}/scripts/net-check.js` to test the endpoints. It names the problem when one fails. Then tell the user the matching setting. These are environment variables, so they must be set in the environment Claude Code runs in (then restart the session), or in Claude Code's `env` settings.

| Problem `net-check` reports | Setting |
|---|---|
| `connect` / `timeout` / `dns`: a proxy is required | `HTTPS_PROXY=http://proxy.corp.example:8080` (curl honors it, and `NO_PROXY` for exceptions). Or `APPSEC_PROXY` to set it for this skill only |
| `proxy-auth` (HTTP 407): the proxy requires authentication | **Windows integrated authentication** (most corporate proxies): `APPSEC_PROXY_AUTH=negotiate`, or `ntlm`, which uses the logged-in user's credentials with no password stored. **Basic:** `APPSEC_PROXY_AUTH=basic`, with `user:password@` in the proxy URL; credentials are never printed |
| `tls`: certificate not trusted (corporate TLS inspection) | Windows uses the system certificate store, so this usually works there. Elsewhere: `APPSEC_CA_BUNDLE=/path/to/corporate-root-ca.pem` |
| `revocation` (Windows): revocation check failed through the proxy | `APPSEC_SSL_REVOKE_BEST_EFFORT=1` |
| `blocked` (HTTP 403), or no internet access at all | Point the skill at internal mirrors: `APPSEC_OSV_URL` (an OSV-compatible API), `APPSEC_KEV_URL` (a copy of the KEV JSON feed), `APPSEC_EPSS_URL`, and `APPSEC_MAVEN_URL` (an Artifactory, Nexus, or other Maven Central mirror) |
| `not-json` | The proxy returned a login or block page instead of the API response. Ask for `api.osv.dev`, `www.cisa.gov`, and `api.first.org` to be allowed, or use mirrors |

If a setting can't be fixed now, continue. `deps.json` records the failure, and the report must say dependency results are **not checked** (the gate enforces it).

## Deciding dependency items

Each `dependency` item in `deps.json` carries: package, version, file, direct or transitive, the advisory ID, its CVEs, severity, fixed versions, KEV status (`null` = not listed, `"unknown"` = KEV couldn't be fetched), and EPSS.

**Reachability, with evidence:**
1. Read the advisory's details for the vulnerable component: a class, function, module, configuration option, or feature (for example "JNDI lookup in message patterns", "`yaml.load` without a `SafeLoader`").
2. Search the code for uses of that component, and trace whether attacker-influenced input reaches it.
3. Decide:
   - **Reachable or plausibly reachable** → `finding`, at the severity `triage.md` gives.
   - **Library used, but not the vulnerable part** (the vulnerable feature, option, or configuration isn't used) → still `finding`, with severity **lowered one level**, saying exactly what isn't used. An upgrade is still the fix.
   - **Vulnerable component absent** (never imported, called, loaded, or configured anywhere) → `false_positive`, with what you searched for (for example: "no `JndiLookup` or `${jndi:` usage; log4j used only via SLF4J with a static pattern in `log4j2.xml`"). For a KEV-listed advisory, only with strong evidence.
   - **Can't tell** → `needs_review`.

**Ranking:** `triage.md`, "Dependency findings": KEV first, then reachability, EPSS, and CVSS. One upgrade usually fixes several advisories, so report the **minimum version that fixes all of them** (from the `fixed` lists), and use `remediation.md` for the upgrade path.

## Manual procedure (non-deterministic mode, without Node.js)

1. Build the package list from the lockfiles by reading them.
2. `POST {APPSEC_OSV_URL or https://api.osv.dev/v1}/querybatch` with `{"queries": [{"package": {"ecosystem": "...", "name": "..."}, "version": "..."}]}` (up to 1000 per request), then `GET .../vulns/<id>` for each distinct ID.
3. Download the KEV JSON feed, and look up EPSS at `https://api.first.org/data/v1/epss?cve=CVE-A,CVE-B` (about 50 per request).

Use `curl` with the same proxy settings: `--proxy`, `--proxy-negotiate -U :`, `--cacert`. The report must be labeled non-deterministic.
