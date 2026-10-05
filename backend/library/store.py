"""Saves uploads and recordings with metadata, embeddings, and linked transcripts."""

from __future__ import annotations

import json
import re
import struct
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.config import settings
from library.embed import cosine, embed_text, embedder_name

_LOCK = threading.Lock()
MAX_BYTES = 100 * 1024 * 1024
_STOP = {"what", "when", "where", "which", "this", "that", "with", "from", "have", "your", "about", "please", "show"}


def library_root() -> Path:
    path = Path(settings.library_root) if settings.library_root else Path(__file__).resolve().parents[2] / "data" / "library"
    path.mkdir(parents=True, exist_ok=True)
    (path / "items").mkdir(exist_ok=True)
    return path


def _index_path() -> Path:
    return library_root() / "index.json"


def _load() -> dict:
    path = _index_path()
    if not path.is_file():
        name, _model = embedder_name()
        return {"embedder": name, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(index: dict) -> None:
    _index_path().write_text(json.dumps(index, indent=2), encoding="utf-8")


def list_items() -> list[dict]:
    with _LOCK:
        items = _load()["items"]
    return sorted(items, key=lambda item: item["created_at"], reverse=True)


def get_item(item_id: str) -> dict | None:
    return next((item for item in list_items() if item["id"] == item_id), None)


def item_file(item: dict) -> Path:
    relative = item.get("relative_path")
    if relative:
        return library_root() / relative
    return library_root() / "items" / item["id"] / item["stored_name"]


def transcript_for(item_id: str) -> dict | None:
    item = get_item(item_id)
    if item and item.get("transcript_path"):
        path = library_root() / item["transcript_path"]
    else:
        path = library_root() / "items" / item_id / "transcript.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_upload(
    *,
    filename: str,
    content: bytes,
    mime: str,
    kind: str,
    source: str,
    note: str = "",
    transcript: str = "",
) -> dict:
    if len(content) > MAX_BYTES:
        raise ValueError("File is larger than 100 MB.")
    if kind not in {"file", "image", "audio", "video"}:
        raise ValueError("Unsupported kind.")
    item_id = uuid4().hex
    suffix = Path(filename).suffix.lower()[:12] or _suffix_for(mime, kind)
    stamp = datetime.now(timezone.utc)
    place = _place_slug(note, content)
    stem = _slug(Path(filename).stem) or "file"
    stored_name = f"{place}-{stamp:%Y%m%d-%H%M}-{stem}{suffix}"
    bucket = _bucket(kind, suffix)
    relative = Path(bucket) / f"{stamp:%Y}" / f"{stamp:%m}" / f"{stamp:%d}" / stored_name
    target = library_root() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 1
    while target.exists():
        stored_name = f"{place}-{stamp:%Y%m%d-%H%M}-{stem}-{count}{suffix}"
        relative = Path(bucket) / f"{stamp:%Y}" / f"{stamp:%m}" / f"{stamp:%d}" / stored_name
        target = library_root() / relative
        count += 1
    target.write_bytes(content)
    extracted = _extract_text(target, suffix)
    transcript_id = ""
    transcript_path = ""
    transcript_text = transcript.strip()
    if kind in {"audio", "video"}:
        transcript_id = uuid4().hex
        record = {
            "transcript_id": transcript_id,
            "media_id": item_id,
            "kind": kind,
            "text": transcript_text,
            "method": "browser-speech" if transcript_text else "pending",
            "created_at": _now(),
        }
        transcript_file = target.with_name(f"{target.stem}.transcript.json")
        transcript_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        transcript_path = transcript_file.relative_to(library_root()).as_posix()
    searchable = "\n".join(part for part in (filename, note, extracted, transcript_text) if part.strip())
    with _LOCK:
        index = _load()
        vector = embed_text(searchable or filename, index["embedder"])
        item = {
            "id": item_id,
            "kind": kind,
            "original_name": Path(filename).name,
            "stored_name": stored_name,
            "relative_path": relative.as_posix(),
            "transcript_path": transcript_path,
            "mime": mime or "application/octet-stream",
            "bytes": len(content),
            "source": source,
            "note": note.strip(),
            "text": searchable[:8000],
            "transcript_id": transcript_id,
            "embedding": vector,
            "created_at": _now(),
        }
        index["items"].append(item)
        _save(index)
    public = dict(item)
    public.pop("embedding", None)
    return public


def search(question: str, limit: int = 4) -> list[dict]:
    terms = [word for word in re.findall(r"[a-z0-9]{3,}", question.lower()) if word not in _STOP]
    with _LOCK:
        index = _load()
        items = index["items"]
        query_vector = embed_text(question, index["embedder"])
    ranked = []
    for item in items:
        vector_score = cosine(query_vector, item.get("embedding") or [])
        hay = f"{item.get('original_name', '')} {item.get('text', '')}".lower()
        keyword_score = (sum(1 for term in terms if term in hay) / len(terms)) if terms else 0
        score = max(vector_score, keyword_score)
        if score < 0.34 and keyword_score < 0.5:
            continue
        ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    found = []
    for score, item in ranked[:limit]:
        transcript = transcript_for(item["id"])
        excerpt = (transcript or {}).get("text") or item.get("text") or item.get("note") or ""
        found.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "title": item["original_name"],
                "excerpt": excerpt[:400],
                "score": round(score, 3),
                "transcript_id": item.get("transcript_id") or "",
            }
        )
    return found


def _extract_text(path: Path, suffix: str) -> str:
    try:
        if suffix in {".txt", ".md", ".csv"}:
            return path.read_text(encoding="utf-8", errors="ignore")[:8000]
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages[:6])[:8000]
        if suffix == ".docx":
            from docx import Document

            document = Document(str(path))
            return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())[:8000]
    except (OSError, ValueError, ImportError):
        return ""
    return ""


def _bucket(kind: str, suffix: str) -> str:
    if kind == "video" or suffix in {".mp4", ".mkv", ".mov", ".avi", ".m4v"}:
        return "video"
    if kind == "audio" or suffix in {".mp3", ".wav", ".m4a", ".ogg", ".aac"}:
        return "audio"
    if kind == "image" or suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}:
        return "image"
    if suffix in {".pdf", ".docx", ".txt", ".md", ".rtf"}:
        return "document"
    if suffix in {".csv", ".xlsx", ".xls"}:
        return "spreadsheet"
    return "other"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _place_slug(note: str, content: bytes) -> str:
    if note.strip():
        return _slug(note) or "unplaced"
    gps = _jpeg_place(content)
    return gps or "unplaced"


def _jpeg_place(content: bytes) -> str:
    if not content.startswith(b"\xff\xd8"):
        return ""
    try:
        lat, lon = _jpeg_gps(content)
    except (ValueError, IndexError, struct.error):
        return ""
    if lat is None:
        return ""
    return f"lat{lat:.2f}-lon{lon:.2f}".replace("-", "m").replace(".", "p").replace("m", "-")


def _jpeg_gps(content: bytes) -> tuple[float | None, float | None]:
    import struct

    offset = 2
    while offset + 4 < len(content):
        if content[offset] != 0xFF:
            break
        marker = content[offset + 1]
        if marker == 0xDA:
            break
        size = struct.unpack(">H", content[offset + 2 : offset + 4])[0]
        if marker == 0xE1 and content[offset + 4 : offset + 10] == b"Exif\x00\x00":
            return _exif_gps(content[offset + 10 : offset + 2 + size])
        offset += 2 + size
    return None, None


def _exif_gps(exif: bytes) -> tuple[float | None, float | None]:
    import struct

    endian = "<" if exif[:2] == b"II" else ">"
    ifd = struct.unpack(endian + "I", exif[4:8])[0]
    gps_offset = _ifd_pointer(exif, ifd, endian, 0x8825)
    if gps_offset is None:
        return None, None
    count = struct.unpack(endian + "H", exif[gps_offset : gps_offset + 2])[0]
    lat = lon = None
    lat_ref = lon_ref = ""
    for index in range(count):
        start = gps_offset + 2 + index * 12
        tag, kind, length, value = struct.unpack(endian + "HHII", exif[start : start + 12])
        if tag == 1:
            lat_ref = exif[start + 8 : start + 9].decode("ascii", errors="ignore")
        elif tag == 3:
            lon_ref = exif[start + 8 : start + 9].decode("ascii", errors="ignore")
        elif tag == 2 and kind == 5:
            lat = _rational_degrees(exif, value if length > 1 else start + 8, endian)
        elif tag == 4 and kind == 5:
            lon = _rational_degrees(exif, value if length > 1 else start + 8, endian)
    if lat is None or lon is None:
        return None, None
    if lat_ref == "S":
        lat = -lat
    if lon_ref == "W":
        lon = -lon
    return lat, lon


def _ifd_pointer(exif: bytes, ifd: int, endian: str, wanted: int) -> int | None:
    import struct

    count = struct.unpack(endian + "H", exif[ifd : ifd + 2])[0]
    for index in range(count):
        start = ifd + 2 + index * 12
        tag, _kind, _length, value = struct.unpack(endian + "HHII", exif[start : start + 12])
        if tag == wanted:
            return value
    return None


def _rational_degrees(exif: bytes, offset: int, endian: str) -> float:
    import struct

    values = []
    for index in range(3):
        num, den = struct.unpack(endian + "II", exif[offset + index * 8 : offset + index * 8 + 8])
        values.append(num / den if den else 0)
    return values[0] + values[1] / 60 + values[2] / 3600


def _suffix_for(mime: str, kind: str) -> str:
    if "webm" in mime:
        return ".webm"
    if "jpeg" in mime or kind == "image":
        return ".jpg"
    if kind == "audio":
        return ".webm"
    if kind == "video":
        return ".webm"
    return ".bin"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
