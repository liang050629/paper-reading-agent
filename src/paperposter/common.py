from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

STORY_FIELDS = (
    "research_problem",
    "motivation",
    "prior_work_gap",
    "core_hypothesis",
    "method_design",
    "theory_or_mechanism",
    "experimental_design",
    "experimental_results",
    "conclusion",
    "limitations",
)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, fallback: str = "paper") -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized[:80] or fallback


def normalize_text(value: str) -> str:
    """Collapse layout whitespace without discarding any source wording."""

    return re.sub(r"\s+", " ", value or "").strip()


def compact_text(value: str, limit: int = 280) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    shortened = text[: max(0, limit - 1)].rsplit(" ", 1)[0]
    return (shortened or text[: limit - 1]) + "…"


def sentences(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return []
    protected = re.sub(
        r"\b(Fig|Eq|Sec|Tab|Dr|Mr|Ms)\.",
        r"\1<prd>",
        text,
        flags=re.I,
    )
    parts = re.split(r"(?<=[.!?。！？])\s+", protected)
    return [
        part.replace("<prd>", ".").strip()
        for part in parts
        if part.strip()
    ]


def complete_sentences(value: str, limit: int = 280) -> str:
    """Select complete source sentences without adding a truncation marker.

    Poster panels must never silently display a partial sentence.  This helper
    keeps as many leading complete sentences as fit the requested budget; when
    none fit, it returns the shortest complete sentence for CSS to handle.
    """

    text = normalize_text(value)
    if not text:
        return ""
    candidates = [
        sentence
        for sentence in sentences(text)
        if not re.search(r"(?:…|\.\.\.|鈥\?)\s*$", sentence)
    ]
    if not candidates:
        return ""
    selected: list[str] = []
    current_length = 0
    for sentence in candidates:
        extra = len(sentence) + (1 if selected else 0)
        if selected and current_length + extra > limit:
            break
        if not selected and len(sentence) > limit:
            continue
        selected.append(sentence)
        current_length += extra
    return " ".join(selected) if selected else min(candidates, key=len)


def token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", value.lower()))


def jaccard(left: str, right: str) -> float:
    a, b = token_set(left), token_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def source_ref(block: dict[str, Any], quote_limit: int = 220) -> dict[str, Any]:
    return {
        "block_id": block["id"],
        "page": int(block.get("page") or 1),
        "bbox": block.get("bbox"),
        "quote": compact_text(block.get("text", ""), quote_limit),
    }


def select_blocks(
    paper_ir: dict[str, Any],
    section_terms: Iterable[str] = (),
    text_terms: Iterable[str] = (),
) -> list[dict[str, Any]]:
    section_terms_l = tuple(term.lower() for term in section_terms)
    text_terms_l = tuple(term.lower() for term in text_terms)
    matches: list[dict[str, Any]] = []
    for block in paper_ir.get("blocks", []):
        section = str(block.get("section_title") or block.get("section_id") or "").lower()
        text = str(block.get("text") or "").lower()
        if section_terms_l and any(term in section for term in section_terms_l):
            matches.append(block)
            continue
        if text_terms_l and any(term in text for term in text_terms_l):
            matches.append(block)
    return matches


def validate_story_sources(story: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in STORY_FIELDS:
        node = story.get(field, {})
        if node.get("status") in {"explicit", "inferred", "conflicted"} and not node.get("sources"):
            issues.append(
                {
                    "code": "STORY_SOURCE_MISSING",
                    "severity": "error",
                    "field": field,
                    "message": f"{field} is asserted without source evidence.",
                    "return_to": "paper-storyline",
                }
            )
    return issues


def find_numbers(value: str) -> set[str]:
    return set(
        re.findall(
            r"(?<!\w)[+-]?(?:\d+\.\d+|\d+)(?:\s?%)?(?!\w)",
            value or "",
        )
    )
