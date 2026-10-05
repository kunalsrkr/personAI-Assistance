"""LinkedIn OAuth and text posts for the signed-in member.

Client keys and the token stay outside the repo, in the user profile,
the same way Gmail does. Nothing here is committed.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

from core.config import settings

LINKEDIN_SCOPES = "openid profile w_member_social"
DEFAULT_REDIRECT = "http://localhost:8000/api/v1/linkedin/callback"
_AUTH = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
_USERINFO = "https://api.linkedin.com/v2/userinfo"
_POSTS = "https://api.linkedin.com/rest/posts"
_VERSIONS = ("202510", "202505", "202401")
_PENDING: dict[str, dict[str, float | str]] = {}


class LinkedInAuthError(RuntimeError):
    pass


class LinkedInError(RuntimeError):
    pass


def keys_path() -> Path:
    if settings.linkedin_oauth_keys_path:
        return Path(settings.linkedin_oauth_keys_path)
    return Path.home() / ".linkedin-mcp" / "oauth.keys.json"


def token_path() -> Path:
    if settings.linkedin_token_path:
        return Path(settings.linkedin_token_path)
    return Path.home() / ".linkedin-mcp" / "token.json"


def redirect_uri() -> str:
    keys = _read_keys()
    custom = str(keys.get("redirect_uri") or "").strip() if keys else ""
    return custom or settings.linkedin_redirect_uri or DEFAULT_REDIRECT


def keys_present() -> bool:
    keys = _read_keys()
    return bool(keys and keys.get("client_id") and keys.get("client_secret"))


def connected() -> bool:
    token = _read_token()
    if not token or not token.get("access_token"):
        return False
    expires = float(token.get("expires_at") or 0)
    if expires and expires < time.time() and not token.get("refresh_token"):
        return False
    return True


def status() -> dict:
    token = _read_token() if connected() else None
    detail = ""
    if not keys_present():
        detail = "LinkedIn keys are not on this computer yet."
    elif token is None:
        detail = "LinkedIn is not connected."
    return {
        "connected": token is not None,
        "name": (token or {}).get("name") or "",
        "keys_present": keys_present(),
        "redirect_uri": redirect_uri(),
        "scopes": LINKEDIN_SCOPES,
        "detail": detail,
    }


def setup_message() -> str:
    destination = keys_path()
    return (
        "LinkedIn is not connected because this computer has no app keys yet.\n\n"
        "In the LinkedIn developer portal (https://www.linkedin.com/developers/apps), create an app and add two products: "
        "Share on LinkedIn, and Sign In with LinkedIn using OpenID Connect.\n\n"
        f"Set the authorized redirect URL to exactly:\n{redirect_uri()}\n\n"
        f"The connect button asks for these scopes: {LINKEDIN_SCOPES}\n\n"
        "Then save the client id and client secret outside this repo, in your user profile:\n"
        ".linkedin-mcp\\oauth.keys.json\n"
        f"The backend reads that mounted file at {destination}.\n\n"
        "Use this shape, with the values from your app:\n"
        '{\n  "client_id": "paste from the LinkedIn app",\n  "client_secret": "paste from the LinkedIn app"\n}\n\n'
        "Restart is not required. Open Connect LinkedIn again after the file is saved."
    )


def authorization_url(return_to: str) -> str:
    if not keys_present():
        raise LinkedInAuthError(setup_message())
    keys = _read_keys()
    state = secrets.token_urlsafe(24)
    _PENDING[state] = {"return_to": safe_return(return_to), "at": time.time()}
    query = urlencode(
        {
            "response_type": "code",
            "client_id": keys["client_id"],
            "redirect_uri": redirect_uri(),
            "state": state,
            "scope": LINKEDIN_SCOPES,
        }
    )
    return f"{_AUTH}?{query}"


def take_return(state: str) -> str:
    pending = _PENDING.pop(state, None)
    if not pending:
        raise LinkedInAuthError("That LinkedIn sign-in session expired. Use Connect LinkedIn again.")
    if time.time() - float(pending["at"]) > 900:
        raise LinkedInAuthError("That LinkedIn sign-in session expired. Use Connect LinkedIn again.")
    return str(pending["return_to"])


def safe_return(url: str) -> str:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme in {"http", "https"} and host in {"localhost", "127.0.0.1"} and parsed.port:
        return f"{parsed.scheme}://{parsed.netloc}/"
    fallback = (settings.public_app_url or "http://localhost:5173").rstrip("/") + "/"
    return fallback


async def exchange_code(code: str) -> dict:
    keys = _read_keys()
    if not keys:
        raise LinkedInAuthError(setup_message())
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            _TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
                "client_id": keys["client_id"],
                "client_secret": keys["client_secret"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise LinkedInAuthError("LinkedIn did not accept the sign-in. Check the redirect URL and the app keys, then connect again.")
        payload = response.json()
        info = await client.get(_USERINFO, headers={"Authorization": f"Bearer {payload.get('access_token', '')}"})
    profile = info.json() if info.status_code < 400 else {}
    _write_token(payload, profile)
    return profile


async def publish_text(commentary: str) -> str:
    token = await _usable_token()
    person = str(token.get("person_id") or "")
    if not person:
        raise LinkedInAuthError("LinkedIn is connected, but the member id is missing. Connect LinkedIn again.")
    author = person if person.startswith("urn:") else f"urn:li:person:{person}"
    body = {
        "author": author,
        "commentary": commentary.strip()[:2900],
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    last_detail = "LinkedIn did not publish the post."
    async with httpx.AsyncClient(timeout=45.0) as client:
        for version in _VERSIONS:
            response = await client.post(
                _POSTS,
                json=body,
                headers={
                    "Authorization": f"Bearer {token['access_token']}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": version,
                },
            )
            if response.status_code < 400:
                post_id = response.headers.get("x-restli-id") or response.headers.get("x-linkedin-id") or ""
                if post_id:
                    return f"https://www.linkedin.com/feed/update/{post_id}"
                return "https://www.linkedin.com/feed/"
            last_detail = _safe_error(response)
            if response.status_code not in {400, 403, 426}:
                break
    raise LinkedInError(last_detail)


def _safe_error(response: httpx.Response) -> str:
    detail = " ".join(response.text.split())[:240]
    return f"LinkedIn did not publish the post (HTTP {response.status_code}). {detail}"


async def _usable_token() -> dict:
    token = _read_token()
    if not token or not token.get("access_token"):
        raise LinkedInAuthError("LinkedIn is not connected. Use Connect LinkedIn on the Ask page.")
    expires = float(token.get("expires_at") or 0)
    if not expires or expires > time.time() + 30:
        return token
    refresh = token.get("refresh_token") or ""
    keys = _read_keys()
    if not refresh or not keys:
        raise LinkedInAuthError("The LinkedIn connection expired. Use Connect LinkedIn again.")
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            _TOKEN,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": keys["client_id"],
                "client_secret": keys["client_secret"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code >= 400:
        raise LinkedInAuthError("The LinkedIn connection expired. Use Connect LinkedIn again.")
    payload = response.json()
    payload.setdefault("refresh_token", refresh)
    _write_token(payload, {"sub": token.get("person_id") or "", "name": token.get("name") or ""})
    updated = _read_token()
    if not updated:
        raise LinkedInAuthError("The LinkedIn connection expired. Use Connect LinkedIn again.")
    return updated


def _read_keys() -> dict | None:
    path = keys_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and "installed" in data and isinstance(data["installed"], dict):
        data = data["installed"]
    if isinstance(data, dict) and "web" in data and isinstance(data["web"], dict):
        data = data["web"]
    return data if isinstance(data, dict) else None


def _read_token() -> dict | None:
    path = token_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_token(payload: dict, profile: dict) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    expires_in = int(payload.get("expires_in") or 0)
    record = {
        "access_token": payload.get("access_token") or "",
        "refresh_token": payload.get("refresh_token") or "",
        "expires_at": time.time() + expires_in - 60 if expires_in else 0,
        "person_id": profile.get("sub") or "",
        "name": profile.get("name") or "",
    }
    path.write_text(json.dumps(record), encoding="utf-8")
