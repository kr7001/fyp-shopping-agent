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
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/ on the path)

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
#   4  22 October 2026, from the verifier's audit of the model's front door. The key a run
#      is scored under is the one for the reading its own box record holds, and a run
#      answered under a reading its task file has no key for is unscored, with the reason,
#      never scored under the task's own key (`under_reading`, `score_under`). Re-scored
#      over every stored run that day, no verdict changes
#   5  22 October 2026, for the second claim market, whose water is sold by the pack. A
#      variant's own label is never a price or a count (`VARIANT_LABEL`): until v5 the
#      count rule read "The 2 x 9.5L pack is in stock at 9 listings" as 2, and `prices_in`
#      read 1.25 from "6 x 1.25L" as a price
#   6  22 October 2026, from the verifier's check of the second claim market. An answer to a
#      "contains" question that names both the expected option and an excluded one is
#      scored by the one it names as the best (`named_best`). Until v6 naming the expected
#      one anywhere won, so "Chandler Direct's 2 x 9.5L ... is the best value; Ambleside's
#      6 x 1.25L is close behind" was correct where Ambleside is the key. Re-scored over
#      every stored run that day: one verdict changes, 20260914T034338
#      scaled-cheapest-target-2, correct to wrong, an answer that named Hillside the
#      cheapest and Redhill, the key, only in a note
VERSION = 6

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


# A variant's own label, which is never a price or a count (score v5, 22 October 2026): a pack,
# a count of bottles times a volume, "2 x 9.5L", "24x350ml", "6 × 1.25 L", with any spacing,
# and a volume on its own, "1.25L", "350 ml", "9.5-litre". The shop's clothing sizes, S to
# XL, hold no figure, so only the water's labels have numbers to set aside. A whole number
# followed by a lone "L" after a space, "3 L", is left alone: it may be a count of size L.
VARIANT_LABEL = re.compile(
    r"\b\d+\s*[x×]\s*\d+(?:\.\d+)?\s*(?:ml|l|litres?|liters?)\b"
    r"|\b\d+(?:\.\d+)?[\s-]*(?:ml|litres?|liters?)\b"
    r"|\b\d+(?:\.\d+)?l\b|\b\d+\.\d+\s+l\b", re.IGNORECASE)


def without_labels(text: str) -> str:
    """The answer with every variant label blanked, character for character, so a position
    in it is a position in the answer."""
    return VARIANT_LABEL.sub(lambda m: " " * len(m.group(0)), text or "")


# What an answer says is the best of what it compares (score v6): "the cheapest", "the best
# value", "the lowest price per litre". A sentence that says none of these only reports.
SUPERLATIVE = re.compile(r"\b(?:best|cheapest|lowest|least\s+expensive|most\s+affordable)\b",
                         re.IGNORECASE)
# The sentences of an answer, never cut at a decimal point: a stop, a question mark, an
# exclamation or a semicolon followed by a space, or a new line.
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\n+")


def named_best(answer: str, wanted: list[str], excluded: list[str]) -> str | None:
    """Which side the answer names as the best, "wanted" or "excluded", or None when no
    sentence makes a superlative claim about either (score v6, 22 October 2026). The first
    sentence that says "best", "cheapest" or "lowest" and names an option decides, by the
    option named nearest the first such word: the answer's conclusion comes in it however
    much it compares after."""
    for sentence in SENTENCE_END.split(answer or ""):
        low = sentence.lower()
        claim = SUPERLATIVE.search(low)
        if claim is None:
            continue
        named = [(abs(m.start() - claim.start()) if m.start() > claim.start()
                  else max(0, claim.start() - m.end()), side)
                 for side, tokens in (("wanted", wanted), ("excluded", excluded))
                 for token in tokens for m in re.finditer(re.escape(token.lower()), low)]
        if named:
            return min(named)[1]
    return None


def has_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(m)}\b", text) for m in markers)


def prices_in(text: str) -> list[float]:
    """Every money-looking number in the answer, in order of appearance, none inside a
    variant's label (score v5): "6 x 1.25L at $6.84" names one price, 6.84."""
    return [float(m) for m in re.findall(r"(?<![\d.])(\d{1,4}\.\d{2})(?![\d])", without_labels(text))]


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


def two_readings_for(tasks_path: pathlib.Path) -> list[str] | None:
    """The questions of a task file that have two readings, as its sidecar names them under
    `two_readings` (the A+ market's, 22 October 2026, whose sidecar holds a buyable key for
    every question, so being in it no longer says that a question has two). None for a
    sidecar without the field, or no sidecar: there every question in it has two."""
    sidecar = tasks_path.with_name(tasks_path.name.replace("tasks_", "readings_", 1))
    if sidecar == tasks_path or not sidecar.exists():
        return None
    return json.loads(sidecar.read_text()).get("two_readings")


# The reading every task's own key was written under, fixed before any run: "offer" means
# in the menu, sold out or not. A sidecar holds the other readings and never this one.
OWN_READING = "menu"


class NoKeyForReading(ValueError):
    """A run answered under a reading its task file has no key for."""


def under_reading(task: dict, reading: str | None, readings: dict,
                  two_readings: list[str] | None = None) -> dict:
    """The task with the answer key for the reading the run was answered under.

    `reading` is what the box did, read from the run's own box record: the reading its
    record holds, the user's reply to an ask it put or the reading it took itself, and None
    when it applied none (`suite.reading_answered`, `verify_cells.run_reading`). Never a
    batch's `--reading` flag, which is a reply only where the box asked, and never the word
    list's guess at whether the question has two readings. No reading, and the menu reading
    every task's own key was written under (`OWN_READING`), take the task's own key, as does
    a question with no key at all. Any other reading takes the sidecar's key for it, and
    with none there the run cannot be scored: this raises, and never falls back to the
    task's own key, since the question the agent was sent was not the task's question.

    Until 20 October 2026 such a reading fell back to the task's own key without a word;
    from then until 22 October it raised only on a question the word list (`ambiguity.ask`)
    reads two ways, so a model's ask on a question the word list reads as clear, answered
    as buyable, was scored under the menu key (verifier finding, 22 October 2026: a correct
    7 for "is size M an option" was scored wrong against the menu's 10). Re-scored over
    every stored run on 22 October 2026, no verdict changes: every stored run answered
    under the buyable reading is on a question the sidecar holds a key for.

    `two_readings`, when given, are the questions whose own key is the menu reading (the
    sidecar's, 23 October 2026, the verifier's FAIL at cce9ab0): elsewhere the key counts
    what can be bought, so "menu" has no key there and raises. Without it every key is the
    menu reading's, as for every caller but suite.py."""
    own = reading == OWN_READING and (two_readings is None or task["id"] in two_readings)
    if reading is None or own or task["expect"].get("kind") == "none":
        return task
    expect = (readings.get(reading) or {}).get(task["id"])
    if expect:
        return {**task, "expect": expect}
    raise NoKeyForReading(f"{task['id']} was answered under the {reading!r} reading, and its "
                          f"readings sidecar has no key for that reading")


def score_under(task: dict, reading: str | None, readings: dict, answer: str, ok: bool) -> dict:
    """A run's verdict under the key for the reading it was answered under, or "unscored",
    with the reason, when its task file has no key for that reading (22 October 2026)."""
    try:
        keyed = under_reading(task, reading, readings)
    except NoKeyForReading as fault:
        return {"verdict": "unscored", "why": f"no answer key for this run: {fault}",
                "prices": prices_in(answer or "")}
    return score(keyed, answer, ok)


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
        # Naming both, the answer is held to the one it says is the best (score v6).
        if hit and bad and named_best(answer, expect["any"], expect["not_any"]) == "excluded":
            return {"verdict": "wrong", "why": "named an excluded option as the best",
                    "prices": found}
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
        # digits inside a price, nor since score v5 those inside a variant's label, "the
        # 2 x 9.5L pack". If that leaves nothing, the first number is used after all, since
        # "All 15 listings offer it" is a count of 15.
        bare = without_labels(answer)
        numbers = list(re.finditer(r"(?<![\d.$])(\d{1,3})(?![\d.])", bare))
        if not numbers:
            return {"verdict": "ambiguous", "why": "no number given", "prices": found}
        coverage = {m.start(1) for m in COVERAGE_NUMBER.finditer(bare)}
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
