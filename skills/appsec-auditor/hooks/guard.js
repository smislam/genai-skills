#!/usr/bin/env node
// appsec-auditor guardrails: a Claude Code PreToolUse hook.
//
// Inert unless an audit is running, marked by .appsec-audit/.active at the
// repository root (created and removed by the skill; ignored after 24 hours).
// While active it enforces SKILL.md rules mechanically:
//   - rule 3: commands and scripts that execute project code need the user's approval ("ask")
//   - rule 6: piping a remote script into a shell is blocked ("deny")
//   - rule 4: secret verification or code-upload scanners need approval ("ask")
//   - rule 8: edits outside .appsec-audit/ need approval ("ask")
//   - rule 7: writing an unredacted secret into .appsec-audit/ is blocked ("deny")
// Uses only Node's standard library. Requires Node.js 18+.

'use strict';

const fs = require('fs');
const path = require('path');

const AUDIT_DIR = '.appsec-audit';

// Commands that run code from the repository or its dependencies.
const EXECUTES_PROJECT_CODE = [
  [/\b(npm|pnpm|yarn|bun)\s+(install|i|ci|add|run|run-script|test|exec|rebuild|start|build)\b/, 'installs packages or runs package scripts (lifecycle scripts execute dependency code)'],
  [/\bnpx\s+(?!--no-install\b)/, 'npx can download and run packages'],
  [/\b(mvn|mvnw|gradle|gradlew)(\.cmd|\.bat)?\b/, 'Maven and Gradle builds run project build logic and plugins'],
  [/\bdotnet\s+(build|restore|test|run|publish|pack|msbuild)\b/, '.NET restore and build run MSBuild logic from packages'],
  [/\bdotnet\s+(list\s+package|package\s+list)\b(?![^\n]*--no-restore)/, 'on .NET 10 this restores automatically, which runs MSBuild logic'],
  [/\bcargo\s+(build|test|run|check|clippy|bench|install|doc|update|fetch)\b/, 'cargo runs build.rs scripts and proc macros'],
  [/\bcargo\s+geiger\b(?![^\n]*--forbid-only)/, 'cargo-geiger builds the crate unless --forbid-only is set'],
  [/\b(cdk|npx\s+cdk)\s+(synth|deploy|diff|bootstrap|watch)\b/, 'cdk synth executes the CDK app'],
  [/\bterraform\s+(init|plan|apply|destroy|refresh|import|console)\b/, 'terraform downloads and runs provider binaries and may use cloud credentials'],
  [/\btofu\s+(init|plan|apply)\b/, 'OpenTofu downloads and runs provider binaries'],
  [/\btflint\s+--init\b/, 'tflint --init downloads plugin binaries'],
  [/\bpip3?\s+install\b|\bpython3?\s+-m\s+pip\s+install\b|\buv\s+(pip\s+install|sync|run)\b|\bpoetry\s+(install|run)\b|\bpipenv\s+(install|run)\b/, 'installing Python packages can run setup code'],
  [/\bpython3?\s+(setup\.py|manage\.py)\b/, 'runs project Python code'],
  [/\b(pytest|tox|nox)\b/, 'runs the project test suite'],
  [/\bgo\s+(build|test|run|generate|install)\b/, 'go generate and go test run project code'],
  [/\bmake\b|\bcmake\s+--build\b|\bninja\b/, 'build tools run project build logic'],
  [/\bdocker\s+(build|run|compose)\b|\bdocker-compose\b|\bpodman\s+(build|run)\b/, 'container builds run Dockerfile RUN steps'],
  [/\bpip-audit\s+(\.|--path)\b/, 'auditing a project directory can build packages'],
  [/\bosv-scanner\b[^\n]*--call-analysis=rust\b/, 'Rust call analysis runs build.rs'],
];

// Off-machine data flows that need explicit opt-in (rule 4).
const SENDS_DATA = [
  [/\btrufflehog\b(?![^\n]*--no-verification)/, 'TruffleHog verification sends secrets to their providers; add --no-verification unless the user opted in'],
  [/\bsemgrep\b[^\n]*--config(=|\s+)auto\b/, 'semgrep --config auto sends the project URL to the Semgrep Registry'],
  [/\bopengrep\s+scan\b(?![^\n]*\s(-f|--config)[=\s])/, 'opengrep without -f falls back to auto config and sends the project URL'],
  [/\bsemgrep\s+(login|ci)\b|\bsnyk\s+(code|auth|monitor)\b/, 'uploads code or authenticates to a cloud scanner'],
  [/\bbetterleaks\b[^\n]*--validation\b/, 'secret validation sends secrets to their providers'],
];

// Reporting findings to anyone outside the machine (rule 10).
const EXTERNAL_REPORTING = [
  /\bgh\s+(issue|pr)\s+(create|comment)\b/,
  /\bgh\s+api\b[^\n]*\b(issues|pulls|security-advisories|comments)\b/,
  /\bglab\s+(issue|mr)\s+(create|note)\b|\bglab\s+api\b[^\n]*\b(issues|merge_requests|notes)\b/,
  /(?:^|[;&|(]\s*)(?:mail|mailx|sendmail|msmtp)\s|\bSend-MailMessage\b/,
  /\bcurl\b[^\n]*\b(api\.github\.com|gitlab\.com\/api)\b[^\n]*\b(issues|pulls|merge_requests|security-advisories|notes|comments)\b/,
];
const GIT_PUSH = /\bgit\s+push\b/;

// Remote script piped into a shell (rule 6).
const PIPE_TO_SHELL = /\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b|\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^\n|]*\|\s*(iex|Invoke-Expression)\b/i;

// Secret shapes that must never appear unredacted in audit output (rule 7).
const SECRET_SHAPES = [
  /\bAKIA[0-9A-Z]{16}\b/,
  /\bASIA[0-9A-Z]{16}\b/,
  /-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----/,
  /\bgh[pousr]_[A-Za-z0-9]{36,}\b/,
  /\bglpat-[A-Za-z0-9_-]{20,}\b/,
  /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/,
  /\bsk_live_[A-Za-z0-9]{20,}\b/,
  /\bAIza[0-9A-Za-z_-]{35}\b/,
  /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/,
];
const KNOWN_EXAMPLES = /AKIAIOSFODNN7EXAMPLE|wJalrXUtnFEMI\/K7MDENG/;

function decide(decision, reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: decision,
      permissionDecisionReason: `[appsec-auditor] ${reason}`,
    },
  }));
  process.exit(0);
}

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
        if (age <= MARKER_MAX_AGE_MS) found.add(path.join(dir, AUDIT_DIR));
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

function insideAuditDir(filePath, auditDirs) {
  return auditDirs.some((dir) => isUnder(filePath, dir));
}

// Scripts run by path: `bash x.sh`, `node x.js`, `python x.py`, `./run`, `& .\build.ps1`,
// `powershell -File x.ps1`. The skill's own scripts and files in the audit directory are fine.
const INTERPRETER = /(?:^|[;&|(]\s*|\s)(bash|sh|zsh|dash|node|deno\s+run|bun\s+run|ts-node|tsx|python3?|py|ruby|perl|php)((?:\s+-{1,2}[A-Za-z][\w-]*(?:=\S+)?)*)\s+("[^"]+"|'[^']+'|[^\s;&|<>]+)/g;
const POWERSHELL_FILE = /\b(?:pwsh|powershell)(?:\.exe)?\b[^\n;|]*?\s-File\s+("[^"]+"|'[^']+'|[^\s;&|]+)/gi;
const DIRECT_EXEC = /(?:^|[;&|(]\s*)(?:&\s*)?("?\.{1,2}[\\/][^\s;&|"]+"?)/g;
const INLINE_CODE_FLAGS = /(^|\s)-(c|e|m|-eval|-print|Command)\b/;

function scriptTargets(command) {
  const targets = [];
  let m;
  INTERPRETER.lastIndex = 0;
  while ((m = INTERPRETER.exec(command))) {
    // `python -c "..."`, `node -e "..."`, `python -m module`: inline or module code, handled elsewhere.
    if (INLINE_CODE_FLAGS.test(m[2] || '')) continue;
    targets.push(m[3]);
  }
  POWERSHELL_FILE.lastIndex = 0;
  while ((m = POWERSHELL_FILE.exec(command))) targets.push(m[1]);
  DIRECT_EXEC.lastIndex = 0;
  while ((m = DIRECT_EXEC.exec(command))) targets.push(m[1]);
  return targets.map((t) => t.replace(/^["']|["']$/g, '')).filter((t) => t && !t.startsWith('-'));
}

function checkScripts(command, input, auditDirs) {
  const allowedRoots = [process.env.CLAUDE_PLUGIN_ROOT].filter(Boolean).concat(auditDirs);
  const base = input.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd();
  for (const target of scriptTargets(command)) {
    const resolved = path.resolve(base, target);
    if (allowedRoots.some((root) => isUnder(resolved, root))) continue;
    decide('ask', `This runs a script by path (${target}), which may be code from the repository under audit. Approve only if you trust it to run here.`);
  }
}

function checkCommand(command, input, auditDirs) {
  if (PIPE_TO_SHELL.test(command)) {
    decide('deny', 'Piping a downloaded script into a shell is not allowed during an audit. Download, verify the checksum or signature, then run (see README.md).');
  }
  if (EXTERNAL_REPORTING.some((pattern) => pattern.test(command))) {
    decide('deny', 'Findings are never reported outside the machine during an audit: no issues, pull requests, advisories, comments, or email (SKILL.md rule 10). The report goes to the user only.');
  }
  if (GIT_PUSH.test(command)) {
    decide('ask', 'Pushing during an audit sends commits to a remote. Approve only if the user asked for it (SKILL.md rule 10).');
  }
  for (const [pattern, why] of SENDS_DATA) {
    if (pattern.test(command)) decide('ask', `This sends data off the machine: ${why}. Approve only if the user opted in.`);
  }
  for (const [pattern, why] of EXECUTES_PROJECT_CODE) {
    if (pattern.test(command)) decide('ask', `This executes code from the repository under audit: ${why}. Approve only if you trust it to run here.`);
  }
  checkScripts(command, input, auditDirs);
}

function checkWrite(input, auditDirs) {
  const toolInput = input.tool_input || {};
  const filePath = toolInput.file_path || toolInput.notebook_path || '';
  if (!filePath) return;
  if (insideAuditDir(filePath, auditDirs)) {
    const text = [toolInput.content, toolInput.new_string, toolInput.new_source]
      .concat((toolInput.edits || []).map((e) => e && e.new_string))
      .filter((v) => typeof v === 'string')
      .join('\n');
    if (KNOWN_EXAMPLES.test(text)) return;
    for (const shape of SECRET_SHAPES) {
      if (shape.test(text)) {
        decide('deny', 'Audit output must not contain unredacted secrets (SKILL.md rule 7). Show the type, location, and at most the first 4 characters.');
      }
    }
    return;
  }
  decide('ask', `Modifying a project file during an audit: ${filePath}. Approve only fixes or proof tests the user has accepted (SKILL.md rule 8).`);
}

function main() {
  let raw = '';
  try {
    raw = fs.readFileSync(0, 'utf8');
  } catch {
    process.exit(0);
  }
  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    process.exit(0);
  }
  const auditDirs = activeAuditDirs(input);
  if (auditDirs.length === 0) process.exit(0);

  const tool = input.tool_name || '';
  if (tool === 'Bash' || tool === 'PowerShell') {
    checkCommand(String((input.tool_input || {}).command || ''), input, auditDirs);
  } else if (tool === 'Write' || tool === 'Edit' || tool === 'MultiEdit' || tool === 'NotebookEdit') {
    checkWrite(input, auditDirs);
  }
  process.exit(0);
}

main();
