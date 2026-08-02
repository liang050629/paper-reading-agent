from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import (
    find_numbers,
    jaccard,
    normalize_text,
    read_json,
    sha256_file,
    validate_story_sources,
    write_json,
)
from .key_idea import (
    DISPLAY_MODES,
    KEY_IDEA_TYPES,
    KEY_IDEA_VISUAL_TYPES,
    audit_key_idea_visible_text,
    visible_text_findings,
    visual_layout_compatible,
)
from .experimental_results import validate_experimental_results_spec
from .highlights import validate_highlights_spec
from .motivation_contributions import (
    validate_motivation_contribution_specs,
)


def _collect_panel_text_entries(
    value: Any,
    key: str | None = None,
    path: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    accepted_keys = {
        "text",
        "summary",
        "label",
        "value",
        "title",
        "short_title",
        "description",
        "visible_text",
        "context",
        "primary_value",
        "headline",
        "takeaway",
        "plain_language_explanation",
    }
    if isinstance(value, dict):
        result: list[dict[str, str]] = []
        for child_key, child in value.items():
            if child_key in {
                "sources",
                "selection_reason",
                "subfigure_semantics",
                "source_headers",
                "source_cell",
                "baseline_cell",
                "rewrite_attempts",
                "visible_text_audit",
                "gate_results",
                "final_gate_results",
                "audit",
            }:
                continue
            result.extend(
                _collect_panel_text_entries(
                    child,
                    child_key,
                    (*path, str(child_key)),
                )
            )
        return result
    if isinstance(value, list):
        result: list[dict[str, str]] = []
        for index, child in enumerate(value):
            result.extend(
                _collect_panel_text_entries(
                    child,
                    key,
                    (*path, str(index)),
                )
            )
        return result
    if isinstance(value, str) and key in accepted_keys:
        return [
            {
                "path": ".".join(path),
                "key": str(key),
                "text": value,
            }
        ]
    return []


def _collect_panel_text(value: Any, key: str | None = None) -> list[str]:
    return [
        entry["text"]
        for entry in _collect_panel_text_entries(value, key)
    ]


MALFORMED_VISIBLE_TEXT_RE = re.compile(
    r"\bhas\s+an\s+origin\s+in\s+(?:the|this)\s+work\b|"
    r"\buses?\s+the\s+work\s+of\s+(?:we|our)\b|"
    r"\b(?:ability|advantages?)\s+of\b.+\bstruggles?\b|"
    r"\bstruggles?\s+with\s+remains\b|"
    r"\bmust\s+[A-Z][A-Za-z0-9-]*\s+to\b|"
    r"\bthe\s+foregoing\s+(?:challenge|challenges|issue|issues)\b",
    re.I,
)
def _visible_text_return_to(path: str) -> str:
    if path.startswith("key_idea"):
        return "paper-key-idea"
    if path.startswith(("method_overview", "method_detail")):
        return "paper-method-visual-compose"
    if path.startswith(("motivation", "contributions")):
        return "paper-motivation-contributions"
    if path.startswith("experimental_results"):
        return "paper-experimental-results"
    if path.startswith("highlights"):
        return "paper-highlights"
    return "paper-poster-compose"


def _global_visible_text_issues(
    panels: dict[str, Any],
) -> list[dict[str, Any]]:
    phrase_keys = {
        "label",
        "value",
        "title",
        "short_title",
        "context",
        "primary_value",
    }
    failures: list[dict[str, Any]] = []
    for entry in _collect_panel_text_entries(panels):
        text = normalize_text(entry["text"])
        if not text:
            continue
        method_visual_phrase = entry["path"].startswith(
            "method_detail.visual_story"
        ) or entry["path"].startswith("method_overview.flow_items")
        findings = visible_text_findings(
            text,
            allow_phrase=(
                entry["key"] in phrase_keys or method_visual_phrase
            ),
        )
        if re.search(r"<[^>]+>|&(?:nbsp|amp|lt|gt);", text, re.I):
            findings.append("html_residue_check")
        if MALFORMED_VISIBLE_TEXT_RE.search(text):
            findings.append("malformed_visible_text_check")
        findings = list(dict.fromkeys(findings))
        if findings:
            failures.append(
                {
                    "path": entry["path"],
                    "text": text,
                    "findings": findings,
                    "return_to": _visible_text_return_to(entry["path"]),
                }
            )
    if not failures:
        return []
    return [
        {
            "code": "VISIBLE_TEXT_INTEGRITY_FAILED",
            "severity": "error",
            "message": (
                "Poster-visible text contains markup, raw math, an "
                "unresolved reference, OCR residue, or a malformed sentence."
            ),
            "details": failures,
            "return_to": failures[0]["return_to"],
        }
    ]


def _normalize_number(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _word_count(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", value))


def _auxiliary_overflow_is_minor(details: Any) -> bool:
    if not isinstance(details, list) or not details:
        return False
    auxiliary_panels = {
        "motivation",
        "contributions",
        "highlights",
        "project",
    }
    for item in details:
        if not isinstance(item, dict):
            return False
        if str(item.get("panel") or "") not in auxiliary_panels:
            return False
        vertical = float(item.get("scrollHeight") or 0) - float(
            item.get("clientHeight") or 0
        )
        horizontal = float(item.get("scrollWidth") or 0) - float(
            item.get("clientWidth") or 0
        )
        if vertical > 8 or horizontal > 2:
            return False
    return True


def _method_fallback_omission_is_minor(details: Any) -> bool:
    if not isinstance(details, dict):
        return False
    empty = details.get("empty") or []
    if empty:
        return False
    expected = int(details.get("expected") or 0)
    rendered = int(details.get("rendered") or 0)
    if expected <= 0:
        return False
    if rendered <= 0:
        return False
    if expected <= 4:
        return rendered >= expected - 1
    return rendered >= max(3, expected - 2)


def _result_provenance_gap_is_minor(details: Any) -> bool:
    if not isinstance(details, dict):
        return False
    missing = set(details.get("missing_fields") or [])
    invalid_claims = details.get("invalid_claim_ids") or []
    invalid_blocks = details.get("invalid_block_ids") or []
    return bool(missing) and missing <= {"caption"} and not invalid_claims and not invalid_blocks


def _method_role_conflict_is_minor(details: Any) -> bool:
    items = details if isinstance(details, list) else [details]
    if not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if str(item.get("code") or "") != "PROPOSED_SUBFIGURE_EXCLUDED_FROM_METHOD":
            return False
        if not item.get("focus_subfigure_labels"):
            return False
    return True


def _apply_delivery_severity_policy(
    issues: list[dict[str, Any]],
    *,
    key_visual_item_count: int,
    motivation_item_count: int,
    contribution_item_count: int,
) -> list[dict[str, Any]]:
    """Downgrade presentation sparsity without weakening truthfulness Gates."""
    always_soft = {
        "HIGHLIGHT_EVIDENCE_INSUFFICIENT",
        "KEY_IDEA_HEADLINE_WEAK",
        "KEY_IDEA_WORD_BUDGET_INVALID",
        "KEY_IDEA_NO_EQUATION_RENDER_UNDERFILLED",
        "RESULT_METRIC_COUNT_INVALID",
        "RESULT_MIXED_EVALUATION_CONTEXT",
        "RESULT_TABLE_FOCUS_CROP_REQUIRED",
        "RESULT_FOCUS_TABLE_UNREADABLE",
        "MOTIVATION_EVIDENCE_INSUFFICIENT",
        "MOTIVATION_COVERAGE_CHECK",
        "CONTRIBUTION_EVIDENCE_INSUFFICIENT",
        "CONTRIBUTION_DISPLAYABLE_COUNT_CHECK",
    }
    conditional_key_idea_soft = {
        "KEY_IDEA_VISUAL_LAYOUT_INCOMPATIBLE",
        "KEY_IDEA_NO_EQUATION_SPACE_UNUSED",
        "KEY_IDEA_NO_EQUATION_RENDER_EMPTY",
    }
    conditional_motivation_soft = {
        "MOTIVATION_EVIDENCE_INSUFFICIENT",
        "MOTIVATION_COVERAGE_CHECK",
    }
    normalized: list[dict[str, Any]] = []
    for original in issues:
        issue = dict(original)
        code = str(issue.get("code") or "")
        downgrade_reason = None
        if code in always_soft:
            downgrade_reason = "presentation_quality"
        elif code in conditional_key_idea_soft and key_visual_item_count >= 1:
            downgrade_reason = "adaptive_key_idea_layout"
        elif code in conditional_motivation_soft and motivation_item_count >= 1:
            downgrade_reason = "sparse_but_traceable_motivation"
        elif (
            code == "CONTRIBUTION_EVIDENCE_INSUFFICIENT"
            and contribution_item_count >= 1
        ):
            downgrade_reason = "sparse_but_traceable_contribution"
        elif code == "OVERFLOW_ELEMENTS" and _auxiliary_overflow_is_minor(
            issue.get("details")
        ):
            downgrade_reason = "minor_auxiliary_overflow"
        elif (
            code == "METHOD_FALLBACK_RENDER_INVALID"
            and _method_fallback_omission_is_minor(issue.get("details"))
        ):
            downgrade_reason = "adaptive_method_card_density"
        elif (
            code == "RESULT_ASSET_PROVENANCE_INCOMPLETE"
            and _result_provenance_gap_is_minor(issue.get("details"))
        ):
            downgrade_reason = "minor_result_caption_gap"
        elif (
            code == "METHOD_FIGURE_ROLE_CONFLICT"
            and _method_role_conflict_is_minor(issue.get("details"))
        ):
            downgrade_reason = "ambiguous_proposed_subfigure_role"
        if downgrade_reason and issue.get("severity") == "error":
            issue["severity"] = "warning"
            issue["delivery_policy"] = downgrade_reason
        normalized.append(issue)
    return normalized


def _asset_exists(asset: dict[str, Any], paper_ir_dir: Path) -> bool:
    if not asset.get("path"):
        return False
    path = Path(str(asset["path"]))
    if not path.is_absolute():
        path = paper_ir_dir / path
    return path.is_file()


def _method_content_mismatches(
    method_asset_ids: set[str],
    method_figure_map: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "asset_id": record.get("asset_id"),
            "visual_content_signals": record.get("visual_content_signals"),
            "mismatch_reasons": record.get(
                "caption_content_mismatch_reasons",
                [],
            ),
        }
        for record in method_figure_map.get("records", [])
        if record.get("asset_id") in method_asset_ids
        and record.get("caption_content_consistent") is False
    ]


def _validate_method_overview(
    panel: dict[str, Any],
    method_nodes: list[dict[str, Any]],
    paper_ir: dict[str, Any],
) -> list[dict[str, Any]]:
    if panel.get("asset"):
        return []

    flow_items = list(panel.get("flow_items") or [])
    if not flow_items:
        return [
            {
                "code": "METHOD_OVERVIEW_CONTENT_MISSING",
                "severity": "error",
                "message": (
                    "Method Overview has neither a reliable original figure "
                    "nor an evidence-backed method flow."
                ),
                "return_to": "paper-poster-compose",
            }
        ]

    known_module_ids = {
        str(node.get("id") or "")
        for node in method_nodes
        if str(node.get("id") or "")
    }
    known_block_ids = {
        str(block.get("id") or "")
        for block in paper_ir.get("blocks", [])
        if str(block.get("id") or "")
    }
    invalid_items: list[dict[str, Any]] = []
    for item in flow_items:
        module_id = str(item.get("module_id") or "")
        source_block_ids = {
            str(value)
            for value in item.get("source_block_ids", [])
            if str(value)
        }
        reasons: list[str] = []
        if not module_id or module_id not in known_module_ids:
            reasons.append("invalid module binding")
        if (
            not normalize_text(str(item.get("label") or ""))
            or not normalize_text(str(item.get("text") or ""))
        ):
            reasons.append("missing visible flow content")
        if (
            not source_block_ids
            or bool(source_block_ids - known_block_ids)
        ):
            reasons.append("invalid source block binding")
        if reasons:
            invalid_items.append(
                {
                    "module_id": module_id,
                    "source_block_ids": sorted(source_block_ids),
                    "reasons": reasons,
                }
            )
    if not invalid_items:
        return []
    return [
        {
            "code": "METHOD_OVERVIEW_FLOW_INVALID",
            "severity": "error",
            "message": (
                "Every generated Method Overview stage must contain readable "
                "content and bind to a real method module and source block."
            ),
            "details": invalid_items,
            "return_to": "paper-poster-compose",
        }
    ]


def validate_poster(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    selected_assets_path: Path,
    method_graph_path: Path,
    method_figure_map_path: Path,
    method_visual_plan_path: Path,
    key_idea_spec_path: Path,
    experimental_results_spec_path: Path,
    highlights_spec_path: Path,
    motivation_spec_path: Path,
    contribution_spec_path: Path,
    poster_spec_path: Path,
    render_bundle_path: Path,
    output_dir: Path,
) -> Path:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    selected = read_json(selected_assets_path)
    method_graph = read_json(method_graph_path)
    method_figure_map = read_json(method_figure_map_path)
    method_visual = read_json(method_visual_plan_path)
    key_idea = read_json(key_idea_spec_path)
    experimental_results = read_json(experimental_results_spec_path)
    highlights = read_json(highlights_spec_path)
    motivation_spec = read_json(motivation_spec_path)
    contribution_spec = read_json(contribution_spec_path)
    spec = read_json(poster_spec_path)
    bundle = read_json(render_bundle_path)
    issues: list[dict[str, Any]] = []
    if str(spec.get("preview_status") or "") != "valid":
        issues.append(
            {
                "code": "KEY_IDEA_FORMAL_COMPOSE_BLOCKED",
                "severity": "error",
                "message": (
                    "A failed Key Idea audit may produce only an invalid debug "
                    "preview, not a formal Poster export."
                ),
                "return_to": "paper-key-idea",
            }
        )

    for issue in validate_story_sources(story):
        issues.append(issue)
    issues.extend(
        validate_experimental_results_spec(
            experimental_results,
            paper_ir,
            evidence,
            check_files=True,
            paper_ir_dir=paper_ir_path.parent,
        )
    )
    issues.extend(validate_highlights_spec(highlights, paper_ir, evidence))
    motivation_contribution_checks, motivation_contribution_issues = (
        validate_motivation_contribution_specs(
            motivation_spec,
            contribution_spec,
            paper_ir,
        )
    )
    issues.extend(motivation_contribution_issues)
    issues.extend(_global_visible_text_issues(spec.get("panels") or {}))
    rendered_motivation_items = list(
        ((spec.get("panels") or {}).get("motivation") or [])
    )
    if motivation_spec.get("items") and not rendered_motivation_items:
        issues.append(
            {
                "code": "MOTIVATION_RENDER_EMPTY",
                "severity": "error",
                "message": (
                    "All selected Motivation items failed the final visible "
                    "text filter."
                ),
                "return_to": "paper-motivation-contributions",
            }
        )
    elif (spec.get("provenance") or {}).get(
        "omitted_invalid_motivation_ids"
    ):
        issues.append(
            {
                "code": "MOTIVATION_INVALID_ITEMS_OMITTED",
                "severity": "warning",
                "message": (
                    "Invalid optional Motivation text was omitted while "
                    "traceable displayable items remained."
                ),
                "details": (spec.get("provenance") or {}).get(
                    "omitted_invalid_motivation_ids"
                ),
                "return_to": "paper-motivation-contributions",
            }
        )

    method_nodes = method_graph.get("nodes", [])
    for node in method_nodes:
        if not node.get("sources"):
            issues.append(
                {
                    "code": "METHOD_GRAPH_SOURCE_MISSING",
                    "severity": "error",
                    "message": f"Method node {node.get('id')} has no source evidence.",
                    "return_to": "paper-method-graph",
                }
            )
    if not method_nodes:
        issues.append(
            {
                "code": "METHOD_GRAPH_EMPTY",
                "severity": "error",
                "message": "The paper has method content but no method modules were recovered.",
                "return_to": "paper-method-graph",
            }
        )
    overview_panel = (spec.get("panels") or {}).get("method_overview") or {}
    issues.extend(
        _validate_method_overview(
            overview_panel,
            method_nodes,
            paper_ir,
        )
    )

    result_leaks = method_visual.get("result_asset_ids_in_method", [])
    if result_leaks:
        issues.append(
            {
                "code": "METHOD_CONTAINS_RESULT_ASSET",
                "severity": "error",
                "message": "Result, qualitative, dataset, or ablation figures entered the Method area.",
                "details": result_leaks,
                "return_to": "paper-method-figure-map",
            }
        )
    method_asset_ids = set(method_visual.get("method_asset_ids", []))
    eligible_ids = {
        record["asset_id"]
        for record in method_figure_map.get("records", [])
        if record.get("method_eligible")
    }
    ineligible_method_assets = sorted(method_asset_ids - eligible_ids)
    if ineligible_method_assets:
        issues.append(
            {
                "code": "METHOD_ASSET_NOT_ELIGIBLE",
                "severity": "error",
                "message": "Method area contains figures not classified as method visuals.",
                "details": ineligible_method_assets,
                "return_to": "paper-method-figure-map",
            }
        )
    inconsistent_method_assets = _method_content_mismatches(
        method_asset_ids,
        method_figure_map,
    )
    if inconsistent_method_assets:
        issues.append(
            {
                "code": "METHOD_ASSET_CONTENT_MISMATCH",
                "severity": "error",
                "message": (
                    "A Method asset's visible content conflicts with its "
                    "caption or Method-reference metadata."
                ),
                "details": inconsistent_method_assets,
                "return_to": "paper-method-figure-map",
            }
        )
    method_coverage = float(method_visual.get("module_coverage_ratio") or 0)
    if method_nodes and method_coverage < 0.67:
        issues.append(
            {
                "code": "METHOD_MODULE_COVERAGE_LOW",
                "severity": "error",
                "message": f"Method visual covers only {method_coverage:.0%} of sourced modules.",
                "return_to": "paper-method-visual-compose",
            }
        )
    if (
        method_visual.get("overview_asset_id")
        and method_visual.get("reuse_overview_in_storyboard")
    ):
        issues.append(
            {
                "code": "METHOD_OVERVIEW_DUPLICATED",
                "severity": "error",
                "message": "The complete overview must not be duplicated as storyboard thumbnails.",
                "return_to": "paper-method-visual-compose",
            }
        )
    if (
        method_figure_map.get("overview_selection_ambiguous")
        and method_visual.get("overview_asset_id")
    ):
        issues.append(
            {
                "code": "METHOD_OVERVIEW_AMBIGUOUS",
                "severity": "error",
                "message": (
                    "Multiple method-overview figures remain tied without "
                    "primary-method evidence; do not resolve by document order."
                ),
                "details": method_figure_map.get("overview_ranking", []),
                "return_to": "paper-method-figure-map",
            }
        )
    semantic_binding_conflicts = method_figure_map.get(
        "semantic_binding_conflicts",
        [],
    )
    if semantic_binding_conflicts:
        issues.append(
            {
                "code": "METHOD_MODULE_BINDING_CONFLICT",
                "severity": "error",
                "message": (
                    "A dedicated method figure conflicts with its unique "
                    "module alias; generic term overlap cannot resolve it."
                ),
                "details": semantic_binding_conflicts,
                "return_to": "paper-method-figure-map",
            }
        )
    role_conflicts = method_figure_map.get("role_conflicts", [])
    if role_conflicts:
        issues.append(
            {
                "code": "METHOD_FIGURE_ROLE_CONFLICT",
                "severity": "error",
                "message": (
                    "A method-cited figure or explicitly proposed subfigure "
                    "was classified outside the Method visual set."
                ),
                "details": role_conflicts,
                "return_to": "paper-method-figure-map",
            }
        )
    omitted_dedicated_modules = method_visual.get(
        "omitted_dedicated_module_ids",
        [],
    )
    if omitted_dedicated_modules:
        issues.append(
            {
                "code": "METHOD_DEDICATED_FIGURE_OMITTED",
                "severity": "error",
                "message": (
                    "High-confidence dedicated figures exist for method "
                    "modules but were omitted from the storyboard."
                ),
                "details": omitted_dedicated_modules,
                "return_to": "paper-method-visual-compose",
            }
        )
    invalid_method_cards: list[dict[str, Any]] = []
    for item in method_visual.get("storyboard_items", []):
        display_mode = str(item.get("display_mode") or "")
        module_ids = [
            str(value)
            for value in item.get("module_ids", [])
            if str(value)
        ]
        if display_mode == "original_figure":
            if not item.get("asset_id") or not module_ids:
                invalid_method_cards.append(
                    {
                        "module_ids": module_ids,
                        "display_mode": display_mode,
                        "reason": "original figure card lacks an asset or module binding",
                    }
                )
        elif display_mode == "mechanism_flow":
            stages = list((item.get("flow") or {}).get("stages") or [])
            if (
                not module_ids
                or not stages
                or not any(
                    normalize_text(str(stage.get("text") or ""))
                    for stage in stages
                )
            ):
                invalid_method_cards.append(
                    {
                        "module_ids": module_ids,
                        "display_mode": display_mode,
                        "reason": "mechanism fallback lacks sourced flow content",
                    }
                )
        else:
            invalid_method_cards.append(
                {
                    "module_ids": module_ids,
                    "display_mode": display_mode,
                    "reason": "method card must choose original_figure or mechanism_flow",
                }
            )
    if invalid_method_cards:
        issues.append(
            {
                "code": "METHOD_CARD_CONTENT_INVALID",
                "severity": "error",
                "message": (
                    "Every Method card must contain a reliable original figure "
                    "or a compact evidence-backed mechanism flow."
                ),
                "details": invalid_method_cards,
                "return_to": "paper-method-visual-compose",
            }
        )

    key_type = str(key_idea.get("type") or "")
    headline = normalize_text(str(key_idea.get("headline") or ""))
    headline_words = _word_count(headline)
    source_claim_ids = set(key_idea.get("source_claim_ids") or [])
    source_block_ids = set(key_idea.get("source_block_ids") or [])
    known_claim_ids = {
        str(claim.get("claim_id"))
        for claim in evidence.get("claims", [])
        if claim.get("claim_id")
    }
    known_block_ids = {
        str(block.get("id"))
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }
    if key_type not in KEY_IDEA_TYPES:
        issues.append(
            {
                "code": "KEY_IDEA_TYPE_INVALID",
                "severity": "error",
                "message": "Key Idea must use one of the five supported primary types.",
                "return_to": "paper-key-idea",
            }
        )
    if not 15 <= headline_words <= 25 or re.match(
        r"^(?:this|it|these|they)\b",
        headline,
        re.I,
    ):
        issues.append(
            {
                "code": "KEY_IDEA_HEADLINE_WEAK",
                "severity": "error",
                "message": "Key Idea headline must stand alone in 15–25 English words.",
                "details": {"headline": headline, "words": headline_words},
                "return_to": "paper-key-idea",
            }
        )
    invalid_claim_ids = sorted(source_claim_ids - known_claim_ids)
    invalid_block_ids = sorted(source_block_ids - known_block_ids)
    if (
        not source_claim_ids
        or not source_block_ids
        or invalid_claim_ids
        or invalid_block_ids
    ):
        issues.append(
            {
                "code": "KEY_IDEA_SOURCE_BINDING_INVALID",
                "severity": "error",
                "message": "Key Idea must bind to both real ClaimEvidence and PaperIR blocks.",
                "details": {
                    "invalid_claim_ids": invalid_claim_ids,
                    "invalid_block_ids": invalid_block_ids,
                },
                "return_to": "paper-key-idea",
            }
        )
    core_text = normalize_text(
        f"{key_idea.get('headline') or ''} {key_idea.get('core_insight') or ''}"
    )
    relevance_sources = [
        str(claim.get("claim") or "")
        for claim in evidence.get("claims", [])
        if claim.get("verdict") in {"supported", "partially_supported"}
    ] + [
        str(node.get("purpose") or node.get("innovation") or "")
        for node in method_nodes
    ]
    key_relevance = max(
        (jaccard(core_text, candidate) for candidate in relevance_sources),
        default=0.0,
    )
    if relevance_sources and key_relevance < 0.03:
        issues.append(
            {
                "code": "KEY_IDEA_NOT_CORE_CONTRIBUTION",
                "severity": "error",
                "message": "Key Idea is not directly related to a supported claim or method contribution.",
                "return_to": "paper-key-idea",
            }
        )
    visual_spec = key_idea.get("visual") or {}
    visual_items = visual_spec.get("items") or []
    key_visual_type = str(visual_spec.get("visual_type") or "")
    if key_visual_type not in KEY_IDEA_VISUAL_TYPES:
        issues.append(
            {
                "code": "KEY_IDEA_VISUAL_TYPE_INVALID",
                "severity": "error",
                "message": "Key Idea visual type is not supported.",
                "details": key_visual_type,
                "return_to": "paper-key-idea",
            }
        )
    elif not visual_layout_compatible(
        key_visual_type,
        len(visual_items),
    ):
        issues.append(
            {
                "code": "KEY_IDEA_VISUAL_LAYOUT_INCOMPATIBLE",
                "severity": "error",
                "message": (
                    "Key Idea item count does not match its adaptive visual "
                    "template."
                ),
                "details": {
                    "visual_type": key_visual_type,
                    "item_count": len(visual_items),
                },
                "return_to": "paper-key-idea",
            }
        )
    overview_id = method_figure_map.get("overview_asset_id")
    visual_asset_ids = {
        str(value)
        for value in [
            visual_spec.get("overview_asset_id"),
            visual_spec.get("asset_id"),
            *(item.get("asset_id") for item in visual_items),
        ]
        if value
    }
    if overview_id and str(overview_id) in visual_asset_ids:
        issues.append(
            {
                "code": "KEY_IDEA_DUPLICATES_METHOD_OVERVIEW",
                "severity": "error",
                "message": "Key Idea must not reuse the complete Method Overview asset.",
                "return_to": "paper-key-idea",
            }
        )
    key_equation = key_idea.get("equation") or {}
    equation_id = key_equation.get("equation_id")
    equation_mode = str(key_equation.get("display_mode") or "none")
    equation_score = key_equation.get("score")
    if equation_mode not in DISPLAY_MODES:
        issues.append(
            {
                "code": "KEY_IDEA_EQUATION_DISPLAY_MODE_INVALID",
                "severity": "error",
                "message": "Key Idea equation display mode is invalid.",
                "return_to": "paper-key-idea",
            }
        )
    if equation_id and (
        equation_score is None
        or float(equation_score) < 7
        or key_equation.get("generic_rejected")
        or any(
            "generic loss/metric" in str(reason)
            for reason in key_equation.get("selection_reason", [])
        )
    ):
        issues.append(
            {
                "code": "KEY_IDEA_EQUATION_NOT_CENTRAL",
                "severity": "error",
                "message": "Selected Key Idea equation did not pass the core-equation score.",
                "return_to": "paper-key-idea",
            }
        )
    if equation_id and not bool(
        (key_equation.get("alignment_gate") or {}).get("passed")
    ):
        issues.append(
            {
                "code": "KEY_IDEA_EQUATION_ALIGNMENT_INVALID",
                "severity": "error",
                "message": (
                    "The selected equation is not directly aligned with the "
                    "current Key Idea."
                ),
                "return_to": "paper-key-idea",
            }
        )
    if equation_id and not key_equation.get("plain_language_explanation"):
        issues.append(
            {
                "code": "KEY_IDEA_EQUATION_EXPLANATION_MISSING",
                "severity": "error",
                "message": "A Key Idea equation requires a natural-language explanation.",
                "return_to": "paper-key-idea",
            }
        )
    if equation_mode == "original_crop":
        image_value = key_equation.get("image_path")
        image_path = Path(str(image_value)) if image_value else None
        if image_path and not image_path.is_absolute():
            image_path = paper_ir_path.parent / image_path
        image_hash = (
            sha256_file(image_path)
            if image_path and image_path.is_file()
            else None
        )
        if (
            not image_path
            or not image_path.is_file()
            or not key_equation.get("crop_integrity")
            or not key_equation.get("bbox")
            or image_hash != key_equation.get("image_sha256")
        ):
            issues.append(
                {
                    "code": "KEY_IDEA_EQUATION_CROP_INVALID",
                    "severity": "error",
                    "message": "Original equation crop is missing, incomplete, or differs from its recorded hash.",
                    "return_to": "paper-key-idea",
                }
            )
    if (
        not equation_id
        and not visual_layout_compatible(
            key_visual_type,
            len(visual_items),
        )
    ):
        issues.append(
            {
                "code": "KEY_IDEA_NO_EQUATION_SPACE_UNUSED",
                "severity": "error",
                "message": (
                    "A no-equation Key Idea must use an adaptive visual whose "
                    "template matches the available evidence-backed items."
                ),
                "return_to": "paper-key-idea",
            }
        )
    key_word_count = int(key_idea.get("display_word_count") or 0)
    if not 60 <= key_word_count <= 120:
        issues.append(
            {
                "code": "KEY_IDEA_WORD_BUDGET_INVALID",
                "severity": "error",
                "message": "Visible Key Idea text must contain 60–120 English words.",
                "details": key_word_count,
                "return_to": "paper-key-idea",
            }
        )
    visible_audit = audit_key_idea_visible_text(key_idea)
    visible_issue_groups = {
        "KEY_IDEA_LATEX_RESIDUE": {
            "latex_residue_check",
            "raw_subscript_superscript_check",
            "unmatched_braces_check",
            "incomplete_equation_fragment_check",
        },
        "KEY_IDEA_MATH_DELIMITER_RESIDUE": {"math_delimiter_check"},
        "KEY_IDEA_SENTENCE_INCOMPLETE": {
            "sentence_completeness_check",
            "clause_completeness_check",
            "dangling_conjunction_check",
            "unmatched_parenthesis_check",
            "unresolved_reference_check",
            "ocr_cleanup_check",
        },
        "KEY_IDEA_CROSS_REFERENCE_RESIDUE": {"cross_reference_check"},
    }
    for issue_code, finding_codes in visible_issue_groups.items():
        matched = [
            finding
            for finding in visible_audit.get("findings", [])
            if finding.get("code") in finding_codes
        ]
        if matched:
            issues.append(
                {
                    "code": issue_code,
                    "severity": "error",
                    "message": (
                        "Key Idea visible text must be complete natural "
                        "language without raw math or source cross-references."
                    ),
                    "details": matched,
                    "return_to": "paper-key-idea",
                }
            )
    if key_idea.get("inferred") and not str(
        key_idea.get("inference_label") or ""
    ).startswith("Inferred"):
        issues.append(
            {
                "code": "KEY_IDEA_INFERENCE_UNLABELED",
                "severity": "error",
                "message": "Inferred Key Idea content must be explicitly labeled.",
                "return_to": "paper-key-idea",
            }
        )

    paper_text = " ".join(
        [
            *(str(block.get("text") or "") for block in paper_ir.get("blocks", [])),
            *(
                " ".join(
                    str(asset.get(field) or "")
                    for field in ("caption", "context_before", "context_after", "html")
                )
                for group in ("figures", "tables", "equations")
                for asset in paper_ir.get(group, [])
            ),
        ]
    )
    paper_numbers = {_normalize_number(number) for number in find_numbers(paper_text)}
    for table in paper_ir.get("tables", []):
        for number in re.findall(
            r"(?<![\w.])[+-]?(?:\d+\.\d+|\d+)",
            str(table.get("html") or ""),
        ):
            paper_numbers.add(_normalize_number(number))
    poster_text = " ".join(_collect_panel_text(spec.get("panels", {})))
    poster_numbers = {_normalize_number(number) for number in find_numbers(poster_text)}
    verified_derived_numbers: set[str] = set()
    for item in highlights.get("highlights") or []:
        for field in (
            "primary_value",
            "context",
            "absolute_difference",
            "relative_difference_percent",
        ):
            verified_derived_numbers.update(
                _normalize_number(number)
                for number in find_numbers(str(item.get(field) or ""))
            )
    numeric_mismatches = sorted(
        poster_numbers - paper_numbers - verified_derived_numbers
    )
    for number in numeric_mismatches:
        issues.append(
            {
                "code": "CONTENT_NUMERIC_MISMATCH",
                "severity": "error",
                "message": f"Poster number {number} was not found in the paper text.",
                "return_to": "paper-poster-compose",
            }
        )

    truncated_panel_text = [
        text
        for text in _collect_panel_text(spec.get("panels", {}))
        if "…" in text or re.search(r"\.{3}\s*$", text)
    ]
    if truncated_panel_text:
        issues.append(
            {
                "code": "CONTENT_TRUNCATED",
                "severity": "error",
                "message": "Poster content contains layout-generated truncation.",
                "details": truncated_panel_text,
                "return_to": "paper-poster-compose",
            }
        )

    expected_captions = len(paper_ir.get("figures", [])) + len(paper_ir.get("tables", []))
    if selected.get("captions_inspected") != expected_captions:
        issues.append(
            {
                "code": "ASSET_CAPTIONS_NOT_FULLY_INSPECTED",
                "severity": "error",
                "message": (
                    f"Inspected {selected.get('captions_inspected')} captions; "
                    f"expected {expected_captions}."
                ),
                "return_to": "paper-asset-select",
            }
        )
    if selected.get("figure_number_prior_used"):
        issues.append(
            {
                "code": "ASSET_FIGURE_NUMBER_PRIOR_USED",
                "severity": "error",
                "message": "Figure number must not influence overview selection.",
                "return_to": "paper-asset-select",
            }
        )

    asset_index = {
        asset["id"]: asset
        for group in ("figures", "equations", "tables")
        for asset in paper_ir.get(group, [])
    }
    selected_ids = []
    if selected.get("overview_asset"):
        selected_ids.append(selected["overview_asset"]["id"])
    selected_ids.extend(item["id"] for item in selected.get("key_equations", []))
    if equation_id:
        selected_ids.append(str(equation_id))
    selected_ids.extend(item["id"] for item in selected.get("result_assets", []))
    selected_ids.extend(method_visual.get("method_asset_ids", []))
    missing_assets = []
    for asset_id in selected_ids:
        asset = asset_index.get(asset_id)
        if asset and (asset.get("latex") or _asset_exists(asset, paper_ir_path.parent)):
            continue
        missing_assets.append(asset_id)
    for asset_id in missing_assets:
        issues.append(
            {
                "code": "ASSET_FILE_MISSING",
                "severity": "error",
                "message": f"Selected asset {asset_id} has no usable local file or LaTeX.",
                "return_to": "paper-asset-select",
            }
        )

    visual = {
        "missing_images": [],
        "overflow_elements": [],
        "overlap_pairs": [],
        "min_font_px": None,
    }
    html_path_value = bundle.get("html_path")
    rendered_html = ""
    if html_path_value and Path(html_path_value).is_file():
        rendered_html = Path(html_path_value).read_text(encoding="utf-8")
    if r"\[" in rendered_html:
        issues.append(
            {
                "code": "EQUATION_NOT_VISUALLY_RENDERED",
                "severity": "error",
                "message": "A selected equation still contains raw display-math delimiters.",
                "return_to": "paper-poster-render",
            }
        )
    if bundle.get("metrics_path") and Path(bundle["metrics_path"]).is_file():
        visual.update(read_json(Path(bundle["metrics_path"])))
    elif bundle.get("browser_export_requested"):
        issues.append(
            {
                "code": "VALIDATOR_BROWSER_METRICS_MISSING",
                "severity": "error",
                "message": "Browser export was requested but DOM metrics are missing.",
                "return_to": "paper-poster-render",
            }
        )
    expected_storyboard_assets = {
        str(item.get("asset_id"))
        for item in method_visual.get("storyboard_items", [])
        if item.get("asset_id")
    }
    rendered_storyboard_assets = {
        str(asset_id) for asset_id in visual.get("method_asset_ids", [])
    }
    missing_rendered_method_assets = sorted(
        expected_storyboard_assets - rendered_storyboard_assets
    )
    if bundle.get("browser_export_requested") and missing_rendered_method_assets:
        issues.append(
            {
                "code": "METHOD_MODULE_RENDER_MISSING",
                "severity": "error",
                "message": (
                    "Planned method-module figures were dropped from the "
                    "rendered poster."
                ),
                "details": missing_rendered_method_assets,
                "return_to": "paper-poster-compose",
            }
        )
    expected_method_fallbacks = sum(
        1
        for item in method_visual.get("storyboard_items", [])
        if item.get("display_mode") == "mechanism_flow"
    )
    if bundle.get("browser_export_requested") and (
        int(visual.get("method_fallback_card_count") or 0)
        != expected_method_fallbacks
        or visual.get("method_empty_fallback_cards")
    ):
        issues.append(
            {
                "code": "METHOD_FALLBACK_RENDER_INVALID",
                "severity": "error",
                "message": (
                    "A planned no-image Method module was omitted or rendered "
                    "without compact mechanism content."
                ),
                "details": {
                    "expected": expected_method_fallbacks,
                    "rendered": int(
                        visual.get("method_fallback_card_count") or 0
                    ),
                    "empty": visual.get("method_empty_fallback_cards", []),
                },
                "return_to": "paper-poster-render",
            }
        )
    expected_overview_mode = (
        "original_figure"
        if overview_panel.get("asset")
        else str(overview_panel.get("fallback") or "no-overview-figure")
    )
    if bundle.get("browser_export_requested"):
        if (
            visual.get("method_overview_mode") != expected_overview_mode
            or (
                expected_overview_mode == "sourced_method_flow"
                and (
                    bool(visual.get("method_overview_empty"))
                    or int(visual.get("method_overview_flow_count") or 0)
                    != len(overview_panel.get("flow_items") or [])
                )
            )
        ):
            issues.append(
                {
                    "code": "METHOD_OVERVIEW_RENDER_EMPTY",
                    "severity": "error",
                    "message": (
                        "The rendered Method Overview is missing the original "
                        "figure or one or more planned sourced flow stages."
                    ),
                    "details": {
                        "expected_mode": expected_overview_mode,
                        "rendered_mode": visual.get("method_overview_mode"),
                        "expected_flow_count": len(
                            overview_panel.get("flow_items") or []
                        ),
                        "rendered_flow_count": int(
                            visual.get("method_overview_flow_count") or 0
                        ),
                    },
                    "return_to": "paper-poster-render",
                }
            )
    if bundle.get("browser_export_requested"):
        if visual.get("key_idea_type") != key_type:
            issues.append(
                {
                    "code": "KEY_IDEA_RENDER_TYPE_MISMATCH",
                    "severity": "error",
                    "message": "Rendered Key Idea type differs from key_idea_spec.json.",
                    "return_to": "paper-poster-render",
                }
            )
        if equation_mode == "original_crop" and (
            visual.get("key_idea_equation_id") != equation_id
            or visual.get("key_idea_equation_object_fit") != "contain"
        ):
            issues.append(
                {
                    "code": "KEY_IDEA_EQUATION_RENDER_INVALID",
                    "severity": "error",
                    "message": "Equation crop was omitted or geometrically distorted in the renderer.",
                    "return_to": "paper-poster-render",
                }
            )
        rendered_key_items = int(
            visual.get("key_idea_visual_items") or 0
        )
        if (
            not equation_id
            and not visual_layout_compatible(
                key_visual_type,
                rendered_key_items,
            )
        ):
            issues.append(
                {
                    "code": "KEY_IDEA_NO_EQUATION_RENDER_EMPTY",
                    "severity": "error",
                    "message": (
                        "No-equation Key Idea did not render the item count "
                        "required by its adaptive template."
                    ),
                    "return_to": "paper-poster-render",
                }
            )
        key_fill_ratio = visual.get("key_idea_visual_fill_ratio")
        if (
            not equation_id
            and key_fill_ratio is not None
            and float(key_fill_ratio) < 0.55
        ):
            issues.append(
                {
                    "code": "KEY_IDEA_NO_EQUATION_RENDER_UNDERFILLED",
                    "severity": "error",
                    "message": (
                        "No-equation Key Idea leaves most of its visual region "
                        "unused."
                    ),
                    "details": key_fill_ratio,
                    "return_to": "paper-poster-render",
                }
            )
        expected_result_assets = {
            str(asset.get("asset_id"))
            for asset in (
                experimental_results.get("primary_asset"),
                experimental_results.get("secondary_asset"),
            )
            if asset and asset.get("asset_id")
        }
        rendered_result_assets = {
            str(asset.get("id"))
            for asset in visual.get("experimental_results_assets", [])
            if asset.get("id")
        }
        if visual.get("experimental_results_layout") != experimental_results.get(
            "layout_template"
        ):
            issues.append(
                {
                    "code": "RESULT_RENDER_LAYOUT_MISMATCH",
                    "severity": "error",
                    "message": "Rendered Experimental Results layout differs from its validated specification.",
                    "return_to": "paper-poster-render",
                }
            )
        if expected_result_assets != rendered_result_assets:
            issues.append(
                {
                    "code": "RESULT_RENDER_ASSET_MISSING",
                    "severity": "error",
                    "message": "A planned Experimental Results asset was omitted or replaced.",
                    "details": {
                        "expected": sorted(expected_result_assets),
                        "rendered": sorted(rendered_result_assets),
                    },
                    "return_to": "paper-poster-compose",
                }
            )
        if int(visual.get("experimental_results_metric_count") or 0) != len(
            experimental_results.get("key_metrics") or []
        ):
            issues.append(
                {
                    "code": "RESULT_RENDER_METRIC_MISSING",
                    "severity": "error",
                    "message": "Rendered key metrics differ from the verified results specification.",
                    "return_to": "paper-poster-render",
                }
            )
        result_specs = {
            str(asset.get("asset_id")): asset
            for asset in (
                experimental_results.get("primary_asset"),
                experimental_results.get("secondary_asset"),
            )
            if asset and asset.get("asset_id")
        }
        for image in visual.get("experimental_results_images", []):
            result_asset_spec = result_specs.get(str(image.get("id"))) or {}
            role = str(image.get("role") or "")
            minimum_width = 650 if role == "primary" else 420
            minimum_height = 120
            if image.get("object_fit") != "contain":
                issues.append(
                    {
                        "code": "RESULT_IMAGE_STRETCHED",
                        "severity": "error",
                        "message": "A result image is geometrically distorted.",
                        "details": image,
                        "return_to": "paper-poster-render",
                    }
                )
            content_scale = float(image.get("content_scale") or 0)
            if (
                result_asset_spec.get("asset_type") == "table"
                and content_scale > 1.05
            ):
                issues.append(
                    {
                        "code": "RESULT_IMAGE_UPSCALED",
                        "severity": "error",
                        "message": "A result image is enlarged beyond its natural pixel resolution.",
                        "details": image,
                        "return_to": "paper-experimental-results",
                    }
                )
            minimum_source_text_height = float(
                (
                    result_asset_spec.get("focus_crop") or {}
                ).get("minimum_source_text_height_px")
                or 0
            )
            focus_crop = result_asset_spec.get("focus_crop") or {}
            if (
                result_asset_spec.get("display_mode")
                == "pdf_text_focus_crop"
                and (
                    focus_crop.get("glyphs_touch_crop_edge") is not False
                    or float(focus_crop.get("edge_ink_ratio") or 0) > 0.02
                )
            ):
                issues.append(
                    {
                        "code": "RESULT_RENDER_GLYPH_CLIPPED",
                        "severity": "error",
                        "message": (
                            "Rendered result table uses a source crop whose "
                            "glyphs touch a crop boundary."
                        ),
                        "details": {
                            **image,
                            "edge_ink_ratio": focus_crop.get(
                                "edge_ink_ratio"
                            ),
                        },
                        "return_to": "paper-experimental-results",
                    }
                )
            if (
                minimum_source_text_height
                and content_scale
                and minimum_source_text_height * content_scale < 14
            ):
                issues.append(
                    {
                        "code": "RESULT_TABLE_TEXT_TOO_SMALL",
                        "severity": "error",
                        "message": "Focused table text remains below the Poster readability threshold.",
                        "details": {
                            **image,
                            "estimated_text_height_px": round(
                                minimum_source_text_height * content_scale,
                                2,
                            ),
                        },
                        "return_to": "paper-experimental-results",
                    }
                )
            if (
                float(image.get("rendered_width") or 0) < minimum_width
                or float(image.get("rendered_height") or 0) < minimum_height
            ):
                issues.append(
                    {
                        "code": "RESULT_ASSET_RENDER_UNREADABLE",
                        "severity": "error",
                        "message": "A selected result asset is unreadable at Poster size; do not shrink it further.",
                        "details": image,
                        "return_to": (
                            "paper-asset-select"
                            if not (
                                result_asset_spec.get("source_resolution") or {}
                            ).get(
                                "source_readable"
                            )
                            else "paper-poster-compose"
                        ),
                    }
                )
        for table in visual.get("experimental_results_focus_tables", []):
            if (
                float(table.get("minimum_font_px") or 0) < 14
                or int(table.get("rows") or 0) < 2
                or int(table.get("columns") or 0) < 2
            ):
                issues.append(
                    {
                        "code": "RESULT_FOCUS_TABLE_UNREADABLE",
                        "severity": "error",
                        "message": "Verified focus table is too small or lacks comparison context.",
                        "details": table,
                        "return_to": "paper-poster-compose",
                    }
                )
            if table.get("horizontal_overflow"):
                issues.append(
                    {
                        "code": "RESULT_FOCUS_TABLE_OVERFLOW",
                        "severity": "error",
                        "message": (
                            "Verified focus table exceeds its result panel; "
                            "reduce or compact columns instead of clipping them."
                        ),
                        "details": table,
                        "return_to": "paper-experimental-results",
                    }
                )
    for image in visual.get("missing_images", []):
        issues.append(
            {
                "code": "ASSET_IMAGE_LOAD_FAILED",
                "severity": "error",
                "message": f"Image failed to load: {image}",
                "return_to": "paper-poster-render",
            }
        )
    if visual.get("overflow_elements"):
        issues.append(
            {
                "code": "OVERFLOW_ELEMENTS",
                "severity": "error",
                "message": f"{len(visual['overflow_elements'])} poster elements overflow.",
                "details": visual["overflow_elements"],
                "return_to": "paper-poster-compose",
            }
        )
    if visual.get("overlap_pairs"):
        issues.append(
            {
                "code": "OVERLAP_PANELS",
                "severity": "error",
                "message": f"{len(visual['overlap_pairs'])} poster panel pairs overlap.",
                "details": visual["overlap_pairs"],
                "return_to": "paper-poster-render",
            }
        )

    if bundle.get("browser_export_requested"):
        for key in ("png_path", "pdf_path"):
            path_value = bundle.get(key)
            if not path_value or not Path(path_value).is_file():
                issues.append(
                    {
                        "code": "RENDER_EXPORT_MISSING",
                        "severity": "error",
                        "message": f"Required export {key} was not generated.",
                        "return_to": "paper-poster-render",
                    }
                )

    issues = _apply_delivery_severity_policy(
        issues,
        key_visual_item_count=len(visual_items),
        motivation_item_count=len(motivation_spec.get("items") or []),
        contribution_item_count=len(contribution_spec.get("items") or []),
    )
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [
        issue for issue in issues if issue.get("severity") == "warning"
    ]
    return_to = errors[0].get("return_to") if errors else None
    checks = {
        "story_assertions_have_sources": not any(
            issue["code"] == "STORY_SOURCE_MISSING" for issue in issues
        ),
        "numeric_mismatches": numeric_mismatches,
        "truncated_panel_text": truncated_panel_text,
        "captions_inspected": selected.get("captions_inspected"),
        "captions_expected": expected_captions,
        "figure_number_prior_used": selected.get("figure_number_prior_used"),
        "missing_assets": missing_assets,
        "method_nodes": len(method_nodes),
        "method_visual_mode": method_visual.get("mode"),
        "method_module_coverage": method_coverage,
        "method_assets": sorted(method_asset_ids),
        "method_result_asset_leaks": result_leaks,
        "method_overview_selection_basis": method_figure_map.get(
            "overview_selection_basis"
        ),
        "method_overview_selection_margin": method_figure_map.get(
            "overview_selection_margin"
        ),
        "method_overview_selection_ambiguous": method_figure_map.get(
            "overview_selection_ambiguous"
        ),
        "method_overview_ambiguity_rejected": bool(
            method_figure_map.get("overview_selection_ambiguous")
            and not method_visual.get("overview_asset_id")
        ),
        "method_overview_mode": expected_overview_mode,
        "method_overview_flow_items": len(
            overview_panel.get("flow_items") or []
        ),
        "method_storyboard_assets_expected": sorted(expected_storyboard_assets),
        "method_storyboard_assets_rendered": sorted(rendered_storyboard_assets),
        "method_storyboard_assets_missing": missing_rendered_method_assets,
        "key_idea_type": key_type,
        "key_idea_headline_words": headline_words,
        "key_idea_relevance": round(key_relevance, 3),
        "key_idea_source_claim_ids": sorted(source_claim_ids),
        "key_idea_source_block_ids": sorted(source_block_ids),
        "key_idea_equation_id": equation_id,
        "key_idea_equation_score": equation_score,
        "key_idea_equation_display_mode": equation_mode,
        "key_idea_word_count": key_word_count,
        "key_idea_inferred": bool(key_idea.get("inferred")),
        "experimental_results_layout": experimental_results.get(
            "layout_template"
        ),
        "experimental_results_metrics": len(
            experimental_results.get("key_metrics") or []
        ),
        "experimental_results_primary_asset": (
            experimental_results.get("primary_asset") or {}
        ).get("asset_id"),
        "experimental_results_secondary_asset": (
            experimental_results.get("secondary_asset") or {}
        ).get("asset_id"),
        "experimental_results_word_count": experimental_results.get(
            "visible_word_count"
        ),
        "highlights_selected": len(highlights.get("highlights") or []),
        "highlights_candidates": highlights.get("candidate_count"),
        "highlights_eligible_candidates": highlights.get(
            "eligible_candidate_count"
        ),
        "motivation_items": len(motivation_spec.get("items") or []),
        "contribution_items": len(contribution_spec.get("items") or []),
        "motivation_contribution_checks": motivation_contribution_checks,
        "supported_claims": sum(
            item.get("verdict") == "supported" for item in evidence.get("claims", [])
        ),
        "visual": visual,
        "html_exists": bool(html_path_value and Path(html_path_value).is_file()),
        "png_exists": bool(bundle.get("png_path") and Path(bundle["png_path"]).is_file()),
        "pdf_exists": bool(bundle.get("pdf_path") and Path(bundle["pdf_path"]).is_file()),
    }
    report = {
        "status": (
            "failed"
            if errors
            else "passed_with_warnings"
            if warnings
            else "passed"
        ),
        "delivery_status": (
            "blocked"
            if errors
            else "usable_with_warnings"
            if warnings
            else "passed"
        ),
        "checks": checks,
        "issues": issues,
        "return_to": return_to,
    }
    return write_json(output_dir / "final_qa_report.json", report)
