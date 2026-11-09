#!/usr/bin/env python3
"""Show the context of a secret checklist item with every secret value redacted.

Judging an item never prints the secret into the conversation (SKILL.md rule 7).
Usage: python -I secret-context.py --root <repo> --id <C-... or H-... item ID> [--lines 4]
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

from lib.cliutil import arg_value, configure_streams, read_json, run_git  # noqa: E402

__all__ = ['main']

LINE_SPLIT = re.compile(r'\r?\n')
DIFF_MARKER = re.compile(r'[+\- ]')
FILE_HEADER = re.compile(r'(\+\+\+|---) ')


def secret_rules(skill_dir: Path) -> list[re.Pattern[str]]:
    """The compiled patterns of every secret rule in rules.json (ASCII \\w, \\d, \\b)."""
    with open(skill_dir / 'rules' / 'rules.json', encoding='utf-8') as handle:
        doc = json.load(handle)
    return [re.compile(r['pattern'], re.ASCII | (re.IGNORECASE if 'i' in (r.get('flags') or '') else 0))
            for r in doc['rules'] if r.get('kind') == 'secret']


def redact(line: str, rules: list[re.Pattern[str]]) -> str:
    """Redact secret values in one line. Diff lines start with "+", "-", or " "; strip that first."""
    marker = line[:1] if DIFF_MARKER.match(line) and not FILE_HEADER.match(line) else ''
    out = line[1:] if marker else line
    for regex in rules:
        out = regex.sub(lambda m: f'{m.group(0)[:4]}****', out)
    return marker + out


def context_lines(root: str, item: dict[str, Any], around: int) -> tuple[list[str], int]:
    """The lines to show and the number of the first one."""
    if item['kind'] == 'secret':
        with open(os.path.join(root, item['file']), 'rb') as handle:
            text = LINE_SPLIT.split(handle.read().decode('utf-8', 'replace'))
        start = max(1, item['line'] - around)
        return text[start - 1:item['line'] + around], start
    # No external diff or text conversion programs from the repository's own config.
    fmt = '--format=commit %H%nDate: %ad%n%n    %s'
    _, out = run_git(root, ['show', '--no-color', '--no-ext-diff', '--no-textconv', fmt, '--date=short',
                            str(item['commit']), '--', str(item['file'])])
    return out.split('\n'), 1


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit status."""
    configure_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    root_arg = arg_value(args, '--root', os.getcwd())
    if root_arg is None:
        sys.stderr.write('Error: missing value after --root\n')
        return 1
    root = os.path.abspath(root_arg)
    item_id = arg_value(args, '--id')
    try:
        around = max(0, int(arg_value(args, '--lines', '4') or ''))
    except ValueError:
        sys.stderr.write('Error: --lines needs a whole number\n')
        return 2
    coverage = read_json(Path(root) / '.appsec-audit' / 'coverage.json')
    if not isinstance(coverage, dict):
        sys.stderr.write('Error: cannot read .appsec-audit/coverage.json\n')
        return 1
    item = next((it for it in coverage.get('items') or [] if isinstance(it, dict) and it.get('id') == item_id), None)
    if item is None or item.get('kind') not in ('secret', 'secret-history'):
        sys.stderr.write(f'No secret item with ID {item_id}.\n')
        return 1
    try:
        rules = secret_rules(Path(_HERE).parent)
        lines, start = context_lines(root, item, around)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f'Error: {exc}\n')
        return 1

    where = f"{item['file']}{f':{item['line']}' if item.get('line') else ''}"
    commit = f" @ {item['commit'][:12]}" if item.get('commit') else ''
    print(f"{item['id']} {item['kind']} {item.get('rule')} {where}{commit}")
    for i, text in enumerate(lines):
        print(f'{start + i:>5}  {redact(text, rules)}' if item['kind'] == 'secret' else redact(text, rules))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
