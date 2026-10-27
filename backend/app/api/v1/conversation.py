"""The investigation conversation (v4 Phase 3): a thread per case.

    GET  /cases/{case_id}/conversation                      the thread, oldest turn first
    POST /cases/{case_id}/conversation                      ask; returns the thread with the answer
    POST /cases/{case_id}/conversation/{turn_id}/pin        pin or unpin a turn

A message is answered by a bounded tool loop over the case's documents and findings, and every claim
of the answer is verified before it is returned (`app/conversation/service.py`). The case id is
checked to be the caller's organisation's before anything runs (`app/api/ownership.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Header, status
from pydantic import Field

from app.api.errors import ApiError
from app.conversation import service, store
from app.conversation.models import Thread
from app.llm import get_provider
from app.schemas.common import JarvisModel

router = APIRouter(prefix="/cases", tags=["conversation"])


class Message(JarvisModel):
    text: str = Field(min_length=1, max_length=4000)


class Pin(JarvisModel):
    pinned: bool = True


@router.get("/{case_id}/conversation", response_model=Thread)
async def get_conversation(case_id: str) -> Thread:
    return store.load(case_id)


@router.post("/{case_id}/conversation", response_model=Thread)
async def ask(
    case_id: str,
    body: Message,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> Thread:
    """Answer one message. Slow by design: up to five tool calls and a verdict per claim."""
    return await service.converse(case_id, body.text.strip(), get_provider(), actor=actor)


@router.post("/{case_id}/conversation/{turn_id}/pin", response_model=Thread)
async def pin(case_id: str, turn_id: str, body: Pin) -> Thread:
    async with store.lock(case_id):
        thread = store.load(case_id)
        turn = next((t for t in thread.turns if t.turn_id == turn_id), None)
        if turn is None:
            raise ApiError(
                "TURN_NOT_FOUND",
                f"no turn {turn_id} in {case_id}",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        turn.pinned = body.pinned
        store.save(thread)
        return thread
