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

    python3 env/generate_apparel_v2_tasks.py
    python3 env/generate_apparel_v2_tasks.py --out /tmp/t.json --readings-out /tmp/r.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys

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


def keys(fixture: dict) -> dict:
    """Every v2 answer, from the variants, checked against `_instance` where they overlap."""
    listings = fixture["families"]
    inst = fixture["_instance"]
    size = inst["target_option"]
    largest = apparel.SIZES[-1]

    able = buyable(listings, size)
    if len(able) != inst["listings_target_buyable"]:
        raise SystemExit("the buyable count recomputed from the variants differs from _instance")
    if (able[0]["seller"], apparel.buyable_price_for(able[0], size)) != \
            (inst["winner"]["seller"], inst["winner"]["price"]):
        raise SystemExit("the cheapest buyable recomputed from the variants differs from _instance")

    yes = witnesses(listings, size, LIMIT_YES)
    if len(yes) != 1:
        raise SystemExit(f"{len(yes)} listings sell size {size} under ${LIMIT_YES}; one is needed")
    if witnesses(listings, size, LIMIT_NO):
        raise SystemExit(f"a listing sells size {size} under ${LIMIT_NO}; none may")

    top = able[:TOP_K]
    if len(able) <= TOP_K or apparel.buyable_price_for(able[TOP_K], size) == \
            apparel.buyable_price_for(top[-1], size):
        raise SystemExit(f"the {TOP_K} cheapest buyable are not a unique set")

    low, high = comparison_pair(listings, size)

    large = buyable(listings, largest)
    if (large[0]["seller"], apparel.buyable_price_for(large[0], largest)) != \
            (inst["largest_size_winner"]["seller"], inst["largest_size_winner"]["price"]):
        raise SystemExit(f"the cheapest buyable {largest} differs from _instance")

    return {
        "size": size, "largest": largest,
        "witness": yes[0], "looks_like_yes": looks_like_yes(listings, size, LIMIT_YES),
        "top": top, "top_next": able[TOP_K], "pair": (low, high),
        "large_winner": large[0], "large_traps": traps(listings, largest),
        "large_with": sum(1 for l in listings if apparel.price_for(l, largest) is not None),
        "large_buyable": len(large),
    }


# ---------------------------------------------------------------------------
# The file

def v2_tasks(fixture: dict, v1: dict) -> list[dict]:
    """The pilot's six tasks as they are, then the new ones."""
    k = keys(fixture)
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
    new = [
        {"id": f"apparel-exists-under-{LIMIT_YES}", "family": "apparel", "gated": True,
         "note": f"Existence under a price limit, answer yes. {witness['seller']} is the one "
                 f"listing that can sell size {size} under ${LIMIT_YES}, at "
                 f"{money(price(witness, size))}. {len(k['looks_like_yes'])} others advertise under "
                 f"${LIMIT_YES} on the results page and cannot: the size is absent, sold out, "
                 f"or dearer once chosen. A yes must name the witness; the question says "
                 f"\"available to buy\" because \"sells size {size}\" would be read as "
                 f"ambiguous and asked back. The box's witness opens cheapest first and may "
                 f"stop at the first that qualifies.",
         "query": f"{search} Is there any {brand} listing with size {size} available to buy "
                  f"for under ${LIMIT_YES}? Answer yes or no, and name the seller if yes.",
         "expect": {"kind": "boolean", "value": True, "any": [first(witness["seller"])],
                    "not_any": [first(l["seller"]) for l in k["looks_like_yes"]]},
         "box": box("plan", "exists_price")},
        {"id": f"apparel-exists-under-{LIMIT_NO}", "family": "apparel", "gated": True,
         "note": f"The same question with a limit no listing meets: no listing can sell size "
                 f"{size} under ${LIMIT_NO}, and the cheapest that can charges "
                 f"{money(price(witness, size))}. A no owes every listing advertised at or below "
                 f"${LIMIT_NO}, which the box's witness check holds it to.",
         "query": f"{search} Is there any {brand} listing with size {size} available to buy "
                  f"for under ${LIMIT_NO}? Answer yes or no, and name the seller if yes.",
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
                 f"{money(apparel.from_price(high))} and charges {money(price(high, size))}. The results "
                 f"page points the wrong way, and neither size-{size} price is on it. The "
                 f"ranked key requires {first(high['seller'])} with its price; "
                 f"{first(low['seller'])} is optional, but if named with a price it must be "
                 f"its size-{size} price, so quoting its advertised price is wrong.",
         "query": f"{search} Between {low['seller']} and {high['seller']}, which is cheaper "
                  f"for size {size}, and what is that price?",
         "expect": {"kind": "ranked",
                    "items": [{"any": [first(high["seller"])], "price": price(high, size)},
                              {"any": [first(low["seller"])], "price": price(low, size),
                               "optional": True}]},
         "box": box("plan", "named_lookup")},
        {"id": f"apparel-cheapest-{largest.lower()}", "family": "apparel", "gated": True,
         "note": f"The cheapest-target question for size {largest}, which the fixture's "
                 f"crossover rule makes a different seller from size {size}. {k['large_with']} "
                 f"of {inst['listings']} listings offer {largest} and {k['large_buyable']} can "
                 f"ship it. {large['seller']} wins at {money(price(large, largest))}; the cheapest "
                 f"advertised listing, {k['large_traps'][0]}, does not sell {largest} at all.",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=pathlib.Path, default=FIXTURE)
    parser.add_argument("--v1-tasks", type=pathlib.Path, default=V1_TASKS)
    parser.add_argument("--v1-readings", type=pathlib.Path, default=V1_READINGS)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--readings-out", type=pathlib.Path, default=DEFAULT_READINGS_OUT)
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text())
    v1 = json.loads(args.v1_tasks.read_text())
    written = spec(fixture, v1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(written, indent=2) + "\n")
    args.readings_out.write_text(
        json.dumps(readings(json.loads(args.v1_readings.read_text()), written["tasks"]), indent=2) + "\n")
    print(f"written: {args.out} ({len(written['tasks'])} tasks)")
    print(f"written: {args.readings_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
