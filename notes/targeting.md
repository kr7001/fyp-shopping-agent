# Targeting: choosing what to retrieve from the question

2026-09-10. 8 runs, $0.73, four gated scaled questions, two repeats each. Matches the
exhaustive arm exactly, so the comparison is like for like.

This is the second half of RQ3, and the first thing built here that acts *before* the
agent looks rather than after it answers.

## The headline is not one number

| Strategy | Question | Runs | Correct | Actions | Exhaustive actions | Saving |
| --- | --- | --- | --- | --- | --- | --- |
| **total_bound** | cheapest / lowest price | 4 | **4** | **7.2** | 31.3 | **77%** |
| refutation | does every listing stock it | 2 | 0 | 5.5 | 20.0 | 73% |
| rate_bound | best per litre | 2 | 0 | 6.5 | 31.0 | 79% |

Pooled, the arm is 50% correct at $0.091 against exhaustive's 100% at $0.568, which reads
as a failure. Split by strategy it is not one result but three, and they disagree.

## total_bound works, and this is the RQ3 claim met

**4 of 4 correct, at 7.2 actions against exhaustive's 31.3.** Same accuracy as the upper
bound for 77 per cent fewer interactions.

The reasoning it was given is branch and bound over the advertised price: the search page
shows each listing's cheapest option, nothing inside a listing can cost less than that, so
a listing whose advertised price already exceeds the best total found cannot win and does
not need opening. The agent executed it and said so:

```
Opened 3 listings, skipped 1 (Bramley Pantry at $16.61, whose theoretical
best cannot beat the best total found).
```

For the question type where a sound bound exists, a question-conditioned policy reaches
the exhaustive answer at roughly a quarter of the cost. That is the claim RQ3 makes,
measured, on 4 runs.

## refutation fails, and the failure is instructive

The strategy is sound. A universal claim needs every listing; its negation needs one
counterexample. Ten of fifteen stock the pack, so the answer is No and one counterexample
settles it.

Both runs answered **"Yes"** after 5 and 6 actions.

The strategy said explicitly: *"Only if you have opened every listing without finding a
counterexample may you answer Yes."* The agent took the permission to stop early and
ignored the condition attached to it.

**This is the point at which the two halves of RQ3 stop being independent.** Targeting
makes the cheap answer cheaper and does nothing about the agent's willingness to assert
the expensive one on no evidence. The sufficiency check catches both runs, flagging
`unverified_universal`. Neither half is sufficient alone: targeting without the gate
answers "Yes" for five actions, and the gate without targeting refuses without ever
becoming cheaper.

## rate_bound fails, and my prompt caused it

Both runs report Redhill Stores at about $0.812 per litre for the 24 x 350ml pack at
$6.82. Checked against the database:

```
agent said : Redhill 24 x 350ml at $6.82   ->  $6.82 / 8.4L = $0.812/L
truth      : Redhill 24 x 350ml is $8.30   ->  $8.30 / 8.4L = $0.988/L
             $6.82 is Redhill 12 x 550ml   ->  $6.82 / 6.6L = $1.033/L
```

The arithmetic is correct and the attribution is not. $6.82 is the advertised price and
belongs to the 12 x 550ml pack; the agent attached it to a different pack and divided by
that pack's volume.

**The strategy prompt taught it to do this.** The rate bound says a listing's best possible
rate is its advertised price divided by the largest volume it could be offering. That is a
device for deciding what *not* to open. The agent carried the same combination into its
answer and reported a price that no pack has.

Two lessons, both fixable:

1. A pruning bound must be explicitly quarantined from the answer. The prompt has to say
   that a figure derived from the bound is for skipping only and must never be reported
2. The failure has the same shape as the delta misread from the RQ2 baseline: right
   arithmetic over a number that means something else. That shape has now appeared twice,
   from two different causes, which suggests it is characteristic of the setting rather
   than of one prompt

**It also exposes a gap in the sufficiency check.** One of the two runs passes clean. The
check verifies that figures were observed, and $6.82 *was* observed; it does not verify
that a figure is attached to the thing it is claimed to describe. Catching this needs a
rule about attribution rather than about presence, and that rule does not exist yet.

## What the arm establishes

- **The efficiency claim of RQ3 is achievable**, demonstrated on the question type where a
  sound bound exists: exhaustive accuracy at 23 per cent of the interactions
- **It does not generalise across question types for free.** Of three strategies, one
  works, one is undermined by the agent ignoring a condition, and one induced a new error
- **The two halves of RQ3 are complements, not alternatives.** The gate catches three of
  the four targeting failures, and targeting is what makes the gate's refusals affordable
  to fix

## What to do next, in order

1. Quarantine the bound from the answer in the `rate_bound` prompt and rerun that question
   alone. Roughly $0.20
2. Run targeting and the gate together as one arm. This is now the interesting
   configuration and neither half alone is the contribution
3. Only then a held-out test, since both fixes above are being made after seeing these runs

## Caveats

- 8 runs, 2 per question. Every figure here is a direction, not an interval
- The strategies are supplied in the prompt, not enforced, and the refutation failure is
  exactly what that permits
- `LARGEST_PACK_LITRES = 19` is a fixture constant. A policy facing an unknown catalogue
  would have to establish it, and the rate bound is loose because of it
