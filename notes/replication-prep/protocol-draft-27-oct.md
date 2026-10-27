# Replication preparation — 27 October 2026 (DRAFT)

This is a reviewable preparation plan, not a frozen protocol or a command to spend money. The original stage-1 protocol and results are unchanged. No new market has been drawn, no shop has been changed, and no API call has been made by this preparation.

## Proposed question

Does the frozen design-B block retain its accuracy/cost pattern on another independently drawn market from the same deliberately constrained generator distribution? This is a second-market replication, not evidence about arbitrary products, live stores, another model family, or naturally occurring rates of misleading labels.

## Intervention and design

Keep the frozen block (box 20, form 15, primitives 13, model prompt 4, normalisation 5, targeting 9, planner 2), DeepSeek V4 Flash, routing, rendered-page reader, one clarification maximum, scripted shopper policy, browser/agent patches, sampling, 300 steps and 1,800-second clock. Do not retune on the new market. Preserve the 45-listing, six-size design-B generator and rejection criteria.

Use three arms in two rounds, with arm order rotated as in the original stage plan:

| Arm | Questions per round | Total requested slots |
| --- | ---: | ---: |
| Shipped | 13 templates | 26 |
| Open everything | 8 gated templates | 16 |
| Block, model parser | 13 templates | 26 |
| Total | 34 | 68 |

No rules-parser arm, held-out rewordings, Haiku run, or text-only reading test. The reduced design asks H1 (correctness versus shipped), H2 (listings opened versus exhaustive), and H3 (cost versus exhaustive), using their original question sets and definitions, with Holm across these three tests. Do not claim a replicated H4/model-versus-rules result. Retain the original sensitivity checks that apply. Report the results separately from stage 1; never pool markets into a single arm without an additional declared cross-market analysis.

`analysis-draft-27-oct.json` is the machine-readable draft. It passes `claim.check_protocol` and resolves against a template-only version of the original task schema. That validates the draft's structure; it does not verify a new shop or authorize a run.

Use the original blind-reading rules and retain automatic scoring beside human scoring. Generate a new random-code sheet for this replication only. The existing 40-row second-reader rule fits a completed 56-keyed-answer maximum, but any shortfall must be handled transparently. Two rounds offer limited power; emphasize effects by question and uncertainty. An inconclusive p-value is not evidence of equivalence.

## Market selection must be fixed before drawing

A new brand alone is not a new market. `draw_b` seeds its random stream from the seed and attempt, not the brand. A direct offline check found identical seller/variant data after changing only the brand and SKU prefix at the same seed and attempt.

The current picker is specific to the first claim: every new search begins at seed 1000, and an accepted search cannot continue. It rejects a fresh record beginning at 1001. Do not falsify a rejected-seed record or change the original frozen protocol to make a second market fit.

Proposed narrow amendment: add an explicit replication-selection configuration with a fresh, fixed start seed of 1001, a separate protocol path and separate fixture/search log. The default original-claim behavior must remain 1000. Validate that 1001 has not already been inspected/tuned on, record the complete stream of candidates and acceptance, use the first candidate meeting the unchanged design-B checks, and preserve the original Wexcombe market. If another seed has been inspected already, document that fact and predeclare the replacement rule before generation.

Use a new brand selected by a recorded first-free check and a new SKU prefix, fixture, task file, search log, result tag and manifest. Check all of them against existing fixtures before seeding. No concrete brand is frozen by this draft.

Generation can be slow: the generator documents millions of rejected draws and searches up to 24 million attempts, in deterministic blocks. Do not bypass rejection rules or select a more convenient market after seeing outcomes.

## Cost and time

The existing estimate model, applied to this exact reduced design and a 45-listing fixture, gives:

| Item | Estimated USD |
| --- | ---: |
| Shipped, 26 slots | 3.97 |
| Open everything, 16 slots | 9.78 |
| Block/model, 26 slots | 2.77 |
| Runs subtotal | 16.53 |
| Existing routing probe | 0.0123 |

These are **estimates from the repository's 23 October pilot cost model**, not new measured run charges or current provider quotes. They exclude re-runs. The same estimator's steeper, quadratic listing-scaling scenario is $30.80 before extras. Thus $20 is a proposed stop budget, not a promise of completion. Re-estimate after stage-1 blind review is locked using operational charges only, and verify current account credit before final approval. At the user-reported $74.75 balance, a $20 batch leaves $54.75, above the requested $20 reserve; that balance has not been checked live here.

With the default chunk of eight, this is 46 invocations. Smaller block invocations improve budget-stop granularity without changing assigned questions. Any chunk change belongs in the final run command and verification. The handover says stage 1 took 19 hours for 198 runs; proportional scaling would be 6.5 hours, but the reduced mix omits many cheap slots, generation adds time, and provider latency varies. Allow an overnight window plus recovery time, not a guaranteed pre-meeting result.

## Launch checklist and order

1. Lock the student's stage-1 hand reading before showing arm results. Use tomorrow's meeting to settle whether a replication is the best use of the remaining time and budget.
2. Review and freeze this reduced design and the new seed-selection rule, dated before generating a new market. Commit its protocol and separate analysis file. This is an extension, not a retrospective edit to stage 1.
3. Make and test only the market-selector and launch-safety changes required below. Preserve frozen intervention bytes/versions. A different intervention version would be a new experiment, not this replication.
4. Confirm the shop and the new market. Docker was initially unavailable; later on 27 October the existing shop was restarted and Wexcombe passed eight read-only `--no-browser` checks (recorded in `report/codex-shop-readiness-27-oct.txt`). No new market has been seeded. Check the new brand, seed the new isolated market and run the full `env/check_aplus_market.py` under `.venv-naive/bin/python`. Retain its record and the complete seed-search record.
5. Generate the new task file and keys from the new fixture, with the original template wording and **without adding rewordings**. Keep the answer keys away from the agent. Check counts, limits, version requirements and all arms with the new task path included in each preflight.
6. Generate the exact command text from the separate replication analysis. Do not copy the old stage-1 command: it requests four arms and text-only reading tests. In the existing generator, `--reading-files` with no values removes those probes, but the emitted script still needs the launcher checks below. Have an independent verifier dry-run the final chain with stubs and check its exact hash.
7. Obtain a fresh verifier pass at the exact committed code and final command. The existing stamp is for commit `5740908` and the original pilot/stage-1 commands; this audit began at `58b9423`. It cannot verify this replication.
8. Present the final run count, estimate, cap, expected duration and account reserve for the student's explicit spending approval. Run under `caffeinate -i`, plugged into power, with no other paid run using the account.
9. Classify voids by the existing technical rule before reading outcomes, re-run at most once within the declared budget, and record incomplete slots rather than silently changing the design. Verify the output, cost and providers; produce the separate blind review sheet; score only after it is filled.

## Launch-safety requirements for Codex

The free watchdog kill test passes outside the sandbox, but fails inside it because `pgrep` cannot read the process list. The final launch context must support the verified process-control path.

The existing workbench guard is a Claude plugin that intercepts the tool named `Bash`. It does **not** automatically intercept Codex's `exec_command`, and the runners themselves do not enforce that approval flow. A dialog or protection inherited from Claude must not be promised in Codex.

Before launching in Codex, use an explicit command-specific approval plus an independently verified launcher that:

- checks the expected commit, experiment-code cleanliness, actual agent-core patch, browser/tool versions and final command hash;
- refuses an existing result tag/manifest, unless running a separately reviewed resume plan;
- binds its watchdog to its own process group, not every `suite.py` process on the machine;
- stops its active invocation on lost budget visibility, and stops the chain on a nonzero subprocess exit or missing batch output;
- applies budget checks to routing probes, browser runs, re-runs and any optional probes;
- records the run status and safe metadata without printing secrets.

The current chain's account-based watchdog polls every 20 seconds and relies on possibly delayed account billing. It is a best-effort spending stop, not a provider-enforced hard cap: an in-flight request can still settle after stopping. Use a conservative margin and state that residual risk before approval. No new guard implementation is claimed by this draft.
