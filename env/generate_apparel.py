#!/usr/bin/env python3
"""Generate a clothing market, where the size you want may not be sold at all.

Every market measured so far sells bottled water in four pack sizes, so every figure in the
project is a figure about one product category. This is the second category, and it is the
held-out test for the coverage rule frozen on 17 September: that rule was written from the
principle and deliberately not fitted to any run, and this market did not exist when it was
written.

Why a sibling file rather than a flag on `generate_catalogue.py`. The water generator is
reproducible from its seed and two recorded markets depend on that, so it is left alone.
The domains also differ in a way a flag would hide: water has a volume, so "best value per
litre" is a question. Clothing has no denominator, so that question does not exist and a
different one takes its place.

What is the same, deliberately, so the comparison is about the product and not the method:
fifteen competing sellers, a price that only appears once a size is chosen, an advertised
price that belongs to a different size, and rejection sampling against rules that are checked
before the market is used.

What is new:

**A count question.** "How many listings stock size M" cannot stop early and cannot be
bounded. Every other question in the project can be finished before the market is exhausted,
and this one cannot, so it is the case where the honest plan is to open everything. A policy
that always saves effort would be wrong here, and the planner has to know that.

**Prices that cross over between sizes.** The cheapest seller for size M is not the cheapest
for size L, so an agent that finds one price and generalises is wrong for a reason that has
nothing to do with how many listings it opened.

**Three availability states rather than two.** A size can be absent from the menu, present
but sold out, or present and buyable. Until 18 September the shop could only render the first
and the third, because Magento hides out of stock variants by default, so a sold out size was
indistinguishable from one never sold. With `cataloginventory/options/show_out_of_stock` set
to 1 it renders as `<option disabled>`, which an accessibility snapshot prints as
`option "M" [disabled]`.

That matters because it is what the live marketplace does. Shopee renders a sold out size as
a button carrying `aria-disabled="true"`, and Lazada as a div whose class name ends
`-disabled`, both announcing that the variant exists while denying that it can be bought.
Neither publishes its price. So the middle state is the one real shops actually have, and it
creates a trap the other two cannot: **a listing can be the cheapest for the size and be
unable to ship it.**

**What that state does NOT support, which cost a question to find out.** A disabled option
cannot be selected, and the gated theme reveals a price only on selection, so **the price of
a sold out variant is unreachable**. Verified on the seeded market: the listing whose M the
fixture records at $15.04 shows `As low as $18.33`, refuses the selection, and contains the
string 15.04 nowhere in the page. Two questions had been written asking for the lowest price
anyone lists including the sold out ones, and neither had a route to its answer. They are now
asked over what can be bought.

This is the right behaviour to keep rather than a limitation to fix. It matches the live
marketplaces, where a greyed out variant publishes no price either, and it means the
availability contrast has to be carried by the counting questions, which read the disabled
state directly and never need the price behind it.

    python env/generate_apparel.py --report
    python env/generate_apparel.py --out env/fixtures/scaled_apparel.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "fixtures" / "scaled_apparel.json"

BRAND = "Thornwood"
SKU_PREFIX = "IGR-APP"
TARGET_SIZE = "M"
CLOTHING_CATEGORY_ID = 14

SIZES = ("S", "M", "L", "XL")

NAME_FIRST = ("Alderney", "Brindle", "Copperfield", "Dunmore", "Elmsworth", "Fairhaven",
              "Garrick", "Haldane", "Ivybridge", "Jarrow", "Kelsall", "Lymington",
              "Marchmont", "Northwick", "Oakhurst", "Pentland", "Quarles", "Rookwood")
NAME_SECOND = ("Outfitters", "Apparel", "Clothing Co", "Garments", "Textiles", "Workwear",
               "Supply", "Threads", "Uniforms", "Collective")

# A plain cotton tee sits in this range across sellers. Wider than it looks, because the
# spread is what gives the advertised price any power to rule a listing out.
BASE_PRICE_RANGE = (11.00, 38.00)

# Each size gets its own multiplier per seller. Without this the cheapest seller for one
# size is the cheapest for all of them, and a single lookup would answer every question.
SIZE_FACTOR_RANGE = (0.88, 1.24)

# Whether a seller offers a given size at all. A size a seller never stocked is absent from
# the menu, and nothing on the page marks the absence.
P_SIZE_MISSING = 0.18

# Whether a size a seller does offer is sold out right now. This is the third state, and it
# is the one the live marketplace actually renders: Shopee shows a sold out size as a button
# with `aria-disabled="true"`, so its existence is announced and its availability is denied.
# WebArena used to collapse this into absence, because Magento hides out of stock variants by
# default. With `cataloginventory/options/show_out_of_stock` set to 1 it renders them as
# `<option disabled>`, which Playwright's accessibility snapshot prints as `option "M"
# [disabled]`. Measured on a probe product on 18 Sep 2026, under both themes.
#
# The three states are then distinct in the page, which is what makes them separately
# answerable: absent says nothing, disabled says "exists, not buyable", and enabled says
# "buyable, and the price is still one click away".
P_SIZE_SOLD_OUT = 0.22

INSTANCE_RULES = """Properties every generated clothing instance must satisfy:

1. unique_winner        exactly one listing is cheapest for the target size, so the answer
                        is a single seller rather than a tie
2. card_probe_wrong     the listing with the lowest advertised price is NOT the winner, so
                        reading the search page gives the wrong seller
3. absent_trap          the listing whose target-size price would be lowest of all does not
                        offer that size at all. A price-only reader that ignores
                        availability names a seller who cannot sell the item. This is the
                        rule the water markets have no equivalent of
4. bound_is_useful      at least three listings can be ruled out on their advertised price
5. bound_not_sufficient at least three listings survive pruning and must be opened
6. some_missing_target  at least four listings do not offer the target size, so the count
                        question has a non-obvious answer and the universal question is
                        false
7. crossover            the cheapest seller for the target size is not the cheapest for the
                        largest size, so a price found for one size cannot be generalised
8. four_answers         the cheapest advertised listing, the cheapest listed price for the
                        target size, the cheapest one actually buyable, and the cheapest for
                        the largest size are four different sellers
9. clear_margin         the winner is at least 8 per cent cheaper than the runner up, so
                        a correct answer is not rounding luck. A percentage rather than
                        a sum, so clothing and water are held to the same standard
10. floor_is_real       at least five listings survive pruning and have to be opened
11. sold_out_trap       the cheapest listed price for the target size belongs to a listing
                        that cannot ship it. An agent that compares prices and ignores
                        availability names a seller it cannot buy from, and the page says so
                        only through a disabled option
12. sold_out_population at least three listings offer the target size and have none of it, so
                        the state is common enough to be worth checking rather than a
                        curiosity
13. enough_buyable      at least four listings can actually ship the target size, so the
                        question has a real field of candidates.

**Rule 10 is set by what the domain allows, and that is the interesting part.**

In water the advertised price is a small pack and the question asks about a large one, so
the published figure is a weak lower bound on the answer. It prunes about 4 listings of 15
and the oracle floor is 11. In clothing every size of a garment costs roughly the same, so
the advertised price is a tight bound and prunes most of the market: sampling 6,000 draws,
every instance that satisfies the other rules has a floor of 3, 4 or 5, and none reaches 6.

A first attempt demanded a floor of eight and found nothing in 20,000 draws. Widening the
size multipliers until it did would have meant a garment whose M costs twice its L, which no
shop sells, so the market would have been fitted to the method. Five is the honest ceiling
and the rule takes it.

That makes this market a different test of the coverage rule rather than a weaker one. On
water the rule has to insist on 11 openings. Here a sound answer can come from 5, and the
rule reads the floor the generator computes rather than a constant, so the question is
whether it permits that. A rule that demanded eleven everywhere would refuse correct answers
in this domain, and this is the market that would catch it.

**Two rules about page position used to live here and have been removed.**

They required the winner to sit late in the catalogue and the cheapest advertised listing to
sit early, as a way of putting the answer out of reach of a glance and the trap in plain
sight. Both were written against the catalogue index, and the catalogue index does not decide
where a listing renders.

What does, measured on 18 September 2026 across eight generated markets: **the number of
variants a listing has.** Magento's fulltext relevance indexes each child, so a listing with
four sizes carries the brand name four times and outranks one with two. In the market
measured, every listing rendering in cards 1 to 8 had four sizes, cards 9 to 11 had three,
and cards 13 to 15 had two.

That interacts badly with the trap. The trap is a listing that does not offer the target
size, so it has fewer variants by construction, so it renders late by construction. Eight
consecutive seeds were rejected with the trap at cards 8, 12, 8, 14, 10, 15, 12 and 13, and
not one landed in the first four. The rule was not unlucky, it was unsatisfiable.

Requiring the trap to carry all four sizes instead collapses the acceptance rate from 1 in
1,904 draws to 1 in 40,000, because it contradicts the rules that make it a trap. So the
generator stops making claims about position altogether, and `env/pick_apparel_market.py`
checks the rendered page, which it was written to do and can actually observe."""

MIN_MARGIN_REL = 0.08
# Percentage only, since 18 Sep 2026. There was an absolute floor of $1.50 alongside this,
# and it was the binding constraint at these price levels while the percentage never was,
# which made an arbitrary constant load bearing. Measured before removing it: of the draws
# passing every other rule, percent-only admitted one extra water market in 33, at a margin
# of $1.47, and no extra clothing market in 17. A scale-free rule states cleanly as "the
# winner is at least 8 per cent cheaper" and survives a change of currency or category,
# where the constant would have to be re-argued for every new product.


def money(value: float) -> float:
    return round(value + 1e-9, 2)


def seller_names(count: int, rng: random.Random) -> list[str]:
    if count > len(NAME_FIRST):
        raise SystemExit(f"only {len(NAME_FIRST)} distinct seller names available")
    firsts = list(NAME_FIRST)
    rng.shuffle(firsts)
    return [f"{first} {rng.choice(NAME_SECOND)}" for first in firsts[:count]]


def build_listing(name: str, index: int, rng: random.Random) -> dict:
    base = rng.uniform(*BASE_PRICE_RANGE)
    offered = [s for s in SIZES if rng.random() > P_SIZE_MISSING]
    if len(offered) < 2:                      # a listing selling one size is not a market
        offered = list(SIZES[:2])

    variants = []
    for size in offered:
        sold_out = rng.random() < P_SIZE_SOLD_OUT
        variants.append({
            "option": size,
            "price": money(base * rng.uniform(*SIZE_FACTOR_RANGE)),
            # Zero means the seeder marks the child out of stock, and Magento then renders
            # the option disabled rather than dropping it. The price is still real and still
            # gated, which is the point: a sold out variant can advertise a price it cannot
            # honour, and only the disabled state says so.
            "qty": 0 if sold_out else rng.randint(12, 140),
            "units": 1,
        })
    if all(v["qty"] == 0 for v in variants):   # a shop with nothing to sell is not a market
        variants[0]["qty"] = rng.randint(12, 140)

    return {
        "key": f"apparel-{index:02d}",
        "parent_sku": f"{SKU_PREFIX}-{index:02d}",
        "name": f"{BRAND} Heavyweight Cotton Tee - {name}",
        "seller": name,
        "attribute": "apparel_size",
        "category_ids": [CLOTHING_CATEGORY_ID],
        "gating": "price-and-stock-by-variant",
        "note": [f"Generated listing {index:02d}, seller {name}."],
        "variants": variants,
    }


def price_for(listing: dict, size: str) -> float | None:
    """What this listing charges for the size, whether or not it can ship it."""
    for variant in listing["variants"]:
        if variant["option"] == size:
            return variant["price"]
    return None


def buyable_price_for(listing: dict, size: str) -> float | None:
    """The same price, but only if the size can actually be bought today.

    The separation is the whole of the third gate. A sold out variant still advertises a
    price, and on the page nothing but the disabled state tells the two apart, so an agent
    that reads prices and ignores availability answers with a garment it cannot buy.
    """
    for variant in listing["variants"]:
        if variant["option"] == size and variant["qty"] > 0:
            return variant["price"]
    return None


def from_price(listing: dict) -> float:
    """What the search page shows without the listing being opened.

    Minimum over the variants that can actually be bought, because that is what Magento
    puts on the card. Measured on the rendered page on 18 September 2026 rather than
    assumed: a listing whose S and M are sold out at $16.22 and $15.04 and whose L and XL
    are in stock at $18.33 and $18.58 advertises **As low as $18.33**. Out of stock
    children are excluded from the indexed price.

    An earlier version of this took the minimum over every variant, and a comment here
    claimed Magento did the same. It does not, and the difference is not cosmetic: the
    whole pruning argument rests on the card price being a true lower bound on what the
    listing can charge, so a fixture that records a lower number than the shop displays
    computes an oracle floor for a market that does not exist.
    """
    live = [v["price"] for v in listing["variants"] if v["qty"] > 0]
    return min(live) if live else min(v["price"] for v in listing["variants"])


def hypothetical_target(listing: dict, rng_note: None = None) -> float:
    """What this listing would charge for the target size if it offered it.

    Used only by the absent_trap rule. A seller that does not offer the size still has a
    price level, and the trap is that the cheapest such seller looks like the answer to
    anyone comparing advertised prices.
    """
    return from_price(listing)


def measure(listings: list[dict]) -> dict:
    # Three populations rather than two, matching the three states the page can render.
    # `carriers` offer the size in the menu. `buyable` offer it and can ship it. `absent`
    # never list it at all.
    carriers = [l for l in listings if price_for(l, TARGET_SIZE) is not None]
    buyable = [l for l in listings if buyable_price_for(l, TARGET_SIZE) is not None]
    sold_out = [l for l in carriers if buyable_price_for(l, TARGET_SIZE) is None]
    absent = [l for l in listings if price_for(l, TARGET_SIZE) is None]

    # The answer is the cheapest one a shopper can actually buy. The cheapest price on
    # offer may belong to a listing that cannot ship it, and that is the trap.
    winner = min(buyable, key=lambda l: buyable_price_for(l, TARGET_SIZE))
    best = buyable_price_for(winner, TARGET_SIZE)
    runners = sorted(buyable_price_for(l, TARGET_SIZE) for l in buyable)

    listed_best = min(carriers, key=lambda l: price_for(l, TARGET_SIZE))
    cheapest_sold_out = (min(sold_out, key=lambda l: price_for(l, TARGET_SIZE))
                         if sold_out else None)

    cheapest_card = min(listings, key=from_price)
    must_open = [l for l in listings if from_price(l) <= best]

    largest = SIZES[-1]
    large_carriers = [l for l in listings if price_for(l, largest) is not None]
    large_winner = min(large_carriers, key=lambda l: price_for(l, largest))

    cheapest_absent = min(absent, key=from_price) if absent else None

    return {
        "target_option": TARGET_SIZE,
        "listings": len(listings),
        # Where the answer sits in the catalogue, which is very nearly where it sits on the
        # results page. A winner inside the first row of four can be found by glancing, and
        # a market like that measures nothing about retrieval.
        "winner_index": listings.index(winner) + 1,
        "cheapest_card_index": listings.index(cheapest_card) + 1,
        "listings_with_target": len(carriers),
        "listings_without_target": len(absent),
        "listings_target_buyable": len(buyable),
        "listings_target_sold_out": len(sold_out),
        # The sold out trap. `listed_best` is the cheapest price the menus advertise for
        # the size, and when it belongs to a listing that cannot ship it, an agent reading
        # prices without reading availability names a seller it cannot buy from.
        "cheapest_listed": {"sku": listed_best["parent_sku"],
                            "seller": listed_best["seller"],
                            "price": price_for(listed_best, TARGET_SIZE)},
        "cheapest_sold_out": None if cheapest_sold_out is None else {
            "sku": cheapest_sold_out["parent_sku"],
            "seller": cheapest_sold_out["seller"],
            "price": price_for(cheapest_sold_out, TARGET_SIZE),
        },
        "sold_out_trap": bool(cheapest_sold_out
                              and price_for(cheapest_sold_out, TARGET_SIZE) < best),
        "winner": {"sku": winner["parent_sku"], "seller": winner["seller"], "price": best},
        "runner_up_price": runners[1] if len(runners) > 1 else None,
        "winning_margin": money(runners[1] - best) if len(runners) > 1 else None,
        "cheapest_card": {
            "sku": cheapest_card["parent_sku"],
            "seller": cheapest_card["seller"],
            "from_price": from_price(cheapest_card),
        },
        "card_probe_wrong": cheapest_card["parent_sku"] != winner["parent_sku"],
        "cheapest_without_target": None if cheapest_absent is None else {
            "sku": cheapest_absent["parent_sku"],
            "seller": cheapest_absent["seller"],
            "from_price": from_price(cheapest_absent),
        },
        "absent_trap": bool(cheapest_absent
                            and from_price(cheapest_absent) < best),
        "largest_size": largest,
        "largest_size_winner": {"sku": large_winner["parent_sku"],
                                "seller": large_winner["seller"],
                                "price": price_for(large_winner, largest)},
        "crossover": large_winner["parent_sku"] != winner["parent_sku"],
        "oracle_min_opens": len(must_open),
        "prunable_by_bound": len(listings) - len(must_open),
        "exhaustive_opens": len(listings),
        "bound_strength": round((len(listings) - len(must_open)) / len(listings), 3),
        "from_price_range": [money(min(from_price(l) for l in listings)),
                             money(max(from_price(l) for l in listings))],
        "target_price_range": [money(min(runners)), money(max(runners))],
    }


def check(listings: list[dict], facts: dict) -> list[str]:
    broken = []
    prices = [buyable_price_for(l, TARGET_SIZE) for l in listings
              if buyable_price_for(l, TARGET_SIZE) is not None]
    best = facts["winner"]["price"]

    if prices.count(best) != 1:
        broken.append("unique_winner")
    if not facts["card_probe_wrong"]:
        broken.append("card_probe_wrong")
    if not facts["absent_trap"]:
        broken.append("absent_trap")
    if facts["prunable_by_bound"] < 3:
        broken.append("bound_is_useful")
    if facts["oracle_min_opens"] < 3:
        broken.append("bound_not_sufficient")
    if facts["listings_without_target"] < 4:
        broken.append("some_missing_target")
    if not facts["crossover"]:
        broken.append("crossover")
    if facts["oracle_min_opens"] < 5:
        broken.append("floor_is_real")
    if not facts["sold_out_trap"]:
        broken.append("sold_out_trap")
    if facts["listings_target_sold_out"] < 3:
        broken.append("sold_out_population")
    if facts["listings_target_buyable"] < 4:
        broken.append("enough_buyable")

    answers = {facts["winner"]["sku"], facts["cheapest_card"]["sku"],
               facts["largest_size_winner"]["sku"], facts["cheapest_listed"]["sku"]}
    if len(answers) != 4:
        broken.append("four_answers")

    runner_up = facts["runner_up_price"]
    if runner_up is None or runner_up - best < best * MIN_MARGIN_REL:
        broken.append("clear_margin")
    return broken


def generate(count: int, seed: int, attempts: int = 80000) -> tuple[list[dict], dict, int]:
    for attempt in range(attempts):
        # A string rather than one number. `seed * 1000 + attempt` collides: seed 12
        # at attempt 3682 and seed 13 at attempt 2682 are the same stream and produce the
        # same market, so a run of consecutive seeds silently explores one draw. Found while
        # searching seeds for a clothing market that lands the right way round on the page.
        rng = random.Random(f"{seed}:{attempt}")
        names = seller_names(count, rng)
        listings = [build_listing(name, i + 1, rng) for i, name in enumerate(names)]
        facts = measure(listings)
        if not check(listings, facts):
            return listings, facts, attempt
    raise SystemExit(f"no instance satisfied every rule in {attempts} attempts")


def to_fixture(listings: list[dict], facts: dict, seed: int, attempt: int) -> dict:
    return {
        "_about": [
            "Generated by env/generate_apparel.py. Do not hand edit.",
            f"Seed {seed}, accepted on attempt {attempt}. Regenerate with the same seed",
            "to reproduce this catalogue exactly.",
            "Seeded with env/seed_variants.py, which reads this same schema.",
        ],
        "_generated": {"seed": seed, "attempt": attempt, "brand": BRAND},
        "_instance": facts,
        "attribute_set_id": 4,
        "website_ids": [1],
        "attributes": [{"code": "apparel_size", "label": "Size", "options": list(SIZES)}],
        "families": listings,
    }


def report(facts: dict, listings: list[dict]) -> None:
    print(INSTANCE_RULES)
    print()
    print(f"{'seller':34} {'from':>7} " + " ".join(f"{s:>7}" for s in SIZES))
    print("-" * 78)
    for listing in listings:
        row = " ".join(
            f"{(price_for(listing, s) or 0):7.2f}" if price_for(listing, s) else f"{'--':>7}"
            for s in SIZES)
        print(f"{listing['seller']:34} {from_price(listing):7.2f} {row}")
    print()
    for key in ("listings", "listings_with_target", "listings_target_buyable",
                "listings_target_sold_out", "listings_without_target",
                "oracle_min_opens", "prunable_by_bound", "winning_margin"):
        print(f"  {key:24} {facts[key]}")
    print(f"  {'winner, buyable':24} {facts['winner']['seller']} at ${facts['winner']['price']}")
    print(f"  {'cheapest listed':24} {facts['cheapest_listed']['seller']} at "
          f"${facts['cheapest_listed']['price']}")
    if facts["cheapest_sold_out"]:
        print(f"  {'trap, sold out':24} {facts['cheapest_sold_out']['seller']} at "
              f"${facts['cheapest_sold_out']['price']}")
    print(f"  {'cheapest advertised':24} {facts['cheapest_card']['seller']} at "
          f"${facts['cheapest_card']['from_price']}")
    print(f"  {'trap, no target size':24} {facts['cheapest_without_target']['seller']} at "
          f"${facts['cheapest_without_target']['from_price']}")
    print(f"  {'cheapest for size ' + facts['largest_size']:24} "
          f"{facts['largest_size_winner']['seller']} at "
          f"${facts['largest_size_winner']['price']}")


def write_tasks(fixture: dict, out: pathlib.Path) -> pathlib.Path:
    """Write the task file from the fixture, so the two cannot drift apart.

    They already did once. The first clothing market was generated, its task file written by
    hand from that market's answers, then the market was regenerated to satisfy a new rule
    and the task file was not. Fifteen runs were scored against a market that no longer
    existed, and the control question read 0 of 3, which is the shape of an answer key that
    has moved rather than an agent that has failed. The fixture is the only source of truth
    for the answers, so the task file is derived from it here.
    """
    inst = fixture["_instance"]
    brand = fixture["_generated"]["brand"]
    win, card = inst["winner"], inst["cheapest_card"]
    absent, large = inst["cheapest_without_target"], inst["largest_size_winner"]
    sold_out, listed = inst["cheapest_sold_out"], inst["cheapest_listed"]
    first = lambda name: name.split()[0]
    search = f"Go to {{base}}/catalogsearch/result/?q={brand} ."

    spec = {
        "_about": [
            "Generated by env/generate_apparel.py alongside the fixture. Do not hand edit.",
            f"Seed {fixture['_generated']['seed']}, accepted on attempt "
            f"{fixture['_generated']['attempt']}.",
            f"{inst['listings']} listings, exhaustive {inst['exhaustive_opens']} opens, "
            f"oracle floor {inst['oracle_min_opens']} opens.",
            "The second product category in the project, and the held-out test for the",
            "coverage rule frozen on 17 September, which did not exist when this market was",
            "generated.",
        ],
        "_environment": [
            "Clothing, seeded 18 September 2026 alongside the water markets rather than",
            "replacing them. Sizes rather than pack volumes, so there is no per-unit",
            "question. Three availability states, since 18 September 2026: a size can be",
            "absent from the menu, present but disabled because it is sold out, or present",
            "and buyable. The middle state needs show_out_of_stock set to 1 in Magento, and",
            "is what the live marketplaces render.",
            f"The winning listing is index {inst['winner_index']} of "
            f"{inst['listings']}, so it is not in the first row of search results.",
        ],
        "base_url": "http://localhost:7770",
        "brand": brand,
        "_instance": inst,
        "tasks": [
            {"id": "apparel-headline", "family": "apparel", "gated": False,
             "note": "Control. Answerable from the results page without opening anything.",
             "query": f"{search} Of the {brand} tee listings shown, which one advertises the "
                      f"lowest price on the results page, and what is that price?",
             "expect": {"kind": "contains", "any": [first(card["seller"])],
                        "price": card["from_price"]}},
            {"id": "apparel-target-price", "family": "apparel", "gated": True,
             "note": f"The price of size {inst['target_option']} appears only once that size "
                     f"is chosen. {inst['listings_without_target']} listings do not offer it "
                     f"and {inst['listings_target_sold_out']} offer it sold out, and a sold "
                     f"out size cannot be selected, so its price cannot be reached at all. "
                     f"The lowest reachable price is therefore the lowest buyable one.",
             "query": f"{search} What is the lowest price anyone charges for size "
                      f"{inst['target_option']} of the {brand} tee, among those that can "
                      f"actually be bought?",
             "expect": {"kind": "price", "value": win["price"]}},
            {"id": "apparel-cheapest-target", "family": "apparel", "gated": True,
             "note": f"Two traps in front of the answer. {absent['seller']} advertises "
                     f"${absent['from_price']} and does not sell size "
                     f"{inst['target_option']} at all. {sold_out['seller']} does sell it, "
                     f"lists it at ${sold_out['price']}, and cannot ship it, which the page "
                     f"says only by rendering that option disabled. Neither can be the "
                     f"answer and both look cheaper than it.",
             "query": f"{search} Across the {brand} listings, which seller is cheapest for "
                      f"size {inst['target_option']}, and what is that price? Only count a "
                      f"listing that can actually supply that size.",
             "expect": {"kind": "contains", "any": [first(win["seller"])],
                        "not_any": [first(absent["seller"]), first(sold_out["seller"])],
                        "price": win["price"]}},
            {"id": "apparel-all-stocked", "family": "apparel", "gated": True,
             "note": f"{inst['listings_without_target']} of {inst['listings']} listings do "
                     f"not offer the size. One counterexample settles it.",
             "query": f"{search} Does every {brand} listing offer size "
                      f"{inst['target_option']}? Answer yes or no.",
             "expect": {"kind": "boolean", "value": False}},
            {"id": "apparel-count-stocked", "family": "apparel", "gated": True,
             "note": "The first counting question in the project. It cannot stop at a "
                     "counterexample and cannot be bounded, so the honest plan is to open "
                     "every listing.",
             "query": f"{search} How many of the {brand} listings offer size "
                      f"{inst['target_option']}?",
             "expect": {"kind": "count", "value": inst["listings_with_target"]}},
            {"id": "apparel-count-buyable", "family": "apparel", "gated": True,
             "note": "Counting, but over availability rather than existence. Differs from "
                     "apparel-count-stocked by exactly the sold out listings, so an agent "
                     "that reads the menu and not the disabled state gives the same answer "
                     "to both.",
             "query": f"{search} How many of the {brand} listings have size "
                      f"{inst['target_option']} in stock and available to buy right now?",
             "expect": {"kind": "count", "value": inst["listings_target_buyable"]}},
        ],
    }
    out.write_text(json.dumps(spec, indent=2) + "\n")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--listings", type=int, default=15)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--tasks", type=pathlib.Path,
                        default=HERE.parent / "experiments" / "tasks_apparel.json",
                        help="task file, written from the same fixture so they cannot drift")
    parser.add_argument("--report", action="store_true",
                        help="print the instance and write nothing")
    args = parser.parse_args()

    listings, facts, attempt = generate(args.listings, args.seed)
    if args.report:
        report(facts, listings)
        print(f"\naccepted on attempt {attempt}, seed {args.seed}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fixture = to_fixture(listings, facts, args.seed, attempt)
    args.out.write_text(json.dumps(fixture, indent=2) + "\n")
    tasks = write_tasks(fixture, args.tasks)
    report(facts, listings)
    print(f"\nwritten: {args.out}")
    print(f"written: {tasks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
