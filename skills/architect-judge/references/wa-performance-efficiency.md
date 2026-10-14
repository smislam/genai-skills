# Well-Architected: Performance Efficiency (`PERF`)

Part of the question-level review in `well-architected.md`. Read that file first for the rating, scoring, and finding rules. Source: AWS Well-Architected Framework, November 6, 2024 release, verified 2026-10-14. Risk if a best practice is not established: **H** High, **M** Medium, **L** Low. *(operating model)* marks a question that is about the operating organization rather than the design.

Design principles: democratize advanced technologies; go global in minutes; use serverless architectures; experiment more often; consider mechanical sympathy.

### Architecture selection

**PERF 1 — How do you select appropriate cloud resources and architecture for your workload?**
Look for: choices justified against the access pattern and load profile, with trade-offs and cost stated; benchmarks or data behind key choices; use of reference architectures.
- PERF01-BP01 Learn about and understand available cloud services and features — H
- PERF01-BP02 Use guidance from your cloud provider or an appropriate partner to learn about architecture patterns and best practices — M
- PERF01-BP03 Factor cost into architectural decisions — M
- PERF01-BP04 Evaluate how trade-offs impact customers and architecture efficiency — H
- PERF01-BP05 Use policies and reference architectures — M
- PERF01-BP06 Use benchmarking to drive architectural decisions — M
- PERF01-BP07 Use a data-driven approach for architectural choices — M

### Compute and hardware

**PERF 2 — How do you select and use compute resources in your workload?**
Look for: the compute model justified (instances, containers, or functions); right-sizing; compute metrics collected; scaling on a defined signal with limits.
- PERF02-BP01 Select the best compute options for your workload — H
- PERF02-BP02 Understand the available compute configuration and features — M
- PERF02-BP03 Collect compute-related metrics — H
- PERF02-BP04 Configure and right-size compute resources — M
- PERF02-BP05 Scale your compute resources dynamically — H
- PERF02-BP06 Use optimized hardware-based compute accelerators — M

### Data management

**PERF 3 — How do you store, manage, and access data in your workload?**
Look for: a purpose-built data store per access pattern; data store metrics; query optimization (indexes, partitioning); caching where latency requires it.
- PERF03-BP01 Use a purpose-built data store that best supports your data access and storage requirements — H
- PERF03-BP02 Evaluate available configuration options for data store — M
- PERF03-BP03 Collect and record data store performance metrics — H
- PERF03-BP04 Implement strategies to improve query performance in data store — M
- PERF03-BP05 Implement data access patterns that utilize caching — M

### Networking and content delivery

**PERF 4 — How do you select and configure networking resources in your workload?**
Look for: the network's latency and bandwidth impact analyzed; load balancing; a CDN or edge where users are distributed; dedicated connectivity or VPN sized for hybrid traffic; workload placement near its users and data.
- PERF04-BP01 Understand how networking impacts performance — H
- PERF04-BP02 Evaluate available networking features — H
- PERF04-BP03 Choose appropriate dedicated connectivity or VPN for your workload — H
- PERF04-BP04 Use load balancing to distribute traffic across multiple resources — H
- PERF04-BP05 Choose network protocols to improve performance — M
- PERF04-BP06 Choose your workload's location based on network requirements — M
- PERF04-BP07 Optimize network configuration based on metrics — L

### Process and culture

**PERF 5 — How do your organizational practices and culture contribute to performance efficiency in your workload?**
Look for: performance KPIs tied to the NFRs (for example p99 latency or throughput); monitoring of those KPIs; load testing against the stated NFRs.
- PERF05-BP01 Establish key performance indicators (KPIs) to measure workload health and performance — H
- PERF05-BP02 Use monitoring solutions to understand the areas where performance is most critical — H
- PERF05-BP03 Define a process to improve workload performance — M
- PERF05-BP04 Load test your workload — L
- PERF05-BP05 Use automation to proactively remediate performance-related issues — L
- PERF05-BP06 Keep your workload and services up-to-date — L
- PERF05-BP07 Review metrics at regular intervals — M
