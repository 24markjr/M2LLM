"""v4 Phase 1c: customer organisations with isolated data, and no file paths through the API."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import aclosing
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.api.recording import _ours
from app.api.registry import MissionRecord, get_registry, reset_registry
from app.auth import ratelimit, service
from app.auth.tenancy import (
    DEFAULT_ORG,
    is_bare_name,
    scoped_workspace,
    uploads_dir,
    use_org,
    visible_workspace,
)
from app.core.config import get_settings
from app.schemas.common import new_run_id
from app.schemas.objective import Objective
from app.tools.loader import resolve_upload

OPERATOR = ("operator@tessera.test", "Operat0r-Password!")
CUSTOMER = ("admin@acme.test", "Acme-Admin-Pass1")


@pytest.fixture(autouse=True)
def _accounts_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "admin_email", OPERATOR[0])
    monkeypatch.setattr(settings, "admin_password", OPERATOR[1])
    service.reset_memory_store()
    service._failures.clear()
    ratelimit.reset()
    reset_registry()
    yield
    reset_registry()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _signed_in(email: str, password: str) -> AsyncClient:
    client = _client()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client


async def _two_organisations() -> tuple[AsyncClient, AsyncClient]:
    """The operator (default organisation) and the admin of a new customer, `acme`."""
    operator = await _signed_in(*OPERATOR)
    created = await operator.post(
        "/api/v1/auth/organisations",
        json={
            "org_id": "acme",
            "admin": {"email": CUSTOMER[0], "password": CUSTOMER[1], "name": "Acme admin"},
        },
    )
    assert created.status_code == 201, created.text
    return operator, await _signed_in(*CUSTOMER)


def _run_of(org: str) -> MissionRecord:
    with use_org(org):
        record = MissionRecord(new_run_id(), Objective(text="Check the reports."), ["r.txt"])
    get_registry()._missions[record.run_id] = record
    return record


# --- organisations -------------------------------------------------------------------------


async def test_only_the_operator_creates_and_lists_organisations() -> None:
    operator, customer = await _two_organisations()
    async with aclosing(operator), aclosing(customer):
        listed = (await operator.get("/api/v1/auth/organisations")).json()
        assert {o["org_id"] for o in listed} == {DEFAULT_ORG, "acme"}
        assert (await customer.get("/api/v1/auth/organisations")).status_code == 403
        again = await operator.post(
            "/api/v1/auth/organisations",
            json={"org_id": "acme", "admin": {"email": "x@y.test", "password": CUSTOMER[1]}},
        )
        assert again.status_code == 409
        me = (await customer.get("/api/v1/auth/me")).json()
        assert me["org_id"] == "acme" and me["role"] == "admin"
        # A customer's admin manages their own people only.
        people = (await customer.get("/api/v1/auth/users")).json()
        assert [p["email"] for p in people] == [CUSTOMER[0]]


# --- runs ----------------------------------------------------------------------------------


async def test_a_run_is_invisible_to_another_organisation() -> None:
    operator, customer = await _two_organisations()
    theirs = _run_of("acme")
    ours = _run_of(DEFAULT_ORG)
    async with aclosing(operator), aclosing(customer):
        assert [m["run_id"] for m in (await customer.get("/api/v1/missions")).json()] == [
            theirs.run_id
        ]
        assert [m["run_id"] for m in (await operator.get("/api/v1/missions")).json()] == [
            ours.run_id
        ]
        assert (await customer.get(f"/api/v1/missions/{theirs.run_id}")).status_code == 200
        # Every route that names the run - not only the ones that look it up - answers 404.
        for path in ("", "/findings", "/events", "/knowledge", "/reviews", "/report.md"):
            response = await operator.get(f"/api/v1/missions/{theirs.run_id}{path}")
            assert response.status_code == 404, path
        assert (await customer.delete(f"/api/v1/missions/{ours.run_id}")).status_code == 404
    assert get_registry().owner(ours.run_id) == DEFAULT_ORG


async def test_a_run_the_server_no_longer_holds_is_the_default_organisations() -> None:
    operator, customer = await _two_organisations()
    async with aclosing(operator), aclosing(customer):
        unknown = await customer.get("/api/v1/missions/run_0123456789ab/knowledge")
        assert unknown.status_code == 404


# --- cases, uploads, evidence, audit -------------------------------------------------------


async def test_cases_are_per_organisation() -> None:
    operator, customer = await _two_organisations()
    async with aclosing(operator), aclosing(customer):
        opened = await customer.post("/api/v1/cases", json={"title": "Acme vendor fraud"})
        assert opened.status_code == 201, opened.text
        case_id = opened.json()["case_id"]
        listed = (await customer.get("/api/v1/cases")).json()["cases"]
        assert [c["case"]["case_id"] for c in listed] == [case_id]
        assert (await operator.get("/api/v1/cases")).json()["cases"] == []
        assert (await operator.get(f"/api/v1/cases/{case_id}")).status_code == 404
        assert (await operator.delete(f"/api/v1/cases/{case_id}")).status_code == 404
        assert (await customer.get(f"/api/v1/cases/{case_id}")).status_code == 200


async def test_uploads_evidence_and_audit_are_per_organisation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(type(get_settings()), "agent_dir", property(lambda _self: tmp_path))
    operator, customer = await _two_organisations()
    memo = ("memo.txt", b"Invoice INV-1042 was paid twice to Blue Harbor.\n", "text/plain")
    async with aclosing(operator), aclosing(customer):
        up = await customer.post("/api/v1/documents", files={"files": memo})
        assert up.status_code == 201, up.text
        theirs = up.json()[0]["evidence_id"]
        assert (uploads_dir("acme") / "memo.txt").is_file()
        assert not (uploads_dir(DEFAULT_ORG) / "memo.txt").exists()

        assert [d["name"] for d in (await customer.get("/api/v1/documents")).json()] == ["memo.txt"]
        mine = (await operator.get("/api/v1/documents")).json()
        assert "memo.txt" not in [d["name"] for d in mine]

        # The operator cannot investigate the customer's file by naming it.
        run = await operator.post(
            "/api/v1/missions", json={"objective": "Read the memo.", "documents": ["memo.txt"]}
        )
        assert run.status_code == 422
        assert run.json()["error_code"] == "NO_READABLE_DOCUMENTS"

        assert (await operator.get(f"/api/v1/evidence/{theirs}")).status_code == 404
        listed = (await operator.get("/api/v1/evidence")).json()["items"]
        assert theirs not in [i["evidence_id"] for i in listed]

        # The same bytes from two organisations are two items, each with its own custody.
        ours = (await operator.post("/api/v1/documents", files={"files": memo})).json()[0]
        assert ours["evidence_id"] and ours["evidence_id"] != theirs

        audit = (await operator.get("/api/v1/audit")).json()
        assert all(CUSTOMER[0] != e["actor"] for e in audit)
        assert any(CUSTOMER[0] == e["actor"] for e in (await customer.get("/api/v1/audit")).json())


# --- no file paths through the API --------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "/proc/self/environ",
        "/etc/hosts",
        "../uploads/memo.txt",
        "..\\..\\.env",
        "C:\\Windows\\win.ini",
        ".env",
        "..",
        "",
    ],
)
def test_the_api_resolves_bare_names_only(name: str) -> None:
    assert not is_bare_name(name) or name == ".env"
    assert not resolve_upload(name).exists()


def test_a_real_file_named_by_its_path_is_not_resolved() -> None:
    real = Path(__file__).resolve()
    assert real.is_file()
    assert not resolve_upload(str(real)).exists()
    assert resolve_upload("aurora_financial_report.txt").is_file()  # a fixture, by name


async def test_a_mission_cannot_read_a_server_file_by_path() -> None:
    this_file = str(Path(__file__).resolve())  # noqa: ASYNC240 - once, before any request
    operator = await _signed_in(*OPERATOR)
    async with aclosing(operator):
        for path in (this_file, "/etc/hosts", "/proc/self/environ"):
            response = await operator.post(
                "/api/v1/missions", json={"objective": "Read the file.", "documents": [path]}
            )
            assert response.status_code == 422, path
            assert response.json()["error_code"] == "NO_READABLE_DOCUMENTS"


# --- workspaces and recordings --------------------------------------------------------------


def test_workspaces_are_named_within_an_organisation() -> None:
    assert scoped_workspace("main") == "main"
    assert visible_workspace("main") == "main"
    assert visible_workspace("acme~main") is None
    with use_org("acme"):
        assert scoped_workspace("main") == "acme~main"
        assert visible_workspace("acme~main") == "main"
        assert visible_workspace("main") is None
        assert visible_workspace("other~main") is None


def test_recordings_belong_to_their_organisation() -> None:
    assert _ours({"run_id": "r"})  # committed and pre-1c recordings: the default organisation's
    assert not _ours({"org_id": "acme"})
    with use_org("acme"):
        assert _ours({"org_id": "acme"})
        assert not _ours({"run_id": "r"})


# --- memory --------------------------------------------------------------------------------


def test_memory_shows_only_the_organisations_own_support() -> None:
    from app.api.v1.memory import _own_facts
    from app.schemas.memory import Fact, FactKind, FactSupport

    theirs, ours = _run_of("acme"), _run_of(DEFAULT_ORG)
    fact = Fact(
        fact_id="f1",
        kind=FactKind.ATTRIBUTE,
        subject="Blue Harbor",
        subject_key="blue harbor",
        predicate="director",
        object="S. Mehta",
        object_key="s. mehta",
        support=[
            FactSupport(run_id=theirs.run_id, source="memo.txt:r2"),
            FactSupport(run_id=ours.run_id, source="po.txt:r1"),
        ],
    )
    only_theirs = fact.model_copy(update={"support": fact.support[:1]})
    assert [f.runs for f in _own_facts([fact])] == [[ours.run_id]]
    assert _own_facts([only_theirs]) == []
    with use_org("acme"):
        assert [f.runs for f in _own_facts([fact, only_theirs])] == [[theirs.run_id]] * 2
