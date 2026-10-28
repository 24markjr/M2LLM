"""Version 1 of the HTTP surface.

Versioned from the start. The frontend generates its types from `docs/openapi.json`, so a
breaking change to a response shape breaks a build somewhere - having `/v2` available is what
makes such a change possible without a flag day.
"""

from fastapi import APIRouter, Depends

from app.api.ownership import own_resources
from app.api.v1 import (
    auth,
    cases,
    context,
    conversation,
    cyber,
    documents,
    evidence,
    followups,
    knowledge,
    language,
    memory,
    missions,
    ops,
    replay,
    reports,
    review,
    system,
)

# Every route that names a run, case or evidence item is checked to be the caller's (v4 Phase 1c).
router = APIRouter(prefix="/api/v1", dependencies=[Depends(own_resources)])
router.include_router(missions.router)
router.include_router(documents.router)
router.include_router(replay.router)
router.include_router(knowledge.router)
router.include_router(memory.router)
router.include_router(context.router)
router.include_router(evidence.router)
router.include_router(cases.router)
router.include_router(conversation.router)
router.include_router(followups.missions)
router.include_router(followups.cases)
router.include_router(review.router)
router.include_router(reports.router)
router.include_router(cyber.router)
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(ops.router)
router.include_router(language.router)

__all__ = ["router"]
