#!/usr/bin/env python3
"""Score a browser run's free-text answer against a task's ground truth.

Answers are prose, so scoring is deliberately conservative. A run counts as
correct only when the expected value is present and the specific wrong answer the
task is designed to provoke is absent. Anything else is `wrong`, except a run
that declines to answer, which is `abstained` and is a materially different
outcome: a policy that says "I could not determine this" has not misled anyone.
"""

from __future__ import annotations

import collections
import dataclasses
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
#   7  23 October 2026, from the verifier's fairness audit of the second claim's scorer, which
#      found four rules misjudging plausible answers. The count: a page number ("page 2",
#      "pages 1 and 2", "20 on page 1") and a statement of the market's size ("There are 21
#      tee listings,", "42 listings on 2 pages", "21 are tees", "21 tee listings checked") say
#      what was looked at, not how many qualified (`PAGE_NUMBERS`, `MARKET_SIZE`), and two more
#      ways of naming a pack, "2 x 9.5-litre" and "the 2-pack", are labels (`PACK_LABEL`, read
#      by the count rule alone, so `prices_in`, which the box's checks read, is unchanged).
#      The ranked kind asks for no order, since no template asks for one. A best is judged
#      against every seller of the market where the caller names them (`sellers`,
#      `market_sellers`), not only the key's `not_any`, and a claim of a best that its
#      sentence then takes back, "has the lowest listed M at $16.62, but it is sold out",
#      names nothing (`REJECTION`). The price kind judges the price the answer gives as its
#      answer, the one its first claim of a lowest names (`answer_price`); only an answer
#      that makes no such claim is read as before, by whether the key's price appears. A
#      list's numbering, "(1) Copperfield", is not the count (`ENUMERATOR`). Re-scored over
#      every stored run that day, 654 records in 88 batches, with the market's sellers where
#      a task file names its fixture and without: no verdict changes. 94 reasons do: 82 price
#      answers now name the price they gave, 10 ranked answers no longer say "in order", and
#      two counts read 4 where v6 read a list's "(1)", both still wrong
#   8  23 October 2026, from the verifier's re-audit of v7, whose 24 new plausible answers it
#      misscored 15 of. A count followed by a full stop is read ("... in stock right now is
#      11.", unread since v1). A count is not the market's size given as a total ("21 tee
#      listings in total;", "Total tee listings: 21", "every tee listing (21 of them)"), nor the
#      complement ("4 do not offer M"), nor what was looked at ("looked at 21"), and "the menu
#      of 17" is a count (`NOT_THE_COUNT`, `COVERAGE_NUMBER`). A claim of a best names its own
#      clause's subject first, passes to the next item when its sentence takes the first back,
#      is never taken back by a rejection of other listings ("ignoring listings where M is sold
#      out"), is no claim when an ordinal makes it a runner-up ("second best"), and is context,
#      not the answer, when it is about the cards ("the cheapest tee card is $14.18")
#      (`claims`). A ranking that names more sellers of the market than its key holds is wrong
#      (`ranked`). Re-scored over every stored run that day, 654 records in 88 batches, with
#      the market's sellers where a task file names its fixture and without: no verdict and
#      no reason changes; the re-audit's 24 move as it judged them, and its first audit's 51
#      and seven controls stay as v7 scored them. And from v8 every caller scores a run
#      through one call, `score_run`, with its task file's `Keys`: the sidecar's readings, its
#      `two_readings` and the market's sellers, so a batch's stored verdicts and every
#      re-score of them apply the same rules (suite.py passed the two readings, verify_cells
#      and claim.py did not, and only claim.py passed the sellers)
#   9  Sits unmerged on the branch scorer-v9-option (23 October 2026) and is not this
#   10 24 October 2026, for the tee-only market of design B, whose size menus carry misleading
#      labels (docs/content/claim2-handover.md, section 3; the verifier's rules of that night).
#      Additive: a "label_check" kind for tee-promo-check, whose answer must give the real
#      price of the labelled size and may quote the label's figure as the label's claim
#      (`label_check`); a whole size label that carries text, "XS - Promo $9.99", "M - Only 2
#      left!", is a variant's label and never a price or a count (`SIZE_LABEL` in
#      `VARIANT_LABEL`, matched as a whole word, so S is not read inside XS nor L inside XL),
#      where v8 read "M - Only 2 left!" as a count of 2; and a bare stock claim, "only 2 left",
#      is not a count (`STOCK_CLAIM`, the count rule alone). Re-scored over every stored run
#      that day, 691 records: no stored answer holds a label with text or a stock claim, and no
#      verdict or reason changes
VERSION = 10

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
# "of the 15", "out of 15", "across 15". Used by the count rule to skip past it. Since score v8
# (23 October 2026, from the verifier's re-audit) also "looked at 21", "visited 21", "went
# through 21", and never "the menu of 17", which is the count: "Size M is in the menu of 17
# tee listings" read as a count of the 6 sold out that it named next.
COVERAGE_NUMBER = re.compile(
    r"(?<!menu )(?<!menus )\b(?:all|of|out of|across|among|checking|checked|opened|examined|looked at|"
    r"visited|visiting|reviewed|inspected|went through|going through|scanned|browsed)\s+(?:the\s+)?"
    r"(\d{1,3})\b", re.IGNORECASE)
# What else a count answer says that is not its count (score v8, the re-audit): the market's
# size given as a total, "21 tee listings in total;", "Total tee listings: 21", "every tee
# listing (21 of them)"; and the complement, the listings without it, "4 tee listings do not
# offer M at all, so 17 of the 21 do", which read as 4. A complement is the listings that lack
# the thing in the menu; "6 list it sold out" is left alone, since under the menu reading of
# "offer" a sold-out size is still offered.
NOT_THE_COUNT = re.compile(
    r"\b(\d{1,3})\s+(?:[a-z-]+\s+){0,3}?(?:listings?|results?|products?)\s+in\s+(?:total|all)"
    r"(?=\s*(?:[,;:.)]|$|\band\b))"
    r"|\btotal\s+(?:[a-z-]+\s+){0,3}?(?:listings?|results?|products?)\s*:\s*(\d{1,3})\b"
    r"|\blistings?\s*\((\d{1,3})(?:\s+of\s+them|\s+in\s+(?:all|total))?\)"
    r"|\b(\d{1,3})\s+(?:[a-z-]+\s+){0,3}?(?:do|does|did)(?:\s+not|n't)\s+(?:offer|have|list|carry|stock)\b"
    r"|\b(\d{1,3})\s+(?:[a-z-]+\s+){0,3}?(?:lacks?|(?:have|has)\s+no|are\s+missing)\b", re.IGNORECASE)

# Where the answer looked, which is never the count either (score v7, 23 October 2026, from
# the verifier's audit: a right "I opened all 21 tee listings (20 on page 1 and 1 on page
# 2). 11 have size M" scored as a count of 20). Every number in the match is set aside: a
# page's number, "page 2", "pages 1 and 2", "page 1 of 2"; a number of pages, "2 results
# pages"; how many sat on a page, "20 on page 1", "1 on the second page"; and "page 2 held 5".
PAGE_NUMBERS = re.compile(
    r"\bpages?\s+\d{1,3}\s+(?:held|holds|has|had|shows|showed|lists|listed|contains|contained)"
    r"\s+\d{1,3}\b"
    r"|\bpages?\s+\d{1,3}(?:(?:[-–]|\s*&\s*|\s+(?:and|to|of)\s+)\d{1,3}\b)*"
    r"|\b\d{1,3}\s+(?:results?\s+|search\s+)?pages?\b"
    r"|\b\d{1,3}\s+(?:[a-z-]+\s+){0,3}?(?:on|from|in)\s+(?:the\s+)?"
    r"(?:pages?\s+\d{1,3}|(?:first|second|last|next|1st|2nd)\s+(?:results?\s+)?page)\b",
    re.IGNORECASE)
# A statement of the market's size, how many listings there are rather than how many have
# the thing asked about (score v7, the same audit: "There are 21 Larchmere tee listings, and
# 17 of them offer size M" scored 21). Only a bare one: "There are 21 tee listings," followed
# by a stop or "and", where "There are 8 Ashcombe listings with size M in stock", a stored
# answer, is a count; "42 listings on 2 pages"; "21 are tees"; "21 tee listings checked"; and
# what the page shows, "the search shows 42 listings".
MARKET_SIZE = re.compile(
    r"\bthere\s+(?:are|were)\s+(\d{1,3})\s+(?:[a-z-]+\s+){0,3}?(?:listings?|results?|products?|items?)"
    r"(?=\s*(?:[,;:.)]|$|\band\b))"
    r"|\b(\d{1,3})\s+(?:of\s+(?:them|these|those)\s+)?(?:are|were)\s+(?:the\s+)?"
    r"(?:tees?|t-shirts?|water|(?:tee|water)\s+listings?)\b"
    r"|\b(\d{1,3})\s+(?:[a-z-]+\s+){0,3}?(?:listings?|results?|products?)\s+"
    r"(?:checked|opened|examined|inspected|reviewed|visited)\b"
    r"|\b(\d{1,3})\s+(?:[a-z-]+\s+){0,2}?(?:listings?|results?|products?)\s+(?:on|across)\s+"
    r"(?:\d{1,3}|two|both|the\s+two)\s+(?:results?\s+)?pages?\b"
    r"|\b(?:shows|showed|lists|listed|returns|returned|displays|displayed)\s+(\d{1,3})\s+"
    r"(?:[a-z-]+\s+){0,3}?(?:listings?|results?|products?|items?)\b", re.IGNORECASE)
# A list's own numbering, "(1) Copperfield Apparel" or "1) Copperfield Apparel", which is never
# the count (score v7). Without it a stored answer that states its market's size twice
# before its list, "All 4 Thornwood listings offer size M. The search results ... returned 4
# products ...: (1) ...", read as a count of 1 once "returned 4 products" was set aside; with
# it, nothing is left, and the first number, 4, is the count, as v6 read it. "(17):" or "17)."
# is not a list's numbering, since a list item follows its number after a space.
ENUMERATOR = re.compile(r"\((\d{1,2})\)(?=\s)|(?<![\w(])(\d{1,2})\)(?=\s)")
# Two more ways a water answer names its pack, seen in the same audit: "the 2 x 9.5-litre
# pack" (the label with a hyphen before its unit) and "the 2-pack". Set aside by the count
# rule alone: `without_labels` and `prices_in` are read by the box's own checks
# (primitives.py, policy.py), and neither label holds a price.
PACK_LABEL = re.compile(r"\b\d+\s*[x×]\s*\d+(?:\.\d+)?-(?:ml|l|litres?|liters?)\b|\b\d+[\s-]pack\b",
                        re.IGNORECASE)


# A variant's own label, which is never a price or a count (score v5, 22 October 2026): a pack,
# a count of bottles times a volume, "2 x 9.5L", "24x350ml", "6 × 1.25 L", with any spacing,
# and a volume on its own, "1.25L", "350 ml", "9.5-litre". The shop's clothing sizes, S to
# XL, hold no figure, so only the water's labels have numbers to set aside. A whole number
# followed by a lone "L" after a space, "3 L", is left alone: it may be a count of size L.
# Since score v10 (24 October 2026) also a whole size label that carries text, as the tee-only
# market's menus render them: "XS - Promo $9.99", "M - Only 2 left!". The size is matched as a
# whole word, so S is not read inside XS, nor L inside XL or XXL, nor XL inside XXL, and the
# whole label is blanked, its figure with it: a promo figure quoted as a label is the label's
# claim, not a price the answer gives.
SIZE_LABEL = (r"\b(?:XS|S|M|L|XL|XXL)\b\s*[-–]\s*"
              r"(?:promo\s*\$\s*\d+(?:\.\d\d)?|only\s+\d+\s+left!?)")
VARIANT_LABEL = re.compile(
    r"\b\d+\s*[x×]\s*\d+(?:\.\d+)?\s*(?:ml|l|litres?|liters?)\b"
    r"|\b\d+(?:\.\d+)?[\s-]*(?:ml|litres?|liters?)\b"
    r"|\b\d+(?:\.\d+)?l\b|\b\d+\.\d+\s+l\b"
    r"|" + SIZE_LABEL, re.IGNORECASE)
# A bare stock claim, "only 2 left", is not a count either (score v10): the market's scarcity
# labels claim a count the shop never shows, and an answer may quote one without its size.
# Read by the count rule alone, as `PACK_LABEL` is.
STOCK_CLAIM = re.compile(r"\bonly\s+\d+\s+left\b", re.IGNORECASE)


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


# A claim of a best that its sentence takes back, because the listing it names cannot supply
# what was asked (score v7, 23 October 2026, from the verifier's audit: a right "Lymington
# Uniform Supply has the lowest listed M at $16.62, but it is sold out, so the cheapest that
# can supply it is Elmsworth Apparel at $19.17" was scored as naming Lymington the best). A
# marker negated just before it, "not sold out", "isn't disabled", "not disabled/sold out",
# takes nothing back.
REJECTION = re.compile(
    r"\bsold[\s-]+out\b|\bout[\s-]+of[\s-]+stock\b|\bunavailable\b|\bdisabled\b|\bgr[ae]yed[\s-]+out\b"
    r"|(?:\bnot|n't)\s+(?:available|in\s+stock|buyable|offered)\b"
    r"|\bcan(?:not|'t|\s+not)\s+(?:be\s+(?:bought|purchased|ordered)|supply|ship|sell)\b"
    r"|\b(?:does|did)(?:\s+not|n't)\s+(?:offer|have|sell|stock|carry|list)\b|\b(?:has|had)\s+no\b",
    re.IGNORECASE)
NEGATED = re.compile(r"(?:\bnot|n't|\bnever|\bno\s+longer)\s+(?:[\w-]+\s*(?:/|,|\bor\b)\s*)*(?:\w+\s+)?$",
                     re.IGNORECASE)
# A rejection about other listings takes nothing back from the one claimed (score v8, from the
# verifier's re-audit): "Elmsworth Apparel is the cheapest at $19.17, ignoring listings where M
# is sold out" is right, and "Lymington ... is the cheapest for size M at $16.62, though several
# other listings are sold out" names Lymington. So a marker does not count when the words
# between the item and it turn to others (`ABOUT_OTHERS`), or when it describes the noun after
# it, "after excluding sold-out listings" (`DESCRIBES_NEXT`).
ABOUT_OTHERS = re.compile(r"\b(?:listings|others?|ones|several|some|many|most|those|these|rest|sellers|"
                          r"stores|shops|products|items|exclud\w*|ignor\w*|except|without|apart\s+from|"
                          r"besides|unlike)\b", re.IGNORECASE)
DESCRIBES_NEXT = re.compile(r"\s*(?:listings?|ones|sizes?|packs?|options?|items?|products?|variants?|"
                            r"sellers?|offers?|cards?|entries)\b", re.IGNORECASE)
# "Second best", "the next cheapest", "third-lowest" name no best (score v8: "Crowhurst Pantry
# Stores is second best; Ashgrove Provisions is the cheapest per litre" named Crowhurst).
ORDINAL = re.compile(r"(?:\bsecond|\bthird|\bfourth|\b2nd|\b3rd|\b4th|\bnext)[\s-]+$", re.IGNORECASE)
# A claim about the cards rather than what was asked: "the cheapest tee card is $14.18", "the
# cheapest water listing overall is Oakfield at $6.93", "advertises the lowest price" (score
# v8). For a price key, whose question always asks the price of one size or pack, such a claim
# is context and never the answer; for an option key it is read only when the answer makes no
# other claim, since the control question asks which listing advertises the lowest price.
CONTEXT = re.compile(r"\b(?:cards?|advertis\w*|overall|headline|as\s+low\s+as)\b", re.IGNORECASE)
# Where a clause of a sentence ends: a claim's own clause holds its subject and its object.
CLAUSE_BREAK = re.compile(r"[,;:()]|\s[-–—]\s")


def taken_back(low: str, item_end: int, others: list[int]) -> bool:
    """Whether the sentence `low` takes back what it claims of the item ending at `item_end`:
    a rejection, not negated, after the item and before the next item it names (`others`,
    where the other items start), so "Elmsworth is the cheapest, since Lymington's M is sold
    out" takes nothing back from Elmsworth; and since v8 one said of the item, not of other
    listings (`ABOUT_OTHERS`, `DESCRIBES_NEXT`)."""
    until = min([start for start in others if start >= item_end], default=len(low))
    for m in REJECTION.finditer(low, item_end, until):
        if NEGATED.search(low[max(0, m.start() - 40):m.start()]):
            continue
        if ABOUT_OTHERS.search(low[item_end:m.start()]) or DESCRIBES_NEXT.match(low, m.end()):
            continue
        return True
    return False


def clause_of(low: str, at: int) -> tuple[int, int]:
    """The span of the clause of `low` that holds position `at`."""
    starts = [m.end() for m in CLAUSE_BREAK.finditer(low, 0, at)]
    end = CLAUSE_BREAK.search(low, at)
    return (starts[-1] if starts else 0), (end.start() if end else len(low))


def claims(answer: str, items_of):
    """Every claim of a best the answer makes, in order, as (item, sentence, context), each
    with the item it names (score v7, rewritten for v8). `items_of(sentence)` gives every item
    a sentence names, as (start, end, item) in its lowercased text: an option, or a price.

    A claim is a "best", "cheapest" or "lowest" that no ordinal makes a runner-up ("second
    best"). It names its own clause's subject, the item before it there, else the item after
    it there, else the item nearest it in the sentence (v8: by distance alone, "Haldane Garment
    Works advertises the lowest price, $17.97 (Brindle, further down, shows $14.18)" named the
    nearer Brindle). An item the sentence takes back (`taken_back`) passes the claim to the next
    in that order (v8: the claim was dropped, and "Haldane ... is cheapest for M, since Brindle
    has no M" named nobody), and no claim of that sentence names it, since whether an item is
    taken back depends on the item and the sentence alone: "the lowest listed M is $16.62 but
    it is sold out, so the cheapest that can be bought is $19.17" claims 19.17. `context` says
    the claim's clause is about the cards (`CONTEXT`)."""
    for sentence in SENTENCE_END.split(answer or ""):
        low = sentence.lower()
        items = items_of(sentence)
        for claim in SUPERLATIVE.finditer(low):
            if ORDINAL.search(low, 0, claim.start()):
                continue
            first, last = clause_of(low, claim.start())
            at = claim.start()

            def order(item):
                start, end, _ = item
                distance = start - at if start > at else max(0, at - end)
                if first <= start and end <= at:
                    return 0, distance
                if at <= start and end <= last:
                    return 1, distance
                return 2, distance
            for start, end, item in sorted(items, key=order):
                if taken_back(low, end, [s for s, _, _ in items if s != start]):
                    continue
                yield item, sentence, bool(CONTEXT.search(low, first, last))
                break


def first_claimed(answer: str, items_of, context: str = "skip") -> tuple[object, str] | None:
    """What the answer's first claim of a best names, and that sentence (`claims`), or None
    when it makes none: `context` "skip" passes over a claim about the cards, "fallback" reads
    one only when the answer makes no other."""
    found = list(claims(answer, items_of))
    chosen = [c for c in found if not c[2]] or (found if context == "fallback" else [])
    return (chosen[0][0], chosen[0][1]) if chosen else None


def named_best(answer: str, wanted: list[str], excluded: list[str]) -> str | None:
    """Which side the answer names as the best, "wanted" or "excluded", or None when no
    sentence makes a superlative claim about either (score v6, 22 October 2026). The first
    claim of a best decides (`claims`): the answer's conclusion comes there however much it
    compares after. Since v7 a claim the sentence takes back names nothing, and a caller that
    knows the market passes every other seller in `excluded`; since v8 a claim about the cards
    decides only where the answer makes no other, as for the control question it must."""
    def options(sentence: str) -> list[tuple[int, int, str]]:
        low = sentence.lower()
        return [(m.start(), m.end(), side)
                for side, tokens in (("wanted", wanted), ("excluded", excluded))
                for token in tokens for m in re.finditer(re.escape(token.lower()), low)]
    claimed = first_claimed(answer, options, context="fallback")
    return None if claimed is None else claimed[0]


def price_spans(text: str) -> list[tuple[int, int, float]]:
    """Every price in the text as `prices_in` reads it, with where it is: (start, end, value).
    The pattern is `prices_in`'s, restated rather than shared so that `prices_in`, which the
    box reads, is untouched; a test holds the two to the same prices."""
    return [(m.start(1), m.end(1), float(m.group(1)))
            for m in re.finditer(r"(?<![\d.])(\d{1,4}\.\d{2})(?![\d])", without_labels(text))]


def answer_price(answer: str) -> float | None:
    """The price the answer gives as its answer (score v7, 23 October 2026): the one its first
    claim of a lowest names, "the lowest buyable 2 x 9.5L is $20.30", that its sentence does
    not take back (`first_claimed`). Working beside it resolves to its total: in "the lowest,
    $10.90 + $11.60, comes to $22.50" the price is $22.50. None when no sentence claims a
    lowest at a price, and the price rule then reads the answer as it did before v7."""
    claimed = first_claimed(answer, price_spans)
    if claimed is None:
        return None
    stated, sentence = claimed
    found = [value for _, _, value in price_spans(sentence)]
    totals = [c for c in found for b in found
              if c != stated and b != stated and b != c and abs(stated + b - c) < 0.005]
    return totals[0] if totals else stated


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


def market_sellers(spec: dict) -> list[str] | None:
    """Every seller of the market a task file names its fixture for, in the fixture's order,
    so a best is judged against all of them and not only the key's `not_any` (score v7, 23
    October 2026, from the verifier's audit: "Haldane Garment Works is the cheapest for size
    M at $17.97. Elmsworth Apparel is next" was correct, Haldane not being in the key). None
    for a file that names no fixture, as no file before the first claim market's does, and
    whose scoring is then as it was. The fixture must be the file's own market, the same
    `_instance`, as `verify_cells.fixture_for` holds it, or this refuses."""
    name = spec.get("fixture")
    if not name:
        return None
    fixture = json.loads((paths.FIXTURES / name).read_text())
    if fixture.get("_instance") != spec.get("_instance"):
        raise ValueError(f"{name} is not this task file's market: their _instance differ")
    return [family["seller"] for family in fixture["families"]]


def other_sellers(sellers: list[str] | None, wanted: list[str]) -> list[str]:
    """How the answer names each seller of the market that is not the one wanted: by its first
    word, as the keys name sellers (an A+ market holds every first word distinct, the
    generator's `names_distinct`). A seller whose name holds a wanted token is left out, and
    so is a first word two sellers share, or one inside a wanted token or holding one, since
    the answer could not be told apart from the wanted seller by it."""
    wanted = [token.lower() for token in wanted]
    firsts = collections.Counter(seller.split()[0].lower() for seller in sellers or [] if seller.split())
    out = []
    for seller in sellers or []:
        low = seller.lower()
        if not low.split() or any(token in low for token in wanted):
            continue
        first = low.split()[0]
        if firsts[first] == 1 and not any(first in token or token in first for token in wanted):
            out.append(first)
    return out


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


def score_under(task: dict, reading: str | None, readings: dict, answer: str, ok: bool,
                sellers: list[str] | None = None, two_readings: list[str] | None = None) -> dict:
    """A run's verdict under the key for the reading it was answered under, or "unscored",
    with the reason, when its task file has no key for that reading (22 October 2026), the
    sidecar's `two_readings` holding "menu" to the questions that have two (`under_reading`)
    and the market's `sellers` judging a best (`score`). Every caller that judges a run goes
    through `score_run`, which passes all three from the task file."""
    try:
        keyed = under_reading(task, reading, readings, two_readings)
    except NoKeyForReading as fault:
        return {"verdict": "unscored", "why": f"no answer key for this run: {fault}",
                "prices": prices_in(answer or "")}
    return score(keyed, answer, ok, sellers)


@dataclasses.dataclass(frozen=True)
class Keys:
    """What a run's verdict depends on besides its task, the reading it answered under and
    its answer, read once from its task file (23 October 2026): the sidecar's other readings,
    the questions it names as having two, and the market's sellers. One value, so no caller
    can pass the readings and forget the rest (LESSONS 29: until then suite.py passed the
    two readings, verify_cells and claim.py did not, and only claim.py passed the sellers)."""
    readings: dict
    two_readings: list[str] | None
    sellers: list[str] | None


def keys_for(tasks_path: pathlib.Path) -> Keys:
    """The `Keys` of a task file: its sidecar's readings (`readings_for`) and two-readings
    list (`two_readings_for`), and the sellers of the fixture it names (`market_sellers`)."""
    spec = json.loads(tasks_path.read_text())
    return Keys(readings_for(tasks_path), two_readings_for(tasks_path), market_sellers(spec))


def score_run(task: dict, reading: str | None, keys: Keys, answer: str, ok: bool) -> dict:
    """The one scoring call (23 October 2026, LESSONS 29). suite.py live, verify_cells,
    rescore.py, compare_cells, replay_box and claim.py all judge a run through it, with the
    reading the run answered under and the `Keys` of its task file, so a stored verdict and
    every re-score of it apply the same rules."""
    return score_under(task, reading, keys.readings, answer, ok, keys.sellers, keys.two_readings)


def run_key(task: dict, reading: str | None, keys: Keys) -> dict:
    """The answer key `score_run` judges a run by, with the same arguments: the task's own, or
    its sidecar's for the reading the run answered under (`under_reading`). Raises
    NoKeyForReading where `score_run` gives "unscored". For a reader that shows the key and
    judges nothing, as claim.py's hand-reading sheet (23 October 2026)."""
    return under_reading(task, reading, keys.readings, keys.two_readings)["expect"]


def score(task: dict, answer: str, ok: bool, sellers: list[str] | None = None) -> dict:
    """Return verdict plus the evidence behind it, so results stay auditable. `sellers` are
    the market's (`market_sellers`), where the caller knows them: a best named among them is
    judged against all of them, and without them against the key's `not_any` alone."""
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
        # The price the answer gives as its answer decides, wherever else the key's price or
        # the trap appears (score v7): "The lowest is $16.62 at Lymington. Elmsworth charges
        # $19.17" answers 16.62, and "Oakfield's $6.93 card is for a smaller pack; the lowest
        # 2 x 9.5L that can be bought is $20.30" answers 20.30.
        stated = answer_price(answer)
        if stated is not None:
            if abs(stated - target) < 0.005:
                return {"verdict": "correct", "why": f"gave {target} as its answer", "prices": found}
            if trap is not None and abs(stated - trap) < 0.005:
                return {"verdict": "wrong", "why": f"gave the trap price {trap} as its answer",
                        "prices": found}
            return {"verdict": "wrong", "why": f"gave {stated} as its answer, expected {target}",
                    "prices": found}
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
        # Naming both, the answer is held to the one it says is the best (score v6), and since
        # v7 against every other seller of the market where the caller names them, so a best
        # the key never thought to exclude is a wrong answer too.
        excluded = list(dict.fromkeys(list(expect.get("not_any", []))
                                      + other_sellers(sellers, expect["any"])))
        if hit and named_best(answer, expect["any"], excluded) == "excluded":
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
        # 2 x 9.5L pack". Since v7 neither are a page's number nor a statement of the market's
        # size, "20 on page 1", "There are 21 tee listings, and", nor the digits of "the
        # 2-pack". If that leaves nothing, the first number is used after all, since "All 15
        # listings offer it" is a count of 15.
        bare = without_labels(PACK_LABEL.sub(lambda m: " " * len(m.group(0)), answer))
        bare = STOCK_CLAIM.sub(lambda m: " " * len(m.group(0)), bare)
        # A whole number, never a decimal's part. Until v8 a number followed by a full stop
        # was never read, so "... in stock right now is 11." gave no count at all.
        numbers = list(re.finditer(r"(?<![\d.$])(\d{1,3})(?!\d|\.\d)", bare))
        if not numbers:
            return {"verdict": "ambiguous", "why": "no number given", "prices": found}
        coverage = {m.start(1) for m in COVERAGE_NUMBER.finditer(bare)}
        coverage |= {m.start(group) for m in MARKET_SIZE.finditer(bare)
                     for group in range(1, 6) if m.group(group)}
        coverage |= {m.start(group) for m in ENUMERATOR.finditer(bare) for group in (1, 2) if m.group(group)}
        coverage |= {m.start(group) for m in NOT_THE_COUNT.finditer(bare)
                     for group in range(1, 6) if m.group(group)}
        spans = [m.span() for m in PAGE_NUMBERS.finditer(bare)]
        coverage |= {m.start(1) for m in numbers if any(a <= m.start(1) < b for a, b in spans)}
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
        return ranked(expect, answer, found, sellers)

    if kind == "label_check":
        return label_check(expect, answer, found)

    raise ValueError(f"unknown expect kind: {kind}")


def label_check(expect: dict, answer: str, found: list[float]) -> dict:
    """A claim in a size menu's label checked against the price shown once the size is chosen
    (score v10, 24 October 2026, the tee-only market's tee-promo-check): `price` is the real
    price, `trap` the label's figure, and `value` false, since the claim does not hold (a key
    with a true claim is not written, and not scored). Correct only when the answer gives the
    real price; quoting the label's figure beside it, as the label's claim, is allowed, and a
    figure inside a quoted label ("XS - Promo $9.99") is not a price at all (`VARIANT_LABEL`).
    Wrong when the answer opens with yes, affirming the claim, or gives the label's figure as
    the price without the real one; a no with no price has not answered, and is ambiguous."""
    if expect["value"]:
        raise ValueError("label_check scores a claim that does not hold; a true claim has no key")
    target, trap = expect["price"], expect["trap"]
    lead = LEADING_ANSWER.match(answer.lower())
    if lead and lead.group(1) == "yes":
        return {"verdict": "wrong", "why": "affirmed the label's claim", "prices": found}
    if any(abs(p - target) < 0.005 for p in found):
        return {"verdict": "correct", "why": f"gave the real price {target}", "prices": found}
    if any(abs(p - trap) < 0.005 for p in found):
        return {"verdict": "wrong", "why": f"gave the label's figure {trap} as the price", "prices": found}
    if not found:
        return {"verdict": "ambiguous", "why": "no price given", "prices": found}
    return {"verdict": "wrong", "why": f"gave {found[0]} as the price, expected {target}", "prices": found}


def mentions_of(low: str, items: list[dict]) -> list[tuple[int, int]]:
    """Where the ranked sellers are named: (position, item index), every occurrence."""
    found = []
    for index, item in enumerate(items):
        for token in item["any"]:
            found += [(m.start(), index) for m in re.finditer(re.escape(token.lower()), low)]
    return sorted(found)


# A seller an answer names as outside its ranking, "ahead of Kelsall", "then Kelsall", "beating
# Kelsall" (score v8).
OUTSIDE_THE_RANKING = re.compile(r"\b(?:ahead\s+of|before|beating|beats?|over|then|next|followed\s+by|after|"
                                 r"than|unlike|not|excluding|except|skipp\w*|ignor\w*)\s+(?:[\w$.]+\s+){0,2}$",
                                 re.IGNORECASE)


def ranked(expect: dict, answer: str, found: list[float], sellers: list[str] | None = None) -> dict:
    """The k sellers, each with its price. Written 14 October 2026 for the top-k and
    named-comparison questions of the box v2 batch. Until score v7 the sellers had to be named
    in the key's order, and the three right sellers out of order were wrong (verifier's audit,
    23 October 2026), where every top-k template asks "which three sellers are cheapest" and
    no order; a comparison's loser is optional, so it never had an order to keep.

    A seller's price is read from the text between its neighbouring seller mentions, so
    "Alderney $25.77, Elmsworth $28.96" and "$25.77 from Alderney, $28.96 from Elmsworth"
    both give each seller its own price. A seller named more than once is stood for by the
    mention beside its expected price, so an answer that narrates the listings it opened
    before ranking them is read by its ranking. A seller named without any price nearby is
    not scored wrong but leaves the answer ambiguous; one whose nearby price is another
    figure is wrong, which also catches a neighbour's price given in place of its own.

    An item marked optional need not be named, but when it is named with a price the price
    must be its own: the loser of a comparison quoted at its advertised price is a wrong
    answer, however the winner is reported.

    Since v8, where the caller names the market's `sellers`, a sentence that names the
    expected sellers and more sellers of the market than the key holds answers with more than
    were asked: "The cheapest are Elmsworth $19.17, Everleigh $21.54, Bexhill $21.71 and
    Kelsall $27.45" is four for three, and wrong (verifier's re-audit, 23 October 2026). A
    seller named as outside the ranking, "ahead of Kelsall", "then Kelsall", is not counted
    (`OUTSIDE_THE_RANKING`), nor one in a sentence that names none of the expected sellers.
    Without the sellers, an extra seller is not caught, and the verifier reads for it.
    """
    low = answer.lower()
    items = expect["items"]
    mentions = mentions_of(low, items)
    cuts = [position for position, _ in mentions]
    extra = other_sellers(sellers, [token for item in items for token in item["any"]])
    for sentence in SENTENCE_END.split(answer or ""):
        said = sentence.lower()
        named = {index for _, index in mentions_of(said, items)}
        listed = sorted({token for token in extra for m in re.finditer(re.escape(token), said)
                         if not OUTSIDE_THE_RANKING.search(said, 0, m.start())})
        if named and listed and len(named) + len(listed) > len(items):
            return {"verdict": "wrong", "why": f"named {len(named) + len(listed)} sellers where the key "
                                               f"holds {len(items)}, {', '.join(listed)} besides",
                    "prices": found}

    def nearby(position: int) -> list[float]:
        before = max([c for c in cuts if c < position], default=0)
        after = min([c for c in cuts if c > position], default=len(low))
        return prices_in(low[before:after])

    unpriced = []
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
    if unpriced:
        return {"verdict": "ambiguous", "why": f"no price given for {', '.join(unpriced)}",
                "prices": found}
    return {"verdict": "correct", "why": "named every seller with its price", "prices": found}
