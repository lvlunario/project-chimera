# M4 disposition readiness — November 27, 2026

Status: **engineering recommendation: ready for M4 review; not approved**.

This packet is a decision aid for the November 28 M4 gate. It is not a completed human
walkthrough, P3/P4/P5 disposition, M4 permission, merge, release, tag, deployment or M5
acceptance. The exact retained engineering nominee remains
`b6b6878a3c4fdc700683508a19b5a5bc2e178671`; the moving development head is deliberately not
a replacement candidate.

## Evidence reconciled

- Retained v4 archive, nomination, receipt and packet identities remain unchanged.
- Connected inspection at `2026-11-27T10:44:02Z` returned exactly open `Defect:` issues
  [#4](https://github.com/lvlunario/project-chimera/issues/4),
  [#14](https://github.com/lvlunario/project-chimera/issues/14),
  [#25](https://github.com/lvlunario/project-chimera/issues/25) and
  [#28](https://github.com/lvlunario/project-chimera/issues/28). Each remains documented as
  fixed/verified pending PR integration; none declares a current release blocker.
- Development head implementation
  [`fa45ad2`](https://github.com/lvlunario/project-chimera/commit/fa45ad2deef4298327559774a23953be0798f84a)
  adds hosted materialization of the real retained v4 binder in both Python jobs.
- [Push run 45984317850](https://github.com/lvlunario/project-chimera/actions/runs/45984317850)
  and [PR-integration run 45984323534](https://github.com/lvlunario/project-chimera/actions/runs/45984323534)
  passed Python 3.11/3.12 normal and optimized suites, exact rehearsal, retained lineage,
  retained-v4 packet materialization, isolated wheel and Chromium controls.
- Local independent verification passed 356/356 normally and optimized, 4/4 workflow
  controls, exact retained materialization, clean install, compilation and diff checks.

The materialized packet reported `packet_complete_for_m4_review`, exact candidate `b6b6878`,
archive SHA-256 `9122615…1646`, receipt `d3ebb942…e80fd` and packet `28618c40…c1f3b`. Its
acceptance script remains blank/unchecked, P3/P4/P5 and M4/M5 remain pending, and human
acceptance remains not granted.

## Leo's 20–30 minute assisted M4 review

Use a fresh directory outside the checkout:

```bash
python -B -m examples.release_review_archive inspect \
  docs/evidence/chimera-m4-review-b6b6878.zip \
  --extract-packet-to /tmp/chimera-m4-v4-packet
```

Then record actual observations in the extracted `M4-ACCEPTANCE-SCRIPT.md`:

1. Confirm the printed candidate is the full `b6b6878…178671` SHA and status is
   `packet_complete_for_m4_review`.
2. Inspect the PASS, natural-FAIL and synthetic-FAIL dashboard runs; trace one source row to
   evidence, requirement verdict, JSON/HTML report and handoff.
3. Record keyboard, desktop-browser, physical-device and screen-reader observations only if
   actually performed. Leave unsupported or unperformed checks explicit.
4. Review the performance, threat-model and readiness residual risks. Confirm synthetic/local
   evidence is not physical-radio validation, production capacity or security certification.
5. Disposition D-004–006 and P3/P4/P5 separately; do not infer acceptance from passing CI.
6. Record one M4 decision verbatim: approve, approve with conditions, request changes or defer.
   M5 remains pending regardless of the M4 choice.

## Decision boundary

Engineering finds no current release-control blocker to presenting the retained nominee for
M4 review. The controlling blockers are governance and validation: Leo's actual observations,
residual-risk disposition, separate phase decisions and explicit M4 response. If those are not
recorded by November 28, report M4 as missed/pending; do not infer approval or move the baseline.

Known post-M4 hardening remains branch protection, signed provenance/trusted time, dependency
locking/SBOM, CodeQL and repository security policy. None should displace the gate review or
silently change the retained candidate on M4 eve.
