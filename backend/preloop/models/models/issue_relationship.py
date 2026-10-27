"""IssueRelationship model."""

import uuid
from sqlalchemy import Float, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from .base import Base

from .issue import Issue


class IssueRelationship(Base):
    """Model for relationships between issues."""

    __tablename__ = "issue_relationship"

    source_issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue.id", ondelete="CASCADE"),
        primary_key=True,
    )
    target_issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue.id", ondelete="CASCADE"),
        primary_key=True,
    )
    type: Mapped[str] = mapped_column(String(50), primary_key=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_committed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comes_from_tracker: Mapped[bool] = mapped_column(Boolean, nullable=False)

    source_issue: Mapped["Issue"] = relationship(
        "Issue", foreign_keys=[source_issue_id]
    )
    target_issue: Mapped["Issue"] = relationship(
        "Issue", foreign_keys=[target_issue_id]
    )
