# Motivation and Contributions Policy

## Pipeline

Use this order:

`source retrieval -> contextual proposition extraction -> role classification
-> coverage assembly -> final semantic validation -> Poster rewrite ->
visible-text cleanup -> final selected-item audit`.

## Motivation

Target 3-5 independent problem-side items. Keep these semantic roles as
descriptive metadata, not as a universal writing template:

- `task_problem_or_challenge`
- `prior_method_limitation`
- `gap_requirement_or_objective`

Classify the paper as a method, theory, clinical, benchmark, or application
paper. Fill three reading functions with profile-specific priorities:

- `core_problem`
- `unresolved_driver`
- `reading_direction`

Any function may use a problem/significance, unresolved-gap/constraint, or
need/objective family when the source semantics support it. Do not require a
literal task-challenge, prior-method-limitation, and objective triplet.

After complete ordered recovery, permit two independent displayable items when
no third evidence unit survives semantic and language audits. Mark this
`MOTIVATION_SPARSE_BUT_SUFFICIENT` and let the Renderer enlarge the two cards.
Do not invent, duplicate, mechanically split evidence, or borrow Method content
to reach three. Fewer than two items remains
`MOTIVATION_EVIDENCE_INSUFFICIENT`.

### Retrieval and contextual extraction

Scan sources in this order:

1. Introduction front: problem importance and task/data challenges.
2. Introduction middle: prior method families and limitations.
3. Last Introduction paragraph before Method: unresolved gap or objective.
4. Abstract front half for supplementation and verification.
5. Conclusion for problem/objective confirmation.
6. Related Work only for a method-family limitation synthesis.

Read the previous, current, and next sentence. Expand to two sentences per side
inside the same paragraph for cross-sentence references. Resolve the problem
subject, prior method family, limitation relation, missing capability,
condition, and consequence before classification.

Split compound sentences into problem-side, solution-side, and optional
reported-effect propositions. A sentence containing `We propose` is not
discarded when an independent problem proposition can be recovered.

Each candidate must contain:

```json
{
  "subject": "",
  "relation": "",
  "object": "",
  "condition": "",
  "consequence": "",
  "role": "",
  "source_sentence_ids": [],
  "context_window_ids": []
}
```

Allowed relations are:

- `problem_has_consequence`
- `task_is_difficult_under_condition`
- `data_contains_challenge`
- `prior_method_lacks_capability`
- `prior_method_causes_failure`
- `tradeoff_remains_unresolved`
- `research_gap_remains`
- `solution_requires_capability`
- `paper_targets_problem`

Apply only these hard Gates during extraction:

- `source_recoverability_gate`
- `problem_side_plausibility_gate`
- `semantic_completeness_gate`

Do not apply visible-text standards to raw candidates. Citations, author voice,
discourse markers, quotation marks, long wording, and direct source overlap are
allowed in source evidence.

### Adaptive coverage assembly

Apply `core_relevance_gate`, `specificity_gate`, `independence_gate`,
`scope_gate`, and `role_coverage_gate` before final selection. Build
quality-ranked candidate queues for the three reading functions, using the
paper profile to prioritize semantic families. Try candidates in order,
rewrite each candidate, and complete a slot only when the resulting item is
displayable. A failed first candidate must be replaced by the next compatible
candidate before recovery begins. Do not choose the five highest scores without
coverage balancing. After rewriting, compare the visible semantics with items
already selected. Reject paraphrased duplicates, including generic
`Effective methods must address ...` restatements of an existing challenge,
and continue through the same slot queue.

When the three reading functions are not covered, execute:

1. Rescan the first 30% of Introduction.
2. Rescan the Introduction middle.
3. Scan the last pre-method Introduction paragraph.
4. Check the Abstract front half.
5. Re-split compound clauses.
6. Expand unresolved reference context.
7. Recheck candidates carrying citations or author voice.
8. Check for over-merging.
9. Recheck whether the paper objective was mislabeled as a Contribution.

After all recovery steps, pass normally with 3-5 items. Pass with the sparse
warning when exactly two independent items fill `core_problem` and
`unresolved_driver` but no defensible `reading_direction` remains. Return
`MOTIVATION_EVIDENCE_INSUFFICIENT` only when fewer than two displayable items
remain or either hard function is empty.

### Poster rewrite

Only selected candidates enter Poster rewrite. Remove citations, quotations,
author voice, discourse markers, source copying, OCR/HTML/LaTeX residue, and
grammar defects here. A source-copy failure requests another rewrite; it does
not invalidate the selected problem proposition. Preserve the structured
relation and provenance even when rewriting fails.

The rewrite contract is:

```json
{
  "status": "passed | failed",
  "visible_text": "",
  "failure_code": null,
  "attempts": [],
  "audit": {}
}
```

Try relation-based rewriting, syntax restructuring, source-copy-aware
rewriting, and evidence-preserving neutral rewriting in that order. Normalize
relations before sentence generation; never splice raw `limited`,
`limitation`, or `limits` tokens into a fixed template.

Poster-visible Motivation uses one complete, neutral statement per item,
preferably 12-24 English words.

Reject a visible sentence when it merely restates the task name, contains an
unresolved `this/these` reference, combines malformed relation fragments, or
duplicates a selected item under different wording. These failures affect the
rewrite result, not the validity of the underlying sourced proposition.

### Final displayability invariant

Only items satisfying every condition below may appear in
`motivation_spec.items` or count toward the adaptive item requirement:

- `selected=true`
- non-empty `visible_text`
- `rewrite_status=passed`
- `language_audit_status=passed`
- `traceability_status=passed`
- `role_separation_status=passed`
- `displayable=true`

Empty and exhausted candidates remain only in the candidate ledger, audit, and
debug report. Optional-item rewrite failure is recorded but does not block
Compose. Hard-function failure triggers candidate replacement and ordered
coverage recovery. A two-item result is valid only after recovery is exhausted
and must carry the sparse warning.

The older semantic types remain valid metadata:

- `problem_significance`
- `practical_need`
- `task_challenge`
- `data_challenge`
- `prior_method_limitation`
- `unresolved_gap`
- `design_requirement`

Parameter growth, training-resource demand, inference memory, deployment
burden, and constrained-resource underperformance are valid problem-side
limitations when the source describes the prior method family rather than the
paper's own result. Positive method effects such as reducing overhead are not
Motivation.

## Contributions

Use `explicit retrieval -> semantic decomposition -> canonical object
normalization -> author contribution grouping -> Method/content binding ->
duplicate merging -> parent/child routing -> core ranking -> role-aware final
selection -> Poster rewrite -> visible-text audit`.

Discover candidates from Introduction contribution lists, Conclusion
summaries, and Abstract novelty statements. MethodGraph and Method/Theory
content verify candidates; they do not automatically create Contributions.

Split each paragraph into sentences before splitting numbered groups so
separate limitation and innovation enumerations in one paragraph cannot be
mixed. Split inline `(1) ...; and (2) ...` contribution groups and coordinated
claims such as `architecture ... and adopts ... loss` into artifact-specific
propositions. Bind every proposition back to the complete source sentence.

Keep solution-side units that identify an innovation object, its mechanism,
and its purpose. Canonical types are architecture, module, mechanism,
algorithm, objective/loss, scoring/selection criterion, optimization/training,
representation, fusion, theory, dataset, benchmark, evaluation protocol,
system/tool, and independent empirical finding.

Require novelty, centrality, specificity, Method support, evidence,
independence, and result separation. A performance number, broad effectiveness
claim, common unmodified component, or contribution-list number is not a
Contribution.

Every candidate must also pass source, contribution-identity,
novelty-claim, method-or-content-support, problem-alignment, scope,
evidence-consistency, factual-accuracy, Poster-relevance, and semantic-role
Gates. The semantic-role Gate explicitly rejects section labels such as
Motivation, Background, Overview, Experimental Setup, Results, Discussion,
Conclusion, and References. Explicit author claims are matched back to a
Method/content node; unmatched claims remain rejected candidates.

Split reported effects from innovation semantics. Route isolated performance
claims to Results/Highlights and keep them in the candidate ledger as
`result_only_candidate`. Preserve unmatched author claims as
`unsupported_explicit_claim`.

### Canonical grouping and routing

Assign every candidate:

```json
{
  "canonical_object_id": "",
  "canonical_object_name": "",
  "author_contribution_group_id": "",
  "parent_object_id": null,
  "component_level": "",
  "contribution_role": ""
}
```

Allowed component levels are `overall_architecture`, `primary_mechanism`,
`secondary_mechanism`, `objective_or_algorithm`, `theory`,
`dataset_or_protocol`, `empirical_validation`, `supporting_submodule`, and
`implementation_step`.

Use explicit author contribution lists or key-idea enumerations as top-level
groups. Map Abstract, Introduction, Method, and Conclusion restatements into
the same group. Normalize acronym/full-name pairs, case changes, suffix
changes, and descriptive appositives into one canonical object. One canonical
object may appear only once in the final Poster.

Keep composite objective names intact. Multiple named loss terms in one
verified objective, such as BCE and MCC, form one composite loss identity
rather than being canonicalized to the first acronym.

Route ordinary stage counts, standard encoder/decoder operations, skip
connections, upsampling, concatenation, preprocessing, and internal
supporting blocks to Method. Route isolated metrics and performance claims to
Results or Highlights. A MethodGraph node is evidence, not automatic
Contribution eligibility.

### Final adaptive 1-4 item invariant

Final Contributions target three or four displayable items. The preferred
roles are:

- `primary_method_or_architecture`
- `primary_innovation_mechanism`
- `secondary_independent_contribution`

Fill roles with distinct canonical objects. Permit an architecture and an
independent child mechanism to coexist only when the child has its own
mechanism, purpose, evidence, and incremental information. Do not count an
architecture together with its ordinary implementation steps.

Select a fourth item only when it is author-emphasized or strongly central,
independently supported, and adds information absent from the first three.
When more than four candidates qualify, rank by title alignment, author
grouping, Abstract/Conclusion emphasis, method centrality, independent
evidence, problem distinction, and Poster explainability. Never take the first
four by source order.

When fewer than three roles remain, recheck the author list, Introduction
ending, Conclusion, Abstract novelty, over-merging, Method objectives/theory/
protocols, and author-declared systematic validation. A systematic empirical
validation may fill the third or fourth role only when it spans multiple
datasets, tasks, modalities, or settings and the author presents it as a
contribution. After recovery, preserve one or two independently verified core
items and mark `CONTRIBUTION_SPARSE_BUT_SUFFICIENT`; do not clear the entire
spec because a third role is absent. Return
`CONTRIBUTION_EVIDENCE_INSUFFICIENT` only when no displayable core
architecture or innovation mechanism remains.

Count only items with non-empty title and description, passed core,
independence, evidence, and visible-text audits, and `displayable=true`.
`contribution_spec.items` must contain only the final one to four items.
Persist author groups, canonical groups, merged candidates, Method/Results
routing ledgers, rejected candidates, displayable count, and quality status.

## Semantic merging

Merge aliases, exact parent/child restatements of one innovation, and repeated
Abstract/Introduction/Conclusion descriptions when they bind the same Method
node or have strong object and meaning overlap. Preserve the most precise
object, mechanism, purpose, all source records, and all merged IDs.

Do not merge separate global/local mechanisms, architecture/loss pairs,
architecture/independently defined child-module pairs, theory/algorithm pairs,
dataset/model pairs, or method/finding pairs.

For Motivation, semantic identity is not determined by the assigned type
alone. Merge `task_challenge`, `data_challenge`,
`prior_method_limitation`, or `unresolved_gap` candidates across types only
when narrow topic evidence and rewritten-meaning overlap show that they
describe the same problem. A shared broad word such as `image`, `target`,
`vessel`, or `scale` is insufficient. Preserve independent causes, operating
conditions, and method-family limitations as separate items.

## Visible language

Motivation uses one complete problem statement per item, preferably 12-24
English words. Contributions use a 2-6 word title and an 8-20 word
description. These are soft budgets; evidence-preserving completeness wins.

Visible text must not contain paper narration, citations, author-year markers,
quotation marks, figure/table/section references, HTML, LaTeX commands,
superscripts, footnotes, OCR corruption, or incomplete clauses.

Reject mechanically spliced templates such as `X makes Y difficult` when X or
Y is itself a clause, repeated adverbs such as `reliably adequately`, generic
placeholders such as `target application`, and discourse fragments such as
`Thus`, `Nonetheless`, or `Clinically`. Prefer direct subject-verb-object
relations recovered from the source sentence. Merge problem statements with
strongly overlapping challenge topics even when their surface wording differs.

Use relation-specific rewrites for causal, limitation, visibility,
resource-cost, and practical-use statements. Reject positive capability
sentences such as `aims to exploit`, `can theoretically capture`, or `stands
out due to` when they are misclassified as challenges. If neither a reliable
relation rewrite nor a complete evidence-preserving neutral sentence can be
formed, reject the candidate through `language_rewrite_gate`; do not emit a
generic fallback such as `complicates the task`, `remains difficult under real
task conditions`, or `practical use depends on`.

Reject more than eight consecutive words copied from any bound raw statement,
excluding protected formal names. Reorganize syntax and meaning; do not merely
delete `We propose` or replace isolated synonyms.

## Audit

Run and persist:

- `citation_artifact_check`
- `quotation_marker_check`
- `author_voice_check`
- `discourse_marker_check`
- `source_copy_check`
- `ocr_cleanup_check`
- `motivation_language_quality_check`
- `role_separation_check`
- `traceability_check`
- `semantic_independence_check`
- `semantic_completeness_check`
- `unsupported_expansion_check`

Run visible-text checks only against selected final items. A selected-item
failure blocks Compose and returns to Poster rewrite or this Skill. A rejected
candidate's failures belong only in the candidate ledger and never block
Compose.

Expose:

```json
{
  "selected_item_blockers": [],
  "rejected_candidate_findings": [],
  "warnings": [],
  "quality_status": ""
}
```

Persist `extraction_diagnostics.json` with Introduction and Abstract block
counts, scanned-block summaries, raw and problem-side candidate counts,
post-semantic-Gate and post-merge counts, selected count, rejection
histogram, required role coverage, recovery traces, rewrite failures, and
remaining blockers.

Persist the complete candidate ledger, `motivation_audit.json`,
`motivation-debug-report.md`, `motivation-preview.html`, and the existing
Contribution-only audit. The debug report records every context window,
relation, role, Gate result, rejection, merge, slot winner, recovery step,
rewrite attempt, final text, and source record. Empty output is not a
successful audit when recoverable problem-side or solution-side evidence
exists.
