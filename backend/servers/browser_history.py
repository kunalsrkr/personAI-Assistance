"""Local browser history for Ask.

Chrome and Edge keep visits in a SQLite file under the user profile. Chrome
locks that file while it is open, so each sync copies it and reads the copy.
Visits stay on this computer in a capped JSON store. Credential-bearing URLs
are dropped or stripped before they are written.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from urllib.parse import urlencode

from core.config import settings
from mcp.gmail_client import is_gmail_query
from servers.file_server import media_request

logger = logging.getLogger(__name__)

STORE_LIMIT = 4000
FETCH_LIMIT = 5000
ANSWER_LIMIT = 15
REFRESH_SECONDS = 180
_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
_LOCK = threading.Lock()
_OFFSET_RE = re.compile(r"^([+-])(\d{1,2}):(\d{2})$")
_SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "password",
    "passwd",
    "pwd",
    "secret",
    "client_secret",
    "auth",
    "authorization",
    "session",
    "sessionid",
    "sid",
    "jwt",
    "otp",
    "reset_token",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "sig",
    "signature",
    "auth_token",
    "key",
}
_RESET_PATH = (
    "reset-password",
    "resetpassword",
    "reset_password",
    "password-reset",
    "password_reset",
    "forgot-password",
    "forgotpassword",
    "forgot_password",
    "magic-link",
    "one-time-password",
)
_BROWSERS = (
    ("Chrome", "AppData/Local/Google/Chrome/User Data"),
    ("Chrome Beta", "AppData/Local/Google/Chrome Beta/User Data"),
    ("Edge", "AppData/Local/Microsoft/Edge/User Data"),
)
_HISTORY_PHRASES = (
    "browser history",
    "browsing history",
    "chrome history",
    "edge history",
    "search history",
    "my history",
)
_TERM_STOP = {
    "what",
    "which",
    "where",
    "when",
    "have",
    "did",
    "does",
    "this",
    "that",
    "with",
    "from",
    "your",
    "mine",
    "about",
    "please",
    "show",
    "find",
    "list",
    "there",
    "their",
    "them",
    "into",
    "need",
    "want",
    "history",
    "browser",
    "browsing",
    "chrome",
    "edge",
    "visited",
    "visit",
    "visiting",
    "opened",
    "open",
    "sites",
    "site",
    "website",
    "websites",
    "pages",
    "page",
    "tabs",
    "tab",
    "yesterday",
    "today",
    "last",
    "week",
    "night",
    "morning",
    "recent",
    "recently",
    "look",
    "looking",
    "tell",
    "give",
    "some",
    "any",
    "the",
    "and",
    "for",
    "was",
    "were",
    "been",
    "you",
    "ask",
    "questions",
    "question",
    "saved",
    "computer",
    "machine",
}


def wants_browser_history(question: str) -> bool:
    """True when the question is about this computer's saved browsing."""
    text = " ".join(question.lower().split())
    if not text or media_request(question) or is_gmail_query(text):
        return False
    if any(word in text for word in ("weather", "forecast", "temperature", "humidity", "raining")):
        return False
    if "history of" in text or "history about" in text:
        return False
    personal = _mentions_own_history(text)
    if any(phrase in text for phrase in ("latest news", "breaking news", "search the web")) and not personal:
        return False
    if re.search(r"\bnews\b", text) and not personal and "visited" not in text and "browser" not in text:
        return False
    return personal


def search_history(question: str, limit: int = ANSWER_LIMIT) -> tuple[list[dict], int]:
    with _LOCK:
        visits = _load_unlocked()
    stored = len(visits)
    window = _time_window(question)
    terms = _search_terms(question)
    dedupe = not re.search(r"\b(every time|each visit|all visits)\b", question.lower())
    matched: list[dict] = []
    seen: set[str] = set()
    for visit in visits:
        when = _parse_time(visit.get("visited_at", ""))
        if window is not None and (when is None or not (window[0] <= when < window[1])):
            continue
        if terms and not _matches(visit, terms):
            continue
        url = clean_url(str(visit.get("url") or ""))
        if not url:
            continue
        if dedupe:
            if url in seen:
                continue
            seen.add(url)
        safe = dict(visit)
        safe["url"] = url
        matched.append(_source(safe))
        if len(matched) >= limit:
            break
    return matched, stored


def sync_if_online() -> dict:
    with _LOCK:
        existing = _load_unlocked()
    if not machine_online():
        logger.info("browser history sync skipped; machine looks offline")
        return {"online": False, "stored": len(existing), "added": 0, "profiles": []}
    return _sync(existing)


def machine_online() -> bool:
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443)):
        try:
            with socket.create_connection((host, port), timeout=2.5):
                return True
        except OSError:
            continue
    return False


async def history_refresh_loop(interval: int = REFRESH_SECONDS) -> None:
    while True:
        try:
            summary = await asyncio.to_thread(sync_if_online)
            logger.info(
                "browser history sync online=%s stored=%s added=%s",
                summary.get("online"),
                summary.get("stored"),
                summary.get("added"),
            )
        except Exception:
            logger.exception("browser history sync failed")
        await asyncio.sleep(interval)


def _mentions_own_history(text: str) -> bool:
    if any(phrase in text for phrase in _HISTORY_PHRASES):
        return True
    if re.search(r"\b(i|i've|ive)\s+(visited|opened|browsed)\b", text):
        return True
    if re.search(r"\b(did|have|had)\s+i\s+(visit|visited|open|opened|browse|browsed)\b", text):
        return True
    if re.search(
        r"\b(sites?|websites?|web sites?|pages?|tabs?)\b.{0,48}\b(i|i've|ive)\b.{0,32}\b(open|opened|visit|visited|browse|browsed|see|seen)\b",
        text,
    ):
        return True
    if re.search(r"\b(what|which)\s+(sites?|websites?|pages?|tabs?)\b", text) and re.search(
        r"\b(open|opened|visit|visited|browse|browsed|history|been)\b", text
    ):
        return True
    words = set(re.findall(r"[a-z0-9']+", text))
    if words & {"visited", "visiting"} and words & {"i", "i've", "ive", "my", "yesterday", "today"}:
        return True
    if "history" in words and words & {"my", "browser", "browsing", "chrome", "edge", "visited", "yesterday", "today"}:
        return True
    if "history" in words and words <= {
        "history",
        "browser",
        "browsing",
        "chrome",
        "edge",
        "my",
        "the",
        "show",
        "me",
        "please",
        "open",
        "list",
        "a",
        "of",
    }:
        return True
    bare = text.strip(" ?!.")
    return bare in {"history", "my history", "browser history", "browsing history"}


def _sync(existing: list[dict]) -> dict:
    fresh, profiles = _collect()
    with _LOCK:
        current = _load_unlocked() or existing
        merged = _merge(current, fresh)
        _save_unlocked(merged)
    added = max(0, len(merged) - len(existing))
    logger.info("browser history stored=%s profiles=%s", len(merged), ",".join(profiles) or "none")
    return {"online": True, "stored": len(merged), "added": added, "profiles": profiles}


def _collect() -> tuple[list[dict], list[str]]:
    home = Path(settings.host_home or "/host-home")
    found: list[dict] = []
    profiles: list[str] = []
    for browser, relative in _BROWSERS:
        root = home / relative
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for profile_dir in children:
            if not profile_dir.is_dir():
                continue
            database = profile_dir / "History"
            if not database.is_file():
                continue
            label = f"{browser}:{profile_dir.name}"
            try:
                rows = _read_database(browser, profile_dir.name, database)
            except (OSError, sqlite3.Error) as exc:
                logger.warning("browser history unreadable %s (%s)", label, type(exc).__name__)
                continue
            if rows:
                profiles.append(label)
                found.extend(rows)
    return found, profiles


def _copy_file(source: Path, dest: Path) -> None:
    try:
        shutil.copy2(source, dest)
    except OSError:
        with source.open("rb") as incoming, dest.open("wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)


def _copy_and_query(database: Path, sidecars: bool) -> list[tuple]:
    with tempfile.TemporaryDirectory(prefix="asteria-history-") as tmp:
        dest = Path(tmp) / "History"
        _copy_file(database, dest)
        if sidecars:
            for suffix in ("-wal", "-shm"):
                extra = Path(str(database) + suffix)
                try:
                    if extra.is_file():
                        _copy_file(extra, Path(str(dest) + suffix))
                except OSError:
                    continue
        connection = sqlite3.connect(dest)
        try:
            return connection.execute(
                """
                SELECT urls.url, urls.title, urls.visit_count, visits.visit_time
                FROM visits
                JOIN urls ON urls.id = visits.url
                ORDER BY visits.visit_time DESC
                LIMIT ?
                """,
                (FETCH_LIMIT,),
            ).fetchall()
        finally:
            connection.close()


def _read_database(browser: str, profile: str, database: Path) -> list[dict]:
    try:
        rows = _copy_and_query(database, sidecars=True)
    except sqlite3.DatabaseError:
        rows = _copy_and_query(database, sidecars=False)
    visits: list[dict] = []
    for url, title, visit_count, visit_time in rows:
        when = _from_chrome(visit_time)
        cleaned = clean_url(str(url or ""))
        if when is None or not cleaned:
            continue
        visits.append(
            {
                "url": cleaned,
                "title": _clean_title(str(title or ""), cleaned),
                "visited_at": when.isoformat(timespec="seconds"),
                "visit_count": max(0, int(visit_count or 0)),
                "browser": browser,
                "profile": profile,
            }
        )
    return visits


def clean_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw or len(raw) > 2000:
        return ""
    lowered = raw.lower()
    if lowered.startswith(("javascript:", "data:", "file:", "blob:")):
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if any(part in parsed.path.lower() for part in _RESET_PATH):
        return ""
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    fragment = parsed.fragment
    if fragment and re.search(r"(token|secret|password|access_token)=", fragment, re.IGNORECASE):
        fragment = ""
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        name = key.lower()
        lowered_value = value.lower()
        if (
            name in _SECRET_KEYS
            or name.endswith(("_token", "_secret", "_password"))
            or "token" in name
            or "secret" in name
            or "password" in name
        ):
            continue
        if name == "code" and len(value) >= 8:
            continue
        if value.startswith("eyJ") and value.count(".") == 2:
            continue
        if any(part in lowered_value for part in ("token=", "password=", "access_token", "client_secret")):
            continue
        kept.append((key, value))
    cleaned = urlunsplit((parsed.scheme, host, parsed.path, urlencode(kept, doseq=True), fragment))
    return cleaned[:2000]


def _clean_title(title: str, url: str) -> str:
    text = " ".join(title.split())
    if re.search(r"(token|password|secret|otp)=", text, re.IGNORECASE) or text.lower().startswith(("http://", "https://")):
        text = ""
    if not text:
        text = urlsplit(url).hostname or "Page"
    return text[:300]


def _from_chrome(value: object) -> datetime | None:
    try:
        when = _EPOCH + timedelta(microseconds=int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if when.year < 2008 or when > datetime.now(timezone.utc) + timedelta(days=2):
        return None
    return when


def _merge(existing: list[dict], fresh: list[dict]) -> list[dict]:
    combined: dict[tuple[str, str, str, str], dict] = {}
    for visit in existing + fresh:
        url = clean_url(str(visit.get("url") or ""))
        if not url:
            continue
        key = (
            str(visit.get("browser") or ""),
            str(visit.get("profile") or ""),
            url,
            str(visit.get("visited_at") or ""),
        )
        combined[key] = {
            "url": url,
            "title": _clean_title(str(visit.get("title") or ""), url),
            "visited_at": key[3],
            "visit_count": int(visit.get("visit_count") or 0),
            "browser": key[0],
            "profile": key[1],
        }
    ordered = sorted(combined.values(), key=lambda item: item["visited_at"], reverse=True)
    return ordered[:STORE_LIMIT]


def _store_file() -> Path:
    root = Path(settings.browser_history_root or "/browser-history")
    return root / "history.json"


def _load_unlocked() -> list[dict]:
    path = _store_file()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("browser history store could not be read")
        return []
    visits = payload.get("visits") if isinstance(payload, dict) else None
    if not isinstance(visits, list):
        return []
    return [item for item in visits if isinstance(item, dict) and item.get("url")]


def _save_unlocked(visits: list[dict]) -> None:
    path = _store_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "visits": visits,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _zone() -> timezone:
    raw = (settings.history_utc_offset or "+00:00").strip()
    match = _OFFSET_RE.match(raw)
    if not match:
        return timezone.utc
    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    if sign == "-":
        delta = -delta
    return timezone(delta)


def _time_window(question: str) -> tuple[datetime, datetime] | None:
    text = question.lower()
    now = datetime.now(_zone())
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "yesterday" in text:
        return (start_today - timedelta(days=1)).astimezone(timezone.utc), start_today.astimezone(timezone.utc)
    if "last night" in text:
        start = (start_today - timedelta(hours=4)).astimezone(timezone.utc)
        end = (start_today + timedelta(hours=6)).astimezone(timezone.utc)
        return start, end
    if "today" in text or "this morning" in text:
        return start_today.astimezone(timezone.utc), (start_today + timedelta(days=1)).astimezone(timezone.utc)
    if any(phrase in text for phrase in ("last week", "past week", "this week")):
        return (now - timedelta(days=7)).astimezone(timezone.utc), (now + timedelta(minutes=1)).astimezone(timezone.utc)
    return None


def _search_terms(question: str) -> list[str]:
    terms: list[str] = []
    for word in re.findall(r"[a-z0-9]+", question.lower()):
        if len(word) < 3 or word in _TERM_STOP or word in terms:
            continue
        terms.append(word)
    return terms[:6]


def _matches(visit: dict, terms: list[str]) -> bool:
    haystack = f"{visit.get('title', '')} {visit.get('url', '')}".lower()
    return all(term in haystack for term in terms)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _source(visit: dict) -> dict:
    url = str(visit.get("url") or "")
    stamp = str(visit.get("visited_at") or "")
    identity = "|".join(
        (
            str(visit.get("browser") or ""),
            str(visit.get("profile") or ""),
            stamp,
            url,
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return {
        "source_id": f"history:{digest}",
        "title": str(visit.get("title") or urlsplit(url).hostname or "Page"),
        "excerpt": _excerpt(visit),
        "origin": "Browser history",
        "url": url,
    }


def _excerpt(visit: dict) -> str:
    when = _parse_time(str(visit.get("visited_at") or ""))
    if when is None:
        stamp = str(visit.get("visited_at") or "")
    else:
        stamp = when.astimezone(_zone()).strftime("%d %b %Y %H:%M")
    count = int(visit.get("visit_count") or 0)
    times = "1 time" if count == 1 else f"{count} times"
    browser = str(visit.get("browser") or "Browser")
    profile = str(visit.get("profile") or "")
    who = f"{browser} {profile}".strip()
    return f"{stamp} · {times} · {who}"
