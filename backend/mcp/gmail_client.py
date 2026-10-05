"""Direct read-only Gmail API client.

Google's hosted Gmail MCP server rejects personal @gmail.com accounts.
Mail questions call https://gmail.googleapis.com with the saved OAuth token.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from core.config import settings
from models.schemas import InvestigationSource

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailAuthError(RuntimeError):
    pass


class GmailMcpError(RuntimeError):
    pass


def keys_path() -> Path:
    if settings.gmail_oauth_keys_path:
        return Path(settings.gmail_oauth_keys_path)
    return Path.home() / ".gmail-mcp" / "gcp-oauth.keys.json"


def token_path() -> Path:
    if settings.gmail_token_path:
        return Path(settings.gmail_token_path)
    return Path.home() / ".gmail-mcp" / "credentials.json"


def is_gmail_query(query: str) -> bool:
    text = query.lower()
    hints = ("gmail", "inbox", "e-mail", "email", "unread mail", "my mail")
    return any(hint in text for hint in hints)


def wants_oldest_mail(question: str) -> bool:
    text = question.lower()
    hints = (
        "created",
        "creation",
        "account opened",
        "signed up",
        "sign up",
        "first email",
        "oldest",
        "earliest",
        "how old",
    )
    return any(hint in text for hint in hints)


def gmail_search_query(question: str) -> str:
    text = question.lower()
    parts: list[str] = []
    if "unread" in text:
        parts.append("is:unread")
    if "today" in text or "yesterday" in text:
        parts.append("newer_than:1d")
    elif "week" in text:
        parts.append("newer_than:7d")
    elif "month" in text:
        parts.append("newer_than:30d")
    elif "recent" in text:
        parts.append("newer_than:14d")
    return " ".join(parts)


def load_credentials() -> Credentials:
    path = token_path()
    if not path.is_file():
        raise GmailAuthError(
            "Gmail is not signed in. From the backend folder run: python gmail_auth.py"
        )
    creds = Credentials.from_authorized_user_file(str(path), [GMAIL_SCOPE])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid or not creds.token:
        raise GmailAuthError("Gmail token is missing or expired. Run python gmail_auth.py again.")
    return creds


class GmailMcpClient:
    """Direct Gmail API lookup. The investigation route keeps this class name."""

    async def _get(self, path: str, params: dict | None = None) -> dict:
        creds = load_credentials()
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.get(
                f"{GMAIL_API}{path}",
                headers={"Authorization": f"Bearer {creds.token}"},
                params=params,
            )
        if response.status_code == 401:
            raise GmailAuthError("Gmail rejected the token. Run python gmail_auth.py again.")
        if response.status_code >= 400:
            detail = response.text[:300].replace("\n", " ")
            raise GmailMcpError(f"Gmail API HTTP {response.status_code}: {detail}")
        return response.json()

    async def _message_ids(self, question: str) -> tuple[list[str], int, str]:
        if wants_oldest_mail(question):
            page_token: str | None = None
            oldest_ids: list[str] = []
            calls = 0
            for _ in range(40):
                params: dict[str, str | int] = {"maxResults": 100}
                if page_token:
                    params["pageToken"] = page_token
                listed = await self._get("/messages", params)
                calls += 1
                page_ids = [item["id"] for item in listed.get("messages") or []]
                if page_ids:
                    oldest_ids = page_ids
                page_token = listed.get("nextPageToken")
                if not page_token:
                    return list(reversed(oldest_ids))[:5], calls, "oldest messages in the mailbox"
            return list(reversed(oldest_ids))[:5], calls, "oldest messages reached before the page limit"

        query = gmail_search_query(question)
        params = {"maxResults": 10}
        if query:
            params["q"] = query
        listed = await self._get("/messages", params)
        calls = 1
        messages = listed.get("messages") or []
        if not messages and query and "newer_than:30d" not in query:
            listed = await self._get("/messages", {"q": "newer_than:30d", "maxResults": 10})
            messages = listed.get("messages") or []
            calls += 1
            scope = "last 30 days"
        else:
            scope = query or "most recent messages"
        return [item["id"] for item in messages[:10]], calls, scope

    async def collect(self, question: str) -> tuple[str, list[InvestigationSource], int]:
        message_ids, calls, scope = await self._message_ids(question)
        blocks: list[str] = [f"Search scope: {scope}"]
        sources: list[InvestigationSource] = []
        for message_id in message_ids:
            message = await self._get(
                f"/messages/{message_id}",
                {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            calls += 1
            headers = {
                header.get("name", ""): header.get("value", "")
                for header in (message.get("payload") or {}).get("headers") or []
            }
            subject = headers.get("Subject") or "(no subject)"
            snippet = message.get("snippet") or ""
            blocks.append(
                "\n".join(
                    [
                        f"id: {message_id}",
                        f"From: {headers.get('From', '')}",
                        f"Subject: {subject}",
                        f"Date: {headers.get('Date', '')}",
                        f"Snippet: {snippet}",
                    ]
                )
            )
            sources.append(
                InvestigationSource(
                    source_id=message_id,
                    title=subject,
                    excerpt=snippet[:240],
                    origin="Gmail",
                )
            )

        if not sources:
            sources.append(
                InvestigationSource(
                    source_id="gmail-search",
                    title="Gmail search",
                    excerpt="No messages matched.",
                )
            )
        return "\n\n".join(blocks)[:12000], sources, calls


_STYLES = {
    "brief": ("Answer in two or three sentences.", 800),
    "clear": ("Answer in one short paragraph.", 1400),
    "full": ("Answer in a few short paragraphs.", 2200),
}


def _answer_prompt(question: str, evidence: str, style: str = "clear", memory: str = "") -> str:
    length, _limit = _STYLES.get(style, _STYLES["clear"])
    prior = f"{memory.strip()}\n\n" if memory.strip() else ""
    return (
        "Answer only from the evidence. Each evidence block names its origin. "
        "Start the answer with the origins you used, such as Gmail, Web, File, Document, Library, or Weather. "
        "For files, name the file and its type. Do not answer from the public web when the evidence is a local file search. "
        "If a fact is not in the evidence, say it was not found. "
        "Use the session so far when the question refers to an earlier answer. "
        f"{length} "
        "The Gmail API does not provide an official account-creation timestamp. "
        "If asked when the account was created, use the earliest message date and say that this is the earliest email found.\n\n"
        f"{prior}Question:\n{question}\n\nEvidence:\n{evidence}"
    )


async def stream_answer(
    question: str,
    evidence: str,
    model: str | None = None,
    deadline: float | None = None,
    style: str = "clear",
    memory: str = "",
):
    """Yield answer and thinking text as Ollama produces it. A slow model is not cut off."""
    del deadline
    if not evidence.strip():
        yield ("answer", "No matching evidence was returned.")
        return
    installed = await list_models()
    chosen = model if model and model in installed else None
    if chosen is None:
        chosen = await _installed_model()
    if chosen is None:
        yield ("answer", "Evidence was retrieved, but Ollama has no model available.\n\n" + evidence[:1500])
        return
    seen = {"answer": "", "think": ""}
    _length, predict = _STYLES.get(style, _STYLES["clear"])
    timeout = httpx.Timeout(20.0, read=None, write=60.0, pool=20.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": chosen,
                    "stream": True,
                    "options": {"num_predict": predict},
                    "messages": [
                        {"role": "system", "content": "You answer only from the supplied evidence and name each source."},
                        {"role": "user", "content": _answer_prompt(question, evidence, style, memory)},
                    ],
                },
            ) as response:
                if response.status_code >= 400:
                    yield ("answer", "The model could not summarize this. The sources above are the evidence.")
                    return
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = payload.get("message") or {}
                    for channel, key in (("think", "thinking"), ("answer", "content")):
                        piece = message.get(key) or ""
                        if not piece:
                            continue
                        previous = seen[channel]
                        delta = piece[len(previous) :] if piece.startswith(previous) and previous else piece
                        if not delta:
                            continue
                        seen[channel] += delta
                        yield (channel, delta)
                    if payload.get("done"):
                        break
    except httpx.HTTPError as exc:
        yield ("answer", f"\n\nThe model paused ({type(exc).__name__}). The sources above are the evidence.")
    if not seen["answer"]:
        yield ("answer", "The model returned no summary. The sources above are the evidence.")


async def summarize(question: str, evidence: str, model: str | None = None) -> str:
    parts = [text async for channel, text in stream_answer(question, evidence, model) if channel == "answer"]
    return "".join(parts)


async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        return [item.get("name", "") for item in response.json().get("models") or [] if item.get("name")]
    except httpx.HTTPError:
        return []


async def _installed_model() -> str | None:
    names = await list_models()
    if not names:
        return None
    preferred = [settings.ollama_model, "llama3.1:latest", "qwen3:8b", "gemma3:latest"]
    for name in preferred:
        if name in names:
            return name
    return names[0] if names else None
