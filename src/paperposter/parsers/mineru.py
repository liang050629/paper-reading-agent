"""MinerU cloud-client adapter and content-list to PaperIR conversion.

The official ``mineru-open-api`` client uploads documents to MinerU's cloud
service and writes Markdown, images, and the stable flat content list locally.
This module invokes that lightweight client and converts the content list into
the PaperIR contract used downstream.  No MinerU model runtime is installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..common import compact_text, sha256_file, slugify, write_json

_SUPPORTED_EXECUTABLE_SUFFIXES = {"", ".exe", ".cmd", ".bat"}
_SUPPORTED_ASSET_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}
_AUXILIARY_TYPES = {
    "aside_text",
    "footer",
    "header",
    "page_footnote",
    "page_number",
}
_FIGURE_NUMBER_RE = re.compile(r"\b(?:figure|fig\.?)\s*([a-z]?\d+)\b", re.I)
_TABLE_NUMBER_RE = re.compile(r"\btable\s*([a-z]?\d+)\b", re.I)
_VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?(?:[-+._a-z0-9]*)?)\b", re.I)
_URL_RE = re.compile(r"https?://[^\s<>{}\[\]\"']+", re.I)
_CODE_URL_RE = re.compile(
    r"^https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|"
    r"huggingface\.co)/",
    re.I,
)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_ARXIV_RE = re.compile(r"\barXiv\s*:\s*(\d{4}\.\d{4,5})(?:v\d+)?\b", re.I)


class MinerUAdapterError(RuntimeError):
    """Raised when strict MinerU ingestion cannot produce trustworthy PaperIR."""

    def __init__(self, message: str, report: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.report = dict(report or {})


def _is_supported_executable(path: Path) -> bool:
    if not path.is_file():
        return False
    if os.name != "nt":
        return os.access(path, os.X_OK)
    return path.suffix.lower() in _SUPPORTED_EXECUTABLE_SUFFIXES


def _resolve_executable(value: str | os.PathLike[str]) -> Path | None:
    raw = os.fspath(value).strip().strip('"')
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate.resolve() if _is_supported_executable(candidate) else None
    located = shutil.which(raw)
    if not located:
        return None
    path = Path(located)
    return path.resolve() if _is_supported_executable(path) else None


def discover_mineru_executable(
    project_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Find the official MinerU cloud CLI.

    Discovery order is:

    1. ``PAPERPOSTER_MINERU_CLI``;
    2. the project-private npm wrapper in ``.tools``;
    3. ``mineru-open-api`` on ``PATH``;
    4. the npm global wrapper in ``APPDATA`` on Windows.
    """

    environment = os.environ if environ is None else environ
    configured = environment.get("PAPERPOSTER_MINERU_CLI")
    if configured:
        resolved = _resolve_executable(configured)
        if resolved:
            return resolved
        raise FileNotFoundError(
            "PAPERPOSTER_MINERU_CLI does not point to a usable "
            f"mineru-open-api executable: {configured}"
        )

    root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    private_bin = root / ".tools" / "node_modules" / ".bin"
    private_names = (
        ("mineru-open-api.cmd", "mineru-open-api.exe")
        if os.name == "nt"
        else ("mineru-open-api",)
    )
    for name in private_names:
        candidate = private_bin / name
        if _is_supported_executable(candidate):
            return candidate.resolve()

    located = _resolve_executable("mineru-open-api")
    if located:
        return located

    if os.name == "nt":
        appdata = environment.get("APPDATA")
        if appdata:
            for name in ("mineru-open-api.cmd", "mineru-open-api.exe"):
                candidate = Path(appdata) / "npm" / name
                if _is_supported_executable(candidate):
                    return candidate.resolve()

    raise FileNotFoundError(
        "The MinerU cloud client was not found. Install the official client "
        "with 'npm install -g mineru-open-api' or set PAPERPOSTER_MINERU_CLI."
    )


def _command_prefix(executable: Path) -> list[str]:
    suffix = executable.suffix.lower()
    if os.name == "nt" and suffix in {".cmd", ".bat"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", str(executable)]
    return [str(executable)]


def _run_command(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    merged_environment = None
    if environment is not None:
        merged_environment = os.environ.copy()
        merged_environment.update(environment)
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
        timeout=timeout,
        env=merged_environment,
        creationflags=creation_flags,
    )


def _mineru_version(executable: Path) -> tuple[str | None, str | None]:
    try:
        result = _run_command([*_command_prefix(executable), "version"], timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"MinerU version detection failed: {error}"
    output = compact_text(f"{result.stdout}\n{result.stderr}", 500)
    match = _VERSION_RE.search(output)
    if result.returncode == 0 and match:
        return match.group(1), None
    return None, f"MinerU cloud client version could not be determined from: {output or 'empty output'}"


def find_content_list(
    raw_output_dir: Path,
    *,
    paper_stem: str | None = None,
    strict: bool = True,
) -> Path:
    """Locate a flat MinerU content list from local or cloud-client output."""

    root = raw_output_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"MinerU raw output directory does not exist: {root}")
    legacy_candidates = [
        path
        for path in root.rglob("*_content_list.json")
        if path.is_file() and not path.name.lower().endswith("_content_list_v2.json")
    ]
    cloud_candidates: list[Path] = []
    if paper_stem:
        exact_cloud = root / f"{paper_stem}.json"
        if exact_cloud.is_file():
            cloud_candidates.append(exact_cloud)
    candidates = [*legacy_candidates, *cloud_candidates]
    if not candidates:
        raise FileNotFoundError(
            "MinerU did not produce a usable content-list JSON file "
            f"under {root}."
        )

    expected = f"{paper_stem}_content_list.json".lower() if paper_stem else None
    expected_cloud = f"{paper_stem}.json".lower() if paper_stem else None

    def score(path: Path) -> tuple[int, int, int]:
        parts = {part.lower() for part in path.parts}
        return (
            int(
                (expected is not None and path.name.lower() == expected)
                or (
                    expected_cloud is not None
                    and path.name.lower() == expected_cloud
                )
            ),
            int("auto" in parts or "pipeline" in parts),
            -len(path.relative_to(root).parts),
        )

    ranked = sorted(candidates, key=lambda path: (score(path), path.as_posix()), reverse=True)
    best_score = score(ranked[0])
    equally_ranked = [path for path in ranked if score(path) == best_score]
    if strict and len(equally_ranked) > 1:
        paths = ", ".join(str(path) for path in equally_ranked)
        raise MinerUAdapterError(f"Multiple equally plausible MinerU content lists found: {paths}")
    return ranked[0]


def _read_content_list(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise MinerUAdapterError(f"Cannot read MinerU content list {path}: {error}") from error
    if not isinstance(value, list):
        raise MinerUAdapterError("MinerU legacy content list must be a top-level JSON array.")
    if not all(isinstance(item, dict) for item in value):
        raise MinerUAdapterError("Every MinerU content-list item must be a JSON object.")
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return compact_text(value, 20_000)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return compact_text(" ".join(_text(item) for item in value), 20_000)
    if isinstance(value, dict):
        for key in ("content", "text"):
            if key in value:
                return _text(value[key])
        return compact_text(" ".join(_text(item) for item in value.values()), 20_000)
    return compact_text(str(value), 20_000)


def _structured_text(value: Any) -> str:
    """Preserve complete HTML/Markdown bodies rather than truncating them."""

    if isinstance(value, str):
        return value.strip()
    return _text(value)


def _item_text(item: Mapping[str, Any]) -> str:
    for key in ("text", "content", "title_content"):
        text = _text(item.get(key))
        if text:
            return text
    return ""


def _caption(item: Mapping[str, Any], kind: str) -> str:
    keys = {
        "image": ("image_caption", "caption"),
        "chart": ("chart_caption", "image_caption", "caption"),
        "table": ("table_caption", "caption"),
    }[kind]
    for key in keys:
        text = _text(item.get(key))
        if text:
            return compact_text(text, 900)
    return ""


def _page(item: Mapping[str, Any], warnings: list[str], index: int) -> int:
    value = item.get("page_idx")
    try:
        page_index = int(value)
    except (TypeError, ValueError):
        warnings.append(f"Item {index} has no valid page_idx; page 1 was used.")
        return 1
    if page_index < 0:
        warnings.append(f"Item {index} has a negative page_idx; page 1 was used.")
        return 1
    return page_index + 1


def _bbox(item: Mapping[str, Any], warnings: list[str], index: int) -> list[float] | None:
    value = item.get("bbox")
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(not isinstance(coordinate, (int, float)) for coordinate in value)
    ):
        warnings.append(f"Item {index} has an invalid bbox; it was discarded.")
        return None
    return [float(coordinate) for coordinate in value]


def _strip_math_delimiters(value: str) -> str:
    text = value.strip()
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        text = text[2:-2].strip()
    elif text.startswith(r"\[") and text.endswith(r"\]"):
        text = text[2:-2].strip()
    return text


def _safe_source_asset(
    path_value: Any,
    *,
    content_list_dir: Path,
    raw_output_dir: Path,
) -> tuple[Path | None, str | None]:
    if not path_value:
        return None, None
    raw_path = str(path_value).strip()
    if not raw_path or "://" in raw_path:
        return None, f"Unsupported MinerU asset path: {raw_path or '<empty>'}"
    candidate = Path(raw_path.replace("/", os.sep))
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (content_list_dir / candidate).resolve()
    allowed_root = raw_output_dir.resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        return None, f"MinerU asset escaped the raw output directory: {raw_path}"
    if not resolved.is_file():
        return None, f"MinerU asset was not found: {raw_path}"
    if resolved.suffix.lower() not in _SUPPORTED_ASSET_SUFFIXES:
        return None, f"MinerU asset has an unsupported file type: {raw_path}"
    return resolved, None


def _copy_asset(
    item: Mapping[str, Any],
    *,
    asset_id: str,
    content_list_dir: Path,
    raw_output_dir: Path,
    output_dir: Path,
) -> tuple[str | None, str | None]:
    source, problem = _safe_source_asset(
        item.get("img_path") or item.get("image_path"),
        content_list_dir=content_list_dir,
        raw_output_dir=raw_output_dir,
    )
    if not source:
        return None, problem
    asset_dir = output_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    target = asset_dir / f"{asset_id}{source.suffix.lower()}"
    if source != target.resolve():
        shutil.copy2(source, target)
    return target.relative_to(output_dir).as_posix(), None


def _render_page_crop(
    source_pdf: Path,
    *,
    page: int,
    bbox: Sequence[float],
    asset_id: str,
    output_dir: Path,
    render_scale: float = 4.4,
) -> tuple[str | None, str | None, str | None]:
    """Render a MinerU bbox from the source PDF into a local PNG.

    Legacy pipeline content lists use coordinates normalized to 0..1000.
    Some VLM-derived legacy files have used 0..1, so that coordinate space is
    also accepted when every coordinate is at most 1.
    """

    try:
        import pypdfium2
    except ImportError:
        return None, "pypdfium2 is unavailable; the bbox crop is pending.", None

    if len(bbox) != 4 or any(not isinstance(value, (int, float)) for value in bbox):
        return None, "The MinerU bbox is invalid; the bbox crop is pending.", None
    coordinates = [float(value) for value in bbox]
    if any(value < 0 for value in coordinates):
        return None, "The MinerU bbox contains negative coordinates.", None
    coordinate_max = 1.0 if max(coordinates, default=0.0) <= 1.0 else 1000.0
    coordinate_space = "mineru-0-1" if coordinate_max == 1.0 else "mineru-0-1000"
    if any(value > coordinate_max for value in coordinates):
        return None, f"The MinerU bbox is outside {coordinate_space}.", coordinate_space
    if coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]:
        return None, "The MinerU bbox has no positive area.", coordinate_space

    document: Any | None = None
    pdf_page: Any | None = None
    rendered: Any | None = None
    crop: Any | None = None
    try:
        document = pypdfium2.PdfDocument(str(source_pdf))
        page_index = page - 1
        if page_index < 0 or page_index >= len(document):
            return None, f"Page {page} is outside the source PDF.", coordinate_space
        pdf_page = document[page_index]
        # Equation bboxes are often narrow. A high-resolution page render
        # keeps their screenshot fallback readable after poster enlargement.
        rendered = pdf_page.render(scale=max(1.0, float(render_scale))).to_pil()
        left = max(0, min(rendered.width, round(coordinates[0] / coordinate_max * rendered.width)))
        top = max(0, min(rendered.height, round(coordinates[1] / coordinate_max * rendered.height)))
        right = max(0, min(rendered.width, round(coordinates[2] / coordinate_max * rendered.width)))
        bottom = max(0, min(rendered.height, round(coordinates[3] / coordinate_max * rendered.height)))
        if right - left < 2 or bottom - top < 2:
            return None, "The mapped MinerU bbox is too small to crop.", coordinate_space
        crop = rendered.crop((left, top, right, bottom))
        asset_dir = output_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        target = asset_dir / f"{asset_id}.png"
        crop.save(target, format="PNG")
        return target.relative_to(output_dir).as_posix(), None, coordinate_space
    except Exception as error:
        return None, f"PDF bbox crop failed: {error}", coordinate_space
    finally:
        if crop is not None:
            crop.close()
        if rendered is not None:
            rendered.close()
        if pdf_page is not None:
            pdf_page.close()
        if document is not None:
            document.close()


def _unique_asset_id(
    prefix: str,
    number: str | None,
    counters: dict[str, int],
    used_ids: set[str],
) -> str:
    if number:
        base = f"{prefix}-{number.lower()}"
    else:
        counters[prefix] = counters.get(prefix, 0) + 1
        base = f"{prefix}-{counters[prefix]}"
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _middle_file_version(content_list_path: Path) -> str | None:
    candidates = sorted(content_list_path.parent.glob("*_middle.json"))
    for candidate in candidates:
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("_version_name"):
            return str(value["_version_name"])
    return None


def _metadata_from_blocks(
    title: str,
    blocks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    full_text = "\n".join(str(block.get("text") or "") for block in blocks)
    front_text = "\n".join(
        str(block.get("text") or "")
        for block in blocks
        if int(block.get("page") or 1) <= 2
    )
    urls = [match.group(0).rstrip(".,;)") for match in _URL_RE.finditer(full_text)]
    code_url = next((url for url in urls if _CODE_URL_RE.match(url)), None)
    paper_url = next((url for url in urls if "doi.org/" in url.lower()), None)
    if not paper_url:
        doi_match = _DOI_RE.search(front_text)
        if doi_match:
            paper_url = f"https://doi.org/{doi_match.group(0).rstrip('.,;)')}"
    if not paper_url:
        paper_url = next((url for url in urls if "arxiv.org/" in url.lower()), None)
    if not paper_url:
        arxiv_match = _ARXIV_RE.search(front_text)
        if arxiv_match:
            paper_url = f"https://arxiv.org/abs/{arxiv_match.group(1)}"
    year_match = re.search(r"\b(?:19|20)\d{2}\b", front_text)

    authors: list[str] = []
    for block in blocks:
        if block.get("section_id") != "front-matter" or block.get("type") == "title":
            continue
        candidate = compact_text(str(block.get("text") or ""), 500)
        lower = candidate.lower()
        if (
            not candidate
            or len(candidate) > 350
            or any(
                marker in lower
                for marker in (
                    "abstract",
                    "index terms",
                    "keywords",
                    "key words",
                    "department",
                    "institute",
                    "laboratory",
                    "university",
                    "http://",
                    "https://",
                    "@",
                )
            )
            or ("," not in candidate and " and " not in lower)
        ):
            continue
        cleaned = re.sub(r"(?<=[A-Za-z])\d+(?:,\d+)*[*†‡]?", "", candidate)
        cleaned = re.sub(r"\band\b", ",", cleaned, flags=re.I)
        parts = [part.strip(" ,;*†‡") for part in cleaned.split(",")]
        plausible = [
            part
            for part in parts
            if 2 <= len(re.findall(r"[A-Za-z][A-Za-z.'-]*", part)) <= 5
            and not re.search(r"\d|=", part)
            and part.lower()
            not in {
                "ieee",
                "member",
                "senior member",
                "fellow",
                "corresponding author",
            }
        ]
        suffixes = sum(
            part.lower()
            in {
                "ieee",
                "member",
                "senior member",
                "fellow",
                "corresponding author",
            }
            for part in parts
        )
        if len(plausible) >= 2 and len(plausible) >= max(
            2,
            len(parts) - 1 - suffixes,
        ):
            authors = plausible
            break

    return {
        "title": title,
        "authors": authors,
        "affiliations": [],
        "year": int(year_match.group(0)) if year_match else None,
        "url": paper_url,
        "code_url": code_url,
    }


def _base_report(
    *,
    source_pdf: Path,
    raw_output_dir: Path,
    mineru_version: str | None,
) -> dict[str, Any]:
    return {
        "status": "running",
        "parser": "mineru",
        "requested_parser": "mineru",
        "actual_parser": "mineru",
        "transport": "cloud-api",
        "model": None,
        "mineru_version": mineru_version,
        "source_path": str(source_pdf.resolve()),
        "raw_output_path": str(raw_output_dir.resolve()),
        "content_list_path": None,
        "pages": 0,
        "blocks": 0,
        "figures": 0,
        "equations": 0,
        "tables": 0,
        "copied_assets": 0,
        "warnings": [],
        "errors": [],
        "exception": None,
    }


def _write_report(output_dir: Path, report: Mapping[str, Any]) -> None:
    write_json(output_dir / "parse_report.json", dict(report))


def _fail(
    message: str,
    *,
    output_dir: Path,
    report: dict[str, Any],
    error: BaseException | None = None,
) -> None:
    exception = error or MinerUAdapterError(message)
    report["status"] = "failed"
    report["errors"].append(message)
    report["exception"] = {
        "type": type(exception).__name__,
        "message": str(exception),
    }
    _write_report(output_dir, report)
    raise MinerUAdapterError(message, report) from error


def convert_content_list(
    content_list_path: Path,
    source_pdf: Path,
    output_dir: Path,
    *,
    raw_output_dir: Path | None = None,
    mineru_version: str | None = None,
    strict: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert a legacy MinerU content list to PaperIR and copy safe assets."""

    output_dir.mkdir(parents=True, exist_ok=True)
    content_list_path = content_list_path.resolve()
    source_pdf = source_pdf.resolve()
    raw_root = (raw_output_dir or content_list_path.parent).resolve()
    report = _base_report(
        source_pdf=source_pdf,
        raw_output_dir=raw_root,
        mineru_version=mineru_version or _middle_file_version(content_list_path),
    )
    report["content_list_path"] = str(content_list_path)
    if not source_pdf.is_file():
        _fail(
            f"Input PDF does not exist: {source_pdf}",
            output_dir=output_dir,
            report=report,
            error=FileNotFoundError(source_pdf),
        )
    try:
        items = _read_content_list(content_list_path)
    except MinerUAdapterError as error:
        _fail(str(error), output_dir=output_dir, report=report, error=error)

    blocks: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    equations: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    assets_in_order: list[dict[str, Any]] = []
    warnings: list[str] = report["warnings"]
    asset_errors: list[str] = []
    used_ids: set[str] = set()
    counters: dict[str, int] = {}
    title = ""
    current_section = "front-matter"
    current_section_title = "Front matter"

    for item_index, item in enumerate(items):
        kind = str(item.get("type") or "").strip().lower()
        if kind in _AUXILIARY_TYPES:
            continue
        page = _page(item, warnings, item_index)
        bbox = _bbox(item, warnings, item_index)

        if kind in {"text", "title"}:
            text = _item_text(item)
            if not text:
                warnings.append(f"Empty {kind} item {item_index} was ignored.")
                continue
            text_level_value = item.get("text_level", 1 if kind == "title" else 0)
            try:
                text_level = int(text_level_value or 0)
            except (TypeError, ValueError):
                text_level = 0
                warnings.append(f"Item {item_index} has an invalid text_level.")
            is_heading = kind == "title" or text_level > 0
            if is_heading and not title:
                title = text
                block_type = "title"
                section_id = "front-matter"
                section_title = "Front matter"
            elif is_heading:
                current_section = slugify(text)
                current_section_title = text
                block_type = "heading"
                section_id = current_section
                section_title = current_section_title
            else:
                block_type = "abstract" if current_section == "abstract" else "paragraph"
                section_id = current_section
                section_title = current_section_title
            blocks.append(
                {
                    "id": f"p{page}-b{len(blocks) + 1}",
                    "type": block_type,
                    "text": text,
                    "page": page,
                    "section_id": section_id,
                    "section_title": section_title,
                    "bbox": bbox,
                    "source_item_index": item_index,
                    "source_parser": "mineru",
                    "source_type": kind,
                }
            )
            continue

        if kind == "equation":
            latex = _strip_math_delimiters(_item_text(item))
            equation_id = _unique_asset_id("equation", None, counters, used_ids)
            path, asset_problem = _copy_asset(
                item,
                asset_id=equation_id,
                content_list_dir=content_list_path.parent,
                raw_output_dir=raw_root,
                output_dir=output_dir,
            )
            crop_problem = None
            coordinate_space = None
            extraction_mode = "mineru-content-list"
            if not path and bbox:
                path, crop_problem, coordinate_space = _render_page_crop(
                    source_pdf,
                    page=page,
                    bbox=bbox,
                    asset_id=equation_id,
                    output_dir=output_dir,
                )
                if path:
                    extraction_mode = "mineru-page-crop-fallback"
            if asset_problem:
                if bbox or latex:
                    warnings.append(f"{equation_id}: {asset_problem}")
                else:
                    asset_errors.append(f"{equation_id}: {asset_problem}")
            if crop_problem:
                warnings.append(f"{equation_id}: {crop_problem}")
            if not path and not latex and not bbox and not asset_problem:
                asset_errors.append(f"{equation_id}: no LaTeX, image, or bbox was provided.")
            equation = {
                "id": equation_id,
                "asset_type": "equation",
                "caption": compact_text(str(item.get("caption") or "Extracted equation"), 900),
                "page": page,
                "section_id": current_section,
                "path": path,
                "latex": latex or None,
                "bbox": bbox,
                "context_before": "",
                "context_after": "",
                "cited_by": [],
                "extraction_mode": extraction_mode,
                "source_item_index": item_index,
                "source_parser": "mineru",
                "source_type": kind,
                "crop_pending": bool(bbox and not path),
                "provenance": {
                    "source_parser": "mineru",
                    "source_type": kind,
                    "bbox_coordinate_space": coordinate_space,
                },
            }
            equations.append(equation)
            assets_in_order.append(equation)
            blocks.append(
                {
                    "id": f"p{page}-b{len(blocks) + 1}",
                    "type": "equation",
                    "text": latex,
                    "page": page,
                    "section_id": current_section,
                    "section_title": current_section_title,
                    "bbox": bbox,
                    "source_item_index": item_index,
                    "source_parser": "mineru",
                    "source_type": kind,
                }
            )
            continue

        if kind in {"image", "chart", "table"}:
            caption = _caption(item, kind)
            if kind == "table":
                number_match = _TABLE_NUMBER_RE.search(caption)
                prefix = "table"
                collection = tables
                asset_type = "table"
            else:
                number_match = _FIGURE_NUMBER_RE.search(caption)
                prefix = "figure"
                collection = figures
                asset_type = "figure"
            asset_id = _unique_asset_id(
                prefix,
                number_match.group(1) if number_match else None,
                counters,
                used_ids,
            )
            path, asset_problem = _copy_asset(
                item,
                asset_id=asset_id,
                content_list_dir=content_list_path.parent,
                raw_output_dir=raw_root,
                output_dir=output_dir,
            )
            crop_problem = None
            coordinate_space = None
            extraction_mode = f"mineru-{kind}"
            if not path and bbox:
                path, crop_problem, coordinate_space = _render_page_crop(
                    source_pdf,
                    page=page,
                    bbox=bbox,
                    asset_id=asset_id,
                    output_dir=output_dir,
                )
                if path:
                    extraction_mode = "mineru-page-crop-fallback"
            structured_content = _structured_text(
                item.get("table_body") if kind == "table" else item.get("content")
            )
            if asset_problem:
                if bbox or structured_content:
                    warnings.append(f"{asset_id}: {asset_problem}")
                else:
                    asset_errors.append(f"{asset_id}: {asset_problem}")
            if crop_problem:
                warnings.append(f"{asset_id}: {crop_problem}")
            if not path and not structured_content and not bbox and not asset_problem:
                asset_errors.append(f"{asset_id}: no image or structured content was provided.")
            asset = {
                "id": asset_id,
                "asset_type": asset_type,
                "caption": caption,
                "page": page,
                "section_id": current_section,
                "path": path,
                "latex": None,
                "bbox": bbox,
                "context_before": "",
                "context_after": "",
                "cited_by": [],
                "extraction_mode": extraction_mode,
                "source_item_index": item_index,
                "source_parser": "mineru",
                "source_type": kind,
                "crop_pending": bool(bbox and not path),
                "provenance": {
                    "source_parser": "mineru",
                    "source_type": kind,
                    "bbox_coordinate_space": coordinate_space,
                },
            }
            if kind == "table":
                asset["html"] = structured_content or None
                asset["footnote"] = _text(item.get("table_footnote"))
            elif kind == "chart":
                asset["chart_content"] = structured_content or None
                asset["footnote"] = _text(item.get("chart_footnote"))
            else:
                asset["footnote"] = _text(item.get("image_footnote"))
            collection.append(asset)
            assets_in_order.append(asset)
            if caption:
                blocks.append(
                    {
                        "id": f"p{page}-b{len(blocks) + 1}",
                        "type": "table" if kind == "table" else "caption",
                        "text": caption,
                        "page": page,
                        "section_id": current_section,
                        "section_title": current_section_title,
                        "bbox": bbox,
                        "source_item_index": item_index,
                        "source_parser": "mineru",
                        "source_type": f"{kind}_caption",
                    }
                )
            continue

        warnings.append(f"Unsupported MinerU item type {kind or '<empty>'!r} at index {item_index}.")

    if not title:
        title = source_pdf.stem
        warnings.append("No document title was identified; the PDF filename was used.")

    text_blocks = [
        block
        for block in blocks
        if block["type"] in {"title", "abstract", "heading", "paragraph"}
    ]
    for asset in assets_in_order:
        item_index = int(asset["source_item_index"])
        same_page = [block for block in text_blocks if block["page"] == asset["page"]]
        before = [block for block in same_page if int(block["source_item_index"]) < item_index]
        after = [block for block in same_page if int(block["source_item_index"]) > item_index]
        asset["context_before"] = compact_text(before[-1]["text"] if before else "", 500)
        asset["context_after"] = compact_text(after[0]["text"] if after else "", 500)
        if asset["asset_type"] == "figure":
            number = str(asset["id"]).split("-", 1)[1].split("-", 1)[0]
            reference = re.compile(rf"\b(?:figure|fig\.?)\s*{re.escape(number)}\b", re.I)
        elif asset["asset_type"] == "table":
            number = str(asset["id"]).split("-", 1)[1].split("-", 1)[0]
            reference = re.compile(rf"\btable\s*{re.escape(number)}\b", re.I)
        else:
            reference = None
        if reference:
            asset["cited_by"] = [
                block["id"]
                for block in text_blocks
                if reference.search(str(block.get("text") or ""))
            ][:8]

    report["pages"] = max(
        [int(block["page"]) for block in blocks]
        + [int(asset["page"]) for asset in assets_in_order],
        default=0,
    )
    report["blocks"] = len(blocks)
    report["figures"] = len(figures)
    report["equations"] = len(equations)
    report["tables"] = len(tables)
    report["copied_assets"] = sum(
        bool(asset.get("path")) for asset in figures + equations + tables
    )
    if not text_blocks:
        asset_errors.append("MinerU produced no usable text or title blocks.")
    if asset_errors:
        report["errors"].extend(asset_errors)
        if strict:
            _fail(
                "Strict MinerU conversion failed: " + "; ".join(asset_errors),
                output_dir=output_dir,
                report=report,
            )
        warnings.extend(asset_errors)
        report["errors"] = []

    paper_ir = {
        "schema_version": "1.0.0",
        "paper_id": slugify(title),
        "metadata": _metadata_from_blocks(title, blocks),
        "blocks": blocks,
        "figures": figures,
        "equations": equations,
        "tables": tables,
        "provenance": {
            "source_path": str(source_pdf.resolve()),
            "source_sha256": sha256_file(source_pdf),
            "parser": "mineru",
            "mineru_version": report["mineru_version"],
            "content_list_path": str(content_list_path),
        },
    }
    report["status"] = "passed_with_warnings" if warnings else "passed"
    _write_report(output_dir, report)
    return paper_ir, report


def run_mineru(
    source_pdf: Path,
    raw_output_dir: Path,
    *,
    executable: Path | str | None = None,
    backend: str = "vlm",
    language: str | None = None,
    timeout: float | None = None,
    environment: Mapping[str, str] | None = None,
    strict: bool = True,
) -> tuple[Path, Path, str | None, dict[str, Any]]:
    """Run the official MinerU cloud client and locate its content list."""

    source_pdf = source_pdf.resolve()
    if not source_pdf.is_file():
        raise FileNotFoundError(f"Input PDF does not exist: {source_pdf}")
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    if executable is None:
        executable_path = discover_mineru_executable()
    else:
        executable_path = _resolve_executable(executable)
        if not executable_path:
            raise FileNotFoundError(f"MinerU executable is not usable: {executable}")
    version, version_warning = _mineru_version(executable_path)
    cli_timeout = max(1, int(timeout or 900))
    command = [
        *_command_prefix(executable_path),
        "extract",
        str(source_pdf),
        "-o",
        str(raw_output_dir.resolve()),
        "-f",
        "md,json",
        "--model",
        backend,
        "--timeout",
        str(cli_timeout),
    ]
    if language:
        command.extend(["-l", language])
    diagnostics = {
        "command": command,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "mineru_version": version,
        "executable": str(executable_path),
        "version_warning": version_warning,
        "transport": "cloud-api",
        "model": backend,
    }
    try:
        result = _run_command(
            command,
            timeout=cli_timeout + 60,
            environment=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        diagnostics["stderr"] = str(error)
        raise MinerUAdapterError(f"MinerU could not be executed: {error}", diagnostics) from error
    diagnostics["returncode"] = result.returncode
    diagnostics["stdout"] = compact_text(result.stdout, 4_000)
    diagnostics["stderr"] = compact_text(result.stderr, 4_000)
    if result.returncode != 0:
        raise MinerUAdapterError(
            f"MinerU exited with code {result.returncode}: "
            f"{compact_text(result.stderr or result.stdout, 1_000)}",
            diagnostics,
        )
    try:
        content_list = find_content_list(
            raw_output_dir,
            paper_stem=source_pdf.stem,
            strict=strict,
        )
    except (FileNotFoundError, MinerUAdapterError) as error:
        raise MinerUAdapterError(str(error), diagnostics) from error
    return content_list, executable_path, version, diagnostics


def ingest_with_mineru(
    source_pdf: Path,
    output_dir: Path,
    *,
    executable: Path | str | None = None,
    backend: str = "vlm",
    language: str | None = None,
    timeout: float | None = None,
    environment: Mapping[str, str] | None = None,
    strict: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run MinerU cloud extraction and emit PaperIR plus parse diagnostics."""

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_output_dir = output_dir / "mineru_raw"
    report = _base_report(
        source_pdf=source_pdf,
        raw_output_dir=raw_output_dir,
        mineru_version=None,
    )
    try:
        content_list, executable_path, version, diagnostics = run_mineru(
            source_pdf,
            raw_output_dir,
            executable=executable,
            backend=backend,
            language=language,
            timeout=timeout,
            environment=environment,
            strict=strict,
        )
    except Exception as error:
        if isinstance(error, MinerUAdapterError) and error.report:
            report["command"] = error.report.get("command")
            report["returncode"] = error.report.get("returncode")
            report["stdout"] = error.report.get("stdout")
            report["stderr"] = error.report.get("stderr")
            report["mineru_version"] = error.report.get("mineru_version")
            report["executable"] = error.report.get("executable")
            report["transport"] = error.report.get("transport", "cloud-api")
            report["model"] = error.report.get("model", backend)
        if isinstance(error, FileNotFoundError) and (
            "was not found" in str(error)
            or "executable is not usable" in str(error)
            or "PAPERPOSTER_MINERU_CLI" in str(error)
            or "Input PDF does not exist" in str(error)
        ):
            report["actual_parser"] = None
        _fail(str(error), output_dir=output_dir, report=report, error=error)

    paper_ir, converted_report = convert_content_list(
        content_list,
        source_pdf,
        output_dir,
        raw_output_dir=raw_output_dir,
        mineru_version=version,
        strict=strict,
    )
    converted_report["executable"] = str(executable_path)
    converted_report["command"] = diagnostics["command"]
    converted_report["returncode"] = diagnostics["returncode"]
    converted_report["stdout"] = diagnostics["stdout"]
    converted_report["stderr"] = diagnostics["stderr"]
    converted_report["transport"] = diagnostics["transport"]
    converted_report["model"] = diagnostics["model"]
    if diagnostics["version_warning"]:
        converted_report["warnings"].append(diagnostics["version_warning"])
        if converted_report["status"] == "passed":
            converted_report["status"] = "passed_with_warnings"
    _write_report(output_dir, converted_report)
    return paper_ir, converted_report
