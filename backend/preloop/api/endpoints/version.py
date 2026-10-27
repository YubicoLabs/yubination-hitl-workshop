import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session  # Import synchronous Session

from preloop.config import (
    SERVER_VERSION,
    MIN_CLIENT_VERSION,
    MAX_CLIENT_VERSION,
)  # Import constants directly
from preloop.api.auth import get_current_user  # Remove oauth2_scheme import
from preloop.schemas.version import VersionInfo
from preloop.utils import get_client_ip
from preloop.models.db.session import get_db_session  # Correct function name

# Account model is returned by get_current_user
from preloop.models.models.client_version_log import ClientVersionLog
from fastapi import HTTPException  # To catch auth errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/version", response_model=VersionInfo)
async def get_version_info(
    request: Request,
    x_client_version: Annotated[Optional[str], Header(alias="X-Client-Version")] = None,
    x_client_organization: Annotated[
        Optional[str], Header(alias="X-Client-Organization")
    ] = None,
    x_client_project: Annotated[Optional[str], Header(alias="X-Client-Project")] = None,
    x_additional_info: Annotated[
        Optional[str], Header(alias="X-Additional-Info")
    ] = None,
    db: Session = Depends(get_db_session),  # Use synchronous Session type hint
    # Removed token dependency: token: Optional[str] = Depends(oauth2_scheme),
):
    """
    Returns the server version information and logs the client version.

    Accepts an optional `X-Client-Version` header from the client.
    If an `Authorization: Bearer <token>` header is provided and valid,
    the associated account ID will also be logged.
    """
    client_ip = get_client_ip(request)
    account_id: Optional[int] = None
    current_user = None
    # Explicitly check header for optional authentication
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        try:
            # Manually attempt to get user if token exists
            current_user = get_current_user(token=token, db=db)
            account_id = current_user.account_id
        except HTTPException:
            # Ignore auth errors (invalid token, inactive user, etc.)
            logger.debug(
                "Optional authentication failed for /version endpoint (token provided but invalid/inactive)."
            )
            pass  # Keep account_id as None
        except Exception as e:
            # Log unexpected errors but don't fail the request
            logger.error(
                f"Unexpected error during optional auth in /version: {e}", exc_info=True
            )
            pass  # Keep account_id as None

    # Log the client version information
    log_entry = ClientVersionLog(
        ip_address=client_ip,
        client_version=x_client_version if x_client_version else "unknown",
        account_id=account_id,
        organization_identifier=x_client_organization,
        project_identifier=x_client_project,
    )
    db.add(log_entry)
    try:
        db.commit()  # Remove await for synchronous commit
        logger.info(
            f"Logged client version: IP={client_ip}, Version={x_client_version}, Org={x_client_organization}, Proj={x_client_project}, AccountID={account_id}, AdditionalInfo={x_additional_info}"
        )
    except Exception as e:
        db.rollback()  # Remove await for synchronous rollback
        logger.error(f"Failed to log client version: {e}", exc_info=True)
        # Continue even if logging fails, returning version info is primary goal

    return VersionInfo(
        server_version=SERVER_VERSION,
        min_client_version=MIN_CLIENT_VERSION,
        max_client_version=MAX_CLIENT_VERSION,
    )
