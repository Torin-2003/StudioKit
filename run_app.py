import sys
import os
from pathlib import Path


def get_app_path():
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "app.py")
    return str(Path(__file__).parent / "app.py")


def setup_ffmpeg():
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        # Try all known PyInstaller layouts:
        # - onefile: _MEIPASS/ffmpeg_bin
        # - Windows onedir: exe/ffmpeg_bin and exe/_internal/ffmpeg_bin
        # - macOS .app bundle: Contents/MacOS/<exe> → ../Resources/ffmpeg_bin and ../Frameworks/ffmpeg_bin
        candidates = [
            Path(sys._MEIPASS) / "ffmpeg_bin",
            exe_dir / "ffmpeg_bin",
            exe_dir / "_internal" / "ffmpeg_bin",
            exe_dir.parent / "Resources" / "ffmpeg_bin",
            exe_dir.parent / "Frameworks" / "ffmpeg_bin",
        ]
        for ffmpeg_dir in candidates:
            if ffmpeg_dir.exists():
                # Prepend to PATH AND export as env var so child Streamlit process inherits
                os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
                os.environ["STUDIOKIT_FFMPEG_DIR"] = str(ffmpeg_dir)
                return


def _open_browser_when_ready(url: str, timeout: int = 30) -> None:
    """Poll url until it responds (up to timeout seconds), then open browser."""
    import time
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            break  # server is up
        except Exception:
            time.sleep(0.5)

    # Open browser — os.startfile is more reliable in Windows frozen bundles
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        import webbrowser
        webbrowser.open(url)


if __name__ == "__main__":
    setup_ffmpeg()
    if getattr(sys, "frozen", False):
        os.environ.pop("STUDIOKIT_DEV", None)

    import threading
    t = threading.Thread(
        target=_open_browser_when_ready,
        args=("http://localhost:8501",),
        daemon=True,
    )
    t.start()

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", get_app_path(),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
