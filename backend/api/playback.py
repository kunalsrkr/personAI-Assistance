"""Stream a movie the phone browser cannot open directly.

MKV and AVI stay on disk. ffmpeg only repackages them into a short-segment
stream. The picture is copied when the phone can already decode it.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path("/tmp/asteria-play")
_current: dict | None = None


async def _probe(path: Path) -> tuple[str, str]:
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    output, _ = await process.communicate()
    video = ""
    audio = ""
    try:
        payload = json.loads(output.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "video" and not video:
            video = str(stream.get("codec_name") or "")
        elif stream.get("codec_type") == "audio" and not audio:
            audio = str(stream.get("codec_name") or "")
    return video, audio


def _stop_current() -> None:
    global _current
    if _current is None:
        return
    process = _current["process"]
    if process.returncode is None:
        process.kill()
    _current = None


async def start_phone_stream(source: Path) -> dict:
    """Start a stream and return once the first piece is ready to play."""
    global _current
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg is not available")
    video, audio = await _probe(source)
    _stop_current()
    session = uuid.uuid4().hex
    folder = ROOT / session
    folder.mkdir(parents=True, exist_ok=True)
    copy_picture = video in {"h264", "avc", "hevc", "h265"}
    hevc = video in {"hevc", "h265"}
    segment = "fmp4" if hevc else "mpegts"
    extension = "m4s" if hevc else "ts"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-sn",
        "-dn",
    ]
    if hevc:
        command += ["-c:v", "copy", "-tag:v", "hvc1"]
        command += ["-c:a", "copy"] if audio == "aac" else ["-c:a", "aac", "-ac", "2", "-b:a", "192k"]
    elif copy_picture:
        command += ["-c:v", "copy", "-bsf:v", "h264_mp4toannexb"]
        command += ["-c:a", "copy"] if audio == "aac" else ["-c:a", "aac", "-ac", "2", "-b:a", "192k"]
    else:
        command += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "160k",
        ]
    command += [
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_list_size",
        "0",
        "-hls_playlist_type",
        "event",
        "-hls_flags",
        "independent_segments+append_list",
        "-hls_segment_type",
        segment,
        "-hls_segment_filename",
        str(folder / f"seg%05d.{extension}"),
        str(folder / "index.m3u8"),
    ]
    log_path = folder / "ffmpeg.log"
    log_handle = log_path.open("wb")
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=log_handle,
    )
    _current = {"id": session, "process": process, "folder": folder, "log": log_handle}
    playlist = folder / "index.m3u8"
    for _ in range(90):
        if playlist.exists() and (any(folder.glob("seg*.ts")) or any(folder.glob("seg*.m4s"))):
            return {
                "id": session,
                "playlist": f"/api/v1/funnel/play/session/{session}/index.m3u8",
                "mode": "copy" if copy_picture else "convert",
            }
        if process.returncode is not None:
            detail = log_path.read_text(errors="replace")[-400:] if log_path.exists() else ""
            raise RuntimeError(detail or "The movie stream stopped before it started.")
        await asyncio.sleep(0.5)
    raise RuntimeError("The movie is taking too long to prepare.")


def session_file(session: str, name: str) -> Path:
    if not session.isalnum() or not name or "/" in name or "\\" in name or name.startswith("."):
        raise FileNotFoundError(name)
    path = (ROOT / session / name).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise FileNotFoundError(name)
    return path
