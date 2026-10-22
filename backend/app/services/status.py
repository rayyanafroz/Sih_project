from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Finding, ValidationRun
from .documents import active_documents

STATUS_LABELS = {
    "DRAFT": "Draft",
    "SUBMITTED": "Awaiting pre-scrutiny",
    "PROCESSING": "Pre-scrutiny running",
    "NEEDS_REVIEW": "Needs review",
    "CLARIFICATION_REQUESTED": "Clarification requested",
    "READY_FOR_DECISION": "Ready for officer decision",
    "DECIDED": "Outcome recorded",
}


def latest_run(db: Session, app_id: int, completed_only: bool = False) -> ValidationRun | None:
    q = select(ValidationRun).where(ValidationRun.application_id == app_id)
    if completed_only:
        q = q.where(ValidationRun.status == "COMPLETED")
    return db.scalars(q.order_by(ValidationRun.id.desc())).first()


def recompute_status(db: Session, app: Application) -> str:
    """Status is derived from facts (runs, findings, outcome) — never set by the AI."""
    if app.outcome:
        status = "DECIDED"
    else:
        last = latest_run(db, app.id)
        if last and last.status == "RUNNING":
            status = "PROCESSING"
        elif not latest_run(db, app.id, completed_only=True):
            status = "SUBMITTED" if active_documents(db, app.id) else "DRAFT"
        else:
            open_statuses = db.scalars(select(Finding.status).where(
                Finding.application_id == app.id, Finding.status.in_(("OPEN", "CLARIFICATION_REQUESTED", "ESCALATED")))).all()
            if "CLARIFICATION_REQUESTED" in open_statuses:
                status = "CLARIFICATION_REQUESTED"
            elif open_statuses:
                status = "NEEDS_REVIEW"
            else:
                status = "READY_FOR_DECISION"
    app.status = status
    return status
