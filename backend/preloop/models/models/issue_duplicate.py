"""Issue Duplicate model."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, String, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


class IssueDuplicate(Base):
    """Issue Duplicate model."""

    __tablename__ = "issue_duplicate"

    issue1_id = Column(UUID(as_uuid=True), ForeignKey("issue.id"), nullable=False)
    issue2_id = Column(UUID(as_uuid=True), ForeignKey("issue.id"), nullable=False)
    decision = Column(String, nullable=False)
    decision_at = Column(DateTime, server_default=func.now())
    ai_model_id = Column(UUID(as_uuid=True), ForeignKey("ai_model.id"), nullable=False)
    ai_model_name = Column(String, nullable=True)
    reason = Column(Text, nullable=True)
    suggestion = Column(Text, nullable=True)
    resolution = Column(String, nullable=True)
    resolution_at = Column(DateTime, nullable=True)
    resolution_reason = Column(Text, nullable=True)
    resulting_issue1_id = Column(
        UUID(as_uuid=True), ForeignKey("issue.id"), nullable=True
    )
    resulting_issue2_id = Column(
        UUID(as_uuid=True), ForeignKey("issue.id"), nullable=True
    )

    issue1 = relationship("Issue", foreign_keys=[issue1_id])
    issue2 = relationship("Issue", foreign_keys=[issue2_id])
    resulting_issue1 = relationship("Issue", foreign_keys=[resulting_issue1_id])
    resulting_issue2 = relationship("Issue", foreign_keys=[resulting_issue2_id])
    ai_model = relationship("AIModel", foreign_keys=[ai_model_id])
