# Tools

The scanners this skill runs: what each covers, how to invoke it safely, and what it must not be allowed to do. Versions, commands, and statuses were verified against official sources on 2026-10-15. Install commands and integrity checks are in `../README.md`. Run `scripts/check-tools.sh` or `scripts/check-tools.ps1` to see what's installed.

Write every tool's raw output to `.appsec-audit/raw/`, and record the tool's version in the report.

**Two rules for every command:**
- **Exclude the audit directory** from every scan, so a later audit doesn't scan an earlier audit's output: Semgrep/Opengrep `--exclude .appsec-audit`, Trivy `--skip-dirs .appsec-audit`, Checkov `--skip-path .appsec-audit`, Bandit `-x ./.appsec-audit`. For tools without an exclude option, drop results under `.appsec-audit/` during triage.
- **Raw secret-scanner output must not contain secrets** (SKILL.md rule 7). Run Gitleaks with `--redact`. For tools that can't redact (TruffleHog's JSON includes the raw secret), don't save their output to disk: read it from the command's output, keep only the detector, file, line, and commit, and write that redacted summary instead.

## Required by stack

"Core" tools apply to every repository. Install the stack tools for what step 1 detected.

| Stack | SAST | Dependencies | Other |
|---|---|---|---|
| **Core (every repo)** | Opengrep **or** Semgrep CE | OSV-Scanner | Gitleaks (or Betterleaks v1.9.0) for secrets; Syft for an SBOM when needed |
| Java / Kotlin | + SpotBugs with Find Security Bugs (needs compiled classes), PMD | OSV-Scanner (Maven, Gradle lockfiles) | |
| Python | + Bandit (with the `sarif` extra) | + pip-audit | |
| JavaScript / TypeScript, front end | + ESLint with eslint-plugin-security (noisy; triage carefully) | + `npm audit` | |
| C# / .NET | + DevSkim | + `dotnet list package --vulnerable` | |
| Go | + gosec | + govulncheck (reports reachability) | |
| Rust | + Clippy security lints (compiles the crate; needs approval) | + cargo-audit, cargo-deny | cargo-geiger `--forbid-only` for an `unsafe` inventory |
| Terraform | | | Checkov; TFLint with the AWS ruleset (optional) |
| AWS CDK | | | Checkov on `cdk.out` (needs an approved `cdk synth`); recommend cdk-nag to the team |
| Dockerfiles | | Trivy (image or filesystem vulnerabilities) | Hadolint |
| Kubernetes, Helm | | | Checkov, kube-linter |
| CI/CD pipelines | Opengrep or Semgrep rules for GitHub Actions and GitLab CI | | Checkov (`github_actions`, `gitlab_ci` frameworks) |
| Prioritization (every run) | | CISA KEV catalog download, FIRST EPSS API | `scripts/fetch-kev.sh` or `scripts/fetch-kev.ps1` |
| Hooks (guardrails) | | | Node.js 18+ (runs `hooks/guard.js`) |

## Status warnings

Check these before recommending or installing a tool:

- **Trivy supply-chain compromise (GHSA-69fq-xp46-6x23, March 2026).**
  - Malicious artifacts: v0.69.4 (binaries, packages, and images), Docker Hub images 0.69.5 and 0.69.6, and hijacked `trivy-action` and `setup-trivy` tags.
  - Use v0.76.0 or later, verified with cosign (see README). Pin images by digest, and pin GitHub Actions by full commit SHA.
- **Terrascan** has been archived and is unmaintained (November 2025). Don't use it.
- **tfsec** has moved into Trivy (`trivy config`). Don't install it standalone.
- **Horusec** has been abandoned since 2022.
- **Security Code Scan (.NET)** has been stale since 2024.
- **Gitleaks** is feature-complete and receives security patches only. Its maintainer now works on **Betterleaks**. If you use Betterleaks, pin **v1.9.0**: v2 (in release candidates) removes SARIF output and changes the CLI.
- **CodeQL** may not be used on private code without a paid GitHub Code Security license. The free license covers open-source code hosted on GitHub. Use it only when one of those applies.
- **Semgrep rules** from the Semgrep Registry are licensed for internal use only. Don't copy them into reports or ship them. The Semgrep CE engine is LGPL-2.1. Cross-file taint analysis is a paid Semgrep feature.
- **Brakeman** (Ruby) uses a non-OSI license with commercial-use restrictions. Have the user confirm it fits their use.
- **TruffleHog** is AGPL-3.0, and verification sends secrets to their providers. Use `--no-verification` unless the user opts in.
- **KICS** publishes no release binaries. Docker Hub's newest image lags the latest version. Prefer Checkov.
- **OWASP Dependency-Check** requires v12.1.0 or later because of NVD API changes, and an NVD API key in practice. It matches by CPE, so expect more false positives. Its repository moved to `dependency-check/DependencyCheck`.

## Commands

Commands for a local scan, chosen not to execute project code or send code off the machine. Where a command does either, it says so. Get approval before running any of those (SKILL.md rules 3 and 4).

### SAST

| Tool | Command | Notes |
|---|---|---|
| Opengrep | `opengrep scan -f <rules-dir> --sarif-output=.appsec-audit/raw/opengrep.sarif .` | **Has no built-in ruleset.** With no `-f`, it falls back to `auto`, which sends the project URL to the Semgrep Registry. Always pass a local rules directory: a pinned checkout of `opengrep/opengrep-rules` (ask before cloning), or the team's own rules |
| Semgrep CE | `semgrep scan --config p/default --metrics off --sarif-output=.appsec-audit/raw/semgrep.sarif .` | `p/default` downloads rules from the Registry (no code is sent). Never use `--config auto`: it requires metrics and sends the project URL. In diff mode, add `--baseline-commit <sha>` |
| Bandit | `bandit -r . -f sarif -o .appsec-audit/raw/bandit.sarif` | SARIF needs `bandit[sarif]`. Respects `# nosec`; check for a justification |
| gosec | `gosec -fmt sarif -out .appsec-audit/raw/gosec.sarif ./...` | Requires Go 1.25+. Loads packages, which can need module downloads |
| SpotBugs + Find Security Bugs | `spotbugs -textui -pluginList findsecbugs-plugin-1.14.0.jar -sarif=.appsec-audit/raw/spotbugs.sarif <compiled-classes-or-jar>` | Needs compiled bytecode. If none exists, building it runs Maven or Gradle (approval). Otherwise skip, and rely on Opengrep/Semgrep plus AI review for Java |
| PMD | `pmd check -d src -R rulesets/java/quickstart.xml -f sarif -r .appsec-audit/raw/pmd.sarif` | Quality-focused; keep only security-relevant rules in the report |
| ESLint + eslint-plugin-security | `npx eslint -f json -o .appsec-audit/raw/eslint.json .`, using a flat config with `pluginSecurity.configs.recommended` | Needs a local install (`npm i -D`). **Approval** if that means `npm install` in the project. The project says it "finds a lot of false positives" |
| DevSkim | `devskim analyze --source-code . --output-file .appsec-audit/raw/devskim.sarif` | Needs the .NET SDK 10+ as a `dotnet tool` |
| Clippy (Rust) | `cargo clippy --message-format=json -- -W clippy::undocumented_unsafe_blocks -W clippy::unwrap_used -W clippy::expect_used -W clippy::indexing_slicing -W clippy::arithmetic_side_effects` | **Compiles the crate, running `build.rs` and proc macros: approval.** SARIF via the third-party `clippy-sarif` |
| cppcheck (C/C++) | `cppcheck --output-format=sarif --output-file=.appsec-audit/raw/cppcheck.sarif <src>` | Secondary language; generic coverage |
| Flawfinder (C/C++) | `flawfinder --sarif . > .appsec-audit/raw/flawfinder.sarif` | Lexical only; noisy |

### Dependencies (SCA)

| Tool | Command | Notes |
|---|---|---|
| OSV-Scanner v2 | `osv-scanner scan source --format sarif --output-file .appsec-audit/raw/osv.sarif -r .` | Queries the OSV.dev API live (sends package names and versions, not code). Reachability for Go by default. Don't enable `--call-analysis=rust`: it runs `build.rs` |
| npm audit | `npm audit --json --omit=dev > .appsec-audit/raw/npm-audit.json` | Needs a lockfile, but no install. Sends the dependency tree to the registry. JSON only (no SARIF) |
| pip-audit | `pip-audit -r requirements.txt -f json -o .appsec-audit/raw/pip-audit.json` | JSON only (no SARIF). **Auditing a project directory (`pip-audit .`) can build packages and run code.** Prefer a requirements or lock file. The project says: "If you wouldn't `pip install` it, you should not `pip audit` it" |
| govulncheck | `govulncheck -format sarif ./... > .appsec-audit/raw/govulncheck.sarif` | Symbol-level reachability: report "affected" findings as reachable. Exits 0 even when vulnerabilities are found, so read the output |
| cargo-audit | `cargo audit --file <path>/Cargo.lock --json > .appsec-audit/raw/cargo-audit.json` | Run from a directory **outside** the project with `--file`. If there's no `Cargo.lock`, cargo-audit runs `cargo update`, which can execute project code |
| cargo-deny | `cargo deny --format json --manifest-path Cargo.toml check advisories licenses bans sources` | `--format` is a global option and goes before `check`. Uses `cargo metadata`; doesn't compile. Needs a `deny.toml` (`cargo deny init` creates one; ask before adding files) |
| .NET | `dotnet list package --vulnerable --include-transitive --format json` (SDK 9 and earlier); `dotnet package list --vulnerable --format json` (.NET 10) | **Restore runs MSBuild and can execute package build logic: approval.** On .NET 10 the command restores automatically unless `--no-restore` is given |
| Trivy | `trivy fs --scanners vuln --format sarif -o .appsec-audit/raw/trivy-fs.sarif .`; `trivy image --format sarif -o ... <image>` | Use for container images and as a second dependency source |
| Grype | `grype dir:. -o sarif > .appsec-audit/raw/grype.sarif` | Shows EPSS and KEV natively; useful as a cross-check |

### Secrets

| Tool | Command | Notes |
|---|---|---|
| Gitleaks | `gitleaks git . --redact -f sarif -r .appsec-audit/raw/gitleaks-history.sarif` and `gitleaks dir . --redact -f sarif -r .appsec-audit/raw/gitleaks-tree.sarif` | Scan **both** git history and the working tree. Respect `.gitleaksignore` entries only when they're justified |
| Betterleaks v1.9.0 | `betterleaks git . --redact -f sarif -r ...` and `betterleaks dir . --redact -f sarif -r ...` | Validation is off by default; keep it off unless the user opts in. Check `betterleaks --help` for `--redact`; if it's missing, apply the TruffleHog rule above |
| TruffleHog | `trufflehog filesystem . --no-verification --json` and `trufflehog git file://. --no-verification --json` | Always `--no-verification` unless the user opts in. Its output includes the raw secret: don't save it unredacted (see the rule at the top) |
| detect-secrets | `detect-secrets scan > .appsec-audit/raw/detect-secrets.json` | Stale (last release 2024); use only when the team already relies on its baseline |

### IaC and containers

| Tool | Command | Notes |
|---|---|---|
| Checkov (Terraform) | `checkov -d . --framework terraform -o sarif --output-file-path .appsec-audit/raw/` | **The default for Terraform.** Doesn't download modules unless `--download-external-modules true` is given |
| Checkov (CDK) | `checkov -d cdk.out --framework cloudformation -o sarif --output-file-path .appsec-audit/raw/` | Needs `cdk.out` from `cdk synth`, which **runs the CDK app: approval**. Checkov's `cdk` framework needs a Prisma Cloud API key; don't use it. Without synth, review CDK constructs with `iac-aws-cdk.md` |
| Checkov (other) | `--framework kubernetes,helm,dockerfile,github_actions,gitlab_ci,cloudformation` | One run can cover several frameworks |
| Terraform plan (optional) | `terraform init && terraform plan -out tfplan.bin && terraform show -json tfplan.bin > tfplan.json && checkov -f tfplan.json --repo-root-for-plan-enrichment .` | More complete results, but **runs provider binaries, usually needs cloud credentials, and plan files can contain secrets: approval** |
| Trivy config | `trivy config --format sarif -o .appsec-audit/raw/trivy-config.sarif .` | **Downloads remote Terraform modules, and this can't be disabled from the CLI** (the docs warn about request forgery on untrusted configs). Use it for Kubernetes, Dockerfiles, and CloudFormation; for Terraform, only with approval |
| TFLint + AWS ruleset | `tflint --init && tflint --recursive -f sarif` | `--init` downloads plugin binaries (approval). The ruleset's `deep_check` uses AWS credentials: don't enable it |
| Hadolint | `hadolint -f sarif Dockerfile > .appsec-audit/raw/hadolint.sarif` | |
| kube-linter | `kube-linter lint . --format sarif > .appsec-audit/raw/kube-linter.sarif` | |
| cdk-nag | Not run by the skill | v3 registers as a CDK validation plugin in the app's own code (`Validations.of(app).addPlugins(new AwsSolutionsChecks(app))`), so running it means editing the project and synthesizing. Recommend it as a fix, with the packs that fit (AwsSolutions, HIPAA Security, NIST 800-53 rev 5, PCI DSS 3.2.1, Serverless) |

### Licenses

See `licenses.md`. Trivy: `trivy fs --scanners license --format json -o .appsec-audit/raw/trivy-license.json .`; Rust: `cargo deny --format json check licenses`; otherwise read the `licenses` field in the SBOM.

### SBOM

| Tool | Command |
|---|---|
| Syft | `syft dir:. -o cyclonedx-json=.appsec-audit/raw/sbom.cdx.json` |
| cdxgen | `cdxgen -o .appsec-audit/raw/sbom.cdx.json .` (can run package managers; check its flags before using it on untrusted code) |

## Vulnerability data freshness

SKILL.md rule 9 requires current data. Before the dependency scans, refresh each tool's data and record its age:

| Tool | How it gets data | Refresh | Check age |
|---|---|---|---|
| OSV-Scanner | Live OSV.dev API by default | Automatic. Don't use `--offline` unless the user requires it, and then download fresh databases first (`--offline --download-offline-databases`) | Live queries are current by definition; record "live" |
| Trivy | Local DB, auto-updated (skips if downloaded in the last hour) | `trivy image --download-db-only` (also used by `fs`). Never pass `--skip-db-update` | `trivy version --format json` → `VulnerabilityDB.UpdatedAt` |
| Grype | Local DB, auto-updated; by default rejects a DB older than 120 h | `grype db update`. Set `GRYPE_DB_MAX_ALLOWED_BUILT_AGE=24h` to match rule 9 | `grype db status -o json` |
| cargo-audit | Git clone of the RustSec advisory DB | Fetches automatically. Never pass `--no-fetch` or `--stale` | Note the fetch in the output |
| govulncheck | Live `https://vuln.go.dev` | Automatic | Record "live" |
| npm audit, pip-audit | Live registry or OSV queries | Automatic | Record "live" |
| .NET | Advisory data downloaded during restore (GitHub Advisory Database via nuget.org) | Runs with restore | Record the restore time |
| Dependency-Check | Local NVD mirror | Updates on each run with an NVD API key. Don't pass `--noupdate` | Data directory timestamp |

If a refresh fails, record which tool and why. The report then flags dependency results as **not verified against current data**.

## CISA KEV and EPSS

- **KEV: every run.** Run `scripts/fetch-kev.sh` or `scripts/fetch-kev.ps1`. It downloads `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` to `.appsec-audit/data/kev.json` and prints `catalogVersion`, `dateReleased`, and `count`.
  - Item fields: `cveID`, `vendorProject`, `product`, `vulnerabilityName`, `dateAdded`, `shortDescription`, `requiredAction`, `dueDate`, `knownRansomwareCampaignUse` (`Known`/`Unknown`), `notes`, `cwes`, and the newer `forensicTriage`.
  - Match every CVE from every scanner against `cveID`.
  - Schema: `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities_schema.json`.
- **EPSS:** `https://api.first.org/data/v1/epss?cve=CVE-A,CVE-B,...` returns `epss`, `percentile`, and `date` per CVE. Batch the CVE IDs, and record the score date.
