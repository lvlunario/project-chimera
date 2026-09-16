# Chimera — Engineering Verification Platform

**Magnum Opus** is the development program for Chimera: an open-source platform
that runs engineering checks, evaluates requirements, and preserves the evidence
needed to investigate failures and hand results to another engineer.

**Prototype target: December 12, 2026. Program manager: Leonardo (Leo) Lunario.**

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
| Ongoing changes, test evidence and next steps | [Daily engineering logs](https://github.com/lvlunario/project-chimera/tree/magnum-opus/development/docs/daily) |
| Requirements and quality approach | [Requirements](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/REQUIREMENTS.md) · [Quality plan](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/QUALITY.md) |

## Progress snapshot — September 16, 2026

The development branch includes:

- A local dependency-aware workflow engine and strict JSON workflow CLI.
- Versioned JSON evidence that can be reopened without executing checks again.
- Separate requirement verdicts and execution outcomes, plus versioned requirement bindings.
- Atomic SQLite storage for completed runs and their selected bindings.
- A Linux ownership-lock prerequisite; journaling/recovery integration is still pending.
- An installable Python package and CI on Python 3.11 and 3.12.

The [September 16 evidence log](https://github.com/lvlunario/project-chimera/blob/magnum-opus/development/docs/daily/2026-09-16.md)
records the morning's **86-test hosted verification** and afternoon's **105 passing
local/independent tests** with isolated installation. Candidate-specific hosted
results are tracked there and in the PR; do not infer them from earlier runs.

**Phase status:** P0 scope acceptance and P1 acceptance remain pending Leo's response.
P1's engineering review packet is ready. P2 storage work is in progress;
per-task journaling and interrupted-task recovery are not implemented yet.
The browser dashboard and measured-data workflow remain planned.
Current demonstrations use synthetic data; this is not a production or certification release.

## When you can try it

All dates below are 2026 delivery targets, subject to the documented scope and reviews.

| Target | What Leo can test or review |
|---|---|
| Now | Command-line synthetic workflows, failed checks, evidence replay, and completed-run storage |
| September 19 | Concept, use cases, exclusions and scope decisions |
| October 3 | Core-engine gate: review evidence and perform the P1 approval exercise |
| October 17 | Complete communications-data-to-result workflow |
| November 7 | Feature-complete prototype with a basic operator dashboard |
| November 28 | Release candidate for structured acceptance testing |
| December 12 | Stabilized prototype, manuals and final acceptance demonstration |

The planned dashboard has a run list, check-by-check results, and an evidence/report view.
The intended journey is to load communications-link data, run verification, inspect
failing samples, then reopen or export the supporting evidence.

## Try the current foundation

Use Python 3.11 or newer. Clone the **development branch** to obtain the implementation:

```bash
git clone --branch magnum-opus/development https://github.com/lvlunario/project-chimera.git
cd project-chimera
python -m pip install .
chimera-demo
python -m examples.approval_demo
python -m examples.storage_demo
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
