from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import ROLE_LABELS, permissions_for
from .config import settings
from .engines.registry import CHECKS
from .models import (Application, AuditLog, Document, ExtractedField, Finding, FindingAction, Rule, RuleVersion,
                     User, ValidationRun, Verification)
from .services.app_settings import category_label
from .services.documents import active_documents
from .services.prescrutiny import STEPS
from .services.status import STATUS_LABELS, latest_run
from .verification.engine import latest_verification


def iso(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
    if isinstance(v, date):
        return v.isoformat()
    return v


def user(u: User | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "role_label": ROLE_LABELS[u.role],
            "permissions": permissions_for(u.role)}


def field(f: ExtractedField) -> dict:
    return {"id": f.id, "field": f.field, "value": f.value, "normalized_value": f.normalized_value, "page": f.page,
            "bbox": f.bbox, "confidence": f.confidence, "method": f.method}


def verification(v: Verification | None) -> dict | None:
    if not v:
        return None
    return {"id": v.id, "document_id": v.document_id, "application_id": v.application_id, "source_key": v.source_key,
            "source_name": v.source_name, "is_mock": v.is_mock, "method": v.method, "query": v.query,
            "status": v.status, "response": v.response, "comparison": v.comparison, "message": v.message,
            "requested_by": v.requested_by_name, "requested_at": iso(v.requested_at),
            "responded_at": iso(v.responded_at)}


def document(db: Session, d: Document, with_fields: bool = False) -> dict:
    out = {"id": d.id, "application_id": d.application_id, "filename": d.filename, "declared_type": d.declared_type,
           "detected_type": d.detected_type, "effective_type": d.effective_type,
           "classification_confidence": d.classification_confidence, "mime": d.mime, "size": d.size,
           "sha256": d.sha256, "page_count": d.page_count, "text_method": d.text_method,
           "ocr_confidence": d.ocr_confidence, "status": d.status, "error": d.error, "metadata": d.pdf_metadata,
           "uploaded_at": iso(d.uploaded_at), "processed_at": iso(d.processed_at),
           "replaces_document_id": d.replaces_document_id, "field_count": len(d.fields),
           "verification": verification(latest_verification(db, d.id))}
    if with_fields:
        out["fields"] = [field(f) for f in sorted(d.fields, key=lambda f: (f.page or 0, f.field))]
        out["pages"] = [{"page_no": p.page_no, "width": p.width, "height": p.height, "method": p.method,
                         "ocr_confidence": p.ocr_confidence, "text": p.text} for p in d.pages]
    return out


def finding_action(a: FindingAction) -> dict:
    return {"id": a.id, "action": a.action, "note": a.note, "actor": a.actor_name, "at": iso(a.at)}


def finding(f: Finding, with_actions: bool = False) -> dict:
    out = {"id": f.id, "application_id": f.application_id, "finding_type": f.finding_type, "severity": f.severity,
           "status": f.status, "title": f.title, "description": f.description, "rule_id": f.rule_id,
           "rule_version": f.rule_version, "source_document_id": f.source_document_id, "source_page": f.source_page,
           "source_field": f.source_field, "evidence": f.evidence, "expected_value": f.expected_value,
           "actual_value": f.actual_value, "confidence": f.confidence, "recommended_action": f.recommended_action,
           "created_at": iso(f.created_at), "updated_at": iso(f.updated_at), "resolved_at": iso(f.resolved_at),
           "resolution_note": f.resolution_note, "run_id": f.run_id}
    if with_actions:
        out["actions"] = [finding_action(a) for a in f.actions]
    return out


def run(r: ValidationRun | None) -> dict | None:
    if not r:
        return None
    return {"id": r.id, "application_id": r.application_id, "mode": r.mode, "status": r.status,
            "step_index": r.step_index, "step_detail": r.step_detail, "steps": STEPS,
            "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
            "reference_date": iso(r.reference_date), "summary": r.summary, "error": r.error}


def application(db: Session, a: Application, detail: bool = False) -> dict:
    findings = db.scalars(select(Finding).where(Finding.application_id == a.id)).all()
    open_f = [f for f in findings if f.status in ("OPEN", "CLARIFICATION_REQUESTED", "ESCALATED")]
    out = {"id": a.id, "code": a.code, "category": a.category, "category_label": category_label(db, a.category),
           "academic_year": a.academic_year, "status": a.status, "status_label": STATUS_LABELS.get(a.status, a.status),
           "submitted_at": iso(a.submitted_at),
           "institution": {"id": a.institution.id, "name": a.institution.name, "aicte_id": a.institution.aicte_id,
                           "state": a.institution.state},
           "open_findings": len(open_f),
           "open_critical": sum(1 for f in open_f if f.severity == "CRITICAL"),
           "outcome": a.outcome, "outcome_note": a.outcome_note, "outcome_at": iso(a.outcome_at),
           "outcome_by": user(db.get(User, a.outcome_by)) if a.outcome_by else None}
    if not detail:
        return out
    docs = active_documents(db, a.id)
    last = latest_run(db, a.id)
    last_done = latest_run(db, a.id, completed_only=True)
    verifs = [v for v in (latest_verification(db, d.id) for d in docs) if v]
    summary = (last_done.summary if last_done else {}) or {}
    stale = bool(docs) and (not last_done or any(d.uploaded_at > last_done.started_at for d in docs))
    out.update({
        "form_data": a.form_data,
        "documents": {"total": len(docs), "processed": sum(1 for d in docs if d.status == "PROCESSED"),
                      "failed": sum(1 for d in docs if d.status == "FAILED")},
        "rules": {"passed": summary.get("rules_passed", 0), "evaluated": summary.get("rules_evaluated", 0)},
        "verification": {"verified": sum(1 for v in verifs if v.status == "VERIFIED"), "total": len(verifs),
                         "pending": sum(1 for v in verifs if v.status in ("PENDING", "SOURCE_UNAVAILABLE",
                                                                          "MANUAL_REVIEW"))},
        "findings": {"critical": sum(1 for f in open_f if f.severity == "CRITICAL"),
                     "warning": sum(1 for f in open_f if f.severity == "WARNING"),
                     "info": sum(1 for f in open_f if f.severity == "INFO"),
                     "open": len(open_f),
                     "reviewed": sum(1 for f in findings if f.status == "REVIEWED"),
                     "cleared": sum(1 for f in findings if f.status == "AUTO_CLEARED")},
        "last_run": run(last), "last_completed_run": run(last_done), "needs_rerun": stale,
        "demo_documents_available": settings.demo_mode and (settings.demo_data_dir / a.code / "manifest.json").exists(),
    })
    return out


def rule(db: Session, r: Rule, with_history: bool = False) -> dict:
    spec = CHECKS.get(r.check)
    out = {"id": r.id, "rule_id": r.rule_id, "name": r.name, "description": r.description, "group": r.group,
           "check": r.check, "check_label": spec.label if spec else r.check, "params": r.params,
           "param_specs": [vars(p) for p in spec.params] if spec else [], "severity": r.severity,
           "applies_to": r.applies_to, "enabled": r.enabled, "version": r.version,
           "source_reference": r.source_reference, "updated_at": iso(r.updated_at),
           "updated_by": user(db.get(User, r.updated_by))["name"] if r.updated_by else "system"}
    if with_history:
        out["history"] = [{"version": h.version, "snapshot": h.snapshot, "change_note": h.change_note,
                           "changed_by": h.changed_by_name, "changed_at": iso(h.changed_at)}
                          for h in db.scalars(select(RuleVersion).where(RuleVersion.rule_id == r.rule_id)
                                              .order_by(RuleVersion.version.desc()))]
    return out


def rule_snapshot(r: Rule) -> dict:
    return {"name": r.name, "description": r.description, "check": r.check, "params": r.params,
            "severity": r.severity, "applies_to": r.applies_to, "enabled": r.enabled,
            "source_reference": r.source_reference}


def audit_entry(e: AuditLog) -> dict:
    return {"id": e.id, "at": iso(e.at), "actor_type": e.actor_type, "actor": e.actor_name, "actor_role": e.actor_role,
            "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id,
            "application_id": e.application_id, "summary": e.summary, "details": e.details}
