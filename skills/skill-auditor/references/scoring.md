# Scoring

Contents: dimensions · rating scale · weights and grade · safety verdict · caps · calibration

Two results, kept apart: a **safety verdict** (can it be trusted on this machine) and a **quality grade** (how well does it work). A skill can be safe and poor, or excellent and unsafe. Never average them.

A third number comes from the script: the **mechanical risk score** (0 to 100, with a SAFE, CAUTION, or DO_NOT_INSTALL band). It is built from pattern findings, weighted by confidence, and says nothing about quality. Use it as evidence for the safety verdict, never as the verdict. A low score can miss a semantic problem the script cannot see, and a high score can be justified when the sensitive behavior is documented, necessary, and bounded. When your verdict differs from the score's band, say so and say why. Report the score after your review (run the script with `--review`), so confirmed, dismissed, and added findings are all reflected.

## Dimensions

| Dimension | Weight | Covers |
|---|---:|---|
| Triggering | 20 | Description clarity, trigger test results, overlap, invocation settings |
| Instruction quality | 25 | Value of each instruction, specificity, clarity, ordering, failure paths (`instructions.md`) |
| Verifiability | 15 | A way to check the work, evidence required, independent check, plan and approval gates |
| Structure and cost | 15 | Size, progressive disclosure, orphans, broken links, tokens on every trigger |
| Portability | 15 | Works from its own folder on another machine, runtime stated, fallbacks real |
| Hooks and enforcement | 10 | Correctness of shipped hooks, and whether hard rules are actually enforced. Not applicable if the skill has no hooks and needs none |

When a dimension does not apply, drop it and scale the others so the weights still total 100. Say so in the report.

## Rating scale

Rate each dimension from 0 to 4 and give two or three pieces of evidence for the rating.

| Rating | Meaning |
|---:|---|
| 4 | Strong. Nothing worth fixing, or only cosmetic items |
| 3 | Good. Minor problems that do not change how well it works |
| 2 | Mixed. At least one problem that will visibly hurt results for some users |
| 1 | Weak. The dimension is mostly failing; the skill works only by luck |
| 0 | Broken. The skill cannot do its job on this dimension |

Rate what is there, not what could be. Do not give 3 for "probably fine"; a rating with no evidence is a guess and does not count.

## Weights and grade

Quality score = sum of (rating ÷ 4 × weight) over applicable dimensions, scaled to 100.

| Score | Grade | Reading |
|---:|---|---|
| 90 and above | A | Ready to share |
| 75 to 89 | B | Good; fix the listed items when convenient |
| 60 to 74 | C | Works; fix before wider sharing |
| 40 to 59 | D | Unreliable; rework |
| Below 40 | F | Does not do its job |

## Safety verdict

Defined in `safety.md`: Safe to install, Install after changes, Do not install, Cannot judge. The quality score does not change it.

## Caps

Apply after computing the score:

- Any confirmed critical safety finding: no grade is issued. Report "Not graded: do not install".
- Triggering rated 0 or 1: the grade cannot exceed C, because a skill that does not load does not work.
- Verifiability rated 0: the grade cannot exceed C for any skill that produces changes or claims.
- A broken `SKILL.md` (STR01) caps the grade at F.
- A skill that can only be used with the author's own setup (Portability 0) caps the grade at C when it is meant for sharing.

## Calibration

Before finishing, check the scores against each other:

- Is any 4 given without two concrete strengths you can quote?
- Does any 1 or 0 lack a finding with an ID and location?
- If the report says "Excellent" in prose, does the score agree?
- Would the author, reading the evidence, accept the rating? If a rating depends on taste, soften it and say so.

A short skill is not a poor one: it is graded on whether it does its job at its size.
