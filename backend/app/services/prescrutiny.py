"""Pre-scrutiny orchestration: documents → records → verification → rules → findings."""
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..db import SessionLocal, utcnow
from ..engines.runner import evaluate_rules
from ..models import Application, Rule, User, ValidationRun, VerificationSource
from ..records.aicte import AicteRecords
from ..verification.engine import latest_verification, verify_document
from .app_settings import reference_date
from .documents import active_documents, process_document
from .status import recompute_status

STEPS = [
    "Validating uploaded files",
    "Reading documents (text layer / OCR)",
    "Classifying documents",
    "Extracting fields with evidence",
    "Retrieving AICTE institutional records",
    "Verifying with issuing authorities",
    "Applying configurable rules",
    "Generating evidence-linked findings",
]
RETRY_STATUSES = ("SOURCE_UNAVAILABLE", "MANUAL_REVIEW")


def start_run(db: Session, app: Application, actor: User | None, mode: str = "FULL") -> ValidationRun:
    running = db.scalars(select(ValidationRun).where(ValidationRun.application_id == app.id,
                                                     ValidationRun.status == "RUNNING")).first()
    if running:
        return running
    run = ValidationRun(application_id=app.id, triggered_by=actor.id if actor else None, mode=mode,
                        reference_date=reference_date(db), step_detail="Queued")
    db.add(run)
    db.flush()
    audit.log(db, "prescrutiny.started", f"AI pre-scrutiny started ({mode.lower().replace('_', ' ')})", actor=actor,
              entity_type="validation_run", entity_id=run.id, application_id=app.id,
              details={"reference_date": run.reference_date.isoformat()})
    recompute_status(db, app)
    db.commit()
    return run


def _step(db: Session, run: ValidationRun, index: int, detail: str, pause: bool = True):
    run.step_index, run.step_detail = index, detail
    db.commit()
    if pause and settings.step_delay:
        time.sleep(settings.step_delay)


def _verification_types(db: Session) -> set[str]:
    types = set()
    for rule in db.scalars(select(Rule).where(Rule.check == "source_verified", Rule.enabled.is_(True))):
        types.update((rule.params or {}).get("doc_types", []))
    return types


def execute_run(run_id: int) -> None:
    """Runs in a background thread with its own session."""
    db = SessionLocal()
    try:
        run = db.get(ValidationRun, run_id)
        app = db.get(Application, run.application_id)
        docs = active_documents(db, app.id)
        full = run.mode == "FULL"

        if full:
            _step(db, run, 0, f"{len(docs)} file(s) — checking checksums and formats")
            for i, d in enumerate(docs):
                _step(db, run, 1, f"Reading {d.filename} ({i + 1}/{len(docs)})", pause=False)
                process_document(db, d)
                db.commit()
            ocr = sum(1 for d in docs if d.text_method in ("ocr", "mixed"))
            _step(db, run, 1, f"{len(docs)} document(s) read, {ocr} via OCR")
            _step(db, run, 2, f"{len(docs)} document(s) classified")
            fields = sum(len(d.fields) for d in docs)
            _step(db, run, 3, f"{fields} field(s) extracted with page references")

            records = AicteRecords(db)
            progs = records.approved_programmes(app.institution_id)
            audit.log(db, "records.checked", f"Retrieved {len(progs)} approved-programme record(s) from {records.source_name}"
                      + (" (mock)" if records.is_mock else ""), entity_type="application", entity_id=app.id,
                      application_id=app.id)
            _step(db, run, 4, f"{len(progs)} approved-programme record(s) retrieved")

            needs = _verification_types(db)
            sources = {t for s in db.scalars(select(VerificationSource)) for t in s.doc_types}
            done = 0
            for d in docs:
                if d.status != "PROCESSED" or (d.effective_type not in needs and d.effective_type not in sources):
                    continue
                last = latest_verification(db, d.id)
                if last and (last.method == "Manual confirmation" or last.status not in RETRY_STATUSES):
                    continue
                verify_document(db, d, run.reference_date)
                done += 1
            _step(db, run, 5, f"{done} verification request(s) sent")

        _step(db, run, 6, "Evaluating rules", pause=full)
        summary = evaluate_rules(db, app, run)
        _step(db, run, 7, f"{summary['findings_critical'] + summary['findings_warning'] + summary['findings_info']} open finding(s)",
              pause=False)

        run.status, run.finished_at, run.summary = "COMPLETED", utcnow(), summary
        recompute_status(db, app)
        audit.log(db, "prescrutiny.completed",
                  f"Pre-scrutiny complete: {summary['rules_passed']}/{summary['rules_evaluated']} rules passed, "
                  f"{summary['findings_critical']} critical, {summary['findings_warning']} warning(s)",
                  entity_type="validation_run", entity_id=run.id, application_id=app.id, details=summary)
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(ValidationRun, run_id)
        if run:
            run.status, run.error, run.finished_at = "FAILED", str(exc), utcnow()
            audit.log(db, "prescrutiny.failed", f"Pre-scrutiny failed: {exc}", entity_type="validation_run",
                      entity_id=run.id, application_id=run.application_id)
            app = db.get(Application, run.application_id)
            recompute_status(db, app)
            db.commit()
    finally:
        db.close()


def revalidate(db: Session, app: Application, actor: User | None) -> ValidationRun:
    """Re-apply rules only (e.g. after a verification update). Synchronous and fast."""
    run = start_run(db, app, actor, mode="RULES_ONLY")
    if run.mode == "RULES_ONLY" and run.status == "RUNNING":
        execute_run(run.id)
    db.expire_all()
    return db.get(ValidationRun, run.id)


def fail_stale_runs() -> None:
    db = SessionLocal()
    try:
        for run in db.scalars(select(ValidationRun).where(ValidationRun.status == "RUNNING")):
            run.status, run.error, run.finished_at = "FAILED", "Interrupted by server restart", utcnow()
            recompute_status(db, db.get(Application, run.application_id))
        db.commit()
    finally:
        db.close()
