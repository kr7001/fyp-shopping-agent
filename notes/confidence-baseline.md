# Asking the agent how confident it is

2026-09-09. 15 runs, $2.78, `plain` wording, scaled suite, model `claude-haiku-4.5`.
Raw results in `experiments/results/20260909T223402/`.

The obvious objection to this project is to ask the agent for a confidence figure and
abstain below a threshold. It is the first thing a reviewer proposes, so it is measured
here rather than argued away with a citation. The prediction was written into the code
before the runs were made: it would not work, because the agent is not uncertain.

## The result in one table

| Task | Confidence | Accuracy |
| --- | --- | --- |
| scaled-headline | 95 to 100 | 1.00 |
| scaled-cheapest-target | 100 | 1.00 |
| scaled-target-price | 95 | 1.00 |
| **scaled-all-stocked** | **100** | **0.00** |
| **scaled-best-per-litre** | **95** | **0.00** |

The task it never gets right scores 100. The task it always gets right scores 95. Two
tasks with accuracy 1.00 and 0.00 both score 95.

## Every measure agrees

```
correct answers   mean confidence 97.8
wrong answers     mean confidence 97.5
gap                              +0.3
AUROC                            0.528     (0.5 is no signal at all)

stated confidence  0.98
actual accuracy    0.60
overconfidence    +0.38
```

All fifteen runs fall between 95 and 100. Five points of a hundred-point scale.

**No threshold works.** Sweeping every cutoff from 0 to 90 changes nothing, because no run
scores below 95. The only cutoff that filters anything is 100, and there it stops 3 wrong
answers by discarding 4 correct ones.

| Method | Wrong stopped | Correct blocked |
| --- | --- | --- |
| Stated confidence, best threshold, chosen with hindsight | 3 of 6 | 4 of 9 |
| Sufficiency check | 3 of 6 | **0 of 9** |

The threshold was chosen after seeing which answers were right, which no deployable system
could do. The baseline was given that advantage and still lost.

**Keeping the scale at 0 to 100 rather than 0 to 10 was load-bearing.** On ten points every
one of these runs would have been a 10, and the clustering, which is the finding, would
have been invisible by construction.

## The number is worthless. The justification is not.

Each run was also asked to say *why*, in one sentence naming what it checked and what it
did not. That turned out to be the most useful part of the arm, and not in the expected
way.

The wrong runs describe their own inadequacy plainly:

```
scaled-all-stocked-2     conf 100   "I directly checked each of the 4 product pages
                                     and confirmed the 2 x 9.5L pack option..."
scaled-best-per-litre-1  conf  95   "I verified all 4 sellers and all their pack sizes
                                     by navigating to each product page..."
```

There are fifteen sellers. The agent says four, and rates itself 95 to 100.

So it is not hiding anything and it is not confused about what it did. It reports its
coverage accurately and does not treat that coverage as bearing on confidence. This is a
sharper finding than overconfidence: **the information needed to abstain is already
present in the agent's own output, and the confidence figure ignores it.**

**Which also means the reason can be checked and the number cannot.** A confidence figure
has no truth value, because there is no correct answer to how confident something should
feel. "I verified all 4 sellers" is a claim about behaviour, and the trace records the
behaviour.

Feeding the stated reason into the sufficiency check, as further text the agent asserted:

| Gate input | Wrong caught | Correct flagged |
| --- | --- | --- |
| Answer only | 3 of 6 | 0 of 9 |
| Answer plus stated reason | **6 of 6** | 2 of 9 |

Recall doubles. The two correct answers it now flags deserve inspection rather than being
written off:

- `scaled-cheapest-target-3` said "verified... on all four seller product pages" and was
  right. It opened 4 of 15 against an oracle floor of 11, which is exactly the unearned
  correct answer that `report_soundness` already counts
- `scaled-target-price-2` said "the lowest among all 8 sellers offering this pack size".
  Ten sellers offer it, not eight. The answer was right and the stated reasoning ran over
  a set that does not exist

Both were correct while reasoning over an incomplete or wrong set. Calling them false
positives assumes accuracy is the only thing worth protecting, which is the assumption
this project disputes.

## What this establishes

1. **Verbalised confidence cannot detect this failure.** Not poorly, at all. AUROC 0.528,
   and no threshold separates a task at accuracy 1.00 from one at 0.00
2. **The agent already knows what it did not check** and says so when asked, and saying so
   does not move the number
3. **Asking for a justification is worth doing anyway**, not as a confidence signal but as
   a checkable artifact

The third point reframes the arm. The conclusion is not that asking the agent about itself
is useless. It is that **a self-report is useful exactly where it is falsifiable, and
useless where it is not.**

## Caveats

- One model, `claude-haiku-4.5`, and one wording. The `retrieval` wording, which names the
  retrieval dimension explicitly, has not been run
- 15 runs, 6 of them wrong. Small
- Feeding the reason into the gate was tried after seeing these runs, so the 6 of 6 is in
  sample and needs a held-out test before it is quoted as a result
