"""Command line: option parsing, custom rules, output formatting, and main()."""

from __future__ import annotations

import math
import os
import re
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from . import report
from .audit import VERSION, audit_path
from .catalog import META
from .model import Rule, SEVS
from .text import scan_re
from .util import dump_json, error_text, read_json_file

__all__ = ['CliError', 'CliOptions', 'load_custom_rules', 'main', 'parse_args']

HELP: str = """skill-auditor lint (Python 3.12+, no dependencies)

usage: python lint.py <skill-folder | folder-of-skills | SKILL.md | file | .zip> [options]

output     --format json|markdown|terminal|sarif   (default json)   --out FILE   --pretty
scope      --recursive (auto when no SKILL.md at the target)   --max-skills N (32)   --exclude GLOB (repeatable)
network    --osv        look up pinned dependencies on OSV.dev and CISA KEV (needs curl; honors HTTPS_PROXY,
                        SKILL_AUDITOR_PROXY, SKILL_AUDITOR_PROXY_AUTH=negotiate|ntlm, SKILL_AUDITOR_CA_BUNDLE)
rules      --rules FILE JSON array of extra rules: {id, severity, confidence, on:["md","code","cfg"], pattern, flags, message}
baseline   --baseline FILE   --show-suppressed   --make-baseline FILE --reason TEXT
review     --review FILE     merge the reviewer's outcomes and added findings   --require-review
compare    --compare PREVIOUS_REPORT.json   report what changed since an earlier audit of the same skill
gates      --max-score N (50)  --fail-on-findings  --fail-on SEVERITY  --fail-on-incomplete  --min-coverage N
exit       0 passed | 1 a gate failed | 2 usage or input error
"""

FORMATS: tuple[str, ...] = ('json', 'markdown', 'terminal', 'sarif')
RULE_SURFACES: tuple[str, ...] = ('md', 'code', 'cfg')
RE_BUILTIN_STYLE_ID: re.Pattern[str] = scan_re(r'^[A-Z]{2,5}\d{2}')


class CliError(Exception):
    """A usage or input error that ends the run with exit code 2."""


@dataclass
class CliOptions:
    """Parsed command-line options."""

    target: str | None = None
    format: str = 'json'
    out: str | None = None
    pretty: bool = False
    recursive: bool = False
    max_skills: float | None = None
    exclude: list[str] = field(default_factory=list)
    osv: bool = False
    rules_file: str | None = None
    baseline: str | None = None
    show_suppressed: bool = False
    make_baseline: str | None = None
    reason: str | None = None
    review_file: str | None = None
    require_review: bool = False
    compare_file: str | None = None
    max_score: float | None = None
    fail_on_findings: bool = False
    fail_on: str | None = None
    fail_on_incomplete: bool = False
    min_coverage: float | None = None
    help: bool = False

    def audit_opts(self) -> dict[str, Any]:
        """The options dictionary for audit_path (camel-case keys; unset options are left out)."""
        pairs: list[tuple[str, Any]] = [
            ('exclude', self.exclude), ('osv', self.osv or None), ('baseline', self.baseline),
            ('maxSkills', self.max_skills), ('maxScore', self.max_score), ('failOn', self.fail_on),
            ('failOnFindings', self.fail_on_findings or None),
            ('failOnIncomplete', self.fail_on_incomplete or None),
            ('minCoverage', self.min_coverage), ('requireReview', self.require_review or None),
            ('showSuppressed', self.show_suppressed or None),
        ]
        return {k: v for k, v in pairs if v is not None}


def parse_number(flag: str, value: str) -> float:
    """A finite number from the command line (whole numbers become ints); CliError otherwise."""
    try:
        x = float(value)
    except ValueError:
        x = math.nan
    if not math.isfinite(x):
        raise CliError(f'{flag} needs a number, got "{value}"')
    return int(x) if x.is_integer() else x


def _setter(attr: str) -> Callable[[CliOptions, str], None]:
    """A handler that stores the option value as text."""
    return lambda opts, value: setattr(opts, attr, value)


def _number_setter(flag: str, attr: str) -> Callable[[CliOptions, str], None]:
    """A handler that stores the option value as a number."""
    return lambda opts, value: setattr(opts, attr, parse_number(flag, value))


VALUE_FLAGS: dict[str, Callable[[CliOptions, str], None]] = {
    '--format': _setter('format'), '-f': _setter('format'),
    '--out': _setter('out'), '-o': _setter('out'),
    '--max-skills': _number_setter('--max-skills', 'max_skills'),
    '--exclude': lambda opts, value: opts.exclude.append(value),
    '--rules': _setter('rules_file'),
    '--baseline': _setter('baseline'), '-b': _setter('baseline'),
    '--make-baseline': _setter('make_baseline'),
    '--reason': _setter('reason'),
    '--review': _setter('review_file'),
    '--compare': _setter('compare_file'),
    '--max-score': _number_setter('--max-score', 'max_score'),
    '--fail-on': _setter('fail_on'),
    '--min-coverage': _number_setter('--min-coverage', 'min_coverage'),
}
BOOL_FLAGS: dict[str, str] = {
    '--help': 'help', '-h': 'help', '--pretty': 'pretty', '--recursive': 'recursive',
    '--osv': 'osv',
    '--show-suppressed': 'show_suppressed', '--require-review': 'require_review',
    '--fail-on-findings': 'fail_on_findings', '--fail-on-incomplete': 'fail_on_incomplete',
}


def parse_args(argv: list[str]) -> CliOptions:
    """Parse the command line by hand (exact option names only, no abbreviations)."""
    o = CliOptions()
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in BOOL_FLAGS:
            setattr(o, BOOL_FLAGS[a], True)
        elif a in VALUE_FLAGS:
            if i + 1 >= len(argv):
                raise CliError('missing value after ' + a)
            VALUE_FLAGS[a](o, argv[i + 1])
            i += 1
            if a == '--fail-on' and o.fail_on not in SEVS:
                raise CliError('--fail-on needs one of ' + ', '.join(SEVS))
        elif a.startswith('-'):
            raise CliError('unknown option ' + a)
        else:
            positional.append(a)
        i += 1
    o.target = positional[0] if positional else None
    if o.format not in FORMATS:
        raise CliError('--format must be json, markdown, terminal, or sarif')
    return o


def _compile_rule_pattern(rule_id: str, pattern: str, flags: str) -> re.Pattern[str]:
    """Compile a custom rule pattern; letters other than i, m, s are rejected."""
    bad = [c for c in flags if c not in 'imsguyd']
    if bad:
        raise CliError(f'rule {rule_id}: unsupported regex flag "{bad[0]}"')
    try:
        return scan_re(pattern, ''.join(c for c in flags if c in 'ims'))
    except (re.error, ValueError, RecursionError) as exc:
        raise CliError(f'rule {rule_id}: invalid pattern: {exc}') from exc


def _custom_rule(r: Any) -> Rule:
    """Build one line rule from a custom-rules entry and register its catalog metadata."""
    if not isinstance(r, dict) or not r.get('id') or not r.get('pattern'):
        raise CliError('each custom rule needs "id" and "pattern"')
    raw_id = str(r['id'])
    rule_id = raw_id if RE_BUILTIN_STYLE_ID.search(raw_id) else 'CUS-' + raw_id
    sev = r.get('severity') or 'medium'
    if sev not in SEVS:
        raise CliError(f'rule {raw_id}: severity must be one of ' + ', '.join(SEVS))
    surfaces = r.get('on') or list(RULE_SURFACES)
    if not isinstance(surfaces, list) or any(s not in RULE_SURFACES for s in surfaces):
        raise CliError(f'rule {raw_id}: "on" must list md, code, or cfg')
    if not META.get(rule_id):
        META[rule_id] = [r.get('message') or rule_id, 'custom', sev, None, None,
                         r.get('remediation') or 'See the rule owner.']
    confidence = r['confidence'] if r.get('confidence') is not None else 0.7
    return {
        'id': rule_id, 'sev': sev, 'conf': confidence, 'on': surfaces, 'message': r.get('message'),
        're': _compile_rule_pattern(raw_id, str(r['pattern']), r.get('flags') or 'i'),
    }


def load_custom_rules(file: str) -> list[Rule]:
    """Load extra rules: a JSON array of {id, pattern, severity, confidence, on, flags, message}."""
    arr = read_json_file(file)
    if not isinstance(arr, list):
        raise CliError('the rules file must contain a JSON array')
    return [_custom_rule(r) for r in arr]


def write_stream(stream: TextIO, s: str) -> None:
    """Write text as UTF-8 bytes without newline translation."""
    try:
        stream.flush()
        stream.buffer.write(s.encode('utf-8', errors='replace'))
        stream.buffer.flush()
    except AttributeError:  # a stream without a binary buffer (for example a test double)
        stream.write(s)


def _read_object(path: str, what: str) -> dict[str, Any]:
    """Read a JSON file that must hold an object."""
    data = read_json_file(path)
    if not isinstance(data, dict):
        raise ValueError(f'the {what} file must contain a JSON object')
    return data


def load_inputs(o: CliOptions, opts: dict[str, Any]) -> None:
    """Load the rules, baseline, review, and compare files named on the command line."""
    if o.rules_file:
        opts['customRules'] = load_custom_rules(o.rules_file)
    if o.baseline:
        opts['baselineData'] = report.load_baseline(o.baseline)
    if o.review_file:
        opts['reviewData'] = _read_object(o.review_file, 'review')
    if o.compare_file:
        opts['compareData'] = _read_object(o.compare_file, 'compare')


def render_output(o: CliOptions, result: dict[str, Any]) -> str:
    """Render the result in the requested format."""
    if o.format == 'sarif':
        return dump_json(report.sarif(result, VERSION), o.pretty)
    if o.format == 'markdown':
        return report.markdown(result)
    if o.format == 'terminal':
        return report.terminal(result)
    return dump_json(result, o.pretty)


def fail(message: str) -> int:
    """Print an error line to stderr and return the usage-error exit code."""
    write_stream(sys.stderr, f'error: {message}\n')
    return 2


def write_baseline(path: str, reason: str | None, result: dict[str, Any]) -> None:
    """Write a baseline for every finding in the result; ValueError or OSError on failure."""
    all_findings = [f for s in result['skills'] for f in s['findings']]
    payload = dump_json(report.make_baseline(all_findings, reason), True)
    Path(path).write_bytes(payload.encode('utf-8'))
    write_stream(sys.stderr, f'baseline written to {path} ({len(all_findings)} finding(s))\n')


def emit(o: CliOptions, result: dict[str, Any], out_text: str) -> None:
    """Send the rendered output to --out or to stdout."""
    if not o.out:
        write_stream(sys.stdout, out_text + '\n')
        return
    Path(o.out).write_bytes(out_text.encode('utf-8'))
    total = sum(len(s['findings']) for s in result['skills'])
    risks = '/'.join(str(s['risk']['score']) for s in result['skills'])
    verdict = 'passed' if result['gates']['passed'] else 'FAILED'
    write_stream(sys.stdout, f"wrote {o.out}: {result['skillCount']} skill(s), {total} finding(s), "
                             f'risk {risks}, gates {verdict}\n')


def run(o: CliOptions, target: str) -> int:
    """Audit the target and produce the output; returns the exit code."""
    opts = o.audit_opts()
    try:
        load_inputs(o, opts)
    except (CliError, ValueError) as exc:
        return fail(str(exc))
    try:
        result = audit_path(target, opts)
    except Exception:  # noqa: BLE001 - any failure while auditing is reported as an input error
        return fail(traceback.format_exc())
    try:
        if o.make_baseline:
            write_baseline(o.make_baseline, o.reason, result)
        if opts.get('reviewData'):
            problems = [
                p for s in result['skills'] if s.get('review') for p in s['review']['problems']
            ]
            if problems:
                result['reviewProblems'] = problems
        emit(o, result, render_output(o, result))
    except (OSError, ValueError) as exc:
        return fail(error_text(exc) if isinstance(exc, OSError) else str(exc))
    for failure in result['gates']['failures']:
        write_stream(sys.stderr, f'gate: {failure}\n')
    return 0 if result['gates']['passed'] else 1


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; returns the process exit code."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure:
            reconfigure(encoding='utf-8', errors='replace')
    args = sys.argv[1:] if argv is None else argv
    try:
        o = parse_args(args)
    except CliError as exc:
        write_stream(sys.stderr, f'error: {exc}\n{HELP}')
        return 2
    if o.help or not o.target:
        write_stream(sys.stdout, HELP)
        return 0 if o.help else 2
    if not os.path.exists(o.target):
        return fail(f'not found: {o.target}')
    return run(o, o.target)
