# Foundation requirement traceability

| ID | Requirement | Acceptance test |
|---|---|---|
| CORE-001 | Reject duplicate or empty task IDs before execution | test_invalid_ids |
| CORE-002 | Reject missing dependencies before execution | test_missing_dependency |
| CORE-003 | Reject cycles before any side effects | test_cycle_preflight |
| CORE-004 | Execute a dependency before its consumer in deterministic order | test_order |
| CORE-005 | Block all descendants of a failed task | test_failure_propagates |
| CORE-006 | Continue independent tasks after failure | test_failure_propagates |
| CORE-007 | Propagate user interrupts | test_interrupt |
| CORE-008 | Allow an empty workflow | test_empty |
| CORE-009 | Preserve validated dependencies when caller-owned sequences change | test_dependency_mutation_preserves_validated_plan |

Tests live in tests/test_engine.py. These cover the prototype kernel only.
Phase P1 also requires evidence serialization, package installation, CLI input and CI.

## Completed-run evidence v1

Tracked in [issue #3](https://github.com/lvlunario/project-chimera/issues/3).
The mutable-dependency regression is [defect #4](https://github.com/lvlunario/project-chimera/issues/4).

| ID | Requirement | Acceptance test (tests/test_evidence.py unless noted) |
|---|---|---|
| EVID-001 | Record schema version 1, unique run UUID, UTC start/finish and ordered outcomes; reload without running tasks | test_round_trip, test_empty_and_generator |
| EVID-002 | Preserve failure errors, dependency IDs, blocked outcomes and independent results | test_failed_blocked_and_independent |
| EVID-003 | Reject malformed/unknown schema, inconsistent outcomes and non-JSON/lossy values | test_reject_invalid_document, test_reject_lossy_values; negative tests in test_evidence_qa.py |
| EVID-004 | Snapshot remains unchanged after caller mutations; preserve validated dependency plan | test_snapshot_is_detached; test_caller_dependency_mutation_cannot_change_validated_plan in test_evidence_qa.py |
| EVID-005 | Invalid graphs execute no actions; interrupts never become completed evidence | test_preflight_and_interrupt |

Local verification and independent QA recorded in the daily log. These are task
execution outcomes, not requirement pass/fail verdicts. Input identity/hashes,
requirement mapping, code/config provenance and crash-safe storage remain planned.

## Packaging

Tracked in [issue #5](https://github.com/lvlunario/project-chimera/issues/5).

| ID | Requirement | Acceptance evidence |
|---|---|---|
| PACK-001 | Install as `project-chimera` on supported Python 3.11+ with no runtime dependencies | `scripts/verify_clean_install.sh`: distribution metadata and dependency check |
| PACK-002 | Import the public API from an isolated environment outside the checkout | clean-install source-path guard and evidence round trip |
| PACK-003 | Provide an installed `chimera-demo` entry point with expected synthetic failure/blocking behavior | clean-install demo output assertions |
| PACK-004 | Leave the repository and host environment unchanged by clean-install verification | temporary source/build/venv with exit cleanup; worktree inspection |

Python 3.12.14 is locally verified. Declaring 3.11 support is not equivalent to
having run the suite on 3.11; the planned CI matrix must supply that evidence.

## Continuous integration

Tracked in [issue #6](https://github.com/lvlunario/project-chimera/issues/6).

| ID | Requirement | Acceptance evidence |
|---|---|---|
| CI-001 | Run every pull request and development/main push on Python 3.11 and 3.12 | GitHub Actions `test` workflow matrix |
| CI-002 | Execute the full regression suite and isolated wheel-install check in each job | workflow steps and successful job logs |
| CI-003 | Use read-only repository permissions, no persisted checkout credential and bounded execution | workflow `permissions`, checkout setting, timeout and concurrency |
| CI-004 | Pin official third-party Actions to reviewed commit SHAs | checkout/setup-python `uses` references |

CI-001–004 are verified on development commit `35f3558d` by
[test run 34744334003](https://github.com/lvlunario/project-chimera/actions/runs/34744334003):
both Python jobs and every named step completed successfully. Inspected logs recorded
31 tests in each job (3.11: 0.006 seconds; 3.12: 0.007 seconds), installed version
`0.1.0.dev0` from the respective temporary venv `site-packages`, and
`clean-install: passed`. This evidence does not close P1 or imply PM acceptance.

## Declarative workflow CLI

Tracked in [issue #7](https://github.com/lvlunario/project-chimera/issues/7).

| ID | Requirement | Acceptance test |
|---|---|---|
| CLI-001 | Load only strict, versioned UTF-8 JSON with bounded bytes, tasks, dependencies, IDs and values | `test_workflow.py` invalid-document/task/size tests |
| CLI-002 | Execute only allowlisted synthetic `emit` and `fail` operations; never import or evaluate workflow-supplied code | parser operation/field tests and independent QA negative tests |
| CLI-003 | Validate graph errors before execution and avoid producing completed evidence for invalid input | `test_invalid_graph_returns_two_without_evidence` |
| CLI-004 | Write reloadable completed-run evidence without overwriting an existing path | CLI success/failure/overwrite tests and clean-install check |
| CLI-005 | Return 0 for all-success, 1 for completed unsuccessful runs, 2 for input/graph/usage errors, and 3 for output errors | `test_cli.py` and independent QA exit-code tests |

The CLI converts a declaration into the existing trusted in-process kernel. Current
operations are intentionally side-effect-free; this is not a sandbox for arbitrary
Python and does not yet ingest engineering telemetry.

CLI-001–005 are verified on development head `1ea07c7e` by 49 local tests,
independent negative-path QA, isolated installed-wheel execution and
[hosted run 34753672209](https://github.com/lvlunario/project-chimera/actions/runs/34753672209)
on Python 3.11/3.12. The preceding run's publication-mode failure and corrective
evidence are preserved in the daily log. This does not close P1 or imply PM acceptance.
