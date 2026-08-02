from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .common import normalize_text, read_json, sentences, write_json


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bullets(items: list[dict[str, Any]]) -> str:
    visible = [item for item in items if item.get("text")]
    if not visible:
        return '<p class="empty-note">Not explicitly stated in the paper.</p>'
    return "<ul>" + "".join(
        f'<li data-status="{html.escape(str(item.get("status", "")))}">'
        f'{html.escape(str(item["text"]))}</li>'
        for item in visible
    ) + "</ul>"


def _motivation(items: list[dict[str, Any]]) -> str:
    visible = [
        str(item.get("visible_text") or "").strip()
        for item in items
        if str(item.get("visible_text") or "").strip()
    ]
    if not visible:
        return '<p class="empty-note">No Motivation item passed every content Gate.</p>'
    return (
        f'<ul class="motivation-items" data-item-count="{len(visible)}">'
        + "".join(f"<li>{html.escape(text)}</li>" for text in visible)
        + "</ul>"
    )


def _copy_asset(
    asset: dict[str, Any] | None,
    paper_ir_dir: Path,
    output_dir: Path,
) -> str | None:
    if not asset or not asset.get("path"):
        return None
    source = Path(str(asset["path"]))
    if not source.is_absolute():
        source = paper_ir_dir / source
    if not source.is_file():
        return None
    target_dir = output_dir / "assets"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{asset.get('id', source.stem)}{source.suffix.lower()}"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target.relative_to(output_dir).as_posix()


def _asset_figure(
    selected: dict[str, Any] | None,
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
    empty_text: str,
    caption_sentence_limit: int | None = None,
) -> str:
    if not selected:
        return f'<div class="asset-placeholder">{html.escape(empty_text)}</div>'
    asset = catalog.get(str(selected.get("id")), selected)
    relative = _copy_asset(asset, paper_ir_dir, output_dir)
    caption = normalize_text(str(asset.get("caption") or ""))
    if caption_sentence_limit and caption:
        caption_parts = sentences(caption)
        if caption_parts:
            caption = " ".join(caption_parts[:caption_sentence_limit])
    if not relative:
        return (
            '<div class="asset-placeholder">'
            f'{html.escape(empty_text)}<small>{html.escape(caption)}</small></div>'
        )
    return (
        f'<figure data-asset-id="{html.escape(str(asset.get("id")))}">'
        f'<img src="{html.escape(relative)}" alt="{html.escape(caption or str(asset.get("id")))}">'
        f'<figcaption>{html.escape(caption)}</figcaption>'
        "</figure>"
    )


def _method_overview_content(
    panel: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    if panel.get("asset"):
        figure = _asset_figure(
            panel.get("asset"),
            catalog,
            paper_ir_dir,
            output_dir,
            "Method overview asset unavailable.",
            caption_sentence_limit=1,
        )
        return (
            '<div class="method-overview-content mode-original-figure" '
            'data-method-overview-mode="original_figure" '
            'data-method-overview-flow-count="0">'
            + figure
            + "</div>"
        )

    flow_items = [
        item
        for item in panel.get("flow_items", [])
        if str(item.get("module_id") or "").strip()
        and normalize_text(str(item.get("label") or ""))
        and normalize_text(str(item.get("text") or ""))
        and item.get("source_block_ids")
    ]
    if flow_items:
        stages = "".join(
            '<article class="method-overview-stage" '
            f'data-module-id="{html.escape(str(item.get("module_id") or ""))}" '
            f'data-source-block-ids="{html.escape(",".join(str(value) for value in item.get("source_block_ids", [])))}">'
            f'<span class="method-overview-index">{index}</span>'
            f'<h3>{html.escape(str(item.get("label") or f"Stage {index}"))}</h3>'
            f'<p>{html.escape(normalize_text(str(item.get("text") or "")))}</p>'
            "</article>"
            for index, item in enumerate(flow_items, start=1)
        )
        return (
            '<div class="method-overview-content mode-sourced-method-flow" '
            'data-method-overview-mode="sourced_method_flow" '
            f'data-method-overview-flow-count="{len(flow_items)}">'
            '<div class="method-overview-flow">'
            + stages
            + "</div></div>"
        )

    return (
        '<div class="method-overview-content mode-no-overview-figure" '
        'data-method-overview-mode="no-overview-figure" '
        'data-method-overview-flow-count="0" '
        'data-method-overview-empty="true">'
        '<p class="empty-note">No evidence-backed method overview could be rendered.</p>'
        "</div>"
    )


def _method_path(callouts: list[dict[str, Any]]) -> str:
    if not callouts:
        return ""
    cards: list[str] = []
    for index, item in enumerate(callouts, start=1):
        cards.append(
            '<article class="method-path-step" '
            f'data-module-id="{html.escape(str(item.get("module_id") or ""))}">'
            f'<span class="method-step-index">{index}</span>'
            f'<h3>{html.escape(str(item.get("label") or f"Step {index}"))}</h3>'
            f'<p>{html.escape(normalize_text(str(item.get("description") or "")))}</p>'
            "</article>"
        )
    return '<div class="method-reading-path">' + "".join(cards) + "</div>"


def _method_storyboard(
    items: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    cards: list[str] = []
    fallback_count = 0
    original_count = 0
    for index, item in enumerate(items, start=1):
        asset_id = str(item.get("asset_id") or "")
        asset = catalog.get(asset_id, item) if asset_id else None
        relative = _copy_asset(asset, paper_ir_dir, output_dir)
        display_mode = str(item.get("display_mode") or "")
        use_original = bool(
            display_mode != "mechanism_flow"
            and asset_id
            and relative
        )
        focus_labels = [
            normalize_text(str(value))
            for value in item.get("focus_subfigure_labels", [])
            if normalize_text(str(value))
        ]
        focus_note = (
            '<span class="method-subfigure-focus">'
            + html.escape(
                "Focus: "
                + ", ".join(
                    f"Fig. {re.sub(r'^figure-', '', str(item.get('asset_id') or ''), flags=re.I)}({label})"
                    for label in focus_labels
                )
            )
            + "</span>"
            if focus_labels
            else ""
        )
        if use_original:
            original_count += 1
            visual = (
                '<figure class="method-story-figure">'
                f'<img src="{html.escape(relative)}" '
                f'alt="{html.escape(str(item.get("label") or asset.get("id")))}">'
                "</figure>"
            )
            card_class = "is-original-figure"
        else:
            fallback_count += 1
            stages = list((item.get("flow") or {}).get("stages") or [])
            if not stages:
                stages = [
                    {
                        "label": "Mechanism",
                        "text": normalize_text(
                            str(item.get("description") or "")
                        ).rstrip("."),
                    }
                ]
            flow_nodes = "".join(
                '<div class="method-flow-stage">'
                f'<strong>{html.escape(str(stage.get("label") or "Step"))}</strong>'
                f'<span>{html.escape(normalize_text(str(stage.get("text") or "")))}</span>'
                "</div>"
                for stage in stages
                if normalize_text(str(stage.get("text") or ""))
            )
            visual = (
                '<div class="method-mechanism-flow" '
                'data-method-fallback="mechanism_flow">'
                + flow_nodes
                + "</div>"
            )
            card_class = "is-mechanism-flow"
        module_ids = [
            str(value)
            for value in item.get("module_ids", [])
            if str(value)
        ]
        asset_attribute = (
            f' data-method-asset-id="{html.escape(asset_id)}"'
            if use_original
            else ""
        )
        cards.append(
            f'<article class="method-story-card {card_class}"'
            + asset_attribute
            + " "
            f'data-module-id="{html.escape(",".join(module_ids))}" '
            f'data-method-card-mode="{"original_figure" if use_original else "mechanism_flow"}" '
            f'data-focus-subfigures="{html.escape(",".join(focus_labels))}" '
            'data-asset-role="method">'
            f'<span class="method-step-index">{index}</span>'
            + visual
            + focus_note
            + f'<h3>{html.escape(str(item.get("label") or f"Step {index}"))}</h3>'
            + f'<p>{html.escape(normalize_text(str(item.get("description") or "")))}</p>'
            + "</article>"
        )
    if not cards:
        return ""
    mode_class = (
        "has-only-mechanism-flow"
        if fallback_count and not original_count
        else "has-mixed-method-cards"
        if fallback_count and original_count
        else "has-only-original-figures"
    )
    return (
        f'<div class="method-storyboard {mode_class}" '
        f'data-method-original-count="{original_count}" '
        f'data-method-fallback-count="{fallback_count}">'
        + "".join(cards)
        + "</div>"
    )


def _experiment_strip(items: list[dict[str, Any]]) -> str:
    labels = {
        "datasets": "DATA",
        "baselines": "BASE",
        "metrics": "METRIC",
        "protocol": "SETUP",
    }
    cards = [
        '<article class="experiment-chip">'
        f'<strong>{labels.get(str(item.get("kind")), "SETUP")}</strong>'
        f'<span>{html.escape(normalize_text(str(item.get("text") or "")))}</span>'
        "</article>"
        for item in items
        if item.get("text")
    ]
    return (
        '<div class="experiment-design-strip">'
        '<div class="experiment-strip-label">Experimental design</div>'
        '<div class="experiment-chip-grid">'
        + "".join(cards)
        + "</div></div>"
        if cards
        else ""
    )


def _method_visual_story(
    plan: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    mode = str(plan.get("mode") or "text_only_method_path")
    storyboard = _method_storyboard(
        plan.get("storyboard_items", []),
        catalog,
        paper_ir_dir,
        output_dir,
    )
    reading_path = _method_path(plan.get("callouts", []))
    primary = storyboard or reading_path
    explanation = ""
    if mode == "single_overview":
        explanation = (
            '<p class="overview-reading-note">'
            "Read the complete overview above in this evidence-backed order."
            "</p>"
        )
    return (
        f'<div class="method-visual-story mode-{html.escape(mode)}" '
        f'data-method-mode="{html.escape(mode)}">'
        + explanation
        + primary
        + _experiment_strip(plan.get("experiment_strip", []))
        + "</div>"
    )


def _equations(
    selected: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    if not selected:
        return '<p class="empty-note">No central equation was identified.</p>'
    values: list[str] = []
    for item in selected:
        asset = catalog.get(str(item.get("id")), item)
        # Prefer the exact source crop. It survives offline HTML/PNG/PDF
        # export and preserves the paper's original mathematical typography.
        relative = _copy_asset(asset, paper_ir_dir, output_dir)
        if relative:
            values.append(
                f'<figure class="equation-figure" '
                f'data-equation-id="{html.escape(str(asset.get("id")))}">'
                f'<img class="equation-image" src="{html.escape(relative)}" '
                f'alt="Equation {html.escape(str(asset.get("id")))}"></figure>'
            )
            continue
        if asset.get("latex"):
            values.append(
                f'<div class="equation equation-fallback" '
                f'data-equation-id="{html.escape(str(asset.get("id")))}">'
                f'{html.escape(str(asset["latex"]))}</div>'
            )
    return "".join(values) or '<p class="empty-note">Equation extraction requires review.</p>'


def _key_idea_content(
    spec: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    idea_type = str(spec.get("type") or "mechanism_centered")
    visual = spec.get("visual") or {}
    visual_type = str(visual.get("visual_type") or "three_step_flow")
    items = visual.get("items") or []
    cards = "".join(
        '<article class="key-idea-item">'
        f'<strong>{html.escape(str(item.get("label") or ""))}</strong>'
        f'<span>{html.escape(normalize_text(str(item.get("text") or "")))}</span>'
        "</article>"
        for item in items
        if item.get("text")
    )
    visual_html = (
        f'<div class="key-idea-visual visual-{html.escape(visual_type)}" '
        f'data-key-idea-visual="{html.escape(visual_type)}">'
        + cards
        + "</div>"
    )

    equation = spec.get("equation") or {}
    display_mode = str(equation.get("display_mode") or "none")
    equation_html = ""
    if display_mode == "original_crop" and equation.get("equation_id"):
        asset = catalog.get(str(equation["equation_id"]), equation)
        relative = _copy_asset(asset, paper_ir_dir, output_dir)
        if relative:
            equation_html = (
                '<figure class="key-idea-equation" '
                f'data-key-equation-id="{html.escape(str(equation["equation_id"]))}" '
                'data-equation-display-mode="original_crop">'
                f'<img src="{html.escape(relative)}" '
                f'alt="Equation {html.escape(str(equation["equation_id"]))}"></figure>'
            )
    elif display_mode == "latex_render":
        # A formal Poster must never expose raw TeX source. The Key Idea
        # generator currently requires an original crop for display; legacy
        # latex_render specs therefore degrade to the adaptive no-equation
        # layout instead of printing unrendered commands.
        equation_html = ""
    explanation = normalize_text(
        str(equation.get("plain_language_explanation") or "")
    )
    if equation_html and explanation:
        equation_html += (
            f'<p class="key-idea-explanation">{html.escape(explanation)}</p>'
        )
    no_equation_class = " no-equation" if not equation_html else ""
    inferred = " inferred" if spec.get("inferred") else ""
    item_count_class = f" items-{len(items)}"
    return (
        f'<div class="key-idea-content type-{html.escape(idea_type)}'
        f'{no_equation_class}{inferred}{item_count_class}" '
        f'data-key-idea-type="{html.escape(idea_type)}" '
        f'data-key-idea-inferred="{str(bool(spec.get("inferred"))).lower()}" '
        f'data-key-idea-item-count="{len(items)}">'
        f'<h3>{html.escape(str(spec.get("headline") or ""))}</h3>'
        + visual_html
        + equation_html
        + (
            '<p class="key-idea-inference-label">'
            f'{html.escape(str(spec.get("inference_label") or "Inferred from source evidence"))}'
            "</p>"
            if spec.get("inferred")
            else ""
        )
        + f'<p class="key-idea-takeaway">{html.escape(str(spec.get("takeaway") or ""))}</p>'
        + "</div>"
    )


def _result_asset(
    selected: dict[str, Any] | None,
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
    role: str,
) -> str:
    if not selected:
        return ""
    asset_id = str(selected.get("asset_id") or "")
    asset = dict(catalog.get(asset_id, selected))
    caption = normalize_text(
        str(selected.get("display_caption") or selected.get("caption") or "")
    )
    asset_type = str(selected.get("asset_type") or asset.get("asset_type") or "")
    focus_table = selected.get("focus_table") or {}
    if (
        selected.get("display_mode") == "verified_focus_table"
        and focus_table.get("headers")
        and focus_table.get("rows")
    ):
        header_html = "".join(
            f"<th>{html.escape(str(value))}</th>"
            for value in focus_table["headers"]
        )
        row_html = "".join(
            '<tr class="focus-row-'
            f'{html.escape(str(row.get("role") or "context"))}">'
            + "".join(
                f"<td>{html.escape(str(value))}</td>"
                for value in row.get("cells", [])
            )
            + "</tr>"
            for row in focus_table["rows"]
        )
        source_note = (
            f"Verified focus view · {asset_id} · p.{focus_table.get('source_page')}"
        )
        return (
            f'<figure class="result-asset result-{html.escape(role)} '
            f'result-type-{html.escape(str(selected.get("result_type") or ""))}" '
            f'data-result-asset-role="{html.escape(role)}" '
            f'data-result-asset-id="{html.escape(asset_id)}" '
            f'data-result-asset-type="{html.escape(asset_type)}">'
            '<div class="result-focus-table-wrap">'
            '<table class="result-focus-table" '
            f'data-source-table-id="{html.escape(asset_id)}">'
            f"<thead><tr>{header_html}</tr></thead>"
            f"<tbody>{row_html}</tbody>"
            "</table>"
            f'<p class="result-focus-source">{html.escape(source_note)}</p>'
            "</div>"
            f"<figcaption>{html.escape(caption)}</figcaption>"
            "</figure>"
        )
    if selected.get("display_path"):
        asset["path"] = selected["display_path"]
    relative = _copy_asset(asset, paper_ir_dir, output_dir)
    if not relative:
        return (
            f'<div class="asset-placeholder result-{html.escape(role)}" '
            f'data-result-asset-role="{html.escape(role)}" '
            f'data-result-asset-id="{html.escape(asset_id)}">'
            "Result asset unavailable.</div>"
        )
    return (
        f'<figure class="result-asset result-{html.escape(role)} '
        f'result-type-{html.escape(str(selected.get("result_type") or ""))}" '
        f'data-result-asset-role="{html.escape(role)}" '
        f'data-result-asset-id="{html.escape(asset_id)}" '
        f'data-result-asset-type="{html.escape(asset_type)}">'
        f'<img src="{html.escape(relative)}" '
        f'alt="{html.escape(str(selected.get("caption") or caption or asset_id))}">'
        f'<figcaption>{html.escape(caption)}</figcaption>'
        "</figure>"
    )


def _result_metrics(metrics: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for metric in metrics[:4]:
        baseline = normalize_text(str(metric.get("baseline") or ""))
        baseline_value = normalize_text(str(metric.get("baseline_value") or ""))
        delta = normalize_text(str(metric.get("delta") or ""))
        comparison = f"vs {baseline}"
        if baseline_value:
            comparison += f" ({baseline_value})"
        if delta:
            comparison += f" · Δ {delta}"
        cards.append(
            '<article class="result-metric-card" '
            f'data-result-metric="{html.escape(str(metric.get("metric") or ""))}" '
            f'data-result-dataset="{html.escape(str(metric.get("dataset") or ""))}" '
            f'data-result-configuration="{html.escape(str(metric.get("configuration") or ""))}">'
            f'<strong>{html.escape(str(metric.get("value") or ""))}</strong>'
            f'<span class="result-metric-name">{html.escape(str(metric.get("metric") or ""))}</span>'
            f'<small>{html.escape(comparison)}</small>'
            "</article>"
        )
    return '<div class="result-metrics">' + "".join(cards) + "</div>"


def _experimental_results_content(
    spec: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    layout = str(spec.get("layout_template") or "quantitative_plus_qualitative")
    primary = _result_asset(
        spec.get("primary_asset"),
        catalog,
        paper_ir_dir,
        output_dir,
        "primary",
    )
    secondary = _result_asset(
        spec.get("secondary_asset"),
        catalog,
        paper_ir_dir,
        output_dir,
        "secondary",
    )
    asset_class = " has-secondary" if secondary else " primary-only"
    return (
        f'<div class="experimental-results-content layout-{html.escape(layout)}'
        f'{asset_class}" data-results-layout="{html.escape(layout)}">'
        f'<h3>{html.escape(str(spec.get("result_headline") or ""))}</h3>'
        + _result_metrics(spec.get("key_metrics") or [])
        + '<div class="result-evidence-grid">'
        + primary
        + secondary
        + "</div>"
        + f'<p class="result-condition">{html.escape(str(spec.get("condition_note") or ""))}</p>'
        + "</div>"
    )


def _contributions(items: list[dict[str, Any]]) -> str:
    visible = [
        str(item.get("visible_text") or "").strip()
        for item in items
        if str(item.get("visible_text") or "").strip()
    ]
    if not visible:
        return '<p class="empty-note">No supported contribution was selected.</p>'
    cards: list[str] = []
    for value in visible:
        title, _, description = value.partition("\n")
        cards.append(
            '<article class="contribution-card">'
            f"<strong>{html.escape(title)}</strong>"
            f"<span>{html.escape(description)}</span>"
            "</article>"
        )
    return (
        f'<div class="contribution-items" data-item-count="{len(cards)}">'
        + "".join(cards)
        + "</div>"
    )


def _highlights(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="empty-note">No result passed every Highlight gate.</p>'
    return "".join(
        '<div class="highlight-card" '
        f'data-highlight-role="{html.escape(str(item.get("role") or ""))}" '
        f'data-evidence-id="{html.escape(str(item.get("evidence_id") or ""))}">'
        f'<strong>{html.escape(str(item.get("primary_value") or "•"))}</strong>'
        f'<span class="highlight-label">{html.escape(normalize_text(str(item.get("label") or "")))}</span>'
        f'<small>{html.escape(normalize_text(str(item.get("context") or "")))}</small>'
        "</div>"
        for item in items
    )


def _project_content(project: dict[str, Any] | None) -> str:
    project = project or {}
    code_url = str(project.get("code_url") or "").strip()
    paper_url = str(project.get("paper_url") or "").strip()
    parts: list[str] = []

    if code_url:
        escaped_code_url = html.escape(code_url, quote=True)
        parts.append('<div class="project-status">Code: Open source</div>')
        parts.append(
            f'<a class="project-link" href="{escaped_code_url}" '
            f'target="_blank" rel="noreferrer">{escaped_code_url}</a>'
        )
    else:
        parts.append(
            '<div class="project-status">Code not publicly available</div>'
        )

    if paper_url:
        escaped_paper_url = html.escape(paper_url, quote=True)
        parts.append(
            f'<a class="project-paper" href="{escaped_paper_url}" '
            f'target="_blank" rel="noreferrer">Paper: {escaped_paper_url}</a>'
        )

    return "".join(parts)


def _find_runtime() -> dict[str, str | None]:
    home = Path.home()
    bundled = home / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"
    node_candidates = [
        os.environ.get("PAPER_READER_NODE"),
        shutil.which("node"),
        str(bundled / "node" / "bin" / "node.exe"),
    ]
    module_candidates = [
        os.environ.get("PAPER_READER_NODE_MODULES"),
        str(bundled / "node" / "node_modules"),
    ]
    browser_candidates = [
        os.environ.get("PAPER_READER_BROWSER"),
        shutil.which("msedge"),
        shutil.which("chrome"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]

    def first_file(values: list[str | None]) -> str | None:
        return next((value for value in values if value and Path(value).is_file()), None)

    def first_dir(values: list[str | None]) -> str | None:
        return next((value for value in values if value and Path(value).is_dir()), None)

    return {
        "node": first_file(node_candidates),
        "node_modules": first_dir(module_candidates),
        "browser": first_file(browser_candidates),
    }


def _browser_export(
    html_path: Path,
    png_path: Path,
    pdf_path: Path,
    metrics_path: Path,
    canvas: dict[str, Any],
) -> tuple[bool, str | None]:
    runtime = _find_runtime()
    if not all(runtime.values()):
        return False, "Node.js, Playwright, or a Chromium browser was not detected."
    script = _project_root() / "skills" / "paper-poster-render" / "scripts" / "render_browser.cjs"
    command = [
        str(runtime["node"]),
        str(script),
        str(html_path.resolve()),
        str(png_path.resolve()),
        str(pdf_path.resolve()),
        str(metrics_path.resolve()),
        str(canvas.get("width_px", 3840)),
        str(canvas.get("height_px", 2160)),
        str(canvas.get("pdf_width", "48in")),
        str(canvas.get("pdf_height", "27in")),
        str(runtime["browser"]),
        str(runtime["node_modules"]),
    ]
    completed = subprocess.run(
        command,
        cwd=str(_project_root()),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Browser export failed.").strip()
        return False, message[-1200:]
    return True, None


def render_poster(
    poster_spec_path: Path,
    paper_ir_path: Path,
    output_dir: Path,
    export_browser: bool = True,
    candidate_output: bool = False,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = read_json(poster_spec_path)
    preview_status = str(spec.get("preview_status") or "invalid")
    formal_output_allowed = bool(
        spec.get("formal_output_allowed")
        and preview_status == "valid"
    )
    paper_ir = read_json(paper_ir_path)
    paper_ir_dir = paper_ir_path.parent
    assets = {
        asset["id"]: asset
        for group in ("figures", "equations", "tables")
        for asset in paper_ir.get(group, [])
    }
    panels = spec["panels"]
    header = spec["header"]

    overview = _method_overview_content(
        panels["method_overview"],
        assets,
        paper_ir_dir,
        output_dir,
    )
    template_path = _project_root() / "skills" / "paper-poster-render" / "assets" / "amp-template" / "poster.html"
    css_path = _project_root() / "skills" / "paper-poster-render" / "assets" / "amp-template" / "poster.css"
    template = template_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    replacements = {
        "STYLE": css,
        "TITLE": html.escape(str(header.get("title") or "Untitled paper")),
        "AUTHORS": html.escape(", ".join(header.get("authors") or [])),
        "AFFILIATIONS": html.escape(" · ".join(header.get("affiliations") or [])),
        "MOTIVATION": _motivation(panels["motivation"]),
        "METHOD_OVERVIEW": overview,
        "METHOD_SUMMARY": html.escape(str(panels["method_overview"]["summary"].get("text") or "")),
        "KEY_IDEA_CONTENT": _key_idea_content(
            panels["key_idea"],
            assets,
            paper_ir_dir,
            output_dir,
        ),
        "METHOD_DETAIL": _bullets(
            [
                panels["method_detail"]["method"],
                panels["method_detail"]["experimental_design"],
            ]
        )
        if not panels["method_detail"].get("visual_story")
        else _method_visual_story(
            panels["method_detail"]["visual_story"],
            assets,
            paper_ir_dir,
            output_dir,
        ),
        "RESULT_CONTENT": _experimental_results_content(
            panels["experimental_results"],
            assets,
            paper_ir_dir,
            output_dir,
        ),
        "CONTRIBUTIONS": _contributions(panels.get("contributions", [])),
        "HIGHLIGHTS": _highlights(panels.get("highlights", [])),
        "PROJECT_CONTENT": _project_content(panels.get("project")),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    rendered = rendered.replace(
        "<body>",
        f'<body data-preview-status="{html.escape(preview_status)}">',
        1,
    )

    if formal_output_allowed:
        html_path = output_dir / (
            "poster-candidate.html" if candidate_output else "poster.html"
        )
    else:
        html_path = output_dir / "key-idea-debug-preview.html"
    html_path.write_text(rendered, encoding="utf-8", newline="\n")
    output_stem = "poster-candidate" if candidate_output else "poster"
    png_path = output_dir / f"{output_stem}.png"
    pdf_path = output_dir / f"{output_stem}.pdf"
    metrics_path = output_dir / (
        "candidate-render-metrics.json"
        if candidate_output
        else "render_metrics.json"
    )
    if not formal_output_allowed:
        for stale_path in (
            output_dir / "poster.html",
            output_dir / "poster.png",
            output_dir / "poster.pdf",
            output_dir / "render_metrics.json",
            output_dir / "poster-candidate.html",
            output_dir / "poster-candidate.png",
            output_dir / "poster-candidate.pdf",
            output_dir / "candidate-render-metrics.json",
        ):
            if stale_path.is_file():
                stale_path.unlink()
    elif candidate_output:
        for stale_path in (
            output_dir / "poster.html",
            output_dir / "poster.png",
            output_dir / "poster.pdf",
            output_dir / "render_metrics.json",
            output_dir / "poster-debug.html",
            output_dir / "poster-debug.png",
            output_dir / "poster-debug.pdf",
            output_dir / "debug-render-metrics.json",
        ):
            if stale_path.is_file():
                stale_path.unlink()
    exported = False
    export_error = None
    effective_export_browser = export_browser and formal_output_allowed
    if effective_export_browser:
        exported, export_error = _browser_export(
            html_path,
            png_path,
            pdf_path,
            metrics_path,
            spec["canvas"],
        )

    bundle = {
        "status": (
            "debug_preview"
            if not formal_output_allowed
            else "passed"
            if (exported or not effective_export_browser)
            else "passed_with_warnings"
        ),
        "preview_status": preview_status,
        "formal_output_allowed": formal_output_allowed,
        "formal_export_blocked": not formal_output_allowed,
        "candidate_output": bool(candidate_output and formal_output_allowed),
        "canvas": dict(spec.get("canvas") or {}),
        "html_path": str(html_path.resolve()),
        "png_path": str(png_path.resolve()) if png_path.is_file() else None,
        "pdf_path": str(pdf_path.resolve()) if pdf_path.is_file() else None,
        "metrics_path": str(metrics_path.resolve()) if metrics_path.is_file() else None,
        "browser_export_requested": effective_export_browser,
        "browser_exported": exported,
        "warnings": [export_error] if export_error else [],
    }
    return html_path, write_json(output_dir / "render_bundle.json", bundle)


def finalize_render_bundle(
    render_bundle_path: Path,
    qa_status: str,
) -> Path:
    """Promote a validated candidate or preserve a failed one as debug output."""
    bundle = read_json(render_bundle_path)
    if not bundle.get("candidate_output"):
        bundle["delivery_status"] = (
            "blocked"
            if qa_status in {"failed", "blocked"}
            else "usable_with_warnings"
            if qa_status == "passed_with_warnings"
            else "passed"
        )
        bundle["status"] = qa_status
        return write_json(render_bundle_path, bundle)

    output_dir = render_bundle_path.parent
    passed = qa_status in {"passed", "passed_with_warnings"}
    target_stem = "poster" if passed else "poster-debug"
    source_html = Path(str(bundle.get("html_path") or ""))
    target_html = output_dir / f"{target_stem}.html"
    target_png = output_dir / f"{target_stem}.png"
    target_pdf = output_dir / f"{target_stem}.pdf"
    target_metrics = output_dir / (
        "render_metrics.json" if passed else "debug-render-metrics.json"
    )
    stale_targets = (
        (
            output_dir / "poster-debug.html",
            output_dir / "poster-debug.png",
            output_dir / "poster-debug.pdf",
            output_dir / "debug-render-metrics.json",
        )
        if passed
        else (
            output_dir / "poster.html",
            output_dir / "poster.png",
            output_dir / "poster.pdf",
            output_dir / "render_metrics.json",
        )
    )
    for stale_path in stale_targets:
        if stale_path.is_file():
            stale_path.unlink()

    if source_html.is_file():
        rendered = source_html.read_text(encoding="utf-8")
        if not passed:
            rendered = rendered.replace(
                'data-preview-status="valid"',
                'data-preview-status="invalid"',
                1,
            )
            rendered = rendered.replace(
                "<body ",
                '<body data-delivery-status="blocked" ',
                1,
            )
        target_html.write_text(rendered, encoding="utf-8", newline="\n")

    browser_requested = bool(bundle.get("browser_export_requested"))
    exported = False
    export_error = None
    if passed:
        for key, target in (
            ("png_path", target_png),
            ("pdf_path", target_pdf),
            ("metrics_path", target_metrics),
        ):
            source_value = bundle.get(key)
            source = Path(str(source_value)) if source_value else None
            if source and source.is_file():
                shutil.copy2(source, target)
        exported = (
            (target_png.is_file() and target_pdf.is_file())
            if browser_requested
            else True
        )
    elif browser_requested and target_html.is_file():
        exported, export_error = _browser_export(
            target_html,
            target_png,
            target_pdf,
            target_metrics,
            bundle.get("canvas") or {"width_px": 3840, "height_px": 2160},
        )

    for stale_path in (
        output_dir / "poster-candidate.html",
        output_dir / "poster-candidate.png",
        output_dir / "poster-candidate.pdf",
        output_dir / "candidate-render-metrics.json",
    ):
        if stale_path.is_file():
            stale_path.unlink()

    bundle.update(
        {
            "status": qa_status,
            "delivery_status": (
                "blocked"
                if not passed
                else "usable_with_warnings"
                if qa_status == "passed_with_warnings"
                else "passed"
            ),
            "candidate_output": False,
            "formal_output_allowed": passed,
            "formal_export_blocked": not passed,
            "html_path": (
                str(target_html.resolve()) if target_html.is_file() else None
            ),
            "png_path": (
                str(target_png.resolve()) if target_png.is_file() else None
            ),
            "pdf_path": (
                str(target_pdf.resolve()) if target_pdf.is_file() else None
            ),
            "metrics_path": (
                str(target_metrics.resolve())
                if target_metrics.is_file()
                else None
            ),
            "browser_exported": exported,
            "warnings": [
                *list(bundle.get("warnings") or []),
                *([export_error] if export_error else []),
            ],
        }
    )
    return write_json(render_bundle_path, bundle)
