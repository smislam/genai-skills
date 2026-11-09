# Supply chain, MCP configs, and changes over time

Contents: what a skill pulls in · manifests and lockfiles · package-source redirection · install-time code · look-alike and abandoned packages · known vulnerabilities (opt-in) · container and CI pinning · MCP configs · changes since an earlier audit · what the script does not do

## What a skill pulls in

A skill is a small package, and anything it installs, downloads, or launches is part of it. Review three layers:

1. **What it ships:** scripts, binaries, archives (`artifacts.md`).
2. **What it installs:** dependencies named in manifests, lockfiles, and install commands.
3. **What it launches:** MCP servers, containers, CI actions, other tools.

## Manifests and lockfiles

The script reads, without running anything: `package.json`, `package-lock.json`, `npm-shrinkwrap.json`, `yarn.lock`, `requirements*.txt`, `constraints.txt`, `pyproject.toml`, `Pipfile`, `setup.py`, `Cargo.lock`, `Gemfile`, `go.mod`, `.gitmodules`, `Dockerfile`, Compose files, and GitHub workflow files.

| Finding | Means |
|---|---|
| SUP01 | A dependency or install command with no exact version (`*`, `latest`, open range, no pin) |
| SUP12 | A dependency from a Git URL, a tarball, a local path, or plain HTTP. A Git submodule is code the review did not cover. |
| SUP13 | A lockfile entry that resolves over HTTP, from a host other than the standard registry, or without an integrity hash |
| SUP14 | A base image or CI action pinned to a moving name (`latest`, `main`) |

Judge by the skill's purpose: a Node-based skill has dependencies; a skill with no code that carries a `package.json` is odd.

## Package-source redirection (SUP10)

Changing where packages come from is a trust change, however friendly the new source looks. The script flags it in config files (`.npmrc`, `.yarnrc`, `pip.conf`, `.pypirc`, `settings.xml`, `.cargo/config`, `nuget.config`), in commands (`npm config set registry`, `--index-url`, `--extra-index-url`, `--trusted-host`, `poetry source add`), in environment variables (`PIP_INDEX_URL`, `GOPROXY`), and in manifests (`overrides`, `resolutions`, a custom index). It reports the setting without judging the host. An internal mirror may be right for the user's company and wrong for everyone else; say which.

A shipped config that contains a token or password is CRD01 (high); credentials in URLs are redacted in the report.

## Install-time code (SUP11)

Anything that runs when a package is installed or built runs before anyone reads it: `preinstall`, `install`, `postinstall`, `prepare` scripts; a `setup.py` that spawns processes or opens sockets; an in-tree build backend. Treat these as scripts the skill runs automatically. Read what they do.

## Look-alike and abandoned packages

SUP06 compares package names with popular ones using edit distance (one or two characters apart) and a list of names reported as malicious look-alikes. It is a lead only; check the exact name on the registry, its age, its owner, and its download count. SUP05 flags packages that are deprecated or unmaintained.

## Known vulnerabilities (opt-in)

`--osv` looks up every dependency pinned to an exact version on OSV.dev, and cross-checks the results against CISA's Known Exploited Vulnerabilities catalog. A match is SUP04: high if the vulnerability is exploited in the wild or rated high or critical, otherwise medium. The finding gives the identifier, a summary, and the fixed version when one exists.

Needs `curl`. It follows `HTTPS_PROXY`; set `SKILL_AUDITOR_PROXY`, `SKILL_AUDITOR_PROXY_AUTH=negotiate` (Windows login), or `SKILL_AUDITOR_CA_BUNDLE` (corporate root certificate) when needed. If the lookup fails, the report says so and why. A skipped lookup is not a clean result.

Only package names, versions, and ecosystem names leave the machine; no file content does. Tell the user that before running it, since it is a network call they did not ask for by name.

## Container and CI pinning

A base image or action named by `latest`, a branch, or no tag changes under you. Pin to a version or, better, a digest (SUP14). Image trust bypasses such as `--disable-content-trust` and `--insecure-registry` are SUP07.

## MCP configs

An MCP config (`.mcp.json`, `mcp.json`, or `mcpServers` in a plugin manifest) starts programs and connects to services on the user's behalf.

| Finding | Means |
|---|---|
| MCP01 | A server launched through `npx`, `uvx`, `docker run`, and similar with no pinned version or digest, so the code it runs can change |
| MCP02 | A server URL over plain HTTP, or an IP address |
| MCP03 | A token or key written into the config (high); environment-variable references are fine |
| MCP04 | A server started through `sh -c` or a shell command string |
| TPO01 / TPO03 | Hidden instructions or very long text in a tool or parameter description. Tool descriptions are read by the model like instructions. |

A tool whose description does not match what its server does is SEM04 (`semantic.md`).

## Shipped settings and hooks

Settings files bundled in a skill (`.claude/settings.json` and similar) are HKS13 or HKS14 when they widen permissions, change the permission mode, auto-approve MCP servers, run helper commands, or set `ANTHROPIC_BASE_URL`, a proxy, or trust roots. Redirecting the API endpoint sends every prompt to someone else. Treat it as high.

## Changes since an earlier audit

A skill can be safe on Monday and not on Friday. After auditing, keep the JSON report. The next time, run:

```
python3 -I scripts/lint.py <skill> --compare <earlier-report.json>
```

The script compares file hashes and reports what changed: permissions added (DIF01), hooks added or changed (DIF02), scripts added or changed (DIF03), description or trigger changed (DIF04), new network hosts (DIF05), new binaries or archives (DIF06). Review the changes first, then the whole skill. A change that widens what the skill can do, with no matching change in its description, is the pattern to look for.

If you were given a skill that is "the same as before", this is how you check.

## What the script does not do

- It does not download dependencies, open their tarballs, or run an install. Dependency contents are not reviewed. Say so.
- It does not follow URLs. Remote content a script fetches is outside the review.
- It does not judge whether a registry or host is trustworthy. It makes the trust change visible.
