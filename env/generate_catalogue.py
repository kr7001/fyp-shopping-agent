#!/usr/bin/env python3
"""Generate a multi-seller catalogue whose answer cannot be reached by a shortcut.

The four hand-authored families answered RQ2, but the cross-listing task scored 5/5:
with two listings and both URLs given, comparing them is cheap enough that the agent
simply does it. The failure this project studies needs a search page wide enough that
opening every listing is a real cost. This builds that page.

Scale is chosen against the agent's own limit, not for its own sake. Every trace
reports `Max steps: 100`, and the RQ2 baseline spent 4-6 actions per listing, so
exhaustive retrieval over 30 listings would exceed the guardrail and fail rather than
merely cost more. A failed baseline cannot anchor the interactions-against-correctness
plot that RQ3 needs, so the default is 15 listings: roughly 60-90 steps exhaustively,
expensive but reachable.

Prices are generated rather than written by hand. Sixty prices imply sixty derived
ground truths, and hand-computing those is where an answer key silently stops matching
the shop. Here one price model feeds both the fixture and the ground truth, so they
cannot disagree.

A random price table usually contains no trap at all, so generation is a search: draw
an instance, test it against the properties the experiment depends on, and redraw until
they hold. `INSTANCE_RULES` states those properties, and a fixture that satisfies none
of them would quietly measure nothing.

    python env/generate_catalogue.py --listings 15 --seed 7
    python env/generate_catalogue.py --listings 15 --seed 7 --report
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import random
import statistics

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "fixtures" / "scaled_water.json"

BRAND = "Rivenhall"
# A held-out test needs a market the policy has not been developed against. Rather than
# replacing the existing one, which would destroy the fixture every recorded run was
# scored on, a second market is generated under a different brand and SKU prefix so both
# can live in the same shop at once. The brand is what the task queries search for, so two
# brands means two independent instances.
SKU_PREFIX = "IGR-RVN"
"""One token shared by every listing, so a single search returns the whole set."""

TARGET_OPTION = "2 x 9.5L"
"""The variant every scaled task asks about. Gated on every listing that carries it."""

GROCERY_CATEGORY_ID = 14

PACKS = (
    {"option": "24 x 350ml", "units": 24, "volume_ml": 350},
    {"option": "12 x 550ml", "units": 12, "volume_ml": 550},
    {"option": "6 x 1.25L", "units": 6, "volume_ml": 1250},
    {"option": "2 x 9.5L", "units": 2, "volume_ml": 9500},
)

# Seller names are drawn from these rather than numbered, because "Seller 07" tells an
# agent it is inside a synthetic benchmark and invites pattern matching over retrieval.
NAME_FIRST = ("Cellar", "Hillside", "Oakfield", "Marlow", "Thornbury", "Ashgrove",
              "Westmere", "Kettering", "Bramley", "Fenwick", "Larkspur", "Redhill",
              "Stonebridge", "Verity", "Whitlock", "Yarrow", "Chandler", "Pembroke")
NAME_SECOND = ("Direct", "Provisions", "Supply Co", "Trading", "Wholesale", "Pantry",
               "Cellars", "Merchants", "Stores", "Distributors")

# Per-litre rate before pack effects.
#
# This range was set empirically, not guessed. The published "from" price is a valid
# lower bound on a listing's target price, but a weak one: it is the cheapest small
# pack, so it rarely exceeds a rival's 9.5L price and rarely prunes anything. Sweeping
# the spread over 300 draws each, counting listings prunable on the bound alone:
#
#     rate range     mean prunable of 15
#     1.02 - 1.94    0.0
#     0.95 - 2.40    0.2
#     0.95 - 3.10    1.4
#     0.90 - 3.80    3.6
#     0.85 - 4.60    5.4
#
# Pruning only appears once sellers differ by roughly threefold. Wider ranges would
# make branch and bound look stronger, at the cost of a catalogue no marketplace would
# produce. The spread below is the widest that stays plausible for bottled water, and
# the honest consequence is recorded in the instance facts as `bound_strength`:
# the published bound saves a little, so most of RQ3's headroom has to come from
# question-conditioned targeting rather than from bounds.
RATE_RANGE = (0.95, 3.10)

# Multiplier applied to a pack's fair price. Above 1 the pack is a poor deal, below 1 a
# good one. Drawn per seller per pack, so bulk is not reliably cheaper anywhere, which
# is what stops "just open the biggest pack" from working as a heuristic.
PACK_FACTOR_RANGE = (0.84, 1.22)

# Some sellers do not stock the largest carton. A listing that cannot answer the
# question at all is a real shape on a search page, and it punishes an agent that
# assumes every result is comparable.
P_MISSING_TARGET = 0.2

INSTANCE_RULES = """Properties every generated instance must satisfy:

1. unique_winner        exactly one listing is cheapest for the target variant, so the
                        correct answer is a single seller rather than a tie
2. card_probe_wrong     the listing with the lowest "from" price is NOT the winner, so
                        reading headline prices off the search page gives the wrong
                        seller. Without this the task is passable without retrieval
3. bound_is_useful      at least three listings can be skipped on their published
                        "from" price alone. Set to three rather than a fraction because
                        the bound is empirically weak, see RATE_RANGE
4. bound_not_sufficient at least three listings survive pruning, so the policy still
                        has to open several. A one-listing answer would make the task
                        trivial rather than selective
5. some_missing_target  at least one listing does not stock the target variant, so
                        "every result is comparable" is a false assumption
6. clear_margin         the winner is at least 8 per cent cheaper than the runner up.
                        A 50 cent gap makes the correct answer feel arbitrary and
                        leaves the verdict sensitive to rounding in the agent's
                        arithmetic. Stated as a percentage rather than a sum, so the
                        rule reads the same on a $9 pack and a $90 one
7. unit_probe_wrong     the best price per litre belongs to a different seller than the
                        lowest headline price. Added after a pilot run answered the per
                        litre question correctly in 7 actions, far too few to have
                        checked 15 listings: the two answers coincided, so guessing from
                        the search page happened to be right. A task that rewards the
                        shortcut under study measures nothing
8. three_answers        the cheapest headline, the cheapest target pack and the best
                        price per litre belong to three different sellers, so each task
                        needs its own retrieval. When two coincide, an agent that has
                        answered one gets the other free and the second task stops
                        being evidence of anything.

Rule 8 holds in roughly 0.3% of draws, so `generate` searches thousands of instances
rather than hundreds. That is cheap arithmetic, and far preferable to relaxing a rule
because the first few hundred tries missed."""

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


def litres(pack: dict) -> float:
    return pack["units"] * pack["volume_ml"] / 1000


def seller_names(count: int, rng: random.Random) -> list[str]:
    """Distinct trading names, deterministic for a given seed.

    First words are never reused. "Bramley Wholesale" alongside "Bramley Provisions"
    makes an answer naming "Bramley" impossible to score, and the agent has no reason
    to know the second word carries the distinction.
    """
    if count > len(NAME_FIRST):
        raise SystemExit(f"only {len(NAME_FIRST)} distinct seller names available")
    firsts = list(NAME_FIRST)
    rng.shuffle(firsts)
    return [f"{first} {rng.choice(NAME_SECOND)}" for first in firsts[:count]]


def build_listing(name: str, index: int, rng: random.Random) -> dict:
    """One seller, its packs and its prices.

    Each seller has a base per-litre rate, then each pack gets its own multiplier. The
    multiplier is what makes bulk pricing unreliable: without it, price would be a
    linear function of volume and the cheapest seller for one pack would be the
    cheapest for all of them, which no retrieval policy would need to check.
    """
    rate = rng.uniform(*RATE_RANGE)
    packs = list(PACKS)
    if rng.random() < P_MISSING_TARGET:
        packs = [p for p in packs if p["option"] != TARGET_OPTION]

    variants = []
    for pack in packs:
        factor = rng.uniform(*PACK_FACTOR_RANGE)
        variants.append({
            "option": pack["option"],
            "price": money(rate * litres(pack) * factor),
            "qty": rng.randint(25, 240),
            "units": pack["units"],
            "volume_ml": pack["volume_ml"],
        })

    return {
        "key": f"scaled-{index:02d}",
        "parent_sku": f"{SKU_PREFIX}-{index:02d}",
        "name": f"{BRAND} Still Spring Water, Multipack - {name}",
        "seller": name,
        "attribute": "pack_size",
        "category_ids": [GROCERY_CATEGORY_ID],
        "gating": "price-by-variant",
        "note": [f"Generated listing {index:02d}, seller {name}."],
        "variants": variants,
    }


def target_price(listing: dict) -> float | None:
    for variant in listing["variants"]:
        if variant["option"] == TARGET_OPTION:
            return variant["price"]
    return None


def unit_price(variant: dict) -> float:
    """Price per litre for one pack."""
    return variant["price"] / litres(variant)


def best_unit_price(listing: dict) -> float:
    """The cheapest per litre rate this listing offers, across all its packs."""
    return min(unit_price(v) for v in listing["variants"])


def from_price(listing: dict) -> float:
    """The headline price a card-level probe reads without opening the listing."""
    return min(v["price"] for v in listing["variants"])


def measure(listings: list[dict]) -> dict:
    """Ground truth plus the numbers that say how hard the instance is.

    `oracle_min_opens` is the floor any correct policy has to pay. A listing whose
    "from" price already exceeds the winning target price cannot possibly win, so it can
    be skipped on published information alone. Everything else has to be opened, because
    its real target price is unknown until then. That count is the best score achievable,
    and it is what RQ3 is measured against rather than against the exhaustive baseline.
    """
    carriers = [l for l in listings if target_price(l) is not None]
    winner = min(carriers, key=target_price)
    best = target_price(winner)
    runners = sorted(target_price(l) for l in carriers)

    cheapest_card = min(listings, key=from_price)
    must_open = [l for l in listings if from_price(l) <= best]

    unit_winner = min(listings, key=best_unit_price)
    unit_variant = min(unit_winner["variants"], key=unit_price)

    return {
        "target_option": TARGET_OPTION,
        "listings": len(listings),
        "listings_with_target": len(carriers),
        "winner": {"sku": winner["parent_sku"], "seller": winner["seller"], "price": best},
        "runner_up_price": runners[1] if len(runners) > 1 else None,
        "winning_margin": money(runners[1] - best) if len(runners) > 1 else None,
        "cheapest_card": {
            "sku": cheapest_card["parent_sku"],
            "seller": cheapest_card["seller"],
            "from_price": from_price(cheapest_card),
        },
        "card_probe_wrong": cheapest_card["parent_sku"] != winner["parent_sku"],
        "best_per_litre": {
            "sku": unit_winner["parent_sku"],
            "seller": unit_winner["seller"],
            "option": unit_variant["option"],
            "price_per_litre": round(unit_price(unit_variant), 4),
        },
        "unit_probe_wrong": unit_winner["parent_sku"] != cheapest_card["parent_sku"],
        "oracle_min_opens": len(must_open),
        "prunable_by_bound": len(listings) - len(must_open),
        "exhaustive_opens": len(listings),
        "bound_strength": round((len(listings) - len(must_open)) / len(listings), 3),
        "from_price_range": [money(min(from_price(l) for l in listings)),
                             money(max(from_price(l) for l in listings))],
        "target_price_range": [money(min(runners)), money(max(runners))],
    }


def check(listings: list[dict], facts: dict) -> list[str]:
    """Return the names of every rule this instance breaks. Empty means usable."""
    broken = []
    prices = [target_price(l) for l in listings if target_price(l) is not None]
    best = facts["winner"]["price"]

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

    answers = {facts["winner"]["sku"], facts["cheapest_card"]["sku"],
               facts["best_per_litre"]["sku"]}
    if len(answers) != 3:
        broken.append("three_answers")

    runner_up = facts["runner_up_price"]
    if runner_up is None or runner_up - best < best * MIN_MARGIN_REL:
        broken.append("clear_margin")
    return broken


def generate(count: int, seed: int, attempts: int = 8000) -> tuple[list[dict], dict, int]:
    """Draw instances until one satisfies every rule.

    Rejection sampling rather than construction: the rules describe a shape that is easy
    to test and awkward to build directly, and at these sizes a satisfying draw arrives
    within a few dozen tries. Raises rather than returning a weaker instance, because a
    fixture that quietly fails `card_probe_wrong` would measure nothing while looking fine.
    """
    for attempt in range(attempts):
        # Deliberately left as it is, despite a collision: `seed * 1000 + attempt` means
        # seed 12 at attempt 3682 and seed 13 at attempt 2682 draw the same market, so a run
        # of consecutive seeds silently explores one draw. The clothing generator uses a
        # string key instead. This one is not changed because the two water fixtures on disk
        # were produced by it and their `_about` promises they can be reproduced from their
        # seeds, which a change would quietly falsify. Seeds 7 and 41 are far enough apart
        # that the collision never touched them.
        rng = random.Random(seed * 1000 + attempt)
        names = seller_names(count, rng)
        listings = [build_listing(name, i + 1, rng) for i, name in enumerate(names)]
        facts = measure(listings)
        if not check(listings, facts):
            return listings, facts, attempt
    raise SystemExit(
        f"no instance satisfied every rule in {attempts} attempts. Run with --diagnose "
        "to see which rule is binding, then widen RATE_RANGE or PACK_FACTOR_RANGE, or "
        "lower the listing count."
    )


def to_fixture(listings: list[dict], facts: dict, seed: int, attempt: int) -> dict:
    options = [p["option"] for p in PACKS]
    return {
        "_about": [
            "Generated by env/generate_catalogue.py. Do not hand edit.",
            f"Seed {seed}, accepted on attempt {attempt}. Regenerate with the same seed",
            "to reproduce this catalogue exactly.",
            "Seeded with env/seed_variants.py, which reads this same schema.",
        ],
        "_generated": {"seed": seed, "attempt": attempt, "brand": BRAND},
        "_instance": facts,
        "attribute_set_id": 4,
        "website_ids": [1],
        "attributes": [{"code": "pack_size", "label": "Pack Size", "options": options}],
        "families": listings,
    }


def report(facts: dict, listings: list[dict]) -> None:
    print(INSTANCE_RULES)
    print()
    print(f"listings                {facts['listings']}")
    print(f"carrying {TARGET_OPTION:<14} {facts['listings_with_target']}")
    print(f"winner                  {facts['winner']['seller']} at ${facts['winner']['price']}")
    print(f"runner up               ${facts['runner_up_price']} "
          f"(margin ${facts['winning_margin']})")
    print(f"lowest headline price   {facts['cheapest_card']['seller']} "
          f"at ${facts['cheapest_card']['from_price']}")
    print(f"card probe wrong        {facts['card_probe_wrong']}")
    print(f"best per litre          {facts['best_per_litre']['seller']} at "
          f"${facts['best_per_litre']['price_per_litre']}/L "
          f"({facts['best_per_litre']['option']})")
    print()
    print(f"exhaustive opens        {facts['exhaustive_opens']}")
    print(f"oracle minimum opens    {facts['oracle_min_opens']}")
    print(f"prunable on bound       {facts['prunable_by_bound']} "
          f"({facts['bound_strength']:.0%} of listings)")
    print(f"headroom                {facts['exhaustive_opens'] - facts['oracle_min_opens']} "
          f"listings a perfect policy never opens")
    print()
    header = f"{'sku':<14} {'seller':<24} {'from':>8} {TARGET_OPTION:>10}"
    print(header)
    print("-" * len(header))
    for listing in sorted(listings, key=from_price):
        target = target_price(listing)
        # Prunable takes precedence over out of stock: a listing skipped on its
        # published price is never opened, so whether it stocks the target is moot.
        flag = ""
        if listing["parent_sku"] == facts["winner"]["sku"]:
            flag = "  <- cheapest"
        elif from_price(listing) > facts["winner"]["price"]:
            flag = "  prunable on bound"
        elif target is None:
            flag = "  opened, not stocked"
        print(f"{listing['parent_sku']:<14} {listing['seller']:<24} "
              f"{from_price(listing):>8.2f} {('-' if target is None else f'{target:.2f}'):>10}{flag}")


def _use_brand(brand: str, prefix: str) -> None:
    """Point the module at a different market before anything reads the constants."""
    global BRAND, SKU_PREFIX
    BRAND, SKU_PREFIX = brand, prefix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--listings", type=int, default=15)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--brand", default=BRAND,
                        help="product brand, which is also what the tasks search for. A "
                             "second brand gives an independent market in the same shop")
    parser.add_argument("--sku-prefix", default=SKU_PREFIX)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true", help="print the instance and write nothing")
    args = parser.parse_args()
    _use_brand(args.brand, args.sku_prefix)

    listings, facts, attempt = generate(args.listings, args.seed)

    if args.report:
        report(facts, listings)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(to_fixture(listings, facts, args.seed, attempt), indent=2) + "\n")
    report(facts, listings)
    print(f"\nwritten to {args.out}")
    print(f"seed with: python env/seed_variants.py seed --fixture {args.out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
