"""Restore the login limiter inadvertently dropped by the RDT migration.

Existing credentials and login sessions are unaffected. Some installations
retained or repaired this table; adopt only a compatible schema without
resetting its security counters.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260914_restore_login_limit"
down_revision = "20260911_approval_decision_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table = "webauthn_login_rate_limit"
    if inspector.has_table(table):
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        expected = {
            "namespace": sa.String(8),
            "key_hash": sa.String(64),
            "hit_count": sa.Integer(),
            "window_start": sa.DateTime(timezone=True),
        }
        incompatible = []
        for name, required_type in expected.items():
            column = columns.get(name)
            if column is None:
                incompatible.append(f"missing {name}")
                continue
            actual_type = column["type"]
            if (
                column["nullable"]
                or not isinstance(actual_type, type(required_type))
                or getattr(actual_type, "length", None)
                != getattr(required_type, "length", None)
                or getattr(actual_type, "timezone", None)
                != getattr(required_type, "timezone", None)
            ):
                incompatible.append(f"invalid {name} type or nullability")
        if inspector.get_pk_constraint(table)["constrained_columns"] != [
            "namespace",
            "key_hash",
        ]:
            incompatible.append("invalid primary key")
        if incompatible:
            raise RuntimeError(
                f"Incompatible existing {table}: " + "; ".join(incompatible)
            )
        return
    op.create_table(
        "webauthn_login_rate_limit",
        sa.Column("namespace", sa.String(8), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("namespace", "key_hash"),
    )


def downgrade() -> None:
    # Previous application versions also require this table. Preserve counters
    # during rollback, including installations that already owned the table.
    pass
