# Foundation requirement traceability

Current acceptance: P0 approved by delegation; P1/P2 conditionally accepted for progression
September 22 under [the decision record](reviews/2026-09-22-delegated-decisions.md).
Historical pending statements below describe their original slices, not today's decisions.
Personal walkthroughs and final acceptance remain unperformed/open.

## Reopened-evidence verification report v1

Tracked in [issue #15](https://github.com/lvlunario/project-chimera/issues/15), target M3
November 7. Bounded P4 implementation; not P4 gate closure or dashboard delivery.

| ID | Requirement | Evidence |
|---|---|---|
| REPORT-001 | Build a canonical versioned communications report only from validated `RunEvidence` and `RequirementBindings`; accept no callbacks | `tests/test_reports.py`, durable `examples.report_demo` |
| REPORT-002 | Identify the exact evidence, binding and canonical report bytes with SHA-256 content identities | fixed digest/round-trip tests and HTML evidence section |
| REPORT-003 | Require exact agreement among COM-LINK-001 Boolean assessment, validated link detail and derived-input identity | pass/fail/conflict/provenance tests |
| REPORT-004 | Represent blocked/missing detail as unavailable and `not_evaluated`/error; never infer pass | missing-evidence durable/report tests |
| REPORT-005 | Emit deterministic self-contained script-free HTML with escaped evidence strings and the canonical report JSON | deterministic HTML, XSS and external-resource tests |
| REPORT-006 | Bound report input to 4 MiB and reject malformed, duplicate, invalid-UTF-8-text or internally inconsistent documents | malformed/tamper/size tests and independent QA |

`VerificationReport` is the authoritative versioned JSON contract; `to_html()` is a
presentation generated from it. Both show content identities, not signatures. The optional
fault summary retains an explicit synthetic label plus source/plan/derived hashes. The HTML
does not embed complete telemetry bytes, authenticate a producer, establish build identity,
or replace the durable journal/evidence databases. Operator file export and dashboard use
remain later integration work.

## Deterministic synthetic faults v1

Tracked in [issue #13](https://github.com/lvlunario/project-chimera/issues/13), target M2
October 17. Bounded P3 implementation, not P3 gate closure or physical-system validation.

| ID | Requirement | Evidence |
|---|---|---|
| FAULT-001 | Strict versioned plan; unique one-based sample indices; finite ASCII-decimal replacement strings; bounded bytes/count/value lengths | `tests/test_faults.py` plan/shape/bound tests |
| FAULT-002 | Same source and canonical plan produce identical CSV bytes without source mutation, random state or decimal rounding | exact vector, order and low-precision-context tests |
| FAULT-003 | Invalid/changed source, missing target index or oversized output fails closed, never returns a valid fault result | invalid-source/identity/index tests; independent output-bound test in `tests/test_faults_qa.py` |
| FAULT-004 | Preserve synthetic label, procedure version, full fault plan/digest and source/derived identities in detached JSON | manifest/detachment tests |
| FAULT-005 | Persist fault provenance, Boolean check and failing-sample report through journal/export/store/reopen without replay; report input identity agrees with derived identity | `examples.fault_demo`, normal/optimized demo tests and installed-wheel control |

Literal replacements exercise software failure detection, not attenuation/channel physics.
`parse_link_csv` shares the existing file-loader validation contract; no new permissive parser.
Fault manifest generation recomputes the result; it is not an independently authenticated
artifact or source-byte bundle. Full source bytes and code-build provenance remain later work.

## Communications-link CSV adapter v1

September 21 bounded adapter/report evidence is in `tests/test_telemetry.py`. This begins
P3/P4 and integrates one synthetic CSV-to-durable-verdict/report path; it does not close
P2/P3/P4 or record PM acceptance.

| ID | Requirement | Current acceptance evidence |
|---|---|---|
| ADAPT-001 | Accept only exact UTF-8 CSV columns `timestamp_utc,link_margin_db`; require at least one row | valid/schema/encoding tests |
| ADAPT-002 | Require exact UTC, strictly increasing timestamps and finite, unpadded ASCII-decimal dB values | timestamp/margin negative tests |
| ADAPT-003 | Bound input to 1 MiB and 10,000 samples before use | byte and row limit tests |
| ADAPT-004 | Identify exact input bytes with lowercase SHA-256 and reject changes before each load | identity/change and LF/CRLF tests |
| ADAPT-005 | Compare minimum margin with exact decimal arithmetic; invalid data/thresholds never become requirement FAIL | boundary, excessive-precision, malformed and threshold tests |
| ADAPT-006 | Journal ingestion/config/check, preserve threshold and input summary, export completed evidence, reopen immutable storage and reproduce verdict without callback replay | durable integration test and installed-wheel check |
| ADAPT-007 | Produce a versioned canonical JSON report containing input identity, exact threshold/minimum, verdict and every below-threshold sample in source order | report round-trip, detachment and exact-finding tests |
| ADAPT-008 | Run the report after a valid Boolean FAIL while keeping the requirement binding on the Boolean check; malformed ingestion blocks both | durable failed-report and malformed-control integration tests |
| ADAPT-009 | Ship passing, failing and malformed synthetic reference fixtures with expected outcomes | fixture tests and `examples.link_csv_demo` |

The ingestion manifest records content identity, byte/sample counts, time range, declared
dB unit and exact-decimal minimum as text. The separate report retains every failing sample
and reopens without telemetry access. It does not copy the complete source file or
authenticate its producer. User-supplied paths are trusted local files; live radios,
streaming data, signatures, fault injection, HTML and general reports remain outside this
slice.

## Per-task journal and bounded recovery

September 19 journal evidence is in `tests/test_journal.py`; September 20 bounded-resume
and commit-reconciliation evidence is in `tests/test_resume.py` and
`tests/test_commit_recovery.py`; completed-export evidence is in
`tests/test_journal_export.py`. None closes P2 or records PM acceptance.

| ID | Current journal evidence |
|---|---|
| RECOVER-001 | committed results are visible to the next task and survive reopen; SIGKILL preserves a running marker |
| RECOVER-002 | death after a synthetic effect yields needs_attention/running without callback retry; repeated inspection is idempotent |
| RECOVER-003 | September 20 bounded resume preserves terminal tasks, validates the exact plan, executes only a pending suffix, blocks descendants of prior failure and continues independent pending work |
| RECOVER-004 | non-finite result and KeyboardInterrupt stop scheduling and preserve attention-required state |
| RECOVER-005 | journal ownership spans callbacks; a second recovery/runner is refused while active and process death releases ownership |
| RECOVER-006 | creation, task-marker, exact terminal-payload, final-run, inspection and resume-claim commits reopen on a fresh connection after injected pre/post-COMMIT errors; callbacks execute at most once; conflicts become non-resumable; missing storage never claims durable attention |
| RECOVER-007 | only an exact-plan completed journal exports schema-v1 evidence with original identity/timestamps/order/dependencies/results; partial/conflicted/corrupt journals fail closed; reopen/export/storage/verdict handoff executes no callbacks |

Canonical changed-plan rejection, strict schema/state validation, immediate mutable-result
detachment, exceptions/blocking/independent continuation, empty runs and installed-wheel
inspection are also tested. RECOVER-003 has bounded synthetic evidence; integration and
PM acceptance remain pending. RECOVER-006 now has bounded synthetic reconciliation
evidence but remains unaccepted until the integrated P2 gate review.
RECOVER-007 now has bounded synthetic export/agreement evidence but remains unaccepted
until vertical integration and P2 review. The journal uses a separate
database from immutable completed evidence; cross-database atomic bundling is not claimed.

Planned P2 requirements STORE-001–004 and RECOVER-001–007 are defined in
[the storage/recovery contract](STORAGE.md) and tracked in
[issue #12](https://github.com/lvlunario/project-chimera/issues/12). Partial journal
evidence exists for RECOVER-001–007 above; no recovery requirement or P2 gate
is fully accepted. STORE-001–004 completed-artifact coverage is implemented below.

## Immutable completed-artifact storage v1

RECOVER-005 prerequisite (September 16): `tests/test_ownership.py` and independent
`tests/test_ownership_qa.py` verify the Linux/local-file ownership guard: second-owner
refusal outside SQLite transactions, exception/SIGKILL release, fork/exec descriptor
safety, same-inode alias contention and changed-path rejection. Installed-wheel
exclusion/release is checked in `scripts/verify_clean_install.sh`. Decision 0009 later
integrates the guard into the journal runner and inspect-only recovery. RECOVER-005
now spans runner, resume, reconciliation and export entry points; no phase gate closes
from primitive or bounded journal tests alone.

September 16: `tests/test_storage.py` and independently derived
`tests/test_storage_qa.py` exercise the first P2 slice (issue #12).

| ID | Current completed-artifact evidence |
|---|---|
| STORE-001 | process/connection reopen reproduces assessment without callback execution; multiple selected mappings preserve originals |
| STORE-002 | identical save is acknowledged; changed same-ID content conflicts; independent concurrent process saves serialize |
| STORE-003 | denied binding INSERT after run INSERT rolls back all artifacts/association; healthy retry succeeds |
| STORE-004 | schema version/definitions, JSON/digests and relationship corruption fail closed on reopen/read/write |

Installed-wheel storage round trip is in `scripts/verify_clean_install.sh`.
Process restart tests are not power-loss durability, resumable execution, authenticity
or full procedure/input provenance evidence. Candidate results belong in the daily log.

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

Python 3.12.14 is locally verified. Python 3.11/3.12 hosted installation evidence
is linked below under CI; each new candidate must pass its own matrix.

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

## Requirement verdict interpretation

Tracked in [issue #9](https://github.com/lvlunario/project-chimera/issues/9).
Implemented as a separate Python API; existing task status, snapshot v1 and CLI
exit codes remain unchanged. `all_passed` covers only explicitly selected requirements.

| ID | Requirement | Acceptance test in tests/test_verdicts.py |
|---|---|---|
| VERDICT-001 | Require explicit nonempty string requirement/task identifiers and deterministic ordering | test_invalid_bindings; test_boolean_verdicts_and_report_continuation |
| VERDICT-002 | Exact boolean success produces pass/fail; execution/nonboolean errors never pass; missing/blocked means not_evaluated | test_boolean_verdicts_and_report_continuation; test_non_boolean_values_are_errors; test_error_blocked_and_missing |
| VERDICT-003 | Reload and assess without executing or modifying evidence | test_round_trip_does_not_execute |
| VERDICT-004 | Return detached immutable outcomes tied to run, task and requirement | test_binding_copy_and_immutable_result; test_round_trip_does_not_execute |
| VERDICT-005 | all_passed requires a nonempty selection with only pass verdicts | test_empty_is_not_pass; test_complete_pass; negative outcome tests |

The clean-install script also exercises the installed verdict API after snapshot reload.
Versioned requirement bindings are implemented below. Procedure/input provenance, measured
data and operator verdict exit codes remain later integration work; this is not full P4
traceability or PM acceptance.

## Requirement-binding artifact v1

Tracked in [issue #10](https://github.com/lvlunario/project-chimera/issues/10).

| ID | Requirement | Acceptance test |
|---|---|---|
| BIND-001 | Serialize an exact schema-versioned requirement-to-task mapping and reload it without task execution | `test_mapping_round_trip_is_canonical_and_detached`; `test_serialized_bindings_identify_assessment` |
| BIND-002 | Reject malformed structure, duplicate fields/requirement IDs, unsupported versions and empty/non-string IDs | `test_rejects_invalid_documents`; `test_rejects_non_mapping_and_non_string_mapping_ids` |
| BIND-003 | Canonicalize by requirement ID so equivalent mappings have identical JSON and SHA-256 identity | `test_equivalent_order_has_same_json_and_digest`; `test_json_is_utf8_stable` |
| BIND-004 | Tie each assessment to both the completed run ID and exact binding content identity | `test_serialized_bindings_identify_assessment`; installed-wheel verification |

The SHA-256 value identifies canonical content; it is not a signature and does not prove
who approved the mapping. Bindings remain a separate artifact from completed-run schema v1,
avoiding a silent schema change. Requirement text, thresholds, procedure/configuration identity,
input hashes, signatures and durable multi-artifact storage remain P2/P4 work.

CLI-001–005 are verified on development head `1ea07c7e` by 49 local tests,
independent negative-path QA, isolated installed-wheel execution and
[hosted run 34753672209](https://github.com/lvlunario/project-chimera/actions/runs/34753672209)
on Python 3.11/3.12. The preceding run's publication-mode failure and corrective
evidence are preserved in the daily log. This does not close P1 or imply PM acceptance.
