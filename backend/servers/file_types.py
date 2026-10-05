"""Detect a file type so the right MCP reader can open it."""

from __future__ import annotations

from pathlib import Path

DOCUMENT_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".rtf"}
SPREADSHEET_SUFFIXES = {".csv", ".xlsx"}


def file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in DOCUMENT_SUFFIXES:
        return "document"
    if suffix in SPREADSHEET_SUFFIXES:
        return "spreadsheet"
    return "unsupported"


def type_label(path: Path) -> str:
    suffix = path.suffix.lower()
    labels = {
        ".pdf": "PDF document",
        ".docx": "Word document",
        ".txt": "text file",
        ".md": "Markdown document",
        ".rtf": "rich text document",
        ".csv": "CSV spreadsheet",
        ".xlsx": "Excel spreadsheet",
    }
    return labels.get(suffix, f"unsupported type {suffix or 'with no extension'}")
