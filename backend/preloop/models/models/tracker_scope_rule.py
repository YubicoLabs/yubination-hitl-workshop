"""Tracker Scope Rule model."""

import enum
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ScopeType(enum.Enum):
    """Enum for scope types."""

    ORGANIZATION = "ORGANIZATION"
    PROJECT = "PROJECT"


class RuleType(enum.Enum):
    """Enum for rule types."""

    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"


class TrackerScopeRule(Base):
    """Tracker Scope Rule model - represents a rule for including or excluding projects."""

    __tablename__ = "tracker_scope_rule"

    tracker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracker.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Possible values: ORGANIZATION, PROJECT",
    )
    rule_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Possible values: INCLUDE, EXCLUDE"
    )
    identifier: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="e.g., 'my-org' or 'my-org/my-repo'",
    )

    tracker: Mapped["Tracker"] = relationship("Tracker", back_populates="scope_rules")  # noqa: F821
