"""Pydantic schemas for approval requests."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, computed_field

from preloop.models.schemas.approval_evidence import ServerRecordedContext


class ApprovalRequestBase(BaseModel):
    """Base schema for approval requests."""

    tool_name: str = Field(..., description="Name of the tool being executed")
    tool_args: Dict[str, Any] = Field(
        default_factory=dict, description="Arguments passed to the tool"
    )
    agent_reasoning: Optional[str] = Field(
        None, description="Agent's reasoning for the tool call"
    )
    execution_id: Optional[str] = Field(
        None, description="Flow execution ID (if applicable)"
    )


class ApprovalRequestCreate(ApprovalRequestBase):
    """Schema for creating a new approval request."""

    account_id: str
    tool_configuration_id: UUID
    approval_workflow_id: UUID
    expires_at: Optional[datetime] = None


class ApprovalRequestUpdate(BaseModel):
    """Schema for updating an approval request."""

    status: Optional[str] = None
    approver_comment: Optional[str] = None
    resolved_at: Optional[datetime] = None
    decided_by_user_id: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    webhook_posted_at: Optional[datetime] = None
    webhook_error: Optional[str] = None
    # AI decision tracking fields
    decided_by_ai: Optional[bool] = None
    ai_model: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None


class ApprovalRequestResponse(ApprovalRequestBase):
    """Schema for approval request response."""

    id: UUID
    account_id: UUID  # Changed from str to UUID for validation, serializer converts to str for JSON
    tool_configuration_id: UUID
    approval_workflow_id: UUID
    status: str
    requested_at: datetime
    resolved_at: Optional[datetime]
    decided_by_user_id: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    expires_at: Optional[datetime]
    approver_comment: Optional[str]
    webhook_posted_at: Optional[datetime]
    webhook_error: Optional[str]
    # AI decision tracking fields
    decided_by_ai: bool = False
    ai_model: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_reasoning: Optional[str] = None
    # Step-up verification fields
    step_up_required: bool = False
    step_up_verified: bool = False
    arkg_step_up_verified: bool = False
    step_up_protocol: Optional[str] = None
    approval_token: Optional[str] = None
    # ARKG proof fields — populated by the endpoint when arkg_step_up_verified
    arkg_step_up_signature_hex: Optional[str] = None
    arkg_derived_pk_hex: Optional[str] = None
    # RDT intent fingerprint — SHA-256(JCS(intent_envelope)); common to both step-up flows
    intent_hash_hex: Optional[str] = None
    rdt_envelope: Optional[Dict[str, Any]] = None
    action_class: Optional[str] = None
    server_recorded_context: Optional[ServerRecordedContext] = Field(
        None,
        description=(
            "Server-recorded requester and matched-policy context. This context is "
            "not cryptographically bound to the intent signature; null means unknown "
            "for legacy requests."
        ),
    )

    # ── Intent verifier fields ────────────────────────────────────────────────
    # All nullable — None for requests created before this feature, or when
    # the verifier was not enabled on the workflow.
    intent_verified: bool = False
    intent_risk_tier: Optional[str] = None
    intent_step_up_override: Optional[bool] = None
    intent_description_match_score: Optional[float] = None
    intent_flags: Optional[list] = None
    intent_reasoning: Optional[str] = None
    intent_model: Optional[str] = None
    intent_latency_ms: Optional[int] = None

    # Computed fields for backward compatibility
    @computed_field
    def approval_policy_id(self) -> str:
        """Alias for backward compatibility with older mobile app versions."""
        return str(self.approval_workflow_id)

    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "id",
        "account_id",
        "tool_configuration_id",
        "approval_workflow_id",
        "decided_by_user_id",
    )
    def serialize_uuid(self, value: Optional[UUID]) -> Optional[str]:
        """Serialize UUID to string."""
        return str(value) if value else None


class ApprovalDecision(BaseModel):
    """Schema for approval decision."""

    approved: bool = Field(
        ..., description="Whether the request is approved or declined"
    )
    comment: Optional[str] = Field(None, description="Comment from the approver")


class IntentHashVerificationResponse(BaseModel):
    """Integrity-only verification of the versioned intent envelope."""

    request_id: UUID
    envelope_version: int
    intent_intact: bool
    signature_verified: bool = False
    detail: str = (
        "Intent Hash matching checks covered evidence integrity only; "
        "it does not verify an agent assertion or hardware signature."
    )
