"""Deterministic field extraction with evidence (page + bounding box) for every value.

Labelled fields ("Reference No.: NOC-28492") and programme/intake table rows are recognised from
reconstructed visual lines, so the same templates work on text-layer PDFs and OCR output.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime

from .text import DocumentText, Line

DATE_RE = r"(\d{1,2}(?:st|nd|rd|th)?[\s\-/\.]+(?:\d{1,2}|[A-Za-z]{3,9})[\s\-/\.,]+\d{4}|\d{4}-\d{2}-\d{2})"
SEP = r"\s*[:\-–]\s*"

LABELLED_FIELDS: dict[str, tuple[str, str]] = {
    # field: (regex with group v, kind)
    "reference_number": (
        r"\b(?:Transaction\s+Ref(?:erence)?|Approval\s+Ref(?:erence)?|Reference|Ref\.?|Certificate|Receipt)"
        r"\s*(?:No\.?|Number)?" + SEP + r"(?P<v>[A-Z0-9][A-Z0-9/\-]{3,})", "id"),
    "institution_name": (
        r"\b(?:Name\s+of\s+(?:the\s+)?Institut(?:ion|e)|Institution\s+Name)" + SEP + r"(?P<v>.+?)\s*$", "text"),
    "aicte_id": (r"\b(?:AICTE\s+)?Permanent\s+ID" + SEP + r"(?P<v>\d[\d\-]{5,})", "id"),
    "issue_date": (r"\b(?:Date\s+of\s+Issue|Issue\s+Date|Issued\s+on|Date\s+of\s+Payment|Payment\s+Date)"
                   + SEP + DATE_RE.replace("(", "(?P<v>", 1), "date"),
    "valid_from": (r"\bValid\s+From" + SEP + DATE_RE.replace("(", "(?P<v>", 1), "date"),
    "expiry_date": (r"\b(?:Valid\s+(?:Until|Till|Upto|up\s+to)|Expiry\s+Date|Date\s+of\s+Expiry)"
                    + SEP + DATE_RE.replace("(", "(?P<v>", 1), "date"),
    "issuer": (r"\b(?:Issued\s+by|Issuing\s+Authority)" + SEP + r"(?P<v>.+?)\s*$", "text"),
    "amount": (r"\bAmount(?:\s+Paid)?" + SEP + r"(?:Rs\.?|INR)?\s*(?P<v>\d[\d,]*(?:\.\d{1,2})?)", "number"),
    "built_up_area": (r"\bBuilt[\s\-]?up\s+Area" + SEP + r"(?P<v>\d[\d,]*(?:\.\d+)?)", "number"),
    "academic_year": (r"\bAcademic\s+Year" + SEP + r"(?P<v>\d{4}\s*[-–]\s*\d{2,4})", "text"),
}

PROGRAMME_RE = re.compile(
    r"^(?:\d{1,2}\.?\s+)?(?P<prog>(?:B\.?\s?Tech|M\.?\s?Tech|B\.?\s?E\b|MBA|MCA|PGDM|B\.?\s?Arch|B\.?\s?Pharm|Diploma)"
    r"\b.*?)\s+(?P<v>\d{2,4})\s*$", re.IGNORECASE)
PROGRAMME_DOC_TYPES = {"PROGRAMME_DETAILS", "PREVIOUS_EOA", "INTAKE_INCREASE_APPROVAL"}

_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %m %Y")


@dataclass
class Extracted:
    field: str
    value: str
    normalized: str | None
    page: int
    bbox: list[float]
    confidence: float
    method: str


def parse_date(raw: str) -> date | None:
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw.strip())
    s = re.sub(r"[,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def normalize_id(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def normalize_name(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", raw.lower())).strip()


def programme_key(raw: str) -> str:
    s = normalize_name(raw)
    s = re.sub(r"\bb\s?tech\b", "btech", s)
    s = re.sub(r"\bm\s?tech\b", "mtech", s)
    s = re.sub(r"\b(programme|program|course)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _normalize(kind: str, value: str) -> str | None:
    if kind == "date":
        d = parse_date(value)
        return d.isoformat() if d else None
    if kind == "number":
        try:
            num = float(value.replace(",", ""))
            return str(int(num)) if num.is_integer() else str(num)
        except ValueError:
            return None
    if kind == "id":
        return normalize_id(value)
    return normalize_name(value) or None


def _span_bbox(line: Line, start: int, end: int) -> tuple[list[float], float]:
    """Union bbox and mean OCR confidence of the words covering text[start:end] of the line."""
    pos, boxes, confs = 0, [], []
    for w in line.words:
        w_start, w_end = pos, pos + len(w.text)
        if w_end > start and w_start < end:
            boxes.append(w)
            confs.append(w.conf)
        pos = w_end + 1
    if not boxes:
        boxes = line.words
        confs = [w.conf for w in boxes]
    bbox = [min(w.x0 for w in boxes), min(w.y0 for w in boxes), max(w.x1 for w in boxes), max(w.y1 for w in boxes)]
    return [round(v, 1) for v in bbox], sum(confs) / len(confs)


def extract_fields(doc_text: DocumentText, doc_type: str | None) -> list[Extracted]:
    found: dict[str, Extracted] = {}
    for page in doc_text.pages:
        is_ocr = page.method == "ocr"
        method = "ocr+regex" if is_ocr else "regex"
        for line in page.lines:
            text = line.text
            for name, (pattern, kind) in LABELLED_FIELDS.items():
                if name in found:
                    continue
                m = re.search(pattern, text, re.IGNORECASE)
                if not m:
                    continue
                value = m.group("v").strip().rstrip(".,;")
                if not value:
                    continue
                normalized = _normalize(kind, value)
                bbox, conf = _span_bbox(line, m.start(), m.end())
                base = conf / 100 if is_ocr else 0.97
                found[name] = Extracted(name, value, normalized, page.page_no, bbox,
                                        round(base * (1.0 if normalized else 0.7), 2), method)
            if doc_type in PROGRAMME_DOC_TYPES:
                m = PROGRAMME_RE.match(text)
                if m:
                    prog = re.sub(r"\s+", " ", m.group("prog")).strip(" -–|")
                    key = "intake:" + programme_key(prog)
                    if key not in found:
                        bbox, conf = _span_bbox(line, 0, len(text))
                        base = conf / 100 if is_ocr else 0.97
                        found[key] = Extracted(key, m.group("v"), m.group("v"), page.page_no, bbox,
                                               round(base, 2), method)
                        found[key].value = f"{prog}: {m.group('v')}"
    return list(found.values())
