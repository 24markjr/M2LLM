"""Integration test fixtures.

pytest-asyncio gives each test its own event loop, but the engine is cached process-wide.
A pooled connection created under one loop cannot be reused or even closed under the next,
which surfaces as `RuntimeError: Event loop is closed` from deep inside asyncpg.

Disposing the engine after every test keeps each one self-contained. Slower than sharing a
pool, and correct - which is the right trade for a suite that exists to catch real
persistence bugs.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator

import pytest

from app.database.session import dispose_engine

# asyncpg tears down cleanly on the selector loop but not on Windows' default Proactor
# loop, where closing a pooled connection during teardown surfaces as
# "Event loop is closed" from inside the transport. Windows-only, test-only: production
# runs a single loop for the process lifetime and never hits it.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
async def _fresh_engine_per_test() -> AsyncIterator[None]:
    yield
    await dispose_engine()
