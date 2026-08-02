from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .common import (
    normalize_text,
    read_json,
    sentences,
    source_ref,
    token_set,
    write_json,
)

METHOD_SECTION_TERMS = (
    "method",
    "methodology",
    "approach",
    "framework",
    "architecture",
    "proposed model",
    "algorithm",
)
EXCLUDED_SECTION_TERMS = (
    "abstract",
    "introduction",
    "related work",
    "background",
    "experiment",
    "evaluation",
    "result",
    "analysis",
    "ablation",
    "comparison",
    "conclusion",
    "reference",
    "appendix",
    "limitation",
)
METHOD_SIGNALS = (
    "we propose",
    "we introduce",
    "we formulate",
    "we define",
    "we compute",
    "we estimate",
    "we score",
    "we prune",
    "we allocate",
    "we apply",
    "we use",
    "we fuse",
    "we combine",
    "our method",
    "our approach",
    "our framework",
    "consists of",
    "comprises",
    "pipeline",
    "module",
    "objective",
    "loss function",
    "weighted fusion",
    "memory bank",
    "router",
)
MAJOR_HEADING_RE = re.compile(
    # IEEE top-level Roman headings begin with I/V/X. This deliberately does
    # not treat C. or D. subsection labels as Roman numerals. MinerU may
    # normalize "3. Method" to "3 Method", so accept an unpunctuated numeric
    # top-level heading without matching decimal subsections such as "3.1".
    r"^\s*(?:(?:\d+|[IVX][IVXLCDM]*)[.)]\s+|\d+\s+)\S",
    re.I,
)
NUMBERED_SUBSECTION_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)+[.)]?|[A-Z][.)])\s+\S",
    re.I,
)
EXPLICIT_METHOD_HEADING_RE = re.compile(
    r"^(?:"
    r"methods?|methodology|our methods?|proposed methods?|"
    r"materials?\s+and\s+methods?|methods?\s+and\s+materials?|"
    r"approach|our approach|proposed approach|"
    r"proposed framework|network architecture|model architecture"
    r")$",
    re.I,
)
RELATED_METHOD_TAXONOMY_RE = re.compile(
    r"\b(?:existing|prior|previous|traditional|cnn|transformer|"
    r"convolutional|learning|deep-learning|model)-based\s+methods?\b",
    re.I,
)
NON_METHOD_ROLE_HEADING_RE = re.compile(
    r"^(?:"
    r"motivation|background|introduction|problem\s+(?:statement|formulation)|"
    r"research\s+(?:problem|gap|motivation)|preliminaries?|related\s+work|"
    r"experimental?\s+(?:setup|settings?|design)|implementation\s+details?|"
    r"experiments?|results?|evaluation|analysis|discussion|conclusion|"
    r"limitations?|future\s+work|appendix|references?"
    r")$",
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


def _body_blocks(paper_ir: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for block in paper_ir.get("blocks", [])
        if block.get("type") not in {"title", "heading", "caption"}
        and normalize_text(str(block.get("text") or ""))
    ]


def _major_section(section_id: str) -> str:
    match = re.match(r"^(\d+)(?:[-.]|$)", section_id)
    return match.group(1) if match else section_id.split("-", 1)[0]


def _heading_label(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(
        r"^\s*(?:(?:\d+(?:\.\d+)*|[IVX][IVXLCDM]*|[A-Z])[.)]?\s+)",
        "",
        value,
        flags=re.I,
    )
    return value.strip(" .:;-").lower()


def _is_explicit_method_heading(value: str) -> bool:
    label = _heading_label(value)
    return bool(
        EXPLICIT_METHOD_HEADING_RE.fullmatch(label)
        and not RELATED_METHOD_TAXONOMY_RE.search(label)
    )


def _is_non_method_role_heading(value: str) -> bool:
    """Return true for discourse/section roles that are not method entities."""

    return bool(NON_METHOD_ROLE_HEADING_RE.fullmatch(_heading_label(value)))


def _is_structural_method_section(value: str) -> bool:
    label = _heading_label(value)
    return bool(
        EXPLICIT_METHOD_HEADING_RE.fullmatch(label)
        or re.fullmatch(
            r"(?:overview|overall architecture|architecture overview|method overview|"
            r"overview of (?:the )?[a-z0-9_-]+)",
            label,
            re.I,
        )
    )


def _is_generic_loss_section(
    title: str,
    blocks: list[dict[str, Any]],
) -> bool:
    if not re.search(r"\b(?:loss|objective)\b", title, re.I):
        return False
    text = " ".join(str(block.get("text") or "") for block in blocks).lower()
    return not any(
        cue in text
        for cue in (
            "we propose",
            "we design",
            "we introduce",
            "novel loss",
            "new loss",
            "custom loss",
            "our loss",
        )
    )


def _is_appendix_section(block: dict[str, Any]) -> bool:
    section = (
        f"{block.get('section_title') or ''} "
        f"{block.get('section_id') or ''}"
    ).lower()
    # A/B/C subsection identifiers are common in IEEE papers and must not be
    # mistaken for appendices. Only explicit appendix labels are excluded.
    return "appendix" in section


def _major_regions(
    paper_ir: dict[str, Any],
) -> list[tuple[str, list[dict[str, Any]]]]:
    all_blocks = paper_ir.get("blocks", [])
    starts = [
        index
        for index, block in enumerate(all_blocks)
        if block.get("type") == "heading"
        and MAJOR_HEADING_RE.match(normalize_text(str(block.get("text") or "")))
    ]
    regions: list[tuple[str, list[dict[str, Any]]]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(all_blocks)
        heading = normalize_text(str(all_blocks[start].get("text") or ""))
        body = [
            block
            for block in all_blocks[start + 1 : end]
            if block.get("type") not in {"title", "heading", "caption"}
            and normalize_text(str(block.get("text") or ""))
        ]
        regions.append((heading, body))
    return regions


def _named_method_region(
    paper_ir: dict[str, Any],
) -> tuple[list[dict[str, Any]], str] | None:
    all_blocks = paper_ir.get("blocks", [])
    # Some publisher PDFs omit section numbers entirely. In that case, use an
    # explicit Method/Methodology heading as the start and stop at the first
    # experiment/result/conclusion heading, retaining its method subsections.
    for start, block in enumerate(all_blocks):
        if block.get("type") != "heading":
            continue
        heading = normalize_text(str(block.get("text") or ""))
        if MAJOR_HEADING_RE.match(heading):
            continue
        # A decimal/alphabetic subsection such as "2.1 CNN-based Methods" is
        # not an unnumbered top-level Method heading. Treating it as one leaks
        # Related Work taxonomy into the method graph.
        if NUMBERED_SUBSECTION_RE.match(heading):
            continue
        if not _is_explicit_method_heading(heading):
            continue
        body: list[dict[str, Any]] = []
        for candidate in all_blocks[start + 1 :]:
            candidate_text = normalize_text(str(candidate.get("text") or ""))
            if (
                candidate.get("type") == "heading"
                and any(
                    term in candidate_text.lower()
                    for term in (
                        "experiment",
                        "evaluation",
                        "result",
                        "analysis",
                        "ablation",
                        "comparison",
                        "conclusion",
                        "reference",
                        "limitation",
                    )
                )
            ):
                break
            if (
                candidate.get("type") not in {"title", "heading", "caption"}
                and candidate_text
            ):
                body.append(candidate)
        if body:
            return body, "explicit_method_heading"

    title_tokens = {
        token
        for token in token_set(
            str(paper_ir.get("metadata", {}).get("title") or "")
        )
        if token not in TITLE_STOPWORDS
    }
    candidates: list[tuple[float, str, list[dict[str, Any]]]] = []
    for heading, blocks in _major_regions(paper_ir):
        heading_lower = heading.lower()
        if any(term in heading_lower for term in EXCLUDED_SECTION_TERMS):
            continue
        if "preliminar" in heading_lower or not blocks:
            continue
        explicit = _is_explicit_method_heading(heading)
        overlap = len(title_tokens & token_set(heading))
        signal_hits = sum(
            signal in str(block.get("text") or "").lower()
            for block in blocks
            for signal in METHOD_SIGNALS
        )
        if explicit:
            basis = "explicit_method_heading"
        elif overlap and signal_hits >= 2:
            basis = "named_method_heading"
        else:
            continue
        score = (100.0 if explicit else 0.0) + overlap * 10.0 + signal_hits
        candidates.append((score, basis, blocks))
    if not candidates:
        return None
    _, basis, blocks = max(candidates, key=lambda item: item[0])
    return blocks, basis


def _method_blocks(paper_ir: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    named_region = _named_method_region(paper_ir)
    if named_region:
        return named_region

    blocks = _body_blocks(paper_ir)
    direct = [
        block
        for block in blocks
        if not _is_appendix_section(block)
        and any(
            term in (
                f"{block.get('section_title') or ''} "
                f"{block.get('section_id') or ''}"
            ).lower()
            for term in METHOD_SECTION_TERMS
        )
        and not any(
            term in str(block.get("section_title") or "").lower()
            for term in EXCLUDED_SECTION_TERMS
        )
        and not RELATED_METHOD_TAXONOMY_RE.search(
            str(block.get("section_title") or "")
        )
    ]
    if direct:
        return direct, "explicit_method_heading"

    section_scores: dict[str, float] = defaultdict(float)
    for block in blocks:
        if _is_appendix_section(block):
            continue
        section = (
            f"{block.get('section_title') or ''} "
            f"{block.get('section_id') or ''}"
        ).lower()
        if any(term in section for term in EXCLUDED_SECTION_TERMS):
            continue
        text = str(block.get("text") or "").lower()
        hits = sum(signal in text for signal in METHOD_SIGNALS)
        if hits:
            section_scores[_major_section(str(block.get("section_id") or ""))] += hits

    if not section_scores:
        return [], "not_found"
    winning_section, winning_score = max(section_scores.items(), key=lambda item: item[1])
    if winning_score < 2:
        return [], "not_found"
    inferred = [
        block
        for block in blocks
        if _major_section(str(block.get("section_id") or "")) == winning_section
    ]
    return inferred, "inferred_from_procedural_signals"


def _clean_label(value: str, fallback: str) -> str:
    value = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", normalize_text(value))
    value = re.sub(r"^(?:a|an|the|our|proposed)\s+", "", value, flags=re.I)
    value = value.strip(" .:;-")
    if not value:
        return fallback
    words = value.split()
    return " ".join(words[:8])


def _figure_number(asset: dict[str, Any]) -> str:
    caption = normalize_text(str(asset.get("caption") or ""))
    match = re.search(r"\bfig(?:ure)?\.?\s*(\d+[A-Za-z]?)\b", caption, re.I)
    if match:
        return match.group(1).lower()
    match = re.match(r"figure-(\d+[A-Za-z]?)$", str(asset.get("id") or ""), re.I)
    return match.group(1).lower() if match else ""


def _figure_numbers_in_text(value: str) -> set[str]:
    # MinerU may retain a LaTeX delimiter between "Fig." and the number,
    # for example ``Fig. $2 \ ( \mathrm{c})$``.
    return {
        match.group(1).lower()
        for match in re.finditer(
            r"\bfig(?:ure)?\.?\s*(?:\\?\$+\s*)?(\d+[A-Za-z]?)\b",
            value,
            re.I,
        )
    }


def _substantive_figure_caption(asset: dict[str, Any]) -> bool:
    caption = normalize_text(str(asset.get("caption") or ""))
    caption = re.sub(r"^\s*fig(?:ure)?\.?\s*\d+[A-Za-z]?\s*[.:]?\s*", "", caption, flags=re.I)
    caption = re.sub(r"^\s*\([a-z]\)\s*$", "", caption, flags=re.I)
    return len(re.findall(r"[A-Za-z]{2,}", caption)) >= 3


def _dataset_example_caption(asset: dict[str, Any]) -> bool:
    caption = normalize_text(str(asset.get("caption") or "")).lower()
    image_evidence = bool(
        re.search(r"\b(?:sample|example|original|input|raw)\s+images?\b", caption)
    )
    dataset_evidence = bool(
        re.search(r"\b(?:dataset|datasets|cohort|fov|field of view|labels?)\b", caption)
    )
    return image_evidence and dataset_evidence


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


def _is_dataset_split_fragment(
    asset: dict[str, Any],
    figures: list[dict[str, Any]],
) -> bool:
    if _substantive_figure_caption(asset):
        return False
    source_index = asset.get("source_item_index")
    for peer in figures:
        if peer is asset or not _dataset_example_caption(peer):
            continue
        peer_index = peer.get("source_item_index")
        if (
            isinstance(source_index, int)
            and isinstance(peer_index, int)
            and abs(source_index - peer_index) > 2
        ):
            continue
        if _shares_split_figure_row(asset, peer):
            return True
    return False


def _bind_figure_references(
    nodes: list[dict[str, Any]],
    paper_ir: dict[str, Any],
) -> None:
    """Bind Method nodes to cited figures using section and citation evidence."""

    figures = paper_ir.get("figures", [])
    blocks = paper_ir.get("blocks", [])
    nodes_per_section: dict[str, int] = defaultdict(int)
    for node in nodes:
        nodes_per_section[str(node.get("section_id") or "")] += 1

    for node in nodes:
        section_id = str(node.get("section_id") or "")
        section_blocks = [
            block
            for block in blocks
            if str(block.get("section_id") or "") == section_id
            and str(block.get("type") or "").lower()
            not in {
                "caption",
                "figure_caption",
                "image_caption",
                "table_caption",
                "equation",
                "heading",
                "title",
            }
        ]
        section_block_ids = {
            str(block.get("id"))
            for block in section_blocks
            if block.get("id")
        }
        section_pages = {
            int(block.get("page"))
            for block in section_blocks
            if isinstance(block.get("page"), int)
        }
        section_text = " ".join(
            normalize_text(str(block.get("text") or ""))
            for block in section_blocks
        )
        referenced_numbers = _figure_numbers_in_text(section_text)
        node_terms = {
            token
            for token in token_set(
                " ".join(
                    str(node.get(key) or "")
                    for key in ("name", "purpose", "innovation", "section_title")
                )
            )
            if token not in TITLE_STOPWORDS
            and token
            not in {
                "method",
                "module",
                "model",
                "network",
                "proposed",
                "attention",
                "block",
            }
        }
        candidates: list[tuple[float, str]] = []
        for figure in figures:
            figure_id = str(figure.get("id") or "")
            if not figure_id:
                continue
            # Dataset illustration panels can be physically placed before the
            # next heading and inherit the preceding Method section ID. Their
            # caption semantics are stronger than that noisy layout label.
            if _dataset_example_caption(figure) or _is_dataset_split_fragment(
                figure,
                figures,
            ):
                continue
            cited_by = {
                str(value)
                for value in figure.get("cited_by", [])
                if value
            }
            same_section = str(figure.get("section_id") or "") == section_id
            cited_in_section = bool(cited_by & section_block_ids)
            explicit_number = (
                bool(_figure_number(figure))
                and _figure_number(figure) in referenced_numbers
            )
            if not (same_section or cited_in_section or explicit_number):
                continue
            figure_section = (
                f"{figure.get('section_title') or ''} "
                f"{figure.get('section_id') or ''}"
            ).lower()
            page = figure.get("page")
            page_distance = (
                min(abs(int(page) - value) for value in section_pages)
                if isinstance(page, int) and section_pages
                else 0
            )
            if (
                not same_section
                and any(term in figure_section for term in EXCLUDED_SECTION_TERMS)
                and (not explicit_number or not figure.get("caption"))
                and page_distance > 2
            ):
                continue
            if (
                cited_in_section
                and not _substantive_figure_caption(figure)
                and (
                    (
                        str(figure.get("section_id") or "")
                        and str(figure.get("section_id") or "") != section_id
                        and any(
                            term in figure_section
                            for term in EXCLUDED_SECTION_TERMS
                        )
                    )
                    or page_distance > 1
                )
            ):
                # Some parsers emit page fragments named figure-N-2 and copy
                # every global Fig. N citation onto them. Do not let such
                # distant, captionless fragments masquerade as Method figures.
                continue
            figure_text = normalize_text(
                " ".join(
                    str(figure.get(key) or "")
                    for key in ("caption", "context_before", "context_after")
                )
            )
            overlap = len(node_terms & token_set(figure_text))
            # Several enumerated nodes may share one section. Do not attach
            # every cited figure to every node without node-specific evidence.
            if nodes_per_section[section_id] > 1 and overlap == 0:
                continue
            score = (
                4.0 * int(cited_in_section)
                + 3.0 * int(explicit_number)
                + 2.0 * int(same_section)
                + min(3.0, float(overlap))
            )
            if re.search(r"\b(?:our|ours|proposed)\b", figure_text, re.I):
                score += 0.5
            if score >= 4.0:
                candidates.append((score, figure_id))
        node["figure_refs"] = [
            figure_id
            for _, figure_id in sorted(
                candidates,
                key=lambda item: (-item[0], item[1]),
            )
        ]


def _description(
    blocks: list[dict[str, Any]],
    section_title: str,
) -> tuple[str, dict[str, Any]]:
    for block in blocks:
        ordered = [
            sentence
            for sentence in sentences(str(block.get("text") or ""))
            if any(
                cue in sentence.lower()
                for cue in ("we first", "then we", "we then", "finally", "after that")
            )
            and "$" not in sentence
            and "\\" not in sentence
        ]
        if len(ordered) >= 2 and sum(len(item.split()) for item in ordered[:3]) <= 36:
            return normalize_text(" ".join(ordered[:3])), block

    title_tokens = token_set(_clean_label(section_title, ""))
    candidates: list[
        tuple[int, int, int, int, int, int, int, str, dict[str, Any]]
    ] = []
    for block in blocks:
        for sentence in sentences(str(block.get("text") or "")):
            lowered = sentence.lower()
            signal_hits = sum(signal in lowered for signal in METHOD_SIGNALS)
            title_overlap = len(title_tokens & token_set(sentence))
            incomplete_penalty = int(
                sentence.rstrip().endswith(":")
                or sentence.rstrip().lower().endswith(
                    (" as", " by", " is", " are", " becomes")
                )
            )
            experiment_penalty = int(
                any(
                    term in lowered
                    for term in (
                        "in the extreme",
                        "experiment",
                        "performance",
                        "result",
                        "benchmark",
                        "validate",
                        "effectiveness",
                        "outperform",
                        "achieve",
                        "table ",
                    )
                )
            )
            design_signal = sum(
                cue in lowered
                for cue in (
                    "we propose",
                    "we introduce",
                    "we design",
                    "we construct",
                    "we develop",
                    "consists of",
                    "is composed of",
                    "is built from",
                    "is treated as",
                    "we first",
                    "we then",
                    "followed by",
                    "as shown in fig",
                    "see fig",
                )
            )
            math_penalty = min(
                4,
                sentence.count("$")
                + sentence.count("\\")
                + int(bool(re.search(r"\bEq\.\s*\(?\d+", sentence))),
            )
            word_count = len(sentence.split())
            length_penalty = abs(word_count - 20)
            candidates.append(
                (
                    incomplete_penalty,
                    experiment_penalty,
                    -design_signal,
                    math_penalty,
                    -title_overlap,
                    -signal_hits,
                    length_penalty,
                    sentence,
                    block,
                )
            )
    if not candidates:
        return "", blocks[0]
    candidates.sort(key=lambda item: item[:7])
    _, _, _, _, _, _, _, sentence, block = candidates[0]
    block_sentences = sentences(str(block.get("text") or ""))
    try:
        selected_index = block_sentences.index(sentence)
    except ValueError:
        selected_index = -1
    if (
        selected_index >= 0
        and selected_index + 1 < len(block_sentences)
        and re.search(
            r"\b(?:consists?|comprises?)\s+of\s+"
            r"(?:\w+\s+){0,3}(?:stages?|parts?)\b",
            sentence,
            re.I,
        )
    ):
        next_sentence = block_sentences[selected_index + 1]
        if (
            re.search(
                r"\b(?:block|module|branch|layer)s?\b|"
                r"\b[A-Z][A-Z0-9-]{1,}\b",
                next_sentence,
            )
            and len((sentence + " " + next_sentence).split()) <= 55
        ):
            sentence = f"{sentence} {next_sentence}"
    return normalize_text(sentence), block


def _enumerated_nodes(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for block in blocks:
        for sentence in sentences(str(block.get("text") or "")):
            lowered = sentence.lower()
            # A list inside an encoder/decoder implementation (e.g. Conv,
            # BatchNorm, ReLU) is not the paper's method story.  Enumerated
            # nodes are only reliable when the sentence explicitly describes
            # the whole architecture or pipeline.
            if not any(
                term in lowered
                for term in (
                    "framework",
                    "pipeline",
                    "architecture",
                    "our method",
                    "proposed network",
                    "overall network",
                    "entire network",
                )
            ):
                continue
            # Formula-heavy explanatory sentences often contain commas and
            # "including", but those fragments are tensor-shape prose rather
            # than top-level method modules.
            if (
                "$" in sentence
                or "\\" in sentence
                or len(sentence.split()) > 55
            ):
                continue
            match = re.search(
                r"\b(?:with|comprises?|consists? of|contains?|including)\b(.+)",
                sentence,
                re.I,
            )
            if not match:
                continue
            tail = re.sub(r"[.;]\s*$", "", match.group(1)).strip()
            parts = [
                normalize_text(part)
                for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", tail)
                if normalize_text(part)
            ]
            # A trailing cross-reference is exposition, not an architecture
            # component (for example, "as illustrated in Fig. 2").
            parts = [
                part
                for part in parts
                if not re.match(
                    r"^(?:as\s+)?(?:shown|illustrated|depicted|presented)\s+in\s+"
                    r"(?:fig(?:ure)?|table)\.?\s*[A-Za-z0-9-]+",
                    part,
                    re.I,
                )
            ]
            if not 2 <= len(parts) <= 6:
                continue
            if any(
                not 2 <= len(part.split()) <= 12
                or re.search(r"\b(?:in addition|however|therefore|indicates that)\b", part, re.I)
                for part in parts
            ):
                continue
            return [
                {
                    "id": f"method-node-{index}",
                    "order": index,
                    "name": _clean_label(part, f"Step {index}"),
                    "purpose": f"Perform {part.rstrip('.').lower()}.",
                    "innovation": part,
                    "section_id": str(block.get("section_id") or ""),
                    "section_title": str(block.get("section_title") or ""),
                    "figure_refs": [],
                    "sources": [source_ref(block)],
                    "status": "explicit",
                }
                for index, part in enumerate(parts, start=1)
            ]
    return []


def _paper_method_names(paper_ir: dict[str, Any]) -> set[str]:
    title = normalize_text(str(paper_ir.get("metadata", {}).get("title") or ""))
    names = {
        token.lower()
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", title)
        if any(character.isupper() for character in token[1:])
    }
    for block in paper_ir.get("blocks", [])[:100]:
        text = normalize_text(str(block.get("text") or ""))
        for match in re.finditer(
            r"\b(?:termed|called|named)\s+([A-Z][A-Za-z0-9-]{2,})\b",
            text,
        ):
            names.add(match.group(1).lower())
    return names


def _section_nodes(
    blocks: list[dict[str, Any]],
    paper_ir: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str]] = []
    for block in blocks:
        section_id = str(block.get("section_id") or "")
        section_title = str(block.get("section_title") or section_id)
        key = (section_id, section_title)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(block)

    candidates: list[tuple[tuple[str, str], list[dict[str, Any]]]] = []
    for key in order:
        section_id, title = key
        if re.match(r"^(?:table|figure|fig\.)\s*\d+", title.strip(), re.I):
            continue
        if _is_non_method_role_heading(title):
            continue
        text = " ".join(str(block.get("text") or "") for block in grouped[key]).lower()
        title_lower = title.lower()
        score = sum(signal in text for signal in METHOD_SIGNALS)
        score += sum(
            term in title_lower
            for term in (
                "module",
                "principle",
                "scoring",
                "approximation",
                "aggregation",
                "allocation",
                "cascade",
                "fusion",
                "encoder",
                "decoder",
                "attention",
                "optimization",
                "recovery",
            )
        )
        if score or re.match(r"^\d+\.\d+", title):
            candidates.append((key, grouped[key]))

    if len(candidates) > 3:
        candidates = [
            item
            for item in candidates
            if "problem formulation" not in item[0][1].lower()
        ]

    # Root "Methodology" and "Overview of X" sections describe the complete
    # system already shown by Method Overview. When dedicated method
    # subsections exist, keep those as graph nodes and avoid counting the
    # structural headings as modules that detail figures must cover.
    substantive = [
        item
        for item in candidates
        if not _is_structural_method_section(item[0][1])
        and not _is_non_method_role_heading(item[0][1])
        and not RELATED_METHOD_TAXONOMY_RE.search(item[0][1])
        and "preliminar" not in item[0][1].lower()
        and not _is_generic_loss_section(item[0][1], item[1])
    ]
    method_names = _paper_method_names(paper_ir)
    structural_system_sections: set[str] = set()
    for (section_id, title), _ in candidates:
        label = _heading_label(title)
        if label not in method_names:
            continue
        numeric_match = re.match(r"^(\d+(?:-\d+)*)", section_id)
        parent_id = numeric_match.group(1) if numeric_match else section_id
        child_prefix = parent_id.rstrip("-") + "-"
        if any(
            other_section != section_id
            and other_section.startswith(child_prefix)
            and len(re.match(r"^(\d+(?:-\d+)*)", other_section).group(1).split("-"))
            > len(parent_id.split("-"))
            for (other_section, _), _ in candidates
            if re.match(r"^(\d+(?:-\d+)*)", other_section)
        ):
            structural_system_sections.add(section_id)
    if structural_system_sections:
        substantive = [
            item
            for item in substantive
            if item[0][0] not in structural_system_sections
        ]
    if substantive:
        candidates = substantive

    nodes: list[dict[str, Any]] = []
    for key, section_blocks in candidates[:6]:
        section_id, title = key
        purpose, evidence_block = _description(section_blocks, title)
        if not purpose:
            continue
        index = len(nodes) + 1
        nodes.append(
            {
                "id": f"method-node-{index}",
                "order": index,
                "name": _clean_label(title, f"Step {index}"),
                "purpose": purpose,
                "innovation": purpose,
                "section_id": section_id,
                "section_title": title,
                "figure_refs": [],
                "sources": [source_ref(evidence_block)],
                "status": "explicit",
            }
        )
    return nodes


def build_method_graph(paper_ir_path: Path, output_dir: Path) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    blocks, selection_basis = _method_blocks(paper_ir)
    section_nodes = _section_nodes(blocks, paper_ir)
    # Formal Method subsections are stronger evidence than a single overview
    # sentence that happens to enumerate "encoder" and "decoder". Fall back
    # to sentence enumeration only when the paper does not expose multiple
    # substantive method sections.
    nodes = (
        section_nodes
        if len(section_nodes) >= 2
        else (_enumerated_nodes(blocks) or section_nodes)
    )
    _bind_figure_references(nodes, paper_ir)
    edges = [
        {
            "id": f"method-edge-{index}",
            "from": nodes[index - 1]["id"],
            "to": nodes[index]["id"],
            "relation": "next in the paper's method exposition",
            "order_basis": "explicit_sequence" if selection_basis == "explicit_method_heading" else "section_order",
            "sources": nodes[index]["sources"],
        }
        for index in range(1, len(nodes))
    ]
    graph = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "selection_basis": selection_basis,
        "nodes": nodes,
        "edges": edges,
        "source_block_count": len(blocks),
        "status": "passed" if nodes else "failed",
    }
    report = {
        "status": graph["status"],
        "selection_basis": selection_basis,
        "method_nodes": len(nodes),
        "method_edges": len(edges),
        "source_block_count": len(blocks),
        "warnings": [] if nodes else ["No evidence-grounded method modules were recovered."],
    }
    return (
        write_json(output_dir / "method_graph.json", graph),
        write_json(output_dir / "method_graph_report.json", report),
    )
