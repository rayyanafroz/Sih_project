"""Check registry.

Rules (rows in the `rules` table) pick a registered check by name and supply its parameters,
severity, applicable categories and on/off state. Admins edit rules; developers add checks.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from sqlalchemy.orm import Session

from ..models import Application, Document, DocumentType, ExtractedField, Institution, Verification
from ..records.aicte import AicteRecords


@dataclass
class ParamSpec:
    name: str
    type: str  # int | float | doc_type | doc_types | string_list
    label: str
    default: object = None
    help: str = ""


@dataclass
class Draft:
    """A finding produced by a check, before it is reconciled with stored findings."""
    subject: str
    finding_type: str
    title: str
    description: str
    evidence: list = field(default_factory=list)
    expected: str | None = None
    actual: str | None = None
    severity: str | None = None  # overrides the rule severity when set
    recommended_action: str = "Manual review by officer"
    confidence: float | None = None
    document: Document | None = None
    field: ExtractedField | None = None


@dataclass
class Result:
    message: str
    drafts: list[Draft] = field(default_factory=list)
    evidence: list = field(default_factory=list)


@dataclass
class CheckDef:
    name: str
    label: str
    description: str
    params: list[ParamSpec]
    fn: Callable


CHECKS: dict[str, CheckDef] = {}


def check(name: str, label: str, description: str, params: list[ParamSpec] | None = None):
    def wrap(fn):
        CHECKS[name] = CheckDef(name, label, description, params or [], fn)
        return fn
    return wrap


@dataclass
class Context:
    db: Session
    app: Application
    institution: Institution
    docs: list[Document]
    ref_date: date
    records: AicteRecords
    doc_types: dict[str, DocumentType]
    verifications: dict[int, Verification]

    def docs_of(self, code: str) -> list[Document]:
        return [d for d in self.docs if d.effective_type == code]

    def field(self, doc: Document, name: str) -> ExtractedField | None:
        return next((f for f in doc.fields if f.field == name), None)

    def type_label(self, code: str) -> str:
        dt = self.doc_types.get(code)
        return dt.label if dt else code

    # ── evidence builders ──
    @staticmethod
    def ev_doc(doc: Document, f: ExtractedField | None = None, label: str | None = None) -> dict:
        return {"kind": "document", "document_id": doc.id, "application_id": doc.application_id,
                "filename": doc.filename, "page": f.page if f else 1, "bbox": f.bbox if f else None,
                "field": f.field if f else None, "value": f.value if f else None,
                "label": label or doc.filename}

    @staticmethod
    def ev_form(field_name: str, value, label: str = "Application form") -> dict:
        return {"kind": "application_form", "field": field_name, "value": str(value), "label": label}

    def ev_record(self, label: str, value, reference: str | None = None) -> dict:
        return {"kind": "record", "source": self.records.source_name, "is_mock": self.records.is_mock,
                "label": label, "value": str(value), "reference": reference}

    @staticmethod
    def ev_verification(v: Verification) -> dict:
        return {"kind": "verification", "verification_id": v.id, "label": v.source_name, "value": v.status,
                "is_mock": v.is_mock, "method": v.method}
