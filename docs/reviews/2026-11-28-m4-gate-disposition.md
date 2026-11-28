# M4 gate disposition — November 28, 2026

## Decision

**Engineering disposition: ready for M4 review.**

**Program gate status at `2026-11-28T10:06:42Z` (18:06 Asia/Manila): M4 not achieved/pending.**

The baseline is date-only and November 28 is still in progress at this checkpoint. If the
required validation remains absent at day close, M4 will be recorded missed/pending on the next
program reconciliation.

This is not a technical rejection and not an inferred sponsor decision. The exact retained
candidate has complete engineering review inputs and no declared release-control blocker, but
the gate requires actual operator observations, residual-risk review, D-004–006, separate
P3/P4/P5 dispositions and an explicit M4 response. Those records do not exist. Passing CI and
AI review cannot substitute for them.

The November 28 baseline remains unchanged. PR #1 stays draft, open and unmerged. No tag,
release, deployment, v5 nomination or M5/final-acceptance authority is created.

## Evidence at the gate

Review target remains exact candidate
[`b6b6878a3c4fdc700683508a19b5a5bc2e178671`](https://github.com/lvlunario/project-chimera/commit/b6b6878a3c4fdc700683508a19b5a5bc2e178671),
not moving program head `0399c4b`.

- The exact [v4 nomination](../m4-candidate-nomination-v4.json) binds candidate
  [push 44291039769](https://github.com/lvlunario/project-chimera/actions/runs/44291039769)
  and [PR integration 44291051452](https://github.com/lvlunario/project-chimera/actions/runs/44291051452),
  which remain successful.
- Retained v4 archive SHA-256: `9122615…1646`.
- Receipt SHA-256: `d3ebb942…e80fd`; packet SHA-256: `28618c40…c1f3b`.
- Fresh lineage inspection selected v4 and preserved P3/P4/P5, M4/M5 and human acceptance as
  pending.
- Fresh packet materialization reported `packet_complete_for_m4_review`, exact candidate v4,
  no checked acceptance item and `M4 decision: pending`.
- Gate-day current-head verification passed 356/356 tests normally in 11.974 seconds and
  356/356 optimized in 12.107 seconds, clean isolated-wheel installation, compilation and
  diff checks.
- Final-head [push 45984903204](https://github.com/lvlunario/project-chimera/actions/runs/45984903204)
  and [PR integration 45984912735](https://github.com/lvlunario/project-chimera/actions/runs/45984912735)
  remain green across Python 3.11/3.12 normal and optimized suites, exact rehearsal, retained
  lineage, real v4 materialization, clean install and Chromium.
- A fresh connected query returned exactly open `Defect:` issues
  [#4](https://github.com/lvlunario/project-chimera/issues/4),
  [#14](https://github.com/lvlunario/project-chimera/issues/14),
  [#25](https://github.com/lvlunario/project-chimera/issues/25) and
  [#28](https://github.com/lvlunario/project-chimera/issues/28). Each remains fixed/verified
  pending PR integration; none declares a current release blocker.

Independent architecture, product/UX, engineering, platform/release and QA/security reviews
agreed on the boundary: engineering GO/ready-to-review, program gate not achieved/pending at this
checkpoint. No reviewer made repository edits or claimed sponsor acceptance.

## Missing controlling evidence

- Leo has not performed or recorded the operator walkthrough.
- Manual desktop/device and screen-reader observations remain unperformed.
- D-004–006 and separate P3/P4/P5 decisions remain pending.
- Residual risks have not received sponsor disposition.
- No explicit M4 choice—approve, approve with conditions, request changes or defer—is recorded.

Therefore M4 cannot truthfully move to approved or approved-with-conditions. It is also not a
failed candidate: the missing evidence is validation/governance, not a demonstrated product or
release-control defect.

## Recovery and next control point

Keep feature scope frozen and use the existing
[20–30 minute assisted review](2026-11-27-m4-disposition-readiness.md) at the earliest opportunity.
Record actual observations and the sponsor's verbatim decisions; do not backdate them to the
November 28 baseline. If no critical blocker is observed, engineering recommends considering
M4 **approve with conditions** solely to enter final acceptance testing, while keeping
unperformed accessibility/device/measured-data checks explicit, P3/P4/P5 separately dispositioned,
PR #1 unmerged until authorized, and M5 pending.

November 29–December 12 remains the stabilization/acceptance window. M5 is at risk but not yet
missed. If no sponsor decision is recorded before November 28 closes, carry M4 as missed/pending
without moving the baseline. Until M4 is explicitly dispositioned, do not merge, tag, release,
deploy, close integration-held defects, rewrite v4 or claim final product acceptance.
