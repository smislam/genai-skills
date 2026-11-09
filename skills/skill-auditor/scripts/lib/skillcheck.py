"""Skill-level checks: frontmatter, name and description, links, capabilities, dependencies."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import deps
from .catalog import BROAD_TRIGGER, SHADOW_NAMES
from .configaudit import audit_config_files, mentions_injection
from .model import Ctx, base_of, ext_of, kind_of
from .text import scan_re
from .util import RE_LINE_SPLIT, get_key, parse_json

__all__ = [
    'Frontmatter',
    'SkillInfo',
    'analyze_skill',
    'parse_frontmatter',
]


KNOWN_KEYS: frozenset[str] = frozenset({
    'name', 'description', 'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation',
    'user-invocable',
    'allowed-tools', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background',
    'hooks', 'paths',
    'shell', 'metadata', 'license', 'compatibility', 'version',
})

RUNTIME_BY_EXT: dict[str, re.Pattern[str]] = {
    '.js': scan_re(r'node', 'i'), '.mjs': scan_re(r'node', 'i'), '.cjs': scan_re(r'node', 'i'),
    '.py': scan_re(r'python', 'i'), '.sh': scan_re(r'bash|shell', 'i'), '.ps1': scan_re(r'powershell', 'i'),
}

HOST_STOP_WORDS: frozenset[str] = frozenset({
    'skill', 'when', 'with', 'that', 'this', 'from', 'your', 'file', 'files', 'code', 'user',
    'asks', 'trigger',
    'triggers', 'review', 'check', 'security', 'audit', 'not', 'for',
})

# Frontmatter.
RE_FRONTMATTER: re.Pattern[str] = scan_re(r'^\ufeff?---\r?\n([\x00-\U0010ffff]*?)\r?\n---[ \t]*(\r?\n|$)')

RE_FM_TOP_KEY: re.Pattern[str] = scan_re(r'^([A-Za-z_][\w-]*)\s*:\s*(.*)$')

RE_LEADING_WS: re.Pattern[str] = scan_re(r'^\s')

RE_LEADING_WS_RUN: re.Pattern[str] = scan_re(r'^\s+')

RE_FM_BLOCK: re.Pattern[str] = scan_re(r'^[>|][+-]?\s*\n([\x00-\U0010ffff]*)$')

RE_FM_QUOTED: re.Pattern[str] = scan_re(r'^(["\']).*\1$')

# SKILL.md checks.
RE_NON_ASCII: re.Pattern[str] = scan_re(r'[^\x00-\x7F]')

RE_SKILL_NAME: re.Pattern[str] = scan_re(r'^[a-z0-9]+(-[a-z0-9]+)*$')

RE_RESERVED_NAME: re.Pattern[str] = scan_re(r'anthropic|claude', 'i')

RE_TRIGGER_CUE: re.Pattern[str] = scan_re(
    r'\b(use (when|for|this|to|it)|when (the )?(user|you)|trigger|invoke|asks? (for|to)|whenever|before you'
    r'|after you)\b', 'i')

RE_FIRST_PERSON: re.Pattern[str] = scan_re(r"^(i|i'll|i can|you|you can|we)\b", 'i')

RE_DESC_WORD: re.Pattern[str] = scan_re(r'[a-z][a-z-]{3,}', '')

RE_TAG_LIKE: re.Pattern[str] = scan_re(r'<\/?[a-z][^>]*>', 'i')

RE_MODEL_NAME: re.Pattern[str] = scan_re(r'^(inherit|sonnet|opus|haiku|fable|claude-[\w.-]+|us\.anthropic\.[\w.:-]+)$', 'i')

RE_TOOL_GRANT: re.Pattern[str] = scan_re(r'[A-Za-z_*][\w*.-]*(\([^)]*\))?')

RE_TOOL_WILDCARD: re.Pattern[str] = scan_re(r'^(\*|all|any|full)$', 'i')

RE_TOOL_BASH_ANY: re.Pattern[str] = scan_re(r'^Bash(\(\*\)|\(\*:\*\))?$')

RE_TOOL_BASH_EMPTY: re.Pattern[str] = scan_re(r'^Bash\(\s*\)$')

RE_TOOL_SHELL: re.Pattern[str] = scan_re(
    r'^Bash\((sh|bash|zsh|cmd|powershell|pwsh|python3?|node|perl|ruby|curl|wget|nc|ssh|scp|sudo|eval|env|xargs)\b',
    'i')

# A grant that names one script (optionally after option flags such as -I or -3) is scoped, not open-ended.
RE_TOOL_SCRIPT_ARG: re.Pattern[str] = scan_re(
    r'^Bash\(\S+(?:\s+-\S+)*\s+(\$\{[A-Z_]+\}|[.~]?[\w.\-]*[\/\\])[^\s)]*\.\w{1,4}\b')

RE_SIDE_EFFECT: re.Pattern[str] = scan_re(
    r'\bgit (push|commit)\b|\bdeploy(ing|ment)?\b|\bpublish(ing)?\b|\bterraform apply\b|\bkubectl apply\b'
    r'|\bsend (an? )?(email|message|slack)\b|\bdelete\b|\bdrop (table|database)\b', 'i')

RE_TRUE: re.Pattern[str] = scan_re(r'^true$', 'i')

RE_VERIFY_WORDS: re.Pattern[str] = scan_re(r'\b(verify|verif|evidence|test(s|ed)?|check(s|ed)?|confirm|validate)\b', 'i')

RE_SHOUTING: re.Pattern[str] = scan_re(r'\b(MUST|NEVER|ALWAYS|IMPORTANT|CRITICAL|DO NOT|YOU MUST)\b')

# Links and orphans.
RE_FENCE_TOGGLE: re.Pattern[str] = scan_re(r'^\s*(```|~~~)')

RE_REF_PATH: re.Pattern[str] = scan_re(r'(?:^|[\s(`"\'])((?:references|scripts|assets|rules)\/[\w.\-\/]+\.\w+)')

RE_TRAILING_PUNCT: re.Pattern[str] = scan_re(r'[.,;:)]+$')

RE_GLOB_CHARS: re.Pattern[str] = scan_re(r'[*<>{}]')

RE_MD_LINK: re.Pattern[str] = scan_re(r'\]\((?!https?:|mailto:|#)([^)#\s]+)(?:#[^)]*)?\)')

RE_BUNDLE_DIR: re.Pattern[str] = scan_re(r'^(references|scripts|assets|rules)\/')

RE_EXTENSION_TAIL: re.Pattern[str] = scan_re(r'\.[^.]+$')

RE_TOC_HEADING: re.Pattern[str] = scan_re(r'^#{1,3}\s+(contents|table of contents|toc)\b', 'im')

RE_TOC_LABEL: re.Pattern[str] = scan_re(r'^\s*(contents|table of contents)\s*:', 'im')

# Capability checks.
RE_USES_NET: re.Pattern[str] = scan_re(
    r'\bfetch\s*\(|https?\.(get|request)|\brequests\.|\burllib|\bcurl\b|\bwget\b|Invoke-(WebRequest|RestMethod)'
    r'|XMLHttpRequest|\bsocket\b')

RE_USES_EXEC: re.Pattern[str] = scan_re(r'child_process|\bsubprocess\b|\bos\.system|spawnSync|execSync|Start-Process|\bexec\(')

RE_USES_WRITE: re.Pattern[str] = scan_re(
    r'''writeFile|appendFile|fs\.(write|mkdir|rm|unlink|rename|copy)|\bopen\([^)]*['"][wa]|Set-Content|Out-File'''
    r'''|shutil\.|os\.(remove|unlink|rename|makedirs)''')

RE_USES_ENV: re.Pattern[str] = scan_re(r'process\.env|os\.environ|\$env:|getenv')

RE_MENTION_NET: re.Pattern[str] = scan_re(r'network|internet|http|download|fetch|api|online|web|url|osv|registry|remote|upload|proxy')

RE_MENTION_CRED: re.Pattern[str] = scan_re(r'credential|secret|token|password|\bkeys?\b|auth|\.env')

RE_MENTION_ENV: re.Pattern[str] = scan_re(r'environment|env var|proxy|variable|\benv\b')

RE_WEB_TOOL: re.Pattern[str] = scan_re(r'^(WebFetch|WebSearch)')

RE_WRITE_TOOL: re.Pattern[str] = scan_re(r'^(Write|Edit|NotebookEdit)')

RE_DOC_WEB: re.Pattern[str] = scan_re(r'http|web|url|fetch|search|download')

RE_DOC_WRITE: re.Pattern[str] = scan_re(r'write|creat|edit|save|modif|generat|output|fix')

RE_FUTURE_PERMISSIONS: re.Pattern[str] = scan_re(
    r'\b(will|may|might|later|future|upcoming)\b[^.\n]{0,40}\b(request|require|need|ask for|add)\s+'
    r'(additional|more|new|elevated|broader|extra)\s+(permissions?|access|privileges?|scopes?)\b', 'i')

RE_PERMISSION_SENTENCE: re.Pattern[str] = scan_re(
    r'[^.\n]*(additional|more|new|elevated|broader|extra)\s+(permissions?|access|privileges?|scopes?)[^.\n]*', 'i')


@dataclass
class Frontmatter:
    """Parsed SKILL.md frontmatter: top-level keys with folded values, and where the body starts."""

    keys: dict[str, str]
    body_start_line: int


@dataclass
class SkillInfo:
    """What the skill-level checks learn about a skill and the audit report needs."""

    name: str
    description: str = ''
    allowed_tools: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(
        default_factory=lambda: {'skillMdLines': 0, 'skillMdTokensEst': 0, 'descriptionChars': 0})
    packages: list[dict[str, Any]] = field(default_factory=list)
    lookups: dict[str, Any] = field(default_factory=dict)


def parse_frontmatter(text: str) -> Frontmatter | None:
    """Parse the YAML-ish frontmatter block of SKILL.md, or return None when there is none."""
    m = RE_FRONTMATTER.match(text)
    if not m:
        return None
    keys: dict[str, str] = {}
    fm = Frontmatter(keys, len(RE_LINE_SPLIT.split(m.group(0))))
    key: str | None = None
    for ln in RE_LINE_SPLIT.split(m.group(1)):
        top = RE_FM_TOP_KEY.match(ln)
        if top and not RE_LEADING_WS.search(ln):
            key = top.group(1)
            keys[key] = top.group(2)
            continue
        if key and (RE_LEADING_WS_RUN.search(ln) or ln == ''):
            keys[key] += '\n' + ln
    for k in list(keys):
        v = keys[k]
        block = RE_FM_BLOCK.match(v)
        v = ' '.join(
            s for s in (x.strip() for x in (block.group(1) if block else v).split('\n')) if s
        )
        if RE_FM_QUOTED.match(v):
            v = v[1:-1]
        keys[k] = v
    return fm


def analyze_skill(ctx: Ctx, siblings: list[dict[str, Any]]) -> SkillInfo:
    """Run the checks that need the whole skill: frontmatter, links, configs, dependencies."""
    skill_text = ctx.texts.get('SKILL.md')
    info = SkillInfo(name=ctx.skill_name)
    if skill_text is None:
        if not ctx.opts.get('singleFile'):
            ctx.add({'id': 'STR01', 'file': 'SKILL.md', 'evidence': 'missing'})
    else:
        check_skill_md(ctx, skill_text, info, siblings)
    links_and_orphans(ctx)
    audit_config_files(ctx)
    check_plugin_manifest(ctx)
    check_dependencies(ctx, info)
    correlate_sources_and_sinks(ctx)
    capability_checks(ctx, info, skill_text)
    return info


def check_skill_md(
    ctx: Ctx, skill_text: str, info: SkillInfo, siblings: list[dict[str, Any]],
) -> None:
    """Frontmatter and length checks for SKILL.md."""
    lines = len(RE_LINE_SPLIT.split(skill_text))
    info.stats['skillMdLines'] = lines
    info.stats['skillMdTokensEst'] = math.ceil(len(skill_text) / 4)
    fm = parse_frontmatter(skill_text)
    if not fm:
        ctx.add(
            {'id': 'STR01', 'file': 'SKILL.md', 'line': 1, 'evidence': 'no YAML frontmatter block'}
        )
    else:
        check_frontmatter(ctx, skill_text, fm, info, siblings)
    if lines > 500:
        ctx.add({'id': 'STR05', 'file': 'SKILL.md', 'evidence': str(lines), 'confidence': 0.9})
    elif lines > 350:
        ctx.add({'id': 'STR05', 'severity': 'low', 'file': 'SKILL.md', 'evidence': str(lines),
                 'confidence': 0.7})


def correlate_sources_and_sinks(ctx: Ctx) -> None:
    """Flag files that touch credentials and make network calls when no flow was traced."""
    for rel, c in list(ctx.caps.items()):
        if c.get('cred') and c.get('net') and not any(
                f['file'] == rel and f['id'] in ('FLW03', 'FLW04') for f in ctx.findings):
            ctx.add({'id': 'FLW07', 'file': rel, 'surface': 'code', 'confidence': 0.6,
                     'evidence': (f"{c['cred']} credential/key reference(s) and "
                                  f"{c['net']} network call(s) in one file")})


def check_plugin_manifest(ctx: Ctx) -> None:
    """Validate .claude-plugin/plugin.json when present."""
    pj = ctx.texts.get('.claude-plugin/plugin.json')
    if pj is None:
        return
    try:
        o = parse_json(pj)
    except ValueError as e:
        ctx.add(
            {
                'id': 'STR11', 'severity': 'high', 'file': '.claude-plugin/plugin.json',
                'evidence': str(e),
            }
        )
        return
    if not get_key(o, 'name'):
        ctx.add(
            {
                'id': 'STR11', 'severity': 'low', 'file': '.claude-plugin/plugin.json',
                'evidence': 'no name',
            }
        )


def check_dependencies(ctx: Ctx, info: SkillInfo) -> None:
    """Dependency manifest checks plus the optional OSV lookup."""
    dep_files = [{'rel': rel, 'text': t} for rel, t in ctx.texts.items()]
    dr = deps.analyze(dep_files)
    for f in dr['findings']:
        ctx.add(f)
    info.packages = dr['packages']
    if ctx.opts.get('osv'):
        o = deps.osv_lookup(dr['packages'])
        for f in o['findings']:
            ctx.add(f)
        info.lookups = o['status']
        if str(info.lookups['osv']).startswith('failed'):
            ctx.add({'id': 'COV02', 'severity': 'low', 'file': '(dependencies)',
                     'evidence': 'vulnerability lookup failed: ' + str(info.lookups['osv'])})
    else:
        info.lookups = {'osv': 'not-requested', 'kev': 'not-requested'}


def check_frontmatter(ctx: Ctx, skill_text: str, fm: Frontmatter, info: SkillInfo,
                      siblings: list[dict[str, Any]]) -> None:
    """Checks on SKILL.md frontmatter and body."""
    k = fm.keys
    info.description = k.get('description') or ''
    check_skill_name(ctx, k, info, siblings)
    check_description(ctx, k, info)
    for key in k:
        if key not in KNOWN_KEYS:
            ctx.add({'id': 'STR06', 'file': 'SKILL.md', 'evidence': key, 'confidence': 0.8})
    if 'hooks' in k:
        ctx.add({'id': 'HKS10', 'file': 'SKILL.md', 'confidence': 0.9})
    model = k.get('model')
    if model and not RE_MODEL_NAME.search(model):
        ctx.add(
            {'id': 'AGY05', 'file': 'SKILL.md', 'evidence': 'model: ' + model, 'confidence': 0.7}
        )
    check_allowed_tools(ctx, k, info)
    check_body(ctx, skill_text, fm, k)
    ctx.declared_name = k.get('name') or None


def check_skill_name(
    ctx: Ctx, k: dict[str, str], info: SkillInfo, siblings: list[dict[str, Any]],
) -> None:
    """Name checks: presence, characters, folder match, reserved words, shadowing, duplicates."""
    name = k.get('name')
    if not name:
        ctx.add({'id': 'STR02', 'severity': 'medium', 'file': 'SKILL.md',
                 'evidence': 'no name; the folder name is used', 'confidence': 0.9})
        return
    info.name = name
    if RE_NON_ASCII.search(name):
        ctx.add({'id': 'TPO02', 'file': 'SKILL.md', 'line': 2, 'confidence': 0.9, 'evidence': name})
    if not RE_SKILL_NAME.search(name) or len(name) > 64:
        ctx.add({'id': 'STR03', 'file': 'SKILL.md', 'evidence': name, 'confidence': 0.9})
    if name != ctx.skill_name and not ctx.opts.get('virtualRoot'):
        ctx.add({'id': 'STR03', 'severity': 'low', 'file': 'SKILL.md',
                 'evidence': f'name={name} folder={ctx.skill_name}', 'confidence': 0.8})
    if RE_RESERVED_NAME.search(name):
        ctx.add({'id': 'STR03', 'severity': 'low', 'file': 'SKILL.md',
                 'evidence': 'reserved word in name: ' + name, 'confidence': 0.7})
    if name.lower() in SHADOW_NAMES:
        ctx.add({'id': 'TRG02', 'file': 'SKILL.md',
                 'evidence': 'built-in or widely used command name: ' + name, 'confidence': 0.7})
    if any(s.get('declaredName') == name for s in siblings or []):
        ctx.add({'id': 'TRG02', 'file': 'SKILL.md', 'confidence': 0.9,
                 'evidence': 'another skill in this scan has the same name'})


def check_description(ctx: Ctx, k: dict[str, str], info: SkillInfo) -> None:
    """Description and when_to_use checks: length, trigger wording, breadth, injection."""
    d = k.get('description') or ''
    wtu = k.get('when_to_use') or ''
    chars = len(d) + len(wtu)
    info.stats['descriptionChars'] = chars
    if not d:
        ctx.add(
            {'id': 'STR02', 'file': 'SKILL.md', 'evidence': 'no description', 'confidence': 0.95}
        )
        return
    dl = d + ' ' + wtu
    if chars > 1536:
        ctx.add(
            {
                'id': 'STR04', 'severity': 'high', 'file': 'SKILL.md', 'evidence': str(chars),
                'confidence': 0.95,
            }
        )
    elif chars > 800:
        ctx.add(
            {
                'id': 'STR04', 'severity': 'low', 'file': 'SKILL.md', 'evidence': str(chars),
                'confidence': 0.7,
            }
        )
    if len(d) < 50:
        ctx.add({'id': 'TRG05', 'file': 'SKILL.md', 'evidence': d, 'confidence': 0.8})
    if not RE_TRIGGER_CUE.search(dl):
        ctx.add({'id': 'TRG04', 'file': 'SKILL.md', 'evidence': d[:120], 'confidence': 0.6})
    if RE_FIRST_PERSON.search(d):
        ctx.add({'id': 'TRG04', 'severity': 'low', 'file': 'SKILL.md',
                 'message': 'Description written in first or second person', 'evidence': d[:80],
                 'confidence': 0.6})
    bt = BROAD_TRIGGER.search(dl)
    if bt:
        ctx.add({'id': 'TRG01', 'file': 'SKILL.md', 'evidence': bt.group(0), 'confidence': 0.65})
    freq: dict[str, int] = {}
    for w in RE_DESC_WORD.findall(dl.lower()):
        freq[w] = freq.get(w, 0) + 1
    # A platform or product name naturally recurs in its own skill's description; stuffing repeats a
    # word many times.
    rep = next(((w, c) for w, c in freq.items() if c >= 8 and w not in HOST_STOP_WORDS), None)
    comma_items = dl.count(',')
    if rep or comma_items >= 28:
        evidence = (f'"{rep[0]}" appears {rep[1]} times' if rep
                    else f'{comma_items} comma-separated terms')
        ctx.add({'id': 'TRG03', 'file': 'SKILL.md', 'evidence': evidence, 'confidence': 0.5})
    tag = RE_TAG_LIKE.search(d)
    if tag:
        ctx.add({'id': 'TRG04', 'severity': 'low', 'file': 'SKILL.md',
                 'message': 'Description contains tag-like text that some hosts reject',
                 'evidence': tag.group(0),
                 'confidence': 0.6})
    if mentions_injection(dl):
        ctx.add({'id': 'TPO01', 'severity': 'high', 'file': 'SKILL.md', 'line': 2,
                 'confidence': 0.85, 'evidence': dl[:140],
                 'message': ('Injection or concealment language inside the description, '
                             'which is loaded into every session')})


def check_allowed_tools(ctx: Ctx, k: dict[str, str], info: SkillInfo) -> None:
    """Flag blanket or interpreter-level pre-approved tool grants."""
    grants = [m.group(0) for m in RE_TOOL_GRANT.finditer(k.get('allowed-tools') or '')]
    info.allowed_tools = grants
    for g in grants:
        if RE_TOOL_WILDCARD.search(g) or RE_TOOL_BASH_ANY.search(g) or RE_TOOL_BASH_EMPTY.search(g):
            ctx.add({'id': 'PRM02', 'file': 'SKILL.md', 'evidence': g, 'confidence': 0.85})
        elif RE_TOOL_SHELL.search(g) and not RE_TOOL_SCRIPT_ARG.search(g):
            ctx.add({'id': 'AGY01', 'file': 'SKILL.md', 'evidence': g, 'confidence': 0.75,
                     'message': ('Pre-approved grant for a shell, interpreter, or network tool: '
                                 'it can run anything')})


def check_body(ctx: Ctx, skill_text: str, fm: Frontmatter, k: dict[str, str]) -> None:
    """Body checks: side-effect verbs, verification wording, shouting."""
    body_lines = RE_LINE_SPLIT.split(skill_text)[fm.body_start_line:]
    body = '\n'.join(body_lines)
    side_effects = list(dict.fromkeys(m.group(0).lower() for m in RE_SIDE_EFFECT.finditer(body)))
    if len(side_effects) >= 2 and not RE_TRUE.search(k.get('disable-model-invocation') or ''):
        severity = 'medium' if len(side_effects) >= 4 else 'low'
        ctx.add({'id': 'AGY06', 'severity': severity, 'file': 'SKILL.md',
                 'evidence': ', '.join(side_effects[:6]), 'confidence': 0.55})
    if not RE_VERIFY_WORDS.search(body):
        ctx.add({'id': 'QLT03', 'file': 'SKILL.md', 'confidence': 0.6})
    caps = len(RE_SHOUTING.findall(body))
    per100 = caps / max(1, len(RE_LINE_SPLIT.split(body))) * 100
    if caps >= 5 and per100 > 3:
        ctx.add({'id': 'QLT01', 'file': 'SKILL.md',
                 'evidence': f'{caps} occurrences, {per100:.1f} per 100 lines', 'confidence': 0.6})


def links_and_orphans(ctx: Ctx) -> None:
    """Report broken references, orphaned bundle files, and long documents with no contents list."""
    names = [r for r in ctx.texts if '!/' not in r and '#' not in r]
    for rel in names:
        if kind_of(rel) in ('skillmd', 'md'):
            check_references(ctx, rel)
    for rel in names:
        if rel == 'SKILL.md' or not RE_BUNDLE_DIR.search(rel):
            continue
        base = base_of(rel)
        stem = RE_EXTENSION_TAIL.sub('', base)
        quoted = [c + stem + q for c in ('/', '"', "'") for q in ('"', "'", '`')]
        imported = re.compile(r'\b(?:from|import)\b[^\n]*\b' + re.escape(stem) + r'\b')
        used = any(o != rel and (base in ctx.texts[o] or any(k in ctx.texts[o] for k in quoted)
                                 or (o.endswith('.py') and imported.search(ctx.texts[o]) is not None))
                   for o in names)
        if not used:
            ctx.add({'id': 'STR08', 'file': rel, 'evidence': base, 'confidence': 0.7})
    for rel in names:
        text = ctx.texts[rel]
        if kind_of(rel) != 'md':
            continue
        n_lines = len(RE_LINE_SPLIT.split(text))
        if n_lines > 300 and not RE_TOC_HEADING.search(text) and not RE_TOC_LABEL.search(text):
            ctx.add({'id': 'STR09', 'file': rel, 'evidence': str(n_lines), 'confidence': 0.7})


def reference_exists(ctx: Ctx, rel_dir: str, target: str) -> bool:
    """True when a referenced path exists under the skill root or the referencing file's folder."""
    probes = (os.path.join(ctx.dir, target), os.path.join(ctx.dir, rel_dir, target))
    return any(os.path.exists(p) for p in probes) or ctx.virtual_has(target)


def check_references(ctx: Ctx, rel: str) -> None:
    """Find path-like and markdown-link references to files that do not exist."""
    fence = False
    rel_dir = os.path.dirname(rel)
    for i, ln in enumerate(RE_LINE_SPLIT.split(ctx.texts[rel])):
        if RE_FENCE_TOGGLE.search(ln):
            fence = not fence
            continue
        if fence:
            continue  # paths inside examples are not references
        targets = [RE_TRAILING_PUNCT.sub('', m.group(1)) for m in RE_REF_PATH.finditer(ln)]
        targets += [m.group(1) for m in RE_MD_LINK.finditer(ln)]
        for t in targets:
            if not RE_GLOB_CHARS.search(t) and not reference_exists(ctx, rel_dir, t):
                ctx.add({'id': 'STR07', 'file': rel, 'line': i + 1, 'evidence': t,
                         'confidence': 0.8})


def capability_checks(ctx: Ctx, info: SkillInfo, skill_text: str | None) -> None:
    """Compare what the scripts do with what SKILL.md says and grants."""
    if skill_text is None:
        return
    doc = (skill_text + ' ' + info.description).lower()
    code_files = [r for r in ctx.texts if kind_of(r) in ('script', 'hook')]
    has = {'net': 0, 'exec': 0, 'write': 0, 'cred': 0, 'env': 0}
    for rel in code_files:
        t = ctx.texts[rel]
        has['net'] += 1 if RE_USES_NET.search(t) else 0
        has['exec'] += 1 if RE_USES_EXEC.search(t) else 0
        has['write'] += 1 if RE_USES_WRITE.search(t) else 0
        has['cred'] += 1 if ctx.caps.get(rel, {}).get('cred') else 0
        has['env'] += 1 if RE_USES_ENV.search(t) else 0
    if has['net'] and not RE_MENTION_NET.search(doc):
        ctx.add({'id': 'PRM01', 'file': 'SKILL.md', 'confidence': 0.6,
                 'evidence': (f"{has['net']} script(s) make network calls, "
                              'but SKILL.md never mentions the network')})
    if has['cred'] and not RE_MENTION_CRED.search(doc):
        ctx.add({'id': 'PRM01', 'severity': 'high', 'file': 'SKILL.md', 'confidence': 0.7,
                 'evidence': (f"{has['cred']} script(s) touch credential or key files, "
                              'but SKILL.md never mentions credentials')})
    if has['env'] and not RE_MENTION_ENV.search(doc):
        ctx.add({'id': 'PRM01', 'severity': 'low', 'file': 'SKILL.md', 'confidence': 0.5,
                 'evidence': 'scripts read environment variables that SKILL.md does not mention'})
    tools = info.allowed_tools
    if code_files and (has['exec'] or has['net'] or has['write']) and not tools:
        ctx.add({'id': 'PRM03', 'file': 'SKILL.md', 'confidence': 0.5,
                 'evidence': f'{len(code_files)} script(s), no allowed-tools'})
    if any(RE_WEB_TOOL.search(g) for g in tools) and not has['net'] and not RE_DOC_WEB.search(doc):
        ctx.add({'id': 'PRM04', 'file': 'SKILL.md', 'confidence': 0.45,
                 'evidence': 'network tools granted but nothing in the skill uses them'})
    if any(RE_WRITE_TOOL.search(g) for g in tools) and not has['write'] and not RE_DOC_WRITE.search(
        doc
    ):
        ctx.add({'id': 'PRM04', 'file': 'SKILL.md', 'confidence': 0.45,
                 'evidence': 'write tools granted but nothing in the skill writes'})
    used = list(dict.fromkeys(ext_of(r) for r in code_files if kind_of(r) == 'script'))
    for e in used:
        rt = RUNTIME_BY_EXT.get(e)
        if rt and not rt.search(skill_text):
            ctx.add({'id': 'PRT03', 'file': 'SKILL.md', 'confidence': 0.7,
                     'evidence': f'{e} scripts, runtime not named'})
    if RE_FUTURE_PERMISSIONS.search(skill_text):
        sentence = RE_PERMISSION_SENTENCE.search(skill_text)
        ctx.add({'id': 'PRM05', 'file': 'SKILL.md', 'confidence': 0.6,
                 'evidence': sentence.group(0)[:120] if sentence else ''})
