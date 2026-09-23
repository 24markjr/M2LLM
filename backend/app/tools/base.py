"""Tool contract and registry.

Tools are the only way the agent reads or affects anything. The contract is designed so that
**routing can be decided deterministically wherever possible**: capability class and schema
compatibility are structural facts, not judgement calls, so most selections never reach a
model at all (Phase 10).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.schemas.common import CostHint, FailureClass, JarvisModel
from app.schemas.tool import ToolCall, ToolCapability, ToolDefinition, ToolError, ToolResult

log = get_logger(__name__)


class ToolContext(JarvisModel):
    """What a tool is allowed to know about the run it serves.

    Deliberately narrow. A tool that could see the findings so far might tailor its output to
    them, which would quietly destroy the independence that makes evidence worth anything.
    """

    run_id: str = ""
    task_id: str = ""
    document_ids: list[str] = Field(default_factory=list)
    # Text content keyed by document id, supplied by the execution engine.
    documents: dict[str, str] = Field(default_factory=dict)
    # Where each page begins, per paginated document. Lets tools cite a page rather than
    # a line, which is the difference between a citation a reader can check and one they
    # cannot.
    page_starts: dict[str, list[int]] = Field(default_factory=dict)


class Tool(ABC):
    """One registered capability."""

    name: ClassVar[str]
    description: ClassVar[str]
    capabilities: ClassVar[set[ToolCapability]]
    input_schema: ClassVar[type[BaseModel]]
    output_schema: ClassVar[type[BaseModel]]
    cost_hint: ClassVar[CostHint] = CostHint.LOW
    timeout_s: ClassVar[float] = 30.0

    @abstractmethod
    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Run the tool. Must not raise: failures come back as a classified `ToolResult`."""

    @classmethod
    def definition(cls) -> ToolDefinition:
        """The public description, exported into the planner and router prompts."""
        return ToolDefinition(
            name=cls.name,
            description=cls.description,
            capabilities=set(cls.capabilities),
            input_schema=cls.input_schema.model_json_schema(),
            output_schema=cls.output_schema.model_json_schema(),
            cost_hint=cls.cost_hint,
            timeout_s=cls.timeout_s,
        )

    @staticmethod
    def failure(call: ToolCall, failure_class: FailureClass, message: str) -> ToolResult:
        """Build a classified failure.

        Classification at the point of failure is what lets the execution engine decide
        retry vs. fallback without inspecting exception text.
        """
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            ok=False,
            error=ToolError(failure_class=failure_class, message=message),
        )

    @staticmethod
    def success(
        call: ToolCall,
        output: dict[str, Any],
        *,
        sources: list[str] | None = None,
        execution_time_ms: int = 0,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            ok=True,
            output=output,
            sources=sources or [],
            execution_time_ms=execution_time_ms,
        )


class ToolRegistry:
    """The set of tools available to a run.

    Registration is explicit rather than by import-time scanning: a tool that exists but was
    never registered is a visible omission, not a mystery.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def serving(self, capability: ToolCapability) -> list[Tool]:
        """Every tool that can satisfy a capability. The router's first, deterministic stage."""
        return [t for t in self.all() if capability in t.capabilities]

    def catalogue(self) -> list[ToolDefinition]:
        """What goes into the prompts, so the model plans against tools that exist."""
        return [t.definition() for t in self.all()]

    def describe(self) -> str:
        """Compact catalogue text for prompt injection."""
        lines = []
        for tool in self.all():
            caps = ", ".join(sorted(c.value for c in tool.capabilities))
            lines.append(f"- {tool.name} [{caps}] cost={tool.cost_hint.value}: {tool.description}")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return len(self._tools)


def build_default_registry() -> ToolRegistry:
    """The standard tool set. Imported lazily to keep this module dependency-free."""
    from app.tools.builtin import DEFAULT_TOOLS

    registry = ToolRegistry()
    for tool in DEFAULT_TOOLS:
        registry.register(tool)
    return registry
