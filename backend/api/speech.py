import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from servers.speech_server import transcribe_bytes

router = APIRouter(prefix="/api/v1", tags=["speech"])
logger = logging.getLogger(__name__)


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("en")) -> dict[str, str]:
    content = await audio.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That recording is too long.")
    if len(content) < 400:
        return {"text": ""}
    suffix = Path(audio.filename or "speech.webm").suffix or ".webm"
    try:
        text = await asyncio.to_thread(transcribe_bytes, content, suffix, language)
    except Exception as exc:
        logger.exception("transcription failed")
        raise HTTPException(status_code=503, detail="This computer recorded the question but could not turn it into text.") from exc
    return {"text": text}
