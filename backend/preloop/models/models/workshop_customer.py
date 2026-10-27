"""Additive per-account synthetic customer; historical shared data is untouched."""

import uuid
from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class WorkshopCustomer(Base):
    __tablename__ = "workshop_customer"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_workshop_customer_account"),
        UniqueConstraint("email", name="uq_workshop_customer_email"),
        CheckConstraint(
            "status IN ('standard', 'vip')", name="ck_workshop_customer_status"
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
