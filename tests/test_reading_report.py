from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paperposter.common import read_json, write_json
from paperposter.pipeline import run_pipeline
from paperposter.reading_report import validate_reading_report


class ReadingReportTests(unittest.TestCase):
    def test_poster_pipeline_generates_sourced_reading_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reading-report-") as temp:
            output = Path(temp) / "run"
            summary = run_pipeline(
                PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                output,
                mode="poster",
                export_browser=False,
            )
            self.assertEqual(summary["status"], "passed")
            for key in (
                "reading_report_spec",
                "reading_report_source_index",
                "reading_report_html",
                "reading_report_markdown",
                "reading_report_qa",
            ):
                self.assertTrue(Path(summary[key]).is_file(), key)

            report = read_json(Path(summary["reading_report_spec"]))
            source_ids = {
                source["block_id"] for source in report["source_index"]
            }
            self.assertTrue(report["storyline"])
            self.assertTrue(report["method_modules"])
            self.assertTrue(report["claim_evidence"])
            self.assertTrue(report["poster_coverage"])
            for section in (
                "motivations",
                "contributions",
                "method_modules",
            ):
                for item in report[section]:
                    self.assertTrue(item["sources"], (section, item))
                    self.assertTrue(
                        all(source["block_id"] in source_ids for source in item["sources"])
                    )
            for formula in report["formulas"]:
                self.assertTrue(formula["page"])
                self.assertTrue(formula["image_path"] or formula["latex"])

            html_text = Path(summary["reading_report_html"]).read_text(encoding="utf-8")
            markdown_text = Path(summary["reading_report_markdown"]).read_text(
                encoding="utf-8"
            )
            self.assertIn("Paper Storyline", html_text)
            self.assertIn("Formula Notebook", html_text)
            self.assertIn("Claim–Evidence Matrix", html_text)
            self.assertIn("Source Index", html_text)
            self.assertNotIn("raw_statement", html_text)
            self.assertIn("## Claim–Evidence Matrix", markdown_text)

    def test_report_qa_rejects_unsourced_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reading-report-qa-") as temp:
            root = Path(temp)
            report_path = write_json(
                root / "reading_report_spec.json",
                {
                    "schema_version": "1.0.0",
                    "paper_id": "paper",
                    "metadata": {},
                    "executive_summary": "",
                    "storyline": [
                        {
                            "id": "story-research-problem",
                            "role": "research_problem",
                            "summary": "An asserted problem.",
                            "sources": [],
                        }
                    ],
                    "motivations": [],
                    "contributions": [],
                    "method_modules": [],
                    "formulas": [],
                    "experimental_design": {},
                    "experimental_results": {},
                    "claim_evidence": [],
                    "limitations": {},
                    "poster_coverage": [],
                    "source_index": [],
                },
            )
            html_path = root / "reading_report.html"
            markdown_path = root / "reading_report.md"
            html_path.write_text("<html></html>", encoding="utf-8")
            markdown_path.write_text("# report\n", encoding="utf-8")
            bundle_path = write_json(
                root / "reading_report_render_bundle.json",
                {
                    "html_path": str(html_path),
                    "markdown_path": str(markdown_path),
                    "pdf_requested": False,
                    "pdf_path": None,
                    "metrics_path": None,
                },
            )
            qa_path = validate_reading_report(report_path, bundle_path, root)
            qa = read_json(qa_path)
            self.assertEqual(qa["status"], "failed")
            self.assertIn(
                "REPORT_SOURCE_MISSING",
                {issue["code"] for issue in qa["issues"]},
            )
            self.assertEqual(qa["return_to"], "paper-reading-report-compose")

    def test_only_inferred_story_nodes_are_labeled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="reading-report-inferred-") as temp:
            output = Path(temp) / "run"
            summary = run_pipeline(
                PROJECT_ROOT / "examples" / "sample-paper-ir.json",
                output,
                mode="poster",
                export_browser=False,
            )
            report = read_json(Path(summary["reading_report_spec"]))
            for item in report["storyline"]:
                self.assertEqual(
                    item["inferred"],
                    item["status"] == "inferred",
                )


if __name__ == "__main__":
    unittest.main()
