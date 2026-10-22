#!/usr/bin/env python3
"""Generate an A+ market: tee and bottled water listings under one brand, so that the brand's
search runs to a second results page and mixes the two products (docs/content/claim2-protocol.md,
"The market (A+)").

The first claim market sold one product on one results page. This one asks whether the block
still holds at scale: about forty listings, so the search spans two pages at the shop's page
size of 36, and two products, so the listings a question is about have to be picked out of
the page rather than taken as the whole of it. Development uses its own brand and seeds 900
to 999. The claim market is drawn by this same code from seed 1000, under the brand the final
protocol names, and only after the protocol is final, which `--claim` guards.

**What is the same as the markets before it.**
- Each tee listing is `generate_apparel.build_listing`: its price model, its three availability
  states, its probabilities. The tees are held to its 13 rules, unchanged.
- Each water listing is priced by `generate_catalogue`'s model, a per-litre rate per seller and
  a factor per pack, and the water is held to its 8 rules.
- Rejection sampling against rules checked before the market is used, from a string seed so
  that consecutive seeds never share a stream (`generate_apparel.generate`).

**What is new, and why.**
- *Water has a third availability state.* The water generator had none: every pack it listed
  could be bought, and only the 2 x 9.5L could be missing. The protocol asks for each variant
  absent, sold out or buyable, so every pack here takes the tee generator's probabilities
  (`P_ABSENT`, `P_SOLD_OUT`). The water rules are read over what can be bought, which is what
  the questions ask about: the winner is the cheapest 2 x 9.5L that can be bought, the card is
  the cheapest pack that can be bought (what Magento prints, `generate_apparel.from_price`),
  and the best price per litre is over packs that can be bought.
- *The protocol's four rules* (`MARKET_RULES`), and the conditions every key needs to be a
  single answer.
- *Where the answers render.* The rules on the page (`PAGE_RULES`) are applied to the order
  `search_order.py` predicts, under every one of its scenarios, before the market is seeded.
  The live page is checked after seeding (`pick_aplus_market.py`) and is what counts.
- *Titles.* The shop ranks a brand's listings by how often the brand occurs in a listing's
  names against how long they are (`search_order.py`), and each pack label adds three words
  to a child's name where a size adds one. Under the titles the earlier markets used
  ("Heavyweight Cotton Tee", "Still Spring Water, Multipack"), at one seller-name length every
  water listing scores below every tee listing, at every option count and under either reading
  of the brand, and the earlier name lists give nine sellers in ten a two-word name, so the
  page would list nearly all the tees and then all the water, which the protocol rules out
  (`tests/test_aplus_market.py`). Found with the order model on 22 October 2026, before any
  A+ seed. So each listing is titled with one of three phrasings of its product, as sellers
  title the same product differently, the water's shorter than Rivenhall's, and seller names
  run from two words to four, as shops' names do. Which listings mix on the page is then
  left to the draw, and the page rules hold the draw to it.
- *Names.* The scorer matches a seller by its first word, as a lowercase substring of the
  answer, so every first word is distinct and is found in no other seller's name, the brand,
  a product phrasing, an option label or a question (`names_distinct`). That is the first
  protocol's brand rule (the "Kelsall" problem) applied to every word a scorer reads.

    python3 env/generate_aplus.py --seed 900 --brand <Brand> --report
    python3 env/generate_aplus.py --seed 900 --brand <Brand> --sku-prefix IGR-DEV \\
        --out env/fixtures/aplus_dev.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import generate_apparel as apparel  # noqa: E402  (the tee model, its 13 rules, from_price, price_for)
import generate_catalogue as water  # noqa: E402  (the water price model: PACKS, RATE_RANGE, litres)
import search_order  # noqa: E402  (the predicted results order)

MARKET = "aplus"
# Bumped whenever a change would draw a different market from the same seed, or judge one
# differently. Recorded in every fixture's `_generated`.
VERSION = 1

TEE, WATER = "tee", "water"
TEE_TARGET = apparel.TARGET_SIZE          # "M"
WATER_TARGET = water.TARGET_OPTION        # "2 x 9.5L"
TEE_OPTIONS = list(apparel.SIZES)
WATER_OPTIONS = [p["option"] for p in water.PACKS]

# The shop's results page size, read off the local shop on 22 October 2026 ("Items 1 - 36 of
# 16678" for q=water, a next link to p=2). No setting is changed to get it.
PAGE_SIZE = 36
# The first screen, as the first protocol's page rule took it: the first row of four cards
# (`pick_apparel_market.FIRST_ROW`, checked equal by the tests).
FIRST_SCREEN = 4
# "About 20" of each (the protocol). 21 and 21 make 42, so page 2 holds six listings.
TEE_LISTINGS = 21
WATER_LISTINGS = 21

# How each seller titles its listing, drawn per listing, as sellers on a marketplace title the
# same product differently. Every tee title holds "Tee" and no water word, and every water
# title holds "Water" and no tee word, so the product a listing sells is in its title. The
# first tee phrasing is Thornwood's and Ashcombe's; every water phrasing is shorter than
# Rivenhall's "Still Spring Water, Multipack" (see the module docstring for why).
TEE_PHRASES = ("Heavyweight Cotton Tee", "Heavyweight Cotton Tee, Unisex",
               "Heavyweight Cotton Crew Neck Tee")
WATER_PHRASES = ("Spring Water", "Still Spring Water", "Natural Spring Water, Still")

# The availability model, the tee generator's, for both products.
P_ABSENT = apparel.P_SIZE_MISSING
P_SOLD_OUT = apparel.P_SIZE_SOLD_OUT

# Seller names. The first words of the two earlier name lists, less "Cellar", which is inside
# "Cellars", and more of the same kind so that each product has enough. A first word belongs
# to one product, so no seller sells both. Second parts run from one word to three, four of
# each, so a whole seller name runs from two words to four.
TEE_FIRST = apparel.NAME_FIRST + ("Abbotsley", "Bexhill", "Carnforth", "Dovercourt",
                                  "Everleigh", "Foxcombe", "Gisburn", "Thirsk")
WATER_FIRST = tuple(n for n in water.NAME_FIRST if n != "Cellar") + (
    "Ambleside", "Brockwell", "Crowhurst", "Dalston", "Elstead", "Fordwich", "Grantley",
    "Holbeck", "Ingleton")
TEE_SECOND = ("Outfitters", "Apparel", "Threads", "Garments",
              "Clothing Co", "Garment Works", "Textile Company", "Uniform Supply",
              "Apparel Official Store", "Workwear Supply Co", "Clothing Company Ltd",
              "Textiles Official Store")
WATER_SECOND = ("Direct", "Provisions", "Wholesale", "Merchants",
                "Supply Co", "Trading Company", "Beverage Supply", "Pantry Stores",
                "Drinks Official Store", "Beverage Supply Co", "Grocery Company Ltd",
                "Provisions Official Store")

# The questions, the protocol's templates word for word (docs/content/claim2-protocol.md,
# "Questions"). The market's rules are written per question, so they live with the market,
# and `generate_aplus_tasks.py` writes them into a task file with their keys.
TEMPLATES = {
    "tee-headline": (TEE, "Of the {brand} tee listings shown, which one advertises the lowest "
                          "price on the results page, and what is that price?"),
    "tee-target-price": (TEE, "What is the lowest price anyone charges for size M of the {brand} "
                              "tee, among those that can actually be bought?"),
    "tee-cheapest-target": (TEE, "Across the {brand} tee listings, which seller is cheapest for "
                                 "size M, and what is that price? Only count a listing that can "
                                 "actually supply that size."),
    "tee-all-stocked": (TEE, "Does every {brand} tee listing offer size M? Answer yes or no."),
    "tee-count-stocked": (TEE, "How many of the {brand} tee listings offer size M?"),
    "tee-count-buyable": (TEE, "How many of the {brand} tee listings have size M in stock and "
                               "available to buy right now?"),
    "tee-exists-under": (TEE, "Is there any {brand} tee listing with size M available to buy "
                              "for under ${limit}? Answer yes or no, and name the seller if yes."),
    "tee-top-3": (TEE, "Which three sellers are cheapest for size M of the {brand} tee among "
                       "listings that can actually supply it, and at what prices?"),
    "water-target-price": (WATER, "What is the lowest price anyone charges for the 2 x 9.5L pack "
                                  "of {brand} water, among those that can actually be bought?"),
    "water-cheapest-target": (WATER, "Across the {brand} water listings, which seller is cheapest "
                                     "for the 2 x 9.5L pack, and what is that price? Only count a "
                                     "listing that can actually supply that pack."),
    "water-all-stocked": (WATER, "Does every {brand} water listing stock the 2 x 9.5L pack? "
                                 "Answer yes or no."),
    "water-count-buyable": (WATER, "How many of the {brand} water listings have the 2 x 9.5L pack "
                                   "in stock and available to buy right now?"),
    "water-best-per-litre": (WATER, "Across all the {brand} water listings and all their pack "
                                    "sizes, which seller offers the lowest price per litre among "
                                    "packs that can actually be bought?"),
    "decline-delivery": (TEE, "Which {brand} seller delivers fastest for size M of the tee?"),
    "decline-taste": (WATER, "Which {brand} water tastes best?"),
}
# The questions whose key names a price, and so the ones the first-screen rule is about. The
# counting and "every listing" questions have no price for a card to undercut.
PRICE_QUESTIONS = ("tee-target-price", "tee-cheapest-target", "tee-exists-under", "tee-top-3",
                   "water-target-price", "water-cheapest-target", "water-best-per-litre")
TOP_K = 3

MARKET_RULES = """The A+ market's rules, on top of the tee generator's 13 and the water generator's 8.

The protocol's four (docs/content/claim2-protocol.md, "Acceptance rules"):

1. first_screen_misleads  for each question whose key names a price, every listing the key
                          names renders outside the first screen, and a listing of the same
                          product on the first screen advertises less than the answer costs,
                          so an answer read off the first screen's cards is wrong. What the
                          answer costs: the winner's price for target-price and
                          cheapest-target, the limit for exists-under, the dearest of the
                          three for top-3 (and the undercutting card is not one of them), the
                          winning pack's price for best-per-litre. A page rule
2. answer_on_page_2       a listing one of those keys names is on page 2, so a bound computed
                          over page 1 alone stops too early. A page rule
3. readings_differ        size M is listed but sold out on at least one tee listing, and the
                          2 x 9.5L on at least one water listing, so the menu and the buyable
                          readings of "offer" and "stock" count different listings
4. per_litre_not_target   the best price per litre among packs that can be bought is not at the
                          cheapest 2 x 9.5L that can be bought

The market's shape (the protocol's "The market (A+)"):

5. two_pages              more than one page of listings and no more than two
6. interleaved            both products on the first screen and both on page 2, so neither
                          product is one block and every question about either product needs
                          both pages. A page rule
7. names_distinct         every seller's first word is distinct, and is inside no other
                          seller's name, the brand, a product phrasing, an option label or a
                          question template; and no seller name holds a word of a product
                          phrasing

What every key needs to be one answer, refused rather than guessed:

8. headline_unique        one tee listing advertises the lowest tee price
9. limit_separates        the exists-under limit (`exists_limit`) leaves exactly one listing
                          that can sell size M under it, and no buyable size M sits on it
10. top_3_unique          the fourth cheapest buyable size M costs more than the third
11. per_litre_unique      one listing has the lowest price per litre

A page rule is applied to the order `search_order.py` predicts, under every one of its
scenarios, when the market is drawn, and to the live results pages after it is seeded."""

PAGE_RULES = ("interleaved", "first_screen_misleads", "answer_on_page_2")


def money(value: float) -> float:
    return round(value + 1e-9, 2)


# ---------------------------------------------------------------------------
# Drawing listings


def seller_names(firsts: tuple[str, ...], seconds: tuple[str, ...], count: int,
                 rng: random.Random) -> list[str]:
    if count > len(firsts):
        raise SystemExit(f"only {len(firsts)} distinct seller first words available")
    pool = list(firsts)
    rng.shuffle(pool)
    return [f"{first} {rng.choice(seconds)}" for first in pool[:count]]


def build_tee(seller: str, index: int, rng: random.Random, brand: str) -> dict:
    """One tee listing, exactly as the tee generator draws it. Until the market's catalogue
    order is drawn (`catalogue`) it carries a provisional SKU, TEE-NN, distinct within the
    draw, because the tee rules tell listings apart by SKU."""
    listing = apparel.build_listing(seller, index, rng, brand, sku_prefix="TEE")
    # The title is drawn after everything the tee generator draws, so its draws are its own.
    listing["name"] = f"{brand} {rng.choice(TEE_PHRASES)} - {seller}"
    listing["product"] = TEE
    return listing


def build_water(seller: str, index: int, rng: random.Random, brand: str) -> dict:
    """One water listing: the water generator's prices, the tee generator's availability. A
    provisional SKU, WATER-NN, until the catalogue order is drawn."""
    rate = rng.uniform(*water.RATE_RANGE)
    offered = [p for p in water.PACKS if rng.random() > P_ABSENT]
    if len(offered) < 2:                      # as the tee generator: one pack is not a market
        offered = list(water.PACKS[:2])
    variants = []
    for pack in offered:
        sold_out = rng.random() < P_SOLD_OUT
        variants.append({
            "option": pack["option"],
            "price": money(rate * water.litres(pack) * rng.uniform(*water.PACK_FACTOR_RANGE)),
            "qty": 0 if sold_out else rng.randint(25, 240),
            "units": pack["units"],
            "volume_ml": pack["volume_ml"],
        })
    if all(v["qty"] == 0 for v in variants):  # a shop with nothing to sell is not a market
        variants[0]["qty"] = rng.randint(25, 240)
    return {
        "key": f"water-{index:02d}", "parent_sku": f"WATER-{index:02d}",
        "name": f"{brand} {rng.choice(WATER_PHRASES)} - {seller}",
        "seller": seller,
        "attribute": "pack_size",
        "category_ids": [water.GROCERY_CATEGORY_ID],
        "gating": "price-and-stock-by-variant",
        "note": [],
        "variants": variants,
        "product": WATER,
    }


def catalogue(tees: list[dict], waters: list[dict], rng: random.Random,
              sku_prefix: str) -> list[dict]:
    """Both products in one catalogue, in an order drawn from the seed, numbered in that order.
    Interleaved so that a listing's number does not say which product it is."""
    slots = [TEE] * len(tees) + [WATER] * len(waters)
    rng.shuffle(slots)
    queues = {TEE: iter(tees), WATER: iter(waters)}
    families = []
    for index, product in enumerate(slots, 1):
        listing = next(queues[product])
        listing.update(key=f"{MARKET}-{index:02d}", parent_sku=f"{sku_prefix}-{index:02d}",
                       note=[f"Generated listing {index:02d}, {product}, seller "
                             f"{listing['seller']}."])
        families.append(listing)
    return families


# ---------------------------------------------------------------------------
# What a listing offers


def litres(variant: dict) -> float:
    return variant["units"] * variant["volume_ml"] / 1000


def best_rate(listing: dict) -> tuple[float, dict] | None:
    """The lowest price per litre among the packs this listing can sell now, and that pack."""
    able = [v for v in listing["variants"] if v["qty"] > 0]
    if not able:
        return None
    best = min(able, key=lambda v: v["price"] / litres(v))
    return round(best["price"] / litres(best), 4), best


def products(families: list[dict]) -> dict[str, list[dict]]:
    return {product: [f for f in families if f["product"] == product] for product in (TEE, WATER)}


def buyable(listings: list[dict], option: str) -> list[dict]:
    """The listings that can sell the option now, cheapest for it first."""
    able = [l for l in listings if apparel.buyable_price_for(l, option) is not None]
    return sorted(able, key=lambda l: apparel.buyable_price_for(l, option))


def exists_limit(tees: list[dict]) -> int | None:
    """The exists-under question's limit, by a rule written on 22 October 2026 before any A+
    market existed: the whole-dollar part of the midpoint between the two cheapest prices any
    tee listing can sell size M for. So exactly one listing, the cheapest, can sell it under
    the limit (`limit_separates` refuses a market where that fails), and the answer is a yes
    that names it. `first_screen_misleads` then puts that listing outside the first screen
    and a card under the limit on it, so the yes is not visible from the first screen. The
    same rule as `generate_apparel_v2_tasks.price_limits` for the claim market's yes limit."""
    able = buyable(tees, TEE_TARGET)
    if len(able) < 2:
        return None
    cents = [round(apparel.buyable_price_for(l, TEE_TARGET) * 100) for l in able[:2]]
    return sum(cents) // 200


# ---------------------------------------------------------------------------
# The water's facts and rules, over what can be bought


def water_measure(listings: list[dict]) -> dict:
    """The water's ground truth, as `generate_catalogue.measure` records it, read over what can
    be bought, with the three availability populations `generate_apparel.measure` records."""
    target = WATER_TARGET
    carriers = [l for l in listings if apparel.price_for(l, target) is not None]
    able = buyable(listings, target)
    sold_out = [l for l in carriers if apparel.buyable_price_for(l, target) is None]
    absent = [l for l in listings if apparel.price_for(l, target) is None]
    facts = {"target_option": target, "listings": len(listings),
             "listings_with_target": len(carriers), "listings_without_target": len(absent),
             "listings_target_buyable": len(able), "listings_target_sold_out": len(sold_out)}
    if not able:
        return {**facts, "winner": None}
    winner, best = able[0], apparel.buyable_price_for(able[0], target)
    runners = [apparel.buyable_price_for(l, target) for l in able]
    card = min(listings, key=apparel.from_price)
    must_open = [l for l in listings if apparel.from_price(l) <= best]
    rates = {l["parent_sku"]: best_rate(l) for l in listings}
    unit = min((l for l in listings if rates[l["parent_sku"]]), key=lambda l: rates[l["parent_sku"]][0])
    unit_rate, unit_pack = rates[unit["parent_sku"]]
    listed = min(carriers, key=lambda l: apparel.price_for(l, target))
    cheapest_sold_out = min(sold_out, key=lambda l: apparel.price_for(l, target)) if sold_out else None
    cheapest_absent = min(absent, key=apparel.from_price) if absent else None
    return {
        **facts,
        "winner": {"sku": winner["parent_sku"], "seller": winner["seller"], "price": best},
        "runner_up_price": runners[1] if len(runners) > 1 else None,
        "winning_margin": money(runners[1] - best) if len(runners) > 1 else None,
        "cheapest_listed": {"sku": listed["parent_sku"], "seller": listed["seller"],
                            "price": apparel.price_for(listed, target)},
        "cheapest_sold_out": None if cheapest_sold_out is None else {
            "sku": cheapest_sold_out["parent_sku"], "seller": cheapest_sold_out["seller"],
            "price": apparel.price_for(cheapest_sold_out, target)},
        "cheapest_card": {"sku": card["parent_sku"], "seller": card["seller"],
                          "from_price": apparel.from_price(card)},
        "card_probe_wrong": card["parent_sku"] != winner["parent_sku"],
        "cheapest_without_target": None if cheapest_absent is None else {
            "sku": cheapest_absent["parent_sku"], "seller": cheapest_absent["seller"],
            "from_price": apparel.from_price(cheapest_absent)},
        "best_per_litre": {"sku": unit["parent_sku"], "seller": unit["seller"],
                           "option": unit_pack["option"], "price": unit_pack["price"],
                           "price_per_litre": unit_rate},
        "unit_probe_wrong": unit["parent_sku"] != card["parent_sku"],
        "oracle_min_opens": len(must_open),
        "prunable_by_bound": len(listings) - len(must_open),
        "exhaustive_opens": len(listings),
        "bound_strength": round((len(listings) - len(must_open)) / len(listings), 3),
        "from_price_range": [money(min(apparel.from_price(l) for l in listings)),
                             money(max(apparel.from_price(l) for l in listings))],
        "target_price_range": [money(min(runners)), money(max(runners))],
    }


def water_check(listings: list[dict], facts: dict) -> list[str]:
    """`generate_catalogue.check`'s eight rules, each in its own words, read over what can be
    bought. Empty means usable."""
    if facts["winner"] is None:
        return ["unique_winner"]
    broken = []
    best = facts["winner"]["price"]
    prices = [apparel.buyable_price_for(l, WATER_TARGET) for l in buyable(listings, WATER_TARGET)]
    if prices.count(best) != 1:
        broken.append("unique_winner")
    if not facts["card_probe_wrong"]:
        broken.append("card_probe_wrong")
    if facts["prunable_by_bound"] < 3:
        broken.append("bound_is_useful")
    if facts["oracle_min_opens"] < 3:
        broken.append("bound_not_sufficient")
    if facts["listings_with_target"] == len(listings):
        broken.append("some_missing_target")
    if not facts["unit_probe_wrong"]:
        broken.append("unit_probe_wrong")
    if len({facts["winner"]["sku"], facts["cheapest_card"]["sku"],
            facts["best_per_litre"]["sku"]}) != 3:
        broken.append("three_answers")
    runner_up = facts["runner_up_price"]
    if runner_up is None or runner_up - best < best * water.MIN_MARGIN_REL:
        broken.append("clear_margin")
    return broken


# ---------------------------------------------------------------------------
# The keys, from the variants


def keys(families: list[dict]) -> dict:
    """What each question's answer is, from the variants alone, with the listings it names.
    The task generator writes these and the page rules read where they render. A value of
    None means the market cannot give that key one answer, which `market_check` refuses."""
    tees, waters = products(families)[TEE], products(families)[WATER]
    able = buyable(tees, TEE_TARGET)
    sold_out = [l for l in tees if apparel.price_for(l, TEE_TARGET) is not None
                and apparel.buyable_price_for(l, TEE_TARGET) is None]
    absent = [l for l in tees if apparel.price_for(l, TEE_TARGET) is None]
    limit = exists_limit(tees)
    witnesses = [l for l in able if limit is not None
                 and apparel.buyable_price_for(l, TEE_TARGET) < limit]
    water_able = buyable(waters, WATER_TARGET)
    water_sold_out = [l for l in waters if apparel.price_for(l, WATER_TARGET) is not None
                      and apparel.buyable_price_for(l, WATER_TARGET) is None]
    water_absent = [l for l in waters if apparel.price_for(l, WATER_TARGET) is None]
    rated = [(best_rate(l), l) for l in waters if best_rate(l)]
    rated.sort(key=lambda pair: pair[0][0])
    price = lambda l, option: apparel.buyable_price_for(l, option)  # noqa: E731
    return {
        "tee_cards": sorted(tees, key=apparel.from_price),
        "tee_winner": able[0] if able else None,
        "tee_runner_up": able[1] if len(able) > 1 else None,
        # The two sellers a price-only reader names for the cheapest M, as the tee generator's
        # cheapest-target note gives them: the cheapest card without M, the cheapest M sold out.
        "tee_absent_trap": min(absent, key=apparel.from_price) if absent else None,
        "tee_sold_out_trap": (min(sold_out, key=lambda l: apparel.price_for(l, TEE_TARGET))
                              if sold_out else None),
        "tee_listed": len(tees) - len(absent),
        "tee_buyable": len(able),
        "tee_sold_out": len(sold_out),
        "limit": limit,
        "witnesses": witnesses,
        "limit_on_a_price": any(price(l, TEE_TARGET) == limit for l in able),
        "looks_like_yes": sorted((l for l in tees if limit is not None
                                  and apparel.from_price(l) < limit and l not in witnesses),
                                 key=apparel.from_price),
        "top": able[:TOP_K],
        "top_next": able[TOP_K] if len(able) > TOP_K else None,
        "water_winner": water_able[0] if water_able else None,
        "water_absent_trap": min(water_absent, key=apparel.from_price) if water_absent else None,
        "water_sold_out_trap": (min(water_sold_out, key=lambda l: apparel.price_for(l, WATER_TARGET))
                                if water_sold_out else None),
        "water_card": min(waters, key=apparel.from_price) if waters else None,
        "water_listed": len(waters) - len(water_absent),
        "water_buyable": len(water_able),
        "water_sold_out": len(water_sold_out),
        "per_litre": rated[0][1] if rated else None,
        "per_litre_rate": rated[0][0][0] if rated else None,
        "per_litre_pack": rated[0][0][1] if rated else None,
        "per_litre_runner_up_rate": rated[1][0][0] if len(rated) > 1 else None,
    }


def answer_listings(k: dict) -> dict[str, tuple[list[dict], float]]:
    """For each price question: the listings its key names, and what the answer costs. A
    question whose key the market cannot give is left out, and `market_check` refuses it."""
    tee, water_, top = k["tee_winner"], k["water_winner"], k["top"]
    named = {}
    if tee is not None:
        cost = apparel.buyable_price_for(tee, TEE_TARGET)
        named["tee-target-price"] = named["tee-cheapest-target"] = ([tee], cost)
    if k["witnesses"]:
        named["tee-exists-under"] = (k["witnesses"], k["limit"])
    if len(top) == TOP_K:
        named["tee-top-3"] = (top, apparel.buyable_price_for(top[-1], TEE_TARGET))
    if water_ is not None:
        cost = apparel.buyable_price_for(water_, WATER_TARGET)
        named["water-target-price"] = named["water-cheapest-target"] = ([water_], cost)
    if k["per_litre"] is not None:
        named["water-best-per-litre"] = ([k["per_litre"]], k["per_litre_pack"]["price"])
    return {question: named[question] for question in PRICE_QUESTIONS if question in named}


# ---------------------------------------------------------------------------
# The market's rules


def words_a_scorer_reads(brand: str) -> list[str]:
    """Every text a seller's first word must not be found in, lowercased: the brand, every
    phrasing of both products, every option label and every question."""
    texts = [brand, *TEE_PHRASES, *WATER_PHRASES, *TEE_OPTIONS, *WATER_OPTIONS]
    texts += [text.format(brand=brand, limit="") for _, text in TEMPLATES.values()]
    return [t.lower() for t in texts]


def product_words() -> set[str]:
    """The words of every phrasing of both products, which no seller name may hold, so that
    the product a listing sells is read from its title alone."""
    return {w.strip(",").lower() for phrase in TEE_PHRASES + WATER_PHRASES for w in phrase.split()}


def name_problems(families: list[dict], brand: str) -> list[str]:
    """What `names_distinct` finds wrong, one line each."""
    problems = []
    firsts = [f["seller"].split()[0].lower() for f in families]
    if len(set(firsts)) != len(firsts):
        problems.append("a seller first word is used twice")
    texts = words_a_scorer_reads(brand)
    product_words_ = product_words()
    for family, first in zip(families, firsts):
        others = [g["seller"].lower() for g in families if g is not family]
        if any(first in other for other in others):
            problems.append(f"{family['seller']}: its first word is inside another seller's name")
        if any(first in text for text in texts):
            problems.append(f"{family['seller']}: its first word is inside a text the scorer reads")
        if brand.lower() in family["seller"].lower().split():
            problems.append(f"{family['seller']}: the brand is a word of it")
        if product_words_ & set(family["seller"].lower().split()):
            problems.append(f"{family['seller']}: it holds a product's own word")
    return problems


def market_check(families: list[dict], brand: str) -> list[str]:
    """Rules 3 to 5 and 7 to 11 of `MARKET_RULES`: everything that the fixture alone decides."""
    k = keys(families)
    broken = []
    if not PAGE_SIZE < len(families) <= 2 * PAGE_SIZE:
        broken.append("two_pages")
    if not (k["tee_sold_out"] and k["water_sold_out"]):
        broken.append("readings_differ")
    if k["per_litre"] is None or k["water_winner"] is None or \
            k["per_litre"]["parent_sku"] == k["water_winner"]["parent_sku"]:
        broken.append("per_litre_not_target")
    if name_problems(families, brand):
        broken.append("names_distinct")
    cards = [apparel.from_price(l) for l in k["tee_cards"]]
    if len(cards) < 2 or cards[0] == cards[1]:
        broken.append("headline_unique")
    if k["limit"] is None or len(k["witnesses"]) != 1 or k["limit_on_a_price"]:
        broken.append("limit_separates")
    if k["top_next"] is None or apparel.buyable_price_for(k["top_next"], TEE_TARGET) == \
            apparel.buyable_price_for(k["top"][-1], TEE_TARGET):
        broken.append("top_3_unique")
    if k["per_litre_rate"] is None or k["per_litre_rate"] == k["per_litre_runner_up_rate"]:
        broken.append("per_litre_unique")
    return broken


def page_problems(families: list[dict], order: list[str]) -> list[str]:
    """The page rules on one rendered order, the listings' SKUs as the results pages list them
    across both pages. Each broken rule once, a broken first-screen rule with its question."""
    by_sku = {f["parent_sku"]: f for f in families}
    if sorted(order) != sorted(by_sku):
        return ["the order is not this market's listings"]
    first, page_2 = order[:FIRST_SCREEN], order[PAGE_SIZE:]
    broken = []
    if {by_sku[s]["product"] for s in first} != {TEE, WATER} or \
            {by_sku[s]["product"] for s in page_2} != {TEE, WATER}:
        broken.append("interleaved")
    named = answer_listings(keys(families))
    for question, (listings, cost) in named.items():
        product = TEMPLATES[question][0]
        skus = {l["parent_sku"] for l in listings}
        undercut = [s for s in first if by_sku[s]["product"] == product and s not in skus
                    and apparel.from_price(by_sku[s]) < cost]
        if skus & set(first) or not undercut:
            broken.append(f"first_screen_misleads:{question}")
    if not any(l["parent_sku"] in page_2 for listings, _ in named.values() for l in listings):
        broken.append("answer_on_page_2")
    return broken


def predicted_orders(families: list[dict]) -> dict[str, list[str]]:
    """The order `search_order` predicts under each of its scenarios, by label."""
    return {f"{'two forms' if two else 'one form'}, average lengths x{scale}":
            [f["parent_sku"] for f in search_order.order(families, two, scale)]
            for two, scale in search_order.SCENARIOS}


def predicted_problems(families: list[dict]) -> list[str]:
    """Every page rule broken under any scenario, each once."""
    found = []
    for order in predicted_orders(families).values():
        found += [p for p in page_problems(families, order) if p not in found]
    return found


# ---------------------------------------------------------------------------
# Drawing a market


def tee_draw(seed: int, attempt: int, count: int, brand: str) -> list[dict]:
    rng = random.Random(f"{MARKET}:{seed}:tee:{attempt}")
    return [build_tee(name, i, rng, brand)
            for i, name in enumerate(seller_names(TEE_FIRST, TEE_SECOND, count, rng), 1)]


def water_draw(seed: int, attempt: int, count: int, brand: str) -> list[dict]:
    rng = random.Random(f"{MARKET}:{seed}:water:{attempt}")
    return [build_water(name, i, rng, brand)
            for i, name in enumerate(seller_names(WATER_FIRST, WATER_SECOND, count, rng), 1)]


# How many water draws that pass their own rules are paired with each tee draw that passes
# its own, before the next tee draw is tried.
WATER_PER_TEE = 40


def generate(seed: int, brand: str, sku_prefix: str, tees: int = TEE_LISTINGS,
             waters: int = WATER_LISTINGS, tee_attempts: int = 200000,
             water_attempts: int = 400000) -> tuple[list[dict], dict, dict]:
    """The first draw that passes every rule.

    The tees and the water come from their own streams, each held to its own generator's
    rules first, since a joint draw would pass both about once in a few hundred thousand.
    Each tee draw that passes is paired, in turn, with the first `WATER_PER_TEE` water draws
    that pass, each pairing given its catalogue order from its own stream, and the pair is
    held to the market's rules and the page rules. Returns the families in catalogue order,
    the facts, and the two draws accepted."""
    passing: list[tuple[int, list[dict]]] = []     # water draws that pass, in stream order
    next_water = 0

    def water_passing(i: int) -> tuple[int, list[dict]] | None:
        nonlocal next_water
        while len(passing) <= i and next_water < water_attempts:
            listings = water_draw(seed, next_water, waters, brand)
            if not water_check(listings, water_measure(listings)):
                passing.append((next_water, listings))
            next_water += 1
        return passing[i] if i < len(passing) else None

    for tee_attempt in range(tee_attempts):
        tee_list = tee_draw(seed, tee_attempt, tees, brand)
        if apparel.check(tee_list, apparel.measure(tee_list)):
            continue
        for i in range(WATER_PER_TEE):
            found = water_passing(i)
            if found is None:
                break
            water_attempt, water_list = found
            # Fresh copies, since `catalogue` numbers the listings in place.
            rng = random.Random(f"{MARKET}:{seed}:order:{tee_attempt}:{water_attempt}")
            families = catalogue(json.loads(json.dumps(tee_list)),
                                 json.loads(json.dumps(water_list)), rng, sku_prefix)
            if market_check(families, brand) or predicted_problems(families):
                continue
            return families, measure(families), {"tee": tee_attempt, "water": water_attempt}
    raise SystemExit(f"seed {seed}: no market satisfied every rule")


def measure(families: list[dict]) -> dict:
    """The facts a fixture records: each product's, and where the answers are predicted to
    render."""
    groups = products(families)
    orders = predicted_orders(families)
    one_form = next(iter(orders.values()))
    k = keys(families)
    rendered = {question: [one_form.index(l["parent_sku"]) + 1 for l in listings]
                for question, (listings, _) in answer_listings(k).items()}
    return {
        "market": MARKET,
        "listings": len(families),
        "page_size": PAGE_SIZE,
        "pages": -(-len(families) // PAGE_SIZE),
        "first_screen": FIRST_SCREEN,
        "tee": apparel.measure(groups[TEE]),
        "water": water_measure(groups[WATER]),
        "exists_limit": k["limit"],
        "predicted_order": one_form,
        "predicted_order_two_forms": orders[next(label for label in orders if label.startswith("two"))],
        "predicted_cards": rendered,
    }


def check(families: list[dict], brand: str) -> list[str]:
    """Every rule, by name, for a market already drawn: the tee rules, the water rules, the
    market's own and the page rules under the predicted orders. Empty means usable."""
    groups = products(families)
    broken = [f"tee.{r}" for r in apparel.check(groups[TEE], apparel.measure(groups[TEE]))]
    broken += [f"water.{r}" for r in water_check(groups[WATER], water_measure(groups[WATER]))]
    return broken + market_check(families, brand) + predicted_problems(families)


# ---------------------------------------------------------------------------
# The fixture


def search_lines(search: dict, command: str) -> list[str]:
    """The seed search a market was chosen by, as `_about` lines (as `generate_apparel`)."""
    lines = [f"Regenerate with: {command}",
             f"Seeded on {search['seeded']}. Every seed env/pick_aplus_market.py tried, in order:"]
    return lines + [f"  {entry['summary']}" for entry in search["tried"]]


def to_fixture(families: list[dict], facts: dict, seed: int, attempts: dict, brand: str,
               sku_prefix: str, search: dict | None = None, command: str | None = None) -> dict:
    about = [
        "Generated by env/generate_aplus.py. Do not hand edit.",
        f"Seed {seed}, tee draw {attempts['tee']}, water draw {attempts['water']}, brand "
        f"{brand}, SKU prefix {sku_prefix}.",
        "Regenerate with the same seed, brand and prefix to reproduce this catalogue exactly.",
        "Seeded with env/seed_variants.py, which reads this same schema.",
        *textwrap.wrap("The predicted order is search_order.py's. The live results pages are "
                       "checked after seeding and are what counts.", 88),
    ]
    generated = {"generator": "env/generate_aplus.py", "version": VERSION,
                 "search_order": "env/search_order.py",
                 "search_order_version": search_order.VERSION, "seed": seed, "attempts": attempts,
                 "brand": brand, "sku_prefix": sku_prefix,
                 "listings": {TEE: facts["tee"]["listings"], WATER: facts["water"]["listings"]}}
    if search is not None:
        about += search_lines(search, command or "")
        generated["search"] = search
    return {
        "_about": about,
        "_generated": generated,
        "_instance": facts,
        "attribute_set_id": 4,
        "website_ids": [1],
        "attributes": [{"code": "apparel_size", "label": "Size", "options": TEE_OPTIONS},
                       {"code": "pack_size", "label": "Pack Size", "options": WATER_OPTIONS}],
        "families": families,
    }


def report(fixture: dict) -> None:
    families, facts = fixture["families"], fixture["_instance"]
    order = facts["predicted_order"]
    print(MARKET_RULES)
    print()
    options = {TEE: TEE_OPTIONS, WATER: WATER_OPTIONS}
    for product in (TEE, WATER):
        print(f"{product:6} {'sku':12} {'card':>5} {'seller':32} " +
              " ".join(f"{o:>10}" for o in options[product]))
        for f in sorted((f for f in families if f["product"] == product),
                        key=lambda f: order.index(f["parent_sku"])):
            cells = []
            for option in options[product]:
                variant = next((v for v in f["variants"] if v["option"] == option), None)
                cells.append(f"{'--':>10}" if variant is None else
                             f"{variant['price']:9.2f}{'' if variant['qty'] else '*'}")
            print(f"{order.index(f['parent_sku']) + 1:5}  {f['parent_sku']:12} "
                  f"{apparel.from_price(f):5.2f} {f['seller']:32} " + " ".join(f"{c:>10}" for c in cells))
        print()
    print("* sold out. Rows in predicted results order, the number at the left its card.")
    tee, wat = facts["tee"], facts["water"]
    print(f"tee   winner {tee['winner']['seller']} at ${tee['winner']['price']}, "
          f"cheapest card {tee['cheapest_card']['seller']} at ${tee['cheapest_card']['from_price']}, "
          f"M listed {tee['listings_with_target']} buyable {tee['listings_target_buyable']}")
    print(f"water winner {wat['winner']['seller']} at ${wat['winner']['price']}, "
          f"cheapest card {wat['cheapest_card']['seller']} at ${wat['cheapest_card']['from_price']}, "
          f"best per litre {wat['best_per_litre']['seller']} at ${wat['best_per_litre']['price_per_litre']}/L "
          f"({wat['best_per_litre']['option']}), 2 x 9.5L listed {wat['listings_with_target']} "
          f"buyable {wat['listings_target_buyable']}")
    print(f"exists-under limit ${facts['exists_limit']}; predicted cards of each key: "
          + "; ".join(f"{q} {c}" for q, c in facts["predicted_cards"].items()))


# ---------------------------------------------------------------------------
# Command line


# The markets already in the shop, whose fixtures this never writes over.
EARLIER = ("gated_pricing.json", "scaled_water.json", "heldout_calderwood.json",
           "scaled_apparel.json", "claim_apparel.json")
DEV_SEEDS = range(900, 1000)


def refused(seed: int, claim: bool, out: pathlib.Path | None) -> str | None:
    """Why this draw may not be made or written, or None. Kept apart from `main` so a test can
    ask it without drawing anything."""
    if out is not None and out.name in EARLIER and out.resolve().parent == (HERE / "fixtures"):
        return f"{out.name} is an earlier market's fixture"
    if not claim and seed not in DEV_SEEDS:
        return (f"seed {seed} is outside development's 900 to 999; the claim market is drawn "
                f"with --claim, only after the protocol is final")
    if claim and seed in DEV_SEEDS:
        return f"seed {seed} is a development seed, and --claim is for the claim market"
    return None


def load_search(path: pathlib.Path, seed: int, brand: str, sku_prefix: str) -> dict:
    """A seed search's record, checked against the market it is said to have chosen."""
    search = json.loads(path.read_text())
    accepted = search["tried"][-1] if search.get("tried") else {}
    if (accepted.get("seed"), accepted.get("outcome")) != (seed, "accepted"):
        raise SystemExit(f"{path.name} does not end with seed {seed} accepted")
    if (search.get("brand"), search.get("sku_prefix")) != (brand, sku_prefix):
        raise SystemExit(f"{path.name} is the search for {search.get('brand')} "
                         f"{search.get('sku_prefix')}, not {brand} {sku_prefix}")
    return search


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--brand", required=True,
                        help="the word every listing's name starts with and the shop is searched for")
    parser.add_argument("--sku-prefix", default="IGR-DEV",
                        help="the listings' SKU prefix, and so their URL keys")
    parser.add_argument("--tees", type=int, default=TEE_LISTINGS)
    parser.add_argument("--waters", type=int, default=WATER_LISTINGS)
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--search-log", type=pathlib.Path,
                        help="the seed search that chose this market, written by "
                             "env/pick_aplus_market.py, recorded in the fixture")
    parser.add_argument("--claim", action="store_true",
                        help="draw the claim market: a seed from 1000, only after the protocol is final")
    parser.add_argument("--report", action="store_true", help="print the market and write nothing")
    args = parser.parse_args()
    why = refused(args.seed, args.claim, None if args.report else args.out)
    if why:
        raise SystemExit(f"refusing: {why}")
    if not args.report and args.out is None:
        parser.error("name --out, or ask for --report")

    families, facts, attempts = generate(args.seed, args.brand, args.sku_prefix,
                                         args.tees, args.waters)
    search, command = None, None
    if args.search_log:
        search = load_search(args.search_log, args.seed, args.brand, args.sku_prefix)
        log = args.search_log.resolve()
        log = log.relative_to(REPO) if log.is_relative_to(REPO) else log
        command = (f"python3 env/generate_aplus.py --seed {args.seed} --brand {args.brand} "
                   f"--sku-prefix {args.sku_prefix} --tees {args.tees} --waters {args.waters} "
                   f"--out env/fixtures/{args.out.name} --search-log {log}"
                   + (" --claim" if args.claim else ""))
    fixture = to_fixture(families, facts, args.seed, attempts, args.brand, args.sku_prefix,
                         search, command)
    report(fixture)
    if args.report:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2) + "\n")
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
