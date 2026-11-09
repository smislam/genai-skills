#!/usr/bin/env python3
"""Render .appsec-audit/results.sarif (SARIF 2.1.0) from .appsec-audit/findings.json.

The SARIF is deterministic: same findings => byte-identical file.
Usage: python -I sarif.py [--root <repo>]
findings.json format: references/output.md, "findings.json".
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write .pyc files next to the scripts

if sys.version_info < (3, 12):
    sys.stderr.write(f'appsec-auditor needs Python 3.12 or newer; found {sys.version.split()[0]}\n')
    raise SystemExit(2)

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

# `python -I` drops the script directory from sys.path. Add only this script's own directory.
_HERE = str(Path(__file__).resolve().parent)
if not sys.path or sys.path[0] != _HERE:
    sys.path.insert(0, _HERE)

from lib.cliutil import arg_value, configure_streams, natural_key, read_json, sha256_hex  # noqa: E402

__all__ = ['main', 'render']

SEVERITY_SCORE = {'Critical': '9.5', 'High': '8.0', 'Medium': '5.5', 'Low': '2.0', 'Info': '0.5'}
LEVEL = {'Critical': 'error', 'High': 'error', 'Medium': 'warning', 'Low': 'note', 'Info': 'note'}
PRECISION = {'Confirmed': 'high', 'Likely': 'medium'}
FINDING_ID = re.compile(r'(F|C)-\d+', re.ASCII)  # same rule as the coverage gate
MAX_PROBLEMS_SHOWN = 10
NON_SLUG = re.compile(r'[^a-z0-9]+')
EDGE_DASH = re.compile(r'^-|-\Z')
LINE_SPLIT = re.compile(r'\r?\n')
WHITESPACE = re.compile(r'[\s\ufeff]+')


def text_of(value: Any) -> str:
    """Text form of a JSON scalar; whole numbers print without a decimal point."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def slug(value: Any) -> str:
    """Lower-case text reduced to dash-separated [a-z0-9] words, at most 60 characters."""
    return EDGE_DASH.sub('', NON_SLUG.sub('-', str(value).lower()))[:60]


def location_problems(locations: Any) -> list[str]:
    """What is wrong with a finding's ``locations`` list (empty when it is usable)."""
    if not isinstance(locations, list) or not locations:
        return ['needs at least one location']
    problems = []
    for index, loc in enumerate(locations, 1):
        if not isinstance(loc, dict) or not isinstance(loc.get('file'), str) or not loc['file']:
            problems.append(f'location {index} needs a repository-relative "file"')
        elif 'line' in loc and (not isinstance(loc['line'], int) or isinstance(loc['line'], bool) or loc['line'] < 1):
            problems.append(f'location {index} "line" must be a whole number of 1 or more')
    return problems


def finding_problems(finding: Any) -> list[str]:
    """What is wrong with one findings.json entry (empty when it is valid).

    The same fields the coverage gate requires, so a finding that renders here also passes there.
    """
    if not isinstance(finding, dict):
        return ['is not an object']
    problems = []
    if not isinstance(finding.get('id'), str) or not FINDING_ID.fullmatch(finding['id']):
        problems.append('"id" must look like F-1 (or C-1 for a chain)')
    if not isinstance(finding.get('title'), str) or not finding['title'].strip():
        problems.append('missing "title"')
    if finding.get('severity') not in SEVERITY_SCORE:
        problems.append(f'"severity" {finding.get("severity")!r} is not one of {", ".join(SEVERITY_SCORE)}')
    if finding.get('confidence') not in PRECISION:
        problems.append(f'"confidence" {finding.get("confidence")!r} is not one of {", ".join(PRECISION)}')
    return problems + location_problems(finding.get('locations'))


def check_findings(findings: Any) -> list[dict[str, Any]]:
    """Return the findings list, or raise ValueError naming every invalid entry and why."""
    if findings is None:
        return []
    if not isinstance(findings, list):
        raise ValueError('findings.json: "findings" must be a list')
    lines = []
    for index, finding in enumerate(findings, 1):
        label = finding.get('id') if isinstance(finding, dict) and isinstance(finding.get('id'), str) else f'entry {index}'
        lines += [f'{label}: {problem}' for problem in finding_problems(finding)]
    if lines:
        shown = lines[:MAX_PROBLEMS_SHOWN]
        more = f'\n  ... and {len(lines) - len(shown)} more' if len(lines) > len(shown) else ''
        raise ValueError(f'findings.json has {len(lines)} problem(s); fix them and re-run:\n  ' + '\n  '.join(shown) + more)
    return findings


def line_hash(root: str, loc: dict[str, Any]) -> str:
    """Fingerprint the normalized source line at a location, so the result survives line shifts."""
    content = ''
    line = loc.get('line') or 1
    try:
        with open(os.path.join(root, str(loc['file'])), 'rb') as handle:
            lines = LINE_SPLIT.split(handle.read().decode('utf-8', 'replace'))
        if isinstance(line, int) and 1 <= line <= len(lines):
            content = lines[line - 1]
    except (OSError, ValueError):
        pass  # file not in the tree (for example a history-only secret)
    return sha256_hex(f"{loc['file']}|{WHITESPACE.sub(' ', content).strip()}")[:32]


def physical(loc: dict[str, Any]) -> dict[str, Any]:
    """A SARIF physicalLocation for a finding location."""
    region: dict[str, Any] = {'startLine': loc.get('line') or 1}
    if loc.get('endLine'):
        region['endLine'] = loc['endLine']
    uri = str(loc['file']).replace('\\', '/')
    return {'physicalLocation': {'artifactLocation': {'uri': uri, 'uriBaseId': '%SRCROOT%'}, 'region': region}}


def build_rule(finding: dict[str, Any], rule_id: str) -> dict[str, Any]:
    """The SARIF rule descriptor for a finding."""
    tags = ['security']
    if finding.get('cwe'):
        tags.append(f"external/cwe/{finding['cwe'].lower()}")
    if finding.get('owasp'):
        tags.append(f"owasp-top10-2025/{finding['owasp'].split(':')[0]}")
    if finding.get('cvssScore'):
        severity = text_of(finding['cvssScore'])
    else:
        severity = SEVERITY_SCORE.get(finding.get('severity'), '5.5')
    fix = finding.get('fix') or ''
    return {
        'id': rule_id,
        'shortDescription': {'text': finding.get('title')},
        'fullDescription': {'text': finding.get('message') or finding.get('title')},
        'help': {'text': fix, 'markdown': fix},
        'properties': {
            'security-severity': severity,
            'precision': PRECISION.get(finding.get('confidence'), 'medium'),
            'tags': tags,
        },
    }


def build_result(root: str, finding: dict[str, Any], rule_id: str, index: int) -> dict[str, Any]:
    """The SARIF result for a finding."""
    locs = [loc for loc in finding.get('locations') or [] if isinstance(loc, dict) and loc.get('file')]
    if locs:
        fingerprint = line_hash(root, locs[0])
    else:
        fingerprint = sha256_hex(f"{finding['id']}{finding.get('title')}")[:32]
    properties = {
        'findingId': finding['id'], 'severity': finding.get('severity'), 'confidence': finding.get('confidence'),
    }
    result: dict[str, Any] = {
        'ruleId': rule_id,
        'ruleIndex': index,
        'level': LEVEL.get(finding.get('severity'), 'warning'),
        'message': {'text': finding.get('message') or finding.get('title')},
        'locations': [physical(loc) for loc in locs[:1]],
        'partialFingerprints': {'primaryLocationLineHash/v1': fingerprint},
        'properties': properties,
    }
    if len(locs) > 1:
        result['relatedLocations'] = [{'id': i + 1, **physical(loc)} for i, loc in enumerate(locs[1:])]
    flow = finding.get('path')
    if isinstance(flow, list) and flow:
        steps = [{'location': {**physical(p), 'message': {'text': p.get('note') or ''}}}
                 for p in flow if isinstance(p, dict) and p.get('file')]
        result['codeFlows'] = [{'threadFlows': [{'locations': steps}]}]
    if finding.get('cvss'):
        properties['cvssVector'] = finding['cvss']
    if isinstance(finding.get('chain'), list) and finding['chain']:
        properties['chainMembers'] = finding['chain']
    return result


def render(root: str) -> dict[str, Any]:
    """Build the SARIF document for the repository at ``root`` (raises when findings.json is unusable)."""
    audit_dir = Path(root) / '.appsec-audit'
    document = read_json(audit_dir / 'findings.json')
    plugin = read_json(Path(_HERE).parent / '.claude-plugin' / 'plugin.json')
    if document is None or not isinstance(plugin, dict):
        raise ValueError('cannot read .appsec-audit/findings.json or .claude-plugin/plugin.json')
    coverage = read_json(audit_dir / 'coverage.json')
    coverage = coverage if isinstance(coverage, dict) else {}

    findings = check_findings(document.get('findings') if isinstance(document, dict) else None)
    kept = [f for f in findings if f.get('severity') != 'Info' or f.get('sarif') is not False]
    rules: list[dict[str, Any]] = []
    rule_index: dict[str, int] = {}
    results = []
    for finding in sorted(kept, key=lambda f: natural_key(f['id'])):
        rule_id = finding.get('ruleId') or (
            f"appsec/{slug(finding.get('cwe') or 'cwe-unknown')}-{slug(finding.get('title'))}")
        if rule_id not in rule_index:
            rule_index[rule_id] = len(rules)
            rules.append(build_rule(finding, rule_id))
        results.append(build_result(root, finding, rule_id, rule_index[rule_id]))

    driver = {'name': 'appsec-auditor', 'version': plugin.get('version'),
              'informationUri': 'https://github.com/smislam/genai-skills', 'rules': rules}
    run: dict[str, Any] = {'tool': {'driver': driver}}
    commit = coverage.get('commit')
    if commit and commit != 'none':
        uri = 'file:///' + re.sub(r'^/', '', root.replace('\\', '/'))
        run['versionControlProvenance'] = [{'repositoryUri': uri, 'revisionId': commit}]
    run['properties'] = {key: coverage[key] for key in ('rulesVersion', 'depth') if key in coverage}
    run['results'] = results
    return {'version': '2.1.0', '$schema': 'https://json.schemastore.org/sarif-2.1.0.json', 'runs': [run]}


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit status."""
    configure_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    root_arg = arg_value(args, '--root', os.getcwd())
    if root_arg is None:
        sys.stderr.write('Error: missing value after --root\n')
        return 1
    root = os.path.abspath(root_arg)
    try:
        sarif = render(root)
        with open(Path(root) / '.appsec-audit' / 'results.sarif', 'w', encoding='utf-8', newline='') as handle:
            handle.write(json.dumps(sarif, indent=2, ensure_ascii=False) + '\n')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        sys.stderr.write(f'Error: {exc}\n')
        return 1
    run = sarif['runs'][0]
    print(f"results.sarif: {len(run['results'])} results, {len(run['tool']['driver']['rules'])} rules")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
