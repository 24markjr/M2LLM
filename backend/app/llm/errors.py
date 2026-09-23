"""LLM layer errors, classified so callers can decide rather than guess."""

from __future__ import annotations

from app.schemas.common import FailureClass


class LLMError(RuntimeError):
    """Base for everything this layer raises."""

    failure_class: FailureClass = FailureClass.INTERNAL_ERROR


class ProviderUnavailableError(LLMError):
    """The model could not be reached. Transient — the execution engine may retry."""

    failure_class = FailureClass.PROVIDER_UNAVAILABLE


class ProviderTimeoutError(LLMError):
    failure_class = FailureClass.TIMEOUT


class StructuredOutputError(LLMError):
    """The model would not produce output matching the schema, after repairs.

    Carries the raw text and the validation errors so the caller can record what actually
    happened. Permanent from the LLM layer's perspective: the caller decides whether to
    degrade the task or fail it, and never quietly substitutes a guess.
    """

    failure_class = FailureClass.SCHEMA_VIOLATION

    def __init__(
        self,
        message: str,
        *,
        raw_text: str = "",
        attempts: int = 0,
        validation_errors: str = "",
        role: str = "",
    ) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.attempts = attempts
        self.validation_errors = validation_errors
        self.role = role


class PromptNotFoundError(LLMError):
    """A prompt asset is missing. A startup-time failure, not a runtime surprise."""

    failure_class = FailureClass.NOT_FOUND
