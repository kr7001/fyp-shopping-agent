#!/usr/bin/env python3
"""Seed A+ markets, one seed at a time, until one holds every rule on the live results pages.

`generate_aplus.py` draws a market whose predicted results pages already hold the page rules,
so a seed is normally accepted at its first live check. This seeds it and reads the pages the
shop actually serves. Each attempt removes the previous candidate, checks that no product of
it survives, seeds the new one, reindexes, checks that the shop holds exactly it and that its
two results pages list exactly its listings, compares the live order with the predicted one,
and applies the page rules to the live order. A live order the model did not predict stops
the search: the model is then wrong for this shop, and selecting seeds by it would select by
a wrong model. `--search-log` writes the record of every seed tried, which the accepted
fixture carries.

The brand rule is the first protocol's (docs/content/claim-protocol.md, "Brand rule"): the
shop's search returns nothing for the brand, no product's name holds it, and it is no word of
any seller name the generator can draw. Here also no seller's first word is inside it, since
the scorer matches a first word as a substring (`generate_aplus.names_distinct`). How the
shop's analyzer reads it, as one form or two, is measured at the start of a search and passed
to the generator (`--brand-forms`), whose page rules and recorded order are then the brand's
own, and the live order must be one the model predicts for that form.

Development uses its own brand, prefix and fixture, and seeds 900 to 999 only. The claim
(`--claim`) refuses until docs/content/claim2-protocol.md no longer says DRAFT, refuses
development's prefix and fixture, and tries seeds only in the order its record allows: 1000
first, each next one after a rejection, the same one again after a stop. Every attempt is
written to the record as it ends. Nothing here costs money, only time: a cycle is several
minutes, most of it reindexing.

    python3 env/pick_aplus_market.py --check-brands Larchmere Quenby
    python3 env/pick_aplus_market.py --brand <Brand> --sku-prefix IGR-DEV \\
        --fixture env/fixtures/aplus_dev.json --search-log env/manifests/aplus_dev-search.json \\
        --seeds 900 901 902
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

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import check_aplus_market as live  # noqa: E402  (the two results pages, read as the shop serves them)
import generate_aplus as aplus  # noqa: E402  (the rules, the pools, the predicted orders)
import pick_apparel_market as pick  # noqa: E402  (Stop, run_or_stop, reindex, mysql, shop_skus)
import seed_variants  # noqa: E402  (expand_skus, the seeder's own child SKUs)

# Every prefix an earlier market was seeded under, which an A+ market may never use or tear
# down: Thornwood, Ashcombe, Rivenhall, Calderwood, and the hand-written families.
EARLIER_PREFIXES = ("IGR-APP", "IGR-CLM", "IGR-RVN", "IGR-CAL", "IGR-WATER", "IGR-TEE",
                    "IGR-COFFEE")
MANIFESTS = HERE / "manifests"
# The seeding manifest of the attempt under way, so a stop after seeding can name it too.
SEEDING: dict = {"manifest": None}


@dataclasses.dataclass(frozen=True)
class Market:
    fixture: pathlib.Path
    brand: str
    sku_prefix: str
    tees: int = aplus.TEE_LISTINGS
    waters: int = aplus.WATER_LISTINGS
    claim: bool = False
    two_forms: bool = False         # how the shop's analyzer reads the brand, measured live


def versions() -> dict:
    """The code an attempt was made with, recorded in every attempt (task E, 22 October 2026),
    so a record spanning a change of rules says which rules each seed was held to."""
    return {"generator_version": aplus.VERSION, "search_order_version": aplus.search_order.VERSION}


def prefix_refused(prefix: str) -> str | None:
    """Why an A+ market may not use this prefix, or None: an earlier market's, or one whose
    SKUs an earlier market's would match (`shop_skus` reads `prefix-%`)."""
    if not re.fullmatch(r"IGR-[A-Z0-9]+", prefix):
        return f"not a prefix of the form IGR-XXX: {prefix!r}"
    for earlier in EARLIER_PREFIXES:
        if prefix == earlier or earlier.startswith(prefix + "-") or prefix.startswith(earlier + "-"):
            return f"{prefix} is or overlaps {earlier}, an earlier market's"
    return None


def teardown_refused(market: Market, fixture: dict) -> str | None:
    """Why the products of the fixture now at the market's path may not be removed, or None:
    it is not an A+ fixture, or not this brand's and prefix's, or its listings are not all the
    prefix's. Kept apart from `teardown` so a test can ask it without anything being deleted."""
    generated = fixture.get("_generated") or {}
    if generated.get("generator") != "env/generate_aplus.py":
        return "it is not an A+ market's fixture"
    if (generated.get("brand"), generated.get("sku_prefix")) != (market.brand, market.sku_prefix):
        return (f"it is the {generated.get('brand')} {generated.get('sku_prefix')} market, not "
                f"{market.brand} {market.sku_prefix}")
    if not all(f["parent_sku"].startswith(market.sku_prefix + "-") for f in fixture["families"]):
        return f"its listings are not all {market.sku_prefix}"
    return prefix_refused(market.sku_prefix)


def teardown(market: Market) -> str:
    if not market.fixture.exists():
        return "no earlier candidate to remove"
    fixture = json.loads(market.fixture.read_text())
    refused = teardown_refused(market, fixture)
    if refused:
        raise SystemExit(f"refusing to tear down {market.fixture.name}: {refused}")
    pick.run_or_stop([sys.executable, "env/seed_variants.py", "teardown", "--fixture",
                      market.fixture.name, "--yes"], f"teardown of {market.fixture.name} failed")
    return f"removed the {len(fixture['families'])} listings of {market.fixture.name}"


def generate_command(seed: int, market: Market, log: pathlib.Path | None = None) -> list[str]:
    """The generator's command for a seed. The claim's always names its record, which decides
    whether the seed may be drawn (`generate_aplus.claim_record_problem`)."""
    command = [sys.executable, "env/generate_aplus.py", "--seed", str(seed), "--brand",
               market.brand, "--brand-forms", "2" if market.two_forms else "1", "--sku-prefix",
               market.sku_prefix, "--tees", str(market.tees), "--waters", str(market.waters),
               "--out", str(market.fixture)]
    if market.claim:
        command += ["--claim", "--search-log", str(log)]
    return command


def fixture_skus(fixture: dict) -> set[str]:
    """Every SKU the seeder writes for a fixture, by the seeder's own rule. Not
    `pick_apparel_market.fixture_skus`, which upper-cases the option as it stands and so names
    a pack "2 x 9.5L" child "...-2 X 9.5L" where the seeder writes "...-2-X-9-5L" (found
    22 October 2026; right for sizes, which have no spaces)."""
    expanded = seed_variants.expand_skus(json.loads(json.dumps(fixture)))
    return {f["parent_sku"] for f in expanded["families"]} | {
        v["sku"] for f in expanded["families"] for v in f["variants"]}


def live_problems(fixture: dict, sku_prefix: str) -> tuple[list[str], list[str]]:
    """What is wrong between the shop and the fixture after seeding, and the live order: SKUs
    left over or missing, results pages that are not exactly the market's two, or the two user
    agents listing it in different orders."""
    problems = []
    want, have = fixture_skus(fixture), pick.shop_skus(sku_prefix)
    if have != want:
        problems.append(f"SKUs left over {sorted(have - want)}, missing {sorted(want - have)}")
    orders = {}
    for label, agent in (("gated", live.GATED_UA), ("plain", live.PLAIN_UA)):
        pages = live.results_pages(fixture["_generated"]["brand"], agent)
        problems += [f"{label}: {p}" for p in live.pages_problems(pages, fixture)]
        orders[label] = live.live_order(pages, fixture)
    if orders["gated"] != orders["plain"]:
        problems.append("the plain and the gated results pages list the listings in different orders")
    return problems, orders["gated"]


def order_match(families: list[dict], order: list[str], two_forms: bool) -> tuple[str | None, str | None]:
    """Which of the model's orders for the brand's own form the live order is, by scenario
    label, or why it is none: an order the model gives only for the other form means the form
    measured is wrong; one it gives for neither, that the model is wrong for this shop. Kept
    apart from `attempt` so a test can ask it without the shop."""
    predicted = aplus.predicted_orders(families, two_forms)
    matched = next((label for label, o in predicted.items() if o == order), None)
    if matched is not None:
        return matched, None
    other = aplus.predicted_orders(families, not two_forms)
    wrong_form = next((label for label, o in other.items() if o == order), None)
    if wrong_form:
        return None, (f"the live order is the model's for the other form ({wrong_form}), not the "
                      f"brand's, so the form measured is wrong")
    return None, "the live order is none the model predicts, so the order model is wrong for this shop"


def attempt(seed: int, market: Market, log: pathlib.Path | None = None) -> dict:
    """One seed: remove the previous candidate, draw this one, seed it, reindex, check the
    shop holds exactly it, and read the live pages. Returns the record of the attempt; raises
    Stop when the shop or the model, not the seed, is at fault."""
    SEEDING["manifest"] = None
    teardown(market)
    if pick.run(generate_command(seed, market, log)):
        return {"seed": seed, **versions(), "outcome": "no instance",
                "summary": f"seed {seed}: no market satisfied every rule"}
    before = {p.name for p in MANIFESTS.glob("*-gated-pricing.json")}
    pick.run_or_stop([sys.executable, "env/seed_variants.py", "seed", "--fixture",
                      market.fixture.name], f"seed {seed}: seeding failed")
    # The manifest the seeder wrote for this attempt, named in its record (and in a stop's).
    written = sorted({p.name for p in MANIFESTS.glob("*-gated-pricing.json")} - before)
    SEEDING["manifest"] = written[-1] if written else None
    pick.run_or_stop([sys.executable, "env/seed_variants.py", "verify", "--fixture",
                      market.fixture.name], f"seed {seed}: the seeded products differ from the fixture")
    if pick.elasticsearch_status() is None:
        raise pick.Stop("Elasticsearch does not answer on 9200 inside the container")
    pick.reindex()
    fixture = json.loads(market.fixture.read_text())
    problems, order = live_problems(fixture, market.sku_prefix)
    if problems:
        raise pick.Stop(f"seed {seed}: the shop does not hold exactly this candidate: "
                        + "; ".join(problems))
    matched, problem = order_match(fixture["families"], order, market.two_forms)
    if problem:
        raise pick.Stop(f"seed {seed}: {problem}. Live: {order}")
    broken = aplus.page_problems(fixture["families"], order)
    attempts = fixture["_generated"]["attempts"]
    cards = {question: [order.index(l["parent_sku"]) + 1 for l in listings]
             for question, (listings, _) in aplus.answer_listings(aplus.keys(fixture["families"])).items()}
    ok = not broken
    # The live order itself is kept, so the order model can be checked against it offline:
    # this market's first seed is the case that showed the model wrong (`search_order.py`).
    return {"seed": seed, **versions(), "brand_forms": 2 if market.two_forms else 1,
            "attempts": attempts, "outcome": "accepted" if ok else "rejected",
            "seeding_manifest": SEEDING["manifest"],
            "live_order": order, "live_order_is": matched, "broken": broken, "answer_cards": cards,
            "summary": (f"seed {seed} (generator v{aplus.VERSION}), tee draw {attempts['tee']} and "
                        f"water draw {attempts['water']} by every rule on the predicted pages: "
                        f"{'accepted' if ok else 'rejected'} on the live pages, whose order is the "
                        f"predicted one ({matched})"
                        + (f"; broken there: {', '.join(broken)}" if broken else ""))}


def earlier_tries(market: Market, log: pathlib.Path | None) -> list[dict]:
    """The seeds a search record already holds for this market, so a search continued in a
    later run records every seed tried, in order, stops included. Refused when the record is
    another market's, or already ends with a seed accepted under the code that runs now. A
    development record accepted under an earlier generator or order model continues, since a
    change of rules draws the market again (task E, 22 October 2026); a claim record never
    does once it accepts."""
    if log is None or not log.exists():
        return []
    search = json.loads(log.read_text())
    if (search.get("brand"), search.get("sku_prefix")) != (market.brand, market.sku_prefix):
        raise SystemExit(f"{log.name} is the search for {search.get('brand')} "
                         f"{search.get('sku_prefix')}, not {market.brand} {market.sku_prefix}")
    tried = search.get("tried", [])
    last = tried[-1] if tried else {}
    now = versions()
    if last.get("outcome") == "accepted" and (
            market.claim or all(last.get(key) == value for key, value in now.items())):
        raise SystemExit(f"{log.name} already ends with seed {last['seed']} accepted")
    return tried


def write_log(market: Market, tried: list[dict], log: pathlib.Path) -> None:
    today = dt.date.today()
    search = {"brand": market.brand, "sku_prefix": market.sku_prefix,
              "seeded": f"{today.day} {today:%B %Y}", "tried": tried}
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(search, indent=2) + "\n")


def accept(market: Market, tried: list[dict], log: pathlib.Path) -> None:
    """Write the search record, then the accepted fixture again with it, and check that the
    market is the one that was seeded."""
    seeded = json.loads(market.fixture.read_text())
    write_log(market, tried, log)
    command = generate_command(tried[-1]["seed"], market, log)
    if not market.claim:
        command += ["--search-log", str(log)]
    if pick.run(command):
        raise pick.Stop("the accepted fixture could not be written again with its search record")
    final = json.loads(market.fixture.read_text())
    if (final["families"], final["_instance"]) != (seeded["families"], seeded["_instance"]):
        raise pick.Stop("the fixture written with the search record is not the market seeded")


# ------------------------------------------------------------------------ the brand rule


def seller_words() -> set[str]:
    """Every word of every seller name the generator can draw, lowercased."""
    names = aplus.TEE_FIRST + aplus.TEE_SECOND + aplus.WATER_FIRST + aplus.WATER_SECOND
    return {word.lower() for name in names for word in name.split()}


def first_word_inside(brand: str) -> list[str]:
    """The seller first words found inside the brand, which a scorer would then match in
    every answer that names the brand."""
    return [w for w in aplus.TEE_FIRST + aplus.WATER_FIRST if w.lower() in brand.lower()]


def analyzer_forms(brand: str) -> int:
    """How many forms the shop's analyzer gives the brand: one when its stem is itself, two
    when the stem differs (Ashcombe, Rivenhall). Read with the index's own analyzer, through
    the alias the store's index keeps across reindexes (`magento2_product_1`)."""
    body = json.dumps({"field": "name", "text": brand})
    out = subprocess.run(["docker", "exec", pick.CONTAINER, "curl", "-s", "-m", "20", "-H",
                          "Content-Type: application/json",
                          "http://localhost:9200/magento2_product_1/_analyze", "-d", body],
                         capture_output=True, text=True)
    try:
        return len({t["token"] for t in json.loads(out.stdout)["tokens"]})
    except (json.JSONDecodeError, KeyError):
        return 0


def brand_checks(brands: list[str]) -> list[dict]:
    rows = []
    for brand in brands:
        if not re.fullmatch(r"[A-Za-z]+", brand):
            raise SystemExit(f"a brand is one word of letters: {brand!r}")
        cards = {label: len(live.page_module.CARD.findall(live.fetch(live.results_url(brand, 1), agent)))
                 for label, agent in live.AGENTS.items()}
        named = int(pick.mysql(
            "SELECT COUNT(*) FROM catalog_product_entity_varchar v JOIN eav_attribute a "
            "ON a.attribute_id = v.attribute_id AND a.attribute_code = 'name' "
            f"AND a.entity_type_id = 4 WHERE v.value LIKE '%{brand}%'").strip())
        clash = brand.lower() in seller_words()
        inside = first_word_inside(brand)
        rows.append({"brand": brand, "cards_plain": cards["plain"], "cards_gated": cards["gated"],
                     "names_in_db": named, "seller_word": clash, "first_words_inside": inside,
                     "forms": analyzer_forms(brand),
                     "free": not (cards["plain"] or cards["gated"] or named or clash or inside)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-brands", nargs="+", metavar="BRAND",
                        help="the brand rule's checks for each brand, in order, and nothing else")
    parser.add_argument("--brand")
    parser.add_argument("--sku-prefix", default="IGR-DEV")
    parser.add_argument("--fixture", type=pathlib.Path,
                        help="the fixture to write, under env/fixtures")
    parser.add_argument("--tees", type=int, default=aplus.TEE_LISTINGS)
    parser.add_argument("--waters", type=int, default=aplus.WATER_LISTINGS)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--search-log", type=pathlib.Path)
    parser.add_argument("--claim", action="store_true",
                        help="the claim market's search, from seed 1000, only after the protocol is final")
    args = parser.parse_args()

    if args.check_brands:
        rows = brand_checks(args.check_brands)
        for r in rows:
            print(f"{r['brand']:12} cards plain {r['cards_plain']:>3}, gated {r['cards_gated']:>3}; "
                  f"names in the database {r['names_in_db']:>3}; a seller word "
                  f"{'yes' if r['seller_word'] else 'no '}; first words inside it "
                  f"{r['first_words_inside'] or 'none'}; analyzer forms {r['forms']}  -> "
                  f"{'free' if r['free'] else 'taken'}")
        free = next((r["brand"] for r in rows if r["free"]), None)
        print(f"first free brand: {free}")
        return 0 if free else 1

    if not (args.brand and args.fixture and args.seeds):
        parser.error("name --brand, --fixture and --seeds, or ask for --check-brands")
    fixture_path = args.fixture.resolve()
    if fixture_path.parent != (HERE / "fixtures").resolve():
        parser.error("--fixture must be under env/fixtures, where the seeder reads it")
    if fixture_path.name in aplus.EARLIER:
        parser.error(f"{fixture_path.name} is an earlier market's fixture")
    refused = prefix_refused(args.sku_prefix)
    if refused:
        parser.error(refused)
    for seed in args.seeds:
        why = aplus.refused(seed, args.claim, fixture_path, args.sku_prefix)
        if why:
            parser.error(why)
    if args.claim and args.search_log is None:
        parser.error("--claim needs --search-log: the claim's record decides which seed comes next")
    # The brand's analyzer form, measured here and passed to the generator, so the page rules
    # and the recorded order are the brand's own (task E).
    forms = analyzer_forms(args.brand)
    if forms not in (1, 2):
        parser.error(f"the shop's analyzer gave {args.brand} {forms} forms; it is checked as 1 or 2")
    market = Market(fixture=fixture_path, brand=args.brand, sku_prefix=args.sku_prefix,
                    tees=args.tees, waters=args.waters, claim=args.claim, two_forms=forms == 2)
    log = args.search_log.resolve() if args.search_log else None
    tried = earlier_tries(market, log)
    seed = None
    try:
        for seed in args.seeds:
            # The claim tries seeds only in the record's order: the first from 1000 that passes.
            problem = aplus.claim_record_problem(tried, seed, False) if market.claim else None
            if problem:
                raise SystemExit(f"refusing: {problem}")
            entry = attempt(seed, market, log)
            tried.append(entry)
            # Written after every attempt, so the record survives an interruption, and the
            # generator reads the claim's order from it.
            if log:
                write_log(market, tried, log)
            print(("KEPT  " if entry["outcome"] == "accepted" else "reject") + "  "
                  + entry["summary"], flush=True)
            if entry["outcome"] == "accepted":
                if log:
                    accept(market, tried, log)
                    print(f"search record: {log}")
                print(f"\nseeded and usable: seed {seed}, fixture {market.fixture.name}.")
                return 0
    except pick.Stop as stop:
        # A stop is a seed tried too: recorded, so the next run continues the same record.
        tried.append({"seed": seed, **versions(), "outcome": "stopped",
                      "seeding_manifest": SEEDING["manifest"],
                      "summary": f"seed {seed}: stopped, {stop}"[:600]})
        if log:
            write_log(market, tried, log)
        print("\nstopped: " + textwrap.fill(str(stop), 100), flush=True)
        print("seeds tried: " + json.dumps([t["summary"] for t in tried], indent=2))
        return 2
    print("\nno seed held every rule on the live pages. Try more seeds.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
