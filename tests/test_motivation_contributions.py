from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import paperposter.motivation_contributions as motivation_module
from paperposter.compose import compose_poster
from paperposter.motivation_contributions import (
    AUTHOR_VOICE_RE,
    CITATION_RE,
    CURRENT_WORK_RE,
    RESULT_CLAIM_RE,
    _merge_candidates,
    build_motivation_contributions,
    clean_visible_text,
    generate_motivation_contribution_specs,
    longest_source_overlap,
    rewrite_motivation,
    validate_motivation_contribution_specs,
)
from paperposter.render import _contributions, _motivation


def real_motivation_regressions() -> dict[str, dict]:
    fixture_path = (
        PROJECT_ROOT
        / "tests"
        / "fixtures"
        / "motivation-displayable-regression"
        / "real-papers.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return {paper["name"]: paper for paper in payload["papers"]}


def method_fixture(count: int = 1) -> tuple[dict, dict, dict, dict]:
    definitions = [
        (
            "Global Context Module",
            "long-range attention",
            "capture distant dependencies",
        ),
        (
            "Local Detail Block",
            "multi-scale convolution",
            "preserve fine boundary details",
        ),
        (
            "Adaptive Fusion Strategy",
            "content-aware weighting",
            "combine deep and shallow features",
        ),
        (
            "Boundary Consistency Loss",
            "boundary-aware supervision",
            "reduce contour fragmentation",
        ),
        (
            "Confidence Scoring Criterion",
            "uncertainty-weighted scoring",
            "rank ambiguous predictions",
        ),
    ][:count]
    blocks = [
        {
            "id": "intro-1",
            "type": "paragraph",
            "page": 1,
            "section_id": "introduction",
            "section_title": "Introduction",
            "text": (
                "Thin structures remain difficult to recover in low-contrast "
                "regions because their boundaries are easily confused with background. "
                "Prior segmentation models fail to preserve fine structures and "
                "long-range context. Effective solutions require both boundary "
                "preservation and global contextual modeling."
            ),
        }
    ]
    nodes = []
    for index, (name, mechanism, purpose) in enumerate(definitions, start=1):
        statement = f"We introduce {name} using {mechanism} to {purpose}."
        block = {
            "id": f"method-{index}",
            "type": "paragraph",
            "page": 2 + index,
            "section_id": f"method-{index}",
            "section_title": "Method",
            "text": statement,
        }
        blocks.append(block)
        nodes.append(
            {
                "id": f"method-node-{index}",
                "order": index,
                "name": name,
                "purpose": statement,
                "innovation": statement,
                "section_id": f"method-{index}",
                "section_title": "Method",
                "figure_refs": [f"figure-{index}"],
                "sources": [
                    {
                        "block_id": block["id"],
                        "page": block["page"],
                        "quote": statement,
                    }
                ],
            }
        )
    paper_ir = {
        "schema_version": "1.0.0",
        "paper_id": "motivation-contribution-test",
        "metadata": {
            "title": "Context and Detail Modeling for Thin Structure Segmentation",
            "authors": [],
            "affiliations": [],
        },
        "blocks": blocks,
        "figures": [],
        "equations": [],
        "tables": [],
    }
    story = {
        "research_problem": {
            "summary": "Thin structure segmentation is difficult in low-contrast regions."
        },
        "motivation": {"summary": "Boundaries are easily confused with background."},
        "prior_work_gap": {"summary": "Prior models lose fine structures."},
    }
    evidence = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "claims": [],
    }
    graph = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "nodes": nodes,
        "edges": [],
        "status": "passed",
    }
    return paper_ir, story, evidence, graph


def valid_specs() -> tuple[dict, dict, dict]:
    paper_ir, _, _, _ = method_fixture(1)
    raw_motivation = paper_ir["blocks"][0]["text"]
    raw_contribution = paper_ir["blocks"][1]["text"]
    motivation = {
        "items": [
            {
                "id": "M1",
                "type": "task_challenge",
                "visible_text": "Low contrast makes thin boundary recovery difficult.",
                "normalized_meaning": "low contrast complicates thin boundary recovery",
                "source_block_ids": ["intro-1"],
                "source_records": [
                    {
                        "block_id": "intro-1",
                        "page": 1,
                        "source_section": "Introduction",
                        "raw_statement": raw_motivation,
                    }
                ],
            }
        ]
    }
    contribution = {
        "items": [
            {
                "id": "C1",
                "short_title": "Global Context Module",
                "description": "Uses long-range attention to capture distant dependencies.",
                "visible_text": (
                    "Global Context Module\n"
                    "Uses long-range attention to capture distant dependencies."
                ),
                "contribution_type": "attention_strategy",
                "innovation_object": "Global Context Module",
                "mechanism": "long-range attention",
                "purpose": "capture distant dependencies",
                "source_block_ids": ["method-1"],
                "source_records": [
                    {
                        "block_id": "method-1",
                        "page": 3,
                        "source_section": "Method",
                        "raw_statement": raw_contribution,
                    }
                ],
            }
        ]
    }
    return motivation, contribution, paper_ir


class CleanupTests(unittest.TestCase):
    def test_citation_variants_are_removed(self) -> None:
        value = (
            "Existing methods [19], [1–3], and (Smith et al., 2020) "
            "lose thin structures."
        )
        cleaned = clean_visible_text(value)
        self.assertNotRegex(cleaned, r"\[|\]|Smith|2020")

    def test_superscript_and_footnote_numbers_are_removed(self) -> None:
        cleaned = clean_visible_text(
            "Thin vessels<sup>19</sup> are difficult to recover²."
        )
        self.assertNotIn("19", cleaned)
        self.assertNotIn("²", cleaned)

    def test_quotation_markers_are_removed(self) -> None:
        cleaned = clean_visible_text(
            "“thin vessels”, 《global context》, and 「local detail」 are important."
        )
        self.assertNotRegex(cleaned, r"[“”《》「」]")

    def test_html_latex_and_ocr_residue_are_cleaned(self) -> None:
        cleaned = clean_visible_text(
            "<sup>3</sup> We propose \\text{fusion} &amp; atten-\n"
            "tion \\cite{x} with � artifacts."
        )
        self.assertNotRegex(cleaned, r"<|>|\\text|\\cite|�|atten-")
        self.assertIn("attention", cleaned)

    def test_author_voice_is_nonblocking_but_discourse_is_rejected(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        motivation["items"][0]["visible_text"] = (
            "Firstly, in this paper We propose a new module."
        )
        checks, issues = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["author_voice_check"]["passed"])
        self.assertFalse(checks["discourse_marker_check"]["passed"])
        self.assertTrue(issues)
        self.assertNotIn(
            "AUTHOR_VOICE_CHECK",
            {issue["code"] for issue in issues},
        )

    def test_author_voice_alone_does_not_block_audit(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        contribution["items"][0].update(
            {
                "selected": True,
                "displayable": True,
                "canonical_object_id": "global-context-module",
                "component_level": "primary_mechanism",
                "final_gate_results": {
                    "core_contribution_gate": {"passed": True}
                },
            }
        )
        motivation["items"][0]["visible_text"] = (
            "In this paper we identify low contrast as a boundary recovery challenge."
        )
        checks, issues = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["author_voice_check"]["passed"])
        self.assertFalse(issues)

    def test_named_core_module_is_not_rejected_as_implementation_step(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        contribution["items"][0].update(
            {
                "short_title": "AUCF",
                "innovation_object": "Attention-Based Upsampling Convolution Fusion",
                "visible_text": (
                    "AUCF\nFuses encoder and decoder cues across skip pathways."
                ),
                "description": (
                    "Fuses encoder and decoder cues across skip pathways."
                ),
                "selected": True,
                "displayable": True,
                "canonical_object_id": "aucf",
                "component_level": "primary_mechanism",
                "final_gate_results": {
                    "core_contribution_gate": {"passed": True}
                },
            }
        )
        checks, issues = validate_motivation_contribution_specs(
            motivation,
            contribution,
            paper_ir,
        )
        self.assertTrue(checks["implementation_step_check"]["passed"])
        self.assertNotIn(
            "IMPLEMENTATION_STEP_CHECK",
            {issue["code"] for issue in issues},
        )

    def test_author_contribution_group_can_be_covered_by_source_records(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        contribution["author_contribution_groups"] = [
            {
                "id": "author-contribution-1",
                "canonical_object_name": "sequence of learnable object queries",
                "raw_statement": (
                    "We introduce a sequence of learnable object queries."
                ),
            }
        ]
        contribution["items"][0].update(
            {
                "selected": True,
                "displayable": True,
                "canonical_object_id": "pulling-branch",
                "component_level": "primary_mechanism",
                "final_gate_results": {
                    "core_contribution_gate": {"passed": True}
                },
                "source_records": [
                    {
                        "block_id": "method-1",
                        "page": 3,
                        "source_section": "Method",
                        "raw_statement": (
                            "The pulling branch uses a sequence of learnable "
                            "object queries as clustered centers."
                        ),
                    }
                ],
            }
        )
        checks, issues = validate_motivation_contribution_specs(
            motivation,
            contribution,
            paper_ir,
        )
        self.assertTrue(checks["author_contribution_alignment_check"]["passed"])
        self.assertNotIn(
            "AUTHOR_CONTRIBUTION_ALIGNMENT_CHECK",
            {issue["code"] for issue in issues},
        )


class MotivationRealRegressionFixtureTests(unittest.TestCase):
    def test_frozen_real_motivation_semantics(self) -> None:
        fixture_root = PROJECT_ROOT / "tests" / "fixtures" / "motivation-regression"
        run_root = (
            PROJECT_ROOT.parent
            / "runs"
            / "motivation-validation-implementation-20260731"
        )
        if not run_root.exists():
            self.skipTest("real Motivation validation artifacts are not available")
        for fixture_path in sorted(fixture_root.glob("*.json")):
            expected = json.loads(fixture_path.read_text(encoding="utf-8"))
            spec_path = run_root / expected["paper_id"] / "motivation_spec.json"
            self.assertTrue(spec_path.exists(), spec_path)
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            items = spec.get("items", [])
            self.assertEqual(len(items), expected["item_count"])
            roles = {str(item.get("selection_role") or "") for item in items}
            self.assertTrue(set(expected["required_roles"]).issubset(roles))
            relations = {
                str((item.get("relation_structure") or {}).get("relation") or "")
                for item in items
            }
            self.assertTrue(set(expected["relation_signatures"]).issubset(relations))
            self.assertTrue(
                all(item.get("source_block_ids") for item in items),
                fixture_path.name,
            )
            visible = " ".join(str(item.get("visible_text") or "") for item in items)
            self.assertFalse(CURRENT_WORK_RE.search(visible))
            self.assertFalse(
                re.search(
                    r"(?<!\w)\d+(?:\.\d+)?\s*%|"
                    r"\b(?:outperform(?:s|ed)?|achiev(?:e|es|ed)|"
                    r"state[-\s]?of[-\s]?the[-\s]?art|experimental results?)\b",
                    visible,
                    re.I,
                )
            )
            self.assertFalse(CITATION_RE.search(visible))
            self.assertFalse(AUTHOR_VOICE_RE.search(visible))
            self.assertTrue(
                all(not item.get("rewrite_blockers") for item in items),
                fixture_path.name,
            )

    def test_deleted_marker_does_not_hide_direct_copy(self) -> None:
        raw = (
            "Firstly, thin vessels are easily lost in low contrast retinal "
            "regions during automatic segmentation tasks."
        )
        visible = clean_visible_text(raw)
        self.assertGreater(longest_source_overlap(visible, raw), 8)

    def test_relation_rewrite_avoids_fragment_splicing(self) -> None:
        cases = [
            (
                "Studies have shown that fundus diseases are one of the most "
                "important causes of blindness.",
                "problem_significance",
                "Fundus diseases are a major cause of blindness.",
            ),
            (
                "Complex backgrounds, such as buildings, clouds, or vegetation, "
                "further obscure targets.",
                "task_challenge",
                "Complex backgrounds obscure targets.",
            ),
            (
                "Nonetheless, the computational complexity of global "
                "self-attention grows quadratically with image size, rendering "
                "it inefficient for high-resolution fundus imagery.",
                "task_challenge",
                "Quadratic global self-attention is inefficient for "
                "high-resolution fundus imagery.",
            ),
            (
                "On the other hand, vision transformers exhibit a quadratic "
                "complexity in processing input sequences, which poses "
                "challenges in handling large-sized images.",
                "task_challenge",
                "Quadratic processing input sequences makes large-sized images costly.",
            ),
            (
                "State space models suffer from the limitations of "
                "unidirectional modeling of input data and a lack of spatial "
                "awareness.",
                "prior_method_limitation",
                "State space models are limited by unidirectional modeling of "
                "input data and a lack of spatial awareness.",
            ),
            (
                "Undifferentiated attention integrates substantial background "
                "noise and redundancy, which dilutes the features of thin "
                "vessels and compromises fidelity.",
                "data_challenge",
                "Substantial background noise and redundancy dilute features "
                "of thin vessels.",
            ),
        ]
        for raw, kind, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(rewrite_motivation(raw, kind), expected)

    def test_real_failure_patterns_rewrite_to_complete_english(self) -> None:
        cases = [
            (
                "This local receptive field limitation often leads to "
                "suboptimal performance in regions with complex background "
                "interference, where global semantic understanding is crucial "
                "for distinguishing vessels from complex backgrounds.",
                "task_challenge",
                "Local receptive fields limit vessel-background discrimination "
                "in complex scenes.",
            ),
            (
                "While, attention mechanisms face scalability challenges due "
                "to their quadratic complexity, posing a significant challenge "
                "when addressing large images.",
                "prior_method_limitation",
                "Quadratic attention limits scalability on large images.",
            ),
            (
                "Areas of poor image quality are difficult to distinguish and "
                "can lead to the rupture or missed detection of thin vessels.",
                "data_challenge",
                "Poor image quality obscures thin vessels and increases missed "
                "detections.",
            ),
            (
                "As the infrared radiation received by the camera decreases "
                "with distance, targets often appear dim with low "
                "signal-to-noise ratio and signal-to-clutter ratio, and lack "
                "texture information.",
                "data_challenge",
                "Distant infrared targets have weak contrast and little texture.",
            ),
        ]
        for raw, kind, expected in cases:
            with self.subTest(raw=raw):
                rewritten = rewrite_motivation(raw, kind)
                self.assertEqual(rewritten, expected)
                motivation, contribution, paper_ir = valid_specs()
                motivation["items"][0]["visible_text"] = rewritten
                checks, _ = validate_motivation_contribution_specs(
                    motivation,
                    contribution,
                    paper_ir,
                )
                self.assertTrue(
                    checks["motivation_language_quality_check"]["passed"]
                )

    def test_unreliable_generic_fallback_returns_empty(self) -> None:
        self.assertEqual(
            rewrite_motivation(
                "These issues pose challenges when handling visual data.",
                "task_challenge",
            ),
            "",
        )
        self.assertEqual(
            rewrite_motivation(
                "This endeavor aims to fully exploit powerful modeling "
                "capabilities.",
                "task_challenge",
            ),
            "",
        )

    def test_resource_rewrite_does_not_invent_moe(self) -> None:
        raw = (
            "The comprehensive network is greatly limited by the high "
            "computation cost related to massive back-projections in network "
            "training."
        )
        rewritten = rewrite_motivation(raw, "prior_method_limitation")
        self.assertEqual(
            rewritten,
            "Massive back-projections make network training computationally expensive.",
        )
        self.assertNotIn("MoE", rewritten)

    def test_iterative_cost_does_not_become_large_model_claim(self) -> None:
        raw = (
            "These iterative reconstruction algorithms require a high "
            "computational cost, which is a bottleneck in practical applications."
        )
        rewritten = rewrite_motivation(raw, "prior_method_limitation")
        self.assertEqual(
            rewritten,
            "High computational cost limits practical iterative reconstruction.",
        )
        self.assertNotIn("Large model", rewritten)
        self.assertNotIn("deployment", rewritten.lower())

    def test_fragment_splicing_fallback_is_rejected(self) -> None:
        self.assertEqual(
            rewrite_motivation(
                "With compressive sensing, total variation, dictionary learning, "
                "and other techniques were used for reconstruction.",
                "task_challenge",
            ),
            "",
        )

    def test_unsupported_technical_entity_fails_expansion_check(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        motivation["items"][0]["visible_text"] = (
            "MoE capacity gains require substantially more training resources."
        )
        checks, _ = validate_motivation_contribution_specs(
            motivation,
            contribution,
            paper_ir,
        )
        self.assertFalse(checks["unsupported_expansion_check"]["passed"])
        failure = checks["unsupported_expansion_check"]["failures"][0]
        self.assertIn("MoE", failure["entities"])

    def test_malformed_motivation_clause_is_rejected(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        motivation["items"][0]["visible_text"] = (
            "Where global context is crucial makes local receptive field difficult."
        )
        checks, _ = validate_motivation_contribution_specs(
            motivation,
            contribution,
            paper_ir,
        )
        self.assertFalse(
            checks["motivation_language_quality_check"]["passed"]
        )

    def test_vague_reference_is_rejected_during_candidate_selection(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "These issues pose challenges when handling visual data."
        )
        story["research_problem"]["summary"] = (
            "Visual data handling remains challenging."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertEqual(motivation["items"], [])
        self.assertEqual(audit["status"], "failed")


class RoleAndTraceabilityTests(unittest.TestCase):
    def test_motivation_rejects_current_method_contribution(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        motivation["items"][0]["visible_text"] = (
            "We propose Global Context Module for long-range modeling."
        )
        checks, _ = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["role_separation_check"]["passed"])

    def test_contribution_rejects_performance_number_as_subject(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        contribution["items"][0]["visible_text"] = (
            "Best Accuracy\nAchieves 95.4% accuracy on Dataset A."
        )
        checks, _ = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["role_separation_check"]["passed"])

    def test_contribution_rejects_motivation_heading_as_innovation(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        contribution["items"][0]["short_title"] = "Motivation"
        contribution["items"][0]["innovation_object"] = "A. Motivation"
        contribution["items"][0]["visible_text"] = (
            "Motivation\nUses resource constraints to justify the method."
        )
        checks, _ = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["semantic_heading_role_check"]["passed"])

    def test_visible_cross_reference_is_rejected(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        contribution["items"][0]["description"] = (
            "Uses the mechanism shown in Figure 2 to capture dependencies."
        )
        contribution["items"][0]["visible_text"] = (
            "Global Context Module\n"
            "Uses the mechanism shown in Figure 2 to capture dependencies."
        )
        checks, _ = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["cross_reference_check"]["passed"])

    def test_every_item_must_trace_to_a_real_block(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        motivation["items"][0]["source_block_ids"] = ["missing"]
        motivation["items"][0]["source_records"][0]["block_id"] = "missing"
        checks, _ = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["traceability_check"]["passed"])

    def test_renderer_uses_only_visible_text(self) -> None:
        motivation_html = _motivation(
            [
                {
                    "visible_text": "Low contrast obscures thin boundaries.",
                    "raw_statement": "SECRET RAW MOTIVATION",
                }
            ]
        )
        contribution_html = _contributions(
            [
                {
                    "visible_text": "Context Module\nModels long-range dependencies.",
                    "short_title": "SECRET TITLE",
                    "description": "SECRET DESCRIPTION",
                    "raw_statement": "SECRET RAW CONTRIBUTION",
                }
            ]
        )
        rendered = motivation_html + contribution_html
        self.assertIn("Low contrast obscures thin boundaries", rendered)
        self.assertIn("Context Module", rendered)
        self.assertNotIn("SECRET", rendered)


class DynamicSelectionTests(unittest.TestCase):
    def assert_valid_motivation_output(
        self,
        motivation: dict,
        audit: dict,
    ) -> None:
        self.assertGreaterEqual(len(motivation["items"]), 3)
        self.assertLessEqual(len(motivation["items"]), 5)
        self.assertTrue(
            set(
                (
                    "task_problem_or_challenge",
                    "prior_method_limitation",
                    "gap_requirement_or_objective",
                )
            ).issubset(
                {
                    item["selection_role"]
                    for item in motivation["items"]
                }
            )
        )
        self.assertTrue(
            all(
                item["source_block_ids"]
                and item["source_records"]
                and item["visible_text"]
                for item in motivation["items"]
            )
        )
        visible = " ".join(
            item["visible_text"] for item in motivation["items"]
        )
        self.assertNotRegex(
            visible,
            r"(?i)\[[0-9]|we propose|we design|in this paper|"
            r"however|<sup|\\cite|state-of-the-art accuracy",
        )
        self.assertNotIn("target application", visible.lower())
        self.assertTrue(
            all(
                max(
                    (
                        longest_source_overlap(
                            item["visible_text"],
                            record["raw_statement"],
                        )
                        for record in item["source_records"]
                    ),
                    default=0,
                )
                <= 8
                for item in motivation["items"]
            )
        )
        self.assertTrue(
            all(audit["extraction_diagnostics"]["required_role_coverage"].values())
        )

    def test_motivation_has_three_to_five_items_and_required_roles(self) -> None:
        motivation, _, audit = generate_motivation_contribution_specs(
            *method_fixture(1)
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertGreaterEqual(len(motivation["items"]), 3)
        self.assertLessEqual(len(motivation["items"]), 5)
        self.assertTrue(
            {
                "task_problem_or_challenge",
                "prior_method_limitation",
                "gap_requirement_or_objective",
            }.issubset(
                {
                    item["selection_role"]
                    for item in motivation["items"]
                }
            )
        )

    def test_valid_cited_source_is_rewritten_without_visible_citation(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Low contrast obscures thin vessel boundaries [19]. "
            "Prior segmentation models [1-3] fail to preserve fine structures "
            "and long-range context. Effective solutions require boundary "
            "preservation and global contextual modeling."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertTrue(
            any(
                "[19]" in record["raw_statement"]
                or "[1-3]" in record["raw_statement"]
                for item in motivation["items"]
                for record in item["source_records"]
            )
        )
        self.assertTrue(
            all(
                not re.search(r"\[[0-9]", item["visible_text"])
                for item in motivation["items"]
            )
        )

    def test_compound_author_voice_sentence_keeps_problem_clause(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Low contrast obscures thin vessel boundaries. "
            "However, prior segmentation models fail to preserve thin "
            "boundaries [19]; We propose BoundaryNet to recover them. "
            "Reliable segmentation systems require boundary-aware global context."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        limitation = next(
            item
            for item in motivation["items"]
            if item["selection_role"] == "prior_method_limitation"
        )
        self.assertNotRegex(
            limitation["visible_text"],
            r"(?i)however|we propose|\[19\]",
        )
        self.assertTrue(
            any(
                attempt.get("mode") == "relation_specific_source_rewrite"
                for attempt in limitation["rewrite_attempts"]
            )
        )
        self.assertTrue(
            audit["extraction_diagnostics"]["recovery_steps_executed"]
        )
        self.assertTrue(
            any(
                "compound_clause_resplit"
                in candidate.get("recovery_tags", [])
                and candidate.get("selected")
                for candidate in audit["motivation_candidate_records"][
                    "candidates"
                ]
            )
        )

    def test_three_realistic_problem_chain_shapes_are_supported(self) -> None:
        outputs: list[tuple[str, ...]] = []

        concentrated = method_fixture(1)
        motivation, _, audit = generate_motivation_contribution_specs(
            *concentrated
        )
        self.assert_valid_motivation_output(motivation, audit)
        outputs.append(
            tuple(item["visible_text"] for item in motivation["items"])
        )

        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"] = [
            {
                "id": "intro-front",
                "type": "paragraph",
                "page": 1,
                "section_id": "introduction",
                "section_title": "Introduction",
                "text": (
                    "Thin vessel segmentation remains difficult under low "
                    "contrast and weak boundaries."
                ),
            },
            {
                "id": "intro-middle",
                "type": "paragraph",
                "page": 1,
                "section_id": "introduction",
                "section_title": "Introduction",
                "text": (
                    "Convolutional models rely on local receptive fields. "
                    "These approaches fail to capture long-range vessel "
                    "dependencies."
                ),
            },
            {
                "id": "intro-transition",
                "type": "paragraph",
                "page": 2,
                "section_id": "introduction",
                "section_title": "Introduction",
                "text": (
                    "Reliable vessel segmentation methods require joint "
                    "local-detail preservation and global context."
                ),
            },
            *paper_ir["blocks"][1:],
        ]
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assert_valid_motivation_output(motivation, audit)
        outputs.append(
            tuple(item["visible_text"] for item in motivation["items"])
        )

        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Low-contrast retinal images make thin vessel recovery difficult. "
            "Convolutional models fail to extract global vessel dependencies. "
            "We design the Global Transformer branch, solving the problem of "
            "low efficiency in extracting global information."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assert_valid_motivation_output(motivation, audit)
        gap = next(
            item
            for item in motivation["items"]
            if item["selection_role"] == "gap_requirement_or_objective"
        )
        self.assertIn("low efficiency", gap["visible_text"].lower())
        outputs.append(
            tuple(item["visible_text"] for item in motivation["items"])
        )

        self.assertEqual(len(set(outputs)), 3)

    def test_method_description_with_limited_as_modifier_is_rejected(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] += (
            " We designed a global and local enhanced residual U-Net with "
            "contrast limited adaptive histogram equalization."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        selected_sources = " ".join(
            record["raw_statement"]
            for item in motivation["items"]
            for record in item["source_records"]
        )
        self.assertNotIn(
            "contrast limited adaptive histogram equalization",
            selected_sources,
        )
        matching = [
            candidate
            for candidate in audit["motivation_candidate_records"]["candidates"]
            if "contrast limited adaptive histogram" in str(
                candidate.get("raw_statement") or ""
            ).lower()
        ]
        self.assertTrue(matching)
        self.assertTrue(
            all(
                not candidate["gate_results"][
                    "problem_side_plausibility_gate"
                ]["passed"]
                for candidate in matching
            )
        )

    def test_resolution_method_history_is_not_a_limitation(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] += (
            " To resolve the limitations, machine learning methods, which "
            "obtain global information under a few hyperparameters, were "
            "applied in image processing."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        selected_sources = " ".join(
            record["raw_statement"]
            for item in motivation["items"]
            for record in item["source_records"]
        )
        self.assertNotIn(
            "To resolve the limitations",
            selected_sources,
        )
        matching = [
            candidate
            for candidate in audit["motivation_candidate_records"]["candidates"]
            if "to resolve the limitations" in str(
                candidate.get("raw_statement") or ""
            ).lower()
        ]
        self.assertTrue(matching)
        self.assertTrue(
            all(
                not candidate["gate_results"][
                    "problem_side_plausibility_gate"
                ]["passed"]
                for candidate in matching
            )
        )

    def test_fixed_receptive_field_limitation_is_rewritten_without_copying(
        self,
    ) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] += (
            " However, the fixed receptive field of the convolution kernels "
            "in the U-Net results in inefficient information acquisition."
        )
        story["prior_work_gap"]["summary"] = (
            "Fixed U-Net receptive fields cause inefficient contextual "
            "information acquisition."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        visible = [
            item["visible_text"]
            for item in motivation["items"]
        ]
        self.assertIn(
            "Fixed U-Net receptive fields limit contextual information acquisition.",
            visible,
        )
        item = next(
            item
            for item in motivation["items"]
            if item["visible_text"].startswith("Fixed U-Net")
        )
        self.assertEqual(item["rewrite_blockers"], [])

    def test_dropped_cap_ocr_does_not_pollute_visible_subject(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "TUDIES have shown that fundus diseases are one of S the most "
            "important causes of blindness. "
            "Low contrast obscures thin retinal vessels. "
            "Prior segmentation models fail to preserve thin vessels. "
            "Reliable screening methods require complete vessel recovery."
        )
        story["research_problem"]["summary"] = (
            "Fundus disease screening requires complete vessel segmentation."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assert_valid_motivation_output(motivation, audit)
        visible = " ".join(
            item["visible_text"] for item in motivation["items"]
        )
        self.assertNotRegex(visible, r"\bTUDIES\b|\bone of S the\b")
        self.assertIn(
            "Fundus diseases are a major cause of blindness",
            visible,
        )

    def test_cross_sentence_reference_uses_context_subject(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Low contrast obscures thin vessel boundaries. "
            "Convolutional models rely on local receptive fields. "
            "These approaches fail to capture long-range dependencies. "
            "Reliable segmentation systems require local detail and global context."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        limitation = next(
            item
            for item in motivation["items"]
            if item["selection_role"] == "prior_method_limitation"
        )
        self.assertIn(
            "Convolutional models",
            limitation["relation_structure"]["subject"],
        )
        self.assertGreaterEqual(len(limitation["context_window_ids"]), 3)

    def test_concessive_gap_and_only_assumed_limitation_are_recovered(
        self,
    ) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Short scans severely degrade image quality. "
            "Although prior analysis began to examine the connection, it only "
            "assumed that learned filters are modified gradient kernels. "
            "Despite earlier progress, practical questions remain regarding "
            "the link between iterative reconstruction and CNNs."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertEqual(
            {
                item["selection_role"]
                for item in motivation["items"][:3]
            },
            {
                "task_problem_or_challenge",
                "prior_method_limitation",
                "gap_requirement_or_objective",
            },
        )
        visible = " ".join(
            item["visible_text"] for item in motivation["items"]
        )
        self.assertIn("modified gradient kernels", visible)
        self.assertIn("insufficiently understood", visible)

    def test_positive_result_sentence_is_not_selected_as_motivation(
        self,
    ) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] += (
            " Dictionary learning resulted in substantially improved image "
            "quality on the benchmark."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        selected_sources = " ".join(
            record["raw_statement"]
            for item in motivation["items"]
            for record in item["source_records"]
        )
        self.assertNotIn("substantially improved image quality", selected_sources)

    def test_source_copy_failure_rewrites_without_deleting_semantics(self) -> None:
        values = method_fixture(1)
        with patch(
            "paperposter.motivation_contributions._relation_motivation_rewrite",
            side_effect=lambda candidate: str(
                candidate.get("raw_statement") or ""
            ),
        ):
            motivation, _, audit = generate_motivation_contribution_specs(
                *values
            )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertEqual(len(motivation["items"]), 3)
        self.assertTrue(
            any(
                "source_copy_check" in attempt.get("failures", [])
                for item in motivation["items"]
                for attempt in item["rewrite_attempts"]
            )
        )
        self.assertTrue(all(item["visible_text"] for item in motivation["items"]))

    def test_rejected_candidate_findings_do_not_block_compose(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        paper_ir["blocks"][0]["text"] += (
            " These issues pose challenges when handling visual data."
        )
        _, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertEqual(audit["selected_item_blockers"], [])
        self.assertTrue(audit["rejected_candidate_findings"])

    def test_insufficient_evidence_does_not_trigger_template_filling(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Low contrast obscures thin vessel boundaries."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["quality_status"], "sparse_but_sufficient")
        self.assertEqual(len(motivation["items"]), 1)
        self.assertLess(len(motivation["items"]), 3)
        self.assertEqual(audit["issues"], [])
        self.assertNotIn(
            "target application",
            " ".join(
                item["visible_text"] for item in motivation["items"]
            ).lower(),
        )

    def test_adaptive_coverage_does_not_require_literal_role_triplet(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["metadata"]["title"] = (
            "Finite-Sample Analysis under Heavy-Tailed Observations"
        )
        paper_ir["blocks"][0]["text"] = (
            "Understanding convergence under nonconvex objectives remains an "
            "open question. Finite-sample guarantees remain difficult under "
            "heavy-tailed noise. Reliable analysis requires bounds that "
            "tolerate dependent observations."
        )
        story["research_problem"]["summary"] = (
            "Finite-sample guarantees are difficult under heavy-tailed noise."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertGreaterEqual(len(motivation["items"]), 2)
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertTrue(
            all(
                audit["required_coverage_status"][slot]["displayable"]
                for slot in ("core_problem", "unresolved_driver")
            )
        )
        self.assertNotEqual(
            {
                item["selection_role"]
                for item in motivation["items"][:3]
            },
            {
                "task_problem_or_challenge",
                "prior_method_limitation",
                "gap_requirement_or_objective",
            },
        )

    def test_sparse_two_item_fallback_warns_without_fabricating_third(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["metadata"]["title"] = (
            "Efficient Convolutional Networks for Embedded Devices"
        )
        paper_ir["blocks"][0]["text"] = (
            "Deploying convolutional neural networks on embedded devices is "
            "difficult due to limited memory and computation resources. "
            "Feature-map redundancy has rarely been investigated in neural "
            "architecture design."
        )
        story["research_problem"]["summary"] = (
            "Embedded CNN deployment is constrained by resources and "
            "underused feature redundancy."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertEqual(len(motivation["items"]), 2)
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertTrue(audit["sparse_fallback_used"])
        self.assertIn(
            "MOTIVATION_SPARSE_BUT_SUFFICIENT",
            {warning["code"] for warning in audit["warnings"]},
        )
        self.assertNotIn(
            "Effective solutions must address this",
            {item["visible_text"] for item in motivation["items"]},
        )

    def test_unresolved_objective_reference_is_not_used_as_motivation(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Low contrast makes thin vessel recovery difficult. Prior "
            "segmentation models lose fine structures. The paper addresses "
            "this."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            graph,
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertTrue(
            all(
                not re.search(r"\b(?:this|these)\.?$", item["visible_text"], re.I)
                for item in motivation["items"]
            )
        )

    def test_finite_predicate_audit_accepts_leaves(self) -> None:
        self.assertIsNone(
            motivation_module._motivation_language_issue(
                "Open-source-only evaluation leaves real-world "
                "generalization uncertain."
            )
        )

    def test_malformed_requirement_is_rejected_before_display(self) -> None:
        self.assertIsNotNone(
            motivation_module._motivation_language_issue(
                "Effective methods require ambiguous feature responses "
                "and improving contrast."
            )
        )

    def test_generic_task_direction_is_not_used_to_fill_space(self) -> None:
        for text in (
            "Effective solutions must address the challenges in "
            "medical image segmentation.",
            "Effective methods require the challenges in medical image "
            "segmentation.",
        ):
            self.assertIsNotNone(
                motivation_module._motivation_language_issue(text)
            )

    def test_visible_semantic_duplicate_detects_generic_direction(self) -> None:
        selected = [
            {
                "candidate_id": "scale-source",
                "_rewrite_result": {
                    "visible_text": "Scale variation complicates crowd counting."
                },
            }
        ]
        self.assertEqual(
            motivation_module._visible_motivation_duplicate(
                "Effective solutions must address the large-scale "
                "variation issue.",
                selected,
            ),
            "scale-source",
        )

    def test_visible_semantic_duplicate_detects_scale_disparity_paraphrase(
        self,
    ) -> None:
        selected = [
            {
                "candidate_id": "scale-source",
                "_rewrite_result": {
                    "visible_text": "Scale variation complicates crowd counting."
                },
            }
        ]
        self.assertEqual(
            motivation_module._visible_motivation_duplicate(
                "Scale disparity among head instances makes it difficult "
                "to explore all scales.",
                selected,
            ),
            "scale-source",
        )

    def test_visible_semantic_duplicate_keeps_distinct_problem_units(self) -> None:
        selected = [
            {
                "candidate_id": "importance-source",
                "_rewrite_result": {
                    "visible_text": (
                        "Retinal vessel analysis supports early diagnosis "
                        "of severe disease."
                    )
                },
            }
        ]
        self.assertIsNone(
            motivation_module._visible_motivation_duplicate(
                "Tortuous retinal vessels make precise segmentation difficult.",
                selected,
            )
        )

    def test_required_roles_are_not_merged_by_shared_task_words(self) -> None:
        motivation, _, _ = generate_motivation_contribution_specs(
            *method_fixture(1)
        )
        roles = [
            item["selection_role"]
            for item in motivation["items"]
        ]
        self.assertEqual(len(roles), len(set(roles)))

    def _assert_real_paper_displayable_motivation(self, paper_name: str) -> tuple[dict, dict]:
        fixture = real_motivation_regressions()[paper_name]
        motivation, _, audit = generate_motivation_contribution_specs(
            fixture["paper_ir"],
            fixture["story"],
            {"claims": []},
            {"nodes": []},
        )
        required_roles = {
            "task_problem_or_challenge",
            "prior_method_limitation",
            "gap_requirement_or_objective",
        }
        self.assertGreaterEqual(len(motivation["items"]), 3)
        self.assertLessEqual(len(motivation["items"]), 5)
        self.assertTrue(
            required_roles.issubset(
                {
                    item["selection_role"]
                    for item in motivation["items"]
                }
            )
        )
        for item in motivation["items"]:
            self.assertTrue(item["selected"])
            self.assertTrue(item["visible_text"].strip())
            self.assertEqual(item["rewrite_status"], "passed")
            self.assertEqual(item["language_audit_status"], "passed")
            self.assertEqual(item["traceability_status"], "passed")
            self.assertEqual(item["role_separation_status"], "passed")
            self.assertTrue(item["displayable"])
            self.assertNotRegex(
                item["visible_text"].lower(),
                r"\bis(?:\s+still|\s+not)?\s+limits\b",
            )
        self.assertEqual(audit["displayable_item_count"], len(motivation["items"]))
        self.assertFalse(audit["empty_visible_items"])
        self.assertFalse(audit["compose_blockers"])
        return motivation, audit

    def test_rccformer_has_three_displayable_motivation_items(self) -> None:
        motivation, audit = self._assert_real_paper_displayable_motivation(
            "RCCFormer"
        )
        self.assertTrue(
            audit["candidate_attempts_per_role"]["prior_method_limitation"]
        )
        self.assertIn(
            "Large scale variation complicates crowd counting.",
            [item["visible_text"] for item in motivation["items"]],
        )

    def test_mslau_net_does_not_count_blank_selected_items(self) -> None:
        motivation, audit = self._assert_real_paper_displayable_motivation(
            "MSLAU-Net"
        )
        self.assertEqual(
            audit["displayable_item_count"],
            len(motivation["items"]),
        )
        self.assertTrue(
            all(
                attempt["status"] == "passed"
                for role_attempts in audit["candidate_attempts_per_role"].values()
                for attempt in role_attempts
                if attempt["candidate_id"]
                in {item["source_candidate_id"] for item in motivation["items"]}
            )
        )

    def test_sim_mpnet_never_emits_blank_motivation(self) -> None:
        motivation, audit = self._assert_real_paper_displayable_motivation(
            "Sim-MPNet"
        )
        self.assertGreaterEqual(len(motivation["items"]), 3)
        self.assertTrue(
            all(
                value["displayable"]
                for value in audit["required_coverage_status"].values()
            )
        )

    def test_required_role_uses_next_candidate_after_rewrite_failure(self) -> None:
        fixture = real_motivation_regressions()["RCCFormer"]
        original = motivation_module._rewrite_selected_motivation
        failed_candidate_id: list[str] = []

        def fail_first_prior(candidate: dict, paper_ir: dict) -> dict:
            if (
                candidate.get("selection_role") == "prior_method_limitation"
                and not failed_candidate_id
            ):
                failed_candidate_id.append(str(candidate["candidate_id"]))
                return {
                    "status": "failed",
                    "visible_text": "",
                    "failure_code": "source_copy_check",
                    "attempts": [
                        {
                            "mode": "source_copy_aware_rewrite",
                            "visible_text": "",
                            "status": "failed",
                            "failure_code": "source_copy_check",
                            "audit": {"displayable": False},
                            "failures": ["source_copy_check"],
                        }
                    ],
                    "audit": {"displayable": False},
                    "normalized_relation": "lacks_capability",
                }
            return original(candidate, paper_ir)

        with patch(
            "paperposter.motivation_contributions._rewrite_selected_motivation",
            side_effect=fail_first_prior,
        ):
            motivation, _, audit = generate_motivation_contribution_specs(
                fixture["paper_ir"],
                fixture["story"],
                {"claims": []},
                {"nodes": []},
            )
        prior_item = next(
            item
            for item in motivation["items"]
            if item["selection_role"] == "prior_method_limitation"
        )
        self.assertNotEqual(prior_item["source_candidate_id"], failed_candidate_id[0])
        self.assertTrue(audit["replacement_candidates_used"])

    def test_selected_semantic_count_cannot_replace_displayable_count(self) -> None:
        values = method_fixture(1)

        def fail_every_rewrite(candidate: dict, paper_ir: dict) -> dict:
            del candidate, paper_ir
            return {
                "status": "failed",
                "visible_text": "",
                "failure_code": "poster_rewrite_failed",
                "attempts": [],
                "audit": {"displayable": False},
                "normalized_relation": "",
            }

        with patch(
            "paperposter.motivation_contributions._rewrite_selected_motivation",
            side_effect=fail_every_rewrite,
        ):
            motivation, contribution, audit = (
                generate_motivation_contribution_specs(*values)
            )
        self.assertGreaterEqual(audit["selected_semantic_count"], 3)
        self.assertEqual(audit["displayable_item_count"], 0)
        self.assertEqual(motivation["items"], [])
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(
            audit["checks"]["motivation_coverage_check"]["failures"][0]["code"],
            "MOTIVATION_EVIDENCE_INSUFFICIENT",
        )
        self.assertEqual(
            [item["short_title"] for item in contribution["items"]],
            ["Global Context Module"],
        )

    def test_one_valid_contribution_is_preserved_without_filling_three_items(self) -> None:
        values = method_fixture(1)
        _, contribution, audit = generate_motivation_contribution_specs(*values)
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertEqual(len(contribution["items"]), 1)
        self.assertEqual(contribution["displayable_count"], 1)
        self.assertTrue(audit["checks"]["contribution_coverage_check"]["passed"])
        self.assertEqual(
            contribution["warnings"][0]["code"],
            "CONTRIBUTION_SPARSE_BUT_SUFFICIENT",
        )

    def test_five_independent_contributions_are_ranked_to_four(self) -> None:
        values = method_fixture(5)
        _, contribution, audit = generate_motivation_contribution_specs(*values)
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(len(contribution["items"]), 4)
        self.assertEqual(contribution["displayable_count"], 4)
        self.assertEqual(
            {
                item["contribution_role"]
                for item in contribution["items"][:3]
            },
            {
                "primary_method_or_architecture",
                "primary_innovation_mechanism",
                "secondary_independent_contribution",
            },
        )
        self.assertTrue(contribution["selection_policy"]["core_ranked_not_truncated"])

    def test_synonymous_contributions_are_merged(self) -> None:
        base = {
            "candidate_id": "c1",
            "contribution_type": "feature_fusion_strategy",
            "innovation_object": "Hierarchical Feature Fusion Module",
            "mechanism": "deep and shallow feature integration",
            "purpose": "combine semantic and spatial details",
            "method_node_id": "node-1",
            "source_records": [
                {
                    "block_id": "b1",
                    "page": 2,
                    "source_section": "Method",
                    "raw_statement": "source one",
                }
            ],
            "gate_results": {
                "novelty_gate": {"passed": True},
                "centrality_gate": {"passed": True},
                "specificity_gate": {"passed": True},
                "method_support_gate": {"passed": True},
                "evidence_gate": {"passed": True},
                "independence_gate": {"passed": True},
                "result_separation_gate": {"passed": True},
            },
            "importance": 0.8,
        }
        synonym = deepcopy(base)
        synonym["candidate_id"] = "c2"
        synonym["innovation_object"] = "Deep-Shallow Fusion Module"
        synonym["source_records"][0]["block_id"] = "b2"
        merged, rejected = _merge_candidates([base, synonym], "contribution")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["merged_from"], ["c2"])
        self.assertEqual(rejected[0]["merged_into"], "c1")

    def test_repeated_motivation_topics_are_merged(self) -> None:
        base_gates = {
            "relevance_gate": {"passed": True},
            "specificity_gate": {"passed": True},
            "causal_gate": {"passed": True},
            "evidence_gate": {"passed": True},
            "independence_gate": {"passed": True},
            "role_separation_gate": {"passed": True},
        }
        first = {
            "candidate_id": "m1",
            "type": "task_challenge",
            "raw_statement": (
                "Local receptive fields restrict long-range vessel context."
            ),
            "normalized_meaning": (
                "Local receptive fields restrict long-range vessel context."
            ),
            "source_records": [
                {
                    "block_id": "b1",
                    "page": 1,
                    "raw_statement": "source one",
                }
            ],
            "gate_results": deepcopy(base_gates),
            "importance": 0.9,
        }
        second = {
            **deepcopy(first),
            "candidate_id": "m2",
            "raw_statement": (
                "Fixed receptive fields lose thin-vessel dependencies over "
                "long distances."
            ),
            "normalized_meaning": (
                "Fixed receptive fields lose thin-vessel dependencies over "
                "long distances."
            ),
            "source_records": [
                {
                    "block_id": "b2",
                    "page": 2,
                    "raw_statement": "source two",
                }
            ],
        }
        merged, rejected = _merge_candidates([first, second], "motivation")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["merged_from"], ["m2"])
        self.assertEqual(rejected[0]["merged_into"], "m1")

    def test_cross_type_duplicate_motivations_are_merged(self) -> None:
        gates = {
            "relevance_gate": {"passed": True},
            "specificity_gate": {"passed": True},
            "causal_gate": {"passed": True},
            "evidence_gate": {"passed": True},
            "independence_gate": {"passed": True},
            "role_separation_gate": {"passed": True},
            "language_rewrite_gate": {"passed": True},
        }
        task = {
            "candidate_id": "m1",
            "type": "task_challenge",
            "raw_statement": (
                "Raindrop-background coupling makes clear-image recovery difficult."
            ),
            "normalized_meaning": (
                "Raindrop-background coupling complicates clear-image recovery."
            ),
            "source_records": [
                {"block_id": "b1", "page": 1, "raw_statement": "source one"}
            ],
            "gate_results": deepcopy(gates),
            "importance": 0.9,
        }
        data = {
            **deepcopy(task),
            "candidate_id": "m2",
            "type": "data_challenge",
            "raw_statement": (
                "Rain degrades object details and frequency information."
            ),
            "normalized_meaning": (
                "Rain degrades object detail and frequency information."
            ),
            "source_records": [
                {"block_id": "b2", "page": 2, "raw_statement": "source two"}
            ],
        }
        merged, rejected = _merge_candidates([task, data], "motivation")
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["merged_from"], ["m2"])
        self.assertEqual(rejected[0]["merged_into"], "m1")

    def test_distinct_single_topic_motivations_are_not_merged(self) -> None:
        gates = {
            "relevance_gate": {"passed": True},
            "specificity_gate": {"passed": True},
            "causal_gate": {"passed": True},
            "evidence_gate": {"passed": True},
            "independence_gate": {"passed": True},
            "role_separation_gate": {"passed": True},
            "language_rewrite_gate": {"passed": True},
        }
        spatial = {
            "candidate_id": "m1",
            "type": "prior_method_limitation",
            "raw_statement": "Standard convolutions ignore target spatial structure.",
            "normalized_meaning": (
                "Standard convolutions ignore target spatial structure."
            ),
            "source_records": [
                {"block_id": "b1", "page": 1, "raw_statement": "source one"}
            ],
            "gate_results": deepcopy(gates),
            "importance": 0.9,
        }
        loss = {
            **deepcopy(spatial),
            "candidate_id": "m2",
            "raw_statement": "Existing losses ignore scale-dependent sensitivity.",
            "normalized_meaning": (
                "Existing losses ignore scale-dependent sensitivity."
            ),
            "source_records": [
                {"block_id": "b2", "page": 2, "raw_statement": "source two"}
            ],
        }
        merged, _ = _merge_candidates([spatial, loss], "motivation")
        self.assertEqual(len(merged), 2)

    def test_independent_contributions_are_not_merged(self) -> None:
        values = method_fixture(2)
        _, contribution, audit = generate_motivation_contribution_specs(*values)
        self.assertEqual(len(contribution["items"]), 2)
        self.assertEqual(
            contribution["selection_trace"]["semantic_selected_count"],
            2,
        )
        self.assertTrue(
            contribution["selection_trace"]["recovery_steps_executed"]
        )
        self.assertTrue(audit["checks"]["contribution_coverage_check"]["passed"])

    def test_resource_burdens_remain_problem_side_motivation(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Resource-constrained MoE deployment remains difficult because devices "
            "must accommodate many expert parameters. Existing MoE models are "
            "limited by substantially increased parameter counts and training costs. "
            "Practical MoE systems require parameter-efficient training and inference."
        )
        story["research_problem"]["summary"] = (
            "MoE training and inference impose large resource demands."
        )
        story["motivation"]["summary"] = (
            "Expert capacity increases parameter and deployment costs."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertTrue(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertGreaterEqual(len(motivation["items"]), 3)
        self.assertEqual(
            {
                item["selection_role"]
                for item in motivation["items"][:3]
            },
            {
                "task_problem_or_challenge",
                "prior_method_limitation",
                "gap_requirement_or_objective",
            },
        )

    def test_empty_motivation_cannot_pass_when_problem_evidence_exists(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"][0]["text"] = (
            "Complex tasks offer important advantages for large-scale systems."
        )
        story["research_problem"]["summary"] = (
            "Complex tasks affect large-scale systems."
        )
        motivation, _, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertEqual(motivation["items"], [])
        self.assertEqual(audit["status"], "failed")
        self.assertFalse(audit["checks"]["motivation_coverage_check"]["passed"])
        self.assertEqual(
            audit["checks"]["motivation_coverage_check"]["failures"][0]["code"],
            "MOTIVATION_EVIDENCE_INSUFFICIENT",
        )

    def test_missing_explicit_contribution_returns_to_storyline(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        paper_ir["blocks"] = [paper_ir["blocks"][0]]
        graph["nodes"] = []
        _, contribution, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertEqual(contribution["items"], [])
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["return_to"], "paper-storyline")
        self.assertFalse(audit["checks"]["contribution_coverage_check"]["passed"])

    def test_skill_writes_candidate_and_contribution_audits(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        with tempfile.TemporaryDirectory(prefix="contribution-artifacts-") as temp:
            root = Path(temp)

            def write(name: str, value: dict) -> Path:
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                return path

            output = root / "output"
            build_motivation_contributions(
                write("paper.json", paper_ir),
                write("story.json", story),
                write("evidence.json", evidence),
                write("graph.json", graph),
                output,
            )
            candidates = json.loads(
                (output / "contribution_candidates.json").read_text(encoding="utf-8")
            )
            audit = json.loads(
                (output / "contribution_audit.json").read_text(encoding="utf-8")
            )
            diagnostics = json.loads(
                (output / "extraction_diagnostics.json").read_text(
                    encoding="utf-8"
                )
            )
            motivation_audit = json.loads(
                (output / "motivation_audit.json").read_text(
                    encoding="utf-8"
                )
            )
            motivation_candidates = json.loads(
                (output / "motivation_candidates.json").read_text(
                    encoding="utf-8"
                )
            )
            motivation_spec = json.loads(
                (output / "motivation_spec.json").read_text(
                    encoding="utf-8"
                )
            )
            debug_report = (
                output / "motivation-debug-report.md"
            ).read_text(encoding="utf-8")
            motivation_preview = (
                output / "motivation-preview.html"
            ).read_text(encoding="utf-8")
        self.assertEqual(candidates["candidate_count"], 1)
        self.assertEqual(candidates["selected_count"], 1)
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(diagnostics["selected_motivation_count"], 3)
        self.assertEqual(diagnostics["selected_count"], 3)
        self.assertGreaterEqual(
            diagnostics["candidates_after_semantic_gates"],
            3,
        )
        self.assertGreaterEqual(diagnostics["candidates_after_merging"], 3)
        self.assertIn("scanned_blocks", diagnostics)
        self.assertIn("rewrite_failures", diagnostics)
        self.assertTrue(
            all(diagnostics["required_role_coverage"].values())
        )
        self.assertEqual(motivation_audit["status"], "passed")
        self.assertEqual(motivation_candidates["selected_count"], 3)
        self.assertEqual(len(motivation_spec["items"]), 3)
        self.assertIn("## Candidate ledger", debug_report)
        self.assertIn("## Required-slot selection", debug_report)
        self.assertIn("## Coverage recovery", debug_report)
        self.assertIn("## Final visible text and evidence", debug_report)
        self.assertIn("<title>Motivation Preview</title>", motivation_preview)

    def test_contribution_artifacts_include_staged_debug_outputs(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(1)
        with tempfile.TemporaryDirectory(prefix="contribution-debug-artifacts-") as temp:
            root = Path(temp)

            def write(name: str, value: dict) -> Path:
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                return path

            output = root / "output"
            build_motivation_contributions(
                write("paper.json", paper_ir),
                write("story.json", story),
                write("evidence.json", evidence),
                write("graph.json", graph),
                output,
            )
            for name in (
                "contribution_candidates.json",
                "contribution_spec.json",
                "contribution_audit.json",
                "contribution_extraction_diagnostics.json",
                "contribution-debug-report.md",
                "contribution-preview.html",
            ):
                self.assertTrue((output / name).exists(), name)
            diagnostics = json.loads(
                (output / "contribution_extraction_diagnostics.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(diagnostics["explicit_claims_found"], 1)
            self.assertEqual(diagnostics["selected_count"], 1)
            self.assertEqual(diagnostics["displayable_count"], 1)
            self.assertTrue(diagnostics["recovery_steps_executed"])

    def test_numbered_contribution_list_is_split_and_result_is_routed(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        paper_ir["blocks"].append(
            {
                "id": "intro-contributions",
                "type": "paragraph",
                "page": 5,
                "section_id": "introduction",
                "section_title": "Introduction",
                "text": (
                    "Our main contributions are as follows: 1) We introduce a "
                    "Boundary Consistency Loss using boundary-aware supervision to "
                    "reduce contour fragmentation; 2) We design a Confidence Scoring "
                    "Criterion using uncertainty-weighted scoring to rank ambiguous "
                    "predictions; 3) Our method achieves 95.2% Dice."
                ),
            }
        )
        _, contribution, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        titles = {item["short_title"] for item in contribution["items"]}
        self.assertIn("Boundary Consistency Loss", titles)
        self.assertIn("Confidence Scoring Criterion", titles)
        self.assertGreaterEqual(audit["contribution_extraction_diagnostics"]["result_only_candidates"], 1)
        self.assertTrue(
            all("95.2" not in item["visible_text"] for item in contribution["items"])
        )

    def test_inline_parenthesized_innovations_split_module_and_loss(self) -> None:
        statement = (
            "It introduces two key innovations: (1) a novel Cross-scale "
            "Spatial Attention (CSA) module that integrates encoder and decoder "
            "features, improving fine-vessel detection; and (2) a compound loss "
            "function that combines BCE with MCC loss, improving robustness to "
            "class imbalance."
        )
        segments = motivation_module._contribution_segments(statement)
        self.assertEqual(len(segments), 2)
        semantics = [
            motivation_module._decompose_contribution_statement(segment)
            for segment in segments
        ]
        self.assertIn("CSA", semantics[0]["innovation_object"])
        self.assertNotIn(
            "MCC",
            semantics[0]["mechanism_or_action"],
        )
        self.assertIn(
            "loss",
            semantics[1]["innovation_object"].lower(),
        )

    def test_architecture_sentence_splits_coordinated_loss_proposition(self) -> None:
        statement = (
            "We propose SA-UNetv2, a lightweight model that injects cross-scale "
            "attention into skip connections to strengthen feature fusion and "
            "adopts a weighted BCE plus MCC loss to address class imbalance."
        )
        propositions = motivation_module._contribution_propositions(statement)
        self.assertEqual(len(propositions), 2)
        self.assertIn("SA-UNetv2", propositions[0])
        self.assertNotIn("MCC loss", propositions[0])
        self.assertIn("MCC loss", propositions[1])

    def test_architecture_and_loss_remain_independent(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        graph["nodes"].append(
            {
                "id": "method-node-loss",
                "name": "Boundary Consistency Loss",
                "innovation": "We introduce Boundary Consistency Loss using boundary-aware supervision to reduce contour fragmentation.",
                "purpose": "reduce contour fragmentation",
                "section_id": "method-loss",
                "sources": [{"block_id": "method-1", "page": 3}],
            }
        )
        _, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertGreaterEqual(len(contribution["items"]), 3)
        types = {item["contribution_type"] for item in contribution["items"]}
        self.assertTrue("architecture" in types or "mechanism" in types)
        self.assertTrue("objective_or_loss" in types or "mechanism" in types)

    def test_unmodified_common_component_is_not_a_contribution(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        graph["nodes"].append(
            {
                "id": "method-node-relu",
                "name": "ReLU",
                "innovation": "The network uses ReLU activations.",
                "purpose": "nonlinear activation",
                "section_id": "method-relu",
                "sources": [{"block_id": "method-1", "page": 3}],
            }
        )
        _, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertNotIn("ReLU", {item["short_title"] for item in contribution["items"]})

    def test_source_copy_failure_keeps_verified_contribution(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        graph["nodes"][0]["innovation"] = (
            "We introduce Global Context Module using long-range attention "
            "to capture distant dependencies."
        )
        _, contribution, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertGreaterEqual(len(contribution["items"]), 3)
        self.assertIn("selected_item_blockers", audit["contribution_audit"])

    def test_contribution_audit_separates_rejected_findings(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        graph["nodes"].append(
            {
                "id": "method-node-heading",
                "name": "Background",
                "innovation": "We describe the background.",
                "purpose": "background context",
                "section_id": "background",
                "sources": [{"block_id": "intro-1", "page": 1}],
            }
        )
        _, _, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertIn("rejected_candidate_findings", audit["contribution_audit"])
        self.assertEqual(audit["contribution_audit"]["selected_item_blockers"], [])

    def test_compact_layout_does_not_delete_valid_items(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(5)
        motivation, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        selected = {
            "paper_id": paper_ir["paper_id"],
            "captions_inspected": 0,
            "overview_asset": None,
            "figure_number_prior_used": False,
        }
        method_visual = {
            "mode": "text_only_method_path",
            "overview_asset_id": None,
            "callouts": [],
            "storyboard_items": [],
            "experiment_strip": [],
            "method_asset_ids": [],
            "result_asset_ids_in_method": [],
        }
        key_idea = {
            "type": "mechanism_centered",
            "headline": "A sourced mechanism explains the central design.",
            "visual": {"visual_type": "three_step_flow", "items": []},
            "equation": {"display_mode": "none", "equation_id": None},
        }
        results = {
            "layout_template": "quantitative_plus_qualitative",
            "primary_asset": None,
            "secondary_asset": None,
            "key_metrics": [],
        }
        highlights = {"highlights": []}
        full_story = {
            **story,
            "method_design": {"summary": "", "status": "not_found", "sources": []},
            "experimental_design": {"summary": "", "status": "not_found", "sources": []},
            "core_hypothesis": {"summary": "", "status": "not_found", "sources": []},
            "theory_or_mechanism": {"summary": "", "status": "not_found", "sources": []},
            "conclusion": {"summary": "", "status": "not_found", "sources": []},
            "limitations": {"summary": "", "status": "not_found", "sources": []},
        }
        with tempfile.TemporaryDirectory(prefix="dynamic-compose-") as temp:
            root = Path(temp)

            def write(name: str, value: dict) -> Path:
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                return path

            args = [
                write("paper.json", paper_ir),
                write("story.json", full_story),
                write("evidence.json", evidence),
                write("selected.json", selected),
                write("graph.json", graph),
                write("method-visual.json", method_visual),
                write("key-idea.json", key_idea),
                write("results.json", results),
                write("highlights.json", highlights),
                write("motivation.json", motivation),
                write("contribution.json", contribution),
            ]
            first, _ = compose_poster(*args, root / "c0", compact_level=0)
            compact, _ = compose_poster(*args, root / "c2", compact_level=2)
            first_spec = json.loads(first.read_text(encoding="utf-8"))
            compact_spec = json.loads(compact.read_text(encoding="utf-8"))
        self.assertEqual(len(first_spec["panels"]["contributions"]), 4)
        self.assertEqual(len(compact_spec["panels"]["contributions"]), 4)


class ContributionFinalSelectionTests(unittest.TestCase):
    def test_architecture_and_child_module_keep_distinct_canonical_ids(self) -> None:
        paper_ir = {
            "metadata": {
                "title": (
                    "I2U-Net with Multi-Functional Information Interaction"
                )
            },
            "blocks": [
                {
                    "id": "intro",
                    "type": "paragraph",
                    "page": 1,
                    "section_title": "Introduction",
                    "text": (
                        "I<sup>2</sup>U-Net uses a dual path. The "
                        "multi-functional information interaction module "
                        "(MFII) fuses cross-path features."
                    ),
                }
            ],
        }
        architecture_id, architecture_name = (
            motivation_module._canonical_object_identity(
                "dual-path I<sup>2</sup>U-Net",
                paper_ir,
            )
        )
        module_id, module_name = (
            motivation_module._canonical_object_identity(
                "multi-functional information interaction module (MFII)",
                paper_ir,
            )
        )
        self.assertEqual(architecture_name, "I2U-Net")
        self.assertEqual(module_name, "MFII")
        self.assertNotEqual(architecture_id, module_id)

    def test_composite_loss_keeps_all_named_objectives_in_identity(self) -> None:
        canonical_id, canonical_name = (
            motivation_module._canonical_object_identity(
                "weighted Binary Cross-Entropy (BCE) + Matthews "
                "Correlation Coefficient (MCC) loss",
                {"metadata": {"title": "Retinal Segmentation"}, "blocks": []},
            )
        )
        self.assertEqual(canonical_name, "BCE + MCC Loss")
        self.assertEqual(canonical_id, "co-bcemccloss")

    def test_parent_architecture_and_primary_child_remain_incremental(self) -> None:
        architecture = {
            "canonical_object_id": "co-model",
            "component_level": "overall_architecture",
            "innovation_object": "ModelNet",
            "mechanism": "injects cross-scale attention into skip connections",
            "purpose": "strengthen feature fusion",
        }
        module = {
            "canonical_object_id": "co-csa",
            "parent_object_id": "co-model",
            "component_level": "primary_mechanism",
            "innovation_object": "Cross-scale Spatial Attention",
            "mechanism": "injects cross-scale attention into skip connections",
            "purpose": "strengthen feature fusion",
        }
        self.assertTrue(
            motivation_module._incremental_contribution(
                module,
                [architecture],
            )
        )

    def test_attention_child_rewrite_recovers_from_source_copy(self) -> None:
        candidate = {
            "innovation_object": "Cross-scale Spatial Attention (CSA) module",
            "canonical_object_name": "CSA",
            "mechanism_or_action": (
                "integrates Cross-scale Spatial Attention into all skip "
                "connections"
            ),
            "solved_problem": (
                "address the semantic gap between encoder and decoder features"
            ),
            "raw_statement": (
                "The CSA module integrates encoder and decoder features "
                "through all skip connections."
            ),
            "description": "",
            "source_records": [
                {
                    "raw_statement": (
                        "The CSA module integrates encoder and decoder features "
                        "through all skip connections."
                    )
                }
            ],
        }
        title, description, attempts, blockers = (
            motivation_module._rewrite_selected_contribution(candidate)
        )
        self.assertEqual(title, "CSA")
        self.assertIn("skip pathways", description)
        self.assertEqual(blockers, [])
        self.assertTrue(
            any(
                attempt["mode"] == "source_copy_aware_rewrite"
                and attempt["passed"]
                for attempt in attempts
            )
        )

    def test_repeated_model_across_sections_has_one_canonical_item(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        paper_ir["blocks"].extend(
            [
                {
                    "id": "abstract-repeat",
                    "type": "paragraph",
                    "page": 1,
                    "section_id": "abstract",
                    "section_title": "Abstract",
                    "text": (
                        "We propose Global Context Module using long-range "
                        "attention to capture distant dependencies."
                    ),
                },
                {
                    "id": "conclusion-repeat",
                    "type": "paragraph",
                    "page": 8,
                    "section_id": "conclusion",
                    "section_title": "Conclusion",
                    "text": (
                        "This work introduces the Global Context Module to "
                        "capture distant dependencies with long-range attention."
                    ),
                },
            ]
        )
        _, contribution, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        identities = [
            item["canonical_object_id"] for item in contribution["items"]
        ]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual(
            sum(item["short_title"] == "Global Context Module" for item in contribution["items"]),
            1,
        )
        self.assertTrue(
            audit["checks"]["duplicate_canonical_object_check"]["passed"]
        )

    def test_duplicate_short_titles_are_blocked_by_final_validator(self) -> None:
        motivation, contribution, paper_ir = valid_specs()
        base = contribution["items"][0]
        contribution["items"] = [
            {
                **deepcopy(base),
                "id": f"C{index}",
                "canonical_object_id": f"co-{index}",
                "displayable": True,
                "selected": True,
            }
            for index in range(1, 4)
        ]
        checks, _ = validate_motivation_contribution_specs(
            motivation, contribution, paper_ir
        )
        self.assertFalse(checks["duplicate_short_title_check"]["passed"])

    def test_four_stage_encoder_is_routed_to_method(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        statement = (
            "We construct a four-stage encoder using standard convolution "
            "blocks to encode hierarchical features."
        )
        paper_ir["blocks"].append(
            {
                "id": "method-stage",
                "type": "paragraph",
                "page": 7,
                "section_id": "method-stage",
                "section_title": "Method",
                "text": statement,
            }
        )
        graph["nodes"].append(
            {
                "id": "method-stage-node",
                "name": "four-stage encoder",
                "innovation": statement,
                "purpose": "encode hierarchical features",
                "section_id": "method-stage",
                "sources": [{"block_id": "method-stage", "page": 7}],
            }
        )
        _, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertNotIn(
            "four-stage encoder",
            {item["short_title"].lower() for item in contribution["items"]},
        )
        self.assertTrue(
            any(
                item["component_level"] == "implementation_step"
                for item in contribution["routed_to_method"]
            )
        )

    def test_ordinary_method_graph_node_is_not_promoted(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        graph["nodes"].append(
            {
                "id": "ordinary-upsampling",
                "name": "Bilinear Upsampling",
                "innovation": "The decoder uses bilinear upsampling.",
                "purpose": "restore spatial resolution",
                "section_id": "method",
                "sources": [{"block_id": "method-1", "page": 3}],
            }
        )
        _, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertNotIn(
            "Bilinear Upsampling",
            {item["short_title"] for item in contribution["items"]},
        )

    def test_architecture_and_independent_module_can_coexist(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        statement = (
            "We propose DetailContextNet, an architecture that coordinates "
            "global context and local detail recovery."
        )
        paper_ir["blocks"].append(
            {
                "id": "architecture-block",
                "type": "paragraph",
                "page": 2,
                "section_id": "introduction",
                "section_title": "Introduction",
                "text": statement,
            }
        )
        graph["nodes"].append(
            {
                "id": "architecture-node",
                "name": "DetailContextNet",
                "innovation": statement,
                "purpose": "coordinate global context and local detail recovery",
                "section_id": "architecture",
                "sources": [{"block_id": "architecture-block", "page": 2}],
            }
        )
        _, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        titles = {item["short_title"] for item in contribution["items"]}
        self.assertIn("DetailContextNet", titles)
        self.assertTrue(
            {"Global Context Module", "Local Detail Block"} & titles
        )

    def test_author_declared_systematic_validation_can_fill_third_role(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(2)
        paper_ir["blocks"].append(
            {
                "id": "explicit-contribution-list",
                "type": "paragraph",
                "page": 2,
                "section_id": "introduction",
                "section_title": "Introduction",
                "text": (
                    "Our main contributions are as follows: 1) We introduce "
                    "Global Context Module using long-range attention to capture "
                    "distant dependencies; 2) We introduce Local Detail Block "
                    "using multi-scale convolution to preserve fine boundaries; "
                    "3) Systematic experiments across three datasets validate "
                    "generalization under distinct evaluation settings."
                ),
            }
        )
        _, contribution, audit = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertEqual(contribution["displayable_count"], 3)
        self.assertIn(
            "empirical_validation",
            {item["component_level"] for item in contribution["items"]},
        )
        self.assertTrue(audit["checks"]["contribution_coverage_check"]["passed"])

    def test_single_performance_number_is_routed_out(self) -> None:
        paper_ir, story, evidence, graph = method_fixture(3)
        paper_ir["blocks"].append(
            {
                "id": "result-only",
                "type": "paragraph",
                "page": 8,
                "section_id": "conclusion",
                "section_title": "Conclusion",
                "text": "Our method achieves 95.2% Dice on Dataset X.",
            }
        )
        _, contribution, _ = generate_motivation_contribution_specs(
            paper_ir, story, evidence, graph
        )
        self.assertTrue(
            all("95.2" not in item["visible_text"] for item in contribution["items"])
        )

    def test_more_than_four_is_core_ranked_not_source_truncated(self) -> None:
        _, contribution, _ = generate_motivation_contribution_specs(
            *method_fixture(5)
        )
        titles = [item["short_title"] for item in contribution["items"]]
        source_first_four = [
            "Global Context Module",
            "Local Detail Block",
            "Adaptive Fusion Strategy",
            "Boundary Consistency Loss",
        ]
        self.assertEqual(len(titles), 4)
        self.assertNotEqual(titles, source_first_four)
        self.assertIn("Boundary Consistency Loss", titles)

    def test_motivation_regressions_remain_deterministic(self) -> None:
        for name, fixture in real_motivation_regressions().items():
            outputs = [
                generate_motivation_contribution_specs(
                    fixture["paper_ir"],
                    fixture["story"],
                    {"claims": []},
                    {"nodes": []},
                )[0]
                for _ in range(2)
            ]
            self.assertEqual(
                json.dumps(outputs[0], sort_keys=True, ensure_ascii=False),
                json.dumps(outputs[1], sort_keys=True, ensure_ascii=False),
                name,
            )
            self.assertTrue(
                all(
                    item.get("coverage_slot")
                    for item in outputs[0]["items"]
                ),
                name,
            )


if __name__ == "__main__":
    unittest.main()
