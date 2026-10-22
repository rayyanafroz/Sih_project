from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import serializers as S
from ..auth import require
from ..db import get_db
from ..models import Application, Document, User, Verification
from ..services.app_settings import reference_date
from ..services.prescrutiny import revalidate
from ..services.status import latest_run
from ..verification.engine import refresh_verification

router = APIRouter(prefix="/verifications", tags=["verification"])


@router.post("/{verification_id}/refresh")
def refresh(verification_id: int, db: Session = Depends(get_db), user: User = Depends(require("verification:run"))):
    v = db.get(Verification, verification_id)
    if not v:
        raise HTTPException(404, "Verification not found")
    app = db.get(Application, v.application_id)
    if app.status == "PROCESSING":
        raise HTTPException(409, "Pre-scrutiny is running for this application. Try again when it finishes.")
    doc = db.get(Document, v.document_id)
    refresh_verification(db, v, doc, reference_date(db), user)
    db.commit()
    if latest_run(db, app.id, completed_only=True) and not app.outcome:
        revalidate(db, app, user)
    return S.verification(v)
