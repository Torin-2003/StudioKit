import sys
import os
from pathlib import Path


def get_app_path():
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "app.py")
    return str(Path(__file__).parent / "app.py")


def setup_ffmpeg():
    if getattr(sys, "frozen", False):
        ffmpeg_dir = Path(sys._MEIPASS) / "ffmpeg_bin"
        if ffmpeg_dir.exists():
            os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")


if __name__ == "__main__":
    setup_ffmpeg()
    if getattr(sys, "frozen", False):
        os.environ.pop("STUDIOKIT_DEV", None)
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", get_app_path(),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
