# AWS CDK: security review guide

Covers AWS CDK v2 apps in TypeScript, Python, Java, C#, and Go. CDK is code that generates CloudFormation, so review it two ways: the construct code (what the author asked for) and, if approved, the synthesized templates (what will actually deploy). Tool commands are in `tools.md`; triage rules in `triage.md`.

## What to read first

| File | Why it matters |
|---|---|
| `cdk.json` | The `app` command (what `cdk synth` executes), feature flags under `context`, and Aspects-related settings |
| `bin/*` (TS), `app.py`, `src/main/**/App.java`, `Program.cs`, `*.go` with `awscdk.NewApp` | The app entry point: which stacks, environments, and Aspects (cdk-nag) are applied |
| `lib/**`, `stacks/**`, construct modules | The resources; the review happens here |
| `cdk.context.json` | Cached lookups (VPC IDs, AMIs, account details). Usually committed; check it for anything sensitive |
| `cdk.out/*.template.json` (if present) | Synthesized CloudFormation; the most accurate view of what deploys, though it may be stale |
| `package.json` / `requirements.txt` / `pom.xml` / `*.csproj` / `go.mod` | `aws-cdk-lib` version, `cdk-nag`, third-party construct libraries |
| Pipeline code (`pipelines.CodePipeline`, `cdk-pipelines`) | Self-mutating pipelines and their roles; see `pipelines-containers.md` |

## Misconfigurations by area

Names below use TypeScript casing; the Python, Java, C#, and Go bindings use the same construct and property names in their own casing (`block_public_access` in Python, `BlockPublicAccess` in C#).

### Identity and IAM

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `new iam.PolicyStatement({ actions: ['*'] })`, or `resources: ['*']` on write actions; `iam.ManagedPolicy.fromAwsManagedPolicyName('AdministratorAccess')` on workload roles | Scoped actions and ARNs; prefer L2 `grant*` methods, which generate least-privilege statements | CWE-269, SEC03-BP02 |
| Broad grants where narrow ones exist: `bucket.grantReadWrite(fn)` when only read is needed; `table.grantFullAccess(...)`; `key.grant(principal, 'kms:*')` | The narrowest `grant*` (`grantRead`, `grantPut`, `grantReadData`, `grantDecrypt`) | CWE-269, SEC03-BP02 |
| `role.addToPolicy` / `addToPrincipalPolicy` statements added for convenience during development | Review each for least privilege | SEC03-BP04 |
| `new iam.AccountRootPrincipal()` or `iam.AnyPrincipal()` in resource policies; `iam.User` with `iam.AccessKey` | Specific principals with conditions; roles with temporary credentials | CWE-284, SEC02-BP02 |
| OIDC deploy roles (`iam.OpenIdConnectPrincipal` / `iam.WebIdentityPrincipal`) whose `StringLike` on `token.actions.githubusercontent.com:sub` allows every repo or branch | Pin `sub` to the repo and branch or environment; check `aud` | CICD-SEC-2 |

### Network exposure

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `securityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(22))` or any non-web port from `anyIpv4()` / `anyIpv6()`; `allowAllOutbound: true` where egress should be restricted | Specific peers or security groups; SSM instead of SSH; restricted egress for sensitive tiers | CWE-284, SEC05-BP02 |
| `rds.DatabaseInstance` / `DatabaseCluster` with `publiclyAccessible: true`, or placed in `vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC }` | Private isolated subnets; `publiclyAccessible: false` | SEC05-BP01 |
| `s3.Bucket` with `blockPublicAccess` relaxed (`BlockPublicAccess.BLOCK_ACLS` only, or custom `BlockPublicAccess({ ... false })`), `publicReadAccess: true`, `bucket.grantPublicAccess()` | `blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL` (the default in recent versions); CloudFront with origin access control for public content | CWE-284, SEC03-BP07 |
| `lambda.FunctionUrl` / `fn.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE })` on non-public functions; API Gateway methods with `authorizationType: AuthorizationType.NONE` | `AWS_IAM`, Cognito, or a Lambda authorizer | CWE-306 |
| `ec2.Instance` / `LaunchTemplate` without `requireImdsv2: true` | `requireImdsv2: true` (also available as the `InstanceRequireImdsv2Aspect`) | CWE-918 (enabler), SEC06-BP05 |
| ALB listeners on HTTP without a redirect; no WAF association | HTTPS with a modern `sslPolicy`; HTTP redirect; `wafv2.CfnWebACLAssociation` | CWE-319, SEC05-BP03 |

### Encryption at rest and in transit

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `s3.Bucket` without `enforceSSL: true`; `encryption` left at the default when the data class requires a customer-managed key | `enforceSSL: true`; `encryption: s3.BucketEncryption.KMS` with `encryptionKey` for restricted data | CWE-319, SEC09-BP02 |
| `rds.DatabaseInstance` with `storageEncrypted: false`; `dynamodb.Table` where the data class requires a customer-managed key but `encryption` is left at the AWS-owned default | `storageEncrypted: true` with `storageEncryptionKey`; `TableEncryption.CUSTOMER_MANAGED` where required | CWE-311, SEC08-BP02 |
| `kms.Key` with `enableKeyRotation: false`; `sns.Topic` / `sqs.Queue` carrying sensitive data without `masterKey` / `encryption` | Rotation on; `encryption: sqs.QueueEncryption.KMS` (or SQS-managed), `masterKey` for SNS | SEC08-BP01, SEC08-BP02 |
| `elasticache.CfnReplicationGroup` (L1) without `transitEncryptionEnabled` / `atRestEncryptionEnabled` | Both `true` | SEC08-BP02 |

L1 `Cfn*` constructs have no secure defaults: every property must be set explicitly. Give them more scrutiny than L2s.

### Logging and monitoring

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `s3.Bucket` without `serverAccessLogsBucket` for sensitive data; ALB without `logAccessLogs`; API Gateway stages without `accessLogDestination` | Logging enabled to a protected bucket or log group | CWE-778, SEC04-BP01 |
| `logs.LogGroup` with `retention: RetentionDays.INFINITE` (cost) or a very short retention (audit gap); no `encryptionKey` for personal data | Retention per policy; KMS for sensitive logs | CWE-778 |
| `ec2.Vpc` without `flowLogs` for production | `vpc.addFlowLog(...)` or the `flowLogs` property | SEC04-BP01 |

### Data protection and backups

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `removalPolicy: RemovalPolicy.DESTROY` (and `autoDeleteObjects: true` on buckets) on production data stores | `RemovalPolicy.RETAIN` or `SNAPSHOT` for stateful resources in production | REL09-BP01 |
| `rds` with `backupRetention: Duration.days(0)` or `deletionProtection: false` in production | Retention per policy; `deletionProtection: true` | REL09-BP01 |
| `dynamodb.Table` without point-in-time recovery (`pointInTimeRecovery: true`, or `pointInTimeRecoverySpecification` in newer versions); `s3.Bucket` without `versioned: true` for data of record | PITR on; versioning on; AWS Backup plans (`backup.BackupPlan`) | REL09-BP01 |

### Secrets

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| Literal secrets in construct props: `environment: { DB_PASSWORD: 'literal' }` on Lambda or ECS; `SecretValue.unsafePlainText('...')`; `credentials: rds.Credentials.fromPassword('admin', SecretValue.unsafePlainText(...))` | `rds.Credentials.fromGeneratedSecret('admin')`; `secretsmanager.Secret`; `ecs.Secret.fromSecretsManager(...)` for container secrets | CWE-798, SEC02-BP03 |
| `SecretValue.secretsManager(...)` or `ssm.StringParameter.valueFromLookup(...)` resolved into Lambda **environment variables**, where the plaintext is visible in the console and API | Pass the secret ARN; read it at runtime with the SDK or the Parameters and Secrets extension | CWE-312, SEC02-BP03 |
| Secrets in `cdk.json` context or `cdk.context.json` | Remove them; context is committed and synthesized into templates | CWE-798 |

### Supply chain and pinning

| Insecure pattern | Secure setting | Mapping |
|---|---|---|
| `aws-cdk-lib` or construct libraries unpinned without a committed lockfile | Committed lockfile; review third-party construct libraries like any dependency | OWASP A03, CWE-1357 |
| `lambda.Code.fromAsset` bundling with `bundling.command` running shell commands built from variables; Docker image assets from unpinned base images | Fixed bundling commands; base images pinned by digest | CWE-78, CWE-829 |
| No cdk-nag (`Aspects.of(app).add(new AwsSolutionsChecks())`), or `NagSuppressions.addResourceSuppressions` without a meaningful `reason` | cdk-nag applied in the app; every suppression justified | CWE-1357, SEC01-BP06 |

## Chains to look for

- **`requireImdsv2` missing + SSRF in the app + `grant*` on broad resources.** Instance or container credentials are stolen and used against the data the role can reach.
- **Self-mutating pipeline + PR-triggered source.** A `pipelines.CodePipeline` with `selfMutation` (the default) deploys whatever the source branch says. If untrusted changes can reach that branch, or the GitHub source action triggers on PRs, the attacker edits the pipeline itself and gains deploy-role access.
- **`AuthorizationType.NONE` API + Lambda with broad table access.** An unauthenticated caller reads or writes the whole table through the function.
- **Secret resolved into an environment variable + a role allowed `lambda:GetFunctionConfiguration`.** Anyone with read-only access to Lambda sees the plaintext secret.

## Execution risks

- **`cdk synth`, `cdk diff`, and `cdk deploy`** execute the CDK app: the command in `cdk.json` `app`, for example `npx ts-node bin/app.ts` or `python3 app.py`. That is arbitrary project code. It may also call AWS APIs for context lookups using the credentials in the environment.
- **Asset bundling** during synth can run Docker builds and shell commands.
- **Ask before running `synth`.** Without approval, review the construct code directly, plus any existing `cdk.out/` templates (noting they may be stale).
- **Never run `deploy` or `destroy`.**
