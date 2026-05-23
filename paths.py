"""Central resolver for persistent file paths."""
import os
from pathlib import Path


def app_data_dir() -> Path:
    """Return the per-user app-data dir, creating it if missing."""
    base = os.environ.get("HYPECUTTER_APP_DATA_DIR")
    if base:
        p = Path(base)
    else:
        p = Path.home() / ".hypecutter"
    p.mkdir(parents=True, exist_ok=True)
    return p
