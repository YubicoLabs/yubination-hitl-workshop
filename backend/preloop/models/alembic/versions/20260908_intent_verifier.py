"""Add intent verifier fields to approval_request.

Revision ID: 20260908_intent_verifier
Revises: 20260804_user_mfa
Create Date: 2026-09-08

Phase 0 of the adaptive intent verifier feature.  Adds nine columns to
approval_request so the rule-based (and later LLM-based) classification
result can be stored for audit, receipt display, and UI warnings.

None of these columns affect existing rows — all are nullable or default
FALSE/NULL so the migration is fully backward-compatible.

See deploy/gcp-iap-demo/INTENT_VERIFIER_DESIGN.md for design context.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260908_intent_verifier"
down_revision: Union[str, Sequence[str], None] = "20260804_user_mfa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True when the intent verifier ran and produced a result.",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_risk_tier",
            sa.String(20),
            nullable=True,
            comment="Risk tier assigned by the intent verifier: low/medium/high/critical.",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_step_up_override",
            sa.Boolean(),
            nullable=True,
            comment=(
                "True when the intent verifier forced step_up_required=True "
                "independently of the workflow's step_up_protocol setting."
            ),
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_description_match_score",
            sa.Float(),
            nullable=True,
            comment=(
                "How well the agent's operation description matches the actual "
                "tool_args (0.0–1.0).  Populated by LLM verifier (Phase 1); "
                "rule-based sets this to NULL."
            ),
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_flags",
            JSONB(),
            nullable=True,
            comment=(
                "JSON array of FLAG_* strings from the intent verifier, e.g. "
                '["IRREVERSIBLE_OPERATION", "MISSING_BOUNDS"].'
            ),
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_reasoning",
            sa.Text(),
            nullable=True,
            comment="Human-readable explanation from the LLM verifier (Phase 1).",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_model",
            sa.String(100),
            nullable=True,
            comment='Classifier used, e.g. "rule_based" or "claude-3-5-haiku-20241022".',
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the intent verifier completed.",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_latency_ms",
            sa.Integer(),
            nullable=True,
            comment="Wall-clock time of the intent verification call in milliseconds.",
        ),
    )

    # Index on risk_tier to support dashboard queries filtering by tier.
    op.create_index(
        "ix_approval_request_intent_risk_tier",
        "approval_request",
        ["intent_risk_tier"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_approval_request_intent_risk_tier",
        table_name="approval_request",
    )
    for col in (
        "intent_latency_ms",
        "intent_verified_at",
        "intent_model",
        "intent_reasoning",
        "intent_flags",
        "intent_description_match_score",
        "intent_step_up_override",
        "intent_risk_tier",
        "intent_verified",
    ):
        op.drop_column("approval_request", col)
