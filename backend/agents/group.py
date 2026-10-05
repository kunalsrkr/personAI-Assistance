"""AutoGen-style group: an orchestrator chooses which specialist speaks.

The specialists are the MCP-backed tools already in this app. The writer
speaks last, using the thread memory and the evidence the others returned.
"""

from __future__ import annotations

from servers.browser_history import wants_browser_history
from servers.file_server import media_request, wants_local_files
from servers.papers_server import is_paper_query, wants_linkedin_post
from mcp.gmail_client import is_gmail_query


ROSTER = {
    "orchestrator": "Chooses which agent speaks next.",
    "movies": "Finds a movie already on this computer and can play it.",
    "files": "Finds files and documents on this computer.",
    "mail": "Reads Gmail.",
    "library": "Searches the library.",
    "web": "Searches the web.",
    "history": "Searches browser history saved on this computer.",
    "papers": "Finds a highly cited arXiv paper, explains it, and can draft a LinkedIn post.",
    "linkedin": "Drafts a LinkedIn post. Publishing is not connected yet.",
    "writer": "Writes the answer from the evidence and this thread's memory.",
}


def plan(question: str) -> list[str]:
    text = question.lower()
    if wants_browser_history(question):
        return ["orchestrator", "history", "writer"]
    kind = media_request(question)
    if kind == "video":
        return ["orchestrator", "movies", "writer"]
    if kind == "audio":
        return ["orchestrator", "songs", "writer"]
    if kind == "image":
        return ["orchestrator", "images", "writer"]
    if is_paper_query(question):
        chosen = ["orchestrator", "papers"]
        if wants_linkedin_post(question):
            chosen.append("linkedin")
        chosen.append("writer")
        return chosen
    if wants_local_files(text):
        return ["orchestrator", "files", "writer"]
    chosen = ["orchestrator"]
    if is_gmail_query(text):
        chosen.append("mail")
    if any(word in text for word in ("file", "folder", "document", "pdf", "note")):
        chosen.append("files")
    if not chosen[1:] or any(word in text for word in ("web", "news", "latest", "weather", "search")):
        chosen.append("web")
    chosen.append("writer")
    return chosen


def opening(question: str) -> str:
    names = [name for name in plan(question) if name != "orchestrator"]
    spoken = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]
    return f"Orchestrator chose {spoken}."
