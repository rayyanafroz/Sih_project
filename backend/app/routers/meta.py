from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ROLE_LABELS, current_user
from ..db import get_db
from ..engines.registry import CHECKS
from ..models import DocumentType, Institution, User, VerificationSource
from ..pipeline.text import ocr_available
from ..services.app_settings import all_settings, reference_date
from ..services.status import STATUS_LABELS

router = APIRouter(tags=["meta"])


@router.get("/meta")
def meta(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {
        "document_types": [{"code": t.code, "label": t.label, "has_expiry": t.has_expiry,
                            "keywords": t.keywords, "filename_hints": t.filename_hints}
                           for t in db.scalars(select(DocumentType).order_by(DocumentType.label))],
        "checks": [{"name": c.name, "label": c.label, "description": c.description,
                    "params": [vars(p) for p in c.params]} for c in CHECKS.values()],
        "settings": all_settings(db),
        "effective_reference_date": reference_date(db).isoformat(),
        "status_labels": STATUS_LABELS,
        "role_labels": ROLE_LABELS,
        "ocr_available": ocr_available(),
        "sources": [{"id": s.id, "key": s.key, "name": s.name, "doc_types": s.doc_types, "method": s.method,
                     "mode": s.mode, "is_mock": s.is_mock} for s in db.scalars(select(VerificationSource))],
    }


@router.get("/institutions")
def institutions(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": i.id, "aicte_id": i.aicte_id, "name": i.name, "address": i.address, "state": i.state}
            for i in db.scalars(select(Institution).order_by(Institution.name))]


@router.get("/health", include_in_schema=False)
def health():
    return {"ok": True, "ocr_available": ocr_available()}
