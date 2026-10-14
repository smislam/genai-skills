# Well-Architected: Cost Optimization (`COST`)

Part of the question-level review in `well-architected.md`. Read that file first for the rating, scoring, and finding rules. Source: AWS Well-Architected Framework, November 6, 2024 release, verified 2026-10-14. Risk if a best practice is not established: **H** High, **M** Medium, **L** Low. *(operating model)* marks a question that is about the operating organization rather than the design.

Design principles: implement Cloud Financial Management; adopt a consumption model; measure overall efficiency; stop spending money on undifferentiated heavy lifting; analyze and attribute expenditure.

### Practice Cloud Financial Management

**COST 1 — How do you implement cloud financial management?** *(operating model)*
- COST01-BP01 Establish ownership of cost optimization — H
- COST01-BP02 Establish a partnership between finance and technology — H
- COST01-BP03 Establish cloud budgets and forecasts — H
- COST01-BP04 Implement cost awareness in your organizational processes — H
- COST01-BP05 Report and notify on cost optimization — L
- COST01-BP06 Monitor cost proactively — M
- COST01-BP07 Keep up-to-date with new service releases — M
- COST01-BP08 Create a cost-aware culture — L
- COST01-BP09 Quantify business value from cost optimization — M

### Expenditure and usage awareness

**COST 2 — How do you govern usage?**
Look for: cost policies and targets; an account structure; cost controls such as budgets, SCPs, and quotas.
- COST02-BP01 Develop policies based on your organization requirements — H
- COST02-BP02 Implement goals and targets — H
- COST02-BP03 Implement an account structure — H
- COST02-BP04 Implement groups and roles — L
- COST02-BP05 Implement cost controls — M
- COST02-BP06 Track project lifecycle — L

**COST 3 — How do you monitor your cost and usage?**
Look for: a tagging and cost-allocation scheme (owner, environment, workload); cost KPIs such as cost per transaction; billing tools configured.
- COST03-BP01 Configure detailed information sources — H
- COST03-BP02 Add organization information to cost and usage — M
- COST03-BP03 Identify cost attribution categories — H
- COST03-BP04 Establish organization metrics — H
- COST03-BP05 Configure billing and cost management tools — H
- COST03-BP06 Allocate costs based on workload metrics — L

**COST 4 — How do you decommission resources?**
Look for: resource tracking over its lifetime; a decommissioning plan for what this design replaces; data retention enforced.
- COST04-BP01 Track resources over their lifetime — H
- COST04-BP02 Implement a decommissioning process — H
- COST04-BP03 Decommission resources — M
- COST04-BP04 Decommission resources automatically — L
- COST04-BP05 Enforce data retention policies — M

### Cost-effective resources

**COST 5 — How do you evaluate cost when you select services?**
Look for: cost requirements stated; every component analyzed for cost, including licensing; cost over time at the projected usage.
- COST05-BP01 Identify organization requirements for cost — H
- COST05-BP02 Analyze all components of the workload — H
- COST05-BP03 Perform a thorough analysis of each component — H
- COST05-BP04 Select software with cost-effective licensing — L
- COST05-BP05 Select components of this workload to optimize cost in line with organization priorities — M
- COST05-BP06 Perform cost analysis for different usage over time — M

**COST 6 — How do you meet cost targets when you select resource type, size and number?**
Look for: a cost model or estimate tied to the load profile; sizing based on data.
- COST06-BP01 Perform cost modeling — H
- COST06-BP02 Select resource type, size, and number based on data — M
- COST06-BP03 Select resource type, size, and number automatically based on metrics — L
- COST06-BP04 Consider using shared resources — M

**COST 7 — How do you use pricing models to reduce cost?**
Look for: pricing-model analysis (on-demand, Savings Plans, Reserved Instances, Spot; serverless versus provisioned); Region choice with its cost considered.
- COST07-BP01 Perform pricing model analysis — H
- COST07-BP02 Choose Regions based on cost — M
- COST07-BP03 Select third-party agreements with cost-efficient terms — M
- COST07-BP04 Implement pricing models for all components of this workload — L
- COST07-BP05 Perform pricing model analysis at the management account level — L

**COST 8 — How do you plan for data transfer charges?**
Look for: data transfer modeled across AZs, Regions, the internet, and NAT gateway processing; VPC endpoints and CDN used to reduce it.
- COST08-BP01 Perform data transfer modeling — H
- COST08-BP02 Select components to optimize data transfer cost — M
- COST08-BP03 Implement services to reduce data transfer costs — M

### Manage demand and supply resources

**COST 9 — How do you manage demand, and supply resources?**
Look for: demand analyzed; buffering or throttling; capacity supplied dynamically.
- COST09-BP01 Perform an analysis on the workload demand — H
- COST09-BP02 Implement a buffer or throttle to manage demand — M
- COST09-BP03 Supply resources dynamically — L

### Optimize over time

**COST 10 — How do you evaluate new services?**
- COST10-BP01 Develop a workload review process — H
- COST10-BP02 Review and analyze this workload regularly — M

**COST 11 — How do you evaluate the cost of effort?**
- COST11-BP01 Perform automation for operations — L
