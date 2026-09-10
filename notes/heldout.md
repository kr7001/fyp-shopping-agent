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

## What cannot be claimed from this

There is **no exhaustive arm on the held-out market**, so the 35 per cent interaction
saving measured on the development market is not established here. 15.1 actions is lower
than the development market's 18.4, but without an exhaustive run on Calderwood there is
nothing to divide it by. Stating a saving would be borrowing a denominator from a
different market, which is the error this project has now made three times in other forms.

That run costs about $4.50 and is the first thing the next credit should buy.

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

## Caveats

- 8 runs, two per question. A direction
- One model, one agent, two markets. The generalisation axes named in the design, a second
  model and a second scaffold, remain untested
- The units fix was made after seeing these runs. It is a correction to a measurement
  instrument rather than to the policy, and the policy itself was not touched, but the
  next held-out run is the honest place to quote it from
