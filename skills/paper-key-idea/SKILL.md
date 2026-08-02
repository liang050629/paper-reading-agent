---
name: paper-key-idea
description: Identify and specify the central differentiating insight of a research paper for a poster, choosing formula-, contrast-, mechanism-, architecture-, or finding-centered presentation with evidence bindings and optional original equation crops. Use after storyline, claim-evidence, method-graph, and method-figure analysis whenever a poster Key Idea must be generated, revised, or audited without defaulting to a formula or repeating Method Overview.
---

# Paper Key Idea

Generate `key_idea_spec.json`; do not render HTML in this stage.

## Procedure

1. Read the title, abstract, Introduction gap, stated contributions, repeated
   method mechanisms, theory/definitions, and ablation or analysis evidence.
2. Choose exactly one primary type:
   `formula_centered`, `contrast_centered`, `mechanism_centered`,
   `architecture_centered`, or `finding_centered`.
3. Bind the insight to real ClaimEvidence IDs and PaperIR block IDs. Mark
   inferred content explicitly.
4. Create a 15–25-word headline, one adaptive visual, an optional equation
   with one explanation, and one takeaway. Keep visible text to 60–120 words.
5. Score every equation on novelty, centrality, necessity, downstream usage,
   validation, and poster explainability. Each dimension is 0–2.
6. Select no equation unless it reaches 7 points and is not a generic
   loss/metric. Use `equation=null` semantics through `display_mode: none`.
7. Apply `equation_key_idea_alignment_gate`. A mechanism-centered equation
   requires centrality=2 plus strong downstream use, validation, or binding to
   a primary Method module. Reject routine training losses even when their raw
   score reaches the numerical threshold.
8. Prefer the original equation crop and preserve page, bbox, ID, and file
   hash. Never print raw LaTeX in HTML; use `display_mode: none` when no
   deterministic equation rendering asset is available.
9. Never reuse the complete Method Overview asset in Key Idea.
10. Select the visual template from the number of independent, source-bound
   items: one item uses a full-size focus template, two use a split template,
   three use a three-step flow, and four use a grid. Do not invent items merely
   to satisfy a template.
11. Generate visual text through proposition recovery, semantic
    normalization, concise rewriting, and sentence-completeness audit. Do not
    truncate source text at an arbitrary word boundary. Exclude ordinary
    Encoder/Decoder stages that do not express the differentiating insight.
12. Keep raw LaTeX only in `equation.latex`. Headline, labels, visual text,
    equation explanation, takeaway, and inference label must be complete,
    plain natural language without math delimiters, LaTeX commands, raw
    scripts, source cross-references, or unresolved references.
13. When `equation=null`, re-plan the visual before rendering. A single
    evidence-backed mechanism is valid when `single_mechanism_focus` fills the
    visual region.
14. Allow `passed` and `passed_with_warnings` into formal Compose. Headline
    length, soft word-budget variance, and imperfect no-equation space use are
    warnings when visible text remains complete and source-bound. A failed
    report may create only an HTML debug preview marked
    `data-preview-status=invalid`; do not export a formal Poster PNG or PDF.

Read [key-idea-policy.md](references/key-idea-policy.md) before changing type,
equation, word-budget, provenance, or no-equation rules.

```powershell
python scripts/run.py --paper-ir paper_ir.json --story paper_story.json --evidence claim_evidence.json --method-graph method_graph.json --method-figure-map method_figure_map.json --output runs/paper/04-poster
```
