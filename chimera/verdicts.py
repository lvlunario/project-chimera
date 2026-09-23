"""Conservative interpretation of explicitly bound boolean check results.

This does not evaluate measurements or authenticate evidence. Callers own the
requirement-to-task binding and must select trusted boolean check tasks.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .bindings import RequirementBindings
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
    bindings_sha256: str
    outcomes: tuple[RequirementOutcome, ...]

    @property
    def all_passed(self) -> bool:
        """An empty selection is not evidence that requirements passed."""
        return bool(self.outcomes) and all(item.verdict == "pass" for item in self.outcomes)


def assess_requirements(
    evidence: RunEvidence, bindings: Mapping[str, str] | RequirementBindings
) -> Assessment:
    """Interpret a completed snapshot without executing tasks or modifying it.

Bindings map unique requirement IDs to task IDs. Results are sorted by
requirement ID, independent of mapping insertion order. Only exact booleans
from succeeded tasks are verdicts; no truthiness conversion is permitted.
"""
    if not isinstance(evidence, RunEvidence):
        raise TypeError("evidence must be validated RunEvidence")
    if isinstance(bindings, RequirementBindings):
        binding_artifact = bindings
    else:
        binding_artifact = RequirementBindings.from_mapping(bindings)
    selected = binding_artifact.to_mapping()
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
    return Assessment(document["run_id"], binding_artifact.sha256, tuple(outcomes))
