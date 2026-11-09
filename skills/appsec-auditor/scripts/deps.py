#!/usr/bin/env python3
"""Check every package in .appsec-audit/coverage.json against live vulnerability data.

Sources: OSV.dev (advisories), CISA KEV (known exploited), FIRST EPSS (exploit probability).
Writes .appsec-audit/deps.json, including one checklist item per package vulnerability.
Usage: python -I deps.py [--root <repo>]
Sends only package names, versions, and CVE IDs (SKILL.md rule 4). Network settings: lib/net.py.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write .pyc files next to the scripts

if sys.version_info < (3, 12):
    sys.stderr.write(f'appsec-auditor needs Python 3.12 or newer; found {sys.version.split()[0]}\n')
    raise SystemExit(2)

import json  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402
from urllib.parse import quote  # noqa: E402

# `python -I` drops the script directory from sys.path. Add only this script's own directory.
_HERE = str(Path(__file__).resolve().parent)
if not sys.path or sys.path[0] != _HERE:
    sys.path.insert(0, _HERE)

from lib import net  # noqa: E402
from lib.cliutil import arg_value, configure_streams, read_json, sha1_hex, utc_now_iso  # noqa: E402

__all__ = ['main']

URI_COMPONENT_SAFE = "-_.!~*'()"
OSV_BATCH = 1000
EPSS_BATCH = 50


def as_dict(value: Any) -> dict[str, Any]:
    """The value if it is a JSON object, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """The value if it is a JSON array, otherwise an empty list."""
    return value if isinstance(value, list) else []


def to_float(value: Any) -> float | None:
    """A number from a JSON value or numeric text; None when it is not a number."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


class Run:
    """State of one dependency check; ``out`` becomes deps.json."""

    def __init__(self, coverage: dict[str, Any], now: str) -> None:
        """Start from the packages listed in coverage.json."""
        self.now = now
        self.packages: list[dict[str, Any]] = [p for p in as_list(coverage.get('packages')) if isinstance(p, dict)]
        self.out: dict[str, Any] = {
            'schema': 1, 'generatedAt': now, 'commit': coverage.get('commit'), 'status': 'ok', 'errors': [],
            'osv': {}, 'kev': {}, 'epss': {}, 'packages': [], 'items': [],
        }
        self.ids_per_pkg: list[list[str]] = []
        self.details: dict[str, Any] = {}
        self.kev_by_id: dict[str, Any] | None = None
        self.osv_ok = True
        self.epss_ok = True

    def fail(self, source: str, result: dict[str, Any]) -> None:
        """Record a failed lookup."""
        error = {'source': source, **{k: result[k] for k in ('category', 'hint', 'status') if k in result}}
        self.out['errors'].append(error)

    def follow_pages(self, query: dict[str, Any], first: dict[str, Any], ids: list[str]) -> None:
        """Collect the remaining result pages of one OSV query into ``ids``."""
        token = first.get('next_page_token')
        while token:
            more = net.post_json(f"{net.ENDPOINTS['osv']}/query", {**query, 'page_token': token})
            if not more['ok']:
                self.fail('osv', more)
                self.osv_ok = False
                break
            ids.extend(v['id'] for v in as_list(as_dict(more['data']).get('vulns')))
            token = as_dict(more['data']).get('next_page_token')

    def query_osv(self) -> None:
        """OSV batch query (up to 1000 queries per request)."""
        for start in range(0, len(self.packages), OSV_BATCH):
            if not self.osv_ok:
                break
            queries = [{'package': {'ecosystem': p['ecosystem'], 'name': p['name']}, 'version': p['version']}
                       for p in self.packages[start:start + OSV_BATCH]]
            result = net.post_json(f"{net.ENDPOINTS['osv']}/querybatch", {'queries': queries})
            if not result['ok']:
                self.fail('osv', result)
                self.osv_ok = False
                break
            for query, res in zip(queries, result['data']['results'], strict=True):
                res = as_dict(res)
                ids = [v['id'] for v in as_list(res.get('vulns'))]
                self.follow_pages(query, res, ids)
                self.ids_per_pkg.append(ids)

    def fetch_details(self) -> None:
        """Each distinct advisory once."""
        if not self.osv_ok:
            return
        for vuln_id in sorted({i for ids in self.ids_per_pkg for i in ids}):
            encoded = quote(vuln_id, safe=URI_COMPONENT_SAFE)  # encodeURIComponent
            result = net.get_json(f"{net.ENDPOINTS['osv']}/vulns/{encoded}")
            if not result['ok']:
                self.fail('osv', result)
                self.osv_ok = False
                break
            self.details[vuln_id] = result['data']

    def fetch_kev(self, audit_dir: Path) -> None:
        """CISA KEV, downloaded fresh."""
        result = net.get_json(net.ENDPOINTS['kev'])
        data = as_dict(result.get('data'))
        if result['ok'] and isinstance(data.get('vulnerabilities'), list):
            self.kev_by_id = {v.get('cveID'): v for v in data['vulnerabilities'] if isinstance(v, dict)}
            self.out['kev'] = {'ok': True, 'catalogVersion': data.get('catalogVersion'),
                               'dateReleased': data.get('dateReleased'), 'count': data.get('count')}
            (audit_dir / 'data').mkdir(parents=True, exist_ok=True)
            with open(audit_dir / 'data' / 'kev.json', 'w', encoding='utf-8', newline='') as handle:
                handle.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
        else:
            self.fail('kev', result if not result['ok'] else
                      {'category': 'format', 'hint': 'Unexpected KEV catalog format.'})
            self.out['kev'] = {'ok': False}


def fixed_versions(vuln: dict[str, Any], pkg: dict[str, Any]) -> list[str]:
    """Fixed versions of an advisory for one package."""
    fixed: set[str] = set()
    for affected in as_list(vuln.get('affected')):
        package = as_dict(as_dict(affected).get('package'))
        if package.get('name') != pkg['name'] or package.get('ecosystem') != pkg['ecosystem']:
            continue
        for rng in as_list(as_dict(affected).get('ranges')):
            for event in as_list(as_dict(rng).get('events')):
                if as_dict(event).get('fixed'):
                    fixed.add(event['fixed'])
    return sorted(fixed)


def build_vuln(run: Run, vuln_id: str, pkg: dict[str, Any], all_cves: set[str]) -> dict[str, Any]:
    """The result record for one advisory of one package."""
    detail = as_dict(run.details.get(vuln_id))
    db = as_dict(detail.get('database_specific'))
    aliases = [a for a in as_list(detail.get('aliases')) + [vuln_id] if str(a).startswith('CVE-')]
    cves = list(dict.fromkeys(aliases))
    all_cves.update(cves)
    kev = next((run.kev_by_id[c] for c in cves if run.kev_by_id and c in run.kev_by_id), None)
    if run.kev_by_id is None:
        kev_value: Any = 'unknown'
    elif kev is not None:
        kev_value = {'dateAdded': kev.get('dateAdded'), 'dueDate': kev.get('dueDate'),
                     'ransomware': kev.get('knownRansomwareCampaignUse')}
    else:
        kev_value = None
    return {
        'id': vuln_id,
        'cves': sorted(cves),
        'summary': detail.get('summary') or '',
        'severity': db.get('severity') or None,
        'cvss': [as_dict(s).get('score') for s in as_list(detail.get('severity'))
                 if str(as_dict(s).get('type')).startswith('CVSS')],
        'cwes': db.get('cwe_ids') or [],
        'fixed': fixed_versions(detail, pkg),
        'published': detail.get('published') or None,
        'kev': kev_value,
    }


def build_items(run: Run) -> set[str]:
    """Fill ``out.packages`` and ``out.items``; return every CVE seen."""
    all_cves: set[str] = set()
    for i, pkg in enumerate(run.packages):
        ids = run.ids_per_pkg[i] if i < len(run.ids_per_pkg) else []
        vulns = [build_vuln(run, vuln_id, pkg, all_cves) for vuln_id in ids]
        run.out['packages'].append({**pkg, 'vulns': vulns})
        for vuln in vulns:
            fields = [pkg.get(k) for k in ('ecosystem', 'name', 'version', 'file')] + [vuln['id']]
            key = '|'.join('' if x is None else str(x) for x in fields)
            item = {
                'id': 'D-' + sha1_hex(key)[:12], 'kind': 'dependency', 'ecosystem': pkg.get('ecosystem'),
                'package': pkg.get('name'), 'version': pkg.get('version'), 'file': pkg.get('file'),
            }
            if 'direct' in pkg:
                item['direct'] = pkg['direct']
            item.update({'vuln': vuln['id'], 'cves': vuln['cves'], 'severity': vuln['severity'],
                         'kev': vuln['kev'], 'fixed': vuln['fixed']})
            run.out['items'].append(item)
    return all_cves


def score_epss(run: Run, cves: set[str]) -> None:
    """EPSS for every CVE, in batches; attach the highest score to each item."""
    cve_list = sorted(cves)
    scores: dict[str, Any] = {}
    for start in range(0, len(cve_list), EPSS_BATCH):
        result = net.get_json(f"{net.ENDPOINTS['epss']}?cve={','.join(cve_list[start:start + EPSS_BATCH])}")
        if not result['ok']:
            run.fail('epss', result)
            run.epss_ok = False
            break
        for row in as_list(as_dict(result['data']).get('data')):
            row = as_dict(row)
            scores[row.get('cve')] = {
                'epss': to_float(row.get('epss')), 'percentile': to_float(row.get('percentile')),
                'date': row.get('date'),
            }
    run.out['epss'] = {'ok': run.epss_ok, 'scores': scores}
    for item in run.out['items']:
        found = [scores[c] for c in item['cves'] if c in scores]
        item['epss'] = max(found, key=lambda s: s['epss'] or 0.0) if found else None


def run_check(root: str) -> int:
    """Run the whole check for the repository at ``root`` and write deps.json."""
    audit_dir = Path(root) / '.appsec-audit'
    coverage = read_json(audit_dir / 'coverage.json')
    if not isinstance(coverage, dict):
        raise ValueError('cannot read .appsec-audit/coverage.json (run inventory.py first)')
    run = Run(coverage, utc_now_iso())
    out = run.out

    run.query_osv()
    run.fetch_details()
    out['osv'] = {'url': net.redact_url(net.ENDPOINTS['osv']), 'queriedAt': run.now, 'ok': run.osv_ok,
                  'packagesQueried': len(run.packages) if run.osv_ok else 0}
    run.fetch_kev(audit_dir)
    score_epss(run, build_items(run))

    out['items'].sort(key=lambda item: item['id'])
    if not run.osv_ok:
        out['status'] = 'failed'
    elif not out['kev']['ok'] or not run.epss_ok:
        out['status'] = 'partial'
    with open(audit_dir / 'deps.json', 'w', encoding='utf-8', newline='') as handle:
        handle.write(json.dumps(out, indent=2, ensure_ascii=False))

    vulnerable = [p for p in out['packages'] if p['vulns']]
    kev_hits = [i for i in out['items'] if i['kev'] not in (None, 'unknown')]
    kev_tail = f" kev_catalog={out['kev']['catalogVersion']}" if out['kev']['ok'] else ''
    print(f"status={out['status']} packages={len(run.packages)} vulnerable_packages={len(vulnerable)} "
          f"advisories={len(run.details)} items={len(out['items'])} kev_matches={len(kev_hits)}{kev_tail}")
    for error in out['errors']:
        print(f"ERROR {error['source']}: {error.get('category')}: {error.get('hint')}")
    if out['status'] == 'failed':
        print('Dependency results are NOT CHECKED. Say so at the top of the report (SKILL.md rule 9). '
              'Run net-check.py to diagnose.')
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit status."""
    configure_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    root_arg = arg_value(args, '--root', os.getcwd())
    if root_arg is None:
        sys.stderr.write('Error: missing value after --root\n')
        return 1
    try:
        return run_check(os.path.abspath(root_arg))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f'Error: {exc}\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
