---
name: paper-asset-select
description: Inspect every paper figure and table caption plus surrounding text, classify asset roles, and select the most likely overview framework, provisional equation candidates, and claim-supporting result assets. Use before building a paper poster or whenever a workflow must choose original paper visuals without assuming Figure 1 is the main diagram.
---

# Paper Asset Select

Select original paper assets with explicit reasons and fallbacks.

## Procedure

1. Read every figure and table caption.
2. Read each caption's section, preceding/following text, and every citing
   sentence.
3. Build the general catalog and classify broad overview/result/equation roles.
4. Rank overview candidates without using the figure number. Treat this result
   as a candidate; `paper-method-figure-map` owns the final Method eligibility.
5. Render the top candidates as a contact sheet and visually verify the
   top-ranked result when vision is available.
6. Map result assets to supported claim IDs.
7. Rank provisional equation candidates by mechanism/objective centrality, not
   visual complexity. `paper-key-idea` owns the final six-dimension equation
   decision and may reject every candidate.

Read [selection-rubric.md](references/selection-rubric.md) for scoring and
fallback rules.

If no reliable overview exists, return `overview_asset: null`; never fill the
poster with an unrelated figure.

```powershell
python scripts/run.py --paper-ir paper_ir.json --evidence claim_evidence.json --output runs/paper/03-assets
```
