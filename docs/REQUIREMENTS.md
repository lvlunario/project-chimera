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

Tests live in tests/test_engine.py. These cover the prototype kernel only.
Phase P1 also requires evidence serialization, package installation, CLI input and CI.
