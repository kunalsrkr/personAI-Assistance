import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.catalog import router as catalog_router
from api.health import router as health_router
from api.investigations import router as investigation_router
from api.funnel import router as funnel_router
from api.library import router as library_router
from api.linkedin import router as linkedin_router
from api.threads import router as thread_router
from api.speech import router as speech_router
from api.translate import router as translate_router
from core.config import settings
from servers.browser_history import history_refresh_loop


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(history_refresh_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(investigation_router)
app.include_router(catalog_router)
app.include_router(library_router)
app.include_router(linkedin_router)
app.include_router(funnel_router)
app.include_router(thread_router)
app.include_router(translate_router)
app.include_router(speech_router)


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "sprint": 0,
        "docs": "/docs",
        "health": "/health",
    }
