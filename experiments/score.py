#!/usr/bin/env python3
"""Score a browser run's free-text answer against a task's ground truth.

Answers are prose, so scoring is deliberately conservative. A run counts as
correct only when the expected value is present and the specific wrong answer the
task is designed to provoke is absent. Anything else is `wrong`, except a run
that declines to answer, which is `abstained` and is a materially different
outcome: a policy that says "I could not determine this" has not misled anyone.
"""

from __future__ import annotations

import re

# Phrases that mean the agent declined rather than answered. Kept narrow on
# purpose: "not" alone is far too broad, "could not determine" is not.
ABSTENTION_MARKERS = (
    "unable to", "could not determine", "couldn't determine", "cannot determine",
    "can't determine", "not able to", "unable", "no answer", "insufficient",
    "need more information", "could not find", "couldn't find", "cannot find",
    "not found", "unclear", "i don't know", "i do not know",
)

NEGATIVE_MARKERS = ("no", "not available", "out of stock", "unavailable", "sold out")
POSITIVE_MARKERS = ("yes", "in stock", "available")


def prices_in(text: str) -> list[float]:
    """Every money-looking number in the answer, in order of appearance."""
    return [float(m) for m in re.findall(r"(?<![\d.])(\d{1,4}\.\d{2})(?![\d])", text or "")]


def abstained(text: str) -> bool:
    low = (text or "").lower()
    return any(marker in low for marker in ABSTENTION_MARKERS)


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
        # Check the negative first: "not available" contains "available".
        says_no = any(m in low for m in NEGATIVE_MARKERS)
        says_yes = any(m in low for m in POSITIVE_MARKERS) and not says_no
        if says_no == (not wants_yes) and (says_no or says_yes):
            return {"verdict": "correct", "why": f"answered {'no' if says_no else 'yes'}",
                    "prices": found}
        if not says_no and not says_yes:
            return {"verdict": "ambiguous", "why": "no clear yes or no", "prices": found}
        return {"verdict": "wrong", "why": f"answered {'no' if says_no else 'yes'}",
                "prices": found}

    if kind == "all_prices":
        wanted = set(expect["values"])
        missing = sorted(wanted - set(found))
        if not missing:
            return {"verdict": "correct", "why": "listed every price", "prices": found}
        return {"verdict": "wrong", "why": f"missing {missing}", "prices": found}

    raise ValueError(f"unknown expect kind: {kind}")
