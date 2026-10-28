"""Data governance (v4 Phase 8): retention, masking, data-subject requests, audit export.

- **Retention** - an organisation keeps finished investigations for `retention_days` (0: until
  deleted). Older ones are deleted the way a person deletes one (`delete_investigation`): the run,
  its archive, recordings, stored timeline and memory. Evidence items and their custody stay -
  custody is append-only by design, and deleting evidence is a legal decision, not a timer's.
- **Masking** - with `mask_personal_data`, exported reports show e-mail addresses, Indian phone,
  Aadhaar, PAN and card numbers as labels ("[aadhaar]"). The stored evidence is never altered:
  masking is of what leaves, not of what is kept.
- **Data-subject requests (DPDP Act 2023)** - find every place a person's identifier appears (the
  text of an investigation's documents, its question and findings, the case conversations), export
  that list, and erase: investigations that hold it are deleted and conversation turns that mention
  it are blanked. Evidence files that hold it are listed for a legal-hold decision, not deleted.
- **Audit export** - the organisation's audit log as CSV.

The policy is kept per organisation beside the run archives (Phase 1c).
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import timedelta
from pathlib import Path

from pydantic import Field

from app.api.registry import get_registry
from app.auth.tenancy import current_org
from app.cases.service import get_case_store
from app.conversation import store as conversations
from app.core.config import get_settings
from app.reporting.document import ReportDocument
from app.review.service import audit, get_review_store
from app.schemas.common import JarvisModel, utcnow


class Policy(JarvisModel):
    retention_days: int = Field(default=0, ge=0, le=3650)
    mask_personal_data: bool = False
    # The organisation's domain pack (v4 Phase 10, `app/packs`): severity phrases, report wording,
    # attribute names, starter questions. "general" changes nothing.
    pack: str = Field(default="general", pattern=r"^[a-z0-9-]{1,48}$")
    # Which material may be sent to Bhashini (v4 Phase 7, `app/language/routing.py`): "off", only
    # "unclassified", or "internal" (Unclassified and Internal). Confidential and Restricted never
    # are, whatever this says; the open-source engine in our cloud serves them.
    bhashini: str = Field(default="off", pattern=r"^(off|unclassified|internal)$")


async def _delete(run_id: str, *, actor: str) -> None:
    """`delete_investigation`, imported when used: the policy is read by the language layer
    outside the API (the benchmark, the CLI), and importing the API package here is circular."""
    from app.api.deletion import delete_investigation

    await delete_investigation(run_id, actor=actor)


def _policy_path() -> Path:
    return get_settings().agent_dir / "runs" / "governance" / f"{current_org()}.json"


def policy() -> Policy:
    path = _policy_path()
    return Policy.model_validate_json(path.read_text("utf-8")) if path.is_file() else Policy()


def save_policy(value: Policy) -> Policy:
    path = _policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.model_dump_json(indent=1), encoding="utf-8")
    return value


# --- masking -------------------------------------------------------------------------------------

# Order matters: an Aadhaar or card number would otherwise be read as a phone number first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("card", re.compile(r"\b(?:\d{4}[ -]?){3}\d{1,7}\b(?=\D|$)")),
    ("aadhaar", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
]


def mask(text: str) -> str:
    for label, pattern in _PATTERNS:
        text = pattern.sub(f"[{label}]", text)
    return text


# --- retention -----------------------------------------------------------------------------------


class RetentionResult(JarvisModel):
    retention_days: int
    dry_run: bool
    deleted: list[str] = Field(default_factory=list)
    kept_running: list[str] = Field(default_factory=list)


async def apply_retention(*, dry_run: bool, actor: str = "retention") -> RetentionResult:
    rule = policy()
    result = RetentionResult(retention_days=rule.retention_days, dry_run=dry_run)
    if rule.retention_days == 0:
        return result
    cutoff = utcnow() - timedelta(days=rule.retention_days)
    for record in get_registry().records():
        if record.created_at >= cutoff:
            continue
        if not record.is_finished():
            result.kept_running.append(record.run_id)
            continue
        if not dry_run:
            await _delete(record.run_id, actor=actor)
        result.deleted.append(record.run_id)
    if result.deleted and not dry_run:
        await audit(
            "governance.retention",
            actor=actor,
            target=f"org:{current_org()}",
            deleted=len(result.deleted),
            retention_days=rule.retention_days,
        )
    return result


# --- data-subject requests -----------------------------------------------------------------------


class SubjectHit(JarvisModel):
    where: str  # document, objective, finding, conversation
    run_id: str = ""
    case_id: str = ""
    location: str = ""
    excerpt: str = ""


class SubjectReport(JarvisModel):
    identifier: str
    hits: list[SubjectHit] = Field(default_factory=list)
    investigations: list[str] = Field(default_factory=list)
    conversations: list[str] = Field(default_factory=list)
    # Evidence files holding it: kept, for a legal-hold decision (custody is append-only).
    evidence_files: list[str] = Field(default_factory=list)
    erased: bool = False


def _excerpt(text: str, at: int, width: int = 60) -> str:
    return text[max(0, at - width) : at + width].replace("\n", " ").strip()


async def find_subject(identifier: str) -> SubjectReport:
    needle = identifier.strip().lower()
    report = SubjectReport(identifier=identifier.strip())
    if len(needle) < 3:
        return report
    runs: set[str] = set()
    files: set[str] = set()
    for record in get_registry().records():
        for name, text in record.texts.items():
            for number, line in enumerate(text.splitlines(), start=1):
                at = line.lower().find(needle)
                if at >= 0:
                    report.hits.append(
                        SubjectHit(
                            where="document",
                            run_id=record.run_id,
                            location=f"{name}:r{number}",
                            excerpt=_excerpt(line, at),
                        )
                    )
                    runs.add(record.run_id)
                    files.add(name)
        if needle in record.objective.text.lower():
            report.hits.append(
                SubjectHit(where="objective", run_id=record.run_id, excerpt=record.objective.text)
            )
            runs.add(record.run_id)
        for finding in record.result.findings if record.result else []:
            if needle in finding.claim.lower():
                report.hits.append(
                    SubjectHit(
                        where="finding",
                        run_id=record.run_id,
                        location=finding.finding_id,
                        excerpt=finding.claim,
                    )
                )
                runs.add(record.run_id)
    for case in await (await get_case_store()).cases():
        thread = conversations.load(case.case_id)
        for turn in thread.turns:
            at = turn.text.lower().find(needle)
            if at >= 0:
                report.hits.append(
                    SubjectHit(
                        where="conversation",
                        case_id=case.case_id,
                        location=turn.turn_id,
                        excerpt=_excerpt(turn.text, at),
                    )
                )
                if case.case_id not in report.conversations:
                    report.conversations.append(case.case_id)
    report.investigations = sorted(runs)
    report.evidence_files = sorted(files)
    return report


async def erase_subject(identifier: str, *, actor: str) -> SubjectReport:
    """Delete the investigations that hold the identifier and blank the conversation turns that
    mention it. Evidence files are reported, not deleted."""
    report = await find_subject(identifier)
    needle = identifier.strip().lower()
    for run_id in report.investigations:
        record = get_registry().get(run_id)
        if record is not None and record.is_finished():
            await _delete(run_id, actor=actor)
    for case_id in report.conversations:
        async with conversations.lock(case_id):
            thread = conversations.load(case_id)
            for turn in thread.turns:
                if needle in turn.text.lower() or any(
                    needle in c.text.lower() for c in turn.claims
                ):
                    turn.text = "[erased under a data-subject request]"
                    turn.claims = []
                    turn.steps = []
            conversations.save(thread)
    report.erased = True
    await audit(
        "governance.subject_erased",
        actor=actor,
        target=f"org:{current_org()}",
        investigations=len(report.investigations),
        conversations=len(report.conversations),
        evidence_files_held=report.evidence_files,
    )
    return report


# --- audit export --------------------------------------------------------------------------------


async def audit_csv(limit: int = 10000) -> str:
    entries = await (await get_review_store()).audit(limit=limit)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["at", "actor", "action", "target", "status_code", "details"])
    for e in entries:
        writer.writerow(
            [
                e.at.isoformat(),
                e.actor,
                e.action,
                e.target,
                e.status_code if e.status_code is not None else "",
                json.dumps(e.details, sort_keys=True),
            ]
        )
    return out.getvalue()


def mask_document(document: ReportDocument) -> ReportDocument:
    """A report with personal details masked, for export under `mask_personal_data`."""
    blocks = [
        block.model_copy(
            update={
                "text": mask(block.text),
                "items": [mask(i) for i in block.items],
                "rows": [
                    [cell.model_copy(update={"text": mask(cell.text)}) for cell in row]
                    for row in block.rows
                ],
                "left": (block.left[0], mask(block.left[1])),
                "right": (block.right[0], mask(block.right[1])),
                "facts": [(k, mask(v)) for k, v in block.facts],
            }
        )
        for block in document.blocks
    ]
    return document.model_copy(
        update={
            "subtitle": mask(document.subtitle),
            "facts": [(k, mask(v)) for k, v in document.facts],
            "blocks": blocks,
        }
    )


RETENTION_EVERY_S = 24 * 3600


async def retention_sweeps() -> None:
    """Apply every organisation's retention once a day, for as long as the server runs."""
    import asyncio

    from app.auth.service import get_auth_store
    from app.auth.tenancy import use_org
    from app.core.logging import get_logger

    log = get_logger(__name__)
    while True:
        await asyncio.sleep(RETENTION_EVERY_S)
        try:
            orgs = sorted({u.org_id for u in await (await get_auth_store()).users()})
            for org in orgs:
                with use_org(org):
                    done = await apply_retention(dry_run=False)
                if done.deleted:
                    log.info("retention_applied", org=org, deleted=len(done.deleted))
        except Exception:
            log.exception("retention_sweep_failed")
