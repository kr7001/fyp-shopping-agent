# RQ3, the two policy arms

2026-09-09. Code in `experiments/policy.py`, applied by `experiments/suite.py --policy`,
replayed by `experiments/replay_gate.py`.

The sufficiency check is a judgement about an answer. A policy is what the system does
with that judgement, and there are two separable things it can do. Keeping them apart
matters, because they cost different amounts and answer different questions.

| Arm | Behaviour on a failed check | Added model cost |
| --- | --- | --- |
| `gate` | Replace the answer with an abstention naming what could not be verified | none |
| `retry` | Re-ask the task, telling the agent why the first answer was rejected | one further run |

## The gate arm is free, so it runs on runs already recorded

The gate issues no browser action, so applying it to a finished run gives exactly the
verdict it would have given live.

```
78 baseline runs replayed under the gate
4 skipped, scored against a catalogue that has since been regenerated

verdict       baseline    gate
-------------------------------
abstained            0      12
correct             66      66
wrong               12       0

wrong answers withdrawn   12 of 12
correct answers withdrawn 0 of 66
added model cost          $0.00, the gate issues no browser action
```

**Read that number with the caveat below.** Two of the five rules were written after
seeing failures in the retry arm, so for those two this is an in-sample figure. The
honest version is in "What is in sample" further down.

Four runs were excluded. The catalogue is regenerated between rounds, so a run made
against an earlier fixture is scored against ground truth that no longer holds. Replay
detects this by rescoring the untouched answer: if today's scorer disagrees with the
verdict recorded at the time, the fixture moved underneath the run. All four came from
the pre-regeneration round, where the cheapest card was Fenwick Wholesale at $6.37 rather
than Hillside Wholesale at $6.44. Suites now record their `_instance` block so this is
detectable directly. Without the exclusion the gate appears to withhold four correct
answers, which would have been a false result reported against my own method.

## The retry arm, 5 tasks x 3 repeats, $4.21

Same tasks and same fixture as the scaled baseline, so the two are comparable. They are
not paired: the retry arm re-ran every task from scratch, so its first attempts are fresh
samples rather than the baseline runs themselves.

| | Baseline | Retry arm |
| --- | --- | --- |
| correct | 10 | 10 |
| wrong | 5 | 2 |
| abstained | 0 | 2 |
| failed | 0 | 1 |
| cost | $3.13 | $4.21 |

Wrong answers fell from 5 to 2 for 34 per cent more spend, and the two that remain are
both on one task. Nothing was converted from wrong to correct for free: every conversion
cost a second full run.

**What the retry actually did.** All three `scaled-all-stocked` runs answered a bare
`Yes` after opening 4 of 15 listings. All three were flagged `unverified_universal`, and
all three second attempts came back with the correct answer and the evidence:

```
attempt 1   "Yes"                                                       4 listings opened
attempt 2   "No. Out of 15 listings, only 10 stock the 2 x 9.5L pack.
             The 5 that do not are: Chandler Wholesale, Pembroke ..."   all 15 opened
```

This is the clearest result in the arm. A one-word wrong answer became a complete correct
one, three times out of three, because the block named what was missing rather than
saying try again.

**One of those three is scored `failed`, and the text was right.** The second attempt on
`scaled-all-stocked-1` returned the correct answer but the runtime reported `ok: false`,
so the scorer records it as a failed run. Leaving it as `failed` understates the arm. I
am not changing the scorer to fix that, because changing a scorer in favour of my own
policy after seeing the result is how a result stops meaning anything. It is reported
here instead.

## The arm exposed two faults in my own check

**A correct answer was blocked.** `scaled-target-price-2` first answered "$17.68, charged
by Redhill Stores", which is exactly right. The rule flagged it `unsupported_number`
because $17.68 appears nowhere on the page: it is the $6.82 base plus the $10.86
surcharge. Both parts were observed, and the composition test only exonerated answers
that stated their own working. An answer that gives the total alone had nothing to
compose and was called unsupported. Showing the arithmetic should be a virtue, not a
precondition for being believed. The composition test now also runs over the observed
absolutes and deltas, not only the figures the answer happens to mention.

That fix costs recall: the gate falls from catching 11 of 12 to 9 of 12. The two it
stops catching were being caught for an accidental reason, not their real one.
`scaled-best-per-litre` names Redhill at $0.93/L when the truth is Thornbury Pantry's
6 x 1.25L at $0.9107/L. Its figures are all observed and correctly combined. Blocking it
because $17.68 is not printed on a page was luck, and losing the catch is the right
trade.

**A blind spot the arithmetic rules cannot see.** That left `scaled-best-per-litre` wrong
three times and flagged zero times. The traces say why in the agent's own words:

```
"... at $0.931/L with the 2 x 9.5L pack size. This was determined by
 analyzing all 4 sellers ..."
```

Every figure is real and every sum is right. The comparison is over 4 of 15. So a fifth
rule, `understated_population`: an answer that states the size of the set it considered
is checked against the size of the set that exists. It needs no ground truth about the
right answer, only the population, and it catches a class the other four cannot, where
sound figures are combined over the wrong set.

With it, 12 of 12 wrong runs are caught and no correct run is flagged.

## What is in sample

Rules 1 to 4 were validated over 82 runs before any of them was used live, so their
figures were out of sample when the retry arm ran. The composition fix and
`understated_population` were both written from failures in that arm, so the 12 of 12
above is in sample for them and should not be quoted as a clean result.

The clean test is cheap, because the gate needs no model calls of its own: one fresh
baseline suite, replayed under the current rules. About $3, and it is the next thing to
spend money on.

## The costs the arms do not remove

Neither arm makes the agent cheaper. The gate is free and reactive. The retry is
expensive and reactive. Both act after an answer exists, and the retry pays a full second
run to do so, which on `scaled-all-stocked` meant opening all 15 listings on the second
pass having opened 4 on the first.

The remaining half of RQ3 acts before: deciding what to retrieve from the question. The
oracle floor is 11 opens of 15, with 4 listings prunable by the "from" price bound. A
policy that reached the floor on the first attempt would get the `all-stocked` answer
right without the second run, and that is where the efficiency result has to come from.
