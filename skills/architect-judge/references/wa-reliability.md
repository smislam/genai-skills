# Well-Architected: Reliability (`REL`)

Part of the question-level review in `well-architected.md`. Read that file first for the rating, scoring, and finding rules. Source: AWS Well-Architected Framework, November 6, 2024 release, verified 2026-10-14. Risk if a best practice is not established: **H** High, **M** Medium, **L** Low. *(operating model)* marks a question that is about the operating organization rather than the design.

## Contents
- [Foundations](#foundations)
  - REL 1: How do you manage Service Quotas and constraints?
  - REL 2: How do you plan your network topology?
- [Workload architecture](#workload-architecture)
  - REL 3: How do you design your workload service architecture?
  - REL 4: How do you design interactions in a distributed system to prevent failures?
  - REL 5: How do you design interactions in a distributed system to mitigate or withstand failures?
- [Change management](#change-management)
  - REL 6: How do you monitor workload resources?
  - REL 7: How do you design your workload to adapt to changes in demand?
  - REL 8: How do you implement change?
- [Failure management](#failure-management)
  - REL 9: How do you back up data?
  - REL 10: How do you use fault isolation to protect your workload?
  - REL 11: How do you design your workload to withstand component failures?
  - REL 12: How do you test reliability?
  - REL 13: How do you plan for disaster recovery (DR)?


Design principles: automatically recover from failure; test recovery procedures; scale horizontally to increase aggregate workload availability; stop guessing capacity; manage change through automation.

### Foundations

**REL 1 — How do you manage Service Quotas and constraints?**
Look for: the relevant quotas identified (including fixed ones) and designed around; headroom for failover; quota monitoring.
- REL01-BP01 Aware of service quotas and constraints — H
- REL01-BP02 Manage service quotas across accounts and regions — H
- REL01-BP03 Accommodate fixed service quotas and constraints through architecture — M
- REL01-BP04 Monitor and manage quotas — M
- REL01-BP05 Automate quota management — M
- REL01-BP06 Ensure that a sufficient gap exists between the current quotas and the maximum usage to accommodate failover — M

**REL 2 — How do you plan your network topology?**
Look for: highly available public endpoints; redundant hybrid connectivity; IP space sized for growth across AZs; hub-and-spoke topology (Transit Gateway); no overlapping CIDRs.
- REL02-BP01 Use highly available network connectivity for your workload public endpoints — H
- REL02-BP02 Provision redundant connectivity between private networks in the cloud and on-premises environments — H
- REL02-BP03 Ensure IP subnet allocation accounts for expansion and availability — M
- REL02-BP04 Prefer hub-and-spoke topologies over many-to-many mesh — M
- REL02-BP05 Enforce non-overlapping private IP address ranges in all private address spaces where they are connected — M

### Workload architecture

**REL 3 — How do you design your workload service architecture?**
Look for: a justified segmentation (monolith, SOA, or microservices); services aligned to business domains; a contract per API.
- REL03-BP01 Choose how to segment your workload — H
- REL03-BP02 Build services focused on specific business domains and functionality — H
- REL03-BP03 Provide service contracts per API — M

**REL 4 — How do you design interactions in a distributed system to prevent failures?**
Look for: dependencies classified (hard or soft, sync or async); loose coupling through queues or events; idempotent mutating operations, with the idempotency key stable across retries.
Failure signs: long synchronous call chains; dual writes; retried writes that aren't idempotent.
- REL04-BP01 Identify the kind of distributed systems you depend on — H
- REL04-BP02 Implement loosely coupled dependencies — H
- REL04-BP03 Do constant work — L
- REL04-BP04 Make mutating operations idempotent — M

**REL 5 — How do you design interactions in a distributed system to mitigate or withstand failures?**
Look for: graceful degradation; throttling; retries that are bounded, with backoff and jitter, and not stacked across layers; client timeouts shorter than the caller's deadline; bounded queues; stateless services; emergency levers.
Failure signs: retries at every layer; no timeouts; unbounded queues; retries firing against an open circuit breaker.
- REL05-BP01 Implement graceful degradation to transform applicable hard dependencies into soft dependencies — H
- REL05-BP02 Throttle requests — H
- REL05-BP03 Control and limit retry calls — H
- REL05-BP04 Fail fast and limit queues — H
- REL05-BP05 Set client timeouts — H
- REL05-BP06 Make systems stateless where possible — M
- REL05-BP07 Implement emergency levers — M

### Change management

**REL 6 — How do you monitor workload resources?**
Look for: every component in the inventory emitting metrics; defined aggregate metrics; notifications on them; end-to-end tracing.
- REL06-BP01 Monitor all components for the workload (Generation) — H
- REL06-BP02 Define and calculate metrics (Aggregation) — H
- REL06-BP03 Send notifications (Real-time processing and alarming) — H
- REL06-BP04 Automate responses (Real-time processing and alarming) — M
- REL06-BP05 Analyze logs — M
- REL06-BP06 Regularly review monitoring scope and metrics — M
- REL06-BP07 Monitor end-to-end tracing of requests through your system — M

**REL 7 — How do you design your workload to adapt to changes in demand?**
Look for: automated scaling on a defined signal, with limits; load testing against the stated peak.
- REL07-BP01 Use automation when obtaining or scaling resources — H
- REL07-BP02 Obtain resources upon detection of impairment to a workload — M
- REL07-BP03 Obtain resources upon detection that more resources are needed for a workload — M
- REL07-BP04 Load test your workload — M

**REL 8 — How do you implement change?**
Look for: runbooks for deployment; functional and resiliency tests in the pipeline; immutable infrastructure; automated deployment.
- REL08-BP01 Use runbooks for standard activities such as deployment — H
- REL08-BP02 Integrate functional testing as part of your deployment — H
- REL08-BP03 Integrate resiliency testing as part of your deployment — M
- REL08-BP04 Deploy using immutable infrastructure — M
- REL08-BP05 Deploy changes with automation — M

### Failure management

**REL 9 — How do you back up data?**
Look for: every data store in the inventory either backed up or reproducible; backups encrypted and isolated (a separate account, vault lock); backups automated; restores tested periodically against the RPO.
Failure signs: backups that have never been restored; an RPO stated that the backup schedule can't meet.
- REL09-BP01 Identify and back up all data that needs to be backed up, or reproduce the data from sources — H
- REL09-BP02 Secure and encrypt backups — H
- REL09-BP03 Perform data backup automatically — M
- REL09-BP04 Perform periodic recovery of the data to verify backup integrity and processes — M

**REL 10 — How do you use fault isolation to protect your workload?**
Look for: multi-AZ at minimum for production, and multi-Region where the RTO/RPO demands it; automated recovery for any single-AZ component; bulkheads or cells to limit the blast radius.
Failure signs: a single-AZ database for a production system of record; shared fate across tenants or features.
- REL10-BP01 Deploy the workload to multiple locations — H
- REL10-BP02 Automate recovery for components constrained to a single location — M
- REL10-BP03 Use bulkhead architectures to limit scope of impact — H

**REL 11 — How do you design your workload to withstand component failures?**
Look for: health checks on every component; automated failover and healing; recovery that relies on the data plane, not the control plane; static stability (capacity pre-provisioned for the loss of an AZ); availability targets that the design can be shown to meet.
- REL11-BP01 Monitor all components of the workload to detect failures — H
- REL11-BP02 Fail over to healthy resources — H
- REL11-BP03 Automate healing on all layers — H
- REL11-BP04 Rely on the data plane and not the control plane during recovery — M
- REL11-BP05 Use static stability to prevent bimodal behavior — M
- REL11-BP06 Send notifications when events impact availability — M
- REL11-BP07 Architect your product to meet availability targets and uptime service level agreements (SLAs) — M

**REL 12 — How do you test reliability?**
Look for: playbooks for failure investigation; post-incident analysis; scalability and performance tests against the NFRs; chaos experiments and game days.
- REL12-BP01 Use playbooks to investigate failures — H
- REL12-BP02 Perform post-incident analysis — H
- REL12-BP03 Test scalability and performance requirements — H
- REL12-BP04 Test resiliency using chaos engineering — M
- REL12-BP05 Conduct game days regularly — M

**REL 13 — How do you plan for disaster recovery (DR)?**
Look for: RTO and RPO stated per workload; a DR strategy matched to them (backup and restore, pilot light, warm standby, or multi-site active-active); DR tested; configuration drift at the DR site controlled; automated recovery.
Failure signs: DR marked "TBD"; a strategy that can't meet the stated RTO (for example backup and restore against a 15-minute RTO); DR never tested.
- REL13-BP01 Define recovery objectives for downtime and data loss — H
- REL13-BP02 Use defined recovery strategies to meet the recovery objectives — H
- REL13-BP03 Test disaster recovery implementation to validate the implementation — H
- REL13-BP04 Manage configuration drift at the DR site or Region — H
- REL13-BP05 Automate recovery — M
