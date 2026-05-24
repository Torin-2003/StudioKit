"""Central resolver for persistent file paths.

All user data lives under app_data_dir() so it survives app upgrades.
Override the root with the HYPECUTTER_APP_DATA_DIR env var (useful for Docker).
"""
import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Return the per-user app-data dir, creating it if missing.

    Resolution order:
    1. HYPECUTTER_APP_DATA_DIR env var (Docker / CI override)
    2. ~/.hypecutter  (same on Windows, Mac, Linux)
    """
    base = os.environ.get("HYPECUTTER_APP_DATA_DIR")
    if base:
        p = Path(base)
    else:
        p = Path.home() / ".hypecutter"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    """SQLite database path."""
    p = app_data_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "hypecutter.db"


def hc_config_path() -> Path:
    """HypeCutter settings JSON path."""
    p = app_data_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p / "hypecutter_config.json"


def sm_config_path() -> Path:
    """Scene Manager settings JSON path."""
    p = app_data_dir() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p / "scene_manager_config.json"


def hc_output_dir() -> Path:
    """Default output directory for HypeCutter clips."""
    p = app_data_dir() / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p


def downloads_dir() -> Path:
    """Temporary downloads directory."""
    p = app_data_dir() / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p
