# M4 retained-binder packet materialization — November 24, 2026

Status: completed AI-assisted P7 handoff stabilization tracked in
[issue #35](https://github.com/lvlunario/project-chimera/issues/35). This is not a new M4
candidate, a human walkthrough, a P3/P4/P5 disposition, M4 permission, M5 acceptance, merge,
tag, release or deployment.

Review target: exact retained engineering candidate
[`b6b6878a3c4fdc700683508a19b5a5bc2e178671`](https://github.com/lvlunario/project-chimera/commit/b6b6878a3c4fdc700683508a19b5a5bc2e178671)
and its immutable v4 nomination/archive pair. Starting development-branch head:
[`ed754f929e0dfe1990d79179a48c88cd9bff4267`](https://github.com/lvlunario/project-chimera/commit/ed754f929e0dfe1990d79179a48c88cd9bff4267).

## Outcome and engineering decision

The retained rehearsal archive already failed closed during portable inspection, but the next
operator step required manually obtaining its embedded M4 packet before using the packet's safe
extractor. The new optional `inspect --extract-packet-to NEW_DIRECTORY` path closes that handoff
gap without exposing general outer-archive extraction.

The command now validates the complete outer deterministic archive and rehearsal first, stages
only the receipt-indexed packet in a private temporary directory, independently reinspects that
packet, cross-checks candidate, blockers and pending authority, then delegates persistent output
to the packet's existing outside-checkout, new-directory, no-overwrite extractor. It never calls
`ZipFile.extract`. Existing paths, symlinks, malformed outer bytes and inside-checkout targets
fail closed. A coherent blocked packet remains materializable for investigation but returns 1.

This is implemented only on the later program head. It does not change the retained archive,
nomination or exact candidate, and therefore does not silently create v5. REHEARSAL-006 records
the bounded control; the current program-head readiness inventory now covers 139/139 requirements
across the same 23 groups while v4 truthfully retains its historical 136/136 inventory.

## Connected reconciliation

Connected inspection found draft [PR #1](https://github.com/lvlunario/project-chimera/pull/1)
open, unmerged and mergeable at the starting head. A fresh connected open-issue listing at
`2026-11-24T10:31:42Z` again returned exactly four `Defect:` issues:
[#4](https://github.com/lvlunario/project-chimera/issues/4),
[#14](https://github.com/lvlunario/project-chimera/issues/14),
[#25](https://github.com/lvlunario/project-chimera/issues/25) and
[#28](https://github.com/lvlunario/project-chimera/issues/28). Their records retain
fixed/verified-pending-integration dispositions and no declared release blocker. This connected
observation does not rewrite the November 22 program manifest or the candidate's November 18
snapshot, establish trusted time or waive the required refresh at actual M4 disposition.

## Actual verification

Final local results on the implementation tree:

- focused archive tests: 6/6 in normal Python and 6/6 under `python -O`;
- full regression: 354/354 in 12.613 seconds;
- optimized full regression: 354/354 in 12.287 seconds;
- isolated wheel build/install and installed API, evidence, storage, journal, telemetry, report,
  operator, dashboard and handoff checks passed;
- `compileall` and `git diff --check` passed; and
- the retained v4 archive materialized through the new command with unchanged archive
  `9122615ca805bd735a2ae54a96412daebd4d642459f050763c5a5bf0798e1646`, receipt
  `d3ebb942a33e74d19f57e9101173040b7eece25ec54c98a322c984a0743e80fd` and packet
  `28618c40e5ad432c2b0301c8a5d3d8ec412734f2075756dc1fc81d0d1efc1f3b` identities.

The materialized packet still names candidate `b6b6878`, reports
`packet_complete_for_m4_review`, retains M4/M5 `pending` and human acceptance `not_granted`, and
contains an unchecked **NOT PERFORMED** acceptance script. Its synthetic-failure handoff
reinspected as COM-LINK-001 FAIL. The extracted three-run workspace served through the real
loopback dashboard/API and returned PASS/FAIL plus synthetic coverage.

The first full-suite attempt truthfully failed two readiness-test assertions that still expected
138 requirements after REHEARSAL-006 made the correct count 139. The manifest already covered the
new requirement; the stale test expectations were corrected, then both complete suites passed.
During the manual dashboard rehearsal, an ad hoc probe first used the nonexistent `/api/runs`
path and received 404; the documented `/api/v1/runs` route then passed. Neither was a product
failure or passing evidence, and neither changed retained artifacts.

## Independent AI QA

Independent integration QA made no edits and passed 38/38 focused archive/packet/rehearsal tests
normally and 38/38 optimized. It materialized 46 files from retained v4, independently checked
candidate/status/pending authority and blank script, reinspected the failure handoff, served the
three-run dashboard workspace, and revalidated retained lineage selecting v4.

Independent adversarial QA made no edits and passed 51/51 related release controls normally and
51/51 optimized. It verified existing-output, symlink and inside-checkout refusal; retained user
data; confirmed invalid outer bytes create no output; and confirmed blocked materialization keeps
blocked exit status. It found one minor truthful-interface issue: the footer still said
“inspection only” after materialization. The footer and its regression were corrected; re-review
passed with no remaining blocker, major or minor finding. These are engineering reviews, not Leo
acceptance.

## Gate status, risks and next action

P0 remains approved by delegation. P1/P2 remain conditionally accepted for continued
development. P3/P4/P5/P7, D-004–006, operator/manual-device/screen-reader observations, M4/M5 and
final product acceptance remain pending. M2 is thirty-eight days late; M3 is seventeen days late
and red. M4 November 28 is four calendar days away and M5 December 12 is eighteen days away. Both
remain amber if feature scope stays frozen and November 29–December 12 remains reserved for
stabilization and acceptance.

No engineering release blocker is declared. Hashes detect disagreement but do not authenticate
a producer. Synthetic/local evidence does not prove physical-radio behavior, production
capacity, security certification or usability. The next task is to use the materialized retained
packet for the existing worksheet, record only actual Leo observations and separate P3/P4/P5/M4
dispositions, and requery connected defects at disposition. No new routine scope decision is
requested.

Teaching note for Leo: the outer ZIP is the sealed shipping carton; the embedded packet is the
review binder. This change lets the project verify the carton, remove the binder through a
controlled path, and verify the binder again before you use it. It reduces handoff mistakes but
cannot decide whether the workflow is understandable or acceptable—that remains your recorded
review decision.
