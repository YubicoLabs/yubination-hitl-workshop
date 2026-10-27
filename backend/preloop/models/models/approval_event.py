"""Approval event model for tracking detailed approval workflow events."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ApprovalEvent(Base):
    """Individual events in an approval workflow for audit trail and agent polling.

    Tracks every step of the approval process: request creation, notifications sent,
    individual votes with comments, escalations, and final resolution.
    """

    __tablename__ = "approval_event"

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the approval request",
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The account this event belongs to",
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Event type: approval_requested, notification_sent, vote_received, escalation_triggered, approval_complete, tool_executed, expired, cancelled",
    )

    detail: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable description of the event",
    )

    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Approver comment (for vote_received events)",
    )

    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User who triggered the event (if applicable)",
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When the event occurred",
    )

    # Relationships
    approval_request: Mapped["ApprovalRequest"] = relationship(
        "ApprovalRequest", back_populates="events"
    )

    def __repr__(self) -> str:
        return (
            f"<ApprovalEvent(type={self.event_type}, "
            f"request_id={self.approval_request_id}, "
            f"timestamp={self.timestamp})>"
        )
