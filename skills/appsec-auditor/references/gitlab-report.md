# GitLab security reports

GitLab shows security findings in merge request widgets, the pipeline security tab, and the vulnerability report. It reads them only from its own JSON format, not SARIF. Produce these reports when the user asks for GitLab output, or when the repository has a `.gitlab-ci.yml` and the user wants the findings in GitLab.

Verified against GitLab's security report schemas, version **15.2.5**, on 2026-10-15. Schemas: `https://gitlab.com/gitlab-org/security-products/security-report-schemas/-/raw/master/dist/<name>-report-format.json`. GitLab rejects any report that fails schema validation, so validate before handing it over (section 4).

## 1. Which file gets which findings

| File | `scan.type` | Contains |
|---|---|---|
| `gl-sast-report.json` | `sast` | Code findings, IaC and container-configuration findings, and exploit chains |
| `gl-secret-detection-report.json` | `secret_detection` | Secrets |
| `gl-dependency-scanning-report.json` | `dependency_scanning` | Vulnerable dependencies |

Write them to `.appsec-audit/gitlab/`. Include verified findings only (Confirmed and Likely), the same set as `results.sarif`. License and performance findings are not included.

## 2. Common structure

```json
{
  "version": "15.2.5",
  "scan": {
    "analyzer": { "id": "appsec-auditor", "name": "appsec-auditor", "version": "1.0.0", "vendor": { "name": "appsec-auditor" } },
    "scanner":  { "id": "appsec-auditor", "name": "appsec-auditor", "version": "1.0.0", "vendor": { "name": "appsec-auditor" } },
    "type": "sast",
    "start_time": "2026-10-15T14:02:11",
    "end_time": "2026-10-15T14:31:40",
    "status": "success"
  },
  "vulnerabilities": []
}
```

- **Required**: `version`, `scan`, `vulnerabilities`. In `scan`: `analyzer`, `scanner`, `type`, `start_time`, `end_time`, `status`. In `analyzer` and `scanner`: `id`, `name`, `version`, `vendor.name`.
- **Timestamps** must match `yyyy-mm-ddThh:mm:ss` exactly, in UTC, with **no `Z` and no fractional seconds**. `2026-10-15T14:02:11Z` fails validation.
- **`status`**: `success`, or `failure` if the audit couldn't complete.

## 3. Each vulnerability

| Field | Required | Value |
|---|---|---|
| `id` | Yes | A UUID, stable for the same finding across runs: derive it from the SARIF fingerprint (a UUID v5 of the fingerprint) |
| `identifiers` | Yes | A list of `{type, name, value}`. **The first entry is the primary identifier.** Use the rule first (`{"type": "appsec_auditor_rule", "name": "<rule id>", "value": "<rule id>"}`), then `{"type": "cwe", "name": "CWE-89", "value": "89"}`, then `{"type": "cve", "name": "CVE-2025-1234", "value": "CVE-2025-1234"}` for dependencies, and OWASP if useful (`{"type": "owasp", "name": "A05:2025 - Injection", "value": "A05:2025"}`) |
| `location` | Yes | See below; differs by report type |
| `severity` | No, but always set it | `Critical`, `High`, `Medium`, `Low`, `Info`, or `Unknown` (capitalized exactly like this) |
| `name` | No, but always set it | The finding title |
| `description` | No | What, path, exploit scenario, impact (Markdown is allowed). **Redact secrets** (SKILL.md rule 7) |
| `solution` | No | The fix guidance |
| `cvss_vectors` | No | `[{"vendor": "appsec-auditor", "vector": "CVSS:4.0/AV:N/..."}]` when an estimated vector exists |
| `links` | No | `[{"url": "https://cwe.mitre.org/data/definitions/89.html"}]`, advisories, and the KEV entry for KEV-listed CVEs |

**Location by type:**

- **SAST:** `{"file": "src/app/UserController.java", "start_line": 88, "end_line": 92}`. `class` and `method` are optional.
- **Secret detection:** also requires `commit.sha`. Use the commit where the secret was found (from Gitleaks history results), or `HEAD`'s SHA for the working tree: `{"file": "config/prod.env", "start_line": 3, "commit": {"sha": "<40-char sha>"}}`.
- **Dependency scanning:** requires `file` (the manifest or lockfile) and `dependency` with `package.name` and `version`. `direct` is optional: `{"file": "package-lock.json", "dependency": {"package": {"name": "lodash"}, "version": "4.17.20", "direct": false}}`.

## 4. Validate

1. Download the schema for each report type from the URL above. This is a download only; no code is sent.
2. Validate each report with a JSON Schema validator that is already available, for example Python with `jsonschema` installed: `python -m jsonschema -i gl-sast-report.json sast-report-format.json`. If no validator is available, ask before installing one. Otherwise check the required fields above by hand, and tell the user the report wasn't machine-validated.
3. Fix any errors before telling the user the report is ready.

## 5. Using the reports in GitLab CI

Tell the user how to publish them. GitLab reads report artifacts from a CI job:

```yaml
appsec-auditor-results:
  stage: test
  script:
    - echo "Publishing appsec-auditor reports"
  artifacts:
    reports:
      sast: .appsec-audit/gitlab/gl-sast-report.json
      secret_detection: .appsec-audit/gitlab/gl-secret-detection-report.json
      dependency_scanning: .appsec-audit/gitlab/gl-dependency-scanning-report.json
```

Which GitLab tiers show which reports in the merge request widget and the vulnerability report depends on the user's GitLab subscription. Say so, and don't promise a specific UI.
