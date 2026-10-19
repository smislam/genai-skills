# Standards and taxonomies

Every finding carries one primary **CWE** ID. Derive the other tags from it: OWASP category, CWE Top 25 rank, and any context-specific list (API, LLM, agentic, mobile, CI/CD). Verified against primary sources on 2026-10-15. When a tag decides severity or a compliance claim, re-check the source if you have tools.

## Contents
- [OWASP Top 10:2025 (current)](#owasp-top-102025-current)
- [CWE Top 25 Most Dangerous Software Weaknesses, 2025](#cwe-top-25-most-dangerous-software-weaknesses-2025)
- [Context-specific lists](#context-specific-lists)
- [OWASP ASVS 5.0.0 (May 30, 2025)](#owasp-asvs-500-may-30-2025)
- [Secure-coding standards (secondary IDs)](#secure-coding-standards-secondary-ids)
- [Compliance evidence the scan supports](#compliance-evidence-the-scan-supports)
- [Severity and prioritization](#severity-and-prioritization)
- [Output formats](#output-formats)


## OWASP Top 10:2025 (current)

Source: `https://top10.owasp.org/2025/`. It maps 248 CWEs. Use OWASP's per-category CWE lists to assign the category.

| ID | Category | Notes |
|---|---|---|
| A01 | Broken Access Control | Now includes SSRF |
| A02 | Security Misconfiguration | |
| A03 | Software Supply Chain Failures | New; widens 2021's "vulnerable components" to the whole supply chain |
| A04 | Cryptographic Failures | |
| A05 | Injection | |
| A06 | Insecure Design | |
| A07 | Authentication Failures | |
| A08 | Software or Data Integrity Failures | |
| A09 | Security Logging and Alerting Failures | |
| A10 | Mishandling of Exceptional Conditions | New |

**Mapping from 2021**, for teams still reporting against it:

| 2021 | 2025 |
|---|---|
| A01 Broken Access Control | A01 |
| A02 Cryptographic Failures | A04 |
| A03 Injection | A05 |
| A04 Insecure Design | A06 |
| A05 Security Misconfiguration | A02 |
| A06 Vulnerable and Outdated Components | A03 |
| A07 Identification and Authentication Failures | A07 |
| A08 Software and Data Integrity Failures | A08 |
| A09 Security Logging and Monitoring Failures | A09 |
| A10 Server-Side Request Forgery | A01 |

## CWE Top 25 Most Dangerous Software Weaknesses, 2025

Published by MITRE and CISA on December 15, 2025, from 39,080 CVE records. Source: `https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html`. "SANS/CWE Top 25" is a legacy name, and SANS isn't credited on the 2025 list. Cite it as "CWE Top 25 (2025)". Flag each finding whose CWE is on the list, with its rank.

| Rank | CWE | Weakness |
|---|---|---|
| 1 | CWE-79 | Cross-site Scripting |
| 2 | CWE-89 | SQL Injection |
| 3 | CWE-352 | Cross-Site Request Forgery |
| 4 | CWE-862 | Missing Authorization |
| 5 | CWE-787 | Out-of-bounds Write |
| 6 | CWE-22 | Path Traversal |
| 7 | CWE-416 | Use After Free |
| 8 | CWE-125 | Out-of-bounds Read |
| 9 | CWE-78 | OS Command Injection |
| 10 | CWE-94 | Code Injection |
| 11 | CWE-120 | Classic Buffer Overflow |
| 12 | CWE-434 | Unrestricted Upload of File with Dangerous Type |
| 13 | CWE-476 | NULL Pointer Dereference |
| 14 | CWE-121 | Stack-based Buffer Overflow |
| 15 | CWE-502 | Deserialization of Untrusted Data |
| 16 | CWE-122 | Heap-based Buffer Overflow |
| 17 | CWE-863 | Incorrect Authorization |
| 18 | CWE-20 | Improper Input Validation |
| 19 | CWE-284 | Improper Access Control |
| 20 | CWE-200 | Exposure of Sensitive Information to an Unauthorized Actor |
| 21 | CWE-306 | Missing Authentication for Critical Function |
| 22 | CWE-918 | Server-Side Request Forgery |
| 23 | CWE-77 | Command Injection |
| 24 | CWE-639 | Authorization Bypass Through User-Controlled Key |
| 25 | CWE-770 | Allocation of Resources Without Limits or Throttling |

## Context-specific lists

Apply a list only when the code has that surface. Tag a finding with both its OWASP Top 10 category and the context list item.

**OWASP API Security Top 10 (2023)**, for HTTP APIs, OpenAPI specs, GraphQL, and gRPC:
- API1 Broken Object Level Authorization
- API2 Broken Authentication
- API3 Broken Object Property Level Authorization
- API4 Unrestricted Resource Consumption
- API5 Broken Function Level Authorization
- API6 Unrestricted Access to Sensitive Business Flows
- API7 Server Side Request Forgery
- API8 Security Misconfiguration
- API9 Improper Inventory Management
- API10 Unsafe Consumption of APIs

**OWASP Top 10 for LLM Applications (2025)**, for code that calls LLMs, builds prompts, or runs retrieval (RAG):
- LLM01 Prompt Injection
- LLM02 Sensitive Information Disclosure
- LLM03 Supply Chain
- LLM04 Data and Model Poisoning
- LLM05 Improper Output Handling
- LLM06 Excessive Agency
- LLM07 System Prompt Leakage
- LLM08 Vector and Embedding Weaknesses
- LLM09 Misinformation
- LLM10 Unbounded Consumption

**OWASP Top 10 for Agentic Applications (2026)**, released December 2025, for agents with tools, memory, or multi-agent communication:
- ASI01 Agent Goal Hijack
- ASI02 Tool Misuse
- ASI03 Identity & Privilege Abuse
- ASI04 Agentic Supply Chain Vulnerabilities
- ASI05 Unexpected Code Execution
- ASI06 Memory & Context Poisoning
- ASI07 Insecure Inter-Agent Communication
- ASI08 Cascading Failures
- ASI09 Human-Agent Trust Exploitation
- ASI10 Rogue Agents

**OWASP Mobile Top 10 (2024)**, for Android and iOS code:
- M1 Improper Credential Usage
- M2 Inadequate Supply Chain Security
- M3 Insecure Authentication/Authorization
- M4 Insufficient Input/Output Validation
- M5 Insecure Communication
- M6 Inadequate Privacy Controls
- M7 Insufficient Binary Protections
- M8 Security Misconfiguration
- M9 Insecure Data Storage
- M10 Insufficient Cryptography

**OWASP Top 10 CI/CD Security Risks**, for pipeline definitions such as `.github/workflows/*`, `.gitlab-ci.yml`, Jenkinsfiles, and buildspecs:
- CICD-SEC-1 Insufficient Flow Control Mechanisms
- CICD-SEC-2 Inadequate Identity and Access Management
- CICD-SEC-3 Dependency Chain Abuse
- CICD-SEC-4 Poisoned Pipeline Execution
- CICD-SEC-5 Insufficient PBAC (Pipeline-Based Access Controls)
- CICD-SEC-6 Insufficient Credential Hygiene
- CICD-SEC-7 Insecure System Configuration
- CICD-SEC-8 Ungoverned Usage of 3rd Party Services
- CICD-SEC-9 Improper Artifact Integrity Validation
- CICD-SEC-10 Insufficient Logging and Visibility

## OWASP ASVS 5.0.0 (May 30, 2025)

Use this to name the verifiable control a finding violates, and to scope a review to a level. Source: `https://github.com/OWASP/ASVS/tree/master/5.0/en`.

**Levels:**
- **L1:** first layer of defense.
- **L2:** standard practice for most applications.
- **L3:** high assurance.

**Chapters:**
- V1 Encoding and Sanitization
- V2 Validation and Business Logic
- V3 Web Frontend Security
- V4 API and Web Service
- V5 File Handling
- V6 Authentication
- V7 Session Management
- V8 Authorization
- V9 Self-contained Tokens
- V10 OAuth and OIDC
- V11 Cryptography
- V12 Secure Communication
- V13 Configuration
- V14 Data Protection
- V15 Secure Coding and Architecture
- V16 Security Logging and Error Handling
- V17 WebRTC

Cite requirements by chapter and number as written in the ASVS 5.0 source. Don't invent an ID format.

## Secure-coding standards (secondary IDs)

- **SEI CERT** coding standards for C, C++, Java, Android, and others, now at `https://cmu-sei.github.io/secure-coding-standards/`. Use rule IDs such as `IDS00-J` as secondary identifiers where a team reports against CERT.
- **MISRA C:2025** and **MISRA C++:2023**, only for safety-critical C or C++ when the team states it follows them.

## Compliance evidence the scan supports

State what the scan is evidence *for*. Never claim it makes a system compliant.

- **NIST SP 800-218 (SSDF) v1.1.** The scan supports PW.7 (review and analyze human-readable code), PW.5 (secure coding practices), PW.9 (secure defaults), and RV.1–RV.3 (respond to vulnerabilities). SSDF v1.2 (Rev. 1) has been an Initial Public Draft since December 2025 and is not final.
- **NIST SP 800-53 Rev. 5.** The scan supports SA-11 (Developer Testing and Evaluation) and its enhancements SA-11(1) Static Code Analysis and SA-11(4) Manual Code Reviews.
- **PCI DSS v4.0.1, Requirement 6.** The scan supports the review of bespoke and custom code before release, the coding techniques that prevent common attacks, and the inventory of third-party components (via the package list in `coverage.json`). Cite sub-requirement numbers only after reading them in the PCI DSS document itself.

## Severity and prioritization

- **CVSS v4.0** (FIRST, November 2023). Severity bands: None 0.0, Low 0.1–3.9, Medium 4.0–6.9, High 7.0–8.9, Critical 9.0–10.0. Label the score with the metric groups used: CVSS-B (base only), CVSS-BT (with threat), CVSS-BE (with environmental), or CVSS-BTE. FIRST says base scores alone "should not be used alone to assess risk."
- **EPSS** (FIRST): the probability that a CVE is exploited in the next 30 days, published daily. Look it up at `https://api.first.org/data/v1/epss?cve=<CVE-ID>`.
- **CISA KEV** (Known Exploited Vulnerabilities): the catalog of vulnerabilities with confirmed exploitation in the wild. It is **mandatory on every run**: download it fresh, never rely on a cached copy older than 24 hours, and never on memory.
  - JSON feed: `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json`.
  - CSV feed: `https://www.cisa.gov/sites/default/files/csv/known_exploited_vulnerabilities.csv`.
  - Record the catalog's version and release date in the report.
  - Match on CVE ID. For each match, report the date it was added to KEV, CISA's due date, and whether it is known to be used in ransomware campaigns. CISA's **BOD 26-04** (June 10, 2026) sets remediation timelines based on exposure, KEV status, whether exploitation can be automated, and technical impact.

`triage.md` defines how these combine into the skill's severity.

## Output formats

- **SARIF 2.1.0** (OASIS Standard, Errata 01, August 2023): the primary machine output. GitHub code scanning accepts only 2.1.0.
- **GitLab** ingests its own JSON security report schema (for example `gl-sast-report.json`), not SARIF. Generate it only when asked; reports that fail schema validation are rejected.

See `output.md` for field mapping.
