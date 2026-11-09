#!/usr/bin/env python3
"""Build the deterministic audit checklist: .appsec-audit/coverage.json.

Same commit + same rules + same depth => the same checklist, every time.
  - files: tracked and untracked-but-not-ignored files (git), minus fixed exclusions
  - items: every rule hit (patterns, entry points, secrets) with a stable ID
  - secret-history items (Standard and Deep): secrets added anywhere in git history
  - packages: parsed from lockfiles and manifests (lib/lockfiles.py)

Usage: python -I inventory.py [--root <repo>] [--depth quick|standard|deep]
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write .pyc files next to the scripts

if sys.version_info < (3, 12):
    sys.stderr.write(f'appsec-auditor needs Python 3.12 or newer; found {sys.version.split()[0]}\n')
    raise SystemExit(2)

import json  # noqa: E402
import os  # noqa: E402
import posixpath  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, NamedTuple  # noqa: E402

# `python -I` drops the script directory from sys.path. Add only this script's own directory.
_HERE = str(Path(__file__).resolve().parent)
if not sys.path or sys.path[0] != _HERE:
    sys.path.insert(0, _HERE)

from lib import lockfiles, net, pathglob  # noqa: E402
from lib.cliutil import (  # noqa: E402
    arg_value, configure_streams, run_git, sha1_hex, utc_now_iso,
)

__all__ = ['main']

# Fixed exclusions, so every run scans the same set. Vendored code is still parsed for packages.
EXCLUDE: list[str] = [
    '.appsec-audit/**', '.git/**', '**/node_modules/**', '**/vendor/**', '**/dist/**', '**/build/**',
    '**/target/**', '**/out/**', '**/.next/**', '**/.nuxt/**', '**/coverage/**', '**/__pycache__/**',
    '**/.venv/**', '**/venv/**', '**/.terraform/**', '**/cdk.out/**', '**/bin/Debug/**',
    '**/bin/Release/**', '**/obj/**', '**/*.min.js', '**/*.min.css', '**/*.map',
]
BINARY = re.compile(
    r'\.(png|jpe?g|gif|bmp|ico|webp|svgz|pdf|zip|gz|tgz|bz2|xz|7z|rar|jar|war|ear|class|dll|exe|so'
    r'|dylib|a|o|bin|woff2?|ttf|otf|eot|mp[34]|mov|avi|wav|ogg|psd|sqlite|db|keystore|pyc)\Z',
    re.IGNORECASE | re.ASCII,
)
MAX_BYTES = 2 * 1024 * 1024

STACK_SIGNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern, re.ASCII)) for name, pattern in [
        ('java', r'\.java\Z|(^|/)pom\.xml\Z|build\.gradle(\.kts)?\Z'),
        ('kotlin', r'\.kts?\Z'),
        ('csharp', r'\.(cs|csproj|cshtml|razor)\Z'),
        ('javascript', r'\.(m?js|cjs|ts|tsx|jsx)\Z|(^|/)package\.json\Z'),
        ('frontend', r'\.(tsx|jsx|vue|svelte|html)\Z|(^|/)angular\.json\Z'),
        ('python', r'\.py\Z|(^|/)(pyproject\.toml|requirements[^/]*\.txt)\Z'),
        ('go', r'\.go\Z|(^|/)go\.mod\Z'),
        ('rust', r'\.rs\Z|(^|/)Cargo\.toml\Z'),
        ('terraform', r'\.tf\Z'),
        ('cdk', r'(^|/)cdk\.json\Z'),
        ('cloudformation', r'\.(template|cfn)\.(json|ya?ml)\Z'),
        ('kubernetes', r'(^|/)(k8s|kubernetes|helm|charts|manifests)/.*\.ya?ml\Z|(^|/)Chart\.yaml\Z'),
        ('docker', r'(^|/)(Dockerfile[^/]*|[^/]*\.Dockerfile|docker-compose[^/]*\.ya?ml|compose\.ya?ml)\Z'),
        ('cicd', r'(^|/)(\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.yml|Jenkinsfile|buildspec[^/]*\.ya?ml'
                 r'|azure-pipelines\.yml|bitbucket-pipelines\.yml)\Z'),
    ]
]
COMMENT_LINE = re.compile(r'^\s*(//|/\*|\*|#|<!--)')
WHITESPACE = re.compile(r'[\s\ufeff]+')
LINE_SPLIT = re.compile(r'\r?\n')
HISTORY_MARK = '@@appsec-commit '


class CliError(Exception):
    """A usage or input error reported on stderr with exit status 1."""


class Rule(NamedTuple):
    """One entry of rules.json with its compiled pattern."""

    data: dict[str, Any]
    regex: re.Pattern[str]

    @property
    def kind(self) -> str:
        """The rule kind (pattern, entrypoint, secret)."""
        return str(self.data.get('kind', ''))

    @property
    def rule_id(self) -> str:
        """The rule ID."""
        return str(self.data['id'])


def normalize(line: str) -> str:
    """Trim a source line and collapse every run of white space to one space."""
    return WHITESPACE.sub(' ', line).strip()


def redact_line(line: str, regex: re.Pattern[str]) -> str:
    """Secret values never go into coverage.json: keep at most 4 characters of each."""
    return regex.sub(lambda m: f'{m.group(0)[:4]}****', line)


def read_text(path: str) -> str:
    """Read a file as UTF-8, replacing invalid bytes."""
    with open(path, 'rb') as handle:
        return handle.read().decode('utf-8', 'replace')


def walk_files(root: str) -> list[str]:
    """List regular files below ``root`` without following symlinks or junctions."""
    found: list[str] = []
    stack = ['']
    while stack:
        rel_dir = stack.pop()
        try:
            with os.scandir(os.path.join(root, rel_dir) if rel_dir else root) as entries:
                listing = list(entries)
        except OSError as exc:
            sys.stderr.write(f'warning: cannot read directory {rel_dir or "."}: {exc.strerror}\n')
            continue
        for entry in listing:
            rel = f'{rel_dir}/{entry.name}' if rel_dir else entry.name
            if entry.is_symlink() or entry.is_junction():
                continue
            if entry.is_dir(follow_symlinks=False):
                if entry.name != '.git':
                    stack.append(rel)
            elif entry.is_file(follow_symlinks=False):
                found.append(rel)
    return found


def list_files(root: str) -> tuple[bool, list[str]]:
    """Return (is_git, sorted unique repo-relative paths with forward slashes)."""
    code, out = run_git(root, ['rev-parse', '--is-inside-work-tree'])
    is_git = code is not None and out.strip() == 'true'
    if is_git:
        _, listing = run_git(root, ['ls-files', '-z', '--cached', '--others', '--exclude-standard'])
        files = [f for f in listing.split('\0') if f]
    else:
        files = walk_files(root)
    return is_git, sorted({f.replace('\\', '/') for f in files})


def select_files(root: str, all_files: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Apply the fixed exclusions and size limit; return (scanned, skipped)."""
    scanned: list[str] = []
    skipped: list[dict[str, str]] = []
    for rel in all_files:
        if pathglob.matches_any(rel, EXCLUDE) or BINARY.search(rel):
            continue
        try:
            size = os.stat(os.path.join(root, rel)).st_size
        except (OSError, ValueError):
            continue
        if size > MAX_BYTES:
            skipped.append({'file': rel, 'reason': f'larger than {MAX_BYTES} bytes'})
            continue
        scanned.append(rel)
    return scanned, skipped


def load_rules(skill_dir: Path) -> tuple[dict[str, Any], list[Rule]]:
    """Read rules/rules.json and compile every pattern (ASCII \\w, \\d, \\b as in the JavaScript rules)."""
    with open(skill_dir / 'rules' / 'rules.json', encoding='utf-8') as handle:
        doc = json.load(handle)
    rules = []
    for raw in doc['rules']:
        flags = str(raw.get('flags') or '')
        opts = re.ASCII | (re.IGNORECASE if 'i' in flags else 0) | (re.MULTILINE if 'm' in flags else 0)
        opts |= re.DOTALL if 's' in flags else 0
        rules.append(Rule(raw, re.compile(raw['pattern'], opts)))
    return doc, rules


def applies(rule: Rule, rel: str) -> bool:
    """Whether the rule's include/exclude globs select this file."""
    return (pathglob.matches_any(rel, rule.data.get('include') or [])
            and not pathglob.matches_any(rel, rule.data.get('exclude') or []))


def find_hits(rule: Rule, text: str, lines: list[str]) -> list[int]:
    """Return the 1-based line numbers where the rule matches."""
    if 's' in str(rule.data.get('flags') or ''):  # multi-line rule: match over the whole text
        return list(dict.fromkeys(text.count('\n', 0, m.start()) + 1 for m in rule.regex.finditer(text)))
    skip_comments = rule.kind == 'entrypoint'
    hits = []
    for i, line in enumerate(lines):
        if skip_comments and COMMENT_LINE.search(line):
            continue  # an entry point mentioned in a comment or Javadoc isn't an entry point
        if rule.regex.search(line):
            hits.append(i + 1)
    return hits


def scan_file(rel: str, text: str, applicable: list[Rule]) -> list[dict[str, Any]]:
    """Return the checklist items for one file."""
    lines = LINE_SPLIT.split(text)
    items: list[dict[str, Any]] = []
    for rule in applicable:
        seen: dict[str, int] = {}
        for line_no in find_hits(rule, text, lines):
            norm = normalize(lines[line_no - 1] if line_no - 1 < len(lines) else '')
            # Stable across line shifts: rule + file + line content + occurrence among identical lines.
            seen[norm] = seen.get(norm, 0) + 1
            excerpt = (redact_line(norm, rule.regex) if rule.kind == 'secret' else norm)[:200]
            digest = sha1_hex('|'.join([rule.rule_id, rel, norm, str(seen[norm])]))[:12]
            items.append({
                'id': f'C-{digest}', 'kind': rule.kind, 'rule': rule.rule_id, 'cwe': rule.data.get('cwe') or '',
                'file': rel, 'line': line_no, 'excerpt': excerpt, 'guide': rule.data.get('guide') or '',
            })
    return items


def scan_items(root: str, scanned: list[str], rules: list[Rule]) -> list[dict[str, Any]]:
    """Run every applicable rule over every scanned file."""
    items: list[dict[str, Any]] = []
    for rel in scanned:
        applicable = [r for r in rules if applies(r, rel)]
        if not applicable:
            continue
        try:
            text = read_text(os.path.join(root, rel))
        except (OSError, ValueError):
            continue
        if '\0' in text:
            continue
        items.extend(scan_file(rel, text, applicable))
    return items


def scan_history(root: str, rules: list[Rule]) -> tuple[list[dict[str, Any]], int]:
    """Secrets added in any commit on any branch; return (items, commit count)."""
    secret_rules = [r for r in rules if r.kind == 'secret']
    _, out = run_git(root, ['log', '--all', '-p', '--no-color', '--no-ext-diff', '--no-textconv', '-U0',
                            f'--format={HISTORY_MARK}%H %ad', '--date=short'])
    found: dict[str, dict[str, Any]] = {}
    commits = 0
    sha = date = file = ''
    file_rules: list[Rule] = []
    rules_for: dict[str, list[Rule]] = {}
    for line in out.split('\n'):
        if line.startswith(HISTORY_MARK):
            commits += 1
            parts = line.split(' ')
            sha, date = parts[1], (parts[2] if len(parts) > 2 else '')
        elif line.startswith('+++ '):
            file = line[4:].removeprefix('b/')
            if file not in rules_for:
                rules_for[file] = [r for r in secret_rules if applies(r, file)]
            file_rules = rules_for[file]
        elif line.startswith('+') and not line.startswith('+++') and file_rules:
            for rule in file_rules:
                match = rule.regex.search(line[1:])
                if match:
                    value_hash = sha1_hex(match.group(0))
                    # git log lists newest first, so the last one seen is where the secret was introduced.
                    found[f'{rule.rule_id}|{file}|{value_hash}'] = {
                        'rule': rule, 'file': file, 'commit': sha, 'date': date, 'valueHash': value_hash[:12],
                        'excerpt': redact_line(normalize(line[1:]), rule.regex)[:200],
                    }
    items = []
    for key in sorted(found):
        h = found[key]
        items.append({
            'id': 'H-' + sha1_hex(key)[:12], 'kind': 'secret-history', 'rule': h['rule'].rule_id,
            'cwe': h['rule'].data.get('cwe') or 'CWE-798', 'file': h['file'], 'commit': h['commit'],
            'date': h['date'], 'excerpt': h['excerpt'], 'valueHash': h['valueHash'],
            'fileStillExists': os.path.exists(os.path.join(root, h['file'].lstrip('/\\'))),
        })
    return items, commits


def sort_items(items: list[dict[str, Any]]) -> None:
    """Order items by file, line, rule, ID (case-insensitive, then exact)."""
    items.sort(key=lambda it: (
        it.get('file', '').casefold(), it.get('file', ''), it.get('line', 0),
        it['rule'].casefold(), it['rule'], it['id'],
    ))


def merge_packages(deps: dict[str, Any]) -> None:
    """Drop unresolved dependencies a sibling manifest resolved; merge duplicate packages."""
    def folder(entry: dict[str, Any]) -> str:
        """The directory part of the entry's file."""
        return posixpath.dirname(str(entry.get('file', '')))

    resolved = {f"{p['ecosystem']}|{p['name']}|{folder(p)}" for p in deps['packages']}
    deps['unresolved'] = [u for u in deps['unresolved'] if f"{u['ecosystem']}|{u['name']}|{folder(u)}" not in resolved]
    # The same package and version from two sibling build files is one package: keep the first
    # file (packages are sorted), and record the others, so one advisory makes one checklist item.
    merged: dict[str, dict[str, Any]] = {}
    for pkg in deps['packages']:
        key = f"{pkg['ecosystem']}|{pkg['name']}|{pkg['version']}|{folder(pkg)}"
        kept = merged.get(key)
        if kept is None:
            merged[key] = dict(pkg)
            continue
        also = set(kept.get('alsoIn') or []) | {pkg['file']}
        kept['alsoIn'] = sorted(f for f in also if f != kept['file'])
        if 'direct' in kept or 'direct' in pkg:
            kept['direct'] = bool(kept.get('direct') or pkg.get('direct'))
    deps['packages'] = list(merged.values())


def git_state(root: str, is_git: bool) -> tuple[str, int]:
    """Return (HEAD commit or 'none', number of uncommitted changes outside .appsec-audit)."""
    if not is_git:
        return 'none', 0
    _, head = run_git(root, ['rev-parse', 'HEAD'])
    _, status = run_git(root, ['status', '--porcelain'])
    dirty = len([ln for ln in status.split('\n') if ln and '.appsec-audit/' not in ln])
    return head.strip() or 'none', dirty


def write_outputs(root: str, coverage: dict[str, Any], scanned: list[str]) -> None:
    """Write coverage.json and files.txt under .appsec-audit."""
    audit_dir = Path(root) / '.appsec-audit'
    audit_dir.mkdir(parents=True, exist_ok=True)
    with open(audit_dir / 'coverage.json', 'w', encoding='utf-8', newline='') as handle:
        handle.write(json.dumps(coverage, indent=2, ensure_ascii=False))
    with open(audit_dir / 'files.txt', 'w', encoding='utf-8', newline='') as handle:
        handle.write('\n'.join(scanned) + '\n')


def build(root: str, depth: str) -> None:
    """Build the checklist for ``root`` and write the outputs."""
    rules_doc, rules = load_rules(Path(_HERE).parent)
    is_git, all_files = list_files(root)
    commit, dirty = git_state(root, is_git)
    scanned, skipped = select_files(root, all_files)
    stacks = [name for name, regex in STACK_SIGNS if any(regex.search(f) for f in scanned)]

    items = scan_items(root, scanned, rules)
    history: dict[str, Any] = {'scanned': False}
    if is_git and depth != 'quick':
        history_items, commits = scan_history(root, rules)
        items.extend(history_items)
        history = {'scanned': True, 'branches': 'all', 'commits': commits}
    sort_items(items)

    # Packages from lockfiles and manifests; Maven parent/BOM resolution through the network layer.
    deps = lockfiles.parse_lockfiles(
        root, [f for f in all_files if not f.startswith('.appsec-audit/')],
        {'fetchText': net.get_text, 'mavenBase': net.ENDPOINTS['maven']},
    )
    merge_packages(deps)

    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item['kind']] = by_kind.get(item['kind'], 0) + 1
    coverage = {
        'schema': 1, 'tool': 'appsec-auditor', 'rulesVersion': rules_doc['version'], 'root': root,
        'commit': commit, 'uncommittedChanges': dirty, 'depth': depth, 'generatedAt': utc_now_iso(),
        'stacks': stacks, 'files': {'count': len(scanned), 'skipped': skipped}, 'history': history,
        'counts': by_kind, 'items': items, 'packages': deps['packages'], 'unresolved': deps['unresolved'],
        'lockfileSources': deps['sources'],
    }
    write_outputs(root, coverage, scanned)

    note = f' (+{dirty} uncommitted changes)' if dirty else ''
    print(f"commit={commit[:12]}{note} depth={depth} rules={rules_doc['version']} files={len(scanned)} "
          f"stacks={','.join(stacks) or '-'}")
    print(f"items={len(items)} {' '.join(f'{k}={v}' for k, v in by_kind.items())}")
    tail = f" history_commits={history['commits']}" if history['scanned'] else ''
    print(f"packages={len(deps['packages'])} unresolved={len(deps['unresolved'])} "
          f"manifests={len(deps['sources'])}{tail}")
    if dirty:
        print('Note: the working tree has uncommitted changes, so the checklist reflects files on disk, '
              'not only the commit.')


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit status."""
    configure_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        root_arg = arg_value(args, '--root', os.getcwd())
        depth_arg = arg_value(args, '--depth', 'standard')
        if root_arg is None or depth_arg is None:
            raise CliError('missing value after --root or --depth')
        depth = depth_arg.lower()
        if depth not in ('quick', 'standard', 'deep'):
            raise CliError(f'unknown depth: {depth}')
        root = os.path.abspath(root_arg)
        if not os.path.isdir(root):
            raise CliError(f'not a directory: {root}')
        build(root, depth)
    except (CliError, OSError, ValueError, KeyError) as exc:
        sys.stderr.write(f'Error: {exc}\n')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
