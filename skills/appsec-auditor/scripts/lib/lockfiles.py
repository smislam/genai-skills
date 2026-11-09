"""Deterministic dependency extraction from lockfiles and manifests, for the OSV.dev lookup.

Python 3.12 standard library only. Reads files; never runs project code.

Public API:
    parse_lockfiles(root, file_list, opts=None) -> {'packages', 'unresolved', 'sources'}
        file_list: repo-relative paths (forward slashes) of every tracked file
        opts['fetchText']: callable(url) -> str | None, a synchronous GET used only for
            Maven parent/BOM/dependency POMs
        opts['mavenBase']: Maven repository base URL (default Maven Central)
    parse_pom(text) -> PomModel
    interpolate(value, props) -> str | None
    normalize_pypi(name) -> str

A package is {'ecosystem', 'name', 'version', 'file', 'direct'} plus optional 'dev', 'scope',
'via'; an unresolved entry is {'ecosystem', 'name', 'file', 'reason'}; a source is
{'file', 'ecosystem', 'parser', 'count'}.

Every parser tolerates malformed or hostile files: a file that cannot be parsed is recorded as
an unresolved '(file)' entry and contributes no packages.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

__all__ = ['interpolate', 'normalize_pypi', 'parse_lockfiles', 'parse_pom']

Pkg: TypeAlias = dict[str, Any]
FetchText: TypeAlias = Callable[[str], str | None]

MAVEN_CENTRAL: str = 'https://repo1.maven.org/maven2'
MAX_POM_DEPTH: int = 6
MAX_TRANSITIVE_DEPTH: int = 12
MAX_TRANSITIVE_FETCHES: int = 1500
FOLLOWED_SCOPES: frozenset[str] = frozenset({'compile', 'runtime'})
FOLLOWED_TYPES: frozenset[str] = frozenset({'jar', 'bundle', 'pom'})
GRADLE_RUNTIME_CONFIGS: frozenset[str] = frozenset({'implementation', 'api', 'runtimeOnly', 'compile'})
NPM_DEP_FIELDS: tuple[str, ...] = ('dependencies', 'devDependencies', 'optionalDependencies')
NPM_LOCK_NAMES: frozenset[str] = frozenset(
    {'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml'})
POM_STRIPPED_BLOCKS: tuple[str, ...] = ('build', 'profiles', 'reporting')
POM_NON_CORE_BLOCKS: tuple[str, ...] = (
    'dependencies', 'properties', 'modules', 'distributionManagement', 'repositories',
    'pluginRepositories', 'developers', 'contributors', 'scm', 'organization', 'licenses',
    'issueManagement', 'ciManagement', 'mailingLists')
POM_TAGS: tuple[str, ...] = (
    'artifactId', 'build', 'classifier', 'ciManagement', 'contributors', 'dependencies',
    'dependencyManagement', 'developers', 'distributionManagement', 'exclusions', 'groupId',
    'issueManagement', 'licenses', 'mailingLists', 'modules', 'optional', 'organization',
    'parent', 'pluginRepositories', 'profiles', 'properties', 'relativePath', 'reporting',
    'repositories', 'scm', 'scope', 'type', 'version')
ASCII_WHITESPACE: tuple[str, ...] = (' ', '\t', '\r', '\n', '\f', '\v')

_ASCII: int = re.ASCII
_MULTI: int = re.ASCII | re.MULTILINE
_DOTALL: int = re.ASCII | re.DOTALL

# ---- path and file selection
RE_SKIP_DIRS: re.Pattern[str] = re.compile(r'(^|/)(node_modules|vendor|\.appsec-audit)/')
RE_GRADLE_LOCKS_DIR: re.Pattern[str] = re.compile(r'/dependency-locks/[^/]+\.lockfile$')
RE_REQUIREMENTS_NAME: re.Pattern[str] = re.compile(r'requirements.*\.txt', _ASCII)
RE_DOTNET_PROJECT: re.Pattern[str] = re.compile(r'.*\.(cs|fs|vb)proj$')
RE_GRADLE_BUILD_NAME: re.Pattern[str] = re.compile(r'build\.gradle(\.kts)?')
RE_PYPI_SEPARATORS: re.Pattern[str] = re.compile(r'[-_.]+')
RE_LINE_SPLIT: re.Pattern[str] = re.compile(r'\r?\n')
RE_DIGIT_START: re.Pattern[str] = re.compile(r'\d', _ASCII)
RE_NON_SPACE_START: re.Pattern[str] = re.compile(r'\S', _ASCII)

# ---- npm
RE_BERRY: re.Pattern[str] = re.compile(r'^__metadata:', _MULTI)
RE_YARN_BERRY_VERSION: re.Pattern[str] = re.compile(r'\s{2}version:\s*"?([^"\s]+)"?\s*$', _ASCII)
RE_YARN_CLASSIC_VERSION: re.Pattern[str] = re.compile(r'\s{2}version\s+"([^"]+)"\s*$', _ASCII)
RE_YARN_TRAILING_COLON: re.Pattern[str] = re.compile(r':\s*$', _ASCII)
RE_COMMA_SPLIT: re.Pattern[str] = re.compile(r',\s*', _ASCII)
RE_EDGE_QUOTES: re.Pattern[str] = re.compile(r'^"|"$')
RE_YARN_NON_REGISTRY: re.Pattern[str] = re.compile(r'@(workspace|patch|link|portal|file):')
RE_PNPM_PACKAGES: re.Pattern[str] = re.compile(r'packages:\s*$', _ASCII)
# Two-space-indented "key:" line; the key may be quoted with ' or " (backreference \1).
RE_PNPM_KEY: re.Pattern[str] = re.compile(r'''\ {2}(?!\ )(['"]?)(.+?)\1:\s*$''', _ASCII)

# ---- PyPI
RE_TOML_PKG_HEADER: re.Pattern[str] = re.compile(r'^\[\[package\]\]\s*$', _MULTI)
RE_TOML_TABLE_START: re.Pattern[str] = re.compile(r'^\[(?!\[package\])', _MULTI)
RE_LINE_BRACKET: re.Pattern[str] = re.compile(r'^\[', _MULTI)
RE_PROJECT_DEPS: re.Pattern[str] = re.compile(
    r'^\[project\].*?^dependencies\s*=\s*\[(.*?)\]', re.ASCII | re.MULTILINE | re.DOTALL)
RE_QUOTED_NAME: re.Pattern[str] = re.compile(r'''["']([A-Za-z0-9][A-Za-z0-9._-]*)''')
RE_POETRY_SECTION: re.Pattern[str] = re.compile(
    r'tool\.poetry\.(dependencies|dev-dependencies|group\.[^\]]+\.dependencies)\]')
RE_TOML_KEY: re.Pattern[str] = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=', _MULTI)
RE_UV_LOCAL_SOURCE: re.Pattern[str] = re.compile(
    r'^source\s*=\s*\{\s*(editable|virtual)\s*=\s*"\."', _MULTI)
RE_PIPFILE_SECTION: re.Pattern[str] = re.compile(r'(packages|dev-packages)\]')
RE_PIPFILE_KEY: re.Pattern[str] = re.compile(r'^"?([A-Za-z0-9][A-Za-z0-9._-]*)"?\s*=', _MULTI)
RE_CONTINUATION: re.Pattern[str] = re.compile(r'\\\r?\n')
RE_COMMENT_TAIL: re.Pattern[str] = re.compile(r'(^|\s)#.*$', _ASCII)
RE_REQ_LINE: re.Pattern[str] = re.compile(
    r'([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(.*)$', _ASCII)
RE_REQ_HASH: re.Pattern[str] = re.compile(r'\s+--hash=\S+', _ASCII)
RE_REQ_PIN: re.Pattern[str] = re.compile(r'===?\s*([^\s,]+)$', _ASCII)
TOML_STRING_KEYS: dict[str, re.Pattern[str]] = {
    key: re.compile(rf'^{key}\s*=\s*"([^"]*)"', _MULTI) for key in ('name', 'version', 'source')}

# ---- crates.io and Go
CARGO_TABLE: str = r'(?:target\..+\.)?(?:workspace\.)?(dependencies|dev-dependencies|build-dependencies)'
RE_CARGO_HEADER: re.Pattern[str] = re.compile(r'([^\]]+)\]')
RE_CARGO_INLINE: re.Pattern[str] = re.compile(CARGO_TABLE + r'\.(.+)\Z', _ASCII)
RE_CARGO_TABLE: re.Pattern[str] = re.compile(CARGO_TABLE + r'\Z', _ASCII)
RE_CARGO_KEY: re.Pattern[str] = re.compile(r'^([A-Za-z0-9_-]+)\s*=', _MULTI)
RE_CARGO_REGISTRY: re.Pattern[str] = re.compile(r'(registry|sparse)\+')
RE_GO_INDIRECT: re.Pattern[str] = re.compile(r'//\s*indirect\b', _ASCII)
RE_GO_REQUIRE_OPEN: re.Pattern[str] = re.compile(r'require\s*\($', _ASCII)
RE_GO_REQUIRE_ONE: re.Pattern[str] = re.compile(r'require\s+(.+)$', _ASCII)
RE_GO_SPEC: re.Pattern[str] = re.compile(r'(\S+)\s+(v\S+)$', _ASCII)

# ---- NuGet
RE_XML_COMMENT: re.Pattern[str] = re.compile(r'<!--.*?-->', _DOTALL)
RE_PACKAGE_VERSION_TAG: re.Pattern[str] = re.compile(r'<PackageVersion\b[^>]*>', re.ASCII | re.IGNORECASE)
RE_NUGET_EXACT: re.Pattern[str] = re.compile(r'\d+(\.\d+){0,3}(-[0-9A-Za-z.-]+)?$', _ASCII)
RE_PACKAGE_REFERENCE: re.Pattern[str] = re.compile(
    r'<PackageReference\b([^>]*?)(/>|>(.*?)</PackageReference>)',
    re.ASCII | re.IGNORECASE | re.DOTALL)
RE_VERSION_CHILD: re.Pattern[str] = re.compile(
    r'<Version>\s*([^<]+?)\s*</Version>', re.ASCII | re.IGNORECASE)
XML_ATTR_NAMES: tuple[str, ...] = ('Include', 'Update', 'Version', 'VersionOverride')
XML_ATTRS: dict[str, re.Pattern[str]] = {
    name: re.compile(rf'\b{name}\s*=\s*"([^"]*)"', re.ASCII | re.IGNORECASE)
    for name in XML_ATTR_NAMES}

# ---- RubyGems and Packagist
RE_GEM_DEPENDENCY: re.Pattern[str] = re.compile(r'\ {2}([^\s!(]+)', _ASCII)
RE_GEM_SPECS: re.Pattern[str] = re.compile(r'\ {2}specs:\s*$', _ASCII)
RE_GEM_SPEC: re.Pattern[str] = re.compile(r'\ {4}([^\s(]+) \(([^)]+)\)\s*$', _ASCII)
RE_GEM_PLATFORM: re.Pattern[str] = re.compile(
    r'-(x86|x64|arm|aarch|universal|java|mingw|mswin|darwin|linux)[\w-]*$', _ASCII)

# ---- Maven
RE_POM_DEPENDENCY: re.Pattern[str] = re.compile(r'<dependency>(.*?)</dependency>', _DOTALL)
RE_POM_EXCLUSION: re.Pattern[str] = re.compile(r'<exclusion>(.*?)</exclusion>', _DOTALL)
RE_POM_PROPERTY: re.Pattern[str] = re.compile(r'<([A-Za-z0-9_.-]+)>([^<]*)</\1>')
RE_PROPERTY_REF: re.Pattern[str] = re.compile(r'\$\{([^}]+)\}')
RE_DYNAMIC_RANGE: re.Pattern[str] = re.compile(r'[\[(]')
POM_INNER: dict[str, re.Pattern[str]] = {
    tag: re.compile(rf'<{tag}(?:\s[^>]*)?>(.*?)</{tag}>', _DOTALL) for tag in POM_TAGS}

# ---- Gradle
RE_GRADLE_LOCK_LINE: re.Pattern[str] = re.compile(r'([^#:\s]+):([^:\s]+):([^=\s]+)=', _ASCII)
RE_TOML_COMMENT: re.Pattern[str] = re.compile(r'(^|\s)#.*$', _MULTI)
RE_CATALOG_ENTRY: re.Pattern[str] = re.compile(r'^([\w.-]+)\s*=\s*(.+)$', _MULTI)
RE_CATALOG_PLAIN: re.Pattern[str] = re.compile(r'"([^"]+)"')
RE_CATALOG_RICH: re.Pattern[str] = re.compile(r'(?:strictly|require|prefer)\s*=\s*"([^"]+)"', _ASCII)
RE_CATALOG_INLINE: re.Pattern[str] = re.compile(r'"([^":]+):([^":]+)(?::([^"]+))?"')
RE_CATALOG_MODULE: re.Pattern[str] = re.compile(r'module\s*=\s*"([^"]+)"', _ASCII)
RE_CATALOG_GROUP: re.Pattern[str] = re.compile(r'group\s*=\s*"([^"]+)"', _ASCII)
RE_CATALOG_NAME: re.Pattern[str] = re.compile(r'\bname\s*=\s*"([^"]+)"', _ASCII)
RE_CATALOG_REF: re.Pattern[str] = re.compile(
    r'version\.ref\s*=\s*"([^"]+)"|version\s*=\s*\{\s*ref\s*=\s*"([^"]+)"', _ASCII)
RE_CATALOG_LITERAL: re.Pattern[str] = re.compile(r'version\s*=\s*"([^"]+)"', _ASCII)
RE_UNSUPPORTED_VERSION: re.Pattern[str] = re.compile(r'[\[(+]')
TOML_SECTIONS: dict[str, re.Pattern[str]] = {
    name: re.compile(rf'^\[{name}\]\s*$(.*?)(?=^\[|\Z)', re.ASCII | re.MULTILINE | re.DOTALL)
    for name in ('versions', 'libraries')}
RE_GRADLE_DECL: re.Pattern[str] = re.compile(
    r'''\b(implementation|api|compileOnly|runtimeOnly|testImplementation|testCompileOnly'''
    r'''|testRuntimeOnly|annotationProcessor|kapt|ksp|compile|testCompile|developmentOnly'''
    r"""|classpath)\s*\(?\s*["']([^"':\s]+):([^"':\s]+)(?::([^"'\s@]+))?(?:@\w+)?["']""",
    _ASCII)
RE_BLOCK_COMMENT: re.Pattern[str] = re.compile(r'/\*.*?\*/', _DOTALL)
RE_LINE_COMMENT: re.Pattern[str] = re.compile(r'(^|[^:])//.*$', _MULTI)
RE_GRADLE_PROPERTY: re.Pattern[str] = re.compile(
    r'^\s*([\w.-]+)\s*[=:]\s*(\S[^\r\n]*?)\s*$', _MULTI)
RE_EXT_BLOCK: re.Pattern[str] = re.compile(r'\bext\s*\{(.*?)\}', _DOTALL)
RE_EXT_ENTRY: re.Pattern[str] = re.compile(
    r"""(?:^|\s)(?:set\(\s*)?["']?([A-Za-z_]\w*)["']?\s*[=,]\s*["']([^"'$]+)["']""", _ASCII)
RE_GRADLE_VAR: re.Pattern[str] = re.compile(r'\$\{([\w.]+)\}|\$([A-Za-z_]\w*)', _ASCII)
# Assignments that define a version variable; group 1 is the name, group 2 the value.
GRADLE_VAR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(re.compile(p, _ASCII) for p in (
    r"""\bext\.([A-Za-z_]\w*)\s*=\s*["']([^"'$]+)["']""",
    r"""\bext\[\s*["'](\w+)["']\s*\]\s*=\s*["']([^"'$]+)["']""",
    r'''\bextra\[\s*"(\w+)"\s*\]\s*=\s*"([^"$]+)"''',
    r'''\bval\s+([A-Za-z_]\w*)\s+by\s+extra\(\s*"([^"$]+)"\s*\)''',
    r'''\bval\s+([A-Za-z_]\w*)\s*(?::\s*String)?\s*=\s*"([^"$]+)"''',
    r"""\bdef\s+([A-Za-z_]\w*)\s*=\s*["']([^"'$]+)["']"""))
RE_BOOT_PLUGIN: re.Pattern[str] = re.compile(
    r"""\bid\s*\(?\s*["']org\.springframework\.boot["']\s*\)?\s*version\s*\(?\s*["']([^"']+)["']""",
    _ASCII)
RE_BOOT_CLASSPATH: re.Pattern[str] = re.compile(
    r"""["']org\.springframework\.boot:spring-boot-gradle-plugin:([^"'\s]+)["']""")
RE_DEPENDENCY_MGMT: re.Pattern[str] = re.compile(r'io\.spring\.dependency-management')
RE_MAVEN_BOM: re.Pattern[str] = re.compile(
    r"""\bmavenBom\s*\(?\s*["']([^"':\s]+):([^"':\s]+):([^"'\s]+)["']""", _ASCII)
RE_PLATFORM: re.Pattern[str] = re.compile(
    r'''\b(?:enforcedPlatform|platform)\s*\(\s*["']([^"':\s]+):([^"':\s]+):([^"'\s]+)["']\s*\)''',
    _ASCII)


# ---------------------------------------------------------------- generic helpers

def read_text(root: str, file: str) -> str | None:
    """Return the file's text (undecodable bytes replaced), or None if it cannot be read."""
    try:
        return Path(root, *file.split('/')).read_bytes().decode('utf-8', errors='replace')
    except (OSError, ValueError):
        return None


def read_required(root: str, file: str) -> str:
    """Return the file's text, raising OSError when it cannot be read."""
    text = read_text(root, file)
    if text is None:
        raise FileNotFoundError(file)
    return text


def json_object(text: str) -> dict[str, Any]:
    """Parse JSON text; a JSON null is corrupt, any other non-object holds nothing."""
    value = json.loads(text)
    if value is None:
        raise TypeError('null document')
    return value if isinstance(value, dict) else {}


def as_object(value: Any) -> dict[str, Any]:
    """Return a JSON object; null is corrupt, any other non-object holds nothing."""
    if value is None:
        raise TypeError('null where an object was expected')
    return value if isinstance(value, dict) else {}


def as_dict(value: Any) -> dict[str, Any]:
    """Return value if it is a JSON object, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def text_or_none(value: Any) -> str | None:
    """Return value if it is a non-empty string, otherwise None."""
    return value if isinstance(value, str) and value else None


def dir_of(file: str) -> str:
    """Directory part of a forward-slash path ('' for top-level files)."""
    return file.rpartition('/')[0]


def base_of(file: str) -> str:
    """File-name part of a forward-slash path."""
    return file.rpartition('/')[2]


def join_path(dir_: str, name: str) -> str:
    """Join a directory and a name with a forward slash."""
    return f'{dir_}/{name}' if dir_ else name


def ancestors(dir_: str) -> list[str]:
    """The directory and each parent up to the repository root ('')."""
    out = [dir_]
    while dir_:
        dir_ = dir_of(dir_)
        out.append(dir_)
    return out


def normalize_pypi(name: str) -> str:
    """PEP 503 name normalization."""
    return RE_PYPI_SEPARATORS.sub('-', name.lower())


def lines_of(text: str) -> list[str]:
    """Split text into lines on LF or CRLF."""
    return RE_LINE_SPLIT.split(text)


def is_indented(line: str) -> bool:
    """True when the line starts with whitespace."""
    return line[:1] in ASCII_WHITESPACE


# ---------------------------------------------------------------- collector

class Collector:
    """Accumulates packages, unresolved entries, and per-file sources."""

    def __init__(self) -> None:
        """Start with empty result lists."""
        self.packages: list[Pkg] = []
        self.unresolved: list[Pkg] = []
        self.sources: list[Pkg] = []

    def add(self, pkg: Pkg) -> None:
        """Record a resolved package."""
        self.packages.append(pkg)

    def unresolve(self, ecosystem: str, name: str, file: str, reason: str) -> None:
        """Record a dependency that could not be resolved to an exact version."""
        self.unresolved.append({'ecosystem': ecosystem, 'name': name, 'file': file, 'reason': reason})

    def source(self, file: str, ecosystem: str, parser: str, count: int) -> None:
        """Record that a file was parsed and how many packages it produced."""
        self.sources.append({'file': file, 'ecosystem': ecosystem, 'parser': parser, 'count': count})


# Anything a parser may raise on a malformed or hostile file.
PARSE_ERRORS: tuple[type[Exception], ...] = (
    json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError, RecursionError, OSError)


def parse_with(c: Collector, file: str, ecosystem: str, parser: str,
               fn: Callable[[], None]) -> None:
    """Run one parser, recording the file as a source, or as unparseable if it fails."""
    before = len(c.packages)
    try:
        fn()
    except PARSE_ERRORS:
        del c.packages[before:]
        c.unresolve(ecosystem, '(file)', file, 'could not parse')
        return
    c.source(file, ecosystem, parser, len(c.packages) - before)


# ---------------------------------------------------------------- npm

def package_json_deps(root: str, dir_: str) -> dict[str, Any] | None:
    """All dependency maps of the directory's package.json merged, or None if it has none."""
    text = read_text(root, join_path(dir_, 'package.json'))
    if not text:
        return None
    manifest = json_object(text)
    deps: dict[str, Any] = {}
    for name in NPM_DEP_FIELDS:
        deps.update(as_dict(manifest.get(name)))
    return deps


def direct_set_for(root: str, dir_: str) -> set[str]:
    """Names declared directly in the directory's package.json (empty if unreadable)."""
    try:
        return set(package_json_deps(root, dir_) or {})
    except PARSE_ERRORS:
        return set()


def add_npm(c: Collector, name: str, version: str, file: str, direct: bool, dev: bool) -> None:
    """Record an npm package, or an unresolved entry for a non-registry version."""
    if not RE_DIGIT_START.match(version):
        c.unresolve('npm', name, file, f'non-registry version ({version})')
        return
    pkg: Pkg = {'ecosystem': 'npm', 'name': name, 'version': version, 'file': file,
                'direct': bool(direct)}
    if dev:
        pkg['dev'] = True
    c.add(pkg)


def npm_lock_v2(c: Collector, file: str, packages: dict[str, Any], direct: set[str]) -> None:
    """lockfileVersion 2 and 3: a flat 'packages' map keyed by node_modules path."""
    root_entry = as_dict(packages.get(''))
    for name in NPM_DEP_FIELDS:
        direct.update(as_dict(root_entry.get(name)))
    marker = 'node_modules/'
    for key, raw in packages.items():
        if key == '' or marker not in key:
            continue
        entry = as_object(raw)
        version = text_or_none(entry.get('version'))
        if entry.get('link') or not version:
            continue
        name = text_or_none(entry.get('name')) or key[key.rindex(marker) + len(marker):]
        top_level = key == f'{marker}{name}'
        add_npm(c, name, version, file, name in direct and top_level, bool(entry.get('dev')))


def npm_lock_v1(c: Collector, file: str, deps: Any, direct: set[str], depth: int = 0) -> None:
    """lockfileVersion 1: a nested 'dependencies' tree."""
    for name, raw in as_dict(deps).items():
        entry = as_object(raw)
        version = text_or_none(entry.get('version'))
        if version:
            add_npm(c, name, version, file, depth == 0 and name in direct, bool(entry.get('dev')))
        npm_lock_v1(c, file, entry.get('dependencies'), direct, depth + 1)


def lockfile_version(lock: dict[str, Any]) -> float:
    """The numeric lockfileVersion, or 0 when absent or not a number."""
    value = lock.get('lockfileVersion')
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def parse_package_lock(c: Collector, root: str, file: str) -> None:
    """package-lock.json and npm-shrinkwrap.json."""
    lock = json_object(read_required(root, file))
    direct = direct_set_for(root, dir_of(file))
    packages = lock.get('packages')
    if isinstance(packages, dict) and lockfile_version(lock) >= 2:
        npm_lock_v2(c, file, packages, direct)
    else:
        npm_lock_v1(c, file, lock.get('dependencies'), direct)


def spec_name(spec: str) -> str:
    """'name@range' -> name; handles scoped packages and Berry's 'name@npm:range'."""
    at = spec.rfind('@')
    return spec[:at] if at > 0 else spec


def yarn_header_names(line: str) -> list[str] | None:
    """Package names on a yarn.lock header line, or None for workspace/patch/link entries."""
    specs = [RE_EDGE_QUOTES.sub('', s.strip())
             for s in RE_COMMA_SPLIT.split(RE_YARN_TRAILING_COLON.sub('', line))]
    if any(RE_YARN_NON_REGISTRY.search(s) for s in specs):
        return None
    return list(dict.fromkeys(spec_name(s) for s in specs))


def parse_yarn_lock(c: Collector, root: str, file: str) -> None:
    """yarn.lock, classic (v1) and Berry."""
    text = read_required(root, file)
    direct = direct_set_for(root, dir_of(file))
    version_re = RE_YARN_BERRY_VERSION if RE_BERRY.search(text) else RE_YARN_CLASSIC_VERSION
    seen: set[str] = set()
    names: list[str] | None = None
    for line in lines_of(text):
        if not line.strip() or line.startswith('#'):
            continue
        if not is_indented(line):
            names = None if line.startswith('__metadata') else yarn_header_names(line)
            continue
        m = version_re.match(line) if names else None
        if not m:
            continue
        for name in names or []:
            if f'{name}@{m[1]}' not in seen:
                seen.add(f'{name}@{m[1]}')
                add_npm(c, name, m[1], file, name in direct, False)
        names = None


def pnpm_split(key: str) -> tuple[str, str] | None:
    """Split a pnpm package key ('/name/1.0.0', 'name@1.0.0(peer)') into (name, version)."""
    key = key.removeprefix('/').partition('(')[0]
    at = key.rfind('@')
    if at <= 0:
        at = key.rfind('/')
        if at <= 0:
            return None
    return key[:at], key[at + 1:].partition('_')[0]


def parse_pnpm_lock(c: Collector, root: str, file: str) -> None:
    """pnpm-lock.yaml: the 'packages:' section keys."""
    direct = direct_set_for(root, dir_of(file))
    in_packages = False
    seen: set[tuple[str, str]] = set()
    for line in lines_of(read_required(root, file)):
        if RE_NON_SPACE_START.match(line):
            in_packages = bool(RE_PNPM_PACKAGES.match(line))
            continue
        m = RE_PNPM_KEY.match(line) if in_packages else None
        split = pnpm_split(m[2]) if m else None
        if split and split not in seen:
            seen.add(split)
            add_npm(c, split[0], split[1], file, split[0] in direct, False)


def check_npm_without_lockfile(c: Collector, root: str, files: Sequence[str],
                               lock_dirs: set[str]) -> None:
    """A package.json with no lockfile in its directory or any ancestor can't be checked exactly."""
    for file in files:
        if base_of(file) != 'package.json':
            continue
        if any(d in lock_dirs for d in ancestors(dir_of(file))):
            continue
        try:
            deps = package_json_deps(root, dir_of(file))
        except PARSE_ERRORS:
            c.unresolve('npm', '(file)', file, 'could not parse')
            continue
        for name in deps or {}:
            c.unresolve('npm', name, file, 'no lockfile')


# ---------------------------------------------------------------- PyPI

def toml_package_blocks(text: str) -> list[str]:
    """The body of each [[package]] table, up to the next table."""
    blocks = RE_TOML_PKG_HEADER.split(text)[1:]
    return [RE_TOML_TABLE_START.split(block, maxsplit=1)[0] for block in blocks]


def toml_string(block: str, key: str) -> str | None:
    """Value of a simple `key = "value"` line in a TOML block (key: name, version or source)."""
    m = TOML_STRING_KEYS[key].search(block)
    return m[1] if m else None


def pyproject_direct(root: str, dir_: str) -> set[str]:
    """Normalized dependency names declared in the directory's pyproject.toml."""
    text = read_text(root, join_path(dir_, 'pyproject.toml'))
    names: set[str] = set()
    if not text:
        return names
    project = RE_PROJECT_DEPS.search(text)
    if project:
        names.update(normalize_pypi(m[1]) for m in RE_QUOTED_NAME.finditer(project[1]))
    for section in RE_LINE_BRACKET.split(text):
        if RE_POETRY_SECTION.match(section):
            names.update(normalize_pypi(m[1]) for m in RE_TOML_KEY.finditer(section)
                         if m[1].lower() != 'python')
    return names


def parse_poetry_or_uv_lock(c: Collector, root: str, file: str) -> None:
    """poetry.lock and uv.lock."""
    text = read_required(root, file)
    direct = pyproject_direct(root, dir_of(file))
    for block in toml_package_blocks(text):
        name = toml_string(block, 'name')
        version = toml_string(block, 'version')
        if not name or not version or RE_UV_LOCAL_SOURCE.search(block):
            continue
        norm = normalize_pypi(name)
        c.add({'ecosystem': 'PyPI', 'name': norm, 'version': version, 'file': file,
               'direct': norm in direct})


def pipfile_direct(root: str, dir_: str) -> set[str]:
    """Normalized names from the [packages] and [dev-packages] tables of the sibling Pipfile."""
    pipfile = read_text(root, join_path(dir_, 'Pipfile')) or ''
    names: set[str] = set()
    for section in RE_LINE_BRACKET.split(pipfile):
        if RE_PIPFILE_SECTION.match(section):
            names.update(normalize_pypi(m[1]) for m in RE_PIPFILE_KEY.finditer(section))
    return names


def parse_pipfile_lock(c: Collector, root: str, file: str) -> None:
    """Pipfile.lock."""
    lock = json_object(read_required(root, file))
    direct = pipfile_direct(root, dir_of(file))
    for group in ('default', 'develop'):
        for name, raw in as_dict(lock.get(group)).items():
            entry = as_object(raw)
            norm = normalize_pypi(name)
            version = entry.get('version')
            if not isinstance(version, str) or not version.startswith('=='):
                reason = ('non-registry source' if entry.get('git') or entry.get('path')
                          else 'no exact version')
                c.unresolve('PyPI', norm, file, reason)
                continue
            pkg: Pkg = {'ecosystem': 'PyPI', 'name': norm, 'version': version[2:], 'file': file,
                        'direct': norm in direct}
            if group == 'develop':
                pkg['dev'] = True
            c.add(pkg)


def requirement_line(c: Collector, file: str, raw: str) -> None:
    """Record one requirements.txt line as a package or an unresolved entry."""
    line = RE_COMMENT_TAIL.sub('', raw, count=1).strip()
    if not line or line.startswith('-'):
        return
    m = RE_REQ_LINE.match(line.split(';')[0].strip())
    if not m:
        return
    name = normalize_pypi(m[1])
    rest = RE_REQ_HASH.sub('', m[3]).strip()
    if rest.startswith('@'):
        c.unresolve('PyPI', name, file, 'direct URL or path reference')
        return
    pin = RE_REQ_PIN.match(rest)
    if not pin or '*' in pin[1]:
        reason = f'not pinned to an exact version ({rest})' if rest else 'no version specified'
        c.unresolve('PyPI', name, file, reason)
        return
    c.add({'ecosystem': 'PyPI', 'name': name, 'version': pin[1], 'file': file, 'direct': True})


def parse_requirements(c: Collector, root: str, file: str) -> None:
    """requirements*.txt: only exact pins (== or ===) resolve."""
    text = RE_CONTINUATION.sub(' ', read_required(root, file))
    for raw in lines_of(text):
        requirement_line(c, file, raw)


# ---------------------------------------------------------------- crates.io

def cargo_direct(root: str, dir_: str) -> set[str]:
    """Dependency names declared in the directory's Cargo.toml."""
    text = read_text(root, join_path(dir_, 'Cargo.toml')) or ''
    names: set[str] = set()
    for section in RE_LINE_BRACKET.split(text):
        header = RE_CARGO_HEADER.match(section)
        if not header:
            continue
        title = header[1].strip()
        inline = RE_CARGO_INLINE.match(title)
        if inline:
            names.add(inline[2].strip())
        elif RE_CARGO_TABLE.match(title):
            names.update(m[1] for m in RE_CARGO_KEY.finditer(section))
    return names


def parse_cargo_lock(c: Collector, root: str, file: str) -> None:
    """Cargo.lock: only crates.io registry packages are in OSV's crates.io data."""
    text = read_required(root, file)
    direct = cargo_direct(root, dir_of(file))
    for block in toml_package_blocks(text):
        name = toml_string(block, 'name')
        version = toml_string(block, 'version')
        source = toml_string(block, 'source')
        if not name or not version or not source:
            continue
        if not RE_CARGO_REGISTRY.match(source):
            c.unresolve('crates.io', name, file, f"non-registry source ({source.split('+')[0]})")
        elif 'crates.io' not in source:
            c.unresolve('crates.io', name, file, 'alternative registry; not in OSV crates.io data')
        else:
            c.add({'ecosystem': 'crates.io', 'name': name, 'version': version, 'file': file,
                   'direct': name in direct})


# ---------------------------------------------------------------- Go

def add_go(c: Collector, spec: str, file: str, indirect: bool) -> None:
    """Record 'module vX.Y.Z' from a go.mod require directive."""
    m = RE_GO_SPEC.match(spec)
    if m:
        c.add({'ecosystem': 'Go', 'name': m[1], 'version': m[2], 'file': file,
               'direct': not indirect})


def parse_go_mod(c: Collector, root: str, file: str) -> None:
    """go.mod require directives, single-line and block."""
    in_block = False
    for raw in lines_of(read_required(root, file)):
        indirect = bool(RE_GO_INDIRECT.search(raw))
        line = raw.partition('//')[0].strip()
        if not line:
            continue
        if in_block:
            if line == ')':
                in_block = False
            else:
                add_go(c, line, file, indirect)
        elif RE_GO_REQUIRE_OPEN.match(line):
            in_block = True
        else:
            single = RE_GO_REQUIRE_ONE.match(line)
            if single:
                add_go(c, single[1], file, indirect)


# ---------------------------------------------------------------- NuGet

def xml_attr(tag: str, name: str) -> str | None:
    """Value of an XML attribute (case-insensitive name), stripped, or None."""
    m = XML_ATTRS[name].search(tag)
    return m[1].strip() if m else None


def strip_xml_comments(text: str) -> str:
    """Remove <!-- ... --> comments."""
    return RE_XML_COMMENT.sub('', text)


def central_versions(root: str, files: set[str], dir_: str) -> dict[str, str]:
    """Versions from Directory.Packages.props files up the tree; nearer files override."""
    versions: dict[str, str] = {}
    for d in reversed(ancestors(dir_)):
        file = join_path(d, 'Directory.Packages.props')
        if file not in files:
            continue
        text = strip_xml_comments(read_text(root, file) or '')
        for m in RE_PACKAGE_VERSION_TAG.finditer(text):
            ident = xml_attr(m[0], 'Include')
            version = xml_attr(m[0], 'Version')
            if ident and version:
                versions[ident.lower()] = version
    return versions


def parse_nuget_lock(c: Collector, root: str, file: str) -> None:
    """packages.lock.json."""
    lock = json_object(read_required(root, file))
    seen: set[tuple[str, str]] = set()
    for target in as_dict(lock.get('dependencies')).values():
        for name, raw in as_object(target).items():
            entry = as_object(raw)
            resolved = text_or_none(entry.get('resolved'))
            if not resolved or entry.get('type') == 'Project' or (name, resolved) in seen:
                continue
            seen.add((name, resolved))
            c.add({'ecosystem': 'NuGet', 'name': name, 'version': resolved, 'file': file,
                   'direct': entry.get('type') == 'Direct'})


def nuget_version(m: re.Match[str], tag: str, central: Mapping[str, str], name: str) -> str | None:
    """The version of a PackageReference: attribute, child element, then central management."""
    version = xml_attr(tag, 'VersionOverride') or xml_attr(tag, 'Version')
    if not version and m[3]:
        child = RE_VERSION_CHILD.search(m[3])
        version = child[1] if child else None
    return version or central.get(name.lower())


def parse_project_file(c: Collector, root: str, file: str, file_set: set[str]) -> None:
    """*.csproj, *.fsproj, *.vbproj PackageReference items."""
    text = strip_xml_comments(read_required(root, file))
    central = central_versions(root, file_set, dir_of(file))
    for m in RE_PACKAGE_REFERENCE.finditer(text):
        tag = f'<PackageReference {m[1]}>'
        name = xml_attr(tag, 'Include') or xml_attr(tag, 'Update')
        if not name:
            continue
        version = nuget_version(m, tag, central, name)
        if not version:
            c.unresolve('NuGet', name, file, 'no version (not in Directory.Packages.props)')
        elif '$(' in version:
            c.unresolve('NuGet', name, file, f'version from an MSBuild property ({version})')
        elif not RE_NUGET_EXACT.match(version):
            c.unresolve('NuGet', name, file, f'version range ({version})')
        else:
            c.add({'ecosystem': 'NuGet', 'name': name, 'version': version, 'file': file,
                   'direct': True})


# ---------------------------------------------------------------- RubyGems, Packagist

def parse_gemfile_lock(c: Collector, root: str, file: str) -> None:
    """Gemfile.lock: GEM specs plus the DEPENDENCIES section for direct flags."""
    section = ''
    in_specs = False
    direct: set[str] = set()
    specs: list[tuple[str, str]] = []
    for line in lines_of(read_required(root, file)):
        if RE_NON_SPACE_START.match(line):
            section = line.strip()
            in_specs = False
        elif section == 'DEPENDENCIES':
            m = RE_GEM_DEPENDENCY.match(line)
            if m:
                direct.add(m[1])
        elif section == 'GEM':
            if RE_GEM_SPECS.match(line):
                in_specs = True
                continue
            m = RE_GEM_SPEC.match(line) if in_specs else None
            if m:
                specs.append((m[1], RE_GEM_PLATFORM.sub('', m[2])))
    for name, version in specs:
        c.add({'ecosystem': 'RubyGems', 'name': name, 'version': version, 'file': file,
               'direct': name in direct})


def composer_direct(root: str, file: str) -> set[str]:
    """Names in composer.json require / require-dev (empty if missing or unreadable)."""
    try:
        manifest = as_object(json.loads(read_text(root, join_path(dir_of(file), 'composer.json'))
                                        or '{}'))
    except PARSE_ERRORS:
        return set()
    return set(as_dict(manifest.get('require'))) | set(as_dict(manifest.get('require-dev')))


def composer_entry(c: Collector, file: str, entry: dict[str, Any], dev: bool,
                   direct: set[str]) -> None:
    """Record one composer.lock package or an unresolved entry for a non-release version."""
    name = text_or_none(entry.get('name')) or '(unnamed)'
    raw = entry.get('version')
    version = raw.removeprefix('v') if isinstance(raw, str) else ''
    if not RE_DIGIT_START.match(version):
        c.unresolve('Packagist', name, file, f'branch or non-release version ({raw})')
        return
    pkg: Pkg = {'ecosystem': 'Packagist', 'name': name, 'version': version, 'file': file,
                'direct': name in direct}
    if dev:
        pkg['dev'] = True
    c.add(pkg)


def parse_composer_lock(c: Collector, root: str, file: str) -> None:
    """composer.lock."""
    lock = json_object(read_required(root, file))
    direct = composer_direct(root, file)
    for group, dev in (('packages', False), ('packages-dev', True)):
        entries = lock.get(group)
        for entry in entries if isinstance(entries, list) else []:
            composer_entry(c, file, as_object(entry), dev, direct)


# ---------------------------------------------------------------- Maven POM model

@dataclass(eq=False)
class PomDep:
    """One <dependency> element."""

    group_id: str | None
    artifact_id: str | None
    version: str | None
    scope: str | None
    type: str | None
    classifier: str | None
    optional: bool
    exclusions: list[str]


@dataclass(eq=False)
class PomParent:
    """A <parent> element."""

    group_id: str | None
    artifact_id: str | None
    version: str | None
    relative_path: str | None


@dataclass(eq=False)
class PomModel:
    """The parts of a POM that dependency resolution needs, plus per-model caches."""

    group_id: str | None = None
    artifact_id: str | None = None
    version: str | None = None
    parent: PomParent | None = None
    props: dict[str, str] = field(default_factory=dict)
    managed: list[PomDep] = field(default_factory=list)
    deps: list[PomDep] = field(default_factory=list)
    file: str | None = None
    parent_resolved: bool = False
    parent_model: PomModel | None = None
    effective: dict[str, str] | None = None


def xml_inner(text: str, tag: str) -> str | None:
    """Inner text of the first <tag>...</tag>, or None."""
    m = POM_INNER[tag].search(text)
    return m[1] if m else None


def xml_text(text: str, tag: str) -> str | None:
    """Stripped inner text of the first <tag>...</tag>, or None."""
    value = xml_inner(text, tag)
    return None if value is None else value.strip()


def remove_block(text: str, tag: str) -> str:
    """Delete every <tag>...</tag> block."""
    return POM_INNER[tag].sub('', text)


def parse_dependency_list(text: str | None) -> list[PomDep]:
    """The <dependency> elements in a <dependencies> body."""
    deps: list[PomDep] = []
    for m in RE_POM_DEPENDENCY.finditer(text or ''):
        exclusions_xml = xml_inner(m[1], 'exclusions') or ''
        d = remove_block(m[1], 'exclusions')
        exclusions = [f"{xml_text(e[1], 'groupId') or '*'}:{xml_text(e[1], 'artifactId') or '*'}"
                      for e in RE_POM_EXCLUSION.finditer(exclusions_xml)]
        deps.append(PomDep(
            xml_text(d, 'groupId'), xml_text(d, 'artifactId'), xml_text(d, 'version'),
            xml_text(d, 'scope'), xml_text(d, 'type'), xml_text(d, 'classifier'),
            xml_text(d, 'optional') == 'true', exclusions))
    return deps


def pom_parent(body: str) -> PomParent | None:
    """The <parent> element of a POM, if it has one."""
    parent_xml = xml_inner(body, 'parent')
    if not parent_xml:
        return None
    return PomParent(xml_text(parent_xml, 'groupId'), xml_text(parent_xml, 'artifactId'),
                     xml_text(parent_xml, 'version'), xml_text(parent_xml, 'relativePath'))


def parse_pom(text: str) -> PomModel:
    """Parse the dependency-relevant parts of a POM (no inheritance or interpolation yet)."""
    body = strip_xml_comments(text)
    for tag in POM_STRIPPED_BLOCKS:
        body = remove_block(body, tag)
    parent = pom_parent(body)
    managed_xml = xml_inner(body, 'dependencyManagement')
    body = remove_block(remove_block(body, 'parent'), 'dependencyManagement')
    deps_xml = xml_inner(body, 'dependencies')
    props_xml = xml_inner(body, 'properties') or ''
    core = body
    for tag in POM_NON_CORE_BLOCKS:
        core = remove_block(core, tag)
    return PomModel(
        group_id=xml_text(core, 'groupId') or (parent.group_id if parent else None),
        artifact_id=xml_text(core, 'artifactId'),
        version=xml_text(core, 'version') or (parent.version if parent else None),
        parent=parent,
        props={m[1]: m[2].strip() for m in RE_POM_PROPERTY.finditer(props_xml)},
        managed=parse_dependency_list(managed_xml and xml_inner(managed_xml, 'dependencies')),
        deps=parse_dependency_list(deps_xml))


def interpolate(value: str | None, props: Mapping[str, Any]) -> str | None:
    """Substitute ${name} references from props (up to 10 passes); unknown names stay as-is."""
    if value is None:
        return None
    out = value
    for _ in range(10):
        if '${' not in out:
            break
        nxt = RE_PROPERTY_REF.sub(
            lambda m: m[0] if props.get(m[1]) is None else str(props[m[1]]), out)
        if nxt == out:
            break
        out = nxt
    return out


def coords_of(dep: PomDep, props: Mapping[str, Any]) -> str | None:
    """The interpolated 'groupId:artifactId' of a dependency, or None if either part is missing."""
    group = interpolate(dep.group_id, props)
    artifact = interpolate(dep.artifact_id, props)
    return f'{group}:{artifact}' if group and artifact else None


# ---------------------------------------------------------------- Maven resolver

class MavenResolver:
    """Resolves parents, BOM imports, and managed versions across local and remote POMs."""

    def __init__(self, root: str, files: Sequence[str], opts: Mapping[str, Any]) -> None:
        """Parse every pom.xml in files; remote POMs are fetched through opts['fetchText']."""
        self.base: str = (opts.get('mavenBase') or MAVEN_CENTRAL).rstrip('/')
        self.fetch_text: FetchText | None = opts.get('fetchText')
        self.local: dict[str, PomModel] = {}
        self.remote: dict[str, PomModel | None] = {}
        self.fetch_failed = False
        for file in files:
            text = read_text(root, file) if base_of(file) == 'pom.xml' else None
            if not text:
                continue
            try:
                model = parse_pom(text)
            except PARSE_ERRORS:
                continue  # reported when the file itself is parsed
            model.file = file
            self.local[file] = model
        self.local_by_coords: dict[str, PomModel] = {
            f'{m.group_id}:{m.artifact_id}': m for m in self.local.values()
            if m.group_id and m.artifact_id}

    def fetch_model(self, group_id: str | None, artifact_id: str | None, version: str | None,
                    transitive: bool = False) -> PomModel | None:
        """A POM from this repository or the remote repository.

        transitive is True for dependency POMs, whose absence doesn't mean a parent or BOM failed.
        """
        if not group_id or not artifact_id or not version or '${' in version:
            return None
        local = self.local_by_coords.get(f'{group_id}:{artifact_id}')
        if local:
            return local
        url = (f"{self.base}/{group_id.replace('.', '/')}/{artifact_id}/{version}/"
               f"{artifact_id}-{version}.pom")
        if url not in self.remote:
            self.remote[url] = self.download(url)
        model = self.remote[url]
        if model is None and not transitive:
            self.fetch_failed = True
        return model

    def download(self, url: str) -> PomModel | None:
        """Fetch and parse one POM; None if unavailable or unparseable."""
        text = self.fetch_text(url) if self.fetch_text else None
        if not text:
            return None
        try:
            return parse_pom(text)
        except PARSE_ERRORS:
            return None

    def parent_of(self, model: PomModel) -> PomModel | None:
        """The parent POM: a local relativePath match first, then the remote repository."""
        if model.parent_resolved:
            return model.parent_model
        model.parent_resolved = True  # also breaks parent cycles
        p = model.parent
        if p is None:
            return None
        if model.file:
            relative = (p.relative_path or '../pom.xml').replace('\\', '/')
            rel = posixpath.normpath(join_path(dir_of(model.file), relative))
            candidate = self.local.get(rel if rel.endswith('.xml') else join_path(rel, 'pom.xml'))
            if candidate and candidate.artifact_id == p.artifact_id:
                model.parent_model = candidate
        if model.parent_model is None:
            model.parent_model = self.fetch_model(p.group_id, p.artifact_id, p.version)
        return model.parent_model

    def effective_props(self, model: PomModel, depth: int = 0) -> dict[str, str]:
        """Properties of the model merged over its parents', plus the project.* coordinates."""
        if model.effective is not None:
            return model.effective
        parent = self.parent_of(model) if depth < MAX_POM_DEPTH else None
        props = dict(self.effective_props(parent, depth + 1) if parent else {})
        props.update(model.props)
        coords: dict[str, str | None] = {
            'project.groupId': model.group_id, 'project.artifactId': model.artifact_id,
            'project.version': model.version, 'pom.version': model.version,
            'version': model.version}
        if model.parent:
            coords['project.parent.version'] = model.parent.version
            coords['parent.version'] = model.parent.version
            coords['project.parent.groupId'] = model.parent.group_id
        # A POM's own coordinates always replace the ones inherited from its parent.
        props.update({k: v for k, v in coords.items() if v is not None})
        model.effective = props
        return props

    def managed_version(self, model: PomModel, key: str, props: Mapping[str, Any],
                        depth: int = 0) -> str | None:
        """The managed version of 'group:artifact'.

        Maven precedence: this POM's own dependencyManagement, then the inherited (parent) one,
        then BOMs imported here. props is the requesting project's context, so a child's
        properties can override versions its parent manages.
        """
        if depth > MAX_POM_DEPTH:
            return None
        for d in model.managed:
            if d.scope != 'import' and d.version and coords_of(d, props) == key:
                return interpolate(d.version, props)
        parent = self.parent_of(model)
        found = self.managed_version(parent, key, props, depth + 1) if parent else None
        return found or self.imported_version(model, key, props, depth)

    def imported_version(self, model: PomModel, key: str, props: Mapping[str, Any],
                         depth: int) -> str | None:
        """Look the key up in the BOMs this POM imports."""
        for d in model.managed:
            if d.scope != 'import' or (d.type and d.type != 'pom'):
                continue
            bom = self.fetch_model(interpolate(d.group_id, props),
                                   interpolate(d.artifact_id, props),
                                   interpolate(d.version, props))
            found = self.managed_version(bom, key, self.effective_props(bom), depth + 1) if bom else None
            if found:
                return found
        return None


# ---------------------------------------------------------------- Maven transitive resolution
#
# An approximation of Maven's dependency mediation, from POM metadata only (nothing is built
# or executed): breadth-first from the project's direct dependencies; compile and runtime
# scopes only; optional, test, provided, and system dependencies are not followed; exclusions
# are inherited down the path. Version selection: the root project's dependencyManagement
# (including its parent and imported BOMs) wins, then nearest-wins, then declaration order.

@dataclass(eq=False)
class RootDep:
    """A direct dependency of the project, already resolved to a version."""

    key: str
    version: str
    scope: str
    exclusions: list[str]


@dataclass(eq=False)
class Node:
    """A queued transitive dependency."""

    key: str
    version: str
    depth: int
    exclusions: list[str]
    via: str


def split_key(key: str) -> tuple[str, str]:
    """('group', 'artifact') from 'group:artifact'."""
    parts = key.split(':')
    return parts[0], parts[1] if len(parts) > 1 else ''


def excluded(key: str, exclusions: Sequence[str]) -> bool:
    """True if any 'group:artifact' exclusion pattern (with * wildcards) matches the key."""
    group, artifact = split_key(key)
    for pattern in exclusions:
        ex_group, ex_artifact = split_key(pattern)
        if ex_group in ('*', group) and ex_artifact in ('*', artifact):
            return True
    return False


def bad_version(version: str | None) -> str | None:
    """Why a Maven version cannot be queried exactly, or None if it can."""
    if not version:
        return 'version not managed or declared'
    if '${' in version:
        return f'unresolved property in version ({version})'
    if RE_DYNAMIC_RANGE.match(version):
        return f'version range ({version})'
    return None


def declared_deps(maven: MavenResolver, model: PomModel) -> list[PomDep]:
    """Dependencies declared in a POM and its parent chain (Maven inherits <dependencies>)."""
    deps: list[PomDep] = []
    seen: set[int] = set()
    current: PomModel | None = model
    for _ in range(MAX_POM_DEPTH + 1):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        deps.extend(current.deps)
        current = maven.parent_of(current)
    return deps


class TransitiveResolver:
    """Breadth-first expansion of the compile/runtime dependency graph from POM metadata."""

    def __init__(self, c: Collector, maven: MavenResolver, file: str, root_model: PomModel,
                 roots: Sequence[RootDep]) -> None:
        """Seed the queue with the followable direct dependencies."""
        self.c = c
        self.maven = maven
        self.file = file
        self.root_model = root_model
        self.root_props = maven.effective_props(root_model)
        self.root_managed: dict[str, str | None] = {}
        self.selected: set[str] = {r.key for r in roots}
        self.reported: set[str] = set()
        self.queue: list[Node] = [
            Node(r.key, r.version, 1, list(r.exclusions), r.key)
            for r in roots if r.scope in FOLLOWED_SCOPES]
        self.capped = ''

    def run(self) -> None:
        """Expand the queue until it is empty or a limit is hit, then report any limit."""
        for node in self.queue:  # the loop also visits nodes appended while iterating
            if node.depth >= MAX_TRANSITIVE_DEPTH:
                self.capped = 'depth'
            elif len(self.maven.remote) >= MAX_TRANSITIVE_FETCHES:
                self.capped = 'fetches'
                break
            else:
                self.expand(node)
        if self.capped:
            limit = (f'depth {MAX_TRANSITIVE_DEPTH}' if self.capped == 'depth'
                     else f'{MAX_TRANSITIVE_FETCHES} POM downloads')
            self.c.unresolve('Maven', '(transitive dependencies)', self.file,
                             f'transitive resolution stopped at the {limit} limit; '
                             'deeper dependencies were not checked')

    def expand(self, node: Node) -> None:
        """Add the dependencies declared by the node's POM."""
        group, artifact = split_key(node.key)
        model = self.maven.fetch_model(group, artifact, node.version, True)
        if model is None:
            if node.key not in self.reported:
                self.reported.add(node.key)
                self.c.unresolve('Maven', f'{node.key}:{node.version}', self.file,
                                 'POM could not be fetched; its dependencies were not checked')
            return
        props = self.maven.effective_props(model)
        for dep in declared_deps(self.maven, model):
            self.consider(node, model, props, dep)

    def managed_by_root(self, key: str) -> str | None:
        """Version the root project's dependencyManagement assigns to the key (cached)."""
        if key not in self.root_managed:
            self.root_managed[key] = self.maven.managed_version(
                self.root_model, key, self.root_props)
        return self.root_managed[key]

    def consider(self, node: Node, model: PomModel, props: Mapping[str, Any], dep: PomDep) -> None:
        """Select one declared dependency, or report why it cannot be checked."""
        scope = interpolate(dep.scope, props) or 'compile'
        if scope not in FOLLOWED_SCOPES or dep.optional:
            return
        if (interpolate(dep.type, props) or 'jar') not in FOLLOWED_TYPES:
            return
        key = coords_of(dep, props)
        if not key or '${' in key or key in self.selected or excluded(key, node.exclusions):
            return
        version = self.managed_by_root(key) or (
            interpolate(dep.version, props) if dep.version
            else self.maven.managed_version(model, key, props))
        why = bad_version(version)
        if why or version is None:
            if key not in self.reported:
                self.reported.add(key)
                self.c.unresolve('Maven', key, self.file, why or 'version not managed or declared')
            return
        self.selected.add(key)
        self.c.add({'ecosystem': 'Maven', 'name': key, 'version': version, 'file': self.file,
                    'direct': False, 'via': node.via})
        self.queue.append(Node(key, version, node.depth + 1,
                               node.exclusions + dep.exclusions, node.via))


def resolve_transitive(c: Collector, maven: MavenResolver, file: str, root_model: PomModel,
                       roots: Sequence[RootDep]) -> None:
    """Add the transitive Maven dependencies of the roots, if remote POMs can be fetched."""
    if not maven.fetch_text:
        c.unresolve('Maven', '(transitive dependencies)', file,
                    'transitive dependencies need Maven Central access, a build, or a lockfile')
        return
    TransitiveResolver(c, maven, file, root_model, roots).run()


def add_pom_dependency(c: Collector, maven: MavenResolver, file: str, model: PomModel,
                       props: Mapping[str, Any], dep: PomDep, roots: list[RootDep]) -> None:
    """Record one direct dependency of a pom.xml (or why it cannot be checked)."""
    group = interpolate(dep.group_id, props)
    artifact = interpolate(dep.artifact_id, props)
    if not group or not artifact:
        return
    name = f'{group}:{artifact}'
    if name in maven.local_by_coords:
        return  # another module of this repository
    version = (interpolate(dep.version, props) if dep.version
               else maven.managed_version(model, name, props))
    if not version:
        why = ('version managed by a parent or BOM that could not be fetched'
               if maven.fetch_failed
               else 'version not found in dependencyManagement, parent, or imported BOMs')
        c.unresolve('Maven', name, file, why)
    elif '${' in version:
        c.unresolve('Maven', name, file, f'unresolved property in version ({version})')
    elif RE_DYNAMIC_RANGE.match(version):
        c.unresolve('Maven', name, file, f'version range ({version})')
    else:
        scope = interpolate(dep.scope, props)
        pkg: Pkg = {'ecosystem': 'Maven', 'name': name, 'version': version, 'file': file,
                    'direct': True}
        if scope and scope != 'compile':
            pkg['scope'] = scope
        c.add(pkg)
        roots.append(RootDep(name, version, scope or 'compile', dep.exclusions))


def parse_pom_file(c: Collector, maven: MavenResolver, file: str) -> None:
    """pom.xml: direct dependencies, then their transitive closure."""
    model = maven.local.get(file)
    if model is None:
        raise ValueError('unparseable pom')
    props = maven.effective_props(model)
    roots: list[RootDep] = []
    for dep in model.deps:
        add_pom_dependency(c, maven, file, model, props, dep, roots)
    if model.deps:
        resolve_transitive(c, maven, file, model, roots)


# ---------------------------------------------------------------- Gradle

def parse_gradle_lockfile(c: Collector, root: str, file: str) -> None:
    """gradle.lockfile and dependency-locks/*.lockfile."""
    for line in lines_of(read_required(root, file)):
        m = RE_GRADLE_LOCK_LINE.match(line)
        if m:
            c.add({'ecosystem': 'Maven', 'name': f'{m[1]}:{m[2]}', 'version': m[3], 'file': file,
                   'direct': False})


def toml_section(text: str, name: str) -> str:
    """Body of the [name] table (versions or libraries), or ''."""
    m = TOML_SECTIONS[name].search(text)
    return m[1] if m else ''


def catalog_versions(text: str) -> dict[str, str]:
    """The [versions] table of a Gradle version catalog."""
    versions: dict[str, str] = {}
    for m in RE_CATALOG_ENTRY.finditer(toml_section(text, 'versions')):
        value = m[2].strip()
        plain = RE_CATALOG_PLAIN.match(value)
        rich = RE_CATALOG_RICH.search(value)
        if plain:
            versions[m[1]] = plain[1]
        elif rich:
            versions[m[1]] = rich[1]
    return versions


def catalog_library(value: str, versions: Mapping[str, str]) -> tuple[str | None, str | None]:
    """(module, version) for one [libraries] entry; either may be None."""
    inline = RE_CATALOG_INLINE.match(value)
    if inline:
        return f'{inline[1]}:{inline[2]}', inline[3] or None
    mod = RE_CATALOG_MODULE.search(value)
    group = RE_CATALOG_GROUP.search(value)
    artifact = RE_CATALOG_NAME.search(value)
    module = mod[1] if mod else (f'{group[1]}:{artifact[1]}' if group and artifact else None)
    ref = RE_CATALOG_REF.search(value)
    literal = RE_CATALOG_LITERAL.search(value)
    if ref:
        return module, versions.get(ref[1] or ref[2])
    return module, literal[1] if literal else None


def parse_version_catalog(c: Collector, root: str, file: str) -> None:
    """gradle/libs.versions.toml."""
    text = RE_TOML_COMMENT.sub('', read_required(root, file))
    versions = catalog_versions(text)
    for m in RE_CATALOG_ENTRY.finditer(toml_section(text, 'libraries')):
        module, version = catalog_library(m[2].strip(), versions)
        if not module:
            continue
        if version and RE_DIGIT_START.match(version) and not RE_UNSUPPORTED_VERSION.search(version):
            c.add({'ecosystem': 'Maven', 'name': module, 'version': version, 'file': file,
                   'direct': True})
        else:
            reason = (f'version range or dynamic version ({version})' if version
                      else 'version managed by the Gradle plugin/BOM; needs a lockfile')
            c.unresolve('Maven', module, file, reason)


def gradle_vars(root: str, file: str, text: str) -> dict[str, str]:
    """String variables a build can use in versions: gradle.properties and ext/extra/val/def."""
    variables: dict[str, str] = {}
    for dir_ in reversed(ancestors(dir_of(file))):
        props = read_text(root, join_path(dir_, 'gradle.properties'))
        for m in RE_GRADLE_PROPERTY.finditer(props or ''):
            variables[m[1]] = m[2]
    for pattern in GRADLE_VAR_PATTERNS:
        for m in pattern.finditer(text):
            variables[m[1]] = m[2]
    for block in RE_EXT_BLOCK.finditer(text):
        for m in RE_EXT_ENTRY.finditer(block[1]):
            variables[m[1]] = m[2]
    return variables


def gradle_interpolate(value: str | None, variables: Mapping[str, str]) -> str | None:
    """Substitute $name and ${name} from the build's variables; unknown names stay as-is."""
    if value is None:
        return None
    return RE_GRADLE_VAR.sub(lambda m: variables.get(m[1] or m[2], m[0]), value)


def gradle_boms(text: str, variables: Mapping[str, str]) -> list[tuple[str, str, str | None]]:
    """BOMs that manage versions: Spring Boot's (with the dependency-management plugin),
    mavenBom imports, and platform()/enforcedPlatform()."""
    boms: list[tuple[str, str, str | None]] = []
    boot = RE_BOOT_PLUGIN.search(text) or RE_BOOT_CLASSPATH.search(text)
    if boot and RE_DEPENDENCY_MGMT.search(text):
        boms.append(('org.springframework.boot', 'spring-boot-dependencies',
                     gradle_interpolate(boot[1], variables)))
    for pattern in (RE_MAVEN_BOM, RE_PLATFORM):
        boms.extend((m[1], m[2], gradle_interpolate(m[3], variables))
                    for m in pattern.finditer(text))
    return boms


def gradle_root_model(boms: Sequence[tuple[str, str, str | None]]) -> PomModel:
    """A synthetic root project whose dependencyManagement imports the build's BOMs."""
    return PomModel(managed=[PomDep(g, a, v, 'import', 'pom', None, False, []) for g, a, v in boms])


def add_gradle_dependency(c: Collector, file: str, config: str, name: str,
                          version: str | None, has_boms: bool, roots: list[RootDep]) -> None:
    """Record one build.gradle dependency declaration (or why it cannot be checked)."""
    if not version:
        c.unresolve('Maven', name, file, 'version not managed by the imported BOMs' if has_boms
                    else 'version managed by the Gradle plugin/BOM; needs a lockfile')
    elif '$' in version:
        c.unresolve('Maven', name, file,
                    f"version from a variable that isn't defined in the build ({version})")
    elif RE_UNSUPPORTED_VERSION.search(version) or 'latest.' in version:
        c.unresolve('Maven', name, file, f'dynamic version ({version})')
    else:
        pkg: Pkg = {'ecosystem': 'Maven', 'name': name, 'version': version, 'file': file,
                    'direct': True}
        runtime = config in GRADLE_RUNTIME_CONFIGS
        if not runtime and config != 'classpath':
            pkg['scope'] = config
        c.add(pkg)
        if runtime:
            roots.append(RootDep(name, version, 'compile', []))


def parse_gradle_build(c: Collector, root: str, file: str, maven: MavenResolver | None) -> None:
    """build.gradle and build.gradle.kts dependency declarations."""
    text = RE_LINE_COMMENT.sub(r'\1', RE_BLOCK_COMMENT.sub('', read_required(root, file)))
    variables = gradle_vars(root, file, text)
    boms = gradle_boms(text, variables)
    root_model = gradle_root_model(boms)
    roots: list[RootDep] = []
    for m in RE_GRADLE_DECL.finditer(text):
        name = f'{m[2]}:{m[3]}'
        version = gradle_interpolate(m[4], variables)
        if not version and boms and maven:
            version = maven.managed_version(root_model, name, maven.effective_props(root_model))
        add_gradle_dependency(c, file, m[1], name, version, bool(boms), roots)
    if roots and maven:
        resolve_transitive(c, maven, file, root_model, roots)


# ---------------------------------------------------------------- entry point

def sort_and_dedupe(items: Sequence[Pkg], key_fn: Callable[[Pkg], tuple[str, ...]]) -> list[Pkg]:
    """Keep the first item per key (marking it direct if any duplicate is), sorted by key."""
    unique: dict[tuple[str, ...], Pkg] = {}
    for item in items:
        prev = unique.setdefault(key_fn(item), item)
        if item.get('direct') and not prev.get('direct'):
            prev['direct'] = True
    return [unique[key] for key in sorted(unique)]


def pkg_key(p: Pkg) -> tuple[str, ...]:
    """Identity of a package: ecosystem, name, version, file."""
    return p['ecosystem'], p['name'], p['version'], p['file']


def unresolved_key(u: Pkg) -> tuple[str, ...]:
    """Identity of an unresolved entry: ecosystem, name, file, reason."""
    return u['ecosystem'], u['name'], u['file'], u['reason']


# basename -> (ecosystem, parser label, parser function) for lockfiles named exactly.
SIMPLE_PARSERS: dict[str, tuple[str, str, Callable[[Collector, str, str], None]]] = {
    'package-lock.json': ('npm', 'package-lock', parse_package_lock),
    'npm-shrinkwrap.json': ('npm', 'package-lock', parse_package_lock),
    'yarn.lock': ('npm', 'yarn.lock', parse_yarn_lock),
    'pnpm-lock.yaml': ('npm', 'pnpm-lock', parse_pnpm_lock),
    'poetry.lock': ('PyPI', 'poetry.lock', parse_poetry_or_uv_lock),
    'uv.lock': ('PyPI', 'uv.lock', parse_poetry_or_uv_lock),
    'Pipfile.lock': ('PyPI', 'Pipfile.lock', parse_pipfile_lock),
    'Cargo.lock': ('crates.io', 'Cargo.lock', parse_cargo_lock),
    'go.mod': ('Go', 'go.mod', parse_go_mod),
    'packages.lock.json': ('NuGet', 'packages.lock.json', parse_nuget_lock),
    'Gemfile.lock': ('RubyGems', 'Gemfile.lock', parse_gemfile_lock),
    'composer.lock': ('Packagist', 'composer.lock', parse_composer_lock),
}


def is_gradle_lockfile(file: str) -> bool:
    """True for gradle.lockfile and dependency-locks/*.lockfile."""
    return base_of(file) == 'gradle.lockfile' or bool(RE_GRADLE_LOCKS_DIR.search(file))


def dispatch(c: Collector, root: str, file: str, file_set: set[str], maven: MavenResolver | None,
             nuget_lock_dirs: set[str], has_gradle_lockfiles: bool) -> None:
    """Run the parser that matches the file name, if any."""
    base = base_of(file)
    simple = SIMPLE_PARSERS.get(base)
    if simple:
        ecosystem, label, parser = simple
        parse_with(c, file, ecosystem, label, lambda: parser(c, root, file))
    elif RE_REQUIREMENTS_NAME.fullmatch(base):
        parse_with(c, file, 'PyPI', 'requirements', lambda: parse_requirements(c, root, file))
    elif RE_DOTNET_PROJECT.match(base) and dir_of(file) not in nuget_lock_dirs:
        parse_with(c, file, 'NuGet', 'project file',
                   lambda: parse_project_file(c, root, file, file_set))
    elif base == 'pom.xml' and maven is not None:
        parse_with(c, file, 'Maven', 'pom.xml', lambda: parse_pom_file(c, maven, file))
    elif is_gradle_lockfile(file):
        parse_with(c, file, 'Maven', 'gradle.lockfile',
                   lambda: parse_gradle_lockfile(c, root, file))
    elif base == 'libs.versions.toml' and not has_gradle_lockfiles:
        parse_with(c, file, 'Maven', 'version catalog',
                   lambda: parse_version_catalog(c, root, file))
    elif RE_GRADLE_BUILD_NAME.fullmatch(base) and not has_gradle_lockfiles:
        parse_with(c, file, 'Maven', 'build.gradle',
                   lambda: parse_gradle_build(c, root, file, maven))


def parse_lockfiles(root: str, file_list: Sequence[str],
                    opts: Mapping[str, Any] | None = None) -> dict[str, list[Pkg]]:
    """Extract packages from every lockfile and manifest in file_list.

    Returns {'packages', 'unresolved', 'sources'}; see the module docstring for the shapes.
    """
    opts = opts or {}
    c = Collector()
    files = sorted(f for f in (name.replace('\\', '/') for name in file_list)
                   if not RE_SKIP_DIRS.search(f'/{f}'))
    file_set = set(files)
    npm_lock_dirs = {dir_of(f) for f in files if base_of(f) in NPM_LOCK_NAMES}
    nuget_lock_dirs = {dir_of(f) for f in files if base_of(f) == 'packages.lock.json'}
    has_gradle_lockfiles = any(is_gradle_lockfile(f) for f in files)
    needs_maven = any(base_of(f) == 'pom.xml' or RE_GRADLE_BUILD_NAME.fullmatch(base_of(f))
                      for f in files)
    maven = MavenResolver(root, files, opts) if needs_maven else None
    for file in files:
        dispatch(c, root, file, file_set, maven, nuget_lock_dirs, has_gradle_lockfiles)
    check_npm_without_lockfile(c, root, files, npm_lock_dirs)
    return {
        'packages': sort_and_dedupe(c.packages, pkg_key),
        'unresolved': sort_and_dedupe(c.unresolved, unresolved_key),
        'sources': sorted(c.sources, key=lambda s: s['file']),
    }
