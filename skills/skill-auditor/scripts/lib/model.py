"""Shared data model: limits, file classification, the per-skill context, and finding helpers."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from . import report
from .catalog import META
from .text import scan_re
from .util import round_half_up

__all__ = [
    'CODE_EXT',
    'Ctx',
    'FileItem',
    'Finding',
    'LIM',
    'MD_EXT',
    'Rule',
    'SEVS',
    'add_host',
    'base_of',
    'ext_of',
    'family_of',
    'inspect_kind_label',
    'is_test_path',
    'kind_of',
    'step_down',
    'surface_of',
]


Rule: TypeAlias = dict[str, Any]

Finding: TypeAlias = dict[str, Any]

SEVS: list[str] = list(report.SEV)

LIM: dict[str, int] = {
    'fileBytes': 1024 * 1024,
    'binaryRead': 16 * 1024 * 1024,
    'ingestBytes': 100 * 1024 * 1024,
    'ingestFiles': 10000,
    'lineScan': 2000,
}

MD_EXT: frozenset[str] = frozenset({'.md', '.markdown', '.txt', '.rst'})

CODE_EXT: frozenset[str] = frozenset({
    '.js', '.mjs', '.cjs', '.ts', '.py', '.sh', '.bash', '.zsh', '.ps1', '.psm1', '.bat', '.cmd',
    '.rb', '.php',
    '.java', '.go', '.rs', '.cs', '.kt', '.pl', '.lua', '.vbs', '.html', '.htm', '.svg',
})

STEP_DOWN: dict[str, str] = {
    'critical': 'high', 'high': 'medium', 'medium': 'low', 'low': 'low', 'info': 'info',
}

RE_TEST_DIR: re.Pattern[str] = scan_re(r'(^|\/)(tests?|__tests__|specs?|e2e|fixtures?)\/', 'i')

RE_TEST_FILE: re.Pattern[str] = scan_re(r'\.(test|spec)\.[jt]sx?$|_test\.py$|(^|\/)test_[^/]+\.py$', 'i')

RE_HOOK_CONFIG: re.Pattern[str] = scan_re(r'hooks?\.json$', 'i')

RE_HOOKS_DIR: re.Pattern[str] = scan_re(r'(^|\/)hooks\/', 'i')

RE_DOC_NAME: re.Pattern[str] = scan_re(r'(^|\/)(readme|changelog|contributing|license)', 'i')

RE_TRAILING_DIGITS: re.Pattern[str] = scan_re(r'\d+$')


def step_down(sev: str) -> str:
    """Lower a severity by one level (an unknown severity is returned unchanged)."""
    return STEP_DOWN.get(sev, sev)


def family_of(rule_id: str) -> str:
    """Rule family: the id without its trailing digits."""
    return RE_TRAILING_DIGITS.sub('', rule_id)


def ext_of(rel: str) -> str:
    """Lowercase file extension of a relative path."""
    return os.path.splitext(rel)[1].lower()


def base_of(rel: str) -> str:
    """File name part of a relative path."""
    return os.path.basename(rel)


def is_test_path(rel: str) -> bool:
    """True for paths that look like tests or fixtures."""
    return bool(RE_TEST_DIR.search(rel) or RE_TEST_FILE.search(rel))


def kind_of(rel: str) -> str:
    """Classify a file: skillmd, hook-config, hook, script, md, or cfg."""
    base, ext = base_of(rel), ext_of(rel)
    if base == 'SKILL.md':
        return 'skillmd'
    if RE_HOOK_CONFIG.search(base):
        return 'hook-config'
    if RE_HOOKS_DIR.search(rel) and ext in CODE_EXT:
        return 'hook'
    if ext in CODE_EXT:
        return 'script'
    if ext in MD_EXT:
        return 'md'
    return 'cfg'


def surface_of(kind: str) -> str:
    """Rule surface for a file kind: md, code, or cfg."""
    if kind in ('skillmd', 'md'):
        return 'md'
    if kind in ('script', 'hook'):
        return 'code'
    return 'cfg'


def inspect_kind_label(kind: str, rel: str) -> str:
    """Finding surface label for a file: docs, instructions, code, or config."""
    if kind in ('skillmd', 'md'):
        return 'docs' if RE_DOC_NAME.search(rel) else 'instructions'
    if kind in ('script', 'hook'):
        return 'code'
    return 'config'


@dataclass
class Ctx:
    """Everything collected while auditing one skill."""

    dir: str
    opts: dict[str, Any]
    findings: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)
    hosts: dict[str, dict[str, Any]] = field(default_factory=dict)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    caps: dict[str, dict[str, int]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)
    zip_budget: dict[str, Any] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    hook_summary: list[str] = field(default_factory=list)
    declared_name: str | None = None
    virtual_files: list[dict[str, Any]] | None = None
    skill_name: str = ''

    def __post_init__(self) -> None:
        """Derive the skill name from the folder name."""
        self.skill_name = os.path.basename(self.dir)

    def virtual_has(self, rel: str) -> bool:
        """True when an in-memory (zip) skill contains this relative path."""
        return bool(
            self.virtual_files is not None and any(v['rel'] == rel for v in self.virtual_files)
        )

    def add(self, f: Finding) -> None:
        """Normalize a finding (defaults, truncation, rounding, enrichment) and record it."""
        meta = META.get(f['id'])
        o: Finding = {
            'line': 1, 'evidence': '', 'confidence': 0.75, 'context': 'prose',
            'surface': 'instructions', **f,
        }
        if not o.get('severity'):
            o['severity'] = meta[2] if meta else 'medium'
        if not o.get('message'):
            o['message'] = meta[0] if meta else f['id']
        if o['evidence'] and len(o['evidence']) > 180:
            o['evidence'] = o['evidence'][:177] + '...'
        o['confidence'] = max(0.05, min(1, round_half_up(o['confidence'] * 100) / 100))
        report.enrich(o)
        if o.get('_suppress'):
            del o['_suppress']
            self.suppressed.append(
                {**o, 'suppressedBy': 'inline audit-ignore', 'reason': 'inline marker'}
            )
        else:
            self.findings.append(o)


@dataclass
class FileItem:
    """One file to process: relative path, size, and a reader."""

    rel: str
    size: int
    read: Callable[[], bytes]


def add_host(ctx: Ctx, host: str, file: str, line: int, flags: list[str]) -> None:
    """Record a host mention with its risk flags."""
    h = ctx.hosts.get(host)
    if h is None:
        h = {'host': host, 'flags': [], 'count': 0, 'first': f'{file}:{line}'}
    for fl in flags:
        if fl not in h['flags']:
            h['flags'].append(fl)
    h['count'] += 1
    ctx.hosts[host] = h
