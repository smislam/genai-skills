#!/usr/bin/env node
// appsec-auditor read tracker: a Claude Code PostToolUse hook for the Read tool.
// During an audit, records each file the AI reads in <audit dir>/reads.jsonl, so the
// coverage gate can check that every entry-point file was actually reviewed.
// Inert unless an audit is running. Node.js 18+, standard library only.

'use strict';

const fs = require('fs');
const path = require('path');
const { activeAuditDirs, isUnder, readInput } = require('./common');

function main() {
  const input = readInput();
  if (!input || input.tool_name !== 'Read') return;
  const filePath = (input.tool_input || {}).file_path;
  if (!filePath) return;
  const auditDirs = activeAuditDirs(input);
  // Log against the audit whose repository contains the file.
  const owners = auditDirs.filter((dir) => isUnder(filePath, path.dirname(dir)));
  const entry = JSON.stringify({
    path: path.resolve(filePath),
    offset: (input.tool_input || {}).offset || null,
    limit: (input.tool_input || {}).limit || null,
    at: new Date().toISOString(),
  }) + '\n';
  for (const dir of owners) {
    try {
      fs.appendFileSync(path.join(dir, 'reads.jsonl'), entry);
    } catch {
      // audit directory not created yet
    }
  }
}

main();
process.exit(0);
