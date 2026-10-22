from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..auth import require
from ..db import get_db
from ..models import Application, AuditLog, Document, Finding, User
from ..verification.engine import latest_verification

router = APIRouter(tags=["dashboard"])
SEV_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
ALERT_TYPES = {"MISSING_DOCUMENT": "Missing document", "EXPIRED_DOCUMENT": "Expiry", "ANOMALY": "Potential anomaly",
               "VERIFICATION": "Verification", "REGULATORY": "Regulatory", "CONSISTENCY": "Inconsistency",
               "INFRASTRUCTURE": "Infrastructure"}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    apps = db.scalars(select(Application).order_by(Application.code.desc())).all()
    open_findings = db.scalars(select(Finding).where(Finding.status.in_(("OPEN", "CLARIFICATION_REQUESTED",
                                                                          "ESCALATED")))).all()
    codes = {a.id: a.code for a in apps}

    pending_verifs = []
    for d in db.scalars(select(Document).where(Document.status == "PROCESSED")):
        v = latest_verification(db, d.id)
        if v and v.status in ("PENDING", "SOURCE_UNAVAILABLE", "MANUAL_REVIEW"):
            pending_verifs.append((d, v))

    alerts = []
    for f in sorted(open_findings, key=lambda f: (SEV_ORDER[f.severity], f.created_at)):
        if f.finding_type == "VERIFICATION":
            continue  # represented by the pending-verification alerts below
        alerts.append({"severity": f.severity, "kind": ALERT_TYPES.get(f.finding_type, f.finding_type),
                       "message": f.title, "application_id": f.application_id,
                       "application_code": codes.get(f.application_id), "finding_id": f.id, "at": S.iso(f.created_at)})
    for d, v in pending_verifs:
        alerts.append({"severity": "INFO" if v.status == "PENDING" else "WARNING", "kind": "Verification",
                       "message": f"{d.filename}: {v.status.replace('_', ' ').lower()} — {v.source_name}",
                       "application_id": d.application_id, "application_code": codes.get(d.application_id),
                       "finding_id": None, "at": S.iso(v.requested_at)})
    alerts.sort(key=lambda a: SEV_ORDER[a["severity"]])

    activity = db.scalars(select(AuditLog).where(AuditLog.action.notin_(("auth.login", "auth.login_failed")))
                          .order_by(AuditLog.id.desc()).limit(10)).all()
    return {
        "metrics": {
            "applications": len(apps),
            "needs_review": sum(1 for a in apps if a.status in ("NEEDS_REVIEW", "CLARIFICATION_REQUESTED")),
            "critical_findings": sum(1 for f in open_findings if f.severity == "CRITICAL"),
            "verification_pending": len(pending_verifs),
            "ready_for_decision": sum(1 for a in apps if a.status == "READY_FOR_DECISION"),
        },
        "applications": [S.application(db, a) for a in apps],
        "alerts": alerts[:15],
        "alert_count": len(alerts),
        "activity": [S.audit_entry(e) | {"application_code": codes.get(e.application_id)} for e in activity],
    }
