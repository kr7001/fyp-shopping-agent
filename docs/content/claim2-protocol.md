# The second claim run, protocol (DRAFT)

Drafted on 22 October 2026, before the second claim market exists. Status: **draft, not
frozen.** It is finalised from the verifier's logic audit and committed before any seed of the
claim market is generated. Everything marked "to fix" is decided at that point and never
changed after the market exists. Amendments after the market, if any, are recorded with their
times, as the first protocol did.

## The question it answers

1. **The front door.** On reworded questions the block was not designed on, does the block with
   a model reading the question answer correctly more often than the block with its rules?
2. **The block at scale.** On a larger, mixed market the block was not tuned on, does the block
   still reach the correctness of exhaustive browsing while opening fewer listings, at lower
   cost?
3. **RQ2 again.** Does the shipped agent still fail there?

## The market (A+)

- **Two products under one brand.** About 20 listings of a tee (sizes S, M, L, XL) and about 20
  listings of bottled water (packs 24 x 350ml, 12 x 550ml, 6 x 1.25L, 2 x 9.5L), from distinct
  sellers, so the brand's search returns about 40 listings, interleaved, not grouped by product.
- **Two results pages.** At the shop's page size of 36, the search spans two pages. No shop
  setting is changed. Every claim question's answer depends on reading both pages.
- **Each variant absent, sold out or buyable at its own price.** The tee and water price models
  are those of the generators already used (Thornwood and Ashcombe for tees, Rivenhall and
  Calderwood for water).
- **Acceptance rules.** The existing tee rules and water rules, plus, to fix:
  - for each gated question the answer renders outside the first screen, and a listing on the
    first screen advertises less than the answer costs, so a card-only answer is wrong;
  - at least one gated question's answer is on page 2, so a bound computed over page 1 alone
    would stop too early;
  - the size or pack each "offer" or "stock" question asks about is listed but sold out on at
    least one listing, so the two readings differ;
  - the best price per litre is not at the cheapest 2 x 9.5L listing.
- **Seed and brand rules.** Development uses its own brand and seeds 900 to 999 only. The claim
  market is the first seed from 1000 that passes every rule, with a brand chosen by the first
  protocol's rule (the shop's search returns nothing for it, and it is no word of any seller
  name the generator can draw). To fix: the brand list.
- **Checked live before any run**, extended to two pages and two products: the search lists
  exactly the market's listings across exactly two pages, every card's advertised price equals
  the listing's cheapest buyable variant, every variant's label, price and stock equals the
  fixture's, and the gated theme hides every variant price until chosen. Thornwood's and
  Ashcombe's results pages are unchanged.

## Questions (templates, to fix)

`{brand}` is the claim market's brand. Keys are computed from the fixture by code, under both
readings where a question has two.

**Tee**

| Id | Question |
| --- | --- |
| tee-headline | Of the {brand} tee listings shown, which one advertises the lowest price on the results page, and what is that price? |
| tee-target-price | What is the lowest price anyone charges for size M of the {brand} tee, among those that can actually be bought? |
| tee-cheapest-target | Across the {brand} tee listings, which seller is cheapest for size M, and what is that price? Only count a listing that can actually supply that size. |
| tee-all-stocked | Does every {brand} tee listing offer size M? Answer yes or no. |
| tee-count-stocked | How many of the {brand} tee listings offer size M? |
| tee-count-buyable | How many of the {brand} tee listings have size M in stock and available to buy right now? |
| tee-exists-under | Is there any {brand} tee listing with size M available to buy for under ${limit}? Answer yes or no, and name the seller if yes. |
| tee-top-3 | Which three sellers are cheapest for size M of the {brand} tee among listings that can actually supply it, and at what prices? |

**Water**

| Id | Question |
| --- | --- |
| water-target-price | What is the lowest price anyone charges for the 2 x 9.5L pack of {brand} water, among those that can actually be bought? |
| water-cheapest-target | Across the {brand} water listings, which seller is cheapest for the 2 x 9.5L pack, and what is that price? Only count a listing that can actually supply that pack. |
| water-all-stocked | Does every {brand} water listing stock the 2 x 9.5L pack? Answer yes or no. |
| water-count-buyable | How many of the {brand} water listings have the 2 x 9.5L pack in stock and available to buy right now? |
| water-best-per-litre | Across all the {brand} water listings and all their pack sizes, which seller offers the lowest price per litre among packs that can actually be bought? |

**Questions the block should not plan**

| Id | Question |
| --- | --- |
| decline-delivery | Which {brand} seller delivers fastest for size M of the tee? |
| decline-taste | Which {brand} water tastes best? |

**Held-out rewordings.** Written blind by the verifier from these templates, before the claim
market exists and without seeing the model parser's prompt, into
`experiments/tasks/paraphrases_v2.json`, with each rewording marked as keeping its template's
meaning or not. The ones that keep it run in the claim with their template's keys. To fix: how
many per template.

## Arms (to fix)

1. **Shipped.** openJiuwen as shipped.
2. **Open everything.** As shipped, told to open every listing of the product the question asks
   about. To fix: the exact wording.
3. **The block, rules.** The block at the frozen commit, `--parser rules`.
4. **The block, model.** The same block, `--parser model`. It may decline a question only when
   the rules confirm the attribute it needs is not shown on this shop.

Every arm: the same model, sampling, browser flags, fresh profile, selector cache and answer
check off. The step and clock limits are raised for every arm alike, to 300 steps and 30
minutes, because exhaustive browsing of two pages exceeds the 100 steps and 10 minutes of the
first claim. Both models: DeepSeek V4 Flash as the main model and Claude Haiku 4.5 for
continuity, each its own result, never pooled. DeepSeek's provider is not pinned: the mix is
recorded and H3 is also reported on tokens.

## Measures and analysis (to fix)

As the first protocol: correct under the key fixed before the run, listings opened by
membership of the market's listings, cost by the provider's charge, by question then pooled,
stratified exact and rank tests, Holm over the primary tests. Candidate primary tests:

- **H1:** the block (model) is correct more often than shipped, on the reading-independent
  questions.
- **H2:** the block (model) opens fewer listings than open everything.
- **H3:** the block (model) costs less per run than open everything.
- **H4:** on the held-out rewordings, the block (model) is correct more often than the block
  (rules).

## Budget (to fix from the dry run)

About $105 is left on the key. The dry run quotes the exact estimate. A cap is checked before
every invocation, as before.

## Limits stated in advance (draft)

- One new market, one draw. Two products only.
- The model parser's prompt was written from paraphrases_v1's failures. The held-out rewordings
  in v2 are the test.
- The stop rule still assumes no card advertises more than its cheapest buyable variant.
- The page's encoded variant store is still in the page source.
