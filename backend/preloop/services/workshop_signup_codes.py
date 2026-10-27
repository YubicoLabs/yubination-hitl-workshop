"""Generate and validate reusable high-entropy workshop signup codes."""

import base64
import hashlib
import secrets

from sqlalchemy.orm import Session

from preloop.models import models
from preloop.models.crud import workshop_signup_code as code_crud

MAX_CODE_INPUT_LENGTH = 128
RANDOM_BYTES = 16


def _normalize(code: str) -> str | None:
    if len(code) > MAX_CODE_INPUT_LENGTH:
        return None
    normalized = code.strip().replace("-", "").upper()
    return normalized or None


def _digest(normalized_code: str) -> str:
    return hashlib.sha256(normalized_code.encode("ascii")).hexdigest()


def create(
    db: Session, *, label: str | None = None
) -> tuple[models.WorkshopSignupCode, str]:
    """Create a code and return its plaintext exactly once with its record."""
    while True:
        normalized = (
            base64.b32encode(secrets.token_bytes(RANDOM_BYTES)).decode().rstrip("=")
        )
        grouped = "-".join(
            normalized[index : index + 4] for index in range(0, len(normalized), 4)
        )
        digest = _digest(normalized)
        if code_crud.get_by_digest(db, code_digest=digest) is None:
            return code_crud.create(db, code_digest=digest, label=label), grouped


def is_valid(db: Session, *, code: str | None) -> bool:
    """Return whether an input normalizes to a currently stored code."""
    if code is None:
        return False
    normalized = _normalize(code)
    if normalized is None:
        return False
    try:
        digest = _digest(normalized)
    except UnicodeEncodeError:
        return False
    return code_crud.get_by_digest(db, code_digest=digest) is not None
