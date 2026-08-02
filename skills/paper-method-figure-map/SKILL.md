---
name: paper-method-figure-map
description: Classify every paper figure by semantic role and map method overview, method-module, mechanism, and method-internal mechanism-analysis figures to sourced method nodes. Use when building a reader-first Method panel that must distinguish architecture and internal feature explanations from experimental results, qualitative comparisons, ablations, and dataset examples.
---

# Paper Method Figure Map

Build a coverage matrix between original paper figures and method modules.

## Workflow

1. Inspect every caption, surrounding paragraph, section, citing sentence,
   and text embedded inside the figure's source-PDF bbox.
2. Assign one primary semantic role and separate it from Poster-zone
   eligibility. Use `mechanism_analysis` for attention maps, feature maps, or
   internal responses that explain a sourced proposed module without measured
   baseline evidence.
3. Mark result, qualitative, ablation, and dataset figures as Method-ineligible.
   Strong metric, axis, percentage, and measured-comparison evidence inside
   the image overrides a conflicting Method caption or reference.
   Do not treat `attention map`, `feature map`, or `visualization` alone as
   strong Result evidence.
4. Map eligible figures to method node IDs with reasons and confidence.
5. Rank overview candidates by semantic completeness and primary-method
   evidence. Prefer the final or experimentally adopted method variant over
   earlier auxiliary variants. Never break a semantic tie by figure number or
   document order; return an ambiguity failure instead.
6. Preserve the whole overview image; do not crop subfigures in this stage.
7. Persist a role evidence ledger, Method-reference strength, visual-content
   signals, Poster eligibility, caption-content consistency, and resolved
   mismatch reasons. Final QA must reject any inconsistent asset that still
   enters Method.

Read [role-policy.md](references/role-policy.md) before changing exclusions.
Return an empty method-asset list rather than filling Method with a result.

```powershell
python scripts/run.py --paper-ir paper_ir.json --method-graph method_graph.json --catalog asset_catalog.json --output runs/paper/03-assets
```
