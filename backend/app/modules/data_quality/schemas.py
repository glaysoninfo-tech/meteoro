from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QualityIssue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    issue_id: str
    organization_id: str
    source_id: str
    variable_code: str
    flag_code: str
    severity: str
    description: str
    detected_at_utc: datetime


class QualityReview(BaseModel):
    reviewer_id: str = Field(min_length=1)
    decision: str = Field(min_length=3, max_length=20)
    reason: str = Field(min_length=3, max_length=500)


class RuleRevisionCreate(BaseModel):
    rule_name: str = Field(min_length=3, max_length=160)
    scope: dict[str, Any]
    condition: dict[str, Any]
    severity: str = Field(min_length=3, max_length=20)
    status: str = Field(default="draft", min_length=3, max_length=20)
    change_reason: str | None = Field(default=None, max_length=1000)


class RuleRevisionUpdate(BaseModel):
    rule_name: str | None = Field(default=None, min_length=3, max_length=160)
    scope: dict[str, Any] | None = None
    condition: dict[str, Any] | None = None
    severity: str | None = Field(default=None, min_length=3, max_length=20)
    status: str | None = Field(default=None, min_length=3, max_length=20)
    change_reason: str = Field(min_length=3, max_length=1000)


class RuleRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_revision_id: str
    organization_id: str
    rule_family_id: str
    revision_number: int
    supersedes_rule_revision_id: str | None
    rule_name: str
    scope_json: str
    condition_json: str
    severity: str
    status: str
    content_hash: str
    created_by: str
    change_reason: str | None
    created_at: datetime
