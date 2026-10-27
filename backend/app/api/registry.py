"""The run registry — missions in flight, and the event history that lets a client catch up.

The API never blocks on a run. `POST /missions` starts a background task and returns
immediately with a run id, because an investigation takes a minute or more and an HTTP
request that waits for one is a request that times out.

**History is kept per run, in order.** SSE reconnection replays from `Last-Event-ID`, and
that is only possible if the events a client missed still exist somewhere. `StreamEventSink`
deliberately drops events for a lagging subscriber rather than stalling the agent, so the
history is what makes that trade safe: the client recovers the gap instead of losing it.

This is in-memory and per-process. The database sink (Phase 3) is the durable record; this
exists so a live client can be served without a round trip to Postgres for every event.
"""

from __future__ import annotations

import asyncio
import itertools
from datetime import datetime

from app.api.archive import RunArchive, read_archives, write_archive
from app.api.persistence import persistence_enabled, record_finished, record_started
from app.api.recording import write_recording
from app.auth.tenancy import current_org
from app.core.config import get_settings
from app.core.events import (
    EventBus,
    MemoryEventSink,
    RunEventEmitter,
    StreamEventSink,
)
from app.core.logging import get_logger
from app.database.event_sink import DatabaseEventSink
from app.intelligence.challenge import ChallengeResult
from app.llm.prompts import get_prompt_library
from app.memory.service import record_run
from app.orchestration.mission import MissionResult, MissionStatus, Stage, run_mission
from app.review.service import audit
from app.schemas.case import CaseInvestigation
from app.schemas.common import RunId, new_run_id, utcnow
from app.schemas.event import ExecutionEvent
from app.schemas.finding import Finding
from app.schemas.objective import Objective

log = get_logger(__name__)


# Runs that may wait for a slot before new ones are refused (v4 Phase 8).
MAX_QUEUE = 50


class MissionRecord:
    """One mission: its result so far, its events, and the task running it."""

    # Monotonic creation order. `created_at` alone is not enough to sort by: two missions
    # created in the same millisecond tie, and the list order then varies between requests
    # for no reason the user can see.
    _sequence = itertools.count()

    def __init__(self, run_id: RunId, objective: Objective, documents: list[str]) -> None:
        self.sequence = next(MissionRecord._sequence)
        self.run_id = run_id
        self.objective = objective
        self.documents = documents
        self.created_at: datetime = utcnow()
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None

        self.status = MissionStatus.PENDING
        self.stage = Stage.UNDERSTANDING
        self.result: MissionResult | None = None
        self.task: asyncio.Task[None] | None = None
        self.events: list[ExecutionEvent] = []
        # The knowledge graph as the explorer draws it, and the run's timeline, built when the run
        # ends so a recording can carry them: replay then opens the 3D graph with no server.
        self.knowledge_view: dict[str, object] | None = None
        self.knowledge_timeline: list[dict[str, object]] | None = None
        # The Evidence Locker (Phase 43): name -> evidence id read, and name -> why it was left out.
        self.evidence: dict[str, str] = {}
        self.excluded: dict[str, str] = {}
        # Each document's source authority tier (Phase 45), fixed when the mission is created.
        self.authority: dict[str, str] = {}
        # The text each document was read as, and its page starts: what a challenge searches for
        # counter-evidence (Phase 48), and what it records against.
        self.texts: dict[str, str] = {}
        self.page_starts: dict[str, list[int]] = {}
        self.challenges: dict[str, ChallengeResult] = {}
        # The same question put to the plain model (Phase U7), once someone asks for it.
        self.comparison: dict[str, object] | None = None
        # The prompt versions the run used, stamped when it finishes: the receipt's (Phase U7).
        self.prompt_versions: dict[str, int] = {}
        # The lines an ATT&CK mapping rests on (Phase 53), computed once from `texts` on first use.
        self.attack_locators: set[str] | None = None
        # The case the mission belongs to (Phase 44).
        self.case_id: str = ""
        # The organisation it belongs to (v4 Phase 1c): whoever started it, inherited by its task.
        self.org_id: str = current_org()

    @classmethod
    def from_archive(cls, archive: RunArchive) -> MissionRecord:
        """A finished mission as it was archived (Phase U1): every route answers for it."""
        record = cls(archive.run_id, archive.objective, list(archive.documents))
        record.created_at = archive.created_at
        record.started_at = archive.started_at
        record.finished_at = archive.finished_at
        record.status = archive.status
        record.stage = archive.stage
        record.result = archive.result
        record.events = list(archive.events)
        record.evidence = dict(archive.evidence)
        record.excluded = dict(archive.excluded)
        record.authority = dict(archive.authority)
        record.texts = dict(archive.texts)
        record.page_starts = dict(archive.page_starts)
        record.case_id = archive.case_id
        record.org_id = archive.org_id
        record.knowledge_view = archive.knowledge_view
        record.knowledge_timeline = archive.knowledge_timeline
        record.challenges = dict(archive.challenges)
        record.comparison = archive.comparison
        record.prompt_versions = dict(archive.prompt_versions)
        return record

    def is_finished(self) -> bool:
        """Whether the run has reached a terminal status.

        A method rather than a property because it changes under the caller: the SSE stream
        checks it repeatedly while the run proceeds, and a property would let a type checker
        narrow the first check and treat the rest as dead code.
        """
        return self.status in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
            MissionStatus.CLARIFICATION_NEEDED,
        }

    def events_after(self, last_event_id: str | None) -> list[ExecutionEvent]:
        """Events the client has not seen, in order.

        An unknown id replays everything rather than nothing. A client reconnecting with an
        id this process never issued - after a restart, say - would otherwise sit waiting
        for events that already happened, which is the one outcome worse than a duplicate.
        """
        if last_event_id is None:
            return list(self.events)
        for index, event in enumerate(self.events):
            if event.event_id == last_event_id:
                return self.events[index + 1 :]
        log.warning("unknown_last_event_id", run_id=self.run_id, last_event_id=last_event_id)
        return list(self.events)


class MissionRegistry:
    """Owns every mission this process is running or has run."""

    def __init__(self) -> None:
        self._missions: dict[RunId, MissionRecord] = {}
        self._stream = StreamEventSink()
        self._max_concurrent = get_settings().max_concurrent_runs
        self._running = 0
        # The queue (v4 Phase 8): a run waits for one of `max_concurrent_runs` slots, first come
        # first served (asyncio's semaphore wakes waiters in order). Waiting runs are PENDING and
        # know their place; only a full queue is refused.
        self._slots = asyncio.Semaphore(self._max_concurrent)
        self._waiting: list[str] = []
        # Created lazily in `create`, because availability is an async question and a registry is
        # constructed synchronously.
        self._database: DatabaseEventSink | None = None
        self._restored = False

    def _restore(self) -> None:
        """Load archived missions once, oldest first, before anything new (Phase U1). A run
        already in memory wins over its archive."""
        if self._restored:
            return
        self._restored = True
        restored = 0
        for archive in read_archives():
            if archive.run_id not in self._missions:
                self._missions[archive.run_id] = MissionRecord.from_archive(archive)
                restored += 1
        if restored:
            log.info("missions_restored", count=restored)

    # --- reading -----------------------------------------------------------

    def get(self, run_id: str) -> MissionRecord | None:
        """The run, if it belongs to the current organisation (v4 Phase 1c): another
        organisation's run is not found, exactly like one that does not exist."""
        self._restore()
        record = self._missions.get(run_id)
        return record if record is not None and record.org_id == current_org() else None

    def owner(self, run_id: str) -> str | None:
        """The organisation a run belongs to, whoever asks; None for a run this server does not
        hold (v4 Phase 1c). For the ownership check, not for serving the run."""
        self._restore()
        record = self._missions.get(run_id)
        return record.org_id if record is not None else None

    def records(self) -> list[MissionRecord]:
        """Newest first: a mission list is read from the top."""
        self._restore()
        # By creation time, then sequence: a restored run keeps its place among new ones (U1).
        org = current_org()
        return sorted(
            (m for m in self._missions.values() if m.org_id == org),
            key=lambda m: (m.created_at, m.sequence),
            reverse=True,
        )

    def forget(self, run_id: str) -> MissionRecord | None:
        """Remove a mission from the registry. Its archive and recording are removed by the
        caller (`app/api/v1/history.py`), which also records the deletion."""
        if self.get(run_id) is None:
            return None
        return self._missions.pop(run_id, None)

    @property
    def stream(self) -> StreamEventSink:
        return self._stream

    @property
    def at_capacity(self) -> bool:
        """The queue is full: refusing is honest only when waiting would be unbounded."""
        return len(self._waiting) >= MAX_QUEUE

    @property
    def running(self) -> int:
        return self._running

    @property
    def waiting(self) -> int:
        return len(self._waiting)

    def queue_position(self, run_id: str) -> int:
        """1 for the next run to start, 0 for one that is running or about to (a slot is free)."""
        if run_id not in self._waiting:
            return 0
        free = self._max_concurrent - self._running
        return max(0, self._waiting.index(run_id) + 1 - free)

    # --- writing -----------------------------------------------------------

    async def create(
        self,
        *,
        objective: Objective,
        documents: list[str],
        loaded: dict[str, str],
        page_starts: dict[str, list[int]],
        provider: object,
        retriever: object = None,
        authority: dict[str, str] | None = None,
    ) -> MissionRecord:
        """Register a mission and start it. Returns as soon as the task is scheduled.

        Async only to probe the database once: attaching a sink that cannot write would log a
        failed connection on every flush, and a log full of expected errors is a log nobody reads.
        """
        self._restore()
        record = MissionRecord(new_run_id(), objective, documents)
        record.authority = dict(authority or {})
        record.texts = dict(loaded)
        record.page_starts = dict(page_starts)
        self._missions[record.run_id] = record

        history = _HistorySink(record)
        memory = MemoryEventSink()
        sinks: list[object] = [history, memory, self._stream]

        # The durable timeline, when a database is reachable. One more sink rather than a
        # replacement: the in-memory history is what serves SSE replay without a round trip to
        # Postgres per event, and the two answer different questions.
        #
        if await persistence_enabled():
            if self._database is None:
                self._database = DatabaseEventSink()
            sinks.append(self._database)

        emitter = RunEventEmitter(EventBus(sinks), record.run_id)  # type: ignore[arg-type]

        # In the queue from the moment it exists, so its position is known before its task starts.
        self._waiting.append(record.run_id)
        record.task = asyncio.create_task(
            self._queued(record, emitter, loaded, page_starts, provider, retriever),
            name=f"mission-{record.run_id}",
        )
        return record

    async def _queued(
        self,
        record: MissionRecord,
        emitter: RunEventEmitter,
        documents: dict[str, str],
        page_starts: dict[str, list[int]],
        provider: object,
        retriever: object = None,
    ) -> None:
        """Wait for a slot, then run. Cancelled while waiting: recorded as cancelled, never run."""
        try:
            await self._slots.acquire()
        except asyncio.CancelledError:
            self._waiting.remove(record.run_id)
            record.status = MissionStatus.CANCELLED
            record.stage = Stage.DONE
            record.finished_at = utcnow()
            write_archive(record)
            log.info("mission_cancelled_in_queue", run_id=record.run_id)
            return
        self._waiting.remove(record.run_id)
        try:
            await self._run(record, emitter, documents, page_starts, provider, retriever)
        finally:
            self._slots.release()

    async def cancel(self, record: MissionRecord) -> bool:
        """Ask a running mission to stop. False if it had already finished."""
        if record.is_finished() or record.task is None:
            return False
        return bool(record.task.cancel())

    async def _run(
        self,
        record: MissionRecord,
        emitter: RunEventEmitter,
        documents: dict[str, str],
        page_starts: dict[str, list[int]],
        provider: object,
        retriever: object = None,
    ) -> None:
        from app.llm.provider import LLMProvider

        assert isinstance(provider, LLMProvider)

        record.status = MissionStatus.RUNNING
        record.started_at = utcnow()
        self._running += 1

        # The run row has to exist before any event references it.
        await record_started(record)

        async def on_stage(stage: Stage, result: MissionResult) -> None:
            # Keeps the mission's phase queryable while the run is still going, so a client
            # that polls instead of streaming still sees where it is.
            record.stage = stage
            record.status = result.status

        try:
            record.result = await run_mission(
                objective=record.objective,
                documents=documents,
                provider=provider,
                emitter=emitter,
                page_starts=page_starts,
                on_stage=on_stage,
                retriever=retriever,
                authority=record.authority,
            )
            record.status = record.result.status
            await _challenge_findings(record, provider)
        except asyncio.CancelledError:
            record.status = MissionStatus.CANCELLED
            log.info("mission_cancelled", run_id=record.run_id)
        finally:
            self._running -= 1
            record.stage = Stage.DONE
            record.finished_at = utcnow()
            # Recorded on the way out, so a run that failed or was cancelled is replayable
            # too. A recording of only the successful runs would make the demo look better
            # than the system is.
            await _capture_knowledge(record)
            record.prompt_versions = get_prompt_library().versions()
            write_recording(record)
            write_archive(record)
            if self._database is not None:
                # Flush before the final write, so the stored timeline is complete when the run
                # row is marked finished.
                await self._database.flush()
            await record_finished(record)
            # Memory last: its episodes reference the run row just written (Phase 33). Written
            # once the run is over and never read back into one.
            if record.result is not None:
                await _record_memory(record.result, record.started_at, await _held(record))
                await _record_citations(record)
            await _file_outcome(record)
            # Again: filing can set the case's outcome after the first write (Phase U1).
            write_archive(record)
            await audit(
                "mission.finished",
                target=record.run_id,
                status=record.status.value,
                findings=len(record.result.findings) if record.result else 0,
            )


async def _challenge_findings(record: MissionRecord, provider: object) -> None:
    """Every verified finding is challenged when the run ends (v4 Phase 2): the counter-evidence
    search of Phase 48, which had to be asked for one finding at a time, now runs on each. Lines
    that disagree are found without a model; the verifier is called only when some do. Recorded
    beside the finding as the system's challenge - the finding itself is not changed - and a
    person can still challenge again. Never fails the run."""
    from app.integrations.verification import build_verification_provider
    from app.intelligence.challenge import challenge
    from app.llm.provider import LLMProvider

    result = record.result
    if result is None or not isinstance(provider, LLMProvider):
        return
    verifier = build_verification_provider(provider)
    for finding in result.verified_findings:
        try:
            record.challenges[finding.finding_id] = await challenge(
                finding,
                record.texts,
                page_starts=record.page_starts,
                authority=record.authority,
                evidence_text=result.evidence_text,
                verifier=verifier.verify,
                actor="automatic",
            )
        except Exception:  # a second opinion never costs the first
            log.exception("auto_challenge_failed", finding_id=finding.finding_id)


async def _capture_knowledge(record: MissionRecord) -> None:
    """Keep the run's graph view and timeline for its recording. Never raises.

    Built from the run's own knowledge base in memory, whichever store held it, so a replay shows
    exactly what the run knew, even after the store is cleared.
    """
    result = record.result
    if result is None or result.knowledge is None:
        return
    try:
        from app.intelligence.knowledge.base import InMemoryKnowledgeBase
        from app.intelligence.knowledge.view import build_view

        base = InMemoryKnowledgeBase(result.knowledge)
        view = await build_view(base, record.run_id, result.findings)
        record.knowledge_view = view.model_dump(mode="json")
        record.knowledge_timeline = [e.model_dump(mode="json") for e in await base.timeline()]
    except Exception:  # the run is over; a recording without its graph is still a recording
        log.exception("knowledge_capture_failed", run_id=record.run_id)


async def _held(record: MissionRecord) -> set[str]:
    """Findings that need a person's review before they count (Phase 50). Never raises."""
    if record.result is None:
        return set()
    try:
        from app.review.service import requirements

        severity = await _case_severity(record.case_id)
        mapped = attack_locators(record)
        return {
            f.finding_id
            for f in record.result.findings
            if requirements(f, case_severity=severity, attack_mapped=cites(f, mapped))
        }
    except Exception:
        log.exception("review_requirements_failed", run_id=record.run_id)
        return {f.finding_id for f in record.result.findings}


def attack_locators(record: MissionRecord) -> set[str]:
    """The lines of the run's documents an ATT&CK mapping rests on (Phase 53). Cached on the
    record; empty when the documents hold no events."""
    if record.attack_locators is None:
        from app.cyber.analysis import analyse
        from app.cyber.attack import mapped_locators

        record.attack_locators = (
            mapped_locators(analyse(record.texts, record.page_starts)) if record.texts else set()
        )
    return record.attack_locators


def cites(finding: Finding, locators: set[str]) -> bool:
    """Whether a finding cites one of these lines."""
    return any(ref.is_resolved and ref.as_ref() in locators for ref in finding.evidence)


async def _case_severity(case_id: str) -> str:
    if not case_id:
        return ""
    from app.cases.service import get_case_store

    case = await (await get_case_store()).get(case_id)
    return case.severity.value if case else ""


async def _record_memory(
    result: MissionResult, started_at: datetime | None, held: set[str] | None = None
) -> None:
    try:
        await record_run(result, started_at=started_at, held=held)
    except Exception:  # the boundary: memory must never fail a run
        log.exception("memory_record_failed", run_id=result.run_id)


async def _file_outcome(record: MissionRecord) -> None:
    """Record what the mission reached in its case (Phase 44), so the case keeps it after a
    restart. Never raises."""
    if not record.case_id:
        return
    from app.cases.service import file_investigation

    await file_investigation(case_investigation(record))


def case_investigation(record: MissionRecord) -> CaseInvestigation:
    result = record.result
    knowledge = result.knowledge if result is not None else None
    return CaseInvestigation(
        case_id=record.case_id,
        run_id=record.run_id,
        objective=record.objective.text,
        status=record.status.value,
        findings=len(result.findings) if result else 0,
        verified=len(result.verified_findings) if result else 0,
        contradictions=len(knowledge.conflicts) if knowledge else 0,
        open_gaps=len(result.unresolved_gaps) if result else 0,
        created_at=record.created_at,
        finished_at=record.finished_at,
    )


async def _record_citations(record: MissionRecord) -> None:
    """CITED in the custody of every evidence item a finding rests on (Phase 43). Never raises."""
    result = record.result
    if result is None or not record.evidence:
        return
    from app.evidence.service import record_citations

    try:
        await record_citations(
            record.run_id,
            record.evidence,
            [
                (finding.finding_id, finding.claim, ref.locator.document_id, ref.as_ref())
                for finding in result.findings
                for ref in finding.evidence
                if ref.is_resolved
            ],
        )
    except Exception:  # the run is over; lost custody links are logged, never fatal
        log.exception("evidence_citations_failed", run_id=record.run_id)


class _HistorySink:
    """Appends every event to a mission's history, so SSE can replay it."""

    def __init__(self, record: MissionRecord) -> None:
        self._record = record

    async def handle(self, event: ExecutionEvent) -> None:
        self._record.events.append(event)


_registry: MissionRegistry | None = None


def get_registry() -> MissionRegistry:
    global _registry
    if _registry is None:
        _registry = MissionRegistry()
    return _registry


def reset_registry() -> None:
    """Drop all state. For tests: a registry that leaks between them is a shared fixture."""
    global _registry
    _registry = None
