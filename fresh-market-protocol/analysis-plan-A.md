# Study A: Browser Use transfer on the fresh market, analysis plan frozen 2 November 2026

Part of `protocol.md` beside this file, and committed with it before the market is drawn.

## Question

In front of Browser Use, does the unchanged block change how often the agent's final answer
is correct, on a market that neither the block nor this agent setup was tuned on? The eight
question types are the ones the earlier Browser Use studies asked on Quenby.

## Condition identity: the repeats 2-3 cohort, exactly

The reference is that cohort's continuation command,
`notes/browser-use-repeat-1-nov/attempt2-complete-1-nov/attempt2-command.json`, SHA-256
`d92255c29e88f96631126c647bf67fdefb94276c7db255ed17a2331418d92d8d`, run at commit
`966e711a49660893edc93b6d34306df4f458df97` (its first attempt, SHA-256
`2a1b0ec9f9a58e047fed80680b03252a30a2c8d2f9594381f9c32257e762d700`, has the same settings).
The launcher compares every row below with that command before any paid call, by value, by
file hash, or for the agent-facing functions by the hash of their source text, and refuses to
start on any difference.

| Component | Held exactly as in the cohort |
| --- | --- |
| Executor and parser | `deepseek/deepseek-v4-flash`; executor temperature 0.2, frequency penalty 0.1, top-p unset; parser temperature 0 with the frozen prompt, normalisation and fallback |
| Provider routing | order GMICloud, DeepInfra, StreamLake; fp8; no fallbacks; price ceilings 0.2 prompt and 0.5 completion per million tokens, no request fee; only those three may serve |
| Framework | Browser Use 0.13.14; dependency lock `experiments/browser-use-macos-py311.lock.txt` (SHA-256 `e2d5b84a77fff7d4aa7a45e187e66cfb34fecbccd817c2c003966749e0428e27`); the same Python environment and Chrome executable; Chrome build 156.0.8078.79 |
| Adapter | `experiments/runners/browser_use_runner.py` byte-identical (SHA-256 `cfcd3f71c3e53c5c9fa855fd2e4c205ee6813ee0a62e5ba56dcf3c733b3fac1f`): native tools without upload and screenshot, the disabled-option checks, fresh local scope for page scripts, loopback-proxy network confinement |
| Host | text only, a fresh browser profile per trial, viewport 1280x720, the gated user agent, service workers blocked, the same first navigation; thinking, planning and message compaction on, judge off, five actions per step |
| Limits | 150 steps, 5 consecutive failures, 2700 s per trial, LLM timeout 120 s, step timeout 180 s, 200000 input bytes, 4096 output tokens, maximum-input-token reservation 1048576 |
| Block and briefing | every `experiments/box/*.py` and `experiments/paths.py` byte-identical to the cohort's hashes; the rendered results-page reader; the same common label warning (`primitives.LABEL_NOTE`) before the question in both arms; the block's planning text, from `box.decide(question, page, parser="model", rate="bound")`, in the block arm only |
| Agent-facing code | `build_query`, `read_observation`, `schedule`, `validate_questions`, `validate_observation` and the common warning in `experiments/runners/browser_use_transfer.py` unchanged from `966e711` |

What changes, and only this: the market and its eight generated questions; repeat numbers
1 and 2 instead of 2 and 3; the study's identity, budget, cap, output paths and deadline;
and one passive measurement, described below, that the agent cannot see.

## Questions and schedule

The question types, in this order: tee-target-price, tee-cheapest-target,
tee-count-buyable, tee-exists-under, tee-top-3, tee-xs-price, tee-promo-check,
tee-headline. Their wording is exactly what `env/generate_aplus_tasks.py` writes for the
fresh market, the shop's address filled in. The agent and the block receive only
`{id, query, start_url}`: no key, fixture or `_instance`.

2 arms x 8 questions x 2 repeats = 32 slots, scheduled by
`browser_use_transfer.schedule(questions, (1, 2))`: the two arms of a question are
adjacent, the first arm alternates over the questions, and repeat 2 reverses repeat 1. The
order is fixed, not randomised. No slot is added, dropped, moved or replayed because of an
outcome.

## Outcomes

- **Correctness**, the verdict of record: the student's blind grade of the final answer under
  the frozen reading rules (`docs/content/claim2-reading-rules.md`), against the key in the
  fresh task file, or its readings sidecar for the run's reading. Rows carry random codes;
  arm, repeat, cost and automatic verdict are hidden, though an answer's style may still hint
  at its arm. The completed sheet is validated before anything is unblinded.
- **Disposition** of every slot: answered; failed (the agent produced no final answer);
  timeout (the 2700 s trial clock); closed by the block; technical void; not started.
- A **technical void** is a failure that is not the agent's: a record whose error the
  launcher's frozen classification (`browser_use_transfer.validate_pilot_record`) treats as
  infrastructure or unknown, which stops the batch; or a slot the guard interrupted (budget,
  deadline, suspension, page reader, browser build).

## Primary test, the only one

- **Hypotheses.** H0: within each question type, the probability of a correct answer does not
  depend on the arm. H1, two-sided: it does.
- **Test.** `compare_cells.stratified_exact(strata)`, one stratum per question type, each
  `(block correct, block trials, baseline correct, baseline trials)`. Within a stratum the
  block's correct count is hypergeometric given the stratum's total correct; the statistic
  is its sum over strata; two-sided in Fisher's sense, the probability of every outcome no
  more likely than the one observed.
- **Decision.** Alpha 0.05, two-sided: a difference is claimed only if p < 0.05, in the
  direction of the arms' total correct counts. The p-value is reported however it falls.
- **Slots in the test.** Every slot in which the agent ran: answered, failed, timeout and
  closed by the block. A slot counts 1 only when the student graded it correct. Not correct,
  unscorable, no final answer, timeout and closure count 0. Technical voids and slots not
  started are left out and listed with their reason; if any is left out, the test runs on
  the rest and is reported as incomplete against the 32-slot plan.
- **Assumptions.** (1) One binary outcome per trial. (2) Under H0 the arm labels are
  exchangeable within a question type, given that question's number of correct answers.
  (3) Trials are independent given question and arm: each has a fresh browser profile and a
  fresh agent, and sampling is stochastic at temperature 0.2. (4) The arm order is balanced
  but fixed, so the test assumes order has no effect. (5) The two repeats of a question are
  two attempts at one shopping problem, so the evidence concerns these eight questions on
  this market under this configuration, not a population of questions, markets, models or
  agents. A stratum where all its trials agree carries no information. With two trials per
  arm per question the test has little power, and a non-significant result is not evidence
  that the arms are equivalent.
- **Sensitivity**, declared now and not a second primary: the same test with unscorable
  answers left out instead of counted 0.
- No other hypothesis test, no multiplicity family, no added repeats, and no decision to stop
  or continue on any result.

## Descriptive results

Every one of the 32 slots, and per question pair (block minus baseline) and per arm: human
verdict; automatic score v10 and every disagreement with the human verdict; disposition;
provider charge, the sum of every call's charge including parser calls, an unknown charge
kept unknown; the parser's share; product listings opened by navigation, from the cohort's
validated counter (unique candidate URLs reached as main-frame product documents); product
pages fetched by script (below); steps; elapsed time including the page read and parsing.
Counts of pairs where the block opened fewer, as many or more listings, and cost less, the
same or more. Medians. Repeats 1 and 2 shown separately. Correctness sits beside charge and
openings; there is no "correct answers only" efficiency headline.

## Product pages fetched by script, a new descriptive measure

The cohort's counter counts main-frame navigations only, and the 29 October report found an
agent fetching every product page through JavaScript instead. This study adds one passive
listener, identical in both arms, on the same browser context: every response for one of the
results page's candidate URLs that arrives by `fetch` or `XMLHttpRequest`, or as a document
in a subframe, is recorded with its status and whether its body is a product page. It is
reported as its own count beside the navigation count, never added to it and never used in
the test. It sends nothing to the page, and the agent neither sees it nor gets anything from
it. Its errors are kept apart from the navigation counter's, so it cannot invalidate a trial.

## Not claimed

No pooling with the Quenby trials or any other study. No claim about other agents, models,
markets or market generators. Openings and charges are descriptive, and Browser Use's
openings are not compared with openJiuwen's.
