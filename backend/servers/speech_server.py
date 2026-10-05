"""Turn a short recording into text on this computer.

Chrome's cloud speech service often fails with a network error when the
connection is inspected. The mic then records here and this model reads it.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from core.config import settings

_model = None
_lock = threading.Lock()
ALLOWED = {"en", "hi", "bn", "mr", "ta", "te", "kn", "ml", "ja"}
# Whisper invents these on silence or room noise. A real question is longer than the phrase.
HALLUCINATIONS = {
    "thanks for watching",
    "thank you for watching",
    "thanks for listening",
    "thank you",
    "thanks",
    "subscribe",
    "take care",
    "take care of it",
    "you",
    "bye",
    "hmm",
    "so",
}


def _root() -> Path:
    path = Path(settings.whisper_root or "/models")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            import faster_whisper.audio as whisper_audio
            from faster_whisper import WhisperModel

            original_open = whisper_audio.av.open

            def open_audio(*args, **kwargs):
                kwargs.pop("metadata_errors", None)
                return original_open(*args, **kwargs)

            whisper_audio.av.open = open_audio
            _model = WhisperModel("base", device="cpu", compute_type="int8", download_root=str(_root()))
    return _model


def transcribe_bytes(content: bytes, suffix: str, language: str) -> str:
    code = language.lower()[:2]
    if code not in ALLOWED:
        code = "en"
    with tempfile.NamedTemporaryFile(suffix=suffix or ".webm", delete=False) as handle:
        handle.write(content)
        path = handle.name
    try:
        segments, _info = _load().transcribe(
            path,
            language=code,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        parts = []
        for segment in segments:
            text = segment.text.strip()
            if not text or segment.no_speech_prob >= 0.5 or segment.avg_logprob < -1.0:
                continue
            parts.append(text)
        spoken = " ".join(parts).strip()
        plain = "".join(ch for ch in spoken.lower() if ch.isalnum() or ch.isspace()).strip()
        if plain in HALLUCINATIONS:
            return ""
        return spoken
    finally:
        Path(path).unlink(missing_ok=True)
