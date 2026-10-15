# Output

Every run produces two artifacts, and proposed fixes when there are findings:

```
.appsec-audit/
├── report.md          # human-readable report (template below)
├── results.sarif      # SARIF 2.1.0, verified findings only
└── raw/               # each tool's own output, untouched (e.g. semgrep.sarif, osv.json)
```

- Write to `.appsec-audit/` at the repository root unless the user names another location. Before writing, tell the user the directory should be git-ignored, and offer to add it to `.gitignore`. The report describes exploitable weaknesses, so it shouldn't be committed by accident.
- **Redact secrets everywhere**: in the report, the SARIF, and your replies. Show the type, location, and at most the first 4 characters, as in `AKIA****` at `config/prod.env:3`. Never echo a full secret.
- GitLab security reports (`.appsec-audit/gitlab/gl-*-report.json`) are generated when the user wants findings in GitLab. Follow `gitlab-report.md`.

## Report template

Lead with the verdict. A reader who stops after the summary should know how bad it is and what to fix first.

```markdown
# Application Security Audit: <repository or path>

**Date:** <YYYY-MM-DD> · **Commit:** <sha, or "working tree"> · **Mode:** <full | diff against <base>> · **Depth:** <Quick | Standard | Deep>

## Summary

**<n> findings: <c> Critical, <h> High, <m> Medium, <l> Low** (+ <k> exploit chains).
<Two or three sentences: the most serious risk, the cheapest fix that removes the most risk, and the overall posture.>

**Fix first:**
1. <finding or chain ID — one line>
2. ...

## Coverage

| Category | Tools run (version) | AI review | Coverage |
|---|---|---|---|
| SAST | opengrep 1.x, bandit 1.x | Yes | Full |
| Dependencies | osv-scanner 2.x | Yes | Full — KEV/EPSS checked live |
| Secrets | gitleaks 8.x (tree + history) | Yes | Full |
| IaC / containers | checkov 3.x | Yes | Partial — `cdk synth` not run (not approved); CDK constructs reviewed by AI only |

**Vulnerability data:**

| Source | Version / last updated | Status |
|---|---|---|
| CISA KEV catalog | <catalog version>, released <date> | Downloaded this run |
| <scanner> vulnerability DB | <timestamp> | Current (< 24 h) / **STALE** / **offline** |
| FIRST EPSS | scores dated <date> | Looked up this run |

<If any row isn't current, add a warning at the top of the Summary: dependency results are not verified against current data.>

**Not covered / reduced:** <each missing tool or skipped step, and what it means for confidence>
**Languages and surfaces found:** <languages, frameworks, entry points, IaC, pipelines, LLM/agent code>

## Exploit chains

<One block per chain, using the format in exploit-chains.md, most severe first.>

## Findings

<Most severe first. One block per finding:>

### F-01. <title> — Critical · Confirmed
- **Where:** `<path>:<line>` (+ related locations)
- **What:** <the vulnerability, specifically>
- **Path:** <source → ... → sink, with file:line at each step>
- **Exploit scenario:** <how an attacker triggers it, and the preconditions>
- **Impact:** <what they get>
- **Classification:** CWE-<n> (<name>) · OWASP A0x:2025 · CWE Top 25 #<rank> · <API/LLM/ASI/CICD item if any> · ASVS V<n>
- **Severity basis:** <matrix cell from triage.md> · CVSS-B (estimated) `<vector>`. For dependencies: **KEV <yes — added <date>, CISA due <date>, ransomware <Known/Unknown> | no>**, EPSS <p> (<percentile>, <date>), reachable <yes/no/unknown>
- **Detected by:** <tool + rule ID, or "AI review">
- **Part of chain:** <C-n, or none>
- **Fix:** <what to change and why it works>

  ```diff
  <proposed patch>
  ```
- **Verify the fix:** <the test or check that proves it>

## License risk

<From `licenses.md`. Not counted with security findings, and not included in the SARIF file.>

## Performance

<From `performance.md`. Not counted with security findings, and not included in the SARIF or GitLab reports. Omit at Quick depth and say so.>

## Needs human review

<Candidates whose path couldn't be traced, with the reason. Not counted as findings.>

## Suppressions and false positives

<Existing suppressions that were respected or overridden, with reasons, and a count of scanner results dismissed as false positives by category, with an example of each.>

## Evidence for compliance

<Only if relevant: what this scan supports, e.g. "SSDF PW.7; NIST 800-53 SA-11(1)". Never claim compliance.>
```

## SARIF 2.1.0 mapping

`results.sarif` contains **verified findings only**: Confirmed and Likely, including chains. Raw scanner output stays in `raw/`. Use one run with `tool.driver.name` set to `appsec-auditor`, and record each contributing tool and its version in `run.properties.tools`.

| Report field | SARIF location |
|---|---|
| Finding ID (`F-01`, `C-1`) | `result.properties.findingId` |
| Rule | `result.ruleId`, plus a `tool.driver.rules[]` entry: `id` (the source tool's rule ID, or `appsec/<cwe>-<slug>` for AI findings), `shortDescription`, `fullDescription`, `help.markdown` (the fix guidance) |
| Severity | `result.level`: Critical and High → `error`, Medium → `warning`, Low and Info → `note`. Also `rule.properties.security-severity` as a string score: the estimated CVSS-B score if there is one, otherwise Critical `"9.5"`, High `"8.0"`, Medium `"5.5"`, Low `"2.0"` |
| Confidence | `rule.properties.precision`: Confirmed → `high`, Likely → `medium` |
| Classification | `rule.properties.tags`: `["security", "external/cwe/cwe-89", "owasp-top10-2025/A05", "cwe-top25-2025/2"]` |
| Location | `result.locations[0].physicalLocation`: `artifactLocation.uri` relative to the repository root, plus `region.startLine` (and `endLine` when known) |
| Source → sink path | `result.codeFlows[0].threadFlows[0].locations[]`, one per step |
| Related locations, chain members | `result.relatedLocations[]`; for chains, `result.properties.chainMembers: ["F-07", "F-12"]` |
| Message | `result.message.text`: one sentence naming the weakness and the impact |
| Stable identity | `result.partialFingerprints`: `{"primaryLocationLineHash/v1": "<hash of the normalized sink line>"}`, so findings survive line shifts across runs |
| Diff mode | `result.baselineState`: `new`, `unchanged`, or `updated` |
| Respected suppression | `result.suppressions[]`: `{"kind": "inSource", "justification": "<reason from the code>"}` |

Validate the file before handing it over: it must be valid JSON, use `"version": "2.1.0"`, and use `"$schema": "https://json.schemastore.org/sarif-2.1.0.json"`. If a validator is available (for example `npx @microsoft/sarif-multitool validate`), run it, but ask first if it would need installing.
