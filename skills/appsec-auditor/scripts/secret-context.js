#!/usr/bin/env node
'use strict';
// Show the context of a secret checklist item with every secret value redacted, so judging it
// never prints the secret into the conversation (SKILL.md rule 7).
// Usage: node secret-context.js --root <repo> --id <C-… or H-… item ID> [--lines 4]

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const root = path.resolve(arg('--root', process.cwd()));
const id = arg('--id');
const around = Number(arg('--lines', '4'));
const coverage = JSON.parse(fs.readFileSync(path.join(root, '.appsec-audit', 'coverage.json'), 'utf8'));
const item = (coverage.items || []).find((it) => it.id === id);
if (!item || !['secret', 'secret-history'].includes(item.kind)) {
  console.error(`No secret item with ID ${id}.`);
  process.exit(1);
}

const rules = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'rules', 'rules.json'), 'utf8')).rules
  .filter((r) => r.kind === 'secret')
  .map((r) => new RegExp(r.pattern, (r.flags || '').replace(/g/g, '') + 'g'));

// Diff lines start with "+", "-", or " "; the rules are anchored to the content, so strip it first.
function redact(line) {
  const marker = /^[+\- ]/.test(line) && !/^(\+\+\+|---) /.test(line) ? line[0] : '';
  let out = marker ? line.slice(1) : line;
  for (const re of rules) out = out.replace(re, (m) => `${m.slice(0, 4)}****`);
  return marker + out;
}

let lines;
let start = 1;
if (item.kind === 'secret') {
  const text = fs.readFileSync(path.join(root, item.file), 'utf8').split(/\r?\n/);
  start = Math.max(1, item.line - around);
  lines = text.slice(start - 1, item.line + around);
} else {
  const show = spawnSync('git', ['-C', root, 'show', '--no-color', '--format=commit %H%nDate: %ad%n%n    %s', '--date=short', item.commit, '--', item.file], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  lines = show.stdout.split('\n');
}

console.log(`${item.id} ${item.kind} ${item.rule} ${item.file}${item.line ? ':' + item.line : ''}${item.commit ? ' @ ' + item.commit.slice(0, 12) : ''}`);
lines.forEach((l, i) => console.log(item.kind === 'secret' ? `${String(start + i).padStart(5)}  ${redact(l)}` : redact(l)));
