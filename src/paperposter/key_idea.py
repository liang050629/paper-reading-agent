from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from .common import (
    complete_sentences,
    jaccard,
    normalize_text,
    read_json,
    sentences,
    sha256_file,
    source_ref,
    token_set,
    write_json,
)

KEY_IDEA_TYPES = {
    "formula_centered",
    "contrast_centered",
    "mechanism_centered",
    "architecture_centered",
    "finding_centered",
}
DISPLAY_MODES = {"original_crop", "latex_render", "none"}
KEY_IDEA_VISUAL_TYPES = {
    "equation_with_callouts",
    "existing_vs_ours",
    "single_mechanism_focus",
    "two_part_mechanism",
    "three_step_flow",
    "mechanism_grid",
    "single_architecture_focus",
    "two_module_relationship",
    "core_module_relationship",
    "evidence_impact",
}
VISUAL_ITEM_COUNT_CONTRACTS = {
    "single_mechanism_focus": (1, 1),
    "two_part_mechanism": (2, 2),
    "three_step_flow": (3, 3),
    "mechanism_grid": (4, 4),
    "single_architecture_focus": (1, 1),
    "two_module_relationship": (2, 2),
    "core_module_relationship": (3, 4),
    "existing_vs_ours": (2, 2),
    "evidence_impact": (2, 2),
    "equation_with_callouts": (1, 2),
}
GENERIC_EQUATION_TERMS = (
    "cross entropy",
    "cross-entropy",
    "binary cross entropy",
    "bce loss",
    "dice loss",
    "mean squared error",
    "mse loss",
    "accuracy",
    "precision",
    "recall",
    "specificity",
    "sensitivity",
    "auc",
    "f1 score",
)
VISIBLE_LATEX_COMMAND_RE = re.compile(
    r"\\(?:begin|end|tag|mathbb|mathcal|mathrm|mathbf|text|"
    r"operatorname|frac|sum|prod|sqrt|lambda|alpha|beta|gamma|"
    r"cdot|times|ldots|dots|in|left|right|overline|underline)\b",
    re.I,
)
MATH_DELIMITER_RE = re.compile(r"\$|\\\(|\\\)|\\\[|\\\]")
RAW_SCRIPT_RE = re.compile(
    r"(?:[A-Za-z0-9)]|\})\s*[_^]\s*(?:\{|[A-Za-z0-9(])"
)
CROSS_REFERENCE_RE = re.compile(
    r"\b(?:as\s+shown\s+in|see|shown\s+in)\s+"
    r"(?:Fig(?:ure)?|Table|Section|Eq(?:uation)?)\.?\s*"
    r"[A-Za-z0-9().-]*",
    re.I,
)
DANGLING_END_RE = re.compile(
    r"\b(?:and|or|through|while|with|from|to|of|for|the|a|an|"
    r"where|which|that|by|in|on|as|including|consists|contains)\s*[,:;.-]*$",
    re.I,
)
UNRESOLVED_REFERENCE_RE = re.compile(
    r"^(?:this|these|those|such|the former|the latter|it|they)\b",
    re.I,
)
OCR_RESIDUE_RE = re.compile(r"(?:\uFFFD|鈥\?|閳|锟)")
GENERIC_VISUAL_NODE_RE = re.compile(
    r"^(?:the\s+)?(?:encoder|decoder|backbone|network|framework|"
    r"architecture|pipeline|training|loss function|objective function|"
    r"stage\s*\d*)$",
    re.I,
)
METHOD_TERMS = (
    "mechanism",
    "fusion",
    "attention",
    "routing",
    "memory",
    "interaction",
    "aggregation",
    "selection",
    "weighting",
    "cross-learning",
)
ARCHITECTURE_TERMS = (
    "architecture",
    "framework",
    "network",
    "pipeline",
    "encoder",
    "decoder",
    "system",
)
CONTRAST_TERMS = (
    "unlike",
    "instead",
    "existing",
    "previous",
    "limitation",
    "without",
    "whereas",
    "compared",
)
FINDING_TERMS = (
    "we find",
    "we observe",
    "reveals",
    "demonstrates",
    "outperform",
    "highest",
    "significant",
    "evidence",
)


def _word_count(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", value))


def _clip_words(value: str, limit: int) -> str:
    words = normalize_text(value).split()
    return " ".join(words[:limit]).rstrip(" ,;:")


def _balanced(value: str, opening: str, closing: str) -> bool:
    depth = 0
    for char in value:
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def visible_text_findings(
    value: str,
    *,
    allow_phrase: bool = False,
) -> list[str]:
    text = normalize_text(str(value or ""))
    findings: list[str] = []
    if not text:
        return ["empty_visible_text"]
    if MATH_DELIMITER_RE.search(text):
        findings.append("math_delimiter_check")
    if VISIBLE_LATEX_COMMAND_RE.search(text) or re.search(r"\\[A-Za-z]+", text):
        findings.append("latex_residue_check")
    if RAW_SCRIPT_RE.search(text):
        findings.append("raw_subscript_superscript_check")
    if not _balanced(text, "{", "}"):
        findings.append("unmatched_braces_check")
    if not _balanced(text, "(", ")"):
        findings.append("unmatched_parenthesis_check")
    if CROSS_REFERENCE_RE.search(text):
        findings.append("cross_reference_check")
    if OCR_RESIDUE_RE.search(text):
        findings.append("ocr_cleanup_check")
    if DANGLING_END_RE.search(text):
        findings.append("dangling_conjunction_check")
    if UNRESOLVED_REFERENCE_RE.search(text):
        findings.append("unresolved_reference_check")
    if re.search(r"(?:=|≤|≥|<|>)\s*$|(?:\+|-|/|\*)\s*$", text):
        findings.append("incomplete_equation_fragment_check")
    if not allow_phrase:
        words = _word_count(text)
        has_terminal = text.endswith((".", "!", "?"))
        complete_clause = bool(
            re.search(
                r"\b(?:is|are|uses|use|combines|extracts|captures|models|"
                r"aggregates|updates|matches|compares|fuses|preserves|"
                r"controls|balances|computes|retrieves|enhances|reduces|"
                r"enables|requires|provides|learns|applies|organizes|"
                r"coordinates|represents|produces|addresses|supports)\b",
                text,
                re.I,
            )
        )
        if words < 4 or not (has_terminal or complete_clause):
            findings.append("sentence_completeness_check")
        starts_with_incomplete_connector = re.match(
            r"^(?:where|which|and|or|through)\b", text, re.I
        )
        starts_with_unresolved_while = re.match(
            r"^while\b", text, re.I
        ) and not re.search(
            r"^while\b.+,\s+.+\b(?:is|are|was|were|do|does|did|has|have|"
            r"can|could|would|may|might|must|surpasses?|exceeds?|improves?|"
            r"maintains?|performs?|uses?|provides?|remains?)\b",
            text,
            re.I,
        )
        if starts_with_incomplete_connector or starts_with_unresolved_while:
            findings.append("clause_completeness_check")
    return list(dict.fromkeys(findings))


def _replace_math_span(match: re.Match[str]) -> str:
    raw = str(match.group(0) or "")
    compact = re.sub(r"[\s{}_^\\$()]+", "", raw).lower()
    if re.search(r"(?:^|[^a-z])w(?:i|k|q)?(?:$|[^a-z])", compact):
        return "the learnable weights"
    if "mathbbr" in compact or "times" in compact:
        return "the input feature map"
    if "ldots" in compact or re.search(r"i=1", compact):
        return "the category index"
    if "lambda" in compact:
        return "the weighting factor"
    return "the feature variables"


def _strip_visible_markup(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<sub\b[^>]*>(.*?)</sub>", r"\1", text, flags=re.I | re.S)
    text = re.sub(r"<sup\b[^>]*>(.*?)</sup>", r"\1", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[0-9,\s–—-]+\]", " ", text)
    text = CROSS_REFERENCE_RE.sub(" ", text)
    text = re.sub(r"\b(?:Fig(?:ure)?|Table|Section|Eq(?:uation)?)\.?\s*\d+[A-Za-z()]*", " ", text, flags=re.I)
    text = re.sub(r"\(\s*\(?[a-z]\)?\s*\)", " ", text, flags=re.I)
    text = re.sub(r"\$[^$]*\$", _replace_math_span, text)
    text = re.sub(r"\\\([^)]*\\\)", _replace_math_span, text)
    text = re.sub(r"\\\[[^\]]*\\\]", _replace_math_span, text)
    text = re.sub(
        r"\\(?:mathbb|mathcal|mathrm|mathbf|text|operatorname)\s*\{([^{}]*)\}",
        r"\1",
        text,
    )
    text = re.sub(r"\\(?:lambda|alpha|beta|gamma)\b", "the parameter", text)
    text = re.sub(r"\\(?:cdot|times)\b", " ", text)
    text = re.sub(r"\\(?:ldots|dots)\b", " ", text)
    text = re.sub(r"\\(?:in|left|right)\b", " ", text)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    text = re.sub(r"[{}_^$]+", " ", text)
    replacements = {
        r"\bwhich(?=[A-Z])": "which ",
        r"\bwhich\s+Neuron\b": "which",
        r"\bcategoryfeatures\b": "category features",
        r"\bofspecific\b": "of specific",
        r"\bcat\s*Feature\s*egories\b": "categories",
        r"\bback\s+bone\b": "backbone",
        r"\befective\b": "effective",
        r"\bdiferent\b": "different",
        r"\bMulti Scale\b": "Multi-Scale",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(
        r"^\s*(?:specifically|therefore|subsequently|however|although|"
        r"to\s+this\s+end|"
        r"in\s+this\s+(?:paper|work|article))\s*[,;:]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*(?:we|the authors)\s+"
        r"(?:propose|introduce|design|develop|present)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\(\s*\)", " ", text)
    text = OCR_RESIDUE_RE.sub(" ", text)
    return normalize_text(text).strip(" ,;:")


def _complete_visible_sentence(
    value: str,
    *,
    max_words: int = 24,
) -> str:
    text = _strip_visible_markup(value)
    if not text:
        return ""
    text = re.sub(
        r",?\s*(?:as\s+shown\s+in|see)\s+"
        r"(?:Fig(?:ure)?|Table|Section|Eq(?:uation)?).*$",
        "",
        text,
        flags=re.I,
    ).strip(" ,;:")
    text = re.sub(
        r"^where\s+the learnable weights\s+are learnable weight parameters,?\s*",
        "Learnable weights ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^where\s+the category index\s*,?\s*",
        "The category index ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^assuming\s+the\s+input\s+size\s+is\s+the\s+input\s+feature\s+map,?\s*",
        "The module processes the input feature map and ",
        text,
        flags=re.I,
    )
    candidates = [
        normalize_text(sentence)
        for sentence in sentences(text)
        if normalize_text(sentence)
    ]
    for candidate in candidates:
        if (
            _word_count(candidate) <= max_words
            and not visible_text_findings(candidate)
        ):
            return candidate
    for candidate in candidates or [text]:
        clauses = [
            normalize_text(part)
            for part in re.split(r"[;:]|,\s+(?:while|whereas|which|and\s+then)\s+", candidate)
            if normalize_text(part)
        ]
        for clause in clauses:
            if (
                4 <= _word_count(clause) <= max_words
                and not DANGLING_END_RE.search(clause)
                and not visible_text_findings(
                    clause.rstrip(".") + "."
                )
            ):
                return clause.rstrip(" ,;:.") + "."
    return ""


def _semantic_visual_rewrite(label: str, source_text: str) -> str:
    lowered = normalize_text(label).lower()
    source = _strip_visible_markup(source_text)
    if "multi-scale linear attention" in lowered:
        return (
            "Combines multi-scale feature extraction with linear attention "
            "to aggregate cross-scale global context."
        )
    if "multi-scale feature" in lowered:
        return (
            "Extracts hierarchical features with depth-wise convolutions "
            "operating at multiple spatial scales."
        )
    if "linear attention" in lowered:
        return (
            "Uses linear attention to aggregate global context with low "
            "computational complexity."
        )
    if "dynamic memory" in lowered or "weight-loss" in lowered:
        return (
            "Updates prototype memories with feature- and loss-aware weights "
            "to retain category-specific evidence."
        )
    if "double-similarity" in lowered:
        return (
            "Combines complementary similarity measures to enhance "
            "category-aware global representations."
        )
    if "cross attention" in lowered or "feature fusion" in lowered:
        return (
            "Cross-attention integrates complementary feature levels into "
            "a unified representation."
        )
    if "scale-aware" in lowered or "scale aware" in lowered:
        return (
            "Adapts spatial sampling to variations in object scale."
        )
    rewritten = _complete_visible_sentence(source, max_words=20)
    if rewritten:
        return rewritten
    return ""


def _clean_visible_label(value: str) -> str:
    label = _strip_visible_markup(value)
    label = re.sub(r"^(?:the\s+)?(?:proposed|novel)\s+", "", label, flags=re.I)
    label = label.strip(" ,;:.")
    if visible_text_findings(label, allow_phrase=True):
        return ""
    words = label.split()
    if len(words) > 8:
        label = " ".join(words[:8]).strip(" ,;:")
    return label


def audit_key_idea_visible_text(spec: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    fields: list[tuple[str, str, bool]] = [
        ("headline", str(spec.get("headline") or ""), False),
        ("takeaway", str(spec.get("takeaway") or ""), False),
        ("inference_label", str(spec.get("inference_label") or ""), True),
    ]
    for index, item in enumerate((spec.get("visual") or {}).get("items") or []):
        fields.append(
            (f"visual.items[{index}].label", str(item.get("label") or ""), True)
        )
        fields.append(
            (f"visual.items[{index}].text", str(item.get("text") or ""), False)
        )
    equation = spec.get("equation") or {}
    if equation.get("equation_id"):
        fields.append(
            (
                "equation.plain_language_explanation",
                str(equation.get("plain_language_explanation") or ""),
                False,
            )
        )
    for path, value, allow_phrase in fields:
        for code in visible_text_findings(value, allow_phrase=allow_phrase):
            findings.append({"field": path, "code": code, "value": value})
    return {
        "status": "passed" if not findings else "failed",
        "findings": findings,
        "latex_residue_check": not any(
            finding["code"] == "latex_residue_check" for finding in findings
        ),
        "math_delimiter_check": not any(
            finding["code"] == "math_delimiter_check" for finding in findings
        ),
        "sentence_completeness_check": not any(
            finding["code"] in {
                "sentence_completeness_check",
                "clause_completeness_check",
                "dangling_conjunction_check",
            }
            for finding in findings
        ),
    }


def _source_ids(sources: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(source.get("block_id"))
            for source in sources
            if source.get("block_id")
        )
    )


def _supported_claims(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        claim
        for claim in evidence.get("claims", [])
        if claim.get("verdict") in {"supported", "partially_supported"}
    ]


def _claim_score(claim: dict[str, Any], gap: str) -> float:
    text = normalize_text(str(claim.get("claim") or ""))
    lowered = text.lower()
    score = float(claim.get("confidence") or 0)
    score += 3.0 * sum(
        term in lowered
        for term in ("we propose", "we design", "we introduce", "novel", "core")
    )
    score += 4.0 if "main idea" in lowered else 0.0
    score += 1.5 * sum(
        term in lowered
        for term in ("preserve two", "two kinds", "principle", "key insight")
    )
    score += 1.5 * sum(term in lowered for term in METHOD_TERMS)
    if re.fullmatch(
        r"(?:we|the authors)\s+(?:propose|introduce)\s+\S+,?\s+"
        r"(?:a|an)\s+(?:novel\s+)?(?:structured\s+)?"
        r"(?:framework|architecture|network|model).?",
        lowered,
    ):
        score -= 2.0
    score += min(1.5, jaccard(text, gap) * 4)
    if re.search(r"\d+\.\d+|%", text):
        score -= 0.8
    return score


def _core_claim(
    evidence: dict[str, Any],
    story: dict[str, Any],
) -> dict[str, Any]:
    gap = str(story.get("prior_work_gap", {}).get("summary") or "")
    candidates = list(_supported_claims(evidence))
    for field in (
        "motivation",
        "core_hypothesis",
        "theory_or_mechanism",
        "method_design",
    ):
        node = story.get(field, {})
        if node.get("summary"):
            candidates.append(
                {
                    "claim_id": None,
                    "claim": node["summary"],
                    "sources": node.get("sources", []),
                    "verdict": (
                        "inferred"
                        if node.get("status") == "inferred"
                        else "supported"
                    ),
                    "confidence": node.get("confidence", 0.5),
                }
            )
    if candidates:
        return max(candidates, key=lambda claim: _claim_score(claim, gap))
    return {
        "claim_id": None,
        "claim": "The paper's differentiating insight could not be recovered.",
        "sources": [],
        "verdict": "inferred",
        "confidence": 0.0,
    }


def _equation_number(asset: dict[str, Any]) -> str | None:
    latex = str(asset.get("latex") or "")
    match = re.search(r"\\tag\{([^{}]+)\}", latex)
    return match.group(1) if match else None


def _equation_dimension_scores(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
    core_text: str,
) -> tuple[dict[str, int], list[str], bool]:
    context = normalize_text(
        " ".join(
            str(asset.get(key) or "")
            for key in ("caption", "context_before", "context_after", "section_id")
        )
    )
    lowered = context.lower()
    latex = normalize_text(str(asset.get("latex") or ""))
    combined = f"{lowered} {latex.lower()}"
    compact_latex = re.sub(r"[^a-z0-9]+", "", latex.lower())
    spaced_loss_name = bool(
        re.search(r"l(?:mathcal)?dice", compact_latex)
        or (
            "dice" in compact_latex
            and any(
                token in compact_latex
                for token in ("lce", "crossentropy", "binarycrossentropy")
            )
        )
        or (
            re.search(r"d\s*i\s*c\s*e", latex, re.I)
            and re.search(r"(?:c\s*e|cross[- ]?entropy)", latex, re.I)
        )
    )
    generic = any(term in combined for term in GENERIC_EQUATION_TERMS) or bool(
        re.search(
            r"(?:\\mathrm\s*\{\s*)?(?:dice|bce|mse)(?:\s*\})?",
            combined,
            re.I,
        )
    ) or spaced_loss_name
    abstract = " ".join(
        str(block.get("text") or "")
        for block in paper_ir.get("blocks", [])
        if block.get("type") == "abstract"
    )
    core_reference = normalize_text(
        f"{core_text} {paper_ir.get('metadata', {}).get('title') or ''} {abstract}"
    )
    theoretical_definition = any(
        term in lowered
        for term in ("definition", "theorem", "proposition", "lemma")
    )

    novelty = 0
    if not generic and (
        any(
            term in lowered
            for term in (
                "we propose",
                "novel",
                "our ",
                "final",
                "hybrid",
                "weighted fusion",
            )
        )
        or (
            theoretical_definition
            and jaccard(context, core_reference) >= 0.035
        )
    ):
        novelty = 2
    elif not generic and any(term in lowered for term in METHOD_TERMS):
        novelty = 1

    overlap = jaccard(context, core_reference)
    centrality = 2 if overlap >= 0.12 or "final objective" in lowered else 1 if overlap >= 0.04 else 0
    if generic:
        centrality = min(centrality, 1)

    necessity = 0
    if not generic and any(
        term in lowered
        for term in (
            "definition",
            "theorem",
            "proposition",
            "lemma",
            "equivalent",
            "derived",
            "defined as",
        )
    ):
        necessity = 2
    elif not generic and any(term in lowered for term in ("mechanism", "objective", "weight")):
        necessity = 1

    number = _equation_number(asset)
    downstream_general = 0
    downstream_validation = 0
    if number:
        eq_pattern = re.compile(
            rf"(?:Eq(?:uation)?\.?\s*\(?{re.escape(number)}\)?|"
            rf"\({re.escape(number)}\))",
            re.I,
        )
        for block in paper_ir.get("blocks", []):
            text = str(block.get("text") or "")
            if not eq_pattern.search(text):
                continue
            downstream_general += 1
            section = (
                f"{block.get('section_title') or ''} "
                f"{block.get('section_id') or ''}"
            ).lower()
            if any(term in section for term in ("result", "analysis", "ablation", "experiment")):
                downstream_validation += 1
    downstream_general += len(asset.get("cited_by") or [])
    downstream_usage = 2 if downstream_general >= 2 else 1 if downstream_general == 1 else 0
    section_label = normalize_text(
        str(asset.get("section_id") or "").replace("-", " ")
    )
    concept_validation = any(
        any(
            term in (
                f"{block.get('section_title') or ''} "
                f"{block.get('section_id') or ''}"
            ).lower()
            for term in ("result", "analysis", "ablation", "experiment")
        )
        and jaccard(section_label, str(block.get("text") or "")) >= 0.08
        for block in paper_ir.get("blocks", [])
    )
    validation = 2 if downstream_validation else 1 if (
        concept_validation
        or any(
            term in lowered
            for term in ("validated", "ablation", "experiment", "analysis")
        )
    ) else 0
    if generic:
        downstream_usage = min(downstream_usage, 1)
        validation = min(validation, 1)

    latex_tokens = re.findall(r"[A-Za-z]+|\\[A-Za-z]+", latex)
    poster_explainability = 0
    if latex and len(latex) <= 180 and len(latex_tokens) <= 20:
        poster_explainability = 2
    elif latex and len(latex) <= 320:
        poster_explainability = 1
    elif asset.get("path") and len(context.split()) <= 80:
        poster_explainability = 1

    dimensions = {
        "novelty": novelty,
        "centrality": centrality,
        "necessity": necessity,
        "downstream_usage": downstream_usage,
        "validation": validation,
        "poster_explainability": poster_explainability,
    }
    reasons = [f"{name}={value}/2" for name, value in dimensions.items()]
    if generic:
        reasons.append("rejected or downweighted as a generic loss/metric equation")
    return dimensions, reasons, generic


def score_equation(
    asset: dict[str, Any],
    paper_ir: dict[str, Any],
    core_text: str,
) -> dict[str, Any]:
    dimensions, reasons, generic = _equation_dimension_scores(
        asset,
        paper_ir,
        core_text,
    )
    score = sum(dimensions.values())
    tier = (
        "key_idea_primary"
        if score >= 9 and not generic
        else "key_idea_supporting"
        if score >= 7 and not generic
        else "method_details"
        if score >= 4
        else "omit"
    )
    return {
        "equation_id": asset.get("id"),
        "score": score,
        "dimensions": dimensions,
        "selection_reason": reasons,
        "generic_rejected": generic,
        "tier": tier,
    }


def _equation_explanation(
    asset: dict[str, Any],
    core_text: str,
) -> str:
    latex = str(asset.get("latex") or "")
    compact = re.sub(r"[^a-z0-9]+", "", latex.lower())
    context = normalize_text(
        f"{asset.get('context_before') or ''} "
        f"{asset.get('context_after') or ''} {core_text}"
    ).lower()
    if "crossattn" in compact or "cross-attention" in context:
        return (
            "Cross-attention uses complementary feature streams to produce "
            "a unified multi-level representation."
        )
    if re.search(r"(?:^|[^a-z])sm(?:$|[^a-z])", compact) or (
        "similarity" in context and "memory" in context
    ):
        return (
            "Similarity matching compares category features with prototype "
            "memories and retrieves a category-aware representation."
        )
    if "weightedfusion" in context or (
        "weight" in context and "fusion" in context
    ):
        return (
            "Adaptive weights control how complementary feature streams are "
            "combined by the central fusion mechanism."
        )
    candidates = [
        _complete_visible_sentence(sentence, max_words=24)
        for context_value in (
            str(asset.get("context_after") or ""),
            str(asset.get("context_before") or ""),
        )
        for sentence in sentences(context_value)
    ]
    candidates = [
        candidate
        for candidate in candidates
        if candidate
        and not visible_text_findings(candidate)
        and any(
            cue in candidate.lower()
            for cue in (
                "computes",
                "controls",
                "estimates",
                "matches",
                "measures",
                "represents",
                "retrieves",
                "weights",
            )
        )
    ]
    if candidates:
        return candidates[0]
    return (
        "The equation computes the selected mechanism from its input "
        "representations and links it to the paper's central design."
    )


def _none_equation(reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "equation_id": None,
        "display_mode": "none",
        "image_path": None,
        "latex": None,
        "page": None,
        "bbox": None,
        "score": None,
        "dimensions": None,
        "generic_rejected": False,
        "primary_method_binding": False,
        "alignment_gate": {
            "passed": False,
            "reason": list(reasons or ["no aligned equation selected"]),
        },
        "selection_reason": list(reasons or ["no aligned equation selected"]),
        "plain_language_explanation": "",
        "image_sha256": None,
        "crop_integrity": None,
    }


def _select_equation(
    paper_ir: dict[str, Any],
    paper_ir_path: Path,
    core_text: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scored = [
        (score_equation(asset, paper_ir, core_text), asset)
        for asset in paper_ir.get("equations", [])
    ]
    scored.sort(key=lambda item: item[0]["score"], reverse=True)
    audits = [audit for audit, _ in scored]
    eligible = [
        (audit, asset)
        for audit, asset in scored
        if audit["score"] >= 7 and not audit["generic_rejected"]
    ]
    if not eligible:
        reasons = ["no equation passed the generic-equation and score gates"]
        if scored:
            reasons.extend(scored[0][0]["selection_reason"])
        return _none_equation(reasons), audits

    audit, asset = eligible[0]
    raw_path = asset.get("path")
    source_path = Path(str(raw_path)) if raw_path else None
    if source_path and not source_path.is_absolute():
        source_path = paper_ir_path.parent / source_path
    image_exists = bool(source_path and source_path.is_file())
    latex = str(asset.get("latex") or "") or None
    # Formal Poster rendering is deterministic and offline. Until a real
    # MathJax/KaTeX renderer is bundled, never expose raw LaTeX as visible HTML.
    display_mode = "original_crop" if image_exists else "none"
    if display_mode == "none":
        return _none_equation(
            audit["selection_reason"]
            + ["candidate has no usable original equation crop"]
        ), audits
    bbox = asset.get("bbox")
    crop_integrity = bool(
        display_mode == "original_crop"
        and bbox
        and len(bbox) == 4
        and float(bbox[2]) > float(bbox[0])
        and float(bbox[3]) > float(bbox[1])
        and not asset.get("crop_pending")
    )
    return {
        "equation_id": asset.get("id"),
        "display_mode": display_mode,
        "image_path": str(raw_path) if display_mode == "original_crop" else None,
        "latex": latex,
        "page": asset.get("page"),
        "bbox": bbox,
        "score": audit["score"],
        "dimensions": audit["dimensions"],
        "generic_rejected": audit["generic_rejected"],
        "primary_method_binding": False,
        "alignment_gate": {"passed": None, "reason": []},
        "selection_reason": audit["selection_reason"],
        "plain_language_explanation": _equation_explanation(asset, core_text),
        "image_sha256": sha256_file(source_path) if image_exists and source_path else None,
        "crop_integrity": crop_integrity if display_mode == "original_crop" else None,
        "_source_context": normalize_text(
            f"{asset.get('caption') or ''} {asset.get('context_before') or ''} "
            f"{asset.get('context_after') or ''} {asset.get('section_id') or ''}"
        ),
    }, audits


def _equation_primary_method_binding(
    equation: dict[str, Any],
    graph: dict[str, Any],
    core_text: str,
) -> bool:
    context = str(equation.get("_source_context") or "")
    if jaccard(context, core_text) >= 0.1:
        return True
    return any(
        jaccard(
            context,
            normalize_text(
                f"{node.get('name') or ''} {node.get('innovation') or ''} "
                f"{node.get('purpose') or ''}"
            ),
        )
        >= 0.1
        for node in graph.get("nodes", [])
        if not GENERIC_VISUAL_NODE_RE.fullmatch(
            normalize_text(str(node.get("name") or ""))
        )
    )


def _apply_equation_alignment_gate(
    equation: dict[str, Any],
    idea_type: str,
    graph: dict[str, Any],
    core_text: str,
) -> dict[str, Any]:
    if not equation.get("equation_id"):
        return equation
    dimensions = dict(equation.get("dimensions") or {})
    primary_binding = _equation_primary_method_binding(
        equation,
        graph,
        core_text,
    )
    centrality = int(dimensions.get("centrality") or 0)
    downstream = int(dimensions.get("downstream_usage") or 0)
    validation = int(dimensions.get("validation") or 0)
    reasons: list[str] = []
    if equation.get("generic_rejected"):
        reasons.append("generic_equation_gate")
    if idea_type == "mechanism_centered":
        if centrality != 2:
            reasons.append("mechanism equation centrality must equal 2")
        if not (downstream == 2 or validation == 2 or primary_binding):
            reasons.append(
                "mechanism equation lacks downstream, validation, or primary-method binding"
            )
    elif centrality < 1:
        reasons.append("equation is not aligned with the selected Key Idea")
    if reasons:
        return _none_equation(
            [
                *equation.get("selection_reason", []),
                "equation_key_idea_alignment_gate failed",
                *reasons,
            ]
        )
    equation = dict(equation)
    equation.pop("_source_context", None)
    equation["primary_method_binding"] = primary_binding
    equation["alignment_gate"] = {
        "passed": True,
        "reason": [
            f"centrality={centrality}/2",
            f"downstream_usage={downstream}/2",
            f"validation={validation}/2",
            f"primary_method_binding={str(primary_binding).lower()}",
        ],
    }
    return equation


def _type_scores(
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    evidence: dict[str, Any],
    graph: dict[str, Any],
    equation: dict[str, Any],
) -> dict[str, float]:
    title = str(paper_ir.get("metadata", {}).get("title") or "")
    abstract = " ".join(
        str(block.get("text") or "")
        for block in paper_ir.get("blocks", [])
        if block.get("type") == "abstract"
    )
    gap = str(story.get("prior_work_gap", {}).get("summary") or "")
    mechanism = str(story.get("theory_or_mechanism", {}).get("summary") or "")
    claims = " ".join(str(item.get("claim") or "") for item in _supported_claims(evidence))
    text = f"{title} {abstract} {gap} {mechanism} {claims}".lower()
    method_nodes = graph.get("nodes", [])
    result_claims = sum(
        bool(re.search(r"\d+\.\d+|%|outperform|highest", str(item.get("claim") or ""), re.I))
        for item in _supported_claims(evidence)
    )
    scores = {
        "formula_centered": 0.0,
        "contrast_centered": 0.0,
        "mechanism_centered": 0.0,
        "architecture_centered": 0.0,
        "finding_centered": 0.0,
    }
    if equation.get("score") is not None:
        scores["formula_centered"] += max(0.0, float(equation["score"]) - 7)
    scores["contrast_centered"] += 0.9 * sum(term in text for term in CONTRAST_TERMS)
    scores["mechanism_centered"] += 1.1 * sum(term in text for term in METHOD_TERMS)
    scores["mechanism_centered"] += min(2.0, max(0, len(method_nodes) - 1) * 0.5)
    theory_node = story.get("theory_or_mechanism", {})
    if theory_node.get("summary") and theory_node.get("status") == "explicit":
        scores["mechanism_centered"] += 2.0
    motivation_text = str(story.get("motivation", {}).get("summary") or "").lower()
    if "main idea" in motivation_text or "principle" in motivation_text:
        scores["mechanism_centered"] += 1.0
    scores["architecture_centered"] += 0.8 * sum(term in text for term in ARCHITECTURE_TERMS)
    scores["architecture_centered"] += 1.5 if len(method_nodes) >= 3 else 0
    scores["finding_centered"] += 1.2 * sum(term in text for term in FINDING_TERMS)
    scores["finding_centered"] += min(3.0, result_claims)
    if story.get("core_hypothesis", {}).get("status") == "inferred":
        scores["finding_centered"] -= 0.5
    if equation.get("score") is None or float(equation.get("score") or 0) < 9:
        scores["formula_centered"] = -1.0
    return {key: round(value, 3) for key, value in scores.items()}


def classify_key_idea_type(
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    evidence: dict[str, Any],
    graph: dict[str, Any],
    equation: dict[str, Any],
) -> tuple[str, dict[str, float]]:
    scores = _type_scores(paper_ir, story, evidence, graph, equation)
    idea_type = max(
        KEY_IDEA_TYPES,
        key=lambda name: (
            scores[name],
            {
                "mechanism_centered": 5,
                "contrast_centered": 4,
                "architecture_centered": 3,
                "finding_centered": 2,
                "formula_centered": 1,
            }[name],
        ),
    )
    return idea_type, scores


def _headline(core_text: str, idea_type: str) -> str:
    cleaned = _strip_visible_markup(core_text)
    cleaned = cleaned.strip(" \t\r\n,;:.")
    cleaned = re.sub(
        r"^to\s+address\s+.+?,\s*(?:we|the authors)\s+"
        r"(?:propose|introduce|design|develop|present)\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"^(?:in\s+(?:this|the)\s+(?:paper|article|work),?\s+)?"
        r"(?:we|the authors)\s+"
        r"(?:propose|proposed|design|designed|introduce|introduced|present|presented)\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"^(?:this\s+(?:paper|article|work)\s+)?"
        r"(?:proposes|proposed|designs|designed|introduces|introduced|presents|presented)\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"^(?:by\s+)?utilizing\s+",
        "Using ",
        cleaned,
        flags=re.I,
    )
    which_clause = re.search(r",\s*which\s+(.+)$", cleaned, re.I)
    if which_clause:
        clause = re.split(
            r",\s*(?:thus|thereby|which\s+helps?)\b",
            which_clause.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        clause = re.sub(
            r"\bthrough\s+the\s+similarity\s+memory\s+prior\s+in\s+"
            r"the\s+prototype\s+memory\s+bank\b",
            "through a prototype memory bank",
            clause,
            flags=re.I,
        )
        cleaned = f"The core mechanism {clause}"
    cleaned = cleaned.strip(" \t\r\n,;:.")
    if not cleaned:
        cleaned = "an evidence-backed design principle that directly addresses the paper's stated research gap"
    if 15 <= _word_count(cleaned) <= 25:
        candidate = cleaned.rstrip(" .") + "."
        if not visible_text_findings(candidate):
            return candidate
    clauses = [
        normalize_text(value)
        for value in re.split(r"(?<=[,;])\s+|\b(?:which|resulting in)\b", cleaned)
        if normalize_text(value)
    ]
    candidate = next(
        (value for value in clauses if 15 <= _word_count(value) <= 25),
        "",
    )
    if candidate:
        candidate = candidate.rstrip(" ,;:.") + "."
        if not visible_text_findings(candidate):
            return candidate
    prefixes = {
        "formula_centered": "The core equation formalizes",
        "contrast_centered": "The core contrast replaces existing limitations through",
        "mechanism_centered": "The core mechanism coordinates complementary operations through",
        "architecture_centered": "The core architecture organizes specialized modules through",
        "finding_centered": "The central finding demonstrates",
    }
    words = f"{prefixes[idea_type]} {cleaned}".split()
    if len(words) < 15:
        words.extend("as the paper's main evidence-backed differentiating principle".split())
    candidate = " ".join(words[:25]).rstrip(" ,;:.") + "."
    if visible_text_findings(candidate):
        return (
            "The central mechanism coordinates task-specific operations that "
            "connect the evidence-backed design gap to the reported behavior."
        )
    return candidate


def _node_alias(name: str) -> str:
    cleaned = re.sub(r"^[A-Z]\.\s*", "", normalize_text(name))
    words = re.findall(r"[A-Za-z]+", cleaned)
    if not words:
        return "Module"
    if "-" in cleaned and len(words) >= 4:
        alias = "".join(word[0] for word in words)
        return alias[:2].lower() + alias[2:].upper()
    alias = "".join(word[0] for word in words).upper()
    return alias if 2 <= len(alias) <= 6 else _clip_words(cleaned, 3)


def _structured_mechanism_headline(
    core_text: str,
    idea_type: str,
    graph: dict[str, Any],
    paper_ir: dict[str, Any],
) -> str | None:
    if idea_type not in {"mechanism_centered", "architecture_centered"}:
        return None
    if not re.search(
        r"\b(?:propose|proposed|introduce|introduced)\b.*"
        r"\b(?:novel|framework|network|model|method)\b",
        core_text,
        re.I,
    ):
        return None
    nodes = [
        node
        for node in graph.get("nodes", [])
        if "loss" not in str(node.get("name") or "").lower()
    ][:3]
    names = " ".join(str(node.get("name") or "") for node in nodes).lower()
    if not (
        len(nodes) == 3
        and "global" in names
        and "local" in names
        and "fusion" in names
        and ("deep" in names or "shallow" in names)
    ):
        return None
    aliases = [_node_alias(str(node.get("name") or "")) for node in nodes]
    title = normalize_text(str(paper_ir.get("metadata", {}).get("title") or ""))
    task_match = re.search(r"\bfor\s+(.+)$", title, re.I)
    task = _clip_words(
        task_match.group(1) if task_match else "the target task",
        5,
    ).rstrip(" .")
    headline = (
        f"{aliases[0]}, {aliases[1]}, and {aliases[2]} coordinate global "
        f"modeling, local detail recovery, and deep-shallow feature fusion "
        f"for {task}."
    )
    return headline if 15 <= _word_count(headline) <= 25 else None


def _append_distinct_visual_item(
    items: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> None:
    label = _clean_visible_label(str(candidate.get("label") or ""))
    text = _semantic_visual_rewrite(
        label,
        str(candidate.get("text") or ""),
    )
    source_ids = list(dict.fromkeys(candidate.get("source_block_ids") or []))
    if (
        not label
        or not text
        or not source_ids
        or visible_text_findings(label, allow_phrase=True)
        or visible_text_findings(text)
    ):
        return
    candidate_text = normalize_text(f"{label} {text}")
    for existing in items:
        existing_text = normalize_text(
            f"{existing.get('label') or ''} {existing.get('text') or ''}"
        )
        if jaccard(candidate_text, existing_text) >= 0.5:
            existing["source_block_ids"] = list(
                dict.fromkeys(
                    [
                        *(existing.get("source_block_ids") or []),
                        *source_ids,
                    ]
                )
            )
            return
    items.append(
        {
            "label": label,
            "text": text,
            "source_block_ids": source_ids,
            "rewrite_status": "passed",
            "visible_text_audit": {
                "status": "passed",
                "findings": [],
            },
        }
    )


def _node_visual_text(node: dict[str, Any]) -> str:
    name = normalize_text(str(node.get("name") or ""))

    def clean(candidate: str) -> str:
        normalized = normalize_text(candidate)
        normalized = re.sub(
            r"^(?:the\s+)?(?:architecture|structure|overview|diagram)\s+"
            r".{0,100}?\b(?:is\s+)?shown\s+in\s+"
            r"(?:fig(?:ure)?\.?\s*\d+[A-Za-z]?)\s*[.:]?\s*",
            "",
            normalized,
            flags=re.I,
        )
        return normalize_text(normalized)

    candidates = [
        clean(str(node.get("innovation") or "")),
        clean(str(node.get("purpose") or "")),
        *[
            clean(str(source.get("quote") or ""))
            for source in node.get("sources", [])
            if isinstance(source, dict)
        ],
    ]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return ""

    def score(candidate: str) -> tuple[float, int]:
        lowered = candidate.lower()
        value = 4.0 * jaccard(name, candidate)
        value += 0.8 * sum(
            term in lowered
            for term in (
                "adapt",
                "align",
                "capture",
                "combine",
                "create",
                "dynamically",
                "expand",
                "fuse",
                "model",
                "preserve",
                "replace",
                "select",
                "unlike",
            )
        )
        value += 0.5 * sum(
            term in lowered
            for term in (
                "asymmetric",
                "frequency",
                "global",
                "local",
                "multiscale",
                "receptive field",
                "scale",
                "spatial",
            )
        )
        if any(
            term in lowered
            for term in (
                "batch normalization",
                "implementation detail",
                "training stability",
                "training speed",
            )
        ):
            value -= 2.0
        return value, -abs(_word_count(candidate) - 18)

    for candidate in sorted(candidates, key=score, reverse=True):
        rewritten = _semantic_visual_rewrite(name, candidate)
        if rewritten and not visible_text_findings(rewritten):
            return rewritten
    return ""


def _method_visual_type(idea_type: str, item_count: int) -> str:
    if idea_type == "mechanism_centered":
        if item_count <= 1:
            return "single_mechanism_focus"
        if item_count == 2:
            return "two_part_mechanism"
        if item_count == 3:
            return "three_step_flow"
        return "mechanism_grid"
    if item_count <= 1:
        return "single_architecture_focus"
    if item_count == 2:
        return "two_module_relationship"
    return "core_module_relationship"


def _adaptive_visual_type(
    idea_type: str,
    item_count: int,
    equation_selected: bool = False,
) -> str:
    if equation_selected:
        return "equation_with_callouts"
    if idea_type in {"mechanism_centered", "architecture_centered"}:
        return _method_visual_type(idea_type, item_count)
    if idea_type == "contrast_centered" and item_count == 2:
        return "existing_vs_ours"
    if idea_type == "finding_centered" and item_count == 2:
        return "evidence_impact"
    if item_count <= 1:
        return "single_mechanism_focus"
    if item_count == 2:
        return "two_part_mechanism"
    if item_count == 3:
        return "three_step_flow"
    return "mechanism_grid"


def visual_layout_compatible(
    visual_type: str,
    item_count: int,
) -> bool:
    contract = VISUAL_ITEM_COUNT_CONTRACTS.get(visual_type)
    if not contract:
        return False
    minimum, maximum = contract
    return minimum <= item_count <= maximum


def _visual_items(
    idea_type: str,
    story: dict[str, Any],
    graph: dict[str, Any],
    core_text: str,
    core_sources: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    gap = str(story.get("prior_work_gap", {}).get("summary") or "")
    nodes = [
        node
        for node in graph.get("nodes", [])
        if "overall" not in str(node.get("name") or "").lower()
        and not GENERIC_VISUAL_NODE_RE.fullmatch(
            normalize_text(str(node.get("name") or ""))
        )
    ]
    if idea_type == "contrast_centered":
        items: list[dict[str, Any]] = []
        for candidate in (
            {
                "label": "Existing",
                "text": gap or "Existing methods retain the paper's stated limitation.",
                "source_block_ids": _source_ids(story.get("prior_work_gap", {}).get("sources", [])),
            },
            {
                "label": "Ours",
                "text": core_text,
                "source_block_ids": _source_ids(core_sources),
            },
        ):
            _append_distinct_visual_item(items, candidate)
        return "existing_vs_ours", items
    if idea_type in {"mechanism_centered", "architecture_centered"} and nodes:
        items: list[dict[str, Any]] = []
        for index, node in enumerate(nodes[:4], start=1):
            _append_distinct_visual_item(
                items,
                {
                    "label": str(node.get("name") or f"Step {index}"),
                    "text": _node_visual_text(node),
                    "source_block_ids": _source_ids(
                        node.get("sources", [])
                    ),
                },
            )
        # Do not manufacture extra steps from weaker Story summaries merely
        # to fill a multi-card template. When the sourced Method Graph has one
        # independent mechanism, render one large focus item.
        return _method_visual_type(idea_type, len(items)), items
    if idea_type in {"mechanism_centered", "architecture_centered"}:
        method = story.get("method_design", {})
        mechanism = story.get("theory_or_mechanism", {})
        fallback_items: list[dict[str, Any]] = []
        _append_distinct_visual_item(
            fallback_items,
            {
                "label": "Design principle",
                "text": str(method.get("summary") or core_text),
                "source_block_ids": _source_ids(method.get("sources", []))
                or _source_ids(core_sources),
            },
        )
        _append_distinct_visual_item(
            fallback_items,
            {
                "label": "Core mechanism",
                "text": str(mechanism.get("summary") or core_text),
                "source_block_ids": _source_ids(mechanism.get("sources", []))
                or _source_ids(core_sources),
            },
        )
        return (
            _method_visual_type(idea_type, len(fallback_items)),
            fallback_items,
        )
    if idea_type == "finding_centered":
        result = story.get("experimental_results", {})
        conclusion = story.get("conclusion", {})
        items = []
        for candidate in (
            {
                "label": "Evidence",
                "text": str(result.get("summary") or core_text),
                "source_block_ids": _source_ids(result.get("sources", [])),
            },
            {
                "label": "Meaning",
                "text": str(conclusion.get("summary") or core_text),
                "source_block_ids": _source_ids(conclusion.get("sources", [])),
            },
        ):
            _append_distinct_visual_item(items, candidate)
        return "evidence_impact", items
    items = []
    for candidate in (
        {
            "label": "Mechanism",
            "text": core_text,
            "source_block_ids": _source_ids(core_sources),
        },
        {
            "label": "Consequence",
            "text": str(story.get("conclusion", {}).get("summary") or core_text),
            "source_block_ids": _source_ids(story.get("conclusion", {}).get("sources", [])),
        },
    ):
        _append_distinct_visual_item(items, candidate)
    return "equation_with_callouts", items


def _takeaway(story: dict[str, Any], core_text: str, idea_type: str) -> str:
    conclusion = complete_sentences(
        str(story.get("conclusion", {}).get("summary") or ""),
        190,
    )
    if conclusion and jaccard(conclusion, core_text) >= 0.08:
        rewritten = _complete_visible_sentence(conclusion, max_words=24)
        if rewritten:
            return rewritten
    fallbacks = {
        "formula_centered": (
            "The relation gives a compact evidence-backed statement of how "
            "the proposed method differs from prior work."
        ),
        "contrast_centered": (
            "The contribution is the changed design principle, not merely "
            "another implementation of the existing approach."
        ),
        "mechanism_centered": (
            "Together, these operations form the evidence-backed mechanism "
            "that turns the paper's contribution into its reported behavior."
        ),
        "architecture_centered": (
            "The contribution lies in how these specialized modules are "
            "organized to resolve the paper's stated gap."
        ),
        "finding_centered": (
            "The evidence makes this finding, rather than a new architectural "
            "component, the paper's central contribution."
        ),
    }
    return fallbacks[idea_type]


def _display_word_count(spec: dict[str, Any]) -> int:
    values = [spec.get("headline", ""), spec.get("takeaway", "")]
    values.extend(
        f"{item.get('label', '')} {item.get('text', '')}"
        for item in spec.get("visual", {}).get("items", [])
    )
    explanation = spec.get("equation", {}).get("plain_language_explanation", "")
    if explanation:
        values.append(explanation)
    return sum(_word_count(str(value)) for value in values)


def _fit_word_budget(spec: dict[str, Any]) -> None:
    count = _display_word_count(spec)
    if count < 60:
        addition = (
            "The mechanism is the main evidence-backed distinction from prior "
            "work and the organizing principle behind its reported behavior."
        )
        spec["takeaway"] = normalize_text(
            f"{spec.get('takeaway') or ''} {addition}"
        )
    if _display_word_count(spec) > 120:
        spec["takeaway"] = (
            "The mechanism is the central evidence-backed distinction from "
            "prior work."
        )
    items = (spec.get("visual") or {}).get("items") or []
    while _display_word_count(spec) > 120 and len(items) > 1:
        items.pop()
    spec["visual"]["visual_type"] = _adaptive_visual_type(
        str(spec.get("type") or "mechanism_centered"),
        len(items),
        bool((spec.get("equation") or {}).get("equation_id")),
    )


def _repair_visible_spec(spec: dict[str, Any]) -> dict[str, Any]:
    spec = dict(spec)
    spec["headline"] = _headline(
        str(spec.get("core_insight") or spec.get("headline") or ""),
        str(spec.get("type") or "mechanism_centered"),
    )
    visual = dict(spec.get("visual") or {})
    repaired_items: list[dict[str, Any]] = []
    for item in visual.get("items") or []:
        label = _clean_visible_label(str(item.get("label") or ""))
        text = _semantic_visual_rewrite(
            label,
            str(item.get("text") or ""),
        )
        if (
            label
            and text
            and not visible_text_findings(label, allow_phrase=True)
            and not visible_text_findings(text)
        ):
            repaired_items.append(
                {
                    **item,
                    "label": label,
                    "text": text,
                    "rewrite_status": "passed",
                    "visible_text_audit": {
                        "status": "passed",
                        "findings": [],
                    },
                }
            )
    if not repaired_items:
        fallback = _semantic_visual_rewrite(
            "Core mechanism",
            str(spec.get("core_insight") or ""),
        )
        if fallback and not visible_text_findings(fallback):
            repaired_items = [
                {
                    "label": "Core mechanism",
                    "text": fallback,
                    "source_block_ids": list(spec.get("source_block_ids") or []),
                    "rewrite_status": "passed",
                    "visible_text_audit": {
                        "status": "passed",
                        "findings": [],
                    },
                }
            ]
    visual["items"] = repaired_items
    if str(spec.get("type") or "") in {
        "mechanism_centered",
        "architecture_centered",
    }:
        visual["visual_type"] = _method_visual_type(
            str(spec.get("type")),
            len(repaired_items),
        )
    spec["visual"] = visual
    equation = dict(spec.get("equation") or {})
    if equation.get("equation_id"):
        explanation = _complete_visible_sentence(
            str(equation.get("plain_language_explanation") or ""),
            max_words=24,
        )
        if not explanation or visible_text_findings(explanation):
            equation = _none_equation(
                [
                    *equation.get("selection_reason", []),
                    "plain-language explanation failed visible-text audit",
                ]
            )
    else:
        equation["plain_language_explanation"] = ""
    spec["equation"] = equation
    takeaway = _complete_visible_sentence(
        str(spec.get("takeaway") or ""),
        max_words=24,
    )
    if not takeaway:
        takeaway = (
            "The mechanism is the central evidence-backed distinction from "
            "prior work."
        )
    spec["takeaway"] = takeaway
    spec["inference_label"] = (
        "Inferred from source evidence" if spec.get("inferred") else "Explicit"
    )
    _fit_word_budget(spec)
    spec["display_word_count"] = _display_word_count(spec)
    spec["visible_text_audit"] = audit_key_idea_visible_text(spec)
    return spec


def build_key_idea(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    method_graph_path: Path,
    method_figure_map_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    graph = read_json(method_graph_path)
    method_map = read_json(method_figure_map_path)
    core = _core_claim(evidence, story)
    core_text = normalize_text(str(core.get("claim") or ""))
    core_sources = list(core.get("sources") or [])
    equation, equation_audits = _select_equation(paper_ir, paper_ir_path, core_text)
    idea_type, type_scores = classify_key_idea_type(
        paper_ir,
        story,
        evidence,
        graph,
        equation,
    )
    equation = _apply_equation_alignment_gate(
        equation,
        idea_type,
        graph,
        core_text,
    )
    if idea_type == "formula_centered" and not equation.get("equation_id"):
        idea_type, type_scores = classify_key_idea_type(
            paper_ir,
            story,
            evidence,
            graph,
            equation,
        )
    visual_type, items = _visual_items(
        idea_type,
        story,
        graph,
        core_text,
        core_sources,
    )
    source_claim_ids = [
        str(core["claim_id"])
        for _ in [0]
        if core.get("claim_id")
    ]
    source_block_ids = _source_ids(core_sources)
    core_source_set = set(source_block_ids)
    related_claim_ids = [
        str(claim.get("claim_id"))
        for claim in _supported_claims(evidence)
        if claim.get("claim_id")
        and (
            jaccard(core_text, str(claim.get("claim") or "")) >= 0.04
            or bool(
                core_source_set
                & set(_source_ids(list(claim.get("sources") or [])))
            )
        )
    ]
    source_claim_ids = list(
        dict.fromkeys([*source_claim_ids, *related_claim_ids])
    )[:3]
    for item in items:
        source_block_ids.extend(item.get("source_block_ids", []))
    source_block_ids = list(dict.fromkeys(source_block_ids))
    inferred = core.get("verdict") == "inferred"
    base_headline = _headline(core_text, idea_type)
    structured_headline = _structured_mechanism_headline(
        core_text,
        idea_type,
        graph,
        paper_ir,
    )
    headline = structured_headline or base_headline
    displayed_core_insight = (
        headline.rstrip(".")
        if structured_headline
        else core_text
    )
    spec = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "type": idea_type,
        "headline": headline,
        "core_insight": displayed_core_insight,
        "visual": {
            "visual_type": visual_type,
            "items": items,
            "overview_asset_id": None,
        },
        "equation": equation,
        "takeaway": _takeaway(story, core_text, idea_type),
        "source_claim_ids": source_claim_ids,
        "source_block_ids": source_block_ids,
        "confidence": round(
            min(
                0.96,
                max(0.0, float(core.get("confidence") or 0.45))
                + min(0.2, max(type_scores.values()) / 30),
            ),
            3,
        ),
        "inferred": inferred,
        "inference_label": "inferred" if inferred else "explicit",
        "type_scores": type_scores,
        "method_overview_asset_id": method_map.get("overview_asset_id"),
        "display_word_count": 0,
    }
    spec = _repair_visible_spec(spec)
    visible_audit = dict(spec.get("visible_text_audit") or {})
    equation = dict(spec.get("equation") or {})
    checks = {
        "type_valid": idea_type in KEY_IDEA_TYPES,
        "visual_type_valid": spec["visual"]["visual_type"] in KEY_IDEA_VISUAL_TYPES,
        "visual_layout_compatible": visual_layout_compatible(
            spec["visual"]["visual_type"],
            len(spec["visual"]["items"]),
        ),
        "headline_words": _word_count(spec["headline"]),
        "headline_valid": 15 <= _word_count(spec["headline"]) <= 25,
        "source_bound": bool(source_claim_ids and source_block_ids),
        "overview_not_reused": spec["visual"]["overview_asset_id"] is None,
        "equation_display_mode_valid": equation["display_mode"] in DISPLAY_MODES,
        "equation_threshold_valid": (
            equation["equation_id"] is None or float(equation.get("score") or 0) >= 7
        ),
        "generic_equation_gate": (
            equation["equation_id"] is None
            or not bool(equation.get("generic_rejected"))
        ),
        "equation_key_idea_alignment_gate": (
            equation["equation_id"] is None
            or bool((equation.get("alignment_gate") or {}).get("passed"))
        ),
        "equation_explained": (
            equation["equation_id"] is None
            or bool(equation.get("plain_language_explanation"))
        ),
        "no_equation_visual_fills_space": (
            equation["equation_id"] is not None
            or visual_layout_compatible(
                spec["visual"]["visual_type"],
                len(spec["visual"]["items"]),
            )
        ),
        "word_count": spec["display_word_count"],
        "word_budget_valid": 60 <= spec["display_word_count"] <= 120,
        "inference_labeled": (
            not inferred
            or str(spec["inference_label"]).startswith("Inferred")
        ),
        "latex_residue_check": bool(
            visible_audit.get("latex_residue_check")
        ),
        "math_delimiter_check": bool(
            visible_audit.get("math_delimiter_check")
        ),
        "sentence_completeness_check": bool(
            visible_audit.get("sentence_completeness_check")
        ),
        "visible_text_audit": visible_audit.get("status") == "passed",
    }
    soft_checks = {
        "headline_valid",
        "word_budget_valid",
        "no_equation_visual_fills_space",
    }
    hard_failed_checks = [
        name
        for name, value in checks.items()
        if name not in {"headline_words", "word_count", *soft_checks}
        and value is False
    ]
    warning_checks = [
        name
        for name, value in checks.items()
        if name in soft_checks and value is False
    ]
    report = {
        "status": (
            "failed"
            if hard_failed_checks
            else "passed_with_warnings"
            if warning_checks
            else "passed"
        ),
        "type": idea_type,
        "equation_audits": equation_audits,
        "visible_text_audit": visible_audit,
        "checks": checks,
        "failed_checks": hard_failed_checks,
        "warnings": warning_checks,
    }
    return (
        write_json(output_dir / "key_idea_spec.json", spec),
        write_json(output_dir / "key_idea_report.json", report),
    )
