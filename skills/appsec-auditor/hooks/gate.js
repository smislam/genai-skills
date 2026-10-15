#!/usr/bin/env node
// appsec-auditor coverage gate: a Claude Code Stop hook.
// While an audit is running, Claude can't finish until scripts/coverage-check.js reports the
// audit complete: every checklist item decided, every entry-point file read, report and SARIF
// written. To wait for the user mid-audit, the skill sets .appsec-audit/state.json to
// {"status": "paused"}; the gate then lets the turn end. Claude Code's own cap on consecutive
// stop-hook continuations prevents an endless loop. Node.js 18+, standard library only.

'use strict';

const fs = require('fs');
const path = require('path');
const { activeAuditDirs, MARKER_MAX_AGE_MS, readInput } = require('./common');

function state(auditDir) {
  try {
    const s = JSON.parse(fs.readFileSync(path.join(auditDir, 'state.json'), 'utf8'));
    const age = Date.now() - Date.parse(s.updatedAt || 0);
    return { status: s.status, fresh: age >= 0 && age <= MARKER_MAX_AGE_MS };
  } catch {
    return { status: 'running', fresh: true };
  }
}

function main() {
  const input = readInput();
  if (!input) return;
  // Work still running in the background (for example, the audit itself in a subagent) will
  // wake the session when it finishes, so ending this turn isn't finishing the audit.
  if (Array.isArray(input.background_tasks) && input.background_tasks.length) return;
  const { check } = require(path.join(__dirname, '..', 'scripts', 'coverage-check.js'));
  const blocking = [];
  for (const auditDir of activeAuditDirs(input)) {
    const s = state(auditDir);
    if (s.status === 'paused' && s.fresh) continue;
    const result = check(path.dirname(auditDir));
    if (result.complete) continue;
    const lines = result.gaps.slice(0, 12).map((g) => `- [${g.type}] ${g.message}${g.sample.length ? ` e.g. ${g.sample.slice(0, 3).join('; ')}` : ''}`);
    blocking.push(`Audit of ${path.dirname(auditDir)} is not complete:\n${lines.join('\n')}`);
  }
  if (!blocking.length) return;
  process.stdout.write(JSON.stringify({
    decision: 'block',
    reason: `[appsec-auditor coverage gate] ${blocking.join('\n\n')}\n\nContinue the audit until \`node scripts/coverage-check.js\` reports complete. If you must stop to wait for the user, write .appsec-audit/state.json as {"status": "paused", "reason": "...", "updatedAt": "<ISO time>"} first, and set it back to "running" when you resume.`,
  }));
}

try {
  main();
} catch (e) {
  // Fail open on a bug in the gate itself, but say so.
  process.stderr.write(`appsec-auditor gate error: ${e.message}\n`);
}
process.exit(0);
