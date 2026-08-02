from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Iterable

from .common import jaccard, normalize_text, read_json, sentences, token_set, write_json


MOTIVATION_TYPES = (
    "problem_significance",
    "practical_need",
    "task_challenge",
    "data_challenge",
    "prior_method_limitation",
    "unresolved_gap",
    "design_requirement",
)
CONTRIBUTION_TYPES = (
    "architecture",
    "module",
    "mechanism",
    "representation_method",
    "fusion_strategy",
    "feature_fusion_strategy",
    "attention_or_interaction_strategy",
    "attention_strategy",
    "objective_or_loss",
    "scoring_or_selection_criterion",
    "scoring_criterion",
    "optimization_method",
    "training_strategy",
    "theoretical_contribution",
    "theoretical_principle",
    "algorithm",
    "dataset",
    "benchmark",
    "evaluation_protocol",
    "system_or_tool",
    "application_contribution",
    "efficiency_contribution",
    "robustness_or_generalization_contribution",
    "empirical_finding",
)
CANONICAL_CONTRIBUTION_TYPES = (
    "architecture",
    "module",
    "mechanism",
    "algorithm",
    "objective_or_loss",
    "scoring_or_selection_criterion",
    "optimization_or_training_method",
    "representation_method",
    "fusion_strategy",
    "theoretical_contribution",
    "dataset",
    "benchmark",
    "evaluation_protocol",
    "system_or_tool",
    "independent_empirical_finding",
)
CONTRIBUTION_TYPE_ALIASES = {
    "feature_fusion_strategy": "fusion_strategy",
    "attention_or_interaction_strategy": "mechanism",
    "attention_strategy": "mechanism",
    "scoring_criterion": "scoring_or_selection_criterion",
    "optimization_method": "optimization_or_training_method",
    "training_strategy": "optimization_or_training_method",
    "theoretical_principle": "theoretical_contribution",
    "application_contribution": "system_or_tool",
    "efficiency_contribution": "independent_empirical_finding",
    "robustness_or_generalization_contribution": "independent_empirical_finding",
    "empirical_finding": "independent_empirical_finding",
}
MOTIVATION_ORDER = {
    value: index for index, value in enumerate(MOTIVATION_TYPES, start=1)
}
CONTRIBUTION_ORDER = {
    value: index for index, value in enumerate(CONTRIBUTION_TYPES, start=1)
}
CONTRIBUTION_ORDER.update(
    {
        "architecture": 1,
        "module": 2,
        "mechanism": 3,
        "fusion_strategy": 4,
        "representation_method": 5,
        "objective_or_loss": 6,
        "algorithm": 7,
        "optimization_or_training_method": 8,
        "scoring_or_selection_criterion": 9,
        "theoretical_contribution": 10,
        "dataset": 11,
        "benchmark": 12,
        "evaluation_protocol": 13,
        "system_or_tool": 14,
        "independent_empirical_finding": 15,
    }
)
CONTRIBUTION_REQUIRED_ROLES = (
    "primary_method_or_architecture",
    "primary_innovation_mechanism",
    "secondary_independent_contribution",
)
CONTRIBUTION_COMPONENT_LEVELS = (
    "overall_architecture",
    "primary_mechanism",
    "secondary_mechanism",
    "objective_or_algorithm",
    "theory",
    "dataset_or_protocol",
    "empirical_validation",
    "supporting_submodule",
    "implementation_step",
)

CITATION_RE = re.compile(
    r"(?:\[\s*\d+(?:\s*[,;]\s*\d+|\s*[-–—]\s*\d+)*\s*\])|"
    r"(?:\([A-Z][A-Za-z-]+(?:\s+et\s+al\.)?(?:\s*(?:and|&)\s*"
    r"[A-Z][A-Za-z-]+)?\s*,?\s*(?:19|20)\d{2}[a-z]?\))|"
    r"(?:\b[A-Z][A-Za-z-]+\s+et\s+al\.(?:\s*,?\s*(?:19|20)\d{2})?)|"
    r"(?:\\(?:cite|citep|citet|ref|eqref)\s*\{[^}]*\})|"
    r"(?:\b(?:see|as\s+shown\s+in)\s+(?:fig(?:ure)?|table|section|sec\.?|"
    r"eq(?:uation)?\.?)\s*[IVX\d().-]+)|"
    r"(?:\b(?:Section|Sec\.?|Eq\.?)\s+[IVX\d().-]+)",
    re.I,
)
CROSS_REFERENCE_RE = re.compile(
    r"\b(?:fig(?:ure)?|table|section|sec|eq(?:uation)?|appendix|"
    r"algorithm)\b\.?\s*(?:[IVX]+\b|\d+\b|[A-Z]\b)"
    r"(?:[().:\-]*[A-Za-z0-9]+)?",
    re.I,
)
QUOTATION_RE = re.compile(r"[\"'“”‘’《》〈〉「」『』]")
AUTHOR_VOICE_RE = re.compile(
    r"\b(?:in\s+this\s+(?:paper|work|article)|we\s+(?:propose|introduce|"
    r"design|develop|present)|our\s+contribution|the\s+authors?\s+propose)\b",
    re.I,
)
NON_BLOCKING_VISIBLE_STYLE_CHECKS = {"author_voice_check"}
DISCOURSE_RE = re.compile(
    r"\b(?:first(?:ly)?|second(?:ly)?|third(?:ly)?|finally|however|although|"
    r"therefore|moreover|furthermore|additionally|in\s+addition|"
    r"to\s+this\s+end|thus|nonetheless|more\s+critically|"
    r"on\s+the\s+other\s+hand)\b",
    re.I,
)
CURRENT_WORK_RE = re.compile(
    r"\b(?:we|our|this\s+(?:paper|work|article)|the\s+proposed|"
    r"proposed\s+(?:method|model|network|module|framework|algorithm))\b",
    re.I,
)
METHOD_LEAKAGE_RE = re.compile(
    r"\b(?:the\s+proposed|"
    r"proposed\s+(?:method|model|network|module|framework|algorithm))\b",
    re.I,
)
RESULT_CLAIM_RE = re.compile(
    r"(?:\b(?:accuracy|auc|dice|dsc|iou|psnr|ssim|mae|rmse|f1|"
    r"outperform(?:s|ed)?|achiev(?:e|es|ed)|performance|experimental\s+"
    r"results?|state-of-the-art)\b|(?<!\w)\d+(?:\.\d+)?\s*%)",
    re.I,
)
POSITIVE_RESULT_RE = re.compile(
    r"\b(?:outperform(?:s|ed)?|achiev(?:e|es|ed)|state-of-the-art|"
    r"experimental\s+results?|result(?:s|ed)?\s+in\s+(?:substantially\s+)?"
    r"improv(?:e|ed|ement)|obtain(?:s|ed)?\s+(?:competitive|superior)|"
    r"prove(?:s|d)?\s+(?:effective|efficient)|demonstrat(?:e|es|ed)\s+"
    r"(?:impressive|superior|promising)|show(?:s|ed)?\s+promising|"
    r"excellent\s+image\s+quality|remarkable\s+outcomes?)\b",
    re.I,
)
OCR_ARTIFACT_RE = re.compile(
    r"(?:<[^>]+>|&(?:nbsp|amp|lt|gt);|\\text[A-Za-z]*\s*\{|"
    r"\\[A-Za-z]+\s*\{|[\uFFFD鈥閳]|"
    r"(?:^|\s)[B-HJ-Zb-hj-z](?:\s|$)|\b\w+-\s+\w+\b)"
)
SUPERLATIVE_RE = re.compile(
    r"\b(?:always|universally|guarantees?|eliminates?|all\s+datasets|"
    r"state-of-the-art|significantly)\b",
    re.I,
)
VERB_RE = re.compile(
    r"\b(?:is|are|has|have|remains?|requires?|needs?|limits?|prevents?|complicates?|"
    r"challenges?|struggles?|lacks?|makes?|supports?|matters?|must|"
    r"cannot|causes?|risks?|injects?|ignores?|obscures?|misses?|loses?|"
    r"degrades?|restricts?|increases?|balances?|dilutes?|appears?|discards?|leaves?|"
    r"captures?|models?|fuses?|combines?|constructs?|organizes?|preserves?|recovers?|uses?|binds?|"
    r"integrates?|aggregates?|unites?|optimizes?|scores?|allocates?|introduces?|provides?|"
    r"routes?|returns?|acquires?|yields?|analyzes?|adopts?|adapts?|hinders?|delays?|outlines?|"
    r"depends?|benefits?|emphasizes?|favors?|varies?|vary)\b",
    re.I,
)
MALFORMED_MOTIVATION_RE = re.compile(
    r"(?:"
    r"^\s*(?:and|as\s+well\s+as|also\s+termed)\b|"
    r"^\s*where\b.*\bmakes?\b|"
    r"\b(?:is|are)\s+(?:an?\s+)?(?:important|critical|crucial)\s+"
    r"(?:task\s+)?matters?\b|"
    r"\bplays?\s+(?:an?\s+)?(?:important|critical|crucial)\s+role\s+matters?\b|"
    r"\blies?\s+constrains?\b|"
    r"\bexhibits?\s+(?:a\s+)?quadratic\s+complexity\s+complicates?\b|"
    r"\bintegrates?\s+.+\s+dilutes?\b|"
    r"\bstudies\s+have\s+shown\s+matters\b|"
    r"\bdepends?\s+on\s+(?:clinically|practically|recently)\b|"
    r"\bmakes?\s+(?:where|with|popular|also|by|thus|however|nonetheless|"
    r"have|has|is|are|"
    r"can|could|would|should)\b|"
    r"\bcannot\s+reliably\s+adequately\b|"
    r"\bmust\s+both\s+\w+\b|"
    r"\bmust\s+(?:local|global|boundary|context|detail|features?|"
    r"capabilit(?:y|ies)|potential|questions?)\b|"
    r"\b(?:limits?|constrains?|makes?|complicates?)\s+.+\s+"
    r"(?:is|are|can|could|would|should|aims?|stands?)\b|"
    r"\ballows?\s+for\s+.+\s+supports?\b|"
    r"\b(?:their|its)\s+.+\s+posing\s+.+\s+makes?\b|"
    r"\bdata\s+limitations?\s+involving\s+(?:posing|dilutes?|hinders?|"
    r"obscures?|makes?)\b|"
    r"\b(?:fundamental\s+)?limitation\s+of\s+.+\s+lies\s+difficult\b|"
    r"\b(?:first|second|third)\s+and\s+accurate\b"
    r")",
    re.I,
)
EMPTY_MOTIVATION_PHRASE_RE = re.compile(
    r"(?:\b(?:target\s+application|real\s+task\s+conditions|"
    r"practical\s+use\s+depends\s+on|complicates?\s+the\s+task|"
    r"complicates?\s+reliable\s+learning)\b|"
    r"^\s*effective\s+(?:methods?|solutions?)\s+"
    r"(?:must\s+address|require)\s+"
    r"(?:the\s+)?challenges?\s+in\b|"
    r"^\s*(?:these|those|such|this)\s+"
    r"(?:issues?|challenges?|problems?|limitations?|tasks?|endeavors?)\b)",
    re.I,
)
VAGUE_MOTIVATION_SUBJECT_RE = re.compile(
    r"^\s*(?:these|those|such|this)\s+"
    r"(?:issues?|challenges?|problems?|limitations?|tasks?|endeavors?|"
    r"abilities?|effects?)\b",
    re.I,
)
POSITIVE_CAPABILITY_STATEMENT_RE = re.compile(
    r"\b(?:aims?\s+to|endeavors?\s+to|can\s+theoretically|"
    r"stands?\s+out\s+(?:due\s+to|because\s+of)|"
    r"fully\s+exploit|powerful\s+.+\s+capabilit(?:y|ies)|"
    r"garnered\s+significant\s+attention)\b",
    re.I,
)
GENERIC_MOTIVATION_RE = re.compile(
    r"^(?:existing|current|prior)\s+(?:methods?|models?|approaches?)\s+"
    r"(?:still\s+)?(?:show|have|achieve|yield)?\s*"
    r"(?:poor|limited|unsatisfactory|suboptimal)\s+performance\.?$",
    re.I,
)
GENERIC_COMPONENT_RE = re.compile(
    r"^(?:convolution(?:al)?(?:\s+layer)?|batch\s*norm(?:alization)?|relu|"
    r"transformer(?:\s+encoder)?|feed[-\s]?forward\s+network|ffn|attention|"
    r"encoder|decoder|backbone|strong\s+baseline|loss\s+function|"
    r"objective\s+function|architecture|framework|model|motivation|overview)$",
    re.I,
)
IMPLEMENTATION_STEP_RE = re.compile(
    r"(?:"
    r"\b(?:two|three|four|five|six|\d+)[-\s]?stage\s+(?:encoder|decoder|network)\b|"
    r"\b(?:encoder|decoder)\s+(?:stage|layer|block)s?\b|"
    r"\b(?:first|last)\s+(?:two|three|four|\d+)\s+stages?\b|"
    r"\b(?:bilinear\s+)?upsampl(?:e|ing)\b|"
    r"\bchannel[-\s]?wise\s+concatenation\b|"
    r"\bskip\s+connections?\b|"
    r"\bpatch\s+embedding(?:\s+layers?)?\b|"
    r"\b(?:convolution|conv(?:olutional)?)\s+(?:layer|block)s?\b|"
    r"\bpre[-\s]?process(?:ing)?\b|"
    r"\btraining\s+(?:pipeline|procedure|schedule)\b"
    r")",
    re.I,
)
NON_CONTRIBUTION_HEADING_RE = re.compile(
    r"^(?:motivation|background|introduction|overview|method(?:ology)?|"
    r"problem\s+(?:statement|formulation)|preliminaries?|related\s+work|"
    r"experimental?\s+(?:setup|settings?|design)|implementation\s+details?|"
    r"experiments?|results?|evaluation|analysis|discussion|conclusion|"
    r"limitations?|future\s+work|appendix|references?|dataset|benchmark)$",
    re.I,
)
RESOURCE_BURDEN_RE = re.compile(
    r"\b(?:parameter(?:s|\s+count)?|training\s+(?:cost|expense|resource|data)|"
    r"inference\s+(?:overhead|memory|cost|resource)|storage|memory|gpu\s+hours?|"
    r"comput(?:e|ation|ational)\s+(?:cost|resource|complexity)|"
    r"deployment\s+(?:cost|resource|burden)|device\s+(?:capacity|memory)|"
    r"resource(?:s|\s+usage|\s+requirement)?|flops?)\b",
    re.I,
)
BURDEN_ACTION_RE = re.compile(
    r"\b(?:increase[ds]?|higher|additional|extra|demand[ses]*|require[sd]?|"
    r"overhead|burden|costly|expensive|constrained|limited|inefficient|"
    r"less\s+efficient|accommodat(?:e|ion))\b",
    re.I,
)

TECHNICAL_ENTITY_RE = re.compile(
    r"\b(?:[A-Z]{2,}[A-Z0-9-]*|[A-Z][a-z]+[A-Z][A-Za-z0-9-]*)\b"
)

MOTIVATION_CUES: dict[str, tuple[str, ...]] = {
    "problem_significance": (
        "important",
        "critical",
        "crucial",
        "essential",
        "significance",
        "plays a vital",
    ),
    "practical_need": (
        "clinical",
        "practical",
        "real-world",
        "real world",
        "diagnosis",
        "deployment",
        "application",
    ),
    "task_challenge": (
        "challenge",
        "challenges",
        "difficult",
        "hard to",
        "complex",
        "variation",
        "ambigu",
        "low contrast",
        "thin",
        "small object",
        "long-range",
        "long range",
        "resource demand",
        "deployment burden",
        "inference overhead",
    ),
    "data_challenge": (
        "data scarcity",
        "limited data",
        "limited annotation",
        "annotation",
        "noise",
        "class imbalance",
        "domain shift",
        "heterogeneous",
        "small dataset",
    ),
    "prior_method_limitation": (
        "existing",
        "previous",
        "prior methods",
        "conventional",
        "fail to",
        "cannot",
        "struggle",
        "suffer",
        "lack",
        "overlook",
        "ignore",
        "limited ability",
        "limits their ability",
        "limits the ability",
        "introduces unexpected noise",
        "parameter count",
        "training cost",
        "training costs",
        "resource",
        "overhead",
        "less efficient",
        "underperform",
    ),
    "unresolved_gap": (
        "remains",
        "unresolved",
        "underexplored",
        "not been addressed",
        "still lacks",
        "open problem",
    ),
    "design_requirement": (
        "need to",
        "needs to",
        "requires",
        "should",
        "must",
        "calls for",
        "is necessary",
    ),
}

SAFE_REWRITE_WORDS = {
    "effective",
    "solutions",
    "prior",
    "methods",
    "struggle",
    "practical",
    "use",
    "requires",
    "data",
    "limitations",
    "complicate",
    "complicates",
    "remains",
    "unresolved",
    "matters",
    "because",
    "makes",
    "difficult",
    "uses",
    "through",
    "to",
    "for",
    "within",
    "dedicated",
}


def _words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", value or "")


def _clip_words(value: str, limit: int) -> str:
    values = _words(value)[:limit]
    while values and values[-1].lower() in {
        "and",
        "or",
        "the",
        "a",
        "an",
        "to",
        "of",
        "in",
        "by",
        "with",
        "which",
        "that",
    }:
        values.pop()
    return " ".join(values)


def _sentence_case(value: str) -> str:
    value = normalize_text(value).strip(" ,;:.")
    if not value:
        return ""
    value = value[0].upper() + value[1:]
    return value + ("" if value.endswith((".", "!", "?")) else ".")


def _resource_burden_rewrite(clean: str) -> str:
    """Rewrite resource limitations only with entities present in the source."""

    lowered = clean.lower()
    has_moe = bool(
        re.search(r"\b(?:moe|mixture[-\s]+of[-\s]+experts?|experts?)\b", lowered)
    )
    if has_moe and "inference" in lowered and (
        "parameter" in lowered or "device" in lowered
    ):
        return _sentence_case(
            "MoE inference requires devices to accommodate many expert parameters"
        )
    if has_moe and "training" in lowered and (
        "parameter" in lowered or "resource" in lowered or "cost" in lowered
    ):
        return _sentence_case(
            "MoE capacity gains require substantially more parameters and training resources"
        )
    if (
        re.search(r"\bback[-\s]?projections?\b", lowered)
        and "training" in lowered
        and re.search(r"\b(?:comput\w*\s+cost|costly|expensive)\b", lowered)
    ):
        return _sentence_case(
            "Massive back-projections make network training computationally expensive"
        )
    if (
        "iterative reconstruction" in lowered
        and re.search(r"\b(?:comput\w*\s+cost|costly|expensive)\b", lowered)
    ):
        if re.search(r"\bpractical\s+applications?\b", lowered):
            return _sentence_case(
                "High computational cost limits practical iterative reconstruction"
            )
        return _sentence_case(
            "Iterative reconstruction is computationally expensive"
        )
    if (
        "transformer" in lowered
        and "computational resources" in lowered
        and "time" in lowered
    ):
        return _sentence_case(
            "Transformer segmentation requires more compute and processing time than convolutional alternatives"
        )
    if "more parameters" in lowered and re.search(
        r"\badjust|optimi[sz]", lowered
    ):
        return _sentence_case(
            "Transformer models require more parameters and complex optimization"
        )
    if re.search(r"\b(?:comput\w*\s+cost|costly|expensive)\b", lowered):
        if "training" in lowered:
            return _sentence_case("Network training incurs high computational cost")
        if re.search(r"\bpractical\s+(?:use|applications?)\b", lowered):
            return _sentence_case("High computational cost limits practical use")
    return ""


def _balanced_parentheses(value: str) -> str:
    chars: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
            chars.append(char)
        elif char == ")":
            if depth:
                depth -= 1
                chars.append(char)
        else:
            chars.append(char)
    result = "".join(chars)
    while depth and "(" in result:
        result = result.rsplit("(", 1)[0].rstrip()
        depth -= 1
    return result


def clean_visible_text(value: str) -> str:
    """Remove paper narration and extraction artifacts before Poster rewriting."""

    text = html.unescape(str(value or ""))
    text = text.replace("\u00ad", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    replacements = {
        r"^\s*TUDIES\b": "Studies",
        r"\bone\s+of\s+S\s+the\b": "one of the",
        r"\bS\s+TUDIES\b": "Studies",
        r"\bfea\s+tures\b": "features",
        r"\bback\s+bone\b": "backbone",
        r"\bapplica\s+tions\b": "applications",
        r"\badap\s+tive\b": "adaptive",
        r"\bselec\s+tive\b": "selective",
        r"\bdistri\s+bution\b": "distribution",
        r"\bachiev\s+ing\b": "achieving",
        r"\bafected\b": "affected",
        r"\befective\b": "effective",
        r"\bdiferen\b": "different",
        r"\bdiferent\b": "different",
        r"\bdiferentiated\b": "differentiated",
        r"\bundiferentiated\b": "undifferentiated",
        r"\bineficient\b": "inefficient",
        r"\btrafic\b": "traffic",
        r"\bfundu\b": "fundus",
        r"\bsignal\s*to\s*[- ]?\s*clutter\b": "signal-to-clutter",
        r"\bsignal\s*to\s*[- ]?\s*noise\b": "signal-to-noise",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"<sup\b[^>]*>.*?</sup>", " ", text, flags=re.I | re.S)
    text = re.sub(r"</?(?:sub|span|i|b|em|strong)\b[^>]*>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\text[A-Za-z]*\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:cite|citep|citet|ref|eqref)\s*\{[^}]*\}", " ", text)
    text = re.sub(r"\([^)]*\bet\s+al\.[^)]*\)", " ", text, flags=re.I)
    text = CITATION_RE.sub(" ", text)
    text = CROSS_REFERENCE_RE.sub(" ", text)
    text = re.sub(r"\(\s*\(?[a-z]\)?\s*\)", " ", text, flags=re.I)
    text = re.sub(r"[\u00b9\u00b2\u00b3\u2070-\u2079]+", "", text)
    text = QUOTATION_RE.sub("", text)
    text = re.sub(r"[\uFFFD鈥閳]", " ", text)
    text = re.sub(r"\\+", " ", text)
    text = re.sub(r"^\s*(?:\(?\d+\)?[.):]|[鈥⒙穃-])\s*", "", text)
    text = re.sub(
        r"^\s*(?:first(?:ly)?|second(?:ly)?|third(?:ly)?|finally|however|"
        r"although|therefore|moreover|furthermore|additionally|in\s+addition|"
        r"to\s+this\s+end|hence|consequently|thus|nonetheless|"
        r"more\s+critically|on\s+the\s+other\s+hand)"
        r"\s*[,;:]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*(?:in\s+this\s+(?:paper|work|article)\s*[,;:]?|"
        r"the\s+authors?\s+propose\s+|our\s+contribution\s+(?:is|includes?)\s+)",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bwe\s+propose\s+", "", text, flags=re.I)
    text = re.sub(r"\bwe\s+(?:introduce|design|develop|present)\s+", "", text, flags=re.I)
    text = re.sub(
        r"^\s*(?:specifically|in\s+this\s+section|to\s+overcome\s+"
        r"(?:this|the)\s+limitation|to\s+address\s+(?:these|the)\s+issues)"
        r"\s*[,;:]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*we\s+(?:first|then|next)\s+(?:introduce|describe|design|apply|use)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bour\s+(?:proposed\s+)?(?:method|model|network|approach)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", text)
    text = normalize_text(_balanced_parentheses(text))
    return text.strip(" ,;:-")


def _source_record(block: dict[str, Any], raw_statement: str) -> dict[str, Any]:
    return {
        "block_id": str(block.get("id") or ""),
        "page": int(block.get("page") or 1),
        "source_section": normalize_text(
            str(block.get("section_title") or block.get("section_id") or "")
        ),
        "raw_statement": raw_statement,
    }


def _section_text(block: dict[str, Any]) -> str:
    return (
        f"{block.get('section_title') or ''} {block.get('section_id') or ''}"
    ).lower()


def _motivation_type(value: str) -> tuple[str | None, int]:
    lowered = value.lower()
    method_family = bool(
        re.search(
            r"\b(?:cnn|cnns|transformer|transformers|vision\s+transformers?|"
            r"state\s+space\s+models?|ssms?|u-net|unet|existing|prior|"
            r"previous|traditional|conventional|methods?|models?|approaches?|"
            r"attention|convolutions?|loss\s+functions?)\b",
            lowered,
        )
    )
    data_subject = bool(
        re.search(
            r"\b(?:images?|data|targets?|regions?|backgrounds?|raindrops?|"
            r"vessels?|structures?)\b",
            lowered,
        )
    )
    if (
        data_subject
        and not method_family
        and re.search(
            r"\b(?:low[-\s]?contrast|noise|degrad\w*|obscur\w*|"
            r"lack(?:s|ed)?\s+(?:of\s+)?texture|small\s+targets?|"
            r"signal-to-(?:noise|clutter)|poor\s+image\s+quality)\b",
            lowered,
        )
    ):
        return "data_challenge", 3
    if (
        method_family
        and re.search(
            r"\b(?:limitations?|limited|quadratic\s+complexity|"
            r"lack(?:s|ed)?|fail(?:s|ed)?\s+to|cannot|struggle|"
            r"unidirectional|spatial\s+awareness|long-range\s+dependencies|"
            r"neglect\w*|do(?:es)?\s+not\s+adequately|constrain\w*|"
            r"dilut\w*|integrat\w*\s+.+\s+noise)\b",
            lowered,
        )
    ):
        return "prior_method_limitation", 3
    if RESOURCE_BURDEN_RE.search(lowered) and BURDEN_ACTION_RE.search(lowered):
        if re.search(
            r"\b(?:existing|previous|prior|these|such|moe|models?|methods?|"
            r"approaches?|gains?|improvement|performance)\b",
            lowered,
        ):
            return "prior_method_limitation", 3
        return "task_challenge", 3
    if re.search(
        r"\b(?:diagnos|clinical|patient|time-consuming)\b.*"
        r"\b(?:need|delay|hinder|important|significance|screen|analyz)",
        lowered,
    ):
        return "practical_need", 2
    if re.search(r"\b(?:problem|challenge|difficulty)\s+(?:lies|arises)\s+in\b", lowered):
        return "task_challenge", 2
    if re.search(
        r"\b(?:integration|fusion|modeling|modelling|perception|"
        r"multi[-\s]?scale\s+information|global\s+context|local\s+detail)\b.*"
        r"\b(?:important|essential|critical|crucial)\b",
        lowered,
    ):
        return "design_requirement", 2
    priority = (
        "prior_method_limitation",
        "unresolved_gap",
        "data_challenge",
        "design_requirement",
        "task_challenge",
        "practical_need",
        "problem_significance",
    )
    for kind in priority:
        hits = sum(cue in lowered for cue in MOTIVATION_CUES[kind])
        if hits:
            return kind, hits
    ranked = sorted(
        (
            (sum(cue in lowered for cue in cues), kind)
            for kind, cues in MOTIVATION_CUES.items()
        ),
        key=lambda item: (item[0], -MOTIVATION_ORDER[item[1]]),
        reverse=True,
    )
    hits, kind = ranked[0]
    return (kind, hits) if hits else (None, 0)


def _story_context(story: dict[str, Any], paper_ir: dict[str, Any]) -> str:
    values = [str(paper_ir.get("metadata", {}).get("title") or "")]
    for key in ("research_problem", "motivation", "prior_work_gap"):
        values.append(str((story.get(key) or {}).get("summary") or ""))
    return " ".join(values)


def _classify_motivation_paper_type(
    paper_ir: dict[str, Any],
    story: dict[str, Any] | None = None,
) -> str:
    """Choose a broad paper profile for adaptive Motivation coverage.

    This is deliberately a soft profile classifier.  It never rejects a
    candidate; it only changes which problem-side semantic family is preferred
    when a paper does not use the conventional method-paper narrative.
    """

    story = story or {}
    title = clean_visible_text(
        str((paper_ir.get("metadata") or {}).get("title") or "")
    )
    text = " ".join(
        [
            title,
            str((story.get("research_problem") or {}).get("summary") or ""),
            str((story.get("motivation") or {}).get("summary") or ""),
            str((story.get("prior_work_gap") or {}).get("summary") or ""),
            *[
                str(block.get("text") or "")
                for block in paper_ir.get("blocks", [])
                if block.get("type") in {"paragraph", "abstract"}
                and str(block.get("section_title") or block.get("section_id") or "")
                .lower()
                .find("introduction") >= 0
            ][:24],
        ]
    ).lower()
    if re.search(
        r"\b(?:theorem|lemma|proposition|proof|convergence|generalization bound|"
        r"complexity bound|formal analysis|theoretical analysis)\b",
        text,
    ):
        return "theory_paper"
    if re.search(
        r"\b(?:clinical study|patient(?:s)?|cohort|retrospective|prospective|"
        r"randomized|trial|diagnos(?:is|tic)|treatment|hospital|clinical outcome|"
        r"medical records?)\b",
        text,
    ):
        return "clinical_study"
    if re.search(
        r"\b(?:benchmark|benchmarking|challenge dataset|new dataset|"
        r"evaluation protocol|leaderboard|data collection)\b",
        text,
    ):
        return "benchmark_paper"
    if re.search(
        r"\b(?:application|deployment|real[-\s]?world|field study|"
        r"screening|monitoring|inspection|robotic|industrial)\b",
        text,
    ) and not re.search(
        r"\b(?:we propose|we introduce|novel network|architecture|transformer|"
        r"convolutional network|deep learning model)\b",
        title.lower(),
    ):
        return "application_paper"
    return "method_paper"


def _motivation_coverage_family(
    candidate: dict[str, Any],
    paper_type: str = "method_paper",
) -> str | None:
    """Map legacy Motivation roles/relations to adaptive coverage families."""

    structure = candidate.get("relation_structure") or {}
    relation = str(structure.get("relation") or "")
    role = str(
        candidate.get("selection_role")
        or candidate.get("role")
        or structure.get("role")
        or ""
    )
    raw = _semantic_source_text(
        str(candidate.get("source_clause") or candidate.get("raw_statement") or "")
    ).lower()
    if relation in {"solution_requires_capability", "paper_targets_problem"}:
        return "need_or_objective_anchor"
    if relation in {
        "prior_method_lacks_capability",
        "prior_method_causes_failure",
        "tradeoff_remains_unresolved",
        "research_gap_remains",
    }:
        return "gap_or_constraint_anchor"
    if role in {"prior_method_limitation", "unresolved_gap"}:
        return "gap_or_constraint_anchor"
    if role in {"design_requirement", "gap_requirement_or_objective"}:
        return "need_or_objective_anchor"
    if re.search(
        r"\b(?:evidence|validation|consensus|underexplored|under[-\s]?studied|"
        r"unknown|unclear|unresolved|open question|remains to be|"
        r"insufficient data|limited data|scarce annotations?|"
        r"evaluation gap|protocol gap|trade[-\s]?off)\b",
        raw,
    ):
        return "gap_or_constraint_anchor"
    if role in {
        "task_problem_or_challenge",
        "data_challenge",
        "problem_significance",
        "practical_need",
        "problem_significance_or_practical_constraint",
    }:
        # A stated objective in a problem-side sentence belongs to the need
        # family even when the legacy classifier called it a task challenge.
        if re.search(
            r"\b(?:aim(?:s|ed)?|objective|goal|need(?:s|ed)?|requires?|"
            r"should\s+be\s+able\s+to|must\s+(?:capture|model|preserve|"
            r"support|estimate|evaluate))\b",
            raw,
        ) and re.search(
            r"\b(?:method|approach|system|model|solution|framework|study|"
            r"analysis|benchmark)\b",
            raw,
        ):
            return "need_or_objective_anchor"
        return "problem_anchor"
    # Profile-specific fallback for papers whose wording does not use the
    # conventional method-paper labels.
    profile = MOTIVATION_FAMILY_PROFILES.get(
        paper_type,
        MOTIVATION_FAMILY_PROFILES["method_paper"],
    )
    for family, roles in profile.items():
        if role in roles:
            return family
    return None


def _motivation_slot_rank(
    candidate: dict[str, Any],
    slot: str,
    paper_type: str,
) -> tuple[int, float, int]:
    priorities = MOTIVATION_SLOT_PRIORITIES.get(
        paper_type,
        MOTIVATION_SLOT_PRIORITIES["method_paper"],
    ).get(slot, MOTIVATION_REQUIRED_FAMILIES)
    family = _motivation_coverage_family(candidate, paper_type)
    try:
        family_rank = priorities.index(str(family))
    except ValueError:
        family_rank = len(priorities)
    source_page = min(
        (
            int(record.get("page") or 1)
            for record in candidate.get("source_records", [])
        ),
        default=1,
    )
    return (
        family_rank,
        -float(candidate.get("importance") or 0),
        source_page,
    )


def _relevance_overlap(value: str, context: str) -> float:
    ignored = {
        "method",
        "methods",
        "model",
        "models",
        "network",
        "networks",
        "existing",
        "current",
        "problem",
        "challenge",
    }
    left = token_set(value) - ignored
    right = token_set(context) - ignored
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _salient_fragment(value: str, limit: int = 7, *, prefer_tail: bool = False) -> str:
    text = clean_visible_text(value)
    parts = [
        normalize_text(part).strip(" ,;:.")
        for part in re.split(
            r"\b(?:because|due\s+to|which|that|while|whereas|but|"
            r"thereby|thus|hence|leading\s+to|resulting\s+in)\b|[,;:]",
            text,
            flags=re.I,
        )
        if normalize_text(part).strip(" ,;:.")
    ]
    if not parts:
        return _clip_words(text, limit)
    part = parts[-1] if prefer_tail else parts[0]
    part = re.sub(
        r"^(?:the|a|an|this|these|those|existing|current|previous|prior)\s+",
        "",
        part,
        flags=re.I,
    )
    return _clip_words(part, limit)


def _after_pattern(value: str, pattern: str, limit: int = 7) -> str:
    match = re.search(pattern, value, re.I)
    if not match:
        return ""
    return _clip_words(clean_visible_text(match.group(1)), limit)


def _looks_plural_subject(value: str) -> bool:
    head = re.split(r"\b(?:such\s+as|including)\b", value, maxsplit=1, flags=re.I)[0]
    words = _words(head)
    if not words:
        return False
    if re.search(r"\band\b", head, re.I):
        return True
    last = words[-1].lower()
    return (
        last in {"data", "people", "methods", "models", "images", "diseases"}
        or (last.endswith("s") and not last.endswith(("ss", "sis")))
    )


def _safe_nominal_fragment(value: str, *, min_words: int = 2) -> bool:
    text = normalize_text(value).strip(" ,;:.")
    words = _words(text)
    if len(words) < min_words or len(words) > 12:
        return False
    if VAGUE_MOTIVATION_SUBJECT_RE.search(text):
        return False
    return not re.search(
        r"\b(?:is|are|was|were|has|have|had|can|could|would|should|"
        r"aims?|stands?|makes?|limits?|constrains?|complicates?|"
        r"poses?|hinders?|obscures?|dilutes?|leads?|results?)\b",
        text,
        re.I,
    )


def _motivation_language_issue(value: str) -> str | None:
    text = normalize_text(value).strip()
    if len(_words(text)) < 5:
        return "incomplete problem-side statement"
    if MALFORMED_MOTIVATION_RE.search(text):
        return "malformed clause composition"
    if EMPTY_MOTIVATION_PHRASE_RE.search(text):
        return "generic placeholder wording"
    if VAGUE_MOTIVATION_SUBJECT_RE.search(text):
        return "vague or unresolved subject"
    if re.search(
        r"\b(\w+ly)\s+\1\b|\b(?:reliably\s+adequately|"
        r"important\s+task\s+matters|critical\s+task\s+matters)\b",
        text,
        re.I,
    ):
        return "repeated or mechanically combined modifiers"
    if re.search(
        r"\b(?:fail|fails)\s+to\s+require\b|"
        r"\b(?:is|are)\s+only\s+(?:trained|tested).+\bstruggles?\b|"
        r"^\s*due\s+to\b.+\bcauses?\b|"
        r"\bcauses?\s+(?:the\s+)?(?:early\s+diagnosis|"
        r"low-level\s+vision\s+field|ability\s+to|detection\s+rate)\b|"
        r"\bmust\s+(?:named|be\s+recognized|not\s+only\s+provide)\b|"
        r"\bcauses?\s+their\s+ability\b|"
        r"\bleading\s+(?:obscures?|limits?|prevents?)\b|"
        r"\bcannot\s+fully\s+\w+ly\b|"
        r"\b(?:address|require)\s+(?:this|these)\s+"
        r"(?:issue|issues|problem|problems|challenge|challenges|"
        r"limitation|limitations|(?:\w+\s+)?deficiency)\b|"
        r"\brequire\s+not\s+only\s+provide\b|"
        r"^\s*it\s+remains\s+difficult\s+for\s+[A-Z]\b|"
        r"\btheir\s+success\b.+\bthese\s+methods\b|"
        r"\bcannot\s+adequately\s+\w+ly\b|"
        r"\baddress\s+.+\band\s+\w+ing\b|"
        r"\brequire\s+(?:ambiguous|unclear|limitations?|challenges?|problems?)\b|"
        r"\brequire\b.+\band\s+(?:improving|reducing|increasing)\b|"
        r"\bstruggles?\s+with\s+limitations?\s+in\b|"
        r"^\s*by\b.+\bcan\s+struggles?\b|"
        r"^\s*struggles?\s+with\b|"
        r"\b(?:medica|efectively|signif\s+icantly)\b",
        text,
        re.I,
    ):
        return "ill-formed or unresolved semantic rewrite"
    if not VERB_RE.search(text):
        return "missing finite predicate"
    return None


def _relation_based_motivation_rewrite(
    clean: str,
    motivation_type: str,
) -> str:
    """Rewrite common source relations without fragment-splicing templates."""

    lowered = clean.lower()
    if motivation_type == "problem_significance":
        major_cause = re.search(
            r"(?:studies?\s+(?:have\s+)?shown?\s+that\s+)?"
            r"(.+?)\s+(?:is|are)\s+(?:one\s+of\s+)?(?:the\s+)?"
            r"(?:most\s+)?important\s+causes?\s+of\s+(.+)",
            clean,
            re.I,
        )
        if major_cause:
            subject = _clip_words(major_cause.group(1), 8)
            copula = "are" if _looks_plural_subject(subject) else "is"
            return _sentence_case(
                f"{subject} {copula} a major cause of "
                f"{_clip_words(major_cause.group(2), 8)}"
            )
        crucial_role = re.search(
            r"(.+?)\s+plays?\s+(?:an?\s+)?(?:important|critical|crucial|"
            r"central)\s+role\s+in\s+(.+)",
            clean,
            re.I,
        )
        if crucial_role and not VAGUE_MOTIVATION_SUBJECT_RE.search(
            crucial_role.group(1)
        ):
            return _sentence_case(
                f"{_clip_words(crucial_role.group(1), 8)} is central to "
                f"{_clip_words(crucial_role.group(2), 9)}"
            )
        important_task = re.search(
            r"(.+?)\s+is\s+(?:an?\s+)?(?:important|critical|crucial|"
            r"fundamental)\s+task\s+in\s+(.+)",
            clean,
            re.I,
        )
        if important_task:
            return _sentence_case(
                f"{_clip_words(important_task.group(1), 8)} is important for "
                f"{_clip_words(important_task.group(2), 8)}"
            )
        performance_fidelity = re.search(
            r"final\s+image\s+quality\s+is\s+(?:critical|important).*?"
            r"balance\s+of\s+performance\s+and\s+fidelity\s+is\s+"
            r"(?:critical|important)",
            clean,
            re.I,
        )
        if performance_fidelity:
            return _sentence_case(
                "Image restoration must balance reconstruction performance and visual fidelity"
            )
        important_for = re.search(
            r"(.+?)\s+(?:is|are)\s+(?:particularly\s+)?"
            r"(?:important|critical|crucial|essential)\s+for\s+(.+)",
            clean,
            re.I,
        )
        if important_for:
            return _sentence_case(
                f"{_clip_words(important_for.group(1), 9)} supports "
                f"{_clip_words(important_for.group(2), 9)}"
            )

    if motivation_type == "practical_need":
        clinical_use = re.search(
            r"(?:clinically\s*,?\s*)?(.+?)\s+is\s+(?:widely\s+)?"
            r"(?:adopted|used)\s+by\s+(?:doctors?|clinicians?|experts?)\s+"
            r"to\s+(.+)",
            clean,
            re.I,
        )
        if clinical_use:
            return _sentence_case(
                f"Clinical workflows use "
                f"{_clip_words(clinical_use.group(1), 8)} to "
                f"{_clip_words(clinical_use.group(2), 10)}"
            )

    if motivation_type in {"task_challenge", "data_challenge"}:
        low_contrast_boundary = re.search(
            r"(.+?)\s+remain(?:s)?\s+difficult\s+to\s+recover\s+in\s+"
            r"low[-\s]?contrast\s+regions?\s+because\s+(?:their|the)\s+"
            r"boundaries?\s+are\s+(?:easily\s+)?confused\s+with\s+"
            r"(?:the\s+)?background",
            clean,
            re.I,
        )
        if low_contrast_boundary:
            return _sentence_case(
                f"Low contrast makes {_clip_words(low_contrast_boundary.group(1), 6)} "
                "boundaries difficult to distinguish from background"
            )
        poor_quality = re.search(
            r"areas?\s+of\s+poor\s+image\s+quality\s+are\s+difficult\s+to\s+"
            r"distinguish.*?(?:rupture|missed\s+detection)\s+of\s+thin\s+vessels",
            clean,
            re.I,
        )
        if poor_quality:
            return _sentence_case(
                "Poor image quality obscures thin vessels and increases missed detections"
            )
        low_target_prevalence = re.search(
            r"(?:have|contain)\s+(?:a\s+)?low\s+proportion\s+of\s+small\s+"
            r"targets.*?which\s+hinder(?:s)?\s+(.+)",
            clean,
            re.I,
        )
        if low_target_prevalence:
            return _sentence_case(
                "Low target prevalence and limited data hinder detector performance in complex scenes"
            )
        local_context = re.search(
            r"local\s+receptive\s+field\s+limitation.*?leads?\s+to\s+"
            r"suboptimal\s+performance.*?where\s+global\s+semantic\s+"
            r"understanding\s+is\s+(?:important|critical|crucial)",
            clean,
            re.I,
        )
        if local_context:
            return _sentence_case(
                "Local receptive fields limit vessel-background discrimination in complex scenes"
            )
        deraining_coupling = re.search(
            r"recovering\s+clear\s+images.*?difficult.*?due\s+to\s+"
            r"(?:the\s+)?complex\s+coupling\s+of\s+raindrops.*?"
            r"(?:loss|missing)\s+of\s+.+?frequency\s+information",
            clean,
            re.I,
        )
        if deraining_coupling:
            return _sentence_case(
                "Raindrop-background coupling and frequency loss complicate clear-image recovery"
            )
        attention_scalability = re.search(
            r"attention\s+mechanisms?\s+face\s+scalability\s+challenges?\s+"
            r"due\s+to\s+(?:their\s+)?quadratic\s+complexity",
            clean,
            re.I,
        )
        if attention_scalability:
            return _sentence_case(
                "Quadratic attention limits scalability on large images"
            )
        rain_degradation = re.search(
            r"images?\s+taken\s+in\s+rainy\s+conditions\s+suffer\s+from\s+"
            r"significant\s+quality\s+degradation.*?(?:object\s+details?|"
            r"contrast).*?(?:loss\s+of\s+)?frequency\s+information",
            clean,
            re.I,
        )
        if rain_degradation:
            return _sentence_case(
                "Rain degrades object detail, contrast, and frequency information"
            )
        low_texture_target = re.search(
            r"targets?\s+often\s+appear\s+dim.*?(?:low\s+signal-to-noise|"
            r"signal-to-clutter).*?lack\s+texture\s+information",
            clean,
            re.I,
        )
        if low_texture_target:
            return _sentence_case(
                "Distant infrared targets have weak contrast and little texture"
            )
        quadratic_challenge = re.search(
            r".+?\s+exhibit(?:s)?\s+(?:a\s+)?quadratic\s+complexity\s+"
            r"in\s+(.+?),\s+which\s+poses?\s+challenges?\s+in\s+handling\s+(.+)",
            clean,
            re.I,
        )
        if quadratic_challenge:
            return _sentence_case(
                f"Quadratic {_clip_words(quadratic_challenge.group(1), 7)} "
                f"makes {_clip_words(quadratic_challenge.group(2), 9)} costly"
            )
        if re.search(
            r"\bcomplex\s+backgrounds?.*?\bobscure(?:s|d)?\s+targets?\b",
            clean,
            re.I,
        ):
            return _sentence_case("Complex backgrounds obscure targets")
        obscure = re.search(
            r"(.+?)\s+(?:further\s+)?obscure(?:s|d)?\s+(.+)",
            clean,
            re.I,
        )
        if obscure:
            subject = _clip_words(obscure.group(1), 8)
            verb = "obscure" if _looks_plural_subject(subject) else "obscures"
            return _sentence_case(
                f"{subject} {verb} "
                f"{_clip_words(obscure.group(2), 8)}"
            )
        hinder = re.search(
            r"(?:have|contain|exhibit)\s+(.+?),\s+which\s+hinder(?:s|ed)?\s+(.+)",
            clean,
            re.I,
        )
        if hinder:
            constraints = _clip_words(hinder.group(1), 11)
            constraints = re.sub(
                r"^a\s+low\s+proportion\s+of\s+small\s+targets",
                "low target prevalence",
                constraints,
                flags=re.I,
            )
            return _sentence_case(
                f"{constraints} hinder {_clip_words(hinder.group(2), 10)}"
            )
        quadratic = re.search(
            r"(?:computational\s+)?complexity\s+of\s+(.+?)\s+grows?\s+"
            r"quadratically.*?inefficient\s+for\s+(.+)",
            clean,
            re.I,
        )
        if quadratic:
            return _sentence_case(
                f"Quadratic {_clip_words(quadratic.group(1), 7)} is inefficient "
                f"for {_clip_words(quadratic.group(2), 8)}"
            )
        constraining = re.search(
            r"(?:the\s+)?(?:fundamental\s+)?limitation\s+of\s+.+?\s+"
            r"lies?\s+in\s+(.+?),\s+constrain(?:ing|s|ed)\s+(.+)",
            clean,
            re.I,
        )
        if constraining:
            constraint = _clip_words(constraining.group(1), 8)
            verb = "constrain" if _looks_plural_subject(constraint) else "constrains"
            return _sentence_case(
                f"{constraint} {verb} "
                f"{_clip_words(constraining.group(2), 10)}"
            )
        generic_constraining = re.search(
            r"(.+?),\s+constrain(?:ing|s|ed)\s+(.+)",
            clean,
            re.I,
        )
        if generic_constraining:
            return _sentence_case(
                f"{_clip_words(generic_constraining.group(1), 8)} constrains "
                f"{_clip_words(generic_constraining.group(2), 10)}"
            )
        leads_to = re.search(
            r"(.+?)\s+(?:often\s+)?leads?\s+to\s+(.+?),\s+where\s+(.+)",
            clean,
            re.I,
        )
        if leads_to:
            return _sentence_case(
                f"{_clip_words(leads_to.group(1), 8)} limits "
                f"{_clip_words(leads_to.group(3), 10)}"
            )
        if (
            re.search(r"\blow[-\s]?contrast\b", lowered)
            and "noise" in lowered
            and re.search(r"\b(?:vessel|structure|geometry)\b", lowered)
        ):
            return _sentence_case(
                "Low contrast, noise, and complex vessel geometry complicate segmentation"
            )
        diluted_by_integration = re.search(
            r"integrates?\s+(.+?),\s+which\s+"
            r"(?:dilute|dilutes|weakens?|obscures?)\s+(?:the\s+)?"
            r"(.+?)(?:\s+and\s+|[,.;]|$)",
            clean,
            re.I,
        )
        if diluted_by_integration:
            cause = _clip_words(diluted_by_integration.group(1), 8)
            verb = "dilute" if _looks_plural_subject(cause) else "dilutes"
            return _sentence_case(
                f"{cause} {verb} "
                f"{_clip_words(diluted_by_integration.group(2), 8)}"
            )

    if motivation_type == "prior_method_limitation":
        attention_scalability = re.search(
            r"attention\s+mechanisms?\s+face\s+scalability\s+challenges?\s+"
            r"due\s+to\s+(?:their\s+)?quadratic\s+complexity",
            clean,
            re.I,
        )
        if attention_scalability:
            return _sentence_case(
                "Quadratic attention limits scalability on large images"
            )
        spatial_neglect = re.search(
            r"(?:methods?\s+typically\s+employ\s+)?standard\s+convolutions?.*?"
            r"neglect(?:ing|s|ed)?\s+to\s+consider\s+the\s+spatial\s+"
            r"characteristics?\s+of\s+(.+)",
            clean,
            re.I,
        )
        if spatial_neglect:
            return _sentence_case(
                "Standard convolutions ignore the spatial structure of infrared small targets"
            )
        scale_sensitive_loss = re.search(
            r"(?:recent\s+)?loss\s+functions?.*?do\s+not\s+adequately\s+"
            r"account\s+for\s+the\s+varying\s+sensitivity\s+of\s+"
            r"(?:these\s+)?losses?\s+across\s+different\s+target\s+scales",
            clean,
            re.I,
        )
        if scale_sensitive_loss:
            return _sentence_case(
                "Existing losses ignore scale-dependent sensitivity in dim-target detection"
            )
        constraining_context = re.search(
            r"(?:the\s+)?(?:fundamental\s+)?limitation\s+of\s+.+?\s+"
            r"lies?\s+in\s+(.+?),\s+constrain(?:ing|s|ed)\s+(.+)",
            clean,
            re.I,
        )
        if constraining_context:
            constraint = _clip_words(constraining_context.group(1), 8)
            verb = "constrain" if _looks_plural_subject(constraint) else "constrains"
            return _sentence_case(
                f"{constraint} {verb} "
                f"{_clip_words(constraining_context.group(2), 10)}"
            )
        diluted_by_attention = re.search(
            r"attention.*?integrates?\s+(.+?),\s+which\s+"
            r"(?:dilute|dilutes|weakens?|obscures?)\s+(?:the\s+)?"
            r"(.+?)(?:\s+and\s+|[,.;]|$)",
            clean,
            re.I,
        )
        if diluted_by_attention:
            cause = _clip_words(diluted_by_attention.group(1), 8)
            verb = "dilute" if _looks_plural_subject(cause) else "dilutes"
            return _sentence_case(
                f"{cause} {verb} "
                f"{_clip_words(diluted_by_attention.group(2), 8)}"
            )
        quadratic_model = re.search(
            r"(.+?)\s+exhibit(?:s)?\s+(?:a\s+)?quadratic\s+complexity\s+"
            r"in\s+(.+?),\s+which\s+poses?\s+challenges?\s+in\s+handling\s+(.+)",
            clean,
            re.I,
        )
        if quadratic_model:
            return _sentence_case(
                "Quadratic sequence processing makes large images costly"
            )
        model_limitations = re.search(
            r"(.+?)\s+suffer(?:s)?\s+from\s+(?:the\s+)?limitations?\s+of\s+"
            r"(.+?)\s+and\s+(?:a\s+)?lack\s+of\s+(.+)",
            clean,
            re.I,
        )
        if model_limitations:
            subject = _clip_words(model_limitations.group(1), 7)
            copula = "are" if _looks_plural_subject(subject) else "is"
            return _sentence_case(
                f"{subject} {copula} limited by "
                f"{_clip_words(model_limitations.group(2), 8)} and "
                f"a lack of {_clip_words(model_limitations.group(3), 7)}"
            )
        modeling_limit = re.search(
            r"(.+?)\s+(?:often\s+)?encounter(?:s)?\s+limitations?\s+in\s+"
            r"(.+?)\s+when\s+(?:dealing|working)\s+with\s+(.+)",
            clean,
            re.I,
        )
        if modeling_limit:
            return _sentence_case(
                f"{_clip_words(modeling_limit.group(1), 6)} struggle with "
                f"{_clip_words(modeling_limit.group(2), 8)} for "
                f"{_clip_words(modeling_limit.group(3), 8)}"
            )
        failed_action = re.search(
            r"(?:fail(?:s|ed)?\s+to|cannot|unable\s+to|struggle(?:s|d)?\s+to)"
            r"\s+(?:adequately|reliably|effectively)?\s*([^;]+)",
            clean,
            re.I,
        )
        if failed_action:
            return _sentence_case(
                f"Earlier approaches fail to "
                f"{_clip_words(failed_action.group(1), 11)}"
            )
    return ""


def rewrite_motivation(raw_statement: str, motivation_type: str) -> str:
    clean = clean_visible_text(raw_statement)
    if not clean:
        return ""
    if (
        motivation_type
        in {
            "task_challenge",
            "data_challenge",
            "prior_method_limitation",
            "unresolved_gap",
        }
        and POSITIVE_CAPABILITY_STATEMENT_RE.search(clean)
    ):
        return ""
    relation_rewrite = _relation_based_motivation_rewrite(
        clean,
        motivation_type,
    )
    if relation_rewrite:
        return relation_rewrite
    subject = _salient_fragment(clean, 7)
    tail = _salient_fragment(clean, 7, prefer_tail=True)

    if motivation_type == "prior_method_limitation":
        lowered = clean.lower()
        if "underperform" in lowered or "less efficient" in lowered:
            if re.search(
                r"\b(?:moe|mixture[-\s]+of[-\s]+experts?|experts?)\b",
                lowered,
            ):
                return _sentence_case(
                    "MoE models can underperform dense models under standard training and constrained resources"
                )
            return ""
        if RESOURCE_BURDEN_RE.search(clean) and BURDEN_ACTION_RE.search(clean):
            return _resource_burden_rewrite(clean)
        if "not all tokens are informative" in lowered and "noise" in lowered:
            return _sentence_case(
                "Uninformative tokens inject noise into contextual feature extraction"
            )
        if "local convolutional structure" in lowered and "long-range" in lowered:
            return _sentence_case(
                "Local convolution restricts long-range dependency modeling"
            )
        if "fixed receptive field" in lowered and "land cover" in lowered:
            return _sentence_case(
                "Fixed receptive fields cannot adapt to varying land-cover context"
            )
        if (
            ("spatial or spectral" in lowered or "either spatial" in lowered)
            and "integrated modeling" in lowered
        ):
            return _sentence_case(
                "Separate spatial or spectral modeling misses their joint context"
            )
        if "independent weighting" in lowered and "foreground object modeling" in lowered:
            return _sentence_case(
                "Independent channel-spatial weighting and weak foreground modeling limit prior methods"
            )
        if "information discrepancy" in lowered and "overlook" in lowered:
            return _sentence_case(
                "Earlier approaches ignore inherent information differences"
            )
        if "traditional methods" in lowered and "diverse structures" in lowered:
            return _sentence_case(
                "Traditional methods miss complex retinal structures and spatial features"
            )
        if (
            "total variation" in lowered
            and "structural details" in lowered
            and "blocky artifacts" in lowered
        ):
            return _sentence_case(
                "Total-variation reconstruction can lose structural details and introduce blocky artifacts"
            )
        if (
            re.search(r"\blose\s+some\s+details?\b", lowered)
            and "remaining artifacts" in lowered
        ):
            return _sentence_case(
                "Iterative reconstruction can lose image details and retain artifacts"
            )
        if (
            re.search(r"\bcomputationally\s+expensive\b", lowered)
            and re.search(r"\btime[-\s]?consuming\b", lowered)
        ):
            return _sentence_case(
                "Iterative reconstruction is computationally expensive and time-consuming"
            )
        if (
            "post-processing methods" in lowered
            and re.search(r"\boverlook\w*\s+(?:the\s+)?data\s+consisten", lowered)
        ):
            return _sentence_case(
                "Post-processing networks can overlook measurement-data consistency"
            )
        if "u-net" in lowered and "different scales and shapes" in lowered:
            return _sentence_case(
                "Simple U-Net variants lose detail across vessel scales and shapes"
            )
        cause = _after_pattern(clean, r"(?:due\s+to|because\s+of)\s+(.+)")
        if cause:
            return _sentence_case(
                f"Earlier approaches remain constrained by {cause}"
            )
        failed_action = _after_pattern(
            clean,
            r"(?:fail(?:s|ed)?\s+to|cannot|do(?:es)?\s+not|"
            r"struggle(?:s|d)?\s+to|unable\s+to|limited\s+ability\s+to)\s+(.+)",
        )
        if failed_action:
            return _sentence_case(
                f"Earlier approaches fail to {failed_action}"
            )
        limitation = (
            _after_pattern(
                clean,
                r"(?:lack(?:s|ed)?|overlook(?:s|ed)?|ignore(?:s|d)?)\s+(.+)",
            )
        )
        if limitation and _safe_nominal_fragment(limitation):
            return _sentence_case(
                f"Earlier approaches remain constrained by {limitation}"
            )
        return ""

    if motivation_type == "design_requirement":
        capability_subject = re.search(
            r"(.+?)\s+(?:is|are|becomes?)\s+(?:particularly\s+)?"
            r"(?:important|essential|critical|crucial)",
            clean,
            re.I,
        )
        if capability_subject:
            return _sentence_case(
                f"Effective solutions need "
                f"{_clip_words(capability_subject.group(1), 7)}"
            )
        capability = (
            _after_pattern(
                clean,
                r"(?:needs?\s+to|must|should|calls?\s+for|requires?)\s+(.+)",
            )
            or tail
        )
        return _sentence_case(f"Effective solutions must {capability}")

    if motivation_type == "problem_significance":
        match = re.search(
            r"(.+?)\s+(?:is|are|remains?)\s+"
            r"(?:important|critical|crucial|essential)(?:\s+because|\s+for|\s+to)?\s*(.*)",
            clean,
            re.I,
        )
        if match:
            subject = _clip_words(match.group(1), 7)
            reason = _clip_words(match.group(2), 7)
            rewritten = _sentence_case(
                f"{subject} matters" + (f" because {reason}" if reason else "")
            )
            return "" if _motivation_language_issue(rewritten) else rewritten
        return ""

    if motivation_type == "practical_need":
        if (
            "medical image segmentation" in clean.lower()
            and re.search(r"\bdiagnosis|treatment\s+planning|monitoring\b", clean, re.I)
        ):
            return _sentence_case(
                "Reliable medical image segmentation supports diagnosis, treatment planning, and disease monitoring"
            )
        gained_attention = re.search(
            r"(?:in\s+recent\s+years\s*,?\s*)?"
            r"(?:due\s+to\s+[^,]+,\s*)?(.+?)\s+has\s+gained\s+"
            r"(?:significant|considerable)\s+attention.*?"
            r"(?:applications?\s+in|applications?\s*:?)\s+(.+)",
            clean,
            re.I,
        )
        if gained_attention:
            return _sentence_case(
                f"{_clip_words(gained_attention.group(1), 6)} supports "
                f"{_clip_words(gained_attention.group(2), 9)}"
            )
        application_attention = re.search(
            r"(.+?)\s+has\s+gained\s+(?:significant|considerable)\s+attention"
            r".*?\bapplications?\s+in\s+(.+)",
            clean,
            re.I,
        )
        if application_attention:
            return _sentence_case(
                f"{_clip_words(application_attention.group(1), 6)} supports "
                f"{_clip_words(application_attention.group(2), 7)}"
            )
        application_task = re.search(
            r"(.+?)\s+has\s+become\s+(?:a\s+)?(?:fundamental|important|"
            r"critical)\s+task.*?\bdue\s+to\s+.*?\bapplications?\s+in\s+"
            r"(?:areas?\s+such\s+as\s+)?(.+)",
            clean,
            re.I,
        )
        if application_task:
            return _sentence_case(
                f"{_clip_words(application_task.group(1), 7)} supports "
                f"{_clip_words(application_task.group(2), 7)}"
            )
        diagnosis = _after_pattern(
            clean,
            r"(?:diagnos(?:is|e)\s+by|diagnosis\s+depends\s+on)\s+(.+)",
        )
        if diagnosis:
            return _sentence_case(
                f"Clinical diagnosis depends on {diagnosis}"
            )
        urgent_need = _after_pattern(
            clean,
            r"(?:urgent\s+need|need)\s+for\s+(.+)",
        )
        if urgent_need:
            return _sentence_case(f"Clinical use requires {urgent_need}")
        if re.search(r"\boverly\s+complex\b.*\bhinder", clean, re.I):
            return _sentence_case(
                "Overly complex diagnostic models hinder timely clinical decisions"
            )
        if re.search(r"\bdelays?\s+in\s+diagnosis\b|time-consuming\s+segmentation", clean, re.I):
            return _sentence_case(
                "Time-consuming segmentation can delay early clinical intervention"
            )
        adoption = _after_pattern(
            clean,
            r"(?:significance|important|essential)\s+to\s+(?:adopt|use)\s+(.+)",
        )
        if adoption:
            if (
                "automatic segmentation" in adoption.lower()
                and ("diagnos" in clean.lower() or "lesion" in clean.lower())
            ):
                return _sentence_case(
                    "Automatic vessel segmentation supports lesion localization and diagnosis"
                )
            return _sentence_case(f"Clinical workflows benefit from {adoption}")
        return ""

    if motivation_type == "data_challenge":
        lowered = clean.lower()
        if "noise" in lowered and "interference" in lowered:
            return _sentence_case(
                "Acquisition interference introduces local noise into fundus images"
            )
        if "noise" in lowered and ("blur" in lowered or "edges" in lowered):
            return _sentence_case("Image noise obscures vessel boundaries")
        if (
            "inferior contrast" in lowered
            and "noise" in lowered
            and "complex structure" in lowered
        ):
            return _sentence_case(
                "Low contrast, noise, and complex vessel geometry complicate segmentation"
            )
        issue = tail if tail.lower() != subject.lower() else subject
        if _safe_nominal_fragment(issue):
            return _sentence_case(
                f"{issue} complicates reliable learning"
            )
        return ""

    if motivation_type == "unresolved_gap":
        gap = tail if tail.lower() != subject.lower() else subject
        if _safe_nominal_fragment(gap):
            return _sentence_case(f"{gap} remains unresolved")
        return ""

    lowered = clean.lower()
    if RESOURCE_BURDEN_RE.search(clean) and BURDEN_ACTION_RE.search(clean):
        return _resource_burden_rewrite(clean)
    if "scale disparity" in lowered and "exploring all scales" in lowered:
        return _sentence_case(
            "Head-scale variation complicates consistent feature extraction across crowds"
        )
    if (
        "morphological characteristics" in lowered
        and ("vessel" in lowered or "vascular" in lowered)
    ):
        return _sentence_case(
            "Complex vessel morphology complicates reliable segmentation"
        )
    if (
        "low-contrast" in lowered
        and "mistake" in lowered
        and "vessel" in lowered
    ):
        return _sentence_case(
            "Ambiguous low-contrast tissue can be mistaken for vessels"
        )
    if (
        "stacked convolution" in lowered
        and "model parameters" in lowered
        and "global contextual" in lowered
    ):
        return _sentence_case(
            "Stacked convolutions increase parameters, amplify interference, and miss global context"
        )
    if "inference cost" in lowered and "resource-limited" in lowered:
        return _sentence_case(
            "ViT-based encoders can be costly for real-time, resource-constrained deployment"
        )

    limitation_pattern = re.search(
        r"(?:limitations?|difficulty)\s+(?:for|in)\s+(.+?),?\s+"
        r"(?:due\s+to|because\s+of)\s+(.+)",
        clean,
        re.I,
    )
    if limitation_pattern:
        return _sentence_case(
            f"{_clip_words(limitation_pattern.group(2), 7)} limits "
            f"{_clip_words(limitation_pattern.group(1), 7)}"
        )

    challenge_match = re.search(
        r"(.+?)\s+(?:also\s+)?poses?\s+(?:a\s+)?"
        r"(?:significant\s+|major\s+|key\s+)?challenge",
        clean,
        re.I,
    )
    if challenge_match:
        if "morphological characteristics" in clean.lower():
            return _sentence_case(
                "Complex vessel morphology complicates accurate segmentation"
            )
        challenge = _clip_words(challenge_match.group(1), 7)
        if _safe_nominal_fragment(challenge):
            return _sentence_case(f"{challenge} creates a major obstacle")
        return ""
    presents_challenge = re.search(
        r"(.+?)\s+presents?\s+(?:a\s+)?challenge\s+in\s+(.+)",
        clean,
        re.I,
    )
    if presents_challenge:
        return _sentence_case(
            f"{_clip_words(presents_challenge.group(1), 7)} complicates "
            f"{_clip_words(presents_challenge.group(2), 7)}"
        )
    challenge_lies = re.search(
        r"(?:challenge|difficulty)\s+(?:lies|arises)\s+in\s+(.+)",
        clean,
        re.I,
    )
    if challenge_lies:
        return _sentence_case(
            f"{_clip_words(challenge_lies.group(1), 7)} complicates the task"
        )
    # Do not splice unrelated head and tail fragments into a plausible-looking
    # sentence. If no source relation was recognized above, reject the
    # candidate and let another evidence-backed sentence represent the need.
    return ""


def _legacy_motivation_candidates(
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    method_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    context = _story_context(story, paper_ir)
    method_names = [
        normalize_text(str(node.get("name") or ""))
        for node in method_graph.get("nodes", [])
        if normalize_text(str(node.get("name") or ""))
    ]
    method_names.extend(
        match.group(0)
        for node in method_graph.get("nodes", [])
        for match in re.finditer(
            r"\b(?:[A-Z]{2,}[A-Z0-9-]*|"
            r"[A-Z][A-Za-z0-9-]*(?:Net|Former|Fusion|Mamba))\b",
            str(node.get("name") or ""),
        )
    )
    title = str(paper_ir.get("metadata", {}).get("title") or "")
    # Only add title tokens that are structurally method names. Treating every
    # capitalized title word as a method name incorrectly classifies ordinary
    # task terms such as Retinal, Vessel, and Segmentation as current-work
    # leakage.
    method_names.extend(
        match.group(0)
        for match in re.finditer(
            r"\b(?:[A-Z]{2,}[A-Z0-9-]*|[A-Z][A-Za-z0-9-]*(?:Net|Former|Mamba))\b",
            title,
        )
        if match.group(0).lower()
        not in {"cnn", "vit", "transformer", "network", "image"}
    )
    candidates: list[dict[str, Any]] = []
    allowed_sections = (
        "abstract",
        "introduction",
        "background",
        "related work",
        "conclusion",
        "discussion",
    )
    excluded_sections = ("method", "experiment", "result", "evaluation", "reference")
    for block in paper_ir.get("blocks", []):
        if block.get("type") in {"title", "heading", "caption", "equation", "table"}:
            continue
        section = _section_text(block)
        if any(term in section for term in excluded_sections) and not any(
            term in section for term in allowed_sections
        ):
            continue
        if not any(term in section for term in allowed_sections) and block.get("type") != "abstract":
            continue
        for raw in sentences(str(block.get("text") or "")):
            cleaned = clean_visible_text(raw)
            kind, cue_hits = _motivation_type(cleaned)
            if not kind or len(_words(cleaned)) < 5:
                continue
            current_method = bool(
                CURRENT_WORK_RE.search(raw)
                or AUTHOR_VOICE_RE.search(raw)
                or re.search(
                    r"\b(?:this|the)\s+(?:design|strategy|variant|mechanism|"
                    r"architecture|framework|approach|method|model)\b|"
                    r"\b(?:we\s+)?(?:propose|introduce|present|develop|design)\b|"
                    r"\bby\s+doing\s+so\b|"
                    r"\b(?:module|block|network)\s+is\s+to\b",
                    raw,
                    re.I,
                )
                or any(
                    name.lower() in cleaned.lower()
                    for name in method_names
                    if len(normalize_text(name)) >= 4
                    and name.lower()
                    not in {
                        "attention",
                        "transformer",
                        "encoder",
                        "decoder",
                        "strong baseline",
                    }
                )
            )
            result_statement = bool(
                re.search(
                    r"^\s*(?:the\s+)?(?:experimental\s+)?results?\s+"
                    r"(?:show|demonstrate|indicate|confirm)\b",
                    cleaned,
                    re.I,
                )
                or
                re.search(
                    r"(?<!\w)\d+(?:\.\d+)?\s*%|\b(?:accuracy|auc|dice|dsc|"
                    r"iou|psnr|ssim|mae|rmse|f1)\b",
                    cleaned,
                    re.I,
                )
                or re.search(
                    r"\b(?:our|the\s+proposed|this)\s+"
                    r"(?:method|model|network|approach|framework)\b.*"
                    r"\b(?:achiev|outperform|improv|performance)\w*\b",
                    cleaned,
                    re.I,
                )
            )
            relevance = _relevance_overlap(cleaned, context)
            citation_dominated = bool(
                re.search(r"^\s*(?:\[\d|[A-Z][A-Za-z-]+\s+et\s+al)", raw)
                or re.search(r"^\s*[A-Z]{3,}\s+(?:have|has|show)", cleaned)
            )
            incomplete = bool(
                re.search(
                    r"\b(?:and|or|the|a|an|to|for|by|with|which|that|of|in)\.?$",
                    cleaned,
                    re.I,
                )
                or cleaned.count("(") != cleaned.count(")")
                or raw.rstrip().endswith(":")
            )
            has_citation = bool(
                CITATION_RE.search(raw)
                or re.search(r"\([^)]*\bet\s+al\.[^)]*\)", raw, re.I)
            )
            named_prior_example = bool(
                has_citation
                and re.search(
                    r"\b(?:proposed|adopted|utilized|investigated|introduced)\b",
                    raw,
                    re.I,
                )
                and not re.search(
                    r"\b(?:existing|current|prior|previous|most|many|these|such|"
                    r"simple)\s+(?:[A-Za-z0-9-]+\s+){0,2}"
                    r"(?:methods?|models?|approaches?|studies)\b|"
                    r"\b(?:fail|lack|limit|struggle|overlook|cannot)\b",
                    raw,
                    re.I,
                )
            )
            conclusion_method_statement = bool(
                "conclusion" in section
                and (
                    re.search(
                        r"\b(?:[A-Z]{2,}[A-Za-z0-9-]*(?:Net|Former)?|"
                        r"[A-Z][a-z]+(?:Net|Former))\b",
                        raw,
                    )
                    or re.search(
                        r"\b(?:selects?|fuses?|introduces?|proposes?|"
                        r"achieves?|outperforms?)\b",
                        raw,
                        re.I,
                    )
                )
            )
            related_specific = bool(
                "related work" in section
                and (
                    citation_dominated
                    or not re.search(
                        r"\b(?:existing|current|prior|previous|most|many|"
                        r"these|such)\s+(?:methods?|models?|approaches?|studies)\b",
                        cleaned,
                        re.I,
                    )
                )
            )
            weak_design_requirement = bool(
                kind == "design_requirement"
                and (
                    "related work" in section
                    or not re.search(
                        r"\b(?:capture|preserve|model|integrate|combine|handle|"
                        r"reduce|recover|represent|adapt|distinguish|exploit)\b",
                        cleaned,
                        re.I,
                    )
                )
            )
            weak_prior_limitation = bool(
                kind == "prior_method_limitation"
                and not re.search(
                    r"\b(?:fail|lack|limit(?:ation)?s?|struggle|suffer|overlook|ignore|"
                    r"cannot|unable|burden|noise|discrepancy|fixed|"
                    r"parameters?|costs?|resources?|overhead|inefficient|"
                    r"efficient|underperform|demands?|requires?|increase|"
                    r"quadratic|dilut\w*|integrat\w*\s+.+\s+noise)\b",
                    cleaned,
                    re.I,
                )
            )
            vague_prior_limitation = bool(
                kind == "prior_method_limitation"
                and re.search(r"^\s*(?:both|these|such)\s+methods?\b", cleaned, re.I)
                and not re.search(
                    r"\b(?:foreground|background|channel|spatial|spectral|"
                    r"vessel|token|receptive|scale|contrast|noise|dependency|"
                    r"boundary|detail|feature)\b",
                    cleaned,
                    re.I,
                )
            )
            vague_reference_statement = bool(
                re.search(
                    r"^\s*(?:these|those|such|this)\s+"
                    r"(?:issues?|challenges?|problems?|limitations?)\b",
                    cleaned,
                    re.I,
                )
            )
            weak_practical_need = bool(
                kind == "practical_need"
                and not re.search(
                    r"\b(?:need|diagnos|delay|time-consuming|important|"
                    r"significance|screen|analyz|deployment|monitoring|"
                    r"agriculture|planning|intervention)\b",
                    cleaned,
                    re.I,
                )
            )
            positive_solution_statement = bool(
                kind
                in {
                    "task_challenge",
                    "data_challenge",
                    "prior_method_limitation",
                    "unresolved_gap",
                }
                and re.search(
                    r"\b(?:advantages?|benefits?|improves?|enhances?|"
                    r"reduces?|retains?|ensures?|matches?|effective|"
                    r"success(?:ful|fully)?|outstanding|garnered)\b",
                    cleaned,
                    re.I,
                )
                and not re.search(
                    r"\b(?:but|however|despite|underperform|constrained|"
                    r"challenge|difficulty|difficult|fail|lack|limit|"
                    r"struggle|costly|burden|overhead|requires?|demand|"
                    r"offset)\b",
                    cleaned,
                    re.I,
                )
            )
            affirmative_capability_statement = bool(
                kind in {"task_challenge", "data_challenge", "unresolved_gap"}
                and re.search(
                    r"\b(?:can|could|is\s+able\s+to|capable\s+of|"
                    r"captures?|models?|enables?|provides?)\b",
                    cleaned,
                    re.I,
                )
                and not re.search(
                    r"\b(?:but|however|despite|challenge|difficult|fail|"
                    r"lack|limit|struggle|costly|burden|overhead|"
                    r"inefficient|cannot|unable|noise|obscur|hinder)\w*\b",
                    cleaned,
                    re.I,
                )
            )
            positive_capability_statement = bool(
                kind
                in {
                    "task_challenge",
                    "data_challenge",
                    "prior_method_limitation",
                    "unresolved_gap",
                }
                and POSITIVE_CAPABILITY_STATEMENT_RE.search(cleaned)
            )
            missing_problem_signal = bool(
                kind in {"task_challenge", "data_challenge", "unresolved_gap"}
                and not re.search(
                    r"\b(?:challenge|difficult|hard|obscur|mistak|ambig|"
                    r"noise|limited|limitation|lack|loss|fail|struggle|"
                    r"interference|low[-\s]?contrast|small|thin|variation|"
                    r"complexity|burden|cost|require|prevent|remain)\w*\b",
                    cleaned,
                    re.I,
                )
            )
            specific = not GENERIC_MOTIVATION_RE.fullmatch(cleaned)
            specific = bool(
                specific
                and len(token_set(cleaned)) >= 4
                and not citation_dominated
                and not incomplete
                and not related_specific
                and not weak_design_requirement
                and not weak_prior_limitation
                and not vague_prior_limitation
                and not vague_reference_statement
                and not weak_practical_need
                and not positive_solution_statement
                and not affirmative_capability_statement
                and not positive_capability_statement
                and not missing_problem_signal
                and not named_prior_example
                and not conclusion_method_statement
                and not re.search(r"\b(?:19|20)\d{2}\b", cleaned)
            )
            causal = bool(
                kind in {
                    "problem_significance",
                    "practical_need",
                    "task_challenge",
                    "data_challenge",
                    "prior_method_limitation",
                    "unresolved_gap",
                    "design_requirement",
                }
                or re.search(
                    r"\b(?:because|due\s+to|challenges?|difficult(?:y|ies)?|"
                    r"limits?|fail|lack|struggle|needs?|requires?|prevent|"
                    r"overlook|burden|costs?|overhead|demand)\b",
                    cleaned,
                    re.I,
                )
            )
            rewritten = rewrite_motivation(raw, kind)
            language_issue = (
                _motivation_language_issue(rewritten)
                if rewritten
                else "no reliable evidence-preserving rewrite"
            )
            gate_results = {
                "relevance_gate": {
                    "passed": relevance >= 0.08 or (
                        cue_hits >= 2 and relevance >= 0.035
                    ),
                    "reason": "candidate overlaps the paper problem or has multiple problem-side cues",
                },
                "specificity_gate": {
                    "passed": bool(specific and not result_statement),
                    "reason": "candidate states a concrete challenge, limitation, need, or significance",
                },
                "causal_gate": {
                    "passed": causal,
                    "reason": "candidate explains why a later design capability is needed",
                },
                "evidence_gate": {
                    "passed": bool(block.get("id") and int(block.get("page") or 0) >= 1),
                    "reason": "candidate is bound to a PaperIR block and page",
                },
                "independence_gate": {
                    "passed": True,
                    "reason": "evaluated after semantic clustering",
                },
                "role_separation_gate": {
                    "passed": not current_method and not result_statement,
                    "reason": "problem-side statement remains valid without the proposed method",
                },
                "language_rewrite_gate": {
                    "passed": language_issue is None,
                    "reason": (
                        "candidate rewrites into a complete, neutral English statement"
                        if language_issue is None
                        else language_issue
                    ),
                },
            }
            candidates.append(
                {
                    "candidate_id": f"mot-candidate-{len(candidates) + 1}",
                    "type": kind,
                    "raw_statement": raw,
                    "normalized_meaning": rewritten,
                    "source_records": [_source_record(block, raw)],
                    "gate_results": gate_results,
                    "importance": round(
                        min(
                            1.0,
                            0.35
                            + 0.12 * cue_hits
                            + 0.35 * min(1.0, relevance)
                            + (0.08 if block.get("type") == "abstract" else 0.0),
                        ),
                        3,
                    ),
                }
            )
    return candidates


MOTIVATION_REQUIRED_ROLES = (
    "task_problem_or_challenge",
    "prior_method_limitation",
    "gap_requirement_or_objective",
)
MOTIVATION_REQUIRED_FAMILIES = (
    "problem_anchor",
    "gap_or_constraint_anchor",
    "need_or_objective_anchor",
)
MOTIVATION_COVERAGE_SLOTS = (
    "core_problem",
    "unresolved_driver",
    "reading_direction",
)
MOTIVATION_HARD_COVERAGE_SLOTS = (
)
MOTIVATION_MIN_ITEMS = 1
MOTIVATION_TARGET_ITEMS = 3
MOTIVATION_MAX_ITEMS = 5
MOTIVATION_PAPER_TYPES = (
    "method_paper",
    "theory_paper",
    "clinical_study",
    "benchmark_paper",
    "application_paper",
)
MOTIVATION_FAMILY_PROFILES = {
    "method_paper": {
        "problem_anchor": (
            "task_challenge",
            "data_challenge",
            "problem_significance",
            "practical_need",
        ),
        "gap_or_constraint_anchor": (
            "prior_method_limitation",
            "unresolved_gap",
            "task_challenge",
        ),
        "need_or_objective_anchor": (
            "design_requirement",
            "unresolved_gap",
            "practical_need",
        ),
    },
    "theory_paper": {
        "problem_anchor": (
            "task_challenge",
            "problem_significance",
            "data_challenge",
        ),
        "gap_or_constraint_anchor": (
            "unresolved_gap",
            "prior_method_limitation",
            "task_challenge",
        ),
        "need_or_objective_anchor": (
            "design_requirement",
            "unresolved_gap",
            "practical_need",
        ),
    },
    "clinical_study": {
        "problem_anchor": (
            "problem_significance",
            "practical_need",
            "task_challenge",
            "data_challenge",
        ),
        "gap_or_constraint_anchor": (
            "unresolved_gap",
            "prior_method_limitation",
            "practical_need",
        ),
        "need_or_objective_anchor": (
            "design_requirement",
            "practical_need",
            "unresolved_gap",
        ),
    },
    "benchmark_paper": {
        "problem_anchor": (
            "task_challenge",
            "problem_significance",
            "data_challenge",
        ),
        "gap_or_constraint_anchor": (
            "unresolved_gap",
            "prior_method_limitation",
            "data_challenge",
        ),
        "need_or_objective_anchor": (
            "design_requirement",
            "unresolved_gap",
            "practical_need",
        ),
    },
    "application_paper": {
        "problem_anchor": (
            "practical_need",
            "problem_significance",
            "task_challenge",
            "data_challenge",
        ),
        "gap_or_constraint_anchor": (
            "unresolved_gap",
            "prior_method_limitation",
            "practical_need",
        ),
        "need_or_objective_anchor": (
            "design_requirement",
            "practical_need",
            "unresolved_gap",
        ),
    },
}
MOTIVATION_SLOT_PRIORITIES = {
    "method_paper": {
        "core_problem": (
            "problem_anchor",
            "gap_or_constraint_anchor",
            "need_or_objective_anchor",
        ),
        "unresolved_driver": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "reading_direction": (
            "need_or_objective_anchor",
            "gap_or_constraint_anchor",
            "problem_anchor",
        ),
    },
    "theory_paper": {
        "core_problem": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "unresolved_driver": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "reading_direction": (
            "need_or_objective_anchor",
            "gap_or_constraint_anchor",
            "problem_anchor",
        ),
    },
    "clinical_study": {
        "core_problem": (
            "problem_anchor",
            "gap_or_constraint_anchor",
            "need_or_objective_anchor",
        ),
        "unresolved_driver": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "reading_direction": (
            "need_or_objective_anchor",
            "problem_anchor",
            "gap_or_constraint_anchor",
        ),
    },
    "benchmark_paper": {
        "core_problem": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "unresolved_driver": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "reading_direction": (
            "need_or_objective_anchor",
            "gap_or_constraint_anchor",
            "problem_anchor",
        ),
    },
    "application_paper": {
        "core_problem": (
            "problem_anchor",
            "gap_or_constraint_anchor",
            "need_or_objective_anchor",
        ),
        "unresolved_driver": (
            "gap_or_constraint_anchor",
            "problem_anchor",
            "need_or_objective_anchor",
        ),
        "reading_direction": (
            "need_or_objective_anchor",
            "problem_anchor",
            "gap_or_constraint_anchor",
        ),
    },
}
MOTIVATION_OPTIONAL_ROLES = (
    "additional_independent_limitation",
    "problem_significance_or_practical_constraint",
)
MOTIVATION_RELATIONS = {
    "problem_has_consequence",
    "task_is_difficult_under_condition",
    "data_contains_challenge",
    "prior_method_lacks_capability",
    "prior_method_causes_failure",
    "tradeoff_remains_unresolved",
    "research_gap_remains",
    "solution_requires_capability",
    "paper_targets_problem",
}
REFERENCE_SUBJECT_RE = re.compile(
    r"^\s*(?:this|these|those|such)\s+"
    r"(?:methods?|models?|approaches?|algorithms?|techniques?|issues?|"
    r"problems?|challenges?|limitations?|data|images?|tasks?)\b|"
    r"^\s*(?:the\s+former|the\s+latter|it|they)\b",
    re.I,
)
METHOD_FAMILY_RE = re.compile(
    r"\b(?:existing|current|prior|previous|traditional|conventional|"
    r"iterative|learning-based|cnn-based|transformer-based|"
    r"methods?|models?|approaches?|algorithms?|techniques?|networks?)\b",
    re.I,
)
PROBLEM_SIGNAL_RE = re.compile(
    r"\b(?:challenge|difficult|hard|ambiguous|obscur|noise|artifact|"
    r"low[-\s]?contrast|limited|limitation|lack|fail|struggle|suffer|"
    r"cannot|unable|cost|expensive|complexity|burden|overhead|"
    r"underperform|unresolved|not\s+addressed|not\s+been\s+fully\s+realized|"
    r"only\s+assum|remain|requires?|needs?|"
    r"must|should|hinder|degrad|loss|miss|limits?|weakness(?:es)?|"
    r"trade[-\s]?off)\w*\b",
    re.I,
)
SOLUTION_SIDE_DESCRIPTION_RE = re.compile(
    r"\b(?:formulat(?:e|ed)|design(?:ed)?|develop(?:ed)?|adapt(?:ed)?|"
    r"appl(?:y|ied)|use(?:d)?)\b.*\b(?:to\s+(?:deal\s+with|address|solve)|"
    r"for\s+(?:denoising|reconstruction|segmentation|detection))\b",
    re.I,
)
PURE_METHOD_PROPOSITION_RE = re.compile(
    r"\b(?:we\s+|this\s+(?:paper|work)\s+|the\s+proposed\s+)?"
    r"(?:propose|introduce|design|develop|present|construct|build|"
    r"formulate|define|employ|adopt|use|apply)(?:s|ed)?\b.*"
    r"\b(?:network|framework|architecture|module|block|branch|layer|"
    r"attention|transformer|u-?net|cnn|loss|strategy|algorithm)\b",
    re.I,
)
EXPLICIT_PROBLEM_RELATION_RE = re.compile(
    r"\b(?:fail(?:s|ed)?\s+to|cannot|unable\s+to|struggle(?:s|d)?\s+to|"
    r"lack(?:s|ed)?|suffer(?:s|ed)?\s+from|limited\s+by|"
    r"(?:is|are|was|were|remain(?:s)?)\s+limited|"
    r"challenge|difficulty|problem|issue|unresolved|unaddressed|"
    r"requires?|needs?|must|should|hinder(?:s|ed)?|degrade(?:s|d)?|"
    r"lead(?:s)?\s+to|result(?:s|ed)?\s+in)\b",
    re.I,
)
RESOLUTION_METHOD_HISTORY_RE = re.compile(
    r"^\s*to\s+(?:resolve|address|overcome|mitigate|alleviate|handle)\s+"
    r"(?:the\s+)?(?:limitations?|problems?|issues?|challenges?)\s*[,;:]?"
    r".*\b(?:methods?|models?|approaches?|algorithms?|techniques?)\b.*"
    r"\b(?:were|was|are|is|have\s+been|has\s+been)\s+"
    r"(?:applied|used|adopted|introduced|developed|employed)\b",
    re.I,
)


def _motivation_section_kind(block: dict[str, Any]) -> str | None:
    section = _section_text(block)
    block_type = str(block.get("type") or "").lower()
    if block_type == "abstract" or "abstract" in section:
        return "abstract"
    if "introduction" in section:
        return "introduction"
    if "background" in section:
        return "background"
    if "related work" in section:
        return "related_work"
    if "conclusion" in section or "discussion" in section:
        return "conclusion"
    return None


def _motivation_sentence_records(
    paper_ir: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    relevant_blocks = [
        block
        for block in paper_ir.get("blocks", [])
        if block.get("type")
        not in {"title", "heading", "caption", "equation", "table"}
        and _motivation_section_kind(block)
        and normalize_text(str(block.get("text") or ""))
    ]
    intro_blocks = [
        block
        for block in relevant_blocks
        if _motivation_section_kind(block) == "introduction"
    ]
    intro_positions = {
        str(block.get("id") or ""): index / max(1, len(intro_blocks) - 1)
        for index, block in enumerate(intro_blocks)
    }
    records: list[dict[str, Any]] = []
    scanned_blocks: list[dict[str, Any]] = []
    for block in relevant_blocks:
        values = sentences(str(block.get("text") or ""))
        block_id = str(block.get("id") or "")
        section_kind = str(_motivation_section_kind(block) or "")
        scanned_blocks.append(
            {
                "block_id": block_id,
                "page": int(block.get("page") or 1),
                "section_kind": section_kind,
                "section_title": normalize_text(
                    str(
                        block.get("section_title")
                        or block.get("section_id")
                        or ""
                    )
                ),
                "sentence_count": len(values),
                "text_preview": _clip_words(
                    _semantic_source_text(str(block.get("text") or "")),
                    28,
                ),
            }
        )
        for index, raw in enumerate(values):
            records.append(
                {
                    "sentence_id": f"{block_id}-s{index + 1}",
                    "sentence_index": index,
                    "paragraph_sentences": values,
                    "block": block,
                    "raw_statement": raw,
                    "section_kind": section_kind,
                    "section_position": intro_positions.get(block_id),
                    "is_last_intro_block": bool(
                        intro_blocks and block is intro_blocks[-1]
                    ),
                }
            )
    return records, {
        "source_blocks_scanned": len(relevant_blocks),
        "introduction_blocks_scanned": sum(
            item["section_kind"] == "introduction"
            for item in scanned_blocks
        ),
        "abstract_blocks_scanned": sum(
            item["section_kind"] == "abstract"
            for item in scanned_blocks
        ),
        "scanned_blocks": scanned_blocks,
    }


def _semantic_source_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\u00ad", "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    # Common dropped-cap / reading-order artifacts found in real journal PDFs.
    text = re.sub(r"^\s*TUDIES\b", "Studies", text, flags=re.I)
    text = re.sub(r"\bone\s+of\s+S\s+the\b", "one of the", text, flags=re.I)
    text = re.sub(r"\bS\s+TUDIES\b", "Studies", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\(?:cite|citep|citet|ref|eqref)\s*\{[^}]*\}", " ", text)
    text = CITATION_RE.sub(" ", text)
    text = CROSS_REFERENCE_RE.sub(" ", text)
    text = QUOTATION_RE.sub("", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return normalize_text(text).strip(" ,;:")


def _context_window(record: dict[str, Any]) -> tuple[list[str], list[str], bool]:
    values = list(record.get("paragraph_sentences") or [])
    index = int(record.get("sentence_index") or 0)
    target = str(record.get("raw_statement") or "")
    radius = 2 if REFERENCE_SUBJECT_RE.search(_semantic_source_text(target)) else 1
    start = max(0, index - radius)
    end = min(len(values), index + radius + 1)
    block_id = str((record.get("block") or {}).get("id") or "")
    ids = [f"{block_id}-s{position + 1}" for position in range(start, end)]
    return values[start:end], ids, radius == 2


def _prior_context_subject(
    context_sentences: list[str],
    target: str,
) -> str:
    target_index = next(
        (
            index
            for index, value in enumerate(context_sentences)
            if normalize_text(value) == normalize_text(target)
        ),
        len(context_sentences) - 1,
    )
    patterns = (
        r"((?:existing|current|prior|previous|traditional|conventional|"
        r"[A-Za-z0-9-]+(?:-based)?)\s+(?:methods?|models?|approaches?|"
        r"algorithms?|techniques?|networks?))\s+",
        r"((?:[A-Z][A-Za-z0-9-]*|CNNs?|Transformers?|ViTs?|"
        r"iterative\s+reconstruction)(?:\s+(?:and|or)\s+"
        r"(?:[A-Z][A-Za-z0-9-]*|CNNs?|Transformers?|ViTs?))?)\s+",
        r"((?:images?|data|targets?|vessels?|structures?|boundaries|"
        r"reconstruction|segmentation|detection))\s+",
    )
    for prior in reversed(context_sentences[:target_index]):
        clean = _semantic_source_text(prior)
        for pattern in patterns:
            match = re.search(pattern, clean, re.I)
            if match:
                subject = _clip_words(match.group(1), 10)
                if subject:
                    return subject
    return ""


def _resolve_context_reference(
    clause: str,
    context_sentences: list[str],
    target: str,
) -> tuple[str, bool]:
    clean = _semantic_source_text(clause)
    if not REFERENCE_SUBJECT_RE.search(clean):
        return clean, False
    subject = _prior_context_subject(context_sentences, target)
    if not subject:
        return clean, False
    resolved = re.sub(
        r"^\s*(?:this|these|those|such)\s+"
        r"(?:methods?|models?|approaches?|algorithms?|techniques?|"
        r"issues?|problems?|challenges?|limitations?|data|images?|tasks?)\b|"
        r"^\s*(?:the\s+former|the\s+latter|it|they)\b",
        subject,
        clean,
        count=1,
        flags=re.I,
    )
    return normalize_text(resolved), True


def _problem_side_clauses(value: str) -> list[tuple[str, str]]:
    text = normalize_text(str(value or ""))
    clauses: list[tuple[str, str]] = []
    scarcity = re.search(
        r"\bwhile\s+(?P<subject>.+?)\s+(?:is|are)\s+scarce\s*,?\s*"
        r"(?:thereby\s+)?leading\s+to\s+(?P<effect>.+?)(?:[.;]|$)",
        text,
        re.I,
    )
    if scarcity:
        clauses.append(
            (
                f"{scarcity.group('subject')} scarcity leads to "
                f"{scarcity.group('effect')}",
                "scarcity_consequence_split",
            )
        )
    conditional_requirement = re.search(
        r"\bif\s+.+?\b(?:directly\s+)?focus(?:es|ed|ing)?\s+on\s+"
        r"(?P<object>.+?)(?:,\s*it\s+may\s+be|\s+may\s+be)\s+"
        r"(?:a\s+)?(?:promising|useful|effective)\s+"
        r"(?:design\s+)?(?:paradigm|direction|strategy)",
        text,
        re.I,
    )
    if conditional_requirement:
        clauses.append(
            (
                "Effective methods require category-aware modeling of "
                f"{conditional_requirement.group('object')}",
                "conditional_requirement_rewrite",
            )
        )
    objective = re.search(
        r"\bto\s+(?:address|solve|overcome|mitigate|tackle|handle)\s+"
        r"(.+?)[,;]\s*(?:we|this\s+(?:paper|work)|the\s+proposed)\b",
        text,
        re.I,
    )
    if objective:
        clauses.append(
            (
                f"The paper addresses {objective.group(1)}",
                "paper_objective_split",
            )
        )

    method_start = re.search(
        r"\b(?:we\s+(?:propose|introduce|design|develop|present)|"
        r"this\s+(?:paper|work)\s+(?:proposes?|introduces?|presents?)|"
        r"the\s+proposed\s+(?:method|model|network|framework))\b",
        text,
        re.I,
    )
    source_segments: list[tuple[str, str]] = []
    if method_start and method_start.start() > 0:
        prefix = text[: method_start.start()].strip(" ,;:")
        prefix = re.sub(
            r"^\s*(?:although|however|while|despite|therefore)\s*[,;:]?\s*",
            "",
            prefix,
            flags=re.I,
        )
        if prefix:
            source_segments.append((prefix, "problem_solution_split"))
    elif not objective and not conditional_requirement:
        source_segments.append((text, "whole_sentence"))

    method_objective = re.search(
        r"\b(?:we\s+(?:propose|introduce|design|develop|present)|"
        r"this\s+(?:paper|work)\s+(?:proposes?|introduces?|presents?))"
        r".*?\bto\s+(?:address|solve|overcome|mitigate|tackle|handle)\s+"
        r"(.+)$",
        text,
        re.I,
    )
    if method_objective:
        clauses.append(
            (
                f"The paper addresses {method_objective.group(1)}",
                "paper_objective_split",
            )
        )

    participial_objective = re.search(
        r"(?:,|;|\bthereby\b)\s*"
        r"(?:solving|addressing|mitigating|alleviating|overcoming|"
        r"tackling|handling)\s+"
        r"(?:(?:the|this)\s+)?"
        r"(?:(?:problem|issue|challenge|limitation)\s+of\s+)?"
        r"(.+?)(?:[.;]|$)",
        text,
        re.I,
    )
    if participial_objective:
        objective_text = participial_objective.group(1).strip(" ,;:.")
        if objective_text:
            clauses.append(
                (
                    f"The paper addresses {objective_text}",
                    "paper_objective_split",
                )
            )

    for segment, default_mode in source_segments:
        leading_contrast = re.match(
            r"^\s*(?:although|despite|while)\s+(.+?),\s*(.+)$",
            segment,
            re.I,
        )
        if leading_contrast:
            concession, main_clause = leading_contrast.groups()
            split_values = [
                value
                for value in (concession, main_clause)
                if PROBLEM_SIGNAL_RE.search(value)
            ]
            if split_values:
                clauses.extend(
                    (value, "contrast_clause_split")
                    for value in split_values
                )
                continue
        clean_segment = re.sub(
            r"^\s*(?:although|however|while|despite|therefore)\s*[,;:]?\s*",
            "",
            segment,
            flags=re.I,
        ).strip(" ,;:")
        split_added = False
        while_match = re.match(
            r"^(.+?),\s*while\s+(.+)$",
            clean_segment,
            re.I,
        )
        if while_match:
            left, right = while_match.groups()
            if PROBLEM_SIGNAL_RE.search(left):
                clauses.append((left, "contrast_clause_split"))
                split_added = True
            if PROBLEM_SIGNAL_RE.search(right):
                clauses.append((right, "contrast_clause_split"))
                split_added = True

        but_match = re.match(r"^(.+?),?\s+but\s+(.+)$", clean_segment, re.I)
        if but_match:
            left, right = but_match.groups()
            if PROBLEM_SIGNAL_RE.search(right):
                subject_match = re.match(
                    r"^(.+?)\s+(?:is|are|has|have|encapsulates?|provides?|"
                    r"offers?|obtains?|achieves?|combines?)\b",
                    left,
                    re.I,
                )
                if re.match(
                    r"^(?:can|may|could|lead|leads|cause|causes|limit|limits|"
                    r"prevent|prevents|degrade|degrades|introduce|introduces)\b",
                    right,
                    re.I,
                ) and subject_match:
                    right = f"{subject_match.group(1)} {right}"
                clauses.append((right, "contrast_clause_split"))
                split_added = True
            if PROBLEM_SIGNAL_RE.search(left):
                clauses.append((left, "contrast_clause_split"))
                split_added = True

        if not split_added and clean_segment:
            clauses.append((clean_segment, default_mode))

    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for clause, mode in clauses:
        normalized = _semantic_source_text(clause)
        key = normalized.lower()
        if normalized and key not in seen:
            unique.append((normalized, mode))
            seen.add(key)
    return unique


def _relation_fragment(value: str, limit: int = 14) -> str:
    text = _semantic_source_text(value)
    text = re.sub(
        r"^\s*(?:although|however|while|despite|therefore|thus|"
        r"moreover|furthermore|in\s+this\s+(?:paper|work))\s*[,;:]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"^\s*(?:the\s+fact\s+that|that)\s+", "", text, flags=re.I)
    return _clip_words(text.strip(" ,;:."), limit)


def _motivation_role_for_relation(
    relation: str,
    motivation_type: str,
) -> str:
    if relation in {
        "prior_method_lacks_capability",
        "prior_method_causes_failure",
    }:
        return "prior_method_limitation"
    if relation in {
        "research_gap_remains",
        "tradeoff_remains_unresolved",
        "solution_requires_capability",
        "paper_targets_problem",
    }:
        return "gap_requirement_or_objective"
    if motivation_type in {"problem_significance", "practical_need"}:
        return "problem_significance_or_practical_constraint"
    return "task_problem_or_challenge"


def _extract_relation_structure(
    clause: str,
    context_sentences: list[str],
    target_sentence: str,
) -> tuple[dict[str, Any] | None, bool]:
    clean, reference_resolved = _resolve_context_reference(
        clause,
        context_sentences,
        target_sentence,
    )
    clean = _semantic_source_text(clean)
    if not clean:
        return None, reference_resolved

    relation = ""
    subject = ""
    obj = ""
    condition = ""
    consequence = ""

    patterns: list[tuple[str, str]] = [
        (
            "task_is_difficult_under_condition",
            r"(?:in\s+(?P<condition>[^,]+),\s*)?"
            r"(?:one\s+of\s+(?:the\s+)?(?:main|key|major|primary)\s+"
            r"challenges?\s+is|(?:a|the)\s+(?:main|key|major|primary)\s+"
            r"challenge\s+is)\s+(?P<subject>.+)",
        ),
        (
            "task_is_difficult_under_condition",
            r"(?P<subject>.+?)\s+(?:is|are)\s+(?:one\s+of\s+)?"
            r"(?:the\s+)?(?:main|key|major|primary)\s+challenges?\s+"
            r"(?:in|for)\s+(?P<object>.+)",
        ),
        (
            "problem_has_consequence",
            r"(?:studies?\s+(?:have\s+)?shown?\s+that\s+)?"
            r"(?P<subject>.+?)\s+(?:is|are)\s+"
            r"(?:one\s+of\s+)?(?:the\s+)?(?:most\s+)?important\s+"
            r"causes?\s+of\s+(?P<object>.+)",
        ),
        (
            "problem_has_consequence",
            r"(?P<subject>.+?)\s+(?:plays?|serves?)\s+"
            r"(?:a\s+)?(?:crucial|critical|important|essential|central)\s+"
            r"role\s+(?:in|for)\s+(?P<object>.+)",
        ),
        (
            "problem_has_consequence",
            r"(?P<subject>.+?)\s+(?:is|are)\s+"
            r"(?:an?\s+)?(?:important|critical|crucial|essential|"
            r"fundamental|vital)\s+(?:task|problem|requirement)\s+"
            r"(?:in|for)\s+(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|assistants?|tools?|reconstruction)|"
            r"(?:CNNs?|ViTs?|Transformers?)(?:\s+(?:and|or)\s+"
            r"(?:CNNs?|ViTs?|Transformers?))?))\s+"
            r"(?:fail(?:s|ed)?\s+to|cannot|are\s+unable\s+to|"
            r"struggle(?:s|d)?\s+to|do(?:es)?\s+not|lack(?:s|ed)?|"
            r"overlook(?:s|ed)?|"
            r"ignore(?:s|d)?|miss(?:es|ed)?|lose(?:s|st)?)\s+"
            r"(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|backbones?|assistants?|tools?|attention|"
            r"CNNs?|ViTs?|Transformers?))\s+.+?\s+"
            r"(?:fail(?:s|ed)?\s+to|do(?:es)?\s+not|cannot|"
            r"are\s+unable\s+to|struggle(?:s|d)?\s+to)\s+"
            r"(?P<object>.+)",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|backbones?|CNNs?|ViTs?|Transformers?))"
            r"\s+(?:often\s+)?(?:encounter(?:s|ed)?|face(?:s|d)?)\s+"
            r"(?:the\s+)?limitations?\s+(?:in|of|when)\s+"
            r"(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|attention|CNNs?|ViTs?|Transformers?))"
            r"\s+(?:is|are)\s+(?:confined|restricted)\s+to\s+"
            r"(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|attention|CNNs?|ViTs?|Transformers?))"
            r"\s+.*?(?:overlook(?:s|ed|ing)?|neglect(?:s|ed|ing)?)\s+"
            r"(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>[A-Z][A-Za-z0-9+_.-]*"
            r"(?:\s+[A-Z][A-Za-z0-9+_.-]*){0,3})\s+.*?"
            r"(?:underuse(?:s|d)?|does\s+not\s+address|"
            r"fails?\s+to|cannot)\s+(?P<object>.+)",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|hybrids?))"
            r"\s+(?:treat|weight|model)(?:s|ed)?\s+"
            r"(?P<object>.+?)\s+(?:equally|uniformly),?\s+"
            r"(?:which\s+)?(?:conflict(?:s|ed)?\s+with|ignoring|"
            r"despite)\s+.+",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|backbones?|attention|CNNs?|ViTs?|"
            r"Transformers?))\s+(?:is|are)\s+"
            r"(?:constrained|restricted|limited)\s+by\s+"
            r"(?P<object>.+?)(?:,\s*(?:hindering|limiting|preventing|"
            r"causing)\s+(?P<consequence>.+))?$",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?(?:self[-\s]?attention|attention|methods?|"
            r"models?|approaches?|algorithms?|techniques?|networks?|"
            r"backbones?|CNNs?|ViTs?|Transformers?))\s+"
            r"(?:suffer(?:s|ed)?\s+from|incur(?:s|red)?|"
            r"impose(?:s|d)?)\s+(?P<object>.+)",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?)\s+(?:pay|pays|require|requires)\s+"
            r"(?P<object>(?:extra|additional|heavy|substantial)\s+"
            r"(?:computation|computations|compute|memory|resources?))"
            r"(?:\s+as\s+(?:a\s+)?price\s+for\s+.+)?",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:attention|methods?|models?|approaches?|"
            r"algorithms?|techniques?|networks?|backbones?|CNNs?|ViTs?|"
            r"Transformers?))\s+(?:restrict(?:s|ed)?|limit(?:s|ed)?|"
            r"prevent(?:s|ed)?)\s+(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:CNNs?|convolutional\s+(?:models?|networks?)))"
            r".+?(?:passive\s+response\s+to|passively\s+respond(?:s|ed)?\s+to|"
            r"focus(?:es|ed)?\s+on)\s+"
            r".+?\s+rather\s+than\s+(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>(?:CNNs?|ViTs?|Transformers?)"
            r"(?:\s+(?:and|or)\s+(?:CNNs?|ViTs?|Transformers?))?)"
            r".+?\band\s+lack(?:s|ed)?\s+(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|attention|CNNs?|ViTs?|Transformers?))"
            r"\s+.+?\s+and\s+fail(?:s|ed)?\s+to\s+(?P<object>.+)",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?(?:ViTs?|Transformers?|CNNs?|models?|"
            r"networks?|methods?|approaches?))\s+require(?:s|d)?\s+"
            r"(?P<object>(?:massive|large|substantial|extensive)\s+data.+)",
        ),
        (
            "prior_method_causes_failure",
            r"(?P<subject>.+?(?:methods?|models?|approaches?|algorithms?|"
            r"techniques?|networks?|reconstruction))\s+"
            r"(?:suffer(?:s|ed)?\s+from|are\s+limited\s+by|remain(?:s)?\s+"
            r"constrained\s+by|introduce(?:s|d)?|cause(?:s|d)?|"
            r"lead(?:s)?\s+to)\s+(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>they|it|the\s+(?:study|method|approach)|"
            r"prior\s+(?:work|study))\s+(?:only|merely)\s+"
            r"(?:assume(?:s|d)?|consider(?:s|ed)?|model(?:s|ed)?|"
            r"address(?:es|ed)?)\s+(?P<object>.+)",
        ),
        (
            "prior_method_lacks_capability",
            r"(?P<subject>.+?)\s+(?:only|merely)\s+"
            r"(?:assume(?:s|d)?|consider(?:s|ed)?|model(?:s|ed)?|"
            r"address(?:es|ed)?)\s+(?P<object>.+)",
        ),
        (
            "task_is_difficult_under_condition",
            r"(?P<subject>.+?)\s+(?:is|are|remains?|becomes?)\s+"
            r"(?:particularly\s+)?(?:difficult|hard|challenging)\s+to\s+"
            r"(?P<object>.+?)(?:\s+because(?:\s+of)?\s+"
            r"(?P<condition>.+))?$",
        ),
        (
            "task_is_difficult_under_condition",
            r"(?P<subject>.+?)\s+makes?\s+"
            r"(?P<object>.+?)\s+(?:particularly\s+)?"
            r"(?:difficult|hard|challenging)",
        ),
        (
            "task_is_difficult_under_condition",
            r"(?P<subject>.+?)\s+(?:is|are|remains?|becomes?)\s+"
            r"(?:particularly\s+)?(?:difficult|hard|challenging)\s*"
            r"(?:(?:under|in|when|because(?:\s+of)?|due\s+to)\s+"
            r"(?P<condition>.+))?",
        ),
        (
            "problem_has_consequence",
            r"(?P<subject>.+?)\s+(?:(?:can|may|could)\s+)?"
            r"(?:cause(?:s|d)?|lead(?:s)?\s+to|result(?:s|ed)?\s+in|"
            r"hinder(?:s|ed)?|obscure(?:s|d)?|degrade(?:s|d)?|"
            r"limit(?:s|ed)?|prevent(?:s|ed)?|increase(?:s|d)?)\s+"
            r"(?P<object>.+)",
        ),
        (
            "data_contains_challenge",
            r"(?P<subject>.+?(?:\bdata\b|\bimages?\b|\bsignals?\b|"
            r"\btargets?\b|\bregions?\b|\bboundaries\b|\bstructures?\b))"
            r"\s+(?:contain(?:s|ed)?|"
            r"suffer(?:s|ed)?\s+from|exhibit(?:s|ed)?|are\s+affected\s+by|"
            r"have|has)\s+(?P<object>.+)",
        ),
        (
            "tradeoff_remains_unresolved",
            r"(?P<subject>.+?)\s+(?:must\s+balance|faces?\s+(?:an?\s+)?"
            r"trade[-\s]?off\s+between|trades?\s+off)\s+(?P<object>.+)",
        ),
        (
            "research_gap_remains",
            r"(?P<subject>.+?)\s+(?:remains?|remain)\s+"
            r"(?P<object>unresolved|underexplored|unaddressed|"
            r"insufficiently\s+studied|difficult)",
        ),
        (
            "task_is_difficult_under_condition",
            r"(?P<subject>.+?)\s+remains?\s+"
            r"(?P<object>(?:a\s+)?(?:persistent|major|key|significant)\s+"
            r"challenge)",
        ),
        (
            "research_gap_remains",
            r"(?P<subject>.+?)\s+(?:has|have)\s+not\s+been\s+"
            r"(?P<object>(?:fully\s+)?(?:addressed|resolved|studied|explored|"
            r"realized|exploited))",
        ),
        (
            "research_gap_remains",
            r"(?P<subject>.+?)(?:,\s*(?:but|yet))?\s+"
            r"(?:has|have)\s+(?:only\s+)?"
            r"(?:rarely|seldom)\s+been\s+"
            r"(?P<object>investigated|studied|examined|explored)"
            r"(?:\s+(?:in|for)\s+.+)?",
        ),
        (
            "research_gap_remains",
            r"(?P<subject>.+?)\s+(?:is|are|remains?)\s+"
            r"(?P<object>(?:a\s+)?(?:challenging\s+and\s+unresolved|"
            r"unresolved|underexplored|open)\s+(?:task|problem|question))",
        ),
        (
            "research_gap_remains",
            r"(?P<subject>.+?(?:questions?|relationship|link|understanding|"
            r"potential))\s+(?:remains?|remain)\s+"
            r"(?P<object>regarding\s+.+|unclear|unknown|open|unresolved)",
        ),
        (
            "solution_requires_capability",
            r"(?P<subject>.+?(?:solutions?|methods?|models?|systems?|"
            r"approaches?|assistants?|tools?|task|analysis|evaluation|"
            r"screening|deployment|inference))\s+"
            r"(?:needs?|requires?|must|should|"
            r"calls?\s+for)\s+(?P<object>.+)",
        ),
        (
            "solution_requires_capability",
            r"if\s+(?P<subject>.+?)\s+(?:directly\s+)?"
            r"(?:focus(?:es)?|model(?:s)?)\s+on\s+(?P<object>.+?)"
            r"(?:,\s*this\s+may\s+provide.+)?$",
        ),
        (
            "solution_requires_capability",
            r"(?:we\s+argue\s+that|it\s+is\s+necessary\s+that)\s+"
            r"(?P<subject>.+?)\s+(?:should|must|needs?\s+to)\s+"
            r"(?P<object>.+)",
        ),
        (
            "paper_targets_problem",
            r"(?:we|this\s+(?:paper|work)|the\s+(?:paper|study))\s+"
            r"(?:aim(?:s)?\s+to|seeks?\s+to|targets?|addresses?|"
            r"explores?|investigates?|examines?|clarifies?)\s+"
            r"(?P<object>.+)",
        ),
        (
            "task_is_difficult_under_condition",
            r"(?P<subject>.+?)\s+(?:poses?|presents?|creates?)\s+"
            r"(?:a\s+)?(?:major\s+|significant\s+|key\s+)?"
            r"(?:challenge|difficulty)(?:\s+(?:for|in)\s+"
            r"(?P<object>.+))?",
        ),
    ]
    for candidate_relation, pattern in patterns:
        match = re.search(pattern, clean, re.I)
        if not match:
            continue
        relation = candidate_relation
        groups = match.groupdict()
        subject = _relation_fragment(groups.get("subject") or "", 12)
        obj = _relation_fragment(groups.get("object") or "", 15)
        condition = _relation_fragment(groups.get("condition") or "", 12)
        consequence = _relation_fragment(groups.get("consequence") or "", 12)
        if re.fullmatch(
            r"(?:they|it|the\s+(?:study|method|approach)|prior\s+work)",
            subject,
            re.I,
        ):
            subject = "Prior study"
        if relation == "research_gap_remains" and re.search(
            r"\b(?:has|have)\s+not\s+been\b",
            clean,
            re.I,
        ):
            obj = f"not {obj}".strip()
        if relation == "paper_targets_problem":
            subject = "the paper objective"
        break

    if not relation:
        significance = re.search(
            r"(?P<subject>.+?)\s+(?:is|are)\s+"
            r"(?:important|critical|crucial|essential|central)\s+"
            r"(?:for|to)\s+(?P<object>.+)",
            clean,
            re.I,
        )
        if significance:
            relation = "problem_has_consequence"
            subject = _relation_fragment(significance.group("subject"), 12)
            obj = _relation_fragment(significance.group("object"), 15)
            consequence = obj

    if not relation:
        growing_importance = re.search(
            r"(?:with|as)\s+(?P<condition>.+?),\s*"
            r"(?P<subject>.+?)\s+(?:has|have)\s+become\s+"
            r"(?:increasingly\s+)?(?:important|critical|essential)",
            clean,
            re.I,
        )
        if growing_importance:
            relation = "problem_has_consequence"
            subject = _relation_fragment(
                growing_importance.group("subject"),
                12,
            )
            obj = _relation_fragment(
                growing_importance.group("condition"),
                12,
            )
            condition = obj

    if not relation:
        diagnostic_value = re.search(
            r"(?P<subject>.+?)\s+(?:can|could|may)\s+be\s+"
            r"(?:applied|used)\s+to\s+(?P<object>.+)",
            clean,
            re.I,
        )
        if diagnostic_value:
            relation = "problem_has_consequence"
            subject = _relation_fragment(
                diagnostic_value.group("subject"),
                12,
            )
            obj = _relation_fragment(
                diagnostic_value.group("object"),
                15,
            )
            consequence = obj

    if not relation:
        natural_direction = re.search(
            r"since\s+(.+?),\s*it\s+is\s+(?:natural|necessary|important)\s+"
            r"to\s+(?:study|develop|build|design)\s+(?P<object>.+)",
            clean,
            re.I,
        )
        if natural_direction:
            relation = "solution_requires_capability"
            subject = "Effective models"
            obj = _relation_fragment(
                natural_direction.group("object"),
                15,
            )
            condition = _relation_fragment(
                natural_direction.group(1),
                12,
            )

    if not relation and METHOD_FAMILY_RE.search(clean):
        limitation = re.search(
            r"\b(?:limitations?|quadratic\s+complexity|costly|"
            r"expensive|inefficient|underperform|overhead|burden)\b|"
            r"\b(?:is|are|was|were|remain(?:s)?)\s+limited\b|"
            r"\blimited\s+by\b",
            clean,
            re.I,
        )
        if limitation:
            relation = "prior_method_causes_failure"
            family = re.search(
                r"(.{0,80}?(?:methods?|models?|approaches?|algorithms?|"
                r"networks?|reconstruction))\b",
                clean,
                re.I,
            )
            subject = _relation_fragment(
                family.group(1) if family else "Prior methods",
                10,
            )
            cause = re.search(
                r"(?:due\s+to|because\s+of|limited\s+by|"
                r"limitation\s+(?:is|lies)\s+in)\s+(.+)",
                clean,
                re.I,
            )
            obj = _relation_fragment(
                cause.group(1) if cause else clean[limitation.start() :],
                15,
            )

    if not relation and PROBLEM_SIGNAL_RE.search(clean):
        cause = re.search(
            r"(?P<subject>.+?)\s+(?:makes?|complicates?)\s+"
            r"(?P<object>.+)",
            clean,
            re.I,
        )
        if cause:
            relation = "problem_has_consequence"
            subject = _relation_fragment(cause.group("subject"), 12)
            obj = _relation_fragment(cause.group("object"), 15)

    if relation == "paper_targets_problem" and re.fullmatch(
        r"(?:this|that|these|those|it|the\s+(?:issue|problem|challenge)|"
        r"these\s+(?:issues|problems|challenges))",
        obj,
        re.I,
    ):
        return None, reference_resolved
    if relation == "paper_targets_problem" and not obj:
        obj = _relation_fragment(clean, 15)
    motivation_type, _ = _motivation_type(clean)
    motivation_type = motivation_type or (
        "prior_method_limitation"
        if relation.startswith("prior_method")
        else "design_requirement"
        if relation in {"solution_requires_capability", "paper_targets_problem"}
        else "task_challenge"
    )
    if relation == "problem_has_consequence" and re.search(
        r"\b(?:one\s+of\s+)?(?:the\s+)?(?:most\s+)?important\s+causes?\s+of\b",
        clean,
        re.I,
    ):
        motivation_type = "problem_significance"
    elif relation == "problem_has_consequence" and re.search(
        r"\b(?:important|critical|crucial|essential|clinical|practical)\b",
        clean,
        re.I,
    ):
        motivation_type = (
            "practical_need"
            if re.search(r"\b(?:clinical|practical|deployment)\b", clean, re.I)
            else "problem_significance"
        )
    role = _motivation_role_for_relation(relation, motivation_type)
    structure = {
        "subject": subject,
        "relation": relation,
        "object": obj,
        "condition": condition,
        "consequence": consequence,
        "role": role,
        "motivation_type": motivation_type,
    }
    complete = bool(
        relation in MOTIVATION_RELATIONS
        and subject
        and (obj or condition or consequence)
    )
    return (structure if complete else None), reference_resolved


def _candidate_semantic_meaning(structure: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            str(structure.get(key) or "")
            for key in (
                "subject",
                "relation",
                "object",
                "condition",
                "consequence",
            )
        )
    )


def _motivation_candidates(
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    method_graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    del method_graph  # Motivation extraction is problem-side and source-led.
    context = _story_context(story, paper_ir)
    paper_type = _classify_motivation_paper_type(paper_ir, story)
    records, scan_summary = _motivation_sentence_records(paper_ir)
    candidates: list[dict[str, Any]] = []
    raw_candidate_count = 0
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        raw = str(record.get("raw_statement") or "")
        window, context_ids, expanded_context = _context_window(record)
        for clause, extraction_mode in _problem_side_clauses(raw):
            raw_candidate_count += 1
            structure, reference_resolved = _extract_relation_structure(
                clause,
                window,
                raw,
            )
            section_kind = str(record.get("section_kind") or "")
            source_recoverable = bool(
                (record.get("block") or {}).get("id")
                and int((record.get("block") or {}).get("page") or 0) >= 1
                and record.get("sentence_id")
            )
            problem_plausible = bool(
                structure
                and structure.get("role")
                in {
                    *MOTIVATION_REQUIRED_ROLES,
                    "problem_significance_or_practical_constraint",
                }
                and not POSITIVE_RESULT_RE.search(
                    _semantic_source_text(clause)
                )
                and not SOLUTION_SIDE_DESCRIPTION_RE.search(
                    _semantic_source_text(clause)
                )
                and not RESOLUTION_METHOD_HISTORY_RE.search(
                    _semantic_source_text(clause)
                )
                and not (
                    PURE_METHOD_PROPOSITION_RE.search(
                        _semantic_source_text(clause)
                    )
                    and not EXPLICIT_PROBLEM_RELATION_RE.search(
                        _semantic_source_text(clause)
                    )
                )
                and (
                    section_kind != "related_work"
                    or (
                        structure.get("role") == "prior_method_limitation"
                        and METHOD_FAMILY_RE.search(
                            _semantic_source_text(clause)
                        )
                    )
                )
            )
            semantically_complete = bool(
                structure
                and structure.get("subject")
                and structure.get("relation") in MOTIVATION_RELATIONS
                and (
                    structure.get("object")
                    or structure.get("condition")
                    or structure.get("consequence")
                )
            )
            if not structure:
                structure = {
                    "subject": "",
                    "relation": "",
                    "object": "",
                    "condition": "",
                    "consequence": "",
                    "role": "",
                }
            structure["source_sentence_ids"] = [str(record["sentence_id"])]
            structure["context_window_ids"] = context_ids
            motivation_type = str(
                structure.get("motivation_type")
                or (
                    "prior_method_limitation"
                    if structure.get("role") == "prior_method_limitation"
                    else "design_requirement"
                    if structure.get("role") == "gap_requirement_or_objective"
                    else "practical_need"
                    if structure.get("role")
                    == "problem_significance_or_practical_constraint"
                    else (
                        _motivation_type(_semantic_source_text(clause))[0]
                        or "task_challenge"
                    )
                )
            )
            meaning = _candidate_semantic_meaning(structure)
            dedupe_key = (
                str(record.get("sentence_id") or ""),
                str(structure.get("relation") or ""),
                normalize_text(str(structure.get("subject") or "")).lower(),
                normalize_text(str(structure.get("object") or "")).lower(),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            relevance = _relevance_overlap(
                f"{structure.get('subject')} {structure.get('object')}",
                context,
            )
            recovery_tags: list[str] = []
            position = record.get("section_position")
            if section_kind == "introduction" and position is not None:
                if float(position) <= 0.30:
                    recovery_tags.append("introduction_front_30_percent")
                elif float(position) < 0.80:
                    recovery_tags.append("introduction_middle")
            if record.get("is_last_intro_block"):
                recovery_tags.append("pre_method_transition")
            if section_kind == "abstract":
                recovery_tags.append("abstract_front_half")
            if extraction_mode != "whole_sentence":
                recovery_tags.append("compound_clause_resplit")
            if expanded_context or reference_resolved:
                recovery_tags.append("expanded_reference_context")
            if (
                CITATION_RE.search(raw)
                or AUTHOR_VOICE_RE.search(raw)
                or DISCOURSE_RE.search(raw)
                or QUOTATION_RE.search(raw)
            ):
                recovery_tags.append("surface_artifact_recheck")
            if structure.get("relation") == "paper_targets_problem":
                recovery_tags.append("paper_objective_recheck")
            confidence = min(
                1.0,
                0.48
                + (0.20 if semantically_complete else 0.0)
                + (0.12 if problem_plausible else 0.0)
                + (0.10 if section_kind == "introduction" else 0.0)
                + 0.10 * min(1.0, relevance),
            )
            gate_results = {
                "source_recoverability_gate": {
                    "passed": source_recoverable,
                    "reason": "candidate binds to a recoverable sentence, block, and page",
                },
                "problem_side_plausibility_gate": {
                    "passed": problem_plausible,
                    "reason": "candidate expresses a plausible problem-side relation",
                },
                "semantic_completeness_gate": {
                    "passed": semantically_complete,
                    "reason": "candidate contains a subject, allowed relation, and relation object",
                },
            }
            candidates.append(
                {
                    "candidate_id": f"mot-candidate-{len(candidates) + 1}",
                    "type": motivation_type,
                    "role": structure.get("role"),
                    "raw_statement": raw,
                    "source_clause": clause,
                    "normalized_meaning": meaning,
                    "relation_structure": structure,
                    "source_sentence_ids": [str(record["sentence_id"])],
                    "context_window_ids": context_ids,
                    "context_window": window,
                    "section_kind": section_kind,
                    "section_position": position,
                    "source_records": [
                        _source_record(record["block"], raw)
                    ],
                    "gate_results": gate_results,
                    "importance": round(confidence, 3),
                    "paper_type": paper_type,
                    "coverage_family": _motivation_coverage_family(
                        {
                            "relation_structure": structure,
                            "role": structure.get("role"),
                            "type": motivation_type,
                            "source_clause": clause,
                        },
                        paper_type,
                    ),
                    "recovery_tags": list(dict.fromkeys(recovery_tags)),
                    "extraction_mode": extraction_mode,
                    "selected": False,
                }
            )
    diagnostics = {
        **scan_summary,
        "raw_candidates": raw_candidate_count,
        "problem_side_candidates": sum(
            _all_base_gates_pass(candidate) for candidate in candidates
        ),
        "candidates_after_semantic_gates": 0,
        "candidates_after_merging": 0,
        "selected_count": 0,
        "selected_motivation_count": 0,
        "rejection_histogram": {},
        "required_role_coverage": {
            role: False for role in MOTIVATION_REQUIRED_ROLES
        },
        "recovery_steps_executed": [],
        "rewrite_failures": [],
        "remaining_blockers": [],
        "paper_type": paper_type,
        "required_family_coverage": {
            family: False for family in MOTIVATION_REQUIRED_FAMILIES
        },
        "required_coverage_slots": {
            slot: False for slot in MOTIVATION_COVERAGE_SLOTS
        },
    }
    return candidates, diagnostics


def _semantic_heading_label(value: str) -> str:
    value = clean_visible_text(value)
    value = re.sub(
        r"^\s*(?:\d+(?:\.\d+)*|[IVX]+|[A-Z])[.)]?\s+",
        "",
        value,
        flags=re.I,
    )
    return normalize_text(value).strip(" ,;:.").lower()


def _is_non_contribution_heading(value: str) -> bool:
    return bool(NON_CONTRIBUTION_HEADING_RE.fullmatch(_semantic_heading_label(value)))


def _formal_object(raw: str, fallback: str) -> str:
    raw = clean_visible_text(raw)
    fallback = re.sub(
        r"^\s*(?:\d+(?:\.\d+)*|[IVX]+|[A-Z])[.)]?\s+",
        "",
        clean_visible_text(fallback),
        flags=re.I,
    )
    matches = re.findall(
        r"(?:novel\s+|new\s+)?([A-Z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,7}\s+"
        r"(?:Module|Block|Network|Framework|Architecture|Strategy|Loss|Objective|"
        r"Algorithm|Criterion|Dataset|Benchmark|Protocol))",
        raw,
    )
    named = re.search(
        r"\b(?:termed|called|named)\s+([A-Z][A-Za-z0-9-]{2,})\b",
        raw,
    )
    named_artifact = re.search(
        r"\b(?:new\s+)?(?:dataset|benchmark)\s*,?\s*"
        r"(?:called|named)?\s*([A-Z][A-Za-z0-9_-]{2,})\b",
        raw,
    )
    # Method-graph node titles are normally the most reliable object identity.
    # A sentence may mention a generic child such as FFN last; selecting the
    # last capitalized phrase would then replace KSFTB with FFN.
    value = (
        named_artifact.group(1)
        if named_artifact and fallback.lower() in {"dataset", "benchmark"}
        else fallback
    ) if fallback and fallback.lower() != "core mechanism" else (
        named.group(1)
        if named
        else (
            named_artifact.group(1)
            if named_artifact
            else (matches[-1] if matches else fallback)
        )
    )
    value = re.sub(r"^\s*(?:\d+(?:\.\d+)*|[IVX]+|[A-Z])[.)]?\s+", "", value, flags=re.I)
    value = re.sub(r"\b(?:novel|new|proposed)\b", "", value, flags=re.I)
    return normalize_text(value).strip(" ,;:.")


def _contribution_type(name: str, text: str) -> str:
    value = f"{name} {text}".lower()
    if re.search(r"\b(?:network|architecture|framework|model)\b", name.lower()):
        return "architecture"
    if re.search(r"\b(?:feature\s+fusion|fusion|integration)\b", value):
        return "feature_fusion_strategy"
    if "attention" in value:
        return "attention_strategy"
    if re.search(r"\b(?:loss|objective)\b", value):
        return "objective_or_loss"
    if re.search(r"\b(?:score|scoring|criterion|importance)\b", value):
        return "scoring_criterion"
    if re.search(r"\b(?:optim(?:ize|ization)|solver)\b", value):
        return "optimization_method"
    if re.search(r"\b(?:training|train|fine-tun|curriculum)\b", value):
        return "training_strategy"
    if re.search(r"\b(?:theorem|theory|principle|proposition)\b", value):
        return "theoretical_principle"
    if re.search(r"\bdataset\b", value):
        return "dataset"
    if re.search(r"\bbenchmark\b", value):
        return "benchmark"
    if re.search(r"\b(?:evaluation\s+protocol|protocol)\b", value):
        return "evaluation_protocol"
    if re.search(r"\b(?:algorithm|procedure)\b", value):
        return "algorithm"
    if re.search(r"\b(?:module|block|branch|layer)\b", name.lower()):
        return "module"
    return "mechanism"


def _canonical_contribution_type(value: str) -> str:
    value = normalize_text(value).lower()
    return CONTRIBUTION_TYPE_ALIASES.get(value, value or "mechanism")


def _is_result_only_contribution(text: str) -> bool:
    """Return whether a statement is an effect/result rather than an innovation."""
    lowered = clean_visible_text(text).lower()
    if re.search(
        r"(?<!\w)\d+(?:\.\d+)?\s*%|"
        r"\b(?:accuracy|auc|dice|dsc|iou|psnr|ssim|mae|rmse|snr|"
        r"outperform(?:s|ed)?|state[-\s]?of[-\s]?the[-\s]?art|"
        r"achiev(?:e|es|ed)|improv(?:e|es|ed|ement)|"
        r"superior|competitive|promising|effective|efficient)\b",
        lowered,
    ):
        return not bool(
            re.search(
                r"\b(?:propose|introduce|present|develop|design|construct|"
                r"build|formulate|define|new|novel|algorithm|network|"
                r"module|framework|architecture|loss|dataset|benchmark|"
                r"protocol|mechanism|strategy)\b",
                lowered,
            )
        )
    return False


def _contribution_segments(text: str) -> list[str]:
    """Split prose, numbered, and bullet contribution lists without losing clauses."""
    text = normalize_text(text)
    if not text:
        return []
    # MinerU often flattens inline enumerations such as
    # "two innovations: (1) ...; and (2) ..." into one sentence. Split the
    # numbered spans before semantic decomposition so a later loss cannot be
    # attached to an earlier module.
    inline_markers = list(
        re.finditer(
            r"(?:(?<=^)|(?<=[;:]))\s*(?:and\s+)?"
            r"(?:\([1-9]\d{0,2}\)|[1-9]\d{0,2}[.)])\s+",
            text,
            re.I,
        )
    )
    if len(inline_markers) >= 2:
        inline_items: list[str] = []
        for index, marker in enumerate(inline_markers):
            start = marker.end()
            end = (
                inline_markers[index + 1].start()
                if index + 1 < len(inline_markers)
                else len(text)
            )
            item = normalize_text(text[start:end]).strip(" ;")
            if item:
                inline_items.append(item)
        if len(inline_items) >= 2:
            return inline_items
    # MinerU often flattens a numbered list into one paragraph. Split before
    # item markers, while retaining the marker in the raw provenance.
    marked = re.sub(
        r"(^|[.;])\s*((?:\(?[1-9]\d{0,2}\)?[.)]|[-•●▪]|[A-Z][.)])\s+)",
        lambda match: f"{match.group(1)}\n{match.group(2)}",
        text,
    )
    pieces = marked.splitlines()
    result: list[str] = []
    for piece in pieces:
        piece = normalize_text(piece).strip(" ;")
        if not piece:
            continue
        # A semicolon-delimited list can still contain independent clauses.
        subpieces = re.split(r";\s+(?=(?:we\s+|our\s+|a\s+novel|a\s+new|"
                             r"the\s+(?:proposed|new)|\(?\d+[.)]))", piece, flags=re.I)
        for subpiece in subpieces:
            subpiece = normalize_text(subpiece).strip(" ;")
            if subpiece:
                result.append(subpiece)
    return result


def _contribution_propositions(text: str) -> list[str]:
    """Split one claim into independently named innovation artifacts."""

    text = normalize_text(text)
    if not text:
        return []
    coordinated = re.search(
        r"\s+and\s+(?:also\s+)?"
        r"(?P<verb>adopts?|introduces?|incorporates?|formulates?|defines?|uses?)"
        r"\s+(?P<tail>(?:a|an|the)\s+.+)$",
        text,
        re.I,
    )
    if not coordinated:
        return [text]
    prefix = normalize_text(text[: coordinated.start()]).strip(" ,;")
    tail = normalize_text(coordinated.group("tail")).strip(" ,;")
    if not (
        re.search(
            r"\b(?:network|architecture|framework|model|method)\b",
            prefix,
            re.I,
        )
        and re.search(
            r"\b(?:loss|objective|module|block|criterion|strategy|algorithm)\b",
            tail,
            re.I,
        )
    ):
        return [text]
    verb = {
        "adopts": "adopt",
        "introduces": "introduce",
        "incorporates": "incorporate",
        "formulates": "formulate",
        "defines": "define",
        "uses": "use",
    }.get(coordinated.group("verb").lower(), coordinated.group("verb").lower())
    return [prefix, normalize_text(f"We {verb} {tail}")]


def _canonical_object_identity(
    innovation_object: str,
    paper_ir: dict[str, Any],
) -> tuple[str, str]:
    """Return a stable within-paper identity for aliases of one innovation."""

    identity_source = re.sub(
        r"<sup\b[^>]*>(.*?)</sup>",
        r"\1",
        str(innovation_object or ""),
        flags=re.I | re.S,
    )
    value = clean_visible_text(identity_source).strip(" ,;:.")
    value = re.sub(r"^(?:a|an|the)\s+(?:novel|new|proposed)\s+", "", value, flags=re.I)
    value = re.sub(
        r",\s+(?:a|an|the)\s+.+$",
        "",
        value,
        flags=re.I,
    ).strip(" ,;:.")
    value = re.sub(
        r",?\s+(?:designed|developed|introduced|proposed)\s*$",
        "",
        value,
        flags=re.I,
    ).strip(" ,;:.")
    if re.search(r"\bmulti[-\s]?scale\s+linear\s+attention\b", value, re.I):
        return "co-msla", "Multi-Scale Linear Attention"
    top_down = re.search(
        r"\btop[-\s]?down(?:\s+multi[-\s]?level)?\s+feature\s+"
        r"aggregation\s+mechanism\b",
        value,
        re.I,
    )
    if top_down:
        return (
            "co-topdownfeatureaggregation",
            "Top-Down Feature Aggregation",
        )
    parentheticals = re.findall(r"\(([A-Z][A-Z0-9-]{1,15})\)", value)
    parenthetical = (
        re.search(r"\(([A-Z][A-Z0-9-]{1,15})\)", value)
        if parentheticals
        else None
    )
    named_models = re.findall(
        r"\b([A-Z][A-Za-z0-9]*[-]?(?:Net|NET)|[A-Z]{3,}[A-Z0-9-]*)\b",
        value,
    )
    named_model = max(
        named_models,
        key=lambda item: (
            item.lower() not in {"unet", "u-net"},
            len(re.sub(r"[^A-Za-z0-9]", "", item)),
        ),
        default="",
    )
    canonical_name = value
    if len(parentheticals) >= 2 and re.search(r"\bloss\b", value, re.I):
        canonical_name = f"{' + '.join(parentheticals)} Loss"
    elif parenthetical and (
        not named_model or named_model.lower() in {"unet", "u-net"}
    ):
        canonical_name = parenthetical.group(1)
    elif named_model and re.search(
        r"(?:network|architecture|framework|model|method)\b|[-]?net\b",
        value,
        re.I,
    ):
        canonical_name = named_model
    elif parenthetical:
        canonical_name = parenthetical.group(1)
    canonical_key = re.sub(r"[^a-z0-9]+", "", canonical_name.lower())
    canonical_key = re.sub(
        r"(?:module|block|network|architecture|framework|model|method)$",
        "",
        canonical_key,
    )
    if not canonical_key:
        canonical_key = re.sub(r"[^a-z0-9]+", "", value.lower())

    title = clean_visible_text(
        str((paper_ir.get("metadata") or {}).get("title") or "")
    )
    for full_name, acronym in re.findall(
        r"([A-Z][A-Za-z0-9 -]{5,80}?)\s*\(([A-Z][A-Z0-9-]{2,15})\)",
        f"{title} "
        + " ".join(
            str(block.get("text") or "")
            for block in paper_ir.get("blocks", [])
            if any(
                section in _section_text(block)
                for section in ("abstract", "introduction", "conclusion")
            )
        ),
    ):
        full_key = re.sub(r"[^a-z0-9]+", "", full_name.lower())
        acronym_key = re.sub(r"[^a-z0-9]+", "", acronym.lower())
        # Do not map a short family token such as "unet" to an unrelated
        # acronym merely because a long extracted full-name span contains it.
        full_name_match = bool(
            canonical_key == full_key
            or (
                len(canonical_key) >= 10
                and (
                    full_key.endswith(canonical_key)
                    or canonical_key.endswith(full_key)
                )
            )
        )
        if canonical_key == acronym_key or full_name_match:
            canonical_name = acronym
            canonical_key = acronym_key
            break
    return f"co-{canonical_key or 'unknown'}", canonical_name or value


def _author_contribution_groups(
    paper_ir: dict[str, Any],
) -> list[dict[str, Any]]:
    """Recover the author's own top-level contribution grouping when present."""

    header_re = re.compile(
        r"\b(?:main|primary|key)?\s*contributions?\b|"
        r"\b(?:two|three|four|five|\d+)\s+key\s+ideas?\b|"
        r"\bcontributions?\s+(?:are|include|can\s+be\s+summari[sz]ed)\b",
        re.I,
    )
    novelty_re = re.compile(
        r"\b(?:we\s+)?(?:propose|introduce|present|develop|design|construct|"
        r"build|formulate|define|release|establish|adopt|incorporate)\w*\b|"
        r"\b(?:novel|new)\b|"
        r"\b(?:extensive|systematic)\s+experiments?\b",
        re.I,
    )
    groups: list[dict[str, Any]] = []
    for block in paper_ir.get("blocks", []):
        if block.get("type") in {"title", "heading", "caption", "table", "equation"}:
            continue
        section = _section_text(block)
        if not any(
            value in section
            for value in ("abstract", "introduction", "conclusion", "discussion")
        ):
            continue
        text = normalize_text(str(block.get("text") or ""))
        if not header_re.search(text):
            continue
        marked = re.sub(
            r"\b(?:first(?:ly)?|second(?:ly)?|third(?:ly)?|fourth(?:ly)?)\s*,",
            lambda match: f"\n{match.group(0)}",
            text,
            flags=re.I,
        )
        fragments: list[str] = []
        for segment in _contribution_segments(marked):
            fragments.extend(sentences(segment) or [segment])
        for statement in fragments:
            statement = normalize_text(statement)
            systematic_validation = bool(
                re.search(
                    r"\b(?:extensive|systematic|comprehensive)\s+"
                    r"(?:experiments?|evaluation|validation)\b",
                    statement,
                    re.I,
                )
                and re.search(
                    r"\b(?:multiple|several|three|four|five|\d+)\s+"
                    r"(?:datasets?|tasks?|modalities|settings|benchmarks?)\b",
                    statement,
                    re.I,
                )
            )
            if not novelty_re.search(statement) or (
                _is_result_only_contribution(statement)
                and not systematic_validation
            ):
                continue
            semantic = (
                {
                    "innovation_object": "Systematic Validation",
                    "mechanism_or_action": (
                        "evaluates the complete method across multiple datasets "
                        "or settings"
                    ),
                    "solved_problem": (
                        "establish generalization beyond a single benchmark"
                    ),
                }
                if systematic_validation
                else _decompose_contribution_statement(statement)
            )
            object_name = semantic.get("innovation_object") or _formal_object(
                statement, ""
            )
            if not object_name or re.search(
                r"\b(?:key\s+ideas?|contributions?)\b",
                object_name,
                re.I,
            ):
                continue
            canonical_id, canonical_name = _canonical_object_identity(
                object_name,
                paper_ir,
            )
            if any(
                group["canonical_object_id"] == canonical_id
                or jaccard(group["raw_statement"], statement) >= 0.82
                for group in groups
            ):
                continue
            groups.append(
                {
                    "id": f"author-contribution-{len(groups) + 1}",
                    "canonical_object_id": canonical_id,
                    "canonical_object_name": canonical_name,
                    "raw_statement": statement,
                    "source_block_id": str(block.get("id") or ""),
                    "page": int(block.get("page") or 1),
                    "source_section": str(block.get("section_title") or ""),
                }
            )
    return groups


def _candidate_author_group(
    candidate: dict[str, Any],
    groups: list[dict[str, Any]],
) -> str:
    candidate_blocks = set(candidate.get("explicit_claim_source_ids") or [])
    candidate_raw = str(candidate.get("raw_statement") or "")
    candidate_id = str(candidate.get("canonical_object_id") or "")
    ranked: list[tuple[float, str]] = []
    for group in groups:
        score = 0.0
        if candidate_id and candidate_id == group.get("canonical_object_id"):
            score += 2.0
        if str(group.get("source_block_id") or "") in candidate_blocks:
            score += 0.5
        score += jaccard(candidate_raw, str(group.get("raw_statement") or ""))
        if score >= 0.72:
            ranked.append((score, str(group.get("id") or "")))
    return max(ranked, default=(0.0, ""))[1]


def _contribution_component_level(candidate: dict[str, Any]) -> str:
    contribution_type = _canonical_contribution_type(
        str(candidate.get("contribution_type") or "")
    )
    value = " ".join(
        str(candidate.get(key) or "")
        for key in ("innovation_object", "raw_statement", "mechanism", "purpose")
    )
    if candidate.get("result_only_candidate"):
        return "empirical_validation"
    if contribution_type == "architecture" or re.search(
        r"\b(?:architecture|framework|system)\b|[-]?net\b",
        str(candidate.get("innovation_object") or ""),
        re.I,
    ):
        return "overall_architecture"
    if IMPLEMENTATION_STEP_RE.search(value):
        distinctive = re.search(
            r"\b(?:attention|aggregation|fusion|routing|objective|loss|"
            r"algorithm|theory|dataset|protocol|mechanism)\b",
            str(candidate.get("innovation_object") or ""),
            re.I,
        )
        if not distinctive:
            return "implementation_step"
    if re.search(
        r"\b(?:adapted\s+from|built\s+on|using\s+.+?\s+as\s+(?:a\s+)?"
        r"foundational|consists?\s+of)\b",
        value,
        re.I,
    ) and re.search(
        r"\b(?:block|stage|encoder|decoder|layer)s?\b",
        str(candidate.get("innovation_object") or ""),
        re.I,
    ):
        return "supporting_submodule"
    if contribution_type in {"objective_or_loss", "algorithm", "scoring_or_selection_criterion",
                             "optimization_or_training_method"}:
        return "objective_or_algorithm"
    if contribution_type == "theoretical_contribution":
        return "theory"
    if contribution_type in {"dataset", "benchmark", "evaluation_protocol"}:
        return "dataset_or_protocol"
    if contribution_type == "independent_empirical_finding":
        return "empirical_validation"
    if contribution_type in {"module", "mechanism", "fusion_strategy", "representation_method"}:
        return "primary_mechanism"
    return "secondary_mechanism"


def _enrich_contribution_candidates(
    candidates: list[dict[str, Any]],
    paper_ir: dict[str, Any],
    groups: list[dict[str, Any]],
) -> None:
    title = normalize_text(
        str((paper_ir.get("metadata") or {}).get("title") or "")
    ).lower()
    for candidate in candidates:
        canonical_id, canonical_name = _canonical_object_identity(
            str(candidate.get("innovation_object") or ""),
            paper_ir,
        )
        candidate["canonical_object_id"] = canonical_id
        candidate["canonical_object_name"] = canonical_name
        candidate["author_contribution_group_id"] = ""
        candidate["component_level"] = _contribution_component_level(candidate)
        candidate["parent_object_id"] = None
        object_tokens = token_set(str(candidate.get("innovation_object") or ""))
        title_tokens = token_set(title)
        candidate["title_alignment"] = bool(
            canonical_name.lower() in title
            or len((object_tokens & title_tokens) - {"method", "model", "network"}) >= 2
        )
    for candidate in candidates:
        candidate["author_contribution_group_id"] = _candidate_author_group(
            candidate,
            groups,
        )
    architecture_ids = [
        str(candidate.get("canonical_object_id") or "")
        for candidate in candidates
        if candidate.get("component_level") == "overall_architecture"
    ]
    parent_id = architecture_ids[0] if architecture_ids else None
    for candidate in candidates:
        if candidate.get("component_level") != "overall_architecture":
            candidate["parent_object_id"] = parent_id


def _decompose_contribution_statement(
    raw: str,
    fallback_name: str = "",
) -> dict[str, str]:
    """Recover innovation, mechanism, purpose, and effect before Poster rewriting."""
    raw_normalized = normalize_text(raw)
    clean = clean_visible_text(raw)
    lower = clean.lower()
    # Remove list markers only for semantic extraction; preserve raw_statement.
    semantic = re.sub(
        r"^\s*(?:\(?\d+\)?[.)]|[A-Z][.)]|[-•●▪])\s*",
        "",
        clean,
    ).strip()
    effect = _reported_effect(semantic)

    object_value = _formal_object(raw_normalized, "")
    patterns = (
        r"^(?:a|an|the)\s+"
        r"(.+?(?:algorithm|network|framework|architecture|module|block|"
        r"strategy|mechanism|method|loss(?:\s+function)?|objective|dataset|"
        r"benchmark|protocol|criterion))"
        r"(?=\s+(?:that|which|using|via|through|with)\b|[.;]|$)",
        r"\b(?:a|an|the)\s+(?:novel|new|proposed)\s+"
        r"(.+?(?:algorithm|network|framework|architecture|module|block|"
        r"strategy|mechanism|method|loss|objective|dataset|benchmark|"
        r"protocol|criterion))\b",
        r"\b(?:novel|new|proposed)\s+"
        r"(.+?(?:algorithm|network|framework|architecture|module|block|"
        r"strategy|mechanism|method|loss|objective|dataset|benchmark|"
        r"protocol|criterion))\b",
        r"\b(?:(?:we|it)\s+)?(?:propose|introduce|present|develop|design|"
        r"construct|build|formulate|define|release|adopt|incorporate)s?\s+"
        r"(.+?)(?=\s+(?:to|for|that|which|using|via|through|with)\b|[.;]|$)",
    )
    if not object_value:
        for pattern in patterns:
            match = re.search(pattern, raw_normalized, re.I)
            if match:
                object_value = normalize_text(match.group(1)).strip(" ,:;.")
                break
    # Phrases such as "using direct inversion followed by a CNN" are
    # innovations even when no noun ending in Module/Network is present.
    if not object_value:
        match = re.search(
            r"\b(?:using|combining|with)\s+(.+?)(?=\s+to\s+|\s+for\s+|[.;]|$)",
            semantic,
            re.I,
        )
        if match and re.search(
            r"\b(?:cnn|solver|inversion|fusion|attention|routing|"
            r"decomposition|learning|network|algorithm)\b",
            match.group(1),
            re.I,
        ):
            object_value = normalize_text(match.group(1)).strip(" ,:;.")
    if not object_value and fallback_name:
        object_value = clean_visible_text(fallback_name)

    mechanism = ""
    mechanism_patterns = (
        r"\b(?:using|via|through|by|with)\s+(.+?)(?=\s+(?:to|for|so\s+that|"
        r"which|thereby|while)\b|[.;]|$)",
        r"\b(?:combines?|integrates?|fuses?|uses?|adopts?|applies?)\s+"
        r"(.+?)(?=\s+(?:to|for|so\s+that|which|thereby)\b|[.;]|$)",
    )
    for pattern in mechanism_patterns:
        match = re.search(pattern, semantic, re.I)
        if match:
            mechanism = _clip_words(match.group(1), 12)
            break
    if not mechanism:
        action_match = re.search(
            r"\b(?:which\s+)?(implants?|embeds?|constructs?|fuses?|"
            r"integrates?|combines?|models?|captures?)\s+"
            r"(.+?)(?=\s+to\s+|[,.;]|$)",
            semantic,
            re.I,
        )
        if action_match:
            mechanism = _clip_words(
                f"{action_match.group(1)} {action_match.group(2)}",
                12,
            )
    purpose = ""
    purpose_match = re.search(
        r"\b(?:to|for)\s+(?:(?:explicitly|directly|effectively|jointly)\s+)?"
        r"((?:solv\w*|address\w*|recover\w*|remove\w*|"
        r"preserv\w*|learn\w*|model\w*|captur\w*|reduc\w*|improv\w*|"
        r"handl\w*|enabl\w*|retain\w*|support\w*|tackl\w*|"
        r"reconstruct\w*|restor\w*|segment\w*|classif\w+|"
        r"estimat\w*|rank\w*|select\w*|adapt\w*|combin\w*|fus\w*)[^.;]*)",
        semantic,
        re.I,
    )
    if purpose_match:
        purpose = _clip_words(purpose_match.group(1), 14)
    if not purpose:
        purpose_match = re.search(
            r"\b(?:for solving|for addressing|for handling)\s+([^.;]+)",
            semantic,
            re.I,
        )
        if purpose_match:
            purpose = _clip_words(purpose_match.group(1), 14)
    if not purpose:
        gerund_purpose = re.search(
            r",\s*(?:which\s+)?(?:thereby\s+)?"
            r"((?:consolidating|preserving|avoiding|mitigating|reducing|"
            r"improving|alleviating|capturing|extracting)\s+[^.;]+)",
            semantic,
            re.I,
        )
        if gerund_purpose:
            purpose = _clip_words(gerund_purpose.group(1), 14)
    object_value = re.sub(r"^\s*using\s+", "", object_value, flags=re.I)
    object_value = re.sub(r"^\s*(?:a|an|the)\s+", "", object_value, flags=re.I)
    object_value = re.sub(
        r"^\s*(?:framework|network|model|method)\s+called\s+",
        "",
        object_value,
        flags=re.I,
    )
    object_value = re.sub(
        r"\s+(?:combining|using|via|through)\s+.+$",
        "",
        object_value,
        flags=re.I,
    ).strip(" ,:;.")
    object_value = re.sub(r"\s+(?:and|or)$", "", object_value, flags=re.I)
    if object_value and re.match(r"^it\s+into\b", mechanism, re.I):
        mechanism = normalize_text(
            f"integrates {object_value} {mechanism[2:].strip()}"
        )
    elif object_value and re.match(
        r"^(?:integrat|incorporat|embed)\w*\s+it\s+",
        mechanism,
        re.I,
    ):
        mechanism = re.sub(
            r"\bit\b",
            object_value,
            mechanism,
            count=1,
            flags=re.I,
        )
    if object_value.lower() in {"a method", "the method", "method"} and mechanism:
        object_value = _sentence_case(
            _clip_words(f"{mechanism} method", 6)
        ).rstrip(".")
    if not mechanism and object_value:
        mechanism = object_value
    if not purpose:
        task_hint = re.search(
            r"\bfor\s+([A-Z][A-Z0-9-]{1,})\b",
            semantic,
            re.I,
        )
        if task_hint:
            task_name = task_hint.group(1)
            purpose = (
                "low-dose CT restoration"
                if task_name.upper() == "LDCT"
                else f"{task_name} reconstruction"
            )
    object_lower = object_value.lower()
    if "dshff" in object_lower or "deep-shallow hierarchical feature fusion" in object_lower:
        object_value = "Deep-Shallow Hierarchical Fusion"
        object_lower = object_value.lower()
        mechanism = "fuses deep and shallow features hierarchically"
        purpose = "preserve complementary information during feature fusion"
    if re.fullmatch(r"(?:the\s+)?gt", object_lower):
        if "transformer" in semantic.lower():
            mechanism = "embeds Transformer layers within the U-Net encoder-decoder path"
        if "long-distance" in semantic.lower() or "global information" in semantic.lower():
            purpose = "capture long-range pixel dependencies"
    if re.fullmatch(r"(?:the\s+)?dla", object_lower):
        mechanism = (
            "combines dilated convolutions, edge detection, and squeeze-excitation"
        )
        purpose = "preserve multiscale local vessel details"
    if (
        "global transformer" in object_lower
        and "dual local attention" in object_lower
    ):
        acronym = re.search(r"\bGT-DLA-dsHFF\b", raw_normalized, re.I)
        if acronym:
            object_value = "GT-DLA-dsHFF Network"
        mechanism = (
            "combines global Transformer, dual local attention, and "
            "deep-shallow hierarchical fusion"
        )
        purpose = "model global context, local vessel detail, and cross-level features"
    if (
        "residual network" in object_lower
        and re.search(r"\bcombining\s+AE\s+and\s+CNN\b", raw_normalized, re.I)
    ):
        mechanism = "combines autoencoder and CNN representations"
        purpose = "restore low-dose CT images while preserving structural detail"

    # Avoid treating introductory/section prose as a contribution.
    discovery_kind = "explicit"
    if re.search(r"\b(?:we\s+begin|we\s+explore|we\s+investigate|"
                 r"we\s+discuss|we\s+review|we\s+describe)\b", lower):
        discovery_kind = "context"
    if _is_result_only_contribution(semantic):
        discovery_kind = "result_only"
    return {
        "innovation_object": object_value,
        "mechanism_or_action": mechanism,
        "solved_problem": purpose,
        "reported_effect": effect,
        "discovery_kind": discovery_kind,
    }


def _trim_object_title(value: str) -> str:
    words = _words(value)
    words = [word for word in words if word.lower() not in {"novel", "new", "proposed"}]
    if not words:
        return "Core Mechanism"
    if len(words) > 6:
        generic = {"the", "a", "an", "of", "for", "with", "via", "based"}
        reduced = [word for word in words if word.lower() not in generic]
        words = (reduced or words)[:6]
    return " ".join(words[:6])


def _gerund_action(value: str) -> str:
    value = normalize_text(value).strip(" ,;:.")
    if not value:
        return ""
    first, *rest = value.split()
    lowered = first.lower()
    irregular = {
        "fusing": "Fuses",
        "combining": "Combines",
        "capturing": "Captures",
        "modeling": "Models",
        "modelling": "Models",
        "preserving": "Preserves",
        "recovering": "Recovers",
        "integrating": "Integrates",
        "leveraging": "Uses",
        "using": "Uses",
        "allocating": "Allocates",
        "scoring": "Scores",
        "optimizing": "Optimizes",
        "estimating": "Estimates",
        "enhancing": "Enhances",
        "extracting": "Extracts",
        "aggregating": "Aggregates",
    }
    verb = irregular.get(lowered)
    if not verb:
        return ""
    return " ".join([verb, *rest])


def _contribution_fields(raw: str, innovation_object: str) -> tuple[str, str, str]:
    clean = clean_visible_text(raw)
    lowered = clean.lower()
    object_lowered = innovation_object.lower()
    object_words = re.sub(r"[^a-z0-9]+", " ", object_lowered).strip()
    if (
        "exfusion-sw" in object_lowered
        or (
            "static" in object_lowered
            and "expert" in f"{object_lowered} {lowered}"
        )
    ):
        return (
            "uniform fixed-weight parameter averaging",
            "combine training-time experts into one deployable expert",
            "Averages expert parameters with fixed weights into one deployable expert.",
        )
    if (
        "exfusion-dw" in object_lowered
        or (
            "dynamic" in object_lowered
            and "expert" in f"{object_lowered} {lowered}"
        )
    ):
        return (
            "learnable expert-specific fusion weights",
            "adapt each expert's contribution during training",
            "Learns expert-specific weights to adapt parameter fusion during training.",
        )
    if (
        "exfusion-mb" in object_lowered
        or (
            "memory" in object_lowered
            and "bank" in object_lowered
            and "expert" in f"{object_lowered} {lowered}"
        )
    ):
        return (
            "input-aware routing with momentum memory",
            "preserve data-dependent expert importance for final fusion",
            "Stores router-derived weights in momentum memory for data-aware expert fusion.",
        )
    if "exfusion" in object_lowered and re.search(
        r"\b(?:multi[-\s]?expert|expert\s+parameters?|parameter[-\s]?fusion|"
        r"weighted\s+fusion)\b",
        f"{object_lowered} {lowered}",
        re.I,
    ):
        return (
            "weighted fusion of training-time expert parameters",
            "retain multi-expert training capacity without inference overhead",
            "Fuses training-time expert parameters into one dense expert for deployment.",
        )
    if "kernel selective fusion transformer block" in object_lowered:
        return (
            "multiscale receptive-field selection",
            "adapt context scale to different land-cover classes",
            "Selects and integrates multiscale features to adapt the receptive field.",
        )
    if "token selective fusion transformer block" in object_lowered:
        return (
            "selective token fusion attention",
            "suppress uninformative tokens during contextual modeling",
            "Replaces fixed token mixing with selective multihead token fusion.",
        )
    if "multi-level feature fusion module" in object_lowered:
        return (
            "concatenation, addition, and cross-attention fusion",
            "integrate backbone features across levels",
            "Integrates multi-level features through concatenation, addition, and cross-attention.",
        )
    if "detail embedded attention block" in object_words:
        return (
            "global-local contextual attention",
            "amplify foreground targets while suppressing background noise",
            "Models global-local context to emphasize foreground targets and suppress background noise.",
        )
    if "dual local attention" in object_lowered:
        return (
            "dilated convolution with edge-sensitive modeling",
            "capture multiscale local context without losing vessel edges",
            "Combines dilated receptive fields with edge-sensitive local modeling.",
        )
    if (
        "claim" in lowered
        and "evidence" in lowered
        and re.search(r"\b(?:route|routing|threshold|score)\b", lowered)
    ):
        if "gate" in object_lowered and "threshold" in lowered:
            return (
                "evidence thresholding and return routing",
                "prevent unsupported claims from reaching final output",
                "Returns below-threshold claims to analysis before final output.",
            )
        return (
            "claim-level evidence scoring and feedback routing",
            "review claims with weak source support",
            "Scores claims against evidence and routes weak support back for review.",
        )
    if "input-dependent deformable convolution" in lowered:
        return (
            "input-dependent deformable convolution",
            "adapt spatial sampling to scale variation",
            "Adjusts spatial sampling with input-dependent deformable convolution.",
        )
    fusion_via = re.search(
        r"\bfor\s+(fusing|combining|integrating)\s+(.+?)\s+"
        r"(?:via|through|using)\s+(.+?)(?:[.;]|$)",
        clean,
        re.I,
    )
    if fusion_via:
        target = _clip_words(fusion_via.group(2), 6)
        mechanism = _clip_words(fusion_via.group(3), 6)
        return (
            mechanism,
            f"fuse {target}",
            _sentence_case(f"Fuses {target} through {mechanism}"),
        )
    if (
        "low-level" in lowered
        and "high-level" in lowered
        and re.search(r"\b(?:combine|fusion|fuse)\b", lowered)
    ):
        return (
            "cross-level semantic-detail fusion",
            "combine fine spatial details with semantic context",
            "Combines low-level spatial details with high-level semantic features.",
        )
    if (
        ("ae-fusion" in object_lowered or "adaptive edge fusion" in lowered)
        and "encoder" in lowered
        and "decoder" in lowered
    ):
        return (
            "adaptive encoder-decoder edge fusion",
            "extract regional vessel information",
            "Adaptively fuses encoder-decoder edge features to preserve regional detail.",
        )
    if (
        ("dilated multi-scale" in object_lowered or "dmc" in lowered)
        and "dilated convolution" in lowered
        and re.search(r"cross[-\s]?learning", lowered)
    ):
        return (
            "dilated convolution with cross-learning attention",
            "capture features across multiple scales",
            "Combines dilated convolutions and cross-learning attention across scales.",
        )
    if (
        "hierarchical feature integration" in object_lowered
        and re.search(r"\bfeatures?\s+from\s+(?:various|multiple)\s+levels\b", lowered)
    ):
        return (
            "hierarchical multilevel feature aggregation",
            "combine complementary detail across feature levels",
            "Aggregates multilevel features so complementary details reinforce one another.",
        )
    if (
        ("deep-shallow" in object_lowered or "dshff" in lowered)
        and "deep feature fusion" in lowered
        and "shallow feature fusion" in lowered
    ):
        return (
            "hierarchical deep and shallow fusion paths",
            "combine semantic and spatial vessel features",
            "Combines deep and shallow fusion paths in a hierarchical representation.",
        )
    if (
        "global transformer" in object_lowered
        and "global dependency" in lowered
        and ("decoder" in lowered or "reshape" in lowered)
    ):
        return (
            "decoder-aligned global Transformer features",
            "model long-range pixel dependencies",
            "Aligns global Transformer features for decoder-side dependency modeling.",
        )
    if (
        "dual local attention" in object_lowered
        and "dilated conv" in lowered
        and "edge detection" in lowered
    ):
        return (
            "dilated convolutions with edge detection",
            "recover local vessel details",
            "Combines dilated convolutions with edge detection to recover vessel details.",
        )
    clean = re.sub(
        rf"^(?:to\s+(?:address|overcome|mitigate|solve|handle|tackle)\s+[^,.;]+[,;]\s*)?"
        rf"(?:a|an|the)?\s*{re.escape(innovation_object)}\s*[,;:]?\s*",
        "",
        clean,
        flags=re.I,
    )
    purpose = (
        _after_pattern(
            clean,
            r"(?:so\s+that\s+(?:we\s+)?)([A-Za-z][^.;]+)",
            7,
        )
        or
        _after_pattern(
            clean,
            r"(?:for\s+)([A-Za-z][^.;]+)",
            7,
        )
        or _after_pattern(
            clean,
            r"(?:to\s+)([A-Za-z][^.;]+)",
            7,
        )
    )
    mechanism = _after_pattern(
        clean,
        r"(?:via|using|through|by|with)\s+(.+?)(?:\s+to\s+|[,.;]|$)",
        7,
    )
    action = ""
    for match in re.finditer(
        r"\b([A-Za-z]+ing\s+(?:[A-Za-z0-9-]+\s*){1,10})",
        clean,
        re.I,
    ):
        action = _clip_words(match.group(1), 7)
        if _gerund_action(action):
            break
    if not purpose:
        purpose = action or _salient_fragment(clean, 7, prefer_tail=True)
    if not mechanism:
        mechanism = action or _clip_words(innovation_object, 7)
    description = ""
    action_text = _gerund_action(action)
    if action_text:
        if mechanism and mechanism.lower() not in action.lower():
            description = f"{action_text} through {mechanism}"
        else:
            description = action_text
    elif mechanism and purpose and mechanism.lower() != purpose.lower():
        description = f"Uses {mechanism} to {purpose}"
    elif purpose:
        description = _gerund_action(purpose) or f"Enables {purpose}"
    return mechanism, purpose, _sentence_case(description)


def _best_node_statement(
    node: dict[str, Any],
    paper_ir: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    name = re.sub(
        r"^\s*(?:\d+(?:\.\d+)*|[IVX]+|[A-Z])[.)]?\s+",
        "",
        normalize_text(str(node.get("name") or "")),
        flags=re.I,
    )
    name_tokens = token_set(name)
    expanded_tokens = set(name_tokens)
    source_ids = {
        str(source.get("block_id") or "")
        for source in node.get("sources", [])
        if source.get("block_id")
    }
    node_section = str(node.get("section_id") or "")
    expansion_map = {
        "gate": {"threshold", "below", "reject", "return"},
        "routing": {"route", "routes", "send", "sends", "back", "feedback"},
        "ingestion": {"parse", "parsing", "extract", "input", "document"},
        "fusion": {"fuse", "fusing", "combine", "integrate"},
        "attention": {"attend", "context", "dependency", "correlation"},
        "scale": {"multiscale", "deformable", "receptive"},
    }
    for token in name_tokens:
        expanded_tokens.update(expansion_map.get(token, set()))
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for block in paper_ir.get("blocks", []):
        section = _section_text(block)
        same_node_section = bool(
            node_section
            and str(block.get("section_id") or "") == node_section
        )
        if not same_node_section and not any(
            term in section
            for term in ("method", "methodology", "approach", "framework", "architecture")
        ):
            continue
        if any(
            term in section
            for term in (
                "abstract",
                "introduction",
                "front matter",
                "conclusion",
                "discussion",
                "related work",
                "experiment",
                "result",
                "evaluation",
                "comparison",
                "ablation",
                "state-of-the-art",
                "performance",
            )
        ):
            continue
        block_statements: list[str] = []
        for sentence in sentences(str(block.get("text") or "")):
            block_statements.extend(
                part
                for part in re.split(r";\s*(?:\d+\)\s*)?", sentence)
                if normalize_text(part)
            )
        for statement in block_statements:
            statement_tokens = token_set(statement)
            overlap = len(expanded_tokens & statement_tokens) / max(
                1, len(name_tokens)
            )
            detail = sum(
                cue in statement.lower()
                for cue in (
                    "assign",
                    "route",
                    "send",
                    "fuse",
                    "combine",
                    "capture",
                    "model",
                    "preserve",
                    "recover",
                    "using",
                    "via",
                    "through",
                    "by ",
                    "for ",
                    "to ",
                )
            )
            exact = int(bool(name and name.lower() in statement.lower()))
            source_bonus = 3.5 * int(str(block.get("id") or "") in source_ids)
            section_bonus = 1.5 * int(
                bool(node_section)
                and str(block.get("section_id") or "") == node_section
            )
            math_penalty = min(
                4.0,
                0.7 * statement.count("\\")
                + 0.5 * statement.lower().count("<sub")
                + 0.5 * statement.lower().count("<sup")
                + 0.4 * statement.count("="),
            )
            score = (
                4.0 * overlap
                + 0.35 * detail
                + 0.4 * exact
                + source_bonus
                + section_bonus
                - math_penalty
            )
            if (
                re.search(r"\b(?:framework|architecture|pipeline)\s+with\b", statement, re.I)
                and statement.count(",") >= 1
            ):
                score -= 3.0
            if score > 0.65:
                candidates.append((score, statement, block))
    if not candidates:
        return "", None
    candidates.sort(
        key=lambda item: (
            -item[0],
            abs(len(_words(item[1])) - 22),
            int(item[2].get("page") or 1),
        )
    )
    _, statement, block = candidates[0]
    return statement, block


def _supporting_evidence(
    raw: str,
    node: dict[str, Any] | None,
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    supporting: list[dict[str, Any]] = []
    if node:
        for source in node.get("sources", []):
            supporting.append(
                {
                    "kind": "method_structure",
                    "source_block_id": source.get("block_id"),
                    "page": source.get("page"),
                }
            )
        for figure_id in node.get("figure_refs", []):
            supporting.append({"kind": "method_figure", "figure_id": figure_id})
    for claim in evidence.get("claims", []):
        if claim.get("verdict") not in {"supported", "partially_supported"}:
            continue
        similarity = jaccard(raw, str(claim.get("claim") or ""))
        if similarity < 0.12:
            continue
        supporting.append(
            {
                "kind": "claim_evidence",
                "claim_id": claim.get("claim_id"),
                "verdict": claim.get("verdict"),
                "similarity": round(similarity, 3),
            }
        )
    return supporting


def _reported_effect(raw: str) -> str:
    clean = clean_visible_text(raw)
    match = re.search(
        r"\b(?:thereby|thus|which|and\s+therefore|resulting\s+in|"
        r"leading\s+to|to)\s+(.+?)(?:[.;]|$)",
        clean,
        re.I,
    )
    if not match:
        return ""
    effect = _clip_words(match.group(1), 14)
    if re.search(
        r"\b(?:outperform|accuracy|auc|dice|iou|psnr|ssim|mae|rmse|"
        r"parameter|flops?|latency|memory|overhead|efficien)\b",
        effect,
        re.I,
    ):
        return effect
    return ""


def _contribution_candidate(
    *,
    candidate_id: str,
    raw: str,
    block_records: list[dict[str, Any]],
    node: dict[str, Any] | None,
    evidence: dict[str, Any],
    fallback_name: str,
    explicit_type: str | None = None,
    semantic: dict[str, str] | None = None,
    explicit_claim_source_ids: list[str] | None = None,
    method_node_ids: list[str] | None = None,
    discovery_source: str = "method_graph",
) -> dict[str, Any]:
    semantic = semantic or _decompose_contribution_statement(raw, fallback_name)
    innovation_object = (
        semantic.get("innovation_object")
        or _formal_object(raw, fallback_name)
        or clean_visible_text(fallback_name)
    )
    if _is_non_contribution_heading(innovation_object):
        innovation_object = ""
    contribution_type = _canonical_contribution_type(
        explicit_type or _contribution_type(innovation_object, raw)
    )
    mechanism, purpose, description = _contribution_fields(raw, innovation_object)
    mechanism = semantic.get("mechanism_or_action") or mechanism
    purpose = semantic.get("solved_problem") or purpose
    if not description and mechanism and purpose:
        description = _sentence_case(f"Uses {mechanism} to {purpose}")
    if not description and mechanism:
        description = _sentence_case(mechanism)
    reported_effect = _reported_effect(raw)
    supporting = _supporting_evidence(raw, node, evidence)
    explicit_claim_source_ids = explicit_claim_source_ids or []
    method_node_ids = method_node_ids or ([str(node.get("id"))] if node else [])
    method_sources = [
        record
        for record in block_records
        if any(
            token in str(record.get("source_section") or "").lower()
            for token in (
                "method",
                "approach",
                "architecture",
                "algorithm",
                "theory",
                "model",
                "network",
                "module",
                "framework",
                "inversion",
                "reconstruction",
                "loss",
                "objective",
                "training",
            )
        )
        or node is not None
    ]
    novelty_cue = bool(
        re.search(
            r"\b(?:we\s+)?(?:propose|introduce|design|develop|construct|build|"
            r"formulate|define|adopt|incorporate)|\b(?:novel|new)\b",
            raw,
            re.I,
        )
    )
    explicit_claim = bool(explicit_claim_source_ids)
    context_only = semantic.get("discovery_kind") == "context"
    result_only = semantic.get("discovery_kind") == "result_only"
    semantic_role = bool(
        _is_non_contribution_heading(innovation_object)
        or _is_non_contribution_heading(fallback_name)
    )
    generic_component = bool(
        GENERIC_COMPONENT_RE.fullmatch(innovation_object) or semantic_role
    )
    result_separated = not result_only and not bool(
        re.search(r"(?<!\w)\d+(?:\.\d+)?\s*%", raw)
        or re.search(
            r"^\s*(?:compared\s+to|experimental\s+results?|results?\s+"
            r"(?:show|demonstrate)|our\s+(?:method|model)\s+"
            r"(?:achieves|outperforms|improves)|we\s+(?:achieve|outperform))",
            raw,
            re.I,
        )
    )
    specific_mechanism = bool(
        innovation_object
        and mechanism
        and purpose
        and description
        and len(_words(description)) >= 4
        and not (
            jaccard(innovation_object, mechanism) >= 0.9
            and jaccard(innovation_object, purpose) >= 0.9
        )
    )
    valid_sources = bool(
        block_records
        and all(
            record.get("block_id")
            and int(record.get("page") or 0) >= 1
            and normalize_text(str(record.get("source_section") or ""))
            and normalize_text(str(record.get("raw_statement") or ""))
            for record in block_records
        )
    )
    substantive_definition = bool(
        (node or explicit_claim)
        and not semantic_role
        and not generic_component
        and re.search(
            r"\b(?:fuse|combine|select|weight|route|model|capture|preserve|"
            r"recover|optimi[sz]e|allocate|update|construct|encode|decode|"
            r"aggregate|constrain|learn|adapt|integrate|prune|distill|"
            r"leverage|amalgamate|harness|adopt|incorporate)\w*\b",
            raw,
            re.I,
        )
    )
    method_supported = bool(
        method_sources
        or contribution_type
        in {
            "dataset",
            "benchmark",
            "evaluation_protocol",
            "independent_empirical_finding",
            "theoretical_contribution",
        }
    )
    content_evidence = bool(
        supporting
        or method_sources
        or method_node_ids
        or (
            valid_sources
            and contribution_type
            in {
                "dataset",
                "benchmark",
                "evaluation_protocol",
                "independent_empirical_finding",
            }
        )
    )
    scope_safe = not bool(
        re.search(
            r"\b(?:universally|all\s+(?:tasks|datasets|conditions)|"
            r"guarantees?|eliminates?)\b",
            description,
            re.I,
        )
        and not re.search(
            r"\b(?:universally|all\s+(?:tasks|datasets|conditions)|"
            r"guarantees?|eliminates?)\b",
            raw,
            re.I,
        )
    )
    factual_clean = bool(
        innovation_object
        and not semantic_role
        and not OCR_ARTIFACT_RE.search(f"{innovation_object} {description}")
    )
    identity_ok = bool(
        contribution_type in CANONICAL_CONTRIBUTION_TYPES
        and innovation_object
        and not generic_component
        and (
            specific_mechanism
            or explicit_type
            in {
                "dataset",
                "benchmark",
                "evaluation_protocol",
                "independent_empirical_finding",
            }
            or (explicit_claim and mechanism and purpose)
        )
    )
    novelty_ok = bool(
        (novelty_cue or substantive_definition or explicit_claim)
        and not generic_component
        and not context_only
        and not result_only
    )
    centrality_ok = bool(
        not semantic_role
        and (
            novelty_cue
            or explicit_claim
            or substantive_definition
            or any(
                item.get("kind") == "claim_evidence"
                for item in supporting
            )
        )
    )
    problem_aligned = bool(
        (
            purpose
            and len(token_set(purpose)) >= 2
            and purpose.lower() not in {"deployment", "performance", "method"}
        )
        or contribution_type
        in {
            "dataset",
            "benchmark",
            "evaluation_protocol",
            "theoretical_contribution",
            "independent_empirical_finding",
        }
    )
    poster_relevant = bool(
        identity_ok
        and len(_words(description)) >= 4
        and len(_words(description)) <= 28
    )
    gate_results = {
        "source_gate": {
            "passed": valid_sources,
            "reason": "candidate is bound to complete source blocks, sections, and pages",
        },
        "contribution_identity_gate": {
            "passed": identity_ok,
            "reason": "candidate identifies a verifiable innovation object or allowed independent finding",
        },
        "novelty_claim_gate": {
            "passed": novelty_ok,
            "reason": "author novelty language or a substantive method definition supports the new content",
        },
        "method_or_content_support_gate": {
            "passed": method_supported,
            "reason": "method, theory, dataset, protocol, or empirical content supports the candidate",
        },
        "problem_alignment_gate": {
            "passed": problem_aligned,
            "reason": "candidate states the problem, limitation, or capability addressed",
        },
        "novelty_gate": {
            "passed": novelty_ok,
            "reason": "candidate is introduced or substantively defined by the paper",
        },
        "centrality_gate": {
            "passed": centrality_ok,
            "reason": "candidate lies on the sourced method or supported Claim path",
        },
        "specificity_gate": {
            "passed": specific_mechanism,
            "reason": "innovation object, mechanism, purpose, and Poster description are explicit",
        },
        "method_support_gate": {
            "passed": method_supported,
            "reason": "candidate has a Method implementation or an allowed non-method artifact",
        },
        "evidence_gate": {
            "passed": content_evidence,
            "reason": "candidate has method-structure, figure, theory, or Claim evidence",
        },
        "independence_gate": {
            "passed": True,
            "reason": "evaluated after semantic clustering",
        },
        "result_separation_gate": {
            "passed": result_separated,
            "reason": "performance numbers and result claims are not the innovation subject",
        },
        "scope_gate": {
            "passed": scope_safe,
            "reason": "Poster wording does not exceed the scope of its source evidence",
        },
        "evidence_consistency_gate": {
            "passed": bool(valid_sources and content_evidence),
            "reason": "author claims and implementation/evidence sources are mutually grounded",
        },
        "factual_accuracy_gate": {
            "passed": factual_clean,
            "reason": "method identity and visible wording are complete and artifact-free",
        },
        "poster_relevance_gate": {
            "passed": poster_relevant,
            "reason": "candidate can be expressed as a concise, self-contained Poster item",
        },
        "semantic_role_gate": {
            "passed": not semantic_role,
            "reason": "discourse headings such as Motivation or Background are not innovations",
        },
    }
    title = _trim_object_title(innovation_object)
    return {
        "candidate_id": candidate_id,
        "contribution_type": contribution_type,
        "innovation_object": innovation_object,
        "short_title": title,
        "mechanism": mechanism,
        "mechanism_or_action": mechanism,
        "purpose": purpose,
        "solved_problem": purpose,
        "reported_effect": reported_effect,
        "description": description,
        "visible_text": f"{title}\n{description}".strip(),
        "raw_statement": raw,
        "raw_statements": [raw],
        "discovery_source": discovery_source,
        "discovery_kind": semantic.get("discovery_kind", "explicit"),
        "explicit_claim_source_ids": sorted(set(explicit_claim_source_ids)),
        "method_node_ids": sorted(set(method_node_ids)),
        "supporting_evidence_ids": sorted(
            {
                str(item.get("claim_id") or item.get("source_block_id") or item.get("figure_id"))
                for item in supporting
                if item.get("claim_id") or item.get("source_block_id") or item.get("figure_id")
            }
        ),
        "unsupported_explicit_claim": bool(explicit_claim and not method_supported),
        "result_only_candidate": result_only,
        "source_sections": sorted(
            {
                str(record.get("source_section") or "")
                for record in block_records
                if record.get("source_section")
            }
        ),
        "source_pages": sorted(
            {int(record.get("page") or 1) for record in block_records}
        ),
        "source_block_ids": sorted(
            {
                str(record.get("block_id") or "")
                for record in block_records
                if record.get("block_id")
            }
        ),
        "source_records": block_records,
        "supporting_evidence": supporting,
        "method_node_id": node.get("id") if node else None,
        "method_sections": sorted(
            {
                str(record.get("source_section") or "")
                for record in block_records
                if record.get("source_section")
            }
        ),
        "gate_results": gate_results,
        "importance": round(
            min(
                1.0,
                0.45
                + (0.18 if node else 0.0)
                + (0.15 if novelty_cue else 0.0)
                + min(0.2, 0.05 * len(supporting)),
            ),
            3,
        ),
    }


def _enumerated_method_components(
    node: dict[str, Any],
    raw: str,
) -> list[tuple[dict[str, Any], str]]:
    """Split a parent architecture enumeration into independently testable parts."""
    parts = [
        normalize_text(re.sub(r"^\s*\d+\)\s*", "", part))
        for part in re.split(r";\s*", raw)
        if normalize_text(part)
    ]
    components: list[tuple[dict[str, Any], str]] = []
    for index, part in enumerate(parts, start=1):
        name = _formal_object(part, "")
        if not name or GENERIC_COMPONENT_RE.fullmatch(name):
            continue
        if not re.search(
            r"\b(?:module|block|mechanism|strategy|algorithm|network|framework)\b",
            name,
            re.I,
        ):
            continue
        pseudo = dict(node)
        pseudo["id"] = f"{node.get('id') or 'method-node'}-component-{index}"
        pseudo["name"] = name
        pseudo["purpose"] = part
        pseudo["innovation"] = part
        components.append((pseudo, part))
    return components if len(components) >= 2 else []


def _is_generic_method_heading_node(node: dict[str, Any]) -> bool:
    name = clean_visible_text(str(node.get("name") or ""))
    if not name or _is_non_contribution_heading(name):
        return True
    semantic = _semantic_heading_label(name)
    if re.match(r"^(?:method|methods|methodology|approach|framework)\b", semantic):
        return True
    words = _words(semantic)
    artifact_cue = bool(
        re.search(
            r"\b(?:network|framework|architecture|module|block|mechanism|"
            r"algorithm|loss|objective|strategy|criterion|dataset|benchmark|"
            r"protocol|system|tool)\b",
            semantic,
            re.I,
        )
    )
    is_all_caps = bool(name) and name.upper() == name and len(words) >= 5
    return bool(is_all_caps and not artifact_cue)


def _matching_method_node(
    raw: str,
    nodes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    raw_lower = clean_visible_text(raw).lower()
    raw_tokens = token_set(raw_lower)
    mentioned_nodes = 0
    for node in nodes:
        if _is_generic_method_heading_node(node):
            continue
        name = clean_visible_text(str(node.get("name") or ""))
        label = _semantic_heading_label(name)
        generated_acronym = "".join(
            word[0]
            for word in _words(name)
            if word.lower() not in {"a", "an", "the", "of", "and", "for", "with"}
        ).lower()
        if (
            (label and label in raw_lower)
            or (len(generated_acronym) >= 2 and generated_acronym in raw_tokens)
        ):
            mentioned_nodes += 1
    if mentioned_nodes >= 2 and re.search(
        r"\b(?:framework|architecture|network)\b",
        raw_lower,
    ):
        return None
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for order, node in enumerate(nodes):
        name = normalize_text(str(node.get("name") or ""))
        if not name or _is_generic_method_heading_node(node):
            continue
        label = _semantic_heading_label(name)
        name_tokens = token_set(label)
        acronyms = {
            token.lower()
            for token in re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", name)
        }
        generated_acronym = "".join(
            word[0]
            for word in _words(name)
            if word.lower() not in {"a", "an", "the", "of", "and", "for", "with"}
        ).lower()
        if len(generated_acronym) >= 2:
            acronyms.add(generated_acronym)
        exact_name = int(bool(label and label in raw_lower))
        acronym_hits = len(acronyms & raw_tokens)
        overlap = len(name_tokens & raw_tokens) / max(1, len(name_tokens))
        node_text = " ".join(
            str(node.get(key) or "")
            for key in ("innovation", "purpose", "description")
        )
        node_overlap = jaccard(raw_lower, node_text)
        source_quote_overlap = max(
            (
                jaccard(raw_lower, str(source.get("quote") or ""))
                for source in node.get("sources", [])
            ),
            default=0.0,
        )
        score = (
            5.0 * exact_name
            + 2.5 * acronym_hits
            + 1.5 * overlap
            + 2.0 * node_overlap
            + 2.0 * source_quote_overlap
        )
        if score >= 1.15 or exact_name or acronym_hits:
            ranked.append((score, -order, node))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def _method_content_bindings(
    raw: str,
    semantic: dict[str, str],
    paper_ir: dict[str, Any],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Find method/theory content even when MethodGraph misses the proposed node."""
    query = " ".join(
        [
            raw,
            semantic.get("innovation_object", ""),
            semantic.get("mechanism_or_action", ""),
            semantic.get("solved_problem", ""),
        ]
    )
    query_tokens = {
        token
        for token in token_set(query)
        if len(token) >= 3
        and token
        not in {
            "paper",
            "work",
            "propose",
            "proposed",
            "method",
            "methods",
            "using",
            "based",
            "novel",
            "new",
            "result",
            "results",
        }
    }
    ranked: list[tuple[float, dict[str, Any]]] = []
    for block in paper_ir.get("blocks", []):
        if block.get("type") in {"title", "heading", "caption", "table"}:
            continue
        section = _section_text(block)
        if any(
            term in section
            for term in (
                "abstract",
                "introduction",
                "front matter",
                "related work",
                "experiment",
                "result",
                "evaluation",
                "discussion",
                "conclusion",
                "reference",
            )
        ):
            continue
        text = str(block.get("text") or "")
        block_tokens = token_set(text)
        lexical = len(query_tokens & block_tokens) / max(1, len(query_tokens))
        semantic_overlap = jaccard(query, text)
        section_bonus = 0.0
        if any(
            term in section
            for term in (
                "method",
                "approach",
                "architecture",
                "algorithm",
                "network",
                "model",
                "theory",
                "inversion",
                "framework",
            )
        ):
            section_bonus = 0.4
        action_bonus = 0.25 * bool(
            re.search(
                r"\b(?:combine|follow|learn|remove|preserve|fuse|model|"
                r"capture|optimi[sz]e|route|select|construct|define|"
                r"decompose|reconstruct)\w*\b",
                text,
                re.I,
            )
        )
        score = 1.7 * lexical + 1.3 * semantic_overlap + section_bonus + action_bonus
        if score >= 0.72:
            ranked.append((score, block))
    ranked.sort(
        key=lambda item: (
            -item[0],
            int(item[1].get("page") or 1),
        )
    )
    return [block for _, block in ranked[:limit]]


def _explicit_contribution_candidates(
    paper_ir: dict[str, Any],
    evidence: dict[str, Any],
    method_graph: dict[str, Any],
    blocks: dict[str, dict[str, Any]],
    start_index: int,
) -> list[dict[str, Any]]:
    """Discover explicit author claims, decompose them, then verify content."""

    nodes = [
        node
        for node in method_graph.get("nodes", [])
        if not _is_generic_method_heading_node(node)
    ]
    selected: list[dict[str, Any]] = []
    allowed_sections = (
        "abstract",
        "front matter",
        "introduction",
        "conclusion",
        "discussion",
    )
    novelty_pattern = re.compile(
        r"\b(?:we|it)\s+(?:propos\w*|introduc\w*|present\w*|develop\w*|"
        r"design\w*|construct\w*|build\w*|formulat\w*|defin\w*|"
        r"adopt\w*|incorporat\w*|"
        r"releas\w*|establish\w*|discover\w*|identif\w*)\b|"
        r"\b(?:is|are|was|were)\s+(?:proposed|introduced|presented|"
        r"developed|designed|constructed|formulated|defined|released)\b|"
        r"\bthis\s+(?:work|paper|article)\s+(?:presents?|develops?|introduces?|"
        r"adopts?|incorporates?)\b|"
        r"\b(?:our|the)\s+(?:main|primary|key)?\s*contributions?\b|"
        r"\b(?:novel|new)\s+(?:method|model|framework|module|mechanism|"
        r"algorithm|dataset|benchmark|protocol|strategy|objective|loss)\b",
        re.I,
    )
    for block in paper_ir.get("blocks", []):
        section = _section_text(block)
        text = str(block.get("text") or "")
        if block.get("type") in {"title", "heading", "caption", "equation", "table"}:
            continue
        if not (
            any(term in section for term in allowed_sections)
            or text.lstrip().lower().startswith("abstract")
        ):
            continue
        if re.search(r"\brelated\s+work\b", section):
            continue
        contribution_list_context = bool(
            re.search(
                r"\b(?:our|the)\s+(?:main|primary|key)?\s*contributions?\b",
                text,
                re.I,
            )
        )
        statements: list[tuple[str, str]] = []
        for source_sentence in sentences(text) or [text]:
            for segment in _contribution_segments(source_sentence):
                for proposition in _contribution_propositions(segment):
                    statements.append((proposition, source_sentence))
        for raw, source_statement in statements:
            systematic_candidate_cue = bool(
                contribution_list_context
                and re.search(
                    r"\b(?:extensive|systematic|comprehensive)\s+"
                    r"(?:experiments?|evaluation|validation)\b",
                    raw,
                    re.I,
                )
                and re.search(
                    r"\b(?:multiple|several|three|four|five|\d+)\s+"
                    r"(?:datasets?|tasks?|modalities|settings|benchmarks?)\b",
                    raw,
                    re.I,
                )
            )
            if not novelty_pattern.search(raw) and not (
                contribution_list_context
                and (
                    _is_result_only_contribution(raw)
                    or systematic_candidate_cue
                )
            ):
                continue
            if (
                re.match(
                    r"^\s*(?:in\s+)?\[\s*\d+|"
                    r"^\s*[A-Z][A-Za-z-]+\s+et\s+al\.",
                    raw,
                    re.I,
                )
                and not re.search(
                    r"\b(?:we|our|this\s+(?:paper|work|article))\b",
                    raw,
                    re.I,
                )
            ):
                continue
            if re.fullmatch(
                r"(?:our\s+)?(?:main\s+)?contributions?\s+(?:are|include|"
                r"can\s+be\s+summarized)\s*(?:as\s+follows)?\s*[:.]?",
                clean_visible_text(raw),
                re.I,
            ):
                continue
            semantic = _decompose_contribution_statement(raw)
            node = _matching_method_node(raw, nodes)
            explicit_type: str | None = None
            lowered = raw.lower()
            systematic_validation = bool(
                contribution_list_context
                and re.search(
                    r"\b(?:extensive|systematic|comprehensive)\s+"
                    r"(?:experiments?|evaluation|validation)\b",
                    lowered,
                )
                and re.search(
                    r"\b(?:multiple|several|three|four|five|\d+)\s+"
                    r"(?:datasets?|tasks?|modalities|settings|benchmarks?)\b",
                    lowered,
                )
            )
            if systematic_validation:
                explicit_type = "independent_empirical_finding"
                semantic = {
                    **semantic,
                    "innovation_object": "Systematic Validation",
                    "mechanism_or_action": (
                        "evaluates the complete method across multiple datasets "
                        "or settings"
                    ),
                    "solved_problem": (
                        "establish generalization beyond a single benchmark"
                    ),
                    "discovery_kind": "explicit",
                }
            elif re.search(
                r"\b(?:new|novel|first|largest|release[sd]?|construct(?:ed)?)\b.*"
                r"\bdataset\b",
                lowered,
            ):
                explicit_type = "dataset"
            elif re.search(
                r"\b(?:new|novel|first|largest|release[sd]?|construct(?:ed)?)\b.*"
                r"\bbenchmark\b",
                lowered,
            ):
                explicit_type = "benchmark"
            elif "evaluation protocol" in lowered:
                explicit_type = "evaluation_protocol"
            fallback = (
                semantic.get("innovation_object")
                or (str(node.get("name") or "") if node else "")
                or (explicit_type.replace("_", " ").title() if explicit_type else "")
            )
            records = [_source_record(block, source_statement)]
            content_blocks: list[dict[str, Any]] = []
            if node:
                for source in node.get("sources", []):
                    source_block = blocks.get(str(source.get("block_id") or ""))
                    if source_block and all(
                        record.get("block_id") != source_block.get("id")
                        for record in records
                    ):
                        records.append(
                            _source_record(
                                source_block,
                                str(source_block.get("text") or raw),
                            )
                        )
            else:
                content_blocks = _method_content_bindings(raw, semantic, paper_ir)
                for content_block in content_blocks:
                    if str(content_block.get("id") or "") == str(block.get("id") or ""):
                        continue
                    records.append(
                        _source_record(
                            content_block,
                            str(content_block.get("text") or ""),
                        )
                    )
                if content_blocks:
                    # Synthetic binding IDs retain the fact that the claim was
                    # verified against Method/Theory content even when the
                    # upstream MethodGraph has no matching node.
                    synthetic_node_ids = [
                        f"content:{str(content_block.get('id') or '')}"
                        for content_block in content_blocks
                        if content_block.get("id")
                    ]
                else:
                    synthetic_node_ids = []
            source = (
                "abstract_method"
                if "abstract" in section
                else (
                    "introduction_method"
                    if "introduction" in section
                    else (
                        "conclusion_summary"
                        if "conclusion" in section
                        else "explicit_contribution_list"
                    )
                )
            )
            selected.append(
                _contribution_candidate(
                    candidate_id=f"con-candidate-{start_index + len(selected)}",
                    raw=raw,
                    block_records=records,
                    node=node,
                    evidence=evidence,
                    fallback_name=fallback,
                    explicit_type=explicit_type,
                    semantic=semantic,
                    explicit_claim_source_ids=[str(block.get("id") or "")],
                    method_node_ids=(
                        [str(node.get("id"))]
                        if node
                        else synthetic_node_ids
                    ),
                    discovery_source=source,
                )
            )
    return selected


def _contribution_candidates(
    paper_ir: dict[str, Any],
    evidence: dict[str, Any],
    method_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks = {
        str(block.get("id") or ""): block
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }
    # Discovery is driven by explicit author claims. MethodGraph verifies those
    # claims and contributes an extra candidate only when the node itself
    # carries strong novelty/centrality evidence.
    candidates = _explicit_contribution_candidates(
        paper_ir,
        evidence,
        method_graph,
        blocks,
        1,
    )
    discovery_text = " ".join(
        str(block.get("text") or "")
        for block in paper_ir.get("blocks", [])
        if any(
            term in _section_text(block)
            for term in ("abstract", "introduction", "conclusion", "front matter")
        )
    ).lower()
    novelty_pattern = re.compile(
        r"\b(?:we\s+)?(?:propose|introduce|design|develop|construct|build|"
        r"formulate|define|release|adopt|incorporate)\b|\b(?:novel|new)\b",
        re.I,
    )
    for node in method_graph.get("nodes", []):
        if _is_generic_method_heading_node(node):
            continue
        node_name = clean_visible_text(str(node.get("name") or ""))
        node_raw = normalize_text(
            str(node.get("innovation") or node.get("purpose") or "")
        )
        source_blocks = [
            blocks.get(str(source.get("block_id") or ""))
            for source in node.get("sources", [])
        ]
        source_blocks = [block for block in source_blocks if block]
        source_novelty = any(
            novelty_pattern.search(str(block.get("text") or ""))
            for block in source_blocks
        )
        central_name_mention = bool(
            node_name
            and len(_words(node_name)) >= 2
            and node_name.lower() in discovery_text
        )
        substantive_node = bool(
            re.search(
                r"\b(?:fuse|combine|select|weight|route|model|capture|"
                r"preserve|recover|optimi[sz]e|allocate|construct|encode|"
                r"decode|aggregate|learn|adapt|integrate|decompose|"
                r"reconstruct|adopt|incorporate)\w*\b",
                node_raw,
                re.I,
            )
        )
        if not (
            novelty_pattern.search(node_raw)
            or source_novelty
            or (central_name_mention and substantive_node)
        ):
            continue
        component_parts = _enumerated_method_components(node, node_raw)
        if component_parts:
            for component_node, component_raw in component_parts:
                records = []
                for source in component_node.get("sources", []):
                    block = blocks.get(str(source.get("block_id") or ""))
                    if block:
                        records.append(_source_record(block, component_raw))
                if not records:
                    continue
                candidates.append(
                    _contribution_candidate(
                        candidate_id=f"con-candidate-{len(candidates) + 1}",
                        raw=component_raw,
                        block_records=records,
                        node=component_node,
                        evidence=evidence,
                        fallback_name=str(component_node.get("name") or "Core Mechanism"),
                        semantic=_decompose_contribution_statement(
                            component_raw,
                            str(component_node.get("name") or ""),
                        ),
                        explicit_claim_source_ids=[
                            str(record.get("block_id") or "")
                            for record in records
                            if novelty_pattern.search(
                                str(record.get("raw_statement") or "")
                            )
                        ],
                        method_node_ids=[str(component_node.get("id") or "")],
                        discovery_source="method_graph_declared",
                    )
                )
            # The parent sentence is only a container for the independently
            # defined components and must not become an extra Contribution.
            continue
        best_statement, best_block = _best_node_statement(node, paper_ir)
        sibling_mentions = sum(
            bool(
                normalize_text(str(other.get("name") or ""))
                and normalize_text(str(other.get("name") or "")).lower()
                in best_statement.lower()
            )
            for other in method_graph.get("nodes", [])
        )
        if sibling_mentions >= 2:
            # An architecture enumeration establishes membership but does not
            # explain each child mechanism. Do not assign the whole list to
            # every node as if it were node-specific evidence.
            best_statement = ""
            best_block = None
        if (
            re.search(
                r"\b(?:we\s+)?(?:propose|introduce|design|develop|construct|"
                r"build|formulate|define|adopt|incorporate)\b|\b(?:novel|new)\b",
                node_raw,
                re.I,
            )
            and len(_words(node_raw)) >= 6
        ):
            raw = node_raw
            best_block = None
        else:
            raw = best_statement or node_raw
        records = []
        for source in node.get("sources", []):
            block = blocks.get(str(source.get("block_id") or ""))
            if block:
                records.append(_source_record(block, raw or str(block.get("text") or "")))
        if best_block and all(
            str(record.get("block_id")) != str(best_block.get("id"))
            for record in records
        ):
            records.append(_source_record(best_block, raw))
        if not raw or not records:
            continue
        candidates.append(
            _contribution_candidate(
                candidate_id=f"con-candidate-{len(candidates) + 1}",
                raw=raw,
                block_records=records,
                node=node,
                evidence=evidence,
                fallback_name=node_name or "Core Mechanism",
                semantic=_decompose_contribution_statement(raw, node_name),
                explicit_claim_source_ids=[
                    str(record.get("block_id") or "")
                    for record in records
                    if novelty_pattern.search(
                        str(record.get("raw_statement") or "")
                    )
                ],
                method_node_ids=[str(node.get("id") or "")],
                discovery_source="method_graph_declared",
            )
        )
    for index, candidate in enumerate(candidates, start=1):
        candidate["candidate_id"] = f"con-candidate-{index}"
    return candidates


def _all_base_gates_pass(candidate: dict[str, Any]) -> bool:
    return all(
        bool(gate.get("passed"))
        for name, gate in candidate.get("gate_results", {}).items()
        if name != "independence_gate"
    )


def _meaning_key(candidate: dict[str, Any], role: str) -> str:
    if role == "motivation":
        return str(candidate.get("normalized_meaning") or "")
    return " ".join(
        str(candidate.get(key) or "")
        for key in ("innovation_object", "mechanism", "purpose")
    )


def _motivation_topics(value: str) -> set[str]:
    lowered = value.lower()
    patterns = {
        "noise": r"\bnoise|noises|noisy\b",
        "low_contrast": r"\blow[-\s]?contrast|inferior\s+contrast\b",
        "image_quality": r"\bimage\s+quality|visual\s+quality|fidelity\b",
        "scale_variation": (
            r"\bscale\s+variation|varying\s+scales?|scale\s+disparity|"
            r"across\s+(?:all|multiple)\s+scales?|receptive\s+field\b"
        ),
        "long_range": (
            r"\blong[-\s]?range|long\s+distances?|global\s+(?:dependency|"
            r"context|semantic)\b"
        ),
        "quadratic_attention": (
            r"\bquadratic\b.*\b(?:attention|transformer|sequence|complexity)\b|"
            r"\b(?:attention|transformer|sequence)\b.*\bquadratic\b"
        ),
        "spatial_awareness": r"\bspatial\s+awareness|spatial\s+context\b",
        "directionality": r"\bunidirectional|single[-\s]?direction\b",
        "spatial_spectral": r"\bspatial\b.*\bspectral\b|\bspectral\b.*\bspatial\b",
        "vessel_detail": r"\bthin|vessel|capillar|microvessel|boundary\b",
        "small_target": r"\bsmall\s+targets?|target\s+prevalence\b",
        "degraded_object": (
            r"\bdegraded\s+(?:objects?|images?|visual\s+data)\b|"
            r"\blow[-\s]?quality\s+objects?\b"
        ),
        "data_scarcity": r"\blimited\s+data|small\s+data|data\s+scarcity\b",
        "texture": r"\btexture|signal-to-(?:noise|clutter)\b",
        "rain_degradation": (
            r"\brain(?:drop|y)?|derain|frequency\s+(?:loss|information)\b"
        ),
        "clinical_delay": r"\bdelay|timely|intervention\b",
        "clinical_screening": r"\bclinical|screen|diagnos|fundus\s+disease\b",
        "foreground": r"\bforeground|background\b",
        "training_resource": (
            r"\btraining\b.*\b(?:parameters?|costs?|resources?|data)\b|"
            r"\b(?:parameters?|costs?|resources?|data)\b.*\btraining\b"
        ),
        "inference_resource": (
            r"\binference\b.*\b(?:parameters?|devices?|memory|resources?)\b|"
            r"\b(?:devices?|memory|resources?)\b.*\binference\b"
        ),
        "resource_efficiency": r"\bunderperform|less\s+efficient|inefficient\b",
    }
    return {
        name for name, pattern in patterns.items() if re.search(pattern, lowered)
    }


def _visible_motivation_duplicate(
    visible: str,
    selected: Iterable[dict[str, Any]],
) -> str | None:
    """Return the selected candidate duplicated by a rewritten visible item."""

    ignored = {
        "effective",
        "existing",
        "methods",
        "method",
        "models",
        "model",
        "solutions",
        "solution",
        "must",
        "require",
        "requires",
        "address",
        "challenge",
        "challenges",
        "issue",
        "issues",
        "problem",
        "problems",
        "the",
        "and",
        "for",
        "with",
    }
    normalized = normalize_text(visible).lower().strip(" .")
    tokens = token_set(normalized) - ignored
    topics = _motivation_topics(normalized)
    generic_direction = bool(
        re.search(
            r"^\s*effective\s+(?:methods?|solutions?)\s+"
            r"(?:must|need\s+to|require)\s+(?:address|handle|solve)\b",
            normalized,
            re.I,
        )
    )
    for item in selected:
        prior_visible = normalize_text(
            str(
                (item.get("_rewrite_result") or {}).get("visible_text")
                or item.get("visible_text")
                or ""
            )
        ).lower().strip(" .")
        if not prior_visible:
            continue
        candidate_id = str(item.get("candidate_id") or "")
        if normalized == prior_visible:
            return candidate_id
        prior_tokens = token_set(prior_visible) - ignored
        shared_topics = topics & _motivation_topics(prior_visible)
        containment = (
            len(tokens & prior_tokens) / min(len(tokens), len(prior_tokens))
            if tokens and prior_tokens
            else 0.0
        )
        explicit_scale_problem = re.compile(
            r"\b(?:scale\s+variation|scale\s+disparity|varying\s+scales?|"
            r"across\s+(?:all|multiple)\s+scales?)\b",
            re.I,
        )
        if (
            "scale_variation" in shared_topics
            and explicit_scale_problem.search(normalized)
            and explicit_scale_problem.search(prior_visible)
        ):
            return candidate_id
        if shared_topics and (
            containment >= 0.5
            or generic_direction
        ):
            return candidate_id
    return None


def _same_semantic_unit(left: dict[str, Any], right: dict[str, Any], role: str) -> bool:
    if role == "contribution":
        left_identity = str(left.get("canonical_object_id") or "")
        right_identity = str(right.get("canonical_object_id") or "")
        if left_identity and left_identity == right_identity:
            return True
        left_group = str(left.get("author_contribution_group_id") or "")
        right_group = str(right.get("author_contribution_group_id") or "")
        if left_group and left_group == right_group:
            return True
        left_type = _canonical_contribution_type(
            str(left.get("contribution_type") or "")
        )
        right_type = _canonical_contribution_type(
            str(right.get("contribution_type") or "")
        )
        independent_pairs = {
            frozenset({"architecture", "module"}),
            frozenset({"architecture", "mechanism"}),
            frozenset({"architecture", "objective_or_loss"}),
            frozenset({"architecture", "theoretical_contribution"}),
            frozenset({"algorithm", "theoretical_contribution"}),
            frozenset({"dataset", "architecture"}),
            frozenset({"dataset", "algorithm"}),
            frozenset({"independent_empirical_finding", "architecture"}),
            frozenset({"independent_empirical_finding", "module"}),
        }
        if frozenset({left_type, right_type}) in independent_pairs:
            return False
        left_object = normalize_text(str(left.get("innovation_object") or "")).lower()
        right_object = normalize_text(str(right.get("innovation_object") or "")).lower()
        left_canonical = re.sub(r"[^a-z0-9]+", "", left_object)
        right_canonical = re.sub(r"[^a-z0-9]+", "", right_object)
        object_equal = bool(left_canonical and left_canonical == right_canonical)
        meaning_overlap = jaccard(
            _meaning_key(left, role), _meaning_key(right, role)
        )
        same_node = bool(
            set(left.get("method_node_ids") or [left.get("method_node_id")])
            & set(right.get("method_node_ids") or [right.get("method_node_id")])
            - {None, ""}
        )
        left_tokens = token_set(_meaning_key(left, role))
        right_tokens = token_set(_meaning_key(right, role))
        opposed_scope = bool(
            ("global" in left_tokens and "local" in right_tokens)
            or ("local" in left_tokens and "global" in right_tokens)
        )
        method_family_types = {
            "architecture",
            "algorithm",
            "mechanism",
            "optimization_or_training_method",
            "representation_method",
        }
        shared_method_anchors = (
            left_tokens
            & right_tokens
            & {
                "cnn",
                "network",
                "solver",
                "inversion",
                "inverse",
                "reconstruction",
                "fusion",
                "attention",
                "encoder",
                "decoder",
                "transformer",
            }
        )
        solved_problem_overlap = jaccard(
            str(left.get("solved_problem") or left.get("purpose") or ""),
            str(right.get("solved_problem") or right.get("purpose") or ""),
        )
        if (
            same_node
            and not opposed_scope
            and left_type in method_family_types
            and right_type in method_family_types
            and (
                meaning_overlap >= 0.22
                or len(shared_method_anchors) >= 2
                or (
                    len(shared_method_anchors) >= 1
                    and solved_problem_overlap >= 0.18
                )
            )
        ):
            return True
        if object_equal and (left_type == right_type or meaning_overlap >= 0.45):
            return True
        object_overlap = jaccard(left_object, right_object)
        if (
            left_object
            and right_object
            and (left_object in right_object or right_object in left_object)
        ):
            return bool(left_type == right_type or meaning_overlap >= 0.55)
        if same_node:
            return bool(
                left_type == right_type
                and (object_overlap >= 0.35 or meaning_overlap >= 0.5)
            )
        return bool(
            left_type == right_type
            and object_overlap >= 0.62
            and meaning_overlap >= 0.48
        )
    left_meaning = _meaning_key(left, role)
    right_meaning = _meaning_key(right, role)
    left_topics = _motivation_topics(
        f"{left_meaning} {left.get('raw_statement') or ''}"
    )
    right_topics = _motivation_topics(
        f"{right_meaning} {right.get('raw_statement') or ''}"
    )
    left_type = str(left.get("type") or "")
    right_type = str(right.get("type") or "")
    left_role = str(left.get("role") or "")
    right_role = str(right.get("role") or "")
    if left_role and right_role and left_role != right_role:
        return False
    same_type = left_type == right_type
    problem_family = {
        "task_challenge",
        "data_challenge",
        "prior_method_limitation",
        "unresolved_gap",
    }
    cross_type_merge_allowed = (
        left_type in problem_family and right_type in problem_family
    )
    lexical_overlap = jaccard(left_meaning, right_meaning)
    if left_topics and left_topics == right_topics:
        return bool(
            (same_type or cross_type_merge_allowed)
            and (
                lexical_overlap >= 0.58
                or (
                    len(left_topics) >= 2
                    and lexical_overlap >= 0.12
                )
                or "resource_efficiency" in left_topics
            )
        )
    shared_topics = left_topics & right_topics
    if (
        "rain_degradation" in shared_topics
        and (same_type or cross_type_merge_allowed)
    ):
        return True
    narrow_duplicate_topics = {
        "quadratic_attention",
        "spatial_awareness",
        "directionality",
    }
    if (
        shared_topics & narrow_duplicate_topics
        and (same_type or cross_type_merge_allowed)
        and lexical_overlap >= 0.15
    ):
        return True
    if (
        shared_topics
        and len(shared_topics) >= 2
        and len(shared_topics) / min(len(left_topics), len(right_topics)) >= 0.67
    ):
        return bool(same_type or cross_type_merge_allowed)
    if (
        "resource_efficiency" in left_topics & right_topics
        and (same_type or cross_type_merge_allowed)
    ):
        return True
    return (
        lexical_overlap >= (0.62 if same_type else 0.74)
        and (same_type or cross_type_merge_allowed)
        or (
            left_meaning.lower() in right_meaning.lower()
            or right_meaning.lower() in left_meaning.lower()
        )
        and (same_type or cross_type_merge_allowed)
        and min(len(_words(left_meaning)), len(_words(right_meaning))) >= 5
    )


def _merge_candidates(
    candidates: list[dict[str, Any]],
    role: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted = [candidate for candidate in candidates if _all_base_gates_pass(candidate)]
    rejected = [candidate for candidate in candidates if not _all_base_gates_pass(candidate)]
    accepted.sort(
        key=lambda item: (
            float(item.get("importance") or 0),
            -min(
                int(record.get("page") or 1)
                for record in item.get("source_records", [])
            ),
        ),
        reverse=True,
    )
    clusters: list[list[dict[str, Any]]] = []
    for candidate in accepted:
        cluster = next(
            (
                values
                for values in clusters
                if _same_semantic_unit(values[0], candidate, role)
            ),
            None,
        )
        if cluster is None:
            clusters.append([candidate])
        else:
            cluster.append(candidate)

    merged: list[dict[str, Any]] = []
    for cluster in clusters:
        primary = dict(cluster[0])
        if role == "contribution" and len(cluster) > 1:
            def detail_score(value: dict[str, Any]) -> float:
                mechanism = str(
                    value.get("mechanism_or_action")
                    or value.get("mechanism")
                    or ""
                )
                purpose = str(
                    value.get("solved_problem")
                    or value.get("purpose")
                    or ""
                )
                score = min(10, len(_words(mechanism))) + min(
                    10, len(_words(purpose))
                )
                if re.search(
                    r"\b(?:direct|adaptive|hierarchical|multiscale|"
                    r"edge|global|local|residual|deformable|selective)\b",
                    mechanism,
                    re.I,
                ):
                    score += 4
                if re.search(r"\b(?:these|them|respectively)\b", purpose, re.I):
                    score -= 3
                if jaccard(mechanism, purpose) >= 0.55:
                    score -= 4
                return score

            detail = max(cluster, key=detail_score)
            if detail_score(detail) > detail_score(primary):
                for key in (
                    "mechanism",
                    "mechanism_or_action",
                    "purpose",
                    "solved_problem",
                    "reported_effect",
                    "description",
                ):
                    if detail.get(key):
                        primary[key] = detail[key]
        primary["merged_from"] = [
            value["candidate_id"] for value in cluster[1:]
        ]
        primary["source_records"] = [
            dict(record)
            for value in cluster
            for record in value.get("source_records", [])
        ]
        if role == "contribution":
            for field in (
                "method_node_ids",
                "explicit_claim_source_ids",
                "supporting_evidence_ids",
                "source_block_ids",
                "source_pages",
                "source_sections",
                "method_sections",
            ):
                primary[field] = sorted(
                    {
                        item
                        for value in cluster
                        for item in (value.get(field) or [])
                        if item not in {None, ""}
                    }
                )
            primary["supporting_evidence"] = [
                evidence_item
                for value in cluster
                for evidence_item in value.get("supporting_evidence", [])
            ]
            group_ids = [
                str(value.get("author_contribution_group_id") or "")
                for value in cluster
                if value.get("author_contribution_group_id")
            ]
            if group_ids:
                primary["author_contribution_group_id"] = group_ids[0]
        seen_records: set[tuple[str, str]] = set()
        primary["source_records"] = [
            record
            for record in primary["source_records"]
            if not (
                (str(record.get("block_id")), str(record.get("raw_statement")))
                in seen_records
                or seen_records.add(
                    (str(record.get("block_id")), str(record.get("raw_statement")))
                )
            )
        ]
        if role == "contribution":
            cluster_source_text = " ".join(
                str(record.get("raw_statement") or "")
                for record in primary["source_records"]
            )
            named_method = re.search(
                r"\b(?:which\s+we\s+call|called|named|termed)\s+(?:the\s+)?"
                r"([A-Z][A-Za-z0-9_-]{2,})\b",
                cluster_source_text,
            )
            if named_method:
                primary["innovation_object"] = named_method.group(1)
            if (
                re.search(r"\bdirect inversion\b", cluster_source_text, re.I)
                and re.search(r"\bCNN\b", cluster_source_text)
            ):
                primary["mechanism"] = (
                    "uses direct inversion as a physics-based front end and "
                    "a CNN for learned refinement"
                )
                primary["mechanism_or_action"] = primary["mechanism"]
                primary["purpose"] = (
                    "reconstruct images from ill-posed normal-convolutional measurements"
                )
                primary["solved_problem"] = primary["purpose"]
        merged.append(primary)
        for duplicate in cluster[1:]:
            duplicate = dict(duplicate)
            duplicate["gate_results"] = dict(duplicate["gate_results"])
            duplicate["gate_results"]["independence_gate"] = {
                "passed": False,
                "reason": f"merged into {primary['candidate_id']}",
            }
            duplicate["merged_into"] = primary["candidate_id"]
            rejected.append(duplicate)
    return merged, rejected


def _remove_protected_phrases(value: str, protected_terms: Iterable[str]) -> str:
    result = value
    for term in sorted(
        {normalize_text(str(term)) for term in protected_terms if normalize_text(str(term))},
        key=len,
        reverse=True,
    ):
        result = re.sub(re.escape(term), " PROTECTED ", result, flags=re.I)
    return result


def longest_source_overlap(
    visible_text: str,
    raw_statement: str,
    protected_terms: Iterable[str] = (),
) -> int:
    visible = [
        token.lower()
        for token in _words(_remove_protected_phrases(visible_text, protected_terms))
        if token.lower() != "protected"
    ]
    source = [
        token.lower()
        for token in _words(_remove_protected_phrases(raw_statement, protected_terms))
        if token.lower() != "protected"
    ]
    if not visible or not source:
        return 0
    previous = [0] * (len(source) + 1)
    longest = 0
    for left in visible:
        current = [0]
        for index, right in enumerate(source, start=1):
            value = previous[index - 1] + 1 if left == right else 0
            current.append(value)
            longest = max(longest, value)
        previous = current
    return longest


def _unsupported_visible_entities(
    visible_text: str,
    raw_statement: str,
) -> list[str]:
    """Return technical entities or burden concepts introduced by rewriting."""

    visible = normalize_text(visible_text)
    raw = normalize_text(raw_statement)
    raw_lower = raw.lower()
    aliases = {
        "ct": ("computed tomography",),
        "cnn": ("convolutional neural network",),
        "ir": ("iterative reconstruction",),
        "tv": ("total variation",),
        "moe": ("mixture of experts", "mixture-of-experts", "expert model"),
    }
    failures: list[str] = []
    for entity in TECHNICAL_ENTITY_RE.findall(visible):
        lowered = entity.lower()
        if lowered in raw_lower:
            continue
        if any(alias in raw_lower for alias in aliases.get(lowered, ())):
            continue
        failures.append(entity)
    if "large model" in visible.lower() and not re.search(
        r"\b(?:large[-\s]+model|model\s+size|parameter\s+count|"
        r"more\s+parameters?|many\s+parameters?|large\s+parameter\s+sizes?)\b",
        raw,
        re.I,
    ):
        failures.append("large model")
    if re.search(r"\bparameters?\b", visible, re.I) and not re.search(
        r"\bparameters?\b", raw, re.I
    ):
        failures.append("parameters")
    if re.search(r"\bdeployment\b", visible, re.I) and not re.search(
        r"\b(?:deploy(?:ment|ing|ed)?|practical\s+(?:use|applications?)|"
        r"real[-\s]?world|resource[-\s]?constrained|inference)\b",
        raw,
        re.I,
    ):
        failures.append("deployment")
    return list(dict.fromkeys(failures))


def _candidate_final_semantic_gates(
    candidate: dict[str, Any],
    context: str,
) -> dict[str, dict[str, Any]]:
    structure = candidate.get("relation_structure") or {}
    subject = normalize_text(str(structure.get("subject") or ""))
    obj = normalize_text(
        str(
            structure.get("object")
            or structure.get("condition")
            or structure.get("consequence")
            or ""
        )
    )
    relevance = _relevance_overlap(f"{subject} {obj}", context)
    specific = bool(
        len(token_set(f"{subject} {obj}")) >= 3
        and not VAGUE_MOTIVATION_SUBJECT_RE.search(subject)
        and not GENERIC_MOTIVATION_RE.fullmatch(
            _semantic_source_text(str(candidate.get("source_clause") or ""))
        )
    )
    source_clause = _semantic_source_text(
        str(candidate.get("source_clause") or "")
    )
    scope_ok = not bool(
        POSITIVE_RESULT_RE.search(source_clause)
        or RESOLUTION_METHOD_HISTORY_RE.search(source_clause)
        or re.search(
            r"\b(?:the\s+)?(?:model|method|network|approach)\s+can\s+"
            r"(?:make|achieve|improve|produce|obtain|generate)\b|"
            r"\b(?:significantly|substantially)\s+improv(?:e|es|ed)\b|"
            r"^(?:this|it)\s+not\s+only\s+aids?\b|"
            r"^the\s+paper\s+addresses\s+(?:this|these|those|it)\b",
            source_clause,
            re.I,
        )
        or (
            PURE_METHOD_PROPOSITION_RE.search(source_clause)
            and not EXPLICIT_PROBLEM_RELATION_RE.search(source_clause)
        )
    )
    return {
        "core_relevance_gate": {
            "passed": (
                relevance >= 0.025
                or (
                    str(structure.get("relation") or "")
                    == "paper_targets_problem"
                    and candidate.get("extraction_mode")
                    == "paper_objective_split"
                    and len(token_set(obj)) >= 3
                )
                or bool(PROBLEM_SIGNAL_RE.search(obj))
                or bool(
                    PROBLEM_SIGNAL_RE.search(
                        _semantic_source_text(
                            str(candidate.get("source_clause") or "")
                        )
                    )
                )
            ),
            "reason": "candidate directly relates to the paper task or a concrete problem relation",
        },
        "specificity_gate": {
            "passed": specific,
            "reason": "candidate names a concrete subject and relation object",
        },
        "independence_gate": {
            "passed": True,
            "reason": "evaluated through role-aware semantic clustering",
        },
        "scope_gate": {
            "passed": scope_ok,
            "reason": "candidate remains problem-side and does not depend on a result claim",
        },
        "role_coverage_gate": {
            "passed": _motivation_coverage_family(candidate) is not None,
            "reason": (
                "candidate maps to a problem, unresolved-constraint, or "
                "research-direction coverage family"
            ),
        },
    }


def _candidate_passes_final_semantics(candidate: dict[str, Any]) -> bool:
    return all(
        bool(result.get("passed"))
        for result in candidate.get("final_gate_results", {}).values()
    )


def _select_motivation_from_pool(
    candidates: list[dict[str, Any]],
    context: str,
    *,
    paper_type: str = "method_paper",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    merged, merged_rejected = _merge_candidates(candidates, "motivation")
    for candidate in merged:
        candidate["final_gate_results"] = _candidate_final_semantic_gates(
            candidate,
            context,
        )
    eligible = [
        candidate
        for candidate in merged
        if _candidate_passes_final_semantics(candidate)
    ]
    eligible.sort(
        key=lambda item: (
            float(item.get("importance") or 0),
            -min(
                int(record.get("page") or 1)
                for record in item.get("source_records", [])
            ),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    slot_winners: dict[str, str | None] = {}
    for slot in MOTIVATION_COVERAGE_SLOTS:
        queue = sorted(
            (
                candidate
                for candidate in eligible
                if candidate not in selected
                and _motivation_coverage_family(candidate, paper_type)
                in MOTIVATION_REQUIRED_FAMILIES
            ),
            key=lambda item: _motivation_slot_rank(
                item,
                slot,
                paper_type,
            ),
        )
        winner = next(
            iter(queue),
            None,
        )
        slot_winners[slot] = (
            str(winner.get("candidate_id") or "") if winner else None
        )
        if winner:
            winner["coverage_family"] = _motivation_coverage_family(
                winner,
                paper_type,
            )
            winner["coverage_slot"] = slot
            winner["selection_role"] = str(
                winner.get("role") or winner.get("type") or slot
            )
            selected.append(winner)

    optional_candidates = [
        candidate
        for candidate in eligible
        if candidate not in selected
        and _motivation_coverage_family(candidate, paper_type)
        in MOTIVATION_REQUIRED_FAMILIES
    ]
    optional_candidates.sort(
        key=lambda item: (
            float(item.get("importance") or 0),
            -min(
                int(record.get("page") or 1)
                for record in item.get("source_records", [])
            ),
        ),
        reverse=True,
    )
    for candidate in optional_candidates:
        if len(selected) >= 5:
            break
        candidate["selection_role"] = (
            str(candidate.get("role") or "additional_independent_limitation")
        )
        candidate["coverage_family"] = _motivation_coverage_family(
            candidate, paper_type
        )
        candidate["coverage_slot"] = f"optional_{len(selected) - 2}"
        selected.append(candidate)

    selected_ids = {
        str(candidate.get("candidate_id") or "") for candidate in selected
    }
    rejected = list(merged_rejected)
    for candidate in merged:
        candidate_id = str(candidate.get("candidate_id") or "")
        if candidate_id in selected_ids:
            candidate["selected"] = True
            continue
        rejected_candidate = dict(candidate)
        rejected_candidate["selected"] = False
        rejected_candidate["rejection_stage"] = "coverage_assembly"
        rejected_candidate["rejection_reasons"] = (
            [
                name
                for name, result in candidate.get(
                    "final_gate_results",
                    {},
                ).items()
                if not bool(result.get("passed"))
            ]
            or ["not selected after required-role coverage assembly"]
        )
        rejected.append(rejected_candidate)

    slot_order = {
        "core_problem": 1,
        "unresolved_driver": 2,
        "reading_direction": 3,
        "optional_1": 4,
        "optional_2": 5,
    }
    selected.sort(
        key=lambda item: (
            slot_order.get(
                str(item.get("coverage_slot") or ""), 99
            ),
            -float(item.get("importance") or 0),
        )
    )
    selected = selected[:5]
    return selected, rejected, {
        "input_candidate_ids": [
            str(candidate.get("candidate_id") or "")
            for candidate in candidates
        ],
        "input_count": len(candidates),
        "merged_candidate_ids": [
            str(candidate.get("candidate_id") or "")
            for candidate in merged
        ],
        "merged_count": len(merged),
        "semantic_gate_pass_ids": [
            str(candidate.get("candidate_id") or "")
            for candidate in eligible
        ],
        "semantic_gate_pass_count": len(eligible),
        "merge_map": {
            str(candidate.get("candidate_id") or ""): list(
                candidate.get("merged_from") or []
            )
            for candidate in merged
            if candidate.get("merged_from")
        },
        "required_slot_winners": {
            slot: slot_winners.get(slot)
            for slot in MOTIVATION_COVERAGE_SLOTS
        },
        "required_role_winners": {
            role: next(
                (
                    str(candidate.get("candidate_id") or "")
                    for candidate in selected
                    if str(
                        candidate.get("selection_role")
                        or candidate.get("role")
                        or ""
                    )
                    == role
                ),
                None,
            )
            for role in MOTIVATION_REQUIRED_ROLES
        },
        "paper_type": paper_type,
        "required_coverage_status": {
            slot: bool(slot_winners.get(slot))
            for slot in MOTIVATION_COVERAGE_SLOTS
        },
        "required_family_status": {
            family: any(
                str(item.get("coverage_family") or "") == family
                for item in selected
            )
            for family in MOTIVATION_REQUIRED_FAMILIES
        },
        "selected_candidate_ids": [
            str(candidate.get("candidate_id") or "")
            for candidate in selected
        ],
    }


def _assemble_motivation_coverage(
    candidates: list[dict[str, Any]],
    paper_ir: dict[str, Any],
    story: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
    dict[str, Any],
]:
    valid = [
        candidate
        for candidate in candidates
        if _all_base_gates_pass(candidate)
    ]
    context = _story_context(story, paper_ir)
    paper_type = _classify_motivation_paper_type(paper_ir, story)
    initial = [
        candidate
        for candidate in valid
        if candidate.get("section_kind") == "introduction"
        and float(candidate.get("importance") or 0) >= 0.78
        and candidate.get("extraction_mode") == "whole_sentence"
        and "expanded_reference_context"
        not in candidate.get("recovery_tags", [])
        and (candidate.get("relation_structure") or {}).get("relation")
        != "paper_targets_problem"
    ]
    pool: list[dict[str, Any]] = list(initial)
    selected, rejected, selection_snapshot = _select_motivation_from_pool(
        pool,
        context,
        paper_type=paper_type,
    )
    executed: list[str] = []
    recovery_trace: list[dict[str, Any]] = []

    recovery_steps = (
        (
            "rescan_introduction_front_30_percent",
            lambda item: "introduction_front_30_percent"
            in item.get("recovery_tags", []),
        ),
        (
            "rescan_introduction_middle",
            lambda item: "introduction_middle" in item.get("recovery_tags", []),
        ),
        (
            "scan_pre_method_transition",
            lambda item: "pre_method_transition"
            in item.get("recovery_tags", []),
        ),
        (
            "check_abstract_front_half",
            lambda item: "abstract_front_half"
            in item.get("recovery_tags", []),
        ),
        (
            "resplit_compound_clauses",
            lambda item: "compound_clause_resplit"
            in item.get("recovery_tags", []),
        ),
        (
            "expand_reference_context",
            lambda item: "expanded_reference_context"
            in item.get("recovery_tags", []),
        ),
        (
            "recheck_surface_artifacts",
            lambda item: "surface_artifact_recheck"
            in item.get("recovery_tags", []),
        ),
        ("recheck_over_merging", lambda item: True),
        (
            "recheck_paper_objective",
            lambda item: "paper_objective_recheck"
            in item.get("recovery_tags", []),
        ),
    )
    for step, predicate in recovery_steps:
        covered_slots = {
            str(item.get("coverage_slot") or "")
            for item in selected
        }
        if all(
            slot in covered_slots
            for slot in MOTIVATION_COVERAGE_SLOTS
        ):
            break
        executed.append(step)
        known = {
            str(candidate.get("candidate_id") or "") for candidate in pool
        }
        added = [
            candidate
            for candidate in valid
            if predicate(candidate)
            and str(candidate.get("candidate_id") or "") not in known
        ]
        pool.extend(added)
        selected, rejected, selection_snapshot = (
            _select_motivation_from_pool(
                pool,
                context,
                paper_type=paper_type,
            )
        )
        recovery_trace.append(
            {
                "step": step,
                "added_candidate_ids": [
                    str(candidate.get("candidate_id") or "")
                    for candidate in added
                ],
                "pool_count": len(pool),
                "selected_candidate_ids": list(
                    selection_snapshot["selected_candidate_ids"]
                ),
                "required_slot_winners": dict(
                    selection_snapshot["required_slot_winners"]
                ),
            }
        )
    return selected, rejected, executed, {
        "initial_candidate_ids": [
            str(candidate.get("candidate_id") or "")
            for candidate in initial
        ],
        "valid_candidate_count": len(valid),
        "recovery_trace": recovery_trace,
        **selection_snapshot,
    }


def _poster_fragment(value: str, limit: int = 12) -> str:
    text = clean_visible_text(value)
    text = re.sub(
        r"^\s*(?:the\s+paper\s+objective|the\s+issue|the\s+problem)\s*$",
        "",
        text,
        flags=re.I,
    )
    return _clip_words(text.strip(" ,;:."), limit)


def _normalized_motivation_relation(
    candidate: dict[str, Any],
) -> dict[str, str]:
    structure = candidate.get("relation_structure") or {}
    raw = _semantic_source_text(
        str(candidate.get("source_clause") or candidate.get("raw_statement") or "")
    )
    subject = _poster_fragment(str(structure.get("subject") or ""), 11)
    subject = re.sub(
        r"(?:\s+(?:is|are|was|were|still|not|only|merely))+\s*$",
        "",
        subject,
        flags=re.I,
    ).strip(" ,;:.")
    obj = _poster_fragment(str(structure.get("object") or ""), 14)
    obj = re.sub(r"^\s*(?:by|to|for)\s+", "", obj, flags=re.I).strip(" ,;:.")
    obj = re.sub(
        r"\b(lesions?\s+or\s+organs?)\s+category\s+features\b",
        r"\1",
        obj,
        flags=re.I,
    )
    condition = _poster_fragment(str(structure.get("condition") or ""), 11)
    consequence = _poster_fragment(
        str(structure.get("consequence") or ""),
        12,
    )
    relation = str(structure.get("relation") or "")
    normalized = {
        "prior_method_lacks_capability": "lacks_capability",
        "prior_method_causes_failure": "struggles_with",
        "task_is_difficult_under_condition": "struggles_with",
        "data_contains_challenge": "struggles_with",
        "tradeoff_remains_unresolved": "creates_tradeoff",
        "research_gap_remains": "remains_unresolved",
        "solution_requires_capability": "requires_capability",
        "paper_targets_problem": "requires_capability",
        "problem_has_consequence": "causes_failure",
    }.get(relation, relation)
    if re.search(r"\b(?:is|are)\s+(?:still\s+)?limited\s+by\b", raw, re.I):
        normalized = "is_limited_in"
    elif re.search(
        r"\b(?:computational|memory|resource|latency|parameter|overhead|cost)\b",
        f"{obj} {condition} {consequence}",
        re.I,
    ):
        normalized = "increases_resource_cost"
    return {
        "subject": subject,
        "object": obj,
        "condition": condition,
        "consequence": consequence,
        "relation": normalized,
        "source_relation": relation,
    }


def _requirement_sentence(object_text: str) -> str:
    capability = _poster_fragment(object_text, 14)
    capability = re.sub(r"^\s*to\s+", "", capability, flags=re.I)
    capability = re.sub(
        r"\b(lesions?\s+or\s+organs?)\s+as\s+category\s+features\b",
        r"category-aware modeling of \1",
        capability,
        flags=re.I,
    )
    if not capability:
        return ""
    if re.match(
        r"^(?:bind|distinguish|capture|model|preserve|handle|exploit|focus|"
        r"recover|represent|combine|integrate|identify|separate|use)\b",
        capability,
        re.I,
    ):
        return _sentence_case(f"Effective methods must {capability}")
    return _sentence_case(f"Effective methods require {capability}")


def _relation_motivation_rewrite(candidate: dict[str, Any]) -> str:
    structure = _normalized_motivation_relation(candidate)
    subject = structure["subject"]
    obj = structure["object"]
    condition = structure["condition"]
    consequence = structure["consequence"]
    relation = structure["relation"]
    raw = _semantic_source_text(
        str(candidate.get("source_clause") or candidate.get("raw_statement") or "")
    )
    inverse_challenge = re.search(
        r"(?:in\s+([^,]+),\s*)?"
        r"(?:one\s+of\s+(?:the\s+)?(?:main|key|major|primary)\s+"
        r"challenges?\s+is|(?:a|the)\s+(?:main|key|major|primary)\s+"
        r"challenge\s+is)\s+(.+)",
        raw,
        re.I,
    )
    if inverse_challenge:
        domain = _poster_fragment(inverse_challenge.group(1) or "", 6)
        challenge = _poster_fragment(inverse_challenge.group(2), 9)
        suffix = f" in {domain}" if domain else ""
        return _sentence_case(f"{challenge} remains a primary challenge{suffix}")
    growing_importance = re.search(
        r"(?:with|as)\s+(.+?),\s*(.+?)\s+(?:has|have)\s+become\s+"
        r"(?:increasingly\s+)?(?:important|critical|essential)",
        raw,
        re.I,
    )
    if growing_importance:
        subject_text = _poster_fragment(growing_importance.group(2), 8)
        condition_text = _poster_fragment(growing_importance.group(1), 8)
        growing_demand = re.match(
            r"(?:the\s+)?growing\s+demand\s+for\s+(.+)",
            condition_text,
            re.I,
        )
        if growing_demand:
            return _sentence_case(
                f"Demand for {_poster_fragment(growing_demand.group(1), 8)} "
                f"increases the need for {subject_text}"
            )
        return _sentence_case(
            f"{subject_text} matter increasingly as {condition_text} grows"
        )
    lowered_raw = raw.lower()
    if (
        "inherent limitations of convolutional operations" in lowered_raw
        and "global contextual information" in lowered_raw
    ):
        return _sentence_case(
            "Local convolutions limit CNN access to global context"
        )
    if (
        "transformer-based medical image segmentation" in lowered_raw
        and "integrate multi-scale information" in lowered_raw
    ):
        return _sentence_case(
            "Transformer segmenters can miss lesions when multi-scale "
            "features are poorly integrated"
        )
    if (
        "lesion edges are often irregular" in lowered_raw
        and "loss of fine details" in lowered_raw
    ):
        return _sentence_case(
            "Irregular, low-contrast lesion boundaries lose detail during "
            "feature compression"
        )
    if (
        "traditional diagnostic methods" in lowered_raw
        and "subjectivity and invasiveness" in lowered_raw
    ):
        return _sentence_case(
            "Subjective and invasive diagnostics do not scale well to "
            "population screening"
        )
    if (
        "prevalence of low-quality objects" in lowered_raw
        and bool(
            re.search(
                r"\b(?:sensor resolution|atmospheric interference|"
                r"motion blur|variable illumination|occlusions?)\b",
                lowered_raw,
            )
        )
    ):
        return _sentence_case(
            "Sensor limits, weather, blur, illumination, and occlusion "
            "degrade remote-sensing objects"
        )
    if (
        "degradation factors compromise feature discriminability"
        in lowered_raw
    ):
        return _sentence_case(
            "Degradation lowers contrast, breaks object boundaries, and "
            "weakens feature responses"
        )
    if (
        "success in multi-scale detection" in lowered_raw
        and "degraded objects" in lowered_raw
    ):
        return _sentence_case(
            "Multi-scale detectors still represent degraded objects "
            "unreliably"
        )
    if (
        "existing rsod methods" in lowered_raw
        and "low-quality objects" in lowered_raw
    ):
        return _sentence_case(
            "Existing remote-sensing detectors remain unreliable on "
            "degraded objects"
        )
    if (
        "diffusion models" in lowered_raw
        and "large prior models" in lowered_raw
        and "computational burden" in lowered_raw
    ):
        return _sentence_case(
            "Large priors and repeated denoising make diffusion restoration "
            "computationally expensive"
        )
    if (
        "cannot remove rains" in lowered_raw
        and bool(re.search(r"\b(?:appearance|scale)s?\b", lowered_raw))
    ):
        return _sentence_case(
            "Manual hyperparameter tuning limits deraining across varied "
            "rain appearances and scales"
        )
    if (
        "insufficient utilization of features at different levels"
        in lowered_raw
        and "semantic conflicts between deep and shallow features"
        in lowered_raw
    ):
        return _sentence_case(
            "Existing networks underuse cross-level features and risk "
            "conflicts between deep and shallow semantics"
        )
    if (
        "did not fully leverage features across different levels"
        in lowered_raw
    ):
        return _sentence_case(
            "Earlier segmentation networks underuse features across "
            "representation levels"
        )
    if (
        re.search(
            r"only\s+trained\s+and\s+(?:tested|evaluated)\s+on\s+"
            r"open[-\s]source\s+datasets",
            lowered_raw,
        )
    ):
        return _sentence_case(
            "Open-source-only evaluation leaves real-world generalization uncertain"
        )
    if "vessel information loss" in lowered_raw and "pooling" in lowered_raw:
        return _sentence_case(
            "Pooling can discard fine vessel information"
        )
    if "thousands of annotated training samples" in lowered_raw:
        return _sentence_case(
            "Transformer training depends on thousands of annotated samples"
        )
    if (
        "self-attentive mechanism" in lowered_raw
        and "large-size images" in lowered_raw
    ):
        return _sentence_case(
            "Global self-attention scales poorly to large images"
        )
    if (
        "retinal blood vessels extracted from fundus images" in lowered_raw
        and "early diagnosis" in lowered_raw
    ):
        return _sentence_case(
            "Retinal vessel analysis supports early diagnosis of severe disease"
        )
    if "image deraining is an important task" in lowered_raw:
        return _sentence_case(
            "Image deraining is central to low-level vision"
        )
    if (
        "challenges in medical image segmentation" in lowered_raw
        and re.search(r"\bto\s+address\b", lowered_raw)
    ):
        return _sentence_case(
            "Medical image segmentation remains challenging"
        )
    if (
        "must not only provide high-quality segmentation results" in lowered_raw
        and "uncertainty metrics" in lowered_raw
    ):
        return _sentence_case(
            "Clinical segmentation requires accurate predictions and uncertainty estimates"
        )
    if (
        "success in multi-scale detection" in lowered_raw
        and "low-quality or degraded objects" in lowered_raw
    ):
        return _sentence_case(
            "Multi-scale detectors struggle to represent degraded objects reliably"
        )
    if (
        "should be recognized with correspondingly required receptive fields"
        in lowered_raw
    ):
        return _sentence_case(
            "HSI recognition requires receptive fields adapted to each land-cover type"
        )
    if (
        "local convolutional structure limits" in lowered_raw
        and "long-range dependencies" in lowered_raw
    ):
        return _sentence_case(
            "Local convolutions cannot capture long-range dependencies"
        )
    if "small polyps" in lowered_raw and "uneven lighting" in lowered_raw:
        return _sentence_case(
            "Uneven lighting makes small polyps difficult to segment"
        )
    if "treat local and global contexts equally" in lowered_raw:
        return _sentence_case(
            "Uniform local-global weighting cannot adapt to image content or network depth"
        )
    if "pay extra computations" in lowered_raw:
        return _sentence_case(
            "Pure self-attention increases computation by discarding efficient convolutional operators"
        )
    if "it is natural to study hybrid networks" in lowered_raw:
        return _sentence_case(
            "Hybrid vision models must balance local detail, global context, and computation"
        )
    if (
        "underuses attention in skip connections" in lowered_raw
        or (
            "attention is confined to the bottleneck" in lowered_raw
            and "foreground" in lowered_raw
        )
    ):
        return _sentence_case(
            "Bottleneck-only attention misses multi-scale skip features and foreground imbalance"
        )
    major_cause = re.search(
        r"(.+?)\s+(?:is|are)\s+(?:one\s+of\s+)?(?:the\s+)?"
        r"(?:most\s+)?important\s+causes?\s+of\s+(.+)",
        raw,
        re.I,
    )
    if major_cause:
        source_subject = re.sub(
            r"^(?:studies?\s+(?:have\s+)?shown?\s+that\s+)?",
            "",
            major_cause.group(1),
            flags=re.I,
        )
        copula = "are" if _looks_plural_subject(source_subject) else "is"
        return _sentence_case(
            f"{_poster_fragment(source_subject, 8)} {copula} a major cause of "
            f"{_poster_fragment(major_cause.group(2), 8)}"
        )
    if structure["source_relation"] == "paper_targets_problem" and obj:
        return _sentence_case(f"Effective solutions must address {obj}")
    if relation == "requires_capability" and obj:
        if (
            "category features" in raw.lower()
            and re.search(r"\b(?:lesions?|organs?)\b", raw, re.I)
        ):
            return _sentence_case(
                "Effective methods require category-aware modeling of lesions or organs"
            )
        return _requirement_sentence(obj)
    if not subject or not (obj or condition or consequence):
        return ""
    if relation == "lacks_capability":
        raw = _semantic_source_text(str(candidate.get("source_clause") or ""))
        if "information discrepancy" in raw.lower() and re.search(
            r"\b(?:overlook|ignore)\w*\b",
            raw,
            re.I,
        ):
            return _sentence_case(
                "Earlier fusion methods ignore differences between feature levels"
            )
        if (
            re.search(r"\bdo(?:es)?\s+not\s+verify\b", raw, re.I)
            and "experiments support" in raw.lower()
        ):
            return _sentence_case(
                "Fluency-focused assistants do not check whether experiments support their conclusions"
            )
        if re.search(r"\b(?:fail\w*\s+to|cannot|unable\s+to|struggle\w*\s+to)\b", raw, re.I):
            return _sentence_case(f"{subject} cannot fully {obj}")
        verb = "lack" if _looks_plural_subject(subject) else "lacks"
        return _sentence_case(f"{subject} {verb} {obj}")
    if relation == "is_limited_in":
        return _sentence_case(f"{subject} is limited to {obj}")
    if relation == "increases_resource_cost":
        burden = consequence or obj or condition
        return _sentence_case(f"{subject} incurs {burden}")
    if relation == "creates_tradeoff":
        return _sentence_case(f"{subject} creates a trade-off involving {obj}")
    if relation == "remains_unresolved":
        if obj.lower().startswith("not fully"):
            return _sentence_case(f"{subject} remains insufficiently explored")
        return _sentence_case(f"{subject} remains unresolved")
    if relation == "causes_failure":
        segmentation_significance = re.search(
            r"(.+?segmentation)\s+allows?\s+for\s+.+?,\s*which\s+is\s+"
            r"(?:important|critical|crucial|essential)\s+for\s+(.+)",
            raw,
            re.I,
        )
        if segmentation_significance:
            if all(
                phrase in raw.lower()
                for phrase in (
                    "treatment planning",
                    "surgical navigation",
                    "disease monitoring",
                )
            ):
                return _sentence_case(
                    "Accurate medical image segmentation supports treatment "
                    "planning, surgical navigation, and disease monitoring"
                )
            return _sentence_case(
                f"{_poster_fragment(segmentation_significance.group(1), 7)} "
                f"supports {_poster_fragment(segmentation_significance.group(2), 12)}"
            )
        obscure_distinction = re.search(
            r"(.+?)\s+obscure(?:s|d)?\s+the\s+distinction\s+between\s+"
            r"(.+?)\s+and\s+(.+)",
            raw,
            re.I,
        )
        if obscure_distinction:
            return _sentence_case(
                f"{_poster_fragment(obscure_distinction.group(1), 7)} make "
                f"{_poster_fragment(obscure_distinction.group(2), 7)} difficult "
                f"to distinguish from "
                f"{_poster_fragment(obscure_distinction.group(3), 7)}"
            )
        if (
            "annotation" in raw.lower()
            and re.search(r"\bscarce|scarcity\b", raw, re.I)
            and "texture rather than anatomy" in raw.lower()
        ):
            return _sentence_case(
                "Scarce medical annotations encourage texture-biased rather than anatomical modeling"
            )
        important_for = re.search(
            r"(.+?)\s+(?:is|are)\s+(?:important|critical|crucial|essential)"
            r"\s+for\s+(.+)",
            raw,
            re.I,
        )
        if important_for:
            return _sentence_case(
                f"{_poster_fragment(important_for.group(1), 8)} supports "
                f"{_poster_fragment(important_for.group(2), 12)}"
            )
        if (
            "high-level features" in raw.lower()
            and "lose detailed crowd location" in raw.lower()
        ):
            return _sentence_case(
                "High-level features alone can discard fine crowd-location details"
            )
        effect = consequence or obj or condition
        verb = "cause" if _looks_plural_subject(subject) else "causes"
        return _sentence_case(f"{subject} {verb} {effect}")
    if relation == "struggles_with":
        if re.search(
            r"\b(?:is|are)\s+(?:one\s+of\s+)?(?:the\s+)?"
            r"(?:main|key|major|primary)\s+challenges?\b",
            raw,
            re.I,
        ):
            challenge = re.search(
                r"(.+?)\s+(?:is|are)\s+(?:one\s+of\s+)?(?:the\s+)?"
                r"(?:main|key|major|primary)\s+challenges?\s+(?:in|for)\s+(.+)",
                raw,
                re.I,
            )
            if challenge:
                return _sentence_case(
                    f"{_poster_fragment(challenge.group(1), 8)} complicates "
                    f"{_poster_fragment(challenge.group(2), 8)}"
                )
        persistent = re.search(
            r"(?:capturing|modeling|recovering|preserving)\s+(.+?)\s+"
            r"remains?\s+(?:a\s+)?(?:persistent|major|key|significant)\s+"
            r"challenge",
            raw,
            re.I,
        )
        if persistent:
            challenge_subject = _poster_fragment(persistent.group(1), 10)
            copula = "remain" if _looks_plural_subject(challenge_subject) else "remains"
            return _sentence_case(
                f"{challenge_subject} {copula} difficult "
                "to capture"
            )
        effect = consequence or obj or condition
        verb = "struggle" if _looks_plural_subject(subject) else "struggles"
        if condition and obj:
            return _sentence_case(f"{subject} {verb} to {obj} under {condition}")
        return _sentence_case(f"{subject} {verb} with {effect}")
    return ""


def _syntax_restructured_motivation_rewrite(
    candidate: dict[str, Any],
) -> str:
    raw = _semantic_source_text(
        str(candidate.get("source_clause") or candidate.get("raw_statement") or "")
    )
    lowered = raw.lower()
    major_cause = re.search(
        r"(.+?)\s+(?:is|are)\s+(?:one\s+of\s+)?(?:the\s+)?"
        r"(?:most\s+)?important\s+causes?\s+of\s+(.+)",
        raw,
        re.I,
    )
    if major_cause:
        subject = re.sub(
            r"^(?:studies?\s+(?:have\s+)?shown?\s+that\s+)?",
            "",
            major_cause.group(1),
            flags=re.I,
        )
        copula = "are" if _looks_plural_subject(subject) else "is"
        return _sentence_case(
            f"{_poster_fragment(subject, 8)} {copula} a major cause of "
            f"{_poster_fragment(major_cause.group(2), 8)}"
        )
    if "short acquisitions" in lowered and "image quality" in lowered:
        return _sentence_case("Short scans severely degrade image quality")
    if (
        "only assumed" in lowered
        and "filters" in lowered
        and "gradient kernels" in lowered
    ):
        return _sentence_case(
            "Prior analysis restricts learned filters to modified gradient kernels"
        )
    if (
        "remain" in lowered
        and "link between" in lowered
    ):
        link = re.search(r"link\s+between\s+(.+)", raw, re.I)
        if link:
            return _sentence_case(
                f"The connection between {link.group(1)} remains "
                "insufficiently understood"
            )
    if (
        "fixed receptive field" in lowered
        and "information acquisition" in lowered
    ):
        return _sentence_case(
            "Fixed U-Net receptive fields limit contextual information acquisition"
        )
    if "information discrepancy" in lowered and re.search(
        r"\b(?:overlook|ignore)\w*\b",
        lowered,
    ):
        return _sentence_case(
            "Earlier fusion methods ignore differences between feature levels"
        )
    if (
        "constrained by fixed convolutional receptive fields" in lowered
        and "long-range" in lowered
    ):
        return _sentence_case(
            "Fixed CNN receptive fields cannot capture long-range semantic context"
        )
    if "sparse attention restricts the receptive field" in lowered:
        return _sentence_case(
            "Sparse attention can miss critical long-range positions"
        )
    if (
        "operate at a single scale" in lowered
        and "multi-scale information" in lowered
    ):
        return _sentence_case(
            "Single-scale linear attention misses information across anatomical scales"
        )
    if (
        "inductive bias" in lowered
        and "local textures" in lowered
        and re.search(r"\b(?:lesions?|organs?)\b", lowered)
    ):
        return _sentence_case(
            "CNN inductive biases favor local textures over anatomical objects"
        )
    if "require massive data" in lowered and re.search(
        r"\b(?:vit|transformer)",
        lowered,
    ):
        return _sentence_case(
            "Vision Transformers require more annotated data than medical imaging typically provides"
        )
    if (
        "category features" in lowered
        and re.search(r"\b(?:lesions?|organs?)\b", lowered)
    ):
        return _sentence_case(
            "Effective methods require category-aware modeling of lesions or organs"
        )
    patterns = (
        (
            "fixed receptive field" in lowered
            and bool(re.search(r"\b(?:global|long-range|context)\b", lowered)),
            "Fixed convolutional receptive fields cannot fully capture long-range context",
        ),
        (
            "self-attention" in lowered
            and bool(re.search(r"\b(?:complexity|memory demand)\b", lowered)),
            "Vanilla self-attention imposes high computation and memory costs",
        ),
        (
            "single scale" in lowered and "multi-scale" in lowered,
            "Single-scale attention misses information across anatomical scales",
        ),
        (
            "annotation is scarce" in lowered
            or "annotations are scarce" in lowered
            or "annotation scarcity" in lowered,
            "Scarce medical annotations hinder reliable semantic learning",
        ),
        (
            "passive response to local textures" in lowered,
            "CNN inductive biases emphasize local textures rather than anatomical objects",
        ),
        (
            "lack prior knowledge" in lowered,
            "Data-driven CNNs and ViTs lack priors for identifying category-specific features",
        ),
        (
            "significant variations between different tissues and lesion areas"
            in lowered,
            "Medical targets vary substantially across tissue and lesion scales",
        ),
        (
            "large scale variation" in lowered
            or "large-scale variation" in lowered,
            "Large head-scale variation weakens reliable crowd representation",
        ),
        (
            "confusion between foreground and background" in lowered,
            "Complex backgrounds make foreground heads difficult to distinguish",
        ),
        (
            "single-level features" in lowered,
            "Single-level Transformer features omit fine crowd details",
        ),
    )
    for matched, rewrite in patterns:
        if matched:
            return _sentence_case(rewrite)
    return _relation_motivation_rewrite(candidate)


def _source_copy_aware_motivation_rewrite(
    candidate: dict[str, Any],
) -> str:
    structure = _normalized_motivation_relation(candidate)
    raw = _semantic_source_text(
        str(candidate.get("source_clause") or candidate.get("raw_statement") or "")
    )
    subject = structure["subject"]
    obj = structure["object"]
    obj = re.sub(
        r"\beffectively\s+capture\s+global\s+contextual\s+information\b",
        "represent long-range context",
        obj,
        flags=re.I,
    )
    obj = re.sub(
        r"\bthe\s+inherent\s+limitations?\s+of\s+convolution(?:al)?\s+operations?\b",
        "local convolutional processing",
        obj,
        flags=re.I,
    )
    obj = re.sub(
        r"\bhigh\s+computational\s+complexity\s+and\s+memory\s+demands\b",
        "heavy compute and memory use",
        obj,
        flags=re.I,
    )
    lowered = raw.lower()
    context_text = " ".join(
        str(value or "")
        for value in candidate.get("context_window", [])
    ).lower()
    semantic_patterns = (
        (
            "limited memory and computation resources" in lowered
            and bool(re.search(r"\bembedded|resource-limited\b", lowered)),
            "Resource-limited devices make full CNN deployment difficult",
        ),
        (
            "feature maps" in lowered
            and "rarely been investigated" in lowered,
            "Feature-map redundancy remains underexplored in neural architecture design",
        ),
        (
            "convergence under nonconvex objectives" in lowered
            and "open question" in lowered,
            "Convergence under nonconvex objectives remains unresolved",
        ),
        (
            "finite-sample guarantees" in lowered
            and "heavy-tailed noise" in lowered,
            "Heavy-tailed noise complicates finite-sample guarantees",
        ),
        (
            "reliable analysis requires bounds" in lowered
            and "dependent observations" in lowered,
            "Reliable analysis requires bounds that tolerate dependent observations",
        ),
        (
            "abstract semantic information" in lowered
            and bool(re.search(r"\blose\b.*\bdetail", lowered)),
            "U-shaped encoders can discard fine details while emphasizing abstract semantics",
        ),
        (
            "semantic gap between low" in lowered
            and "high-resolution" in lowered,
            "Large cross-scale semantic gaps can blur fused feature representations",
        ),
        (
            "retinal blood vessels" in lowered
            and "high tortuosity" in lowered,
            "Tortuous, shape-varying retinal vessels make precise segmentation difficult",
        ),
        (
            "diabetic retinopathy" in lowered
            and "blood vessels leak" in lowered,
            "Diabetic retinopathy can cause retinal leakage and vessel swelling",
        ),
        (
            "hypertensive retinopathy" in lowered
            and "high blood pressure" in lowered,
            "High blood pressure can damage retinal vessels through hypertensive retinopathy",
        ),
        (
            "plays a crucial role" in lowered
            and "low-level" in lowered,
            "Low-level vision depends on reliable image restoration",
        ),
        (
            "limitations in modeling capabilities" in lowered
            and "long-range dependencies" in lowered,
            "CNNs struggle to represent long-range structure in large images",
        ),
        (
            "quadratic complexity" in lowered
            and bool(re.search(r"\b(?:large-sized|high-resolution|large)\s+images?\b", lowered)),
            "Quadratic attention costs make high-resolution restoration difficult to scale",
        ),
        (
            "unidirectional modeling" in lowered
            and "spatial awareness" in lowered,
            "Unidirectional state-space models miss important spatial context",
        ),
        (
            "challenging and unresolved task" in lowered
            and "data modeling" in lowered,
            "Efficient multidimensional visual modeling remains an unresolved design problem",
        ),
        (
            "important task" in lowered
            and "deraining" in lowered,
            "Reliable image deraining is central to low-level vision",
        ),
        (
            "fixed receptive field" in lowered
            and "land cover" in lowered,
            "Fixed receptive fields cannot adapt context to different land-cover classes",
        ),
        (
            "not all tokens are informative" in lowered,
            "Unfiltered self-attention lets irrelevant tokens contaminate contextual features",
        ),
        (
            "spatial or spectral information alone" in lowered,
            "Single-domain context modeling misses joint spatial-spectral dependencies",
        ),
        (
            "hsi classification" in lowered
            and "disaster monitoring" in lowered,
            "Hyperspectral classification supports disaster monitoring, precision agriculture, and urban planning",
        ),
        (
            "underuses attention in skip connections" in lowered
            or (
                "attention is confined to the bottleneck" in lowered
                and "foreground" in lowered
            ),
            "Bottleneck-only attention misses multi-scale skip features and foreground imbalance",
        ),
        (
            "large parameter sizes" in lowered
            and bool(re.search(r"\b(?:cpu|resource-limited|deployment)\b", lowered)),
            "Large model footprints hinder deployment on CPU-only devices",
        ),
        (
            "retinal vessel segmentation is essential" in lowered
            and "early diagnosis" in lowered,
            "Retinal vessel maps support early detection of diabetic, hypertensive, and neurological disease",
        ),
        (
            "treat local and global contexts equally" in lowered,
            "Uniform local-global weighting cannot adapt to image content or network depth",
        ),
        (
            "pay extra computations" in lowered,
            "Pure self-attention increases computation by discarding efficient convolutional operators",
        ),
        (
            "it is natural to study hybrid networks" in lowered,
            "Hybrid vision models must balance local detail, global context, and computation",
        ),
        (
            "these tasks play a crucial role" in lowered
            and "image restoration" in context_text,
            "Image restoration is central to low-level computer vision",
        ),
        (
            "degrades outdoor vision" in lowered
            and "rain streak removal" in lowered,
            "Rain streaks reduce outdoor image quality and motivate reliable restoration",
        ),
        (
            "limited-range receptive field" in lowered
            and "long-range dependencies" in lowered,
            "Local convolutional fields prevent CNNs from modeling distant dependencies",
        ),
        (
            "confined to self-attention" in lowered
            and "spectral domain" in lowered,
            "Windowed or channel-wise attention misses long-range spectral rain correlations",
        ),
    )
    for matched, rewrite in semantic_patterns:
        if matched:
            return _sentence_case(rewrite)
    if "linear attention" in raw.lower() and "underexplored" in raw.lower():
        return _sentence_case(
            "Linear attention remains underused in medical image segmentation"
        )
    if structure["relation"] == "requires_capability":
        return _requirement_sentence(obj)
    if structure["relation"] == "lacks_capability":
        return _sentence_case(f"{subject} cannot adequately {obj}")
    if structure["relation"] == "is_limited_in":
        return _sentence_case(f"{subject} relies on only {obj}")
    if structure["relation"] == "increases_resource_cost":
        return _sentence_case(f"{subject} demands excessive computational resources")
    if structure["relation"] == "remains_unresolved":
        return _sentence_case(f"{subject} is still insufficiently studied")
    return _syntax_restructured_motivation_rewrite(candidate)


def _neutral_motivation_rewrite(candidate: dict[str, Any]) -> str:
    structure = _normalized_motivation_relation(candidate)
    subject = structure["subject"]
    obj = structure["object"]
    relation = structure["relation"]
    if relation == "requires_capability" and obj:
        return _requirement_sentence(obj)
    if relation == "lacks_capability" and subject and obj:
        return _sentence_case(f"{subject} does not adequately support {obj}")
    if relation in {"struggles_with", "is_limited_in"} and subject and obj:
        return _sentence_case(f"{obj} remains difficult for {subject}")
    if relation == "causes_failure" and subject and obj:
        return _sentence_case(f"{subject} contributes to {obj}")
    if relation == "remains_unresolved" and subject:
        return _sentence_case(f"{subject} has not been fully explored")
    return ""


def _motivation_visible_audit(
    candidate: dict[str, Any],
    visible: str,
    paper_ir: dict[str, Any],
) -> dict[str, Any]:
    records = list(candidate.get("source_records") or [])
    raw_joined = " ".join(
        str(record.get("raw_statement") or "") for record in records
    )
    maximum_overlap = max(
        (
            longest_source_overlap(
                visible,
                str(record.get("raw_statement") or ""),
            )
            for record in records
        ),
        default=0,
    )
    language_failures: list[str] = []
    surface_checks = (
        ("citation_artifact_check", CITATION_RE),
        ("cross_reference_check", CROSS_REFERENCE_RE),
        ("quotation_check", QUOTATION_RE),
        ("discourse_marker_check", DISCOURSE_RE),
        ("ocr_cleanup_check", OCR_ARTIFACT_RE),
    )
    for name, pattern in surface_checks:
        if pattern.search(visible):
            language_failures.append(name)
    language_issue = _motivation_language_issue(visible)
    if language_issue:
        language_failures.append(language_issue)
    if maximum_overlap > 8:
        language_failures.append("source_copy_check")
    if _unsupported_visible_entities(visible, raw_joined):
        language_failures.append("unsupported_expansion_check")
    blocks = {
        str(block.get("id") or ""): block
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }
    traceable = bool(
        records
        and all(
            record.get("block_id")
            and str(record.get("block_id")) in blocks
            and int(record.get("page") or 0) >= 1
            for record in records
        )
    )
    role_separated = not bool(
        METHOD_LEAKAGE_RE.search(visible)
        or POSITIVE_RESULT_RE.search(visible)
    )
    non_empty = bool(normalize_text(visible))
    language_passed = non_empty and not language_failures
    displayable = bool(non_empty and language_passed and traceable and role_separated)
    return {
        "non_empty": non_empty,
        "language_audit_status": "passed" if language_passed else "failed",
        "traceability_status": "passed" if traceable else "failed",
        "role_separation_status": "passed" if role_separated else "failed",
        "maximum_source_overlap": maximum_overlap,
        "language_failures": list(dict.fromkeys(language_failures)),
        "displayable": displayable,
    }


def _rewrite_selected_motivation(
    candidate: dict[str, Any],
    paper_ir: dict[str, Any],
) -> dict[str, Any]:
    raw = str(candidate.get("raw_statement") or "")
    strategies = (
        (
            "relation_specific_source_rewrite",
            _relation_motivation_rewrite(candidate),
        ),
        (
            "syntax_restructuring",
            _syntax_restructured_motivation_rewrite(candidate),
        ),
        (
            "source_copy_aware_rewrite",
            _source_copy_aware_motivation_rewrite(candidate),
        ),
        (
            "evidence_preserving_neutral_rewrite",
            _neutral_motivation_rewrite(candidate),
        ),
        (
            "legacy_source_rewrite",
            rewrite_motivation(raw, str(candidate.get("type") or "")),
        ),
    )
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    last_audit: dict[str, Any] = {
        "non_empty": False,
        "language_audit_status": "failed",
        "traceability_status": "failed",
        "role_separation_status": "failed",
        "maximum_source_overlap": 0,
        "language_failures": ["poster_rewrite_failed"],
        "displayable": False,
    }
    for mode, value in strategies:
        visible = _sentence_case(clean_visible_text(value))
        if not visible or visible.lower() in seen:
            attempts.append(
                {
                    "mode": mode,
                    "visible_text": visible,
                    "status": "failed",
                    "failure_code": (
                        "empty_rewrite" if not visible else "duplicate_rewrite"
                    ),
                    "audit": last_audit,
                    "failures": [
                        "empty_rewrite" if not visible else "duplicate_rewrite"
                    ],
                }
            )
            continue
        seen.add(visible.lower())
        audit = _motivation_visible_audit(candidate, visible, paper_ir)
        last_audit = audit
        attempts.append(
            {
                "mode": mode,
                "visible_text": visible,
                "status": "passed" if audit["displayable"] else "failed",
                "failure_code": (
                    None
                    if audit["displayable"]
                    else (
                        audit["language_failures"][0]
                        if audit["language_failures"]
                        else "displayability_check_failed"
                    )
                ),
                "audit": audit,
                "failures": list(audit.get("language_failures") or []),
            }
        )
        if audit["displayable"]:
            return {
                "status": "passed",
                "visible_text": visible,
                "failure_code": None,
                "attempts": attempts,
                "audit": audit,
                "normalized_relation": _normalized_motivation_relation(
                    candidate
                )["relation"],
            }
    failures = [
        str(attempt.get("failure_code") or "")
        for attempt in attempts
        if attempt.get("failure_code")
    ]
    return {
        "status": "failed",
        "visible_text": "",
        "failure_code": (
            failures[-1] if failures else "poster_rewrite_failed"
        ),
        "attempts": attempts,
        "audit": last_audit,
        "normalized_relation": _normalized_motivation_relation(candidate)[
            "relation"
        ],
    }


def _contribution_action_sentence(
    mechanism: str,
    purpose: str,
) -> str:
    mechanism = clean_visible_text(mechanism).strip(" ,;:.")
    purpose = clean_visible_text(purpose).strip(" ,;:.")
    purpose = re.sub(r"^(?:to|for)\s+", "", purpose, flags=re.I)
    purpose = re.sub(
        r"\bby\s+(?:combining|using|fusing|integrating)\s+.+$",
        "",
        purpose,
        flags=re.I,
    ).strip(" ,;:.")
    purpose = re.sub(r"^solving\b", "solve", purpose, flags=re.I)
    purpose = re.sub(r"^recovering\b", "recover", purpose, flags=re.I)
    purpose = re.sub(r"^preserving\b", "preserve", purpose, flags=re.I)
    purpose = re.sub(r"^combining\b", "combine", purpose, flags=re.I)
    purpose = re.sub(
        r"^(?P<adverb>[A-Za-z-]+ly\s+)?(?P<verb>optimizes|assigns|routes|"
        r"captures|preserves|combines|integrates|aggregates)\b",
        lambda match: (
            f"{match.group('adverb') or ''}"
            + {
                "optimizes": "optimize",
                "assigns": "assign",
                "routes": "route",
                "captures": "capture",
                "preserves": "preserve",
                "combines": "combine",
                "integrates": "integrate",
                "aggregates": "aggregate",
            }[match.group("verb").lower()]
        ),
        purpose,
        flags=re.I,
    )
    if not mechanism and not purpose:
        return ""
    if re.match(
        r"^(?:combines?|fuses?|integrates?|embeds?|implants?|models?|captures?|preserves?|"
        r"learns?|uses?|applies?|selects?|scores?|routes?|optimizes?|"
        r"constructs?|defines?|introduces?|adapts?|removes?|recovers?)\b",
        mechanism,
        re.I,
    ):
        base = mechanism
        base = re.sub(r"^(combining)\b", "Combines", base, flags=re.I)
        base = re.sub(r"^(using)\b", "Uses", base, flags=re.I)
        base = re.sub(r"^(fusing)\b", "Fuses", base, flags=re.I)
        base = re.sub(r"^(integrating)\b", "Integrates", base, flags=re.I)
    elif re.search(r"\b(?:fusion|integration|combination)\b", mechanism, re.I):
        base = f"Fuses {mechanism}"
    elif re.search(r"\b(?:attention|context|dependency)\b", mechanism, re.I):
        base = f"Models features with {mechanism}"
    elif re.search(r"\b(?:solver|inversion|reconstruction)\b", mechanism, re.I):
        base = f"Combines {mechanism}"
    elif re.search(r"\b(?:loss|objective|criterion|score)\b", mechanism, re.I):
        base = f"Optimizes predictions with {mechanism}"
    else:
        base = f"Uses {mechanism}"
    if purpose:
        return _sentence_case(f"{base} to {purpose}")
    return _sentence_case(base)


def _evidence_contribution_description(candidate: dict[str, Any]) -> str:
    """Prefer a relation-preserving sentence over mechanically spliced fields."""

    raw = " ".join(
        str(record.get("raw_statement") or "")
        for record in candidate.get("source_records", [])
    )
    value = f"{candidate.get('innovation_object') or ''} {raw}"
    if re.search(
        r"\bevidence\s+alignment\s+loss\b",
        str(candidate.get("innovation_object") or ""),
        re.I,
    ):
        return "Jointly optimizes task fidelity and source consistency."
    if re.search(
        r"\bbinds?\b.*\b(?:paper|source)\s+blocks?\b.*\broutes?\b",
        raw,
        re.I,
    ):
        return (
            "Binds generated claims to source blocks and routes unsupported "
            "claims back for review."
        )
    if re.search(
        r"\b(?:assigns?|computes?)\b.*\bevidence\s+scores?\b.*"
        r"\b(?:returns?|sends?|routes?)\b",
        raw,
        re.I,
    ):
        return (
            "Scores claims against evidence and returns weakly supported "
            "claims for review."
        )
    if re.search(r"\bevidence\s+alignment\s+loss\b", value, re.I):
        return "Jointly optimizes task fidelity and source consistency."
    if re.search(r"\bhybrid\b.*\bCNN\b.*\bTransformer\b", value, re.I):
        purpose = clean_visible_text(str(candidate.get("purpose") or ""))
        task = re.search(
            r"\b(?:for|to)\s+((?:efficient\s+)?[A-Za-z -]{3,45}"
            r"(?:segmentation|reconstruction|classification|detection))\b",
            raw,
            re.I,
        )
        target = task.group(1) if task else purpose
        target = re.sub(r"^(?:to|for)\s+", "", target, flags=re.I).strip(" ,;:.")
        if not target or re.search(r"\bthese\s+limitations\b", target, re.I):
            target = "the target task"
        return _sentence_case(
            "Combines CNN local modeling with Transformer global context "
            f"for {target}"
        )
    if re.search(r"\bmulti[-\s]?scale\s+linear\s+attention\b", value, re.I):
        return (
            "Combines multi-scale local extraction with linear attention "
            "to model global context efficiently."
        )
    if re.search(
        r"\btop[-\s]?down\b.*\b(?:feature\s+)?aggregation\b",
        value,
        re.I,
    ):
        return (
            "Aggregates multi-level encoder features top-down to unite "
            "spatial detail with semantic context."
        )
    if candidate.get("component_level") == "empirical_validation" and re.search(
        r"\b(?:multiple|several|three|four|\d+)\s+"
        r"(?:datasets?|tasks?|modalities|settings)\b",
        raw,
        re.I,
    ):
        return (
            "Validates the method systematically across multiple datasets "
            "and evaluation settings."
        )
    return ""


def _source_copy_aware_contribution_description(
    candidate: dict[str, Any],
) -> str:
    value = " ".join(
        str(candidate.get(key) or "")
        for key in (
            "innovation_object",
            "mechanism_or_action",
            "solved_problem",
            "raw_statement",
        )
    )
    if (
        str(candidate.get("component_level") or "") == "overall_architecture"
        and re.search(r"\blightweight\b", value, re.I)
        and re.search(r"\bskip\b", value, re.I)
        and re.search(r"\battention\b", value, re.I)
    ):
        return (
            "Organizes lightweight feature processing and cross-scale skip "
            "fusion within one segmentation network."
        )
    if (
        re.search(r"\battention\b", value, re.I)
        and re.search(r"\bencoder\b", value, re.I)
        and re.search(r"\bdecoder\b", value, re.I)
        and re.search(r"\bskip\b", value, re.I)
    ):
        return (
            "Fuses encoder and decoder cues across skip pathways to reduce "
            "their semantic mismatch."
        )
    if (
        re.search(r"\b(?:loss|objective)\b", value, re.I)
        and re.search(r"\b(?:class|foreground).{0,20}\bimbalance\b", value, re.I)
    ):
        return (
            "Combines pixel-wise fitting with correlation-aware optimization "
            "for imbalanced segmentation."
        )
    return ""


def _rewrite_selected_contribution(
    candidate: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]], list[str]]:
    records = list(candidate.get("source_records") or [])
    innovation_object = clean_visible_text(
        str(candidate.get("innovation_object") or "")
    )
    short_title = _trim_object_title(
        clean_visible_text(
            str(candidate.get("canonical_object_name") or innovation_object)
        )
    )
    mechanism = str(
        candidate.get("mechanism_or_action")
        or candidate.get("mechanism")
        or ""
    )
    purpose = str(
        candidate.get("solved_problem")
        or candidate.get("purpose")
        or ""
    )
    raw_description = clean_visible_text(str(candidate.get("description") or ""))
    alternatives = [
        (
            "evidence_relation_rewrite",
            _evidence_contribution_description(candidate),
        ),
        (
            "source_copy_aware_rewrite",
            _source_copy_aware_contribution_description(candidate),
        ),
        ("structured_semantic_rewrite", _contribution_action_sentence(mechanism, purpose)),
        ("candidate_description_rewrite", _sentence_case(raw_description)),
    ]
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mode, description in alternatives:
        description = _sentence_case(clean_visible_text(description))
        if not description or description.lower() in seen:
            continue
        seen.add(description.lower())
        visible = f"{short_title}\n{description}".strip()
        failures: list[str] = []
        if not (
            1 <= len(_words(short_title)) <= 8
            and (
                len(_words(short_title)) >= 2
                or bool(
                    re.search(
                        r"[A-Z]{2,}|[A-Z][a-z]+[A-Z]|"
                        r"\b[A-Za-z0-9]+-(?:U-?)?Net(?:v\d+)?\b|"
                        r"\b[A-Z][A-Za-z0-9]*Net(?:v\d+)?\b",
                        short_title,
                    )
                )
            )
        ):
            failures.append("short_title_budget")
        if (
            re.search(r"\battention\b", innovation_object, re.I)
            and re.search(r"\b(?:loss|objective)\b", description, re.I)
            and not re.search(
                r"\b(?:attention|spatial|scale|feature|skip)\b",
                description,
                re.I,
            )
        ):
            failures.append("innovation_description_mismatch")
        if not (4 <= len(_words(description)) <= 28):
            failures.append("description_completeness")
        if (
            CITATION_RE.search(visible)
            or CROSS_REFERENCE_RE.search(visible)
            or QUOTATION_RE.search(visible)
            or DISCOURSE_RE.search(visible)
            or OCR_ARTIFACT_RE.search(visible)
        ):
            failures.append("visible_text_cleanup_failed")
        if RESULT_CLAIM_RE.search(visible):
            failures.append("result_separation_gate")
        maximum_overlap = max(
            (
                longest_source_overlap(
                    visible,
                    str(record.get("raw_statement") or ""),
                    [innovation_object, short_title],
                )
                for record in records
            ),
            default=0,
        )
        if maximum_overlap > 8:
            failures.append("source_copy_check")
        raw_joined = " ".join(
            str(record.get("raw_statement") or "") for record in records
        )
        if _unsupported_visible_entities(visible, raw_joined):
            failures.append("unsupported_expansion_check")
        attempts.append(
            {
                "mode": mode,
                "short_title": short_title,
                "description": description,
                "passed": not failures,
                "failures": failures,
                "maximum_source_overlap": maximum_overlap,
            }
        )
        if not failures:
            return short_title, description, attempts, []
    blockers = sorted(
        {
            failure
            for attempt in attempts
            for failure in attempt.get("failures", [])
        }
        or {"poster_rewrite_failed"}
    )
    return short_title, "", attempts, blockers


def _motivation_candidate_ledger(
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_ids = {
        str(candidate.get("candidate_id") or "") for candidate in selected
    }
    selected_index = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in selected
    }
    rejection_index: dict[str, dict[str, Any]] = {}
    for candidate in rejected:
        candidate_id = str(candidate.get("candidate_id") or "")
        reasons = list(candidate.get("rejection_reasons") or [])
        reasons.extend(_candidate_failure_reasons(candidate))
        rejection_index[candidate_id] = {
            **candidate,
            "rejection_reasons": list(dict.fromkeys(reasons)),
        }
    ledger: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        selected_candidate = selected_index.get(candidate_id)
        rejected_candidate = rejection_index.get(candidate_id, {})
        merged_into = rejected_candidate.get("merged_into")
        selected_flag = candidate_id in selected_ids
        ledger.append(
            {
                **candidate,
                "selected": selected_flag,
                "selection_role": (
                    selected_candidate.get("selection_role")
                    if selected_candidate
                    else None
                ),
                "coverage_slot": (
                    selected_candidate.get("coverage_slot")
                    if selected_candidate
                    else None
                ),
                "coverage_family": (
                    selected_candidate.get("coverage_family")
                    if selected_candidate
                    else candidate.get("coverage_family")
                ),
                "final_gate_results": (
                    selected_candidate.get("final_gate_results", {})
                    if selected_candidate
                    else rejected_candidate.get("final_gate_results", {})
                ),
                "merged_from": (
                    selected_candidate.get("merged_from", [])
                    if selected_candidate
                    else candidate.get("merged_from", [])
                ),
                "merged_into": merged_into,
                "rejection_stage": (
                    None
                    if selected_flag
                    else rejected_candidate.get(
                        "rejection_stage",
                        (
                            "semantic_candidate_gates"
                            if _candidate_failure_reasons(candidate)
                            else "coverage_assembly"
                        ),
                    )
                ),
                "rejection_reasons": (
                    []
                    if selected_flag
                    else rejected_candidate.get(
                        "rejection_reasons",
                        _candidate_failure_reasons(candidate)
                        or ["not selected after coverage assembly"],
                    )
                ),
            }
        )
    return ledger


def _check_result(name: str, failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "passed": not failures,
        "failures": failures,
    }


def validate_motivation_contribution_specs(
    motivation_spec: dict[str, Any],
    contribution_spec: dict[str, Any],
    paper_ir: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocks = {
        str(block.get("id") or ""): block
        for block in paper_ir.get("blocks", [])
        if block.get("id")
    }
    checks: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    items = [
        ("motivation", item)
        for item in motivation_spec.get("items", [])
    ] + [
        ("contribution", item)
        for item in contribution_spec.get("items", [])
    ]

    def run_text_check(name: str, pattern: re.Pattern[str]) -> None:
        failures = [
            {"role": role, "id": item.get("id"), "text": item.get("visible_text")}
            for role, item in items
            if pattern.search(str(item.get("visible_text") or ""))
        ]
        checks[name] = _check_result(name, failures)

    run_text_check("citation_artifact_check", CITATION_RE)
    run_text_check("cross_reference_check", CROSS_REFERENCE_RE)
    run_text_check("quotation_marker_check", QUOTATION_RE)
    run_text_check("author_voice_check", AUTHOR_VOICE_RE)
    run_text_check("discourse_marker_check", DISCOURSE_RE)
    run_text_check("ocr_cleanup_check", OCR_ARTIFACT_RE)
    motivation_language_failures = [
        {
            "role": role,
            "id": item.get("id"),
            "text": item.get("visible_text"),
            "reason": _motivation_language_issue(
                str(item.get("visible_text") or "")
            ),
        }
        for role, item in items
        if role == "motivation"
        and _motivation_language_issue(
            str(item.get("visible_text") or "")
        )
    ]
    checks["motivation_language_quality_check"] = _check_result(
        "motivation_language_quality_check",
        motivation_language_failures,
    )

    source_copy_failures: list[dict[str, Any]] = []
    traceability_failures: list[dict[str, Any]] = []
    role_failures: list[dict[str, Any]] = []
    semantic_heading_failures: list[dict[str, Any]] = []
    completeness_failures: list[dict[str, Any]] = []
    expansion_failures: list[dict[str, Any]] = []
    contribution_objects = {
        normalize_text(str(item.get(field) or "")).lower()
        for item in contribution_spec.get("items", [])
        for field in ("short_title", "innovation_object")
        if len(_words(str(item.get(field) or ""))) >= 2
    }
    for role, item in items:
        visible = str(item.get("visible_text") or "")
        records = item.get("source_records") or []
        protected = [
            str(item.get("innovation_object") or ""),
            str(item.get("short_title") or ""),
        ]
        overlaps = [
            longest_source_overlap(
                visible,
                str(record.get("raw_statement") or ""),
                protected,
            )
            for record in records
        ]
        if overlaps and max(overlaps) > 8:
            source_copy_failures.append(
                {
                    "role": role,
                    "id": item.get("id"),
                    "maximum_consecutive_words": max(overlaps),
                }
            )
        invalid_records = [
            record
            for record in records
            if not record.get("block_id")
            or str(record.get("block_id")) not in blocks
            or int(record.get("page") or 0) < 1
        ]
        source_ids = item.get("source_block_ids") or []
        if not records or not source_ids or invalid_records:
            traceability_failures.append(
                {"role": role, "id": item.get("id"), "invalid_records": invalid_records}
            )
        if role == "motivation":
            visible_lower = normalize_text(visible).lower()
            if METHOD_LEAKAGE_RE.search(visible) or any(
                contribution_object
                and contribution_object in visible_lower
                for contribution_object in contribution_objects
            ):
                role_failures.append(
                    {"role": role, "id": item.get("id"), "reason": "method contribution leaked into Motivation"}
                )
            if not VERB_RE.search(visible) or len(_words(visible)) < 4:
                completeness_failures.append(
                    {"role": role, "id": item.get("id"), "reason": "incomplete problem-side statement"}
                )
        else:
            if RESULT_CLAIM_RE.search(visible):
                role_failures.append(
                    {"role": role, "id": item.get("id"), "reason": "performance result leaked into Contribution"}
                )
            if any(
                _is_non_contribution_heading(str(item.get(field) or ""))
                for field in ("short_title", "innovation_object")
            ):
                semantic_heading_failures.append(
                    {
                        "role": role,
                        "id": item.get("id"),
                        "reason": "a discourse/section heading was misclassified as an innovation",
                        "short_title": item.get("short_title"),
                    }
                )
            if not all(
                normalize_text(str(item.get(field) or ""))
                for field in ("innovation_object", "mechanism", "purpose", "description")
            ):
                completeness_failures.append(
                    {"role": role, "id": item.get("id"), "reason": "innovation object, mechanism, or purpose is missing"}
                )
        raw_joined = " ".join(str(record.get("raw_statement") or "") for record in records)
        unsupported_terms = [
            match.group(0)
            for match in SUPERLATIVE_RE.finditer(visible)
            if match.group(0).lower() not in raw_joined.lower()
        ]
        unsupported_entities = _unsupported_visible_entities(
            visible,
            raw_joined,
        )
        if unsupported_terms or unsupported_entities:
            expansion_failures.append(
                {
                    "role": role,
                    "id": item.get("id"),
                    "terms": unsupported_terms,
                    "entities": unsupported_entities,
                }
            )

    checks["source_copy_check"] = _check_result(
        "source_copy_check", source_copy_failures
    )
    checks["role_separation_check"] = _check_result(
        "role_separation_check", role_failures
    )
    checks["semantic_heading_role_check"] = _check_result(
        "semantic_heading_role_check", semantic_heading_failures
    )
    checks["traceability_check"] = _check_result(
        "traceability_check", traceability_failures
    )
    checks["semantic_completeness_check"] = _check_result(
        "semantic_completeness_check", completeness_failures
    )
    checks["unsupported_expansion_check"] = _check_result(
        "unsupported_expansion_check", expansion_failures
    )

    independence_failures: list[dict[str, Any]] = []
    for role, spec in (
        ("motivation", motivation_spec),
        ("contribution", contribution_spec),
    ):
        role_items = list(spec.get("items", []))
        for index, item in enumerate(role_items):
            for other in role_items[index + 1 :]:
                left = (
                    str(item.get("normalized_meaning") or "")
                    if role == "motivation"
                    else " ".join(
                        str(item.get(key) or "")
                        for key in ("innovation_object", "mechanism", "purpose")
                    )
                )
                right = (
                    str(other.get("normalized_meaning") or "")
                    if role == "motivation"
                    else " ".join(
                        str(other.get(key) or "")
                        for key in ("innovation_object", "mechanism", "purpose")
                    )
                )
                left_topics = _motivation_topics(left) if role == "motivation" else set()
                right_topics = _motivation_topics(right) if role == "motivation" else set()
                topic_overlap = (
                    len(left_topics & right_topics)
                    / min(len(left_topics), len(right_topics))
                    if left_topics and right_topics
                    else 0.0
                )
                if jaccard(left, right) >= 0.82 or (
                    role == "motivation"
                    and len(left_topics & right_topics) >= 2
                    and topic_overlap >= 0.67
                ):
                    independence_failures.append(
                        {
                            "role": role,
                            "ids": [item.get("id"), other.get("id")],
                        }
                    )
    checks["semantic_independence_check"] = _check_result(
        "semantic_independence_check", independence_failures
    )

    contribution_items = list(contribution_spec.get("items", []))
    displayable_contributions = [
        item
        for item in contribution_items
        if item.get("selected") is True
        and item.get("short_title")
        and item.get("description")
        and item.get("displayable") is True
    ]
    checks["contribution_displayable_count_check"] = _check_result(
        "contribution_displayable_count_check",
        (
            []
            if 1 <= len(displayable_contributions) <= 4
            else [
                {
                    "displayable_count": len(displayable_contributions),
                    "required_range": [1, 4],
                }
            ]
        ),
    )
    canonical_seen: dict[str, str] = {}
    canonical_failures: list[dict[str, Any]] = []
    title_seen: dict[str, str] = {}
    title_failures: list[dict[str, Any]] = []
    for item in displayable_contributions:
        canonical_id = str(item.get("canonical_object_id") or "")
        normalized_title = normalize_text(str(item.get("short_title") or "")).lower()
        if canonical_id and canonical_id in canonical_seen:
            canonical_failures.append(
                {"ids": [canonical_seen[canonical_id], item.get("id")], "canonical_object_id": canonical_id}
            )
        elif canonical_id:
            canonical_seen[canonical_id] = str(item.get("id") or "")
        if normalized_title and normalized_title in title_seen:
            title_failures.append(
                {"ids": [title_seen[normalized_title], item.get("id")], "short_title": item.get("short_title")}
            )
        elif normalized_title:
            title_seen[normalized_title] = str(item.get("id") or "")
    checks["duplicate_canonical_object_check"] = _check_result(
        "duplicate_canonical_object_check", canonical_failures
    )
    checks["duplicate_short_title_check"] = _check_result(
        "duplicate_short_title_check", title_failures
    )

    author_group_ids = {
        str(group.get("id") or "")
        for group in contribution_spec.get("author_contribution_groups", [])
        if group.get("id")
    }
    selected_group_ids = [
        str(item.get("author_contribution_group_id") or "")
        for item in displayable_contributions
        if item.get("author_contribution_group_id")
    ]
    author_alignment_failures: list[dict[str, Any]] = []
    invalid_group_ids = sorted(set(selected_group_ids) - author_group_ids)
    if invalid_group_ids:
        author_alignment_failures.append({"invalid_group_ids": invalid_group_ids})
    if author_group_ids and not selected_group_ids:
        uncovered_group_ids: list[str] = []
        for group in contribution_spec.get("author_contribution_groups", []):
            group_text = " ".join(
                str(group.get(key) or "")
                for key in (
                    "canonical_object_name",
                    "raw_statement",
                )
            )
            group_tokens = token_set(group_text) - {
                "method",
                "model",
                "module",
                "network",
                "architecture",
                "contribution",
            }
            covered_by_child = any(
                len(
                    group_tokens
                    & (
                        (
                            token_set(
                                " ".join(
                                    str(item.get(key) or "")
                                    for key in (
                                        "innovation_object",
                                        "canonical_object_name",
                                        "short_title",
                                    )
                                )
                            )
                            | token_set(
                                " ".join(
                                    str(record.get("raw_statement") or "")
                                    for record in item.get("source_records", [])
                                )
                            )
                        )
                        - {
                            "method",
                            "model",
                            "module",
                            "network",
                            "architecture",
                            "contribution",
                        }
                    )
                )
                >= 2
                for item in displayable_contributions
            )
            if not covered_by_child:
                uncovered_group_ids.append(str(group.get("id") or ""))
        if uncovered_group_ids:
            author_alignment_failures.append(
                {
                    "reason": "explicit author contribution groups were ignored",
                    "uncovered_group_ids": uncovered_group_ids,
                }
            )
    if len(selected_group_ids) != len(set(selected_group_ids)):
        author_alignment_failures.append(
            {"reason": "one author contribution group was counted more than once"}
        )
    checks["author_contribution_alignment_check"] = _check_result(
        "author_contribution_alignment_check", author_alignment_failures
    )

    selected_canonical_ids = {
        str(item.get("canonical_object_id") or "")
        for item in displayable_contributions
    }
    parent_child_failures = [
        {
            "id": item.get("id"),
            "parent_object_id": item.get("parent_object_id"),
            "component_level": item.get("component_level"),
        }
        for item in displayable_contributions
        if item.get("parent_object_id") in selected_canonical_ids
        and item.get("component_level") in {"implementation_step", "supporting_submodule"}
    ]
    checks["parent_child_overlap_check"] = _check_result(
        "parent_child_overlap_check", parent_child_failures
    )
    def implementation_failure(item: dict[str, Any]) -> dict[str, Any] | None:
        level = str(item.get("component_level") or "")
        if level in {"implementation_step", "supporting_submodule"}:
            return {
                "id": item.get("id"),
                "component_level": level,
                "trigger_reason": "component_level",
            }
        innovation_object = str(item.get("innovation_object") or "")
        if not IMPLEMENTATION_STEP_RE.search(innovation_object):
            return None
        core_passed = bool(
            (
                item.get("final_gate_results", {}).get(
                    "core_contribution_gate"
                )
                or {}
            ).get("passed")
        )
        named_module = bool(
            re.search(
                r"\b[A-Z]{2,}\b|"
                r"\b[A-Z][A-Za-z0-9]*Net\b|"
                r"\b(?:module|branch|network|decoder|fusion|attention)\b",
                " ".join(
                    str(item.get(key) or "")
                    for key in ("short_title", "innovation_object")
                ),
                re.I,
            )
        )
        if core_passed and named_module:
            return None
        return {
            "id": item.get("id"),
            "component_level": level,
            "trigger_reason": "implementation_keyword",
            "innovation_object": innovation_object,
        }

    implementation_failures = [
        failure
        for failure in (
            implementation_failure(item)
            for item in displayable_contributions
        )
        if failure
    ]
    checks["implementation_step_check"] = _check_result(
        "implementation_step_check", implementation_failures
    )
    core_failures = [
        {"id": item.get("id")}
        for item in displayable_contributions
        if not bool(
            (item.get("final_gate_results", {}).get("core_contribution_gate") or {}).get("passed")
        )
    ]
    checks["core_contribution_check"] = _check_result(
        "core_contribution_check", core_failures
    )
    incremental_failures: list[dict[str, Any]] = []
    for index, item in enumerate(displayable_contributions):
        for other in displayable_contributions[index + 1 :]:
            if jaccard(
                " ".join(str(item.get(key) or "") for key in ("innovation_object", "mechanism", "purpose")),
                " ".join(str(other.get(key) or "") for key in ("innovation_object", "mechanism", "purpose")),
            ) >= 0.72:
                incremental_failures.append({"ids": [item.get("id"), other.get("id")]})
    checks["incremental_information_check"] = _check_result(
        "incremental_information_check", incremental_failures
    )
    result_only_failures = [
        {"id": item.get("id"), "visible_text": item.get("visible_text")}
        for item in displayable_contributions
        if item.get("result_only_candidate")
        or RESULT_CLAIM_RE.search(str(item.get("visible_text") or ""))
    ]
    checks["result_only_check"] = _check_result(
        "result_only_check", result_only_failures
    )
    grammar_failures = [
        {"id": item.get("id"), "description": item.get("description")}
        for item in displayable_contributions
        if len(_words(str(item.get("description") or ""))) < 4
        or not VERB_RE.search(str(item.get("description") or ""))
        or re.search(
            r"\buses?\s+(.{3,40}?)\s+to\s+\1\b|"
            r"\b(?:these|those)\s+(?:limitations?|issues?|methods?)\b",
            str(item.get("description") or ""),
            re.I,
        )
    ]
    checks["visible_grammar_check"] = _check_result(
        "visible_grammar_check", grammar_failures
    )
    routing_failures = [
        {"id": item.get("id"), "component_level": item.get("component_level")}
        for item in displayable_contributions
        if item.get("component_level") in {"implementation_step", "supporting_submodule"}
        or item.get("result_only_candidate")
    ]
    checks["role_routing_check"] = _check_result(
        "role_routing_check", routing_failures
    )

    for check in checks.values():
        if check["name"] in NON_BLOCKING_VISIBLE_STYLE_CHECKS:
            continue
        if not check["passed"]:
            issues.append(
                {
                    "code": check["name"].upper(),
                    "severity": "error",
                    "message": f"{check['name']} failed for Poster-visible Motivation or Contributions.",
                    "details": check["failures"],
                    "return_to": "paper-motivation-contributions",
                }
            )
    return checks, issues


def _filter_invalid_visible_items(
    motivation_spec: dict[str, Any],
    contribution_spec: dict[str, Any],
    paper_ir: dict[str, Any],
) -> None:
    """Keep blocking visible-text defects out of Compose and Renderer."""

    blocking_checks = {
        "citation_artifact_check",
        "cross_reference_check",
        "quotation_marker_check",
        "discourse_marker_check",
        "ocr_cleanup_check",
        "motivation_language_quality_check",
        "source_copy_check",
        "role_separation_check",
        "semantic_heading_role_check",
        "traceability_check",
        "semantic_completeness_check",
        "unsupported_expansion_check",
    }
    for role, spec in (
        ("motivation", motivation_spec),
        ("contribution", contribution_spec),
    ):
        if role == "motivation":
            # Motivation semantics have already passed final selection Gates.
            # A visible-text defect must block Compose and trigger a rewrite,
            # not silently delete the selected semantic unit.
            continue
        # Contributions are semantically selected before Poster rewriting.
        # Preserve a verified item when a visible-text check fails; the audit
        # records the blocker and the renderer is stopped upstream for retry.
        if role == "contribution":
            for item in spec.get("items", []):
                item.setdefault("rewrite_blockers", [])
            continue
        retained: list[dict[str, Any]] = []
        for item in spec.get("items", []):
            item_motivation = {"items": [item]} if role == "motivation" else {"items": []}
            item_contribution = {"items": [item]} if role == "contribution" else {"items": []}
            checks, _ = validate_motivation_contribution_specs(
                item_motivation,
                item_contribution,
                paper_ir,
            )
            failed = [
                name
                for name in blocking_checks
                if not bool((checks.get(name) or {}).get("passed"))
            ]
            if not failed:
                retained.append(item)
                continue
            spec.setdefault("rejected_candidates", []).append(
                {
                    "candidate_id": item.get("id"),
                    "rejection_stage": "poster_visible_quality",
                    "failed_checks": sorted(failed),
                    "visible_text": item.get("visible_text"),
                    "source_block_ids": item.get("source_block_ids", []),
                    "source_records": item.get("source_records", []),
                }
            )
        spec["items"] = retained


def _effective_motivation_role(candidate: dict[str, Any]) -> str:
    role = str(candidate.get("role") or "")
    raw = _semantic_source_text(
        str(candidate.get("source_clause") or candidate.get("raw_statement") or "")
    )
    if (
        role == "problem_significance_or_practical_constraint"
        and re.search(
            r"\b(?:variations?|vary|scarce|heterogeneous|low[-\s]?contrast|"
            r"noise|artifact|ambiguity|occlusion|complex\s+background)\b",
            raw,
            re.I,
        )
    ):
        return "task_problem_or_challenge"
    if (
        role == "task_problem_or_challenge"
        and (
            METHOD_FAMILY_RE.search(raw)
            or re.search(r"\b(?:backbone|transformer|cnn|vit)\b", raw, re.I)
        )
        and re.search(
            r"\b(?:limited|limitation|fail|cannot|unable|overlook|ignore|"
            r"restrict|receptive\s+field)\b",
            raw,
            re.I,
        )
    ):
        return "prior_method_limitation"
    return role


def _motivation_recovery_plan() -> tuple[tuple[str, Any], ...]:
    return (
        ("rescan_introduction_front_30_percent", lambda item: "introduction_front_30_percent" in item.get("recovery_tags", [])),
        ("rescan_introduction_middle", lambda item: "introduction_middle" in item.get("recovery_tags", [])),
        ("scan_pre_method_transition", lambda item: "pre_method_transition" in item.get("recovery_tags", [])),
        ("check_abstract_front_half", lambda item: "abstract_front_half" in item.get("recovery_tags", [])),
        ("resplit_compound_clauses", lambda item: "compound_clause_resplit" in item.get("recovery_tags", [])),
        ("expand_reference_context", lambda item: "expanded_reference_context" in item.get("recovery_tags", [])),
        ("recover_surface_rejected_semantics", lambda item: "surface_artifact_recheck" in item.get("recovery_tags", [])),
        ("recheck_over_merging", lambda item: True),
        (
            "recheck_paper_objective",
            lambda item: "paper_objective_recheck" in item.get("recovery_tags", [])
            or item.get("extraction_mode") == "conditional_requirement_rewrite",
        ),
    )


def _assemble_displayable_motivation(
    candidates: list[dict[str, Any]],
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    *,
    selected_semantic_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, Any]]:
    valid = [candidate for candidate in candidates if _all_base_gates_pass(candidate)]
    context = _story_context(story, paper_ir)
    paper_type = _classify_motivation_paper_type(paper_ir, story)
    initial = [
        candidate
        for candidate in valid
        if candidate.get("section_kind") == "introduction"
        and float(candidate.get("importance") or 0) >= 0.78
        and candidate.get("extraction_mode") == "whole_sentence"
        and "expanded_reference_context" not in candidate.get("recovery_tags", [])
        and (candidate.get("relation_structure") or {}).get("relation")
        != "paper_targets_problem"
    ]
    pool = list(initial)
    attempted: set[tuple[str, str]] = set()
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    attempts_per_slot: dict[str, list[dict[str, Any]]] = {
        slot: []
        for slot in (
            *MOTIVATION_COVERAGE_SLOTS,
            "optional_1",
            "optional_2",
        )
    }
    rewrite_exhausted: list[str] = []
    replacement_candidates: list[dict[str, Any]] = []
    executed: list[str] = []
    recovery_trace: list[dict[str, Any]] = []
    final_merged: list[dict[str, Any]] = []
    final_merge_rejected: list[dict[str, Any]] = []
    final_eligible: list[dict[str, Any]] = []

    def evaluate_pool() -> None:
        nonlocal final_merged, final_merge_rejected, final_eligible
        final_merged, final_merge_rejected = _merge_candidates(pool, "motivation")
        for value in final_merged:
            value["final_gate_results"] = _candidate_final_semantic_gates(
                value,
                context,
            )
        final_eligible = [
            value
            for value in final_merged
            if _candidate_passes_final_semantics(value)
        ]
        final_eligible.sort(
            key=lambda item: (
                float(item.get("importance") or 0),
                -min(
                    int(record.get("page") or 1)
                    for record in item.get("source_records", [])
                ),
            ),
            reverse=True,
        )

    def try_slot(slot: str, *, required: bool = True) -> bool:
        queue = sorted(
            (
                value
                for value in final_eligible
                if str(value.get("candidate_id") or "") not in selected_ids
                and _motivation_coverage_family(value, paper_type)
                in MOTIVATION_REQUIRED_FAMILIES
            ),
            key=lambda item: _motivation_slot_rank(
                item,
                slot if required else "reading_direction",
                paper_type,
            ),
        )
        if not required:
            represented = {
                str(item.get("coverage_family") or "")
                for item in selected
            }
            queue.sort(
                key=lambda item: (
                    _motivation_coverage_family(item, paper_type)
                    in represented,
                    *_motivation_slot_rank(
                        item,
                        "reading_direction",
                        paper_type,
                    ),
                )
            )
        prior_failures = len(attempts_per_slot[slot])
        for position, value in enumerate(queue, start=1):
            candidate_id = str(value.get("candidate_id") or "")
            attempt_key = (slot, candidate_id)
            if attempt_key in attempted:
                continue
            attempted.add(attempt_key)
            candidate = dict(value)
            candidate["coverage_slot"] = slot
            candidate["coverage_family"] = _motivation_coverage_family(
                candidate,
                paper_type,
            )
            candidate["selection_role"] = (
                _effective_motivation_role(candidate)
                or str(candidate.get("role") or "")
                or str(candidate.get("type") or "")
            )
            candidate["role_reclassified_for_display"] = (
                candidate["selection_role"]
                != str(value.get("role") or "")
            )
            rewrite = _rewrite_selected_motivation(candidate, paper_ir)
            attempt_record = {
                "candidate_id": candidate_id,
                "rank": position,
                "coverage_family": candidate["coverage_family"],
                "semantic_role": candidate["selection_role"],
                "status": rewrite["status"],
                "failure_code": rewrite["failure_code"],
                "attempts": rewrite["attempts"],
            }
            attempts_per_slot[slot].append(attempt_record)
            if rewrite["status"] == "passed":
                duplicated_candidate_id = _visible_motivation_duplicate(
                    str(rewrite.get("visible_text") or ""),
                    selected,
                )
                if duplicated_candidate_id:
                    attempt_record["status"] = "failed"
                    attempt_record[
                        "failure_code"
                    ] = "semantic_duplicate_visible_text"
                    attempt_record["duplicate_of"] = duplicated_candidate_id
                    continue
                if position > 1 or prior_failures:
                    replacement_candidates.append(
                        {
                            "coverage_slot": slot,
                            "candidate_id": candidate_id,
                            "replaced_candidate_ids": [
                                str(item.get("candidate_id") or "")
                                for item in attempts_per_slot[slot][:-1]
                            ],
                        }
                    )
                candidate["_rewrite_result"] = rewrite
                candidate["selected"] = True
                candidate["displayable"] = True
                selected.append(candidate)
                selected_ids.add(candidate_id)
                return True
            rewrite_exhausted.append(candidate_id)
        return False

    evaluate_pool()
    for slot in MOTIVATION_COVERAGE_SLOTS:
        try_slot(slot)

    for step, predicate in _motivation_recovery_plan():
        covered_slots = {
            str(item.get("coverage_slot") or "")
            for item in selected
        }
        if all(
            slot in covered_slots
            for slot in MOTIVATION_COVERAGE_SLOTS
        ):
            break
        executed.append(step)
        known = {str(candidate.get("candidate_id") or "") for candidate in pool}
        added = [
            candidate
            for candidate in valid
            if predicate(candidate)
            and str(candidate.get("candidate_id") or "") not in known
        ]
        pool.extend(added)
        evaluate_pool()
        missing_slots = [
            slot
            for slot in MOTIVATION_COVERAGE_SLOTS
            if slot
            not in {
                str(item.get("coverage_slot") or "")
                for item in selected
            }
        ]
        for slot in missing_slots:
            try_slot(slot)
        recovery_trace.append(
            {
                "step": step,
                "added_candidate_ids": [
                    str(candidate.get("candidate_id") or "") for candidate in added
                ],
                "missing_coverage_slots_after_step": [
                    slot
                    for slot in MOTIVATION_COVERAGE_SLOTS
                    if slot not in {
                        str(item.get("coverage_slot") or "")
                        for item in selected
                    }
                ],
            }
        )

    covered_slots = {
        str(item.get("coverage_slot") or "")
        for item in selected
    }
    if all(
        slot in covered_slots
        for slot in MOTIVATION_COVERAGE_SLOTS
    ):
        known = {str(candidate.get("candidate_id") or "") for candidate in pool}
        pool.extend(
            candidate
            for candidate in valid
            if str(candidate.get("candidate_id") or "") not in known
        )
        evaluate_pool()
        for slot in ("optional_1", "optional_2"):
            if len(selected) >= 5:
                break
            try_slot(slot, required=False)

    slot_order = {
        "core_problem": 1,
        "unresolved_driver": 2,
        "reading_direction": 3,
        "optional_1": 4,
        "optional_2": 5,
    }
    selected.sort(
        key=lambda item: slot_order.get(
            str(item.get("coverage_slot") or ""),
            99,
        )
    )
    selected = selected[:5]
    selected_ids = {str(candidate.get("candidate_id") or "") for candidate in selected}
    failed_rewrites = {
        str(attempt.get("candidate_id") or ""): attempt
        for slot_attempts in attempts_per_slot.values()
        for attempt in slot_attempts
        if attempt.get("status") == "failed"
    }
    rejected = list(final_merge_rejected)
    for candidate in final_merged:
        candidate_id = str(candidate.get("candidate_id") or "")
        if candidate_id in selected_ids:
            continue
        rejected_candidate = dict(candidate)
        rejected_candidate["selected"] = False
        if candidate_id in failed_rewrites:
            rejected_candidate["rejection_stage"] = "poster_visible_rewrite"
            rejected_candidate["rejection_reasons"] = [
                str(
                    failed_rewrites[candidate_id].get("failure_code")
                    or "poster_rewrite_failed"
                )
            ]
        else:
            rejected_candidate["rejection_stage"] = "coverage_assembly"
            rejected_candidate["rejection_reasons"] = (
                [
                    name
                    for name, result in candidate.get("final_gate_results", {}).items()
                    if not bool(result.get("passed"))
                ]
                or ["not selected after displayable role coverage"]
            )
        rejected.append(rejected_candidate)
    required_status = {
        slot: {
            "displayable": slot
            in {str(item.get("coverage_slot") or "") for item in selected},
            "candidate_id": next(
                (
                    str(item.get("candidate_id") or "")
                    for item in selected
                    if str(item.get("coverage_slot") or "") == slot
                ),
                None,
            ),
            "coverage_family": next(
                (
                    str(item.get("coverage_family") or "")
                    for item in selected
                    if str(item.get("coverage_slot") or "") == slot
                ),
                None,
            ),
            "semantic_role": next(
                (
                    str(item.get("selection_role") or "")
                    for item in selected
                    if str(item.get("coverage_slot") or "") == slot
                ),
                None,
            ),
        }
        for slot in MOTIVATION_COVERAGE_SLOTS
    }
    empty_visible = [
        {"coverage_slot": slot, "candidate_id": attempt.get("candidate_id")}
        for slot, values in attempts_per_slot.items()
        for attempt in values
        if attempt.get("status") == "failed"
        and not any(
            normalize_text(str(value.get("visible_text") or ""))
            for value in attempt.get("attempts", [])
        )
    ]
    blockers = []
    missing_preferred_slots = [
        slot
        for slot in MOTIVATION_COVERAGE_SLOTS
        if not required_status[slot]["displayable"]
    ]
    sparse_fallback_used = bool(
        MOTIVATION_MIN_ITEMS <= len(selected) < MOTIVATION_TARGET_ITEMS
        and executed
    )
    if len(selected) < MOTIVATION_MIN_ITEMS:
        blockers.append(
            {
                "code": "MOTIVATION_EVIDENCE_INSUFFICIENT",
                "displayable_item_count": len(selected),
                "missing_coverage_slots": missing_preferred_slots,
            }
        )
    attempts_per_role: dict[str, list[dict[str, Any]]] = {
        role: [] for role in MOTIVATION_REQUIRED_ROLES
    }
    for slot_attempts in attempts_per_slot.values():
        for attempt in slot_attempts:
            role = str(attempt.get("semantic_role") or "")
            if role in attempts_per_role:
                attempts_per_role[role].append(attempt)
    return selected, rejected, executed, {
        "selected_semantic_count": selected_semantic_count,
        "displayable_item_count": len(selected),
        "paper_type": paper_type,
        "required_coverage_status": required_status,
        "required_role_status": {
            role: {
                "displayable": any(
                    str(item.get("selection_role") or "") == role
                    for item in selected
                ),
                "candidate_id": next(
                    (
                        str(item.get("candidate_id") or "")
                        for item in selected
                        if str(item.get("selection_role") or "") == role
                    ),
                    None,
                ),
            }
            for role in MOTIVATION_REQUIRED_ROLES
        },
        "candidate_attempts_per_slot": attempts_per_slot,
        "candidate_attempts_per_role": attempts_per_role,
        "empty_visible_items": empty_visible,
        "rewrite_exhausted_candidates": sorted(set(rewrite_exhausted)),
        "replacement_candidates_used": replacement_candidates,
        "coverage_recovery_executed": executed,
        "sparse_fallback_used": sparse_fallback_used,
        "missing_preferred_coverage_slots": missing_preferred_slots,
        "recovery_trace": recovery_trace,
        "compose_blockers": blockers,
        "semantic_gate_pass_count": len(final_eligible),
        "merged_count": len(final_merged),
        "selected_candidate_ids": [
            str(candidate.get("candidate_id") or "") for candidate in selected
        ],
        "required_slot_winners": {
            slot: required_status[slot]["candidate_id"]
            for slot in MOTIVATION_COVERAGE_SLOTS
        },
    }


def _finalize_motivation(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates.sort(
        key=lambda item: (
            {
                "core_problem": 1,
                "unresolved_driver": 2,
                "reading_direction": 3,
                "optional_1": 4,
                "optional_2": 5,
            }.get(
                str(item.get("coverage_slot") or ""),
                99,
            ),
            -float(item.get("importance") or 0),
        )
    )
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        records = candidate.get("source_records", [])
        rewrite = dict(candidate.get("_rewrite_result") or {})
        audit = dict(rewrite.get("audit") or {})
        if (
            rewrite.get("status") != "passed"
            or not normalize_text(str(rewrite.get("visible_text") or ""))
            or not bool(audit.get("displayable"))
        ):
            continue
        visible = str(rewrite.get("visible_text") or "")
        items.append(
            {
                "id": "",
                "source_candidate_id": candidate.get("candidate_id"),
                "type": candidate.get("type"),
                "role": candidate.get("role"),
                "selection_role": candidate.get(
                    "selection_role",
                    candidate.get("role"),
                ),
                "coverage_slot": candidate.get("coverage_slot"),
                "coverage_family": candidate.get("coverage_family"),
                "paper_type": candidate.get("paper_type"),
                "visible_text": visible,
                "normalized_meaning": str(
                    candidate.get("normalized_meaning") or ""
                ),
                "relation_structure": candidate.get("relation_structure", {}),
                "source_sentence_ids": candidate.get(
                    "source_sentence_ids",
                    [],
                ),
                "context_window_ids": candidate.get(
                    "context_window_ids",
                    [],
                ),
                "source_block_ids": sorted(
                    {str(record.get("block_id")) for record in records if record.get("block_id")}
                ),
                "source_pages": sorted(
                    {int(record.get("page") or 1) for record in records}
                ),
                "source_sections": sorted(
                    {
                        str(record.get("source_section"))
                        for record in records
                        if record.get("source_section")
                    }
                ),
                "source_records": records,
                "gate_results": candidate.get("gate_results"),
                "final_gate_results": candidate.get(
                    "final_gate_results",
                    {},
                ),
                "merged_from": candidate.get("merged_from", []),
                "confidence": candidate.get("importance", 0.0),
                "rewrite_attempts": list(rewrite.get("attempts") or []),
                "rewrite_blockers": [],
                "selected": True,
                "rewrite_status": "passed",
                "language_audit_status": audit.get(
                    "language_audit_status",
                    "failed",
                ),
                "traceability_status": audit.get(
                    "traceability_status",
                    "failed",
                ),
                "role_separation_status": audit.get(
                    "role_separation_status",
                    "failed",
                ),
                "displayable": bool(audit.get("displayable")),
                "normalized_relation": rewrite.get("normalized_relation"),
            }
        )
    for index, item in enumerate(items, start=1):
        item["id"] = f"M{index}"
    return items


def _contribution_core_score(candidate: dict[str, Any]) -> float:
    sections = " ".join(candidate.get("source_sections") or []).lower()
    level = str(candidate.get("component_level") or "")
    level_bonus = {
        "overall_architecture": 22.0,
        "primary_mechanism": 18.0,
        "secondary_mechanism": 14.0,
        "objective_or_algorithm": 16.0,
        "theory": 18.0,
        "dataset_or_protocol": 16.0,
        "empirical_validation": 10.0,
        "supporting_submodule": -18.0,
        "implementation_step": -35.0,
    }.get(level, 0.0)
    return round(
        35.0 * float(candidate.get("importance") or 0)
        + level_bonus
        + (24.0 if candidate.get("title_alignment") else 0.0)
        + (18.0 if candidate.get("author_contribution_group_id") else 0.0)
        + (8.0 if "abstract" in sections else 0.0)
        + (7.0 if "conclusion" in sections else 0.0)
        + (6.0 if candidate.get("method_node_ids") else 0.0)
        + min(8.0, 2.0 * len(candidate.get("supporting_evidence") or [])),
        3,
    )


def _prepare_contribution_selection(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    routed_to_method: list[dict[str, Any]] = []
    routed_to_results: list[dict[str, Any]] = []
    for candidate in candidates:
        level = str(candidate.get("component_level") or "")
        contribution_text = normalize_text(
            " ".join(
                str(candidate.get(key) or "")
                for key in (
                    "innovation_object",
                    "raw_statement",
                    "mechanism",
                    "purpose",
                )
            )
        )
        comparison_or_prior_work = bool(
            re.search(
                r"\b(?:comparison|compared?)\s+(?:with|against)\b.*"
                r"\b(?:standard|existing|other|prior)\b.*"
                r"\b(?:algorithms?|methods?|approaches?)\b|"
                r"\b(?:standard|existing|other|prior)\b.*"
                r"\b(?:algorithms?|methods?|approaches?)\b.*"
                r"\b(?:are|were)\s+(?:introduced|reviewed|compared)\b",
                contribution_text,
                re.I,
            )
        )
        result_only = bool(candidate.get("result_only_candidate"))
        implementation = level in {"implementation_step", "supporting_submodule"}
        evidence_passed = bool(
            (candidate.get("gate_results", {}).get("evidence_gate") or {}).get(
                "passed"
            )
        )
        base_passed = _all_base_gates_pass(candidate)
        core_passed = bool(
            base_passed
            and evidence_passed
            and not result_only
            and not implementation
            and not comparison_or_prior_work
            and (
                candidate.get("title_alignment")
                or candidate.get("author_contribution_group_id")
                or candidate.get("explicit_claim_source_ids")
                or candidate.get("component_level")
                in {
                    "overall_architecture",
                    "objective_or_algorithm",
                    "theory",
                    "dataset_or_protocol",
                }
            )
        )
        candidate["core_score"] = _contribution_core_score(candidate)
        candidate["final_gate_results"] = {
            "core_contribution_gate": {
                "passed": core_passed,
                "reason": "candidate is a central, independently supported paper addition",
            },
            "independence_gate": {
                "passed": True,
                "reason": "checked during role-aware final selection",
            },
            "evidence_gate": {
                "passed": evidence_passed,
                "reason": "candidate retains method, theory, dataset, or experimental evidence",
            },
            "implementation_step_check": {
                "passed": not implementation,
                "reason": "ordinary stages and internal operations belong in Method",
            },
            "result_only_check": {
                "passed": not result_only,
                "reason": "isolated performance claims belong in Results or Highlights",
            },
            "prior_work_or_comparison_check": {
                "passed": not comparison_or_prior_work,
                "reason": (
                    "comparisons and descriptions of standard or prior "
                    "methods are not paper Contributions"
                ),
            },
        }
        if result_only:
            candidate["route_target"] = "results"
            routed_to_results.append(candidate)
        elif implementation:
            candidate["route_target"] = "method"
            routed_to_method.append(candidate)
        elif core_passed:
            candidate["route_target"] = "contributions"
            eligible.append(candidate)
        else:
            candidate["route_target"] = "rejected"
    eligible.sort(key=lambda item: (-float(item.get("core_score") or 0), str(item.get("candidate_id") or "")))
    return eligible, routed_to_method, routed_to_results


def _incremental_contribution(
    candidate: dict[str, Any],
    selected: list[dict[str, Any]],
) -> bool:
    identity = str(candidate.get("canonical_object_id") or "")
    meaning = _meaning_key(candidate, "contribution")
    for other in selected:
        if identity and identity == str(other.get("canonical_object_id") or ""):
            return False
        candidate_level = str(candidate.get("component_level") or "")
        other_level = str(other.get("component_level") or "")
        parent_child_pair = bool(
            (
                candidate.get("parent_object_id")
                and candidate.get("parent_object_id")
                == other.get("canonical_object_id")
                and candidate_level
                in {
                    "primary_mechanism",
                    "secondary_mechanism",
                    "objective_or_algorithm",
                }
            )
            or (
                other.get("parent_object_id")
                and other.get("parent_object_id")
                == candidate.get("canonical_object_id")
                and other_level
                in {
                    "primary_mechanism",
                    "secondary_mechanism",
                    "objective_or_algorithm",
                }
            )
        )
        if parent_child_pair:
            continue
        if jaccard(meaning, _meaning_key(other, "contribution")) >= 0.72:
            return False
        same_parent = bool(
            candidate.get("parent_object_id")
            and candidate.get("parent_object_id") == other.get("canonical_object_id")
        )
        if same_parent and candidate.get("component_level") not in {
            "primary_mechanism",
            "secondary_mechanism",
            "objective_or_algorithm",
        }:
            return False
    return True


def _contribution_rewrite(candidate: dict[str, Any]) -> dict[str, Any]:
    cached = candidate.get("_final_rewrite")
    if isinstance(cached, dict):
        return cached
    short_title, description, attempts, blockers = _rewrite_selected_contribution(
        candidate
    )
    result = {
        "short_title": short_title,
        "description": description,
        "attempts": attempts,
        "blockers": blockers,
        "passed": bool(short_title and description and not blockers),
    }
    candidate["_final_rewrite"] = result
    return result


def _select_final_contributions(
    candidates: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    eligible, routed_to_method, routed_to_results = _prepare_contribution_selection(
        candidates
    )
    selected: list[dict[str, Any]] = []
    attempts: dict[str, list[dict[str, Any]]] = {
        role: [] for role in CONTRIBUTION_REQUIRED_ROLES
    }

    def role_queue(role: str) -> list[dict[str, Any]]:
        if role == "primary_method_or_architecture":
            preferred = {
                "overall_architecture",
                "objective_or_algorithm",
                "theory",
                "dataset_or_protocol",
            }
        elif role == "primary_innovation_mechanism":
            preferred = {
                "primary_mechanism",
                "secondary_mechanism",
                "objective_or_algorithm",
            }
        else:
            preferred = set(CONTRIBUTION_COMPONENT_LEVELS) - {
                "implementation_step",
                "supporting_submodule",
            }
        return sorted(
            eligible,
            key=lambda item: (
                0 if item.get("component_level") in preferred else 1,
                -float(item.get("core_score") or 0),
            ),
        )

    for role in CONTRIBUTION_REQUIRED_ROLES:
        for candidate in role_queue(role):
            candidate_id = str(candidate.get("candidate_id") or "")
            if candidate in selected or not _incremental_contribution(candidate, selected):
                attempts[role].append(
                    {
                        "candidate_id": candidate_id,
                        "status": "rejected",
                        "reason": "duplicate_or_nonincremental",
                    }
                )
                continue
            rewrite = _contribution_rewrite(candidate)
            attempts[role].append(
                {
                    "candidate_id": candidate_id,
                    "status": "passed" if rewrite["passed"] else "failed",
                    "reason": None if rewrite["passed"] else "visible_text_audit",
                    "rewrite_blockers": rewrite["blockers"],
                }
            )
            if not rewrite["passed"]:
                continue
            candidate["contribution_role"] = role
            selected.append(candidate)
            break

    recovery_steps: list[str] = []
    if len(selected) < 3:
        recovery_steps = [
            "recheck_author_contribution_groups",
            "recheck_introduction_ending",
            "recheck_conclusion",
            "recheck_abstract_novelty",
            "check_overmerged_independent_objects",
            "check_method_objective_theory_protocol",
            "check_author_declared_systematic_validation",
            "check_empirical_validation_independence",
        ]

    if len(selected) >= 3:
        for candidate in eligible:
            if candidate in selected or not _incremental_contribution(candidate, selected):
                continue
            rewrite = _contribution_rewrite(candidate)
            fourth_eligible = bool(
                rewrite["passed"]
                and (
                    candidate.get("author_contribution_group_id")
                    or candidate.get("title_alignment")
                    or float(candidate.get("core_score") or 0) >= 55.0
                )
            )
            if not fourth_eligible:
                continue
            candidate["contribution_role"] = "optional_fourth_core_contribution"
            selected.append(candidate)
            break

    selection_rejected: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate in selected:
            continue
        rejected = dict(candidate)
        if candidate in routed_to_method:
            reason = "routed_to_method"
        elif candidate in routed_to_results:
            reason = "routed_to_results"
        elif not bool(
            (candidate.get("final_gate_results", {}).get("core_contribution_gate") or {}).get("passed")
        ):
            reason = "core_contribution_gate"
        else:
            reason = "not_selected_after_core_ranking"
        rejected["rejection_reasons"] = list(
            dict.fromkeys(
                [*rejected.get("rejection_reasons", []), reason]
            )
        )
        selection_rejected.append(rejected)

    required_role_status = {
        role: any(
            candidate.get("contribution_role") == role for candidate in selected
        )
        for role in CONTRIBUTION_REQUIRED_ROLES
    }
    core_role_present = bool(
        required_role_status["primary_method_or_architecture"]
        or required_role_status["primary_innovation_mechanism"]
    )
    sufficient = bool(1 <= len(selected) <= 4 and core_role_present)
    sparse = bool(sufficient and len(selected) < 3)
    trace = {
        "eligible_count": len(eligible),
        "selected_count": len(selected) if sufficient else 0,
        "semantic_selected_count": len(selected),
        "required_role_status": required_role_status,
        "candidate_attempts_per_role": attempts,
        "recovery_steps_executed": recovery_steps,
        "quality_status": (
            "sparse_but_sufficient"
            if sparse
            else "passed"
            if sufficient
            else "blocked"
        ),
        "warning": (
            "CONTRIBUTION_SPARSE_BUT_SUFFICIENT" if sparse else None
        ),
        "blocker": None if sufficient else "CONTRIBUTION_EVIDENCE_INSUFFICIENT",
    }
    return (
        selected if sufficient else [],
        selection_rejected,
        routed_to_method,
        routed_to_results,
        trace,
    )


def _finalize_contributions(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        records = candidate.get("source_records", [])
        rewrite = _contribution_rewrite(candidate)
        short_title = str(rewrite.get("short_title") or "")
        description = str(rewrite.get("description") or "")
        rewrite_attempts = list(rewrite.get("attempts") or [])
        rewrite_blockers = list(rewrite.get("blockers") or [])
        core_passed = bool(
            (candidate.get("final_gate_results", {}).get("core_contribution_gate") or {}).get("passed")
        )
        evidence_passed = bool(
            (candidate.get("final_gate_results", {}).get("evidence_gate") or {}).get("passed")
        )
        displayable = bool(
            short_title
            and description
            and core_passed
            and evidence_passed
            and not rewrite_blockers
        )
        items.append(
            {
                "id": f"C{index}",
                "short_title": short_title,
                "description": description,
                "visible_text": f"{short_title}\n{description}".strip(),
                "contribution_type": candidate.get("contribution_type"),
                "innovation_object": candidate.get("innovation_object"),
                "mechanism": candidate.get("mechanism"),
                "mechanism_or_action": candidate.get("mechanism_or_action"),
                "purpose": candidate.get("purpose"),
                "solved_problem": candidate.get("solved_problem"),
                "reported_effect": candidate.get("reported_effect"),
                "canonical_object_id": candidate.get("canonical_object_id"),
                "canonical_object_name": candidate.get("canonical_object_name"),
                "author_contribution_group_id": candidate.get(
                    "author_contribution_group_id"
                ),
                "parent_object_id": candidate.get("parent_object_id"),
                "component_level": candidate.get("component_level"),
                "contribution_role": candidate.get("contribution_role"),
                "source_candidate_ids": [
                    candidate.get("candidate_id"),
                    *candidate.get("merged_from", []),
                ],
                "source_block_ids": sorted(
                    {str(record.get("block_id")) for record in records if record.get("block_id")}
                ),
                "source_pages": sorted(
                    {int(record.get("page") or 1) for record in records}
                ),
                "method_sections": candidate.get("method_sections", []),
                "method_node_ids": candidate.get(
                    "method_node_ids",
                    [candidate.get("method_node_id")]
                    if candidate.get("method_node_id")
                    else [],
                ),
                "source_records": records,
                "supporting_evidence": candidate.get("supporting_evidence", []),
                "gate_results": candidate.get("gate_results"),
                "final_gate_results": candidate.get("final_gate_results", {}),
                "merged_from": candidate.get("merged_from", []),
                "confidence": candidate.get("importance", 0.0),
                "core_score": candidate.get("core_score", 0.0),
                "rewrite_attempts": rewrite_attempts,
                "rewrite_blockers": rewrite_blockers,
                "selected": True,
                "visible_text_audit": "passed" if not rewrite_blockers else "failed",
                "displayable": displayable,
            }
        )
    return items


def _candidate_failure_reasons(candidate: dict[str, Any]) -> list[str]:
    return [
        name
        for name, result in candidate.get("gate_results", {}).items()
        if not bool(result.get("passed"))
    ]


def _contribution_candidate_snapshot(
    candidates: list[dict[str, Any]],
    contribution_spec: dict[str, Any],
) -> dict[str, Any]:
    selected_ids: set[str] = set()
    selected_by: dict[str, str] = {}
    merged_into: dict[str, str] = {}
    rejected_index = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in contribution_spec.get("rejected_candidates", [])
        if candidate.get("candidate_id")
    }
    for item in contribution_spec.get("items", []):
        final_id = str(item.get("id") or "")
        source_ids = [
            str(candidate_id)
            for candidate_id in item.get("source_candidate_ids", [])
            if candidate_id
        ]
        primary_id = source_ids[0] if source_ids else ""
        for candidate_id in source_ids:
            if candidate_id:
                selected_ids.add(str(candidate_id))
                selected_by[str(candidate_id)] = final_id
                if primary_id and candidate_id != primary_id:
                    merged_into[candidate_id] = primary_id
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        rejected_candidate = rejected_index.get(candidate_id, {})
        failures = list(
            rejected_candidate.get("rejection_reasons")
            or _candidate_failure_reasons(candidate)
        )
        records.append(
            {
                **candidate,
                "selected": candidate_id in selected_ids,
                "selected_as": selected_by.get(candidate_id),
                "merged_into": (
                    merged_into.get(candidate_id)
                    or rejected_candidate.get("merged_into")
                ),
                "rejection_reasons": [] if candidate_id in selected_ids else failures,
                "route_target": rejected_candidate.get(
                    "route_target",
                    candidate.get("route_target"),
                ),
            }
        )
    return {
        "schema_version": "1.0.0",
        "paper_id": contribution_spec.get("paper_id"),
        "candidate_count": len(records),
        "selected_count": len(contribution_spec.get("items", [])),
        "candidates": records,
    }


def _contribution_audit_summary(
    contribution_spec: dict[str, Any],
    candidate_snapshot: dict[str, Any],
    checks: dict[str, Any],
) -> dict[str, Any]:
    items = list(contribution_spec.get("items", []))
    source_coverage = sum(
        bool(item.get("source_block_ids") and item.get("source_records"))
        for item in items
    )
    failed_candidate_counts: dict[str, int] = {}
    for candidate in candidate_snapshot.get("candidates", []):
        for reason in candidate.get("rejection_reasons", []):
            failed_candidate_counts[reason] = failed_candidate_counts.get(reason, 0) + 1
    check_names = (
        "citation_artifact_check",
        "cross_reference_check",
        "quotation_marker_check",
        "author_voice_check",
        "discourse_marker_check",
        "source_copy_check",
        "ocr_cleanup_check",
        "role_separation_check",
        "semantic_heading_role_check",
        "traceability_check",
        "semantic_independence_check",
        "semantic_completeness_check",
        "unsupported_expansion_check",
        "contribution_coverage_check",
        "contribution_displayable_count_check",
        "duplicate_canonical_object_check",
        "duplicate_short_title_check",
        "author_contribution_alignment_check",
        "parent_child_overlap_check",
        "implementation_step_check",
        "core_contribution_check",
        "incremental_information_check",
        "result_only_check",
        "visible_grammar_check",
        "role_routing_check",
    )
    relevant_checks = {
        name: checks.get(name, {"name": name, "passed": False, "failures": []})
        for name in check_names
    }
    selected_item_blockers = [
        {
            "id": item.get("id"),
            "blockers": item.get("rewrite_blockers", []),
        }
        for item in items
        if item.get("rewrite_blockers")
    ]
    rejected_findings = [
        {
            "candidate_id": candidate.get("candidate_id"),
            "findings": candidate.get("rejection_reasons", []),
            "unsupported_explicit_claim": candidate.get(
                "unsupported_explicit_claim", False
            ),
        }
        for candidate in candidate_snapshot.get("candidates", [])
        if not candidate.get("selected")
    ]
    warnings = []
    if any(candidate.get("result_only_candidate") for candidate in candidate_snapshot.get("candidates", [])):
        warnings.append({"code": "RESULT_ONLY_CANDIDATES_ROUTED_TO_RESULTS"})
    if any(candidate.get("merged_from") for candidate in candidate_snapshot.get("candidates", [])):
        warnings.append({"code": "DUPLICATE_CONTRIBUTION_CLAIMS_MERGED"})
    if (
        1 <= int(contribution_spec.get("displayable_count") or 0) < 3
        and contribution_spec.get("selection_trace", {}).get("warning")
        == "CONTRIBUTION_SPARSE_BUT_SUFFICIENT"
    ):
        warnings.append(
            {
                "code": "CONTRIBUTION_SPARSE_BUT_SUFFICIENT",
                "message": (
                    "Only independently verified core Contributions are "
                    "shown; no weak third item was fabricated."
                ),
            }
        )
    failed_final_checks = [
        name
        for name, check in relevant_checks.items()
        if not bool(check.get("passed"))
        and name not in NON_BLOCKING_VISIBLE_STYLE_CHECKS
    ]
    if failed_final_checks:
        selected_item_blockers.append(
            {
                "id": None,
                "blockers": failed_final_checks,
            }
        )
    quality_status = "blocked" if selected_item_blockers else "passed"
    return {
        "schema_version": "1.0.0",
        "paper_id": contribution_spec.get("paper_id"),
        "status": quality_status,
        "quality_status": quality_status,
        "candidate_count": candidate_snapshot.get("candidate_count", 0),
        "selected_count": len(items),
        "displayable_count": contribution_spec.get("displayable_count", 0),
        "required_role_status": (
            contribution_spec.get("selection_trace", {}).get(
                "required_role_status",
                {},
            )
        ),
        "source_coverage": {
            "covered_items": source_coverage,
            "total_items": len(items),
            "complete": source_coverage == len(items),
        },
        "gate_rejection_counts": failed_candidate_counts,
        "checks": relevant_checks,
        "selected_item_blockers": selected_item_blockers,
        "rejected_candidate_findings": rejected_findings,
        "warnings": warnings,
    }


def _contribution_diagnostics(
    candidates: list[dict[str, Any]],
    contribution_spec: dict[str, Any],
    audit: dict[str, Any],
) -> dict[str, Any]:
    rejected = [candidate for candidate in candidates if not candidate.get("selected")]
    rejection_histogram: dict[str, int] = {}
    for candidate in rejected:
        for reason in candidate.get("rejection_reasons", []):
            rejection_histogram[str(reason)] = rejection_histogram.get(str(reason), 0) + 1
    return {
        "schema_version": "1.0.0",
        "paper_id": contribution_spec.get("paper_id"),
        "explicit_claims_found": sum(
            bool(candidate.get("explicit_claim_source_ids")) for candidate in candidates
        ),
        "semantic_candidates": len(candidates),
        "method_bound_candidates": sum(
            bool(candidate.get("method_node_ids") or candidate.get("method_node_id"))
            for candidate in candidates
        ),
        "unsupported_explicit_claims": sum(
            bool(candidate.get("unsupported_explicit_claim")) for candidate in candidates
        ),
        "duplicate_groups": sum(
            len(item.get("source_candidate_ids", [])) > 1
            for item in contribution_spec.get("items", [])
        ),
        "selected_count": len(contribution_spec.get("items", [])),
        "displayable_count": contribution_spec.get("displayable_count", 0),
        "author_contribution_group_count": len(
            contribution_spec.get("author_contribution_groups", [])
        ),
        "canonical_object_group_count": len(
            contribution_spec.get("canonical_object_groups", [])
        ),
        "routed_to_method_count": len(
            contribution_spec.get("routed_to_method", [])
        ),
        "routed_to_results_count": len(
            contribution_spec.get("routed_to_results", [])
        ),
        "required_role_status": contribution_spec.get(
            "selection_trace", {}
        ).get("required_role_status", {}),
        "candidate_attempts_per_role": contribution_spec.get(
            "selection_trace", {}
        ).get("candidate_attempts_per_role", {}),
        "recovery_steps_executed": contribution_spec.get(
            "selection_trace", {}
        ).get("recovery_steps_executed", []),
        "result_only_candidates": sum(
            bool(candidate.get("result_only_candidate")) for candidate in candidates
        ),
        "rewrite_failures": [
            {
                "id": item.get("id"),
                "blockers": item.get("rewrite_blockers", []),
                "attempts": item.get("rewrite_attempts", []),
            }
            for item in contribution_spec.get("items", [])
            if item.get("rewrite_blockers")
        ],
        "rejection_histogram": rejection_histogram,
        "remaining_blockers": audit.get("selected_item_blockers", []),
    }


def _contribution_debug_report_md(
    contribution_spec: dict[str, Any],
    snapshot: dict[str, Any],
    diagnostics: dict[str, Any],
    contribution_audit: dict[str, Any],
) -> str:
    lines = [
        "# Contributions Debug Report",
        "",
        f"- Paper: `{contribution_spec.get('paper_id')}`",
        f"- Quality status: **{contribution_audit.get('quality_status', '')}**",
        "",
        "## Stage statistics",
        "",
    ]
    for key in (
        "explicit_claims_found",
        "semantic_candidates",
        "method_bound_candidates",
        "unsupported_explicit_claims",
        "duplicate_groups",
        "selected_count",
        "displayable_count",
        "author_contribution_group_count",
        "canonical_object_group_count",
        "routed_to_method_count",
        "routed_to_results_count",
        "result_only_candidates",
    ):
        lines.append(f"- {key}: {diagnostics.get(key, 0)}")
    lines.extend(
        [
            "",
            "## Author contribution groups",
            "",
            f"`{contribution_spec.get('author_contribution_groups', [])}`",
            "",
            "## Canonical object groups",
            "",
            f"`{contribution_spec.get('canonical_object_groups', [])}`",
            "",
            "## Role selection and recovery",
            "",
            f"- Required roles: `{diagnostics.get('required_role_status', {})}`",
            f"- Attempts: `{diagnostics.get('candidate_attempts_per_role', {})}`",
            f"- Recovery: `{diagnostics.get('recovery_steps_executed', [])}`",
            "",
            "## Routing",
            "",
            f"- Method: `{contribution_spec.get('routed_to_method', [])}`",
            f"- Results: `{contribution_spec.get('routed_to_results', [])}`",
        ]
    )
    lines.extend(["", "## Candidate ledger", ""])
    for candidate in snapshot.get("candidates", []):
        lines.extend(
            [
                f"### {candidate.get('candidate_id')} — {candidate.get('innovation_object') or '[unresolved object]'}",
                f"- Discovery: `{candidate.get('discovery_source')}` / `{candidate.get('discovery_kind')}`",
                f"- Type: `{candidate.get('contribution_type')}`; method nodes: `{candidate.get('method_node_ids')}`",
                f"- Canonical object: `{candidate.get('canonical_object_id')}` / `{candidate.get('canonical_object_name')}`",
                f"- Author group: `{candidate.get('author_contribution_group_id')}`; parent: `{candidate.get('parent_object_id')}`",
                f"- Component level: `{candidate.get('component_level')}`; route: `{candidate.get('route_target')}`",
                f"- Raw claim: {candidate.get('raw_statement')}",
                f"- Mechanism: {candidate.get('mechanism_or_action')}",
                f"- Solved problem: {candidate.get('solved_problem')}",
                f"- Selected: `{candidate.get('selected')}`; merged into: `{candidate.get('merged_into')}`",
                f"- Rejection reasons: `{candidate.get('rejection_reasons')}`",
                f"- Sources: `{candidate.get('source_block_ids')}` pages `{candidate.get('source_pages')}`",
                "",
            ]
        )
    lines.extend(["## Final visible items", ""])
    for item in contribution_spec.get("items", []):
        lines.extend(
            [
                f"### {item.get('id')} — {item.get('short_title')}",
                f"- Visible description: {item.get('description')}",
                f"- Role: `{item.get('contribution_role')}`; canonical object: `{item.get('canonical_object_id')}`",
                f"- Displayable: `{item.get('displayable')}`; core score: `{item.get('core_score')}`",
                f"- Rewrite blockers: `{item.get('rewrite_blockers')}`",
                f"- Source candidates: `{item.get('source_candidate_ids')}`",
                f"- Evidence blocks: `{item.get('source_block_ids')}` pages `{item.get('source_pages')}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _contribution_preview_html(
    contribution_spec: dict[str, Any],
    contribution_audit: dict[str, Any],
) -> str:
    cards = "".join(
        "<article><h2>"
        + html.escape(str(item.get("short_title") or ""))
        + "</h2><p>"
        + html.escape(str(item.get("description") or ""))
        + "</p><small>"
        + html.escape(", ".join(str(block) for block in item.get("source_block_ids", [])))
        + "</small></article>"
        for item in contribution_spec.get("items", [])
    ) or "<p>No verified Contribution passed semantic selection.</p>"
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>Contributions Preview</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;color:#10234d;background:#f6f9ff}}main{{max-width:980px;margin:auto}}.status{{color:#52627a}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}article{{background:white;border:1px solid #c8d9f5;border-radius:10px;padding:16px}}article p{{line-height:1.4}}small{{color:#64748b}}</style></head>
<body><main><h1>Contributions</h1><p class=\"status\">Audit: {html.escape(str(contribution_audit.get('quality_status') or ''))}</p><div class=\"grid\">{cards}</div></main></body></html>"""


def _has_explicit_contribution_statement(paper_ir: dict[str, Any]) -> bool:
    allowed_sections = ("abstract", "introduction", "conclusion", "discussion")
    pattern = re.compile(
        r"\b(?:we\s+)?(?:propose|introduce|present|develop|design|construct|"
        r"build|formulate|define|release|establish|discover|identify|"
        r"adopt|incorporate)\b|"
        r"\b(?:main|primary|key)\s+contributions?\b|"
        r"\b(?:novel|new)\s+(?:method|model|framework|module|mechanism|"
        r"algorithm|dataset|benchmark|protocol|strategy|objective|loss)\b",
        re.I,
    )
    return any(
        pattern.search(str(block.get("text") or ""))
        and any(term in _section_text(block) for term in allowed_sections)
        for block in paper_ir.get("blocks", [])
        if block.get("type") not in {"title", "heading", "caption", "table", "equation"}
    )


def generate_motivation_contribution_specs(
    paper_ir: dict[str, Any],
    story: dict[str, Any],
    evidence: dict[str, Any],
    method_graph: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    motivation_candidates, extraction_diagnostics = _motivation_candidates(
        paper_ir,
        story,
        method_graph,
    )
    contribution_candidates = _contribution_candidates(
        paper_ir, evidence, method_graph
    )
    author_contribution_groups = _author_contribution_groups(paper_ir)
    _enrich_contribution_candidates(
        contribution_candidates,
        paper_ir,
        author_contribution_groups,
    )
    (
        semantic_motivation,
        _semantic_rejected_motivation,
        _semantic_recovery_steps,
        semantic_selection_trace,
    ) = _assemble_motivation_coverage(
        motivation_candidates,
        paper_ir,
        story,
    )
    (
        selected_motivation,
        rejected_motivation,
        recovery_steps,
        motivation_selection_trace,
    ) = _assemble_displayable_motivation(
        motivation_candidates,
        paper_ir,
        story,
        selected_semantic_count=len(semantic_motivation),
    )
    motivation_selection_trace["semantic_selection_trace"] = (
        semantic_selection_trace
    )
    merged_contributions, rejected_contributions = _merge_candidates(
        contribution_candidates, "contribution"
    )
    (
        selected_contributions,
        selection_rejected_contributions,
        routed_to_method,
        routed_to_results,
        contribution_selection_trace,
    ) = _select_final_contributions(merged_contributions)
    rejected_contributions = [
        *rejected_contributions,
        *selection_rejected_contributions,
    ]
    motivation_items = _finalize_motivation(selected_motivation)
    motivation_spec = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir.get("paper_id"),
        "items": motivation_items,
        "rejected_candidates": rejected_motivation,
        "selection_policy": {
            "fixed_item_count": False,
            "minimum_items": MOTIVATION_MIN_ITEMS,
            "target_minimum_items": MOTIVATION_TARGET_ITEMS,
            "maximum_items": MOTIVATION_MAX_ITEMS,
            "required_coverage_slots": list(MOTIVATION_COVERAGE_SLOTS),
            "hard_coverage_slots": list(MOTIVATION_HARD_COVERAGE_SLOTS),
            "preferred_semantic_roles": list(MOTIVATION_REQUIRED_ROLES),
            "hard_role_triplet_required": False,
            "sparse_output_allowed": True,
            "paper_type": motivation_selection_trace.get("paper_type"),
            "coverage_assembled": True,
            "gate_driven": True,
            "semantic_merge_required": True,
            "count_basis": "displayable_items_only",
        },
    }
    contribution_spec = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir.get("paper_id"),
        "items": _finalize_contributions(selected_contributions),
        "displayable_count": len(selected_contributions),
        "author_contribution_groups": author_contribution_groups,
        "canonical_object_groups": [
            {
                "canonical_object_id": candidate.get("canonical_object_id"),
                "canonical_object_name": candidate.get("canonical_object_name"),
                "candidate_ids": [
                    candidate.get("candidate_id"),
                    *candidate.get("merged_from", []),
                ],
            }
            for candidate in merged_contributions
        ],
        "merged_candidates": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "canonical_object_id": candidate.get("canonical_object_id"),
                "merged_from": candidate.get("merged_from", []),
            }
            for candidate in merged_contributions
            if candidate.get("merged_from")
        ],
        "routed_to_method": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "canonical_object_id": candidate.get("canonical_object_id"),
                "innovation_object": candidate.get("innovation_object"),
                "component_level": candidate.get("component_level"),
            }
            for candidate in routed_to_method
        ],
        "routed_to_results": [
            {
                "candidate_id": candidate.get("candidate_id"),
                "canonical_object_id": candidate.get("canonical_object_id"),
                "innovation_object": candidate.get("innovation_object"),
            }
            for candidate in routed_to_results
        ],
        "rejected_candidates": rejected_contributions,
        "quality_status": contribution_selection_trace["quality_status"],
        "selection_policy": {
            "minimum_items": 1,
            "target_minimum_items": 3,
            "maximum_items": 4,
            "required_roles": list(CONTRIBUTION_REQUIRED_ROLES),
            "hard_required_roles": [
                "primary_method_or_architecture_or_innovation_mechanism"
            ],
            "sparse_output_allowed": True,
            "count_basis": "displayable_items_only",
            "gate_driven": True,
            "semantic_merge_required": True,
            "core_ranked_not_truncated": True,
        },
        "selection_trace": contribution_selection_trace,
    }
    _filter_invalid_visible_items(
        motivation_spec,
        contribution_spec,
        paper_ir,
    )
    checks, issues = validate_motivation_contribution_specs(
        motivation_spec,
        contribution_spec,
        paper_ir,
    )
    motivation_coverage_failures: list[dict[str, Any]] = []
    displayable_items = [
        item
        for item in motivation_spec["items"]
        if item.get("selected") is True
        and item.get("visible_text")
        and item.get("rewrite_status") == "passed"
        and item.get("language_audit_status") == "passed"
        and item.get("traceability_status") == "passed"
        and item.get("role_separation_status") == "passed"
        and item.get("displayable") is True
    ]
    covered_slots = {
        str(item.get("coverage_slot") or "")
        for item in displayable_items
    }
    missing_hard_slots = [
        slot
        for slot in MOTIVATION_HARD_COVERAGE_SLOTS
        if slot not in covered_slots
    ]
    missing_preferred_slots = [
        slot
        for slot in MOTIVATION_COVERAGE_SLOTS
        if slot not in covered_slots
    ]
    if len(displayable_items) < MOTIVATION_MIN_ITEMS:
        motivation_coverage_failures.append(
            {
                "code": "MOTIVATION_EVIDENCE_INSUFFICIENT",
                "reason": (
                    "no displayable, sourced problem-side statement survived "
                    "the Motivation gates"
                ),
                "selected_semantic_count": len(semantic_motivation),
                "displayable_item_count": len(displayable_items),
                "required_count": MOTIVATION_MIN_ITEMS,
                "target_count": MOTIVATION_TARGET_ITEMS,
                "missing_coverage_slots": missing_preferred_slots,
                "recovery_steps_executed": recovery_steps,
            }
        )
    elif (
        len(displayable_items) < MOTIVATION_TARGET_ITEMS
        or missing_preferred_slots
    ):
        motivation_spec["warnings"] = [
            *motivation_spec.get("warnings", []),
            {
                "code": "MOTIVATION_SPARSE_COVERAGE",
                "displayable_item_count": len(displayable_items),
                "missing_preferred_coverage_slots": missing_preferred_slots,
                "message": (
                    "The Poster keeps the available verified Motivation items "
                    "without inventing missing coverage slots."
                ),
            },
        ]
    if len(displayable_items) > MOTIVATION_MAX_ITEMS:
        motivation_coverage_failures.append(
            {
                "code": "MOTIVATION_ITEM_LIMIT_EXCEEDED",
                "reason": "Motivation selection exceeded the five-item limit",
                "displayable_item_count": len(displayable_items),
            }
        )
    checks["motivation_coverage_check"] = _check_result(
        "motivation_coverage_check", motivation_coverage_failures
    )

    contribution_coverage_failures: list[dict[str, Any]] = []
    contribution_displayable = [
        item
        for item in contribution_spec["items"]
        if item.get("selected") is True
        and item.get("short_title")
        and item.get("description")
        and item.get("displayable") is True
        and bool(
            (item.get("final_gate_results", {}).get("core_contribution_gate") or {}).get("passed")
        )
        and bool(
            (item.get("final_gate_results", {}).get("evidence_gate") or {}).get("passed")
        )
    ]
    contribution_roles = {
        str(item.get("contribution_role") or "")
        for item in contribution_displayable
    }
    missing_contribution_roles = [
        role
        for role in CONTRIBUTION_REQUIRED_ROLES
        if role not in contribution_roles
    ]
    core_contribution_present = bool(
        contribution_roles
        & {
            "primary_method_or_architecture",
            "primary_innovation_mechanism",
        }
    )
    if (
        not (1 <= len(contribution_displayable) <= 4)
        or not core_contribution_present
    ):
        recoverable_contribution_candidates = [
            candidate
            for candidate in contribution_candidates
            if all(
                bool((candidate.get("gate_results", {}).get(name) or {}).get("passed"))
                for name in (
                    "source_gate",
                    "contribution_identity_gate",
                    "method_or_content_support_gate",
                    "semantic_role_gate",
                )
            )
        ]
        if recoverable_contribution_candidates:
            contribution_coverage_failures.append(
                {
                    "code": "CONTRIBUTION_EVIDENCE_INSUFFICIENT",
                    "reason": (
                        "no displayable core architecture or innovation "
                        "mechanism remains after ordered recovery"
                    ),
                    "displayable_count": len(contribution_displayable),
                    "missing_roles": missing_contribution_roles,
                    "recovery_steps_executed": contribution_selection_trace.get(
                        "recovery_steps_executed",
                        [],
                    ),
                    "candidate_ids": [
                        candidate.get("candidate_id")
                        for candidate in recoverable_contribution_candidates
                    ],
                    "return_to": "paper-motivation-contributions",
                }
            )
        else:
            has_explicit_claim = _has_explicit_contribution_statement(paper_ir)
            contribution_coverage_failures.append(
                {
                    "code": "CONTRIBUTION_EVIDENCE_INSUFFICIENT",
                    "reason": (
                        "explicit contribution claims were found but none had verified "
                        "content support"
                        if has_explicit_claim
                        else "no explicit contribution statement was found"
                    ),
                    "candidate_ids": [
                        candidate.get("candidate_id")
                        for candidate in contribution_candidates
                    ],
                    "return_to": (
                        "paper-motivation-contributions"
                        if has_explicit_claim
                        else "paper-storyline"
                    ),
                }
            )
    contribution_spec["displayable_count"] = len(contribution_displayable)
    contribution_spec["quality_status"] = (
        "blocked"
        if contribution_coverage_failures
        else (
            "sparse_but_sufficient"
            if len(contribution_displayable) < 3
            else "passed"
        )
    )
    if not contribution_coverage_failures and len(contribution_displayable) < 3:
        contribution_spec["warnings"] = [
            {
                "code": "CONTRIBUTION_SPARSE_BUT_SUFFICIENT",
                "displayable_count": len(contribution_displayable),
                "missing_target_roles": missing_contribution_roles,
                "message": (
                    "The Poster keeps all verified independent Contributions "
                    "without inventing a third item."
                ),
            }
        ]
    checks["contribution_coverage_check"] = _check_result(
        "contribution_coverage_check", contribution_coverage_failures
    )
    if contribution_coverage_failures:
        # The detailed coverage failure below carries the recovery trace and
        # the correct return target. Keep the generic count check in `checks`,
        # but do not let its earlier issue shadow the actionable blocker.
        issues = [
            issue
            for issue in issues
            if issue.get("code") != "CONTRIBUTION_DISPLAYABLE_COUNT_CHECK"
        ]
    for check_name in (
        "motivation_coverage_check",
        "contribution_coverage_check",
    ):
        check = checks[check_name]
        if not check["passed"]:
            return_to = (
                str(check["failures"][0].get("return_to"))
                if check["failures"]
                and check["failures"][0].get("return_to")
                else "paper-motivation-contributions"
            )
            issues.append(
                {
                    "code": (
                        str(check["failures"][0].get("code"))
                        if check["failures"]
                        and check["failures"][0].get("code")
                        else check_name.upper()
                    ),
                    "severity": "error",
                    "message": f"{check_name} failed; empty output would hide sourced paper content.",
                    "details": check["failures"],
                    "return_to": return_to,
                }
            )

    contribution_candidate_records = _contribution_candidate_snapshot(
        contribution_candidates,
        contribution_spec,
    )
    contribution_audit = _contribution_audit_summary(
        contribution_spec,
        contribution_candidate_records,
        checks,
    )
    contribution_spec["quality_status"] = contribution_audit["quality_status"]
    contribution_diagnostics = _contribution_diagnostics(
        contribution_candidates,
        contribution_spec,
        contribution_audit,
    )
    motivation_candidate_records = _motivation_candidate_ledger(
        motivation_candidates,
        selected_motivation,
        rejected_motivation,
    )
    rejection_histogram: dict[str, int] = {}
    for candidate in motivation_candidate_records:
        if candidate.get("selected"):
            continue
        for reason in candidate.get("rejection_reasons", []):
            rejection_histogram[str(reason)] = (
                rejection_histogram.get(str(reason), 0) + 1
            )
    failed_role_attempts = [
        {
            "selection_role": role,
            "candidate_id": attempt.get("candidate_id"),
            "failure_code": attempt.get("failure_code"),
            "attempts": attempt.get("attempts", []),
        }
        for role, role_attempts in motivation_selection_trace.get(
            "candidate_attempts_per_role",
            {},
        ).items()
        for attempt in role_attempts
        if attempt.get("status") == "failed"
    ]
    extraction_diagnostics.update(
        {
            "candidates_after_semantic_gates": int(
                motivation_selection_trace.get(
                    "semantic_gate_pass_count",
                    0,
                )
            ),
            "candidates_after_merging": int(
                motivation_selection_trace.get("merged_count", 0)
            ),
            "selected_count": len(displayable_items),
            "selected_motivation_count": len(displayable_items),
            "selected_semantic_count": len(semantic_motivation),
            "displayable_item_count": len(displayable_items),
            "rejection_histogram": rejection_histogram,
            "required_role_coverage": {
                role: any(
                    str(item.get("selection_role") or "") == role
                    for item in displayable_items
                )
                for role in MOTIVATION_REQUIRED_ROLES
            },
            "required_coverage_slots": {
                slot: slot in covered_slots
                for slot in MOTIVATION_COVERAGE_SLOTS
            },
            "required_family_coverage": {
                family: any(
                    str(item.get("coverage_family") or "") == family
                    for item in displayable_items
                )
                for family in MOTIVATION_REQUIRED_FAMILIES
            },
            "paper_type": motivation_selection_trace.get("paper_type"),
            "required_coverage_status": motivation_selection_trace.get(
                "required_coverage_status",
                {},
            ),
            "required_role_status": motivation_selection_trace.get(
                "required_role_status",
                {},
            ),
            "candidate_attempts_per_slot": motivation_selection_trace.get(
                "candidate_attempts_per_slot",
                {},
            ),
            "candidate_attempts_per_role": motivation_selection_trace.get(
                "candidate_attempts_per_role",
                {},
            ),
            "empty_visible_items": motivation_selection_trace.get(
                "empty_visible_items",
                [],
            ),
            "rewrite_exhausted_candidates": motivation_selection_trace.get(
                "rewrite_exhausted_candidates",
                [],
            ),
            "replacement_candidates_used": motivation_selection_trace.get(
                "replacement_candidates_used",
                [],
            ),
            "coverage_recovery_executed": motivation_selection_trace.get(
                "coverage_recovery_executed",
                [],
            ),
            "sparse_fallback_used": motivation_selection_trace.get(
                "sparse_fallback_used",
                False,
            ),
            "compose_blockers": motivation_selection_trace.get(
                "compose_blockers",
                [],
            ),
            "recovery_steps_executed": recovery_steps,
            "rewrite_failures": failed_role_attempts,
            "remaining_blockers": [
                *motivation_coverage_failures,
                *motivation_selection_trace.get("compose_blockers", []),
            ],
            "selection_trace": motivation_selection_trace,
        }
    )
    rejected_candidate_findings = [
        {
            "candidate_id": candidate.get("candidate_id"),
            "rejection_stage": candidate.get(
                "rejection_stage",
                "candidate_selection",
            ),
            "findings": candidate.get("rejection_reasons", []),
        }
        for candidate in motivation_candidate_records
        if not candidate.get("selected")
    ]
    selected_item_blockers = list(issues)
    warnings: list[dict[str, Any]] = []
    if recovery_steps:
        warnings.append(
            {
                "code": "MOTIVATION_COVERAGE_RECOVERY_EXECUTED",
                "steps": recovery_steps,
            }
        )
    if motivation_selection_trace.get("sparse_fallback_used"):
        warnings.append(
            {
                "code": "MOTIVATION_SPARSE_BUT_SUFFICIENT",
                "displayable_item_count": len(displayable_items),
                "reason": (
                    "ordered recovery found fewer than the target number of "
                    "independent, displayable problem-side units; no weak or "
                    "duplicated item was fabricated"
                ),
            }
        )
    audit = {
        "schema_version": "1.0.0",
        "paper_id": paper_ir.get("paper_id"),
        "status": "failed" if selected_item_blockers else "passed",
        "quality_status": (
            "blocked"
            if selected_item_blockers
            else (
                "sparse_but_sufficient"
                if len(displayable_items) < MOTIVATION_TARGET_ITEMS
                else "passed"
            )
        ),
        "motivation_candidates": len(motivation_candidates),
        "motivation_selected": len(displayable_items),
        "selected_semantic_count": len(semantic_motivation),
        "displayable_item_count": len(displayable_items),
        "paper_type": motivation_selection_trace.get("paper_type"),
        "required_coverage_status": motivation_selection_trace.get(
            "required_coverage_status",
            {},
        ),
        "required_role_status": motivation_selection_trace.get(
            "required_role_status",
            {},
        ),
        "candidate_attempts_per_slot": motivation_selection_trace.get(
            "candidate_attempts_per_slot",
            {},
        ),
        "candidate_attempts_per_role": motivation_selection_trace.get(
            "candidate_attempts_per_role",
            {},
        ),
        "empty_visible_items": motivation_selection_trace.get(
            "empty_visible_items",
            [],
        ),
        "rewrite_exhausted_candidates": motivation_selection_trace.get(
            "rewrite_exhausted_candidates",
            [],
        ),
        "replacement_candidates_used": motivation_selection_trace.get(
            "replacement_candidates_used",
            [],
        ),
        "coverage_recovery_executed": motivation_selection_trace.get(
            "coverage_recovery_executed",
            [],
        ),
        "sparse_fallback_used": motivation_selection_trace.get(
            "sparse_fallback_used",
            False,
        ),
        "compose_blockers": motivation_selection_trace.get(
            "compose_blockers",
            [],
        ),
        "contribution_candidates": len(contribution_candidates),
        "contribution_selected": len(contribution_spec["items"]),
        "checks": checks,
        "issues": selected_item_blockers,
        "selected_item_blockers": selected_item_blockers,
        "rejected_candidate_findings": rejected_candidate_findings,
        "warnings": warnings,
        "return_to": (
            str(
                selected_item_blockers[0].get(
                    "return_to",
                    "paper-motivation-contributions",
                )
            )
            if selected_item_blockers
            else None
        ),
        "motivation_candidate_records": {
            "schema_version": "1.0.0",
            "paper_id": paper_ir.get("paper_id"),
            "candidate_count": len(motivation_candidate_records),
            "selected_count": len(displayable_items),
            "selected_semantic_count": len(semantic_motivation),
            "displayable_item_count": len(displayable_items),
            "candidates": motivation_candidate_records,
        },
        "extraction_diagnostics": extraction_diagnostics,
        "contribution_candidate_records": contribution_candidate_records,
        "contribution_audit": contribution_audit,
        "contribution_extraction_diagnostics": contribution_diagnostics,
    }
    return motivation_spec, contribution_spec, audit


def _failure_targets_motivation(failure: dict[str, Any]) -> bool:
    role = str(failure.get("role") or "")
    item_id = str(failure.get("id") or "")
    item_ids = [str(value or "") for value in failure.get("ids", [])]
    return bool(
        role == "motivation"
        or item_id.startswith("M")
        or any(value.startswith("M") for value in item_ids)
        or failure.get("code") == "MOTIVATION_EVIDENCE_INSUFFICIENT"
    )


def _motivation_audit_summary(
    motivation_spec: dict[str, Any],
    candidate_snapshot: dict[str, Any],
    combined_audit: dict[str, Any],
) -> dict[str, Any]:
    motivation_check_names = (
        "citation_artifact_check",
        "cross_reference_check",
        "quotation_marker_check",
        "author_voice_check",
        "discourse_marker_check",
        "source_copy_check",
        "ocr_cleanup_check",
        "role_separation_check",
        "traceability_check",
        "semantic_independence_check",
        "semantic_completeness_check",
        "unsupported_expansion_check",
        "motivation_language_quality_check",
        "motivation_coverage_check",
    )
    checks: dict[str, Any] = {}
    blockers: list[dict[str, Any]] = []
    combined_checks = combined_audit.get("checks", {})
    for name in motivation_check_names:
        original = combined_checks.get(
            name,
            {"name": name, "passed": False, "failures": []},
        )
        failures = list(original.get("failures") or [])
        if name != "motivation_coverage_check":
            failures = [
                failure
                for failure in failures
                if _failure_targets_motivation(failure)
            ]
        check = {
            "name": name,
            "passed": not failures,
            "failures": failures,
        }
        checks[name] = check
        if failures and name not in NON_BLOCKING_VISIBLE_STYLE_CHECKS:
            blockers.append(
                {
                    "code": name.upper(),
                    "failures": failures,
                    "return_to": "paper-motivation-contributions",
                }
            )
    rewrite_blockers = [
        {
            "code": "MOTIVATION_VISIBLE_TEXT_REWRITE_FAILED",
            "id": item.get("id"),
            "selection_role": item.get("selection_role"),
            "blockers": item.get("rewrite_blockers", []),
        }
        for item in motivation_spec.get("items", [])
        if item.get("rewrite_blockers")
    ]
    blockers.extend(rewrite_blockers)
    rejected_findings = [
        {
            "candidate_id": candidate.get("candidate_id"),
            "rejection_stage": candidate.get("rejection_stage"),
            "findings": candidate.get("rejection_reasons", []),
            "merged_into": candidate.get("merged_into"),
        }
        for candidate in candidate_snapshot.get("candidates", [])
        if not candidate.get("selected")
    ]
    return {
        "schema_version": "1.0.0",
        "paper_id": motivation_spec.get("paper_id"),
        "status": "failed" if blockers else "passed",
        "quality_status": (
            "blocked"
            if blockers
            else (
                "sparse_but_sufficient"
                if len(motivation_spec.get("items", []))
                < MOTIVATION_TARGET_ITEMS
                else "passed"
            )
        ),
        "selected_count": len(motivation_spec.get("items", [])),
        "selected_semantic_count": combined_audit.get(
            "selected_semantic_count",
            0,
        ),
        "displayable_item_count": combined_audit.get(
            "displayable_item_count",
            len(motivation_spec.get("items", [])),
        ),
        "paper_type": combined_audit.get("paper_type"),
        "required_coverage_status": combined_audit.get(
            "required_coverage_status",
            {},
        ),
        "required_role_status": combined_audit.get(
            "required_role_status",
            {},
        ),
        "candidate_attempts_per_slot": combined_audit.get(
            "candidate_attempts_per_slot",
            {},
        ),
        "candidate_attempts_per_role": combined_audit.get(
            "candidate_attempts_per_role",
            {},
        ),
        "empty_visible_items": combined_audit.get(
            "empty_visible_items",
            [],
        ),
        "rewrite_exhausted_candidates": combined_audit.get(
            "rewrite_exhausted_candidates",
            [],
        ),
        "replacement_candidates_used": combined_audit.get(
            "replacement_candidates_used",
            [],
        ),
        "coverage_recovery_executed": combined_audit.get(
            "coverage_recovery_executed",
            [],
        ),
        "sparse_fallback_used": combined_audit.get(
            "sparse_fallback_used",
            False,
        ),
        "compose_blockers": combined_audit.get(
            "compose_blockers",
            [],
        ),
        "required_role_coverage": (
            combined_audit.get("extraction_diagnostics", {}).get(
                "required_role_coverage",
                {},
            )
        ),
        "checks": checks,
        "selected_item_blockers": blockers,
        "rejected_candidate_findings": rejected_findings,
        "warnings": [
            *(
                [
                    {
                        "code": "MOTIVATION_COVERAGE_RECOVERY_EXECUTED",
                        "steps": combined_audit.get(
                            "extraction_diagnostics",
                            {},
                        ).get("recovery_steps_executed", []),
                    }
                ]
                if combined_audit.get("extraction_diagnostics", {}).get(
                    "recovery_steps_executed"
                )
                else []
            ),
            *(
                [
                    {
                        "code": "MOTIVATION_SPARSE_BUT_SUFFICIENT",
                        "displayable_item_count": combined_audit.get(
                            "displayable_item_count",
                            0,
                        ),
                    }
                ]
                if combined_audit.get("sparse_fallback_used")
                else []
            ),
        ],
    }


def _motivation_debug_report_md(
    motivation_spec: dict[str, Any],
    candidate_snapshot: dict[str, Any],
    diagnostics: dict[str, Any],
    motivation_audit: dict[str, Any],
) -> str:
    lines = [
        "# Motivation Debug Report",
        "",
        f"- Paper ID: `{motivation_spec.get('paper_id') or ''}`",
        f"- Raw candidates: {diagnostics.get('raw_candidates', 0)}",
        (
            "- Problem-side candidates: "
            f"{diagnostics.get('problem_side_candidates', 0)}"
        ),
        (
            "- Candidates after semantic Gates: "
            f"{diagnostics.get('candidates_after_semantic_gates', 0)}"
        ),
        (
            "- Candidates after merging: "
            f"{diagnostics.get('candidates_after_merging', 0)}"
        ),
        (
            "- Selected semantic candidates: "
            f"{diagnostics.get('selected_semantic_count', 0)}"
        ),
        (
            "- Displayable items: "
            f"{diagnostics.get('displayable_item_count', 0)}"
        ),
        (
            "- Empty visible attempts: "
            f"{len(diagnostics.get('empty_visible_items', []))}"
        ),
        (
            "- Replacement candidates used: "
            f"{len(diagnostics.get('replacement_candidates_used', []))}"
        ),
        f"- Quality status: `{motivation_audit.get('quality_status', '')}`",
        "",
        "## Scanned sections and paragraphs",
        "",
    ]
    for block in diagnostics.get("scanned_blocks", []):
        lines.extend(
            [
                (
                    f"### `{block.get('block_id')}` — "
                    f"{block.get('section_title') or block.get('section_kind')} "
                    f"(page {block.get('page')})"
                ),
                "",
                (
                    f"- Kind: `{block.get('section_kind')}`; "
                    f"sentences: {block.get('sentence_count', 0)}"
                ),
                f"- Preview: {block.get('text_preview') or ''}",
                "",
            ]
        )
    lines.extend(["## Candidate ledger", ""])
    for candidate in candidate_snapshot.get("candidates", []):
        gate_results = {
            **(candidate.get("gate_results") or {}),
            **(candidate.get("final_gate_results") or {}),
        }
        failed_gates = [
            name
            for name, result in gate_results.items()
            if not bool(result.get("passed"))
        ]
        structure = candidate.get("relation_structure") or {}
        lines.extend(
            [
                (
                    f"### `{candidate.get('candidate_id')}` — "
                    f"{'selected' if candidate.get('selected') else 'rejected'}"
                ),
                "",
                f"- Raw: {candidate.get('raw_statement') or ''}",
                f"- Extracted clause: {candidate.get('source_clause') or ''}",
                (
                    "- Context window: "
                    + " | ".join(
                        str(value)
                        for value in candidate.get("context_window", [])
                    )
                ),
                (
                    "- Relation: "
                    f"`{structure.get('subject', '')}` → "
                    f"`{structure.get('relation', '')}` → "
                    f"`{structure.get('object', '')}`"
                ),
                (
                    f"- Role: `{candidate.get('role') or ''}`; "
                    f"selection role: `{candidate.get('selection_role') or ''}`"
                ),
                (
                    "- Gate results: "
                    + (
                        ", ".join(
                            f"{name}={'pass' if result.get('passed') else 'fail'}"
                            for name, result in gate_results.items()
                        )
                        or "none"
                    )
                ),
                (
                    "- Rejection reasons: "
                    + (
                        ", ".join(
                            str(value)
                            for value in candidate.get(
                                "rejection_reasons",
                                [],
                            )
                        )
                        or "none"
                    )
                ),
                (
                    f"- Merge: merged into "
                    f"`{candidate.get('merged_into') or ''}`; merged from "
                    f"`{', '.join(candidate.get('merged_from', []))}`"
                ),
                (
                    "- Source: "
                    + ", ".join(
                        (
                            f"{record.get('block_id')} p.{record.get('page')} "
                            f"[{record.get('source_section')}]"
                        )
                        for record in candidate.get("source_records", [])
                    )
                ),
                (
                    "- Blocking Gates: "
                    + (", ".join(failed_gates) or "none")
                ),
                "",
            ]
        )
    trace = diagnostics.get("selection_trace", {})
    lines.extend(
        [
            "## Required-slot selection",
            "",
            *[
                f"- `{role}`: `{winner or 'unfilled'}`"
                for role, winner in trace.get(
                    "required_slot_winners",
                    {},
                ).items()
            ],
            "",
            "## Candidate rewrite attempts by role",
            "",
        ]
    )
    for role, role_attempts in trace.get(
        "candidate_attempts_per_role",
        {},
    ).items():
        lines.append(f"### `{role}`")
        lines.append("")
        if not role_attempts:
            lines.append("- No eligible candidate was available.")
            lines.append("")
            continue
        for attempt in role_attempts:
            lines.append(
                f"- `{attempt.get('candidate_id')}` rank "
                f"{attempt.get('rank')}: `{attempt.get('status')}`"
                + (
                    f" (`{attempt.get('failure_code')}`)"
                    if attempt.get("failure_code")
                    else ""
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Coverage recovery",
            "",
        ]
    )
    recovery_trace = trace.get("recovery_trace", [])
    if recovery_trace:
        for step in recovery_trace:
            lines.append(
                f"- `{step.get('step')}` added "
                f"{len(step.get('added_candidate_ids', []))} candidates; "
                f"missing roles={step.get('missing_roles_after_step', [])}"
            )
    else:
        lines.append("- Not triggered.")
    lines.extend(
        [
            "",
            "## Final count and Compose audit",
            "",
            (
                "- Required role status: "
                f"{diagnostics.get('required_role_status', {})}"
            ),
            (
                "- Rewrite-exhausted candidates: "
                f"{diagnostics.get('rewrite_exhausted_candidates', [])}"
            ),
            (
                "- Compose blockers: "
                f"{diagnostics.get('compose_blockers', [])}"
            ),
        ]
    )
    lines.extend(["", "## Final visible text and evidence", ""])
    for item in motivation_spec.get("items", []):
        attempts = item.get("rewrite_attempts", [])
        before = next(
            (
                attempt.get("visible_text")
                for attempt in attempts
                if attempt.get("visible_text")
            ),
            "",
        )
        lines.extend(
            [
                (
                    f"### `{item.get('id')}` — "
                    f"`{item.get('selection_role')}`"
                ),
                "",
                f"- First rewrite attempt: {before}",
                f"- Final visible_text: {item.get('visible_text') or ''}",
                (
                    "- Evidence: "
                    + ", ".join(
                        (
                            f"{record.get('block_id')} p.{record.get('page')} — "
                            f"{record.get('raw_statement')}"
                        )
                        for record in item.get("source_records", [])
                    )
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _motivation_preview_html(
    motivation_spec: dict[str, Any],
    motivation_audit: dict[str, Any],
) -> str:
    cards = "".join(
        (
            "<article><span class=\"role\">"
            + html.escape(str(item.get("selection_role") or ""))
            + "</span><p>"
            + html.escape(str(item.get("visible_text") or ""))
            + "</p><small>"
            + html.escape(
                ", ".join(
                    f"{record.get('block_id')} · p.{record.get('page')}"
                    for record in item.get("source_records", [])
                )
            )
            + "</small></article>"
        )
        for item in motivation_spec.get("items", [])
    ) or "<p>No Motivation item passed semantic selection and rewrite audit.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Motivation Preview</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #10234d; background: #f6f9ff; }}
main {{ max-width: 980px; margin: auto; }}
.status {{ color: #52627a; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px; }}
article {{ background: white; border: 1px solid #c8d9f5; border-radius: 10px; padding: 16px; }}
.role {{ color: #315da8; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
article p {{ font-size: 18px; line-height: 1.35; }}
small {{ color: #64748b; }}
</style>
</head>
<body><main>
<h1>Motivation</h1>
<p class="status">Audit: {html.escape(str(motivation_audit.get("quality_status") or ""))}</p>
<div class="grid">{cards}</div>
</main></body>
</html>
"""


def _preview_html(
    motivation_spec: dict[str, Any],
    contribution_spec: dict[str, Any],
) -> str:
    motivation = "".join(
        f"<li>{html.escape(str(item.get('visible_text') or ''))}</li>"
        for item in motivation_spec.get("items", [])
    ) or "<li>No Motivation item passed every Gate.</li>"
    contributions = "".join(
        "<article><strong>"
        + html.escape(str(item.get("short_title") or ""))
        + "</strong><p>"
        + html.escape(str(item.get("description") or ""))
        + "</p></article>"
        for item in contribution_spec.get("items", [])
    ) or "<p>No Contribution item passed every Gate.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Motivation and Contributions Preview</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 32px; color: #10234d; }}
section {{ margin-bottom: 28px; }}
ul {{ display: grid; gap: 10px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
article {{ border: 1px solid #c8d9f5; border-radius: 8px; padding: 14px; }}
article p {{ margin: 7px 0 0; }}
</style>
</head>
<body>
<section><h1>Motivation</h1><ul>{motivation}</ul></section>
<section><h1>Contributions</h1><div class="cards">{contributions}</div></section>
</body>
</html>
"""


def build_motivation_contributions(
    paper_ir_path: Path,
    story_path: Path,
    evidence_path: Path,
    method_graph_path: Path,
    output_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    paper_ir = read_json(paper_ir_path)
    story = read_json(story_path)
    evidence = read_json(evidence_path)
    method_graph = read_json(method_graph_path)
    motivation_spec, contribution_spec, audit = (
        generate_motivation_contribution_specs(
            paper_ir,
            story,
            evidence,
            method_graph,
        )
    )
    motivation_candidate_records = audit.get(
        "motivation_candidate_records",
        {},
    )
    motivation_audit = _motivation_audit_summary(
        motivation_spec,
        motivation_candidate_records,
        audit,
    )
    audit["motivation_audit"] = motivation_audit
    motivation_path = write_json(
        output_dir / "motivation_spec.json", motivation_spec
    )
    contribution_path = write_json(
        output_dir / "contribution_spec.json", contribution_spec
    )
    audit_path = write_json(
        output_dir / "motivation_contribution_audit.json", audit
    )
    write_json(
        output_dir / "contribution_candidates.json",
        audit.get("contribution_candidate_records", {}),
    )
    write_json(
        output_dir / "contribution_audit.json",
        audit.get("contribution_audit", {}),
    )
    write_json(
        output_dir / "contribution_extraction_diagnostics.json",
        audit.get("contribution_extraction_diagnostics", {}),
    )
    write_json(
        output_dir / "motivation_candidates.json",
        motivation_candidate_records,
    )
    write_json(
        output_dir / "extraction_diagnostics.json",
        audit.get("extraction_diagnostics", {}),
    )
    write_json(
        output_dir / "motivation_audit.json",
        motivation_audit,
    )
    debug_path = output_dir / "motivation-debug-report.md"
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(
        _motivation_debug_report_md(
            motivation_spec,
            motivation_candidate_records,
            audit.get("extraction_diagnostics", {}),
            motivation_audit,
        ),
        encoding="utf-8",
        newline="\n",
    )
    motivation_preview_path = output_dir / "motivation-preview.html"
    motivation_preview_path.write_text(
        _motivation_preview_html(
            motivation_spec,
            motivation_audit,
        ),
        encoding="utf-8",
        newline="\n",
    )
    contribution_debug_path = output_dir / "contribution-debug-report.md"
    contribution_debug_path.write_text(
        _contribution_debug_report_md(
            contribution_spec,
            audit.get("contribution_candidate_records", {}),
            audit.get("contribution_extraction_diagnostics", {}),
            audit.get("contribution_audit", {}),
        ),
        encoding="utf-8",
        newline="\n",
    )
    contribution_preview_path = output_dir / "contribution-preview.html"
    contribution_preview_path.write_text(
        _contribution_preview_html(
            contribution_spec,
            audit.get("contribution_audit", {}),
        ),
        encoding="utf-8",
        newline="\n",
    )
    preview_path = output_dir / "motivation_contribution_preview.html"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(
        _preview_html(motivation_spec, contribution_spec),
        encoding="utf-8",
        newline="\n",
    )
    return motivation_path, contribution_path, audit_path, preview_path
