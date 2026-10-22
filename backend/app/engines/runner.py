from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import utcnow
from ..models import Application, DocumentType, Finding, Rule, RuleResult, ValidationRun
from ..records.aicte import AicteRecords
from ..services.documents import active_documents
from ..verification.engine import latest_verification
from . import checks  # noqa: F401  (registers checks)
from .registry import CHECKS, Context, Draft

SEVERITY_RANK = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}


def build_context(db: Session, app: Application, run: ValidationRun) -> Context:
    docs = [d for d in active_documents(db, app.id)]
    verifs = {}
    for d in docs:
        v = latest_verification(db, d.id)
        if v:
            verifs[d.id] = v
    return Context(db=db, app=app, institution=app.institution, docs=docs, ref_date=run.reference_date,
                   records=AicteRecords(db), doc_types={t.code: t for t in db.scalars(select(DocumentType))},
                   verifications=verifs)


def effective_params(rule: Rule) -> dict:
    spec = CHECKS[rule.check]
    params = {ps.name: ps.default for ps in spec.params}
    params.update(rule.params or {})
    return params


def _upsert(db: Session, app: Application, run: ValidationRun, rule: Rule, draft: Draft,
            existing: dict[str, Finding]) -> Finding:
    fp = f"{rule.rule_id}:{draft.subject}"
    f = existing.get(fp)
    now = utcnow()
    if f is None:
        f = Finding(application_id=app.id, fingerprint=fp, created_at=now, status="OPEN")
        db.add(f)
        is_new = True
    else:
        is_new = False
        if f.status == "AUTO_CLEARED":
            f.status, f.resolved_at, f.resolved_by, f.resolution_note = "OPEN", None, None, None
            is_new = True
    f.run_id = run.id
    f.rule_id, f.rule_version = rule.rule_id, rule.version
    f.finding_type = draft.finding_type
    f.severity = draft.severity or rule.severity
    f.title, f.description = draft.title, draft.description
    f.evidence = draft.evidence
    f.expected_value, f.actual_value = draft.expected, draft.actual
    f.confidence = draft.confidence
    f.recommended_action = draft.recommended_action
    f.source_document_id = draft.document.id if draft.document else None
    f.source_page = draft.field.page if draft.field else (1 if draft.document else None)
    f.source_field = draft.field.field if draft.field else None
    f.updated_at = now
    db.flush()
    if is_new:
        audit.log(db, "finding.created", f"[{f.severity}] {f.title}", entity_type="finding", entity_id=f.id,
                  application_id=app.id, details={"rule_id": rule.rule_id, "rule_version": rule.version})
    existing[fp] = f
    return f


def evaluate_rules(db: Session, app: Application, run: ValidationRun) -> dict:
    ctx = build_context(db, app, run)
    rules = db.scalars(select(Rule).order_by(Rule.rule_id)).all()
    existing = {}
    for f in db.scalars(select(Finding).where(Finding.application_id == app.id).order_by(Finding.id)):
        existing[f.fingerprint] = f
    seen: set[str] = set()
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "PENDING": 0, "DISABLED": 0, "ERROR": 0}

    for rule in rules:
        if app.category not in (rule.applies_to or []):
            continue
        rr = RuleResult(run_id=run.id, application_id=app.id, rule_id=rule.rule_id, rule_version=rule.version,
                        rule_name=rule.name, group=rule.group, severity=rule.severity)
        if not rule.enabled:
            rr.outcome, rr.message = "DISABLED", "Rule disabled by administrator"
        elif rule.check not in CHECKS:
            rr.outcome, rr.message = "ERROR", f"Unknown check '{rule.check}'"
        else:
            try:
                res = CHECKS[rule.check].fn(ctx, effective_params(rule))
                ids, worst = [], 0
                for draft in res.drafts:
                    f = _upsert(db, app, run, rule, draft, existing)
                    seen.add(f.fingerprint)
                    ids.append(f.id)
                    worst = max(worst, SEVERITY_RANK[f.severity])
                rr.finding_ids = ids
                rr.message = res.message
                rr.evidence = res.evidence
                rr.outcome = {3: "FAIL", 2: "WARN", 1: "PENDING", 0: "PASS"}[worst]
            except Exception as exc:  # one broken rule must not stop the others
                rr.outcome, rr.message = "ERROR", f"Check raised an error: {exc}"
        counts[rr.outcome] += 1
        db.add(rr)

    for fp, f in existing.items():
        if fp not in seen and f.status != "AUTO_CLEARED":
            f.status = "AUTO_CLEARED"
            f.resolved_at = utcnow()
            f.resolution_note = f"No longer detected in pre-scrutiny run #{run.id}"
            audit.log(db, "finding.auto_cleared", f"Cleared: {f.title}", entity_type="finding", entity_id=f.id,
                      application_id=app.id, details={"run_id": run.id})

    db.flush()
    open_findings = db.scalars(select(Finding).where(Finding.application_id == app.id,
                                                     Finding.status != "AUTO_CLEARED")).all()
    summary = {
        "rules_evaluated": sum(counts.values()) - counts["DISABLED"],
        "rules_passed": counts["PASS"],
        "rules_failed": counts["FAIL"],
        "rules_warned": counts["WARN"],
        "rules_pending": counts["PENDING"],
        "rules_disabled": counts["DISABLED"],
        "rules_errored": counts["ERROR"],
        "findings_critical": sum(1 for f in open_findings if f.severity == "CRITICAL"),
        "findings_warning": sum(1 for f in open_findings if f.severity == "WARNING"),
        "findings_info": sum(1 for f in open_findings if f.severity == "INFO"),
        "documents": len(ctx.docs),
    }
    audit.log(db, "rules.evaluated",
              f"{summary['rules_evaluated']} rules evaluated: {counts['PASS']} passed, {counts['FAIL']} failed, "
              f"{counts['WARN']} warnings, {counts['PENDING']} pending",
              entity_type="validation_run", entity_id=run.id, application_id=app.id,
              details={"rule_versions": {r.rule_id: r.version for r in rules}, **summary})
    return summary
