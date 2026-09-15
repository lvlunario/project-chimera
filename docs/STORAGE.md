# P2 durable execution contract — design candidate

September 15, 2026. AI-assisted design; not implemented, independently approved,
or PM-accepted. P1 remains open. Target: M2 October 17, 2026.

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
Writer transactions are not a runner ownership guard: a separate process-lifetime
exclusive ownership mechanism must cover callback execution and recovery, including
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
2. Per-task journal with immediate detached outputs and inspect-only recovery.
3. Explicit bounded synthetic resume; integration with CSV slice and P2 packet.

Each slice stays in draft PR #1 while open. P0/P1 decisions remain pending; this
reversible design does not authorize merge or change scope. M2 remains October 17;
if journaling/integration evidence is incomplete, report a slip rather than claiming
that snapshot persistence satisfies recovery. November 29–December 12 is stabilization.

Teaching note: after a crash, “I have no saved result” does not mean “the task never
ran.” Conservative recovery trades convenience for avoiding duplicated effects.
Practical review exercise: a synthetic task increments a counter then the process
dies before result commit. Expected proposed outcome: needs_attention, no automatic
second increment, no completed export. This exercise is not runnable yet.
Recommendation: retain conservative recovery; no additional PM decision required
until a runnable P2 candidate is presented under the phase approval guide.
