from api.health import router as health_router
from api.investigations import router as investigation_router
from api.catalog import router as catalog_router

__all__ = ["health_router", "investigation_router", "catalog_router"]
