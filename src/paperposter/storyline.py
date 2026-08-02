from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import (
    complete_sentences,
    compact_text,
    jaccard,
    read_json,
    sentences,
    source_ref,
    token_set,
    write_json,
)

NODE_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "research_problem": {
        "sections": ("abstract", "introduction", "background"),
        "terms": (
            "problem",
            "challenge",
            "we study",
            "we investigate",
            "difficult",
            "critical task",
            "aiming to",
            "degraded input",
            "low-contrast",
            "thin vessel",
        ),
    },
    "motivation": {
        "sections": ("abstract", "introduction", "background"),
        "terms": (
            "important",
            "however",
            "demand",
            "motivat",
            "critical",
            "crucial",
            "significant attention",
            "blindness",
            "clinically",
            "diagnosis",
        ),
    },
    "prior_work_gap": {
        "sections": ("abstract", "introduction", "related work", "background"),
        "terms": (
            "existing",
            "previous",
            "prior",
            "limitation",
            "fail",
            "limited receptive",
            "insufficient global",
            "local detail",
            "global context",
            "independently",
            "overlook",
            "interdependency",
            "unable",
            "quadratic complexity",
            "computationally intensive",
            "long-range dependencies",
            "unidirectional",
        ),
    },
    "core_hypothesis": {
        "sections": ("introduction", "method", "approach"),
        "terms": (
            "hypoth",
            "conject",
            "we posit",
            "we expect",
            "complementary",
            "spatial and frequency",
            "local details",
            "global context",
            "information flow",
            "six directions",
            "could we",
            "we posit",
            "inspired by",
            "averaging",
            "weighted fusion",
        ),
    },
    "method_design": {
        "sections": ("method", "methodology", "approach", "framework", "model"),
        "terms": (
            "we propose",
            "our method",
            "framework",
            "architecture",
            "built upon",
            "encoder",
        ),
    },
    "theory_or_mechanism": {
        "sections": ("method", "methodology", "theory", "analysis"),
        "terms": (
            "mechanism",
            "theorem",
            "objective",
            "because",
            "in parallel",
            "selective",
            "frequency",
            "attention",
            "boundary",
            "variance",
            "averaging",
            "weighted fusion",
            "fused expert",
            "equivalent",
        ),
    },
    "experimental_design": {
        "sections": ("experiment", "experimental setup", "evaluation"),
        "terms": (
            "dataset",
            "baseline",
            "metric",
            "implementation",
            "evaluation",
        ),
    },
    "experimental_results": {
        "sections": ("result", "experiment", "evaluation"),
        "terms": (
            "outperform",
            "improve",
            "achieve",
            "highest",
            "result",
            "compared",
        ),
    },
    "conclusion": {
        "sections": ("conclusion", "discussion"),
        "terms": (
            "in conclusion",
            "we demonstrate",
            "we show",
            "this paper proposes",
            "results show",
            "in this paper, we propose",
            "experimental results demonstrate",
        ),
    },
    "limitations": {
        "sections": ("limitation", "discussion", "conclusion"),
        "terms": (
            "limitation",
            "future work",
            "cannot",
            "remains",
            "may limit",
            "small public benchmarks",
            "external validation",
            "clinical evidence",
            "computational complexity",
            "confidence intervals",
            "statistical significance",
        ),
    },
}
TOP_LEVEL_HEADING_RE = re.compile(
    r"^\s*(?:\d+|[IVX][IVXLCDM]*)[.)]\s+\S",
    re.I,
)
METHOD_STORY_NODES = {
    "core_hypothesis",
    "method_design",
    "theory_or_mechanism",
}
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


def _parent_headings(paper_ir: dict[str, Any]) -> dict[str, str]:
    current = ""
    parents: dict[str, str] = {}
    for block in paper_ir.get("blocks", []):
        text = str(block.get("text") or "")
        if (
            block.get("type") == "heading"
            and TOP_LEVEL_HEADING_RE.match(text)
        ):
            current = text
        parents[str(block.get("id") or "")] = current
    return parents


def _choose_sentence(block: dict[str, Any], terms: tuple[str, ...]) -> str:
    block_sentences = sentences(block.get("text", ""))
    def score(sentence: str) -> float:
        lowered = sentence.lower()
        term_hits = sum(term.lower() in lowered for term in terms)
        outcome_hits = sum(
            term in lowered
            for term in ("achiev", "outperform", "highest", "improve", "superior")
        )
        citation_count = len(re.findall(r"\[\s*\d+", sentence))
        length_penalty = max(0.0, (len(sentence) - 300) / 120)
        return term_hits * 3.0 + outcome_hits * 1.5 - citation_count * 0.8 - length_penalty

    ranked = sorted(block_sentences, key=score, reverse=True)
    if ranked:
        return complete_sentences(ranked[0], 340)
    return complete_sentences(block.get("text", ""), 340)


def _extract_node(
    paper_ir: dict[str, Any],
    node_name: str,
    rule: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    scored: list[tuple[float, bool, dict[str, Any]]] = []
    parent_headings = _parent_headings(paper_ir)
    title_tokens = {
        token
        for token in token_set(
            str(paper_ir.get("metadata", {}).get("title") or "")
        )
        if token not in TITLE_STOPWORDS
    }
    for block in paper_ir.get("blocks", []):
        if block.get("type") in {"title", "heading", "caption"}:
            continue
        section = (
            f"{block.get('section_title') or ''} "
            f"{block.get('section_id') or ''} "
            f"{parent_headings.get(str(block.get('id') or ''), '')}"
        ).lower()
        text = str(block.get("text") or "").lower()
        section_match = any(term.lower() in section for term in rule["sections"])
        parent = parent_headings.get(str(block.get("id") or ""), "")
        named_method_section = (
            node_name in METHOD_STORY_NODES
            and bool(title_tokens & token_set(parent))
            and not any(
                term in parent.lower()
                for term in (
                    "abstract",
                    "introduction",
                    "related work",
                    "experiment",
                    "result",
                    "discussion",
                    "conclusion",
                    "limitation",
                )
            )
        )
        section_match = section_match or named_method_section
        term_hits = sum(term.lower() in text for term in rule["terms"])
        if not term_hits:
            continue
        score = term_hits * 3.0 + (2.0 if section_match else 0.0)
        if block.get("type") == "abstract":
            score += 0.5
        score -= min(4.0, text.count("=") * 0.8)
        if node_name == "limitations":
            # Page-layout extraction can splice a nearby results table into the
            # first limitations paragraph. Prefer prose over number-dense text.
            score -= min(9.0, len(re.findall(r"\d", text)) * 0.2)
        if node_name == "prior_work_gap":
            if any(term in text for term in ("however", "suffer", "fail", "challenge")):
                score += 2.5
            if any(
                term in text
                for term in ("we propose", "our proposed", "overcomes", "to address")
            ):
                score -= 4.0
        scored.append((score, section_match, block))
    if node_name == "limitations" and not any(
        section_match for _, section_match, _ in scored
    ):
        return {"summary": "", "status": "not_found", "sources": [], "confidence": 0.0}
    if any(section_match for _, section_match, _ in scored):
        scored = [item for item in scored if item[1]]
    scored.sort(key=lambda item: (-item[0], int(item[2].get("page") or 1)))
    if not scored:
        return {"summary": "", "status": "not_found", "sources": [], "confidence": 0.0}

    selected = [block for _, _, block in scored[:1]]
    summaries = [_choose_sentence(block, rule["terms"]) for block in selected]
    selected_text = " ".join(str(block.get("text") or "") for block in selected).lower()
    explicit_hypothesis = any(
        term in selected_text
        for term in ("hypoth", "conject", "we posit", "we expect")
    )
    status = (
        "inferred"
        if node_name == "core_hypothesis" and not explicit_hypothesis
        else "explicit"
    )
    return {
        "summary": complete_sentences(" ".join(dict.fromkeys(summaries)), 520),
        "status": status,
        "sources": [source_ref(block) for block in selected],
        "confidence": 0.68 if len(selected) == 1 else 0.76,
    }


def _extract_claims(paper_ir: dict[str, Any]) -> list[dict[str, Any]]:
    patterns = (
        "we propose",
        "we introduce",
        "we design",
        "we demonstrate",
        "we show",
        "outperform",
        "achieve",
        "highest",
        "improve",
    )
    candidates: list[tuple[float, dict[str, Any], str]] = []
    for block in paper_ir.get("blocks", []):
        if block.get("type") in {"title", "heading", "caption"}:
            continue
        section = str(block.get("section_id") or "").lower()
        if "reference" in section:
            continue
        for sentence in sentences(block.get("text", "")):
            lowered = sentence.lower()
            hits = sum(pattern in lowered for pattern in patterns)
            if len(sentence) < 45 or not hits:
                continue
            score = float(hits)
            if any(term in section for term in ("result", "conclusion", "abstract", "introduction")):
                score += 1.0
            if re.search(r"\d+\.\d+|%", sentence):
                score += 1.0
            candidates.append((score, block, sentence))
    candidates.sort(key=lambda item: (-item[0], int(item[1].get("page") or 1)))

    ranked_candidates: list[tuple[float, dict[str, Any], str]] = []
    contribution_candidates: list[tuple[float, dict[str, Any], str]] = []
    result_candidates: list[tuple[float, dict[str, Any], str]] = []
    for candidate in candidates:
        _, _, sentence = candidate
        if re.search(r"\d|outperform|achieve|improve|highest", sentence, re.I):
            result_candidates.append(candidate)
        else:
            if all(
                jaccard(sentence, prior[2]) < 0.25
                for prior in contribution_candidates
            ):
                contribution_candidates.append(candidate)
    ranked_candidates.extend(contribution_candidates[:3])
    ranked_candidates.extend(result_candidates[:5])

    claims: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, block, sentence in ranked_candidates:
        sentence = re.sub(r"^[•·\-]\s*", "", sentence).strip()
        normalized = re.sub(r"\W+", " ", sentence.lower()).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        claims.append(
            {
                "id": f"claim-{len(claims) + 1}",
                "text": complete_sentences(sentence, 420),
                "type": (
                    "result"
                    if re.search(r"\d|outperform|achieve|improve|highest", sentence, re.I)
                    else "contribution"
                ),
                "sources": [source_ref(block)],
                "status": "extracted",
            }
        )
        if len(claims) >= 8:
            break
    return claims


def extract_story(paper_ir_path: Path, output_dir: Path) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story: dict[str, Any] = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "generator": "heuristic-offline",
    }
    for node_name, rule in NODE_RULES.items():
        story[node_name] = _extract_node(paper_ir, node_name, rule)
    story["claims"] = _extract_claims(paper_ir)
    report = {
        "status": "passed_with_warnings",
        "generator": "heuristic-offline",
        "nodes_found": sum(story[field]["status"] != "not_found" for field in NODE_RULES),
        "claims": len(story["claims"]),
        "warnings": [
            "The offline extractor is a deterministic fallback.",
            "A model-guided agent should refine the story using the paper-storyline skill before final submission.",
        ],
    }
    return (
        write_json(output_dir / "paper_story.json", story),
        write_json(output_dir / "storyline_report.json", report),
    )
