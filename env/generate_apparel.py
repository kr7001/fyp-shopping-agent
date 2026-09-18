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

**Gating by absence, at scale.** Magento removes a size with no stock from the menu rather
than showing it greyed out, so a missing size looks exactly like a size that was never sold.
Five of fifteen listings do not offer the target size. This is the same mechanism the small
fixture's t-shirt uses, and it is stated plainly rather than described as a second kind of
gate, because in this shop it is not one.

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

# Whether a seller offers a given size at all. Magento drops a size with no stock from the
# menu, so this is what "out of stock" looks like to a shopper: the option is simply absent.
P_SIZE_MISSING = 0.18

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
8. three_answers        the cheapest advertised listing, the cheapest for the target size
                        and the cheapest for the largest size are three different sellers
9. clear_margin         the winner beats the runner up by a visible amount, so a correct
                        answer is not rounding luck
10. floor_is_real       at least five listings survive pruning and have to be opened.

**Rule 10 is set by what the domain allows, and that is the interesting part.**

In water the advertised price is a small pack and the question asks about a large one, so
the published figure is a weak lower bound on the answer. It prunes about 4 listings of 15
and the oracle floor is 11. In clothing every size of a garment costs roughly the same, so
the advertised price is a tight bound and prunes most of the market: sampling 6,000 draws,
every instance that satisfies the other nine rules has a floor of 3, 4 or 5, and none
reaches 6.

A first attempt demanded a floor of eight and found nothing in 20,000 draws. Widening the
size multipliers until it did would have meant a garment whose M costs twice its L, which no
shop sells, so the market would have been fitted to the method. Five is the honest ceiling
and the rule takes it.

That makes this market a different test of the coverage rule rather than a weaker one. On
water the rule has to insist on 11 openings. Here a sound answer can come from 5, and the
rule reads the floor the generator computes rather than a constant, so the question is
whether it permits that. A rule that demanded eleven everywhere would refuse correct answers
in this domain, and this is the market that would catch it."""

MIN_MARGIN_ABS = 1.50
MIN_MARGIN_REL = 0.08


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
        variants.append({
            "option": size,
            "price": money(base * rng.uniform(*SIZE_FACTOR_RANGE)),
            "qty": rng.randint(12, 140),
            "units": 1,
        })

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
    for variant in listing["variants"]:
        if variant["option"] == size:
            return variant["price"]
    return None


def from_price(listing: dict) -> float:
    """What the search page shows without the listing being opened."""
    return min(v["price"] for v in listing["variants"])


def hypothetical_target(listing: dict, rng_note: None = None) -> float:
    """What this listing would charge for the target size if it offered it.

    Used only by the absent_trap rule. A seller that does not offer the size still has a
    price level, and the trap is that the cheapest such seller looks like the answer to
    anyone comparing advertised prices.
    """
    return from_price(listing)


def measure(listings: list[dict]) -> dict:
    carriers = [l for l in listings if price_for(l, TARGET_SIZE) is not None]
    absent = [l for l in listings if price_for(l, TARGET_SIZE) is None]
    winner = min(carriers, key=lambda l: price_for(l, TARGET_SIZE))
    best = price_for(winner, TARGET_SIZE)
    runners = sorted(price_for(l, TARGET_SIZE) for l in carriers)

    cheapest_card = min(listings, key=from_price)
    must_open = [l for l in listings if from_price(l) <= best]

    largest = SIZES[-1]
    large_carriers = [l for l in listings if price_for(l, largest) is not None]
    large_winner = min(large_carriers, key=lambda l: price_for(l, largest))

    cheapest_absent = min(absent, key=from_price) if absent else None

    return {
        "target_option": TARGET_SIZE,
        "listings": len(listings),
        "listings_with_target": len(carriers),
        "listings_without_target": len(absent),
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
    prices = [price_for(l, TARGET_SIZE) for l in listings
              if price_for(l, TARGET_SIZE) is not None]
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

    answers = {facts["winner"]["sku"], facts["cheapest_card"]["sku"],
               facts["largest_size_winner"]["sku"]}
    if len(answers) != 3:
        broken.append("three_answers")

    runner_up = facts["runner_up_price"]
    if runner_up is None or runner_up - best < max(MIN_MARGIN_ABS, best * MIN_MARGIN_REL):
        broken.append("clear_margin")
    return broken


def generate(count: int, seed: int, attempts: int = 20000) -> tuple[list[dict], dict, int]:
    for attempt in range(attempts):
        rng = random.Random(seed * 1000 + attempt)
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
    for key in ("listings", "listings_with_target", "listings_without_target",
                "oracle_min_opens", "prunable_by_bound", "winning_margin"):
        print(f"  {key:24} {facts[key]}")
    print(f"  {'winner':24} {facts['winner']['seller']} at ${facts['winner']['price']}")
    print(f"  {'cheapest advertised':24} {facts['cheapest_card']['seller']} at "
          f"${facts['cheapest_card']['from_price']}")
    print(f"  {'trap, no target size':24} {facts['cheapest_without_target']['seller']} at "
          f"${facts['cheapest_without_target']['from_price']}")
    print(f"  {'cheapest for size ' + facts['largest_size']:24} "
          f"{facts['largest_size_winner']['seller']} at "
          f"${facts['largest_size_winner']['price']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--listings", type=int, default=15)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true",
                        help="print the instance and write nothing")
    args = parser.parse_args()

    listings, facts, attempt = generate(args.listings, args.seed)
    if args.report:
        report(facts, listings)
        print(f"\naccepted on attempt {attempt}, seed {args.seed}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(to_fixture(listings, facts, args.seed, attempt), indent=2) + "\n")
    report(facts, listings)
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
