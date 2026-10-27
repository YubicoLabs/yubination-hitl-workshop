"""Account-scoped model pricing overrides for gateway cost estimates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModelPriceOverride(Base):
    """Pricing metadata that overrides default provider estimates for one account."""

    __tablename__ = "model_price_overrides"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_model.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    input_price_per_1k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    output_price_per_1k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cache_read_input_price_per_1k: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    cache_creation_input_price_per_1k: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    price_per_1k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    request_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prepaid_token_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prepaid_credit_balance_usd: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    effective_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account = relationship("Account")
    ai_model = relationship("AIModel")

    __table_args__ = (
        Index(
            "ix_model_price_overrides_lookup",
            "account_id",
            "model_alias",
            "provider_name",
            "is_active",
        ),
    )

    def to_pricing_dict(self) -> dict[str, float | str]:
        """Return the normalized pricing dictionary used by cost estimation."""
        pricing: dict[str, float | str] = {"currency": self.currency}
        for key in (
            "input_price_per_1k",
            "output_price_per_1k",
            "cache_read_input_price_per_1k",
            "cache_creation_input_price_per_1k",
            "price_per_1k",
            "request_price",
            "discount_percent",
            "prepaid_token_balance",
            "prepaid_credit_balance_usd",
        ):
            value = getattr(self, key)
            if value is not None:
                pricing[key] = float(value)
        return pricing
