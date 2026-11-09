#!/usr/bin/env python3
"""skill-auditor mechanical pass. Python 3.12+, standard library only.

Usage:
    python -I lint.py <skill-folder | folder-of-skills | SKILL.md | file | .zip> [options]

Run ``python -I lint.py --help`` for the option list.

Reads a skill (or a folder of skills, a single file, or a .zip) and reports leads for the AI
reviewer: pattern findings with context, taint flows, archive and image inspection, dependency
checks, hook and settings review, a coverage ledger, a mechanical risk score, and output as JSON,
Markdown, terminal, or SARIF. It only reads. It never runs, installs, or writes anything in the
audited skill (the optional --out and --make-baseline files are written where the caller says).

This file is only the entry point; the code lives in the ``lib`` package next to it.

Exit codes: 0 passed, 1 a gate failed, 2 usage or input error.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write .pyc files into the audited or the installed folders

if sys.version_info < (3, 12):
    sys.stderr.write(f'skill-auditor needs Python 3.12 or newer; found {sys.version.split()[0]}\n')
    raise SystemExit(2)

import os  # noqa: E402

# `python -I` drops the script directory from sys.path. Add only this script's own directory, never
# the current directory or the audited folder.
_HERE = os.path.dirname(os.path.abspath(__file__))
if not sys.path or sys.path[0] != _HERE:
    sys.path.insert(0, _HERE)

from lib.audit import VERSION, audit_path  # noqa: E402
from lib.cli import main  # noqa: E402

__all__ = ['VERSION', 'audit_path', 'main']

if __name__ == '__main__':
    raise SystemExit(main())
