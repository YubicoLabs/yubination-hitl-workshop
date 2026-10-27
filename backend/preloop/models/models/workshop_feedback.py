"""One current workshop satisfaction response per participant."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkshopFeedback(Base):
    """Account-scoped feedback; not a learning assessment."""

    __tablename__ = "workshop_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_workshop_feedback_user"),
        CheckConstraint(
            "recommendation BETWEEN 1 AND 10", name="ck_workshop_feedback_rating"
        ),
        CheckConstraint(
            "char_length(worked_well) <= 2000", name="ck_workshop_feedback_worked"
        ),
        CheckConstraint(
            "char_length(could_improve) <= 2000", name="ck_workshop_feedback_improve"
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    recommendation: Mapped[int] = mapped_column(Integer, nullable=False)
    worked_well: Mapped[str | None] = mapped_column(Text)
    could_improve: Mapped[str | None] = mapped_column(Text)
