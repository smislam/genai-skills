#!/usr/bin/env bash
# Preflight for the appsec-auditor skill: report what's available on this machine.
# The skill never installs anything. 'required' items run the deterministic checklist, the
# hooks, and the vulnerability-data lookups; scanner rows are optional extras, used only if
# already present.
# Usage: check-tools.sh            (all tools)
#        check-tools.sh --missing  (only tools that are not installed)
# Read-only: runs each tool's version command, nothing else.

set -u
only_missing=0
[ "${1:-}" = "--missing" ] && only_missing=1

# category|tool|binary|version command
tools='
required|Node.js 18+ (scripts, hooks, gate)|node|node --version
required|git|git|git --version
required|curl (OSV.dev, KEV, EPSS, proxy)|curl|curl --version
sast|Opengrep|opengrep|opengrep --version
sast|Semgrep CE|semgrep|semgrep --version
sast|Bandit (Python)|bandit|bandit --version
sast|gosec (Go)|gosec|gosec -version
sast|SpotBugs (Java/Kotlin)|spotbugs|spotbugs -version
sast|PMD (Java/Kotlin)|pmd|pmd --version
sast|ESLint (JS/TS, via npx)|npx|npx --no-install eslint --version
sast|DevSkim (C#/.NET)|devskim|devskim --version
sast|Clippy (Rust)|cargo-clippy|cargo clippy --version
sast|cppcheck (C/C++)|cppcheck|cppcheck --version
sast|Flawfinder (C/C++)|flawfinder|flawfinder --version
sca|OSV-Scanner|osv-scanner|osv-scanner --version
sca|Trivy|trivy|trivy --version
sca|Grype|grype|grype version
sca|pip-audit (Python)|pip-audit|pip-audit --version
sca|npm (npm audit)|npm|npm --version
sca|govulncheck (Go)|govulncheck|govulncheck -version
sca|cargo-audit (Rust)|cargo-audit|cargo audit --version
sca|cargo-deny (Rust)|cargo-deny|cargo deny --version
sca|.NET SDK (dotnet list package)|dotnet|dotnet --version
secrets|Gitleaks|gitleaks|gitleaks version
secrets|Betterleaks|betterleaks|betterleaks --version
secrets|TruffleHog|trufflehog|trufflehog --version
iac|Checkov|checkov|checkov --version
iac|TFLint|tflint|tflint --version
iac|Hadolint|hadolint|hadolint --version
iac|kube-linter|kube-linter|kube-linter version
sbom|Syft|syft|syft version
'

printf '%-11s %-34s %-10s %s\n' CATEGORY TOOL STATUS VERSION
printf '%s\n' "$tools" | while IFS='|' read -r cat name bin vcmd; do
  [ -z "$cat" ] && continue
  status=MISSING
  ver=-
  if command -v "$bin" >/dev/null 2>&1; then
    # </dev/null keeps the version command from reading this loop's input.
    if out=$($vcmd 2>&1 </dev/null); then
      status=installed
      ver=$(printf '%s\n' "$out" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1 || true)
      ver=${ver:-unknown}
    fi
  fi
  [ "$only_missing" = 1 ] && [ "$status" = installed ] && continue
  printf '%-11s %-34s %-10s %s\n' "$cat" "$name" "$status" "$ver"
done

echo
major=$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)
if [ "$major" -lt 18 ] 2>/dev/null; then
  echo "Node.js 18+ is missing: the audit runs without the checklist and gate, and is labeled non-deterministic."
fi
echo "Scanners are optional: used only if already installed (references/tools.md)."
echo "This skill never installs tools."
