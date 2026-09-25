"""Version 1 of the HTTP surface.

Versioned from the start. The frontend generates its types from `docs/openapi.json`, so a
breaking change to a response shape breaks a build somewhere - having `/v2` available is what
makes such a change possible without a flag day.
"""

from fastapi import APIRouter

from app.api.v1 import documents, missions, replay

router = APIRouter(prefix="/api/v1")
router.include_router(missions.router)
router.include_router(documents.router)
router.include_router(replay.router)

__all__ = ["router"]
