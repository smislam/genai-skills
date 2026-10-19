# Output

Every run produces two artifacts, and proposed fixes when there are findings:

## Contents
- [Report template](#report-template)
- [findings.json](#findingsjson)


```
.appsec-audit/
├── report.md          # human-readable report (template below)
├── results.sarif      # SARIF 2.1.0, verified findings only
├── coverage.json      # the deterministic checklist (inventory.js)
├── deps.json          # OSV, KEV, and EPSS results (deps.js)
├── ledger.json        # your decision for every checklist item
├── reads.jsonl        # files you opened (track hook)
├── state.json         # running / paused / done
├── files.txt          # files scanned
├── data/              # kev.json
└── raw/               # output of any already-installed scanner, if one was run
```

- Write to `.appsec-audit/` at the repository root unless the user names another location. Before writing, tell the user the directory should be git-ignored, and offer to add it to `.gitignore`. The report describes exploitable weaknesses, so it shouldn't be committed by accident.
- **Redact secrets everywhere**: in the report, the SARIF, and your replies. Show the type, location, and at most the first 4 characters, as in `AKIA****` at `config/prod.env:3`. Never echo a full secret.
- GitLab security reports (`.appsec-audit/gitlab/gl-*-report.json`) are generated when the user wants findings in GitLab. Follow `gitlab-report.md`.

## Report template

Lead with the verdict. A reader who stops after the summary should know how bad it is and what to fix first.

```markdown
# Application Security Audit: <repository or path>

**Date:** <YYYY-MM-DD> · **Commit:** <sha, or "working tree"> · **Depth:** <Quick | Standard | Deep> · **Method:** AI-led review<, plus <scanners already installed>>

## Summary

**<n> findings: <c> Critical, <h> High, <m> Medium, <l> Low** (+ <k> exploit chains).
<Two or three sentences: the most serious risk, the cheapest fix that removes the most risk, and the overall posture.>

**Fix first:**
1. <finding or chain ID — one line>
2. ...

## Coverage

<Paste the output of `node scripts/coverage-check.js --root <repo> --summary` here, verbatim. It's the deterministic checklist summary, and the coverage gate checks it's present and current. If Node.js wasn't available, write "**Non-deterministic: coverage not enforced**" instead.>

| Category | How it was covered | Coverage |
|---|---|---|
| Code | AI review of <n> entry points and their paths; <n> rule hits decided<; semgrep 1.x already installed, also run> | <Full / partial — what was skipped> |
| Dependencies | <n> packages from <lockfiles> queried at OSV.dev; KEV and EPSS checked live | <n> checked, <m> not checked (<why: no lockfile, transitive not resolved>) |
| Secrets | Secret patterns over the tree<, and git history (<branches>)> | <Full / tree only> |
| IaC / containers / CI | AI review of <files> | <Full / partial> |

State plainly that this is an AI-led review: thorough where it looked, but not exhaustive the way rule-based scanners are.

**Vulnerability data:**

| Source | Version / last updated | Status |
|---|---|---|
| CISA KEV catalog | <catalog version>, released <date> | Downloaded this run |
| OSV.dev | Queried <timestamp> | Live / **failed** |
| FIRST EPSS | scores dated <date> | Looked up this run |

<If any row isn't current, add a warning at the top of the Summary: dependency results are not verified against current data.>

**Not covered / reduced:** <each skipped step or unchecked area, and what it means for confidence>
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
- **Detected by:** <"AI review", "search pattern", "OSV.dev", or an already-installed tool + rule ID>
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

<Existing suppressions that were respected or overridden, with reasons, and a count of candidates dismissed as false positives by category, with an example of each.>

## Evidence for compliance

<Only if relevant: what this scan supports, e.g. "SSDF PW.7; NIST 800-53 SA-11(1)". Never claim compliance.>
```

## findings.json

`findings.json` holds every finding in structured form. `sarif.js` renders `results.sarif` from it, deterministically, and the gate checks the two match. Write it alongside the report:

```json
{
  "findings": [
    {
      "id": "F-01",
      "title": "All Actuator endpoints exposed without authentication",
      "severity": "High",
      "confidence": "Confirmed",
      "cwe": "CWE-200",
      "owasp": "A02:2025",
      "cvss": "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:L/VA:N/SC:N/SI:N/SA:N",
      "message": "Every Actuator endpoint, including heapdump, is reachable without authentication.",
      "locations": [{ "file": "src/main/resources/application.properties", "line": 21 }],
      "path": [{ "file": "src/main/resources/application.properties", "line": 21, "note": "exposure.include=*" }],
      "fix": "Set management.endpoints.web.exposure.include=health,info ...",
      "chain": []
    }
  ]
}
```

- **Required:** `id` (`F-n`, or `C-n` for a chain), `title`, `severity` (`Critical`, `High`, `Medium`, `Low`, or `Info`), `confidence` (`Confirmed` or `Likely`; "needs review" items aren't findings), and at least one `locations` entry with a repository-relative `file` and a `line`.
- **Optional:** `cwe`, `owasp`, `cvss` (the estimated vector), `cvssScore`, `message` (one sentence), `path` (source-to-sink steps), `fix` (Markdown), and `chain` (member finding IDs, for chains).
- **Redact secrets** in every field (rule 7).

Then run `node ${CLAUDE_SKILL_DIR}/scripts/sarif.js --root <repo>`. Never edit `results.sarif` by hand; change `findings.json` and re-run.

**What `sarif.js` produces:**
- one run, with the tool name `appsec-auditor` and the commit;
- one rule per finding type (`appsec/<cwe>-<title>`), carrying `security-severity` (from the CVSS score, or the severity level) and CWE and OWASP tags;
- `level` from the severity: Critical and High → `error`, Medium → `warning`, Low and Info → `note`;
- the primary location, related locations, and the source-to-sink path as a code flow;
- `partialFingerprints` from a hash of the normalized source line, so results stay matched across line shifts.

Results are sorted by finding ID, so the same `findings.json` always gives a byte-identical file.
