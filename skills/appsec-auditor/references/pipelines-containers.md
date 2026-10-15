# Pipelines and containers: security review guide

Covers CI/CD definitions (GitHub Actions, GitLab CI, Jenkins, AWS CodeBuild), Dockerfiles, and Kubernetes manifests and Helm charts. Findings map to the OWASP Top 10 CI/CD Security Risks (`CICD-SEC-n`, listed in `standards.md`). Tool commands are in `tools.md`; triage rules in `triage.md`.

## What to read first

| File | Why it matters |
|---|---|
| `.github/workflows/*.yml`, `.github/actions/**/action.yml` | GitHub Actions triggers, permissions, secrets, third-party actions |
| `.gitlab-ci.yml`, included files (`include:`), `.gitlab/ci/**` | GitLab jobs, rules, variables, runners, included templates |
| `Jenkinsfile`, `jenkins/**`, shared library references (`@Library`) | Pipeline steps, credentials bindings, agents |
| `buildspec.yml`, `buildspec*.yml` | CodeBuild commands, env variables, `secrets-manager` and `parameter-store` usage |
| `Dockerfile*`, `*.dockerfile`, `docker-compose*.yml` | Base images, users, secrets in layers, exposed ports |
| `k8s/**`, `manifests/**`, `charts/**/templates/*.yaml`, `values*.yaml`, `kustomization.yaml` | Pod security, RBAC, network policies, secrets |
| `CODEOWNERS`, branch protection docs, `.github/dependabot.yml`, `renovate.json` | Flow control and dependency-update automation |

## Misconfigurations by area

### Pipelines: identity, triggers, and flow control

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| GitHub `on: pull_request_target` (or `workflow_run`) that checks out the PR head (`ref: ${{ github.event.pull_request.head.sha }}`) and runs its code or build | Use `pull_request` for untrusted code; if `pull_request_target` is required, never check out or execute PR code in it | CICD-SEC-4, CWE-94 |
| Script injection: `run: echo "${{ github.event.issue.title }}"`, or `${{ github.event.pull_request.title }}`, `.body`, `.head.ref`, `.head.label`, `${{ github.head_ref }}`, `${{ github.event.comment.body }}`, commit messages interpolated into `run:` or `script:` | Pass through `env:` and reference `"$VAR"` in the shell; never interpolate event fields into scripts | CICD-SEC-4, CWE-78 |
| No top-level `permissions:` (inherits the repo default, which may be write-all); `permissions: write-all` | `permissions: {}` or `contents: read` at the top, with per-job grants only as needed | CICD-SEC-5, CWE-269 |
| GitLab jobs with protected-variable access running for merge requests from forks; `rules:` that run deploy jobs on any branch | Protected variables only on protected branches and tags; deploy jobs restricted to protected refs; manual approval for production (`when: manual` plus protected environments) | CICD-SEC-1, CICD-SEC-5 |
| Self-hosted GitHub runners or shared GitLab runners used by public repos or forks; runners not ephemeral | Ephemeral, isolated runners; never self-hosted runners for public-repo PRs | CICD-SEC-7 |
| Long-lived cloud keys stored as CI secrets (`AWS_ACCESS_KEY_ID`) | OIDC federation (`id-token: write` with `aws-actions/configure-aws-credentials` role assumption; GitLab `id_tokens`); trust conditions pinned to repo and branch | CICD-SEC-6, SEC02-BP02 |
| Jenkins: `script { sh "... ${params.X}" }` with Groovy string interpolation of parameters or credentials; Script Security sandbox disabled; `withCredentials` values echoed | Single-quoted `sh '...'` with environment variables; sandbox on; masked credentials | CICD-SEC-4, CWE-78 |
| CodeBuild `buildspec.yml` with secrets in `env: variables:` (plaintext); privileged mode enabled on the project without need (a project setting, not a buildspec key: `privilegedMode: true` in CloudFormation, `privileged_mode = true` in the Terraform `aws_codebuild_project` `environment` block) | `env: secrets-manager:` / `parameter-store:`; privileged mode only for Docker builds that need it | CICD-SEC-6, CWE-798 |

### Pipelines: secrets and logging

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| Secrets printed (`echo $TOKEN`, `set -x` in steps with secrets, `env` or `printenv` dumps), or written to artifacts or caches | Never echo secrets; avoid `set -x` around them; exclude secret files from artifacts | CICD-SEC-6, CWE-532 |
| GitLab variables not marked masked or protected; secrets defined in `.gitlab-ci.yml` `variables:` | Masked and protected CI/CD variables, or an external secrets manager | CICD-SEC-6 |
| No audit trail of deployments or pipeline changes | Pipeline changes behind code review (`CODEOWNERS` on workflow files); deployment logs retained | CICD-SEC-10, CICD-SEC-1 |

### Pipelines: supply chain and pinning

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| Third-party actions by tag or branch (`uses: org/action@v3`, `@main`) | Pin to a full commit SHA, with the tag in a comment. Tags are mutable: in March 2026, 76 of 77 `aquasecurity/trivy-action` tags were hijacked to point at malicious code (GHSA-69fq-xp46-6x23) | CICD-SEC-3, CICD-SEC-8, CWE-829 |
| GitLab `include: remote:` or `project:` without a pinned `ref`; container `image:` by tag only | Pin `ref` to a SHA or protected tag; images by digest (`image@sha256:...`) | CICD-SEC-3, CICD-SEC-9 |
| `curl ... \| sh` / `bash <(curl ...)` installers in pipeline steps | Download, verify the checksum or signature, then run | CICD-SEC-3, CWE-494 |
| Artifacts deployed without signing or provenance; no check between build and deploy | Sign artifacts and images (for example Sigstore cosign) and verify at deploy; build provenance (SLSA) | CICD-SEC-9, CWE-345 |
| Dependency installs that ignore lockfiles (`npm install` instead of `npm ci`, `pip install` without hashes) | Lockfile-respecting installs (`npm ci`, `pip install --require-hashes`) | CICD-SEC-3 |

### Dockerfiles

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `FROM image:latest` or tag-only base images | Pin by digest (`FROM image@sha256:...`), with the tag in a comment | CWE-829, CICD-SEC-9 |
| No `USER` instruction (runs as root), or `USER root` at the end | A non-root `USER` with a fixed UID | CWE-250 |
| Secrets in `ENV`, `ARG`, or `COPY` of `.env` or keys; secrets removed in a later layer (they stay in history) | BuildKit secret mounts (`RUN --mount=type=secret,...`); never bake secrets into layers | CWE-798, CWE-538 |
| `ADD` with remote URLs; `curl \| sh` in `RUN` | `COPY` for local files; download, verify the checksum, then run | CWE-494 |
| Full OS images with build tools and shells in the runtime stage | Multi-stage builds; minimal or distroless runtime images | CWE-1104 |
| No `.dockerignore` (copies `.git`, `.env`, and credentials into the build context) | A `.dockerignore` excluding VCS data, env files, and keys | CWE-538 |

### Kubernetes manifests and Helm

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `securityContext.privileged: true`; `allowPrivilegeEscalation` not `false`; `runAsNonRoot` not `true`; added capabilities (`SYS_ADMIN`, `NET_ADMIN`) | `privileged: false`, `allowPrivilegeEscalation: false`, `runAsNonRoot: true`, `capabilities: drop: ["ALL"]`, `readOnlyRootFilesystem: true`, `seccompProfile: RuntimeDefault`; enforce Pod Security Admission `restricted` on namespaces | CWE-250, CWE-269 |
| `hostPath` volumes (especially `/`, `/var/run/docker.sock`, `/proc`); `hostNetwork`, `hostPID`, `hostIPC: true` | Avoid host namespaces and hostPath; use PVCs | CWE-668 |
| No `resources.limits` / `requests` | CPU and memory requests and limits; a `LimitRange` per namespace | CWE-770 |
| `automountServiceAccountToken` not set to `false` for pods that don't call the API; default service account used | `automountServiceAccountToken: false`; dedicated service accounts | CWE-269 |
| RBAC: `ClusterRole` with `verbs: ["*"]`, `resources: ["*"]`, or `secrets` `get/list`; `cluster-admin` bindings for workloads | Namespaced `Role`s with minimal verbs and resources | CWE-269 |
| No `NetworkPolicy` (all pod-to-pod traffic allowed) | Default-deny policies plus explicit allows | CWE-923 |
| Secrets in plain manifests or `values.yaml` (`kind: Secret` with `data:` committed, or Helm values containing passwords) | External Secrets, Sealed Secrets, or the CSI secrets store; never commit secret values | CWE-798 |
| Images by tag (`:latest`) with `imagePullPolicy: Always`, or tags without digests | Image digests; admission policies that verify signatures | CWE-829 |
| `Service` of `type: LoadBalancer` or `NodePort` exposing internal services; Ingress without TLS | `ClusterIP` for internal services; TLS on Ingress | CWE-284, CWE-319 |

## Chains to look for

- **Poisoned pipeline execution → deploy credentials.** A `pull_request_target` workflow checks out PR code (CICD-SEC-4) and has access to secrets or `id-token: write` with a cloud role (CICD-SEC-6). An outside contributor runs code with production deploy rights.
- **Script injection in an issue- or comment-triggered workflow → token theft.** `${{ github.event.comment.body }}` lands in `run:`, `GITHUB_TOKEN` has write permissions, and branch protection is missing. The attacker pushes to the default branch.
- **Unpinned third-party action → secret exfiltration.** A tag-pinned action in a job that sees secrets. If the action's tags are hijacked, as happened with Trivy in 2026, every run leaks those secrets.
- **Privileged pod + application RCE → node and cluster compromise.** An RCE in the app (see the language guides) inside a pod with `privileged: true` or a `docker.sock` hostPath escapes to the node. A service account token with broad RBAC then takes over the cluster.
- **Secret baked into an image layer + a public or broadly readable registry.** Anyone who can pull the image extracts the credential from layer history.

## Execution risks

- **`docker build`** executes every `RUN` instruction and fetches base images and remote `ADD` URLs.
- **Running pipeline steps locally** (for example with `act` or `gitlab-runner exec`) executes their scripts.
- **`helm template`** renders charts and runs no hooks. `helm install` or `upgrade` contacts the cluster: never run those.
- **`kubectl apply`** changes the cluster: never run it.
- **Ask before building images or executing pipeline steps.** Reading the files and static scanning are always safe.
