from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from paperposter.common import read_json
from paperposter.parsers.mineru import (
    MinerUAdapterError,
    _mineru_version,
    _run_command,
    convert_content_list,
    discover_mineru_executable,
    find_content_list,
    ingest_with_mineru,
)


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class MinerUDiscoveryTests(unittest.TestCase):
    def test_environment_setting_has_priority(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-discovery-") as temp:
            executable = Path(temp) / "mineru-open-api.exe"
            executable.write_bytes(b"")
            found = discover_mineru_executable(
                Path(temp) / "project",
                {"PAPERPOSTER_MINERU_CLI": str(executable)},
            )
            self.assertEqual(found, executable.resolve())

    def test_windows_npm_wrapper_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-cloud-cli-") as temp:
            root = Path(temp)
            executable = root / "npm" / "mineru-open-api.cmd"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"")
            with patch(
                "paperposter.parsers.mineru._resolve_executable",
                return_value=None,
            ):
                self.assertEqual(
                    discover_mineru_executable(
                        root / "project",
                        {"APPDATA": str(root)},
                    ),
                    executable.resolve(),
                )

    def test_cloud_client_semver_keeps_leading_zero(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["mineru-open-api", "version"],
            returncode=0,
            stdout="mineru-open-api v0.5.9\n",
            stderr="",
        )
        with patch("paperposter.parsers.mineru._run_command", return_value=completed):
            self.assertEqual(
                _mineru_version(Path("mineru-open-api")),
                ("0.5.9", None),
            )


class MinerUConversionTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        pdf = root / "A Paper.pdf"
        pdf.write_bytes(b"%PDF-test")
        raw = root / "raw"
        content_dir = raw / "A Paper" / "auto"
        images = content_dir / "images"
        images.mkdir(parents=True)
        for name in ("overview.png", "chart.jpg", "equation.png", "table.png"):
            (images / name).write_bytes(name.encode("ascii"))
        content = [
            {
                "type": "text",
                "text": "Reliable Networks",
                "text_level": 1,
                "page_idx": 0,
                "bbox": [10, 20, 900, 80],
            },
            {
                "type": "title",
                "text": "1 Introduction",
                "page_idx": 0,
                "bbox": [10, 100, 400, 130],
            },
            {
                "type": "text",
                "text": "Figure 2 presents the complete architecture.",
                "page_idx": 0,
                "bbox": [10, 140, 900, 190],
            },
            {
                "type": "image",
                "img_path": "images/overview.png",
                "image_caption": ["Figure 2: Overall architecture."],
                "page_idx": 0,
                "bbox": [10, 200, 900, 600],
            },
            {
                "type": "chart",
                "img_path": "images/chart.jpg",
                "chart_caption": ["Fig. 3: Accuracy comparison."],
                "content": "|model|score|",
                "page_idx": 1,
                "bbox": [10, 20, 900, 300],
            },
            {
                "type": "equation",
                "img_path": "images/equation.png",
                "text": "$$E = mc^2$$",
                "text_format": "latex",
                "page_idx": 1,
                "bbox": [100, 320, 800, 390],
            },
            {
                "type": "table",
                "img_path": "images/table.png",
                "table_caption": ["Table 1: Main results."],
                "table_body": "<table><tr><td>98.1</td></tr></table>",
                "page_idx": 2,
                "bbox": [10, 20, 900, 500],
            },
            {
                "type": "header",
                "text": "Journal header",
                "page_idx": 2,
                "bbox": [0, 0, 1000, 20],
            },
        ]
        content_list = _write_json(
            content_dir / "A Paper_content_list.json",
            content,
        )
        _write_json(
            content_dir / "A Paper_middle.json",
            {"_version_name": "2.6.0"},
        )
        return pdf, raw, content_list

    def test_legacy_content_list_is_selected_and_v2_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-content-") as temp:
            root = Path(temp)
            expected = _write_json(
                root / "paper" / "auto" / "paper_content_list.json",
                [],
            )
            _write_json(
                root / "paper" / "auto" / "paper_content_list_v2.json",
                [[{"type": "paragraph"}]],
            )
            self.assertEqual(
                find_content_list(root, paper_stem="paper"),
                expected,
            )

    def test_maps_core_types_and_safely_copies_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-convert-") as temp:
            root = Path(temp)
            pdf, raw, content_list = self._fixture(root)
            paper_ir, report = convert_content_list(
                content_list,
                pdf,
                root / "output",
                raw_output_dir=raw,
            )
            self.assertEqual(paper_ir["metadata"]["title"], "Reliable Networks")
            self.assertEqual(paper_ir["blocks"][1]["type"], "heading")
            self.assertEqual(paper_ir["blocks"][2]["section_id"], "1-introduction")
            self.assertEqual(
                [item["id"] for item in paper_ir["figures"]],
                ["figure-2", "figure-3"],
            )
            self.assertEqual(paper_ir["figures"][1]["source_type"], "chart")
            self.assertTrue(
                all(
                    block["source_parser"] == "mineru" and block["source_type"]
                    for block in paper_ir["blocks"]
                )
            )
            self.assertTrue(
                all(
                    asset["source_parser"] == "mineru" and asset["source_type"]
                    for group in ("figures", "equations", "tables")
                    for asset in paper_ir[group]
                )
            )
            self.assertEqual(paper_ir["equations"][0]["latex"], "E = mc^2")
            self.assertEqual(
                paper_ir["tables"][0]["html"],
                "<table><tr><td>98.1</td></tr></table>",
            )
            self.assertEqual(paper_ir["figures"][0]["cited_by"], ["p1-b3"])
            self.assertTrue(
                (root / "output" / paper_ir["figures"][0]["path"]).is_file()
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["mineru_version"], "2.6.0")
            self.assertEqual(report["pages"], 3)
            self.assertEqual(report["copied_assets"], 4)
            self.assertEqual(report["requested_parser"], "mineru")
            self.assertEqual(report["actual_parser"], "mineru")
            self.assertIsNone(report["exception"])

    def test_metadata_recovers_code_url_year_and_conservative_authors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-metadata-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            raw = root / "raw"
            content_list = _write_json(
                raw / "paper" / "auto" / "paper_content_list.json",
                [
                    {"type": "title", "text": "Paper Title", "page_idx": 0},
                    {
                        "type": "text",
                        "text": (
                            "Alice Researcher1, Bob Scientist2, and Carol Writer3, "
                            "Member, IEEE"
                        ),
                        "page_idx": 0,
                    },
                    {
                        "type": "text",
                        "text": "Index Terms—Mixture-of-Experts, Efficient Training Method.",
                        "page_idx": 0,
                    },
                    {
                        "type": "text",
                        "text": (
                            "Published in 2025. Code: "
                            "https://github.com/example/paper."
                        ),
                        "page_idx": 0,
                    },
                ],
            )
            paper_ir, _ = convert_content_list(
                content_list,
                pdf,
                root / "output",
                raw_output_dir=raw,
            )
            metadata = paper_ir["metadata"]
            self.assertEqual(
                metadata["authors"],
                ["Alice Researcher", "Bob Scientist", "Carol Writer"],
            )
            self.assertEqual(metadata["year"], 2025)
            self.assertEqual(metadata["code_url"], "https://github.com/example/paper")

    def test_strict_mode_rejects_asset_path_traversal_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-unsafe-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            raw = root / "raw"
            content_dir = raw / "paper" / "auto"
            outside = root / "secret.png"
            outside.write_bytes(b"secret")
            content_list = _write_json(
                content_dir / "paper_content_list.json",
                [
                    {"type": "title", "text": "Paper", "page_idx": 0},
                    {
                        "type": "image",
                        "img_path": "../../../secret.png",
                        "image_caption": ["Figure 1: Unsafe."],
                        "page_idx": 0,
                    },
                ],
            )
            output = root / "output"
            with self.assertRaises(MinerUAdapterError) as caught:
                convert_content_list(
                    content_list,
                    pdf,
                    output,
                    raw_output_dir=raw,
                    strict=True,
                )
            self.assertEqual(caught.exception.report["status"], "failed")
            report = read_json(output / "parse_report.json")
            self.assertEqual(report["requested_parser"], "mineru")
            self.assertEqual(report["actual_parser"], "mineru")
            self.assertEqual(report["exception"]["type"], "MinerUAdapterError")
            self.assertIn("escaped", " ".join(report["errors"]))
            self.assertFalse((output / "assets" / "figure-1.png").exists())

    def test_non_strict_mode_keeps_missing_asset_as_warning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-nonstrict-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            raw = root / "raw"
            content_list = _write_json(
                raw / "paper" / "auto" / "paper_content_list.json",
                [
                    {"type": "title", "text": "Paper", "page_idx": 0},
                    {
                        "type": "image",
                        "img_path": "images/missing.png",
                        "image_caption": ["Figure 1: Missing."],
                        "page_idx": 0,
                    },
                ],
            )
            paper_ir, report = convert_content_list(
                content_list,
                pdf,
                root / "output",
                raw_output_dir=raw,
                strict=False,
            )
            self.assertIsNone(paper_ir["figures"][0]["path"])
            self.assertEqual(report["status"], "passed_with_warnings")
            self.assertFalse(report["errors"])
            self.assertTrue(any("not found" in warning for warning in report["warnings"]))

    def test_missing_image_with_bbox_uses_source_pdf_page_crop(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory(prefix="mineru-crop-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=100)
            with pdf.open("wb") as handle:
                writer.write(handle)
            raw = root / "raw"
            content_list = _write_json(
                raw / "paper" / "auto" / "paper_content_list.json",
                [
                    {"type": "title", "text": "Paper", "page_idx": 0},
                    {
                        "type": "image",
                        "image_caption": ["Figure 1: Overview."],
                        "page_idx": 0,
                        "bbox": [100, 100, 900, 900],
                    },
                ],
            )
            paper_ir, report = convert_content_list(
                content_list,
                pdf,
                root / "output",
                raw_output_dir=raw,
                strict=True,
            )
            figure = paper_ir["figures"][0]
            self.assertEqual(figure["extraction_mode"], "mineru-page-crop-fallback")
            self.assertFalse(figure["crop_pending"])
            self.assertEqual(
                figure["provenance"]["bbox_coordinate_space"],
                "mineru-0-1000",
            )
            self.assertTrue((root / "output" / figure["path"]).is_file())
            self.assertEqual(report["status"], "passed")

    def test_bbox_crop_failure_is_explicitly_pending_not_falsely_successful(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-crop-pending-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            raw = root / "raw"
            content_list = _write_json(
                raw / "paper" / "auto" / "paper_content_list.json",
                [
                    {"type": "title", "text": "Paper", "page_idx": 0},
                    {
                        "type": "image",
                        "image_caption": ["Figure 1: Overview."],
                        "page_idx": 0,
                        "bbox": [100, 100, 900, 900],
                    },
                ],
            )
            with patch(
                "paperposter.parsers.mineru._render_page_crop",
                return_value=(None, "renderer unavailable", "mineru-0-1000"),
            ):
                paper_ir, report = convert_content_list(
                    content_list,
                    pdf,
                    root / "output",
                    raw_output_dir=raw,
                    strict=True,
                )
            figure = paper_ir["figures"][0]
            self.assertIsNone(figure["path"])
            self.assertTrue(figure["crop_pending"])
            self.assertNotEqual(figure["extraction_mode"], "mineru-page-crop-fallback")
            self.assertEqual(report["status"], "passed_with_warnings")
            self.assertTrue(any("renderer unavailable" in item for item in report["warnings"]))


class MinerURunTests(unittest.TestCase):
    def test_command_environment_overrides_without_erasing_system_environment(self) -> None:
        completed = subprocess.CompletedProcess(["mineru"], 0, "", "")
        with patch("paperposter.parsers.mineru.subprocess.run", return_value=completed) as run:
            _run_command(
                ["mineru-open-api", "version"],
                environment={"MINERU_TOKEN": "test-only-token"},
            )
        invoked_environment = run.call_args.kwargs["env"]
        self.assertEqual(invoked_environment["MINERU_TOKEN"], "test-only-token")
        for key in ("PATH", "SystemRoot"):
            if key in os.environ:
                copied_key = next(
                    candidate
                    for candidate in invoked_environment
                    if candidate.lower() == key.lower()
                )
                self.assertEqual(invoked_environment[copied_key], os.environ[key])

    def test_ingestion_uses_argument_array_and_records_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mineru-run-") as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-test")
            executable = root / "mineru-open-api.exe"
            executable.write_bytes(b"")
            output = root / "output"

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                raw = Path(command[command.index("-o") + 1])
                _write_json(
                    raw / "paper.json",
                    [{"type": "title", "text": "Paper", "page_idx": 0}],
                )
                return subprocess.CompletedProcess(command, 0, "parsed", "")

            with (
                patch("paperposter.parsers.mineru._mineru_version", return_value=("2.6.0", None)),
                patch("paperposter.parsers.mineru._run_command", side_effect=fake_run) as run,
            ):
                paper_ir, report = ingest_with_mineru(
                    pdf,
                    output,
                    executable=executable,
                )

            command = run.call_args.args[0]
            self.assertIsInstance(command, list)
            self.assertEqual(command[0], str(executable.resolve()))
            self.assertEqual(command[1], "extract")
            self.assertEqual(command[2], str(pdf.resolve()))
            self.assertEqual(command[command.index("-f") + 1], "md,json")
            self.assertEqual(command[command.index("--model") + 1], "vlm")
            self.assertNotIn("-l", command)
            self.assertEqual(paper_ir["metadata"]["title"], "Paper")
            self.assertEqual(report["mineru_version"], "2.6.0")
            self.assertEqual(report["transport"], "cloud-api")
            self.assertEqual(report["model"], "vlm")
            self.assertEqual(report["returncode"], 0)
            self.assertEqual(report["raw_output_path"], str((output / "mineru_raw").resolve()))
            self.assertEqual(read_json(output / "parse_report.json")["status"], "passed")


if __name__ == "__main__":
    unittest.main()
