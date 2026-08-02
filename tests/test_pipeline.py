from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paperposter.assets import _equation_score, select_assets
from paperposter.common import read_json, sentences
from paperposter.compose import (
    _highlight_numbers,
    _method_overview_flow_items,
    _sanitize_panel_text,
    compose_poster,
)
from paperposter.experimental_results import (
    _headline as _result_headline,
    _order_metrics_for_claim,
)
from paperposter.ingest import ingest
from paperposter.key_idea import (
    _apply_equation_alignment_gate,
    _complete_visible_sentence,
    _core_claim,
    _headline,
    _node_visual_text,
    _structured_mechanism_headline,
    _takeaway,
    _visual_items,
    audit_key_idea_visible_text,
    build_key_idea,
    classify_key_idea_type,
    score_equation,
    visible_text_findings,
    visual_layout_compatible,
)
from paperposter.method_figures import (
    _analyze_visual_text,
    classify_figure_role,
    map_method_figures,
)
from paperposter.method_graph import build_method_graph
from paperposter.method_visual import (
    _dedicated_module_details,
    _mechanism_flow,
    compose_method_visual,
)
from paperposter.pipeline import run_pipeline
from paperposter.qa import (
    _apply_delivery_severity_policy,
    _collect_panel_text,
    _global_visible_text_issues,
    _method_content_mismatches,
    _validate_method_overview,
)
from paperposter.render import (
    _find_runtime,
    _key_idea_content,
    _method_overview_content,
    _method_storyboard,
    _project_content,
    finalize_render_bundle,
    render_poster,
)
from paperposter.storyline import extract_story


class ContractTests(unittest.TestCase):
    def test_schema_contains_core_contracts(self) -> None:
        schema = read_json(PROJECT_ROOT / "schemas" / "paper-poster.schema.json")
        expected = {
            "PaperIR",
            "PaperStory",
            "MotivationSpec",
            "ContributionSpec",
            "ContributionCandidateSpec",
            "ContributionAudit",
            "ClaimEvidence",
            "MethodGraph",
            "MethodFigureMap",
            "MethodVisualPlan",
            "KeyIdeaSpec",
            "ExperimentalResultsSpec",
            "HighlightsSpec",
            "SelectedAssets",
            "PosterSpec",
            "ReadingReportSpec",
            "ReadingReportQa",
            "QaReport",
        }
        self.assertTrue(expected.issubset(schema["$defs"]))

    def test_every_skill_has_no_todo(self) -> None:
        for skill_path in (PROJECT_ROOT / "skills").glob("*/SKILL.md"):
            content = skill_path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", content, skill_path)

    def test_highlight_ignores_confidence_level_and_year(self) -> None:
        claim = (
            "In 2026, the model achieves ACC 0.9804 and F1 0.8799 "
            "with a corresponding 95% confidence interval."
        )
        self.assertEqual(_highlight_numbers(claim), ["0.9804", "0.8799"])

    def test_highlight_ignores_bracketed_citation_numbers(self) -> None:
        claim = "The method improves PSNR by 0.48 dB over BebyGAN [23]."
        self.assertEqual(_highlight_numbers(claim), ["0.48"])

    def test_highlight_repairs_missing_space_before_percentage(self) -> None:
        claim = "The model reaches higher accuracy with only26% of the computational cost."
        self.assertEqual(_highlight_numbers(claim), ["26%"])

    def test_sentence_splitter_preserves_figure_reference(self) -> None:
        self.assertEqual(
            sentences("The architecture is depicted in Fig. 2. It is compact."),
            ["The architecture is depicted in Fig. 2.", "It is compact."],
        )

    def test_project_panel_reports_code_availability(self) -> None:
        open_source = _project_content(
            {
                "code_url": "https://github.com/example/project",
                "paper_url": "https://arxiv.org/abs/2403.11423",
            }
        )
        self.assertIn("Code: Open source", open_source)
        self.assertIn("https://github.com/example/project", open_source)
        self.assertIn("Paper:", open_source)

        closed_source = _project_content({"paper_url": "https://example.com/paper"})
        self.assertIn("Code not publicly available", closed_source)

    def test_delivery_policy_softens_only_presentation_sparsity(self) -> None:
        issues = [
            {"code": "HIGHLIGHT_EVIDENCE_INSUFFICIENT", "severity": "error"},
            {"code": "MOTIVATION_EVIDENCE_INSUFFICIENT", "severity": "error"},
            {"code": "KEY_IDEA_HEADLINE_WEAK", "severity": "error"},
            {
                "code": "OVERFLOW_ELEMENTS",
                "severity": "error",
                "details": [
                    {
                        "panel": "contributions",
                        "clientWidth": 900,
                        "scrollWidth": 900,
                        "clientHeight": 195,
                        "scrollHeight": 201,
                    }
                ],
            },
            {"code": "RESULT_MIXED_EVALUATION_CONTEXT", "severity": "error"},
            {"code": "RESULT_METRIC_COUNT_INVALID", "severity": "error"},
            {"code": "RESULT_TABLE_FOCUS_CROP_REQUIRED", "severity": "error"},
            {"code": "RESULT_FOCUS_TABLE_UNREADABLE", "severity": "error"},
            {"code": "MOTIVATION_COVERAGE_CHECK", "severity": "error"},
            {"code": "CONTRIBUTION_EVIDENCE_INSUFFICIENT", "severity": "error"},
            {"code": "CONTRIBUTION_DISPLAYABLE_COUNT_CHECK", "severity": "error"},
            {
                "code": "RESULT_ASSET_PROVENANCE_INCOMPLETE",
                "severity": "error",
                "details": {
                    "missing_fields": ["caption"],
                    "invalid_claim_ids": [],
                    "invalid_block_ids": [],
                },
            },
            {
                "code": "RESULT_ASSET_PROVENANCE_INCOMPLETE",
                "severity": "error",
                "details": {
                    "missing_fields": ["bbox"],
                    "invalid_claim_ids": [],
                    "invalid_block_ids": [],
                },
            },
            {
                "code": "METHOD_FIGURE_ROLE_CONFLICT",
                "severity": "error",
                "details": [
                    {
                        "code": "PROPOSED_SUBFIGURE_EXCLUDED_FROM_METHOD",
                        "focus_subfigure_labels": ["g"],
                    }
                ],
            },
            {
                "code": "METHOD_FIGURE_ROLE_CONFLICT",
                "severity": "error",
                "details": [
                    {
                        "code": "METHOD_CITED_FIGURE_EXCLUDED",
                        "focus_subfigure_labels": [],
                    }
                ],
            },
            {
                "code": "METHOD_FALLBACK_RENDER_INVALID",
                "severity": "error",
                "details": {"expected": 6, "rendered": 4, "empty": []},
            },
            {
                "code": "METHOD_FALLBACK_RENDER_INVALID",
                "severity": "error",
                "details": {"expected": 3, "rendered": 0, "empty": []},
            },
            {"code": "METHOD_MODULE_BINDING_CONFLICT", "severity": "error"},
            {"code": "CONTENT_TRUNCATED", "severity": "error"},
        ]
        normalized = _apply_delivery_severity_policy(
            issues,
            key_visual_item_count=1,
            motivation_item_count=1,
            contribution_item_count=1,
        )
        severities = {
            item["code"]: item["severity"] for item in normalized
        }
        self.assertEqual(
            severities["HIGHLIGHT_EVIDENCE_INSUFFICIENT"],
            "warning",
        )
        self.assertEqual(
            severities["MOTIVATION_EVIDENCE_INSUFFICIENT"],
            "warning",
        )
        self.assertEqual(severities["KEY_IDEA_HEADLINE_WEAK"], "warning")
        self.assertEqual(severities["OVERFLOW_ELEMENTS"], "warning")
        self.assertEqual(
            severities["RESULT_MIXED_EVALUATION_CONTEXT"],
            "warning",
        )
        self.assertEqual(
            severities["RESULT_METRIC_COUNT_INVALID"],
            "warning",
        )
        self.assertEqual(
            severities["RESULT_TABLE_FOCUS_CROP_REQUIRED"],
            "warning",
        )
        self.assertEqual(severities["RESULT_FOCUS_TABLE_UNREADABLE"], "warning")
        self.assertEqual(severities["MOTIVATION_COVERAGE_CHECK"], "warning")
        self.assertEqual(
            severities["CONTRIBUTION_EVIDENCE_INSUFFICIENT"],
            "warning",
        )
        self.assertEqual(
            severities["CONTRIBUTION_DISPLAYABLE_COUNT_CHECK"],
            "warning",
        )
        minor_provenance, hard_provenance = [
            item
            for item in normalized
            if item["code"] == "RESULT_ASSET_PROVENANCE_INCOMPLETE"
        ]
        self.assertEqual(minor_provenance["severity"], "warning")
        self.assertEqual(
            minor_provenance["delivery_policy"],
            "minor_result_caption_gap",
        )
        self.assertEqual(hard_provenance["severity"], "error")
        minor_role, hard_role = [
            item
            for item in normalized
            if item["code"] == "METHOD_FIGURE_ROLE_CONFLICT"
        ]
        self.assertEqual(minor_role["severity"], "warning")
        self.assertEqual(
            minor_role["delivery_policy"],
            "ambiguous_proposed_subfigure_role",
        )
        self.assertEqual(hard_role["severity"], "error")
        method_fallback = [
            item
            for item in normalized
            if item["code"] == "METHOD_FALLBACK_RENDER_INVALID"
        ]
        self.assertEqual(method_fallback[0]["severity"], "warning")
        self.assertEqual(
            method_fallback[0]["delivery_policy"],
            "adaptive_method_card_density",
        )
        self.assertEqual(
            method_fallback[1]["severity"],
            "error",
        )
        self.assertEqual(
            severities["METHOD_MODULE_BINDING_CONFLICT"],
            "error",
        )
        self.assertEqual(severities["CONTENT_TRUNCATED"], "error")

    def test_global_visible_text_audit_blocks_malformed_text_only(
        self,
    ) -> None:
        issues = _global_visible_text_issues(
            {
                "key_idea": {
                    "headline": "Residual learning supports low-dose CT reconstruction.",
                    "visual": {
                        "items": [
                            {
                                "label": "Residual autoencoder",
                                "text": "The network has an origin in the work.",
                            }
                        ]
                    },
                },
                "method_detail": {
                    "experimental_design": {
                        "text": "We employed the reported training schedule."
                    }
                },
            }
        )
        self.assertEqual(issues[0]["code"], "VISIBLE_TEXT_INTEGRITY_FAILED")
        self.assertEqual(len(issues[0]["details"]), 1)
        findings = {
            finding
            for detail in issues[0]["details"]
            for finding in detail["findings"]
        }
        self.assertIn("malformed_visible_text_check", findings)
        self.assertNotIn("author_voice_check", findings)

    def test_global_visible_text_audit_allows_author_voice(self) -> None:
        self.assertFalse(
            _global_visible_text_issues(
                {
                    "method_detail": {
                        "experimental_design": {
                            "text": "We employed the reported training schedule."
                        }
                    },
                    "contributions": [
                        {
                            "visible_text": (
                                "In this paper, we propose a compact attention "
                                "module for cross-scale feature exchange."
                            )
                        }
                    ],
                }
            )
        )

    def test_global_visible_text_audit_accepts_neutral_complete_text(self) -> None:
        self.assertFalse(
            _global_visible_text_issues(
                {
                    "key_idea": {
                        "headline": (
                            "Residual connections preserve image detail during "
                            "low-dose CT reconstruction."
                        ),
                        "visual": {
                            "items": [
                                {
                                    "label": "Residual autoencoder",
                                    "text": (
                                        "Encoder and decoder paths exchange "
                                        "features through residual links."
                                    ),
                                }
                            ]
                        },
                    }
                }
            )
        )

    def test_collect_panel_text_ignores_result_provenance_cells(self) -> None:
        values = _collect_panel_text(
            {
                "experimental_results": {
                    "key_metrics": [
                        {
                            "value": "96.21",
                            "baseline_value": "96.02",
                            "source_cell": {
                                "value": "96.21",
                                "extracted_value": "96.21",
                            },
                            "baseline_cell": {
                                "value": "02=0.158",
                                "extracted_value": "96.02",
                            },
                        }
                    ]
                }
            }
        )
        self.assertIn("96.21", values)
        self.assertNotIn("02=0.158", values)

    def test_compose_sanitizes_real_visible_text_failure_patterns(self) -> None:
        samples = [
            "Stated another way.",
            "Stated another way, the\uFFFD.",
            (
                "Three public datasets, including ISIC 2017, ISIC 2018, "
                "and PH, are used in this paper for evaluating the "
                "performance of our methods in comparison against the "
                "state-of-the-arts."
            ),
            (
                "Following in, we utilize 18 CT scans (2,212 axial slices) "
                "for training and the remaining 12 CT scans for testing."
            ),
            "On the ACDC dataset, we use Dice as the sole performance metric.",
            "Here we adopt the differential.",
            "Datasets and Settings.",
            (
                "and most importantly, the Cross-scale Spatial Attention "
                "(CSA) module and, for the first time in this architecture lineage."
            ),
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                cleaned = _sanitize_panel_text(sample)
                self.assertFalse(visible_text_findings(cleaned), cleaned)

    def test_visible_text_allows_complete_while_clauses(self) -> None:
        samples = [
            (
                "While MSHNet performed better than the baseline with the "
                "combined approach, it did not surpass the performance of "
                "PConv with SDM loss alone."
            ),
            (
                "While ScaleFusionNet maintains a higher accuracy, its "
                "computational complexity is higher compared to some methods."
            ),
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertFalse(visible_text_findings(sample), sample)

    def test_candidate_render_is_promoted_or_kept_as_debug(self) -> None:
        with tempfile.TemporaryDirectory(prefix="render-finalize-") as temp:
            root = Path(temp)
            candidate = root / "poster-candidate.html"
            candidate.write_text(
                '<body data-preview-status="valid">Poster</body>',
                encoding="utf-8",
            )
            bundle_path = root / "render_bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "status": "candidate_rendered",
                        "candidate_output": True,
                        "formal_output_allowed": True,
                        "browser_export_requested": False,
                        "html_path": str(candidate),
                        "png_path": None,
                        "pdf_path": None,
                        "metrics_path": None,
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            finalize_render_bundle(bundle_path, "passed_with_warnings")
            promoted = read_json(bundle_path)
            self.assertEqual(
                promoted["delivery_status"],
                "usable_with_warnings",
            )
            self.assertEqual(Path(promoted["html_path"]).name, "poster.html")
            self.assertFalse(candidate.exists())

            debug_candidate = root / "poster-candidate.html"
            debug_candidate.write_text(
                '<body data-preview-status="valid">Poster</body>',
                encoding="utf-8",
            )
            bundle_path.write_text(
                json.dumps(
                    {
                        "status": "candidate_rendered",
                        "candidate_output": True,
                        "formal_output_allowed": True,
                        "browser_export_requested": False,
                        "html_path": str(debug_candidate),
                        "png_path": None,
                        "pdf_path": None,
                        "metrics_path": None,
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            finalize_render_bundle(bundle_path, "failed")
            blocked = read_json(bundle_path)
            debug_html = Path(blocked["html_path"])
            self.assertEqual(blocked["delivery_status"], "blocked")
            self.assertEqual(debug_html.name, "poster-debug.html")
            self.assertIn(
                'data-preview-status="invalid"',
                debug_html.read_text(encoding="utf-8"),
            )

    def test_method_graph_recovers_ieee_named_method_region(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "exfusion",
            "metadata": {
                "title": "ExFusion: Efficient Transformer Training via Multi-Experts Fusion",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h1",
                    "type": "heading",
                    "text": "III. PRELIMINARIES",
                    "page": 3,
                    "section_id": "iii-preliminaries",
                    "section_title": "III. PRELIMINARIES",
                },
                {
                    "id": "p1",
                    "type": "paragraph",
                    "text": "A Transformer contains attention and feed-forward layers.",
                    "page": 3,
                    "section_id": "a-transformer",
                    "section_title": "A. Transformer",
                },
                {
                    "id": "h2",
                    "type": "heading",
                    "text": "IV. MULTI-EXPERTS FUSION (EXFUSION)",
                    "page": 4,
                    "section_id": "iv-multi-experts-fusion-exfusion",
                    "section_title": "IV. MULTI-EXPERTS FUSION (EXFUSION)",
                },
                {
                    "id": "p-motivation",
                    "type": "paragraph",
                    "text": (
                        "MoE models require substantially more parameters and "
                        "training resources than dense models."
                    ),
                    "page": 4,
                    "section_id": "a-motivation",
                    "section_title": "A. Motivation",
                },
                {
                    "id": "p2",
                    "type": "paragraph",
                    "text": "We fuse multiple experts with uniform static weights.",
                    "page": 4,
                    "section_id": "b-static-weights-exfusion",
                    "section_title": "B. Static-Weights ExFusion",
                },
                {
                    "id": "p3",
                    "type": "paragraph",
                    "text": "We use learnable weights to combine experts dynamically.",
                    "page": 4,
                    "section_id": "c-dynamic-weights-exfusion",
                    "section_title": "C. Dynamic-Weights ExFusion",
                },
                {
                    "id": "p4",
                    "type": "paragraph",
                    "text": "We introduce a router and memory bank for data-dependent fusion.",
                    "page": 5,
                    "section_id": "d-memory-bank-exfusion",
                    "section_title": "D. Memory-Bank ExFusion",
                },
                {
                    "id": "h3",
                    "type": "heading",
                    "text": "V. EXPERIMENTS",
                    "page": 5,
                    "section_id": "v-experiments",
                    "section_title": "V. EXPERIMENTS",
                },
                {
                    "id": "h4",
                    "type": "heading",
                    "text": "VI. DISCUSSION AND LIMITATION",
                    "page": 6,
                    "section_id": "vi-discussion-and-limitation",
                    "section_title": "VI. DISCUSSION AND LIMITATION",
                },
                {
                    "id": "p5",
                    "type": "paragraph",
                    "text": "Efficient tuning methods optimize existing architectures.",
                    "page": 6,
                    "section_id": "d-distinction-from-other-methods",
                    "section_title": "D. Distinction from Other Methods",
                },
            ],
            "figures": [],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="named-method-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, _ = build_method_graph(source, root / "out")
            graph = read_json(graph_path)
        self.assertEqual(graph["selection_basis"], "named_method_heading")
        self.assertEqual(len(graph["nodes"]), 3)
        self.assertEqual(
            [node["section_id"] for node in graph["nodes"]],
            [
                "b-static-weights-exfusion",
                "c-dynamic-weights-exfusion",
                "d-memory-bank-exfusion",
            ],
        )
        self.assertNotIn(
            "a-motivation",
            {node["section_id"] for node in graph["nodes"]},
        )

    def test_method_graph_recovers_unpunctuated_numeric_method_heading(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "medcore",
            "metadata": {
                "title": "MedCore: Boundary-Preserving Medical Core Pruning",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h1",
                    "type": "heading",
                    "text": "2 Related Work",
                    "page": 2,
                    "section_id": "2-related-work",
                    "section_title": "2 Related Work",
                },
                {
                    "id": "p1",
                    "type": "paragraph",
                    "text": "Prior pruning methods estimate parameter importance.",
                    "page": 2,
                    "section_id": "2-related-work",
                    "section_title": "2 Related Work",
                },
                {
                    "id": "h2",
                    "type": "heading",
                    "text": "3 MedCore: Boundary-Preserving Medical Core Pruning",
                    "page": 3,
                    "section_id": "3-medcore-boundary-preserving-medical-core-pruning",
                    "section_title": "3 MedCore: Boundary-Preserving Medical Core Pruning",
                },
                {
                    "id": "p2",
                    "type": "paragraph",
                    "text": (
                        "We propose MedCore and first score medically adapted "
                        "structures using dual intervention."
                    ),
                    "page": 3,
                    "section_id": "3-medcore-boundary-preserving-medical-core-pruning",
                    "section_title": "3 MedCore: Boundary-Preserving Medical Core Pruning",
                },
                {
                    "id": "p3",
                    "type": "paragraph",
                    "text": (
                        "We estimate boundary-aware Fisher scores and "
                        "we allocate the pruning budget."
                    ),
                    "page": 4,
                    "section_id": "3-4-boundary-aware-fisher",
                    "section_title": "3.4 Boundary-Aware Fisher",
                },
                {
                    "id": "h3",
                    "type": "heading",
                    "text": "4 Experiments",
                    "page": 5,
                    "section_id": "4-experiments",
                    "section_title": "4 Experiments",
                },
            ],
            "figures": [],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="method-numeric-heading-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, report_path = build_method_graph(source, root / "out")
            graph = read_json(graph_path)
            report = read_json(report_path)
        self.assertGreaterEqual(len(graph["nodes"]), 1)
        self.assertEqual(report["selection_basis"], "named_method_heading")

    def test_formula_heavy_sentence_is_not_split_into_method_modules(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "gt-dla",
            "metadata": {
                "title": "Global Transformer and Dual Local Attention Network",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h1",
                    "type": "heading",
                    "text": "III. METHODS",
                    "page": 3,
                    "section_id": "iii-methods",
                    "section_title": "III. METHODS",
                },
                {
                    "id": "p1",
                    "type": "paragraph",
                    "text": (
                        "The architecture receives $H \\times W \\times C$ "
                        "features, including $1 \\times D$ patches. In addition, "
                        "prior work indicates that recurrent networks differ "
                        "from transformer structures."
                    ),
                    "page": 3,
                    "section_id": "a-global-transformer",
                    "section_title": "A. Global Transformer",
                },
                {
                    "id": "p2",
                    "type": "paragraph",
                    "text": (
                        "We use cascaded transformer encoders to recover global "
                        "context for fine-vessel segmentation."
                    ),
                    "page": 4,
                    "section_id": "a-global-transformer",
                    "section_title": "A. Global Transformer",
                },
                {
                    "id": "p3",
                    "type": "paragraph",
                    "text": (
                        "We propose dual local attention to recover multiscale "
                        "local vessel details."
                    ),
                    "page": 4,
                    "section_id": "b-dual-local-attention",
                    "section_title": "B. Dual Local Attention",
                },
                {
                    "id": "p4",
                    "type": "paragraph",
                    "text": (
                        "We propose deep-shallow hierarchical feature fusion "
                        "to combine semantic and spatial details."
                    ),
                    "page": 5,
                    "section_id": "c-deep-shallow-hierarchical-feature-fusion",
                    "section_title": "C. Deep-Shallow Hierarchical Feature Fusion",
                },
                {
                    "id": "h2",
                    "type": "heading",
                    "text": "IV. EXPERIMENTS",
                    "page": 6,
                    "section_id": "iv-experiments",
                    "section_title": "IV. EXPERIMENTS",
                },
            ],
            "figures": [],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="method-formula-list-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, _ = build_method_graph(source, root / "out")
            graph = read_json(graph_path)
        self.assertEqual(
            [node["name"] for node in graph["nodes"]],
            [
                "A. Global Transformer",
                "B. Dual Local Attention",
                "C. Deep-Shallow Hierarchical Feature Fusion",
            ],
        )

    def test_variant_specific_overviews_are_combined(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "split-overview",
            "metadata": {"title": "ExFusion", "authors": [], "affiliations": []},
            "blocks": [
                {
                    "id": "h1",
                    "type": "heading",
                    "text": "V. EXPERIMENTS",
                    "page": 6,
                    "section_id": "v-experiments",
                    "section_title": "V. EXPERIMENTS",
                },
                {
                    "id": "p1",
                    "type": "paragraph",
                    "text": (
                        "All main experiments train and evaluate ExFusion-mb. "
                        "ExFusion-mb is the adopted model used for downstream tasks."
                    ),
                    "page": 6,
                    "section_id": "v-experiments",
                    "section_title": "V. EXPERIMENTS",
                },
            ],
            "figures": [
                {
                    "id": "figure-sw-dw",
                    "caption": "Overall architecture of ExFusion-sw and ExFusion-dw.",
                    "page": 4,
                    "section_id": "method",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
                {
                    "id": "figure-mb",
                    "caption": "Overall architecture of ExFusion-mb with router and memory bank.",
                    "page": 5,
                    "section_id": "method",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
            ],
            "equations": [],
            "tables": [],
        }
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "split-overview",
            "nodes": [
                {
                    "id": "sw",
                    "order": 1,
                    "name": "Static-Weights ExFusion (ExFusion-sw)",
                    "purpose": "Fuse experts with static weights.",
                    "innovation": "Static fusion.",
                    "section_id": "b-exfusion-sw",
                    "section_title": "ExFusion-sw",
                    "sources": [],
                },
                {
                    "id": "dw",
                    "order": 2,
                    "name": "Dynamic-Weights ExFusion (ExFusion-dw)",
                    "purpose": "Learn expert fusion weights.",
                    "innovation": "Dynamic fusion.",
                    "section_id": "c-exfusion-dw",
                    "section_title": "ExFusion-dw",
                    "sources": [],
                },
                {
                    "id": "mb",
                    "order": 3,
                    "name": "Memory-Bank ExFusion (ExFusion-mb)",
                    "purpose": "Use a router and memory bank.",
                    "innovation": "Data-dependent fusion.",
                    "section_id": "d-exfusion-mb",
                    "section_title": "ExFusion-mb",
                    "sources": [],
                },
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory(prefix="variant-overviews-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "graph.json"
            catalog_path = root / "catalog.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"figures": paper_ir["figures"]}),
                encoding="utf-8",
            )
            figure_map_path, _ = map_method_figures(
                paper_path,
                graph_path,
                catalog_path,
                root / "assets",
            )
            visual_path, _ = compose_method_visual(
                paper_path,
                graph_path,
                figure_map_path,
                root / "poster",
            )
            figure_map = read_json(figure_map_path)
            visual = read_json(visual_path)
        self.assertEqual(visual["mode"], "overview_plus_details")
        self.assertEqual(visual["overview_asset_id"], "figure-mb")
        self.assertEqual(
            figure_map["overview_selection_basis"],
            "primary_variant_evidence",
        )
        self.assertFalse(figure_map["overview_selection_ambiguous"])
        self.assertEqual(
            [
                item["asset_id"]
                for item in visual["storyboard_items"]
                if item["display_mode"] == "original_figure"
            ],
            ["figure-sw-dw"],
        )
        fallback_items = [
            item
            for item in visual["storyboard_items"]
            if item["display_mode"] == "mechanism_flow"
        ]
        self.assertEqual(len(fallback_items), 1)
        self.assertEqual(fallback_items[0]["module_ids"], ["mb"])
        self.assertEqual(
            visual["storyboard_items"][0]["module_ids"],
            ["sw", "dw"],
        )
        self.assertEqual(visual["module_coverage_ratio"], 1.0)

    def test_proposed_method_diagram_stays_above_named_module_diagrams(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "retinal-network",
            "metadata": {
                "title": (
                    "Global Transformer and Dual Local Attention Network via "
                    "Deep-Shallow Hierarchical Feature Fusion"
                ),
                "authors": [],
                "affiliations": [],
            },
            "blocks": [],
            "figures": [
                {
                    "id": "figure-total",
                    "caption": "Diagram of the proposed GT-DLA-dsHFF method.",
                    "page": 3,
                    "section_id": "introduction",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
                {
                    "id": "figure-gt",
                    "caption": "Diagram of GT.",
                    "page": 4,
                    "section_id": "methodology",
                    "path": None,
                    "context_before": (
                        "The proposed framework contains GT, DLA, and dsHFF."
                    ),
                    "context_after": "Global Transformer",
                    "cited_by": [],
                },
                {
                    "id": "figure-dla",
                    "caption": "Diagram of DLA.",
                    "page": 5,
                    "section_id": "global-transformer",
                    "path": None,
                    "context_before": "",
                    "context_after": "Dual Local Attention",
                    "cited_by": [],
                },
                {
                    "id": "figure-dshff",
                    "caption": "Diagram of dsHFF.",
                    "page": 6,
                    "section_id": "feature-fusion",
                    "path": None,
                    "context_before": "",
                    "context_after": "Deep-Shallow Hierarchical Feature Fusion",
                    "cited_by": [],
                },
            ],
            "equations": [],
            "tables": [],
        }
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "retinal-network",
            "nodes": [
                {
                    "id": "gt",
                    "order": 1,
                    "name": "Global Transformer",
                    "purpose": "Capture global information.",
                    "innovation": "Global Transformer.",
                    "section_id": "global-transformer",
                    "section_title": "Global Transformer",
                    "sources": [],
                },
                {
                    "id": "dla",
                    "order": 2,
                    "name": "Dual Local Attention",
                    "purpose": "Capture local information.",
                    "innovation": "Dual Local Attention.",
                    "section_id": "dual-local-attention",
                    "section_title": "Dual Local Attention",
                    "sources": [],
                },
                {
                    "id": "dshff",
                    "order": 3,
                    "name": "Deep-Shallow Hierarchical Feature Fusion",
                    "purpose": "Fuse deep and shallow features.",
                    "innovation": "Hierarchical feature fusion.",
                    "section_id": "feature-fusion",
                    "section_title": "Deep-Shallow Hierarchical Feature Fusion",
                    "sources": [],
                },
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory(prefix="retinal-overview-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "graph.json"
            catalog_path = root / "catalog.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"figures": paper_ir["figures"]}),
                encoding="utf-8",
            )
            figure_map_path, _ = map_method_figures(
                paper_path,
                graph_path,
                catalog_path,
                root / "assets",
            )
            visual_path, _ = compose_method_visual(
                paper_path,
                graph_path,
                figure_map_path,
                root / "poster",
            )
            figure_map = read_json(figure_map_path)
            visual = read_json(visual_path)
        roles = {
            record["asset_id"]: record["role"]
            for record in figure_map["records"]
        }
        self.assertEqual(roles["figure-total"], "method_overview")
        self.assertEqual(roles["figure-gt"], "method_module")
        self.assertEqual(figure_map["overview_asset_id"], "figure-total")
        self.assertEqual(visual["mode"], "overview_plus_details")
        self.assertEqual(visual["overview_asset_id"], "figure-total")
        self.assertEqual(
            [item["asset_id"] for item in visual["storyboard_items"]],
            ["figure-gt", "figure-dla", "figure-dshff"],
        )

    def test_dsformer_module_figures_bind_exclusively_and_both_render(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "dsformer",
            "metadata": {
                "title": (
                    "Dual Selective Fusion Transformer Network for "
                    "Hyperspectral Image Classification"
                ),
                "authors": [],
                "affiliations": [],
            },
            "blocks": [],
            "figures": [
                {
                    "id": "figure-2",
                    "caption": (
                        "Figure 2: An illustration of the proposed DSFormer. "
                        "The Dual Selective Fusion Transformer Group is composed "
                        "of a KSFTB and three consecutive TSFTBs."
                    ),
                    "page": 3,
                    "section_id": "3-1-overview",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
                {
                    "id": "figure-3",
                    "caption": (
                        "Figure 3: The proposed Kernel Selective Fusion "
                        "Attention (KSFA)."
                    ),
                    "page": 4,
                    "section_id": "3-2-ksftb",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
                {
                    "id": "figure-4",
                    "caption": (
                        "Figure 4: The illustration of the proposed Token "
                        "Selective Fusion Attention (TSFA)."
                    ),
                    "page": 5,
                    "section_id": "3-3-tsftb",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
            ],
            "equations": [],
            "tables": [],
        }
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "dsformer",
            "nodes": [
                {
                    "id": "ksftb",
                    "order": 1,
                    "name": "Kernel Selective Fusion Transformer Block",
                    "purpose": (
                        "KSFTB contains Kernel Selective Fusion Attention "
                        "(KSFA) and an FFN."
                    ),
                    "innovation": "Adaptively select receptive-field kernels.",
                    "section_id": "3-2-ksftb",
                    "section_title": "Kernel Selective Fusion Transformer Block",
                    "sources": [],
                },
                {
                    "id": "tsftb",
                    "order": 2,
                    "name": "Token Selective Fusion Transformer Block",
                    "purpose": (
                        "TSFTB contains Token Selective Fusion Attention "
                        "(TSFA) and an FFN."
                    ),
                    "innovation": "Select informative tokens before attention.",
                    "section_id": "3-3-tsftb",
                    "section_title": "Token Selective Fusion Transformer Block",
                    "sources": [],
                },
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory(prefix="dsformer-module-map-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "graph.json"
            catalog_path = root / "catalog.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"figures": paper_ir["figures"]}),
                encoding="utf-8",
            )
            figure_map_path, _ = map_method_figures(
                paper_path,
                graph_path,
                catalog_path,
                root / "assets",
            )
            visual_path, _ = compose_method_visual(
                paper_path,
                graph_path,
                figure_map_path,
                root / "poster",
            )
            figure_map = read_json(figure_map_path)
            visual = read_json(visual_path)

        records = {
            record["asset_id"]: record
            for record in figure_map["records"]
        }
        self.assertEqual(records["figure-2"]["role"], "method_overview")
        self.assertEqual(records["figure-3"]["role"], "method_module")
        self.assertEqual(records["figure-4"]["role"], "method_module")
        self.assertEqual(
            [item["module_id"] for item in records["figure-3"]["module_mappings"]],
            ["ksftb"],
        )
        self.assertEqual(
            [item["module_id"] for item in records["figure-4"]["module_mappings"]],
            ["tsftb"],
        )
        self.assertEqual(
            records["figure-3"]["module_mappings"][0]["match_kind"],
            "exact_unique_alias",
        )
        self.assertEqual(
            records["figure-4"]["module_mappings"][0]["match_kind"],
            "exact_unique_alias",
        )
        self.assertEqual(
            [item["asset_id"] for item in visual["storyboard_items"]],
            ["figure-3", "figure-4"],
        )
        self.assertEqual(visual["omitted_dedicated_module_ids"], [])

    def test_dedicated_details_keep_distinct_sibling_modules(self) -> None:
        graph = {
            "nodes": [
                {
                    "id": "encoder",
                    "order": 1,
                    "name": "Encoder",
                    "purpose": "The encoder contains LFE and GFE blocks.",
                }
            ]
        }
        figure_map = {
            "module_alias_index": {"encoder": ["lfe", "gfe"]},
            "records": [
                {
                    "asset_id": "figure-2",
                    "role": "method_module",
                    "caption": "Figure 2. Details of the LFE block.",
                    "caption_aliases": ["lfe"],
                    "exclusive_alias_owner_ids": ["encoder"],
                    "module_mappings": [
                        {
                            "module_id": "encoder",
                            "score": 1.0,
                            "match_kind": "exact_unique_alias",
                        }
                    ],
                },
                {
                    "asset_id": "figure-3",
                    "role": "method_module",
                    "caption": "Figure 3. Details of the GFE block.",
                    "caption_aliases": ["gfe"],
                    "exclusive_alias_owner_ids": ["encoder"],
                    "module_mappings": [
                        {
                            "module_id": "encoder",
                            "score": 1.0,
                            "match_kind": "exact_unique_alias",
                        }
                    ],
                },
            ],
        }

        details = _dedicated_module_details(graph, figure_map)

        self.assertEqual(
            [record["asset_id"] for record in details],
            ["figure-2", "figure-3"],
        )

    def test_rccformer_mixed_subfigure_and_idconv_are_method_details(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "rccformer",
            "metadata": {
                "title": (
                    "RCCFormer: A Robust Crowd Counting Network Based on "
                    "Transformer"
                ),
                "authors": [],
                "affiliations": [],
            },
            "blocks": [],
            "figures": [
                {
                    "id": "figure-2",
                    "caption": (
                        "Figure 2: Different multi-level fusion methods. "
                        "(a) elementwise addition; (b) concatenation; "
                        "(c) our strong baseline."
                    ),
                    "page": 4,
                    "section_id": "3-1-strong-baseline",
                    "path": None,
                    "context_before": (
                        "We propose a Multi-level Feature Fusion Module "
                        "via cross attention as shown in Fig. 2(c)."
                    ),
                    "context_after": (
                        "Cross attention obtains the final fusion result."
                    ),
                    "cited_by": ["b-strong"],
                },
                {
                    "id": "figure-3",
                    "caption": (
                        "Figure 3: The overall framework of the proposed "
                        "RCCFormer with MFFM, DEAB, and ASAM."
                    ),
                    "page": 5,
                    "section_id": "3-2-rccformer",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": [],
                },
                {
                    "id": "figure-4",
                    "caption": (
                        "Figure 4: Illustration of the proposed "
                        "Detail-Embedded Attention."
                    ),
                    "page": 6,
                    "section_id": "3-2-1-deab",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": ["b-deab"],
                },
                {
                    "id": "figure-5",
                    "caption": (
                        "Figure 5: Illustration of the proposed "
                        "Input-dependent Deformable Convolution."
                    ),
                    "page": 6,
                    "section_id": "3-2-2-asam",
                    "path": None,
                    "context_before": "",
                    "context_after": "",
                    "cited_by": ["b-asam"],
                },
            ],
            "equations": [],
            "tables": [],
        }
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "rccformer",
            "nodes": [
                {
                    "id": "strong",
                    "order": 1,
                    "name": "Strong Baseline",
                    "purpose": "Fuse multi-level features with cross attention.",
                    "innovation": "Multi-level Feature Fusion Module.",
                    "section_id": "3-1-strong-baseline",
                    "section_title": "Strong Baseline",
                    "figure_refs": ["figure-2"],
                    "sources": [{"block_id": "b-strong"}],
                },
                {
                    "id": "deab",
                    "order": 2,
                    "name": "Detail-Embedded Attention Block",
                    "purpose": "Combine global context and local details.",
                    "innovation": "Detail-Embedded Attention.",
                    "section_id": "3-2-1-deab",
                    "section_title": "Detail-Embedded Attention Block",
                    "figure_refs": ["figure-4"],
                    "sources": [{"block_id": "b-deab"}],
                },
                {
                    "id": "asam",
                    "order": 3,
                    "name": "Adaptive Scale-Aware Module",
                    "purpose": (
                        "Use Input-dependent Deformable Convolution for "
                        "scale-aware perception."
                    ),
                    "innovation": "Input-dependent Deformable Convolution.",
                    "section_id": "3-2-2-asam",
                    "section_title": "Adaptive Scale-Aware Module",
                    "figure_refs": ["figure-5"],
                    "sources": [{"block_id": "b-asam"}],
                },
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory(prefix="rccformer-method-map-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "graph.json"
            catalog_path = root / "catalog.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"figures": paper_ir["figures"]}),
                encoding="utf-8",
            )
            figure_map_path, _ = map_method_figures(
                paper_path,
                graph_path,
                catalog_path,
                root / "assets",
            )
            visual_path, _ = compose_method_visual(
                paper_path,
                graph_path,
                figure_map_path,
                root / "poster",
            )
            figure_map = read_json(figure_map_path)
            visual = read_json(visual_path)

        records = {
            record["asset_id"]: record
            for record in figure_map["records"]
        }
        self.assertEqual(records["figure-2"]["role"], "method_module")
        self.assertEqual(records["figure-2"]["focus_subfigure_labels"], ["c"])
        self.assertNotIn("figure-2", figure_map["result_excluded_ids"])
        self.assertEqual(records["figure-5"]["role"], "method_module")
        self.assertEqual(records["figure-5"]["referenced_node_ids"], ["asam"])
        self.assertEqual(figure_map["role_conflicts"], [])
        self.assertEqual(visual["overview_asset_id"], "figure-3")
        self.assertEqual(
            [item["asset_id"] for item in visual["storyboard_items"]],
            ["figure-2", "figure-4", "figure-5"],
        )
        self.assertEqual(
            visual["storyboard_items"][0]["focus_subfigure_labels"],
            ["c"],
        )

    def test_parent_module_figure_covers_named_children_not_noisy_reference(
        self,
    ) -> None:
        figure = {
            "id": "figure-2",
            "caption": (
                "Fig. 2. Architecture of the proposed Adaptive Rotation "
                "Attention (ARA) module."
            ),
            "page": 5,
            "section_id": "2-3-adaptive-rotation-attention",
            "path": None,
            "cited_by": ["pcr-block", "ara-block"],
        }
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "nested-module",
            "metadata": {
                "title": "Multi-Oriented Vessel Preservation Network"
            },
            "blocks": [],
            "figures": [figure],
            "equations": [],
            "tables": [],
        }
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "nested-module",
            "nodes": [
                {
                    "id": "pcr",
                    "order": 1,
                    "name": "Pinwheel Convolution Residual HDWT",
                    "purpose": "Preserve vessel details during downsampling.",
                    "innovation": "PCR-HDWT.",
                    "section_id": "2-2-pcr",
                    "section_title": "PCR-HDWT",
                    "figure_refs": ["figure-2"],
                    "sources": [{"block_id": "pcr-block"}],
                },
                {
                    "id": "ara",
                    "order": 2,
                    "name": "Adaptive Rotation Attention",
                    "purpose": (
                        "ARA contains an Orientation-Adaptive Attention "
                        "Branch and a Query-Key Cache Updating (QKCU) Block."
                    ),
                    "innovation": "Adaptive Rotation Attention.",
                    "section_id": "2-3-ara",
                    "section_title": "Adaptive Rotation Attention",
                    "figure_refs": ["figure-2"],
                    "sources": [{"block_id": "ara-block"}],
                },
                {
                    "id": "orientation",
                    "order": 3,
                    "name": "Orientation-Adaptive Attention Branch",
                    "purpose": "Rotate relative position bias.",
                    "innovation": "Orientation-adaptive bias.",
                    "section_id": "orientation-branch",
                    "section_title": "Orientation-Adaptive Attention Branch",
                    "figure_refs": [],
                    "sources": [{"block_id": "orientation-block"}],
                },
                {
                    "id": "qkcu",
                    "order": 4,
                    "name": "Query-Key Cache Updating Block",
                    "purpose": "Share query-key information between heads.",
                    "innovation": "QKCU.",
                    "section_id": "qkcu-block",
                    "section_title": "Query-Key Cache Updating Block",
                    "figure_refs": [],
                    "sources": [{"block_id": "qkcu-block"}],
                },
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory(prefix="nested-method-map-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "graph.json"
            catalog_path = root / "catalog.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"figures": [figure]}),
                encoding="utf-8",
            )
            figure_map_path, _ = map_method_figures(
                paper_path,
                graph_path,
                catalog_path,
                root / "assets",
            )
            figure_map = read_json(figure_map_path)
        record = figure_map["records"][0]
        mappings = {
            item["module_id"]: item["match_kind"]
            for item in record["module_mappings"]
        }
        self.assertEqual(record["role"], "method_module")
        self.assertNotIn("pcr", mappings)
        self.assertEqual(mappings["ara"], "explicit_figure_reference")
        self.assertEqual(
            mappings["orientation"],
            "parent_module_structure",
        )
        self.assertEqual(mappings["qkcu"], "parent_module_structure")

    def test_method_graph_binds_section_figures_and_drops_system_root(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "rccformer-graph",
            "metadata": {
                "title": (
                    "RCCFormer: A Robust Crowd Counting Network Based on "
                    "Transformer"
                )
            },
            "blocks": [
                {
                    "id": "h3",
                    "type": "heading",
                    "text": "3. Methodology",
                    "page": 4,
                    "section_id": "3-methodology",
                    "section_title": "3. Methodology",
                },
                {
                    "id": "b-strong",
                    "type": "paragraph",
                    "text": (
                        "We propose a strong baseline with a Multi-level "
                        "Feature Fusion Module, as shown in Fig. 2(c)."
                    ),
                    "page": 4,
                    "section_id": "3-1-strong-baseline",
                    "section_title": "3.1. Strong Baseline",
                },
                {
                    "id": "b-root",
                    "type": "paragraph",
                    "text": (
                        "The proposed RCCFormer consists of DEAB and ASAM."
                    ),
                    "page": 5,
                    "section_id": "3-2-rccformer",
                    "section_title": "3.2. RCCFormer",
                },
                {
                    "id": "b-deab",
                    "type": "paragraph",
                    "text": (
                        "We propose a Detail-Embedded Attention Block, "
                        "illustrated in Fig. 4."
                    ),
                    "page": 5,
                    "section_id": "3-2-1-deab",
                    "section_title": "3.2.1. Detail-Embedded Attention Block",
                },
                {
                    "id": "b-asam",
                    "type": "paragraph",
                    "text": (
                        "We propose Input-dependent Deformable Convolution "
                        "inside the Adaptive Scale-Aware Module in Fig. 5."
                    ),
                    "page": 6,
                    "section_id": "3-2-2-asam",
                    "section_title": "3.2.2. Adaptive Scale-Aware Module",
                },
                {
                    "id": "b-loss",
                    "type": "paragraph",
                    "text": "We use a distribution matching loss function.",
                    "page": 7,
                    "section_id": "3-3-loss",
                    "section_title": "3.3. Loss Function",
                },
                {
                    "id": "h4",
                    "type": "heading",
                    "text": "4. Experiments",
                    "page": 7,
                    "section_id": "4-experiments",
                    "section_title": "4. Experiments",
                },
            ],
            "figures": [
                {
                    "id": "figure-2",
                    "caption": "Figure 2: Fusion methods; (c) ours.",
                    "page": 4,
                    "section_id": "3-1-strong-baseline",
                    "cited_by": ["b-strong"],
                },
                {
                    "id": "figure-4",
                    "caption": "Figure 4: Proposed DEAB.",
                    "page": 5,
                    "section_id": "3-2-1-deab",
                    "cited_by": ["b-deab"],
                },
                {
                    "id": "figure-5",
                    "caption": "Figure 5: Proposed IDConv.",
                    "page": 6,
                    "section_id": "3-2-2-asam",
                    "cited_by": ["b-asam"],
                },
            ],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="rccformer-method-graph-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, _ = build_method_graph(paper_path, root / "out")
            graph = read_json(graph_path)

        nodes = {node["name"]: node for node in graph["nodes"]}
        self.assertNotIn("RCCFormer", nodes)
        self.assertEqual(nodes["Strong Baseline"]["figure_refs"], ["figure-2"])
        self.assertEqual(
            nodes["Detail-Embedded Attention Block"]["figure_refs"],
            ["figure-4"],
        )
        self.assertEqual(
            nodes["Adaptive Scale-Aware Module"]["figure_refs"],
            ["figure-5"],
        )

    def test_dataset_examples_override_noisy_method_reference(self) -> None:
        paper_ir = {
            "metadata": {"title": "Retinal Segmentation Network"},
            "blocks": [],
        }
        classification = classify_figure_role(
            {
                "id": "figure-5",
                "caption": (
                    "Fig. 5. Partial original images, labels and FOVs "
                    "in the four datasets."
                ),
                "section_id": "d-loss-function",
            },
            paper_ir,
            referenced_node_ids={"method-node-loss"},
        )
        self.assertEqual(classification["role"], "dataset_example")

    def test_proposed_module_architecture_is_not_system_overview(self) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-2",
                "caption": (
                    "Fig. 2. Architecture of the proposed Adaptive "
                    "Rotated Attention (ARA) module."
                ),
                "section_id": "2-3-adaptive-rotation-attention",
            },
            {
                "metadata": {
                    "title": (
                        "MVP-Net: Multi-Oriented Vessel Detail "
                        "Preservation Network"
                    )
                },
                "figures": [],
            },
        )
        self.assertEqual(classification["role"], "method_module")

    def test_proposed_system_alias_overrides_listed_inner_modules(self) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-1",
                "caption": (
                    "Fig. 1. Architecture of the proposed MIFONet, which "
                    "consists of an encoder, decoder, CFFP, HFIM, and MSCA."
                ),
                "section_id": "3-method",
            },
            {
                "metadata": {
                    "title": (
                        "Application of Multilayer Information Fusion and "
                        "Optimization Network in Polyp Segmentation"
                    )
                },
                "figures": [],
            },
        )
        self.assertEqual(classification["role"], "method_overview")

    def test_measured_comparison_remains_result_despite_method_reference(self) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-1",
                "caption": (
                    "Fig. 1. Comparison of retinal vessel segmentation "
                    "networks. Ours has the highest F1 score and lowest "
                    "model complexity."
                ),
                "section_id": "2-method",
            },
            {
                "metadata": {"title": "Retinal Vessel Segmentation Network"},
                "figures": [],
            },
            referenced_node_ids={"method-node-loss"},
        )
        self.assertEqual(classification["role"], "experimental_result")

    def test_visual_bbox_metrics_override_incorrect_method_caption(self) -> None:
        visual_signals = _analyze_visual_text(
            "Dense MoE-8-1 MoE-16-1 Ours Top-1 Accuracy (%) "
            "77.9% 71.5% 75.3% 81.1%"
        )
        classification = classify_figure_role(
            {
                "id": "figure-2",
                "caption": "(a) Vanilla Top-k MoE.",
                "section_id": "3-method",
                "visual_content_signals": visual_signals,
            },
            {
                "metadata": {"title": "Efficient Transformer Training"},
                "figures": [],
            },
            referenced_node_ids={"method-node-moe"},
        )
        self.assertEqual(
            visual_signals["content_role"],
            "experimental_result",
        )
        self.assertEqual(classification["role"], "experimental_result")
        self.assertFalse(classification["caption_content_consistent"])
        self.assertIn(
            "accuracy",
            classification["visual_content_signals"]["metric_terms"],
        )

    def test_visual_bbox_architecture_remains_method_eligible(self) -> None:
        visual_signals = _analyze_visual_text(
            "Input Tokens Router Expert 1 Expert 2 Fusion FFN Output"
        )
        classification = classify_figure_role(
            {
                "id": "figure-3",
                "caption": "Architecture of the proposed fusion module.",
                "section_id": "3-method",
                "visual_content_signals": visual_signals,
            },
            {
                "metadata": {"title": "Efficient Transformer Training"},
                "figures": [],
            },
        )
        self.assertEqual(visual_signals["content_role"], "method_diagram")
        self.assertEqual(classification["role"], "method_module")
        self.assertTrue(classification["caption_content_consistent"])

    def test_method_map_audits_caption_content_role_conflict(self) -> None:
        visual_signals = _analyze_visual_text(
            "Baseline Ours Top-1 Accuracy (%) 70.0% 75.0% 81.0%"
        )
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "caption-mismatch",
            "metadata": {"title": "Efficient Transformer Training"},
            "blocks": [],
            "figures": [
                {
                    "id": "figure-2",
                    "caption": "Diagram of MoE.",
                    "page": 1,
                    "bbox": [100, 100, 500, 400],
                    "section_id": "3-method",
                    "path": None,
                    "visual_content_signals": visual_signals,
                }
            ],
            "tables": [],
            "equations": [],
        }
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "caption-mismatch",
            "nodes": [
                {
                    "id": "method-node-moe",
                    "order": 1,
                    "name": "Mixture of Experts",
                    "purpose": "Route inputs through multiple experts.",
                    "innovation": "Expert routing.",
                    "section_id": "3-method",
                    "section_title": "Method",
                    "figure_refs": ["figure-2"],
                    "sources": [{"block_id": "b-method"}],
                }
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory(prefix="method-content-conflict-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "graph.json"
            catalog_path = root / "catalog.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            catalog_path.write_text(
                json.dumps({"figures": paper_ir["figures"]}),
                encoding="utf-8",
            )
            figure_map_path, _ = map_method_figures(
                paper_path,
                graph_path,
                catalog_path,
                root / "out",
            )
            figure_map = read_json(figure_map_path)
        record = figure_map["records"][0]
        self.assertEqual(record["role"], "experimental_result")
        self.assertFalse(record["caption_content_consistent"])
        self.assertEqual(
            figure_map["resolved_role_conflicts"][0]["code"],
            "METHOD_REFERENCE_VISUAL_CONTENT_RESULT_CONFLICT",
        )
        self.assertEqual(figure_map["role_conflicts"], [])
        self.assertEqual(
            _method_content_mismatches(
                {"figure-2"},
                {
                    "records": [
                        {
                            **record,
                            "method_eligible": True,
                        }
                    ]
                },
            )[0]["asset_id"],
            "figure-2",
        )

    def test_test_result_plot_does_not_become_overview(self) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-36",
                "caption": (
                    "Fig. 36. Test result plots of each module and the "
                    "overall network model on the STARE dataset."
                ),
                "section_id": "results",
            },
            {
                "metadata": {"title": "Layered Transformer Network"},
                "figures": [],
            },
        )
        self.assertEqual(classification["role"], "experimental_result")

    def test_spaced_figure_prefix_preserves_method_roles(self) -> None:
        paper_ir = {
            "metadata": {
                "title": (
                    "MSLAU-Net: A Hybrid CNN-Transformer Network "
                    "for Medical Image Segmentation"
                )
            },
            "figures": [],
        }
        module = classify_figure_role(
            {
                "id": "figure-1",
                "caption": (
                    "F I G U R E 1 Details of Multi-Scale Linear "
                    "Attention. The input feature map is processed "
                    "with multiple convolution kernels."
                ),
                "section_id": "3-2-msla",
            },
            paper_ir,
        )
        overview = classify_figure_role(
            {
                "id": "figure-4",
                "caption": (
                    "F I G U R E 4 The proposed MSLAU-Net adopts an "
                    "encoder-decoder structure and produces a final "
                    "mask prediction."
                ),
                "context_after": "4.3 Comparison on the benchmark dataset",
                "section_id": "4-2-implementation-details",
            },
            paper_ir,
        )
        self.assertEqual(module["role"], "method_module")
        self.assertEqual(overview["role"], "method_overview")

    def test_attention_heatmap_and_effectiveness_fragments_are_results(
        self,
    ) -> None:
        paper_ir = {
            "metadata": {"title": "Medical Segmentation Network"},
            "figures": [],
        }
        heatmap = classify_figure_role(
            {
                "id": "figure-7",
                "caption": (
                    "F I G U R E 7 The bottom row displays the "
                    "corresponding attention heatmaps."
                ),
                "section_id": "4-7-visualization",
            },
            paper_ir,
        )
        fragment = classify_figure_role(
            {
                "id": "figure-6-panel-a",
                "caption": "",
                "section_id": "4-6-3-effectiveness-of-encoder-design",
            },
            paper_ir,
        )
        self.assertEqual(heatmap["role"], "experimental_result")
        self.assertEqual(fragment["role"], "experimental_result")

    def test_attention_map_inside_sourced_method_flow_is_mechanism_analysis(
        self,
    ) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-method-attention",
                "caption": (
                    "Feature anisotropic attention mechanism. Maximum and "
                    "minimum input features are subtracted, concatenated, "
                    "passed through sigmoid to obtain an attention map, and "
                    "multiplied with the input feature."
                ),
                "section_id": "3-4-feature-attention",
                "visual_content_signals": {
                    "extraction_method": "unavailable",
                    "text_sample": "",
                    "content_role": "unknown",
                    "confidence": 0.5,
                    "result_score": 0,
                    "method_score": 0,
                },
            },
            {
                "metadata": {"title": "General Feature Network"},
                "figures": [],
            },
            referenced_node_ids={"method-node-attention"},
        )
        self.assertEqual(classification["role"], "mechanism_analysis")
        self.assertEqual(
            classification["preferred_zone"],
            "method_details",
        )
        self.assertIn(
            "experimental_results_secondary",
            classification["poster_eligibility"],
        )
        self.assertTrue(
            classification["evidence_ledger"][
                "mechanism_analysis_signal"
            ]
        )

    def test_internal_branch_feature_visualization_is_not_forced_to_result(
        self,
    ) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-branch-responses",
                "caption": (
                    "Visualization of degradation-prior attention maps and "
                    "three-branch features. The spatial, frequency, and "
                    "Fourier branches produce complementary feature maps."
                ),
                "section_id": "3-3-architecture",
            },
            {
                "metadata": {"title": "Multi-Branch Restoration Network"},
                "figures": [],
            },
            referenced_node_ids={"method-node-branches"},
        )
        self.assertEqual(classification["role"], "mechanism_analysis")
        self.assertTrue(
            classification["evidence_ledger"][
                "explicit_method_reference"
            ]
        )

    def test_error_map_comparison_remains_result_despite_method_reference(
        self,
    ) -> None:
        classification = classify_figure_role(
            {
                "id": "figure-error-comparison",
                "caption": (
                    "Error map between the restored image and ground truth. "
                    "Our result contains fewer errors than the baseline."
                ),
                "section_id": "3-method",
            },
            {
                "metadata": {"title": "Image Restoration Network"},
                "figures": [],
            },
            referenced_node_ids={"method-node-restoration"},
        )
        self.assertEqual(classification["role"], "qualitative_result")
        self.assertEqual(
            classification["preferred_zone"],
            "experimental_results",
        )

    def test_result_headline_prefers_favorable_claim_aligned_metric(self) -> None:
        metrics = [
            {
                "metric": "Params (M)",
                "value": "21.90",
                "baseline_value": "14.80",
                "baseline": "U-Net",
                "direction": "lower_is_better",
                "dataset": "Synapse",
            },
            {
                "metric": "DSC (%)",
                "value": "83.18",
                "baseline_value": "82.47",
                "baseline": "BRAU-Net++",
                "direction": "higher_is_better",
                "dataset": "Synapse",
            },
        ]
        claim = {
            "claim": "MSLAU-Net improves segmentation performance.",
            "verdict": "supported",
        }
        ordered = _order_metrics_for_claim(metrics, claim)
        headline = _result_headline(ordered, claim)
        self.assertEqual(ordered[0]["metric"], "DSC (%)")
        self.assertIn("outperforming BRAU-Net++", headline)
        self.assertNotIn("Params (M) 21.90", headline)

    def test_captionless_split_panel_inherits_dataset_role(self) -> None:
        fragment = {
            "id": "figure-1-2",
            "caption": "",
            "page": 6,
            "bbox": [81.0, 65.0, 290.0, 176.0],
            "source_item_index": 89,
            "section_id": "d-loss-function",
        }
        captioned_peer = {
            "id": "figure-5",
            "caption": (
                "Fig. 5. Partial original images, labels and FOVs "
                "in the four datasets."
            ),
            "page": 6,
            "bbox": [285.0, 65.0, 485.0, 176.0],
            "source_item_index": 90,
            "section_id": "d-loss-function",
        }
        classification = classify_figure_role(
            fragment,
            {
                "metadata": {"title": "Retinal Segmentation Network"},
                "figures": [fragment, captioned_peer],
            },
            referenced_node_ids={"method-node-global", "method-node-local"},
        )
        self.assertEqual(classification["role"], "dataset_example")
        self.assertIn("adjacent split figure", classification["reasons"][0])

    def test_method_graph_rejects_distant_captionless_figure_fragments(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "fragment-reference",
            "metadata": {
                "title": "Adaptive Fusion Network",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h3",
                    "type": "heading",
                    "text": "3. Method",
                    "page": 3,
                    "section_id": "3-method",
                    "section_title": "3. Method",
                },
                {
                    "id": "p31",
                    "type": "paragraph",
                    "text": (
                        "We propose an Adaptive Fusion Module whose structure "
                        "is shown in Fig. 2."
                    ),
                    "page": 3,
                    "section_id": "3-1-adaptive-fusion-module",
                    "section_title": "3.1 Adaptive Fusion Module",
                },
            ],
            "figures": [
                {
                    "id": "figure-2",
                    "caption": "Fig. 2. Structure of the proposed fusion module.",
                    "page": 3,
                    "section_id": "3-1-adaptive-fusion-module",
                    "cited_by": ["p31"],
                },
                {
                    "id": "figure-2-2",
                    "caption": "(a) (b) (c)",
                    "page": 5,
                    "section_id": "4-ablation-studies",
                    "cited_by": ["p31"],
                },
            ],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="method-fragment-filter-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, _ = build_method_graph(source, root / "out")
            graph = read_json(graph_path)
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["figure_refs"], ["figure-2"])

    def test_method_subsections_beat_overview_sentence_enumeration(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "section-first-method",
            "metadata": {
                "title": "Hybrid Segmentation Network",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h3",
                    "type": "heading",
                    "text": "3 METHOD",
                    "page": 3,
                    "section_id": "3-method",
                    "section_title": "3 METHOD",
                },
                {
                    "id": "p31",
                    "type": "paragraph",
                    "text": (
                        "We propose multi-scale linear attention to model "
                        "local and long-range dependencies."
                    ),
                    "page": 3,
                    "section_id": "3-1-multi-scale-linear-attention",
                    "section_title": "3.1 Multi-Scale Linear Attention",
                },
                {
                    "id": "p32",
                    "type": "paragraph",
                    "text": (
                        "We design an encoder with local and global feature "
                        "extraction blocks."
                    ),
                    "page": 4,
                    "section_id": "3-2-encoder",
                    "section_title": "3.2 Encoder",
                },
                {
                    "id": "p33",
                    "type": "paragraph",
                    "text": (
                        "The proposed network architecture consists of an "
                        "encoder and decoder described above."
                    ),
                    "page": 5,
                    "section_id": "3-3-architecture-overview",
                    "section_title": "3.3 Architecture Overview",
                },
                {
                    "id": "h4",
                    "type": "heading",
                    "text": "4 EXPERIMENTS",
                    "page": 6,
                    "section_id": "4-experiments",
                    "section_title": "4 EXPERIMENTS",
                },
            ],
            "figures": [],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="section-first-method-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, _ = build_method_graph(source, root / "out")
            graph = read_json(graph_path)
        names = [node["name"] for node in graph["nodes"]]
        self.assertEqual(names, ["Multi-Scale Linear Attention", "Encoder"])
        self.assertNotIn("decoder described above", names)

    def test_related_work_based_methods_do_not_enter_method_graph(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "dsformer-sections",
            "metadata": {
                "title": "Dual Selective Fusion Transformer Network",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h2",
                    "type": "heading",
                    "text": "2. Related Work",
                    "page": 2,
                    "section_id": "2-related-work",
                    "section_title": "2. Related Work",
                },
                {
                    "id": "h21",
                    "type": "heading",
                    "text": "2.1. CNN-based Methods",
                    "page": 2,
                    "section_id": "2-1-cnn-based-methods",
                    "section_title": "2.1. CNN-based Methods",
                },
                {
                    "id": "p21",
                    "type": "paragraph",
                    "text": "Prior CNN methods extract local spatial features.",
                    "page": 2,
                    "section_id": "2-1-cnn-based-methods",
                    "section_title": "2.1. CNN-based Methods",
                },
                {
                    "id": "h22",
                    "type": "heading",
                    "text": "2.2. Transformer-based Methods",
                    "page": 3,
                    "section_id": "2-2-transformer-based-methods",
                    "section_title": "2.2. Transformer-based Methods",
                },
                {
                    "id": "p22",
                    "type": "paragraph",
                    "text": "Prior transformer methods model long-range context.",
                    "page": 3,
                    "section_id": "2-2-transformer-based-methods",
                    "section_title": "2.2. Transformer-based Methods",
                },
                {
                    "id": "h3",
                    "type": "heading",
                    "text": "3. Methodology",
                    "page": 3,
                    "section_id": "3-methodology",
                    "section_title": "3. Methodology",
                },
                {
                    "id": "p3",
                    "type": "paragraph",
                    "text": "Our method contains two complementary modules.",
                    "page": 3,
                    "section_id": "3-methodology",
                    "section_title": "3. Methodology",
                },
                {
                    "id": "p32",
                    "type": "paragraph",
                    "text": "We propose KSFTB to adaptively select receptive fields.",
                    "page": 4,
                    "section_id": "3-2-ksftb",
                    "section_title": "3.2. Kernel Selective Fusion Transformer Block",
                },
                {
                    "id": "p33",
                    "type": "paragraph",
                    "text": "We propose TSFTB to select informative tokens.",
                    "page": 5,
                    "section_id": "3-3-tsftb",
                    "section_title": "3.3. Token Selective Fusion Transformer Block",
                },
                {
                    "id": "h4",
                    "type": "heading",
                    "text": "4. Experiments",
                    "page": 6,
                    "section_id": "4-experiments",
                    "section_title": "4. Experiments",
                },
            ],
            "figures": [],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="method-region-boundary-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path, _ = build_method_graph(source, root / "out")
            graph = read_json(graph_path)
        names = [node["name"] for node in graph["nodes"]]
        self.assertEqual(
            names,
            [
                "Kernel Selective Fusion Transformer Block",
                "Token Selective Fusion Transformer Block",
            ],
        )
        self.assertFalse(any("based Methods" in name for name in names))

    def test_named_method_story_beats_related_work_attention(self) -> None:
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "story-exfusion",
            "metadata": {
                "title": "ExFusion: Efficient Transformer Training via Multi-Experts Fusion",
                "authors": [],
                "affiliations": [],
            },
            "blocks": [
                {
                    "id": "h1",
                    "type": "heading",
                    "text": "II. RELATED WORK",
                    "page": 2,
                    "section_id": "ii-related-work",
                    "section_title": "II. RELATED WORK",
                },
                {
                    "id": "p1",
                    "type": "paragraph",
                    "text": "CSWin computes attention in parallel to improve efficiency.",
                    "page": 2,
                    "section_id": "a-transformer-models",
                    "section_title": "A. Transformer Models",
                },
                {
                    "id": "h2",
                    "type": "heading",
                    "text": "IV. MULTI-EXPERTS FUSION (EXFUSION)",
                    "page": 4,
                    "section_id": "iv-exfusion",
                    "section_title": "IV. MULTI-EXPERTS FUSION (EXFUSION)",
                },
                {
                    "id": "p2",
                    "type": "paragraph",
                    "text": (
                        "Inspired by ensemble averaging, we posit that expert outputs "
                        "can be merged through weighted fusion. The fused expert is "
                        "equivalent to applying the weighted experts and reduces variance."
                    ),
                    "page": 4,
                    "section_id": "a-motivation",
                    "section_title": "A. Motivation",
                },
            ],
            "figures": [],
            "equations": [],
            "tables": [],
        }
        with tempfile.TemporaryDirectory(prefix="named-story-") as temp:
            root = Path(temp)
            source = root / "paper.json"
            source.write_text(json.dumps(paper_ir), encoding="utf-8")
            story_path, _ = extract_story(source, root / "out")
            story = read_json(story_path)
        self.assertIn("weighted fusion", story["core_hypothesis"]["summary"].lower())
        self.assertIn("fused expert", story["theory_or_mechanism"]["summary"].lower())
        self.assertNotIn("cswin", story["theory_or_mechanism"]["summary"].lower())

    def test_weighted_fusion_equation_is_key_equation_candidate(self) -> None:
        score, reasons = _equation_score(
            {
                "latex": r"Y=\sum_i w_iE_i(x)=\bar E(x)",
                "path": "assets/equation-7.png",
                "context_before": (
                    "The weighted averaging process creates a singular fused expert "
                    "through a weighted fusion mechanism."
                ),
                "context_after": "",
                "section_id": "a-motivation",
            }
        )
        self.assertGreaterEqual(score, 2.5)
        self.assertIn("context contains 'weighted fusion'", reasons)

    def test_generic_cross_entropy_is_not_a_key_idea_equation(self) -> None:
        paper_ir = {"blocks": []}
        audit = score_equation(
            {
                "id": "equation-ce",
                "latex": r"L=-\sum_i y_i\log p_i",
                "path": "assets/equation-ce.png",
                "context_before": (
                    "We use the standard binary cross entropy loss for training."
                ),
                "context_after": "",
                "section_id": "implementation",
            },
            paper_ir,
            "The model introduces a dual-fusion mechanism.",
        )
        self.assertTrue(audit["generic_rejected"])
        self.assertNotIn(
            audit["tier"],
            {"key_idea_primary", "key_idea_supporting"},
        )

    def test_explicit_main_idea_beats_generic_framework_claim(self) -> None:
        core = _core_claim(
            {
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "claim": "We propose MedCore, a structured framework.",
                        "sources": [{"block_id": "p1-b6"}],
                        "verdict": "partially_supported",
                        "confidence": 0.56,
                    }
                ]
            },
            {
                "prior_work_gap": {"summary": "Compression can erase boundaries."},
                "motivation": {
                    "summary": (
                        "The main idea is to preserve two kinds of structures: "
                        "medically adapted structures and high boundary-leverage structures."
                    ),
                    "status": "explicit",
                    "sources": [{"block_id": "p1-b6"}],
                    "confidence": 0.68,
                },
            },
        )
        self.assertIn("main idea", core["claim"].lower())

    def test_core_definition_can_be_a_supporting_equation(self) -> None:
        paper_ir = {
            "metadata": {
                "title": "Boundary-Preserving Medical Core Pruning"
            },
            "blocks": [
                {
                    "type": "abstract",
                    "text": (
                        "The main idea preserves structures with high boundary leverage."
                    ),
                },
                {
                    "type": "paragraph",
                    "section_id": "5-analysis",
                    "section_title": "5 Analysis",
                    "text": (
                        "Boundary leverage reveals why head pruning causes more "
                        "boundary damage."
                    ),
                },
                {
                    "type": "paragraph",
                    "section_id": "3-method",
                    "section_title": "3 Method",
                    "text": "We use Eq. (3) to allocate compression.",
                },
            ],
        }
        audit = score_equation(
            {
                "id": "equation-3",
                "latex": (
                    r"\lambda_G^{bd}=\frac{1}{\Delta C_G}"
                    r"\mathbb{E}_{x\in B}\frac{|\delta_G(x)|}"
                    r"{\|\nabla s_\theta(x)\|_2+\epsilon}\tag{3}"
                ),
                "section_id": "3-2-boundary-leverage-principle",
                "context_before": (
                    "Definition 3.2 (Boundary leverage). We define boundary "
                    "leverage for a compression operation."
                ),
                "context_after": (
                    "This quantity estimates boundary displacement per unit compression."
                ),
                "path": "assets/equation-3.png",
            },
            paper_ir,
            (
                "The main idea preserves medically adapted structures and "
                "high boundary-leverage structures."
            ),
        )
        self.assertIn(audit["tier"], {"key_idea_supporting", "key_idea_primary"})
        self.assertGreaterEqual(audit["score"], 7)

    def test_key_idea_headline_removes_paper_boilerplate_and_double_period(self) -> None:
        headline = _headline(
            "In this article, we proposed a novel GT-DLA network for retinal vessel segmentation.",
            "mechanism_centered",
        )
        self.assertNotIn("through In this", headline)
        self.assertNotIn("..", headline)
        self.assertNotRegex(headline, r"(?i)^in this (paper|article)")

    def test_structured_modules_replace_generic_method_headline(self) -> None:
        headline = _structured_mechanism_headline(
            "In this article, we proposed a novel GT-DLA-dsHFF model.",
            "mechanism_centered",
            {
                "nodes": [
                    {"name": "A. Global Transformer"},
                    {"name": "B. Dual Local Attention"},
                    {"name": "C. Deep-Shallow Hierarchical Feature Fusion"},
                    {"name": "D. Loss Function"},
                ]
            },
            {
                "metadata": {
                    "title": (
                        "Global Transformer and Dual Local Attention Network "
                        "for Retinal Vessel Segmentation"
                    )
                }
            },
        )
        self.assertIsNotNone(headline)
        self.assertIn("global modeling", headline)
        self.assertIn("local detail recovery", headline)
        self.assertIn("deep-shallow feature fusion", headline)
        self.assertNotIn("proposed a novel", headline)

    def test_key_idea_takeaway_rejects_unrelated_conclusion_sentence(self) -> None:
        takeaway = _takeaway(
            {
                "conclusion": {
                    "summary": (
                        "The model remains stable across variations in dropout rate, "
                        "batch size, and learning rate."
                    )
                }
            },
            "CGA-Fusion and AE-Fusion create a dual-fusion mechanism for vessel segmentation.",
            "mechanism_centered",
        )
        self.assertNotIn("dropout", takeaway.lower())
        self.assertIn("mechanism", takeaway.lower())

    def test_equation_crop_precedes_low_confidence_latex(self) -> None:
        with tempfile.TemporaryDirectory(prefix="key-equation-crop-") as temp:
            root = Path(temp)
            crop = root / "equation-7.png"
            crop.write_bytes(b"\x89PNG\r\n\x1a\nsource-equation-crop")
            paper_ir = {
                "schema_version": "1.0.0",
                "paper_id": "fusion-paper",
                "metadata": {"title": "Weighted Fusion", "authors": [], "affiliations": []},
                "blocks": [
                    {
                        "id": "b1",
                        "type": "paragraph",
                        "text": "Equation (7) is validated in the ablation analysis.",
                        "page": 4,
                        "section_id": "ablation",
                    }
                ],
                "figures": [],
                "equations": [
                    {
                        "id": "equation-7",
                        "asset_type": "equation",
                        "caption": "Proposed weighted fusion objective",
                        "page": 3,
                        "section_id": "method",
                        "path": str(crop),
                        "latex": r"F_{out}=wF_a+(1-w)F_b\tag{7}",
                        "latex_confidence": 0.2,
                        "bbox": [100, 200, 520, 280],
                        "context_before": (
                            "We propose a novel final weighted fusion mechanism, "
                            "defined as the central objective and validated by ablation."
                        ),
                        "context_after": "",
                        "cited_by": ["b1", "b2"],
                        "crop_pending": False,
                    }
                ],
                "tables": [],
            }
            story = {
                "paper_id": "fusion-paper",
                "prior_work_gap": {"summary": "Existing fusion is static.", "sources": []},
                "core_hypothesis": {"summary": "", "status": "not_found", "sources": []},
                "theory_or_mechanism": {"summary": "Weighted fusion adapts two feature paths.", "status": "explicit", "sources": [{"block_id": "b1"}]},
                "method_design": {"summary": "", "status": "not_found", "sources": []},
                "experimental_results": {"summary": "Ablation validates weighted fusion.", "sources": [{"block_id": "b1"}]},
                "conclusion": {"summary": "Adaptive weighting improves fusion.", "sources": [{"block_id": "b1"}]},
            }
            evidence = {
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "claim": "We propose a novel weighted fusion mechanism.",
                        "sources": [{"block_id": "b1"}],
                        "verdict": "supported",
                        "confidence": 0.9,
                    }
                ]
            }
            graph = {
                "nodes": [
                    {
                        "id": "m1",
                        "order": 1,
                        "name": "Weighted fusion",
                        "purpose": "Adaptively combine two feature paths.",
                        "sources": [{"block_id": "b1"}],
                    }
                ]
            }
            method_map = {"overview_asset_id": "figure-overview"}
            paths = {}
            for name, value in (
                ("paper.json", paper_ir),
                ("story.json", story),
                ("evidence.json", evidence),
                ("graph.json", graph),
                ("map.json", method_map),
            ):
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                paths[name] = path
            spec_path, _ = build_key_idea(
                paths["paper.json"],
                paths["story.json"],
                paths["evidence.json"],
                paths["graph.json"],
                paths["map.json"],
                root / "out",
            )
            spec = read_json(spec_path)
        equation = spec["equation"]
        self.assertEqual(equation["display_mode"], "original_crop")
        self.assertEqual(equation["bbox"], [100, 200, 520, 280])
        self.assertTrue(equation["crop_integrity"])
        self.assertIn(r"F_{out}", equation["latex"])
        self.assertIn(r"\tag{7}", equation["latex"])
        self.assertTrue(equation["image_sha256"])

    def test_no_equation_key_idea_expands_visual_without_overview(self) -> None:
        spec = {
            "type": "mechanism_centered",
            "headline": "Complementary evidence routing mechanisms expose unsupported claims before they enter the final paper summary.",
            "visual": {
                "visual_type": "three_step_flow",
                "items": [
                    {"label": "Extract", "text": "Recover source evidence."},
                    {"label": "Route", "text": "Bind claims to blocks."},
                    {"label": "Check", "text": "Reject unsupported claims."},
                ],
                "overview_asset_id": None,
            },
            "equation": {"equation_id": None, "display_mode": "none"},
            "takeaway": "The mechanism improves traceability.",
            "inferred": False,
        }
        html = _key_idea_content(spec, {}, Path("."), Path("."))
        self.assertIn("no-equation", html)
        self.assertEqual(
            html.count('<article class="key-idea-item">'),
            3,
        )
        self.assertNotIn("key-idea-equation", html)
        self.assertNotIn("data-asset-id", html)

    def test_single_mechanism_without_equation_uses_full_focus_layout(
        self,
    ) -> None:
        visual_type, items = _visual_items(
            "mechanism_centered",
            {
                "method_design": {
                    "summary": "Directional kernels preserve target details.",
                    "sources": [{"block_id": "b1"}],
                },
                "theory_or_mechanism": {
                    "summary": "Directional kernels preserve target details.",
                    "sources": [{"block_id": "b1"}],
                },
            },
            {
                "nodes": [
                    {
                        "id": "m1",
                        "name": "Directional convolution",
                        "purpose": "Directional kernels preserve target details.",
                        "sources": [{"block_id": "b1"}],
                    }
                ]
            },
            "Directional kernels preserve target details.",
            [{"block_id": "b1"}],
        )
        self.assertEqual(visual_type, "single_mechanism_focus")
        self.assertEqual(len(items), 1)
        self.assertTrue(visual_layout_compatible(visual_type, len(items)))
        spec = {
            "type": "mechanism_centered",
            "headline": (
                "Directional convolution preserves weak target evidence "
                "without forcing an unsupported multi-step explanation."
            ),
            "visual": {
                "visual_type": visual_type,
                "items": items,
                "overview_asset_id": None,
            },
            "equation": {"equation_id": None, "display_mode": "none"},
            "takeaway": "The single mechanism remains the central idea.",
            "inferred": False,
        }
        html = _key_idea_content(spec, {}, Path("."), Path("."))
        self.assertIn("items-1", html)
        self.assertIn(
            'data-key-idea-visual="single_mechanism_focus"',
            html,
        )
        self.assertEqual(
            html.count('<article class="key-idea-item">'),
            1,
        )

    def test_two_independent_mechanisms_use_two_part_layout(self) -> None:
        visual_type, items = _visual_items(
            "mechanism_centered",
            {},
            {
                "nodes": [
                    {
                        "id": "m1",
                        "name": "Directional convolution",
                        "purpose": "Preserve anisotropic target details.",
                        "sources": [{"block_id": "b1"}],
                    },
                    {
                        "id": "m2",
                        "name": "Scale-aware objective",
                        "purpose": "Adapt optimization to target size.",
                        "sources": [{"block_id": "b2"}],
                    },
                ]
            },
            "Two mechanisms address representation and optimization.",
            [{"block_id": "b1"}, {"block_id": "b2"}],
        )
        self.assertEqual(visual_type, "two_part_mechanism")
        self.assertEqual(len(items), 2)
        self.assertTrue(visual_layout_compatible(visual_type, len(items)))

    def test_key_idea_prefers_core_source_mechanism_over_training_detail(
        self,
    ) -> None:
        text = _node_visual_text(
            {
                "name": "Directional convolution",
                "purpose": (
                    "Batch normalization improves training stability and "
                    "training speed."
                ),
                "innovation": (
                    "Batch normalization improves training stability."
                ),
                "sources": [
                    {
                        "block_id": "b1",
                        "quote": (
                            "The architecture is shown in Figure 3. Unlike "
                            "standard convolution, the module uses "
                            "asymmetric padding to create horizontal and "
                            "vertical kernels and expand the receptive field."
                        ),
                    }
                ],
            }
        )
        self.assertIn("asymmetric padding", text.lower())
        self.assertNotIn("batch normalization", text.lower())
        self.assertNotIn("figure 3", text.lower())

    def test_architecture_without_graph_uses_architecture_visual_not_equation(self) -> None:
        visual_type, items = _visual_items(
            "architecture_centered",
            {
                "method_design": {
                    "summary": "The framework prunes a medically adapted encoder.",
                    "sources": [{"block_id": "p3-b21"}],
                },
                "theory_or_mechanism": {
                    "summary": "Boundary leverage protects contour-critical structures.",
                    "sources": [{"block_id": "p4-b29"}],
                },
            },
            {"nodes": []},
            "A compact medical core preserves adaptation and boundary structure.",
            [{"block_id": "p1-b6"}],
        )
        self.assertEqual(visual_type, "two_module_relationship")
        self.assertEqual(len(items), 2)

    def test_different_papers_choose_different_key_idea_types(self) -> None:
        empty_equation = {"score": None}
        graph = {"nodes": []}
        base_story = {
            "prior_work_gap": {"summary": ""},
            "theory_or_mechanism": {"summary": ""},
            "core_hypothesis": {"status": "explicit"},
        }
        finding_type, _ = classify_key_idea_type(
            {"metadata": {"title": "A Clinical Finding Study"}, "blocks": []},
            base_story,
            {
                "claims": [
                    {
                        "claim": "We find a significant effect and demonstrate the highest response.",
                        "verdict": "supported",
                    }
                ]
            },
            graph,
            empty_equation,
        )
        architecture_type, _ = classify_key_idea_type(
            {"metadata": {"title": "A Modular Encoder Decoder Network Architecture"}, "blocks": []},
            base_story,
            {"claims": []},
            {
                "nodes": [
                    {"name": "Encoder"},
                    {"name": "Fusion branch"},
                    {"name": "Decoder"},
                ]
            },
            empty_equation,
        )
        formula_type, _ = classify_key_idea_type(
            {"metadata": {"title": "A Theoretical Relation"}, "blocks": []},
            base_story,
            {"claims": []},
            graph,
            {"score": 12},
        )
        contrast_type, _ = classify_key_idea_type(
            {
                "metadata": {
                    "title": (
                        "Unlike Existing and Previous Methods: Learning Without "
                        "Their Limitation"
                    )
                },
                "blocks": [],
            },
            base_story,
            {"claims": []},
            graph,
            empty_equation,
        )
        mechanism_type, _ = classify_key_idea_type(
            {
                "metadata": {
                    "title": "Attention Routing and Fusion Selection Mechanism"
                },
                "blocks": [],
            },
            base_story,
            {"claims": []},
            {"nodes": [{"name": "Route"}, {"name": "Fuse"}]},
            empty_equation,
        )
        self.assertEqual(finding_type, "finding_centered")
        self.assertEqual(architecture_type, "architecture_centered")
        self.assertEqual(formula_type, "formula_centered")
        self.assertEqual(contrast_type, "contrast_centered")
        self.assertEqual(mechanism_type, "mechanism_centered")
        self.assertEqual(
            {
                finding_type,
                architecture_type,
                formula_type,
                contrast_type,
                mechanism_type,
            },
            {
                "finding_centered",
                "architecture_centered",
                "formula_centered",
                "contrast_centered",
                "mechanism_centered",
            },
        )

class KeyIdeaVisibleTextTests(unittest.TestCase):
    def test_visual_math_delimiter_is_rejected(self) -> None:
        audit = audit_key_idea_visible_text(
            {
                "headline": (
                    "Multi-scale extraction and linear attention coordinate "
                    "local detail with global context for segmentation."
                ),
                "visual": {
                    "items": [
                        {
                            "label": "Linear Attention",
                            "text": "$w_i$ are learnable weights.",
                        }
                    ]
                },
                "equation": {"equation_id": None},
                "takeaway": (
                    "The mechanism efficiently combines complementary "
                    "representations."
                ),
                "inference_label": "Explicit",
            }
        )
        codes = {item["code"] for item in audit["findings"]}
        self.assertIn("math_delimiter_check", codes)
        self.assertIn("raw_subscript_superscript_check", codes)

    def test_explanation_latex_command_is_rejected(self) -> None:
        audit = audit_key_idea_visible_text(
            {
                "headline": (
                    "Prototype matching retrieves category-aware features "
                    "from a dynamically updated memory bank."
                ),
                "visual": {
                    "items": [
                        {
                            "label": "Prototype Matching",
                            "text": (
                                "Similarity matching retrieves category-aware "
                                "representations from prototype memories."
                            ),
                        }
                    ]
                },
                "equation": {
                    "equation_id": "equation-1",
                    "plain_language_explanation": (
                        "The value uses \\mathcal{L}_{dice} during training."
                    ),
                },
                "takeaway": (
                    "The memory prior supplies direct category evidence."
                ),
                "inference_label": "Explicit",
            }
        )
        self.assertTrue(
            any(
                item["code"] == "latex_residue_check"
                for item in audit["findings"]
            )
        )

    def test_latex_removal_cannot_leave_dangling_clause(self) -> None:
        self.assertEqual(
            _complete_visible_sentence(
                "where $w_i$ are learnable weight parameters and",
            ),
            "",
        )

    def test_cross_reference_is_rejected(self) -> None:
        audit = audit_key_idea_visible_text(
            {
                "headline": (
                    "The central mechanism integrates multi-scale local "
                    "features with efficient global context."
                ),
                "visual": {
                    "items": [
                        {
                            "label": "Feature Extraction",
                            "text": "The module extracts features as shown in Fig. 4.",
                        }
                    ]
                },
                "equation": {"equation_id": None},
                "takeaway": (
                    "The combined mechanism addresses the paper's stated gap."
                ),
                "inference_label": "Explicit",
            }
        )
        self.assertTrue(
            any(
                item["code"] == "cross_reference_check"
                for item in audit["findings"]
            )
        )

    def test_dice_ce_combination_is_generic(self) -> None:
        audit = score_equation(
            {
                "id": "equation-17",
                "latex": (
                    r"\mathcal {L}=\lambda\mathcal {L}_{d i c e}"
                    r"+(1-\lambda)\mathcal {L}_{c e}\tag{17}"
                ),
                "context_before": (
                    "The weighted loss combines Dice and cross-entropy loss."
                ),
                "context_after": "",
                "section_id": "training-objective",
                "path": "assets/equation-17.png",
            },
            {"blocks": []},
            "Multi-scale linear attention aggregates global context.",
        )
        self.assertTrue(audit["generic_rejected"])
        self.assertNotIn(
            audit["tier"],
            {"key_idea_primary", "key_idea_supporting"},
        )

    def test_high_scoring_generic_equation_still_fails_alignment(self) -> None:
        equation = _apply_equation_alignment_gate(
            {
                "equation_id": "equation-loss",
                "display_mode": "original_crop",
                "score": 10,
                "generic_rejected": True,
                "dimensions": {
                    "centrality": 2,
                    "downstream_usage": 2,
                    "validation": 2,
                },
                "selection_reason": [],
                "_source_context": "generic training loss",
            },
            "mechanism_centered",
            {"nodes": []},
            "The mechanism aggregates cross-scale global context.",
        )
        self.assertIsNone(equation["equation_id"])
        self.assertEqual(equation["display_mode"], "none")

    def test_mechanism_key_idea_rejects_unaligned_training_loss(self) -> None:
        equation = _apply_equation_alignment_gate(
            {
                "equation_id": "equation-loss",
                "display_mode": "original_crop",
                "score": 8,
                "generic_rejected": False,
                "dimensions": {
                    "centrality": 1,
                    "downstream_usage": 0,
                    "validation": 0,
                },
                "selection_reason": [],
                "_source_context": "training objective",
            },
            "mechanism_centered",
            {
                "nodes": [
                    {
                        "name": "Multi-Scale Linear Attention",
                        "purpose": "Aggregate cross-scale global context.",
                    }
                ]
            },
            "Multi-scale linear attention aggregates global context.",
        )
        self.assertEqual(equation["display_mode"], "none")

    def test_mslau_visual_omits_encoder_and_uses_three_complete_items(self) -> None:
        graph = {
            "nodes": [
                {
                    "name": "Multi-Scale Linear Attention",
                    "purpose": "Aggregate cross-scale global context.",
                    "sources": [{"block_id": "b1"}],
                },
                {
                    "name": "Multi-Scale Feature Extraction",
                    "purpose": "Extract hierarchical multi-scale features.",
                    "sources": [{"block_id": "b2"}],
                },
                {
                    "name": "Linear Attention Computation",
                    "purpose": "Model global context efficiently.",
                    "sources": [{"block_id": "b3"}],
                },
                {
                    "name": "Encoder",
                    "purpose": "The encoder has four stages.",
                    "sources": [{"block_id": "b4"}],
                },
            ]
        }
        visual_type, items = _visual_items(
            "mechanism_centered",
            {},
            graph,
            "Multi-scale extraction and linear attention aggregate global context.",
            [{"block_id": "b1"}],
        )
        self.assertEqual(visual_type, "three_step_flow")
        self.assertEqual(len(items), 3)
        self.assertNotIn("Encoder", {item["label"] for item in items})
        self.assertTrue(
            all(not visible_text_findings(item["text"]) for item in items)
        )

    def test_invalid_key_idea_generates_debug_preview_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="invalid-key-preview-") as temp:
            root = Path(temp)

            def write(name: str, value: dict) -> Path:
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                return path

            paper = write(
                "paper.json",
                {
                    "paper_id": "preview-paper",
                    "metadata": {
                        "title": "Preview Paper",
                        "authors": [],
                        "affiliations": [],
                    },
                    "blocks": [],
                    "figures": [],
                    "equations": [],
                    "tables": [],
                },
            )
            key_path = write(
                "key_idea_spec.json",
                {
                    "type": "mechanism_centered",
                    "headline": "Invalid $w_i$ headline remains visible.",
                    "visual": {"visual_type": "single_mechanism_focus", "items": []},
                    "equation": {"equation_id": None, "display_mode": "none"},
                    "takeaway": "Invalid preview.",
                },
            )
            write(
                "key_idea_report.json",
                {"status": "failed", "failed_checks": ["latex_residue_check"]},
            )
            story_fields = {
                key: {"summary": "", "status": "not_found", "sources": []}
                for key in (
                    "core_hypothesis",
                    "theory_or_mechanism",
                    "method_design",
                    "experimental_design",
                    "conclusion",
                    "limitations",
                )
            }
            spec_path, _ = compose_poster(
                paper,
                write("story.json", story_fields),
                write("evidence.json", {"claims": []}),
                write("selected.json", {}),
                write("graph.json", {"nodes": []}),
                write(
                    "method.json",
                    {
                        "mode": "text_only_method_path",
                        "overview_asset_id": None,
                        "callouts": [],
                        "storyboard_items": [],
                        "experiment_strip": [],
                    },
                ),
                key_path,
                write(
                    "results.json",
                    {
                        "layout_template": "quantitative_plus_qualitative",
                        "key_metrics": [],
                        "primary_asset": None,
                        "secondary_asset": None,
                    },
                ),
                write("highlights.json", {"highlights": []}),
                write("motivation.json", {"items": []}),
                write("contributions.json", {"items": []}),
                root / "poster",
            )
            html_path, bundle_path = render_poster(
                spec_path,
                paper,
                root / "poster",
                export_browser=True,
            )
            bundle = read_json(bundle_path)
            html_text = html_path.read_text(encoding="utf-8")
        self.assertEqual(spec_path.name, "poster_debug_spec.json")
        self.assertIn('data-preview-status="invalid"', html_text)
        self.assertTrue(bundle["formal_export_blocked"])
        self.assertIsNone(bundle["png_path"])
        self.assertIsNone(bundle["pdf_path"])


class PipelineTests(unittest.TestCase):
    def test_analysis_mode_stops_before_poster_branch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="paper-analysis-") as temp:
            output = Path(temp) / "run"
            summary = run_pipeline(
                PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                output,
                mode="analysis",
                export_browser=False,
            )
            self.assertEqual(summary["mode"], "analysis")
            self.assertEqual(summary["status"], "passed_with_warnings")
            self.assertNotIn("poster_html", summary)
            self.assertFalse((output / "03-assets").exists())
            self.assertFalse((output / "04-poster").exists())

    def test_pipeline_allows_empty_motivation_as_warning(self) -> None:
        from paperposter.motivation_contributions import (
            build_motivation_contributions as real_build_motivation,
        )

        def build_blocked_motivation(*args, **kwargs):
            result = real_build_motivation(*args, **kwargs)
            output_dir = Path(args[-1])
            motivation_path = output_dir / "motivation_spec.json"
            motivation = read_json(motivation_path)
            motivation["items"] = []
            motivation_path.write_text(
                json.dumps(motivation),
                encoding="utf-8",
            )
            audit_path = output_dir / "motivation_audit.json"
            audit = read_json(audit_path)
            audit["status"] = "failed"
            audit["quality_status"] = "blocked"
            audit["compose_blockers"] = [
                {
                    "code": "MOTIVATION_EVIDENCE_INSUFFICIENT",
                    "displayable_item_count": 0,
                    "missing_roles": ["task_problem_or_challenge"],
                }
            ]
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            return result

        with tempfile.TemporaryDirectory(prefix="motivation-compose-block-") as temp:
            with patch(
                "paperposter.pipeline.build_motivation_contributions",
                side_effect=build_blocked_motivation,
            ):
                summary = run_pipeline(
                    PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                    Path(temp) / "run",
                    mode="poster",
                    export_browser=False,
                )
            self.assertIn(summary["status"], {"passed", "passed_with_warnings"})
            self.assertEqual(
                summary["motivation_preflight_warnings"][0]["code"],
                "MOTIVATION_EVIDENCE_INSUFFICIENT",
            )
            self.assertTrue(Path(summary["poster_spec"]).exists())

    def test_pdf_rejects_basic_parser(self) -> None:
        with tempfile.TemporaryDirectory(prefix="paper-parser-policy-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            with self.assertRaisesRegex(RuntimeError, "only supports parser='mineru'"):
                ingest(pdf, root / "out", "basic-pdf")

    def test_missing_configured_mineru_writes_failure_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="paper-mineru-missing-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            missing = root / "missing-mineru-open-api.exe"
            with (
                patch.dict(
                    os.environ,
                    {"PAPERPOSTER_MINERU_CLI": str(missing)},
                    clear=False,
                ),
                self.assertRaisesRegex(RuntimeError, "PAPERPOSTER_MINERU_CLI"),
            ):
                ingest(pdf, root / "out", "mineru")
            report = read_json(root / "out" / "parse_report.json")
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["requested_parser"], "mineru")
            self.assertIsNone(report["actual_parser"])

    def test_offline_pipeline_selects_figure_two_not_figure_one(self) -> None:
        with tempfile.TemporaryDirectory(prefix="paper-reader-") as temp:
            output = Path(temp) / "run"
            summary = run_pipeline(
                PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                output,
                mode="poster",
                export_browser=False,
            )
            self.assertEqual(summary["status"], "passed")
            selected = read_json(Path(summary["selected_assets"]))
            method_graph = read_json(Path(summary["method_graph"]))
            method_figure_map = read_json(Path(summary["method_figure_map"]))
            method_visual = read_json(Path(summary["method_visual_plan"]))
            key_idea = read_json(Path(summary["key_idea_spec"]))
            self.assertEqual(selected["overview_asset"]["id"], "figure-2")
            self.assertFalse(selected["figure_number_prior_used"])
            self.assertEqual(selected["captions_inspected"], 4)
            self.assertNotIn(
                "figure-1",
                {asset["id"] for asset in selected["result_assets"]},
            )
            self.assertEqual(len(method_graph["nodes"]), 3)
            self.assertEqual(method_visual["mode"], "single_overview")
            self.assertEqual(method_visual["overview_asset_id"], "figure-2")
            self.assertEqual(len(method_visual["storyboard_items"]), 3)
            self.assertTrue(
                all(
                    item["display_mode"] == "mechanism_flow"
                    for item in method_visual["storyboard_items"]
                )
            )
            self.assertEqual(method_visual["module_coverage_ratio"], 1.0)
            self.assertIsNone(key_idea["equation"]["equation_id"])
            self.assertNotEqual(key_idea["type"], "formula_centered")
            self.assertIsNone(key_idea["visual"]["overview_asset_id"])
            self.assertIn("figure-3", method_figure_map["result_excluded_ids"])
            self.assertIn("figure-1", method_figure_map["result_excluded_ids"])
            self.assertEqual(method_visual["result_asset_ids_in_method"], [])
            html_text = Path(summary["poster_html"]).read_text(encoding="utf-8")
            self.assertIn('data-asset-id="figure-2"', html_text)
            self.assertIn('data-method-mode="single_overview"', html_text)
            self.assertIn("method-mechanism-flow", html_text)
            self.assertNotIn(
                '<div class="method-story-placeholder">',
                html_text,
            )
            self.assertNotIn('data-method-asset-id="figure-3"', html_text)
            self.assertIn("<h2>Project</h2>", html_text)
            self.assertIn("Code: Open source", html_text)
            self.assertIn("https://example.org/code", html_text)
            self.assertNotIn("Conclusion &amp; Limitations", html_text)
            self.assertNotIn(r"\[", html_text)
            self.assertNotIn("…", html_text)
            self.assertNotIn("{{", html_text)

    def test_method_storyboard_degrades_missing_image_to_mechanism_flow(
        self,
    ) -> None:
        items = [
            {
                "asset_id": "missing-figure",
                "display_mode": "original_figure",
                "module_ids": ["module-1"],
                "label": "Context Mixer",
                "description": "Combines local and global context.",
                "flow": {
                    "visual_type": "mechanism_flow",
                    "stages": [
                        {
                            "label": "Mechanism",
                            "text": "Combines local and global context",
                        }
                    ],
                },
            }
        ]
        with tempfile.TemporaryDirectory(prefix="method-card-fallback-") as temp:
            rendered = _method_storyboard(
                items,
                {},
                Path(temp),
                Path(temp),
            )
        self.assertIn('data-method-card-mode="mechanism_flow"', rendered)
        self.assertIn("method-mechanism-flow", rendered)
        self.assertNotIn("Method figure unavailable", rendered)
        self.assertNotIn("method-story-placeholder", rendered)

    def test_method_flow_does_not_treat_contrast_phrase_as_purpose(
        self,
    ) -> None:
        flow = _mechanism_flow(
            {
                "name": "OSS Block",
                "purpose": (
                    "In contrast to the Vision Mamba block, our proposed OSS "
                    "block introduces a module capable of modeling information "
                    "flows from diverse feature dimensions."
                ),
            }
        )
        self.assertEqual(len(flow["stages"]), 1)
        self.assertEqual(flow["stages"][0]["label"], "Mechanism")
        self.assertIn("OSS block introduces", flow["stages"][0]["text"])
        self.assertNotIn("recent design", flow["stages"][0]["text"])

    def test_multi_figure_storyboard_uses_only_method_modules(self) -> None:
        fixture = read_json(PROJECT_ROOT / "examples" / "sample-paper-ir.json")
        source_path = str(
            (PROJECT_ROOT / "examples" / "assets" / "figure-2.svg").resolve()
        )
        result_figure = fixture["figures"][2]
        result_figure["path"] = str(
            (PROJECT_ROOT / "examples" / result_figure["path"]).resolve()
        )
        for group in ("equations", "tables"):
            for asset in fixture[group]:
                if asset.get("path"):
                    asset["path"] = str(
                        (PROJECT_ROOT / "examples" / asset["path"]).resolve()
                    )
        fixture["figures"] = [
            {
                "id": "module-ingestion",
                "asset_type": "figure",
                "caption": "Structured ingestion module.",
                "page": 3,
                "section_id": "method",
                "path": source_path,
                "context_before": "",
                "context_after": "",
                "cited_by": [],
            },
            {
                "id": "module-routing",
                "asset_type": "figure",
                "caption": "Claim-to-evidence routing mechanism.",
                "page": 4,
                "section_id": "method",
                "path": source_path,
                "context_before": "",
                "context_after": "",
                "cited_by": [],
            },
            {
                "id": "module-gate",
                "asset_type": "figure",
                "caption": "Hard quality gate module.",
                "page": 5,
                "section_id": "method",
                "path": source_path,
                "context_before": "",
                "context_after": "",
                "cited_by": [],
            },
            result_figure,
        ]
        with tempfile.TemporaryDirectory(prefix="paper-storyboard-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            paper_path.write_text(json.dumps(fixture), encoding="utf-8")
            summary = run_pipeline(
                paper_path,
                root / "run",
                mode="poster",
                export_browser=False,
            )
            self.assertEqual(
                summary["status"],
                "passed",
                read_json(Path(summary["qa_report"])),
            )
            method_visual = read_json(Path(summary["method_visual_plan"]))
            self.assertEqual(method_visual["mode"], "multi_figure_storyboard")
            self.assertEqual(
                {item["asset_id"] for item in method_visual["storyboard_items"]},
                {"module-ingestion", "module-routing", "module-gate"},
            )
            self.assertNotIn("figure-3", method_visual["method_asset_ids"])
            html_text = Path(summary["poster_html"]).read_text(encoding="utf-8")
            self.assertIn('data-method-mode="multi_figure_storyboard"', html_text)
            self.assertIn('data-method-asset-id="module-routing"', html_text)
            self.assertNotIn('data-method-asset-id="figure-3"', html_text)

    def test_no_overview_returns_explicit_fallback(self) -> None:
        fixture = read_json(PROJECT_ROOT / "examples" / "sample-paper-ir.json")
        for figure in fixture["figures"]:
            figure["caption"] = "Qualitative experimental result and ablation visualization."
            figure["section_id"] = "results"
            figure["context_before"] = ""
            figure["context_after"] = ""
            figure["cited_by"] = []
        with tempfile.TemporaryDirectory(prefix="paper-assets-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            evidence_path = root / "evidence.json"
            paper_path.write_text(json.dumps(fixture), encoding="utf-8")
            evidence_path.write_text(
                json.dumps({"paper_id": fixture["paper_id"], "claims": []}),
                encoding="utf-8",
            )
            _, selected_path, _ = select_assets(paper_path, evidence_path, root / "out")
            selected = read_json(selected_path)
            self.assertIsNone(selected["overview_asset"])
            self.assertEqual(selected["fallback"], "no-overview-figure")

    def test_pipeline_replays_failed_results_stage_and_dependencies(self) -> None:
        qa_calls = 0

        def fake_validate(*args, **kwargs):
            nonlocal qa_calls
            qa_calls += 1
            output_dir = Path(args[-1])
            if qa_calls == 1:
                payload = {
                    "status": "failed",
                    "issues": [
                        {
                            "code": "RESULT_NUMERIC_CONTEXT_MISSING",
                            "severity": "error",
                            "return_to": "paper-experimental-results",
                        }
                    ],
                    "return_to": "paper-experimental-results",
                }
            else:
                payload = {
                    "status": "passed",
                    "issues": [],
                    "return_to": None,
                }
            path = output_dir / "final_qa_report.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            return path

        from paperposter.experimental_results import (
            build_experimental_results as real_build_results,
        )
        from paperposter.highlights import build_highlights as real_build_highlights

        with tempfile.TemporaryDirectory(prefix="pipeline-repair-results-") as temp:
            with (
                patch(
                    "paperposter.pipeline.validate_poster",
                    side_effect=fake_validate,
                ),
                patch(
                    "paperposter.pipeline.build_experimental_results",
                    wraps=real_build_results,
                ) as results_spy,
                patch(
                    "paperposter.pipeline.build_highlights",
                    wraps=real_build_highlights,
                ) as highlights_spy,
            ):
                summary = run_pipeline(
                    PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                    Path(temp) / "run",
                    mode="poster",
                    export_browser=False,
                )
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(results_spy.call_count, 2)
        self.assertEqual(highlights_spy.call_count, 2)
        self.assertEqual(
            summary["validation_attempts"][0]["repaired_dependency_chain"],
            ["paper-experimental-results", "paper-highlights"],
        )

    def test_pipeline_stops_repeated_stage_failure_as_no_progress(self) -> None:
        def fake_validate(*args, **kwargs):
            output_dir = Path(args[-1])
            payload = {
                "status": "failed",
                "issues": [
                    {
                        "code": "METHOD_FIGURE_ROLE_CONFLICT",
                        "severity": "error",
                        "return_to": "paper-method-figure-map",
                    }
                ],
                "return_to": "paper-method-figure-map",
            }
            path = output_dir / "final_qa_report.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            return path

        with tempfile.TemporaryDirectory(prefix="pipeline-no-progress-") as temp:
            with patch(
                "paperposter.pipeline.validate_poster",
                side_effect=fake_validate,
            ):
                summary = run_pipeline(
                    PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                    Path(temp) / "run",
                    mode="poster",
                    export_browser=False,
                    max_validation_cycles=3,
                )
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(len(summary["validation_attempts"]), 2)
        self.assertTrue(summary["validation_attempts"][-1]["no_progress"])

    def test_no_overview_builds_sourced_method_flow(self) -> None:
        graph = {
            "nodes": [
                {
                    "id": "method-node-1",
                    "order": 1,
                    "name": "Global encoder",
                    "purpose": "Captures long-range context across the image.",
                    "sources": [{"block_id": "p3-b1"}],
                },
                {
                    "id": "method-node-2",
                    "order": 2,
                    "name": "Local decoder",
                    "purpose": "Restores fine structures with local features.",
                    "sources": [{"block_id": "p4-b2"}],
                },
            ]
        }
        visual = {
            "callouts": [
                {
                    "module_id": node["id"],
                    "order": node["order"],
                    "label": node["name"],
                    "description": node["purpose"],
                    "sources": node["sources"],
                }
                for node in graph["nodes"]
            ]
        }
        items = _method_overview_flow_items(visual, graph)
        self.assertEqual(
            [item["module_id"] for item in items],
            ["method-node-1", "method-node-2"],
        )
        self.assertEqual(items[0]["source_block_ids"], ["p3-b1"])
        with tempfile.TemporaryDirectory(prefix="method-overview-flow-") as temp:
            rendered = _method_overview_content(
                {
                    "asset": None,
                    "fallback": "sourced_method_flow",
                    "flow_items": items,
                },
                {},
                Path(temp),
                Path(temp),
            )
        self.assertIn('data-method-overview-mode="sourced_method_flow"', rendered)
        self.assertIn('data-method-overview-flow-count="2"', rendered)
        self.assertIn('data-module-id="method-node-2"', rendered)
        self.assertNotIn("does not provide a reliable overview", rendered)

    def test_missing_overview_asset_and_flow_fails_qa(self) -> None:
        paper_ir = {
            "blocks": [
                {"id": "p3-b1", "type": "paragraph", "text": "Method evidence."}
            ]
        }
        nodes = [
            {
                "id": "method-node-1",
                "sources": [{"block_id": "p3-b1"}],
            }
        ]
        issues = _validate_method_overview(
            {"asset": None, "fallback": "no-overview-figure", "flow_items": []},
            nodes,
            paper_ir,
        )
        self.assertEqual(issues[0]["code"], "METHOD_OVERVIEW_CONTENT_MISSING")

    def test_ambiguous_overview_is_rejected_for_sourced_flow(self) -> None:
        graph = {
            "schema_version": "1.0.0",
            "paper_id": "ambiguous-overview",
            "nodes": [
                {
                    "id": "method-node-1",
                    "order": 1,
                    "name": "Encoder",
                    "purpose": "Encodes the input into compact features.",
                    "sources": [{"block_id": "p2-b1"}],
                },
                {
                    "id": "method-node-2",
                    "order": 2,
                    "name": "Decoder",
                    "purpose": "Reconstructs the target from compact features.",
                    "sources": [{"block_id": "p3-b2"}],
                },
            ],
        }
        figure_map = {
            "overview_asset_id": "figure-1",
            "overview_selection_ambiguous": True,
            "overview_ranking": [
                {"asset_id": "figure-1", "score": 12.0},
                {"asset_id": "figure-2", "score": 11.8},
            ],
            "records": [
                {
                    "asset_id": "figure-1",
                    "role": "method_overview",
                    "module_mappings": [
                        {
                            "module_id": "method-node-1",
                            "score": 0.9,
                            "match_kind": "complete_overview",
                        }
                    ],
                },
                {
                    "asset_id": "figure-2",
                    "role": "method_overview",
                    "module_mappings": [
                        {
                            "module_id": "method-node-2",
                            "score": 0.9,
                            "match_kind": "complete_overview",
                        }
                    ],
                },
            ],
            "result_excluded_ids": [],
        }
        paper_ir = {
            "schema_version": "1.0.0",
            "paper_id": "ambiguous-overview",
            "metadata": {"title": "Ambiguous Overview", "authors": []},
            "blocks": [],
        }
        with tempfile.TemporaryDirectory(prefix="ambiguous-overview-") as temp:
            root = Path(temp)
            paper_path = root / "paper.json"
            graph_path = root / "method_graph.json"
            map_path = root / "method_figure_map.json"
            paper_path.write_text(json.dumps(paper_ir), encoding="utf-8")
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            map_path.write_text(json.dumps(figure_map), encoding="utf-8")
            plan_path, _ = compose_method_visual(
                paper_path,
                graph_path,
                map_path,
                root / "out",
            )
            plan = read_json(plan_path)
        self.assertIsNone(plan["overview_asset_id"])
        self.assertTrue(plan["decision"]["ambiguous_overview_rejected"])
        self.assertEqual(plan["method_asset_ids"], [])
        self.assertTrue(
            all(
                item["display_mode"] == "mechanism_flow"
                for item in plan["storyboard_items"]
            )
        )

    def test_overview_flow_requires_real_module_and_source_block(self) -> None:
        issues = _validate_method_overview(
            {
                "asset": None,
                "fallback": "sourced_method_flow",
                "flow_items": [
                    {
                        "module_id": "unknown-module",
                        "label": "Stage",
                        "text": "Performs the operation.",
                        "source_block_ids": ["unknown-block"],
                    }
                ],
            },
            [{"id": "method-node-1"}],
            {"blocks": [{"id": "p3-b1"}]},
        )
        self.assertEqual(issues[0]["code"], "METHOD_OVERVIEW_FLOW_INVALID")

    @unittest.skipUnless(all(_find_runtime().values()), "Browser export runtime unavailable")
    def test_browser_exports_png_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory(prefix="paper-render-") as temp:
            summary = run_pipeline(
                PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                Path(temp) / "run",
                mode="poster",
                export_browser=True,
            )
            self.assertEqual(summary["status"], "passed")
            self.assertTrue(Path(summary["poster_png"]).is_file())
            self.assertTrue(Path(summary["poster_pdf"]).is_file())


if __name__ == "__main__":
    unittest.main()
