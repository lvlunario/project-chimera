# Architecture decision 0001: deterministic core first

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
Requirement verdict/failure categorization and full provenance are still pending.

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
