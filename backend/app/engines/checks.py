"""Deterministic checks used by the rules engine.

Anomaly checks produce *indicators* only. Their wording must never claim forgery; see
ANOMALY_DISCLAIMER and the wording test in tests/test_engines.py.
"""
import re
from datetime import date, datetime

from rapidfuzz import fuzz
from sqlalchemy import select

from ..models import Application, Document, ExtractedField
from ..pipeline.extract import normalize_id, normalize_name, programme_key
from .registry import Context, Draft, ParamSpec, Result, check

ANOMALY_DISCLAIMER = "This is a preliminary indicator, not proof of manipulation. Manual verification required."
# Record comparisons can differ for innocent reasons (data-entry errors, records not yet updated).
VERIFY_NOTE = "This may have an innocent explanation, such as a data-entry error or a record not yet updated. Manual verification required."
VERIFY_SUFFIX = " — verification required"
ACTIVE = ("UPLOADED", "PROCESSED", "FAILED")


def _d(iso: str | None) -> date | None:
    try:
        return date.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


# ───────────────────────── Documents ─────────────────────────

@check("required_document", "Required document present",
       "Fails when no active document of the configured type has been submitted.",
       [ParamSpec("doc_type", "doc_type", "Document type", "NOC")])
def required_document(ctx: Context, p: dict) -> Result:
    code = p["doc_type"]
    label = ctx.type_label(code)
    docs = ctx.docs_of(code)
    if docs:
        return Result(f"{label} on file: {', '.join(d.filename for d in docs)}",
                      evidence=[ctx.ev_doc(d) for d in docs])
    submitted = ", ".join(d.filename for d in ctx.docs) or "none"
    return Result(f"{label} not found", [Draft(
        subject=code, finding_type="MISSING_DOCUMENT",
        title=f"Required document missing: {label}",
        description=f"No submitted document was identified as {label}. The checklist for this application "
                    f"category requires it.",
        evidence=[{"kind": "checklist", "label": f"Submitted documents ({len(ctx.docs)})", "value": submitted}],
        expected=f"{label} submitted", actual="Not found in submission",
        recommended_action=f"Request the institution to submit the {label}.")])


@check("declared_type_matches", "Declared type matches content",
       "Warns when the type chosen at upload differs from what the document content indicates.",
       [ParamSpec("min_confidence", "float", "Minimum classifier confidence", 0.6)])
def declared_type_matches(ctx: Context, p: dict) -> Result:
    drafts = []
    for d in ctx.docs:
        if d.declared_type and d.detected_type and d.declared_type != d.detected_type \
                and (d.classification_confidence or 0) >= p["min_confidence"]:
            drafts.append(Draft(
                subject=str(d.id), finding_type="CONSISTENCY", document=d,
                title=f"Document type differs from upload label: {d.filename}{VERIFY_SUFFIX}",
                description=f"Uploaded as {ctx.type_label(d.declared_type)}, but its content reads as "
                            f"{ctx.type_label(d.detected_type)} (classifier confidence "
                            f"{d.classification_confidence:.0%}). Checks use the detected type.",
                evidence=[ctx.ev_doc(d)], expected=ctx.type_label(d.declared_type),
                actual=ctx.type_label(d.detected_type), confidence=d.classification_confidence,
                recommended_action="Confirm the document type."))
    return Result("All declared types match document content" if not drafts else f"{len(drafts)} type mismatch(es)",
                  drafts)


@check("document_readable", "Documents readable",
       "Warns when a document failed processing, has no readable text, or OCR confidence is low.",
       [ParamSpec("min_ocr_confidence", "float", "Minimum OCR confidence (0–100)", 60),
        ParamSpec("exempt_types", "doc_types", "Types that may have no text (e.g. photos)", ["INFRA_PHOTOS"])])
def document_readable(ctx: Context, p: dict) -> Result:
    drafts = []
    for d in ctx.docs:
        if d.effective_type in p["exempt_types"]:
            continue
        reason = None
        if d.status == "FAILED":
            reason = f"Processing failed: {d.error}"
        elif d.text_method == "none":
            reason = "No readable text found (OCR unavailable or blank document)."
        elif d.ocr_confidence is not None and d.ocr_confidence < p["min_ocr_confidence"]:
            reason = f"Low OCR confidence ({d.ocr_confidence:.0f}%). Extracted values may be unreliable."
        if reason:
            drafts.append(Draft(
                subject=str(d.id), finding_type="ANOMALY", document=d,
                title=f"OCR / readability irregularity: {d.filename}",
                description=f"{reason} {ANOMALY_DISCLAIMER}", evidence=[ctx.ev_doc(d)],
                recommended_action="Inspect the document manually; request a clearer copy if needed."))
    return Result("All documents readable" if not drafts else f"{len(drafts)} document(s) hard to read", drafts)


# ───────────────────────── Expiry ─────────────────────────

def _expiry_docs(ctx: Context, types: list[str]):
    for d in ctx.docs:
        if types and d.effective_type not in types:
            continue
        f = ctx.field(d, "expiry_date")
        exp = _d(f.normalized_value) if f else None
        if exp:
            yield d, f, exp


@check("not_expired", "Documents not expired",
       "Fails when a document's validity date is before the reference date.",
       [ParamSpec("doc_types", "doc_types", "Limit to document types (empty = all)", [])])
def not_expired(ctx: Context, p: dict) -> Result:
    drafts, checked = [], []
    for d, f, exp in _expiry_docs(ctx, p["doc_types"]):
        checked.append(ctx.ev_doc(d, f))
        if exp < ctx.ref_date:
            days = (ctx.ref_date - exp).days
            label = ctx.type_label(d.effective_type)
            drafts.append(Draft(
                subject=str(d.id), finding_type="EXPIRED_DOCUMENT", document=d, field=f,
                title=f"Expired document: {label}",
                description=f"{d.filename} states it is valid until {_fmt(exp)}, which is {days} day(s) before "
                            f"the evaluation date {_fmt(ctx.ref_date)}.",
                evidence=[ctx.ev_doc(d, f, f"{d.filename} — validity")],
                expected=f"Valid on {_fmt(ctx.ref_date)}", actual=f"Expired {_fmt(exp)}", confidence=f.confidence,
                recommended_action=f"Request a renewed {label}."))
    msg = f"{len(checked)} dated document(s) checked" + (f", {len(drafts)} expired" if drafts else ", none expired")
    return Result(msg, drafts, checked)


@check("expiring_soon", "Documents not about to expire",
       "Warns when a document expires within the configured window after the reference date.",
       [ParamSpec("window_days", "int", "Warning window (days)", 30),
        ParamSpec("doc_types", "doc_types", "Limit to document types (empty = all)", [])])
def expiring_soon(ctx: Context, p: dict) -> Result:
    drafts = []
    for d, f, exp in _expiry_docs(ctx, p["doc_types"]):
        days = (exp - ctx.ref_date).days
        if 0 <= days <= p["window_days"]:
            label = ctx.type_label(d.effective_type)
            drafts.append(Draft(
                subject=str(d.id), finding_type="EXPIRED_DOCUMENT", document=d, field=f,
                title=f"{label} expires in {days} day(s)",
                description=f"{d.filename} is valid until {_fmt(exp)}. If review continues past that date a renewed "
                            f"document will be needed.",
                evidence=[ctx.ev_doc(d, f, f"{d.filename} — validity")],
                expected=f"Valid beyond {p['window_days']} days", actual=f"{days} day(s) remaining",
                confidence=f.confidence, recommended_action="Monitor expiry; request renewal if review extends."))
    return Result(f"No document expires within {p['window_days']} days" if not drafts
                  else f"{len(drafts)} document(s) expiring soon", drafts)


# ───────────────────────── Consistency ─────────────────────────

@check("institution_name_consistent", "Institution name consistent",
       "Compares the institution name on the form and on each document with AICTE records (fuzzy match).",
       [ParamSpec("threshold", "int", "Minimum similarity (0–100)", 92),
        ParamSpec("critical_below", "int", "Treat as critical below (0–100)", 60)])
def institution_name_consistent(ctx: Context, p: dict) -> Result:
    official = ctx.institution.name
    drafts, checked = [], []
    candidates = []
    if ctx.app.form_data.get("institution_name"):
        candidates.append((None, None, ctx.app.form_data["institution_name"]))
    for d in ctx.docs:
        f = ctx.field(d, "institution_name")
        if f:
            candidates.append((d, f, f.value))
    for d, f, name in candidates:
        score = fuzz.token_sort_ratio(normalize_name(name), normalize_name(official))
        ev = ctx.ev_doc(d, f) if d else ctx.ev_form("institution_name", name)
        checked.append(ev)
        if score >= p["threshold"]:
            continue
        where = d.filename if d else "the application form"
        drafts.append(Draft(
            subject=str(d.id) if d else "form", finding_type="CONSISTENCY", document=d, field=f,
            severity="CRITICAL" if score < p["critical_below"] else None,
            title=f"Institution name variation: {where}",
            description=f"The name on {where} (\"{name}\") differs from the name in AICTE records "
                        f"(\"{official}\"). Similarity {score:.0f}% is below the configured {p['threshold']}%.",
            evidence=[ev, ctx.ev_record("Registered institution name", official, ctx.institution.aicte_id)],
            expected=official, actual=name, confidence=round(score / 100, 2),
            recommended_action="Request clarification on the name used by the issuing authority."))
    return Result(f"{len(checked)} name occurrence(s) compared with AICTE records", drafts, checked)


@check("identifier_matches_record", "AICTE permanent ID consistent",
       "Compares the AICTE permanent ID printed on documents with the institution record.",
       [ParamSpec("field", "string", "Extracted field name", "aicte_id")])
def identifier_matches_record(ctx: Context, p: dict) -> Result:
    official = ctx.institution.aicte_id
    drafts, checked = [], []
    for d in ctx.docs:
        f = ctx.field(d, p["field"])
        if not f:
            continue
        checked.append(ctx.ev_doc(d, f))
        if normalize_id(f.value) != normalize_id(official):
            drafts.append(Draft(
                subject=str(d.id), finding_type="CONSISTENCY", document=d, field=f,
                title=f"AICTE ID on {d.filename} differs from records{VERIFY_SUFFIX}",
                description=f"{d.filename} carries ID {f.value}; AICTE records list {official} for this institution. "
                            f"{VERIFY_NOTE}",
                evidence=[ctx.ev_doc(d, f), ctx.ev_record("AICTE permanent ID", official)],
                expected=official, actual=f.value, confidence=f.confidence,
                recommended_action="Verify the identifier with the institution."))
    return Result(f"{len(checked)} identifier(s) compared", drafts, checked)


def _doc_intake(ctx: Context, doc_type: str, programme: str):
    key = "intake:" + programme_key(programme)
    for d in ctx.docs_of(doc_type):
        f = ctx.field(d, key)
        if f:
            return d, f
    return None, None


@check("programme_details_match_form", "Programme details match application form",
       "Compares intake stated in the programme details document with the intake on the form.")
def programme_details_match_form(ctx: Context, p: dict) -> Result:
    drafts, checked = [], []
    for prog in ctx.app.form_data.get("programmes", []):
        d, f = _doc_intake(ctx, "PROGRAMME_DETAILS", prog["programme"])
        if not f:
            continue
        checked.append(ctx.ev_doc(d, f))
        if int(f.normalized_value) != int(prog["intake"]):
            drafts.append(Draft(
                subject=programme_key(prog["programme"]), finding_type="CONSISTENCY", document=d, field=f,
                title=f"Programme intake differs between form and document: {prog['programme']}{VERIFY_SUFFIX}",
                description=f"The form states {prog['intake']} seats; {d.filename} states {f.normalized_value}. "
                            f"{VERIFY_NOTE}",
                evidence=[ctx.ev_form(f"intake — {prog['programme']}", prog["intake"]), ctx.ev_doc(d, f)],
                expected=str(prog["intake"]), actual=f.normalized_value, confidence=f.confidence,
                recommended_action="Request clarification of the intended intake."))
    return Result(f"{len(checked)} programme(s) compared", drafts, checked)


@check("intake_within_approved", "Intake within approved intake",
       "Fails when a programme's requested intake exceeds the intake approved in AICTE records, "
       "unless an increase-in-intake approval document is submitted.",
       [ParamSpec("allow_if_doc", "doc_type", "Document that permits an increase", "INTAKE_INCREASE_APPROVAL")])
def intake_within_approved(ctx: Context, p: dict) -> Result:
    drafts, checked = [], []
    has_allowance = bool(ctx.docs_of(p["allow_if_doc"]))
    for prog in ctx.app.form_data.get("programmes", []):
        name, intake = prog["programme"], int(prog["intake"])
        rec = ctx.records.approved_intake(ctx.institution.id, name)
        form_ev = ctx.ev_form(f"intake — {name}", intake)
        if not rec:
            drafts.append(Draft(
                subject=programme_key(name), finding_type="REGULATORY", severity="WARNING",
                title=f"No approval record for programme: {name}",
                description=f"{name} appears on the application but no previous approval exists in AICTE records. "
                            f"A new programme needs separate approval.",
                evidence=[form_ev], expected="Programme previously approved", actual="No record found",
                recommended_action="Check whether a new-programme approval exists."))
            continue
        rec_ev = ctx.ev_record(f"Approved intake {rec.academic_year} — {rec.programme}", rec.approved_intake,
                               rec.approval_ref)
        checked.append(rec_ev)
        if intake <= rec.approved_intake or has_allowance:
            continue
        evidence = [form_ev]
        pd, pf = _doc_intake(ctx, "PROGRAMME_DETAILS", name)
        if pf:
            evidence.append(ctx.ev_doc(pd, pf, f"{pd.filename} — requested intake"))
        evidence.append(rec_ev)
        ed, ef = _doc_intake(ctx, "PREVIOUS_EOA", name)
        if ef:
            evidence.append(ctx.ev_doc(ed, ef, f"{ed.filename} — approved intake"))
        diff = intake - rec.approved_intake
        drafts.append(Draft(
            subject=programme_key(name), finding_type="REGULATORY", document=ed or pd, field=ef or pf,
            title=f"Requested intake exceeds approved intake on record: {name}",
            description=f"The application requests {intake} seats for {name}. AICTE records show {rec.approved_intake} "
                        f"approved for {rec.academic_year} (ref {rec.approval_ref}). An increase of {diff} seats needs "
                        f"a separate increase-in-intake approval, and none was submitted.",
            evidence=evidence, expected=f"≤ {rec.approved_intake}", actual=str(intake), confidence=0.97,
            recommended_action="Manual verification required; request increase-in-intake approval or a corrected form."))
    return Result(f"{len(ctx.app.form_data.get('programmes', []))} programme(s) checked against approved intake",
                  drafts, checked)


@check("payment_on_ledger", "Processing fee paid (TER payment record)",
       "Matches the fee receipt's transaction reference and amount with the AICTE payment ledger.",
       [ParamSpec("min_amount", "int", "Minimum fee (Rs.)", 150000)])
def payment_on_ledger(ctx: Context, p: dict) -> Result:
    receipts = ctx.docs_of("FEE_RECEIPT")
    if not receipts:
        return Result("No fee receipt to check (see required-document rule)")
    drafts, checked = [], []
    for d in receipts:
        ref_f, amt_f = ctx.field(d, "reference_number"), ctx.field(d, "amount")
        if not ref_f:
            drafts.append(Draft(subject=f"{d.id}:noref", finding_type="REGULATORY", document=d,
                                title="Fee receipt has no readable transaction reference",
                                description=f"No transaction reference could be read from {d.filename}.",
                                evidence=[ctx.ev_doc(d)], recommended_action="Verify payment manually."))
            continue
        entry = ctx.records.payment(ref_f.value)
        ev = [ctx.ev_doc(d, ref_f, f"{d.filename} — transaction reference")]
        checked.extend(ev)
        if not entry:
            drafts.append(Draft(subject=f"{d.id}:missing", finding_type="REGULATORY", document=d, field=ref_f,
                                title=f"No matching payment found in AICTE ledger{VERIFY_SUFFIX}",
                                description=f"Transaction {ref_f.value} from {d.filename} has no matching entry in the "
                                            f"AICTE payment ledger. {VERIFY_NOTE}",
                                evidence=ev, expected="Ledger entry exists", actual="No entry",
                                recommended_action="Verify payment with the accounts section."))
            continue
        ev.append(ctx.ev_record("Ledger entry", f"Rs. {entry.amount:,} on {_fmt(entry.paid_on)}", entry.txn_ref))
        if entry.institution_id != ctx.institution.id:
            drafts.append(Draft(subject=f"{d.id}:owner", finding_type="REGULATORY", document=d, field=ref_f,
                                title=f"Payment record linked to a different institution{VERIFY_SUFFIX}",
                                description=f"Ledger entry {entry.txn_ref} is recorded against another institution "
                                            f"(AICTE institution #{entry.institution_id}), not {ctx.institution.name}. "
                                            f"{VERIFY_NOTE}",
                                evidence=ev, expected=ctx.institution.name, actual="Other institution",
                                recommended_action="Manual verification required."))
            continue
        submitted_amt = int(amt_f.normalized_value) if amt_f and amt_f.normalized_value else None
        if submitted_amt is not None and submitted_amt != entry.amount:
            drafts.append(Draft(subject=f"{d.id}:amount", finding_type="REGULATORY", document=d, field=amt_f,
                                title=f"Fee receipt amount differs from ledger{VERIFY_SUFFIX}",
                                description=f"Receipt shows Rs. {submitted_amt:,}; the ledger records Rs. {entry.amount:,}. "
                                            f"{VERIFY_NOTE}",
                                evidence=ev + [ctx.ev_doc(d, amt_f)], expected=str(entry.amount),
                                actual=str(submitted_amt), recommended_action="Verify payment with accounts."))
        elif entry.amount < p["min_amount"]:
            drafts.append(Draft(subject=f"{d.id}:short", finding_type="REGULATORY", document=d, severity="WARNING",
                                title="Fee paid is below the prescribed amount",
                                description=f"Ledger shows Rs. {entry.amount:,}; prescribed fee is Rs. {p['min_amount']:,}.",
                                evidence=ev, expected=f"≥ {p['min_amount']}", actual=str(entry.amount),
                                recommended_action="Request payment of the balance."))
    return Result(f"{len(receipts)} receipt(s) matched against the payment ledger", drafts, checked)


# ───────────────────────── Anomaly indicators ─────────────────────────

def _app_label(db, application_id: int) -> str:
    app = db.get(Application, application_id)
    return f"{app.code} ({app.institution.name})" if app else f"application #{application_id}"


@check("duplicate_file_hash", "No duplicate files",
       "Flags files whose SHA-256 checksum matches another submitted file (in any application).")
def duplicate_file_hash(ctx: Context, p: dict) -> Result:
    drafts = []
    for d in ctx.docs:
        others = ctx.db.scalars(select(Document).where(Document.sha256 == d.sha256, Document.id != d.id,
                                                       Document.status.in_(ACTIVE))).all()
        for o in others:
            where = "this application" if o.application_id == d.application_id else _app_label(ctx.db, o.application_id)
            drafts.append(Draft(
                subject=f"{min(d.id, o.id)}-{max(d.id, o.id)}", finding_type="ANOMALY", document=d,
                title=f"Potential anomaly: identical file submitted twice ({d.filename})",
                description=f"{d.filename} is byte-for-byte identical to {o.filename} in {where}. {ANOMALY_DISCLAIMER}",
                evidence=[ctx.ev_doc(d), ctx.ev_doc(o, label=f"{o.filename} — {where}")],
                expected="Unique file", actual=f"Duplicate of {o.filename}", confidence=1.0,
                recommended_action="Confirm why the same file appears twice."))
    unique = {dr.subject: dr for dr in drafts}
    return Result(f"{len(ctx.docs)} file checksum(s) compared" if not unique else f"{len(unique)} duplicate file(s)",
                  list(unique.values()))


@check("duplicate_reference_number", "No duplicate reference numbers",
       "Flags reference/transaction/certificate numbers that also appear on another document (in any application).",
       [ParamSpec("fields", "string_list", "Fields to compare", ["reference_number"])])
def duplicate_reference_number(ctx: Context, p: dict) -> Result:
    drafts, checked = [], 0
    for d in ctx.docs:
        for name in p["fields"]:
            f = ctx.field(d, name)
            if not f or not f.normalized_value:
                continue
            checked += 1
            rows = ctx.db.execute(
                select(ExtractedField, Document).join(Document, Document.id == ExtractedField.document_id)
                .where(ExtractedField.field == name, ExtractedField.normalized_value == f.normalized_value,
                       Document.id != d.id, Document.status.in_(ACTIVE))).all()
            for of, o in rows:
                same_app = o.application_id == d.application_id
                where = "this application" if same_app else _app_label(ctx.db, o.application_id)
                drafts.append(Draft(
                    subject=f"{f.normalized_value}:{min(d.id, o.id)}-{max(d.id, o.id)}", finding_type="ANOMALY",
                    document=d, field=f,
                    title=f"Potential anomaly: reference {f.value} reused",
                    description=f"{f.value} on {d.filename} also appears on {o.filename} submitted with {where}. "
                                f"A reference number should identify one document. {ANOMALY_DISCLAIMER}",
                    evidence=[ctx.ev_doc(d, f), ctx.ev_doc(o, of, f"{o.filename} — {where}")],
                    expected="Unique reference", actual=f"Also on {o.filename} ({where})", confidence=0.95,
                    recommended_action="Verify the reference with the issuing body."))
    unique = {dr.subject: dr for dr in drafts}
    return Result(f"{checked} reference number(s) compared across all applications", list(unique.values()))


@check("date_irregularity", "Dates are plausible",
       "Flags issue dates after expiry, issue dates in the future, and dates before the institution was established.")
def date_irregularity(ctx: Context, p: dict) -> Result:
    drafts = []
    est = ctx.institution.established_year
    for d in ctx.docs:
        fi, fe = ctx.field(d, "issue_date"), ctx.field(d, "expiry_date")
        issue = _d(fi.normalized_value) if fi else None
        expiry = _d(fe.normalized_value) if fe else None
        problems = []
        if issue and expiry and issue > expiry:
            problems.append(("order", f"issue date {_fmt(issue)} is after validity date {_fmt(expiry)}"))
        if issue and issue > ctx.ref_date:
            problems.append(("future", f"issue date {_fmt(issue)} is after the evaluation date {_fmt(ctx.ref_date)}"))
        if issue and issue.year < est and d.effective_type not in ("LAND_RECORD",):
            problems.append(("before_est", f"issue date {_fmt(issue)} predates the institution (est. {est})"))
        for key, text in problems:
            drafts.append(Draft(
                subject=f"{d.id}:{key}", finding_type="ANOMALY", document=d, field=fi,
                title=f"Potential anomaly: irregular date on {d.filename}",
                description=f"On {d.filename}, the {text}. {ANOMALY_DISCLAIMER}",
                evidence=[ctx.ev_doc(d, fi)] + ([ctx.ev_doc(d, fe)] if fe else []),
                recommended_action="Verify the dates with the issuing authority."))
    return Result("All document dates plausible" if not drafts else f"{len(drafts)} date irregularit(ies)", drafts)


def _pdf_date(raw: str | None) -> datetime | None:
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", raw or "")
    if not m:
        return None
    y, mo, dd, hh, mi = (int(x) if x else 0 for x in m.groups())
    try:
        return datetime(y, mo, dd, hh, mi)
    except ValueError:
        return None


@check("metadata_modified_after_creation", "File metadata consistent",
       "Flags PDFs modified long after they were created, especially with editing software.",
       [ParamSpec("max_gap_days", "int", "Allowed gap between creation and modification (days)", 30),
        ParamSpec("editor_keywords", "string_list", "Producer/creator keywords indicating an editor",
                  ["editor", "edit", "photoshop", "acrobat pro"])])
def metadata_modified_after_creation(ctx: Context, p: dict) -> Result:
    drafts, checked = [], 0
    for d in ctx.docs:
        meta = d.pdf_metadata or {}
        created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
        if not created or not modified:
            continue
        checked += 1
        gap = (modified - created).days
        tool = " ".join(filter(None, [meta.get("producer"), meta.get("creator")]))
        editor = any(k.lower() in tool.lower() for k in p["editor_keywords"])
        if gap <= p["max_gap_days"]:
            continue
        drafts.append(Draft(
            subject=str(d.id), finding_type="ANOMALY", document=d, confidence=0.8 if editor else 0.6,
            title=f"Potential anomaly: {d.filename} modified after issue",
            description=f"File metadata shows it was created on {_fmt(created.date())} and last modified on "
                        f"{_fmt(modified.date())} ({gap} days later)"
                        + (f" using \"{tool}\", which is editing software" if editor else "")
                        + f". {ANOMALY_DISCLAIMER}",
            evidence=[ctx.ev_doc(d, label=f"{d.filename} — file metadata"),
                      {"kind": "metadata", "label": "PDF metadata", "value":
                       f"Created {meta.get('creationDate')}, modified {meta.get('modDate')}, producer {tool or '—'}"}],
            expected=f"Modified within {p['max_gap_days']} days of creation", actual=f"Modified {gap} days later",
            recommended_action="Verify with the issuing authority; request an original copy."))
    return Result(f"{checked} file(s) with metadata checked", drafts)


# ───────────────────────── Verification ─────────────────────────

@check("source_verified", "Verified with issuing authority",
       "Requires a VERIFIED result from the issuing authority (or manual confirmation) for the configured types.",
       [ParamSpec("doc_types", "doc_types", "Document types requiring verification", ["NOC"])])
def source_verified(ctx: Context, p: dict) -> Result:
    drafts, checked = [], []
    for d in ctx.docs:
        if d.effective_type not in p["doc_types"]:
            continue
        v = ctx.verifications.get(d.id)
        label = ctx.type_label(d.effective_type)
        if v:
            checked.append(ctx.ev_verification(v))
        if v and v.status == "VERIFIED":
            continue
        status = v.status if v else "NOT_REQUESTED"
        sev, title, action = {
            "PENDING": ("INFO", f"Source verification pending: {label}", "Awaiting issuing-authority response."),
            "MISMATCH": ("CRITICAL", f"Issuing authority record differs from submitted {label}{VERIFY_SUFFIX}",
                         "Manual verification required; request clarification."),
            "EXPIRED": ("WARNING", f"Issuing authority lists {label} as no longer valid", "Request a renewed document."),
        }.get(status, ("WARNING", f"Manual verification required: {label}",
                       "Verification Officer to confirm with the issuing authority."))
        drafts.append(Draft(
            subject=str(d.id), finding_type="VERIFICATION", document=d, severity=sev, title=title,
            description=(v.message if v else "No verification has been requested for this document.")
                        + (" (Mock/demo source.)" if v and v.is_mock else ""),
            evidence=[ctx.ev_doc(d, ctx.field(d, "reference_number"))] + ([ctx.ev_verification(v)] if v else []),
            expected="VERIFIED", actual=status, recommended_action=action))
    return Result(f"{len(checked)} verification result(s) reviewed", drafts, checked)


# ───────────────────────── Infrastructure ─────────────────────────

@check("infrastructure_evidence_complete", "Infrastructure evidence complete",
       "Requires the configured infrastructure evidence set; gaps are routed for evidence request or inspection.",
       [ParamSpec("required", "doc_types", "Required evidence types", ["INFRA_CERT", "FLOOR_PLAN", "INFRA_PHOTOS"]),
        ParamSpec("min_photos", "int", "Minimum number of photographs", 2)])
def infrastructure_evidence_complete(ctx: Context, p: dict) -> Result:
    missing = [ctx.type_label(t) for t in p["required"] if not ctx.docs_of(t)]
    photos = len(ctx.docs_of("INFRA_PHOTOS"))
    if "INFRA_PHOTOS" in p["required"] and 0 < photos < p["min_photos"]:
        missing.append(f"at least {p['min_photos']} photographs (received {photos})")
    present = [ctx.ev_doc(d) for t in p["required"] for d in ctx.docs_of(t)]
    if not missing:
        return Result("Required infrastructure evidence set is complete", evidence=present)
    return Result("Infrastructure evidence incomplete", [Draft(
        subject="evidence-set", finding_type="INFRASTRUCTURE",
        title="Infrastructure evidence: REVIEW REQUIRED",
        description=f"Required evidence set incomplete. Missing: {', '.join(missing)}. Automated review cannot "
                    f"assess infrastructure without it.",
        evidence=present + [{"kind": "checklist", "label": "Missing evidence", "value": ", ".join(missing)}],
        expected=", ".join(ctx.type_label(t) for t in p["required"]), actual="Missing: " + ", ".join(missing),
        recommended_action="Request the missing evidence, or route for physical inspection.")], present)


@check("infra_values_consistent", "Infrastructure figures consistent",
       "Compares the built-up area on the infrastructure certificate with the application form.",
       [ParamSpec("tolerance_pct", "float", "Allowed difference (%)", 5)])
def infra_values_consistent(ctx: Context, p: dict) -> Result:
    claimed = ctx.app.form_data.get("built_up_area_sqm")
    drafts, checked = [], []
    for d in ctx.docs_of("INFRA_CERT"):
        f = ctx.field(d, "built_up_area")
        if not f or not claimed or not f.normalized_value:
            continue
        checked.append(ctx.ev_doc(d, f))
        cert = float(f.normalized_value)
        diff = abs(cert - float(claimed)) / float(claimed) * 100
        if diff > p["tolerance_pct"]:
            drafts.append(Draft(
                subject=str(d.id), finding_type="INFRASTRUCTURE", document=d, field=f,
                title=f"Built-up area differs between certificate and application{VERIFY_SUFFIX}",
                description=f"Certificate states {cert:,.0f} sq.m; the form states {float(claimed):,.0f} sq.m "
                            f"({diff:.1f}% difference).",
                evidence=[ctx.ev_doc(d, f), ctx.ev_form("built_up_area_sqm", claimed)],
                expected=str(claimed), actual=f.normalized_value,
                recommended_action="Request clarification; consider physical inspection."))
    return Result(f"{len(checked)} certificate figure(s) compared", drafts, checked)
