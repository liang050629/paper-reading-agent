from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paperposter.common import read_json, write_json
from paperposter.experimental_results import (
    _edge_ink_metrics,
    _focus_table_payload,
    _paper_method_terms,
    _prepare_table_focus_crop,
    _table_context,
    _table_focus_columns,
    _layout,
    build_experimental_results,
    extract_key_metrics,
    parse_html_table,
    validate_experimental_results_spec,
)
from paperposter.render import _experimental_results_content


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    asset_dir = root / "assets"
    asset_dir.mkdir()
    Image.new("RGB", (1400, 520), "white").save(asset_dir / "main.png")
    Image.new("RGB", (1000, 360), "white").save(asset_dir / "qual.png")
    paper_ir = {
        "schema_version": "1.0.0",
        "paper_id": "fancynet",
        "metadata": {
            "title": "FancyNet for Reliable Medical Segmentation",
            "authors": [],
            "affiliations": [],
        },
        "blocks": [
            {
                "id": "b-main",
                "type": "table",
                "text": "FancyNet reaches Dice 0.91 and HD95 4.2 against StrongNet.",
                "page": 6,
                "section_id": "results",
                "bbox": [10, 20, 90, 70],
            },
            {
                "id": "b-qual",
                "type": "caption",
                "text": "Qualitative comparison preserves fine boundaries.",
                "page": 7,
                "section_id": "results",
                "bbox": [10, 20, 90, 70],
            },
        ],
        "figures": [
            {
                "id": "figure-9",
                "asset_type": "figure",
                "caption": "Qualitative visual comparison of boundary preservation.",
                "page": 7,
                "section_id": "qualitative-results",
                "path": "assets/qual.png",
                "bbox": [10, 20, 90, 70],
                "context_before": "",
                "context_after": "",
                "cited_by": ["b-qual"],
            }
        ],
        "equations": [],
        "tables": [
            {
                "id": "table-7",
                "asset_type": "table",
                "caption": (
                    "Main macro-averaged comparison on ClinicDB under the "
                    "matched single-model setting."
                ),
                "page": 6,
                "section_id": "main-results",
                "path": "assets/main.png",
                "bbox": [10, 20, 90, 70],
                "context_before": "",
                "context_after": "FancyNet outperforms StrongNet.",
                "cited_by": ["b-main"],
                "footnote": "",
                "html": (
                    "<table><tr><th>Dataset</th><th>Method</th>"
                    "<th>Dice ↑</th><th>HD95 ↓</th><th>Params ↓</th></tr>"
                    "<tr><td>ClinicDB</td><td>StrongNet</td>"
                    "<td>0.88</td><td>5.8</td><td>18M</td></tr>"
                    "<tr><td>ClinicDB</td><td>FancyNet (ours)</td>"
                    "<td>0.91</td><td>4.2</td><td>12M</td></tr></table>"
                ),
            }
        ],
    }
    story = {
        "experimental_design": {
            "summary": "All models use the same split and evaluation protocol."
        }
    }
    evidence = {
        "claims": [
            {
                "claim_id": "claim-main",
                "claim": (
                    "FancyNet outperforms StrongNet on ClinicDB with Dice 0.91 "
                    "and HD95 4.2 using 12M parameters."
                ),
                "sources": [{"block_id": "b-main", "page": 6}],
                "evidence": [
                    {
                        "source": {
                            "block_id": "b-main",
                            "page": 6,
                            "quote": "FancyNet reaches Dice 0.91 and HD95 4.2.",
                        },
                        "strength": "direct",
                    }
                ],
                "verdict": "supported",
                "confidence": 0.9,
                "limitations": [],
            },
            {
                "claim_id": "claim-qual",
                "claim": "Qualitative comparison shows fewer boundary artifacts.",
                "sources": [{"block_id": "b-qual", "page": 7}],
                "evidence": [],
                "verdict": "partially_supported",
                "confidence": 0.6,
                "limitations": [],
            },
        ]
    }
    paper_path = write_json(root / "paper_ir.json", paper_ir)
    story_path = write_json(root / "paper_story.json", story)
    evidence_path = write_json(root / "claim_evidence.json", evidence)
    return paper_path, story_path, evidence_path


class ExperimentalResultsTests(unittest.TestCase):
    def test_decorated_variant_uses_exact_plain_backbone_as_baseline(self) -> None:
        table = {
            "id": "table-variants",
            "asset_type": "table",
            "page": 6,
            "caption": (
                "ImageNet-1k results. Variants marked with \u2020 use our "
                "multi-expert fusion method."
            ),
            "html": (
                "<table><tr><th>Method</th><th>#Params</th>"
                "<th>FLOPs</th><th>Top-1 (%)</th></tr>"
                "<tr><td>ViT-S</td><td>22.1</td><td>4.6</td><td>71.8</td></tr>"
                "<tr><td>ViT-S\u2020</td><td>22.1</td><td>4.6</td>"
                "<td>80.4 (+8.6)</td></tr>"
                "<tr><td>ViT-B</td><td>86.6</td><td>17.6</td><td>77.9</td></tr>"
                "<tr><td>ViT-B\u2020</td><td>86.6</td><td>17.6</td>"
                "<td>81.1 (+3.2)</td></tr>"
                "<tr><td>DeiT-T</td><td>5.7</td><td>1.2</td><td>72.2</td></tr>"
                "<tr><td>DeiT-T\u2020</td><td>5.7</td><td>1.2</td>"
                "<td>74.1 (+1.9)</td></tr></table>"
            ),
        }
        paper_ir = {
            "metadata": {
                "title": "ExFusion: Efficient Transformer Training",
            },
            "blocks": [
                {
                    "text": (
                        "Our ViT-B\u2020 and other marked variants use ExFusion."
                    )
                }
            ],
            "tables": [table],
            "figures": [],
        }
        self.assertNotIn("vit-b", _paper_method_terms(paper_ir))
        metrics = extract_key_metrics(
            table,
            {
                "claim": (
                    "The ViT-B variant reaches 81.1 Top-1 on ImageNet-1k."
                )
            },
            paper_ir,
            {"experimental_design": {"summary": "same recipe"}},
            ["block-results"],
        )
        top1 = next(item for item in metrics if "Top-1" in item["metric"])
        self.assertEqual(top1["row_label"], "ViT-B\u2020")
        self.assertEqual(top1["baseline_row_label"], "ViT-B")
        self.assertEqual(top1["baseline_value"], "77.9")
        self.assertEqual(top1["delta"], "+3.2")
        self.assertEqual(top1["baseline_selection"], "paired_base_variant")

    def test_method_acronym_does_not_make_baseline_row_ours(self) -> None:
        table = {
            "id": "table-msd-ema",
            "asset_type": "table",
            "caption": "Comparative results on five polyp datasets.",
            "html": (
                "<table><tr><td rowspan=\"2\">DatasetsMethods</td>"
                "<td colspan=\"2\">CVC-ColonDB</td><td colspan=\"2\">ETIS</td></tr>"
                "<tr><td>IoU</td><td>Dice</td><td>IoU</td><td>Dice</td></tr>"
                "<tr><td>EMA-Net(CVPR'19)</td><td>0.554</td><td>0.648</td>"
                "<td>0.481</td><td>0.577</td></tr>"
                "<tr><td>APCNet(TIM'23)</td><td>0.679</td><td>0.758</td>"
                "<td>0.648</td><td>0.726</td></tr>"
                "<tr><td>Ours</td><td>0.684</td><td>0.763</td>"
                "<td>0.691</td><td>0.775</td></tr></table>"
            ),
        }
        metrics = extract_key_metrics(
            table,
            {"claim": "MSD-EMA improves polyp segmentation."},
            {"metadata": {"title": "MSD-EMA: Multiscale Decoupled EM Attention"}},
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertGreaterEqual(len(metrics), 2)
        self.assertTrue(all(item["row_label"] == "Ours" for item in metrics))
        self.assertNotIn(
            "EMA-Net(CVPR'19)",
            {item["row_label"] for item in metrics},
        )

    def test_claim_metrics_fallback_supports_oa_improvements(self) -> None:
        figure = {
            "id": "figure-13",
            "asset_type": "figure",
            "caption": (
                "OA values of different MSCNs with various g values counted "
                "on the UCM, AID, and NWPU datasets."
            ),
            "context_before": "",
            "context_after": "",
        }
        metrics = extract_key_metrics(
            figure,
            {
                "claim": (
                    "Compared to other methods, the improvements achieved by "
                    "MSCN are 0.69% (over CrossViT-15-D), 0.57% "
                    "(over Swin-T), and 2.39% (over TCNN)."
                )
            },
            {"metadata": {"title": "MSCN"}},
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertEqual(len(metrics), 3)
        self.assertEqual({item["metric"] for item in metrics}, {"OA"})
        self.assertEqual(
            [item["baseline"] for item in metrics],
            ["CrossViT-15-D", "Swin-T", "TCNN"],
        )

    def test_focus_table_compacts_repeated_group_headers(self) -> None:
        rows = [
            [
                "ImageNet-22K pre-trained models / method",
                "ImageNet-22K pre-trained models / image size",
                "ImageNet-22K pre-trained models / #param.",
                "ImageNet-22K pre-trained models / FLOPs",
                "ImageNet-22K pre-trained models / Top-1 Acc.",
            ],
            ["BaseNet", "224x224", "34.2", "80.0", "86.5"],
            ["FancyNet (ours)", "224x224", "17.7", "80.5", "87.1"],
        ]
        payload = _focus_table_payload(
            {"id": "table-imagenet", "page": 6},
            {"metadata": {"title": "FancyNet"}},
            rows,
            1,
            [0, 1],
            [0, 1, 2, 3, 4],
            [
                {"metric": "#param.", "baseline": "BaseNet"},
                {"metric": "FLOPs", "baseline": "BaseNet"},
                {"metric": "Top-1 Acc.", "baseline": "BaseNet"},
            ],
        )
        self.assertEqual(
            payload["headers"],
            ["method", "image size", "#param.", "FLOPs", "Top-1 Acc."],
        )
        self.assertEqual(payload["source_headers"], rows[0])

    def test_focus_columns_compact_six_column_table_when_metrics_are_known(self) -> None:
        rows = [
            ["Method", "Params", "FLOPs", "DSC", "ACC", "mIoU"],
            ["Base", "10M", "20", "88.1", "95.0", "80.0"],
            ["FancyNet (ours)", "12M", "18", "89.9", "96.1", "82.2"],
        ]
        selected = _table_focus_columns(
            {"caption": "Comparison on ISIC."},
            rows,
            1,
            [
                {"metric": "DSC"},
                {"metric": "ACC"},
            ],
        )
        self.assertEqual(selected, [0, 3, 4])

    def test_large_table_without_pdf_text_uses_verified_focus_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "wide.png"
            Image.new("RGB", (1200, 320), "white").save(source)
            headers = [
                "Method",
                "Params",
                "Dice",
                "HD95",
                "A",
                "B",
                "C",
                "D",
            ]
            data = [
                ["BaseNet", "20", "0.88", "5.8", "1", "2", "3", "4"],
                *[
                    [f"Other-{index}", "18", "0.87", "6.0", "1", "2", "3", "4"]
                    for index in range(7)
                ],
                ["FancyNet (ours)", "12", "0.91", "4.2", "1", "2", "3", "4"],
            ]
            html_rows = [headers, *data]
            table_html = "<table>" + "".join(
                "<tr>"
                + "".join(f"<td>{cell}</td>" for cell in row)
                + "</tr>"
                for row in html_rows
            ) + "</table>"
            asset = {
                "id": "table-wide",
                "asset_type": "table",
                "path": str(source),
                "page": 2,
                "bbox": [100, 100, 900, 500],
                "html": table_html,
            }
            asset_spec = {
                "asset_id": "table-wide",
                "asset_type": "table",
                "display_path": str(source),
                "source_resolution": {
                    "width": 1200,
                    "height": 320,
                    "source_readable": True,
                },
            }
            paper_ir = {
                "metadata": {"title": "FancyNet"},
                "provenance": {},
            }
            metrics = [
                {
                    "metric": "Dice",
                    "baseline": "BaseNet",
                    "dataset": "TestDB",
                }
            ]

            _prepare_table_focus_crop(
                asset,
                asset_spec,
                {"claim": "FancyNet reaches Dice 0.91."},
                paper_ir,
                root,
                root / "out",
                metrics,
            )

            self.assertEqual(
                asset_spec["display_mode"],
                "verified_focus_table",
            )
            self.assertEqual(
                asset_spec["focus_crop"]["coordinate_method"],
                "verified_source_table_cells",
            )
            self.assertNotEqual(
                asset_spec["focus_crop"]["row_mapping"],
                "html-row-order-to-original-table-raster",
            )
            self.assertGreaterEqual(
                len(asset_spec["focus_table"]["rows"]),
                2,
            )

    def test_edge_ink_check_detects_clipped_glyphs(self) -> None:
        safe = Image.new("RGB", (220, 80), "white")
        safe_draw = ImageDraw.Draw(safe)
        safe_draw.rectangle((40, 18, 75, 56), fill="black")
        safe_metrics = _edge_ink_metrics(safe)
        self.assertFalse(safe_metrics["glyphs_touch_crop_edge"])

        clipped = Image.new("RGB", (220, 80), "white")
        clipped_draw = ImageDraw.Draw(clipped)
        clipped_draw.rectangle((40, 0, 75, 32), fill="black")
        clipped_metrics = _edge_ink_metrics(clipped)
        self.assertTrue(clipped_metrics["glyphs_touch_crop_edge"])
        self.assertGreater(clipped_metrics["edge_ink_ratio"], 0)

    def test_unsafe_pdf_crop_falls_back_to_verified_focus_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "wide.png"
            Image.new("RGB", (1200, 360), "white").save(source)
            source_pdf = root / "paper.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
            rows = [
                ["Method", "Params", "Dice", "HD95", "A", "B", "C"],
                ["BaseNet", "20", "0.88", "5.8", "1", "2", "3"],
                *[
                    [f"Other-{index}", "18", "0.87", "6.0", "1", "2", "3"]
                    for index in range(7)
                ],
                ["FancyNet (ours)", "12", "0.91", "4.2", "1", "2", "3"],
            ]
            table_html = "<table>" + "".join(
                "<tr>"
                + "".join(f"<td>{cell}</td>" for cell in row)
                + "</tr>"
                for row in rows
            ) + "</table>"
            asset = {
                "id": "table-wide",
                "asset_type": "table",
                "path": str(source),
                "page": 1,
                "bbox": [100, 100, 900, 500],
                "html": table_html,
            }
            asset_spec = {
                "asset_id": "table-wide",
                "asset_type": "table",
                "display_path": str(source),
            }
            paper_ir = {
                "metadata": {"title": "FancyNet"},
                "provenance": {"source_path": str(source_pdf)},
            }

            def unsafe_crop(*args, **kwargs):
                target = args[-1]
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (600, 180), "white").save(target)
                return {
                    "coordinate_method": "pdf_text_boxes",
                    "geometry_confidence": 1.0,
                    "minimum_source_text_height_px": 20,
                    "duplicate_band_score": 0.0,
                    "glyph_padding_px": 4,
                    "edge_ink_ratio": 0.08,
                    "glyphs_touch_crop_edge": True,
                    "row_bounds_source": [{"source_row_index": 0}],
                    "row_bounds_padded": [{"source_row_index": 0}],
                    "row_mapping": "source-html-row-cell-union-to-pdf-text-boxes",
                    "column_mapping": "source-html-headers-to-pdf-text-boxes",
                    "separators_inserted": True,
                }

            with patch(
                "paperposter.experimental_results._pdf_text_focus_crop",
                side_effect=unsafe_crop,
            ):
                _prepare_table_focus_crop(
                    asset,
                    asset_spec,
                    {"claim": "FancyNet reaches Dice 0.91."},
                    paper_ir,
                    root,
                    root / "out",
                    [
                        {
                            "metric": "Dice",
                            "baseline": "BaseNet",
                            "dataset": "TestDB",
                        }
                    ],
                )

            self.assertEqual(
                asset_spec["display_mode"],
                "verified_focus_table",
            )
            self.assertEqual(
                asset_spec["focus_crop"]["coordinate_method"],
                "verified_source_table_cells",
            )
            self.assertFalse(
                asset_spec["focus_crop"]["glyphs_touch_crop_edge"]
            )

    def test_table_parser_preserves_rowspan_context(self) -> None:
        rows = parse_html_table(
            "<table><tr><th>Dataset</th><th>Method</th><th>Dice</th></tr>"
            '<tr><td rowspan="2">A</td><td>Base</td><td>0.8</td></tr>'
            "<tr><td>Ours</td><td>0.9</td></tr></table>"
        )
        self.assertEqual(rows[2][0], "A")
        self.assertEqual(rows[2][1], "Ours")

    def test_repeated_setting_header_keeps_multiple_metrics_in_one_context(self) -> None:
        table = {
            "id": "table-condition",
            "asset_type": "table",
            "caption": "Comparison of methods on DRIVE datasets.",
            "html": (
                "<table>"
                "<tr><th>Model</th><th>F1</th><th>Jacc</th><th>AUC</th></tr>"
                "<tr><th>Without FOV Mask</th><th>Without FOV Mask</th>"
                "<th>Without FOV Mask</th><th>Without FOV Mask</th></tr>"
                "<tr><td>StrongNet</td><td>82.61</td><td>70.15</td><td>98.62</td></tr>"
                "<tr><td>SA-UNetv2</td><td>82.82</td><td>70.69</td><td>98.71</td></tr>"
                "<tr><td>With FOV Mask</td><td>With FOV Mask</td>"
                "<td>With FOV Mask</td><td>With FOV Mask</td></tr>"
                "<tr><td>OtherNet</td><td>99.90</td><td>99.90</td><td>99.90</td></tr>"
                "</table>"
            ),
        }
        metrics = extract_key_metrics(
            table,
            {
                "claim": (
                    "SA-UNetv2 reaches F1 82.82, Jaccard 70.69, and AUC 98.71."
                )
            },
            {"metadata": {"title": "SA-UNetv2 for Retinal Segmentation"}},
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertEqual([item["metric"] for item in metrics], ["F1", "AUC", "Jacc"])
        self.assertTrue(all(item["dataset"] == "DRIVE datasets" for item in metrics))
        self.assertTrue(
            all(
                item["evaluation_condition"] == "Without FOV Mask"
                for item in metrics
            )
        )
        self.assertEqual(
            {item["baseline_value"] for item in metrics},
            {"82.61", "70.15", "98.62"},
        )

    def test_common_metric_aliases_and_significance_suffixes_are_supported(self) -> None:
        table = {
            "id": "table-aliases",
            "asset_type": "table",
            "caption": "Comparison on TestDB.",
            "html": (
                "<table><tr><th>Method</th><th>DSC↑</th><th>HD (mm)↓</th>"
                "<th>mAP↑</th><th>#P (M)↓</th></tr>"
                "<tr><td>StrongNet</td><td>90.1&lt;1e-3</td><td>12.4</td>"
                "<td>80.2</td><td>20.0</td></tr>"
                "<tr><td>FancyNet</td><td>91.0</td><td>10.2</td>"
                "<td>82.3</td><td>12.0</td></tr></table>"
            ),
        }
        metrics = extract_key_metrics(
            table,
            {"claim": "FancyNet improves DSC, HD, mAP, and parameter efficiency."},
            {"metadata": {"title": "FancyNet"}},
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertEqual(len(metrics), 4)
        self.assertIn("DSC↑", {item["metric"] for item in metrics})
        self.assertIn("HD (mm)↓", {item["metric"] for item in metrics})
        self.assertIn("mAP↑", {item["metric"] for item in metrics})
        self.assertIn("#P (M)↓", {item["metric"] for item in metrics})
        dsc = next(item for item in metrics if item["metric"] == "DSC↑")
        self.assertEqual(dsc["baseline_value"], "90.1")

    def test_builds_claim_grounded_results_without_number_prior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper, story, evidence = _fixture(root)
            spec_path, report_path = build_experimental_results(
                paper,
                story,
                evidence,
                root / "out",
            )
            spec = read_json(spec_path)
            report = read_json(report_path)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(spec["primary_asset"]["asset_id"], "table-7")
            self.assertEqual(spec["secondary_asset"]["asset_id"], "figure-9")
            self.assertEqual(
                spec["layout_template"],
                "quantitative_plus_qualitative",
            )
            self.assertGreaterEqual(len(spec["key_metrics"]), 2)
            for metric in spec["key_metrics"]:
                self.assertEqual(metric["dataset"], "ClinicDB")
                self.assertEqual(metric["baseline"], "StrongNet")
                self.assertTrue(metric["configuration"])
                self.assertTrue(metric["evaluation_condition"])
                self.assertEqual(metric["source_table_id"], "table-7")
            self.assertTrue(spec["primary_asset"]["table_context"]["complete"])
            self.assertEqual(
                spec["primary_asset"]["crop_strategy"],
                "full_high_resolution_original_table",
            )
            self.assertNotIn("focus_crop", spec["primary_asset"])

    def test_transposed_snr_table_is_complete_and_extractable(self) -> None:
        paper_ir = {
            "paper_id": "fbpconvnet",
            "metadata": {
                "title": "Deep Convolutional Neural Network for Inverse Problems",
            },
            "blocks": [],
            "tables": [],
            "figures": [],
        }
        table = {
            "id": "table-2",
            "asset_type": "table",
            "caption": (
                "Comparison of SNR between reconstruction algorithms for "
                "the biomedical dataset."
            ),
            "html": (
                "<table><tr><th>Metrics\\Methods</th><th>Setting</th>"
                "<th>FBP</th><th>TV</th><th>Proposed</th></tr>"
                "<tr><td>avg. SNR (dB)</td><td>143 views</td>"
                "<td>24.97</td><td>31.92</td><td>36.15</td></tr>"
                "<tr><td>avg. SNR (dB)</td><td>50 views</td>"
                "<td>13.52</td><td>25.20</td><td>28.83</td></tr></table>"
            ),
        }
        paper_ir["tables"] = [table]
        self.assertTrue(_table_context(table, paper_ir)["complete"])
        metrics = extract_key_metrics(
            table,
            {"claim": "The proposed reconstruction improves biomedical CT quality."},
            paper_ir,
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertEqual(len(metrics), 2)
        self.assertEqual({item["metric"] for item in metrics}, {"avg. SNR (dB)"})
        self.assertEqual({item["value"] for item in metrics}, {"36.15", "28.83"})

    def test_blank_method_header_still_forms_comparative_table(self) -> None:
        paper_ir = {
            "paper_id": "red-cnn",
            "metadata": {"title": "Low-Dose CT with RED-CNN"},
            "blocks": [],
            "tables": [],
            "figures": [],
        }
        table = {
            "id": "table-1",
            "asset_type": "table",
            "caption": "Quantitative results on the abdominal image.",
            "html": (
                "<table><tr><th></th><th>PSNR</th><th>RMSE</th><th>SSIM</th></tr>"
                "<tr><td>LDCT</td><td>34.3</td><td>0.019</td><td>0.828</td></tr>"
                "<tr><td>CNN10</td><td>40.1</td><td>0.010</td><td>0.930</td></tr>"
                "<tr><td>RED-CNN</td><td>42.4</td><td>0.007</td><td>0.966</td></tr>"
                "</table>"
            ),
        }
        paper_ir["tables"] = [table]
        self.assertTrue(_table_context(table, paper_ir)["complete"])
        metrics = extract_key_metrics(
            table,
            {"claim": "RED-CNN improves PSNR, RMSE, and SSIM."},
            paper_ir,
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertEqual(len(metrics), 3)
        self.assertEqual(
            {item["metric"] for item in metrics},
            {"PSNR", "RMSE", "SSIM"},
        )

    def test_loss_definition_table_is_not_a_main_result_table(self) -> None:
        paper_ir = {
            "paper_id": "wgan",
            "metadata": {"title": "WGAN for CT Denoising"},
            "blocks": [],
            "tables": [],
            "figures": [],
        }
        table = {
            "id": "table-loss",
            "asset_type": "table",
            "caption": "Summary of trained networks and their loss functions.",
            "html": (
                "<table><tr><th>Network</th><th>Loss</th></tr>"
                "<tr><td>CNN-MSE</td><td>MSE loss</td></tr>"
                "<tr><td>WGAN-MSE</td><td>WGAN plus MSE loss</td></tr>"
                "</table>"
            ),
        }
        self.assertFalse(_table_context(table, paper_ir)["complete"])

    def test_configuration_count_is_not_extracted_as_metric(self) -> None:
        figure = {
            "id": "figure-12",
            "asset_type": "figure",
            "caption": (
                "Four slices were reconstructed; the method reports PSNR "
                "38.97 on the matched test set."
            ),
            "context_before": "",
            "context_after": "",
        }
        metrics = extract_key_metrics(
            figure,
            {
                "claim": (
                    "Four slices were reconstructed and the method reports "
                    "PSNR 38.97 on the matched test set."
                )
            },
            {"metadata": {"title": "Reconstruction Network"}},
            {"experimental_design": {"summary": ""}},
            ["b-results"],
        )
        self.assertEqual([item["value"] for item in metrics], ["38.97"])
        self.assertEqual(metrics[0]["metric"], "PSNR")

    def test_layout_changes_with_supporting_evidence_type(self) -> None:
        primary = {"result_type": "performance"}
        self.assertEqual(
            _layout(primary, {"result_type": "ablation"}),
            "main_plus_ablation",
        )
        self.assertEqual(
            _layout({"result_type": "theory"}, {"result_type": "generalization"}),
            "finding_plus_generalization",
        )
        self.assertEqual(
            _layout(primary, {"result_type": "qualitative"}),
            "quantitative_plus_qualitative",
        )

    def test_qa_rejects_mixed_settings_and_qualitative_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper, story, evidence = _fixture(root)
            spec_path, _ = build_experimental_results(
                paper,
                story,
                evidence,
                root / "out",
            )
            spec = read_json(spec_path)
            spec["key_metrics"][1]["dataset"] = "DifferentDB"
            issues = validate_experimental_results_spec(
                spec,
                read_json(paper),
                read_json(evidence),
            )
            self.assertIn(
                "RESULT_MIXED_EVALUATION_CONTEXT",
                {issue["code"] for issue in issues},
            )
            spec["key_metrics"] = []
            issues = validate_experimental_results_spec(
                spec,
                read_json(paper),
                read_json(evidence),
            )
            self.assertIn(
                "RESULT_QUALITATIVE_WITHOUT_QUANTITATIVE",
                {issue["code"] for issue in issues},
            )

    def test_qa_allows_explicit_single_metric_table_split(self) -> None:
        spec = {
            "schema_version": "1.0.0",
            "paper_id": "pnpnet",
            "result_headline": "PnPNet improves Dice across LA/LAA regions.",
            "layout_template": "quantitative_plus_qualitative",
            "key_metrics": [
                {
                    "value": "84.51",
                    "metric": "Dice",
                    "direction": "higher_is_better",
                    "baseline": "nnUNet",
                    "dataset": "LAA",
                    "configuration": "paper-reported configuration",
                    "evaluation_condition": "LAA column",
                    "source_block_ids": ["b-results"],
                    "source_table_id": "table-4",
                    "verification": "exact_table_cell_match",
                },
                {
                    "value": "95.73",
                    "metric": "Dice",
                    "direction": "higher_is_better",
                    "baseline": "MedNeXt",
                    "dataset": "LA",
                    "configuration": "paper-reported configuration",
                    "evaluation_condition": "LA column",
                    "source_block_ids": ["b-results"],
                    "source_table_id": "table-4",
                    "verification": "exact_table_cell_match",
                },
                {
                    "value": "90.12",
                    "metric": "Dice",
                    "direction": "higher_is_better",
                    "baseline": "MedNeXt",
                    "dataset": "LA/LAA",
                    "configuration": "paper-reported configuration",
                    "evaluation_condition": "Mean column",
                    "source_block_ids": ["b-results"],
                    "source_table_id": "table-4",
                    "verification": "exact_table_cell_match",
                },
            ],
            "primary_asset": {
                "asset_id": "table-4",
                "asset_type": "table",
                "result_type": "performance",
                "source_block_ids": ["b-results"],
            },
            "secondary_asset": None,
            "condition_note": "",
            "source_claim_ids": ["claim-main"],
            "source_block_ids": ["b-results"],
            "visible_word_count": 20,
            "confidence": 0.8,
        }
        paper_ir = {
            "blocks": [{"id": "b-results", "text": "Dice results."}],
            "tables": [
                {
                    "id": "table-4",
                    "html": (
                        "<table><tr><td>Ours</td><td>84.51</td>"
                        "<td>95.73</td><td>90.12</td></tr></table>"
                    ),
                    "caption": "LA/LAA Dice results.",
                }
            ],
            "figures": [],
        }
        issues = validate_experimental_results_spec(
            spec,
            paper_ir,
            {"claims": [{"claim_id": "claim-main"}]},
        )
        self.assertNotIn(
            "RESULT_MIXED_EVALUATION_CONTEXT",
            {issue["code"] for issue in issues},
        )

    def test_renderer_preserves_original_assets_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper, story, evidence = _fixture(root)
            spec_path, _ = build_experimental_results(
                paper,
                story,
                evidence,
                root / "out",
            )
            paper_ir = read_json(paper)
            catalog = {
                asset["id"]: asset
                for group in ("tables", "figures")
                for asset in paper_ir[group]
            }
            rendered = _experimental_results_content(
                read_json(spec_path),
                catalog,
                root,
                root / "render",
            )
            self.assertIn('data-results-layout="quantitative_plus_qualitative"', rendered)
            self.assertIn('data-result-asset-id="table-7"', rendered)
            self.assertIn('data-result-asset-id="figure-9"', rendered)
            self.assertNotIn("<svg", rendered)


if __name__ == "__main__":
    unittest.main()
