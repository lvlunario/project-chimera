"""Strict declarative workflow input for the bounded local operator CLI."""
import json
import math
from pathlib import Path
import re

from .engine import Task


SCHEMA_VERSION = 1
MAX_WORKFLOW_BYTES = 1_048_576
MAX_TASKS = 1_000
MAX_DEPENDENCIES = 1_000
MAX_FAILURE_MESSAGE = 1_000
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class WorkflowError(ValueError):
    """A workflow file cannot be safely represented by schema version 1."""


class WorkflowTaskFailure(RuntimeError):
    """Expected failure requested by a declarative synthetic task."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkflowError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise WorkflowError(f"Non-finite JSON number is not allowed: {value}")


def _fields(value: object, expected: set[str], context: str) -> None:
    if type(value) is not dict or set(value) != expected:
        raise WorkflowError(
            f"{context} must contain exactly: {', '.join(sorted(expected))}"
        )


def _json_value(value: object, depth: int = 0) -> None:
    if depth > 100:
        raise WorkflowError("Workflow values may not exceed 100 nesting levels")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for child in value:
            _json_value(child, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for child in value.values():
            _json_value(child, depth + 1)
        return
    raise WorkflowError("Task values must use finite JSON primitives, lists and objects")


def _dependencies(value: object, task_id: str) -> tuple[str, ...]:
    if type(value) is not list or len(value) > MAX_DEPENDENCIES:
        raise WorkflowError(
            f"Task {task_id}: dependencies must be a list of at most {MAX_DEPENDENCIES} IDs"
        )
    dependencies: list[str] = []
    for dependency in value:
        if type(dependency) is not str or _TASK_ID.fullmatch(dependency) is None:
            raise WorkflowError(f"Task {task_id}: invalid dependency ID")
        if dependency in dependencies:
            raise WorkflowError(f"Task {task_id}: duplicate dependency {dependency}")
        dependencies.append(dependency)
    return tuple(dependencies)


def _emit(value: object):
    return lambda: value


def _fail(message: str):
    def action() -> None:
        raise WorkflowTaskFailure(message)

    return action


def parse_workflow(text: str) -> tuple[Task, ...]:
    """Parse JSON schema version 1 into allowlisted, side-effect-free tasks."""
    if type(text) is not str:
        raise WorkflowError("Workflow input must be JSON text")
    try:
        document = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except WorkflowError:
        raise
    except (ValueError, RecursionError) as exc:
        raise WorkflowError(f"Invalid workflow JSON: {exc}") from exc

    _fields(document, {"schema_version", "tasks"}, "Workflow")
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise WorkflowError("Unsupported workflow schema_version; expected integer 1")
    task_documents = document["tasks"]
    if type(task_documents) is not list or len(task_documents) > MAX_TASKS:
        raise WorkflowError(f"tasks must be a list of at most {MAX_TASKS} entries")

    tasks: list[Task] = []
    seen: set[str] = set()
    for index, task_document in enumerate(task_documents):
        if type(task_document) is not dict:
            raise WorkflowError(f"Task at index {index} must be an object")
        task_id = task_document.get("id")
        if type(task_id) is not str or _TASK_ID.fullmatch(task_id) is None:
            raise WorkflowError(f"Task at index {index}: invalid id")
        if task_id in seen:
            raise WorkflowError(f"Duplicate task id: {task_id}")
        seen.add(task_id)
        operation = task_document.get("operation")
        dependencies = _dependencies(task_document.get("dependencies", []), task_id)
        if operation == "emit":
            _fields(task_document, {"id", "operation", "value"} | ({"dependencies"} if "dependencies" in task_document else set()), f"Task {task_id}")
            _json_value(task_document["value"])
            action = _emit(task_document["value"])
        elif operation == "fail":
            _fields(task_document, {"id", "operation", "message"} | ({"dependencies"} if "dependencies" in task_document else set()), f"Task {task_id}")
            message = task_document["message"]
            if type(message) is not str or not message.strip() or len(message) > MAX_FAILURE_MESSAGE:
                raise WorkflowError(
                    f"Task {task_id}: message must be 1-{MAX_FAILURE_MESSAGE} characters"
                )
            action = _fail(message)
        else:
            raise WorkflowError(f"Task {task_id}: unsupported operation {operation!r}")
        tasks.append(Task(task_id, action, dependencies))
    return tuple(tasks)


def load_workflow(path: str | Path) -> tuple[Task, ...]:
    """Read a size-bounded UTF-8 workflow file and parse it strictly."""
    path = Path(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_WORKFLOW_BYTES + 1)
    except OSError as exc:
        raise WorkflowError(f"Cannot read workflow: {exc}") from exc
    if len(data) > MAX_WORKFLOW_BYTES:
        raise WorkflowError(f"Workflow exceeds {MAX_WORKFLOW_BYTES} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkflowError("Workflow must be UTF-8 JSON") from exc
    return parse_workflow(text)
