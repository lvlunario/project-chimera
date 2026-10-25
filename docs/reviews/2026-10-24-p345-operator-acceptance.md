# P3/P4/P5 operator acceptance packet — October 24, 2026

Status: asynchronous acceptance preparation; not a completed meeting, human walkthrough or
phase approval. P0 remains approved by delegation and P1/P2 remain conditionally accepted
for continued development. P3/P4/P5 and final product acceptance remain open.

Exact engineering candidate:
[`932062a`](https://github.com/lvlunario/project-chimera/commit/932062a1580cd2d9930c7b264cc87cae74873789).
Use only that full commit for this exercise. The packet command refuses a dirty checkout or a
different `HEAD`.

## Outcome and timebox (25–30 minutes)

This packet prepares one persistent synthetic workspace for the overdue P3/P4 disposition
and November 7 P5 review. It preserves three completed runs, refused invalid inputs, explicit
missing-evidence output, resume identities, repeat handoffs and an unchecked human worksheet.

Suggested timebox: 3 minutes for scope, 5 minutes to prepare the workspace, 10 minutes for
the keyboard/dashboard/report/handoff journey, 5 minutes for malformed and missing evidence,
and 2–7 minutes for actual observations and a decision. Running the packet later does not
pause reversible defect/documentation work.

## Prepare the exact candidate

Use a fresh checkout or remove all tracked/untracked changes first. The output must not exist
and must be outside the repository.

```bash
git switch --detach 932062a1580cd2d9930c7b264cc87cae74873789
python -m examples.operator_acceptance_prep \
  --candidate-commit 932062a1580cd2d9930c7b264cc87cae74873789 \
  --output /tmp/chimera-p345-932062a
```

Expected: eight lines beginning `PASS P345-1` through `PASS P345-8`, followed by the exact
candidate, preparation-record path and observation-worksheet path. The final line must say
that human observations and P3/P4/P5 acceptance remain pending.

Do not use a directory containing `.PUBLISHING`; it records an exceptional incomplete
filesystem publication. The tool never replaces an existing path.

## Engineering coverage

| Control | Expected prepared evidence |
|---|---|
| P345-1 | synthetic reference produces durable COM-LINK-001 PASS |
| P345-2 | natural sample 2 measures 2.0 dB, below the 3.0 dB threshold |
| P345-3 | explicit synthetic fault retains source/plan/derived identity and matches the natural engineering failure |
| P345-4 | malformed value, missing column and invalid unit each raise bounded input errors and create no run state |
| P345-5 | missing evidence remains `not_evaluated` with engineering detail `unavailable` |
| P345-6 | completed resume preserves SHA-256 for all five portable artifacts |
| P345-7 | two file handoffs are byte-identical, independently inspectable and agree on run/requirement/FAIL |
| P345-8 | dashboard download headers and bytes match the file export and reopen identically |

`acceptance-preparation.json` is canonical machine-readable preparation evidence. It indexes
the retained invalid inputs, run artifacts, missing-evidence reports, handoffs and blank
worksheet with relative paths, byte counts and SHA-256. Separate preparations intentionally
have new run IDs/timestamps. Git/content hashes identify bytes; they are not signatures,
trusted build attestation, execution authorship or measurement authenticity.

## Phase-checklist crosswalk

This packet is the exact-candidate companion to the current
[phase approval guide](../APPROVALS.md), not a replacement for its P3/P4/P5 checklists. The
25–30 minute journey below does not by itself close any phase. Complete and record both the
applicable guide items and the generated worksheet before a disposition.

| Phase | Prepared/automated evidence | Human evidence still required |
|---|---|---|
| P3 — data and faults | strict PASS/natural-FAIL/synthetic-FAIL imports; source and fault-plan identity; three malformed refusals; independently asserted 2.0 dB sample against 3.0 dB | inspect the supplied CSV and fault plan, compare the selected source/result/threshold, judge whether import and diagnosis match the intended engineering task, and record the synthetic/measured-data limitation |
| P4 — requirements and reports | COM-LINK-001 binding; canonical JSON/HTML; explicit missing evidence; immutable resume; repeatable inspectable handoff | trace one failure across input identity, requirement, sample, JSON, HTML and handoff, then explain the failure and next investigation step without developer reconstruction |
| P5 — operator product | validated read-only list/detail/report/evidence/handoff paths; native keyboard and 390-pixel Chromium controls; restrictive headers | perform the same-computer keyboard/usability journey, record actual desktop-browser, physical-device and screen-reader/WCAG observations, and disposition any defects |

The current P5 prototype deliberately separates CLI orchestration from the local read-only
dashboard. The preparation command creates the candidate runs; the dashboard investigates
sealed results and cannot start or modify a run. This follows the bounded D-005 recommendation
in the [September 28 review](2026-09-28.md). Leo's response to D-004–006 remains unrecorded;
if live dashboard control is required, record it as a scope/security/schedule change rather
than marking this read-only candidate accepted.

## Human operator journey

Read `/tmp/chimera-p345-932062a/operator-observations.md`; it is generated with every box
unchecked and every phase decision pending. Then, from the same exact checkout:

```bash
python -m chimera.cli serve-dashboard \
  /tmp/chimera-p345-932062a/runs --port 8765
```

On the same computer, open `http://127.0.0.1:8765/` and follow the worksheet using Tab,
Shift+Tab and Enter. Inspect FAIL, the synthetic run, its 2.0 dB sample, return navigation,
the downloaded handoff, PASS and natural FAIL. In another terminal, inspect the download
from this exact checkout:

```bash
python -m chimera.cli inspect-link DOWNLOADED_ZIP
```

The server intentionally binds only to loopback, so a separate phone/tablet cannot reach it
without an unapproved network-boundary change. A physical-device observation requires the
browser to run on that same supported device. Screen-reader evidence requires an actual
combination such as NVDA/Windows or VoiceOver/macOS. Headless Chromium and its 390-pixel
viewport do not fill either field.

## Actual automated verification

- Local full regression passed 267/267 normally and 267/267 under optimized Python; the
  isolated wheel and exact-clean-commit preparation command passed.
- Published branch-head
  [CI 40088078017](https://github.com/lvlunario/project-chimera/actions/runs/40088078017)
  passed all three jobs. Python 3.11 ran 267 tests in 7.582 seconds, executed all eight
  preparation controls and passed clean-wheel verification. Python 3.12 ran 267 tests in
  5.359 seconds with the same preparation/clean-wheel result. Chromium passed 2/2 in
  3.989 seconds.
- Independent AI gate/browser reviewers initially found publication-race, single candidate
  check, unindexed retained input, missing-evidence, stale-command, wording and publication-
  marker gaps. All were corrected with permanent adversarial controls. Final independent
  re-review found no remaining implementation blocker.

These results verify automation; they do not state that Leo ran the journey or accepted a
phase.

## Limits and risks

- Synthetic references validate software behavior, not RF physics or live hardware.
- Manual keyboard/usability, browser diversity, physical-device and screen-reader/WCAG
  observations remain unperformed.
- The local dashboard has no authentication, TLS, remote hosting, multi-user isolation or
  production-server security claim.
- A running/unknown interrupted task remains non-resumable pending investigation.
- The October 17 M2 disposition is seven days late. November 7 remains amber until actual
  observations, defect disposition and phase decisions are recorded.

## Decision record — intentionally blank

Complete the generated worksheet during the actual review, then record the response here
without paraphrasing it into an approval:

- Reviewer and method:
- Actual review date/time and environment:
- P3 verification/validation result:
- P4 verification/validation result:
- P5 verification/validation result:
- Defects, severity, owner and due date:
- Decision: pending / approve / approve with conditions / request changes / defer
- Actual response (verbatim):

No response is required before performing the walkthrough. Recommended sequence: use this
exact candidate, record actual observations, fix any critical defect, then disposition P3
and P4 separately; resolve D-004–006 before P5 disposition. Do not merge or deploy
automatically.
