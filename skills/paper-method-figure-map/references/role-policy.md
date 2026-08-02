# Figure role policy

Method-eligible roles:

- `method_overview`
- `method_module`
- `mechanism`
- `mechanism_analysis`

`mechanism_analysis` covers method-internal attention maps, activation or
feature responses, and branch visualizations when they explain a sourced
module and do not contain a measured baseline comparison. It is eligible for
Method Details, never Method Overview. It may also be eligible as secondary
analysis evidence, but the Poster planner must choose one preferred zone.

Always exclude from Method:

- `experimental_result`
- `qualitative_result`
- `ablation`
- `dataset_example`

Use caption, context, section, citing sentences, and source-PDF text inside the
figure bbox. Never use the figure number as a semantic prior. Treat metric
names, axes, repeated numeric ticks, percentages, baseline/Ours labels, and
measured costs as strong result evidence. This evidence overrides a noisy
Method reference or mismatched caption and excludes the asset from Method.
Attention-map, feature-map, heatmap, and visualization words are boundary
signals, not hard Result evidence. Combine them with Method-reference,
operation-flow, baseline, ground-truth, metric, and section evidence before
assigning a role.
Record `visual_content_signals`, `caption_content_consistent`, mismatch
reasons, `poster_eligibility`, `preferred_zone`, and resolved reference
conflicts. A strong complete overview may
cover module labels visible inside the image even when its short caption omits
them; record this as overview-semantic coverage.
