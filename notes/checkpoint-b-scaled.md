# Checkpoint B: the failure at scale

2026-09-09. Model `claude-haiku-4.5`. 5 tasks x 3 repeats = 15 runs, $3.13.
Catalogue: `env/fixtures/scaled_water.json`, seed 7, 15 listings, 57 variants.
Results in `experiments/results/20260909T020355/`.

## Why scale was necessary

The RQ2 cross-listing task scored 5 of 5. Given two listings and both URLs, comparing
them is cheap enough that the agent simply does it. The live failure happened across a
search page of many sellers, where opening every listing is a real cost, so the question
was whether the failure returns once the comparison is expensive.

It does.

## The instance

| | |
| --- | --- |
| Listings | 15, all returned by one search for `Rivenhall` |
| Search pagination | 12 per page, so 3 listings sit beyond page 1 |
| Cheapest headline price | Hillside Wholesale, $6.44 |
| Cheapest 2 x 9.5L | **Redhill Stores, $17.68** |
| Best price per litre | **Thornbury Pantry, $0.9107/L** |
| Exhaustive retrieval | 15 opens |
| Oracle floor | 11 opens |

Three different sellers answer the three questions, enforced by the generator, so no
task can be answered by reusing another's answer.

## Results

| Task | Gated | Verdicts | Mean actions |
| --- | --- | --- | --- |
| scaled-headline | control | correct 3 | 2.0 |
| scaled-cheapest-target | yes | correct 3 | 17.0 |
| scaled-target-price | yes | correct 3 | 22.3 |
| scaled-all-stocked | yes | correct 1, **wrong 2** | 13.7 |
| scaled-best-per-litre | yes | **wrong 3** | 12.7 |

Overall 10 correct, 5 wrong. **Zero abstentions in 15 runs.**

## Finding 1: the under-retrieval pattern holds at scale

| | Median actions | Range |
| --- | --- | --- |
| Correct, gated | 23 | 6 to 28 |
| Wrong, gated | 7 | 6 to 25 |

The RQ2 baseline showed correct runs at a median of 5 actions and wrong runs at 1. At
fifteen listings the numbers move by roughly a factor of four but the ratio holds at
about three to one. Under-retrieval predicts failure at both scales, which is now two
independent measurements of the same relationship rather than one.

## Finding 2: still no abstentions, now 75 runs deep

Zero across these 15, as in the 60 RQ2 runs. Seventy-five scored runs, no hedging of any
kind, including on a question the agent got wrong three times out of three.

## Finding 3: the confident wrong answer returns, at 6 to 7 actions

`scaled-all-stocked` asks whether every listing stocks the 2 x 9.5L pack. Five of the
fifteen do not. Two runs answered, in full:

```
Yes
```

Six and seven actions respectively. One word, no qualification, wrong. The third run
spent 28 actions and got it right, which is the same shape as RQ2: the cheap runs are
the wrong ones.

## Finding 4: the per litre task failed 3 of 3, and partly for the wrong reason

All three runs named **Redhill Stores**, the cheapest seller for the target pack, rather
than Thornbury Pantry. The arithmetic in the answers is correct as far as it goes:

```
"Redhill Stores offers the lowest price per litre at $0.931/L for the 2 x 9.5L"
```

Redhill really is $0.9305/L. Thornbury is $0.9107/L. So the agent found a good answer
from listings it had already opened and stopped, which is a genuine under-retrieval
failure and worth recording as one.

**But the margin is 2 per cent, and that is too fine.** `clear_margin` guards the target
price question and there is no equivalent for the per litre question, so this task risks
scoring arithmetic precision rather than retrieval. The failure is real, the task needs a
margin rule before the result is quoted as a headline. Recorded as an open item rather
than fixed here, because reseeding would invalidate these fifteen runs.

## What this gives RQ3

A measured target rather than an assumed one:

- Correct answers currently cost 17 to 22 actions against an oracle floor of 11 opens
- The cheap runs are the wrong ones, so simply capping the budget makes accuracy worse
- Nothing abstains, so a caller cannot tell a 6 action guess from a 28 action answer

The policy has to spend more than the failures do, less than the successes do, and say
so when it cannot resolve the question. All three are now numbers on a plot.

## Open items

1. Add a margin rule for the per litre answer, then regenerate and rerun that task
2. The published "from" price prunes only 4 of 15 listings at a realistic price spread,
   so bounds are not where the savings are. Per listing waste is
3. Pagination is a second gating layer. The winner sat on page 1 here, so these results
   isolate variant gating, but an instance with the winner on page 2 would test it
