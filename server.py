"""
El Descargador Pro — Web Backend API
Powered by FastAPI + yt-dlp

This server:
1. Serves the static frontend files
2. Exposes REST endpoints for metadata extraction and downloads
3. Manages download state and progress via in-memory store
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

import yt_dlp

# ── Configuration ────────────────────────────────────────────

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/tmp/downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# How long to keep completed downloads before cleanup (seconds)
FILE_TTL = int(os.environ.get("FILE_TTL", "600"))  # 10 minutes

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("descargador-api")

# ── FastAPI App ──────────────────────────────────────────────

app = FastAPI(
    title="El Descargador Pro API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory Download Store ─────────────────────────────────

downloads: dict[str, dict[str, Any]] = {}
downloads_lock = threading.Lock()


# ── Request / Response Models ────────────────────────────────

class MetadataRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"   # "mp4" or "mp3"
    quality: int = 1080    # Pixel height for video, kbps for audio


# ── Error Translation ────────────────────────────────────────

_ERROR_KEYWORDS: list[tuple[str, str]] = [
    ("Private video", "El contenido es privado y no se puede acceder."),
    ("Video unavailable", "El contenido no está disponible."),
    ("bot", "El sitio detectó un acceso automatizado. Intentá de nuevo más tarde."),
    ("Sign in", "Se requiere iniciar sesión para acceder a este contenido."),
    ("cookies", "Se requieren cookies para acceder a este contenido."),
    ("Geo-restricted", "El contenido no está disponible en tu región."),
    ("HTTP Error 403", "Acceso denegado al contenido (HTTP 403)."),
    ("HTTP Error 404", "El contenido no fue encontrado (HTTP 404)."),
    ("Unable to download", "No se pudo descargar el contenido."),
    ("urlopen error", "Error de red. Verificá tu conexión a Internet."),
    ("timed out", "La conexión expiró. Intentá de nuevo."),
    ("No video formats found", "No se encontraron formatos de video disponibles."),
    ("Requested format is not available", "El formato solicitado no está disponible."),
    ("Unsupported URL", "La URL proporcionada no es compatible."),
    ("age-restricted", "Este video tiene restricción de edad. YouTube requiere iniciar sesión para acceder a él."),
]


def _translate_error(exc: Exception) -> str:
    msg = str(exc).lower()
    for keyword, friendly in _ERROR_KEYWORDS:
        if keyword.lower() in msg:
            return friendly
    return f"Ocurrió un error inesperado al procesar el video: {msg[:100]}"


# ── Helper: Clean YouTube Playlist Params ────────────────────

def _strip_playlist(url: str) -> str:
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    try:
        parsed = urlparse(url)
        if parsed.netloc in ("www.youtube.com", "youtube.com", "m.youtube.com") and parsed.path == "/watch":
            params = parse_qs(parsed.query, keep_blank_values=True)
            if "v" in params and "list" in params:
                return urlunparse(parsed._replace(query=urlencode({"v": params["v"][0]})))
    except Exception:
        pass
    return url


# ══════════════════════════════════════════════════════════════
#  APP STARTUP (FFmpeg Path)
# ══════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    # Asegurarnos que el binario de FFmpeg esté en el PATH de Render
    ffmpeg_bin = Path(__file__).parent / "bin"
    if ffmpeg_bin.exists():
        os.environ["PATH"] = f"{ffmpeg_bin}{os.pathsep}{os.environ.get('PATH', '')}"
        log.info("FFmpeg bin directory added to PATH: %s", ffmpeg_bin)


# ══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.post("/api/metadata")
async def extract_metadata(req: MetadataRequest):
    """Extract video/audio metadata without downloading."""
    url = _strip_playlist(req.url)

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": False,
        "noplaylist": True,
        "extractor_args": {"youtube": ["player_client=ios,android,web"]},
    }

    try:
        # Intento 1: Cliente web
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                log.warning("Web client failed: %s. Trying mobile fallback...", e)
                # Intento 2: Fallback a mobile (Android/iOS) que evade mejor los bots
                opts["extractor_args"] = {"youtube": ["player_client=android,ios"]}
                with yt_dlp.YoutubeDL(opts) as ydl_mobile:
                    info = ydl_mobile.extract_info(url, download=False)

            if info is None:
                raise HTTPException(status_code=400, detail="No se obtuvo información del contenido.")

        duration = float(info.get("duration") or 0)
        return {
            "title": info.get("title", "Sin título"),
            "thumbnail_url": info.get("thumbnail", ""),
            "duration_seconds": duration,
            "extractor": info.get("extractor", info.get("extractor_key", "")),
            "webpage_url": info.get("webpage_url", ""),
        }

    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=400, detail=_translate_error(exc))
    except Exception as exc:
        log.error("Metadata error: %s", exc)
        raise HTTPException(status_code=500, detail=_translate_error(exc))


@app.post("/api/download")
async def start_download(req: DownloadRequest):
    """Start an async download and return a download_id for progress tracking."""
    download_id = str(uuid.uuid4())

    with downloads_lock:
        downloads[download_id] = {
            "state": "starting",
            "percent": 0,
            "speed": "—",
            "eta": "—",
            "status_text": "Preparando descarga...",
            "error": None,
            "file_path": None,
            "filename": None,
            "created_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_download,
        args=(download_id, req.url, req.format, req.quality),
        daemon=True,
    )
    thread.start()

    return {"download_id": download_id}


@app.get("/api/progress/{download_id}")
async def get_progress(download_id: str):
    """Poll download progress."""
    with downloads_lock:
        info = downloads.get(download_id)

    if not info:
        raise HTTPException(status_code=404, detail="Download not found.")

    return {
        "state": info["state"],
        "percent": info["percent"],
        "speed": info["speed"],
        "eta": info["eta"],
        "status_text": info["status_text"],
        "error": info["error"],
    }


@app.get("/api/file/{download_id}")
async def get_file(download_id: str):
    """Serve the completed download file."""
    with downloads_lock:
        info = downloads.get(download_id)

    if not info:
        raise HTTPException(status_code=404, detail="Download not found.")

    if info["state"] != "complete" or not info["file_path"]:
        raise HTTPException(status_code=400, detail="Download not ready yet.")

    file_path = info["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on server.")

    filename = info.get("filename") or os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


# ── Background Download Worker ───────────────────────────────

def _run_download(download_id: str, url: str, fmt: str, quality: int):
    """Execute a download in a background thread."""
    url = _strip_playlist(url)

    # Build unique output directory per download
    dl_dir = DOWNLOAD_DIR / download_id
    dl_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(dl_dir / "%(title)s.%(ext)s")

    opts: dict[str, Any] = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "overwrites": True,
        "noplaylist": True,
        "windowsfilenames": True,
        "nopart": True,
        "extractor_args": {"youtube": ["player_client=ios,android,web"]},
    }

    # Format selection
    if fmt == "mp4":
        opts["format"] = (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}]/"
            f"best"
        )
        opts["merge_output_format"] = "mp4"
    else:  # mp3
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(quality),
        }]

    final_filepath = ""

    def _progress_hook(d: dict):
        nonlocal final_filepath
        status = d.get("status", "")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total > 0 else 0

            speed_bps = d.get("speed")
            if speed_bps and isinstance(speed_bps, (int, float)) and speed_bps > 0:
                if speed_bps >= 1_048_576:
                    speed_str = f"{speed_bps / 1_048_576:.1f} MB/s"
                elif speed_bps >= 1024:
                    speed_str = f"{speed_bps / 1024:.0f} KB/s"
                else:
                    speed_str = f"{speed_bps:.0f} B/s"
            else:
                speed_str = "—"

            eta_sec = d.get("eta")
            if eta_sec and isinstance(eta_sec, (int, float)):
                m, s = divmod(int(eta_sec), 60)
                eta_str = f"{m}:{s:02d}"
            else:
                eta_str = "—"

            with downloads_lock:
                dl = downloads.get(download_id)
                if dl:
                    dl["state"] = "downloading"
                    dl["percent"] = round(pct, 1)
                    dl["speed"] = speed_str
                    dl["eta"] = eta_str
                    dl["status_text"] = "Descargando..."

        elif status == "finished":
            final_filepath = d.get("filename", "")
            with downloads_lock:
                dl = downloads.get(download_id)
                if dl:
                    dl["percent"] = 100
                    dl["status_text"] = "Postprocesando..."
                    dl["speed"] = "—"
                    dl["eta"] = "—"

    opts["progress_hooks"] = [_progress_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # Find the output file
        actual_file = final_filepath
        if not actual_file or not os.path.exists(actual_file):
            # Search for any file in the download directory
            ext = "mp3" if fmt == "mp3" else "mp4"
            for f in dl_dir.iterdir():
                if f.suffix.lower() == f".{ext}":
                    actual_file = str(f)
                    break
            else:
                # If no specific ext found, take any file
                files = list(dl_dir.iterdir())
                if files:
                    actual_file = str(files[0])

        with downloads_lock:
            dl = downloads.get(download_id)
            if dl:
                dl["state"] = "complete"
                dl["percent"] = 100
                dl["status_text"] = "¡Completo!"
                dl["file_path"] = actual_file
                dl["filename"] = os.path.basename(actual_file) if actual_file else "download"

        log.info("Download complete: %s -> %s", download_id, actual_file)

    except Exception as exc:
        friendly = _translate_error(exc)
        log.error("Download %s failed: %s", download_id, exc)
        with downloads_lock:
            dl = downloads.get(download_id)
            if dl:
                dl["state"] = "error"
                dl["error"] = friendly
                dl["status_text"] = "Error"


# ── Periodic Cleanup ─────────────────────────────────────────

def _cleanup_loop():
    """Remove old downloads every 60 seconds."""
    import shutil
    while True:
        time.sleep(60)
        now = time.time()
        to_remove = []
        with downloads_lock:
            for did, info in downloads.items():
                if now - info["created_at"] > FILE_TTL:
                    to_remove.append(did)
            for did in to_remove:
                info = downloads.pop(did, None)
                if info and info.get("file_path"):
                    dl_dir = DOWNLOAD_DIR / did
                    if dl_dir.exists():
                        shutil.rmtree(dl_dir, ignore_errors=True)
                        log.info("Cleaned up download: %s", did)

_cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
_cleanup_thread.start()


# ── Serve Frontend ───────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
