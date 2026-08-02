from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from .common import (
    STORY_FIELDS,
    find_numbers,
    jaccard,
    normalize_text,
    read_json,
    complete_sentences,
    write_json,
)
from .key_idea import visible_text_findings
from .motivation_contributions import clean_visible_text


def _neutral_story_text(value: str) -> str:
    text = clean_visible_text(value)
    dataset_eval = re.match(
        r"^\s*(.+?)\s+are\s+used\s+in\s+this\s+paper\s+for\s+evaluating\s+"
        r"the\s+performance\s+of\s+our\s+methods?\s+in\s+comparison\s+"
        r"against\s+the\s+state-of-the-arts?\.?\s*$",
        text,
        re.I,
    )
    if dataset_eval:
        return normalize_text(
            f"Evaluation uses {dataset_eval.group(1)} to compare the "
            "method against state-of-the-art baselines."
        )
    following_utilize = re.match(
        r"^\s*following\s+in,?\s*we\s+utili[sz]e\s+(.+?)\s+for\s+"
        r"training\s+and\s+(.+?)\s+for\s+testing\.?\s*$",
        text,
        re.I,
    )
    if following_utilize:
        return normalize_text(
            f"Training uses {following_utilize.group(1)} and testing uses "
            f"{following_utilize.group(2)}."
        )
    dataset_metric = re.match(
        r"^\s*on\s+the\s+(.+?)\s+dataset,?\s*we\s+use\s+(.+?)\s+as\s+"
        r"the\s+sole\s+performance\s+metric\.?\s*$",
        text,
        re.I,
    )
    if dataset_metric:
        return normalize_text(
            f"Evaluation uses {dataset_metric.group(2)} as the sole "
            f"performance metric on the {dataset_metric.group(1)} dataset."
        )
    adopt = re.match(
        r"^\s*(?:here\s+)?we\s+adopt\s+(.+?)\.?\s*$",
        text,
        re.I,
    )
    if adopt:
        return normalize_text(f"The method uses {adopt.group(1)}.")
    text = re.sub(
        r"^\s*following\s+the\s+training\s+settings?\s*,?\s*"
        r"we\s+(?:employ(?:ed)?|use(?:d)?|adopt(?:ed)?)\s+",
        "Training uses ",
        text,
        flags=re.I,
    )
    evaluation = re.match(
        r"^\s*we\s+evaluate\s+on\s+(.+?)\s+using\s+(.+)$",
        text,
        re.I,
    )
    if evaluation:
        return normalize_text(
            f"Evaluation uses {evaluation.group(1)} with "
            f"{evaluation.group(2)}"
        )
    text = re.sub(
        r"^\s*we\s+(?:employ(?:ed)?|use(?:d)?|utili[sz]e(?:d)?|"
        r"adopt(?:ed)?)\s+",
        "The study uses ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*we\s+(?:perform(?:ed)?|evaluate(?:d)?|train(?:ed)?)\s+",
        "The study performs ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*we\s+(?:fix(?:ed)?|set|configure(?:d)?)\s+",
        "The setup fixes ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*(?:our\s+investigation|this\s+paper)\s+"
        r"(?:uses?|employs?|adopts?|evaluates?|investigates?|approaches?)\s+",
        "The study uses ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*following\s+the\s+training\s+settings?\s*(?:in)?\s*",
        "Training follows ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*training\s+follows\s*,?\s*we\s+"
        r"(?:employ(?:ed)?|use(?:d)?|adopt(?:ed)?)\s+",
        "Training uses ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*this\s+(?:empowers?|enables?)\s+it\s+to\s+",
        "The architecture can ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r",?\s+(?:as\s+)?illustrated\s+in\s*\.?\s*$|"
        r"\s+which\s+is\s+called\s*\.?\s*$",
        "",
        text,
        flags=re.I,
    )
    return normalize_text(text)


def _neutralize_method_visual(
    method_visual: dict[str, Any],
) -> dict[str, Any]:
    result = dict(method_visual)
    result["callouts"] = [
        {
            **item,
            "description": _neutral_story_text(
                str(item.get("description") or "")
            ),
        }
        for item in result.get("callouts", [])
    ]
    storyboard_items: list[dict[str, Any]] = []
    for original in result.get("storyboard_items", []):
        item = dict(original)
        item["description"] = _neutral_story_text(
            str(item.get("description") or "")
        )
        flow = dict(item.get("flow") or {})
        flow["stages"] = [
            {
                **stage,
                "text": _neutral_story_text(str(stage.get("text") or "")),
            }
            for stage in flow.get("stages", [])
        ]
        item["flow"] = flow
        storyboard_items.append(item)
    result["storyboard_items"] = storyboard_items
    result["experiment_strip"] = [
        {
            **item,
            "text": _neutral_story_text(str(item.get("text") or "")),
        }
        for item in result.get("experiment_strip", [])
    ]
    return result


def _clean_header_value(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<sup\b[^>]*>.*?</sup>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_text(text)


def _safe_motivation_items(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    visible: list[dict[str, Any]] = []
    omitted: list[str] = []
    for item in items:
        item = _sanitize_visible_panel_value(dict(item))
        text = normalize_text(str(item.get("visible_text") or ""))
        if text and not visible_text_findings(text):
            visible.append(item)
        else:
            omitted.append(str(item.get("id") or "unknown"))
    return visible, omitted


def _node(story: dict[str, Any], name: str, limit: int = 260) -> dict[str, Any]:
    value = story.get(name, {})
    return {
        # Panels may omit sentences but must never show a source sentence cut
        # in half. The complete-sentence selector is also compact-level aware.
        "text": complete_sentences(
            _neutral_story_text(str(value.get("summary", ""))),
            limit,
        ),
        "status": value.get("status", "not_found"),
        "sources": value.get("sources", []),
    }


def _compact_display_text(value: str, limit: int) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    complete = complete_sentences(text, limit)
    if complete and len(complete) <= limit:
        return complete
    first_sentence = complete_sentences(text, max(len(text), limit))
    clauses = [
        normalize_text(clause)
        for clause in re.split(r"(?<=[,;:])\s+", first_sentence or text)
        if normalize_text(clause)
    ]
    selected: list[str] = []
    for clause in clauses:
        candidate = " ".join([*selected, clause])
        if len(candidate) > limit:
            break
        selected.append(clause)
    compact = " ".join(selected).rstrip(" ,;:")
    if len(compact) >= 40:
        return compact if compact.endswith((".", "!", "?")) else compact + "."
    words: list[str] = []
    for word in text.split():
        candidate = " ".join([*words, word])
        if len(candidate) > limit - 1:
            break
        words.append(word)
    compact = " ".join(words).rstrip(" ,;:")
    return compact + "." if compact else ""


VISIBLE_PANEL_TEXT_KEYS = {
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
PHRASE_VISIBLE_KEYS = {
    "label",
    "value",
    "title",
    "short_title",
    "context",
    "primary_value",
}
VISIBLE_PANEL_SKIP_KEYS = {
    "sources",
    "selection_reason",
    "subfigure_semantics",
    "source_headers",
    "rewrite_attempts",
    "visible_text_audit",
    "gate_results",
    "final_gate_results",
    "audit",
}


def _trim_dangling_visible_text(text: str) -> str:
    text = normalize_text(text).rstrip(" ,;:")
    for _ in range(4):
        trimmed = re.sub(
            r"\b(?:and|or|through|while|with|from|to|of|for|the|a|an|"
            r"where|which|that|by|in|on|as|including|consists|contains)"
            r"\s*[,:;.-]*$",
            "",
            text,
            flags=re.I,
        ).rstrip(" ,;:")
        if trimmed == text:
            break
        text = trimmed
    return text


def _looks_like_short_heading(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text)
    if not (2 <= len(words) <= 5):
        return False
    if re.search(
        r"\b(?:is|are|uses?|combines?|contains?|supports?|shows?|"
        r"provides?|requires?|enables?)\b",
        text,
        re.I,
    ):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9()&/ -]+\.?", text.strip()))


def _complete_short_heading(text: str) -> str:
    heading = normalize_text(text).strip(" .")
    lower = heading.lower()
    if re.search(r"\b(?:dataset|datasets|setting|settings|training|testing)\b", lower):
        return f"The experimental design covers {lower}."
    if re.search(r"\b(?:metric|metrics|evaluation|result|results)\b", lower):
        return f"The evaluation summary covers {lower}."
    return f"The poster section covers {lower}."


def _repair_leading_visible_fragment(text: str) -> str:
    repaired = normalize_text(text)
    repaired = re.sub(
        r"^\s*and\s+(?:most\s+importantly,\s*)?",
        "",
        repaired,
        flags=re.I,
    )
    repaired = re.sub(
        r"\s+and,\s+for\s+the\s+first\s+time\b.*$",
        "",
        repaired,
        flags=re.I,
    )
    repaired = normalize_text(repaired).strip(" ,;:.")
    if not repaired:
        return text
    if re.fullmatch(
        r"(?:the\s+)?[A-Za-z0-9()&/ -]{3,90}\s+"
        r"(?:module|network|architecture|branch|block|layer|framework|"
        r"decoder|encoder|attention|fusion|design)",
        repaired,
        re.I,
    ):
        subject = repaired
        if not subject.lower().startswith("the "):
            subject = f"The {subject}"
        return f"{subject} is the central method component."
    return repaired


def _sanitize_panel_text(value: str, *, allow_phrase: bool = False) -> str:
    raw = normalize_text(html.unescape(str(value or "")))
    if allow_phrase and re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)\s?%?", raw
    ):
        return raw
    text = _neutral_story_text(value)
    if re.fullmatch(
        r"(?:stated\s+another\s+way|in\s+other\s+words)\.?",
        text,
        re.I,
    ):
        text = (
            "The source evidence supports the central design choice as the "
            "key mechanism."
        )
    text = re.sub(r"[\uFFFD]+|鈥\?|��", " ", text)
    text = re.sub(r"(?:…|\.\.\.)\s*\.?$", "", text)
    text = re.sub(r"\bFrom,\s+", "", text, flags=re.I)
    text = re.sub(
        r"\bthe\s+(.{1,60}?)\s+studied\s+in\s+this\s+article\b",
        r"the \1",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s*_\s*", "-", text)
    text = re.sub(r"\$([^$]{1,80})\$", r"\1", text)
    text = re.sub(r"\\\(([^)]{1,80})\\\)", r"\1", text)
    text = re.sub(r"\\\[([^\]]{1,120})\\\]", r"\1", text)
    text = re.sub(r"[{}_^$]+", " ", text)
    if not allow_phrase and _looks_like_short_heading(text):
        text = _complete_short_heading(text)
    if not allow_phrase and re.match(r"^\s*and\b", text, re.I):
        text = _repair_leading_visible_fragment(text)
    text = re.sub(
        r"^(?:this\s+(mechanism|relation|architecture|module|design|"
        r"framework|network|result|finding|setup|stage|operation))\b",
        r"The \1",
        text,
        flags=re.I,
    )
    text = re.sub(r"^This\s+", "The ", text, flags=re.I)
    text = re.sub(r"^These\s+", "The selected ", text, flags=re.I)
    text = re.sub(r"^(?:It|They)\s+", "The method ", text, flags=re.I)
    text = _trim_dangling_visible_text(text)
    if not allow_phrase:
        complete = complete_sentences(text, max(len(text), 260))
        if complete:
            text = complete
        text = _trim_dangling_visible_text(text)
    text = normalize_text(text)
    if re.fullmatch(
        r"(?:stated\s+another\s+way|in\s+other\s+words)\.?",
        text,
        re.I,
    ):
        text = (
            "The source evidence supports the central design choice as the "
            "key mechanism."
        )
    if text and not allow_phrase and not text.endswith((".", "!", "?")):
        text += "."
    return text


def _sanitize_visible_panel_value(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            child_key: (
                child
                if child_key in VISIBLE_PANEL_SKIP_KEYS
                else _sanitize_visible_panel_value(child, child_key)
            )
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_visible_panel_value(item, key) for item in value]
    if isinstance(value, str) and key in VISIBLE_PANEL_TEXT_KEYS:
        allow_phrase = key in PHRASE_VISIBLE_KEYS
        cleaned = _sanitize_panel_text(value, allow_phrase=allow_phrase)
        if cleaned and not visible_text_findings(cleaned, allow_phrase=allow_phrase):
            return cleaned
        compact = _compact_display_text(cleaned, 180 if not allow_phrase else 60)
        return compact or cleaned
    return value


def _supported_claims(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in evidence.get("claims", [])
        if item.get("verdict") in {"supported", "partially_supported"}
    ]


def _distinct_nodes(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    distinct: list[dict[str, Any]] = []
    for item in items:
        text = str(item.get("text") or "")
        if not text:
            continue
        if any(
            jaccard(text, str(prior.get("text") or "")) >= 0.78
            for prior in distinct
        ):
            continue
        distinct.append(item)
    return distinct


def _source_block_ids(sources: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(source.get("block_id") or "")
            for source in sources
            if str(source.get("block_id") or "")
        )
    )


def _method_overview_flow_items(
    method_visual: dict[str, Any],
    method_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = list(method_visual.get("callouts") or [])
    if not candidates:
        candidates = [
            {
                "module_id": node.get("id"),
                "order": node.get("order"),
                "label": node.get("name"),
                "description": node.get("purpose") or node.get("innovation"),
                "sources": node.get("sources", []),
            }
            for node in method_graph.get("nodes", [])
        ]

    items: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: int(item.get("order") or 10**6),
    ):
        module_id = str(candidate.get("module_id") or "")
        label = normalize_text(str(candidate.get("label") or ""))
        text = _compact_display_text(
            str(candidate.get("description") or ""),
            135,
        )
        source_block_ids = _source_block_ids(
            list(candidate.get("sources") or [])
        )
        if not module_id or not label or not text or not source_block_ids:
            continue
        items.append(
            {
                "module_id": module_id,
                "label": label,
                "text": text,
                "source_block_ids": source_block_ids,
            }
        )
    return items[:5]


def _highlight_numbers(claim: str) -> list[str]:
    citation_stripped = re.sub(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]", "", claim)
    citation_stripped = re.sub(
        r"\b(only|over|approximately|about|around)(?=\d)",
        r"\1 ",
        citation_stripped,
        flags=re.I,
    )
    numbers = find_numbers(citation_stripped)
    lowered = claim.lower()
    if "confidence interval" in lowered or "confidence intervals" in lowered:
        numbers = {value for value in numbers if not value.strip().endswith("%")}
    numbers = {
        value
        for value in numbers
        if not (
            not value.strip().endswith("%")
            and value.strip().isdigit()
            and 1900 <= int(value.strip()) <= 2099
        )
    }
    return sorted(
        numbers,
        key=lambda value: abs(float(value.strip().rstrip("%"))),
        reverse=True,
    )


def compose_poster(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    selected_assets_path: Path,
    method_graph_path: Path,
    method_visual_plan_path: Path,
    key_idea_spec_path: Path,
    experimental_results_spec_path: Path,
    highlights_spec_path: Path,
    motivation_spec_path: Path,
    contribution_spec_path: Path,
    output_dir: Path,
    compact_level: int = 0,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    selected = read_json(selected_assets_path)
    method_graph = read_json(method_graph_path)
    method_visual = read_json(method_visual_plan_path)
    key_idea = read_json(key_idea_spec_path)
    key_idea_report_path = key_idea_spec_path.with_name("key_idea_report.json")
    key_idea_report = (
        read_json(key_idea_report_path)
        if key_idea_report_path.is_file()
        else {"status": "failed", "failed_checks": ["missing_key_idea_report"]}
    )
    key_idea_valid = str(key_idea_report.get("status") or "") in {
        "passed",
        "passed_with_warnings",
    }
    experimental_results = read_json(experimental_results_spec_path)
    highlights_spec = read_json(highlights_spec_path)
    motivation_spec = read_json(motivation_spec_path)
    contribution_spec = read_json(contribution_spec_path)
    title = paper_ir["metadata"]["title"]
    authors = [
        cleaned
        for value in paper_ir["metadata"].get("authors", [])
        if (cleaned := _clean_header_value(value))
    ]
    affiliations = [
        cleaned
        for value in paper_ir["metadata"].get("affiliations", [])
        if (cleaned := _clean_header_value(value))
    ]
    motivation_items, omitted_motivation_ids = _safe_motivation_items(
        list(motivation_spec.get("items") or [])
    )
    contributions = list(contribution_spec.get("items") or [])

    highlights = list(highlights_spec.get("highlights") or [])[:3]

    hypothesis = _node(story, "core_hypothesis", 180)
    mechanism = _node(story, "theory_or_mechanism", 240)
    if (
        hypothesis["text"]
        and mechanism["text"]
        and jaccard(hypothesis["text"], mechanism["text"]) >= 0.75
    ):
        if hypothesis["status"] == "inferred" and mechanism["status"] == "explicit":
            hypothesis = {"text": "", "status": "not_found", "sources": []}
        else:
            mechanism = {"text": "", "status": "not_found", "sources": []}

    method_visual = _neutralize_method_visual(dict(method_visual))
    # Method modules are the reading core. Do not drop them to repair overflow
    # caused by an unrelated panel.
    method_visual["callouts"] = method_visual.get("callouts", [])[:5]
    method_visual["storyboard_items"] = method_visual.get("storyboard_items", [])[:4]
    method_description_limit = max(105, 210 - compact_level * 45)
    method_visual["callouts"] = [
        {
            **item,
            "description": _compact_display_text(
                str(item.get("description") or ""),
                method_description_limit,
            ),
        }
        for item in method_visual["callouts"]
    ]
    method_visual["storyboard_items"] = [
        {
            **item,
            "description": _compact_display_text(
                str(item.get("description") or ""),
                method_description_limit,
            ),
        }
        for item in method_visual["storyboard_items"]
    ]
    method_visual["experiment_strip"] = method_visual.get("experiment_strip", [])[
        : max(2, 4 - compact_level)
    ]
    method_overview_id = method_visual.get("overview_asset_id")
    method_overview_asset = (
        {"id": method_overview_id}
        if method_overview_id
        else None
    )
    method_overview_flow = (
        []
        if method_overview_id
        else _method_overview_flow_items(method_visual, method_graph)
    )
    method_overview_fallback = (
        None
        if method_overview_id
        else (
            "sourced_method_flow"
            if method_overview_flow
            else "no-overview-figure"
        )
    )

    poster_spec = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "theme": "amp",
        "preview_status": "valid" if key_idea_valid else "invalid",
        "formal_output_allowed": key_idea_valid,
        "canvas": {
            "width_px": 3840,
            "height_px": 2160,
            "ratio": "16:9",
            "pdf_width": "48in",
            "pdf_height": "27in",
        },
        "header": {
            "title": title,
            "authors": authors,
            "affiliations": affiliations,
            "url": paper_ir["metadata"].get("url"),
        },
        "panels": {
            # These panels consume only validated Poster-language specs.
            # Compact retries may alter layout but must not delete semantic
            # items that already passed every content Gate.
            "motivation": motivation_items,
            "method_overview": {
                "asset": method_overview_asset,
                "fallback": method_overview_fallback,
                "flow_items": method_overview_flow,
                "summary": _node(story, "method_design", 260),
            },
            "key_idea": key_idea,
            "method_detail": {
                "visual_story": method_visual,
                "method": _node(story, "method_design", max(180, 320 - compact_level * 50)),
                "experimental_design": _node(
                    story,
                    "experimental_design",
                    max(150, 260 - compact_level * 40),
                ),
            },
            "experimental_results": experimental_results,
            "contributions": contributions,
            "highlights": highlights,
            "conclusion": _node(story, "conclusion", 220),
            "limitations": _node(story, "limitations", 180),
            "project": {
                "paper_url": paper_ir["metadata"].get("url"),
                "code_url": paper_ir["metadata"].get("code_url"),
                "code_status": (
                    "open_source"
                    if paper_ir["metadata"].get("code_url")
                    else "not_publicly_available"
                ),
            },
        },
        "provenance": {
            "story_fields": list(STORY_FIELDS),
            "figure_number_prior_used": selected.get("figure_number_prior_used", False),
            "captions_inspected": selected.get("captions_inspected", 0),
            "compact_level": compact_level,
            "method_graph_nodes": len(method_graph.get("nodes", [])),
            "method_visual_mode": method_visual.get("mode"),
            "method_overview_mode": (
                "original_figure"
                if method_overview_id
                else method_overview_fallback
            ),
            "method_overview_flow_items": len(method_overview_flow),
            "key_idea_type": key_idea.get("type"),
            "key_idea_report_status": key_idea_report.get("status"),
            "key_idea_failed_checks": key_idea_report.get(
                "failed_checks",
                [],
            ),
            "experimental_results_layout": experimental_results.get(
                "layout_template"
            ),
            "motivation_items": len(motivation_items),
            "omitted_invalid_motivation_ids": omitted_motivation_ids,
            "contribution_items": len(contributions),
            "method_result_asset_leaks": method_visual.get(
                "result_asset_ids_in_method",
                [],
            ),
        },
    }
    poster_spec["panels"] = _sanitize_visible_panel_value(
        poster_spec["panels"]
    )
    report = {
        "status": "passed" if key_idea_valid else "debug_preview",
        "preview_status": "valid" if key_idea_valid else "invalid",
        "formal_output_allowed": key_idea_valid,
        "key_idea_report_status": key_idea_report.get("status"),
        "key_idea_failed_checks": key_idea_report.get("failed_checks", []),
        "compact_level": compact_level,
        "motivation_items": len(motivation_items),
        "contributions": len(contributions),
        "highlights": len(highlights),
        "overview_asset": method_overview_id
        or (
            selected.get("overview_asset", {}).get("id")
            if selected.get("overview_asset")
            else None
        ),
        "overview_mode": (
            "original_figure"
            if method_overview_id
            else method_overview_fallback
        ),
        "overview_flow_items": len(method_overview_flow),
        "method_visual_mode": method_visual.get("mode"),
        "method_storyboard_assets": len(method_visual.get("storyboard_items", [])),
        "result_assets": int(bool(experimental_results.get("primary_asset")))
        + int(bool(experimental_results.get("secondary_asset"))),
        "warnings": (
            [
                *(
                    []
                    if method_overview_id or method_overview_flow
                    else [
                        "Poster has neither a reliable overview figure nor a "
                        "sourced method flow."
                    ]
                ),
                *(
                    [
                        "Omitted invalid Motivation items: "
                        + ", ".join(omitted_motivation_ids)
                    ]
                    if omitted_motivation_ids
                    else []
                ),
            ]
        ),
    }
    spec_name = "poster_spec.json" if key_idea_valid else "poster_debug_spec.json"
    return (
        write_json(output_dir / spec_name, poster_spec),
        write_json(output_dir / "compose_report.json", report),
    )
