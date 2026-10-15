'use strict';
// Deterministic dependency extraction from lockfiles and manifests, for the OSV.dev lookup.
// Node.js 18+ standard library only. Reads files; never runs project code.
//
// parseLockfiles(root, files, opts) -> { packages, unresolved, sources }
//   files: repo-relative paths (forward slashes) of every tracked file
//   opts.fetchText(url) -> string|null: synchronous GET, used only for Maven parent/BOM POMs
//   opts.mavenBase: Maven repository base URL (default Maven Central)

const fs = require('fs');
const path = require('path');

const SKIP_DIRS = /(^|\/)(node_modules|vendor|\.appsec-audit)\//;
const MAVEN_CENTRAL = 'https://repo1.maven.org/maven2';
const MAX_POM_DEPTH = 6;

function readFile(root, file) {
  try {
    return fs.readFileSync(path.join(root, file), 'utf8');
  } catch {
    return null;
  }
}

function dirOf(file) {
  const i = file.lastIndexOf('/');
  return i < 0 ? '' : file.slice(0, i);
}

function baseOf(file) {
  return file.slice(file.lastIndexOf('/') + 1);
}

function joinPath(dir, name) {
  return dir ? `${dir}/${name}` : name;
}

function ancestors(dir) {
  const out = [dir];
  while (dir) {
    dir = dirOf(dir);
    out.push(dir);
  }
  return out;
}

function normalizePypi(name) {
  return name.toLowerCase().replace(/[-_.]+/g, '-');
}

function createCollector() {
  const c = { packages: [], unresolved: [], sources: [] };
  c.add = (pkg) => c.packages.push(pkg);
  c.unresolve = (ecosystem, name, file, reason) => c.unresolved.push({ ecosystem, name, file, reason });
  c.source = (file, ecosystem, parser, count) => c.sources.push({ file, ecosystem, parser, count });
  return c;
}

// Run one parser, recording the file as a source, or as unparseable if it throws.
function parseWith(c, file, ecosystem, parser, fn) {
  const before = c.packages.length;
  try {
    fn();
  } catch {
    c.packages.length = before;
    c.unresolve(ecosystem, '(file)', file, 'could not parse');
    return;
  }
  c.source(file, ecosystem, parser, c.packages.length - before);
}

// ---------------------------------------------------------------- npm

function packageJsonDeps(root, dir) {
  const text = readFile(root, joinPath(dir, 'package.json'));
  if (!text) return null;
  const pkg = JSON.parse(text);
  const deps = {};
  for (const field of ['dependencies', 'devDependencies', 'optionalDependencies']) {
    Object.assign(deps, pkg[field] || {});
  }
  return deps;
}

function directSetFor(root, dir) {
  try {
    return new Set(Object.keys(packageJsonDeps(root, dir) || {}));
  } catch {
    return new Set();
  }
}

function parsePackageLock(c, root, file) {
  const lock = JSON.parse(readFile(root, file));
  const direct = directSetFor(root, dirOf(file));
  if (lock.packages && (lock.lockfileVersion || 0) >= 2) {
    const rootEntry = lock.packages[''] || {};
    for (const field of ['dependencies', 'devDependencies', 'optionalDependencies']) {
      for (const name of Object.keys(rootEntry[field] || {})) direct.add(name);
    }
    for (const [key, entry] of Object.entries(lock.packages)) {
      if (key === '' || !key.includes('node_modules/') || entry.link || !entry.version) continue;
      const name = entry.name || key.slice(key.lastIndexOf('node_modules/') + 'node_modules/'.length);
      addNpm(c, name, entry.version, file, direct.has(name) && key === `node_modules/${name}`, entry.dev);
    }
    return;
  }
  const walk = (deps, depth) => {
    for (const [name, entry] of Object.entries(deps || {})) {
      if (entry.version) addNpm(c, name, entry.version, file, depth === 0 && direct.has(name), entry.dev);
      walk(entry.dependencies, depth + 1);
    }
  };
  walk(lock.dependencies, 0);
}

function addNpm(c, name, version, file, direct, dev) {
  if (!/^\d/.test(version)) {
    c.unresolve('npm', name, file, `non-registry version (${version})`);
    return;
  }
  const pkg = { ecosystem: 'npm', name, version, file, direct: Boolean(direct) };
  if (dev) pkg.dev = true;
  c.add(pkg);
}

// "name@range" -> name; handles scoped packages and Berry's "name@npm:range".
function specName(spec) {
  const at = spec.lastIndexOf('@');
  return at > 0 ? spec.slice(0, at) : spec;
}

function parseYarnLock(c, root, file) {
  const text = readFile(root, file);
  const direct = directSetFor(root, dirOf(file));
  const berry = /^__metadata:/m.test(text);
  const seen = new Set();
  let names = null;
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.startsWith('#')) continue;
    if (!/^\s/.test(line)) {
      if (line.startsWith('__metadata')) {
        names = null;
        continue;
      }
      const specs = line.replace(/:\s*$/, '').split(/,\s*/).map((s) => s.trim().replace(/^"|"$/g, ''));
      if (specs.some((s) => /@(workspace|patch|link|portal|file):/.test(s))) {
        names = null;
        continue;
      }
      names = [...new Set(specs.map(specName))];
      continue;
    }
    if (!names) continue;
    const m = berry ? line.match(/^\s{2}version:\s*"?([^"\s]+)"?\s*$/) : line.match(/^\s{2}version\s+"([^"]+)"\s*$/);
    if (!m) continue;
    for (const name of names) {
      const key = `${name}@${m[1]}`;
      if (seen.has(key)) continue;
      seen.add(key);
      addNpm(c, name, m[1], file, direct.has(name), false);
    }
    names = null;
  }
}

function parsePnpmLock(c, root, file) {
  const text = readFile(root, file);
  const direct = directSetFor(root, dirOf(file));
  let inPackages = false;
  const seen = new Set();
  for (const line of text.split(/\r?\n/)) {
    if (/^\S/.test(line)) {
      inPackages = /^packages:\s*$/.test(line);
      continue;
    }
    if (!inPackages) continue;
    const m = line.match(/^ {2}(?! )(['"]?)(.+?)\1:\s*$/);
    if (!m) continue;
    let key = m[2].replace(/^\//, '').replace(/\(.*$/, '');
    let name;
    let version;
    const at = key.lastIndexOf('@');
    if (at > 0) {
      name = key.slice(0, at);
      version = key.slice(at + 1);
    } else {
      const slash = key.lastIndexOf('/');
      if (slash <= 0) continue;
      name = key.slice(0, slash);
      version = key.slice(slash + 1);
    }
    version = version.replace(/_.*$/, '');
    const id = `${name}@${version}`;
    if (seen.has(id)) continue;
    seen.add(id);
    addNpm(c, name, version, file, direct.has(name), false);
  }
}

// A package.json with no lockfile in its directory or any ancestor can't be checked exactly.
function checkNpmWithoutLockfile(c, root, files, lockDirs) {
  for (const file of files) {
    if (baseOf(file) !== 'package.json') continue;
    if (ancestors(dirOf(file)).some((d) => lockDirs.has(d))) continue;
    let deps;
    try {
      deps = packageJsonDeps(root, dirOf(file));
    } catch {
      c.unresolve('npm', '(file)', file, 'could not parse');
      continue;
    }
    for (const name of Object.keys(deps || {})) c.unresolve('npm', name, file, 'no lockfile');
  }
}

// ---------------------------------------------------------------- PyPI

function tomlPackageBlocks(text) {
  return text.split(/^\[\[package\]\]\s*$/m).slice(1).map((block) => block.split(/^\[(?!\[package\])/m)[0]);
}

function tomlString(block, key) {
  const m = block.match(new RegExp(`^${key}\\s*=\\s*"([^"]*)"`, 'm'));
  return m ? m[1] : null;
}

function pyprojectDirect(root, dir) {
  const text = readFile(root, joinPath(dir, 'pyproject.toml'));
  const names = new Set();
  if (!text) return names;
  const project = text.match(/^\[project\][\s\S]*?^dependencies\s*=\s*\[([\s\S]*?)\]/m);
  if (project) {
    for (const m of project[1].matchAll(/["']([A-Za-z0-9][A-Za-z0-9._-]*)/g)) names.add(normalizePypi(m[1]));
  }
  const sections = text.split(/^\[/m);
  for (const section of sections) {
    if (!/^tool\.poetry\.(dependencies|dev-dependencies|group\.[^\]]+\.dependencies)\]/.test(section)) continue;
    for (const m of section.matchAll(/^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=/gm)) {
      if (m[1].toLowerCase() !== 'python') names.add(normalizePypi(m[1]));
    }
  }
  return names;
}

function parsePoetryOrUvLock(c, root, file) {
  const text = readFile(root, file);
  const direct = pyprojectDirect(root, dirOf(file));
  for (const block of tomlPackageBlocks(text)) {
    const name = tomlString(block, 'name');
    const version = tomlString(block, 'version');
    if (!name || !version) continue;
    if (/^source\s*=\s*\{\s*(editable|virtual)\s*=\s*"\."/m.test(block)) continue;
    const norm = normalizePypi(name);
    c.add({ ecosystem: 'PyPI', name: norm, version, file, direct: direct.has(norm) });
  }
}

function parsePipfileLock(c, root, file) {
  const lock = JSON.parse(readFile(root, file));
  const pipfile = readFile(root, joinPath(dirOf(file), 'Pipfile')) || '';
  const direct = new Set();
  for (const section of pipfile.split(/^\[/m)) {
    if (!/^(packages|dev-packages)\]/.test(section)) continue;
    for (const m of section.matchAll(/^"?([A-Za-z0-9][A-Za-z0-9._-]*)"?\s*=/gm)) direct.add(normalizePypi(m[1]));
  }
  for (const group of ['default', 'develop']) {
    for (const [name, entry] of Object.entries(lock[group] || {})) {
      const norm = normalizePypi(name);
      const version = String(entry.version || '');
      if (!version.startsWith('==')) {
        c.unresolve('PyPI', norm, file, entry.git || entry.path ? 'non-registry source' : 'no exact version');
        continue;
      }
      const pkg = { ecosystem: 'PyPI', name: norm, version: version.slice(2), file, direct: direct.has(norm) };
      if (group === 'develop') pkg.dev = true;
      c.add(pkg);
    }
  }
}

function parseRequirements(c, root, file) {
  const text = readFile(root, file).replace(/\\\r?\n/g, ' ');
  for (let line of text.split(/\r?\n/)) {
    line = line.replace(/(^|\s)#.*$/, '').trim();
    if (!line || line.startsWith('-')) continue;
    line = line.split(';')[0].trim();
    const nameMatch = line.match(/^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*(.*)$/);
    if (!nameMatch) continue;
    const name = normalizePypi(nameMatch[1]);
    const rest = nameMatch[3].replace(/\s+--hash=\S+/g, '').trim();
    if (rest.startsWith('@')) {
      c.unresolve('PyPI', name, file, 'direct URL or path reference');
      continue;
    }
    const pin = rest.match(/^===?\s*([^\s,]+)$/);
    if (!pin || pin[1].includes('*')) {
      c.unresolve('PyPI', name, file, rest ? `not pinned to an exact version (${rest})` : 'no version specified');
      continue;
    }
    c.add({ ecosystem: 'PyPI', name, version: pin[1], file, direct: true });
  }
}

// ---------------------------------------------------------------- crates.io

function cargoDirect(root, dir) {
  const text = readFile(root, joinPath(dir, 'Cargo.toml')) || '';
  const names = new Set();
  for (const section of text.split(/^\[/m)) {
    const header = section.match(/^([^\]]+)\]/);
    if (!header) continue;
    const h = header[1].trim();
    const inline = h.match(/^(?:target\..+\.)?(?:workspace\.)?(dependencies|dev-dependencies|build-dependencies)\.(.+)$/);
    if (inline) {
      names.add(inline[2].trim());
      continue;
    }
    if (!/^(?:target\..+\.)?(?:workspace\.)?(dependencies|dev-dependencies|build-dependencies)$/.test(h)) continue;
    for (const m of section.matchAll(/^([A-Za-z0-9_-]+)\s*=/gm)) names.add(m[1]);
  }
  return names;
}

function parseCargoLock(c, root, file) {
  const text = readFile(root, file);
  const direct = cargoDirect(root, dirOf(file));
  for (const block of tomlPackageBlocks(text)) {
    const name = tomlString(block, 'name');
    const version = tomlString(block, 'version');
    const source = tomlString(block, 'source');
    if (!name || !version || !source) continue;
    if (!/^(registry|sparse)\+/.test(source)) {
      c.unresolve('crates.io', name, file, `non-registry source (${source.split('+')[0]})`);
      continue;
    }
    if (!/crates\.io/.test(source)) {
      c.unresolve('crates.io', name, file, 'alternative registry; not in OSV crates.io data');
      continue;
    }
    c.add({ ecosystem: 'crates.io', name, version, file, direct: direct.has(name) });
  }
}

// ---------------------------------------------------------------- Go

function parseGoMod(c, root, file) {
  const text = readFile(root, file);
  let inRequire = false;
  for (const raw of text.split(/\r?\n/)) {
    const indirect = /\/\/\s*indirect\b/.test(raw);
    const line = raw.replace(/\/\/.*$/, '').trim();
    if (!line) continue;
    if (inRequire) {
      if (line === ')') {
        inRequire = false;
        continue;
      }
      addGo(c, line, file, indirect);
      continue;
    }
    if (/^require\s*\($/.test(line)) {
      inRequire = true;
      continue;
    }
    const single = line.match(/^require\s+(.+)$/);
    if (single) addGo(c, single[1], file, indirect);
  }
}

function addGo(c, spec, file, indirect) {
  const m = spec.match(/^(\S+)\s+(v\S+)$/);
  if (m) c.add({ ecosystem: 'Go', name: m[1], version: m[2], file, direct: !indirect });
}

// ---------------------------------------------------------------- NuGet

function xmlAttr(tag, name) {
  const m = tag.match(new RegExp(`\\b${name}\\s*=\\s*"([^"]*)"`, 'i'));
  return m ? m[1].trim() : null;
}

function stripXmlComments(text) {
  return text.replace(/<!--[\s\S]*?-->/g, '');
}

function centralVersions(root, files, dir) {
  const versions = {};
  for (const d of ancestors(dir).reverse()) {
    const file = joinPath(d, 'Directory.Packages.props');
    if (!files.has(file)) continue;
    const text = stripXmlComments(readFile(root, file) || '');
    for (const m of text.matchAll(/<PackageVersion\b[^>]*>/gi)) {
      const id = xmlAttr(m[0], 'Include');
      const version = xmlAttr(m[0], 'Version');
      if (id && version) versions[id.toLowerCase()] = version;
    }
  }
  return versions;
}

function nugetExact(version) {
  return /^\d+(\.\d+){0,3}(-[0-9A-Za-z.-]+)?$/.test(version);
}

function parseNugetLock(c, root, file) {
  const lock = JSON.parse(readFile(root, file));
  const seen = new Set();
  for (const target of Object.values(lock.dependencies || {})) {
    for (const [name, entry] of Object.entries(target)) {
      if (!entry.resolved || entry.type === 'Project') continue;
      const key = `${name}@${entry.resolved}`;
      if (seen.has(key)) continue;
      seen.add(key);
      c.add({ ecosystem: 'NuGet', name, version: entry.resolved, file, direct: entry.type === 'Direct' });
    }
  }
}

function parseProjectFile(c, root, file, fileSet) {
  const text = stripXmlComments(readFile(root, file));
  const central = centralVersions(root, fileSet, dirOf(file));
  const refs = text.matchAll(/<PackageReference\b([^>]*?)(\/>|>([\s\S]*?)<\/PackageReference>)/gi);
  for (const m of refs) {
    const tag = `<PackageReference ${m[1]}>`;
    const name = xmlAttr(tag, 'Include') || xmlAttr(tag, 'Update');
    if (!name) continue;
    let version = xmlAttr(tag, 'VersionOverride') || xmlAttr(tag, 'Version');
    if (!version && m[3]) {
      const child = m[3].match(/<Version>\s*([^<]+?)\s*<\/Version>/i);
      if (child) version = child[1];
    }
    if (!version) version = central[name.toLowerCase()] || null;
    if (!version) {
      c.unresolve('NuGet', name, file, 'no version (not in Directory.Packages.props)');
    } else if (version.includes('$(')) {
      c.unresolve('NuGet', name, file, `version from an MSBuild property (${version})`);
    } else if (!nugetExact(version)) {
      c.unresolve('NuGet', name, file, `version range (${version})`);
    } else {
      c.add({ ecosystem: 'NuGet', name, version, file, direct: true });
    }
  }
}

// ---------------------------------------------------------------- RubyGems, Packagist

function parseGemfileLock(c, root, file) {
  const text = readFile(root, file);
  let section = '';
  let inSpecs = false;
  const direct = new Set();
  const specs = [];
  for (const line of text.split(/\r?\n/)) {
    if (/^\S/.test(line)) {
      section = line.trim();
      inSpecs = false;
      continue;
    }
    if (section === 'DEPENDENCIES') {
      const m = line.match(/^ {2}([^\s!(]+)/);
      if (m) direct.add(m[1]);
      continue;
    }
    if (section !== 'GEM') continue;
    if (/^ {2}specs:\s*$/.test(line)) {
      inSpecs = true;
      continue;
    }
    if (!inSpecs) continue;
    const m = line.match(/^ {4}([^\s(]+) \(([^)]+)\)\s*$/);
    if (m) specs.push([m[1], m[2].replace(/-(x86|x64|arm|aarch|universal|java|mingw|mswin|darwin|linux)[\w-]*$/, '')]);
  }
  for (const [name, version] of specs) c.add({ ecosystem: 'RubyGems', name, version, file, direct: direct.has(name) });
}

function parseComposerLock(c, root, file) {
  const lock = JSON.parse(readFile(root, file));
  let direct = new Set();
  try {
    const manifest = JSON.parse(readFile(root, joinPath(dirOf(file), 'composer.json')) || '{}');
    direct = new Set([...Object.keys(manifest.require || {}), ...Object.keys(manifest['require-dev'] || {})]);
  } catch {
    // direct flags stay false
  }
  for (const [group, dev] of [['packages', false], ['packages-dev', true]]) {
    for (const entry of lock[group] || []) {
      const version = String(entry.version || '').replace(/^v/, '');
      if (!/^\d/.test(version)) {
        c.unresolve('Packagist', entry.name, file, `branch or non-release version (${entry.version})`);
        continue;
      }
      const pkg = { ecosystem: 'Packagist', name: entry.name, version, file, direct: direct.has(entry.name) };
      if (dev) pkg.dev = true;
      c.add(pkg);
    }
  }
}

// ---------------------------------------------------------------- Maven

function xmlInner(text, tag) {
  const m = text.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)</${tag}>`));
  return m ? m[1] : null;
}

function xmlText(text, tag) {
  const v = xmlInner(text, tag);
  return v == null ? null : v.trim();
}

function removeBlock(text, tag) {
  return text.replace(new RegExp(`<${tag}(?:\\s[^>]*)?>[\\s\\S]*?</${tag}>`, 'g'), '');
}

function parseDependencyList(text) {
  if (!text) return [];
  const deps = [];
  for (const m of text.matchAll(/<dependency>([\s\S]*?)<\/dependency>/g)) {
    const exclusionsXml = xmlInner(m[1], 'exclusions') || '';
    const d = removeBlock(m[1], 'exclusions');
    const exclusions = [];
    for (const e of exclusionsXml.matchAll(/<exclusion>([\s\S]*?)<\/exclusion>/g)) {
      exclusions.push(`${xmlText(e[1], 'groupId') || '*'}:${xmlText(e[1], 'artifactId') || '*'}`);
    }
    deps.push({
      groupId: xmlText(d, 'groupId'),
      artifactId: xmlText(d, 'artifactId'),
      version: xmlText(d, 'version'),
      scope: xmlText(d, 'scope'),
      type: xmlText(d, 'type'),
      classifier: xmlText(d, 'classifier'),
      optional: xmlText(d, 'optional') === 'true',
      exclusions,
    });
  }
  return deps;
}

function parsePom(text) {
  let body = stripXmlComments(text);
  for (const tag of ['build', 'profiles', 'reporting']) body = removeBlock(body, tag);
  const parentXml = xmlInner(body, 'parent');
  const parent = parentXml
    ? {
      groupId: xmlText(parentXml, 'groupId'),
      artifactId: xmlText(parentXml, 'artifactId'),
      version: xmlText(parentXml, 'version'),
      relativePath: xmlText(parentXml, 'relativePath'),
    }
    : null;
  const managedXml = xmlInner(body, 'dependencyManagement');
  body = removeBlock(removeBlock(body, 'parent'), 'dependencyManagement');
  const depsXml = xmlInner(body, 'dependencies');
  const propsXml = xmlInner(body, 'properties') || '';
  let core = body;
  for (const tag of ['dependencies', 'properties', 'modules', 'distributionManagement', 'repositories', 'pluginRepositories', 'developers', 'contributors', 'scm', 'organization', 'licenses', 'issueManagement', 'ciManagement', 'mailingLists']) {
    core = removeBlock(core, tag);
  }
  const props = {};
  for (const m of propsXml.matchAll(/<([A-Za-z0-9_.-]+)>([^<]*)<\/\1>/g)) props[m[1]] = m[2].trim();
  return {
    groupId: xmlText(core, 'groupId') || (parent && parent.groupId),
    artifactId: xmlText(core, 'artifactId'),
    version: xmlText(core, 'version') || (parent && parent.version),
    parent,
    props,
    managed: parseDependencyList(managedXml && xmlInner(managedXml, 'dependencies')),
    deps: parseDependencyList(depsXml),
  };
}

function interpolate(value, props) {
  if (value == null) return value;
  let out = value;
  for (let i = 0; i < 10 && out.includes('${'); i++) {
    const next = out.replace(/\$\{([^}]+)\}/g, (all, key) => (props[key] != null ? props[key] : all));
    if (next === out) break;
    out = next;
  }
  return out;
}

function createMavenResolver(root, files, opts) {
  const base = (opts.mavenBase || MAVEN_CENTRAL).replace(/\/+$/, '');
  const fetchText = opts.fetchText;
  const local = new Map();
  const remote = new Map();
  const state = { fetchFailed: false };

  for (const file of files) {
    if (baseOf(file) !== 'pom.xml') continue;
    const text = readFile(root, file);
    if (!text) continue;
    try {
      const model = parsePom(text);
      model.file = file;
      local.set(file, model);
    } catch {
      // reported when the file itself is parsed
    }
  }
  const localByCoords = new Map();
  for (const model of local.values()) {
    if (model.groupId && model.artifactId) localByCoords.set(`${model.groupId}:${model.artifactId}`, model);
  }

  // transitive: true for dependency POMs, whose absence doesn't mean a parent or BOM failed.
  function fetchModel(groupId, artifactId, version, transitive = false) {
    if (!groupId || !artifactId || !version || version.includes('${')) return null;
    const key = `${groupId}:${artifactId}`;
    if (localByCoords.has(key)) return localByCoords.get(key);
    const url = `${base}/${groupId.replace(/\./g, '/')}/${artifactId}/${version}/${artifactId}-${version}.pom`;
    if (remote.has(url)) {
      const cached = remote.get(url);
      if (!cached && !transitive) state.fetchFailed = true;
      return cached;
    }
    let model = null;
    const text = fetchText ? fetchText(url) : null;
    if (text) {
      try {
        model = parsePom(text);
      } catch {
        model = null;
      }
    }
    if (!model && !transitive) state.fetchFailed = true;
    remote.set(url, model);
    return model;
  }

  function parentOf(model) {
    if (model.parentModel !== undefined) return model.parentModel;
    model.parentModel = null;
    const p = model.parent;
    if (p) {
      if (model.file) {
        const rel = path.posix.normalize(joinPath(dirOf(model.file), (p.relativePath || '../pom.xml').replace(/\\/g, '/')));
        const relFile = rel.endsWith('.xml') ? rel : joinPath(rel, 'pom.xml');
        const candidate = local.get(relFile);
        if (candidate && candidate.artifactId === p.artifactId) model.parentModel = candidate;
      }
      if (!model.parentModel) model.parentModel = fetchModel(p.groupId, p.artifactId, p.version);
    }
    return model.parentModel;
  }

  function effectiveProps(model, depth = 0) {
    if (model.effective) return model.effective;
    const parent = depth < MAX_POM_DEPTH ? parentOf(model) : null;
    const props = Object.assign({}, parent ? effectiveProps(parent, depth + 1) : {}, model.props);
    const coords = {
      'project.groupId': model.groupId,
      'project.artifactId': model.artifactId,
      'project.version': model.version,
      'pom.version': model.version,
      version: model.version,
    };
    if (model.parent) {
      coords['project.parent.version'] = model.parent.version;
      coords['parent.version'] = model.parent.version;
      coords['project.parent.groupId'] = model.parent.groupId;
    }
    // A POM's own coordinates always replace the ones inherited from its parent.
    for (const [k, v] of Object.entries(coords)) if (v != null) props[k] = v;
    model.effective = props;
    return props;
  }

  // Maven precedence: this POM's own dependencyManagement, then the inherited (parent) one,
  // then BOMs imported here. `props` is the requesting project's context, so a child's
  // properties can override versions its parent manages.
  function managedVersion(model, key, props, depth = 0) {
    if (depth > MAX_POM_DEPTH) return null;
    for (const d of model.managed) {
      if (d.scope === 'import') continue;
      if (`${interpolate(d.groupId, props)}:${interpolate(d.artifactId, props)}` === key && d.version) {
        return interpolate(d.version, props);
      }
    }
    const parent = parentOf(model);
    if (parent) {
      const found = managedVersion(parent, key, props, depth + 1);
      if (found) return found;
    }
    for (const d of model.managed) {
      if (d.scope !== 'import' || (d.type && d.type !== 'pom')) continue;
      const bom = fetchModel(interpolate(d.groupId, props), interpolate(d.artifactId, props), interpolate(d.version, props));
      if (!bom) continue;
      const found = managedVersion(bom, key, effectiveProps(bom), depth + 1);
      if (found) return found;
    }
    return null;
  }

  return { local, localByCoords, state, remote, fetchText, fetchModel, parentOf, effectiveProps, managedVersion };
}

// ---------------------------------------------------------------- Maven transitive resolution
//
// An approximation of Maven's dependency mediation, from POM metadata only (nothing is built
// or executed): breadth-first from the project's direct dependencies; compile and runtime
// scopes only; optional, test, provided, and system dependencies are not followed; exclusions
// are inherited down the path. Version selection: the root project's dependencyManagement
// (including its parent and imported BOMs) wins, then nearest-wins, then declaration order.

const MAX_TRANSITIVE_DEPTH = 12;
const MAX_TRANSITIVE_FETCHES = 1500;
const FOLLOWED_SCOPES = new Set(['compile', 'runtime']);
const FOLLOWED_TYPES = new Set(['jar', 'bundle', 'pom']);

function excluded(key, exclusions) {
  const [g, a] = key.split(':');
  return exclusions.some((x) => {
    const [eg, ea] = x.split(':');
    return (eg === '*' || eg === g) && (ea === '*' || ea === a);
  });
}

function badVersion(version) {
  if (!version) return 'version not managed or declared';
  if (version.includes('${')) return `unresolved property in version (${version})`;
  if (/^[[(]/.test(version)) return `version range (${version})`;
  return null;
}

// Dependencies declared in a POM and its parent chain (Maven inherits <dependencies>).
function declaredDeps(maven, model) {
  const deps = [];
  const seen = new Set();
  for (let m = model, depth = 0; m && depth <= MAX_POM_DEPTH && !seen.has(m); m = maven.parentOf(m), depth++) {
    seen.add(m);
    for (const d of m.deps) deps.push({ d, owner: m });
  }
  return deps;
}

// roots: [{ key, version, scope, exclusions, order }] — the project's direct dependencies,
// already resolved. rootModel supplies the project's dependencyManagement.
function resolveTransitive(c, maven, file, rootModel, roots) {
  if (!maven.fetchText) {
    c.unresolve('Maven', '(transitive dependencies)', file, 'transitive dependencies need Maven Central access, a build, or a lockfile');
    return;
  }
  const rootProps = maven.effectiveProps(rootModel);
  const rootManagedCache = new Map();
  const rootManaged = (key) => {
    if (!rootManagedCache.has(key)) rootManagedCache.set(key, maven.managedVersion(rootModel, key, rootProps));
    return rootManagedCache.get(key);
  };
  const selected = new Set(roots.map((r) => r.key));
  const reported = new Set();
  const queue = roots
    .filter((r) => FOLLOWED_SCOPES.has(r.scope || 'compile'))
    .map((r) => ({ key: r.key, version: r.version, depth: 1, exclusions: r.exclusions || [], via: r.key }));
  let capped = false;

  for (let i = 0; i < queue.length; i++) {
    const node = queue[i];
    if (node.depth >= MAX_TRANSITIVE_DEPTH) { capped = 'depth'; continue; }
    if (maven.remote.size >= MAX_TRANSITIVE_FETCHES) { capped = 'fetches'; break; }
    const [g, a] = node.key.split(':');
    const model = maven.fetchModel(g, a, node.version, true);
    if (!model) {
      if (!reported.has(node.key)) {
        reported.add(node.key);
        c.unresolve('Maven', `${node.key}:${node.version}`, file, 'POM could not be fetched; its dependencies were not checked');
      }
      continue;
    }
    const props = maven.effectiveProps(model);
    for (const { d } of declaredDeps(maven, model)) {
      const scope = interpolate(d.scope, props) || 'compile';
      if (!FOLLOWED_SCOPES.has(scope) || d.optional) continue;
      const type = interpolate(d.type, props) || 'jar';
      if (!FOLLOWED_TYPES.has(type)) continue;
      const key = `${interpolate(d.groupId, props)}:${interpolate(d.artifactId, props)}`;
      if (key.includes('${') || selected.has(key) || excluded(key, node.exclusions)) continue;
      const version = rootManaged(key)
        || (d.version ? interpolate(d.version, props) : maven.managedVersion(model, key, props));
      const why = badVersion(version);
      if (why) {
        if (!reported.has(key)) { reported.add(key); c.unresolve('Maven', key, file, why); }
        continue;
      }
      selected.add(key);
      c.add({ ecosystem: 'Maven', name: key, version, file, direct: false, via: node.via });
      queue.push({ key, version, depth: node.depth + 1, exclusions: node.exclusions.concat(d.exclusions || []), via: node.via });
    }
  }
  if (capped) {
    const limit = capped === 'depth' ? `depth ${MAX_TRANSITIVE_DEPTH}` : `${MAX_TRANSITIVE_FETCHES} POM downloads`;
    c.unresolve('Maven', '(transitive dependencies)', file, `transitive resolution stopped at the ${limit} limit; deeper dependencies were not checked`);
  }
}

function parsePomFile(c, maven, file) {
  const model = maven.local.get(file);
  if (!model) throw new Error('unparseable pom');
  const props = maven.effectiveProps(model);
  const roots = [];
  for (const dep of model.deps) {
    const groupId = interpolate(dep.groupId, props);
    const artifactId = interpolate(dep.artifactId, props);
    if (!groupId || !artifactId) continue;
    const name = `${groupId}:${artifactId}`;
    if (maven.localByCoords.has(name)) continue; // another module of this repository
    const version = dep.version ? interpolate(dep.version, props) : maven.managedVersion(model, name, props);
    if (!version) {
      const why = maven.state.fetchFailed
        ? 'version managed by a parent or BOM that could not be fetched'
        : 'version not found in dependencyManagement, parent, or imported BOMs';
      c.unresolve('Maven', name, file, why);
    } else if (version.includes('${')) {
      c.unresolve('Maven', name, file, `unresolved property in version (${version})`);
    } else if (/^[[(]/.test(version)) {
      c.unresolve('Maven', name, file, `version range (${version})`);
    } else {
      const scope = interpolate(dep.scope, props);
      const pkg = { ecosystem: 'Maven', name, version, file, direct: true };
      if (scope && scope !== 'compile') pkg.scope = scope;
      c.add(pkg);
      roots.push({ key: name, version, scope: scope || 'compile', exclusions: dep.exclusions });
    }
  }
  if (model.deps.length) resolveTransitive(c, maven, file, model, roots);
}

// ---------------------------------------------------------------- Gradle

function parseGradleLockfile(c, root, file) {
  for (const line of readFile(root, file).split(/\r?\n/)) {
    const m = line.match(/^([^#:\s]+):([^:\s]+):([^=\s]+)=/);
    if (m) c.add({ ecosystem: 'Maven', name: `${m[1]}:${m[2]}`, version: m[3], file, direct: false });
  }
}

function tomlSection(text, name) {
  const m = text.match(new RegExp(`^\\[${name}\\]\\s*$([\\s\\S]*?)(?=^\\[|(?![\\s\\S]))`, 'm'));
  return m ? m[1] : '';
}

function parseVersionCatalog(c, root, file) {
  const text = readFile(root, file).replace(/(^|\s)#.*$/gm, '');
  const versions = {};
  for (const m of tomlSection(text, 'versions').matchAll(/^([\w.-]+)\s*=\s*(.+)$/gm)) {
    const value = m[2].trim();
    const plain = value.match(/^"([^"]+)"/);
    const rich = value.match(/(?:strictly|require|prefer)\s*=\s*"([^"]+)"/);
    if (plain) versions[m[1]] = plain[1];
    else if (rich) versions[m[1]] = rich[1];
  }
  for (const m of tomlSection(text, 'libraries').matchAll(/^([\w.-]+)\s*=\s*(.+)$/gm)) {
    const value = m[2].trim();
    let module = null;
    let version = null;
    const inline = value.match(/^"([^":]+):([^":]+)(?::([^"]+))?"/);
    if (inline) {
      module = `${inline[1]}:${inline[2]}`;
      version = inline[3] || null;
    } else {
      const mod = value.match(/module\s*=\s*"([^"]+)"/);
      const group = value.match(/group\s*=\s*"([^"]+)"/);
      const artifact = value.match(/\bname\s*=\s*"([^"]+)"/);
      module = mod ? mod[1] : group && artifact ? `${group[1]}:${artifact[1]}` : null;
      const ref = value.match(/version\.ref\s*=\s*"([^"]+)"|version\s*=\s*\{\s*ref\s*=\s*"([^"]+)"/);
      const lit = value.match(/version\s*=\s*"([^"]+)"/);
      version = ref ? versions[ref[1] || ref[2]] || null : lit ? lit[1] : null;
    }
    if (!module) continue;
    if (version && /^\d/.test(version) && !/[[(+]/.test(version)) {
      c.add({ ecosystem: 'Maven', name: module, version, file, direct: true });
    } else {
      c.unresolve('Maven', module, file, version ? `version range or dynamic version (${version})` : 'version managed by the Gradle plugin/BOM; needs a lockfile');
    }
  }
}

const GRADLE_DECL = /\b(implementation|api|compileOnly|runtimeOnly|testImplementation|testCompileOnly|testRuntimeOnly|annotationProcessor|kapt|ksp|compile|testCompile|developmentOnly|classpath)\s*\(?\s*["']([^"':\s]+):([^"':\s]+)(?::([^"'\s@]+))?(?:@\w+)?["']/g;

// Configurations whose dependencies end up on the runtime classpath, so their transitives are followed.
const GRADLE_RUNTIME_CONFIGS = new Set(['implementation', 'api', 'runtimeOnly', 'compile']);

// String variables a build can use in versions: ext / extra / val / def assignments and gradle.properties.
function gradleVars(root, file, text) {
  const vars = {};
  for (const dir of ancestors(dirOf(file)).reverse()) {
    const props = readFile(root, joinPath(dir, 'gradle.properties'));
    if (!props) continue;
    for (const m of props.matchAll(/^\s*([\w.-]+)\s*[=:]\s*(\S[^\r\n]*?)\s*$/gm)) {
      if (!m[1].startsWith('#')) vars[m[1]] = m[2];
    }
  }
  const patterns = [
    /\bext\.([A-Za-z_]\w*)\s*=\s*["']([^"'$]+)["']/g,
    /\bext\[\s*["'](\w+)["']\s*\]\s*=\s*["']([^"'$]+)["']/g,
    /\bextra\[\s*"(\w+)"\s*\]\s*=\s*"([^"$]+)"/g,
    /\bval\s+([A-Za-z_]\w*)\s+by\s+extra\(\s*"([^"$]+)"\s*\)/g,
    /\bval\s+([A-Za-z_]\w*)\s*(?::\s*String)?\s*=\s*"([^"$]+)"/g,
    /\bdef\s+([A-Za-z_]\w*)\s*=\s*["']([^"'$]+)["']/g,
  ];
  for (const re of patterns) for (const m of text.matchAll(re)) vars[m[1]] = m[2];
  for (const block of text.matchAll(/\bext\s*\{([\s\S]*?)\}/g)) {
    for (const m of block[1].matchAll(/(?:^|\s)(?:set\(\s*)?["']?([A-Za-z_]\w*)["']?\s*[=,]\s*["']([^"'$]+)["']/g)) vars[m[1]] = m[2];
  }
  return vars;
}

function gradleInterpolate(value, vars) {
  if (value == null) return value;
  return value.replace(/\$\{([\w.]+)\}|\$([A-Za-z_]\w*)/g, (all, a, b) => (vars[a || b] != null ? vars[a || b] : all));
}

// BOMs that manage versions in a Gradle build: Spring's dependency-management plugin with the
// Spring Boot plugin (Boot's BOM), mavenBom imports, and platform()/enforcedPlatform().
function gradleBoms(text, vars) {
  const boms = [];
  const boot = text.match(/\bid\s*\(?\s*["']org\.springframework\.boot["']\s*\)?\s*version\s*\(?\s*["']([^"']+)["']/)
    || text.match(/["']org\.springframework\.boot:spring-boot-gradle-plugin:([^"'\s]+)["']/);
  const depMgmt = /io\.spring\.dependency-management/.test(text);
  if (boot && depMgmt) boms.push(['org.springframework.boot', 'spring-boot-dependencies', gradleInterpolate(boot[1], vars)]);
  for (const m of text.matchAll(/\bmavenBom\s*\(?\s*["']([^"':\s]+):([^"':\s]+):([^"'\s]+)["']/g)) boms.push([m[1], m[2], gradleInterpolate(m[3], vars)]);
  for (const m of text.matchAll(/\b(?:enforcedPlatform|platform)\s*\(\s*["']([^"':\s]+):([^"':\s]+):([^"'\s]+)["']\s*\)/g)) boms.push([m[1], m[2], gradleInterpolate(m[3], vars)]);
  return boms;
}

function parseGradleBuild(c, root, file, maven) {
  const text = readFile(root, file).replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
  const vars = gradleVars(root, file, text);
  const boms = gradleBoms(text, vars);
  // A synthetic root project whose dependencyManagement imports the build's BOMs.
  const rootModel = {
    groupId: null, artifactId: null, version: null, parent: null, props: {}, deps: [],
    managed: boms.map(([groupId, artifactId, version]) => ({ groupId, artifactId, version, scope: 'import', type: 'pom' })),
  };
  const roots = [];
  for (const m of text.matchAll(GRADLE_DECL)) {
    const config = m[1];
    const name = `${m[2]}:${m[3]}`;
    let version = m[4] ? gradleInterpolate(m[4], vars) : null;
    if (!version && boms.length && maven) version = maven.managedVersion(rootModel, name, maven.effectiveProps(rootModel));
    if (!version) {
      c.unresolve('Maven', name, file, boms.length ? 'version not managed by the imported BOMs' : 'version managed by the Gradle plugin/BOM; needs a lockfile');
    } else if (version.includes('$')) {
      c.unresolve('Maven', name, file, `version from a variable that isn't defined in the build (${version})`);
    } else if (/[[(+]/.test(version) || version.includes('latest.')) {
      c.unresolve('Maven', name, file, `dynamic version (${version})`);
    } else {
      const pkg = { ecosystem: 'Maven', name, version, file, direct: true };
      if (!GRADLE_RUNTIME_CONFIGS.has(config) && config !== 'classpath') pkg.scope = config;
      c.add(pkg);
      if (GRADLE_RUNTIME_CONFIGS.has(config)) roots.push({ key: name, version, scope: 'compile', exclusions: [] });
    }
  }
  if (roots.length && maven) resolveTransitive(c, maven, file, rootModel, roots);
}

// ---------------------------------------------------------------- entry point

function sortAndDedupe(list, keyFn) {
  const map = new Map();
  for (const item of list) {
    const key = keyFn(item);
    const prev = map.get(key);
    if (!prev) map.set(key, item);
    else if (item.direct && !prev.direct) prev.direct = true;
  }
  return [...map.values()].sort((a, b) => (keyFn(a) < keyFn(b) ? -1 : keyFn(a) > keyFn(b) ? 1 : 0));
}

function parseLockfiles(root, fileList, opts = {}) {
  const c = createCollector();
  const files = fileList.map((f) => f.replace(/\\/g, '/')).filter((f) => !SKIP_DIRS.test(`/${f}`)).sort();
  const fileSet = new Set(files);
  const npmLockDirs = new Set();
  const nugetLockDirs = new Set();
  let gradleLockfiles = 0;
  for (const f of files) {
    const b = baseOf(f);
    if (['package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml'].includes(b)) npmLockDirs.add(dirOf(f));
    if (b === 'packages.lock.json') nugetLockDirs.add(dirOf(f));
    if (b === 'gradle.lockfile' || /\/dependency-locks\/[^/]+\.lockfile$/.test(f)) gradleLockfiles++;
  }
  const maven = files.some((f) => baseOf(f) === 'pom.xml' || /^build\.gradle(\.kts)?$/.test(baseOf(f)))
    ? createMavenResolver(root, files, opts)
    : null;

  for (const file of files) {
    const b = baseOf(file);
    if (b === 'package-lock.json' || b === 'npm-shrinkwrap.json') parseWith(c, file, 'npm', 'package-lock', () => parsePackageLock(c, root, file));
    else if (b === 'yarn.lock') parseWith(c, file, 'npm', 'yarn.lock', () => parseYarnLock(c, root, file));
    else if (b === 'pnpm-lock.yaml') parseWith(c, file, 'npm', 'pnpm-lock', () => parsePnpmLock(c, root, file));
    else if (b === 'poetry.lock' || b === 'uv.lock') parseWith(c, file, 'PyPI', b, () => parsePoetryOrUvLock(c, root, file));
    else if (b === 'Pipfile.lock') parseWith(c, file, 'PyPI', 'Pipfile.lock', () => parsePipfileLock(c, root, file));
    else if (/^requirements.*\.txt$/.test(b)) parseWith(c, file, 'PyPI', 'requirements', () => parseRequirements(c, root, file));
    else if (b === 'Cargo.lock') parseWith(c, file, 'crates.io', 'Cargo.lock', () => parseCargoLock(c, root, file));
    else if (b === 'go.mod') parseWith(c, file, 'Go', 'go.mod', () => parseGoMod(c, root, file));
    else if (b === 'packages.lock.json') parseWith(c, file, 'NuGet', 'packages.lock.json', () => parseNugetLock(c, root, file));
    else if (/\.(cs|fs|vb)proj$/.test(b) && !nugetLockDirs.has(dirOf(file))) parseWith(c, file, 'NuGet', 'project file', () => parseProjectFile(c, root, file, fileSet));
    else if (b === 'Gemfile.lock') parseWith(c, file, 'RubyGems', 'Gemfile.lock', () => parseGemfileLock(c, root, file));
    else if (b === 'composer.lock') parseWith(c, file, 'Packagist', 'composer.lock', () => parseComposerLock(c, root, file));
    else if (b === 'pom.xml') parseWith(c, file, 'Maven', 'pom.xml', () => parsePomFile(c, maven, file));
    else if (b === 'gradle.lockfile' || /\/dependency-locks\/[^/]+\.lockfile$/.test(file)) parseWith(c, file, 'Maven', 'gradle.lockfile', () => parseGradleLockfile(c, root, file));
    else if (b === 'libs.versions.toml' && gradleLockfiles === 0) parseWith(c, file, 'Maven', 'version catalog', () => parseVersionCatalog(c, root, file));
    else if (/^build\.gradle(\.kts)?$/.test(b) && gradleLockfiles === 0) {
      parseWith(c, file, 'Maven', 'build.gradle', () => parseGradleBuild(c, root, file, maven));
    }
  }
  checkNpmWithoutLockfile(c, root, files, npmLockDirs);

  const pkgKey = (p) => `${p.ecosystem}\u0000${p.name}\u0000${p.version}\u0000${p.file}`;
  const unresKey = (u) => `${u.ecosystem}\u0000${u.name}\u0000${u.file}\u0000${u.reason}`;
  return {
    packages: sortAndDedupe(c.packages, pkgKey),
    unresolved: sortAndDedupe(c.unresolved, unresKey),
    sources: c.sources.sort((a, b) => (a.file < b.file ? -1 : a.file > b.file ? 1 : 0)),
  };
}

module.exports = { parseLockfiles, parsePom, interpolate, normalizePypi };
