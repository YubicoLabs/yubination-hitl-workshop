"""Workshop-only, owner-bound browser migration authorization."""

import os
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from preloop.models import models
from preloop.models.crud.webauthn_credential import crud_webauthn_credential
from preloop.services.pq_authentication import credential_algorithm, key_hash
from preloop.services.fido_metadata import metadata_cache, pq_upgrade_support


def require_workshop() -> None:
    if os.getenv("WORKSHOP_ONBOARDING_ENABLED", "").lower() != "true":
        raise HTTPException(404, "Workshop migration is disabled")


def bound_credential(
    db: Session, user: models.User, credential_id: uuid.UUID
) -> models.UserWebAuthnCredential:
    credentials = crud_webauthn_credential.list_by_user(
        db, user_id=user.id, account_id=user.account_id
    )
    credential = next((item for item in credentials if item.id == credential_id), None)
    if credential is None or credential.uv_initialized is not True:
        raise HTTPException(403, "Credential is not available")
    return credential


def binding(
    user: models.User,
    credential: models.UserWebAuthnCredential,
    *,
    target_algorithm: int = -48,
) -> dict[str, Any]:
    return {
        "owner": str(user.id),
        "account": str(user.account_id),
        "source": str(credential.id),
        "key_hash": key_hash(credential),
        "version": user.pq_policy_version,
        "target": target_algorithm,
    }


def validate_binding(
    db: Session,
    user: models.User,
    expected: dict[str, Any],
    *,
    require_transition: bool = True,
) -> models.UserWebAuthnCredential:
    require_workshop()
    try:
        target_algorithm = expected["target"]
        if type(target_algorithm) is not int or target_algorithm not in (-7, -48):
            raise HTTPException(403, "Invalid migration target")
        credential = bound_credential(db, user, uuid.UUID(expected["source"]))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, "Invalid migration binding")
    if binding(user, credential, target_algorithm=target_algorithm) != expected:
        raise HTTPException(409, "Passkey settings changed; start again")
    if require_transition and credential.discoverable is not True:
        raise HTTPException(
            403, "Upgrade requires a credential recorded as discoverable"
        )
    if require_transition and target_algorithm == -48:
        entries, metadata_status = metadata_cache.snapshot()
        aaguid = str(uuid.UUID(bytes=bytes(credential.aaguid)))
        if pq_upgrade_support(entries, metadata_status, aaguid) is False:
            raise HTTPException(
                403,
                "This authenticator model lists only classical algorithms. Use a compatible beta key for this exercise.",
            )
    if require_transition and (
        user.pq_only is True
        or (credential_algorithm(credential), target_algorithm)
        not in ((-7, -48), (-48, -7))
    ):
        raise HTTPException(
            403,
            "Migration requires opposite ES256/ML-DSA-44 algorithms "
            "and a non-PQ-only policy",
        )
    return credential
