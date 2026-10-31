# Chimera — Engineering Verification Platform

**Magnum Opus** is the development program for Chimera: an open-source platform
that runs engineering checks, evaluates requirements, and preserves the evidence
needed to investigate failures and hand results to another engineer.

**Prototype target: December 12, 2026. Program manager: Leo (project owner).**

## Start here

Implementation and detailed documentation currently live on
[`magnum-opus/development`](https://github.com/lvlunario/project-chimera/tree/magnum-opus/development)
in [draft PR #1](https://github.com/lvlunario/project-chimera/pull/1). The repository homepage is the project
entry point; the implementation has not been merged into `main`.

| What you need | Where to go |
|---|---|
| Current implementation and installation instructions | [Development README](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/README.md) |
| Product concepts and operating instructions | [Project manual](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/MANUAL.md) |
| Deadlines and deliverables | [Roadmap](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/ROADMAP.md) |
| Your verification, validation and approval instructions | [Phase approval guide: P0–P7](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/APPROVALS.md) |
| First concept review and scope decisions | [P0 review](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-09-14.md) |
| Core-engine evidence and practical approval exercise | [P1 approval packet](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-09-15-p1.md) |
| Durable execution verification and validation exercise | [P2 approval packet](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-09-22-p2.md) |
| Current P3/P4/P5 operator exercise | [October 24 acceptance packet](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-10-24-p345-operator-acceptance.md) |
| Latest weekly concept review | [October 26 P5 trust-boundary review](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-10-26.md) |
| Ongoing changes, test evidence and next steps | [Daily engineering logs](https://github.com/lvlunario/project-chimera/tree/magnum-opus/development/docs/daily) |
| Requirements and quality approach | [Requirements](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/REQUIREMENTS.md) · [Quality plan](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/QUALITY.md) |

## Progress snapshot — October 31, 2026

The development branch includes:

- A local dependency-aware workflow engine and strict JSON workflow CLI.
- Versioned JSON evidence that can be reopened without executing checks again.
- Separate requirement verdicts and execution outcomes, plus versioned requirement bindings.
- Atomic SQLite storage for completed runs and their selected bindings.
- A Linux-owned per-task journal with pending-only restart and exact task-commit reconciliation.
- Callback-free completed-journal export into the existing evidence/storage/verdict workflow.
- Strict timestamp/link-margin CSV ingestion with exact input SHA-256 identity,
  deterministic synthetic fault plans, failing-sample evidence and passing/malformed controls.
- A canonical reopened-evidence JSON report and deterministic self-contained HTML view.
- An integrated `chimera verify-link` operator command from strict CSV and optional
  fault plan through journal, immutable reopen, verdict and JSON/HTML report.
- A deterministic self-verifying ZIP handoff plus independent inspection command.
- Read-only loopback API and multi-run dashboard that cross-validate completed artifacts,
  keep invalid packages visible, provide bounded investigation views, and download the
  same validated handoff bundle.
- Test-only headless-Chromium coverage for native keyboard navigation, desktop/mobile-width
  rendering, security headers, and download/reopen behavior.
- An exact-clean-commit operator-acceptance preparation workspace with machine evidence and
  a deliberately unfilled human observation worksheet.
- A versioned exact-commit P7 performance control for the synthetic operator, handoff and
  dashboard workload, with explicit local-prototype regression budgets.
- A versioned local-prototype threat model and exact-clean-candidate assessment that trace
  ten threats to current controls, evidence files and explicit residual risks without
  claiming security or human acceptance.
- An exact-clean-candidate release-readiness inventory covering every declared requirement,
  the dated open-defect snapshot, required guide headings and pending human decisions without
  translating inventory completeness into release approval.
- A bounded exact-candidate M4 evidence packet that composes and portably reinspects the
  operator, performance, threat and readiness records while retaining a blank acceptance
  script and pending M4/M5 decisions.
- An installable Python package and CI on Python 3.11 and 3.12.

The [October 24 implementation evidence](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-24.md),
[October 25 packet-publication record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-25.md),
the [October 26 weekly-review record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-26.md),
the [October 27 performance-baseline record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-27.md),
the [October 28 threat-model record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-28.md),
the [October 29 readiness-inventory record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-29.md),
and the [October 31 M4-packet record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-10-31.md)
record candidate-specific local, independent and hosted results. Do not infer a new
candidate's status from an earlier successful run.

**Acceptance state — October 31:** P0 scope (D-001–003) is approved by delegation.
P1 and P2 are conditionally accepted for continued development under the
[delegated decision record](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-09-22-delegated-decisions.md). Leo's personal walkthroughs remain unperformed;
final product validation remains open. P3/P4/P5 remain in progress; P7 release preparation
now includes versioned performance, threat-model, readiness-inventory and bounded M4-packet
controls. The October 17 M2 exact-candidate disposition is fourteen days late; November 7 is
forecast amber with seven calendar days remaining while the
prepared operator worksheet and human walkthrough remain open. Synthetic fixtures establish software
behavior; authorized measured-data validation, production deployment and certification are
not claimed.

## When you can try it

All dates below are 2026 delivery targets, subject to the documented scope and reviews.

| Target | What Leo can test or review |
|---|---|
| Now | Complete local communications workflow, reports, handoff, and read-only dashboard |
| September 19 | M0 baseline; delegated scope decision recorded September 22 |
| October 3 | M1 baseline; P1 retained as conditionally accepted for progression |
| October 17 | M2 baseline missed; engineering candidate exists, exact disposition overdue |
| November 7 | M3 operator packet and walkthrough; current forecast amber |
| November 28 | Release candidate for structured acceptance testing |
| December 12 | Stabilized prototype, manuals and final acceptance demonstration |

The implemented dashboard lists sealed completed runs, exposes PASS/FAIL and synthetic
status, shows failing samples, and links canonical evidence, reports and handoff bundles.
It is a local read-only prototype, not a hosted multi-user service.

## Try the current foundation

Use Python 3.11 or newer. Clone the **development branch** to obtain the implementation:

```bash
git clone --branch magnum-opus/development https://github.com/lvlunario/project-chimera.git
cd project-chimera
python -m pip install .
chimera-demo
python -m examples.approval_demo
python -m examples.storage_demo
python -m examples.journal_demo
python -m examples.resume_demo
python -m examples.commit_recovery_demo
python -m examples.journal_export_demo
python -m examples.link_csv_demo
python -m examples.p2_approval_demo
python -m examples.fault_demo
python -m examples.report_demo
python -m examples.p34_candidate_demo
chimera verify-link examples/fixtures/link_margin_passed.csv \
  --threshold-db 3.0 --output /tmp/chimera-link-run
chimera serve-link /tmp/chimera-link-run --port 8765
chimera export-link /tmp/chimera-link-run --output /tmp/chimera-link-run.zip
chimera inspect-link /tmp/chimera-link-run.zip
mkdir -p /tmp/chimera-runs
cp -R /tmp/chimera-link-run /tmp/chimera-runs/passing
chimera serve-dashboard /tmp/chimera-runs --port 8765
```

Some demonstrations deliberately show failures to verify correct failure handling.
Follow the [P1 packet](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/reviews/2026-09-15-p1.md)
for expected results and your 20–30-minute verification/validation walkthrough.

For detailed CLI, evidence and verdict commands, use the [manual](docs/MANUAL.md).
Maintainers run `python -m unittest discover -s tests -v` and
`scripts/verify_clean_install.sh`; neither publishes a package. On Linux, try
`python -m examples.ownership_demo` for the [ownership exercise](docs/MANUAL.md#database-ownership-guard-linux-prerequisite).

## How approvals work

**Verification:** Does the implementation meet its documented requirements?
**Validation:** Does the demonstrated workflow solve the intended engineering problem?

Each phase provides evidence, steps to try or observe, expected results, and a decision
record. Leo can **Approve**, **Approve with conditions**, **Request changes**, or **Defer**.
Passing tests do not constitute PM acceptance; no phase is accepted from silence.

Development uses Conventional Commits, versioned phase documentation, daily evidence
logs and weekly concept/demo reviews. AI-assisted implementation and independent AI
QA are identified separately from Leo's acceptance and personal engineering proficiency.
