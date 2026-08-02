from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paperposter.common import read_json, write_json
from paperposter.deliverables import export_deliverables


class DeliverablesTests(unittest.TestCase):
    def test_export_deliverables_copies_human_facing_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="deliverables-") as temp:
            root = Path(temp)
            run = root / "run"
            poster = run / "04-poster"
            report = run / "06-reading-report"
            qa = run / "05-reports"
            poster.mkdir(parents=True)
            report.mkdir(parents=True)
            qa.mkdir(parents=True)

            for path, content in {
                poster / "poster.html": "<html>poster</html>",
                poster / "poster.png": "png",
                poster / "poster.pdf": "pdf",
                report / "reading_report.html": "<html>report</html>",
                report / "reading_report.md": "# Report",
                report / "reading_report.pdf": "pdf",
                qa / "final_qa_report.json": "{}",
                report / "reading_report_qa.json": "{}",
            }.items():
                path.write_text(content, encoding="utf-8")

            reading_spec = {
                "metadata": {
                    "title": "Example Paper",
                    "authors": ["A. Author"],
                },
                "executive_summary": "The paper solves a concrete problem.",
                "storyline": [
                    {
                        "label": "Motivation",
                        "summary": "The task is difficult.",
                        "sources": [{"page": 1}],
                    }
                ],
            }
            poster_spec = {
                "header": {"title": "Example Paper"},
                "panels": {
                    "motivation": [
                        {"visible_text": "The task is difficult."}
                    ],
                    "method_overview": {
                        "summary": {
                            "text": "The method uses a compact pipeline."
                        }
                    },
                    "experimental_results": {
                        "headline": "The method improves the main metric.",
                        "key_metrics": [
                            {
                                "value": "91.2",
                                "metric": "Dice",
                                "dataset": "TestDB",
                                "baseline": "UNet",
                            }
                        ],
                    },
                },
            }
            reading_spec_path = write_json(
                report / "reading_report_spec.json",
                reading_spec,
            )
            poster_spec_path = write_json(poster / "poster_spec.json", poster_spec)
            summary_path = write_json(
                run / "pipeline_summary.json",
                {
                    "status": "passed",
                    "delivery_status": "passed",
                    "output_dir": str(run),
                    "poster_html": str(poster / "poster.html"),
                    "poster_png": str(poster / "poster.png"),
                    "poster_pdf": str(poster / "poster.pdf"),
                    "qa_report": str(qa / "final_qa_report.json"),
                    "reading_report_html": str(report / "reading_report.html"),
                    "reading_report_markdown": str(report / "reading_report.md"),
                    "reading_report_pdf": str(report / "reading_report.pdf"),
                    "reading_report_qa": str(report / "reading_report_qa.json"),
                    "reading_report_spec": str(reading_spec_path),
                    "poster_spec": str(poster_spec_path),
                },
            )

            deliverables = export_deliverables(summary_path)

            self.assertTrue((deliverables / "README.md").is_file())
            self.assertTrue((deliverables / "poster" / "poster.png").is_file())
            self.assertTrue(
                (deliverables / "reading-report" / "reading_report.md").is_file()
            )
            notes = (deliverables / "notes" / "reading-notes.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Example Paper", notes)
            self.assertIn("The method uses a compact pipeline.", notes)
            manifest = read_json(deliverables / "manifest.json")
            self.assertEqual(manifest["delivery_status"], "passed")
            self.assertIn("poster/poster.png", manifest["files"])


if __name__ == "__main__":
    unittest.main()
