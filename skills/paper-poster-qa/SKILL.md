---
name: paper-poster-qa
description: Validate an academic poster against its source PaperIR, storyline, evidence matrix, selected assets, and browser metrics. Use before delivering HTML/PNG/PDF to detect unsupported statements, numeric mismatches, skipped captions, missing assets, Figure-1 bias, failed exports, overflow, and panel overlap.
---

# Paper Poster QA

Act as a truth-preserving delivery gate. Do not repair content silently.

## Checks

1. Require sources for every asserted story node.
2. Match poster numbers against paper text or structured tables.
3. Require inspection of every figure and table caption.
4. Reject any figure-number ranking prior.
5. Verify selected assets exist or have a reliable LaTeX representation.
6. Require HTML, PNG, and PDF when browser export was requested.
7. Reject missing images, DOM overflow, and overlapping panels.
8. Reject layout-generated ellipses and raw, unrendered LaTeX.
9. Return the responsible stage for every failure.
10. Require sources for every method node and at least 67% method-module
    coverage.
11. Reject result, qualitative, ablation, and dataset figures in Method.
    Reject any Method asset whose visible PDF-bbox content conflicts with its
    caption or Method-reference metadata.
12. Reject duplicate rendering of a complete overview as detail thumbnails.
    If no complete overview asset exists, require an ordered sourced method
    flow. Reject missing stages, dangling module/block bindings, an empty DOM
    render, or a rendered stage count that differs from the plan.
13. When vision is available, blind-read the Method panels and reject a layout
    whose modules, order, purposes, or innovations cannot be recovered without
    reopening the paper.
14. Reject an ambiguous overview choice and reject any choice resolved only by
    figure number or document order. The overview must represent the canonical
    or experimentally adopted main method; auxiliary variants belong below.
    Accept ambiguity only when every tied candidate is rejected and a sourced
    method flow replaces the overview.
15. Compare the planned storyboard asset IDs with browser-rendered asset IDs.
    Reject any layout repair that silently removes a method-module figure.
16. Validate Key Idea type, standalone headline, contribution relevance,
    Claim/PaperIR bindings, Method Overview non-duplication, 60–120-word
    budget, and explicit inference labeling.
17. Reject a Key Idea equation below 7/12, a generic loss or metric, a missing
    explanation, a changed crop hash, an invalid bbox, or a stretched render.
18. When no equation is selected, require the rendered item count to match its
    adaptive template, no fixed empty equation slot, and at least 55% visual
    region occupancy. A one-item full-size focus template is valid.
19. Validate Experimental Results headline, Claim/block bindings, contextual
    metrics, exact table values, metric directions, baseline,
    dataset/configuration consistency, original-asset use, and the 100-word
    budget. Treat sparse metric-card count, mixed context density, and missing
    large-table focus crops as warnings when the numbers and source bindings
    remain truthful.
20. Reject table crops that lose headers, methods, metric directions, the
    proposed row, a strong baseline, dataset/setting, or necessary footnotes.
21. Reject missing result assets, stretched images, unreadable table text,
    layout mismatches, and qualitative evidence without quantitative support.
22. Reject equal-grid raster slicing, duplicated table bands, image upscaling,
    clipped focus tables, missing glyph-bound padding, edge-touching glyph
    components, missing configuration columns, and focus-table text below the
    Poster readability threshold.
23. Validate every Motivation and Contribution Gate, source block, semantic
    merge, role boundary, and completeness field. Reject citations, quotations,
    author voice, discourse markers, OCR/HTML/LaTeX residue, unsupported
    expansion, or more than eight copied source words.
24. Require Renderer output to contain only the validated visible strings;
    raw statements and source metadata must remain absent from Poster HTML.
25. Return a stage that the orchestrator can execute. After a routed repair,
    reject repeated identical failures as `no_progress` rather than looping
    without change.
26. Return `passed_with_warnings`/`usable_with_warnings` for an empty optional
    Highlights panel, one traceable Motivation item, soft Key Idea
    length/space variance, sparse or mixed-but-truthful result presentation,
    non-empty adaptive Method fallback-card reduction, missing large-table
    focus crop, or at most eight pixels of auxiliary-panel vertical overflow.
    Keep evidence, figure-role, language-integrity, and core readability
    failures blocking.

Read [quality-gates.md](references/quality-gates.md) for routing rules.

```powershell
python scripts/run.py --paper-ir paper_ir.json --story paper_story.json --evidence claim_evidence.json --assets selected_assets.json --method-graph method_graph.json --method-figure-map method_figure_map.json --method-visual method_visual_plan.json --key-idea key_idea_spec.json --experimental-results experimental_results_spec.json --highlights highlights_spec.json --motivation motivation_spec.json --contributions contribution_spec.json --spec poster_spec.json --render render_bundle.json --output runs/paper/05-reports
```
