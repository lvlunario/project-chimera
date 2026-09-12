# Quality, test and integration plan

## Role responsibilities
These are AI specialist assignments when tools are available, not hired employees.
Program manager (Leo): scope, priorities and milestone acceptance.
Implementation lead: small cohesive changes and unit tests.
QA reviewer: independently derive acceptance/negative tests from requirements.
Integration reviewer: cross-component contracts, clean setup, persistence and reports.
Release reviewer: evidence completeness, reproducibility, known defects and documentation.

Use separate bounded agent reviews for nontrivial features and release gates where
available. The implementer must not be the sole reviewer of critical release evidence.
If independent review cannot run, record it as pending; do not invent approval.
Create parallel tasks only for independent work; coordinate interface changes first.
External human hiring, paid tools and infrastructure require concrete scope/cost proposals.

## Definition of done for an increment
Requirement or defect identified; code reviewed; relevant tests actually executed;
commands/environment/commit and results recorded; documentation/examples updated;
integration effects assessed; no unreported critical defect. Distinguish implemented
from verified, independently reviewed, and PM-accepted.

## Prototype acceptance checklist
- New developer can run the documented demo within 30 minutes on the supported
  environment; record observed time and environment, not merely estimate it.
- Valid passing/failing datasets produce the expected traceable verdicts.
- Missing/invalid data cannot silently become a pass; units and timestamps validated.
- Run evidence includes schema version, run ID, input identity/hash, requirement IDs,
  code/config version and outcomes; records can be reopened and reports agree with them.
- Invalid graph preflight has no task side effects; failed dependencies block consumers.
- Interruption/restart behavior is documented and tested; no unsupported exactly-once claim.
- End-to-end test traverses the actual operator entry point through storage and export.
- All critical prototype requirements pass on the release commit; zero open release
  blockers; remaining limitations are explicit and dispositions reviewed with Leo.
- Clean install, regression evidence, manuals and acceptance script accompany a tag.
- Leo records acceptance or outstanding conditions after running/observing the demo.

Workload and latency targets will be baselined at M1 against the chosen use cases.
No invented performance benchmark or hardware validation claim.

## Defects and risk
Use GitHub issues: reproduction, expected/actual result, version, environment, severity,
requirement, owner role, target fix and retest evidence. Blocker = cannot run or trust
critical acceptance (including false pass/data loss); major = critical workflow impaired;
minor = noncritical problem with documented workaround.
Track malformed input, state consistency, repeated side effects, dependency failures,
environment drift and misleading reports throughout integration.

## Independent planning review — September 12
A separate AI QA planning reviewer recommended a single operational vertical slice,
clean-install evidence, negative-path coverage, requirement traceability, independent
release review and explicit PM acceptance. These were incorporated into this plan.
This was a planning review, not a code or release approval.
