"""Configurable regulatory requirements: rules, global settings and verification sources (Admin)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..auth import require
from ..db import get_db, utcnow
from ..engines.registry import CHECKS
from ..models import AppSetting, DocumentType, Rule, RuleVersion, User, VerificationSource
from ..schemas import RuleCreateIn, RuleUpdateIn, SettingsIn, SourceUpdateIn
from ..services.app_settings import all_settings, get_setting

router = APIRouter(tags=["rules"])
GROUPS = ("DOCUMENT", "EXPIRY", "CONSISTENCY", "REGULATORY", "ANOMALY", "VERIFICATION", "INFRASTRUCTURE")


def _validate_params(db: Session, check: str, params: dict) -> dict:
    spec = CHECKS.get(check)
    if not spec:
        raise HTTPException(400, f"Unknown check '{check}'")
    known = {p.name: p for p in spec.params}
    unknown = set(params) - set(known)
    if unknown:
        raise HTTPException(400, f"Unknown parameter(s): {', '.join(sorted(unknown))}")
    types = {t.code for t in db.scalars(select(DocumentType))}
    clean = {}
    for name, value in params.items():
        p = known[name]
        try:
            if p.type == "int":
                value = int(value)
            elif p.type == "float":
                value = float(value)
            elif p.type in ("doc_types", "string_list"):
                if isinstance(value, str):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                value = [str(v) for v in value]
            else:
                value = str(value)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Parameter '{p.label}' must be a {p.type}")
        if p.type in ("int", "float") and value < 0:
            raise HTTPException(400, f"Parameter '{p.label}' cannot be negative")
        if p.type == "doc_type" and value not in types:
            raise HTTPException(400, f"Unknown document type '{value}'")
        if p.type == "doc_types" and not set(value) <= types:
            raise HTTPException(400, f"Unknown document type(s): {', '.join(sorted(set(value) - types))}")
        clean[name] = value
    return clean


def _validate_categories(db: Session, cats: list[str]) -> list[str]:
    valid = {c["code"] for c in get_setting(db, "categories")}
    if not cats:
        raise HTTPException(400, "Select at least one application category")
    if not set(cats) <= valid:
        raise HTTPException(400, f"Unknown category: {', '.join(sorted(set(cats) - valid))}")
    return cats


def _snapshot(db: Session, r: Rule, user: User | None, note: str):
    db.add(RuleVersion(rule_id=r.rule_id, version=r.version, snapshot=S.rule_snapshot(r), change_note=note,
                       changed_by=user.id if user else None, changed_by_name=user.name if user else "system"))


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), _: User = Depends(require("rules:view"))):
    return [S.rule(db, r) for r in db.scalars(select(Rule).order_by(Rule.rule_id))]


@router.get("/rules/{rule_id}")
def get_rule(rule_id: str, db: Session = Depends(get_db), _: User = Depends(require("rules:view"))):
    r = db.scalars(select(Rule).where(Rule.rule_id == rule_id)).first()
    if not r:
        raise HTTPException(404, "Rule not found")
    return S.rule(db, r, with_history=True)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: str, body: RuleUpdateIn, db: Session = Depends(get_db),
                user: User = Depends(require("rules:edit"))):
    r = db.scalars(select(Rule).where(Rule.rule_id == rule_id)).first()
    if not r:
        raise HTTPException(404, "Rule not found")
    before = S.rule_snapshot(r)
    if body.params is not None:
        r.params = {**(r.params or {}), **_validate_params(db, r.check, body.params)}
    if body.applies_to is not None:
        r.applies_to = _validate_categories(db, body.applies_to)
    for attr in ("name", "description", "severity", "enabled", "source_reference"):
        val = getattr(body, attr)
        if val is not None:
            setattr(r, attr, val)
    after = S.rule_snapshot(r)
    changes = {k: {"from": before[k], "to": after[k]} for k in after if before[k] != after[k]}
    if not changes:
        raise HTTPException(400, "No changes to save")
    r.version += 1
    r.updated_by, r.updated_at = user.id, utcnow()
    _snapshot(db, r, user, body.change_note)
    audit.log(db, "rule.updated", f"Rule {r.rule_id} updated to v{r.version}: {body.change_note}", actor=user,
              entity_type="rule", entity_id=r.rule_id, details={"version": r.version, "changes": changes})
    db.commit()
    return S.rule(db, r, with_history=True)


@router.post("/rules")
def create_rule(body: RuleCreateIn, db: Session = Depends(get_db), user: User = Depends(require("rules:edit"))):
    if db.scalars(select(Rule).where(Rule.rule_id == body.rule_id)).first():
        raise HTTPException(400, f"Rule {body.rule_id} already exists")
    if body.group not in GROUPS:
        raise HTTPException(400, f"Group must be one of {', '.join(GROUPS)}")
    params = _validate_params(db, body.check, body.params)
    missing = [p.label for p in CHECKS[body.check].params if p.name not in params and p.default is None]
    if missing:
        raise HTTPException(400, f"Missing parameter(s): {', '.join(missing)}")
    r = Rule(rule_id=body.rule_id, name=body.name, description=body.description, group=body.group, check=body.check,
             params=params, severity=body.severity, applies_to=_validate_categories(db, body.applies_to),
             enabled=True, version=1, source_reference=body.source_reference, updated_by=user.id)
    db.add(r)
    db.flush()
    _snapshot(db, r, user, body.change_note)
    audit.log(db, "rule.created", f"Rule {r.rule_id} created: {r.name}", actor=user, entity_type="rule",
              entity_id=r.rule_id, details=S.rule_snapshot(r))
    db.commit()
    return S.rule(db, r, with_history=True)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require("rules:view"))):
    return all_settings(db)


@router.put("/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require("settings:edit"))):
    changes = {}
    for key in ("reference_date", "max_upload_mb"):
        val = getattr(body, key)
        if val is None:
            continue
        old = get_setting(db, key)
        if old == val:
            continue
        row = db.get(AppSetting, key)
        if row:
            row.value, row.updated_by = val, user.id
        else:
            db.add(AppSetting(key=key, value=val, updated_by=user.id))
        changes[key] = {"from": old, "to": val}
    if not changes:
        raise HTTPException(400, "No changes to save")
    audit.log(db, "settings.updated", f"Settings updated: {body.change_note}", actor=user, entity_type="settings",
              details={"changes": changes})
    db.commit()
    return all_settings(db)


@router.put("/sources/{key}")
def update_source(key: str, body: SourceUpdateIn, db: Session = Depends(get_db),
                  user: User = Depends(require("settings:edit"))):
    src = db.scalars(select(VerificationSource).where(VerificationSource.key == key)).first()
    if not src:
        raise HTTPException(404, "Source not found")
    old = src.mode
    src.mode = body.mode
    audit.log(db, "source.updated", f"Verification source {src.name}: {old} → {body.mode} ({body.change_note})",
              actor=user, entity_type="verification_source", entity_id=key, details={"from": old, "to": body.mode})
    db.commit()
    return {"key": src.key, "mode": src.mode}
