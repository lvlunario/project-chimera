# Architecture decision 0001: deterministic core first

Next design candidate: [P2 storage/recovery contract](STORAGE.md), September 15.
It specifies planned atomic artifact associations, separate task journaling,
lifetime runner ownership and conservative uncertain-outcome recovery. This is
not implemented or accepted, and does not supersede the P1 decisions below.

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
