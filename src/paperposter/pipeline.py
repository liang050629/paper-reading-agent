from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .assets import select_assets
from .common import read_json, write_json
from .compose import compose_poster
from .deliverables import export_deliverables
from .evidence import audit_evidence
from .experimental_results import build_experimental_results
from .highlights import build_highlights
from .ingest import ingest
from .key_idea import build_key_idea
from .method_figures import map_method_figures
from .method_graph import build_method_graph
from .method_visual import compose_method_visual
from .motivation_contributions import build_motivation_contributions
from .qa import validate_poster
from .reading_report import build_reading_report
from .render import finalize_render_bundle, render_poster
from .storyline import extract_story


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    parser: str = "mineru",
    mode: str = "analysis",
    export_browser: bool = True,
    max_validation_cycles: int = 3,
) -> dict[str, Any]:
    if mode not in {"analysis", "poster"}:
        raise ValueError("mode must be 'analysis' or 'poster'")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ingestion_dir = output_dir / "01-ingestion"
    analysis_dir = output_dir / "02-analysis"
    asset_dir = output_dir / "03-assets"
    poster_dir = output_dir / "04-poster"
    report_dir = output_dir / "05-reports"
    reading_report_dir = output_dir / "06-reading-report"

    paper_ir_path, parse_report_path = ingest(input_path, ingestion_dir, parser)
    story_path, storyline_report_path = extract_story(paper_ir_path, analysis_dir)
    method_graph_path, method_graph_report_path = build_method_graph(
        paper_ir_path,
        analysis_dir,
    )
    evidence_path, evidence_report_path = audit_evidence(
        paper_ir_path,
        story_path,
        analysis_dir,
    )

    core_report_paths = [
        parse_report_path,
        storyline_report_path,
        method_graph_report_path,
        evidence_report_path,
    ]
    if mode == "analysis":
        statuses = [str(read_json(path).get("status") or "") for path in core_report_paths]
        if any(status in {"failed", "blocked"} for status in statuses):
            status = "failed"
        elif any(status == "passed_with_warnings" for status in statuses):
            status = "passed_with_warnings"
        else:
            status = "passed"
        summary = {
            "schema_version": "1.0.0",
            "status": status,
            "mode": "analysis",
            "input": str(input_path.resolve()),
            "output_dir": str(output_dir),
            "paper_ir": str(paper_ir_path.resolve()),
            "paper_story": str(story_path.resolve()),
            "claim_evidence": str(evidence_path.resolve()),
            "method_graph": str(method_graph_path.resolve()),
            "stage_reports": [str(path.resolve()) for path in core_report_paths],
        }
        write_json(output_dir / "pipeline_summary.json", summary)
        return summary

    catalog_path, selected_path, asset_report_path = select_assets(
        paper_ir_path,
        evidence_path,
        asset_dir,
    )
    method_figure_map_path, method_figure_map_report_path = map_method_figures(
        paper_ir_path,
        method_graph_path,
        catalog_path,
        asset_dir,
    )
    method_visual_plan_path, method_visual_report_path = compose_method_visual(
        paper_ir_path,
        method_graph_path,
        method_figure_map_path,
        poster_dir,
    )
    key_idea_spec_path, key_idea_report_path = build_key_idea(
        paper_ir_path,
        story_path,
        evidence_path,
        method_graph_path,
        method_figure_map_path,
        poster_dir,
    )
    experimental_results_spec_path, experimental_results_report_path = (
        build_experimental_results(
            paper_ir_path,
            story_path,
            evidence_path,
            poster_dir,
        )
    )
    highlights_spec_path, highlights_report_path = build_highlights(
        paper_ir_path,
        story_path,
        evidence_path,
        experimental_results_spec_path,
        poster_dir,
    )
    (
        motivation_spec_path,
        contribution_spec_path,
        motivation_contribution_audit_path,
        motivation_contribution_preview_path,
    ) = build_motivation_contributions(
        paper_ir_path,
        story_path,
        evidence_path,
        method_graph_path,
        poster_dir,
    )
    contribution_candidates_path = poster_dir / "contribution_candidates.json"
    contribution_audit_path = poster_dir / "contribution_audit.json"
    motivation_audit_path = poster_dir / "motivation_audit.json"

    highlights_report = read_json(highlights_report_path)
    if str(highlights_report.get("status") or "") == "failed":
        highlight_blockers = [
            issue
            for issue in highlights_report.get("issues", [])
            if issue.get("severity") == "error"
        ]
        summary = {
            "schema_version": "1.0.0",
            "status": "failed",
            "mode": "poster",
            "input": str(input_path.resolve()),
            "output_dir": str(output_dir),
            "paper_ir": str(paper_ir_path.resolve()),
            "paper_story": str(story_path.resolve()),
            "claim_evidence": str(evidence_path.resolve()),
            "experimental_results_spec": str(
                experimental_results_spec_path.resolve()
            ),
            "highlights_spec": str(highlights_spec_path.resolve()),
            "highlights_report": str(highlights_report_path.resolve()),
            "compose_blockers": highlight_blockers,
            "return_to": "paper-highlights",
            "stage_reports": [
                str(parse_report_path.resolve()),
                str(storyline_report_path.resolve()),
                str(evidence_report_path.resolve()),
                str(experimental_results_report_path.resolve()),
                str(highlights_report_path.resolve()),
            ],
        }
        write_json(output_dir / "pipeline_summary.json", summary)
        return summary

    # Motivation is a required visible Poster panel.  Do not let Compose turn
    # a semantically selected but non-displayable set of candidates into an
    # empty panel.  Contributions keep their existing independent audit path.
    motivation_audit = read_json(motivation_audit_path)
    motivation_items = list(read_json(motivation_spec_path).get("items") or [])
    motivation_blockers = list(motivation_audit.get("compose_blockers") or [])
    motivation_blockers.extend(
        blocker
        for blocker in motivation_audit.get("selected_item_blockers", [])
        if str(blocker.get("code") or "")
        in {
            "MOTIVATION_EVIDENCE_INSUFFICIENT",
            "MOTIVATION_COVERAGE_CHECK",
            "MOTIVATION_VISIBLE_TEXT_REWRITE_FAILED",
        }
    )
    if motivation_items:
        motivation_blockers = [
            blocker
            for blocker in motivation_blockers
            if str(blocker.get("code") or "")
            not in {
                "MOTIVATION_EVIDENCE_INSUFFICIENT",
                "MOTIVATION_COVERAGE_CHECK",
            }
        ]
    elif not motivation_blockers:
        motivation_blockers = [
            {
                "code": "MOTIVATION_EVIDENCE_INSUFFICIENT",
                "displayable_item_count": 0,
                "message": (
                    "No traceable, displayable Motivation item survived "
                    "recovery."
                ),
            }
        ]
    motivation_preflight_warnings = [
        {
            **dict(blocker),
            "severity": "warning",
            "delivery_policy": "empty_motivation_panel_allowed",
        }
        for blocker in motivation_blockers
    ]

    def repair_failed_stage(stage: str) -> list[str]:
        nonlocal story_path
        nonlocal storyline_report_path
        nonlocal method_graph_path
        nonlocal method_graph_report_path
        nonlocal evidence_path
        nonlocal evidence_report_path
        nonlocal catalog_path
        nonlocal selected_path
        nonlocal asset_report_path
        nonlocal method_figure_map_path
        nonlocal method_figure_map_report_path
        nonlocal method_visual_plan_path
        nonlocal method_visual_report_path
        nonlocal key_idea_spec_path
        nonlocal key_idea_report_path
        nonlocal experimental_results_spec_path
        nonlocal experimental_results_report_path
        nonlocal highlights_spec_path
        nonlocal highlights_report_path
        nonlocal motivation_spec_path
        nonlocal contribution_spec_path
        nonlocal motivation_contribution_audit_path
        nonlocal motivation_contribution_preview_path

        repaired: list[str] = []

        if stage == "paper-storyline":
            story_path, storyline_report_path = extract_story(
                paper_ir_path,
                analysis_dir,
            )
            repaired.append("paper-storyline")
            evidence_path, evidence_report_path = audit_evidence(
                paper_ir_path,
                story_path,
                analysis_dir,
            )
            repaired.append("paper-evidence-audit")
        elif stage in {"paper-evidence-audit", "paper-claim-evidence"}:
            evidence_path, evidence_report_path = audit_evidence(
                paper_ir_path,
                story_path,
                analysis_dir,
            )
            repaired.append("paper-evidence-audit")
        elif stage == "paper-method-graph":
            method_graph_path, method_graph_report_path = build_method_graph(
                paper_ir_path,
                analysis_dir,
            )
            repaired.append("paper-method-graph")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-asset-select",
        }:
            catalog_path, selected_path, asset_report_path = select_assets(
                paper_ir_path,
                evidence_path,
                asset_dir,
            )
            repaired.append("paper-asset-select")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-asset-select",
            "paper-method-graph",
            "paper-method-figure-map",
        }:
            (
                method_figure_map_path,
                method_figure_map_report_path,
            ) = map_method_figures(
                paper_ir_path,
                method_graph_path,
                catalog_path,
                asset_dir,
            )
            repaired.append("paper-method-figure-map")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-asset-select",
            "paper-method-graph",
            "paper-method-figure-map",
            "paper-method-visual-compose",
        }:
            (
                method_visual_plan_path,
                method_visual_report_path,
            ) = compose_method_visual(
                paper_ir_path,
                method_graph_path,
                method_figure_map_path,
                poster_dir,
            )
            repaired.append("paper-method-visual-compose")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-asset-select",
            "paper-method-graph",
            "paper-method-figure-map",
            "paper-key-idea",
        }:
            key_idea_spec_path, key_idea_report_path = build_key_idea(
                paper_ir_path,
                story_path,
                evidence_path,
                method_graph_path,
                method_figure_map_path,
                poster_dir,
            )
            repaired.append("paper-key-idea")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-asset-select",
            "paper-experimental-results",
        }:
            (
                experimental_results_spec_path,
                experimental_results_report_path,
            ) = build_experimental_results(
                paper_ir_path,
                story_path,
                evidence_path,
                poster_dir,
            )
            repaired.append("paper-experimental-results")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-asset-select",
            "paper-experimental-results",
            "paper-highlights",
        }:
            highlights_spec_path, highlights_report_path = build_highlights(
                paper_ir_path,
                story_path,
                evidence_path,
                experimental_results_spec_path,
                poster_dir,
            )
            repaired.append("paper-highlights")

        if stage in {
            "paper-storyline",
            "paper-evidence-audit",
            "paper-claim-evidence",
            "paper-method-graph",
            "paper-motivation-contributions",
        }:
            (
                motivation_spec_path,
                contribution_spec_path,
                motivation_contribution_audit_path,
                motivation_contribution_preview_path,
            ) = build_motivation_contributions(
                paper_ir_path,
                story_path,
                evidence_path,
                method_graph_path,
                poster_dir,
            )
            repaired.append("paper-motivation-contributions")

        return list(dict.fromkeys(repaired))

    attempts: list[dict[str, Any]] = []
    qa_path: Path | None = None
    spec_path: Path | None = None
    render_bundle_path: Path | None = None
    previous_repair_failure: tuple[str, tuple[str, ...]] | None = None
    repairable_stages = {
        "paper-storyline",
        "paper-evidence-audit",
        "paper-claim-evidence",
        "paper-asset-select",
        "paper-method-graph",
        "paper-method-figure-map",
        "paper-method-visual-compose",
        "paper-key-idea",
        "paper-experimental-results",
        "paper-highlights",
        "paper-motivation-contributions",
    }
    for cycle in range(max_validation_cycles):
        spec_path, compose_report_path = compose_poster(
            paper_ir_path,
            story_path,
            evidence_path,
            selected_path,
            method_graph_path,
            method_visual_plan_path,
            key_idea_spec_path,
            experimental_results_spec_path,
            highlights_spec_path,
            motivation_spec_path,
            contribution_spec_path,
            poster_dir,
            compact_level=cycle,
        )
        _, render_bundle_path = render_poster(
            spec_path,
            paper_ir_path,
            poster_dir,
            export_browser=export_browser,
            candidate_output=True,
        )
        qa_path = validate_poster(
            paper_ir_path,
            story_path,
            evidence_path,
            selected_path,
            method_graph_path,
            method_figure_map_path,
            method_visual_plan_path,
            key_idea_spec_path,
            experimental_results_spec_path,
            highlights_spec_path,
            motivation_spec_path,
            contribution_spec_path,
            spec_path,
            render_bundle_path,
            report_dir,
        )
        qa = read_json(qa_path)
        error_codes = tuple(
            sorted(
                str(issue.get("code") or "")
                for issue in qa.get("issues", [])
                if issue.get("severity") == "error"
                and str(issue.get("code") or "")
            )
        )
        attempt = {
            "cycle": cycle,
            "status": qa["status"],
            "return_to": qa.get("return_to"),
            "issues": [issue.get("code") for issue in qa.get("issues", [])],
        }
        attempts.append(attempt)
        if qa["status"] in {"passed", "passed_with_warnings"}:
            break
        return_to = str(qa.get("return_to") or "")
        if return_to in {"paper-poster-compose", "paper-poster-render"}:
            attempt["repaired_stage"] = return_to
            continue
        if return_to not in repairable_stages:
            attempt["unhandled_return_to"] = return_to or None
            break
        repair_failure = (return_to, error_codes)
        if repair_failure == previous_repair_failure:
            attempt["no_progress"] = True
            break
        repaired_stages = repair_failed_stage(return_to)
        attempt["repaired_stage"] = return_to
        attempt["repaired_dependency_chain"] = repaired_stages
        previous_repair_failure = repair_failure

    assert qa_path is not None and spec_path is not None and render_bundle_path is not None
    qa = read_json(qa_path)
    render_bundle_path = finalize_render_bundle(
        render_bundle_path,
        str(qa.get("status") or "failed"),
    )
    render_bundle = read_json(render_bundle_path)
    (
        reading_report_spec_path,
        reading_report_bundle_path,
        reading_report_qa_path,
    ) = build_reading_report(
        paper_ir_path=paper_ir_path,
        story_path=story_path,
        evidence_path=evidence_path,
        method_graph_path=method_graph_path,
        asset_catalog_path=catalog_path,
        selected_assets_path=selected_path,
        method_figure_map_path=method_figure_map_path,
        method_visual_plan_path=method_visual_plan_path,
        key_idea_spec_path=key_idea_spec_path,
        experimental_results_spec_path=experimental_results_spec_path,
        highlights_spec_path=highlights_spec_path,
        motivation_spec_path=motivation_spec_path,
        contribution_spec_path=contribution_spec_path,
        poster_spec_path=spec_path,
        output_dir=reading_report_dir,
        export_pdf=export_browser,
    )
    reading_report_qa = read_json(reading_report_qa_path)
    reading_report_bundle = read_json(reading_report_bundle_path)
    stage_statuses = [str(qa.get("status") or ""), str(reading_report_qa.get("status") or "")]
    if any(status in {"failed", "blocked"} for status in stage_statuses):
        final_status = "failed"
    elif any(status == "passed_with_warnings" for status in stage_statuses):
        final_status = "passed_with_warnings"
    else:
        final_status = "passed"
    delivery_status = (
        "blocked"
        if final_status == "failed"
        else "usable_with_warnings"
        if final_status == "passed_with_warnings"
        else "passed"
    )
    poster_deliverable = str(qa.get("status") or "") in {
        "passed",
        "passed_with_warnings",
    }
    summary = {
        "schema_version": "1.0.0",
        "status": final_status,
        "delivery_status": delivery_status,
        "mode": "poster",
        "input": str(input_path.resolve()),
        "output_dir": str(output_dir),
        "paper_ir": str(paper_ir_path.resolve()),
        "paper_story": str(story_path.resolve()),
        "claim_evidence": str(evidence_path.resolve()),
        "method_graph": str(method_graph_path.resolve()),
        "asset_catalog": str(catalog_path.resolve()),
        "selected_assets": str(selected_path.resolve()),
        "method_figure_map": str(method_figure_map_path.resolve()),
        "method_visual_plan": str(method_visual_plan_path.resolve()),
        "key_idea_spec": str(key_idea_spec_path.resolve()),
        "experimental_results_spec": str(
            experimental_results_spec_path.resolve()
        ),
        "highlights_spec": str(highlights_spec_path.resolve()),
        "motivation_spec": str(motivation_spec_path.resolve()),
        "contribution_spec": str(contribution_spec_path.resolve()),
        "contribution_candidates": str(contribution_candidates_path.resolve()),
        "contribution_audit": str(contribution_audit_path.resolve()),
        "motivation_contribution_audit": str(
            motivation_contribution_audit_path.resolve()
        ),
        "motivation_contribution_preview": str(
            motivation_contribution_preview_path.resolve()
        ),
        "motivation_extraction_diagnostics": str(
            (poster_dir / "extraction_diagnostics.json").resolve()
        ),
        "motivation_preflight_warnings": motivation_preflight_warnings,
        "poster_spec": str(spec_path.resolve()),
        "poster_html": (
            render_bundle.get("html_path") if poster_deliverable else None
        ),
        "poster_png": (
            render_bundle.get("png_path") if poster_deliverable else None
        ),
        "poster_pdf": (
            render_bundle.get("pdf_path") if poster_deliverable else None
        ),
        "poster_debug_html": (
            None if poster_deliverable else render_bundle.get("html_path")
        ),
        "poster_debug_png": (
            None if poster_deliverable else render_bundle.get("png_path")
        ),
        "poster_debug_pdf": (
            None if poster_deliverable else render_bundle.get("pdf_path")
        ),
        "qa_report": str(qa_path.resolve()),
        "reading_report_spec": str(reading_report_spec_path.resolve()),
        "reading_report_source_index": str(
            (reading_report_dir / "source_index.json").resolve()
        ),
        "reading_report_html": reading_report_bundle.get("html_path"),
        "reading_report_markdown": reading_report_bundle.get("markdown_path"),
        "reading_report_pdf": reading_report_bundle.get("pdf_path"),
        "reading_report_qa": str(reading_report_qa_path.resolve()),
        "stage_reports": [
            str(parse_report_path.resolve()),
            str(storyline_report_path.resolve()),
            str(method_graph_report_path.resolve()),
            str(evidence_report_path.resolve()),
            str(asset_report_path.resolve()),
            str(method_figure_map_report_path.resolve()),
            str(method_visual_report_path.resolve()),
            str(key_idea_report_path.resolve()),
            str(experimental_results_report_path.resolve()),
            str(highlights_report_path.resolve()),
            str(contribution_audit_path.resolve()),
            str(motivation_contribution_audit_path.resolve()),
            str(compose_report_path.resolve()),
            str(reading_report_qa_path.resolve()),
        ],
        "validation_attempts": attempts,
    }
    deliverables_dir = output_dir / "00-final-deliverables"
    summary["deliverables_dir"] = str(deliverables_dir.resolve())
    summary["deliverables_manifest"] = str(
        (deliverables_dir / "manifest.json").resolve()
    )
    summary_path = write_json(output_dir / "pipeline_summary.json", summary)
    try:
        export_deliverables(summary_path, deliverables_dir)
    except Exception as exc:  # pragma: no cover - defensive delivery hook
        summary.setdefault("warnings", []).append(
            f"Final deliverables export failed: {exc}"
        )
        write_json(summary_path, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the evidence-grounded paper reader.")
    parser.add_argument("--input", required=True, type=Path, help="PDF or PaperIR JSON input.")
    parser.add_argument("--output", required=True, type=Path, help="Explicit run output directory.")
    parser.add_argument(
        "--mode",
        choices=("analysis", "poster"),
        default="analysis",
        help="Run the reusable analysis core or continue through the Poster branch.",
    )
    parser.add_argument(
        "--no-browser-export",
        action="store_true",
        help="Create HTML only and skip PNG/PDF export.",
    )
    parser.add_argument("--max-validation-cycles", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_pipeline(
            args.input,
            args.output,
            parser="mineru",
            mode=args.mode,
            export_browser=not args.no_browser_export,
            max_validation_cycles=max(1, min(args.max_validation_cycles, 3)),
        )
    except Exception as error:
        print(f"paper-reader failed: {error}", file=sys.stderr)
        return 1
    print(summary["status"])
    print(summary.get("poster_html") or summary["paper_story"])
    return 0 if summary["status"] in {"passed", "passed_with_warnings"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
