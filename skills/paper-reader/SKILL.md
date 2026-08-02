---
name: paper-reader
description: Orchestrate evidence-grounded reading of a research PDF or PaperIR, producing a sourced storyline and claim-evidence audit, with an optional AMP-style HTML/PNG/PDF Poster and detailed HTML/Markdown/PDF reading report. Use when a user asks to read, analyze, summarize, verify, question, create reading notes, or turn an academic paper into a Poster while preserving original figures, equations, results, and source provenance.
---

# Paper Reader

Run a thin orchestration layer around a reusable analysis core. Treat Poster
generation as one optional consumer of the analysis, not as the whole project.
Exchange only validated JSON artifacts between stages.

## Core analysis

1. Validate the explicit input and output paths.
2. Invoke `paper-ingest`; parse every PDF with MinerU or validate PaperIR JSON.
3. Invoke `paper-storyline` and require source evidence for every assertion.
4. Invoke `paper-method-graph` to reconstruct sourced method modules and
   reading order.
5. Invoke `paper-evidence-audit` to map claims to methods, experiments, figures, and tables.

Stop when MinerU or provenance validation fails. Never retry through a basic
PDF parser.

## Poster branch

Enter this branch only when the user requests a Poster, HTML, PNG, or PDF.

1. Invoke `paper-asset-select`; inspect every caption and never use figure
   number as a ranking feature.
2. Invoke `paper-method-figure-map`; exclude every result, qualitative,
   ablation, and dataset figure from Method. Distinguish a complete-system
   overview from a local module even when both captions say "proposed".
   Parse subfigure labels independently: a mixed comparison figure may be a
   Method asset when a specific panel is explicitly described as `ours` or
   `proposed`, but the focus label must be preserved in the visual plan. Bind
   figures first through their explicit Method-section citations, then through
   exact aliases and module-distinctive terms;
   generic words such as `attention`, `fusion`, `block`, and `transformer`
   never establish a sibling-module mapping by themselves. A lone generic
   word such as `result` in method prose is not experimental evidence.
   Normalize publisher-styled prefixes such as `F I G U R E 4` before role
   classification. Captions that directly describe the proposed full system
   or the details of a named block take precedence over noisy neighboring
   page context. A measured comparison, test-result plot, training curve,
   heatmap, or feature visualization remains a result asset even when a noisy
   Method reference or the phrase `overall network` is nearby. Treat
   `Architecture of the proposed <Name>Net/Network/Model` as a complete-system
   overview even when the same caption lists its inner modules. Extract text
   inside each source-PDF figure bbox and let strong metric, axis, percentage,
   or measured-comparison evidence override a mismatched Method caption or
   reference. Persist the resolved mismatch and exclude the asset from Method.
3. Invoke `paper-method-visual-compose`; choose one complete overview,
   overview plus dedicated details, or a multi-figure storyboard. If a
   high-confidence dedicated figure exists for a core module, include it
   unless the four-detail visual budget is already filled by earlier sourced
   modules; overview coverage does not suppress a clearer module figure. A
   parent module may retain multiple dedicated figures when each introduces a
   different parent-owned alias, such as separate LFE and GFE blocks; do not
   collapse those complementary innovations into one arbitrary winner.
   When no reliable complete overview exists, build a compact ordered flow
   from sourced MethodGraph modules. Require every stage to bind to a real
   module ID and PaperIR block; never leave a large empty overview placeholder.
   If overview candidates remain tied, reject all tied candidates from the
   Overview and local-module storyboard instead of selecting by document order.
4. Invoke `paper-key-idea`; choose one evidence-grounded type and an optional
   core equation without reusing Method Overview.
5. Invoke `paper-experimental-results`; select Claim-grounded original result
   assets, verify contextual metrics, and choose an adaptive result layout.
   Re-render every selected table from its PDF bbox at high resolution. Keep
   small tables whole. For large tables, use PDF text coordinates to retain
   the true header, Ours row, matched strong baselines, configuration columns,
   and Claim-relevant metrics. Derive row bands from the union of matched cell
   text boxes, add glyph-height-based padding, and reject edge-touching ink.
   Never infer equal row heights or column widths.
   If reliable PDF text geometry is unavailable, render a deterministic
   verified focus table from source cells instead of stitching raster strips.
   Reject upscaled table images, duplicated bands, and final text below the
   Poster readability threshold. Compact repeated multi-row header prefixes
   for display while retaining the exact source headers in provenance.
6. Invoke `paper-highlights`; require exact source cells, complete matched
   comparison context, recomputed absolute and relative differences, seven
   passed hard Gates, and a score of at least 75. Select zero to three
   non-duplicate items. Zero verified items omit the optional cards with a
   warning rather than blocking the Poster; require exact plain/decorated backbone pairing,
   explicit Claim metric and dataset alignment, and efficiency-aware role
   assignment. Never add a weak result to fill the layout.
7. Invoke `paper-motivation-contributions`; extract problem-side and
   solution-side semantic units, apply every Gate, merge only true synonyms,
   rewrite into neutral Poster language, and block citations, author voice,
   OCR residue, result leakage, or direct source copying.
8. Invoke `paper-poster-compose` to create `poster_spec.json`.
9. Invoke `paper-poster-render` to produce HTML and browser exports.
10. Invoke `paper-poster-qa`; route each failure only to the responsible stage.
11. Invoke `paper-reading-report-compose` to expand all validated artifacts
    into a page- and block-traceable reading report.
12. Invoke `paper-reading-report-render` to create HTML, Markdown, and A4 PDF.
13. Invoke `paper-reading-report-qa`; fail the final run when report
    traceability or required rendering fails.
14. Export `00-final-deliverables/` as the human-facing handoff folder. Copy
    the final Poster HTML/PNG/PDF, reading report HTML/Markdown/PDF, concise
    generated reading notes, final QA, reading-report QA, and
    `pipeline_summary.json`. Preserve the full run directory separately for
    debugging and provenance.

The reading report is a sibling output built from the shared analysis graph.
Never reconstruct it from the Poster screenshot.

Read [orchestration.md](references/orchestration.md) before changing stage order
or retry rules. Read [contracts.md](references/contracts.md) before modifying
any artifact shape.

## Run

```powershell
python scripts/run.py --input paper.pdf --output runs/paper --mode analysis
python scripts/run.py --input paper.pdf --output runs/poster --mode poster
```

Treat `passed_with_warnings` from parsing or heuristic analysis as requiring an
agent review before final submission. Expose it as
`delivery_status=usable_with_warnings`. Never report success when final QA is
`failed` or `blocked`, and retain such a render only as `poster-debug.*`.

For an existing completed run, regenerate the clean handoff folder with:

```powershell
python scripts/export_deliverables.py --summary runs/poster/pipeline_summary.json
```

