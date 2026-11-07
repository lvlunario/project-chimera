# Chimera local-prototype threat model

Model version: `p7-local-prototype-threat-model-v1`  
Phase: P7 release readiness; M4 decision pending  
Machine source: [`threat-model-v1.json`](threat-model-v1.json)

This model covers Chimera's approved prototype boundary: one authorized operator on one
trusted local host, local files, a read-only IPv4-loopback dashboard, and synthetic or
separately authorized data. It consolidates current controls and residual risk for M4 review.
It is not a penetration test, vulnerability scan, security certification or acceptance of
residual risk.

## Trust boundary

Included:

- strict workflow, telemetry, fault-plan and archive input handling;
- durable execution, recovery, completed evidence, reports and handoff;
- the local read-only API/dashboard and repository-level release evidence.

Explicitly excluded:

- remote hosting, accounts, multi-user isolation, TLS and production operation;
- sandboxing arbitrary Python callbacks, hostile-host filesystem defense and general
  exactly-once external effects;
- digital signatures, trusted time, build attestation, measurement authenticity, live
  hardware and certification; and
- handoff transport, receiver-host security and authenticity across an untrusted channel.

The operator protects the host, checkout and output directories. Typed data is untrusted,
but Python callbacks and operation identities are trusted declarations. Inputs must not
contain secrets or personal data: Chimera has no automatic redaction, encryption or access
control. Synthetic fixtures prove software behavior, not physical-radio performance.

## Threat inventory

| ID | Threat | Current control boundary | Residual risk / M4 position |
|---|---|---|---|
| RISK-001 | Untrusted code or callback gains host authority | Declarative input cannot select code; communications execution uses a typed operator path | Python callbacks remain trusted, in-process, unsandboxed and without timeout/cancellation; tracked for M4 |
| RISK-002 | Malformed or oversized input changes meaning or exhausts resources | Strict schemas, duplicate rejection, exact units and bounded files/tasks/entries | Trusted callback and local-disk resource use remain unbounded; tracked for M4 |
| RISK-003 | Evidence/report substitution creates a coherent false record | Canonical schemas, SHA-256 identities and cross-validation; handoff is reconstructed and revalidated | Coherent replacement of every unsigned artifact can recompute hashes; no authorship/trusted-time claim; tracked for M4 |
| RISK-004 | Paths, links or publication races redirect state | Regular-file bounds, no-overwrite/symlink refusal, exclusive publication and inode ownership | Trusted stable local directories and cooperative processes are assumed; hostile-directory and network-filesystem hardening are out of scope; tracked for M4 |
| RISK-005 | Interrupted work repeats an external effect | Lifetime ownership, running marker, pending-only resume and commit reconciliation | Operation IDs are declarations; ambiguous external effects require investigation, not automatic exactly-once recovery; tracked for M4 |
| RISK-006 | Loopback presentation discloses, mutates or injects rendered evidence | IPv4 loopback, GET-only immutable snapshot, escaped script-free HTML, no CORS, no-cache and restrictive headers | Loopback is not per-user authentication; same-host processes can connect, and future templates require the same escaping discipline; tracked for M4 |
| RISK-007 | Malicious handoff archive escapes its contract | Exact six-entry allowlist/order, stored unencrypted bytes, size bounds and complete reopen validation | Bundle authenticity is unsigned and local directory trust remains; tracked for M4 |
| RISK-008 | Sensitive data persists in artifacts/responses | Manual no-sensitive-data rule and local read-only boundary | No redaction, encryption or confidentiality guarantee; sensitive-data use requires a scope change; tracked for M4 |
| RISK-009 | Mutable CI/dependencies produce untrusted release evidence | Read-only CI, no persisted credential, exact Action pins, bounded jobs and isolated wheel check | Runner images, ranged build tools, package index, browser/system packages remain mutable; no signing/SBOM/attestation; tracked for M4 |
| RISK-010 | Automation or synthetic data is presented as human/physical acceptance | Exact-candidate controls, explicit synthetic labels and always-blank human worksheet | Automation cannot perform Leo's walkthrough, accept residual risk or establish measurement authenticity; tracked for M4 |

No `must_fix_before_m4` threat is currently identified inside this exact trusted-host,
local-only, no-sensitive-data boundary. That is an engineering disposition for review, not
Leo's acceptance. Remote access, sensitive data, untrusted callbacks, authenticity guarantees
or hostile-host operation would expand the boundary and require new controls before use.

## Candidate-bound assessment

Run from an exact clean checkout and write the assessment outside the repository:

```bash
CANDIDATE_COMMIT=$(git rev-parse HEAD)
python -m examples.release_threat_model \
  --candidate-commit "$CANDIDATE_COMMIT" \
  --output /tmp/chimera-release-threat-model.json
```

`RISK-*` identifies an inventory item; the separate `THREAT-*` IDs identify executable
model-control requirements, so a passing check cannot be mistaken for a mitigated risk.
The command validates canonical JSON with duplicate-key rejection, exact fields and IDs,
every cross-reference, declared requirement IDs, tracked regular evidence paths, and the M4
blocker list. It records the candidate, model SHA-256 and exact byte/SHA-256 identity of each
referenced evidence file. It checks the clean candidate before assessment and again before
atomic no-replace publication.

Expected for a complete model: five `PASS THREAT-*` lines and `status: model_complete` in
the canonical output. Invalid input or unsafe publication exits 2. A correctly formed model
with a `must_fix_before_m4` threat still publishes its record but exits 1. `model_complete`
means only that the threat inventory and references passed this control; it does not prove
that controls are effective or close P7.

## Release use

For M4, review this model alongside exact-candidate regression, clean-install, performance,
open-defect and operator evidence. Confirm that the deployment still matches the assumptions.
If the boundary changes, update the versioned model and controls rather than treating an old
assessment as applicable. Leo's M4 and M5 decisions remain pending until actually recorded.

Teaching note for Leo: hashes and cross-checks act like tamper-evident seals on a local test
record. They show whether the pieces agree, but not who created them. A digital signature or
trusted attestation would answer that different question and is outside this prototype.
