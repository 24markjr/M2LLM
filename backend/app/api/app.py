"""The FastAPI application.

A factory rather than a module-level `app`: tests need an application with a clean registry,
and a module-level instance would share run state between them.

The engine is reachable over HTTP from here, but nothing in this package touches a model.
Invariant 1 - the LLM is only ever called through `app/llm/` - holds at this layer because the
API's only route to inference is the orchestrator it hands a provider to.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.registry import reset_registry
from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm import get_provider
from app.schemas.common import JarvisModel

log = get_logger(__name__)

DESCRIPTION = """
An adaptive, evidence-driven investigation engine.

Missions run in the background: `POST /api/v1/missions` returns a run id immediately and
`GET /api/v1/missions/{id}/stream` streams the run as it happens. Every finding carries the
source locators it rests on, and every claim the evidence does not support is reported as
unsupported rather than dropped.
""".strip()


class HealthResponse(JarvisModel):
    status: str
    model: str
    provider_healthy: bool
    version: str = "1"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("api_starting", model=settings.ollama_model, env=settings.app_env)
    yield
    # Missions are background tasks owned by the registry. Dropping it on shutdown cancels
    # them, which is what should happen: a half-finished run has no consumer after the
    # process that was streaming it is gone.
    reset_registry()
    log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="JARVIS",
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=_lifespan,
        # The frontend generates its types from this, so it is a build input, not a nicety.
        openapi_url="/openapi.json",
        docs_url="/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Without this the browser cannot read the header, and SSE reconnection silently
        # loses its place - the one bug that only shows up after a dropped connection.
        expose_headers=["Last-Event-ID"],
    )

    register_error_handlers(app)
    app.include_router(v1_router)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        """Whether the engine can actually run. Reports the model, not just a 200."""
        provider = get_provider()
        healthy = await provider.health()
        return HealthResponse(
            status="ok" if healthy else "degraded",
            model=provider.model_id,
            provider_healthy=healthy,
        )

    return app
