"""Structured output with a repair loop.

This is the highest-risk component in the project. Every intelligence engine depends on
getting a valid typed object out of a 4B local model, and small models get strict JSON wrong
often enough that a plain retry is not an answer.

The loop:

1. Call the model with the JSON schema injected and provider-level JSON mode on
2. Extract JSON from the response — models wrap it in fences and prose
3. Validate against the Pydantic model
4. On `ValidationError`, re-prompt **with the validation errors appended**. Telling the
   model *"evidence.0.locator.page: Input should be a valid integer"* fixes far more than
   asking it to try again.
5. After `max_repairs`, raise `StructuredOutputError` carrying the raw text. The caller
   decides whether to degrade the task or fail it; this layer never substitutes a guess.

Repair counts are telemetry, not a hidden implementation detail: a model needing two repairs
per call is a different engineering proposition from one needing none, and Phase 20 reports
it as a metric.

The Phase 2 decision to use `extra="forbid"` on every schema is what makes step 4 work — a
model inventing a field fails validation loudly instead of producing a plausible object with
information silently dropped.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from app.core.agent_config import get_models_config
from app.core.logging import get_logger
from app.llm.errors import StructuredOutputError
from app.llm.provider import CompletionRequest, LLMProvider
from app.llm.telemetry import LLMCallRecord, record_call

log = get_logger(__name__)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull the JSON object out of a model response.

    Models wrap JSON in code fences, prefix it with "Here is the result:", or append a
    closing remark. Tolerating that is not sloppiness — it is the actual behaviour of the
    models this system is built for, and refusing to parse it would burn repair attempts on
    a formatting quirk rather than a real schema failure.
    """
    stripped = text.strip()

    fenced = _FENCE.search(stripped)
    if fenced:
        stripped = fenced.group(1).strip()

    # Take the outermost balanced object or array, starting from whichever opener appears
    # first. Checking "{" first would pull the leading object out of a JSON array and
    # silently return a fragment.
    candidates = [
        (stripped.find(opener), opener, closer)
        for opener, closer in (("{", "}"), ("[", "]"))
        if stripped.find(opener) != -1
    ]
    for start, opener, closer in sorted(candidates):
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return stripped[start : i + 1]
        # Unbalanced: fall through and let validation report it.

    return stripped


def _format_errors(exc: ValidationError) -> str:
    """Render validation errors as instructions the model can act on."""
    lines: list[str] = []
    for err in exc.errors()[:12]:
        location = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {location}: {err['msg']}")
    return "\n".join(lines)


async def generate_structured[T: BaseModel](
    provider: LLMProvider,
    schema: type[T],
    prompt: str,
    *,
    role: str = "default",
    system: str = "",
    max_repairs: int | None = None,
    emit: object | None = None,
) -> T:
    """Get a validated instance of `schema` from the model, repairing if needed.

    Raises `StructuredOutputError` if the model cannot produce valid output within the
    repair budget.
    """
    config = get_models_config()
    params = config.params_for(role) if role in config.roles else config.params_for("intent")
    budget = config.structured_output.max_repairs if max_repairs is None else max_repairs

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    current_prompt = prompt
    last_text = ""
    last_errors = ""

    for attempt in range(budget + 1):
        response = await provider.complete(
            CompletionRequest(
                prompt=current_prompt,
                system=system,
                role=role,
                temperature=params.temperature,
                seed=params.seed,
                top_p=params.top_p,
                max_tokens=params.max_tokens,
                json_mode=params.format == "json",
                think=params.think,
                schema_hint=schema_json,
            )
        )
        last_text = response.text

        try:
            payload = json.loads(extract_json(response.text))
            result = schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_errors = (
                _format_errors(exc)
                if isinstance(exc, ValidationError)
                else f"- (root): response was not valid JSON: {exc}"
            )
            await record_call(
                LLMCallRecord(
                    role=role,
                    model=response.model,
                    latency_ms=response.latency_ms,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    repair_attempt=attempt,
                    ok=False,
                    schema_name=schema.__name__,
                ),
                emit=emit,
            )

            if attempt >= budget:
                break

            log.warning(
                "structured_output_repair",
                role=role,
                schema=schema.__name__,
                attempt=attempt + 1,
                of=budget,
            )
            current_prompt = (
                f"{prompt}\n\n"
                "Your previous response could not be used. These validation errors were "
                "reported:\n"
                f"{last_errors}\n\n"
                "Return corrected JSON matching the schema exactly. Output only the JSON "
                "object, with no commentary and no code fences."
            )
            continue

        await record_call(
            LLMCallRecord(
                role=role,
                model=response.model,
                latency_ms=response.latency_ms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                repair_attempt=attempt,
                ok=True,
                schema_name=schema.__name__,
            ),
            emit=emit,
        )
        return result

    raise StructuredOutputError(
        f"{schema.__name__} could not be produced for role '{role}' after {budget + 1} attempt(s)",
        raw_text=last_text,
        attempts=budget + 1,
        validation_errors=last_errors,
        role=role,
    )
