#!/usr/bin/env node
'use strict';
// The coverage gate. Compares the deterministic checklist (coverage.json from inventory.js,
// deps.json from deps.js) with the AI's decisions (ledger.json), the read log (reads.jsonl,
// written by the track hook), and the report. The audit is complete only when every
// checklist item has a valid decision, every entry-point file was read, and the report and
// SARIF exist and carry the current coverage summary.
//
// Usage: node coverage-check.js [--root <repo>] [--json] [--summary]
//   --summary  print the coverage block to paste into report.md (deterministic)

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const glob = require('./lib/glob');

const STATUSES = ['finding', 'false_positive', 'needs_review', 'reviewed', 'not_applicable'];
const KINDS = ['entrypoint', 'pattern', 'secret', 'secret-history', 'dependency'];

function readJSON(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

function samePath(a, b) {
  const n = (p) => { const f = path.resolve(p).replace(/\\/g, '/'); return process.platform === 'win32' ? f.toLowerCase() : f; };
  return n(a) === n(b);
}

// Validate one ledger entry; returns an error string or null.
function entryError(e) {
  if (!STATUSES.includes(e.status)) return `unknown status "${e.status}"`;
  if (e.status === 'finding' && !/^(F|C)-\d+$/.test(e.finding || '')) return 'a "finding" decision needs a finding ID like F-03 or C-1';
  if (e.status !== 'finding' && String(e.reason || '').trim().length < 10) return `a "${e.status}" decision needs a reason of at least 10 characters`;
  if (e.match) {
    if (e.status === 'finding') return 'group entries ("match") cannot be findings; record each finding by item ID';
    if (e.match.kind === 'entrypoint') return 'entry points must each be decided by ID, not by a group entry';
    if (!e.match.rule && !e.match.kind && !e.match.path) return 'a group entry needs at least one of match.rule, match.kind, match.path';
  } else if (!e.id) {
    return 'an entry needs an "id" or a "match"';
  }
  return null;
}

function groupMatches(e, item) {
  const m = e.match;
  if (item.kind === 'entrypoint') return false;
  if (m.rule && m.rule !== item.rule) return false;
  if (m.kind && m.kind !== item.kind) return false;
  if (m.path && !(glob.matches(item.file || '', m.path) || String(item.file || '').startsWith(m.path))) return false;
  return true;
}

function check(root) {
  const auditDir = path.join(root, '.appsec-audit');
  const gaps = [];
  const gap = (type, message, sample = [], count = sample.length || 1) => gaps.push({ type, message, count, sample: sample.slice(0, 10) });

  const coverage = readJSON(path.join(auditDir, 'coverage.json'));
  if (!coverage) {
    gap('inventory', 'No coverage.json. Run inventory.js first; it builds the checklist.');
    return { complete: false, gaps, summary: '', fingerprint: '', undecidedIds: [] };
  }
  const head = spawnSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' });
  if (head.status === 0 && coverage.commit && coverage.commit !== 'none' && head.stdout.trim() !== coverage.commit) {
    gap('stale', `coverage.json was built for commit ${coverage.commit.slice(0, 12)}, but HEAD is ${head.stdout.trim().slice(0, 12)}. Re-run inventory.js.`);
  }

  const deps = readJSON(path.join(auditDir, 'deps.json'));
  if ((coverage.packages || []).length && !deps) gap('deps', 'No deps.json. Run deps.js to check dependencies against OSV.dev and KEV.');

  const items = (coverage.items || []).concat(deps ? deps.items || [] : []);
  const ledger = readJSON(path.join(auditDir, 'ledger.json')) || { entries: [] };
  const entries = Array.isArray(ledger.entries) ? ledger.entries : [];

  const invalid = [];
  const byId = new Map();
  const groups = [];
  entries.forEach((e, i) => {
    const err = entryError(e || {});
    if (err) { invalid.push(`entry ${i}${e && e.id ? ` (${e.id})` : ''}: ${err}`); return; }
    if (e.match) groups.push(e); else byId.set(e.id, e);
  });
  if (invalid.length) gap('ledger-invalid', `${invalid.length} ledger entries are invalid.`, invalid, invalid.length);

  const known = new Set(items.map((it) => it.id));
  const unknownIds = [...byId.keys()].filter((id) => !known.has(id));
  if (unknownIds.length) gap('ledger-unknown', `${unknownIds.length} ledger entries refer to IDs not in the current checklist (stale or mistyped).`, unknownIds, unknownIds.length);

  // Decide each item: an ID entry wins over a group entry.
  const decision = new Map();
  for (const it of items) {
    const e = byId.get(it.id) || groups.find((g) => groupMatches(g, it));
    if (e) decision.set(it.id, e);
  }
  const undecided = items.filter((it) => !decision.has(it.id));
  if (undecided.length) {
    gap('undecided', `${undecided.length} checklist items have no decision in ledger.json.`, undecided.map((it) => `${it.id} ${it.kind} ${it.rule || it.vuln || ''} ${it.file || ''}${it.line ? ':' + it.line : ''}`.trim()), undecided.length);
  }

  // Every entry-point file must have been read with the Read tool.
  const reads = [];
  try {
    for (const line of fs.readFileSync(path.join(auditDir, 'reads.jsonl'), 'utf8').split('\n')) {
      if (line.trim()) reads.push(JSON.parse(line).path);
    }
  } catch {
    // no reads yet
  }
  const entryFiles = [...new Set(items.filter((it) => it.kind === 'entrypoint').map((it) => it.file))].sort();
  const unread = entryFiles.filter((f) => !reads.some((r) => samePath(r, path.join(root, f))));
  if (unread.length) gap('unread', `${unread.length} entry-point files were never opened with the Read tool.`, unread, unread.length);

  // Dependency lookups: a failure must be disclosed, not hidden.
  const reportPath = path.join(auditDir, 'report.md');
  const report = fs.existsSync(reportPath) ? fs.readFileSync(reportPath, 'utf8') : null;
  if (deps && deps.status === 'failed' && report && !/not checked/i.test(report)) {
    gap('deps-failed', 'deps.js could not reach OSV.dev, but report.md doesn\'t say dependency results are "not checked".');
  }

  // Report and SARIF.
  const fingerprint = crypto.createHash('sha256')
    .update(items.map((it) => `${it.id}=${(decision.get(it.id) || {}).status || '-'}`).sort().join('\n'))
    .update(String(coverage.commit) + String(coverage.rulesVersion))
    .digest('hex').slice(0, 16);
  const summary = renderSummary(coverage, deps, items, decision, entryFiles, unread, fingerprint);
  if (!report) {
    gap('report', 'No report.md yet.');
  } else {
    if (!report.includes(`<!-- appsec-coverage v1 fingerprint=${fingerprint} -->`)) {
      gap('summary', 'report.md doesn\'t contain the current coverage summary. Run coverage-check.js --summary and paste its output into the Coverage section (re-paste after any ledger change).');
    }
    const findingIds = [...new Set(entries.filter((e) => e && e.status === 'finding').map((e) => e.finding))].sort();
    const missing = findingIds.filter((f) => !new RegExp(`\\b${f}\\b`).test(report));
    if (missing.length) gap('report-findings', `${missing.length} finding IDs from the ledger don't appear in report.md.`, missing, missing.length);
  }
  // findings.json is the structured source for the SARIF; sarif.js renders it deterministically.
  const ledgerFindings = [...new Set(entries.filter((e) => e && e.status === 'finding').map((e) => e.finding))].sort();
  const findingsDoc = readJSON(path.join(auditDir, 'findings.json'));
  if (!findingsDoc) {
    gap('findings', 'No findings.json. Write it (format in references/output.md), then run sarif.js.');
  } else {
    const list = Array.isArray(findingsDoc.findings) ? findingsDoc.findings : [];
    const ids = new Set(list.map((f) => f && f.id));
    const missing = ledgerFindings.filter((f) => !ids.has(f));
    if (missing.length) gap('findings', `${missing.length} finding IDs used in the ledger are missing from findings.json.`, missing, missing.length);
    const bad = list.filter((f) => !f || !/^(F|C)-\d+$/.test(f.id || '') || !f.title || !['Critical', 'High', 'Medium', 'Low', 'Info'].includes(f.severity) || !['Confirmed', 'Likely'].includes(f.confidence) || !Array.isArray(f.locations) || !f.locations.length);
    if (bad.length) gap('findings', `${bad.length} entries in findings.json lack id, title, severity, confidence (Confirmed or Likely), or a location.`, bad.map((f) => (f && f.id) || '?'), bad.length);
  }
  const sarif = readJSON(path.join(auditDir, 'results.sarif'));
  if (!sarif) {
    gap('sarif', 'No valid results.sarif yet. Run sarif.js.');
  } else if (findingsDoc) {
    let expected = null;
    try { expected = require('./sarif').render(root); } catch { /* reported above */ }
    if (expected && JSON.stringify(expected) !== JSON.stringify(sarif)) gap('sarif', 'results.sarif doesn\'t match findings.json. Re-run sarif.js; don\'t edit the SARIF by hand.');
  }

  return { complete: gaps.length === 0, gaps, summary, fingerprint, undecidedIds: undecided.map((it) => it.id) };
}

function renderSummary(coverage, deps, items, decision, entryFiles, unread, fingerprint) {
  const count = (kind, status) => items.filter((it) => it.kind === kind && (status === undefined || (status === null ? !decision.has(it.id) : (decision.get(it.id) || {}).status === status))).length;
  const rows = KINDS.map((k) => {
    const n = count(k);
    if (!n) return null;
    return `| ${k} | ${n} | ${count(k, 'finding')} | ${count(k, 'false_positive')} | ${count(k, 'needs_review')} | ${count(k, 'reviewed')} | ${count(k, 'not_applicable')} | ${count(k, null)} |`;
  }).filter(Boolean);
  const d = deps || {};
  const lines = [
    `<!-- appsec-coverage v1 fingerprint=${fingerprint} -->`,
    `**Checklist:** commit \`${String(coverage.commit).slice(0, 12)}\` · rules ${coverage.rulesVersion} · depth ${coverage.depth} · ${coverage.files ? coverage.files.count : 0} files scanned · ${(coverage.packages || []).length} packages (${(coverage.unresolved || []).length} not resolvable)`,
    '',
    '| Checklist | Items | Findings | False positives | Needs review | Reviewed | Not applicable | Undecided |',
    '|---|---|---|---|---|---|---|---|',
    ...rows,
    '',
    `**Entry-point files read:** ${entryFiles.length - unread.length} of ${entryFiles.length}`,
    `**Dependency data:** OSV.dev ${d.osv && d.osv.ok ? 'queried' : '**not checked**'}; KEV ${d.kev && d.kev.ok ? `catalog ${d.kev.catalogVersion}` : '**unknown**'}; EPSS ${d.epss && d.epss.ok ? 'scored' : '**not scored**'}`,
    '<!-- /appsec-coverage -->',
  ];
  return lines.join('\n');
}

module.exports = { check };

if (require.main === module) {
  const i = process.argv.indexOf('--root');
  const root = path.resolve(i >= 0 ? process.argv[i + 1] : process.cwd());
  const result = check(root);
  if (process.argv.includes('--list')) {
    // Compact checklist view: node coverage-check.js --list [--undecided] [--kind <kind>]
    const auditDir = path.join(root, '.appsec-audit');
    const items = ((readJSON(path.join(auditDir, 'coverage.json')) || {}).items || []).concat(((readJSON(path.join(auditDir, 'deps.json')) || {}).items) || []);
    const ki = process.argv.indexOf('--kind');
    const undecided = new Set(result.undecidedIds);
    for (const it of items) {
      if (ki >= 0 && it.kind !== process.argv[ki + 1]) continue;
      if (process.argv.includes('--undecided') && !undecided.has(it.id)) continue;
      const where = it.file ? `${it.file}${it.line ? ':' + it.line : ''}` : '';
      const what = it.kind === 'dependency' ? `${it.package}@${it.version} ${it.vuln} ${(it.cves || []).join(',')} ${it.severity || ''}` : `${it.rule} | ${it.excerpt || ''}`;
      console.log(`${it.id}  ${it.kind.padEnd(14)} ${where}  ${what}`.slice(0, 240));
    }
    process.exit(0);
  }
  if (process.argv.includes('--summary')) {
    process.stdout.write(result.summary + '\n');
  } else if (process.argv.includes('--json')) {
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } else {
    console.log(result.complete ? 'Coverage complete.' : `Coverage INCOMPLETE: ${result.gaps.length} gap types.`);
    for (const g of result.gaps) {
      console.log(`- [${g.type}] ${g.message}`);
      for (const s of g.sample) console.log(`    ${s}`);
      if (g.sample.length && g.count > g.sample.length) console.log(`    … and ${g.count - g.sample.length} more`);
    }
  }
}
