from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from library.store import get_item, item_file, list_items, save_upload, search, transcript_for

router = APIRouter(prefix="/api/v1/library", tags=["library"])


@router.get("/items")
async def items() -> dict:
    return {"items": list_items_public()}


@router.post("/items")
async def create_item(
    file: UploadFile = File(...),
    kind: str = Form("file"),
    source: str = Form("upload"),
    note: str = Form(""),
    transcript: str = Form(""),
) -> dict:
    content = await file.read()
    try:
        item = save_upload(
            filename=file.filename or "upload",
            content=content,
            mime=file.content_type or "",
            kind=kind,
            source=source if source in {"upload", "capture"} else "upload",
            note=note,
            transcript=transcript,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


@router.get("/search")
async def find(q: str) -> dict:
    return {"results": search(q)}


@router.get("/items/{item_id}")
async def read_item(item_id: str) -> dict:
    item = _public(item_id)
    item["transcript"] = transcript_for(item_id)
    return item


@router.get("/items/{item_id}/file")
async def read_file(item_id: str) -> FileResponse:
    item = get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    path = item_file(item)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type=item["mime"], filename=item["original_name"])


def list_items_public() -> list[dict]:
    public = []
    for item in list_items():
        copy = dict(item)
        copy.pop("embedding", None)
        public.append(copy)
    return public


def _public(item_id: str) -> dict:
    item = get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    copy = dict(item)
    copy.pop("embedding", None)
    return copy
