# Well-Architected: Sustainability (`SUS`)

Part of the question-level review in `well-architected.md`. Read that file first for the rating, scoring, and finding rules. Source: AWS Well-Architected Framework, November 6, 2024 release, verified 2026-10-14. Risk if a best practice is not established: **H** High, **M** Medium, **L** Low. *(operating model)* marks a question that is about the operating organization rather than the design.

Design principles: understand your impact; establish sustainability goals; maximize utilization; anticipate and adopt new, more efficient hardware and software offerings; use managed services; reduce the downstream impact of your cloud workloads.

### Region selection

**SUS 1 — How do you select Regions for your workload?**
- SUS01-BP01 Choose Region based on both business requirements and sustainability goals — M

### Alignment to demand

**SUS 2 — How do you align cloud resources to your demand?**
Look for: scaling with demand, including to zero where viable; no idle always-on capacity without a reason; buffering to flatten peaks.
- SUS02-BP01 Scale workload infrastructure dynamically — M
- SUS02-BP02 Align SLAs with sustainability goals — L
- SUS02-BP03 Stop the creation and maintenance of unused assets — L
- SUS02-BP04 Optimize geographic placement of workloads based on their networking requirements — M
- SUS02-BP05 Optimize team member resources for activities performed — L
- SUS02-BP06 Implement buffering or throttling to flatten the demand curve — L

### Software and architecture

**SUS 3 — How do you take advantage of software and architecture patterns to support your sustainability goals?**
- SUS03-BP01 Optimize software and architecture for asynchronous and scheduled jobs — M
- SUS03-BP02 Remove or refactor workload components with low or no use — M
- SUS03-BP03 Optimize areas of code that consume the most time or resources — M
- SUS03-BP04 Optimize impact on devices and equipment — M
- SUS03-BP05 Use software patterns and architectures that best support data access and storage patterns — M

### Data

**SUS 4 — How do you take advantage of data management policies and patterns to support your sustainability goals?**
Look for: lifecycle policies that tier or delete data nobody reads; minimal data movement; backups only for data that is hard to recreate.
- SUS04-BP01 Implement a data classification policy — M
- SUS04-BP02 Use technologies that support data access and storage patterns — L
- SUS04-BP03 Use policies to manage the lifecycle of your datasets — M
- SUS04-BP04 Use elasticity and automation to expand block storage or file system — M
- SUS04-BP05 Remove unneeded or redundant data — M
- SUS04-BP06 Use shared file systems or storage to access common data — M
- SUS04-BP07 Minimize data movement across networks — M
- SUS04-BP08 Back up data only when difficult to recreate — M

### Hardware and services

**SUS 5 — How do you select and use cloud hardware and services in your architecture to support your sustainability goals?**
Look for: minimal hardware; efficient instance families (for example Graviton); managed services over self-run fleets.
- SUS05-BP01 Use the minimum amount of hardware to meet your needs — M
- SUS05-BP02 Use instance types with the least impact — M
- SUS05-BP03 Use managed services — M
- SUS05-BP04 Optimize your use of hardware-based compute accelerators — M

### Process and culture

**SUS 6 — How do your organizational processes support your sustainability goals?** *(operating model)*
- SUS06-BP01 Communicate and cascade your sustainability goals — M
- SUS06-BP02 Adopt methods that can rapidly introduce sustainability improvements — M
- SUS06-BP03 Keep your workload up-to-date — L
- SUS06-BP04 Increase utilization of build environments — L
- SUS06-BP05 Use managed device farms for testing — L
