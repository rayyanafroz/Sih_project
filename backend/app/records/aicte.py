"""Adapter for "authorised AICTE systems" (approved programmes/intake, payment ledger).

The prototype implementation reads synthetic tables. A production adapter would call the real AICTE
services with proper authorisation; callers only depend on this interface.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApprovedProgramme, Institution, PaymentLedger
from ..pipeline.extract import normalize_id, programme_key


class AicteRecords:
    source_name = "AICTE institutional records"
    is_mock = True

    def __init__(self, db: Session):
        self.db = db

    def describe(self) -> dict:
        return {"source": self.source_name, "is_mock": self.is_mock}

    def institution(self, institution_id: int) -> Institution | None:
        return self.db.get(Institution, institution_id)

    def approved_programmes(self, institution_id: int) -> list[ApprovedProgramme]:
        return self.db.scalars(select(ApprovedProgramme).where(ApprovedProgramme.institution_id == institution_id)).all()

    def approved_intake(self, institution_id: int, programme: str) -> ApprovedProgramme | None:
        key = programme_key(programme)
        for p in self.approved_programmes(institution_id):
            if programme_key(p.programme) == key:
                return p
        return None

    def payment(self, txn_ref: str) -> PaymentLedger | None:
        target = normalize_id(txn_ref)
        for row in self.db.scalars(select(PaymentLedger)).all():
            if normalize_id(row.txn_ref) == target:
                return row
        return None
