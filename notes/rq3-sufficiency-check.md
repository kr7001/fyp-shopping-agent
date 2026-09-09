# RQ3 first slice: a sufficiency check, validated before integration

2026-09-09. `experiments/sufficiency.py`. No API spend.

## Method note

The check was built and evaluated **offline against the 82 recorded runs** before any of
it was wired into the agent. Integration costs money and time; replaying a check over
traces already on disk costs neither, and it answers the only question that matters
first: does the signal separate right answers from wrong ones?

It did not, on the first attempt. That is the point of doing it in this order.

## Rules

Three tests, all reading only what a run already observed, so none costs a page fetch.
That constraint is deliberate: this is meant to run inside the agent immediately before
it answers, where the budget for checking is close to zero.

**delta_as_absolute.** Magento labels variant options with a surcharge, `2 x 9.5L +$15.01`
against a $9.89 base. A figure that appears among the observed deltas but never as an
observed total is a surcharge being reported as a price. See
[delta-not-fabrication.md](delta-not-fabrication.md).

**unsupported_number.** The asserted amount appears nowhere in the run's observations.

**claim_without_content.** The answer announces a completed list and contains no figures.

## Result over the 82 recorded runs

| Scored verdict | Flag | Runs |
| --- | --- | --- |
| correct | clean | 69 |
| wrong | claim_without_content | 4 |
| wrong | delta_as_absolute | 2 |
| wrong | unsupported_number | 2 |
| wrong | clean | 4 |
| ambiguous | clean | 1 |

**Caught 8 of 13 wrong runs. Zero false flags across 69 correct runs.**

Precision matters more than recall here. A check that blocks correct answers makes the
agent worse, and would have to be argued for. One that never blocks a correct answer can
be adopted on its own terms, and improved on recall later.

## Two iterations, both instructive

The first version scored 5 of 13 caught and **22 of 69 correct runs false-flagged**, a
32% false-flag rate. Unusable. Two distinct causes, both visible only by reading the
false-flagged answers:

Correct answers that state their own arithmetic were being punished for it:

```
"Redhill Stores at $17.68 (base price $6.82 + pack upgrade $10.86)"
```

$10.86 is a delta and appears nowhere as a total, so the rule fired, on an answer doing
exactly what the check exists to encourage. Fixed by detecting a visible sum among the
claimed figures and treating it as evidence of correct composition.

Derived rates were being treated as unobserved:

```
"500g is the best value per kilogram at $29.80/kg"
```

$29.80/kg is computed and correctly absent from the page. Fixed by excluding figures
carrying a per-unit denominator, plus a stated `RATE_CEILING` for cases where the unit is
phrased loosely. The ceiling is a domain assumption and is written down as one.

## What is still uncaught

Four wrong runs pass clean, and all four are non-numeric:

```
scaled-all-stocked   "Yes"        x3    truth: 5 of 15 listings do not stock it
scaled-best-per-litre  names the wrong seller, no checkable figure
```

These need a fourth rule of a different kind: a universal claim, "every listing stocks
it", is only supportable if the run observed every listing. That is a coverage test
rather than a consistency test, and it needs the count of results on the search page
against the count of listings actually opened. Both are recoverable from the trace. Next
slice.

## Where this goes in the agent

`service.py:1713`, the `if parsed_ok:` branch immediately before a successful response is
returned, is where an answer is accepted. A rail attached there can run these tests and,
on a flag, return openJiuwen's existing `blocked` state rather than the answer.

The architecture already supports this. Goal Mode defines
`Phi_t in {continue, complete, blocked}`, and `blocked` means the task cannot be completed
on its merits, distinct from running out of budget. Across 82 runs the browser agent
reached it zero times. See [openjiuwen-architecture-review.md](openjiuwen-architecture-review.md).

## Honest limits

- 13 wrong runs is a small denominator. 8 of 13 is indicative, not a rate to quote
- Both delta catches come from one gating mechanism on one platform. Whether the pattern
  generalises beyond Magento's surcharge labelling is untested
- The check is evaluated on the same runs that motivated its rules, so it is fitted to
  them. The real test is a held-out run against the modified agent
