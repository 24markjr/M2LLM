"""Phase 4 — the LLM abstraction, structured output and the repair loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import Field

from app.llm.echo import EchoProvider, NoFixtureError, fixture_key, synthesize_from_schema
from app.llm.errors import PromptNotFoundError, StructuredOutputError
from app.llm.prompts import PromptLibrary
from app.llm.provider import CompletionRequest, LLMProvider
from app.llm.structured import extract_json, generate_structured
from app.llm.telemetry import LLMCallRecord, TelemetryCollector, get_collector
from app.schemas.common import JarvisModel, NonEmptyStr


class Simple(JarvisModel):
    name: NonEmptyStr
    count: int = Field(ge=0)


# --- JSON extraction -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"name": "a", "count": 1}', '{"name": "a", "count": 1}'),
        ('```json\n{"name": "a"}\n```', '{"name": "a"}'),
        ('```\n{"name": "a"}\n```', '{"name": "a"}'),
        ('Here is the result:\n{"name": "a"}', '{"name": "a"}'),
        ('{"name": "a"}\n\nHope that helps!', '{"name": "a"}'),
        ('[{"name": "a"}]', '[{"name": "a"}]'),
    ],
)
def test_extract_json_tolerates_real_model_output(raw: str, expected: str) -> None:
    """Fences and surrounding prose are what these models actually emit.

    Refusing to parse them would burn repair attempts on formatting quirks instead of real
    schema failures.
    """
    assert extract_json(raw) == expected


def test_extract_json_handles_braces_inside_strings() -> None:
    raw = '{"name": "a } b", "count": 1}'
    assert json.loads(extract_json(raw))["name"] == "a } b"


def test_extract_json_handles_nested_objects() -> None:
    raw = 'prefix {"outer": {"inner": {"deep": 1}}} suffix'
    assert json.loads(extract_json(raw))["outer"]["inner"]["deep"] == 1


# --- the repair loop -----------------------------------------------------------


async def test_valid_first_response_needs_no_repair() -> None:
    collector = get_collector()
    collector.clear()
    provider = EchoProvider(responses={"intent": ['{"name": "ok", "count": 2}']})

    result = await generate_structured(provider, Simple, "do the thing", role="intent")

    assert result.name == "ok"
    assert collector.records[-1].repair_attempt == 0
    assert collector.repair_rate == 0.0


async def test_malformed_json_is_repaired_on_the_second_attempt() -> None:
    """The core risk-mitigation for small local models."""
    collector = get_collector()
    collector.clear()
    provider = EchoProvider(
        responses={
            "intent": [
                "not json at all",
                '{"name": "recovered", "count": 1}',
            ]
        }
    )

    result = await generate_structured(provider, Simple, "do the thing", role="intent")

    assert result.name == "recovered"
    assert collector.records[-1].repair_attempt == 1
    assert collector.repair_rate == 1.0, "the success required a repair, and that is recorded"


async def test_the_repair_prompt_contains_the_validation_errors() -> None:
    """Telling the model what was wrong fixes far more than asking it to try again."""
    provider = EchoProvider(
        responses={
            "intent": [
                '{"name": "ok", "count": -5}',  # violates ge=0
                '{"name": "ok", "count": 5}',
            ]
        }
    )

    await generate_structured(provider, Simple, "do the thing", role="intent")

    repair_prompt = provider.calls[1].prompt
    assert "count" in repair_prompt
    assert "greater than or equal to 0" in repair_prompt


async def test_an_invented_field_triggers_the_repair_loop() -> None:
    """Why Phase 2 chose extra='forbid'.

    A silently dropped field would produce a plausible object missing information nobody
    noticed was absent.
    """
    provider = EchoProvider(
        responses={
            "intent": [
                '{"name": "ok", "count": 1, "invented": "surprise"}',
                '{"name": "ok", "count": 1}',
            ]
        }
    )

    result = await generate_structured(provider, Simple, "prompt", role="intent")
    assert result.count == 1
    assert len(provider.calls) == 2


async def test_exhausting_the_repair_budget_raises_with_the_raw_text() -> None:
    """This layer never substitutes a guess. The caller decides to degrade or fail."""
    provider = EchoProvider(responses={"intent": ["still not json"]})

    with pytest.raises(StructuredOutputError) as exc_info:
        await generate_structured(provider, Simple, "prompt", role="intent", max_repairs=1)

    err = exc_info.value
    assert err.attempts == 2
    assert err.raw_text == "still not json"
    assert err.role == "intent"
    assert err.validation_errors


async def test_repair_budget_of_zero_means_one_attempt() -> None:
    provider = EchoProvider(responses={"intent": ["bad"]})
    with pytest.raises(StructuredOutputError) as exc_info:
        await generate_structured(provider, Simple, "prompt", role="intent", max_repairs=0)
    assert exc_info.value.attempts == 1
    assert len(provider.calls) == 1


async def test_the_schema_is_injected_into_the_request() -> None:
    """The prompt states intent; the schema states shape."""
    provider = EchoProvider(responses={"intent": ['{"name": "a", "count": 0}']})
    await generate_structured(provider, Simple, "prompt", role="intent")

    hint = provider.calls[0].schema_hint
    assert "properties" in hint
    assert "count" in hint


# --- telemetry -----------------------------------------------------------------


def test_repair_rate_counts_only_successful_results() -> None:
    collector = TelemetryCollector()
    collector.add(LLMCallRecord(role="planner", model="m", ok=False, repair_attempt=0))
    collector.add(LLMCallRecord(role="planner", model="m", ok=True, repair_attempt=1))
    collector.add(LLMCallRecord(role="planner", model="m", ok=True, repair_attempt=0))

    assert collector.total_calls == 3
    assert collector.repair_rate == pytest.approx(0.5)


async def test_telemetry_reaches_the_run_timeline() -> None:
    from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
    from app.schemas.common import new_run_id
    from app.schemas.event import EventType

    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    provider = EchoProvider(responses={"intent": ['{"name": "a", "count": 1}']})

    await generate_structured(provider, Simple, "prompt", role="intent", emit=emitter)

    calls = memory.of_type(EventType.LLM_CALL_COMPLETED)
    assert len(calls) == 1
    assert calls[0].payload["role"] == "intent"
    assert calls[0].payload["ok"] is True


async def test_telemetry_events_carry_no_prompt_or_completion_text() -> None:
    """Counts and timings, never content (invariant #3)."""
    from app.core.events import EventBus, MemoryEventSink, RunEventEmitter
    from app.schemas.common import new_run_id
    from app.schemas.event import EventType

    memory = MemoryEventSink()
    emitter = RunEventEmitter(EventBus([memory]), new_run_id())
    provider = EchoProvider(responses={"intent": ['{"name": "secret-value", "count": 1}']})

    await generate_structured(
        provider, Simple, "confidential prompt text", role="intent", emit=emitter
    )

    payload = memory.of_type(EventType.LLM_CALL_COMPLETED)[0].payload
    serialized = json.dumps(payload)
    assert "confidential prompt text" not in serialized
    assert "secret-value" not in serialized


# --- EchoProvider --------------------------------------------------------------


async def test_echo_satisfies_the_provider_protocol() -> None:
    """The abstraction is only real if something other than Ollama implements it."""
    provider: LLMProvider = EchoProvider()
    assert isinstance(provider, LLMProvider)
    assert await provider.health() is True


async def test_echo_raises_loudly_when_no_fixture_exists() -> None:
    """A silently synthesized response would let a test pass while proving nothing."""
    provider = EchoProvider()
    with pytest.raises(NoFixtureError, match="no fixture for role"):
        await provider.complete(CompletionRequest(prompt="hello", role="planner"))


async def test_echo_repeats_its_last_queued_response() -> None:
    provider = EchoProvider(responses={"r": ["only"]})
    first = await provider.complete(CompletionRequest(prompt="a", role="r"))
    second = await provider.complete(CompletionRequest(prompt="b", role="r"))
    assert first.text == second.text == "only"


async def test_echo_reads_a_recorded_fixture(tmp_path: Path) -> None:
    provider = EchoProvider(fixture_dir=tmp_path)
    request = CompletionRequest(prompt="investigate this", role="intent")
    path = tmp_path / f"{fixture_key('intent', request.prompt)}.json"
    path.write_text('{"name": "from-fixture", "count": 3}', encoding="utf-8")

    response = await provider.complete(request)
    assert "from-fixture" in response.text


def test_fixture_keys_are_stable_and_prompt_specific() -> None:
    assert fixture_key("intent", "abc") == fixture_key("intent", "abc")
    assert fixture_key("intent", "abc") != fixture_key("intent", "abd")
    assert fixture_key("intent", "abc") != fixture_key("planner", "abc")


async def test_echo_embeddings_are_deterministic() -> None:
    """Reproducible in tests, and meaningless as a quality signal - by design."""
    provider = EchoProvider(embedding_dim=8)
    a = await provider.embed(["hello"])
    b = await provider.embed(["hello"])
    c = await provider.embed(["goodbye"])

    assert a.vectors == b.vectors
    assert a.vectors != c.vectors
    assert a.dimensions == 8


# --- schema synthesis ----------------------------------------------------------


def test_synthesis_produces_a_schema_valid_instance() -> None:
    instance = synthesize_from_schema(Simple.model_json_schema())
    assert Simple.model_validate(instance)


def test_synthesis_satisfies_pattern_constrained_identifiers() -> None:
    """The project's id patterns must round-trip, or synthesis is useless for our schemas."""
    from app.schemas.task import Task

    instance = synthesize_from_schema(Task.model_json_schema())
    assert Task.model_validate(instance)


def test_synthesis_respects_enums_and_minimums() -> None:
    schema = {
        "type": "object",
        "properties": {
            "mode": {"enum": ["A", "B"]},
            "n": {"type": "integer", "minimum": 5},
        },
        "required": ["mode", "n"],
    }
    result = synthesize_from_schema(schema)
    assert result == {"mode": "A", "n": 5}


async def test_synthesis_mode_serves_unfixtured_roles() -> None:
    provider = EchoProvider(synthesize=True)
    result = await generate_structured(provider, Simple, "prompt", role="intent")
    assert isinstance(result, Simple)


# --- prompt library ------------------------------------------------------------


def test_prompt_is_parsed_with_front_matter(tmp_path: Path) -> None:
    (tmp_path / "intent.md").write_text(
        "---\nrole: intent\nversion: 3\noutput_schema: app.schemas.intent.Intent\nphase: 6\n"
        "---\n\nAnalyse the objective: {{objective}}\n",
        encoding="utf-8",
    )
    asset = PromptLibrary(tmp_path).get("intent")

    assert asset.version == 3
    assert asset.phase == 6
    assert asset.output_schema == "app.schemas.intent.Intent"
    assert asset.variables == {"objective"}


def test_render_substitutes_variables(tmp_path: Path) -> None:
    (tmp_path / "p.md").write_text("Objective: {{objective}}", encoding="utf-8")
    rendered = PromptLibrary(tmp_path).get("p").render(objective="find contradictions")
    assert rendered == "Objective: find contradictions"


def test_render_refuses_to_leave_a_placeholder_unfilled(tmp_path: Path) -> None:
    """An unfilled `{{document_text}}` reaching the model produces confidently wrong
    output rather than an error."""
    (tmp_path / "p.md").write_text("A: {{a}} B: {{b}}", encoding="utf-8")
    with pytest.raises(KeyError, match="'b'"):
        PromptLibrary(tmp_path).get("p").render(a="1")


def test_a_missing_prompt_fails_with_a_useful_message(tmp_path: Path) -> None:
    with pytest.raises(PromptNotFoundError, match="versioned assets"):
        PromptLibrary(tmp_path).get("nonexistent")


def test_prompt_without_front_matter_still_loads(tmp_path: Path) -> None:
    (tmp_path / "bare.md").write_text("Just a prompt body.", encoding="utf-8")
    asset = PromptLibrary(tmp_path).get("bare")
    assert asset.role == "bare"
    assert asset.version == 1


def test_versions_reports_only_loaded_prompts(tmp_path: Path) -> None:
    """A run's stamp describes what it used, not what happened to be on disk."""
    (tmp_path / "a.md").write_text("---\nversion: 2\n---\nA", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\nversion: 7\n---\nB", encoding="utf-8")

    library = PromptLibrary(tmp_path)
    assert library.versions() == {}
    library.get("a")
    assert library.versions() == {"a": 2}


# --- schema echo ---------------------------------------------------------------


def test_a_model_echoing_the_schema_still_yields_its_answer() -> None:
    """Observed with qwen3:4b: the model returns the schema *and* the data.

    Under extra="forbid" that rejected a perfectly good answer because of the wrapper it
    arrived in.
    """
    from app.llm.structured import strip_schema_echo

    payload = {
        "$defs": {"Simple": {"type": "object"}},
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Simple",
        "name": "recovered",
        "count": 3,
    }
    cleaned = strip_schema_echo(payload, Simple)

    assert cleaned == {"name": "recovered", "count": 3}
    assert Simple.model_validate(cleaned)


def test_stripping_never_removes_a_declared_field() -> None:
    """A schema whose own field is called `type` or `description` must be untouched."""
    from app.llm.structured import strip_schema_echo

    class Shaped(JarvisModel):
        type: str
        description: str

    payload = {"type": "report", "description": "a real value", "$defs": {}}
    assert strip_schema_echo(payload, Shaped) == {"type": "report", "description": "a real value"}


def test_a_clean_payload_is_returned_unchanged() -> None:
    from app.llm.structured import strip_schema_echo

    payload = {"name": "a", "count": 1}
    assert strip_schema_echo(payload, Simple) == payload


def test_a_response_of_pure_schema_is_left_for_validation_to_reject() -> None:
    """Stripping everything would hide the real problem behind an empty object."""
    from app.llm.structured import strip_schema_echo

    payload = {"$defs": {}, "title": "Simple"}
    assert strip_schema_echo(payload, Simple) == payload


def test_a_list_payload_passes_through() -> None:
    from app.llm.structured import strip_schema_echo

    assert strip_schema_echo([1, 2, 3], Simple) == [1, 2, 3]


async def test_the_repair_loop_recovers_a_schema_wrapped_answer() -> None:
    """End to end: no repair attempt is spent on a wrapper."""
    collector = get_collector()
    collector.clear()
    provider = EchoProvider(
        responses={
            "intent": [
                '{"$defs": {"x": {}}, "title": "Simple", "name": "ok", "count": 2}',
            ]
        }
    )

    result = await generate_structured(provider, Simple, "prompt", role="intent")

    assert result.name == "ok"
    assert collector.records[-1].repair_attempt == 0, "recovered without spending a repair"
