# Chimera — Engineering Verification Platform

Magnum Opus is the development program for Chimera: an open-source platform for
orchestrating verification workflows and collecting evidence against requirements.

Status: foundation prototype. No claim of production readiness or certification.
The current implementation executes trusted Python tasks locally, in sequence,
validates their dependency graph before execution, and blocks downstream tasks
after a failure. AI orchestration and distributed execution are future milestones.

## Install and run
Python 3.11 or newer; the foundation has no third-party runtime dependencies.

```bash
python -m pip install .
chimera-demo
chimera run examples/workflow.json --evidence run.json
python -m unittest discover -s tests -v
python -m chimera
python -m examples.evidence_demo
python -m examples.verdict_demo
```

The demo intentionally fails a link-margin check and shows its dependent report
as blocked, while an independent health check succeeds.
The evidence demo saves/reopens a versioned JSON snapshot in a temporary file.
The workflow example intentionally exits 1 after saving evidence because its synthetic
link check fails; Chimera never overwrites an existing evidence path. See the
[manual](docs/MANUAL.md#declarative-workflow-cli) for schema, exit codes and limitations.
Maintainers can verify an isolated wheel install with
`scripts/verify_clean_install.sh`; it builds from a temporary source copy and does
not publish a package.

The [verdict demo](docs/MANUAL.md#requirement-verdicts) shows a successfully executed
check returning a failed requirement while its handoff task still runs. It also shows
error and missing/blocked outcomes. This is synthetic, not a measured-data adapter.

## Program
Prototype target: **December 12, 2026**. Leo is the program manager.
Start with the [project manual](docs/MANUAL.md), [dated roadmap](docs/ROADMAP.md),
and [quality plan](docs/QUALITY.md). Weekly reviews explain concepts and demonstrate progress.

See [program plan](docs/PROGRAM.md), [requirements](docs/REQUIREMENTS.md),
[architecture](docs/ARCHITECTURE.md), and [daily logs](docs/daily/).

Development takes place on `magnum-opus/development`. Progress means working,
verified increments; phases close only when acceptance evidence exists.
AI-assisted implementation is recorded as such. The program owner reviews scope
and milestone outcomes; generated code is not evidence of owner proficiency.

## Phase approval

Leo: use the [phase approval guide](docs/APPROVALS.md) for P0–P7 verification and validation checklists,
required evidence, walkthroughs, expected results and decision records.
Each phase packet must include these checks and candidate-specific runnable instructions.
Engineering verification and Leo's acceptance are tracked separately; no phase is
accepted from silence or from a test count alone.
