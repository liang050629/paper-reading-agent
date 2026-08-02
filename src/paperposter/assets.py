from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import compact_text, jaccard, normalize_text, read_json, write_json
from .method_figures import classify_figure_role

OVERVIEW_TERMS = {
    "overview": 4.0,
    "overall": 3.5,
    "framework": 3.2,
    "architecture": 3.2,
    "pipeline": 3.0,
    "workflow": 3.0,
    "proposed method": 2.8,
    "diagram": 1.5,
    "method": 2.0,
    "proposed": 1.2,
    "system": 1.5,
    "框架": 3.2,
    "总体": 3.5,
    "架构": 3.2,
    "流程": 3.0,
}
NEGATIVE_OVERVIEW_TERMS = {
    "ablation": -4.0,
    "qualitative": -2.5,
    "sensitivity": -3.0,
    "confusion matrix": -3.0,
    "dataset sample": -2.5,
    "visualization results": -2.0,
    "消融": -4.0,
    "敏感性": -3.0,
    "实验结果": -2.0,
}
RESULT_TERMS = (
    "result",
    "comparison",
    "ablation",
    "accuracy",
    "roc",
    "performance",
    "evaluation",
    "结果",
    "对比",
    "消融",
    "性能",
)


def _combined_text(asset: dict[str, Any]) -> str:
    return " ".join(
        str(asset.get(field) or "")
        for field in ("caption", "context_before", "context_after", "section_id")
    ).lower()


def _classify_figure(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
) -> dict[str, Any]:
    return classify_figure_role(asset, paper_ir)


def _overview_score(asset: dict[str, Any]) -> tuple[float, list[str]]:
    if asset.get("semantic_role") != "method_overview":
        return -10.0, ["semantic classifier rejects complete-system overview role"]
    text = _combined_text(asset)
    score = 0.0
    reasons: list[str] = []
    for term, weight in OVERVIEW_TERMS.items():
        if term in text:
            score += weight
            reasons.append(f"caption/context contains '{term}'")
    for term, weight in NEGATIVE_OVERVIEW_TERMS.items():
        if term in text:
            score += weight
            reasons.append(f"penalized as '{term}'")
    section = str(asset.get("section_id") or "").lower()
    if any(term in section for term in ("method", "approach", "framework", "architecture")):
        score += 2.0
        reasons.append("located in a method/approach section")
    cited_by = asset.get("cited_by") or []
    if cited_by:
        score += min(2.0, 0.35 * len(cited_by))
        reasons.append(f"cited by {len(cited_by)} sentence(s)")
    if not asset.get("path"):
        score -= 2.0
        reasons.append("no extracted local image")
    # Deliberately do not inspect the figure number. Figure 1 gets no prior.
    return round(score, 3), reasons


def _equation_score(asset: dict[str, Any]) -> tuple[float, list[str]]:
    text = _combined_text(asset)
    compact = re.sub(r"\s+", "", text)
    score = 0.0
    reasons: list[str] = []
    if "finalhybridloss" in compact or "weightedsumofthetwocomponents" in compact:
        score += 4.0
        reasons.append("context identifies the final combined loss")
    for term, weight in (
        ("objective", 3.0),
        ("loss", 2.5),
        ("final hybrid", 3.0),
        ("total", 2.2),
        ("optimization", 2.3),
        ("defined as", 1.8),
        ("mechanism", 2.0),
        ("weighted fusion", 3.0),
        ("weighted averaging", 2.8),
        ("fused expert", 2.0),
        ("memory bank", 1.8),
        ("router", 1.0),
        ("zoh", 3.0),
        ("discret", 2.5),
        ("state space", 1.2),
        ("目标函数", 3.0),
        ("损失", 2.5),
        ("定义为", 1.8),
    ):
        if term in text:
            score += weight
            reasons.append(f"context contains '{term}'")
    if asset.get("latex"):
        score += 1.5
        reasons.append("LaTeX is available")
    if asset.get("path"):
        score += 0.5
        reasons.append("screenshot fallback is available")
    return round(score, 3), reasons


def _catalog_item(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
) -> dict[str, Any]:
    item = dict(asset)
    if asset.get("asset_type") == "figure":
        classification = _classify_figure(asset, paper_ir)
        item["semantic_role"] = classification["role"]
        item["semantic_role_confidence"] = round(
            float(classification["confidence"]),
            3,
        )
        item["semantic_role_reasons"] = classification["reasons"]
        item["subfigure_semantics"] = classification[
            "subfigure_semantics"
        ]
        item["focus_subfigure_labels"] = classification[
            "focus_subfigure_labels"
        ]
        item["roles"] = [
            {
                "type": classification["role"],
                "confidence": item["semantic_role_confidence"],
            }
        ]
        score, reasons = _overview_score(item)
        item["overview_score"] = score
        item["overview_reasons"] = reasons
    elif asset.get("asset_type") == "equation":
        score, reasons = _equation_score(asset)
        item["key_equation_score"] = score
        item["key_equation_reasons"] = reasons
    return item


def select_assets(
    paper_ir_path: Path,
    evidence_path: Path,
    output_dir: Path,
    max_equations: int = 1,
    max_results: int = 1,
) -> tuple[Path, Path, Path]:
    paper_ir = read_json(paper_ir_path)
    evidence = read_json(evidence_path)
    figures = [
        _catalog_item(asset, paper_ir)
        for asset in paper_ir.get("figures", [])
    ]
    equations = [
        _catalog_item(asset, paper_ir)
        for asset in paper_ir.get("equations", [])
    ]
    tables = [
        _catalog_item(asset, paper_ir)
        for asset in paper_ir.get("tables", [])
    ]

    overview_candidates = sorted(
        (
            item
            for item in figures
            if item.get("semantic_role") == "method_overview"
        ),
        key=lambda item: item.get("overview_score", 0),
        reverse=True,
    )
    overview = None
    if overview_candidates and overview_candidates[0].get("overview_score", 0) >= 3.0:
        winner = overview_candidates[0]
        overview = {
            "id": winner["id"],
            "score": winner["overview_score"],
            "confidence": min(0.96, 0.5 + winner["overview_score"] / 20),
            "reason": winner["overview_reasons"],
            "path": winner.get("path"),
            "page": winner.get("page"),
            "visual_verification": "required",
        }

    equation_candidates = sorted(
        equations,
        key=lambda item: item.get("key_equation_score", 0),
        reverse=True,
    )
    selected_equations = [
        {
            "id": item["id"],
            "score": item.get("key_equation_score", 0),
            "reason": item.get("key_equation_reasons", []),
            "latex": item.get("latex"),
            "path": item.get("path"),
            "page": item.get("page"),
        }
        for item in equation_candidates[:max_equations]
        if item.get("key_equation_score", 0) >= 2.5
    ]

    supported_audits = [
        audit
        for audit in evidence.get("claims", [])
        if audit.get("verdict") in {"supported", "partially_supported"}
    ]
    result_candidates: list[tuple[float, dict[str, Any]]] = []
    for item in figures + tables:
        if item.get("asset_type") == "figure" and item.get(
            "semantic_role"
        ) in {
            "method_overview",
            "method_module",
            "mechanism",
            "mechanism_analysis",
        }:
            continue
        text = _combined_text(item)
        caption_text = str(item.get("caption") or "").lower()
        score = sum(1.2 for term in RESULT_TERMS if term in caption_text)
        section = str(item.get("section_id") or "").lower()
        if any(term in section for term in ("result", "experiment", "evaluation")):
            score += 1.2
        if (
            "existing method" in caption_text
            or "existingmethod" in caption_text
            or "state-of-the-art" in caption_text
        ):
            score += 2.0
        if item.get("asset_type") == "table":
            score += 0.8
        elif any(term in caption_text for term in ("comparison", "roc", "segmentation result")):
            score += 1.0
        if "visual comparison" in caption_text:
            score += 2.0
        if any(
            term in caption_text
            for term in (
                "architecture",
                "information flow",
                "linear computational complexity",
                "self-attention",
            )
        ):
            score -= 2.5
        if "ablation" in caption_text:
            score -= 1.5
        if any(
            term in caption_text
            for term in ("metrics for evaluation", "metric for evaluation", "dataset summary", "summarization")
        ):
            score -= 4.0
        source_claims = [
            audit["claim_id"]
            for audit in supported_audits
            if jaccard(str(audit.get("claim") or ""), text) >= 0.04
        ][:3]
        score += min(1.5, len(source_claims) * 0.5)
        if overview and item["id"] == overview["id"]:
            score -= 5
        if score > 0:
            candidate = dict(item)
            candidate["result_score"] = round(score, 3)
            candidate["source_claim_ids"] = source_claims
            result_candidates.append((score, candidate))
    result_candidates.sort(key=lambda pair: pair[0], reverse=True)
    ranked_items = [item for _, item in result_candidates]
    diverse_items: list[dict[str, Any]] = []
    if max_results == 1:
        # A single legible result is more useful on a fixed-size poster than
        # two unreadable thumbnails. Use the strongest caption-grounded item.
        diverse_items.extend(ranked_items[:1])
    else:
        best_table = next(
            (item for item in ranked_items if item.get("asset_type") == "table"),
            None,
        )
        if best_table is not None:
            diverse_items.append(best_table)
        diverse_items.extend(
            item
            for item in ranked_items
            if item.get("asset_type") == "figure" and item not in diverse_items
        )
        diverse_items.extend(item for item in ranked_items if item not in diverse_items)
    selected_results = [
        {
            "id": item["id"],
            "score": item["result_score"],
            "path": item.get("path"),
            "page": item.get("page"),
            "caption": normalize_text(item.get("caption", "")),
            "source_claim_ids": item.get("source_claim_ids", []),
        }
        for item in diverse_items[:max_results]
        if item.get("result_score", 0) >= 2.4
    ]

    catalog = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "figures": figures,
        "equations": equations,
        "tables": tables,
    }
    selected = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "captions_inspected": len(figures) + len(tables),
        "figure_number_prior_used": False,
        "overview_asset": overview,
        "overview_candidates": [
            {
                "id": item["id"],
                "score": item.get("overview_score", 0),
                "reason": item.get("overview_reasons", []),
            }
            for item in overview_candidates[:5]
        ],
        "key_equations": selected_equations,
        "result_assets": selected_results,
        "fallback": None if overview else "no-overview-figure",
    }
    report = {
        "status": "passed_with_warnings" if overview and overview["visual_verification"] == "required" else "passed",
        "figures_inspected": len(figures),
        "tables_inspected": len(tables),
        "equations_inspected": len(equations),
        "overview_selected": overview["id"] if overview else None,
        "warnings": (
            ["The top overview candidate requires visual verification before final submission."]
            if overview
            else ["No sufficiently supported overview figure was found; the poster must use a fallback."]
        ),
    }
    return (
        write_json(output_dir / "asset_catalog.json", catalog),
        write_json(output_dir / "selected_assets.json", selected),
        write_json(output_dir / "asset_selection_report.json", report),
    )
