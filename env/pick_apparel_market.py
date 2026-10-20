#!/usr/bin/env python3
"""Seed clothing markets until one lands the right way round on the results page.

A market is only a trap if the glance is wrong. The answer has to sit outside the first row
of search results, and something inside that row has to look cheaper than the answer, or the
questions measure something other than retrieval. The clothing market got this wrong twice:
the first draw put the answer at card 4 and the agent scored 3 of 3 by glancing, and the
second put the cheapest listing at card 11 so a glance found nothing misleading at all and
the control question stopped being a control.

Both times the fix was a rule on the listing's index in the catalogue, and both times it
failed. **Catalogue index does not decide where a listing renders. Variant count does.**
Measured on 18 September 2026 across eight generated markets: Magento's fulltext relevance
indexes every child product, so a listing offering four sizes carries the brand name four
times and outranks one offering two. In the market measured, every listing in cards 1 to 8
had four sizes, cards 9 to 11 had three, and cards 13 to 15 had two.

That made the old condition unsatisfiable rather than merely unlucky. The cheapest advertised
listing is the one missing the target size, so it has fewer variants by construction, so it
renders late by construction. Eight consecutive seeds were rejected with it at cards 8, 12,
8, 14, 10, 15, 12 and 13, never once in the first four.

So the condition is now the one that actually matters, and it is weaker in the right way: the
answer must render outside the first row, and at least one listing inside the first row must
advertise a price below what the answer costs. A shopper glancing at the first screen then
sees something that looks like a better deal and is not. Which particular listing plays that
role does not matter.

**What a card advertises** is the cheapest size that can be bought, which is what Magento
prints on it (`generate_apparel.from_price`), and since 20 October 2026 the rule reads it off
the live page. Until then it took the cheapest of every size, sold out included, so a listing
like igr-app-07, whose S and M are sold out at $16.22 and $15.04 and whose card shows
"As low as $18.33", counted as advertising $15.04 (verifier's logic audit, found before the
claim market was drawn). On Thornwood the two readings name the same three listings.

**A second market** runs under its own fixture, brand and SKU prefix, so Thornwood's 15
listings are never torn down. Each attempt removes the previous candidate, checks that no
product of it survives in the shop or on the results page, and records what it found;
`--search-log` writes the record of every seed tried, which the accepted fixture carries.

Nothing here costs money, only time: a cycle is about five minutes, most of it reindexing.

    python env/pick_apparel_market.py --check-only     # just measure what is seeded now
    python env/pick_apparel_market.py --check-brands Ashcombe Hartwell Wyndham
    python env/pick_apparel_market.py --brand <Brand> --sku-prefix IGR-CLM \
        --fixture env/fixtures/claim_apparel.json \
        --search-log env/manifests/claim_apparel-search.json --seeds 204 205 206
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import textwrap
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "experiments"))
import generate_apparel as apparel  # noqa: E402  (the defaults, from_price, the name lists)
import paths  # noqa: E402,F401  (puts experiments/box on the path)
import page as page_module  # noqa: E402  (the box's own reading of the results page)

FIXTURE = HERE / "fixtures" / "scaled_apparel.json"
TASKS = REPO / "experiments" / "tasks" / "tasks_apparel.json"
CONTAINER = "webarena-shopping"
MAGE = "/var/www/magento2/bin/magento"
FIRST_ROW = 4
BASE = "http://localhost:7770"
GATED_UA = page_module.GATED_UA

# Written into the search record, and so into the accepted fixture's `_about`.
PAGE_RULE = ("Page rule: the answer renders outside the first 4 cards, and a listing inside "
             "the first 4 advertises less than the answer costs, read off the live page's "
             "card, which shows the cheapest size that can be bought. Until 20 October 2026 "
             "the rule's implementation took the cheapest of every size, sold out included; "
             "corrected before this search began (verifier's logic audit).")


class Stop(RuntimeError):
    """The shop, not the seed, is at fault: the search stops rather than reject a seed."""


@dataclasses.dataclass(frozen=True)
class Market:
    """Which market a search draws: the fixture it writes, the task file written with it
    (None for none), and the brand and SKU prefix its listings carry. Thornwood's by
    default. `replace_thornwood` must be set to tear Thornwood's listings down."""
    fixture: pathlib.Path = FIXTURE
    tasks: pathlib.Path | None = TASKS
    brand: str = apparel.BRAND
    sku_prefix: str = apparel.SKU_PREFIX
    replace_thornwood: bool = False


def run(command: list[str], quiet: bool = True) -> int:
    return subprocess.run(command, cwd=REPO,
                          capture_output=quiet, text=True).returncode


def run_or_stop(command: list[str], what: str) -> None:
    """Run a step whose failure means the shop, not the seed, is at fault, and stop the
    search with the step's own last words."""
    done = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
    if done.returncode:
        tail = (done.stdout + done.stderr).strip()[-600:]
        raise Stop(f"{what} (exit {done.returncode}): {tail}")


def results_html(brand: str, user_agent: str | None = None) -> str:
    """The results page for the brand. Without a user agent, urllib's own, as the rule has
    always read it; the gated theme's with GATED_UA, as the agent's browser reads it."""
    request = urllib.request.Request(f"{BASE}/catalogsearch/result/?q={brand}")
    if user_agent:
        request.add_header("User-Agent", user_agent)
    return urllib.request.urlopen(request, timeout=120).read().decode()


def rendered_order(brand: str, user_agent: str | None = None) -> list[str]:
    """The sellers as the results page actually lists them, in order."""
    html = results_html(brand, user_agent)
    seen: list[str] = []
    for match in re.finditer(rf"{brand} Heavyweight Cotton Tee - ([A-Za-z ]+?)\s*<", html):
        seller = match.group(1).strip()
        if seller not in seen:
            seen.append(seller)
    return seen


def positions(fixture: dict) -> tuple[int | None, int | None, list[str]]:
    instance = fixture["_instance"]
    order = rendered_order(fixture["_generated"]["brand"])
    def place(name: str) -> int | None:
        return order.index(name) + 1 if name in order else None
    return (place(instance["cheapest_card"]["seller"]),
            place(instance["winner"]["seller"]), order)


def card_prices(fixture: dict) -> dict[str, float]:
    """What each listing's card advertises, from the fixture: its cheapest buyable size."""
    return {f["seller"]: apparel.from_price(f) for f in fixture["families"]}


def first_row_misleads(fixture: dict, order: list[str],
                       advertised: dict[str, float] | None = None) -> list[str]:
    """Listings in the visible row that advertise less than the real answer costs.

    This replaces asking where one particular listing rendered. What has to be true is
    that a glance at the first row is actively misleading, and that holds whenever any
    visible listing advertises a price below what the answer actually costs. Requiring it
    of the single cheapest listing was both stronger than needed and, as it turned out,
    unsatisfiable: the cheapest listing is the one missing the target size, which gives it
    fewer variants, and Magento ranks a listing with fewer variants lower.

    `advertised` is each seller's card price as the live page shows it; without it, what
    the fixture says the card shows (`card_prices`). Never the cheapest of every size: a
    sold-out size's price is not on the card (20 October 2026, see the module docstring).
    """
    instance = fixture["_instance"]
    answer_price = instance["winner"]["price"]
    if advertised is None:
        advertised = card_prices(fixture)
    return [seller for seller in order[:FIRST_ROW]
            if advertised.get(seller, float("inf")) < answer_price]


def usable(answer: int | None, misleading: list[str]) -> bool:
    """The answer is out of reach of a glance, and a glance is actively wrong."""
    return bool(answer and answer > FIRST_ROW and misleading)


def reindex() -> None:
    # Stock as well as search, since 18 Sep 2026. A market now seeds variants with qty 0 on
    # purpose, and without the stock index Magento keeps serving the old availability, so a
    # sold out size still renders as buyable and the draw is measured against a page that
    # does not exist.
    run(["docker", "exec", CONTAINER, "php", MAGE, "indexer:reindex",
         "catalogsearch_fulltext", "cataloginventory_stock"])
    run(["docker", "exec", CONTAINER, "php", MAGE, "cache:flush"])


def elasticsearch_status() -> str | None:
    """The search engine's cluster status, asked on port 9200 inside the container, or None
    when it does not answer. CLAUDE.md's order confirms it before any reindex, because under
    emulation it can hang while supervisor reports it running."""
    out = subprocess.run(["docker", "exec", CONTAINER, "curl", "-s", "-m", "5",
                          "http://localhost:9200/_cluster/health"],
                         capture_output=True, text=True)
    try:
        status = json.loads(out.stdout).get("status")
    except json.JSONDecodeError:
        return None
    return status if status in ("green", "yellow") else None


def mysql(sql: str) -> str:
    """One query in the shop's database. These are the fixed image credentials, not secrets."""
    done = subprocess.run(["docker", "exec", CONTAINER, "mysql", "-u", "magentouser",
                           "-pMyPassword", "magentodb", "-N", "-e", sql],
                          capture_output=True, text=True)
    if done.returncode:
        raise Stop(f"mysql failed: {done.stderr.strip()[-200:]}")
    return done.stdout


# ------------------------------------------------------------------ what is in the shop


def fixture_skus(fixture: dict) -> set[str]:
    """Every SKU the seeder writes for a fixture: each parent, and each size as the seeder
    names it (`seed_variants.expand_skus`)."""
    out = set()
    for family in fixture["families"]:
        out.add(family["parent_sku"])
        out.update(v.get("sku") or f"{family['parent_sku']}-{v['option'].upper()}"
                   for v in family["variants"])
    return out


def shop_skus(prefix: str) -> set[str]:
    """Every product in the shop whose SKU carries the prefix, read from the database."""
    if not re.fullmatch(r"[A-Z0-9-]+", prefix):
        raise SystemExit(f"not a SKU prefix: {prefix!r}")
    return set(mysql(f"SELECT sku FROM catalog_product_entity WHERE sku LIKE '{prefix}-%'")
               .split())


def listing_url(family: dict) -> str:
    """The URL the shop gives a listing: its URL key is its SKU (`seed_variants.slugify`)."""
    return f"{BASE}/{family['parent_sku'].lower()}.html"


def shop_matches(fixture: dict, prefix: str) -> list[str]:
    """What is wrong between the shop and the fixture, after seeding and reindexing: SKUs
    left over or missing, and a results page that does not list exactly the fixture's
    listings at their URLs and card prices, in one order under both user agents. Empty
    when nothing is. A rejected seed's products must not survive into the next attempt."""
    problems = []
    want, have = fixture_skus(fixture), shop_skus(prefix)
    if have != want:
        problems.append(f"SKUs left over {sorted(have - want)}, missing {sorted(want - have)}")
    brand = fixture["_generated"]["brand"]
    url = f"{BASE}/catalogsearch/result/?q={brand}"
    expected = {listing_url(f): (f["seller"], apparel.from_price(f)) for f in fixture["families"]}
    orders = {}
    for label, agent in (("plain", None), ("gated", GATED_UA)):
        try:
            seen = page_module.parse(results_html(brand, agent), url)
        except ValueError as error:
            problems.append(f"{label} results page unreadable: {error}")
            continue
        got = {item.url: (item.seller, item.advertised) for item in seen.listings}
        if got != expected or seen.next_page or seen.total != len(expected):
            problems.append(f"{label} results page lists {len(got)} (total {seen.total}, next "
                            f"page {seen.next_page}), not the fixture's {len(expected)}: "
                            f"{sorted(set(got.items()) ^ set(expected.items()))}")
        orders[label] = [item.seller for item in seen.listings]
    if len(orders) == 2 and orders["plain"] != orders["gated"]:
        problems.append("the plain and the gated results pages list the sellers in different "
                        "orders, so the rule would measure a page the agent does not see")
    return problems


# ------------------------------------------------------------------------- one attempt


def teardown_refused(market: Market, fixture: dict) -> str | None:
    """Why the products of this fixture may not be torn down, or None when they may: its
    listings do not all carry the market's prefix, or they are Thornwood's and nobody asked,
    since the stored development batches ran on Thornwood's 15 listings. Kept apart from
    `teardown` so a test can ask it without anything being deleted."""
    parents = [f["parent_sku"] for f in fixture["families"]]
    if not all(sku.startswith(market.sku_prefix + "-") for sku in parents):
        return f"its listings are not all {market.sku_prefix}"
    if market.fixture.resolve() == FIXTURE.resolve() and not market.replace_thornwood:
        return "they are Thornwood's, and --replace-thornwood was not given"
    return None


def teardown(market: Market) -> str:
    """Delete the products of the fixture now at `market.fixture`, the previous candidate's,
    unless `teardown_refused` says why not."""
    if not market.fixture.exists():
        return "no earlier candidate to remove"
    fixture = json.loads(market.fixture.read_text())
    refused = teardown_refused(market, fixture)
    if refused:
        raise SystemExit(f"refusing to tear down {market.fixture.name}: {refused}")
    run_or_stop([sys.executable, "env/seed_variants.py", "teardown", "--fixture",
                 market.fixture.name, "--yes"], f"teardown of {market.fixture.name} failed")
    return f"removed the {len(fixture['families'])} listings of {market.fixture.name}"


def attempt(seed: int, market: Market = Market()) -> dict:
    """One seed: remove the previous candidate, draw this one by the 13 rules, seed it,
    reindex, check that the shop holds exactly it, and apply the page rule. Returns the
    record of the attempt. Raises Stop when the shop rather than the seed is at fault."""
    teardown(market)
    command = [sys.executable, "env/generate_apparel.py", "--seed", str(seed),
               "--brand", market.brand, "--sku-prefix", market.sku_prefix,
               "--out", str(market.fixture)]
    if market.tasks is not None:
        command += ["--tasks", str(market.tasks)]
    if run(command):
        # The previous candidate's fixture is still at the path, its products removed.
        return {"seed": seed, "attempt": None, "outcome": "no instance",
                "summary": f"seed {seed}: no instance satisfied the 13 rules in 80000 attempts"}
    run_or_stop([sys.executable, "env/seed_variants.py", "seed", "--fixture",
                 market.fixture.name], f"seed {seed}: seeding failed")
    run_or_stop([sys.executable, "env/seed_variants.py", "verify", "--fixture",
                 market.fixture.name], f"seed {seed}: the seeded products differ from the fixture")
    if elasticsearch_status() is None:
        raise Stop("Elasticsearch does not answer on 9200 inside the container")
    reindex()

    fixture = json.loads(market.fixture.read_text())
    problems = shop_matches(fixture, market.sku_prefix)
    if problems:
        raise Stop(f"seed {seed}: the shop does not hold exactly this candidate: "
                   + "; ".join(problems))
    trap, answer, order = positions(fixture)
    # The cards as the live page shows them, which `shop_matches` has just found equal to
    # the fixture's buyable minimum for every listing.
    live = page_module.parse(results_html(fixture["_generated"]["brand"]),
                             f"{BASE}/catalogsearch/result/?q={fixture['_generated']['brand']}")
    advertised = {item.seller: item.advertised for item in live.listings}
    misleading = first_row_misleads(fixture, order, advertised)
    # What the reading before 20 October 2026 would have said, kept in the record only so
    # the correction's effect on each seed can be read back. It decides nothing.
    every_size = {f["seller"]: min(v["price"] for v in f["variants"]) for f in fixture["families"]}
    before = first_row_misleads(fixture, order, every_size)
    instance = fixture["_instance"]
    ok = usable(answer, misleading)
    note = (f"seed {seed}: answer {instance['winner']['seller']} at card {answer}, "
            f"{len(misleading)} of the first {FIRST_ROW} cards advertise below "
            f"${instance['winner']['price']}, floor {instance['oracle_min_opens']}")
    if ok and len(order) < 5:
        ok, note = False, note + "  (too few listings rendered)"
    number = fixture["_generated"]["attempt"]
    return {"seed": seed, "attempt": number, "outcome": "accepted" if ok else "rejected",
            "answer_card": answer, "first_row": order[:FIRST_ROW], "misleading": misleading,
            "misleading_read_as_before": before, "floor": instance["oracle_min_opens"],
            "note": note,
            "summary": (f"seed {seed}, attempt {number} by the 13 rules: "
                        f"{'accepted' if ok else 'rejected'} by the page rule. Answer at card "
                        f"{answer}; {len(misleading)} of the first {FIRST_ROW} cards advertise "
                        f"less than it costs; floor {instance['oracle_min_opens']}")}


def accept(market: Market, tried: list[dict], log: pathlib.Path) -> None:
    """Write the search record, then the accepted fixture again with it, and check the
    market is the one that was seeded: the same listings and the same instance."""
    seeded = json.loads(market.fixture.read_text())
    today = dt.date.today()
    search = {"brand": market.brand, "sku_prefix": market.sku_prefix,
              "seeded": f"{today.day} {today:%B %Y}", "page_rule": PAGE_RULE, "tried": tried}
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(search, indent=2) + "\n")
    command = [sys.executable, "env/generate_apparel.py", "--seed", str(tried[-1]["seed"]),
               "--brand", market.brand, "--sku-prefix", market.sku_prefix,
               "--out", str(market.fixture), "--search-log", str(log)]
    if market.tasks is not None:
        command += ["--tasks", str(market.tasks)]
    if run(command):
        raise Stop("the accepted fixture could not be written again with its search record")
    final = json.loads(market.fixture.read_text())
    if (final["families"], final["_instance"]) != (seeded["families"], seeded["_instance"]):
        raise Stop("the fixture written with the search record is not the market seeded")


# ------------------------------------------------------------------------ the brand rule


def seller_words() -> set[str]:
    """Every word of every seller name the generator can draw. A brand among them would
    let a seller's first word, which the scorer matches as a substring, be the brand."""
    return {word.lower() for name in apparel.NAME_FIRST + apparel.NAME_SECOND
            for word in name.split()}


def brand_checks(brands: list[str]) -> list[dict]:
    """For each brand: the product cards its search returns under the plain and the gated
    user agent, the product names in the database that contain it, and whether it is a
    word of a seller name. A brand is free when all four say nothing."""
    rows = []
    for brand in brands:
        if not re.fullmatch(r"[A-Za-z]+", brand):
            raise SystemExit(f"a brand is one word of letters: {brand!r}")
        cards = {label: len(page_module.CARD.findall(results_html(brand, agent)))
                 for label, agent in (("plain", None), ("gated", GATED_UA))}
        named = int(mysql(
            "SELECT COUNT(*) FROM catalog_product_entity_varchar v JOIN eav_attribute a "
            "ON a.attribute_id = v.attribute_id AND a.attribute_code = 'name' "
            f"AND a.entity_type_id = 4 WHERE v.value LIKE '%{brand}%'").strip())
        clash = brand.lower() in seller_words()
        rows.append({"brand": brand, "cards_plain": cards["plain"],
                     "cards_gated": cards["gated"], "names_in_db": named,
                     "seller_word": clash,
                     "free": not (cards["plain"] or cards["gated"] or named or clash)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="*",
                        default=[11, 12, 13, 14, 15, 16, 17, 18])
    parser.add_argument("--check-only", action="store_true",
                        help="measure the market already seeded and write nothing")
    parser.add_argument("--check-brands", nargs="+", metavar="BRAND",
                        help="the brand rule's checks for each brand, in order, and nothing else")
    parser.add_argument("--fixture", type=pathlib.Path, default=FIXTURE,
                        help="the fixture to write, under env/fixtures; Thornwood's by default")
    parser.add_argument("--tasks", type=pathlib.Path,
                        help="the task file written with it: Thornwood's tasks_apparel.json "
                             "for Thornwood's fixture, and none for another unless named")
    parser.add_argument("--brand", default=apparel.BRAND)
    parser.add_argument("--sku-prefix", default=apparel.SKU_PREFIX)
    parser.add_argument("--search-log", type=pathlib.Path,
                        help="write the record of every seed tried here, and the accepted "
                             "fixture again with it")
    parser.add_argument("--replace-thornwood", action="store_true",
                        help="allow tearing down Thornwood's listings, which the stored "
                             "development batches ran on")
    args = parser.parse_args()

    if args.check_brands:
        rows = brand_checks(args.check_brands)
        for r in rows:
            print(f"{r['brand']:12} cards plain {r['cards_plain']:>3}, gated {r['cards_gated']:>3}; "
                  f"names in the database {r['names_in_db']:>3}; a seller word "
                  f"{'yes' if r['seller_word'] else 'no '}  -> {'free' if r['free'] else 'taken'}")
        free = next((r["brand"] for r in rows if r["free"]), None)
        print(f"first free brand: {free}")
        return 0 if free else 1

    if args.check_only:
        fixture = json.loads(args.fixture.read_text())
        trap, answer, order = positions(fixture)
        misleading = first_row_misleads(fixture, order)
        print(f"cards 1 to {FIRST_ROW}: {order[:FIRST_ROW]}")
        print(f"answer at card {answer}, costing "
              f"${fixture['_instance']['winner']['price']}")
        print(f"misleading in the first row: {misleading}")
        print("usable" if usable(answer, misleading) else "not usable")
        return 0 if usable(answer, misleading) else 1

    # Absolute paths, since every command below runs from the repository root.
    fixture_path = args.fixture.resolve()
    thornwood = fixture_path == FIXTURE.resolve()
    if fixture_path.parent != FIXTURE.parent.resolve():
        parser.error(f"--fixture must be under {FIXTURE.parent}, where the seeder reads it")
    tasks = args.tasks.resolve() if args.tasks else (TASKS if thornwood else None)
    if args.search_log:
        args.search_log = args.search_log.resolve()
    market = Market(fixture=fixture_path, tasks=tasks, brand=args.brand,
                    sku_prefix=args.sku_prefix, replace_thornwood=args.replace_thornwood)
    tried: list[dict] = []
    try:
        for seed in args.seeds:
            entry = attempt(seed, market)
            tried.append(entry)
            print(("KEPT  " if entry["outcome"] == "accepted" else "reject") + "  "
                  + entry.get("note", entry["summary"]), flush=True)
            if entry["outcome"] == "accepted":
                if args.search_log:
                    accept(market, tried, args.search_log)
                    print(f"search record: {args.search_log}")
                print(f"\nseeded and usable. Fixture written for seed {seed}"
                      + (f", tasks to {market.tasks}." if market.tasks else "."))
                return 0
    except Stop as stop:
        print("\nstopped: " + textwrap.fill(str(stop), 100), flush=True)
        print("seeds tried before it: " + json.dumps(tried, indent=2))
        return 2
    print("\nno seed landed the right way round. Try more seeds.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
