#!/usr/bin/env python3
"""Check that the vulnerability-data endpoints are reachable with the current proxy settings.

Says exactly what to fix when they aren't. Usage: python -I net-check.py [--json]
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write .pyc files next to the scripts

if sys.version_info < (3, 12):
    sys.stderr.write(f'appsec-auditor needs Python 3.12 or newer; found {sys.version.split()[0]}\n')
    raise SystemExit(2)

import json  # noqa: E402
from collections.abc import Callable  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

# `python -I` drops the script directory from sys.path. Add only this script's own directory.
_HERE = str(Path(__file__).resolve().parent)
if not sys.path or sys.path[0] != _HERE:
    sys.path.insert(0, _HERE)

from lib import net  # noqa: E402
from lib.cliutil import configure_streams  # noqa: E402

__all__ = ['main']

MAVEN_PROBE = '/org/springframework/boot/spring-boot-starter-parent/maven-metadata.xml'


def checks() -> list[tuple[str, Callable[[], dict[str, Any]]]]:
    """The endpoint probes, in report order (Maven Central last: only Maven/Gradle needs it)."""
    endpoints = net.ENDPOINTS
    left_pad = {'queries': [{'package': {'ecosystem': 'npm', 'name': 'left-pad'}, 'version': '1.3.0'}]}
    return [
        ('OSV.dev', lambda: net.post_json(f"{endpoints['osv']}/querybatch", left_pad)),
        ('CISA KEV', lambda: net.request({'url': endpoints['kev']})),
        ('FIRST EPSS', lambda: net.get_json(f"{endpoints['epss']}?cve=CVE-2021-44228")),
        ('Maven Central', lambda: net.request({'url': f"{endpoints['maven']}{MAVEN_PROBE}"})),
    ]


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit status."""
    configure_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    config = net.describe_config()
    results = []
    for name, probe in checks():
        r = probe()
        results.append({'name': name, 'ok': r['ok'], 'status': r['status'],
                        'category': r.get('category') or '', 'hint': r.get('hint') or ''})

    if '--json' in args:
        sys.stdout.write(json.dumps({'config': config, 'results': results}, indent=2, ensure_ascii=False) + '\n')
        return 0
    source = f" ({config['proxySource']})" if config['proxySource'] else ''
    no_proxy = f" no_proxy={config['noProxy']}" if config['noProxy'] else ''
    print(f"proxy={config['proxy']}{source} auth={config['proxyAuth']} ca={config['caBundle']}{no_proxy}")
    for r in results:
        detail = f"HTTP {r['status']}" if r['ok'] else f"{r['category']}: {r['hint']}"
        print(f"{'OK  ' if r['ok'] else 'FAIL'} {r['name'].ljust(14)} {detail}")
    # Maven Central is needed only for Maven/Gradle version resolution.
    if all(r['ok'] for r in results[:3]):
        print('Vulnerability data: reachable.')
    else:
        print('Vulnerability data: NOT reachable. Dependency results will be marked "not checked" until this is fixed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
