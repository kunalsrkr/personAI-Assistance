"""Move a file between this computer and the phone on the same Wi-Fi.

Computer files are read from the folders the app already searches.
Phone uploads land in the Desktop Asteria folder.
Secret names and hidden credential folders are not listed or sent.
"""

from __future__ import annotations

import asyncio
import mimetypes
import re
import struct
import zlib
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from api.playback import session_file, start_phone_stream
from core.config import settings
from servers.file_server import SKIP_DIRS, find_by_name
from servers.workspace import search_roots

router = APIRouter(prefix="/api/v1/funnel", tags=["funnel"])

MAX_BYTES = 16 * 1024 * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass", ".ssa", ".sub", ".idx"}
SECRET_NAMES = {
    ".env",
    ".netrc",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "ntuser.dat",
    "ntuser.dat.log",
}
SECRET_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".kdbx", ".blf", ".regtrans-ms"}
HIDDEN_DIRS = SKIP_DIRS | {
    ".ssh",
    ".gmail-mcp",
    ".linkedin-mcp",
    ".aws",
    ".gnupg",
    ".azure",
    ".kube",
    ".docker",
    "cookies",
    "local settings",
    "my documents",
    "nethood",
    "printhood",
    "recent",
    "sendto",
    "start menu",
    "templates",
    "application data",
}


def funnel_dir() -> Path:
    path = Path(settings.funnel_root) if settings.funnel_root else Path.home() / "Desktop" / "Asteria"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _roots() -> list[Path]:
    return search_roots()


def _hidden(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith(".") or name.startswith("ntuser") or name in HIDDEN_DIRS or name in SECRET_NAMES:
        return True
    return Path(name).suffix.lower() in SECRET_SUFFIXES


def _inside(root_id: int, relative: str) -> Path:
    roots = _roots()
    if root_id < 0 or root_id >= len(roots):
        raise HTTPException(status_code=404, detail="That computer folder is not available.")
    root = roots[root_id]
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=403, detail="That path is outside this computer.")
    return candidate


def _place(path: Path) -> tuple[int, str] | None:
    resolved = path.resolve()
    for index, root in enumerate(_roots()):
        if resolved.is_relative_to(root):
            return index, resolved.relative_to(root).as_posix()
    return None


def _safe_name(raw: str) -> str:
    name = Path(raw or "upload").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:120]
    if not cleaned or _hidden(Path(cleaned)):
        raise HTTPException(status_code=400, detail="That file name cannot be sent.")
    return cleaned


@router.get("/roots")
async def roots() -> dict:
    items = []
    for index, root in enumerate(_roots()):
        label = "This computer" if root.name == "host-home" or index == 0 else root.name
        items.append({"id": index, "label": label})
    return {"roots": items, "inbox": "Desktop/Asteria"}


@router.get("/browse")
async def browse(root: int = 0, path: str = "") -> dict:
    directory = _inside(root, path)
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail="That folder was not found.")
    entries = []
    try:
        children = sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError as exc:
        raise HTTPException(status_code=403, detail="That folder cannot be opened.") from exc
    for child in children:
        if _hidden(child):
            continue
        try:
            info = child.stat()
        except OSError:
            continue
        movie, subtitles = _movie_marks(child) if child.is_dir() else (False, 0)
        entries.append(
            {
                "name": child.name,
                "kind": "dir" if child.is_dir() else "file",
                "group": _group(child),
                "bytes": info.st_size if child.is_file() else 0,
                "modified": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                "path": child.relative_to(_roots()[root]).as_posix(),
                "movie": movie,
                "subtitles": subtitles,
            }
        )
        if len(entries) >= 300:
            break
    parent = str(Path(path).parent.as_posix()) if path else ""
    if parent == ".":
        parent = ""
    return {"root": root, "path": path, "parent": parent, "entries": entries}


@router.get("/search")
async def search(q: str) -> dict:
    terms = [part for part in re.findall(r"[a-z0-9]+", q.lower()) if len(part) >= 2][:4]
    if not terms:
        return {"results": []}
    found = []
    matches = await asyncio.to_thread(find_by_name, terms, 12)
    for item in matches:
        placed = _place(Path(item["path"]))
        if placed is None or _hidden(Path(item["path"])):
            continue
        root_id, relative = placed
        found.append({"root": root_id, "path": relative, "name": item["name"], "type": item["type"]})
    return {"results": found}


_MEDIA = {
    ".mkv": "video/x-matroska",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@router.get("/play")
async def play(root: int, path: str) -> FileResponse:
    target = _inside(root, path)
    if _hidden(target) or not target.is_file():
        raise HTTPException(status_code=404, detail="That file cannot be played.")
    if target.stat().st_size > MAX_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 16 GB.")
    media = _MEDIA.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media, filename=target.name, content_disposition_type="inline")


@router.post("/play/session")
async def play_session(root: int, path: str) -> dict:
    target = _inside(root, path)
    if _hidden(target) or not target.is_file():
        raise HTTPException(status_code=404, detail="That file cannot be played.")
    if target.stat().st_size > MAX_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 16 GB.")
    try:
        return await start_phone_stream(target)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:300]) from exc


@router.get("/play/session/{session}/{name}")
async def play_session_file(session: str, name: str) -> FileResponse:
    try:
        target = session_file(session, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="That part of the movie is not ready.") from None
    if name.endswith(".m3u8"):
        media = "application/vnd.apple.mpegurl"
    elif name.endswith(".ts"):
        media = "video/mp2t"
    elif name.endswith(".m4s") or name.endswith(".mp4"):
        media = "video/mp4"
    else:
        media = "application/octet-stream"
    return FileResponse(target, media_type=media, content_disposition_type="inline", headers={"Cache-Control": "no-cache"})


@router.get("/file")
async def send_to_phone(root: int, path: str) -> FileResponse:
    target = _inside(root, path)
    if _hidden(target) or not target.is_file():
        raise HTTPException(status_code=404, detail="That file cannot be sent.")
    if target.stat().st_size > MAX_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 16 GB.")
    return FileResponse(target, filename=target.name)


@router.get("/folder")
async def send_folder(root: int, path: str) -> StreamingResponse:
    directory = _inside(root, path)
    if not directory.is_dir() or _hidden(directory):
        raise HTTPException(status_code=404, detail="That folder cannot be sent.")
    members = _folder_members(directory)
    if not members:
        raise HTTPException(status_code=404, detail="That folder has no files to send.")
    total = sum(item.stat().st_size for _name, item in members)
    if total > MAX_BYTES:
        raise HTTPException(status_code=413, detail="That folder is larger than 16 GB.")
    filename = f"{directory.name}.zip"
    return StreamingResponse(
        iterate_in_threadpool(_zip_chunks(members)),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/inbox")
async def inbox() -> dict:
    folder = funnel_dir()
    files = []
    for path in sorted(folder.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_file() and not _hidden(path):
            files.append({"name": path.name, "bytes": path.stat().st_size})
    return {"folder": "Desktop/Asteria", "files": files}


@router.post("/inbox")
async def send_to_computer(file: UploadFile = File(...)) -> dict:
    name = _safe_name(file.filename or "upload")
    folder = funnel_dir()
    dest = folder / name
    stem, suffix = dest.stem, dest.suffix
    count = 1
    while dest.exists():
        dest = folder / f"{stem}-{count}{suffix}"
        count += 1
    total = 0
    try:
        with dest.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(status_code=413, detail="That file is larger than 16 GB.")
                handle.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    return {"name": dest.name, "bytes": total, "folder": "Desktop/Asteria"}


@router.get("/inbox/{name}")
async def open_inbox(name: str) -> FileResponse:
    cleaned = _safe_name(name)
    target = (funnel_dir() / cleaned).resolve()
    if not target.is_relative_to(funnel_dir()) or not target.is_file():
        raise HTTPException(status_code=404, detail="That file is not in the funnel folder.")
    return FileResponse(target, filename=target.name)


def _group(path: Path) -> str:
    if path.is_dir():
        return "folder"
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in SUBTITLE_SUFFIXES:
        return "subtitle"
    if suffix in {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}:
        return "audio"
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}:
        return "image"
    return "file"


def _movie_marks(folder: Path) -> tuple[bool, int]:
    movie = False
    subtitles = 0
    try:
        children = list(folder.iterdir())
    except OSError:
        return False, 0
    for child in children[:80]:
        if not child.is_file() or _hidden(child):
            continue
        suffix = child.suffix.lower()
        if suffix in VIDEO_SUFFIXES:
            movie = True
        elif suffix in SUBTITLE_SUFFIXES:
            subtitles += 1
    return movie, subtitles


def _folder_members(folder: Path) -> list[tuple[str, Path]]:
    members: list[tuple[str, Path]] = []

    def walk(current: Path, prefix: str, depth: int) -> None:
        if depth > 2 or len(members) >= 200:
            return
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            return
        for child in children:
            if _hidden(child):
                continue
            name = child.name if not prefix else f"{prefix}/{child.name}"
            if child.is_dir():
                walk(child, name, depth + 1)
                continue
            if child.is_file():
                members.append((name, child))

    walk(folder, "", 0)
    return members


def _zip_chunks(members: list[tuple[str, Path]]) -> Iterator[bytes]:
    """Stream an uncompressed zip so a movie and its subtitles copy without a second full file on disk."""
    central: list[bytes] = []
    offset = 0
    for name, path in members:
        encoded = name.encode("utf-8")
        local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 45, 0x0808, 0, 0, 0, 0, 0, 0, len(encoded), 0)
        yield local + encoded
        crc = 0
        size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                crc = zlib.crc32(chunk, crc) & 0xFFFFFFFF
                size += len(chunk)
                yield chunk
        yield struct.pack("<IIQQ", 0x08074B50, crc, size, size)
        extra = struct.pack("<HHQQQ", 0x0001, 24, size, size, offset)
        header = struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            45,
            45,
            0x0808,
            0,
            0,
            0,
            crc,
            0xFFFFFFFF,
            0xFFFFFFFF,
            len(encoded),
            len(extra),
            0,
            0,
            0,
            0,
            0xFFFFFFFF,
        )
        central.append(header + encoded + extra)
        offset += 30 + len(encoded) + size + 24
    central_blob = b"".join(central)
    central_offset = offset
    yield central_blob
    zip64 = struct.pack(
        "<IQHHIIQQQQ",
        0x06064B50,
        44,
        45,
        45,
        0,
        0,
        len(members),
        len(members),
        len(central_blob),
        central_offset,
    )
    yield zip64
    yield struct.pack("<IIQI", 0x07064B50, 0, central_offset + len(central_blob), 1)
    yield struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
