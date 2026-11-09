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

# Python 3.12+ runs the scripts and hooks. Find a launcher that is new enough: python3, python,
# or the Windows launcher (py -3). If none is, fall back to the first one that runs at all.
$pyBin = $null; $pyArgs = @(); $pyOk = $false
foreach ($cand in @(@('python3'), @('python'), @('py', '-3'))) {
  if (-not (Get-Command $cand[0] -ErrorAction SilentlyContinue)) { continue }
  $extra = @($cand | Select-Object -Skip 1)
  $global:LASTEXITCODE = 0
  & $cand[0] @extra -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { $pyBin = $cand[0]; $pyArgs = $extra; $pyOk = $true; break }
  $global:LASTEXITCODE = 0
  & $cand[0] @extra --version 2>&1 | Out-Null
  if ($null -eq $pyBin -and $LASTEXITCODE -eq 0) { $pyBin = $cand[0]; $pyArgs = $extra }
}
if (-not $pyBin) { $pyBin = 'python3' }
$pyCmd = (@($pyBin) + $pyArgs) -join ' '

$tools = @(
  @('required',   'Python 3.12+ (scripts and hooks)', $pyBin,        "$pyCmd --version"),
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
    # $vcmd comes from the fixed table above ("program arg arg"); split it and call the program
    # directly instead of passing a string to Invoke-Expression.
    # Keep the arguments an array: splatting a bare string passes it one character at a time.
    $parts = @($vcmd -split '\s+')
    $exe = $parts[0]
    $exeArgs = @($parts | Select-Object -Skip 1)
    $out = try { (& $exe @exeArgs 2>&1 | Out-String) } catch { $null }
    if ($null -ne $out -and $LASTEXITCODE -eq 0) {
      $status = 'installed'
      $ver = if ($out -match '\d+\.\d+(\.\d+)?') { $Matches[0] } else { 'unknown' }
    }
  }
  if ($Missing -and $status -eq 'installed') { continue }
  [pscustomobject]@{ Category = $category; Tool = $name; Status = $status; Version = $ver }
}
$rows | Format-Table -AutoSize

if (-not $pyOk) { Write-Output 'Python 3.12+ is missing: the audit runs without the checklist and gate, and is labeled non-deterministic.' }
Write-Output 'Scanners are optional: used only if already installed (references/tools.md).'
Write-Output 'This skill never installs tools.'
