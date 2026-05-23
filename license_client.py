"""Machine ID generation, local license persistence, heartbeat scheduling."""
import functools
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from paths import app_data_dir

_LEGACY_LICENSE_PATH = Path(
    os.environ.get("HC_LEGACY_LICENSE_PATH", str(Path.home() / ".hypecutter" / "license.json"))
)
_DEFAULT_LICENSE_PATH = app_data_dir() / "license.json"
_HEARTBEAT_INTERVAL = timedelta(days=7)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0

# Ed25519 public key — shared with video-dubbing (same key pair across products is fine)
EMBEDDED_PUBLIC_KEY_B64 = "UkHe-VTosYuA3yj4Yw9pRnph1MX7WV5pJJC7hlIfzPQ"


def _selftest_embedded_key() -> None:
    from license.keys import _load_public_key
    try:
        _load_public_key(EMBEDDED_PUBLIC_KEY_B64)
    except Exception as e:
        raise RuntimeError(f"Embedded public key self-test failed: {e}")


_selftest_embedded_key()


def verify_token_signature(token: str) -> dict:
    from license.keys import verify_license_key
    return verify_license_key(token, EMBEDDED_PUBLIC_KEY_B64)


@functools.lru_cache(maxsize=1)
def get_machine_id() -> str:
    parts = []
    sys_name = platform.system()
    if sys_name == "Darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"], text=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            for line in out.splitlines():
                if "Serial Number" in line or "Hardware UUID" in line:
                    parts.append(line.strip())
        except Exception:
            pass
    elif sys_name == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Cryptography") as k:
                guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            parts.append(str(guid))
        except Exception:
            try:
                out = subprocess.check_output(
                    ["wmic", "csproduct", "get", "UUID"],
                    text=True, timeout=5, creationflags=_NO_WINDOW,
                )
                parts.append(out.strip())
            except Exception:
                pass
    import uuid as _uuid
    parts.append(str(_uuid.getnode()))
    raw = "|".join(parts) or "fallback"
    return hashlib.sha256(raw.encode()).hexdigest()


def save_license(
    token: str,
    *,
    expires_at: Optional[str] = None,
    plan: Optional[str] = None,
    license_path: Path = _DEFAULT_LICENSE_PATH,
) -> None:
    license_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "token": token,
        "machine_id": get_machine_id(),
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at,
        "plan": plan or "lifetime",
    }
    license_path.write_text(json.dumps(data, indent=2))


def load_license(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> Optional[dict]:
    try:
        return json.loads(license_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def update_heartbeat(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> None:
    data = load_license(license_path=license_path)
    if data:
        data["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        license_path.write_text(json.dumps(data, indent=2))


def is_heartbeat_due(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> bool:
    data = load_license(license_path=license_path)
    if not data:
        return True
    last = datetime.fromisoformat(data["last_heartbeat"])
    return datetime.now(timezone.utc) - last > _HEARTBEAT_INTERVAL


def license_state(*, license_path: Path = _DEFAULT_LICENSE_PATH) -> str:
    data = load_license(license_path=license_path)
    if not data:
        return "none"
    token = data.get("token", "")
    try:
        payload = verify_token_signature(token)
    except Exception:
        return "invalid"
    exp = payload.get("expires_at")
    if exp and datetime.now(timezone.utc) > datetime.fromisoformat(exp):
        return "expired"
    if data.get("machine_id") != get_machine_id():
        return "mismatch"
    return "active"
