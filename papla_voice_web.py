"""Flask web interface for Papla voice generation."""
# Version: 2025-12-09-v2 - Fixed indentation
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import List, Optional
import tempfile
import shutil
import io
import contextlib
import re

import requests
from flask import Flask, render_template, request, session, jsonify, url_for, send_file
from flask_session import Session

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None  # type: ignore[assignment]

API_BASE_URL = "https://api.papla.media"
VOICES_ENDPOINT = f"{API_BASE_URL}/v1/voices"
TTS_ENDPOINT_TEMPLATE = f"{API_BASE_URL}/v1/text-to-speech/{{voice_id}}"
DEFAULT_MODEL_ID = "papla_p1"
MAX_TTS_CHARACTERS = 800
DEFAULT_AUDIO_MIME = "audio/mpeg"
AUDIO_EXTENSION_BY_MIME = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


def improve_text_for_tts(text: str) -> str:
    """Improve text for TTS by ensuring proper punctuation and adding pauses for better pacing."""
    if not text:
        return text
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Split text into sentences using regex
    sentence_endings = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s')
    sentences = sentence_endings.split(text)
    
    processed_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            # Capitalize first letter if it's lowercase
            if sentence[0].islower():
                sentence = sentence[0].upper() + sentence[1:]
            
            # Add commas before conjunctions for better pacing
            sentence = re.sub(r'(\w{3,}) (and|but|or|so|because) ', r'\1, \2 ', sentence)
            
            # Add commas after introductory words
            sentence = re.sub(r'(Well|Now|Then|However|Therefore|Moreover|Furthermore|Consequently|Meanwhile|Instead|Likewise|Similarly|Otherwise)( \w)', r'\1,\2', sentence)
            
            # Add period if doesn't end with punctuation
            if not sentence[-1] in '.!?':
                sentence += '.'
            processed_sentences.append(sentence)
    
    return ' '.join(processed_sentences)


def get_default_api_key() -> str:
    """Return an API key from the environment if present."""

    return os.environ.get("PAPLA_API_KEY", "")


@dataclass
class VoiceOption:
    voice_id: str
    display_name: str
    preview_url: Optional[str] = None


def _parse_voice_entries(payload: object) -> List[VoiceOption]:
    voices: List[VoiceOption] = []
    candidates: List[object] = []

    if isinstance(payload, dict):
        for key in ("voices", "data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, (list, tuple)):
                candidates = list(value)
                break
        else:
            if all(isinstance(key, str) for key in payload.keys()):
                for key, value in payload.items():
                    voice_id = key
                    display = value if isinstance(value, str) else None
                    preview_url = None
                    if isinstance(value, dict):
                        voice_id = value.get("voice_id") or value.get("id") or key
                        display = (
                            value.get("name")
                            or value.get("display_name")
                            or value.get("label")
                            or value.get("title")
                        )
                        preview_url = (
                            value.get("preview_url")
                            or value.get("sample_url")
                            or value.get("preview")
                            or value.get("audio_preview_url")
                            or value.get("demo_url")
                        )
                    if voice_id:
                        voices.append(
                            VoiceOption(
                                voice_id=str(voice_id),
                                display_name=str(display or voice_id),
                                preview_url=str(preview_url) if preview_url else None,
                            )
                        )
                if voices:
                    return voices
            candidates = list(payload.values())
    elif isinstance(payload, (list, tuple)):
        candidates = list(payload)

    seen: set[str] = set()
    for entry in candidates:
        if isinstance(entry, dict):
            voice_id = entry.get("voice_id") or entry.get("id") or entry.get("value")
            display = (
                entry.get("name")
                or entry.get("display_name")
                or entry.get("label")
                or entry.get("title")
            )
            preview_url = (
                entry.get("preview_url")
                or entry.get("sample_url")
                or entry.get("preview")
                or entry.get("audio_preview_url")
                or entry.get("demo_url")
            )
        elif isinstance(entry, str):
            voice_id = entry
            display = entry
            preview_url = None
        else:
            voice_id = str(entry)
            display = str(entry)
            preview_url = None

        if not voice_id:
            continue
        voice_id_str = str(voice_id)
        if voice_id_str in seen:
            continue
        seen.add(voice_id_str)
        voices.append(
            VoiceOption(
                voice_id=voice_id_str,
                display_name=str(display or voice_id),
                preview_url=str(preview_url) if preview_url else None,
            )
        )

    return voices


def _fetch_voice_options(api_key: str) -> List[VoiceOption]:
    headers = {
        "papla-api-key": api_key,
        "Accept": "application/json",
    }
    response = requests.get(VOICES_ENDPOINT, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    voices = _parse_voice_entries(payload)
    return voices


def _extract_pdf_lines(pdf_file) -> List[str]:
    """Extract raw text lines from an uploaded PDF file object.

    Returns a flat list of lines (with basic whitespace normalization).
    """

    if PdfReader is None:
        raise RuntimeError("PDF support is not available. Please install PyPDF2.")

    reader = PdfReader(pdf_file)
    lines: List[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                lines.append(re.sub(r"\s+", " ", line))
    return lines


def _is_speakable_line(line: str, mode: str = "strict") -> bool:
    """Return True if a line should be spoken, according to the chosen mode.

    "strict" filters more aggressively; "loose" allows more borderline lines.
    """

    if not line:
        return False

    # Basic content checks
    if len(line) < 5:
        return False

    # Drop lines that are mostly non-letters (IDs, codes, etc.)
    letters = sum(1 for ch in line if ch.isalpha())
    if letters / max(len(line), 1) < (0.3 if mode == "loose" else 0.5):
        return False

    # Timestamp patterns: 00:12, 01:02:03, [00:12], etc.
    timestamp_pattern = r"^\[?\d{1,2}:\d{2}(?::\d{2})?\]?"  # e.g. 00:12 or 01:02:03
    if re.match(timestamp_pattern, line):
        return False

    # Lines that look like timecodes or cue markers, e.g. 00:00: Intro
    if re.search(r"\b\d{1,2}:\d{2}\b", line) and len(line.split()) <= 6:
        return False

    # Common non-spoken prefixes
    lowered = line.lower()
    instruction_prefixes = (
        "note:",
        "notes:",
        "instruction:",
        "instructions:",
        "timestamp:",
        "timestamps:",
        "cue:",
        "cues:",
        "slide ",
    )
    if any(lowered.startswith(p) for p in instruction_prefixes):
        return False

    # Scene headings or all-caps short labels (INTRO, SCENE 1, SECTION 3)
    if line.isupper() and len(line) <= 40:
        # In loose mode, allow long-ish all-caps sentences.
        if mode == "loose" and len(line.split()) > 4:
            return True
        return False

    # Bullet-only lines with little text
    if re.match(r"^[\-•*]+$", line):
        return False

    return True


def _group_lines_for_tts(lines: List[str], max_characters: int, max_lines_per_chunk: int = 2) -> List[str]:
    """Group lines into chunks for TTS, up to max_lines_per_chunk and character limit."""

    chunks: List[str] = []
    i = 0
    while i < len(lines):
        current = lines[i]
        # Try to append one more line if available and within limit
        if (
            i + 1 < len(lines)
            and max_lines_per_chunk > 1
            and len(current) + 1 + len(lines[i + 1]) <= max_characters
        ):
            current = f"{current} {lines[i + 1]}"
            i += 2
        else:
            # Single line chunk (or would exceed char limit with the next one)
            # If a single line is too long, truncate to the hard limit.
            if len(current) > max_characters:
                current = current[: max_characters]
            i += 1
        chunks.append(current)
    return chunks


def _generate_tts_audio(script: str, voice_id: str, api_key: str, script_index: int, audio_sources: List[dict]) -> tuple[Optional[str], Optional[str]]:
    """Helper function to generate TTS audio and append to sources list."""
    try:
        # TTS API call
        headers = {
            "papla-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {"text": script, "model_id": DEFAULT_MODEL_ID}
        tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice_id)
        resp = requests.post(tts_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        audio_bytes = resp.content
        if not audio_bytes:
            raise ValueError("Empty audio received from Papla Media API.")
        mime_type = resp.headers.get("Content-Type", DEFAULT_AUDIO_MIME) or DEFAULT_AUDIO_MIME
        if not mime_type.startswith("audio/"):
            mime_type = DEFAULT_AUDIO_MIME
        audio_extension = AUDIO_EXTENSION_BY_MIME.get(mime_type, "mp3")
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        audio_src = f"data:{mime_type};base64,{audio_b64}"
        
        # Store the audio source with its index
        audio_sources.append({
            "index": script_index,
            "src": audio_src,
            "mime": mime_type,
            "extension": audio_extension,
            "script": script[:50] + "..." if len(script) > 50 else script
        })
        
        return None, f"Voice generated successfully for script {script_index + 1}."
    except requests.HTTPError as exc:
        resp = exc.response
        detail = ""
        if resp is not None:
            try:
                detail = resp.json().get("message", "")  # type: ignore[arg-type]
            except ValueError:
                detail = resp.text
            error = f"API error: {resp.status_code} {resp.reason}"
        else:
            error = f"API error: {exc}"
        if detail:
            detail = detail.strip()
            if detail:
                error = f"{error} – {detail}"
        return error, None
    except requests.RequestException as exc:
        return f"Network error: {exc}", None
    except ValueError as exc:
        return str(exc), None
    except Exception as exc:
        return f"Unexpected error: {str(exc)}", None


def make_app() -> Flask:
    # Get absolute paths to avoid path resolution issues
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(current_dir, "templates")
    static_dir = os.path.join(current_dir, "static")
    
    app = Flask(__name__, static_folder=static_dir, template_folder=template_dir)
    app.secret_key = os.environ.get("PAPLA_APP_SECRET", "papla-secret")
    
    # Configure session
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False
    
    # Initialize session
    Session(app)

    @app.route("/test-connection", methods=["POST"])
    def test_connection():
        """Test API connection and return list of voices"""
        api_key = request.form.get("api_key", "").strip()
        
        if not api_key:
            return {"error": "API key is required."}
        
        try:
            voices = _fetch_voice_options(api_key)
            # Store API key in session
            session['api_key'] = api_key
            return {
                "success": True,
                "message": f"Connection successful! Found {len(voices)} voices.",
                "voices": [
                    {
                        "voice_id": v.voice_id,
                        "display_name": v.display_name,
                        "preview_url": v.preview_url,
                    }
                    for v in voices
                ],
            }
        except requests.HTTPError as exc:
            resp = exc.response
            message = ""
            if resp is not None:
                try:
                    message = resp.json().get("message", "")
                except ValueError:
                    message = resp.text
                error_msg = f"Voice list error: {resp.status_code} {resp.reason}"
            else:
                error_msg = f"Voice list error: {exc}"
            if message:
                error_msg = f"{error_msg} – {message.strip()}"
            return {"error": error_msg}
        except requests.RequestException as exc:
            return {"error": f"Unable to refresh voices: {exc}"}

    @app.route("/upload-pdf", methods=["POST"])
    def upload_pdf():
        """Accept a PDF upload, extract text, and generate TTS clips for its content.

        The client provides:
        - pdf_file: uploaded PDF
        - api_key: optional (falls back to session)
        - voice: required
        - filter_mode: "strict" or "loose" (defaults to "strict")
        """

        api_key = request.form.get("api_key", "").strip() or session.get("api_key", "")
        voice = request.form.get("voice", "").strip()
        filter_mode = request.form.get("filter_mode", "strict").strip().lower()
        if filter_mode not in {"strict", "loose"}:
            filter_mode = "strict"

        if not api_key:
            return jsonify({"error": "API key is required."}), 400
        if not voice:
            return jsonify({"error": "Please select a voice."}), 400

        if "pdf_file" not in request.files:
            return jsonify({"error": "No PDF file provided."}), 400

        pdf_file = request.files["pdf_file"]
        if not pdf_file or not pdf_file.filename:
            return jsonify({"error": "No PDF file selected."}), 400

        if not pdf_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only PDF files are supported."}), 400

        try:
            raw_lines = _extract_pdf_lines(pdf_file)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 500
        except Exception as exc:  # pragma: no cover - defensive
            return jsonify({"error": f"Failed to read PDF: {exc}"}), 500

        speakable_lines = [ln for ln in raw_lines if _is_speakable_line(ln, filter_mode)]
        if not speakable_lines:
            return jsonify({"error": "No suitable lines found in PDF after filtering."}), 400

        chunks = _group_lines_for_tts(speakable_lines, MAX_TTS_CHARACTERS, max_lines_per_chunk=2)

        headers = {
            "papla-api-key": api_key,
            "Content-Type": "application/json",
        }
        audio_sources: List[dict] = []

        for idx, text in enumerate(chunks):
            text = improve_text_for_tts(text)
            if len(text) > MAX_TTS_CHARACTERS:
                text = text[:MAX_TTS_CHARACTERS]
            try:
                payload = {"text": text, "model_id": DEFAULT_MODEL_ID}
                tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice)
                resp = requests.post(tts_url, headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                audio_bytes = resp.content
                if not audio_bytes:
                    raise ValueError("Empty audio received from Papla Media API.")
                mime_type = resp.headers.get("Content-Type", DEFAULT_AUDIO_MIME) or DEFAULT_AUDIO_MIME
                if not mime_type.startswith("audio/"):
                    mime_type = DEFAULT_AUDIO_MIME
                audio_extension = AUDIO_EXTENSION_BY_MIME.get(mime_type, "mp3")
                audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                audio_src = f"data:{mime_type};base64,{audio_b64}"

                preview = text[:50] + "..." if len(text) > 50 else text
                audio_sources.append(
                    {
                        "index": idx,
                        "src": audio_src,
                        "mime": mime_type,
                        "extension": audio_extension,
                        "script": preview,
                    }
                )
            except Exception as exc:  # pragma: no cover - return partials
                return jsonify({
                    "error": f"Error generating audio for chunk {idx + 1}: {exc}",
                    "generated": audio_sources,
                }), 500

        return jsonify(
            {
                "success": True,
                "filter_mode": filter_mode,
                "total_lines": len(raw_lines),
                "speakable_lines": len(speakable_lines),
                "chunks": audio_sources,
            }
        )

    @app.route("/preview-voice", methods=["POST"])
    def preview_voice():
        """Generate a short preview clip for the selected voice."""

        api_key = request.form.get("api_key", "").strip() or session.get("api_key", "")
        voice = request.form.get("voice", "").strip()
        text = request.form.get("text", "").strip() or "This is a sample of this voice."

        text = improve_text_for_tts(text)

        if not api_key:
            return jsonify({"error": "API key is required."}), 400
        if not voice:
            return jsonify({"error": "Please select a voice."}), 400

        if len(text) > MAX_TTS_CHARACTERS:
            text = text[:MAX_TTS_CHARACTERS]

        headers = {
            "papla-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = {"text": text, "model_id": DEFAULT_MODEL_ID}
        tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice)

        try:
            resp = requests.post(tts_url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            audio_bytes = resp.content
            if not audio_bytes:
                raise ValueError("Empty audio received from Papla Media API.")
            mime_type = resp.headers.get("Content-Type", DEFAULT_AUDIO_MIME) or DEFAULT_AUDIO_MIME
            if not mime_type.startswith("audio/"):
                mime_type = DEFAULT_AUDIO_MIME
            audio_extension = AUDIO_EXTENSION_BY_MIME.get(mime_type, "mp3")
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            audio_src = f"data:{mime_type};base64,{audio_b64}"

            preview = text[:50] + "..." if len(text) > 50 else text
            return jsonify(
                {
                    "success": True,
                    "src": audio_src,
                    "mime": mime_type,
                    "extension": audio_extension,
                    "script": preview,
                }
            )
        except requests.HTTPError as exc:
            resp = exc.response
            detail = ""
            if resp is not None:
                try:
                    detail = resp.json().get("message", "")  # type: ignore[arg-type]
                except ValueError:
                    detail = resp.text
                error_msg = f"API error: {resp.status_code} {resp.reason}"
            else:
                error_msg = f"API error: {exc}"
            if detail:
                detail = detail.strip()
                if detail:
                    error_msg = f"{error_msg} – {detail}"
            return jsonify({"error": error_msg}), 502
        except requests.RequestException as exc:
            return jsonify({"error": f"Network error: {exc}"}), 502
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/", methods=["GET", "POST"])
    def index():
        # Get API key from session or form
        api_key = session.get('api_key', '')
        
        # Initialize variables
        scripts = ["", "", ""]  # Default 3 empty scripts
        voice = ""
        audio_sources: List[dict] = []  # Store multiple audio sources
        error: Optional[str] = None
        status: Optional[str] = None
        voice_warning: Optional[str] = None
        voices: List[VoiceOption] = []
        trigger_generation = False
        trigger_generation_all = False

        if request.method == "POST":
            # Update API key if provided in form
            form_api_key = request.form.get("api_key", "").strip()
            if form_api_key:
                api_key = form_api_key
                session['api_key'] = api_key
            
            # Get scripts from form
            scripts = []
            for i in range(1, 11):  # Support up to 10 scripts
                script_key = f"script_{i}"
                if script_key in request.form:
                    scripts.append(request.form.get(script_key, "").strip())
            
            # Ensure we have at least 3 scripts
            while len(scripts) < 3:
                scripts.append("")
            
            voice = request.form.get("voice", "").strip()
            trigger_generation = "generate" in request.form
            trigger_generation_all = "generate_all" in request.form

        if api_key:
            try:
                voices = _fetch_voice_options(api_key)
            except requests.HTTPError as exc:
                resp = exc.response
                message = ""
                if resp is not None:
                    try:
                        message = resp.json().get("message", "")  # type: ignore[arg-type]
                    except ValueError:
                        message = resp.text
                    voice_warning = f"Voice list error: {resp.status_code} {resp.reason}"
                else:
                    voice_warning = f"Voice list error: {exc}"
                if message:
                    voice_warning = f"{voice_warning} – {message.strip()}"
            except requests.RequestException as exc:
                voice_warning = f"Unable to refresh voices: {exc}"

        if not voice and voices:
            voice = voices[0].voice_id

        # Handle single script generation
        if trigger_generation and not error:
            script_index = int(request.form.get("script_index", "0"))
            script = scripts[script_index] if script_index < len(scripts) else ""
            
            script = improve_text_for_tts(script)
            
            if not api_key:
                error = "API key is required."
            elif not script:
                error = "Please enter some text to synthesize."
            else:
                if len(script) > MAX_TTS_CHARACTERS:
                    script = script[:MAX_TTS_CHARACTERS]
                if not voice:
                    error = "Please select a voice."
                else:
                    try:
                        # TTS API call
                        headers = {
                            "papla-api-key": api_key,
                            "Content-Type": "application/json",
                        }
                        payload = {"text": script, "model_id": DEFAULT_MODEL_ID}
                        tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice)
                        resp = requests.post(tts_url, headers=headers, json=payload, timeout=60)
                        resp.raise_for_status()
                        audio_bytes = resp.content
                        if not audio_bytes:
                            raise ValueError("Empty audio received from Papla Media API.")
                        mime_type = resp.headers.get("Content-Type", DEFAULT_AUDIO_MIME) or DEFAULT_AUDIO_MIME
                        if not mime_type.startswith("audio/"):
                            mime_type = DEFAULT_AUDIO_MIME
                        audio_extension = AUDIO_EXTENSION_BY_MIME.get(mime_type, "mp3")
                        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                        audio_src = f"data:{mime_type};base64,{audio_b64}"
                        
                        # Store the audio source with its index
                        audio_sources.append({
                            "index": script_index,
                            "src": audio_src,
                            "mime": mime_type,
                            "extension": audio_extension,
                            "script": script[:50] + "..." if len(script) > 50 else script
                        })
                        
                        status = f"Voice generated successfully for script {script_index + 1}."
                    except requests.HTTPError as exc:
                        resp = exc.response
                        detail = ""
                        if resp is not None:
                            try:
                                detail = resp.json().get("message", "")  # type: ignore[arg-type]
                            except ValueError:
                                detail = resp.text
                            error = f"API error: {resp.status_code} {resp.reason}"
                        else:
                            error = f"API error: {exc}"
                        if detail:
                            detail = detail.strip()
                            if detail:
                                error = f"{error} – {detail}"
                    except requests.RequestException as exc:
                        error = f"Network error: {exc}"
                    except ValueError as exc:
                        error = str(exc)

        # Handle generate all scripts
        if trigger_generation_all and not error:
            if not api_key:
                error = "API key is required."
            elif not any(scripts):
                error = "Please enter at least one script to synthesize."
            elif not voice:
                error = "Please select a voice."
            else:
                generated_count = 0
                for i, script in enumerate(scripts):
                    if not script:
                        continue
                    script = improve_text_for_tts(script)
                    if len(script) > MAX_TTS_CHARACTERS:
                        script = script[:MAX_TTS_CHARACTERS]
                    
                    try:
                        headers = {
                            "papla-api-key": api_key,
                            "Content-Type": "application/json",
                        }
                        payload = {"text": script, "model_id": DEFAULT_MODEL_ID}
                        tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice)
                        resp = requests.post(tts_url, headers=headers, json=payload, timeout=60)
                        resp.raise_for_status()
                        audio_bytes = resp.content
                        if not audio_bytes:
                            raise ValueError("Empty audio received from Papla Media API.")
                        mime_type = resp.headers.get("Content-Type", DEFAULT_AUDIO_MIME) or DEFAULT_AUDIO_MIME
                        if not mime_type.startswith("audio/"):
                            mime_type = DEFAULT_AUDIO_MIME
                        audio_extension = AUDIO_EXTENSION_BY_MIME.get(mime_type, "mp3")
                        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
                        audio_src = f"data:{mime_type};base64,{audio_b64}"
                        
                        # Store the audio source with its index
                        audio_sources.append({
                            "index": i,
                            "src": audio_src,
                            "mime": mime_type,
                            "extension": audio_extension,
                            "script": script[:50] + "..." if len(script) > 50 else script
                        })
                        
                        generated_count += 1
                    except Exception as exc:
                        error = f"Error generating script {i+1}: {str(exc)}"
                        break
                
                if not error:
                    status = f"Successfully generated {generated_count} voice(s)."

        if not voices and voice:
            voices = [VoiceOption(voice_id=voice, display_name=voice)]

        return render_template(
            "index.html",
            api_key=api_key,
            scripts=scripts,
            voice=voice,
            audio_sources=audio_sources,
            error=error,
            status=status,
            voice_warning=voice_warning,
            voices=voices,
            max_characters=MAX_TTS_CHARACTERS,
        )

    return app


app = make_app()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=5003, debug=debug)
