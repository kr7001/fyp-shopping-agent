# Shopping agents under interaction-gated information

FYP, NUS Data Science and Analytics, Aug to Nov 2026.
Student: Kayleen Lee Kai Rong. Supervisor: Prof. Markus Kirchberg.

See [CLAUDE.md](CLAUDE.md) for the full problem statement, research questions and method sketch.

---

## Running the WebArena environment

The environment is the ServiceNow **WebArena-Verified** shopping distribution, run as two
self-contained Docker images (Magento 2 + MySQL + Elasticsearch + Redis under supervisord,
all inside one container each). Chosen over the original WebArena images because they are
considerably smaller and correct known annotation bugs.

| Container | Image | URL | Purpose |
| --- | --- | --- | --- |
| `webarena-shopping` | `am1n3e/webarena-verified-shopping` | http://localhost:7770 | Storefront. This is the one experiments run against |
| `webarena-shopping-admin` | `am1n3e/webarena-verified-shopping_admin` | http://localhost:7780 | Magento admin. Only needed for authoring products |

Both images are amd64 and run under emulation on Apple Silicon. First boot is slow.

### Everyday start

Docker Desktop must be running first (`open -a Docker` on macOS, then wait for the daemon).

```bash
./env/start.sh            # storefront only
./env/start.sh --admin    # storefront and the admin panel
```

The script starts the container, waits for Elasticsearch, then checks the catalogue
actually returns products. That last check matters: Magento serves a 200 while its search
engine is still booting, and in that window the shop looks empty for no visible reason.
A plain `docker start` cannot tell the two states apart.

By hand, if preferred:

```bash
docker start webarena-shopping
# admin panel, only when authoring products
docker start webarena-shopping-admin
```

Then wait for Elasticsearch to finish booting before touching the site. It is the slow part
and the site looks broken until it is green:

```bash
docker exec -it webarena-shopping wget -qO- "http://localhost:9200/_cluster/health?pretty"
docker exec -it webarena-shopping supervisorctl status
open http://localhost:7770
```

Quick check that the catalogue is actually indexed, not just that the site returns 200.
An empty result here is the Elasticsearch failure below, not a missing product:

```bash
curl -s "http://localhost:7770/catalogsearch/result/?q=cake+topper" | grep -c product-item-link
```

Admin credentials for the admin container are the WebArena documented defaults,
`admin` / `admin1234`. Not verified from a login in this repo yet.

### First-time setup, from nothing

```bash
docker pull am1n3e/webarena-verified-shopping
docker run -d --name webarena-shopping \
  -p 7770:80 -p 7771:8877 \
  am1n3e/webarena-verified-shopping

# admin, optional
docker pull am1n3e/webarena-verified-shopping_admin
docker run -d --name webarena-shopping-admin \
  -p 7780:80 -p 7781:8877 \
  am1n3e/webarena-verified-shopping_admin
```

After the first run the catalogue indexes have to be built once, see the Elasticsearch note below.

### Stopping

```bash
docker stop webarena-shopping webarena-shopping-admin
```

Use `stop`, not `rm`. The container holds the MySQL data directory, so removing it discards
the catalogue and any products authored for the experiments.

---

## Known issue: Elasticsearch appears to hang on Apple Silicon

**Symptom.** Site loads but the catalogue appears almost empty. Category pages show no
products, search returns nothing. `supervisorctl status` reports `elasticsearch RUNNING`,
so the failure is silent. Port 9200 never starts listening.

**Root cause, found 2026-09-08.** Not an Elasticsearch problem. Docker Desktop was running
the amd64 image under QEMU user-mode emulation instead of Rosetta:

```bash
python3 -c "import json;d=json.load(open('$HOME/Library/Group Containers/group.com.docker/settings-store.json'));print(d['UseVirtualizationFrameworkRosetta'])"
# False
```

With Rosetta off, every amd64 instruction is interpreted. The JVM bootstrap is the worst
case for this. Observed here: the pre-launch `qemu-x86_64 .../java` process accumulated
5m52s of CPU time at a pegged 100% of one core without reaching Elasticsearch's first
log line. It is not deadlocked, it is being emulated roughly an order of magnitude slower
than it needs to be. Everything else in the container tolerates that; a 512MB-heap JVM
does not.

**Fix, measured 2026-09-08.** Docker Desktop, Settings, General, enable *Use Rosetta for
x86_64/amd64 emulation on Apple Silicon*, then restart Docker Desktop. Requires macOS 13+.

| | Elasticsearch cold boot to cluster health |
| --- | --- |
| QEMU (Rosetta off) | 19 min, never reached healthy. Three attempts, none completed |
| Rosetta on | **20 s** |

Confirm which translator is actually in use. Under QEMU the process list shows
`qemu-x86_64`; under Rosetta it shows `/run/rosetta/rosetta`:

```bash
docker exec -it webarena-shopping sh -c 'ps -o args | grep -c "[q]emu-x86_64"'   # 0 when Rosetta is on
docker exec -it webarena-shopping sh -c 'ps -o pid,args | grep [j]ava | cut -c1-80'
```

Caveats. Rosetta implements fewer x86 instruction extensions than QEMU, so software using
them crashes rather than running slowly. This container is Alpine/musl, historically the
less reliable case for Rosetta. Nothing in this stack has hit either problem, but the
setting is one checkbox to revert if something does.

**Confirming it is this and not something else:**

```bash
# 9200 never opens
docker exec -it webarena-shopping sh -c 'netstat -tln | grep 9200'
# the JVM is burning CPU rather than blocked
docker exec -it webarena-shopping sh -c 'ps -o pid,etime,time,args | grep [e]lastic'
# the log stops at the seccomp warning and never reaches "version[7.17.0]"
docker exec -it webarena-shopping sh -c 'tail -5 /usr/share/java/elasticsearch/logs/elasticsearch.log'
```

The `seccomp unavailable: CONFIG_SECCOMP not compiled into kernel` warning at the top of
that log is normal inside Docker and is not the problem.

**If the catalogue is still empty once Elasticsearch is up,** the indexes were never
built. Reindex by hand, which is slow but only needed once:

```bash
docker exec -it webarena-shopping php /var/www/magento2/bin/magento indexer:reindex
docker exec -it webarena-shopping php /var/www/magento2/bin/magento cache:flush
docker exec -it webarena-shopping php /var/www/magento2/bin/magento indexer:status
```

Note that all indexers ship in **Update on Save** mode, so any product write triggers an
inline fulltext reindex and will fail while Elasticsearch is down.

`xpack.ml.enabled: false` in `/usr/share/java/elasticsearch/config/elasticsearch.yml` was
tried in August as a fix and did not help. It was reverted.

---

## Database access, for ground truth

Magento's DB is inside the container. Credentials come from
`/var/www/magento2/app/etc/env.php`:

```bash
docker exec -it webarena-shopping grep -A 20 "'db'" /var/www/magento2/app/etc/env.php
```

Working query, catalogue composition:

```bash
docker exec -it webarena-shopping mysql -u magentouser -pMyPassword magentodb -e \
  "SELECT type_id, COUNT(*) FROM catalog_product_entity GROUP BY type_id;"
```

These are the fixed WebArena image credentials, not secrets, and are not reachable from
outside the container.

---

## Market ledger

A market can be spent once. The moment its failures are examined, any rule written
afterwards is fitted to them, and it stops being able to test that rule. Runs already
recorded against it stay valid as measurements. What is lost is its use as a held-out test.

Keep this table current. It is the only record of which market may still test what.

| Market | Listings | Status | What it may still be used for |
| --- | --- | --- | --- |
| small fixture | 4 | **Development.** Authoring notes removed 13 Sep 2026, everything before that is a different environment | RQ2 baseline. Not a held-out test for anything |
| Rivenhall | 15 | **Development.** The targeting strategies were written and twice corrected against its failures | Cost and action comparisons. Not a held-out test |
| Calderwood | 15 | **Spent 17 Sep 2026.** Held out until then, and its nine failures have now been read, which is what produced the coverage rule | Reporting the held-out result already measured. It cannot test rules version 2 |
| Apparel | planned | **Reserved.** Generated after rules version 2 is frozen, so it can test it | The held-out test for the coverage rule, and the first market with two gates at once |
| Calderwood-S | planned | **Reserved.** Calderwood's prices with the variant prices suppressed in the DOM | Measuring what the Magento price leak was worth, with answers held identical |

Two rules follow from the table and are worth stating separately, because both have already
been broken once.

**Freeze before generating.** A rule written after seeing a market's failures cannot be
tested on that market. Write it from the principle, record the version, then generate the
next market.

**One change per comparison.** When the DOM changes, prices stay identical. When the
scaffold changes, the model stays fixed. When the model changes, the scaffold stays fixed.

### The metric that survives a change of scaffold

`actions` counts what `trace_stats.py` classifies from openJiuwen's tool calls, so it is not
comparable across agents that name their tools differently. Two figures are:

| Metric | Where it comes from | Why it transfers |
| --- | --- | --- |
| Listings opened | `sufficiency.listings_opened`, from URLs in the trace | A product page visit is a property of the browser, not of the agent |
| Cost per run | OpenRouter usage delta around the run | Tokens are tokens |

Report those two first when a second scaffold arrives. Actions stay in the tables as a
per-scaffold detail.

---

## Decision log

### 2026-08-28
- WebArena-Verified shopping site running locally via Docker (amd64 under emulation on M-series)
- Catalogue: 104,368 products, all `type_id = simple`. No configurable products
- Product options exist (e.g. colour on cake topper SKU B09GFC1D5R) but are Magento custom options, so price does not vary by selection
- Implication: environment provides interaction-gated options but not per-variant pricing. Configurable products with divergent prices will need to be authored for the experiments

### 2026-09-08
- Environment startup procedure documented above, so runs are reproducible from a cold machine
- Root cause of the August "Elasticsearch hangs" issue identified and fixed: Docker Desktop had Rosetta emulation disabled, so the amd64 JVM ran under QEMU interpretation. Not an Elasticsearch or Magento fault. Cold boot to cluster health went from 19 min and never completing, to 20 s. Two intermediate theories were tried and discarded first, `xpack.ml.enabled` in August and "restart the container rather than the service" today. Neither held up; both are recorded above so the dead ends are not repeated
- Timings recorded before and after the change are not comparable. Anything measured prior to 2026-09-08 ran under QEMU
- Catalogue audit extended from product types to option pricing. 425,384 select-type option values and 68,584 non-select options, **none** carrying a non-zero price delta. Confirms the environment has option variance but no price variance, from the database rather than by inspection
- `env/` now holds `seed_variants.py`, which authors configurable products with per-variant pricing over the Magento REST API and writes a ground-truth manifest per run. See [env/README.md](env/README.md)
- Seeded and verified: 4 configurable parents and 14 variant children, all prefixed `IGR-`, plus 3 new attributes on attribute set 4. No existing WebArena product was modified. The environment now has interaction-gated pricing it did not have before

### 2026-09-18, later
- **Phase 2 built: the shop now has a variant price that is genuinely gated.** Magento hands the browser the whole price table on first load and renders every option label with its surcharge, `2 x 9.5L +$32.50`, so the thing this project studies was readable without interacting. A theme override flattens the price table, and the theme is selected by **user agent**, so ordinary browsing and every recorded run are untouched. Same products, same prices, same answers, same URLs. Verified in a real browser: labels lose their surcharges, the page holds one price instead of four, and selecting the option still reveals the true $48.64. See [env/README.md](env/README.md)
- **The mechanism was wrong the first time and cost $2.72.** The theme was first put on a second store view. Magento carries the store only in the query string or a URL prefix, so the agent searched with `___store=gated` and then followed ordinary product links: the search page rendered suppressed and every product page rendered leaky. Confirmed afterwards by fetching a product URL with the store cookie set, which returns all four prices. That twelve run arm measured a mixture of two environments and is recorded as `superseded` inside its own `suite.json` rather than deleted
- **Two ways to take the whole shop down, both found by doing it.** `design/theme/ua_regexp` is handed straight to `preg_match`, so the pattern needs delimiters, and Magento reads the key `regexp` rather than `search`. Either mistake returns 500 on every page of the shop. Down twice for about a minute, with nothing running
- **In the verification run the unmodified agent selected a pack size twice**, which it had never once done on a fifteen seller market across 122 recorded runs. With the surcharge gone from the label there is nothing to add, so it has to interact. That is the mechanism working
- **A third instrument bug, in the listing counter.** The store view attempt served product URLs in Magento's id form, which neither pattern matched, so every gated run reported zero listings opened. Since the coverage rules read that count, they would have refused everything. Every URL form now reduces to the listing's url key, so a listing counts once however it was reached. Set sizes are unchanged on every existing run, so no recorded verdict moves
- **A fourth, in the replay.** It grouped runs by catalogue draw, which was right until a second model existed, and the four deepseek runs were being added to haiku's fifteen. Tables are now keyed by draw and model together
- **Phase 2 measured. Closing the variant gate changes what the agent does and not whether it is right.** Twelve unmodified runs with the labels suppressed, against the twelve already recorded on the same market with the ordinary theme:

| Arm | Right | Actions | Opened | $/run | Selected a size | Label arithmetic |
| --- | --- | --- | --- | --- | --- | --- |
| Ordinary browser | 3 of 12 | 10.2 | 6.5 | $0.137 | 0 of 12 | 4 of 12 |
| Suppressed labels | 2 of 12 | 18.3 | 5.8 | $0.224 | **8 of 12** | **0 of 12** |

- **The gate now behaves like a gate.** Selection goes from 0 of 12 to 8 of 12. Across 122 recorded runs on the fifteen seller markets the unmodified agent had selected a pack size twice in total. With nothing to add in the label it has to interact, and it does
- **It costs 64 per cent more and buys nothing.** Actions rise 10.2 to 18.3, cost $0.137 to $0.224, accuracy moves 3 of 12 to 2 of 12, which at twelve runs is noise. The leak was saving the agent effort rather than saving it from being wrong
- **The failure was never the variant gate.** Coverage separates the verdicts identically in both arms: every right answer opened 12 to 15 listings, every wrong answer opened exactly 4. That is the two-layer reading measured rather than argued. The listing-level gate is what the results are about, and the variant-level gate, real on the live marketplace, was cosmetic in this shop for this agent
- **Phase 3 built and first result in, and the prediction was wrong.** `experiments/naive_agent.py` is a second scaffold written from scratch: four tools, no card probe, no advice about how much to look, matched to openJiuwen on model, step budget and viewport and judged by the same scoring, gate and coverage counter. The prediction recorded beforehand was that a loop with no probe would under-retrieve less

| Scaffold | Runs | Right | Refused | Wrong | Opened | Actions | $/run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openJiuwen | 12 | 3 | 0 | 9 | 6.5 | 10.2 | $0.137 |
| From scratch, no probe | 12 | 4 | 1 | 7 | **3.7** | 21.6 | $0.871 |

- **It under-retrieves more.** It spends its actions re-searching, sorting by price, sorting by name, paging and rephrasing the query, opening 3.7 listings on average across 21.6 actions. So the four card ceiling is not what makes the agent stop early: a scaffold with no ceiling stops sooner, for six times the money. The probe both causes the ceiling and carries the agent further than a bare loop does, which puts the failure in the model's judgement about when it has looked enough rather than in one agent's default. Recorded with the prediction it falsified
- **Per question, the difference is not spread evenly**, and where it sits is the interesting part. The naive loop answers "does every listing stock the pack" **3 of 3** where openJiuwen manages 1 of 3, and answers neither superlative question at all, 0 of 6. Its right answers opened 2, 2, 3 and 3 listings and its wrong ones opened 2 to 9, so coverage stops separating the verdicts for this scaffold, and it should: the question it answers is the one a single counterexample settles. **How much retrieval an answer needs is a property of the question rather than of the agent**, which is what the planner encodes and what the coverage rule tests per question kind. The project's own thesis turning up in its control
- One caveat next to that single refusal: the naive prompt says to say so rather than guess when the answer cannot be determined, and openJiuwen's does not, so 1 refusal in 12 is not comparable with 0 in 125. Written before any of these runs and left as it is
- **A fifth instrument bug, in the measure that was supposed to be scaffold independent.** The listing counter recognised URL shapes rather than the idea of a product page: `page.goto` only at first, then `igr-*.html` only, and it read zero for every naive run because that scaffold follows the site's own links, which are named after the product. Magento serves a product page as a single path segment ending in .html or as an id path and serves nothing else that way, so that is the rule now, one rule for every scaffold. It reproduces openJiuwen's validated figures exactly, so no recorded verdict moves
- **A sixth, in the replay again.** It pooled the naive runs into openJiuwen's baseline. Tables are keyed by draw, model and scaffold together. Three dimensions have now each widened a denominator the first time they appeared

### 2026-09-18
- **Phase 0 done, no spend.** `superlative_without_coverage` written from the principle that a superlative over a population is only determined by evidence covering that population, thresholded at the oracle floor the generator already computes, and frozen before the market that will test it exists. Replayed free over the 125 unmodified runs on current draws: wrong answers withdrawn goes **19 of 31 to 29 of 31**, held-out **3 of 9 to 9 of 9**, correct answers withheld 3 of 94 to 5 of 94
- **The same rule refuses four answers the policy arm got right.** They opened 9 listings where the floor is 11, so the policy prunes further than its own bound licenses and was right anyway on these draws. Under the new rules the held-out policy arm reads 7 correct, 5 refused, 0 wrong against the 11, 1, 0 it was measured as. Both are reported. This is the sharpest instance of right against earned in the project and it was found by a rule rather than by a score
- `planner.py`: plans carry the population, the bound, the stop rule and the evidence the answer will be held to, and the instruction text is rendered from the plan, so the policy and the check cannot drift apart. `--regression` asserts byte-identical text to the frozen strategies for all 22 questions. Suites now record `rules_version` and `model`
- **Market ledger added to this file.** A market can be held out once, and Calderwood is now spent
- **Phase 1, two probes, $0.14 total.** Both were built to decide what to build next rather than to produce a headline
- **The model can write its own retrieval plan, mostly.** 8 questions, 2 conditions, 16 calls, $0.028. Told only the schema it produces a sound plan **6 of 8** times, and told the four soundness properties as well, **7 of 8**. The two blind failures are both the historical mistake, bounding over a population without enumerating it first. The guided failure is a counting question labelled as universal, where the plan was behaviourally right and the label was wrong
- **The probe found two bugs in my own verifier on its first run**, both over-strict: it demanded enumeration of every plan, which is wrong for an existential question where one witness settles it, and it demanded listing coverage for every superlative, which is wrong when the attribute compared is published on the results page. Both now conditional, and the plan records which case it is in
- **The failure the verifier did not catch is the useful one.** Asked "which seller delivers fastest", where the shop publishes no delivery times, the model proposed a perfectly sound plan to open all 15 listings and compare something that does not exist. Every property held. The missing fifth property is that the attribute compared must exist in the environment, and it is the rule the unanswerable question in phase 4 needs
- **A second model works, and the four-card failure is not only the scaffold's.** deepseek/deepseek-v4-flash, same agent, same four gated questions on the held-out market, 1 repeat: **2 correct, 2 wrong at $0.028 per run**, a fifth of haiku's $0.137. It opened 10, 7, 10 and 4 listings where haiku opens 4 on nearly every failing run, and the one run that opened 4 is the one that was wrong. So stopping at the first screen is a property of the model and the scaffold together rather than of the card probe alone, which changes what the second scaffold in phase 3 is testing
- Spend $10.08 of the $50 faculty credit, 35 runs on it so far

### 2026-09-17
- **Faculty credit approved, $50. First call on it was the two arms the held-out market never had.** 27 runs, $8.55. Calderwood had exactly one arm until today, targeting plus gate, so there was no baseline to improve on and no ceiling to be cheaper than. Now: unmodified **3 correct of 12**, exhaustive **10 of 12 with 1 wrong and 1 that produced no answer**. See [notes/heldout.md](notes/heldout.md)
- **The saving now holds out of sample, and is larger there.** The policy arm was topped up from 8 runs to 12 so every arm shares a denominator; the four new runs were 4 of 4 correct. All three arms at twelve runs on one draw: unmodified 3 correct at 10.2 actions and $0.137, exhaustive 10 correct at 28.4 and $0.564, **targeting plus gate 11 correct, 1 refused, 0 wrong, at 14.8 actions and $0.335**. That is **48% fewer actions and 41% less money than exhaustive at better accuracy**, 11 of 11 answered against 10 of 11, where in sample it was 35% and 33% at equal accuracy
- **The unmodified baseline was flattered by the development market.** Rivenhall 21 of 36, 58%. Calderwood 3 of 12, 25%. On Rivenhall the cheapest seller for the target pack sits in the first four cards, so a four-card read is right by luck; on Calderwood it does not and the same read is wrong every time. The 58% was measuring where the winner happened to sit as much as it was measuring the agent
- **Coverage separates the verdicts perfectly on the held-out market.** Opened 4 listings: 9 runs, 0 correct. Opened 12 to 15: 3 runs, 3 correct. Four is what `browser_probe_cards` returns in a 1200 x 701 viewport. The same table on Rivenhall reads 4, 4, 14 and 15 six times for correct answers against 4 for every wrong one, which is why coverage gating was left open there. Here it is unambiguous
- **Exhaustive retrieval is not a ceiling.** 8 of 8 on Rivenhall, 10 of 12 here. One run opened all fifteen listings and answered "Oakfield Pantry at $5.75", which is that seller's advertised from-price and not its price for the pack asked about: an attribution error rather than a coverage one, and the gate cannot catch it because $5.75 is genuinely on the page. One run hit the 100-step limit at 99 calls and $1.008, the most expensive run on record, with 18 clicks and 10 `browser_select_option` calls in its trace. It was doing the right thing and ran out of budget
- **The gate transfers worse than the policy does.** Wrong answers withdrawn by the frozen rules: small 5 of 7, Rivenhall 11 of 15, **Calderwood 3 of 9**, with no correct answer withheld here. The six misses are one shape, a market-wide superlative asserted after opening 4 listings of 15. The rule that would catch them is that a superlative over a population requires the enumeration to cover that population. **Not written yet, deliberately:** writing it against these six runs would make Calderwood a development market. It should be stated from the principle and frozen before the next market exists
- **A bug in my own replay, found before it produced a figure.** `replay_gate.py` resolved tasks by id alone, and the held-out market reuses the development market's ids on purpose, so a Calderwood suite would have been scored against Rivenhall's answer key. Now resolved from the `tasks_file` each suite records. The same run also printed one pooled table across three markets, which is the error the draw id exists to prevent; it now prints one table per draw
- Spend: **$9.94 of the $50 faculty credit**, 31 runs. The gate-precision figures now cover 125 unmodified runs on the three current draws, withdrawing 19 of 31 wrong answers and withholding 3 of 94 correct ones, with **0 abstentions** by the unmodified agent across all 125
- **How often the agent actually selects a pack size, counted rather than assumed.** On the fifteen-listing markets, 11 of 122 runs. It reads the surcharge from the option label and adds instead: 48 of 290 stored answers show the arithmetic in the text. Magento also ships every variant price in `jsonConfig.optionPrices`, so inside an opened listing no interaction is strictly required. The listing-level gate, one "from" price per search card, holds on WebArena and Shopee both and is where every measured failure lives. The variant-level gate holds on Shopee only and is now stated as a limitation of the environment rather than a property of the results

### 2026-09-14, later
- **Third unmodified batch on the current Rivenhall draw**, 4 gated tasks x 3 repeats, $2.15 logged: 6 correct, 6 wrong. Over all three batches the unmodified arm is **36 runs, 21 correct, 15 wrong, 58.3%** (batches 58.3%, 66.7%, 50.0%). The per-task pattern is stable across batches: both price questions 18 of 18, per-litre 0 of 9, all-stocked 3 of 9
- **The gate rules are not at the `7771e24` freeze.** Three commits since changed decisions: `refutation_without_evidence` added (`d78e017`), the `QUANTITY` units fix (`f9d15b8`), and click-opened listings counted (`f046675`). The literal frozen code was extracted and checked: it reproduces the recorded 3 of 4 caught, 0 of 11 blocked on batch 2
- **Frozen gate, out of sample:** batch 3 alone, 3 of 6 wrong withdrawn and 1 of 6 correct withheld; batches 2 and 3 together, **6 of 10 wrong withdrawn, 1 of 14 correct withheld**. The current rules make identical decisions on every one of these runs. Batch 3 postdates the last rule change, so it is out of sample for the current rules too; batch 2 is out of sample only for the frozen ones
- Batch 3's control question run separately (`20260914T060640`, 3 runs, $0.07), since the gated batch was limited to four tasks. `scaled-headline` over three batches: **9 of 9 correct, median 2 actions (range 1 to 3)**. Only 6 of 9 runs reached page 2 and saw all 15 listings; 3 answered from page 1's 12, correctly because the lowest advertised price sits on page 1. One failed action in 9 runs
- **Why per-litre is 0 of 9.** Every unmodified run's first read of the results page is `browser_probe_cards`, which openJiuwen's prompt directs agents to call first on listing pages. It defaults to `viewport_only` and, at 1200 x 701, reports `total_candidates: 4, returned: 4`. All nine runs open exactly those four and name the best of them; the true best rate is the sixth card, never opened. The same read explains the price questions (winner is card 2) and all-stocked (the listings lacking the pack are cards 11 to 15). Every arm that enumerates gets per-litre right (exhaustive 2 of 2, targeting v2 3 of 3, held-out 2 of 2), which resolves the update 3 caveat that the 2 per cent margin might be scoring arithmetic precision
- Pages updated to the three-batch figures: unmodified 21 of 36, gate 20 correct, 12 refused, 4 wrong, 107 unmodified runs on current draws with 0 abstentions, median actions at fifteen listings 22 against 7, exhaustive 2.4 times the cost. The right-versus-earned example now uses the two correct cheapest-pack answers at 4 of 15 listings; the per-litre example's one correct answer came from the superseded pilot. Spend $45.48 on the account, 275 run records
- The batch 2 figure alone, 3 of 4, overstated recall. All four escapes across batches 2 and 3 are per-litre answers that opened 4 of 15 listings and did not state their coverage, which is the known ceiling of a rule that reads the agent's own claims. The one correct answer withheld said it checked "all four" listings, having opened 4 of 15

### 2026-09-14
- **RQ2 baseline re-run clean.** 60 runs with the answer notes off the pages, $3.63 logged: **53 correct, 7 wrong, 0 abstentions, 48 of 55 gated (87%)**, against 49 of 55 (89%) with the notes on the page. No leaked fragment in any run's context. The 8 Sep suite stays on disk under its own draw and is no longer quoted
- The task most helped by its note, `tee-all-sizes-stocked`, fell from 5 of 5 to 3 of 5. Magento renders a configurable option only when it has an in-stock child, so size M is absent from the rendered dropdown while still present in the page's JavaScript config with an empty product list. Two runs saw S, L and XL and answered yes. **Gating by absence**, a form not on the list: nothing in the observation marks the gap, and the sufficiency check cannot catch it on this fixture
- **"Under-retrieval predicts failure" does not survive on the small fixture.** Clean buckets: 1 action 2 of 3, 2 to 3 actions 20 of 20, 4 to 6 18 of 20, 7 or more 8 of 12; median actions 4.5 correct against 9 wrong. The failures are three mechanisms at three effort levels. At fifteen listings it holds, 23 against 7, which is the fixture RQ3 depends on
- **A third bug, in the scorer.** Yes/no answers were matched by substring, so "Yes... (no pagination)" scored as a No and "not offered" as a No. A leading yes or no now decides, otherwise whole words. Across the 188 answers already on disk one changed, and its stored verdict was already a refusal; in the new suite two "Yes" answers moved from correct to wrong. The Calderwood refusal therefore caught a wrong answer, not a correct one
- **Confidence baseline re-checked with the fixed listing counter: AUROC 0.528 unchanged**, as are overconfidence (0.98 against 0.60), the threshold sweep, the head-to-head and the reason-fed gate (6 of 6 caught, 2 of 9 flagged). The correlation between listings opened and stated confidence moved from -0.535 to -0.338; it was never quoted
- **The coverage-gating rejection was built on the undercount.** Over the two comparison tasks on the current draw, correct answers opened 4, 15, 15, 15, 15 and 15 listings and wrong ones 4 every time. A floor at 11 catches all six failures and blocks one correct answer, itself reached after opening 4 of 15. Reopened as a design question rather than adopted, since refutation needs one counterexample, not eleven openings
- **Gate precision is no longer 1.00.** Over the 95 unmodified runs on current draws it withdraws 13 of 16 wrong answers and withholds **2 of 79 correct** ones, both correct yes/no answers mentioning "XL +$2.00", which `delta_as_absolute` reads as a price. Not patched: the rule set is frozen for held-out measurement. Where the gate ran live, 3 of 27 correct answers were refused, all for claiming coverage of 4 or 7 listings of 15
- Stale figures corrected in `docs/index.html`, `docs/progress.html`, both `updates/` documents and `notes/cost-axis.md`. Dated timeline entries are left as they were written, and a 13 to 14 Sep entry records the corrections
- Spend: $43.08 on the account, 263 run records, $37.30 logged. The clean baseline logged 9% under its account span
- **Open, not started:** `delta_as_absolute` fires on a surcharge quoted inside a yes/no answer. **Open, not started:** whether the sufficiency check can be given a listed set for option menus, so gating by absence becomes checkable

### 2026-09-13
- **The small fixture's product pages carried the answer key.** `env/seed_variants.py` wrote each family's authoring `note` into the Magento `description`, which renders in the Details section inside the accessibility snapshot the agent reads. Unlike the `spConfig` leak, this one was in the observation channel. On `igr-water-b` it read "Ground truth for 'cheapest 2 x 9.5L': this seller, 22.50 against 24.90"; on `igr-tee-a`, "M is NOT available"; the coffee and water-a notes described their traps
- **How far it reached:** a note fragment was in context in **59 of the 60** runs of the RQ2 baseline (`20260908T223116`), and the model's own text cites it in **26**. Every figure from that suite, including the 89% on the small fixture and the 5 of 5 on the two-listing comparison, was measured with the answer on the page
- **What it does not affect:** the 30 scaled listings. Their descriptions read only "Generated listing NN, seller X", and a scan of all 30 pages found no answer text. Rivenhall, Calderwood, the exhaustive arm and every targeting result are clean
- Fixed: descriptions blanked in both store scopes with a new `seed_variants.py strip-notes`, and the seeder no longer sends notes to Magento; they stay in the fixture JSON. Verified by rescanning all four pages for five fragments, zero hits, with children, prices, stock, visibility and categories byte-identical before and after
- Two-listing comparison re-run clean, 5 runs: **5 of 5 correct, 5.6 actions (5, 5, 8, 5, 5), $0.332**, no leaked fragment in any run's context, and every run read both rendered prices. The earlier 5 of 5 is superseded as evidence; the finding that two listings is cheap enough to check exhaustively stands on the clean runs
- **A second bug in my own checker.** `listings_opened` counted only `page.goto`, so a listing opened by clicking its card counted as never opened. 35 runs across 9 suites were undercounted, and one correct "No" was refused for having opened nothing after opening three. Now counts the landing URL as well. The four suites where the gate ran live were rescored through the corrected checker, with the previous verdicts and the reason recorded in `rescored`: Calderwood **7 correct, 1 refused, 0 wrong** (was 5/3/0), targeting+gate v2 11/1/0 (was 10/2/0), targeting+gate v1 3/6/3 (was 3/7/2), v3 unchanged. The retry arm cannot be rescored, since its second runs were triggered by the old count
- **A sixth pooling error, and a seventh.** `arms.py` grouped suites by condition only, so four runs from the Rivenhall draw replaced at 02:02 on 9 Sep sat in the unmodified baseline, and one of them inside the gate's replay. `headline.py` excluded only policy and confidence suites, so its "15 listings, 68%" counted the exhaustive arm and targeting v1 as the unmodified agent. Every suite now records a content-addressed `draw`; older suites were assigned one by `experiments/backfill_draw.py` with the basis written alongside, and no script adds populations across draws
- Corrected figures on the current Rivenhall draw: **unmodified 24 runs, 15 correct, 9 wrong, 62.5%**, $0.267 and 17.6 actions per run. Gate replayed over the same 24: **15 correct, 8 refused, 1 wrong**, no correct answer withdrawn. The superseded draw's 4 runs are reported on their own line
- Spend: account $38.75 before today's run, $39.08 after. 203 run records, $33.67 logged. The per-run figures remain a lower bound, as recorded on 9 Sep; today's five runs happened to settle within the poll window
- **Open, not started:** drawing `TARGET_OPTION` per market. Needs its own random generator or seeds 7 and 41 stop reproducing Rivenhall and Calderwood, and markets drawn that way cannot be pooled with any existing run. Measured beforehand: a smaller target makes the published bound stronger, and at the 12 x 550ml the trap disappears
- **Open, not started:** `generate_catalogue.py:319` tells the user to run `--diagnose`, which `main()` never defines. The 20,000-draw sweep in [docs/rejection_sampling_answers.md](docs/rejection_sampling_answers.md) is the obvious body for it

### 2026-09-10
- **Both halves of RQ3 built.** Targeting plus the gate matches exhaustive retrieval on accuracy at 18.4 actions against 28.4 and $0.382 against $0.568, with **no wrong answers in 12 runs**. That is the claim the research question was written to make. See [notes/targeting.md](notes/targeting.md)
- Exhaustive upper bound measured, 8 of 8 correct at $4.54, which established the cost axis and settled that the failure is a retrieval problem rather than a reasoning one: the model gets the per-litre question right when made to look, having been wrong in every other arm. See [notes/cost-axis.md](notes/cost-axis.md)
- **A result was published and withdrawn the same day.** Targeting v1 was reported as the efficiency claim met, 4 of 4 at 7.2 actions. It never enumerated the candidate set, read the first four listings as the whole market, and was right because the winner happens to sit inside those four. Seven actions against thirty-one was not a saving from pruning, it was a saving from not looking. The sufficiency check caught this and I did not, which is the project's own thesis applied to its author
- Verbalised confidence measured and it fails: AUROC 0.528, stated 0.98 against accuracy 0.60, and no threshold separates a task at 100% accuracy from one at 0%. Asked why, the agent states its own thin coverage plainly and rates itself 95 regardless. See [notes/confidence-baseline.md](notes/confidence-baseline.md)
- Literature cut from a survey to five works read properly. Kadavath is the one that matters: their P(IK) rises with relevant material in context, and on a gated page the relevant material *is* in context, so their result does not transfer to an agent that chooses its own context. See [notes/related-work.md](notes/related-work.md)
- **Held-out test done the same day.** A second market generated with a different seed and brand, seeded alongside the first so no recorded run lost its ground truth. Different winner, different trap, different per-litre answer. **7 correct, 1 refused, 0 wrong.** Across both markets, sixteen of sixteen answers are correct or refused. See [notes/heldout.md](notes/heldout.md)
- **No saving is claimed on the held-out market.** There is no exhaustive arm there, so 15.1 actions has nothing to be divided by. That run is the first call on the new credit
- A result was published and withdrawn the same day. Targeting v1 read the first four listings as the whole market and was right because the winner sits inside them. The sufficiency check caught it and I did not
- Two of the held-out run's three refusals were a bug in my own checker, which read "8.4 litres" as an unsupported $8.40. A quantity mistaken for money, the same family as the delta misread that started the project
- Spend $18.63 of the original $20 plus $21 self-funded, roughly 190 browser runs. Further credit approved by the supervisor

### 2026-09-09, later
- Verbalised-confidence baseline measured and it fails. 15 runs, $2.78. The task the agent never gets right scores 100, the task it always gets right scores 95. AUROC 0.528 against 0.5 for no signal, stated confidence 0.98 against accuracy 0.60. No threshold separates them, and the sufficiency check stops the same failures while discarding none of the correct answers. See [notes/confidence-baseline.md](notes/confidence-baseline.md)
- Asked why, the agent says "I verified all 4 sellers" where there are fifteen, and rates itself 95. So the information needed to abstain is already in its own output and the number ignores it. Feeding that justification into the check doubles recall, 3 of 6 to 6 of 6, in sample
- Retry now quotes the agent's own justification back to it rather than reporting an external verdict, and an `investigate` arm asks it to diagnose its own error and retrieve only what settles it, rather than redoing the task
- Headline figures are now computed by `experiments/headline.py` rather than written by hand, after two documents carried different percentages for what read as the same claim. **89% on the 4-listing fixture, 64% at 15 listings, 81% pooled over 85 gated runs.** A rate without its fixture and denominator is not quotable; the gap between the two is the scale finding
- Live price instability scoped out as a limitation. A TikTok Shop listing priced the same option at S$188.30 and S$205.55 on consecutive loads. Not the project's to fix, but it makes the self-hosted environment necessary rather than merely convenient. See [notes/live-price-instability.md](notes/live-price-instability.md)
- Literature positioning written against selective prediction, calibration, self-verification, adaptive retrieval, attribution and unanswerable QA, plus the project's lineage from injection work in the same WebArena shop. See [notes/related-work.md](notes/related-work.md)
- **Open and named: there is no exhaustive arm, so there is no upper bound on cost and no efficiency claim can be made in either direction yet**

### 2026-09-09
- RQ3 first slice: a sufficiency check that decides whether an answer is supported by what the run observed, applied as a policy in two arms. `gate` abstains, `retry` re-asks with the reason. See [notes/rq3-policy-arms.md](notes/rq3-policy-arms.md)
- The gate issues no browser action, so it replays exactly over runs already recorded and costs nothing. Over 78 earlier baseline runs it withdrew 12 of 12 wrong answers and lost none of 66 correct ones
- Retry arm, 15 runs, $4.21 against the baseline's $3.13: wrong answers fell from 5 to 2. All three `scaled-all-stocked` runs answered a bare "Yes" after opening 4 of 15, were flagged, and all three second attempts returned the correct answer with its evidence
- That arm broke the check twice. It blocked a correct answer whose price was a base plus a surcharge and so never printed on the page, and it was blind to an answer that combines real figures over the wrong set. Both fixed, so both figures were in sample
- Rules frozen at `7771e24`, fresh baseline run, $3.41, replayed under them alone: **3 of 4 failures caught, 0 of 11 correct answers blocked, $0.00 added cost**. Out of sample
- Gating on retrieval coverage was tested and rejected again. Correct answers to the comparison tasks opened 1, 4, 4, 8, 12, 13, 14 and 14 listings; wrong ones opened 4 every time. A floor at 11 catches all six failures and blocks three correct answers
- `scaled-best-per-litre` opens exactly 4 listings in all seven runs, right and wrong alike, so its one correct answer rests on the same evidence as its six wrong ones. Correctness and soundness are separate properties and the report carries both
- Spend to date **$18.63**, 120 browser runs, topped up by a further $15 so the remaining arms are funded. Cost is measured two ways and they disagree. The sum of per-run deltas is $15.94; OpenRouter's own usage for the key is $18.63. The key figure is authoritative and the per-run figures are a lower bound: exploratory runs made before cost capture worked are absent, and a run's delta is read as soon as spend moves rather than once it has fully settled.

### 2026-09-08, later
- openJiuwen runs end to end against the seeded environment. `experiments/` now holds a task suite, a scorer, an interaction counter and a suite driver
- RQ2 baseline measured: 60 runs, $2.98, `claude-haiku-4.5`. 87% correct on gated tasks, **0 abstentions in 60 runs**, and correctness collapses to 20% when the agent spends only one action. See [notes/rq2-baseline.md](notes/rq2-baseline.md)
- Two upstream openJiuwen bugs found and patched locally: an empty probe result reported as a JSON parse error, and the worker's `ok: false` not reaching the runtime result. Apache 2.0, candidates for a pull request
- Cheap models could not complete the tasks. `gemini-2.5-flash-lite` fails openJiuwen's structured output contract; `deepseek-chat` and `qwen3.7-flash` were rate-limited at their providers regardless of account credit. The cheap-tier assumption in the proposal does not hold
