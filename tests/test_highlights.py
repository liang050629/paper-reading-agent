from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paperposter.highlights import (
    _candidate_from_metric,
    build_highlights,
    evaluate_highlight_candidate,
    recompute_improvement,
    select_highlights_from_candidates,
    validate_highlights_spec,
)
from paperposter.experimental_results import extract_key_metrics


def candidate(
    *,
    candidate_id: str = "claim-1:table-1:r2c2",
    claim_id: str = "claim-1",
    claim_text: str = "The full model improves Accuracy on Dataset-A.",
    metric: str = "Accuracy",
    dataset: str = "Dataset-A",
    primary_value: str = "90%",
    baseline_value: str = "80%",
    row_index: int = 2,
    column_index: int = 2,
) -> dict:
    condition = {
        "dataset": dataset,
        "split": "official test split",
        "metric": metric,
        "protocol": "same evaluation protocol",
        "fine_tuning": "without fine-tuning",
        "recovery": "without recovery",
    }
    return {
        "candidate_id": candidate_id,
        "claim_id": claim_id,
        "evidence_id": candidate_id,
        "claim_text": claim_text,
        "claim_verdict": "supported",
        "claim_category": "performance",
        "source_kind": "main_results",
        "source_asset_type": "table",
        "source_asset_id": "table-1",
        "page": 5,
        "source_block_ids": ["block-1"],
        "primary_value": primary_value,
        "baseline_value": baseline_value,
        "metric": metric,
        "metric_direction": "higher_is_better",
        "dataset": dataset,
        "configuration": "full proposed model",
        "baseline": "StrongBaseline",
        "baseline_configuration": "full proposed model",
        "evaluation_condition": "official test split without recovery",
        "baseline_evaluation_condition": "official test split without recovery",
        "source_cell": {
            "row_index": row_index,
            "column_index": column_index,
            "value": primary_value,
            "extracted_value": primary_value,
        },
        "baseline_cell": {
            "row_index": 1,
            "column_index": column_index,
            "value": baseline_value,
            "extracted_value": baseline_value,
        },
        "row_label": "Ours",
        "column_label": metric,
        "ours_condition": deepcopy(condition),
        "baseline_condition": deepcopy(condition),
        "is_core_claim": True,
        "is_main_result": True,
        "is_ablation": False,
        "baseline_is_strong": True,
        "claim_alignment_score": 0.8,
        "claims_significance": False,
        "significance_reported": False,
        "required_caveats": [
            "full proposed model",
            "official test split without recovery",
        ],
        "caveats": [
            "full proposed model",
            "official test split without recovery",
        ],
        "dataset_count": 1,
        "trends_consistent": True,
    }


def paper_and_evidence() -> tuple[dict, dict]:
    paper_ir = {
        "paper_id": "highlight-test",
        "blocks": [{"id": "block-1", "page": 5, "text": "Main results."}],
        "figures": [],
        "tables": [
            {
                "id": "table-1",
                "asset_type": "table",
                "page": 5,
                "caption": "Main results on Dataset-A.",
                "html": (
                    "<table><tr><th>Method</th><th>Dataset</th>"
                    "<th>Accuracy</th><th>F1</th></tr>"
                    "<tr><td>StrongBaseline</td><td>Dataset-A</td>"
                    "<td>80%</td><td>70%</td></tr>"
                    "<tr><td>Ours</td><td>Dataset-A</td>"
                    "<td>90%</td><td>85%</td></tr></table>"
                ),
            }
        ],
    }
    evidence = {
        "claims": [
            {
                "claim_id": "claim-1",
                "claim": "The full model improves Accuracy on Dataset-A.",
                "verdict": "supported",
            },
            {
                "claim_id": "claim-2",
                "claim": "The full model improves F1 on Dataset-A.",
                "verdict": "supported",
            },
        ]
    }
    return paper_ir, evidence


class HighlightGateTests(unittest.TestCase):
    def test_number_without_dataset_is_rejected(self) -> None:
        value = candidate(dataset="")
        value["ours_condition"]["dataset"] = ""
        value["baseline_condition"]["dataset"] = ""
        evaluated = evaluate_highlight_candidate(value)
        self.assertFalse(evaluated["gate_results"]["context_gate"]["passed"])
        self.assertFalse(evaluated["eligible"])

    def test_recovery_mismatch_is_rejected(self) -> None:
        value = candidate()
        value["baseline_condition"]["recovery"] = "after recovery"
        evaluated = evaluate_highlight_candidate(value)
        self.assertFalse(
            evaluated["gate_results"]["matched_comparison_gate"]["passed"]
        )
        self.assertFalse(evaluated["eligible"])

    def test_relative_percent_and_percentage_points_are_distinct(self) -> None:
        result = recompute_improvement(
            "90%",
            "80%",
            "Accuracy",
            "higher_is_better",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["absolute_difference"], 10.0)
        self.assertEqual(result["absolute_difference_type"], "percentage_points")
        self.assertEqual(result["relative_difference_percent"], 12.5)

    def test_top1_without_percent_sign_is_still_percentage_points(self) -> None:
        result = recompute_improvement(
            "81.1",
            "77.9",
            "Top-1 (%)",
            "higher_is_better",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["absolute_difference"], 3.2)
        self.assertEqual(result["absolute_difference_type"], "percentage_points")

    def test_paired_variant_requires_the_same_backbone(self) -> None:
        value = candidate(
            metric="Top-1 (%)",
            primary_value="81.1",
            baseline_value="74.1",
        )
        value["comparison_pair_kind"] = "paired_base_variant"
        value["row_label"] = "ViT-B\u2020"
        value["baseline_row_label"] = "DeiT-T"
        evaluated = evaluate_highlight_candidate(value)
        self.assertFalse(
            evaluated["gate_results"]["matched_comparison_gate"]["passed"]
        )
        self.assertFalse(evaluated["eligible"])

    def test_broad_performance_claim_accepts_top1_but_miou_claim_does_not(self) -> None:
        metric = {
            "value": "81.1",
            "metric": "Top-1 (%)",
            "direction": "higher_is_better",
            "baseline": "Dense ViT-B",
            "baseline_value": "77.9",
            "dataset": "ImageNet-1k dataset",
            "configuration": "full-model row",
            "baseline_configuration": "full-model row",
            "evaluation_condition": "same training recipe",
            "baseline_evaluation_condition": "same training recipe",
            "row_label": "ExFusion ViT-B",
            "baseline_row_label": "Dense ViT-B",
            "column_label": "Top-1 (%)",
            "source_cell": {
                "row_index": 2,
                "column_index": 1,
                "value": "81.1",
                "extracted_value": "81.1",
            },
            "baseline_cell": {
                "row_index": 1,
                "column_index": 1,
                "value": "77.9",
                "extracted_value": "77.9",
            },
            "source_block_ids": ["block-1"],
            "baseline_selection": "strongest_matched",
        }
        asset = {
            "id": "table-1",
            "asset_type": "table",
            "page": 5,
            "caption": "Main Top-1 comparison on ImageNet-1k dataset.",
        }
        paper_ir = {
            "blocks": [
                {
                    "id": "block-1",
                    "text": "Main Top-1 results on ImageNet-1k.",
                }
            ]
        }
        broad = _candidate_from_metric(
            metric,
            {
                "claim_id": "claim-1",
                "claim": (
                    "ExFusion enhances Transformer performance without "
                    "incurring additional inference overhead."
                ),
                "verdict": "supported",
            },
            asset,
            paper_ir,
            source_kind="main_results",
            is_main_result=True,
        )
        miou = _candidate_from_metric(
            metric,
            {
                "claim_id": "claim-2",
                "claim": "The method improves mIoU on ADE20K dataset.",
                "verdict": "supported",
            },
            asset,
            paper_ir,
            source_kind="main_results",
            is_main_result=True,
        )
        self.assertTrue(
            evaluate_highlight_candidate(broad)["gate_results"][
                "claim_alignment_gate"
            ]["passed"]
        )
        self.assertTrue(broad["constraint_preservation_supported"])
        self.assertFalse(
            evaluate_highlight_candidate(miou)["gate_results"][
                "claim_alignment_gate"
            ]["passed"]
        )

    def test_primary_asset_claim_binding_recovers_low_lexical_overlap(self) -> None:
        value = candidate(
            claim_text="The proposed model achieves the strongest main result."
        )
        value["claim_verdict"] = "partially_supported"
        value["claim_alignment_score"] = 0.0
        value["upstream_claim_binding"] = True
        evaluated = evaluate_highlight_candidate(value)
        self.assertTrue(
            evaluated["gate_results"]["claim_alignment_gate"]["passed"]
        )

    def test_claim_context_recovers_dataset_and_fov_condition(self) -> None:
        metric = {
            "value": "82.82",
            "metric": "F1",
            "direction": "higher_is_better",
            "baseline": "BCE",
            "baseline_value": "82.75",
            "dataset": "reported evaluation dataset(s)",
            "configuration": "reported configuration",
            "baseline_configuration": "reported configuration",
            "evaluation_condition": "reported evaluation condition",
            "baseline_evaluation_condition": "reported evaluation condition",
            "row_label": "BCE + MCC",
            "baseline_row_label": "BCE",
            "column_label": "F1",
            "source_cell": {
                "row_index": 3,
                "column_index": 1,
                "extracted_value": "82.82",
            },
            "baseline_cell": {
                "row_index": 1,
                "column_index": 1,
                "extracted_value": "82.75",
            },
            "source_block_ids": ["results-block"],
            "baseline_selection": "strongest_matched",
        }
        claim = {
            "claim_id": "claim-drive",
            "claim": (
                "Under the primary evaluation protocol on DRIVE without FOV, "
                "the full model reaches F1 of 82.82."
            ),
            "verdict": "supported",
            "source_block_ids": ["results-block"],
        }
        asset = {
            "id": "table-loss",
            "asset_type": "table",
            "page": 7,
            "caption": "Loss function analysis.",
        }
        paper_ir = {
            "blocks": [
                {
                    "id": "results-block",
                    "text": (
                        "Loss combinations are evaluated on DRIVE without FOV "
                        "under the primary evaluation protocol."
                    ),
                }
            ]
        }
        recovered = _candidate_from_metric(
            metric,
            claim,
            asset,
            paper_ir,
            source_kind="main_results",
            is_main_result=True,
            upstream_claim_binding=True,
        )
        evaluated = evaluate_highlight_candidate(recovered)
        self.assertEqual(recovered["dataset"], "DRIVE")
        self.assertIn("without FOV", recovered["evaluation_condition"])
        self.assertEqual(recovered["configuration"], "BCE + MCC configuration")
        self.assertEqual(recovered["baseline_configuration"], "BCE configuration")
        self.assertTrue(evaluated["gate_results"]["context_gate"]["passed"])
        self.assertTrue(
            evaluated["gate_results"]["matched_comparison_gate"]["passed"]
        )

    def test_matched_protocol_allows_distinct_method_configurations(self) -> None:
        value = candidate()
        value["configuration"] = "proposed full model"
        value["baseline_configuration"] = "baseline full model"
        evaluated = evaluate_highlight_candidate(value)
        self.assertTrue(
            evaluated["gate_results"]["matched_comparison_gate"]["passed"]
        )

    def test_mdice_is_treated_as_a_percentage_metric(self) -> None:
        result = recompute_improvement(
            "0.820",
            "0.810",
            "mDice",
            "higher_is_better",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["absolute_difference_type"], "percentage_points")
        self.assertEqual(result["absolute_difference"], 1.0)

    def test_efficiency_metric_cannot_displace_primary_effectiveness(self) -> None:
        effectiveness = candidate(
            metric="Top-1 (%)",
            primary_value="81.1",
            baseline_value="77.9",
        )
        efficiency = candidate(
            candidate_id="claim-1:table-1:r2c3",
            metric="#Params",
            primary_value="86.6",
            baseline_value="86.6",
            column_index=3,
        )
        efficiency["metric_direction"] = "lower_is_better"
        efficiency["ours_condition"]["metric"] = "#Params"
        efficiency["baseline_condition"]["metric"] = "#Params"
        efficiency["source_kind"] = "efficiency"
        efficiency["claim_text"] = (
            "The method improves performance without additional parameters."
        )
        efficiency["constraint_preservation_supported"] = True
        selected, _ = select_highlights_from_candidates(
            [efficiency, effectiveness]
        )
        self.assertEqual(selected[0]["role"], "primary_effectiveness")
        self.assertEqual(selected[0]["metric"], "Top-1 (%)")
        self.assertIn("+3.20 pp", selected[0]["context"])
        self.assertEqual(
            selected[1]["role"],
            "efficiency_or_generalization_or_robustness",
        )
        self.assertEqual(selected[1]["primary_value"], "No extra parameters")

    def test_unchanged_cost_requires_an_explicit_preservation_claim(self) -> None:
        value = candidate(
            metric="#Params",
            primary_value="86.6",
            baseline_value="86.6",
        )
        value["metric_direction"] = "lower_is_better"
        value["ours_condition"]["metric"] = "#Params"
        value["baseline_condition"]["metric"] = "#Params"
        value["source_kind"] = "efficiency"
        value["claim_text"] = "The method improves classification accuracy."
        value["constraint_preservation_supported"] = False
        evaluated = evaluate_highlight_candidate(value)
        self.assertFalse(
            evaluated["gate_results"]["claim_alignment_gate"]["passed"]
        )
        self.assertFalse(evaluated["eligible"])

    def test_single_dataset_cannot_claim_consistent_gains(self) -> None:
        value = candidate(
            claim_text="The method delivers consistent gains across all datasets."
        )
        value["dataset_count"] = 1
        evaluated = evaluate_highlight_candidate(value)
        self.assertFalse(
            evaluated["gate_results"]["representativeness_gate"]["passed"]
        )
        self.assertFalse(evaluated["eligible"])

    def test_ablation_does_not_replace_full_model_result(self) -> None:
        main = candidate()
        ablation = candidate(
            candidate_id="claim-2:table-1:r2c3",
            claim_id="claim-2",
            metric="F1",
            primary_value="85%",
            baseline_value="70%",
            column_index=3,
        )
        ablation["is_ablation"] = True
        ablation["is_main_result"] = False
        selected, _ = select_highlights_from_candidates([ablation, main])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["claim_id"], "claim-1")

    def test_contribution_number_cannot_become_highlight(self) -> None:
        value = candidate(claim_text="1. Accuracy reaches 90% on Dataset-A.")
        evaluated = evaluate_highlight_candidate(value)
        self.assertFalse(
            evaluated["gate_results"]["claim_alignment_gate"]["passed"]
        )
        self.assertFalse(evaluated["eligible"])

    def test_only_two_strong_candidates_render_two_cards(self) -> None:
        first = candidate()
        second = candidate(
            candidate_id="claim-2:table-1:r2c3",
            claim_id="claim-2",
            claim_text="The full model improves F1 on Dataset-A.",
            metric="F1",
            primary_value="85%",
            baseline_value="70%",
            column_index=3,
        )
        selected, evaluated = select_highlights_from_candidates([first, second])
        self.assertEqual(sum(item["eligible"] for item in evaluated), 2)
        self.assertEqual(len(selected), 2)

    def test_zero_selected_highlights_warns_without_blocking_poster(self) -> None:
        import json
        import tempfile

        paper_ir, evidence = paper_and_evidence()
        story = {"nodes": []}
        experimental = {"primary_asset": None, "key_metrics": []}
        with tempfile.TemporaryDirectory(prefix="highlights-empty-") as temp:
            root = Path(temp)
            paths = {}
            for name, value in (
                ("paper.json", paper_ir),
                ("story.json", story),
                ("evidence.json", evidence),
                ("results.json", experimental),
            ):
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                paths[name] = path
            _, report_path = build_highlights(
                paths["paper.json"],
                paths["story.json"],
                paths["evidence.json"],
                paths["results.json"],
                root / "out",
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "passed_with_warnings")
        self.assertEqual(
            report["issues"][0]["code"],
            "HIGHLIGHT_EVIDENCE_INSUFFICIENT",
        )
        self.assertEqual(report["issues"][0]["severity"], "warning")

    def test_final_highlight_traces_to_exact_table_cell(self) -> None:
        paper_ir, evidence = paper_and_evidence()
        selected, _ = select_highlights_from_candidates([candidate()])
        spec = {"highlights": selected}
        issues = validate_highlights_spec(spec, paper_ir, evidence)
        self.assertFalse(
            any(issue["code"] == "HIGHLIGHT_CELL_TRACE_INVALID" for issue in issues)
        )

    def test_semantic_duplicate_highlights_are_not_selected(self) -> None:
        first = candidate()
        duplicate = candidate(candidate_id="claim-1:table-1:r2c2-copy")
        selected, _ = select_highlights_from_candidates([first, duplicate])
        self.assertEqual(len(selected), 1)

    def test_all_improvements_are_recomputed_from_raw_values(self) -> None:
        paper_ir, evidence = paper_and_evidence()
        selected, _ = select_highlights_from_candidates([candidate()])
        selected[0]["absolute_difference"] = 11.0
        issues = validate_highlights_spec(
            {"highlights": selected},
            paper_ir,
            evidence,
        )
        self.assertIn(
            "HIGHLIGHT_ARITHMETIC_MISMATCH",
            {issue["code"] for issue in issues},
        )

    def test_transposed_main_table_keeps_exact_method_cells(self) -> None:
        asset = {
            "id": "table-2",
            "asset_type": "table",
            "page": 6,
            "caption": "Quantitative results on Dataset-A.",
            "html": (
                "<table><tr><td>Metric</td><td>Baseline-A</td>"
                "<td>Baseline-B</td><td>DSFormer</td></tr>"
                "<tr><td>OA (%)</td><td>91.2</td><td>93.4</td>"
                "<td>96.6</td></tr></table>"
            ),
        }
        metrics = extract_key_metrics(
            asset,
            {"claim": "DSFormer reaches 96.6% OA on Dataset-A."},
            {"metadata": {"title": "DSFormer for Classification"}},
            {},
            ["block-2"],
        )
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["source_cell"]["row_index"], 1)
        self.assertEqual(metrics[0]["source_cell"]["column_index"], 3)
        self.assertEqual(metrics[0]["baseline_cell"]["column_index"], 2)
        self.assertEqual(metrics[0]["baseline_value"], "93.4")


if __name__ == "__main__":
    unittest.main()
