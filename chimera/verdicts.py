"""Conservative interpretation of explicitly bound boolean check results.

This does not evaluate measurements or authenticate evidence. Callers own the
requirement-to-task binding and must select trusted boolean check tasks.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .evidence import RunEvidence


@dataclass(frozen=True)
class RequirementOutcome:
    requirement_id: str
    task_id: str
    verdict: Literal["pass", "fail", "error", "not_evaluated"]
    reason: str


@dataclass(frozen=True)
class Assessment:
    run_id: str
    outcomes: tuple[RequirementOutcome, ...]

    @property
    def all_passed(self) -> bool:
        """An empty selection is not evidence that requirements passed."""
        return bool(self.outcomes) and all(item.verdict == "pass" for item in self.outcomes)


def assess_requirements(
    evidence: RunEvidence, bindings: Mapping[str, str]
) -> Assessment:
    """Interpret a completed snapshot without executing tasks or modifying it.

Bindings map unique requirement IDs to task IDs. Results are sorted by
requirement ID, independent of mapping insertion order. Only exact booleans
from succeeded tasks are verdicts; no truthiness conversion is permitted.
"""
    if not isinstance(evidence, RunEvidence):
        raise TypeError("evidence must be validated RunEvidence")
    if not isinstance(bindings, Mapping):
        raise TypeError("bindings must map requirement IDs to task IDs")
    selected = dict(bindings)
    if any(type(value) is not str or not value.strip()
           for pair in selected.items() for value in pair):
        raise ValueError("Requirement and task IDs must be nonempty strings")
    document = evidence.to_dict()
    tasks = {task["task_id"]: task for task in document["tasks"]}
    outcomes = []
    for requirement_id, task_id in sorted(selected.items()):
        task = tasks.get(task_id)
        if task is None:
            verdict, reason = "not_evaluated", "Task is absent from run evidence"
        elif task["status"] == "blocked":
            verdict, reason = "not_evaluated", task["error"]
        elif task["status"] == "failed":
            verdict, reason = "error", task["error"]
        elif type(task["value"]) is not bool:
            verdict, reason = "error", "Check must return an exact boolean verdict"
        elif task["value"]:
            verdict, reason = "pass", "Check returned True"
        else:
            verdict, reason = "fail", "Check returned False"
        outcomes.append(RequirementOutcome(requirement_id, task_id, verdict, reason))
    return Assessment(document["run_id"], tuple(outcomes))
