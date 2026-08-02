# Experimental Results policy

## Claim-to-asset mapping

| Claim | Primary evidence |
|---|---|
| Main performance | Main result table or performance chart |
| Efficiency | Parameters, FLOPs, latency, throughput, or memory comparison |
| Module effect | Ablation table or plot |
| Generalization | Cross-dataset, external, or robustness result |
| Visual quality | Qualitative comparison backed by quantitative evidence |
| Theory or mechanism | Analysis figure or statistical table |

Do not select by `Figure 1`, `Table 1`, or document order.

## Asset contract

Every displayed asset retains:

- `source_claim_ids`;
- `source_block_ids`;
- `page` and `bbox`;
- `table_id` or `figure_id`;
- full source caption and a one-line display caption;
- selection reasons;
- original local path and source resolution.

The display priority is original vector/embedded image, a high-resolution PDF
`page+bbox` crop, an existing PaperIR crop, and finally a deterministic focus
table reconstructed from verified PaperIR cells. Experimental data must never
be AI-redrawn.

## Table context

Prefer a full original crop plus verified metric cards when cell-level crop
coordinates are unavailable. A reduced table crop is valid only if it retains
the header, proposed row, at least one strong baseline, metric names and
directions, dataset/setting, and necessary footnotes.

For large tables, find row and column boundaries from PDF text boxes. Preserve
the real header and selected source rows/columns, insert visible separators
where regions are skipped, and build each row from the union of its matched
cell text boxes rather than method-name centers alone. Add padding derived
from the median glyph height, then reject any band whose non-rule ink touches
its top or bottom edge. Record row indices, source and padded row bounds,
`glyph_padding_px`, `edge_ink_ratio`, `glyphs_touch_crop_edge`, column indices,
coordinate method, source/display hashes, and a duplicate-band score.
Equal-grid raster slicing is forbidden because real table rows and columns
are not uniform. When text geometry or safe padding is unavailable, render
verified cells as a crisp HTML focus table and retain the original headers
separately for provenance.

## Metric contract

Each visible number needs value, metric, direction, baseline, dataset,
configuration, evaluation condition, source table ID, and source block IDs.
Never combine metrics from unmatched configurations in one metric row. Record
absolute and relative deltas distinctly.

Metric-card count is a presentation target. Prefer two to four cards, but do
not fabricate or over-extract metrics to fill the grid. A sparse panel with
zero or one verified metric, or a panel whose verified cards span multiple
contexts, should remain deliverable with warnings when exact values, source
bindings, and primary quantitative evidence are intact.

## Failure routing

- no suitable or readable primary asset: `paper-asset-select`;
- invalid Claim/metric/layout plan: `paper-experimental-results`;
- unreadable rendered table or missing rendered asset:
  `paper-poster-compose` or `paper-asset-select`;
- duplicated bands, unsafe geometry, or missing comparison context:
  `paper-experimental-results`;
- sparse metric count, mixed-but-truthful contexts, or missing large-table
  focus crop: warning from `paper-experimental-results`/`paper-asset-select`;
- stretching, upscaling, missing axes/legend, clipped focus tables, or DOM
  overflow: `paper-poster-render`.
