"""Deterministic execution of trusted, in-process verification tasks."""
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Task:
    id: str
    action: Callable[[], object]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
    task_id: str
    status: Literal["succeeded", "failed", "blocked"]
    value: object = None
    error: str | None = None


def _ordered(tasks: Iterable[Task]) -> list[Task]:
    graph: dict[str, Task] = {}
    for task in tasks:
        if not isinstance(task.id, str) or not task.id.strip() or task.id in graph:
            raise ValueError("Task IDs must be nonempty and unique")
        if not callable(task.action):
            raise ValueError(f"Task {task.id} has no callable action")
        graph[task.id] = task
    for task in graph.values():
        for dependency in task.dependencies:
            if dependency not in graph:
                raise ValueError(f"Task {task.id}: missing dependency {dependency}")
    ordered: list[Task] = []
    done: set[str] = set()
    while len(done) < len(graph):
        ready = sorted(
            task_id for task_id, task in graph.items()
            if task_id not in done and all(dep in done for dep in task.dependencies)
        )
        if not ready:
            raise ValueError("Workflow contains a dependency cycle")
        for task_id in ready:
            ordered.append(graph[task_id])
            done.add(task_id)
    return ordered


def run(tasks: Iterable[Task]) -> dict[str, Result]:
    """Validate first, then run each task once; failures block descendants."""
    ordered = _ordered(tasks)
    results: dict[str, Result] = {}
    for task in ordered:
        blocked = [dep for dep in task.dependencies if results[dep].status != "succeeded"]
        if blocked:
            results[task.id] = Result(task.id, "blocked", error=f"Unsuccessful dependencies: {', '.join(blocked)}")
            continue
        try:
            value = task.action()
        except Exception as exc:
            results[task.id] = Result(task.id, "failed", error=f"{type(exc).__name__}: {exc}")
        else:
            results[task.id] = Result(task.id, "succeeded", value=value)
    return results
