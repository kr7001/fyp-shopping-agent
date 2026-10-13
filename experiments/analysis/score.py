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
    none for it, so a question that was never ambiguous is scored as before."""
    expect = (readings.get(reading) or {}).get(task["id"]) if reading else None
    return {**task, "expect": expect} if expect else task


def score(task: dict, answer: str, ok: bool) -> dict:
    """Return verdict plus the evidence behind it, so results stay auditable."""
    answer = answer or ""
    expect = task["expect"]
    kind = expect["kind"]
    found = prices_in(answer)
    low = answer.lower()

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

    raise ValueError(f"unknown expect kind: {kind}")
