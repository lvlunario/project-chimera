# Chimera project manual

## Database ownership guard (Linux prerequisite)

Implemented September 16: `DatabaseOwnership` protects an existing local database
inode with a nonblocking, cooperative process-lifetime lock. It does not journal,
execute, resume or recover tasks. P1 runners and `EvidenceStore` do not automatically
acquire it. Future journal/recovery entry points must integrate it before RECOVER-005
can be accepted end to end. Current support: Linux, local filesystem, one owning
context/thread; no network filesystems or cross-thread transfer/fork during acquisition.

```python
from chimera import DatabaseOwnership, EvidenceStore

with EvidenceStore("evidence.sqlite"):
    pass  # Initialize the database first, without running tasks.
with DatabaseOwnership("evidence.sqlite") as owner:
    owner.check()
    # Future journal transitions/callbacks must remain inside this lifetime.
```

Another guard on the same file raises `OwnershipBusy` immediately, even after a
SQLite transaction or connection closes. Normal exit, exceptions and process death
release ownership. Fork children drop their inherited guard descriptors without
unlocking the parent; descriptors do not survive exec. Child code must acquire its
own guard before use. No PID file, clock deadline or stale-lock deletion is used.
Missing paths are not created; filesystem errors propagate. Non-Linux acquisition
raises `OwnershipError` without preventing import/use of the existing P1 APIs.

Use a trusted directory, stable path and no hardlinks. Symlink aliases contend on
the same inode. **Never replace, rename, unlink or hardlink a database while in use.**
`check()` detects identity changes at checkpoints, not hostile changes between
checks. Advisory locks do not stop uncooperative programs, SQLite writes, or trusted
callbacks that bypass the guard. This is not schema validation or security isolation.

Run `python -m examples.ownership_demo` on Linux. Expected: two PASS lines showing
second-owner refusal after SQLite close and acquisition after release. The temporary
database is removed. Unit/independent QA tests additionally kill a synthetic owning
process and prove a new owner can acquire the file; no hardware is accessed.

Teaching note for Leo: a SQLite write lock protects a transaction, not the time
spent performing a check between transactions. The lifetime guard fills that gap.
Predict whether finishing a database write should permit a second recovery operator
to act while the original check is still running: no. It still cannot tell us what
an interrupted task did; the later journal/recovery sections show how Chimera records
that uncertainty and refuses an unsafe retry.

## Immutable completed-evidence storage

Implemented September 16 as the first P2 slice; the separate journal, bounded resume and
completed-evidence handoff are documented later in this manual.
Run `python -m examples.storage_demo` from the development checkout. Expected:
original failed verdict preserved after reopen, identical save acknowledged,
check invoked once, temporary database removed. This is synthetic evidence.

To retain an artifact pair locally after trusted task execution:

```python
from chimera import EvidenceStore, RequirementBindings, Task, run_with_evidence

evidence = run_with_evidence([Task("link-check", lambda: False)])
bindings = RequirementBindings.from_mapping({"COM-LINK-001": "link-check"})
with EvidenceStore("evidence.sqlite") as store:
    store.save(evidence, bindings)
with EvidenceStore("evidence.sqlite") as store:
    reopened_run, reopened_bindings = store.load(
        evidence.to_dict()["run_id"], bindings.sha256)
```

Save the run ID and binding digest for explicit selection. Missing associations
raise KeyError; changed same-ID evidence raises StorageConflict; malformed schema
or content raises StorageError. SQLite errors propagate, including busy/unavailable
storage. Do not automatically rerun tasks or retry a failed COMMIT: close/reopen and
inspect whether the association is durable first. CLI SQLite input/output is not
implemented; the existing CLI still writes JSON. No recovery or partial-run API exists.
Use local files and trusted completed snapshots, not network filesystems, secrets,
or production hardware data. Hashes are not proof of approval/authenticity.

Leo's exercise: predict whether reopening a stored False check calls the check
again (it must not), then run/observe the demo and explain why the verdict stays fail.
This demonstrates storage verification, not full P2 validation or acceptance.

## How to use this manual
The README is the short entry point. This versioned Markdown manual is the living
source of truth, so documentation changes can be reviewed with code in a PR.
Use a PDF/Word snapshot only when an export is requested; do not maintain a second
editable master that drifts from the repository.

Read in this order:
1. [Program](PROGRAM.md): who it serves and how work is managed.
2. [Roadmap](ROADMAP.md): prototype journey, deadlines and your phase gates.
3. [Architecture](ARCHITECTURE.md): decisions and system behavior.
4. [Requirements](REQUIREMENTS.md): what must be true and how it is tested.
5. [Quality plan](QUALITY.md): independent checks and release evidence.
6. [Kickoff review](reviews/2026-09-12-kickoff.md): current concept and open decisions.
7. [Daily logs](daily/): changes, experiments, results and next steps.

## Phase learning guide
| Phase | Question you should be able to answer | Review exercise |
|---|---|---|
| P0 Concept | Who uses this, and what problem does it solve? | Walk through one test session and its required output |
| P1 Core | How do dependencies and failures affect execution? | Predict which tasks run after a check fails |
| P2 Persistence | What survives a restart, and what must not run twice? | Compare an interrupted run with a completed one |
| P3 Adapters | Which data is valid and what do units mean? | Inspect good, malformed and missing-data fixtures |
| P4 Evidence | Why does this report justify its verdict? | Trace one requirement to input, test and result |
| P5 Operator UI | Can a new engineer complete the workflow? | Execute the operator acceptance script |
| P6 AI (stretch) | What can the AI suggest, and what remains deterministic? | Compare a suggestion with verified evidence |
| P7 Release | Can someone reproduce the result without the author? | Follow clean-install instructions and review limitations |

Each implementation iteration adds a short teaching note: problem, approach, why,
test evidence, alternative considered, and one question or exercise for Leo.
Document commands and expected output once the feature exists; mark future instructions
as planned. Do not imply that an unimplemented feature can be run.

## Reviews and participation
Daily asynchronous briefings accompany the existing morning/afternoon/evening
development sessions. Evening briefing consolidates the day. Read/reply when available.
Weekly concept/demo review: Monday morning, approximately 8 AM Manila, starting Sep 14.
Allow roughly 25–30 minutes of your time. These are review sessions in ChatGPT,
not booked calendar calls or meetings with hired personnel.

Agenda: outcome and demo (5 min), one concept (10 min), quality/schedule risks (5 min),
your questions and decisions (10 min). Attach reading links and a reproducible demo
when available. Save a review packet under docs/reviews/YYYY-MM-DD.md.
Record actual replies afterward as minutes, with decisions, owner and due date.
A delivered agenda is not a completed meeting.

Trigger an additional concept discussion when interfaces, scope, cost, critical
acceptance criteria or milestone forecasts change. Give a recommendation and impact.
Routine authorized engineering continues while feedback is pending; keep dependent
scope choices reversible. Never mark a gate accepted without Leo's response.

## Decision and change record
For each decision: ID, question, options, recommendation, rationale, impact on scope/
date/quality, owner, requested-by date, status, actual response and related issue/PR.
Use architecture decision records for technical choices, and review minutes for
product decisions. Supersede records explicitly rather than deleting their history.

## Prototype operator/developer chapters
Current runnable instructions are in the README. As milestones ship, add installation,
CSV schema/examples, CLI reference, persisted-run recovery, dashboard walkthrough,
report interpretation, troubleshooting and extension instructions here or linked
chapters. These chapters are planned, not currently implemented.

## Completed-run evidence v1

Implemented in P1; not a persistent runner or release-complete evidence bundle.
From the repository root on Python 3.11+:

```bash
python -m unittest discover -s tests -v
python -m examples.evidence_demo
```

The synthetic demo writes a temporary JSON file, reloads it and checks exact snapshot
equality. It shows health/ingest succeeded, link-check failed and report blocked.
The temporary file is removed on exit. No hardware or network is contacted.

### Python API and retaining a file

```python
from pathlib import Path
from chimera import RunEvidence, Task, run_with_evidence

evidence = run_with_evidence([
    Task("measure", lambda: {"source": "synthetic", "margin_db": 2.0}),
])
path = Path("run.json")
with path.open("x", encoding="utf-8") as stream:
    stream.write(evidence.to_json())
reopened = RunEvidence.from_json(path.read_text(encoding="utf-8"))
assert reopened == evidence
print(reopened.to_dict()["tasks"])
```

Exclusive `x` mode refuses to overwrite existing evidence. Choose a new filename
for another run. This caller-managed write is not atomic or crash-safe; disk failure
can leave a partial file, which must not be treated as a successful durable save.

Schema version 1 has exactly `schema_version`, `run_id`, `started_at`, `finished_at`
and `tasks`. Each task records `task_id`, `status`, `value`, `error`, `dependencies`.
Task order preserves execution order. Start/finish timestamps are UTC, run IDs are
UUIDs, and new runs are intentionally not byte-identical. Scheduling is deterministic;
arbitrary task behavior, wall-clock timestamps and IDs are not.

Task status is `succeeded`, `failed` or `blocked`. A successful callable may return
`False` or `None`; success means no exception, not a requirement pass verdict.
Failed/blocked tasks have an error and null value. Dependency failures must agree
with blocked status. The separate [requirement verdict API](#requirement-verdicts)
now classifies explicitly bound boolean checks without changing this schema.

Values may contain only finite JSON primitives, lists and string-key dictionaries.
Unsupported values or malformed evidence raise `EvidenceError`; graph errors and
interrupts propagate. Values are copied at completion, not at each task return.
An evidence-encoding failure happens after tasks ran: do not automatically retry,
because actions may have side effects. There is no partial-run recovery yet.

Do not place secrets or personal data in task outputs/errors: snapshots retain both,
without automatic redaction. Do not commit real operational evidence without review.
Validation checks consistency, not authenticity; someone can edit a JSON file.
No schema migration, input hashes, code/config provenance, requirement mapping,
storage service, timeout, sandbox or resource-limited untrusted-file parser is provided.

### Teaching note for Leo

The saved snapshot is the test record; executing the procedure again is a new run.
Separating the two lets another engineer inspect an outcome without repeating actions.
We reject unsupported values instead of turning them into text because a description
of an object is not necessarily enough to reconstruct its measurement.

Exercise: after loading the demo's evidence, explain why `report: blocked` is not a
failed measurement, and why a successfully saved file does not establish crash recovery.
See [architecture decision 0002](ARCHITECTURE.md#decision-0002-strict-completed-run-json-snapshots).

## Requirement verdicts

Implemented Python API: `assess_requirements(evidence, bindings)`. Bindings map each
selected requirement ID to its trusted boolean-check task ID. They may be supplied as a
mapping or a strict, versioned `RequirementBindings` artifact. This is an explicit caller
contract, not automatic discovery or validation of the requirement definition.
From a trusted checkout, run `python -m examples.verdict_demo`.

Expected: `link-check` and `handoff` execute successfully, COM-LINK-001 is `fail`,
CONTROL is `pass`, INVALID is `error`, and BLOCKED/MISSING are `not_evaluated`.
The demo saves/reopens evidence in a temporary directory and confirms an identical
assessment using the same bindings. It removes the file on exit. Measurements and
the 3 dB threshold are hard-coded synthetic examples, not a CSV or radio adapter.

```python
from chimera import RequirementBindings, Task, assess_requirements, run_with_evidence

evidence = run_with_evidence([Task("check", lambda: 2.0 >= 3.0)])
bindings = RequirementBindings.from_mapping({"COM-LINK-001": "check"})
reopened = RequirementBindings.from_json(bindings.to_json())
assessment = assess_requirements(evidence, reopened)
print(assessment.outcomes[0].verdict)  # fail
print(assessment.all_passed)          # False
print(assessment.bindings_sha256 == bindings.sha256)  # True
```

| Recorded task outcome | Requirement verdict |
|---|---|
| succeeded, exact boolean True | pass |
| succeeded, exact boolean False | fail |
| succeeded, any other value; or failed execution | error |
| blocked; or selected task absent | not_evaluated |

Strings, numbers (including 0/1), null and containers never count as boolean checks.
Empty bindings never establish all_passed. Results are immutable and sorted by
requirement ID, carrying the run ID, task ID and a reason. all_passed covers only
the supplied selection, not every product requirement or phase acceptance.

Schema-v1 evidence and CLI exit codes are unchanged. An `emit` of False still exits
0 because the CLI reports task execution, NOT requirement acceptance. Use this API
and explicit bindings to interpret it. A future operator verdict exit policy is
separate integration work. The original synthetic `fail` operation still represents
an execution error, not this new boolean requirement-failure model.

Bindings can now be serialized separately and identified by canonical SHA-256 content.
They are deliberately not inserted into completed-run schema v1. Retain both artifacts to
reproduce an assessment. The digest does not authenticate or approve a mapping. No input
hashes, procedure/configuration identity, versioned requirement definition, signatures or
full provenance are claimed. Do not use this classification alone as physical verification
or release acceptance.

Teaching exercise: why should a report/handoff task run after a False check, but
remain blocked after that check raises an exception? The first has a finding to
explain; the second lacks a valid check result. See architecture decision 0005.

## Installation

### P1 approval controls

Run `python -m examples.approval_demo` from a trusted repository checkout to check
passing, execution-error, no-overwrite, invalid-graph, requirement-failure and replay
controls. Six `PASS:` lines are expected. The demo uses temporary synthetic artifacts
and removes them; it does not establish PM acceptance or crash recovery. Follow the
[P1 packet](reviews/2026-09-15-p1.md) for verification/validation and decision instructions.

### Package installation

The development package requires Python 3.11 or newer and has no third-party runtime
dependencies. From a trusted checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
chimera-demo
```

The installed demo must show `link-check: failed` and `report: blocked`; both are
intentional synthetic outcomes. The distribution version is `0.1.0.dev0`, meaning
development build—not a supported release. Nothing is uploaded to a package index.

Maintainers can exercise the stricter integration path:

```bash
scripts/verify_clean_install.sh
```

It copies only packaging inputs to a temporary directory, builds one wheel with the
current interpreter/build backend, installs it without dependencies or index access
into a new virtual environment, then changes outside the repository. It verifies
distribution metadata, confirms `chimera` came from that environment, exercises the
public evidence API, checks the console demo, and runs the installed declarative CLI
through evidence reload. A trap removes temporary files.
The offline build step requires Python 3.11+ and local setuptools 77+; the script
checks both first and reports a direct error when the prerequisite is unavailable.

This check does not prove every platform or declared interpreter works. Python 3.11
and 3.12 CI is verified for the commits cited below; new commits need their own evidence.
The first local run used Linux/Python 3.12.14. It also
does not sign the wheel, create a reproducible byte-for-byte build, publish a release,
or protect against a malicious checkout/build backend.

### Teaching note for Leo

A source test answers “does the code work here?” A clean wheel install answers a
different question: “did we package all required code and entry points so another
environment can run it?” Changing directories after installation is the key guard;
otherwise Python might quietly load the checkout and conceal a broken package.

Exercise: if unit tests pass but `chimera-demo` is absent after installation, which
gate failed—core execution or packaging—and why should P1 remain open?

## Continuous integration

The GitHub Actions `test` workflow is intended to run two independent Linux jobs:
Python 3.11 and Python 3.12. Each runs the full regression suite followed by the
isolated wheel-install verification. The workflow never deploys or publishes Chimera.

The repository grants only read access. Checkout credentials are not retained, jobs
time out after ten minutes, and newer work on the same branch cancels obsolete work.
Official checkout and Python-setup actions are pinned to exact commits rather than
floating tags. The preparation step downloads setuptools/wheel from the package
index; CI therefore still depends on GitHub runners, those action commits and PyPI.

A workflow file in the repository is only a test plan. A CI claim requires an actual
completed run for the relevant commit, both matrix jobs green, and inspected logs
showing the regression and clean-install steps executed.

First verified hosted evidence: [run 34744334003](https://github.com/lvlunario/project-chimera/actions/runs/34744334003)
on development commit `35f3558d`, September 13, 2026. Python 3.11 and 3.12 jobs both
completed successfully; inspected logs show 31 tests and the clean-install proof in
each. Treat later commits as unverified until their own required checks complete.

Latest CLI integration evidence: [run 34753672209](https://github.com/lvlunario/project-chimera/actions/runs/34753672209)
on development head `1ea07c7e`. Both jobs passed 49 tests and installed CLI/evidence
verification. The earlier failed mode-publication run is recorded in the daily log.

### Teaching note for Leo

The matrix checks compatibility, not just repetition: identical code runs under two
Python interpreters on fresh machines. A local pass on 3.12 cannot prove 3.11 works.
Pinning Actions makes the automation code reviewable; it does not eliminate the need
to review and periodically update those dependencies.

## Declarative workflow CLI

After installation, run the bounded synthetic example from a trusted checkout:

```bash
chimera run examples/workflow.json --evidence run.json
echo $?
```

The example prints health/ingest as succeeded, link-check as failed and report as
blocked. It exits 1 and still creates `run.json`; inspect that file with the evidence
API described above. Choose a new output name for every run because Chimera refuses
to replace an existing file.

Workflow schema version 1 contains exactly `schema_version` and `tasks`. Every task
has an `id`, `operation`, optional `dependencies`, and one operation-specific field:

```json
{
  "schema_version": 1,
  "tasks": [
    {"id": "ingest", "operation": "emit", "value": {"source": "synthetic"}},
    {"id": "check", "operation": "fail", "message": "synthetic threshold miss", "dependencies": ["ingest"]}
  ]
}
```

`emit` returns its finite JSON `value`. `fail` records its nonempty `message` as an
expected task failure. No field can import code, invoke a shell, contact a URL or name
an arbitrary callable. Input must be UTF-8 and at most one MiB, with at most 1,000
tasks and 1,000 dependencies per task. IDs use letters, digits, dot, underscore or
hyphen, start alphanumerically, and are at most 128 characters. Duplicate keys/IDs/
dependencies, unknown fields/operations, malformed graphs and non-finite numbers fail
before a completed record is written.

Exit codes:

- 0: completed and every task succeeded.
- 1: completed with at least one failed or blocked task; evidence was written.
- 2: invalid workflow, invalid dependency graph or command usage; no run evidence.
- 3: evidence output exists or cannot be created.

These codes distinguish “the verification ran and found trouble” from “the procedure
could not be established.” Current operations are synthetic and side-effect-free.
Future measured-data and fault-injection adapters require their own schemas and safety
review. The one-MiB limit reduces accidental resource use but is not hostile-input
sandboxing. The evidence write is exclusive, not crash-safe or a P2 durable journal.

### Teaching note for Leo

A workflow file is treated as data, never as a program. This keeps review simple:
operators can see the complete set of allowed effects from the schema. Exit 1 still
produces evidence because a failed check is a valid, important test outcome; exit 2
means Chimera could not safely start that test at all.

Exercise: explain why a missing dependency should produce exit 2 with no evidence,
while a deliberate `fail` task should produce exit 1 and a preserved record.

## Durable storage and interrupted-run inspection

The [P2 contract](STORAGE.md) defines atomic run/binding storage, per-task journaling,
conservative recovery and negative tests ([issue #12](https://github.com/lvlunario/project-chimera/issues/12)).
Completed artifact storage, the separate per-task journal and bounded pending-only resume
are implemented. Existing P1 CLI/API behavior is unchanged. Task-transition and final-run
commit reconciliation are implemented. Completed journals can now be exported into
existing schema-v1 evidence; communications
CSV integration and the full P2 approval packet remain planned.

After an interruption, a running task has an uncertain outcome; missing evidence is
not proof the action never happened. Recovery defaults to attention rather than automatic
repetition. On Linux, run:

```bash
python -m examples.journal_demo
```

Expected output reports one performed effect, a `needs_attention` run, a `running`
(unknown-outcome) task and zero recovery callback invocations. The temporary database
and effect marker are removed. The fixture deliberately kills a child process; it does
not kill the demo or contact hardware/network services.

Developer API: construct `JournalTask(id, action, operation_id, dependencies)`, then call
`run_journaled(path, tasks)`. `operation_id` is required provenance supplied by trusted
code; it is not an authenticated code hash. Use `JournalPlan.from_tasks` and
`inspect_interrupted(path, run_id, plan)` to inspect only. Inspection accepts no callbacks.

### Pending-only restart exercise

On Linux, run:

```bash
python -m examples.resume_demo
```

The synthetic child process dies after committing the first task's successful result but
before starting the second. A new process preserves the first result, invokes only the
pending second task and completes the same run. The demo uses a private test-only fault
injection point to make the crash boundary deterministic; no hardware/network is contacted.

Use `resume_journaled(path, run_id, tasks)` with the identical task IDs, dependencies and
operation IDs. The function holds exclusive ownership, revalidates all durable content and
never calls terminal tasks. It returns an already completed run without callbacks. If any
task is `running`, resume refuses the entire run and persists `needs_attention`; it does
not run otherwise independent pending tasks. The caller must investigate/reconcile that
unknown effect rather than relabel or repeat it.

Teaching exercise: compare two crashes. If task A is durably succeeded and task B is
pending, B may resume. If A is running, neither A nor B may execute. Explain why B's
independence cannot make A's unknown external effect safe to ignore.

Teaching note for Leo: Chimera writes “this task started” before allowing the effect.
If the process dies afterward, it refuses to infer whether the effect finished. That is
less convenient than retrying, but avoids silently performing an action twice. Pending-only
resume is now implemented; unknown running work remains deliberately non-resumable.

### Ambiguous commit exercise

On Linux, run:

```bash
python -m examples.commit_recovery_demo
```

The synthetic connection reports an error after the first task's terminal COMMIT. Chimera
discards that connection, reopens the existing database under the same owner, validates the
whole journal and continues only because the exact state and canonical result match. Expected
output reports one `measure` callback, one `report` callback and a completed run.

If reopen instead finds `running` after the callback returned, Chimera records
`needs_attention`, stops later work and raises `JournalCommitUncertain`. If the database
cannot be reopened and validated, it raises `JournalStorageUnavailable` without claiming
that attention was saved. This is local synthetic fault injection, not power-loss evidence.

Teaching note for Leo: an error message cannot tell us which side of COMMIT occurred. The
durable row can. Comparing the entire intended record lets Chimera accept a commit that did
happen without ever repeating the engineering action that produced it.

### Completed journal evidence handoff

On Linux, run:

```bash
python -m examples.journal_export_demo
```

The demonstration runs one synthetic link-margin check, exports the completed journal as
schema-v1 `RunEvidence`, saves/reopens it through `EvidenceStore`, and evaluates its
requirement verdict. Expected output shows the same run ID, a failed requirement, and
exactly one callback invocation even though the evidence is reopened and assessed.

Developer API: call `export_journal_evidence(path, run_id, plan)` with the exact
`JournalPlan`. Export opens only an existing journal, validates all rows in one read
transaction, and refuses running, needs-attention, commit-conflicted, wrong-plan or corrupt
runs. It never accepts callbacks. Missing paths remain missing rather than being initialized.

Teaching note for Leo: a journal is the execution record; schema-v1 evidence is the portable
handoff. Chimera copies only a fully completed, internally consistent run. The current
handoff does not atomically join the two databases, and schema v1 does not preserve the
operation IDs or plan digest after conversion—those provenance fields require a future
versioned evidence contract rather than a silent format change.

## Phase approval instructions

Use the [phase approval guide](APPROVALS.md) for P0–P7 verification and validation checklists,
required evidence, walkthroughs, expected results and decision records.
Each phase packet must include these checks and candidate-specific runnable instructions.
Engineering verification and Leo's acceptance are tracked separately; no phase is
accepted from silence or from a test count alone.
