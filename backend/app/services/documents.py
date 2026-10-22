import hashlib
import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..db import utcnow
from ..models import Application, Document, DocumentPage, DocumentType, ExtractedField, User
from ..pipeline.classify import classify, guess_from_filename
from ..pipeline.extract import extract_fields
from ..pipeline.text import read_document
from .app_settings import get_setting

MAGIC = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
EXT_MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def _safe_name(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", name)[:120] or "file"


def validate_file(db: Session, filename: str, data: bytes) -> str:
    """Return the MIME type or raise 400. Checks extension whitelist, size and magic bytes."""
    ext = Path(filename).suffix.lower().lstrip(".")
    allowed = get_setting(db, "allowed_extensions")
    if ext not in allowed or ext not in EXT_MIME:
        raise HTTPException(400, f"{filename}: file type .{ext or '?'} is not allowed (allowed: {', '.join(allowed)})")
    max_mb = get_setting(db, "max_upload_mb")
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"{filename}: file is larger than {max_mb} MB")
    if not data:
        raise HTTPException(400, f"{filename}: file is empty")
    mime = EXT_MIME[ext]
    if not any(data.startswith(sig) for sig in MAGIC[mime]):
        raise HTTPException(400, f"{filename}: content does not match a valid .{ext} file")
    return mime


def save_upload(db: Session, app: Application, filename: str, data: bytes, declared_type: str | None,
                user: User | None, replaces: Document | None = None) -> Document:
    mime = validate_file(db, filename, data)
    if declared_type and not db.get(DocumentType, declared_type):
        raise HTTPException(400, f"Unknown document type {declared_type}")
    sha = hashlib.sha256(data).hexdigest()
    folder = settings.storage_dir / app.code
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha[:16]}_{_safe_name(filename)}"
    path.write_bytes(data)
    doc = Document(
        application_id=app.id, filename=Path(filename).name, declared_type=declared_type or None, mime=mime,
        size=len(data), sha256=sha, storage_path=str(path), uploaded_by=user.id if user else None,
        replaces_document_id=replaces.id if replaces else None,
    )
    db.add(doc)
    db.flush()
    if replaces:
        replaces.status = "SUPERSEDED"
        audit.log(db, "document.replaced", f"{replaces.filename} replaced by {doc.filename}", actor=user,
                  entity_type="document", entity_id=doc.id, application_id=app.id,
                  details={"old_document_id": replaces.id, "sha256": sha})
    else:
        audit.log(db, "document.uploaded", f"Uploaded {doc.filename}", actor=user, entity_type="document",
                  entity_id=doc.id, application_id=app.id,
                  details={"sha256": sha, "size": len(data), "declared_type": declared_type})
    return doc


def read_file(doc: Document) -> bytes:
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(404, "Stored file is missing")
    return path.read_bytes()


def process_document(db: Session, doc: Document) -> Document:
    """Text/OCR → classification → field extraction. Safe to call again (re-processes)."""
    doc_types = db.scalars(select(DocumentType)).all()
    try:
        data = read_file(doc)
        if hashlib.sha256(data).hexdigest() != doc.sha256:
            raise ValueError("Stored file checksum does not match upload checksum")
        text = read_document(data, doc.mime)
        doc.pages.clear()
        doc.fields.clear()
        db.flush()
        for p in text.pages:
            doc.pages.append(DocumentPage(page_no=p.page_no, width=p.width, height=p.height, method=p.method,
                                          text=p.text, ocr_confidence=p.ocr_confidence))
        doc.page_count = len(text.pages)
        doc.text_method = text.method
        doc.ocr_confidence = text.ocr_confidence
        doc.pdf_metadata = text.metadata

        detected, conf = classify(text.full_text, doc_types)
        if not detected:
            detected = guess_from_filename(doc.filename, doc_types)
            conf = 0.5 if detected and not doc.declared_type else 0.3 if detected else 0.0
        doc.detected_type, doc.classification_confidence = detected, conf

        for ex in extract_fields(text, doc.effective_type):
            doc.fields.append(ExtractedField(field=ex.field, value=ex.value, normalized_value=ex.normalized,
                                             page=ex.page, bbox=ex.bbox, confidence=ex.confidence, method=ex.method))
        doc.status, doc.error = "PROCESSED", None
        doc.processed_at = utcnow()
        audit.log(db, "document.processed",
                  f"{doc.filename}: {text.method.upper()} read {doc.page_count} page(s), classified as "
                  f"{doc.effective_type}, {len(doc.fields)} field(s) extracted",
                  entity_type="document", entity_id=doc.id, application_id=doc.application_id,
                  details={"text_method": text.method, "ocr_confidence": doc.ocr_confidence,
                           "detected_type": detected, "classification_confidence": conf})
    except Exception as exc:  # a bad file must not break the whole run
        doc.status, doc.error = "FAILED", str(exc)
        audit.log(db, "document.processing_failed", f"{doc.filename}: processing failed — {exc}",
                  entity_type="document", entity_id=doc.id, application_id=doc.application_id)
    return doc


def active_documents(db: Session, application_id: int) -> list[Document]:
    return db.scalars(select(Document).where(Document.application_id == application_id,
                                             Document.status.in_(("UPLOADED", "PROCESSED", "FAILED")))
                      .order_by(Document.id)).all()
