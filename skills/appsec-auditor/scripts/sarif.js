#!/usr/bin/env node
'use strict';
// Render .appsec-audit/results.sarif (SARIF 2.1.0) from .appsec-audit/findings.json, so the
// SARIF is deterministic: same findings => byte-identical file. Usage: node sarif.js [--root <repo>]
// findings.json format: references/output.md, "findings.json".

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const SEVERITY_SCORE = { Critical: '9.5', High: '8.0', Medium: '5.5', Low: '2.0', Info: '0.5' };
const LEVEL = { Critical: 'error', High: 'error', Medium: 'warning', Low: 'note', Info: 'note' };
const PRECISION = { Confirmed: 'high', Likely: 'medium' };

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
}

// Fingerprint the normalized source line at a location, so the result survives line shifts.
function lineHash(root, loc) {
  let content = '';
  try {
    content = fs.readFileSync(path.join(root, loc.file), 'utf8').split(/\r?\n/)[(loc.line || 1) - 1] || '';
  } catch {
    // file not in the tree (for example a history-only secret)
  }
  return crypto.createHash('sha256').update(`${loc.file}|${content.trim().replace(/\s+/g, ' ')}`).digest('hex').slice(0, 32);
}

function physical(loc) {
  const region = { startLine: loc.line || 1 };
  if (loc.endLine) region.endLine = loc.endLine;
  return { physicalLocation: { artifactLocation: { uri: loc.file.replace(/\\/g, '/'), uriBaseId: '%SRCROOT%' }, region } };
}

function render(root) {
  const auditDir = path.join(root, '.appsec-audit');
  const findings = JSON.parse(fs.readFileSync(path.join(auditDir, 'findings.json'), 'utf8')).findings || [];
  let coverage = {};
  try { coverage = JSON.parse(fs.readFileSync(path.join(auditDir, 'coverage.json'), 'utf8')); } catch { /* optional */ }
  const plugin = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '.claude-plugin', 'plugin.json'), 'utf8'));

  const sorted = [...findings].filter((f) => f.severity !== 'Info' || f.sarif !== false).sort((a, b) => a.id.localeCompare(b.id, 'en', { numeric: true }));
  const rules = [];
  const ruleIndex = new Map();
  const results = sorted.map((f) => {
    const ruleId = f.ruleId || `appsec/${slug(f.cwe || 'cwe-unknown')}-${slug(f.title)}`;
    if (!ruleIndex.has(ruleId)) {
      ruleIndex.set(ruleId, rules.length);
      const tags = ['security'];
      if (f.cwe) tags.push(`external/cwe/${f.cwe.toLowerCase()}`);
      if (f.owasp) tags.push(`owasp-top10-2025/${f.owasp.split(':')[0]}`);
      rules.push({
        id: ruleId,
        shortDescription: { text: f.title },
        fullDescription: { text: f.message || f.title },
        help: { text: f.fix || '', markdown: f.fix || '' },
        properties: { 'security-severity': f.cvssScore ? String(f.cvssScore) : SEVERITY_SCORE[f.severity] || '5.5', precision: PRECISION[f.confidence] || 'medium', tags },
      });
    }
    const locs = (f.locations || []).filter((l) => l && l.file);
    const result = {
      ruleId,
      ruleIndex: ruleIndex.get(ruleId),
      level: LEVEL[f.severity] || 'warning',
      message: { text: f.message || f.title },
      locations: locs.slice(0, 1).map(physical),
      partialFingerprints: { 'primaryLocationLineHash/v1': locs.length ? lineHash(root, locs[0]) : crypto.createHash('sha256').update(f.id + f.title).digest('hex').slice(0, 32) },
      properties: { findingId: f.id, severity: f.severity, confidence: f.confidence },
    };
    if (locs.length > 1) result.relatedLocations = locs.slice(1).map((l, i) => ({ id: i + 1, ...physical(l) }));
    if (Array.isArray(f.path) && f.path.length) {
      result.codeFlows = [{ threadFlows: [{ locations: f.path.filter((p) => p.file).map((p) => ({ location: { ...physical(p), message: { text: p.note || '' } } })) }] }];
    }
    if (f.cvss) result.properties.cvssVector = f.cvss;
    if (Array.isArray(f.chain) && f.chain.length) result.properties.chainMembers = f.chain;
    return result;
  });

  return {
    version: '2.1.0',
    $schema: 'https://json.schemastore.org/sarif-2.1.0.json',
    runs: [{
      tool: { driver: { name: 'appsec-auditor', version: plugin.version, informationUri: 'https://github.com/smislam/genai-skills', rules } },
      versionControlProvenance: coverage.commit && coverage.commit !== 'none' ? [{ repositoryUri: 'file:///' + root.replace(/\\/g, '/').replace(/^\//, ''), revisionId: coverage.commit }] : undefined,
      properties: { rulesVersion: coverage.rulesVersion, depth: coverage.depth },
      results,
    }],
  };
}

module.exports = { render };

if (require.main === module) {
  const root = path.resolve(arg('--root', process.cwd()));
  const sarif = render(root);
  fs.writeFileSync(path.join(root, '.appsec-audit', 'results.sarif'), JSON.stringify(sarif, null, 2) + '\n');
  console.log(`results.sarif: ${sarif.runs[0].results.length} results, ${sarif.runs[0].tool.driver.rules.length} rules`);
}
