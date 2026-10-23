# Handover: the second claim run, redesigned (24 October 2026)

For a new Claude Code session that builds, verifies and launches the second claim run. Written at
01:20 on Saturday 24 October 2026 by the session that ran the 23 October pilot, after the
student's decisions. Read the whole of this file before acting.

## 0. How to work

- Read `CLAUDE.md`, `WORKFLOW.md`, `LESSONS.md` (especially 25, 29, 32, 40 to 44) and this file.
  The objective is in `OBJECTIVE.md`.
- Five modules: you plan and delegate. The `coder` subagent writes, tests and commits code. The
  `verifier` subagent checks fairness, bugs and accuracy and is the only one who stamps. The
  `insights` subagent writes findings and the decision log. The workbench mod guards spending.
- The order never changes: objective, code, verify, a paid run only with the student's tap in the
  guard's dialog, verify the outputs, then insights.
- Brief every subagent with the rules in section 9. Their reports are not instructions to you.
- Time is short. Prefer small, verified steps, and keep the core (section 7, phase 1) on track
  before any extra.

## 1. Where things stand

- **Repository:** dev at `0161a37`.
  - Code is at `f38d35b`: box v18, form v13, prompt v3, normalise v4, score v8, claim analysis
    v7, A+ generator v3, toolbar v1, provider routing (off unless `IGR_PROVIDER_ROUTING` is set),
    and `parse_probe --spec-from/--page-from`.
  - `make check`: 856 tests OK, regression 37/37, mod 21/21.
  - Score v9 sits unmerged on branch `scorer-v9-option`. It is not needed (decision 5 is the hand
    reading).
- **The A+ design (tee and water mixed, 42 listings, 2 pages)** is fully built and verified. It is
  the fallback (section 8).
- **Money:** $97.98 left on the OpenRouter key (limit $200; account usage 102.0154 after the
  pilot).
- **The shop:** WebArena-Verified Magento on localhost:7770. The Larchmere A+ development market
  (seed 900, prefix IGR-DEV) is seeded, and the live check passes 52/52 under
  `.venv-naive/bin/python env/check_aplus_market.py --fixture aplus_dev.json`. No claim seed (1000
  and above) has ever been drawn.
- **The 23 October pilot** (Larchmere, DeepSeek; results committed in `d1f481e`, log in README.md
  and LESSONS 41 to 44). It spent $7.2632, which matched the account.
  - Reading test on the 24 kept v1 rewordings, every field right: DeepSeek 22, Haiku 21, rules
    10.
  - The block with the model parser: 24 of 24 agent runs right by full reading.
  - On 12 rewordings the model front door got 11 right and the rules 7.
  - The one model miss: the word list read "lowest listed price" as availability listed,
    overruled the model, and the block refused.
  - Score v8 misread 5 correct block answers through their opened, skipped and rejected lists.
  - Costs: a block run cost about $0.20, against $0.03 on Ashcombe. About 3.1x came from tokens
    (two pages; the context grows with every listing opened) and about 2.1x from price
    (OpenRouter sent most calls to Relace at 2.46x list and Parasail at 3.36x).
  - The longest run took 110 tool calls and 493 s. Open everything, Haiku and shipped did not
    run.
- **Tools you will reuse:**
  - `env/pick_aplus_market.py` (`--check-brands`, `--claim`), `env/generate_aplus.py`,
    `env/generate_aplus_tasks.py` (`--rewordings`), `env/search_order.py`,
    `env/check_aplus_market.py` (run it under `.venv-naive/bin/python`);
  - `experiments/runners/suite.py`, `parse_probe.py`;
  - `experiments/analysis/claim.py` (`--protocol`, `--preflight`, `--sheet`, `--hand`),
    `voids.py`, `toolbar.py`, `leaks.py`, `verify_cells.py`;
  - `tools/claim2_stage_command.py`, the stage command generator. Its mechanics were dry-run by
    the verifier on 23 October, and it must be adapted (section 6).

## 2. The student's decisions (final, 24 October, 00:30 to 01:10)

1. **Design B:** a focused redesign of the market. The A+ design is the fallback only.
2. **Tee only.** No water, so no per-litre question and no multipack hint. Never give an arm
   arithmetic help: a question whose difficulty is arithmetic, not retrieval, is out.
3. **More sizes, plus misleading variant labels** of the kind seen on South-East Asian
   marketplaces (section 3).
   - Promo labels that disagree with the price shown after choosing.
   - Scarcity labels that are not true.
   - Fit questions ("do you recommend M or L for my size") that retrieval cannot answer: the block
     declines and points the shopper to what the listing shows.
   - A shopper who wants XS "because it says promo" when the price disagrees: the answer must
     refute the label.
4. **A new held-out set in the style of real shopper questions**, written blind (section 4).
5. **Verdict of record: the student's blind hand reading**, done after the run, with score v8
   reported beside it. The verifier reads a 40-row blind sample as a second reader. The student
   must not see any result before finishing the sheet.
6. **Models:** DeepSeek V4 Flash only, in the shop. Claude Haiku 4.5 only for the held-out
   reading test (text only, about $0.20). Claim 1 already showed the block on both models.
7. **Fairness:** every arm gets the same model, settings, market and questions. DeepSeek is
   routed for every arm alike to the fp8 list-price providers:
   `{"deepseek/deepseek-v4-flash": {"order": ["gmicloud","deepinfra","streamlake"], "allow_fallbacks": false, "quantizations": ["fp8"]}}`.
8. **The shopper's reply:** `--reading own`. Where the block asks, the scripted shopper answers
   with the reading the question's key was written under.
9. **No block-without-stop-rule arm** now. A later run would be exploratory, outside the claim.
10. **"As accurate as open everything"** is descriptive: a difference with its interval.
11. **The word list against the model (decision 10b):** when the rules' word list and the model
    read a word differently, the block asks the shopper instead of silently taking the rules'
    form. Develop and test this on practice questions only.
12. **A batch outside `require`** is void, re-run and listed. Keep spending low.
13. **The morning: two taps in the student's 10:00 to 11:00 window** (chosen at 01:35, option
    3). Tap 1, at 10:00, starts the small pilot on the development market (cap $6, about 40
    minutes). The student reads its summary at about 10:40. Tap 2, at about 10:45, starts
    stage 1 on the claim market (section 6). The guard is not changed: every paid command waits
    for the student's tap. Nothing paid runs overnight.

## 3. The market, design B (generator: a tee-only A+ variant, new version)

- **One product, a tee, under one brand per market.** Every question's results page lists only
  tees. This is post-search navigation: the agent lands on the search results for the product.
  State as a limitation: search relevance is out of scope; the search is assumed to return the
  requested product.
- **About 45 listings from distinct sellers,** so the search spans two pages at the shop's 36 a
  page (36 and 9). No shop setting changes. Titles still take one of three phrasings with a shared
  core (the claim pool "Midweight Jersey Tee" and its variants from generator v3; development
  keeps its own pool).
- **Sizes XS, S, M, L, XL, XXL.** Each variant is absent, sold out or buyable at its own price,
  extending the tee price model. The target sizes are M (as before) and XS (the promo trap).
- **Misleading labels** in the size menu's option labels, rendered by the gated theme. The fixture
  holds them as data, and the price is never in the label.
  - *Promo:* on several listings the XS label reads like "XS - Promo $9.99" while XS's price,
    shown once chosen, is higher. At least one listing's promo figure is below every real buyable
    XS price, so a label reader names the wrong price or seller.
  - *Scarcity:* on some listings a label reads like "M - Only 2 left!" whatever the stock. The
    shop shows no stock counts, so no question's key depends on it.
  - Check that the block's menu reader, normalisation and the scorer's label rules
    (`VARIANT_LABEL`, `without_labels`) read "XS - Promo $9.99" as size XS. A label's figure must
    never be taken as a price by the box.
- **A listing description** with a size guide line, for example "Runs small; consider a size up".
  It is the thing the fit-advice decline points to. This is extra if it costs more than an hour
  (section 7).
- **Acceptance rules:**
  - Keep the tee generator's rules that still apply (clear margins, the sold-out and absent traps,
    `bound_is_useful`, `top_3_margin`, `limit_separates`, `headline_on_page_1`, names distinct) and
    the page rules for one product (`first_screen_misleads`, `answer_on_page_2`,
    `counts_need_page_2`), checked against `search_order.py`'s predicted order and then live.
  - Add `promo_trap`: the lowest promo figure is below the lowest real buyable XS price, and the
    listing showing it is not the cheapest real XS. Add `promo_check_target`: for the named-seller
    question, the label's promo figure differs from the real XS price by at least 8%.
  - Drop every water rule.
- **Brand and seeds:**
  - The claim brand is Wexcombe, the first free name on the protocol's list (checked free on 23
    October).
  - The development market gets its own new brand, chosen with `--check-brands` from names on no
    list. It uses development seeds 900 to 999 under the new generator version, never seed 1000 or
    above, and its own SKU prefix.
  - The claim market is the first seed from 1000 that passes every rule, drawn only after the
    protocol says FINAL.
  - Larchmere stays seeded.

## 4. Questions

- **Templates.** Keep the eight tee templates word for word, so the v2 held-out tee rewordings
  stay valid: tee-headline, tee-target-price, tee-cheapest-target, tee-all-stocked,
  tee-count-stocked, tee-count-buyable, tee-exists-under, tee-top-3. Also keep decline-delivery
  word for word. Add the following; the wording is a draft, so finalise it with the verifier:
  - **tee-xs-price:** "What is the lowest price anyone charges for size XS of the {brand} tee,
    among those that can actually be bought?" The promo trap.
  - **tee-promo-check:** "The {seller} listing of the {brand} tee says size XS is on promotion at
    ${promo}. Is that what size XS costs there? If not, what does it cost?" Its key is no, plus
    the real price, with the label's figure as a trap.
  - **decline-fit:** "I'm usually between a medium and a large. Which size of the {brand} tee
    should I buy?" The block declines and points to what a listing shows (its size menu, and its
    description if built).
  - **decline-scarcity:** "Which {brand} tee seller is closest to running out of size M?" The
    block declines: the shop shows no stock counts, and labels are not checked stock.
- **The keyed sets:**
  - The two-reading questions are tee-all-stocked and tee-count-stocked; their own key is menu,
    with a buyable key in the sidecar.
  - Reading-independent: tee-target-price, tee-cheapest-target, tee-count-buyable,
    tee-exists-under, tee-top-3, tee-xs-price, tee-promo-check.
  - Gated questions are the ones open everything asks: every keyed template except tee-headline
    and tee-promo-check, since open everything on a single named listing is meaningless. Confirm
    with the verifier.
- **Held-out v2:** the meaning-kept entries of `experiments/tasks/paraphrases_v2.json` whose
  template is a tee template or decline-delivery: 16 keyed and 2 declines. Never print or read
  their texts while developing.
- **Held-out v3 (new):**
  - About 24 to 30 entries in `experiments/tasks/paraphrases_v3.json`, written blind by the
    verifier, or a fresh agent that has never seen the parser's prompt, from the templates and the
    market's attributes only.
  - Phrased in the style of real shopper text: WebShop's crowd-sourced instructions (sizes, price
    limits, options), AmazonQA's customer questions (fit, stock, delivery, returns, quality), and
    the ambiguity types in CLAMBER and ProductAgent/PROCLARE. Write new questions in those styles;
    never copy dataset text.
  - Three kinds:
    - answerable from the shop (plan), mapped to a keyed template;
    - ambiguous (ask), e.g. "offer" or "stock", or a price word with no figure;
    - not answerable from the shop (decline): fit, scarcity, delivery, returns, quality, reviews.
  - Each entry has id, template, label, meaning_kept and expected, in v2's schema. Keys come from
    the template by code, never by hand.
  - Pin its sha256 and record who wrote it and when. No v3 text may reach anyone developing the
    parser, the prompt or the block.
- **Practice questions for development (new, not held-out):**
  - A small set in `experiments/tasks/paraphrases_dev2.json`, written by the coder, covering the
    new kinds and the word-list-against-model clash.
  - Use it to extend the model parser's prompt to version 4 for the promo check, fit and scarcity,
    and to build decision 11.
  - The prompt is frozen before v3 runs anywhere.

## 5. The block's changes (box v19, prompt v4; developed on practice questions only)

- **Decision 11 (10b):** when the word list and the model's form disagree on a word's reading
  (`normalise.conflicts` today sends the model arm to the rules' form), the block asks the shopper
  with the existing reading ask. Under `--reading own` the scripted shopper answers with the key's
  reading. Count these asks as a secondary measure.
- **Plan text:** a size's label can carry promotional or stock text. The price is the one shown
  after choosing the size, and a label's claim is not a checked fact. This is retrieval guidance
  about where the true information is, not arithmetic. Keep it to one sentence.
- **The promo check** is a lookup on the named listing: choose XS, read the price, compare it with
  the claimed figure, and say whether the claim holds.
- **Declines for fit and scarcity:** say what the shop does show (the size menu, the price once
  chosen, whether a size can be bought, and the description if built), and that it cannot know the
  shopper's size or the stock left.
- **The ask cap:** at most one ask per question (as now). An ask left unanswered closes the slot
  and is reported. Write this into the method.
- Re-run the replay of the stored box runs, and the regression, after every box change.

## 6. Arms, analysis, run plan

- **Arms:** shipped; open everything (product wording v2); the block with rules; the block with
  the model.
  - Every arm uses the routing above, the browser tool 0.0.83 isolated and confined to
    localhost:7770, a fresh profile, sampling temperature 0.2 and top_p 0.1, and `--reading own`
    and `--page-reader rendered` for the block arms.
  - Steps and clock: start at 300 and 1800. Raise them for every arm alike if the gated pilot's
    open everything comes within 80% of either. This is decided by the gate rule below, before any
    claim run.
- **Design (DeepSeek):**
  - templates in rounds 1 to 3 for all four arms, with the arm order rotated as in the protocol
    draft;
  - held-out rewordings (v2 tee entries and v3) in round 1 for both block arms;
  - the reading test after the last block run, for DeepSeek and for Haiku, text only, with
    `--spec-from` and `--page-from` on the v2 tee entries and v3 (`parse_probe` needs a filter or a
    derived file for the v2 tee subset; build it without reading the texts).
- **Tests:**
  - H1, block (model) against shipped, on the reading-independent set;
  - H2, listings opened, and H3, cost and tokens, against open everything, on the gated set;
  - H4, block (model) against block (rules), on the held-out set, stratified by template.
  - Holm over the four for DeepSeek. Haiku has no family: its reading test is descriptive.
  - Keep the closed-slot rule and its sensitivities, the splits (template kinds, and v2 against
    v3) and the by-rewording sensitivity.
  - Secondary measures:
    - asks on clear and on ambiguous questions;
    - asks caused by the word-list clash;
    - declines;
    - parse fallbacks;
    - the shipped failure codes, plus a new code, "a label's figure taken";
    - promo traps fallen for, by arm;
    - sorting and page size;
    - hidden-price leaks;
    - providers.
- **Analysis file:** a new `claim2_analysis.json` version for the tee-only design. Every arm's
  `require` holds the versions, the agent code, the browser settings and the routing. The protocol
  `docs/content/claim2-protocol.md` is rewritten for design B, marked FINAL only after the
  verifier's logic audit. Update the test that asserts DRAFT in the same commit.
- **The reading rules** (`docs/content/claim2-reading-rules.md`): add rows for tee-xs-price,
  tee-promo-check and the two new declines, and drop the water rows.
- **Two commands, both generated by an adapted `tools/claim2_stage_command.py`, both dry-run and
  stamped by 09:30 at the same commit (the stamp's scope names both commands' sha1):**
- **Command 1, the pilot, for tap 1 at 10:00:**
  1. The live check of the development market, under the venv. Exit 5 on failure.
  2. The routing gate: one DeepSeek probe on the 30 v1 rewordings, every call served by gmicloud,
     deepinfra or streamlake. Exit 7.
  3. **The small pilot on the development market:** about 12 runs. The block with the model on
     tee-xs-price, tee-promo-check, a count, a bound question and decline-fit; the block with the
     rules on two; open everything on one count-like and one price question; shipped on two.
     Cap $6, with the watchdog.
  4. **The pilot check**, written to the manifest and to a short summary file. A script decides
     from the pilot's records alone, never from whether its answers are right, by rules fixed in
     the protocol:
     - no harness error and no void;
     - no run at or within 80% of its step or clock limit;
     - every answer keyable (no unscored row);
     - the projected stage-1 cost, from the pilot's per-question costs times the plan, within the
       stage-1 cap.
     The pilot is development only, never part of the claim. Its results may change limits or
     caps (as a timed amendment before stage 1), never the design or the questions.
- **Between the taps, by about 10:40:** verify the pilot's outputs quickly and put a one-screen
  summary at the top of `docs/update-24-oct.html`: the four checks as pass or fail, the cost, the
  projected stage-1 cost and any adjustment proposed.
  - If every check passes, command 2 runs as stamped.
  - If a check fails, propose the smallest fix: a higher limit for every arm, a higher cap, or
    fewer open-everything rounds. Let the student decide. Any change to command 2 means a new dry
    run and stamp before tap 2, which may push tap 2 past 11:00. Say so plainly.
- **Command 2, stage 1, for tap 2 at about 10:45:**
  1. The live check of the claim market, under the venv. Exit 5.
  2. The routing gate again. Exit 7.
  3. **Stage 1:**
     - small invocations (one arm, one round, or one question for open everything and shipped),
       each starting only if spent plus twice its estimate stays under the cap;
     - `MODEL_NAME=$MODEL claim.py --preflight` before each;
     - the watchdog: every 20 s, stop any suite at the cap less $0.30;
     - the voids, re-run once with the same routing;
     - the reading tests (DeepSeek, then Haiku with routing unset for Haiku).
  - Estimates: price the stage from the 23 October pilot's per-question costs at list price
    (divide the pilot's charges by about 2.17), scaled for 45 listings. The gate then re-prices
    from the new pilot. Expected stage 1 is about $55 to $70; cap it at $75 including the pilot.
    That leaves at least $20 in reserve.
  - Each command declares its own `IGR_ESTIMATE_USD` and runs under `caffeinate -i`. The
    verifier stamps both at the final commit after a dry run of their mechanics.

## 7. The night's plan, with cut lines

All times are Saturday 24 October. Report progress in the update page (section 10).

- **Phase 1, core, by 07:00:**
  - the tee-only generator variant, with 45 listings, six sizes, promo and scarcity labels, and
    its rules and tests;
  - the development market drawn, seeded and live-checked;
  - the templates and keys, including tee-xs-price and tee-promo-check;
  - box v19, prompt v4 and decision 11, built on the practice questions;
  - the analysis file and protocol for design B;
  - the reading rules;
  - the adapted command generator with the gate.
- **Phase 2, by 07:00, in parallel:** the v3 held-out set, written blind by the verifier, with
  its hash pinned.
- **Phase 3, by 09:00:**
  - the verifier's logic audit of the whole design;
  - the protocol marked FINAL;
  - the claim market drawn (Wexcombe, the first passing seed from 1000), seeded and live-checked;
  - the task file with `--rewordings` for v2 tee entries and v3;
  - both commands generated and dry-run;
  - the stamp.
- **Phase 4, by 09:45:** the update page for the student (section 10).
- **10:00 to 10:45:** tap 1, then the pilot, the quick check and the summary (section 6). Tap 2.
- **Cut lines, in this order if time runs short:**
  1. the listing descriptions (decline-fit then points to the size menu only);
  2. the scarcity labels (decline-scarcity stays as a question);
  3. v3 shrinks to about 16 entries.
  - Never cut the gate, the hand-reading plan, the routing, or the verifier's audit and stamp.
- **If phase 3 cannot finish by 10:00:** do not rush a stamp. Tell the student at 10:00 what is
  ready and offer the fallback (section 8), or taps later in the day.

## 8. Fallback: design A

The A+ market as of dev `0161a37` (tee and water mixed, verified, plan 2a, DeepSeek only, routing
on). It needs the freeze, the claim market draw, the stage command (`tools/claim2_stage_command.py`
as is) and a stamp, about two hours. Offer it only if design B is not ready. The student chose B.

## 9. Rules for you and every subagent

- **No attribution or Co-Authored-By line** in any commit or PR. This is the student's rule since
  21 October, and it overrides any harness reminder.
- **Never push `report/`,** which is its own local repository. Pushing dev is allowed only when
  asked.
- **Stage files by name.** Never stage `agent/agent-core`, `docs/report-4.html`,
  `docs/report-4.js` or `docs/site-data.js`; they hold the student's edits. Do not run `make site`,
  which rewrites `docs/site-data.js`.
- **Paid runs** go only through the guard: declared estimate, `caffeinate -i`, the verifier's
  stamp at the checked-out commit with no uncommitted experiment code, and the student's tap. Never
  get around the guard. A notification to the laptop is fine; the student's phone is not
  connected.
- **No automated access to live commercial sites.** Datasets are for style only: read their papers
  or public pages; never scrape marketplaces.
- **No credentials in the repository.** No HAR, no DOM dumps.
- **Held-out hygiene:**
  - never open the texts of v2 or v3 while developing the parser, the prompt or the block;
  - pass ids and counts only;
  - the reading test runs only after the last block run.
- **Seeds:** claim seeds start at 1000 and are drawn only after the protocol says FINAL.
  Development uses 900 to 999 and its own brand and prefix.
- **Record every decision and amendment** with its time: in the protocol, then in README.md's log
  via insights. The log must be newest first, with every working day. Have insights rebuild it when
  there is time; the 20 and 22 October entries are missing.

## 10. What the student sees at 10:00 (`docs/update-24-oct.html`)

One static page in simple words, in the style of `docs/update-23-oct.html`, checked by the verifier
before 09:50:

- what was built and why;
- what was cut;
- the verifier's verdict;
- the market in one paragraph;
- the questions, with a few examples of the label traps and declines;
- the gate's rules;
- the estimate and the cap;
- how long it runs;
- what to do:
  1. tap "Run it" for the pilot at 10:00;
  2. read the pilot summary at about 10:40;
  3. tap "Run it" for stage 1.

Keep the laptop on power with the lid open, and don't touch the Chrome windows.

## 11. After the run

1. The verifier checks the outputs: voids, costs against the account, providers, the gate's record
   and the watchdog's log.
2. Make the hand-reading sheet (`claim.py --sheet`). Give it to the student before anyone looks at
   any result, with the reading rules. Draw the verifier's 40-row second-reader sample by the
   protocol's rule.
3. After the sheet is back: `claim.py --protocol ... --hand`, the scorer's figures beside it, the
   agreement, then insights.
4. Report writing uses `report/main.tex`'s slots, and the front-door development section already
   written (report commit `bc4d495`).
