from datetime import date

from sqlalchemy.orm import Session

from ..models import AppSetting

DEFAULTS = {
    # Date used for expiry checks. Empty means "today". Pinned for demos so results stay reproducible.
    "reference_date": "",
    "max_upload_mb": 15,
    "allowed_extensions": ["pdf", "png", "jpg", "jpeg"],
    "categories": [
        {"code": "EOA", "label": "Extension of Approval"},
        {"code": "NEW_INSTITUTION", "label": "New Institution"},
        {"code": "INTAKE_CHANGE", "label": "Increase / Reduction in Intake"},
        {"code": "NAME_CHANGE", "label": "Change of Name"},
    ],
}


def get_setting(db: Session, key: str):
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def all_settings(db: Session) -> dict:
    out = dict(DEFAULTS)
    for row in db.query(AppSetting).all():
        out[row.key] = row.value
    return out


def reference_date(db: Session) -> date:
    raw = get_setting(db, "reference_date")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return date.today()


def category_label(db: Session, code: str) -> str:
    for c in get_setting(db, "categories"):
        if c["code"] == code:
            return c["label"]
    return code
