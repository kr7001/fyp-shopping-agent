#!/usr/bin/env python3
"""Write the task file and the readings sidecar for an A+ market, every key computed from its
fixture.

The questions are the protocol's templates word for word (`generate_aplus.TEMPLATES`, from
docs/content/claim2-protocol.md, "Questions"): eight about the tee, five about the water, and
two the block should not plan, each after the instruction to open the brand's results page,
as every question since the first clothing market. Every key comes from the fixture's
variants through `generate_aplus.keys`, never typed, and where a key overlaps what the
fixture's `_instance` records the two are compared and the file is refused if they differ
(as `generate_apparel_v2_tasks.keys` does since a hand-written key once scored fifteen runs
against a market that no longer existed).

**Two readings.** Three questions say "offer" or "stock" of a size or pack and nothing that
settles which availability they mean, which is the box's rule for asking back
(`box/ambiguity.py`): tee-all-stocked, tee-count-stocked and water-all-stocked. A task's own
key is the menu reading, a sold-out variant counted as offered or stocked, as every key
since 8 October 2026. The sidecar holds the buyable reading, a sold-out variant not counted,
computed by the same rule as `generate_apparel_v2_tasks.buyable_reading`. The market's rule
`readings_differ` makes the two readings count different listings: on this market a sold-out
variant is the whole difference. "In stock and available to buy right now" and "can actually
be bought" settle the reading, so the questions that say them have one key.

**The exists-under limit** is `generate_aplus.exists_limit`: the whole-dollar part of the
midpoint between the two cheapest prices any tee listing can sell size M for. Exactly one
listing can sell it under that, the market's rule `limit_separates` refuses a market where
that fails, and `first_screen_misleads` puts that listing outside the first screen with a card
under the limit on it, so the yes is not visible from the first screen.

**The box field** says what the protocol asks the block to do with each question: plan it,
ask which reading is meant, or decline the two it should not plan. The kinds are the ones
the block gives the same questions on the first claim market. It is not yet checked against
the box, which does not read a second results page.

    python3 env/generate_aplus_tasks.py --fixture env/fixtures/aplus_dev.json \\
        --out experiments/tasks/tasks_aplus_dev.json --readings-out experiments/tasks/readings_aplus_dev.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import generate_aplus as aplus  # noqa: E402  (TEMPLATES, keys, exists_limit)
import generate_apparel as apparel  # noqa: E402  (from_price, buyable_price_for, price_for)

TASKS = REPO / "experiments" / "tasks"
FAMILY = "aplus"
# The questions with two readings, by the box's rule (`ambiguity.ask`, checked by the tests).
TWO_READINGS = ("tee-all-stocked", "tee-count-stocked", "water-all-stocked")
NOT_PLANNED = ("decline-delivery", "decline-taste")
BOX = {
    "tee-headline": ("plan", "results_page"),
    "tee-target-price": ("plan", "availability_bound"),
    "tee-cheapest-target": ("plan", "availability_bound"),
    "tee-all-stocked": ("ask", "refutation"),
    "tee-count-stocked": ("ask", "survey"),
    "tee-count-buyable": ("plan", "survey"),
    "tee-exists-under": ("plan", "exists_price"),
    "tee-top-3": ("plan", "topk_price"),
    "water-target-price": ("plan", "availability_bound"),
    "water-cheapest-target": ("plan", "availability_bound"),
    "water-all-stocked": ("ask", "refutation"),
    "water-count-buyable": ("plan", "survey"),
    "water-best-per-litre": ("plan", "rate_bound"),
    "decline-delivery": ("refuse", None),
    "decline-taste": ("refuse", None),
}


def first(listing: dict) -> str:
    """The token the scorer looks for: the seller's first word (`names_distinct`)."""
    return listing["seller"].split()[0]


def money(value: float) -> str:
    return f"${value:.2f}"


def wrap(text: str) -> list[str]:
    return textwrap.wrap(text, 88)


def unique(names: list[str]) -> list[str]:
    return [n for i, n in enumerate(names) if n not in names[:i]]


def checked_keys(fixture: dict) -> dict:
    """`generate_aplus.keys` from the variants, compared with `_instance` where they overlap,
    and refused when the market cannot give a key one answer."""
    families = fixture["families"]
    broken = aplus.market_check(families, fixture["_generated"]["brand"])
    if broken:
        raise SystemExit(f"the market breaks its own rules, so its keys are not single: {broken}")
    k = aplus.keys(families)
    tee, water = fixture["_instance"]["tee"], fixture["_instance"]["water"]
    overlaps = {
        "the tee winner": ((k["tee_winner"]["parent_sku"],
                            apparel.buyable_price_for(k["tee_winner"], aplus.TEE_TARGET)),
                           (tee["winner"]["sku"], tee["winner"]["price"])),
        "the cheapest tee card": (k["tee_cards"][0]["parent_sku"], tee["cheapest_card"]["sku"]),
        "the tee counts": ((k["tee_listed"], k["tee_buyable"], k["tee_sold_out"]),
                           (tee["listings_with_target"], tee["listings_target_buyable"],
                            tee["listings_target_sold_out"])),
        "the water winner": ((k["water_winner"]["parent_sku"],
                              apparel.buyable_price_for(k["water_winner"], aplus.WATER_TARGET)),
                             (water["winner"]["sku"], water["winner"]["price"])),
        "the cheapest water card": (k["water_card"]["parent_sku"], water["cheapest_card"]["sku"]),
        "the water counts": ((k["water_listed"], k["water_buyable"], k["water_sold_out"]),
                             (water["listings_with_target"], water["listings_target_buyable"],
                              water["listings_target_sold_out"])),
        "the best per litre": ((k["per_litre"]["parent_sku"], k["per_litre_rate"]),
                               (water["best_per_litre"]["sku"], water["best_per_litre"]["price_per_litre"])),
        "the limit": (k["limit"], fixture["_instance"]["exists_limit"]),
    }
    for what, (computed, recorded) in overlaps.items():
        if computed != recorded:
            raise SystemExit(f"{what} recomputed from the variants, {computed}, differs from "
                             f"_instance, {recorded}")
    return k


def tasks(fixture: dict) -> list[dict]:
    k = checked_keys(fixture)
    brand = fixture["_generated"]["brand"]
    tees = [f for f in fixture["families"] if f["product"] == aplus.TEE]
    waters = [f for f in fixture["families"] if f["product"] == aplus.WATER]
    size, pack = aplus.TEE_TARGET, aplus.WATER_TARGET
    tee_price = lambda l: apparel.buyable_price_for(l, size)  # noqa: E731
    water_price = lambda l: apparel.buyable_price_for(l, pack)  # noqa: E731
    card, winner = k["tee_cards"][0], k["tee_winner"]
    absent, sold_out = k["tee_absent_trap"], k["tee_sold_out_trap"]
    w_winner, w_card = k["water_winner"], k["water_card"]
    w_absent, w_sold_out = k["water_absent_trap"], k["water_sold_out_trap"]
    per_litre, rate = k["per_litre"], k["per_litre_rate"]
    witness, limit = k["witnesses"][0], k["limit"]
    top = k["top"]
    search = f"Go to {{base}}/catalogsearch/result/?q={brand} ."
    traps = lambda *ls: unique([first(l) for l in ls if l is not None])  # noqa: E731

    notes = {
        "tee-headline": "Control. Answerable from the results pages without opening anything: "
                        f"of the {len(tees)} tee listings, {card['seller']} advertises the lowest "
                        f"price, {money(apparel.from_price(card))}. It renders on page 1 and every "
                        f"tee card on page 2 is at least 8 per cent dearer (headline_on_page_1), so "
                        f"\"on the results page\" read as page 1 or as both pages gives this answer.",
        "tee-target-price": f"The price of size {size} appears only once it is chosen. "
                            f"{len(tees) - k['tee_listed']} tee listings do not offer it and "
                            f"{k['tee_sold_out']} offer it sold out. The lowest buyable is "
                            f"{winner['seller']}'s, {money(tee_price(winner))}.",
        "tee-cheapest-target": f"{winner['seller']} at {money(tee_price(winner))}. In front of it, "
                               + (f"{absent['seller']} advertises {money(apparel.from_price(absent))} "
                                  f"and does not sell size {size}" if absent else "no listing without the size")
                               + (f"; {sold_out['seller']} lists it at "
                                  f"{money(apparel.price_for(sold_out, size))} and cannot ship it"
                                  if sold_out else "") + ".",
        "tee-all-stocked": f"Menu reading (this key): {len(tees) - k['tee_listed']} of {len(tees)} tee "
                           f"listings do not list size {size}, so no. Buyable reading (the "
                           f"sidecar): {len(tees) - k['tee_buyable']} cannot sell it now, so no.",
        "tee-count-stocked": f"Menu reading (this key): {k['tee_listed']} tee listings list size "
                             f"{size}, sold out or not. Buyable reading (the sidecar): "
                             f"{k['tee_buyable']} can sell it now. The {k['tee_sold_out']} sold out "
                             f"are the difference.",
        "tee-count-buyable": f"{k['tee_buyable']} tee listings can sell size {size} now; "
                             f"{k['tee_sold_out']} more list it sold out.",
        "tee-exists-under": f"Yes. {witness['seller']} is the one tee listing that can sell size "
                            f"{size} under ${limit}, at {money(tee_price(witness))}. "
                            f"{len(k['looks_like_yes'])} others advertise under ${limit} and cannot. "
                            f"The limit is exists_limit's: the whole-dollar part of the midpoint "
                            f"between the two cheapest buyable size {size} prices.",
        "tee-top-3": "The three cheapest that can sell size M, in order: "
                     + ", ".join(f"{l['seller']} at {money(tee_price(l))}" for l in top)
                     + f". The next is {money(tee_price(k['top_next']))}, so the set is unique.",
        "water-target-price": f"The price of the {pack} appears only once it is chosen. "
                              f"{len(waters) - k['water_listed']} water listings do not offer it and "
                              f"{k['water_sold_out']} offer it sold out. The lowest buyable is "
                              f"{w_winner['seller']}'s, {money(water_price(w_winner))}; the lowest "
                              f"water card is {money(apparel.from_price(w_card))}.",
        "water-cheapest-target": f"{w_winner['seller']} at {money(water_price(w_winner))}. "
                                 f"{w_card['seller']} advertises the lowest water price, "
                                 f"{money(apparel.from_price(w_card))}, for a smaller pack."
                                 + (f" {w_sold_out['seller']} lists the {pack} at "
                                    f"{money(apparel.price_for(w_sold_out, pack))} and cannot ship it."
                                    if w_sold_out else ""),
        "water-all-stocked": f"Menu reading (this key): {len(waters) - k['water_listed']} of "
                             f"{len(waters)} water listings do not list the {pack}, so no. Buyable "
                             f"reading (the sidecar): {len(waters) - k['water_buyable']} cannot sell "
                             f"it now, so no.",
        "water-count-buyable": f"{k['water_buyable']} water listings can sell the {pack} now; "
                               f"{k['water_sold_out']} more list it sold out.",
        "water-best-per-litre": f"{per_litre['seller']}, at ${rate:.4f} a litre for its "
                                f"{k['per_litre_pack']['option']} ({money(k['per_litre_pack']['price'])}), "
                                f"each pack's litres its units times its volume, over packs that can "
                                f"be bought; the next seller's best is ${k['per_litre_runner_up_rate']:.4f}. "
                                f"Not the cheapest card ({w_card['seller']}) and not the cheapest "
                                f"{pack} ({w_winner['seller']}). {k['sold_out_rate_listing']['seller']} "
                                f"lists a pack at ${k['sold_out_rate']:.4f} a litre and cannot ship it.",
        "decline-delivery": "Push-back. Delivery time is not shown anywhere on this shop. No key.",
        "decline-taste": "Push-back. Taste is not shown anywhere on this shop. No key.",
    }
    expects = {
        "tee-headline": {"kind": "contains", "any": [first(card)], "price": apparel.from_price(card)},
        "tee-target-price": {"kind": "price", "value": tee_price(winner)},
        "tee-cheapest-target": {"kind": "contains", "any": [first(winner)],
                                "not_any": traps(absent, sold_out), "price": tee_price(winner)},
        "tee-all-stocked": {"kind": "boolean", "value": k["tee_listed"] == len(tees)},
        "tee-count-stocked": {"kind": "count", "value": k["tee_listed"]},
        "tee-count-buyable": {"kind": "count", "value": k["tee_buyable"]},
        "tee-exists-under": {"kind": "boolean", "value": True, "any": [first(witness)],
                             "not_any": [first(l) for l in k["looks_like_yes"]]},
        "tee-top-3": {"kind": "ranked",
                      "items": [{"any": [first(l)], "price": tee_price(l)} for l in top]},
        "water-target-price": {"kind": "price", "value": water_price(w_winner),
                               "trap": apparel.from_price(w_card)},
        "water-cheapest-target": {"kind": "contains", "any": [first(w_winner)],
                                  "not_any": traps(w_card, w_absent, w_sold_out),
                                  "price": water_price(w_winner)},
        "water-all-stocked": {"kind": "boolean", "value": k["water_listed"] == len(waters)},
        "water-count-buyable": {"kind": "count", "value": k["water_buyable"]},
        "water-best-per-litre": {"kind": "contains", "any": [first(per_litre)],
                                 "not_any": traps(*(l for l in (w_card, w_winner, k["sold_out_rate_listing"])
                                                    if l is not per_litre))},
        "decline-delivery": {"kind": "none"},
        "decline-taste": {"kind": "none"},
    }
    out = []
    for task_id, (product, template) in aplus.TEMPLATES.items():
        outcome, kind = BOX[task_id]
        out.append({
            "id": task_id, "family": FAMILY, "product": product,
            "gated": task_id not in ("tee-headline",) + NOT_PLANNED,
            "note": notes[task_id],
            "query": f"{search} {template.format(brand=brand, limit=limit)}",
            "expect": expects[task_id],
            "box": {"outcome": outcome, "kind": kind},
        })
    return out


def buyable_reading(fixture: dict) -> dict:
    """The scripted user's buyable reading of the three questions with two readings: a
    variant counts only if it can be bought now."""
    k = checked_keys(fixture)
    tees = sum(1 for f in fixture["families"] if f["product"] == aplus.TEE)
    waters = sum(1 for f in fixture["families"] if f["product"] == aplus.WATER)
    return {"buyable": {
        "tee-all-stocked": {"kind": "boolean", "value": k["tee_buyable"] == tees},
        "tee-count-stocked": {"kind": "count", "value": k["tee_buyable"]},
        "water-all-stocked": {"kind": "boolean", "value": k["water_buyable"] == waters},
    }}


def environment(fixture: dict) -> list[str]:
    """What the task file says about the shop the market lives in (`_environment`, which
    `suite.draw_id` hashes)."""
    generated, inst = fixture["_generated"], fixture["_instance"]
    prefix = generated["sku_prefix"]
    search = generated.get("search")
    seeded = (f"seeded on {search['seeded']}" if search else
              "not yet chosen by a recorded seed search")
    return wrap(
        f"Tees and bottled water under one brand ({generated['brand']}), {seeded} beside the "
        f"markets already in the shop, which it leaves as they were, under its own SKU prefix "
        f"and URL keys ({prefix}, {prefix.lower()}-NN.html). {inst['listings']} listings, "
        f"{generated['listings']['tee']} tees and {generated['listings']['water']} water, across "
        f"{inst['pages']} results pages at the shop's page size of {inst['page_size']}, no setting "
        f"changed. Three availability states for every size and pack: absent from the menu, "
        f"present but disabled because it is sold out (show_out_of_stock set to 1), or present "
        f"and buyable. Under the gated theme only the advertised price shows until a size or "
        f"pack is chosen.")


def spec(fixture: dict, fixture_name: str) -> dict:
    generated = fixture["_generated"]
    return {
        "_about": [
            f"Generated by env/generate_aplus_tasks.py from env/fixtures/{fixture_name}. Do not hand edit.",
            *wrap(f"Seed {generated['seed']}, tee draw {generated['attempts']['tee']}, water draw "
                  f"{generated['attempts']['water']}, brand {generated['brand']}, an A+ market "
                  f"(docs/content/claim2-protocol.md)."),
            *wrap("The protocol's question templates word for word, eight about the tee, five "
                  "about the water and two the block should not plan, every key computed from "
                  "the fixture's variants and checked against _instance where the two overlap. "
                  "The three questions with two readings keep the menu reading here; the "
                  "buyable reading is in the readings sidecar."),
            *wrap("\"box\" says what the protocol asks the block to do with each question. It "
                  "is not yet checked against the box, which reads one results page."),
            *wrap("\"fixture\" names the market's fixture, so the analysis tools read its ground "
                  "truth."),
        ],
        "_environment": environment(fixture),
        "base_url": "http://localhost:7770",
        "brand": generated["brand"],
        "fixture": fixture_name,
        "_instance": fixture["_instance"],
        "tasks": tasks(fixture),
    }


def readings(fixture: dict, fixture_name: str, tasks_name: str) -> dict:
    return {
        "_about": [
            *wrap(f"Computed by env/generate_aplus_tasks.py from env/fixtures/{fixture_name}: the "
                  f"scripted user's second reading of the three questions in {tasks_name} with "
                  f"two readings, used by suite.py --reading buyable and by verify_cells.py when "
                  f"a batch records that reading. Do not hand edit."),
            *wrap("The task's own expect is the menu reading: a sold-out size or pack counts as "
                  "offered or stocked. Here it does not: \"offer\" and \"stock\" are read as \"can "
                  "sell it now\"."),
        ],
        "readings": buyable_reading(fixture),
    }


def refused(fixture_path: pathlib.Path, fixture: dict, out: pathlib.Path,
            readings_out: pathlib.Path) -> str | None:
    """Why this may not be written, or None: the fixture is not an A+ market's under
    env/fixtures, or an output is a file of another market's. Kept apart from `main` so a test
    can ask it without writing."""
    if fixture_path.resolve().parent != (HERE / "fixtures").resolve():
        return "the fixture must be under env/fixtures, where the analysis tools look for it"
    if (fixture.get("_generated") or {}).get("generator") != "env/generate_aplus.py":
        return f"{fixture_path.name} is not an A+ market's fixture"
    for path in (out, readings_out):
        if path.exists():
            other = json.loads(path.read_text())
            named = other.get("fixture")
            if path == out and named != fixture_path.name:
                return f"{path.name} is the task file of {named or 'another market'}"
            if path == readings_out and fixture_path.name not in " ".join(other.get("_about", [])):
                return f"{path.name} is the readings of another market"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--readings-out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    why = refused(args.fixture, fixture, args.out, args.readings_out)
    if why:
        raise SystemExit(f"refusing: {why}")
    written = spec(fixture, args.fixture.name)
    sidecar = readings(fixture, args.fixture.name, args.out.name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(written, indent=2) + "\n")
    args.readings_out.write_text(json.dumps(sidecar, indent=2) + "\n")
    print(f"written: {args.out} ({len(written['tasks'])} tasks)")
    print(f"written: {args.readings_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
