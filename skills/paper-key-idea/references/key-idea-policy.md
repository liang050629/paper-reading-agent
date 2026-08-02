# Key Idea policy

## Type decision

Select one type from evidence, never from a fixed template:

- `formula_centered`: a 9–12-point equation is itself the main innovation.
- `contrast_centered`: the insight is best explained as Existing vs. Ours.
- `mechanism_centered`: a repeated mechanism or interaction explains the gain.
- `architecture_centered`: the novel relationship among specialized modules is central.
- `finding_centered`: the main contribution is a theoretical or experimental finding.

Formula-centered has no default priority. Prefer the highest evidence score;
resolve ties by mechanism, contrast, architecture, finding, then formula.

## Equation scoring

Score 0–2 for each:

1. novelty;
2. centrality;
3. necessity;
4. downstream usage;
5. theoretical, analytical, or ablation validation;
6. poster explainability.

Interpret totals:

- 9–12: primary Key Idea equation;
- 7–8: optional supporting Key Idea equation;
- 4–6: Method Details only;
- 0–3: omit.

Reject or heavily downweight generic cross-entropy, Dice, MSE, metrics, routine
problem definitions, implementation-only equations, unrelated recovery
equations, long prerequisite-heavy derivations, and unsupported formulas.
Normalize OCR-spaced names such as `d i c e` and `c e` before applying the
generic-equation gate. Generic status is blocking and cannot be overridden by
the numerical score.

## Equation alignment

Apply `equation_key_idea_alignment_gate` after selecting the Key Idea type.

For `mechanism_centered`:

- the equation must express the selected module computation or mechanism;
- centrality must equal 2;
- downstream usage=2, validation=2, or a direct primary-Method binding must
  also be present;
- routine training losses are never aligned with an unrelated mechanism.

When alignment fails, set the equation to `display_mode: none`, clear the
plain-language explanation, and re-plan the visual without an equation slot.

## Crop contract

Prefer `original_crop`. Retain `equation_id`, `page`, `bbox`, source-relative
`image_path`, and SHA-256. Require a non-pending crop, valid bbox, unchanged
aspect ratio (`object-fit: contain`), and a natural-language explanation.

Do not print raw LaTeX into ordinary HTML. Until a deterministic MathJax/KaTeX
runtime is bundled and verified, use `display_mode: none` when the original
crop is unavailable.

## Visible-text contract

Only `equation.latex` may retain source LaTeX. These visible fields must be
plain natural language:

- `headline`;
- `visual.items[].label`;
- `visual.items[].text`;
- `equation.plain_language_explanation`;
- `takeaway`;
- `inference_label`.

Run:

1. source proposition recovery;
2. semantic normalization;
3. concise rewrite;
4. LaTeX and delimiter audit;
5. sentence and clause completeness audit;
6. cross-reference and unresolved-reference audit.

Reject dollar math, `\(...\)`, `\[...\]`, LaTeX commands, raw scripts,
unmatched braces or parentheses, equation fragments, and Figure/Table/Section
references. A failed visible field must be rewritten from its bound source
meaning. If rewriting still fails, remove that item and re-plan the visual.
Never remove TeX characters mechanically while retaining a broken clause.

The equation explanation must state the variables' roles, the operation, or
the equation's relation to the Key Idea. It must not reproduce the formula,
start with an incomplete `where` clause, or contain raw notation.

## Visual contract

Never reuse Method Overview. For no-equation layouts:

- contrast: two large Existing/Ours cards;
- mechanism: a one-item focus, two-part mechanism, three-step flow, or
  four-item grid selected from the independent evidence-backed item count;
- architecture: a one-item focus, two-module relationship, or core module
  relationship selected from the independent item count;
- finding: evidence and meaning.

The renderer must expand these visuals instead of reserving an empty equation
slot. Do not split one mechanism into artificial steps merely to fill space.
Ordinary Encoder, Decoder, stage, backbone, or training nodes must not be added
solely to fill a grid.

## Formal-output gate

A specification whose `key_idea_report.status` is `passed` or
`passed_with_warnings` may enter formal Poster Compose. Treat headline length,
soft word-budget variance, and imperfect no-equation space use as warnings
only when provenance and visible-text audits pass. A failed specification may
produce a debug HTML preview marked `data-preview-status=invalid`; it must not
produce the final Poster PNG or PDF.
