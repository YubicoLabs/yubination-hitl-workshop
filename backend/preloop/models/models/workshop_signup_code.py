"""Deployment-wide admission codes for workshop account signup."""

from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, String, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped

from .base import Base


workshop_signup_code_table = Table(
    "workshop_signup_code",
    Base.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("label", Text, nullable=True),
    Column("code_digest", String(64), unique=True, nullable=False),
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
)


class WorkshopSignupCode:
    """A reusable workshop code represented only by its digest."""

    id: Mapped[uuid.UUID]
    label: Mapped[str | None]
    code_digest: Mapped[str]
    created_at: Mapped[datetime]


Base.registry.map_imperatively(WorkshopSignupCode, workshop_signup_code_table)
