"""Papla voice generator GUI.

Provide a Tkinter interface to enter text, choose a voice, submit to the
Papla Voice API, and play or save the generated audio locally."""

from __future__ import annotations

import base64
import os
import platform
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, List

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

API_BASE_URL = "https://api.papla.media"
VOICES_ENDPOINT = f"{API_BASE_URL}/v1/voices"
TTS_ENDPOINT_TEMPLATE = f"{API_BASE_URL}/v1/text-to-speech/{{voice_id}}"
DEFAULT_VOICE = "alloy"
CONFIG_DIR = Path.home() / ".papla_voice_app"
CONFIG_FILE = CONFIG_DIR / "config.json"
PREVIEW_TEXT = "This is a sample of this voice."


def _fetch_voice_options(api_key: str) -> List[str]:
    """Fetch available voices from Papla API."""
    try:
        headers = {
            "papla-api-key": api_key,
            "Accept": "application/json",
        }
        response = requests.get(VOICES_ENDPOINT, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        
        # Parse voice options from response
        voices = []
        if isinstance(payload, dict):
            for key in ("voices", "data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, (list, tuple)):
                    voices = [str(v.get("voice_id") or v.get("id") or v) if isinstance(v, dict) else str(v) for v in value]
                    break
            else:
                # If no standard keys found, try to extract from dict values
                voices = [str(k) for k in payload.keys() if isinstance(k, str)]
        elif isinstance(payload, (list, tuple)):
            voices = [str(v.get("voice_id") or v.get("id") or v) if isinstance(v, dict) else str(v) for v in payload]
        
        return voices
    except Exception as exc:
        print(f"Error fetching voices: {exc}")
        return ["alloy", "bright", "warm", "resonant"]  # Fallback voices


def get_env_api_key() -> Optional[str]:
    """Retrieve a Papla API key from the environment if available."""

    return os.environ.get("PAPLA_API_KEY")


def load_saved_api_key() -> Optional[str]:
    """Return the persisted API key if one exists on disk."""

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def save_api_key_to_disk(api_key: str) -> None:
    """Persist the provided API key to the user's config file."""

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as fh:
            fh.write(api_key)
    except OSError:
        # Silently ignore persistence errors; the app can run without saving.
        pass


def clear_saved_api_key() -> None:
    """Remove the stored API key if present."""

    try:
        CONFIG_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


class PaplaVoiceApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("")
        self.root.geometry("840x640")

        self.thumbnail_refs: list[tk.PhotoImage] = []  # Placeholder to mirror structure
        self.env_api_key = get_env_api_key()
        self.saved_api_key = load_saved_api_key()

        self.temp_files: list[str] = []
        self.latest_audio_path: Optional[str] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        api_frame = ttk.LabelFrame(main_frame, text="API Credentials", padding=12)
        api_frame.pack(fill=tk.X, expand=False, pady=(0, 12))

        ttk.Label(api_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        initial_api_key = self.env_api_key or self.saved_api_key or ""
        self.api_var = tk.StringVar(value=initial_api_key)
        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_var, show="*")
        self.api_entry.grid(row=0, column=1, sticky=tk.EW)
        api_frame.columnconfigure(1, weight=1)

        self.remember_var = tk.BooleanVar(value=bool(self.saved_api_key))
        remember_check = ttk.Checkbutton(
            api_frame,
            variable=self.remember_var,
            text="Remember API key on this device",
        )
        remember_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        self.forget_button = ttk.Button(
            api_frame,
            text="Forget stored key",
            command=self._forget_api_key,
        )
        self.forget_button.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
        if not self.saved_api_key:
            self.forget_button.state(["disabled"])

        voice_frame = ttk.LabelFrame(main_frame, text="Voice Settings", padding=12)
        voice_frame.pack(fill=tk.X, expand=False, pady=(0, 12))

        ttk.Label(voice_frame, text="Voice:").grid(row=0, column=0, sticky=tk.W)
        self.voice_var = tk.StringVar(value=DEFAULT_VOICE)
        
        # Fetch available voices if API key is available
        api_key = self.env_api_key or self.saved_api_key
        if api_key:
            voices = _fetch_voice_options(api_key)
        else:
            voices = ["alloy", "bright", "warm", "resonant"]  # Fallback voices
            
        self.voice_combo = ttk.Combobox(
            voice_frame,
            textvariable=self.voice_var,
            values=voices,
            state="readonly",
            width=18,
        )
        self.voice_combo.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

        preview_button = ttk.Button(
            voice_frame,
            text="Preview Voices",
            command=self._preview_voices,
        )
        preview_button.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

        self.voice_preview_button = ttk.Button(
            voice_frame,
            text="Listen Preview",
            command=self.start_voice_preview,
        )
        self.voice_preview_button.grid(row=1, column=2, columnspan=2, sticky=tk.W, pady=(8, 0))

        ttk.Label(voice_frame, text="Format:").grid(row=0, column=2, sticky=tk.W, padx=(16, 0))
        self.format_var = tk.StringVar(value="mp3")
        self.format_combo = ttk.Combobox(
            voice_frame,
            textvariable=self.format_var,
            values=["mp3", "wav", "ogg"],
            state="readonly",
            width=10,
        )
        self.format_combo.grid(row=0, column=3, sticky=tk.W, padx=(8, 0))

        text_frame = ttk.LabelFrame(main_frame, text="Script", padding=12)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        self.text_widget = tk.Text(text_frame, wrap=tk.WORD, height=12)
        self.text_widget.pack(fill=tk.BOTH, expand=True)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, expand=False, pady=(0, 12))

        self.generate_button = ttk.Button(
            action_frame,
            text="Generate Voice",
            command=self.start_generation,
        )
        self.generate_button.pack(side=tk.LEFT)

        self.play_button = ttk.Button(
            action_frame,
            text="Play",
            command=self._play_audio,
            state="disabled",
        )
        self.play_button.pack(side=tk.LEFT, padx=(8, 0))

        self.save_button = ttk.Button(
            action_frame,
            text="Save As...",
            command=self._save_audio,
            state="disabled",
        )
        self.save_button.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Enter text and press Generate Voice")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(fill=tk.X)

    def _preview_voices(self) -> None:
        api_key = self.api_var.get().strip() or self.env_api_key or self.saved_api_key or ""
        if not api_key:
            messagebox.showwarning("Missing API Key", "Please provide a Papla API key to load voices.")
            return

        self._set_status("Fetching available voices…")
        try:
            voices: List[str] = _fetch_voice_options(api_key)
        except Exception as exc:  # defensive
            messagebox.showerror("Voice Fetch Error", f"Unable to fetch voices: {exc}")
            self._set_status("Failed to fetch voices.")
            return

        if not voices:
            messagebox.showinfo("Available Voices", "No voices were returned by the API.")
            self._set_status("No voices returned by API.")
            return

        # Refresh combobox with latest voices
        self.voice_combo["values"] = voices
        self.voice_var.set(voices[0])

        preview_text = "\n".join(voices)
        messagebox.showinfo("Available Voices", preview_text)
        self._set_status(f"Loaded {len(voices)} voice option(s).")

    def start_voice_preview(self) -> None:
        api_key = self.api_var.get().strip()
        if not api_key:
            messagebox.showwarning("Missing API Key", "Please provide a Papla API key.")
            return

        voice = self.voice_var.get()
        audio_format = self.format_var.get()

        self._set_status("Generating voice preview...")
        self.voice_preview_button.state(["disabled"])

        thread = threading.Thread(
            target=self._preview_voice,
            args=(api_key, voice, audio_format),
            daemon=True,
        )
        thread.start()

    def _preview_voice(self, api_key: str, voice: str, audio_format: str) -> None:
        try:
            headers = {
                "papla-api-key": api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": PREVIEW_TEXT,
                "model_id": "papla_p1",
            }
            tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice)
            response = requests.post(tts_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            audio_bytes = response.content
            if not audio_bytes:
                raise ValueError("Empty audio received from Papla Media API.")

            mime_type = response.headers.get("Content-Type", "audio/mpeg") or "audio/mpeg"
            if not mime_type.startswith("audio/"):
                mime_type = "audio/mpeg"

            audio_extension_map = {
                "audio/mpeg": "mp3",
                "audio/mp3": "mp3",
                "audio/wav": "wav",
                "audio/x-wav": "wav",
                "audio/ogg": "ogg",
                "audio/webm": "webm",
            }
            audio_extension = audio_extension_map.get(mime_type, audio_format or "mp3")

            with tempfile.NamedTemporaryFile(suffix=f".{audio_extension}", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

        except requests.HTTPError as exc:
            self._set_status(f"API error (preview): {exc.response.status_code} {exc.response.reason}")
            self._enable_voice_preview()
            return
        except requests.RequestException as exc:
            self._set_status(f"Network error (preview): {exc}")
            self._enable_voice_preview()
            return
        except ValueError as exc:
            self._set_status(f"Invalid preview response: {exc}")
            self._enable_voice_preview()
            return
        except OSError as exc:
            self._set_status(f"Failed to save preview audio: {exc}")
            self._enable_voice_preview()
            return

        self.temp_files.append(temp_path)
        self.latest_audio_path = temp_path

        def _play_preview() -> None:
            self._set_status("Playing voice preview...")
            self._play_audio()
            self.voice_preview_button.state(["!disabled"])

        self.root.after(0, _play_preview)

    def _enable_voice_preview(self) -> None:
        self.root.after(0, lambda: self.voice_preview_button.state(["!disabled"]))

    def start_generation(self) -> None:
        api_key = self.api_var.get().strip()
        script = self.text_widget.get("1.0", tk.END).strip()

        if not api_key:
            messagebox.showwarning("Missing API Key", "Please provide a Papla API key.")
            return

        if not script:
            messagebox.showwarning("Missing Script", "Please enter some text to synthesize.")
            return

        self._persist_api_key_choice(api_key)
        self._set_status("Generating voice...")
        self.generate_button.state(["disabled"])
        self.play_button.state(["disabled"])
        self.save_button.state(["disabled"])

        voice = self.voice_var.get()
        audio_format = self.format_var.get()

        thread = threading.Thread(
            target=self._generate_voice,
            args=(api_key, script, voice, audio_format),
            daemon=True,
        )
        thread.start()

    def _persist_api_key_choice(self, api_key: str) -> None:
        if self.remember_var.get() and api_key:
            save_api_key_to_disk(api_key)
            self.saved_api_key = api_key
            self.forget_button.state(["!disabled"])
        else:
            clear_saved_api_key()
            self.saved_api_key = None
            self.forget_button.state(["disabled"])

    def _forget_api_key(self) -> None:
        clear_saved_api_key()
        self.saved_api_key = None
        self.remember_var.set(False)
        self.api_var.set("")
        self.forget_button.state(["disabled"])
        self._set_status("Stored API key cleared. Please enter a key to continue.")

    def _generate_voice(self, api_key: str, script: str, voice: str, audio_format: str) -> None:
        try:
            headers = {
                "papla-api-key": api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": script,
                "model_id": "papla_p1",
            }
            tts_url = TTS_ENDPOINT_TEMPLATE.format(voice_id=voice)
            response = requests.post(tts_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            audio_bytes = response.content
            if not audio_bytes:
                raise ValueError("Empty audio received from Papla Media API.")
            
            # Determine file extension from MIME type
            mime_type = response.headers.get("Content-Type", "audio/mpeg") or "audio/mpeg"
            if not mime_type.startswith("audio/"):
                mime_type = "audio/mpeg"
            
            audio_extension_map = {
                "audio/mpeg": "mp3",
                "audio/mp3": "mp3",
                "audio/wav": "wav",
                "audio/x-wav": "wav",
                "audio/ogg": "ogg",
                "audio/webm": "webm",
            }
            audio_extension = audio_extension_map.get(mime_type, "mp3")
            
            with tempfile.NamedTemporaryFile(suffix=f".{audio_extension}", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

        except requests.HTTPError as exc:
            self._set_status(f"API error: {exc.response.status_code} {exc.response.reason}")
            self._enable_generate()
            return
        except requests.RequestException as exc:
            self._set_status(f"Network error: {exc}")
            self._enable_generate()
            return
        except ValueError as exc:
            self._set_status(f"Invalid response from API: {exc}")
            self._enable_generate()
            return
        except OSError as exc:
            self._set_status(f"Failed to save audio: {exc}")
            self._enable_generate()
            return

        self.temp_files.append(temp_path)
        self.latest_audio_path = temp_path
        self.root.after(0, lambda: self._on_generation_success(temp_path))

    def _on_generation_success(self, path: str) -> None:
        self._set_status(f"Voice generated ({path}).")
        self.generate_button.state(["!disabled"])
        self.play_button.state(["!disabled"])
        self.save_button.state(["!disabled"])

    def _enable_generate(self) -> None:
        self.root.after(0, lambda: self.generate_button.state(["!disabled"]))

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _play_audio(self) -> None:
        if not self.latest_audio_path:
            return

        try:
            if platform.system() == "Windows":
                os.startfile(self.latest_audio_path)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.run(["open", self.latest_audio_path], check=True)
            else:
                subprocess.run(["xdg-open", self.latest_audio_path], check=True)
            self._set_status("Playing audio...")
        except (subprocess.SubprocessError, OSError) as exc:
            self._set_status(f"Failed to open audio player: {exc}")

    def _save_audio(self) -> None:
        if not self.latest_audio_path:
            return

        audio_format = self.format_var.get()
        path = filedialog.asksaveasfilename(
            title="Save Audio",
            defaultextension=f".{audio_format}",
            filetypes=[
                (audio_format.upper(), f"*.{audio_format}"),
                ("All Files", "*.*"),
            ],
            initialfile="papla_voice_output",
        )
        if not path:
            return

        try:
            shutil.copyfile(self.latest_audio_path, path)
            self._set_status(f"Audio saved to {path}")
        except OSError as exc:
            self._set_status(f"Failed to save audio: {exc}")

    def _on_close(self) -> None:
        for temp_path in self.temp_files:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    PaplaVoiceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
