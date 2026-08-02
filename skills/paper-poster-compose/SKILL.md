---
name: paper-poster-compose
description: Convert a sourced paper storyline, claim-evidence matrix, and selected original assets into a compact AMP-style poster specification. Use when planning poster content, enforcing word and visual budgets, mapping evidence to panels, or revising content after completeness or overflow failures.
---

# Paper Poster Compose

Plan content; do not render HTML in this stage.

## AMP mapping

- Motivation: render every validated item from `motivation_spec.json`; do not
  reuse Storyline source sentences or add layout fillers.
- Method Overview: verified overview asset or explicit fallback.
- Key Idea: render the validated `key_idea_spec.json`; do not substitute a
  generic hypothesis/mechanism block or add equations not selected there.
- Method Detail: render `method_visual_plan.json`; keep the whole overview in
  Method Overview and include only non-redundant method-module figures below.
  Put datasets, baselines, metrics, and protocol in a secondary strip.
- Experimental Results: render the validated
  `experimental_results_spec.json`; do not substitute a chapter summary,
  select by figure/table number, or introduce unverified numbers.
- Contributions: render every validated independent item from
  `contribution_spec.json`; do not truncate by compact level or substitute
  result Claims.
- Highlights: up to four source-verified numbers.
- Project: a compact code-availability panel. Show a verified repository URL
  when available; otherwise state `Code not publicly available`.

Keep conclusion and limitations in the machine-readable storyline. Do not
allocate the bottom-right poster panel to them unless the user explicitly asks.
Keep poster sentences complete. Reduce the number of items or adjust layout
instead of inserting layout-generated ellipses.

Read [amp-layout.md](references/amp-layout.md) before changing panel budgets.
Do not include an unsupported claim as a contribution or headline.
Do not add a result, qualitative, ablation, or dataset figure to Method.

```powershell
python scripts/run.py --paper-ir paper_ir.json --story paper_story.json --evidence claim_evidence.json --assets selected_assets.json --method-graph method_graph.json --method-visual method_visual_plan.json --key-idea key_idea_spec.json --experimental-results experimental_results_spec.json --highlights highlights_spec.json --motivation motivation_spec.json --contributions contribution_spec.json --output runs/paper/04-poster
```
