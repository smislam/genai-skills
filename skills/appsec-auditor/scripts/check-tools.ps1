<#
Preflight for the appsec-auditor skill: report what's available on this machine.
The skill never installs anything. 'required' items run the deterministic checklist, the
hooks, and the vulnerability-data lookups; scanner rows are optional extras, used only if
already present.
Usage: .\check-tools.ps1            (all tools)
       .\check-tools.ps1 -Missing   (only tools that are not installed)
Read-only: runs each tool's version command, nothing else.
#>
param([switch]$Missing)

$tools = @(
  @('required',   'Node.js 18+ (scripts, hooks, gate)', 'node',       'node --version'),
  @('required',   'git',                             'git',          'git --version'),
  @('required',   'curl (OSV.dev, KEV, EPSS, proxy)', 'curl.exe',    'curl.exe --version'),
  @('sast',       'Opengrep',                        'opengrep',     'opengrep --version'),
  @('sast',       'Semgrep CE',                      'semgrep',      'semgrep --version'),
  @('sast',       'Bandit (Python)',                 'bandit',       'bandit --version'),
  @('sast',       'gosec (Go)',                      'gosec',        'gosec -version'),
  @('sast',       'SpotBugs (Java/Kotlin)',          'spotbugs',     'spotbugs -version'),
  @('sast',       'PMD (Java/Kotlin)',               'pmd',          'pmd --version'),
  @('sast',       'ESLint (JS/TS, via npx)',         'npx',          'npx --no-install eslint --version'),
  @('sast',       'DevSkim (C#/.NET)',               'devskim',      'devskim --version'),
  @('sast',       'Clippy (Rust)',                   'cargo-clippy', 'cargo clippy --version'),
  @('sast',       'cppcheck (C/C++)',                'cppcheck',     'cppcheck --version'),
  @('sast',       'Flawfinder (C/C++)',              'flawfinder',   'flawfinder --version'),
  @('sca',        'OSV-Scanner',                     'osv-scanner',  'osv-scanner --version'),
  @('sca',        'Trivy',                           'trivy',        'trivy --version'),
  @('sca',        'Grype',                           'grype',        'grype version'),
  @('sca',        'pip-audit (Python)',              'pip-audit',    'pip-audit --version'),
  @('sca',        'npm (npm audit)',                 'npm',          'npm --version'),
  @('sca',        'govulncheck (Go)',                'govulncheck',  'govulncheck -version'),
  @('sca',        'cargo-audit (Rust)',              'cargo-audit',  'cargo audit --version'),
  @('sca',        'cargo-deny (Rust)',               'cargo-deny',   'cargo deny --version'),
  @('sca',        '.NET SDK (dotnet list package)',  'dotnet',       'dotnet --version'),
  @('secrets',    'Gitleaks',                        'gitleaks',     'gitleaks version'),
  @('secrets',    'Betterleaks',                     'betterleaks',  'betterleaks --version'),
  @('secrets',    'TruffleHog',                      'trufflehog',   'trufflehog --version'),
  @('iac',        'Checkov',                         'checkov',      'checkov --version'),
  @('iac',        'TFLint',                          'tflint',       'tflint --version'),
  @('iac',        'Hadolint',                        'hadolint',     'hadolint --version'),
  @('iac',        'kube-linter',                     'kube-linter',  'kube-linter version'),
  @('sbom',       'Syft',                            'syft',         'syft version')
)

$rows = foreach ($t in $tools) {
  $category, $name, $bin, $vcmd = $t
  $status = 'MISSING'
  $ver = '-'
  if (Get-Command $bin -ErrorAction SilentlyContinue) {
    $global:LASTEXITCODE = 0
    $out = try { (Invoke-Expression "$vcmd 2>&1" | Out-String) } catch { $null }
    if ($null -ne $out -and $LASTEXITCODE -eq 0) {
      $status = 'installed'
      $ver = if ($out -match '\d+\.\d+(\.\d+)?') { $Matches[0] } else { 'unknown' }
    }
  }
  if ($Missing -and $status -eq 'installed') { continue }
  [pscustomobject]@{ Category = $category; Tool = $name; Status = $status; Version = $ver }
}
$rows | Format-Table -AutoSize

$major = 0
if (Get-Command node -ErrorAction SilentlyContinue) { $major = [int](node -p "process.versions.node.split('.')[0]") }
if ($major -lt 18) { Write-Output 'Node.js 18+ is missing: the audit runs without the checklist and gate, and is labeled non-deterministic.' }
Write-Output 'Scanners are optional: used only if already installed (references/tools.md).'
Write-Output 'This skill never installs tools.'
