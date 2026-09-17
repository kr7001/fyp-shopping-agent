# Held-out test: a market the policy has never seen

2026-09-10. 8 runs, $2.62, four gated questions, two repeats, targeting plus gate.
Results in `experiments/results/20260910T133605/`.

Everything measured before this was in sample. The strategies were written against one
generated market and corrected twice after watching them fail on it, so the figures were
fitted to the failures they were designed to fix.

## What makes it held out

A **second market**, generated with a different seed and brand, seeded alongside the first
rather than replacing it. The original fixture stays intact, so every recorded run remains
scoreable against the manifest it was made under. Regenerating in place would have
destroyed that.

| | Development market | Held-out market |
| --- | --- | --- |
| Brand | Rivenhall | **Calderwood** |
| Winner, cheapest 2 x 9.5L | Redhill Stores, $17.68 | **Bramley Trading, $17.36** |
| Cheapest advertised, the trap | Hillside, $6.44 | **Chandler Direct, $5.54** |
| Best per litre | Thornbury, 6 x 1.25L | **Oakfield Pantry, 24 x 350ml** |

Same structural guarantees, oracle floor 11 and 4 prunable, different answers throughout.
The per-litre winner here does not stock the target pack at all, which is a structure the
policy had never met. No line of the policy was written or changed with reference to this
market.

## The result

```
8 runs   7 correct   1 refused   0 wrong   15.1 actions   $0.328 per run
```

Against the development market's 12 runs at 10 correct, 2 refused, 0 wrong, 18.4 actions
and $0.382 per run.

**The property that transfers is the one that matters: no wrong answers.** Sixteen of
sixteen answers across both markets are either correct or refused. The single refusal here
is a "Yes" to the universal question after opening 10 of 15, flagged
`unverified_universal`, which is the rule working rather than failing.

## What could not be claimed from this, until 17 September

There was **no exhaustive arm on the held-out market**, so the 35 per cent interaction
saving measured on the development market was not established here. 15.1 actions is lower
than the development market's 18.4, but without an exhaustive run on Calderwood there was
nothing to divide it by. Stating a saving would have been borrowing a denominator from a
different market, which is the error this project has now made three times in other forms.

That run was the first call on the faculty credit, and it is recorded in the next section.

## The fix this run forced

Two of the three original refusals were **wrong, and the fault was mine.** Both per-litre
answers were correct, matching ground truth to four decimal places and showing their
working:

```
Oakfield Pantry, $0.8298 per litre for the 24 x 350ml pack (8.4 litres total).
$6.97 total / 8.4 litres = $0.8298 per litre.
```

The check flagged `unsupported_number` on `$8.40`, which is not money. It is **8.4 litres**.
The money patterns could not tell a quantity from a price, so a correct answer was refused
for showing its units.

This is the same family as the delta misread that started the project, a number meaning
something other than money, this time in my own checker rather than the agent's answer.
Added a quantity pattern: a decimal followed by a unit is a measurement, not an amount.

With the fix the held-out result is 7 correct, 1 refused, 0 wrong, and the gate's only
remaining refusals of correct answers across every recorded run are the four
`refutation_without_evidence` cases, all of which answered with no evidence at all.

**Worth stating plainly: this correction was only possible because the answers were
checked rather than counted.** Reported as three refusals, the run would have read as the
policy being appropriately cautious on unfamiliar ground. It was two thirds a bug.

## The missing arms, 17 September

Faculty credit approved, and the first thing it bought was the two arms this market
lacked. 27 runs, $8.55, same draw `Calderwood:95cc00c4ca`, results in
`experiments/results/20260917T115725` and `20260917T121222`.

The unmodified arm was never run here either, which the note above did not say plainly
enough: until today the held-out market had **one** arm, so there was no baseline to
improve on and no ceiling to be cheaper than.

### Two findings that change what the earlier numbers meant

**The unmodified baseline was flattered by the development market.** Rivenhall 21 of 36,
58 per cent. Calderwood **3 of 12, 25 per cent**. Same questions, same model, same
structure, a different draw.

The reason is visible in the traces. On Rivenhall the cheapest seller for the target pack,
Redhill Stores, sits in the first four cards, so a four-card read gets the price questions
right by luck. On Calderwood the winner, Bramley Trading, does not, and the four-card read
is wrong every time. The development figure was measuring where the winner happened to
sit as much as it was measuring the agent.

**Coverage separates the verdicts perfectly on this market**, which it did not on
Rivenhall:

| Listings opened | Runs | Correct |
| --- | --- | --- |
| 4 | 9 | **0** |
| 12 to 15 | 3 | **3** |

Four is the number of cards `browser_probe_cards` returns in a 1200 x 701 viewport. Nine
failures, one cause. On Rivenhall the same table reads 4, 4, 14, 15, 15, 15, 15, 15, 15 for
correct answers against 4 for every wrong one, which is why coverage gating was left open
there. Here it is unambiguous.

### Exhaustive retrieval is not a ceiling

| | Rivenhall | Calderwood |
| --- | --- | --- |
| Runs | 8 | 12 |
| Correct | 8 | 10 |
| Wrong | 0 | **1** |
| No answer | 0 | **1** |
| Actions | 28.4 | 28.4 |
| Cost per run | $0.568 | $0.564 |

The wrong one opened all fifteen listings and still answered "Oakfield Pantry at $5.75",
which is Oakfield's advertised from-price rather than its price for the pack asked about.
An attribution error, not a coverage error, and the gate does not catch it because $5.75
genuinely appears on the page. This is the failure `QUARANTINE` was written for in
`experiments/targeting.py`, occurring in the arm that has no strategy text to quarantine.

The run that produced no answer hit the 100-step limit at 99 tool calls and $1.008, the
most expensive single run on record. Its trace is the interesting one: 18 clicks and **10
`browser_select_option` calls**, so it was doing the thing the environment is supposed to
force, and ran out of budget doing it.

### The gate transfers worse than the policy does

Wrong answers withdrawn by the frozen rules, replayed free:

| Market | Withdrawn | Correct withheld |
| --- | --- | --- |
| small | 5 of 7 | 2 of 58 |
| Rivenhall | 11 of 15 | 1 of 30 |
| **Calderwood** | **3 of 9** | **0 of 6** |

The six it misses are all one shape: a market-wide superlative asserted after opening four
listings of fifteen. Only `understated_population` fires, and only once. The rule that
would catch them is that a superlative over a population requires the enumeration to cover
that population, which is a statement about the question rather than about these six runs.
Writing it against these runs would make Calderwood a development market and cost the
held-out claim, so it should be written from the principle and frozen before the next
market exists.

### The saving, now that there is something to divide by

The policy arm was topped up from 8 runs to 12 so that every arm has the same denominator.
The four new runs were **4 of 4 correct**, one per gated question, and the classifier chose
`total_bound`, `total_bound`, `refutation` and `rate_bound`, which is what it should choose.

| Arm | Runs | Correct | Refused | Wrong | No answer | Actions | Cost/run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Unmodified | 12 | 3 | 0 | 9 | 0 | 10.2 | $0.137 |
| Unmodified + frozen gate | 12 | 3 | 3 | 6 | 0 | 10.2 | $0.137 |
| Exhaustive | 12 | 10 | 0 | 1 | 1 | 28.4 | $0.564 |
| **Targeting + gate** | 12 | **11** | 1 | **0** | 0 | **14.8** | **$0.335** |

**48 per cent fewer actions and 41 per cent less money than exhaustive retrieval, at better
accuracy: 11 of 11 answered correctly against 10 of 11.** In sample the same comparison was
35 per cent and 33 per cent at equal accuracy, so both the saving and the accuracy gap are
larger on the market the policy had never seen. The arm is also 2.4 times the unmodified
agent's cost, which is what the accuracy is bought with.

The direction is worth stating carefully. The policy does not beat exhaustive retrieval by
retrieving better inside a listing; it beats it by opening the listings that matter and
stopping, which leaves budget that exhaustive spends on listings that cannot change the
answer, and leaves fewer chances to misattribute a number along the way.

### How often the variant is actually selected

Counted from `trace.by_tool` over every recorded run, because the environment's gate is
weaker than the live marketplace's and it is better to say so with a number:

| Market | Arm | Runs | Selected a variant |
| --- | --- | --- | --- |
| Calderwood | unmodified | 15 | 0 |
| Calderwood | targeting | 8 | 0 |
| Calderwood | exhaustive | 12 | 4 |
| Rivenhall | unmodified | 69 | 2 |
| Rivenhall | targeting | 35 | 5 |
| Rivenhall | exhaustive | 8 | 4 |
| small | unmodified | 127 | 47 |

On the fifteen-listing markets the agent almost never selects a pack size. It reads the
surcharge from the option label and adds: 48 of 290 stored answers show the arithmetic
explicitly ("base price $5.54 + pack size upgrade $14.21"). Magento also ships every
variant price in the page's `jsonConfig.optionPrices`, so within an opened listing no
interaction is strictly required.

That splits the gate in two, and only one half is a property of this environment:

| Layer | Gate | Holds on |
| --- | --- | --- |
| Listing-level | The search card shows one "from" price, so each listing must be opened | WebArena and Shopee both |
| Variant-level | The price for a chosen size exists only after selecting it | Shopee only, verified by hand in August 2026 |

Every failure measured in this project is a listing-level failure. No run has ever opened a
listing and then failed to obtain a variant price. The measured claims are therefore about
the listing-level gate, and the variant-level gate is motivation from the live marketplace
plus a stated limitation of the environment.

## Caveats

- 12 runs per arm, three per question. A direction, not an interval
- One model, one agent, two markets. The generalisation axes named in the design, a second
  model and a second scaffold, remain untested
- The units fix was made after seeing these runs. It is a correction to a measurement
  instrument rather than to the policy, and the policy itself was not touched, but the
  next held-out run is the honest place to quote it from
