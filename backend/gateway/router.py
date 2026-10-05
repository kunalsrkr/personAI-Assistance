"""Routes a question to the focused MCP servers and streams progress."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from gateway.clarify import apply_choice, support_step
from agents.group import plan
from gateway.memory import follow_up, prompt_block
from mcp.gmail_client import GmailAuthError, GmailMcpClient, GmailMcpError, is_gmail_query, stream_answer
from models.schemas import InvestigationSource
from library.store import search as search_library
from servers import document_server, file_server, papers_server, search_server, spreadsheet_server
from servers.browser_history import search_history, wants_browser_history
from servers.papers_server import is_paper_query
from servers.file_server import filename_terms, find_by_name, find_media, media_request, media_terms, wants_local_files
from servers.workspace import search_roots

SERVERS = ("file", "document", "spreadsheet", "search", "gmail")


def select_servers(question: str) -> list[str]:
    text = question.lower()
    if wants_local_files(text):
        return ["local_files"]
    if is_paper_query(question):
        return ["papers"]
    chosen: list[str] = []
    if is_gmail_query(text):
        chosen.append("gmail")
    if any(word in text for word in ("spreadsheet", "csv", "excel", "revenue", "sheet")):
        chosen.append("spreadsheet")
    if any(word in text for word in ("file", "folder", "workspace", "document", "contract", "pdf", "note")):
        chosen.append("file")
        chosen.append("document")
    web_words = ("web", "internet", "online", "news", "search the web", "look up", "latest")
    if any(word in text for word in web_words) or not chosen:
        chosen.append("search")
    return list(dict.fromkeys(chosen))


def _stage(stage_id: str, label: str, status: str, detail: str = "") -> dict[str, Any]:
    return {"type": "stage", "stage": {"id": stage_id, "label": label, "status": status, "detail": detail}}


def _evidence(source: InvestigationSource) -> dict[str, Any]:
    return {"type": "evidence", "source": source.model_dump()}


async def run_question(question: str, model: str | None) -> tuple[str, list[InvestigationSource], int, str | None]:
    answer: list[str] = []
    sources: list[InvestigationSource] = []
    calls = 0
    async for event in iter_question(question, model):
        if event["type"] == "token" and event.get("channel", "answer") == "answer":
            answer.append(event["text"])
        elif event["type"] == "evidence":
            sources.append(InvestigationSource(**event["source"]))
        elif event["type"] == "stage" and event["stage"]["status"] == "completed":
            calls += 1
    return "".join(answer), sources, calls, model


def _out_of_time(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() > deadline


def _direct_answer(sources: list[InvestigationSource]) -> str:
    for source in sources:
        if source.origin == "Weather" and source.excerpt.strip():
            return source.excerpt.strip()
    excerpts = [source.excerpt.strip() for source in sources if source.excerpt.strip()]
    if excerpts:
        return excerpts[0]
    return ""


async def iter_question(
    question: str,
    model: str | None,
    deadline: float | None = None,
    style: str = "clear",
    steer=None,
    deadline_box: list | None = None,
    memory: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    box = deadline_box if deadline_box is not None else [deadline]
    routed = question if memory is not None else follow_up(question)
    servers = ["movies"] if media_request(question) else select_servers(routed)
    names = [name for name in plan(question) if name != "orchestrator"]
    spoken = ", ".join(names)
    yield _stage("route", "Orchestrator", "running", "Choosing which agent speaks")
    yield _stage("route", "Orchestrator", "completed", spoken)
    yield {"type": "hint", "text": f"Orchestrator chose {spoken}."}
    evidence_blocks: list[str] = []
    sources: list[InvestigationSource] = []
    if wants_browser_history(question):
        stored = 0
        async for event in _iter_history(question):
            if event["type"] == "history_meta":
                stored = int(event.get("stored") or 0)
                continue
            if event["type"] == "evidence":
                sources.append(InvestigationSource(**event["source"]))
            yield event
        if sources:
            note = f"{len(sources)} pages from your browser history on this computer. Open a link to go to that page."
        elif stored == 0:
            note = "No browser history is saved yet. It is collected on this computer when the machine is online."
        else:
            note = "No saved browser history matched that question."
        yield {"type": "token", "text": note, "channel": "answer"}
        yield _stage("model", "Writer", "completed", "browser history")
        return

    if is_paper_query(routed) and not media_request(question):
        used_memory = memory if memory is not None else prompt_block()
        async for event in _iter_papers(routed, model, style, used_memory):
            yield event
        return

    if servers != ["movies"]:
        async for event in _iter_library(question):
            if event["type"] == "block":
                evidence_blocks.append(event["text"])
                continue
            if event["type"] == "evidence":
                sources.append(InvestigationSource(**event["source"]))
            yield event

    if servers == ["movies"]:
        catalog_total = 0
        async for event in _iter_movies(question):
            if event["type"] == "catalog":
                catalog_total = int(event.get("total") or 0)
                continue
            if event["type"] == "evidence":
                sources.append(InvestigationSource(**event["source"]))
            yield event
        kind = media_request(question) or "video"
        label = {"video": "movies", "audio": "songs", "image": "images"}.get(kind, "files")
        if sources:
            count = f"{len(sources)} of {catalog_total}" if catalog_total > len(sources) else str(len(sources))
            note = f"{count} {label} on this computer. Choose Play on the one you want."
        else:
            note = f"No {label} matched on this computer."
        yield {"type": "token", "text": note, "channel": "answer"}
        yield _stage("model", "Writer", "completed", label)
        return

    if servers == ["local_files"]:
        async for event in _iter_local_files(routed):
            if event["type"] == "block":
                evidence_blocks.append(event["text"])
                continue
            if event["type"] == "evidence":
                sources.append(InvestigationSource(**event["source"]))
            yield event
    else:
        for server in servers:
            label = _server_label(server)
            yield _stage(server, label, "running", "Working")
            yield {"type": "hint", "text": f"{label} is running."}
            try:
                block, found, count = await _call(server, routed)
            except (GmailAuthError, GmailMcpError, OSError, ValueError, FileNotFoundError, httpx.HTTPError) as exc:
                yield {"type": "hint", "text": f"{label} could not finish ({type(exc).__name__}). Continuing."}
                yield _stage(server, label, "completed", type(exc).__name__)
                continue
            evidence_blocks.append(block)
            for source in found:
                sources.append(source)
                yield _evidence(source)
            yield _stage(server, label, "completed", f"{count} result{'s' if count != 1 else ''}")

    if steer is not None and not _out_of_time(box[0]):
        step = support_step(question, [source.title for source in sources])
        if step:
            choice, note = await steer(step)
            question = apply_choice(question, choice, note)
            yield {"type": "hint", "text": "Using your choice."}
            if choice not in {"", "use_found"}:
                yield {"type": "hint", "text": "Looking again with your change."}
                try:
                    block, found, count = await _call("search", question)
                except (OSError, ValueError, httpx.HTTPError):
                    block, found, count = "", [], 0
                if block:
                    evidence_blocks.append(block)
                for source in found:
                    if any(existing.source_id == source.source_id for existing in sources):
                        continue
                    sources.append(source)
                    yield _evidence(source)
                if count:
                    yield _stage("search", "Searching the web", "completed", f"{count} more")
    weather = next((source.excerpt.strip() for source in sources if source.origin == "Weather" and source.excerpt.strip()), "")
    if weather:
        yield {"type": "token", "text": weather + "\n\n", "channel": "answer"}
    evidence = "\n\n".join(block for block in evidence_blocks if block.strip())[:12000]
    model_name = model or "the local model"
    yield _stage("model", "Writer", "running", model_name)
    yield {"type": "hint", "text": f"Writer is using this thread's memory and the evidence."}
    used_memory = memory if memory is not None else prompt_block()
    async for channel, text in stream_answer(question, evidence, model, style=style, memory=used_memory):
        yield {"type": "token", "text": text, "channel": channel}
    yield _stage("model", "Writer", "completed", model_name)


async def _iter_library(question: str) -> AsyncIterator[dict[str, Any]]:
    hits = await asyncio.to_thread(search_library, question)
    if not hits:
        return
    yield _stage("library", "Searching your library", "running", f"{len(hits)} match{'es' if len(hits) != 1 else ''}")
    lines = ["[Library]"]
    for hit in hits:
        source = InvestigationSource(
            source_id=f"library:{hit['id']}",
            title=hit["title"],
            excerpt=hit["excerpt"],
            origin="Library",
        )
        link = f" transcript {hit['transcript_id']}" if hit.get("transcript_id") else ""
        lines.append(f"{hit['kind']}: {hit['title']}{link}\n{hit['excerpt']}")
        yield _evidence(source)
    yield {"type": "block", "text": "\n".join(lines)}
    yield _stage("library", "Searching your library", "completed", ", ".join(hit["title"] for hit in hits))


def _server_label(server: str) -> str:
    return {
        "gmail": "Mail agent",
        "search": "Web agent",
        "file": "File agent",
        "document": "File agent",
        "spreadsheet": "File agent",
        "movies": "Movie agent",
        "history": "History agent",
        "papers": "Papers agent",
        "linkedin": "LinkedIn",
    }.get(server, server)


async def _call(server: str, question: str) -> tuple[str, list[InvestigationSource], int]:
    if server == "gmail":
        evidence, sources, calls = await GmailMcpClient().collect(question)
        return f"[Gmail]\n{evidence}", sources, calls
    if server == "search":
        lines: list[str] = []
        sources: list[InvestigationSource] = []
        calls = 0
        place = search_server.weather_place(question)
        if place:
            report = await search_server.weather_report(place)
            if report:
                sources.append(
                    InvestigationSource(
                        source_id=f"weather:{place.lower()}",
                        title=report["title"],
                        excerpt=report["snippet"],
                        origin="Weather",
                    )
                )
                lines.append(f"[Weather]\n{report['snippet']}")
                calls += 1
        results = await search_server.web_search(question, limit=5)
        for item in results:
            link = str(item.get("url") or "")
            sources.append(
                InvestigationSource(
                    source_id=link or item["title"],
                    title=item["title"],
                    excerpt=item.get("snippet", ""),
                    origin="Web",
                    url=link if link.startswith(("http://", "https://")) else "",
                )
            )
            lines.append(f"[Web search]\n- {item['title']} | {item['url']}")
        if results:
            page = await search_server.fetch_page(results[0]["url"])
            lines.append(f"Fetched page: {results[0]['url']}\n{page[:1500]}")
            calls += 1
        calls += 1
        return "\n".join(lines), sources, calls
    if server == "file":
        matches = file_server.search_files(question) or file_server.list_files()
        sources = [
            InvestigationSource(source_id=item["path"], title=item["path"], origin="File")
            for item in matches[:8]
        ]
        lines = ["[File]"] + [f"- {item['path']}" for item in matches[:8]]
        return "\n".join(lines), sources, 1
    if server == "document":
        hits = document_server.search(question)
        if not hits:
            files = [item["path"] for item in file_server.list_files() if item["path"].endswith((".md", ".txt"))]
            hits = [{"path": path, "excerpt": document_server.extract_text(path)[:400]} for path in files[:2]]
        sources = [
            InvestigationSource(source_id=item["path"], title=item["path"], excerpt=item["excerpt"][:240], origin="Document")
            for item in hits
        ]
        lines = ["[Document]"]
        for item in hits:
            lines.append(f"{item['path']}\n{item['excerpt']}")
        return "\n\n".join(lines), sources, 1
    if server == "spreadsheet":
        sheets = spreadsheet_server.list_sheets()
        blocks = ["[Spreadsheet]"]
        sources = []
        for sheet in sheets[:3]:
            data = spreadsheet_server.read_sheet(sheet)
            sources.append(InvestigationSource(source_id=sheet, title=sheet, origin="Spreadsheet"))
            blocks.append(f"{sheet} columns={data['columns']} rows={data['rows']}")
        return "\n".join(blocks), sources, len(sheets[:3]) or 1
    raise ValueError(f"Unknown server {server}")


def _play_place(path: Path) -> tuple[int, str] | None:
    resolved = path.resolve()
    for index, root in enumerate(search_roots()):
        try:
            if resolved.is_relative_to(root.resolve()):
                return index, resolved.relative_to(root.resolve()).as_posix()
        except OSError:
            continue
    return None


async def _iter_papers(question: str, model: str | None, style: str, memory: str) -> AsyncIterator[dict[str, Any]]:
    yield _stage("papers", "Papers agent", "running", "arXiv and OpenAlex")
    yield {"type": "hint", "text": "Looking up the most cited arXiv paper for this topic."}
    try:
        paper = await papers_server.find_paper(question)
    except (httpx.HTTPError, OSError, LookupError, ValueError) as exc:
        yield _stage("papers", "Papers agent", "completed", type(exc).__name__)
        yield {"type": "token", "text": "I could not fetch an arXiv paper for that topic.", "channel": "answer"}
        return

    abs_url = paper.get("abs_url") or ""
    if abs_url.startswith("https://"):
        yield _evidence(
            InvestigationSource(
                source_id=abs_url,
                title=paper.get("title") or "arXiv paper",
                excerpt=_paper_excerpt(paper),
                origin="arXiv",
                url=abs_url,
            )
        )
    openalex_url = str(paper.get("openalex_url") or "")
    if openalex_url.startswith("https://"):
        citations = int(paper.get("citations") or 0)
        yield _evidence(
            InvestigationSource(
                source_id=openalex_url,
                title=f"{paper.get('title') or 'Paper'} citations",
                excerpt=f"{citations:,} citations on OpenAlex",
                origin="OpenAlex",
                url=openalex_url,
            )
        )
    for extra in paper.get("runners") or []:
        extra_url = extra.get("abs_url") or ""
        if not extra_url.startswith("https://"):
            continue
        yield _evidence(
            InvestigationSource(
                source_id=extra_url,
                title=extra.get("title") or extra_url,
                excerpt=f"{int(extra.get('citations') or 0):,} citations on OpenAlex",
                origin="arXiv",
                url=extra_url,
            )
        )
    saved = paper.get("pdf_saved") or "PDF not saved"
    yield _stage("papers", "Papers agent", "completed", saved)
    if paper.get("pdf_saved"):
        yield {"type": "hint", "text": f"Saved the PDF at {paper['pdf_saved']}."}
    else:
        yield {"type": "hint", "text": "The PDF could not be saved. The explanation uses the abstract."}

    del memory
    explanation = papers_server.fallback_explanation(paper, style)
    if papers_server.wants_linkedin_post(question):
        draft = papers_server.draft_linkedin_post(paper)
        explanation = (
            f"{explanation}\n\nLinkedIn draft:\n{draft}\n\n"
            "Posting needs a LinkedIn connection which is not set up yet."
        )
        yield _stage("linkedin", "LinkedIn", "completed", "Not connected")
    yield _stage("model", "Writer", "running", "abstract and PDF")
    yield {"type": "token", "text": explanation, "channel": "answer"}
    yield _stage("model", "Writer", "completed", model or "abstract and PDF")


def _paper_excerpt(paper: dict) -> str:
    citations = int(paper.get("citations") or 0)
    abstract = " ".join(str(paper.get("abstract") or "").split())
    prefix = f"{citations:,} citations. " if citations else ""
    return (prefix + abstract)[:240]


async def _iter_history(question: str) -> AsyncIterator[dict[str, Any]]:
    yield _stage("history", "History agent", "running", "Saved browser history on this computer")
    hits, stored = await asyncio.to_thread(search_history, question)
    yield {"type": "history_meta", "stored": stored}
    if not hits:
        detail = "None saved" if stored == 0 else "No match"
        yield _stage("history", "History agent", "completed", detail)
        return
    yield _stage("history", "History agent", "completed", f"{len(hits)} pages")
    for hit in hits:
        yield _evidence(
            InvestigationSource(
                source_id=hit["source_id"],
                title=hit["title"],
                excerpt=hit.get("excerpt", ""),
                origin=hit.get("origin") or "Browser history",
                url=hit.get("url") or "",
            )
        )


async def _iter_movies(question: str) -> AsyncIterator[dict[str, Any]]:
    kind = media_request(question) or "video"
    words = set(question.lower().split())
    catalog = bool(words & {"list", "lists", "all", "every", "show"})
    terms = [] if catalog and not media_terms(question) else media_terms(question)
    agent = {"video": "Movie agent", "audio": "Song agent", "image": "Image agent"}.get(kind, "Movie agent")
    origin = {"video": "Movie", "audio": "Song", "image": "Image"}.get(kind, "Movie")
    detail = " ".join(terms) or f"every {kind} file"
    yield _stage("movies", agent, "running", detail)
    yield {"type": "hint", "text": f"Looking on this computer for {detail}."}
    matches, total, stopped = await asyncio.to_thread(find_media, kind, terms, 80, catalog)
    if not matches:
        yield _stage("movies", agent, "completed", "None on this computer")
        return
    extra = f"{len(matches)} of {total}" if total > len(matches) else f"{len(matches)} found"
    yield _stage("movies", agent, "completed", extra)
    yield {"type": "catalog", "total": total, "shown": len(matches)}
    if stopped and total <= len(matches):
        yield {"type": "hint", "text": "The folder scan stopped before every folder was opened."}
    elif total > len(matches):
        yield {"type": "hint", "text": f"Showing {len(matches)} of {total}. Choose Play on one."}
    for item in matches:
        placed = _play_place(Path(item["path"]))
        if placed is None:
            continue
        root_id, relative = placed
        size = item["bytes"]
        if size >= 1024 * 1024 * 1024:
            label = f"{size / (1024 * 1024 * 1024):.1f} GB"
        elif size >= 1024 * 1024:
            label = f"{round(size / (1024 * 1024))} MB"
        else:
            label = f"{max(1, round(size / 1024))} KB"
        source = InvestigationSource(
            source_id=item["path"],
            title=item["name"],
            excerpt=label,
            origin=origin,
            play_root=root_id,
            play_path=relative,
        )
        yield _evidence(source)


async def _iter_local_files(question: str, deadline: float | None = None) -> AsyncIterator[dict[str, Any]]:
    terms = filename_terms(question)
    detail = ", ".join(terms) or "the words in your question"
    lowered = question.lower()
    cap = 1 if "best matching file" in lowered else 3 if "a few matching files" in lowered else 5
    yield _stage("search", "Searching your computer", "running", f"File names containing {detail}")
    yield {"type": "hint", "text": f"Looking through your folders for {detail}."}
    search = asyncio.create_task(asyncio.to_thread(find_by_name, terms, cap))
    ticks = 0
    while not search.done():
        await asyncio.sleep(1.5)
        if search.done():
            break
        ticks += 1
        yield {"type": "hint", "text": f"Still scanning folders… {ticks * 2}s. Matches will show up here as soon as they are found."}
    matches = await search
    if not matches:
        yield _stage("search", "Searching your computer", "completed", "No matching file names")
        yield {"type": "block", "text": f"[File search] No file names matched: {detail}"}
        return
    names = ", ".join(item["name"] for item in matches)
    yield _stage("search", "Searching your computer", "completed", names)
    yield {"type": "hint", "text": f"Found {len(matches)} file{'s' if len(matches) != 1 else ''}. Checking each file type before reading."}
    blocks = [f"[File search] filename terms: {detail}"]
    for index, item in enumerate(matches, start=1):
        stage_id = f"read-{index}"
        yield _stage(stage_id, f"Reading {item['name']}", "running", item["type"])
        yield {"type": "hint", "text": f"{item['name']} is a {item['type']}. Opening it with the matching reader."}
        block, source = await asyncio.to_thread(_read_match, item)
        blocks.append(block)
        yield _evidence(source)
        yield _stage(stage_id, f"Reading {item['name']}", "completed", item["type"])
    yield {"type": "block", "text": "\n\n".join(blocks)}


def _read_match(item: dict) -> tuple[str, InvestigationSource]:
    try:
        if item["kind"] == "document":
            text = document_server.extract_path(Path(item["path"]))
            origin = "Document"
            excerpt = text[:400]
            block = f"Found {item['name']} ({item['type']}) at {item['path']}\n[Document:{item['type']}]\n{text[:2500]}"
        elif item["kind"] == "spreadsheet":
            data = spreadsheet_server.read_path(Path(item["path"]))
            origin = "Spreadsheet"
            excerpt = f"columns={data['columns']}"
            block = f"[Spreadsheet:{item['type']}]\n{data['path']} columns={data['columns']} rows={data['rows']}"
        else:
            origin = "File"
            excerpt = f"Found the file, but {item['type']} cannot be read."
            block = excerpt
    except (OSError, ValueError, ImportError) as exc:
        origin = "File"
        excerpt = str(exc)
        block = f"Could not read {item['name']}: {exc}"
    source = InvestigationSource(
        source_id=item["path"],
        title=f"{item['name']} ({item['type']})",
        excerpt=excerpt[:240],
        origin=origin,
    )
    return block, source


def _preface(sources: list[InvestigationSource]) -> str:
    lines = ["Sources used:"]
    if not sources:
        lines.append("- None. The model had no tool evidence.")
        return "\n".join(lines)
    seen: set[str] = set()
    for source in sources:
        label = f"- [{source.origin or 'Unknown'}] {source.title}"
        if label in seen:
            continue
        seen.add(label)
        lines.append(label)
    return "\n".join(lines)
