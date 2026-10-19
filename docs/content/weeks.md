# Weekly log

One entry per week, written from the dated record: the README decision log, the supervisor
updates in `docs/archive/updates/`, and the commit history. The commit count beside each week
is added by `docs/build_site.py` from `git log`. A week with nothing dated in any of those is
listed as such, with no reason given, because none was recorded.

## Before 17 August

*Supervisor update 1, undated. Its findings were entered in the decision log on 28 August,
when the repository was created.*

- Set up the WebArena-Verified shopping site locally in Docker. Elasticsearch hung on Apple Silicon while still reporting as running, so the catalogue looked almost empty
- The catalogue holds 104,368 products, all of one simple type. Options exist but never change the price, so the shop had gated options and no gated prices
- Checked the structured data on WebArena and Shopee. Both publish one price for a product sold at several, where schema.org has AggregateOffer for exactly this case. So a lower bound for pruning cannot come from structured data

## Week of 17 August

*Supervisor update 2, 20 August.*

- Reframed the project from a security question, whether injection defences catch manipulated feeds, to a retrieval one: the same wrong answer happens with no attacker at all
- Chose an existing shop (WebArena) and an existing open source agent (openJiuwen) over building both
- Wrote up the motivating case. A live listing with four pack sizes shows one price at a time, and its JSON-LD price stays at the cheapest pack whichever size is chosen

## Week of 24 August

- Repository and decision log created on 28 August
- Recorded that products with a different price per size would have to be authored, since the shop has none

## Week of 31 August

No commits, notes or updates are dated in this week.

## Week of 7 September

*Supervisor update 3, 9 September.*

- Found the real cause of the Elasticsearch hang: Rosetta was off in Docker Desktop, so the shop ran under slow emulation. Cold boot went from never finishing to 20 seconds
- Authored the first gated products, 4 listings with 14 sizes, and ran openJiuwen end to end for the first time. The RQ2 baseline: 60 runs, and not one said it was unsure
- Cheaper models failed. One could not hold openJiuwen's output format and two were rate limited, so Claude Haiku 4.5 became the working model
- Built the sufficiency check, a rule that asks whether an answer is supported by what the run actually opened, and replayed it over finished runs at no cost
- Asked the agent how confident it was. The number did not separate right answers from wrong ones (AUROC 0.528, where 0.5 is no signal)
- Generated two 15 listing water markets, Rivenhall to develop on and Calderwood to test on, and measured the "open everything" upper bound
- Strategy text plus the check matched "open everything" on accuracy with fewer actions on Rivenhall, and gave no wrong answers on Calderwood. One version was reported and withdrawn the same day: it had read the first four listings as the whole market

## Week of 14 September

- Over 13 and 14 September, found that the small fixture's product pages carried the answer key, written there by my own seeder. Removed it and re-ran the baseline clean
- Fixed a counting bug in the checker and a yes or no bug in the scorer, and gave every batch a market id, so runs on different markets are never added together
- The faculty credit of $50 arrived. Completed the held-out market with 12 runs each of the agent as shipped, "open everything", and strategy plus check
- Wrote the coverage rule from the principle before the next market existed, and the planner that turns a question into a plan
- Built a shop theme that hides each size's price until the size is chosen, selected by the browser's user agent. The first attempt, on a store view, leaked prices on product pages and cost $2.72
- Built a second agent from scratch with no card probe, and a clothing market, Thornwood, where a size can be absent, sold out or buyable
- Progress report and checkpoint slides, 18 September

## Week of 21 September

No commits, notes or updates are dated in this week.

## Week of 28 September

No commits, notes or updates are dated in this week.

## Week of 5 October

- Found the second agent's first 12 runs were void. A link cap of mine meant it never reached a product page. Fixed, and its cell re-run
- Gave each openJiuwen run its own selector cache, and switched cost to the provider's charge per call
- Ran cells 1, 2 and 3 on the clothing market. The four listing behaviour comes from one default in openJiuwen's card probe, which reports only the cards inside the browser window
- Wrote the 7 October update deck for the supervisor
- Re-derived every figure from the raw run files the next day, found three figures from 7 October were wrong, and corrected them
- Ran cell 5, openJiuwen told to open everything. The laptop slept mid-batch, so three runs were voided by rule and re-run
- Stepped back. Wrote `OBJECTIVE.md`, `LESSONS.md` and `PARKED.md`, and set up the workbench mod and three subagents, so the work stays on the objective and nothing is spent without a check
- Reorganised the code into folders, added unit tests, and replaced five pages with this site. The verifier failed it four times on claims stronger than the evidence, and passed it on the fifth
- Rewrote the history not yet on GitHub, so it could be published: the openJiuwen paper out of every commit, and Magento's licence notice into every copy of the gated theme's template

## Week of 12 October

- Wrote the box v1 specification overnight on 13 to 14 October, built it with 90 tests, pinned the browser tool at 0.0.83, and had the verifier pass the pilot command before anything ran
- The pilot, 14 October, 08:43: two runs, both correct, $0.61 charged against $1.05 declared. The cheapest question opened the 8 listings the advertised prices could not rule out and skipped 7
- Researched what the shopping benchmarks ask and what has been built for adaptive retrieval and clarification, and designed box v2 from it: a logical form per question, five soundness properties, seven retrieval primitives. Built it the same day, with the six clothing questions rendering byte for byte what v1 rendered
- The census parse: a model wrote the logical form of all 37 questions for $0.069 and agreed with the rules on the plan-deciding fields for 33 of 37
- A question the box cannot classify bypasses it, at the student's request, and the gated browser is confined to the shop's origin
- Progress report 4 and a short update written for the supervisor meeting
- The development batches, 14 October evening: 32 agent runs in three batches on Thornwood, $6.96 charged against $11 declared, their verification left for the following week

## Week of 19 October

- The verifier passed the three batches of 14 October and found six things, fixed in box v7: a bare "No" is supported by an observed menu without the size, an attribute the shop does not show is refused whatever the word, a keyless run that did not finish is unscored, two written kinds of error, the listing counter's fourth correction, and the development cell in `compare_cells`. The browser now blocks service workers too
- The verifier then failed the new menu reader twice before accepting it: a search excerpt is not a whole menu, and a depth-cut snapshot prints a menu with no sizes. Box v8 and v9, 254 tests, frozen for the fresh market
- Six lessons added, 33 to 38. The site gained the development cell, in sample and never pinned, with every answer of the three batches in full
