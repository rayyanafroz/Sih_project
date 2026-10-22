"""Text acquisition: PDF text layer via PyMuPDF, falling back to Tesseract OCR for scans/images.

Every word keeps its coordinates so extracted values can be traced back to a page region.
Coordinates are in PDF points for PDFs and in pixels for images (matching how pages are rendered).
"""
import io
from dataclasses import dataclass, field
from functools import lru_cache

import pymupdf as fitz
from PIL import Image, ImageOps

from ..config import tesseract_cmd

OCR_DPI = 300
MIN_TEXT_CHARS = 25


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    conf: float = 100.0


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class PageText:
    page_no: int
    width: float
    height: float
    method: str  # text | ocr | none
    words: list[Word] = field(default_factory=list)
    ocr_confidence: float | None = None
    lines: list[Line] = field(default_factory=list)

    def __post_init__(self):
        self.lines = group_lines(self.words)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class DocumentText:
    pages: list[PageText]
    metadata: dict

    @property
    def method(self) -> str:
        methods = {p.method for p in self.pages if p.method != "none"}
        if not methods:
            return "none"
        return methods.pop() if len(methods) == 1 else "mixed"

    @property
    def ocr_confidence(self) -> float | None:
        vals = [p.ocr_confidence for p in self.pages if p.ocr_confidence is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


def group_lines(words: list[Word]) -> list[Line]:
    """Group words into visual lines by vertical overlap. Table cells on one row end up in one line."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0)):
        yc = (w.y0 + w.y1) / 2
        if lines:
            cur = lines[-1]
            top = min(x.y0 for x in cur)
            bottom = max(x.y1 for x in cur)
            if top <= yc <= bottom:
                cur.append(w)
                continue
        lines.append([w])
    return [Line(sorted(ws, key=lambda w: w.x0)) for ws in lines]


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    cmd = tesseract_cmd()
    if not cmd:
        return False
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_image(img: Image.Image, scale: float = 1.0) -> tuple[list[Word], float | None]:
    """OCR an image. `scale` converts pixel coordinates back to the page coordinate system."""
    import pytesseract
    gray = ImageOps.grayscale(img)
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config="--psm 6")
    words, confs = [], []
    for i, txt in enumerate(data["text"]):
        txt = (txt or "").strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(x / scale, y / scale, (x + w) / scale, (y + h) / scale, txt, conf))
        confs.append(conf)
    return words, (round(sum(confs) / len(confs), 1) if confs else None)


def read_pdf(data: bytes) -> DocumentText:
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        raw = page.get_text("words")
        words = [Word(w[0], w[1], w[2], w[3], w[4]) for w in raw if w[4].strip()]
        text_len = sum(len(w.text) for w in words)
        if text_len >= MIN_TEXT_CHARS:
            pages.append(PageText(i + 1, page.rect.width, page.rect.height, "text", words))
        elif ocr_available():
            zoom = OCR_DPI / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_words, conf = _ocr_image(img, scale=zoom)
            pages.append(PageText(i + 1, page.rect.width, page.rect.height, "ocr", ocr_words, conf))
        else:
            pages.append(PageText(i + 1, page.rect.width, page.rect.height, "none", words))
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    doc.close()
    return DocumentText(pages, meta)


def read_image(data: bytes) -> DocumentText:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    width, height = img.size
    meta = {"format": img.format or "", "size": f"{width}x{height}"}
    if not ocr_available():
        return DocumentText([PageText(1, width, height, "none")], meta)
    words, conf = _ocr_image(img)
    # Photos often contain little or no text; whatever was read is kept.
    return DocumentText([PageText(1, width, height, "ocr", words, conf)], meta)


def read_document(data: bytes, mime: str) -> DocumentText:
    if mime == "application/pdf":
        return read_pdf(data)
    return read_image(data)
