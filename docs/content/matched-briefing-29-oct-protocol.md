# Matched factual briefing study, 29 October 2026

This supplementary study serves RQ3: whether task-specific planning adds value beyond giving an ordinary browser agent the same candidate information and factual shop guidance. It is an exploratory mechanism audit proposed after observing the earlier results. Quenby is an already observed market, not a fresh holdout. The original Wexcombe and Quenby designs, records, verdicts and analyses remain unchanged.

The machine-readable design is `experiments/tasks/matched_briefing_29_oct.json`. Its status becomes `frozen` at the code revision verified before any paid execution. A prepared file, dry run or live-shop check is not paid-launch approval.

## Conditions and scope

1. **Full block:** the existing model-parser block, including normalisation, validation, fallback, question-specific plan and its existing answer-format instructions. The original block and suite source are unchanged. Its rate-plan setting remains `bound`.
2. **Matched factual briefing:** the same browser executor receives the original question, complete candidate URLs and advertised prices in the same sorted order, results-page coverage, factual size-selection/price/availability mechanics, the advertised-price lower-bound fact and the exact label warning. It receives no logical form, task-specific retrieval plan, pruning instruction, stopping instruction or instruction to inspect every listing. It may devise its own policy.

The common inventory is read from rendered results pages, not from fixtures or answer keys. The factual baseline has one fixed prompt template for all questions. Different prompt lengths and parser charges are part of the comparison; this is not a token-matched study. The full block retains its original reporting instructions, so a difference cannot be attributed to the stopping rule alone. This design does not test whether an LLM parser is necessary.

The four original, clear tasks are cheapest available M (`tee-cheapest-target`), cheapest available XS (`tee-xs-price`), the three cheapest available M sellers (`tee-top-3`) and the exact count of listings that can supply M (`tee-count-buyable`). They cover minimum, misleading-label minimum, top-k and full coverage. The count is a control where pruning cannot remove necessary inspections. Selection reflects mechanism coverage on a known task set, not a random sample of shopping questions.

There are two repetitions per task and condition, hence 16 scheduled slots. Both conditions are run freshly. Historical runs are used only to size costs and time. Within each task/repetition the two conditions are adjacent. The first condition alternates over tasks and reverses in repetition two, as enumerated in the JSON. No slot is added or removed because an observed result is favourable, unfavourable or nonsignificant.

## Controlled execution

Use the existing Quenby fixture, tasks, rendered/gated shop and clean-state openJiuwen scaffold. Do not regenerate or retune the market. Use DeepSeek V4 Flash, the recorded fp8 provider-routing policy with fallbacks disabled, the same browser-tool version, 300-step limit and 1,800-second agent clock. Preserve and record the agent revision and patch. The model parser uses the original prompt, temperature and validation. The ordinary executor uses the same browser sampling settings. Record Chrome version as well as browser-tool version.

Use one question per invocation, sequential execution and fresh process/browser state. Each invocation performs its own rendered candidate pre-read. Record pre-read time and browser execution time separately; include actual parser charges in full-block provider cost. A local pre-read is not a free computational operation simply because it has no provider charge.

The wrapper and analysis must identify these new conditions explicitly, with study, protocol hash and schedule-slot metadata. Never relabel the factually briefed condition as the previously tested shipped condition. The control's factual prompt may not inspect task keys, fixture prices, offline answer keys or historical answers.

## Outcomes and analysis fixed before execution

The primary descriptive comparison is the difference in actual product listings opened within each task/repetition. Report all eight pairs and each condition's per-task results. Report provider charges on the same pairs, including parser charges, with unknown charges treated as missing rather than zero. Report pre-read and execution time separately. Product openings must come from the existing log/market-membership counter, not the agent's claimed count.

Correct final answers use the original frozen hand-reading rubric. Prepare a new blind sheet with new codes; preserve full answers, keys and codes. The student reviews it before arm outcomes or automatic verdicts are exposed. Report human verdicts, automatic verdicts and disagreements separately. An unscorable human row is shown in the all-scheduled-slot outcome table and excluded from the assessable correctness denominator, explicitly. If an unreadable/noncommittal distinction is doubtful, retain the original human grade and record the coding caveat rather than silently changing it after unblinding.

No formal significance test, non-inferiority conclusion or statistical stopping rule is planned for these 16 runs. Two repetitions and four templates provide descriptive mechanism evidence, not a broad task distribution. Do not pool these runs with the earlier studies or describe a confidence interval over repeated trials as uncertainty across markets. Inspect plan compliance descriptively after human review, distinguishing recorded actions from statements in the final answer. Do not treat explanation quality as a new primary correctness criterion.

Apply the original operational definitions in `experiments/analysis/voids.py`. Independently audit missing records, failed parser calls and externally interrupted or suspended executions before reading outcomes. Ordinary clock limits, step limits, abstentions and wrong answers remain outcomes unless the frozen technical-void rule applies. A format error with a nonempty final answer is not automatically a technical void. Keep all attempted charges and failure records. There are no automatic retries. A technical void can be replayed at most once only after independent operational audit and approval of an exact recovery command. If incomplete, report the missing slots and reason.

## Interpretation

- If correctness is similar and the block opens fewer listings or costs less, the result supports incremental retrieval efficiency beyond the factual briefing on these tasks.
- If the factual baseline matches or exceeds the block, narrow claims about the necessity of structured planning and describe the simpler alternative.
- If the block is more accurate, attribute that descriptive difference to its remaining planning/reporting package, not to the stopping instruction alone.
- If effects differ by task, report those differences, especially the exact-count control. A median may conceal tasks where the block is more expensive.

The selected generator family, valid-bound assumption, complete supplied candidate scope, single model/scaffold and misleading labels remain limitations. This experiment does not establish ordinary-market representativeness, safe deployment, prompt-injection defence or transfer to another executor.

## Budget and launch gate

The planning estimate is USD4 to USD8, with a proposed USD10 study cap and at least USD20 remaining key allowance. This is a new supplementary budget, not a reopening of the completed replication's USD20 cap. Matching historical full-block and exhaustive invocations cost USD3.751064 and about two browser hours together; they only provide a sizing proxy for the unmeasured baseline. Plan for roughly three to six hours, not a guaranteed completion time.

The proposed latest stop is 12:00 Singapore on 30 October. The dated wrapper retains within-run account polling, conservative spending high-water and remaining-credit low-water checks, per-step wall limits, an inflight reserve, exclusive account locking and cleanup limited to owned process groups. Billing may lag, so a local monitor is not an atomic provider billing cap. It must refuse a new trial without enough time for the whole configured trial allowance. Use a separately verified receipt binding code and exact command, and obtain user approval of that command before spending. Do not reuse or relax the previous run's expired deadline.

If verification cannot finish in time, defer the new study and finish Friday's report using the completed evidence. An unfinished supplementary experiment does not invalidate the completed primary studies.
