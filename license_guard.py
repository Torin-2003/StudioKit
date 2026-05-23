"""Local-only license verification. Pure: file read + one Ed25519 verify."""
import json
from datetime import datetime, timezone
from pathlib import Path

from license_client import verify_token_signature, get_machine_id, _DEFAULT_LICENSE_PATH


def verify_local_license():
    """Returns (status, payload):
      ('active', payload) | ('none', None) | ('tampered', None)
      | ('expired', None) | ('mismatch', None)
    """
    lp = _DEFAULT_LICENSE_PATH
    try:
        data = json.loads(lp.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return ("none", None)
    if not data:
        return ("none", None)
    token = data.get("token", "")
    try:
        payload = verify_token_signature(token)
    except Exception:
        return ("tampered", None)
    exp = payload.get("expires_at")
    if exp:
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(exp):
                return ("expired", None)
        except Exception:
            return ("tampered", None)
    if data.get("machine_id") != get_machine_id():
        return ("mismatch", None)
    return ("active", payload)
