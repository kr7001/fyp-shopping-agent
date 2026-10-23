# Shopping agents under interaction-gated information

FYP, NUS Data Science and Analytics, Aug to Nov 2026.
Student: Kayleen Lee Kai Rong. Supervisor: Prof. Markus Kirchberg.

**Start with the project site, [`docs/index.html`](docs/index.html).** Open it in a browser. It
holds the objective, every verified result with the test behind it, every experiment, the
markets, the problems solved and open, a week by week record, the plan to the final
presentation, and the commands to check any figure yourself. Its computed figures are generated
from the run files by `make site`, never typed. The few it quotes from this log carry their date.

| File | What it holds |
| --- | --- |
| [OBJECTIVE.md](OBJECTIVE.md) | The north star and the current milestone |
| [WORKFLOW.md](WORKFLOW.md) | How the work is done: five modules, one job each, and the spend guard |
| [LESSONS.md](LESSONS.md) | Every mistake that cost time, money or a wrong claim, and the rule it produced |
| [PARKED.md](PARKED.md) | Side ideas saved instead of pursued |
| [experiments/README.md](experiments/README.md) | The code, folder by folder, and which scripts cost money |
| [env/README.md](env/README.md) | The shop: generators, the seeder, the gated theme |
| [agent/README.md](agent/README.md) | openJiuwen, pinned, and the one local patch to it |

A check that everything works, all of it free:

```bash
make check     # unit tests, the planner regression, the mod's tests
make facts     # every clothing-cell figure on the results page, from the raw runs
```

Below are the environment setup and the decision log, the dated record of what was
considered and why.

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
| Thornwood, clothing | 15 | **Development since 8 Oct 2026.** Generated on 18 Sep, after the coverage rule was frozen. Cells 1, 2, 3 and 5 were measured on it on 7 and 8 Oct, and strategy v7 and planner v2 were then written from its failures. Box v1's pilot and box v2's three development batches ran on it on 14 Oct, and box v7 to v9 were written from those batches' failures on 20 Oct | Reporting cells 1, 2, 3 and 5, the pilot and the development cell, all in sample for the box. Not a held-out test for anything the box does |
| Calderwood-S | 15 | **Measured 18 Sep 2026** as `Calderwood-gated`, Calderwood's prices with the variant prices suppressed. Its first batch went through a store view, measured two shops at once and is superseded | Reporting the 18 Sep result: hiding the prices changed what the agent did, not whether it was right |
| Fresh clothing market | 15 | **Reserved.** To be generated with a new seed now that box v9 is frozen for it (20 Oct 2026). Four sizes, or the menu reader's excerpt rule is extended first | The held-out test for the box, the claim: shipped, open everything and box v9, three repeats, per question |
| Larchmere, tees and water | 42 | **Development since 22 Oct 2026.** Drawn by the A+ generator with seed 900, prefix IGR-DEV (`env/README.md`): 21 tees and 21 waters over two results pages, the second claim's market shape. The front door's pilot ran on it on 23 Oct | Development only: costs, step and clock limits, and the front door's development. No claim is made on it, and it is not a held-out test for anything |

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

## How this project was built

Kayleen Lee Kai Rong designed the research, made every decision and reviewed every result.
Claude Code (Anthropic), used with Claude Opus and Claude Fable models, wrote most of the code
under the student's direction, ran the independent verification passes, and drafted the
documentation, this README included. The decision log below records what was decided, when and
why. Until 21 October 2026 commits named Claude as a co-author. At the student's request those
lines were taken out of the history, and the credit moved here.

---

## Decision log

Entries before 9 October 2026 name scripts by their old paths, from before the code moved into
folders. [experiments/README.md](experiments/README.md) maps each old path to its new one, and
the pages they mention are in [docs/archive/](docs/archive/).

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

### 2026-10-23
- **A pilot of the front door before the big run, and one more check of the big run's fairness and clarity, both at the student's request.** The pilot was to cost under $8 and run by itself. It ran on Larchmere, the development market of 21 tees and 21 waters over two results pages, the shape of the second claim's market. So every figure below is in sample, development evidence only and never a claim (LESSONS 19). One agent model ran, DeepSeek V4 Flash, once per question
- **The spend guard cannot pre-approve a run, and it was not weakened.** A notification went out at 11:16, and the guard's dialog was answered "Run it" at about 11:20
- **The verifier refused the pilot's version 1 twice, then once more on a cost estimate, before its pass at 11:14 on `782853d`.** Blocker 1: under `--reading menu` the scripted user told pv1-15 ("How many Larchmere listings can sell me a size M today?") the opposite of its own question. The fix is `--reading own`, where the scripted user answers with the reading the question's key was written under (`782853d`). Blocker 2: the $8 cap was checked only between invocations. Now each invocation runs only if the spend so far plus its high estimate stays under $8, and the chain does not start when the account cannot be read. The third refusal: the Haiku box invocation's high estimate was too low, and was raised from $0.60 to $0.95, for an estimate of $6.94. Form v13 went in with the fixes: `parse_reply` handles a reply that is not a string, and reasoning that contains braces
- **The pilot ran from 11:20:25 to 13:25:13 at `782853d` and spent $7.2632**: agent $7.0817, parse $0.0110 and probes $0.1705. That equals the account's movement, from 94.7522 to 102.0154. The chain stopped itself before DeepSeek's open everything, because the spend so far plus that invocation's $1.80 high would have reached $8. So open everything, Haiku and shipped did not run, and the pilot measured neither baseline. The chain's own record is `experiments/results/pilot-20261023.manifest`, with `pilot-20261023.done` and `pilot-20261023.watchdog` beside it
- **A watchdog was added at 11:58, after the first runs showed costs far above their estimates.** It is a script in the session's scratchpad, not in the repository, and only its record is committed. It would stop any run that would pass $8. It stopped none
- **The reading test: on the 24 v1 rewordings that keep their template's meaning, every field right for DeepSeek on 22, Haiku on 21 and the rules on 10.** Haiku with prompt v1 had 2 on 20 October. Today's probes ran under prompt v3 and form v13. By tier (the quantifier, with the objective, with the population, every field): DeepSeek 22/22/22/22, Haiku 22/22/22/21, the rules 17/14/14/10, and Haiku on 20 October 21/16/8/2. Neither model asked back on any of the 7 rewordings labelled clear. A reading cost DeepSeek about $0.0004 and Haiku about $0.005. These are in-sample development figures, because the prompt was written from these rewordings. `python3 experiments/analysis/paraphrase_scores.py experiments/results/parse-probe-paraphrases_v1-20261023T112717.json` prints DeepSeek's tiers and charge, and the same command on `parse-probe-paraphrases_v1-20261023T112838.json` and `parse-probe-paraphrases_v1-20261020T223344.json` prints Haiku's, today and on 20 October. The asks on clear rewordings are counted from each row's `model_box` in the same files, which no script prints yet
- **The block with the model parser, DeepSeek, 27 slots** (`experiments/results/20261023T112840`). Read in full, 24 of 24 agent runs are correct: the 13 keyed templates and 11 of the 12 rewordings. The 12th, pv1-01 ("which Larchmere tee has the lowest listed price"), was refused. The rules' word list read "listed" as availability listed, overruled the model's correct form, and the box fell back to the rules' form. The two questions the box should not plan, on delivery and on taste, were refused. The stored verdicts give 23 correct and 1 "abstained", which is a scorer misread. $4.7352
- **The block with the rules, DeepSeek, on the same 12 rewordings** (`experiments/results/20261023T124833`): 7 correct, 3 wrong, 2 refused, $2.3574. The model parser was right and the rules wrong on 4, never the reverse. Sign test p = 0.125, one run each, so suggestive only. This compares the block's two front doors with each other, on one market and one model. It says nothing yet against openJiuwen as shipped or told to open everything
- **Every scorer misread falls against the block.** Score v8 misreads 4 correct answers through the lists of opened and skipped listings that the block asks its agent to write: tee-top-3, pv1-19 and pv1-06 under the model parser, and pv1-20 under the rules. The v1 abstention rule misreads water-cheapest-target, where "unable to" sits in a clause rejecting listings. All five lean against the block. `make verify BATCH=experiments/results/20261023T112840`, and the same for `20261023T124833`, re-derive each batch at `93b8413` and print every answer. The four v8 misreads are its "stored verdict correct, re-scored wrong" lines, and `python3 experiments/analysis/voids.py --all` on the two batches shows the abstention. The same problem list also names three rewordings with no floor rule (pv1-03, pv1-06, pv1-19) and two that name no product (pv1-12, pv1-13). For those two the box's scope record says "the question names none of the products the titles name (water, tee), so every listing is planned over", and their runs opened water listings as well as tees
- **DeepSeek's serving providers, from the run logs.** Relace served 750 calls for $4.36, 2.46 times list price (fp4, no cache discount). Parasail 195 calls, $1.91, 3.36 times. GMICloud 410 calls, $0.50, 1.00 times. StreamLake 147 calls, $0.31, 0.77 times. Overall 2.16 times list, against 1.02 times on Ashcombe, the first claim's market. The 6.6-fold rise in cost per block run over Ashcombe splits into about 3.1 times the tokens, from the two pages, and 2.1 times the price. The call counts are `claim.serving_providers` over each run's log. The costs and ratios are the verifier's, from the raw files, and no committed script prints them yet. The logs stay on this laptop, as before
- **The runs were clean.** No voids, and the longest silence in a log was 26 s. No run sorted the results or changed the page size, and none read a hidden price. The longest run took 110 tool calls and 493 s, against limits of 300 and 1800. `python3 experiments/analysis/voids.py --all`, `toolbar.py`, which prints a run only when it sorted or resized, and `leaks.py`, each on both batches. The calls and seconds are each row's `tool_calls` and `elapsed_s` in the batches' `suite.json`. The longest silence is the verifier's figure
- **The fairness re-audits of the big run.** The first found 16 items, the second R1 to R11. The fixes landed on the scorer branch: score v7 then v8, `toolbar.py`, `claim.py` v2 to v4 (closed slots, the H4 splits, Holm per model, failure codes, `require`, the provider tables, and the blind hand-reading sheet with its read-back), and `generate_aplus` v3 (the claim titles "Midweight Jersey Tee" and its variants, and `top_3_margin`). They were merged into dev as `93b8413`, where `make check` gives 779 OK. `docs/content/claim2-protocol.md` is rewritten as version 2 from the re-audits and the pilot, and stays a draft until the student's decisions
- **Considered and not done.** Circumventing the guard. Dropping the rules arm to make room for open everything, since the rules arm is the front-door comparison the student asked for. OpenRouter's `:floor` routing, which ranks providers by the advertised input price and would favour Relace
- **Open for the student tonight: the 11 decisions in Part E of `docs/update-23-oct.html`**, the student's page for today, committed as written. Insights, this entry: four lessons, 41 to 44, and a market ledger row for Larchmere. The site is not rebuilt in this change, because `make site` would write over `docs/site-data.js`, which holds the student's uncommitted edits. So the site is stale, and `make site-check` will say so

### 2026-10-21
- **The Claude co-author lines were taken out of the history at the student's request.** 219 of the 225 commit messages carried one, and none does now. The rewrite was force-pushed to GitHub with leases pinned to the old tips: the old tip of `dev`, `bddd6e1`, is now `21e808d`, and the old tip of `main`, `ee0a7eb`, is now `8cad71a`. Claude's part is credited under "How this project was built"
- **223 of the 225 commit ids changed.** The first two commits carried no line and kept theirs. Trees, authors, committers and dates are unchanged, and parents map to the old ones. This was checked pair by pair against a mirror of the old history, kept outside the repository and never pushed. `git filter-repo` also mapped the commit ids quoted inside 15 commit messages. The steps and both scripts are in `docs/guides/git-coauthor-cleanup.md`
- **Old ids map to new in `docs/archive/commit-map-2026-10-21.txt`.** An id from before 10 October goes through `docs/archive/commit-map.txt` first, then this map. Ids quoted in this log, the notes, the guides, `PARKED.md`, `docs/content/` and the code comments (`090dc54`) now name the rewritten commits. The two local tags moved through the map
- **Some files are left as written: the run records in `experiments/results/`, the archived pages, the verifier's stamps, and the claim protocol.** The protocol's pre-registered text stays byte-identical, so it still quotes `ea17804` and `c09bd87`, now `9cf54a5` and `51f3b0f`. A paid run from now on needs a fresh verifier stamp. `backup/before-rewrite`, the local branch from 10 October, is untouched and has never been pushed
- **`docs/site-data.js` is not rebuilt in this change.** It was last rebuilt on 20 October at 12:01, and later commits left it stale in five keys: clothing, code, experiments, patterns and tests. The ids replaced today make five more stale: open, report, today and v2 from `docs/content/`, and parked from `PARKED.md`. The next `make site`, checked by the verifier, brings the new ids with it

### 2026-10-20
- **The verifier passed the three batches of 14 October and every code commit since.** Its six findings on the batches are box v7, `82fe453`: a bare "No" to "does every listing offer size M" is supported when the log shows an opened listing whose observed size menu lacks the size, whether or not the answer names it (five correct bare "No" runs had been refused for naming nothing). A superlative or comparative on an attribute the shop does not show is refused whatever the word, so "the softest tee" no longer reaches the survey fallback that opened all 15 listings for $0.80. A keyless run that did not finish is unscored rather than failed, which moves one stored verdict, apparel-softest-1 of batch 20261014T220116, and no other. Two written kinds of error, a listing judged by `browser_find("disabled")` alone and the seller faults read for every ranked seller. The listing counter's fourth correction (LESSONS 2), which counted the category page `electronics.html` as a listing in `20261014T213118/apparel-all-stocked-2` and now counts by membership of the page's own listings, moving that one count from 2 to 1. And `compare_cells.DEVELOPMENT`, the three batches as one in-sample cell printed after the four cells. The gated browser also runs with `--block-service-workers`, recorded as `browser_flags`. The three batches ran without it, and the bypassed poem run's `data:` page is noted as no breach, since `--allowed-origins` confines network requests only
- **Then the verifier failed the new menu reader twice, and both failures are rules now.** First, `9491c53`: `sufficiency.size_menus` had taken a `browser_find` excerpt, the matched line and three more with no gap marker, for the whole size menu, so a size cut off the excerpt counted as absent: `20261014T213118/apparel-count-stocked-2` read igr-app-08 as S, M where the menu is S, M, L, XL. Each reading now says whether it is complete, a reply that carries the page URL shows the whole page and so does an option block followed by another line of the page's tree, and absence counts only from a complete reading. Second, `921efce`: a snapshot taken with a depth prints a node beyond it as a leaf with no children and no mark, and `20260910T133605/scaled-cheapest-target-1` prints the combobox with no colon and no option lines in a reply that carries the page URL, which the rule took for a complete menu with no sizes. A combobox head line without a trailing colon now gives no reading at all, checked on every stored snapshot line: 5,574 combobox heads in every stored tool reply: 3,646 with a colon, every one followed by a child line, 1,924 without a colon, none with a child, and 4 with a colon and no child at the end of a find window, which give no reading (the census is in experiments/box/sufficiency.py). The closing round, `4b6fda4`: a find block whose first option line is not the placeholder may have lost options before its window, so it is partial at the front and shows presence only, with one such stored block (`20261014T220116/apparel-cheapest-xl-1`, igr-app-08) and no figure moved. The reader is validated against the fixture over every stored run of the three batches, `python3 experiments/analysis/replay_box.py experiments/results/20261014T213118 experiments/results/20261014T220116 experiments/results/20261014T222007 --menus`: 180 readings, 109 complete and all equal to the fixture's menu, 71 partial and all a prefix of it. The box's check replayed over the same runs: wrong refused 0 of 3, not wrong refused 1 of 29, `20261014T222007/apparel-all-stocked-1`, whose only view of its counterexample's menu was a cut excerpt
- **The box's own reading.** "best price" and "best deal" parse as the cheapest, "top" does not (form v8, since "top price" can mean the highest). A question whose shape compares a price and whose verb is ambiguous takes the "can sell now" reading without asking, because the gated page never prints a sold-out size's price, writes it into the text the agent gets, records `reading_by: box`, and is scored under that reading's key. A question answerable under both readings still asks. Written on the design page before being coded. Of the 58 task-file questions no form changed and the dry runs are byte for byte the same below the header
- **The patch digest is reproducible.** `agent_core_patch` is the sha1 of `git diff --full-index`, so it no longer depends on the machine's abbreviation setting, and `agent/openjiuwen-local.patch` is regenerated with the same flag so the file's sha1 is the figure a batch records. The four October batches recorded the abbreviated form, `ae20d543...`, for the same content
- **One row re-scored.** `rescore.py` now writes the scorer version into the batch. Applied once, to `20261014T220116`, with the reason recorded in its `suite.json`: `apparel-softest-1` failed to unscored, previous verdict kept beside the new, scorer v2 to v3. `make verify BATCH=experiments/results/20261014T220116` lists it among the three unscored runs and finds no problem. `20261014T222007` was not re-scored, since it is scored under the buyable sidecar
- Also fixed: `test_probe`'s failed-call test shared one folder across four subtests, and the census comment in `sufficiency.py` names its sources. `make check` green twice at `4b6fda4`, 254 tests, planner regression 37 questions 0 failures, mod 21 pass, and `make facts` sections A to G byte for byte the baseline throughout. The design page's last change, `0db2fe9`, says the box takes a reading only where the shape compares a price, not on a survey
- **Insights, this entry.** Six lessons added, 33 to 38. The site's Results page gains the development cell, in sample and never pinned as a claim, with its per-question table, its tests against cells 1 and 5, the ten new questions' outcomes, the check replay, the cost cross-check and every answer in full, all from `docs/build_site.py` (`make site`). The Report and Today pages' blank tables are filled from `make facts` section H and `make verify` on each batch. The Problems and Plan pages say what is next: the fresh market after the freeze, the claim run, then the review questions, the top-k limit and the second agent's confinement. Nothing was spent today
- The verifier's stamps in `.verification/` cover paid commands only, so the pass on the batches' outputs and on `82fe453` to `0db2fe9` is recorded in those commits' messages and here, not in a stamp

### 2026-10-14, evening
- **Box v2's development batches ran, 21:31 to 22:28, $6.9638 charged against $11 declared.** Three commands at `146c582`, box v6, form v4, primitives v3, scorer v2, the verifier's stamp of 21:30, the student's yes in the guard's dialog, under `caffeinate -i`: the six clothing questions three times under `--reading menu`, 18 runs, declared $6, charged $4.0702 (`20261014T213118`). The ten new questions once, 10 rows of which 8 reached the agent, declared $3, charged $2.1899 (`20261014T220116`). The two "offer" questions three times under `--reading buyable`, 6 runs, declared $2, charged $0.7037 (`20261014T222007`). Each re-derived with `make verify BATCH=experiments/results/<batch>`: every answer read in full, no silence over 60 seconds, listing counts from the log, cost re-summed from the provider's charge per call, no problem found. The account reading stored with the runs moved from $57.2861 before the first to $64.1931 at the last, $6.9071, the last reading taken before that run's own charge settled. A live reading on 20 October gives $64.2499, so the account moved $6.9638, the charges to the cent, and $35.75 of the $100 remains. Policy off, so every raw answer stands and the check is replayed afterwards. Thornwood, in sample, no claim (LESSONS 19)
- **What it showed, on the five questions cells 1 and 5 asked** (`make facts`, section H): 13 of 15 correct, 14 of 15 opened what the answer needs, a median of 8 listings opened, 29 tool calls and $0.258 a run, the control 3 of 3. Cell 1 on the same questions 4, 3 and $0.176, cell 5 11, 15 and $0.524. By question, two sided exact: against cell 1 p = 0.00155 correct and 0.00034 opened, against cell 5 p = 0.63 and 1.0. Per question, correct and opened of 3: target-price 3 and 3 (8 opened each time), cheapest-target 2 and 2 (6, 8, 8), all-stocked 3 and 3 (1), count-stocked 3 and 3 (15), count-buyable 2 and 3 (15). The box asked on the two "offer" questions in all 12 of their slots, and under the buyable reading they were 6 of 6 against that key
- **The ten new questions, one run each.** Exists under $27 (yes, Alderney), exists under $25 (no), the named pair and cheapest XL correct, opening 8, 7, 2 and 3 listings. Top-3 wrong, 12 opened: Alderney first, then Oakhurst and Lymington at their advertised prices, two sellers that cannot sell M. "Delivers fastest" refused and "a cheap tee" asked back for a figure, $0 each. "The softest tee" fell to the survey fallback, opened all 15, 95 calls and $0.796, and gave no answer. It was scored failed then, and unscored since the 20 October re-score. The two bypassed questions cost $0.013 and $0.009: the capital run's six navigations to google, bing and wikipedia were blocked with `net::ERR_BLOCKED_BY_CLIENT` and it answered from the model, and the poem run wrote its poem into a `data:` page of its own composition, which makes no network request
- **The three wrong runs, by the written rules** (`make facts`, section H): `cheapest-target-1` did not open what the answer needs and read the price before the page revealed it, naming Copperfield at its advertised $23.40 after 6 of the 8 listings its bound required. `count-buyable-2` tested for the word "disabled" on 12 of 15 listings and never read the menu, so an absent size counted as available and it said 10 where 5 is right. `top-3-1` named sellers that cannot sell M. The box's check, replayed from the logs with `replay_box.py`, refuses 0 of the 3 and 1 of the 29 others, and the advertised-price misread is invisible to any page-only check
- **The design decisions taken from it**, written on the design page on 20 October before being coded: a bare "No" is supported by a complete observed menu that lacks the size, whether or not the answer names the listing. An attribute the shop does not show is refused whatever the word, so no fallback plan can spend on it. And the box takes the "can sell now" reading without asking when the shape compares a price, because the menu reading has no price on the gated page
- Spend: $57.29 used before the batches, $64.19 by the last stored reading, which lags the final charge

### 2026-10-14
- **Box v1 specified and built, overnight before the week 1 meeting.** The spec, `docs/content/box-v1-spec.md`, makes eight decisions and gives the free test each rests on. The build is commit `867851f`, with `8adeece` the same night tightening the ambiguity rule: `experiments/box/page.py` fetches and parses the results page, `ambiguity.py` decides whether to ask the user back, `box.py` renders the exact text the agent receives, `policy.gate_from_page` runs the refusal check from the page's numbers, and `suite.py` gains `--box`, `--reading` and a dry run that prints the text. 90 unit tests. The frozen strategy text is unchanged, checked by a byte comparison, so strategies stay at v7 and the planner at v2
- **What the free tests settled.** The results page fetched over HTTP with the agent's user agent shows the same 15 sellers at the same advertised prices in the same order as the agent's own whole-page card probe (`20261007T115021/apparel-target-price-1.log`). The refusal check with the market size and floor taken from the page, replayed over cells 1, 2 and 5, refuses 8 of the 9 answers that did not open what they needed and none of the 26 correct ones, against 9 and 0 with the answer key's numbers. The miss, cell 1 cheapest-target-3, opened every listing its bound required and misread Copperfield's advertised $23.40 as its size-M price, which no page-only check can see. The ambiguity rule asks on the two "offer" clothing questions and on none of the four clear ones. Across the 45 openJiuwen runs on this market each listing opened costs about 3.6 tool calls and $0.035, so a plan that stops at 8 listings should cost about $0.25 a run against cell 5's $0.52
- **The rule's first version was wrong, and the build's own report said so.** Fired on "which seller offers the lowest price per litre", where "offers" is about price, not availability, 6 of 37 questions instead of 4. Tightened so the verb must govern the variant phrase. A false ask on a clear question is the control the spec defines, so it is tested on every question in the project
- The browser tool is pinned at `@playwright/mcp@0.0.83`, the version every clothing cell used and still npm's latest, and recorded in each batch. `--dry-run` now prints the exact text the agent receives, through the same function the paid loop uses, which closes the gap behind lesson 17
- **Not done this week:** the raw logs are still only on this laptop, and `water/arms.py` and `water/headline.py` still pool across models and agents. No paid run of the box exists yet. The proposed runs with their estimates, $13.65 for 26 runs at cell 5's cost a run, are on the site's Today page and wait for a verifier stamp and the student's yes
- **The verifier passed the pilot command at the committed code and stamped it.** It built the held-constant table against cells 1 and 5 and named every intended difference, reproduced the page-based refusal replay (8 of 9, 0 of 26) and the key-based one (9, 0), checked every seller, price and URL in the box's text against the live shop and the fifteen product pages, and spliced the box's text into a real log to show the listing counter does not count the URLs the box lists. Its findings: the agent's local openJiuwen patch was present in every cell but no batch record named it, now recorded in each batch; the pilot's two questions were cell 5's dearer ones, so the estimate is a mean rather than a ceiling; one sentence of the frozen v7 text is strictly false of a sold-out size, left for v8 and listed as an open problem; the rule fires on four of 37 distinct questions, which is five of the 42 entries, since the held-out gated file repeats five questions
- **The pilot ran at 08:43, two runs, both correct, $0.61 against $1.05 declared.** Cheapest buyable M: Alderney at $25.77, opened exactly the 8 listings advertised at or below that price and skipped 7, 40 tool calls, $0.39, where cell 5 opened 15 at about $0.59 a run. How many sell M now: 5, opened all 15, 33 calls, $0.22. Re-derived with `make verify BATCH=experiments/results/20261014T084322`, no silence over 60 seconds, the refusal check from the page passed both. One run each, in sample: a working pipeline, not a result
- **Research before v2, on the site's Research page.** What the shopping benchmarks ask (WebShop, WebMall, DeepShop), what people use assistants for, the 2026 work on adaptive retrieval budgets and on clarification, the product QA literature's answerability problem, and the LLM-Modulo pattern of a model proposing and rules verifying. Nobody builds the pre-browse policy as a separate verifiable step. The box's "offer" case is what DiscoBench calls facet ambiguity, and its scripted user is that benchmark's simulator
- **Box v2 designed, on the site's Box v2 page.** A logical form per question (quantifier, objective, filters, population), parsed by rules and by a model, verified by five properties including "the attribute compared exists on this shop", composed from seven retrieval primitives, asking only when the form is underdetermined on this page. The honest answer to "should the box be an agent": a model parses, rules do everything after
- **The census parse ran, 37 model calls, $0.069.** The model chooses the same quantifier as the rules on 34 of 37 questions and the same quantifier and objective on 33; every field on only 5, from two prompt vocabulary gaps (the URL never put in the filters, "listing" for "results"). Four real disagreements, the rules right on three, and the fifth soundness property refused the model's one invented attribute. Figures from `experiments/results/parse-probe-20261014T112047.json`, in sample for the rules. The verifier passed the command beforehand and named five fixes for v2 before any box batch, all made in `8102c99`: the witness check accepted an answer that names a listing without "yes" even when nothing was opened, the probe's agreement test compared 20 with 20.0 as different, an HTTP error would have lost the probe's cost record, a bound tie on a future market would refuse a run that followed the text, and "which three sellers offer size M cheapest" lost its three
- **Where the v2 build departs from its design, as the coder recorded and the verifier judged.** The eight single-listing questions parse as lookups where v1's classifier said survey, with the text sent unchanged. A listing page on the generated markets shows size, price and availability and no description or rating, so "cheapest with rating at least 4.5" is refused as not answerable there, which is right for those markets and not for a catalogue product with reviews. Existence and top-k questions take the "can sell now" reading silently unless the question uses one of the lexicon's verbs, recorded in the form's evidence. A "does every" answer that names no listing is refused, which would have refused 5 of 14 correct bare "No" answers in the old cells and is kept because the box's own text tells the agent to name the counterexample. The floor for a "cheapest" answer counts the listings advertised strictly below the answered price plus one when a listing is advertised at exactly that price, which equals the old rule on every stored row. A filter only the model states stays a disagreement in the census, so "5 of 37" is every-field agreement and is never quoted as the model's accuracy. The verifier's second pass found four more, fixed in `0376778`: the witness check read "none of the sellers" as an affirmation, the floor's extra one is now for the answer's own listing only, a refused fallback was counted twice, and a bypassed question could have taken the browser off the shop, so openJiuwen on the gated shop now runs with `--allowed-origins http://localhost:7770`, recorded in every batch as a condition cells 1 to 5 ran without (no run of theirs left the shop). Not confined: the second agent, which drives its own browser, so a bypassed question must not run under it until it is. The verifier passed `0376778` in the afternoon, reproducing each fix and finding the denial pattern starts none of the 446 stored answers, so no replay moves. Two items it left for the batches they concern were fixed in `d06ebfc`, 182 tests: an existence question written "under $20" now exempts its own limit, since the plan text writes it as "$20.00" and the check refused the echo, and `--box` with the second agent is refused until that agent's browser is confined to the shop. Noted for the record: the origin flag does not stop a redirect or a service worker, and a scan of every stored log finds only the shop's origin
- **A question the box cannot classify now bypasses it**, at the student's request: no shopping shape and no shopping signal means the agent gets the question unchanged and the batch counts it; a shopping question about an attribute the shop does not show is pushed back with what the shop does show; a shopping question with no recognised quantifier keeps v1's fallback and is counted as such
- Spend: $56.61 of the $100 key used before today, the pilot's $0.61 and the parse's $0.07 on top

### 2026-10-10
- **The history was rewritten so the repository can be published.** 122 of the 133 commits not yet on GitHub were rebuilt, everything from `af7dc77` on, the commit that added the paper and is now `a05ae2e`, and two things changed in them. `openjiuwen.pdf`, which arXiv's licence does not let this repository redistribute, is gone from the 101 that held it. Magento's licence notice is in the gated theme's template in the 60 that lacked it. Checked commit by commit against a copy of the old history: no other file, author, date or message changed, except three messages whose quoted commit ids now name the rebuilt commits, and the final code is identical. The old history stays on a local branch, `backup/before-rewrite`, which is never pushed
- **Old commit ids are mapped to new ones** in `docs/archive/commit-map.txt`. Ids quoted in this log, in the notes and in the code were updated. The archived pages keep the ids they were written with, and so do four run records, the `suite.json` files of `20260910T015857`, `T101847`, `T131504` and `T133605`, whose re-scoring notes quote `f9d15b8`, now `670ed0d`. Run records are left as written
- The tag `rq3-gate-heldout` moved to the rebuilt copy of its commit, `6c218b3`, since it still pointed at the old one, which holds the paper
- **Published by decision.** The supervisor's inline replies in `docs/archive/updates/` go public with the rest, as the student decided, and `main` is brought level with `dev`, a fast-forward that overwrites nothing
- The template's note now says when the notice was added and that it was written into the older commits too

### 2026-10-09
- **The code is in folders by job, and nothing it prints changed.** `experiments/` was 23 scripts and 6 question files in one folder. It is now `box/` (targeting, planner, sufficiency, policy), `runners/` (everything that can spend money), `analysis/` (scoring, checking, the figure scripts), `water/` (the September study), `tasks/` and `tests/`, with every location in `experiments/paths.py`. Before the move 34 free commands were run and their output saved: every figure script, every dry run, the planner regression, the catalogue generators and the mod's tests. After it all 34 matched line for line, apart from the clock times in openJiuwen's own start-up log. `suite.py` still accepts an old `--tasks experiments/tasks_*.json` path, and `experiments/README.md` maps every old path to its new one
- **41 unit tests and a Makefile.** They cover the scorer's count, price, yes or no and refusal rules, the suspended run rule, selection counting, repeat detection and the stratified test, each on the fault it was written for and on a case it must leave alone. Every clothing-cell figure on the site's Results page is pinned, every p value, silence and denominator included, and so are the runs its error and check tables name, so a change to any of them fails a test. The Experiments page's per-batch counts are the verdicts stored in each suite.json, checked by `make site-check` rather than a unit test. The three generated markets and their three generated question files are regenerated and compared byte for byte. The code that runs before the agent is checked for reads of an answer, instance or manifest key, of a fixture or manifest file, and for any seller or price copied from a market, with planted reads to prove the check can fail. A bare number such as the market size is not checked. `make check` runs them with the planner regression and the mod's 21 tests. The Makefile has no paid target, because the spend guard reads the command line
- **One site replaces five pages.** `docs/index.html` covers the objective, the results, every experiment, the markets, the problems, the tests, the architecture, the workflow, a week by week record and the plan to the final presentation. Its computed figures, tables and code excerpts are generated from the repository by `docs/build_site.py` (`make site`), and `make site-check` fails if the page is stale. `cell_facts.py` was split into one function that computes every clothing figure and a printer, so the command and the site are the same computation, and its output is unchanged. The old pages and the supervisor updates are in `docs/archive/`
- **Four problems found while reorganising, recorded and not yet fixed**, because the reorganisation was not allowed to change any output. `water/arms.py` and `water/headline.py` put 4 DeepSeek runs and 12 void second agent runs into the Calderwood "unmodified" row, 28 runs and 9 correct, where like for like it is 3 of 12, the figure this log quoted on 17 September. The browser tool is still fetched as `@playwright/mcp@latest`. The raw logs, about 1.7 GB, exist only on this laptop. And of the two local openJiuwen fixes this log names on 8 September, only one is in the submodule's working tree. All four are on the site's Problems page with what to do about each
- **openJiuwen can be rebuilt from a fresh clone.** The submodule now has a `.gitmodules` entry, pinned at `18d45d6`, and its one local change is kept as `agent/openjiuwen-local.patch`, described in `agent/README.md`
- **The openJiuwen paper is cited, not redistributed.** arXiv distributes 2608.27969 under its non-exclusive licence, which gives no one else the right to redistribute it, and this repository is public. The PDF is no longer tracked and stays on the laptop, ignored by git. Earlier commits on this branch still contain it, and none of them has been pushed. Taking it out of them rewrites the branch's history, so that waits for a decision
- openJiuwen's own `logs/` folder, start-up logs written whenever it is imported from the repository root, is no longer tracked
- An invalid escape sequence in the second agent's page script was fixed. The string sent to the browser is byte for byte the same, checked by comparing every constant in the file before and after
- The market ledger above now says what happened to the clothing market and Calderwood-S, and reserves the fresh clothing market the box must be tested on
- **The verifier failed the first version of all this, and was right.** It confirmed the reorganisation changed no output, from its own copy of the old commit. It also found that one count test could not fail on its fault and the answer key check missed four of five planted reads, both rewritten. It found claims stronger than the evidence, now corrected on the site and listed here
- **Correction to 18 September:** of the four DeepSeek runs, two were wrong, and the run that opened 4 listings was one of them, not the only one. Counted from the raw logs of `20260918T004730`
- **Correction to 8 October:** the refusal check replayed over the clothing cells refuses the 9 coverage failures only because `policy.gate` hands it two numbers from the answer key, the market size and the floor. Without them it refuses none. The September gate arms ran on the code of 10 September, which read the market size from the answer key but not yet the floor, added on 18 September, and the Calderwood gate batch of 10 September was re-scored on 13 September after a checker fix. Both September claims are suggestive, not established
- `--dry-run` lists tasks and answer kinds, not the text the agent receives, and `verify_cells.py` reads Thornwood's fixture by name. Both are on the plan before any paid run. Magento's licence notice was restored to the gated theme's template, which is derived from Magento's own

### 2026-10-08, later
- **A step back, and a narrower objective.** The experiments had run for weeks without a decisive result, so the project now has one written objective, in `OBJECTIVE.md`: build and prove a pre-processing box that reads the user's question and the first page, hands openJiuwen a retrieval plan, and asks the user back when the question is ambiguous. The ambiguous "offer" question is kept as a test case rather than reworded, because catching it is the box's job. Nothing was re-run for it
- **Cell 4 as designed is dropped.** It measured strategy text appended to the question, which the box replaces. The box is measured against the same baselines, cell 1 and cell 5
- **Every mistake this project has paid for is now in `LESSONS.md`**, 27 of them, each with the rule it produced and who enforces it
- **A workbench to enforce those rules**, in `tools/workbench/`, installed for this project only. A Claude Code mod attaches the objective to every prompt, checks each finished turn for drift, and adds `/objective`, `/park` and `/guard`. It also refuses any command that would spend OpenRouter credit unless the cost is declared, the run is kept awake, the verifier has stamped a pass at the checked-out commit with no uncommitted experiment code, and the user says yes in a dialog. Three subagents in `.claude/agents/` take the coding, the verification and the write-up, with the verifier the only one allowed to stamp
- **The guard is tested, not assumed.** 21 tests pass. Breaking three of its rules in a copy fails exactly the three tests for those rules. In a live session it refused a paid-looking command without a declared cost, refused it again without a stamp, and let a dry run through. The live test used a harmless stand-in script, so nothing could be spent
- Claude Code updated from 2.1.257 to 2.1.294, since mods need 2.1.287 or later. The VS Code extension already carried 2.1.293

### 2026-10-08
- **Every figure from cells 1 to 3 re-derived from the raw run files**, without trusting the suite's own summary. `experiments/verify_cells.py` re-scores every answer, recounts listings from the log and again from the tool replies alone, re-sums cost from the provider's charge per call, and checks each run's setting in what the browser reported. `experiments/compare_cells.py` redoes the statistics. Both read files only and are free to re-run. Held: listing counts agree in all 54 runs, no 404 page and no leaked price in any run, the window setting correct in every card summary reply, 1200 by 701 in every reply, a fresh cache per run, browser tool 0.0.83 throughout, and cost matching the account to the cent for cells 2 and 3. Cell 1 is $0.026 higher, which is exactly the late charge of the pilot run before it
- **Three figures were wrong.** A scoring error: the count rule took the first number, so "after checking all 15 listings, I found that 5 products have size M in stock" scored as 15. Fixed in `score.py` and re-scored through `rescore.py`, which changes exactly one verdict on this market, so cell 2 is 11 of 15, not 10. "Met the floor" counted 8 listings for every question, where each question has its own: the 8 that cannot be ruled out for the best price questions, all 15 for a count, one counterexample for "does every listing". Recounted, with the right listings required rather than enough of them, the numbers come out the same by coincidence. And the second agent samples at temperature 0 and replays itself, so its 15 gated runs are 7 different runs
- **Corrected tests, exact and stratified by question.** Window limit off against on: accuracy 11 against 4 of 15, p 0.005, pooled 0.027, reported on 7 October as 0.066. Opening what the answer needs, 15 against 3, p 0.00004. Second agent against openJiuwen as shipped on coverage, p 0.031 on its 7 distinct runs, reported as 0.003. The main result got stronger and the second agent result weaker
- **The word "offer" is ambiguous** in two questions. The key, fixed before any run, counts a sold out size as offered. Every run that explained its count read it as "can sell it now". Reported under both readings, and every comparison holds under both. The wording is kept for the remaining cells so all five answer the same questions
- **Two gaps in the 7 October fairness audit.** Sampling differs, openJiuwen at 0.2 with top_p 0.1, its shipped default, the second agent at 0. So does the clock, ten minutes for openJiuwen and none for the second agent. Neither bound in cells 1 to 3
- **A counting gap in my own tools.** Sizes chosen inside `browser_batch_interact` were not counted as selections, 28 across the openJiuwen cells. `trace_stats.py` counts them now, with tool call counts unchanged. The pilot's and September's claims of zero selections were re-checked and stand
- **Cell 5, told to open everything, 15 runs, $8.06.** The laptop slept on battery mid-batch and three runs were suspended for 17 to 50 minutes, where no openJiuwen run in any earlier batch was silent for more than 31 seconds. They are void under a rule set before their answers were read, and $2.18 went on them. The three were re-run the same afternoon with the machine kept awake, the same question text byte for byte, for $1.98. **Final, 15 valid runs: 11 correct under the key, 14 under the other reading, all 15 opened every listing the answer needs, $0.52 a run.** The same accuracy as cell 2 (p 1) and well above the shipped agent (p 0.007 by question). Told to be thorough, the shipped agent switched its own window limit off in 4 of the 18 runs made, which it never did in cell 1's 18
- **The gated reveal has a 60 millisecond delay of my own making, and it decided one run.** The theme writes the real price 60 ms after a size change so that Magento's widget cannot overwrite it. A script the agent wrote changed the size and read the price in the same instant, and got the stale price. Reproduced exactly with the agent's script. 2 of 51 openJiuwen runs wrote scripts like that. Kept, so every cell meets the same page, and stated as a property of this shop
- **Error analysis.** Not opening what the answer needs, 9 runs, all in cell 1. Reading the price before the page revealed it, 7. The "offer" reading, 9. Claiming a size is on sale when it is not, 1. Running out of steps, 2. The refusal check replayed over finished runs refuses exactly the 9 coverage failures and none of the 26 correct answers in cells 1, 2 and 5, and cannot see any other kind
- **Strategy v7 and planner v2, not yet run.** Choose the size, then look again before reading the price. Report only a price seen while its option was chosen. "The search results may run to more than one page" in place of a claim that they are paginated, which no current market is. Counting questions are told availability shows in the menu. Results page questions get their own strategy. Planner regression 37 questions, 0 failures. Cell 4 on this market is in sample for these changes, so the clean test is a freshly drawn market
- The 18 September label arithmetic figure re-counted from the run logs: surcharge sums appear in the reasoning of 9 of 12 runs and in no final answer. The 4 of 12 recorded then could not be reproduced, and the docs now say so
- **Every figure on the catch-up page's results is now generated from the run files**, and `experiments/cell_facts.py` prints all of them in one command, so the page can be checked line by line. `experiments/reveal_race.py` reproduces the 60 ms race with the agent's own script, copied byte for byte from its log
- The October update deck corrected in three places: group 2 is 11 of 15, "looked at enough" is each question's own need rather than eight listings, and the screenshot ratio. That sentence paired 1,656 snapshots with a thirteen to one ratio, which only holds counting page searches and card summaries too: 3,645 page reads to 278 screenshots over 361 runs, recounted from the run files
- Spend: cells 1 to 3 $12.10, cell 5 $8.06 and its three re-runs $1.98, plus $0.05 billed for two model calls the clock cut off. $43.39 of $100 left

### 2026-10-07
- **Three cells on the clothing market, 54 runs**, one question set, one model, one gated shop: openJiuwen as shipped, openJiuwen with its card summary's window limit off and nothing else changed, and the second agent with its link cap fixed. Figures as corrected on 8 October are above
- **The four listing behaviour is caused by one default in openJiuwen's card summary**, which keeps only cards whose top is inside the window and does not say what it dropped. Turning it off took opening what the answer needs from 3 of 15 runs to 15 of 15
- openJiuwen's selector cache, kept under the home directory across runs, made later runs differ from earlier ones. Each run now gets its own. Cost is now the provider's charge per call, after both earlier methods were shown wrong
- The second agent's first twelve runs were void, opening zero product pages with 49 missing page errors, from a link cap of mine. Fixed by counting content links before navigation links

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
- **The gate rules are not at the `c736bc0` freeze.** Three commits since changed decisions: `refutation_without_evidence` added (`cfad4b6`), the `QUANTITY` units fix (`670ed0d`), and click-opened listings counted (`28b6583`). The literal frozen code was extracted and checked: it reproduces the recorded 3 of 4 caught, 0 of 11 blocked on batch 2
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
- Rules frozen at `c736bc0`, fresh baseline run, $3.41, replayed under them alone: **3 of 4 failures caught, 0 of 11 correct answers blocked, $0.00 added cost**. Out of sample
- Gating on retrieval coverage was tested and rejected again. Correct answers to the comparison tasks opened 1, 4, 4, 8, 12, 13, 14 and 14 listings; wrong ones opened 4 every time. A floor at 11 catches all six failures and blocks three correct answers
- `scaled-best-per-litre` opens exactly 4 listings in all seven runs, right and wrong alike, so its one correct answer rests on the same evidence as its six wrong ones. Correctness and soundness are separate properties and the report carries both
- Spend to date **$18.63**, 120 browser runs, topped up by a further $15 so the remaining arms are funded. Cost is measured two ways and they disagree. The sum of per-run deltas is $15.94; OpenRouter's own usage for the key is $18.63. The key figure is authoritative and the per-run figures are a lower bound: exploratory runs made before cost capture worked are absent, and a run's delta is read as soon as spend moves rather than once it has fully settled.

### 2026-09-08, later
- openJiuwen runs end to end against the seeded environment. `experiments/` now holds a task suite, a scorer, an interaction counter and a suite driver
- RQ2 baseline measured: 60 runs, $2.98, `claude-haiku-4.5`. 87% correct on gated tasks, **0 abstentions in 60 runs**, and correctness collapses to 20% when the agent spends only one action. See [notes/rq2-baseline.md](notes/rq2-baseline.md)
- Two upstream openJiuwen bugs found and patched locally: an empty probe result reported as a JSON parse error, and the worker's `ok: false` not reaching the runtime result. Apache 2.0, candidates for a pull request
- Cheap models could not complete the tasks. `gemini-2.5-flash-lite` fails openJiuwen's structured output contract; `deepseek-chat` and `qwen3.7-flash` were rate-limited at their providers regardless of account credit. The cheap-tier assumption in the proposal does not hold
