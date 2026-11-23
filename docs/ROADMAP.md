# Prototype delivery baseline — September 12 to December 12, 2026

All dates use Asia/Manila. Target dates are a managed baseline, not a guarantee.
Baseline version 1: September 12. September 22 update: P0 is approved by explicit
delegation; P1/P2 are conditionally accepted for continued development under the
[decision record](reviews/2026-09-22-delegated-decisions.md). Personal walkthroughs
remain unperformed. Original dates below are unchanged; M0's scope decision was recorded
September 22, three days after its September 19 target. Downstream forecasts
remain October 3/17, November 7/28 and December 12 with no baseline movement.

## Status update — November 23, 2026

The October 17 M2 baseline was missed by thirty-seven days. M3 November 7 is **missed and red,
sixteen days late**. The engineering vertical, acceptance-preparation workspace, read-only
dashboard and evidence controls are implemented and verified, but no Leo walkthrough,
manual-device/screen-reader observation or separate P3/P4/P5 disposition is recorded. This is
a schedule slip, not a change to the original baseline. Recovery remains: freeze feature scope,
run the existing worksheet, record actual observations, disposition defects and phases, and
continue reversible release preparation without treating silence as approval.

The November 22 connected open-issue listing returned four open `Defect:` issues: #4, #14,
#25 and #28. Connected issue/comment inspection confirmed all four remain fixed/verified on the
still-open development PR and none is currently declared a release blocker. The program-head
manifest carries the `2026-11-22T10:22:42Z` offline snapshot. Exact tested candidate `b6b6878`
truthfully retains the preceding November 18 four-defect snapshot in its v4 nomination/archive;
that retained evidence was not edited. Historical nominee
`9edce78`, its archive and its embedded three-defect November 9 snapshot remain unchanged.
This engineering supersession is not an M4 decision.

P7 release preparation retains historical exact candidate
[`04606a4`](https://github.com/lvlunario/project-chimera/commit/04606a4b87c270fdce37fd3673ec18c74af82a54)
as its first engineering nomination for M4 review. Its push and PR-integration matrices passed Python 3.11,
Python 3.12, exact rehearsal/reinspection, clean-wheel verification and Chromium. A fresh
outside-checkout rehearsal regenerated the operator, performance, threat and 133-requirement
readiness records plus the bounded M4 packet. The retained nomination record binds its exact
receipt/packet identities, dated defect snapshot, connected run IDs and generated PR merge
commit. It deliberately retains D-004–006, P3/P4/P5, M4/M5 and human acceptance as pending.

The readiness snapshot contained three open fixed/verified defects and zero declared release
blockers; it was 88,344 seconds old when nominated. A connected query at
`2026-11-10T10:58:04Z` returned the same open defects #4, #14 and #25. This confirms inventory
continuity but does not create trusted time or waive the required refresh at M4 disposition.
The failed predecessor `b3920b4` is retained as evidence: both hosted matrices stopped on an
over-specific Python 3.11 test assertion, while the product control still failed closed.
Superseding `04606a4` corrected the cross-version assertion and passed both matrices. On
November 12, issue #28 then exposed a candidate-bound mismatch between string packet blockers
and integer-only rehearsal receipt validation. The control failed closed, but a coherent blocked
directory could not be retained. Corrected candidate `594b03c` added the bounded contract and
deterministic negative-path regression, passed both hosted matrices, completed a clean detached
rehearsal/reinspection, and is separately retained in the v2 superseding nomination.

November 14 stabilization adds a deterministic local archive and portable inspector for one
validated rehearsal. The archive retains the exact receipt-indexed bytes and fail-closed status
without turning CI into storage: Actions builds and inspects it in runner-temporary space but
does not upload or retain it. This cannot recover the already-lost v2 rehearsal. At that point
candidate `594b03c` remained the last nominee; the archive-changing branch head needed a
separately retained rehearsal/archive, matching hosted matrices and a separate v3 nomination
before it can replace that record.

The November 15 correction addressed one portability defect exposed by November 14 hosted
integration. A GitHub Linux runner reused the removed archive inode for an adversarial FIFO
replacement, so identity-only cleanup could remove the unrelated entry. The corrected publisher
holds the original file descriptor through final validation and permits cleanup only for the
same regular file. Both corrected hosted matrices are green across Python 3.11, Python 3.12 and
Chromium. This closed the engineering portability defect without changing the candidate rule;
at that point `594b03c` remained the last nominee and no gate or human decision was inferred.

On November 16, the program regenerated the full rehearsal from exact clean candidate
`9edce78f8fc2b2033eefe78421c475a8cbc62ce0`, whose push and PR-integration matrices had
already passed Python 3.11, Python 3.12, clean install, archive controls and Chromium. The
rehearsal and deterministic archive reinspected as complete with no declared release blocker.
The repository now retains the 767,529-byte archive (SHA-256 `638bbb07…c2cc`) and a separate
v3 nomination that binds the same candidate, connected hosted runs, receipt and packet.
Branch regression portably reinspects that archive and keeps P3/P4/P5, M4/M5 and human
acceptance pending. This supersedes v2 as engineering evidence; it is not M4 permission.

November 17 stabilization exposes the branch-only archive/nomination cross-check as a
read-only portable command. It validates the retained archive first, then requires v3's
candidate, receipt/packet and complete rehearsal identities, dated defect snapshot/age,
hosted-CI evidence and pending authority to agree without the source rehearsal directory.
This improves inspection of the existing nominee; it neither refreshes the dated connected
defect snapshot nor selects a new candidate or grants M4.

On November 19, exact candidate `b6b6878` was regenerated after both hosted matrices passed
Python 3.11, Python 3.12, clean install, rehearsal/archive controls and Chromium. Its fresh
detached rehearsal and deterministic 774,686-byte archive reinspected as complete with no
declared release blocker. A separate v4 nomination binds the candidate, connected run IDs,
generated PR merge commit, receipt `d3ebb94…e80fd`, packet `28618c4…c1f3b`, archive SHA-256
`9122615…1646` and dated four-defect snapshot. v1–v3 remain immutable; no gate or human
authority changed.

November 20 stabilization adds one read-only `inspect-retained` preflight across the retained
v3/v4 archive pairs. It validates both complete pairs, rejects duplicate candidates, skipped
versions or nonchronological nominations, and identifies v4 only after every check succeeds.
This resolves stale-binder selection risk without changing either archive, nominating the later
program head, refreshing defects or deciding M4.

November 21 stabilization replaces both official CI dependencies with reviewed full-SHA
Node-24-native releases and regression-locks the exact patch tags in both Python/browser jobs.
Fresh push and PR-integration matrices passed Python 3.11, Python 3.12, retained-lineage,
clean-install and Chromium controls without the previous Node 20 forced-runtime warning. This
removes a branch-maintenance risk; it does not alter the retained v4 nominee or create a gate
decision.

November 22 program-head reconciliation refreshes the dated connected defect inventory while
preserving the four issue records, their fixed/verified-pending-integration dispositions and zero
declared release blockers. It deliberately does not rewrite v4, establish trusted time, close
issue #23 or grant M4. Refresh the connected listing again at actual M4 disposition.

November 23 engineering preflight independently repeated the exact `b6b6878` regression,
optimized regression, isolated-wheel install, full rehearsal and portable-archive inspection
from a clean detached checkout. Connected inspection reconfirmed both candidate matrices and
the same four fixed/verified open `Defect:` issues. The ephemeral regenerated binder was deleted;
retained v4 stayed immutable. This lowers setup-drift risk but does not perform the operator
walkthrough, refresh the canonical manifest, disposition P3/P4/P5 or decide M4.

M4 November 28 is five days away and M5 December 12 is nineteen days away. Both remain amber with
the current nominee's local, portable and
hosted evidence retained, provided feature scope stays frozen and November 29–December 12
remains reserved for stabilization and acceptance. Candidate-bound changes require a new
candidate rehearsal, hosted evidence, retained archive and superseding nomination. Automation
still cannot substitute for human acceptance.
All four retained nomination records are pinned by branch regression that validates canonical
bytes, hosted-CI content identity, receipt/packet hashes and pending authority. The v3 and
current v4 controls also portably reinspect their separately retained deterministic archives,
and the combined operator command checks each pair. This is an integrity guard, not a human
gate decision.

## Operational problem and proposed scope
An integration engineer needs to verify a communications test run, identify failing
requirements, and hand another engineer reproducible evidence rather than screenshots.

Prototype demonstration:
1. Import a timestamped link-margin CSV using a documented schema and units.
2. Select requirements and run checks; view pass, fail, blocked and missing-evidence states.
3. Save and reopen the run, inspect the failing samples, and export a traceable report.
4. Repeat with a passing fixture and a malformed input; show correct outcomes for each.

Use synthetic fixtures first. The file adapter must also accept user-supplied measured
data conforming to the schema. Real-data validation remains pending until a suitable,
authorized dataset exists; no claims of hardware validation based on synthetic runs.
No live radio control, distributed worker fleet, enterprise tenancy or certification
in the three-month prototype. AI summaries are optional and cannot change verdicts.

## Milestones and acceptance
| Gate | Deadline | Engineering deliverable | Leo's participation |
|---|---|---|---|
| M0 / P0 | Sep 19 | Target user, three use cases, demo script, exclusions and risks documented | Review concept and adjust priorities |
| M1 / P1 | Oct 3 | Versioned evidence, CLI, installable package, CI; requirements/interface baseline | Explain workflow/failure semantics; review evidence |
| M2 / P2–P3 | Oct 17 | Vertical slice: CSV to check to persisted/reopened result; restart behavior tested | Observe pass/fail demo; challenge assumptions |
| M3 / P3–P5 | Nov 7 | Prototype features complete: telemetry validation, requirement mapping, reports and basic operator dashboard | Try operator journey and record defects |
| M4 / P7 | Nov 28 | Release candidate: clean install, integrated regression, critical requirements verified | Review readiness, limitations and acceptance script |
| M5 / P7 | Dec 12 | Tagged prototype, operator/developer manuals, evidence bundle and demonstrated acceptance | Run or observe acceptance and record disposition |

Nov 29–Dec 12 is reserved for defect correction, documentation, and acceptance.
New features in that interval need a stated impact and Leo's decision.
P6 AI assistance starts only when critical prototype work is on track; it is not
a release gate. Phase overlap allows documentation/UI design during core work,
but dependent integrations use agreed interfaces.

## Tracking rules
Each work issue includes requirement IDs, deliverable, role owner, target date,
dependencies and verification method. Track engineering state separately from
PM acceptance: planned / in progress / implemented / verified / reviewed / accepted.
Only evidence moves engineering state; acceptance requires Leo's actual response or an
evidence-backed decision within his explicit delegation. Silence is never acceptance.
The September 22 delegation does not waive tests, validation conditions or final acceptance.

Report green when the next gate is achievable with current evidence and known work;
amber when an unresolved dependency or scope threatens it; red when forecast exceeds
the gate date or a release blocker prevents it. Show original deadline, forecast,
cause and recovery options. Do not move the baseline date silently.

## Phase approval instructions

Use the [phase approval guide](APPROVALS.md) for P0–P7 verification and validation checklists,
required evidence, walkthroughs, expected results and decision records.
Each phase packet must include these checks and candidate-specific runnable instructions.
Engineering verification and Leo's acceptance are tracked separately; no phase is
accepted from silence or from a test count alone.
