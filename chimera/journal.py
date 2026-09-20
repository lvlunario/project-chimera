"""Durable sequential task journal with conservative bounded recovery."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Callable, Literal
from uuid import UUID, uuid4

from .engine import Task, _ordered
from .ownership import DatabaseOwnership


class JournalError(RuntimeError):
    """The journal request or durable state is invalid."""


class JournalConflict(JournalError):
    """A run identity or lifecycle transition conflicts with durable state."""


@dataclass(frozen=True)
class JournalTask:
    """Trusted callback plus stable operator-supplied implementation identity."""

    id: str
    action: Callable[[], object]
    operation_id: str
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedTask:
    task_id: str
    operation_id: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class JournalPlan:
    """Canonical execution plan; callback code is deliberately not serialized."""

    _json: str

    @classmethod
    def from_tasks(cls, tasks: Iterable[JournalTask]) -> "JournalPlan":
        snapshots: list[JournalTask] = []
        for task in tasks:
            if not isinstance(task, JournalTask):
                raise TypeError("Expected JournalTask entries")
            if not isinstance(task.operation_id, str) or not task.operation_id.strip():
                raise JournalError("operation_id must be a nonempty string")
            snapshots.append(JournalTask(task.id, task.action, task.operation_id,
                                         tuple(task.dependencies)))
        ordered = _ordered(Task(task.id, task.action, task.dependencies) for task in snapshots)
        by_id = {task.id: task for task in snapshots}
        document = {
            "schema_version": 1,
            "tasks": [
                {"task_id": task.id,
                 "operation_id": by_id[task.id].operation_id,
                 "dependencies": list(task.dependencies)}
                for task in ordered
            ],
        }
        return cls(json.dumps(document, sort_keys=True, separators=(",", ":")))

    @classmethod
    def from_json(cls, text: str) -> "JournalPlan":
        try:
            document = json.loads(text, object_pairs_hook=_unique_object)
        except (ValueError, TypeError, RecursionError) as exc:
            raise JournalError(f"Invalid plan JSON: {exc}") from exc
        if type(document) is not dict or set(document) != {"schema_version", "tasks"}:
            raise JournalError("Invalid plan fields")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise JournalError("Unsupported plan schema_version")
        if type(document["tasks"]) is not list:
            raise JournalError("Plan tasks must be a list")
        tasks: list[JournalTask] = []
        for item in document["tasks"]:
            if type(item) is not dict or set(item) != {"task_id", "operation_id", "dependencies"}:
                raise JournalError("Invalid planned task fields")
            if (type(item["task_id"]) is not str or not item["task_id"].strip()
                    or type(item["operation_id"]) is not str or not item["operation_id"].strip()
                    or type(item["dependencies"]) is not list
                    or any(type(value) is not str for value in item["dependencies"])):
                raise JournalError("Invalid planned task value")
            tasks.append(JournalTask(item["task_id"], lambda: None,
                                     item["operation_id"], tuple(item["dependencies"])))
        canonical = cls.from_tasks(tasks)._json
        if canonical != text:
            raise JournalError("Plan JSON is not canonical")
        return cls(canonical)

    @property
    def sha256(self) -> str:
        return sha256(self._json.encode("utf-8")).hexdigest()

    @property
    def tasks(self) -> tuple[PlannedTask, ...]:
        return tuple(PlannedTask(item["task_id"], item["operation_id"],
                                 tuple(item["dependencies"]))
                     for item in json.loads(self._json)["tasks"])

    def to_json(self) -> str:
        return self._json


@dataclass(frozen=True)
class TaskInspection:
    task_id: str
    state: Literal["pending", "running", "succeeded", "failed", "blocked"]
    value: object
    error: str | None


@dataclass(frozen=True)
class RunInspection:
    run_id: str
    state: Literal["running", "needs_attention", "completed"]
    plan_sha256: str
    tasks: tuple[TaskInspection, ...]


_SCHEMA = {
    "journal_runs": "CREATE TABLE journal_runs (run_id TEXT PRIMARY KEY NOT NULL, plan_json TEXT NOT NULL, plan_digest TEXT NOT NULL, state TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT)",
    "journal_tasks": "CREATE TABLE journal_tasks (run_id TEXT NOT NULL REFERENCES journal_runs(run_id), position INTEGER NOT NULL, task_id TEXT NOT NULL, state TEXT NOT NULL, value_json TEXT, error TEXT, PRIMARY KEY(run_id, task_id), UNIQUE(run_id, position))",
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise JournalError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _json_value(value: object, ancestors: set[int] | None = None) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) not in (list, dict):
        raise JournalError("Results must use finite JSON primitives, lists and string-key objects")
    ancestors = set() if ancestors is None else ancestors
    if id(value) in ancestors:
        raise JournalError("Circular result value")
    ancestors.add(id(value))
    try:
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise JournalError("Result object keys must be strings")
            children = value.values()
        else:
            children = value
        for child in children:
            _json_value(child, ancestors)
    finally:
        ancestors.remove(id(value))


def _result_json(value: object) -> str:
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _OwnedJournal:
    """Internal single-owner journal connection."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.owner: DatabaseOwnership | None = None
        self.db: sqlite3.Connection | None = None

    def __enter__(self) -> "_OwnedJournal":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Create only the inode before locking it. Schema initialization and every
        # later SQLite write occur after lifetime ownership is established.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
        os.close(fd)
        self.owner = DatabaseOwnership(self.path).__enter__()
        try:
            self.db = sqlite3.connect(self.path, timeout=5)
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.execute("PRAGMA synchronous = FULL")
            self.db.execute("PRAGMA busy_timeout = 5000")
            _initialize_connected(self.db)
            self._validate()
            return self
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.owner is not None:
            self.owner.close()
            self.owner = None

    def __exit__(self, *_):
        self.close()

    def checkpoint(self) -> None:
        assert self.owner is not None
        self.owner.check()

    def _validate(self) -> None:
        assert self.db is not None
        if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise JournalError("Unsupported journal schema")
        definitions = dict(self.db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"))
        if definitions != _SCHEMA:
            raise JournalError("Unexpected journal table definitions")
        if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
            raise JournalError("Unexpected journal trigger/view")
        if self.db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise JournalError("Journal integrity check failed")
        if self.db.execute("PRAGMA foreign_key_check").fetchall():
            raise JournalError("Invalid journal relationship")
        for row in self.db.execute(
                "SELECT run_id,plan_json,plan_digest,state,started_at,finished_at FROM journal_runs"):
            run_id, plan_json, digest, state, started, finished = row
            try:
                UUID(run_id)
                started_at = datetime.fromisoformat(started)
                finished_at = datetime.fromisoformat(finished) if finished is not None else None
            except (ValueError, TypeError) as exc:
                raise JournalError("Invalid journal run identity/timestamp") from exc
            if (started_at.tzinfo is None or started_at.utcoffset() != timezone.utc.utcoffset(started_at)
                    or (finished_at is not None and
                        (finished_at.tzinfo is None
                         or finished_at.utcoffset() != timezone.utc.utcoffset(finished_at)
                         or finished_at < started_at))):
                raise JournalError("Journal timestamps must be ordered UTC values")
            plan = JournalPlan.from_json(plan_json)
            if plan.sha256 != digest or state not in ("running", "needs_attention", "completed"):
                raise JournalError("Invalid journal run content")
            if (state == "completed") != (finished_at is not None):
                raise JournalError("Journal completion timestamp/state mismatch")
            rows = self.db.execute(
                "SELECT position,task_id,state,value_json,error FROM journal_tasks "
                "WHERE run_id=? ORDER BY position", (run_id,)).fetchall()
            if len(rows) != len(plan.tasks):
                raise JournalError("Journal task plan/result mismatch")
            prior_states: dict[str, str] = {}
            frontier_seen = False
            for position, (stored, expected) in enumerate(zip(rows, plan.tasks, strict=True)):
                pos, task_id, task_state, value_json, error = stored
                if pos != position or task_id != expected.task_id:
                    raise JournalError("Journal task order mismatch")
                if task_state not in ("pending", "running", "succeeded", "failed", "blocked"):
                    raise JournalError("Invalid journal task state")
                if frontier_seen and task_state != "pending":
                    raise JournalError("Journal contains work beyond its execution frontier")
                if task_state in ("pending", "running"):
                    frontier_seen = True
                if task_state == "succeeded":
                    if value_json is None or error is not None:
                        raise JournalError("Invalid succeeded task content")
                    if _result_json(json.loads(value_json,
                                               object_pairs_hook=_unique_object)) != value_json:
                        raise JournalError("Task result JSON is not canonical")
                elif value_json is not None or ((task_state in ("failed", "blocked")) !=
                                                (type(error) is str and bool(error))):
                    raise JournalError("Invalid non-success task content")
                unsuccessful = any(prior_states[dep] != "succeeded"
                                   for dep in expected.dependencies)
                if task_state == "blocked" and not unsuccessful:
                    raise JournalError("Blocked task has no unsuccessful dependency")
                if task_state in ("running", "succeeded", "failed") and unsuccessful:
                    raise JournalError("Executed task has an unsuccessful dependency")
                prior_states[task_id] = task_state
            if state == "completed" and any(row[2] in ("pending", "running") for row in rows):
                raise JournalError("Completed run contains nonterminal tasks")

    def create(self, run_id: str, plan: JournalPlan) -> None:
        assert self.db is not None
        self.checkpoint()
        try:
            UUID(run_id)
        except (ValueError, TypeError) as exc:
            raise JournalError("run_id must be a UUID string") from exc
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._validate()
            if self.db.execute("SELECT 1 FROM journal_runs WHERE run_id=?", (run_id,)).fetchone():
                raise JournalConflict("run_id already exists")
            self.db.execute("INSERT INTO journal_runs VALUES (?,?,?,?,?,NULL)",
                            (run_id, plan.to_json(), plan.sha256, "running", _now()))
            self.db.executemany("INSERT INTO journal_tasks VALUES (?,?,?,?,NULL,NULL)",
                                ((run_id, index, task.task_id, "pending")
                                 for index, task in enumerate(plan.tasks)))

    def task_state(self, run_id: str, task_id: str) -> str:
        assert self.db is not None
        row = self.db.execute(
            "SELECT state FROM journal_tasks WHERE run_id=? AND task_id=?", (run_id, task_id)
        ).fetchone()
        if row is None:
            raise JournalConflict("Unknown task")
        return row[0]

    def transition(self, run_id: str, task_id: str, expected: str, state: str,
                   value_json: str | None = None, error: str | None = None) -> None:
        assert self.db is not None
        self.checkpoint()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            changed = self.db.execute(
                "UPDATE journal_tasks SET state=?,value_json=?,error=? "
                "WHERE run_id=? AND task_id=? AND state=?",
                (state, value_json, error, run_id, task_id, expected)).rowcount
            if changed != 1:
                raise JournalConflict(f"Task {task_id} is not {expected}")

    def finish(self, run_id: str) -> None:
        assert self.db is not None
        self.checkpoint()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute(
                    "SELECT 1 FROM journal_tasks WHERE run_id=? AND state IN ('pending','running')",
                    (run_id,)).fetchone():
                raise JournalConflict("Cannot complete a run with nonterminal tasks")
            changed = self.db.execute(
                "UPDATE journal_runs SET state='completed',finished_at=? "
                "WHERE run_id=? AND state='running'", (_now(), run_id)).rowcount
            if changed != 1:
                raise JournalConflict("Run is not running")

    def prepare_resume(self, run_id: str, plan: JournalPlan) -> bool:
        """Validate and claim resumable work; never change or retry a running task.

        Returns false for an already completed run. An interrupted run may still
        say ``running`` when its prior owner died between task commits; exclusive
        ownership plus the absence of a running task makes its pending suffix safe.
        """
        assert self.db is not None
        self.checkpoint()
        unknown_running = False
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._validate()
            row = self.db.execute(
                "SELECT plan_json,plan_digest,state FROM journal_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row[0] != plan.to_json() or row[1] != plan.sha256:
                raise JournalConflict("Recovery plan does not match durable plan")
            if row[2] == "completed":
                return False
            if self.db.execute(
                    "SELECT 1 FROM journal_tasks WHERE run_id=? AND state='running'",
                    (run_id,)).fetchone():
                if row[2] == "running":
                    self.db.execute(
                        "UPDATE journal_runs SET state='needs_attention' WHERE run_id=?",
                        (run_id,),
                    )
                unknown_running = True
            elif row[2] == "needs_attention":
                self.db.execute(
                    "UPDATE journal_runs SET state='running' WHERE run_id=?",
                    (run_id,),
                )
        if unknown_running:
            raise JournalConflict("Unknown running task prevents resume")
        return True

    def inspect(self, run_id: str, plan: JournalPlan, recover: bool) -> RunInspection:
        assert self.db is not None
        self.checkpoint()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE" if recover else "BEGIN")
            self._validate()
            row = self.db.execute(
                "SELECT plan_json,plan_digest,state FROM journal_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row[0] != plan.to_json() or row[1] != plan.sha256:
                raise JournalConflict("Recovery plan does not match durable plan")
            state = row[2]
            if recover and state == "running":
                self.db.execute("UPDATE journal_runs SET state='needs_attention' WHERE run_id=?",
                                (run_id,))
                state = "needs_attention"
            rows = self.db.execute(
                "SELECT task_id,state,value_json,error FROM journal_tasks "
                "WHERE run_id=? ORDER BY position", (run_id,)).fetchall()
            tasks = tuple(TaskInspection(task_id, task_state,
                                         json.loads(value_json) if value_json is not None else None,
                                         error)
                          for task_id, task_state, value_json, error in rows)
            return RunInspection(run_id, state, row[1], tasks)


def _initialize_connected(db: sqlite3.Connection) -> None:
    try:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if version == 0 and not tables:
            for statement in _SCHEMA.values():
                db.execute(statement)
            db.execute("PRAGMA user_version = 1")
        elif version != 1 or tables != set(_SCHEMA):
            raise JournalError("Unsupported journal schema; expected version 1")
        db.commit()
    except BaseException:
        db.rollback()
        raise


def run_journaled(path: str | Path, tasks: Iterable[JournalTask], *,
                  run_id: str | None = None) -> RunInspection:
    """Execute once under ownership, committing every transition before continuing.

    Interrupts, serialization errors and storage errors stop scheduling. A task left
    in ``running`` has an unknown outcome and is never retried by this API.
    """
    task_tuple = tuple(tasks)
    plan = JournalPlan.from_tasks(task_tuple)
    actions = {task.id: task.action for task in task_tuple}
    run_id = str(uuid4()) if run_id is None else run_id
    with _OwnedJournal(path) as journal:
        journal.create(run_id, plan)
        states: dict[str, str] = {}
        for task in plan.tasks:
            unsuccessful = [dep for dep in task.dependencies if states[dep] != "succeeded"]
            if unsuccessful:
                journal.transition(run_id, task.task_id, "pending", "blocked", error=
                                   f"Unsuccessful dependencies: {', '.join(unsuccessful)}")
                states[task.task_id] = "blocked"
                continue
            journal.transition(run_id, task.task_id, "pending", "running")
            journal.checkpoint()
            try:
                value = actions[task.task_id]()
            except Exception as exc:
                journal.transition(run_id, task.task_id, "running", "failed",
                                   error=f"{type(exc).__name__}: {exc}")
                states[task.task_id] = "failed"
            else:
                # Detach before committing and before any later callback can mutate it.
                value_json = _result_json(value)
                journal.transition(run_id, task.task_id, "running", "succeeded",
                                   value_json=value_json)
                states[task.task_id] = "succeeded"
        journal.finish(run_id)
        return journal.inspect(run_id, plan, recover=False)


def resume_journaled(path: str | Path, run_id: str,
                     tasks: Iterable[JournalTask]) -> RunInspection:
    """Continue only a validated pending suffix under exclusive ownership.

    Terminal tasks are never invoked again. If any task is durably ``running``, its
    outcome is unknown and the entire resume is refused without invoking callbacks.
    The operation identity is trusted caller-supplied provenance, not authentication.
    """
    task_tuple = tuple(tasks)
    plan = JournalPlan.from_tasks(task_tuple)
    actions = {task.id: task.action for task in task_tuple}
    with _OwnedJournal(path) as journal:
        if not journal.prepare_resume(run_id, plan):
            return journal.inspect(run_id, plan, recover=False)
        current = journal.inspect(run_id, plan, recover=False)
        states = {task.task_id: task.state for task in current.tasks}
        for task in plan.tasks:
            if states[task.task_id] != "pending":
                continue
            unsuccessful = [dep for dep in task.dependencies
                            if states[dep] != "succeeded"]
            if unsuccessful:
                journal.transition(
                    run_id, task.task_id, "pending", "blocked",
                    error=f"Unsuccessful dependencies: {', '.join(unsuccessful)}",
                )
                states[task.task_id] = "blocked"
                continue
            journal.transition(run_id, task.task_id, "pending", "running")
            journal.checkpoint()
            try:
                value = actions[task.task_id]()
            except Exception as exc:
                journal.transition(
                    run_id, task.task_id, "running", "failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
                states[task.task_id] = "failed"
            else:
                value_json = _result_json(value)
                journal.transition(
                    run_id, task.task_id, "running", "succeeded",
                    value_json=value_json,
                )
                states[task.task_id] = "succeeded"
        journal.finish(run_id)
        return journal.inspect(run_id, plan, recover=False)


def inspect_interrupted(path: str | Path, run_id: str, plan: JournalPlan) -> RunInspection:
    """Inspect a run under exclusive ownership and mark an interruption for attention.

    This function never accepts or executes callbacks and never resumes work.
    Repeated inspection is idempotent.
    """
    if not isinstance(plan, JournalPlan):
        raise TypeError("Expected JournalPlan")
    with _OwnedJournal(path) as journal:
        return journal.inspect(run_id, plan, recover=True)
