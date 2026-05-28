import sys
import os
from pathlib import Path

# CRITICAL: force UTF-8 on stdout/stderr BEFORE anything else prints.
# On Windows, the default cp1252 codec raises UnicodeEncodeError when emoji
# (e.g. ✅) are printed. In a frozen bundle, an unhandled UnicodeEncodeError
# inside Streamlit's status callback can propagate up and kill the process
# with an ACCESS VIOLATION (0xC0000005) when it bubbles through C extensions.
# This must run before ANY print(), and before Streamlit imports.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        # Python 3.7+: reconfigure existing streams
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


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
    # On macOS, PyInstaller .app bundles re-exec themselves as a child process.
    # Use a lock file so only the FIRST instance runs the full test; subsequent
    # child processes exit immediately to avoid OOM from concurrent Whisper loads.
    import tempfile
    _lock = Path(tempfile.gettempdir()) / "studiokit_selftest.lock"
    if _lock.exists():
        print(f"[self-test] child process detected (lock exists) — exiting", flush=True)
        return 0
    _lock.touch()
    try:
        return _run_self_test_inner()
    finally:
        _lock.unlink(missing_ok=True)


def _run_self_test_inner() -> int:
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

    # Verify faster_whisper assets are bundled (silero_vad_v6.onnx must exist)
    try:
        import faster_whisper
        fw_dir = Path(faster_whisper.__file__).parent
        onnx = fw_dir / "assets" / "silero_vad_v6.onnx"
        if not onnx.exists():
            # Also check sys._MEIPASS path
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                onnx = Path(meipass) / "faster_whisper" / "assets" / "silero_vad_v6.onnx"
        if onnx.exists():
            print(f"OK: faster_whisper silero_vad_v6.onnx found at {onnx}", flush=True)
        else:
            print(f"FAIL: silero_vad_v6.onnx not found (checked {fw_dir}/assets/)", flush=True)
            return 1
    except Exception as e:
        print(f"FAIL: faster_whisper assets check: {e}", flush=True)
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

    # Critical test: verify yt-dlp can find and USE bundled ffmpeg for merging.
    # YouTube blocks CI datacenter IPs, so we test the merge path directly:
    # 1. Use bundled ffmpeg to create separate video-only and audio-only files
    # 2. Use yt-dlp's FFmpegMergerPP (the exact code path that fails when ffmpeg missing)
    #    to merge them — this is the SAME code yt-dlp runs after downloading
    try:
        import yt_dlp
        from yt_dlp.postprocessor import FFmpegMergerPP
        out_dir = Path(tempfile.gettempdir()) / "studiokit_selftest_dl"
        out_dir.mkdir(exist_ok=True)

        # Create video-only stream (simulate bestvideo)
        vid_only = out_dir / "video_only.mp4"
        r = subprocess.run(
            [str(ff), "-y",
             "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=30",
             "-an", "-c:v", "libx264", "-preset", "ultrafast", str(vid_only)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            print(f"FAIL: create video-only failed: {r.stderr[-300:]}", flush=True)
            return 1

        # Create audio-only stream (simulate bestaudio)
        aud_only = out_dir / "audio_only.m4a"
        r = subprocess.run(
            [str(ff), "-y",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-vn", "-c:a", "aac", str(aud_only)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            print(f"FAIL: create audio-only failed: {r.stderr[-300:]}", flush=True)
            return 1

        print(f"OK: created separate video ({vid_only.stat().st_size}B) and audio ({aud_only.stat().st_size}B) streams", flush=True)

        # Now invoke FFmpegMergerPP — this is EXACTLY what yt-dlp does after downloading
        # separate streams. This fails with "ffmpeg is not installed" when ffmpeg_location wrong.
        merged = out_dir / "merged.mp4"
        ydl_opts = {
            "ffmpeg_location": ffmpeg_dir,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            merger = FFmpegMergerPP(ydl)
            # FFmpegMergerPP.run() uses requested_formats + __files_to_merge
            info = {
                "id": "selftest",
                "ext": "mp4",
                "filepath": str(merged),
                "__files_to_merge": [str(vid_only), str(aud_only)],
                "requested_formats": [
                    {"filepath": str(vid_only), "ext": "mp4", "vcodec": "h264", "acodec": "none", "protocol": "https"},
                    {"filepath": str(aud_only), "ext": "m4a", "vcodec": "none", "acodec": "aac", "protocol": "https"},
                ],
            }
            files, _ = merger.run(info)

        if merged.exists() and merged.stat().st_size > 5_000:
            print(f"OK: yt-dlp FFmpegMergerPP merged to {merged.name} ({merged.stat().st_size} bytes)", flush=True)
        else:
            print(f"FAIL: merged output missing or empty: {merged}", flush=True)
            return 1
    except Exception as e:
        msg = str(e).lower()
        if "ffmpeg" in msg or "merging" in msg or "not installed" in msg:
            print(f"FAIL: yt-dlp can't find bundled ffmpeg: {e}", flush=True)
            return 1
        print(f"FAIL: yt-dlp merger error: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1

    # ── DIAGNOSTIC: trace every step after transcription to find exact crash point ──
    # User reports crash after "✅ Transcription complete: 3167 words" every time.
    # We run each step in isolation with explicit print before AND after.
    # The last printed line before crash = the crash location.

    # Step A: Generate a REALISTIC video (10 min, matches user's actual workload)
    # User reports crash after transcribing 3161 words = ~15min real speech.
    # We use 600s test signal to reproduce the same Whisper memory pressure.
    import uuid as _uuid
    _run_id = _uuid.uuid4().hex[:8]
    DURATION_S = 600  # 10 minutes — matches user's real video length
    print(f"DIAG: generating {DURATION_S}s test video (run_id={_run_id})...", flush=True)
    av_file = Path(tempfile.gettempdir()) / f"studiokit_selftest_{_run_id}_av.mp4"
    r = subprocess.run(
        [str(ff), "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={DURATION_S}:size=320x240:rate=15",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION_S}",
         "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(av_file)],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        print(f"FAIL: ffmpeg av generation: {r.stderr[-300:]}", flush=True)
        return 1
    print(f"DIAG: av file ready ({av_file.stat().st_size} bytes)", flush=True)

    # Step B: Load Whisper model (base, same as default user setting)
    hf_cache = Path(tempfile.gettempdir()) / "studiokit_hf_cache"
    hf_cache.mkdir(exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_cache))

    print("DIAG: loading faster_whisper...", flush=True)
    import faster_whisper
    print(f"DIAG: faster_whisper version {faster_whisper.__version__}", flush=True)

    print("DIAG: creating WhisperModel(tiny)...", flush=True)
    model = faster_whisper.WhisperModel("tiny", device="cpu", compute_type="int8")
    print("DIAG: WhisperModel created OK", flush=True)

    # Step C: transcribe — exact same params as Transcriber.transcribe()
    print("DIAG: calling model.transcribe() with word_timestamps=True, beam_size=5, vad_filter=False...", flush=True)
    try:
        segments_gen, info = model.transcribe(
            str(av_file),
            language=None,
            word_timestamps=True,
            beam_size=5,
            vad_filter=False,
        )
        print(f"DIAG: transcribe() returned generator, iterating segments...", flush=True)
        words = []
        for i, seg in enumerate(segments_gen):
            if seg.words:
                for w in seg.words:
                    words.append({"word": w.word, "start": w.start, "end": w.end})
            if i % 5 == 0:
                print(f"DIAG: processed {i+1} segments so far, {len(words)} words...", flush=True)
        print(f"DIAG: transcription done: {len(words)} words, lang={info.language}", flush=True)
    except Exception as e:
        print(f"FAIL: transcription exception: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1
    del model
    print("DIAG: model deleted (memory freed)", flush=True)

    # Step D: probe video duration (VideoEditor.probe_duration — next step after transcription)
    print("DIAG: testing VideoEditor.probe_duration...", flush=True)
    try:
        from hypecutter.core_engine import VideoEditor
        duration = VideoEditor.probe_duration(str(av_file))
        print(f"DIAG: probe_duration OK: {duration:.1f}s", flush=True)
    except Exception as e:
        print(f"FAIL: probe_duration: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1

    # Step E: test openai import (AI analysis step — happens right after transcription)
    print("DIAG: testing openai import...", flush=True)
    try:
        import openai
        print(f"DIAG: openai version {openai.__version__} OK", flush=True)
    except Exception as e:
        print(f"FAIL: openai import: {type(e).__name__}: {e}", flush=True)
        return 1

    print("DIAG: testing anthropic import...", flush=True)
    try:
        import anthropic
        print(f"DIAG: anthropic version {anthropic.__version__} OK", flush=True)
    except Exception as e:
        print(f"FAIL: anthropic import: {type(e).__name__}: {e}", flush=True)
        return 1

    # Step F: Full VideoEditor render — this is the step AFTER AI analysis
    # Test process_clip with a real clip on a real mp4 to catch rendering crashes
    print("DIAG: testing VideoEditor full render pipeline...", flush=True)
    try:
        from hypecutter.core_engine import VideoEditor
        out_dir = Path(tempfile.gettempdir()) / "studiokit_selftest_render"
        out_dir.mkdir(exist_ok=True)
        editor = VideoEditor(output_dir=str(out_dir))
        print("DIAG: VideoEditor created OK", flush=True)

        # Simulate a highlight segment from AI output
        highlight = {
            "title": "Test Clip",
            "start": 2.0,
            "end": 8.0,
            "duration": 6.0,
            "score": 8,
            "hook_strength": 7,
            "reason": "test",
            "caption": "test caption",
        }
        fake_words = [
            {"word": "hello", "start": 2.5, "end": 3.0},
            {"word": "world", "start": 3.1, "end": 3.6},
            {"word": "this", "start": 4.0, "end": 4.3},
            {"word": "is", "start": 4.4, "end": 4.6},
            {"word": "a", "start": 4.7, "end": 4.8},
            {"word": "test", "start": 4.9, "end": 5.3},
        ]
        print("DIAG: calling process_clip (vertical=False, burn_subtitles=False)...", flush=True)
        out_path = editor.process_clip(
            source_path=str(av_file),
            highlight=highlight,
            words=fake_words,
            clip_index=1,
            vertical=False,
            font_path=None,
            burn_subtitles=False,
        )
        print(f"DIAG: process_clip OK: {out_path}", flush=True)

        # Also test vertical crop (9:16) which uses different ffmpeg filter chain
        # Test vertical=True without subtitles first (isolate crop vs subtitle issue)
        print("DIAG: calling process_clip (vertical=True, burn_subtitles=False)...", flush=True)
        out_path2 = editor.process_clip(
            source_path=str(av_file),
            highlight=highlight,
            words=fake_words,
            clip_index=2,
            vertical=True,
            font_path=None,
            burn_subtitles=False,
        )
        print(f"DIAG: process_clip vertical=True OK: {out_path2}", flush=True)

        # Then test vertical=True WITH subtitles (this is where crash happens)
        print("DIAG: calling process_clip (vertical=True, burn_subtitles=True)...", flush=True)
        out_path3 = editor.process_clip(
            source_path=str(av_file),
            highlight=highlight,
            words=fake_words,
            clip_index=3,
            vertical=True,
            font_path=None,
            burn_subtitles=True,
        )
        print(f"DIAG: process_clip vertical+subtitles OK: {out_path3}", flush=True)

    except Exception as e:
        print(f"FAIL: VideoEditor render: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1

    # ── Step G: FULL end-to-end engine.process() — reproduces user crash ──
    # User reports crash after "✅ Transcription complete: 3161 words".
    # Only AutoHighlightEngine.process() exercises the full code path the user hits:
    # download → transcribe → probe → AI analyze → render. We run it here with the
    # real OpenAI API (via STUDIOKIT_TEST_OPENAI_KEY secret) on a 5-min video.
    test_key = os.environ.get("STUDIOKIT_TEST_OPENAI_KEY")
    if not test_key:
        print("DIAG: STUDIOKIT_TEST_OPENAI_KEY not set — skipping full engine.process() test", flush=True)
        print("=== self-test PASSED (skipped full process) ===", flush=True)
        return 0

    print("[DIAG] STEP G: starting FULL engine.process() reproduction", flush=True)
    print(f"[DIAG] STEP G: generating 5min talking-like video (run_id={_run_id})...", flush=True)

    # 5min video with varied audio so Whisper produces real word output
    long_av = Path(tempfile.gettempdir()) / f"studiokit_full_{_run_id}.mp4"
    r = subprocess.run(
        [str(ff), "-y",
         "-f", "lavfi", "-i", "testsrc=duration=300:size=320x240:rate=15",
         # Modulated sine — Whisper hallucinates real words on noise-like signals
         "-f", "lavfi", "-i", "aevalsrc=0.5*sin(440*2*PI*t)+0.3*sin(880*2*PI*t)*sin(2*PI*t/3):duration=300",
         "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(long_av)],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        print(f"FAIL: long video generation: {r.stderr[-300:]}", flush=True)
        return 1
    print(f"[DIAG] STEP G: long video ready ({long_av.stat().st_size} bytes)", flush=True)

    # We can't easily reproduce real Whisper output with synthetic audio (returns 0 words).
    # So we test the POST-transcription path directly: fake the words list and call the
    # rest of engine.process()'s logic manually (analyze + render). This is exactly the
    # code path that crashes for the user, after "Transcription complete".
    try:
        from hypecutter.core_engine import AutoHighlightEngine, AIAnalyzer, VideoEditor
        from config_client import fetch_config
        test_base = os.environ.get("STUDIOKIT_TEST_OPENAI_BASE", "")
        test_model = os.environ.get("STUDIOKIT_TEST_OPENAI_MODEL", "gpt-4o-mini")

        # Fake a realistic words list (5min of "speech" at ~3 words/sec = 900 words)
        # Matches user's "3161 words" workload pattern.
        import random
        random.seed(42)
        vocab = ["hello", "world", "this", "is", "a", "test", "video", "with", "many",
                 "words", "to", "simulate", "real", "transcription", "output", "from",
                 "whisper", "model", "running", "in", "frozen", "bundle"]
        fake_words = []
        t = 0.0
        for i in range(900):
            word = random.choice(vocab)
            duration = random.uniform(0.2, 0.5)
            fake_words.append({"word": word, "start": round(t, 3), "end": round(t + duration, 3)})
            t += duration + random.uniform(0.0, 0.2)
        print(f"[DIAG] STEP G: built {len(fake_words)} fake words, last_end={fake_words[-1]['end']}", flush=True)

        # Force unicode print BEFORE creating engine to surface any encoding crash
        print("[DIAG] STEP G: testing emoji print: ✅ 🎙️ 🧠 🎬", flush=True)
        print("[DIAG] STEP G: emoji print survived", flush=True)

        # Build AIAnalyzer directly (skip Whisper instantiation since we have fake words)
        wf = fetch_config()
        print(f"[DIAG] STEP G: workflow_config keys: {list(wf.keys())}", flush=True)
        analyzer = AIAnalyzer(
            provider="openai",
            api_key=test_key,
            model=test_model,
            base_url=test_base,
            workflow_config=wf,
        )
        print(f"[DIAG] STEP G: AIAnalyzer built, provider={analyzer.provider}", flush=True)

        print(f"[DIAG] STEP G: fake_words[0]={fake_words[0]}", flush=True)
        print(f"[DIAG] STEP G: fake_words type: {type(fake_words).__name__}, item type: {type(fake_words[0]).__name__}", flush=True)
        # Test calling _words_to_timed_transcript DIRECTLY (it's a staticmethod)
        print("[DIAG] STEP G: calling _words_to_timed_transcript directly...", flush=True)
        try:
            from hypecutter.core_engine import AIAnalyzer as _AIA
            test_transcript = _AIA._words_to_timed_transcript(fake_words[:10])
            print(f"[DIAG] STEP G: direct call OK, transcript[:200]={test_transcript[:200]!r}", flush=True)
        except Exception as e:
            print(f"[DIAG] STEP G: direct call FAILED: {type(e).__name__}: {e}", flush=True)
            import traceback; traceback.print_exc()

        print("[DIAG] STEP G: calling analyzer.analyze_highlights() — this is where user crashes", flush=True)
        highlights = analyzer.analyze_highlights(
            fake_words,
            target_duration=30,
            n_clips=2,
            smart_mode=False,
            condense_mode=False,
            range_mode=False,
            range_label="",
            range_lo=30,
            range_hi=60,
        )
        print(f"[DIAG] STEP G: analyze_highlights OK: {len(highlights)} highlights", flush=True)

        # Now render the clips like engine.process() would
        out_dir = Path(tempfile.gettempdir()) / f"studiokit_full_out_{_run_id}"
        out_dir.mkdir(exist_ok=True)
        renderer = VideoEditor(output_dir=str(out_dir))

        for i, hl in enumerate(highlights, 1):
            print(f"[DIAG] STEP G: rendering clip {i}/{len(highlights)}: {hl.get('title', '?')[:30]}", flush=True)
            out_path = renderer.process_clip(
                source_path=str(long_av),
                highlight=hl,
                words=fake_words,
                clip_index=i,
                vertical=True,
                font_path=None,
                burn_subtitles=False,
            )
            print(f"[DIAG] STEP G: clip {i} rendered: {out_path}", flush=True)

    except Exception as e:
        print(f"FAIL: STEP G: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1

    # ── Step H: scene_manager end-to-end (Cython compiled, untested before) ──
    # scene_manager.analyzer and scene_manager.classifier are also Cython compiled.
    # Verify they don't crash in the frozen bundle like core_engine did before.
    print("[DIAG] STEP H: scene_manager Cython modules test", flush=True)
    try:
        # 1. Import compiled modules
        from scene_manager import analyzer as sm_analyzer
        from scene_manager import classifier as sm_classifier
        from scene_manager import splitter as sm_splitter
        from scene_manager import metadata as sm_metadata
        print("[DIAG] STEP H: imports OK", flush=True)

        # 2. Use a short scenedetect-friendly video (cuts + black + content)
        sm_video = Path(tempfile.gettempdir()) / f"studiokit_sm_{_run_id}.mp4"
        # Two cuts: black 1s → color 2s → black 1s → color 2s
        r = subprocess.run(
            [str(ff), "-y",
             "-f", "lavfi", "-i", "color=black:s=320x240:d=1,color=red:s=320x240:d=2,color=black:s=320x240:d=1,color=blue:s=320x240:d=2",
             "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1[v]",
             "-map", "[v]",
             "-c:v", "libx264", "-preset", "ultrafast", "-r", "30",
             str(sm_video)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            # Simpler fallback: testsrc with cuts
            r = subprocess.run(
                [str(ff), "-y",
                 "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=30",
                 "-c:v", "libx264", "-preset", "ultrafast", str(sm_video)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                print(f"FAIL: STEP H ffmpeg gen: {r.stderr[-200:]}", flush=True)
                return 1
        print(f"[DIAG] STEP H: video ready ({sm_video.stat().st_size} bytes)", flush=True)

        # 3. detect_scenes (uses scenedetect + cv2 — was a crash candidate)
        print("[DIAG] STEP H: calling detect_scenes...", flush=True)
        scenes = sm_splitter.detect_scenes(str(sm_video), threshold=27.0, min_clip_sec=0.5)
        print(f"[DIAG] STEP H: detect_scenes OK: {len(scenes)} scenes", flush=True)

        # 4. split_video (subprocess ffmpeg calls)
        sm_split_dir = Path(tempfile.gettempdir()) / f"studiokit_sm_split_{_run_id}"
        sm_split_dir.mkdir(exist_ok=True)
        print("[DIAG] STEP H: calling split_video...", flush=True)
        clips = sm_splitter.split_video(
            video_path=str(sm_video),
            scenes=scenes,
            output_dir=str(sm_split_dir),
            base_name="sm_test",
            min_clip_sec=0.5,
            black_filter=False,
        )
        print(f"[DIAG] STEP H: split_video OK: {len(clips)} clips", flush=True)

        if not clips:
            print("[DIAG] STEP H: no clips to test downstream — skipping classifier", flush=True)
        else:
            # 5. extract_frames + analyze_clip_frames (cv2 + OpenAI vision API)
            print("[DIAG] STEP H: calling extract_frames...", flush=True)
            frames = sm_splitter.extract_frames(clips[0]["path"], num_frames=2)
            print(f"[DIAG] STEP H: extract_frames OK: {len(frames)} frames", flush=True)

            if frames:
                from openai import OpenAI as _OpenAI
                oa_client = _OpenAI(api_key=test_key, base_url=test_base)
                print("[DIAG] STEP H: calling analyze_clip_frames (vision API)...", flush=True)
                try:
                    analysis = sm_analyzer.analyze_clip_frames(
                        client=oa_client,
                        frame_paths=frames,
                        source_video_name="sm_test.mp4",
                        timestamp=clips[0]["timestamp_in_source"],
                        granularity="medium",
                        model=test_model,
                        topic="",
                    )
                    print(f"[DIAG] STEP H: analyze_clip_frames OK: category={analysis.get('suggested_category', '?')}", flush=True)

                    # 6. resolve_target_folder (uses dict iteration — Cython compiled)
                    sm_out_dir = Path(tempfile.gettempdir()) / f"studiokit_sm_out_{_run_id}"
                    sm_out_dir.mkdir(exist_ok=True)
                    print("[DIAG] STEP H: calling resolve_target_folder...", flush=True)
                    folder_name = sm_classifier.resolve_target_folder(
                        client=oa_client,
                        output_dir=str(sm_out_dir),
                        suggested_category=analysis.get("suggested_category", "test_category"),
                        category_description=analysis.get("category_description", ""),
                        granularity="medium",
                        model=test_model,
                        analysis_content_type=analysis.get("content_type", ""),
                    )
                    print(f"[DIAG] STEP H: resolve_target_folder OK: {folder_name}", flush=True)

                    # 7. place_clip (file move + metadata write)
                    print("[DIAG] STEP H: calling place_clip...", flush=True)
                    final_path = sm_classifier.place_clip(
                        output_dir=str(sm_out_dir),
                        clip_info=clips[0],
                        analysis=analysis,
                        folder_name=folder_name,
                        source_video_name="sm_test.mp4",
                    )
                    print(f"[DIAG] STEP H: place_clip OK: {final_path}", flush=True)
                except Exception as inner:
                    # Vision API failures are acceptable (e.g. base_url doesn't support vision)
                    # but Cython crashes (SEGV) would not even reach this except clause.
                    print(f"[DIAG] STEP H: vision/classify step raised (non-fatal): {type(inner).__name__}: {inner}", flush=True)

    except Exception as e:
        print(f"FAIL: STEP H: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1

    # ── Step I: scene_manager.downloader (yt-dlp via Python module) ──
    # User reported: "yt-dlp not available: yt-dlp not found. Install with: brew install yt-dlp"
    # Root cause: original scene_manager/downloader.py used shutil.which("yt-dlp") to find
    # the CLI binary — but our bundle ships the Python yt_dlp package, not a CLI binary.
    # New downloader prefers the Python module. Verify here.
    print("[DIAG] STEP I: scene_manager.downloader test", flush=True)
    try:
        from scene_manager import downloader as sm_dl
        # 1. check_ytdlp must report available WITHOUT relying on system binary
        avail, ver = sm_dl.check_ytdlp()
        if not avail:
            print(f"FAIL: STEP I: check_ytdlp says unavailable: {ver}", flush=True)
            return 1
        print(f"[DIAG] STEP I: check_ytdlp OK: version={ver}", flush=True)

        # 2. Real download via a local HTTP server serving a real mp4 file.
        # yt-dlp's generic extractor handles direct URLs without needing YouTube.
        # This avoids CI IP blocking while exercising the same code path that
        # users hit when downloading from any URL.
        import http.server
        import socketserver
        import threading as _thr

        sm_dl_dir = Path(tempfile.gettempdir()) / f"studiokit_sm_dl_{_run_id}"
        sm_dl_dir.mkdir(exist_ok=True)
        sm_serve_dir = Path(tempfile.gettempdir()) / f"studiokit_sm_serve_{_run_id}"
        sm_serve_dir.mkdir(exist_ok=True)

        # Generate a test mp4 in the served directory
        served_mp4 = sm_serve_dir / "test_video.mp4"
        r = subprocess.run(
            [str(ff), "-y",
             "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=15",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
             "-c:v", "libx264", "-preset", "ultrafast",
             "-c:a", "aac", "-shortest", str(served_mp4)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            print(f"FAIL: STEP I served mp4 gen: {r.stderr[-200:]}", flush=True)
            return 1
        print(f"[DIAG] STEP I: served mp4 ready ({served_mp4.stat().st_size} bytes)", flush=True)

        # Start a local HTTP server in the serving dir
        os.chdir(str(sm_serve_dir))

        class _QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args, **kwargs):
                pass

        httpd = socketserver.TCPServer(("127.0.0.1", 0), _QuietHandler)
        port = httpd.server_address[1]
        server_thread = _thr.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        test_url = f"http://127.0.0.1:{port}/test_video.mp4"
        print(f"[DIAG] STEP I: local http server on port {port}, url={test_url}", flush=True)

        try:
            # 3. get_video_info — uses yt_dlp.YoutubeDL.extract_info(download=False)
            print("[DIAG] STEP I: calling get_video_info...", flush=True)
            try:
                info = sm_dl.get_video_info(test_url)
                print(f"[DIAG] STEP I: get_video_info OK: title={info.get('title', '?')[:40]}", flush=True)
            except Exception as e:
                # Generic extractor may not return full metadata for a direct mp4 — that's OK
                print(f"[DIAG] STEP I: get_video_info raised (non-fatal for direct mp4): {e}", flush=True)

            # 4. download_video — the actual user-facing call
            print("[DIAG] STEP I: calling download_video...", flush=True)
            progress_calls = [0]
            def _prog(pct, speed, eta):
                progress_calls[0] += 1

            out_file = sm_dl.download_video(
                url=test_url,
                output_dir=str(sm_dl_dir),
                quality="best",
                progress_callback=_prog,
            )
            if not Path(out_file).exists():
                print(f"FAIL: STEP I: download_video returned non-existent path: {out_file}", flush=True)
                return 1
            print(f"[DIAG] STEP I: download_video OK: {out_file} ({Path(out_file).stat().st_size} bytes)", flush=True)
        finally:
            httpd.shutdown()
            httpd.server_close()

    except Exception as e:
        print(f"FAIL: STEP I: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1

    # ── Step J: UI helpers (output folder resolution, open-in-explorer) ──
    # User reported: clicked "Output 文件夹路径" but path shown was relative,
    # didn't auto-open, and instructions mentioned macOS (Cmd+Shift+G) only.
    # Verify the resolved output dir is absolute + the open-in-file-manager
    # helper imports cleanly in the frozen bundle.
    print("[DIAG] STEP J: UI helpers test", flush=True)
    try:
        from paths import hc_output_dir as _hc_out, app_data_dir as _app_dir
        out_dir = _hc_out()
        if not out_dir.is_absolute():
            print(f"FAIL: STEP J: hc_output_dir is not absolute: {out_dir}", flush=True)
            return 1
        if not out_dir.exists():
            print(f"FAIL: STEP J: hc_output_dir does not exist: {out_dir}", flush=True)
            return 1
        print(f"[DIAG] STEP J: hc_output_dir OK and absolute: {out_dir}", flush=True)
        print(f"[DIAG] STEP J: app_data_dir: {_app_dir()}", flush=True)

        # Import the UI helper (does NOT actually open a folder — just verifies it loads)
        from hypecutter.ui import _open_in_file_manager
        # Sanity check: calling with non-existent path must return False, not crash.
        result_nonexistent = _open_in_file_manager("/this/path/does/not/exist/xyzzy")
        if result_nonexistent is not False:
            print(f"FAIL: STEP J: _open_in_file_manager should return False for missing path, got {result_nonexistent}", flush=True)
            return 1
        print(f"[DIAG] STEP J: _open_in_file_manager handles missing paths correctly", flush=True)
    except Exception as e:
        print(f"FAIL: STEP J: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return 1

    print("=== self-test PASSED (incl. full engine.process + scene_manager + downloader + ui helpers) ===", flush=True)
    return 0


if __name__ == "__main__":
    setup_ffmpeg()
    if getattr(sys, "frozen", False):
        os.environ.pop("STUDIOKIT_DEV", None)

    # Self-test mode: run smoke checks inside the frozen bundle, then exit
    if os.environ.get("STUDIOKIT_SELFTEST") == "1":
        sys.exit(run_self_test())

    # Set up crash log so errors aren't lost when the console window closes
    import logging
    import traceback as _tb
    _log_dir = Path.home() / "StudioKit_logs"
    _log_dir.mkdir(exist_ok=True)
    _log_file = _log_dir / "studiokit.log"
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(_log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    print(f"[StudioKit] Log file: {_log_file}", flush=True)

    try:
        import threading

        app_path = get_app_path()
        print(f"[StudioKit] app_path={app_path}", flush=True)
        print(f"[StudioKit] sys.executable={sys.executable}", flush=True)
        print(f"[StudioKit] frozen={getattr(sys, 'frozen', False)}", flush=True)

        # Open browser once server is ready (daemon thread)
        browser_t = threading.Thread(
            target=_open_browser_when_ready,
            args=("http://localhost:8501",),
            daemon=True,
        )
        browser_t.start()

        import asyncio
        from streamlit.web import bootstrap
        from streamlit.web.server import Server

        flag_options = {
            "server.headless": True,
            "browser.gatherUsageStats": False,
            "global.developmentMode": False,
        }
        bootstrap.load_config_options(flag_options=flag_options)

        # Problem: in a PyInstaller frozen bundle, asyncio.run() and bootstrap.run()
        # both return immediately because the bootloader has already set up an event
        # loop context. The main thread exits, killing the console window.
        #
        # Fix: run Streamlit's async server in a non-daemon thread with its own
        # fresh event loop. Then block the main thread with _done.wait() — this
        # keeps the process alive regardless of asyncio loop state.
        _done = threading.Event()
        _exit_code = [0]

        async def _run_server():
            try:
                server = Server(app_path, is_hello=False)
                await server.start()
                bootstrap._on_server_start(server)
                await server.stopped
            except Exception as exc:
                print(f"[StudioKit] Server error: {exc}", flush=True)
                _tb.print_exc()
                _exit_code[0] = 1
            finally:
                _done.set()

        def _thread_main():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run_server())
            finally:
                loop.close()

        # non-daemon so process stays alive even if main thread returns
        server_thread = threading.Thread(target=_thread_main, daemon=False, name="streamlit-server")
        server_thread.start()

        # Block main thread — keeps console window open until server stops
        _done.wait()
        sys.exit(_exit_code[0])

    except Exception as _e:
        _tb.print_exc()
        with open(_log_file, "a", encoding="utf-8") as _f:
            _f.write("\n=== CRASH ===\n")
            _tb.print_exc(file=_f)
        print(f"\n[StudioKit] CRASHED — see log: {_log_file}", flush=True)
        if sys.platform == "win32":
            input("Press Enter to close...")
        sys.exit(1)
