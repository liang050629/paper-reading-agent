# Highlights Policy

## Purpose

Treat Highlights as the Poster's five-second memory area. Select one to three
results that are important, strongly evidenced, context-complete, and
independently traceable. Do not rank by numeric magnitude, author emphasis, or
empty layout space.

## Allowed candidate sources

Use only:

- a core quantitative result in the Abstract;
- a main result table or chart;
- a result repeated in the Conclusion;
- a core Claim with `verdict=supported` in the Claim-Evidence Matrix;
- an independent efficiency, generalization, or robustness experiment.

Reject candidates derived only from Related Work, experiment settings,
ordinary hyperparameters, module numbering, contribution numbering, or an
ablation that substitutes for the full model's main result.

## Seven hard Gates

Every selected candidate must pass:

1. `traceability_gate`: bind a table or figure, page, source blocks, and exact
   source and baseline row/column cells.
2. `context_gate`: provide value, metric, dataset, configuration, baseline,
   evaluation condition, baseline value, and metric direction.
3. `matched_comparison_gate`: use the same dataset, split, metric, protocol,
   fine-tuning condition, recovery condition, and comparable configuration.
   Proposed and baseline method/loss configurations may differ, but both must
   be explicit and all evaluation conditions must match.
   A footnote-decorated variant must use the exact undecorated row with the
   same normalized backbone label as its baseline. Footnote markers never
   authorize cross-backbone comparison.
4. `arithmetic_gate`: recompute absolute and relative differences from source
   values; distinguish percentage points from relative percent.
5. `claim_alignment_gate`: directly support a core Claim and reject
   contribution-number prose. Explicit Claim metrics and datasets are hard
   constraints: for example, an ADE20K mIoU Claim cannot bind an ImageNet
   Top-1 result. When a Claim states only broad performance improvement, the
   main quality metric may be considered without importing unrelated metric
   names from surrounding evidence blocks.
6. `representativeness_gate`: keep the conclusion within the supported dataset
   scope; require at least two consistent datasets for broad consistency
   language.
7. `caveat_gate`: retain every condition that changes interpretation.

Gate failure always overrides a high score.

When an extracted table field is a placeholder, recover context in this
order: bound Claim, asset caption, bound source blocks. The Claim's explicit
dataset and caveat, such as `DRIVE without FOV`, override other datasets
mentioned in neighboring prose. If no evidence-backed dataset or condition can
be recovered, keep the Gate failed; never substitute an unrelated dataset.

## Weighted score

Score each dimension from 0 to 5 and convert to a 0-100 weighted total:

| Dimension | Weight |
|---|---:|
| `claim_relevance` | 30% |
| `evidence_strength` | 20% |
| `comparison_fairness` | 20% |
| `practical_significance` | 15% |
| `representativeness` | 10% |
| `memorability` | 5% |

Classify:

- 85-100: `strong_highlight`;
- 75-84: `eligible_highlight`;
- 60-74: `results_only`;
- below 60: `reject`.

Apply these deductions:

- single favorable dataset with inconsistent remaining evidence: -10;
- ablation-only evidence: -10;
- non-strong baseline: -15;
- fine-tuning or recovery mismatch: -20 and Gate failure;
- conflicting experimental trend: -15;
- unverified significance language: -15;
- unclear unit or percentage scale: reject through the arithmetic Gate.

## Final selection

Select at most one item for each preferred role:

1. `primary_effectiveness`;
2. `improvement_over_baseline`;
3. `efficiency_or_generalization_or_robustness`.

Reject semantic duplicates with the same metric, dataset, configuration, and
Claim category. Do not select three cards that all restate one dataset-metric
comparison. One to three cards are valid. Zero cards produce the warning
`HIGHLIGHT_EVIDENCE_INSUFFICIENT` after the recovery pass. Compose must omit
the optional cards and retain Experimental Results instead of fabricating a
weak Highlight.

Canonicalize superficial dataset wording before this check. Articles,
`dataset`, and `benchmark` suffixes do not make `the ImageNet-1k dataset` a
different scope from `ImageNet-1k`.

Treat Params, FLOPs, latency, runtime, throughput, and memory as efficiency
evidence regardless of which table contains them. They cannot displace the
main effectiveness result. A zero-difference efficiency value may communicate
`No extra parameters` or another preserved-budget constraint only when the
bound Claim explicitly requires unchanged overhead; never label it as a gain.

## Required output fields

Each selected Highlight must preserve:

- `primary_value`, `label`, and `context`;
- `claim_id`, `evidence_id`, `claim_verdict`, and `claim_text`;
- source asset type and ID, page, source row/column, and baseline cells;
- dataset, configuration, baseline, metric, metric direction, and evaluation
  condition;
- absolute difference, difference type, and relative difference percent;
- source block IDs, Gate results, weighted scores, penalties, and caveats;
- dataset count and trend-consistency status.

The enclosing specification records candidate counts, rejected candidates, the
minimum score, maximum item count, and disabled magnitude/emphasis/layout
priors.

## Display budget

- `primary_value`: a number or at most four English words;
- `label`: at most six English words;
- `context`: at most ten English words.

Render exactly the number of qualified cards. Expand one or two cards instead
of inserting a fallback result.

## Validation and routing

Reject:

- an item below score 75;
- any failed hard Gate;
- missing provenance or comparison context;
- a value that cannot be recovered from its exact source table cell;
- arithmetic that differs from recomputation;
- semantic duplication;
- broad consistency language supported by only one dataset.

Route failures created by this stage to `paper-highlights`. Route unsupported
Claims to `paper-evidence-audit`, incorrect result assets or extracted metrics
to `paper-experimental-results`, and missing source geometry/content to
`paper-ingest`.
