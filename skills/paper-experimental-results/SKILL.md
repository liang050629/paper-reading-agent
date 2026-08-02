---
name: paper-experimental-results
description: Build and validate a claim-grounded Experimental Results specification for a research poster by selecting original quantitative and supporting assets, extracting contextual metrics, choosing an adaptive layout, and preserving exact PaperIR provenance. Use after Claim–Evidence auditing whenever a poster results panel must answer whether, against what, by how much, and under which evaluation conditions a method works.
---

# Paper Experimental Results

Generate `experimental_results_spec.json`; do not render HTML in this stage.

## Procedure

1. Read the Claim–Evidence Matrix before considering figures or tables.
2. Classify supported Claims as performance, efficiency, ablation,
   generalization, qualitative, or theory/analysis.
3. Rank every result figure and table against those Claims. Figure or table
   number contributes zero points.
4. Select exactly one primary quantitative asset. Select at most one
   non-redundant secondary asset.
5. Bind each asset to real Claim IDs, block IDs, page, bbox, caption, and an
   explicit selection reason.
6. Target two to four exact metrics, but keep a truthful sparse result panel
   when fewer verified metrics survive extraction. Metric-card count and mixed
   context density are presentation warnings, not delivery blockers. Preserve
   metric direction, strong baseline, dataset, configuration, evaluation
   condition, and table/block provenance. Support both standard method-row
   tables and transposed tables whose methods are columns. Reject
   configuration counts and table/figure numbers as metrics, and reject
   loss-definition tables as main results.
7. Use the original embedded asset or re-render its `page+bbox` from the
   source PDF at high resolution. Never redraw experimental data with AI.
8. For tables, preserve the header, method names, metric names/directions,
   proposed row, a strong baseline, dataset/setting, and necessary footnotes.
   Keep a small table whole. For a large table, locate real row and column
   boundaries with PDF text coordinates and retain only Claim-relevant
   comparisons, with visible separators across skipped regions. Derive each
   row band from the union of all matched cell text boxes, add
   glyph-height-based top/bottom padding, and run a connected-component
   edge-ink check. Never divide a raster into equal-height rows or equal-width
   columns. If any glyph touches a crop boundary or PDF geometry cannot be
   verified, render a deterministic focus table from the verified PaperIR
   cells instead of guessing pixel boundaries. If neither a verified focus
   crop nor a focus table can be built, keep the original asset and route the
   missing focus crop as a warning unless readability or numeric provenance is
   unsafe.
9. Choose one adaptive layout:
   `quantitative_plus_qualitative`, `main_plus_ablation`, or
   `finding_plus_generalization`.
10. Keep the headline to 15–30 words, prose to 100 words, captions to one
    line, and the condition note to one or two lines.

11. Reject duplicated bands, clipped or upscaled tables, missing configuration
    columns, unreadable final text, and any focused table that overflows its
    rendered panel.

Read [results-policy.md](references/results-policy.md) before changing Claim
mapping, crop context, metric verification, layout selection, or failure
routing.

```powershell
python scripts/run.py --paper-ir paper_ir.json --story paper_story.json --evidence claim_evidence.json --output runs/paper/04-poster
```
