"""Short text translation for Ask voice.

The question is turned into English before the agents run. The finished
answer is turned back into the language the user selected. Chunks run
together so a spoken question stays quick.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["translate"])

ALLOWED = {"en", "hi", "bn", "mr", "ta", "te", "kn", "ml", "ja"}


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    source: str = Field(min_length=2, max_length=5)
    target: str = Field(min_length=2, max_length=5)


def _pieces(text: str, size: int = 450) -> list[str]:
    parts: list[str] = []
    current = ""
    for block in text.split("\n"):
        if len(current) + len(block) + 1 > size and current:
            parts.append(current)
            current = block
            continue
        current = f"{current}\n{block}" if current else block
    if current:
        parts.append(current)
    return parts or [text]


async def _google(client: httpx.AsyncClient, text: str, source: str, target: str) -> str:
    response = await client.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
    )
    response.raise_for_status()
    payload = response.json()
    return "".join(row[0] for row in payload[0] if row and row[0])


async def _memory(client: httpx.AsyncClient, text: str, source: str, target: str) -> str:
    response = await client.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text[:450], "langpair": f"{source}|{target}"},
    )
    response.raise_for_status()
    payload = response.json()
    translated = str(payload.get("responseData", {}).get("translatedText") or "")
    if not translated or translated.upper().startswith("QUERY LENGTH"):
        raise ValueError("empty translation")
    return translated


async def _one(client: httpx.AsyncClient, text: str, source: str, target: str) -> str:
    try:
        return await _google(client, text, source, target)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        return await _memory(client, text, source, target)


@router.post("/translate")
async def translate(body: TranslateRequest) -> dict[str, str]:
    source = body.source.lower()
    target = body.target.lower()
    if source not in ALLOWED or target not in ALLOWED:
        raise HTTPException(status_code=400, detail="That language is not supported.")
    text = body.text.strip()
    if source == target or not text:
        return {"text": text}
    pieces = _pieces(text)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            translated = await asyncio.gather(*(_one(client, piece, source, target) for piece in pieces))
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=503, detail="Translation is not reachable right now.") from exc
    return {"text": "".join(translated).strip()}
