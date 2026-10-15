#!/usr/bin/env bash
# Download the current CISA Known Exploited Vulnerabilities (KEV) catalog and,
# optionally, match CVE IDs against it. Required on every audit (SKILL.md rule 9).
#
# Usage: fetch-kev.sh [output-dir] [CVE-ID ...]
#   output-dir defaults to .appsec-audit/data
#   CVE IDs may also be piped in, one per line:  ... | fetch-kev.sh .appsec-audit/data -
#
# Prints the catalog version, release date, and entry count, then one line per
# matched CVE. Exits 1 if the catalog can't be downloaded or parsed.

set -euo pipefail
KEV_URL='https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
out_dir="${1:-.appsec-audit/data}"
[ $# -gt 0 ] && shift
mkdir -p "$out_dir"
kev="$out_dir/kev.json"

if ! curl -fsSL --retry 3 --max-time 60 -o "$kev.tmp" "$KEV_URL"; then
  echo "ERROR: could not download the KEV catalog from $KEV_URL" >&2
  echo "Report KEV status as UNKNOWN for every CVE (SKILL.md rule 9)." >&2
  exit 1
fi
mv "$kev.tmp" "$kev"

cves=("$@")
if [ "${cves[0]:-}" = "-" ]; then
  mapfile -t cves < <(grep -oE 'CVE-[0-9]{4}-[0-9]+' || true)
fi

# Parse with Node (required by the guardrail hooks) or Python, whichever exists.
if command -v node >/dev/null 2>&1; then
  KEV_FILE="$kev" node -e '
    const kev = JSON.parse(require("fs").readFileSync(process.env.KEV_FILE, "utf8"));
    console.log(`catalogVersion=${kev.catalogVersion} dateReleased=${kev.dateReleased} count=${kev.count}`);
    const byId = new Map(kev.vulnerabilities.map((v) => [v.cveID, v]));
    for (const id of process.argv.slice(1)) {
      const v = byId.get(id.toUpperCase());
      console.log(v
        ? `KEV ${v.cveID} added=${v.dateAdded} due=${v.dueDate} ransomware=${v.knownRansomwareCampaignUse} | ${v.vendorProject} ${v.product}: ${v.vulnerabilityName}`
        : `not-in-kev ${id}`);
    }' "${cves[@]+"${cves[@]}"}"
elif command -v python3 >/dev/null 2>&1; then
  KEV_FILE="$kev" python3 -I -c '
import json, os, sys
kev = json.load(open(os.environ["KEV_FILE"], encoding="utf-8"))
print("catalogVersion={catalogVersion} dateReleased={dateReleased} count={count}".format(**kev))
by_id = {v["cveID"]: v for v in kev["vulnerabilities"]}
for cve in sys.argv[1:]:
    v = by_id.get(cve.upper())
    if v:
        print("KEV {cveID} added={dateAdded} due={dueDate} ransomware={r} | {vendorProject} {product}: {vulnerabilityName}".format(
            r=v.get("knownRansomwareCampaignUse"), **v))
    else:
        print("not-in-kev " + cve)
' "${cves[@]+"${cves[@]}"}"
else
  echo "ERROR: Node.js or Python 3 is needed to parse $kev" >&2
  exit 1
fi
