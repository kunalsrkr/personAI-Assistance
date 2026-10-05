from datetime import datetime, timezone
from uuid import UUID, uuid4

from models.schemas import Investigation, InvestigationCreate, InvestigationStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationStore:
    """In-memory store used when PostgreSQL is unavailable (local Sprint 0)."""

    def __init__(self) -> None:
        self._items: dict[UUID, Investigation] = {}

    def create(self, payload: InvestigationCreate) -> Investigation:
        item = Investigation(
            id=uuid4(),
            query=payload.query,
            status=InvestigationStatus.PENDING,
            started_at=utcnow(),
            step_count=0,
            model=payload.model,
        )
        self._items[item.id] = item
        return item

    def list(self) -> list[Investigation]:
        return sorted(self._items.values(), key=lambda item: item.started_at, reverse=True)

    def get(self, investigation_id: UUID) -> Investigation | None:
        return self._items.get(investigation_id)

    def save(self, item: Investigation) -> Investigation:
        self._items[item.id] = item
        return item


store = InvestigationStore()
