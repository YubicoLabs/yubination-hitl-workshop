"""Schemas for IssueComplianceResult model."""

from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional, List, Any
import json


class Annotation(BaseModel):
    text: str
    label: str
    status: str
    comment: str


class IssueComplianceResultBase(BaseModel):
    prompt_id: str
    name: str
    compliance_factor: float
    reason: str
    suggestion: str
    annotated_description: Optional[List[Annotation]] = None
    issue_id: str


class IssueComplianceResultCreate(IssueComplianceResultBase):
    pass


class IssueComplianceResultResponse(IssueComplianceResultBase):
    id: str
    short_name: str
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "issue_id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v: Any) -> str:
        """Convert UUID objects to strings for JSON serialization."""
        if v is None:
            return ""
        return str(v)

    @field_validator("annotated_description", mode="before")
    @classmethod
    def parse_annotated_description(cls, v: Any) -> Optional[List[dict]]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None  # Or handle error appropriately
        return v

    model_config = ConfigDict(from_attributes=True)


class ComplianceSuggestionResponse(BaseModel):
    title: str
    description: str
    changes: str


class CompliancePromptMetadata(BaseModel):
    id: str
    name: str
    short_name: str


class Prompt(BaseModel):
    name: str
    system: str
    user: str


class ComplianceWorkflow(BaseModel):
    name: str
    short_name: str
    evaluate: Prompt
    propose_improvement: Prompt
