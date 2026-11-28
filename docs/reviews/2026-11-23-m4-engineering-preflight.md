# M4 engineering preflight — November 23, 2026

Status: completed AI-assisted engineering dry run for the November 28 M4 review. This is not
the Monday-morning weekly concept review, a human walkthrough, a P3/P4/P5 disposition, M4
permission or M5 product acceptance. It records reproducible evidence without changing the
retained nominee.

Review target: exact engineering candidate
[`b6b6878a3c4fdc700683508a19b5a5bc2e178671`](https://github.com/lvlunario/project-chimera/commit/b6b6878a3c4fdc700683508a19b5a5bc2e178671).
Current program head at the start of the preflight:
[`1b0f54c33419238c89fc5c8c157ed6337740e206`](https://github.com/lvlunario/project-chimera/commit/1b0f54c33419238c89fc5c8c157ed6337740e206).
The distinction is deliberate: later program documentation and controls do not silently
become a new release candidate.

## Outcome

The retained v4 nomination/archive pair and a fresh clean-checkout regeneration both passed
their bounded controls. No engineering release blocker was found. The evidence supports
presenting the exact candidate for M4 review, but it does not complete the review: Leo's
actual operator observations, separate P3/P4/P5 dispositions, residual-risk review and M4
decision remain blank and controlling.

## Connected GitHub reconciliation

Connected inspection at `2026-11-23T10:32:30Z` found draft
[PR #1](https://github.com/lvlunario/project-chimera/pull/1) open, unmerged and mergeable at
program head `1b0f54c`. The retained candidate's two bound workflow runs still report
completed/success, and all six required jobs and their named steps report success:

| Evidence | Python 3.11 | Python 3.12 | Chromium |
|---|---:|---:|---:|
| [push 44291039769](https://github.com/lvlunario/project-chimera/actions/runs/44291039769) | 350 tests / 14.067 s | 350 tests / 14.116 s | 2 tests / 6.672 s |
| [PR integration 44291051452](https://github.com/lvlunario/project-chimera/actions/runs/44291051452) | 350 tests / 16.509 s | 350 tests / 12.496 s | 2 tests / 5.102 s |

Both Python matrices also printed `packet_complete_for_m4_review` and completed isolated-wheel
verification. These are hosted engineering results, not a merge or acceptance decision.

The same connected query returned exactly four open issue titles with the machine-checked
`Defect:` prefix: [#4](https://github.com/lvlunario/project-chimera/issues/4),
[#14](https://github.com/lvlunario/project-chimera/issues/14),
[#25](https://github.com/lvlunario/project-chimera/issues/25) and
[#28](https://github.com/lvlunario/project-chimera/issues/28). Their issue bodies or latest
verification comments retain `fixed/verified pending PR integration`; none declares a current
release blocker. The canonical program-head readiness manifest still carries the preceding
`2026-11-22T10:22:42Z` offline snapshot. This preflight query confirms continuity but does not
rewrite the manifest, establish trusted time or waive the required query at actual disposition.

## Fresh exact-candidate dry run

A new detached worktree was created at the full candidate SHA, verified clean before use and
removed after the run. The actual results were:

- full suite: 350/350 passed in 12.043 seconds;
- optimized full suite: 350/350 passed in 12.360 seconds;
- isolated wheel install passed from outside the checkout using installed package code;
- a new exact-candidate review rehearsal reported operator acceptance preparation `passed`,
  performance `passed`, threat model `model_complete`, readiness `review_inputs_complete`,
  packet `packet_complete_for_m4_review` and no release blocker;
- read-only rehearsal reinspection passed;
- a new deterministic archive was built and reinspected successfully; and
- final candidate status and `git diff --check` were clean.

The transient dry-run receipt was
`4ee2273d297efb6d2d97c5810a95bc851032d29ee35100f288aa8f0ba96d773c`, its packet was
`92ff562748fc518e9625f61f5dcfffc3660019b85f70417d0a38be8ae6fefbb4`, and the 774,690-byte
archive was `0dcba90fa31ef04e41ae673ce4dea247a610a0474a57e9bc25100a450d1fe13e`.
The temporary rehearsal/archive were deleted after inspection; these identities are execution
evidence, not a retained nomination or a replacement for v4. Separate preparations contain
new run IDs, timestamps and performance samples, so their hashes are expected to differ from
the retained binder.

The repository's read-only retained-lineage command separately validated both archived pairs
before selecting v4. The retained current evidence remains byte-for-byte unchanged:

- nomination SHA-256:
  `2e3adb3db89ceeb41a50b89583080886ed2ad4363ea4102621e31fb336c517a9`;
- archive SHA-256:
  `9122615ca805bd735a2ae54a96412daebd4d642459f050763c5a5bf0798e1646`;
- receipt SHA-256:
  `d3ebb942a33e74d19f57e9101173040b7eece25ec54c98a322c984a0743e80fd`;
- packet SHA-256:
  `28618c40e5ad432c2b0301c8a5d3d8ec412734f2075756dc1fc81d0d1efc1f3b`.

Two harness-only corrections are retained for transparency. The first timing wrapper called
`/usr/bin/time`, which is absent in this environment, so it stopped before executing product
tests and was replaced with the shell's timing builtin. After the official rehearsal and
archive inspectors had passed, an ad hoc diagnostic snippet assumed a nonexistent
`assessment` field and raised `KeyError`; the canonical records and official inspectors were
unchanged. Neither event is a Chimera defect or a passing product result.

Two independent AI reviews made no repository edits and reported PASS. Gate QA rechecked the
program/roadmap authority boundary, v4 identities, connected PR/defect facts and schedule
arithmetic, finding no M4 engineering-evidence blocker. Integration QA independently ran the
retained lineage, archive and nomination inspectors, then passed 35/35 focused release controls
in 4.399 seconds and 35/35 under optimized Python in 4.351 seconds. It confirmed P3/P4/P5 and
M4/M5 remain `pending` and human acceptance remains `not_granted`. These are independent
engineering reviews, not Leo acceptance.

## Gate status, risks and next actions

P0 remains approved by delegation. P1/P2 remain conditionally accepted for continued
development. P3/P4/P5/P7 remain in progress; D-004–006, operator/manual-device/screen-reader
observations, M4/M5 and final product acceptance remain pending. M2 is thirty-seven days late;
M3 is sixteen days late and red. M4 November 28 is five calendar days away and M5 December 12
is nineteen days away. Both remain amber if feature scope stays frozen and November 29–December
12 remains reserved for stabilization and acceptance.

Before an M4 disposition:

1. query the connected `Defect:` inventory again and record any changed issue/blocker state;
2. use the retained v4 binder and its blank `M4-ACCEPTANCE-SCRIPT.md` against the exact
   candidate rather than the moving branch head;
3. record the actual reviewer/method, checklist results, residual-risk disposition, defects,
   conditions and verbatim M4 decision; and
4. leave M5 pending—M4 only permits final acceptance testing.

No new routine scope decision is requested. The existing decisions needed are Leo's actual
P3/P4/P5 dispositions and M4 response. If the exact candidate changes, regenerate matching
hosted evidence, rehearsal, retained archive and a separately named nomination; never edit v4.

Teaching note for Leo: this preflight is a fire drill for the review binder. Repeating the
technical procedure proves the exits still open and the binder still agrees with the named
candidate; it cannot record whether the operator journey is understandable or whether you
permit final acceptance testing. Those judgments require your actual response.
