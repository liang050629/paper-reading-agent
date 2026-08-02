---
name: paper-highlights
description: Select and validate zero to three evidence-gated results for the five-second memory area of a research poster. Use after paper-experimental-results when Poster Highlights must be traceable to exact source table cells, preserve matched comparison context, recompute improvement arithmetic, reject weak or misleading numbers, avoid semantic duplication, and omit the optional panel rather than inventing weak evidence.
---

# Paper Highlights

Generate `highlights_spec.json` and `highlights_report.json`; do not compose or
render the Poster in this stage.

## Procedure

1. Read `paper_ir.json`, `paper_story.json`, `claim_evidence.json`, and
   `experimental_results_spec.json`.
2. Consider candidates only from supported core Claims, main results,
   independently evidenced efficiency/generalization/robustness results, or
   traceable quantitative results repeated in the Abstract or Conclusion.
3. Reject Related Work numbers, experiment settings, hyperparameters,
   contribution numbering, module numbering, and layout-filling fallbacks.
4. Require every candidate to pass all seven hard Gates: traceability, complete
   context, matched comparison, recomputed arithmetic, Claim alignment,
   representativeness, and caveat preservation.
5. Interpret decorated table rows such as `ViT-B†` as variants only when an
   exact undecorated `ViT-B` row exists in the same table group. Never compare
   a decorated method against a different backbone or let `our ViT-B†` mark
   plain `ViT-B` as the proposed method.
6. Match explicit Claim metrics and datasets before scoring. A broad
   performance Claim may support a main quality metric, but an explicit mIoU
   Claim cannot generate a Top-1 card from another task or dataset.
   When extracted table metadata uses a placeholder, recover dataset and
   interpretation-changing conditions from the bound Claim first, then the
   asset caption and bound source blocks. Prefer the Claim's explicit scope
   over unrelated datasets mentioned elsewhere in the same paragraph.
7. Classify Params, FLOPs, latency, runtime, throughput, and memory as
   efficiency evidence even when they appear in the main-results table. They
   cannot occupy `primary_effectiveness`; an unchanged cost is displayable
   only as a preserved-budget constraint, not as a fabricated gain.
8. Score only candidates that pass every Gate. Apply the defined weights and
   penalties; require a final score of at least 75.
9. Select at most three non-duplicate roles in this order:
   `primary_effectiveness`, `improvement_over_baseline`, and
   `efficiency_or_generalization_or_robustness`.
10. Canonicalize dataset names before deduplication so `ImageNet-1k` and
   `the ImageNet-1k dataset` cannot create duplicate cards for the same metric.
11. Keep one or two items when fewer than three candidates qualify. Never
   synthesize a weak Highlight to fill space. If none qualifies after
   recovery, return `HIGHLIGHT_EVIDENCE_INSUFFICIENT` as a warning, omit the
   Highlight cards, and keep the verified Experimental Results panel.
12. Persist exact table/figure identity, page, source and baseline cells,
   dataset, configuration, evaluation conditions, arithmetic, Gate results,
   scores, caveats, Claim IDs, and source block IDs.
    Distinct method or loss configurations may be compared only when their
    dataset, split, metric, protocol, fine-tuning, and recovery conditions are
    matched and both configurations remain explicit.
13. Treat invalid selected Highlights as blocking. An empty selection is
   `passed_with_warnings`; arithmetic, source-cell, Gate, scoring, scope, or
   duplication failures in a selected item remain blocking.

Read [highlights-policy.md](references/highlights-policy.md) before changing
candidate eligibility, Gate definitions, scoring, penalties, role selection,
display budgets, provenance, or validation routing.

```powershell
python scripts/run.py `
  --paper-ir paper_ir.json `
  --story paper_story.json `
  --evidence claim_evidence.json `
  --experimental-results experimental_results_spec.json `
  --output runs/paper/04-poster
```
