"""arXiv and OpenAlex paper specialist.

arXiv search and PDF download use the public export API. Citation counts
come from OpenAlex, which does not need an API key. PDFs are stored under
the gitignored papers directory.
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from core.config import settings

NAME = "papers"
TOOLS = ["papers.search", "papers.download"]

_ATOM = "{http://www.w3.org/2005/Atom}"
_UA = "Asteria/0.1 (mailto:asteria@localhost)"
_MAX_PDF = 40 * 1024 * 1024
_ARXIV_ID = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|arxiv[:/]|10\.48550/arxiv\.)"
    r"(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?",
    re.I,
)
_WEAK_TOPICS = {"it", "this", "that", "one", "topic", "paper", "papers", "a", "an", "the"}


def papers_root() -> Path:
    if settings.papers_root:
        path = Path(settings.papers_root)
    else:
        path = Path(__file__).resolve().parents[2] / "data" / "papers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_paper_query(question: str) -> bool:
    """True for arXiv, citation, and famous-paper questions."""
    text = " ".join(question.lower().split())
    if not text:
        return False
    from servers.file_server import media_request

    if media_request(question):
        return False
    from mcp.gmail_client import is_gmail_query

    if is_gmail_query(question) and "arxiv" not in text and "linkedin" not in text and "linked in" not in text:
        return False
    if any(word in text for word in ("newspaper", "wallpaper", "paperwork", "paper trail")):
        return False
    if any(
        hint in text
        for hint in (
            "arxiv",
            "research paper",
            "research papers",
            "famous paper",
            "famous papers",
            "citation count",
            "most cited",
            "highly cited",
        )
    ):
        return True
    if re.search(r"\bcitations?\b", text) and re.search(r"\b(paper|papers|arxiv|topic)\b", text):
        return True
    if re.search(r"\bpapers?\b", text) and re.search(
        r"\b(on|about|regarding|topic|download|explain|famous|cite|cited|arxiv)\b",
        text,
    ):
        return True
    if wants_linkedin_post(question) and not any(
        word in text for word in ("weather", "forecast", "temperature", "humidity", "gmail", "inbox", "email", "movie", "movies", "song", "songs")
    ):
        if re.search(r"\b(explain|summarize|summary|download|paper|papers|arxiv|citation|citations|famous)\b", text):
            return True
    return False


def wants_linkedin_post(question: str) -> bool:
    text = question.lower()
    return "linkedin" in text or "linked in" in text


def topic_from_question(question: str) -> str:
    cleaned = _strip_instructions(question)
    if len(cleaned) < 3 or cleaned.lower() in _WEAK_TOPICS:
        lighter = re.sub(
            r"\b(please|post|publish|share|linkedin|linked in|download|explain)\b",
            " ",
            question,
            flags=re.I,
        )
        lighter = re.sub(r"\s+", " ", lighter).strip(" .?:-")
        return lighter or question.strip()
    return cleaned


def draft_linkedin_post(paper: dict) -> str:
    year = f" ({paper['year']})" if paper.get("year") else ""
    citations = int(paper.get("citations") or 0)
    cite = f"{citations:,} citations on OpenAlex" if citations else "listed on OpenAlex"
    summary = _sentences(paper.get("abstract") or "", 2)
    body = summary or "The abstract is the best short account of what the authors set out to show."
    text = (
        f"\"{paper.get('title') or 'This paper'}\"{year} by {paper.get('authors') or 'the authors'} "
        f"is a highly cited paper on this topic ({cite}).\n\n"
        f"{body}\n\n"
        f"Read it: {paper.get('abs_url') or ''}"
    )
    return text.strip()[:2900]


def display_pdf_path(path: Path) -> str:
    return f"data/papers/{path.name}"


async def _quiet(task):
    try:
        return await task
    except (httpx.HTTPError, OSError, ValueError):
        return []


async def find_paper(question: str) -> dict:
    topic = topic_from_question(question)
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True, headers={"User-Agent": _UA}) as client:
        arxiv_hits, works = await asyncio.gather(
            _quiet(_arxiv_search(client, topic)),
            _quiet(_openalex_search(client, topic)),
        )
        await _fill_citations(client, arxiv_hits, works)
        await _attach_famous(client, arxiv_hits, works)
        ranked = _rank_papers(arxiv_hits, [], topic)
        if not ranked:
            raise LookupError(f"No arXiv paper matched {topic}.")
        chosen = ranked[0]
        if not chosen.get("abstract"):
            await asyncio.sleep(3)
            meta = await _arxiv_by_id(client, chosen["arxiv_id"])
            chosen = _merge(chosen, meta)
        paper = _with_https(chosen)
        path = await _download_pdf(client, paper["arxiv_id"])
        paper["pdf_path"] = str(path) if path else ""
        paper["pdf_saved"] = display_pdf_path(path) if path else ""
        paper["pdf_excerpt"] = _pdf_excerpt(path) if path else ""
        paper["runners"] = [_with_https(item) for item in ranked[1:3] if item.get("arxiv_id")]
        paper["topic"] = topic
        return paper


def evidence_text(paper: dict) -> str:
    lines = [
        "[arXiv]",
        f"Title: {paper.get('title') or ''}",
        f"Authors: {paper.get('authors') or ''}",
        f"Year: {paper.get('year') or ''}",
        f"Citations on OpenAlex: {int(paper.get('citations') or 0)}",
        f"arXiv: {paper.get('abs_url') or ''}",
        f"PDF saved: {paper.get('pdf_saved') or 'not saved'}",
        "",
        "Abstract:",
        paper.get("abstract") or "(no abstract returned)",
    ]
    if paper.get("pdf_excerpt"):
        lines.extend(["", "Text extracted from the PDF:", paper["pdf_excerpt"][:4000]])
    runners = paper.get("runners") or []
    if runners:
        lines.append("")
        lines.append("Other highly cited matches:")
        for item in runners:
            lines.append(
                f"- {item.get('title')} ({int(item.get('citations') or 0)} citations) {item.get('abs_url') or ''}"
            )
    return "\n".join(lines)[:12000]


def fallback_explanation(paper: dict, style: str = "clear") -> str:
    abstract_count, excerpt_count = {"brief": (1, 0), "clear": (2, 1), "full": (3, 2)}.get(style, (2, 1))
    citations = int(paper.get("citations") or 0)
    cite = f"OpenAlex lists {citations:,} citations." if citations else "OpenAlex did not return a citation count."
    abstract = _sentences(paper.get("abstract") or "", abstract_count)
    excerpt = _sentences(paper.get("pdf_excerpt") or "", excerpt_count) if excerpt_count else ""
    parts = [
        f"{paper.get('title')} by {paper.get('authors')} ({paper.get('year') or 'year not listed'}). {cite}",
        "",
        abstract or "The abstract was not available.",
    ]
    if excerpt:
        parts.extend(["", f"From the PDF: {excerpt}"])
    if paper.get("abs_url"):
        parts.extend(["", f"Paper: {paper['abs_url']}"])
    if paper.get("pdf_saved"):
        parts.append(f"Saved PDF: {paper['pdf_saved']}")
    return "\n".join(parts)


def _strip_instructions(question: str) -> str:
    text = re.sub(
        r"\b(please|can you|could you|would you|check|find|look up|search for|search|download|explain|summarize|write|draft|create|make|post|publish|share|linkedin|linked in|a famous papers|a famous paper|famous papers|famous paper|research papers|research paper|papers|paper|by topic|and citation|citations|citation|cited|arxiv|the pdf|pdf|about)\b",
        " ",
        question,
        flags=re.I,
    )
    text = re.sub(r"[^A-Za-z0-9 .:'\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    text = re.sub(r"\b(and|it|on|to|for|me|my|this|that|also|then|just)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    text = re.sub(r"^(on|about|for|the|a|an)\s+", "", text, flags=re.I)
    return text.strip()


def _sentences(text: str, count: int) -> str:
    cleaned = " ".join(text.split())
    if not cleaned or count <= 0:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    kept: list[str] = []
    for part in parts:
        if len(part) < 40:
            continue
        if re.search(
            r"permission to reproduce|all rights reserved|provided proper attribution|copyright|published as a conference paper",
            part,
            re.I,
        ):
            continue
        if len(part) > 500:
            continue
        kept.append(part)
        if len(kept) >= count:
            break
    return " ".join(kept)[:700]


def _abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    slots: list[tuple[int, str]] = []
    for word, indexes in inverted.items():
        for index in indexes or []:
            if isinstance(index, int):
                slots.append((index, word))
    slots.sort()
    return " ".join(word for _, word in slots)


def _arxiv_id_from(value: str) -> str:
    match = _ARXIV_ID.search(value or "")
    return match.group(1) if match else ""


def _work_arxiv_id(work: dict) -> str:
    """Trust only the DOI. OpenAlex locations sometimes point at a different paper."""
    ids = work.get("ids") or {}
    blobs = [str(work.get("doi") or "")]
    if isinstance(ids, dict):
        blobs.append(str(ids.get("doi") or ""))
    for blob in blobs:
        found = _arxiv_id_from(blob)
        if found:
            return found
    return ""


def _authors(work: dict) -> str:
    names = []
    for person in work.get("authorships") or []:
        name = (person.get("author") or {}).get("display_name") or ""
        if name:
            names.append(name)
    if not names:
        return ""
    if len(names) <= 3:
        return ", ".join(names)
    return ", ".join(names[:3]) + ", et al."


def _normalize_work(work: dict) -> dict:
    arxiv_id = _work_arxiv_id(work)
    openalex = (work.get("ids") or {}).get("openalex") or work.get("id") or ""
    return {
        "title": " ".join(str(work.get("display_name") or "").split()),
        "authors": _authors(work),
        "year": str(work.get("publication_year") or ""),
        "citations": int(work.get("cited_by_count") or 0),
        "abstract": _abstract(work.get("abstract_inverted_index")),
        "arxiv_id": arxiv_id,
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
        "openalex_url": str(openalex),
    }


def _https(url: str) -> str:
    raw = (url or "").strip()
    if raw.startswith("http://"):
        raw = "https://" + raw[len("http://") :]
    return raw if raw.startswith("https://") else ""


def _with_https(paper: dict) -> dict:
    item = dict(paper)
    arxiv_id = item.get("arxiv_id") or ""
    item["abs_url"] = _https(item.get("abs_url") or "") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")
    item["openalex_url"] = _https(item.get("openalex_url") or "")
    return item


def _rank_papers(arxiv_hits: list[dict], works: list[dict], topic: str) -> list[dict]:
    pool: list[dict] = []
    seen: set[str] = set()
    for hit in arxiv_hits:
        arxiv_id = hit.get("arxiv_id") or ""
        if not arxiv_id or arxiv_id in seen:
            continue
        seen.add(arxiv_id)
        pool.append(hit)
    for work in works:
        arxiv_id = work.get("arxiv_id") or ""
        if not arxiv_id or arxiv_id in seen:
            continue
        seen.add(arxiv_id)
        pool.append(work)
    needle = re.sub(r"[^a-z0-9]+", " ", topic.lower()).strip()

    def sort_key(row: dict) -> tuple[int, int]:
        title = re.sub(r"[^a-z0-9]+", " ", (row.get("title") or "").lower()).strip()
        titled = 1 if needle and (needle in title or title in needle) else 0
        return (int(row.get("citations") or 0), titled)

    pool.sort(key=sort_key, reverse=True)
    return pool


async def _fill_citations(client: httpx.AsyncClient, arxiv_hits: list[dict], works: list[dict]) -> None:
    known = {work["arxiv_id"]: work for work in works if work.get("arxiv_id")}
    missing = [hit["arxiv_id"] for hit in arxiv_hits if hit.get("arxiv_id") and hit["arxiv_id"] not in known]
    found = await _openalex_by_arxiv(client, missing[:12]) if missing else {}
    for hit in arxiv_hits:
        match = known.get(hit.get("arxiv_id") or "") or found.get(hit.get("arxiv_id") or "")
        if not match:
            continue
        hit["citations"] = int(match.get("citations") or 0)
        if match.get("openalex_url"):
            hit["openalex_url"] = match["openalex_url"]
        if not hit.get("abstract") and match.get("abstract"):
            hit["abstract"] = match["abstract"]


def _merge(chosen: dict, meta: dict | None) -> dict:
    paper = dict(chosen)
    if not meta:
        return paper
    if meta.get("title"):
        paper["title"] = meta["title"]
    if meta.get("authors"):
        paper["authors"] = meta["authors"]
    if meta.get("year"):
        paper["year"] = meta["year"]
    if meta.get("abstract"):
        paper["abstract"] = meta["abstract"]
    if meta.get("abs_url"):
        paper["abs_url"] = meta["abs_url"]
    return paper


async def _openalex_search(client: httpx.AsyncClient, topic: str) -> list[dict]:
    response = await client.get(
        "https://api.openalex.org/works",
        params={"search": topic, "per-page": 20},
    )
    response.raise_for_status()
    works = []
    for item in response.json().get("results") or []:
        normalized = _normalize_work(item)
        if normalized["title"]:
            works.append(normalized)
    return works


def _arxiv_query(topic: str) -> str:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-]*", topic)
    if not words:
        return "all:science"
    if len(words) >= 4:
        phrase = " ".join(words[:12]).replace('"', "")
        return f'ti:"{phrase}" OR all:"{phrase}"'
    return " AND ".join(f"all:{word}" for word in words[:6])


async def _arxiv_search(client: httpx.AsyncClient, topic: str) -> list[dict]:
    response = await client.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": _arxiv_query(topic),
            "start": 0,
            "max_results": 10,
            "sortBy": "relevance",
            "sortOrder": "descending",
        },
    )
    response.raise_for_status()
    return _parse_arxiv(response.text)


def _norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _titles_close(left: str, right: str) -> bool:
    first = _norm_title(left)
    second = _norm_title(right)
    return bool(first and second and first == second)


def _copy_counts(hit: dict, work: dict) -> None:
    hit["citations"] = max(int(hit.get("citations") or 0), int(work.get("citations") or 0))
    if work.get("openalex_url"):
        hit["openalex_url"] = work["openalex_url"]
    if not hit.get("authors") and work.get("authors"):
        hit["authors"] = work["authors"]


async def _arxiv_by_title(client: httpx.AsyncClient, title: str) -> dict | None:
    safe = title.replace('"', "").replace("\\", "")
    response = await client.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": f'ti:"{safe}"',
            "start": 0,
            "max_results": 3,
            "sortBy": "relevance",
            "sortOrder": "descending",
        },
    )
    response.raise_for_status()
    for hit in _parse_arxiv(response.text):
        if _titles_close(hit.get("title") or "", title):
            return hit
    return None


async def _attach_famous(client: httpx.AsyncClient, arxiv_hits: list[dict], works: list[dict]) -> None:
    """Add the most cited OpenAlex matches that arXiv can confirm."""
    by_id = {hit["arxiv_id"]: hit for hit in arxiv_hits if hit.get("arxiv_id")}
    lookups = 0
    famous = sorted(works, key=lambda work: int(work.get("citations") or 0), reverse=True)
    for work in famous:
        title = work.get("title") or ""
        matched = next((hit for hit in arxiv_hits if _titles_close(hit.get("title") or "", title)), None)
        if matched:
            _copy_counts(matched, work)
            continue
        arxiv_id = work.get("arxiv_id") or ""
        if arxiv_id and arxiv_id in by_id:
            _copy_counts(by_id[arxiv_id], work)
            continue
        if arxiv_id:
            row = dict(work)
            row["abs_url"] = f"https://arxiv.org/abs/{arxiv_id}"
            arxiv_hits.append(row)
            by_id[arxiv_id] = row
            continue
        if lookups >= 3 or int(work.get("citations") or 0) < 200 or len(title) < 12:
            continue
        lookups += 1
        await asyncio.sleep(3)
        try:
            hit = await _arxiv_by_title(client, title)
        except (httpx.HTTPError, OSError, ValueError):
            continue
        if not hit or not hit.get("arxiv_id"):
            continue
        existing = by_id.get(hit["arxiv_id"])
        if existing:
            _copy_counts(existing, work)
            continue
        _copy_counts(hit, work)
        arxiv_hits.append(hit)
        by_id[hit["arxiv_id"]] = hit


async def _openalex_by_arxiv(client: httpx.AsyncClient, arxiv_ids: list[str]) -> dict[str, dict]:
    modern = [arxiv_id for arxiv_id in arxiv_ids if "/" not in arxiv_id]
    if not modern:
        return {}
    dois = "|".join(f"10.48550/arxiv.{arxiv_id}" for arxiv_id in modern)
    try:
        response = await client.get(
            "https://api.openalex.org/works",
            params={"filter": f"doi:{dois}", "per-page": max(len(modern), 1)},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return {}
    found: dict[str, dict] = {}
    for item in response.json().get("results") or []:
        normalized = _normalize_work(item)
        if normalized.get("arxiv_id"):
            found[normalized["arxiv_id"]] = normalized
    return found


async def _arxiv_by_id(client: httpx.AsyncClient, arxiv_id: str) -> dict | None:
    response = await client.get(
        "https://export.arxiv.org/api/query",
        params={"id_list": arxiv_id, "max_results": 1},
    )
    response.raise_for_status()
    hits = _parse_arxiv(response.text)
    return hits[0] if hits else None


def _parse_arxiv(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    papers = []
    for entry in root.findall(f"{_ATOM}entry"):
        title = " ".join((entry.findtext(f"{_ATOM}title") or "").split())
        if not title or title.lower() == "error":
            continue
        summary = " ".join((entry.findtext(f"{_ATOM}summary") or "").split())
        year = (entry.findtext(f"{_ATOM}published") or "")[:4]
        names = []
        for author in entry.findall(f"{_ATOM}author"):
            name = author.findtext(f"{_ATOM}name") or ""
            if name:
                names.append(name)
        if len(names) > 3:
            authors = ", ".join(names[:3]) + ", et al."
        else:
            authors = ", ".join(names)
        raw_id = entry.findtext(f"{_ATOM}id") or ""
        arxiv_id = _arxiv_id_from(raw_id)
        for link in entry.findall(f"{_ATOM}link"):
            href = link.attrib.get("href") or ""
            if not arxiv_id:
                arxiv_id = _arxiv_id_from(href)
        abs_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
        if not arxiv_id:
            continue
        papers.append(
            {
                "title": title,
                "authors": authors,
                "year": year,
                "citations": 0,
                "abstract": summary,
                "arxiv_id": arxiv_id,
                "abs_url": abs_url,
                "openalex_url": "",
            }
        )
    return papers


def _pdf_file(arxiv_id: str) -> Path:
    safe = arxiv_id.replace("/", "_")
    return papers_root() / f"{safe}.pdf"


async def _download_pdf(client: httpx.AsyncClient, arxiv_id: str) -> Path | None:
    destination = _pdf_file(arxiv_id)
    if destination.is_file() and destination.stat().st_size > 1000:
        with destination.open("rb") as handle:
            head = handle.read(5)
        if head.startswith(b"%PDF"):
            return destination
    response = await client.get(f"https://arxiv.org/pdf/{arxiv_id}.pdf")
    if response.status_code >= 400:
        return None
    content = response.content
    if len(content) < 1000 or len(content) > _MAX_PDF or not content.startswith(b"%PDF"):
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def _pdf_excerpt(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages[:6]]
    except Exception:
        return ""
    return "\n".join(pages)[:6000]
