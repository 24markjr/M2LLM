"""The error contract.

Every 4xx and 5xx response has the same shape, and it always carries a code:

    {"error_code": "MISSION_NOT_FOUND", "message": "...", "run_id": "...", "details": {}}

The frontend renders codes, not strings. A client that branches on message text breaks the
moment the wording improves, and a client that gets a raw exception string is being shown
the server's internals - which is both a leak and useless to the person reading it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.schemas.common import JarvisModel

log = get_logger(__name__)


class ErrorResponse(JarvisModel):
    """The body of every failed request."""

    error_code: str
    message: str
    run_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ApiError(Exception):
    """An error with a code the client is expected to handle."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.run_id = run_id
        self.details = details or {}

    def response(self) -> JSONResponse:
        body = ErrorResponse(
            error_code=self.error_code,
            message=self.message,
            run_id=self.run_id,
            details=self.details,
        )
        return JSONResponse(status_code=self.status_code, content=body.model_dump(mode="json"))


class MissionNotFoundError(ApiError):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            "MISSION_NOT_FOUND",
            f"no mission with id {run_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            run_id=run_id,
        )


class MissionNotFinishedError(ApiError):
    """The resource exists but the run has not produced it yet.

    409 rather than 404: the difference between "there is no report" and "there is no report
    *yet*" decides whether the client should retry, and a 404 would tell it to give up.
    """

    def __init__(self, run_id: str, resource: str, stage: str) -> None:
        super().__init__(
            "MISSION_NOT_FINISHED",
            f"this mission has no {resource} yet; it is at stage {stage}",
            status_code=status.HTTP_409_CONFLICT,
            run_id=run_id,
            details={"stage": stage},
        )


def register_error_handlers(app: FastAPI) -> None:
    """Route every failure through the contract, including the ones FastAPI raises itself."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return exc.response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default body has no error_code, so a client cannot branch on it.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=ErrorResponse(
                error_code="INVALID_REQUEST",
                message="the request body did not match the expected shape",
                details={"errors": exc.errors()},
            ).model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=_CODES.get(exc.status_code, "HTTP_ERROR"),
                message=str(exc.detail),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The message is deliberately generic. The detail goes to the log, where it belongs,
        # and the client gets something it can report rather than a stack trace fragment.
        log.exception("unhandled_api_error", path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="the server failed to handle this request",
            ).model_dump(mode="json"),
        )


_CODES = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
}
