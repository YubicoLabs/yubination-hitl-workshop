"""WebAuthn credential and challenge session models."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_CHALLENGE_TTL_MINUTES = 5
_REG_SESSION_TTL_MINUTES = 5
_LOGIN_SESSION_TTL_MINUTES = 5


class UserWebAuthnCredential(Base):
    """A registered FIDO2 credential belonging to a user."""

    __tablename__ = "user_webauthn_credential"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True
    )
    public_key_cbor: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    aaguid: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    authentication_tested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    authentication_key_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )

    # ARKG previewSign fields (YubiKey 5.8+, webauthn_arkg_preview protocol)
    arkg_seed_pub_cbor: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True
    )
    arkg_derived_pk: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    arkg_seed_kh: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    arkg_derived_kh: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    arkg_protocol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # FIDO MDS snapshot — populated at registration from the FIDO Metadata Service JWT.
    # Allows the audit UI to display authenticator name, key protection, and icon without
    # a live MDS fetch. None for credentials registered before MDS enrichment was added.
    mds_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mds_key_protection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mds_icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Backup eligibility / state flags (FIDO2 spec §6.1.3 BE/BS bits).
    # backup_eligible: credential CAN be backed up to cloud (BE flag at registration).
    # backup_state: credential IS currently backed up (BS flag, updated each authentication).
    # uv_initialized: UV was asserted during registration; credentials without UV must not authenticate.
    # Residency provenance distinguishes credProps, saved required registration,
    # and browser discovery observations. Legacy missing evidence stays unknown.
    registration_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    discoverability_source: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    discoverable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    backup_eligible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    backup_state: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    uv_initialized: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)


class WebAuthnChallengeSession(Base):
    """Ephemeral challenge session for a WebAuthn ceremony.

    TTL is 5 minutes from created_at. Must be deleted immediately after
    the ceremony completes (success or failure).
    """

    __tablename__ = "webauthn_challenge_session"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fido2_state: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    challenge: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    challenge_nonce: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary(32), nullable=True
    )

    def is_expired(self) -> bool:
        """Return True if this session is older than the TTL."""
        if self.created_at is None:
            return True
        created = self.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > timedelta(
            minutes=_CHALLENGE_TTL_MINUTES
        )


class WebAuthnRegistrationSession(Base):
    """Ephemeral session for a WebAuthn credential registration ceremony.

    Stored in the DB so that begin and complete can land on different workers.
    Consumed (deleted) immediately after the ceremony completes.
    """

    __tablename__ = "webauthn_registration_session"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def is_expired(self) -> bool:
        """Return True if this session is past its expiry time."""
        if self.expires_at is None:
            return True
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp


class WebAuthnLoginSession(Base):
    """Ephemeral session for a WebAuthn login ceremony.

    No FK to user/account — discoverable-credential flow starts without knowing
    who the user is. user_id / account_id are populated by begin only when a
    specific user is being targeted (2FA path); they stay NULL for the
    discoverable (passwordless) path until complete resolves the credential.

    Consumed atomically via DELETE ... RETURNING to prevent TOCTOU replay.
    """

    __tablename__ = "webauthn_login_session"

    # Nullable — NULL for discoverable (passkey) flow until complete resolves user.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # Serialised fido2 state dict (JSON).
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Raw challenge bytes for receipt / audit logging.
    challenge: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # "passwordless" or "2fa"
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="passwordless"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def is_expired(self) -> bool:
        """Return True if this session is past its expiry time."""
        if self.expires_at is None:
            return True
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp
