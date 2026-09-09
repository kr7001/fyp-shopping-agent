#!/usr/bin/env python3
"""Choose a retrieval strategy from the question, before any page is opened.

Everything built so far is reactive: it inspects an answer that already exists and decides
whether to trust it. This is the other half of RQ3 and it acts first, reading the question
and deciding what has to be retrieved to settle it.

Three strategies, because three kinds of question need different work, and the whole point
is that the choice is made from the question rather than applied uniformly.

**total bound.** "Which seller is cheapest for the 2 x 9.5L pack." The search page shows
each listing's lowest advertised price, and no option inside a listing can cost less than
that, so the advertised price is a valid lower bound on anything the listing could offer.
Open in ascending order of it and a listing can be skipped the moment its advertised price
reaches the best total already found. This is branch and bound, and the fixture reports 4
of 15 prunable with an oracle floor of 11.

**refutation.** "Does every listing stock the pack." A universal claim and its negation
need different amounts of evidence: proving it takes all fifteen, refuting it takes one.
Since ten of fifteen stock the pack the answer is No, and the cheapest correct route is to
hunt for a counterexample rather than to survey.

**rate bound.** "Best price per litre across all listings and pack sizes." The bound is
weaker but real. A listing's best possible rate is its advertised price divided by the
largest volume it could be offering, so if that already exceeds the best rate found, the
listing cannot win.

Classification reads the question text, not the task id. Keying off the id would make the
policy look like it works while doing nothing, since the id encodes the answer the
experiment is meant to test for.
"""

from __future__ import annotations

import re

# Ordered, and the order matters. A universal question about stock also contains the word
# "lowest" in some phrasings, so the coverage test is applied before the price tests.
UNIVERSAL = re.compile(r"\b(every|all)\b.*\b(stock|carry|offer|have)\b", re.IGNORECASE)
UNIT_RATE = re.compile(r"per\s+(litre|liter|kg|kilogram|unit)|best value", re.IGNORECASE)
CHEAPEST = re.compile(r"\b(cheapest|lowest price|lowest cost|least expensive)\b",
                      re.IGNORECASE)

# The largest pack in this catalogue, in litres. The rate bound needs an upper bound on
# how much volume an advertised price could be buying. Stated here as a fixture constant
# rather than discovered, and it is a genuine limitation: a policy that had to work on an
# unknown catalogue would have to establish this itself.
LARGEST_PACK_LITRES = 19


def classify(question: str) -> str:
    if UNIVERSAL.search(question):
        return "refutation"
    if UNIT_RATE.search(question):
        return "rate_bound"
    if CHEAPEST.search(question):
        return "total_bound"
    return "survey"


STRATEGIES = {
    "total_bound": (
        "Use this retrieval strategy, and follow it rather than opening listings in the "
        "order they appear.\n"
        "1. Read the advertised price of every listing from the search results first. "
        "That price is the cheapest option in that listing, so nothing inside it can cost "
        "less.\n"
        "2. Open listings in ascending order of advertised price. For each, find the "
        "actual total for the pack size asked about.\n"
        "3. After each one, skip every unopened listing whose advertised price is already "
        "at or above the best total you have found. Such a listing cannot win, so opening "
        "it cannot change the answer.\n"
        "4. Stop as soon as no unopened listing has an advertised price below your best "
        "total.\n"
        "In your answer, say how many listings you opened, how many you skipped, and why "
        "skipping them was safe."),
    "refutation": (
        "Use this retrieval strategy, and note what the question actually requires.\n"
        "It asks whether EVERY listing qualifies. Those two possible answers need "
        "different amounts of evidence. To answer No you need one counterexample and "
        "nothing more. To answer Yes you need to have checked all of them.\n"
        "1. Open listings and check the option asked about.\n"
        "2. The moment you find one that does not have it, you can answer No and stop. "
        "Name it as your evidence.\n"
        "3. Only if you have opened every listing without finding a counterexample may "
        "you answer Yes.\n"
        "In your answer, say how many listings you opened and which one settled it."),
    "rate_bound": (
        "Use this retrieval strategy, and follow it rather than opening listings in the "
        "order they appear.\n"
        f"1. The largest pack any listing offers is {LARGEST_PACK_LITRES} litres, so a "
        "listing's best possible price per litre is its advertised price divided by "
        f"{LARGEST_PACK_LITRES}. Nothing it offers can beat that figure.\n"
        "2. Open listings in ascending order of advertised price, and for each work out "
        "the actual best price per litre across its pack sizes.\n"
        "3. Skip any unopened listing whose advertised price divided by "
        f"{LARGEST_PACK_LITRES} is already at or above the best rate you have found. It "
        "cannot win.\n"
        "4. Stop when no unopened listing can beat your best rate.\n"
        "In your answer, say how many listings you opened, how many you skipped, and why "
        "skipping them was safe."),
    "survey": (
        "Open every listing in the search results and check the relevant option on each "
        "before answering. Say how many you opened."),
}


def targeting_query(question: str) -> tuple[str, str]:
    """The question with its strategy attached, and the strategy's name."""
    kind = classify(question)
    return f"{question}\n\n{STRATEGIES[kind]}", kind
