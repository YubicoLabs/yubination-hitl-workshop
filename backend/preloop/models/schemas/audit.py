"""Pydantic schemas for the audit decisions endpoint."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AuditDecisionRecord(BaseModel):
    id: uuid.UUID
    tool_name: str
    tool_args: dict[str, Any]
    status: str
    requested_at: datetime
    resolved_at: Optional[datetime]
    decided_by_user_id: Optional[uuid.UUID]
    decided_at: Optional[datetime]
    intent_hash_hex: Optional[str]
    step_up_required: bool
    step_up_verified: bool
    step_up_verified_at: Optional[datetime]
    step_up_key_name: Optional[str]
    step_up_key_id_tail: Optional[str]
    decided_by_ai: bool
    ai_model: Optional[str]
    ai_confidence: Optional[float]
    ai_reasoning: Optional[str]
    approver_comment: Optional[str]
    verifiable: bool

    @classmethod
    def from_orm(cls, obj: Any) -> "AuditDecisionRecord":
        nonce = getattr(obj, "step_up_challenge_nonce", None)
        verified = getattr(obj, "step_up_verified", False)
        return cls(
            id=obj.id,
            tool_name=obj.tool_name,
            tool_args=obj.tool_args or {},
            status=obj.status,
            requested_at=obj.requested_at,
            resolved_at=obj.resolved_at,
            decided_by_user_id=getattr(obj, "decided_by_user_id", None),
            decided_at=getattr(obj, "decided_at", None),
            intent_hash_hex=obj.intent_hash_hex,
            step_up_required=obj.step_up_required,
            step_up_verified=obj.step_up_verified,
            step_up_verified_at=obj.step_up_verified_at,
            step_up_key_name=obj.step_up_key_name,
            step_up_key_id_tail=obj.step_up_key_id_tail,
            decided_by_ai=obj.decided_by_ai or False,
            ai_model=obj.ai_model,
            ai_confidence=obj.ai_confidence,
            ai_reasoning=obj.ai_reasoning,
            approver_comment=obj.approver_comment,
            verifiable=bool(verified and nonce is not None),
        )


class AuditDecisionList(BaseModel):
    items: list[AuditDecisionRecord]
    total: int
    skip: int
    limit: int
