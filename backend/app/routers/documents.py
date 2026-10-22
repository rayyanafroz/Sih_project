from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..auth import require
from ..db import get_db
from ..models import Application, Document, ExtractedField, User
from ..pipeline.render import render_page
from ..schemas import ManualVerificationIn
from ..services.app_settings import reference_date
from ..services.documents import process_document, read_file, save_upload
from ..services.prescrutiny import revalidate
from ..services.status import latest_run, recompute_status
from ..verification.engine import record_manual, verify_document

router = APIRouter(prefix="/documents", tags=["documents"])


def get_doc(db: Session, doc_id: int) -> Document:
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    return d


def _editable(db: Session, d: Document) -> Application:
    app = db.get(Application, d.application_id)
    if app.status == "PROCESSING":
        raise HTTPException(409, "Pre-scrutiny is running for this application. Try again when it finishes.")
    if app.outcome:
        raise HTTPException(409, "An outcome has been recorded; documents can no longer be changed.")
    return app


def _revalidate_if_run(db: Session, app: Application, user: User):
    if latest_run(db, app.id, completed_only=True):
        revalidate(db, app, user)


@router.get("/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require("application:view"))):
    d = get_doc(db, doc_id)
    out = S.document(db, d, with_fields=True)
    app = db.get(Application, d.application_id)
    out["application_code"] = app.code
    return out


@router.get("/{doc_id}/file")
def download(doc_id: int, db: Session = Depends(get_db), user: User = Depends(require("application:view"))):
    d = get_doc(db, doc_id)
    read_file(d)  # 404 if missing
    audit.log(db, "document.viewed", f"Viewed original file {d.filename}", actor=user, entity_type="document",
              entity_id=d.id, application_id=d.application_id)
    db.commit()
    return FileResponse(d.storage_path, media_type=d.mime, filename=d.filename, content_disposition_type="inline")


@router.get("/{doc_id}/pages/{page_no}/image")
def page_image(doc_id: int, page_no: int, boxes: str = Query("", description="x0,y0,x1,y1;…"),
               field_id: int | None = None, db: Session = Depends(get_db),
               _: User = Depends(require("application:view"))):
    d = get_doc(db, doc_id)
    rects: list[list[float]] = []
    if field_id:
        f = db.get(ExtractedField, field_id)
        if f and f.document_id == d.id and f.bbox and f.page == page_no:
            rects.append(f.bbox)
    for part in filter(None, boxes.split(";")):
        try:
            vals = [float(x) for x in part.split(",")]
        except ValueError:
            raise HTTPException(400, "Invalid boxes parameter")
        if len(vals) == 4:
            rects.append(vals)
    try:
        png = render_page(read_file(d), d.mime, page_no, rects)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.post("/{doc_id}/process")
def reprocess(doc_id: int, db: Session = Depends(get_db), user: User = Depends(require("document:upload"))):
    d = get_doc(db, doc_id)
    app = _editable(db, d)
    process_document(db, d)
    audit.log(db, "document.reprocessed", f"Officer re-processed {d.filename}", actor=user, entity_type="document",
              entity_id=d.id, application_id=app.id)
    db.commit()
    return S.document(db, d, with_fields=True)


@router.post("/{doc_id}/replace")
async def replace(doc_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                  user: User = Depends(require("document:upload"))):
    """Rectification: upload a corrected document. The old one is kept as SUPERSEDED for audit."""
    old = get_doc(db, doc_id)
    app = _editable(db, old)
    if old.status not in ("UPLOADED", "PROCESSED", "FAILED"):
        raise HTTPException(409, "Only active documents can be replaced")
    new = save_upload(db, app, file.filename or old.filename, await file.read(), old.declared_type, user, replaces=old)
    recompute_status(db, app)
    db.commit()
    return S.document(db, new)


@router.delete("/{doc_id}")
def remove(doc_id: int, db: Session = Depends(get_db), user: User = Depends(require("document:upload"))):
    d = get_doc(db, doc_id)
    app = _editable(db, d)
    d.status = "REMOVED"
    audit.log(db, "document.removed", f"Removed {d.filename} from the submission", actor=user,
              entity_type="document", entity_id=d.id, application_id=app.id)
    recompute_status(db, app)
    db.commit()
    return {"ok": True}


@router.post("/{doc_id}/verify")
def verify(doc_id: int, db: Session = Depends(get_db), user: User = Depends(require("verification:run"))):
    d = get_doc(db, doc_id)
    app = _editable(db, d)
    if d.status != "PROCESSED":
        raise HTTPException(400, "Run pre-scrutiny first so the reference number can be extracted.")
    v = verify_document(db, d, reference_date(db), actor=user)
    db.commit()
    _revalidate_if_run(db, app, user)
    return S.verification(v)


@router.post("/{doc_id}/verify/manual")
def verify_manual(doc_id: int, body: ManualVerificationIn, db: Session = Depends(get_db),
                  user: User = Depends(require("verification:manual"))):
    d = get_doc(db, doc_id)
    app = _editable(db, d)
    v = record_manual(db, d, body.status, body.note, user)
    db.commit()
    _revalidate_if_run(db, app, user)
    return S.verification(v)
