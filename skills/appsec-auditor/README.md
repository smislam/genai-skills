# appsec-auditor

An Agent Skill for Claude Code that audits a **whole repository** for security vulnerabilities the way an AppSec engineer would, with **nothing to install** and **deterministic coverage**. The AI does the review:
- it maps the attack surface;
- it walks every entry point through to its sinks (injection, authorization, authentication, business logic, crypto, CI/CD, IaC, containers, LLM and agent code);
- it searches the code and git history for leaked secrets;
- it checks every dependency against live vulnerability data from OSV.dev and the CISA KEV catalog;
- it analyzes how findings chain into real exploits.

Scripts build a fixed checklist from the repository, the AI must decide every item on it, and a hook won't let the audit finish until it has. Every finding is proven against the code before it's reported. Findings map to CWE, OWASP Top 10 (2025), CWE Top 25 (2025), and ASVS 5.0. License risk and performance problems are reported in separate sections. Output is a Markdown report, a SARIF 2.1.0 file, optional GitLab security reports, and proposed fixes as diffs.

This README is for people setting the skill up. The agent's instructions are in `SKILL.md` and `references/`.

## When to use it, and when to use `/security-review`

| | `/security-review` (built into Claude Code) | `appsec-auditor` |
|---|---|---|
| Scope | The pending changes on your current branch | The whole repository as it stands |
| Use it for | A security check before you merge a change | A full audit: before a release, of an inherited codebase, or periodically |
| Covers | The new code | Code, dependencies (live CVE and KEV data), secrets in git history, IaC, containers, CI/CD, exploit chains, licenses, performance |
| Output | Findings in the conversation | Report, SARIF, GitLab reports, proposed fixes |

Ask `appsec-auditor` to review only your branch's changes, and it points you to `/security-review`.

## Install the skill

Copy the whole folder, not just `SKILL.md`. The scripts, references, and optional guardrail hooks are part of the skill.

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

Run `/reload-plugins`, or start a new session. Then ask for an audit ("run a full security audit of this repository"), or invoke it directly with `/appsec-auditor`.

The folder also contains `.claude-plugin/plugin.json`, so Claude Code loads it as the plugin `appsec-auditor@skills-dir`, which carries the optional guardrail hooks. A copy under a project's `.claude/skills/` loads only after you accept the workspace trust dialog for that folder.

## Requirements

**Nothing is installed by the skill, or for it.** It needs:

| Requirement | Used for |
|---|---|
| Claude Code | Running the skill and its hooks |
| **Node.js 18 or later** | The checklist scripts, the guardrail hooks, and the coverage gate (standard library only, with no npm packages) |
| `git` | The file list, and secrets in git history |
| `curl` | All network calls, including through corporate proxies. Ships with macOS, Linux, Git Bash, and Windows 10+ |
| Network access to `api.osv.dev`, `www.cisa.gov`, `api.first.org`, and `repo1.maven.org`, directly, through a proxy, or through internal mirrors | Live vulnerability data. Without it, the report marks dependency results **not checked** instead of calling them clean |

Without Node.js, the audit still runs by instruction alone, but nothing enforces the coverage, and the report is labeled **non-deterministic**.

**Optional, if already present:** security scanners you already have (Semgrep, Gitleaks, OSV-Scanner, Trivy, Checkov, and others). The skill runs them as an extra source of candidates and verifies their results like everything else. It never asks you to install one. See `references/tools.md`.

Check what's present:

```bash
bash ~/.claude/skills/appsec-auditor/scripts/check-tools.sh
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$HOME\.claude\skills\appsec-auditor\scripts\check-tools.ps1"
```

## Corporate proxies and firewalls

Every network call goes through `curl`, so standard proxy settings work. Test them:

```bash
node ~/.claude/skills/appsec-auditor/scripts/net-check.js
```

It tests each endpoint and names the problem when one fails. Set these in the environment Claude Code runs in, or in Claude Code's `env` settings:

| Situation | Setting |
|---|---|
| A proxy is required | `HTTPS_PROXY=http://proxy.corp.example:8080` (and `NO_PROXY` for exceptions), or `APPSEC_PROXY` to set it for this skill only |
| The proxy authenticates with your Windows login (NTLM/Kerberos) | `APPSEC_PROXY_AUTH=negotiate` (or `ntlm`). curl uses the logged-in user's credentials; no password is stored |
| The proxy uses a username and password | `APPSEC_PROXY_AUTH=basic`, with `http://user:password@proxy:port` as the proxy. Credentials are never printed or written to reports |
| TLS inspection (the corporate CA re-signs traffic) | Works automatically on Windows (system certificate store). Elsewhere: `APPSEC_CA_BUNDLE=/path/to/corporate-root-ca.pem` |
| Windows revocation checks fail through the proxy | `APPSEC_SSL_REVOKE_BEST_EFFORT=1` |
| No internet, only internal mirrors | `APPSEC_OSV_URL`, `APPSEC_KEV_URL`, `APPSEC_EPSS_URL`, `APPSEC_MAVEN_URL` (for example an Artifactory or Nexus Maven mirror) |

These were tested against a forward proxy, both open and requiring authentication, and with `NO_PROXY` bypass. NTLM and Kerberos use curl's standard `--proxy-negotiate` support.

## Deterministic coverage

What gets examined doesn't depend on the AI:

1. **`inventory.js`** builds the checklist, `coverage.json`:
   - every file;
   - every hit of the versioned rules in `rules/rules.json`: sinks, misconfigurations, entry points, and secrets, including git history;
   - every package from lockfiles and manifests.

   Each item gets a stable ID.
2. **`deps.js`** checks every package against OSV.dev, CISA KEV, and EPSS, and adds one item per advisory.
3. **The AI decides every item** in `ledger.json`: a finding, a false positive with the reason, or needs review. It must open every entry-point file. A hook logs each file it reads.
4. **The `Stop` hook** runs `coverage-check.js` and won't let the audit finish until every item is decided, every entry-point file was read, and the report carries the coverage summary. The summary's numbers come from the script, not the AI.

The same commit, rules version, and depth produce the same checklist every time. Two audits of the same commit can be compared decision by decision. The AI's *judgment* on an item can still differ between runs, but every judgment is recorded with its reason. Details: `references/coverage.md`.

## What it never does

- **Install anything:** no scanners, packages, plugins, or runtimes.
- **Run your project's code** (builds, tests, package installs, `cdk synth`, `terraform init`) without asking you first.
- **Send your code or secrets anywhere.** Only package names and versions go to OSV.dev, and CVE IDs to FIRST EPSS. The KEV catalog is a download.
- **Test live systems.** Exploit analysis stays on paper, or in local tests you approve.
- **Report findings to anyone but you:** no issues, pull requests, advisories, or emails to maintainers.
- **Change your code** without your approval. Fixes are proposed as diffs.
- **Show full secrets.** They're redacted everywhere, to at most the first 4 characters.

## How it checks dependencies without a scanner

1. **Package list:** `inventory.js` parses your lockfiles and manifests (npm, Yarn, pnpm, Poetry, uv, Pipenv, pip, Maven, Gradle, Go, Cargo, NuGet, Bundler, Composer) into a list of every package and its exact version.
2. **OSV.dev:** `deps.js` sends that list to [OSV.dev](https://osv.dev), the open vulnerability database behind many commercial scanners. It returns each matching advisory, with its CVE IDs, severity, and fixed versions.
3. **KEV and EPSS:** it downloads the current CISA Known Exploited Vulnerabilities catalog, flags every CVE that's being actively exploited, and adds each CVE's EPSS exploit-probability score.
4. **Reachability:** the AI checks whether your code actually uses the vulnerable part of each library.

**One limitation:** Maven and Gradle projects usually have no lockfile. The skill resolves versions managed by a parent POM or BOM (such as Spring Boot's) from Maven Central, but it can't list transitive dependencies without running the build. It reports those as not checked, and suggests committing a lockfile or generating an SBOM in CI.

## Hooks

The folder loads as the plugin `appsec-auditor@skills-dir`, with three hooks (Node.js). All of them do nothing unless an audit is running: the skill creates `.appsec-audit/.active` when it starts, and removes it at the end. Markers older than 24 hours are ignored.

| Hook | What it does |
|---|---|
| `PreToolUse` (`guard.js`) | **Asks you** before: commands that run project code, running scripts by path (except the skill's own), anything that sends data off the machine, edits outside `.appsec-audit/`, and `git push`. **Blocks:** piping downloaded scripts into a shell, unredacted secrets in the report, edits to the checklist files, and reporting findings outside the machine (issues, pull requests, advisories, comments, email) |
| `PostToolUse` (`track.js`) | Logs each file the AI opens, as evidence for the coverage gate |
| `Stop` (`gate.js`) | Sends the AI back to work until coverage is complete. If the audit needs to wait for you, the skill marks it paused, so the gate lets the turn end |

The hooks work with both the Bash and PowerShell tools and handle Windows paths. Because they're loaded as a plugin, Claude Code starts them on every matching event in every session; without an audit marker they exit immediately. To turn them off: `claude plugin disable appsec-auditor@skills-dir`.

**If the hooks don't load** (a plain-skill copy, or an untrusted workspace), the skill detects it at the start of an audit and asks whether to enable them or continue. If you continue, the AI follows the rules by instruction alone, and the report says the guardrails and the entry-point read check were **not enforced**. Everything else, including the checklist, the ledger, and the coverage summary, works the same.

## Output

Each audit writes to `.appsec-audit/` at the repository root:
- `report.md`: the human-readable report.
- `findings.json` and `results.sarif`: the findings in structured form, and SARIF 2.1.0 rendered from them by `sarif.js` (deterministic: the same findings give the same file). GitHub code scanning and SARIF-aware IDEs can ingest it.
- `coverage.json`, `deps.json`, `ledger.json`, `reads.jsonl`, `files.txt`: the checklist, the dependency data, the AI's decisions, and the read log. Keep them with the report; they're the evidence for its coverage numbers.
- `data/kev.json`: the KEV catalog used.
- `gitlab/`: GitLab security reports (`gl-sast-report.json`, `gl-secret-detection-report.json`, `gl-dependency-scanning-report.json`) when you ask for GitLab output. Publish them from a CI job as `artifacts: reports:`; the skill shows you the job snippet.
- `raw/`: output of any already-installed scanner it ran.

**Add `.appsec-audit/` to `.gitignore`.** The report describes exploitable weaknesses. The skill offers to add it.

**Depth:** Standard by default. Ask for **Quick** on very large repositories or for a first look, and **Deep** before a release or for high-risk systems.

## Validate the skill

Before relying on the skill, measure it. Run it against intentionally vulnerable practice applications, where the vulnerabilities are known in advance, and compare what it found with what's there. AI-led review varies more than rule-based scanners, so this matters.

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
| [OWASP Benchmark](https://owasp.org/www-project-benchmark/) | Java and Python test cases with an expected-results file, built for scoring accuracy |

**How to measure:**
1. Clone a practice app into its own folder, and run the skill at **Standard** depth.
2. Compare the report against the app's documented vulnerabilities, or the Benchmark's expected-results file:
   - **True positives**: real vulnerabilities it reported.
   - **False positives**: findings that aren't real.
   - **Misses**: documented vulnerabilities it didn't report.
3. Run the same app two or three times. AI review isn't fully deterministic, and the spread between runs tells you how consistent it is.
4. Track the results over time. When you change the skill or its references, re-run the same apps and check that nothing got worse.

To automate this, the `skill-creator` skill can turn these runs into an eval set (prompts plus expected findings) and benchmark the skill's results across versions.

## Limitations

- **AI-led review is not exhaustive.** It's thorough where it looks, and every finding is proven, but it doesn't apply thousands of fixed rules the way a scanner does. It can miss vulnerabilities, especially in code paths it didn't trace, and results can vary between runs. Treat a clean report as reduced risk, not proof of security. For regulated or high-assurance work, pair it with your organization's approved scanners.
- **It does static analysis only.** No testing of running applications (DAST) or penetration testing.
- **Dependency coverage depends on lockfiles.** Without one, transitive dependencies may go unchecked; the report says which.
- **Very large repositories** take time and tokens. Use Quick depth, or audit one service at a time.
