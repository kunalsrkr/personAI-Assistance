"""Builds a stable vector for library search. Uses Ollama when an embed model is installed."""

from __future__ import annotations

import hashlib
import math
import re

import httpx

from core.config import settings

DIM = 256


def hash_embed(text: str) -> list[float]:
    vector = [0.0] * DIM
    tokens = re.findall(r"[a-z0-9]{2,}", text.lower())
    for token in tokens:
        slot = int(hashlib.md5(token.encode()).hexdigest(), 16) % DIM
        vector[slot] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def ollama_embed(text: str, model: str) -> list[float] | None:
    base = settings.ollama_base_url.rstrip("/")
    try:
        response = httpx.post(f"{base}/api/embed", json={"model": model, "input": text[:4000]}, timeout=30.0)
        if response.status_code < 400:
            vectors = response.json().get("embeddings") or []
            if vectors and isinstance(vectors[0], list):
                return [float(value) for value in vectors[0]]
    except httpx.HTTPError:
        return None
    return None


def embedder_name() -> tuple[str, str | None]:
    try:
        response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=4.0)
        names = [item.get("name", "") for item in response.json().get("models") or []]
    except httpx.HTTPError:
        names = []
    for candidate in ("nomic-embed-text", "mxbai-embed-large", "all-minilm"):
        match = next((name for name in names if name.split(":")[0] == candidate), "")
        if match and ollama_embed("library", match):
            return f"ollama:{match}", match
    return "hash-v1", None


def embed_text(text: str, embedder: str) -> list[float]:
    if embedder.startswith("ollama:"):
        vector = ollama_embed(text, embedder.split(":", 1)[1])
        if vector:
            return vector
    return hash_embed(text)


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
