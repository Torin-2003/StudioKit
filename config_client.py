"""Fetch workflow config from Vercel API on startup. Falls back to defaults."""
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

_CONFIG_URL = os.environ.get(
    "HYPECUTTER_CONFIG_URL", "https://hype-cutter.vercel.app/config"
)

_DEFAULTS: dict[str, Any] = {
    "system_prompt_extra": "",
    "bad_ending_words_extra": [],
    "bad_start_words_extra": [],
    "hook_strength_weight": 1.0,
    "viral_score_weight": 1.0,
    "promo_phrases_extra": [],
}

_cached: dict[str, Any] | None = None


def fetch_config(force: bool = False) -> dict[str, Any]:
    """Return workflow config. Caches after first successful fetch.
    Falls back to _DEFAULTS on network error."""
    global _cached
    if _cached is not None and not force:
        return _cached
    if os.environ.get("HYPECUTTER_DEV") == "1":
        _cached = dict(_DEFAULTS)
        return _cached
    try:
        resp = requests.get(_CONFIG_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        merged = {**_DEFAULTS, **data}
        _cached = merged
        logger.info("Workflow config loaded from cloud")
        return _cached
    except Exception as e:
        logger.warning("Failed to fetch config from cloud, using defaults: %s", e)
        _cached = dict(_DEFAULTS)
        return _cached
