from __future__ import annotations

import argparse
from pathlib import Path
from shutil import copy2
from typing import Any

from .common import normalize_text, read_json, write_json


DELIVERABLE_DIRNAME = "00-final-deliverables"


def _path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_file() else None


def _copy_file(
    source: Path | None,
    target_dir: Path,
    target_name: str | None = None,
) -> dict[str, Any] | None:
    if not source:
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (target_name or source.name)
    copy2(source, target)
    return {
        "name": target.name,
        "path": str(target),
        "source": str(source),
    }


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _link(label: str, path: Path | None, root: Path) -> str:
    if not path or not path.exists():
        return f"- {label}: not available"
    return f"- {label}: [{path.name}]({_rel(path, root)})"


def _text(value: Any) -> str:
    return normalize_text(str(value or ""))


def _panel_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "summary", "visible_text", "headline", "takeaway"):
            child = value.get(key)
            text = _panel_text(child) if isinstance(child, (dict, list)) else _text(child)
            if text:
                return text
        for child in value.values():
            text = _panel_text(child) if isinstance(child, (dict, list)) else ""
            if text:
                return text
        return ""
    if isinstance(value, list):
        for item in value:
            text = _panel_text(item)
            if text:
                return text
        return ""
    return _text(value)


def _source_pages(sources: list[dict[str, Any]]) -> str:
    pages = sorted(
        {
            int(source.get("page") or 0)
            for source in sources
            if int(source.get("page") or 0) > 0
        }
    )
    if not pages:
        return ""
    return "p." + ", ".join(str(page) for page in pages[:5])


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if item]


def _storyline_notes(reading_report: dict[str, Any]) -> list[str]:
    lines = ["## Paper Logic", ""]
    for item in reading_report.get("storyline", []):
        label = _text(item.get("label") or item.get("role"))
        summary = _text(item.get("summary"))
        if not label or not summary:
            continue
        pages = _source_pages(list(item.get("sources") or []))
        suffix = f" ({pages})" if pages else ""
        lines.append(f"### {label}{suffix}")
        lines.append(summary)
        lines.append("")
    return lines


def _poster_notes(poster_spec: dict[str, Any]) -> list[str]:
    panels = poster_spec.get("panels") or {}
    lines = ["## Poster Modules", ""]

    motivation = panels.get("motivation") or []
    if motivation:
        lines.extend(["### Motivation", ""])
        lines.extend(
            _bullet_lines(_text(item.get("visible_text")) for item in motivation)
        )
        lines.append("")

    key_idea = panels.get("key_idea") or {}
    if key_idea:
        lines.extend(["### Key Idea", ""])
        for key in ("headline", "takeaway", "plain_language_explanation"):
            value = _text(key_idea.get(key))
            if value:
                lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        visual = key_idea.get("visual") or {}
        visual_items = visual.get("items") or []
        if visual_items:
            lines.append("- Visual points:")
            for item in visual_items:
                label = _text(item.get("label"))
                text = _text(item.get("text"))
                if label or text:
                    lines.append(f"  - {label}: {text}".rstrip(": "))
        lines.append("")

    overview = panels.get("method_overview") or {}
    detail = panels.get("method_detail") or {}
    if overview or detail:
        lines.extend(["### Method", ""])
        overview_text = _panel_text(overview)
        if overview_text:
            lines.append(f"- Overview: {overview_text}")
        detail_text = _panel_text(detail.get("method", {}))
        if detail_text:
            lines.append(f"- Detail: {detail_text}")
        experiment_text = _panel_text(detail.get("experimental_design", {}))
        if experiment_text:
            lines.append(f"- Experimental Design: {experiment_text}")
        flow_items = overview.get("flow_items") or []
        if flow_items:
            lines.append("- Method flow:")
            for item in flow_items:
                label = _text(item.get("label"))
                text = _text(item.get("text"))
                if label or text:
                    lines.append(f"  - {label}: {text}".rstrip(": "))
        lines.append("")

    results = panels.get("experimental_results") or {}
    if results:
        lines.extend(["### Experimental Results", ""])
        headline = _text(results.get("headline") or results.get("result_headline"))
        if headline:
            lines.append(f"- Headline: {headline}")
        metrics = results.get("key_metrics") or []
        if metrics:
            lines.append("- Key metrics:")
            for metric in metrics:
                value = _text(metric.get("value"))
                name = _text(metric.get("metric"))
                dataset = _text(metric.get("dataset"))
                baseline = _text(metric.get("baseline"))
                parts = [part for part in [value, name, dataset] if part]
                line = " ".join(parts)
                if baseline:
                    line += f" vs. {baseline}"
                if line:
                    lines.append(f"  - {line}")
        lines.append("")

    contributions = panels.get("contributions") or []
    if contributions:
        lines.extend(["### Contributions", ""])
        for item in contributions:
            visible = _text(item.get("visible_text"))
            title = _text(item.get("short_title") or item.get("title"))
            description = _text(item.get("description"))
            line = visible or " - ".join(
                part for part in [title, description] if part
            )
            if line:
                lines.append(f"- {line}")
        lines.append("")

    limitations = panels.get("limitations") or {}
    limitation_text = _text(
        limitations.get("text") if isinstance(limitations, dict) else limitations
    )
    if limitation_text:
        lines.extend(["### Limitations", "", f"- {limitation_text}", ""])

    return lines


def _write_notes(
    output_dir: Path,
    summary: dict[str, Any],
    reading_report: dict[str, Any],
    poster_spec: dict[str, Any],
) -> Path:
    metadata = reading_report.get("metadata") or {}
    title = _text(metadata.get("title")) or _text(
        (poster_spec.get("header") or {}).get("title")
    )
    authors = [
        _text(author)
        for author in metadata.get("authors", [])
        if _text(author)
    ]
    lines = [
        "# Reading Notes",
        "",
        f"- Title: {title or 'Unknown'}",
        f"- Status: {_text(summary.get('status'))}",
        f"- Delivery: {_text(summary.get('delivery_status'))}",
    ]
    if authors:
        lines.append(f"- Authors: {', '.join(authors)}")
    lines.append("")
    executive_summary = _text(reading_report.get("executive_summary"))
    if executive_summary:
        lines.extend(["## Executive Summary", "", executive_summary, ""])
    lines.extend(_storyline_notes(reading_report))
    if poster_spec:
        lines.extend(_poster_notes(poster_spec))
    output_dir.mkdir(parents=True, exist_ok=True)
    notes_path = output_dir / "reading-notes.md"
    notes_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return notes_path


def _write_readme(
    output_dir: Path,
    summary: dict[str, Any],
    copied: dict[str, dict[str, Any] | None],
) -> Path:
    title = "Paper Reading Deliverables"
    report_spec = _path(summary.get("reading_report_spec"))
    if report_spec:
        metadata = read_json(report_spec).get("metadata") or {}
        title = _text(metadata.get("title")) or title
    lines = [
        f"# {title}",
        "",
        "This folder contains the final, human-facing outputs copied from the full pipeline run.",
        "The original run directory is preserved separately for debugging and provenance.",
        "",
        "## Open First",
        "",
        _link("Reading notes", output_dir / "notes" / "reading-notes.md", output_dir),
        _link(
            "Reading report HTML",
            output_dir / "reading-report" / "reading_report.html",
            output_dir,
        ),
        _link("Poster PNG", output_dir / "poster" / "poster.png", output_dir),
        _link("Poster PDF", output_dir / "poster" / "poster.pdf", output_dir),
        _link("Poster HTML", output_dir / "poster" / "poster.html", output_dir),
        "",
        "## Status",
        "",
        f"- Pipeline status: {_text(summary.get('status'))}",
        f"- Delivery status: {_text(summary.get('delivery_status'))}",
        f"- Full run directory: `{_text(summary.get('output_dir'))}`",
        "",
        "## Contents",
        "",
        "- `reading-report/`: navigable HTML, Markdown notes, and PDF report when available.",
        "- `poster/`: final poster image, PDF, and HTML. If the run was blocked, debug poster files are kept with `debug-` names.",
        "- `notes/`: compact section-by-section reading notes generated from validated artifacts.",
        "- `qa/`: final QA reports and a copy of the pipeline summary.",
        "",
    ]
    manifest = copied.get("manifest")
    if manifest:
        lines.extend(["## Manifest", "", _link("manifest.json", Path(manifest["path"]), output_dir), ""])
    readme_path = output_dir / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    return readme_path


def export_deliverables(
    summary_path: Path,
    output_dir: Path | None = None,
) -> Path:
    summary_path = summary_path.resolve()
    summary = read_json(summary_path)
    run_dir = Path(str(summary.get("output_dir") or summary_path.parent)).resolve()
    output_dir = (output_dir or run_dir / DELIVERABLE_DIRNAME).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_summary": str(summary_path),
        "run_dir": str(run_dir),
        "status": summary.get("status"),
        "delivery_status": summary.get("delivery_status"),
        "files": {},
    }

    poster_dir = output_dir / "poster"
    reading_dir = output_dir / "reading-report"
    notes_dir = output_dir / "notes"
    qa_dir = output_dir / "qa"

    poster_sources = {
        "poster.html": _path(summary.get("poster_html")),
        "poster.png": _path(summary.get("poster_png")),
        "poster.pdf": _path(summary.get("poster_pdf")),
    }
    if not any(poster_sources.values()):
        poster_sources = {
            "debug-poster.html": _path(summary.get("poster_debug_html")),
            "debug-poster.png": _path(summary.get("poster_debug_png")),
            "debug-poster.pdf": _path(summary.get("poster_debug_pdf")),
        }
    for name, source in poster_sources.items():
        manifest["files"][f"poster/{name}"] = _copy_file(
            source,
            poster_dir,
            name,
        )

    reading_sources = {
        "reading_report.html": _path(summary.get("reading_report_html")),
        "reading_report.md": _path(summary.get("reading_report_markdown")),
        "reading_report.pdf": _path(summary.get("reading_report_pdf")),
    }
    for name, source in reading_sources.items():
        manifest["files"][f"reading-report/{name}"] = _copy_file(
            source,
            reading_dir,
            name,
        )

    qa_sources = {
        "final_qa_report.json": _path(summary.get("qa_report")),
        "reading_report_qa.json": _path(summary.get("reading_report_qa")),
        "pipeline_summary.json": summary_path,
    }
    for name, source in qa_sources.items():
        manifest["files"][f"qa/{name}"] = _copy_file(source, qa_dir, name)

    reading_report = (
        read_json(path)
        if (path := _path(summary.get("reading_report_spec")))
        else {}
    )
    poster_spec = (
        read_json(path) if (path := _path(summary.get("poster_spec"))) else {}
    )
    notes_path = _write_notes(notes_dir, summary, reading_report, poster_spec)
    manifest["files"]["notes/reading-notes.md"] = {
        "name": notes_path.name,
        "path": str(notes_path),
        "source": "generated",
    }
    manifest_path = write_json(output_dir / "manifest.json", manifest)
    manifest["files"]["manifest.json"] = {
        "name": manifest_path.name,
        "path": str(manifest_path),
        "source": "generated",
    }
    write_json(manifest_path, manifest)
    _write_readme(output_dir, summary, {"manifest": manifest["files"]["manifest.json"]})
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy final paper-reader artifacts into a clean deliverables folder."
    )
    parser.add_argument(
        "--summary",
        required=True,
        type=Path,
        help="Path to pipeline_summary.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit deliverables directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = export_deliverables(args.summary, args.output)
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
