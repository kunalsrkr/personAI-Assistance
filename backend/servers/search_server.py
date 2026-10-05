"""Web search MCP server. Search and page fetch stay separate."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

NAME = "search"
TOOLS = ["search.web", "search.fetch", "search.weather"]
_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_WEATHER = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    95: "Thunderstorm",
}


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict] = []
        self._capture = False
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "a" and "result__a" in data.get("class", ""):
            self._capture = True
            self._href = data.get("href", "")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture:
            title = " ".join(part.strip() for part in self._text if part.strip())
            url = _clean_url(self._href)
            if title and url:
                self.results.append({"title": title, "url": url, "snippet": "", "source": "DuckDuckGo"})
            self._capture = False


def _clean_url(href: str) -> str:
    if "uddg=" in href:
        parsed = parse_qs(urlparse(href).query)
        if parsed.get("uddg"):
            return unquote(parsed["uddg"][0])
    if href.startswith("http"):
        return href
    return ""


def weather_place(question: str) -> str | None:
    if not any(word in question.lower() for word in ("weather", "temperature", "forecast", "humidity", "raining", "rain")):
        return None
    match = re.search(
        r"\b(?:in|at|for)\s+([A-Za-z][A-Za-z .'-]{0,40}?)(?=\s+(?:give|cover|say|show|list|summarize|compare|open|keep|include|prefer|answer|also|use|search)\b|[?.]|$)",
        question.strip(),
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" ?.")
    return None


def _prefer_city(place: str, matches: list[dict]) -> dict:
    lowered = place.lower()
    indian = {
        "bangalore",
        "bengaluru",
        "kolkata",
        "calcutta",
        "mumbai",
        "bombay",
        "delhi",
        "chennai",
        "hyderabad",
        "pune",
        "jaipur",
    }
    if any(name in lowered for name in indian):
        for city in matches:
            if city.get("country") == "India":
                return city
    return matches[0]


async def weather_report(place: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": place, "count": 8, "language": "en", "format": "json"},
            )
            if geo.status_code >= 400:
                return None
            matches = (geo.json() or {}).get("results") or []
            if not matches:
                return None
            city = _prefer_city(place, matches)
            forecast = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": city["latitude"],
                    "longitude": city["longitude"],
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
            )
            if forecast.status_code >= 400:
                return None
            data = forecast.json()
    except httpx.HTTPError:
        return None
    current = data.get("current") or {}
    units = data.get("current_units") or {}
    condition = _WEATHER.get(current.get("weather_code"), "Unknown conditions")
    name = ", ".join(part for part in (city.get("name"), city.get("admin1"), city.get("country")) if part)
    text = (
        f"{name}. Now {current.get('temperature_2m')} {units.get('temperature_2m', '°C')}, {condition}, "
        f"humidity {current.get('relative_humidity_2m')}%, "
        f"wind {current.get('wind_speed_10m')} {units.get('wind_speed_10m', 'km/h')}."
    )
    daily = data.get("daily") or {}
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    if highs and lows:
        text += f" Today high {highs[0]} and low {lows[0]}."
    return {
        "title": f"Weather in {city.get('name') or place}",
        "url": "https://open-meteo.com/",
        "snippet": text,
        "source": "Open-Meteo",
    }


async def web_search(query: str, limit: int = 5) -> list[dict]:
    results: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": _BROWSER},
            )
        if response.status_code < 400:
            parser = _ResultParser()
            parser.feed(response.text)
            results = parser.results[:limit]
    except httpx.HTTPError:
        results = []
    if results:
        return results
    try:
        fallback = await client_fallback(query)
    except httpx.HTTPError:
        return []
    return fallback[:limit]


async def client_fallback(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1"},
        )
    if response.status_code >= 400:
        return []
    payload = response.json()
    results = []
    if payload.get("AbstractText") and payload.get("AbstractURL"):
        results.append(
            {
                "title": payload.get("Heading") or query,
                "url": payload["AbstractURL"],
                "snippet": payload["AbstractText"],
                "source": "DuckDuckGo",
            }
        )
    return results


async def fetch_page(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https pages can be fetched.")
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _BROWSER})
    except httpx.HTTPError as exc:
        return f"The page could not be opened ({type(exc).__name__})."
    if response.status_code >= 400:
        return f"The page returned HTTP {response.status_code}."
    text = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", response.text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]
