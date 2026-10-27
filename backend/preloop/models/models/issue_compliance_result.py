"""IssueComplianceResult model."""

import uuid
from typing import Optional, List
from sqlalchemy import Float, ForeignKey, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .issue import Issue


class IssueComplianceResult(Base):
    """Model for storing compliance results for an issue."""

    prompt_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    compliance_factor: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    suggestion: Mapped[str] = mapped_column(String, nullable=False)
    annotated_description: Mapped[Optional[List[dict]]] = mapped_column(
        JSON, nullable=True
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    issue: Mapped["Issue"] = relationship("Issue")
