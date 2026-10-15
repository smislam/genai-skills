# appsec-auditor

An Agent Skill for Claude Code that audits application code for security vulnerabilities the way an AppSec engineer would. It runs free local scanners (SAST, dependencies, secrets, IaC and containers), verifies every result against the code, reviews what scanners miss (authorization, business logic, crypto, CI/CD, LLM and agent code), and analyzes how findings chain into real exploits. Findings map to CWE, OWASP Top 10 (2025), CWE Top 25 (2025), and ASVS 5.0. Dependencies are ranked against the live CISA KEV catalog, reachability, EPSS, and CVSS. It also flags dependency license risk and performance problems, in separate report sections. Output is a Markdown report, a SARIF 2.1.0 file, optional GitLab security reports, and proposed fixes as diffs.

This README is for people setting the skill up. The agent's instructions are in `SKILL.md` and `references/`.

> **The skill is only as thorough as the tools installed.** Before every audit it checks which scanners are present and uses every installed tool that fits your stack. For each missing tool it asks you to choose:
> - **I'll install it myself.** It shows the pinned command below and waits.
> - **Install it for me.** It installs the pinned version and verifies it, after your approval.
> - **Skip it.** AI review covers that category instead.
>
> Declining, not answering, or a failed install all count as "skip". The audit never stops for a missing tool, and the report says where coverage is reduced. For the best results, install at least the **core** tools plus the ones for your stacks.

## Contents

- [Install the skill](#install-the-skill)
- [Dependencies](#dependencies)
  - [Required for every audit](#required-for-every-audit)
  - [Core scanners](#core-scanners)
  - [Stack-specific scanners](#stack-specific-scanners)
  - [Install commands](#install-commands)
  - [Verify what you downloaded](#verify-what-you-downloaded)
- [Check your setup](#check-your-setup)
- [Guardrail hooks](#guardrail-hooks)
- [Network access and data sent](#network-access-and-data-sent)
- [Output](#output)
- [Validate the skill](#validate-the-skill)
- [Limitations](#limitations)

## Install the skill

Copy the whole folder, not just `SKILL.md`. The hooks, scripts, and references are part of the skill.

```bash
# For you, in every project
cp -r skills/appsec-auditor ~/.claude/skills/

# Or for one repository (commit it to share with your team)
mkdir -p .claude/skills && cp -r /path/to/genai-skills/skills/appsec-auditor .claude/skills/
```

On Windows PowerShell:

```powershell
Copy-Item -Recurse skills\appsec-auditor "$HOME\.claude\skills\"
```

The folder contains `.claude-plugin/plugin.json`, so Claude Code loads it both as the skill `/appsec-auditor` and as the plugin `appsec-auditor@skills-dir`, which carries the guardrail hooks. Run `/reload-plugins`, or start a new session, to load it. A copy under a project's `.claude/skills/` loads only after you accept the workspace trust dialog for that folder, and only when the session starts at the repository root.

## Dependencies

Versions below were the latest stable releases, verified on **2026-10-15**. Pin to these, or to a newer release that you verify the same way. Each tool's license is listed so you can check it against your organization's policy.

### Required for every audit

| Dependency | Why | Version | License |
|---|---|---|---|
| **Claude Code** | Runs the skill, and loads its folder as a plugin for the hooks | Current release | — |
| **Node.js** | Runs the guardrail hook (`hooks/guard.js`) and parses the KEV catalog | 18 or later | MIT |
| **git** | Secret scanning of history; diff-mode audits | Any current | GPL-2.0 |
| **curl** (macOS, Linux, Git Bash) or **PowerShell** (Windows) | Downloads the CISA KEV catalog on every run | Any current | — |
| **Network access** to `www.cisa.gov`, `api.first.org`, and `api.osv.dev` | Current KEV, EPSS, and vulnerability data. Without it, dependency results are flagged as unverified | — | — |

### Core scanners

Install these for every repository.

| Category | Tool | Version | License | Notes |
|---|---|---|---|---|
| SAST (multi-language) | **Opengrep** | v1.31.0 | LGPL-2.1 | Open fork of Semgrep with cross-function taint. Has no built-in rules: clone `opengrep/opengrep-rules` at a pinned commit, or use your own rules |
| | *or* **Semgrep CE** | 1.181.0 | LGPL-2.1 engine; Registry rules are internal-use only | Run with `--config p/default --metrics off`. Windows support is beta |
| Dependencies | **OSV-Scanner** | v2.7.0 | Apache-2.0 | Queries OSV.dev live |
| Secrets | **Gitleaks** | v8.30.1 | MIT | Security patches only from now on |
| | *or* **Betterleaks** | v1.9.0 | MIT | Gitleaks' successor. Stay on v1.x: v2 drops SARIF output |
| Download verification | **cosign** | Current | Apache-2.0 | Verifies signatures of Opengrep, Trivy, Grype, Syft, and TruffleHog |

### Stack-specific scanners

| Stack | Tool | Version | License | Notes |
|---|---|---|---|---|
| Python | Bandit (with `sarif` extra) | 1.9.4 | Apache-2.0 | Needs Python 3.10+ |
| | pip-audit | 2.10.1 | Apache-2.0 | |
| Java / Kotlin | SpotBugs | 4.10.5 | LGPL-2.1 | Needs compiled classes and Java |
| | Find Security Bugs plugin | 1.14.0 | LGPL-3.0 | `findsecbugs-plugin-1.14.0.jar` from Maven Central |
| | PMD | 7.28.0 | BSD-style | Needs Java 8+ |
| JavaScript / TypeScript | ESLint | 10.12.0 | MIT | Node ^20.19, ^22.13, or >=24 |
| | eslint-plugin-security | 4.2.0 | Apache-2.0 | Noisy; the skill triages its output |
| | npm (for `npm audit`) | Bundled with Node | Artistic-2.0 | Needs a lockfile |
| C# / .NET | DevSkim | 1.0.100 | MIT | .NET SDK 10+; installed as a `dotnet tool` |
| | .NET SDK | 9 or 10 | MIT | For `dotnet list package --vulnerable` |
| Go | gosec | v2.29.0 | Apache-2.0 | Needs Go 1.25+ |
| | govulncheck | v1.9.0 | BSD-3-Clause | Reports whether vulnerable code is actually called |
| Rust | cargo-audit | 0.22.2 | Apache-2.0 OR MIT | Rust 1.88+ |
| | cargo-deny | 0.20.2 | MIT OR Apache-2.0 | |
| | Clippy | Ships with rustup | MIT OR Apache-2.0 | Compiles the crate, so the skill asks first |
| Terraform | Checkov | 3.3.29 | Apache-2.0 | Default for Terraform; also covers Kubernetes, Helm, Dockerfiles, CloudFormation, and CI pipelines |
| | TFLint + AWS ruleset (optional) | v0.64.0 / v0.49.0 | MPL-2.0; release binaries also BUSL-1.1 | `--init` downloads plugins |
| AWS CDK | Checkov (on `cdk.out`) | 3.3.29 | Apache-2.0 | Needs an approved `cdk synth`. The skill recommends **cdk-nag 3.0.2** (Apache-2.0) for the team to add to the app; it doesn't run it |
| Containers | Trivy | **v0.76.0 or later** | Apache-2.0 | See the security warning below |
| | Hadolint | v2.15.1 | GPL-3.0 | Dockerfiles |
| Kubernetes | kube-linter | v0.8.3 | Apache-2.0 | |
| SBOM | Syft | v1.54.1 | Apache-2.0 | |
| Cross-check (optional) | Grype | v0.120.1 | Apache-2.0 | Shows EPSS and KEV natively |
| Secrets (optional) | TruffleHog | v3.99.2 | **AGPL-3.0** | The skill always runs it with `--no-verification` unless you opt in |
| C / C++ (generic coverage) | cppcheck | 2.22.0 | GPL-3.0-or-later | |
| | Flawfinder | 2.0.20 | GPL-2.0+ | |

> **Trivy security warning.** Trivy's release pipeline was compromised in March 2026 (advisory GHSA-69fq-xp46-6x23). The malicious artifacts were v0.69.4 (binaries, packages, and images), Docker Hub images 0.69.5 and 0.69.6, and hijacked `trivy-action` and `setup-trivy` tags. Install v0.76.0 or later, verify it with cosign (below), reference container images by digest, and pin GitHub Actions to a full commit SHA.

**Don't install these:** Terrascan (archived), standalone tfsec (now part of Trivy), Horusec (abandoned), and Security Code Scan for .NET (stale). CodeQL can't be used on private code without a paid GitHub Code Security license.

### Install commands

Pin a version in every method below. Homebrew can't install an exact older version (`brew pin` only stops upgrades), and some formulas lag behind releases. When you need an exact version, use pipx, npm, `go install`, `cargo install`, or a verified release binary.

**Python tools** (all platforms; use [pipx](https://pipx.pypa.io/) or `uv tool`):

```bash
pipx install semgrep==1.181.0
pipx install "bandit[sarif]==1.9.4"
pipx install pip-audit==2.10.1
pipx install checkov==3.3.29
pipx install flawfinder==2.0.20
```

On Windows, set `PYTHONUTF8=1` before running Semgrep.

**Go tools** (all platforms; needs Go):

```bash
go install github.com/google/osv-scanner/v2/cmd/osv-scanner@v2.7.0   # needs Go 1.26.2+
go install github.com/securego/gosec/v2/cmd/gosec@v2.29.0            # needs Go 1.25+
go install golang.org/x/vuln/cmd/govulncheck@v1.9.0
go install github.com/zricethezav/gitleaks/v8@v8.30.1
go install github.com/terraform-linters/tflint@v0.64.0
go install golang.stackrox.io/kube-linter/cmd/kube-linter@v0.8.3
```

`go install` verifies modules against the Go checksum database automatically.

**Rust tools:**

```bash
cargo install --locked cargo-audit@0.22.2
cargo install --locked cargo-deny@0.20.2
```

**Node tools** (install into the project being audited, as dev dependencies; the skill asks first, because installing runs package scripts):

```bash
npm i -D --save-exact eslint@10.12.0 eslint-plugin-security@4.2.0
npm audit signatures   # checks registry signatures and provenance
```

**.NET tools:**

```bash
dotnet tool install --global Microsoft.CST.DevSkim.CLI --version 1.0.100
```

**Opengrep.** Download the installer, read it, then run it with signature verification:

```bash
curl -fsSLo opengrep-install.sh https://raw.githubusercontent.com/opengrep/opengrep/main/install.sh
less opengrep-install.sh
bash opengrep-install.sh -v v1.31.0 --verify-signatures
```

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/opengrep/opengrep/main/install.ps1 -OutFile opengrep-install.ps1
Get-Content opengrep-install.ps1    # read it first
.\opengrep-install.ps1 -Version v1.31.0
```

On Windows, keep `opengrep.exe` in the same folder as its DLLs. Then fetch rules at a pinned commit, for example `git clone https://github.com/opengrep/opengrep-rules && git -C opengrep-rules checkout <commit>`.

**Trivy, Grype, Syft, TruffleHog, Hadolint, and other release binaries.** Prefer downloading the release archive and verifying it (next section) over install scripts. Where you use the vendors' install scripts, download and read them first; never pipe them straight into a shell:

```bash
curl -fsSLo grype-install.sh https://get.anchore.io/grype
less grype-install.sh
sh grype-install.sh -b /usr/local/bin -v v0.120.1     # -v makes the script verify with cosign
```

**Windows package managers** (when you don't need an exact older version):

| Tool | winget | Scoop |
|---|---|---|
| Trivy | Find the ID with `winget search trivy`, then `winget install -e --id <id> --version 0.76.0` | `scoop install trivy` |
| OSV-Scanner | `winget install -e --id Google.OSVScanner` (lags: 2.6.0) | `scoop install osv-scanner` |
| Grype | `winget install -e --id Anchore.Grype` | `scoop install grype` |
| Syft | `winget install -e --id Anchore.syft` | `scoop install syft` |
| Gitleaks | `winget install -e --id Gitleaks.Gitleaks` | `scoop install gitleaks` |
| Betterleaks | `winget install -e --id Betterleaks.Betterleaks` | — |
| TFLint | `winget install -e --id TerraformLinters.tflint` | `scoop install tflint` |
| Hadolint | — | `scoop install hadolint` |
| cppcheck | `winget install -e --id Cppcheck.Cppcheck` | `scoop install cppcheck` |

Check a winget package ID with `winget show <id>` before installing.

**macOS and Linux with Homebrew** (latest version only):

```bash
brew install osv-scanner trivy grype syft gitleaks hadolint kube-linter cppcheck
```

For Betterleaks, install v1 explicitly (`brew install --cask betterleaks/tap/betterleaks@1`), because the default formula may track v2, which drops SARIF.

`brew install trivy` builds from source and wasn't affected by the March 2026 compromise.

**Not natively packaged:** KICS has no release binaries (build from source or use Docker). Prefer Checkov.

### Verify what you downloaded

These commands come from each project's documentation. Replace `<v>` with the version you installed.

**Trivy** (cosign 3+; with cosign 2.4+ add `--new-bundle-format`):

```bash
cosign verify-blob trivy_0.76.0_Linux-64bit.tar.gz \
  --bundle trivy_0.76.0_Linux-64bit.tar.gz.sigstore.json \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity 'https://github.com/aquasecurity/trivy/.github/workflows/reusable-release.yaml@refs/tags/v0.76.0'
```

Trivy container images:

```bash
cosign verify aquasec/trivy:0.76.0 \
  --certificate-identity-regexp 'https://github\.com/aquasecurity/trivy/\.github/workflows/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

**Grype and Syft** (cosign 2.5+; `<tool>` is `grype` or `syft`):

```bash
cosign verify-blob checksums.txt --bundle checksums.txt.sigstore.json \
  --certificate-identity-regexp 'https://github\.com/anchore/<tool>/\.github/workflows/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum --ignore-missing -c checksums.txt
```

**TruffleHog:**

```bash
cosign verify-blob trufflehog_<v>_checksums.txt \
  --certificate trufflehog_<v>_checksums.txt.pem --signature trufflehog_<v>_checksums.txt.sig \
  --certificate-identity-regexp 'https://github\.com/trufflesecurity/trufflehog/\.github/workflows/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum --ignore-missing -c trufflehog_<v>_checksums.txt
```

**Opengrep:** the installer's `--verify-signatures` runs the following check itself:

```bash
cosign verify-blob --cert opengrep.cert --signature opengrep.sig \
  --certificate-identity-regexp "https://github.com/opengrep/opengrep.+" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" opengrep
```

**OSV-Scanner** (SLSA provenance, with [slsa-verifier](https://github.com/slsa-framework/slsa-verifier)):

```bash
slsa-verifier verify-artifact ./osv-scanner_linux_amd64 \
  --provenance-path multiple.intoto.jsonl \
  --source-uri github.com/google/osv-scanner --source-tag v2.7.0
```

**TFLint:**

```bash
gh attestation verify checksums.txt -R terraform-linters/tflint
sha256sum --ignore-missing -c checksums.txt
```

**Gitleaks, Hadolint, cargo-deny:** checksums only. Run `sha256sum -c` against the release's checksum file. On Windows, use `Get-FileHash <file> -Algorithm SHA256` and compare by eye.

**PyPI and npm packages:** PyPI shows publish attestations on each release page (Semgrep, Bandit, pip-audit, Checkov, and cdk-nag have them). Run `npm audit signatures` after an npm install.

**Not documented by the project:** a signature-verification command for gosec, Betterleaks, and kube-linter binaries, a GPG key for PMD, and any signatures for cppcheck, Flawfinder, and detect-secrets. Download these from the official release page only, and check checksums where they're published.

## Check your setup

```bash
bash ~/.claude/skills/appsec-auditor/scripts/check-tools.sh            # everything
bash ~/.claude/skills/appsec-auditor/scripts/check-tools.sh --missing  # only what's missing
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\skills\appsec-auditor\scripts\check-tools.ps1" -Missing
```

Test the KEV download (it prints the catalog version and checks a known-exploited CVE):

```bash
bash ~/.claude/skills/appsec-auditor/scripts/fetch-kev.sh /tmp/kev CVE-2021-44228
```

## Guardrail hooks

The skill ships a `PreToolUse` hook (`hooks/guard.js`, registered in `hooks/hooks.json`) that enforces its safety rules mechanically. The skill instructions alone don't.

- **It is inert unless an audit is running.** The skill creates `.appsec-audit/.active` in the project when an audit starts and removes it when the audit is done. Without that file, the hook exits immediately and changes nothing.
- **During an audit:**
  - It asks you before any command that executes code from the repository, such as package installs, builds, tests, `cdk synth`, or `terraform init`.
  - It asks before anything that sends secrets or code off the machine.
  - It asks before edits outside `.appsec-audit/`.
  - It asks before running scripts by path (`bash x.sh`, `node x.js`, `./run`), except the skill's own, and before `git push`.
  - It blocks piping downloaded scripts into a shell, writing unredacted secrets into the report, and reporting findings to anyone outside the machine (issues, pull requests, advisories, comments, email).
- **It covers both shells.** It works with the Bash and PowerShell tools and handles Windows paths.
- **It needs Node.js.** If Node.js is missing, the hook can't start. Claude Code shows a hook error and lets the action through, and the skill tells you the guardrails are off.
- **If an audit was interrupted**, the marker may be left behind. The hook ignores markers older than 24 hours; delete `.appsec-audit/.active` to stop it sooner.
- **To turn the hooks off entirely:** `claude plugin disable appsec-auditor@skills-dir`.

## Network access and data sent

| Destination | What is sent | When |
|---|---|---|
| `www.cisa.gov` | Nothing (a download of the KEV catalog) | Every run |
| `api.first.org` (EPSS) | CVE IDs | Every run with dependency findings |
| `api.osv.dev`, npm registry, PyPI, `vuln.go.dev`, NuGet, RustSec (git) | Package names and versions | Dependency scans |
| Scanner database mirrors (Trivy, Grype) | Nothing (downloads) | When those tools run |
| Semgrep Registry | A rules download for `p/default` (no code); metrics turned off | Only if you use Semgrep CE |
| Secret providers (TruffleHog or Betterleaks verification) | **Secrets** | **Only if you opt in** |
| Cloud scanners (Snyk Code, Semgrep login) | **Source code** | **Only if you opt in** |

No source code leaves the machine unless you opt in.

## Output

Each audit writes to `.appsec-audit/` at the repository root:
- `report.md`: the human-readable report.
- `results.sarif`: SARIF 2.1.0, which GitHub code scanning and SARIF-aware IDEs can ingest.
- `raw/`: each tool's own output.
- `data/kev.json`: the KEV catalog used.
- `gitlab/`: GitLab security reports (`gl-sast-report.json`, `gl-secret-detection-report.json`, `gl-dependency-scanning-report.json`) when you ask for GitLab output. Publish them from a CI job as `artifacts: reports:`; the skill shows you the job snippet.

**Add `.appsec-audit/` to `.gitignore`.** The report describes exploitable weaknesses. The skill offers to add it.

## Validate the skill

Before relying on the skill, measure it. Run it against intentionally vulnerable practice applications, where the vulnerabilities are known in advance, and compare what it found with what's there.

**Practice apps** (scan the source only; never deploy them on a reachable network):

| App | Covers |
|---|---|
| [OWASP Juice Shop](https://owasp.org/www-project-juice-shop/) | Node.js and TypeScript back end, Angular front end. Its challenge list documents the vulnerabilities |
| [OWASP WebGoat](https://owasp.org/www-project-webgoat/) | Java and Spring |
| [OWASP NodeGoat](https://github.com/OWASP/NodeGoat) | Node.js and Express |
| [OWASP PyGoat](https://github.com/adeyosemanputra/pygoat) | Python and Django |
| [OWASP crAPI](https://owasp.org/www-project-crapi/) | APIs (the OWASP API Security Top 10) across several microservices |
| [OWASP WrongSecrets](https://owasp.org/www-project-wrongsecrets/) | Secrets handling |
| [TerraGoat](https://github.com/bridgecrewio/terragoat), [CDKGoat](https://github.com/bridgecrewio/cdkgoat) | Terraform and AWS CDK misconfigurations |
| [Kubernetes Goat](https://github.com/madhuakula/kubernetes-goat) | Kubernetes and containers |
| [OWASP Benchmark](https://owasp.org/www-project-benchmark/) | Java and Python test cases with an expected-results file, built for scoring how accurate a scanner is |

**How to measure:**
1. Clone a practice app into its own folder, and run the skill at **Standard** depth.
2. Compare the report against the app's documented vulnerabilities, or the Benchmark's expected-results file:
   - **True positives**: real vulnerabilities it reported.
   - **False positives**: findings that aren't real.
   - **Misses**: documented vulnerabilities it didn't report.
3. Repeat with no scanners installed (AI-only) and with all of them, to see how much the tools add.
4. Track the results over time. When you change the skill or its references, re-run the same apps and check that nothing got worse.

To automate this, the `skill-creator` skill can turn these runs into an eval set (prompts plus expected findings) and benchmark the skill's results across versions.

## Limitations

- **AI review is not a guarantee.** The skill reduces false positives by requiring code evidence for every finding and attempting to disprove serious ones. It can still miss vulnerabilities, especially in code paths it couldn't trace. Treat a clean report as reduced risk, not proof of security.
- **It does static analysis only.** No testing of running applications (DAST) or penetration testing. Exploit proofs are local tests you approve; nothing is ever sent to deployed systems.
- **Coverage depends on installed tools.** The report states exactly what ran and what didn't.
- **Versions in this README age.** Check each project's releases page before installing, and verify downloads as shown above.
