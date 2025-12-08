"""Pexels image search GUI.

Search the Pexels API for photos, preview thumbnails, open them in the browser,
or download locally using a Tkinter interface.
"""

from __future__ import annotations

import io
import json
import os
import platform
import subprocess
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

import requests
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

API_URL = "https://api.pexels.com/v1/search"
PHOTO_API_URL = "https://api.pexels.com/v1/search"
VIDEO_API_URL = "https://api.pexels.com/videos/search"
DEFAULT_RESULTS = 9
CONFIG_DIR = Path.home() / ".pexels_app"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_env_api_key() -> str | None:
    """Retrieve a Pexels API key from the environment if available."""
    return os.environ.get("PEXELS_API_KEY")


def load_saved_api_key() -> str | None:
    """Return the persisted API key if one exists on disk."""

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    except OSError:
        return None

    return data.get("api_key") if isinstance(data, dict) else None


def save_api_key_to_disk(api_key: str) -> None:
    """Persist the provided API key to the user's config file."""

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as fh:
            json.dump({"api_key": api_key}, fh)
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


@dataclass
class PhotoInfo:
    """Lightweight wrapper around Pexels photo data."""

    id: int
    photographer: str
    url: str
    image_url: str


@dataclass
class VideoInfo:
    """Lightweight wrapper around Pexels video data."""

    id: int
    photographer: str
    url: str
    video_files: List[dict]
    image_preview: str
    duration: int


MediaInfo = Union[PhotoInfo, VideoInfo]


class PexelsApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pexels Media Search")
        self.root.geometry("960x720")

        self.thumbnail_refs: List[ImageTk.PhotoImage] = []
        self.temp_files: List[str] = []  # Track temporary video files
        self.env_api_key = get_env_api_key()
        self.saved_api_key = load_saved_api_key()

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct all UI widgets."""

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

        search_frame = ttk.LabelFrame(main_frame, text="Search", padding=12)
        search_frame.pack(fill=tk.X, expand=False, pady=(0, 12))

        ttk.Label(search_frame, text="Query:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        self.query_var = tk.StringVar()
        query_entry = ttk.Entry(search_frame, textvariable=self.query_var)
        query_entry.grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(search_frame, text="Media Type:").grid(row=0, column=2, sticky=tk.W, padx=(12, 8))
        self.media_type_var = tk.StringVar(value="photos")
        media_type_combo = ttk.Combobox(
            search_frame,
            textvariable=self.media_type_var,
            values=["photos", "videos", "all"],
            state="readonly",
            width=10,
        )
        media_type_combo.grid(row=0, column=3, sticky=tk.W)

        ttk.Label(search_frame, text="Results:").grid(row=1, column=0, sticky=tk.W, padx=(0, 8))
        self.results_var = tk.IntVar(value=DEFAULT_RESULTS)
        results_spin = ttk.Spinbox(
            search_frame,
            from_=1,
            to=80,
            textvariable=self.results_var,
            width=5,
        )
        results_spin.grid(row=1, column=1, sticky=tk.W)

        search_button = ttk.Button(search_frame, text="Search", command=self.start_search)
        search_button.grid(row=1, column=2, columnspan=2, padx=(12, 0), sticky=tk.W)
        search_frame.columnconfigure(1, weight=1)

        self.status_var = tk.StringVar(value="Enter a query and press Search")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(fill=tk.X)

        results_container = ttk.Frame(main_frame)
        results_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(results_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(results_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.results_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.results_frame, anchor="nw")

        self.results_frame.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.bind_all("<MouseWheel>", self._on_mouse_wheel)

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def start_search(self) -> None:
        """Run the search in a background thread to keep the UI responsive."""

        api_key = self.api_var.get().strip()
        query = self.query_var.get().strip()
        media_type = self.media_type_var.get()

        if not api_key:
            messagebox.showwarning("Missing API Key", "Please provide a Pexels API key.")
            return

        if not query:
            messagebox.showwarning("Missing Query", "Please enter a search term.")
            return

        per_page = max(1, min(80, self.results_var.get()))

        self.status_var.set("Searching...")
        self._clear_results()

        self._persist_api_key_choice(api_key)

        thread = threading.Thread(
            target=self._perform_search,
            args=(api_key, query, per_page, media_type),
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
        if hasattr(self, "status_var"):
            self.status_var.set("Stored API key cleared. Please enter a key to continue.")

    def _perform_search(self, api_key: str, query: str, per_page: int, media_type: str) -> None:
        try:
            headers = {"Authorization": api_key}
            results = []

            # Search for photos if requested
            if media_type in ["photos", "all"]:
                params = {"query": query, "per_page": per_page}
                response = requests.get(PHOTO_API_URL, headers=headers, params=params, timeout=20)
                response.raise_for_status()
                data = response.json()
                photos = [
                    PhotoInfo(
                        id=item["id"],
                        photographer=item["photographer"],
                        url=item["url"],
                        image_url=item["src"].get("medium") or item["src"].get("original"),
                    )
                    for item in data.get("photos", [])
                    if item.get("src")
                ]
                results.extend(photos)

            # Search for videos if requested
            if media_type in ["videos", "all"]:
                params = {"query": query, "per_page": per_page}
                response = requests.get(VIDEO_API_URL, headers=headers, params=params, timeout=20)
                response.raise_for_status()
                data = response.json()
                videos = [
                    VideoInfo(
                        id=item["id"],
                        photographer=item["photographer"],
                        url=item["url"],
                        video_files=item.get("video_files", []),
                        image_preview=item.get("image"),
                        duration=item.get("duration", 0),
                    )
                    for item in data.get("videos", [])
                    if item.get("video_files") and item.get("image")
                ]
                results.extend(videos)

        except requests.HTTPError as exc:
            self._set_status(f"API error: {exc.response.status_code} {exc.response.reason}")
            return
        except requests.RequestException as exc:
            self._set_status(f"Network error: {exc}")
            return

        if not results:
            self._set_status("No results found.")
            return

        self.root.after(0, lambda: self._display_results(results))

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _clear_results(self) -> None:
        for child in self.results_frame.winfo_children():
            child.destroy()
        self.thumbnail_refs.clear()
        
        # Clean up temporary video files
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass
        self.temp_files.clear()

    def _display_results(self, media_items: List[MediaInfo]) -> None:
        self._clear_results()
        self.status_var.set(f"Displaying {len(media_items)} result(s)")

        for idx, media in enumerate(media_items, start=1):
            frame = ttk.Frame(self.results_frame, padding=12)
            frame.grid(row=(idx - 1) // 3, column=(idx - 1) % 3, sticky=tk.NSEW, padx=6, pady=6)

            image_label = ttk.Label(frame)
            image_label.pack()

            # Display media information
            if isinstance(media, PhotoInfo):
                info_text = f"Photo #{media.id}\nBy {media.photographer}"
            else:  # VideoInfo
                duration_min = media.duration // 60
                duration_sec = media.duration % 60
                info_text = f"Video #{media.id}\nBy {media.photographer}\nDuration: {duration_min}:{duration_sec:02d}"

            photographer_label = ttk.Label(
                frame,
                text=info_text,
                justify=tk.CENTER,
            )
            photographer_label.pack(pady=(8, 4))

            button_frame = ttk.Frame(frame)
            button_frame.pack()

            open_button = ttk.Button(
                button_frame,
                text="Open",
                command=lambda url=media.url: webbrowser.open(url),
            )
            open_button.pack(side=tk.LEFT, padx=4)

            # Add preview button for videos
            if isinstance(media, VideoInfo):
                preview_button = ttk.Button(
                    button_frame,
                    text="Preview",
                    command=lambda info=media: self._preview_video(info),
                )
                preview_button.pack(side=tk.LEFT, padx=4)

            download_button = ttk.Button(
                button_frame,
                text="Download",
                command=lambda info=media: self._download_media(info),
            )
            download_button.pack(side=tk.LEFT, padx=4)

            # Load thumbnail
            if isinstance(media, PhotoInfo):
                self._load_thumbnail_async(media.image_url, image_label)
            else:  # VideoInfo
                self._load_thumbnail_async(media.image_preview, image_label)

        for column in range(3):
            self.results_frame.columnconfigure(column, weight=1)

    def _load_thumbnail_async(self, url: str, label: ttk.Label) -> None:
        def worker() -> None:
            image = self._fetch_image(url)
            if image is None:
                return

            image.thumbnail((240, 240))
            photo_image = ImageTk.PhotoImage(image)

            def update() -> None:
                label.configure(image=photo_image)
                self.thumbnail_refs.append(photo_image)

            self.root.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_image(self, url: str) -> Image.Image | None:
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content))
        except requests.RequestException as exc:
            self._set_status(f"Image download failed: {exc}")
        except Image.UnidentifiedImageError:
            self._set_status("Unsupported image format returned by API")
        return None

    def _preview_video(self, video: VideoInfo) -> None:
        """Download and preview a video file locally."""
        # Get the best quality video file (prefer HD)
        video_file = None
        for vf in video.video_files:
            if vf.get("quality") == "hd":
                video_file = vf
                break
        
        if not video_file:
            # Fallback to any available file
            video_file = video.video_files[0] if video.video_files else None
        
        if not video_file:
            self._set_status("No video file available for preview")
            return

        video_url = video_file.get("file_link")
        if not video_url:
            self._set_status("Invalid video URL")
            return

        self._set_status("Downloading video for preview...")
        
        def download_worker():
            try:
                response = requests.get(video_url, stream=True, timeout=30)
                response.raise_for_status()
                
                # Create a temporary file
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_file.write(chunk)
                    temp_path = temp_file.name
                
                self.temp_files.append(temp_path)
                
                # Open the video with the default player
                self._set_status("Opening video preview...")
                self._open_video_player(temp_path)
                
            except requests.RequestException as exc:
                self._set_status(f"Video download failed: {exc}")
            except OSError as exc:
                self._set_status(f"Failed to save video: {exc}")

        threading.Thread(target=download_worker, daemon=True).start()

    def _open_video_player(self, video_path: str) -> None:
        """Open video file with the system's default video player."""
        try:
            if platform.system() == "Windows":
                os.startfile(video_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", video_path], check=True)
            else:  # Linux and other Unix-like
                subprocess.run(["xdg-open", video_path], check=True)
        except (subprocess.SubprocessError, OSError) as exc:
            self._set_status(f"Failed to open video player: {exc}")

    def _download_media(self, media: MediaInfo) -> None:
        """Download either a photo or video based on the media type."""
        if isinstance(media, PhotoInfo):
            self._download_photo(media)
        else:  # VideoInfo
            self._download_video(media)

    def _download_photo(self, photo: PhotoInfo) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("All Files", "*.*")],
            initialfile=f"pexels_{photo.id}.jpg",
        )
        if not path:
            return

        image = self._fetch_image(photo.image_url)
        if image is None:
            return

        try:
            image.save(path)
            self._set_status(f"Saved to {path}")
        except OSError as exc:
            self._set_status(f"Failed to save image: {exc}")

    def _download_video(self, video: VideoInfo) -> None:
        """Download a video file to the user's chosen location."""
        # Get the best quality video file (prefer HD)
        video_file = None
        for vf in video.video_files:
            if vf.get("quality") == "hd":
                video_file = vf
                break
        
        if not video_file:
            # Fallback to any available file
            video_file = video.video_files[0] if video.video_files else None
        
        if not video_file:
            self._set_status("No video file available for download")
            return

        video_url = video_file.get("file_link")
        if not video_url:
            self._set_status("Invalid video URL")
            return

        path = filedialog.asksaveasfilename(
            title="Save Video",
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4"), ("All Files", "*.*")],
            initialfile=f"pexels_video_{video.id}.mp4",
        )
        if not path:
            return

        self._set_status("Downloading video...")
        
        def download_worker():
            try:
                response = requests.get(video_url, stream=True, timeout=30)
                response.raise_for_status()
                
                with open(path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self._set_status(f"Video saved to {path}")
                
            except requests.RequestException as exc:
                self._set_status(f"Video download failed: {exc}")
            except OSError as exc:
                self._set_status(f"Failed to save video: {exc}")

        threading.Thread(target=download_worker, daemon=True).start()


def main() -> None:
    root = tk.Tk()
    PexelsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
