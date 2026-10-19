#!/usr/bin/env python3
"""Score a browser run's free-text answer against a task's ground truth.

Answers are prose, so scoring is deliberately conservative. A run counts as
correct only when the expected value is present and the specific wrong answer the
task is designed to provoke is absent. Anything else is `wrong`, except a run
that declines to answer, which is `abstained` and is a materially different
outcome: a policy that says "I could not determine this" has not misled anyone.
"""

from __future__ import annotations

import json
import pathlib
import re

# Bumped when a rule changes a verdict or a kind of key is added. Recorded in every suite
# payload as `scorer_version` since 14 October 2026; a batch without the field was scored
# by version 1. Runs scored under different versions are compared only after a rescore.
#
#   1  The rules as they stood on 14 October 2026: price, contains, boolean, count,
#      all_prices
#   2  14 October 2026, for the box v2 batch. A yes-or-no key may name the witness a yes
#      must name (`any`, `not_any` on a boolean). A "ranked" kind holds an answer to k
#      sellers in order, each with its price. A "none" kind marks a question with no key,
#      one the box is expected to ask on, refuse or bypass; its verdict is "unscored". No
#      stored key uses any of the three, so no stored verdict changes
#   3  20 October 2026. A "none" key is unscored whether or not the run finished. Until
#      now a keyless run that ended without ok was scored failed, and verify_cells counted
#      it in the control ratio (verifier finding on 20261014T220116: apparel-softest-1 ran
#      out of answers and showed as "control correct 0 of 1"). Replayed over every stored
#      run, that one verdict changes, failed to unscored; the batch's suite.json keeps the
#      stored verdict until it is rescored
VERSION = 3

# Phrases that mean the agent declined rather than answered. Kept narrow on
# purpose: "not" alone is far too broad, "could not determine" is not.
ABSTENTION_MARKERS = (
    "unable to", "could not determine", "couldn't determine", "cannot determine",
    "can't determine", "not able to", "unable", "no answer", "insufficient",
    "need more information", "could not find", "couldn't find", "cannot find",
    "not found", "unclear", "i don't know", "i do not know",
)

NEGATIVE_MARKERS = ("no", "not available", "out of stock", "unavailable", "sold out",
                    "not every", "not all")
POSITIVE_MARKERS = ("yes", "in stock", "available")

# An answer that opens with yes or no has said which it means, and the rest is explanation.
# Reading markers anywhere in the text instead, as substrings, scored "Yes. All 10 listings
# stock the pack. I enumerated all listings (no pagination)..." as a No, because "no" sits
# inside "(no pagination)". The same test also matched "not", "cannot" and "know".
LEADING_ANSWER = re.compile(r"^[\W_]*(yes|no)\b")

# A number that says how much was examined rather than how many qualified: "all 15",
# "of the 15", "out of 15", "across 15". Used by the count rule to skip past it.
COVERAGE_NUMBER = re.compile(
    r"\b(?:all|of|out of|across|among|checking|checked|opened|examined)\s+(?:the\s+)?"
    r"(\d{1,3})\b", re.IGNORECASE)


def has_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(m)}\b", text) for m in markers)


def prices_in(text: str) -> list[float]:
    """Every money-looking number in the answer, in order of appearance."""
    return [float(m) for m in re.findall(r"(?<![\d.])(\d{1,4}\.\d{2})(?![\d])", text or "")]


def abstained(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in ABSTENTION_MARKERS)


def readings_for(tasks_path: pathlib.Path) -> dict:
    """The scripted user's other readings of a task file's ambiguous questions.

    Read from the sidecar beside the task file, `readings_apparel.json` beside
    `tasks_apparel.json`, keyed by reading and then task id. Empty when there is none. The
    "menu" reading is the task's own key, so it never appears here.
    """
    sidecar = tasks_path.with_name(tasks_path.name.replace("tasks_", "readings_", 1))
    if sidecar == tasks_path or not sidecar.exists():
        return {}
    return json.loads(sidecar.read_text()).get("readings", {})


def under_reading(task: dict, reading: str | None, readings: dict) -> dict:
    """The task with the answer key for this reading, or its own key when the reading has
    none for it, so a question that was never ambiguous is scored as before. `reading` is
    the one the run answered under: the user's reply to the box's question, or the reading
    the box took itself when the other had no answer on the shop (since 20 Oct 2026 the
    row carries it as `reading` with `reading_by`)."""
    expect = (readings.get(reading) or {}).get(task["id"]) if reading else None
    return {**task, "expect": expect} if expect else task


def score(task: dict, answer: str, ok: bool) -> dict:
    """Return verdict plus the evidence behind it, so results stay auditable."""
    answer = answer or ""
    expect = task["expect"]
    kind = expect["kind"]
    found = prices_in(answer)
    low = answer.lower()

    if kind == "none":
        # No key. The box is expected to ask on, refuse or bypass this question; when a
        # bypassed one runs, its answer is read by hand rather than judged here. Before the
        # failed branch since 20 October 2026: a keyless run that did not finish has no
        # key to fail against either, and "failed" was counted as a wrong control answer.
        return {"verdict": "unscored", "why": "no answer key for this question", "prices": found}
    if not ok or not answer.strip():
        return {"verdict": "failed", "why": "run did not produce an answer", "prices": found}
    if abstained(answer):
        return {"verdict": "abstained", "why": "answer declined to commit", "prices": found}

    if kind == "price":
        target, trap = expect["value"], expect.get("trap")
        if target in found:
            if trap is not None and trap in found:
                # An answer naming both is muddled only if it does not resolve them.
                # Magento states variant prices as a surcharge, so a correct answer often
                # shows its working: "$22.50 (base $10.90 + charge $11.60)". That names
                # the trap value and is right, and an earlier version of this rule scored
                # it ambiguous, penalising exactly the composition the task requires.
                if any(abs(a + b - target) < 0.005
                       for a in found for b in found if a is not b):
                    return {"verdict": "correct",
                            "why": f"found {target}, with working that resolves to it",
                            "prices": found}
                return {"verdict": "ambiguous",
                        "why": f"names both {target} and the trap price {trap}",
                        "prices": found}
            return {"verdict": "correct", "why": f"found {target}", "prices": found}
        if trap is not None and trap in found:
            return {"verdict": "wrong", "why": f"reported trap price {trap}", "prices": found}
        return {"verdict": "wrong", "why": f"expected {target}, saw {found or 'no price'}",
                "prices": found}

    if kind == "contains":
        # Naming the expected option wins even when the answer also mentions the
        # alternatives. A good comparison answer says "500g is best, 250g costs
        # more", and an earlier version of this scorer marked exactly that wrong
        # because the excluded token appeared anywhere in the text. `not_any` now
        # only decides cases where the expected option was never named at all.
        hit = any(token.lower() in low for token in expect["any"])
        bad = any(token.lower() in low for token in expect.get("not_any", []))
        price = expect.get("price")
        if hit:
            if price is not None and price not in found:
                return {"verdict": "ambiguous", "why": f"right option, missing price {price}",
                        "prices": found}
            return {"verdict": "correct", "why": "named the expected option", "prices": found}
        if bad:
            return {"verdict": "wrong", "why": "named an excluded option instead",
                    "prices": found}
        return {"verdict": "wrong", "why": "expected option not named", "prices": found}

    if kind == "boolean":
        wants_yes = expect["value"]
        lead = LEADING_ANSWER.match(low)
        if lead:
            says_no = lead.group(1) == "no"
            says_yes = not says_no
        else:
            # Check the negative first: "not available" contains "available".
            says_no = has_marker(low, NEGATIVE_MARKERS)
            says_yes = has_marker(low, POSITIVE_MARKERS) and not says_no
        if says_no == (not wants_yes) and (says_no or says_yes):
            if says_yes and expect.get("any"):
                # "Name the seller if yes": a yes owes its witness. A yes that names an
                # excluded seller instead, the sold-out or absent-size trap, is wrong; one
                # that names nobody has not finished answering.
                hit = any(token.lower() in low for token in expect["any"])
                bad = any(token.lower() in low for token in expect.get("not_any", []))
                if not hit and bad:
                    return {"verdict": "wrong", "why": "answered yes naming an excluded seller",
                            "prices": found}
                if not hit:
                    return {"verdict": "ambiguous", "why": "answered yes but named no seller",
                            "prices": found}
            return {"verdict": "correct", "why": f"answered {'no' if says_no else 'yes'}",
                    "prices": found}
        if not says_no and not says_yes:
            return {"verdict": "ambiguous", "why": "no clear yes or no", "prices": found}
        return {"verdict": "wrong", "why": f"answered {'no' if says_no else 'yes'}",
                "prices": found}

    if kind == "count":
        # "How many listings stock it" is answered with a number rather than a name or a
        # price. The rule was once "the number the answer leads with", on the grounds that
        # "9 of the 15 listings" states its count first. The first answer to break that
        # read "After checking all 15 listings, I found that 5 products have size M", which
        # is right and was scored as a count of 15. So a number stating how many were looked
        # at, "all 15", "of the 15", "out of 15", is not the count, and neither are the
        # digits inside a price. If that leaves nothing, the first number is used after all,
        # since "All 15 listings offer it" is a count of 15.
        numbers = list(re.finditer(r"(?<![\d.$])(\d{1,3})(?![\d.])", answer or ""))
        if not numbers:
            return {"verdict": "ambiguous", "why": "no number given", "prices": found}
        coverage = {m.start(1) for m in COVERAGE_NUMBER.finditer(answer or "")}
        kept = [m for m in numbers if m.start(1) not in coverage]
        stated = int((kept or numbers)[0].group(1))
        if stated == expect["value"]:
            return {"verdict": "correct", "why": f"counted {stated}", "prices": found}
        return {"verdict": "wrong",
                "why": f"counted {stated}, expected {expect['value']}", "prices": found}

    if kind == "all_prices":
        wanted = set(expect["values"])
        missing = sorted(wanted - set(found))
        if not missing:
            return {"verdict": "correct", "why": "listed every price", "prices": found}
        return {"verdict": "wrong", "why": f"missing {missing}", "prices": found}

    if kind == "ranked":
        return ranked(expect, answer, found)

    raise ValueError(f"unknown expect kind: {kind}")


def mentions_of(low: str, items: list[dict]) -> list[tuple[int, int]]:
    """Where the ranked sellers are named: (position, item index), every occurrence."""
    found = []
    for index, item in enumerate(items):
        for token in item["any"]:
            found += [(m.start(), index) for m in re.finditer(re.escape(token.lower()), low)]
    return sorted(found)


def ranked(expect: dict, answer: str, found: list[float]) -> dict:
    """The k sellers in order, each with its price. Written 14 October 2026 for the top-k
    and named-comparison questions of the box v2 batch.

    A seller's price is read from the text between its neighbouring seller mentions, so
    "Alderney $25.77, Elmsworth $28.96" and "$25.77 from Alderney, $28.96 from Elmsworth"
    both give each seller its own price. A seller named more than once is stood for by the
    mention beside its expected price, so an answer that narrates the listings it opened
    before ranking them is read by its ranking. A seller named without any price nearby is
    not scored wrong but leaves the answer ambiguous; one whose nearby price is another
    figure is wrong, which also catches a neighbour's price given in place of its own.

    An item marked optional need not be named, but when it is named with a price the price
    must be its own: the loser of a comparison quoted at its advertised price is a wrong
    answer, however the winner is reported. Not caught: an extra seller ranked ahead of the
    expected ones, which the verifier reads for (LESSONS 4).
    """
    low = answer.lower()
    items = expect["items"]
    mentions = mentions_of(low, items)
    cuts = [position for position, _ in mentions]

    def nearby(position: int) -> list[float]:
        before = max([c for c in cuts if c < position], default=0)
        after = min([c for c in cuts if c > position], default=len(low))
        return prices_in(low[before:after])

    chosen, unpriced = [], []
    for index, item in enumerate(items):
        name = item["any"][0]
        own = [position for position, i in mentions if i == index]
        if not own:
            if item.get("optional"):
                continue
            return {"verdict": "wrong", "why": f"expected seller {name} not named", "prices": found}
        position = next((p for p in own if item["price"] in nearby(p)), own[0])
        prices = nearby(position)
        if item["price"] not in prices:
            if prices:
                return {"verdict": "wrong",
                        "why": f"{name} priced at {prices[0]}, expected {item['price']}",
                        "prices": found}
            if not item.get("optional"):
                unpriced.append(name)
        if not item.get("optional"):
            chosen.append(position)
    if chosen != sorted(chosen):
        return {"verdict": "wrong", "why": "sellers named out of order", "prices": found}
    if unpriced:
        return {"verdict": "ambiguous", "why": f"no price given for {', '.join(unpriced)}",
                "prices": found}
    return {"verdict": "correct", "why": "named every seller in order with its price",
            "prices": found}
