# Running the script: options, outputs, gates, baselines, reviews

Contents: running it · scope · outputs · exit codes and gates · the review file · baselines · custom rules · comparing versions · using it in CI · the install gate hook · verifying the tool itself

Needs Python 3.12 or newer and nothing else: standard library only, no packages to install, no virtual environment. It only reads the audited files.

```
python3 -I <skill-auditor>/scripts/lint.py <target> [options]
```

The command name varies by platform: `python3` on macOS and Linux, `python` or `py -3` on Windows. Use whichever runs Python 3.12 or newer. Keep `-I` (isolated mode): the audited folder is untrusted, and `-I` stops Python from importing anything from the current folder or from the user's environment variables. The script never writes bytecode files.

`<target>` is a skill folder, a folder of skills, a single file, or a `.zip` (audited in memory; nothing is extracted).

## Scope

| Option | Effect |
|---|---|
| `--recursive` | Look for skills below the target. This happens automatically when the target itself has no `SKILL.md`. |
| `--max-skills N` | Stop after N skills (default 32) |
| `--exclude GLOB` | Skip matching paths. Repeat for several. Excluded files are counted in the coverage report, never hidden. |
| `--rules FILE` | Add your own rules (below) |
| `--osv` | Look up pinned dependencies on OSV.dev and CISA KEV (`supply-chain.md`) |

## Outputs

| Option | Effect |
|---|---|
| `--format json` | Default. Everything: findings, coverage ledger, hosts, dependency status, snapshot, risk score |
| `--format markdown` | A readable summary table |
| `--format terminal` | Compact text |
| `--format sarif` | SARIF 2.1.0 for code-scanning tools and editors. Each result has a stable fingerprint, a location, a severity level, and the review outcome. |
| `--out FILE` | Write to a file (print a one-line summary). Do not write inside the audited folder. |
| `--pretty` | Indent the JSON |

Each finding has: `id`, `name`, `category`, `severity`, `confidence`, `file`, `line`, `evidence`, `context`, `surface` (instructions, docs, code, config, tests, comments), `cwe`, `owasp`, `fix`, `fingerprint`, and `review` once reviewed.

## Exit codes and gates

| Code | Meaning |
|---|---|
| 0 | Every gate passed |
| 1 | A gate failed (reasons are printed to stderr and listed under `gates`) |
| 2 | Bad usage or unreadable input |

Gates:

| Option | Fails when |
|---|---|
| (default) | The mechanical risk score is over 50 |
| `--max-score N` | The score is over N |
| `--fail-on-findings` | Any active finding other than quality items |
| `--fail-on SEVERITY` | Any finding at that severity or above |
| `--fail-on-incomplete` | Coverage is not complete |
| `--min-coverage N` | Coverage is below N percent |
| `--require-review` | A high or critical finding has no review outcome, or there is no review file |

**The risk score** (0 to 100) is a saturating sum of finding points (critical 40, high 22, medium 4, low 1) weighted by confidence, 1.25× for scripts and hooks, with repeats in one file counted at a quarter. Bands: under 20 SAFE, 20 to 49 CAUTION, 50 and over DO_NOT_INSTALL. Any confirmed critical finding sets a floor of 85. Incomplete coverage turns SAFE into CAUTION. Quality findings (structure, wording, portability) never count. The score is an input to your verdict, not the verdict.

## The review file

The script's findings are leads. Your outcomes and your added findings go in a JSON file passed with `--review`, so they appear in the score, the report, and SARIF:

```json
{
  "outcomes": [
    { "fingerprint": "ab12cd34ef56…", "outcome": "confirmed", "confidence": 0.9, "reason": "Script posts the environment to webhook.site." },
    { "id": "SUP02", "file": "references/vuln-classes.md", "line": 99, "outcome": "dismissed", "reason": "A table row naming the pattern as something to detect; not an instruction." }
  ],
  "findings": [
    { "id": "SEM04", "severity": "high", "file": "scripts/sync.js", "line": 12, "message": "Uploads project files; the description says it only formats.", "evidence": "fetch(url, {method:'POST', body: files})", "confidence": 0.9 }
  ]
}
```

Outcomes: `confirmed`, `dismissed` (reason of ten characters or more, or it is ignored and the finding stays), `low-confidence`, `needs-user`. Structural findings keep counting even if dismissed. A finding with no outcome counts in full and shows under `review.summary.unreviewed`. Write the file as you work, then run the script again with `--review` to get the final numbers.

## Baselines

A baseline records findings someone has already looked at and accepted, so a later run shows only what is new.

```
python3 -I lint.py <skill> --make-baseline baseline.json --reason "Reviewed 2026-11-06 by <name>: documented patterns in references"
python3 -I lint.py <skill> --baseline baseline.json --show-suppressed
```

- Entries are either exact fingerprints (tied to the rule set, file, and matched text, so any edit reactivates them) or rules with `id`, `path`, and `message` globs (which survive edits). Every entry needs a reason of at least eight characters or the file is rejected.
- Suppressed findings never add to the score or the gate. They are listed in the report with their reason.
- Structural findings cannot be baselined.
- Keep the baseline outside the audited folder. If it is inside, it is left out of the scan.
- **Use only a baseline you wrote.** A baseline shipped by the skill's author is the author telling you what to ignore.

Inline: the marker `audit-ignore` on a line, or on the line above it, moves that line's findings to `suppressed`. The report then adds STR13 so the suppression is itself visible. Never accept an inline marker in someone else's skill without reading what it hides.

## Custom rules

```json
[{ "id": "ORG-1", "severity": "high", "confidence": 0.8, "on": ["md", "code", "cfg"],
   "pattern": "internal\\.corp\\.example", "flags": "i", "message": "Internal host reference" }]
```

`on` selects instruction text, scripts, and config files. Custom IDs are reported as `CUS-<id>`. Use this for your organization's rules (banned hosts, required licenses, naming).

## Comparing versions

`--compare previous-report.json` adds the DIF findings (`supply-chain.md`). Keep each audit's JSON next to the decision memo.

## Using it in CI

```
python3 -I scripts/lint.py skills --recursive --format sarif --out skill-audit.sarif --baseline .skill-baseline.json --fail-on high --fail-on-incomplete
```

Upload the SARIF file with your code-scanning tool. The exit code fails the job. Use `--max-skills` and `--exclude` to bound large repositories. Run `--osv` only where the runner may reach the internet.

## The install gate hook

`hooks/install-gate.py` is optional and does nothing unless you set `SKILL_AUDITOR_GATE`:

- `advise`: after a skill file is written or edited, audit that skill and tell the agent the top findings. When a command installs a skill (a clone of a skills repository, a plugin install, a copy into a skills folder), remind the agent to audit first.
- `strict`: also block when the mechanical recommendation is DO_NOT_INSTALL.

To use it, install `skill-auditor` as a plugin so `hooks/hooks.json` is picked up, then set the variable in your environment. It reads files only. A hook that fails lets the work continue.

`hooks/hooks.json` starts the hook through a small shell launcher, so there is nothing to configure per platform. The launcher tries `python3`, then `python`, then `py -3`, and runs the hook with the first one that really is Python 3.12 or newer (this also skips the Windows Store placeholder for `python3`). It needs a POSIX shell: `sh` on macOS and Linux, and Git Bash on Windows, which Claude Code uses there by default. Without Git Bash, Claude Code falls back to PowerShell, the launcher cannot run, and the hook does nothing. If no suitable Python is found the hook also does nothing: it fails open, so nothing is blocked and nothing is reported. Check that it runs by editing a skill file with `SKILL_AUDITOR_GATE=advise` set. On Windows the launcher costs about 55 ms per hook call, measured.

## Verifying the tool itself

```
python3 -I scripts/selftest.py
```

Builds a deliberately hostile skill and a clean one in a temporary folder, runs the script on them, and checks about eighty things: that each attack technique is detected, that the clean skill stays quiet, and that formats, gates, baselines, reviews, comparisons, ZIP input, custom rules, and suppression behave. It exits 1 on any failure. Run it after changing the script or its rules.
