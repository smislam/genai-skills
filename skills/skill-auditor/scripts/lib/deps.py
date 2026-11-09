"""Dependency and package-manager checks for files shipped inside a skill.

Covers manifests, lockfiles, registry redirection, install-time scripts, look-alike package
names, and (opt-in) live OSV.dev and CISA KEV lookups through curl, which follows the standard
proxy variables.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .util import RE_LINE_SPLIT, as_text, dump_json, error_text, get_key, iter_items, parse_json

__all__ = ['analyze', 'osv_lookup', 'INSTALL_SCRIPTS']

POPULAR_NPM: list[str] = (
    'react react-dom lodash express axios moment chalk commander debug async request underscore '
    'bluebird webpack typescript jquery vue angular next eslint prettier jest mocha chai babel-core '
    'dotenv uuid yargs minimist glob rimraf mkdirp semver tslib rxjs core-js classnames body-parser '
    'cors cookie-parser mongoose mysql pg redis socket.io passport jsonwebtoken bcrypt nodemon '
    'inquirer ora colors fs-extra cheerio puppeteer playwright cypress zod tailwindcss postcss sass '
    'less vite rollup esbuild lodash-es date-fns dayjs ramda immer redux mobx node-fetch got '
    'superagent winston pino morgan helmet multer sharp ws yaml js-yaml marked handlebars ejs pug '
    'underscore.string left-pad nanoid ioredis knex sequelize typeorm prisma graphql apollo-server '
    'cross-env concurrently husky lint-staged'
).split(' ')
POPULAR_PYPI: list[str] = (
    'requests numpy pandas scipy matplotlib flask django fastapi pytest setuptools wheel pip six '
    'urllib3 certifi idna chardet charset-normalizer boto3 botocore awscli pyyaml jinja2 markupsafe '
    'click cryptography pillow sqlalchemy psycopg2 pymysql redis celery beautifulsoup4 lxml '
    'scikit-learn tensorflow torch keras httpx aiohttp pydantic uvicorn gunicorn tqdm rich typer '
    'attrs packaging python-dateutil pytz tzdata colorama openpyxl paramiko pyjwt docker kubernetes '
    'selenium scrapy nltk spacy transformers openai anthropic langchain black flake8 mypy isort '
    'pylint coverage tox poetry virtualenv pipenv twine'
).split(' ')
LEGIT_NEIGHBORS: set[str] = {
    'pytz', 'pytest', 'chai', 'colors', 'color', 'debug', 'ora', 'ws', 'got', 'pg', 'vue', 'next',
    'less', 'sass', 'zod', 'pino', 'yaml', 'marked', 'knex', 'ejs', 'pug', 'glob', 'async', 'pip',
    'six', 'attrs', 'rich', 'click', 'black', 'tox', 'keras', 'redux', 'mobx', 'react-dom',
    'lodash-es', 'markupsafe', 'pyyaml', 'pymysql', 'psycopg2',
}
KNOWN_BAD_NPM: set[str] = {
    'crossenv', 'cross-env.js', 'mongose', 'babelcli', 'nodefabric', 'flatmap-stream', 'electorn',
    'loadsh',
}
KNOWN_BAD_PYPI: set[str] = {
    'colourama', 'python3-dateutil', 'jeilyfish', 'urlib3', 'setup-tools', 'acqusition',
    'apidev-coop', 'django-server', 'pytagora', 'pytagora2', 'libpeshnx',
}
ABANDONED_NPM: set[str] = {
    'request', 'request-promise', 'request-promise-native', 'node-uuid', 'gulp-util', 'tslint',
    'bower', 'coffee-script', 'istanbul', 'jade', 'babel-core', 'left-pad', 'node-sass', 'nomnom',
}
ABANDONED_PYPI: set[str] = {
    'pycrypto', 'nose', 'distribute', 'pep8', 'simplejson2', 'mock', 'optparse', 'argparse',
    'pyyaml2', 'python-jose',
}
ABANDONED_NOTE: dict[str, str] = {
    'request': 'deprecated since 2020',
    'node-sass': 'deprecated; use sass',
    'tslint': 'deprecated; use eslint',
    'pycrypto': 'unmaintained since 2013; use pycryptodome',
    'nose': 'unmaintained; use pytest',
    'node-uuid': 'deprecated; use uuid',
    'gulp-util': 'deprecated',
    'bower': 'deprecated',
    'istanbul': 'deprecated; use nyc',
    'jade': 'renamed to pug',
}

INSTALL_SCRIPTS: list[str] = [
    'preinstall', 'install', 'postinstall', 'prepare', 'prepublish', 'prepublishOnly', 'prepack',
    'postpack',
]

_A = re.ASCII
_I = re.IGNORECASE

# Config files that can redirect a package manager (matched on a forward-slash path).
CONFIG_FILES: re.Pattern[str] = re.compile(
    r'(^|/)(\.npmrc|\.yarnrc|\.yarnrc\.yml|pip\.conf|pip\.ini|\.pypirc|settings\.xml|\.condarc'
    r'|nuget\.config|config(\.toml)?|\.bunfig\.toml|bunfig\.toml)\Z', _I)
# Hosts that are normal package sources.
REGISTRY_OK: re.Pattern[str] = re.compile(
    r'(registry\.npmjs\.org|registry\.yarnpkg\.com|pypi\.org|files\.pythonhosted\.org'
    r'|repo\.maven\.apache\.org|repo1\.maven\.org|crates\.io|index\.crates\.io|static\.crates\.io'
    r'|rubygems\.org|proxy\.golang\.org|github\.com|codeload\.github\.com)\Z', _I)

AddFn = Callable[[str, str, str, int, str, str, float], None]
CheckNameFn = Callable[[str, str, str, str], None]


def osa(a: str, b: str) -> int:
    """Return the optimal string alignment distance (edits plus adjacent transpositions)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def line_of(text: str, needle: str) -> int:
    """Return the 1-based line of the first occurrence of needle (1 when missing)."""
    i = text.find(needle)
    return 1 if i < 0 else len(RE_LINE_SPLIT.split(text[:i]))


def typo(eco: str, raw_name: str) -> dict[str, Any] | None:
    """Return a look-alike verdict for a package name, or None."""
    name = raw_name.lower().replace('_', '-')
    popular = POPULAR_NPM if eco == 'npm' else POPULAR_PYPI
    bad = KNOWN_BAD_NPM if eco == 'npm' else KNOWN_BAD_PYPI
    if name in bad:
        return {'sev': 'high', 'msg': 'Name matches a package reported as a malicious look-alike; '
                'verify it on the registry', 'conf': 0.85}
    if name.startswith('@') or name in popular or name in LEGIT_NEIGHBORS:
        return None
    for p in popular:
        if abs(len(p) - len(name)) > 1:
            continue
        d = osa(name, p)
        if (d == 1 and len(name) >= 5) or (d == 2 and len(name) >= 10):
            plural = 's' if d > 1 else ''
            msg = f'Name is {d} edit{plural} from the popular package "{p}"'
            return {'sev': 'medium', 'msg': msg, 'conf': 0.55 if d == 1 else 0.4}
    return None


_WEB_SCHEMES = frozenset({'http', 'https', 'ftp', 'ws', 'wss'})


def parse_url(s: str) -> tuple[str, str] | None:
    """(scheme, host) of an absolute URL, or None when it is malformed or a web URL has no host."""
    try:
        parts = urllib.parse.urlsplit(s.strip())
    except ValueError:
        return None
    host = parts.hostname
    if not parts.scheme or (parts.scheme in _WEB_SCHEMES and not host):
        return None
    return parts.scheme, host or ''


_RE_REQ_FILE = re.compile(r'requirements.*\.txt\Z')
_RE_DOCKERFILE = re.compile(r'dockerfile')
_RE_DOCKERFILE_EXT = re.compile(r'\.dockerfile\Z')
_RE_COMPOSE = re.compile(r'docker-compose.*\.ya?ml\Z')
_RE_WORKFLOW = re.compile(r'(^|/)\.github/workflows/.+\.ya?ml\Z')
_RE_CFG_EXT = re.compile(r'\.(npmrc|yarnrc|condarc|pypirc)')
_RE_PIP_CFG = re.compile(r'pip\.(conf|ini)\Z')
_RE_BUNFIG = re.compile(r'bunfig')
_RE_CARGO_CFG = re.compile(r'(^|/)\.cargo/config')


def _is_config_target(base: str, reln: str) -> bool:
    """Return True when the file is a package-manager config worth scanning."""
    if not CONFIG_FILES.search(reln):
        return False
    return bool(
        _RE_CFG_EXT.search(base) or _RE_PIP_CFG.match(base) or base == 'settings.xml'
        or base == 'nuget.config' or _RE_BUNFIG.search(base) or _RE_CARGO_CFG.search(reln))


def analyze(files: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    """Scan dependency-related files ({'rel','text'} dicts) and return findings and packages."""
    findings: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []

    def add(id_: str, severity: str, file: str, line: int, message: str, evidence: str,
            confidence: float) -> None:
        """Record one finding."""
        findings.append({
            'id': id_, 'severity': severity, 'file': file, 'line': line or 1, 'message': message,
            'evidence': evidence or '', 'confidence': confidence or 0.75, 'surface': 'config'})

    def check_name(eco: str, name: str, file: str, text: str) -> None:
        """Flag look-alike and abandoned package names."""
        t = typo(eco, name)
        if t:
            add('SUP06', t['sev'], file, line_of(text, name), t['msg'], name, t['conf'])
        if name.lower() in (ABANDONED_NPM if eco == 'npm' else ABANDONED_PYPI):
            note = ABANDONED_NOTE.get(name.lower())
            suffix = ': ' + note if note else ''
            add('SUP05', 'medium', file, line_of(text, name),
                'Abandoned or deprecated package' + suffix, name, 0.7)

    for fobj in files:
        rel = fobj['rel']
        text = fobj['text']
        reln = rel.replace('\\', '/')
        base = reln.rsplit('/', 1)[-1].lower()
        try:
            _dispatch(rel, text, base, add, check_name, packages)
            if _is_config_target(base, reln):
                config_file(rel, text, add)
        except Exception as exc:  # noqa: BLE001 - one bad manifest must not stop the other checks
            add('COV01', 'low', rel, 1, 'Dependency file could not be parsed', error_text(exc), 0.6)
    return {'findings': findings, 'packages': packages}


def _dispatch(rel: str, text: str, base: str, add: AddFn, check_name: CheckNameFn,
              packages: list[dict[str, Any]]) -> None:
    """Route a file to the parser for its ecosystem."""
    if base == 'package.json':
        pkg_json(rel, text, add, check_name, packages)
    elif base in ('package-lock.json', 'npm-shrinkwrap.json'):
        npm_lock(rel, text, add, packages)
    elif base == 'yarn.lock':
        yarn_lock(rel, text, add)
    elif _RE_REQ_FILE.match(base) or base == 'constraints.txt':
        requirements(rel, text, add, check_name, packages)
    elif base == 'pyproject.toml':
        pyproject(rel, text, add, check_name)
    elif base == 'pipfile':
        pipfile(rel, text, add)
    elif base == 'setup.py':
        setup_py(rel, text, add)
    elif base == 'cargo.lock':
        cargo_lock(rel, text, packages)
    elif base == 'gemfile':
        gemfile(rel, text, add)
    elif base == 'go.mod':
        go_mod(rel, text, add)
    elif base == '.gitmodules':
        gitmodules(rel, text, add)
    elif _RE_DOCKERFILE.match(base) or _RE_DOCKERFILE_EXT.search(base):
        dockerfile(rel, text, add)
    elif _RE_COMPOSE.search(base) or _RE_WORKFLOW.search(rel):
        ci_yaml(rel, text, add)


_RE_GIT_SPEC = re.compile(r'(git\+|git:|github:|gitlab:|bitbucket:|ssh:|git@)', _I)
# owner/repo shorthand, optionally with a #ref.
_RE_SHORTHAND = re.compile(r'[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(#.*)?\Z')
_RE_HTTP_SPEC = re.compile(r'http://', _I)
_RE_HTTPS_SPEC = re.compile(r'https?://', _I)
_RE_LOCAL_SPEC = re.compile(r'(file|link):', _I)
_RE_X_SPEC = re.compile(r'x\Z', _I)
_RE_GE_SPEC = re.compile(r'>=?\s*[0-9]')
_RE_UPPER_BOUND = re.compile(r'<|\|\|')
_RE_OVERRIDE_URL = re.compile(r'https?://[^"]+|git\+[^"]+')
_NPM_DEP_KEYS = ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies')


def _classify_npm_spec(rel: str, text: str, name: str, s: str, add: AddFn) -> None:
    """Report a risky npm dependency specifier."""
    where = line_of(text, name)
    ev = f'{name}: {s}'
    if _RE_GIT_SPEC.match(s) or _RE_SHORTHAND.match(s):
        add(
            'SUP12', 'medium', rel, where,
            'Dependency comes from a Git repository, not a registry release', ev, 0.8,
        )
    elif _RE_HTTP_SPEC.match(s):
        add('SUP12', 'high', rel, where, 'Dependency downloaded over plain HTTP', ev, 0.9)
    elif _RE_HTTPS_SPEC.match(s):
        add('SUP12', 'medium', rel, where, 'Dependency comes from a tarball URL', ev, 0.8)
    elif _RE_LOCAL_SPEC.match(s):
        add('SUP12', 'low', rel, where, 'Dependency comes from a local path', ev, 0.5)
    elif (s in ('', '*', 'latest') or _RE_X_SPEC.match(s)
          or (_RE_GE_SPEC.match(s) and not _RE_UPPER_BOUND.search(s))):
        add('SUP01', 'low', rel, where, 'Unbounded version range', f'{name}: {s or "(empty)"}', 0.6)


def pkg_json(rel: str, text: str, add: AddFn, check_name: CheckNameFn,
             packages: list[dict[str, Any]]) -> None:
    """Check a package.json manifest."""
    try:
        o = parse_json(text)
    except ValueError:
        add('COV01', 'low', rel, 1, 'package.json is not valid JSON', '', 0.6)
        return
    for key in _NPM_DEP_KEYS:
        for name, spec in iter_items(get_key(o, key)):
            check_name('npm', name, rel, text)
            _classify_npm_spec(rel, text, name, as_text(spec).strip(), add)
    scripts = get_key(o, 'scripts')
    for k in INSTALL_SCRIPTS:
        if get_key(scripts, k):
            add('SUP11', 'high', rel, line_of(text, '"' + k + '"'),
                f'Runs "{k}" script when the package is installed',
                f'{k}: {as_text(scripts[k])[:120]}', 0.85)
    for k in ('overrides', 'resolutions'):
        bad = _RE_OVERRIDE_URL.search(as_text(get_key(o, k) or {}))
        if bad:
            add('SUP10', 'high', rel, line_of(text, '"' + k + '"'),
                f'{k} redirect a dependency to a URL', bad.group(0), 0.8)
    reg = get_key(get_key(o, 'publishConfig'), 'registry') or get_key(
        get_key(o, 'config'), 'registry',
    )
    if reg:
        add('SUP10', 'medium', rel, line_of(text, as_text(reg)), 'Package config sets a registry',
            as_text(reg), 0.7)


def npm_lock(rel: str, text: str, add: AddFn, packages: list[dict[str, Any]]) -> None:
    """Check package-lock.json or npm-shrinkwrap.json."""
    try:
        o = parse_json(text)
    except ValueError:
        add('COV01', 'low', rel, 1, 'Lockfile is not valid JSON', '', 0.6)
        return
    no_integrity = 0
    install = 0
    hosts: dict[str, int] = {}
    for p, v in iter_items(get_key(o, 'packages')):
        if not p or not isinstance(v, dict) or v.get('link'):
            continue
        name = p.split('node_modules/')[-1]
        if v.get('version') and name:
            packages.append(
                {'eco': 'npm', 'osv': 'npm', 'name': name, 'version': v['version'], 'file': rel}
            )
        if v.get('hasInstallScript'):
            install += 1
        if not v.get('resolved'):
            continue
        resolved = as_text(v['resolved'])
        u = parse_url(resolved)
        if u is None:
            continue
        if u[0] == 'http':
            add('SUP13', 'high', rel, line_of(text, resolved),
                'Lockfile entry resolves over plain HTTP', f'{name} -> {resolved}', 0.9)
        elif not REGISTRY_OK.match(u[1]):
            hosts[u[1]] = hosts.get(u[1], 0) + 1
        if not v.get('integrity'):
            no_integrity += 1
    for h, n in hosts.items():
        plural = 's' if n > 1 else ''
        add('SUP13', 'medium', rel, 1, 'Lockfile resolves packages from a non-standard host',
            f'{h} ({n} package{plural})', 0.8)
    if no_integrity:
        add(
            'SUP13', 'low', rel, 1, 'Lockfile entries without an integrity hash',
            f'{no_integrity} entries', 0.7,
        )
    if install:
        add(
            'SUP11', 'low', rel, 1, 'Lockfile packages that run install scripts',
            f'{install} packages', 0.6,
        )


_RE_YARN_RESOLVED = re.compile(r'resolved\s+"?(https?://[^"#\s]+)')
_RE_YARN_INTEGRITY = re.compile(r'integrity\s')


def yarn_lock(rel: str, text: str, add: AddFn) -> None:
    """Check yarn.lock."""
    hosts: dict[str, int] = {}
    n = 0
    for m in _RE_YARN_RESOLVED.finditer(text):
        u = parse_url(m.group(1))
        if u is None:
            continue
        if u[0] == 'http':
            add(
                'SUP13', 'high', rel, line_of(text, m.group(1)),
                'Lockfile entry resolves over plain HTTP', m.group(1), 0.9,
            )
        elif not REGISTRY_OK.match(u[1]):
            hosts[u[1]] = hosts.get(u[1], 0) + 1
        n += 1
    for h, c in hosts.items():
        add(
            'SUP13', 'medium', rel, 1, 'Lockfile resolves packages from a non-standard host',
            f'{h} ({c})', 0.8,
        )
    if n and not _RE_YARN_INTEGRITY.search(text):
        add('SUP13', 'low', rel, 1, 'Lockfile has no integrity hashes', '', 0.6)


_RE_TRAILING_COMMENT = re.compile(r'\s+#.*\Z')
_RE_REQ_INDEX_OPT = re.compile(r'(-i|--index-url|--extra-index-url|--trusted-host|-f|--find-links)\b', _A)
_RE_REQ_INCLUDE = re.compile(r'-r\b|-c\b', _A)
_RE_REQ_VCS = re.compile(r'(-e\s+)?(git\+|hg\+|svn\+|bzr\+)', _I)
_RE_REQ_AT_GIT = re.compile(r'@\s*git\+')
_RE_REQ_URL = re.compile(r'(-e\s+)?https?://', _I)
_RE_REQ_AT_URL = re.compile(r'@\s*https?://')
# name, optional extras, optional comparison operator, version.
_RE_REQ_PIN = re.compile(r'([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(==|===|~=|>=|<=|>|<|!=)?\s*([^;\s,]*)')


def requirements(rel: str, text: str, add: AddFn, check_name: CheckNameFn,
                 packages: list[dict[str, Any]]) -> None:
    """Check a pip requirements or constraints file."""
    for i, raw in enumerate(RE_LINE_SPLIT.split(text)):
        ln = _RE_TRAILING_COMMENT.sub('', raw, count=1).strip()
        if not ln or ln.startswith('#'):
            continue
        if _RE_REQ_INDEX_OPT.match(ln):
            add(
                'SUP10', 'high', rel, i + 1, 'Requirements file changes where packages come from',
                ln, 0.85,
            )
            continue
        if _RE_REQ_INCLUDE.match(ln):
            continue
        if _RE_REQ_VCS.match(ln) or _RE_REQ_AT_GIT.search(ln):
            add(
                'SUP12', 'medium', rel, i + 1, 'Dependency comes from a version-control URL', ln,
                0.8,
            )
            continue
        if _RE_REQ_URL.match(ln) or _RE_REQ_AT_URL.search(ln):
            add(
                'SUP12', 'high' if 'http://' in ln else 'medium', rel, i + 1,
                'Dependency comes from a URL', ln, 0.8,
            )
            continue
        m = _RE_REQ_PIN.match(ln)
        if not m:
            continue
        check_name('pypi', m.group(1), rel, text)
        if m.group(3) in ('==', '==='):
            packages.append(
                {
                    'eco': 'pypi', 'osv': 'PyPI', 'name': m.group(1), 'version': m.group(4),
                    'file': rel,
                }
            )
        else:
            add(
                'SUP01', 'low', rel, i + 1, 'Dependency is not pinned to an exact version', ln,
                0.55,
            )


_RE_PY_DEPS = re.compile(r'(^|\n)\s*dependencies\s*=\s*\[([\s\S]*?)\]')
_RE_PY_DEP_NAME = re.compile(r'["\']\s*([A-Za-z0-9][A-Za-z0-9._-]*)')
_RE_PY_INDEX = re.compile(
    r'\[\[tool\.poetry\.source\]\]|\[\[tool\.uv\.index\]\]|index-url|extra-index-url'
    r'|\[tool\.uv\][^\[]*index', _I)
_RE_PY_INDEX_TOKEN = re.compile(r'\[\[tool\.(poetry\.source|uv\.index)\]\]|index-url|extra-index-url', _I)
_RE_PY_BACKEND = re.compile(r'build-backend\s*=\s*["\']([^"\']+)')
_RE_PY_BACKEND_OK = re.compile(
    r'(setuptools|hatchling|poetry|flit_core|pdm|maturin|scikit_build_core|mesonpy|uv_build|sipbuild)')
_RE_PY_BACKEND_PATH = re.compile(r'backend-path\s*=')


def pyproject(rel: str, text: str, add: AddFn, check_name: CheckNameFn) -> None:
    """Check pyproject.toml."""
    dep = _RE_PY_DEPS.search(text)
    if dep:
        for m in _RE_PY_DEP_NAME.finditer(dep.group(2)):
            check_name('pypi', m.group(1), rel, text)
    if _RE_PY_INDEX.search(text):
        token = _RE_PY_INDEX_TOKEN.search(text)
        needle = token.group(0) if token else '[tool.uv]'
        add(
            'SUP10', 'high', rel, line_of(text, needle),
            'Project config adds or replaces a package index', '', 0.8,
        )
    be = _RE_PY_BACKEND.search(text)
    if be and not _RE_PY_BACKEND_OK.match(be.group(1)):
        add(
            'SUP11', 'high', rel, line_of(text, be.group(1)),
            'Custom build backend runs code when the package is built', be.group(1), 0.75,
        )
    if _RE_PY_BACKEND_PATH.search(text):
        add(
            'SUP11', 'high', rel, line_of(text, 'backend-path'),
            'In-tree build backend runs project code at build time', '', 0.8,
        )


_RE_PIPFILE_SOURCE = re.compile(r'\[\[source\]\][\s\S]*?url\s*=\s*"([^"]+)"')
_RE_PYPI_HOST = re.compile(r'pypi\.org')
_RE_PIPFILE_STAR = re.compile(r'^([A-Za-z0-9._-]+)\s*=\s*"\*"', re.MULTILINE)


def pipfile(rel: str, text: str, add: AddFn) -> None:
    """Check a Pipfile."""
    for m in _RE_PIPFILE_SOURCE.finditer(text):
        if not _RE_PYPI_HOST.search(m.group(1)):
            add(
                'SUP10', 'high', rel, line_of(text, m.group(1)),
                'Pipfile uses a non-PyPI package source', m.group(1), 0.8,
            )
    for m in _RE_PIPFILE_STAR.finditer(text):
        add('SUP01', 'low', rel, line_of(text, m.group(0)), 'Unpinned dependency', m.group(1), 0.55)


_RE_SETUP_RISKY = re.compile(
    r'\bcmdclass\b|\bsubprocess\b|\bos\.system\b|\bexec\s*\(|\burllib\b|\brequests\b|\bsocket\b|\bbase64\b', _A)


def setup_py(rel: str, text: str, add: AddFn) -> None:
    """Check setup.py for install-time code."""
    m = _RE_SETUP_RISKY.search(text)
    if m:
        add('SUP11', 'high', rel, line_of(text, m.group(0)),
            'setup.py runs code at install time that goes beyond describing the package',
            m.group(0), 0.7)


_RE_CARGO_PKG = re.compile(
    r'\[\[package\]\]\s*name = "([^"]+)"\s*version = "([^"]+)"(?:\s*source = "([^"]+)")?')


def cargo_lock(rel: str, text: str, packages: list[dict[str, Any]]) -> None:
    """Collect registry packages from Cargo.lock."""
    for m in _RE_CARGO_PKG.finditer(text):
        if m.group(3) and 'registry+' in m.group(3):
            packages.append(
                {
                    'eco': 'cargo', 'osv': 'crates.io', 'name': m.group(1), 'version': m.group(2),
                    'file': rel,
                }
            )


_RE_GEM_HTTP = re.compile(r'\s*source\s+[\'"]http://')
_RE_GEM_OTHER = re.compile(r'\s*source\s+[\'"]https?://(?!rubygems\.org)')
_RE_GEM_GIT = re.compile(r'\bgit(hub)?\s*:', _A)


def gemfile(rel: str, text: str, add: AddFn) -> None:
    """Check a Gemfile."""
    for i, ln in enumerate(RE_LINE_SPLIT.split(text)):
        if _RE_GEM_HTTP.match(ln):
            add('SUP10', 'high', rel, i + 1, 'Gem source over plain HTTP', ln.strip(), 0.9)
        elif _RE_GEM_OTHER.match(ln):
            add('SUP10', 'medium', rel, i + 1, 'Non-default gem source', ln.strip(), 0.7)
        if _RE_GEM_GIT.search(ln):
            add('SUP12', 'medium', rel, i + 1, 'Gem comes from a Git repository', ln.strip(), 0.7)


_RE_GO_REPLACE = re.compile(r'\s*replace\b.*=>', _A)


def go_mod(rel: str, text: str, add: AddFn) -> None:
    """Check go.mod for replace directives."""
    for i, ln in enumerate(RE_LINE_SPLIT.split(text)):
        if _RE_GO_REPLACE.match(ln):
            add(
                'SUP10', 'medium', rel, i + 1, 'Go module replaced by another source', ln.strip(),
                0.7,
            )


_RE_SUBMODULE_URL = re.compile(r'url\s*=\s*(\S+)')
_RE_BAD_TRANSPORT = re.compile(r'(http:|git:|ssh://|ext::)')


def gitmodules(rel: str, text: str, add: AddFn) -> None:
    """Check .gitmodules."""
    for m in _RE_SUBMODULE_URL.finditer(text):
        u = m.group(1)
        if _RE_BAD_TRANSPORT.match(u):
            add('SUP12', 'critical' if u.startswith('ext::') else 'high', rel, line_of(text, u),
                'Git submodule over an unencrypted or command-running transport', u, 0.85)
        else:
            add(
                'SUP12', 'medium', rel, line_of(text, u),
                'Skill pulls in a Git submodule that is not part of this review', u, 0.7,
            )


_RE_DOCKER_FROM = re.compile(r'\s*FROM\s+(?:--platform=\S+\s+)?(\S+)', _I)
_RE_DOCKER_ADD = re.compile(r'\s*ADD\s+https?://', _I)
_RE_REGISTRY_PREFIX = re.compile(r'^[^/]*/')
_RE_VARIABLE_START = re.compile(r'\$|\{')


def _is_unpinned_image(ref: str) -> bool:
    """Return True when an image reference has no tag (other than latest) and no digest."""
    stripped = _RE_REGISTRY_PREFIX.sub('', ref, count=1)
    return '@sha256:' not in ref and (':' not in stripped or ref.endswith(':latest'))


def dockerfile(rel: str, text: str, add: AddFn) -> None:
    """Check a Dockerfile."""
    for i, ln in enumerate(RE_LINE_SPLIT.split(text)):
        f = _RE_DOCKER_FROM.match(ln)
        if f:
            img = f.group(1)
            if img.lower() != 'scratch' and _is_unpinned_image(
                img
            ) and not _RE_VARIABLE_START.match(img):
                add(
                    'SUP14', 'low', rel, i + 1, 'Base image is not pinned to a version or digest',
                    img, 0.7,
                )
        if _RE_DOCKER_ADD.match(ln):
            add(
                'SUP12', 'medium', rel, i + 1, 'ADD downloads a remote file at build time',
                ln.strip(), 0.8,
            )


_RE_CI_USES = re.compile(r'\buses:\s*([\w./-]+)@(main|master|latest|dev|develop)\b', _A)
_RE_CI_IMAGE = re.compile(r'\bimage:\s*["\']?([^\s"\'#]+)', _A)


def ci_yaml(rel: str, text: str, add: AddFn) -> None:
    """Check docker-compose and GitHub workflow YAML."""
    for i, ln in enumerate(RE_LINE_SPLIT.split(text)):
        u = _RE_CI_USES.search(ln)
        if u:
            add(
                'SUP14', 'medium', rel, i + 1, 'CI action pinned to a moving branch',
                f'{u.group(1)}@{u.group(2)}', 0.8,
            )
        img = _RE_CI_IMAGE.search(ln)
        if img and _is_unpinned_image(img.group(1)) and '$' not in img.group(1):
            add(
                'SUP14', 'low', rel, i + 1, 'Image is not pinned to a version or digest',
                img.group(1), 0.6,
            )


# Lines that redirect where a package manager gets packages (anchored alternatives).
_RE_CFG_REDIRECT = re.compile(
    r'^(@[\w-]+:)?registry\s*=|^npmRegistryServer\b|^npmScopes\b|^index-url\b|^extra-index-url\b'
    r'|^trusted-host\b|<mirror>|<url>https?:|^replace-with\b|^\[source\.|^\[registries'
    r'|^default-index|^channels?\b|<packageSources|<add key=.*value="https?:|^registry\s*='
    r'|^\s*url\s*=\s*"?https?:', _A | _I)
_RE_CFG_CREDENTIAL = re.compile(r'_authToken|_auth\s*=|_password|password\s*=|always-auth\s*=\s*true', _A | _I)
_RE_CFG_TLS = re.compile(r'strict-ssl\s*=\s*false|enableStrictSsl:\s*false|ssl_verify\s*=\s*false|trusted-host', _A | _I)
_RE_CFG_SCRIPTS = re.compile(r'script-shell|unsafeHttpWhitelist|ignore-scripts\s*=\s*false', _A | _I)
_RE_URL_USERINFO = re.compile(r'(://)[^@/\s]+@')
_RE_ASSIGN_VALUE = re.compile(r'=.*')


def config_file(rel: str, text: str, add: AddFn) -> None:
    """Check shipped package-manager configuration files."""
    for i, ln in enumerate(RE_LINE_SPLIT.split(text)):
        s = ln.strip()
        if not s or s.startswith(('#', ';', '//')):
            continue
        if _RE_CFG_REDIRECT.search(s):
            add('SUP10', 'high', rel, i + 1,
                'Shipped package-manager config redirects where packages come from',
                _RE_URL_USERINFO.sub(r'\1***@', s[:160], count=1), 0.85)
        if _RE_CFG_CREDENTIAL.search(s):
            add('CRD01', 'high', rel, i + 1, 'Package-manager config contains a credential',
                _RE_ASSIGN_VALUE.sub('=***', s, count=1), 0.85)
        if _RE_CFG_TLS.search(s):
            add(
                'TLM03', 'medium', rel, i + 1, 'Package-manager config turns off TLS verification',
                s, 0.8,
            )
        if _RE_CFG_SCRIPTS.search(s):
            add(
                'SUP11', 'medium', rel, i + 1,
                'Package-manager config changes how install scripts run', s, 0.7,
            )


# ---------- live lookups (opt-in) ----------
_RE_PROXY_AUTH = re.compile(r'(negotiate|ntlm)', _I)
_CURL_TIMEOUT_SECONDS = 120


def _curl_args(url: str, body_file: Path | None) -> list[str]:
    """Build the curl argument list from the environment.

    curl is resolved with ``shutil.which`` so the first one on PATH is used, as in the user's own
    shell. On Windows, starting a bare "curl" searches System32 first, and that build may lack the
    NTLM/Negotiate proxy support the shell's curl has.
    """
    env = os.environ
    args = [shutil.which('curl') or 'curl', '-sS', '--max-time', '25', '-w', '\n__HTTP__%{http_code}']
    if env.get('SKILL_AUDITOR_CA_BUNDLE'):
        args += ['--cacert', env['SKILL_AUDITOR_CA_BUNDLE']]
    if sys.platform == 'win32' and env.get('SKILL_AUDITOR_SSL_REVOKE_BEST_EFFORT') == '1':
        args.append('--ssl-revoke-best-effort')
    if env.get('SKILL_AUDITOR_PROXY'):
        args += ['--proxy', env['SKILL_AUDITOR_PROXY']]
    proxy_auth = env.get('SKILL_AUDITOR_PROXY_AUTH') or ''
    if _RE_PROXY_AUTH.fullmatch(proxy_auth):
        args += ['--proxy-' + proxy_auth.lower(), '-U', ':']
    if body_file is not None:
        args += [
            '-X', 'POST', '-H', 'Content-Type: application/json', '--data-binary',
            '@' + str(body_file),
        ]
    args.append(url)
    return args


def _curl_hint(rc: int | None, status: int) -> str:
    """Explain a failed curl call."""
    if rc in (5, 6):
        return 'host name not resolved; behind a firewall set HTTPS_PROXY or SKILL_AUDITOR_PROXY'
    if rc in (7, 28):
        return 'could not connect or timed out; a proxy may be required'
    if status == 407:
        return 'proxy needs authentication (set SKILL_AUDITOR_PROXY_AUTH=negotiate)'
    if rc in (35, 60):
        return 'TLS certificate not trusted; set SKILL_AUDITOR_CA_BUNDLE to the corporate root CA'
    return f'curl exit {rc}, HTTP {status}'


def _run_curl(url: str, body_file: Path | None) -> subprocess.CompletedProcess[bytes] | None:
    """Run curl, returning None when it cannot be started or times out."""
    try:
        return subprocess.run(
            _curl_args(url, body_file), capture_output=True, check=False,
            timeout=_CURL_TIMEOUT_SECONDS, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess([], 28, b'', b'')
    except OSError:
        return None


def _http_status(text: str) -> int:
    """The HTTP status code printed by curl, or 0 when it is not a number."""
    try:
        return int(text.strip())
    except ValueError:
        return 0


def curl(url: str, body: Any = None) -> dict[str, Any]:
    """Fetch JSON with curl (GET, or POST when a body is given) and return {'ok', 'data'|'why'}."""
    if body is not None:
        with tempfile.TemporaryDirectory(prefix='skill-auditor-') as tmpdir:
            tmp = Path(tmpdir) / f'skill-auditor-{os.getpid()}-{int(time.time() * 1000)}.json'
            tmp.write_bytes(dump_json(body, False).encode('utf-8'))
            r = _run_curl(url, tmp)
    else:
        r = _run_curl(url, None)
    if r is None:
        return {'ok': False, 'why': 'curl was not found on PATH'}
    out = (r.stdout or b'').decode('utf-8', errors='replace')
    k = out.rfind('\n__HTTP__')
    status = _http_status(out[k + 9:]) if k >= 0 else 0
    text = out[:k] if k >= 0 else out
    if r.returncode != 0 or status < 200 or status >= 300:
        return {'ok': False, 'why': _curl_hint(r.returncode, status)}
    try:
        return {'ok': True, 'data': parse_json(text)}
    except ValueError:
        return {'ok': False, 'why': 'response was not JSON (a proxy may have answered)'}


def sev_from_osv(v: Any, kev: bool) -> str:
    """Map an OSV record (and KEV membership) to a finding severity."""
    if kev:
        return 'high'
    sv = get_key(get_key(v, 'database_specific'), 'severity')
    s = as_text(sv).upper() if sv else ''
    if s in ('CRITICAL', 'HIGH'):
        return 'high'
    if s == 'LOW':
        return 'low'
    return 'medium'


def _first_fixed(v: Any) -> Any:
    """Return the first fixed version in the first affected entry, or None."""
    aff = get_key(v, 'affected')
    first = aff[0] if isinstance(aff, list) and aff else None
    ranges = get_key(first, 'ranges')
    for rg in ranges if isinstance(ranges, list) else []:
        events = get_key(rg, 'events')
        for e in events if isinstance(events, list) else []:
            if get_key(e, 'fixed'):
                return e['fixed']
    return None


def _collect_vulnerable(uniq: list[dict[str, Any]],
                        status: dict[str, Any]) -> dict[str, list[dict[str, Any]]] | None:
    """Query OSV in batches; return {vuln id: packages} or None after recording a failure."""
    ids: dict[str, list[dict[str, Any]]] = {}
    for i in range(0, len(uniq), 500):
        chunk = uniq[i:i + 500]
        queries = [
            {'package': {'name': p['name'], 'ecosystem': p['osv']}, 'version': p['version']}
                for p in chunk
        ]
        r = curl('https://api.osv.dev/v1/querybatch', {'queries': queries})
        if not r['ok']:
            status['osv'] = 'failed: ' + r['why']
            return None
        results = get_key(r['data'], 'results')
        for j, res in enumerate(results if isinstance(results, list) else []):
            vulns = get_key(res, 'vulns')
            for v in vulns if isinstance(vulns, list) else []:
                ids.setdefault(v['id'], []).append(chunk[j])
    return ids


def osv_lookup(packages: list[dict[str, Any]]) -> dict[str, Any]:
    """Look up pinned packages in OSV.dev and CISA KEV and return {'findings', 'status'}."""
    status: dict[str, Any] = {
        'osv': 'not-requested', 'kev': 'not-requested', 'queried': 0, 'vulnerable': 0,
    }
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for p in packages:
        key = p['osv'] + p['name'] + p['version']
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    uniq = uniq[:2000]
    status['queried'] = len(uniq)
    if not uniq:
        status['osv'] = 'no pinned packages found'
        return {'findings': findings, 'status': status}
    ids = _collect_vulnerable(uniq, status)
    if ids is None:
        return {'findings': findings, 'status': status}
    status['osv'] = 'ok'
    status['vulnerable'] = len({p['name'] + p['version'] for pkgs in ids.values() for p in pkgs})
    kev: set[Any] | None = None
    kr = curl('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json')
    if kr['ok']:
        vulns = get_key(kr['data'], 'vulnerabilities')
        kev = {get_key(v, 'cveID') for v in (vulns if isinstance(vulns, list) else [])}
        status['kev'] = 'ok'
    else:
        status['kev'] = 'failed: ' + kr['why']
    for n, (vid, pkgs) in enumerate(ids.items()):
        if n >= 80:
            break
        d = curl('https://api.osv.dev/v1/vulns/' + urllib.parse.quote(vid, safe="-_.!~*'()"))
        v = d['data'] if d['ok'] else {'id': vid, 'summary': ''}
        aliases = get_key(v, 'aliases')
        in_kev = kev is not None and any(
            a in kev for a in [vid] + (aliases if isinstance(aliases, list) else [])
        )
        fixed = _first_fixed(v)
        summary = get_key(v, 'summary')
        extra = ' - ' + as_text(summary)[:80] if summary else ''
        fix = '; fixed in ' + as_text(fixed) if fixed else ''
        label = ' (actively exploited, CISA KEV)' if in_kev else ''
        for p in pkgs[:3]:
            findings.append({
                'id': 'SUP04', 'severity': sev_from_osv(v, in_kev), 'file': p['file'], 'line': 1,
                'message': f'Known vulnerability{label}',
                'evidence': f"{p['name']}@{p['version']}: {vid}{extra}{fix}",
                'confidence': 0.9, 'surface': 'config'})
    return {'findings': findings, 'status': status}
