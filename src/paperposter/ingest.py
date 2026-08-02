from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .common import read_json, sha256_file, write_json
from .parsers import ingest_with_mineru


def _ensure_paper_ir(value: dict[str, Any], source_path: Path) -> dict[str, Any]:
    required = {
        "schema_version",
        "paper_id",
        "metadata",
        "blocks",
        "figures",
        "equations",
        "tables",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"PaperIR is missing required fields: {', '.join(missing)}")
    value.setdefault("provenance", {})
    value["provenance"].setdefault("source_path", str(source_path.resolve()))
    value["provenance"].setdefault("source_sha256", sha256_file(source_path))
    return value


def _copy_json_assets(
    paper_ir: dict[str, Any],
    source_path: Path,
    output_dir: Path,
) -> None:
    target_dir = output_dir / "assets"
    for group in ("figures", "equations", "tables"):
        for asset in paper_ir.get(group, []):
            path_value = asset.get("path")
            if not path_value:
                continue
            source = Path(str(path_value))
            if not source.is_absolute():
                source = source_path.parent / source
            if not source.is_file():
                asset["path"] = None
                asset.setdefault("warnings", []).append(
                    "Referenced source asset was not found."
                )
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{asset['id']}{source.suffix.lower()}"
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            asset["path"] = target.relative_to(output_dir).as_posix()


def ingest(
    input_path: Path,
    output_dir: Path,
    parser: str = "mineru",
) -> tuple[Path, Path]:
    input_path = input_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_path.is_file():
        raise FileNotFoundError(input_path)

    if input_path.suffix.lower() == ".json":
        paper_ir = _ensure_paper_ir(read_json(input_path), input_path)
        _copy_json_assets(paper_ir, input_path, output_dir)
        report = {
            "status": "passed",
            "parser": "paper-ir",
            "pages": max(
                (int(block.get("page", 1)) for block in paper_ir["blocks"]),
                default=1,
            ),
            "blocks": len(paper_ir["blocks"]),
            "figures": len(paper_ir["figures"]),
            "equations": len(paper_ir["equations"]),
            "tables": len(paper_ir["tables"]),
            "warnings": [],
        }
    elif input_path.suffix.lower() == ".pdf":
        if parser != "mineru":
            raise RuntimeError(
                "PDF ingestion is fail-closed and only supports parser='mineru'. "
                "No basic PDF fallback is installed."
            )
        environment = os.environ.copy()
        try:
            timeout = float(
                environment.get("PAPERPOSTER_MINERU_TIMEOUT_SECONDS", "900")
            )
        except ValueError as error:
            raise ValueError(
                "PAPERPOSTER_MINERU_TIMEOUT_SECONDS must be a number."
            ) from error
        model = environment.get("PAPERPOSTER_MINERU_MODEL", "vlm").strip().lower()
        if model not in {"vlm", "pipeline"}:
            raise ValueError(
                "PAPERPOSTER_MINERU_MODEL must be 'vlm' or 'pipeline'."
            )
        language = environment.get("PAPERPOSTER_MINERU_LANGUAGE", "en").strip()
        paper_ir, report = ingest_with_mineru(
            input_path,
            output_dir,
            backend=model,
            language=language or None,
            timeout=timeout,
            environment=environment,
            strict=True,
        )
    else:
        raise ValueError("Input must be a PDF or PaperIR JSON file.")

    ir_path = write_json(output_dir / "paper_ir.json", paper_ir)
    report_path = write_json(output_dir / "parse_report.json", report)
    return ir_path, report_path
