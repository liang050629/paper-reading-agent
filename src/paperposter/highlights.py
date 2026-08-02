from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import jaccard, normalize_text, read_json, write_json
from .experimental_results import (
    _asset_block_ids,
    _asset_score,
    _number,
    _source_block_ids,
    _variant_label_parts,
    classify_asset,
    classify_claim,
    extract_key_metrics,
    parse_html_table,
)

SCORE_WEIGHTS = {
    "claim_relevance": 30,
    "evidence_strength": 20,
    "comparison_fairness": 20,
    "practical_significance": 15,
    "representativeness": 10,
    "memorability": 5,
}
PLACEHOLDER_RE = re.compile(
    r"^(?:reported|not stated|unknown|unspecified|paper-reported|"
    r"strongest reported|reported evaluation dataset)",
    re.I,
)
CONTRIBUTION_NUMBER_RE = re.compile(
    r"^\s*(?:contribution\s*)?(?:\(?[1-9]\)?[.):]|"
    r"(?:first|second|third|fourth)\s+contribution\b)",
    re.I,
)
GENERALIZATION_LANGUAGE_RE = re.compile(
    r"\b(?:consistent(?:ly)?|across all|all datasets|overall advantage|"
    r"universally|general(?:ly|izes?)|robust across)\b",
    re.I,
)
PERCENTAGE_METRICS = (
    "accuracy",
    "acc",
    "top-1",
    "top-5",
    "dice",
    "mdice",
    "dsc",
    "iou",
    "miou",
    "jaccard",
    "auc",
    "f1",
    "map",
    "precision",
    "recall",
    "oa",
    "aa",
    "kappa",
)
KNOWN_RAW_METRICS = (
    "psnr",
    "ssim",
    "hd95",
    "hausdorff",
    "mae",
    "rmse",
    "lpips",
    "latency",
    "memory",
    "flops",
    "macs",
    "parameter",
    "params",
    "throughput",
    "time",
)


def _words(value: str) -> list[str]:
    return re.findall(
        r"[+-]?\d+(?:\.\d+)?(?:%|pp)?|"
        r"[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*",
        value,
    )


def _clip_words(value: str, limit: int) -> str:
    return " ".join(_words(normalize_text(value))[:limit])


def _normalized(value: Any) -> str:
    return normalize_text(str(value or "")).lower()


def _explicit(value: Any) -> bool:
    text = normalize_text(str(value or ""))
    return bool(text and not PLACEHOLDER_RE.match(text))


def _metric_families(value: str) -> set[str]:
    lowered = _normalized(value)
    families: set[str] = set()
    patterns = {
        "accuracy": r"\b(?:accuracy|acc|top[- ]?[15]|oa|aa)\b",
        "iou": r"\b(?:miou|iou|jaccard)\b",
        "dice": r"\b(?:m?dice|dsc)\b",
        "f1": r"\bf1\b",
        "auc": r"\bauc\b",
        "map": r"\bmap(?:@\d+)?\b",
        "params": r"\b(?:parameters?|params?|#params?)\b",
        "flops": r"\b(?:flops?|macs?)\b",
        "latency": r"\b(?:latency|runtime|inference time|training time)\b",
        "throughput": r"\bthroughput\b",
        "memory": r"\b(?:memory|storage)\b",
        "psnr": r"\bpsnr\b",
        "ssim": r"\bssim\b",
        "error": r"\b(?:hd95|hausdorff|mae|rmse|lpips)\b",
    }
    for family, pattern in patterns.items():
        if re.search(pattern, lowered, re.I):
            families.add(family)
    return families


def _metric_source_kind(metric: Any, fallback: str) -> str:
    families = _metric_families(str(metric or ""))
    if families & {"params", "flops", "latency", "memory", "throughput"}:
        return "efficiency"
    if fallback == "efficiency":
        return "performance"
    return fallback


def _canonical_dataset(value: Any) -> str:
    normalized = _normalized(value)
    normalized = re.sub(r"^(?:the|a|an)\s+", "", normalized)
    normalized = re.sub(r"\b(?:dataset|benchmark)\b", "", normalized)
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _dataset_markers(value: str) -> set[str]:
    markers = {
        match.group(1).lower()
        for match in re.finditer(
            r"\b([A-Za-z][A-Za-z0-9_-]{1,30})\s+"
            r"(?:dataset|benchmark)\b",
            value,
            re.I,
        )
    }
    return {
        marker
        for marker in markers
        if marker not in {"the", "same", "training", "test", "validation"}
    }


def _highlight_source_context(
    claim: dict[str, Any],
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
) -> str:
    block_ids = {
        str(value)
        for value in [
            *_source_block_ids(claim),
            *_asset_block_ids(asset, paper_ir),
        ]
        if value
    }
    block_text = [
        str(block.get("text") or "")
        for block in paper_ir.get("blocks", [])
        if str(block.get("id") or "") in block_ids
    ]
    return normalize_text(
        " ".join(
            [
                str(claim.get("claim") or ""),
                str(asset.get("caption") or ""),
                str(asset.get("context_before") or ""),
                str(asset.get("context_after") or ""),
                *block_text,
            ]
        )
    )


def _recover_dataset_name(
    current: Any,
    source_context: str,
) -> str:
    if _explicit(current):
        return normalize_text(str(current))
    patterns = (
        r"\b([A-Z][A-Za-z0-9_-]{2,30})\s+(?:dataset|benchmark)s?\b",
        r"\b(?:on|from|using)\s+(?:the\s+)?"
        r"([A-Z][A-Z0-9_-]{2,30})\b"
        r"(?=\s+(?:with|without|under|dataset|benchmark|test|validation)|[,.;])",
    )
    rejected = {
        "ACC",
        "AUC",
        "BCE",
        "CNN",
        "CPU",
        "DSC",
        "FLOPS",
        "FOV",
        "GPU",
        "IOU",
        "MCC",
        "PSNR",
        "SSIM",
    }
    for pattern in patterns:
        for match in re.finditer(pattern, source_context):
            value = normalize_text(match.group(1)).strip(" ,;:.")
            if (
                value
                and value[0].isupper()
                and value.upper() not in rejected
            ):
                return value
    return normalize_text(str(current or ""))


def _recover_evaluation_condition(
    current: Any,
    source_context: str,
) -> str:
    if _explicit(current):
        return normalize_text(str(current))
    fragments: list[str] = []
    patterns = (
        r"\bprimary\s+evaluation\s+protocol\b",
        r"\bofficial\s+(?:test|validation)\s+(?:split|set)\b",
        r"\b(?:without|with)\s+(?:an?\s+)?FOV(?:\s+mask(?:ing)?)?\b",
        r"\b(?:without|with|after|before)\s+(?:recovery|retraining)\b",
        r"\b\d+\s*[- ]fold\s+cross[- ]validation\b",
    )
    for pattern in patterns:
        match = re.search(pattern, source_context, re.I)
        if match:
            fragment = normalize_text(match.group(0))
            if fragment.lower() not in {value.lower() for value in fragments}:
                fragments.append(fragment)
    return " ".join(fragments)


def _comparison_base_label(value: Any) -> str:
    base, _ = _variant_label_parts(str(value or ""))
    return _normalized(base)


def _condition_fragment(value: str, kind: str) -> str:
    patterns = {
        "recovery": r"\b(?:without|with|after|before)\s+(?:recovery|retraining)\b",
        "fine_tuning": r"\b(?:without|with|after|before)\s+fine[- ]?tun(?:e|ing)\b",
        "split": r"\b(?:train|test|validation)\s+(?:split|set)\b[^,;.]*",
        "protocol": r"\b(?:cross[- ]validation|fold|protocol|checkpoint)\b[^,;.]*",
    }
    match = re.search(patterns[kind], value, re.I)
    return normalize_text(match.group(0)) if match else "same source-table block"


def recompute_improvement(
    primary_value: str,
    baseline_value: str,
    metric: str,
    metric_direction: str,
) -> dict[str, Any]:
    ours = _number(primary_value)
    baseline = _number(baseline_value)
    if (
        ours is None
        or baseline is None
        or baseline == 0
        or metric_direction not in {"higher_is_better", "lower_is_better"}
    ):
        return {"valid": False, "reason": "numeric values or direction are invalid"}
    ours_percent = "%" in primary_value
    baseline_percent = "%" in baseline_value
    if ours_percent != baseline_percent:
        return {"valid": False, "reason": "percentage units do not match"}

    lowered_metric = _normalized(metric)
    percentage_metric = any(
        re.search(rf"\b{re.escape(term)}\b", lowered_metric)
        for term in PERCENTAGE_METRICS
    )
    if ours_percent:
        scale = "percentage"
        multiplier = 1.0
        unit = "percentage_points"
    elif percentage_metric and 0 <= ours <= 1 and 0 <= baseline <= 1:
        scale = "ratio"
        multiplier = 100.0
        unit = "percentage_points"
    elif percentage_metric and 0 <= ours <= 100 and 0 <= baseline <= 100:
        scale = "percentage"
        multiplier = 1.0
        unit = "percentage_points"
    elif any(term in lowered_metric for term in KNOWN_RAW_METRICS):
        scale = "raw"
        multiplier = 1.0
        unit = "metric_units"
    else:
        return {"valid": False, "reason": "metric unit or percentage scale is unclear"}

    signed_raw = ours - baseline
    if metric_direction == "lower_is_better":
        signed_raw = baseline - ours
    absolute = signed_raw * multiplier
    relative = signed_raw / abs(baseline) * 100.0
    if unit == "percentage_points":
        display = f"{absolute:+.2f} pp"
    else:
        display = f"{absolute:+.4g}"
    return {
        "valid": True,
        "primary_numeric": ours,
        "baseline_numeric": baseline,
        "scale": scale,
        "absolute_difference": round(absolute, 6),
        "absolute_difference_type": unit,
        "absolute_difference_display": display,
        "relative_difference_percent": round(relative, 6),
    }


def _gate(
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {"passed": bool(passed), "reason": reason}


def evaluate_highlight_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    result = dict(candidate)
    source_cell = candidate.get("source_cell") or {}
    baseline_cell = candidate.get("baseline_cell") or {}
    traceable = bool(
        candidate.get("source_asset_id")
        and candidate.get("source_asset_type") in {"table", "figure"}
        and int(candidate.get("page") or 0) >= 1
        and isinstance(source_cell.get("row_index"), int)
        and isinstance(source_cell.get("column_index"), int)
        and isinstance(baseline_cell.get("row_index"), int)
        and isinstance(baseline_cell.get("column_index"), int)
        and candidate.get("source_block_ids")
        and normalize_text(str(source_cell.get("extracted_value") or ""))
        == normalize_text(str(candidate.get("primary_value") or ""))
        and normalize_text(str(baseline_cell.get("extracted_value") or ""))
        == normalize_text(str(candidate.get("baseline_value") or ""))
    )

    context_fields = (
        "primary_value",
        "metric",
        "dataset",
        "configuration",
        "baseline",
        "evaluation_condition",
        "metric_direction",
    )
    context_complete = all(_explicit(candidate.get(field)) for field in context_fields)
    context_complete = context_complete and _explicit(candidate.get("baseline_value"))

    ours_condition = candidate.get("ours_condition") or {}
    baseline_condition = candidate.get("baseline_condition") or {}
    comparison_keys = (
        "dataset",
        "split",
        "metric",
        "protocol",
        "fine_tuning",
        "recovery",
    )
    matched_comparison = all(
        _explicit(ours_condition.get(key))
        and _normalized(ours_condition.get(key))
        == _normalized(baseline_condition.get(key))
        for key in comparison_keys
    )
    matched_comparison = matched_comparison and all(
        _explicit(candidate.get(field))
        for field in ("configuration", "baseline_configuration")
    )
    if candidate.get("comparison_pair_kind") == "paired_base_variant":
        matched_comparison = matched_comparison and bool(
            _comparison_base_label(candidate.get("row_label"))
            and _comparison_base_label(candidate.get("row_label"))
            == _comparison_base_label(candidate.get("baseline_row_label"))
        )

    arithmetic = recompute_improvement(
        str(candidate.get("primary_value") or ""),
        str(candidate.get("baseline_value") or ""),
        str(candidate.get("metric") or ""),
        str(candidate.get("metric_direction") or ""),
    )
    arithmetic_valid = bool(arithmetic.get("valid"))

    claim_text = normalize_text(str(candidate.get("claim_text") or ""))
    allowed_non_matrix_source = candidate.get("source_kind") in {
        "main_results",
        "performance",
        "efficiency",
        "generalization",
        "robustness",
        "abstract",
        "conclusion",
    }
    upstream_claim_binding = bool(candidate.get("upstream_claim_binding"))
    claim_aligned = bool(
        candidate.get("claim_id")
        and (
            candidate.get("claim_verdict") == "supported"
            or (
                candidate.get("claim_verdict") == "partially_supported"
                and upstream_claim_binding
            )
            or (allowed_non_matrix_source and traceable)
        )
        and candidate.get("claim_metric_aligned", True)
        and candidate.get("claim_dataset_aligned", True)
        and (
            upstream_claim_binding
            or float(candidate.get("claim_alignment_score") or 0) >= 0.12
        )
        and not CONTRIBUTION_NUMBER_RE.match(claim_text)
    )
    zero_efficiency_constraint = bool(
        candidate.get("source_kind") == "efficiency"
        and arithmetic_valid
        and float(arithmetic.get("absolute_difference") or 0) == 0
    )
    if zero_efficiency_constraint:
        claim_aligned = claim_aligned and bool(
            candidate.get("constraint_preservation_supported")
        )

    generalized_claim = bool(GENERALIZATION_LANGUAGE_RE.search(claim_text))
    dataset_count = int(candidate.get("dataset_count") or 1)
    trends_consistent = bool(candidate.get("trends_consistent", True))
    representative = not generalized_claim or (
        dataset_count >= 2 and trends_consistent
    )

    required_caveats = {
        normalize_text(str(value))
        for value in candidate.get("required_caveats", [])
        if normalize_text(str(value))
    }
    caveats = {
        normalize_text(str(value))
        for value in candidate.get("caveats", [])
        if normalize_text(str(value))
    }
    caveat_complete = required_caveats.issubset(caveats)

    gate_results = {
        "traceability_gate": _gate(
            traceable,
            "source asset, exact cells, page, and source blocks are bound",
        ),
        "context_gate": _gate(
            context_complete,
            "value, metric, dataset, configuration, baseline, condition, and direction are explicit",
        ),
        "matched_comparison_gate": _gate(
            matched_comparison,
            "method and baseline share dataset, split, metric, protocol, fine-tuning, and recovery",
        ),
        "arithmetic_gate": _gate(
            arithmetic_valid,
            str(arithmetic.get("reason") or "differences recomputed from source values"),
        ),
        "claim_alignment_gate": _gate(
            claim_aligned,
            "candidate binds a supported core Claim without contribution numbering",
        ),
        "representativeness_gate": _gate(
            representative,
            "scope wording is no broader than the available dataset evidence",
        ),
        "caveat_gate": _gate(
            caveat_complete,
            "all interpretation-changing conditions are retained",
        ),
    }
    all_gates = all(item["passed"] for item in gate_results.values())

    scores = {
        "claim_relevance": min(
            5.0,
            3.0
            + float(candidate.get("is_core_claim", False))
            + float(candidate.get("is_main_result", False)),
        ),
        "evidence_strength": 5.0 if traceable else 0.0,
        "comparison_fairness": (
            5.0
            if matched_comparison and candidate.get("baseline_is_strong", False)
            else (3.0 if matched_comparison else 0.0)
        ),
        "practical_significance": (
            5.0
            if (
                candidate.get("claim_category")
                in {"efficiency", "generalization", "robustness"}
                or candidate.get("source_kind")
                in {"efficiency", "generalization", "robustness"}
            )
            else (4.0 if arithmetic_valid and arithmetic["relative_difference_percent"] > 0 else 2.0)
        ),
        "representativeness": (
            5.0 if dataset_count >= 2 and trends_consistent else (3.0 if representative else 0.0)
        ),
        "memorability": (
            5.0
            if len(_words(str(candidate.get("primary_value") or ""))) <= 4
            else 3.0
        ),
    }
    weighted = sum(
        scores[name] / 5.0 * weight
        for name, weight in SCORE_WEIGHTS.items()
    )
    penalties: list[dict[str, Any]] = []

    def penalize(code: str, points: int, active: bool) -> None:
        nonlocal weighted
        if active:
            weighted -= points
            penalties.append({"code": code, "points": -points})

    penalize(
        "single_favorable_dataset_inconsistent_elsewhere",
        10,
        dataset_count == 1 and not trends_consistent,
    )
    penalize("ablation_only", 10, bool(candidate.get("is_ablation")))
    penalize(
        "non_strong_baseline",
        15,
        not bool(candidate.get("baseline_is_strong")),
    )
    penalize(
        "fine_tuning_or_recovery_mismatch",
        20,
        not matched_comparison,
    )
    penalize(
        "conflicting_experiment_trend",
        15,
        not trends_consistent,
    )
    penalize(
        "significance_not_verified",
        15,
        bool(candidate.get("claims_significance"))
        and not bool(candidate.get("significance_reported")),
    )
    weighted_total = round(max(0.0, min(100.0, weighted)), 2)
    if not all_gates:
        classification = "reject"
    elif weighted_total >= 85:
        classification = "strong_highlight"
    elif weighted_total >= 75:
        classification = "eligible_highlight"
    elif weighted_total >= 60:
        classification = "results_only"
    else:
        classification = "reject"

    result.update(arithmetic)
    result["gate_results"] = gate_results
    result["scores"] = {
        **scores,
        "weighted_total": weighted_total,
        "classification": classification,
        "penalties": penalties,
    }
    result["eligible"] = classification in {
        "strong_highlight",
        "eligible_highlight",
    }
    return result


def _semantic_key(candidate: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _normalized(candidate.get("metric")),
        _canonical_dataset(candidate.get("dataset")),
        _normalized(candidate.get("configuration")),
        _normalized(candidate.get("claim_category")),
    )


def _display_item(candidate: dict[str, Any], role: str) -> dict[str, Any]:
    metric = normalize_text(str(candidate.get("metric") or "Result"))
    dataset = normalize_text(str(candidate.get("dataset") or "dataset"))
    baseline = normalize_text(str(candidate.get("baseline") or "baseline"))
    configuration = normalize_text(str(candidate.get("configuration") or ""))
    if role == "improvement_over_baseline":
        primary_value = str(candidate.get("absolute_difference_display") or "")
        label = _clip_words(f"{metric} gain over baseline", 6)
    elif (
        role == "efficiency_or_generalization_or_robustness"
        and candidate.get("source_kind") == "efficiency"
        and float(candidate.get("absolute_difference") or 0) == 0
    ):
        metric_label = (
            "parameters"
            if _metric_families(metric) == {"params"}
            else metric
        )
        primary_value = _clip_words(f"No extra {metric_label}", 4)
        label = _clip_words("Matched inference budget", 6)
    else:
        primary_value = normalize_text(str(candidate.get("primary_value") or ""))
        label = _clip_words(f"{metric} on {dataset}", 6)
    improvement = normalize_text(
        str(candidate.get("absolute_difference_display") or "")
    )
    context_parts = [f"vs {baseline}"]
    if role == "primary_effectiveness" and improvement:
        context_parts.append(improvement)
    context_parts.append(configuration)
    context = _clip_words("; ".join(context_parts), 10)
    return {
        "role": role,
        "primary_value": primary_value,
        "label": label,
        "context": context,
        "claim_id": candidate.get("claim_id"),
        "evidence_id": candidate.get("evidence_id"),
        "claim_verdict": candidate.get("claim_verdict"),
        "source_kind": candidate.get("source_kind"),
        "source_asset_type": candidate.get("source_asset_type"),
        "source_asset_id": candidate.get("source_asset_id"),
        "page": candidate.get("page"),
        "row": {
            "index": (candidate.get("source_cell") or {}).get("row_index"),
            "label": candidate.get("row_label"),
        },
        "column": {
            "index": (candidate.get("source_cell") or {}).get("column_index"),
            "label": candidate.get("column_label"),
        },
        "dataset": dataset,
        "configuration": configuration,
        "baseline": baseline,
        "baseline_value": candidate.get("baseline_value"),
        "evaluation_condition": candidate.get("evaluation_condition"),
        "metric": metric,
        "metric_direction": candidate.get("metric_direction"),
        "absolute_difference": candidate.get("absolute_difference"),
        "absolute_difference_type": candidate.get("absolute_difference_type"),
        "relative_difference_percent": candidate.get(
            "relative_difference_percent"
        ),
        "source_cell": candidate.get("source_cell"),
        "baseline_cell": candidate.get("baseline_cell"),
        "source_block_ids": candidate.get("source_block_ids", []),
        "gate_results": candidate.get("gate_results"),
        "scores": candidate.get("scores"),
        "caveats": candidate.get("caveats", []),
        "claim_text": candidate.get("claim_text"),
        "dataset_count": candidate.get("dataset_count"),
        "trends_consistent": candidate.get("trends_consistent"),
    }


def select_highlights_from_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evaluated = [
        candidate
        if "gate_results" in candidate
        else evaluate_highlight_candidate(candidate)
        for candidate in candidates
    ]
    eligible = sorted(
        (candidate for candidate in evaluated if candidate.get("eligible")),
        key=lambda item: (
            float((item.get("scores") or {}).get("weighted_total") or 0),
            bool(item.get("is_main_result")),
            bool(item.get("is_core_claim")),
        ),
        reverse=True,
    )
    chosen: list[dict[str, Any]] = []
    keys: set[tuple[str, str, str, str]] = set()

    def take(predicate: Any, role: str) -> None:
        for candidate in eligible:
            key = _semantic_key(candidate)
            if candidate in chosen or key in keys or not predicate(candidate):
                continue
            if any(
                (
                    bool(_metric_families(str(candidate.get("metric") or "")))
                    and _metric_families(str(candidate.get("metric") or ""))
                    == _metric_families(str(prior.get("metric") or ""))
                    and _canonical_dataset(candidate.get("dataset"))
                    == _canonical_dataset(prior.get("dataset"))
                )
                or jaccard(
                    f"{candidate.get('metric')} {candidate.get('dataset')}",
                    f"{prior.get('metric')} {prior.get('dataset')}",
                )
                >= 0.9
                for prior in chosen
            ):
                continue
            chosen.append(candidate)
            keys.add(key)
            candidate["_selected_role"] = role
            return

    take(
        lambda item: item.get("claim_category") not in {"efficiency", "generalization", "robustness"}
        and item.get("source_kind") not in {"efficiency", "generalization", "robustness"}
        and not item.get("is_ablation"),
        "primary_effectiveness",
    )
    take(
        lambda item: item.get("claim_category") not in {"efficiency", "generalization", "robustness"}
        and item.get("source_kind") not in {"efficiency", "generalization", "robustness"}
        and not item.get("is_ablation"),
        "improvement_over_baseline",
    )
    take(
        lambda item: (
            item.get("claim_category")
            in {"efficiency", "generalization", "robustness"}
            or item.get("source_kind")
            in {"efficiency", "generalization", "robustness"}
        ),
        "efficiency_or_generalization_or_robustness",
    )
    return [
        _display_item(candidate, str(candidate["_selected_role"]))
        for candidate in chosen[:3]
    ], evaluated


def _candidate_from_metric(
    metric: dict[str, Any],
    claim: dict[str, Any],
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
    *,
    source_kind: str,
    is_main_result: bool,
    upstream_claim_binding: bool = False,
) -> dict[str, Any]:
    claim_text = normalize_text(str(claim.get("claim") or ""))
    asset_text = normalize_text(
        str(asset.get("caption") or "")
    )
    source_context = _highlight_source_context(claim, asset, paper_ir)
    dataset = _recover_dataset_name(metric.get("dataset"), claim_text)
    if not _explicit(dataset):
        dataset = _recover_dataset_name("", asset_text)
    if not _explicit(dataset):
        dataset = _recover_dataset_name("", source_context)
    ablation_asset = classify_asset(asset) == "ablation" or bool(
        re.search(
            r"\b(?:ablation|dif{1,2}erent modules?|module contributions?|"
            r"component contributions?|with and without|w/o)\b",
            asset_text,
            re.I,
        )
    )
    configuration = normalize_text(str(metric.get("configuration") or ""))
    if PLACEHOLDER_RE.match(configuration):
        configuration = ""
    if not configuration:
        row_label = normalize_text(str(metric.get("row_label") or ""))
        if _explicit(row_label):
            configuration = f"{row_label} configuration"
    evaluation_condition = normalize_text(str(metric.get("evaluation_condition") or ""))
    if PLACEHOLDER_RE.match(evaluation_condition):
        evaluation_condition = ""
    if not evaluation_condition:
        evaluation_condition = _recover_evaluation_condition(
            "",
            claim_text,
        )
    if not evaluation_condition:
        evaluation_condition = _recover_evaluation_condition("", source_context)
    if not evaluation_condition and dataset and asset.get("id"):
        evaluation_condition = (
            f"shared {dataset} evaluation within {asset.get('id')}"
        )
    baseline_configuration = normalize_text(str(metric.get("baseline_configuration") or ""))
    if PLACEHOLDER_RE.match(baseline_configuration):
        baseline_configuration = ""
    if not baseline_configuration:
        baseline_label = normalize_text(
            str(metric.get("baseline_row_label") or metric.get("baseline") or "")
        )
        if _explicit(baseline_label):
            baseline_configuration = f"{baseline_label} configuration"
    baseline_evaluation = normalize_text(
        str(metric.get("baseline_evaluation_condition") or evaluation_condition)
    )
    if PLACEHOLDER_RE.match(baseline_evaluation):
        baseline_evaluation = ""
    if not baseline_evaluation:
        baseline_evaluation = evaluation_condition
    source_cell = metric.get("source_cell") or {}
    baseline_cell = metric.get("baseline_cell") or {}
    claim_metric_families = _metric_families(claim_text)
    candidate_metric_families = _metric_families(
        str(metric.get("metric") or "")
    )
    claim_metric_aligned = bool(
        not claim_metric_families
        or claim_metric_families & candidate_metric_families
    )
    claim_dataset_markers = _dataset_markers(claim_text)
    candidate_dataset_text = normalize_text(
        " ".join(
            [
                dataset,
                str(asset.get("caption") or ""),
                str(asset.get("context_before") or ""),
                str(asset.get("context_after") or ""),
            ]
        )
    ).lower()
    claim_dataset_aligned = bool(
        not claim_dataset_markers
        or any(
            marker in candidate_dataset_text
            for marker in claim_dataset_markers
        )
    )
    evidence_id = (
        f"{claim.get('claim_id')}:{asset.get('id')}:"
        f"r{source_cell.get('row_index')}c{source_cell.get('column_index')}"
    )
    condition_text = f"{configuration} {evaluation_condition}"
    ours_condition = {
        "dataset": dataset,
        "split": _condition_fragment(condition_text, "split"),
        "metric": metric.get("metric"),
        "protocol": _condition_fragment(condition_text, "protocol"),
        "fine_tuning": _condition_fragment(condition_text, "fine_tuning"),
        "recovery": _condition_fragment(condition_text, "recovery"),
    }
    baseline_condition = {
        "dataset": dataset,
        "split": _condition_fragment(baseline_evaluation, "split"),
        "metric": metric.get("metric"),
        "protocol": _condition_fragment(baseline_evaluation, "protocol"),
        "fine_tuning": _condition_fragment(
            f"{baseline_configuration} {baseline_evaluation}",
            "fine_tuning",
        ),
        "recovery": _condition_fragment(
            f"{baseline_configuration} {baseline_evaluation}",
            "recovery",
        ),
    }
    required_caveats = [configuration, evaluation_condition]
    effective_source_kind = _metric_source_kind(
        metric.get("metric"),
        source_kind,
    )
    return {
        "candidate_id": evidence_id,
        "claim_id": claim.get("claim_id"),
        "evidence_id": evidence_id,
        "claim_text": claim_text,
        "claim_verdict": claim.get("verdict"),
        "claim_category": classify_claim(claim),
        "source_kind": effective_source_kind,
        "source_asset_type": asset.get("asset_type"),
        "source_asset_id": asset.get("id"),
        "page": asset.get("page"),
        "bbox": asset.get("bbox"),
        "source_block_ids": list(
            dict.fromkeys(
                [
                    *(metric.get("source_block_ids") or []),
                    *_source_block_ids(claim),
                ]
            )
        ),
        "primary_value": metric.get("value"),
        "baseline_value": metric.get("baseline_value"),
        "metric": metric.get("metric"),
        "metric_direction": metric.get("direction"),
        "dataset": dataset,
        "configuration": configuration,
        "baseline": metric.get("baseline"),
        "baseline_configuration": baseline_configuration,
        "evaluation_condition": evaluation_condition,
        "baseline_evaluation_condition": baseline_evaluation,
        "source_cell": source_cell,
        "baseline_cell": baseline_cell,
        "row_label": metric.get("row_label"),
        "baseline_row_label": metric.get("baseline_row_label"),
        "column_label": metric.get("column_label"),
        "ours_condition": ours_condition,
        "baseline_condition": baseline_condition,
        "is_core_claim": claim.get("verdict") == "supported",
        "is_main_result": is_main_result,
        "is_ablation": ablation_asset,
        "baseline_is_strong": metric.get("baseline_selection")
        in {"strongest_matched", "paired_base_variant"},
        "comparison_pair_kind": metric.get("baseline_selection"),
        "claim_metric_aligned": claim_metric_aligned,
        "claim_dataset_aligned": claim_dataset_aligned,
        "upstream_claim_binding": upstream_claim_binding,
        "constraint_preservation_supported": bool(
            re.search(
                r"\b(?:without|no)\s+"
                r"(?:(?:incurring|adding|requiring)\s+)?"
                r"(?:any\s+)?(?:additional|extra|added)\b|"
                r"\b(?:same|unchanged|matched|preserv(?:e|es|ing|ed))\b"
                r".{0,24}\b(?:parameters?|params?|flops?|latency|memory|"
                r"runtime|throughput|overhead|cost)\b",
                claim_text,
                re.I,
            )
        ),
        "claim_alignment_score": max(
            (
                jaccard(claim_text, asset_text)
                if claim_metric_aligned and claim_dataset_aligned
                else 0.0
            ),
            (
                0.2
                if claim_metric_aligned
                and claim_dataset_aligned
                and classify_claim(claim) == classify_asset(asset)
                else 0.0
            ),
        ),
        "claims_significance": bool(re.search(r"\bsignificant(?:ly)?\b", claim_text, re.I)),
        "significance_reported": bool(
            re.search(r"\b(?:p\s*[<=>]|confidence interval|statistically significant)\b", asset_text, re.I)
        ),
        "required_caveats": required_caveats,
        "caveats": list(required_caveats),
        "dataset_count": 1,
        "trends_consistent": True,
    }


def _allowed_asset(asset: dict[str, Any]) -> bool:
    value = _normalized(
        str(asset.get("caption") or "")
    )
    if asset.get("asset_type") != "table" or not asset.get("html"):
        return False
    if any(
        term in value
        for term in (
            "related work",
            "experimental setting",
            "implementation detail",
            "hyperparameter",
            "parameter setting",
        )
    ):
        return False
    return True


def _highlight_source_kind(asset: dict[str, Any]) -> str:
    value = _normalized(
        str(asset.get("caption") or "")
    )
    if any(
        term in value
        for term in (
            "parameter",
            "params",
            "flops",
            "latency",
            "memory",
            "inference time",
            "throughput",
            "computational cost",
        )
    ):
        return "efficiency"
    return classify_asset(asset)


def _collect_candidates(
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    evidence: dict[str, Any],
    experimental_results: dict[str, Any],
) -> list[dict[str, Any]]:
    primary_spec = experimental_results.get("primary_asset") or {}
    primary_claim_ids = set(primary_spec.get("source_claim_ids") or [])
    claims = [
        claim
        for claim in evidence.get("claims", [])
        if (
            claim.get("verdict") == "supported"
            or (
                claim.get("verdict") == "partially_supported"
                and (
                    claim.get("claim_id") in primary_claim_ids
                    or bool(re.search(r"\d", str(claim.get("claim") or "")))
                )
            )
        )
        and not CONTRIBUTION_NUMBER_RE.match(
            normalize_text(str(claim.get("claim") or ""))
        )
    ]
    assets = {
        str(asset.get("id")): asset
        for asset in paper_ir.get("tables", [])
        if _allowed_asset(asset)
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary_id = str(primary_spec.get("asset_id") or "")
    primary_asset = assets.get(primary_id)

    for claim in claims:
        source_ids = list(
            dict.fromkeys(
                [
                    *_source_block_ids(claim),
                    *(
                        _asset_block_ids(primary_asset, paper_ir)
                        if primary_asset
                        else []
                    ),
                ]
            )
        )
        if primary_asset and (
            not primary_claim_ids
            or claim.get("claim_id") in primary_claim_ids
            or claim.get("verdict") == "supported"
        ):
            metrics = extract_key_metrics(
                primary_asset,
                claim,
                paper_ir,
                story,
                source_ids,
                limit=8,
            )
            for metric in metrics:
                candidate = _candidate_from_metric(
                    metric,
                    claim,
                    primary_asset,
                    paper_ir,
                    source_kind="main_results",
                    is_main_result=True,
                    upstream_claim_binding=(
                        not primary_claim_ids
                        or claim.get("claim_id") in primary_claim_ids
                    ),
                )
                if candidate["candidate_id"] not in seen:
                    candidates.append(candidate)
                    seen.add(candidate["candidate_id"])

    for claim in claims:
        for asset in assets.values():
            if str(asset.get("id")) == primary_id:
                continue
            asset_score, _ = _asset_score(asset, claim, primary=False)
            asset_text = normalize_text(
                f"{asset.get('caption') or ''} {asset.get('context_before') or ''} "
                f"{asset.get('context_after') or ''}"
            )
            if (
                asset_score < 2.5
                and classify_claim(claim) != classify_asset(asset)
                and jaccard(str(claim.get("claim") or ""), asset_text) < 0.05
            ):
                continue
            source_ids = list(
                dict.fromkeys(
                    [*_source_block_ids(claim), *_asset_block_ids(asset, paper_ir)]
                )
            )
            metrics = extract_key_metrics(
                asset,
                claim,
                paper_ir,
                story,
                source_ids,
                limit=8,
            )
            for metric in metrics:
                candidate = _candidate_from_metric(
                    metric,
                    claim,
                    asset,
                    paper_ir,
                    source_kind=_highlight_source_kind(asset),
                    is_main_result=False,
                )
                if candidate["candidate_id"] not in seen:
                    candidates.append(candidate)
                    seen.add(candidate["candidate_id"])

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = (
            _normalized(candidate.get("source_asset_id")),
            _normalized(candidate.get("metric")),
            _normalized(candidate.get("configuration")),
        )
        groups.setdefault(key, []).append(candidate)
    for group in groups.values():
        datasets = {
            _normalized(candidate.get("dataset"))
            for candidate in group
            if _explicit(candidate.get("dataset"))
        }
        arithmetic = [
            recompute_improvement(
                str(candidate.get("primary_value") or ""),
                str(candidate.get("baseline_value") or ""),
                str(candidate.get("metric") or ""),
                str(candidate.get("metric_direction") or ""),
            )
            for candidate in group
        ]
        trends_consistent = all(
            item.get("valid")
            and float(item.get("relative_difference_percent") or 0) >= 0
            for item in arithmetic
        )
        for candidate in group:
            candidate["dataset_count"] = max(1, len(datasets))
            candidate["trends_consistent"] = trends_consistent
    return candidates


def validate_highlights_spec(
    spec: dict[str, Any],
    paper_ir: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    highlights = spec.get("highlights") or []
    if not highlights:
        issues.append(
            {
                "code": "HIGHLIGHT_EVIDENCE_INSUFFICIENT",
                "severity": "warning",
                "message": (
                    "No context-complete, traceable Highlight survived the "
                    "evidence Gates and recovery pass. Keep the verified "
                    "Experimental Results panel and omit Highlights rather "
                    "than inventing a weak card."
                ),
                "details": {
                    "candidate_count": int(spec.get("candidate_count") or 0),
                    "eligible_candidate_count": int(
                        spec.get("eligible_candidate_count") or 0
                    ),
                },
                "return_to": "paper-highlights",
            }
        )
    if len(highlights) > 3:
        issues.append(
            {
                "code": "HIGHLIGHT_COUNT_INVALID",
                "severity": "error",
                "message": "Highlights may contain at most three verified results.",
                "return_to": "paper-highlights",
            }
        )
    claims = {
        str(claim.get("claim_id")): claim
        for claim in evidence.get("claims", [])
        if claim.get("claim_id")
    }
    assets = {
        str(asset.get("id")): asset
        for group in ("tables", "figures")
        for asset in paper_ir.get(group, [])
        if asset.get("id")
    }
    semantic_keys: set[tuple[str, str, str]] = set()
    for item in highlights:
        missing = [
            field
            for field in (
                "primary_value",
                "label",
                "context",
                "claim_id",
                "evidence_id",
                "source_asset_id",
                "page",
                "row",
                "column",
                "dataset",
                "configuration",
                "baseline",
                "metric_direction",
                "absolute_difference",
                "relative_difference_percent",
                "gate_results",
                "scores",
                "caveats",
            )
            if item.get(field) in (None, "", [])
        ]
        if missing:
            issues.append(
                {
                    "code": "HIGHLIGHT_FIELDS_MISSING",
                    "severity": "error",
                    "message": "A Highlight lacks required context or provenance.",
                    "details": missing,
                    "return_to": "paper-highlights",
                }
            )
            continue
        if any(
            not gate.get("passed")
            for gate in (item.get("gate_results") or {}).values()
        ):
            issues.append(
                {
                    "code": "HIGHLIGHT_GATE_FAILED",
                    "severity": "error",
                    "message": "A selected Highlight failed a hard Gate.",
                    "details": item.get("evidence_id"),
                    "return_to": "paper-highlights",
                }
            )
        if float((item.get("scores") or {}).get("weighted_total") or 0) < 75:
            issues.append(
                {
                    "code": "HIGHLIGHT_SCORE_TOO_LOW",
                    "severity": "error",
                    "message": "A selected Highlight scores below 75.",
                    "return_to": "paper-highlights",
                }
            )
        if len(_words(str(item.get("primary_value") or ""))) > 4:
            issues.append(
                {
                    "code": "HIGHLIGHT_PRIMARY_VALUE_TOO_LONG",
                    "severity": "error",
                    "message": "Highlight primary_value exceeds four English words.",
                    "return_to": "paper-highlights",
                }
            )
        if len(_words(str(item.get("label") or ""))) > 6:
            issues.append(
                {
                    "code": "HIGHLIGHT_LABEL_TOO_LONG",
                    "severity": "error",
                    "message": "Highlight label exceeds six English words.",
                    "return_to": "paper-highlights",
                }
            )
        if len(_words(str(item.get("context") or ""))) > 10:
            issues.append(
                {
                    "code": "HIGHLIGHT_CONTEXT_TOO_LONG",
                    "severity": "error",
                    "message": "Highlight context exceeds ten English words.",
                    "return_to": "paper-highlights",
                }
            )
        claim = claims.get(str(item.get("claim_id") or ""))
        if (
            not claim
            or (
                claim.get("verdict") != "supported"
                and item.get("source_kind")
                not in {
                    "main_results",
                    "performance",
                    "efficiency",
                    "generalization",
                    "robustness",
                    "abstract",
                    "conclusion",
                }
            )
            or CONTRIBUTION_NUMBER_RE.match(str(claim.get("claim") or ""))
        ):
            issues.append(
                {
                    "code": "HIGHLIGHT_CLAIM_INVALID",
                    "severity": "error",
                    "message": "Highlight must bind a supported non-numbered Claim.",
                    "return_to": "paper-highlights",
                }
            )
        asset = assets.get(str(item.get("source_asset_id") or ""))
        row = item.get("row") or {}
        column = item.get("column") or {}
        source_cell = item.get("source_cell") or {}
        baseline_cell = item.get("baseline_cell") or {}
        table_rows = parse_html_table(str((asset or {}).get("html") or ""))
        row_index = row.get("index")
        column_index = column.get("index")
        baseline_row_index = baseline_cell.get("row_index")
        baseline_column_index = baseline_cell.get("column_index")
        if (
            not asset
            or asset.get("asset_type") != "table"
            or not isinstance(row_index, int)
            or not isinstance(column_index, int)
            or not isinstance(baseline_row_index, int)
            or not isinstance(baseline_column_index, int)
            or row_index >= len(table_rows)
            or baseline_row_index >= len(table_rows)
            or column_index >= len(table_rows[row_index])
            or baseline_column_index >= len(table_rows[baseline_row_index])
            or normalize_text(table_rows[row_index][column_index])
            != normalize_text(str(source_cell.get("value") or ""))
            or normalize_text(
                table_rows[baseline_row_index][baseline_column_index]
            )
            != normalize_text(str(baseline_cell.get("value") or ""))
        ):
            issues.append(
                {
                    "code": "HIGHLIGHT_CELL_TRACE_INVALID",
                    "severity": "error",
                    "message": "Highlight cannot be traced to exact source table cells.",
                    "return_to": "paper-highlights",
                }
            )
        recomputed = recompute_improvement(
            str(source_cell.get("extracted_value") or ""),
            str(baseline_cell.get("extracted_value") or ""),
            str(item.get("metric") or ""),
            str(item.get("metric_direction") or ""),
        )
        if (
            not recomputed.get("valid")
            or abs(
                float(recomputed.get("absolute_difference") or 0)
                - float(item.get("absolute_difference") or 0)
            )
            > 1e-6
            or abs(
                float(recomputed.get("relative_difference_percent") or 0)
                - float(item.get("relative_difference_percent") or 0)
            )
            > 1e-6
        ):
            issues.append(
                {
                    "code": "HIGHLIGHT_ARITHMETIC_MISMATCH",
                    "severity": "error",
                    "message": "Highlight improvement was not recomputed from source values.",
                    "return_to": "paper-highlights",
                }
            )
        key = (
            _normalized(item.get("metric")),
            _normalized(item.get("dataset")),
            _normalized(item.get("configuration")),
        )
        if key in semantic_keys:
            issues.append(
                {
                    "code": "HIGHLIGHT_SEMANTIC_DUPLICATE",
                    "severity": "error",
                    "message": "Highlights contain semantically duplicate results.",
                    "return_to": "paper-highlights",
                }
            )
        semantic_keys.add(key)
        if (
            GENERALIZATION_LANGUAGE_RE.search(str(item.get("claim_text") or ""))
            and int(item.get("dataset_count") or 1) < 2
        ):
            issues.append(
                {
                    "code": "HIGHLIGHT_SCOPE_OVERCLAIM",
                    "severity": "error",
                    "message": "A single favorable dataset cannot imply consistent gains.",
                    "return_to": "paper-highlights",
                }
            )
    return issues


def build_highlights(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    experimental_results_spec_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    experimental_results = read_json(experimental_results_spec_path)
    raw_candidates = _collect_candidates(
        paper_ir,
        story,
        evidence,
        experimental_results,
    )
    highlights, evaluated = select_highlights_from_candidates(raw_candidates)
    spec = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "highlights": highlights,
        "candidate_count": len(evaluated),
        "eligible_candidate_count": sum(
            bool(candidate.get("eligible")) for candidate in evaluated
        ),
        "selection_policy": {
            "minimum_score": 75,
            "maximum_items": 3,
            "hard_gates_required": True,
            "numeric_magnitude_prior_used": False,
            "author_emphasis_prior_used": False,
            "layout_fill_prior_used": False,
        },
        "rejected_candidates": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "classification": (candidate.get("scores") or {}).get(
                    "classification"
                ),
                "failed_gates": [
                    name
                    for name, gate in (candidate.get("gate_results") or {}).items()
                    if not gate.get("passed")
                ],
                "score": (candidate.get("scores") or {}).get("weighted_total"),
            }
            for candidate in evaluated
            if not candidate.get("eligible")
        ],
    }
    issues = validate_highlights_spec(spec, paper_ir, evidence)
    report = {
        "status": (
            "failed"
            if any(issue.get("severity") == "error" for issue in issues)
            else "passed_with_warnings"
            if issues
            else "passed"
        ),
        "candidate_count": len(evaluated),
        "eligible_candidate_count": spec["eligible_candidate_count"],
        "selected_count": len(highlights),
        "recovery_steps_executed": (
            []
            if highlights
            else [
                "rebind_primary_asset_claim_ids",
                "recover_exact_source_and_baseline_cells",
                "recover_metric_units_and_direction",
                "recover_dataset_configuration_and_evaluation_condition",
                "recompute_absolute_and_relative_differences",
                "recheck_claim_metric_and_dataset_alignment",
                "recheck_matched_comparison_conditions",
            ]
        ),
        "issues": issues,
        "return_to": next(
            (
                issue.get("return_to")
                for issue in issues
                if issue.get("severity") == "error"
            ),
            None,
        ),
    }
    return (
        write_json(output_dir / "highlights_spec.json", spec),
        write_json(output_dir / "highlights_report.json", report),
    )
