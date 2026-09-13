# Review pagination as the second gating mechanism

Measured 13 September 2026, against the local WebArena-Verified catalogue.
All figures from direct MySQL queries and `curl` against the rendered storefront.

## Scale

| Quantity | Value |
| --- | --- |
| Reviews in catalogue | 308,939 |
| Products carrying reviews | 32,944 of 104,368 (32%) |
| Products with >= 30 reviews | 454 |
| Maximum on one product | 122 |
| Mean review length | 362 characters |

Text is real imported Amazon prose, not generated filler.

## The gate

Two separate walls, and the first one is the surprising one.

**The product page renders no review text at all.** `grep -c review-item` on
a product page with 122 reviews returns 0. The reviews live at a different
URL entirely: `/review/product/list/id/<entity_id>/`.

**That listing serves 10 per page, server-fixed.** 122 reviews becomes 13
pages. `?limit=30` and `?limit=100` are both ignored and still return 10.

There is **no sort control and no star filter**. Shopee publishes rating tabs
("1 Star (234)") that let a shopper jump straight to the complaints. WebArena
publishes nothing of the kind. The only way to reach a one-star review is to
paginate past the others.

**Consequence for method.** The stratified-retrieval sketch in CLAUDE.md said
"for example filtering to one-star reviews". That filter does not exist on this
platform. Stratification has to be done by reading and discarding, not by
querying. This is the same shape of discovery as the missing `lowPrice`:
the affordance the method assumed is absent, found before implementation.

## What is published and what is not

| Field | Product page | Review list page |
| --- | --- | --- |
| Mean rating | yes, `ratingValue` 91 of `bestRating` 100 | -- |
| Review count | yes, `reviewCount` 122 | -- |
| Per-star histogram | **no** | **no** |
| Per-review star value | no | yes, `itemprop="ratingValue"` |
| Review text | no | yes, 10 at a time |

This inverts the price case in an instructive way. For price, the aggregate
was missing and had to be parsed. For reviews, **the aggregate is published and
is the wrong aggregate**. `ratingValue=91` is free, accurate, and tells you
nothing about whether four people reported the product arriving broken.

The mean is a bound on nothing that a shopper asks about.

## Is the ordering adversarial? No.

Order is `created_at DESC`, newest first. Tested whether low ratings are pushed
to the back, across all 310 products with >= 40 reviews and a one-star review,
2,374 one-star reviews in total:

| Statistic | Observed | Under random arrangement |
| --- | --- | --- |
| Mean percentile position of a one-star review | 0.454 | 0.500 |
| Fraction in the last 20% | 26.6% | 20% |
| Fraction in the first 20% | 30.7% | 20% |

Slightly front-loaded if anything. **There is no systematic burying.** Any
single product that looks buried is coincidence, and I checked one that did:
product 20718 (M&M's Peanut, 122 reviews) has all four of its one-star reviews
on pages 12 and 13, with pages 1 through 11 averaging 4.5 to 5.0 stars and
containing zero one-star reviews. That is chance, not design.

## The trap, and why it is the thesis title

Of the 454 products with >= 30 reviews, **63 (14%) have a page 1 that is
uniformly four and five stars while carrying three or more one- or two-star
reviews deeper in the pagination.**

Nobody arranged this. The ordering is near-random. It falls out of a J-shaped
rating distribution (corpus-wide: 55% five-star, 15% one-star) meeting a
ten-row page cut. On a well-rated product the complaints are rare enough that
ten consecutive draws frequently contain none.

An agent that reads page 1 and reports "buyers are overwhelmingly positive, no
recurring complaints" is making a true statement about its sample and a false
statement about the product, with no merchant having done anything.
This is *ambiguity without adversary* in its cleanest form.

## Two question types, two guarantees

The distinction is what a review question actually asks for.

### Type A, existence. "Is this phone case waterproof?"

Asymmetric, and the asymmetry is the whole point.

- One review saying it leaked **settles it**. Stop on first hit. Exact.
- Zero mentions after k pages **settles nothing**. It bounds prevalence, it
  does not establish absence.

This is the same shape as the `all_stocked` refutation strategy already in
`experiments/targeting.py`, and the `unverified_universal` rule in
`experiments/sufficiency.py` already catches the failure, which is an agent
reporting "no buyer mentions leaking" after reading 10 of 122.

Needle instances occur naturally and are plentiful:

| Term | Products with 1-3 mentions among >= 30 reviews | Mean reviews on those products |
| --- | --- | --- |
| broke | 152 | 79 |
| leak | 42 | 92 |
| refund | 109 | 88 |

Sampled positions of a single "leak" mention, by page: 10, 6, 8, 7, 4, 10, 1, 2.
Scattered, so the depth required varies and cannot be guessed.

### Type B, consensus. "What do buyers generally say?"

Decomposes into a free part and a gated part, and an agent should know which
is which:

- **The mean is free.** `ratingValue` is on the product page. Spending browser
  actions to estimate it by reading reviews is pure waste.
- **The reasons are gated.** Why the unhappy minority is unhappy exists only
  in text, 10 rows at a time, with no filter to isolate it.

So the retrieval target is not "estimate the mean", it is "recover the
complaint themes", and the stopping rule is thematic saturation with a stated
bound: after reading n of N reviews and seeing no theme recur, the probability
that a theme of prevalence p was missed is bounded.

Correctness for Type B is harder to define than for Type A, because the ground
truth is a set of themes rather than a number. That is the main cost of taking
this on, and it is a real one.

## Recommendation

Take Type A now, defer Type B.

Type A reuses the existing refutation strategy and the existing sufficiency
rule almost unchanged, so it buys a second gating mechanism for RQ1 and a
second question family for RQ3 cheaply. It also strengthens the generality
claim: the same policy handles price gating and review gating without being
retuned per mechanism.

Type B needs a new stopping rule, a new correctness definition and a new
grader. That competes directly with the two generalisation axes (second model,
second scaffold), which are unrun and matter more to the thesis. Type B is the
better paper section; the generalisation axes are the better use of the weeks
remaining.

The 14% figure stands on its own as an RQ1 result regardless, since it is
measured from the database and costs no agent runs to report.
