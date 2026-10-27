"""API endpoints for approval requests."""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from preloop.api.auth import get_current_active_user
from preloop.services.approval_service import ApprovalService
from preloop.models.crud import crud_approval_request
from preloop.models.db.session import get_async_db_session, get_db_session
from preloop.models.models import ApprovalRequest
from preloop.models.models.user import User
from preloop.models.schemas.approval_request import (
    ApprovalDecision,
    ApprovalRequestResponse,
    IntentHashVerificationResponse,
)
from preloop.services.rdt_intent import verify_intent_hash

router = APIRouter(
    prefix="/approval-requests",
    tags=["approval_requests"],
)


def _same_account(left: uuid.UUID | str, right: uuid.UUID | str) -> bool:
    """Compare ORM and serialized tenant IDs without accepting invalid identities."""
    try:
        return uuid.UUID(str(left)) == uuid.UUID(str(right))
    except (ValueError, TypeError, AttributeError):
        return False


@router.get("/{request_id}", response_model=ApprovalRequestResponse)
def get_approval_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db_session),
) -> ApprovalRequestResponse:
    """Get an approval request by ID.

    Args:
        request_id: Approval request ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Approval request

    Raises:
        HTTPException: If request not found or unauthorized
    """
    # Use CRUD layer with account_id filtering
    approval_request = crud_approval_request.get(
        db, id=str(request_id), account_id=current_user.account_id
    )

    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    response = ApprovalRequestResponse.model_validate(approval_request)

    # Populate ARKG proof fields when step-up was completed via ARKG previewSign
    if approval_request.arkg_step_up_verified:
        if approval_request.arkg_step_up_signature:
            response.arkg_step_up_signature_hex = (
                approval_request.arkg_step_up_signature.hex()
            )
        if approval_request.arkg_step_up_derived_pk:
            response.arkg_derived_pk_hex = bytes(
                approval_request.arkg_step_up_derived_pk
            ).hex()

    return response


@router.get(
    "/{request_id}/verify-intent",
    response_model=IntentHashVerificationResponse,
)
def verify_approval_intent(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db_session),
) -> IntentHashVerificationResponse:
    """Recompute the request's versioned Intent Hash for the current account."""
    approval_request = crud_approval_request.get(
        db, id=str(request_id), account_id=current_user.account_id
    )
    if approval_request is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if not approval_request.intent_hash_hex:
        raise HTTPException(status_code=422, detail="Intent Hash is not available")

    risk_tier = getattr(approval_request, "intent_risk_tier", None)
    flags = getattr(approval_request, "intent_flags", None)
    intact = verify_intent_hash(
        approval_request.intent_hash_hex,
        account_id=approval_request.account_id,
        approval_request_id=approval_request.id,
        tool_name=approval_request.tool_name,
        tool_args=approval_request.tool_args or {},
        requested_at=approval_request.requested_at,
        intent_risk_tier=risk_tier,
        intent_flags=flags,
    )
    return IntentHashVerificationResponse(
        request_id=approval_request.id,
        envelope_version=2 if risk_tier is not None else 1,
        intent_intact=intact,
    )


@router.get("", response_model=list[ApprovalRequestResponse])
def list_approval_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    execution_id: Optional[str] = Query(None, description="Filter by execution ID"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
    skip: int = Query(0, description="Number of results to skip"),
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db_session),
) -> list[ApprovalRequest]:
    """List approval requests for the current account.

    Args:
        status: Filter by status (pending, approved, declined, etc.)
        execution_id: Filter by execution ID
        limit: Maximum number of results
        skip: Number of results to skip
        current_user: Current authenticated user

    Returns:
        List of approval requests
    """
    # Use CRUD layer to get approval requests with filters
    return crud_approval_request.get_multi_by_account(
        db,
        account_id=current_user.account_id,
        execution_id=execution_id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.post("/{request_id}/approve", response_model=ApprovalRequestResponse)
async def approve_request(
    request_id: uuid.UUID,
    decision: ApprovalDecision,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> ApprovalRequestResponse:
    """Approve an approval request.

    Args:
        request_id: Approval request ID
        decision: Approval decision with optional comment
        request: HTTP request
        current_user: Current authenticated user

    Returns:
        Updated approval request

    Raises:
        HTTPException: If request not found or unauthorized
    """
    # Get base URL from request
    base_url = os.getenv("PRELOOP_URL", str(request.base_url).rstrip("/"))

    async with get_async_db_session() as db:
        approval_service = ApprovalService(db, base_url)

        # Get approval request
        approval_request = await approval_service.get_approval_request(request_id)
        if not approval_request:
            raise HTTPException(status_code=404, detail="Approval request not found")

        # Check authorization
        if not _same_account(approval_request.account_id, current_user.account_id):
            raise HTTPException(
                status_code=403, detail="Not authorized to approve this request"
            )

        # Check if already resolved
        if approval_request.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Request already {approval_request.status}",
            )

        # Approve (pass user_id for quorum tracking)
        updated = await approval_service.approve_request(
            request_id, decision.comment, user_id=current_user.id
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to approve request")

        # Convert to Pydantic model while session is still open to avoid
        # DetachedInstanceError during response serialization.
        return ApprovalRequestResponse.model_validate(updated)


@router.post("/{request_id}/decline", response_model=ApprovalRequestResponse)
async def decline_request(
    request_id: uuid.UUID,
    decision: ApprovalDecision,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> ApprovalRequestResponse:
    """Decline an approval request.

    Args:
        request_id: Approval request ID
        decision: Approval decision with optional comment
        request: HTTP request
        current_user: Current authenticated user

    Returns:
        Updated approval request

    Raises:
        HTTPException: If request not found or unauthorized
    """
    # Get base URL from request
    base_url = os.getenv("PRELOOP_URL", str(request.base_url).rstrip("/"))

    async with get_async_db_session() as db:
        approval_service = ApprovalService(db, base_url)

        # Get approval request
        approval_request = await approval_service.get_approval_request(request_id)
        if not approval_request:
            raise HTTPException(status_code=404, detail="Approval request not found")

        # Check authorization
        if not _same_account(approval_request.account_id, current_user.account_id):
            raise HTTPException(
                status_code=403, detail="Not authorized to decline this request"
            )

        # Check if already resolved
        if approval_request.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Request already {approval_request.status}",
            )

        # Decline (pass user_id for quorum tracking)
        updated = await approval_service.decline_request(
            request_id, decision.comment, user_id=current_user.id
        )
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to decline request")

        # Convert to Pydantic model while session is still open to avoid
        # DetachedInstanceError during response serialization.
        return ApprovalRequestResponse.model_validate(updated)


@router.post("/{request_id}/decide", response_model=ApprovalRequestResponse)
async def decide_request(
    request_id: uuid.UUID,
    decision: ApprovalDecision,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> ApprovalRequestResponse:
    """Approve or decline an approval request based on decision.approved.

    This is a convenience endpoint that calls approve or decline based on
    the decision.approved boolean.

    Args:
        request_id: Approval request ID
        decision: Approval decision with approved flag and optional comment
        request: HTTP request
        current_user: Current authenticated user

    Returns:
        Updated approval request

    Raises:
        HTTPException: If request not found or unauthorized
    """
    # Get base URL from request
    base_url = os.getenv("PRELOOP_URL", str(request.base_url).rstrip("/"))

    async with get_async_db_session() as db:
        approval_service = ApprovalService(db, base_url)

        # Get approval request
        approval_request = await approval_service.get_approval_request(request_id)
        if not approval_request:
            raise HTTPException(status_code=404, detail="Approval request not found")

        # Check authorization
        if not _same_account(approval_request.account_id, current_user.account_id):
            raise HTTPException(
                status_code=403, detail="Not authorized to decide on this request"
            )

        # Check if already resolved
        if approval_request.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Request already {approval_request.status}",
            )

        # Approve or decline based on decision (pass user_id for quorum tracking)
        if decision.approved:
            updated = await approval_service.approve_request(
                request_id, decision.comment, user_id=current_user.id
            )
        else:
            updated = await approval_service.decline_request(
                request_id, decision.comment, user_id=current_user.id
            )

        if not updated:
            raise HTTPException(status_code=500, detail="Failed to process decision")

        # Convert to Pydantic model while session is still open to avoid
        # DetachedInstanceError during response serialization.
        return ApprovalRequestResponse.model_validate(updated)


@router.get("/{request_id}/rdt-envelope")
def get_rdt_envelope(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db_session),
) -> dict:
    """Get the RDT envelope for an approved request (Phase A demo endpoint - READ ONLY).

    Security: Changed from POST to GET to prevent tampering with audit trail.
    The envelope is constructed and stored automatically during step-up completion.

    Args:
        request_id: Approval request ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        RDT envelope dict or error

    Raises:
        HTTPException: If request not found or no envelope exists
    """
    # Get approval request
    approval_request = crud_approval_request.get(
        db, id=str(request_id), account_id=current_user.account_id
    )

    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if not approval_request.rdt_envelope:
        raise HTTPException(
            status_code=404,
            detail="No RDT envelope - request must complete step-up verification first",
        )

    return approval_request.rdt_envelope
