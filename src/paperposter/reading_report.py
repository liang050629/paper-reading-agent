from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .common import normalize_text, read_json, write_json
from .render import _find_runtime


STORY_FIELDS = (
    ("research_problem", "Research Problem"),
    ("motivation", "Motivation"),
    ("prior_work_gap", "Prior-Work Gap"),
    ("core_hypothesis", "Core Hypothesis"),
    ("method_design", "Method Design"),
    ("theory_or_mechanism", "Theory or Mechanism"),
    ("experimental_design", "Experimental Design"),
    ("experimental_results", "Experimental Results"),
    ("conclusion", "Conclusion"),
    ("limitations", "Limitations"),
)


def _load_optional(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return read_json(path)


def _unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value in (None, "", []):
            continue
        if value not in result:
            result.append(value)
    return result


def _block_index(paper_ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(block.get("id")): block
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }


def _asset_index(paper_ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(asset.get("id")): asset
        for group in ("figures", "equations", "tables")
        for asset in paper_ir.get(group, [])
        if asset.get("id")
    }


def _attach_source_assets(
    sources: list[dict[str, Any]],
    assets: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    for source in sources:
        block_id = str(source.get("block_id") or "")
        for asset_id, asset in assets.items():
            if block_id not in {str(value) for value in asset.get("cited_by") or []}:
                continue
            target = {
                "figure": "figure_ids",
                "table": "table_ids",
                "equation": "equation_ids",
            }.get(str(asset.get("asset_type") or ""))
            if target and asset_id not in source[target]:
                source[target].append(asset_id)
    return sources


def _source_record(
    block_id: str,
    blocks: dict[str, dict[str, Any]],
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block = blocks.get(block_id, {})
    fallback = fallback or {}
    return {
        "block_id": block_id,
        "page": int(block.get("page") or fallback.get("page") or 1),
        "section": str(
            block.get("section_title")
            or block.get("section_id")
            or fallback.get("section")
            or ""
        ),
        "bbox": block.get("bbox", fallback.get("bbox")),
        "quote": normalize_text(
            str(block.get("text") or fallback.get("quote") or fallback.get("raw_statement") or "")
        ),
        "figure_ids": [],
        "table_ids": [],
        "equation_ids": [],
    }


def _source_records(
    source_ids: Iterable[str],
    blocks: dict[str, dict[str, Any]],
    fallbacks: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    fallback_by_id = {
        str(item.get("block_id")): item for item in fallbacks if item.get("block_id")
    }
    return [
        _source_record(block_id, blocks, fallback_by_id.get(block_id))
        for block_id in _unique(str(item) for item in source_ids if item)
    ]


def _storyline(story: dict[str, Any], blocks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, label in STORY_FIELDS:
        node = story.get(key) or {}
        sources = node.get("sources") or []
        source_ids = [str(source.get("block_id")) for source in sources if source.get("block_id")]
        items.append(
            {
                "id": f"story-{key.replace('_', '-')}",
                "role": key,
                "label": label,
                "summary": normalize_text(str(node.get("summary") or "")),
                "status": str(node.get("status") or "not_found"),
                "confidence": float(node.get("confidence") or 0.0),
                "inferred": node.get("status") == "inferred",
                "sources": _source_records(source_ids, blocks, sources),
            }
        )
    return items


def _motivation_items(
    spec: dict[str, Any], blocks: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in spec.get("items", []):
        source_ids = item.get("source_block_ids") or []
        items.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "text": item.get("visible_text") or item.get("normalized_meaning") or "",
                "confidence": item.get("confidence", 0.0),
                "sources": _source_records(
                    source_ids,
                    blocks,
                    item.get("source_records") or [],
                ),
            }
        )
    return items


def _contribution_items(
    spec: dict[str, Any], blocks: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in spec.get("items", []):
        items.append(
            {
                "id": item.get("id"),
                "short_title": item.get("short_title") or "Contribution",
                "description": item.get("description") or item.get("visible_text") or "",
                "contribution_type": item.get("contribution_type"),
                "innovation_object": item.get("innovation_object") or "",
                "mechanism": item.get("mechanism") or item.get("mechanism_or_action") or "",
                "purpose": item.get("purpose") or item.get("solved_problem") or "",
                "supporting_evidence": item.get("supporting_evidence") or [],
                "confidence": item.get("confidence", 0.0),
                "sources": _source_records(
                    item.get("source_block_ids") or [],
                    blocks,
                    item.get("source_records") or [],
                ),
            }
        )
    return items


def _method_modules(
    method_graph: dict[str, Any],
    method_figure_map: dict[str, Any],
    assets: dict[str, dict[str, Any]],
    blocks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping_records = {
        str(record.get("asset_id")): record
        for record in method_figure_map.get("records", [])
        if record.get("asset_id")
    }
    overview_asset_id = str(method_figure_map.get("overview_asset_id") or "")
    modules: list[dict[str, Any]] = []
    for node in sorted(method_graph.get("nodes", []), key=lambda value: value.get("order", 0)):
        node_id = str(node.get("id") or "")
        figure_ids = list(node.get("figure_refs") or [])
        for asset_id, record in mapping_records.items():
            if any(
                str(mapping.get("module_id") or mapping.get("node_id") or "") == node_id
                for mapping in record.get("module_mappings") or []
            ):
                figure_ids.append(asset_id)
        figure_ids = [
            figure_id
            for figure_id in _unique(figure_ids)
            if figure_id in assets and figure_id != overview_asset_id
        ]
        modules.append(
            {
                "id": node_id,
                "order": node.get("order"),
                "name": node.get("name") or node.get("section_title") or "Method module",
                "purpose": normalize_text(str(node.get("purpose") or "")),
                "innovation": normalize_text(str(node.get("innovation") or "")),
                "section_id": node.get("section_id"),
                "section_title": node.get("section_title"),
                "status": node.get("status"),
                "figure_ids": figure_ids,
                "figures": [
                    {
                        "asset_id": figure_id,
                        "caption": assets[figure_id].get("caption") or "",
                        "page": assets[figure_id].get("page"),
                        "bbox": assets[figure_id].get("bbox"),
                        "path": assets[figure_id].get("path"),
                    }
                    for figure_id in figure_ids
                ],
                "sources": _source_records(
                    [
                        str(source.get("block_id"))
                        for source in node.get("sources") or []
                        if source.get("block_id")
                    ],
                    blocks,
                    node.get("sources") or [],
                ),
            }
        )
    return modules


def _formula_items(
    paper_ir: dict[str, Any],
    key_idea: dict[str, Any],
    claims: list[dict[str, Any]],
    blocks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    core_equation_id = str((key_idea.get("equation") or {}).get("equation_id") or "")
    claim_blocks = {
        str(claim.get("claim_id") or claim.get("id") or ""): {
            str(source.get("block_id"))
            for source in claim.get("sources") or []
            if source.get("block_id")
        }
        for claim in claims
    }
    formulas: list[dict[str, Any]] = []
    for equation in paper_ir.get("equations", []):
        equation_id = str(equation.get("id") or "")
        cited_by = [str(value) for value in equation.get("cited_by") or []]
        linked_claims = [
            claim_id for claim_id, source_ids in claim_blocks.items() if source_ids.intersection(cited_by)
        ]
        source_ids = cited_by or [
            str(block.get("id"))
            for block in blocks.values()
            if block.get("type") == "equation"
            and block.get("page") == equation.get("page")
        ]
        formulas.append(
            {
                "equation_id": equation_id,
                "latex": equation.get("latex"),
                "image_path": equation.get("path"),
                "page": equation.get("page"),
                "bbox": equation.get("bbox"),
                "section_id": equation.get("section_id"),
                "context_before": normalize_text(str(equation.get("context_before") or "")),
                "context_after": normalize_text(str(equation.get("context_after") or "")),
                "caption": normalize_text(str(equation.get("caption") or "")),
                "is_poster_core_equation": equation_id == core_equation_id,
                "poster_explanation": (
                    (key_idea.get("equation") or {}).get("plain_language_explanation")
                    if equation_id == core_equation_id
                    else ""
                ),
                "linked_claim_ids": linked_claims,
                "sources": _source_records(source_ids, blocks),
            }
        )
    return formulas


def _claim_items(
    claim_evidence: dict[str, Any],
    blocks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for claim in claim_evidence.get("claims", []):
        evidence_items: list[dict[str, Any]] = []
        for evidence in claim.get("evidence") or []:
            source = evidence.get("source") or {}
            block_id = str(source.get("block_id") or "")
            evidence_items.append(
                {
                    "support_type": evidence.get("support_type"),
                    "strength": evidence.get("strength"),
                    "similarity": evidence.get("similarity"),
                    "source": _source_record(block_id, blocks, source) if block_id else None,
                }
            )
        claim_sources = claim.get("sources") or []
        result.append(
            {
                "claim_id": claim.get("claim_id"),
                "claim": claim.get("claim") or "",
                "verdict": claim.get("verdict"),
                "confidence": claim.get("confidence", 0.0),
                "limitations": claim.get("limitations") or [],
                "sources": _source_records(
                    [
                        str(source.get("block_id"))
                        for source in claim_sources
                        if source.get("block_id")
                    ],
                    blocks,
                    claim_sources,
                ),
                "evidence": evidence_items,
            }
        )
    return result


def _poster_coverage(
    poster_spec: dict[str, Any],
    key_idea: dict[str, Any],
    results: dict[str, Any],
    highlights: dict[str, Any],
    motivations: list[dict[str, Any]],
    contributions: list[dict[str, Any]],
    method_modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    panels = poster_spec.get("panels") or {}
    coverage: list[dict[str, Any]] = []
    for item in motivations:
        coverage.append(
            {
                "poster_panel": "motivation",
                "poster_item_id": item.get("id"),
                "report_section": "motivations",
                "report_item_id": item.get("id"),
                "text": item.get("text"),
            }
        )
    for item in contributions:
        coverage.append(
            {
                "poster_panel": "contributions",
                "poster_item_id": item.get("id"),
                "report_section": "contributions",
                "report_item_id": item.get("id"),
                "text": item.get("description"),
            }
        )
    if panels.get("method_overview") or method_modules:
        overview_panel = panels.get("method_overview") or {}
        overview_asset = overview_panel.get("asset") or {}
        overview_summary = overview_panel.get("summary") or {}
        coverage.append(
            {
                "poster_panel": "method_overview",
                "poster_item_id": overview_asset.get("id"),
                "report_section": "method_modules",
                "report_item_id": method_modules[0].get("id") if method_modules else None,
                "text": overview_summary.get("text", ""),
            }
        )
    if key_idea:
        coverage.append(
            {
                "poster_panel": "key_idea",
                "poster_item_id": key_idea.get("type"),
                "report_section": "key_idea",
                "report_item_id": "key-idea",
                "text": key_idea.get("headline"),
            }
        )
    if results:
        coverage.append(
            {
                "poster_panel": "experimental_results",
                "poster_item_id": (results.get("primary_asset") or {}).get("asset_id"),
                "report_section": "experimental_results",
                "report_item_id": "experimental-results",
                "text": results.get("result_headline"),
            }
        )
    for index, item in enumerate(highlights.get("highlights") or [], start=1):
        coverage.append(
            {
                "poster_panel": "highlights",
                "poster_item_id": item.get("evidence_id") or f"highlight-{index}",
                "report_section": "experimental_results",
                "report_item_id": item.get("claim_id"),
                "text": f"{item.get('primary_value', '')} {item.get('label', '')}".strip(),
            }
        )
    return coverage


def _augment_result_sources(
    results: dict[str, Any],
    blocks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = copy.deepcopy(results)
    payload["sources"] = _source_records(
        payload.get("source_block_ids") or [],
        blocks,
    )
    for metric in payload.get("key_metrics") or []:
        metric["sources"] = _source_records(
            metric.get("source_block_ids") or [],
            blocks,
        )
    for role in ("primary_asset", "secondary_asset"):
        asset = payload.get(role)
        if asset:
            asset["sources"] = _source_records(
                asset.get("source_block_ids") or [],
                blocks,
            )
    return payload


def _executive_summary(storyline: list[dict[str, Any]]) -> str:
    by_role = {item["role"]: item for item in storyline}
    parts = [
        by_role.get("research_problem", {}).get("summary"),
        by_role.get("method_design", {}).get("summary"),
        by_role.get("experimental_results", {}).get("summary"),
    ]
    return " ".join(str(part) for part in parts if part)


def compose_reading_report(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    method_graph_path: Path,
    asset_catalog_path: Path | None,
    selected_assets_path: Path | None,
    method_figure_map_path: Path | None,
    method_visual_plan_path: Path | None,
    key_idea_spec_path: Path | None,
    experimental_results_spec_path: Path | None,
    highlights_spec_path: Path | None,
    motivation_spec_path: Path | None,
    contribution_spec_path: Path | None,
    poster_spec_path: Path | None,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    method_graph = read_json(method_graph_path)
    catalog = _load_optional(asset_catalog_path)
    selected = _load_optional(selected_assets_path)
    method_map = _load_optional(method_figure_map_path)
    method_visual = _load_optional(method_visual_plan_path)
    key_idea = _load_optional(key_idea_spec_path)
    blocks = _block_index(paper_ir)
    assets = _asset_index(paper_ir)
    results = _augment_result_sources(
        _load_optional(experimental_results_spec_path),
        blocks,
    )
    highlights = _load_optional(highlights_spec_path)
    motivation = _load_optional(motivation_spec_path)
    contribution = _load_optional(contribution_spec_path)
    poster = _load_optional(poster_spec_path)

    storyline = _storyline(story, blocks)
    motivation_items = _motivation_items(motivation, blocks)
    contribution_items = _contribution_items(contribution, blocks)
    method_modules = _method_modules(method_graph, method_map, assets, blocks)
    overview_asset_id = str(method_map.get("overview_asset_id") or "")
    overview_asset = assets.get(overview_asset_id) or {}
    method_overview = (
        {
            "asset_id": overview_asset_id,
            "caption": overview_asset.get("caption") or "",
            "page": overview_asset.get("page"),
            "bbox": overview_asset.get("bbox"),
            "path": overview_asset.get("path"),
            "selection_basis": method_map.get("overview_selection_basis"),
        }
        if overview_asset_id and overview_asset
        else None
    )
    claims = _claim_items(evidence, blocks)
    formulas = _formula_items(
        paper_ir,
        key_idea,
        evidence.get("claims") or story.get("claims") or [],
        blocks,
    )
    coverage = _poster_coverage(
        poster,
        key_idea,
        results,
        highlights,
        motivation_items,
        contribution_items,
        method_modules,
    )

    referenced_block_ids: set[str] = set()
    for collection in (storyline, motivation_items, contribution_items, method_modules, formulas, claims):
        for item in collection:
            for source in item.get("sources") or []:
                if source.get("block_id"):
                    referenced_block_ids.add(str(source["block_id"]))
            for evidence_item in item.get("evidence") or []:
                source = evidence_item.get("source") or {}
                if source.get("block_id"):
                    referenced_block_ids.add(str(source["block_id"]))
    for metric in results.get("key_metrics") or []:
        referenced_block_ids.update(str(value) for value in metric.get("source_block_ids") or [])
    for asset_role in ("primary_asset", "secondary_asset"):
        referenced_block_ids.update(
            str(value) for value in (results.get(asset_role) or {}).get("source_block_ids") or []
        )
    referenced_block_ids.update(
        str(value) for value in key_idea.get("source_block_ids") or []
    )

    source_index = [
        _source_record(block_id, blocks)
        for block_id in sorted(
            (block_id for block_id in referenced_block_ids if block_id in blocks),
            key=lambda block_id: (
                int(blocks.get(block_id, {}).get("page") or 10**6),
                block_id,
            ),
        )
    ]
    source_index = _attach_source_assets(source_index, assets)
    source_index_payload = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir.get("paper_id"),
        "sources": source_index,
    }
    source_index_path = write_json(output_dir / "source_index.json", source_index_payload)

    report = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir.get("paper_id"),
        "metadata": paper_ir.get("metadata") or {},
        "source_pdf": (paper_ir.get("provenance") or {}).get("source_path"),
        "poster": {
            "available": bool(poster),
            "theme": poster.get("theme"),
            "poster_spec_path": str(poster_spec_path.resolve()) if poster_spec_path else None,
        },
        "executive_summary": _executive_summary(storyline),
        "storyline": storyline,
        "motivations": motivation_items,
        "contributions": contribution_items,
        "method_modules": method_modules,
        "method_overview": method_overview,
        "method_graph": {
            "selection_basis": method_graph.get("selection_basis"),
            "edges": method_graph.get("edges") or [],
            "visual_plan": method_visual,
            "selected_assets": selected,
        },
        "key_idea": key_idea,
        "formulas": formulas,
        "experimental_design": next(
            (item for item in storyline if item["role"] == "experimental_design"),
            {},
        ),
        "experimental_results": results,
        "highlights": highlights.get("highlights") or [],
        "claim_evidence": claims,
        "limitations": next(
            (item for item in storyline if item["role"] == "limitations"),
            {},
        ),
        "poster_coverage": coverage,
        "source_index_path": str(source_index_path.resolve()),
        "source_index": source_index,
        "asset_catalog": {
            "figures": len(catalog.get("figures") or paper_ir.get("figures") or []),
            "equations": len(catalog.get("equations") or paper_ir.get("equations") or []),
            "tables": len(catalog.get("tables") or paper_ir.get("tables") or []),
        },
        "generation": {
            "policy": "compose from validated upstream artifacts; never infer facts from poster pixels",
            "inferred_items_are_labeled": True,
        },
    }
    spec_path = write_json(output_dir / "reading_report_spec.json", report)
    return spec_path, source_index_path


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _source_badges(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return '<span class="source missing">No source</span>'
    return "".join(
        (
            f'<a class="source" href="#source-{_esc(source.get("block_id"))}">'
            f'Page {_esc(source.get("page"))} · {_esc(source.get("section") or "Source")} · '
            f'{_esc(source.get("block_id"))}</a>'
        )
        for source in sources
    )


def _resolve_asset_path(
    raw_path: str | None,
    paper_ir_dir: Path,
    output_dir: Path,
    prefix: str,
) -> str | None:
    if not raw_path:
        return None
    source = Path(raw_path)
    if not source.is_absolute():
        source = paper_ir_dir / source
    if not source.is_file():
        return None
    asset_dir = output_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{prefix}-{source.name}"
    target = asset_dir / target_name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return f"assets/{target_name}"


def _figure_html(
    path: str | None,
    caption: str,
    page: Any,
    asset_id: str,
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    copied = _resolve_asset_path(path, paper_ir_dir, output_dir, asset_id)
    if not copied:
        return ""
    return (
        f'<figure data-report-asset="{_esc(asset_id)}">'
        f'<img src="{_esc(copied)}" alt="{_esc(caption or asset_id)}">'
        f'<figcaption>{_esc(caption)} <span>Page {_esc(page)}</span></figcaption>'
        "</figure>"
    )


def _storyline_html(items: list[dict[str, Any]]) -> str:
    cards = []
    for item in items:
        if item.get("status") == "not_found" and not item.get("summary"):
            continue
        inferred = '<span class="flag">Inferred</span>' if item.get("inferred") else ""
        cards.append(
            '<article class="story-card">'
            f'<h3>{_esc(item.get("label"))}{inferred}</h3>'
            f'<p>{_esc(item.get("summary"))}</p>'
            f'<div class="sources">{_source_badges(item.get("sources") or [])}</div>'
            "</article>"
        )
    return "".join(cards)


def _list_section(items: list[dict[str, Any]], kind: str) -> str:
    cards = []
    for item in items:
        title = item.get("short_title") if kind == "contribution" else item.get("type")
        text = item.get("description") if kind == "contribution" else item.get("text")
        details = ""
        if kind == "contribution":
            detail_items = [
                ("Object", item.get("innovation_object")),
                ("Mechanism", item.get("mechanism")),
                ("Purpose", item.get("purpose")),
            ]
            details = "<dl>" + "".join(
                f"<dt>{_esc(label)}</dt><dd>{_esc(value)}</dd>"
                for label, value in detail_items
                if value
            ) + "</dl>"
        cards.append(
            '<article class="detail-card">'
            f'<h3>{_esc(title)}</h3><p>{_esc(text)}</p>{details}'
            f'<div class="sources">{_source_badges(item.get("sources") or [])}</div>'
            "</article>"
        )
    return "".join(cards) or '<p class="empty">No validated items were extracted.</p>'


def _method_html(
    modules: list[dict[str, Any]],
    overview: dict[str, Any] | None,
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    rendered = []
    if overview:
        rendered.append(
            '<article class="method-overview-report">'
            "<h3>Complete Method Overview</h3>"
            + _figure_html(
                overview.get("path"),
                str(overview.get("caption") or ""),
                overview.get("page"),
                str(overview.get("asset_id") or "method-overview"),
                paper_ir_dir,
                output_dir,
            )
            + "</article>"
        )
    for module in modules:
        figures = "".join(
            _figure_html(
                figure.get("path"),
                str(figure.get("caption") or ""),
                figure.get("page"),
                str(figure.get("asset_id") or "method"),
                paper_ir_dir,
                output_dir,
            )
            for figure in module.get("figures") or []
        )
        rendered.append(
            '<article class="method-module">'
            f'<div class="step">{_esc(module.get("order"))}</div>'
            f'<div class="method-copy"><h3>{_esc(module.get("name"))}</h3>'
            f'<p><strong>Purpose.</strong> {_esc(module.get("purpose"))}</p>'
            f'<p><strong>Innovation.</strong> {_esc(module.get("innovation"))}</p>'
            f'<div class="sources">{_source_badges(module.get("sources") or [])}</div></div>'
            f'<div class="method-assets">{figures}</div>'
            "</article>"
        )
    return "".join(rendered) or '<p class="empty">No sourced method modules were reconstructed.</p>'


def _formula_html(
    formulas: list[dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    cards = []
    for formula in formulas:
        image = _figure_html(
            formula.get("image_path"),
            formula.get("caption") or formula.get("equation_id") or "",
            formula.get("page"),
            str(formula.get("equation_id") or "equation"),
            paper_ir_dir,
            output_dir,
        )
        latex = (
            f'<pre class="latex">{_esc(formula.get("latex"))}</pre>'
            if formula.get("latex")
            else ""
        )
        core = '<span class="flag core">Poster core equation</span>' if formula.get("is_poster_core_equation") else ""
        context = formula.get("poster_explanation") or formula.get("context_after") or formula.get("context_before")
        provenance = (
            '<div class="sources">'
            f'<span class="source">Page {_esc(formula.get("page"))} · '
            f'{_esc(formula.get("equation_id"))} · bbox {_esc(formula.get("bbox"))}</span>'
            f'{_source_badges(formula.get("sources") or []) if formula.get("sources") else ""}'
            "</div>"
        )
        cards.append(
            '<article class="formula-card">'
            f'<h3>{_esc(formula.get("equation_id"))}{core}</h3>{image or latex}{latex if image else ""}'
            f'<p>{_esc(context)}</p>'
            f"{provenance}"
            "</article>"
        )
    return "".join(cards) or '<p class="empty">No equations were extracted from this paper.</p>'


def _key_idea_html(key_idea: dict[str, Any]) -> str:
    if not key_idea:
        return '<p class="empty">No Poster Key Idea specification was available.</p>'
    items = "".join(
        f'<li><strong>{_esc(item.get("label"))}</strong> {_esc(item.get("text"))}</li>'
        for item in (key_idea.get("visual") or {}).get("items") or []
    )
    inferred = '<span class="flag">Inferred</span>' if key_idea.get("inferred") else ""
    equation = key_idea.get("equation") or {}
    explanation = str(equation.get("plain_language_explanation") or "")
    if re.search(r"[\\$]|\bmathbb\b|\boverline\b", explanation):
        explanation = (
            "See the Formula Notebook for the original equation crop, "
            "notation, and source context."
        )
    equation_note = (
        f'<p><strong>Core equation:</strong> {_esc(equation.get("equation_id"))} — '
        f'{_esc(explanation)}</p>'
        if equation.get("equation_id")
        else "<p><strong>Core equation:</strong> none selected; the insight is not formula-centered.</p>"
    )
    return (
        '<article class="key-idea-card">'
        f'<h3>{_esc(key_idea.get("headline"))}{inferred}</h3>'
        f'<p>{_esc(key_idea.get("core_insight"))}</p>'
        f'{"<ul>" + items + "</ul>" if items else ""}'
        f'{equation_note}<p class="takeaway">{_esc(key_idea.get("takeaway"))}</p>'
        "</article>"
    )


def _results_html(
    results: dict[str, Any],
    highlights: list[dict[str, Any]],
    assets: dict[str, dict[str, Any]],
    paper_ir_dir: Path,
    output_dir: Path,
) -> str:
    metrics = "".join(
        '<article class="metric">'
        f'<strong>{_esc(item.get("value"))}</strong>'
        f'<span>{_esc(item.get("metric"))} · {_esc(item.get("dataset"))}</span>'
        f'<small>vs {_esc(item.get("baseline"))} ({_esc(item.get("baseline_value"))}), '
        f'{_esc(item.get("delta"))}; {_esc(item.get("evaluation_condition"))}</small>'
        "</article>"
        for item in results.get("key_metrics") or []
    )
    highlight_cards = "".join(
        '<article class="highlight">'
        f'<strong>{_esc(item.get("primary_value"))}</strong>'
        f'<span>{_esc(item.get("label"))}</span>'
        f'<small>{_esc(item.get("context"))}</small>'
        "</article>"
        for item in highlights
    )
    result_assets = []
    for role in ("primary_asset", "secondary_asset"):
        item = results.get(role) or {}
        if not item:
            continue
        asset_id = str(item.get("asset_id") or item.get("table_id") or item.get("figure_id") or role)
        source_asset = assets.get(asset_id) or {}
        path = item.get("display_path") or item.get("path") or source_asset.get("path")
        result_assets.append(
            _figure_html(
                path,
                str(item.get("caption") or source_asset.get("caption") or ""),
                item.get("page") or source_asset.get("page"),
                f"result-{asset_id}",
                paper_ir_dir,
                output_dir,
            )
        )
        focus_table = item.get("focus_table") or {}
        if focus_table.get("headers") and focus_table.get("rows"):
            headers = "".join(f"<th>{_esc(value)}</th>" for value in focus_table["headers"])
            rows = "".join(
                "<tr>" + "".join(f"<td>{_esc(value)}</td>" for value in row.get("cells") or []) + "</tr>"
                for row in focus_table["rows"]
            )
            result_assets.append(
                f'<div class="table-wrap"><table><thead><tr>{headers}</tr></thead>'
                f"<tbody>{rows}</tbody></table></div>"
            )
    return (
        f'<p class="headline">{_esc(results.get("result_headline"))}</p>'
        f'<div class="metric-grid">{metrics}</div>'
        f'<div class="highlight-grid">{highlight_cards}</div>'
        f'<div class="result-assets">{"".join(result_assets)}</div>'
        f'<p class="condition">{_esc(results.get("condition_note"))}</p>'
    )


def _claims_html(claims: list[dict[str, Any]]) -> str:
    cards = []
    for item in claims:
        evidence = "".join(
            '<li>'
            f'<strong>{_esc(ev.get("strength") or ev.get("support_type"))}</strong> '
            f'{_esc((ev.get("source") or {}).get("quote"))}'
            f'<div class="sources">{_source_badges([ev["source"]] if ev.get("source") else [])}</div>'
            "</li>"
            for ev in item.get("evidence") or []
        )
        limitations = "".join(f"<li>{_esc(value)}</li>" for value in item.get("limitations") or [])
        cards.append(
            '<article class="claim-card">'
            f'<header><h3>{_esc(item.get("claim_id"))}</h3>'
            f'<span class="verdict">{_esc(item.get("verdict"))}</span></header>'
            f'<p>{_esc(item.get("claim"))}</p>'
            f'<div class="sources">{_source_badges(item.get("sources") or [])}</div>'
            f'<h4>Supporting evidence</h4><ul>{evidence or "<li>No linked evidence.</li>"}</ul>'
            f'{"<h4>Caveats</h4><ul>" + limitations + "</ul>" if limitations else ""}'
            "</article>"
        )
    return "".join(cards) or '<p class="empty">No Claim–Evidence records were available.</p>'


def _sources_html(sources: list[dict[str, Any]]) -> str:
    return "".join(
        '<article class="source-row" '
        f'id="source-{_esc(source.get("block_id"))}">'
        f'<div><strong>Page {_esc(source.get("page"))}</strong>'
        f'<span>{_esc(source.get("section"))}</span>'
        f'<code>{_esc(source.get("block_id"))}</code></div>'
        f'<p>{_esc(source.get("quote"))}</p>'
        "</article>"
        for source in sources
    )


def _markdown_sources(sources: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"p.{source.get('page')} {source.get('section') or ''} [{source.get('block_id')}]"
        for source in sources
    )


def _render_markdown(report: dict[str, Any]) -> str:
    metadata = report.get("metadata") or {}
    lines = [
        f"# {metadata.get('title') or report.get('paper_id')}",
        "",
        ", ".join(metadata.get("authors") or []),
        "",
        "## Executive Summary",
        "",
        str(report.get("executive_summary") or ""),
        "",
        "## Paper Storyline",
        "",
    ]
    for item in report.get("storyline") or []:
        if item.get("summary"):
            status = " (inferred)" if item.get("inferred") else ""
            lines.extend(
                [
                    f"### {item.get('label')}{status}",
                    "",
                    str(item.get("summary")),
                    "",
                    f"Source: {_markdown_sources(item.get('sources') or [])}",
                    "",
                ]
            )
    lines.extend(["## Motivation", ""])
    for item in report.get("motivations") or []:
        lines.append(f"- {item.get('text')} — {_markdown_sources(item.get('sources') or [])}")
    lines.extend(["", "## Contributions", ""])
    for item in report.get("contributions") or []:
        lines.extend(
            [
                f"### {item.get('short_title')}",
                "",
                str(item.get("description") or ""),
                "",
                f"- Mechanism: {item.get('mechanism') or ''}",
                f"- Purpose: {item.get('purpose') or ''}",
                f"- Source: {_markdown_sources(item.get('sources') or [])}",
                "",
            ]
        )
    lines.extend(["## Method Modules", ""])
    for module in report.get("method_modules") or []:
        lines.extend(
            [
                f"### {module.get('order')}. {module.get('name')}",
                "",
                f"- Purpose: {module.get('purpose') or ''}",
                f"- Innovation: {module.get('innovation') or ''}",
                f"- Figures: {', '.join(module.get('figure_ids') or [])}",
                f"- Source: {_markdown_sources(module.get('sources') or [])}",
                "",
            ]
        )
    lines.extend(["## Formulas", ""])
    for formula in report.get("formulas") or []:
        lines.extend(
            [
                f"### {formula.get('equation_id')}",
                "",
                f"```latex\n{formula.get('latex') or ''}\n```",
                "",
                str(formula.get("poster_explanation") or formula.get("context_after") or ""),
                "",
                f"Source: page {formula.get('page')}, bbox {formula.get('bbox')}",
                "",
            ]
        )
    results = report.get("experimental_results") or {}
    lines.extend(["## Experimental Results", "", str(results.get("result_headline") or ""), ""])
    for metric in results.get("key_metrics") or []:
        lines.append(
            f"- {metric.get('value')} {metric.get('metric')} on {metric.get('dataset')}; "
            f"baseline {metric.get('baseline')}={metric.get('baseline_value')}; "
            f"delta {metric.get('delta')}; {metric.get('evaluation_condition')}."
        )
    lines.extend(["", "## Claim–Evidence Matrix", ""])
    for claim in report.get("claim_evidence") or []:
        lines.extend(
            [
                f"### {claim.get('claim_id')} — {claim.get('verdict')}",
                "",
                str(claim.get("claim") or ""),
                "",
                f"Claim source: {_markdown_sources(claim.get('sources') or [])}",
                "",
            ]
        )
        for evidence in claim.get("evidence") or []:
            source = evidence.get("source") or {}
            lines.append(
                f"- {evidence.get('strength') or evidence.get('support_type')}: "
                f"{source.get('quote') or ''} "
                f"(p.{source.get('page')}, {source.get('block_id')})"
            )
        lines.append("")
    lines.extend(["## Source Index", ""])
    for source in report.get("source_index") or []:
        lines.append(
            f"- p.{source.get('page')} {source.get('section') or ''} "
            f"[{source.get('block_id')}]: {source.get('quote') or ''}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _browser_export(
    html_path: Path,
    pdf_path: Path,
    metrics_path: Path,
) -> tuple[bool, str | None]:
    runtime = _find_runtime()
    if not all(runtime.values()):
        return False, "Node.js, Playwright, or a Chromium browser was not detected."
    script = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "paper-reading-report-render"
        / "scripts"
        / "render_browser.cjs"
    )
    command = [
        str(runtime["node"]),
        str(script),
        str(html_path.resolve()),
        str(pdf_path.resolve()),
        str(metrics_path.resolve()),
        str(runtime["browser"]),
        str(runtime["node_modules"]),
    ]
    completed = subprocess.run(
        command,
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Browser export failed.").strip()
        return False, message[-1600:]
    return True, None


def render_reading_report(
    report_spec_path: Path,
    paper_ir_path: Path,
    output_dir: Path,
    export_pdf: bool = True,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = read_json(report_spec_path)
    paper_ir = read_json(paper_ir_path)
    assets = _asset_index(paper_ir)
    template_root = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "paper-reading-report-render"
        / "assets"
        / "report-template"
    )
    template = (template_root / "reading-report.html").read_text(encoding="utf-8")
    style = (template_root / "reading-report.css").read_text(encoding="utf-8")
    paper_ir_dir = paper_ir_path.parent
    metadata = report.get("metadata") or {}
    results = report.get("experimental_results") or {}
    limitations = report.get("limitations") or {}
    limitation_html = (
        f'<p>{_esc(limitations.get("summary"))}</p>'
        f'<div class="sources">{_source_badges(limitations.get("sources") or [])}</div>'
        if limitations.get("summary")
        else '<p class="empty">No explicit limitation statement was found.</p>'
    )
    content = {
        "STYLE": style,
        "TITLE": _esc(metadata.get("title") or report.get("paper_id")),
        "AUTHORS": _esc(", ".join(metadata.get("authors") or [])),
        "META": _esc(
            " · ".join(
                str(value)
                for value in (metadata.get("year"), metadata.get("url"))
                if value
            )
        ),
        "EXECUTIVE_SUMMARY": _esc(report.get("executive_summary")),
        "STORYLINE": _storyline_html(report.get("storyline") or []),
        "MOTIVATIONS": _list_section(report.get("motivations") or [], "motivation"),
        "CONTRIBUTIONS": _list_section(report.get("contributions") or [], "contribution"),
        "KEY_IDEA": _key_idea_html(report.get("key_idea") or {}),
        "METHOD_MODULES": _method_html(
            report.get("method_modules") or [],
            report.get("method_overview"),
            paper_ir_dir,
            output_dir,
        ),
        "FORMULAS": _formula_html(report.get("formulas") or [], paper_ir_dir, output_dir),
        "EXPERIMENTAL_DESIGN": _storyline_html(
            [report.get("experimental_design") or {}]
        ),
        "EXPERIMENTAL_RESULTS": _results_html(
            results,
            report.get("highlights") or [],
            assets,
            paper_ir_dir,
            output_dir,
        ),
        "CLAIMS": _claims_html(report.get("claim_evidence") or []),
        "LIMITATIONS": limitation_html,
        "SOURCES": _sources_html(report.get("source_index") or []),
    }
    rendered = template
    for key, value in content.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    html_path = output_dir / "reading_report.html"
    html_path.write_text(rendered, encoding="utf-8", newline="\n")
    markdown_path = output_dir / "reading_report.md"
    markdown_path.write_text(_render_markdown(report), encoding="utf-8", newline="\n")
    pdf_path = output_dir / "reading_report.pdf"
    metrics_path = output_dir / "reading_report_render_metrics.json"
    exported = False
    error = None
    if export_pdf:
        exported, error = _browser_export(html_path, pdf_path, metrics_path)
    bundle = {
        "schema_version": "1.0.0",
        "status": "passed" if (exported or not export_pdf) else "passed_with_warnings",
        "html_path": str(html_path.resolve()),
        "markdown_path": str(markdown_path.resolve()),
        "pdf_path": str(pdf_path.resolve()) if pdf_path.is_file() else None,
        "metrics_path": str(metrics_path.resolve()) if metrics_path.is_file() else None,
        "pdf_requested": export_pdf,
        "export_error": error,
    }
    bundle_path = write_json(output_dir / "reading_report_render_bundle.json", bundle)
    return html_path, bundle_path


def _issue(
    code: str,
    message: str,
    return_to: str,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "return_to": return_to,
    }


def validate_reading_report(
    report_spec_path: Path,
    render_bundle_path: Path,
    output_dir: Path,
) -> Path:
    report = read_json(report_spec_path)
    bundle = read_json(render_bundle_path)
    issues: list[dict[str, Any]] = []
    source_ids = {
        str(source.get("block_id"))
        for source in report.get("source_index") or []
        if source.get("block_id")
    }

    for section in ("storyline", "motivations", "contributions", "method_modules"):
        for item in report.get(section) or []:
            asserted = bool(
                item.get("summary")
                or item.get("text")
                or item.get("description")
                or item.get("innovation")
            )
            if asserted and not item.get("sources"):
                issues.append(
                    _issue(
                        "REPORT_SOURCE_MISSING",
                        f"{section} item {item.get('id') or item.get('role')} has no source.",
                        "paper-reading-report-compose",
                    )
                )
            for source in item.get("sources") or []:
                if str(source.get("block_id")) not in source_ids:
                    issues.append(
                        _issue(
                            "REPORT_SOURCE_INDEX_DANGLING",
                            f"{source.get('block_id')} is not present in source_index.",
                            "paper-reading-report-compose",
                        )
                    )

    for formula in report.get("formulas") or []:
        if not formula.get("page") or (
            not formula.get("bbox") and not formula.get("latex")
        ):
            issues.append(
                _issue(
                    "REPORT_FORMULA_PROVENANCE_MISSING",
                    f"{formula.get('equation_id')} lacks page or bbox.",
                    "paper-reading-report-compose",
                )
            )
        if not formula.get("image_path") and not formula.get("latex"):
            issues.append(
                _issue(
                    "REPORT_FORMULA_CONTENT_MISSING",
                    f"{formula.get('equation_id')} has neither an original crop nor LaTeX.",
                    "paper-reading-report-compose",
                )
            )

    for claim in report.get("claim_evidence") or []:
        if not claim.get("sources"):
            issues.append(
                _issue(
                    "REPORT_CLAIM_SOURCE_MISSING",
                    f"{claim.get('claim_id')} lacks a Claim source.",
                    "paper-reading-report-compose",
                )
            )
        if claim.get("verdict") in {"supported", "partially_supported"} and not claim.get("evidence"):
            issues.append(
                _issue(
                    "REPORT_CLAIM_EVIDENCE_MISSING",
                    f"{claim.get('claim_id')} is {claim.get('verdict')} without linked evidence.",
                    "paper-reading-report-compose",
                )
            )

    for item in report.get("poster_coverage") or []:
        if not item.get("report_section"):
            issues.append(
                _issue(
                    "REPORT_POSTER_COVERAGE_MISSING",
                    f"Poster item {item.get('poster_item_id')} has no report mapping.",
                    "paper-reading-report-compose",
                )
            )

    key_idea = report.get("key_idea") or {}
    for block_id in key_idea.get("source_block_ids") or []:
        if str(block_id) not in source_ids:
            issues.append(
                _issue(
                    "REPORT_KEY_IDEA_SOURCE_DANGLING",
                    f"Key Idea source {block_id} is not present in source_index.",
                    "paper-reading-report-compose",
                )
            )

    results = report.get("experimental_results") or {}
    result_records = list(results.get("key_metrics") or [])
    result_records.extend(
        item
        for item in (results.get("primary_asset"), results.get("secondary_asset"))
        if item
    )
    for item in result_records:
        for block_id in item.get("source_block_ids") or []:
            if str(block_id) not in source_ids:
                issues.append(
                    _issue(
                        "REPORT_RESULT_SOURCE_DANGLING",
                        f"Experimental result source {block_id} is not present in source_index.",
                        "paper-reading-report-compose",
                    )
                )

    for key in ("html_path", "markdown_path"):
        path = bundle.get(key)
        if not path or not Path(path).is_file():
            issues.append(
                _issue(
                    "REPORT_RENDER_OUTPUT_MISSING",
                    f"{key} was not produced.",
                    "paper-reading-report-render",
                )
            )
    if bundle.get("pdf_requested") and not bundle.get("pdf_path"):
        issues.append(
            _issue(
                "REPORT_PDF_EXPORT_FAILED",
                str(bundle.get("export_error") or "Reading report PDF was not produced."),
                "paper-reading-report-render",
            )
        )

    metrics: dict[str, Any] = {}
    metrics_path = bundle.get("metrics_path")
    if metrics_path and Path(metrics_path).is_file():
        metrics = read_json(Path(metrics_path))
        if metrics.get("missing_images"):
            issues.append(
                _issue(
                    "REPORT_IMAGE_MISSING",
                    f"Missing images: {metrics['missing_images']}",
                    "paper-reading-report-render",
                )
            )
        if metrics.get("horizontal_overflow"):
            issues.append(
                _issue(
                    "REPORT_HORIZONTAL_OVERFLOW",
                    "Reading report contains horizontally overflowing elements.",
                    "paper-reading-report-render",
                )
            )
        min_font = metrics.get("min_font_px")
        if isinstance(min_font, (int, float)) and min_font < 10:
            issues.append(
                _issue(
                    "REPORT_FONT_TOO_SMALL",
                    f"Minimum rendered font is {min_font}px.",
                    "paper-reading-report-render",
                )
            )

    errors = [issue for issue in issues if issue["severity"] == "error"]
    status = "failed" if errors else ("passed_with_warnings" if issues else "passed")
    qa = {
        "schema_version": "1.0.0",
        "status": status,
        "checks": {
            "traceability": not any(issue["code"].endswith("SOURCE_MISSING") for issue in issues),
            "source_index_integrity": not any(
                issue["code"] == "REPORT_SOURCE_INDEX_DANGLING" for issue in issues
            ),
            "formula_provenance": not any(
                issue["code"].startswith("REPORT_FORMULA_") for issue in issues
            ),
            "poster_coverage": not any(
                issue["code"] == "REPORT_POSTER_COVERAGE_MISSING" for issue in issues
            ),
            "render_outputs": not any(
                issue["code"] in {"REPORT_RENDER_OUTPUT_MISSING", "REPORT_PDF_EXPORT_FAILED"}
                for issue in issues
            ),
            "visual_integrity": not any(
                issue["code"]
                in {"REPORT_IMAGE_MISSING", "REPORT_HORIZONTAL_OVERFLOW", "REPORT_FONT_TOO_SMALL"}
                for issue in issues
            ),
        },
        "issues": issues,
        "return_to": errors[0]["return_to"] if errors else None,
        "metrics": metrics,
    }
    return write_json(output_dir / "reading_report_qa.json", qa)


def build_reading_report(
    *,
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    method_graph_path: Path,
    asset_catalog_path: Path | None,
    selected_assets_path: Path | None,
    method_figure_map_path: Path | None,
    method_visual_plan_path: Path | None,
    key_idea_spec_path: Path | None,
    experimental_results_spec_path: Path | None,
    highlights_spec_path: Path | None,
    motivation_spec_path: Path | None,
    contribution_spec_path: Path | None,
    poster_spec_path: Path | None,
    output_dir: Path,
    export_pdf: bool = True,
) -> tuple[Path, Path, Path]:
    spec_path, _ = compose_reading_report(
        paper_ir_path,
        story_path,
        evidence_path,
        method_graph_path,
        asset_catalog_path,
        selected_assets_path,
        method_figure_map_path,
        method_visual_plan_path,
        key_idea_spec_path,
        experimental_results_spec_path,
        highlights_spec_path,
        motivation_spec_path,
        contribution_spec_path,
        poster_spec_path,
        output_dir,
    )
    _, bundle_path = render_reading_report(
        spec_path,
        paper_ir_path,
        output_dir,
        export_pdf=export_pdf,
    )
    qa_path = validate_reading_report(spec_path, bundle_path, output_dir)
    return spec_path, bundle_path, qa_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a sourced paper reading report.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    spec, bundle, qa = build_reading_report(
        paper_ir_path=run_dir / "01-ingestion" / "paper_ir.json",
        story_path=run_dir / "02-analysis" / "paper_story.json",
        evidence_path=run_dir / "02-analysis" / "claim_evidence.json",
        method_graph_path=run_dir / "02-analysis" / "method_graph.json",
        asset_catalog_path=run_dir / "03-assets" / "asset_catalog.json",
        selected_assets_path=run_dir / "03-assets" / "selected_assets.json",
        method_figure_map_path=run_dir / "03-assets" / "method_figure_map.json",
        method_visual_plan_path=run_dir / "04-poster" / "method_visual_plan.json",
        key_idea_spec_path=run_dir / "04-poster" / "key_idea_spec.json",
        experimental_results_spec_path=run_dir / "04-poster" / "experimental_results_spec.json",
        highlights_spec_path=run_dir / "04-poster" / "highlights_spec.json",
        motivation_spec_path=run_dir / "04-poster" / "motivation_spec.json",
        contribution_spec_path=run_dir / "04-poster" / "contribution_spec.json",
        poster_spec_path=run_dir / "04-poster" / "poster_spec.json",
        output_dir=run_dir / "06-reading-report",
        export_pdf=not args.no_pdf,
    )
    result = read_json(qa)
    print(result["status"])
    print(spec)
    print(bundle)
    return 0 if result["status"] in {"passed", "passed_with_warnings"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
