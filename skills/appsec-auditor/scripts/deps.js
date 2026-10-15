#!/usr/bin/env node
'use strict';
// Check every package in .appsec-audit/coverage.json against live vulnerability data:
// OSV.dev (advisories), CISA KEV (known exploited), FIRST EPSS (exploit probability).
// Writes .appsec-audit/deps.json, including one checklist item per package vulnerability.
// Usage: node deps.js [--root <repo>]
// Sends only package names, versions, and CVE IDs (SKILL.md rule 4). Network settings: lib/net.js.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const net = require('./lib/net');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const root = path.resolve(arg('--root', process.cwd()));
const auditDir = path.join(root, '.appsec-audit');
const coverage = JSON.parse(fs.readFileSync(path.join(auditDir, 'coverage.json'), 'utf8'));
const packages = coverage.packages || [];
const now = new Date().toISOString();
const out = { schema: 1, generatedAt: now, commit: coverage.commit, status: 'ok', errors: [], osv: {}, kev: {}, epss: {}, packages: [], items: [] };

function fail(source, r) {
  out.errors.push({ source, category: r.category, hint: r.hint, status: r.status });
}

// 1. OSV batch query (up to 1000 queries per request), then each distinct advisory once.
const idsPerPkg = [];
let osvOk = true;
for (let start = 0; start < packages.length && osvOk; start += 1000) {
  const chunk = packages.slice(start, start + 1000);
  const queries = chunk.map((p) => ({ package: { ecosystem: p.ecosystem, name: p.name }, version: p.version }));
  const r = net.postJSON(`${net.ENDPOINTS.osv}/querybatch`, { queries });
  if (!r.ok) { fail('osv', r); osvOk = false; break; }
  r.data.results.forEach((res, i) => {
    let ids = (res.vulns || []).map((v) => v.id);
    let token = res.next_page_token;
    while (token) {
      const more = net.postJSON(`${net.ENDPOINTS.osv}/query`, { ...queries[i], page_token: token });
      if (!more.ok) { fail('osv', more); osvOk = false; break; }
      ids = ids.concat((more.data.vulns || []).map((v) => v.id));
      token = more.data.next_page_token;
    }
    idsPerPkg.push(ids);
  });
}
const details = {};
if (osvOk) {
  for (const id of [...new Set(idsPerPkg.flat())].sort()) {
    const r = net.getJSON(`${net.ENDPOINTS.osv}/vulns/${encodeURIComponent(id)}`);
    if (!r.ok) { fail('osv', r); osvOk = false; break; }
    details[id] = r.data;
  }
}
out.osv = { url: net.redactUrl(net.ENDPOINTS.osv), queriedAt: now, ok: osvOk, packagesQueried: osvOk ? packages.length : 0 };

// 2. CISA KEV, downloaded fresh.
let kevById = null;
{
  const r = net.getJSON(net.ENDPOINTS.kev);
  if (r.ok && Array.isArray(r.data.vulnerabilities)) {
    kevById = new Map(r.data.vulnerabilities.map((v) => [v.cveID, v]));
    out.kev = { ok: true, catalogVersion: r.data.catalogVersion, dateReleased: r.data.dateReleased, count: r.data.count };
    fs.mkdirSync(path.join(auditDir, 'data'), { recursive: true });
    fs.writeFileSync(path.join(auditDir, 'data', 'kev.json'), JSON.stringify(r.data));
  } else {
    fail('kev', r.ok ? { category: 'format', hint: 'Unexpected KEV catalog format.' } : r);
    out.kev = { ok: false };
  }
}

function fixedVersions(v, pkg) {
  const fixed = new Set();
  for (const a of v.affected || []) {
    if (!a.package || a.package.name !== pkg.name || a.package.ecosystem !== pkg.ecosystem) continue;
    for (const range of a.ranges || []) for (const e of range.events || []) if (e.fixed) fixed.add(e.fixed);
  }
  return [...fixed].sort();
}

// 3. Build the result and one checklist item per (package, advisory).
const allCves = new Set();
packages.forEach((pkg, i) => {
  const vulns = (idsPerPkg[i] || []).map((id) => {
    const v = details[id] || {};
    const db = v.database_specific || {};
    const cves = (v.aliases || []).concat(id.startsWith('CVE-') ? [id] : []).filter((a) => a.startsWith('CVE-'));
    cves.forEach((c) => allCves.add(c));
    const kev = kevById ? cves.map((c) => kevById.get(c)).filter(Boolean)[0] : undefined;
    return {
      id,
      cves: [...new Set(cves)].sort(),
      summary: v.summary || '',
      severity: db.severity || null,
      cvss: (v.severity || []).filter((s) => String(s.type).startsWith('CVSS')).map((s) => s.score),
      cwes: db.cwe_ids || [],
      fixed: fixedVersions(v, pkg),
      published: v.published || null,
      kev: kevById === null ? 'unknown' : kev ? { dateAdded: kev.dateAdded, dueDate: kev.dueDate, ransomware: kev.knownRansomwareCampaignUse } : null,
    };
  });
  out.packages.push({ ...pkg, vulns });
  for (const v of vulns) {
    const id = 'D-' + crypto.createHash('sha1').update([pkg.ecosystem, pkg.name, pkg.version, pkg.file, v.id].join('|')).digest('hex').slice(0, 12);
    out.items.push({ id, kind: 'dependency', ecosystem: pkg.ecosystem, package: pkg.name, version: pkg.version, file: pkg.file, direct: pkg.direct, vuln: v.id, cves: v.cves, severity: v.severity, kev: v.kev, fixed: v.fixed });
  }
});

// 4. EPSS for every CVE, in batches.
const cveList = [...allCves].sort();
const epss = {};
let epssOk = true;
for (let i = 0; i < cveList.length; i += 50) {
  const r = net.getJSON(`${net.ENDPOINTS.epss}?cve=${cveList.slice(i, i + 50).join(',')}`);
  if (!r.ok) { fail('epss', r); epssOk = false; break; }
  for (const row of r.data.data || []) epss[row.cve] = { epss: Number(row.epss), percentile: Number(row.percentile), date: row.date };
}
out.epss = { ok: epssOk, scores: epss };
for (const item of out.items) {
  const scores = item.cves.map((c) => epss[c]).filter(Boolean);
  item.epss = scores.length ? scores.sort((a, b) => b.epss - a.epss)[0] : null;
}

out.items.sort((a, b) => a.id.localeCompare(b.id));
if (!osvOk) out.status = 'failed';
else if (!out.kev.ok || !epssOk) out.status = 'partial';
fs.writeFileSync(path.join(auditDir, 'deps.json'), JSON.stringify(out, null, 2));

const vulnerable = out.packages.filter((p) => p.vulns.length);
const kevHits = out.items.filter((i) => i.kev && i.kev !== 'unknown');
console.log(`status=${out.status} packages=${packages.length} vulnerable_packages=${vulnerable.length} advisories=${Object.keys(details).length} items=${out.items.length} kev_matches=${kevHits.length}${out.kev.ok ? ` kev_catalog=${out.kev.catalogVersion}` : ''}`);
for (const e of out.errors) console.log(`ERROR ${e.source}: ${e.category}: ${e.hint}`);
if (out.status === 'failed') console.log('Dependency results are NOT CHECKED. Say so at the top of the report (SKILL.md rule 9). Run net-check.js to diagnose.');
