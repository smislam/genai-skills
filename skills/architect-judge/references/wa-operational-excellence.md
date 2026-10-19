# Well-Architected: Operational Excellence (`OPS`)

Part of the question-level review in `well-architected.md`. Read that file first for the rating, scoring, and finding rules. Source: AWS Well-Architected Framework, November 6, 2024 release, verified 2026-10-14. Risk if a best practice is not established: **H** High, **M** Medium, **L** Low. *(operating model)* marks a question that is about the operating organization rather than the design.

## Contents
- [Organization](#organization)
  - OPS 1: How do you determine what your priorities are?
  - OPS 2: How do you structure your organization to support your business outcomes?
  - OPS 3: How does your organizational culture support your business outcomes?
- [Prepare](#prepare)
  - OPS 4: How do you implement observability in your workload?
  - OPS 5: How do you reduce defects, ease remediation, and improve flow into production?
  - OPS 6: How do you mitigate deployment risks?
  - OPS 7: How do you know that you are ready to support a workload?
- [Operate](#operate)
  - OPS 8: How do you utilize workload observability in your organization?
  - OPS 9: How do you understand the health of your operations?
  - OPS 10: How do you manage workload and operations events?
- [Evolve](#evolve)
  - OPS 11: How do you evolve operations?


Design principles: organize teams around business outcomes; implement observability for actionable insights; safely automate where possible; make frequent, small, reversible changes; refine operations procedures frequently; anticipate failure; learn from all operational events and metrics; use managed services.


### Organization

**OPS 1 — How do you determine what your priorities are?** *(operating model)*
Look for: customer, governance, and compliance requirements feeding the design priorities; explicit trade-offs.
- OPS01-BP01 Evaluate external customer needs — H
- OPS01-BP02 Evaluate internal customer needs — H
- OPS01-BP03 Evaluate governance requirements — H
- OPS01-BP04 Evaluate compliance requirements — H
- OPS01-BP05 Evaluate threat landscape — M
- OPS01-BP06 Evaluate tradeoffs while managing benefits and risks — M

**OPS 2 — How do you structure your organization to support your business outcomes?** *(operating model)*
Look for: named owners for every resource, process, and operational activity; a change and exception mechanism.
- OPS02-BP01 Resources have identified owners — H
- OPS02-BP02 Processes and procedures have identified owners — H
- OPS02-BP03 Operations activities have identified owners responsible for their performance — H
- OPS02-BP04 Mechanisms exist to manage responsibilities and ownership — H
- OPS02-BP05 Mechanisms exist to request additions, changes, and exceptions — M
- OPS02-BP06 Responsibilities between teams are predefined or negotiated — L

**OPS 3 — How does your organizational culture support your business outcomes?** *(operating model)*
- OPS03-BP01 Provide executive sponsorship — H
- OPS03-BP02 Team members are empowered to take action when outcomes are at risk — M
- OPS03-BP03 Escalation is encouraged — H
- OPS03-BP04 Communications are timely, clear, and actionable — H
- OPS03-BP05 Experimentation is encouraged — M
- OPS03-BP06 Team members are encouraged to maintain and grow their skill sets — M
- OPS03-BP07 Resource teams appropriately — M

### Prepare

**OPS 4 — How do you implement observability in your workload?**
Look for: KPIs tied to business outcomes; application, user-experience, and dependency telemetry; distributed tracing across service boundaries. "CloudWatch enabled" with no named signals is Not met.
- OPS04-BP01 Identify key performance indicators — H
- OPS04-BP02 Implement application telemetry — H
- OPS04-BP03 Implement user experience telemetry — H
- OPS04-BP04 Implement dependency telemetry — H
- OPS04-BP05 Implement distributed tracing — H

**OPS 5 — How do you reduce defects, ease remediation, and improve flow into production?**
Look for: everything in version control, including infrastructure as code; automated tests; a CI/CD pipeline; patching; separate environments.
- OPS05-BP01 Use version control — H
- OPS05-BP02 Test and validate changes — H
- OPS05-BP03 Use configuration management systems — M
- OPS05-BP04 Use build and deployment management systems — M
- OPS05-BP05 Perform patch management — M
- OPS05-BP06 Share design standards — M
- OPS05-BP07 Implement practices to improve code quality — M
- OPS05-BP08 Use multiple environments — M
- OPS05-BP09 Make frequent, small, reversible changes — L
- OPS05-BP10 Fully automate integration and deployment — L

**OPS 6 — How do you mitigate deployment risks?**
Look for: a rollback plan for every change type, including schema and data changes; a canary, blue/green, or rolling strategy; automated rollback on health signals.
- OPS06-BP01 Plan for unsuccessful changes — H
- OPS06-BP02 Test deployments — H
- OPS06-BP03 Employ safe deployment strategies — M
- OPS06-BP04 Automate testing and rollback — M

**OPS 7 — How do you know that you are ready to support a workload?**
Look for: an operational readiness review; runbooks and playbooks for the known failure modes; a support plan.
- OPS07-BP01 Ensure personnel capability — H
- OPS07-BP02 Ensure a consistent review of operational readiness — H
- OPS07-BP03 Use runbooks to perform procedures — M
- OPS07-BP04 Use playbooks to investigate issues — M
- OPS07-BP05 Make informed decisions to deploy systems and changes — L
- OPS07-BP06 Create support plans for production workloads — L

### Operate

**OPS 8 — How do you utilize workload observability in your organization?**
Look for: actionable alerts with thresholds and routing (not dashboards alone); metrics, logs, and traces analyzed.
- OPS08-BP01 Analyze workload metrics — M
- OPS08-BP02 Analyze workload logs — M
- OPS08-BP03 Analyze workload traces — M
- OPS08-BP04 Create actionable alerts — H
- OPS08-BP05 Create dashboards — M

**OPS 9 — How do you understand the health of your operations?** *(operating model)*
- OPS09-BP01 Measure operations goals and KPIs with metrics — M
- OPS09-BP02 Communicate status and trends to ensure visibility into operation — M
- OPS09-BP03 Review operations metrics and prioritize improvement — M

**OPS 10 — How do you manage workload and operations events?**
Look for: an incident and problem process; a response defined for every alert; business-impact priorities; escalation paths; customer communication.
- OPS10-BP01 Use a process for event, incident, and problem management — H
- OPS10-BP02 Have a process per alert — H
- OPS10-BP03 Prioritize operational events based on business impact — H
- OPS10-BP04 Define escalation paths — M
- OPS10-BP05 Define a customer communication plan for service-impacting events — M
- OPS10-BP06 Communicate status through dashboards — M
- OPS10-BP07 Automate responses to events — M

### Evolve

**OPS 11 — How do you evolve operations?** *(operating model)*
- OPS11-BP01 Have a process for continuous improvement — H
- OPS11-BP02 Perform post-incident analysis — H
- OPS11-BP03 Implement feedback loops — H
- OPS11-BP04 Perform knowledge management — H
- OPS11-BP05 Define drivers for improvement — M
- OPS11-BP06 Validate insights — M
- OPS11-BP07 Perform operations metrics reviews — M
- OPS11-BP08 Document and share lessons learned — L
- OPS11-BP09 Allocate time to make improvements — L
