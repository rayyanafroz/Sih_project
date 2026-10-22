"""Verification through (mock) issuing-authority sources.

Each source sits behind the same interface: look up the submitted reference number, compare the
official record with what was extracted from the document, store source + method + timestamp + result.
Statuses: VERIFIED, MISMATCH, EXPIRED, PENDING, SOURCE_UNAVAILABLE, MANUAL_REVIEW.
"""
from datetime import date

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import utcnow
from ..models import Document, IssuerRecord, User, Verification, VerificationSource
from ..pipeline.extract import normalize_id, normalize_name

COMPARED_FIELDS = ("institution_name", "issue_date", "expiry_date", "built_up_area")
LABELS = {"institution_name": "Institution name", "issue_date": "Date of issue", "expiry_date": "Valid until",
          "built_up_area": "Built-up area (sq.m)"}


def source_for(db: Session, doc_type: str) -> VerificationSource | None:
    for src in db.scalars(select(VerificationSource)).all():
        if doc_type in src.doc_types:
            return src
    return None


def latest_verification(db: Session, document_id: int) -> Verification | None:
    return db.scalars(select(Verification).where(Verification.document_id == document_id)
                      .order_by(Verification.id.desc())).first()


def _fields(doc: Document) -> dict[str, str]:
    return {f.field: f.value if f.field == "institution_name" else (f.normalized_value or f.value) for f in doc.fields}


def _compare(submitted: dict, official: dict) -> list[dict]:
    rows = []
    for key in COMPARED_FIELDS:
        if key not in official or key not in submitted:
            continue
        s, o = str(submitted[key]), str(official[key])
        if key == "institution_name":
            match = fuzz.token_sort_ratio(normalize_name(s), normalize_name(o)) >= 90
        else:
            match = s == o
        rows.append({"field": key, "label": LABELS[key], "submitted": s, "official": o, "match": match})
    return rows


def _resolve(db: Session, v: Verification, src: VerificationSource, ref: str, submitted: dict, ref_date: date):
    """Query the mock registry and set status/response/comparison on the verification row."""
    record = db.scalars(select(IssuerRecord).where(IssuerRecord.source_key == src.key)).all()
    match = next((r for r in record if normalize_id(r.reference_number) == normalize_id(ref)), None)
    v.responded_at = utcnow()
    if not match:
        v.status = "MANUAL_REVIEW"
        v.response = {"found": False}
        v.message = f"No record for {ref} was returned by {src.name}. Routed for manual confirmation."
        return
    official = match.record
    v.response = {"found": True, "record": official}
    v.comparison = _compare(submitted, official)
    mismatches = [c for c in v.comparison if not c["match"]]
    expiry = official.get("expiry_date")
    if official.get("status") == "REVOKED":
        v.status, v.message = "MISMATCH", "Issuing authority lists this document as revoked. Manual verification required."
    elif mismatches:
        v.status = "MISMATCH"
        v.message = "Official record differs from the submitted document: " + "; ".join(
            f"{c['label']} submitted {c['submitted']} vs official {c['official']}" for c in mismatches) + \
            ". This may have an innocent explanation; manual verification required."
    elif official.get("status") == "EXPIRED" or (expiry and date.fromisoformat(expiry) < ref_date):
        v.status, v.message = "EXPIRED", f"Record found, but the issuing authority lists it as valid only until {expiry}."
    else:
        v.status, v.message = "VERIFIED", "Official record matches the submitted document."


def verify_document(db: Session, doc: Document, ref_date: date, actor: User | None = None) -> Verification:
    fields = _fields(doc)
    ref = next((f.value for f in doc.fields if f.field == "reference_number"), None)
    src = source_for(db, doc.effective_type)
    v = Verification(application_id=doc.application_id, document_id=doc.id,
                     requested_by=actor.id if actor else None,
                     requested_by_name=actor.name if actor else "VerifyAI system")
    if not src:
        v.source_name, v.method, v.is_mock = "No authorised source configured", "—", False
        v.status = "MANUAL_REVIEW"
        v.message = f"No authorised verification source is configured for {doc.effective_type}. Manual confirmation required."
    else:
        v.source_key, v.source_name, v.method, v.is_mock = src.key, src.name, src.method, src.is_mock
        v.query = {"reference_number": ref}
        if not ref:
            v.status = "MANUAL_REVIEW"
            v.message = "No reference number could be extracted from the document, so it cannot be looked up."
        elif src.mode == "OFFLINE":
            v.status = "SOURCE_UNAVAILABLE"
            v.message = f"{src.name} did not respond. Routed for manual confirmation."
        elif src.mode == "ASYNC":
            v.status = "PENDING"
            v.message = f"Request sent to {src.name}. Awaiting response from issuing authority."
        else:
            _resolve(db, v, src, ref, fields, ref_date)
    db.add(v)
    db.flush()
    audit.log(db, "verification.requested",
              f"{doc.filename}: verification via {v.source_name} — {v.status}", actor=actor,
              entity_type="verification", entity_id=v.id, application_id=doc.application_id,
              details={"reference": ref, "status": v.status, "is_mock": v.is_mock, "method": v.method})
    return v


def refresh_verification(db: Session, v: Verification, doc: Document, ref_date: date, actor: User) -> Verification:
    """Poll a PENDING request (async source) or retry an unavailable source."""
    if v.status not in ("PENDING", "SOURCE_UNAVAILABLE"):
        return v
    src = db.scalars(select(VerificationSource).where(VerificationSource.key == v.source_key)).first()
    if not src:
        return v
    if src.mode == "OFFLINE":
        v.message = f"{src.name} is still unavailable. Retry later or record a manual confirmation."
        v.responded_at = utcnow()
    else:
        _resolve(db, v, src, v.query.get("reference_number") or "", _fields(doc), ref_date)
    audit.log(db, "verification.refreshed", f"{doc.filename}: verification refreshed — {v.status}", actor=actor,
              entity_type="verification", entity_id=v.id, application_id=doc.application_id,
              details={"status": v.status})
    return v


def record_manual(db: Session, doc: Document, status: str, note: str, actor: User) -> Verification:
    v = Verification(application_id=doc.application_id, document_id=doc.id, source_name="Manual confirmation by officer",
                     is_mock=False, method="Manual confirmation", status=status, message=note,
                     requested_by=actor.id, requested_by_name=actor.name, responded_at=utcnow(),
                     response={"recorded_by": actor.name, "note": note})
    db.add(v)
    db.flush()
    audit.log(db, "verification.manual_recorded", f"{doc.filename}: manual verification recorded — {status}",
              actor=actor, entity_type="verification", entity_id=v.id, application_id=doc.application_id,
              details={"status": status, "note": note})
    return v
