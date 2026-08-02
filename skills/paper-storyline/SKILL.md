---
name: paper-storyline
description: Extract an evidence-grounded research storyline from PaperIR, including problem, motivation, prior gap, hypothesis, method, theory or mechanism, experimental design, results, conclusion, and limitations. Use when a user asks to understand a paper's logic, prepare a poster, or produce structured paper analysis with citations to exact source blocks.
---

# Paper Storyline

Read the complete paper before finalizing a storyline. Use the offline script
only as a scaffold; refine it with the agent's full-paper reasoning.

## Extraction rules

1. Extract the ten required story nodes.
2. Mark each node `explicit`, `inferred`, `not_found`, or `conflicted`.
3. Attach source block IDs, pages, coordinates, and short quotes.
4. Separate author claims from reviewer interpretation.
5. Do not invent a hypothesis or mechanism when the paper does not state one.
6. Extract major contribution and result claims as separate records.

Read [analysis-rubric.md](references/analysis-rubric.md) before refining the
offline result.

## Run the scaffold

```powershell
python scripts/run.py --paper-ir paper_ir.json --output runs/paper/02-analysis
```

Validate every non-`not_found` node has at least one source before handing the
artifact to the evidence auditor.

