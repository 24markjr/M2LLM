"""Demo readiness: one deadline for a whole run, so a run always finishes with what it has."""

from __future__ import annotations

import time

import pytest

from app.core import deadline
from app.intelligence.execution.engine import ExecutionEngine


@pytest.fixture(autouse=True)
def _no_deadline_left_over() -> None:
    deadline.clear()


def test_outside_a_run_there_is_no_deadline() -> None:
    assert deadline.remaining() is None
    assert deadline.used_share() == 0.0
    assert not deadline.past(0.1)


def test_the_share_used_grows_and_the_deadline_passes() -> None:
    deadline.start(0.2)
    assert not deadline.past(0.9)
    time.sleep(0.25)
    assert deadline.past(1.0)
    assert deadline.remaining() == 0.0


def test_an_engine_started_late_gets_only_what_is_left(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug: each engine started its own clock with the full limit, so a run's later stages
    could each take the whole limit again."""
    deadline.start(30.0)
    engine = ExecutionEngine.__new__(ExecutionEngine)
    ExecutionEngine.__init__(engine, graph=None, registry=None, router=None)  # type: ignore[arg-type]
    assert engine.budget.wallclock_limit_s <= 30.0


def test_outside_a_run_an_engine_keeps_its_configured_budget() -> None:
    engine = ExecutionEngine.__new__(ExecutionEngine)
    ExecutionEngine.__init__(engine, graph=None, registry=None, router=None)  # type: ignore[arg-type]
    assert engine.budget.wallclock_limit_s > 30.0
