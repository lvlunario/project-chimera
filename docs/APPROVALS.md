# Leo's phase approval guide

Requested by Leo on September 14, 2026. All approval records start pending.
This guide adds review instructions; it does not approve the existing concept,
close any phase, or change the [delivery dates](ROADMAP.md).

## Your responsibility

**Verification:** review evidence that the implementation meets its documented requirements.
**Validation:** try or observe the intended engineering task and judge whether it solves the user's problem.

The development/QA team supplies tests, fixtures, results, defects and a recommendation.
You review the evidence, perform or observe the walkthrough, challenge unclear behavior,
and record your decision. You do not need to read every line of code or rerun the whole suite.
Allow 20–30 minutes per phase; allow 45–60 minutes for operator/release acceptance.
Watching an assisted demonstration is allowed: record it as observed, not personally executed.
An iPhone can be used for document review; command-line exercises need a prepared computer
or an assisted demonstration. Dashboard device support will be declared in its review packet.

## Required packet before every approval request

- [ ] Phase, gate, target date and exact candidate commit/version identified.
- [ ] Changes and user benefit explained in plain language.
- [ ] Requirement IDs linked to actual tests, outcomes and evidence files.
- [ ] Setup prerequisites, exact commands or clicks, supplied input files and expected output included.
- [ ] Passing, failing and invalid/missing-input cases included where applicable.
- [ ] Known defects, limitations, schedule impact and recommendation stated.
- [ ] Checklist below copied into a dated review record, with space for actual observations.

Future exercises below are acceptance scenarios, not commands for shipped features.
Before presenting a future phase for approval, the team must supply runnable,
candidate-specific instructions and reference results. Missing evidence means not ready.

## P0 — Concept and scope / M0, September 19

Read [the concept review](reviews/2026-09-14.md) and [roadmap](ROADMAP.md).

- [ ] Verification: find the intended user, three use cases, exclusions, deliverables and dates;
      flag any requirement whose success cannot be demonstrated.
- [ ] Validation: walk through importing communications data, investigating a failed requirement,
      and handing off evidence. Explain whether this is the product you want built.
- [ ] Decide D-001: retain communications-link verification or describe the replacement.
- [ ] Decide D-002: retain the listed prototype exclusions or specify changes and priorities.
- [ ] Decide D-003: prioritize failed-link investigation, then malformed-input and passing controls.

Expected: an agreed problem, scope and demonstrable success criteria.
Approve the concept only; this does not accept working software.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P1 — Core execution / M1, October 3

Review [the CLI and evidence instructions](MANUAL.md) and candidate-specific CI evidence.

- [ ] Verification: inspect both supported Python CI jobs and clean-install results for the
      candidate. Confirm graph validation, failure propagation, evidence and CLI criteria have proof.
- [ ] Run or observe the current synthetic workflow using the manual. Predict results first:
      health/ingest succeeded, link-check failed, report blocked, exit 1, evidence preserved.
- [ ] Reopen the record using the manual's evidence API. Confirm the same run ID and results,
      without executing another test.
- [ ] Observe the supplied invalid-dependency and existing-output cases. Expected: invalid
      workflow exits 2 without run evidence; an existing evidence file is not overwritten.
- [ ] For final P1 closure, review the completed requirement-verdict/error model demonstration:
      a valid failing measurement differs from an execution error and a blocked check.
      This model and its separate versioned binding artifact are now implemented; use the
      candidate packet for exact evidence and commit references.
- [ ] Validation: explain which steps ran, why the report was blocked, and what evidence you
      would hand another engineer. Ask for clearer feedback if the output is ambiguous.

Expected: all P1 exit criteria evidenced and the core behavior understandable.
Additional implemented exercise: run or observe `python -m examples.verdict_demo`.
Verify COM-LINK-001 is fail while link-check/handoff executed successfully; INVALID
is error and BLOCKED/MISSING are not_evaluated. Explain why a failed requirement is
not a crashed check. Assessment recomputed from saved/reopened evidence must be
identical using the same serialized bindings and confirm the assessment's binding digest
matches that artifact. This API-only
exercise does not change the CLI's execution exit codes or establish full provenance.
The synthetic demo alone is insufficient for full P1 acceptance.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P2 — Durable storage / M2, October 17 (planned)

- [ ] Verification: review restart, incomplete-write and duplicate-execution test evidence.
- [ ] Follow the supplied interruption exercise; record the run ID and completed steps,
      stop at the specified safe test point, restart and reopen the record.
- [ ] Compare before/after evidence. Expected: committed results survive; incomplete work is
      identified; completed work is not silently duplicated. Resume behavior matches the documented policy.
- [ ] Validation: explain how you would recover from an interrupted session and distinguish a
      completed record from one needing attention.

Approval covers persistence/recovery, not hardware side-effect guarantees.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P3 — Engineering data and faults / M2 slice October 17; complete by M3 November 7 (planned)

- [ ] Verification: inspect the schema, declared units, reference calculations and fault fixtures.
- [ ] Load the supplied passing and failing CSVs using the packet's steps. Compare a selected
      sample with its independently calculated expected value and threshold.
- [ ] Load missing-column, invalid-unit and malformed-value cases. Expected: explicit input
      errors and unavailable dependent checks; invalid evidence must never produce a pass.
- [ ] Apply the supplied deterministic fault twice with the same configuration.
      Expected: the same engineering outcome; run IDs/timestamps may differ.
- [ ] Validation: decide whether importing and diagnosing these files resembles your intended
      test workflow and whether the error tells you what to correct.

Synthetic fixtures establish software behavior. Measured-data validation remains separately
pending until a suitable authorized dataset is tested.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P4 — Requirements and reports / M3, November 7 (planned)

- [ ] Verification: select one failing requirement; trace its ID to input identity, procedure/
      configuration version, threshold, calculation, failing samples and final verdict.
- [ ] Export JSON and HTML, reopen the run, and compare the engineering results across views.
      Expected: matching verdicts and traceable evidence, with no need to rerun measurements.
- [ ] Inspect a missing-evidence example. Expected: an explicit unavailable/error state,
      with no unsupported pass or invented measurement.
- [ ] Validation: use the report to explain the failure and next investigation step without
      asking the developer to reconstruct it.

Expected: a report another engineer can understand and audit.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P5 — Operator dashboard / M3, November 7 (planned)

- [ ] Verification: review API, dashboard, accessibility and end-to-end test evidence against
      the declared supported environment.
- [ ] Follow the supplied clicks: select data/procedure, start a run, inspect the failed
      requirement, find its samples, reopen the saved run and export the report.
- [ ] Repeat the passing and malformed-input controls. Expected: consistent results in UI,
      stored evidence and reports; clear recovery guidance for errors.
- [ ] Validation: attempt the journey using the operator guide. Record where you need help,
      confusing labels, missing information and steps that do not support your task.
      Assisted steps remain marked assisted and unresolved usability issues get defect IDs.

Expected: the intended user can complete the agreed journey; any critical usability blocker
is resolved before phase acceptance.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P6 — AI assistance / optional, no committed delivery date (planned)

- [ ] Verification: review the evaluation set, baseline comparison and permission boundaries.
- [ ] Compare a suggestion with its cited run evidence; try missing evidence and a misleading
      input from the supplied evaluation set.
- [ ] Expected: AI cannot alter deterministic verdicts or invent supporting measurements;
      unsupported claims are identified and evaluated.
- [ ] Validation: decide whether the assistance provides useful explanation beyond the
      deterministic report and whether its limitations are acceptable.

Record approve/change/defer. Deferring P6 does not block the December prototype.
Decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## P7 — Release / M4 November 28 and M5 December 12 (planned)

### M4: permission to enter final acceptance testing

- [ ] Verification: review requirement coverage, integrated regression, clean-install proof,
      performance results against documented targets, threat model and open defects.
- [ ] Follow or observe installation in the declared clean environment using only the guide.
      Expected: the candidate starts and the documented demonstration works.
- [ ] Validation: confirm the final acceptance script covers your intended workflow and that
      limitations and remaining noncritical issues are explicit.

M4 acceptance permits final testing; it does not constitute M5 product acceptance.
M4 decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

### M5: prototype acceptance

- [ ] Repeat the passing, failing, malformed-input, recovery and report-handoff scenarios
      against the exact release candidate and retain the results.
- [ ] Verify fixes and confirm there are no unresolved critical acceptance failures.
- [ ] Validation: judge whether the whole workflow meets the agreed user need and whether
      another engineer can reproduce it using the operator/developer manuals.
- [ ] Record the accepted version, evidence bundle and any explicitly accepted limitations.
      If release tagging follows this decision, link the tag to the accepted commit.

M5 decision: **Pending**. Actual observations/conditions: **Not yet recorded**.

## How to record your decision

Reply here in ChatGPT or in the relevant GitHub review. A concise response is sufficient:
"P1 — request changes. I observed the demo; reopening evidence was unclear. Please
add the missing instruction and demonstrate it again."

For each phase, copy this record into its dated review packet:

- Phase/gate and candidate commit:
- Evidence/CI/fixture links:
- Reviewer: Leonardo Lunario
- Method: personally executed / observed demonstration / document review
- Checklist results: item, expected result, actual result, pass/fail/not run
- Verification conclusion:
- Validation conclusion:
- Decision: pending / approve / approve with conditions / request changes / defer
- Conditions or defects, owner and due date:
- Actual response (verbatim) and response date/time:
- Recheck evidence and condition closure, if applicable:

Full acceptance requires the phase criteria, evidence and Leo's actual approval.
Conditional approval remains conditional until its conditions are evidenced and
disposed of as specified by Leo; it is not automatically full gate closure.
Critical acceptance failures require correction or an explicit scope/baseline change.
A scope change must never relabel a failing test as passing.
No response means pending. Routine reversible authorized development may continue.
Product acceptance is separate from a GitHub merge or deployment decision.
