---
name: paper-motivation-contributions
description: Generate and audit Poster Motivation and Contributions from PaperIR, Storyline, Claim-Evidence, and MethodGraph artifacts. Use before poster composition to recover an adaptive, evidence-backed Motivation problem chain across method, theory, clinical, benchmark, and application papers, preserve one to four canonical and independently supported Contributions without fabricating filler, rewrite selected semantics into neutral scan-friendly language, and keep rejected-candidate findings separate from Compose-blocking visible-text defects.
---

# Paper Motivation Contributions

Generate `motivation_spec.json`, `contribution_candidates.json`,
`contribution_spec.json`, `contribution_audit.json`,
`contribution_extraction_diagnostics.json`, `contribution-debug-report.md`,
`contribution-preview.html`,
`motivation_contribution_audit.json`, and
`motivation_contribution_preview.html`. Also persist
`motivation_candidates.json`, `motivation_audit.json`,
`extraction_diagnostics.json`, `motivation-debug-report.md`, and
`motivation-preview.html`. The Motivation-only artifacts must remain usable
even when Contributions has an unrelated audit failure. Do not render the
full Poster here.

## Procedure

1. Retrieve Motivation evidence primarily from the Introduction. Use its
   front, middle, and pre-method transition paragraphs before Abstract,
   Conclusion, or synthesized Related Work verification.
2. Read each Motivation target with the previous/current/next sentence.
   Expand to two sentences on each side inside the same paragraph when
   resolving `this`, `these approaches`, `the former`, or similar references.
3. Split compound statements into problem-side, solution-side, and reported
   effect propositions. Preserve only the problem-side relation for
   Motivation.
4. Represent each Motivation candidate as subject, relation, object,
   condition, consequence, source sentence IDs, and context-window IDs.
   During extraction apply only source recoverability, problem-side
   plausibility, and semantic completeness Gates. Do not reject useful source
   semantics because the source contains citations, quotations, author voice,
   discourse markers, or copied wording.
5. Classify the paper profile and assemble adaptive Motivation coverage.
   Preserve semantic roles as metadata, but fill the reading functions
   `core_problem`, `unresolved_driver`, and `reading_direction` using
   profile-specific family priorities. Do not require every paper to state the
   literal triplet `task challenge -> prior-method limitation -> objective`.
   Try the next independent candidate whenever rewriting fails. Target 3-5
   displayable items. After complete ordered recovery, permit exactly two
   strong independent items with `MOTIVATION_SPARSE_BUT_SUFFICIENT`; never
   duplicate, mechanically split, or import Method content to fabricate a
   third item.
6. If coverage is incomplete, execute the ordered recovery scan defined in
   [generation-policy.md](references/generation-policy.md). Return
   `MOTIVATION_EVIDENCE_INSUFFICIENT` only after recovery is exhausted.
7. Rewrite only selected Motivation semantics into Poster language. Return a
   structured result containing `status`, `visible_text`, `failure_code`,
   `attempts`, and `audit`. Treat citation cleanup, grammar, source-copy, OCR,
   and author-voice failures as rewrite failures, not semantic-candidate
   rejection. Reject vague task restatements and compare each passing rewrite
   with already selected visible items; semantic duplicates must try the next
   candidate instead of filling another slot. Failed, duplicate, or empty
   rewrite results stay in diagnostics and never enter
   `motivation_spec.items`.
8. Discover Contributions from explicit claims in Introduction contribution
   lists, Conclusion summaries, and Abstract novelty statements. Split
   numbered or bulleted lists and split compound claims that coordinate an
   architecture with a separately named module, objective, or loss. Decompose
   each artifact-specific proposition into innovation object, mechanism,
   solved problem, and reported effect. Recover the author's top-level
   contribution groups when a numbered list or explicit key-idea structure
   exists.
9. Assign every Contribution candidate a `canonical_object_id`,
   `canonical_object_name`, `author_contribution_group_id`,
   `parent_object_id`, `component_level`, and `contribution_role`. Merge
   acronym/full-name aliases and cross-section restatements before selection.
   Preserve composite objective identities such as `BCE + MCC Loss`; do not
   collapse them to the first acronym.
10. Use MethodGraph and Method/Theory content to verify claims. Route ordinary
    encoder/decoder stages, upsampling, concatenation, preprocessing, and
    supporting submodules to Method. Route isolated result numbers to Results
    or Highlights. Do not promote every MethodGraph node.
11. Target `primary_method_or_architecture`,
    `primary_innovation_mechanism`, and
    `secondary_independent_contribution` with distinct displayable items.
    Add a fourth only when it supplies independently supported core
    information. Rank candidates by title alignment, author grouping,
    Abstract/Conclusion emphasis, centrality, evidence, and Poster
    explainability; never truncate the source order.
12. Rewrite only verified Contributions. Count an item only when title,
    description, core/evidence/independence Gates, visible audit, and
    `displayable=true` all pass. Return
    one or two verified independent core items with
    `CONTRIBUTION_SPARSE_BUT_SUFFICIENT` after ordered recovery. Return
    `CONTRIBUTION_EVIDENCE_INSUFFICIENT` only when no displayable core
    architecture or innovation mechanism remains. Treat source-copy failure as
    a rewrite problem: try an evidence-preserving paraphrase before replacing
    the candidate. Never invent a third item.
13. Count Motivation only after visible-text audit. An item counts only when it
    is selected, non-empty, rewrite-passed, language-audit-passed,
    traceability-passed, role-separation-passed, and `displayable=true`.
    Block Compose with `MOTIVATION_EVIDENCE_INSUFFICIENT` when fewer than two
    displayable items remain or the hard `core_problem` and
    `unresolved_driver` functions cannot both be filled after ordered
    recovery. Treat a missing third direction item as a warning only after
    recovery proves that no independent evidence remains.

Read [generation-policy.md](references/generation-policy.md) before changing
candidate types, Gates, semantic merging, rewriting, source-copy detection,
visible fields, or audit routing.

```powershell
python scripts/run.py `
  --paper-ir paper_ir.json `
  --story paper_story.json `
  --evidence claim_evidence.json `
  --method-graph method_graph.json `
  --output runs/paper/04-poster
```
