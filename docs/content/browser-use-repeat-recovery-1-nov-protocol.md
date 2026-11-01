# Plain Browser Use queue recovery, 1 November 2026

This is the single proposed operational continuation of the 1 November plain
repeat batch. It does not introduce a new agent, observation fix, prompt or
market. The original repeat protocol and hash-bound descriptive analysis plan
remain in force. This addendum records a queue-classification defect discovered
after attempt 1 stopped, without inspecting answers or correctness grades.

## Cause and narrow correction

Attempt 1 stopped at 15:32:32 Singapore time after five answered trials and one
failed trial. All 424 provider calls have recorded charges, totalling USD
0.28053916066, with no requests in flight and no spending block. The failed
trial's measurement is valid. Its error metadata includes
`Element index -1 not found in browser state` and JavaScript action errors.

The installed Browser Use scroll tool returns the element-index message when
its requested node is absent, before attempting a scroll/CDP operation. The
batch classifier did not recognize that message as an ordinary action failure,
so its conservative unknown-error rule stopped the entire queue. The correction
recognizes only the complete `Element index -?\d+ not found in browser state`
message. Infrastructure errors retain priority, and other unknown errors still
stop the queue. This changes queue handling after a completed failed trial,
not the agent's actions, outputs, limits or available tools.

The failed trial stays failed. None of the six attempted trials may be replayed
or replaced. Their original files and financial records remain immutable.

## Exact continuation

Attempt 2 uses stage `plain-repeat-recovery` and the same budget identity
`browser-use-plain-repeat-2026-11-01`. Bind the complete stopped attempt's command,
ledger, terminal status, 32-slot schedule, slot dispositions, completed list and
six result files by hash. The continuation must equal the original schedule
filtered to its **26 not-started slots**, in unchanged order. Selection uses only
execution status, never answer content, automatic scores or human grades.

Keep the original eight question strings, repeat IDs 2 and 3, original Browser
Use adapter, frozen block/parser, provider policy, model, browser build,
dependencies, sampling and task limits. No paid diagnostics, observation adapter,
parallel execution or additional questions are permitted. Report both attempts
and their operational interruption explicitly. Preserve the original 16-trial
cohort separately and follow the existing question-stratified analysis plan.

## Cumulative spending and authorization

Attempt-1 carryover is USD **0.28053916066**. The proposed additional estimate is
USD **1.30**. Its maximum remaining allowance is USD **1.71946083934**, so both
attempts together remain within the already specified USD **2.00** shared cap.
No unknown request charge is treated as zero. Reconcile any discrepancy before
launch. Preserve USD 20.2117632 of account credit, including the historical
unsettled reservation. No third attempt is supported or implicitly approved.

The absolute deadline remains **2 November 2026 at 12:00 Singapore time**.
The retained exclusive launch marker, per-request reservations, owned worker
and caffeinate processes, monotonic deadline and suspension guard remain active.
No paid calls may begin on Tuesday or later under this plan.

Free synthetic regression tests must cover the exact missing-element message,
real infrastructure errors embedded in mixed messages, other unknown errors,
no replay, schedule/status tampering, cumulative accounting and attempt limits.
Retain the earlier 60-check Quenby preflight with its actual provenance, and
recheck current package/browser/source identity. Do not present the reused shop
preflight as a new browser run or a paid-command verifier pass.

Launching requires independent verification of the revised exact command and
the student's concrete approval under the existing spending workflow. Existing
attempt-1 receipts do not approve a different command. On 1 November the student
authorized five additional percentage points of weekly Codex usage for final
verification and continuation within the existing shared cap. The recovery's
final verifier is a separate Codex reviewer, identified as such in its receipt,
not an asserted Claude review. The initial attempt's verification requirement
is unchanged. No paid continuation is performed by preparing this addendum.
Recreate operational monitoring every **20 minutes**, as requested with that
authorization, when the continuation actually starts. Stop and ask at 90% weekly
Codex usage. Keep answers blinded until the student completes and validates the
review.
