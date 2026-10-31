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

Workload and latency targets were scheduled for M1; the first fixed local-prototype workload
is established October 27 after the integrated operator path became available. This slip is
recorded rather than backdated. No invented hardware-validation or production-capacity claim.

## Release performance evidence

The fixed `p7-local-prototype-v1` workload is the first documented performance baseline.
It generates 10,000 synthetic communications samples, exercises ten fresh durable runs
through the public Python operator boundary behind `verify-link`, repeats handoff
creation/inspection ten times, and opens a ten-run dashboard workspace snapshot five times.
Interpreter/CLI-process startup, HTTP handling and browser rendering are outside these metrics.
The control records raw monotonic timings and p50/p95/max summaries against broad regression
budgets: 3,000 ms operator p95, 1,000 ms handoff p95 and 3,000 ms dashboard-snapshot p95.
Nearest-rank p95 is the observed maximum for the deliberately small ten/five-sample sets.

Run it from an exact clean candidate on each supported CI interpreter. CI prints the full
JSON record even when a target misses; preserve the record or inspected job output for M4
review and do not compare results without their runtime environment. A pass is only a local
synthetic regression check. It is not evidence of
physical-radio performance, concurrent or multi-user capacity, remote-service latency,
production availability or an SLO. Revisit targets only through an explicit versioned
workload/decision change, never by silently raising a budget after a regression.

## Threat-model evidence

The fixed `p7-local-prototype-threat-model-v1` model covers the approved single-operator,
trusted-local-host boundary. Each threat must identify affected assets/boundaries, likelihood,
impact, current controls, declared requirements, tracked evidence files, residual risk and an
M4 disposition. Unit controls reject duplicate/unknown fields, boolean schema versions,
noncanonical JSON, invalid IDs/references, missing residual risk, undeclared requirements,
path traversal, URLs, untracked/directory/symbolic-link evidence and inconsistent blocker
lists. Output tests cover wrong/dirty candidates, checkout/symlink destinations, publication
races, partial writes and canonical reopen in normal and optimized Python.

CI runs the fixed assessment from each exact Python 3.11/3.12 candidate and prints the full
record. `model_complete` establishes only model completeness, candidate binding and reference
validity. It does not establish mitigation effectiveness, penetration-test coverage,
vulnerability absence, build authenticity, security certification, residual-risk acceptance
or phase approval. A `must_fix_before_m4` threat makes the control nonzero while retaining its
record. Independent release review and Leo's M4/M5 decisions remain separate.

## Release-readiness inventory evidence

The fixed `p7-local-prototype-release-readiness-v1` manifest assigns every requirement table
row to exactly one evidence group, captures open `Defect:` issues from GitHub as a dated
snapshot, and declares required headings across the operator and release guides. Its
exact-candidate assessment records the manifest digest and exact identities of referenced
tracked files. Unit controls reject incomplete/duplicate requirement coverage, untracked or
non-regular evidence, missing/out-of-order headings, inconsistent defect/blocker state,
noncanonical input, dirty/wrong candidates and unsafe publication.

This control is an evidence index, not evidence that every cited test passed. A complete
record also does not establish guide usability, live issue state, release readiness, phase
closure or acceptance. Recheck the GitHub defect snapshot and inspect actual hosted test
logs at M4. Unresolved release blockers make the control nonzero while preserving the record;
manual-device, screen-reader, operator, D-004–006 and M4/M5 evidence stay explicitly pending.

## M4 evidence-packet boundary

The `p7-m4-review-evidence-packet-v1` packet is a deterministic transport for existing
candidate-bound review inputs, not a new authority. It admits only the fixed operator,
performance, threat and readiness record contracts for one exact clean commit. Packet tests
must recompute numeric performance outcomes, candidate-model and readiness summaries,
operator P345 cross-field agreement, source chronology, fixed scope limitations and all
pending-human states; merely copying an aggregate `passed` string is insufficient.

The stored ZIP has fixed metadata, bounded entry/byte counts and an exact member allowlist.
Every non-manifest member has a byte count and SHA-256 in the manifest. Portable inspection
rejects duplicate, extra, unindexed, compressed, encrypted, traversing, malformed and
file/path-prefix-colliding entries. Extraction uses a new outside-checkout directory and
never overwrites existing data. Regression coverage includes coherent reindexing attacks,
not only byte changes that leave an obviously stale manifest.

A coherent failed performance target, open must-fix threat or readiness release blocker is
retained as `blocked_by_release_controls`; PACKET-003 is blocked and the command returns
nonzero. The blank acceptance script, M4/M5 decisions and human observations remain pending
in every machine status. Git/SHA identities are not signatures, trusted timestamps or build
attestation. CI logs, live GitHub defect state, actual operator observations and Leo's
recorded decision remain separate evidence. The workflow creates no tag, release artifact,
deployment or external publication.

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

## Continuous integration policy

The `test` workflow exercises Python 3.11 and 3.12 on pull requests and pushes to
the development or main branch. Each matrix job runs the unit regression suite and
the same isolated wheel-install check used locally. Jobs have read-only repository
permissions, do not retain checkout credentials, use no repository secrets, and
are bounded by timeout and concurrency cancellation.

Official checkout/setup Actions are pinned to commit SHAs; comments show the reviewed
major tags. Build tools still come from the Python package index and GitHub-hosted
runner images can change. Logs and action pins must be inspected at release review;
a green badge alone is not complete release evidence. No deployment or publication
occurs in this workflow.

## Local operator API boundary

The first P5 API slice is verified directly as a WSGI application and through an isolated
installed wheel. Tests must cover artifact disagreement, invalid methods, security/no-cache
headers, symbolic links and bounded reads in normal and optimized Python. The server must
bind only to `127.0.0.1` and start only after one completed run is cross-validated. This is
local prototype evidence, not a penetration test, accessibility review, authentication/TLS
assessment or production-deployment approval.

## Local dashboard boundary

The bounded dashboard suite covers passing, failing, synthetic, invalid, empty, duplicate-ID,
symbolic-link and oversized-workspace controls. Direct WSGI tests verify the versioned index,
list/detail/report journey, semantic markup, explicit text status, deterministic responses,
GET-only behavior, security headers and lack of CORS. Fixed HTML views must be keyboard links,
filter only the presentation, leave the versioned JSON snapshot complete and reject ambiguous,
unknown or oversized query input. List → detail navigation must carry only an allowlisted
originating view and provide a native breadcrumb back to it, with no redirect, cookie or
mutable session. It must reject a detail origin whose validated run is not a member of the
claimed view. The isolated wheel must import and
exercise the dashboard against a completed operator run. These automated checks establish
accessibility fundamentals; they do not replace keyboard/browser/device testing or Leo's
operator validation before P5 acceptance.

An end-to-end standard-library control starts the actual WSGI application on an ephemeral
IPv4 loopback port and retrieves the list, a filtered view, detail, canonical report, portable
evidence and requirement bindings over HTTP. It also proves an ambiguous view query receives
HTTP 400 and that a filtered detail returns to the same view. A dependency-free HTML parser audits language, landmark,
heading, caption, scoped-column-header, visible-focus and non-empty-link contracts. This is
transport and structural evidence, not a claim of conformance with WCAG or completion of
screen-reader, browser/device and human usability testing.

A separate Ubuntu 24.04 CI job installs pinned Playwright test tooling and its matching
Chromium build, then opens the real loopback dashboard at desktop and 390-pixel mobile widths. It exercises
native Tab/Enter navigation, visible focus, truthful FAIL-view return, rendered engineering
details, security headers, responsive overflow and a browser-downloaded handoff reopened by
the independent bundle inspector. Playwright remains test-only and is not added to the wheel
or runtime dependencies. This is real-browser automation, not a manual device assessment,
screen-reader/WCAG conformance claim or Leo's operator acceptance.

## Portable handoff boundary

The handoff suite must prove byte-identical repeat export, strict archive entry order and
metadata, exact manifest sizes/digests, completed-run revalidation, existing-output refusal
and fail-closed behavior for changed or extra content. Normal and optimized tests plus an
isolated-wheel CLI export/inspect round trip are required. The bundle's content hashes prove
agreement and transport integrity only; tests must not describe them as signatures,
authorship, trusted time or measurement authenticity.

The dashboard download control must compare its body byte-for-byte with the deterministic
exporter, reopen the response through the bundle inspector over an actual loopback HTTP
server, verify attachment/content/no-cache headers and prove invalid or duplicate identities
remain non-routable. The route packages only the immutable startup snapshot and adds no
filesystem write, mutation method, CORS permission or remote binding.

## Integrated P3/P4 candidate control

The executable candidate control must use the public operator, handoff and dashboard
boundaries and fail with a nonzero process result if any expected condition is absent. Its
checks must survive optimized Python rather than depend on removable `assert` statements.
Both PASS and valid synthetic FAIL are required outcomes; malformed input must create no run
state; completed resume must preserve portable artifacts; and CLI-style export and dashboard
download must be byte-identical and independently inspectable. This is reproducible
engineering verification, not Leo's walkthrough, physical-system validation or phase
acceptance.

## Operator acceptance-preparation boundary

The P3/P4/P5 preparation control checks the full clean candidate commit both before controls
and immediately before publication, and writes outside the source tree. It must stage
privately, refuse any existing/symbolic-link final
path and publish no final workspace after a failed engineering control. Regression coverage
includes invalid/wrong commit identities, dirty state, output races, normal/optimized Python,
three malformed telemetry shapes, portable-artifact resume hashes, repeated handoff identity,
dashboard headers/download bytes and canonical record reopening.

The canonical record is an index of this preparation run, not a new product authority. Run
UUIDs and timestamps make separate preparations different by design. Every retained review
input, run artifact, handoff and worksheet path is relative and hashed, and the record labels
its engineering data synthetic.
The companion worksheet must contain no checked item, observation or decision when generated.
Manual keyboard/usability, browser diversity, physical-device and screen-reader/WCAG evidence
must state the actual environment and observer later. A headless browser or responsive
viewport cannot be relabeled as those observations, and automation cannot record Leo's gate
decision.
