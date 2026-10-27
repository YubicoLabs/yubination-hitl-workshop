"""Authenticated, rate-limited FIDO metadata for model information, not attestation.

Trust anchor: GlobalSign Root R46, announced by FIDO in August 2026.
The independently installed CA bundle supplies its bytes; the fingerprint pins it.
"""

import base64
import json
import logging
import os
from pathlib import Path
import ssl
import tempfile
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener

import certifi
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.verification import PolicyBuilder, Store

logger = logging.getLogger(__name__)

ROOT_SHA256 = "4fa3126d8d3a11d1c4855a4f807cbad6cf919d3a5a88b03bea2c6372d93c40c9"
MDS_URL = "https://mds.fidoalliance.org/"
MAX_BYTES = 20 * 1024 * 1024


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _root() -> x509.Certificate:
    for certificate in x509.load_pem_x509_certificates(
        Path(certifi.where()).read_bytes()
    ):
        if certificate.fingerprint(hashes.SHA256()).hex() == ROOT_SHA256:
            return certificate
    raise ValueError("Pinned MDS root is absent from installed CA bundle")


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise ValueError("Metadata redirects are not allowed")


def _read(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "preloop-mds/2.0"})
    opener = build_opener(
        _NoRedirects(),
        HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
    )
    with opener.open(request, timeout=20) as response:
        value = response.read(MAX_BYTES + 1)
    if len(value) > MAX_BYTES:
        raise ValueError("Metadata response exceeds limit")
    return value


def verify_blob(
    blob: str,
    root: x509.Certificate,
    now: datetime,
    crls_for: Callable[[x509.Certificate], list[x509.CertificateRevocationList]],
) -> dict[str, Any]:
    """Verify signer path, fresh signed CRLs, JWS and payload freshness.

    The CRL loader is an I/O boundary. This does not verify authenticator attestation.
    """
    header_part, payload_part, signature_part = blob.strip().split(".")
    header = json.loads(_decode(header_part))
    if (
        header.get("crit")
        or header.get("x5u")
        or header.get("alg") not in ("RS256", "ES256")
    ):
        raise ValueError("Unsupported MDS JWS header")
    chain = [
        x509.load_der_x509_certificate(base64.b64decode(value, validate=True))
        for value in header["x5c"]
    ]
    if not chain or len(chain) > 5:
        raise ValueError("Invalid signer chain")
    verified = (
        PolicyBuilder()
        .store(Store([root]))
        .time(now)
        .build_server_verifier(x509.DNSName("mds.fidoalliance.org"))
        .verify(chain[0], chain[1:])
    )
    valid_until = min(c.not_valid_after_utc.timestamp() for c in verified)
    for certificate, issuer in zip(verified, verified[1:], strict=False):
        valid = False
        for crl in crls_for(certificate):
            if crl.issuer != issuer.subject or not crl.is_signature_valid(
                issuer.public_key()
            ):
                continue
            if (
                crl.next_update_utc is None
                or not crl.last_update_utc <= now < crl.next_update_utc
            ):
                continue
            # Unsupported indirect/delta CRLs cannot establish complete revocation status.
            if any(
                isinstance(
                    e.value, (x509.DeltaCRLIndicator, x509.IssuingDistributionPoint)
                )
                for e in crl.extensions
            ):
                continue
            if crl.get_revoked_certificate_by_serial_number(certificate.serial_number):
                raise ValueError("MDS signer revoked")
            valid_until = min(valid_until, crl.next_update_utc.timestamp())
            valid = True
        if not valid:
            raise ValueError("Current signer revocation evidence unavailable")
    key = chain[0].public_key()
    signature = _decode(signature_part)
    message = f"{header_part}.{payload_part}".encode("ascii")
    if header["alg"] == "RS256" and isinstance(key, rsa.RSAPublicKey):
        key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
    elif (
        header["alg"] == "ES256"
        and isinstance(key, ec.EllipticCurvePublicKey)
        and isinstance(key.curve, ec.SECP256R1)
    ):
        if len(signature) != 64:
            raise ValueError("Invalid ES256 signature length")
        der = encode_dss_signature(
            int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
        )
        key.verify(der, message, ec.ECDSA(hashes.SHA256()))
    else:
        raise ValueError("MDS algorithm/key mismatch")
    payload = json.loads(_decode(payload_part))
    if (
        datetime.fromisoformat(payload["nextUpdate"]).replace(tzinfo=timezone.utc)
        <= now
    ):
        raise ValueError("MDS metadata expired")
    if type(payload.get("no")) is not int or payload["no"] < 0:
        raise ValueError("Invalid MDS serial")
    if not isinstance(payload.get("entries"), list) or not all(
        isinstance(e, dict) for e in payload["entries"]
    ):
        raise ValueError("Invalid MDS entries")
    payload["_verified_until"] = min(
        valid_until,
        datetime.fromisoformat(payload["nextUpdate"])
        .replace(tzinfo=timezone.utc)
        .timestamp(),
    )
    return payload


class MetadataCache:
    """One monthly refresh per process; signed disk cache and failure backoff.

    Expired/unverifiable data never becomes a current model match. Legacy decoded
    caches are intentionally ignored. CRLs are fetched only from GlobalSign URLs
    found in a verified chain and cached until their signed expiry.
    """

    def __init__(self, path: Path, fetch: Callable[[str], bytes] = _read):
        self.path = path
        self.fetch = fetch
        self.lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.state: dict[str, Any] = {}
        self.payload: dict[str, Any] | None = None
        self.status = "unavailable"
        self.checked_until = 0.0

    def _crls(
        self, certificate: x509.Certificate
    ) -> list[x509.CertificateRevocationList]:
        points = certificate.extensions.get_extension_for_class(
            x509.CRLDistributionPoints
        ).value
        result = []
        for point in points:
            for name in point.full_name or []:
                if not isinstance(name, x509.UniformResourceIdentifier):
                    continue
                parsed = urlparse(name.value)
                host = parsed.hostname or ""
                if (
                    parsed.scheme not in ("http", "https")
                    or not host.endswith(".globalsign.com")
                    or parsed.username
                    or parsed.port
                ):
                    continue
                # Fetch via TLS even when the authenticated certificate lists HTTP.
                url = parsed._replace(scheme="https").geturl()
                cached = self.state.setdefault("crls", {}).get(url)
                crl = (
                    x509.load_der_x509_crl(base64.b64decode(cached)) if cached else None
                )
                now = datetime.now(timezone.utc)
                if (
                    crl is None
                    or crl.next_update_utc is None
                    or now >= crl.next_update_utc
                ):
                    raw = self.fetch(url)
                    crl = x509.load_der_x509_crl(raw)
                    self.state["crls"][url] = base64.b64encode(raw).decode()
                result.append(crl)
        return result

    def _save(self) -> None:
        name = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, delete=False
            ) as output:
                name = output.name
                json.dump(self.state, output)
            os.replace(name, self.path)
        except OSError:
            pass
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def snapshot(self) -> tuple[list[dict[str, Any]], str]:
        """Return only a current verified snapshot, never wait on network or locks."""
        now = time.time()
        payload = self.payload
        if payload and now < min(self.checked_until, payload["_verified_until"]):
            return payload["entries"], "current"
        status = "stale" if payload else "unavailable"
        if self.refresh_lock.acquire(blocking=False):

            def refresh() -> None:
                try:
                    self.entries()
                finally:
                    self.refresh_lock.release()

            threading.Thread(target=refresh, daemon=True, name="mds-refresh").start()
        return [], status

    def entries(self) -> list[dict[str, Any]]:
        with self.lock:
            now = time.time()
            if self.payload and now < min(
                self.checked_until, self.payload["_verified_until"]
            ):
                return self.payload["entries"]
            if not self.state:
                try:
                    disk = json.loads(self.path.read_text())
                    if isinstance(disk, dict):
                        self.state = disk
                except (OSError, ValueError):
                    pass
            if self.state.get("source_url") != MDS_URL:
                # A failed retired endpoint must not suppress the first attempt
                # against the configured canonical source. Preserve signed data,
                # CRLs and serial floor; all verification still runs below.
                self.state["retry_after"] = 0
                self.state["source_url"] = MDS_URL
            if now < self.state.get("retry_after", 0):
                # Persisted blob verification may fetch CRLs; honor cooldown first.
                if self.payload and now < self.payload["_verified_until"]:
                    return self.payload["entries"]
                return []
            previous = self.state.get("blob")
            # Authenticate persisted bytes again; never trust persisted parsed fields.
            if previous:
                try:
                    self.payload = verify_blob(
                        previous, _root(), datetime.now(timezone.utc), self._crls
                    )
                    self.status = "current"
                    expiry = self.payload["_verified_until"]
                    self.checked_until = min(now + 3600, expiry)
                    # Signed nextUpdate and CRL expiry are verified above.
                    # Otherwise reuse the registry for 30 days, not per-day.
                    if now - self.state.get("fetched_at", 0) < 30 * 86400:
                        return self.payload["entries"]
                except Exception:
                    self.payload = None
                    self.status = "stale"
            try:
                raw = self.fetch(MDS_URL).decode().strip()
                payload = verify_blob(
                    raw, _root(), datetime.now(timezone.utc), self._crls
                )
                # Retain a monotonic floor even if the old signed payload expired.
                old_serial = self.state.get("serial", -1)
                if payload["no"] < old_serial or (
                    payload["no"] == old_serial and previous and raw != previous
                ):
                    raise ValueError("MDS rollback or changed same-serial payload")
                self.state.update(
                    blob=raw, serial=payload["no"], fetched_at=now, retry_after=0
                )
                self.payload = payload
                self.status = "current"
                self.checked_until = min(now + 3600, payload["_verified_until"])
            except Exception as error:
                logger.warning(
                    "FIDO metadata refresh failed: %s (HTTP status %s)",
                    type(error).__name__,
                    getattr(error, "code", None),
                )
                retry = now + 3600
                if isinstance(error, HTTPError) and error.headers:
                    value = error.headers.get("Retry-After")
                    if value:
                        try:
                            retry = max(retry, now + float(value))
                        except ValueError:
                            try:
                                retry = max(
                                    retry, parsedate_to_datetime(value).timestamp()
                                )
                            except (ValueError, TypeError, OverflowError):
                                pass
                self.state["retry_after"] = retry
            self._save()
            return self.payload["entries"] if self.payload else []


metadata_cache = MetadataCache(
    Path(os.getenv("MDS_CACHE_DIR", tempfile.gettempdir()))
    / "preloop_mds_signed_v2.json"
)


# Explicit FIDO registry strings only. Unknown/future algorithms are not
# evidence of classical-only capability. This is model metadata, not attestation.
_CLASSICAL_AUTHENTICATION_ALGORITHMS = frozenset(
    {
        "secp256r1_ecdsa_sha256_raw",
        "secp256r1_ecdsa_sha256_der",
        "secp256k1_ecdsa_sha256_raw",
        "secp256k1_ecdsa_sha256_der",
        "rsassa_pss_sha256_raw",
        "rsassa_pss_sha256_der",
        "rsassa_pss_sha384_raw",
        "rsassa_pss_sha512_raw",
        "rsassa_pkcsv15_sha256_raw",
        "rsassa_pkcsv15_sha384_raw",
        "rsassa_pkcsv15_sha512_raw",
        "secp384r1_ecdsa_sha384_raw",
        "secp521r1_ecdsa_sha512_raw",
        "ed25519_eddsa_sha512_raw",
        "ed448_eddsa_sha512_raw",
    }
)


def pq_upgrade_support(
    entries: list[dict[str, Any]], status: str, aaguid: str
) -> bool | None:
    """Return False only for current verified classical-only model evidence."""
    if status != "current" or aaguid == "00000000-0000-0000-0000-000000000000":
        return None
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("aaguid"), str)
        and entry["aaguid"].lower() == aaguid.lower()
    ]
    if len(matches) != 1:
        return None
    statement = matches[0].get("metadataStatement")
    algorithms = (
        statement.get("authenticationAlgorithms")
        if isinstance(statement, dict)
        else None
    )
    if (
        isinstance(algorithms, list)
        and algorithms
        and all(
            isinstance(algorithm, str)
            and algorithm in _CLASSICAL_AUTHENTICATION_ALGORITHMS
            for algorithm in algorithms
        )
    ):
        return False
    return None
