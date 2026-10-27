"""Gateway interaction search corpus rows keyed to API usage."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.vector_types import VectorType
from .base import Base

if TYPE_CHECKING:
    from .api_usage import ApiUsage


class GatewayUsageSearchDocument(Base):
    """Normalized search corpus row for a captured gateway interaction."""

    __tablename__ = "gateway_usage_search_document"

    api_usage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_usage.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    searchable_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        VectorType(1536), nullable=True
    )
    meta_data: Mapped[Optional[Dict]] = mapped_column(JSONB, nullable=True)

    api_usage: Mapped["ApiUsage"] = relationship(
        "ApiUsage", back_populates="gateway_search_document"
    )
