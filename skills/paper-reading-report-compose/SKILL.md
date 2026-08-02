---
name: paper-reading-report-compose
description: Build a detailed, evidence-traceable reading report from validated PaperIR, storyline, method graph, Claim–Evidence, asset, and Poster artifacts. Use after paper analysis or Poster generation when the user wants structured reading notes with page, section, block, bbox, figure, table, equation, Claim, and experiment links.
---

# Paper Reading Report Compose

Create the long-form reading artifact that complements the Poster. Do not
summarize the Poster image. Read the validated upstream JSON artifacts and
preserve their stable IDs.

## Workflow

1. Require `paper_ir.json`, `paper_story.json`, `method_graph.json`, and
   `claim_evidence.json`.
2. Reuse Poster-branch artifacts when available, including Motivation,
   Contributions, Key Idea, Experimental Results, Highlights, method figures,
   and `poster_spec.json`.
3. Build `reading_report_spec.json` and `source_index.json`.
4. Expand every Poster item into a sourced report entry.
5. Keep `inferred` labels. Never present an unsupported inference as fact.

## Content contract

Include:

- executive summary and complete paper storyline;
- validated Motivation and Contributions;
- ordered method modules with linked original figures;
- every extracted equation with page, bbox, crop or LaTeX, context, and core
  equation status;
- experimental design, contextual metrics, result assets, and Highlights;
- Claim–Evidence verdicts, support blocks, and caveats;
- limitations and a complete source index;
- Poster-to-report coverage mappings.

Every factual entry must bind at least one source block or a source asset with
page and bbox. Read [report-contract.md](references/report-contract.md) before
changing the output shape.

## Run

```powershell
python scripts/run.py --run-dir D:\path\to\completed-poster-run
```
