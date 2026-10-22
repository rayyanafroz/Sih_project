from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import serializers as S
from ..auth import require
from ..db import get_db
from ..models import Application, AuditLog, User

router = APIRouter(tags=["audit"])


@router.get("/audit")
def global_audit(limit: int = 300, action: str = "", db: Session = Depends(get_db),
                 _: User = Depends(require("audit:view_all"))):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 2000))
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    codes = {a.id: a.code for a in db.scalars(select(Application))}
    return [S.audit_entry(e) | {"application_code": codes.get(e.application_id)} for e in db.scalars(q)]
