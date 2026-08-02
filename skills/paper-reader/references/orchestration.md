# Orchestration

## Core analysis path

1. `paper-ingest`
2. `paper-storyline`
3. `paper-method-graph`
4. `paper-evidence-audit`

Stop on MinerU installation, execution, structured-output, or provenance
failure. Never route a failed PDF to a basic parser.

Route unsupported claims to storyline or evidence audit. Preserve this core
for question answering, reading notes, comparison, and future output branches.

## Poster branch

After core analysis, run:

1. `paper-asset-select`
2. `paper-method-figure-map`
3. `paper-method-visual-compose`
4. `paper-key-idea`
5. `paper-experimental-results`
6. `paper-highlights`
7. `paper-motivation-contributions`
8. `paper-poster-compose`
9. `paper-poster-render`
10. `paper-poster-qa`
11. `paper-reading-report-compose`
12. `paper-reading-report-render`
13. `paper-reading-report-qa`

Route caption failures to ingest, wrong assets to asset selection, missing
method modules to method graph, figure-role errors to method figure mapping,
coverage or duplication failures to method visual composition, content density
to poster compose, Key Idea type/equation/provenance failures to paper-key-idea,
result Claim/metric/layout failures to paper-experimental-results, wrong result
assets to paper-asset-select, Highlight Gate/arithmetic/deduplication failures
to paper-highlights, Motivation/Contribution role, copy, cleanup, merge, or
traceability failures to paper-motivation-contributions, and DOM/render
failures to render.

Execute the returned route rather than stopping at the first non-render
failure. Rebuild its dependent stages before composing and rendering again:

- Results rebuilds Results and Highlights.
- Motivation/Contributions rebuilds its validated specs.
- Method figure mapping rebuilds the map, method visual plan, and Key Idea.
- Asset selection rebuilds selected assets, method mapping/visuals, Results,
  Highlights, and Key Idea.
- Method graph rebuilds all downstream method-dependent artifacts.

Allow at most three validation cycles. If the same responsible stage returns
the same error-code set after a repair, record `no_progress` and stop.

Render each validation attempt to `poster-candidate.*`. Promote a candidate to
`poster.*` only when QA returns `passed` or `passed_with_warnings`; rename a
blocked final attempt to `poster-debug.*`. Optional Highlight absence, one
traceable Motivation item, and soft Key Idea length/space variance may produce
`usable_with_warnings`. Numeric/context errors, figure-role conflicts, raw
LaTeX, residual fragments, core truncation, unreadable tables, missing images,
and major overflow remain blocking.

After Poster QA, build the reading report from all upstream artifacts rather
than from the rendered Poster. Route missing sources, dangling block IDs,
unsupported expansions, Formula provenance, Claim–Evidence, or Poster coverage
failures to reading-report compose. Route missing assets, horizontal overflow,
small text, and PDF export failures to reading-report render. The final
pipeline status cannot be `passed` when reading-report QA fails.

Experimental result tables follow a readability-first evidence route. Re-render
the source `page+bbox` at high resolution even when the parser emitted a
nominally large raster. Preserve a small table whole. For a large table, bind
HTML rows and headers to PDF text boxes before selecting non-contiguous rows or
columns; insert visible separators wherever source regions are skipped. If the
PDF has no reliable text geometry, use a verified structured focus table whose
cells come deterministically from the source table extraction. Never use equal
row-height or equal-column-width raster slicing. Form each row band from the
union of its matched cell boxes, add glyph-height-based padding, and inspect
connected components at the top and bottom edges. Fall back to a verified
structured table when safe padding is impossible. Final QA rejects table image
upscaling, duplicated bands, edge-touching glyphs, missing comparison context,
and unreadable text.

Method figure mapping must resolve the real Method region before matching
assets. Related Work taxonomies such as `CNN-based Methods` are never method
modules. A complete system diagram may cover all method nodes; a local module
diagram must be bound by an explicit Method-section figure citation, an exact
alias, or a module-distinctive term. Parse `(a)/(b)/(c)` semantics before
assigning a whole-figure role, preserve the focus label for an explicitly
proposed panel, and do not let a lone generic `result` token override Method
evidence. Conversely, explicit test-result, measured-comparison, training-curve,
heatmap, and qualitative-result captions override noisy Method references and
must remain outside Method. A caption beginning `Architecture of the proposed
<Name>Net/Network/Model` is a complete-system overview even if it subsequently
enumerates local modules. Route ambiguous alias ownership or missing figure-reference bindings
to method graph, role conflicts to method figure mapping, and omitted
high-confidence dedicated figures to method visual composition. A system
overview may establish context, but it must not suppress clearer local figures
for the core modules. Normalize spaced publisher captions (`F I G U R E N`)
before classification. A direct full-system caption or `Details of <module>`
caption outranks noisy neighboring result prose. When one parent node owns
several separately illustrated aliases, retain complementary sibling figures
within the four-detail budget rather than enforcing one figure per parent.
Heatmaps, attention visualizations, effectiveness plots, and other result
assets never enter Method through this sibling rule.
Before accepting a Method asset, inspect text embedded inside its source-PDF
bbox. Strong metric names, axes, repeated numbers, percentages, baseline/Ours
labels, or measured costs override a conflicting caption/reference. Exclude
the asset and record the mismatch as resolved; block only if an inconsistent
asset still enters the visual plan.

When no reliable complete overview figure survives mapping, Compose must build
an ordered `sourced_method_flow` from MethodGraph modules. Each flow item
requires a module ID, readable label and explanation, and real source block
IDs. Renderer must expose its mode and item count to browser metrics. QA
rejects a missing flow, dangling bindings, or an empty rendered flow.
When overview ranking remains ambiguous, Method Visual must reject every tied
candidate as an overview and must not reuse those full-system candidates as
local module cards.

Retry at most three times. Tighten content budgets for compose/render failures;
for semantic or provenance failures, return to the named analysis stage and
rebuild its dependent artifacts.

