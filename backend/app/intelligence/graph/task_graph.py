"""The live task graph.

A `Plan` is a proposal. A `TaskGraph` is the running thing: it tracks state, decides what is
ready to run, blocks descendants of terminal failures, and — from Phase 16 — lets the agent
insert new tasks mid-run.

`ready_tasks()` is the single place ordering is decided. That makes "no task ran before its
dependencies completed" an assertable property rather than an emergent one.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.plan import Plan
from app.schemas.task import TERMINAL_STATUSES, Task, TaskStatus

log = get_logger(__name__)


class TaskGraph:
    """Mutable DAG of tasks, with an explicit state machine."""

    def __init__(self, tasks: list[Task]) -> None:
        self._tasks: dict[str, Task] = {t.task_id: t for t in tasks}
        self.revision = 0
        self.mutations: list[str] = []

    @classmethod
    def from_plan(cls, plan: Plan) -> TaskGraph:
        return cls([t.model_copy(deep=True) for t in plan.tasks])

    # --- reads -----------------------------------------------------------------

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def with_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self._tasks.values() if t.status is status]

    def ready_tasks(self) -> list[Task]:
        """Tasks whose dependencies are all COMPLETED.

        The only source of truth for what may run next.
        """
        ready: list[Task] = []
        for task in self._tasks.values():
            if task.status not in {TaskStatus.PENDING, TaskStatus.READY}:
                continue
            if all(self._is_complete(dep) for dep in task.depends_on):
                ready.append(task)
        return sorted(ready, key=lambda t: t.task_id)

    def _is_complete(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return task is not None and task.status is TaskStatus.COMPLETED

    def has_runnable_work(self) -> bool:
        """Whether anything could still run.

        False when every task is terminal, or when the only remaining tasks are blocked
        behind a failure - which is how the scheduler knows to stop rather than spin.
        """
        return bool(self.ready_tasks()) or bool(self.with_status(TaskStatus.RUNNING))

    @property
    def is_finished(self) -> bool:
        return all(
            t.status in TERMINAL_STATUSES or t.status is TaskStatus.BLOCKED
            for t in self._tasks.values()
        )

    def progress(self) -> tuple[int, int]:
        done = sum(1 for t in self._tasks.values() if t.status in TERMINAL_STATUSES)
        return done, len(self._tasks)

    # --- state transitions -----------------------------------------------------

    def mark(self, task_id: str, status: TaskStatus) -> Task:
        """Move a task to a new state, raising on an illegal transition."""
        task = self._tasks[task_id]
        task.transition_to(status)
        if status is TaskStatus.FAILED and task.retries_remaining == 0:
            self.block_descendants(task_id)
        return task

    def block_descendants(self, task_id: str) -> list[str]:
        """Block everything transitively downstream of a terminal failure.

        Only descendants. A task on an independent branch is unaffected, so one dead path
        does not abandon an investigation that could still produce something.
        """
        blocked: list[str] = []
        frontier = [task_id]
        while frontier:
            current = frontier.pop()
            for task in self._tasks.values():
                if current in task.depends_on and task.status not in TERMINAL_STATUSES:
                    if task.status is TaskStatus.BLOCKED:
                        continue
                    if task.status in {TaskStatus.PENDING, TaskStatus.READY}:
                        task.transition_to(TaskStatus.BLOCKED)
                        blocked.append(task.task_id)
                        frontier.append(task.task_id)
        if blocked:
            log.info("tasks_blocked", cause=task_id, blocked=blocked)
        return blocked

    # --- mutation (the API replanning uses in Phase 16) ------------------------

    def insert_task(self, task: Task, *, after: list[str] | None = None) -> Task:
        """Add a task mid-run. Re-validates acyclicity afterwards.

        This is the mechanism behind the headline feature: when gap detection names missing
        evidence, closing it means putting a new node into a graph that is already running.
        """
        if task.task_id in self._tasks:
            raise ValueError(f"{task.task_id} is already in the graph")

        task.depends_on = [d for d in (after or []) if d in self._tasks]
        self._tasks[task.task_id] = task

        cycle = self.find_cycle()
        if cycle:
            del self._tasks[task.task_id]
            raise ValueError(f"inserting {task.task_id} would create a cycle: {cycle}")

        self.revision += 1
        self.mutations.append(f"inserted {task.task_id} after {task.depends_on or '-'}")
        return task

    def find_cycle(self) -> list[str]:
        """Re-validate acyclicity. Run after every mutation."""
        colour: dict[str, int] = dict.fromkeys(self._tasks, 0)
        stack: list[str] = []

        def visit(node: str) -> list[str]:
            colour[node] = 1
            stack.append(node)
            for parent in self._tasks[node].depends_on:
                if parent not in colour:
                    continue
                if colour[parent] == 1:
                    return [*stack[stack.index(parent) :], parent]
                if colour[parent] == 0:
                    found = visit(parent)
                    if found:
                        return found
            colour[node] = 2
            stack.pop()
            return []

        for node in self._tasks:
            if colour[node] == 0:
                cycle = visit(node)
                if cycle:
                    return cycle
        return []

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "tasks": [t.model_dump(mode="json") for t in self._tasks.values()],
            "mutations": self.mutations,
        }
