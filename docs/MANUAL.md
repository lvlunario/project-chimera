# Chimera project manual

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
with blocked status. Requirement verdicts and error categories will be separate work.

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
