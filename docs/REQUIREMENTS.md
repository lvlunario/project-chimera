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
