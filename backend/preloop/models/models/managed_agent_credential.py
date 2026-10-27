"""Durable credential metadata for managed agents."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .account import Account
    from .api_key import ApiKey
    from .managed_agent import ManagedAgent
    from .user import User


class ManagedAgentCredential(Base):
    """First-class durable credential record for one managed agent."""

    __tablename__ = "managed_agent_credential"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "managed_agent_id",
            "name",
            name="uq_managed_agent_credential_name",
        ),
        UniqueConstraint("api_key_id", name="uq_managed_agent_credential_api_key"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    managed_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("managed_agent.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_key.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credential_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="durable_api_key"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    key_prefix: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    last_issued_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account: Mapped["Account"] = relationship(
        "Account", back_populates="managed_agent_credentials"
    )
    managed_agent: Mapped["ManagedAgent"] = relationship(
        "ManagedAgent", back_populates="credentials"
    )
    api_key: Mapped["ApiKey"] = relationship(
        "ApiKey", back_populates="managed_agent_credential"
    )
    created_by_user: Mapped[Optional["User"]] = relationship("User")
