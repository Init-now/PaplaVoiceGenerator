# Papla Voice Generator — MVP Codebase Notes

## 1. Purpose & Scope
- Browser-based text-to-speech (TTS) experience powered by Papla Media’s API, with ergonomic workflows for batch script generation and downloading. @papla_voice_web.py#20-490 @templates/index.html#1-305
- Supplementary tooling:
  - Desktop GUI built with Tkinter for offline-ish usage. @papla_voice_gui.py#1-386
  - CLI-oriented FFmpeg combiner to stitch generated MP3 clips. @audio_combiner.py#1-370

## 2. Core Modules
1. **`papla_voice_web.py` (Flask app)**
   - Configures templates/static paths, session-backed API key storage, and Flask-Session. @papla_voice_web.py#124-139
   - `/test-connection`: validates a Papla API key, fetches voices, and caches the key in the session. @papla_voice_web.py#140-173
   - `/` (GET/POST): main workflow; manages up to 10 script textareas, voice selection, single-script or batch TTS generation, and captures resulting audio as base64 data URLs for frontend playback/download. @papla_voice_web.py#300-490
   - (Removed) Earlier experimental audio combining endpoints were part of the Flask app; the current MVP focuses on TTS only.

2. **`templates/index.html` (Main UI)**
   - Provides sidebar settings, multi-script grid, CTA buttons, and generated-audio gallery. @templates/index.html#27-305
   - JS utilities for character counting, per-script submit buttons, download-all automation, and async calls to `/tools/combine-audio` & `/combine-audio`. @templates/index.html#305-745

3. **`audio_combiner.py`**
   - Scans `/audio_files`, sorts clips by timestamp embedded in filenames, injects 2–4 second silence gaps, and concatenates via FFmpeg’s concat demuxer. @audio_combiner.py#162-356
   - Performs dependency checks (FFmpeg), detailed logging, and temp-file cleanup. @audio_combiner.py#67-205 @audio_combiner.py#284-370

4. **`papla_voice_gui.py`**
   - Tkinter app with credential persistence, voice selection, local playback, and save-as dialog; communicates with the same Papla TTS endpoints via `requests`. @papla_voice_gui.py#30-386

5. **Utility Entrypoints**
   - `minimal_app.py`: lightweight Flask loader for serving `index.html` only (useful for static UX checks). @minimal_app.py#1-17
   - `run_app.sh` / `start.sh` / `stop.sh`: shell scripts to bootstrap the Flask server on port 5003 with optional `.venv` activation. @run_app.sh#1-19

## 3. External Dependencies
- **Python**: `Flask`, `Flask-Session`, `requests`, `tkinter` (stdlib), plus FFmpeg availability for audio mixing. @README.md#46-120 @audio_combiner.py#77-205
- **Papla Media API**: `GET /v1/voices` and `POST /v1/text-to-speech/{voice_id}` with `papla-api-key` header. @papla_voice_web.py#20-121 @papla_voice_gui.py#22-58

## 4. Run & Test (MVP)
1. Install deps per README. @README.md#46-70
2. `./run_app.sh` → visit `http://localhost:5003`.
3. Provide a valid API key, test connection, craft scripts, generate audio, optionally download or combine via browser / CLI helper.
4. For Tkinter GUI, `python papla_voice_gui.py` (ensuring GUI toolkit availability).

## 5. Observed Gaps / Next Questions
1. Server-side `/combine-audio-with-pauses` is placeholder (copies first file) — needs real DSP implementation or clearer “experimental” labeling. @papla_voice_web.py#671-705
2. No automated tests; smoke coverage for API flows or audio combiner would reduce regressions.
3. Secrets handling limited to in-session storage; consider env-based injection or encrypted persistence for multi-user hosting.
4. Frontend currently loads 15 script blocks regardless of use; could be virtualized/dynamic for perf.
5. GUI and web app duplicate logic (voice fetch, TTS request); opportunity to extract shared client module.

---

**MVP takeaway:** Functional end-to-end TTS pipeline (web + desktop) is in place with manual audio post-processing aids; next steps revolve around robustness, real audio processing, and UX polish.
