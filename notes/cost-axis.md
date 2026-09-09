# The cost axis, and where a policy has to live

2026-09-10. Exhaustive arm, 8 runs on the four gated scaled questions, $4.54.
Comparison produced by `experiments/arms.py`, which restricts every arm to the same four
questions so the denominators match.

## Every arm, same questions

| Arm | Runs | Correct | Refused | Wrong | Rate | Actions | Cost per run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Unmodified | 28 | 18 | 0 | 10 | 64% | 17.7 | $0.276 |
| Confidence, plain | 12 | 6 | 0 | 6 | 50% | 13.9 | $0.219 |
| **Gate** | 25 | 15 | 9 | 1 | **94%** | 17.2 | **$0.260**, replayed |
| Retry | 13 | 8 | 2 | 2 | 73% | 27.3 | $0.374 |
| **Exhaustive** | 8 | 8 | 0 | 0 | **100%** | 28.4 | **$0.568** |

Rate is correct as a share of questions the arm actually answered, so refusing is neither
rewarded nor punished by that column.

## The upper bound behaves exactly as an upper bound should

**8 of 8 correct, at 2.1 times the cost of the unmodified agent.** That includes
`scaled-best-per-litre`, which every other arm gets wrong in every run: 0 of 3 unmodified,
0 of 3 under the confidence prompt, 0 of 3 on retry. Told to open everything, the agent
gets it right twice out of two.

That settles something the project could previously only assume. The failure is **not** a
reasoning or arithmetic limitation of the model. The information is reachable, the
comparison is within the model's competence, and the answer is available for $0.57. What
the unmodified agent lacks is the decision to go and look.

## The axis

```
unmodified     64% correct   17.7 actions   $0.276
exhaustive    100% correct   28.4 actions   $0.568
```

Two points, so there is now a line to plot against. Any policy worth having lives between
them: it must approach exhaustive's accuracy while approaching the unmodified agent's
cost. **The oracle floor of 11 openings says the room exists** — exhaustive spends 28.4
actions and a perfect method needs 11 openings, so a large part of exhaustive's cost is
avoidable in principle.

## Where each arm sits, and what it is for

**The gate is the only arm that changes the outcome without changing the spend.** It
issues no browser action, so it sits at the unmodified arm's cost and converts wrong
answers into refusals: 94% correct on what it answers, one wrong of 25. It buys soundness,
not accuracy, and it buys it for nothing.

**The retry buys accuracy and pays for it**, 73% at $0.374, because a second attempt is a
second full run.

**The confidence arm is not a policy** and appears here only for comparison. Its 50% is
noise on twelve runs rather than evidence that asking for confidence makes the agent
worse; what matters is that it never abstains, so the prompt changes nothing about the
outcome.

## What this does not yet show

There is no targeting arm, so the interesting region of the axis is empty. Everything
measured so far is at one end or the other: the gate is free and reactive, the retry and
the exhaustive arm both pay in full. Nothing yet spends *less* than exhaustive while
matching it.

That is the remaining claim of RQ3 and it is now plottable, which it was not this morning.

## Caveats

- 8 runs in the exhaustive arm, 2 per question. Enough to establish the upper bound as a
  point, not enough for a confidence interval on it
- The control question is excluded from every arm here. Its answer is on the results page,
  so an exhaustive arm has nothing to be exhaustive about, and including it would inflate
  cost with a run no policy can act on. Its exclusion is why these figures differ from the
  suite totals quoted elsewhere
- The exhaustive instruction is given in the prompt rather than enforced. The agent was
  told to open everything and its traces show 20 to 36 actions, but nothing checks that it
  literally opened all 15 before answering
