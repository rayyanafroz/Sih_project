"""Reset the database to the demo state. Used by scripts/reset_demo.py and the test-suite."""
import json
import shutil
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, serializers as S
from ..auth import hash_password
from ..config import BACKEND_DIR, settings
from ..db import Base, SessionLocal, engine, utcnow
from ..models import (AppSetting, Application, ApprovedProgramme, DocumentType, Finding, Institution, IssuerRecord,
                      PaymentLedger, Rule, RuleVersion, User, VerificationSource)
from ..services.documents import active_documents, save_upload
from ..services.prescrutiny import execute_run, revalidate, start_run
from ..services.status import recompute_status
from ..verification.engine import latest_verification, record_manual, refresh_verification
from . import dataset as D
from .generate import build

SEED_DIR = BACKEND_DIR / "seed"


def seed_configuration(db: Session) -> None:
    for t in json.loads((SEED_DIR / "document_types.json").read_text()):
        db.add(DocumentType(**t))
    for r in json.loads((SEED_DIR / "rules.json").read_text()):
        rule = Rule(**r, enabled=True, version=1)
        db.add(rule)
        db.add(RuleVersion(rule_id=rule.rule_id, version=1, snapshot=S.rule_snapshot(rule),
                           change_note="Initial configuration (seed)", changed_by_name="system"))


def seed_demo_records(db: Session) -> dict[str, Institution]:
    users = [User(name=u["name"], email=u["email"], role=u["role"], password_hash=hash_password(D.DEMO_PASSWORD))
             for u in D.USERS]
    db.add_all(users)
    db.add(AppSetting(key="reference_date", value=D.REFERENCE_DATE))
    insts = {}
    for key, data in D.INSTITUTIONS.items():
        insts[key] = Institution(**data)
        db.add(insts[key])
    db.flush()
    for key, (ref, progs) in D.APPROVED.items():
        for prog, intake in progs:
            db.add(ApprovedProgramme(institution_id=insts[key].id, programme=prog, approved_intake=intake,
                                     academic_year="2025-26", approval_ref=ref))
    for key, txn, amount, paid in D.PAYMENTS:
        db.add(PaymentLedger(institution_id=insts[key].id, txn_ref=txn, amount=amount,
                             paid_on=date.fromisoformat(paid), purpose="Processing fee", academic_year="2026-27"))
    for s in D.SOURCES:
        db.add(VerificationSource(**s, is_mock=True))
    for src, ref, record in D.ISSUER_RECORDS:
        db.add(IssuerRecord(source_key=src, reference_number=ref, record=record))
    db.flush()
    return insts


def _user(db: Session, role: str) -> User:
    return db.scalars(select(User).where(User.role == role)).first()


def _attach(db: Session, app: Application, user: User) -> None:
    folder = settings.demo_data_dir / app.code
    for item in json.loads((folder / "manifest.json").read_text()):
        save_upload(db, app, item["filename"], (folder / item["filename"]).read_bytes(), item["declared_type"], user)
    db.commit()


def _run_now(db: Session, app: Application, user: User) -> None:
    run = start_run(db, app, user)
    execute_run(run.id)
    db.expire_all()


def reset(generate_documents: bool = True, quiet: bool = False) -> None:
    say = (lambda *a: None) if quiet else print
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if settings.storage_dir.exists():
        shutil.rmtree(settings.storage_dir)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if generate_documents or not (settings.demo_data_dir / "EoA-2026-4821" / "manifest.json").exists():
        build(settings.demo_data_dir)
        say(f"Generated synthetic documents in {settings.demo_data_dir}")

    saved_delay, settings.step_delay = settings.step_delay, 0
    db = SessionLocal()
    try:
        seed_configuration(db)
        insts = seed_demo_records(db)
        scrutiny, verifier = _user(db, "SCRUTINY_OFFICER"), _user(db, "VERIFICATION_OFFICER")
        apps = {}
        for a in D.APPLICATIONS:
            inst = insts[a["inst"]]
            app = Application(code=a["code"], institution_id=inst.id, category="EOA", academic_year="2026-27",
                              created_by=scrutiny.id, submitted_at=datetime.fromisoformat(a["submitted_at"]),
                              form_data={"institution_name": inst.name, "address": inst.address,
                                         "programmes": [{"programme": p, "intake": n} for p, n in a["programmes"]],
                                         "built_up_area_sqm": a["built_up_area_sqm"]})
            db.add(app)
            db.flush()
            audit.log(db, "application.created", f"Application {app.code} received for {inst.name}", actor=scrutiny,
                      entity_type="application", entity_id=app.id, application_id=app.id)
            recompute_status(db, app)
            apps[a["code"]] = (app, a)
        db.commit()

        for code, (app, a) in apps.items():
            if not a["preload"]:
                continue
            _attach(db, app, scrutiny)
            _run_now(db, app, scrutiny)
            say(f"Pre-scrutiny completed for {code}: {app.status}")

        # EoA-2026-4820: walk through the complete lifecycle so the dashboard shows a decided case
        nec, _ = apps["EoA-2026-4820"]
        for d in active_documents(db, nec.id):
            v = latest_verification(db, d.id)
            if v and v.status == "PENDING":
                refresh_verification(db, v, d, date.fromisoformat(D.REFERENCE_DATE), verifier)
            elif v and v.status == "SOURCE_UNAVAILABLE":
                record_manual(db, d, "VERIFIED", "Confirmed by phone with the District Notary office; registry "
                                                 "entry AFF-2026-0877 read back and matched.", verifier)
        db.commit()
        revalidate(db, nec, verifier)
        db.refresh(nec)
        for f in db.scalars(select(Finding).where(Finding.application_id == nec.id,
                                                  Finding.status == "OPEN")):
            say(f"  note: unexpected open finding on {nec.code}: {f.title}")
        if nec.status == "READY_FOR_DECISION":
            nec.outcome, nec.outcome_by = "RECOMMEND_APPROVAL", scrutiny.id
            nec.outcome_note = "All checks passed; sources verified. Recommended for Extension of Approval."
            nec.outcome_at = utcnow()
            audit.log(db, "outcome.recorded", "Officer recorded outcome: Recommend Approval", actor=scrutiny,
                      entity_type="application", entity_id=nec.id, application_id=nec.id,
                      details={"outcome": nec.outcome, "note": nec.outcome_note})
            recompute_status(db, nec)
            db.commit()
        say(f"{nec.code}: {nec.status}")
    finally:
        db.close()
        settings.step_delay = saved_delay


def ensure_seeded() -> bool:
    """Create the demo data if the database has no users (first start, or an earlier start that stopped part-way).

    Runs when the server starts, so every way of launching the app ends up with working demo accounts.
    Returns True if it seeded. Disabled when demo mode is off.
    """
    if not settings.demo_mode:
        return False
    db = SessionLocal()
    try:
        if db.query(User).first() is not None:
            return False
    finally:
        db.close()
    print("No users found: setting up the demo data (first start only, about 15 seconds)...", flush=True)
    reset(generate_documents=False, quiet=True)
    print("Demo data ready. Sign in with scrutiny@verifyai.demo / demo1234", flush=True)
    return True
