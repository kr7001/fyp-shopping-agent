# Environment fixtures

Tooling that adds **interaction-gated pricing** to a self-hosted WebArena shopping site.

## Why this exists

WebArena's stock catalogue cannot express the failure this project studies. Measured
against the running instance on 2026-09-08:

| Measurement | Value |
| --- | --- |
| Products | 104,368 |
| Products of type `configurable` | 0 |
| Select-type custom option values | 425,384 |
| Option values carrying a non-zero price delta | **0** |
| Non-select options carrying a price | **0** |

Query used, for anyone re-checking:

```bash
docker exec -it webarena-shopping mysql -u magentouser -pMyPassword magentodb -e "
SELECT 'select-type option values' AS scope, COUNT(*) AS total_values,
       SUM(CASE WHEN COALESCE(tp.price,0) <> 0 THEN 1 ELSE 0 END) AS with_price_delta
FROM catalog_product_option_type_value v
LEFT JOIN catalog_product_option_type_price tp ON tp.option_type_id = v.option_type_id;"
```

So the environment has option *variance* but no price *variance*. A shopper can pick a
colour, but every choice costs the same, and nothing is hidden behind the click. Magento
2.4.6 supports configurable products natively — the tables are present and empty — so this
is a catalogue gap, not a platform limit.

`seed_variants.py` fills that gap.

## What gets seeded

Four families, 14 variants, all SKUs prefixed `IGR-`. Defined in
[fixtures/gated_pricing.json](fixtures/gated_pricing.json).

| Family | Gating | The trap |
| --- | --- | --- |
| `water-cellar-direct` | price by variant | "From" price is the 12 x 550ml pack. Cheapest per litre is the 2 x 9.5L. Mirrors the live listing observed by hand in August 2026 |
| `water-hillside-provisions` | price by variant | Same product, second seller. Higher "from" price, **cheaper** 2 x 9.5L. A card-level probe ranks the two listings backwards |
| `coffee-bulk-reversal` | price by variant | Cost per kilo falls then rises. The best unit price is in the middle of the range and cannot be inferred from either endpoint |
| `tee-stock-gating` | stock by variant | Parent reads In Stock. Size M is out of stock, XL carries a surcharge. Neither is in the first observation |

The two water families are the important pair. They reproduce the deployed-assistant
failure exactly: comparing headline prices names the wrong seller for a large-carton
question.

## Usage

```bash
cd env
python seed_variants.py seed --dry-run    # print the plan, write nothing
python seed_variants.py seed              # idempotent, safe to re-run
python seed_variants.py verify            # read back from Magento, check prices
python seed_variants.py teardown --yes    # delete every IGR- product
python seed_variants.py strip-notes       # blank descriptions seeded before 13 Sep 2026
```

A family's `note` in the fixture is for people reading the fixture. It is never sent to
Magento. Until 13 Sep 2026 it was written into the product description, which the agent
reads, and on the hand-written fixture those notes stated the answers. `strip-notes`
removes them from products seeded before the change; `seed` cannot, because it skips any
product that already exists. See the README decision log for what the leak affected.

Then reindex, or the storefront will not show any of it:

```bash
docker exec -it webarena-shopping php /var/www/magento2/bin/magento indexer:reindex
docker exec -it webarena-shopping php /var/www/magento2/bin/magento cache:flush
```

Defaults target `http://localhost:7770` as `admin`/`admin1234`. Override with
`--base-url`, `--user`, `--password`. Writes go through the Magento REST API, never
through direct SQL, so Magento's own validation and indexing apply.

## Ground truth

Every `seed` run writes `manifests/<timestamp>-gated-pricing.json` containing the SKUs
created and a computed `ground_truth` block: the "from" price per family, the per-unit
price of each variant, which variant actually wins, and a `card_probe_wrong` flag for
each option contested by two listings.

That file is the answer key. Runs can be scored against it without re-reading the
storefront, and it records exactly which products are mine rather than WebArena's.

## Prerequisites

- The shopping container running, see the root [README](../README.md)
- `requests` (`pip install -r requirements.txt`)
- Elasticsearch actually up. Catalog Search is in Update on Save mode, so a product save
  triggers an inline fulltext reindex. See the Apple Silicon note in the root README —
  on an M-series Mac without Rosetta enabled this is the step that appears to hang

## The gated store view, added 18 September 2026

Magento hands the browser every variant price on first load. The page carries an
`optionPrices` table, and the configurable widget renders each option label with its
surcharge, `2 x 9.5L +$32.50`. Both are readable in the first observation an agent takes,
so a variant price is not gated here the way it is on the live marketplace, where the page
holds exactly one price at a time. The agent noticed before I did: it selects a pack size
in 11 of 122 runs on the fifteen seller markets, and adds the surcharge to the base price
instead in 48 of 290 stored answers.

`install_gated_theme.py` adds a **second store view** rather than changing the shop.

| | Store view `default` | Store view `gated` |
| --- | --- | --- |
| Theme | Magento Blank, untouched | `IGR/suppressed` |
| Prices in the page on load | all four | the "from" price only |
| Option labels | `2 x 9.5L +$32.50` | `2 x 9.5L` |
| Price after selecting the option | $48.64 | $48.64 |

Same products, same prices, same answers. Every run already recorded was made against
`default`, which still renders exactly as it did, so nothing recorded loses the environment
it was measured in. Reach the gated view by adding `___store=gated` to any URL.

```bash
python env/install_gated_theme.py --check
python env/install_gated_theme.py --install
docker exec webarena-shopping php /var/www/magento2/bin/magento indexer:reindex catalogsearch_fulltext
python env/install_gated_theme.py --remove
```

Run the reindex **on its own**. Two reindexes at once is how this container ends up with an
index stuck in `working`, which the root README has the fix for.

**What this does not claim.** The real prices still reach the browser, in an opaque blob
that the page decodes for the one option actually selected. An agent that runs JavaScript of
its own could decode it, exactly as an agent on the live marketplace could call the API its
page fetches from. What is removed is the price being *readable in the observation the agent
takes before interacting*, which is the property the experiments measure.
