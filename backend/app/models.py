from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

# ── Enumerations (kept as plain strings for portability) ──
ROLES = ("SCRUTINY_OFFICER", "VERIFICATION_OFFICER", "ADMIN")
SEVERITIES = ("CRITICAL", "WARNING", "INFO")
FINDING_TYPES = ("MISSING_DOCUMENT", "EXPIRED_DOCUMENT", "CONSISTENCY", "ANOMALY",
                 "VERIFICATION", "REGULATORY", "INFRASTRUCTURE")
FINDING_OPEN_STATUSES = ("OPEN", "CLARIFICATION_REQUESTED", "ESCALATED")
VERIFICATION_STATUSES = ("VERIFIED", "MISMATCH", "EXPIRED", "PENDING", "SOURCE_UNAVAILABLE", "MANUAL_REVIEW")
OUTCOMES = ("RECOMMEND_APPROVAL", "ISSUE_DEFICIENCY_LETTER", "REFER_FOR_INSPECTION", "REFER_TO_COMMITTEE")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AppSetting(Base):
    """Admin-editable global settings (reference date, upload limits, categories)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DocumentType(Base):
    __tablename__ = "document_types"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    filename_hints: Mapped[list] = mapped_column(JSON, default=list)
    has_expiry: Mapped[bool] = mapped_column(Boolean, default=False)


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[int] = mapped_column(primary_key=True)
    aicte_id: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(80))
    established_year: Mapped[int] = mapped_column(Integer)


# ── Mock "authorised AICTE system" records ──
class ApprovedProgramme(Base):
    __tablename__ = "approved_programmes"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    programme: Mapped[str] = mapped_column(String(200))
    approved_intake: Mapped[int] = mapped_column(Integer)
    academic_year: Mapped[str] = mapped_column(String(20))
    approval_ref: Mapped[str] = mapped_column(String(80))


class PaymentLedger(Base):
    __tablename__ = "payment_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    txn_ref: Mapped[str] = mapped_column(String(80), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[date] = mapped_column(Date)
    purpose: Mapped[str] = mapped_column(String(200))
    academic_year: Mapped[str] = mapped_column(String(20))


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    category: Mapped[str] = mapped_column(String(40))
    academic_year: Mapped[str] = mapped_column(String(20))
    # What the institution claimed on the form: name, address, programmes[{programme, intake}], built_up_area_sqm
    form_data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    outcome: Mapped[str | None] = mapped_column(String(40))
    outcome_note: Mapped[str | None] = mapped_column(Text)
    outcome_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime)

    institution: Mapped[Institution] = relationship()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    declared_type: Mapped[str | None] = mapped_column(String(40))
    detected_type: Mapped[str | None] = mapped_column(String(40))
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    mime: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    pdf_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    text_method: Mapped[str | None] = mapped_column(String(20))  # text | ocr | mixed | none
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    # UPLOADED → PROCESSED | FAILED; SUPERSEDED when replaced; REMOVED when withdrawn
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED")
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    replaces_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))

    pages: Mapped[list["DocumentPage"]] = relationship(cascade="all, delete-orphan", order_by="DocumentPage.page_no")
    fields: Mapped[list["ExtractedField"]] = relationship(cascade="all, delete-orphan")

    @property
    def effective_type(self) -> str:
        if self.detected_type and (self.classification_confidence or 0) >= 0.5:
            return self.detected_type
        return self.declared_type or self.detected_type or "UNKNOWN"


class DocumentPage(Base):
    __tablename__ = "document_pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text, default="")
    ocr_confidence: Mapped[float | None] = mapped_column(Float)


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    field: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[str] = mapped_column(String(500))
    normalized_value: Mapped[str | None] = mapped_column(String(500), index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(20))  # regex | ocr+regex | llm


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    group: Mapped[str] = mapped_column(String(40))
    check: Mapped[str] = mapped_column(String(80))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(20))
    applies_to: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_reference: Mapped[str] = mapped_column(String(200), default="")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RuleVersion(Base):
    __tablename__ = "rule_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    change_note: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_by_name: Mapped[str] = mapped_column(String(120), default="system")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("rule_id", "version"),)


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(20), default="FULL")  # FULL | RULES_ONLY
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING | COMPLETED | FAILED
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    step_detail: Mapped[str] = mapped_column(String(300), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    reference_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class RuleResult(Base):
    __tablename__ = "rule_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id"), index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[int] = mapped_column(Integer)
    rule_name: Mapped[str] = mapped_column(String(200))
    group: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    # PASS | FAIL | WARN | PENDING | DISABLED | ERROR
    outcome: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    finding_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("validation_runs.id"))
    fingerprint: Mapped[str] = mapped_column(String(200), index=True)
    finding_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    # OPEN | CLARIFICATION_REQUESTED | ESCALATED | REVIEWED | AUTO_CLEARED
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[str | None] = mapped_column(String(40))
    rule_version: Mapped[int | None] = mapped_column(Integer)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_field: Mapped[str | None] = mapped_column(String(120))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    expected_value: Mapped[str | None] = mapped_column(String(500))
    actual_value: Mapped[str | None] = mapped_column(String(500))
    confidence: Mapped[float | None] = mapped_column(Float)
    recommended_action: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    actions: Mapped[list["FindingAction"]] = relationship(order_by="FindingAction.at", cascade="all, delete-orphan")


class FindingAction(Base):
    __tablename__ = "finding_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VerificationSource(Base):
    __tablename__ = "verification_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    doc_types: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(120))
    # ONLINE answers immediately, ASYNC answers on refresh, OFFLINE is unreachable
    mode: Mapped[str] = mapped_column(String(20), default="ONLINE")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)


class IssuerRecord(Base):
    """Records held by the (mock) issuing-authority registries."""
    __tablename__ = "issuer_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40), index=True)
    reference_number: Mapped[str] = mapped_column(String(80), index=True)
    record: Mapped[dict] = mapped_column(JSON)


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_key: Mapped[str | None] = mapped_column(String(40))
    source_name: Mapped[str] = mapped_column(String(200))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    method: Mapped[str] = mapped_column(String(120))
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30))
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    comparison: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_by_name: Mapped[str] = mapped_column(String(120), default="VerifyAI system")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor_type: Mapped[str] = mapped_column(String(20))  # system | user
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(120))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
