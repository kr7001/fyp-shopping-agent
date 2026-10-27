# Codex experiment audit — 27 October 2026

## Verdict

**Good idea, but needs constraints.** The project has a coherent intervention, versioned conditions, a protocol frozen before its claim market, operational void rules, blind human scoring, and a testable analysis pipeline. Finish the existing blind reading and explain that experiment before allocating the remaining budget. A second market is a useful external-validity improvement within the same generated distribution, but the next paid run is not currently launch-ready.

This audit read the workflow, objective, lessons, handover, frozen protocol/configuration, stage planner/command generator, market-selector/generator, block pipeline documentation and relevant code, analysis preflight/hand-reading paths, and synthetic tests. It did not read `claim2b-stage1.sheet.key.json`, `claim2b-stage1.analysis.json`, or `claim2b-stage1.second-reader.verdicts.csv`, and did not inspect stage-1 arm outcomes. No paid model call, seeding operation, or protocol/intervention edit was performed.

## Evidence that survives self-check

### 1. The Claude spending dialog does not transfer to Codex

`tools/workbench/igr-workbench/hooks/register.js:206` explicitly intercepts `tool.call` for the tool named `Bash`, enabled through `.claude/settings.json`. The declared `IGR_ESTIMATE_USD` and `caffeinate` strings are not by themselves an approval mechanism inside `suite.py`. Codex uses `exec_command`, so a user-facing statement that the old dialog automatically protects this session would be false.

**Action:** require explicit approval of the actual reduced command, independently verify it, and record the estimate/cap before launching. Do not treat presence of the OpenRouter key as approval. A small launcher can enforce the same checks outside any assistant-specific plugin; it is not implemented by this audit.

**Self-check:** the generated chain has separate preflight, account gates and watchdog logic, so the entire budget protection has not disappeared. What does not transfer is the Claude hook's verification/approval interception.

### 2. The current watchdog needs process access unavailable inside this sandbox

`tools/claim2_stage_command.py:157` discovers running suites with `pgrep` and kills those processes. The synthetic budget-watchdog test failed inside the sandbox because `pgrep` returned `sysmond service not found; Cannot get process list`. The invocation completed instead of being killed; the before-next-invocation budget gate still stopped the chain.

A read-only escalated process-list check succeeded normally (no suite process existed), and the exact failing synthetic test then passed outside the sandbox in 2.5 seconds. Thus this is a permissions limitation of the current execution context, not evidence that the watchdog failed in the original Claude experiment.

**Action:** verify process control in the final launch context with this free test. Prefer a watchdog bound to its own child/process group; the present selector can target another matching suite on the machine. Avoid concurrent paid runs. Lost account visibility currently leaves an active invocation running (`u != None` is required before killing), while the next invocation fails closed. Account polling/billing latency means the cap is a best-effort stop rather than a provider-enforced hard guarantee.

### 3. The first-claim picker cannot yet produce the intended second independent seed

`env/generate_aplus.py:1771` fixes `CLAIM_FIRST_SEED=1000`; `claim_record_problem` at line 1812 rejects a new record starting at 1001 and rejects any continuation after an accepted seed. Both rejection cases were reproduced offline. Changing the brand and SKU prefix at fixed seed/attempt returned identical seller and variant data; `draw_b` at line 1492 seeds randomness without the brand.

**Action:** predeclare a separate replication seed stream (proposed start 1001), then narrowly extend the picker to read that configuration while retaining original defaults. Do not reuse seed 1000 under another name and call it independent. Do not manufacture rejection-history entries. A search of recorded fixtures/manifests and project notes found no existing seed-1001 record, but that cannot prove no unrecorded inspection ever occurred.

### 4. No new exact-command verification is ready; the existing shop was restored

The latest verification stamp observed here covers commit `5740908` and the original pilot/stage-1 commands; audit HEAD was `58b9423`. Neither that stamp nor the original command covers this reduced replication. `docker ps` could not connect to the Docker daemon both inside and outside the sandbox. Python, the Playwright virtualenv path, `caffeinate` and Claude CLI are present; credential values were not inspected or printed.

**Action:** restore the shop, check new isolated market state, independently verify the new command at its final commit, and obtain spending approval. Do not claim the run is queued or underway.

**Later readiness update, 27 October:** the parent agent started Docker Desktop and the existing `webarena-shopping` container. The storefront returned HTTP 200; Elasticsearch answered with all seven primary shards active (single-node cluster status yellow). `.venv-naive/bin/python env/check_aplus_market.py --fixture tee_claim.json --no-browser` passed all eight checks for Wexcombe's cards, two-page coverage, prices and recorded order. Output: `report/codex-shop-readiness-27-oct.txt` (local). No new market was seeded and no paid model was called. This resolves the stopped-shop condition, not the need for new-market live checks, fresh command verification or launch safeguards.

### 5. State the scientific claim at the level actually isolated

The protocol already discloses the following; they are constraints on interpretation, not newly discovered proof of invalid data:

- Only the block arms receive the sentence warning that promotional/stock text in labels is not a checked fact (`claim2-protocol.md:418`). H1 on the promo questions partly measures this briefing. The experiment does not isolate a general ability to resist unseen label types.
- The generated market guarantees that bounds can save work and the initial screen can mislead (`claim2-protocol.md:441`). Results generalize to this stress-test distribution. They do not estimate failure prevalence on typical shopping sites.
- The cost comparison includes the plan, briefing and pre-read result pages, not just the branch-and-bound stopping rule (`claim2-protocol.md:443`). Do not claim that the stop rule alone caused all savings.
- Design B makes promotional labels false and scarcity claims untrue (`env/generate_aplus.py:1029` and the B_RULES). It contains no injected instructions, but it is not a clean test containing only truthful benign UI text. Separate the original non-deceptive motivating example from the deliberately misleading-label experiment.
- Three rounds on one market, and two rounds in a replication, leave substantial uncertainty. Human–AI agreement is reader agreement, not ground-truth validation or independent human replication.

**Action:** preserve the pre-registered analyses and state these limits plainly. A balanced briefing/stop-rule ablation is future work unless the supervisor explicitly prioritizes it; do not spend tonight redesigning the study after outcomes exist.

## Concrete replication prepared

See `notes/replication-prep/protocol-draft-27-oct.md` and `analysis-draft-27-oct.json`.

- Three arms, two rounds, 68 scheduled slots; 46 invocations with chunk eight.
- Original H1–H3 question scopes and Holm adjustment over three tests; no H4, new model, or rewording claim.
- Existing pilot-based cost estimator: $16.53 runs + about $0.0123 routing probe, excluding re-runs. Its steeper scaling scenario is $30.80; $20 therefore cannot promise completion.
- Keep a separate market, task set, manifest and blind sheet. Freeze the replication design/selection before drawing it. Preserve stage-1 outcomes and frozen intervention.

The original design contains **227 scheduled question-arm-round slots** in 87 invocations, from 13 templates and 43 rewordings; `198 runs` in the handover is a different operational count. Never interchange requested slots, actual browser executions, retained answers and hand-sheet rows. This audit did not unblind outcomes to reconcile them.

## Verification performed

1. `python3 -m unittest discover -s experiments/tests -p test_claim2_analysis.py`: **109 tests passed** (synthetic protocol/analysis data).
2. `python3 -m unittest discover -s experiments/tests -p test_stage_command.py`: **24 passed, one watchdog test failed inside the sandbox** for the process-access reason above.
3. `python3 -m unittest discover -s experiments/tests -p test_stage_command.py -k stops_a_run_once`, outside the sandbox: **the remaining test passed**. The whole suite was not redundantly re-run.
4. Offline generator checks reproduced the seed-order constraints and same-seed/new-brand identity without generating a new accepted market.
5. `claim.check_protocol` returned no draft-schema problems; `claim.resolve_protocol` accepted the template-only draft design; `stage_plan.stage1_invocations` produced 68 slots/46 invocations. All cost estimates use the existing development-pilot estimator, not stage-1 correctness results or a new API call.

These checks support a preparation plan. They are not an exhaustive proof of all code, a current provider-price check, an empirical accuracy result, or a verifier pass for spending.
