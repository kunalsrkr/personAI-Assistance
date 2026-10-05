"""Document MCP server. Reads a file only after its type is known."""

from __future__ import annotations

from pathlib import Path

from servers.file_server import list_files, read_file
from servers.file_types import DOCUMENT_SUFFIXES
from servers.workspace import allowed_file, safe_path

NAME = "document"
TOOLS = ["document.extract_text", "document.search"]
TEXT_SUFFIXES = {".txt", ".md", ".csv"}


def extract_path(path: Path) -> str:
    target = allowed_file(path)
    suffix = target.suffix.lower()
    if suffix not in DOCUMENT_SUFFIXES:
        raise ValueError(f"Unsupported document type: {suffix or 'unknown'}")
    if suffix == ".pdf":
        return _pdf_text(target)
    if suffix == ".docx":
        return _docx_text(target)
    if suffix == ".rtf":
        return _rtf_text(target)
    return target.read_text(encoding="utf-8", errors="ignore")[:8000]


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages[:8]]
    return "\n".join(pages)[:8000]


def _docx_text(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    return text[:8000]


def _rtf_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    stripped = raw.replace("\\par", "\n")
    return stripped[:8000]


def extract_text(relative_path: str) -> str:
    path = safe_path(relative_path)
    if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix.lower() not in DOCUMENT_SUFFIXES:
        raise ValueError(f"Unsupported document type: {path.suffix or 'unknown'}")
    return extract_path(path)[:8000]


def search(query: str) -> list[dict]:
    needle = query.lower()
    hits = []
    for item in list_files():
        if not item["path"].lower().endswith(tuple(TEXT_SUFFIXES)):
            continue
        text = read_file(item["path"])
        index = text.lower().find(needle)
        if index < 0:
            continue
        start = max(0, index - 80)
        hits.append({"path": item["path"], "excerpt": text[start : start + 240]})
    return hits[:10]
