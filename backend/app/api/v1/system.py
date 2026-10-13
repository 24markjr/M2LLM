"""Where the console's records are kept right now (Phase U1).

The stores fall back to memory when Postgres cannot be reached, and say so only in the log. A page
showing "0 entries" then cannot tell an empty log from one that is not being kept. This names the
store behind each part, so the page can.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.archive import read_archives
from app.api.persistence import persistence_enabled
from app.cases.service import get_case_store
from app.evidence.service import get_locker
from app.review.service import get_review_store
from app.schemas.common import JarvisModel

router = APIRouter(prefix="/system", tags=["system"])

IN_MEMORY = (
    "in memory: the database was not reachable, so this is lost when the engine stops "
    "(checked again every 30 seconds)"
)


class StoreStatus(JarvisModel):
    part: str
    store: str
    note: str = ""


class SystemStores(JarvisModel):
    stores: list[StoreStatus]


@router.get("/stores", response_model=SystemStores)
async def stores() -> SystemStores:
    """The store behind cases, evidence, the audit log and investigations."""
    parts = [
        ("cases", (await get_case_store()).name),
        ("evidence", (await get_locker()).name),
        ("audit log", (await get_review_store()).name),
    ]
    found = [
        StoreStatus(part=part, store=name, note=IN_MEMORY if name == "memory" else "")
        for part, name in parts
    ]
    archived = len(read_archives())
    found.append(
        StoreStatus(
            part="investigations",
            store="files" + (" + postgres" if await persistence_enabled() else ""),
            note=f"{archived} finished investigation(s) archived in .agent/runs/",
        )
    )
    return SystemStores(stores=found)
