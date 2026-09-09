# RQ2 baseline: unmodified openJiuwen on the seeded environment

2026-09-08. Model `anthropic/claude-haiku-4.5` via OpenRouter. 12 tasks x 5 repeats =
60 runs, $2.98 total. Raw results in `experiments/results/20260908T223116/`.

Task suite in `experiments/tasks.json`, scored against the ground truth in
`env/manifests/` by `experiments/score.py`. Eleven tasks are gated, one is a control
whose answer is on the card.

## Headline

| | |
| --- | --- |
| Overall | 53 correct, 6 wrong, 1 ambiguous of 60 |
| Gated tasks | 48 correct of 55, 87% |
| Control task | 5 of 5, at 1 action per run |
| **Abstentions** | **0 of 60** |

## Finding 1: the agent never signals uncertainty

Zero abstentions in sixty runs. Every failure is a confident assertion. The scorer looks
for a wide set of hedges, "unable to", "could not determine", "insufficient", "unclear",
and none of them ever fired.

This answers the second half of RQ2 directly. The agent does sometimes fail to retrieve
gated information, and when it does it does not say so. There is no uncertainty marker to
act on, which is precisely what makes the failure dangerous downstream.

## Finding 2: correctness falls off a cliff below two actions

Gated runs, bucketed by the number of page-changing actions spent:

| Actions | Runs | Correct | Rate |
| --- | --- | --- | --- |
| 1 | 5 | 1 | **20%** |
| 2-3 | 16 | 16 | 100% |
| 4-6 | 20 | 18 | 90% |
| 7+ | 14 | 13 | 93% |

Correct runs spent a median of 5 actions; wrong runs a median of 1. Four of the seven
failures happened at exactly one action.

The relationship is not "more retrieval is better". Beyond three actions the rate is flat
within noise. It is specifically **under-retrieval** that predicts failure, and the cliff
sits between one action and two.

That is the RQ3 premise stated as a measurement rather than an assumption: there is a
minimum retrieval budget below which answers stop being reliable, and above which extra
interactions buy nothing.

## Finding 3: two distinct failure modes

**Corrected 2026-09-09, see [delta-not-fabrication.md](delta-not-fabrication.md).** This
section originally described the first mode as fabrication. It is not.

**Delta misread as an absolute price.** One action, and a number that is right as a
surcharge and wrong as a price:

```
water-a-9l5-price   1 action   "The price of the 2 x 9.5L pack is $15.01"   truth $24.90
water-b-9l5-price   1 action   "The price of the 2 x 9.5L pack is $11.60"   truth $22.50
```

Magento labels each variant option with a price **delta**. The option reads
`2 x 9.5L +$15.01`, and the traces confirm both runs observed exactly that:

```
9.89 + 15.01 = 24.90     truth 24.90
10.90 + 11.60 = 22.50    truth 22.50
```

Both numbers are correct as deltas. The agent retrieved the right token and misread its
semantics. The original check, that neither number appears in the page source, was itself
correct; the inference from it was wrong. The label is computed in the browser from
`spConfig` rather than written into the HTML, so it lives only in the rendered page,
which is where the agent was looking and where the grep was not.

A third run on the same task shows that composition is the discriminating step:

```
"The price of the 2 x 9.5L pack is $22.50 (base price $10.90 + additional charge $11.60)"
```

Same two numbers observed, correct answer, because it added them. Scored ambiguous only
because the scorer penalises an answer carrying both the target and the trap value, which
is the wrong rule for an answer showing its own working.

**Retrieved but did not report.** `water-a-all-prices` asks for every pack size and price
and failed four times in five, at 5, 6, 7 and 1 actions:

```
"Successfully listed all pack sizes and their prices from the Glenmoor Still Spring Water
 product page."
```

The answer asserts completion and contains no prices. At 5 to 7 actions the retrieval
probably happened and the reporting did not. This is a reporting-contract failure rather
than a retrieval failure and should be counted separately.

## Finding 4: the cross-listing trap did not fire

`water-cross-listing`, the task modelled directly on the deployed-assistant failure,
was correct 5 times out of 5 at a mean of 6.4 actions. The agent opened both listings,
selected the variant on each, and named Hillside Provisions at $22.50.

This is a negative result and it matters. With two listings and an explicit instruction
naming both URLs, the comparison is cheap enough that the agent simply does the work. The
live failure happened over a search results page with many sellers, where opening every
listing is expensive. Reproducing it needs scale, not a better trap.

## What this means for RQ3

The headroom is not correctness. At 87% on gated tasks the unmodified agent is mostly
right. The headroom is that it has no way to know when it has retrieved enough:

- It spends 1 action and misreads, or spends 7 and is right, with no principle
  distinguishing the two beforehand
- Extra actions past three buy nothing measurable, so a large part of current spend is
  waste
- It never abstains, so a caller cannot tell a 1-action guess from a 7-action verification

A question-conditioned policy has four things to beat: eliminate the sub-two-action
answers, cut the cases spending 7+ actions where 2 suffice, check that a reported price is
consistent with any delta label observed, and abstain rather than answer when the budget
genuinely runs out.

## Caveats

- One model. `claude-haiku-4.5` only. Cheaper models could not complete the tasks at all
- Seven failures is a small sample. The 20% rate in the one-action bucket rests on 5 runs
- Headed Chrome, not headless. Kept constant across all 60 runs
- An earlier version of the scorer marked six correct answers wrong because it penalised
  any mention of the alternatives, which is what a good comparison answer does. The rule
  now treats naming the expected option as decisive. Verdicts changed by that fix are
  recorded as `previous_verdict` in `suite.json`
