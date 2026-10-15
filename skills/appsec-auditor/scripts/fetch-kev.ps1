<#
Download the current CISA Known Exploited Vulnerabilities (KEV) catalog and,
optionally, match CVE IDs against it. Required on every audit (SKILL.md rule 9).

Usage: .\fetch-kev.ps1 [-OutDir .appsec-audit\data] [-Cve CVE-2024-1234,CVE-2025-5678]
       Get-Content cves.txt | .\fetch-kev.ps1

Prints the catalog version, release date, and entry count, then one line per
matched CVE. Exits 1 if the catalog can't be downloaded or parsed.
#>
param(
  [string]$OutDir = '.appsec-audit\data',
  [string[]]$Cve = @(),
  [Parameter(ValueFromPipeline = $true)][string]$InputLine
)
begin {
  $KevUrl = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
  $piped = New-Object System.Collections.Generic.List[string]
}
process {
  if ($InputLine) {
    foreach ($m in [regex]::Matches($InputLine, 'CVE-\d{4}-\d+')) { $piped.Add($m.Value) }
  }
}
end {
  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  $kevPath = Join-Path $OutDir 'kev.json'
  try {
    Invoke-WebRequest -Uri $KevUrl -OutFile "$kevPath.tmp" -UseBasicParsing -TimeoutSec 60
    Move-Item -Force "$kevPath.tmp" $kevPath
    $kev = Get-Content -Raw -Encoding UTF8 $kevPath | ConvertFrom-Json
  } catch {
    Write-Error "Could not download or parse the KEV catalog from $KevUrl. Report KEV status as UNKNOWN for every CVE (SKILL.md rule 9)."
    exit 1
  }

  Write-Output "catalogVersion=$($kev.catalogVersion) dateReleased=$($kev.dateReleased) count=$($kev.count)"
  $byId = @{}
  foreach ($v in $kev.vulnerabilities) { $byId[$v.cveID] = $v }
  # -File passes "A,B" as one string; split on commas and whitespace.
  $ids = @($Cve | ForEach-Object { $_ -split '[,\s]+' }) + $piped | Where-Object { $_ }
  foreach ($id in $ids) {
    $v = $byId[$id.ToUpper()]
    if ($v) {
      Write-Output "KEV $($v.cveID) added=$($v.dateAdded) due=$($v.dueDate) ransomware=$($v.knownRansomwareCampaignUse) | $($v.vendorProject) $($v.product): $($v.vulnerabilityName)"
    } else {
      Write-Output "not-in-kev $id"
    }
  }
}
