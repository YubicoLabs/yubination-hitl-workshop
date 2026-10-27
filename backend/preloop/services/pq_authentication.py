"""Per-user sign-in acceptance, independent of hardware/metadata assurance."""

import hashlib
from typing import Any

from fido2.cbor import decode
from fido2.cose import CoseKey

PQ_ALGORITHMS = frozenset({-48})


def credential_algorithm(credential: Any) -> int | None:
    """Return a supported, parsable stored COSE algorithm; labels are not evidence."""
    try:
        key = decode(credential.public_key_cbor)
        algorithm = key[3]
        if type(algorithm) is not int:
            return None
        parsed = CoseKey.parse(key)
        if parsed.ALGORITHM != algorithm:
            return None
        if algorithm in PQ_ALGORITHMS:
            from cryptography.hazmat.primitives.asymmetric.mldsa import MLDSA44PublicKey

            if key.get(1) != 7 or not isinstance(key.get(-1), bytes):
                return None
            MLDSA44PublicKey.from_public_bytes(key[-1])
        return algorithm
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None


def eligible(credential: Any) -> bool:
    return (
        credential.uv_initialized is True
        and credential_algorithm(credential) in PQ_ALGORITHMS
    )


def key_hash(credential: Any) -> str:
    return hashlib.sha256(credential.public_key_cbor).hexdigest()


def authentication_tested(credential: Any) -> bool:
    """A successful authentication remains evidence only for the tested key."""
    return (
        credential.authentication_tested_at is not None
        and credential.authentication_key_hash == key_hash(credential)
    )


def tested(credential: Any) -> bool:
    """Count only algorithm-eligible tested credentials toward PQ readiness."""
    return eligible(credential) and authentication_tested(credential)


def policy_status(user: Any, credentials: list[Any]) -> dict[str, Any]:
    eligible_count = sum(eligible(c) for c in credentials)
    tested_count = sum(tested(c) for c in credentials)
    warning = None
    if user.pq_only and eligible_count == 1:
        warning = "Only one PQ passkey remains. Add and test a replacement. If you lose access to the remaining key, this demo account has no recovery option."
    elif user.pq_only and eligible_count == 0:
        warning = "No eligible PQ passkey remains. This demo account has no recovery option. Existing sessions may remain active."
    return dict(
        enabled=user.pq_only,
        version=user.pq_policy_version,
        eligible_count=eligible_count,
        tested_count=tested_count,
        ready=tested_count >= 2,
        warning=warning,
        credentials=[
            dict(
                id=str(c.id),
                cose_algorithm=credential_algorithm(c),
                eligible=eligible(c),
                authentication_tested_at=c.authentication_tested_at.isoformat()
                if authentication_tested(c)
                else None,
            )
            for c in credentials
        ],
    )
