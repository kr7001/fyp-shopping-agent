# Lessons

Every mistake this project has made that cost time, money or a wrong claim, with the rule it
produced and who enforces the rule. The coder, verifier and insights agents read this before
they work. Add to it whenever a new mistake is found. Never delete an entry.

Who enforces: **C** coder, **V** verifier, **I** insights, **G** the workbench guard (the mod in
`tools/workbench/`), **M** the main conversation.

## Counting and measuring

| # | What happened | Rule | Who |
|---|---|---|---|
| 1 | The second agent's link cap sent twelve runs to missing pages. The listing counter counted the 49 missing pages as listings opened, and "3.7 listings opened" was reported before anyone looked | Every counter is run on a batch where the fault is known to exist, and must find it, before it is trusted on a new batch | C, V |
| 2 | The listing counter recognised URL shapes rather than the idea of a product page, and read zero three times in three different ways | Count by what a thing is, not how one example of it is spelled, and test the counter on every scaffold | C, V |
| 3 | Sizes chosen inside `browser_batch_interact` were not counted as selections. 28 went missing, and a run reported as choosing nothing had chosen eleven | Before counting an action, list every tool the agent has that can perform it, from the agent's own tool schema | C, V |
| 4 | The scorer took the first number in an answer as its count, so "after checking all 15 listings, I found 5" scored as 15, and was then described to the user as "counted the whole market" | Read every answer in full, not only its verdict. A scorer change re-scores every stored run and keeps the old verdict beside the new | V |
| 5 | "Met the floor" used eight listings for every question, where each question type needs a different amount of evidence | Define every measure per question type, in writing, before computing it | C, V |
| 6 | Cost was taken from the account balance, which lags and billed one run 32 times its own spend. Tokens times price was also wrong, because it ignores caching | Cost is the provider's charge per call, summed, then checked against the account per batch | C, V |

## Statistics

| # | What happened | Rule | Who |
|---|---|---|---|
| 7 | Runs from different arms, catalogue draws, models and scaffolds were pooled into one figure, six separate times | An arm's identity includes market draw, model, scaffold, shop, probe setting and every strategy and rules version. Never pool across any of them | V, I |
| 8 | Fisher's test was run on pooled runs, ignoring that questions differ hugely in difficulty | Compare within each question first, then combine (stratified exact test) | V, I |
| 9 | The second agent runs at temperature 0, so its three repeats were the same run three times. Its fifteen runs were reported as fifteen pieces of evidence and one comparison as "settled" | Check that repeats differ before counting them. Report the unit of evidence. Claim strength follows the corrected test | V, I |

## Fairness and environment

| # | What happened | Rule | Who |
|---|---|---|---|
| 10 | The fairness audit held model, window, steps and shop constant, and missed that the two agents sample differently (0.2 against 0) and that only one has a ten minute clock | The held-constant table lists sampling, step budget, wall clock, viewport, shop and theme, tool versions, caches, question text byte for byte, scorer and rules versions | V |
| 11 | openJiuwen kept a selector cache in the home directory that outlived every run, so run 18 was a different experiment from run 1 | Every run starts from clean state. Look for state a tool keeps between runs | C, V |
| 12 | The browser tool is fetched as "latest" on every run, so a release mid-batch would change the tool | Record tool versions, and check them before and after every batch | V |
| 13 | Our own gated theme reveals a price 60 ms after a size changes. One run's own script read the price before that and answered wrongly | Every change we make to the environment is listed as a condition. Reproduce a mechanism on the live shop before describing it | V, I |
| 14 | The first gated shop put the theme on a store view, and product pages leaked every price. $2.72 of runs measured a mixture of two shops | Check the environment property itself, in a real browser, before any run depends on it | V |
| 15 | The laptop slept on battery in the middle of a batch. Three runs were suspended for up to 50 minutes and voided, $2.18 wasted | Paid runs are wrapped in `caffeinate -i`. A run whose log is silent for more than 60 seconds is void, by rule, before its answer is read | G, V |
| 16 | The word "offer" in two questions has two reasonable meanings, and nobody noticed before running them | Before a question runs, write down every reasonable reading and the answer under each. Ambiguity found later is kept and reported, never quietly fixed | V |
| 17 | Strategy text told the agent "the search results are paginated" and that a disabled size's "price is still printed". Both were false in the shop being tested | Check every factual statement in agent-facing text against the current environment | C, V |
| 18 | The control question was routed to a strategy that tells the agent to open listings | Run the classifier over every question, controls included, and read the result | C, V |
| 19 | Strategy changes were designed on the same market they were then going to be tested on | The market used to design or tune is never the market used to claim. Claims need a market the box was not tuned on | V, I, M |

## Claims and documents

| # | What happened | Rule | Who |
|---|---|---|---|
| 20 | A claim about openJiuwen was traced to project notes instead of its code, and another accused its authors of a false claim that was true | A claim about code cites the file and line it rests on | V, I |
| 21 | One run's failure was described as "chose the size and never looked". It had looked, then re-read the page too early | Trace the whole step sequence before describing a mechanism | V, I |
| 22 | Numbers typed into pages by hand were wrong: a "4 of 12" no one could reproduce, a "thirteen to one" its own figures contradicted, a $0.49 that rounds to $0.48 | Numbers in documents are generated by code and cross-checked. Every figure has a command that reproduces it | I, V |
| 23 | Results were reported to the user before they were verified, and three had to be corrected later | Verify before reporting | M, V |
| 24 | A checker reported failures against a healthy shop three times: labels written by JavaScript, a range string Magento never prints, a hidden wishlist card. Another read "8.4 litres" as $8.40 | When a check fails, suspect the check first. Validate it on a known good case and a known bad case | V |

## Process

| # | What happened | Rule | Who |
|---|---|---|---|
| 25 | About $30 of credit was spent quickly without the user seeing it coming, and the supervisor flagged it | No paid run without a declared estimate and the user's explicit yes | G, M |
| 26 | Weeks of side investigations without a decisive result | Every task names the part of the objective it serves. Side ideas go to `PARKED.md` with `/park` | G, M |
| 27 | A careless edit deleted functions from `trace_stats.py`, and a broad `pkill` killed the assistant's own shells | Edit with exact anchors, review the diff before committing, never use broad destructive commands | C |
| 28 | The old main page was overwritten by the new site, written to the same path before the old file had been moved to the archive. It was recovered from git | Move or copy a file away before writing a new one to its path | C, M |
| 29 | Two September scripts kept adding two models and two agents into one Calderwood row, 28 runs where like for like there are 12, weeks after the rule against pooling existed. The rule had been applied to new code only | When a rule is adopted, search the existing scripts for the old pattern too, and fix or list each one | V |
| 30 | A paper whose licence lets only arXiv distribute it was committed to a repository that is public, and nearly pushed | Check the licence of any file this project did not write before committing it. Cite papers by their id | C, M |
| 31 | A test was named for a fault it could not catch: with the scorer's price exclusion removed, all three count tests still passed. Another check for answer key reads missed four of five planted reads | Before claiming a test catches a fault, plant the fault and watch the test fail | C, V |
| 32 | The refusal check was presented as part of the box, but it reads the market size and the fewest sound openings from the answer key. Without them it refused none of the nine failures it was credited with | Before calling a component part of the box, list every input it reads and check each is visible to the agent | V, I |

## Reading the runs, from the box v2 batches of 14 October 2026

| # | What happened | Rule | Who |
|---|---|---|---|
| 33 | The listing counter, in its fourth form, counted the category page `electronics.html` as a listing opened, because it recognised a `.html` path rather than membership of the market. One stored count moved from 2 to 1 (lesson 2, a fourth time) | Count a listing by membership of the page's own listing set, read from the box's page record, else by the generated market's product page, and never by the shape of a URL. Replay the counter over every stored run and list each count that moves | C, V |
| 34 | A run with no answer key, the "softest tee" fallback, ended without `ok` and was scored failed, so it sat in the wrong column as if a key had judged it | Order the scorer by what the key can say: no key means unscored, whatever the run did. When the scorer version changes, re-score every stored run, record the version and the reason in the batch, and keep the old verdict beside the new | V |
| 35 | The survey fallback took "who sells the softest tee", an attribute no page shows, opened all 15 listings for $0.80 and found nothing, because the fallback was not held to the fifth soundness property | Every plan, the fallback included, is held to every soundness property before it is rendered. A shape the box does not know is still refused when its attribute is not shown | C, V |
| 36 | `--allowed-origins` was recorded as confining the browser to the shop. It confines network requests only: a bypassed run composed a `data:` page of its own and navigated to it with no request made | For every confinement flag, record what it does not cover, and test the gap with a run that tries it. Service workers are blocked too, and the second agent, which is not confined at all, runs no bypassed question until it is | C, V |
| 37 | The menu reader took a `browser_find` excerpt, the matched line and three more with no gap marker, for the whole size menu, so a size cut off the excerpt counted as absent and a "No" was supported by a menu that had the size | Before absence from an observation counts as evidence, check the observation is complete. Every log reader is validated against the fixture on every stored run: the readings it calls complete must equal the fixture's menu, and the partial ones must be a prefix of it | C, V |
| 38 | A snapshot taken with a depth limit prints a menu beyond it as a leaf, a head line with no children and no marker, and the reader took that for a complete menu with no sizes | A head line without a trailing colon has no rendered children and gives no reading at all. Checked on every stored snapshot line: heads with a colon always have a child, heads without never do | C, V |
