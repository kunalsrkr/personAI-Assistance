"""File MCP server. Finds files by name, then leaves reading to a typed server."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from servers.file_types import file_kind, type_label
from servers.workspace import safe_path, search_roots, workspace_root

NAME = "file"
TOOLS = ["file.list", "file.search", "file.read", "file.find_by_name"]
SKIP_DIRS = {
    "appdata",
    "application data",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".npm",
    ".cache",
    "cache",
    "temp",
    "tmp",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
    "site-packages",
}
STOP_WORDS = {
    "what",
    "which",
    "where",
    "when",
    "have",
    "does",
    "this",
    "that",
    "with",
    "from",
    "your",
    "mine",
    "system",
    "computer",
    "machine",
    "laptop",
    "file",
    "files",
    "document",
    "documents",
    "about",
    "please",
    "show",
    "find",
    "list",
    "read",
    "there",
    "their",
    "them",
    "into",
    "need",
    "want",
}


def list_files() -> list[dict]:
    root = workspace_root()
    if not root.exists():
        return []
    found = []
    for path in root.rglob("*"):
        if path.is_file() and len(found) < 100:
            found.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size})
    return found


def search_files(query: str) -> list[dict]:
    needle = query.lower()
    matches = []
    for item in list_files():
        path = safe_path(item["path"])
        name_hit = needle in item["path"].lower()
        text_hit = False
        if path.suffix.lower() in {".txt", ".md", ".csv"} and path.stat().st_size < 200_000:
            text_hit = needle in path.read_text(encoding="utf-8", errors="ignore").lower()
        if name_hit or text_hit:
            matches.append(item)
    return matches[:20]


def filename_terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    terms = []
    for word in words:
        if len(word) < 4 or word in STOP_WORDS:
            continue
        if word not in terms:
            terms.append(word)
    return terms[:6]


VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MEDIA_WORDS = {
    "video": {"movie", "movies", "film", "films", "video", "videos"},
    "audio": {"song", "songs", "music", "audio", "track", "tracks"},
    "image": {"image", "images", "photo", "photos", "picture", "pictures"},
}
ASK_WORDS = {"list", "lists", "show", "all", "every", "find", "play", "watch", "search", "open", "give", "my"}
MOVIE_STOP = STOP_WORDS | {
    "movie",
    "movies",
    "film",
    "films",
    "video",
    "videos",
    "play",
    "watch",
    "find",
    "search",
    "named",
    "called",
    "some",
    "open",
    "list",
    "lists",
    "show",
    "all",
    "every",
    "give",
    "display",
    "song",
    "songs",
    "music",
    "audio",
    "track",
    "tracks",
    "image",
    "images",
    "photo",
    "photos",
    "picture",
    "pictures",
}


def movie_terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    terms = []
    for word in words:
        if len(word) < 3 or word in MOVIE_STOP or word in terms:
            continue
        terms.append(word)
    return terms[:6]


def _words(question: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", question.lower()))


def wants_movie(question: str) -> bool:
    return media_request(question) == "video"


def media_request(question: str) -> str:
    """video, audio, or image when the question asks for files on this computer."""
    words = _words(question)
    blocked = {
        "weather",
        "forecast",
        "gmail",
        "imdb",
        "rating",
        "release",
        "latest",
        "news",
        "pdf",
        "mail",
        "email",
        "contract",
        "invoice",
        "note",
        "arxiv",
        "paper",
        "papers",
        "citation",
        "citations",
        "linkedin",
        "abstract",
    }
    if words & blocked:
        return ""
    for kind, vocab in MEDIA_WORDS.items():
        if words & vocab and (words & ASK_WORDS or len(words) <= 6):
            return kind
    if "find" in words and movie_terms(question) and not (words & {"file", "files", "folder", "document"}):
        return "video"
    return ""


def media_terms(question: str) -> list[str]:
    return movie_terms(question)


def find_media(kind: str, terms: list[str], limit: int = 80, catalog: bool = False) -> tuple[list[dict], int, bool]:
    suffixes = {"video": VIDEO_SUFFIXES, "audio": AUDIO_SUFFIXES, "image": IMAGE_SUFFIXES}.get(kind, VIDEO_SUFFIXES)
    if catalog and kind == "video":
        minimum = 8 * 1024 * 1024
    elif catalog and kind == "audio":
        minimum = 100 * 1024
    elif catalog and kind == "image":
        minimum = 30 * 1024
    else:
        minimum = 0
    deadline = time.monotonic() + (45 if catalog else 25)
    scored: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    stopped = False
    for root in search_roots():
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _error: None):
            dirnames[:] = [name for name in dirnames if name.lower() not in SKIP_DIRS and not name.startswith(".")]
            if time.monotonic() > deadline:
                stopped = True
                break
            for filename in filenames:
                suffix = Path(filename).suffix.lower()
                if suffix not in suffixes or filename.startswith("."):
                    continue
                lowered = filename.lower()
                compact = re.sub(r"[^a-z0-9]", "", lowered)
                if terms and not all(term in lowered or term in compact for term in terms):
                    continue
                full = str(Path(dirpath) / filename)
                if full in seen:
                    continue
                seen.add(full)
                try:
                    size = Path(full).stat().st_size
                except OSError:
                    size = 0
                if size < minimum:
                    continue
                scored.append((lowered, size, full))
        if stopped:
            break
    if catalog:
        scored.sort(key=lambda item: item[0])
    else:
        scored.sort(key=lambda item: (-item[1], item[0]))
    total = len(scored)
    found = []
    for _name, size, full in scored[:limit]:
        path = Path(full)
        found.append({"path": str(path), "name": path.name, "bytes": size})
    return found, total, stopped or total > limit


def wants_local_files(question: str) -> bool:
    text = question.lower()
    phrases = (
        "my system",
        "in my system",
        "on my system",
        "my computer",
        "on my computer",
        "my pc",
        "my machine",
        "my laptop",
        "my files",
        "in my files",
        "local file",
        "on my disk",
    )
    return any(phrase in text for phrase in phrases)


def find_by_name(terms: list[str], limit: int = 8) -> list[dict]:
    if not terms:
        return []
    deadline = time.monotonic() + 25
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for root in search_roots():
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _error: None):
            dirnames[:] = [name for name in dirnames if name.lower() not in SKIP_DIRS and not name.startswith(".")]
            if time.monotonic() > deadline:
                break
            for filename in filenames:
                lowered = filename.lower()
                compact = re.sub(r"[^a-z0-9]", "", lowered)
                hits = sum(1 for term in terms if term in lowered or term in compact)
                if not hits:
                    continue
                anchor = max(terms, key=len)
                if anchor in lowered or anchor in compact:
                    hits += 5
                full = str(Path(dirpath) / filename)
                if full in seen:
                    continue
                seen.add(full)
                kind = file_kind(Path(full))
                kind_rank = 0 if kind in {"document", "spreadsheet"} else 1
                scored.append((hits, kind_rank, full))
    scored.sort(key=lambda item: (-item[0], item[1], item[2].lower()))
    found = []
    seen_names: set[str] = set()
    for _hits, _rank, full in scored:
        path = Path(full)
        if path.name.lower() in seen_names:
            continue
        seen_names.add(path.name.lower())
        if len(found) >= limit:
            break
        found.append(
            {
                "path": str(path),
                "name": path.name,
                "kind": file_kind(path),
                "type": type_label(path),
            }
        )
    return found


def read_file(relative_path: str) -> str:
    path = safe_path(relative_path)
    if not path.is_file():
        raise FileNotFoundError(relative_path)
    if path.stat().st_size > 200_000:
        raise ValueError("File is too large to read in one call.")
    return path.read_text(encoding="utf-8", errors="ignore")
