---
name: paper-method-graph
description: Reconstruct a research paper's evidence-grounded method modules, innovation points, and reading order from PaperIR. Use when an academic-paper reader or poster must explain how a method works before selecting visuals, including papers whose method section is named after the proposed model instead of Method.
---

# Paper Method Graph

Recover the method's explanatory structure before composing a Poster.

## Workflow

1. Read Method text, relevant Introduction contributions, headings, and source
   coordinates.
2. Identify explicit stages or method subsections.
3. Create one node per genuine module or innovation point.
4. Preserve the paper's explicit sequence. Otherwise use documented section
   order and label the edge accordingly.
5. Attach source blocks to every node and edge.
6. Keep results, ablations, datasets, and performance claims outside the graph.

Read [graph-contract.md](references/graph-contract.md) before changing node or
edge semantics. Do not invent a data-flow edge when the paper only provides an
exposition order.

```powershell
python scripts/run.py --paper-ir paper_ir.json --output runs/paper/02-analysis
```
