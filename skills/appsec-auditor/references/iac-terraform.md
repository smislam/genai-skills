# Terraform: security review guide

Covers Terraform and OpenTofu configurations, mainly with the AWS provider, plus the Terraform concerns that apply to any provider: state, variables, providers, and modules. Tool commands are in `tools.md`; triage rules in `triage.md`.

## What to read first

| File | Why it matters |
|---|---|
| `*.tf` (root module) | The resources actually deployed; start from `main.tf` and the provider blocks |
| `modules/**`, `module` blocks | Reused modules; `source` and `version` decide what code you inherit |
| `versions.tf`, `required_providers`, `.terraform.lock.hcl` | Provider and version pinning; the lock file records provider checksums |
| `backend` block, `*.tfbackend` | Where state lives, and whether it's encrypted and locked |
| `*.tfvars`, `*.auto.tfvars`, `terraform.tfvars.json` | Variable values; secrets are often committed here |
| `variables.tf`, `outputs.tf` | Whether `sensitive = true` is set on secrets; outputs can leak secrets into logs and state |
| `*.tfstate`, `*.tfstate.backup` (if committed) | Contain every attribute in plaintext, including secrets. Committing them is itself a finding |
| Policy files (`*.rego`, Sentinel, `.checkov.yaml`, `.tflint.hcl`) | Existing guardrails and suppressions |

## Misconfigurations by area

### Identity and IAM

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `aws_iam_policy` / `aws_iam_role_policy` / `data "aws_iam_policy_document"` with `actions = ["*"]` or `resources = ["*"]` on write actions | Least-privilege actions and specific ARNs; conditions (`aws:SourceArn`, `aws:PrincipalOrgID`) | CWE-269, SEC03-BP02 |
| `assume_role_policy` trusting `"AWS": "*"`, or any account without an `sts:ExternalId` condition for third parties | Specific principals; `ExternalId` for cross-account vendor roles | CWE-284, SEC03-BP09 |
| GitHub/GitLab OIDC role trust with a `sub` condition wildcarded to all repos or branches (`repo:org/*`) | Pin `sub` to the specific repo and branch or environment; check `aud` | CWE-284, CICD-SEC-2 |
| `aws_iam_user` with `aws_iam_access_key` | Roles with temporary credentials; IAM Identity Center for people | CWE-798, SEC02-BP02 |
| `iam:PassRole` on `*` | Scope `PassRole` to specific roles with an `iam:PassedToService` condition | CWE-269 |

### Network exposure

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `aws_security_group` / `aws_security_group_rule` with `cidr_blocks = ["0.0.0.0/0"]` (or `ipv6_cidr_blocks = ["::/0"]`), or `aws_vpc_security_group_ingress_rule` with `cidr_ipv4 = "0.0.0.0/0"` (or `cidr_ipv6 = "::/0"`), on ports other than 80/443 (22, 3389, database ports) | Specific CIDRs or security-group references; SSM Session Manager instead of SSH | CWE-284, SEC05-BP02 |
| `aws_db_instance` / `aws_rds_cluster_instance` with `publicly_accessible = true` | `false`; private subnets | SEC05-BP01 |
| `aws_s3_bucket_public_access_block` missing or with any `block_public_*` / `ignore_public_acls` / `restrict_public_buckets` set to `false`; bucket policy with `Principal: "*"` | All four set to `true`; account-level `aws_s3_account_public_access_block` | CWE-284, SEC03-BP07 |
| `aws_instance` with `associate_public_ip_address = true` in a tier meant to be private | Private subnets behind a load balancer | SEC05-BP01 |
| `aws_lb_listener` on HTTP without a redirect; ALB without WAF (`aws_wafv2_web_acl_association`) on public apps | HTTPS listeners with a TLS 1.2+ `ssl_policy`; HTTP → HTTPS redirect; WAF | CWE-319, SEC05-BP03 |
| `aws_instance` / `aws_launch_template` `metadata_options` without `http_tokens = "required"` (IMDSv1 allowed), or `http_put_response_hop_limit` > 1 for container hosts | `http_tokens = "required"`; hop limit 1 unless containers need 2 | CWE-918 (enabler), SEC06-BP05 |
| `aws_lambda_function_url` with `authorization_type = "NONE"` on non-public functions | `AWS_IAM`, or authentication in front | CWE-306 |

### Encryption at rest and in transit

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `aws_db_instance` / `aws_rds_cluster` with `storage_encrypted = false` or unset | `storage_encrypted = true`; `kms_key_id` for customer-managed keys where required | CWE-311, SEC08-BP02 |
| `aws_ebs_volume` with `encrypted` unset; no `aws_ebs_encryption_by_default` | `encrypted = true`; account default encryption | SEC08-BP02 |
| `aws_s3_bucket_server_side_encryption_configuration` missing where a CMK is required; no bucket policy denying non-TLS requests (`aws:SecureTransport = false`) | SSE-KMS with a CMK for restricted data; a TLS-only bucket policy | CWE-319, SEC09-BP02 |
| `aws_kms_key` with `enable_key_rotation = false`; key policy granting `kms:*` to `*` | Rotation on; key administrators separated from key users | SEC08-BP01 |
| `aws_elasticache_replication_group` without `transit_encryption_enabled` / `at_rest_encryption_enabled`; `aws_opensearch_domain` without `encrypt_at_rest` / `node_to_node_encryption` | Both enabled | SEC08-BP02, SEC09-BP02 |
| `aws_sns_topic` / `aws_sqs_queue` carrying sensitive data without `kms_master_key_id` (or SSE) | SSE with KMS | SEC08-BP02 |

### Logging and monitoring

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| No `aws_cloudtrail` (or no org trail); `enable_log_file_validation = false`; `is_multi_region_trail = false` | Organization multi-Region trail with log file validation, delivered to a separate log-archive account | CWE-778, SEC04-BP01 |
| `aws_flow_log` absent for production VPCs | VPC Flow Logs enabled | SEC04-BP01 |
| S3 access logging, ALB `access_logs`, API Gateway stage logging absent for sensitive workloads | Enabled, with retention set on `aws_cloudwatch_log_group` (`retention_in_days`) | CWE-778 |
| `aws_cloudwatch_log_group` without `kms_key_id` for logs containing personal data | KMS encryption | SEC08-BP02 |

### Data protection and backups

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `aws_db_instance` with `backup_retention_period = 0`, `deletion_protection = false`, `skip_final_snapshot = true` in production | Retention ≥ 7 days (or per policy), deletion protection, final snapshot | REL09-BP01 |
| `aws_s3_bucket_versioning` disabled for data of record; no Object Lock where immutability is required | Versioning on; Object Lock or AWS Backup vault lock for backups | REL09-BP02 |
| `aws_dynamodb_table` without `point_in_time_recovery { enabled = true }` | PITR enabled | REL09-BP01 |
| `lifecycle { prevent_destroy = false }` (the default) on stateful resources | `prevent_destroy = true` on critical data stores | REL09-BP01 |

### Secrets

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| Literal passwords or keys in `.tf` or `.tfvars` (`password = "..."` on `aws_db_instance`, `aws_secretsmanager_secret_version.secret_string` with a literal) | `manage_master_user_password = true` (RDS-managed secret); generate with `random_password` and store in Secrets Manager; `ephemeral` resources and write-only arguments where supported (Terraform 1.10+/1.11+) | CWE-798, SEC02-BP03 |
| Variables holding secrets without `sensitive = true`; outputs exposing secrets | `sensitive = true` (this hides the value in CLI output only; it's still in state) | CWE-532 |
| Local backend, or state committed to git | Remote backend; never commit `*.tfstate` | CWE-312 |
| `backend "s3"` without `encrypt = true`, without locking (`use_lockfile = true`, generally available in Terraform 1.11+; DynamoDB locking is deprecated), or a state bucket readable by broad roles | Encrypted (SSE-KMS), locked, versioned, access-restricted state bucket | CWE-312, SEC08-BP02 |

### Supply chain and pinning

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `required_providers` without `version` constraints; `.terraform.lock.hcl` not committed | Version constraints plus a committed lock file (it records provider hashes) | CWE-1357, OWASP A03 |
| `module` `source` from git without `?ref=<tag or commit>`; registry modules without `version` | Pin to a tag, or better a commit SHA, for git sources; `version =` for registry modules | CWE-829, CICD-SEC-3 |
| `local-exec` / `remote-exec` provisioners or `external` data sources running scripts with interpolated variables | Avoid provisioners; if needed, no untrusted interpolation into commands | CWE-78 |

## Chains to look for

- **IMDSv1 + application SSRF → instance role credentials.** `http_tokens` not `"required"` on an instance or launch template, plus an SSRF in the app running there (see the language guides), plus an instance profile with broad `s3:*` or `iam:*`. The result is a data breach or account takeover.
- **Wildcard role + leaked key.** An `aws_iam_access_key` (or a secret in `.tfvars` or state) plus a policy with `"*"` actions. One leaked credential becomes full account compromise.
- **Readable state bucket → every secret.** State in an S3 bucket readable by a broad role or principal, plus database passwords or keys in state. Anyone with that role gets every credential Terraform manages.
- **Over-trusting OIDC role + pipeline from forks.** A CI role whose `sub` condition accepts any branch or fork, plus a pipeline that runs on untrusted PRs. A pull request deploys to production (see `pipelines-containers.md`).
- **Public bucket + static-site config holding keys.** Public read on a bucket plus config files or backups stored in it.

## Execution risks

- **`terraform init`** downloads providers (executable binaries) and modules from the configured sources. Malicious or typo-squatted modules run when you plan or apply.
- **`terraform plan`** executes providers and `external` data sources, which can run arbitrary programs, and calls cloud APIs with whatever credentials are in the environment.
- **Plan JSON** (`terraform show -json` of a saved plan) gives scanners resolved values and is more accurate than scanning HCL. It needs `init` and `plan`, which need credentials. **Ask before running `init` or `plan`.** Static scanning of the `.tf` files needs neither.
- **Never run `apply` or `destroy`.**

## Quick search patterns

Candidates only; each hit still goes through `triage.md`.

```
"0\.0\.0\.0/0"|"::/0"
actions\s*=\s*\[\s*"\*"|"Action"\s*:\s*"\*"
resources\s*=\s*\[\s*"\*"\s*\]
publicly_accessible\s*=\s*true
http_tokens\s*=\s*"optional"
storage_encrypted\s*=\s*false|encrypted\s*=\s*false
block_public_(acls|policy)\s*=\s*false
skip_final_snapshot\s*=\s*true|deletion_protection\s*=\s*false
(password|secret|token|access_key)\s*=\s*"[^"$]
aws_iam_access_key
source\s*=\s*"git::[^"?]*"
local-exec|remote-exec|data\s+"external"
authorization_type\s*=\s*"NONE"
enable_key_rotation\s*=\s*false
```
