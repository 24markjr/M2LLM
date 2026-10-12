"""The knowledge tool: the knowledge layer's findings, as an observation reasoning can cite.

Phase 30.

Serves `KNOWLEDGE_GRAPH`, which `extract_entities` and `extract_claims` tasks route to. It is
deterministic and calls no model: the run's knowledge base was built before execution, and this
tool reads it from `ToolContext.knowledge`.

**Conflicts come first, each side as its own item, naming the other side.** One line per claim, on
the line it was found:

    aurora_financial_report.txt:r12  Project Aurora.completion_date = 14 May 2026
                                     [conflicts with aurora_project_report.txt:r10 = 30 April 2026]

That is the pairing a 4B reasoning model will not reliably make by itself (BUG-005, BUG-012). The
tool supplies the pair, and the reasoning engine still has to state the finding. The evidence
binder, the comparative rule, the relevance gate and verification still judge it. A conflict here
is never a finding by itself: Experiment 005 measured one false conflict per run from a misread
value.

`mode` selects what is returned: `conflicts` (the knowledge pass, which wants only the pairs) or
`all` (conflicts, then other grounded claims, capped). With no knowledge base, because the layer is
disabled or was never built, the tool falls back to the regex extraction these task types used
before Phase 30, and says so in its note.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from app.schemas.common import CostHint, FailureClass, JarvisModel
from app.schemas.knowledge import KnowledgeClaim, KnowledgeSnapshot
from app.schemas.tool import ToolCall, ToolCapability, ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.builtin import DocumentExtractTool, Extraction, ExtractOutput
from app.tools.loader import cap

# Claims returned beside the conflicts in `all` mode. Each becomes a line in the reasoning prompt,
# and a flood of single-source facts is what produced restatements in the first place (BUG-005).
MAX_CLAIMS = 30
MAX_CONFLICT_ITEMS = 40


class KnowledgeInput(JarvisModel):
    mode: Literal["all", "conflicts"] = "all"
    pattern: str = Field(default="", description="Used only by the regex fallback")


def conflict_items(snapshot: KnowledgeSnapshot) -> list[Extraction]:
    """One item per claim on each side of each conflict, naming what it conflicts with."""
    claims = {c.claim_id: c for c in snapshot.claims}
    items: list[Extraction] = []
    for conflict in snapshot.conflicts:
        for index, side in enumerate(conflict.sides):
            others = [s for i, s in enumerate(conflict.sides) if i != index]
            against = "; ".join(f"{o.sources[0]} = {o.value}" for o in others)
            for claim_id in side.claim_ids:
                claim = claims.get(claim_id)
                if claim is None or claim.line is None:
                    continue
                items.append(
                    Extraction(
                        document_id=claim.document_id,
                        line=claim.line,
                        value=(
                            f"{conflict.entity_name}.{conflict.attribute} = {side.value} "
                            f"[conflicts with {against}]"
                        ),
                        kind="conflict",
                    )
                )
    return items


def claim_items(snapshot: KnowledgeSnapshot, exclude: set[str]) -> list[Extraction]:
    names = {e.entity_id: e.name for e in snapshot.entities}

    def item(claim: KnowledgeClaim) -> Extraction:
        return Extraction(
            document_id=claim.document_id,
            line=claim.line or 1,
            value=f"{names.get(claim.entity_id, claim.entity_id)}.{claim.attribute} = "
            f"{claim.value}",
            kind="claim",
        )

    return [item(c) for c in snapshot.claims if c.grounded and c.claim_id not in exclude and c.line]


class KnowledgeGraphTool(Tool):
    name = "knowledge_graph"
    description = (
        "Entities and claims extracted from every document, and the claims that conflict across "
        "sources, each with both citations."
    )
    capabilities: ClassVar[set[ToolCapability]] = {ToolCapability.KNOWLEDGE_GRAPH}
    input_schema = KnowledgeInput
    output_schema = ExtractOutput
    cost_hint = CostHint.LOW

    def __init__(self) -> None:
        self._fallback = DocumentExtractTool()

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        try:
            payload = KnowledgeInput.model_validate(call.arguments)
        except Exception as exc:  # noqa: BLE001 - tools classify, they do not raise
            return self.failure(call, FailureClass.SCHEMA_VIOLATION, str(exc))

        snapshot = ctx.knowledge
        if snapshot is None:
            return with_cyber(self, call, await self._regex_fallback(call, payload, ctx), ctx)

        conflicts = conflict_items(snapshot)[:MAX_CONFLICT_ITEMS]
        items = list(conflicts)
        note = f"{len(snapshot.conflicts)} conflict(s) across sources"
        if payload.mode == "all":
            in_conflict = {
                claim_id
                for conflict in snapshot.conflicts
                for side in conflict.sides
                for claim_id in side.claim_ids
            }
            claims, claim_cap = cap(claim_items(snapshot, in_conflict), MAX_CLAIMS)
            items += claims
            note += f"; {claim_cap.note() or f'{len(claims)} other claim(s)'}"

        sources = list(
            dict.fromkeys(
                c.source
                for c in snapshot.claims
                if any(i.document_id == c.document_id and i.line == c.line for i in items)
            )
        )
        return with_cyber(
            self,
            call,
            self.success(
                call,
                ExtractOutput(extractions=items, note=note).model_dump(),
                sources=sources,
            ),
            ctx,
        )

    async def _regex_fallback(
        self, call: ToolCall, payload: KnowledgeInput, ctx: ToolContext
    ) -> ToolResult:
        inner = ToolCall(
            tool_name=self._fallback.name,
            arguments={"pattern": payload.pattern, "document_ids": list(ctx.documents)},
        )
        result = await self._fallback.execute(inner, ctx)
        if result.failed:
            return result
        output = dict(result.output)
        output["note"] = "knowledge layer not built for this run; regex extraction used. " + str(
            output.get("note", "")
        )
        return self.success(call, output, sources=result.sources)


# --- security logs (Phase 52) ----------------------------------------------------------------------

# Items added from security logs. A decoded command or an observed connection is what a 4B reasoning
# model does not derive by itself: measured, it reported "PowerShell ran on WS-12" three times and
# never the address the encoded command fetched from.
MAX_CYBER_ITEMS = 30


def cyber_items(documents: dict[str, str], page_starts: dict[str, list[int]]) -> list[Extraction]:
    """Decoded commands and observed relations from any event logs among the documents, each on
    the line that states it. Deterministic; empty when no document holds events."""
    from app.cyber.analysis import analyse

    analysis = analyse(documents, page_starts)
    if analysis.events == 0:
        return []
    items: list[Extraction] = []

    def at(locator: str, value: str, kind: str) -> None:
        name, _, position = locator.rpartition(":")
        if position.startswith("r"):
            items.append(
                Extraction(document_id=name, line=int(position[1:]), value=value, kind=kind)
            )

    for command in analysis.decoded_commands:
        at(
            command.locator,
            f"decoded -EncodedCommand on {command.host or 'the host'}: {command.script[:300]}",
            "decoded_command",
        )
    for relation in analysis.relations:
        subject = relation.subject.split(":", 1)[-1]
        target = relation.object.split(":", 1)[-1]
        detail = f" ({relation.detail})" if relation.detail else ""
        for locator in relation.sources[:2]:
            at(locator, f"{subject} {relation.predicate} {target}{detail}", "observed_relation")
    return items[:MAX_CYBER_ITEMS]


def with_cyber(tool: Tool, call: ToolCall, result: ToolResult, ctx: ToolContext) -> ToolResult:
    """The knowledge tool's result, with what the run's security logs show appended (Phase 52)."""
    if result.failed:
        return result
    extra = cyber_items(ctx.documents, ctx.page_starts)
    if not extra:
        return result
    output = dict(result.output)
    output["extractions"] = [*output.get("extractions", []), *(e.model_dump() for e in extra)]
    output["note"] = (
        f"{output.get('note', '')}; {len(extra)} item(s) from security logs "
        "(decoded commands, observed relations)"
    ).lstrip("; ")
    sources = list(dict.fromkeys([*result.sources, *(f"{e.document_id}:r{e.line}" for e in extra)]))
    return tool.success(call, output, sources=sources)
