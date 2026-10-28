"""Bhashini, MeitY's language platform, as an optional second engine (v4 Phase 7).

Bhashini serves the same model families JARVIS runs itself (IndicTrans2, IndicConformer, Indic TTS)
on government infrastructure, behind the ULCA pipeline API. Two calls:

1. **Discovery** (`getModelsPipeline`, with the user id and ULCA key from onboarding): which service
   performs a task for a language pair, and the inference endpoint and key to call it with. Cached
   for an hour per task and language pair.
2. **Compute** (the endpoint discovery returned): the task itself.

Every call is bounded by a timeout and retried twice on a server error or a timeout, never on a
refusal. Usage - task, languages, characters or seconds, latency, outcome - goes to the language
usage log (`app/language/usage.py`). Whether a request may come here is decided by
`app/language/routing.py`; this module only talks to Bhashini.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.language import Language

log = get_logger(__name__)

ENGINE_NAME = "bhashini"
DISCOVERY_TTL_S = 3600.0
RETRIES = 2


def record_usage(**usage: Any) -> None:
    """The language usage log, imported when used: `app.language` imports this module."""
    from app.language.usage import record_usage as record

    record(**usage)


class BhashiniError(RuntimeError):
    """Bhashini could not do it: not configured, refused, unreachable or malformed."""


class Bhashini:
    name = ENGINE_NAME

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._discovered: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
        self._versions: dict[tuple[str, str], str] = {}

    @staticmethod
    def configured() -> bool:
        settings = get_settings()
        return bool(settings.bhashini_user_id and settings.bhashini_api_key)

    def version(self, target: str = "en") -> str:
        """The service id discovery last returned for a translation into `target`."""
        found = next((v for (_, t), v in self._versions.items() if t == target), "")
        return found or "bhashini"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=get_settings().bhashini_timeout_s, transport=self._transport
        )

    async def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                async with self._client() as client:
                    response = await client.post(url, headers=headers, json=body)
                if response.status_code >= 500:
                    raise BhashiniError(f"Bhashini answered {response.status_code}")
                if response.status_code >= 400:
                    # A refusal (bad key, quota, unsupported pair) does not improve with a retry.
                    raise _Refused(
                        f"Bhashini refused: {response.status_code} {response.text[:200]}"
                    )
                return response.json()
            except _Refused as exc:
                raise BhashiniError(str(exc)) from exc
            except (httpx.TimeoutException, httpx.TransportError, BhashiniError) as exc:
                last = exc
                if attempt < RETRIES:
                    await asyncio.sleep(0.5 * 2**attempt)
            except ValueError as exc:
                raise BhashiniError(f"Bhashini sent something that is not JSON: {exc}") from exc
        raise BhashiniError(f"Bhashini unreachable after {RETRIES + 1} attempts: {last}")

    async def _discover(self, task: str, language: dict[str, str]) -> dict[str, Any]:
        """The service and endpoint for one task: from cache, else asked of Bhashini."""
        if not self.configured():
            raise BhashiniError("Bhashini is not configured (BHASHINI_USER_ID, BHASHINI_API_KEY)")
        key = (task, language.get("sourceLanguage", ""), language.get("targetLanguage", ""))
        hit = self._discovered.get(key)
        if hit and time.monotonic() - hit[0] < DISCOVERY_TTL_S:
            return hit[1]
        settings = get_settings()
        answer = await self._post(
            settings.bhashini_config_url,
            {"userID": settings.bhashini_user_id, "ulcaApiKey": settings.bhashini_api_key},
            {
                "pipelineTasks": [{"taskType": task, "config": {"language": language}}],
                "pipelineRequestConfig": {"pipelineId": settings.bhashini_pipeline_id},
            },
        )
        try:
            config = answer["pipelineResponseConfig"][0]["config"][0]
            endpoint = answer["pipelineInferenceAPIEndPoint"]
            found = {
                "service_id": config["serviceId"],
                "url": endpoint["callbackUrl"],
                "auth": {endpoint["inferenceApiKey"]["name"]: endpoint["inferenceApiKey"]["value"]},
            }
        except (KeyError, IndexError, TypeError) as exc:
            raise BhashiniError(f"Bhashini offers no {task} for {language}") from exc
        self._discovered[key] = (time.monotonic(), found)
        return found

    async def _compute(
        self, task: str, language: dict[str, str], data: dict[str, Any], extra: dict[str, Any]
    ) -> dict[str, Any]:
        service = await self._discover(task, language)
        answer = await self._post(
            service["url"],
            service["auth"],
            {
                "pipelineTasks": [
                    {
                        "taskType": task,
                        "config": {
                            "language": language,
                            "serviceId": service["service_id"],
                            **extra,
                        },
                    }
                ],
                "inputData": data,
            },
        )
        try:
            result: dict[str, Any] = answer["pipelineResponse"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise BhashiniError("Bhashini's answer has no pipelineResponse") from exc
        self._versions[(language.get("sourceLanguage", ""), language.get("targetLanguage", ""))] = (
            service["service_id"]
        )
        return result

    async def translate(self, lines: list[str], source: Language, target: Language) -> list[str]:
        """One output line per input line; blank lines are not sent."""
        wanted = [i for i, line in enumerate(lines) if line.strip()]
        out = list(lines)
        if not wanted:
            return out
        started = time.perf_counter()
        language = {"sourceLanguage": source.code, "targetLanguage": target.code}
        ok = False
        try:
            result = await self._compute(
                "translation", language, {"input": [{"source": lines[i]} for i in wanted]}, {}
            )
            output = result.get("output") or []
            if len(output) != len(wanted):
                raise BhashiniError(f"Bhashini returned {len(output)} lines for {len(wanted)}")
            for i, item in zip(wanted, output, strict=True):
                out[i] = str(item.get("target", ""))
            ok = True
            return out
        finally:
            record_usage(
                engine=ENGINE_NAME,
                task="translation",
                source=source.code,
                target=target.code,
                amount=sum(len(lines[i]) for i in wanted),
                unit="characters",
                ms=int((time.perf_counter() - started) * 1000),
                ok=ok,
            )

    async def transcribe(self, audio_wav: bytes, language: Language) -> str:
        started = time.perf_counter()
        ok = False
        try:
            result = await self._compute(
                "asr",
                {"sourceLanguage": language.code},
                {"audio": [{"audioContent": base64.b64encode(audio_wav).decode("ascii")}]},
                {"audioFormat": "wav", "samplingRate": 16000},
            )
            ok = True
            return " ".join(str(o.get("source", "")) for o in result.get("output") or []).strip()
        finally:
            record_usage(
                engine=ENGINE_NAME,
                task="asr",
                source=language.code,
                target=language.code,
                amount=len(audio_wav),
                unit="bytes",
                ms=int((time.perf_counter() - started) * 1000),
                ok=ok,
            )

    async def speak(self, text: str, language: Language) -> bytes:
        started = time.perf_counter()
        ok = False
        try:
            result = await self._compute(
                "tts",
                {"sourceLanguage": language.code},
                {"input": [{"source": text}]},
                {"gender": "female"},
            )
            audio = (result.get("audio") or [{}])[0].get("audioContent", "")
            if not audio:
                raise BhashiniError("Bhashini returned no audio")
            ok = True
            return base64.b64decode(audio)
        finally:
            record_usage(
                engine=ENGINE_NAME,
                task="tts",
                source=language.code,
                target=language.code,
                amount=len(text),
                unit="characters",
                ms=int((time.perf_counter() - started) * 1000),
                ok=ok,
            )

    async def transliterate(self, text: str, language: Language) -> str:
        """Roman-script text (`kitna paisa`) in the language's own script (`कितना पैसा`)."""
        started = time.perf_counter()
        ok = False
        try:
            result = await self._compute(
                "transliteration",
                {"sourceLanguage": "en", "targetLanguage": language.code},
                {"input": [{"source": text}]},
                {"isSentence": True},
            )
            output = result.get("output") or [{}]
            target = output[0].get("target", "")
            ok = bool(target)
            return str(target[0] if isinstance(target, list) else target)
        finally:
            record_usage(
                engine=ENGINE_NAME,
                task="transliteration",
                source="en",
                target=language.code,
                amount=len(text),
                unit="characters",
                ms=int((time.perf_counter() - started) * 1000),
                ok=ok,
            )


class _Refused(Exception):
    pass


_client: Bhashini | None = None


def get_bhashini() -> Bhashini:
    global _client
    if _client is None:
        _client = Bhashini()
    return _client
