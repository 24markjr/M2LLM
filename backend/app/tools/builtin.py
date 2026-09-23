"""The built-in tool set.

Small and domain-specific by design. The interesting engineering here is `CalculatorTool`:
it parses arithmetic with `ast.parse` and walks a node whitelist. No `eval`, no `exec`, no
dynamic import. The specification's "no arbitrary code execution" rule is enforced in the
parser rather than by filtering input strings, and `test_llm_isolation.py` fails the build
if `eval` ever appears anywhere in the application.
"""

from __future__ import annotations

import ast
import csv
import io
import re
import time
from typing import ClassVar

from pydantic import Field

from app.schemas.common import CostHint, FailureClass, JarvisModel
from app.schemas.tool import ToolCall, ToolCapability, ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.loader import MAX_CSV_ROWS, ResultCap, cap


class UnsafeExpressionError(ValueError):
    """An expression contained something outside the arithmetic whitelist."""


# --- calculator ----------------------------------------------------------------

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Tuple,
    ast.Load,
)


def safe_eval(expression: str) -> float:
    """Evaluate an arithmetic expression, or refuse.

    Walks the parsed tree and rejects any node outside the whitelist. `__import__("os")`
    fails because `ast.Call` and `ast.Name` are not allowed, not because the string was
    pattern-matched - string filtering is defeatable, a node whitelist is not.
    """
    if len(expression) > 200:
        raise UnsafeExpressionError("expression too long")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"not a valid expression: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpressionError(f"{type(node).__name__} is not allowed in an expression")
        # Reject exponents large enough to hang the process.
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = node.right
            if isinstance(exponent, ast.Constant) and isinstance(exponent.value, int | float):
                if abs(exponent.value) > 100:
                    raise UnsafeExpressionError("exponent too large")

    return float(_reduce(tree.body))


def _reduce(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise UnsafeExpressionError("only numeric literals are allowed")
        return float(node.value)
    if isinstance(node, ast.UnaryOp):
        value = _reduce(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _reduce(node.left), _reduce(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise UnsafeExpressionError("division by zero")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise UnsafeExpressionError("division by zero")
            return float(left // right)
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise UnsafeExpressionError("division by zero")
            return left % right
        if isinstance(node.op, ast.Pow):
            return float(left**right)
    raise UnsafeExpressionError(f"{type(node).__name__} is not allowed")


class CalculatorInput(JarvisModel):
    expression: str = Field(description="An arithmetic expression, e.g. (450000-380000)/380000")


class CalculatorOutput(JarvisModel):
    value: float
    expression: str


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate an arithmetic expression. Numeric literals and operators only."
    capabilities: ClassVar[set[ToolCapability]] = {ToolCapability.COMPUTATION}
    input_schema = CalculatorInput
    output_schema = CalculatorOutput
    cost_hint = CostHint.LOW
    timeout_s = 10.0

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        started = time.perf_counter()
        try:
            payload = CalculatorInput.model_validate(call.arguments)
        except Exception as exc:  # noqa: BLE001 - tools classify, they do not raise
            return self.failure(call, FailureClass.SCHEMA_VIOLATION, str(exc))

        try:
            value = safe_eval(payload.expression)
        except UnsafeExpressionError as exc:
            return self.failure(call, FailureClass.UNSAFE_EXPRESSION, str(exc))

        return self.success(
            call,
            CalculatorOutput(value=value, expression=payload.expression).model_dump(),
            execution_time_ms=int((time.perf_counter() - started) * 1000),
        )


# --- document search -----------------------------------------------------------


class SearchInput(JarvisModel):
    query: str
    scope: list[str] = Field(default_factory=list)
    k: int = Field(default=5, ge=1, le=50)


class Passage(JarvisModel):
    document_id: str
    line: int
    text: str
    score: float


class SearchOutput(JarvisModel):
    passages: list[Passage] = Field(default_factory=list)
    cap: ResultCap = Field(default_factory=ResultCap)
    note: str = ""


class DocumentSearchTool(Tool):
    """Keyword search with line-level locators.

    Deliberately lexical rather than semantic at this phase: semantic retrieval arrives with
    pgvector in Phase 12. What matters now is that every passage carries an exact locator,
    because an evidence reference that cannot be resolved to a location is worthless.
    """

    name = "document_search"
    description = "Find passages matching a query across the run's documents."
    capabilities: ClassVar[set[ToolCapability]] = {
        ToolCapability.DOCUMENT_SEARCH,
        ToolCapability.EVIDENCE_RETRIEVAL,
    }
    input_schema = SearchInput
    output_schema = SearchOutput
    cost_hint = CostHint.LOW

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        started = time.perf_counter()
        try:
            payload = SearchInput.model_validate(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return self.failure(call, FailureClass.SCHEMA_VIOLATION, str(exc))

        terms = [t for t in re.split(r"\W+", payload.query.lower()) if len(t) > 2]
        if not terms:
            return self.failure(call, FailureClass.MISSING_INPUT, "query has no searchable terms")

        scope = payload.scope or list(ctx.documents)
        passages: list[Passage] = []

        for doc_id in scope:
            text = ctx.documents.get(doc_id)
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                lowered = line.lower()
                hits = sum(1 for term in terms if term in lowered)
                if hits:
                    passages.append(
                        Passage(
                            document_id=doc_id,
                            line=number,
                            text=line.strip()[:300],
                            score=hits / len(terms),
                        )
                    )

        passages.sort(key=lambda p: p.score, reverse=True)
        top, result_cap = cap(passages, payload.k)
        return self.success(
            call,
            SearchOutput(passages=top, cap=result_cap, note=result_cap.note()).model_dump(),
            sources=[f"{p.document_id}:r{p.line}" for p in top],
            execution_time_ms=int((time.perf_counter() - started) * 1000),
        )


# --- document extract ----------------------------------------------------------


class ExtractInput(JarvisModel):
    document_ids: list[str] = Field(default_factory=list)
    pattern: str = Field(default="", description="What to extract: dates, amounts, or a regex")


class Extraction(JarvisModel):
    document_id: str
    line: int
    value: str
    kind: str


class ExtractOutput(JarvisModel):
    extractions: list[Extraction] = Field(default_factory=list)
    # How many were found versus returned. A capped result must never look complete.
    cap: ResultCap = Field(default_factory=ResultCap)
    note: str = ""


# Ceiling on extractions returned from one document set.
MAX_EXTRACTIONS = 60

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\s+\w+\s+\d{4}\b")
_AMOUNT = re.compile(r"[$£€]\s?[\d,]+(?:\.\d{2})?|\b\d[\d,]{2,}(?:\.\d{2})?\b")


class DocumentExtractTool(Tool):
    name = "document_extract"
    description = "Extract dates or monetary amounts from documents, with line locators."
    capabilities: ClassVar[set[ToolCapability]] = {ToolCapability.DOCUMENT_EXTRACT}
    input_schema = ExtractInput
    output_schema = ExtractOutput
    cost_hint = CostHint.MEDIUM
    timeout_s = 60.0

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        started = time.perf_counter()
        try:
            payload = ExtractInput.model_validate(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return self.failure(call, FailureClass.SCHEMA_VIOLATION, str(exc))

        doc_ids = payload.document_ids or list(ctx.documents)
        if not doc_ids:
            return self.failure(call, FailureClass.MISSING_INPUT, "no documents supplied")

        wants_dates = "date" in payload.pattern.lower() or "timeline" in payload.pattern.lower()
        wants_amounts = any(
            word in payload.pattern.lower() for word in ("amount", "budget", "cost", "financial")
        )
        if not wants_dates and not wants_amounts:
            wants_dates = wants_amounts = True

        found: list[Extraction] = []
        for doc_id in doc_ids:
            text = ctx.documents.get(doc_id)
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if wants_dates:
                    found += [
                        Extraction(document_id=doc_id, line=number, value=m, kind="date")
                        for m in _DATE.findall(line)
                    ]
                if wants_amounts:
                    found += [
                        Extraction(document_id=doc_id, line=number, value=m.strip(), kind="amount")
                        for m in _AMOUNT.findall(line)
                    ]

        # A hundred-page PDF yields thousands of matches. Returning them all would
        # overflow the reasoning prompt; returning some silently would let the agent
        # conclude "nothing found" from evidence it never saw. So: cap, and report it.
        returned, result_cap = cap(found, MAX_EXTRACTIONS)
        return self.success(
            call,
            ExtractOutput(
                extractions=returned, cap=result_cap, note=result_cap.note()
            ).model_dump(),
            sources=sorted({f"{e.document_id}:r{e.line}" for e in returned}),
            execution_time_ms=int((time.perf_counter() - started) * 1000),
        )


# --- csv analysis --------------------------------------------------------------


class CsvInput(JarvisModel):
    document_id: str
    column: str = ""


class CsvOutput(JarvisModel):
    rows: int
    columns: list[str] = Field(default_factory=list)
    total: float | None = None
    # A sample, not the column. A thousand-row CSV is analysed by aggregate; reciting it
    # into a prompt would crowd out everything else the agent learned.
    values: list[str] = Field(default_factory=list)
    cap: ResultCap = Field(default_factory=ResultCap)
    note: str = ""
    minimum: float | None = None
    maximum: float | None = None


class CsvAnalysisTool(Tool):
    name = "csv_analysis"
    description = "Read a CSV: row count, columns, and the sum of a numeric column."
    capabilities: ClassVar[set[ToolCapability]] = {
        ToolCapability.TABULAR_ANALYSIS,
        ToolCapability.COMPUTATION,
    }
    input_schema = CsvInput
    output_schema = CsvOutput
    cost_hint = CostHint.LOW

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        started = time.perf_counter()
        try:
            payload = CsvInput.model_validate(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return self.failure(call, FailureClass.SCHEMA_VIOLATION, str(exc))

        text = ctx.documents.get(payload.document_id)
        if text is None:
            return self.failure(
                call, FailureClass.NOT_FOUND, f"document '{payload.document_id}' not available"
            )

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        columns = list(reader.fieldnames or [])

        total: float | None = None
        minimum: float | None = None
        maximum: float | None = None
        values: list[str] = []
        if payload.column and payload.column in columns:
            values = [str(r.get(payload.column, "")) for r in rows]
            numbers: list[float] = []
            for raw in values:
                cleaned = re.sub(r"[^\d.\-]", "", raw)
                if cleaned:
                    try:
                        numbers.append(float(cleaned))
                    except ValueError:
                        continue
            total = sum(numbers) if numbers else None
            minimum = min(numbers) if numbers else None
            maximum = max(numbers) if numbers else None

        sample, result_cap = cap(values, MAX_CSV_ROWS)
        return self.success(
            call,
            CsvOutput(
                rows=len(rows),
                columns=columns,
                total=total,
                values=sample,
                cap=result_cap,
                note=result_cap.note(),
                minimum=minimum,
                maximum=maximum,
            ).model_dump(),
            sources=[f"{payload.document_id}:r0"],
            execution_time_ms=int((time.perf_counter() - started) * 1000),
        )


# --- context retrieval (local fallback for M2Context, Phase 12) ----------------


class ContextInput(JarvisModel):
    query: str
    k: int = Field(default=5, ge=1, le=50)


class ContextOutput(JarvisModel):
    passages: list[Passage] = Field(default_factory=list)
    provider: str = "local"


class ContextRetrievalTool(Tool):
    """Recall from the run's accumulated documents.

    The local fallback behind `ContextProvider`. Member 2's service swaps in at this seam in
    Phase 12; nothing outside `app/integrations/` will need to change.
    """

    name = "context_retrieval"
    description = "Recall relevant passages from the run's accumulated context."
    capabilities: ClassVar[set[ToolCapability]] = {
        ToolCapability.CONTEXT_RETRIEVAL,
        ToolCapability.KNOWLEDGE_SEARCH,
    }
    input_schema = ContextInput
    output_schema = ContextOutput
    cost_hint = CostHint.LOW

    def __init__(self) -> None:
        self._search = DocumentSearchTool()

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        try:
            payload = ContextInput.model_validate(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return self.failure(call, FailureClass.SCHEMA_VIOLATION, str(exc))

        inner = ToolCall(
            tool_name=self.name,
            arguments={"query": payload.query, "k": payload.k},
        )
        result = await self._search.execute(inner, ctx)
        if result.failed:
            return result

        output = ContextOutput.model_validate(
            {"passages": result.output.get("passages", []), "provider": "local"}
        )
        return self.success(call, output.model_dump(), sources=result.sources)


def _build() -> list[Tool]:
    return [
        CalculatorTool(),
        ContextRetrievalTool(),
        CsvAnalysisTool(),
        DocumentExtractTool(),
        DocumentSearchTool(),
    ]


DEFAULT_TOOLS: list[Tool] = _build()

__all__ = [
    "DEFAULT_TOOLS",
    "CalculatorTool",
    "ContextRetrievalTool",
    "CsvAnalysisTool",
    "DocumentExtractTool",
    "DocumentSearchTool",
    "UnsafeExpressionError",
    "safe_eval",
]
