# Artifact contracts

The canonical schema is `../../../schemas/paper-poster.schema.json`.

Do not pass unstructured stage prose as the next stage's source of truth.

Always persist the core artifacts:

- `paper_ir.json`
- `parse_report.json`
- `paper_story.json`
- `method_graph.json`
- `claim_evidence.json`

Persist these only when running the Poster branch:

- `selected_assets.json`
- `method_figure_map.json`
- `method_visual_plan.json`
- `key_idea_spec.json`
- `experimental_results_spec.json`
- `highlights_spec.json`
- `motivation_spec.json`
- `contribution_candidates.json`
- `contribution_spec.json`
- `contribution_audit.json`
- `motivation_contribution_audit.json`
- `motivation_contribution_preview.html`
- `poster_spec.json`
- `render_bundle.json`
- `final_qa_report.json`

The Poster branch also persists the sibling reading-report artifacts:

- `reading_report_spec.json`
- `source_index.json`
- `reading_report.html`
- `reading_report.md`
- `reading_report.pdf` when browser export is enabled
- `reading_report_render_bundle.json`
- `reading_report_render_metrics.json`
- `reading_report_qa.json`

The Poster branch also persists a human-facing handoff folder:

- `00-final-deliverables/README.md`
- `00-final-deliverables/manifest.json`
- `00-final-deliverables/notes/reading-notes.md`
- `00-final-deliverables/poster/poster.html`
- `00-final-deliverables/poster/poster.png` when browser export is enabled
- `00-final-deliverables/poster/poster.pdf` when browser export is enabled
- `00-final-deliverables/reading-report/reading_report.html`
- `00-final-deliverables/reading-report/reading_report.md`
- `00-final-deliverables/reading-report/reading_report.pdf` when available
- `00-final-deliverables/qa/final_qa_report.json`
- `00-final-deliverables/qa/reading_report_qa.json`
- `00-final-deliverables/qa/pipeline_summary.json`

This folder copies final human-facing files only. It must not replace or delete
the complete run directory and must not include rejected candidates, raw
statements, parser dumps, or intermediate audit JSON beyond the final QA files.

Use stable IDs across every artifact. A poster claim keeps its claim ID; a
selected figure keeps its asset ID; every assertion keeps its source block IDs.

The reading report expands, but never renumbers, those IDs. Each visible fact
keeps page, section, block ID, bbox, and a short evidence quotation. Formula
records preserve Equation ID plus original image or LaTeX. Poster coverage maps
each Poster item to its detailed report section.

Each local entry in `method_figure_map.json` records `match_kind` and
`binding_evidence`. Accepted match kinds are `exact_unique_alias`,
`exact_alias`, `explicit_figure_reference`, `distinctive_terms`,
`parent_module_structure`, `contextual_overlap`, and `complete_overview`.
`parent_module_structure` is valid only when a sourced parent-module
description explicitly names the covered child module. Figure records also keep
`semantic_role`, `role_confidence`, `role_reasons`, `subfigure_semantics`, and
`focus_subfigure_labels`, plus `visual_content_signals`,
`caption_content_consistent`, and mismatch reasons. Strong image-content
evidence that safely excludes a wrongly referenced result is recorded under
`resolved_role_conflicts`; unresolved ambiguity remains under `role_conflicts`.
The map records `role_conflicts` whenever a
Method-referenced figure lacks a stronger result role, or a proposed
method-design subfigure remains unclassified. A proposed panel inside a
qualitative or quantitative result does not become Method merely because it is
the authors' output. The visual plan records dedicated target, selected,
omitted, and sourced text-fallback module IDs so final QA can reject false
coverage caused by generic word overlap without forcing result charts into
Method.

Each item in `highlights_spec.json` binds a supported Claim and exact source
table cells, records all seven hard Gate results, stores recomputed absolute
and relative differences, and carries its weighted score and caveats. Zero to
three items are valid; composition must not synthesize fallback Highlights.
Decorated variants preserve their exact undecorated backbone baseline,
explicit Claim metric/dataset alignment, and a metric-derived source role so
efficiency columns cannot be rendered as primary effectiveness.

Each Motivation and Contribution visible string is a Poster-language rewrite,
not a source quote. `source_records` retain raw statements, block IDs, pages,
and sections for audit but Renderer reads only `visible_text`. Item counts are
Gate-driven and unbounded by a fixed target. Synonym clusters preserve all
merged IDs and source records.

Each large table in `experimental_results_spec.json` records `focus_crop` with
selected source row and column indices, `coordinate_method`,
`geometry_confidence`, `row_mapping`, `column_mapping`,
`duplicate_band_score`, source and padded row bounds, `glyph_padding_px`,
`edge_ink_ratio`, `glyphs_touch_crop_edge`, and whether visible separators
were inserted.
`display_mode=pdf_text_focus_crop` identifies an original PDF crop aligned by
real text boxes. `display_mode=verified_focus_table` requires `focus_table`
headers and rows copied deterministically from the source table HTML with
source table ID, page, and verification mode. Equal-grid raster mappings are
invalid.
