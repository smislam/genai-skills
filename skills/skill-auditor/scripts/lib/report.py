"""Scoring, baselines, AI-review merging, and output formats (Markdown, terminal, SARIF 2.1.0)."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from .catalog import META, RULESET_VERSION
from .util import as_list, as_text, error_text, get_key, now_iso, parse_json

__all__ = [
    'POINTS', 'PROTECTED', 'SEV', 'apply_baseline', 'apply_review', 'enrich', 'fingerprint',
    'glob_to_re',
    'is_quality', 'load_baseline', 'make_baseline', 'markdown', 'sarif', 'score', 'terminal',
]

SEV: list[str] = ['critical', 'high', 'medium', 'low', 'info']
POINTS: dict[str, int] = {'critical': 40, 'high': 22, 'medium': 4, 'low': 1, 'info': 0}
QUALITY_CATS: frozenset[str] = frozenset({'structure', 'quality', 'portability'})
QUALITY_IDS: frozenset[str] = frozenset({'TRG04', 'TRG05', 'STR12'})
# Findings from structural facts. A reviewer cannot dismiss these on judgment alone.
PROTECTED: frozenset[str] = frozenset({
    'SUP08', 'SUP09', 'SUP10', 'ART01', 'ART02', 'ART06', 'ART09', 'ART11', 'ART13', 'COV03',
    'HKS12', 'HKS13', 'HKS14', 'INJ02',
})
REVIEW_OUTCOMES: tuple[str, ...] = ('confirmed', 'dismissed', 'low-confidence', 'needs-user')
MIN_BASELINE_REASON = 8
MIN_DISMISSAL_REASON = 10
SCORE_NOTE = ('Mechanical score only. The audit verdict comes from reading the findings; '
              'this number is an input.')

# A run of whitespace including the Unicode spaces and the BOM, so evidence fingerprints do not
# change
# when a hostile file swaps a space for a look-alike.
_RE_WS_RUN = re.compile(
    r'[ \t\n\v\f\r\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+')
_RE_GLOB_SPECIAL = re.compile(r'[.+^${}()|\[\]\\]')
_RE_NON_ALNUM_RUN = re.compile(r'[^A-Za-z0-9]+')
_RE_SPACE_WORD = re.compile(r' (\w)', re.ASCII)


def fingerprint(f: dict[str, Any]) -> str:
    """Stable 24-hex fingerprint of a finding: rule set, id, file, and normalized evidence."""
    evidence = _RE_WS_RUN.sub(' ', as_text(f.get('evidence') or '')).strip()[:200]
    parts = [RULESET_VERSION, as_text(f.get('id') or ''), as_text(f.get('file') or ''), evidence]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def enrich(f: dict[str, Any]) -> dict[str, Any]:
    """Attach catalog metadata and the fingerprint to a finding (in place).

    A finding that arrives without a severity gets the one from the catalog (medium when the id is
    unknown), so every finding can be scored and rendered.
    """
    m = META.get(f.get('id')) or [
        f.get('message') or f.get('id'), 'other', f.get('severity'), None, None, '',
    ]
    if not f.get('severity'):
        f['severity'] = m[2] or 'medium'
    f['name'] = m[0]
    f['category'] = m[1]
    f['cwe'] = m[3]
    f['owasp'] = m[4]
    f['fix'] = m[5]
    f['fingerprint'] = fingerprint(f)
    return f


def is_quality(f: dict[str, Any]) -> bool:
    """True for structure, quality, and portability findings, which do not add risk."""
    return f.get('category') in QUALITY_CATS or f.get('id') in QUALITY_IDS


def _review_outcome(f: dict[str, Any]) -> Any:
    """The review outcome recorded on a finding, or None."""
    return get_key(f.get('review'), 'outcome')


def _is_dismissed_unprotected(f: dict[str, Any]) -> bool:
    """True when a reviewer dismissal is honored for this finding."""
    return _review_outcome(f) == 'dismissed' and f['id'] not in PROTECTED


def _weight(f: dict[str, Any]) -> float:
    """Risk weight of one finding: severity points times confidence, adjusted for surface/review."""
    points = POINTS.get(f.get('severity'), POINTS['medium'])
    w = points * (f.get('confidence') or 0.7)
    if f.get('surface') in ('code', 'hook'):
        w *= 1.25
    if _review_outcome(f) == 'low-confidence':
        w *= 0.5
    return w


def score(findings: list[dict[str, Any]], coverage: dict[str, Any] | None) -> dict[str, Any]:
    """Compute the mechanical risk score (0 to 100), its band, and the recommendation."""
    groups: dict[str, list[float]] = {}
    for f in findings:
        if is_quality(f) or f['id'].startswith('SEM12') or _is_dismissed_unprotected(f):
            continue
        groups.setdefault(f['id'] + '|' + f['file'], []).append(_weight(f))
    raw = 0.0
    for ws in groups.values():
        ws.sort(reverse=True)
        rest = 0.0
        for x in ws[1:]:  # plain left-to-right addition; sum() would round differently in 3.12
            rest += x
        raw += min(ws[0] + 0.25 * rest, ws[0] * 2)
    # Saturating curve: the first serious finding moves the score a lot, a pile of minor ones
    # cannot reach the top alone.
    total = math.floor(100 * (1 - math.exp(-raw / 90)) + 0.5)
    hard_critical = any(
        f.get('severity') == 'critical' and not is_quality(f)
        and (f.get('confidence') or 0) >= 0.7 and not _is_dismissed_unprotected(f)
        for f in findings)
    if hard_critical:
        total = max(total, 85)
    band = (
        'critical' if total >= 80 else 'high' if total >= 50 else 'medium' if total >= 20 else 'low'
    )
    rec = 'DO_NOT_INSTALL' if total >= 50 else 'CAUTION' if total >= 20 else 'SAFE'
    reasons: list[str] = []
    if coverage and not coverage.get('complete') and rec == 'SAFE':
        rec = 'CAUTION'
        reasons.append(
            f"analysis incomplete: {len(coverage['uninspected'])} file(s) not fully inspected"
        )
    return {
        'score': total, 'severity': band, 'recommendation': rec, 'reasons': reasons,
        'note': SCORE_NOTE,
    }


# ---------- baselines ----------
def glob_to_re(glob: Any) -> re.Pattern[str]:
    """Compile a glob (* and ?) to a case-insensitive whole-string regex."""
    escaped = _RE_GLOB_SPECIAL.sub(lambda m: '\\' + m.group(0), str(glob))
    return re.compile(escaped.replace('*', '.*').replace('?', '.') + r'\Z', re.IGNORECASE)


def _check_baseline_entries(entries: Any) -> None:
    """Raise ValueError unless every baseline entry is well formed."""
    if entries is None:
        return
    if not isinstance(entries, list):
        raise ValueError('baseline "entries" must be an array')
    for e in entries:
        if not isinstance(e, dict):
            raise ValueError('every baseline entry must be an object')
        if len(as_text(e.get('reason') or '').strip()) < MIN_BASELINE_REASON:
            raise ValueError(
                f'every baseline entry needs a reason of at least {MIN_BASELINE_REASON} characters'
            )
        if not e.get('fingerprint') and not e.get('rule'):
            raise ValueError('baseline entry needs a "fingerprint" or a "rule" object')


def load_baseline(file: str | Path) -> dict[str, Any]:
    """Read and validate a version 2 baseline file; raises ValueError with a clear message."""
    try:
        raw = Path(file).read_bytes().decode('utf-8', errors='replace')
    except OSError as exc:
        raise ValueError(f'baseline unreadable: {error_text(exc)}') from exc
    try:
        b = parse_json(raw)
    except ValueError as exc:
        raise ValueError(f'baseline is not valid JSON: {exc}') from exc
    if not isinstance(b, dict) or b.get('version') != 2 or isinstance(b.get('version'), bool):
        raise ValueError('baseline must have "version": 2')
    _check_baseline_entries(b.get('entries'))
    return b


def apply_baseline(findings: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[
    str, list[dict[str, Any]],
]:
    """Split findings into active and baseline-suppressed ones."""
    active: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    fps: dict[Any, dict[str, Any]] = {}
    rules: list[dict[str, Any]] = []
    for e in as_list(baseline.get('entries')):
        if e.get('fingerprint'):
            fps[e['fingerprint']] = e
        rule = e.get('rule')
        if rule:
            rules.append({
                'e': e,
                'id': glob_to_re(get_key(rule, 'id') or '*'),
                'path': glob_to_re(get_key(rule, 'path') or '*'),
                'msg': as_text(get_key(rule, 'message') or '').lower(),
            })
    for f in findings:
        hit = fps.get(f.get('fingerprint')) or _find_rule_hit(rules, f)
        if hit is not None and f['id'] not in PROTECTED:
            suppressed.append({**f, 'suppressedBy': 'baseline', 'reason': hit.get('reason')})
        else:
            active.append(f)
    return {'active': active, 'suppressed': suppressed}


def _find_rule_hit(rules: list[dict[str, Any]], f: dict[str, Any]) -> dict[str, Any] | None:
    """The entry of the first baseline rule matching the finding, or None."""
    haystack = f"{f.get('message') or ''} {f.get('evidence') or ''}".lower()
    for r in rules:
        if r['id'].match(f['id']) and r['path'].match(f['file']) and (
            not r['msg'] or r['msg'] in haystack
        ):
            return r['e']
    return None


def make_baseline(findings: list[dict[str, Any]], reason: str | None) -> dict[str, Any]:
    """Build a baseline that suppresses the given findings (except protected ones)."""
    if not reason or len(reason.strip()) < MIN_BASELINE_REASON:
        raise ValueError(
            f'--reason is required (at least {MIN_BASELINE_REASON} characters) to write a baseline'
        )
    return {
        'version': 2, 'created': now_iso(), 'rulesetVersion': RULESET_VERSION,
        'entries': [
            {
                'fingerprint': f.get('fingerprint'), 'id': f['id'], 'file': f.get('file'),
                'reason': reason,
            }
            for f in findings if f['id'] not in PROTECTED],
    }


# ---------- AI review merge ----------
def _apply_outcome(o: dict[str, Any], findings: list[dict[str, Any]],
                   by_fp: dict[Any, dict[str, Any]], problems: list[str],
                   out: dict[str, int]) -> None:
    """Attach one reviewer outcome to its finding."""
    f = by_fp.get(o.get('fingerprint'))
    if f is None and o.get('id'):
        f = next((x for x in findings if x['id'] == o['id'] and x.get('file') == o.get('file')
                  and (o.get('line') is None or x.get('line') == o['line'])), None)
    if f is None:
        problems.append(
            'outcome for an unknown finding: '
                + as_text(o.get('fingerprint') or o.get('id') or 'undefined')
        )
        return
    outcome = o.get('outcome')
    if outcome not in REVIEW_OUTCOMES:
        problems.append(f'bad outcome "{as_text(o.get("outcome", "undefined"))}" for {f["id"]}')
        return
    if outcome == 'dismissed' and len(
        as_text(o.get('reason') or '').strip()
    ) < MIN_DISMISSAL_REASON:
        where = f'{f["id"]} at {f["file"]}:{f.get("line")}'
        problems.append(f'dismissal of {where} has no reason; kept as unreviewed')
        return
    review: dict[str, Any] = {'outcome': outcome}
    if 'confidence' in o:
        review['confidence'] = o['confidence']
    review['reason'] = o.get('reason') or ''
    f['review'] = review
    if outcome == 'dismissed' and f['id'] in PROTECTED:
        review['note'] = 'dismissal not honored for structural findings'
        out['ignoredDismissals'] += 1


def _add_reviewer_finding(n: dict[str, Any], findings: list[dict[str, Any]], problems: list[str],
                          out: dict[str, int]) -> None:
    """Append a finding added by the reviewer."""
    if not all(n.get(k) for k in ('id', 'severity', 'file', 'message')):
        problems.append('added finding missing id, severity, file, or message')
        return
    if n['severity'] not in SEV:
        problems.append('added finding has bad severity ' + as_text(n['severity']))
        return
    f = enrich({
        'id': n['id'], 'severity': n['severity'],
        'confidence': n['confidence'] if n.get('confidence') is not None else 0.8,
        'file': n['file'], 'line': n.get('line') or 1, 'message': n['message'],
        'evidence': n.get('evidence') or '', 'context': 'review',
        'surface': n.get('surface') or 'instructions', 'source': 'reviewer'})
    if n['id'] in META:
        f['name'] = META[n['id']][0]
    f['review'] = {
        'outcome': 'confirmed', 'confidence': f['confidence'],
        'reason': n.get('reason') or 'added by reviewer',
    }
    findings.append(f)
    out['added'] += 1


def _tally_review(findings: list[dict[str, Any]], out: dict[str, int]) -> None:
    """Count review outcomes; findings with none are unreviewed (high/critical fail closed)."""
    keys = {'confirmed': 'confirmed', 'dismissed': 'dismissed', 'low-confidence': 'lowConfidence',
            'needs-user': 'needsUser'}
    for f in findings:
        key = keys.get(_review_outcome(f))
        if key:
            out[key] += 1
        elif not is_quality(f) and f.get('severity') != 'info':
            out['unreviewed'] += 1
            if f.get('severity') in ('high', 'critical'):
                out['unreviewedHighCritical'] += 1


def apply_review(findings: list[dict[str, Any]], review: dict[str, Any]) -> dict[str, Any]:
    """Merge an AI review (outcomes and added findings) into the findings and summarize it."""
    by_fp = {f.get('fingerprint'): f for f in findings}
    problems: list[str] = []
    out: dict[str, int] = {
        'total': len(findings), 'confirmed': 0, 'dismissed': 0, 'lowConfidence': 0, 'needsUser': 0,
        'unreviewed': 0, 'unreviewedHighCritical': 0, 'ignoredDismissals': 0, 'added': 0,
    }
    for o in as_list(review.get('outcomes')):
        if isinstance(o, dict):
            _apply_outcome(o, findings, by_fp, problems, out)
        else:
            problems.append('review outcome is not an object')
    for n in as_list(review.get('findings')):
        if isinstance(n, dict):
            _add_reviewer_finding(n, findings, problems, out)
        else:
            problems.append('added finding is not an object')
    _tally_review(findings, out)
    return {'summary': out, 'problems': problems}


# ---------- SARIF ----------
def _level(severity: Any) -> str:
    """Map a severity to a SARIF level."""
    if severity in ('critical', 'high'):
        return 'error'
    return 'warning' if severity == 'medium' else 'note'


def _rule_name(f: dict[str, Any]) -> str:
    """Build the camel-cased SARIF rule name from a finding's display name."""
    name = _RE_NON_ALNUM_RUN.sub(' ', as_text(f.get('name') or f['id'])).strip()
    return _RE_SPACE_WORD.sub(lambda m: m.group(1).upper(), name)


def _sarif_rule(f: dict[str, Any]) -> dict[str, Any]:
    """Build the SARIF rule descriptor for a finding id."""
    m = META.get(f['id'])
    tags = ['security', f.get('category')]
    if f.get('cwe'):
        tags.append(f['cwe'])
    if f.get('owasp'):
        tags.append('OWASP-' + f['owasp'])
    props: dict[str, Any] = {}
    if f.get('category') is not None:
        props['category'] = f['category']
    props['tags'] = tags
    return {
        'id': f['id'], 'name': _rule_name(f),
        'shortDescription': {'text': f.get('name') or f['id']},
        'help': {'text': f.get('fix') or ''},
        'defaultConfiguration': {'level': _level(m[2] if m else f.get('severity'))},
        'properties': props,
    }


def _sarif_result(sk: dict[str, Any], f: dict[str, Any]) -> dict[str, Any]:
    """Build one SARIF result for a finding."""
    evidence = f.get('evidence')
    props: dict[str, Any] = {'severity': f.get('severity')}
    if f.get('confidence') is not None:
        props['confidence'] = f['confidence']
    props['context'] = f.get('context') or None
    props['surface'] = f.get('surface') or None
    props['review'] = _review_outcome(f) if f.get('review') else 'unreviewed'
    prefix = sk['name'] + '/' if sk.get('name') else ''
    line = f.get('line')
    return {
        'ruleId': f['id'], 'level': _level(f.get('severity')),
        'message': {
            'text': as_text(f.get('message') or '')
                + (' | ' + as_text(evidence) if evidence else '')
        },
        'locations': [{'physicalLocation': {
            'artifactLocation': {'uri': prefix + as_text(f.get('file') or '')},
            'region': {'startLine': line if isinstance(line, int) and line > 0 else 1}}}],
        'partialFingerprints': {'skillAuditor/v1': f.get('fingerprint')},
        'properties': props,
    }


def sarif(result: dict[str, Any], version: str | None = None) -> dict[str, Any]:
    """Build a SARIF 2.1.0 document from an audit result."""
    used: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for sk in result['skills']:
        for f in sk['findings']:
            if f['id'] not in used:
                used[f['id']] = _sarif_rule(f)
            results.append(_sarif_result(sk, f))
    return {
        '$schema': 'https://json.schemastore.org/sarif-2.1.0.json',
        'version': '2.1.0',
        'runs': [{
            'tool': {'driver': {'name': 'skill-auditor', 'version': version or RULESET_VERSION,
                                'rules': list(used.values())}},
            'results': results,
            'invocations': [{'executionSuccessful': True, 'properties': {'coverage': [
                {'skill': s.get('name'), 'percent': s['coverage'].get('percent'),
                 'complete': s['coverage'].get('complete')}
                for s in result['skills']]}}],
        }],
    }


# ---------- markdown and terminal ----------
def _cell(f: dict[str, Any]) -> str:
    """Format a finding's evidence for a markdown table cell."""
    return as_text(f.get('evidence') or '').replace('|', '\\|').replace('\n', ' ')[:90]


def _what(f: dict[str, Any]) -> str:
    """The display name of a finding (falls back to its message)."""
    return as_text(f.get('name') or f.get('message') or '')


def _markdown_header(s: dict[str, Any]) -> list[str]:
    """Build the heading, risk, coverage, and counts lines for one skill."""
    risk = s['risk']
    cov = s['coverage']
    reasons = ' (' + '; '.join(risk['reasons']) + ')' if risk['reasons'] else ''
    partial = f", {len(cov['partial'])} partial" if cov['partial'] else ''
    uninspected = f", {len(cov['uninspected'])} not inspected" if cov['uninspected'] else ''
    counts = ', '.join(f"{k} {s['counts'].get(k, 0)}" for k in SEV)
    suppressed = f" | suppressed {len(s['suppressed'])}" if s['suppressed'] else ''
    return [
        f"## {s['name']}", '',
        f"**Risk score:** {risk['score']}/100 ({risk['severity']}) | "
        f"**Mechanical recommendation:** {risk['recommendation']}{reasons}",
        f"**Coverage:** {cov['percent']}% ({cov['inspected']} of "
        f"{cov['total']} files fully inspected{partial}{uninspected})",
        f'**Findings:** {counts}{suppressed}', '',
    ]


def _markdown_table(s: dict[str, Any]) -> list[str]:
    """Build the findings table for one skill."""
    lines = ['| Sev | ID | Where | What | Evidence |', '|---|---|---|---|---|']
    for f in [x for x in s['findings'] if x.get('severity') != 'info'][:60]:
        where = f"`{f['file']}:{f.get('line') or ''}`"
        lines.append(f"| {f.get('severity')} | {f['id']} | {where} | {_what(f)} | {_cell(f)} |")
    if len(s['findings']) > 60:
        lines += ['', f"\u2026and {len(s['findings']) - 60} more in the JSON output."]
    lines.append('')
    return lines


def _markdown_footer(s: dict[str, Any]) -> list[str]:
    """Build the not-inspected, hosts, and review lines for one skill."""
    lines: list[str] = []
    if s['coverage']['uninspected']:
        lines += ['**Not inspected:**']
        lines += [f"- `{u['file']}`: {u['reason']}" for u in s['coverage']['uninspected'][:20]]
        lines.append('')
    if s['network']['hosts']:
        hosts = ', '.join(
            '`' + h['host'] + '`' + (' (' + ', '.join(h['flags']) + ')' if h['flags'] else '')
            for h in s['network']['hosts'][:20])
        lines += ['**Hosts mentioned:** ' + hosts, '']
    if s.get('review'):
        r = s['review']['summary']
        lines += [
            f"**Review:** confirmed {r['confirmed']}, dismissed {r['dismissed']}, "
            f"low-confidence {r['lowConfidence']}, unreviewed {r['unreviewed']} "
            f"({r['unreviewedHighCritical']} high or critical)", '']
    return lines


def markdown(result: dict[str, Any]) -> str:
    """Render the audit result as Markdown."""
    lines = [
        '# Skill audit: mechanical pass', '',
        f"Target: `{result['target']}` | skills: {result['skillCount']} | "
        f'rule set {RULESET_VERSION}',
        '',
    ]
    for s in result['skills']:
        lines += _markdown_header(s)
        if s['findings']:
            lines += _markdown_table(s)
        lines += _markdown_footer(s)
    lines.append(
        '_Mechanical results are leads. The audit verdict comes from reading each flagged place._'
    )
    return '\n'.join(lines)


def terminal(result: dict[str, Any]) -> str:
    """Render the audit result as plain terminal text."""
    lines: list[str] = []
    for s in result['skills']:
        counts = ' '.join(f"{k[0].upper()}{s['counts'].get(k, 0)}" for k in SEV[:4])
        lines.append(
            f"{s['name']}  risk {s['risk']['score']}/100 {s['risk']['recommendation']}  "
            f"coverage {s['coverage']['percent']}%  " + counts)
        for f in [x for x in s['findings'] if x.get('severity') != 'info'][:25]:
            evidence = f.get('evidence')
            tail = '  | ' + as_text(evidence)[:70] if evidence else ''
            lines.append(
                f"  {str(f.get('severity')).ljust(8)} {f['id'].ljust(6)} "
                f"{f['file']}:{f.get('line') or ''}  {_what(f)}{tail}")
        if len(s['findings']) > 25:
            lines.append(f"  \u2026 {len(s['findings']) - 25} more")
    return '\n'.join(lines)
