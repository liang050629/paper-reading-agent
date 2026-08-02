# Reading report contract

`reading_report_spec.json` is the human-readable expansion of the validated
analysis graph. It contains metadata, executive summary, storyline,
Motivations, Contributions, method modules, formulas, experimental design,
experimental results, Highlights, Claim–Evidence records, limitations,
Poster coverage, and source index.

Every source record uses:

```json
{
  "block_id": "p3-b19",
  "page": 3,
  "section": "Introduction",
  "bbox": [227, 424, 787, 469],
  "quote": "source wording",
  "figure_ids": [],
  "table_ids": [],
  "equation_ids": []
}
```

The report may quote short source evidence for audit. Summaries and
explanations remain separate from those quotations. Stable PaperIR, Claim,
Figure, Table, Equation, Motivation, Contribution, and method-node IDs must not
be renumbered.
