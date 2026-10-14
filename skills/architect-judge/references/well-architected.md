# AWS Well-Architected review

How to run the full question-level review across all six pillars. The questions, best practices (BPs), and the risk AWS documents for not establishing each BP are in one file per pillar (see "Pillar files" below). This is the AWS Well-Architected (`WA`) dimension. It is the only place security is scored.

**Source.** AWS Well-Architected Framework, publication date **November 6, 2024**, the latest framework release as of the verification date. Question and BP titles and risk levels were read from each page under `https://docs.aws.amazon.com/wellarchitected/latest/framework/` on 2026-10-14. AWS edits these pages between releases. If you have tools and a rating turns on a BP's exact wording or risk level, re-read that BP's page, and cite the framework date in the report.

**Size.** 57 questions and 307 best practices:

| Pillar | Questions | BPs | High | Medium | Low |
|---|---|---|---|---|---|
| Operational Excellence | 11 | 68 | 30 | 31 | 7 |
| Security | 11 | 63 | 30 | 28 | 5 |
| Reliability | 13 | 65 | 33 | 31 | 1 |
| Performance Efficiency | 5 | 32 | 13 | 15 | 4 |
| Cost Optimization | 11 | 50 | 21 | 17 | 12 |
| Sustainability | 6 | 29 | 0 | 21 | 8 |

## How to run it

### 1. Confirm the review depth

**The default is a full review: every question in every pillar.** Don't skip questions on your own judgment.

Seven questions are about the operating organization rather than the design: OPS 1, 2, 3, 9, and 11, COST 1, and SUS 6, each marked *(operating model)* in the pillar files. If the artifact doesn't cover the operating model, ask the requester once, before rating, whether they want a **design-stage review** instead:

> "This artifact doesn't describe the operating model (ownership, culture, operations reviews, cloud financial management). A full review rates those 7 questions, and they will mostly come out High risk. A design-stage review marks them N/A (out of scope: operating model) and lists them as Not assessed. Which do you want? If you don't say, it stays a full review."

Asking about review depth is a scope question, not a request for context about the design, so it doesn't break the blind-review rules in SKILL.md. If the requester doesn't answer, or you can't ask (for example in a non-interactive run), do the full review. In a design-stage review, list the 7 questions in the report as *Not assessed* so nobody reads them as passed. State the depth in the initial assessment.

### 2. Rate every best practice

For each BP, record one status, with the artifact location as evidence:

| Status | Meaning |
|---|---|
| **Met** | The artifact shows it is designed in or in place: a section, diagram, configuration, or test result. |
| **Not met** | The artifact contradicts it, or doesn't address it. Rule 2 of SKILL.md applies: *not evidenced is not met*. |
| **N/A** | It doesn't apply to this workload, with one of the AWS reasons: out of scope, business priorities, architecture constraints, or other. Each needs a one-line justification. "We didn't get to it" is not a reason. |

"Will be" statements count as Met only when the artifact specifies *what* and *how*. "Will be monitored" is Not met; "CloudWatch alarms on p99 latency > 300 ms paging the on-call [§6.2]" is Met.

### 3. Rate every question

AWS documents a risk level for each BP but does not publish the algorithm its tool uses to turn BP selections into a question risk. This skill uses the following rule. It is consistent with AWS's definitions: a High-risk BP is "a foundational, must-do practice within a pillar" and a Medium-risk BP is "an enabling practice that can substantially improve a workload". Present it as the skill's rule, not as AWS's.

| Question risk | Rule |
|---|---|
| **High risk** | Any High-risk BP is Not met. |
| **Medium risk** | No High-risk BP is Not met, but any Medium-risk BP is. |
| **No risk** | Only Low-risk BPs, or none, are Not met. |
| **N/A** | The whole question doesn't apply, with a reason. |

### 4. Score each question and pillar

Question score (0–5):
1. Weight each in-scope BP: High = 3, Medium = 2, Low = 1. Ignore BPs marked N/A.
2. Raw score = 5 × (weight of Met BPs ÷ weight of all in-scope BPs).
3. Cap the result by the question risk: a High-risk question scores at most **2.0**, and a Medium-risk question at most **3.5**.

Pillar score = the mean of its in-scope question scores, to one decimal.

WA dimension score = (2 × Security + Operational Excellence + Reliability + Performance Efficiency + Cost Optimization + Sustainability) ÷ 7, over the in-scope pillars. Security counts twice because this is the only place it is scored.

### 5. Turn risks into findings

- **One finding per question at risk, not one per BP.** The finding lists the Not met BPs by ID. This keeps the report readable when dozens of BPs are missing.
- **A High-risk question becomes a High finding.** Escalate it to **Critical** when it meets the Critical definition in `scoring.md`. Typical cases: restricted data unencrypted or reachable without authorization (SEC 3, SEC 8, SEC 9); no backup for a system of record (REL 9); no rollback path for an irreversible change (OPS 6); credentials exposed on the deployment path (SEC 2, SEC 11).
- **A Medium-risk question becomes a Medium finding.** Raise it to High only with a stated reason tied to this workload.
- **Unmet Low-risk BPs** go into the improvement list.
- **Remediations name the BP's intent and the concrete change.** "Implement SEC08-BP02" is not a remediation. "Enable default SSE-KMS with a customer-managed key on the `claims-raw` bucket and deny unencrypted `PutObject` in the bucket policy (SEC08-BP02)" is.

### 6. Apply lenses

When the system profile matches an official lens, apply that lens's questions alongside the framework. Score each lens question under the pillar it belongs to, using the same rules. Lenses in the AWS Well-Architected Tool lens catalog, as of the verification date:

| Lens | Apply when the workload is |
|---|---|
| Serverless Applications | Built mainly on Lambda, API Gateway, Step Functions, EventBridge, or similar |
| SaaS | Multi-tenant software sold as a service |
| Container Build | Containerized, covering image design and build |
| Data Analytics | A data lake, warehouse, streaming, or batch analytics workload |
| Machine Learning | Training, hosting, or operating ML models |
| Generative AI | Built on foundation models |
| IoT | Device fleets, edge, or telemetry ingestion |
| Financial Services Industry | In a regulated financial institution |
| Healthcare Industry | Handling healthcare workloads |
| Government | Delivering government services |
| Connected Mobility | Vehicle or transportation connectivity |
| SAP | Running SAP on AWS |
| Migration | Being moved to AWS |
| Mergers and Acquisitions | Integrating workloads during an M&A |
| DevOps | (DevOps Guidance) Delivery pipeline and practice |

AWS publishes more lenses outside the tool catalog, among them Agentic AI, Responsible AI, Games, Life Sciences, Telco, Streaming Media, HPC, Hybrid Networking, Microsoft Workloads, and Digital Sovereignty. The index is at `https://docs.aws.amazon.com/wellarchitected/`.

**Do not apply a lens from memory.** If you have tools, fetch the lens's questions and BPs from its AWS documentation page before applying it. If you can't, say "Lens identified but not applied: question set not available in this session" in the initial assessment.

## Pillar files

| Pillar | File |
|---|---|
| Operational Excellence | `wa-operational-excellence.md` |
| Security | `wa-security.md` |
| Reliability | `wa-reliability.md` |
| Performance Efficiency | `wa-performance-efficiency.md` |
| Cost Optimization | `wa-cost-optimization.md` |
| Sustainability | `wa-sustainability.md` |

A full review reads all six. When the review is split across subagents, give each one this file plus only its pillars' files.
