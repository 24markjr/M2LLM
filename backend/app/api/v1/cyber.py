"""Cyber analysis of a run's documents over HTTP (Phase 52).

Indicators, entities, observed relations, per-host and per-account timelines and decoded commands,
read from the run's documents without a model - and, when the run's case has opted in (D19), other
cases sharing distinctive indicators, labelled as context.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.errors import ApiError
from app.api.registry import get_registry
from app.cases.service import get_case_store
from app.cyber.analysis import analyse
from app.cyber.recall import distinctive, similar_cases
from app.schemas.cyber import CyberAnalysis

router = APIRouter(tags=["cyber"])


@router.get("/missions/{run_id}/cyber", response_model=CyberAnalysis)
async def get_cyber_analysis(run_id: str) -> CyberAnalysis:
    record = get_registry().get(run_id)
    if record is None:
        raise ApiError(
            "MISSION_NOT_FOUND", f"no mission {run_id}", status_code=status.HTTP_404_NOT_FOUND
        )
    analysis = analyse(record.texts, record.page_starts)
    if not record.case_id:
        analysis.recall = "off: the run is not in a case"
        return analysis
    case = await (await get_case_store()).get(record.case_id)
    if case is None or not case.recall_similar:
        analysis.recall = "off: the case has not opted in to recall"
        return analysis
    analysis.similar_cases = await similar_cases(case.case_id, distinctive(analysis.indicators))
    analysis.recall = "on: context only - nothing recalled can be cited"
    return analysis
