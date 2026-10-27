"""Add intent verifier config columns to approval_workflow.

Revision ID: 20260910_intent_verifier_workflow_config
Revises: 20260908_intent_verifier
Create Date: 2026-09-10

Phase 1 of the adaptive intent verifier.  Adds four columns that let
operators opt in to LLM-based risk classification per workflow.

All columns are nullable or have safe server defaults so the migration
is fully backward-compatible — existing workflows behave identically
(intent_verification_enabled defaults to FALSE).

See deploy/gcp-iap-demo/INTENT_VERIFIER_DESIGN.md §Phase 1.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_iv_workflow_cfg"
down_revision: Union[str, Sequence[str], None] = "20260908_intent_verifier"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_workflow",
        sa.Column(
            "intent_verification_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment=(
                "Enable LLM-based intent verification for this workflow. "
                "When False, only the rule-based pre-filter runs."
            ),
        ),
    )
    op.add_column(
        "approval_workflow",
        sa.Column(
            "intent_verification_model",
            sa.String(100),
            nullable=True,
            comment=(
                "LLM model for intent verification, e.g. 'claude-3-5-haiku-20241022'. "
                "Inherits provider detection from model name (same as ai_model field). "
                "NULL = use service default."
            ),
        ),
    )
    op.add_column(
        "approval_workflow",
        sa.Column(
            "intent_risk_threshold",
            sa.String(20),
            nullable=False,
            server_default="high",
            comment=(
                "Minimum risk tier that triggers intent_step_up_override. "
                "One of: low, medium, high, critical. Default 'high'."
            ),
        ),
    )
    # Fix any rows created with the quoted server_default bug ('high' → high).
    op.execute(
        "UPDATE approval_workflow SET intent_risk_threshold = 'high' "
        "WHERE intent_risk_threshold = '''high'''"
    )
    op.add_column(
        "approval_workflow",
        sa.Column(
            "intent_fail_closed",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment=(
                "When True, LLM verifier timeout or error forces step_up_required=True. "
                "When False, falls back to workflow policy on failure."
            ),
        ),
    )


def downgrade() -> None:
    for col in (
        "intent_fail_closed",
        "intent_risk_threshold",
        "intent_verification_model",
        "intent_verification_enabled",
    ):
        op.drop_column("approval_workflow", col)
