"""Approval request model for tool execution approvals."""

import secrets
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Integer,
    LargeBinary,
    String,
    DateTime,
    Text,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .account import Account
from .tool_configuration import ApprovalWorkflow, ToolConfiguration

from .base import Base

if TYPE_CHECKING:
    from .approval_event import ApprovalEvent


class ApprovalRequestStatus(str):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalRequest(Base):
    """Approval request for tool execution.

    An approval request is created when a tool requiring approval is called.
    The MCP tool execution pauses and waits for approval/decline via webhook link.
    """

    __tablename__ = "approval_request"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The account this approval request belongs to",
    )

    tool_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_configuration.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the tool configuration",
    )

    approval_workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_workflow.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the approval workflow",
    )

    execution_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Flow execution ID (if applicable)",
    )

    tool_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the tool being executed",
    )

    tool_args: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Arguments passed to the tool",
    )

    server_recorded_context: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment=(
            "Immutable requester and matched-policy context recorded by the server "
            "when approval was created; not cryptographically bound to intent proofs"
        ),
    )

    agent_reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Agent's reasoning for the tool call",
    )

    tool_result: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="Cached result of tool execution after approval (for async mode)",
    )

    status: Mapped[str] = mapped_column(
        SQLEnum(
            "pending",
            "approved",
            "declined",
            "expired",
            "cancelled",
            name="approval_request_status",
        ),
        nullable=False,
        default=ApprovalRequestStatus.PENDING,
        index=True,
        comment="Current status of the approval request",
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When the approval was requested",
    )

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the approval was resolved (approved/declined)",
    )

    decided_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User whose vote produced the final human decision",
    )

    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the request reached its final approved or declined state",
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the approval request expires",
    )

    approver_comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Comment from the approver",
    )

    # Quorum tracking: stores individual votes
    # Format: [{"user_id": "uuid", "decision": "approved"|"declined", "comment": "...", "timestamp": "iso"}]
    responses: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="Individual approval/decline responses for quorum tracking",
    )

    # Escalation tracking
    escalation_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When escalation was triggered (if applicable)",
    )

    webhook_posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the webhook notification was posted",
    )

    webhook_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if webhook posting failed",
    )

    approval_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
        comment="Secure token for public approval links",
    )

    intent_hash_hex: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "SHA-256 hex digest of the RFC 8785 JCS-canonicalized intent envelope. "
            "Null for legacy requests created before this feature."
        ),
    )

    # Step-up verification fields
    step_up_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether this request requires hardware step-up before approval",
    )
    step_up_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether step-up verification has been completed",
    )
    step_up_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When step-up verification was completed",
    )
    step_up_key_name: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Name of the security key used for step-up",
    )
    step_up_key_id_tail: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Tail of the credential ID used for step-up (for audit display)",
    )

    # Assertion bytes — persisted at step_up_complete time for audit re-verification
    step_up_challenge_nonce: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary(32),
        nullable=True,
        comment="32-byte nonce; expected challenge = SHA-256(intent_hash_bytes || nonce)",
    )
    step_up_client_data_json: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Raw clientDataJSON bytes signed by the authenticator",
    )
    step_up_authenticator_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Raw authenticatorData bytes signed by the authenticator",
    )
    step_up_signature: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Raw ECDSA signature bytes from the FIDO2 assertion",
    )

    # ARKG previewSign step-up fields (webauthn_arkg_preview protocol)
    arkg_step_up_signature: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="ES256 signature from previewSign GetAssertion — signs tbs prehash",
    )
    arkg_step_up_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether ARKG previewSign step-up has been cryptographically verified",
    )
    arkg_step_up_derived_pk: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="P-256 uncompressed public key (65 bytes) from previewSign assertion",
    )

    # Authenticator sign counter at step-up time — stored for clone-detection audit.
    # A regressing counter is a FIDO2 security alert (potential credential cloning).
    step_up_sign_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Authenticator sign counter at the time of step-up",
    )

    # Full credential_id bytes — enables direct FK lookup in the receipt endpoint
    # instead of the probabilistic 8-character tail match.
    step_up_credential_id: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Full credential_id bytes of the authenticator used for step-up",
    )

    # AI decision tracking fields
    decided_by_ai: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether this request was decided by AI",
    )
    ai_model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="AI model that made the decision (if decided_by_ai=True)",
    )
    ai_confidence: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="AI confidence score for the decision (0.0-1.0)",
    )
    ai_reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="AI's reasoning for the approval/denial decision",
    )

    # ── Intent verifier fields (Phase 0: rule-based; Phase 1: LLM) ───────────
    # These are distinct from the decided_by_ai / ai_reasoning fields above.
    # decided_by_ai = AI *approves* on behalf of a human (ai_driven workflow mode).
    # intent_verified = AI *assesses risk* before the human sees the request.
    intent_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True when the intent verifier ran and produced a result.",
    )
    intent_risk_tier: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Risk tier from the intent verifier: low/medium/high/critical.",
    )
    intent_step_up_override: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment=(
            "True when the intent verifier forced step_up_required=True "
            "independently of the workflow's step_up_protocol setting."
        ),
    )
    intent_description_match_score: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment=(
            "How well the agent description matches actual tool_args (0.0–1.0). "
            "Populated by LLM verifier (Phase 1); rule-based leaves this NULL."
        ),
    )
    intent_flags: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
        comment='JSON array of FLAG_* strings, e.g. ["IRREVERSIBLE_OPERATION"].',
    )
    intent_reasoning: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable explanation from the LLM verifier (Phase 1).",
    )
    intent_model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment='Classifier used, e.g. "rule_based" or "claude-3-5-haiku-20241022".',
    )
    intent_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the intent verifier completed.",
    )
    intent_latency_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Wall-clock time of the intent verification call in milliseconds.",
    )

    # RDT (Role Delegation Token) fields - Phase A demo
    rdt_envelope: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="RDT envelope containing action_class, operation, context, reasoning, timestamp, approver_id, credential info, and WebAuthn signature/authenticator_data (Phase A: JSON+SHA256; Phase C: CBOR+domain-separation)",
    )
    action_class: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="RDT action classification: read|write|delete|deploy|spend|admin|privacy (inferred by AI reviewer or explicitly set)",
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account", back_populates="approval_requests"
    )
    tool_configuration: Mapped["ToolConfiguration"] = relationship(
        "ToolConfiguration", back_populates="approval_requests"
    )
    approval_workflow: Mapped["ApprovalWorkflow"] = relationship(
        "ApprovalWorkflow", back_populates="approval_requests"
    )
    events: Mapped[list["ApprovalEvent"]] = relationship(
        "ApprovalEvent",
        back_populates="approval_request",
        cascade="all, delete-orphan",
        order_by="ApprovalEvent.timestamp",
    )

    @property
    def step_up_protocol(self) -> Optional[str]:
        """Return the step-up protocol from the linked approval workflow.

        Lazy-loads via the SQLAlchemy relationship; safe in sync contexts.
        """
        if self.approval_workflow is not None:
            return self.approval_workflow.step_up_protocol
        return None

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<ApprovalRequest(id={self.id}, tool_name={self.tool_name}, "
            f"status={self.status}, requested_at={self.requested_at})>"
        )
