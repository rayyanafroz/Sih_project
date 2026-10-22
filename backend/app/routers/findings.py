from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..auth import require
from ..db import get_db, utcnow
from ..models import Application, Document, Finding, FindingAction, User
from ..schemas import FindingActionIn
from ..services.status import recompute_status

router = APIRouter(prefix="/findings", tags=["findings"])

TRANSITIONS = {
    "request_clarification": "CLARIFICATION_REQUESTED",
    "mark_reviewed": "REVIEWED",
    "escalate": "ESCALATED",
    "reopen": "OPEN",
}
LABELS = {"request_clarification": "Requested clarification", "mark_reviewed": "Marked reviewed",
          "escalate": "Escalated", "reopen": "Re-opened"}


@router.get("/{finding_id}")
def get_finding(finding_id: int, db: Session = Depends(get_db), user: User = Depends(require("application:view"))):
    f = db.get(Finding, finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    out = S.finding(f, with_actions=True)
    doc = db.get(Document, f.source_document_id) if f.source_document_id else None
    out["source_document"] = {"id": doc.id, "filename": doc.filename, "page_count": doc.page_count,
                              "mime": doc.mime} if doc else None
    audit.log(db, "finding.viewed", f"Officer opened finding: {f.title}", actor=user, entity_type="finding",
              entity_id=f.id, application_id=f.application_id)
    db.commit()
    return out


@router.post("/{finding_id}/actions")
def act(finding_id: int, body: FindingActionIn, db: Session = Depends(get_db),
        user: User = Depends(require("finding:act"))):
    f = db.get(Finding, finding_id)
    if not f:
        raise HTTPException(404, "Finding not found")
    app = db.get(Application, f.application_id)
    if app.outcome:
        raise HTTPException(409, "An outcome has been recorded for this application.")
    if f.status == "AUTO_CLEARED":
        raise HTTPException(409, "This finding was cleared by a later pre-scrutiny run.")
    if body.action != "reopen" and len(body.note) < 3:
        raise HTTPException(400, "Please add a short note explaining the action.")
    f.status = TRANSITIONS[body.action]
    f.updated_at = utcnow()
    if body.action == "mark_reviewed":
        f.resolved_at, f.resolved_by, f.resolution_note = utcnow(), user.id, body.note
    elif body.action == "reopen":
        f.resolved_at = f.resolved_by = f.resolution_note = None
    db.add(FindingAction(finding_id=f.id, actor_id=user.id, actor_name=user.name, action=body.action, note=body.note))
    audit.log(db, f"finding.{body.action}", f"{LABELS[body.action]}: {f.title}", actor=user, entity_type="finding",
              entity_id=f.id, application_id=f.application_id, details={"note": body.note, "status": f.status})
    recompute_status(db, app)
    db.commit()
    db.refresh(f)
    return S.finding(f, with_actions=True)
