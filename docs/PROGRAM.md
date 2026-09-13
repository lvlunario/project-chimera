# Magnum Opus program

## Product and audience
Chimera helps integration and test engineers run repeatable verification workflows,
trace results to requirements, and explain failures with preserved evidence.
Start with simulated engineering systems; introduce real hardware through explicit
adapters later. The initial vertical is communications-link verification.

## Roles
Program manager: Leonardo Lunario — product priorities and milestone acceptance.
Implementation: AI-assisted development — architecture, code, tests, documentation.
The 100-developer framing expresses ambition, not actual staffing or throughput.

## Delivery phases
| Phase | Deliverable | Exit criteria | State |
|---|---|---|---|
| P0 | Charter and architecture | Scope, requirements, risks, development policy recorded and reviewed with Leo | Draft documented; PM review pending |
| P1 | Local execution core | Graph validation, failure propagation, evidence schema, CLI, package install and CI verified | In progress |
| P2 | Durable execution | SQLite run storage; restart recovery and idempotency tested | Planned |
| P3 | Engineering adapters | Synthetic telemetry ingestion and deterministic fault injection with reference fixtures | Planned |
| P4 | Verification evidence | Requirement mapping, reproducible JSON/HTML reports, missing-evidence detection | Planned |
| P5 | Operator product | API and accessible dashboard; end-to-end acceptance tests | Planned |
| P6 | AI assistance | Provider adapter, bounded permissions, evaluation dataset and measured baseline comparison | Planned |
| P7 | Release | Reproducible deployment, performance results, threat model, demo and operator guide | Planned |

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
1. Completed-run JSON evidence v1 is implemented; next define verification verdict
   versus execution-error categorization and full provenance without implying P1 closure.
2. Packaging and Python 3.11/3.12 CI are implemented and verified on the development
   branch; retain their evidence for P1 integration and final gate review.
3. Next: add CLI workflow input with strict validation and meaningful exit codes.
4. Add durable run storage before concurrency/retries.
5. Close P1 only after its full exit criteria pass.

## Risks
Trusted task functions execute in-process and can hang, mutate state or access the host.
The prototype is not a sandbox. There is no timeout, cancellation, durable state,
retry, concurrency, web UI or production isolation yet. Synthetic demonstrations
must remain labeled synthetic; they do not establish physical-system performance.
