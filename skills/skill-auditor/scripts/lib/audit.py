"""Running audits: one skill, a folder of skills, or a zip; compare, finalize, and gates."""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any

from . import archive, report
from .catalog import RULESET_VERSION
from .ingest import SKIP_DIRS, ingest_dir, process_file, sorted_entries
from .model import SEVS, Ctx, FileItem, Finding, kind_of
from .skillcheck import analyze_skill
from .text import scan_re
from .util import (
    as_list,
    audited_size,
    get_key,
    name_sort_key,
    now_iso,
    read_audited_bytes,
    round_half_up,
)

__all__ = [
    'VERSION',
    'apply_compare',
    'audit_one',
    'audit_path',
    'evaluate_gates',
    'finalize',
]


VERSION: str = '1.0.0'

ZIP_ENTRY_MAX_OUTPUT: int = 8 * 1024 * 1024

DEFAULT_MAX_SKILLS: int = 32

DEFAULT_MAX_SCORE: int = 50

# Compare.
RE_BINARY_ARCHIVE: re.Pattern[str] = scan_re(r'\.(zip|jar|exe|dll|so|wasm|pyc|docx|xlsx|pptx|tar|gz|7z)$', 'i')

RE_ZIP_INPUT: re.Pattern[str] = scan_re(r'\.(zip|skill|jar)$', 'i')

RE_ZIP_LEADING: re.Pattern[str] = scan_re(r'^\.?\/')

RE_SKILL_MD_PATH: re.Pattern[str] = scan_re(r'(^|\/)SKILL\.md$')

RE_SKILL_MD_TAIL: re.Pattern[str] = scan_re(r'SKILL\.md$')

RE_EXT_TAIL: re.Pattern[str] = scan_re(r'\.\w+$')


def build_items(ctx: Ctx, root: str, opts: dict[str, Any]) -> list[FileItem]:
    """The files to process for one skill: virtual (zip), a single file, or a folder walk."""
    virtual = opts.get('_virtual')
    if virtual is not None:
        ctx.dir = root
        return [
            FileItem(rel=v['rel'], size=len(v['buf']), read=lambda b=v['buf']: b) for v in virtual
        ]
    single = opts.get('singleFile')
    if single:
        return [FileItem(rel=os.path.basename(single), size=audited_size(single),
                         read=lambda p=single: read_audited_bytes(p))]
    return ingest_dir(ctx, root)


def build_coverage(ctx: Ctx,
                   findings: list[Finding]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Coverage summary from the ledger; adds COV01 findings for files that were not inspected."""
    ledger = [x for x in ctx.ledger if x['status'] != 'excluded']
    inspected = sum(1 for x in ledger if x['status'] == 'inspected')
    partial = [x for x in ledger if x['status'] == 'partial']
    unins = [x for x in ledger if x['status'] == 'uninspected']
    total = len(ledger)
    budget_hit = any(f['id'] in ('COV02', 'COV03') for f in ctx.findings)
    coverage = {
        'total': total, 'inspected': inspected,
        'partial': [{'file': p['file'], 'reason': p['reason']} for p in partial],
        'uninspected': [{'file': p['file'], 'reason': p['reason']} for p in unins],
        'percent': round_half_up(100 * (inspected + 0.5 * len(partial)) / total) if total else 100,
        'complete': not partial and not unins and not budget_hit,
        'excluded': sum(1 for x in ctx.ledger if x['status'] == 'excluded'),
    }
    covered_ids = ('COV01', 'ART11', 'SUP08', 'ART02', 'ART15', 'ART06')
    for u in unins:
        if not any(f['file'] == u['file'] and f['id'] in covered_ids for f in findings):
            findings.append(report.enrich({
                'id': 'COV01', 'severity': 'medium', 'file': u['file'], 'line': 1,
                'evidence': u['reason'],
                'message': 'File not inspected', 'confidence': 0.9, 'context': 'prose',
                'surface': 'code',
            }))
    return coverage, ledger


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def ledger_entry(x: dict[str, Any]) -> dict[str, Any]:
    """One coverage-ledger row for the report: file, status, and the reason when there is one."""
    entry = {'file': x['file'], 'status': x['status']}
    if x['reason']:
        entry['reason'] = x['reason']
    return entry


def summarize_hosts(ctx: Ctx) -> list[dict[str, Any]]:
    """Hosts sorted by number of risk flags, then mention count."""
    hosts = [{'host': h['host'], 'flags': list(h['flags']), 'count': h['count'],
              'first': h['first']} for h in ctx.hosts.values()]
    return sorted(hosts, key=lambda h: (-len(h['flags']), -h['count']))


def audit_one(root: str, opts: dict[str, Any], siblings: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit a single skill and return its (not yet finalized) result."""
    ctx = Ctx(root, opts)
    ctx.zip_budget = {'members': 0, 'bytes': 0, 'start': time.time() * 1000}
    ctx.virtual_files = opts.get('_virtual')
    for item in build_items(ctx, root, opts):
        process_file(ctx, item)
    info = analyze_skill(ctx, siblings)

    seen: set[str] = set()
    findings: list[dict[str, Any]] = []
    for f in ctx.findings:
        key = f"{f['id']}|{f['file']}|{f['line']}|{f['evidence'][:60]}"
        if key not in seen:
            seen.add(key)
            findings.append(f)
    suppressed = list(ctx.suppressed)
    if suppressed:
        findings.append(report.enrich({
            'id': 'STR13', 'severity': 'medium', 'file': '(multiple)', 'line': 1,
            'message': 'Findings hidden by an inline suppression marker',
            'evidence': f'{len(suppressed)} suppressed; read each one', 'confidence': 0.9,
            'context': 'prose',
            'surface': 'instructions'}))
    coverage, ledger = build_coverage(ctx, findings)
    hosts = summarize_hosts(ctx)
    texts = ctx.texts
    snapshot = {
        'files': ctx.hashes, 'description': info.description, 'allowedTools': info.allowed_tools,
        'hooks': ctx.hook_summary or [], 'hosts': [h['host'] for h in hosts],
    }
    stats = {
        'files': coverage['total'],
        'scripts': sum(1 for r in texts if kind_of(r) in ('script', 'hook') and '!/' not in r),
        'references': sum(1 for r in texts if kind_of(r) == 'md'),
        **info.stats,
    }
    return {
        'path': root, 'name': info.name or ctx.skill_name, 'description': info.description,
        'stats': stats,
        'coverage': coverage,
        'files': [ledger_entry(x) for x in ledger],
        'findings': findings, 'suppressed': suppressed,
        'network': {'hosts': hosts},
        'dependencies': {'packages': len(info.packages), 'lookups': info.lookups},
        'images': ctx.images, 'snapshot': snapshot, '_declaredName': ctx.declared_name,
    }


def apply_compare(sk: dict[str, Any], prev_skill: dict[str, Any]) -> None:
    """Add DIF findings describing what changed since an earlier audit of the same skill."""
    p = prev_skill.get('snapshot')
    if not p:
        return
    cur = sk['snapshot']

    def add(f: dict[str, Any]) -> None:
        """Append an enriched DIF finding with the usual defaults."""
        sk['findings'].append(report.enrich({
            'line': 1, 'confidence': 0.9, 'context': 'prose', 'surface': 'instructions', **f}))

    p_files: dict[str, str] = p.get('files') or {}
    added = [f for f in cur['files'] if f not in p_files]
    removed = [f for f in p_files if f not in cur['files']]
    changed = [f for f in cur['files'] if f in p_files and p_files[f] != cur['files'][f]]
    p_tools = as_list(p.get('allowedTools'))
    new_tools = [t for t in cur['allowedTools'] if t not in p_tools]
    if new_tools:
        add({'id': 'DIF01', 'file': 'SKILL.md', 'evidence': 'new: ' + ', '.join(new_tools)})
    p_hooks = as_list(p.get('hooks'))
    new_hooks = [h for h in cur['hooks'] if h not in p_hooks]
    if new_hooks:
        add({'id': 'DIF02', 'file': 'hooks', 'evidence': ' ; '.join(new_hooks[:3])})
    scripts = [f for f in added + changed if kind_of(f) in ('script', 'hook')]
    if scripts:
        add({'id': 'DIF03', 'file': scripts[0],
             'evidence': f"{len(scripts)} script(s) added or changed: {', '.join(scripts[:4])}"})
    p_desc = p.get('description')
    if cur['description'] != p_desc:
        was = (p_desc or '')[:70]
        add(
            {'id': 'DIF04', 'file': 'SKILL.md',
             'evidence': f"was: {was} | now: {cur['description'][:70]}"}
        )
    p_hosts = as_list(p.get('hosts'))
    new_hosts = [h for h in cur['hosts'] if h not in p_hosts]
    if new_hosts:
        add({'id': 'DIF05', 'file': '(network)', 'evidence': ', '.join(new_hosts[:8])})
    binaries = [f for f in added if RE_BINARY_ARCHIVE.search(f)]
    if binaries:
        add({'id': 'DIF06', 'file': binaries[0], 'evidence': ', '.join(binaries)})
    sk['changes'] = {'added': added, 'removed': removed, 'modified': changed,
                     'newAllowedTools': new_tools, 'newHosts': new_hosts, 'newHooks': new_hooks}


def sev_index(sev: Any) -> int:
    """Position of a severity in SEVS (0 is the most severe); -1 for an unknown value."""
    return SEVS.index(sev) if sev in SEVS else -1


def finding_sort_key(f: dict[str, Any]) -> tuple[Any, ...]:
    """Order: severity, confidence (high first), file, line."""
    severity = sev_index(f.get('severity'))
    return severity, -f.get('confidence', 0), name_sort_key(f['file']), f['line']


def finalize(sk: dict[str, Any], opts: dict[str, Any],
             prev_skill: dict[str, Any] | None) -> dict[str, Any]:
    """Apply compare, baseline, and review data; then sort findings and compute counts and risk."""
    if prev_skill:
        apply_compare(sk, prev_skill)
    for f in sk['findings'] + sk['suppressed']:
        if not f.get('fingerprint'):
            report.enrich(f)
    if opts.get('baselineData'):
        b = report.apply_baseline(sk['findings'], opts['baselineData'])
        sk['findings'] = b['active']
        sk['suppressed'] = sk['suppressed'] + b['suppressed']
    if opts.get('reviewData'):
        sk['review'] = report.apply_review(sk['findings'], opts['reviewData'])
    sk['findings'].sort(key=finding_sort_key)
    sk['counts'] = {s: sum(1 for f in sk['findings'] if f.get('severity') == s) for s in SEVS}
    sk['risk'] = report.score(sk['findings'], sk['coverage'])
    sk.pop('_declaredName', None)
    if not opts.get('showSuppressed'):
        keys = ('id', 'file', 'line', 'severity', 'suppressedBy', 'reason', 'evidence')
        sk['suppressed'] = [{k: f[k] for k in keys if k in f} for f in sk['suppressed']]
    return sk


def find_skill_dirs(p: str, max_skills: int) -> list[str]:
    """Folders (up to five levels down) that contain a SKILL.md."""
    if os.path.exists(os.path.join(p, 'SKILL.md')):
        return [p]
    out: list[str] = []

    def rec(d: str, depth: int) -> None:
        """Search one directory level for skill folders."""
        if depth > 5 or len(out) >= max_skills:
            return
        try:
            ents = sorted_entries(d)
        except OSError:
            return
        for e in ents:
            if not e.is_dir(follow_symlinks=False) or e.name in SKIP_DIRS:
                continue
            full = os.path.join(d, e.name)
            if os.path.exists(os.path.join(full, 'SKILL.md')):
                if len(out) < max_skills:
                    out.append(full)
            else:
                rec(full, depth + 1)

    rec(p, 0)
    return out


def max_skills_limit(opts: dict[str, Any]) -> int:
    """The --max-skills limit (a missing or zero value means the default)."""
    return int(opts.get('maxSkills') or DEFAULT_MAX_SKILLS)


def read_zip_files(buf: bytes) -> list[dict[str, Any]]:
    """The readable members of a ZIP held in memory as {'rel', 'buf'} (nothing is extracted)."""
    files: list[dict[str, Any]] = []
    for e in archive.list_zip(buf).get('entries') or []:
        too_big = e['usize'] > archive.LIMITS['memberBytes'] * 8
        if e['name'].endswith('/') or e['flags'] & 1 or too_big:
            continue
        data = archive.read_entry(buf, e, ZIP_ENTRY_MAX_OUTPUT) if e['method'] in (0, 8) else None
        if data is not None:
            files.append({'rel': RE_ZIP_LEADING.sub('', e['name'], count=1), 'buf': data})
    return files


def inspect_whole_archive(buf: bytes, name: str) -> dict[str, Any]:
    """Container-level findings for the archive itself; a failing inspection is itself a finding."""
    budget = {'members': 0, 'bytes': 0, 'start': time.time() * 1000}
    try:
        whole = archive.inspect(buf, name, budget, 0)
        found = whole['findings']
        kind = whole['type']
    except Exception as exc:  # noqa: BLE001 - a malformed archive must not abort the audit
        kind = None
        found = [{'id': 'COV01', 'severity': 'medium', 'message': 'File not inspected',
                  'evidence': f'inspection failed: {type(exc).__name__}', 'confidence': 0.9}]
    return {
        'type': kind,
        'findings': [
            report.enrich({'file': name, 'line': 1, 'context': 'prose', 'surface': 'code', **f})
            for f in found],
    }


def plan_zip_runs(abs_path: str, opts: dict[str, Any],
                  result: dict[str, Any]) -> list[dict[str, Any]]:
    """Read a .zip/.skill/.jar into memory and group its files per SKILL.md folder."""
    buf = read_audited_bytes(abs_path)
    try:
        files = read_zip_files(buf)
    except Exception:  # noqa: BLE001 - a malformed archive is reported by inspect_whole_archive
        files = []
    roots = [RE_SKILL_MD_TAIL.sub('', f['rel']) for f in files if RE_SKILL_MD_PATH.search(f['rel'])]
    uniq = list(dict.fromkeys(roots))[:max_skills_limit(opts)] if roots else ['']
    default_label = RE_EXT_TAIL.sub('', os.path.basename(abs_path))
    runs = []
    for r in uniq:
        label = r[:-1] if r.endswith('/') else r
        runs.append({
            'root': abs_path,
            'virtual': [
                {'rel': f['rel'][len(r):], 'buf': f['buf']} for f in files if f['rel'].startswith(r)
            ],
            'label': label.split('/')[-1] or default_label,
        })
    result['container'] = inspect_whole_archive(buf, os.path.basename(abs_path))
    return runs


def audit_path(target: str, opts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Audit a skill folder, a folder of skills, a single file, or a .zip; return the result."""
    opts = opts or {}
    abs_path = os.path.abspath(target)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(abs_path)
    result: dict[str, Any] = {
        'tool': 'skill-auditor', 'version': VERSION, 'rulesetVersion': RULESET_VERSION,
        'python': sys.version.split()[0], 'generatedAt': now_iso(), 'target': abs_path,
        'skillCount': 0,
        'skills': [],
    }
    is_file = os.path.isfile(abs_path)
    runs: list[dict[str, Any]]
    if is_file and RE_ZIP_INPUT.search(abs_path):
        runs = plan_zip_runs(abs_path, opts, result)
    elif is_file:
        runs = [{'root': os.path.dirname(abs_path), 'single': abs_path}]
    else:
        dirs = find_skill_dirs(abs_path, max_skills_limit(opts))
        if not dirs:
            result['note'] = 'No SKILL.md found at or below the target.'
            dirs.append(abs_path)
            result['noSkill'] = True
        runs = [{'root': d} for d in dirs]
    if len(runs) >= max_skills_limit(opts):
        prefix = result['note'] + ' ' if result.get('note') else ''
        result['note'] = f'{prefix}Stopped at --max-skills {max_skills_limit(opts)}.'
    skills = run_audits(abs_path, runs, opts)
    names: dict[str, int] = {}
    for s in skills:
        names[s['name']] = names.get(s['name'], 0) + 1
    for s in skills:
        if names[s['name']] > 1:
            s['findings'].append(report.enrich({
                'id': 'STR12', 'file': 'SKILL.md', 'line': 1, 'evidence': s['name'],
                'confidence': 0.9,
                'context': 'prose', 'surface': 'instructions'}))
    compare = opts.get('compareData')
    prev: list[dict[str, Any]] | None = as_list(get_key(compare, 'skills')) if compare else None
    result['skills'] = [finalize(s, opts, pick_previous(prev, s)) for s in skills]
    result['skillCount'] = len(result['skills'])
    if 'container' in result:
        merge_container(result)
    result['gates'] = evaluate_gates(result, opts)
    return result


def pick_previous(prev: list[dict[str, Any]] | None, s: dict[str, Any]) -> dict[str, Any] | None:
    """The earlier report's entry for this skill (by name, or the only one)."""
    if prev is None:
        return None
    for p in prev:
        if isinstance(p, dict) and p.get('name') == s['name']:
            return p
    return prev[0] if len(prev) == 1 else None


def run_audits(abs_path: str, runs: list[dict[str, Any]],
               opts: dict[str, Any]) -> list[dict[str, Any]]:
    """Audit each planned run, remembering declared names so duplicates can be reported."""
    siblings: list[dict[str, Any]] = []
    skills: list[dict[str, Any]] = []
    for run in runs:
        is_virtual = run.get('virtual') is not None
        o = {
            **opts, 'singleFile': run.get('single'), '_virtual': run.get('virtual'),
            'virtualRoot': is_virtual,
        }
        sk = audit_one(run['label'] if is_virtual else run['root'], o, siblings)
        if is_virtual:
            sk['name'] = sk['name'] or run['label']
            sk['path'] = abs_path + '!/' + (run['label'] or '')
        siblings.append({'declaredName': sk.get('_declaredName')})
        skills.append(sk)
    return skills


def merge_container(result: dict[str, Any]) -> None:
    """Add the whole-archive findings to every skill found inside it and rescore."""
    for s in result['skills']:
        for f in result['container']['findings']:
            s['findings'].append(f)
        s['counts'] = {k: sum(1 for f in s['findings'] if f.get('severity') == k) for k in SEVS}
        s['risk'] = report.score(s['findings'], s['coverage'])


def evaluate_gates(result: dict[str, Any], o: dict[str, Any]) -> dict[str, Any]:
    """Check each skill against the configured gates."""
    failures: list[str] = []
    max_score = o['maxScore'] if o.get('maxScore') is not None else DEFAULT_MAX_SCORE
    for s in result['skills']:
        name = s['name']
        active = [
            f for f in s['findings'] if f.get('severity') != 'info' and not report.is_quality(f)
        ]
        if s['risk']['score'] > max_score:
            failures.append(f"{name}: risk score {s['risk']['score']} is over {max_score}")
        if o.get('failOnFindings') and active:
            failures.append(f'{name}: {len(active)} active finding(s)')
        if o.get('failOn'):
            i = sev_index(o['failOn'])
            n = sum(1 for f in s['findings'] if sev_index(f.get('severity')) <= i)
            if n:
                failures.append(f"{name}: {n} finding(s) at {o['failOn']} or above")
        if o.get('failOnIncomplete') and not s['coverage']['complete']:
            failures.append(f'{name}: coverage is incomplete')
        min_cov = o.get('minCoverage')
        if min_cov is not None and s['coverage']['percent'] < min_cov:
            failures.append(f"{name}: coverage {s['coverage']['percent']}% is under {min_cov}%")
        if o.get('requireReview'):
            rv = s.get('review')
            if not rv:
                failures.append(f'{name}: no review file supplied')
            elif rv['summary']['unreviewedHighCritical']:
                n = rv['summary']['unreviewedHighCritical']
                failures.append(f'{name}: {n} high or critical finding(s) have no review outcome')
    return {'passed': not failures, 'failures': failures, 'maxScore': max_score}
