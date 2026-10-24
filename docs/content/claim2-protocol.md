# The second claim run, protocol (DRAFT)

Drafted on 22 October 2026, before the second claim market exists. Version 2 was rewritten on 23
October from the verifier's fairness re-audit and the front door's pilot. Version 3, this text, was
rewritten on 24 October 2026 for design B, the student's decisions of that night (the section
"Decisions of 24 October" at the end). Status: **draft, not frozen.** It is final only after the
verifier's logic audit of the frozen commit, and it is committed before any seed of the claim market
is drawn. After the market exists nothing here changes; an amendment, if any, is recorded with its
time, as the first protocol's were.

## The questions it answers

1. **The front door.** On reworded questions the block was not designed on, does the block with a
   model reading the question answer correctly more often than the block with its rules?
2. **The block on a misleading market.** On a market the block was not tuned on, whose size menus
   carry labels that read like prices and stock counts but are neither, does the block still reach
   the correctness of exhaustive browsing while opening fewer listings, at lower cost?
3. **RQ2 again.** Does the shipped agent still fail there, and does it take a label's figure for a
   price?

## One commit

Every run is made at one commit, named here at the freeze with every version it carries: box, form,
prompt, normalisation, primitives, targeting, planner, scorer, sufficiency rules, the analysis file,
the tee-only generator, the search-order model and the toolbar counter. The analysis file
`experiments/tasks/claim2_analysis.json` (version 7) holds each arm's conditions under `require`:
those versions, the agent's code and patch, the browser tool, flags and origins, for the model arm
the parser's model, and the provider routing. The claim command checks them before every invocation
(`claim.py --preflight`) and spends nothing on a mismatch; since analysis version 8 the preflight
also resolves the protocol's question sets against the task file, so a set naming a question the
file lacks is refused before any run. A batch found outside `require` afterwards is void as a
whole: it is listed, re-run under the required conditions, and until then it holds up the analysis
(decision 12).

To fix at the freeze: the commit, and the version list. As this text is written the file requires
box 18, form 13, prompt 3, normalisation 4, primitives 12, targeting 9 and planner 2; the box coder
is bumping the box to 19 and the prompt to 4 for decision 11, and `tests/test_claim2_analysis.py`
holds every required version to the code's constant, so the file cannot lag the code unseen. The
scorer is not an arm's condition: the analysis scores every answer again with the scorer it imports
and lists any stored verdict that moves.

Fixed settings, the same for every arm: the agent's sampling (temperature 0.2, top_p 0.1), the
browser tool (Playwright MCP 0.0.83, isolated, service workers blocked) confined to the shop's
origin, the gated theme's user agent, a fresh browser profile and selector cache for each run, 300
steps and 1800 seconds, and `IGR_PROVIDER_ROUTING` exported once for the stage with DeepSeek's
value `{"order": ["gmicloud", "deepinfra", "streamlake"], "allow_fallbacks": false,
"quantizations": ["fp8"]}` (decision 7). The routing names providers and a quantisation, not a
price; the providers' prices on 23 October were at or below list.

## The market (design B, the tee-only generator)

- **One product, a tee, under one brand.** Every question's results page lists only tees. This is
  post-search navigation: the agent lands on the search results for the product. Search relevance
  is out of scope, a limit: the search is assumed to return the requested product.
- **About 45 listings from distinct sellers,** so the search spans two results pages at the shop's
  36 a page. No shop setting is changed. Titles take one of three phrasings with a shared core, the
  claim pool "Midweight Jersey Tee" and its variants; development keeps its own pool.
- **Sizes XS, S, M, L, XL, XXL.** Each is absent, sold out or buyable at its own price. The target
  sizes are M, as in the first claim, and XS, the promo trap.
- **Misleading labels in the size menu**, rendered by the gated theme as part of the option's
  label. The fixture holds them as data (`label`, `label_kind`, `label_price`), and the price is
  never in the label: a size's price shows once the size is chosen.
  - *Promo labels* sit on size XS only, on several listings, as "XS - Promo $9.99". Every one is
    false: the figure is at least 8 per cent below the real XS price. At least one listing's figure
    is below every XS price that can be bought, so a label reader names the wrong price or seller.
  - *Scarcity labels* sit on buyable size M only, as "M - Only 2 left!", whatever the stock. The
    shop shows no stock counts, so no key depends on them.
- **No listing description.** The fit line "Runs small" was cut (the handover's first cut line): it
  would have made decline-fit answerable. The fit decline points to the size menu.
- **Acceptance rules.** The tee generator's rules that still apply (clear margins, the sold-out and
  absent traps, `bound_is_useful`, `top_3_margin`, `limit_separates`, `headline_on_page_1`, names
  distinct) and the page rules for one product (`first_screen_misleads`, `answer_on_page_2`,
  `counts_need_page_2`), checked against the predicted order and then live. The label rules, being
  added by the generator coder, in short: `promo_trap` (amended: the lowest promo figure is below
  the lowest real buyable XS price, and the listing showing it is not the cheapest real XS),
  `promo_labels_false`, `promo_xs_only`, `xs_unique_winner`, `xs_clear_margin`,
  `xs_answer_not_on_cards`, `xs_sold_out_trap` if feasible, `promo_check_target` (the named
  listing's label figure differs from its real XS price by at least 8 per cent),
  `promo_check_card`, `promo_check_distinct`, `promo_check_choice`, `no_fit_text` and
  `scarcity_labels`. Every water rule is dropped. The exact list and each rule's text are the
  generator's file's, to be named here at the freeze.
- **Brand and seeds.** The claim brand is Wexcombe, the first free name on the list, checked free
  on 23 October. The development market gets a new brand of its own, chosen with `--check-brands`
  from names on no list, under development seeds 900 to 999 and its own SKU prefix. The claim
  market is the first seed from 1000 that passes every rule, drawn only after this file says
  FINAL. Larchmere stays seeded.
- **Checked live before any run** (`env/check_aplus_market.py`): the search lists exactly the
  market's listings on exactly two pages; every card's price equals the listing's cheapest buyable
  variant; every variant's label, price and stock equals the fixture's; the gated theme hides every
  variant price until chosen; the live results order equals the order recorded when the seed was
  accepted, which the failure codes read, and the page rules hold on it. The check runs again before
  each stage.

## Questions

`{brand}` is the claim market's brand, `{limit}` the exists-under limit, `{seller}` the full seller
name as in the listing's title, `{promo}` that listing's XS label figure to two decimals. Keys are
computed from the fixture by code, under both readings where a question has two. The eight tee
templates and decline-delivery are the A+ design's word for word, so v2's rewordings of them stay
valid; the four new rows are the verifier's final texts of 24 October 2026.

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
| tee-xs-price | What is the lowest price anyone charges for size XS of the {brand} tee, among those that can actually be bought? |
| tee-promo-check | The {seller} listing of the {brand} tee says in its size menu that size XS is on promotion at ${promo}. Is that what size XS costs on that listing? If not, what does it cost? |
| decline-delivery | Which {brand} seller delivers fastest for size M of the tee? |
| decline-fit | I'm usually between a medium and a large. Will size M or size L of the {brand} tee fit me better? |
| decline-scarcity | Of the {brand} tee listings where size M can actually be bought, which seller has the fewest units of it left? |

The thirteen rows above are fixed by their sha256, the table rows joined by line breaks, as the
first protocol's were: `36d660fdacaf3661553495fe1a9672c16bca113ae963e29254e18afa4afcf002`. The command
that computes it is
`python3 -c "import hashlib,re,sys; rows=[l for l in open('docs/content/claim2-protocol.md').read().splitlines() if re.match(r'^\| (tee|decline)-[a-z0-9-]+ \|', l)]; print(len(rows), hashlib.sha256('\n'.join(rows).encode()).hexdigest())"`.

**Keys.** tee-xs-price's key is the lowest XS price that can be bought, with the lowest promo
figure as its trap. tee-promo-check's key is no, the label is false, plus the real XS price of the
named listing; its yes or no is constant by design, since every label is false, so only the real
price discriminates, and it is scored so (score v10's kind for it). The three declines have no
key: the shop shows no delivery time, no fit and no stock count.

**The sets** (the analysis file's): control, tee-headline; gated, the eight keyed questions open
everything asks, every keyed template but tee-headline and tee-promo-check, since open everything
on one named listing is meaningless; lookup, tee-promo-check; two readings, tee-all-stocked and
tee-count-stocked, whose own key is the menu reading with a buyable key in the sidecar;
reading-independent, the seven keyed questions with one reading, tee-promo-check among them.

**Two readings.** tee-all-stocked and tee-count-stocked say "offer" of a size and nothing that
settles which availability they mean: "in the size menu, even if sold out" (the menu reading, their
own key) or "can be bought now" (the buyable reading, a second key in the readings sidecar). Every
other keyed question has one reading, the buyable one.

**Held-out rewordings, v2.** The meaning-kept entries of `experiments/tasks/paraphrases_v2.json`
whose template is a tee template or decline-delivery: 16 keyed and 2 declines, read by id and
template only. v2 has no entry for the two new templates.

**Held-out rewordings, v3.** `experiments/tasks/paraphrases_v3.json`, 29 entries, written blind
by a fresh agent (Claude Fable 5.1) that never saw the parser, its prompt, the box's code, or v1's
or v2's texts, from the thirteen templates and a description of the shop only; it read v2's
structure, not its texts. Finished at 02:03 on 24 October 2026. The sha256 of its entries, as
`generate_aplus_tasks.entries_digest` computes it:
`4bd12c1a522e378cef945a59763c9c440128de4abbe119f4da7bcde2be32d00b`. By template: two each of the
ten keyed templates, decline-fit and decline-scarcity, one of decline-delivery, and four with
template null. By expected outcome: plan 16, ask 6, decline 7. The 25 entries with a template run
in the shop (20 keyed, 5 declines). The four with template null run in the text-only reading test
alone; each carries `ask_kind` (availability, threshold, other), so a "menu or buyable?" ask on a
price word with no figure is not counted right. The style is that of real shopper questions
(sizes, price limits, options, fit, stock, delivery, returns, quality), written new and never
copied from a dataset.

Each rewording's task carries its template's id and keys, and its `source`, the file it came from.
No v2 or v3 text reaches anyone developing the parser, the prompt or the block.

## Arms

1. **Shipped.** openJiuwen as shipped.
2. **Open everything.** As shipped, told to open every listing of the product the question asks
   about (`--exhaustive --exhaustive-wording product`, wording version 2).
3. **The block, rules.** The block at the frozen commit, `--box --parser rules`.
4. **The block, model.** The same block, `--box --parser model`, the parse made by the run's own
   model at temperature 0 under the frozen prompt (version 4). It may decline a question only when
   the rules confirm the attribute it needs is not shown on this shop. A reply that gives no usable
   form falls back to the rules' form, recorded on the run. A parse call that fails voids the slot:
   no agent runs, and it is re-run once with the voids.

Both block arms: the rendered page reader (`--page-reader rendered`, every results page), and
`--reading own` (decision 8): where the block asks, the scripted shopper answers with the reading
the question's own key was written under, the menu reading for the two two-reading questions and
their rewordings, the buyable reading for every other keyed question. The rate plan flag is dropped:
it changes a plan only on a per-litre question (`primitives.every_rate`), which this design has
none of; the batch records the default, which `require` holds it to. The block's plan text carries
one sentence about labels: a size's label can carry promotional or stock text, the price is the one
shown after choosing the size, and a label's claim is not a checked fact. Shipped and open
everything are not told this (a limit, below).

Every arm: the same model, the fixed settings above, 300 steps and 1800 seconds. If the pilot's
open everything comes within 80 per cent of either limit, both limits rise for every arm alike, as
a timed amendment before stage 1 (the pilot, below).

**The ask cap.** The block asks at most once per question. An ask the scripted shopper cannot
answer, a price word with no figure or a reading the shopper's own key does not settle, closes the
slot: no agent runs, the slot counts as not correct in H1 and H4, and every closed slot is reported
by question and arm.

## Models

DeepSeek V4 Flash alone runs in the shop, the one model the analysis file names, routed for every
arm alike as decision 7 says. Its four tests are the claim, with Holm over the four. Claude Haiku
4.5 runs no arm: it is in the text-only reading test alone, descriptive, with no family and no
Holm. Claim 1 already showed the block on both models.

## Design and order

Each round runs every arm once (`--repeats 1 --repeat-start r`), and the order of the arms rotates:
round 1 shipped, open everything, the block (rules), the block (model); round 2 starts at open
everything; round 3 at the block (rules). Shipped asks the thirteen templates; open everything the
eight gated; each block arm the thirteen templates and, in round 1, the held-out rewordings: v2's
18 and v3's 25. The analysis file holds this design; a run it does not ask for is listed and left
out of every figure, and a test's two arms are asked its questions in the same rounds.

## The pilot

Development only, never part of the claim, on the development market, about 12 runs, cap $6: the
block with the model on tee-xs-price, tee-promo-check, a count, a bound question and decline-fit;
the block with the rules on two; open everything on one count-like and one price question; shipped
on two. Its chain ends by running `experiments/analysis/pilot_check.py`, which decides four checks
from the pilot's records alone, never from whether an answer is right (a test plants flipped
verdicts and holds its output unchanged), writes PASS or FAIL for each with the pilot's cost, the
projected stage-1 cost and a proposed fix into a summary file the student reads, writes
`pilot-check|PASS or FAIL|<the summary file>` to the manifest, and exits 9 when a check fails. The
rules, as the script's docstring fixes them:

1. **No harness error and no void.** Every run of every batch the manifest names is put in its
   class by voids.py's rule (a log silent over the suspended-run limit, no record, a provider or
   runner error), and none is void; and no run's record carries an error other than the step
   budget's or the clock's markers, which are rule 2's. A failure proposes no change of limit or
   cap: the fault is looked at before stage 1.
2. **No run at or within 80% of its step or clock limit.** For every run, its tool calls (the
   trace's `tool_calls_total`, the figure the protocol compares with the step limit) are under 0.8
   times its record's `max_steps`, and its `elapsed_s` under 0.8 times its `clock_s`. When any
   run, open everything's above all, is at or over either, the fix is both limits raised for every
   arm alike: each to the first multiple of 50 steps or 300 seconds at which the pilot's largest
   figure is under 80%, and never lowered.
3. **Every answer to a keyed question keyable.** No row of a keyed question has the verdict
   "unscored", the scorer's word for a run with no key for the reading it answered under. The
   keyless questions, the task file's tasks with no key (the declines), are excepted; a slot the
   box closed is not an unscored row. A failure proposes no change of limit or cap: the task
   file's sidecar lacks a key.
4. **The projected stage-1 cost within the stage-1 cap.** Each question of stage 1's plan (from
   the analysis file and the claim market's task file) is priced by the pilot's mean cost per run
   for the same arm and the question's kind (a held-out task by its template's kind), the parse's
   charge included. An (arm, kind) the pilot did not run is priced by these rules, in order:
   a. a block arm's headline is priced as its lookup: both read one page;
   b. the block (rules) by the block (model) for the same kind: the same box text, the parse's
      charge aside;
   c. open everything by the dearest kind it measured: its work is every listing, whatever the
      question;
   d. shipped by its mean over every run it measured: its work does not follow the question's
      kind;
   e. anything else is unpriceable, and the check fails saying which pair.
   Added to the plan: the routing gate at what the pilot's own gate probe charged, DeepSeek's
   reading tests at that probe's charge per call times the entries they parse, and Haiku's at the
   23 October Haiku probe's charge per call times the same entries. No allowance is made for void
   re-runs; the chain's cap gate holds them. The development market is taken to have the claim
   market's shape, the same listings over the same pages, so nothing is scaled. When the
   projection is over the cap, the fix proposed is the cap at the projection plus 10%, rounded up
   to the dollar, with what fewer open-everything rounds would cost printed beside it; the student
   decides.

The pilot's results may change limits or caps, as a timed amendment recorded here before stage 1,
never the design or the questions. The analysis file's design names its sets as the stage plan
reads them: "templates", the tasks without a template; "held_out", the tasks with one; "gated",
the file's gated set.

## Budget and stopping

$97.98 is left on the key. The total cap is $75 including the pilot: $6 for the pilot, $69 for
stage 1, leaving at least $20 in reserve. Stage 1 is one command with its own declared estimate:
small invocations (one arm and one round, or one question for open everything and shipped), each
starting only if spent plus twice its estimate stays under the cap; `claim.py --preflight` before
each; a watchdog reading the account every 20 seconds that stops any suite at the cap less $0.30;
the voids re-run once under the same routing; then the reading tests. Estimates are priced from the
23 October pilot's per-question costs at list price, scaled for 45 listings, and re-priced from the
new pilot by the gate. A repair is allowed only for a fault in the harness, the shop or the laptop
found from the logs, never from the answers: the fix is verified, the whole affected arm is re-run,
and the repair is recorded here as a timed amendment.

## Measures and scoring

As the first protocol: listings opened by membership of the market's listings, cost by the
provider's charge, the parse call's tokens and charge counted in its run. A run is scored under the
reading it was answered under; a run with no key for that reading is unscored and reported, never
scored against another key.

**The verdict of record is the student's blind hand reading** (decision 5), done after the run
under the written rules in `docs/content/claim2-reading-rules.md`, with the scorer's verdict
reported beside it. The scorer at the freeze is score v10, v8 plus additive kinds (one for
tee-promo-check, and whole-label blanking so "M - Only 2 left!" is not read as a count): a decision
taken on the student's behalf at 01:58 on 24 October, pending the generator coder's confirmation.
The sheet is written by `claim.py --sheet`: one random code per run hides its arm, model, batch,
task and round; the scorer's verdict is not on the sheet, only in the key file; a held-out
rewording is shown under its template's question. Closed slots, answers to the keyless questions
and runs with no key for their reading are not on the sheet and are counted in the key file. The
student must not see any result before finishing the sheet. The filled sheet is read back by
`claim.py --hand`, which refuses a sheet with any gap or foreign code, reruns the four tests on the
hand verdicts, and lists every disagreement with the scorer by arm after unblinding, with its lean.
A run may be marked unscorable only when its answer cannot be read at all, and unscorable runs are
counted by arm beside each test. **The second reader**, the verifier, reads 40 rows of the same
sheet blind, drawn by `claim.py --sheet` itself as `random.Random(20261024).sample` over the
sheet's codes in sorted order and written beside the sheet as `<name>.second-reader.json`. The
agreement of the two readers (the share of rows read alike, and Cohen's kappa) is computed by a
short script committed with the results.

## Tests

Stratified exact tests of correct and van Elteren tests of listings and cost, two-sided, by question
then pooled, Holm over DeepSeek's four:

- **H1:** the block (model) is correct more often than shipped, on the seven reading-independent
  questions.
- **H2:** the block (model) opens fewer listings than open everything, on the eight gated
  questions.
- **H3:** the block (model) costs less per run than open everything, on the eight gated questions,
  also reported on tokens.
- **H4:** on the held-out rewordings, the block (model) is correct more often than the block
  (rules), stratified by template, one test of the ten keyed templates.

In H1 and H4 a slot the box closes counts as not correct, as does an abstention. H2 and H3 count
only slots where the agent ran: a closed slot is listed by question and arm, and two sensitivities
put the closed slots back, at zero listings and the parse call's charge, and, cautiously, at open
everything's median for that question. H4 is repeated, secondary and unadjusted, on two
pre-specified splits, each within a set: v2 against v3, within the kept eight templates; and the two
new templates against the kept eight, within v3. Both parsers are deterministic, so the sensitivity
"H4 by rewording, not by run" takes one unit a rewording. The block's correctness against open
everything is a difference with its interval, never a test (decision 10); tee-promo-check, which
open everything does not ask, is reported there as not run by design. Further sensitivities: without
the two-reading questions; distinct runs only; with the voids; without runs that saw a hidden price;
without runs that sorted or changed the page size.

## Exclusions

A run is void when its log falls silent for more than 60 seconds or it ends with no final
completion for a reason outside the agent. Voids are decided from the log before any answer is
judged, re-run once after the last round under the same flags and routing, and a second void is
reported as such. Every other run counts; a run that stops at the step or clock limit without an
answer counts as not correct. A batch outside `require` is void as a whole, re-run and listed
(decision 12).

## Secondary measures

Each defined in the analysis file before any run, by arm:

- asks on questions labelled clear and on those labelled ambiguous, with Wilson's 95 per cent
  interval;
- **asks caused by the word-list clash** (decision 11): of the box's asks, those whose record gives
  the reason "clash", the rules' word list and the model having read a word differently, against
  "ambiguous", the question's own two readings, by the sidecar's label, each named;
- declines: what each arm did with the three decline templates and their rewordings;
- the parse's fallbacks;
- the shipped arm's failures on the reading-independent questions by written code, the first that
  holds: "page 2 never reached", applied only where the key needs a listing past page 1; "sorted or
  resized, its first page alone"; "a card or sold-out price taken"; **"a label's figure taken"**,
  the answer states as a price a figure a size label shows as a promotion that the key does not hold
  as right and the question does not quote; "other";
- **promo traps fallen for**, on tee-xs-price and tee-promo-check and their rewordings, of the runs
  that answered, by what the key can say: on a price key the run fell for the trap when the price
  the answer gives as its answer is a label's promo figure the key does not hold as right; on any
  other key when the answer affirms the label, or says neither yes nor no, states a label's figure
  and states no price the key holds as right; a share with Wilson's interval, each run named;
- sorts and page-size changes;
- hidden-price leaks;
- the serving provider, and H3 within each provider that served whole runs of both arms where the
  mixes differ.

## The reading test

After the stage's last block run, each model parses the held-out entries once, as text, at the
frozen prompt: DeepSeek routed as in the shop, then Haiku unrouted. The entries are v2's whose
template is a tee template or decline-delivery, and every v3 entry, the four with template null
included (`parse_probe.py --questions ... --spec-from <the claim task file> --page-from <the
stage's first block batch>`, which fills the brand, the limit and the results page from the claim
market). Each form is compared with its template's in the probe's four tiers, each outcome with the
entry's expected one (plan, ask or decline), a v3 entry's ask with its `ask_kind`, and the rules'
form is read beside it. Descriptive, no test. It runs after the last block run, so no parse of a
held-out entry precedes the run that answers it.

## Limits stated in advance

- One new market, one draw, one product.
- **The block's label sentence is in-sample by kind** (LESSONS 19). Only the block arms are told
  about the trap, and the sentence was written knowing the market's label kinds. H1 on tee-xs-price
  and tee-promo-check, and "promo traps fallen for", partly measure that sentence. The claim does
  not show that the block handles label kinds it was not told about.
- **tee-promo-check's yes or no is constant:** every label is false by design, so only the real
  price discriminates, and it is scored so.
- **decline-scarcity:** the right decline says the shop does not display stock counts. Whether the
  cart bounds stock is being checked.
- Search relevance is out of scope: the agent lands on the product's results page.
- The model parser's prompt (version 4) was developed on `paraphrases_dev2.json` and v1 only, with
  no live model call; v2 and v3 are the test, and the v2-against-v3 split shows the difference.
- The rules were never tuned on rewordings; a failed parse falls back to the rules, which pulls H4
  toward no difference.
- The stop rule assumes no card advertises more than its cheapest buyable variant.
- The page's encoded variant store is still in the page source; leaks are counted.
- The page rules hold for the shop's relevance order at 36 a page only; sorting is counted.
- The scorer's known misreadings lean mostly against long, careful answers; the hand reading is the
  verdict of record for that reason.
- The market's rules guarantee the block something to save (`bound_is_useful`, the traps), as they
  guarantee the shipped agent something to miss; the result holds for markets with that shape.
- The box reads the results pages for its agent and hands it the listings' addresses and the shop's
  mechanics; open everything is told only to open everything, so H3 measures the plan, the briefing
  and the free page reading together, not the stop rule alone.
- DeepSeek's serving provider varies within the providers decision 7 allows, and with it the price
  per token; H3 on tokens is reported beside H3 on cost.

## History and disclosure

- The model parser's prompt version 3 was written from paraphrases_v1's failures (23 October) and
  piloted on Larchmere with v1 rewordings and the templates. Prompt version 4, for the promo check,
  fit and scarcity and for decision 11, was developed on the practice questions
  `experiments/tasks/paraphrases_dev2.json` and v1 only, with no live model call, on 24 October.
- The v2 disclosures of 23 October stand: the verifier read the prompt and v2 for its audits and
  reported ids and counts only; a coder printed four lines of v2's `_about` and the distinct values
  of four entry fields, no text, and no change to the parser followed.
- v3 was written blind on the night of 24 October by a fresh agent, Claude Fable 5.1, finished at
  02:03, from the templates and a description of the shop; its sha256 is pinned above. The
  coordinator passed its ids and counts, never a text, to the coder writing this protocol and the
  analysis.
- The verifier's question check of 24 October fixed the four new templates' texts, added the lookup
  set, and replaced the handover's split drafts with the two splits above.

## Decisions of 24 October

Each is the student's, taken between 00:30 and 01:10 unless timed otherwise.

1. **Design B**, a focused redesign of the market; the A+ design is the fallback only.
2. **Tee only.** No water, no per-litre question, no multipack hint; a question whose difficulty
   is arithmetic is out.
3. **More sizes and misleading variant labels:** promo labels that disagree with the price shown
   after choosing, scarcity labels that are not true, a fit question the block declines, and a
   shopper who wants XS "because it says promo".
4. **A new held-out set in the style of real shopper questions,** written blind.
5. **Verdict of record: the student's blind hand reading**, score reported beside it, the
   verifier reading a 40-row blind sample as second reader.
6. **Models:** DeepSeek V4 Flash only in the shop; Claude Haiku 4.5 only for the reading test.
7. **Fairness:** the same model, settings, market and questions for every arm; DeepSeek routed to
   the fp8 list-price providers for every arm alike.
8. **The shopper's reply:** `--reading own`.
9. **No block-without-stop-rule arm.**
10. **"As accurate as open everything" is descriptive**, a difference with its interval.
11. **The word list against the model:** a clash becomes an ask, developed and tested on practice
    questions only.
12. **A batch outside `require` is void, re-run and listed.**
13. **The morning as two taps** (01:35): the pilot first, stage 1 after the student reads its
    summary. The guard is not changed. (The 10:00 taps did not happen; new times are set with the
    student once the work is stamped.)
14. **Usage limits and models** (01:45): the night's work spread across models, capacity kept for
    verification; the model that did each piece of work is recorded.
15. **Score v10 beside the hand reading** (01:58, taken on the student's behalf, pending the
    generator coder's confirmation).
