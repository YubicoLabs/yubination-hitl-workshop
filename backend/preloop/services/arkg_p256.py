"""ARKG-P256 key derivation and ES256 verification for the previewSign showcase.

Implements the Relying Party side of ARKG-BL-EC-Add with HMAC-KEM (HKDF-SHA-256),
for derived public-key verification of PreviewSign assertions.

Draft: draft-bradleylundberg-cfrg-arkg-09

Usage at enrollment:
    seed = parse_arkg_seed_from_cbor(cose_key_cbor)
    derived = arkg_derive_public_key(seed, user_id.bytes, b"preloop-approval-audit")
    # store derived.public_key (arkg_derived_pk) and derived.key_handle (arkg_derived_kh)

Usage at verification:
    ok = verify_arkg_signature(arkg_derived_pk, tbs_bytes, signature_bytes)
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fido2.cbor import decode as cbor_decode
from fido2.cbor import encode as cbor_encode

# ---------------------------------------------------------------------------
# P-256 constants
# ---------------------------------------------------------------------------

_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_A = _P - 3  # curve parameter a = -3 mod P
_Gx = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_Gy = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B

_DST_EXT = b"ARKG-P256"

# expand_message_xmd L for P-256: ceil((256 + 128) / 8) = 48
_XMD_L = 48


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ARKGPublicSeed:
    pk_bl: Tuple[int, int]  # (x, y) affine P-256 point — blinding base key
    pk_kem: Tuple[int, int]  # (x, y) affine P-256 point — KEM public key


@dataclass
class ARKGDerived:
    public_key: bytes  # 65-byte uncompressed P-256 point (0x04 || x || y)
    key_handle: bytes  # HMAC-KEM ciphertext = 16-byte tag || 65-byte eph_pk = 81 bytes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_arkg_seed_from_cbor(cose_key_cbor: bytes) -> ARKGPublicSeed:
    """Parse an ARKG public seed from the previewSign MakeCredential COSE key.

    The COSE key map has kty=-65537 (Yubico custom), with sub-keys:
      -1: COSE EC2 key for pk_bl
      -2: COSE EC2 key for pk_kem
    """
    try:
        cose_key = cbor_decode(cose_key_cbor)
    except Exception as exc:
        raise ValueError(f"Failed to decode ARKG seed COSE key CBOR: {exc}") from exc

    if not isinstance(cose_key, dict):
        raise ValueError("ARKG seed COSE key must be a CBOR map")

    pk_bl_cose = cose_key.get(-1)
    pk_kem_cose = cose_key.get(-2)

    if pk_bl_cose is None:
        raise ValueError("ARKG seed COSE key missing pk_bl at index -1")
    if pk_kem_cose is None:
        raise ValueError("ARKG seed COSE key missing pk_kem at index -2")

    return ARKGPublicSeed(
        pk_bl=_cose_ec2_to_point(pk_bl_cose, "pk_bl"),
        pk_kem=_cose_ec2_to_point(pk_kem_cose, "pk_kem"),
    )


def arkg_derive_public_key(
    seed: ARKGPublicSeed,
    ikm: bytes,
    ctx: bytes,
) -> ARKGDerived:
    """Derive an ARKG public key and key handle from a seed.

    Args:
        seed: Parsed from the YubiKey MakeCredential previewSign output.
        ikm: Input keying material — use user_id.bytes for stable single-key derivation.
        ctx: Domain-separation context string (e.g. b"preloop-approval-audit").

    Returns:
        ARKGDerived where public_key is stored as arkg_derived_pk and key_handle
        is stored as arkg_derived_kh (used in encode_arkg_sign_args → additionalArgs).
    """
    if len(ctx) > 64:
        raise ValueError(f"ctx must be ≤64 bytes, got {len(ctx)}")

    ctx_prime = bytes([len(ctx)]) + ctx
    ctx_kem = b"ARKG-Derive-Key-KEM." + ctx_prime
    ctx_bl = b"ARKG-Derive-Key-BL." + ctx_prime

    ikm_tau, c = _hmac_kem_encaps(seed.pk_kem, ikm, ctx_kem)
    tau = _bl_prf(ikm_tau, ctx_bl)
    pk_prime = _bl_blind_public_key(seed.pk_bl, tau)

    x, y = pk_prime
    pk_bytes = b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")

    return ARKGDerived(public_key=pk_bytes, key_handle=c)


def encode_arkg_sign_args(alg: int, arkg_kh: bytes, ctx: bytes) -> bytes:
    """Encode ARKG COSE_Sign_Args for the previewSign GetAssertion additionalArgs.

    Produces CBOR map {3: alg, -1: arkg_kh, -2: ctx} as expected by the
    native host when constructing the CTAP2 extension.

    Args:
        alg: COSE algorithm ID (-65539 = COSE_ALG_ESP256_ARKG for previewSign).
        arkg_kh: arkg_derived_kh bytes (from ARKGDerived.key_handle).
        ctx: Same context bytes used at derivation time.
    """
    return cbor_encode({3: alg, -1: arkg_kh, -2: ctx})


def verify_arkg_signature(
    derived_public_key: bytes,
    tbs: bytes,
    signature: bytes,
) -> bool:
    """Verify an ES256 previewSign signature against the ARKG-derived public key.

    The YubiKey's previewSign extension uses prehash ECDSA: `tbs` is the 32-byte
    digest that the device signs directly without re-hashing. This is why we use
    hashes.Prehashed() — calling ECDSA(SHA256) would double-hash and always fail.

    Args:
        derived_public_key: 65-byte uncompressed P-256 point (0x04 prefix), stored
            as arkg_derived_pk at enrollment time.
        tbs: The 32-byte prehash (SHA-256 of canonical approval JSON) passed to the
            device in the signByCredential extension field.
        signature: DER-encoded ECDSA signature from the previewSign result.

    Returns:
        True if the signature is cryptographically valid, False otherwise.
    """
    if len(derived_public_key) != 65 or derived_public_key[0] != 0x04:
        raise ValueError(
            "derived_public_key must be a 65-byte uncompressed P-256 point"
        )

    try:
        x = int.from_bytes(derived_public_key[1:33], "big")
        y = int.from_bytes(derived_public_key[33:], "big")
        pub_key = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    except Exception as exc:
        raise ValueError(f"Invalid derived_public_key: {exc}") from exc

    try:
        pub_key.verify(signature, tbs, ec.ECDSA(Prehashed(hashes.SHA256())))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# COSE key parsing helpers
# ---------------------------------------------------------------------------


def _cose_ec2_to_point(cose_key: object, label: str) -> Tuple[int, int]:
    if not isinstance(cose_key, dict):
        raise ValueError(f"COSE EC2 key ({label}) must be a map, got {type(cose_key)}")

    x_bytes = cose_key.get(-2)
    y_bytes = cose_key.get(-3)

    if not isinstance(x_bytes, bytes) or len(x_bytes) != 32:
        raise ValueError(
            f"COSE EC2 key ({label}): x must be 32 bytes, got {type(x_bytes)}"
        )
    if not isinstance(y_bytes, bytes) or len(y_bytes) != 32:
        raise ValueError(
            f"COSE EC2 key ({label}): y must be 32 bytes, got {type(y_bytes)}"
        )

    x = int.from_bytes(x_bytes, "big")
    y = int.from_bytes(y_bytes, "big")

    if not _point_on_curve(x, y):
        raise ValueError(f"COSE EC2 key ({label}): point is not on the P-256 curve")

    return (x, y)


# ---------------------------------------------------------------------------
# ARKG-BL-EC-Add primitives
# ---------------------------------------------------------------------------


def _bl_prf(ikm_tau: bytes, ctx: bytes) -> int:
    dst = b"ARKG-BL-EC." + _DST_EXT + ctx
    return _hash_to_scalar(ikm_tau, dst)


def _bl_blind_public_key(pk: Tuple[int, int], tau: int) -> Tuple[int, int]:
    tau_g = _scalar_mul(tau, (_Gx, _Gy))
    result = _point_add(pk, tau_g)
    if result is None:
        raise ValueError("BL blinding produced the point at infinity")
    return result


# ---------------------------------------------------------------------------
# HMAC-KEM encapsulation
# ---------------------------------------------------------------------------


def _hmac_kem_encaps(
    pk_kem: Tuple[int, int],
    ikm: bytes,
    ctx: bytes,
) -> Tuple[bytes, bytes]:
    """Return (shared_secret k, ciphertext c) for ARKG HMAC-KEM.

    c = 16-byte HMAC tag || 65-byte eph_pk uncompressed = 81 bytes total.
    """
    dst_aug = b"ARKG-ECDH.ARKG-P256"

    eph_pk, eph_sk = _kem_derive_keypair(ikm)

    # ECDH: x-coordinate of (eph_sk * pk_kem)
    shared_point = _scalar_mul(eph_sk, pk_kem)
    k_prime = shared_point[0].to_bytes(32, "big")

    # Ephemeral public key as uncompressed point (65 bytes)
    eph_x, eph_y = eph_pk
    c_prime = b"\x04" + eph_x.to_bytes(32, "big") + eph_y.to_bytes(32, "big")

    mac_info = b"ARKG-KEM-HMAC-mac." + dst_aug + ctx
    mk = _hkdf_sha256(k_prime, b"", mac_info, 32)

    t = hmac.new(mk, c_prime, "sha256").digest()[:16]

    shared_info = b"ARKG-KEM-HMAC-shared." + dst_aug + ctx
    k = _hkdf_sha256(k_prime, b"", shared_info, len(k_prime))

    c = t + c_prime  # 16 + 65 = 81 bytes
    return k, c


def _kem_derive_keypair(ikm: bytes) -> Tuple[Tuple[int, int], int]:
    dst = b"ARKG-KEM-ECDH-KG.ARKG-ECDH." + _DST_EXT
    sk = _hash_to_scalar(ikm, dst)
    pk = _scalar_mul(sk, (_Gx, _Gy))
    return pk, sk


# ---------------------------------------------------------------------------
# Hash-to-scalar: expand_message_xmd (RFC 9380) then reduce mod N
# ---------------------------------------------------------------------------


def _hash_to_scalar(msg: bytes, dst: bytes) -> int:
    uniform = _expand_message_xmd(msg, dst, _XMD_L)
    scalar = int.from_bytes(uniform, "big") % _N
    if scalar == 0:
        raise ValueError(
            "hash_to_scalar produced zero scalar — astronomically unlikely"
        )
    return scalar


def _expand_message_xmd(msg: bytes, dst: bytes, length: int) -> bytes:
    """RFC 9380 §5.3.1 expand_message_xmd with SHA-256."""
    b_in_bytes = 32  # SHA-256 output
    s_in_bytes = 64  # SHA-256 block size

    ell = (length + b_in_bytes - 1) // b_in_bytes
    assert ell <= 255 and length <= 65535 and len(dst) <= 255

    dst_prime = dst + bytes([len(dst)])
    z_pad = bytes(s_in_bytes)
    l_i_b_str = length.to_bytes(2, "big")

    msg_prime = z_pad + msg + l_i_b_str + b"\x00" + dst_prime
    b0 = hashlib.sha256(msg_prime).digest()

    b = [b0, hashlib.sha256(b0 + b"\x01" + dst_prime).digest()]

    for i in range(2, ell + 1):
        xored = bytes(a ^ c for a, c in zip(b[0], b[i - 1], strict=True))
        b.append(hashlib.sha256(xored + bytes([i]) + dst_prime).digest())

    return b"".join(b[1:])[:length]


# ---------------------------------------------------------------------------
# HKDF-SHA-256
# ---------------------------------------------------------------------------


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt if salt else None,
        info=info,
    )
    return hkdf.derive(ikm)


# ---------------------------------------------------------------------------
# P-256 affine point arithmetic
# ---------------------------------------------------------------------------


def _point_on_curve(x: int, y: int) -> bool:
    lhs = (y * y) % _P
    rhs = (x * x * x + _A * x + _B) % _P
    return lhs == rhs


def _point_add(
    p1: Optional[Tuple[int, int]],
    p2: Optional[Tuple[int, int]],
) -> Optional[Tuple[int, int]]:
    """Add two P-256 affine points. None represents the point at infinity."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2:
        if y1 != y2:
            return None  # P + (-P) = identity
        # Point doubling: λ = (3x² + a) / (2y)
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, _P - 2, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, _P - 2, _P) % _P

    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return (x3, y3)


def _scalar_mul(k: int, point: Tuple[int, int]) -> Tuple[int, int]:
    """Scalar multiplication via double-and-add."""
    result: Optional[Tuple[int, int]] = None
    current: Optional[Tuple[int, int]] = point
    k = k % _N
    while k > 0:
        if k & 1:
            result = _point_add(result, current)
        current = _point_add(current, current)
        k >>= 1
    if result is None:
        raise ValueError("Scalar multiplication produced the point at infinity")
    return result
