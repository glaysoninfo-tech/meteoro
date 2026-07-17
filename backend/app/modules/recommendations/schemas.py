from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecommendationCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    audience: str = Field(min_length=2, max_length=80)
    criteria: dict[str, Any]
    content: dict[str, Any]
    change_reason: str | None = Field(default=None, max_length=1000)


class RecommendationRevise(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    audience: str | None = Field(default=None, min_length=2, max_length=80)
    criteria: dict[str, Any] | None = None
    content: dict[str, Any] | None = None
    status: str | None = Field(default=None, min_length=3, max_length=20)
    change_reason: str = Field(min_length=3, max_length=1000)


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recommendation_revision_id: str
    organization_id: str
    recommendation_family_id: str
    revision_number: int
    supersedes_recommendation_revision_id: str | None
    title: str
    audience: str
    criteria_json: str
    content_json: str
    status: str
    content_hash: str
    created_by: str
    change_reason: str | None
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    published_by: str | None
    published_at: datetime | None


class RecommendationApprovalRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class RecommendationPublicationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
