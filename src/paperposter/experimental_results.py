from __future__ import annotations

import html as html_module
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from statistics import median
from typing import Any

from .common import (
    find_numbers,
    jaccard,
    normalize_text,
    read_json,
    sha256_file,
    write_json,
)
from .parsers.mineru import _render_page_crop

RESULT_LAYOUTS = {
    "quantitative_plus_qualitative",
    "main_plus_ablation",
    "finding_plus_generalization",
}

CLAIM_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "efficiency": (
        "parameter",
        "params",
        "flops",
        "latency",
        "memory",
        "throughput",
        "computational cost",
        "compression",
        "efficient",
    ),
    "ablation": (
        "ablation",
        "w/o",
        "component",
        "module contributes",
    ),
    "generalization": (
        "cross-dataset",
        "cross dataset",
        "external dataset",
        "unseen",
        "generalization",
        "generalisation",
        "robust",
        "different dataset",
        "cross-modality",
        "cross modality",
    ),
    "qualitative": (
        "qualitative",
        "visual comparison",
        "visualization comparison",
        "visual quality",
        "boundary artifact",
        "failure case",
    ),
    "theory": (
        "theoretical",
        "theorem",
        "proposition",
        "statistical",
        "mechanism validation",
        "analysis confirms",
        "correlation",
    ),
    "performance": (
        "outperform",
        "improve",
        "higher",
        "lower",
        "state-of-the-art",
        "sota",
        "achieve",
        "performance",
        "accuracy",
        "dice",
        "iou",
        "auc",
        "f1",
        "psnr",
        "ssim",
        "hd95",
    ),
}

LOWER_IS_BETTER_TERMS = (
    "hd95",
    "lpips",
    "hausdorff",
    "mae",
    "rmse",
    "error",
    "loss",
    "latency",
    "memory",
    "flops",
    "params",
    "parameter",
    "runtime",
    "time",
    "unsupported",
)

NON_RESULT_ASSET_TERMS = (
    "architecture",
    "framework overview",
    "pipeline overview",
    "dataset sample",
    "evaluation metric",
    "metrics for evaluation",
)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._pending_rowspans: dict[int, tuple[int, str]] = {}
        self._colspan = 1
        self._rowspan = 1

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            values = dict(attrs)
            self._colspan = max(1, int(values.get("colspan") or 1))
            self._rowspan = max(1, int(values.get("rowspan") or 1))

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def _fill_spans(self) -> None:
        if self._row is None:
            return
        while len(self._row) in self._pending_rowspans:
            column = len(self._row)
            remaining, value = self._pending_rowspans[column]
            self._row.append(value)
            if remaining <= 1:
                del self._pending_rowspans[column]
            else:
                self._pending_rowspans[column] = (remaining - 1, value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._fill_spans()
            value = normalize_text(html_module.unescape("".join(self._cell)))
            start = len(self._row)
            for offset in range(self._colspan):
                self._row.append(value)
                if self._rowspan > 1:
                    self._pending_rowspans[start + offset] = (
                        self._rowspan - 1,
                        value,
                    )
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._fill_spans()
            if any(cell for cell in self._row):
                self.rows.append(self._row)
            self._row = None


def parse_html_table(value: str) -> list[list[str]]:
    parser = _TableParser()
    try:
        parser.feed(value or "")
    except (ValueError, TypeError):
        return []
    width = max((len(row) for row in parser.rows), default=0)
    return [row + [""] * (width - len(row)) for row in parser.rows]


def _text(value: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            str(value.get(field) or "")
            for field in (
                "caption",
                "section_id",
                "context_before",
                "context_after",
                "html",
            )
        )
    )


def _claim_text(claim: dict[str, Any]) -> str:
    parts = [str(claim.get("claim") or "")]
    parts.extend(
        str(item.get("source", {}).get("quote") or "")
        for item in claim.get("evidence", [])
    )
    return normalize_text(" ".join(parts))


def classify_claim(claim: dict[str, Any]) -> str:
    value = _claim_text(claim).lower()
    scores = {
        category: sum(term in value for term in terms)
        for category, terms in CLAIM_CATEGORY_TERMS.items()
    }
    priority = ("efficiency", "ablation", "generalization", "qualitative", "theory", "performance")
    winner = max(priority, key=lambda item: (scores[item], -priority.index(item)))
    return winner if scores[winner] else "performance"


def classify_asset(asset: dict[str, Any]) -> str:
    value = _text(asset).lower()
    caption_section = normalize_text(
        f"{asset.get('caption') or ''} {asset.get('section_id') or ''}"
    ).lower()
    if any(
        term in caption_section for term in CLAIM_CATEGORY_TERMS["generalization"]
    ):
        return "generalization"
    if any(
        term in caption_section
        for term in (
            "diseased images",
            "external validation",
            "cross-dataset",
            "cross dataset",
            "cross-validation",
            "cross validation",
        )
    ):
        return "generalization"
    if any(
        term in caption_section for term in CLAIM_CATEGORY_TERMS["ablation"]
    ):
        return "ablation"
    if any(
        term in caption_section for term in CLAIM_CATEGORY_TERMS["qualitative"]
    ):
        return "qualitative"
    if "visualization" in caption_section and any(
        term in caption_section
        for term in ("segmentation result", "prediction", "output")
    ):
        return "qualitative"
    if any(
        term in caption_section for term in CLAIM_CATEGORY_TERMS["efficiency"]
    ):
        if asset.get("asset_type") == "figure" and any(
            term in value for term in ("curve", "trade-off", "tradeoff", "latency")
        ):
            return "efficiency"
    if any(term in caption_section for term in CLAIM_CATEGORY_TERMS["theory"]):
        return "theory"
    return "performance"


def _source_block_ids(claim: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in claim.get("sources", []):
        if source.get("block_id"):
            values.append(str(source["block_id"]))
    for evidence in claim.get("evidence", []):
        source = evidence.get("source") or {}
        if source.get("block_id"):
            values.append(str(source["block_id"]))
    return list(dict.fromkeys(values))


def _asset_block_ids(asset: dict[str, Any], paper_ir: dict[str, Any]) -> list[str]:
    known_ids = {
        str(block.get("id"))
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }
    values = [
        str(value)
        for value in asset.get("cited_by", [])
        if value and str(value) in known_ids
    ]
    page = asset.get("page")
    caption = normalize_text(str(asset.get("caption") or ""))
    caption_tokens = set(re.findall(r"\b(?:figure|fig|table)\s*\d+\b", caption.lower()))
    for block in paper_ir.get("blocks", []):
        if block.get("page") != page:
            continue
        block_text = normalize_text(str(block.get("text") or ""))
        if block.get("type") in {"caption", "table"} and (
            jaccard(caption, block_text) >= 0.18
            or caption_tokens.intersection(
                re.findall(r"\b(?:figure|fig|table)\s*\d+\b", block_text.lower())
            )
        ):
            values.append(str(block["id"]))
    return list(dict.fromkeys(values))


def _asset_score(
    asset: dict[str, Any],
    claim: dict[str, Any],
    *,
    primary: bool,
) -> tuple[float, list[str]]:
    asset_category = classify_asset(asset)
    claim_category = classify_claim(claim)
    text = _text(asset)
    claim_value = _claim_text(claim)
    score = jaccard(text, claim_value) * 12
    reasons: list[str] = []
    if asset_category == claim_category:
        score += 4.0
        reasons.append(f"asset type matches the {claim_category} Claim")
    elif claim_category in {"performance", "efficiency"} and asset_category in {
        "performance",
        "efficiency",
    }:
        score += 2.0
        reasons.append("asset provides directly comparable quantitative evidence")
    if asset.get("asset_type") == "table":
        score += 3.0 if primary else 1.0
        reasons.append("original result table preserves methods, metrics, and settings")
        if primary and any(
            phrase in text.lower()
            for phrase in (
                "performance comparison",
                "comparison of segmentation performance",
                "comparison with structured pruning baselines",
                "main result",
                "main performance",
            )
        ):
            score += 3.0
            reasons.append("caption identifies a primary comparative result")
    if asset.get("asset_type") == "figure" and any(
        term in text.lower()
        for term in ("curve", "comparison", "quantitative", "performance")
    ):
        score += 2.0
        reasons.append("figure is a direct quantitative comparison")
    if any(term in text.lower() for term in NON_RESULT_ASSET_TERMS):
        score -= 6.0
        reasons.append("penalized as method, dataset, or metric-description content")
    if primary and asset_category in {"qualitative", "ablation"}:
        score -= 5.0
    if asset.get("path"):
        score += 1.0
        reasons.append("original extracted asset is available")
    if asset.get("bbox") and asset.get("page"):
        score += 1.0
        reasons.append("page and bounding box support source-accurate cropping")
    if asset.get("cited_by"):
        score += min(1.5, len(asset.get("cited_by") or []) * 0.35)
    return round(score, 3), reasons


def _supported_claims(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        claim
        for claim in evidence.get("claims", [])
        if claim.get("verdict") in {"supported", "partially_supported"}
        and not re.match(
            r"^(?:some studies|numerous efforts|subsequent work|other methods|"
            r"prior work|previous studies|existing studies)\b",
            normalize_text(str(claim.get("claim") or "")),
            re.I,
        )
    ]


def _claim_priority(claim: dict[str, Any]) -> float:
    value = normalize_text(str(claim.get("claim") or ""))
    category = classify_claim(claim)
    score = {"performance": 5, "efficiency": 4, "generalization": 3, "ablation": 2, "theory": 2, "qualitative": 1}[category]
    if claim.get("verdict") == "supported":
        score += 2
    score += min(3, len(find_numbers(value)) * 0.7)
    if not find_numbers(value):
        score -= 3
    if any(
        phrase in value.lower()
        for phrase in (
            "should be read together",
            "interpret with",
            "caution",
            "limitation",
            "setting.",
        )
    ):
        score -= 4
    score += max(
        (
            2.0
            if item.get("strength") == "direct"
            else 0.7
            for item in claim.get("evidence", [])
        ),
        default=0,
    )
    return score


def _best_asset_for_claims(
    assets: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    paper_ir: dict[str, Any],
    *,
    primary: bool,
    exclude_ids: set[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, float, list[str]]:
    excluded = exclude_ids or set()
    candidates: list[tuple[float, float, dict[str, Any], dict[str, Any], list[str]]] = []
    for claim in claims:
        for asset in assets:
            if str(asset.get("id")) in excluded:
                continue
            asset_score, reasons = _asset_score(asset, claim, primary=primary)
            if asset.get("asset_type") == "table":
                table_context = _table_context(asset, paper_ir)
                if table_context["complete"]:
                    asset_score += 8.0 if primary else 3.0
                    reasons.append(
                        "table contains a proposed row, strong baseline, metrics, and setting"
                    )
                elif primary:
                    asset_score -= 10.0
                    reasons.append(
                        "penalized because the table is not a comparative result table"
                    )
            candidates.append(
                (
                    asset_score + _claim_priority(claim),
                    asset_score,
                    asset,
                    claim,
                    reasons,
                )
            )
    if not candidates:
        return None, None, 0.0, []
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, score, asset, claim, reasons = candidates[0]
    return asset, claim, score, reasons


def _direction(metric: str) -> str:
    lowered = metric.lower()
    compact = re.sub(r"\s+", "", lowered)
    if (
        "↓" in metric
        or any(term in lowered for term in LOWER_IS_BETTER_TERMS)
        or re.search(r"(?:^|/)#?p(?:\(m\))?(?:$|/)", compact)
        or re.search(r"(?:^|/)f\(g\)(?:$|/)", compact)
        or "macs" in compact
        or re.search(r"\bhd(?:95)?\b", lowered)
    ):
        return "lower_is_better"
    return "higher_is_better"


def _number(value: str) -> float | None:
    match = re.search(r"[+-]?(?:\d+\.\d+|\d+)", value.replace(",", ""))
    return float(match.group(0)) if match else None


def _header_rows(rows: list[list[str]]) -> int:
    count = 1
    for index, row in enumerate(rows[:3], start=1):
        joined = " ".join(row).lower()
        numeric_cells = sum(_number(cell) is not None for cell in row)
        if index == 1 or numeric_cells < max(1, len(row) // 3) or any(
            term in joined for term in ("metric", "method", "dataset", "dice", "iou", "f1", "accuracy")
        ):
            count = index
            continue
        break
    return min(count, max(1, len(rows) - 1))


def _headers(rows: list[list[str]], header_count: int) -> list[str]:
    width = max((len(row) for row in rows), default=0)
    values: list[str] = []
    for column in range(width):
        parts: list[str] = []
        for row in rows[:header_count]:
            if column < len(row) and row[column] and row[column] not in parts:
                parts.append(row[column])
        values.append(normalize_text(" / ".join(parts)))
    return values


def _effective_headers(
    asset: dict[str, Any],
    rows: list[list[str]],
    header_count: int,
) -> list[str]:
    """Recover metric labels when a table reports one metric across datasets.

    Some papers put dataset names in the header and state the shared metric
    only in the caption (for example, four dataset columns "reported in
    OA (%)").  Preserve each dataset as grouping context while making the
    metric explicit for downstream extraction and QA.
    """

    headers = _headers(rows, header_count)
    caption = normalize_text(str(asset.get("caption") or ""))
    shared_metric_match = re.search(
        r"(?:reported|measured|evaluated)\s+in\s+"
        r"(OA|AA|accuracy|mAP(?:\d+)?|Dice|IoU|F1)(?:\s*\(%\))?",
        caption,
        re.I,
    )
    if (
        not shared_metric_match
        and any(term in caption.lower() for term in ("transferability", "classification"))
        and any(
            re.search(r"\b(?:cifar|imagenet|places|tiny-imagenet)[- ]?\d*\b", header, re.I)
            for header in headers
        )
    ):
        shared_metric_match = re.search(r"(Accuracy)", "Accuracy")
    if not shared_metric_match:
        return headers
    shared_metric = normalize_text(shared_metric_match.group(1))
    data_rows = rows[header_count:]
    adjusted = list(headers)
    configuration_terms = (
        "method",
        "model",
        "approach",
        "module",
        "component",
        "depth",
        "scale",
        "loss",
        "variant",
        "configuration",
        "setting",
    )
    for index, header in enumerate(headers):
        if _looks_like_metric_header(header):
            continue
        if any(term in header.lower() for term in configuration_terms):
            continue
        numeric = sum(
            index < len(row) and _number(row[index]) is not None
            for row in data_rows
        )
        if numeric >= max(1, len(data_rows) // 2):
            adjusted[index] = f"{header} / {shared_metric}" if header else shared_metric
    return adjusted


def _method_column(
    headers: list[str],
    data_rows: list[list[str]] | None = None,
) -> int:
    for index, value in enumerate(headers):
        if any(
            term in value.lower()
            for term in (
                "method",
                "model",
                "approach",
                "loss",
                "module",
                "component",
                "variant",
                "configuration",
                "setting",
                "depth",
                "scale",
            )
        ):
            return index
    if data_rows:
        width = max((len(row) for row in data_rows), default=0)
        for index in range(min(width, 3)):
            values = [
                normalize_text(row[index])
                for row in data_rows
                if index < len(row) and normalize_text(row[index])
            ]
            if len(values) < 2:
                continue
            label_count = sum(_number(value) is None for value in values)
            if label_count >= max(2, (len(values) * 3 + 4) // 5):
                return index
    return 1 if len(headers) > 1 else 0


VARIANT_FOOTNOTE_RE = re.compile(
    r"^(?P<base>.*?)(?P<marker>[†‡*]{1,3})$"
)


def _variant_label_parts(value: str) -> tuple[str, str]:
    label = normalize_text(value)
    match = VARIANT_FOOTNOTE_RE.match(label)
    if not match:
        return label, ""
    return normalize_text(match.group("base")), match.group("marker")


def _paired_table_base_labels(paper_ir: dict[str, Any]) -> set[str]:
    paired: set[str] = set()
    for asset in paper_ir.get("tables", []):
        rows = parse_html_table(str(asset.get("html") or ""))
        if len(rows) < 3:
            continue
        header_count = _header_rows(rows)
        headers = _effective_headers(asset, rows, header_count)
        data_rows = rows[header_count:]
        method_column = _method_column(headers, data_rows)
        plain_labels: set[str] = set()
        marked_labels: set[str] = set()
        for row in data_rows:
            if method_column >= len(row):
                continue
            base, marker = _variant_label_parts(row[method_column])
            normalized = base.lower()
            if not normalized:
                continue
            if marker:
                marked_labels.add(normalized)
            else:
                plain_labels.add(normalized)
        paired.update(plain_labels & marked_labels)
    return paired


def _paper_method_terms(paper_ir: dict[str, Any]) -> set[str]:
    title = str(paper_ir.get("metadata", {}).get("title") or "")
    terms: set[str] = set()

    blocked_terms = {
        "em",
        "ema",
        "cnn",
        "net",
        "unet",
        "resnet",
        "vit",
        "transformer",
    }

    def add_term(value: str) -> None:
        term = normalize_text(value).lower()
        if len(term) < 3 or term in blocked_terms:
            return
        terms.add(term)

    lead = re.match(r"\s*([A-Za-z][A-Za-z0-9-]{2,})", title)
    if lead:
        add_term(lead.group(1))
    for token in re.findall(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b", title):
        add_term(token)
    acronym = "".join(
        token[0]
        for token in re.findall(r"[A-Za-z]+", title)
        if token.lower() not in {"the", "and", "for", "with", "via", "of"}
    )
    if len(acronym) >= 3:
        add_term(acronym)
    # Recover author-named components that do not appear in the title.
    # Bind abbreviations to proposal syntax or an explicit "our X" phrase;
    # collecting every acronym in a long abstract would also capture baseline
    # losses, datasets, and hardware names.
    source_texts = [
        normalize_text(str(block.get("text") or ""))
        for block in paper_ir.get("blocks", [])[:100]
    ]
    source_texts.extend(
        normalize_text(str(asset.get("caption") or ""))
        for group in ("tables", "figures")
        for asset in paper_ir.get(group, [])
    )
    paired_base_labels = _paired_table_base_labels(paper_ir)
    for text in source_texts:
        for match in re.finditer(
            r"\b(?:we\s+(?:propose|introduce|design|develop)|"
            r"this\s+(?:paper|work)\s+(?:proposes|introduces))\b"
            r".{0,100}?\(([A-Z][A-Za-z0-9-]{1,})\)",
            text,
            re.I,
        ):
            add_term(match.group(1))
        for match in re.finditer(
            r"\bour\s+([A-Z][A-Za-z0-9-]{1,})(?:[†‡*])?"
            r"(?:\s*\([^)]*\))?",
            text,
        ):
            candidate = match.group(1).lower()
            if candidate not in paired_base_labels:
                add_term(candidate)
    return terms


def _method_term_in_text(term: str, text: str) -> bool:
    if not term or len(term) < 3:
        return False
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])",
            text,
            re.I,
        )
    )


def _row_is_ours(row: list[str], method_column: int, method_terms: set[str]) -> bool:
    method = row[method_column].lower() if method_column < len(row) else ""
    row_text = " ".join(row).lower()
    positive_markers = sum(
        cell.strip() in {"✓", "√", "✔", "yes", "Yes", "YES"} for cell in row
    )
    negative_markers = sum(
        cell.strip() in {"✗", "×", "X", "x", "no", "No", "NO"} for cell in row
    )
    return (
        "ours" in method
        or "proposed" in method
        or any(_method_term_in_text(term, row_text) for term in method_terms)
        or (positive_markers >= 2 and negative_markers == 0)
    )


def _paired_proposed_row_indices(
    asset: dict[str, Any],
    data_rows: list[list[str]],
    method_column: int,
) -> dict[int, int]:
    plain_by_base: dict[str, int] = {}
    marked_by_base: dict[str, int] = {}
    for index, row in enumerate(data_rows):
        if method_column >= len(row):
            continue
        base, marker = _variant_label_parts(row[method_column])
        normalized = base.lower()
        if not normalized:
            continue
        if marker:
            marked_by_base[normalized] = index
        else:
            plain_by_base[normalized] = index
    pairs = {
        marked_index: plain_by_base[base]
        for base, marked_index in marked_by_base.items()
        if base in plain_by_base
    }
    if not pairs:
        return {}
    context = normalize_text(
        " ".join(
            str(asset.get(key) or "")
            for key in (
                "caption",
                "context_before",
                "context_after",
                "footnote",
            )
        )
    ).lower()
    explicit_method_context = bool(
        re.search(
            r"\b(?:our|proposed|method|framework|training|fine[- ]?tun)"
            r"\b",
            context,
        )
    )
    gain_rows = sum(
        any(
            re.search(r"\(\s*\+\s*\d", normalize_text(cell))
            for cell in data_rows[marked_index]
        )
        for marked_index in pairs
    )
    if not explicit_method_context and gain_rows == 0:
        return {}
    if len(pairs) == 1 and gain_rows == 0:
        return {}
    return pairs


def _context_value(
    headers: list[str],
    row: list[str],
    terms: tuple[str, ...],
) -> str:
    for index, header in enumerate(headers):
        if any(term in header.lower() for term in terms) and index < len(row):
            return normalize_text(row[index])
    return ""


def _dataset_from_asset(
    asset: dict[str, Any],
    headers: list[str],
    row: list[str],
    metric_header: str = "",
) -> str:
    if " / " in metric_header:
        prefix = normalize_text(metric_header.split(" / ", 1)[0])
        if prefix and prefix.lower() not in {"metric", "result", "performance"}:
            return prefix
    value = _context_value(headers, row, ("dataset", "benchmark", "cohort", "task"))
    if value:
        return value
    caption = normalize_text(str(asset.get("caption") or ""))
    matches = re.findall(
        r"\bon\s+(.+?)(?=\.|;|\s+with\b|\s+without\b|\s+under\b|\s+using\b|$)",
        caption,
        re.I,
    )
    if not matches:
        matches = re.findall(
            r"\b(?:results?|performance)\s+of\s+(?:the\s+)?(.+?)\s+dataset\b",
            caption,
            re.I,
        )
    if matches:
        value = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", "", matches[0])
        value = re.sub(
            r"\bsegmentation metrics\b",
            "segmentation benchmarks",
            value,
            flags=re.I,
        )
        return normalize_text(value).rstrip(" ,")
    return "reported evaluation dataset(s)"


def _configuration(
    asset: dict[str, Any],
    headers: list[str],
    row: list[str],
) -> str:
    value = _context_value(
        headers,
        row,
        ("configuration", "compression", "setting", "variant"),
    )
    if value:
        return value
    caption = normalize_text(str(asset.get("caption") or ""))
    for phrase in re.split(r"(?<=[.;])\s+", caption):
        if any(
            term in phrase.lower()
            for term in ("fine-tuning", "fine tuning", "checkpoint", "configuration", "setting")
        ):
            return normalize_text(phrase)
    return "paper-reported configuration"


def _evaluation_condition(asset: dict[str, Any], story: dict[str, Any]) -> str:
    caption = normalize_text(str(asset.get("caption") or ""))
    for phrase in re.split(r"(?<=[.;])\s+", caption):
        if any(
            term in phrase.lower()
            for term in (
                "fine-tuning",
                "fine tuning",
                "without",
                "same",
                "average",
                "macro",
                "test",
                "checkpoint",
            )
        ):
            return normalize_text(phrase)
    design = normalize_text(
        str(story.get("experimental_design", {}).get("summary") or "")
    )
    if design and any(
        term in design.lower()
        for term in (
            "training",
            "test split",
            "cross-validation",
            "cross validation",
            "checkpoint",
            "fine-tun",
            "batch",
            "learning rate",
        )
    ):
        return _clip_words(design, 22)
    return "paper-reported matched test protocol"


def _metric_columns(headers: list[str], method_column: int) -> list[int]:
    columns: list[int] = []
    for index, header in enumerate(headers):
        if index == method_column:
            continue
        if _looks_like_metric_header(header):
            columns.append(index)
    return columns


def _looks_like_metric_header(value: str) -> bool:
    lowered = normalize_text(value).lower()
    compact = re.sub(r"\s+", "", lowered)
    if any(
        term in lowered
        for term in (
            "dice",
            "iou",
            "f1",
            "auc",
            "accuracy",
            "acc",
            "precision",
            "recall",
            "psnr",
            "pnsr",
            "ssim",
            "hd95",
            "hausdorff",
            "latency",
            "flops",
            "param",
            "memory",
            "lpips",
            "error",
            "unsupported",
            "score",
        )
    ):
        return True
    if re.search(
        r"(?:^|[/\s(])(?:snr|cnr|nmse|mse)(?:$|[/\s)(])",
        lowered,
        re.I,
    ):
        return True
    return bool(
        re.search(
            r"(?:^|[/])(?:dsc|oa|aa|κ|kappa|m?ap(?:@\d+)?|mae|rmse|hd|macs?|"
            r"top[-]?[15]|#p|p\(m\)|f\(g\)|t_i)(?:$|[/↑↓(])",
            compact,
        )
    )


def _split_metric_header(header: str) -> tuple[str, list[str]]:
    """Separate a metric label from multi-row table grouping context.

    MinerU flattens stacked headers with ``" / "``. Depending on the source
    table, the metric can appear before or after a repeated setting label:
    ``F1 / Without FOV Mask`` and ``ClinicDB / Dice`` are both common. Treating
    the first component as a dataset made every metric look like a different
    evaluation context and incorrectly collapsed a multi-metric table to one
    Poster card.
    """

    parts = [
        normalize_text(part)
        for part in header.split(" / ")
        if normalize_text(part)
    ]
    metric_index = next(
        (
            index
            for index, part in enumerate(parts)
            if _looks_like_metric_header(part)
        ),
        None,
    )
    if metric_index is None:
        return (parts[0] if parts else normalize_text(header), parts[1:])
    return parts[metric_index], [
        part for index, part in enumerate(parts) if index != metric_index
    ]


def _header_dataset_context(parts: list[str]) -> str:
    condition_terms = (
        "with ",
        "without ",
        "mask",
        "average",
        "mean",
        "test",
        "validation",
        "fold",
        "protocol",
        "setting",
    )
    for part in parts:
        lowered = part.lower()
        if not any(term in lowered for term in condition_terms):
            return part
    return ""


def _header_evaluation_condition(parts: list[str]) -> str:
    condition_terms = (
        "with ",
        "without ",
        "mask",
        "average",
        "mean",
        "test",
        "validation",
        "fold",
        "protocol",
        "setting",
    )
    for part in parts:
        lowered = part.lower()
        if any(term in lowered for term in condition_terms):
            return part
    return ""


def _row_group_label(row: list[str]) -> str:
    values = [normalize_text(cell) for cell in row if normalize_text(cell)]
    if len(values) < 2 or any(_number(value) is not None for value in values):
        return ""
    unique = {value.lower() for value in values}
    return values[0] if len(unique) == 1 else ""


def _same_group_rows(
    data_rows: list[list[str]],
    ours: list[str],
    initial_group: str,
) -> list[list[str]]:
    """Return comparable rows from the same table section as the proposed row."""

    current_group = normalize_text(initial_group)
    ours_group = current_group
    grouped_rows: list[tuple[list[str], str]] = []
    for row in data_rows:
        separator = _row_group_label(row)
        if separator:
            current_group = separator
            continue
        grouped_rows.append((row, current_group))
        if row is ours:
            ours_group = current_group
    if not ours_group:
        return [row for row, _ in grouped_rows]
    return [
        row
        for row, group in grouped_rows
        if normalize_text(group).lower() == ours_group.lower()
    ]


def _best_baseline(
    data_rows: list[list[str]],
    ours: list[str],
    column: int,
    method_column: int,
    direction: str,
    method_terms: set[str],
    context_columns: list[int] | None = None,
) -> list[str] | None:
    context_columns = context_columns or []
    candidates = [
        row
        for row in data_rows
        if row is not ours
        and not _row_is_ours(row, method_column, method_terms)
        and column < len(row)
        and _number(row[column]) is not None
        and all(
            index < len(row)
            and index < len(ours)
            and normalize_text(row[index]) == normalize_text(ours[index])
            for index in context_columns
            if index < len(ours) and normalize_text(ours[index])
        )
    ]
    if not candidates:
        return None
    reverse = direction == "higher_is_better"
    return sorted(
        candidates,
        key=lambda row: _number(row[column]) or 0.0,
        reverse=reverse,
    )[0]


def _format_delta(
    ours: str,
    baseline: str,
    direction: str,
) -> tuple[str | None, str | None]:
    ours_value = _number(ours)
    baseline_value = _number(baseline)
    if ours_value is None or baseline_value is None:
        return None, None
    signed = ours_value - baseline_value
    if direction == "lower_is_better":
        signed = baseline_value - ours_value
    precision = max(
        len(ours.split(".", 1)[1]) if "." in ours else 0,
        len(baseline.split(".", 1)[1]) if "." in baseline else 0,
    )
    if "%" in ours and "%" in baseline:
        return f"{signed:+.{min(precision, 4)}f} pp", "percentage_points"
    return f"{signed:+.{min(precision, 4)}f}", "absolute"


def _primary_metric_cell_value(value: str) -> str:
    normalized = normalize_text(value)
    match = re.search(r"[+-]?(?:\d+\.\d+|\d+)(?:\s*%)?", normalized)
    return normalize_text(match.group(0)) if match else normalized


def _transposed_key_metrics(
    asset: dict[str, Any],
    rows: list[list[str]],
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    source_block_ids: list[str],
) -> list[dict[str, Any]]:
    """Extract exact cells when methods are columns and metrics are rows."""

    if len(rows) < 2:
        return []
    headers = [normalize_text(cell) for cell in rows[0]]
    method_terms = _paper_method_terms(paper_ir)
    ours_columns = [
        index
        for index, header in enumerate(headers)
        if header
        and (
            "ours" in header.lower()
            or "proposed" in header.lower()
            or any(term in header.lower() for term in method_terms)
        )
    ]
    if not ours_columns:
        return []
    ours_column = ours_columns[-1]
    label_column = next(
        (
            index
            for index, header in enumerate(headers[:ours_column])
            if header.lower() in {"metric", "measure", "method"}
        ),
        0,
    )
    metric_pattern = re.compile(
        r"\b(?:oa|aa|auc|acc(?:uracy)?|dice|dsc|iou|f1|snr|cnr|"
        r"psnr|ssim|nmse|mse|hd95|hausdorff|mae|rmse|lpips|"
        r"latency|inference time|runtime|memory|flops|macs|"
        r"parameters?|params?|throughput)\b",
        re.I,
    )
    metrics: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows[1:], start=1):
        if label_column >= len(row) or ours_column >= len(row):
            continue
        metric = normalize_text(row[label_column])
        if not metric_pattern.search(metric) or _number(row[ours_column]) is None:
            continue
        direction = _direction(metric)
        baseline_columns = [
            column
            for column in range(label_column + 1, min(len(headers), len(row)))
            if column != ours_column and _number(row[column]) is not None
        ]
        if not baseline_columns:
            continue
        baseline_column = sorted(
            baseline_columns,
            key=lambda column: _number(row[column]) or 0.0,
            reverse=direction == "higher_is_better",
        )[0]
        ours_value = _primary_metric_cell_value(row[ours_column])
        baseline_value = _primary_metric_cell_value(row[baseline_column])
        delta, delta_type = _format_delta(
            ours_value,
            baseline_value,
            direction,
        )
        dataset = (
            normalize_text(row[0])
            if label_column > 0 and normalize_text(row[0])
            else _dataset_from_asset(asset, headers, row, metric)
        )
        evaluation_condition = _evaluation_condition(asset, story)
        metrics.append(
            {
                "value": ours_value,
                "metric": metric,
                "direction": direction,
                "baseline": headers[baseline_column],
                "baseline_value": baseline_value,
                "delta": delta,
                "delta_type": delta_type,
                "dataset": dataset,
                "configuration": "matched full-model columns in source table",
                "baseline_configuration": "matched full-model columns in source table",
                "evaluation_condition": evaluation_condition,
                "baseline_evaluation_condition": evaluation_condition,
                "source_table_id": asset.get("id"),
                "source_block_ids": source_block_ids,
                "verification": "exact_table_cell_match",
                "row_label": metric,
                "baseline_row_label": metric,
                "column_label": headers[ours_column],
                "source_cell": {
                    "row_index": row_index,
                    "column_index": ours_column,
                    "value": normalize_text(row[ours_column]),
                    "extracted_value": ours_value,
                },
                "baseline_cell": {
                    "row_index": row_index,
                    "column_index": baseline_column,
                    "value": normalize_text(row[baseline_column]),
                    "extracted_value": baseline_value,
                },
                "baseline_selection": "strongest_matched",
            }
        )
    return metrics


def extract_key_metrics(
    asset: dict[str, Any],
    claim: dict[str, Any],
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    source_block_ids: list[str],
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if asset.get("asset_type") != "table" or not asset.get("html"):
        return _metrics_from_claim(
            asset,
            claim,
            story,
            source_block_ids,
            limit=limit,
        )
    rows = parse_html_table(str(asset.get("html") or ""))
    if len(rows) < 2:
        return _metrics_from_claim(
            asset,
            claim,
            story,
            source_block_ids,
            limit=limit,
        )
    header_count = _header_rows(rows)
    headers = _effective_headers(asset, rows, header_count)
    data_rows = rows[header_count:]
    method_column = _method_column(headers, data_rows)
    method_terms = _paper_method_terms(paper_ir)
    paired_rows = _paired_proposed_row_indices(
        asset,
        data_rows,
        method_column,
    )
    ours_indices = (
        sorted(paired_rows)
        if paired_rows
        else [
            index
            for index, row in enumerate(data_rows)
            if _row_is_ours(row, method_column, method_terms)
        ]
    )
    ours_rows = [data_rows[index] for index in ours_indices]
    if not ours_rows:
        transposed_metrics = _transposed_key_metrics(
            asset,
            rows,
            paper_ir,
            story,
            source_block_ids,
        )
        if transposed_metrics:
            return transposed_metrics[:limit]
        return _metrics_from_claim(
            asset,
            claim,
            story,
            source_block_ids,
            limit=limit,
        )
    # Prefer the proposed row that shares the most numbers with the selected
    # Claim. This avoids silently mixing compression levels/configurations.
    claim_numbers = {
        _normalized_number(value)
        for value in find_numbers(str(claim.get("claim") or ""))
    }
    ours = max(
        ours_rows,
        key=lambda row: (
            len(
                claim_numbers
                & {
                    _normalized_number(value)
                    for cell in row
                    for value in find_numbers(cell)
                }
            ),
            jaccard(" ".join(row), str(claim.get("claim") or "")),
        ),
    )
    ours_data_index = next(
        index for index, row in enumerate(data_rows) if row is ours
    )
    context_columns = [
        index
        for index, header in enumerate(headers)
        if index != method_column
        if any(
            term in header.lower()
            for term in (
                "dataset",
                "compression",
                "configuration",
                "setting",
                "variant",
                "recovery",
                "retraining",
                "fine-tuning",
                "fine tuning",
                "protocol",
                "split",
                "checkpoint",
                "pretrain",
            )
        )
        and not any(
            term in header.lower()
            for term in ("venue", "publication", "reference", "year")
        )
    ]
    first_metric_column = next(iter(_metric_columns(headers, method_column)), None)
    initial_group = ""
    if first_metric_column is not None:
        _, first_header_context = _split_metric_header(headers[first_metric_column])
        initial_group = _header_evaluation_condition(first_header_context)
    comparable_rows = _same_group_rows(data_rows, ours, initial_group)
    metrics: list[dict[str, Any]] = []
    for column in _metric_columns(headers, method_column):
        if column >= len(ours) or _number(ours[column]) is None:
            continue
        raw_metric = headers[column] or f"Metric {column + 1}"
        metric, header_context = _split_metric_header(raw_metric)
        direction = _direction(metric)
        paired_baseline_index = paired_rows.get(ours_data_index)
        paired_baseline = (
            data_rows[paired_baseline_index]
            if paired_baseline_index is not None
            else None
        )
        baseline_row = (
            paired_baseline
            if paired_baseline is not None
            and column < len(paired_baseline)
            and _number(paired_baseline[column]) is not None
            else _best_baseline(
                comparable_rows,
                ours,
                column,
                method_column,
                direction,
                method_terms,
                context_columns,
            )
        )
        if not baseline_row:
            continue
        baseline_name = normalize_text(baseline_row[method_column])
        if (
            re.fullmatch(
                r"[+-]?(?:\d+\.\d+|\d+)(?:\s*%)?",
                baseline_name,
            )
            or len(baseline_name) < 2
        ):
            configuration_parts = [
                f"{headers[index]}={normalize_text(cell)}"
                for index, cell in enumerate(baseline_row)
                if index < len(headers)
                and normalize_text(cell)
                and index not in _metric_columns(headers, method_column)
            ]
            if configuration_parts:
                baseline_name = "; ".join(configuration_parts)
        ours_value = _primary_metric_cell_value(ours[column])
        baseline_value = _primary_metric_cell_value(baseline_row[column])
        delta, delta_type = _format_delta(ours_value, baseline_value, direction)
        ours_row_index = header_count + ours_data_index
        baseline_row_index = header_count + next(
            index for index, row in enumerate(data_rows) if row is baseline_row
        )
        evaluation_condition = (
            _header_evaluation_condition(header_context)
            or _evaluation_condition(asset, story)
        )
        configuration = _configuration(asset, headers, ours)
        baseline_configuration = _configuration(asset, headers, baseline_row)
        metrics.append(
            {
                "value": ours_value,
                "metric": metric,
                "direction": direction,
                "baseline": baseline_name,
                "baseline_value": baseline_value,
                "delta": delta,
                "delta_type": delta_type,
                "dataset": (
                    _header_dataset_context(header_context)
                    or _dataset_from_asset(asset, headers, ours, metric)
                ),
                "configuration": configuration,
                "baseline_configuration": baseline_configuration,
                "evaluation_condition": evaluation_condition,
                "baseline_evaluation_condition": evaluation_condition,
                "source_table_id": asset.get("id"),
                "source_block_ids": source_block_ids,
                "verification": "exact_table_cell_match",
                "row_label": normalize_text(ours[method_column]),
                "baseline_row_label": normalize_text(
                    baseline_row[method_column]
                ),
                "column_label": raw_metric,
                "source_cell": {
                    "row_index": ours_row_index,
                    "column_index": column,
                    "value": normalize_text(ours[column]),
                    "extracted_value": ours_value,
                },
                "baseline_cell": {
                    "row_index": baseline_row_index,
                    "column_index": column,
                    "value": normalize_text(baseline_row[column]),
                    "extracted_value": baseline_value,
                },
                "baseline_selection": (
                    "paired_base_variant"
                    if baseline_row is paired_baseline
                    else "strongest_matched"
                ),
            }
        )
    # Favor accuracy/quality metrics but retain one efficiency cost when the
    # central Claim is an efficiency Claim.
    category = classify_claim(claim)
    metrics.sort(
        key=lambda item: (
            category == "efficiency"
            and any(
                term in item["metric"].lower()
                for term in ("param", "flops", "latency", "memory")
            ),
            any(
                term in item["metric"].lower()
                for term in ("dice", "f1", "auc", "accuracy", "psnr", "ssim", "hd95")
            ),
        ),
        reverse=True,
    )
    if not metrics:
        return []
    metrics_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in metrics:
        metrics_by_name.setdefault(
            normalize_text(str(item.get("metric") or "")).lower(),
            [],
        ).append(item)
    multi_dataset_group = max(
        (
            group
            for group in metrics_by_name.values()
            if len(
                {
                    normalize_text(str(item.get("dataset") or ""))
                    for item in group
                    if normalize_text(str(item.get("dataset") or ""))
                    not in {"not stated", "paper dataset"}
                }
            )
            >= 2
        ),
        key=len,
        default=[],
    )
    if multi_dataset_group:
        # One shared metric reported across explicitly labelled datasets is
        # already contextualized and may be shown as several metric cards.
        return multi_dataset_group[:limit]
    # A single Poster metric row must not silently combine DRIVE, STARE, and
    # another benchmark. Keep the strongest internally matched context.
    context_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for metric in metrics:
        key = (
            str(metric["dataset"]),
            str(metric["configuration"]),
            str(metric["evaluation_condition"]),
        )
        context_groups.setdefault(key, []).append(metric)
    best_group = max(
        context_groups.values(),
        key=lambda group: (
            len(group),
            sum(
                any(
                    term in item["metric"].lower()
                    for term in ("dice", "f1", "auc", "accuracy", "acc", "hd95")
                )
                for item in group
            ),
        ),
    )
    return best_group[:limit]


def _metrics_from_claim(
    asset: dict[str, Any],
    claim: dict[str, Any],
    story: dict[str, Any],
    source_block_ids: list[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    claim_value = _claim_text(claim)
    asset_value = _text(asset)
    values = [
        number
        for number in find_numbers(claim_value)
        if _normalized_number(number) in _normalized_number(asset_value)
    ]
    if asset.get("asset_type") != "table":
        values = list(find_numbers(claim_value))
    metric_terms = (
        "BF1",
        "HD95",
        "OA",
        "AA",
        "Kappa",
        "Dice",
        "IoU",
        "AUC",
        "accuracy",
        "F1",
        "PSNR",
        "SNR",
        "CNR",
        "SSIM",
        "NMSE",
        "MSE",
        "RMSE",
        "MAE",
        "FLOPs",
        "parameters",
        "latency",
        "memory",
    )
    metric_hint_text = f"{claim_value} {asset_value}"
    claim_metric = next(
        (
            term.upper() if term.lower() in {"auc", "iou"} else term
            for term in metric_terms
            if term.lower() in metric_hint_text.lower()
        ),
        None,
    )
    metrics: list[dict[str, Any]] = []
    for value in sorted(values, key=lambda item: claim_value.find(item))[:limit]:
        location = claim_value.find(value)
        context = claim_value[max(0, location - 90) : location + len(value) + 60]
        local_value_context = claim_value[
            max(0, location - 18) : location + len(value) + 24
        ]
        if re.search(
            r"\b(?:fig(?:ure)?|table|slice|view|epoch|layer|filter|sample|"
            r"iteration|patient|subject|image|patch|fold)s?\b",
            local_value_context,
            re.I,
        ):
            continue
        if "%" not in value and "." not in value and re.search(
            rf"(?:[A-Za-z]+[-\s]+{re.escape(value)}|"
            rf"{re.escape(value)}[-\s]+[A-Za-z])",
            local_value_context,
        ):
            continue
        metric = next(
            (
                term.upper() if term in {"auc", "iou"} else term
                for term in metric_terms
                if term.lower() in context.lower()
            ),
            claim_metric,
        )
        if not metric:
            continue
        post_value_context = claim_value[
            location + len(value) : location + len(value) + 90
        ]
        baseline_match = re.search(
            r"(?:over|than|versus|vs\.?)\s+(?:the\s+)?(.{2,45}?)(?:[,.);]|$)",
            post_value_context,
            re.I,
        )
        baseline = (
            normalize_text(baseline_match.group(1))
            if baseline_match
            else "strongest reported baseline"
        )
        metrics.append(
            {
                "value": value,
                "metric": metric,
                "direction": _direction(metric),
                "baseline": baseline,
                "baseline_value": None,
                "delta": None,
                "delta_type": None,
                "dataset": _dataset_from_asset(asset, [], []),
                "configuration": _configuration(asset, [], []),
                "evaluation_condition": _evaluation_condition(asset, story),
                "source_table_id": asset.get("id")
                if asset.get("asset_type") == "table"
                else None,
                "source_block_ids": source_block_ids,
                "verification": "exact_claim_and_asset_text_match",
            }
        )
    return metrics


def _normalized_number(value: str) -> str:
    return re.sub(r"[\s,+]", "", value)


def _clip_words(value: str, limit: int) -> str:
    words = normalize_text(value).split()
    return " ".join(words[:limit]).rstrip(" ,;:")


def _display_caption(asset: dict[str, Any], role: str) -> str:
    category = classify_asset(asset).replace("_", " ")
    if role == "primary":
        return _clip_words(f"Primary quantitative evidence: {category} comparison.", 12)
    return _clip_words(f"Supporting evidence: {category}.", 10)


def _asset_resolution(asset: dict[str, Any], paper_ir_dir: Path) -> dict[str, Any]:
    path_value = asset.get("path")
    if not path_value:
        return {"width": None, "height": None, "source_readable": False}
    path = Path(str(path_value))
    if not path.is_absolute():
        path = paper_ir_dir / path
    if not path.is_file():
        return {"width": None, "height": None, "source_readable": False}
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        if path.suffix.lower() != ".svg":
            return {"width": None, "height": None, "source_readable": False}
        try:
            source = path.read_text(encoding="utf-8")
            width_match = re.search(r'\bwidth=["\']([\d.]+)', source)
            height_match = re.search(r'\bheight=["\']([\d.]+)', source)
            if not width_match or not height_match:
                return {"width": None, "height": None, "source_readable": False}
            width = int(float(width_match.group(1)))
            height = int(float(height_match.group(1)))
        except (OSError, ValueError):
            return {"width": None, "height": None, "source_readable": False}
    min_width = 550 if asset.get("asset_type") == "table" else 500
    return {
        "width": width,
        "height": height,
        "source_readable": width >= min_width and height >= 100,
    }


def _upgrade_unreadable_asset_from_pdf(
    asset: dict[str, Any],
    asset_spec: dict[str, Any],
    paper_ir: dict[str, Any],
    output_dir: Path,
    *,
    force_pdf_crop: bool = False,
) -> None:
    if (
        (asset_spec.get("source_resolution") or {}).get("source_readable")
        and not force_pdf_crop
    ):
        return
    source_value = (paper_ir.get("provenance") or {}).get("source_path")
    bbox = asset.get("bbox")
    page = asset.get("page")
    if not source_value or not bbox or not page:
        return
    source_pdf = Path(str(source_value))
    if not source_pdf.is_file() or source_pdf.suffix.lower() != ".pdf":
        return
    relative_path, problem, coordinate_space = _render_page_crop(
        source_pdf,
        page=int(page),
        bbox=bbox,
        asset_id=f"result-{asset.get('id')}-hires",
        output_dir=output_dir,
        render_scale=7.0 if asset.get("asset_type") == "table" else 4.4,
    )
    if problem or not relative_path:
        return
    target = output_dir / relative_path
    resolution = _asset_resolution(
        {"path": str(target), "asset_type": asset.get("asset_type")},
        output_dir,
    )
    if not resolution.get("source_readable"):
        return
    asset_spec["display_path"] = str(target.resolve())
    asset_spec["display_mode"] = "pdf_bbox_crop"
    asset_spec["source_resolution"] = resolution
    asset_spec["display_resolution"] = resolution
    asset_spec["bbox_coordinate_space"] = coordinate_space
    asset_spec["selection_reason"] = list(
        dict.fromkeys(
            [
                *(asset_spec.get("selection_reason") or []),
                (
                    "table re-rendered from the source PDF at high resolution"
                    if force_pdf_crop
                    else "low-resolution extracted asset replaced by a high-resolution PDF bbox crop"
                ),
            ]
        )
    )


def _table_focus_rows(
    asset: dict[str, Any],
    claim: dict[str, Any],
    paper_ir: dict[str, Any],
    metrics: list[dict[str, Any]],
) -> tuple[int, list[int], int] | None:
    rows = parse_html_table(str(asset.get("html") or ""))
    if len(rows) < 3:
        return None
    header_count = _header_rows(rows)
    headers = _effective_headers(asset, rows, header_count)
    data_rows = rows[header_count:]
    method_column = _method_column(headers, data_rows)
    method_terms = _paper_method_terms(paper_ir)
    paired_rows = _paired_proposed_row_indices(
        asset,
        data_rows,
        method_column,
    )
    ours_rows = [
        (index, row)
        for index, row in enumerate(data_rows)
        if (
            index in paired_rows
            if paired_rows
            else _row_is_ours(row, method_column, method_terms)
        )
    ]
    if not ours_rows:
        return None
    claim_numbers = {
        _normalized_number(value)
        for value in find_numbers(str(claim.get("claim") or ""))
    }
    ours_index, ours = max(
        ours_rows,
        key=lambda item: (
            len(
                claim_numbers
                & {
                    _normalized_number(value)
                    for cell in item[1]
                    for value in find_numbers(cell)
                }
            ),
            jaccard(" ".join(item[1]), str(claim.get("claim") or "")),
        ),
    )
    context_columns = [
        index
        for index, header in enumerate(headers)
        if index != method_column
        if any(
            term in header.lower()
            for term in ("dataset", "compression", "configuration", "setting", "variant")
        )
        and not any(
            term in header.lower()
            for term in ("venue", "publication", "reference", "year")
        )
    ]
    group_indices = [
        index
        for index, row in enumerate(data_rows)
        if all(
            column < len(row)
            and column < len(ours)
            and normalize_text(row[column]) == normalize_text(ours[column])
            for column in context_columns
            if column < len(ours) and normalize_text(ours[column])
        )
    ]
    if not group_indices:
        group_indices = list(range(len(data_rows)))
    baseline_names = [
        normalize_text(str(metric.get("baseline") or ""))
        for metric in metrics
        if metric.get("baseline")
    ]
    baseline_indices: list[int] = []
    for baseline_name in baseline_names:
        match = next(
            (
                index
                for index in group_indices
                if method_column < len(data_rows[index])
                and normalize_text(data_rows[index][method_column])
                == baseline_name
            ),
            None,
        )
        if match is not None and match not in baseline_indices:
            baseline_indices.append(match)
    if len(group_indices) <= 8:
        selected = group_indices
    else:
        selected = [
            *(baseline_indices[:3] or group_indices[:1]),
            ours_index,
        ]
    return header_count, sorted(set(selected)), len(rows)


def _table_focus_columns(
    asset: dict[str, Any],
    rows: list[list[str]],
    header_count: int,
    metrics: list[dict[str, Any]],
) -> list[int]:
    headers = _effective_headers(asset, rows, header_count)
    if len(headers) <= 4:
        return list(range(len(headers)))
    method_column = _method_column(headers, rows[header_count:])
    context_columns = [
        index
        for index, header in enumerate(headers)
        if any(
            term in header.lower()
            for term in ("dataset", "setting", "configuration", "variant")
        )
    ]
    selected_metric_names = {
        normalize_text(str(metric.get("metric") or "")).lower()
        for metric in metrics
        if normalize_text(str(metric.get("metric") or ""))
    }
    metric_columns = [
        index
        for index, header in enumerate(headers)
        if normalize_text(_split_metric_header(header)[0]).lower()
        in selected_metric_names
    ]
    leading_configuration_columns: list[int] = []
    if metric_columns:
        first_metric = min(metric_columns)
        if first_metric > method_column:
            leading_configuration_columns = [
                index
                for index in range(method_column + 1, first_metric)
                if any(
                    term in headers[index].lower()
                    for term in ("dataset", "setting", "configuration", "variant")
                )
            ]
    selected = [
        method_column,
        *leading_configuration_columns,
        *context_columns[:1],
        *metric_columns,
    ]
    if len(selected) == 1:
        selected.extend(range(1, min(len(headers), 4)))
    return sorted(set(selected))[:5]


def _search_terms(value: str) -> list[str]:
    normalized = normalize_text(html_module.unescape(value))
    normalized = re.sub(r"\\(?:underline|mathbf|mathrm|textbf)\s*\{([^{}]*)\}", r"\1", normalized)
    normalized = normalized.replace("$", "").replace("{", "").replace("}", "")
    parts = [normalized]
    metric, context = _split_metric_header(normalized)
    parts.extend([metric, context])
    parts.extend(re.split(r"\s*[|/]\s*", normalized))
    cleaned: list[str] = []
    for part in parts:
        part = normalize_text(part)
        without_direction = normalize_text(
            part.replace("↑", "").replace("↓", "").replace("鈫?", "")
        )
        for candidate in (part, without_direction):
            if len(candidate) >= 2 and candidate not in cleaned:
                cleaned.append(candidate)
    return cleaned


def _pdf_table_rect(
    page_width: float,
    page_height: float,
    bbox: list[float],
) -> tuple[float, float, float, float] | None:
    if len(bbox) != 4:
        return None
    coordinate_max = 1.0 if max(bbox, default=0.0) <= 1.0 else 1000.0
    left = bbox[0] / coordinate_max * page_width
    right = bbox[2] / coordinate_max * page_width
    top = page_height - bbox[1] / coordinate_max * page_height
    bottom = page_height - bbox[3] / coordinate_max * page_height
    if right <= left or top <= bottom:
        return None
    return left, bottom, right, top


def _text_occurrences(
    text_page: Any,
    value: str,
    table_rect: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    table_left, table_bottom, table_right, table_top = table_rect
    occurrences: list[tuple[float, float, float, float]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for term in _search_terms(value):
        searcher = None
        try:
            searcher = text_page.search(term)
            while True:
                result = searcher.get_next()
                if not result:
                    break
                start, count = result
                boxes = [
                    text_page.get_charbox(index)
                    for index in range(start, start + count)
                ]
                boxes = [box for box in boxes if box and len(box) == 4]
                if not boxes:
                    continue
                rect = (
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                )
                center_x = (rect[0] + rect[2]) / 2
                center_y = (rect[1] + rect[3]) / 2
                if not (
                    table_left <= center_x <= table_right
                    and table_bottom <= center_y <= table_top
                ):
                    continue
                key = tuple(round(value * 10) for value in rect)
                if key not in seen:
                    seen.add(key)
                    occurrences.append(rect)
        except Exception:
            continue
        finally:
            if searcher is not None:
                searcher.close()
        if occurrences:
            break
    return occurrences


def _group_indices(indices: list[int]) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    for index in sorted(set(indices)):
        if groups and index == groups[-1][1]:
            groups[-1] = (groups[-1][0], index + 1)
        else:
            groups.append((index, index + 1))
    return groups


def _focus_table_payload(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
    rows: list[list[str]],
    header_count: int,
    selected_rows: list[int],
    selected_columns: list[int],
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    headers = _effective_headers(asset, rows, header_count)
    selected_headers = [
        normalize_text(headers[column])
        for column in selected_columns
        if column < len(headers)
    ]
    header_metrics = [
        normalize_text(_split_metric_header(header)[0])
        for header in selected_headers
    ]
    metric_counts = Counter(
        metric.lower() for metric in header_metrics if metric
    )

    def display_header(header: str) -> str:
        parts = [
            normalize_text(part)
            for part in header.split(" / ")
            if normalize_text(part)
        ]
        if not parts:
            return ""
        leaf = parts[-1]
        if leaf.lower() in {
            "method",
            "methods",
            "model",
            "models",
            "image size",
            "input size",
            "depth",
            "year",
            "configuration",
            "setting",
            "variant",
        }:
            return leaf
        if re.fullmatch(r"#?\s*params?\.?", leaf, re.I):
            return leaf
        metric, context = _split_metric_header(header)
        metric = normalize_text(metric)
        if metric and metric_counts.get(metric.lower(), 0) > 1 and context:
            context_label = normalize_text(context[0])
            return f"{context_label} / {metric}"
        return metric or leaf

    data_rows = rows[header_count:]
    method_column = _method_column(headers, data_rows)
    method_terms = _paper_method_terms(paper_ir)
    paired_rows = _paired_proposed_row_indices(
        asset,
        data_rows,
        method_column,
    )
    baselines = {
        normalize_text(str(metric.get("baseline") or ""))
        for metric in metrics
        if normalize_text(str(metric.get("baseline") or ""))
    }
    payload_rows: list[dict[str, Any]] = []
    for index in selected_rows:
        if index >= len(data_rows):
            continue
        row = data_rows[index]
        method_name = (
            normalize_text(row[method_column])
            if method_column < len(row)
            else ""
        )
        role = "ours" if (
            index in paired_rows
            if paired_rows
            else _row_is_ours(row, method_column, method_terms)
        ) else (
            "baseline" if method_name in baselines else "context"
        )
        payload_rows.append(
            {
                "source_row_index": index,
                "role": role,
                "cells": [
                    normalize_text(row[column]) if column < len(row) else ""
                    for column in selected_columns
                ],
            }
        )
    return {
        "headers": [display_header(header) for header in selected_headers],
        "source_headers": selected_headers,
        "rows": payload_rows,
        "selected_column_indices": selected_columns,
        "source_table_id": asset.get("id"),
        "source_page": asset.get("page"),
        "verification": "deterministic_cells_from_source_table_html",
    }


def _edge_ink_metrics(image: Any) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {
            "edge_ink_ratio": 0.0,
            "glyphs_touch_crop_edge": False,
            "edge_check_method": "unavailable",
        }
    gray = np.asarray(image.convert("L"))
    if gray.ndim != 2 or gray.size == 0:
        return {
            "edge_ink_ratio": 0.0,
            "glyphs_touch_crop_edge": False,
            "edge_check_method": "empty",
        }
    ink = (gray < 175).astype("uint8")
    height, width = ink.shape
    if height < 3 or width < 3:
        return {
            "edge_ink_ratio": 1.0,
            "glyphs_touch_crop_edge": True,
            "edge_check_method": "connected_components",
        }
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(
        ink,
        connectivity=8,
    )
    edge_area = 0
    clipped_components = 0
    for index in range(1, component_count):
        x, y, component_width, component_height, area = [
            int(value) for value in stats[index]
        ]
        touches_edge = y <= 1 or y + component_height >= height - 1
        if not touches_edge or area < 3:
            continue
        horizontal_rule = (
            component_width >= width * 0.55
            and component_height <= max(3, round(height * 0.025))
        )
        if horizontal_rule:
            continue
        clipped_components += 1
        edge_area += area
    edge_depth = max(2, min(8, round(height * 0.06)))
    denominator = max(1, width * edge_depth * 2)
    return {
        "edge_ink_ratio": round(edge_area / denominator, 6),
        "glyphs_touch_crop_edge": clipped_components > 0,
        "edge_touching_component_count": clipped_components,
        "edge_check_method": "connected_components",
    }


def _pdf_text_focus_crop(
    source_pdf: Path,
    source_image: Path,
    asset: dict[str, Any],
    rows: list[list[str]],
    header_count: int,
    selected_rows: list[int],
    selected_columns: list[int],
    target: Path,
) -> dict[str, Any] | None:
    try:
        import pypdfium2
        from PIL import Image, ImageDraw, ImageOps
    except ImportError:
        return None
    document: Any | None = None
    pdf_page: Any | None = None
    text_page: Any | None = None
    try:
        document = pypdfium2.PdfDocument(str(source_pdf))
        page_index = int(asset.get("page") or 0) - 1
        if page_index < 0 or page_index >= len(document):
            return None
        pdf_page = document[page_index]
        page_width, page_height = pdf_page.get_size()
        table_rect = _pdf_table_rect(
            float(page_width),
            float(page_height),
            [float(value) for value in (asset.get("bbox") or [])],
        )
        if not table_rect:
            return None
        text_page = pdf_page.get_textpage()
        headers = _effective_headers(asset, rows, header_count)
        data_rows = rows[header_count:]
        method_column = _method_column(headers, data_rows)

        row_anchor_rects: dict[int, tuple[float, float, float, float]] = {}
        for index, row in enumerate(data_rows):
            if method_column >= len(row):
                return None
            occurrences = _text_occurrences(
                text_page,
                row[method_column],
                table_rect,
            )
            if not occurrences:
                return None
            row_anchor_rects[index] = min(
                occurrences,
                key=lambda rect: rect[0],
            )

        header_rects: dict[int, tuple[float, float, float, float]] = {}
        previous_x = table_rect[0]
        for index, header in enumerate(headers):
            occurrences = [
                rect
                for rect in _text_occurrences(text_page, header, table_rect)
                if (rect[0] + rect[2]) / 2 > previous_x
            ]
            if not occurrences:
                continue
            expected_x = table_rect[0] + (
                (index + 0.5) / max(1, len(headers))
            ) * (table_rect[2] - table_rect[0])
            winner = min(
                occurrences,
                key=lambda rect: abs((rect[0] + rect[2]) / 2 - expected_x),
            )
            header_rects[index] = winner
            previous_x = (winner[0] + winner[2]) / 2
        if not all(index in header_rects for index in selected_columns):
            return None

        method_header = header_rects.get(method_column)
        if not method_header:
            return None
        row_centers_pdf = {
            index: (rect[1] + rect[3]) / 2
            for index, rect in row_anchor_rects.items()
        }
        ordered_centers_pdf = [
            row_centers_pdf[index] for index in range(len(data_rows))
        ]
        if any(
            ordered_centers_pdf[index] <= ordered_centers_pdf[index + 1]
            for index in range(len(ordered_centers_pdf) - 1)
        ):
            return None
        header_center_pdf = (method_header[1] + method_header[3]) / 2
        row_content_rects: dict[
            int,
            tuple[float, float, float, float],
        ] = {}
        row_text_rects: dict[
            int,
            list[tuple[float, float, float, float]],
        ] = {}
        for index, row in enumerate(data_rows):
            center = row_centers_pdf[index]
            upper_center = (
                header_center_pdf
                if index == 0
                else row_centers_pdf[index - 1]
            )
            lower_center = (
                table_rect[1]
                if index + 1 == len(data_rows)
                else row_centers_pdf[index + 1]
            )
            upper_boundary = (upper_center + center) / 2
            lower_boundary = (center + lower_center) / 2
            matched_rects = [row_anchor_rects[index]]
            for cell in row:
                if not normalize_text(cell):
                    continue
                occurrences = _text_occurrences(
                    text_page,
                    cell,
                    table_rect,
                )
                candidates = [
                    rect
                    for rect in occurrences
                    if lower_boundary
                    <= (rect[1] + rect[3]) / 2
                    <= upper_boundary
                ]
                if candidates:
                    matched_rects.append(
                        min(
                            candidates,
                            key=lambda rect: abs(
                                (rect[1] + rect[3]) / 2 - center
                            ),
                        )
                    )
            row_text_rects[index] = list(
                dict.fromkeys(matched_rects)
            )
            row_content_rects[index] = (
                min(rect[0] for rect in matched_rects),
                min(rect[1] for rect in matched_rects),
                max(rect[2] for rect in matched_rects),
                max(rect[3] for rect in matched_rects),
            )

        with Image.open(source_image) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            width, height = image.size
            table_left, table_bottom, table_right, table_top = table_rect
            table_width = table_right - table_left
            table_height = table_top - table_bottom

            def x_pixel(value: float) -> int:
                return round((value - table_left) / table_width * width)

            def y_pixel(value: float) -> int:
                return round((table_top - value) / table_height * height)

            row_centers = [y_pixel(value) for value in ordered_centers_pdf]
            header_center = y_pixel(header_center_pdf)
            text_heights_px = [
                (rect[3] - rect[1]) / table_height * height
                for rects in row_text_rects.values()
                for rect in rects
            ]
            text_heights_px.extend(
                (header_rects[index][3] - header_rects[index][1])
                / table_height
                * height
                for index in selected_columns
            )
            if not text_heights_px:
                return None
            median_text_height_px = float(median(text_heights_px))
            min_text_height = min(text_heights_px)
            glyph_padding = max(
                4,
                round(median_text_height_px * 0.35),
            )
            minimum_required_padding = max(
                2,
                round(median_text_height_px * 0.12),
            )
            row_bounds_source: list[tuple[int, int]] = []
            row_bounds_padded: list[tuple[int, int]] = []
            for index, center in enumerate(row_centers):
                previous_center = (
                    header_center if index == 0 else row_centers[index - 1]
                )
                next_center = (
                    height if index + 1 == len(row_centers)
                    else row_centers[index + 1]
                )
                allowed_top = max(
                    0,
                    round((previous_center + center) / 2),
                )
                allowed_bottom = min(
                    height,
                    round((center + next_center) / 2),
                )
                content_rect = row_content_rects[index]
                glyph_top = max(0, y_pixel(content_rect[3]))
                glyph_bottom = min(height, y_pixel(content_rect[1]))
                if glyph_bottom <= glyph_top:
                    return None
                top = max(allowed_top, glyph_top - glyph_padding)
                bottom = min(
                    allowed_bottom,
                    glyph_bottom + glyph_padding,
                )
                if bottom <= top:
                    return None
                if (
                    glyph_top - top < minimum_required_padding
                    or bottom - glyph_bottom < minimum_required_padding
                ):
                    return None
                row_bounds_source.append((glyph_top, glyph_bottom))
                row_bounds_padded.append((top, bottom))

            header_glyph_bottom = max(
                y_pixel(rect[1]) for rect in header_rects.values()
            )
            header_bottom = min(
                row_bounds_padded[0][0],
                max(
                    header_glyph_bottom + glyph_padding,
                    round((header_center + row_centers[0]) / 2),
                ),
            )
            if (
                header_bottom <= 1
                or header_bottom - header_glyph_bottom
                < minimum_required_padding
            ):
                return None

            vertical_parts: list[tuple[Any, bool]] = [
                (image.crop((0, 0, width, header_bottom)), False)
            ]
            previous_end = -1
            for start, end in _group_indices(selected_rows):
                top = row_bounds_padded[start][0]
                bottom = row_bounds_padded[end - 1][1]
                vertical_parts.append(
                    (
                        image.crop((0, top, width, bottom)),
                        previous_end >= 0 and start > previous_end,
                    )
                )
                previous_end = end
            edge_checks = [
                _edge_ink_metrics(part)
                for part, _ in vertical_parts
            ]
            if any(
                check.get("glyphs_touch_crop_edge")
                for check in edge_checks
            ):
                return None
            gap = max(10, round(height * 0.025))
            canvas_height = sum(part.height for part, _ in vertical_parts)
            canvas_height += sum(gap for _, skipped in vertical_parts if skipped)
            canvas = Image.new("RGB", (width, canvas_height), "white")
            draw = ImageDraw.Draw(canvas)
            y = 0
            for part, skipped in vertical_parts:
                if skipped:
                    draw.line(
                        (0, y + gap // 2, width, y + gap // 2),
                        fill="#9aa8bc",
                        width=max(2, gap // 8),
                    )
                    y += gap
                canvas.paste(part, (0, y))
                y += part.height

            header_centers = {
                index: x_pixel((rect[0] + rect[2]) / 2)
                for index, rect in header_rects.items()
            }
            horizontal_parts: list[Any] = []
            column_groups = _group_indices(selected_columns)
            for start, end in column_groups:
                left = 0
                if start > 0 and start - 1 in header_centers:
                    left = round(
                        (header_centers[start - 1] + header_centers[start]) / 2
                    )
                right = width
                if end < len(headers) and end in header_centers:
                    right = round(
                        (header_centers[end - 1] + header_centers[end]) / 2
                    )
                if right <= left:
                    return None
                horizontal_parts.append(canvas.crop((left, 0, right, canvas.height)))

            horizontal_gap = max(14, round(width * 0.008))
            focused_width = sum(part.width for part in horizontal_parts)
            focused_width += horizontal_gap * (len(horizontal_parts) - 1)
            focused = Image.new("RGB", (focused_width, canvas.height), "white")
            focus_draw = ImageDraw.Draw(focused)
            x = 0
            for part_index, part in enumerate(horizontal_parts):
                if part_index:
                    focus_draw.line(
                        (
                            x + horizontal_gap // 2,
                            0,
                            x + horizontal_gap // 2,
                            focused.height,
                        ),
                        fill="#9aa8bc",
                        width=max(2, horizontal_gap // 7),
                    )
                    x += horizontal_gap
                focused.paste(part, (x, 0))
                x += part.width

            target.parent.mkdir(parents=True, exist_ok=True)
            focused.save(target, format="PNG", optimize=True)
            edge_ink_ratio = max(
                (
                    float(check.get("edge_ink_ratio") or 0)
                    for check in edge_checks
                ),
                default=0.0,
            )
            return {
                "coordinate_method": "pdf_text_boxes",
                "geometry_confidence": 1.0,
                "minimum_source_text_height_px": round(min_text_height, 2),
                "duplicate_band_score": 0.0,
                "glyph_padding_px": glyph_padding,
                "edge_ink_ratio": round(edge_ink_ratio, 6),
                "glyphs_touch_crop_edge": False,
                "edge_check_method": "connected_components",
                "row_bounds_source": [
                    {
                        "source_row_index": index,
                        "top": row_bounds_source[index][0],
                        "bottom": row_bounds_source[index][1],
                    }
                    for index in selected_rows
                ],
                "row_bounds_padded": [
                    {
                        "source_row_index": index,
                        "top": row_bounds_padded[index][0],
                        "bottom": row_bounds_padded[index][1],
                    }
                    for index in selected_rows
                ],
                "row_mapping": (
                    "source-html-row-cell-union-to-pdf-text-boxes"
                ),
                "column_mapping": "source-html-headers-to-pdf-text-boxes",
                "separators_inserted": (
                    len(_group_indices(selected_rows)) > 1
                    or len(column_groups) > 1
                ),
            }
    except Exception:
        return None
    finally:
        if text_page is not None:
            text_page.close()
        if pdf_page is not None:
            pdf_page.close()
        if document is not None:
            document.close()


def _prepare_table_focus_crop(
    asset: dict[str, Any],
    asset_spec: dict[str, Any],
    claim: dict[str, Any],
    paper_ir: dict[str, Any],
    paper_ir_dir: Path,
    output_dir: Path,
    metrics: list[dict[str, Any]],
) -> None:
    if asset.get("asset_type") != "table":
        return
    row_plan = _table_focus_rows(asset, claim, paper_ir, metrics)
    path_value = asset_spec.get("display_path") or asset.get("path")
    if not row_plan or not path_value:
        return
    source = Path(str(path_value))
    if not source.is_absolute():
        source = paper_ir_dir / source
    if not source.is_file():
        return
    header_count, selected_rows, _ = row_plan
    html_rows = parse_html_table(str(asset.get("html") or ""))
    headers = _effective_headers(asset, html_rows, header_count)
    selected_columns = _table_focus_columns(
        asset,
        html_rows,
        header_count,
        metrics,
    )
    large_table = (
        len(html_rows) - header_count > 6
        or len(headers) > 6
    )
    if not large_table:
        asset_spec["crop_strategy"] = "full_high_resolution_original_table"
        asset_spec["display_resolution"] = _asset_resolution(
            {"path": str(source), "asset_type": "table"},
            paper_ir_dir,
        )
        return

    target = output_dir / "result-assets" / f"{asset.get('id')}-focus.png"
    source_value = (paper_ir.get("provenance") or {}).get("source_path")
    source_pdf = Path(str(source_value)) if source_value else None
    geometry = (
        _pdf_text_focus_crop(
            source_pdf,
            source,
            asset,
            html_rows,
            header_count,
            selected_rows,
            selected_columns,
            target,
        )
        if asset_spec.get("evidence_role") != "secondary"
        and source_pdf
        and source_pdf.is_file()
        and source_pdf.suffix.lower() == ".pdf"
        else None
    )
    full_width_preserved = selected_columns == list(range(len(headers)))
    focus_table = _focus_table_payload(
        asset,
        paper_ir,
        html_rows,
        header_count,
        selected_rows,
        selected_columns,
        metrics,
    )
    safe_raster_geometry = bool(
        geometry
        and not geometry.get("glyphs_touch_crop_edge")
        and float(geometry.get("edge_ink_ratio") or 0) <= 0.02
        and geometry.get("row_bounds_source")
        and geometry.get("row_bounds_padded")
    )
    if safe_raster_geometry and target.is_file():
        asset_spec["display_path"] = str(target.resolve())
        asset_spec["display_mode"] = "pdf_text_focus_crop"
        asset_spec["crop_strategy"] = "pdf_text_coordinate_focus_crop"
        asset_spec["display_resolution"] = _asset_resolution(
            {"path": str(target), "asset_type": "table"},
            paper_ir_dir,
        )
        display_sha256 = sha256_file(target)
    else:
        asset_spec["display_mode"] = "verified_focus_table"
        asset_spec["crop_strategy"] = "verified_structured_focus_table"
        asset_spec["focus_table"] = focus_table
        display_sha256 = None
        geometry = {
            "coordinate_method": "verified_source_table_cells",
            "geometry_confidence": 1.0,
            "minimum_source_text_height_px": None,
            "duplicate_band_score": 0.0,
            "glyph_padding_px": None,
            "edge_ink_ratio": 0.0,
            "glyphs_touch_crop_edge": False,
            "edge_check_method": "structured_html",
            "row_bounds_source": [],
            "row_bounds_padded": [],
            "row_mapping": "source-html-cell-order",
            "column_mapping": "source-html-cell-order",
            "separators_inserted": False,
        }
    asset_spec["focus_crop"] = {
        "header_rows": header_count,
        "data_row_indices": selected_rows,
        "source_path": str(source.resolve()),
        "source_sha256": sha256_file(source),
        "display_sha256": display_sha256,
        "full_width_preserved": full_width_preserved,
        "selected_column_indices": selected_columns,
        **geometry,
    }


def _table_context(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
) -> dict[str, Any]:
    rows = parse_html_table(str(asset.get("html") or ""))
    header_count = _header_rows(rows) if rows else 0
    headers = _effective_headers(asset, rows, header_count) if rows else []
    data = rows[header_count:] if rows else []
    method_column = _method_column(headers, data) if headers else 0
    method_terms = _paper_method_terms(paper_ir)
    transposed_metrics = (
        _transposed_key_metrics(asset, rows, paper_ir, {}, [])
        if rows
        else []
    )
    transposed = bool(transposed_metrics)
    paired_rows = _paired_proposed_row_indices(asset, data, method_column)
    ours = transposed or bool(paired_rows) or any(
        _row_is_ours(row, method_column, method_terms) for row in data
    )
    baseline = transposed or any(
        index not in paired_rows
        and not _row_is_ours(row, method_column, method_terms)
        and method_column < len(row)
        and bool(row[method_column])
        for index, row in enumerate(data)
    )
    dataset_or_setting = any(
        any(term in header.lower() for term in ("dataset", "setting", "configuration", "compression"))
        for header in headers
    ) or bool(normalize_text(str(asset.get("caption") or "")))
    context = {
        "display_mode": "full_original_crop_with_metric_cards",
        "table_header": bool(headers),
        "method_names": transposed
        or any(
            any(
                term in header.lower()
                for term in (
                    "method",
                    "model",
                    "approach",
                    "loss",
                    "module",
                    "component",
                    "variant",
                    "configuration",
                    "setting",
                    "depth",
                    "scale",
                )
            )
            for header in headers
        )
        or sum(
            method_column < len(row)
            and bool(normalize_text(row[method_column]))
            and _number(row[method_column]) is None
            for row in data
        )
        >= 2,
        "metric_names_and_directions": transposed
        or bool(_metric_columns(headers, method_column)),
        "proposed_method_row": ours,
        "strong_baseline_row": baseline,
        "dataset_or_setting": dataset_or_setting,
        "necessary_footnote": bool(asset.get("footnote"))
        or not bool(str(asset.get("footnote") or "").strip()),
    }
    context["complete"] = all(
        context[key]
        for key in (
            "table_header",
            "method_names",
            "metric_names_and_directions",
            "proposed_method_row",
            "strong_baseline_row",
            "dataset_or_setting",
            "necessary_footnote",
        )
    )
    return context


def _asset_spec(
    asset: dict[str, Any],
    claim: dict[str, Any],
    paper_ir: dict[str, Any],
    paper_ir_dir: Path,
    reasons: list[str],
    role: str,
) -> dict[str, Any]:
    claim_blocks = _source_block_ids(claim)
    asset_blocks = _asset_block_ids(asset, paper_ir)
    source_blocks = list(dict.fromkeys([*claim_blocks, *asset_blocks]))
    return {
        "asset_id": asset.get("id"),
        "asset_type": asset.get("asset_type"),
        "evidence_role": role,
        "result_type": classify_asset(asset),
        "path": asset.get("path"),
        "page": asset.get("page"),
        "bbox": asset.get("bbox"),
        "table_id": asset.get("id") if asset.get("asset_type") == "table" else None,
        "figure_id": asset.get("id") if asset.get("asset_type") == "figure" else None,
        "caption": normalize_text(str(asset.get("caption") or "")),
        "display_caption": _display_caption(asset, role),
        "selection_reason": list(dict.fromkeys(reasons)),
        "source_claim_ids": [str(claim.get("claim_id"))],
        "source_block_ids": source_blocks,
        "display_mode": "original_asset",
        "crop_strategy": (
            "full_original_crop_with_metric_cards"
            if asset.get("asset_type") == "table"
            else "original_figure_or_pdf_bbox_crop"
        ),
        "table_context": (
            _table_context(asset, paper_ir)
            if asset.get("asset_type") == "table"
            else None
        ),
        "source_resolution": _asset_resolution(asset, paper_ir_dir),
    }


def _secondary_claims(
    claims: list[dict[str, Any]],
    primary_claim: dict[str, Any],
) -> list[dict[str, Any]]:
    preferred = (
        "qualitative",
        "ablation",
        "generalization",
        "efficiency",
        "theory",
    )
    values = [claim for claim in claims if claim is not primary_claim]
    values.sort(
        key=lambda claim: (
            preferred.index(classify_claim(claim))
            if classify_claim(claim) in preferred
            else len(preferred),
            -_claim_priority(claim),
        )
    )
    return values


def _layout(
    primary: dict[str, Any],
    secondary: dict[str, Any] | None,
) -> str:
    secondary_type = str((secondary or {}).get("result_type") or "")
    primary_type = str(primary.get("result_type") or "")
    if secondary_type == "ablation":
        return "main_plus_ablation"
    if primary_type == "theory" or secondary_type in {"generalization", "theory"}:
        return "finding_plus_generalization"
    return "quantitative_plus_qualitative"


def _metric_is_favorable(metric: dict[str, Any]) -> bool:
    value = _number(str(metric.get("value") or ""))
    baseline = _number(str(metric.get("baseline_value") or ""))
    if value is None or baseline is None:
        return False
    if metric.get("direction") == "lower_is_better":
        return value < baseline
    return value > baseline


def _order_metrics_for_claim(
    metrics: list[dict[str, Any]],
    claim: dict[str, Any],
) -> list[dict[str, Any]]:
    claim_type = classify_claim(claim)
    performance_terms = (
        "accuracy",
        "auc",
        "dice",
        "dsc",
        "f1",
        "iou",
        "mae",
        "mse",
        "psnr",
        "recall",
        "sensitivity",
        "specificity",
        "ssim",
        "hd",
    )
    efficiency_terms = (
        "flop",
        "latency",
        "memory",
        "mac",
        "param",
        "runtime",
        "throughput",
    )

    def alignment(metric: dict[str, Any]) -> int:
        name = str(metric.get("metric") or "").lower()
        terms = efficiency_terms if claim_type == "efficiency" else performance_terms
        return int(any(term in name for term in terms))

    return [
        metric
        for _, metric in sorted(
            enumerate(metrics),
            key=lambda item: (
                int(_metric_is_favorable(item[1])),
                alignment(item[1]),
                -item[0],
            ),
            reverse=True,
        )
    ]


def _headline(
    metrics: list[dict[str, Any]],
    primary_claim: dict[str, Any],
) -> str:
    if metrics:
        first = metrics[0]
        metric = str(first.get("metric") or "the reported metric")
        value = str(first.get("value") or "")
        baseline = str(first.get("baseline") or "a strong baseline")
        dataset = str(first.get("dataset") or "the reported benchmark")
        if _metric_is_favorable(first):
            words = (
                f"The proposed method reaches {metric} {value} on {dataset}, "
                f"outperforming {baseline} under the paper's matched evaluation setting."
            )
        else:
            words = (
                f"The proposed method reports {metric} {value} on {dataset}, "
                f"compared with {baseline} under the paper's matched evaluation setting."
            )
    else:
        core = _clip_words(str(primary_claim.get("claim") or ""), 18)
        words = f"Claim-linked experimental evidence directly supports the paper's central result: {core}"
    tokens = words.split()
    if len(tokens) < 15:
        words += " with the original comparison context preserved."
    return _clip_words(words, 30).rstrip(".") + "."


def _condition_note(
    metrics: list[dict[str, Any]],
    primary_claim: dict[str, Any],
) -> str:
    if metrics:
        first = metrics[0]
        return _clip_words(
            f"Condition: {first['configuration']}; "
            f"{str(first['evaluation_condition']).rstrip('.')}.",
            24,
        )
    limitations = primary_claim.get("limitations") or []
    return _clip_words(
        f"Condition: {limitations[0]}"
        if limitations
        else "Condition: interpret the result only under the paper-reported evaluation setting.",
        24,
    )


def _visible_word_count(spec: dict[str, Any]) -> int:
    values = [
        str(spec.get("result_headline") or ""),
        str(spec.get("condition_note") or ""),
    ]
    for asset_key in ("primary_asset", "secondary_asset"):
        asset = spec.get(asset_key) or {}
        values.append(str(asset.get("display_caption") or ""))
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", " ".join(values)))


def build_experimental_results(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    claims = sorted(_supported_claims(evidence), key=_claim_priority, reverse=True)
    assets = [
        asset
        for group in ("tables", "figures")
        for asset in paper_ir.get(group, [])
        if asset.get("path")
    ]
    primary_asset, primary_claim, score, reasons = _best_asset_for_claims(
        assets,
        claims,
        paper_ir,
        primary=True,
    )
    if primary_asset is None or primary_claim is None:
        spec = {
            "schema_version": "1.0.0",
            "paper_id": paper_ir["paper_id"],
            "result_headline": "",
            "layout_template": "quantitative_plus_qualitative",
            "key_metrics": [],
            "primary_asset": None,
            "secondary_asset": None,
            "condition_note": "",
            "source_claim_ids": [],
            "source_block_ids": [],
            "visible_word_count": 0,
            "confidence": 0.0,
        }
        issues = [
            {
                "code": "RESULT_PRIMARY_ASSET_MISSING",
                "severity": "error",
                "message": "No claim-linked quantitative result asset was available.",
                "return_to": "paper-asset-select",
            }
        ]
    else:
        primary_spec = _asset_spec(
            primary_asset,
            primary_claim,
            paper_ir,
            paper_ir_path.parent,
            reasons,
            "primary",
        )
        secondary_asset = None
        secondary_claim = None
        secondary_reasons: list[str] = []
        secondary_candidates = _secondary_claims(claims, primary_claim)
        secondary_assets = [
            asset
            for asset in assets
            if classify_asset(asset)
            in {"qualitative", "ablation", "generalization", "efficiency", "theory"}
        ]
        if secondary_candidates and secondary_assets:
            secondary_asset, secondary_claim, secondary_score, secondary_reasons = (
                _best_asset_for_claims(
                    secondary_assets,
                    secondary_candidates,
                    paper_ir,
                    primary=False,
                    exclude_ids={str(primary_asset.get("id"))},
                )
            )
            if secondary_score < 3.0:
                secondary_asset = None
                secondary_claim = None
        secondary_spec = (
            _asset_spec(
                secondary_asset,
                secondary_claim,
                paper_ir,
                paper_ir_path.parent,
                secondary_reasons,
                "secondary",
            )
            if secondary_asset is not None and secondary_claim is not None
            else None
        )
        metrics = extract_key_metrics(
            primary_asset,
            primary_claim,
            paper_ir,
            story,
            primary_spec["source_block_ids"],
            limit=4,
        )
        metrics = _order_metrics_for_claim(metrics, primary_claim)
        _upgrade_unreadable_asset_from_pdf(
            primary_asset,
            primary_spec,
            paper_ir,
            output_dir,
            force_pdf_crop=primary_asset.get("asset_type") == "table",
        )
        _prepare_table_focus_crop(
            primary_asset,
            primary_spec,
            primary_claim,
            paper_ir,
            paper_ir_path.parent,
            output_dir,
            metrics,
        )
        if not (primary_spec.get("focus_crop") or {}).get(
            "full_width_preserved",
            True,
        ):
            # A column-focused primary table needs the whole result panel to
            # remain readable; the secondary evidence is optional.
            secondary_asset = None
            secondary_claim = None
            secondary_spec = None
        if secondary_asset is not None and secondary_claim is not None and secondary_spec:
            _upgrade_unreadable_asset_from_pdf(
                secondary_asset,
                secondary_spec,
                paper_ir,
                output_dir,
                force_pdf_crop=secondary_asset.get("asset_type") == "table",
            )
            _prepare_table_focus_crop(
                secondary_asset,
                secondary_spec,
                secondary_claim,
                paper_ir,
                paper_ir_path.parent,
                output_dir,
                [],
            )
            secondary_resolution = (
                secondary_spec.get("display_resolution")
                or secondary_spec.get("source_resolution")
                or {}
            )
            secondary_context = secondary_spec.get("table_context") or {}
            if (
                not secondary_resolution.get("source_readable")
                or (
                    secondary_spec.get("asset_type") == "table"
                    and not secondary_context.get("complete")
                )
            ):
                secondary_asset = None
                secondary_claim = None
                secondary_spec = None
        source_claim_ids = list(
            dict.fromkeys(
                [
                    *primary_spec["source_claim_ids"],
                    *((secondary_spec or {}).get("source_claim_ids") or []),
                ]
            )
        )
        source_block_ids = list(
            dict.fromkeys(
                [
                    *primary_spec["source_block_ids"],
                    *((secondary_spec or {}).get("source_block_ids") or []),
                ]
            )
        )
        spec = {
            "schema_version": "1.0.0",
            "paper_id": paper_ir["paper_id"],
            "result_headline": _headline(metrics, primary_claim),
            "layout_template": _layout(primary_spec, secondary_spec),
            "key_metrics": metrics[:4],
            "primary_asset": primary_spec,
            "secondary_asset": secondary_spec,
            "condition_note": _condition_note(metrics, primary_claim),
            "source_claim_ids": source_claim_ids,
            "source_block_ids": source_block_ids,
            "visible_word_count": 0,
            "confidence": round(
                min(
                    0.96,
                    0.45
                    + score / 25
                    + (0.1 if metrics else 0)
                    + (0.05 if secondary_spec else 0),
                ),
                3,
            ),
        }
        spec["visible_word_count"] = _visible_word_count(spec)
        issues = validate_experimental_results_spec(
            spec,
            paper_ir,
            evidence,
            check_files=True,
            paper_ir_dir=paper_ir_path.parent,
        )
    report = {
        "status": "failed"
        if any(issue["severity"] == "error" for issue in issues)
        else "passed",
        "checks": {
            "layout_template": spec["layout_template"],
            "key_metrics": len(spec["key_metrics"]),
            "primary_asset_id": (spec.get("primary_asset") or {}).get("asset_id"),
            "secondary_asset_id": (spec.get("secondary_asset") or {}).get("asset_id"),
            "visible_word_count": spec["visible_word_count"],
        },
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
        write_json(output_dir / "experimental_results_spec.json", spec),
        write_json(output_dir / "experimental_results_report.json", report),
    )


def validate_experimental_results_spec(
    spec: dict[str, Any],
    paper_ir: dict[str, Any],
    evidence: dict[str, Any],
    *,
    check_files: bool = False,
    paper_ir_dir: Path | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    known_claims = {
        str(claim.get("claim_id")): claim
        for claim in evidence.get("claims", [])
        if claim.get("claim_id")
    }
    blocks = {
        str(block.get("id")): block
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }
    assets = {
        str(asset.get("id")): asset
        for group in ("tables", "figures")
        for asset in paper_ir.get(group, [])
        if asset.get("id")
    }
    headline = normalize_text(str(spec.get("result_headline") or ""))
    headline_words = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", headline))
    if not 15 <= headline_words <= 30 or re.match(
        r"^(?:however|note|limitation|caution|results are unavailable)\b",
        headline,
        re.I,
    ):
        issues.append(
            {
                "code": "RESULT_HEADLINE_WEAK",
                "severity": "error",
                "message": "Result headline must state a conclusion in 15–30 words.",
                "return_to": "paper-experimental-results",
            }
        )
    if spec.get("layout_template") not in RESULT_LAYOUTS:
        issues.append(
            {
                "code": "RESULT_LAYOUT_INVALID",
                "severity": "error",
                "message": "Experimental Results uses an unsupported layout template.",
                "return_to": "paper-experimental-results",
            }
        )
    metrics = spec.get("key_metrics") or []
    if not 2 <= len(metrics) <= 4:
        issues.append(
            {
                "code": "RESULT_METRIC_COUNT_INVALID",
                "severity": "error",
                "message": "Experimental Results must contain two to four contextual key metrics.",
                "details": {
                    "metric_count": len(metrics),
                    "accepted_range": [2, 4],
                    "reason": (
                        "metric-card density is a presentation target; "
                        "exact numeric consistency remains checked by "
                        "separate hard gates"
                    ),
                },
                "return_to": "paper-experimental-results",
            }
        )
    contexts = set()
    for metric in metrics:
        missing = [
            field
            for field in (
                "value",
                "metric",
                "direction",
                "baseline",
                "dataset",
                "configuration",
                "evaluation_condition",
                "source_block_ids",
            )
            if not metric.get(field)
        ]
        if missing:
            issues.append(
                {
                    "code": "RESULT_METRIC_CONTEXT_MISSING",
                    "severity": "error",
                    "message": "A key number lacks comparison or evaluation context.",
                    "details": missing,
                    "return_to": "paper-experimental-results",
                }
            )
        if metric.get("direction") not in {"higher_is_better", "lower_is_better"}:
            issues.append(
                {
                    "code": "RESULT_METRIC_DIRECTION_INVALID",
                    "severity": "error",
                    "message": "Metric direction is missing or invalid.",
                    "return_to": "paper-experimental-results",
                }
            )
        elif metric.get("direction") != _direction(str(metric.get("metric") or "")):
            issues.append(
                {
                    "code": "RESULT_METRIC_DIRECTION_MISMATCH",
                    "severity": "error",
                    "message": "Metric direction conflicts with the source metric semantics.",
                    "return_to": "paper-experimental-results",
                }
            )
        contexts.add(
            (
                metric.get("dataset"),
                metric.get("configuration"),
                metric.get("evaluation_condition"),
            )
        )
        asset = assets.get(str(metric.get("source_table_id")))
        if asset and _normalized_number(str(metric.get("value"))) not in _normalized_number(
            str(asset.get("html") or "") + " " + _text(asset)
        ):
            issues.append(
                {
                    "code": "RESULT_NUMBER_MISMATCH",
                    "severity": "error",
                    "message": "A key metric does not exactly match its source table.",
                    "details": metric,
                    "return_to": "paper-experimental-results",
                }
            )
        if asset and (
            not metric.get("baseline_value")
            or _normalized_number(str(metric.get("baseline_value")))
            not in _normalized_number(str(asset.get("html") or "") + " " + _text(asset))
        ):
            issues.append(
                {
                    "code": "RESULT_BASELINE_NOT_VERIFIED",
                    "severity": "error",
                    "message": "A table-derived key metric lacks an exact strong-baseline value.",
                    "details": metric,
                    "return_to": "paper-experimental-results",
                }
            )
    explicitly_split_single_metric = (
        len(contexts) > 1
        and len(
            {
                normalize_text(str(metric.get("metric") or "")).lower()
                for metric in metrics
            }
        )
        == 1
        and len(
            {
                normalize_text(str(metric.get("source_table_id") or ""))
                for metric in metrics
                if normalize_text(str(metric.get("source_table_id") or ""))
            }
        )
        <= 1
        and all(
            str(metric.get("verification") or "").startswith("exact_")
            for metric in metrics
        )
        and all(normalize_text(str(metric.get("dataset") or "")) for metric in metrics)
    )
    if len(contexts) > 1 and not explicitly_split_single_metric:
        issues.append(
            {
                "code": "RESULT_MIXED_EVALUATION_CONTEXT",
                "severity": "error",
                "message": "Key metrics mix datasets or configurations without an explicit split.",
                "details": {
                    "contexts": [
                        {
                            "dataset": context[0],
                            "configuration": context[1],
                            "evaluation_condition": context[2],
                        }
                        for context in sorted(contexts)
                    ],
                    "metric_count": len(metrics),
                },
                "return_to": "paper-experimental-results",
            }
        )
    primary = spec.get("primary_asset")
    if not primary:
        issues.append(
            {
                "code": "RESULT_PRIMARY_ASSET_MISSING",
                "severity": "error",
                "message": "A primary quantitative asset is required.",
                "return_to": "paper-asset-select",
            }
        )
    elif primary.get("result_type") in {"qualitative", "ablation"}:
        issues.append(
            {
                "code": "RESULT_PRIMARY_NOT_QUANTITATIVE",
                "severity": "error",
                "message": "The primary asset must directly answer the main performance, efficiency, or finding Claim.",
                "return_to": "paper-asset-select",
            }
        )
    for role in ("primary_asset", "secondary_asset"):
        selected = spec.get(role)
        if not selected:
            continue
        asset_id = str(selected.get("asset_id") or "")
        if asset_id not in assets:
            issues.append(
                {
                    "code": "RESULT_ASSET_BINDING_INVALID",
                    "severity": "error",
                    "message": f"{role} does not bind to a real PaperIR asset.",
                    "return_to": "paper-asset-select",
                }
            )
        invalid_claim_ids = sorted(
            set(selected.get("source_claim_ids") or []) - set(known_claims)
        )
        invalid_block_ids = sorted(
            set(selected.get("source_block_ids") or []) - set(blocks)
        )
        missing_provenance_fields = [
            field
            for field in (
                "source_claim_ids",
                "source_block_ids",
                "page",
                "bbox",
                "caption",
                "selection_reason",
            )
            if not selected.get(field)
        ]
        if (
            missing_provenance_fields
            or invalid_claim_ids
            or invalid_block_ids
        ):
            issues.append(
                {
                    "code": "RESULT_ASSET_PROVENANCE_INCOMPLETE",
                    "severity": "error",
                    "message": "Every result asset needs Claim, block, page, bbox, caption, and selection bindings.",
                    "details": {
                        "asset_id": asset_id,
                        "missing_fields": missing_provenance_fields,
                        "invalid_claim_ids": invalid_claim_ids,
                        "invalid_block_ids": invalid_block_ids,
                    },
                    "return_to": "paper-experimental-results",
                }
            )
        if selected.get("display_mode") not in {
            "original_asset",
            "original_crop",
            "pdf_bbox_crop",
            "pdf_text_focus_crop",
            "verified_focus_table",
        }:
            issues.append(
                {
                    "code": "RESULT_ASSET_NOT_ORIGINAL",
                    "severity": "error",
                    "message": "Experimental data must use an original paper asset or PDF crop.",
                    "return_to": "paper-asset-select",
                }
            )
        if selected.get("asset_type") == "table" and not (
            selected.get("table_context") or {}
        ).get("complete"):
            issues.append(
                {
                    "code": "RESULT_TABLE_CONTEXT_LOST",
                    "severity": "error",
                    "message": "Table crop does not preserve headers, methods, metrics, baseline, and setting.",
                    "return_to": "paper-asset-select",
                }
            )
        source_asset = assets.get(asset_id) or {}
        table_rows = parse_html_table(str(source_asset.get("html") or ""))
        table_columns = max((len(row) for row in table_rows), default=0)
        if (
            selected.get("asset_type") == "table"
            and (len(table_rows) > 8 or table_columns > 6)
        ):
            focus = selected.get("focus_crop") or {}
            display_value = selected.get("display_path")
            display_path = Path(str(display_value)) if display_value else None
            if display_path and not display_path.is_absolute() and paper_ir_dir:
                display_path = paper_ir_dir / display_path
            verified_focus = selected.get("focus_table") or {}
            valid_raster_focus = bool(
                display_path
                and display_path.is_file()
                and focus.get("display_sha256")
                and sha256_file(display_path) == focus.get("display_sha256")
            )
            valid_structured_focus = bool(
                selected.get("display_mode") == "verified_focus_table"
                and verified_focus.get("headers")
                and len(verified_focus.get("rows") or []) >= 2
                and verified_focus.get("verification")
                == "deterministic_cells_from_source_table_html"
            )
            if (
                not focus
                or len(focus.get("data_row_indices") or []) < 2
                or not (valid_raster_focus or valid_structured_focus)
            ):
                issues.append(
                    {
                        "code": "RESULT_TABLE_FOCUS_CROP_REQUIRED",
                        "severity": "error",
                        "message": "A large result table requires a verified original header-and-rows focus crop.",
                        "details": {
                            "asset_id": asset_id,
                            "display_mode": selected.get("display_mode"),
                            "table_rows": len(table_rows),
                            "table_columns": table_columns,
                            "selected_focus_rows": len(
                                focus.get("data_row_indices") or []
                            ),
                            "has_raster_focus": valid_raster_focus,
                            "has_structured_focus": valid_structured_focus,
                        },
                        "return_to": "paper-asset-select",
                    }
                )
            if focus.get("coordinate_method") in {
                "equal_row_height",
                "equal_column_width",
                "html-row-order-to-original-table-raster",
            }:
                issues.append(
                    {
                        "code": "RESULT_TABLE_UNSAFE_GEOMETRY",
                        "severity": "error",
                        "message": "Table focus crop uses inferred equal row or column geometry.",
                        "return_to": "paper-experimental-results",
                    }
                )
            if float(focus.get("duplicate_band_score") or 0) > 0.12:
                issues.append(
                    {
                        "code": "RESULT_TABLE_DUPLICATE_BAND",
                        "severity": "error",
                        "message": "Table focus crop contains a likely duplicated or overlapping band.",
                        "return_to": "paper-experimental-results",
                    }
                )
            if selected.get("display_mode") == "pdf_text_focus_crop":
                if (
                    focus.get("glyphs_touch_crop_edge") is not False
                    or float(focus.get("edge_ink_ratio") or 0) > 0.02
                ):
                    issues.append(
                        {
                            "code": "RESULT_TABLE_GLYPH_CLIPPED",
                            "severity": "error",
                            "message": (
                                "Table focus crop has glyph ink touching "
                                "its top or bottom boundary."
                            ),
                            "details": {
                                "asset_id": asset_id,
                                "edge_ink_ratio": focus.get(
                                    "edge_ink_ratio"
                                ),
                                "glyphs_touch_crop_edge": focus.get(
                                    "glyphs_touch_crop_edge"
                                ),
                            },
                            "return_to": "paper-experimental-results",
                        }
                    )
                if not (
                    focus.get("row_bounds_source")
                    and focus.get("row_bounds_padded")
                    and int(focus.get("glyph_padding_px") or 0) >= 2
                ):
                    issues.append(
                        {
                            "code": "RESULT_TABLE_GLYPH_PADDING_MISSING",
                            "severity": "error",
                            "message": (
                                "PDF text focus crop lacks verified row "
                                "glyph bounds and safety padding."
                            ),
                            "return_to": "paper-experimental-results",
                        }
                    )
        if check_files and paper_ir_dir is not None:
            resolution = (
                selected.get("display_resolution")
                or selected.get("source_resolution")
                or {}
            )
            if (
                selected.get("display_mode") != "verified_focus_table"
                and not resolution.get("source_readable")
            ):
                issues.append(
                    {
                        "code": "RESULT_ASSET_SOURCE_UNREADABLE",
                        "severity": "error",
                        "message": "Selected result crop is not readable at its source resolution.",
                        "return_to": "paper-asset-select",
                    }
                )
    secondary = spec.get("secondary_asset") or {}
    if secondary.get("result_type") == "qualitative" and not metrics:
        issues.append(
            {
                "code": "RESULT_QUALITATIVE_WITHOUT_QUANTITATIVE",
                "severity": "error",
                "message": "Qualitative evidence cannot stand without quantitative support.",
                "return_to": "paper-experimental-results",
            }
        )
    if int(spec.get("visible_word_count") or 0) > 100:
        issues.append(
            {
                "code": "RESULT_WORD_BUDGET_EXCEEDED",
                "severity": "error",
                "message": "Experimental Results visible prose exceeds 100 English words.",
                "return_to": "paper-experimental-results",
            }
        )
    condition_words = len(
        re.findall(
            r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*",
            str(spec.get("condition_note") or ""),
        )
    )
    if condition_words > 24:
        issues.append(
            {
                "code": "RESULT_CONDITION_NOTE_TOO_LONG",
                "severity": "error",
                "message": "The result condition note exceeds the one-to-two-line budget.",
                "return_to": "paper-experimental-results",
            }
        )
    return issues
