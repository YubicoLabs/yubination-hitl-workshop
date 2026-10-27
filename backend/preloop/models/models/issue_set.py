"""IssueSet model."""

from typing import Dict, List, Optional
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

from .ai_model import AIModel


class IssueSet(Base):
    """
    Represents a set of issues, often generated or curated by an AI model.
    """

    __tablename__ = "issue_set"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Using JSONB to store an array of issue IDs (which are strings).
    # This allows for efficient querying of subsets.
    issue_ids: Mapped[List[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )

    # Foreign key to the AI model that generated or is associated with this set.
    ai_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_model.id"), nullable=True, index=True
    )

    # Additional metadata about the issue set.
    meta_data: Mapped[Optional[Dict]] = mapped_column(JSONB, nullable=True)

    # Relationship to the AIModel.
    ai_model: Mapped[Optional["AIModel"]] = relationship(
        "AIModel", back_populates="issue_sets"
    )

    def __repr__(self):
        return (
            f"<IssueSet(id={self.id}, name='{self.name}', count={len(self.issue_ids)})>"
        )
