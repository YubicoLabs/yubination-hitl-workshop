"""Runtime limiter tables registered for Alembic schema ownership.

These counters deliberately have no Base UUID/timestamps: their hashed keys
are the primary keys consumed by the atomic endpoint upserts. Registering the
Core tables prevents autogenerate from treating them as orphaned tables.
"""

import sqlalchemy as sa

from .base import Base

step_up_rate_limit = sa.Table(
    "webauthn_step_up_rate_limit",
    Base.metadata,
    sa.Column("token_hash", sa.String(64), primary_key=True),
    sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
)

login_rate_limit = sa.Table(
    "webauthn_login_rate_limit",
    Base.metadata,
    sa.Column("namespace", sa.String(8), primary_key=True),
    sa.Column("key_hash", sa.String(64), primary_key=True),
    sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column(
        "window_start",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
)
