# Working on this FYP with Codex

Read `OBJECTIVE.md`, `WORKFLOW.md`, `LESSONS.md` and the latest dated handover first. The
original workflow describes Claude modules; use independent coding/review responsibilities
in Codex without claiming that Claude-specific hooks protect Codex tools.

## Research integrity

- Preserve the frozen experiment. `docs/content/claim2-protocol.md` and
  `experiments/tasks/claim2_analysis.json` specify the original design. A new market or
  changed intervention needs its own dated design before drawing/testing it. Do not retune
  after seeing outcomes or pool different markets/models/conditions into one arm.
- As of the 27 October handover, the student's stage-1 hand review is incomplete. Until the
  student confirms it is complete and its CSV is validated, do not read
  `experiments/results/claim2b-stage1.sheet.key.json`,
  `experiments/results/claim2b-stage1.analysis.json`, or
  `experiments/results/claim2b-stage1.second-reader.verdicts.csv`, or otherwise expose arm
  outcomes from raw records. The blind `.sheet.csv` and reading rules are safe to use.
- Never fill AI-generated grades and describe them as an independent human review. Help
  with rules using synthetic examples. After completion, retain human and automatic
  scores separately and report disagreement.
- Ground numbers and citations in evidence. A bibliography key resolving is not a source
  verification. A nonsignificant test is not evidence of no effect.
- Design B combines interaction gating with deliberately false labels. Only the block gets
  a label warning. Its generator selects useful lower bounds and difficult cases. State
  those limits; no prompt-injection defence was evaluated.
- A drafted proposal, posted issue, submitted PR and merged contribution are different
  statuses. Use the verified current status. On 27 October 2026 at 22:36 Singapore time,
  the user's approved proposal was posted and verified as
  [WebArena-Verified issue #60](https://github.com/ServiceNow/webarena-verified/issues/60).
  It is an open proposal issue,
  not a submitted PR or merged contribution.

## Spending and environment

- Paid OpenRouter runs require the user's approval of a concrete command, declared estimate,
  budget stop and an independent verification at the actual code/command. Existing keys are
  not approval. Preserve the user's requested reserve.
- `tools/workbench/igr-workbench` intercepts Claude's `Bash`; it does not intercept Codex
  `exec_command`. Do not bypass this by assuming `IGR_ESTIMATE_USD` is an enforced gate.
  Verify the launch context, watchdog/process control and account checks before spending.
- Never print credentials or `.env` contents. Do not commit credentials, HARs or private
  raw page/session dumps. Do not automate live commercial shopping sites.
- The report directory is local and gitignored. Preserve this; do not force-add it. Back
  up source/PDF before substantial edits. Full MacTeX is under `/Library/TeX/texbin`.

## Current entry points

- Student workflow: `notes/start-here-27-oct.md`.
- Meeting: `notes/meeting-28-oct-brief.md`, `docs/update-28-oct.html`.
- Review tooling: `tools/hand_review.py`; generated local reader in
  `report/hand-review-27-oct.html`. Validation/import reads no arm keys; `--score` explicitly
  unblinds only a completed sheet. Do not regenerate the sheet's random codes.
- Replication: `notes/replication-prep/protocol-draft-27-oct.md` and its draft JSON. These
  are preparation artifacts, not a frozen or launch-ready experiment.
- Audit: `notes/codex-experiment-audit-27-oct.md`. The user confirmed on 27 October that
  **6 November is the first report/full-draft deadline**, not an abstract-only deadline.
  Prepare the full draft by 5 November; confirm the submission time, format and limits.

## Verification and file hygiene

- Preserve existing user changes and the modified `agent/agent-core` submodule. Stage files
  by explicit name; never broadly add the submodule, private report or raw results.
- `make check` is the historical full suite; some tests read historical result files and
  `make mod` depends on Claude. During blinding, inspect test inputs and prefer the relevant
  synthetic suites. Do not use a broad analysis/site rebuild to expose pending outcomes.
- `make facts` covers original clothing cells, not every report figure. Claim outputs and
  reader agreement have their own commands documented in the student guide.
- Record narrow fixes, tests and limitations. Do not call preparation checks a verifier
  pass for a paid run.
