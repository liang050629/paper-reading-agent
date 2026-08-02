from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import normalize_text, read_json, sentences, source_ref, write_json
from .method_figures import MODULE_MATCH_THRESHOLD

MATCH_KIND_WEIGHT = {
    "explicit_figure_reference": 5.0,
    "exact_unique_alias": 4.0,
    "exact_alias": 3.0,
    "parent_module_structure": 3.0,
    "distinctive_terms": 2.0,
    "contextual_overlap": 0.5,
    "complete_overview": 0.25,
}


def _clip_words(value: str, limit: int) -> str:
    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", value or "")
    while len(words) > limit:
        words.pop()
    while words and words[-1].lower() in {
        "a",
        "an",
        "and",
        "by",
        "for",
        "in",
        "of",
        "or",
        "the",
        "to",
        "with",
    }:
        words.pop()
    return " ".join(words)


def _clean_method_card_text(value: str, limit: int = 28) -> str:
    text = normalize_text(value)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(
        r"\b(?:as\s+)?(?:shown|illustrated|depicted|presented)\s+in\s+"
        r"(?:fig(?:ure)?|table)\.?\s*[A-Za-z0-9().-]+",
        " ",
        text,
        flags=re.I,
    )
    proposed_clause = re.search(r"\bour\s+proposed\s+(.+)", text, re.I)
    if proposed_clause:
        text = proposed_clause.group(1)
    text = re.sub(
        r"^\s*(?:inspired\s+by.+?,\s*)?"
        r"(?:in\s+contrast\s+to.+?,\s*)?(?:to\s+address.+?,\s*)?"
        r"(?:we\s+(?:then\s+)?(?:propose|introduce|design|develop|"
        r"investigate|apply|use|compute)\s+|"
        r"our\s+proposed\s+)",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bwe\s+(?:then\s+)?(?:propose|introduce|design|develop|"
        r"investigate|apply|use|compute)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bour\s+proposed\s+", "", text, flags=re.I)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = normalize_text(text).strip(" ,;:-")
    clipped = _clip_words(text, limit)
    if not clipped:
        return ""
    return clipped[0].upper() + clipped[1:] + "."


def _mechanism_flow(node: dict[str, Any]) -> dict[str, Any]:
    raw = normalize_text(
        str(node.get("purpose") or node.get("innovation") or node.get("name") or "")
    )
    purpose_match = re.match(
        r"^\s*to\s+(.+?),\s*(?:we\s+|the\s+method\s+|the\s+module\s+)?(.+)",
        raw,
        re.I,
    )
    purpose = ""
    operation_source = raw
    if purpose_match:
        purpose = _clip_words(purpose_match.group(1), 12)
        operation_source = purpose_match.group(2)
    else:
        trailing_purpose = re.search(
            r"(.+?)\s+(?:so\s+that|thereby)\s+(.+)",
            raw,
            re.I,
        )
        if trailing_purpose:
            operation_source = trailing_purpose.group(1)
            purpose = _clip_words(trailing_purpose.group(2), 12)

    operation = _clean_method_card_text(operation_source, 18)
    if not operation:
        operation = _clean_method_card_text(raw, 18)
    stages = [
        {
            "label": "Mechanism",
            "text": operation.rstrip("."),
        }
    ]
    if purpose:
        purpose_text = purpose[0].upper() + purpose[1:] if purpose else ""
        if purpose_text.lower() not in operation.lower():
            stages.append({"label": "Purpose", "text": purpose_text})
    return {
        "visual_type": "mechanism_flow",
        "stages": stages,
    }


def _mapping_value(mapping: dict[str, Any]) -> float:
    return float(mapping.get("score") or 0) * MATCH_KIND_WEIGHT.get(
        str(mapping.get("match_kind") or "contextual_overlap"),
        0.5,
    )


def _asset_number(asset_id: str) -> int:
    match = re.search(r"(\d+)(?!.*\d)", asset_id)
    return int(match.group(1)) if match else 10**6


def _dedicated_targets(
    graph: dict[str, Any],
    figure_map: dict[str, Any],
) -> list[str]:
    node_order = {
        node["id"]: int(node.get("order") or 10**6)
        for node in graph.get("nodes", [])
    }
    best: dict[str, float] = {}
    for record in figure_map.get("records", []):
        if record.get("role") not in {
            "method_module",
            "mechanism",
            "mechanism_analysis",
        }:
            continue
        for mapping in record.get("module_mappings", []):
            if mapping.get("match_kind") not in {
                "explicit_figure_reference",
                "exact_unique_alias",
                "exact_alias",
                "parent_module_structure",
                "distinctive_terms",
            }:
                continue
            module_id = str(mapping.get("module_id") or "")
            if module_id:
                best[module_id] = max(best.get(module_id, 0.0), _mapping_value(mapping))
    return [
        module_id
        for module_id, _ in sorted(
            best.items(),
            key=lambda item: (node_order.get(item[0], 10**6), -item[1]),
        )
    ][:4]


def _experiment_strip(paper_ir: dict[str, Any]) -> list[dict[str, Any]]:
    categories = {
        "datasets": ("dataset", "cohort", "database", "benchmark"),
        "baselines": ("baseline", "compare with", "comparison method"),
        "metrics": ("metric", "dice", "accuracy", "auc", "f1", "psnr", "ssim", "hd95"),
        "protocol": (
            "training",
            "optimizer",
            "learning rate",
            "batch size",
            "split",
            "cross-validation",
            "calibration images",
            "gpu",
            "epoch",
            "steps",
            "momentum",
            "number of experts",
        ),
    }
    results: list[dict[str, Any]] = []
    used_texts: set[str] = set()

    def matches(sentence: str, term: str) -> bool:
        if re.fullmatch(r"[a-z0-9-]{1,4}", term):
            return bool(re.search(rf"\b{re.escape(term)}\b", sentence))
        return term in sentence

    for category, terms in categories.items():
        found = None
        for block in paper_ir.get("blocks", []):
            section = (
                f"{block.get('section_title') or ''} "
                f"{block.get('section_id') or ''}"
            ).lower()
            if not any(term in section for term in ("experiment", "evaluation", "setup", "dataset")):
                continue
            for sentence in sentences(str(block.get("text") or "")):
                lowered = sentence.lower()
                if len(sentence.split()) < 4:
                    continue
                if any(matches(lowered, term) for term in terms):
                    normalized = normalize_text(sentence)
                    if normalized in used_texts:
                        continue
                    found = {
                        "kind": category,
                        "text": normalized,
                        "sources": [source_ref(block)],
                    }
                    break
            if found:
                break
        if found:
            results.append(found)
            used_texts.add(found["text"])
    return results


def _asset_record(figure_map: dict[str, Any], asset_id: str) -> dict[str, Any] | None:
    return next(
        (
            record
            for record in figure_map.get("records", [])
            if record.get("asset_id") == asset_id
        ),
        None,
    )


def _greedy_details(
    graph: dict[str, Any],
    figure_map: dict[str, Any],
    already_covered: set[str],
    excluded_asset_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    remaining = {node["id"] for node in graph.get("nodes", [])} - already_covered
    selected: list[dict[str, Any]] = []
    excluded_asset_ids = excluded_asset_ids or set()
    candidates = [
        record
        for record in figure_map.get("records", [])
        if record.get("role")
        in {
            "method_overview",
            "method_module",
            "mechanism",
            "mechanism_analysis",
        }
        and str(record.get("asset_id") or "") not in excluded_asset_ids
    ]
    while remaining and candidates and len(selected) < 4:
        winner = max(
            candidates,
            key=lambda record: sum(
                _mapping_value(mapping)
                for mapping in record.get("module_mappings", [])
                if mapping["module_id"] in remaining
            ),
        )
        covered = {
            mapping["module_id"]
            for mapping in winner.get("module_mappings", [])
            if mapping["module_id"] in remaining
            and mapping["score"] >= MODULE_MATCH_THRESHOLD
        }
        if not covered:
            break
        selected.append(
            {
                **winner,
                "_selected_module_ids": [
                    mapping["module_id"]
                    for mapping in winner.get("module_mappings", [])
                    if mapping["module_id"] in covered
                ],
            }
        )
        remaining -= covered
        candidates.remove(winner)
    return selected


def _dedicated_module_details(
    graph: dict[str, Any],
    figure_map: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_by_asset: dict[str, dict[str, Any]] = {}
    candidates = [
        record
        for record in figure_map.get("records", [])
        if record.get("role")
        in {"method_module", "mechanism", "mechanism_analysis"}
    ]
    for node in sorted(
        graph.get("nodes", []),
        key=lambda item: int(item.get("order") or 10**6),
    ):
        if len(selected_by_asset) >= 4:
            break
        node_id = str(node.get("id") or "")
        ranked: list[tuple[float, dict[str, Any]]] = []
        for record in candidates:
            mapping = next(
                (
                    item
                    for item in record.get("module_mappings", [])
                    if item.get("module_id") == node_id
                    and item.get("score", 0) >= MODULE_MATCH_THRESHOLD
                ),
                None,
            )
            if not mapping:
                continue
            strong_mappings = [
                item
                for item in record.get("module_mappings", [])
                if item.get("score", 0) >= MODULE_MATCH_THRESHOLD
            ]
            score = _mapping_value(mapping)
            if node_id in set(record.get("exclusive_alias_owner_ids", [])):
                score += 6.0
            if len(strong_mappings) == 1:
                score += 2.0
            else:
                score -= 0.75 * (len(strong_mappings) - 1)
            if record.get("focus_subfigure_labels"):
                score += 1.0
            ranked.append((score, record))
        if not ranked:
            continue
        _, winner = max(
            ranked,
            key=lambda item: (
                item[0],
                -_asset_number(str(item[1].get("asset_id") or "")),
            ),
        )
        asset_id = str(winner.get("asset_id") or "")
        if asset_id in selected_by_asset:
            selected_by_asset[asset_id]["_selected_module_ids"].append(node_id)
        else:
            selected_by_asset[asset_id] = {
                **winner,
                "_selected_module_ids": [node_id],
            }

    # A formal method section can group several independently illustrated
    # innovations under one parent node (for example, an encoder containing
    # both LFE and GFE blocks). Selecting only one asset per graph node loses
    # those sibling modules. Retain a supplementary figure only when it:
    #   1) maps strongly to an already selected parent,
    #   2) owns an alias declared by that parent, and
    #   3) introduces a new parent-owned alias.
    # This keeps complementary module figures without admitting generic or
    # experimentally visualized assets.
    alias_index = {
        str(module_id): {
            normalize_text(str(alias)).lower()
            for alias in aliases
            if normalize_text(str(alias))
        }
        for module_id, aliases in figure_map.get("module_alias_index", {}).items()
    }
    selected_aliases: dict[str, set[str]] = {
        module_id: set()
        for module_id in alias_index
    }
    for record in selected_by_asset.values():
        caption_aliases = {
            normalize_text(str(alias)).lower()
            for alias in record.get("caption_aliases", [])
            if normalize_text(str(alias))
        }
        for module_id in record.get("_selected_module_ids", []):
            selected_aliases.setdefault(module_id, set()).update(
                caption_aliases & alias_index.get(module_id, set())
            )

    supplementary: list[tuple[float, str, dict[str, Any], list[str]]] = []
    for record in candidates:
        asset_id = str(record.get("asset_id") or "")
        if not asset_id or asset_id in selected_by_asset:
            continue
        caption_aliases = {
            normalize_text(str(alias)).lower()
            for alias in record.get("caption_aliases", [])
            if normalize_text(str(alias))
        }
        owner_ids = set(record.get("exclusive_alias_owner_ids", []))
        mapped_ids = {
            str(mapping.get("module_id") or "")
            for mapping in record.get("module_mappings", [])
            if mapping.get("score", 0) >= MODULE_MATCH_THRESHOLD
            and mapping.get("match_kind")
            in {
                "explicit_figure_reference",
                "exact_unique_alias",
                "exact_alias",
                "parent_module_structure",
            }
        }
        eligible_ids: list[str] = []
        new_alias_count = 0
        for module_id in sorted(owner_ids & mapped_ids):
            parent_aliases = alias_index.get(module_id, set())
            new_aliases = (
                caption_aliases
                & parent_aliases
                - selected_aliases.get(module_id, set())
            )
            if new_aliases:
                eligible_ids.append(module_id)
                new_alias_count += len(new_aliases)
        if not eligible_ids:
            continue
        mapping_score = sum(
            _mapping_value(mapping)
            for mapping in record.get("module_mappings", [])
            if str(mapping.get("module_id") or "") in eligible_ids
        )
        supplementary.append(
            (
                mapping_score + 4.0 * new_alias_count,
                asset_id,
                record,
                eligible_ids,
            )
        )

    for _, asset_id, record, module_ids in sorted(
        supplementary,
        key=lambda item: (-item[0], item[1]),
    ):
        if len(selected_by_asset) >= 4:
            break
        selected_by_asset[asset_id] = {
            **record,
            "_selected_module_ids": module_ids,
        }
        caption_aliases = {
            normalize_text(str(alias)).lower()
            for alias in record.get("caption_aliases", [])
            if normalize_text(str(alias))
        }
        for module_id in module_ids:
            selected_aliases.setdefault(module_id, set()).update(
                caption_aliases & alias_index.get(module_id, set())
            )
    return list(selected_by_asset.values())


def _detail_caption_label(caption: str) -> str:
    normalized = normalize_text(caption)
    normalized = re.sub(
        r"^\s*(?:f\s*i\s*g\s*u\s*r\s*e|fig(?:ure)?)\s*\d+\s*[:.\-]?\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    match = re.match(
        r"details?\s+of\s+(?:the\s+)?(.+?)(?:[.;]|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    label = normalize_text(match.group(1)).strip(" .:")
    words = label.split()
    return " ".join(words[:8])


def compose_method_visual(
    paper_ir_path: Path,
    method_graph_path: Path,
    method_figure_map_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    graph = read_json(method_graph_path)
    figure_map = read_json(method_figure_map_path)
    nodes = graph.get("nodes", [])
    node_index = {node["id"]: node for node in nodes}
    overview_ambiguous = bool(figure_map.get("overview_selection_ambiguous"))
    ambiguous_overview_ids = {
        str(item.get("asset_id") or "")
        for item in figure_map.get("overview_ranking", [])
        if str(item.get("asset_id") or "")
    }
    overview_id = (
        None
        if overview_ambiguous
        else figure_map.get("overview_asset_id")
    )
    overview_record = _asset_record(figure_map, overview_id) if overview_id else None
    overview_covered = {
        mapping["module_id"]
        for mapping in (overview_record or {}).get("module_mappings", [])
        if mapping.get("score", 0) >= MODULE_MATCH_THRESHOLD
    }
    coverage_ratio = len(overview_covered) / len(nodes) if nodes else 0.0

    details: list[dict[str, Any]] = []
    dedicated_details = _dedicated_module_details(graph, figure_map)
    dedicated_target_ids = _dedicated_targets(graph, figure_map)
    if overview_record:
        details = list(dedicated_details)
        detail_covered = {
            module_id
            for record in details
            for module_id in record.get("_selected_module_ids", [])
        }
        if len(details) < 4:
            extras = _greedy_details(
                graph,
                figure_map,
                overview_covered | detail_covered,
            )
            selected_asset_ids = {
                str(record.get("asset_id") or "") for record in details
            }
            details.extend(
                record
                for record in extras
                if str(record.get("asset_id") or "") not in selected_asset_ids
            )
            details = details[:4]
        mode = "overview_plus_details" if details else "single_overview"
    else:
        details = _greedy_details(
            graph,
            figure_map,
            set(),
            excluded_asset_ids=ambiguous_overview_ids,
        )
        mode = "multi_figure_storyboard" if details else "text_only_method_path"

    # Selection is coverage-greedy, but the reader should see the selected
    # modules in the paper's declared method order.
    def detail_order(record: dict[str, Any]) -> int:
        selected_ids = record.get("_selected_module_ids") or [
            mapping["module_id"] for mapping in record.get("module_mappings", [])
        ]
        return min(
            (node_index.get(node_id, {}).get("order", 10**6) for node_id in selected_ids),
            default=10**6,
        )

    details.sort(key=detail_order)

    storyboard_items: list[dict[str, Any]] = []
    for record in details:
        mapped_ids = record.get("_selected_module_ids") or [
            mapping["module_id"]
            for mapping in record.get("module_mappings", [])
            if mapping.get("score", 0) >= MODULE_MATCH_THRESHOLD
        ]
        mapped_ids = sorted(
            mapped_ids,
            key=lambda node_id: node_index.get(node_id, {}).get("order", 10**6),
        )
        mapped_nodes = [node_index[node_id] for node_id in mapped_ids if node_id in node_index]
        if not mapped_nodes:
            continue
        primary = mapped_nodes[0]
        storyboard_items.append(
            {
                "asset_id": record["asset_id"],
                "display_mode": "original_figure",
                "module_ids": mapped_ids,
                "label": _detail_caption_label(str(record.get("caption") or ""))
                or primary["name"],
                "description": _clean_method_card_text(
                    str(primary.get("purpose") or ""),
                ),
                "flow": _mechanism_flow(primary),
                "caption": record.get("caption", ""),
                "focus_subfigure_labels": record.get(
                    "focus_subfigure_labels",
                    [],
                ),
                "subfigure_semantics": record.get(
                    "subfigure_semantics",
                    [],
                ),
                "sources": primary.get("sources", []),
                "selection_reason": [
                    {
                        "module_id": mapping["module_id"],
                        "match_kind": mapping.get("match_kind"),
                        "binding_evidence": mapping.get("binding_evidence", []),
                    }
                    for mapping in record.get("module_mappings", [])
                    if mapping["module_id"] in mapped_ids
                ],
            }
        )

    selected_detail_modules = {
        module_id
        for item in storyboard_items
        for module_id in item["module_ids"]
    }
    # Every Method card is either an original paper figure or an explicitly
    # marked evidence-backed mechanism flow. This avoids stretching a short
    # paragraph into an empty image-shaped card when no dedicated module
    # figure exists.
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in selected_detail_modules:
            continue
        storyboard_items.append(
            {
                "asset_id": None,
                "display_mode": "mechanism_flow",
                "module_ids": [node_id],
                "label": str(node.get("name") or "Method module"),
                "description": _clean_method_card_text(
                    str(node.get("purpose") or ""),
                ),
                "flow": _mechanism_flow(node),
                "caption": "",
                "focus_subfigure_labels": [],
                "subfigure_semantics": [],
                "sources": node.get("sources", []),
                "selection_reason": [
                    {
                        "module_id": node_id,
                        "match_kind": "text_fallback",
                        "binding_evidence": [
                            "no reliable dedicated module figure"
                        ],
                    }
                ],
            }
        )
    storyboard_items.sort(
        key=lambda item: min(
            (
                int(node_index.get(module_id, {}).get("order") or 10**6)
                for module_id in item.get("module_ids", [])
            ),
            default=10**6,
        )
    )

    covered_by_plan = set(overview_covered)
    for item in storyboard_items:
        covered_by_plan.update(item["module_ids"])
    text_fallback_modules = {
        module_id
        for item in storyboard_items
        if item.get("display_mode") == "mechanism_flow"
        for module_id in item.get("module_ids", [])
    }
    # A sourced text callout is the correct fallback when the paper does not
    # provide a method-eligible figure for a module. Do not force an
    # experimental chart into Method merely to satisfy visual coverage.
    covered_by_plan.update(text_fallback_modules)
    if mode == "text_only_method_path":
        covered_by_plan.update(node_index)

    callouts = [
        {
            "module_id": node["id"],
            "order": node["order"],
            "label": node["name"],
            "description": node["purpose"],
            "sources": node.get("sources", []),
        }
        for node in nodes[:5]
    ]
    method_asset_ids = [
        value
        for value in [overview_id, *(item["asset_id"] for item in storyboard_items)]
        if value
    ]
    result_leaks = sorted(
        set(method_asset_ids) & set(figure_map.get("result_excluded_ids", []))
    )
    selected_detail_modules = {
        module_id
        for item in storyboard_items
        if item.get("display_mode") == "original_figure"
        for module_id in item["module_ids"]
    }
    omitted_dedicated_modules = sorted(
        set(dedicated_target_ids) - selected_detail_modules,
        key=lambda node_id: node_index.get(node_id, {}).get("order", 10**6),
    )
    plan = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "mode": mode,
        "overview_asset_id": overview_id,
        "reuse_overview_in_storyboard": False,
        "callouts": callouts,
        "storyboard_items": storyboard_items,
        "experiment_strip": _experiment_strip(paper_ir),
        "method_asset_ids": method_asset_ids,
        "result_asset_ids_in_method": result_leaks,
        "dedicated_target_module_ids": dedicated_target_ids,
        "selected_dedicated_module_ids": sorted(
            selected_detail_modules & set(dedicated_target_ids),
            key=lambda node_id: node_index.get(node_id, {}).get("order", 10**6),
        ),
        "omitted_dedicated_module_ids": omitted_dedicated_modules,
        "text_fallback_module_ids": sorted(
            text_fallback_modules,
            key=lambda node_id: node_index.get(node_id, {}).get("order", 10**6),
        ),
        "module_coverage_ratio": (
            round(len(covered_by_plan) / len(nodes), 3) if nodes else 0.0
        ),
        "decision": {
            "overview_coverage_ratio": round(coverage_ratio, 3),
            "whole_overview_preserved": bool(overview_id),
            "ambiguous_overview_rejected": overview_ambiguous,
            "rejected_overview_asset_ids": sorted(ambiguous_overview_ids),
            "subfigure_cropping_used": False,
            "reason": {
                "single_overview": "The canonical overview covers all sourced method modules.",
                "overview_plus_details": "The overview is retained and dedicated, non-redundant module figures explain the paper's innovations.",
                "multi_figure_storyboard": "No complete overview exists; method figures are ordered by the sourced method graph.",
                "text_only_method_path": "No method-eligible figure exists; retain a sourced reading path without inventing visuals.",
            }[mode],
        },
    }
    report = {
        "status": (
            "failed"
            if result_leaks or omitted_dedicated_modules or not nodes
            else "passed"
        ),
        "mode": mode,
        "method_nodes": len(nodes),
        "storyboard_assets": len(storyboard_items),
        "module_coverage_ratio": plan["module_coverage_ratio"],
        "result_asset_ids_in_method": result_leaks,
        "dedicated_target_module_ids": dedicated_target_ids,
        "omitted_dedicated_module_ids": omitted_dedicated_modules,
        "warnings": (
            [
                "Ambiguous overview candidates were rejected; a sourced method flow is used."
            ]
            if overview_ambiguous
            else ["No method figure was available; a sourced text path is used."]
            if mode == "text_only_method_path"
            else (
                ["High-confidence dedicated module figures were omitted."]
                if omitted_dedicated_modules
                else []
            )
        ),
    }
    return (
        write_json(output_dir / "method_visual_plan.json", plan),
        write_json(output_dir / "method_visual_report.json", report),
    )
