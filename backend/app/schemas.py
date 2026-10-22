"""Typed request bodies. Responses are built by app/serializers.py."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    email: str
    password: str


class ProgrammeIn(BaseModel):
    programme: str = Field(min_length=2, max_length=200)
    intake: int = Field(ge=0, le=5000)


class ApplicationIn(BaseModel):
    institution_id: int
    category: str = "EOA"
    academic_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    institution_name: str | None = None
    address: str | None = None
    programmes: list[ProgrammeIn] = Field(min_length=1)
    built_up_area_sqm: float | None = Field(default=None, ge=0)


class FindingActionIn(BaseModel):
    action: Literal["request_clarification", "mark_reviewed", "escalate", "reopen"]
    note: str = Field(default="", max_length=2000)

    @field_validator("note")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class OutcomeIn(BaseModel):
    outcome: Literal["RECOMMEND_APPROVAL", "ISSUE_DEFICIENCY_LETTER", "REFER_FOR_INSPECTION", "REFER_TO_COMMITTEE"]
    note: str = Field(min_length=5, max_length=4000)
    acknowledge_open_findings: bool = False


class ManualVerificationIn(BaseModel):
    status: Literal["VERIFIED", "MISMATCH", "EXPIRED", "MANUAL_REVIEW"]
    note: str = Field(min_length=5, max_length=2000)


class RuleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    severity: Literal["CRITICAL", "WARNING", "INFO"] | None = None
    enabled: bool | None = None
    applies_to: list[str] | None = None
    params: dict | None = None
    source_reference: str | None = None
    change_note: str = Field(min_length=3, max_length=1000)


class RuleCreateIn(BaseModel):
    rule_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-]{2,39}$")
    name: str = Field(min_length=3, max_length=200)
    description: str = ""
    group: str = "DOCUMENT"
    check: str
    params: dict = {}
    severity: Literal["CRITICAL", "WARNING", "INFO"] = "CRITICAL"
    applies_to: list[str] = ["EOA"]
    source_reference: str = ""
    change_note: str = Field(default="Rule created", min_length=3)


class SettingsIn(BaseModel):
    reference_date: str | None = Field(default=None, pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    max_upload_mb: int | None = Field(default=None, ge=1, le=100)
    change_note: str = Field(min_length=3)


class SourceUpdateIn(BaseModel):
    mode: Literal["ONLINE", "ASYNC", "OFFLINE"]
    change_note: str = Field(min_length=3)
