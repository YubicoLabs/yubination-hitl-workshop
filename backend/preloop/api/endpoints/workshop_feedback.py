"""Participant feedback HTTP boundary."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from preloop.api.auth import get_current_active_user
from preloop.api.auth.jwt import decode_token, oauth2_scheme
from preloop.models import crud, models
from preloop.models.db.session import get_db_session
from preloop.models.schemas.workshop_feedback import FeedbackInput

router = APIRouter(prefix="/workshop/feedback", tags=["Workshop feedback"])


async def human_participant(
    token: str = Depends(oauth2_scheme),
    user: models.User = Depends(get_current_active_user),
) -> models.User:
    """Require a human access JWT, not an API key or refresh credential."""
    claims = decode_token(token)
    if (
        claims.refresh is not False
        or claims.exp is None
        or claims.sub != str(user.id)
        or not user.is_active
    ):
        raise HTTPException(401, "Human access token required")
    return user


@router.get("", response_model=FeedbackInput | None)
def get_feedback(
    user: models.User = Depends(human_participant),
    db: Session = Depends(get_db_session),
) -> FeedbackInput | None:
    """Restore only this participant's response."""
    try:
        return crud.workshop_feedback.get_own(
            db, account_id=user.account_id, user_id=user.id
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Feedback temporarily unavailable") from None


@router.put("", response_model=FeedbackInput)
def save_feedback(
    answers: FeedbackInput,
    user: models.User = Depends(human_participant),
    db: Session = Depends(get_db_session),
) -> FeedbackInput:
    """Save or replace only this participant's response."""
    try:
        return crud.workshop_feedback.save_own(
            db, account_id=user.account_id, user_id=user.id, answers=answers
        )
    except ValueError:
        raise HTTPException(403, "Participant unavailable") from None
    except SQLAlchemyError:
        raise HTTPException(503, "Feedback could not be saved") from None
