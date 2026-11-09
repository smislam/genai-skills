#!/usr/bin/env python3
"""The coverage gate.

Compares the deterministic checklist (coverage.json from inventory.py, deps.json from deps.py)
with the AI's decisions (ledger.json), the read log (reads.jsonl, written by the track hook),
and the report. The audit is complete only when every checklist item has a valid decision,
every entry-point file was read, and the report and SARIF exist and carry the current coverage
summary.

Usage: python -I coverage-check.py [--root <repo>] [--json] [--summary]
                                   [--list [--undecided] [--kind <kind>]]
  --summary  print the coverage block to paste into report.md (deterministic)

The importable API is ``check(root) -> dict`` with the keys complete, gaps, summary,
fingerprint, undecidedIds.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write .pyc files next to the scripts

if sys.version_info < (3, 12):
    sys.stderr.write(f'appsec-auditor needs Python 3.12 or newer; found {sys.version.split()[0]}\n')
    raise SystemExit(2)

import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

# `python -I` drops the script directory from sys.path. Add only this script's own directory.
_HERE = str(Path(__file__).resolve().parent)
if not sys.path or sys.path[0] != _HERE:
    sys.path.insert(0, _HERE)

from lib import pathglob  # noqa: E402
from lib.cliutil import arg_value, configure_streams, read_json, run_git  # noqa: E402

__all__ = ['check', 'main']

STATUSES = ['finding', 'false_positive', 'needs_review', 'reviewed', 'not_applicable']
KINDS = ['entrypoint', 'pattern', 'secret', 'secret-history', 'dependency']
SEVERITIES = ['Critical', 'High', 'Medium', 'Low', 'Info']
CONFIDENCES = ['Confirmed', 'Likely']
FINDING_ID = re.compile(r'(F|C)-\d+', re.ASCII)
NOT_CHECKED = re.compile(r'not checked', re.IGNORECASE | re.ASCII)
UNDECIDED = object()  # status marker for "items with no decision"
ANY_STATUS = object()  # status marker for "all items"
SAMPLE_MAX = 10


def as_dict(value: Any) -> dict[str, Any]:
    """The value if it is a JSON object, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """The value if it is a JSON array, otherwise an empty list."""
    return value if isinstance(value, list) else []


def path_key(path: str) -> str | None:
    """Normalize a path for comparison (case-insensitive on Windows); None if unusable."""
    try:
        return os.path.normcase(os.path.abspath(path))
    except (ValueError, OSError):
        return None


def is_group(entry: dict[str, Any]) -> bool:
    """Whether a ledger entry has a ``match`` (an empty object still counts, and is then invalid)."""
    return entry.get('match') not in (None, False, 0, '')


def entry_error(entry: Any) -> str | None:
    """Validate one ledger entry; return an error string or None."""
    entry = as_dict(entry)
    status = entry.get('status')
    if status not in STATUSES:
        return f'unknown status "{"undefined" if status is None else status}"'
    if status == 'finding' and not FINDING_ID.fullmatch(str(entry.get('finding') or '')):
        return 'a "finding" decision needs a finding ID like F-03 or C-1'
    if status != 'finding' and len(str(entry.get('reason') or '').strip()) < 10:
        return f'a "{status}" decision needs a reason of at least 10 characters'
    if is_group(entry):
        match = as_dict(entry['match'])
        if status == 'finding':
            return 'group entries ("match") cannot be findings; record each finding by item ID'
        if match.get('kind') == 'entrypoint':
            return 'entry points must each be decided by ID, not by a group entry'
        if not (match.get('rule') or match.get('kind') or match.get('path')):
            return 'a group entry needs at least one of match.rule, match.kind, match.path'
    elif not entry.get('id'):
        return 'an entry needs an "id" or a "match"'
    return None


def group_matches(entry: dict[str, Any], item: dict[str, Any]) -> bool:
    """Whether a group ledger entry covers a checklist item."""
    match = as_dict(entry.get('match'))
    if item.get('kind') == 'entrypoint':
        return False
    if match.get('rule') and match['rule'] != item.get('rule'):
        return False
    if match.get('kind') and match['kind'] != item.get('kind'):
        return False
    if match.get('path'):
        file, pattern = str(item.get('file') or ''), str(match['path'])
        if not (pathglob.matches(file, pattern) or file.startswith(pattern)):
            return False
    return True


def read_reads(audit_dir: Path) -> list[str]:
    """The paths in reads.jsonl (lines that are not valid JSON objects are ignored)."""
    reads: list[str] = []
    try:
        with open(audit_dir / 'reads.jsonl', 'rb') as handle:
            text = handle.read().decode('utf-8', 'replace')
    except OSError:
        return reads  # no reads yet
    for line in text.split('\n'):
        try:
            path = as_dict(json.loads(line)).get('path')
        except ValueError:
            continue
        if isinstance(path, str):
            reads.append(path)
    return reads


class Gaps:
    """Collects gap records in the order they are found."""

    def __init__(self) -> None:
        """Start with no gaps."""
        self.items: list[dict[str, Any]] = []

    def add(self, kind: str, message: str, sample: list[Any] | None = None,
            count: int | None = None) -> None:
        """Record a gap; ``count`` defaults to the sample size, or 1 for an empty sample."""
        sample = sample or []
        self.items.append({
            'type': kind, 'message': message, 'count': count if count is not None else (len(sample) or 1),
            'sample': sample[:SAMPLE_MAX],
        })


def split_entries(entries: list[Any], gaps: Gaps) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Validate ledger entries; return (entries by ID, group entries)."""
    invalid: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    groups: list[dict[str, Any]] = []
    for i, entry in enumerate(entries):
        err = entry_error(entry)
        if err:
            entry_id = as_dict(entry).get('id')
            invalid.append(f"entry {i}{f' ({entry_id})' if entry_id else ''}: {err}")
        elif is_group(entry):
            groups.append(entry)
        else:
            by_id[str(entry['id'])] = entry
    if invalid:
        gaps.add('ledger-invalid', f'{len(invalid)} ledger entries are invalid.', invalid, len(invalid))
    return by_id, groups


def decide(items: list[dict[str, Any]], by_id: dict[str, dict[str, Any]],
           groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map item ID to its ledger entry: an ID entry wins over a group entry."""
    decision: dict[str, dict[str, Any]] = {}
    for item in items:
        entry = by_id.get(item['id']) or next((g for g in groups if group_matches(g, item)), None)
        if entry is not None:
            decision[item['id']] = entry
    return decision


def describe_item(item: dict[str, Any]) -> str:
    """The one-line description of an undecided item."""
    line = f":{item['line']}" if item.get('line') else ''
    rule = item.get('rule') or item.get('vuln') or ''
    return f"{item['id']} {item.get('kind')} {rule} {item.get('file') or ''}{line}".strip()


def count_items(items: list[dict[str, Any]], decision: dict[str, dict[str, Any]], kind: str, status: Any) -> int:
    """Number of items of ``kind`` with the given status (ANY_STATUS, UNDECIDED, or a status name)."""
    total = 0
    for item in items:
        if item.get('kind') != kind:
            continue
        if status is ANY_STATUS:
            total += 1
        elif status is UNDECIDED:
            total += item['id'] not in decision
        else:
            total += decision.get(item['id'], {}).get('status') == status
    return total


def render_summary(coverage: dict[str, Any], deps: dict[str, Any], items: list[dict[str, Any]],
                   decision: dict[str, dict[str, Any]], entry_files: list[str], unread: list[str],
                   fingerprint: str, hooks_off: bool) -> str:
    """The coverage block the report must contain."""
    rows = []
    for kind in KINDS:
        n = count_items(items, decision, kind, ANY_STATUS)
        if n:
            cells = [count_items(items, decision, kind, s) for s in
                     ('finding', 'false_positive', 'needs_review', 'reviewed', 'not_applicable', UNDECIDED)]
            rows.append(f"| {kind} | {n} | {' | '.join(str(c) for c in cells)} |")
    if hooks_off:
        read_line = ('**Entry-point files read:** **not enforced** (the guardrail hooks were not active, so reads '
                     f'were not logged; {len(entry_files)} entry-point files were to be opened by instruction only)')
    else:
        read_line = f'**Entry-point files read:** {len(entry_files) - len(unread)} of {len(entry_files)}'
    kev = as_dict(deps.get('kev'))
    kev_text = f"catalog {kev.get('catalogVersion')}" if kev.get('ok') else '**unknown**'
    osv_text = 'queried' if as_dict(deps.get('osv')).get('ok') else '**not checked**'
    epss_text = 'scored' if as_dict(deps.get('epss')).get('ok') else '**not scored**'
    files = as_dict(coverage.get('files'))
    lines = [
        f'<!-- appsec-coverage v1 fingerprint={fingerprint} -->',
        f"**Checklist:** commit `{str(coverage.get('commit'))[:12]}` \u00b7 rules {coverage.get('rulesVersion')} "
        f"\u00b7 depth {coverage.get('depth')} \u00b7 {files.get('count', 0)} files scanned \u00b7 "
        f"{len(as_list(coverage.get('packages')))} packages "
        f"({len(as_list(coverage.get('unresolved')))} not resolvable)",
        '',
        '| Checklist | Items | Findings | False positives | Needs review | Reviewed | Not applicable | Undecided |',
        '|---|---|---|---|---|---|---|---|',
        *rows,
        '',
        read_line,
        f'**Dependency data:** OSV.dev {osv_text}; KEV {kev_text}; EPSS {epss_text}',
        '<!-- /appsec-coverage -->',
    ]
    return '\n'.join(lines)


def ledger_findings(entries: list[Any]) -> list[str]:
    """Distinct finding IDs of the ledger's finding decisions, sorted."""
    return sorted({str(e['finding']) for e in entries
                   if isinstance(e, dict) and e.get('status') == 'finding' and e.get('finding')})


def check_report(report: str, fingerprint: str, ids: list[str], gaps: Gaps) -> None:
    """The report must carry the current summary and every ledger finding ID."""
    if f'<!-- appsec-coverage v1 fingerprint={fingerprint} -->' not in report:
        gaps.add('summary', "report.md doesn't contain the current coverage summary. Run coverage-check.py --summary "
                 'and paste its output into the Coverage section (re-paste after any ledger change).')
    missing = [f for f in ids if not re.search(rf'\b{re.escape(f)}\b', report, re.ASCII)]
    if missing:
        gaps.add('report-findings', f"{len(missing)} finding IDs from the ledger don't appear in report.md.",
                 missing, len(missing))


def check_findings(findings_doc: Any, ids: list[str], gaps: Gaps) -> None:
    """findings.json must exist, cover every ledger finding, and be well formed."""
    if not findings_doc:
        gaps.add('findings', 'No findings.json. Write it (format in references/output.md), then run sarif.py.')
        return
    listing = as_list(as_dict(findings_doc).get('findings'))
    present = {str(as_dict(f).get('id')) for f in listing}
    missing = [f for f in ids if f not in present]
    if missing:
        gaps.add('findings', f'{len(missing)} finding IDs used in the ledger are missing from findings.json.',
                 missing, len(missing))
    bad = [f for f in listing if not valid_finding(f)]
    if bad:
        gaps.add('findings', f'{len(bad)} entries in findings.json lack id, title, severity, confidence '
                 '(Confirmed or Likely), or a location.', [as_dict(f).get('id') or '?' for f in bad], len(bad))


def valid_finding(finding: Any) -> bool:
    """Whether a findings.json entry has an ID, title, severity, confidence, and a location."""
    f = as_dict(finding)
    return bool(FINDING_ID.fullmatch(str(f.get('id') or '')) and f.get('title')
                and f.get('severity') in SEVERITIES and f.get('confidence') in CONFIDENCES
                and isinstance(f.get('locations'), list) and f['locations'])


def render_sarif(root: str) -> Any:
    """Render the expected SARIF with sarif.py (loaded by path, so this file's name needs no import)."""
    spec = importlib.util.spec_from_file_location('appsec_sarif', Path(_HERE) / 'sarif.py')
    if spec is None or spec.loader is None:
        raise ImportError('cannot load sarif.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render(root)


def check_sarif(root: str, audit_dir: Path, findings_doc: Any, gaps: Gaps) -> None:
    """results.sarif must be exactly what sarif.py renders from the current findings.json."""
    sarif = read_json(audit_dir / 'results.sarif')
    if not sarif:
        gaps.add('sarif', 'No valid results.sarif yet. Run sarif.py.')
    elif findings_doc:
        try:
            expected = render_sarif(root)
        except Exception:  # noqa: BLE001 - any failure is already reported as a findings gap
            return
        if json.loads(json.dumps(expected)) != sarif:
            gaps.add('sarif', "results.sarif doesn't match findings.json. Re-run sarif.py; "
                     "don't edit the SARIF by hand.")


def find_unread(root: str, audit_dir: Path, items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Return (entry-point files, those never opened with the Read tool)."""
    entry_files = sorted({str(it.get('file')) for it in items if it.get('kind') == 'entrypoint'})
    read_keys = {path_key(r) for r in read_reads(audit_dir)}
    return entry_files, [f for f in entry_files if path_key(os.path.join(root, f)) not in read_keys]


def compute_fingerprint(coverage: dict[str, Any], items: list[dict[str, Any]],
                        decision: dict[str, dict[str, Any]]) -> str:
    """A short digest of the checklist, the decisions, the commit, and the rules version."""
    statuses = sorted(f"{it['id']}={decision.get(it['id'], {}).get('status') or '-'}" for it in items)
    digest = hashlib.sha256()
    digest.update('\n'.join(statuses).encode('utf-8'))
    digest.update((str(coverage.get('commit')) + str(coverage.get('rulesVersion'))).encode('utf-8'))
    return digest.hexdigest()[:16]


def check_inputs(root: str, audit_dir: Path, coverage: dict[str, Any], gaps: Gaps) -> dict[str, Any]:
    """Flag a stale coverage.json or a missing deps.json; return the parsed deps.json (or {})."""
    commit = coverage.get('commit')
    code, head_out = run_git(root, ['rev-parse', 'HEAD'])
    head = head_out.strip()
    if code == 0 and commit and commit != 'none' and head != commit:
        gaps.add('stale', f"coverage.json was built for commit {str(commit)[:12]}, but HEAD is {head[:12]}. "
                 'Re-run inventory.py.')
    deps = read_json(audit_dir / 'deps.json')
    if as_list(coverage.get('packages')) and not deps:
        gaps.add('deps', 'No deps.json. Run deps.py to check dependencies against OSV.dev and KEV.')
    return as_dict(deps)


def check(root: str) -> dict[str, Any]:
    """Run the coverage gate for the repository at ``root``."""
    audit_dir = Path(root) / '.appsec-audit'
    gaps = Gaps()
    coverage = as_dict(read_json(audit_dir / 'coverage.json'))
    if not coverage:
        gaps.add('inventory', 'No coverage.json. Run inventory.py first; it builds the checklist.')
        return {'complete': False, 'gaps': gaps.items, 'summary': '', 'fingerprint': '', 'undecidedIds': []}
    deps = check_inputs(root, audit_dir, coverage, gaps)
    items = [it for it in as_list(coverage.get('items')) + as_list(deps.get('items')) if isinstance(it, dict)]
    entries = as_list(as_dict(read_json(audit_dir / 'ledger.json')).get('entries'))
    by_id, groups = split_entries(entries, gaps)

    known = {it['id'] for it in items}
    unknown_ids = [i for i in by_id if i not in known]
    if unknown_ids:
        gaps.add('ledger-unknown', f'{len(unknown_ids)} ledger entries refer to IDs not in the current checklist '
                 '(stale or mistyped).', unknown_ids, len(unknown_ids))
    decision = decide(items, by_id, groups)
    undecided = [it for it in items if it['id'] not in decision]
    if undecided:
        gaps.add('undecided', f'{len(undecided)} checklist items have no decision in ledger.json.',
                 [describe_item(it) for it in undecided], len(undecided))

    entry_files, unread = find_unread(root, audit_dir, items)
    # Without the track hook nothing logs reads, so the check can't be enforced. The audit
    # records "hooks": false in state.json, and the summary then says so instead of failing.
    hooks_off = as_dict(read_json(audit_dir / 'state.json')).get('hooks') is False
    if unread and not hooks_off:
        gaps.add('unread', f'{len(unread)} entry-point files were never opened with the Read tool.',
                 unread, len(unread))

    report_path = audit_dir / 'report.md'
    report = report_path.read_bytes().decode('utf-8', 'replace') if report_path.exists() else None
    if deps.get('status') == 'failed' and report is not None and not NOT_CHECKED.search(report):
        gaps.add('deps-failed', "deps.py could not reach OSV.dev, but report.md doesn't say dependency results are "
                 '"not checked".')

    fingerprint = compute_fingerprint(coverage, items, decision)
    summary = render_summary(coverage, deps, items, decision, entry_files, unread, fingerprint, hooks_off)
    ids = ledger_findings(entries)
    if report is None:
        gaps.add('report', 'No report.md yet.')
    else:
        check_report(report, fingerprint, ids, gaps)
    findings_doc = read_json(audit_dir / 'findings.json')
    check_findings(findings_doc, ids, gaps)
    check_sarif(root, audit_dir, findings_doc, gaps)
    return {'complete': not gaps.items, 'gaps': gaps.items, 'summary': summary, 'fingerprint': fingerprint,
            'undecidedIds': [it['id'] for it in undecided]}


def list_items(root: str, args: list[str], undecided_ids: list[str]) -> None:
    """Compact checklist view: --list [--undecided] [--kind <kind>]."""
    audit_dir = Path(root) / '.appsec-audit'
    cov, deps = as_dict(read_json(audit_dir / 'coverage.json')), as_dict(read_json(audit_dir / 'deps.json'))
    wanted_kind = arg_value(args, '--kind')
    undecided = set(undecided_ids)
    for item in as_list(cov.get('items')) + as_list(deps.get('items')):
        if '--kind' in args and item.get('kind') != wanted_kind:
            continue
        if '--undecided' in args and item.get('id') not in undecided:
            continue
        where = f"{item['file']}{f':{item['line']}' if item.get('line') else ''}" if item.get('file') else ''
        if item.get('kind') == 'dependency':
            cves = ','.join(str(c) for c in item.get('cves') or [])
            what = f"{item.get('package')}@{item.get('version')} {item.get('vuln')} {cves} {item.get('severity') or ''}"
        else:
            what = f"{item.get('rule')} | {item.get('excerpt') or ''}"
        print(f"{item.get('id')}  {str(item.get('kind')).ljust(14)} {where}  {what}"[:240])


def print_text(result: dict[str, Any]) -> None:
    """The default human-readable report."""
    gaps = result['gaps']
    print('Coverage complete.' if result['complete'] else f'Coverage INCOMPLETE: {len(gaps)} gap types.')
    for gap in gaps:
        print(f"- [{gap['type']}] {gap['message']}")
        for sample in gap['sample']:
            print(f'    {sample}')
        if gap['sample'] and gap['count'] > len(gap['sample']):
            print(f"    \u2026 and {gap['count'] - len(gap['sample'])} more")


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
        result = check(root)
        if '--list' in args:
            list_items(root, args, result['undecidedIds'])
        elif '--summary' in args:
            sys.stdout.write(result['summary'] + '\n')
        elif '--json' in args:
            sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        else:
            print_text(result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f'Error: {exc}\n')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
