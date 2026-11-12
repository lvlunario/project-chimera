# Magnum Opus program

## Product and audience
Chimera helps integration and test engineers run repeatable verification workflows,
trace results to requirements, and explain failures with preserved evidence.
Start with simulated engineering systems; introduce real hardware through explicit
adapters later. The initial vertical is communications-link verification.

## Roles
Program manager: Leo (project owner) — product priorities and milestone acceptance.
Implementation: AI-assisted development — architecture, code, tests, documentation.
The 100-developer framing expresses ambition, not actual staffing or throughput.

## Delivery phases
| Phase | Deliverable | Exit criteria | State |
|---|---|---|---|
| P0 | Charter and architecture | Scope, requirements, risks, development policy recorded and reviewed with Leo | Approved by delegation September 22 |
| P1 | Local execution core | Graph validation, failure propagation, evidence schema, CLI, package install and CI verified | Conditionally accepted for continued development September 22 |
| P2 | Durable execution | SQLite run storage; restart recovery and idempotency tested | Conditionally accepted for continued development September 22; bounded recovery limitations retained |
| P3 | Engineering adapters | Synthetic telemetry ingestion and deterministic fault injection with reference fixtures | In progress; strict CSV ingestion, deterministic faults, integrated operator path and exact-candidate acceptance preparation implemented; human validation pending |
| P4 | Verification evidence | Requirement mapping, reproducible JSON/HTML reports, missing-evidence detection | In progress; canonical reports, deterministic handoff, missing-evidence control and exact-candidate preparation implemented; overdue gate disposition pending |
| P5 | Operator product | API and accessible dashboard; end-to-end acceptance tests | In progress; API/dashboard, investigation views, handoff download, first-focus bypass/contextual run names, automated Chromium controls and operator worksheet implemented; manual-device, screen-reader and operator acceptance pending |
| P6 | AI assistance | Provider adapter, bounded permissions, evaluation dataset and measured baseline comparison | Planned |
| P7 | Release | Reproducible deployment, performance results, threat model, demo and operator guide | In progress; performance, threat-model, readiness, M4 packet/rehearsal and exact-SHA engineering nomination controls implemented; historical nominee `04606a4` requires explicit supersession after issue #28; M4/M5 and human decisions pending |

Prototype delivery target: December 12, 2026 (Asia/Manila). See [dated roadmap](ROADMAP.md).
This supersedes the original undated plan. Dates are delivery targets; passing evidence and
Leo's recorded acceptance control gate closure. Report forecast slips promptly.
P6 AI assistance is a stretch goal after prototype-critical P1–P5 and P7 work.
See [manual](MANUAL.md) and [quality plan](QUALITY.md) for participation and release policy.
AI assistance cannot decide that missing evidence is a passing verification.

## Work policy
- Read current repository instructions, branch head, PR and logs before every session.
- Deliver one bounded, useful increment with appropriate tests.
- Use Conventional Commits: feat(core), fix(core), test(core), docs(program), ci(test).
- Commit only completed changes with actual timestamps. Do not fabricate activity,
  developers, test outcomes, reviews, or the owner's personal work.
- Update docs/daily/YYYY-MM-DD.md in Asia/Manila with goal, changes, verification,
  unresolved risks, and next task. Include available commit/PR references.
- Keep acceptance criteria and phase state current. Do not silently expand scope.
- Preserve user edits and history. Never force-push. Resume the development branch
  while its PR is open; once merged, create the next phase branch from current main.
- A blocked session reports the concrete blocker; empty commits are not progress.
- Avoid paid infrastructure and live hardware operations until separately authorized.

## Next tasks
Current direction, November 12: the October 17 M2 exact-candidate disposition is twenty-six
days late. M3 missed its November 7 baseline and is five days late because no Leo walkthrough,
manual-device/screen-reader observation or separate P3/P4/P5 disposition is recorded. This is
a schedule slip, not an engineering blocker and not implied acceptance. The
[November 2 weekly review](reviews/2026-11-02.md) remains the 25–30 minute runbook, but its
pinned SHA is historical. Record actual operator and accessibility observations for the
bounded dashboard tracked in [issue #19](https://github.com/lvlunario/project-chimera/issues/19)
before P5 acceptance; keep P3/P4/P5 pending.

P7's first retained engineering nominee is now historical. Exact candidate
[`04606a4`](https://github.com/lvlunario/project-chimera/commit/04606a4b87c270fdce37fd3673ec18c74af82a54)
passed the connected
[push matrix](https://github.com/lvlunario/project-chimera/actions/runs/42602816452) and
[PR-integration matrix](https://github.com/lvlunario/project-chimera/actions/runs/42602825660)
on Python 3.11, Python 3.12 and Chromium. The strict
[nomination record](m4-candidate-nomination-v1.json), tracked in
[issue #27](https://github.com/lvlunario/project-chimera/issues/27), binds those runs and the
generated PR merge commit to a freshly reinspected rehearsal, receipt and packet. Its state is
only `nominated_for_m4_review`: D-004–006, P3/P4/P5, M4/M5 and human acceptance remain pending.
An earlier candidate `b3920b4` was rejected by both hosted matrices because a Python 3.11 test
asserted one version-specific JSON error phrase; `04606a4` corrected the assertion without
weakening controlled fail-closed behavior.

On November 12, full-suite load exposed [issue #28](https://github.com/lvlunario/project-chimera/issues/28):
the packet correctly emitted a namespaced string performance blocker, but the rehearsal receipt
validator accepted only integers. The control failed closed and granted no authority, yet could
not retain the documented coherent blocked directory. Engineering corrected the contract and
added deterministic passing/failed-performance regressions. Because this changes candidate-bound
release tooling, `04606a4` remains truthful historical evidence but is no longer the current
corrected nominee. A fresh exact candidate, rehearsal, hosted matrices and separate superseding
nomination are required before M4 review.

Stabilization now directly regression-checks the retained nomination's canonical bytes,
embedded hosted-CI identity, exact receipt/packet hashes, change policy and still-pending
authority. This guard prevents an in-place evidence edit from passing branch CI; it does not
reinspect or recreate the separately sealed rehearsal and does not supersede `04606a4`.

The current readiness inventory covers 133 declared requirements across 23 groups, six guides
with 51 required headings, three open fixed/verified defect issues and zero declared release
blockers in its dated snapshot. That snapshot was 88,344 seconds old at nomination; the age is
arithmetic evidence, not trusted time or a freshness decision. A fresh connected query at
`2026-11-10T10:58:04Z` returned the same open defect issues #4, #14 and #25. Query again at M4
disposition. Performance, threat-model, readiness, bounded packet and one-command rehearsal
controls remain synthetic/local-prototype evidence; they do not prove physical-radio behavior,
producer identity, security certification or operator acceptance.

M4 November 28 and M5 December 12 remain amber but the M4 forecast is at risk until the
replacement candidate passes local and hosted gates. Recovery keeps feature scope frozen and
November 29–December 12 reserved for stabilization and acceptance. Next: publish and nominate
the corrected exact candidate, support the existing worksheet, record Leo's actual observations and separate
phase decisions, correct any critical defect, refresh live defects at disposition, and then
record M4 explicitly. Do not replace the nominee silently; the corrected candidate requires a
new superseding nomination record.
The deterministic P4 handoff work is tracked in
[issue #20](https://github.com/lvlunario/project-chimera/issues/20).
[Delegated decisions](reviews/2026-09-22-delegated-decisions.md)
supersede historical pending-P0/P1/P2 statements below. Personal walkthroughs are unperformed;
final acceptance remains separate. Do not reopen P0/P1/P2; new P5 interface recommendations
are in the [September 28 weekly review](reviews/2026-09-28.md).

Historical implementation sequence:
1. Completed-run evidence, boolean-check verdict classification and versioned requirement
   bindings are implemented. The communications vertical now also binds input/configuration
   provenance and durable artifacts; generalized authenticated provenance remains outside
   the prototype boundary.
2. Packaging and Python 3.11/3.12 CI are implemented and verified on the development
   branch; retain their evidence for P1 integration and final gate review.
3. Strict declarative CLI workflow input is implemented, independently reviewed and
   verified on the published Python 3.11/3.12 CI head; retain its gate evidence.
4. September 15: the requirement-binding interface is versioned and serializable separately
   from schema-v1 run evidence (issue #10). The consolidated [P1 packet](reviews/2026-09-15-p1.md)
   and executable review controls are prepared (issue #11); inspect their candidate CI
   and obtain Leo's actual verification/validation disposition before gate closure.
5. Add durable run storage before concurrency/retries; close P1 only after all exit
   criteria pass.
6. September 15: [P2 storage/restart contract](STORAGE.md) and
   [issue #12](https://github.com/lvlunario/project-chimera/issues/12) define planned
   atomic artifacts, journaling and conservative recovery. Next implementation:
   completed-run/binding SQLite repository is implemented September 16 with
   rollback/conflict/reopen tests. A separate, lifetime-owned per-task journal and
   inspect-only recovery are implemented September 19. September 20 adds explicit
   pending-only resume while refusing every unknown running task. Creation, task
   transition, finish, inspection and resume-claim reconciliation is implemented
   September 20. Completed-journal schema-v1 export is also implemented. September 21
   adds strict communications CSV identity/ingestion and a durable failed-verdict path,
   followed by versioned failing-sample JSON reports and passing/malformed reference
   controls. The combined P2 executable walkthrough and approval packet are prepared
   September 22; exact-candidate verification and Leo's response remain before gate
   closure. September 22 adds deterministic sample-replacement fault plans; September 23
   adds canonical reopened-evidence JSON plus self-contained HTML presentation. September 27
   adds the integrated `verify-link` local operator entry point with conservative resume
   and a read-only, loopback-only API that cross-validates completed artifacts before
   presentation. September 28 adds the bounded multi-run dashboard and loopback HTTP
   acceptance controls; September 29 adds a deterministic ZIP handoff whose manifest and
   enclosed artifacts are independently revalidated. Browser/operator and phase-gate
   evidence remain P3/P4/P5 work. September 30 adds counted keyboard investigation views
   as presentation-only projections without changing the canonical API snapshot.
   These slices do not close P2, P3, P4 or P5.
7. September 16: Linux local-file lifetime ownership primitive implemented as a
   bounded prerequisite for RECOVER-005. September 19 runner integration holds this
   guard from plan creation through callbacks and terminal commits; September 20 resume,
   reconciliation and export paths use the same boundary. No recovery gate closes from
   these bounded slices alone.

## Risks
Trusted task functions execute in-process and can hang, mutate state or access the host.
The prototype is not a sandbox. There is no timeout, cancellation, general adapter retry,
concurrency, production web service or production isolation yet. A local read-only dashboard
exists. Bounded resume applies only to tasks
durably proven pending; running/unknown work is never retried. Synthetic demonstrations
must remain labeled synthetic; they do not establish physical-system performance.

## Phase approval instructions

Use the [phase approval guide](APPROVALS.md) for P0–P7 verification and validation checklists,
required evidence, walkthroughs, expected results and decision records.
Each phase packet must include these checks and candidate-specific runnable instructions.
Engineering verification and Leo's acceptance are tracked separately; no phase is
accepted from silence or from a test count alone.
