import asyncio
import json
import time
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from gateway.clarify import apply_choice, guidance_steps, review_step
from gateway.threads import context_for, note_investigation, open_thread, record
from servers.browser_history import wants_browser_history
from servers.file_server import media_request
from servers.papers_server import is_paper_query
from gateway.memory import remember
from gateway.live import LiveRun
from gateway.router import iter_question
from mcp.gmail_client import list_models
from models.schemas import (
    ChatRequest,
    ChatResponse,
    ChoiceRequest,
    ClarifyChoice,
    Investigation,
    InvestigationCreate,
    InvestigationSource,
    InvestigationStage,
    InvestigationStatus,
    utcnow,
)
from models.store import store

router = APIRouter(prefix="/api/v1", tags=["investigations"])
runs: dict[UUID, LiveRun] = {}


def _apply(item: Investigation, event: dict) -> None:
    kind = event.get("type")
    if kind == "stage":
        stage = InvestigationStage(**event["stage"])
        updated: list[InvestigationStage] = []
        replaced = False
        for existing in item.stages:
            if existing.id == stage.id:
                updated.append(stage)
                replaced = True
            else:
                updated.append(existing)
        if not replaced:
            updated.append(stage)
        item.stages = updated
    elif kind == "evidence":
        source = InvestigationSource(**event["source"])
        if not any(existing.source_id == source.source_id for existing in item.sources):
            item.sources.append(source)
        item.step_count = len(item.sources)
    elif kind == "token":
        if event.get("channel") == "think":
            item.thinking += event["text"]
        else:
            item.final_answer = (item.final_answer or "") + event["text"]
    elif kind == "hint":
        item.hint = event["text"]


async def _ask(
    item: Investigation,
    run: LiveRun,
    step: dict,
    index: int,
    total: int,
    keep_running: bool = False,
) -> tuple[str, str]:
    if not keep_running:
        item.status = InvestigationStatus.APPROVAL
    item.clarify_prompt = step["prompt"]
    item.clarify_choices = [ClarifyChoice(**choice) for choice in step["choices"]]
    item.hint = step["prompt"]
    store.save(item)
    run.publish(
        {
            "type": "clarify",
            "prompt": step["prompt"],
            "choices": step["choices"],
            "step": index,
            "total": total,
            "seconds": step.get("seconds", 20),
        }
    )
    try:
        await asyncio.wait_for(run.choice.wait(), timeout=step.get("seconds", 20))
    except TimeoutError:
        run.selected = step["choices"][0]["id"]
        run.publish({"type": "hint", "text": "No choice in time, so the first option was used."})
    chosen = run.selected or step["choices"][0]["id"]
    note = run.note
    run.selected = None
    run.note = ""
    run.choice = asyncio.Event()
    return chosen, note


async def _worker(
    item: Investigation,
    run: LiveRun,
    query: str,
    model: str | None,
    time_limit: int,
    style: str,
    skip_guidance: bool = False,
) -> None:
    active_query = query
    if not skip_guidance and not media_request(query) and not wants_browser_history(query) and not is_paper_query(query):
        steps = guidance_steps(query)
        for index, step in enumerate(steps, start=1):
            chosen, note = await _ask(item, run, step, index, len(steps))
            active_query = apply_choice(active_query, chosen, note)
    item.status = InvestigationStatus.RUNNING
    item.deadline_at = utcnow() + timedelta(seconds=time_limit)
    item.hint = "Working. If this runs long, it stays in the session and you can ask the next question."
    store.save(item)
    run.publish({"type": "hint", "text": item.hint})
    run.publish({"type": "clock", "seconds": time_limit, "deadline": item.deadline_at.isoformat()})
    deadline_box = [time.monotonic() + time_limit]

    async def _note_if_slow() -> None:
        try:
            await asyncio.wait_for(run.finished.wait(), timeout=time_limit)
        except TimeoutError:
            if not run.finished.is_set():
                item.hint = "Still working. You can ask the next question."
                store.save(item)
                run.publish({"type": "park", "text": item.hint})

    asyncio.create_task(_note_if_slow())

    async def steer(step: dict) -> tuple[str, str]:
        pause = int(step.get("seconds", 15))
        item.deadline_at = (item.deadline_at or utcnow()) + timedelta(seconds=pause)
        store.save(item)
        run.publish({"type": "clock", "seconds": time_limit, "deadline": item.deadline_at.isoformat()})
        started = time.monotonic()
        chosen, note = await _ask(item, run, step, 1, 1, keep_running=True)
        waited = time.monotonic() - started
        unused = max(0.0, pause - waited)
        if item.deadline_at is not None:
            item.deadline_at -= timedelta(seconds=unused)
        deadline_box[0] += waited
        store.save(item)
        run.publish({"type": "clock", "seconds": time_limit, "deadline": item.deadline_at.isoformat() if item.deadline_at else ""})
        item.status = InvestigationStatus.RUNNING
        return chosen, note

    try:
        async for event in iter_question(
            active_query,
            model,
            deadline=deadline_box[0],
            style=style,
            steer=steer,
            deadline_box=deadline_box,
            memory=context_for(item.thread_id),
        ):
            _apply(item, event)
            store.save(item)
            run.publish(event)
        item.status = InvestigationStatus.COMPLETED
        item.confidence = 0.7 if item.sources else 0.3
        item.hint = "Answer ready."
        remember(query, item.final_answer or "")
        if item.thread_id:
            record(item.thread_id, query, item.final_answer or "", str(item.id))
    except Exception as exc:
        item.hint = f"Finished with a tool problem ({type(exc).__name__}). Showing what was already found."
        item.status = InvestigationStatus.COMPLETED
        if not item.final_answer:
            item.final_answer = item.hint
        elif item.hint not in item.final_answer:
            item.final_answer = f"{item.final_answer}\n\n{item.hint}"
        run.publish({"type": "hint", "text": item.hint})
        if item.thread_id and item.final_answer:
            record(item.thread_id, query, item.final_answer, str(item.id))
    item.completed_at = utcnow()
    review = review_step(query)
    item.clarify_prompt = review["prompt"]
    item.clarify_choices = [ClarifyChoice(**choice) for choice in review["choices"]]
    store.save(item)
    run.publish(
        {
            "type": "done",
            "status": item.status,
            "final_answer": item.final_answer,
            "thinking": item.thinking,
            "hint": item.hint,
            "sources": [source.model_dump() for source in item.sources],
            "stages": [stage.model_dump() for stage in item.stages],
            "review_prompt": review["prompt"],
            "review_choices": review["choices"],
        }
    )
    run.finished.set()


def start_investigation(
    query: str,
    model: str | None = None,
    time_limit: int = 45,
    style: str = "clear",
    skip_guidance: bool = False,
    thread_id: str = "",
) -> Investigation:
    thread = open_thread(query[:72], thread_id)
    item = store.create(InvestigationCreate(query=query, model=model, time_limit=time_limit, style=style))
    item.status = InvestigationStatus.RUNNING
    item.time_limit = time_limit
    item.iteration = 1
    item.thread_id = thread["id"]
    item.hint = "The orchestrator is choosing agents for this thread."
    note_investigation(thread["id"], str(item.id))
    store.save(item)
    run = LiveRun()
    runs[item.id] = run
    asyncio.create_task(
        _worker(
            item,
            run,
            query,
            model,
            time_limit,
            style if style in {"brief", "clear", "full"} else "clear",
            skip_guidance,
        )
    )
    return item


async def open_investigation(query: str, model: str | None = None) -> Investigation:
    item = start_investigation(query, model)
    await runs[item.id].finished.wait()
    return store.get(item.id) or item


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/models")
async def models() -> dict:
    names = await list_models()
    return {"models": names, "default": names[0] if names else None}


@router.post("/investigations", response_model=Investigation)
async def create_investigation(payload: InvestigationCreate) -> Investigation:
    return start_investigation(payload.query, payload.model, payload.time_limit, payload.style, thread_id=payload.thread_id)


@router.get("/investigations", response_model=list[Investigation])
async def list_investigations() -> list[Investigation]:
    return store.list()


@router.post("/investigations/{investigation_id}/choice", response_model=Investigation)
async def choose(investigation_id: UUID, payload: ChoiceRequest) -> Investigation:
    item = store.get(investigation_id)
    run = runs.get(investigation_id)
    if item is None or run is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    allowed = {choice.id for choice in item.clarify_choices}
    if payload.choice_id not in allowed or run.choice.is_set():
        raise HTTPException(status_code=409, detail="That choice is no longer available")
    run.selected = payload.choice_id
    run.note = payload.note
    item.hint = next(choice.label for choice in item.clarify_choices if choice.id == payload.choice_id)
    store.save(item)
    run.choice.set()
    return item


@router.post("/investigations/{investigation_id}/retry", response_model=Investigation)
async def retry(investigation_id: UUID, payload: ChoiceRequest) -> Investigation:
    item = store.get(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if payload.choice_id == "keep":
        return item
    allowed = {choice.id for choice in item.clarify_choices}
    if payload.choice_id not in allowed:
        raise HTTPException(status_code=409, detail="That choice is no longer available")
    refined = apply_choice(item.query, payload.choice_id, payload.note)
    style = "brief" if payload.choice_id == "again_shorter" else "clear"
    return start_investigation(refined, item.model, item.time_limit or 45, style, skip_guidance=True, thread_id=item.thread_id)


@router.get("/investigations/{investigation_id}/events")
async def stream_events(investigation_id: UUID) -> StreamingResponse:
    item = store.get(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    run = runs.get(investigation_id)

    async def generate():
        if run is None:
            yield _sse(
                {
                    "type": "done",
                    "status": item.status,
                    "final_answer": item.final_answer,
                    "thinking": item.thinking,
                    "hint": item.hint,
                    "sources": [source.model_dump() for source in item.sources],
                    "stages": [stage.model_dump() for stage in item.stages],
                }
            )
            return
        cursor = 0
        while True:
            while cursor < len(run.events):
                yield _sse(run.events[cursor])
                cursor += 1
            if run.finished.is_set() and cursor >= len(run.events):
                break
            yield _sse({"type": "ping"})
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/investigations/{investigation_id}", response_model=Investigation)
async def get_investigation(investigation_id: UUID) -> Investigation:
    item = store.get(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return item


@router.get("/investigations/{investigation_id}/trace")
async def get_trace(investigation_id: UUID) -> dict:
    item = store.get(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {
        "investigation_id": str(item.id),
        "stages": [stage.model_dump() for stage in item.stages],
        "hint": item.hint,
    }


@router.get("/investigations/{investigation_id}/sources")
async def get_sources(investigation_id: UUID) -> dict:
    item = store.get(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {
        "investigation_id": str(item.id),
        "sources": [source.model_dump() for source in item.sources],
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    investigation = await open_investigation(payload.message, payload.model)
    return ChatResponse(
        investigation_id=investigation.id,
        message=investigation.final_answer or "Investigation created.",
    )
