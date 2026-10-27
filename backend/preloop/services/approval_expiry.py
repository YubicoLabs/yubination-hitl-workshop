"""Enforce approval deadlines even when a background waiter has stopped."""

from datetime import datetime, timezone

from fastapi import HTTPException

from preloop.models.models.approval_request import ApprovalRequest


def require_unexpired_approval(request: ApprovalRequest) -> None:
    """Reject at the deadline; database timestamps without an offset are UTC."""
    expires_at = request.expires_at
    if expires_at is None:
        return
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= expires_at:
        raise HTTPException(
            status_code=410,
            detail="Approval request expired. Start a new action request.",
        )
