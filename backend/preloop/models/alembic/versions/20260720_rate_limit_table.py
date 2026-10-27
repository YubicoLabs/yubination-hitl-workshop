"""Add webauthn_step_up_rate_limit table.

Revision ID: 20260720_rate_limit_table
Revises: 20260720_step_up_cred_id
Create Date: 2026-07-20

DB-backed fixed-window rate limiter for WebAuthn step-up endpoints.
Replaces the previous in-process dict that reset on restart and didn't
span multiple API processes.

Schema: one row per approval token (keyed by SHA-256 hash). Atomic
PostgreSQL upsert resets or increments the counter in a single
statement, so no separate SELECT+INSERT races are possible.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_rate_limit_table"
down_revision: Union[str, Sequence[str], None] = "20260720_step_up_cred_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_step_up_rate_limit",
        sa.Column(
            "token_hash",
            sa.String(64),
            nullable=False,
            primary_key=True,
            comment="SHA-256 hex of the approval token — one row per token",
        ),
        sa.Column(
            "hit_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of requests in the current window",
        ),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Start of the current fixed window",
        ),
    )


def downgrade() -> None:
    op.drop_table("webauthn_step_up_rate_limit")
