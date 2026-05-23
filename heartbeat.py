"""Background heartbeat: pings license server every 15 minutes."""
import logging
import os
import threading
import time

import requests

from license_client import get_machine_id, load_license, update_heartbeat, _DEFAULT_LICENSE_PATH

logger = logging.getLogger(__name__)

_LICENSE_SERVER_URL = os.environ.get(
    "LICENSE_SERVER_URL", "https://hype-cutter.vercel.app"
)
_CHECK_INTERVAL_SECONDS = 60 * 15


def run_heartbeat_once() -> bool:
    data = load_license()
    if not data:
        return True
    try:
        resp = requests.post(
            f"{_LICENSE_SERVER_URL}/heartbeat",
            json={"token": data["token"], "machine_id": get_machine_id()},
            timeout=15,
        )
        if resp.ok and resp.json().get("valid"):
            update_heartbeat()
            logger.info("Heartbeat OK")
            return True
        if resp.status_code in (403, 404):
            _DEFAULT_LICENSE_PATH.unlink(missing_ok=True)
            logger.warning("License revoked by server (status=%s)", resp.status_code)
            return False
        logger.warning("Heartbeat rejected (status=%s)", resp.status_code)
        return False
    except Exception as exc:
        logger.warning("Heartbeat network error: %s", exc)
        return True


def _scheduler_loop():
    while True:
        try:
            run_heartbeat_once()
        except Exception as exc:
            logger.exception("Heartbeat loop error: %s", exc)
        time.sleep(_CHECK_INTERVAL_SECONDS)


def start_heartbeat_scheduler():
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    return t
