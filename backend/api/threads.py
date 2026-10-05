"""Session threads: several topics, each with memory and checkpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gateway import threads

router = APIRouter(prefix="/api/v1", tags=["threads"])


class ThreadCreate(BaseModel):
    title: str = Field(default="New thread", max_length=80)


class RestoreRequest(BaseModel):
    checkpoint_id: str = Field(min_length=4, max_length=80)


@router.get("/threads")
async def list_threads() -> dict:
    return {"threads": threads.list_threads()}


@router.post("/threads")
async def create_thread(payload: ThreadCreate) -> dict:
    return threads.open_thread(payload.title)


@router.get("/threads/{thread_id}")
async def read_thread(thread_id: str) -> dict:
    item = threads.get_thread(thread_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That thread is not in this session.")
    return item


@router.post("/threads/{thread_id}/restore")
async def restore_thread(thread_id: str, payload: RestoreRequest) -> dict:
    item = threads.restore(thread_id, payload.checkpoint_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That checkpoint is not on this thread.")
    return item
