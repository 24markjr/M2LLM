"""The specification's "must not do" list, made checkable.

Phase 23's acceptance criterion is that **every one of these would fail if the rule were
violated**. A rule stated in a document and nowhere else is a hope; a rule with a test is a
constraint. `test_llm_isolation.py` covers invariant 1 and the no-`eval` rule by reading the
source tree. This file covers the rest:

- **Invariant 3** — no model deliberation is ever persisted
- **Invariant 7** — every loop is bounded
- Closed vocabularies stay closed
- Confidence cannot be asserted, only computed
- Configuration ceilings cannot be exceeded by policy

These are deliberately blunt. A test here that needed interpretation would not be doing its job.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
from app.schemas.common import new_run_id
from app.schemas.event import REDACTED_PAYLOAD_KEYS, EventType, ExecutionEvent
from app.schemas.finding import Confidence, FindingClassification
from app.schemas.intent import Operation
from app.schemas.task import TaskStatus, TaskType

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


# --- invariant 3: no model deliberation is ever persisted -----------------------


def test_deliberation_keys_are_redacted_from_every_event() -> None:
    """A reasoning model returns its thinking. None of it may reach a sink.

    This is the difference between an auditable record of what the system *did* and a
    transcript of what a model mulled over - which is not evidence, cannot be verified, and
    would be the most misleading thing in the log.
    """
    event = ExecutionEvent(
        run_id=new_run_id(),
        event_type=EventType.LLM_CALL_COMPLETED,
        t_offset_ms=120,
        payload={
            "role": "reasoning",
            "latency_ms": 42,
            **{key: "the model was mulling this over" for key in REDACTED_PAYLOAD_KEYS},
        },
    )

    clean = event.redacted()

    for key in REDACTED_PAYLOAD_KEYS:
        assert key not in clean.payload, f"{key} survived redaction"
    assert clean.payload["latency_ms"] == 42, "operational fields are kept"


async def test_the_bus_redacts_before_any_sink_sees_an_event() -> None:
    """Redaction on the bus, not in each sink. A sink added later must not have to remember."""
    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())

    await emitter.emit(
        EventType.LLM_CALL_COMPLETED,
        payload={"thinking": "deliberation", "role": "planner"},
    )

    assert len(memory.events) == 1
    assert "thinking" not in memory.events[0].payload
    assert memory.events[0].payload["role"] == "planner"


@pytest.mark.parametrize(
    "key",
    [
        "thinking",
        "chain_of_thought",
        "reasoning_trace",
        "raw_response",
        "raw_completion",
        "prompt",
        "system_prompt",
        "messages",
    ],
)
def test_every_deliberation_and_prompt_key_is_redacted(key: str) -> None:
    """A partial list would leak through whichever name a provider happens to use.

    Prompts are redacted alongside deliberation: a stored prompt is not what the system did,
    and a document quoted inside one would put the investigated text into the audit record.
    """
    assert key in REDACTED_PAYLOAD_KEYS


def test_the_ollama_provider_never_reads_the_thinking_field() -> None:
    """qwen3 returns deliberation in `thinking`. The provider must not touch it.

    Checked against the source because the guarantee is that the code contains no path to it -
    a behavioural test could only show that one particular call did not happen to read it.
    """
    source = (APP_ROOT / "llm" / "ollama.py").read_text(encoding="utf-8")
    code_lines = [
        line
        for line in source.splitlines()
        if not line.lstrip().startswith("#") and '"""' not in line
    ]
    body = "\n".join(code_lines)

    assert '"thinking"' not in body, "the provider reads the deliberation field"
    assert '"think": request.think' in body, "the provider must send think explicitly"


# --- invariant 7: every loop is bounded -----------------------------------------


def test_every_loop_ceiling_is_configured_and_finite() -> None:
    """A loop that can run forever is not adaptive, it is broken.

    Each of these bounds a real loop in the system. If one went missing the loop it guards
    would still run - just without a stop.
    """
    from app.core.agent_config import get_agent_bounds

    bounds = get_agent_bounds()

    assert bounds.max_replan_iterations >= 0, "the adaptive loop"
    assert bounds.max_task_retries >= 0, "task retry"
    assert bounds.max_tool_calls_per_run >= 1, "total tool calls in a run"
    assert bounds.max_plan_tasks >= 2, "plan size"
    assert bounds.wallclock_limit_s > 0, "the run as a whole"
    assert bounds.observation_budget_tokens >= 500, "what reasoning may read"

    for name, value in vars(bounds).items():
        assert value is not None, f"{name} has no ceiling"


def test_the_structured_output_repair_loop_is_bounded() -> None:
    """The repair loop re-prompts on a schema violation. Unbounded, a model that never
    complies would spin until the process was killed."""
    from app.core.agent_config import get_models_config

    policy = get_models_config().structured_output
    assert policy.max_repairs >= 0
    assert policy.max_repairs <= 5, "a high repair count hides a prompt problem behind retries"


def test_the_replanning_controller_caps_what_one_iteration_may_insert() -> None:
    """Measured at 24 tasks inserted in a single replan. A per-iteration cap is what keeps
    each iteration's confidence gain attributable, which the diminishing-returns stop needs."""
    from app.intelligence.replanning.controller import MAX_ACTIONS_PER_ITERATION

    assert 1 <= MAX_ACTIONS_PER_ITERATION <= 5


def test_no_unbounded_while_true_outside_a_guarded_loop() -> None:
    """`while True` is allowed only where the body provably exits.

    Rather than trying to prove that automatically, this asserts the count does not grow: each
    existing one has been read and has a bounded body. A new one has to be justified here, which
    is the point - it forces the question to be asked.
    """
    known = {
        # SSE: exits on client disconnect, on the terminal frame, or when the task is cancelled.
        "api/v1/stream.py": 1,
        # Task retry and tool fallback. Retries are capped by `task.attempts <
        # self._max_attempts`; fallbacks are capped by the `tried` set against a finite
        # registry; every remaining path returns. Read 2026-09-25.
        "intelligence/execution/engine.py": 1,
    }

    found: dict[str, int] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        count = path.read_text(encoding="utf-8").count("while True:")
        if count:
            found[path.relative_to(APP_ROOT).as_posix()] = count

    assert found == known, (
        f"an unreviewed `while True` appeared: {found}. Read its exit condition, then record "
        "it here."
    )


# --- closed vocabularies stay closed -------------------------------------------


@pytest.mark.parametrize(
    ("enum", "expected"),
    [(Operation, 17), (TaskType, 16), (TaskStatus, 8), (EventType, 37)],
)
def test_the_closed_vocabularies_are_the_size_they_claim(enum: type, expected: int) -> None:
    """Extending one of these is a deliberate act.

    A new operation needs a task type that can execute it and a tool that can serve it, or
    planning produces work routing cannot fulfil. This test failing is not a problem - it is the
    reminder to update the count and check the rest of the chain.
    """
    assert len(list(enum)) == expected, (
        f"{enum.__name__} has {len(list(enum))} members, not {expected}. If that was "
        "intentional, update this count and confirm the vocabulary is still executable."
    )


def test_every_event_type_value_matches_its_name() -> None:
    """Event types are serialised into the log and compared as strings.

    A member whose value drifted from its name - `FINDING_VERIFED = "FINDING_VERIFIED"` - would
    still import, still type check, and silently never match a filter written against the name.
    """
    mismatched = [member.name for member in EventType if member.value != member.name]
    assert mismatched == [], f"these event types have a value that is not their name: {mismatched}"


def test_every_vocabulary_value_is_unique() -> None:
    """Two members sharing a value collapse into one after a round trip through JSON."""
    for enum in (Operation, TaskType, TaskStatus, EventType):
        values = [member.value for member in enum]
        assert len(values) == len(set(values)), f"{enum.__name__} has a duplicated value"


# --- confidence is computed, never asserted ------------------------------------


def test_a_bare_confidence_number_cannot_be_constructed() -> None:
    """`Confidence(value=0.96)` must be impossible.

    Enforced in the type rather than by convention, because a convention is something a future
    contributor can be unaware of. This is what makes "confidence is computed from evidence" a
    property of the system instead of a claim about it.
    """
    with pytest.raises(ValidationError):
        Confidence(value=0.96)  # type: ignore[call-arg]


def test_confidence_compute_is_keyword_only_and_records_its_factors() -> None:
    """The factors stay on the finding so a number can be taken apart afterwards. A confidence
    nobody can decompose is indistinguishable from one that was made up."""
    signature = inspect.signature(Confidence.compute)
    positional = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    assert positional == [], "compute() takes keywords only, so a call site cannot be misread"

    confidence = Confidence.compute(refs=[], classification=FindingClassification.UNKNOWN)
    for factor in ("resolution_rate", "evidence_strength", "source_agreement"):
        assert hasattr(confidence, factor)


# --- configuration: policy can never exceed an .env ceiling --------------------


def test_yaml_policy_cannot_raise_a_hard_ceiling() -> None:
    """Two configuration surfaces, and the ordering between them is not negotiable: `.env` sets
    ceilings, `agent.yaml` expresses preference within them. A policy file that could raise a
    ceiling would make the ceiling decorative."""
    from app.core.agent_config import clamp

    assert clamp(99, 3, name="max_replan_iterations") == 3
    assert clamp(2, 3, name="max_replan_iterations") == 2


def test_the_agent_bounds_never_exceed_settings() -> None:
    """The realised bounds, checked against the ceilings they were clamped to."""
    from app.core.agent_config import get_agent_bounds
    from app.core.config import get_settings

    bounds = get_agent_bounds()
    settings = get_settings()

    assert bounds.max_replan_iterations <= settings.max_replan_iterations
    assert bounds.max_parallel_tasks <= settings.max_parallel_tasks
    assert bounds.max_task_retries <= settings.max_task_retries
    assert bounds.max_plan_tasks <= settings.max_plan_tasks
    assert bounds.max_tool_calls_per_run <= settings.max_tool_calls_per_run
