"""Render a document page to PNG, optionally drawing evidence rectangles for the evidence viewer."""
import io

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageOps

HIGHLIGHT_RGB = (155, 63, 45)  # terracotta, matches the UI critical colour
RENDER_DPI = 110


def render_page(data: bytes, mime: str, page_no: int, boxes: list[list[float]]) -> bytes:
    if mime == "application/pdf":
        doc = fitz.open(stream=data, filetype="pdf")
        if not 1 <= page_no <= doc.page_count:
            raise ValueError("Page out of range")
        page = doc[page_no - 1]
        for b in boxes:
            rect = fitz.Rect(b[0] - 3, b[1] - 3, b[2] + 3, b[3] + 3)
            shape = page.new_shape()
            shape.draw_rect(rect)
            color = tuple(c / 255 for c in HIGHLIGHT_RGB)
            shape.finish(color=color, fill=color, fill_opacity=0.12, width=1.6)
            shape.commit()
        pix = page.get_pixmap(dpi=RENDER_DPI)
        png = pix.tobytes("png")
        doc.close()
        return png

    if page_no != 1:
        raise ValueError("Page out of range")
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    if boxes:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        pad = max(4, img.width // 300)
        for b in boxes:
            rect = [b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad]
            draw.rectangle(rect, fill=HIGHLIGHT_RGB + (32,), outline=HIGHLIGHT_RGB + (255,), width=max(2, pad // 2))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    img.thumbnail((1400, 1800))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()
