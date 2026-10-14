# Well-Architected: Security (`SEC`)

Part of the question-level review in `well-architected.md`. Read that file first for the rating, scoring, and finding rules. Source: AWS Well-Architected Framework, November 6, 2024 release, verified 2026-10-14. Risk if a best practice is not established: **H** High, **M** Medium, **L** Low. *(operating model)* marks a question that is about the operating organization rather than the design.

Design principles: implement a strong identity foundation; maintain traceability; apply security at all layers; automate security best practices; protect data in transit and at rest; keep people away from data; prepare for security events.

Security is judged in depth here, with no separate security dimension. Each question carries the specific checks to make against the artifact. Supporting standards for those checks: NIST CSF 2.0; NIST SP 800-207 (zero trust); NIST SP 800-53 Rev. 5; OWASP ASVS, OWASP Top 10, and OWASP API Security Top 10 (2023); CIS Benchmarks; SLSA and SBOM practice for the supply chain.

### Security foundations

**SEC 1 — How do you securely operate your workload?**
Look for: workload and environment separation by account (for example AWS Organizations with SCPs); a secured root user; a security baseline deployed automatically to every account; a threat model (STRIDE or equivalent) that covers every trust boundary in the inventory, with mitigations mapped to threats.
Failure signs: production and non-production in one account; no preventive guardrails; no threat model, or threats listed without mitigations.
- SEC01-BP01 Separate workloads using accounts — H
- SEC01-BP02 Secure account root user and properties — H
- SEC01-BP03 Identify and validate control objectives — H
- SEC01-BP04 Stay up to date with security threats and recommendations — H
- SEC01-BP05 Reduce security management scope — M
- SEC01-BP06 Automate deployment of standard security controls — M
- SEC01-BP07 Identify threats and prioritize mitigations using a threat model — H
- SEC01-BP08 Evaluate and implement new security services and features regularly — L

### Identity and access management

**SEC 2 — How do you manage authentication for people and machines?**
Look for: a centralized IdP with MFA for people; workload identity (IAM roles) for services; temporary credentials only; a secrets manager with rotation; no secrets in code, images, task definitions, or environment files.
Failure signs: IAM users with long-lived access keys; shared service accounts; API keys as the only service authentication; credentials in config repositories.
- SEC02-BP01 Use strong sign-in mechanisms — H
- SEC02-BP02 Use temporary credentials — H
- SEC02-BP03 Store and use secrets securely — H
- SEC02-BP04 Rely on a centralized identity provider — H
- SEC02-BP05 Audit and rotate credentials periodically — H
- SEC02-BP06 Employ user groups and attributes — M

**SEC 3 — How do you manage permissions for people and machines?**
Look for: least-privilege policies scoped to resources; authorization enforced at every trust boundary, not only at the edge; object-level authorization (OWASP API1, BOLA); a tenant isolation model for multi-tenant systems (silo, pool, or bridge), enforced below the application layer where the risk demands it; permission guardrails; break-glass access.
Failure signs: wildcard actions or resources; trusting a caller-supplied tenant or user ID; tenant isolation enforced only by a `WHERE` clause.
- SEC03-BP01 Define access requirements — H
- SEC03-BP02 Grant least privilege access — H
- SEC03-BP03 Establish emergency access process — M
- SEC03-BP04 Reduce permissions continuously — M
- SEC03-BP05 Define permission guardrails for your organization — M
- SEC03-BP06 Manage access based on lifecycle — M
- SEC03-BP07 Analyze public and cross-account access — L
- SEC03-BP08 Share resources securely within your organization — M
- SEC03-BP09 Share resources securely with a third party — M

### Detection

**SEC 4 — How do you detect and investigate security events?**
Look for: service and application logging (CloudTrail, VPC Flow Logs, application audit logs) centralized in a separate log-archive account, immutable and retained; detective services (GuardDuty, Security Hub, Config, or equivalents) routed to a responder; automated remediation of non-compliant resources.
Failure signs: logs on local disk or in the workload account only; findings with no routing.
- SEC04-BP01 Configure service and application logging — H
- SEC04-BP02 Capture logs, findings, and metrics in standardized locations — M
- SEC04-BP03 Correlate and enrich security alerts — L
- SEC04-BP04 Initiate remediation for non-compliant resources — M

### Infrastructure protection

**SEC 5 — How do you protect your network resources?**
Look for: network layers (public, private, data) with traffic controlled between them; private connectivity to managed services (VPC endpoints); controlled egress; WAF and DDoS protection on public endpoints; network controls in code.
Failure signs: databases in public subnets; security groups open to `0.0.0.0/0` on non-public ports; unrestricted egress.
- SEC05-BP01 Create network layers — H
- SEC05-BP02 Control traffic flow within your network layers — H
- SEC05-BP03 Implement inspection-based protection — M
- SEC05-BP04 Automate network protection — M

**SEC 6 — How do you protect your compute resources?**
Look for: vulnerability scanning of hosts and images; hardened, minimal base images; no interactive access (SSM instead of SSH); image signing and provenance verified at deploy time.
Failure signs: SSH from the internet; mutable `latest` tags; no scanning.
- SEC06-BP01 Perform vulnerability management — H
- SEC06-BP02 Provision compute from hardened images — H
- SEC06-BP03 Reduce manual management and interactive access — M
- SEC06-BP04 Validate software integrity — M
- SEC06-BP05 Automate compute protection — M

### Data protection

**SEC 7 — How do you classify your data?**
Look for: a classification scheme applied to every data store in the inventory; controls that differ by class; a lifecycle per class.
Failure signs: no classification; restricted data mixed into general-purpose stores.
- SEC07-BP01 Understand your data classification scheme — H
- SEC07-BP02 Apply data protection controls based on data sensitivity — H
- SEC07-BP03 Automate identification and classification — M
- SEC07-BP04 Define scalable data lifecycle management — H

**SEC 8 — How do you protect your data at rest?**
Look for: encryption at rest enforced by policy, not by convention; key management stated (KMS, with customer-managed keys where the data class or a regulation requires them); key policies that separate key administration from data access; access control on stores.
Failure signs: "encrypted" with no key ownership stated; encryption optional per resource.
- SEC08-BP01 Implement secure key management — H
- SEC08-BP02 Enforce encryption at rest — H
- SEC08-BP03 Automate data at rest protection — M
- SEC08-BP04 Enforce access control — H

**SEC 9 — How do you protect your data in transit?**
Look for: TLS 1.2 or later on every hop that carries sensitive data, including internal hops; managed certificates with rotation; authenticated service-to-service traffic (mTLS or SigV4).
Failure signs: TLS terminated at the load balancer and sent in plaintext inside the VPC for restricted data.
- SEC09-BP01 Implement secure key and certificate management — H
- SEC09-BP02 Enforce encryption in transit — H
- SEC09-BP03 Authenticate network communications — L

### Incident response

**SEC 10 — How do you anticipate, respond to, and recover from incidents?**
Look for: named responders and external contacts; an incident plan and playbooks specific to this workload; forensic capability (log retention, snapshot isolation); pre-provisioned responder access; simulations.
Failure signs: no IR plan, or a generic enterprise plan with no workload-specific playbooks.
- SEC10-BP01 Identify key personnel and external resources — H
- SEC10-BP02 Develop incident management plans — H
- SEC10-BP03 Prepare forensic capabilities — M
- SEC10-BP04 Develop and test security incident response playbooks — M
- SEC10-BP05 Pre-provision access — M
- SEC10-BP06 Pre-deploy tools — M
- SEC10-BP07 Run simulations — M
- SEC10-BP08 Establish a framework for learning from incidents — M

### Application security

**SEC 11 — How do you incorporate and validate the security properties of applications throughout the design, development, and deployment lifecycle?**
Look for: input validation, output encoding, rate limiting, and schema validation on every API; SAST, DAST, and dependency scanning in the pipeline; a private package repository; an SBOM; penetration testing; programmatic deployment only; a pipeline protected from tampering, with least-privilege deploy roles.
Failure signs: public APIs with no throttling; no validation strategy; the pipeline holds admin credentials; manual production deployments.
- SEC11-BP01 Train for application security — M
- SEC11-BP02 Automate testing throughout the development and release lifecycle — M
- SEC11-BP03 Perform regular penetration testing — H
- SEC11-BP04 Conduct code reviews — M
- SEC11-BP05 Centralize services for packages and dependencies — M
- SEC11-BP06 Deploy software programmatically — H
- SEC11-BP07 Regularly assess security properties of the pipelines — H
- SEC11-BP08 Build a program that embeds security ownership in workload teams — L
