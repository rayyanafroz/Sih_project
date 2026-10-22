import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..auth import require
from ..config import settings
from ..db import get_db, utcnow
from ..models import (Application, AuditLog, Document, Finding, Institution, RuleResult, User, ValidationRun,
                      Verification)
from ..schemas import ApplicationIn, OutcomeIn
from ..services.documents import active_documents, save_upload
from ..services.prescrutiny import execute_run, start_run
from ..services.status import latest_run, recompute_status
from ..verification.engine import latest_verification

router = APIRouter(prefix="/applications", tags=["applications"])
SEV_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
STATUS_ORDER = {"OPEN": 0, "ESCALATED": 1, "CLARIFICATION_REQUESTED": 2, "REVIEWED": 3, "AUTO_CLEARED": 4}


def get_app(db: Session, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    return app


def _ensure_editable(app: Application):
    if app.status == "PROCESSING":
        raise HTTPException(409, "Pre-scrutiny is running for this application. Try again when it finishes.")


@router.get("")
def list_applications(q: str = "", status: str = "", db: Session = Depends(get_db),
                      _: User = Depends(require("application:view"))):
    apps = db.scalars(select(Application).order_by(Application.code.desc())).all()
    if q:
        ql = q.lower()
        apps = [a for a in apps if ql in a.code.lower() or ql in a.institution.name.lower()
                or ql in a.institution.aicte_id.lower()]
    if status:
        apps = [a for a in apps if a.status == status]
    return [S.application(db, a) for a in apps]


@router.post("")
def create_application(body: ApplicationIn, db: Session = Depends(get_db),
                       user: User = Depends(require("application:create"))):
    inst = db.get(Institution, body.institution_id)
    if not inst:
        raise HTTPException(400, "Unknown institution")
    prefix = {"EOA": "EoA"}.get(body.category, body.category.title().replace("_", ""))
    year = body.academic_year[:4]
    codes = db.scalars(select(Application.code).where(Application.code.like(f"%-{year}-%"))).all()
    nums = [int(c.rsplit("-", 1)[1]) for c in codes if c.rsplit("-", 1)[1].isdigit()]
    code = f"{prefix}-{year}-{(max(nums) + 1) if nums else 4801}"
    app = Application(code=code, institution_id=inst.id, category=body.category, academic_year=body.academic_year,
                      created_by=user.id, form_data={
                          "institution_name": body.institution_name or inst.name,
                          "address": body.address or inst.address,
                          "programmes": [p.model_dump() for p in body.programmes],
                          "built_up_area_sqm": body.built_up_area_sqm,
                      })
    db.add(app)
    db.flush()
    audit.log(db, "application.created", f"Application {code} created for {inst.name}", actor=user,
              entity_type="application", entity_id=app.id, application_id=app.id)
    recompute_status(db, app)
    db.commit()
    return S.application(db, app, detail=True)


@router.get("/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    return S.application(db, get_app(db, app_id), detail=True)


# ── Documents ──

@router.get("/{app_id}/documents")
def list_documents(app_id: int, include_inactive: bool = False, db: Session = Depends(get_db),
                   _: User = Depends(require("application:view"))):
    get_app(db, app_id)
    if include_inactive:
        docs = db.scalars(select(Document).where(Document.application_id == app_id).order_by(Document.id)).all()
    else:
        docs = active_documents(db, app_id)
    return [S.document(db, d) for d in docs]


@router.post("/{app_id}/documents")
async def upload_documents(app_id: int, files: list[UploadFile] = File(...), declared_types: list[str] = Form([]),
                           db: Session = Depends(get_db), user: User = Depends(require("document:upload"))):
    app = get_app(db, app_id)
    _ensure_editable(app)
    if app.outcome:
        raise HTTPException(409, "An outcome has been recorded; documents can no longer be added.")
    payloads = [(f.filename or "file", await f.read()) for f in files]
    docs = []
    for i, (name, data) in enumerate(payloads):
        declared = declared_types[i] if i < len(declared_types) and declared_types[i] else None
        docs.append(save_upload(db, app, name, data, declared, user))
    recompute_status(db, app)
    db.commit()
    return [S.document(db, d) for d in docs]


@router.post("/{app_id}/demo-documents")
def load_demo_documents(app_id: int, db: Session = Depends(get_db), user: User = Depends(require("document:upload"))):
    """Demo shortcut: attach the synthetic demo documents for this application (same path as a real upload)."""
    if not settings.demo_mode:
        raise HTTPException(404, "Not available")
    app = get_app(db, app_id)
    _ensure_editable(app)
    folder = settings.demo_data_dir / app.code
    manifest = folder / "manifest.json"
    if not manifest.exists():
        raise HTTPException(404, f"No synthetic demo documents exist for {app.code}")
    existing = {d.filename for d in active_documents(db, app.id)}
    added = []
    for item in json.loads(manifest.read_text()):
        if item["filename"] in existing:
            continue
        data = (folder / item["filename"]).read_bytes()
        added.append(save_upload(db, app, item["filename"], data, item.get("declared_type"), user))
    recompute_status(db, app)
    db.commit()
    return [S.document(db, d) for d in added]


# ── Pre-scrutiny ──

@router.post("/{app_id}/prescrutiny")
def run_prescrutiny(app_id: int, background: BackgroundTasks, db: Session = Depends(get_db),
                    user: User = Depends(require("prescrutiny:run"))):
    app = get_app(db, app_id)
    if app.outcome:
        raise HTTPException(409, "An outcome has been recorded for this application.")
    if not active_documents(db, app.id):
        raise HTTPException(400, "Upload documents before running pre-scrutiny.")
    existing = latest_run(db, app.id)
    run = start_run(db, app, user)
    if not (existing and existing.id == run.id):
        background.add_task(execute_run, run.id)
    return S.run(run)


@router.get("/{app_id}/runs")
def list_runs(app_id: int, db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    runs = db.scalars(select(ValidationRun).where(ValidationRun.application_id == app_id)
                      .order_by(ValidationRun.id.desc())).all()
    return [S.run(r) for r in runs]


# ── Findings / compliance / verification / audit ──

@router.get("/{app_id}/findings")
def list_findings(app_id: int, include_cleared: bool = True, db: Session = Depends(get_db),
                  _: User = Depends(require("application:view"))):
    get_app(db, app_id)
    fs = db.scalars(select(Finding).where(Finding.application_id == app_id)).all()
    if not include_cleared:
        fs = [f for f in fs if f.status != "AUTO_CLEARED"]
    fs.sort(key=lambda f: (STATUS_ORDER.get(f.status, 9), SEV_ORDER[f.severity], f.id))
    return [S.finding(f) for f in fs]


@router.get("/{app_id}/compliance")
def compliance(app_id: int, db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    get_app(db, app_id)
    run = latest_run(db, app_id, completed_only=True)
    if not run:
        return {"run": None, "results": []}
    results = db.scalars(select(RuleResult).where(RuleResult.run_id == run.id).order_by(RuleResult.rule_id)).all()
    return {"run": S.run(run), "results": [
        {"rule_id": r.rule_id, "rule_version": r.rule_version, "rule_name": r.rule_name, "group": r.group,
         "severity": r.severity, "outcome": r.outcome, "message": r.message, "finding_ids": r.finding_ids,
         "evidence": r.evidence, "evaluated_at": S.iso(r.evaluated_at)} for r in results]}


@router.get("/{app_id}/verifications")
def verifications(app_id: int, db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    get_app(db, app_id)
    out = []
    for d in active_documents(db, app_id):
        history = db.scalars(select(Verification).where(Verification.document_id == d.id)
                             .order_by(Verification.id.desc())).all()
        out.append({"document": S.document(db, d), "latest": S.verification(history[0]) if history else None,
                    "history": [S.verification(v) for v in history]})
    return out


@router.get("/{app_id}/audit")
def application_audit(app_id: int, db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    get_app(db, app_id)
    rows = db.scalars(select(AuditLog).where(AuditLog.application_id == app_id).order_by(AuditLog.id)).all()
    return [S.audit_entry(e) for e in rows]


# ── Officer outcome (human decision) ──

@router.post("/{app_id}/outcome")
def record_outcome(app_id: int, body: OutcomeIn, db: Session = Depends(get_db),
                   user: User = Depends(require("outcome:record"))):
    app = get_app(db, app_id)
    _ensure_editable(app)
    if not latest_run(db, app.id, completed_only=True):
        raise HTTPException(400, "Run pre-scrutiny before recording an outcome.")
    open_critical = db.scalars(select(Finding).where(
        Finding.application_id == app.id, Finding.severity == "CRITICAL",
        Finding.status.in_(("OPEN", "CLARIFICATION_REQUESTED", "ESCALATED")))).all()
    if open_critical and body.outcome == "RECOMMEND_APPROVAL" and not body.acknowledge_open_findings:
        raise HTTPException(400, f"{len(open_critical)} critical finding(s) are still open. Review them, or "
                                 f"explicitly acknowledge them to record this outcome.")
    previous = app.outcome
    app.outcome, app.outcome_note, app.outcome_by, app.outcome_at = body.outcome, body.note, user.id, utcnow()
    audit.log(db, "outcome.revised" if previous else "outcome.recorded",
              f"Officer recorded outcome: {body.outcome.replace('_', ' ').title()}", actor=user,
              entity_type="application", entity_id=app.id, application_id=app.id,
              details={"outcome": body.outcome, "previous": previous, "note": body.note,
                       "open_critical_acknowledged": len(open_critical) if body.acknowledge_open_findings else 0})
    recompute_status(db, app)
    db.commit()
    return S.application(db, app, detail=True)


@router.get("/{app_id}/report")
def report(app_id: int, db: Session = Depends(get_db), user: User = Depends(require("application:view"))):
    """Structured validation report (printable in the UI, downloadable as JSON)."""
    app = get_app(db, app_id)
    audit.log(db, "report.generated", "Validation report generated", actor=user, entity_type="application",
              entity_id=app.id, application_id=app.id)
    db.commit()
    return {
        "generated_at": S.iso(utcnow()),
        "generated_by": S.user(user),
        "disclaimer": "AI-assisted pre-scrutiny output. Advisory only — statutory scrutiny, inspection and final "
                      "decisions rest with the competent AICTE authority.",
        "application": S.application(db, app, detail=True),
        "documents": [S.document(db, d, with_fields=True) for d in active_documents(db, app.id)],
        "compliance": compliance(app_id, db, user),
        "findings": list_findings(app_id, True, db, user),
        "verifications": [S.verification(latest_verification(db, d.id)) for d in active_documents(db, app.id)
                          if latest_verification(db, d.id)],
    }
