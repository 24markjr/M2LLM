"""The investigation conversation (v4 Phase 3; streamed, editable and with sources in Phase 4).

    GET  /cases/{case_id}/conversation                       the thread, oldest turn first
    POST /cases/{case_id}/conversation                       ask; returns the thread with the answer
    POST /cases/{case_id}/conversation/stream                ask, regenerate or edit, streamed
    POST /cases/{case_id}/conversation/{turn_id}/regenerate  answer that message again
    POST /cases/{case_id}/conversation/{turn_id}/edit        edit a message; the thread branches
    POST /cases/{case_id}/conversation/{turn_id}/pin         pin or unpin a turn
    GET  /cases/{case_id}/sources                            the case's documents, for the viewer

A message is answered by a bounded tool loop over the case's documents and findings, and every claim
of the answer is verified before it is marked (`app/conversation/service.py`). The stream sends, as
server-sent events: `activity` (what it is doing, in words), `words` (the answer, a few words at a
time), `verdict` (a claim's mark, once checked), then `done` with the thread - or `error`. The case
id is checked to be the caller's organisation's before anything runs (`app/api/ownership.py`).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, status
from fastapi.responses import StreamingResponse
from pydantic import Field

from app.api.errors import ApiError
from app.conversation import service, store
from app.conversation.models import Thread
from app.conversation.tools import gather
from app.core.logging import get_logger
from app.llm import get_provider
from app.schemas.common import JarvisModel

log = get_logger(__name__)

router = APIRouter(prefix="/cases", tags=["conversation"])


class Message(JarvisModel):
    text: str = Field(min_length=1, max_length=4000)


class StreamRequest(JarvisModel):
    """Exactly one of: a new message (`text`), an answer to regenerate, or a message to edit
    (`edit` with the new `text`)."""

    text: str = Field(default="", max_length=4000)
    regenerate: str = Field(default="", max_length=32)
    edit: str = Field(default="", max_length=32)


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


@router.post("/{case_id}/conversation/stream")
async def ask_streamed(
    case_id: str,
    body: StreamRequest,
    actor: str = Header(default="console", alias="X-Jarvis-User", max_length=128),
) -> StreamingResponse:
    provider = get_provider()
    if not body.regenerate:
        _require_text(body.text)  # refused before the stream opens, as a plain 422

    async def start(emit: service.Emit) -> Thread:
        if body.regenerate:
            return await service.regenerate(case_id, body.regenerate, provider, emit=emit)
        if body.edit:
            return await service.edit(case_id, body.edit, body.text.strip(), provider, emit=emit)
        return await service.converse(case_id, body.text.strip(), provider, actor=actor, emit=emit)

    return StreamingResponse(
        _events(start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(start: Any) -> AsyncIterator[str]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def work() -> None:
        try:
            thread = await start(emit)
            await queue.put({"type": "done", "thread": thread.model_dump(mode="json")})
        except service.TurnNotFoundError as exc:
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:
            log.exception("conversation_stream_failed")
            await queue.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(work())
    try:
        while (event := await queue.get()) is not None:
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        if not task.done():
            task.cancel()


@router.post("/{case_id}/conversation/{turn_id}/regenerate", response_model=Thread)
async def regenerate(case_id: str, turn_id: str) -> Thread:
    try:
        return await service.regenerate(case_id, turn_id, get_provider())
    except service.TurnNotFoundError as exc:
        raise _no_turn(str(exc)) from exc


@router.post("/{case_id}/conversation/{turn_id}/edit", response_model=Thread)
async def edit(case_id: str, turn_id: str, body: Message) -> Thread:
    try:
        return await service.edit(case_id, turn_id, body.text.strip(), get_provider())
    except service.TurnNotFoundError as exc:
        raise _no_turn(str(exc)) from exc


@router.post("/{case_id}/conversation/{turn_id}/pin", response_model=Thread)
async def pin(case_id: str, turn_id: str, body: Pin) -> Thread:
    async with store.lock(case_id):
        thread = store.load(case_id)
        turn = next((t for t in thread.turns if t.turn_id == turn_id), None)
        if turn is None:
            raise _no_turn(f"no turn {turn_id} in {case_id}")
        turn.pinned = body.pinned
        store.save(thread)
        return thread


@router.get("/{case_id}/sources", response_model=dict[str, str])
async def sources(case_id: str) -> dict[str, str]:
    """The text each of the case's documents was read as - what a citation's line number counts."""
    return (await gather(case_id)).documents


def _require_text(text: str) -> None:
    if not text.strip():
        raise ApiError(
            "EMPTY_MESSAGE",
            "a message needs text",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


def _no_turn(message: str) -> ApiError:
    return ApiError("TURN_NOT_FOUND", message, status_code=status.HTTP_404_NOT_FOUND)
