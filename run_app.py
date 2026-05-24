import sys
import os
from pathlib import Path


def get_app_path():
    if getattr(sys, "frozen", False):
        return str(Path(sys._MEIPASS) / "app.py")
    return str(Path(__file__).parent / "app.py")


def setup_ffmpeg():
    frozen = getattr(sys, "frozen", False)
    print(f"[setup_ffmpeg] frozen={frozen} executable={sys.executable}", flush=True)
    if frozen:
        exe_dir = Path(sys.executable).parent
        candidates = [
            Path(sys._MEIPASS) / "ffmpeg_bin",
            exe_dir / "ffmpeg_bin",
            exe_dir / "_internal" / "ffmpeg_bin",
            exe_dir.parent / "Resources" / "ffmpeg_bin",
            exe_dir.parent / "Frameworks" / "ffmpeg_bin",
        ]
        for ffmpeg_dir in candidates:
            print(f"[setup_ffmpeg] trying {ffmpeg_dir} exists={ffmpeg_dir.exists()}", flush=True)
            if ffmpeg_dir.exists():
                os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
                os.environ["STUDIOKIT_FFMPEG_DIR"] = str(ffmpeg_dir)
                print(f"[setup_ffmpeg] SET STUDIOKIT_FFMPEG_DIR={ffmpeg_dir}", flush=True)
                return
        print("[setup_ffmpeg] NO candidate matched", flush=True)


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


def run_self_test() -> int:
    """In-bundle smoke test: actually invoke yt-dlp + ffmpeg the way a user would.

    Triggered by STUDIOKIT_SELFTEST=1 env var. Runs INSIDE the frozen bundle so
    we test the real yt-dlp + bundled ffmpeg integration that the user hits.
    """
    print("=== StudioKit self-test ===", flush=True)
    print(f"frozen={getattr(sys, 'frozen', False)}", flush=True)
    print(f"executable={sys.executable}", flush=True)
    print(f"PATH={os.environ.get('PATH', '')[:500]}...", flush=True)
    print(f"STUDIOKIT_FFMPEG_DIR={os.environ.get('STUDIOKIT_FFMPEG_DIR', '<unset>')}", flush=True)

    # Import core_engine — this triggers Downloader/yt-dlp init paths
    try:
        from hypecutter import core_engine  # noqa: F401
        print("OK: core_engine imported", flush=True)
    except Exception as e:
        print(f"FAIL: core_engine import: {e}", flush=True)
        return 1

    # Generate test video with bundled ffmpeg (proves ffmpeg works from inside bundle)
    import subprocess
    import tempfile
    ffmpeg_dir = os.environ.get("STUDIOKIT_FFMPEG_DIR")
    if not ffmpeg_dir:
        print("FAIL: STUDIOKIT_FFMPEG_DIR not set", flush=True)
        return 1
    ext = ".exe" if sys.platform == "win32" else ""
    ff = Path(ffmpeg_dir) / f"ffmpeg{ext}"
    tmp = Path(tempfile.gettempdir()) / "studiokit_selftest.mp4"
    r = subprocess.run(
        [str(ff), "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=30",
         "-c:v", "libx264", "-preset", "ultrafast", str(tmp)],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        print(f"FAIL: bundled ffmpeg returned {r.returncode}: {r.stderr[-500:]}", flush=True)
        return 1
    print(f"OK: bundled ffmpeg generated {tmp} ({tmp.stat().st_size} bytes)", flush=True)

    # Now the critical test: invoke yt-dlp with ydl_opts pointing at a public MP4
    # AND verify it can use bundled ffmpeg (-merge requires ffmpeg)
    try:
        import yt_dlp
        # Real YouTube URL — short Creative Commons video, exactly what users hit
        # "Me at the zoo" (first YouTube video, 18 seconds)
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        out_dir = Path(tempfile.gettempdir()) / "studiokit_selftest_dl"
        out_dir.mkdir(exist_ok=True)
        # Same options the real Downloader class uses — including the merge that
        # triggers the "ffmpeg is not installed" error
        opts = {
            "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
            "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": False,
            "no_warnings": False,
            "ffmpeg_location": ffmpeg_dir,
            "nocheckcertificate": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            print(f"OK: yt-dlp downloaded YouTube video {info.get('id', '?')}", flush=True)
            # Verify the merged mp4 actually exists and has content
            mp4 = out_dir / f"{info.get('id', '?')}.mp4"
            if mp4.exists() and mp4.stat().st_size > 10_000:
                print(f"OK: merged output {mp4.name} ({mp4.stat().st_size} bytes)", flush=True)
            else:
                print(f"FAIL: merged mp4 missing or empty: {mp4}", flush=True)
                return 1
    except Exception as e:
        # If yt-dlp can't find ffmpeg, this is THE bug — fail loudly
        msg = str(e).lower()
        if "ffmpeg" in msg or "merging of multiple formats" in msg:
            print(f"FAIL: yt-dlp can't find bundled ffmpeg: {e}", flush=True)
            return 1
        # Other errors (geo block, age gate) — still fail since we picked a public video
        print(f"FAIL: yt-dlp error: {type(e).__name__}: {e}", flush=True)
        return 1

    print("=== self-test PASSED ===", flush=True)
    return 0


if __name__ == "__main__":
    setup_ffmpeg()
    if getattr(sys, "frozen", False):
        os.environ.pop("STUDIOKIT_DEV", None)

    # Self-test mode: run smoke checks inside the frozen bundle, then exit
    if os.environ.get("STUDIOKIT_SELFTEST") == "1":
        sys.exit(run_self_test())

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
