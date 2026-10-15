#!/usr/bin/env node
'use strict';
// Build the deterministic audit checklist: .appsec-audit/coverage.json.
// Same commit + same rules + same depth => the same checklist, every time.
//   - files: tracked and untracked-but-not-ignored files (git), minus fixed exclusions
//   - items: every rule hit (patterns, entry points, secrets) with a stable ID
//   - secret-history items (Standard and Deep): secrets added anywhere in git history
//   - packages: parsed from lockfiles and manifests (lib/lockfiles.js)
// Usage: node inventory.js [--root <repo>] [--depth quick|standard|deep]

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const glob = require('./lib/glob');
const lockfiles = require('./lib/lockfiles');
const net = require('./lib/net');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const root = path.resolve(arg('--root', process.cwd()));
const depth = arg('--depth', 'standard').toLowerCase();
if (!['quick', 'standard', 'deep'].includes(depth)) throw new Error(`unknown depth: ${depth}`);
const auditDir = path.join(root, '.appsec-audit');
const rulesFile = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'rules', 'rules.json'), 'utf8'));

// Fixed exclusions, so every run scans the same set. Vendored code is still parsed for packages.
const EXCLUDE = [
  '.appsec-audit/**', '.git/**', '**/node_modules/**', '**/vendor/**', '**/dist/**', '**/build/**', '**/target/**',
  '**/out/**', '**/.next/**', '**/.nuxt/**', '**/coverage/**', '**/__pycache__/**', '**/.venv/**', '**/venv/**',
  '**/.terraform/**', '**/cdk.out/**', '**/bin/Debug/**', '**/bin/Release/**', '**/obj/**',
  '**/*.min.js', '**/*.min.css', '**/*.map',
];
const BINARY = /\.(png|jpe?g|gif|bmp|ico|webp|svgz|pdf|zip|gz|tgz|bz2|xz|7z|rar|jar|war|ear|class|dll|exe|so|dylib|a|o|bin|woff2?|ttf|otf|eot|mp[34]|mov|avi|wav|ogg|psd|sqlite|db|keystore|pyc)$/i;
const MAX_BYTES = 2 * 1024 * 1024;

function git(args) {
  return spawnSync('git', ['-C', root, ...args], { encoding: 'utf8', maxBuffer: 1024 * 1024 * 1024, windowsHide: true });
}

function sha1(s) {
  return crypto.createHash('sha1').update(s).digest('hex');
}

// Secret values never go into coverage.json: keep a hash and at most 4 characters.
function redactLine(line, re) {
  return line.replace(new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g'), (m) => `${m.slice(0, 4)}****`);
}

function listFiles() {
  const isGit = git(['rev-parse', '--is-inside-work-tree']).stdout.trim() === 'true';
  let files;
  if (isGit) {
    files = git(['ls-files', '-z', '--cached', '--others', '--exclude-standard']).stdout.split('\0').filter(Boolean);
  } else {
    files = [];
    const walk = (dir) => {
      for (const e of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
        const rel = dir ? `${dir}/${e.name}` : e.name;
        if (e.isDirectory()) { if (e.name !== '.git') walk(rel); } else if (e.isFile()) files.push(rel);
      }
    };
    walk('');
  }
  return { isGit, files: [...new Set(files.map((f) => f.replace(/\\/g, '/')))].sort() };
}

const STACK_SIGNS = [
  ['java', /\.java$|(^|\/)pom\.xml$|build\.gradle(\.kts)?$/], ['kotlin', /\.kts?$/], ['csharp', /\.(cs|csproj|cshtml|razor)$/],
  ['javascript', /\.(m?js|cjs|ts|tsx|jsx)$|(^|\/)package\.json$/], ['frontend', /\.(tsx|jsx|vue|svelte|html)$|(^|\/)angular\.json$/],
  ['python', /\.py$|(^|\/)(pyproject\.toml|requirements[^/]*\.txt)$/], ['go', /\.go$|(^|\/)go\.mod$/], ['rust', /\.rs$|(^|\/)Cargo\.toml$/],
  ['terraform', /\.tf$/], ['cdk', /(^|\/)cdk\.json$/], ['cloudformation', /\.(template|cfn)\.(json|ya?ml)$/],
  ['kubernetes', /(^|\/)(k8s|kubernetes|helm|charts|manifests)\/.*\.ya?ml$|(^|\/)Chart\.yaml$/],
  ['docker', /(^|\/)(Dockerfile[^/]*|[^/]*\.Dockerfile|docker-compose[^/]*\.ya?ml|compose\.ya?ml)$/],
  ['cicd', /(^|\/)(\.github\/workflows\/[^/]+\.ya?ml|\.gitlab-ci\.yml|Jenkinsfile|buildspec[^/]*\.ya?ml|azure-pipelines\.yml|bitbucket-pipelines\.yml)$/],
];

function main() {
  const { isGit, files: all } = listFiles();
  const commit = isGit ? (git(['rev-parse', 'HEAD']).stdout.trim() || 'none') : 'none';
  const dirty = isGit ? git(['status', '--porcelain']).stdout.split('\n').filter((l) => l && !l.includes('.appsec-audit/')).length : 0;

  const scanned = [];
  const skipped = [];
  for (const f of all) {
    if (glob.matchesAny(f, EXCLUDE)) continue;
    if (BINARY.test(f)) continue;
    let st;
    try { st = fs.statSync(path.join(root, f)); } catch { continue; }
    if (st.size > MAX_BYTES) { skipped.push({ file: f, reason: `larger than ${MAX_BYTES} bytes` }); continue; }
    scanned.push(f);
  }
  const stacks = STACK_SIGNS.filter(([, re]) => scanned.some((f) => re.test(f))).map(([s]) => s);

  const rules = rulesFile.rules.map((r) => ({ ...r, re: new RegExp(r.pattern, (r.flags || '').replace(/g/g, '')) }));

  const items = [];
  for (const f of scanned) {
    const applicable = rules.filter((r) => glob.matchesAny(f, r.include) && !glob.matchesAny(f, r.exclude || []));
    if (!applicable.length) continue;
    let text;
    try { text = fs.readFileSync(path.join(root, f), 'utf8'); } catch { continue; }
    if (text.includes('\0')) continue;
    const lines = text.split(/\r?\n/);
    for (const r of applicable) {
      const seen = new Map();
      const hits = [];
      if ((r.flags || '').includes('s')) {
        const g = new RegExp(r.re.source, r.re.flags + 'g');
        let m;
        while ((m = g.exec(text))) {
          hits.push(text.slice(0, m.index).split('\n').length);
          if (m[0].length === 0) g.lastIndex++;
        }
      } else {
        // An entry point mentioned in a comment or Javadoc isn't an entry point.
        const skipComments = r.kind === 'entrypoint';
        lines.forEach((line, i) => {
          if (skipComments && /^\s*(\/\/|\/\*|\*|#|<!--)/.test(line)) return;
          if (r.re.test(line)) hits.push(i + 1);
        });
      }
      for (const lineNo of [...new Set(hits)]) {
        const raw = lines[lineNo - 1] || '';
        const norm = raw.trim().replace(/\s+/g, ' ');
        // Stable across line shifts: rule + file + line content + occurrence among identical lines.
        const n = (seen.get(norm) || 0) + 1;
        seen.set(norm, n);
        const kind = r.kind === 'secret' ? 'secret' : r.kind;
        const excerpt = (kind === 'secret' ? redactLine(norm, r.re) : norm).slice(0, 200);
        items.push({ id: 'C-' + sha1([r.id, f, norm, n].join('|')).slice(0, 12), kind, rule: r.id, cwe: r.cwe || '', file: f, line: lineNo, excerpt, guide: r.guide || '' });
      }
    }
  }

  // Secrets in git history: lines added in any commit on any branch. Not at Quick depth.
  let history = { scanned: false };
  if (isGit && depth !== 'quick') {
    const secretRules = rules.filter((r) => r.kind === 'secret');
    const log = git(['log', '--all', '-p', '--no-color', '--no-ext-diff', '-U0', '--format=@@appsec-commit %H %ad', '--date=short']);
    const found = new Map();
    let commitSha = '';
    let date = '';
    let file = '';
    let fileRules = [];
    // Which secret rules apply depends only on the file, so decide once per file, not per line.
    const rulesFor = new Map();
    for (const line of log.stdout.split('\n')) {
      if (line.startsWith('@@appsec-commit ')) { [, commitSha, date] = line.split(' '); continue; }
      if (line.startsWith('+++ ')) {
        file = line.slice(4).replace(/^b\//, '');
        if (!rulesFor.has(file)) rulesFor.set(file, secretRules.filter((r) => glob.matchesAny(file, r.include) && !glob.matchesAny(file, r.exclude || [])));
        fileRules = rulesFor.get(file);
        continue;
      }
      if (!line.startsWith('+') || line.startsWith('+++') || !fileRules.length) continue;
      const added = line.slice(1);
      for (const r of fileRules) {
        const m = added.match(r.re);
        if (!m) continue;
        const key = `${r.id}|${file}|${sha1(m[0])}`;
        // git log lists newest first, so the last one seen is where the secret was introduced.
        found.set(key, { rule: r, file, commit: commitSha, date, excerpt: redactLine(added.trim().replace(/\s+/g, ' '), r.re).slice(0, 200), valueHash: sha1(m[0]).slice(0, 12) });
      }
    }
    for (const [key, h] of [...found.entries()].sort()) {
      items.push({ id: 'H-' + sha1(key).slice(0, 12), kind: 'secret-history', rule: h.rule.id, cwe: h.rule.cwe || 'CWE-798', file: h.file, commit: h.commit, date: h.date, excerpt: h.excerpt, valueHash: h.valueHash, fileStillExists: fs.existsSync(path.join(root, h.file)) });
    }
    history = { scanned: true, branches: 'all', commits: (log.stdout.match(/^@@appsec-commit /gm) || []).length };
  }

  items.sort((a, b) => (a.file || '').localeCompare(b.file || '') || (a.line || 0) - (b.line || 0) || a.rule.localeCompare(b.rule) || a.id.localeCompare(b.id));

  // Packages from lockfiles and manifests; Maven parent/BOM resolution through the network layer.
  const deps = lockfiles.parseLockfiles(root, all.filter((f) => !f.startsWith('.appsec-audit/')), { fetchText: net.getText, mavenBase: net.ENDPOINTS.maven });
  // A project with two build files (pom.xml and build.gradle) declares the same dependencies twice.
  // Don't report a dependency as unresolved when a sibling manifest in the same folder resolved it.
  const resolvedHere = new Set(deps.packages.map((p) => `${p.ecosystem}|${p.name}|${path.posix.dirname(p.file)}`));
  deps.unresolved = deps.unresolved.filter((u) => !resolvedHere.has(`${u.ecosystem}|${u.name}|${path.posix.dirname(u.file)}`));
  // The same package and version from two sibling build files is one package: keep the first
  // file (packages are sorted), and record the others, so one advisory makes one checklist item.
  const merged = new Map();
  for (const p of deps.packages) {
    const key = `${p.ecosystem}|${p.name}|${p.version}|${path.posix.dirname(p.file)}`;
    const kept = merged.get(key);
    if (!kept) { merged.set(key, { ...p }); continue; }
    kept.alsoIn = [...new Set([...(kept.alsoIn || []), p.file])].filter((f) => f !== kept.file).sort();
    kept.direct = kept.direct || p.direct;
  }
  deps.packages = [...merged.values()];

  const byKind = {};
  for (const it of items) byKind[it.kind] = (byKind[it.kind] || 0) + 1;
  const coverage = {
    schema: 1,
    tool: 'appsec-auditor',
    rulesVersion: rulesFile.version,
    root,
    commit,
    uncommittedChanges: dirty,
    depth,
    generatedAt: new Date().toISOString(),
    stacks,
    files: { count: scanned.length, skipped },
    history,
    counts: byKind,
    items,
    packages: deps.packages,
    unresolved: deps.unresolved,
    lockfileSources: deps.sources,
  };
  fs.mkdirSync(auditDir, { recursive: true });
  fs.writeFileSync(path.join(auditDir, 'coverage.json'), JSON.stringify(coverage, null, 2));
  fs.writeFileSync(path.join(auditDir, 'files.txt'), scanned.join('\n') + '\n');

  console.log(`commit=${commit.slice(0, 12)}${dirty ? ` (+${dirty} uncommitted changes)` : ''} depth=${depth} rules=${rulesFile.version} files=${scanned.length} stacks=${stacks.join(',') || '-'}`);
  console.log(`items=${items.length} ${Object.entries(byKind).map(([k, v]) => `${k}=${v}`).join(' ')}`);
  console.log(`packages=${deps.packages.length} unresolved=${deps.unresolved.length} manifests=${deps.sources.length}${history.scanned ? ` history_commits=${history.commits}` : ''}`);
  if (dirty) console.log('Note: the working tree has uncommitted changes, so the checklist reflects files on disk, not only the commit.');
}

main();
