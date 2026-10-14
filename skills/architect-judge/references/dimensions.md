# Evaluation dimensions

Six dimensions, each with criteria, the standards they are measured against, and the failure signs that most often justify a finding. Criteria are probes, not a form to fill in: score every criterion in scope, but put your words where the evidence bites.

Each criterion has an ID (for example `DAT-4`). Well-Architected findings use the AWS question and best-practice IDs (for example `REL 9`, `SEC08-BP02`). Use it in findings so scores and issues cross-reference cleanly.

## Minimum reviewable content

An artifact is fully reviewable when it contains at least the following. Each item that is missing is a gap, scored under the dimension shown.

| Content | Dimension it feeds |
|---|---|
| Business context, goals, and in/out-of-scope statement | Alignment |
| Quantified non-functional requirements (availability, latency, throughput, RTO/RPO, cost envelope) | Alignment, Well-Architected |
| Context and container views (C4 levels 1–2 or equivalent), with deployment view | Quality |
| Data flows, data stores, and data classification | Data, Well-Architected (Security) |
| Trust boundaries and identity model | Well-Architected (Security) |
| Key decisions with alternatives and rationale (ADRs or equivalent) | Governance, Quality |
| Risks, assumptions, constraints, and open issues | Governance |
| Applicable regulatory and policy obligations | Compliance |
| Operational model: deployment, monitoring, incident response, ownership | Well-Architected, Governance |

## Adapting to the artifact type

| Artifact | Emphasize | De-emphasize (score N/A only if truly absent from scope) |
|---|---|---|
| Solution / system architecture | All six dimensions at full depth | — |
| Reference architecture | Quality, Governance (reuse rules, variation points), Security pillar baseline | Workload-specific NFR numbers |
| Design pattern | Quality (forces, consequences, applicability), Security pillar and Data implications of the pattern | Cost and Sustainability specifics |
| Cloud / migration strategy | Alignment, Governance (roadmap, decision rights), Data (migration, cutover), Reliability (rollback), Cost | Component-level detail |
| Trade-off analysis / ADR | Alternatives, criteria, evidence, consequences, reversibility | Full operational model |
| Infrastructure-as-code | Security, Reliability, Cost Optimization, and Operational Excellence pillars as implemented | Business alignment (judge only against what the repo states) |

---

## 1. Architecture Alignment (`ALN`)

Does the design serve the goals it claims, within the enterprise context it claims to operate in?

Standards: ISO/IEC/IEEE 42010:2022 (stakeholders, concerns, viewpoints); TOGAF Standard ADM (Architecture Vision, Requirements Management); any enterprise principles or reference architectures the artifact cites.

| ID | Criterion | Failure signs |
|---|---|---|
| ALN-1 | Business goals and drivers are stated and traceable to architectural decisions | Goals listed but no decision references them; architecture could serve any goal |
| ALN-2 | Requirements are complete and quantified, including NFRs | "Highly available", "scalable", "fast" with no numbers; no RTO/RPO; no load profile |
| ALN-3 | Stakeholders and their concerns are identified and each concern is addressed by a view or decision | No stakeholder list; operations, security, or finance concerns are silent |
| ALN-4 | Alignment with enterprise principles, standards, target state, and approved technology | Introduces a new datastore, language, or vendor without justification against the standard stack |
| ALN-5 | Scope, constraints, and assumptions are explicit | Boundaries unclear; assumptions buried in prose or missing |
| ALN-6 | Build/buy/reuse is justified; existing capabilities are reused where fit | Rebuilds a capability the enterprise already runs (identity, messaging, observability) |
| ALN-7 | Success is measurable: KPIs or acceptance criteria tied to the goals | No way to tell whether the architecture achieved its purpose |

---

## 2. AWS Well-Architected (`WA`)

Run the full question-level review in `well-architected.md`, with the questions in one file per pillar (`wa-operational-excellence.md`, `wa-security.md`, `wa-reliability.md`, `wa-performance-efficiency.md`, `wa-cost-optimization.md`, `wa-sustainability.md`). It covers all 57 questions and 307 best practices across the six pillars (`OPS`, `SEC`, `REL`, `PERF`, `COST`, `SUS`), plus any official lens that matches the workload. Each best practice is rated Met, Not met, or N/A, and each question High risk, Medium risk, or No risk. Pillar scores are calculated from those ratings.

Security is judged in depth there, under the Security pillar (SEC 1–11, in `wa-security.md`), with no separate security dimension. It counts twice in the dimension score.

Standard: AWS Well-Architected Framework (November 6, 2024 release). For non-AWS targets, judge the pillar principles and best-practice intent, and map them to the platform's equivalents.

---

## 3. Architecture Quality (`QAL`)

Is it a well-built design: coherent, appropriately simple, evolvable, and documented well enough to build and run?

Standards: ISO/IEC 25010:2023 product quality model; C4 model or arc42 for documentation; established pattern literature (Hohpe & Woolf for integration, Richardson for microservices, GoF and POSA for design).

| ID | Criterion | Failure signs |
|---|---|---|
| QAL-1 | Quality attributes are prioritized, and trade-offs between them are explicit | Every attribute is "high"; no statement of what was sacrificed for what |
| QAL-2 | Decomposition: clear responsibilities, high cohesion, low coupling, boundaries aligned to the domain | Distributed monolith (services that must deploy together); shared database across services; anemic "manager" services |
| QAL-3 | Patterns fit their forces, and their consequences are handled | Microservices for a small team and simple domain; event sourcing without a replay or versioning plan; CQRS with no account of staleness |
| QAL-4 | Integration style fits: sync vs async, contracts, versioning, backpressure | Long synchronous chains; no API versioning; no dead-letter or poison-message handling |
| QAL-5 | Simplicity: complexity is proportional to the requirements | Speculative generality; technology chosen for novelty; more moving parts than the NFRs need |
| QAL-6 | Evolvability: changes are localized, there are extension points, and lock-in is a conscious decision | Proprietary coupling with no exit; changes ripple across many components |
| QAL-7 | Failure modes are analyzed: what happens when each dependency is slow, down, or wrong | Only the happy path is described |
| QAL-8 | Documentation is clear, consistent, and complete enough to build from: views agree with each other and with the text | Diagrams contradict the prose; boxes and lines with no legend; components appear in one view only |

---

## 4. Data Management (`DAT`)

Is the data owned, modeled, protected, consistent, and governed across its whole lifecycle?

Standards: DAMA-DMBOK (data governance, architecture, quality, metadata, security, lifecycle); the regulation-specific data obligations in §7.

| ID | Criterion | Failure signs |
|---|---|---|
| DAT-1 | Data is classified (public, internal, confidential, restricted, or the enterprise scheme), and the classification drives controls | No classification; PII mixed into general-purpose stores |
| DAT-2 | Ownership: each data entity has one system of record and an accountable owner | Two services write the same entity; no source of truth |
| DAT-3 | Storage choices fit the access patterns, volume, and consistency needs | Relational defaulted for key-value access, or NoSQL chosen while joins are required |
| DAT-4 | Consistency model is explicit; distributed transactions are handled (saga, transactional outbox, idempotent consumers) | Dual writes to a database and a queue; "eventual consistency" with no conflict or reconciliation strategy |
| DAT-5 | Lifecycle: retention, archival, deletion, and legal hold are defined per data class | Keep-forever by default; no deletion path for erasure requests |
| DAT-6 | Schema and contract evolution: versioning, backward compatibility, migration approach | Breaking schema changes with no migration or compatibility plan |
| DAT-7 | Data quality and lineage: validation at ingestion, lineage for derived and analytical data | No validation; analytics built on unreconciled copies |
| DAT-8 | Backup, recovery, and integrity: RPO met by the backup design; restores tested; corruption detectable | Backups without restore tests; RPO stated but the design can't meet it |
| DAT-9 | Residency and sovereignty: the location of data, replicas, backups, and logs is known and permitted | Cross-region replication of regulated data with no residency analysis |
| DAT-10 | Migration (where applicable): approach, validation, cutover, rollback, dual-run period | Big-bang migration with no reconciliation or rollback |

---

## 5. Architecture Governance (`GOV`)

Is the design controlled: decisions recorded, deviations sanctioned, ownership clear, and conformance verifiable over time?

Standards: TOGAF Standard (Architecture Governance, Architecture Compliance review); ADR practice (Nygard format or MADR); ISO/IEC 38500 for IT governance principles.

| ID | Criterion | Failure signs |
|---|---|---|
| GOV-1 | Significant decisions are recorded with context, alternatives, rationale, and consequences | Decisions stated as facts with no alternatives; "we chose X" with no reason |
| GOV-2 | Deviations from enterprise standards are identified and go through a waiver/exception process with expiry | Non-standard technology used silently |
| GOV-3 | Ownership and decision rights: accountable owners for the architecture, components, and data (RACI or equivalent) | "The team" owns everything; no escalation path |
| GOV-4 | Risks, assumptions, issues, and dependencies are logged with owners and mitigations | No risk register; risks without mitigations or owners |
| GOV-5 | Conformance is verifiable: fitness functions, policy-as-code, automated guardrails, or review checkpoints | Conformance depends entirely on people remembering the document |
| GOV-6 | Artifact control: versioned, dated, status-marked (draft or baselined), with a change history | Undated; unclear which version is authoritative |
| GOV-7 | Roadmap and transition: transition architectures, sequencing, and decommissioning of what is replaced | Target state only; no path from current state; legacy left running indefinitely |
| GOV-8 | Technical debt is acknowledged and tracked, with a plan to pay it down | Shortcuts taken "for now" with no record |

---

## 6. Compliance (`CMP`)

Does the design meet the regulatory, contractual, and policy obligations that apply to it, and can it prove it?

First, determine applicability from the system profile. Record which regimes apply and why: industry, data classes, geography, and customer contracts. Common regimes:

| Regime | Applies when the artifact shows | Architecture-relevant obligations |
|---|---|---|
| GDPR / UK GDPR | Personal data of people in the EU or UK | Lawful basis, data protection by design (Art. 25), DPIA for high-risk processing (Art. 35), data-subject rights including erasure (Art. 17), restrictions on international transfers (Chapter V), breach notification within 72 hours (Art. 33) |
| CCPA / CPRA | Personal information of California residents, where the business meets the thresholds | Access, deletion, correction, and opt-out of sale or sharing |
| PCI DSS v4.0.1 | Storing, processing, or transmitting cardholder data | CDE scoping and segmentation, PAN protection, strong cryptography, access control, logging, vulnerability management |
| HIPAA | Protected health information, by covered entities or business associates | Security Rule administrative, physical, and technical safeguards; BAAs with processors including the cloud provider |
| SOC 2 | Service organization attesting to customers | Controls against the Trust Services Criteria: Security, Availability, Processing Integrity, Confidentiality, Privacy |
| ISO/IEC 27001:2022 | An ISMS certification in scope | Annex A controls and the Statement of Applicability |
| FedRAMP / FISMA | US federal data or systems | NIST SP 800-53 baseline at the authorized impact level; authorized services and regions |
| DORA | EU financial entities (applies from 17 January 2025) | ICT risk management, resilience testing, incident reporting, third-party risk |
| NIS2 | Essential or important entities in the EU | Risk management measures, incident reporting, supply-chain security |
| SOX | Financial reporting systems of US public companies | Change management, access control, and audit trail on in-scope systems |

Verify specifics against the regulation text when a score depends on them. Do not present the review as legal advice.

| ID | Criterion | Failure signs |
|---|---|---|
| CMP-1 | Applicable regimes and internal policies are identified, with the reasoning | Regulated data in the profile but no regime named. This is Critical. |
| CMP-2 | Obligations are mapped to architectural controls (a control matrix or traceability) | "We are compliant" with no mapping |
| CMP-3 | Scope is minimized: regulated data is isolated, tokenized, or kept out where possible, reducing the audit boundary | Cardholder or health data flows through general-purpose components |
| CMP-4 | Privacy by design: data minimization, purpose limitation, consent, and support for data-subject rights in the design | No erasure or export path; personal data copied into logs and analytics |
| CMP-5 | Evidence and auditability: immutable audit trails, retention matched to the obligation, evidence that can be collected automatically | Audit logs mutable or short-lived; evidence gathered by screenshot |
| CMP-6 | Residency and transfer: regions, replicas, support access, and sub-processors comply with residency and transfer rules | Global services or support access patterns not analyzed |
| CMP-7 | Third-party and shared responsibility: the provider's shared-responsibility split is understood; eligible services are used for regulated workloads (for example HIPAA-eligible services, FedRAMP-authorized services) | A service used for PHI or federal data without confirming its eligibility |

Severity guidance: processing regulated data without the controls the regime requires, or without being able to demonstrate them, is **Critical**.
