"""Account/user scoped atomic participant feedback operations."""

from uuid import UUID, uuid4

from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from preloop.models import models
from preloop.models.schemas.workshop_feedback import FeedbackInput


def get_own(db: Session, *, account_id: UUID, user_id: UUID) -> FeedbackInput | None:
    """Read only the authenticated participant's current answers."""
    row = db.execute(
        select(models.WorkshopFeedback).where(
            models.WorkshopFeedback.account_id == account_id,
            models.WorkshopFeedback.user_id == user_id,
        )
    ).scalar_one_or_none()
    return FeedbackInput.model_validate(row) if row is not None else None


def save_own(
    db: Session, *, account_id: UUID, user_id: UUID, answers: FeedbackInput
) -> FeedbackInput:
    """Upsert under a unique constraint; acknowledge only a committed response."""
    values = answers.model_dump()
    statement = insert(models.WorkshopFeedback).from_select(
        ["id", "account_id", "user_id", *values],
        select(
            literal(uuid4()),
            models.User.account_id,
            models.User.id,
            *[literal(value) for value in values.values()],
        ).where(models.User.id == user_id, models.User.account_id == account_id),
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_workshop_feedback_user",
        set_={**values, "updated_at": func.now()},
        where=models.WorkshopFeedback.account_id == account_id,
    ).returning(
        models.WorkshopFeedback.recommendation,
        models.WorkshopFeedback.worked_well,
        models.WorkshopFeedback.could_improve,
    )
    try:
        row = db.execute(statement).mappings().one_or_none()
        if row is None:
            raise ValueError("Participant unavailable in this account")
        result = FeedbackInput.model_validate(dict(row))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
