"""One-time LinkedIn connect for member posts."""

from __future__ import annotations

from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mcp.linkedin_client import (
    LinkedInAuthError,
    authorization_url,
    exchange_code,
    keys_present,
    safe_return,
    setup_message,
    status,
    take_return,
)

router = APIRouter(prefix="/api/v1/linkedin", tags=["linkedin"])


@router.get("/status")
async def linkedin_status() -> dict:
    return status()


@router.get("/connect", response_model=None)
async def linkedin_connect(request: Request, return_to: str = "") -> RedirectResponse | HTMLResponse:
    if not keys_present():
        return HTMLResponse(_page("Connect LinkedIn", setup_message()))
    origin = return_to or request.headers.get("referer") or ""
    try:
        url = authorization_url(origin)
    except LinkedInAuthError as exc:
        return HTMLResponse(_page("Connect LinkedIn", str(exc)))
    return RedirectResponse(url)


@router.get("/callback", response_model=None)
async def linkedin_callback(code: str = "", state: str = "", error: str = "", error_description: str = "") -> RedirectResponse:
    try:
        back = take_return(state)
    except LinkedInAuthError as exc:
        return RedirectResponse(_with_query(safe_return(""), {"linkedin": "error", "reason": str(exc)[:180]}))
    if error or not code:
        reason = error_description or error or "LinkedIn did not return a sign-in code."
        return RedirectResponse(_with_query(back, {"linkedin": "error", "reason": reason[:180]}))
    try:
        await exchange_code(code)
    except LinkedInAuthError as exc:
        return RedirectResponse(_with_query(back, {"linkedin": "error", "reason": str(exc)[:180]}))
    return RedirectResponse(_with_query(back, {"linkedin": "connected"}))


def _with_query(url: str, query: dict[str, str]) -> str:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}/"
    return base + "?" + urlencode(query)


def _page(title: str, message: str) -> str:
    body = "<br>".join(line or "<br>" for line in _escape(message).split("\n"))
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + _escape(title)
        + "</title></head><body style='font-family:Georgia,serif;max-width:40rem;margin:3rem auto;line-height:1.5'>"
        f"<h1>{_escape(title)}</h1><p>{body}</p><p><a href='/'>Back to Ask</a></p></body></html>"
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
