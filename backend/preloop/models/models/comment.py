"""Comment model."""

import uuid
from typing import TYPE_CHECKING, Optional, List, Dict

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base

if TYPE_CHECKING:
    from .issue import Issue
    from .tracker import Tracker
    from .embedding import IssueEmbedding


class Comment(Base):
    """Comment model - represents a comment on an issue or other entities."""

    __tablename__ = "comment"

    body: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="issue",
        comment="Type of comment (e.g., 'issue', 'merge_request')",
    )
    external_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="External ID of the comment",
    )

    # Foreign keys
    issue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    author: Mapped[Optional[str]] = mapped_column(  # Reverted to Optional[str]
        String(255),  # Reverted to String(36)
        nullable=True,  # Allow comments from deleted users or system
        index=True,
    )
    tracker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracker.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="comments")
    tracker: Mapped["Tracker"] = relationship("Tracker", back_populates="comments")
    embeddings: Mapped[List["IssueEmbedding"]] = relationship(
        "IssueEmbedding", back_populates="comment", cascade="all, delete-orphan"
    )

    # Metadata stored as JSON (for custom fields, labels, etc.)
    meta_data: Mapped[Dict] = mapped_column(JSON, nullable=True, default=dict)

    def __repr__(self) -> str:
        return f"<Comment(id={self.id}, type='{self.type}', issue_id='{self.issue_id}', author='{self.author}')>"
