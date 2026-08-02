from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .common import jaccard, normalize_text, read_json, token_set, write_json

RESULT_TERMS = (
    "result",
    "comparison",
    "performance",
    "accuracy",
    "quantitative",
    "qualitative",
    "prediction",
    "segmentation comparison",
    "roc",
    "confusion matrix",
    "ablation",
    "sensitivity",
    "benchmark",
    "drops",
    "recovers",
    "improves",
    "sparsity",
    "parameter reduction",
    "effectiveness",
    "outperforms",
    "compared",
)
RESULT_SECTION_TERMS = (
    "result",
    "experiment",
    "evaluation",
    "analysis",
    "ablation",
    "effectiveness",
    "visualization",
)
OVERVIEW_TERMS = (
    "overview",
    "overall",
    "complete pipeline",
    "framework",
    "architecture",
    "workflow",
    "proposed method",
)
METHOD_VISUAL_TERMS = (
    "module",
    "mechanism",
    "architecture",
    "framework",
    "pipeline",
    "workflow",
    "information flow",
    "encoder",
    "decoder",
    "first",
    "attention",
    "fusion",
    "pruning",
)
DATASET_TERMS = ("dataset sample", "data sample", "cohort", "example images")
MODULE_MATCH_THRESHOLD = 0.25
GENERIC_MODULE_TERMS = {
    "about",
    "after",
    "also",
    "and",
    "architecture",
    "attention",
    "block",
    "component",
    "design",
    "encoder",
    "decoder",
    "framework",
    "from",
    "fusion",
    "group",
    "head",
    "here",
    "into",
    "layer",
    "mechanism",
    "method",
    "model",
    "module",
    "network",
    "overview",
    "pipeline",
    "principle",
    "proposed",
    "represents",
    "selective",
    "stage",
    "structure",
    "system",
    "the",
    "then",
    "through",
    "transformer",
    "unit",
    "using",
    "with",
    "which",
    "where",
    "based",
    "used",
}
SYSTEM_LEVEL_TERMS = {
    "architecture",
    "framework",
    "method",
    "model",
    "network",
    "pipeline",
    "system",
    "workflow",
}
LOCAL_COMPONENT_TERMS = {
    "attention",
    "block",
    "branch",
    "convolution",
    "conv",
    "decoder",
    "encoder",
    "fusion",
    "head",
    "layer",
    "mechanism",
    "module",
    "operator",
    "pooling",
    "router",
    "stage",
    "transform",
    "unit",
}
EXPLICIT_RESULT_CAPTION_TERMS = (
    "experimental result",
    "test result",
    "result plot",
    "quantitative result",
    "qualitative result",
    "performance comparison",
    "visual comparison",
    "prediction comparison",
    "segmentation comparison",
    "density map",
    "confusion matrix",
    "roc curve",
    "training curve",
    "metric curve",
    "ablation",
)
MECHANISM_ANALYSIS_TERMS = (
    "attention map",
    "attention maps",
    "attention heatmap",
    "attention heatmaps",
    "activation map",
    "activation maps",
    "branch feature",
    "branch features",
    "feature map",
    "feature maps",
    "feature response",
    "feature responses",
    "intermediate feature",
    "intermediate features",
    "response map",
    "response maps",
)
SPACED_FIGURE_RE = re.compile(
    r"\bF\s+I\s+G\s+U\s+R\s+E\b",
    re.I,
)
PROPOSED_SYSTEM_DESCRIPTION_RE = re.compile(
    r"\b(?:the\s+)?proposed\s+[A-Za-z][A-Za-z0-9-]*\s+"
    r"(?:adopts|uses|employs|follows|has)\s+(?:an?\s+)?"
    r"(?:encoder[-\s]decoder|network|framework|architecture|pipeline)\b",
    re.I,
)
DETAILS_OF_METHOD_COMPONENT_RE = re.compile(
    r"\bdetails?\s+of\s+(?:the\s+)?"
    r".{1,100}\b(?:attention|block|module|encoder|decoder|fusion|"
    r"convolution|transform)\b",
    re.I,
)
VARIANT_MARKER_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9][A-Za-z0-9-]*\b"
)
PROPOSED_METHOD_DIAGRAM_RE = re.compile(
    r"\b(?:diagram|architecture|framework|pipeline|overview)\s+of\s+"
    r"(?:the\s+)?proposed\b.{0,100}\b"
    r"(?:method|network|model|framework|architecture)\b",
    re.I,
)
MODULE_DIAGRAM_RE = re.compile(
    r"\bdiagram\s+of\s+(?!the\s+proposed\b)[A-Za-z][A-Za-z0-9_-]{1,24}\b",
    re.I,
)
DETAILED_METHOD_STRUCTURE_RE = re.compile(
    r"\b(?:detailed\s+)?structure\s+of\s+(?:the\s+)?(?:proposed\s+)?"
    r".{0,100}\b(?:module|fusion|attention|encoder|decoder|mechanism)\b",
    re.I,
)
TOP_LEVEL_HEADING_RE = re.compile(
    r"^\s*(?:\d+|[IVX][IVXLCDM]*)[.)]\s+\S",
    re.I,
)
TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "via",
    "with",
}
VISUAL_RESULT_METRIC_TERMS = {
    "accuracy",
    "acc",
    "auc",
    "dice",
    "dsc",
    "f1",
    "flops",
    "gpu hours",
    "gpu hour",
    "hd95",
    "iou",
    "jaccard",
    "latency",
    "loss",
    "mae",
    "map",
    "memory",
    "miou",
    "params",
    "parameters",
    "psnr",
    "rmse",
    "runtime",
    "ssim",
    "throughput",
    "top-1",
    "top-5",
    "training time",
}
VISUAL_RESULT_COMPARISON_TERMS = {
    "baseline",
    "dense",
    "ground truth",
    "ours",
    "proposed",
    "sota",
}
VISUAL_METHOD_CONTENT_TERMS = {
    "attention",
    "block",
    "branch",
    "decoder",
    "encoder",
    "expert",
    "feature",
    "ffn",
    "fusion",
    "input",
    "layer",
    "memory bank",
    "module",
    "output",
    "router",
    "stage",
    "token",
}
METHOD_ROLES = {
    "method_overview",
    "method_module",
    "mechanism",
    "mechanism_analysis",
}
RESULT_ROLES = {
    "ablation",
    "dataset_example",
    "experimental_result",
    "qualitative_result",
}


def _pdf_rect(
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


def _pdf_text_in_asset_bbox(
    source_pdf: Path,
    asset: dict[str, Any],
) -> str:
    try:
        import pypdfium2
    except ImportError:
        return ""
    bbox = asset.get("bbox") or []
    page_number = int(asset.get("page") or 0)
    if not source_pdf.is_file() or page_number <= 0 or len(bbox) != 4:
        return ""
    document: Any | None = None
    page: Any | None = None
    text_page: Any | None = None
    try:
        document = pypdfium2.PdfDocument(str(source_pdf))
        page_index = page_number - 1
        if page_index < 0 or page_index >= len(document):
            return ""
        page = document[page_index]
        rect = _pdf_rect(
            *[float(value) for value in page.get_size()],
            [float(value) for value in bbox],
        )
        if not rect:
            return ""
        text_page = page.get_textpage()
        return normalize_text(text_page.get_text_bounded(*rect))
    except Exception:
        return ""
    finally:
        if text_page is not None:
            text_page.close()
        if page is not None:
            page.close()
        if document is not None:
            document.close()


def _analyze_visual_text(value: str) -> dict[str, Any]:
    text = normalize_text(value)
    lowered = text.lower()
    metric_terms = sorted(
        term for term in VISUAL_RESULT_METRIC_TERMS if term in lowered
    )
    comparison_terms = sorted(
        term for term in VISUAL_RESULT_COMPARISON_TERMS if term in lowered
    )
    architecture_terms = sorted(
        term for term in VISUAL_METHOD_CONTENT_TERMS if term in lowered
    )
    percent_count = len(re.findall(r"\d+(?:\.\d+)?\s*%", text))
    numeric_token_count = len(
        re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?![A-Za-z])", text)
    )
    result_score = (
        min(6, len(metric_terms)) * 2
        + min(4, percent_count) * 2
        + min(4, len(comparison_terms))
        + (2 if numeric_token_count >= 5 else 0)
    )
    method_score = min(8, len(architecture_terms)) * 1.5
    if result_score >= 8 and result_score >= method_score + 2:
        content_role = "experimental_result"
        confidence = min(0.99, 0.72 + result_score * 0.025)
    elif method_score >= 6 and method_score >= result_score + 2:
        content_role = "method_diagram"
        confidence = min(0.96, 0.7 + method_score * 0.025)
    else:
        content_role = "unknown"
        confidence = 0.5
    return {
        "extraction_method": "pdf_text_bbox" if text else "unavailable",
        "text_sample": text[:400],
        "content_role": content_role,
        "confidence": round(confidence, 3),
        "result_score": round(result_score, 3),
        "method_score": round(method_score, 3),
        "metric_terms": metric_terms,
        "comparison_terms": comparison_terms,
        "architecture_terms": architecture_terms,
        "percent_count": percent_count,
        "numeric_token_count": numeric_token_count,
    }


def _visual_content_signals(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
) -> dict[str, Any]:
    precomputed = asset.get("visual_content_signals")
    if isinstance(precomputed, dict):
        return dict(precomputed)
    source_value = (paper_ir.get("provenance") or {}).get("source_path")
    source_pdf = Path(str(source_value)) if source_value else None
    text = (
        _pdf_text_in_asset_bbox(source_pdf, asset)
        if source_pdf is not None
        else ""
    )
    return _analyze_visual_text(text)


def _caption_content_consistency(
    role: str,
    visual_signals: dict[str, Any],
) -> tuple[bool, list[str]]:
    content_role = str(visual_signals.get("content_role") or "unknown")
    confidence = float(visual_signals.get("confidence") or 0)
    if (
        role in METHOD_ROLES
        and content_role == "experimental_result"
        and confidence >= 0.82
    ):
        return False, [
            "image-bbox text contains strong metric/comparison evidence "
            "that conflicts with the Method caption or reference"
        ]
    if (
        role in RESULT_ROLES
        and content_role == "method_diagram"
        and confidence >= 0.88
    ):
        return False, [
            "image-bbox text describes a method diagram but the caption "
            "classifies the asset as a result"
        ]
    return True, []


def _semantic_tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", value)
        if token.lower() not in GENERIC_MODULE_TERMS
    }


def _normalize_alias(value: str) -> str:
    alias = re.sub(r"[^A-Za-z0-9]", "", value).lower()
    if len(alias) >= 5 and alias.endswith("s"):
        alias = alias[:-1]
    return alias


def _explicit_aliases(value: str) -> set[str]:
    aliases = {
        _normalize_alias(token)
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{1,}\b", value)
        if sum(character.isupper() for character in token) >= 2
    }
    return {
        alias
        for alias in aliases
        if len(alias) >= 2 and alias not in {"fig", "figure", "table"}
    }


def _node_aliases(node: dict[str, Any]) -> set[str]:
    name = str(node.get("name") or node.get("section_title") or "")
    all_text = " ".join(
        str(node.get(key) or "")
        for key in ("name", "purpose", "innovation", "section_title")
    )
    source_text = " ".join(
        str(source.get("quote") or "")
        for source in node.get("sources", [])
        if isinstance(source, dict)
    )
    all_text = f"{all_text} {source_text}"
    aliases = _explicit_aliases(all_text)
    acronym = _normalize_alias(_node_acronym(node))
    if len(acronym) >= 2:
        aliases.add(acronym)
    # Parenthetical names in prose often connect a block to its inner
    # mechanism, e.g. KSFTB -> Kernel Selective Fusion Attention (KSFA).
    aliases.update(
        _normalize_alias(match)
        for match in re.findall(r"\(([A-Z][A-Z0-9-]{1,})\)", all_text)
    )
    return {alias for alias in aliases if len(alias) >= 2} | _explicit_aliases(name)


def _caption_lead(caption: str) -> str:
    caption = SPACED_FIGURE_RE.sub("FIGURE", caption)
    stripped = re.sub(r"^\s*(?:fig(?:ure)?\.?\s*\d+[A-Za-z]?\s*[:.-]?\s*)", "", caption, flags=re.I)
    return re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)[0].lower()


def _system_aliases(paper_ir: dict[str, Any]) -> set[str]:
    title = normalize_text(str(paper_ir.get("metadata", {}).get("title") or ""))
    aliases = _explicit_aliases(title)
    aliases.update(
        _normalize_alias(token)
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", title)
        if any(character.isupper() for character in token[1:])
    )
    acronym = "".join(
        token[0]
        for token in re.findall(r"[A-Za-z]+", title)
        if token.lower() not in TITLE_STOPWORDS
    )
    if len(acronym) >= 3:
        aliases.add(_normalize_alias(acronym))
    return {alias for alias in aliases if len(alias) >= 3}


def _proposed_visual_scope(
    caption: str,
    system_aliases: set[str] | None = None,
) -> str | None:
    lead = _caption_lead(caption)
    if not re.search(
        r"\b(?:illustration|diagram|overview|architecture|framework|pipeline)"
        r"\s+of\s+(?:the\s+)?proposed\b",
        lead,
        re.I,
    ):
        return None
    lead_tokens = set(re.findall(r"[a-z][a-z0-9-]*", lead))
    # "Architecture" is used for both whole networks and local modules.
    # An explicit local noun is therefore stronger than the generic diagram
    # form; the first caption sentence of a real overview normally names the
    # network/model and does not contain "module" or "block".
    normalized_lead = _normalize_alias(lead)
    if any(alias in normalized_lead for alias in (system_aliases or set())):
        return "system"
    if re.search(
        r"\b(?:architecture|framework|overview|pipeline)\s+of\s+"
        r"(?:the\s+)?proposed\s+[A-Za-z][A-Za-z0-9-]*"
        r"(?:net|network|model)\b",
        lead,
        re.I,
    ):
        return "system"
    if lead_tokens & LOCAL_COMPONENT_TERMS:
        return "component"
    if lead_tokens & SYSTEM_LEVEL_TERMS:
        return "system"
    # Unknown proposed structures are safer as local components. A complete
    # system requires a system noun or a paper-title alias.
    return "component"


def _subfigure_semantics(caption: str) -> list[dict[str, str]]:
    stripped = re.sub(
        r"^\s*(?:fig(?:ure)?\.?\s*\d+[A-Za-z]?\s*[:.-]?\s*)",
        "",
        normalize_text(caption),
        flags=re.I,
    )
    matches = list(re.finditer(r"\(([a-z])\)\s*", stripped, re.I))
    results: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
        text = stripped[match.end() : end].strip(" ;,.:-")
        ownership = (
            "proposed"
            if re.search(r"\b(?:our|ours|proposed|novel)\b", text, re.I)
            else "reference"
        )
        results.append(
            {
                "label": match.group(1).lower(),
                "text": text,
                "ownership": ownership,
            }
        )
    return results


def _contains_term(value: str, term: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
            value,
            re.I,
        )
    )


def _context_has_result_evidence(value: str) -> bool:
    hits = {
        term
        for term in RESULT_TERMS
        if _contains_term(value, term)
    }
    numeric_outcome = bool(
        re.search(
            r"\b(?:accuracy|auc|dice|iou|mae|mse|psnr|ssim)\b"
            r".{0,30}\d+(?:\.\d+)?%?",
            value,
            re.I,
        )
    )
    return numeric_outcome or len(hits) >= 2


def _caption_has_measured_comparison(value: str) -> bool:
    return bool(
        re.search(r"\b(?:comparison|compared|versus|vs\.?)\b", value, re.I)
        and re.search(
            r"\b(?:f1|dice|dsc|iou|auc|accuracy|acc|mae|mse|rmse|psnr|"
            r"ssim|flops?|macs?|parameters?|params?|latency|runtime|"
            r"complexity|score|performance)\b",
            value,
            re.I,
        )
    )


def _caption_has_qualitative_comparison(value: str) -> bool:
    lowered = normalize_text(value).lower()
    explicit_comparison = any(
        term in lowered
        for term in (
            "error map",
            "failure case",
            "qualitative comparison",
            "visual comparison",
            "visual quality comparison",
        )
    )
    restored_output_comparison = bool(
        re.search(
            r"\b(?:ours|our result|proposed|baseline|restored image|prediction)\b",
            lowered,
        )
        and re.search(
            r"\b(?:ground truth|reference image|error|difference)\b",
            lowered,
        )
    )
    multi_method_panels = bool(
        re.search(r"\b(?:ours|proposed)\b", lowered)
        and re.search(
            r"\b(?:baseline|existing method|state-of-the-art|ground truth)\b",
            lowered,
        )
    )
    return explicit_comparison or restored_output_comparison or multi_method_panels


def _has_mechanism_analysis_signal(value: str) -> bool:
    lowered = normalize_text(value).lower()
    return any(term in lowered for term in MECHANISM_ANALYSIS_TERMS)


def _has_method_operation_signal(value: str) -> bool:
    lowered = normalize_text(value).lower()
    operation_terms = (
        "concatenate",
        "concatenated",
        "convolution",
        "extract",
        "extracted",
        "feed",
        "fused",
        "fusion",
        "input feature",
        "multiplied",
        "multiply",
        "output feature",
        "processed",
        "sigmoid",
        "subtract",
        "transformed",
    )
    return any(term in lowered for term in operation_terms)


def _method_reference_strength(
    referenced_node_ids: set[str],
    section: str,
) -> str:
    if not referenced_node_ids:
        return "none"
    if any(term in section for term in RESULT_SECTION_TERMS):
        return "weak"
    return "strong"


def _is_dataset_example_caption(value: str) -> bool:
    image_evidence = bool(
        re.search(
            r"\b(?:sample|example|original|input|raw)\s+images?\b",
            value,
            re.I,
        )
    )
    dataset_evidence = bool(
        re.search(
            r"\b(?:dataset|datasets|cohort|fov|field of view|labels?)\b",
            value,
            re.I,
        )
    )
    return image_evidence and dataset_evidence


def _substantive_caption(value: str) -> bool:
    value = re.sub(
        r"^\s*fig(?:ure)?\.?\s*\d+[A-Za-z]?\s*[.:]?\s*",
        "",
        normalize_text(value),
        flags=re.I,
    )
    value = re.sub(r"^\s*\([a-z]\)\s*$", "", value, flags=re.I)
    return len(re.findall(r"[A-Za-z]{2,}", value)) >= 3


def _shares_split_figure_row(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    if left.get("page") != right.get("page"):
        return False
    left_box = left.get("bbox")
    right_box = right.get("bbox")
    if not (
        isinstance(left_box, list)
        and isinstance(right_box, list)
        and len(left_box) == 4
        and len(right_box) == 4
    ):
        return False
    left_height = max(1.0, float(left_box[3]) - float(left_box[1]))
    right_height = max(1.0, float(right_box[3]) - float(right_box[1]))
    vertical_overlap = max(
        0.0,
        min(float(left_box[3]), float(right_box[3]))
        - max(float(left_box[1]), float(right_box[1])),
    )
    horizontal_gap = max(
        0.0,
        max(float(left_box[0]), float(right_box[0]))
        - min(float(left_box[2]), float(right_box[2])),
    )
    return (
        vertical_overlap / min(left_height, right_height) >= 0.7
        and horizontal_gap <= 40.0
    )


def _inherited_split_figure_role(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
    *,
    system_aliases: set[str],
    title_tokens: set[str],
) -> tuple[str, float, list[str]] | None:
    if _substantive_caption(str(asset.get("caption") or "")):
        return None
    source_index = asset.get("source_item_index")
    for peer in paper_ir.get("figures", []):
        if peer is asset or not _shares_split_figure_row(asset, peer):
            continue
        peer_index = peer.get("source_item_index")
        if (
            isinstance(source_index, int)
            and isinstance(peer_index, int)
            and abs(source_index - peer_index) > 2
        ):
            continue
        peer_role, peer_confidence, _ = _role(
            peer,
            system_aliases=system_aliases,
            title_tokens=title_tokens,
            referenced_node_ids=set(),
        )
        if peer_role in {
            "ablation",
            "dataset_example",
            "experimental_result",
            "qualitative_result",
        }:
            return (
                peer_role,
                min(0.94, peer_confidence),
                [
                    "captionless panel inherits non-Method role from "
                    f"adjacent split figure {peer.get('id')}"
                ],
            )
    return None


def _combined(asset: dict[str, Any]) -> str:
    cited = " ".join(str(value) for value in asset.get("cited_by", []))
    return normalize_text(
        " ".join(
            str(asset.get(key) or "")
            for key in (
                "caption",
                "context_before",
                "context_after",
                "section_id",
            )
        )
        + " "
        + cited
    ).lower()


def _role(
    asset: dict[str, Any],
    *,
    system_aliases: set[str] | None = None,
    title_tokens: set[str] | None = None,
    referenced_node_ids: set[str] | None = None,
) -> tuple[str, float, list[str]]:
    text = _combined(asset)
    caption = SPACED_FIGURE_RE.sub(
        "FIGURE",
        normalize_text(str(asset.get("caption") or "")),
    ).lower()
    section = str(asset.get("section_id") or "").lower()
    referenced_node_ids = referenced_node_ids or set()
    reference_strength = _method_reference_strength(referenced_node_ids, section)
    reasons: list[str] = []

    if "ablation" in caption or "ablation" in section:
        return "ablation", 0.96, ["caption or section identifies an ablation"]
    if any(
        term in caption
        for term in ("qualitative", "visual comparison", "prediction comparison")
    ) or _caption_has_qualitative_comparison(caption):
        return "qualitative_result", 0.96, [
            "caption explicitly identifies a qualitative or error comparison"
        ]
    if (
        any(term in caption for term in EXPLICIT_RESULT_CAPTION_TERMS)
        or _caption_has_measured_comparison(caption)
    ):
        return "experimental_result", 0.96, [
            "caption explicitly identifies an experimental result"
        ]
    if _is_dataset_example_caption(caption) or any(
        term in caption for term in DATASET_TERMS
    ):
        return "dataset_example", 0.9, ["caption identifies dataset examples"]
    if PROPOSED_SYSTEM_DESCRIPTION_RE.search(caption):
        return "method_overview", 0.97, [
            "caption directly describes the proposed complete system"
        ]
    if DETAILS_OF_METHOD_COMPONENT_RE.search(caption):
        return "method_module", 0.95, [
            "caption directly describes details of a method component"
        ]

    proposed_scope = _proposed_visual_scope(caption, system_aliases)
    proposed_lead_tokens = set(
        re.findall(r"[a-z][a-z0-9-]*", _caption_lead(caption))
    )
    title_overlap = (title_tokens or set()) & token_set(caption)
    if (
        proposed_scope == "component"
        and not proposed_lead_tokens.intersection(LOCAL_COMPONENT_TERMS)
        and len(title_overlap) >= 2
    ):
        proposed_scope = "system"
    if proposed_scope == "component":
        return "method_module", 0.97, [
            "caption identifies a proposed local component rather than the complete system"
        ]
    if PROPOSED_METHOD_DIAGRAM_RE.search(caption):
        return "method_overview", 0.97, [
            "caption identifies the proposed complete method"
        ]
    if proposed_scope == "system":
        return "method_overview", 0.97, [
            "caption identifies the proposed complete system"
        ]

    subfigures = _subfigure_semantics(caption)
    proposed_subfigures = [
        item for item in subfigures if item["ownership"] == "proposed"
    ]
    if proposed_subfigures and any(
        term in caption
        for term in (
            "method",
            "module",
            "fusion",
            "attention",
            "convolution",
            "architecture",
            "framework",
            "baseline",
        )
    ):
        return "method_module", 0.96, [
            "caption identifies proposed method subfigure(s): "
            + ", ".join(item["label"] for item in proposed_subfigures)
        ]

    mechanism_analysis = _has_mechanism_analysis_signal(caption)
    if (
        mechanism_analysis
        and reference_strength == "strong"
        and not _caption_has_measured_comparison(caption)
        and not _caption_has_qualitative_comparison(caption)
    ):
        return "mechanism_analysis", 0.92, [
            "Method text explicitly references an internal feature or attention visualization"
        ]
    if (
        mechanism_analysis
        and _has_method_operation_signal(caption)
        and not _caption_has_measured_comparison(caption)
        and not _caption_has_qualitative_comparison(caption)
    ):
        return "mechanism_analysis", 0.9, [
            "caption explains how an internal method response is produced"
        ]
    if (
        mechanism_analysis
        and any(
            term in section
            for term in ("method", "approach", "architecture", "module", "network")
        )
        and not _context_has_result_evidence(caption)
    ):
        return "mechanism_analysis", 0.86, [
            "internal feature visualization belongs to a Method section without measured result evidence"
        ]
    if mechanism_analysis and any(
        term in section for term in RESULT_SECTION_TERMS
    ):
        return "experimental_result", 0.9, [
            "internal-response visualization is presented as result analysis"
        ]

    if any(term in caption for term in OVERVIEW_TERMS):
        return "method_overview", 0.94, [
            "caption explicitly identifies a complete method view"
        ]
    # Extraction may attach a method figure to the next major heading. A
    # caption that explicitly describes a module structure is stronger
    # evidence than that neighboring section label.
    if DETAILED_METHOD_STRUCTURE_RE.search(caption):
        return "method_module", 0.93, [
            "caption identifies a detailed method module"
        ]
    if reference_strength == "strong":
        return "method_module", 0.95, [
            "method graph contains an explicit figure reference"
        ]
    if any(term in section for term in RESULT_SECTION_TERMS) and (
        _context_has_result_evidence(text)
        or len(re.findall(r"\d+(?:\.\d+)?%?", caption)) >= 3
    ):
        return "experimental_result", 0.94, [
            "result section and result evidence agree"
        ]
    if not caption and any(
        term in section
        for term in ("ablation", "effectiveness", "visualization")
    ):
        return "experimental_result", 0.9, [
            "captionless figure belongs to an explicit result-analysis section"
        ]
    if _context_has_result_evidence(text):
        return "experimental_result", 0.86, [
            "caption or context contains multiple result signals"
        ]
    if any(term in text for term in DATASET_TERMS):
        return "dataset_example", 0.86, ["caption identifies dataset examples"]
    if MODULE_DIAGRAM_RE.search(caption):
        return "method_module", 0.9, ["caption identifies a named method module"]
    if any(term in text for term in OVERVIEW_TERMS) and not caption:
        return "method_overview", 0.91, [
            "caption or context identifies a complete method view"
        ]
    if "mechanism" in text or "principle" in text:
        return "mechanism", 0.8, ["caption identifies a method mechanism"]
    if any(term in text for term in METHOD_VISUAL_TERMS):
        return "method_module", 0.78, [
            "caption or context contains method-structure language"
        ]
    return "other", 0.5, reasons


def classify_figure_role(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
    *,
    referenced_node_ids: set[str] | None = None,
    visual_content_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title_tokens = {
        token
        for token in token_set(
            str(paper_ir.get("metadata", {}).get("title") or "")
        )
        if token not in TITLE_STOPWORDS
    }
    system_aliases = _system_aliases(paper_ir)
    inherited_role = _inherited_split_figure_role(
        asset,
        paper_ir,
        system_aliases=system_aliases,
        title_tokens=title_tokens,
    )
    if inherited_role:
        role, confidence, reasons = inherited_role
    else:
        role, confidence, reasons = _role(
            asset,
            system_aliases=system_aliases,
            title_tokens=title_tokens,
            referenced_node_ids=referenced_node_ids,
        )
    visual_signals = (
        dict(visual_content_signals)
        if visual_content_signals is not None
        else _visual_content_signals(asset, paper_ir)
    )
    caption_content_consistent, mismatch_reasons = (
        _caption_content_consistency(role, visual_signals)
    )
    if (
        not caption_content_consistent
        and str(visual_signals.get("content_role"))
        == "experimental_result"
        and role in METHOD_ROLES
    ):
        role = "experimental_result"
        confidence = max(
            confidence,
            float(visual_signals.get("confidence") or 0),
        )
        reasons = [
            *mismatch_reasons,
            "strong visual-content evidence overrides noisy Method metadata",
        ]
    subfigures = _subfigure_semantics(
        normalize_text(str(asset.get("caption") or ""))
    )
    caption_text = normalize_text(str(asset.get("caption") or ""))
    section = str(asset.get("section_id") or "").lower()
    reference_strength = _method_reference_strength(
        referenced_node_ids or set(),
        section,
    )
    if role == "mechanism_analysis":
        poster_eligibility = [
            "method_details",
            "experimental_results_secondary",
        ]
        preferred_zone = "method_details"
    elif role in METHOD_ROLES:
        preferred_zone = (
            "method_overview"
            if role == "method_overview"
            else "method_details"
        )
        poster_eligibility = [preferred_zone]
    elif role in RESULT_ROLES:
        poster_eligibility = ["experimental_results"]
        preferred_zone = "experimental_results"
    else:
        poster_eligibility = []
        preferred_zone = None
    return {
        "role": role,
        "confidence": confidence,
        "reasons": reasons,
        "reference_strength": reference_strength,
        "poster_eligibility": poster_eligibility,
        "preferred_zone": preferred_zone,
        "subfigure_semantics": subfigures,
        "focus_subfigure_labels": [
            item["label"]
            for item in subfigures
            if item["ownership"] == "proposed"
        ],
        "visual_content_signals": visual_signals,
        "caption_content_consistent": caption_content_consistent,
        "caption_content_mismatch_reasons": mismatch_reasons,
        "evidence_ledger": {
            "explicit_method_reference": reference_strength == "strong",
            "mechanism_analysis_signal": _has_mechanism_analysis_signal(
                caption_text
            ),
            "method_operation_signal": _has_method_operation_signal(
                caption_text
            ),
            "measured_comparison": _caption_has_measured_comparison(
                caption_text
            ),
            "qualitative_comparison": _caption_has_qualitative_comparison(
                caption_text
            ),
            "visual_content_available": (
                visual_signals.get("extraction_method") != "unavailable"
            ),
        },
    }


def _node_acronym(node: dict[str, Any]) -> str:
    label = str(node.get("name") or node.get("section_title") or "")
    label = re.sub(r"^\s*[A-Z0-9]+[.)]\s*", "", label, flags=re.I)
    words = re.findall(r"[A-Za-z]+", label)
    return "".join(word[0] for word in words if len(word) > 1).lower()


def _node_match(
    asset_text: str,
    node: dict[str, Any],
    caption: str = "",
    *,
    node_aliases: set[str] | None = None,
    unique_aliases: set[str] | None = None,
    distinctive_tokens: set[str] | None = None,
    allow_context_distinctive: bool = False,
) -> tuple[float, list[str], str, list[str]]:
    node_text = " ".join(
        str(node.get(key) or "")
        for key in ("name", "purpose", "innovation", "section_title")
    )
    node_specific = _semantic_tokens(node_text)
    asset_specific = _semantic_tokens(asset_text)
    caption_specific = _semantic_tokens(caption)
    score = jaccard(
        " ".join(sorted(asset_specific)),
        " ".join(sorted(node_specific)),
    )
    reasons: list[str] = []
    evidence: list[str] = []
    aliases = node_aliases or _node_aliases(node)
    caption_aliases = _explicit_aliases(caption)
    alias_hits = aliases & caption_aliases
    unique_hits = alias_hits & (unique_aliases or set())
    if unique_hits:
        score += 0.95
        evidence.extend(f"alias:{alias}" for alias in sorted(unique_hits))
        reasons.append(
            "caption uniquely matches module alias: " + ", ".join(sorted(unique_hits))
        )
        match_kind = "exact_unique_alias"
    elif alias_hits:
        score += 0.75
        evidence.extend(f"alias:{alias}" for alias in sorted(alias_hits))
        reasons.append("caption matches module alias: " + ", ".join(sorted(alias_hits)))
        match_kind = "exact_alias"
    else:
        match_kind = "contextual_overlap"

    distinctive_source = (
        caption_specific | asset_specific
        if allow_context_distinctive
        else caption_specific
    )
    distinctive_hits = distinctive_source & (distinctive_tokens or set())
    if distinctive_hits:
        score += min(0.7, len(distinctive_hits) * 0.35)
        prefix = "context_term" if allow_context_distinctive else "term"
        evidence.extend(
            f"{prefix}:{term}" for term in sorted(distinctive_hits)
        )
        reasons.append(
            (
                "caption or context contains module-distinctive terms: "
                if allow_context_distinctive
                else "caption contains module-distinctive terms: "
            )
            + ", ".join(sorted(distinctive_hits))
        )
        if match_kind == "contextual_overlap":
            match_kind = "distinctive_terms"

    shared_specific = caption_specific & node_specific
    if shared_specific:
        score += min(0.36, len(shared_specific) * 0.12)
        reasons.append(
            "caption shares specific module terms: "
            + ", ".join(sorted(shared_specific))
        )
    section_id = str(node.get("section_id") or "").lower()
    if section_id and section_id in asset_text:
        score += 0.05
        reasons.append("same method section")
    return min(1.0, score), reasons, match_kind, evidence


def _parent_describes_node(
    parent: dict[str, Any],
    child: dict[str, Any],
    child_aliases: set[str],
) -> tuple[bool, list[str]]:
    parent_text = normalize_text(
        " ".join(
            str(parent.get(key) or "")
            for key in ("purpose", "innovation")
        )
    )
    normalized_parent = _normalize_alias(parent_text)
    matched_aliases = sorted(
        alias
        for alias in child_aliases
        if len(alias) >= 3 and alias in normalized_parent
    )
    if matched_aliases:
        return True, [f"parent_text_alias:{alias}" for alias in matched_aliases]
    child_tokens = _semantic_tokens(str(child.get("name") or ""))
    parent_tokens = _semantic_tokens(parent_text)
    overlap = child_tokens & parent_tokens
    if len(child_tokens) >= 2 and len(overlap) / len(child_tokens) >= 0.6:
        return True, [f"parent_text_term:{term}" for term in sorted(overlap)]
    return False, []


def _variant_markers(value: str) -> set[str]:
    return {
        marker.lower()
        for marker in VARIANT_MARKER_RE.findall(value)
    }


def _variant_compatible(caption: str, node: dict[str, Any]) -> bool:
    caption_markers = _variant_markers(caption)
    if not caption_markers:
        return True
    caption_families = {marker.split("-", 1)[0] for marker in caption_markers}
    node_markers = _variant_markers(
        " ".join(
            str(node.get(key) or "")
            for key in ("name", "section_title", "purpose", "innovation")
        )
    )
    sibling_markers = {
        marker
        for marker in node_markers
        if marker.split("-", 1)[0] in caption_families
    }
    return not sibling_markers or bool(sibling_markers & caption_markers)


def _primary_evidence_text(paper_ir: dict[str, Any]) -> str:
    current_major = ""
    evidence: list[str] = []
    for block in paper_ir.get("blocks", []):
        text = normalize_text(str(block.get("text") or ""))
        if block.get("type") == "heading" and TOP_LEVEL_HEADING_RE.match(text):
            current_major = text.lower()
            continue
        if block.get("type") in {"title", "heading", "caption"} or not text:
            continue
        section = (
            f"{block.get('section_title') or ''} "
            f"{block.get('section_id') or ''} "
            f"{current_major}"
        ).lower()
        if any(term in section for term in ("related work", "background", "ablation")):
            continue
        if (
            any(
                term in section
                for term in (
                    "abstract",
                    "introduction",
                    "experiment",
                    "evaluation",
                    "result",
                    "conclusion",
                )
            )
            or text.lower().startswith("abstract")
        ):
            evidence.append(text.lower())
    return " ".join(evidence)


def _primary_variant_evidence(
    paper_ir: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> tuple[set[str], dict[str, int]]:
    families: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        node_text = " ".join(
            str(node.get(key) or "")
            for key in ("name", "section_title", "purpose", "innovation")
        )
        for marker in _variant_markers(node_text):
            families[marker.split("-", 1)[0]].add(marker)
    comparable_markers = {
        marker
        for markers in families.values()
        if len(markers) >= 2
        for marker in markers
    }
    evidence_text = _primary_evidence_text(paper_ir)
    counts = Counter(
        {
            marker: len(re.findall(rf"\b{re.escape(marker)}\b", evidence_text))
            for marker in comparable_markers
        }
    )
    highest = max(counts.values(), default=0)
    primary = {
        marker
        for marker, count in counts.items()
        if highest > 0 and count == highest
    }
    return primary, dict(sorted(counts.items()))


def _overview_rank(
    record: dict[str, Any],
    paper_ir: dict[str, Any],
    primary_variants: set[str],
) -> tuple[float, list[str]]:
    caption = normalize_text(str(record.get("caption") or "")).lower()
    reasons: list[str] = []
    score = 10.0
    if "overall" in caption or "overview" in caption:
        score += 2.0
        reasons.append("caption explicitly states overall/overview")
    if any(term in caption for term in ("architecture", "framework", "pipeline", "workflow")):
        score += 2.0
        reasons.append("caption describes a complete system structure")
    if "training" in caption and "inference" in caption:
        score += 1.5
        reasons.append("caption spans training and inference")
    if "input" in caption and "output" in caption:
        score += 1.0
        reasons.append("caption spans input and output")
    if any(
        phrase in caption
        for phrase in (
            "network consists",
            "model consists",
            "framework consists",
            "complete network",
            "entire network",
        )
    ):
        score += 2.0
        reasons.append("caption explicitly describes the complete network")
    if any(
        phrase in caption
        for phrase in (
            "update strategy",
            "attention maps",
            "feature maps",
            "visualization of",
        )
    ):
        score -= 2.0
        reasons.append("caption is limited to a module strategy or analysis view")

    title_tokens = {
        token
        for token in token_set(
            str(paper_ir.get("metadata", {}).get("title") or "")
        )
        if token not in TITLE_STOPWORDS
    }
    overlap = title_tokens & token_set(caption)
    if overlap:
        score += min(3.0, len(overlap) * 0.8)
        reasons.append("caption aligns with paper title: " + ", ".join(sorted(overlap)))

    covered = {
        mapping["module_id"]
        for mapping in record.get("module_mappings", [])
        if mapping.get("score", 0) >= MODULE_MATCH_THRESHOLD
    }
    score += min(1.5, len(covered) * 0.25)
    if covered:
        reasons.append(f"covers {len(covered)} sourced method node(s)")

    caption_markers = _variant_markers(caption)
    if primary_variants:
        primary_families = {
            marker.split("-", 1)[0] for marker in primary_variants
        }
        caption_family_markers = {
            marker
            for marker in caption_markers
            if marker.split("-", 1)[0] in primary_families
        }
        matched = caption_family_markers & primary_variants
        if matched:
            score += 6.0
            reasons.append(
                "matches primary variant evidence: " + ", ".join(sorted(matched))
            )
        elif caption_family_markers:
            score -= 4.0
            reasons.append(
                "caption is limited to non-primary variant(s): "
                + ", ".join(sorted(caption_family_markers))
            )
    return round(score, 3), reasons


def map_method_figures(
    paper_ir_path: Path,
    method_graph_path: Path,
    asset_catalog_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    graph = read_json(method_graph_path)
    catalog = read_json(asset_catalog_path)
    figures = catalog.get("figures") or paper_ir.get("figures", [])
    nodes = graph.get("nodes", [])
    aliases_by_node = {
        node["id"]: _node_aliases(node)
        for node in nodes
    }
    alias_owners: dict[str, set[str]] = defaultdict(set)
    token_owners: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        node_id = node["id"]
        for alias in aliases_by_node[node_id]:
            alias_owners[alias].add(node_id)
        node_text = " ".join(
            str(node.get(key) or "")
            for key in ("name", "purpose", "innovation", "section_title")
        )
        for token in _semantic_tokens(node_text):
            token_owners[token].add(node_id)
    unique_aliases_by_node = {
        node["id"]: {
            alias
            for alias in aliases_by_node[node["id"]]
            if alias_owners[alias] == {node["id"]}
        }
        for node in nodes
    }
    distinctive_tokens_by_node = {
        node["id"]: {
            token
            for token, owners in token_owners.items()
            if owners == {node["id"]}
        }
        for node in nodes
    }
    records: list[dict[str, Any]] = []
    coverage_matrix: dict[str, dict[str, float]] = {}
    semantic_conflicts: list[dict[str, Any]] = []
    role_conflicts: list[dict[str, Any]] = []
    resolved_role_conflicts: list[dict[str, Any]] = []

    for asset in figures:
        referenced_node_ids = {
            str(node.get("id"))
            for node in nodes
            if asset.get("id") in (node.get("figure_refs") or [])
        }
        classification = classify_figure_role(
            asset,
            paper_ir,
            referenced_node_ids=referenced_node_ids,
        )
        role = classification["role"]
        confidence = classification["confidence"]
        reasons = classification["reasons"]
        visual_content_signals = classification["visual_content_signals"]
        caption_content_consistent = classification[
            "caption_content_consistent"
        ]
        caption_content_mismatch_reasons = classification[
            "caption_content_mismatch_reasons"
        ]
        reference_strength = classification["reference_strength"]
        poster_eligibility = classification["poster_eligibility"]
        preferred_zone = classification["preferred_zone"]
        evidence_ledger = classification["evidence_ledger"]
        text = _combined(asset)
        caption_text = normalize_text(str(asset.get("caption") or ""))
        caption = caption_text.lower()
        subfigure_semantics = classification["subfigure_semantics"]
        focus_subfigure_labels = classification["focus_subfigure_labels"]
        if referenced_node_ids and role in {
            "experimental_result",
            "qualitative_result",
            "ablation",
            "dataset_example",
        }:
            conflict = {
                "asset_id": asset["id"],
                "code": (
                    "METHOD_REFERENCE_VISUAL_CONTENT_RESULT_CONFLICT"
                    if not caption_content_consistent
                    and visual_content_signals.get("content_role")
                    == "experimental_result"
                    else "METHOD_REFERENCE_CLASSIFIED_AS_NON_METHOD"
                ),
                "referenced_node_ids": sorted(referenced_node_ids),
                "assigned_role": role,
                "visual_content_signals": visual_content_signals,
                "caption_content_mismatch_reasons": (
                    caption_content_mismatch_reasons
                ),
            }
            hard_semantic_result_evidence = bool(
                evidence_ledger.get("measured_comparison")
                or evidence_ledger.get("qualitative_comparison")
                or role in {"ablation", "dataset_example"}
                or any(
                    term in caption
                    for term in EXPLICIT_RESULT_CAPTION_TERMS
                )
                or (
                    any(
                        term in str(asset.get("section_id") or "").lower()
                        for term in RESULT_SECTION_TERMS
                    )
                    and _context_has_result_evidence(text)
                )
            )
            if (
                not caption_content_consistent
                and visual_content_signals.get("content_role")
                == "experimental_result"
            ):
                conflict["resolution"] = (
                    "excluded_from_method_by_visual_content"
                )
                resolved_role_conflicts.append(conflict)
            elif hard_semantic_result_evidence:
                conflict["resolution"] = (
                    "excluded_from_method_by_semantic_result_evidence"
                )
                resolved_role_conflicts.append(conflict)
            else:
                role_conflicts.append(conflict)
        if (
            focus_subfigure_labels
            and role == "other"
            and not _context_has_result_evidence(caption_text)
            and not _caption_has_measured_comparison(caption_text)
            and not any(
                term in caption for term in EXPLICIT_RESULT_CAPTION_TERMS
            )
        ):
            role_conflicts.append(
                {
                    "asset_id": asset["id"],
                    "code": "PROPOSED_SUBFIGURE_EXCLUDED_FROM_METHOD",
                    "focus_subfigure_labels": focus_subfigure_labels,
                    "assigned_role": role,
                }
            )
        caption_aliases = _explicit_aliases(caption_text)
        exclusive_alias_owners = {
            owner
            for alias in caption_aliases
            if len(alias_owners.get(alias, set())) == 1
            for owner in alias_owners[alias]
        }
        mappings: list[dict[str, Any]] = []
        if role in METHOD_ROLES:
            for node in nodes:
                if not _variant_compatible(caption, node):
                    continue
                if node["id"] in referenced_node_ids:
                    mappings.append(
                        {
                            "module_id": node["id"],
                            "score": 1.0,
                            "reasons": [
                                "method section explicitly references this figure"
                            ],
                            "match_kind": "explicit_figure_reference",
                            "binding_evidence": [
                                f"figure_ref:{asset.get('id')}"
                            ],
                        }
                    )
                    continue
                score, match_reasons, match_kind, binding_evidence = _node_match(
                    text,
                    node,
                    caption_text,
                    node_aliases=aliases_by_node[node["id"]],
                    unique_aliases=unique_aliases_by_node[node["id"]],
                    distinctive_tokens=distinctive_tokens_by_node[node["id"]],
                    allow_context_distinctive=role == "method_overview",
                )
                if score >= MODULE_MATCH_THRESHOLD:
                    mappings.append(
                        {
                            "module_id": node["id"],
                            "score": round(score, 3),
                            "reasons": match_reasons,
                            "match_kind": match_kind,
                            "binding_evidence": binding_evidence,
                        }
                    )
            if role in {
                "method_module",
                "mechanism",
                "mechanism_analysis",
            }:
                # An alias that belongs to exactly one method node is
                # exclusive evidence. It must not be overridden by generic
                # sibling words such as fusion/transformer/block/attention.
                if exclusive_alias_owners:
                    mappings = [
                        mapping
                        for mapping in mappings
                        if mapping["module_id"] in exclusive_alias_owners
                    ]
                else:
                    strong_grounded = [
                        mapping
                        for mapping in mappings
                        if mapping.get("match_kind")
                        in {
                            "exact_unique_alias",
                            "exact_alias",
                            "distinctive_terms",
                            "explicit_figure_reference",
                        }
                    ]
                    if strong_grounded:
                        strongest = max(item["score"] for item in strong_grounded)
                        mappings = [
                            item
                            for item in strong_grounded
                            if item["score"] >= strongest - 0.2
                        ]
                    else:
                        mappings = []
                # A parent-module diagram also explains child modules when
                # the parent's sourced description explicitly names them.
                # This recovers nested structures without assuming that every
                # complete overview covers every method node.
                mapped_ids = {item["module_id"] for item in mappings}
                mapped_parents = [
                    node for node in nodes if node["id"] in mapped_ids
                ]
                for child in nodes:
                    if child["id"] in mapped_ids:
                        continue
                    for parent in mapped_parents:
                        described, evidence = _parent_describes_node(
                            parent,
                            child,
                            unique_aliases_by_node[child["id"]],
                        )
                        if described:
                            mappings.append(
                                {
                                    "module_id": child["id"],
                                    "score": 0.85,
                                    "reasons": [
                                        "sourced parent-module description "
                                        "explicitly names this child module"
                                    ],
                                    "match_kind": "parent_module_structure",
                                    "binding_evidence": evidence,
                                }
                            )
                            mapped_ids.add(child["id"])
                            break
            if role == "method_overview" and nodes:
                # Retain low-confidence system-level associations for reading
                # aids, but do not let them count as visual coverage without
                # node-specific caption, context, alias, or citation evidence.
                mapped = {item["module_id"] for item in mappings}
                for node in nodes:
                    if (
                        node["id"] not in mapped
                        and _variant_compatible(caption, node)
                    ):
                        mappings.append(
                            {
                                "module_id": node["id"],
                                "score": 0.2,
                                "reasons": [
                                    "unverified complete-overview association"
                                ],
                                "match_kind": "complete_overview",
                                "binding_evidence": [
                                    "caption:complete_system_unverified"
                                ],
                            }
                        )
        if (
            role in {
                "method_module",
                "mechanism",
                "mechanism_analysis",
            }
            and exclusive_alias_owners
        ):
            mapped_ids = {mapping["module_id"] for mapping in mappings}
            missing_owners = sorted(exclusive_alias_owners - mapped_ids)
            if missing_owners:
                semantic_conflicts.append(
                    {
                        "asset_id": asset["id"],
                        "code": "UNRESOLVED_EXCLUSIVE_ALIAS",
                        "expected_module_ids": missing_owners,
                    }
                )
        coverage_matrix[asset["id"]] = {
            item["module_id"]: item["score"] for item in mappings
        }
        records.append(
            {
                "asset_id": asset["id"],
                "role": role,
                "confidence": confidence,
                "reasons": reasons,
                "method_eligible": role in METHOD_ROLES,
                "result_excluded": role
                in {
                    "experimental_result",
                    "qualitative_result",
                    "ablation",
                    "dataset_example",
                },
                "module_mappings": sorted(
                    mappings,
                    key=lambda item: item["score"],
                    reverse=True,
                ),
                "caption_aliases": sorted(caption_aliases),
                "exclusive_alias_owner_ids": sorted(exclusive_alias_owners),
                "referenced_node_ids": sorted(referenced_node_ids),
                "subfigure_semantics": subfigure_semantics,
                "focus_subfigure_labels": focus_subfigure_labels,
                "visual_content_signals": visual_content_signals,
                "caption_content_consistent": caption_content_consistent,
                "caption_content_mismatch_reasons": (
                    caption_content_mismatch_reasons
                ),
                "reference_strength": reference_strength,
                "poster_eligibility": poster_eligibility,
                "preferred_zone": preferred_zone,
                "evidence_ledger": evidence_ledger,
                "path": asset.get("path"),
                "page": asset.get("page"),
                "caption": normalize_text(str(asset.get("caption") or "")),
            }
        )

    method_assets = [record for record in records if record["method_eligible"]]
    primary_variants, variant_counts = _primary_variant_evidence(paper_ir, nodes)
    overview_candidates = [
        record for record in method_assets if record["role"] == "method_overview"
    ]
    for record in overview_candidates:
        rank_score, rank_reasons = _overview_rank(
            record,
            paper_ir,
            primary_variants,
        )
        record["canonical_overview_score"] = rank_score
        record["canonical_overview_reasons"] = rank_reasons
    ranked_overviews = sorted(
        overview_candidates,
        key=lambda item: (
            item.get("canonical_overview_score", 0),
            len(item.get("module_mappings", [])),
            item.get("confidence", 0),
        ),
        reverse=True,
    )
    overview = ranked_overviews[0] if ranked_overviews else None
    selection_margin = (
        round(
            float(ranked_overviews[0]["canonical_overview_score"])
            - float(ranked_overviews[1]["canonical_overview_score"]),
            3,
        )
        if len(ranked_overviews) >= 2
        else None
    )
    overview_ambiguous = bool(
        len(ranked_overviews) >= 2
        and selection_margin is not None
        and selection_margin < 0.75
    )
    if len(ranked_overviews) <= 1:
        overview_basis = "single_overview_candidate"
    elif overview and any(
        reason.startswith("matches primary variant evidence")
        for reason in overview.get("canonical_overview_reasons", [])
    ):
        overview_basis = "primary_variant_evidence"
    else:
        overview_basis = "semantic_completeness"
    result_excluded_ids = [
        record["asset_id"] for record in records if record["result_excluded"]
    ]
    figure_map = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "figures_inspected": len(records),
        "records": records,
        "overview_asset_id": overview["asset_id"] if overview else None,
        "overview_selection_basis": overview_basis,
        "overview_selection_margin": selection_margin,
        "overview_selection_ambiguous": overview_ambiguous,
        "primary_variant_markers": sorted(primary_variants),
        "primary_variant_evidence_counts": variant_counts,
        "overview_ranking": [
            {
                "asset_id": record["asset_id"],
                "score": record.get("canonical_overview_score", 0),
                "reasons": record.get("canonical_overview_reasons", []),
            }
            for record in ranked_overviews
        ],
        "method_asset_ids": [record["asset_id"] for record in method_assets],
        "result_excluded_ids": result_excluded_ids,
        "coverage_matrix": coverage_matrix,
        "semantic_binding_conflicts": semantic_conflicts,
        "role_conflicts": role_conflicts,
        "resolved_role_conflicts": resolved_role_conflicts,
        "module_alias_index": {
            node_id: sorted(aliases)
            for node_id, aliases in aliases_by_node.items()
        },
        "figure_number_prior_used": False,
    }
    report = {
        "status": (
            "failed"
            if overview_ambiguous or semantic_conflicts or role_conflicts
            else "passed"
        ),
        "figures_inspected": len(records),
        "method_assets": len(method_assets),
        "result_assets_excluded_from_method": len(result_excluded_ids),
        "overview_asset_id": figure_map["overview_asset_id"],
        "overview_selection_basis": overview_basis,
        "overview_selection_margin": selection_margin,
        "primary_variant_markers": sorted(primary_variants),
        "warnings": (
            ["Multiple overview figures remain semantically ambiguous."]
            if overview_ambiguous
            else (
                ["Exclusive module aliases could not be resolved."]
                if semantic_conflicts
                else (
                    ["Method-cited or proposed subfigures have conflicting roles."]
                    if role_conflicts
                    else (
                        []
                        if method_assets
                        else ["No method-eligible paper figure was found."]
                    )
                )
            )
        ),
    }
    return (
        write_json(output_dir / "method_figure_map.json", figure_map),
        write_json(output_dir / "method_figure_map_report.json", report),
    )
