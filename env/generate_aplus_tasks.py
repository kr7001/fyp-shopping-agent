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
variant is the whole difference. "Can actually be bought", "can actually supply" and
"available to buy" settle the reading, and a card advertises the cheapest variant that can be
bought, so every other question with a key has one reading.

Since 22 October 2026 the sidecar holds a buyable key for every keyed question, not only the
three: the model parser can lead any question it reads to the buyable reading, and
`suite.py` refuses a batch under it with a question that has none. Each is computed over
the market as bought (`as_bought`, every sold-out size and pack taken out of its menu), so
for the three it is their second key, and for the rest it is their own key computed a second
way, which must equal the task file's or nothing is written. The sidecar's `two_readings`
names the three, since being in the sidecar no longer says that a question has two.

**The exists-under limit** is `generate_aplus.exists_limit`: the whole-dollar part of the
midpoint between the two cheapest prices any tee listing can sell size M for. Exactly one
listing can sell it under that, the market's rule `limit_separates` refuses a market where
that fails, and `first_screen_misleads` puts that listing outside the first screen with a card
under the limit on it, so the yes is not visible from the first screen.

**The box field** says what the protocol asks the block to do with each question: plan it,
ask which reading is meant, or decline the two it should not plan. The kinds are the ones
the block gives the same questions on the first claim market. It is not yet checked against
the box, which does not read a second results page.

**The held-out rewordings** (since 22 October 2026, task F). With `--rewordings`, each
rewording in experiments/tasks/paraphrases_v2.json that keeps its template's meaning is a
task too (`reworded`), so one command writes the claim's task file for both: its id is
`rw-NN` from the rewording's id, it carries its template's id (`template`), product, gated
flag and keys, its expected outcome from the held-out file, which must be its template's,
and its query is the template's lead with the rewording after it, the market's brand and
limit filled in. Its template's wording as the rewording's author read it is held to the
task file's, so a template changed since is refused. The rewordings are read here by id,
template, meaning_kept and expected, and their texts only to be written into the queries:
nothing here prints one. They go into the claim market's task file, or for a test into a
file outside experiments/tasks/, never beside a development market's questions there, which
the free tests put the rules to (`refused`), so no rule or prompt is tuned on them (the
held-out file's own _about, LESSONS 19). The sidecar gives each its template's buyable key,
and names the rewordings of the three questions with two readings among them.

**The development rewordings** (since 23 October 2026, for the front door's pilot). With
`--rewordings experiments/tasks/paraphrases_v1.json`, the thirty rewordings of Thornwood's
clothing questions are used instead. They are in sample: the model parser's prompt v2 and its
normalisation were written from their failures (`parse_probe.IN_SAMPLE`). The set is known by
the digest tests/test_probe.py pins on its entries, never by its file name
(`is_development`). Each that keeps its meaning and rewords a question this market asks of
its tee, apparel-X where tee-X is a template here, is a task (`development_reworded`): id
pv1-NN, its template's id, product, gated flag, keys and box field, and its query the
template's lead with the rewording after it, Thornwood's brand word replaced by this
market's. Two that keep their template's form are still not tasks, because their template's
key would score a right answer wrong (`KEY_DOES_NOT_FIT`). Every rewording that is not a task
is in the task file's `_skipped`, with the reason. They go into a pilot's files in
experiments/tasks/pilot/ and nowhere else under experiments/tasks/, and never into a claim
market's (`refused`).

    python3 env/generate_aplus_tasks.py --fixture env/fixtures/aplus_dev.json \\
        --out experiments/tasks/tasks_aplus_dev.json --readings-out experiments/tasks/readings_aplus_dev.json
    python3 env/generate_aplus_tasks.py --fixture env/fixtures/<claim market>.json \\
        --out experiments/tasks/tasks_<market>.json --readings-out experiments/tasks/readings_<market>.json \\
        --rewordings experiments/tasks/paraphrases_v2.json
    python3 env/generate_aplus_tasks.py --fixture env/fixtures/aplus_dev.json \\
        --out experiments/tasks/pilot/tasks_pilot_v1rw_larchmere.json \\
        --readings-out experiments/tasks/pilot/readings_pilot_v1rw_larchmere.json \\
        --rewordings experiments/tasks/paraphrases_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import generate_aplus as aplus  # noqa: E402  (TEMPLATES, keys, exists_limit)
import generate_apparel as apparel  # noqa: E402  (from_price, buyable_price_for, price_for)
# After env/, so no module of experiments/ is found before this folder's own.
sys.path.insert(1, str(REPO / "experiments"))
import paths  # noqa: E402  (PILOT_TASKS)
import fixture_order  # noqa: E402  (the order claim.py reads where a key's listings render; no scipy)

TASKS = REPO / "experiments" / "tasks"
FAMILY = "aplus"
# A held-out rewording's task id, from its id in the held-out file.
REWORDING_ID = "rw-{id:02d}"
# The held-out file's expected outcome, in the box field's words.
EXPECTED = {"plan": "plan", "ask": "ask", "decline": "refuse"}

# The development rewordings (23 October 2026, for the front door's pilot): the thirty
# entries of experiments/tasks/paraphrases_v1.json, by the sha256 tests/test_probe.py pins on
# them, so that no other set, edited or held out, passes as them.
DEVELOPMENT_DIGEST = "0737b62164b56cc15b3685786211d9597808d7fafc498bad7c706aa439c6976d"
DEVELOPMENT_ID = "pv1-{id:02d}"
# Their audit's expected outcome, in the box field's words: ASK and REFUSE are outcomes, any
# other word is the kind of plan expected.
AUDIT_OUTCOME = {"ASK": "ask", "REFUSE": "refuse"}
# Development rewordings that keep their template's form, so meaning_kept is true, but whose
# template's key would score a right answer wrong, so they are not tasks. Read by hand from
# paraphrases_v1.json on 23 October 2026, when the file was first given keys, each by its id.
KEY_DOES_NOT_FIT = {
    11: "asks whether some seller lacks size M, so a right answer is yes, where its template "
        "asks whether every tee listing offers size M and its key wants no",
    30: "asks only what the cheapest tee costs, where its template's key also wants the listing "
        "named, so a right answer that gives the price alone would be scored wrong",
}
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


def as_bought(families: list[dict]) -> list[dict]:
    """The market as the buyable reading reads it: every size or pack that cannot be bought
    now taken out of its menu, so that "offer", "stock" and "list" count only what can be
    sold today. A card's price is unchanged, since a card advertises only what can be bought
    (`generate_apparel.from_price`)."""
    return [{**f, "variants": [v for v in f["variants"] if v["qty"] > 0]} for f in families]


def checked_keys(fixture: dict) -> dict:
    """`generate_aplus.keys` from the variants, compared with `_instance` where they overlap,
    and refused when the market cannot give a key one answer: every rule of the version the
    market was drawn under, its `_generated.version` (23 October 2026), so a market drawn under
    version 3 is held to `top_3_margin` here too, and development's, drawn under version 2, is
    not. A design-B fixture's keys are `checked_keys_b`."""
    if design_of(fixture) == aplus.DESIGN_B:
        return checked_keys_b(fixture)
    families = fixture["families"]
    broken = aplus.market_check(families, fixture["_generated"]["brand"], fixture["_generated"]["version"])
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


def tee_expects(answers: dict, shown: dict, tees: int) -> dict:
    """The eight tee questions' keys, as `expects_from` documents them: the part both designs
    share (24 October 2026, factored out of `expects_from`, which gives the same keys)."""
    size = aplus.TEE_TARGET
    tee_price = lambda l: apparel.buyable_price_for(l, size)  # noqa: E731
    traps = lambda *ls: unique([first(l) for l in ls if l is not None])  # noqa: E731
    card, winner, top = answers["tee_cards"][0], answers["tee_winner"], answers["top"]
    return {
        "tee-headline": {"kind": "contains", "any": [first(card)], "price": apparel.from_price(card)},
        "tee-target-price": {"kind": "price", "value": tee_price(winner)},
        "tee-cheapest-target": {"kind": "contains", "any": [first(winner)],
                                "not_any": traps(shown["tee_absent_trap"], shown["tee_sold_out_trap"]),
                                "price": tee_price(winner)},
        "tee-all-stocked": {"kind": "boolean", "value": answers["tee_listed"] == tees},
        "tee-count-stocked": {"kind": "count", "value": answers["tee_listed"]},
        "tee-count-buyable": {"kind": "count", "value": answers["tee_buyable"]},
        "tee-exists-under": {"kind": "boolean", "value": bool(answers["witnesses"]),
                             "any": [first(answers["witnesses"][0])],
                             "not_any": [first(l) for l in shown["looks_like_yes"]]},
        "tee-top-3": {"kind": "ranked",
                      "items": [{"any": [first(l)], "price": tee_price(l)} for l in top]},
    }


def expects_from(answers: dict, shown: dict, tees: int, waters: int) -> dict:
    """Every question's key. What a right answer says, its seller, price, count or yes, comes
    from `answers`, `generate_aplus.keys` of the market as the key's reading reads it. What a
    wrong one says (`not_any`, `trap`) comes from `shown`, the keys of the market as its pages
    show it: a reading changes what counts as offered, never which listings a reader of the
    pages names wrongly. `tees` and `waters` are how many listings each product has."""
    pack = aplus.WATER_TARGET
    water_price = lambda l: apparel.buyable_price_for(l, pack)  # noqa: E731
    traps = lambda *ls: unique([first(l) for l in ls if l is not None])  # noqa: E731
    w_winner, per_litre = answers["water_winner"], answers["per_litre"]
    # By SKU, not by identity: over the market as bought the answer is a copy of the listing
    # the market as shown names.
    other_than_answer = lambda l: l is not None and l["parent_sku"] != per_litre["parent_sku"]  # noqa: E731
    return {
        **tee_expects(answers, shown, tees),
        "water-target-price": {"kind": "price", "value": water_price(w_winner),
                               "trap": apparel.from_price(shown["water_card"])},
        "water-cheapest-target": {"kind": "contains", "any": [first(w_winner)],
                                  "not_any": traps(shown["water_card"], shown["water_absent_trap"],
                                                   shown["water_sold_out_trap"]),
                                  "price": water_price(w_winner)},
        "water-all-stocked": {"kind": "boolean", "value": answers["water_listed"] == waters},
        "water-count-buyable": {"kind": "count", "value": answers["water_buyable"]},
        "water-best-per-litre": {"kind": "contains", "any": [first(per_litre)],
                                 "not_any": traps(*filter(other_than_answer, (
                                     shown["water_card"], shown["water_winner"], shown["sold_out_rate_listing"])))},
        "decline-delivery": {"kind": "none"},
        "decline-taste": {"kind": "none"},
    }


# ---------------------------------------------------------------------------
# Design B (24 October 2026): the tee-only market's questions and keys

TWO_READINGS_B = ("tee-all-stocked", "tee-count-stocked")
NOT_PLANNED_B = ("decline-delivery", "decline-fit", "decline-scarcity")
# The box field for design B. tee-xs-price is tee-target-price's shape for size XS;
# tee-promo-check is a lookup on the named listing (box v19 names its kind; "lookup" here until
# then); the declines are the block's refusals.
BOX_B = {
    **{name: BOX[name] for name in ("tee-headline", "tee-target-price", "tee-cheapest-target", "tee-all-stocked",
                                    "tee-count-stocked", "tee-count-buyable", "tee-exists-under", "tee-top-3")},
    "tee-xs-price": ("plan", "availability_bound"),
    "tee-promo-check": ("plan", "lookup"),
    "decline-delivery": ("refuse", None),
    "decline-fit": ("refuse", None),
    "decline-scarcity": ("refuse", None),
}
# A held-out rewording's task id by the set it comes from: v2's ids are numbers, rw-NN; v3's
# read "v3-NN" and become rw3-NN, so the two never collide in one task file.
V3_ID = "rw3-{number:02d}"


def design_of(fixture: dict) -> str:
    return fixture["_generated"].get("design", aplus.DESIGN_A)


def results_order(fixture: dict) -> list[str]:
    """The order the results pages list the listings in, as the fixture records it: the live
    order its seed search accepted, else the predicted order (`fixture_order`)."""
    order, _ = fixture_order.fixture_order(fixture)
    return [sku.upper() for sku in order or []]


def named_listing(fixture: dict) -> dict:
    """The listing tee-promo-check names: the first in the results order that passes rules 11
    to 13 (`generate_aplus.promo_check_named`), which must be the one `_instance` recorded."""
    named = aplus.promo_check_named(fixture["families"], results_order(fixture))
    recorded = fixture["_instance"].get("promo_check") or {}
    if named is None or named["parent_sku"] != recorded.get("sku"):
        raise SystemExit(f"the named listing of tee-promo-check, {named and named['parent_sku']}, is not the one "
                         f"_instance records, {recorded.get('sku')}")
    return named


def checked_keys_b(fixture: dict) -> dict:
    """`checked_keys` for design B: the market's rules hold, and the keys recomputed from the
    variants agree with `_instance` where they overlap."""
    families = fixture["families"]
    broken = aplus.market_check_b(families, fixture["_generated"]["brand"], fixture["_generated"]["version"])
    if broken:
        raise SystemExit(f"the market breaks its own rules, so its keys are not single: {broken}")
    k = aplus.keys_b(families)
    inst, tee, xs = fixture["_instance"], fixture["_instance"]["tee"], fixture["_instance"]["xs"]
    named = named_listing(fixture)
    label = aplus.size_variant(named, aplus.XS_TARGET)
    overlaps = {
        "the tee winner": ((k["tee_winner"]["parent_sku"], apparel.buyable_price_for(k["tee_winner"], aplus.TEE_TARGET)),
                           (tee["winner"]["sku"], tee["winner"]["price"])),
        "the cheapest tee card": (k["tee_cards"][0]["parent_sku"], tee["cheapest_card"]["sku"]),
        "the tee counts": ((k["tee_listed"], k["tee_buyable"], k["tee_sold_out"]),
                           (tee["listings_with_target"], tee["listings_target_buyable"], tee["listings_target_sold_out"])),
        "the XS winner": ((k["xs_winner"]["parent_sku"], apparel.buyable_price_for(k["xs_winner"], aplus.XS_TARGET)),
                          (xs["winner"]["sku"], xs["winner"]["price"])),
        "the lowest promo figure": ((k["promo_trap"]["parent_sku"], k["promo_trap_figure"]),
                                    (inst["labels"]["lowest_promo"]["sku"], inst["labels"]["lowest_promo"]["label_price"])),
        "the named listing's label and price": ((label["label_price"], label["price"]),
                                                (inst["promo_check"]["promo"], inst["promo_check"]["price"])),
        "the limit": (k["limit"], inst["exists_limit"]),
    }
    for what, (computed, recorded) in overlaps.items():
        if computed != recorded:
            raise SystemExit(f"{what} recomputed from the variants, {computed}, differs from _instance, {recorded}")
    return k


def expects_from_b(answers: dict, shown: dict, tees: int, named: dict) -> dict:
    """Every design-B question's key (`expects_from`'s reading of `answers` and `shown`). The
    XS question's trap is the lowest promo figure, as the pages show it; the promo check's key
    is the named listing's real XS price, its label figure the trap, and `value` false: the
    label's claim does not hold (score v10's label_check)."""
    xs = aplus.XS_TARGET
    label = aplus.size_variant(named, xs)
    return {
        **tee_expects(answers, shown, tees),
        "tee-xs-price": {"kind": "price", "value": apparel.buyable_price_for(answers["xs_winner"], xs),
                         "trap": shown["promo_trap_figure"]},
        "tee-promo-check": {"kind": "label_check", "value": False, "price": label["price"], "trap": label["label_price"]},
        "decline-delivery": {"kind": "none"},
        "decline-fit": {"kind": "none"},
        "decline-scarcity": {"kind": "none"},
    }


def promo_text(figure: float) -> str:
    """The promo figure as the label renders it, two decimals, for {promo}."""
    return f"{figure:.2f}"


def tasks_b(fixture: dict) -> list[dict]:
    k = checked_keys_b(fixture)
    brand = fixture["_generated"]["brand"]
    families = fixture["families"]
    size, xs = aplus.TEE_TARGET, aplus.XS_TARGET
    tee_price = lambda l: apparel.buyable_price_for(l, size)  # noqa: E731
    card, winner = k["tee_cards"][0], k["tee_winner"]
    absent, sold_out = k["tee_absent_trap"], k["tee_sold_out_trap"]
    witness, limit, top = k["witnesses"][0], k["limit"], k["top"]
    xs_winner, xs_runner = k["xs_winner"], k["xs_runner_up"]
    trap, trap_figure = k["promo_trap"], k["promo_trap_figure"]
    named = named_listing(fixture)
    label = aplus.size_variant(named, xs)
    inst_xs = fixture["_instance"]["xs"]
    search = f"Go to {{base}}/catalogsearch/result/?q={brand} ."
    n = len(families)
    notes = {
        "tee-headline": f"Control. Answerable from the results pages without opening anything: of the {n} "
                        f"listings, {card['seller']} advertises the lowest price, {money(apparel.from_price(card))}. "
                        f"It renders on page 1 and every card on page 2 is at least 8 per cent dearer "
                        f"(headline_on_page_1), so \"on the results page\" read as page 1 or as both pages gives "
                        f"this answer.",
        "tee-target-price": f"The price of size {size} appears only once it is chosen. {n - k['tee_listed']} listings "
                            f"do not offer it and {k['tee_sold_out']} offer it sold out. The lowest buyable is "
                            f"{winner['seller']}'s, {money(tee_price(winner))}.",
        "tee-cheapest-target": f"{winner['seller']} at {money(tee_price(winner))}. In front of it, "
                               + (f"{absent['seller']} advertises {money(apparel.from_price(absent))} and does not sell "
                                  f"size {size}" if absent else "no listing without the size")
                               + (f"; {sold_out['seller']} lists it at {money(apparel.price_for(sold_out, size))} and "
                                  f"cannot ship it" if sold_out else "") + ".",
        "tee-all-stocked": f"Menu reading (this key): {n - k['tee_listed']} of {n} listings do not list size {size}, "
                           f"so no. Buyable reading (the sidecar): {n - k['tee_buyable']} cannot sell it now, so no.",
        "tee-count-stocked": f"Menu reading (this key): {k['tee_listed']} listings list size {size}, sold out or not. "
                             f"Buyable reading (the sidecar): {k['tee_buyable']} can sell it now. The {k['tee_sold_out']} "
                             f"sold out are the difference. Scarcity labels on some M options claim a count the shop "
                             f"never shows; they change no count.",
        "tee-count-buyable": f"{k['tee_buyable']} listings can sell size {size} now; {k['tee_sold_out']} more list it "
                             f"sold out.",
        "tee-exists-under": f"Yes. {witness['seller']} is the one listing that can sell size {size} under ${limit}, at "
                            f"{money(tee_price(witness))}. {len(k['looks_like_yes'])} others advertise under ${limit} "
                            f"and cannot. The limit is exists_limit's: the whole-dollar part of the midpoint between "
                            f"the two cheapest buyable size {size} prices.",
        "tee-top-3": f"The three cheapest that can sell size {size}, in order: "
                     + ", ".join(f"{l['seller']} at {money(tee_price(l))}" for l in top)
                     + f". The next is {money(tee_price(k['top_next']))}, so the set is unique.",
        "tee-xs-price": f"The promo trap. The lowest buyable size {xs} is {xs_winner['seller']}'s, "
                        f"{money(apparel.buyable_price_for(xs_winner, xs))}; the next is "
                        f"{money(apparel.buyable_price_for(xs_runner, xs))}. {len(k['promo'])} listings label their {xs} "
                        f"with a promo figure below its real price; the lowest, {trap['seller']}'s "
                        f"{money(trap_figure)}, is below every real buyable {xs} price, and that listing's {xs} really "
                        f"costs {money(apparel.price_for(trap, xs))}. " +
                        (f"{inst_xs['cheapest_sold_out']['seller']} lists {xs} sold out at "
                         f"{money(inst_xs['cheapest_sold_out']['price'])}, below the answer, and cannot ship it. "
                         if inst_xs.get("cheapest_sold_out") else "") +
                        f"No card advertises the answer (xs_answer_not_on_cards).",
        "tee-promo-check": f"The label check. {named['seller']}'s size menu reads {label['label']!r}; its {xs} really "
                           f"costs {money(label['price'])} once chosen, and its card advertises "
                           f"{money(apparel.from_price(named))}, below the label's figure, so the answer is read only "
                           f"after choosing {xs}. The key is no, with the real price; the label's figure is the trap. "
                           f"The listing is the first in results order whose {xs} carries a promo label and passes "
                           f"rules 11 to 13 (promo_check_choice).",
        "decline-delivery": "Push-back. Delivery time is not shown anywhere on this shop. No key.",
        "decline-fit": "Push-back. The shop shows a size menu, a price once a size is chosen and whether a size can "
                       "be bought; it shows nothing about fit, and no title or label carries fit advice "
                       "(no_fit_text). No key.",
        "decline-scarcity": f"Push-back. The shop shows no stock counts. {len(k['scarcity'])} listings label their "
                            f"{size} \"Only N left!\"; the labels are not checked stock and no question's key depends "
                            f"on them. No key.",
    }
    expects = expects_from_b(k, k, n, named)
    out = []
    for task_id, (product, template) in aplus.B_TEMPLATES.items():
        outcome, kind = BOX_B[task_id]
        out.append({
            "id": task_id, "family": FAMILY, "product": product,
            "gated": task_id not in ("tee-headline",) + NOT_PLANNED_B,
            "note": notes[task_id],
            "query": f"{search} " + template.format(brand=brand, limit=limit, seller=named["seller"],
                                                   promo=promo_text(label["label_price"])),
            "expect": expects[task_id],
            "box": {"outcome": outcome, "kind": kind},
        })
    return out


def rewording_task_id(entry_id) -> tuple[str, str]:
    """A held-out rewording's task id and its set: v2's numbered entries are rw-NN, v3's
    "v3-NN" entries rw3-NN (the coordinator's note of 24 October 2026)."""
    if isinstance(entry_id, int):
        return REWORDING_ID.format(id=entry_id), "v2"
    matched = re.fullmatch(r"v3-(\d+)", str(entry_id))
    if matched is None:
        raise SystemExit(f"rewording id {entry_id!r} is neither a v2 number nor a v3 id")
    return V3_ID.format(number=int(matched.group(1))), "v3"


def reworded_b(templates: list[dict], held_out: dict, brand: str, limit: int, named: dict) -> tuple[list[dict], list[dict]]:
    """A task for each held-out rewording that fits a design-B template, and every other entry
    in `_skipped` with why, by id and never by text (24 October 2026). Skipped: an entry whose
    template is null (reading-test-only, with its `ask_kind`), one that does not keep its
    template's meaning, one whose template this market does not ask (the water's, decline-
    taste), and one expected to be handled other than its template, whose key would be a
    person's to decide. Refused outright: a template worded other than its author read it,
    since its keys may not apply. The query is the template's lead with the rewording after it,
    the market's brand, limit, named seller and promo figure filled in."""
    by_id = {task["id"]: task for task in templates}
    label = aplus.size_variant(named, aplus.XS_TARGET)
    fill = dict(brand=brand, limit=limit, seller=named["seller"], promo=promo_text(label["label_price"]))
    out, skipped = [], []
    for entry in held_out["paraphrases"]:
        template = entry.get("template")
        why = None
        if template is None:
            why = "reading-test-only: its template is null" + (f" (ask_kind {entry['ask_kind']})" if entry.get("ask_kind") else "")
        elif not entry["meaning_kept"]:
            why = "does not keep its template's meaning (meaning_kept false)"
        elif template not in by_id:
            why = f"rewords {template}, which this market does not ask"
        if why:
            skipped.append({"rewording": entry["id"], "template": template, "why": why})
            continue
        task = by_id[template]
        lead, wording = task["query"].split(" . ", 1)
        if entry["template_text"].format(**fill) != wording:
            raise SystemExit(f"rewording {entry['id']}'s template, {template}, is not worded as its author read it, "
                             f"so its keys may not apply")
        outcome, kind = BOX_B[template]
        if EXPECTED[entry["expected"]] != outcome:
            skipped.append({"rewording": entry["id"], "template": template,
                            "why": f"expected to {entry['expected']} where its template is to {outcome}, so which "
                                   f"key applies is for a person to decide"})
            continue
        task_id, held = rewording_task_id(entry["id"])
        out.append({
            "id": task_id, "family": FAMILY, "product": task["product"], "gated": task["gated"],
            "template": template, "rewording": entry["id"], "held_out": held,
            "note": f"Held-out rewording {entry['id']} of {template} (paraphrases_{held}.json), which keeps its "
                    f"meaning, so its template's keys apply.",
            "query": f"{lead} . {entry['text'].format(**fill)}",
            "expect": task["expect"],
            "box": {"outcome": outcome, "kind": kind},
        })
    return out, skipped


def rewordings_of_b(templates: list[dict], files: list[dict], fixture: dict) -> tuple[list[dict], list[dict]]:
    """The tasks every rewording file adds to a design-B task file, and the entries skipped: the
    development set as for design A (`development_reworded`), a held-out set by `reworded_b`.
    Two files whose task ids collide are refused."""
    brand = fixture["_generated"]["brand"]
    limit = checked_keys_b(fixture)["limit"]
    named = named_listing(fixture)
    out, skipped = [], []
    for held_out in files:
        if is_development(held_out):
            tasks_, left = development_reworded(templates, held_out, brand)
            left = [{**entry, "why": entry["why"]} for entry in left]
        else:
            if any("template_text" not in entry for entry in held_out["paraphrases"] if entry.get("template")):
                raise SystemExit("these rewordings are not the development set paraphrases_v1.json pins, and they "
                                 "have no template_text, so which key each may take is unknown")
            tasks_, left = reworded_b(templates, held_out, brand, limit, named)
        if {t["id"] for t in tasks_} & {t["id"] for t in out}:
            raise SystemExit("two rewording files give the same task ids")
        out += tasks_
        skipped += left
    return out, skipped


def tasks(fixture: dict) -> list[dict]:
    if design_of(fixture) == aplus.DESIGN_B:
        return tasks_b(fixture)
    k = checked_keys(fixture)
    brand = fixture["_generated"]["brand"]
    tees = [f for f in fixture["families"] if f["product"] == aplus.TEE]
    waters = [f for f in fixture["families"] if f["product"] == aplus.WATER]
    size, pack = aplus.TEE_TARGET, aplus.WATER_TARGET
    tee_price = lambda l: apparel.buyable_price_for(l, size)  # noqa: E731
    water_price = lambda l: apparel.buyable_price_for(l, pack)  # noqa: E731
    card, winner = k["tee_cards"][0], k["tee_winner"]
    absent, sold_out = k["tee_absent_trap"], k["tee_sold_out_trap"]
    w_winner, w_card, w_sold_out = k["water_winner"], k["water_card"], k["water_sold_out_trap"]
    per_litre, rate = k["per_litre"], k["per_litre_rate"]
    witness, limit = k["witnesses"][0], k["limit"]
    top = k["top"]
    search = f"Go to {{base}}/catalogsearch/result/?q={brand} ."

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
    # The task's own keys: the market as shown, the menu reading where a question has two.
    expects = expects_from(k, k, len(tees), len(waters))
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


def reworded(templates: list[dict], held_out: dict, brand: str, limit: int) -> list[dict]:
    """A task for each held-out rewording that keeps its template's meaning, with its
    template's keys (`--rewordings`, 22 October 2026). Refused when a rewording names a
    template the task file does not hold, when its template's wording as its author read it
    is not the task file's, so its keys would be another question's, or when the block is
    expected to do with it other than with its template, so its reading would be a person's
    to decide. No text is printed: the reason names the rewording by its id."""
    by_id = {task["id"]: task for task in templates}
    out = []
    for entry in held_out["paraphrases"]:
        if not entry["meaning_kept"]:
            continue
        template = by_id.get(entry["template"])
        if template is None:
            raise SystemExit(f"rewording {entry['id']} rewords {entry['template']!r}, which the task "
                             f"file does not hold")
        lead, wording = template["query"].split(" . ", 1)
        if entry["template_text"].format(brand=brand, limit=limit) != wording:
            raise SystemExit(f"rewording {entry['id']}'s template, {entry['template']}, is not worded "
                             f"as its author read it, so its keys may not apply")
        outcome, kind = BOX[entry["template"]]
        if EXPECTED[entry["expected"]] != outcome:
            # A rewording that keeps its template's meaning keeps what the block should do with
            # it, as all thirty in the file of 22 October 2026 do. One that did not would leave
            # which reading it has, and so which key, for a person to decide.
            raise SystemExit(f"rewording {entry['id']} is expected to {entry['expected']} where its "
                             f"template, {entry['template']}, is to {outcome}, so which key applies "
                             f"is for a person to decide")
        out.append({
            "id": REWORDING_ID.format(id=entry["id"]), "family": FAMILY, "product": template["product"],
            "gated": template["gated"], "template": entry["template"], "rewording": entry["id"],
            "note": f"Held-out rewording {entry['id']} of {entry['template']} (paraphrases_v2.json), which "
                    f"keeps its meaning, so its template's keys apply.",
            "query": f"{lead} . {entry['text'].format(brand=brand, limit=limit)}",
            "expect": template["expect"],
            "box": {"outcome": EXPECTED[entry["expected"]], "kind": kind if entry["expected"] != "decline" else None},
        })
    return out


def entries_digest(entries: list[dict]) -> str:
    """The sha256 of a rewording file's entries, as tests/test_probe.py computes it."""
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def is_development(rewordings: dict) -> bool:
    """Whether a rewording file holds the development set, paraphrases_v1.json's thirty
    entries unchanged, by their digest (23 October 2026)."""
    return entries_digest(rewordings.get("paraphrases") or []) == DEVELOPMENT_DIGEST


def development_reworded(templates: list[dict], development: dict, brand: str) -> tuple[list[dict], list[dict]]:
    """A task for each development rewording that keeps its template's meaning and rewords a
    question this market asks of its tee (apparel-X as tee-X), with that template's keys, and
    every other rewording with the reason it is not one (23 October 2026, for the front
    door's pilot). Thornwood's brand word becomes this market's, and the query is the
    template's lead with the rewording after it. Refused, by id, when a rewording does not
    name the brand it was written for, or when its audit expected the box to do with it
    other than with its template here."""
    by_id = {task["id"]: task for task in templates}
    searched = re.search(r"[?&]q=([A-Za-z]+)", development["lead"])
    if searched is None:
        raise SystemExit("the development rewordings' lead searches for no brand")
    old = searched.group(1)
    out, skipped = [], []
    for entry in development["paraphrases"]:
        rewords = entry["template"]
        mapped = "tee-" + rewords[len("apparel-"):] if rewords.startswith("apparel-") else None
        template = by_id.get(mapped)
        why = None
        if not entry["meaning_kept"]:
            why = f"does not keep its template's meaning: {entry.get('meaning_differs')}"
        elif template is None:
            why = f"rewords {rewords}, and this market asks no {mapped or 'tee question like it'}"
        elif entry["id"] in KEY_DOES_NOT_FIT:
            why = f"its template's key does not fit: it {KEY_DOES_NOT_FIT[entry['id']]}"
        if why:
            skipped.append({"rewording": entry["id"], "template": rewords, "why": why})
            continue
        text, named = re.subn(rf"\b{re.escape(old)}\b", brand, entry["text"])
        if not named:
            raise SystemExit(f"rewording {entry['id']} does not name {old}, so it would not ask "
                             f"about this market once re-branded")
        audit = entry["audit_expected"]
        outcome, kind = AUDIT_OUTCOME.get(audit), None
        if outcome is None:
            outcome, kind = "plan", audit
        if outcome != template["box"]["outcome"] or (kind is not None and kind != template["box"]["kind"]):
            raise SystemExit(f"rewording {entry['id']}'s audit expected {audit} where its template "
                             f"here, {mapped}, is to {template['box']['outcome']}, so which key "
                             f"applies is for a person to decide")
        lead = template["query"].split(" . ", 1)[0]
        out.append({
            "id": DEVELOPMENT_ID.format(id=entry["id"]), "family": FAMILY, "product": template["product"],
            "gated": template["gated"], "template": mapped, "rewording": entry["id"],
            "note": f"Development rewording {entry['id']} of {rewords} (paraphrases_v1.json, in sample), "
                    f"written for {old} and re-branded to {brand}, asked here as {mapped}, whose keys "
                    f"apply because it keeps that question's meaning.",
            "query": f"{lead} . {text}",
            "expect": template["expect"],
            "box": template["box"],
        })
    return out, skipped


def rewordings_of(templates: list[dict], rewordings: dict, brand: str, limit: int) -> tuple[list[dict], list[dict] | None]:
    """The tasks a rewording file adds, and for the development set the rewordings it
    leaves out with why (`development_reworded`); for any other set, the held-out
    rewordings (`reworded`), with None. A file in the development set's shape whose entries
    are not that set is refused, since whose keys each may take is then unknown."""
    if is_development(rewordings):
        return development_reworded(templates, rewordings, brand)
    if any("template_text" not in entry for entry in rewordings["paraphrases"]):
        raise SystemExit("these rewordings are not the development set paraphrases_v1.json pins, "
                         "and they have no template_text, so which key each may take is unknown")
    return reworded(templates, rewordings, brand, limit), None


def two_readings_of(fixture: dict) -> tuple[str, ...]:
    """The questions with two readings in a fixture's design: three in design A, two in B."""
    return TWO_READINGS_B if design_of(fixture) == aplus.DESIGN_B else TWO_READINGS


def reading_problems(own: dict, bought: dict, two_readings: tuple[str, ...] = TWO_READINGS) -> list[str]:
    """The questions with one reading whose key over the market as bought is not their own:
    a key that counted a sold-out variant where its question cannot mean one."""
    return [task_id for task_id in own if task_id not in two_readings and own[task_id] != bought[task_id]]


def buyable_reading(fixture: dict) -> dict:
    """The scripted user's buyable reading of every keyed question, a variant counted only if
    it can be bought now: each key over the market as bought (`as_bought`), with the wrong
    answers it names from the market as shown. For the three questions with two readings it
    is their second key. The rest settle the reading in their words ("can actually be
    bought", "can actually supply", "available to buy") or ask what a card advertises, the
    cheapest variant that can be bought, so it is their own key computed a second way, and
    nothing is written if the two differ (`reading_problems`). Design B: its two, and the
    same recomputation, over its own keys (`expects_from_b`)."""
    k = checked_keys(fixture)
    families = fixture["families"]
    if design_of(fixture) == aplus.DESIGN_B:
        named = named_listing(fixture)
        own = expects_from_b(k, k, len(families), named)
        bought = expects_from_b(aplus.keys_b(as_bought(families)), k, len(families), named)
    else:
        tees = sum(1 for f in families if f["product"] == aplus.TEE)
        waters = sum(1 for f in families if f["product"] == aplus.WATER)
        own = expects_from(k, k, tees, waters)
        bought = expects_from(aplus.keys(as_bought(families)), k, tees, waters)
    differ = reading_problems(own, bought, two_readings_of(fixture))
    if differ:
        raise SystemExit(f"{', '.join(differ)}: the key over the market as bought differs from the "
                         f"task's own, and the question has one reading, so one of them counts a "
                         f"variant that cannot be bought")
    return {"buyable": {task_id: key for task_id, key in bought.items() if key["kind"] != "none"}}


def environment(fixture: dict) -> list[str]:
    """What the task file says about the shop the market lives in (`_environment`, which
    `suite.draw_id` hashes)."""
    generated, inst = fixture["_generated"], fixture["_instance"]
    prefix = generated["sku_prefix"]
    search = generated.get("search")
    seeded = (f"seeded on {search['seeded']}" if search else
              "not yet chosen by a recorded seed search")
    if design_of(fixture) == aplus.DESIGN_B:
        return wrap(
            f"Tees under one brand ({generated['brand']}), {seeded} beside the markets already in the "
            f"shop, which it leaves as they were, under its own SKU prefix and URL keys ({prefix}, "
            f"{prefix.lower()}-NN.html). {inst['listings']} listings from distinct sellers across "
            f"{inst['pages']} results pages at the shop's page size of {inst['page_size']}, no setting "
            f"changed. Six sizes, {', '.join(inst['sizes'])}, each absent from the menu, present but "
            f"disabled because it is sold out (show_out_of_stock set to 1), or present and buyable. Some "
            f"size-menu options carry a label: a promo figure on XS that disagrees with the price shown "
            f"after choosing it, or a stock claim on M that the shop never shows a count for. Under the "
            f"gated theme only the advertised price shows until a size is chosen.")
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


def spec_b(fixture: dict, fixture_name: str, files: list[dict]) -> dict:
    """The task file of a design-B market: its thirteen templates, then the rewordings every
    file in `files` adds (`rewordings_of_b`), the entries skipped listed with why."""
    generated = fixture["_generated"]
    templates = tasks_b(fixture)
    rewordings, skipped = rewordings_of_b(templates, files, fixture) if files else ([], [])
    sets = sorted({t.get("held_out", "v1") for t in rewordings})
    return {
        "_about": [
            f"Generated by env/generate_aplus_tasks.py from env/fixtures/{fixture_name}. Do not hand edit.",
            *wrap(f"Seed {generated['seed']}, draw {generated['attempts']['tee']}, brand {generated['brand']}, "
                  f"the tee-only market of design B (docs/content/claim2-handover.md, section 3; "
                  f"env/generate_aplus.py version {generated['version']})."),
            *wrap("The question templates word for word: the eight tee questions of the A+ protocol, "
                  "tee-xs-price and tee-promo-check, and three the block should not plan (delivery, fit, "
                  "scarcity). Every key is computed from the fixture's variants and checked against "
                  "_instance where the two overlap. The two questions with two readings keep the menu "
                  "reading here; the buyable reading is in the readings sidecar."),
            *wrap("tee-xs-price's trap is the lowest promo figure in a size menu; tee-promo-check names the "
                  "first listing in results order whose XS carries a promo label and whose card is below "
                  "it, and its key is no, with the real price (score v10's label_check)."),
            *wrap("\"box\" says what the protocol asks the block to do with each question. \"fixture\" names "
                  "the market's fixture, so the analysis tools read its ground truth."),
            *(wrap(f"Then {len(rewordings)} held-out rewordings from paraphrases_{' and paraphrases_'.join(sets)}.json, "
                   f"those that keep a template this market asks, each a task with its template's keys, its id "
                   f"rw-NN (v2) or rw3-NN (v3) and the template's id under \"template\". The other "
                   f"{len(skipped)} entries are in _skipped, each with the reason. Only the claim run puts the "
                   f"block to them: no free test or probe reads their queries, and nothing is tuned on them "
                   f"(LESSONS 19).") if rewordings or skipped else []),
        ],
        "_environment": environment(fixture),
        "base_url": "http://localhost:7770",
        "brand": generated["brand"],
        "fixture": fixture_name,
        "_instance": fixture["_instance"],
        **({"_skipped": skipped} if files else {}),
        "tasks": templates + rewordings,
    }


def readings_b(fixture: dict, fixture_name: str, tasks_name: str, files: list[dict]) -> dict:
    keys = buyable_reading(fixture)
    two = list(TWO_READINGS_B)
    if files:
        for task in rewordings_of_b(tasks_b(fixture), files, fixture)[0]:
            if task["template"] in keys["buyable"]:
                keys["buyable"][task["id"]] = keys["buyable"][task["template"]]
            if task["template"] in TWO_READINGS_B:
                two.append(task["id"])
    return {
        "_about": [
            *wrap(f"Computed by env/generate_aplus_tasks.py from env/fixtures/{fixture_name}: the scripted "
                  f"user's buyable reading of every keyed question in {tasks_name}, used by suite.py "
                  f"--reading buyable or own, by the model parser, which can lead any question it reads to "
                  f"this reading, and by verify_cells.py when a run records it. Do not hand edit."),
            *wrap("Here a size counts only if it can be bought now. The questions in two_readings say "
                  "\"offer\", and their own expect is the menu reading, a sold-out size counted as offered: "
                  "here is their second key. The others say \"can actually be bought\", \"can actually "
                  "supply\" or \"available to buy\", ask what a card advertises, or look up one named "
                  "listing: here is their own key, computed again over the market with every sold-out "
                  "variant taken out, and checked equal to it."),
            *(wrap("The held-out rewordings, rw-NN and rw3-NN, are described by their templates and not by "
                   "the words above: each keeps its template's meaning, so it has its template's key here "
                   "and is in two_readings where its template is.") if files else []),
        ],
        "two_readings": two,
        "readings": keys,
    }


def spec(fixture: dict, fixture_name: str, held_out: dict | list[dict] | None = None) -> dict:
    generated = fixture["_generated"]
    if design_of(fixture) == aplus.DESIGN_B:
        return spec_b(fixture, fixture_name, as_files(held_out))
    templates = tasks(fixture)
    rewordings, skipped = (rewordings_of(templates, held_out, generated["brand"], checked_keys(fixture)["limit"])
                           if held_out is not None else ([], None))
    development = skipped is not None
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
            *(wrap(f"Then {len(rewordings)} held-out rewordings from experiments/tasks/paraphrases_v2.json, "
                   f"those that keep their template's meaning, each a task with its template's keys, "
                   f"id rw-NN and the template's id under \"template\". Only the claim run puts the "
                   f"block to them: no free test or probe reads their queries, and nothing is tuned "
                   f"on them (LESSONS 19).") if held_out is not None and not development else []),
            *(wrap(f"Then {len(rewordings)} development rewordings from experiments/tasks/paraphrases_v1.json, "
                   f"written for Thornwood's clothing questions and in sample (the model parser's prompt "
                   f"v2 and its normalisation were written from them), each that keeps its meaning and "
                   f"rewords a question asked here of the tee, re-branded to {generated['brand']}: a task "
                   f"with its template's keys, id pv1-NN and the template's id under \"template\". The "
                   f"other {len(skipped)} are in _skipped, each with the reason. For a pilot only: no "
                   f"claim is made on them (LESSONS 19).") if development else []),
        ],
        "_environment": environment(fixture),
        "base_url": "http://localhost:7770",
        "brand": generated["brand"],
        "fixture": fixture_name,
        "_instance": fixture["_instance"],
        **({"_skipped": skipped} if development else {}),
        "tasks": templates + rewordings,
    }


def as_files(held_out: dict | list[dict] | None) -> list[dict]:
    """The rewording files given, as a list: design B takes several (v2 and v3 together)."""
    if held_out is None:
        return []
    return list(held_out) if isinstance(held_out, list) else [held_out]


def readings(fixture: dict, fixture_name: str, tasks_name: str, held_out: dict | list[dict] | None = None) -> dict:
    if design_of(fixture) == aplus.DESIGN_B:
        return readings_b(fixture, fixture_name, tasks_name, as_files(held_out))
    keys = buyable_reading(fixture)
    two = list(TWO_READINGS)
    development = held_out is not None and is_development(held_out)
    if held_out is not None:
        # A rewording keeps its template's meaning, so its keys are its template's under
        # either reading, and it has two readings where its template has.
        generated = fixture["_generated"]
        for task in rewordings_of(tasks(fixture), held_out, generated["brand"], checked_keys(fixture)["limit"])[0]:
            if task["template"] in keys["buyable"]:
                keys["buyable"][task["id"]] = keys["buyable"][task["template"]]
            if task["template"] in TWO_READINGS:
                two.append(task["id"])
    return {
        "_about": [
            *wrap(f"Computed by env/generate_aplus_tasks.py from env/fixtures/{fixture_name}: the "
                  f"scripted user's buyable reading of every keyed question in {tasks_name}, used "
                  f"by suite.py --reading buyable, by the model parser, which can lead any "
                  f"question it reads to this reading, and by verify_cells.py when a run records "
                  f"it. Do not hand edit."),
            *wrap("Here a size or pack counts only if it can be bought now. The questions in "
                  "two_readings say \"offer\" or \"stock\", and their own expect is the menu "
                  "reading, a sold-out size or pack counted as offered or stocked: here is their "
                  "second key. The others say \"can actually be bought\", \"can actually supply\" "
                  "or \"available to buy\", or ask what a card advertises, which is the cheapest "
                  "variant that can be bought: here is their own key, computed again over the "
                  "market with every sold-out variant taken out, and checked equal to it."),
            *(wrap("The held-out rewordings, rw-NN, are described by their templates and not by "
                   "the words above: each keeps its template's meaning, so it has its template's "
                   "key here and is in two_readings where its template is.")
              if held_out is not None and not development else []),
            *(wrap("The development rewordings, pv1-NN, are described by their templates and not by "
                   "the words above: each keeps its template's meaning, so it has its template's "
                   "key here and is in two_readings where its template is.") if development else []),
        ],
        "two_readings": two,
        "readings": keys,
    }


def refused(fixture_path: pathlib.Path, fixture: dict, out: pathlib.Path,
            readings_out: pathlib.Path, rewordings: bool = False, development: bool = False) -> str | None:
    """Why this may not be written, or None: the fixture is not an A+ market's under
    env/fixtures, an output is a file of another market's, or the held-out rewordings would
    go beside a development market's questions in experiments/tasks/. `development` says the
    rewordings are the development set (`is_development`, 23 October 2026): those may go into
    a pilot's files in experiments/tasks/pilot/ on a development market, and never into a
    claim market's. Kept apart from `main` so a test can ask it without writing."""
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
    # The development rewordings are in sample, the set the model parser's prompt was written
    # from, so they never go into a claim market's task file, whose rewordings are its
    # held-out test. On a development market a pilot's files in experiments/tasks/pilot/ may
    # hold them, where no claim reads them; anywhere else under experiments/tasks/ the rule
    # below holds for them too (23 October 2026).
    if rewordings and development:
        if fixture["_generated"].get("phrasings") != "development":
            return ("the development rewordings are in sample, so they never go into a claim "
                    "market's task file")
        pilot = paths.PILOT_TASKS.resolve()
        if all(path.resolve().parent == pilot for path in (out, readings_out)):
            return None
        for path in (out, readings_out):
            if TASKS.resolve() in path.resolve().parents:
                return (f"{path.name} would put the development rewordings beside a development "
                        f"market's questions; a pilot's files go in experiments/tasks/pilot/")
        return None
    # The rewordings go into the claim market's task file, or for a test into a file outside
    # experiments/tasks/. A development market's task file there is the one the free tests and
    # probes put the rules to, which would tune them on the held-out set (LESSONS 19,
    # 22 October 2026).
    if rewordings and fixture["_generated"].get("phrasings") == "development":
        for path in (out, readings_out):
            if TASKS.resolve() in path.resolve().parents:
                return (f"{path.name} would put the held-out rewordings beside a development "
                        f"market's questions, where the free tests put the rules to them")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--readings-out", type=pathlib.Path, required=True)
    parser.add_argument("--rewordings", type=pathlib.Path, default=None, nargs="+",
                        help="experiments/tasks/paraphrases_v2.json: add each held-out rewording "
                             "that keeps its template's meaning, with its template's keys. "
                             "experiments/tasks/paraphrases_v1.json, the development set, for a "
                             "pilot's files in experiments/tasks/pilot/ only. A design-B market "
                             "takes several files, paraphrases_v2.json and paraphrases_v3.json")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text())
    files = [json.loads(path.read_text()) for path in args.rewordings or []]
    if len(files) > 1 and design_of(fixture) != aplus.DESIGN_B:
        parser.error("a design-A market takes one rewording file")
    held_out = (files if design_of(fixture) == aplus.DESIGN_B else files[0]) if files else None
    development = bool(files) and all(is_development(f) for f in files)
    why = refused(args.fixture, fixture, args.out, args.readings_out,
                  rewordings=bool(files), development=development)
    if why:
        raise SystemExit(f"refusing: {why}")
    written = spec(fixture, args.fixture.name, held_out)
    sidecar = readings(fixture, args.fixture.name, args.out.name, held_out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(written, indent=2) + "\n")
    args.readings_out.write_text(json.dumps(sidecar, indent=2) + "\n")
    print(f"written: {args.out} ({len(written['tasks'])} tasks)")
    print(f"written: {args.readings_out}")
    # Which development rewordings are not tasks, and why, by id and never by text.
    for left in written.get("_skipped", []):
        print(f"skipped: rewording {left['rewording']} of {left['template']}: {left['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
