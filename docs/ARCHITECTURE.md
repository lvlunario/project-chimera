# Architecture decision 0001: deterministic core first

Next contract: [P2 storage/recovery contract](STORAGE.md), September 15–16.
It specifies atomic artifact associations, separate task journaling,
lifetime runner ownership and conservative uncertain-outcome recovery. The
completed-artifact, ownership, journal, pending-only resume and task-commit reconciliation
slices plus completed-journal export are implemented; vertical integration remains, with
PM acceptance pending. The first strict communications CSV adapter slice is also
implemented, including a versioned failing-sample JSON report; combined phase-gate and
general report integration remain. These decisions do not supersede the P1 decisions below.

## Decision 0014: report findings separately from the Boolean requirement check

September 21, 2026. Implemented as a bounded P3/P4 slice; gate/PM acceptance pending.
Generate a canonical schema-v1 link-margin report from validated telemetry with the exact
input digest/length, rule, unit, decimal threshold and minimum, Boolean verdict, sample
count and every below-threshold sample in source order. Validate the complete document on
construction/reopen and serialize with stable key ordering and separators.

Keep `COM-LINK-001` bound to a separate exact Boolean task. A valid `False` is a successful
check execution, so its dependent report still runs and preserves investigation details.
Malformed or changed input fails ingestion and blocks both check and report, producing
`not_evaluated` rather than a misleading threshold failure. This separation prevents a
presentation artifact from redefining requirement semantics.

Tradeoffs: the report proves agreement with its own fields and exact input identity, but
does not embed all source bytes, authenticate the producer, sign the artifact or support a
general/HTML report model. It is stored as a task value inside existing run evidence rather
than as a separately indexed atomic artifact. Those are later P4/release concerns.

## Decision 0013: hash exact CSV bytes and reload against that identity

September 21, 2026. Implemented as a bounded P3 adapter/P2 integration slice;
gate/PM acceptance pending. The communications adapter accepts one exact UTF-8 CSV schema:
`timestamp_utc,link_margin_db`. It requires an exact UTC timestamp grammar, strictly
increasing times, finite ASCII-decimal dB values, at least one sample, no more than 10,000
samples and no more than 1 MiB.

Hash the exact bounded source bytes before execution. The integrated workflow includes
that SHA-256 identity in journal operation IDs and the ingestion manifest, plus preserves
the threshold/unit/rule as a separate configuration task. Each ingestion/check callback reloads
and verifies the same digest. This makes process restart possible without depending on an
in-memory dataset and converts a changed file into an execution error rather than a false
engineering verdict. Line-ending changes intentionally create a different identity even
when parsed samples match.

Use exact `Decimal` comparison for the minimum sample margin. This prevents an arbitrarily
precise value just below 3 dB from rounding to binary `3.0` and falsely passing. Valid
measurements below threshold are requirement FAIL; malformed, changed or missing input is
an execution error and can never pass or become a threshold FAIL.

Tradeoffs: callbacks reread a small bounded file, and local paths/producers are trusted.
The evidence retains a summary, exact input identity and threshold configuration. Decision
0014 adds every failing sample in a canonical JSON task value. Signatures, atomic
file/database bundling, streaming/live-radio input, fault injection and authenticated
report provenance remain later work. SHA-256 proves sameness of bytes, not truth or
authorization of the measurement.

## Decision 0012: export completed journals through the existing evidence schema

September 20, 2026. Implemented as a bounded P2 slice; gate/PM acceptance pending.
`export_journal_evidence` opens an existing journal without creating files or directories,
holds lifetime ownership, validates the entire database and exact `JournalPlan` in one read
transaction, and accepts only lifecycle state `completed`. It maps durable task rows into
the existing schema-v1 `RunEvidence`, preserving the original run ID, timestamps, plan
order, dependencies, canonical values and exact error text. `RunEvidence` performs the
final schema validation and returns detached JSON.

Incomplete, needs-attention and commit-conflicted runs are storage views, not completed
evidence. Missing/wrong task rows, corrupt state or a changed plan fail closed. Export is
callback-free and interoperates with the immutable artifact store, but that handoff is a
copy across two databases—not an atomic bundle.

Tradeoff: schema-v1 evidence does not contain operation IDs or the journal plan digest.
The export proves exact plan agreement during conversion, but the standalone artifact
cannot later prove which operation identities were checked. Expanding provenance requires
a separately versioned evidence contract; this slice does not silently change P1 schema.

## Decision 0011: reopen and compare an ambiguous task commit

September 20, 2026. Implemented as a bounded P2 slice; gate/PM acceptance pending.
When SQLite reports an error around a task transition, keep lifetime database ownership,
discard the suspect connection, reopen the existing database without creating it, validate
the full schema/plan, and compare state, canonical result JSON and error text with the exact
intended write. Continue only when that complete record matches.

If a pending-to-running marker was not committed, repeating that marker is safe because the
callback has not been entered. If a callback returned but its terminal write is still
`running`, persist `needs_attention` and stop all later scheduling; never repeat the callback.
A final run-state write can be retried after all task records are terminal because it invokes
no callback. Missing/replaced/corrupt storage raises an explicit unavailable error and never
claims attention was persisted.

This is not general exactly-once execution: external systems still need adapter-specific
idempotency/reconciliation. Creation, resume-claim and attention-inspection mutations use
the same callback-free reopen/retry rule. RECOVER-006 has bounded synthetic evidence but
remains unaccepted until integrated P2 review; Decision 0012 adds completed journal export.

## Decision 0010: resume only a proven pending suffix

September 20, 2026. Implemented as a bounded P2 slice; gate/PM acceptance pending.
An explicit `resume_journaled` call acquires lifetime ownership, validates the complete
canonical plan and durable state, preserves every terminal task, and executes only the
remaining pending suffix. A run abandoned between commits may resume because no callback
was marked running. A run containing any running task is changed to `needs_attention`
and refused in full, including independent pending work.

This chooses safety over availability: Chimera will not guess that an unknown task is
safe just because later work is independent. Resumed exceptions retain normal failure/
blocking semantics; interrupts, invalid results and storage errors stop scheduling and
leave the current task unknown. An already completed run is returned without callbacks.
Operation IDs remain trusted declarations, not authenticated code hashes. Decision 0011
adds bounded creation/task/finish/inspection/claim reconciliation; Decision 0012 adds
completed export. Adapter-specific idempotency remains later work.

## Decision 0009: separate owned journal and inspect-only recovery

September 19, 2026. Implemented as a bounded P2 slice; gate/PM acceptance pending.
Keep the task journal in its own strict SQLite schema rather than adding tables to the
completed-artifact database. `EvidenceStore` deliberately validates an exact version-1
schema; silently extending that database would break existing evidence stores or require
a separately tested migration. Separation preserves both contracts while interfaces settle.

Require a canonical plan containing stable operator-supplied operation identities.
Hold `DatabaseOwnership` before schema initialization or lifecycle mutation and across
every callback. Commit a running marker before an effect and a detached terminal JSON
value before scheduling the next task. After interruption, matching-plan inspection marks
the run needs_attention but accepts no callbacks and performs no retry.

Tradeoff: the two databases are not an atomic evidence bundle, and operation identifiers
are declarations rather than authenticated code hashes. Decision 0010 later adds bounded
pending-only resume; Decisions 0011–0012 add reconciliation and completed export. This conservative boundary
prevents a missing result from being mistaken for proof that an effect never occurred.

## Decision 0008: lifetime ownership independent of SQLite transactions

September 16, 2026. Linux/local-filesystem prerequisite, not integrated recovery.
Use nonblocking advisory `flock` on an existing database inode rather than a PID
file/expiry lease. The kernel releases descriptors on process death, avoiding a
clock-based guess that a slow callback is dead. Keep the descriptor open across
transactions; normal SQLite connection close does not release the independent lock.
Fork children close inherited descriptors without explicit unlock; exec closes them.

All future runner/recovery entry points must cooperate and check stable inode identity
before transitions/callbacks. Reject hardlinks; require trusted stable paths and one
owning context/thread. This does not defend against hostile pathname replacement,
network filesystems, uncooperative programs or callbacks that bypass ownership.
Existing P1 APIs remain unchanged. Separate sidecar locks were not selected because
deletion/recreation and path aliases can accidentally create independent lock domains.
Locking the database inode avoids that sidecar alias problem but still requires the
database itself never be replaced during use. Unknown task outcomes need journaling;
ownership does not establish exactly-once effects or recovery gate acceptance.

## Decision 0007: atomic immutable completed-artifact pairs

September 16, 2026. First P2 implementation slice; gate/PM acceptance pending.
Use standard-library SQLite, explicit atomic run/binding/association transactions,
strict schema/content validation and conflicts rather than REPLACE/upsert updates.
This preserves an original run while allowing multiple separately selected binding
interpretations. Load is read-only and never executes callbacks. FULL synchronous
is not a guarantee against defective disks or external side effects. A failed COMMIT
can be ambiguous and requires inspection; no implicit retry is implemented.
Alternative: separate JSON files with inferred filename relationships. Rejected for
this slice because a failed second write could leave a misleading partial handoff.
Update September 19–20: Decisions 0009–0010 implement the separate per-task journal,
ownership integration and pending-only resume; cross-artifact bundling remains later work.

Status: accepted for foundation.

Use a small Python standard-library execution kernel before network services or
LLM agents. Task IDs and dependencies define a directed acyclic graph. Validate
the entire graph before running any task, so malformed input cannot partially run.
Among ready tasks, choose lexicographic ID order for reproducibility.

A task succeeds when its trusted callable returns, fails when it raises Exception,
and is blocked when any dependency did not succeed. Independent tasks continue.
KeyboardInterrupt and SystemExit propagate to the caller. A task with a failing
assertion is a failure, not a successful return of a false-looking value.
Dependencies order execution; they do not currently pass data between callables.

The base run API returns in-memory results. The optional evidence API now provides
schema-versioned completed-run JSON snapshots with timestamps (decision 0002 below).
Requirement IDs, artifact hashes and durable execution remain planned before retries.
The callable interface allows future engineering adapters and bounded AI workers.
Untrusted code requires a separate isolated execution design.

Tradeoff: sequential execution is simple to reason about and test, but slow for
large workloads. Determinism applies to scheduling, not arbitrary task behavior.

## Decision 0002: strict completed-run JSON snapshots

Status: implemented and independently reviewed for this bounded increment;
P1 gate and PM acceptance pending. September 12, 2026.

`run_with_evidence` preserves the existing scheduler and returns a validated
`RunEvidence` containing schema version 1, run UUID, UTC start/finish and ordered
task records. Reload validates structure and dependency/outcome consistency without
executing code. Both execution entry points freeze dependency sequences before
preflight, preventing caller-list mutation from changing the approved graph.

Strict finite JSON values preserve meaning across reload. Reject arbitrary objects,
tuples, non-string dictionary keys, NaN/infinity, duplicate JSON keys and unknown
fields/versions rather than using repr, pickle or silent conversion. Internally
retain validated JSON text; dictionary access produces a copy.

Alternative: a durable execution journal. Deferred to P2 because restart recovery
needs explicit side-effect/idempotency semantics, not merely a file write. This
increment snapshots values at run completion, not each task's return time. If later
tasks mutate shared outputs, those final values are captured. An unrepresentable
value raises EvidenceError after execution; do not retry automatically. Interrupts
propagate and produce no completed record. A backward wall-clock jump is rejected.
There are no authenticity, tamper-proofing, resource-limit or crash-safety guarantees.
At initial implementation, requirement verdict categorization and full provenance
were still pending.

Update September 14: decision 0005 implements a separate interpretation layer for
explicit boolean checks. Full provenance and durable binding storage remain pending.

## Decision 0003: standard wheel with zero runtime dependencies

Status: implemented, locally integration-tested and independently reviewed; P1 gate
remains pending. September 13, 2026.

Package the current kernel as the `project-chimera` Python distribution using
PEP 517 metadata and setuptools. Keep the import package named `chimera`, expose
the existing synthetic runner as `chimera-demo`, and retain zero runtime dependencies.
The development version is `0.1.0.dev0`; it is not a release tag or stability claim.

The clean-install check builds a wheel from a temporary source copy, creates a new
virtual environment, installs the wheel with `--no-index --no-deps`, and changes to
a directory outside the checkout before importing. This prevents a common false
positive where tests accidentally import local source instead of installed files.
Wheel building deliberately uses the maintainer environment's installed build backend
with `--no-build-isolation`; the later CI matrix will test declared Python versions
and build-backend setup. No package is uploaded to an index.

## Decision 0004: declarative allowlist at the operator boundary

Status: implemented, independently reviewed and hosted-CI verified; P1 gate and PM
acceptance pending.
September 13, 2026.

The operator CLI accepts schema-versioned JSON and converts only two allowlisted,
side-effect-free operations into tasks: `emit` returns a finite JSON value and `fail`
raises an expected synthetic task failure. Workflow fields cannot name a Python module,
callable, shell command, URL or adapter. Strict fields, duplicate-key rejection,
UTF-8 and finite-value checks, one MiB input, 1,000-task/dependency bounds and short
IDs/messages constrain ambiguity and accidental resource use before graph execution.

The command refuses an evidence path that exists and uses exclusive creation after
the run to resist overwrite races. Exit 0 means all workflow tasks succeeded; exit 1
means a completed record contains a failure or blocked task; exit 2 means no valid run
was established; exit 3 means evidence could not be created. A completed failed run
still writes evidence because failure is an outcome worth preserving.

Alternative: import Python callables named in JSON. Rejected because it would turn a
data file into an arbitrary code-execution interface. Future telemetry/fault adapters
need separately reviewed, typed operation schemas. The current runner remains in-process
and is not a security sandbox; bounded parsing is defense in depth, not hostile-input
isolation. Exclusive creation is not an atomic durable journal or crash recovery.

## Decision 0005: interpret boolean checks separately from execution

September 14, 2026. Implemented for P1; integration evidence is in the daily log.
P1 gate and PM acceptance remain pending.

`assess_requirements` takes validated `RunEvidence` plus explicit requirement-to-task
bindings. Exact True/False values from succeeded tasks mean pass/fail. Other returned
values mean error, raised exceptions mean error, and blocked/absent tasks mean
not_evaluated. Assessment includes the run ID and immutable ordered outcomes with
requirement ID, task ID and reason. Empty selections cannot claim all_passed.

A boolean False is a completed check, so dependent handoff tasks may still execute.
Dependency edges gate on execution success, not requirement verdict; this is unchanged.
An explicit binding declares a task to be a trusted boolean check. We do not scan
arbitrary values for pass-like strings or infer requirements from task names.

Alternative: extend task status or reinterpret all False outputs as execution failures.
Rejected because it conflates an engineering finding with a procedure fault, blocks
useful handoff work, and changes the existing CLI contract. Schema-v1 evidence is
unchanged. Assessments are derived in memory, not a new durable evidence schema.
Reproduction requires the same snapshot AND the same caller-supplied bindings.
Binding/procedure/input provenance must be persisted before P4 report acceptance.
The current CLI still reports execution exit codes, not overall requirement acceptance.

## Decision 0006: version bindings separately and identify canonical content

September 15, 2026. Implemented for the P1 interface baseline; gate and PM acceptance
remain pending.

`RequirementBindings` stores the requirement-to-task mapping as strict schema-version-1
JSON, sorts entries by requirement ID, and calculates SHA-256 over that canonical UTF-8
representation. `Assessment` records both the completed run ID and binding digest. Reloading
the run and binding artifacts reproduces the same classification without executing tasks.
Existing mapping-based calls remain supported and are converted to the same artifact.

Keep bindings separate from completed-run evidence v1. A mapping describes how results are
interpreted and can change independently of an immutable run; embedding it now would silently
break the evidence schema contract. Later P2/P4 storage can retain both artifacts and their
relationship explicitly.

Alternative: store only the caller's dictionary or silently add bindings to evidence v1.
Rejected because the first cannot be handed off reproducibly and the second violates strict
schema versioning. The digest is a content identity, not authentication, approval, or tamper
protection. Procedure/version, requirement text and thresholds, input hashes and signatures
remain required before audit-ready reports.
