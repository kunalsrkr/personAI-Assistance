from fastapi import APIRouter

from core.config import settings
from models.store import store

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "investigations": len(store.list()),
        "ollama_base_url": settings.ollama_base_url,
        "notes": {
            "postgres": "optional in Sprint 0; API uses in-memory store until DB is wired in later sprints",
            "agents": "not implemented in Sprint 0",
        },
    }
