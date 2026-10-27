"""Every route that names a run, case or evidence item checks it is the caller's (v4 Phase 1c).

The stores already filter by organisation, and most routes look the resource up before using it;
this is the second line, in front of all of them, so a route that reads a run's files or rows
directly by id cannot serve another organisation's. One dependency on the whole `/api/v1` router,
like the auth middleware, so a new route is covered without remembering to be.

Another organisation's resource answers 404, exactly as one that does not exist.
"""

from __future__ import annotations

from fastapi import Request, status

from app.api.errors import ApiError, MissionNotFoundError
from app.api.registry import get_registry
from app.auth.tenancy import DEFAULT_ORG, current_org
from app.cases.service import get_case_store
from app.evidence.service import get_locker


def run_visible(run_id: str) -> bool:
    """Whether the current organisation may read what a run left behind. A run the server no
    longer holds (its knowledge or memory outlived its archive) predates organisations, so only the
    default organisation may still read what is left of it."""
    return (get_registry().owner(run_id) or DEFAULT_ORG) == current_org()


async def own_resources(request: Request) -> None:
    params = request.path_params
    run_id = params.get("run_id")
    if run_id is not None and not run_visible(run_id):
        raise MissionNotFoundError(run_id)

    case_id = params.get("case_id")
    if case_id is not None and await (await get_case_store()).get(case_id) is None:
        raise ApiError(
            "CASE_NOT_FOUND", f"no case {case_id}", status_code=status.HTTP_404_NOT_FOUND
        )

    evidence_id = params.get("evidence_id")
    if evidence_id is not None and await (await get_locker()).get(evidence_id) is None:
        raise ApiError(
            "EVIDENCE_NOT_FOUND",
            f"no evidence item {evidence_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
