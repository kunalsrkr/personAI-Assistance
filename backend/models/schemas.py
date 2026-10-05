from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    APPROVAL = "APPROVAL"
    FAILED = "FAILED"


class InvestigationCreate(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    model: str | None = None
    time_limit: int = Field(default=45, ge=20, le=120)
    style: str = "clear"
    thread_id: str = ""


class InvestigationSource(BaseModel):
    source_id: str
    title: str
    excerpt: str = ""
    origin: str = ""
    url: str = ""
    play_root: int | None = None
    play_path: str = ""


class InvestigationStage(BaseModel):
    id: str
    label: str
    status: str
    detail: str = ""


class ClarifyChoice(BaseModel):
    id: str
    label: str


class Investigation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    query: str
    status: InvestigationStatus = InvestigationStatus.PENDING
    iteration: int = 0
    max_iterations: int = 8
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    final_answer: str | None = None
    thinking: str = ""
    hint: str = ""
    confidence: float | None = None
    step_count: int = 0
    model: str | None = None
    time_limit: int = 45
    deadline_at: datetime | None = None
    sources: list[InvestigationSource] = Field(default_factory=list)
    stages: list[InvestigationStage] = Field(default_factory=list)
    clarify_prompt: str = ""
    clarify_choices: list[ClarifyChoice] = Field(default_factory=list)
    thread_id: str = ""


class ChoiceRequest(BaseModel):
    choice_id: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=80)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    model: str | None = None


class ChatResponse(BaseModel):
    investigation_id: UUID
    message: str
