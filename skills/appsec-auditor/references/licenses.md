# License compliance

Dependency licenses are a legal and business risk, not a security vulnerability. They're reported in their own section of the report, are never counted with security findings, and don't go into the SARIF file. This is not legal advice: flag the risk, explain why it matters, and recommend a review by the organization's legal or open-source program office when a finding is High.

## Collecting license data

Use data the audit already has, and nothing that needs installing.

| Source | Where |
|---|---|
| Lockfiles | `package-lock.json` (lockfile v2 and later) records a `license` for each entry in `packages`. Most other lockfiles (`poetry.lock`, `uv.lock`, `Cargo.lock`, `packages.lock.json`) don't |
| Installed packages | Vendored or installed packages carry their license: `node_modules/<pkg>/package.json` `license`, Python `*.dist-info/METADATA` `License-Expression`, `vendor/` `LICENSE` files |
| Registry metadata | For direct dependencies without local data, the registry's public metadata: `https://registry.npmjs.org/<pkg>/<version>` (`license`), `https://pypi.org/pypi/<pkg>/<version>/json` (`info.license_expression` or `info.license`), `https://crates.io/api/v1/crates/<crate>/<version>` (`version.license`), the Maven POM's `<licenses>`. Sends only package names |
| Policy | `deny.toml` license rules, or an allow-list file, if the project has one |
| An already-installed tool | Trivy's license scanner or an existing SBOM, if present |

At Standard depth, check direct dependencies at minimum. At Deep depth, check transitive ones where the data is available. Say in the report which you covered.

Use SPDX identifiers (`MIT`, `Apache-2.0`, `GPL-3.0-only`) in the report. When sources disagree, report the most restrictive one and say so.

## Risk categories

| Category | Examples | Why it matters | Default risk |
|---|---|---|---|
| **Network copyleft** | AGPL-3.0, SSPL-1.0 | Obligations can apply when the software is offered over a network, including SaaS. SSPL isn't OSI-approved | **High** |
| **Strong copyleft** | GPL-2.0, GPL-3.0 | Distributing a combined work can require releasing its source under the same license | **High** if the software is distributed (installers, mobile apps, devices, on-premises products); **Medium** for internal or server-only use |
| **Source-available, not open source** | BUSL-1.1, Elastic License 2.0, Commons Clause, PolyForm | Restricts commercial or competing use; terms vary per project | **High** |
| **Weak copyleft** | LGPL-2.1, LGPL-3.0, MPL-2.0, EPL-2.0 | Obligations are usually limited to modifications of the library itself, and to how it's linked | **Medium** |
| **Unknown or missing license** | No license declared, `UNLICENSED`, `NOASSERTION`, a custom license text | No license means no granted right to use the code | **High** |
| **Permissive** | MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC | Attribution and notice requirements only | **Low**: report only when notices are missing from the distribution |

Adjust by context, and state the assumption you made:
- **Distribution model.** SaaS, internal tool, distributed binary, library published to a registry. Ask the user if it's unclear and it changes a rating; otherwise assume distributed and say so.
- **Dependency type.** Dev-only and build-only dependencies (test frameworks, linters) that never ship carry little license risk. Report them as Low at most.
- **Project policy.** If the repository has a policy (`deny.toml` license rules, an allow-list file, a `LICENSE-POLICY` document), apply it and report violations against it.
- **The project's own license.** A copyleft dependency in a project already released under a compatible copyleft license is usually not a conflict.

## Report section

```markdown
## License risk

| Risk | Package (version) | License | Used as | Why |
|---|---|---|---|---|
| High | example-lib (2.1.0) | AGPL-3.0 | runtime, direct | Network copyleft in a SaaS service; legal review recommended |
| Medium | other-lib (1.4.2) | LGPL-2.1 | runtime, transitive via foo | Weak copyleft; check linking and modification |

**Assumptions:** <distribution model assumed, policy applied or "no project policy found">
**Not legal advice.** High items should go to legal or open-source program review.
```
