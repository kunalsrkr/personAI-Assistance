"""One local session, many topic threads, each with memory and checkpoints."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.config import settings

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    configured = (settings.sessions_root or "").strip()
    path = Path(configured) if configured else Path("/sessions")
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path("/tmp/asteria-sessions")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _file() -> Path:
    return _root() / "session.json"


def _empty() -> dict:
    return {"id": uuid4().hex, "threads": []}


def _load() -> dict:
    path = _file()
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict) or not isinstance(data.get("threads"), list):
        return _empty()
    return data


def _save(data: dict) -> None:
    path = _file()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _memory(turns: list[dict]) -> str:
    lines = []
    for turn in turns[-8:]:
        role = "Asked" if turn.get("role") == "user" else "Answered"
        text = " ".join(str(turn.get("text") or "").split())[:220]
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)[:1400]


def _public(thread: dict) -> dict:
    return {
        "id": thread["id"],
        "title": thread.get("title") or "New thread",
        "memory": thread.get("memory") or "",
        "turns": thread.get("turns") or [],
        "checkpoints": [
            {"id": item["id"], "label": item.get("label") or "Checkpoint", "at": item.get("at") or ""}
            for item in thread.get("checkpoints") or []
        ],
        "active_checkpoint": thread.get("active_checkpoint") or "",
        "latest_investigation_id": thread.get("latest_investigation_id") or "",
        "updated_at": thread.get("updated_at") or "",
    }


def list_threads() -> list[dict]:
    with _lock:
        data = _load()
    threads = sorted(data["threads"], key=lambda item: item.get("updated_at") or "", reverse=True)
    return [_public(item) for item in threads]


def get_thread(thread_id: str) -> dict | None:
    with _lock:
        data = _load()
    for item in data["threads"]:
        if item["id"] == thread_id:
            return _public(item)
    return None


def open_thread(title: str, thread_id: str = "") -> dict:
    with _lock:
        data = _load()
        if thread_id:
            for item in data["threads"]:
                if item["id"] == thread_id:
                    return _public(item)
        thread = {
            "id": uuid4().hex,
            "title": (title or "New thread").strip()[:80] or "New thread",
            "memory": "",
            "turns": [],
            "checkpoints": [],
            "active_checkpoint": "",
            "latest_investigation_id": "",
            "updated_at": _now(),
        }
        data["threads"].append(thread)
        data["threads"] = data["threads"][-40:]
        _save(data)
        return _public(thread)


def note_investigation(thread_id: str, investigation_id: str) -> None:
    with _lock:
        data = _load()
        for item in data["threads"]:
            if item["id"] == thread_id:
                item["latest_investigation_id"] = investigation_id
                item["updated_at"] = _now()
                _save(data)
                return


def context_for(thread_id: str) -> str:
    with _lock:
        data = _load()
    for item in data["threads"]:
        if item["id"] == thread_id:
            memory = item.get("memory") or ""
            if not memory:
                return ""
            return f"This thread's memory:\n{memory}"
    return ""


def record(thread_id: str, question: str, answer: str, investigation_id: str = "") -> dict | None:
    with _lock:
        data = _load()
        thread = next((item for item in data["threads"] if item["id"] == thread_id), None)
        if thread is None:
            return None
        asked = question.strip()
        replied = " ".join((answer or "").split())
        thread["turns"].append({"role": "user", "text": asked[:2000], "at": _now()})
        thread["turns"].append({"role": "assistant", "text": replied[:4000], "at": _now()})
        thread["turns"] = thread["turns"][-40:]
        if thread.get("title") in {"", "New thread"} or thread["title"] == thread_id:
            thread["title"] = asked[:72] or "New thread"
        thread["memory"] = _memory(thread["turns"])
        checkpoint = {
            "id": uuid4().hex,
            "label": asked[:72] or "Checkpoint",
            "at": _now(),
            "turns": deepcopy(thread["turns"]),
            "memory": thread["memory"],
        }
        thread.setdefault("checkpoints", []).append(checkpoint)
        thread["checkpoints"] = thread["checkpoints"][-20:]
        thread["active_checkpoint"] = checkpoint["id"]
        if investigation_id:
            thread["latest_investigation_id"] = investigation_id
        thread["updated_at"] = _now()
        _save(data)
        return _public(thread)


def restore(thread_id: str, checkpoint_id: str) -> dict | None:
    with _lock:
        data = _load()
        thread = next((item for item in data["threads"] if item["id"] == thread_id), None)
        if thread is None:
            return None
        checkpoint = next((item for item in thread.get("checkpoints") or [] if item["id"] == checkpoint_id), None)
        if checkpoint is None:
            return None
        thread["turns"] = deepcopy(checkpoint.get("turns") or [])
        thread["memory"] = checkpoint.get("memory") or _memory(thread["turns"])
        thread["active_checkpoint"] = checkpoint_id
        thread["updated_at"] = _now()
        _save(data)
        return _public(thread)
