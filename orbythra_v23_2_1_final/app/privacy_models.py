from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

LawfulBasis = Literal[
    "consent",
    "contract",
    "legal_obligation",
    "vital_interests",
    "public_task",
    "legitimate_interests",
]


class PrivacyRecordCreate(BaseModel):
    subject_id: str = Field(min_length=1, max_length=256)
    purpose: str = Field(min_length=3, max_length=240)
    lawful_basis: LawfulBasis
    data_categories: list[str] = Field(min_length=1, max_length=40)
    declared_fields: list[str] = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    retention_days: int = Field(ge=1, le=3650)
    consent_reference: str | None = Field(default=None, max_length=240)
    special_category: bool = False
    article9_condition: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def validate_legal_metadata(self):
        if self.lawful_basis == "consent" and not (self.consent_reference or "").strip():
            raise ValueError("consent_reference_required")
        if self.special_category and not (self.article9_condition or "").strip():
            raise ValueError("article9_condition_required_for_special_category_data")
        payload_fields = {str(key) for key in self.payload.keys()}
        declared = {item.strip() for item in self.declared_fields if item.strip()}
        if not payload_fields.issubset(declared):
            unknown = sorted(payload_fields - declared)
            raise ValueError("undeclared_payload_fields:" + ",".join(unknown))
        if len(declared) != len(self.declared_fields):
            raise ValueError("duplicate_or_empty_declared_fields")
        return self


class PrivacyRecordResponse(BaseModel):
    record_id: str
    purpose: str
    lawful_basis: LawfulBasis
    data_categories: list[str]
    declared_fields: list[str]
    payload: dict[str, Any]
    retention_until: int
    restricted: bool
    consent_withdrawn: bool
    special_category: bool
    article9_condition: str | None
    created_at: int
    updated_at: int


class SubjectRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=256)


class RectifyRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=256)
    record_id: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any]
    declared_fields: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_minimisation(self):
        payload_fields = {str(key) for key in self.payload.keys()}
        declared = {item.strip() for item in self.declared_fields if item.strip()}
        if not payload_fields.issubset(declared):
            unknown = sorted(payload_fields - declared)
            raise ValueError("undeclared_payload_fields:" + ",".join(unknown))
        return self


class SubjectExportResponse(BaseModel):
    format: Literal["application/json"] = "application/json"
    generated_at: int
    subject_id: str
    records: list[PrivacyRecordResponse]


class PrivacyActionResponse(BaseModel):
    subject_id: str
    affected_records: int
    action: str


class RetentionPurgeResponse(BaseModel):
    purged_records: int
    purged_at: int


class BreachCreate(BaseModel):
    incident_reference: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=3, max_length=4000)
    detected_at: int
    personal_data_categories: list[str] = Field(default_factory=list, max_length=40)
    estimated_subjects: int | None = Field(default=None, ge=0)
    risk_assessment: Literal["unlikely", "possible", "likely", "high"] = "possible"


class BreachResponse(BaseModel):
    breach_id: str
    incident_reference: str
    detected_at: int
    notification_deadline_at: int
    authority_notified_at: int | None
    status: str
    risk_assessment: str


class PrivacyInventoryResponse(BaseModel):
    active_records: int
    restricted_records: int
    expired_records: int
    purposes: dict[str, int]
    lawful_bases: dict[str, int]
    encryption_at_rest: bool
    raw_subject_identifiers_stored: bool = False
