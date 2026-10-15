# Already-installed scanners (optional)

This skill never installs tools (SKILL.md rule 6). The AI review, the OSV.dev and KEV lookups, and `git` cover every category on their own. If step 2 finds security scanners **already installed** on the machine, run the ones that apply, as an extra source of candidates. Their results get the same verification as AI candidates (`triage.md`). Never suggest installing a missing one.

Commands and cautions were verified against official sources on 2026-10-15. Write each tool's output to `.appsec-audit/raw/`, record its version in the coverage section, and run independent ones in parallel.

**Two rules for every command:**
- **Exclude the audit directory**, so an audit doesn't scan an earlier audit's output: Semgrep and Opengrep `--exclude .appsec-audit`, Trivy `--skip-dirs .appsec-audit`, Checkov `--skip-path .appsec-audit`, Bandit `-x ./.appsec-audit`. For tools without an exclude option, drop results under `.appsec-audit/` during triage.
- **Raw secret-scanner output must not contain secrets** (rule 7). Run Gitleaks or Betterleaks with `--redact`. TruffleHog's JSON includes the raw secret, so don't save it; keep only the detector, file, line, and commit.

## Cautions before running an installed tool

- **Trivy v0.69.4, 0.69.5, or 0.69.6:** these builds were malicious (supply-chain compromise GHSA-69fq-xp46-6x23, March 2026). Don't run them. Tell the user to remove that build.
- **Semgrep:** never `--config auto`, which requires metrics and sends the project URL; use `--config p/default --metrics off`. Never `semgrep login` or `semgrep ci`, which use the cloud service.
- **Opengrep:** has no built-in ruleset. Without `-f <local rules>`, it falls back to `auto` and sends the project URL. Run it only if local rules exist on the machine.
- **TruffleHog and Betterleaks:** always disable secret verification (`--no-verification`; Betterleaks validation is off by default). Verification sends secrets to their providers.
- **Snyk:** `snyk code` uploads source code. Don't run it. `snyk test` sends the dependency list, which is fine only if the user is already authenticated and agrees.
- **CodeQL:** its license doesn't allow use on private code without a paid GitHub license. Run it only on open-source code, or if the user confirms they're licensed.
- **Tools that execute project code:** SpotBugs needs compiled classes, Clippy compiles the crate, `pip-audit .` can build packages, `.NET` restore runs MSBuild, `cdk synth` runs the app, and `terraform init` downloads providers. Each needs the user's approval (rule 3); without it, skip the tool.
- **Trivy and Terraform:** `trivy config` downloads remote Terraform modules and can't be stopped from doing so. For Terraform, prefer Checkov, or run Trivy only with approval.
- **Vulnerability databases:** let the tool update its own database as it normally does, and record the database date if the tool shows it. OSV.dev and KEV (`dependencies.md`) remain the source of record for dependency findings.

## Commands

### Code (SAST)

| Tool | Command |
|---|---|
| Semgrep CE | `semgrep scan --config p/default --metrics off --exclude .appsec-audit --sarif-output=.appsec-audit/raw/semgrep.sarif .` |
| Opengrep | `opengrep scan -f <local-rules-dir> --exclude .appsec-audit --sarif-output=.appsec-audit/raw/opengrep.sarif .` |
| Bandit (Python) | `bandit -r . -x ./.appsec-audit -f sarif -o .appsec-audit/raw/bandit.sarif` (SARIF needs the `sarif` extra; otherwise `-f json`) |
| gosec (Go) | `gosec -fmt sarif -out .appsec-audit/raw/gosec.sarif ./...` |
| PMD (Java) | `pmd check -d src -R rulesets/java/quickstart.xml -f sarif -r .appsec-audit/raw/pmd.sarif` (keep only security-relevant rules) |
| DevSkim (.NET and others) | `devskim analyze --source-code . --output-file .appsec-audit/raw/devskim.sarif` |
| cppcheck, Flawfinder (C/C++) | `cppcheck --output-format=sarif --output-file=.appsec-audit/raw/cppcheck.sarif <src>`; `flawfinder --sarif . > .appsec-audit/raw/flawfinder.sarif` |

### Dependencies

These are cross-checks; `deps.js` (OSV.dev, KEV, EPSS) is the source of record.

| Tool | Command |
|---|---|
| OSV-Scanner | `osv-scanner scan source --format sarif --output-file .appsec-audit/raw/osv.sarif -r .` (don't use `--call-analysis=rust`, which runs `build.rs`) |
| Grype | `grype dir:. -o sarif > .appsec-audit/raw/grype.sarif` |
| Trivy | `trivy fs --scanners vuln --skip-dirs .appsec-audit --format sarif -o .appsec-audit/raw/trivy-fs.sarif .` |
| npm | `npm audit --json --omit=dev > .appsec-audit/raw/npm-audit.json` (needs a lockfile; no install) |
| govulncheck (Go) | `govulncheck -format sarif ./... > .appsec-audit/raw/govulncheck.sarif` (reports whether vulnerable code is called) |
| cargo-audit (Rust) | `cargo audit --file <path>/Cargo.lock --json` (run from outside the project) |

### Secrets

| Tool | Command |
|---|---|
| Gitleaks | `gitleaks git . --redact -f sarif -r .appsec-audit/raw/gitleaks-history.sarif` and `gitleaks dir . --redact -f sarif -r .appsec-audit/raw/gitleaks-tree.sarif` |
| Betterleaks (v1) | The same commands with `betterleaks`; check `betterleaks --help` for `--redact` |
| TruffleHog | `trufflehog git file://. --no-verification --json`: read the output, don't save it |

### IaC and containers

| Tool | Command |
|---|---|
| Checkov | `checkov -d . --skip-path .appsec-audit -o sarif --output-file-path .appsec-audit/raw/` (Terraform, CloudFormation, Kubernetes, Helm, Dockerfiles, GitHub Actions, GitLab CI). On Windows, Checkov may be a Python script without an `.exe`: run it with `python -m checkov.main` in its environment |
| Trivy config | `trivy config --skip-dirs .appsec-audit --format sarif -o .appsec-audit/raw/trivy-config.sarif .` (see the Terraform caution) |
| Hadolint | `hadolint -f sarif Dockerfile > .appsec-audit/raw/hadolint.sarif` |
| kube-linter | `kube-linter lint . --format sarif > .appsec-audit/raw/kube-linter.sarif` |
