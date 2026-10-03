# P2 durable execution contract

September 15 design; completed-artifact storage landed September 16 and the separate
per-task journal/inspect-only recovery slice landed September 19 with AI assistance.
Pending-only bounded resume, commit reconciliation and completed-journal export landed
September 20; communications vertical/report integration landed September 21. The combined
P2 walkthrough and approval packet are prepared September 22; nothing is PM-accepted.
P1 remains open. Target: M2 October 17, 2026.

## Implemented ownership prerequisite (not runner integration)

September 16: `DatabaseOwnership` holds a Linux local-file nonblocking advisory
`flock` on the existing database inode, independently of SQLite transactions.
It releases on context exit or process death; fork children close inherited guard
descriptors without unlocking the parent, and exec does not inherit them. No stale
PID/clock heuristic or lock-file deletion. `check()` requires the original inode,
active owner process and a single filesystem link. Missing/special/hardlinked files
are refused; symlink aliases lock the same inode. Import remains portable but guard
acquisition currently supports Linux only. One context/thread, no cross-thread
transfer or fork during acquisition; trusted stable paths/local filesystems only.

Never replace/unlink/rename/hardlink the database during use. Identity checkpoints
detect changes, not adversarial races between checks. Advisory ownership is not a
SQLite write prohibition or sandbox. Existing `run`, `run_with_evidence` and
`EvidenceStore` are unchanged and do not acquire the guard automatically. This slice
proves the locking primitive only, **not RECOVER-005 end-to-end completion**. Future
journal/recovery entry points must hold it across callbacks and between commits.
The September 19 journal entry point now holds this guard across callbacks and commits.
Manual exercise and subprocess SIGKILL evidence are provided. Bounded resume,
reconciliation and callback-free completed export now use this ownership boundary.

## Implemented journal and inspect-only recovery boundary

`run_journaled` uses a separate SQLite journal database so adding task records cannot
silently invalidate the exact version-1 `EvidenceStore` schema. A canonical plan records
ordered task IDs, dependencies and required operator-supplied operation identities;
callback code is never serialized. The runner commits `running` before a callback,
serializes and detaches its finite JSON result immediately, commits the terminal state,
and only then schedules another task. Linux database ownership spans the whole operation.

Exceptions become durable failures, descendants become blocked and independent work
continues. KeyboardInterrupt/SystemExit, invalid result serialization and storage errors
stop scheduling; a task already marked running remains outcome-unknown. `inspect_interrupted`
requires exclusive ownership and the identical canonical plan, changes an interrupted
run to `needs_attention`, returns pending/running/terminal states, and accepts no callbacks.
It is idempotent and never resumes or retries work. A completed run remains completed.

September 20 adds explicit `resume_journaled`: under exclusive ownership it accepts the
identical canonical plan, preserves the terminal prefix and executes only tasks still
durably pending. A running task makes the entire run outcome-uncertain; resume persists
`needs_attention`, invokes zero callbacks and refuses even independent pending tasks.
Completed resume is callback-free. Resumed failures block descendants while independent
pending work continues; interrupts and invalid values again leave running/unknown state.

The September 20 bounded reconciliation slice reopens a fresh connection after injected
task-transition or finish errors, validates all durable content, and compares the exact
intended state/value/error before continuing. A durable `running` task after its callback
stops scheduling and persists attention; unavailable storage makes no such claim.

`export_journal_evidence` now requires an existing database, exact canonical plan and
completed lifecycle, then maps the original run identity, timestamps, task order,
dependencies, results and errors into validated schema-v1 `RunEvidence` in one read
transaction. Partial/attention/conflicted/corrupt journals fail closed. Repeated process
reopen is byte-identical and callback-free; the exported artifact can be saved and assessed
through `EvidenceStore` without task execution.

Schema-v1 evidence does not retain operation IDs or the plan digest, so plan agreement is
verified at conversion time rather than carried as standalone provenance. The implementation
does not authenticate operation identity or prove power-loss durability. The separate
journal and completed-artifact databases are not yet
one atomic bundle. RECOVER-006 has bounded synthetic evidence but is not accepted before
the integrated P2 review. RECOVER-007 also has bounded evidence but remains unaccepted
until the communications vertical and P2 review.

## Implemented completed-artifact boundary

`EvidenceStore` uses schema version 1 and immutable runs/bindings/associations.
`save` uses BEGIN IMMEDIATE for validation/conflict detection and all inserts in
one transaction; `load` uses a read transaction for a consistent selected pair.
Identical saves perform no content updates. Existing run identity with changed
evidence raises StorageConflict. Unknown/forged schema, triggers/views, inconsistent
JSON, hashes or relationships are rejected. SQL parameters carry operator IDs.
FULL synchronous, foreign keys and a five-second busy timeout are verified.
This initial implementation scans all artifacts for consistency on open/save/load;
acceptable for bounded prototype fixtures, not a benchmarked large-data service.
Use one local connection per caller, never across threads. Short SQLite write locks
serialize artifact transactions; they are NOT process-lifetime runner ownership.
SQLite errors propagate; failed commit can be ambiguous. Reopen and inspect the
selected pair before deciding what to do; there is no automatic retry/reconciliation.
Stored hashes detect accidental mismatch, not authenticated tampering. Coordinated
edits to documents and hashes are not prevented. Only completed P1 snapshots are
stored; no task plan/configuration identity, journal or partial-run export exists yet.

## Problem and boundary

Completed-run JSON cannot explain an interruption halfway through execution.
P2 will retain a validated execution plan and commit each task result before
another task starts. SQLite is the proposed local store; no service or paid
infrastructure is needed. Keep existing P1 APIs and schema-v1 exports unchanged.
The first implementation slice is an immutable completed-run/binding repository;
task journaling follows separately. A snapshot repository alone does not close P2.

## Proposed records and invariants

Store schema metadata, runs, ordered task plans/results, and binding artifacts.
A run records its UUID, UTC times, workflow/configuration identity, lifecycle and
storage schema version. A completed-run artifact retains P1 JSON; bindings retain
their canonical JSON and digest. Relationships are explicit, never inferred from
filenames. A content digest identifies bytes, not approval or authenticity.
One immutable run may associate with multiple immutable binding digests. Adding a
new association must not alter an existing artifact or pretend the original mapping
was approved. Each assessment identifies its selected run/digest pair explicitly.

Use one sequential writer and local filesystem storage. Start with an explicit
transaction boundary, foreign-key enforcement, FULL synchronous mode and a bounded
busy timeout. Verify effective settings; refuse unknown storage schema versions.
No distributed workers, network filesystem guarantees or concurrent runners.
Writer transactions are not a runner ownership guard: the new process-lifetime
ownership primitive must be integrated to cover callback execution and recovery, including
the intervals between commits. Its supported platform and crash-release behavior
must be declared and tested before any resumable runner ships.
Readers cannot observe a half-written run/binding pair. Do not use REPLACE to hide
conflicts. Existing identical content may be acknowledged without mutation; the
same run ID with different evidence is a conflict, not an update.

Run lifecycle: pending → running → completed. An interrupted running run becomes
needs_attention when explicitly recovered under exclusive operator ownership.
Task lifecycle: pending → running → succeeded/failed; dependency blocking commits
blocked. Terminal results never revert to pending. An empty valid plan may complete.
Requirement fail remains a successful task with False; it does not become an
execution failure. Missing/nonboolean evidence never becomes a passing verdict.

Before invoking a task, commit its running marker. After return/Exception, serialize
and detach its result immediately, then commit the terminal result. Only then choose
another task. This differs from P1's completion-time snapshots and must have separate
tests; do not silently change run_with_evidence behavior. Interrupts propagate.
Unserializable output or a commit failure stops execution and leaves attention-required
state; neither permits implicit retry. Completed export requires all tasks terminal.
If COMMIT raises or a connection is lost, the commit outcome may be unknown. Stop
scheduling, reopen a healthy connection under exclusive ownership, and reconcile
the durable record before any transition or retry. Do not assume rollback or claim
needs_attention was persisted through a failed connection. If reconciliation fails,
report storage unavailable/unknown and retain the last verifiable state.
Partial runs are a distinct storage view, not malformed schema-v1 completed evidence.

## Recovery and idempotency policy

Reopening evidence never executes tasks. Recovery first validates schema, plan identity,
dependency consistency, artifact identity and terminal results; corruption fails closed.
Refuse resume with changed workflow/configuration or unidentified callable behavior.
An active owner must not be mistaken for a crashed process: initially require exclusive
ownership and explicit operator recovery, not an automatic time-based lease heuristic.

- Committed terminal tasks are not executed again during resume.
- Pending tasks may continue only after the recovery policy and plan are validated.
- A running task at interruption has an unknown outcome. Stop for attention unless a
  separately reviewed side-effect-free adapter explicitly permits retry.
- Default trusted Python callables have unknown effects and are never auto-retried.

A process may perform an external effect and die before committing its result.
SQLite cannot undo that effect or prove it happened exactly once. A future adapter
needs its own idempotency key/reconciliation contract; live hardware remains excluded.
First journaling slice may support inspect-only recovery before bounded synthetic resume.

## Planned requirements and evidence (not passing claims)

| ID | Contract | Required test evidence |
|---|---|---|
| STORE-001 | Atomic immutable completed-run/binding association | reopen after connection/process restart; round trip and identical assessment; multiple binding associations preserve originals |
| STORE-002 | Explicit identity conflicts, no overwrite | duplicate identical save; changed same-ID save; concurrent duplicate attempts |
| STORE-003 | Failed transaction exposes no partial association | injected failure between artifact writes; rollback; retry without orphan records |
| STORE-004 | Strict schema/content validation | unknown version, corrupt JSON/digest and invalid relationship rejected |
| RECOVER-001 | Committed task results survive interruption | subprocess termination before/after terminal commit; reopening never invokes tasks |
| RECOVER-002 | Unknown outcomes do not silently retry or pass | death after running marker/effect; needs_attention and invocation-count controls |
| RECOVER-003 | Resume preserves validated plan and terminal work | changed plan rejected; completed tasks not repeated; pending descendants obey dependencies |
| RECOVER-004 | Failure to serialize/commit stops scheduling | unsupported return value and storage error; consumer not invoked |
| RECOVER-005 | Lifetime ownership excludes a second runner/recovery | second process refused during callback and between commits; guard releases after owner death |
| RECOVER-006 | Ambiguous commit is reconciled, never blindly retried | inject error after successful commit and connection loss; reopen observes terminal or running state correctly; unavailable storage never claims persisted attention |
| RECOVER-007 | Completed exports agree with journal/plan | missing/duplicate results, wrong task IDs and partial runs rejected; later callback mutation cannot alter committed output |

Use temporary databases and synthetic invocation counters. Subprocess kill tests
establish process-interruption behavior, not power-loss or defective-disk durability.
Add clean-wheel coverage and Python 3.11/3.12 CI for every implementation candidate.
Independent AI QA must inspect transaction boundaries and reproduce negative paths.
No gate closure from this design or a future happy-path round trip alone.

## Delivery slices and Leo's participation

1. Immutable completed-run/binding save/load with rollback/conflict evidence.
2. Per-task journal with immediate detached outputs and inspect-only recovery. Implemented
   September 19; gate remains open.
3. Explicit bounded synthetic resume. Implemented September 20; gate remains open.
4. Creation/task/finish/inspection/claim ambiguous-commit reconciliation and completed
   export implemented September 20; CSV/report integration landed September 21.
5. Combined executable P2 walkthrough and approval packet prepared September 22; exact-
   candidate evidence and Leo's actual verification/validation disposition remain.

Each slice stays in draft PR #1 while open. P0/P1 decisions remain pending; this
reversible design does not authorize merge or change scope. M2 remains October 17;
if journaling/integration evidence is incomplete, report a slip rather than claiming
that snapshot persistence satisfies recovery. November 29–December 12 is stabilization.

Teaching note: after a crash, “I have no saved result” does not mean “the task never
ran.” Conservative recovery trades convenience for avoiding duplicated effects.
Practical review exercise: run `python -m examples.journal_demo`. A synthetic task
performs an effect then its process dies before result commit. Expected: needs_attention,
running/unknown task, zero callback invocations during recovery and no automatic retry.
Recommendation: retain conservative recovery. The runnable candidate is now presented in
[`reviews/2026-09-22-p2.md`](reviews/2026-09-22-p2.md); Leo's actual disposition remains
required before P2 gate closure.
