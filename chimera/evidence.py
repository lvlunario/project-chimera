"""Versioned snapshots of completed runs, not a durable execution journal."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from uuid import UUID, uuid4

from .engine import Task, run


class EvidenceError(ValueError):
    """Evidence cannot be represented or does not satisfy schema version 1."""


def _json_value(value: object, ancestors: set[int] | None = None) -> None:
    """Reject lossy conversions, non-finite numbers, and recursive containers."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) not in (list, dict):
        raise EvidenceError("Values must use finite JSON primitives, lists and string-key objects")
    ancestors = set() if ancestors is None else ancestors
    if id(value) in ancestors:
        raise EvidenceError("Circular evidence value")
    ancestors.add(id(value))
    try:
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise EvidenceError("Evidence object keys must be strings")
            children = value.values()
        else:
            children = value
        for child in children:
            _json_value(child, ancestors)
    finally:
        ancestors.remove(id(value))


def _fields(value: object, fields: set[str]) -> None:
    if type(value) is not dict or set(value) != fields:
        raise EvidenceError(f"Expected exactly these fields: {', '.join(sorted(fields))}")


def _timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise EvidenceError("Timestamps must be UTC ISO-8601 strings")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError("Invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvidenceError("Timestamps must include a UTC offset")
    return parsed


def _validate(document: object) -> None:
    _json_value(document)
    _fields(document, {"schema_version", "run_id", "started_at", "finished_at", "tasks"})
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise EvidenceError("Unsupported evidence schema_version; expected integer 1")
    try:
        if type(document["run_id"]) is not str:
            raise ValueError
        UUID(document["run_id"])
    except ValueError as exc:
        raise EvidenceError("run_id must be a UUID string") from exc
    if _timestamp(document["finished_at"]) < _timestamp(document["started_at"]):
        raise EvidenceError("finished_at precedes started_at")
    if type(document["tasks"]) is not list:
        raise EvidenceError("tasks must be a list in execution order")
    seen: dict[str, str] = {}
    for task in document["tasks"]:
        _fields(task, {"task_id", "status", "value", "error", "dependencies"})
        task_id = task["task_id"]
        if type(task_id) is not str or not task_id.strip() or task_id in seen:
            raise EvidenceError("Task IDs must be nonempty and unique")
        status = task["status"]
        if type(status) is not str or status not in ("succeeded", "failed", "blocked"):
            raise EvidenceError("Invalid task status")
        dependencies = task["dependencies"]
        if type(dependencies) is not list or any(
            type(dep) is not str or dep not in seen for dep in dependencies
        ):
            raise EvidenceError("Dependencies must refer to earlier tasks")
        unsuccessful = any(seen[dep] != "succeeded" for dep in dependencies)
        if (status == "blocked") != unsuccessful:
            raise EvidenceError("Blocked status must agree with dependency outcomes")
        if status == "succeeded":
            if task["error"] is not None:
                raise EvidenceError("Successful tasks cannot contain an error")
        elif task["value"] is not None or type(task["error"]) is not str or not task["error"]:
            raise EvidenceError("Failed/blocked tasks require an error and a null value")
        seen[task_id] = status


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class RunEvidence:
    """Immutable validated JSON snapshot; dictionary access returns a fresh copy."""

    _json: str

    def __post_init__(self) -> None:
        if type(self._json) is not str:
            raise EvidenceError("Evidence input must be JSON text")
        try:
            document = json.loads(self._json, object_pairs_hook=_unique_object)
            _validate(document)
        except (ValueError, TypeError, RecursionError) as exc:
            raise EvidenceError(str(exc)) from exc
        object.__setattr__(self, "_json", json.dumps(document, sort_keys=True, allow_nan=False))

    @classmethod
    def from_json(cls, text: str) -> "RunEvidence":
        """Load supported evidence without executing task code."""
        return cls(text)

    def to_json(self) -> str:
        return self._json

    def to_dict(self) -> dict:
        return json.loads(self._json)


def run_with_evidence(tasks: Iterable[Task]) -> RunEvidence:
    """Run trusted tasks and snapshot their final results.

    Graph errors and interrupts propagate. Unrepresentable output raises
    EvidenceError *after* execution; callers must not automatically retry tasks.
    This API neither writes a file nor records an interrupted/partially completed run.
    """
    # Snapshot graph metadata before trusted actions can mutate caller-owned lists.
    tasks = tuple(Task(task.id, task.action, tuple(task.dependencies)) for task in tasks)
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid4())
    results = run(tasks)
    dependencies = {task.id: list(task.dependencies) for task in tasks}
    document = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [
            {"task_id": result.task_id, "status": result.status,
             "value": result.value, "error": result.error,
             "dependencies": dependencies[result.task_id]}
            for result in results.values()
        ],
    }
    try:
        _validate(document)
        return RunEvidence(json.dumps(document, allow_nan=False))
    except (ValueError, TypeError, RecursionError) as exc:
        raise EvidenceError(str(exc)) from exc
