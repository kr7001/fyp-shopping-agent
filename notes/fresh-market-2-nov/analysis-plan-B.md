# Study B: matched briefing on the fresh market, analysis plan frozen 2 November 2026

Part of `protocol.md` beside this file, and committed with it before the market is drawn.

## Question

The 29 October question, on a market neither arm was tuned on: does the full block's
task-specific planning add value beyond giving the same openJiuwen executor the same
candidates and factual shop guidance? The 29 October study (`docs/content/matched-briefing-29-oct-protocol.md`,
`experiments/tasks/matched_briefing_29_oct.json`) ran on Quenby only.

## Condition identity: the 29 October study, unchanged

| Component | Held exactly as on 29 October |
| --- | --- |
| Study runner | `experiments/runners/matched_briefing.py` byte-identical to commit `afba41b` (SHA-256 `735ecdf4ef00df529e58ece8d0b8caf767d6fc1a4b1049b9b9c7e873f026841d`), so the factual briefing (`SHOP_FACTS`, the candidate preamble, the label warning) and the full block's text come from the same code; only the study identity it stamps is set from outside |
| Suite and executor runner | `experiments/runners/suite.py` (SHA-256 `961e4430f1eecf62b7e70d559f9f0b5dcefd0c4e2a8ce19ef150b16f7015f0c7`) and `experiments/runners/run_browser_task.py` (`7c4d91d37480bcf28c7cac3a071cbf58796dfe960e2b6cc6f176153be88916a2`), with every `experiments/box/*.py` file as bound on 29 October |
| Agent | openJiuwen `agent/agent-core` at commit `18d45d6e90d3735ef72c1ee9ad2467821212f7db` with the same working-tree patch (`git diff --binary HEAD` SHA-256 `a3f4c0c43cf8567f8e6a6936d48f39b5c51ac7573a3baa565a178be86f54fea9`); Playwright MCP browser tool 0.0.83, origins `http://localhost:7770`, flags `--block-service-workers --isolated`; gated shop; viewport card probe |
| Model and sampling | `deepseek/deepseek-v4-flash` for executor and parser; provider order GMICloud, DeepInfra, StreamLake, fp8, no fallbacks; the executor's sampling variables unset as on 29 October; parser temperature 0, prompt v4, normalisation v5 |
| Block | box v20, form v15, primitives v13, targeting v9, planner v2; model parser; rendered page reader; rate plan bound; reading own |
| Limits | 300 steps and 1800 s per trial; one question per invocation; fresh process and browser state; sequential |
| Tasks | the four 29 October templates as generated for the fresh market: tee-cheapest-target (cheapest M), tee-xs-price (cheapest XS), tee-top-3 (three cheapest M), tee-count-buyable (count of listings that can supply M) |
| Conditions | full block (`box-model`) and matched factual briefing (`matched-briefing`) |
| Schedule | two repeats, 16 slots, in the 29 October order slot for slot: 1 block, 2 briefing on tee-cheapest-target r1; 3 briefing, 4 block on tee-xs-price r1; 5 block, 6 briefing on tee-top-3 r1; 7 briefing, 8 block on tee-count-buyable r1; 9 briefing, 10 block on tee-cheapest-target r2; 11 block, 12 briefing on tee-xs-price r2; 13 briefing, 14 block on tee-top-3 r2; 15 block, 16 briefing on tee-count-buyable r2 |
| Launcher | the matched-briefing launcher on the replication guard: a live market check before the first trial, account polling, a spending high-water mark, owned process groups, an absolute deadline, no automatic retry, and offline blind-sheet preparation after the last trial |

What differs, and only this: the market; the study identity `matched-briefing-fresh-2026-11-02`
and its analysis file `experiments/tasks/matched_briefing_2_nov.json`, whose schedule,
`require` and `arm_require` blocks are copied from the 29 October file and whose inputs are
the fresh market's; a USD 2 cap with a USD 0.50 in-flight reserve; the deadline; and the
Chrome build (156.0.8078.79 here, 156.0.8078.49 on 29 October), recorded in the manifest.

## Outcomes and analysis, as on 29 October

- **Primary, descriptive.** Per task and repeat, the difference in product listings opened,
  from the frozen log and market-membership counter, never an answer's own claim. All eight
  pairs and each condition's per-task results are reported.
- Provider charges on the same pairs, the parser's included, an unknown charge kept as
  unknown. Pre-read time and browser execution time separately.
- **Correctness:** the student's blind grade under the frozen hand-reading rubric
  (`docs/content/claim2-reading-rules.md`), on a new sheet with new codes, reviewed before arm
  outcomes or automatic verdicts are seen. Automatic verdicts separately, and every
  disagreement listed. An unscorable row stays in the all-slots table and leaves the
  assessable denominator, explicitly.
- No significance test, no non-inferiority conclusion and no statistical stopping rule.
- Plan compliance is described after the human review, recorded actions kept apart from what
  the final answer says.
- Technical voids by the frozen rules of `experiments/analysis/voids.py`, read before any
  outcome; voids are left out with their charges kept. Ordinary clock limits, step limits,
  abstentions and wrong answers are outcomes. No automatic retry.
- The reader is `experiments/analysis/matched_briefing_analysis.py`: `--check-manifest`
  during the run, `--sheet` once after it, `--hand` only on a completed sheet.

## Reporting rules fixed before the 29 October launch, applied unchanged

From `notes/replication-prep/matched-briefing-pre-unblinding-note-29-oct.md`:

1. A slot the full block closes counts as not correct and stays in the denominator. Its count
   is reported separately, and its pair's opening, cost and time differences are reported as
   not comparable, not as 0 openings.
2. On tee-count-buyable the briefing gives more availability facts than the block's text for
   that task. If the briefing equals or beats the block there, that is not evidence against
   planning.
3. No small difference is called a difference. Each task has two runs per condition: a
   per-task difference of one correct answer or less is reported as "no observable
   difference". Totals over the eight runs per condition are exact counts with no
   significance claim.
4. The comparison is the plan with its reporting rules, not planning alone. An accuracy gap
   is credited to the plan and reporting package together.
5. Integrity check after the runs and before unblinding: all 16 slots carry the same
   `preamble_sha256`, the same 45-listing briefing. The result is recorded before the
   student opens the blind sheet.

Also as reported on 29 October: the frozen counter measures product-page navigation only. Any
product document an agent fetched through JavaScript is looked for in the run logs and
reported beside the count, never merged into it.

## Interpretation, as on 29 October

- Similar correctness with fewer openings or lower charges for the block supports retrieval
  efficiency beyond the factual briefing on these tasks.
- If the briefing matches or beats the block, claims that structured planning is necessary
  are narrowed and the simpler alternative is described.
- A more accurate block is credited to its planning and reporting package, not to the
  stopping instruction alone.
- Effects that differ by task are reported by task; a median may hide a task where the block
  costs more.

The fresh market is reported on its own, beside the 29 October Quenby result and never pooled
with it into one figure. One market from one generator family, one model and one executor:
no claim beyond them.
