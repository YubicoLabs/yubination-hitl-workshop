"""Add arkg_step_up_derived_pk to approval_request.

Revision ID: 20260720_arkg_step_up_derived_pk
Revises: 20260717_add_arkg_columns
Create Date: 2026-07-20

Stores the derived P-256 public key captured from the previewSign extension
at step-up time, alongside the signature already stored in arkg_step_up_signature.
Needed for the receipt so auditors can verify the ARKG signature offline even if
the credential is de-enrolled later.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_arkg_step_up_derived_pk"
down_revision: Union[str, Sequence[str], None] = "20260717_add_arkg_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column(
            "arkg_step_up_derived_pk",
            sa.LargeBinary(),
            nullable=True,
            comment="P-256 uncompressed public key (65 bytes) from previewSign assertion",
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "arkg_step_up_derived_pk")
