'use strict';
// Shared by the appsec-auditor hooks: finding the active audit, comparing paths, reading hook input.

const fs = require('fs');
const path = require('path');

const AUDIT_DIR = '.appsec-audit';

// A marker older than this is treated as left over from an interrupted audit.
const MARKER_MAX_AGE_MS = 24 * 60 * 60 * 1000;

// The audit directory sits at the repository root, which may be above the session's
// project directory or cwd (for example, a session started in a subfolder). Walk up
// from both and collect every directory with a fresh marker.
function activeAuditDirs(input) {
  const found = new Set();
  for (const start of [process.env.CLAUDE_PROJECT_DIR, input.cwd].filter(Boolean)) {
    let dir = path.resolve(start);
    for (;;) {
      const marker = path.join(dir, AUDIT_DIR, '.active');
      try {
        const age = Date.now() - fs.statSync(marker).mtimeMs;
        if (age <= MARKER_MAX_AGE_MS) {
          // An empty marker means "this repository is being audited". A marker that lists
          // absolute paths only points to audits elsewhere, and isn't an audit itself.
          const targets = fs.readFileSync(marker, 'utf8').split(/\r?\n/).map((l) => l.trim()).filter((l) => l && path.isAbsolute(l));
          if (targets.length) for (const t of targets) found.add(path.join(t, AUDIT_DIR));
          else found.add(path.join(dir, AUDIT_DIR));
        }
      } catch {
        // no marker here
      }
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return [...found];
}

// Windows paths arrive with backslashes and are case-insensitive; elsewhere, compare exactly.
function normalizePath(p) {
  const forward = String(p).replace(/\\/g, '/');
  return process.platform === 'win32' ? forward.toLowerCase() : forward;
}

function isUnder(filePath, dir) {
  const f = normalizePath(filePath);
  const d = normalizePath(dir).replace(/\/+$/, '');
  return f === d || f.startsWith(d + '/');
}

function readInput() {
  try {
    return JSON.parse(fs.readFileSync(0, 'utf8'));
  } catch {
    return null;
  }
}

module.exports = { AUDIT_DIR, MARKER_MAX_AGE_MS, activeAuditDirs, normalizePath, isUnder, readInput };
