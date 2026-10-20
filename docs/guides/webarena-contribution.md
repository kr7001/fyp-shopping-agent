# Contributing the gated-variant shop to WebArena-Verified

Prepared 21 October 2026 from the repository at `05663e9` and from GitHub, Docker Hub and Magento's sources. Nothing here touches tonight's batch or costs money.

## 1. The contribution, in two sentences

WebArena-Verified's shopping catalogue has 104,368 products, all `type_id = simple`, so no task can ask for a price or stock level that depends on the size or pack selected. This extension adds configurable products whose variants differ in price and stock, a theme that shows a variant's price only once it is selected, a seeded generator that builds 15-seller markets with answer keys computed from the fixture, and a checker that confirms in a real browser that the shop matches the fixture.

## 2. What upstream looks like

- `ServiceNow/webarena-verified`, Apache-2.0. Its one code owner and maintainer is `@Am1n3e`, Amine El hattami, the paper's first author.
- It re-audits WebArena's 812 tasks, swaps `string_match`, `url_match` and `program_html` for typed evaluators on a JSON answer, and scores offline from network traces.
- He builds the site images with numbered shell scripts run in the original image, and pushes them under `am1n3e`. The shopping tags, `latest` and `0.1.0`, date from 2 February 2026.
- CONTRIBUTING.md welcomes dataset and evaluation improvements by fork and pull request. It has no CLA, DCO or AI policy, and there are no issue templates.
- The last commit on `main` is from 7 February 2026, his last issue or pull request comment from 14 March. All 27 merges are his, and four outside pull requests are open, the oldest since March.
- Precedent: VisualWebArena (a new site), WebArena-Lite (a 165-task refined subset), WebChoreArena (532 new tasks) and WASP (injected content) each shipped as a separate repository on the WebArena images.

## 3. Recommended route

1. Build a small, separate repository with only the environment work.
2. Open one issue on `ServiceNow/webarena-verified` describing the gap, linking it, and asking whether and how they want it (section 8).
3. Open a pull request only in the shape they ask for.

Why. The change is shop-wide (two store options, 63 products) under an image carrying 192 verified shopping tasks, so it must stay opt-in. Nothing from outside has had a maintainer reply since 14 March, so the FYP cannot wait on a merge. Their evaluator can still score your tasks through its config's `test_data_file` (documented, not tried), if your runner writes their JSON answer shape.

Alternatives. A site directory in their pipeline is most native, but means shell scripts run inside the container and an image they publish. Tasks alone would fail on the stock image, since `sites` cannot name an extended shop. Your own `docker commit` image is heaviest and redistributes the catalogue.

## 4. What to package

| | Files | Change first |
|---|---|---|
| Ship | `env/magento.py`, `env/seed_variants.py` | drop `strip-notes`, a project-only repair |
| Ship | `env/install_gated_theme.py`, `env/gated_theme/` | container name as a flag, default `webarena-verified-shopping` |
| Ship | `env/generate_apparel.py` | drop the Thornwood guard, add a writer for their format |
| Ship | `env/check_market.py`, `experiments/box/page.py` | drop the `paths` import, base URL as a flag |
| Ship | `env/pick_apparel_market.py` | the same import fixes |
| Ship | `env/fixtures/claim_apparel.json`, `env/manifests/claim_apparel-search.json` | none |
| Ship | a new `setup.sh`, the run-free tests from `test_claim_market.py` and `test_catalogues.py` | section 7's order |
| Convert | `tasks_claim_apparel.json` | its 11 keyed questions, by script from the fixture, with the two "offer" questions reworded |
| Later | `verify_shop.py`, the water markets | the same fixes |
| Leave | the readings and v2 task files, the review, demo, inspection and probe scripts | project-specific |

Copy files in, do not fork. Leave out `.env`, `.env.example`, `.har` files, results, runs, logs, timestamped manifests, `.verification/`, `.claude/`, `tools/`, the planning files, `agent/`, `docs/`, `notes/`, Shopee and Lazada material, the deck and the PDF. The files to ship contain no local paths, keys or personal details, and their Magento logins are the image's public defaults.

## 5. Licences and attribution

- License your files Apache-2.0 like upstream, which meets CONTRIBUTING's licence rule. Add `LICENSE`, `NOTICE`, and SPDX and copyright lines. The FYP repository has no licence yet, and I found no NUS rule on licensing FYP code, so ask the supervisor.
- Magento 2.4.6's `composer.json` declares OSL-3.0 and AFL-3.0, though `COPYING.txt` names only OSL. Both require keeping Magento's notices and marking changes. OSL is reciprocal and counts network use as distribution. AFL allows any compatible licence.
- So keep `configurable.phtml` under both, as its header says, with Magento's two licence texts beside it. Name it in `NOTICE` as the one non-Apache file, and raise it in the issue.
- Cite both projects, state that you are not affiliated with or endorsed by ServiceNow or the WebArena authors, and keep "webarena-verified" off the front of your repository's name.

## 6. One question in their format

`apparel-cheapest-target`, keys from the Ashcombe fixture.

```json
{
  "sites": ["shopping"],
  "task_id": 90001,
  "intent_template_id": 90001,
  "start_urls": ["__SHOPPING__/catalogsearch/result/?q=Ashcombe"],
  "intent": "Across the Ashcombe listings, which seller is cheapest for size M, and what is that price? Only count a listing that can actually supply that size. Return an object with keys \"seller\" (the name after the dash in the listing title) and \"price\" (as a number, e.g., 10.99) only, without any additional details.",
  "intent_template": "Across the {{brand}} listings, which seller is cheapest for size {{size}}, and what is that price? Only count a listing that can actually supply that size. {{retrieved_data_format_spec}}.",
  "instantiation_dict": {
    "brand": "Ashcombe",
    "size": "M",
    "retrieved_data_format_spec": "Return an object with keys \"seller\" (the name after the dash in the listing title) and \"price\" (as a number, e.g., 10.99) only, without any additional details"
  },
  "eval": [
    {
      "evaluator": "AgentResponseEvaluator",
      "results_schema": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "seller": {"type": "string"},
            "price": {"type": "number", "format": "currency"}
          }
        }
      },
      "expected": {
        "task_type": "retrieve",
        "status": "SUCCESS",
        "retrieved_data": [{"seller": "Copperfield Outfitters", "price": 23.43}]
      }
    }
  ],
  "revision": 1
}
```

Notes, (?) where unsure:
- `task_id`, `intent_template_id` (?): placeholders. Theirs use 0 to 811 and 4 to 6100.
- `start_urls` (?): no task starts on a query string. Fallback: `__SHOPPING__`, with the search in the intent.
- `revision` (?): at least 1. Existing tasks use 2 to 4.
- `seller` (?): matched after lowercasing. Two or more listed alternatives would also accept "Copperfield".
- The exact one-object list should fail an answer that also names Ivybridge or Brindle, your `not_any`. Not run.
- Drop `gated`, `family`, `note` and `box`, which their model rejects.
- Prices match within 0.10. The nearest other price, Rookwood's size L, is $23.23, so this holds. Add a generator check.

In the original WebArena format the `eval` block would be this, but `must_include` cannot forbid a seller.

```json
"eval": {
  "eval_types": ["string_match"],
  "reference_answers": {"must_include": ["Copperfield", "23.43"]},
  "reference_url": "",
  "program_html": [],
  "string_note": "",
  "reference_answer_raw_annotation": "Copperfield Outfitters, $23.43"
}
```

## 7. Pre-submission checklist

Begin once tonight's batch is verified and disk space checked. Stop the project container (never `rm` it), as the scripts assume port 7770.

- [ ] Read the two options you set by hand. Commit `f183b46` records only "the page size is 36", and `show_out_of_stock` was never scripted.

```bash
docker exec webarena-shopping mysql -u magentouser -pMyPassword magentodb -e "SELECT scope, scope_id, path, value FROM core_config_data WHERE path LIKE 'catalog/frontend/grid_per_page%' OR path = 'cataloginventory/options/show_out_of_stock'"
docker inspect webarena-shopping --format '{{.Image}}'
```

- [ ] From the package, after the section 4 changes: a fresh container in CLAUDE.md's order, then the extension, then the checks.

```bash
docker stop webarena-shopping
docker pull am1n3e/webarena-verified-shopping:0.1.0
docker run -d --name webarena-verified-shopping -p 7770:80 -p 7771:8877 am1n3e/webarena-verified-shopping:0.1.0
docker exec webarena-verified-shopping curl -s http://localhost:9200/_cluster/health
# once that answers, Initialize on the control panel at http://localhost:7771
docker exec webarena-verified-shopping php /var/www/magento2/bin/magento indexer:reindex
docker exec webarena-verified-shopping php /var/www/magento2/bin/magento cache:flush
# the extension, as setup.sh should run it. Paths and values (?) until the read above confirms them
docker exec webarena-verified-shopping php /var/www/magento2/bin/magento config:set cataloginventory/options/show_out_of_stock 1
docker exec webarena-verified-shopping php /var/www/magento2/bin/magento config:set catalog/frontend/grid_per_page 36
python3 env/seed_variants.py seed --fixture claim_apparel.json
python3 env/seed_variants.py verify --fixture claim_apparel.json
python3 env/install_gated_theme.py --install
docker exec webarena-verified-shopping php /var/www/magento2/bin/magento indexer:reindex
docker exec webarena-verified-shopping php /var/www/magento2/bin/magento cache:flush
# the checks, with a Python that has Playwright
python3 env/check_market.py --fixture claim_apparel.json
python3 env/pick_apparel_market.py --check-only --fixture env/fixtures/claim_apparel.json
```

- [ ] `check_market.py` reports 0 failed, `--check-only` prints `usable` with the answer at card 11, and the ported tests pass.
- [ ] Stock tasks hold. Count out-of-stock products, which the option reveals, and re-check tasks reading search or category pages, such as 124 to 126, 263, 439, 467 and 793.
- [ ] No secrets. `git ls-files` lists only intended files, and `git grep -n -i -e sk-or -e openrouter -e api_key -e cookie` finds nothing.
- [ ] Licence files and headers as in section 5.
- [ ] A one-page design note on why gating matters: CLAUDE.md's finding that structured data publishes no lower bound (Shopee's JSON-LD and WebArena's microdata are plain `Offer`s, never `AggregateOffer`), the all-`simple` catalogue, Magento's `optionPrices` leak (`env/README.md`) and the theme's limit, that prices still reach the browser encoded.
- [ ] Stop the fresh container, then restart the project one with `./env/start.sh`.

## 8. Draft issue

**Title:** Proposal: an optional shopping extension with variant-dependent prices and stock

Thank you for WebArena-Verified. I am a final-year student at the National University of Singapore, studying how web agents handle information that appears only after an interaction.

All 104,368 shopping products are `type_id = simple` and no option carries a price delta, so no task needs a variant selected to learn its price or stock.

I have built an opt-in extension at <link>, Apache-2.0 apart from one Magento-derived template:
- a REST seeder for configurable products, SKUs prefixed `IGR-`, with teardown
- a theme, served only to a marked user agent, that withholds variant prices until one is selected
- a market generator with answer keys computed from the fixture, and a browser checker
- example tasks in your format

It sets `show_out_of_stock` to 1 and a page size of 36 and adds 63 products, so I propose it as opt-in only. Would you like it upstream, or as a separate repository you link to? More questions below.

## 9. Draft pull request description, only if they ask for one

Adds the opt-in shopping extension discussed in #<issue>.
- **Adds:** seeder, theme, generator, checker, one market and its tasks.
- **Try it:** `setup.sh` on a fresh `am1n3e/webarena-verified-shopping:0.1.0`, then `check_market.py`.
- **Unchanged:** the default image, existing tasks, the evaluator.
- **Checked:** fresh container on <date>, checker clean, stock tasks <list> re-checked, `uv run pytest` and `inv -r dev code-format-and-check` pass.
- **Licensing:** Apache-2.0, except `configurable.phtml`, kept under Magento's OSL-3.0 and AFL-3.0 with both texts.
- Partly written with an AI coding assistant, and reviewed by me.

## 10. What not to say until a pull request is merged

The project claims no upstream contribution unless a pull request is merged, here into `main`. Until then say "an open-source extension for the WebArena-Verified shopping image", "proposed in issue #N" or "pull request #N, under review". Never say "contributed to WebArena" or "WebArena-Verified", "upstreamed", "accepted", "part of" or "official", in the report, slides, site, decision log or CV.

## 11. Sources, and what I could not confirm

- https://github.com/ServiceNow/webarena-verified
- https://github.com/ServiceNow/webarena-verified/blob/main/CONTRIBUTING.md
- https://github.com/ServiceNow/webarena-verified/blob/main/.github/CODEOWNERS
- https://github.com/ServiceNow/webarena-verified/tree/main/dev/environments
- https://github.com/ServiceNow/webarena-verified/blob/main/docs/getting_started/data_format.md
- https://github.com/ServiceNow/webarena-verified/blob/main/docs/getting_started/configuration.md
- https://github.com/ServiceNow/webarena-verified/blob/main/src/webarena_verified/types/task.py
- https://github.com/ServiceNow/webarena-verified/blob/main/src/webarena_verified/core/evaluation/data_types/currency.py
- https://github.com/ServiceNow/webarena-verified/blob/main/src/webarena_verified/core/evaluation/data_types/string.py
- https://github.com/ServiceNow/webarena-verified/blob/main/src/webarena_verified/core/evaluation/data_types/base.py
- https://github.com/ServiceNow/webarena-verified/blob/main/assets/dataset/webarena-verified.json
- https://api.github.com/repos/ServiceNow/webarena-verified/pulls?state=all
- https://api.github.com/repos/ServiceNow/webarena-verified/issues?state=all
- https://openreview.net/forum?id=94tlGxmqkN
- https://neurips.cc/virtual/2025/124576
- https://hub.docker.com/r/am1n3e/webarena-verified-shopping/tags
- https://api.github.com/users/Am1n3e
- https://github.com/web-arena-x/webarena
- https://github.com/web-arena-x/webarena/blob/main/config_files/test.raw.json
- https://github.com/web-arena-x/visualwebarena
- https://github.com/THUDM/VisualAgentBench/tree/main/VAB-WebArena-Lite
- https://github.com/WebChoreArena/WebChoreArena
- https://github.com/facebookresearch/wasp
- https://github.com/magento/magento2/blob/2.4.6/COPYING.txt
- https://github.com/magento/magento2/blob/2.4.6/composer.json
- https://github.com/magento/magento2/blob/2.4.6/app/code/Magento/ConfigurableProduct/composer.json
- https://github.com/magento/magento2/blob/2.4.6/LICENSE.txt
- https://github.com/magento/magento2/blob/2.4.6/LICENSE_AFL.txt
- https://www.apache.org/licenses/LICENSE-2.0

Not confirmed: the maintainers' response, your page-size config path and scope, whether `eval-tasks` takes an outside task file or fails an extra answer object, your container's image digest, any effect on stock tasks, and NUS's licensing rule.

## 12. Open questions only the maintainers can answer

1. Upstream, or a separate repository you link to?
2. If upstream, a site directory and image you publish, or scripts run against the stock container?
3. Where should its tasks live, with which ID ranges, `revision` and start URL, and should `sites` gain a value?
4. Are the two shop-wide options acceptable if opt-in, or should they be scoped?
5. Should gated-price tasks keep the 0.10 currency tolerance?
6. How should one file under OSL-3.0 and AFL-3.0 be handled, given the contribution licence rule?
7. Would a retrieval-coverage check, reading which listing pages the network trace fetched, be in scope?
