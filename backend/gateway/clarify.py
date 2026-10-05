"""A short run of multiple-choice questions so a vague request gets a direction."""

from __future__ import annotations

import re

from mcp.gmail_client import is_gmail_query
from servers.file_server import wants_local_files


def guidance_steps(question: str) -> list[dict]:
    from servers.browser_history import wants_browser_history

    from servers.papers_server import is_paper_query

    if wants_browser_history(question) or is_paper_query(question):
        return []
    text = question.lower()
    steps: list[dict] = []
    weather = any(word in text for word in ("weather", "temperature", "forecast", "humidity"))
    place = re.search(r"\b(?:in|at|for)\s+[a-z]", text)
    if weather and not place:
        steps.append(
            {
                "prompt": "Which place should I check?",
                "choices": [
                    {"id": "kolkata", "label": "Kolkata"},
                    {"id": "mumbai", "label": "Mumbai"},
                    {"id": "delhi", "label": "Delhi"},
                    {"id": "bengaluru", "label": "Bengaluru"},
                ],
            }
        )
    if weather:
        steps.append(
            {
                "prompt": "What do you want from the forecast?",
                "choices": [
                    {"id": "weather_now", "label": "Right now"},
                    {"id": "weather_today", "label": "The whole day"},
                    {"id": "weather_out", "label": "Should I go out"},
                ],
            }
        )
    elif wants_local_files(text):
        steps.append(
            {
                "prompt": "How should I use the files I find?",
                "choices": [
                    {"id": "list", "label": "List the names"},
                    {"id": "summarize", "label": "Summarize each"},
                    {"id": "compare", "label": "Compare them"},
                ],
            }
        )
        steps.append(
            {
                "prompt": "How many files should I open?",
                "choices": [
                    {"id": "top", "label": "The best match"},
                    {"id": "few", "label": "A few"},
                    {"id": "all", "label": "As many as the limit allows"},
                ],
            }
        )
    elif is_gmail_query(text):
        steps.append(
            {
                "prompt": "Which mail should I read?",
                "choices": [
                    {"id": "recent", "label": "The latest"},
                    {"id": "unread", "label": "Unread"},
                    {"id": "oldest", "label": "The oldest"},
                ],
            }
        )
        steps.append(
            {
                "prompt": "How much of each message?",
                "choices": [
                    {"id": "one_line", "label": "One line each"},
                    {"id": "details", "label": "A few details"},
                ],
            }
        )
    else:
        steps.append(
            {
                "prompt": "What should I focus on?",
                "choices": [
                    {"id": "direct", "label": "A direct answer"},
                    {"id": "latest", "label": "The latest"},
                    {"id": "overview", "label": "A short overview"},
                ],
            }
        )
        steps.append(
            {
                "prompt": "How do you want it told?",
                "choices": [
                    {"id": "one_line", "label": "One or two sentences"},
                    {"id": "details", "label": "A short note"},
                    {"id": "walk", "label": "Walk me through it"},
                ],
            }
        )
    return steps[:2]


def support_step(question: str, titles: list[str]) -> dict | None:
    """One question after sources arrive, so a missed site can be added before writing."""
    text = question.lower()
    if "also read" in text or "use only the direct weather" in text:
        return None
    found = ", ".join(titles[:3]) or "nothing yet"
    weather = any(word in text for word in ("weather", "temperature", "forecast", "humidity"))
    if weather:
        return {
            "prompt": f"Sources so far: {found}. Did the search miss a site?",
            "seconds": 15,
            "choices": [
                {"id": "use_found", "label": "Use what was found"},
                {"id": "site_accu", "label": "Also open AccuWeather"},
                {"id": "site_imd", "label": "Also check IMD"},
                {"id": "site_custom", "label": "Use a site I name"},
            ],
        }
    return {
        "prompt": f"Sources so far: {found}. Should I look again before writing?",
        "seconds": 15,
        "choices": [
            {"id": "use_found", "label": "Write from these"},
            {"id": "narrow", "label": "Look again, narrower"},
            {"id": "broader", "label": "Look again, more broadly"},
            {"id": "site_custom", "label": "Use a site I name"},
        ],
    }


def review_step(question: str = "") -> dict:
    choices = [
        {"id": "keep", "label": "This is enough"},
        {"id": "again_shorter", "label": "Try again, shorter"},
        {"id": "again_broader", "label": "Try again, different pages"},
    ]
    if any(word in question.lower() for word in ("weather", "temperature", "forecast", "humidity")):
        choices.insert(1, {"id": "again_weather", "label": "Try again from the weather report"})
    return {
        "prompt": "Does this answer work? If not, I will run it again with your change.",
        "choices": choices,
    }


def apply_choice(question: str, choice_id: str, note: str = "") -> str:
    if choice_id == "site_custom":
        cleaned = re.sub(r"[^A-Za-z0-9. \-]", "", note).strip()[:60]
        if cleaned:
            return f"{question} Also read {cleaned}."
        return question
    extra = {
        "kolkata": " in Kolkata",
        "mumbai": " in Mumbai",
        "delhi": " in Delhi",
        "bengaluru": " in Bengaluru",
        "list": " List the matching file names.",
        "summarize": " Summarize each matching file.",
        "compare": " Compare the matching files.",
        "recent": " Show the latest messages.",
        "unread": " Show unread mail.",
        "oldest": " Show the oldest messages.",
        "weather_now": " Give the conditions right now.",
        "weather_today": " Cover the whole day.",
        "weather_out": " Say whether it is a good time to go out.",
        "top": " Open only the best matching file.",
        "few": " Open a few matching files.",
        "all": " Open the matching files the search returns.",
        "one_line": " Keep each message to one line.",
        "details": " Include a few details from each message.",
        "direct": " Give a direct answer.",
        "latest": " Prefer the latest information.",
        "overview": " Give a short overview.",
        "walk": " Walk through the answer in a few short steps.",
        "use_found": "",
        "site_accu": " Also read AccuWeather.",
        "site_imd": " Also read the India Meteorological Department forecast.",
        "narrow": " Search again with a narrower query.",
        "broader": " Search again more broadly.",
        "again_weather": " Use only the direct weather report. Answer from that report.",
        "again_shorter": " Answer in two sentences.",
        "again_broader": " Search again more broadly and open a different page.",
    }.get(choice_id, "")
    return f"{question}{extra}"
