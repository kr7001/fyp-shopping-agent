# The second claim run, protocol (DRAFT)

Drafted on 22 October 2026, before the second claim market exists; version 2 rewritten on 23
October 2026 from the verifier's fairness re-audit and the front door's pilot. Status:
**draft, not frozen.** It is finalised from the student's decisions (the section "Decisions
before the freeze" at the end) and the verifier's logic audit of the frozen commit, and
committed before any seed of the claim market is generated. After the market exists nothing
here changes; an amendment, if any, is recorded with its time, as the first protocol's were.

## The question it answers

1. **The front door.** On reworded questions the block was not designed on, does the block with
   a model reading the question answer correctly more often than the block with its rules?
2. **The block at scale.** On a larger, mixed market the block was not tuned on, does the block
   still reach the correctness of exhaustive browsing while opening fewer listings, at lower
   cost?
3. **RQ2 again.** Does the shipped agent still fail there?

## One commit

Every run is made at one commit, named here at the freeze with every version it carries: box,
form, prompt, normalisation, primitives, targeting, planner, scorer, sufficiency rules, the
analysis file, the A+ generator, the search-order model and the toolbar counter. The
analysis file's `require` holds each arm's conditions: those versions, the agent's code and
patch, the browser tool, flags and origins, and for the model arm the parser's model. The
claim command checks them before every invocation and spends nothing on a mismatch. A batch
found outside `require` afterwards is void as a whole: it is listed, re-run under the
required conditions, and until then it holds up only its own model's analysis. To fix at the
freeze: the commit and the version list.

Fixed settings, the same for every arm: the agent's sampling (temperature 0.2, top_p 0.1),
the browser tool (Playwright MCP 0.0.83, isolated, service workers blocked) confined to the
shop's origin, the gated theme's user agent, and a fresh browser profile and selector cache
for each run.

## The market (A+, generator version 3)

- **Two products under one brand.** 21 listings of a tee (sizes S, M, L, XL) and 21 of bottled
  water (packs 24 x 350ml, 12 x 550ml, 6 x 1.25L, 2 x 9.5L), each from a distinct seller, so
  the brand's search returns 42 listings over two results pages at the shop's page size of 36,
  in the shop's relevance order. No shop setting is changed.
- **Titles.** Each listing's title takes one of three phrasings of its product, drawn per
  listing, because with one fixed title the shop's relevance order lists nearly all of one
  product first (measured with `env/search_order.py --validate`). The claim's pools share no
  word with development's but the product noun: tee "Midweight Jersey Tee", "Midweight Jersey
  Knit Tee", "Midweight Jersey Tee, Short Sleeve"; water "Mineral Water", "Mineral Water,
  Bottled", "Pure Mineral Water, Bottled". Each pool shares one core, its shortest phrasing,
  so "the {brand} tee" and "{brand} water" each read as one product, and each names its
  product as its last word before any comma, which product scoping reads.
- **Each variant absent, sold out or buyable at its own price**, under the price models of the
  generators already used (Thornwood and Ashcombe for tees, Rivenhall and Calderwood for water).
- **Acceptance rules.** The tee generator's 13 rules (`env/generate_apparel.py`), the water
  generator's 8 (`env/generate_catalogue.py`), and the A+ market's 15 (`env/generate_aplus.py`),
  each in its file's rule text, which is part of this protocol by reference. In short:
  - *Price winners are clear.* Each price question's winner is unique and leads the next seller
    by at least 8 per cent (`unique_winner`, `clear_margin`); the best price per litre leads by
    8 per cent (`per_litre_margin`); the top three for size M are each at least 8 per cent
    apart, and the fourth 8 per cent above the third (`top_3_margin`, new in version 3).
  - *Sold-out and absent traps.* For the tee, the cheapest listed size M belongs to a listing
    that cannot sell it (`sold_out_trap`), and the listing whose size M would be cheapest of all
    has no size M (`absent_trap`). For the water, a 2 x 9.5L listed but sold out costs less than
    the buyable winner (`water_sold_out_trap`), and a pack listed but sold out is cheaper per
    litre than the best that can be bought (`per_litre_sold_out_trap`). So "can actually be
    bought" decides every price answer, and the readings of "offer" and "stock" count different
    listings (`readings_differ`).
  - *The first page misleads.* Every price question's answer renders outside the first screen,
    the four cards openJiuwen's card probe sees at its 1200 x 701 viewport, and a first-screen
    listing advertises less than the answer costs (`first_screen_misleads`); at least one price
    answer is on page 2 (`answer_on_page_2`); every count, under each reading, counts a page-2
    listing (`counts_need_page_2`); both products appear on the first screen and on page 2
    (`interleaved`). The two "does every listing" questions answer No under both readings and
    are not held to page 2: seven listings would have to fit on a page 2 of six.
  - *One answer per key.* The headline card is unique and on page 1, and every page-2 tee card
    is 8 per cent dearer (`headline_unique`, `headline_on_page_1`); the exists-under limit leaves
    exactly one buyable size M under it (`limit_separates`); the fourth cheapest size M costs
    more than the third (`top_3_unique`); the best per litre is not at the cheapest 2 x 9.5L
    (`per_litre_not_target`); every seller's first word is distinct and is inside no other
    seller's name, the brand, a product phrasing, an option label or a question template, and no
    seller name holds a word of a product phrasing (`names_distinct`).
  - *The bound can prune.* On the four target-price and cheapest-target questions, a bound
    computed from the cards can rule out at least three listings (`bound_is_useful`), and at
    least three survive it and must be opened (`bound_not_sufficient`). This guarantees the
    block something to save on those four questions and is stated as a limit below.
- **Seed and brand.** Development uses its own brand, Larchmere, and seeds 900 to 999 only. The
  claim market is the first seed from 1000 that passes every rule, drawn by
  `env/pick_aplus_market.py --claim`, which refuses while this file says DRAFT. The brand is
  the first of Wexcombe, Penhallow, Tarnbrook, Quillfield and Brackwater that the shop's
  search returns nothing for and that is no word of a seller name the generator can draw. (On
  23 October, before any seed, `env/pick_aplus_market.py --check-brands` found all five free:
  no card, plain or gated, no product name holding it, no seller word, no seller's first word
  inside it. The first, Wexcombe, is the brand; the shop's analyzer reads it in two forms.)
- **Checked live before any run** across both pages and both products
  (`env/check_aplus_market.py`): the search lists exactly the market's listings on exactly two
  pages; every card's advertised price equals the listing's cheapest buyable variant; every
  variant's label, price and stock equals the fixture's; the gated theme hides every variant
  price until chosen; the live results order equals the order recorded when the seed was
  accepted, which the failure codes read, and the page rules hold on it. This check runs again
  before each stage. Thornwood's, Ashcombe's and Larchmere's results pages are unchanged
  against snapshots taken before the claim market is seeded. Larchmere stays seeded; its brand
  word is not the claim brand's.

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

The fifteen rows above are unchanged since 22 October (sha256 of the rows, joined by line
breaks: `eaaab56a07897e36d87d970bad79d4e8f1d81179347a9b6323fd9d48bedae2cf`), so the
held-out rewordings written from them still apply.

**Two readings.** tee-all-stocked, tee-count-stocked and water-all-stocked say "offer" or
"stock", which reads as "in the size menu, even if sold out" (the menu reading, their own
key) or "can be bought now" (the buyable reading, a second key in the readings sidecar). Every
other keyed question has one reading, the buyable one, and its own key is it.

**Held-out rewordings.** `experiments/tasks/paraphrases_v2.json`, 36 entries, written blind by
the verifier from the templates before the claim market exists and without seeing the model
parser's prompt (sha256 of its entries, as `env/generate_aplus_tasks.py` computes it: to
record at the freeze). Thirty keep their
template's meaning; 26 of them have a key (the other four reword the two decline questions).
Six do not keep it and are not run. No v2 entry has met either parser, the prompt or any
person developing them before the run.

## Arms

1. **Shipped.** openJiuwen as shipped.
2. **Open everything.** As shipped, told to open every listing of the product the question asks
   about (`--exhaustive --exhaustive-wording product`, wording version 2): "Before answering,
   open every {product} listing in the search results, including any on later pages, and check
   every option the question needs on each one. Listings of anything else in the results are
   not part of the question and need not be opened. Do not stop early because a listing looks
   unpromising from its search-result price. Base the answer only on listings you have opened,
   and say how many you opened."
3. **The block, rules.** The block at the frozen commit, `--box --parser rules`.
4. **The block, model.** The same block, `--box --parser model`, the parse made by the run's
   own model at temperature 0 under prompt version 3. It may decline a question only when the
   rules confirm the attribute it needs is not shown on this shop, and a price question cannot
   be declined by naming a missing attribute. A reply that gives no usable form falls back to
   the rules' form, recorded on the run.

Both block arms: the rendered page reader (`--page-reader rendered`, headless Chromium,
following the pager across every results page), and the rate plan without a bound
(`--rate-plan every`, decision 1). Where the box asks back, the scripted user answers with
the reading the question's own key was written under (`--reading own`, decision 3): the menu
reading for the three two-reading questions and the six held-out entries that reword them,
the buyable reading for every other keyed question. A user never contradicts their own
question, and every ask is still counted (secondary measures).

Every arm: the same model and the fixed settings above, the answer check off, and 300 steps and
30 minutes (`--max-steps 300 --clock 1800`), raised for every arm alike because exhaustive
browsing of two pages exceeds the first claim's 100 steps and 10 minutes. On the pilot (23
October, Larchmere, DeepSeek) the longest block run took 110 tool calls and 493 seconds.

## Models

DeepSeek V4 Flash is the primary model: its four tests are the claim, with Holm over its
four. Claude Haiku 4.5 is a replication: a family of its own, Holm over its own tests, never
pooled with DeepSeek's. DeepSeek's serving provider is set by decision 9: either left to
OpenRouter (openJiuwen sends no provider preference) or restricted, for every arm alike, to the
listed fp8 providers at or below list price. Every run records its providers; H3 is also
reported on tokens, and within each provider wherever the two arms' provider mixes differ.

## Design and order

Each round runs every arm once (`--repeats 1 --repeat-start r`), and the order of the arms
rotates: round 1 shipped, open everything, the block (rules), the block (model); round 2 starts
at open everything; round 3 at the block (rules). Shipped asks the fifteen templates; open
everything the twelve gated ones; each block arm the fifteen templates and the held-out
rewordings. Rounds and what each model runs: to fix from the budget (decision 2).

## Budget and stopping

About $98 is left on the key after the pilot (to fix from the account at the freeze). The run
is staged, each stage one command with its own declared estimate and a cap: every invocation
starts only if the spend so far plus that invocation's high estimate stays under the stage's
cap, and an account that cannot be read stops the stage. Stage 1 is DeepSeek; the verifier
checks its outputs before stage 2, Haiku, starts. Every stage's design is fixed here before
stage 1 starts, and nothing changes between stages except void re-runs. The claim command
for each stage is written from this section, dry-run, and verified before it runs.

A reserve is held back for void re-runs and for one repair. A repair is allowed only for a
fault in the harness, the shop or the laptop found from the logs (never from the answers or
the verdicts): the fault's fix is verified, the whole affected arm is re-run in that stage, the
repair is recorded here as a timed amendment, and the runs it replaces are reported beside it.
To fix: the stage caps and the reserve (decision 2).

## Measures and scoring

As the first protocol: correct under the key fixed before the run, listings opened by
membership of the market's listings, cost by the provider's charge, the parse call's tokens and
charge counted in its run. Answers are scored by the scorer at the frozen commit (score
version 8, to confirm at the freeze) with the same arguments in every caller (the market's
sellers and the two-reading list), so a run has one verdict wherever it is scored. A run is
scored under the reading it was answered under; a run with no key for that reading is
unscored and reported, never scored against another key.

The scorer is frozen at the commit (version 8, or version 9 if decision 5 adopts the three
fixes prepared on 23 October), and its known limits are stated: on fresh plausible answers
written by the verifier after version 8, version 8 misjudged 11 of 24, mostly long and careful
answers read as wrong, with a few wrong long answers read as correct; and on the pilot's 34
real answers it misjudged 5 correct block answers, all through the list of opened and skipped
listings the block asks its agent to write. The verdict of record is set by decision 5. Beside it, every answer is read by hand from a sheet in which the arm,
the model and the scorer's verdict are all replaced by random codes (`claim.py --sheet`); the
filled sheet is read back by `claim.py --hand`, H1 to H4 are rerun on the hand verdicts, and
every disagreement with the scorer is listed by arm and model after unblinding. A hand reading
cannot be blind to an answer's own style, which is stated.

## Tests

Stratified exact tests of correct and van Elteren tests of listings and cost, two-sided, by
question then pooled, Holm over the four within each model:

- **H1:** the block (model) is correct more often than shipped, on the nine reading-independent
  questions.
- **H2:** the block (model) opens fewer listings than open everything, on the twelve gated
  questions.
- **H3:** the block (model) costs less per run than open everything, on the twelve gated
  questions, also reported on tokens.
- **H4:** on the held-out rewordings, the block (model) is correct more often than the block
  (rules), stratified by template, one test of all thirteen keyed templates.

In H1 and H4 a slot the box closes (a decline, or an ask with no reply) counts as not correct,
as does an abstention. H2 and H3 count only slots where the agent ran: a closed slot runs no
agent and is listed by question and arm. Two sensitivities put the closed slots back: at zero
listings and the parse call's charge, and, cautiously, at open everything's median for that
question. H4 is repeated, secondary and unadjusted, on two pre-specified splits (the first
claim's six templates against the seven added; tee against water), and with one unit per
rewording rather than per run. The block's correctness against open everything is reported as
a difference with its confidence interval, not tested (decision 8). Further sensitivities:
without the two-reading questions; distinct runs only; with the voids; without runs that saw a
hidden price; without runs that sorted the results or changed the page size.

## Exclusions

A run is void when its log falls silent for more than 60 seconds or it ends with no final
completion for a reason outside the agent (the shop, the provider, the laptop). Voids are
decided from the log before any answer is judged, re-run once after the last round under the
same flags, and a second void is reported as such. Every other run counts; a run that stops at
the step or clock limit without an answer counts as not correct.

## Secondary measures

Asks on questions labelled clear and on those labelled ambiguous, declines, and parse
fallbacks, by arm and model; the shipped arm's failures on the reading-independent questions
by written code ("page 2 never reached", applied only where the key needs a listing past page 1
in the accepted order; a separate code for a run that sorted or changed the page size and
stayed on page 1; "a card or sold-out price taken"; "other"); sorts and page-size changes by
arm; runs that saw a hidden price; the DeepSeek provider mix by arm.

## Limits stated in advance

- One new market, one draw, two products.
- The model parser's prompt was developed on paraphrases_v1, which holds tee questions only;
  the held-out v2 set is the test, and the tee-against-water split shows the difference.
- The rules were never tuned on rewordings; a failed parse falls back to the rules, which pulls
  H4 toward no difference.
- Product scoping is a rules step both block arms share (decision 7), and relies on titles
  built to name their product's noun last.
- The stop rule still assumes no card advertises more than its cheapest buyable variant.
- The page's encoded variant store is still in the page source.
- The page rules hold for the shop's relevance order at 36 a page only; sorting is counted.
- The page rules select mildly for answer listings with longer titles and seller names, which
  rank lower in search (development seeds 901 to 920: the shortest phrasing was 18% of tee
  answer listings against 29% of all tees, and 22.5% of water answer listings against 37.6% of
  all waters, `env/manifests/aplus_dev-title-study.json`).
- The scorer's known misreadings (above), which lean mostly against long, careful answers.
- The rules' word list can overrule the model parser: it asks back on wording that already
  settles the reading, and a clash with it sends the model arm to the rules' form. On the
  pilot, "lowest listed price" was read as "listed, even if sold out" and the question was
  refused (decision 10).
- The market's rules guarantee the block something to save (`bound_is_useful`, the absent
  traps), as they guarantee the shipped agent something to miss; the result holds for markets
  with that shape.
- The box reads the results pages for its agent and hands it the listings' addresses and the
  shop's mechanics; open everything is told only to open everything, so H3 measures the plan,
  the briefing and the free page reading together, not the stop rule alone (decision 4).
- The block's per-litre plan tells its agent to multiply bottles by each bottle's volume;
  shipped and open everything are not told this (decision 6).
- Under `--rate-plan every` the per-litre question opens every water listing, so it tests no
  pruning.
- DeepSeek's serving provider varies within the providers decision 9 allows, and with it the
  price per token; H3 on tokens is reported beside H3 on cost.

## History and disclosure

- The model parser's prompt was written from paraphrases_v1's failures (prompt version 3, 23
  October). On 23 October it was probed on the 30 v1 rewordings with both models, and piloted on
  Larchmere with v1 rewordings and the templates; form version 13 (replies with reasoning or in
  parts) came from preparing that pilot. No v2 entry was used in any of it.
- The verifier read the prompt and v2 for its audits. It reported nothing from v2 beyond entry
  ids and counts, and no v2 text reached the parser's development.

## Decisions before the freeze

Each is the student's; the text above is written under the recommended option.

1. **Per-litre plan.** Every listing (`--rate-plan every`, recommended: no fact only the fixture
   knows) or the bound at the largest pack (shows pruning, but rests on the fixture's 19 litres).
2. **Budget.** What each model runs, the rounds, the stage caps and the reserve.
3. **Scripted reply.** `own` (recommended) or `menu` for every ask.
4. **The stop rule's own effect.** Add the block without its stop rule on the price questions,
   or state the limit above.
5. **Verdict of record.** (a) Fix the three rules that misread the block's own report
   (version 9), freeze, with the blind hand reading beside it (recommended); (b) freeze
   version 8, and the blind hand reading is the verdict of record; (c) freeze version 8, with
   the hand reading as a sensitivity only.
6. **Multipack hint.** Keep it and state it, remove it, or give the same sentence to open
   everything.
7. **Product scoping.** A shared rules step (recommended), or the model names the product.
8. **"As correct as open everything".** Descriptive, with its interval (recommended), or a
   non-inferiority test with a margin chosen now.
9. **DeepSeek provider.** (a) Unpinned and recorded (accepted on 22 October, before the pilot
   showed 2.16 times list price, mostly from two providers); (b) restricted to the fp8 providers
   at or below list price, GMICloud, DeepInfra and StreamLake, by a switchable change identical
   for every arm (recommended); (c) OpenRouter's cheapest-provider routing, which ranks by the
   advertised input price and would favour the provider with no cache discount.
10. **The word list overruling the model.** (a) Leave it, state it, and count asks on clear
    questions by arm (recommended); (b) turn a clash into an ask; (c) let the model's form win.
11. **A batch outside `require`.** Void, re-run and blocking only its own model (recommended), or
    blocking the whole analysis.
