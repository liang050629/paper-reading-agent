from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import jaccard, read_json, source_ref, validate_story_sources, write_json


def _candidate_evidence(paper_ir: dict[str, Any], claim: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[tuple[float, dict[str, Any]]] = []
    author_source_ids = {
        str(source.get("block_id"))
        for source in claim.get("sources", [])
        if source.get("block_id")
    }
    for block in paper_ir.get("blocks", []):
        section = (
            f"{block.get('section_title') or ''} "
            f"{block.get('section_id') or ''}"
        ).lower()
        if not any(term in section for term in ("result", "experiment", "evaluation", "discussion", "conclusion")):
            continue
        score = (
            1.0
            if str(block.get("id")) in author_source_ids
            else jaccard(claim["text"], block.get("text", ""))
        )
        if score > 0:
            candidates.append((score, block))
    candidates.sort(key=lambda item: item[0], reverse=True)
    evidence: list[dict[str, Any]] = []
    for score, block in candidates[:3]:
        evidence.append(
            {
                "source": source_ref(block),
                "support_type": "reported-result" if "result" in str(block.get("section_id", "")).lower() else "discussion",
                "strength": "direct" if score >= 0.28 else "partial",
                "similarity": round(score, 3),
            }
        )
    return evidence


def audit_evidence(
    paper_ir_path: Path,
    story_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    audits: list[dict[str, Any]] = []
    for claim in story.get("claims", []):
        evidence = _candidate_evidence(paper_ir, claim)
        direct = any(item["strength"] == "direct" for item in evidence)
        verdict = "supported" if direct else ("partially_supported" if evidence else "unsupported")
        audits.append(
            {
                "claim_id": claim["id"],
                "claim": claim["text"],
                "sources": claim.get("sources", []),
                "evidence": evidence,
                "verdict": verdict,
                "confidence": 0.76 if direct else (0.56 if evidence else 0.25),
                "limitations": [] if direct else ["No high-overlap result block was found by the offline auditor."],
            }
        )

    story_issues = validate_story_sources(story)
    unsupported = [audit for audit in audits if audit["verdict"] == "unsupported"]
    report = {
        "status": "failed" if story_issues else "passed_with_warnings",
        "claims_total": len(audits),
        "claims_supported": sum(audit["verdict"] == "supported" for audit in audits),
        "claims_partially_supported": sum(audit["verdict"] == "partially_supported" for audit in audits),
        "claims_unsupported": len(unsupported),
        "story_source_issues": story_issues,
        "warnings": [
            "Offline lexical matching cannot establish scientific validity; use the evidence-audit skill for final review."
        ],
    }
    matrix = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir["paper_id"],
        "generator": "heuristic-offline",
        "claims": audits,
    }
    return (
        write_json(output_dir / "claim_evidence.json", matrix),
        write_json(output_dir / "evidence_audit_report.json", report),
    )
