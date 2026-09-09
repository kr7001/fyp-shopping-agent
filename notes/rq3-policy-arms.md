# RQ3, the two policy arms

2026-09-09. Code in `experiments/policy.py`, applied by `experiments/suite.py --policy`.

The sufficiency check from [rq3-sufficiency-check.md](rq3-sufficiency-check.md) is a
judgement about an answer. A policy is what the system does with that judgement, and
there are two separable things it can do. Keeping them apart matters, because they cost
different amounts and they answer different questions.

| Arm | Behaviour on a failed check | Added model cost |
| --- | --- | --- |
| `gate` | Replace the answer with an abstention naming what could not be verified | none |
| `retry` | Re-ask the task, telling the agent why the first answer was rejected | one further run |

## The gate arm is free, so it was measured on runs already recorded

The gate issues no browser action, so applying it to a finished run gives exactly the
verdict it would have given live. `experiments/replay_gate.py` replays it over every
baseline run on disk.

```
78 baseline runs replayed under the gate
4 skipped, scored against a catalogue that has since been regenerated

verdict       baseline    gate
-------------------------------
abstained            0      11
correct             66      66
wrong               12       1

wrong answers withdrawn   11 of 12
correct answers withdrawn 0 of 66
added model cost          $0.00, the gate issues no browser action
```

Eleven of twelve wrong answers are withdrawn and no correct answer is lost, for no
tokens. The one that survives is a wrong answer whose figures were all observed and
whose coverage was adequate: the fault is in the comparison, not in the evidence, so
none of the four rules apply.

This is the RQ2 finding turned into a fix. The baseline never abstained in eighty-two
runs, which is what made its failures dangerous. Under the gate it abstains eleven times,
and every one of those is a run that would otherwise have asserted something false.

**Four runs were excluded, and the exclusion rule is worth stating.** The catalogue is
regenerated between rounds, so a run made against an earlier fixture is scored against
ground truth that no longer holds. Replay detects this by rescoring the untouched answer:
if today's scorer disagrees with the verdict recorded at the time, the fixture moved
underneath the run and it cannot be compared. All four came from the pre-regeneration
round, where the cheapest card was Fenwick Wholesale at $6.37 rather than Hillside
Wholesale at $6.44. Suites now record their `_instance` block so this is detectable
directly rather than inferred. Without the exclusion the gate appears to withhold four
correct answers, which would have been a false result reported against my own method.

## The retry arm has to be paid for

A gate improves soundness and never improves accuracy: the best it can do is convert a
wrong answer into a refusal. The retry arm is the one that can convert it into a correct
answer, by returning openJiuwen's `blocked` state with a reason attached and asking again.

Smoke test on `scaled-all-stocked`, the universal-coverage task:

```
attempt 1   "Yes"                                     $0.062   flagged unverified_universal
attempt 2   "No. Out of 15 total listings, only 10    $0.678   clean
             stock this pack size: ..."
```

Correct, and it cost $0.74 against a baseline wrong answer's $0.08. That ratio is the
real finding of the arm and it should not be buried: **being right here costs about nine
times being wrong**, because the second attempt does the exhaustive work the first
skipped. An accuracy-only plot would show the policy winning and hide what it spent.

The second attempt runs in a fresh browser, since each run is its own process and the
runtime shuts the browser down on exit. So the retry inherits the reason but not the page
state. That makes it a harder test than a true in-loop block, and makes its cost a full
second run rather than a few extra steps. An in-loop integration inside `service.py`
would be cheaper and is the obvious next step, but it is not what these numbers measure
and the report should not imply otherwise.

## What this leaves for the efficiency half

Neither arm makes the agent cheaper. The gate is free and the retry is expensive, and
both are reactive: they act after an answer exists. The remaining half of RQ3 is the
part that acts before, deciding what to retrieve from the question, and that is where the
oracle floor of 11 opens and the 4 prunable-by-bound listings come in.
