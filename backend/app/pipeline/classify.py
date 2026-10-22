"""Keyword-based document classifier. Keywords live in the document_types table (configurable)."""
import re

from ..models import DocumentType


def classify(text: str, doc_types: list[DocumentType]) -> tuple[str | None, float]:
    """Return (type code, confidence 0–1). Keywords near the top of the document (titles) weigh more."""
    lowered = text.lower()
    head = lowered[:300]
    scores: dict[str, float] = {}
    for dt in doc_types:
        score = 0.0
        for kw in dt.keywords:
            kw = kw.lower()
            hits = len(re.findall(r"\b" + re.escape(kw) + r"\b", lowered))
            if hits:
                score += min(hits, 3)
                if kw in head:
                    score += 3
        if score:
            scores[dt.code] = score
    if not scores:
        return None, 0.0
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_code, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = (best - second) / best
    confidence = 0.5 + 0.5 * margin if best >= 3 else 0.35 * margin
    return best_code, round(min(confidence, 0.99), 2)


def guess_from_filename(filename: str, doc_types: list[DocumentType]) -> str | None:
    name = re.sub(r"[^a-z0-9]+", " ", filename.lower())
    for dt in doc_types:
        for hint in dt.filename_hints:
            if re.search(r"\b" + re.escape(hint.lower()), name):
                return dt.code
    return None
