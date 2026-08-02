---
name: paper-evidence-audit
description: Audit whether a paper's methods, experiments, tables, and figures support its extracted claims and storyline. Use after paper-storyline or when checking overclaims, experimental validity, ablation support, confounds, causal language, reproducibility, and claim-to-evidence traceability.
---

# Paper Evidence Audit

Evaluate the paper that exists, not a preferred alternative paper.

## Audit

For every claim:

1. Record the author location.
2. Identify the required evidence type.
3. Link actual result blocks, figures, or tables.
4. Compare direction, magnitude, setting, baselines, and uncertainty.
5. Classify support as `supported`, `partially_supported`, `unsupported`, or
   `conflicted`.
6. Record confounds, missing controls, alternative explanations, and
   generalization limits.

Read [audit-rubric.md](references/audit-rubric.md) for claim-type checks.
The offline script uses lexical matching only; replace its tentative verdicts
with a full agent audit before final submission.

```powershell
python scripts/run.py --paper-ir paper_ir.json --story paper_story.json --output runs/paper/02-analysis
```

