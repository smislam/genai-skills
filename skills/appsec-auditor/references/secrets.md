# Secrets

`inventory.js` finds secret candidates deterministically, using the `secret` rules in `rules/rules.json`:
- **`secret` items** come from the working tree.
- **`secret-history` items** come from every commit on every branch (Standard and Deep depth): lines added anywhere in history, recorded at the commit that introduced them.

Excerpts are already redacted, so `coverage.json` never contains a secret value. Your job is to decide each item with `triage.md`, "Secrets". Never test a secret against its provider (SKILL.md rule 4), and redact everything you write (rule 7).

## Deciding secret items

Look at each item with `node ${CLAUDE_SKILL_DIR}/scripts/secret-context.js --root <repo> --id <item ID>`. It prints the surrounding lines, or the commit's change for history items, with every secret value redacted. **Don't use `git show` or open the file directly to look at a secret:** that prints the raw value into the conversation (rule 7). Then judge the value in context:

| Looks like | Decision |
|---|---|
| A live-format credential (cloud key, token, private key, password) for a real system | `finding`. Severity by `triage.md`: in the current tree it can be Critical; history-only is High, because it's still exposed and must be rotated |
| A placeholder (`changeme`, `<your-key>`, `${ENV_VAR}`, `xxxx`), an empty value, or a documented example (`AKIAIOSFODNN7EXAMPLE`) | `false_positive`, saying which |
| A test fixture with a dummy value, used only in tests | `false_positive`. Use a group entry by rule and path for many of them |
| A public key or certificate (not a private key) | `false_positive` |
| A value whose nature or environment can't be determined | `needs_review` |

**Context that matters:**
- Is the file ignored by git (`git check-ignore -v <file>`)? A local, ignored `.env` holding production credentials is still worth a note.
- Is the secret still in the current tree?
- Which environment is it for, judging by the file name, the hostnames, and the variable names?

**Where else to look.** These files often hold secrets in forms the rules can't recognize, so read them when the checklist includes them: `.env*`, `*.tfvars`, `application*.yml` and `.properties`, `appsettings*.json`, `docker-compose*.yml`, Kubernetes `Secret` manifests (base64 is encoding, not encryption), CI files, `.npmrc`, `.pypirc`, `*.pem`, `*.p12`, `*.pfx`, and `*.jks`. Report anything found that way as a finding beyond the checklist.

## Report

For each secret, give the type, file, line, and commit (for history findings), and at most the first 4 characters. Never the value. The fix is `remediation.md`, "Leaked secrets": revoke and rotate first.

## Manual procedure (non-deterministic mode, without Node.js)

The `secret` patterns in `rules/rules.json` are JavaScript regular expressions, which ripgrep (the Grep tool) also understands. `git log -G` uses a different dialect, so don't pass them to git.

1. **Working tree:** search with the Grep tool, using each `secret` pattern (apply its `flags`, for example `-i`).
2. **History** (Standard and Deep depth): write the added lines of every commit to a file inside the audit directory, then search that file with the Grep tool:
   ```
   git log --all -p --no-color -U0 --format="@@commit %H %ad" --date=short > .appsec-audit/tmp/history.txt
   ```
   For each match, the nearest preceding `@@commit` line gives the commit, and the nearest `+++ b/<file>` line gives the file.
3. Delete `history.txt` when you're done, because it contains the secrets themselves.

Label the report non-deterministic.
