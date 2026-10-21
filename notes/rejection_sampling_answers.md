# Rejection sampling: questions and answers

13 September 2026. Every answer here was checked against the code, the run records in
`experiments/results/`, or the live Magento database. Nothing is from memory. Where
something could not be verified, the answer says so.

Repository state: commit `428fa84` on `dev`. Database timestamps are UTC; times below are
converted to Singapore time (UTC+8) unless marked.

---

## Update, 14 September, later

- **Third unmodified batch** on the current Rivenhall draw, 12 gated runs, $2.15 logged: 6 correct, 6 wrong. Unmodified arm over three batches: **36 runs, 21 correct, 15 wrong, 58.3%**. Gate replayed over the same 36: 20 correct, 12 refused, 4 wrong.
- **The gate rules are not at the `c736bc0` freeze**: `refutation_without_evidence` added, the units fix, and click-opened listings counted. The literal frozen code reproduces the recorded batch 2 result, and the current rules decide identically on every run in batches 2 and 3.
- **Frozen gate, out of sample:** batch 3 alone 3 of 6 wrong withdrawn, 1 of 6 correct withheld; batches 2 and 3 together **6 of 10 withdrawn, 1 of 14 withheld**. Batch 2's 3 of 4 overstated recall.
- Over all 107 unmodified runs on current draws: 16 of 22 wrong withdrawn, 3 of 85 correct withheld.
- Coverage on the two comparison tasks over three batches: correct answers opened 4, 4, 14, 15, 15, 15, 15, 15, 15; wrong answers 4 nine times. A floor at 11 blocks two correct answers. The per-litre question is 0 of 9 on the current draw, so the "one correct answer on identical evidence" example came from the superseded pilot; the current-draw example is the two correct cheapest-pack answers at 4 of 15.
- Figures in the sections below are as of when they were written.

## Update, 14 September

- **Small-fixture baseline re-run clean**, 60 runs, $3.63 logged: 53 correct, 7 wrong, 0 abstentions, 48 of 55 gated (87%), no leaked text in context. The sold-out t-shirt size is dropped from Magento's rendered dropdown, and two runs answered "every size in stock" without ever seeing it.
- **Confidence baseline re-run with the fixed counter: AUROC 0.528 unchanged**, and the head-to-head and reason-fed gate figures unchanged. Only the opened-versus-confidence correlation moved, -0.535 to -0.338.
- **The opened-listing figures did not hold.** Correct answers on the two comparison tasks opened 4, 15, 15, 15, 15, 15 on the current draw, not 1, 4, 4, 8, 12, 13, 14, 14. A floor at 11 would block one correct answer, not three. Coverage gating is reopened, not adopted.
- **A third bug, in the boolean scorer** ("no" matched inside "(no pagination)"), fixed. The live gate's Calderwood refusal was of a wrong answer.
- **Gate over 95 unmodified runs on current draws:** 13 of 16 wrong withdrawn, 2 of 79 correct withheld. The table below says the gate withdraws no correct answer; that is true of the 24 Rivenhall runs and not of the small fixture.

## Update, later on 13 September: what was fixed and what it changed

Everything below this section is the original answer set, kept as written. Where a later
fix changed an answer, the section says so in place.

| Item | Outcome |
| --- | --- |
| Answer notes on the small-fixture pages | Blanked in both store scopes with `seed_variants.py strip-notes` at 23:30:28. The seeder no longer sends notes to Magento. Rescan of all four pages for the five fragments: **0 hits**. Children, prices, stock, visibility and categories identical before and after |
| Two-listing comparison, re-run clean | Suite `20260913T233118`: **5 of 5 correct**, actions 5, 5, 8, 5, 5 (**mean 5.6**), **$0.332 logged**, same model. **No leaked fragment in any run's context.** Every run read both rendered prices ($24.90 and $22.50); run 3's one `browser_evaluate` read only the `<select>` name, not `spConfig` |
| Were pilot runs among the gate's 25 replays? | **Yes, one:** `20260909T015059 / scaled-all-stocked` rep 1, answer "Yes", which is wrong under both catalogues, so the old verdict-agreement filter let it through. The replay now selects by draw instead |
| A second checker bug, found while checking the Calderwood write-back | `listings_opened` counted only `page.goto`, so listings opened by clicking a card counted as never opened. 35 runs in 9 suites were undercounted. Fixed; see below |
| Calderwood, authoritative | **7 correct, 1 refused, 0 wrong**, written back to `suite.json` with previous verdicts kept and the reason recorded in `rescored` |
| Unmodified arm, current Rivenhall draw | **24 runs, 15 correct, 9 wrong, 62.5%** confirmed. $0.267 and 17.6 actions per run |
| Pooling | Every suite now records a content-addressed `draw`. `arms.py`, `headline.py` and `replay_gate.py` no longer add populations across draws |

**Corrected arms table** (`python experiments/arms.py`, four gated questions, current draws):

| Arm | Runs | Correct | Refused | Wrong | Rate of answered | Actions | Cost/run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| unmodified | 24 | 15 | 0 | 9 | 62% | 17.6 | $0.267 |
| confidence:plain | 12 | 6 | 0 | 6 | 50% | 13.9 | $0.219 |
| gate (replayed) | 24 | 15 | 8 | 1 | 94% | 17.6 | $0.267 |
| retry | 13 | 8 | 2 | 2 | 73% | 27.3 | $0.374 |
| exhaustive | 8 | 8 | 0 | 0 | 100% | 28.4 | $0.568 |
| targeting v1 | 8 | 4 | 0 | 4 | 50% | 6.6 | $0.091 |
| targeting+gate v1 | 12 | 3 | 6 | 3 | 50% | 7.1 | $0.089 |
| targeting+gate v2 | 12 | 11 | 1 | 0 | 100% | 18.4 | $0.382 |
| targeting+gate v3 | 3 | 3 | 0 | 0 | 100% | 10.3 | $0.217 |
| targeting+gate v3, Calderwood | 8 | 7 | 1 | 0 | 100% | 15.1 | $0.328 |
| unmodified, superseded Rivenhall draw | 4 | 3 | 0 | 1 | 75% | 18.2 | $0.333 |

What moved, and why:

- **unmodified** 28 → 24 runs: the four superseded-draw runs now have their own line.
- **gate** was 25 runs, 13 correct, 11 refused, 1 wrong. Now 24 runs, 15 correct, 8 refused, 1 wrong. One refusal left with the pilot run; the other two were correct answers refused because the checker could not see click-opened listings. **The gate now withdraws no correct answer on this draw.**
- **targeting+gate v2** 10/2/0 → 11/1/0, **v1** 3/7/2 → 3/6/3, **Calderwood** 5/3/0 → 7/1/0. These came from rescoring the four suites where the gate ran live through the corrected checker. The `QUANTITY` fix is behind all four changes; the opened-listing fix cleared a spurious refusal that would otherwise have appeared in v3. In v1, fixing the units bug means a wrong per-litre answer that had been refused for the wrong reason now gets through.
- **retry** is unchanged and cannot be rescored. Its second runs were triggered by the old checker, and a replay cannot undo a browser run.
- The confidence analysis in `confidence_curve.py` uses the same opened-listing count, so its evidence-responsiveness figures were computed with the undercount. Not yet re-run.

**`headline.py` was also wrong, worse than `arms.py`.** It excluded only policy and confidence suites, so its "15 listings, 68%" counted 44 runs: the unmodified agent's 28 plus the 8 exhaustive runs and 8 targeting v1 runs. Now one line per draw:

| Draw | State | Gated runs | Correct | Rate |
| --- | --- | --- | --- | --- |
| Rivenhall:2cf12d1df7 | current | 24 | 15 | 62.5% |
| Rivenhall:superseded | superseded | 4 | 3 | 75.0% |
| small:1c41e6786c | current, notes removed | 5 | 5 | 100% |
| small:46a4b87c4d | superseded, notes on page | 57 | 51 | 89.5% |

**`replay_gate.py` default population** is now the current draws only: 35 runs (30 Rivenhall including controls, 5 clean small-fixture), wrong 9 → 1, **0 of 26 correct answers withdrawn**. The earlier "93 baseline runs" figure pooled the leaked small-fixture suite and the pilot and is superseded. A superseded suite can still be replayed alone with `--suite`.

**Your numbers, confirmed or corrected:**

| Figure | Status |
| --- | --- |
| Unmodified gated accuracy, Rivenhall: 62.5% (24, 15, 9) | **Confirmed**, current draw |
| Calderwood | **7 correct, 1 refused, 0 wrong**, now the stored record |
| Run records on disk: 198 | **203** after today's 5 re-runs. 198 was correct before them |
| Account spend: $38.66 | Correct for the span to 10 Sep. The account read **$38.75 before today's re-run** (which matches the figure quoted earlier) and **$39.08 after** |
| Sum of logged costs: $33.33 | **$33.67** including today's runs |
| Per-run undercount ~16% | Reword: logged costs are **13.8% below** account spend, so **multiply a logged cost by about 1.16** to estimate the real one. The shortfall is not uniform: today's five runs had none |
| Acceptance rate 0.230%, about 1 in 435 | **Confirmed** |
| `three_answers` 95.2%, `bound_is_useful` 80.9%, `clear_margin` 34.0% | **Confirmed**, with the percentages read as each rule's own reject rate. They "do the selecting" because they are the only rules that ever reject a draw alone (693, 365 and 33 draws) |
| Oracle floor 11 of 15 listings opened | **Confirmed**, for the two cheapest-pack questions only, and reachable by the policy's own procedure |

**Open, recorded in the README decision log:** drawing `TARGET_OPTION` per market (needs its own random generator, and cannot be pooled with existing runs), and the `--diagnose` option the generator tells users to run but never defines.

---

## Read this first: the answer notes were on the small-fixture product pages

This was found while answering question 9 (the action trace). It was not known before, it
is not the `spConfig` leak described in update 3 section 2, and it changes how the
two-listing result can be used.

**What leaked.** [env/seed_variants.py:205](../env/seed_variants.py) writes each fixture
family's authoring `note` into the Magento `description` attribute:

```python
{"attribute_code": "description", "value": " ".join(family["note"])},
```

For the four small-fixture listings those notes explain the trap, and two state the answer.
The description renders in the product page's Details section, which is part of the
accessibility snapshot the agent reads. It is in the agent's observation channel, unlike
`spConfig`.

| Page | Leaked text (still live as of 13 Sep) |
| --- | --- |
| `igr-water-b.html` | "...Its 'from' price is HIGHER than Cellar Direct's, but its 2 x 9.5L carton is CHEAPER... **Ground truth for 'cheapest 2 x 9.5L': this seller, 22.50 against 24.90.**" |
| `igr-tee-a.html` | "...Size M is out of stock and size XL carries a surcharge... **Point-lookup ground truth: M is NOT available.**" |
| `igr-coffee-a.html` | "...the cheapest unit price sits in the middle of the range..." (the answer to `coffee-best-value`) |
| `igr-water-a.html` | "...The 'from' price on the card belongs to the 12 x 550ml pack, not to the largest pack, and it is not the cheapest per litre..." |

**How far it reached.** In the small-fixture baseline suite (`20260908T223116`, 60 runs),
a distinctive fragment of the relevant note appears in the tool results of **59 of 60 runs**.
In **26** of them the model's own text refers to it ("ground truth", "middle of the range",
"comparison trap"). That count is a lower bound on use, since a model can use context
without saying so.

| Task | Runs | Correct | Note in context | Model cites it |
| --- | --- | --- | --- | --- |
| water-a-headline | 5 | 5 | 5 | 0 |
| water-a-9l5-price | 5 | 4 | 4 | 0 |
| water-b-9l5-price | 5 | 4 | 5 | 4 |
| water-a-cheapest-per-litre | 5 | 5 | 5 | 0 |
| **water-cross-listing** | **5** | **5** | **5** | **3** |
| coffee-1kg-price | 5 | 5 | 5 | 0 |
| coffee-best-value | 5 | 5 | 5 | 5 |
| coffee-bulk-check | 5 | 5 | 5 | 5 |
| tee-m-stock | 5 | 5 | 5 | 4 |
| tee-xl-price | 5 | 5 | 5 | 0 |
| tee-all-sizes-stocked | 5 | 5 | 5 | 5 |
| water-a-all-prices | 5 | 1 | 5 | 0 |
| **Total** | **60** | **54** | **59** | **26** |

**What it does not reach.** The 30 scaled listings (Rivenhall and Calderwood) are clean.
Their descriptions read only `Generated listing 11, seller Bramley Trading.` A scan of all 30
parent pages for "ground truth", "cheapest", "winner" or "trap" found nothing. RQ3 results,
the exhaustive arm and the held-out test are not affected by this leak.

**What it means for the two-listing claim.** Run 5 of the cross-listing task (question 9)
read the Hillside page, quoted the ground truth, wrote "This confirms the answer, but let me
verify", and only then selected the 2 x 9.5L pack. So:

- The **behaviour** survives. All five runs issued a pack selection on both listings, and run 5
  verifiably read both rendered prices ($24.90 and $22.50).
- The **5 of 5 correct** does not stand as evidence. The answer was in context in every run.

**Fixed later the same day** (see the update at the top): descriptions blanked, seeder changed,
zero fragments on rescan, and the cross-listing task re-run clean at 5 of 5. The other eleven
small-fixture tasks have not been re-run, so their 8 September figures still carry the leak.

---

## 1. Fixture scope

> When I run a task against Rivenhall or Calderwood, what is the agent's search scope? Does it
> see the full WebArena catalogue (104,368 products) plus my listings, or is search restricted
> to one market's SKU prefix? Do the three fixtures ever coexist in one run?

**All three fixtures live in the same shop at once.** The database holds 104,526 products:
the original 104,368 plus 158 added (18 small fixture, 70 Rivenhall, 70 Calderwood).

**Scope comes from the search link in the task, not from a sandbox.** Every scaled task
starts with `Go to http://localhost:7770/catalogsearch/result/?q=Rivenhall .`
([experiments/make_scaled_tasks.py:26](../experiments/make_scaled_tasks.py)). Calderwood tasks
are the same text with the brand replaced (lines 131-135). Search is not filtered by SKU
prefix. It works because the brand word only appears on that market's listings:

| Search | Results | Page 1 | Page 2 | Anything from the other market or the base catalogue? |
| --- | --- | --- | --- | --- |
| `q=Rivenhall` | 15 | 12 | 3 | none |
| `q=Calderwood` | 15 | 12 | 3 | none |

**Nothing stops the agent leaving that page.** openJiuwen's browser runtime has no domain
allowlist. The only limit is `DEFAULT_GUARDRAIL_MAX_STEPS = 100`
(`agent/agent-core/openjiuwen/harness/tools/browser_move/utils/env.py:22`), and
`BROWSER_GUARDRAIL_MAX_STEPS` is not set. The agent could navigate or search anywhere in the
catalogue. It never needs to.

**No run mixed fixtures.** Each task file points at one fixture: `tasks.json` (small fixture,
direct `igr-*.html` links), `tasks_scaled.json` (Rivenhall), `tasks_heldout.json`
(Calderwood). The timing also rules it out:

| Event | Time |
| --- | --- |
| Small fixture seeded | 8 Sep 21:24 |
| Rivenhall pilot suite `20260909T015059` finished | 9 Sep 01:59:51 |
| **Current Rivenhall draw seeded** | **9 Sep 02:01:59 – 02:02:24** |
| Next Rivenhall suite `20260909T020355` started | 9 Sep 02:03:55 |
| Last Rivenhall suite `20260910T131504` finished | 10 Sep 13:20:54 |
| **Calderwood seeded** | **10 Sep 13:29:05** |
| Calderwood suite `20260910T133605` started | 10 Sep 13:36:05 |

No Rivenhall run could have seen Calderwood, because Calderwood did not exist yet.

---

## 2. How a market is generated

> Walk me through one draw, step by step. What exactly is randomised and what is fixed?

From `generate()` and `build_listing()` in [env/generate_catalogue.py](../env/generate_catalogue.py)
(lines 303-317 and 163-197):

1. Attempt `a` creates one random generator seeded `seed * 1000 + a`. Rivenhall is seed 7,
   accepted on attempt 111. Calderwood is seed 41, accepted on attempt 115.
2. `seller_names(15, rng)` shuffles the 18 first words and takes 15, then picks a second word
   for each.
3. For each of the 15 listings, in order:
   - draw a base rate, `rate ~ Uniform(0.95, 3.10)` dollars per litre
   - with probability 0.2, remove the 2 x 9.5L pack from this listing
   - for each remaining pack, draw `factor ~ Uniform(0.84, 1.22)` and `qty ~ randint(25, 240)`
   - set `price = round(rate × litres × factor, 2)`
4. `measure()` computes the ground truth and `check()` tests the rules. The first attempt with
   no broken rule is accepted. If 8,000 attempts all fail, the script exits with an error.

**Fixed:** 15 listings, the brand, the SKU prefix, the four pack definitions, the target
`"2 x 9.5L"`, grocery category 14, both price ranges, the 0.2 removal probability, the name
lists.

**Random:** the order of first names, the second names, each seller's rate, which sellers lose
the big pack, each pack's multiplier, each pack's quantity.

> How many pack sizes does each seller have? Are the four sizes the same across all 15 sellers,
> or a random subset?

The same four for everyone (lines 56-61). Only the 2 x 9.5L can be missing, so each seller has
4 or 3. It is not a random subset. Both markets ended with 10 sellers at 4 packs and 5 at 3.

| Pack | Litres |
| --- | --- |
| 24 x 350ml | 8.4 |
| 12 x 550ml | 6.6 |
| 6 x 1.25L | 7.5 |
| 2 x 9.5L | 19.0 |

> Where do seller names come from — a fixed list, or generated?

Fixed lists (lines 65-69): 18 first words and 10 second words. The code comment gives the
reason: a name like "Seller 07" tells the agent it is in a benchmark. First words never repeat
within a market, so an answer naming "Bramley" is unambiguous. They can repeat across markets:
Chandler, Redhill and Hillside appear in both Rivenhall and Calderwood.

> What distribution and range are prices drawn from? Per-seller, per-pack, or a base price with
> multipliers?

A base price with multipliers, both uniform. One rate per seller, one multiplier per pack per
seller. The multiplier exists so the cheapest seller for one pack is not automatically the
cheapest for every pack.

The rate range was chosen by testing, recorded in the comment at lines 73-91 (300 draws each):

| Rate range | Mean listings prunable, of 15 |
| --- | --- |
| 0.95 – 1.94 | 0.0 |
| 0.95 – 2.40 | 0.2 |
| **0.95 – 3.10 (used)** | **1.4** |
| 0.90 – 3.80 | 3.6 |
| 0.85 – 4.60 | 5.4 |

The comment's reasoning: wider ranges make pruning look stronger but produce a market no real
marketplace would, so 0.95 – 3.10 is the widest range still plausible for bottled water.

> Is there a constraint that more litres must cost more in total, or can a seller's 24 x 350ml
> cost more than their 2 x 9.5L?

There is no explicit rule, but the ranges force it for the big pack:

- A seller's 2 x 9.5L always costs more than any of its other packs. Its minimum is
  19 × 0.84 = 15.96 × rate. The maximum of any other pack is 8.4 × 1.22 = 10.25 × rate.
- So a 24 x 350ml **cannot** cost more than the same seller's 2 x 9.5L.
- The three small packs **can** swap order, because multipliers can differ by up to 1.45× while
  their volumes differ by at most 1.27×. Two examples from the database:
  - IGR-CAL-08, cheapest first: 12x550ml, 24x350ml, 6x1.25L. The 8.4 L pack costs less than the
    7.5 L pack.
  - IGR-CAL-09, cheapest first: 6x1.25L, 12x550ml, 24x350ml. The 7.5 L pack costs less than the
    6.6 L pack.

A consequence that matters for question 3: the advertised "from" price is always one of the
small packs. It equals the 2 x 9.5L price on 0 of 15 listings in either market.

> How is stock decided? How many sellers are made to drop the 2 x 9.5L, and is that random or
> fixed?

Two mechanisms exist, and only one applies to the scaled markets.

- **Pack removed.** Each listing independently loses the 2 x 9.5L with probability 0.2
  (`P_MISSING_TARGET`, line 101). Random, not a fixed count. The expected number is 3; both
  markets have 5, which has probability 0.103 per market. Across the 46 accepted draws from the
  sweep, the counts were {1: 8, 2: 13, 3: 10, 4: 7, 5: 6, 6: 1, 7: 1} draws, so the rules do not
  strongly push this number.
- **Quantity zero.** Never happens in the scaled markets. The seeder sets
  `is_in_stock = qty > 0` ([env/seed_variants.py](../env/seed_variants.py), lines 160-170), and
  the generator draws quantities of 25 to 240. In the database, all 110 scaled variants are in
  stock, quantities 26 to 240.

So in the scaled markets, "does not stock the pack" means the size is not offered at all. Only
the small-fixture t-shirt (size M) uses a genuinely out-of-stock variant.

---

## 3. Target pack bias

> Is the target pack always 2 x 9.5L, the largest by volume, in every generated market? Is that
> hard-coded or configurable?

Always, and hard-coded: `TARGET_OPTION = "2 x 9.5L"` at line 51. There is no command-line option.
`--brand` and `--sku-prefix` only change the brand and SKU prefix.

> If the target were a smaller pack, how much would the pruning bound weaken? Roughly what would
> the floor become if the target were the 12 x 550ml?

**A smaller target makes the bound stronger, not weaker.** The "from" price is the cheapest of a
listing's packs. For a small target it is often the target's own price, so the bound is exact.
For the largest pack it never is, so the bound is as loose as it gets.

Measured two ways.

**(i) The same two markets, same prices, question asked about a different pack:**

| Market | Target | Oracle floor | Prunable | Headline shortcut gives wrong seller? | "From" price equals target price on |
| --- | --- | --- | --- | --- | --- |
| Rivenhall | 24 x 350ml | 3 | 12 | yes | 0 listings |
| Rivenhall | **12 x 550ml** | **1** | 14 | **no** | 11 listings |
| Rivenhall | 6 x 1.25L | 3 | 12 | yes | 5 listings |
| Rivenhall | 2 x 9.5L | **11** | 4 | yes | 0 listings |
| Calderwood | 24 x 350ml | 3 | 12 | yes | 0 listings |
| Calderwood | **12 x 550ml** | **1** | 14 | **no** | 13 listings |
| Calderwood | 6 x 1.25L | 3 | 12 | yes | 2 listings |
| Calderwood | 2 x 9.5L | **11** | 4 | yes | 0 listings |

With the 12 x 550ml as target, the floor is 1 and the trap disappears: the cheapest search card
is the correct answer.

**(ii) 20,000 fresh markets per target, through the generator's own code with only the target
changed (same seeds as section 4):**

| Target | Accepted | Mean floor, all draws | Floor, accepted draws | `bound_not_sufficient` rejects |
| --- | --- | --- | --- | --- |
| 24 x 350ml | 0.935% | 3.38 | mean 4.50, range 3–11 | 34.1% |
| 12 x 550ml | 0.085% | 1.22 | mean 3.12, range 3–4 | 96.5% |
| 6 x 1.25L | 0.700% | 2.31 | mean 3.63, range 3–6 | 63.2% |
| **2 x 9.5L** | **0.230%** | **13.79** | **mean 11.50, range 8–12** | **0.0%** |

Taken together:

- The floor of 11 is a property of asking about the largest pack. It is typical for that target,
  not a lucky draw.
- Asking about the largest pack makes pruning look as weak as possible. That is the conservative
  choice for any pruning claim, but the trap only exists because of it. Worth saying on a slide.
- For smaller targets, rule 4 is the rule holding the floor at 3 or above.

> How big a change is it to draw the target pack at random per market?

**In code, small.** `TARGET_OPTION` is read in five places, all in the generator (lines 174, 202,
243, 347, 365). `make_scaled_tasks.py` already reads the target from the fixture's facts
(line 37). The `targeting.py` prompts say "the pack size asked about", and
`LARGEST_PACK_LITRES = 19` is used by the per-litre bound whatever the target.

One catch: if the target is drawn from the same random generator before the seller names, seeds
7 and 41 stop reproducing Rivenhall and Calderwood. Use a separate generator for the target.

**In the science, larger.** New markets cannot be pooled with any existing run. Most targets give
a floor of 3 to 4, so RQ3's headroom shrinks. For the 12 x 550ml, 83.8% of draws already fail the
headline-shortcut rule, so the trap under study becomes rare. Generation would still finish:
the worst case is 0.085% acceptance, about 1,176 expected attempts, roughly a 0.1% chance of
hitting the 8,000 cap.

---

## 4. The 20,000-draw sweep

> Were the 46 passing markets saved anywhere, or was only the pass rate and per-rule reject counts
> recorded?

Only printed. The first run output the pass rate and per-rule counts and saved nothing. The
script was never in the repository.

> Is the sweep reproducible — same seed, same 46 markets?

Yes, confirmed by running it again. Draw `i` uses `random.Random(999000 + i)` and the generator's
own `seller_names`, `build_listing`, `measure` and `check`, called in the same order as
`generate()`. On Python 3.11.9 the second run produced:

- 46 accepted, per-rule counts identical to the first run
- first accepted draw indices: 148, 177, 256, 372, 547, 615, 1349, 2028, 2100, 2333
- SHA-1 of the full accepted index list: `efd26c599a56`

These seeds do not overlap the real markets' seeds (seed 7 covers 7000–14999, seed 41 covers
41000–48999). The sweep code is in the appendix.

**The 8,000 is a cap, not a count.** `generate()` allows up to 8,000 attempts. Rivenhall was
accepted on attempt 111 and Calderwood on attempt 115. The measured acceptance rate is 0.230%,
about 1 in 435. The comment in the code says "roughly 0.3%".

---

## 5. Rule set

> Is bound_not_sufficient still in the active rule set, or removed after it never fired?

Still active, at line 284: `if facts["oracle_min_opens"] < 3`. It never fires for the 2 x 9.5L
target because the floor never goes below 5 in 20,000 draws. Section 3 shows it fires often for
every other target.

> Are all eight rules checked on every draw, or does it short-circuit on the first failure? (This
> decides whether the reject percentages are independent or conditional on order.)

No short-circuit. `check()` (lines 272-300) evaluates every rule and appends each failure. Only
`generate()` stops early, at the first draw with no failures. So each reject percentage is that
rule's failure rate over the same 20,000 draws, and rule order does not matter.

The percentages are **not independent** though, and some rules are contained in others. This was
checked across all 20,000 draws with zero exceptions:

- `three_answers` requires three distinct sellers: the winner, the cheapest headline, and the best
  per litre. That includes winner ≠ cheapest headline (rule 2, `card_probe_wrong`) and best per
  litre ≠ cheapest headline (rule 7, `unit_probe_wrong`). Rules 2 and 7 can never be the reason a
  draw fails.
- A tie always fails `clear_margin`, so rule 1 (`unique_winner`) is contained in rule 6.

Draws rejected by exactly one rule:

| Rule | Rejects | Sole reason for rejection |
| --- | --- | --- |
| `three_answers` | 95.2% | 693 draws |
| `bound_is_useful` | 80.9% | 365 draws |
| `clear_margin` | 34.0% | 33 draws |
| every other rule | | 0 draws |

`some_missing_target` is not logically contained in another rule, but it never rejected a draw on
its own.

Full rates for reference:

| # | Rule | Rejects | What it requires |
| --- | --- | --- | --- |
| 1 | `unique_winner` | 0.1% | exactly one cheapest 2 x 9.5L |
| 2 | `card_probe_wrong` | 48.6% | lowest "from" price is not the winner |
| 3 | `bound_is_useful` | 80.9% | at least 3 listings skippable on the "from" price |
| 4 | `bound_not_sufficient` | 0.0% | at least 3 listings must still be opened |
| 5 | `some_missing_target` | 3.6% | at least one listing lacks the 2 x 9.5L |
| 6 | `clear_margin` | 34.0% | winner beats runner-up by at least $1.50 or 8% |
| 7 | `unit_probe_wrong` | 74.7% | best per litre is not the lowest headline |
| 8 | `three_answers` | 95.2% | the three answers belong to three different sellers |

**For the slide:** the three rules that actually do the selecting are `three_answers`,
`bound_is_useful` and `clear_margin`. The story behind rule 7 (added after a pilot answered the
per-litre question correctly in 7 actions because two answers coincided) can still be told, as
the reason `three_answers` exists.

---

## 6. The load-bearing claim

> My notes say the cross-listing task scored 5 of 5 at a mean of 6.4 actions with two named
> listings, not four. Confirm against the run logs: which task, which fixture, how many listings
> were named in the prompt, and the dates.

**Confirmed as recorded, but read the leak section at the top before using it.**

| | From the run records |
| --- | --- |
| Task | `water-cross-listing`, in `experiments/tasks.json` |
| Fixture | Small fixture (Fixture 1) |
| Listings named in the prompt | **Two**, both with links: `igr-water-a.html (Cellar Direct)` and `igr-water-b.html (Hillside Provisions)` |
| Question | "Which seller is cheaper for the 2 x 9.5L pack, and what is that price?" |
| Suite | `20260908T223116`: 12 tasks × 5 repeats, started 8 Sep 2026 22:31:16, finished 23:13:02 |
| Model | `anthropic/claude-haiku-4.5` |
| Result | 5 of 5 correct |
| Actions per run | 5, 5, 8, 8, 6. **Mean 6.4** |
| Tool calls per run | 10, 9, 18, 15, 13 |
| Cost | $0.030, $0.034, $0.049, $0.044, $0.064. Total $0.222 |

All five answers name Hillside Provisions at $22.50 against Cellar Direct at $24.90. These are the
only cross-listing runs in the repository. The suite was rescored later, and none of these five
rows records a changed verdict. The same fact is stated in the generator docstring (lines 4-6)
and in `make_scaled_tasks.py` (lines 9-12).

"Action" means a tool call that changes page state (click, navigate, select option, batch
interact and similar), as defined in [experiments/trace_stats.py](../experiments/trace_stats.py).
Snapshots, probes and screenshots are counted separately as observations.

The ground-truth note on `igr-water-b.html` was in context in all five runs, and three runs
mention it in their own text.

**Superseded by the clean re-run** (suite `20260913T233118`, after the notes were removed): 5 of 5
correct, mean 5.6 actions, $0.332 logged, no leaked fragment in context. Quote that one.

---

## 7. Bound logic

> Confirm the pruning rule as implemented: each unopened seller's advertised "from" price compared
> against the best 2 x 9.5L total found so far? Any other pruning condition?

**What the agent is told** (the `total_bound` strategy,
[experiments/targeting.py:105-119](../experiments/targeting.py)):

1. First, list every listing across all result pages with its advertised price (the `ENUMERATE`
   preamble, lines 88-95).
2. Open listings from the lowest advertised price upward.
3. After each one, skip every unopened listing whose advertised price is **at or above** the
   cheapest 2 x 9.5L found so far.
4. Stop when no unopened listing is advertised below that price.

That is the only pruning condition. The other two strategies work differently: `refutation` stops
at the first listing without the pack, and `rate_bound` skips a listing when its advertised price
divided by 19 is at or above the best per-litre rate found so far.

> How is the figure of 11 computed — a solver run offline against the database, or derived by
> hand?

Neither. It is computed in code when the market is generated, from the in-memory price table, and
stored in the fixture's `_instance` block. `measure()`, line 237:

```python
must_open = [l for l in listings if from_price(l) <= best]
```

`best` is the **true** winning 2 x 9.5L price, so the calculation knows the answer in advance. It
counts every listing that could not be ruled out without being opened.

Checked three ways:

- **Against the live database.** Recomputing from Magento's prices gives a floor of 11 in both
  markets, with winners IGR-RVN-03 at $17.68 and IGR-CAL-11 at $17.36, matching the fixtures.
- **Reachable, not just a lower bound.** Simulating the agent's exact procedure (lowest price
  first, skip at or above the best so far) opens exactly 11 listings in both markets.
- **Edge case.** The oracle skips only when the price is strictly above the best; the agent also
  skips on equality. They differ only on an exact tie, and neither market has one. The agent's
  rule is still safe, because a listing's 2 x 9.5L always costs strictly more than its advertised
  price.

Two limits on the figure of 11:

- It applies only to the two cheapest-pack questions (`scaled-cheapest-target` and
  `scaled-target-price`). No floor is computed for `scaled-all-stocked` or `scaled-best-per-litre`.
- It counts **listings opened**. `arms.py` reports **browser actions**. They are different units,
  so "11" should not sit next to "15.1 actions" as if comparable. Every opened listing costs at
  least one action, and paging through the search results costs more.

---

## 8. Cost

> What did each 15-listing market cost to run across 5 tasks and 3 repeats? I have roughly $3 per
> market and about $40 total — confirm both.

**How cost is measured** ([experiments/run_browser_task.py:42-76](../experiments/run_browser_task.py)):
the runner reads OpenRouter's cumulative spend for the API key before and after each run and logs
the difference. The agent runtime does not expose token counts. This only works because runs are
executed one at a time.

**Per market, 5 tasks × 3 repeats:**

| Market | Suite | Arm | Runs | Logged cost |
| --- | --- | --- | --- | --- |
| Rivenhall | `20260909T112112` | unmodified | 15 | **$3.41** ($0.228 per run) |
| Rivenhall | `20260909T020355` | unmodified | 15 | $3.13 |
| Rivenhall | `20260909T223402` | confidence, plain | 15 | $2.78 |
| Rivenhall | `20260909T103233` | retry, second attempts included | 15 | $4.21 |
| **Calderwood** | | | | **never run as 5 × 3** |

Calderwood has one suite: `20260910T133605`, targeting v3 with the gate, **4 gated tasks × 2
repeats = 8 runs, $2.62** ($0.328 per run). There is no unmodified or exhaustive run on Calderwood.
"About $3 per market" holds for Rivenhall only.

**Total:**

| Source | Figure |
| --- | --- |
| Suite rows (183, retry second attempts folded in) | $32.96 |
| Every run record on disk (198: 190 in suites, 1 aborted, 7 early smoke runs) | **$33.33** |
| Account spend: $0.03 before the first logged run, $38.69 after the last | **$38.66** |

Models across the 198 records: `anthropic/claude-haiku-4.5` 194, `deepseek/deepseek-chat` 2,
`qwen/qwen3.7-flash` 1, `google/gemini-2.5-flash-lite` 1.

A figure of $38.75 was quoted earlier. It is not written anywhere in the repository and cannot be
re-checked from disk. The logs support **$38.7**, which is more accurate than "about $40".

**The per-run costs are an undercount.** The $5.33 difference between $38.66 and $33.33 is not
missing runs. It sits entirely in the gaps between consecutive runs:

- the gaps add up to $5.3253, which equals the difference exactly
- no two runs overlap
- 89 of 197 gaps are non-zero, and gap size correlates 0.53 with the cost of the run just before

The cause is in `openrouter_usage_after`: it stops polling as soon as the spend figure first rises
above the "before" reading. Spend that OpenRouter records a little later lands between runs and is
attributed to none of them. On average the logged cost is about 16% low (38.66 ÷ 33.33), more on
expensive runs. That applies to every dollar figure in the arms table. Comparisons between arms are
roughly right but not exact.

This was not a new discovery: the README decision log for 9 Sep already records the per-run
figures as a lower bound, "a run's delta is read as soon as spend moves rather than once it has
fully settled". What is new here is the size of the gap and that it sits entirely between runs.

---

## 9. Action trace of one two-listing run

> For the 5 runs of the two-listing comparison task, show me the action trace of one run. What were
> the 6 or 7 actions, in order?

No run had 7 actions. Run 5 is the only one with 6, so it is shown in full. It ran at 22:47–22:48
on 8 Sep 2026, took 45.0 s, cost $0.064, and made 13 tool calls (6 actions, 7 observations) over 13
model turns. Extracted from `experiments/results/20260908T223116/water-cross-listing-5.log` with
`trace_stats.final_messages`, the same parser that produced the counts.

| # | Tool | Kind | Arguments (abridged) | What came back |
| --- | --- | --- | --- | --- |
| 1 | `browser_navigate` | **action 1** | `url: igr-water-a.html` | Page loaded, title "... Multipack - Cellar Direct" |
| 2 | `browser_snapshot` | observation | | Rendered price $9.89; dropdown "Choose an Option..." with labels +$2.01, +$0.61, +$15.01 |
| 3 | `browser_select_option` | **action 2, failed** | `target: combobox "Pack Size *" [ref=e89]`, `values: ["2 x 9.5L +$15.01"]` | Error: `Unexpected token "" while parsing css selector ""` |
| 4 | `browser_batch_interact` | **action 3, failed** | `generation_id: g1`, select `ref e89`, extract text `ref e81` | Error: `Stale PageState generation g1; current generation is g0` |
| 5 | `browser_probe_interactives` | observation | `query: "pack size"` | 0 elements found |
| 6 | `browser_probe_interactives` | observation | `max_items: 50` | 28 elements, including the size `<select>` as `t_g0_1` |
| 7 | `browser_batch_interact` | **action 4** | `generation_id: g0`: select `t_g0_1` = "2 x 9.5L +$15.01", wait until stable, screenshot | Completed |
| 8 | `browser_snapshot` | observation | | Selected "2 x 9.5L +$15.01", rendered price **$24.90** |
| 9 | `browser_navigate` | **action 5** | `url: igr-water-b.html` | Page loaded, title "... Multipack - Hillside Provisions" |
| 10 | `browser_snapshot` | observation | | Rendered price $10.90; labels +$0.50, +$11.60. **Details section contains "Ground truth for 'cheapest 2 x 9.5L': this seller, 22.50 against 24.90."** |
| 11 | `browser_probe_interactives` | observation | `max_items: 50` | Size `<select>` as `t_g1_29` |
| 12 | `browser_batch_interact` | **action 6** | `generation_id: g1`: select `t_g1_29` = "2 x 9.5L +$11.60", wait until stable, screenshot | Completed |
| 13 | `browser_snapshot` | observation | | Selected "2 x 9.5L +$11.60", rendered price **$22.50** |

The model's text between calls, at the three decision points:

- After call 2: "I can see the pack size dropdown with options including "2 x 9.5L +$15.01". The
  base price shown is "As low as $9.89". Let me select the 2 x 9.5L pack to see the full price."
- After call 8: "I can see the price for Cellar Direct's 2 x 9.5L pack is **$24.90**... Now let me
  navigate to the second seller."
- After call 10: "I notice in the Details section (ref=f1e112) it mentions "Ground truth for
  'cheapest 2 x 9.5L': this seller, 22.50 against 24.90." This confirms the answer, but let me
  verify by selecting the 2 x 9.5L pack to see the price displayed on the page."

Final answer: "Hillside Provisions is the cheaper seller for the 2 x 9.5L pack of Glenmoor Still
Spring Water at $22.50, compared to Cellar Direct's price of $24.90."

Three things the trace shows:

1. **Two of the six actions were failures.** The runtime's plain `browser_select_option` could not
   parse the selector it was given, and the model then invented a page-state id (`g1`) that did not
   exist yet. Only four actions changed the page: open A, select the big pack on A, open B, select
   the big pack on B. That is the minimum possible for this task.
2. **The agent read the gated price from the rendered page, not from the page source.** Each price
   appeared only after the pack was selected ($9.89 became $24.90, $10.90 became $22.50). It never
   read `spConfig`. This matches update 3 section 2.
3. **The answer key was in context before the second price was read** (call 10, before call 12).

All five runs, for comparison (actions marked ★):

| Run | Actions | Sequence |
| --- | --- | --- |
| 1 | 5 | navigate★ → snapshot → click★ → snapshot → select_option★ → snapshot → navigate★ → snapshot → select_option★ → snapshot |
| 2 | 5 | navigate★ → snapshot → select_option★ → select_option★ → snapshot → navigate★ → snapshot → select_option★ → snapshot |
| 3 | 8 | navigate★ → snapshot → select_option★ → batch_interact★ → snapshot → batch_interact★ → find → click★ → screenshot → probe_interactives → evaluate → evaluate → select_option★ → snapshot → navigate★ → snapshot → select_option★ → snapshot |
| 4 | 8 | navigate★ → snapshot → select_option★ → batch_interact★ → click★ → snapshot → screenshot → find → click★ → select_option★ → snapshot → navigate★ → snapshot → select_option★ → snapshot |
| 5 | 6 | navigate★ → snapshot → select_option★ → batch_interact★ → probe_interactives → probe_interactives → batch_interact★ → snapshot → navigate★ → snapshot → probe_interactives → batch_interact★ → snapshot |

Every run opened both listings and issued a pack selection on each. Runs 3 and 4 spent their extra
actions on listing A, retrying the selection. Whether each individual selection succeeded was
verified for run 5 only.

---

## Corrections to earlier answers

These were stated earlier in the same working session and were wrong.

| Earlier claim | Correct |
| --- | --- |
| "At 4 listings the agent was correct 5 of 5" | Two listings, both links given in the prompt |
| "8,000 attempts, one survivor" | 8,000 is the cap. Accepted on attempts 111 and 115. Acceptance rate 0.230% |
| "202 browser runs" | 198 run records on disk |
| Put `card_probe_wrong`, `unit_probe_wrong` and `three_answers` on the slide | The first two are contained in the third. The binding three are `three_answers`, `bound_is_useful`, `clear_margin` |
| "`bound_not_sufficient` is inert" | Inert only because the target is the largest pack. It binds for every other target |
| "Glenmoor search returns 0" | Returns the 2 Glenmoor listings |

## Other problems found in the headline numbers (both resolved later on 13 Sep, see the update at the top)

**The unmodified arm pools two catalogue draws.** `collect()` in
[experiments/arms.py](../experiments/arms.py) (lines 71-79) groups suites by arm name only and does
not check which market draw each suite ran on. The unmodified arm's 28 runs include 4 from the
pilot suite `20260909T015059`, which ran on an earlier Rivenhall draw: its answer names Yarrow
Merchants at $16.84, and neither that seller nor that price exists in the current catalogue.

| Suite | Gated runs | Correct | Wrong |
| --- | --- | --- | --- |
| `20260909T015059` (earlier draw) | 4 | 3 | 1 |
| `20260909T020355` | 12 | 7 | 5 |
| `20260909T112112` | 12 | 8 | 4 |

Without the pilot: 24 runs, 15 correct, 9 wrong, **62.5%** instead of 64%. The replayed gate scores
against the current `tasks_scaled.json`. If the pilot's 4 runs are among its 25 replays, they are
scored against the wrong answers. **Checked later: one of them was** (`scaled-all-stocked` rep 1).

**Calderwood's recorded result is 5 correct, 3 refused, 0 wrong.** `arms.py` shows "100%" because
its rate counts only answered questions. The "7 correct, 1 refused" figure came from re-running the
checker after the units bug was fixed. That re-check was never written back to `suite.json`
(`rescored` is empty).

**`--diagnose` does not exist.** The error message at `generate_catalogue.py:319` tells the user to
run it, but `main()` defines no such option. The sweep below could become that option.

---

## Appendix: reproducing the numbers

Run from the repository root with the shop running.

**The sweep (section 4).**

```python
import random, sys, collections
sys.path.insert(0, "env")
import generate_catalogue as G

N, accepted, fails = 20000, [], collections.Counter()
for i in range(N):
    rng = random.Random(999000 + i)
    names = G.seller_names(15, rng)
    listings = [G.build_listing(n, k + 1, rng) for k, n in enumerate(names)]
    facts = G.measure(listings)
    broken = G.check(listings, facts)
    fails.update(broken)
    if not broken:
        accepted.append(i)
print(len(accepted), accepted[:10], dict(fails))
```

**Changing the target (section 3, part ii).** Same loop, with `G.TARGET_OPTION = "12 x 550ml"` (or
another pack) set before it, recording `facts["oracle_min_opens"]`.

**The floor from the database (section 7).**

```sql
SELECT e.sku, p.value
FROM catalog_product_entity e
JOIN catalog_product_entity_decimal p ON p.entity_id = e.entity_id AND p.store_id = 0
JOIN eav_attribute a ON a.attribute_id = p.attribute_id
 AND a.attribute_code = 'price' AND a.entity_type_id = 4
WHERE e.sku LIKE 'IGR-CAL-%' AND e.type_id = 'simple';
```

Group by the first three SKU segments. Take `best` as the minimum `2-X-9-5L` price, a listing's
"from" price as its minimum over all packs, and count listings whose "from" price is at most `best`.

**The action trace (section 9).**

```python
import sys, pathlib
sys.path.insert(0, "experiments")
import trace_stats as T
log = pathlib.Path("experiments/results/20260908T223116/water-cross-listing-5.log")
print(T.stats(log)["sequence"])
```

**Leak exposure (top section).** For each run in `20260908T223116`, load `T.final_messages(log)`,
join the `content` of every `tool` message, and search for a fragment of each note:
`not to the largest pack`, `22.50 against 24.90`, `sits in the middle of the range`,
`M is NOT available`. Search on `22.50 against 24.90` rather than the quoted "Ground truth for
'cheapest...'", because quotes are escaped inside snapshots and the longer string misses them.
