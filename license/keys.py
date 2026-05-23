import base64
import json
import uuid
from datetime import datetime, timezone, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_der_public_key


def _load_private_key(private_key_b64: str) -> Ed25519PrivateKey:
    raw = base64.urlsafe_b64decode(private_key_b64 + "==")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _load_public_key(public_key_b64: str):
    raw = base64.urlsafe_b64decode(public_key_b64 + "==")
    # Wrap raw Ed25519 bytes in DER SubjectPublicKeyInfo envelope
    # OID 1.3.101.112 prefix for Ed25519 (12 bytes)
    der_prefix = bytes.fromhex("302a300506032b6570032100")
    return load_der_public_key(der_prefix + raw)


_PLAN_DURATIONS = {
    "trial_1h": timedelta(hours=1),
    "trial_1d": timedelta(days=1),
    "monthly":  timedelta(days=30),
    "lifetime": None,
}


def generate_license_key(
    private_key_b64: str,
    customer_name: str,
    plan: str = "lifetime",
) -> str:
    """Sign a payload with Ed25519 private key, return as base64url token."""
    if plan not in _PLAN_DURATIONS:
        raise ValueError(f"Unknown plan '{plan}'. Valid: {list(_PLAN_DURATIONS)}")
    duration = _PLAN_DURATIONS[plan]
    expires_at = (
        (datetime.now(timezone.utc) + duration).isoformat() if duration else None
    )
    payload = {
        "key_id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan,
        "expires_at": expires_at,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")

    private_key = _load_private_key(private_key_b64)
    signature = private_key.sign(payload_bytes)
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{payload_b64}.{sig_b64}"


def verify_license_key(token: str, public_key_b64: str) -> dict:
    """Verify Ed25519 signature and return payload dict. Raises on invalid."""
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Invalid token format")

    payload_b64, sig_b64 = parts
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
    sig_bytes = base64.urlsafe_b64decode(sig_b64 + "==")

    public_key = _load_public_key(public_key_b64)
    # Raises InvalidSignature if signature doesn't match
    public_key.verify(sig_bytes, payload_bytes)

    return json.loads(payload_bytes)
