#!/usr/bin/env python3
"""Write the task file for the box v2 development batch on Thornwood, with every answer
computed from the fixture.

Box v2 plans forms that v1 could not express: a witness under a price limit, the k
cheapest, a comparison of named listings (docs/content/box-v2-design.md, "How v2 is
measured", step 2). The pilot's six questions cover none of them, so this writes
`experiments/tasks/tasks_apparel_v2.json`: the six questions the pilot ran, copied byte for
byte from `experiments/tasks/tasks_apparel.json` so the batch runs the text the pilot ran,
then one question for each missing form, then questions the box must not plan: an
attribute the shop does not show, a price word with no figure, a market word with no
shape, and two with no shopping signal at all.

Every key is computed here from the fixture's variants, through the same functions
`generate_apparel.measure` uses, and never typed. The first clothing market's task file
was once written by hand and scored fifteen runs against a market that no longer existed
(see `generate_apparel.write_tasks`), so where a key overlaps what `_instance` records,
the two are compared and the script refuses to write if they differ.

`_instance` and `_environment` are the fixture's own, unchanged, so `suite.draw_id` is
the same as the pilot's file gives and a batch on this file is on the same market draw as
cells 1 to 5. Nothing here is read by the box: `tests/test_box.py` checks that the code
that runs before the agent reads no task file.

**A market with no pilot**, such as the claim market of 20 October 2026, gets the same
sixteen questions from its own fixture alone: `--fixture` names it, and with no `--v1-tasks`
the first six are written by `generate_apparel.py`'s own task writer for that market, so the
words are Thornwood's apart from the brand, and the readings sidecar is computed from the
fixture rather than copied. Nothing is copied from Thornwood's files, and a pilot file given
with another market's `_instance` is refused. The file names its fixture, so the analysis
tools read that market's ground truth (`verify_cells.fixture_for`).

    python3 env/generate_apparel_v2_tasks.py
    python3 env/generate_apparel_v2_tasks.py --out /tmp/t.json --readings-out /tmp/r.json
    python3 env/generate_apparel_v2_tasks.py --fixture env/fixtures/claim_apparel.json \
        --out experiments/tasks/tasks_claim_apparel.json \
        --readings-out experiments/tasks/readings_claim_apparel.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_apparel as apparel  # noqa: E402  (price_for, buyable_price_for, from_price)

FIXTURE = HERE / "fixtures" / "scaled_apparel.json"
TASKS = HERE.parent / "experiments" / "tasks"
V1_TASKS = TASKS / "tasks_apparel.json"
V1_READINGS = TASKS / "readings_apparel.json"
DEFAULT_OUT = TASKS / "tasks_apparel_v2.json"
DEFAULT_READINGS_OUT = TASKS / "readings_apparel_v2.json"

# The two price limits the existence questions state. Question parameters, like "size M",
# not answers: the script checks the fixture gives the intended answer under each (exactly
# one listing can sell the size under the first, none under the second) and refuses to
# write otherwise.
LIMIT_YES = 27
LIMIT_NO = 25
TOP_K = 3
# How the top-k question writes its k, so the box's `form.TOPK_COUNT` reads it as a count.
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}

# What the box is expected to do with each task, so a batch's box counts can be checked
# against the file: `outcome` is plan, ask, refuse, fallback or bypass, and `kind` is the
# plan's kind, for an ask the kind planned once a --reading answers it, None when nothing
# is planned. The six copied questions keep the kinds `tests/test_box.Classifier` pins.
V1_BOX = {
    "apparel-headline": ("plan", "results_page"),
    "apparel-target-price": ("plan", "availability_bound"),
    "apparel-cheapest-target": ("plan", "availability_bound"),
    "apparel-all-stocked": ("ask", "refutation"),
    "apparel-count-stocked": ("ask", "survey"),
    "apparel-count-buyable": ("plan", "survey"),
}


def first(name: str) -> str:
    """The token the scorer looks for: the seller's first word, distinct across the
    generator's name list, as `generate_apparel.write_tasks` uses it."""
    return name.split()[0]


def box(outcome: str, kind: str | None = None) -> dict:
    return {"outcome": outcome, "kind": kind}


# ---------------------------------------------------------------------------
# Keys, from the variants

def buyable(listings: list[dict], size: str) -> list[dict]:
    """Listings that can sell the size now, cheapest for that size first."""
    able = [l for l in listings if apparel.buyable_price_for(l, size) is not None]
    return sorted(able, key=lambda l: apparel.buyable_price_for(l, size))


def witnesses(listings: list[dict], size: str, limit: float) -> list[dict]:
    """Listings that can sell the size under the limit. "under" is strict here and "at or
    below" in the box's reading of the question, so no buyable price may sit exactly on
    the limit, or the two would disagree on the answer."""
    if any(apparel.buyable_price_for(l, size) == limit for l in buyable(listings, size)):
        raise SystemExit(f"a listing sells size {size} at exactly ${limit}: choose another limit")
    return [l for l in buyable(listings, size) if apparel.buyable_price_for(l, size) < limit]


def price_limits(fixture: dict) -> tuple[int, int]:
    """The two limits for a market with no pilot, by a rule written on 20 October 2026
    before the claim market existed: under the first, the whole-dollar part of the midpoint
    between the two cheapest prices any listing can sell the target size for, exactly one
    listing can sell it; under the second, the whole-dollar part of the cheapest, none can.
    Thornwood's 27 and 25 were chosen by hand for its 25.77 and 28.96, and the rule gives
    them back (tests/test_claim_market.py), so it asks the same thing of a new market.
    `keys` still checks the answer each gives, and refuses when the rule cannot give it."""
    size = fixture["_instance"]["target_option"]
    # In whole cents, so a midpoint that is a whole dollar is not floored a dollar short.
    cheapest, second = (round(apparel.buyable_price_for(l, size) * 100)
                        for l in buyable(fixture["families"], size)[:2])
    return (cheapest + second) // 200, cheapest // 100


def looks_like_yes(listings: list[dict], size: str, limit: float) -> list[dict]:
    """Listings the results page makes look like a yes and are not: advertised under the
    limit, not a witness. The sold-out trap, the absent-size trap and the card-only
    reader's answer are all in here."""
    able = witnesses(listings, size, limit)
    return sorted((l for l in listings if apparel.from_price(l) < limit and l not in able),
                  key=apparel.from_price)


def traps(listings: list[dict], size: str) -> list[str]:
    """The two sellers a price-only reader names for the cheapest of a size, as
    `generate_apparel.write_tasks` lists them: the cheapest advertised listing without the
    size, and the cheapest listed price for the size that cannot ship it, when there is one."""
    absent = [l for l in listings if apparel.price_for(l, size) is None]
    sold_out = [l for l in listings if apparel.price_for(l, size) is not None
                and apparel.buyable_price_for(l, size) is None]
    named = []
    if absent:
        named.append(first(min(absent, key=apparel.from_price)["seller"]))
    if sold_out:
        named.append(first(min(sold_out, key=lambda l: apparel.price_for(l, size))["seller"]))
    return named


def large_trap_clause(listings: list[dict], winner: dict, size: str) -> str:
    """The end of the largest-size question's note: what the cheapest advertised listing
    does with the size. On Thornwood it does not sell it, which is what the note said of
    every market until 20 October 2026; on the claim market the cheapest card is the winner
    itself, and the note said a listing advertised third did not sell the size, so each case
    now says what is true, and the traps the key excludes are named as what they are."""
    money = lambda value: f"${value:.2f}"  # noqa: E731
    cheapest = min(listings, key=apparel.from_price)
    if cheapest is winner:
        absent = [l for l in listings if apparel.price_for(l, size) is None]
        sold_out = [l for l in listings if apparel.price_for(l, size) is not None
                    and apparel.buyable_price_for(l, size) is None]
        parts = [f"the cheapest advertised listing is the winner itself, so a card-only reader "
                 f"is right here"]
        if sold_out:
            trap = min(sold_out, key=lambda l: apparel.price_for(l, size))
            parts.append(f"{trap['seller']} lists {size} at {money(apparel.price_for(trap, size))} "
                         f"and cannot ship it")
        if absent:
            trap = min(absent, key=apparel.from_price)
            parts.append(f"{trap['seller']}, advertised at {money(apparel.from_price(trap))}, does "
                         f"not sell {size} at all")
        return "; ".join(parts) + "."
    if apparel.price_for(cheapest, size) is None:
        return f"the cheapest advertised listing, {first(cheapest['seller'])}, does not sell {size} at all."
    return (f"the cheapest advertised listing, {first(cheapest['seller'])}, sells {size} at "
            f"{money(apparel.price_for(cheapest, size))}"
            + ("" if apparel.buyable_price_for(cheapest, size) is not None else " and cannot ship it")
            + ".")


def comparison_pair(listings: list[dict], size: str) -> tuple[dict, dict]:
    """Two listings that can both sell the size, where the one advertised cheaper is the
    dearer for the size, so the results page points the wrong way. Among those, a pair
    where neither listing's advertised price is its price for the size is preferred, so
    the answer is behind the size menu on both and cannot be read from a card; then the
    largest advertised gap. Returned as (advertised cheaper, advertised dearer). Any two
    buyable listings when no pair crosses over."""
    pool = buyable(listings, size)
    crossed = []
    for a, b in itertools.combinations(pool, 2):
        low, high = sorted((a, b), key=apparel.from_price)
        if apparel.buyable_price_for(low, size) <= apparel.buyable_price_for(high, size):
            continue
        hidden = all(apparel.from_price(l) != apparel.buyable_price_for(l, size) for l in (low, high))
        crossed.append((hidden, apparel.from_price(high) - apparel.from_price(low), low, high))
    if not crossed:
        return pool[0], pool[1]
    _, _, low, high = max(crossed, key=lambda entry: entry[:2])
    return low, high


def keys(fixture: dict, limits: tuple[int, int] | None = None) -> dict:
    """Every v2 answer, from the variants, checked against `_instance` where they overlap.
    `limits` are the existence questions' two price limits, Thornwood's by default."""
    listings = fixture["families"]
    inst = fixture["_instance"]
    size = inst["target_option"]
    largest = apparel.SIZES[-1]
    limit_yes, limit_no = limits or (LIMIT_YES, LIMIT_NO)

    able = buyable(listings, size)
    if len(able) != inst["listings_target_buyable"]:
        raise SystemExit("the buyable count recomputed from the variants differs from _instance")
    if (able[0]["seller"], apparel.buyable_price_for(able[0], size)) != \
            (inst["winner"]["seller"], inst["winner"]["price"]):
        raise SystemExit("the cheapest buyable recomputed from the variants differs from _instance")

    yes = witnesses(listings, size, limit_yes)
    if len(yes) != 1:
        raise SystemExit(f"{len(yes)} listings sell size {size} under ${limit_yes}; one is needed")
    if witnesses(listings, size, limit_no):
        raise SystemExit(f"a listing sells size {size} under ${limit_no}; none may")

    top = able[:TOP_K]
    if len(able) <= TOP_K or apparel.buyable_price_for(able[TOP_K], size) == \
            apparel.buyable_price_for(top[-1], size):
        raise SystemExit(f"the {TOP_K} cheapest buyable are not a unique set")

    low, high = comparison_pair(listings, size)

    # Like with like. `_instance.largest_size_winner` is the cheapest price listed for the
    # largest size, sold out or not (`generate_apparel.measure`), so it is compared with the
    # cheapest listed recomputed here, and the key, the cheapest that can be bought, is
    # computed beside it. Until 20 October 2026 the key itself was compared, which on a
    # market whose cheapest listed XL is sold out refuses a correct file; on Thornwood both
    # are Ivybridge Collective at $18.08, so its file is unchanged.
    listed = min((l for l in listings if apparel.price_for(l, largest) is not None),
                 key=lambda l: apparel.price_for(l, largest))
    if (listed["seller"], apparel.price_for(listed, largest)) != \
            (inst["largest_size_winner"]["seller"], inst["largest_size_winner"]["price"]):
        raise SystemExit(f"the cheapest listed {largest} differs from _instance")
    large = buyable(listings, largest)

    return {
        "size": size, "largest": largest,
        "witness": yes[0], "looks_like_yes": looks_like_yes(listings, size, limit_yes),
        "top": top, "top_next": able[TOP_K], "pair": (low, high),
        "large_winner": large[0], "large_traps": traps(listings, largest),
        "large_with": sum(1 for l in listings if apparel.price_for(l, largest) is not None),
        "large_buyable": len(large),
    }


# ---------------------------------------------------------------------------
# The file

# What the box does since 20 October 2026 where it differs from what it did when Thornwood's
# file was written on 14 October (box v6, form v4): a superlative on an attribute the shop
# does not show is refused rather than planned by the fallback (box v7, form v5). Thornwood's
# file is the frozen record of the batch it ran, so its field stays; a file written for a
# market with no pilot says what the box does now, with a note that says so.
SINCE_20_OCT = {
    "apparel-softest": {
        "note": "Refused. A superlative on an attribute the shop does not show (softness): "
                "since 20 October 2026 the box refuses it before the agent runs, whatever "
                "the word, and says what the shop does show. No agent runs; the slot is "
                "recorded as refused. No key.",
        "box": {"outcome": "refuse", "kind": None},
    },
}


def v2_tasks(fixture: dict, v1: dict, limits: tuple[int, int] | None = None,
             now: bool = False) -> list[dict]:
    """The pilot's six tasks as they are, then the new ones. `limits` are the existence
    questions' price limits, Thornwood's by default, and `now` writes what the box does
    today where it differs from the pilot's day (`SINCE_20_OCT`)."""
    k = keys(fixture, limits)
    limit_yes, limit_no = limits or (LIMIT_YES, LIMIT_NO)
    inst = fixture["_instance"]
    brand = fixture["_generated"]["brand"]
    size, largest = k["size"], k["largest"]
    search = f"Go to {{base}}/catalogsearch/result/?q={brand} ."
    price = lambda listing, option: apparel.buyable_price_for(listing, option)  # noqa: E731
    money = lambda value: f"${value:.2f}"  # noqa: E731  (the notes print every price this way)

    copied = []
    for task in v1["tasks"]:
        outcome, kind = V1_BOX[task["id"]]
        copied.append({**task, "box": box(outcome, kind)})

    witness, low, high = k["witness"], k["pair"][0], k["pair"][1]
    top = k["top"]
    large = k["large_winner"]
    # The pair's answer is whichever of the two is cheaper for the size. `comparison_pair`
    # prefers a pair the page points the wrong way on, where that is the one advertised
    # dearer, `high`; with no such pair it falls back to the two cheapest, where it is
    # `low`, and until 20 October 2026 the key still named `high`, a wrong key. Thornwood's
    # pair crosses over, so its file is unchanged; the claim market's does not.
    crossed = price(low, size) > price(high, size)
    cheaper, dearer = (high, low) if crossed else (low, high)
    new = [
        {"id": f"apparel-exists-under-{limit_yes}", "family": "apparel", "gated": True,
         "note": f"Existence under a price limit, answer yes. {witness['seller']} is the one "
                 f"listing that can sell size {size} under ${limit_yes}, at "
                 f"{money(price(witness, size))}. {len(k['looks_like_yes'])} others advertise under "
                 f"${limit_yes} on the results page and cannot: the size is absent, sold out, "
                 f"or dearer once chosen. A yes must name the witness; the question says "
                 f"\"available to buy\" because \"sells size {size}\" would be read as "
                 f"ambiguous and asked back. The box's witness opens cheapest first and may "
                 f"stop at the first that qualifies.",
         "query": f"{search} Is there any {brand} listing with size {size} available to buy "
                  f"for under ${limit_yes}? Answer yes or no, and name the seller if yes.",
         "expect": {"kind": "boolean", "value": True, "any": [first(witness["seller"])],
                    "not_any": [first(l["seller"]) for l in k["looks_like_yes"]]},
         "box": box("plan", "exists_price")},
        {"id": f"apparel-exists-under-{limit_no}", "family": "apparel", "gated": True,
         "note": f"The same question with a limit no listing meets: no listing can sell size "
                 f"{size} under ${limit_no}, and the cheapest that can charges "
                 f"{money(price(witness, size))}. A no owes every listing advertised at or below "
                 f"${limit_no}, which the box's witness check holds it to.",
         "query": f"{search} Is there any {brand} listing with size {size} available to buy "
                  f"for under ${limit_no}? Answer yes or no, and name the seller if yes.",
         "expect": {"kind": "boolean", "value": False},
         "box": box("plan", "exists_price")},
        {"id": f"apparel-top-{TOP_K}", "family": "apparel", "gated": True,
         "note": f"The {TOP_K} cheapest that can sell size {size}, in order: "
                 + ", ".join(f"{l['seller']} at {money(price(l, size))}" for l in top)
                 + f". The next can sell it at {money(price(k['top_next'], size))}, so the set is "
                 f"unique. Scored by the ranked kind: the sellers in that order, each with "
                 f"its price.",
         "query": f"{search} Which {NUMBER_WORDS[TOP_K]} sellers are cheapest for size {size} "
                  f"among listings that can actually supply it, and at what prices?",
         "expect": {"kind": "ranked",
                    "items": [{"any": [first(l["seller"])], "price": price(l, size)} for l in top]},
         "box": box("plan", "topk_price")},
        {"id": "apparel-named-pair", "family": "apparel", "gated": True,
         "note": f"A comparison of two named listings that both sell size {size}. "
                 f"{low['seller']} advertises {money(apparel.from_price(low))} and charges "
                 f"{money(price(low, size))} for {size}; {high['seller']} advertises "
                 f"{money(apparel.from_price(high))} and charges {money(price(high, size))}. "
                 + (f"The results page points the wrong way, and neither size-{size} price is on it. "
                    if crossed else
                    f"No two listings that can sell size {size} cross over on this market, so "
                    f"the pair is the two cheapest that can sell it and the results page points "
                    f"the right way; "
                    + ("neither" if all(apparel.from_price(l) != price(l, size) for l in (low, high))
                       else "not every")
                    + f" size-{size} price is on it. ")
                 + f"The ranked key requires {first(cheaper['seller'])} with its price; "
                 f"{first(dearer['seller'])} is optional, but if named with a price it must be "
                 f"its size-{size} price, so quoting its advertised price is wrong.",
         "query": f"{search} Between {low['seller']} and {high['seller']}, which is cheaper "
                  f"for size {size}, and what is that price?",
         "expect": {"kind": "ranked",
                    "items": [{"any": [first(cheaper["seller"])], "price": price(cheaper, size)},
                              {"any": [first(dearer["seller"])], "price": price(dearer, size),
                               "optional": True}]},
         "box": box("plan", "named_lookup")},
        {"id": f"apparel-cheapest-{largest.lower()}", "family": "apparel", "gated": True,
         "note": f"The cheapest-target question for size {largest}, which the fixture's "
                 f"crossover rule makes a different seller from size {size}. {k['large_with']} "
                 f"of {inst['listings']} listings offer {largest} and {k['large_buyable']} can "
                 f"ship it. {large['seller']} wins at {money(price(large, largest))}; "
                 + large_trap_clause(fixture["families"], large, largest),
         "query": f"{search} Across the {brand} listings, which seller is cheapest for size "
                  f"{largest}, and what is that price? Only count a listing that can actually "
                  f"supply that size.",
         "expect": {"kind": "contains", "any": [first(large["seller"])],
                    "not_any": k["large_traps"], "price": price(large, largest)},
         "box": box("plan", "availability_bound")},
        {"id": "apparel-delivery", "family": "apparel", "gated": False,
         "note": "Push-back. Delivery time is not shown anywhere on this shop, so the box "
                 "must refuse and say what the shop does show. No agent runs; the slot is "
                 "recorded as refused. No key.",
         "query": f"{search} Which {brand} seller delivers fastest for size {size}?",
         "expect": {"kind": "none"},
         "box": box("refuse")},
        {"id": "apparel-cheap-no-figure", "family": "apparel", "gated": False,
         "note": "Ask, numerical. \"cheap\" with no figure: the box must ask for a limit. "
                 "The scripted user has no limit to give (--reading answers only the menu "
                 "or buyable question), so under every reading the slot is recorded as "
                 "asked and no agent runs. No key.",
         "query": f"{search} Is there a cheap {brand} tee in size {size}?",
         "expect": {"kind": "none"},
         "box": box("ask")},
        {"id": "apparel-softest", "family": "apparel", "gated": False,
         "note": "Fallback. A market word (\"sells\") and no shape the rules know: v1's "
                 "survey plan runs and the record says it was a fallback. The shop shows no "
                 "softness, so there is no key; the answer is read by hand.",
         "query": f"{search} Who sells the softest {brand} tee?",
         "expect": {"kind": "none"},
         "box": box("fallback", "survey")},
        {"id": "bypass-poem", "family": "apparel", "gated": False,
         "note": "Bypass. No shopping signal, so the agent gets the text unchanged, with no "
                 "page and no plan, and the batch counts it as bypassed. Intended: the run "
                 "shows what the baseline agent does with an open question while its browser "
                 "is confined to the shop. No key.",
         "query": "Write a four-line poem about shoes.",
         "expect": {"kind": "none"},
         "box": box("bypass")},
        {"id": "bypass-capital", "family": "apparel", "gated": False,
         "note": "Bypass, a factual question. As above: intended to run unchanged, confined "
                 "to the shop, and counted as bypassed. No key.",
         "query": "What is the capital of Portugal?",
         "expect": {"kind": "none"},
         "box": box("bypass")},
    ]
    if now:
        for task in new:
            task.update(SINCE_20_OCT.get(task["id"], {}))
    return copied + new


def spec(fixture: dict, v1: dict) -> dict:
    inst = fixture["_instance"]
    return {
        "_about": [
            "Generated by env/generate_apparel_v2_tasks.py from env/fixtures/scaled_apparel.json",
            "and experiments/tasks/tasks_apparel.json. Do not hand edit.",
            f"Seed {fixture['_generated']['seed']}, accepted on attempt "
            f"{fixture['_generated']['attempt']}: the same market as tasks_apparel.json.",
            "The box v2 development batch on Thornwood: the six questions the pilot ran,",
            "copied unchanged, then one question for each form v1 lacked, then questions",
            "the box must not plan. Every key is computed from the fixture's variants.",
            "_instance and _environment are the fixture's own, unchanged, so the draw id is",
            "the pilot's and a batch here is on the market draw of cells 1 to 5.",
            "Each task's \"box\" field says what the box is expected to do with it: outcome",
            "plan, ask, refuse, fallback or bypass, and the plan's kind (for an ask, the kind",
            "planned once a --reading answers it; null when nothing is planned).",
            "tests/test_apparel_v2.py checks the box does that, and that a batch's box",
            "counts follow from it.",
        ],
        "_environment": v1["_environment"],
        "base_url": v1["base_url"],
        "brand": v1["brand"],
        "_instance": inst,
        "tasks": v2_tasks(fixture, v1),
    }


def readings(v1_readings: dict, tasks: list[dict]) -> dict:
    """The scripted user's second reading, copied for the questions carried over. The new
    questions are clear, or are an ask no reading answers, so none has one."""
    carried = {task["id"] for task in tasks}
    return {
        "_about": [
            "Written by env/generate_apparel_v2_tasks.py from experiments/tasks/readings_apparel.json:",
            "the scripted user's second reading of the two ambiguous clothing questions, copied",
            "for the questions tasks_apparel_v2.json carries over unchanged. Do not hand edit.",
            "The new questions in that file are clear, or are asks no reading answers (a price",
            "word with no figure), so none has a second reading.",
        ],
        "readings": {reading: {task_id: expect for task_id, expect in keys_.items()
                               if task_id in carried}
                     for reading, keys_ in v1_readings["readings"].items()},
    }


# ---------------------------------------------------------------------------
# A market with no pilot: everything from its own fixture (20 October 2026)

def wrap(text: str) -> list[str]:
    return textwrap.wrap(text, 88)


def own_spec(fixture: dict, fixture_name: str) -> dict:
    """The sixteen questions for a market with no pilot batch, from its fixture alone: its
    own six, written by `generate_apparel.task_spec`, then the ten, with the existence
    limits by `price_limits` and the box fields of today's box. `fixture` names the fixture
    under env/fixtures, so the analysis tools read this market's ground truth."""
    six = apparel.task_spec(fixture)
    generated, inst = fixture["_generated"], fixture["_instance"]
    limit_yes, limit_no = price_limits(fixture)
    about = [
        f"Generated by env/generate_apparel_v2_tasks.py from env/fixtures/{fixture_name} alone. "
        f"Do not hand edit.",
        *wrap(f"Seed {generated['seed']}, accepted on attempt {generated['attempt']}, brand "
              f"{generated['brand']}: a market with no pilot batch, so nothing here is copied from "
              f"another market's file."),
        *wrap("The six questions the Thornwood cells asked, written for this market by "
              "env/generate_apparel.py's own task writer, so the words are the same apart from "
              "the brand, then the ten box v2 questions, with every key computed from the "
              "fixture's variants and checked against _instance where the two overlap."),
        *wrap(f"The existence questions' limits, ${limit_yes} and ${limit_no}, follow "
              f"price_limits, a rule written on 20 October 2026 before this market existed, "
              f"which gives Thornwood's 27 and 25 on Thornwood. The named pair follows "
              f"comparison_pair, the rule Thornwood's pair was chosen by."),
        *wrap("Each task's \"box\" field says what the box does with it when this file was "
              "written, on 20 October 2026: outcome plan, ask, refuse, fallback or bypass, and "
              "the plan's kind (for an ask, the kind planned once a --reading answers it; null "
              "when nothing is planned). tests/test_claim_market.py checks the box does that."),
        *wrap("\"fixture\" names the market's fixture, so verify_cells, compare_cells, "
              "cell_facts and replay_box read its ground truth, and count a listing as opened "
              "only when it is one of its own."),
    ]
    return {
        "_about": about,
        "_environment": six["_environment"],
        "base_url": six["base_url"],
        "brand": six["brand"],
        "fixture": fixture_name,
        "_instance": inst,
        "tasks": v2_tasks(fixture, six, limits=(limit_yes, limit_no), now=True),
    }


def buyable_reading(fixture: dict) -> dict:
    """The scripted user's buyable reading of the two "offer" questions, from the variants:
    "offer" read as "can sell it now". The count is the listings that can sell the target
    size, and "every listing" is yes only if all of them can. The rule readings_apparel.json
    was written by on 8 October 2026, and on Thornwood's fixture it gives that file's keys."""
    inst = fixture["_instance"]
    able = buyable(fixture["families"], inst["target_option"])
    if len(able) != inst["listings_target_buyable"]:
        raise SystemExit("the buyable count recomputed from the variants differs from _instance")
    return {"buyable": {
        "apparel-count-stocked": {"kind": "count", "value": len(able)},
        "apparel-all-stocked": {"kind": "boolean", "value": len(able) == len(fixture["families"])},
    }}


def own_readings(fixture: dict, fixture_name: str, tasks_name: str) -> dict:
    size = fixture["_instance"]["target_option"]
    return {
        "_about": [
            *wrap(f"Computed by env/generate_apparel_v2_tasks.py from env/fixtures/{fixture_name}: "
                  f"the scripted user's second reading of the two ambiguous clothing questions in "
                  f"{tasks_name}, used by suite.py --reading buyable and by verify_cells.py when a "
                  f"batch records that reading. Do not hand edit."),
            *wrap(f"The task's own expect is the menu reading: a sold out size counts as offered. "
                  f"Here \"offer\" is read as \"can sell it now\": apparel-count-stocked counts the "
                  f"listings that can sell size {size} now, which is "
                  f"_instance.listings_target_buyable, and apparel-all-stocked is yes only if every "
                  f"listing can. The rule readings_apparel.json was written by on 8 October 2026, "
                  f"computed here rather than copied (buyable_reading). The other questions are "
                  f"clear, or are asks no reading answers, so none has a second reading."),
        ],
        "readings": buyable_reading(fixture),
    }


def own_market_refused(fixture: pathlib.Path, out: pathlib.Path,
                       readings_out: pathlib.Path) -> str | None:
    """Why a market with no pilot may not be written where asked, or None: its fixture is
    not under env/fixtures, where the analysis tools look for it, or an output is one of
    Thornwood's two v2 files. Kept apart from `main` so a test can ask it without writing."""
    if fixture.resolve().parent != FIXTURE.parent.resolve():
        return f"the fixture must be under {FIXTURE.parent}, where the analysis tools look for it"
    if {out.resolve(), readings_out.resolve()} & {DEFAULT_OUT.resolve(),
                                                  DEFAULT_READINGS_OUT.resolve()}:
        return ("refusing to write another market over Thornwood's v2 files: name --out and "
                "--readings-out")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=pathlib.Path, default=FIXTURE)
    parser.add_argument("--v1-tasks", type=pathlib.Path,
                        help="the pilot's task file whose six questions are copied, by default "
                             "tasks_apparel.json for Thornwood's fixture. For any other fixture "
                             "there is no pilot unless one is named: the six are written from the "
                             "fixture by generate_apparel.py's task writer")
    parser.add_argument("--v1-readings", type=pathlib.Path,
                        help="the pilot's readings, by default readings_apparel.json with the "
                             "pilot. Without a pilot they are computed from the fixture")
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--readings-out", type=pathlib.Path, default=DEFAULT_READINGS_OUT)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text())
    thornwood = args.fixture.resolve() == FIXTURE.resolve()
    pilot = args.v1_tasks or (V1_TASKS if thornwood else None)
    if pilot is None:
        # Another market's file, its fixture named in it, never over Thornwood's two.
        refused = own_market_refused(args.fixture, args.out, args.readings_out)
        if refused:
            raise SystemExit(refused)
        written = own_spec(fixture, args.fixture.name)
        sidecar = own_readings(fixture, args.fixture.name, args.out.name)
    else:
        v1 = json.loads(pilot.read_text())
        # The six copied must be this market's: the same `_instance`, or the file is refused.
        if v1["_instance"] != fixture["_instance"]:
            raise SystemExit(f"{pilot.name} is not {args.fixture.name}'s market: its _instance "
                             f"differs, so its six questions would be another market's")
        written = spec(fixture, v1)
        sidecar = readings(json.loads((args.v1_readings or V1_READINGS).read_text()),
                           written["tasks"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(written, indent=2) + "\n")
    args.readings_out.write_text(json.dumps(sidecar, indent=2) + "\n")
    print(f"written: {args.out} ({len(written['tasks'])} tasks)")
    print(f"written: {args.readings_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
