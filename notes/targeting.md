# Targeting: choosing what to retrieve from the question

> **Correction, 2026-09-10.** The first version of this note reported total_bound as the
> RQ3 claim met, 4 of 4 correct at 7.2 actions against exhaustive's 31.3. **That result is
> withdrawn.** The arm never enumerated the candidate set: it read the first four listings
> on the search page and treated those as the whole market. The true winner for the
> cheapest-total questions happens to sit inside those four, so the answers were right
> without the bound doing any work. Seven actions against thirty-one was not a saving from
> pruning, it was a saving from not looking.
>
> The exhaustive arm saw all fifteen and opened all fifteen, because its instruction said
> "including any on later pages". So this was never a perception limit. It was a missing
> step in my strategy prompt.
>
> Two things about how it surfaced. **The sufficiency check caught it and I did not**:
> `understated_population` fired on exactly these runs, because the answers said "I opened
> 4 listings, all 4 listings were checked". And it is this project's own thesis applied to
> its author, since I reported a correct-looking result reached from insufficient evidence
> and did not notice because the answer was right.
>
> It also explains `best-per-litre` being wrong in every arm except exhaustive: Thornbury
> Pantry, the correct answer, was never visible. That task was unanswerable wherever the
> agent did not paginate.
>
> Enumeration is now an explicit first step in every strategy. The sections below record
> the original run and are kept for the record rather than corrected in place.


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

---

# Targeting v2: enumerate, then prune

2026-09-10. 12 runs, $4.58, four gated questions, three repeats, run with the gate on.
Results in `experiments/results/20260910T101847/`.

The only change from v1 is that every strategy now begins by establishing the candidate
set: paginate the search results, list every listing with its advertised price, and skip
only what has been enumerated.

**Enumeration verified before reading anything else.** All twelve runs observed the full
seller list and opened between 10 and 15 listings, against v1's four.

## The result

| | Correct | Refused | Wrong | Actions | Cost per run |
| --- | --- | --- | --- | --- | --- |
| Unmodified | 64% | 0 | 10 of 28 | 17.7 | $0.276 |
| Exhaustive | 100% | 0 | 0 of 8 | 28.4 | $0.568 |
| **Targeting + gate** | **100%** | 2 | **0 of 12** | **18.4** | **$0.382** |

Rate is correct as a share of what the arm answered.

**It matches the exhaustive upper bound on accuracy, for 35 per cent fewer interactions
and 33 per cent less money, and it gets no answers wrong at all.** That is the claim RQ3
was written to make.

## By strategy

| Strategy | Correct | Refused | Wrong | Actions | Exhaustive | Saving |
| --- | --- | --- | --- | --- | --- | --- |
| total_bound | 5 | 1 | 0 | 21.7 | 31.2 | 31% |
| refutation | 3 | 0 | 0 | 14.3 | 20.0 | 28% |
| rate_bound | 2 | 1 | 0 | 16.0 | 31.0 | 48% |

Two of these are firsts. `scaled-all-stocked` is correct three times from three, having
been wrong in every previous arm except exhaustive. `scaled-best-per-litre` is correct at
all for the first time in the project, which follows directly from the correction: its
answer, Thornbury Pantry, was never visible until the agent was made to paginate.

## The gate is doing work, and it is the right work

Two runs were refused rather than answered, and both refusals look correct:
`understated_population` on a run that opened 9 listings and described that as complete,
and `unsupported_number` on a per-litre answer. Neither became a wrong answer, and the
other ten were right. **The combination has no wrong answers in twelve runs**, which
neither half achieved alone: targeting alone was wrong four times in eight, and the gate
alone never got cheaper.

## What is still on the table

`refutation` should be the cheapest strategy and is not. Refuting "does every listing
stock it" needs **one** counterexample, and five of the fifteen do not stock the pack, so
a hunt should terminate in two or three openings. The runs opened ten or eleven. The agent
enumerated and then surveyed rather than hunting, so it is executing the letter of the
strategy and not its point. That is the largest remaining saving visible in the data and
it needs a sharper prompt rather than a new idea.

## Caveats, and the one that matters most

- **In sample.** The enumeration step was added after watching v1 fail, so these numbers
  are fitted to the failure they were designed to fix. A held-out run on a regenerated
  catalogue is needed before this figure is quoted as a result
- 12 runs, three per question. A direction, not an interval
- Strategies are supplied in the prompt and not enforced. The refutation shortfall is
  exactly what that permits
- The v1 numbers remain in the section above, wrong, with the correction attached. They
  are kept because the record of what was claimed is part of the result

---

# Refutation v3, and a hole it exposed

2026-09-10. 3 runs, $0.65, `scaled-all-stocked` only.

v2's refutation was correct three times from three and cost more than it should. Refuting
a claim about every listing needs one counterexample, five of fifteen lack the pack, and
the runs were opening ten or eleven. The agent was following the letter of the instruction
and not its point.

The instruction now says to stop immediately on the first counterexample, and that
stopping after one or two openings is the correct outcome rather than a sign of having
done too little.

| | Actions | Against exhaustive's 20.0 |
| --- | --- | --- |
| v2 | 14.3 | 28% saved |
| **v3** | **10.3** | **48% saved** |

Still 3 of 3 correct, and one run named its counterexample explicitly:

```
No. Not every Rivenhall listing stocks the 2 x 9.5L pack. Counterexample:
Chandler Wholesale (listing 11 of 15) does not offer it.
```

## The hole

One of the three answered **"No" having opened no listing at all.** Correct, and correct by
luck.

The coverage rule only ever looked at affirmations. `unverified_universal` catches a "Yes"
from partial coverage, and nothing caught the mirror case, because refuting is supposed to
be cheap. But cheap is not free: one counterexample settles the question and the
counterexample has to have been seen.

Checked rather than assumed: the search results page contains no mention of "9.5L" and no
mention of stock at the option level, so a listing's lack of the pack cannot be established
without opening it. The rule is sound.

Added `refutation_without_evidence`: a denial of a universal claim with zero listings
opened. It fires on two recorded runs, both correct, both unearned.

## What that does to the gate's headline, honestly

The gate's strongest property was that it had never blocked a correct answer. That is no
longer true.

```
93 baseline runs replayed under the gate

verdict       baseline    gate
-------------------------------
abstained            0      17
correct             77      75
wrong               16       1

wrong answers withdrawn   15 of 16
correct answers withdrawn  2 of 77
```

Two correct answers are now withheld, and both are answers reached with no evidence at
all. Whether that counts as a cost depends on which property is being bought. Under
accuracy it is a loss of two. Under soundness it is the rule working: an answer that was
right without evidence is exactly what this project argues should not be trusted.

The honest way to report it is both numbers, not the flattering one.

## A recurring hazard worth naming

`replay_gate.py` had been pooling the confidence, exhaustive and targeting suites into the
baseline, because its filter tested only the one flag that existed when it was written.
That is the third time a figure has come out wrong from mixing conditions, after the two
headline percentages and the pooling of targeting v1 with v2.

The pattern is the same each time: an arm is added, and code written before it existed
silently treats it as more of what it already knew. The filter is now written as an
explicit list of everything that makes a suite not a baseline, and any further arm has to
be added to it deliberately.
