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

# Bumped whenever a strategy prompt changes in a way that changes behaviour. Runs made
# under different versions are different policies and must not be pooled, which is the
# same denominator discipline applied everywhere else. v1 lacked the enumeration step and
# pruned within whatever the first screen happened to show.
VERSION = 6

# Ordered, and the order matters. A universal question about stock also contains the word
# "lowest" in some phrasings, so the coverage test is applied before the price tests.
UNIVERSAL = re.compile(r"\b(every|all)\b.*\b(stock|carry|offer|have)\b", re.IGNORECASE)
# Added 18 Sep 2026 with the third availability state. A question that constrains the answer
# to what can actually be bought is a different retrieval problem from one that does not: the
# price bound still prunes, but the winner has to clear a second test the price never shows.
# Checked before the plain cheapest test, since these questions contain "cheapest" too.
BUYABLE = re.compile(
    r"\b(buy|bought|buyable|purchas\w+|available|in stock|suppl\w+|ship\w*)\b",
    re.IGNORECASE)
# Reviews gate by depth rather than by a click, so they need their own strategy. Checked
# first because a review question can contain almost any other keyword: a buyer may well
# mention a refund, a leak, or the cheapest place they found it.
REVIEWS = re.compile(r"\b(buyers?|reviewers?|reviews?)\b", re.IGNORECASE)
UNIT_RATE = re.compile(r"per\s+(litre|liter|kg|kilogram|unit)|best value", re.IGNORECASE)
CHEAPEST = re.compile(r"\b(cheapest|lowest price|lowest cost|least expensive)\b",
                      re.IGNORECASE)

# The largest pack in this catalogue, in litres. The rate bound needs an upper bound on
# how much volume an advertised price could be buying. Stated here as a fixture constant
# rather than discovered, and it is a genuine limitation: a policy that had to work on an
# unknown catalogue would have to establish this itself.
LARGEST_PACK_LITRES = 19


def classify(question: str) -> str:
    if REVIEWS.search(question):
        return "depth_search"
    if UNIVERSAL.search(question):
        return "refutation"
    if UNIT_RATE.search(question):
        return "rate_bound"
    if CHEAPEST.search(question) and BUYABLE.search(question):
        return "availability_bound"
    if CHEAPEST.search(question):
        return "total_bound"
    return "survey"



# A bound is a device for deciding what not to open. It is not a price, and the measured
# failure of the rate strategy was the agent carrying the bound's arithmetic into its
# answer: it combined an advertised price of $6.82 with the volume of a pack that actually
# costs $8.30, and reported $0.812 per litre for a pack that has no such rate. The
# arithmetic was right and the attribution was invented.
#
# So every strategy that hands the agent a bound now also says, in the same breath, that
# figures derived from it may not be reported. Stated once here and appended to both bound
# strategies, since the same hazard applies to each.

# A bound rules out candidates. It cannot rule out candidates you never knew existed, and
# the first run of this arm failed exactly there: the agent read the first four listings
# on the search page, treated those as the whole market, and pruned within them. It got
# the right answer twice because the true winner happens to sit inside the first four,
# which is luck rather than the strategy working. Seven actions against exhaustive's
# thirty-one was not a saving from pruning, it was a saving from not looking.
#
# So enumeration is now a separate, explicit first step, stated before any strategy. It
# costs actions, and honestly so: the price of a sound bound is knowing what you are
# bounding over.
ENUMERATE = (
    "First, establish the complete candidate set before opening anything.\n"
    "The search results are paginated. Go through every page and list every listing "
    "together with its advertised price. State how many listings exist in total, and do "
    "not assume the first screen is all of them.\n"
    "You may only skip a listing you have enumerated. A bound cannot rule out something "
    "you never knew was there.\n\n"
    "Then use this retrieval strategy.\n")

QUARANTINE = (
    "\nImportant: the figure this bound produces is a limit used only to decide what to "
    "skip. It is not a real price and must never appear in your answer. Only report a "
    "price you read from a listing you opened, attached to the exact pack size it was "
    "shown against. Never pair an advertised price with a pack size unless you opened the "
    "listing and saw that price shown for that pack.")

STRATEGIES = {
    "total_bound": (
        ENUMERATE + "Use this retrieval strategy, and follow it rather than opening listings in the "
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
        "skipping them was safe." + QUARANTINE),
    "refutation": (
        ENUMERATE + "Note what the question actually requires, because the two possible "
        "answers need very different amounts of work.\n"
        "To answer No you need exactly ONE listing that lacks the option. Nothing more. "
        "One counterexample settles a claim about every listing.\n"
        "To answer Yes you must have opened every single one.\n"
        "So hunt for a counterexample rather than surveying:\n"
        "1. Open a listing and check for the option asked about.\n"
        "2. If it lacks the option, you are finished. Answer No, name that listing as your "
        "evidence, and stop immediately. Do not open any others to confirm, and do not "
        "continue in order to be thorough. Opening more cannot change the answer.\n"
        "3. Only if you exhaust every enumerated listing without finding one may you "
        "answer Yes.\n"
        "In your answer, say how many listings you opened and which one settled it. "
        "Stopping after one or two openings is the correct outcome here, not a sign that "
        "you did too little.\n"
        "Note that the previous version of this instruction was followed to the letter and "
        "not to its point: the agent enumerated and then opened ten listings when the "
        "first counterexample had already settled the question."),
    "rate_bound": (
        ENUMERATE + "Use this retrieval strategy, and follow it rather than opening listings in the "
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
        "skipping them was safe." + QUARANTINE),
    "availability_bound": (
        ENUMERATE + "Use this retrieval strategy, and follow it rather than opening listings in the "
        "order they appear.\n"
        "1. Read the advertised price of every listing from the search results first. That "
        "price is the cheapest option in that listing, so nothing inside it can cost less.\n"
        "2. Open listings in ascending order of advertised price. For each one, do two "
        "separate things. Find the price for the option asked about, and check whether that "
        "option can actually be bought. An option can be listed and still be unavailable, "
        "in which case it is shown as disabled or greyed out and cannot be selected. Its "
        "price is still printed, and that price does not count.\n"
        "3. A listing only becomes your best candidate if the option is both cheaper and "
        "available. A cheaper unavailable one changes nothing.\n"
        "4. Skip every unopened listing whose advertised price is at or above your best "
        "available total. Such a listing cannot win whatever its stock.\n"
        "5. Stop when no unopened listing has an advertised price below your best available "
        "total.\n"
        "In your answer, name the seller, give the price, and say explicitly that you "
        "checked the option was available rather than only listed. Say how many listings "
        "you opened, how many you skipped, and how many you rejected for being unavailable."
        + QUARANTINE),
    "depth_search": (
        "Note what this question needs, because the two possible answers cost very "
        "different amounts.\n"
        "To answer yes you need exactly ONE review saying it. Quote that review and stop. "
        "Nothing is gained by finding a second.\n"
        "To answer no you must have read every review there is, and there are many more "
        "than the page shows.\n"
        "The reviews are paginated, ten to a page, and there is no way to filter or sort "
        "them. The first page is not a sample you can generalise from: complaints are a "
        "minority, so ten consecutive reviews frequently contain none even when several "
        "exist further in.\n"
        "So:\n"
        "1. Read page one and check for the thing asked about.\n"
        "2. If it is there, quote it, say which page, and stop.\n"
        "3. Otherwise turn to the next page and repeat. The page parameter is ?p=2, ?p=3 "
        "and so on.\n"
        "4. Only after reaching the last page without a single mention may you answer no.\n"
        "If you run out of budget before the last page, do not answer no. Say how many "
        "pages of how many you read and that you found no mention in those. An unread page "
        "is not an absence of evidence, and reporting it as one is the error this is "
        "written to prevent."),
    "survey": (
        ENUMERATE + "Open every listing in the search results and check the relevant option on each "
        "before answering. Say how many you opened."),
}


def targeting_query(question: str) -> tuple[str, str]:
    """The question with its strategy attached, and the strategy's name."""
    kind = classify(question)
    return f"{question}\n\n{STRATEGIES[kind]}", kind
