#!/usr/bin/env python3
"""Generate an A+ market: tee and bottled water listings under one brand, so that the brand's
search runs to a second results page and mixes the two products (docs/content/claim2-protocol.md,
"The market (A+)").

The first claim market sold one product on one results page. This one asks whether the block
still holds at scale: about forty listings, so the search spans two pages at the shop's page
size of 36, and two products, so the listings a question is about have to be picked out of
the page rather than taken as the whole of it. Development uses its own brand and seeds 900
to 999. The claim market is drawn by this same code from seed 1000, under the brand the final
protocol names, and only after the protocol is final, which `--claim` guards.

**What is the same as the markets before it.**
- Each tee listing is `generate_apparel.build_listing`: its price model, its three availability
  states, its probabilities. The tees are held to its 13 rules, unchanged.
- Each water listing is priced by `generate_catalogue`'s model, a per-litre rate per seller and
  a factor per pack, and the water is held to its 8 rules.
- Rejection sampling against rules checked before the market is used, from a string seed so
  that consecutive seeds never share a stream (`generate_apparel.generate`).

**What is new, and why.**
- *Water has a third availability state.* The water generator had none: every pack it listed
  could be bought, and only the 2 x 9.5L could be missing. The protocol asks for each variant
  absent, sold out or buyable, so every pack here takes the tee generator's probabilities
  (`P_ABSENT`, `P_SOLD_OUT`). The water rules are read over what can be bought, which is what
  the questions ask about: the winner is the cheapest 2 x 9.5L that can be bought, the card is
  the cheapest pack that can be bought (what Magento prints, `generate_apparel.from_price`),
  and the best price per litre is over packs that can be bought.
- *The protocol's four rules* (`MARKET_RULES`), and the conditions every key needs to be a
  single answer.
- *Where the answers render.* The rules on the page (`PAGE_RULES`) are applied to the order
  `search_order.py` predicts, under every one of its scenarios, before the market is seeded.
  The live page is checked after seeding (`pick_aplus_market.py`) and is what counts.
- *Titles.* The shop ranks a brand's listings by how often the brand occurs in a listing's
  names against how long they are (`search_order.py`), and each pack label adds three words
  to a child's name where a size adds one. Under the titles the earlier markets used
  ("Heavyweight Cotton Tee", "Still Spring Water, Multipack"), at one seller-name length every
  water listing scores below every tee listing, at every option count and under either reading
  of the brand, and the earlier name lists give nine sellers in ten a two-word name, so the
  page would list nearly all the tees and then all the water, which the protocol rules out
  (`tests/test_aplus_market.py`). Found with the order model on 22 October 2026, before any
  A+ seed. So each listing is titled with one of three phrasings of its product, as sellers
  title the same product differently, the water's shorter than Rivenhall's, and seller names
  run from two words to four, as shops' names do. Which listings mix on the page is then
  left to the draw, and the page rules hold the draw to it.
- *Names.* The scorer matches a seller by its first word, as a lowercase substring of the
  answer, so every first word is distinct and is found in no other seller's name, the brand,
  a product phrasing, an option label or a question (`names_distinct`). That is the first
  protocol's brand rule (the "Kelsall" problem) applied to every word a scorer reads.
- *The claim is held apart* (version 2). Its titles come from phrasings development never
  drew, sharing only the head noun (`CLAIM_TEE_PHRASES`, `CLAIM_WATER_PHRASES`, the rule in
  `phrase_problems`). `--claim` refuses while the protocol says DRAFT, below seed 1000, and
  under development's prefix or over its fixture; draws only the seed its record allows next,
  so the claim market is the first seed from 1000 that passes (`claim_record_problem`); and
  prints a claim market only once it is written and recorded as accepted (`claim_gate`).
  Since version 3 its phrasings name one product, as development's do.
- *Rules by version* (version 3). A market is held to the rules of the version it was drawn
  under, and drawn again under the version its seed search accepted it under
  (`RULES_SINCE`, `drawn_under`), so development's market stays the one the shop holds.
  Without its search record (`--search-log env/manifests/aplus_dev-search.json`) a seed is
  drawn under this version's rules, and seed 900 is then not development's market.

**Design B, the tee-only market** (version 4, 24 October 2026, `--design B`; docs/content/
claim2-handover.md section 3 and the verifier's rules of that night). One product under one
brand, about 45 listings from distinct sellers so the search spans two pages; six sizes XS to
XXL by the tee generator's model (`build_tee_b`); misleading labels in the size menu, held as
data on the variant (`add_labels`): promo labels on XS whose figure is below the real price,
scarcity labels on a buyable M claiming a count the shop never shows. Size XS is a second
target, for the promo trap (tee-xs-price), and one listing is named by rule for tee-promo-check
(`promo_check_named`). The rules are `B_RULES`; the water is dropped; a listing description was
cut. Every design-A code path is unchanged, so Larchmere draws and checks as before. The labels
reach the shop as option values of the market's own attribute (`B_ATTRIBUTE`, the seeder), so
both themes render them in the menu, the plain theme with Magento's surcharge after the text,
and the index holds them in the children's names, which `search_order.py` counts.

    python3 env/generate_aplus.py --seed 900 --brand <Brand> --brand-forms 2 --report
    python3 env/generate_aplus.py --seed 900 --brand <Brand> --brand-forms 2 --sku-prefix IGR-DEV \\
        --out env/fixtures/aplus_dev.json
    python3 env/generate_aplus.py --seed 900 --brand <Brand> --brand-forms 2 --sku-prefix IGR-TDV \\
        --design B --out env/fixtures/<the design-B development fixture>
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import generate_apparel as apparel  # noqa: E402  (the tee model, its 13 rules, from_price, price_for)
import generate_catalogue as water  # noqa: E402  (the water price model: PACKS, RATE_RANGE, litres)
import search_order  # noqa: E402  (the predicted results order)

MARKET = "aplus"
# Bumped whenever a change would draw a different market from the same seed, or judge one
# differently. Recorded in every fixture's `_generated` and every attempt of a seed search.
#   1  22 October 2026, the first A+ market (Larchmere, seed 900)
#   2  22 October 2026, from the verifier's check of version 1 (task E): an 8 per cent margin
#      for the best price per litre (`per_litre_margin`, replacing `per_litre_unique`); a
#      sold-out trap on every water price question (`water_sold_out_trap`,
#      `per_litre_sold_out_trap`); page 2 rules a market can meet (`counts_need_page_2`); the
#      headline answered alike from page 1 and from both pages (`headline_on_page_1`); the
#      page rules and the recorded order for the brand's own analyzer form (`--brand-forms`);
#      the claim market's titles drawn from phrasings development never used; the claim's
#      seed guards. Rules about one product are checked on its own draw, before pairing
#   3  23 October 2026, from the verifier's fairness audit, before any claim draw. The claim's
#      tee titles read as one product, as development's all say "Heavyweight Cotton": version
#      2's "Classic Organic Tee" and "Relaxed Fit Basic Tee" named two materials and two fits,
#      so "the {brand} tee" had a second reading. The claim's water loses "Alpine", a source
#      the others do not claim. Every pool shares one core, its shortest phrasing's words
#      (`phrase_problems`). And a margin through the top three (`top_3_margin`): version 2
#      let the second and third cheapest buyable size M tie. A market is held to the rules of
#      the version it was drawn under (`RULES_SINCE`, `drawn_under`): development's, drawn
#      under version 2, is kept as drawn, and fails the margin by its second and third,
#      $21.54 and $21.71, 0.8 per cent apart; it is development's, and no claim rests on it
#   4  24 October 2026, design B (`--design B`, the student's decision of that night, docs/
#      content/claim2-handover.md section 3): one product, a tee, about 45 listings over two
#      pages; six sizes XS to XXL; promo and scarcity labels in the size menu as data on the
#      variant, never holding a real price; size XS the second target, with its rules and the
#      promo trap's (`B_RULES`); the water dropped. A design-A market draws and checks exactly
#      as under version 3: every design-A code path is unchanged, and `drawn_under` still
#      draws Larchmere under version 2. The order model counts a label's words in a child's
#      name (`search_order.menu_label`), which changes no market without labels
VERSION = 4
# The rules a market drawn under an earlier version was not held to, by the version that
# brought each in. A market is judged by the rules of the version it was drawn under, its
# fixture's `_generated.version`, and redrawn under that version (`drawn_under`).
RULES_SINCE = {"top_3_margin": 3}

TEE, WATER = "tee", "water"
TEE_TARGET = apparel.TARGET_SIZE          # "M"
WATER_TARGET = water.TARGET_OPTION        # "2 x 9.5L"
TEE_OPTIONS = list(apparel.SIZES)
WATER_OPTIONS = [p["option"] for p in water.PACKS]

# The shop's results page size, read off the local shop on 22 October 2026 ("Items 1 - 36 of
# 16678" for q=water, a next link to p=2). No setting is changed to get it.
PAGE_SIZE = 36
# The first screen, as the first protocol's page rule took it: the first row of four cards
# (`pick_apparel_market.FIRST_ROW`, checked equal by the tests).
FIRST_SCREEN = 4
# "About 20" of each (the protocol). 21 and 21 make 42, so page 2 holds six listings.
TEE_LISTINGS = 21
WATER_LISTINGS = 21

# How each seller titles its listing, drawn per listing, as sellers on a marketplace title the
# same product differently. The rule every phrasing keeps: its head noun, the last word before
# any comma, is its product's (`HEAD_NOUNS`), because that is the word the box scopes a
# question to a product by (`box.head_noun`); and it holds no word of the other product.
# Development's phrasings: the first tee phrasing is Thornwood's and Ashcombe's, and every
# water phrasing is shorter than Rivenhall's "Still Spring Water, Multipack" (see the module
# docstring for why).
DEV_TEE_PHRASES = ("Heavyweight Cotton Tee", "Heavyweight Cotton Tee, Unisex",
                   "Heavyweight Cotton Crew Neck Tee")
DEV_WATER_PHRASES = ("Spring Water", "Still Spring Water", "Natural Spring Water, Still")
# The claim market's, held out (task E, 22 October 2026): phrasings development never drew,
# sharing no word with development's but the head noun, so nothing built on the development
# market's titles carries over to the claim's. The same number of words, phrasing by
# phrasing, as development's (3, 4, 5 for the tee, 2, 3, 4 for the water), since a title's
# length moves where it renders. Since version 3 (23 October 2026) they read as one product,
# as development's do: one core, a midweight jersey tee and a mineral water, with words that
# every such listing could carry (a knit, a short sleeve; bottled, pure), where version 2's
# set "Classic Organic" against "Relaxed Fit Basic", two materials and two fits, and an
# "Alpine" water against two that claim no source.
CLAIM_TEE_PHRASES = ("Midweight Jersey Tee", "Midweight Jersey Knit Tee",
                     "Midweight Jersey Tee, Short Sleeve")
CLAIM_WATER_PHRASES = ("Mineral Water", "Mineral Water, Bottled", "Pure Mineral Water, Bottled")
HEAD_NOUNS = {TEE: "Tee", WATER: "Water"}
ALL_PHRASES = DEV_TEE_PHRASES + DEV_WATER_PHRASES + CLAIM_TEE_PHRASES + CLAIM_WATER_PHRASES


def phrasings(claim: bool) -> dict[str, tuple[str, ...]]:
    """The titles a market draws from: the claim's held-out pool, or development's."""
    if claim:
        return {TEE: CLAIM_TEE_PHRASES, WATER: CLAIM_WATER_PHRASES}
    return {TEE: DEV_TEE_PHRASES, WATER: DEV_WATER_PHRASES}


def head_noun(phrase: str) -> str:
    """A phrasing's head noun, read as the box reads a title's: the last word before any
    comma."""
    return phrase.split(",", 1)[0].split()[-1]


def phrase_words(phrases: tuple[str, ...]) -> set[str]:
    return {w.lower() for phrase in phrases for w in phrase.replace(",", " ").split()}


def phrase_problems() -> list[str]:
    """What is wrong with the phrasing pools, one line each: a head noun not its product's,
    a word of the other product in a phrasing, a claim phrasing sharing a word other than
    the head noun with development's, a claim pool whose word counts are not development's,
    or a pool whose phrasings do not share one core (version 3): every phrasing of a pool
    holds each word of its shortest, as each of development's holds "Heavyweight Cotton
    Tee" and "Spring Water", so the pool names one product. Whether the words beyond the
    core are ones every such listing could carry is read by hand (the module's version
    notes). Empty when nothing is."""
    problems = []
    nouns = {noun.lower() for noun in HEAD_NOUNS.values()}
    for product, dev, claim in ((TEE, DEV_TEE_PHRASES, CLAIM_TEE_PHRASES),
                                (WATER, DEV_WATER_PHRASES, CLAIM_WATER_PHRASES)):
        other = HEAD_NOUNS[WATER if product == TEE else TEE].lower()
        for phrase in dev + claim:
            if head_noun(phrase) != HEAD_NOUNS[product]:
                problems.append(f"{phrase!r}: its head noun is not {HEAD_NOUNS[product]!r}")
            if other in phrase_words((phrase,)):
                problems.append(f"{phrase!r}: it holds the other product's noun")
        shared = phrase_words(claim) & phrase_words(DEV_TEE_PHRASES + DEV_WATER_PHRASES) - nouns
        if shared:
            problems.append(f"{product}: the claim phrasings share {sorted(shared)} with development's")
        if sorted(len(p.split()) for p in dev) != sorted(len(p.split()) for p in claim):
            problems.append(f"{product}: the claim phrasings' word counts are not development's")
        for name, pool in (("development", dev), ("claim", claim)):
            core = phrase_words((min(pool, key=lambda p: len(p.split())),))
            apart = [phrase for phrase in pool if not core <= phrase_words((phrase,))]
            if apart:
                problems.append(f"{product}: the {name} phrasings share no one core: {apart} lack "
                                f"{sorted(core)}")
    return problems

# The availability model, the tee generator's, for both products.
P_ABSENT = apparel.P_SIZE_MISSING
P_SOLD_OUT = apparel.P_SIZE_SOLD_OUT

# Seller names. The first words of the two earlier name lists, less "Cellar", which is inside
# "Cellars", and more of the same kind so that each product has enough. A first word belongs
# to one product, so no seller sells both. Second parts run from one word to three, four of
# each, so a whole seller name runs from two words to four.
TEE_FIRST = apparel.NAME_FIRST + ("Abbotsley", "Bexhill", "Carnforth", "Dovercourt",
                                  "Everleigh", "Foxcombe", "Gisburn", "Thirsk")
WATER_FIRST = tuple(n for n in water.NAME_FIRST if n != "Cellar") + (
    "Ambleside", "Brockwell", "Crowhurst", "Dalston", "Elstead", "Fordwich", "Grantley",
    "Holbeck", "Ingleton")
TEE_SECOND = ("Outfitters", "Apparel", "Threads", "Garments",
              "Clothing Co", "Garment Works", "Textile Company", "Uniform Supply",
              "Apparel Official Store", "Workwear Supply Co", "Clothing Company Ltd",
              "Textiles Official Store")
WATER_SECOND = ("Direct", "Provisions", "Wholesale", "Merchants",
                "Supply Co", "Trading Company", "Beverage Supply", "Pantry Stores",
                "Drinks Official Store", "Beverage Supply Co", "Grocery Company Ltd",
                "Provisions Official Store")

# The questions, the protocol's templates word for word (docs/content/claim2-protocol.md,
# "Questions"). The market's rules are written per question, so they live with the market,
# and `generate_aplus_tasks.py` writes them into a task file with their keys.
TEMPLATES = {
    "tee-headline": (TEE, "Of the {brand} tee listings shown, which one advertises the lowest "
                          "price on the results page, and what is that price?"),
    "tee-target-price": (TEE, "What is the lowest price anyone charges for size M of the {brand} "
                              "tee, among those that can actually be bought?"),
    "tee-cheapest-target": (TEE, "Across the {brand} tee listings, which seller is cheapest for "
                                 "size M, and what is that price? Only count a listing that can "
                                 "actually supply that size."),
    "tee-all-stocked": (TEE, "Does every {brand} tee listing offer size M? Answer yes or no."),
    "tee-count-stocked": (TEE, "How many of the {brand} tee listings offer size M?"),
    "tee-count-buyable": (TEE, "How many of the {brand} tee listings have size M in stock and "
                               "available to buy right now?"),
    "tee-exists-under": (TEE, "Is there any {brand} tee listing with size M available to buy "
                              "for under ${limit}? Answer yes or no, and name the seller if yes."),
    "tee-top-3": (TEE, "Which three sellers are cheapest for size M of the {brand} tee among "
                       "listings that can actually supply it, and at what prices?"),
    "water-target-price": (WATER, "What is the lowest price anyone charges for the 2 x 9.5L pack "
                                  "of {brand} water, among those that can actually be bought?"),
    "water-cheapest-target": (WATER, "Across the {brand} water listings, which seller is cheapest "
                                     "for the 2 x 9.5L pack, and what is that price? Only count a "
                                     "listing that can actually supply that pack."),
    "water-all-stocked": (WATER, "Does every {brand} water listing stock the 2 x 9.5L pack? "
                                 "Answer yes or no."),
    "water-count-buyable": (WATER, "How many of the {brand} water listings have the 2 x 9.5L pack "
                                   "in stock and available to buy right now?"),
    "water-best-per-litre": (WATER, "Across all the {brand} water listings and all their pack "
                                    "sizes, which seller offers the lowest price per litre among "
                                    "packs that can actually be bought?"),
    "decline-delivery": (TEE, "Which {brand} seller delivers fastest for size M of the tee?"),
    "decline-taste": (WATER, "Which {brand} water tastes best?"),
}
# The questions whose key names a price, and so the ones the first-screen rule is about. The
# counting and "every listing" questions have no price for a card to undercut.
PRICE_QUESTIONS = ("tee-target-price", "tee-cheapest-target", "tee-exists-under", "tee-top-3",
                   "water-target-price", "water-cheapest-target", "water-best-per-litre")
TOP_K = 3

MARKET_RULES = """The A+ market's rules, on top of the tee generator's 13 and the water generator's 8.

The protocol's four (docs/content/claim2-protocol.md, "Acceptance rules"):

1. first_screen_misleads  for each question whose key names a price, every listing the key
                          names renders outside the first screen, and a listing of the same
                          product on the first screen advertises less than the answer costs,
                          so an answer read off the first screen's cards is wrong. What the
                          answer costs: the winner's price for target-price and
                          cheapest-target, the limit for exists-under, the dearest of the
                          three for top-3 (and the undercutting card is not one of them), the
                          winning pack's price for best-per-litre. A page rule
2. answer_on_page_2       a listing one of those keys names is on page 2, so a bound computed
                          over page 1 alone stops too early. A page rule
   counts_need_page_2     and every count question, under each of its readings, counts at
                          least one listing on page 2, so a count over page 1 alone is short.
                          (Version 2. "Every 'every listing' question needs both pages" was
                          proposed too and cannot be met at 21 and 21 listings. Both answer
                          no, and a no needs page 2 only when every listing without the
                          variant renders there: at least four tees without size M in the
                          menu (the tee rule some_missing_target) and a water without the
                          2 x 9.5L (the water rule of that name), beside a tee that can sell
                          size M and a water that can sell the 2 x 9.5L, which the counts put
                          on page 2. That is seven listings, nine read as what can be bought,
                          and page 2 holds six. The protocol's wording says so.) A page
                          rule
3. readings_differ        size M is listed but sold out on at least one tee listing, and the
                          2 x 9.5L on at least one water listing, so the menu and the buyable
                          readings of "offer" and "stock" count different listings
4. per_litre_not_target   the best price per litre among packs that can be bought is not at the
                          cheapest 2 x 9.5L that can be bought

So that "can actually be bought" decides every water price question (version 2), as the tee
rule `sold_out_trap` does for the tee's:

5. water_sold_out_trap    a 2 x 9.5L is listed but sold out at a price below the winner's
6. per_litre_sold_out_trap a pack listed but sold out is cheaper per litre than the best
                          that can be bought

The market's shape (the protocol's "The market (A+)"):

7. two_pages              more than one page of listings and no more than two
8. interleaved            both products on the first screen and both on page 2, so neither
                          product is one block and every question about either product needs
                          both pages. A page rule
9. names_distinct         every seller's first word is distinct, and is inside no other
                          seller's name, the brand, a product phrasing, an option label or a
                          question template; and no seller name holds a word of a product
                          phrasing

What every key needs to be one answer, refused rather than guessed:

10. headline_unique       one tee listing advertises the lowest tee price
11. headline_on_page_1    that listing renders on page 1, and every tee card on page 2 is at
                          least 8 per cent dearer, so "on the results page" read as page 1 or
                          as every page names the same listing at the same price (version 2).
                          A page rule
12. limit_separates       the exists-under limit (`exists_limit`) leaves exactly one listing
                          that can sell size M under it, and no buyable size M sits on it
13. top_3_unique          the fourth cheapest buyable size M costs more than the third
14. per_litre_margin      one listing has the lowest price per litre, at least 8 per cent below
                          the next listing's, as `clear_margin` holds the price winners
                          (version 2, replacing per_litre_unique)
15. top_3_margin          the third cheapest buyable size M is at least 8 per cent above the
                          second, and the fourth at least 8 per cent above the third, as
                          `clear_margin` holds the second above the first, so neither who is in
                          the three nor what each charges is rounding luck (version 3; markets
                          drawn under an earlier version were not held to it)

A page rule is applied to the order `search_order.py` predicts for the brand's analyzer form,
under each of its scenarios, when the market is drawn, and to the live results pages after
it is seeded. The rules about one product are checked on that product's draw before the two
are paired, so the water draws paired with each tee draw are the first `WATER_PER_TEE` that
pass every rule about water (version 2)."""

PAGE_RULES = ("interleaved", "first_screen_misleads", "answer_on_page_2", "counts_need_page_2",
              "headline_on_page_1")


def money(value: float) -> float:
    return round(value + 1e-9, 2)


# ---------------------------------------------------------------------------
# Drawing listings


def seller_names(firsts: tuple[str, ...], seconds: tuple[str, ...], count: int,
                 rng: random.Random) -> list[str]:
    if count > len(firsts):
        raise SystemExit(f"only {len(firsts)} distinct seller first words available")
    pool = list(firsts)
    rng.shuffle(pool)
    return [f"{first} {rng.choice(seconds)}" for first in pool[:count]]


def build_tee(seller: str, index: int, rng: random.Random, brand: str,
              phrases: tuple[str, ...] = DEV_TEE_PHRASES) -> dict:
    """One tee listing, exactly as the tee generator draws it. Until the market's catalogue
    order is drawn (`catalogue`) it carries a provisional SKU, TEE-NN, distinct within the
    draw, because the tee rules tell listings apart by SKU."""
    listing = apparel.build_listing(seller, index, rng, brand, sku_prefix="TEE")
    # The title is drawn after everything the tee generator draws, so its draws are its own,
    # and either pool of phrasings leaves the prices and stock of a seed as they are.
    listing["name"] = f"{brand} {rng.choice(phrases)} - {seller}"
    listing["product"] = TEE
    return listing


def build_water(seller: str, index: int, rng: random.Random, brand: str,
                phrases: tuple[str, ...] = DEV_WATER_PHRASES) -> dict:
    """One water listing: the water generator's prices, the tee generator's availability. A
    provisional SKU, WATER-NN, until the catalogue order is drawn."""
    rate = rng.uniform(*water.RATE_RANGE)
    offered = [p for p in water.PACKS if rng.random() > P_ABSENT]
    if len(offered) < 2:                      # as the tee generator: one pack is not a market
        offered = list(water.PACKS[:2])
    variants = []
    for pack in offered:
        sold_out = rng.random() < P_SOLD_OUT
        variants.append({
            "option": pack["option"],
            "price": money(rate * water.litres(pack) * rng.uniform(*water.PACK_FACTOR_RANGE)),
            "qty": 0 if sold_out else rng.randint(25, 240),
            "units": pack["units"],
            "volume_ml": pack["volume_ml"],
        })
    if all(v["qty"] == 0 for v in variants):  # a shop with nothing to sell is not a market
        variants[0]["qty"] = rng.randint(25, 240)
    return {
        "key": f"water-{index:02d}", "parent_sku": f"WATER-{index:02d}",
        "name": f"{brand} {rng.choice(phrases)} - {seller}",
        "seller": seller,
        "attribute": "pack_size",
        "category_ids": [water.GROCERY_CATEGORY_ID],
        "gating": "price-and-stock-by-variant",
        "note": [],
        "variants": variants,
        "product": WATER,
    }


def catalogue(tees: list[dict], waters: list[dict], rng: random.Random,
              sku_prefix: str) -> list[dict]:
    """Both products in one catalogue, in an order drawn from the seed, numbered in that order.
    Interleaved so that a listing's number does not say which product it is."""
    slots = [TEE] * len(tees) + [WATER] * len(waters)
    rng.shuffle(slots)
    queues = {TEE: iter(tees), WATER: iter(waters)}
    families = []
    for index, product in enumerate(slots, 1):
        listing = next(queues[product])
        listing.update(key=f"{MARKET}-{index:02d}", parent_sku=f"{sku_prefix}-{index:02d}",
                       note=[f"Generated listing {index:02d}, {product}, seller "
                             f"{listing['seller']}."])
        families.append(listing)
    return families


# ---------------------------------------------------------------------------
# What a listing offers


def litres(variant: dict) -> float:
    return variant["units"] * variant["volume_ml"] / 1000


def best_rate(listing: dict) -> tuple[float, dict] | None:
    """The lowest price per litre among the packs this listing can sell now, and that pack."""
    able = [v for v in listing["variants"] if v["qty"] > 0]
    if not able:
        return None
    best = min(able, key=lambda v: v["price"] / litres(v))
    return round(best["price"] / litres(best), 4), best


def products(families: list[dict]) -> dict[str, list[dict]]:
    return {product: [f for f in families if f["product"] == product] for product in (TEE, WATER)}


def buyable(listings: list[dict], option: str) -> list[dict]:
    """The listings that can sell the option now, cheapest for it first."""
    able = [l for l in listings if apparel.buyable_price_for(l, option) is not None]
    return sorted(able, key=lambda l: apparel.buyable_price_for(l, option))


def exists_limit(tees: list[dict]) -> int | None:
    """The exists-under question's limit, by a rule written on 22 October 2026 before any A+
    market existed: the whole-dollar part of the midpoint between the two cheapest prices any
    tee listing can sell size M for. So exactly one listing, the cheapest, can sell it under
    the limit (`limit_separates` refuses a market where that fails), and the answer is a yes
    that names it. `first_screen_misleads` then puts that listing outside the first screen
    and a card under the limit on it, so the yes is not visible from the first screen. The
    same rule as `generate_apparel_v2_tasks.price_limits` for the claim market's yes limit."""
    able = buyable(tees, TEE_TARGET)
    if len(able) < 2:
        return None
    cents = [round(apparel.buyable_price_for(l, TEE_TARGET) * 100) for l in able[:2]]
    return sum(cents) // 200


# ---------------------------------------------------------------------------
# The water's facts and rules, over what can be bought


def water_measure(listings: list[dict]) -> dict:
    """The water's ground truth, as `generate_catalogue.measure` records it, read over what can
    be bought, with the three availability populations `generate_apparel.measure` records."""
    target = WATER_TARGET
    carriers = [l for l in listings if apparel.price_for(l, target) is not None]
    able = buyable(listings, target)
    sold_out = [l for l in carriers if apparel.buyable_price_for(l, target) is None]
    absent = [l for l in listings if apparel.price_for(l, target) is None]
    facts = {"target_option": target, "listings": len(listings),
             "listings_with_target": len(carriers), "listings_without_target": len(absent),
             "listings_target_buyable": len(able), "listings_target_sold_out": len(sold_out)}
    if not able:
        return {**facts, "winner": None}
    winner, best = able[0], apparel.buyable_price_for(able[0], target)
    runners = [apparel.buyable_price_for(l, target) for l in able]
    card = min(listings, key=apparel.from_price)
    must_open = [l for l in listings if apparel.from_price(l) <= best]
    rates = {l["parent_sku"]: best_rate(l) for l in listings}
    unit = min((l for l in listings if rates[l["parent_sku"]]), key=lambda l: rates[l["parent_sku"]][0])
    unit_rate, unit_pack = rates[unit["parent_sku"]]
    listed = min(carriers, key=lambda l: apparel.price_for(l, target))
    cheapest_sold_out = min(sold_out, key=lambda l: apparel.price_for(l, target)) if sold_out else None
    cheapest_absent = min(absent, key=apparel.from_price) if absent else None
    return {
        **facts,
        "winner": {"sku": winner["parent_sku"], "seller": winner["seller"], "price": best},
        "runner_up_price": runners[1] if len(runners) > 1 else None,
        "winning_margin": money(runners[1] - best) if len(runners) > 1 else None,
        "cheapest_listed": {"sku": listed["parent_sku"], "seller": listed["seller"],
                            "price": apparel.price_for(listed, target)},
        "cheapest_sold_out": None if cheapest_sold_out is None else {
            "sku": cheapest_sold_out["parent_sku"], "seller": cheapest_sold_out["seller"],
            "price": apparel.price_for(cheapest_sold_out, target)},
        "cheapest_card": {"sku": card["parent_sku"], "seller": card["seller"],
                          "from_price": apparel.from_price(card)},
        "card_probe_wrong": card["parent_sku"] != winner["parent_sku"],
        "cheapest_without_target": None if cheapest_absent is None else {
            "sku": cheapest_absent["parent_sku"], "seller": cheapest_absent["seller"],
            "from_price": apparel.from_price(cheapest_absent)},
        "best_per_litre": {"sku": unit["parent_sku"], "seller": unit["seller"],
                           "option": unit_pack["option"], "price": unit_pack["price"],
                           "price_per_litre": unit_rate},
        "unit_probe_wrong": unit["parent_sku"] != card["parent_sku"],
        "oracle_min_opens": len(must_open),
        "prunable_by_bound": len(listings) - len(must_open),
        "exhaustive_opens": len(listings),
        "bound_strength": round((len(listings) - len(must_open)) / len(listings), 3),
        "from_price_range": [money(min(apparel.from_price(l) for l in listings)),
                             money(max(apparel.from_price(l) for l in listings))],
        "target_price_range": [money(min(runners)), money(max(runners))],
    }


def water_check(listings: list[dict], facts: dict) -> list[str]:
    """`generate_catalogue.check`'s eight rules, each in its own words, read over what can be
    bought. Empty means usable."""
    if facts["winner"] is None:
        return ["unique_winner"]
    broken = []
    best = facts["winner"]["price"]
    prices = [apparel.buyable_price_for(l, WATER_TARGET) for l in buyable(listings, WATER_TARGET)]
    if prices.count(best) != 1:
        broken.append("unique_winner")
    if not facts["card_probe_wrong"]:
        broken.append("card_probe_wrong")
    if facts["prunable_by_bound"] < 3:
        broken.append("bound_is_useful")
    if facts["oracle_min_opens"] < 3:
        broken.append("bound_not_sufficient")
    if facts["listings_with_target"] == len(listings):
        broken.append("some_missing_target")
    if not facts["unit_probe_wrong"]:
        broken.append("unit_probe_wrong")
    if len({facts["winner"]["sku"], facts["cheapest_card"]["sku"],
            facts["best_per_litre"]["sku"]}) != 3:
        broken.append("three_answers")
    runner_up = facts["runner_up_price"]
    if runner_up is None or runner_up - best < best * water.MIN_MARGIN_REL:
        broken.append("clear_margin")
    return broken


# ---------------------------------------------------------------------------
# The keys, from the variants


def tee_keys(tees: list[dict]) -> dict:
    """The tee questions' keys, from the tee listings alone: the part of `keys` both designs
    share (version 4 factored it out of `keys`, which gives the same values as before)."""
    able = buyable(tees, TEE_TARGET)
    sold_out = [l for l in tees if apparel.price_for(l, TEE_TARGET) is not None
                and apparel.buyable_price_for(l, TEE_TARGET) is None]
    absent = [l for l in tees if apparel.price_for(l, TEE_TARGET) is None]
    limit = exists_limit(tees)
    witnesses = [l for l in able if limit is not None
                 and apparel.buyable_price_for(l, TEE_TARGET) < limit]
    price = lambda l, option: apparel.buyable_price_for(l, option)  # noqa: E731
    return {
        "tee_cards": sorted(tees, key=apparel.from_price),
        "tee_winner": able[0] if able else None,
        "tee_runner_up": able[1] if len(able) > 1 else None,
        # The two sellers a price-only reader names for the cheapest M, as the tee generator's
        # cheapest-target note gives them: the cheapest card without M, the cheapest M sold out.
        "tee_absent_trap": min(absent, key=apparel.from_price) if absent else None,
        "tee_sold_out_trap": (min(sold_out, key=lambda l: apparel.price_for(l, TEE_TARGET))
                              if sold_out else None),
        "tee_listed": len(tees) - len(absent),
        "tee_buyable": len(able),
        "tee_sold_out": len(sold_out),
        "limit": limit,
        "witnesses": witnesses,
        "limit_on_a_price": any(price(l, TEE_TARGET) == limit for l in able),
        "looks_like_yes": sorted((l for l in tees if limit is not None
                                  and apparel.from_price(l) < limit and l not in witnesses),
                                 key=apparel.from_price),
        "top": able[:TOP_K],
        "top_next": able[TOP_K] if len(able) > TOP_K else None,
    }


def keys(families: list[dict], design: str = "A") -> dict:
    """What each question's answer is, from the variants alone, with the listings it names.
    The task generator writes these and the page rules read where they render. A value of
    None means the market cannot give that key one answer, which `market_check` refuses.
    `design` B (version 4) is the tee-only market's, `keys_b`."""
    if design == DESIGN_B:
        return keys_b(families)
    tees, waters = products(families)[TEE], products(families)[WATER]
    water_able = buyable(waters, WATER_TARGET)
    water_sold_out = [l for l in waters if apparel.price_for(l, WATER_TARGET) is not None
                      and apparel.buyable_price_for(l, WATER_TARGET) is None]
    water_absent = [l for l in waters if apparel.price_for(l, WATER_TARGET) is None]
    rated = [(best_rate(l), l) for l in waters if best_rate(l)]
    rated.sort(key=lambda pair: pair[0][0])
    # Every pack listed but sold out, by its price per litre: the per-litre question's trap.
    sold_rates = sorted(((round(v["price"] / litres(v), 4), l, v) for l in waters
                         for v in l["variants"] if v["qty"] == 0), key=lambda t: t[0])
    return {
        **tee_keys(tees),
        "water_winner": water_able[0] if water_able else None,
        "water_absent_trap": min(water_absent, key=apparel.from_price) if water_absent else None,
        "water_sold_out_trap": (min(water_sold_out, key=lambda l: apparel.price_for(l, WATER_TARGET))
                                if water_sold_out else None),
        "water_card": min(waters, key=apparel.from_price) if waters else None,
        "water_listed": len(waters) - len(water_absent),
        "water_buyable": len(water_able),
        "water_sold_out": len(water_sold_out),
        "per_litre": rated[0][1] if rated else None,
        "per_litre_rate": rated[0][0][0] if rated else None,
        "per_litre_pack": rated[0][0][1] if rated else None,
        "per_litre_runner_up_rate": rated[1][0][0] if len(rated) > 1 else None,
        "per_litre_runner_up": rated[1][1] if len(rated) > 1 else None,
        "sold_out_rate": sold_rates[0][0] if sold_rates else None,
        "sold_out_rate_listing": sold_rates[0][1] if sold_rates else None,
    }


def tee_answer_listings(k: dict) -> dict[str, tuple[list[dict], float]]:
    """`answer_listings` for the tee questions both designs ask."""
    tee, top = k["tee_winner"], k["top"]
    named = {}
    if tee is not None:
        cost = apparel.buyable_price_for(tee, TEE_TARGET)
        named["tee-target-price"] = named["tee-cheapest-target"] = ([tee], cost)
    if k["witnesses"]:
        named["tee-exists-under"] = (k["witnesses"], k["limit"])
    if len(top) == TOP_K:
        named["tee-top-3"] = (top, apparel.buyable_price_for(top[-1], TEE_TARGET))
    return named


def answer_listings(k: dict, design: str = "A") -> dict[str, tuple[list[dict], float]]:
    """For each price question: the listings its key names, and what the answer costs. A
    question whose key the market cannot give is left out, and `market_check` refuses it."""
    if design == DESIGN_B:
        return answer_listings_b(k)
    water_ = k["water_winner"]
    named = tee_answer_listings(k)
    if water_ is not None:
        cost = apparel.buyable_price_for(water_, WATER_TARGET)
        named["water-target-price"] = named["water-cheapest-target"] = ([water_], cost)
    if k["per_litre"] is not None:
        named["water-best-per-litre"] = ([k["per_litre"]], k["per_litre_pack"]["price"])
    return {question: named[question] for question in PRICE_QUESTIONS if question in named}


# ---------------------------------------------------------------------------
# The market's rules


def words_a_scorer_reads(brand: str) -> list[str]:
    """Every text a seller's first word must not be found in, lowercased: the brand, every
    phrasing of both products in both pools, every option label and every question."""
    texts = [brand, *ALL_PHRASES, *TEE_OPTIONS, *WATER_OPTIONS]
    texts += [text.format(brand=brand, limit="") for _, text in TEMPLATES.values()]
    return [t.lower() for t in texts]


def product_words() -> set[str]:
    """The words of every phrasing in both pools, which no seller name may hold, so that the
    product a listing sells is read from its title alone."""
    return phrase_words(ALL_PHRASES)


def name_problems(families: list[dict], brand: str, design: str = "A") -> list[str]:
    """What `names_distinct` finds wrong, one line each. Design B reads its own texts, the
    label texts and its templates among them (`words_a_scorer_reads_b`)."""
    problems = []
    firsts = [f["seller"].split()[0].lower() for f in families]
    if len(set(firsts)) != len(firsts):
        problems.append("a seller first word is used twice")
    texts = words_a_scorer_reads_b(brand, families) if design == DESIGN_B else words_a_scorer_reads(brand)
    product_words_ = product_words()
    for family, first in zip(families, firsts):
        others = [g["seller"].lower() for g in families if g is not family]
        if any(first in other for other in others):
            problems.append(f"{family['seller']}: its first word is inside another seller's name")
        if any(first in text for text in texts):
            problems.append(f"{family['seller']}: its first word is inside a text the scorer reads")
        if brand.lower() in family["seller"].lower().split():
            problems.append(f"{family['seller']}: the brand is a word of it")
        if product_words_ & set(family["seller"].lower().split()):
            problems.append(f"{family['seller']}: it holds a product's own word")
    return problems


def held_to(rule: str, version: int | None) -> bool:
    """Whether a market drawn under `version` is held to `rule`. None asks for the rules every
    version holds, for a caller that cannot say which version its market was drawn under;
    generate_aplus_tasks.py passes its fixture's `_generated.version` (since 23 October 2026)."""
    return rule not in RULES_SINCE or (version is not None and version >= RULES_SINCE[rule])


def top_3_separated(k: dict) -> bool:
    """`top_3_margin`: the second, third and fourth cheapest buyable size M each at least
    `apparel.MIN_MARGIN_REL` above the one before, where the second above the first is
    `clear_margin`'s, the tee generator's."""
    if k["top_next"] is None or len(k["top"]) < TOP_K:
        return False
    prices = [apparel.buyable_price_for(l, TEE_TARGET) for l in k["top"] + [k["top_next"]]]
    return all(b - a >= a * apparel.MIN_MARGIN_REL for a, b in zip(prices[1:], prices[2:]))


def tee_market_rules(k: dict, version: int | None = VERSION) -> list[str]:
    """The rules of `MARKET_RULES` about the tees alone, from `keys` of a draw that need hold
    nothing but tees, so the generator can check them before pairing, as a market drawn
    under `version` is held to them (`held_to`)."""
    broken = []
    if not k["tee_sold_out"]:
        broken.append("readings_differ")
    cards = [apparel.from_price(l) for l in k["tee_cards"]]
    if len(cards) < 2 or cards[0] == cards[1]:
        broken.append("headline_unique")
    if k["limit"] is None or len(k["witnesses"]) != 1 or k["limit_on_a_price"]:
        broken.append("limit_separates")
    if k["top_next"] is None or apparel.buyable_price_for(k["top_next"], TEE_TARGET) == \
            apparel.buyable_price_for(k["top"][-1], TEE_TARGET):
        broken.append("top_3_unique")
    if held_to("top_3_margin", version) and not top_3_separated(k):
        broken.append("top_3_margin")
    return broken


def water_market_rules(k: dict) -> list[str]:
    """The rules of `MARKET_RULES` about the water alone, as `tee_market_rules`."""
    broken = []
    if not k["water_sold_out"]:
        broken.append("readings_differ")
    winner, unit = k["water_winner"], k["per_litre"]
    if unit is None or winner is None or unit["parent_sku"] == winner["parent_sku"]:
        broken.append("per_litre_not_target")
    # As `clear_margin` holds the price winners (8 per cent, `generate_catalogue.MIN_MARGIN_REL`):
    # Larchmere's first market had its best per litre 0.31 per cent ahead of the next seller.
    rate, runner_up = k["per_litre_rate"], k["per_litre_runner_up_rate"]
    if rate is None or runner_up is None or runner_up - rate < rate * water.MIN_MARGIN_REL:
        broken.append("per_litre_margin")
    # As the tee rule `sold_out_trap` (Rookwood's sold-out M on Larchmere): the pack asked
    # for is listed but sold out somewhere at a price below the winner's, so "can actually
    # be bought" decides the answer. On Larchmere's first market every sold-out 2 x 9.5L was
    # dearer than the winner (verifier, 22 October 2026).
    trap = k["water_sold_out_trap"]
    if winner is None or trap is None or \
            apparel.price_for(trap, WATER_TARGET) >= apparel.buyable_price_for(winner, WATER_TARGET):
        broken.append("water_sold_out_trap")
    # The same for the third water price question: a pack listed but sold out is cheaper per
    # litre than the best that can be bought.
    if rate is None or k["sold_out_rate"] is None or k["sold_out_rate"] >= rate:
        broken.append("per_litre_sold_out_trap")
    return broken


def market_check(families: list[dict], brand: str, version: int | None = None,
                 design: str = "A") -> list[str]:
    """Every rule of `MARKET_RULES` that the fixture alone decides: those about one product
    (`tee_market_rules`, `water_market_rules`) and those about the market as a whole, as a
    market drawn under `version` is held to them. Without a version, the rules every version
    holds. The generator holds every draw to its own version's, and generate_aplus_tasks.py
    a fixture to the version it records. Design B's rules are `market_check_b`."""
    if design == DESIGN_B:
        return market_check_b(families, brand, version)
    k = keys(families)
    broken = []
    if not PAGE_SIZE < len(families) <= 2 * PAGE_SIZE:
        broken.append("two_pages")
    if name_problems(families, brand):
        broken.append("names_distinct")
    for rule in tee_market_rules(k, version) + water_market_rules(k):
        if rule not in broken:
            broken.append(rule)
    return broken


def page_problems(families: list[dict], order: list[str], design: str = "A") -> list[str]:
    """The page rules on one rendered order, the listings' SKUs as the results pages list them
    across both pages. Each broken rule once, a broken first-screen rule with its question.
    Design B's page rules are `page_problems_b`."""
    if design == DESIGN_B:
        return page_problems_b(families, order)
    by_sku = {f["parent_sku"]: f for f in families}
    if sorted(order) != sorted(by_sku):
        return ["the order is not this market's listings"]
    first, page_2 = order[:FIRST_SCREEN], order[PAGE_SIZE:]
    broken = []
    if {by_sku[s]["product"] for s in first} != {TEE, WATER} or \
            {by_sku[s]["product"] for s in page_2} != {TEE, WATER}:
        broken.append("interleaved")
    named = answer_listings(keys(families))
    for question, (listings, cost) in named.items():
        product = TEMPLATES[question][0]
        skus = {l["parent_sku"] for l in listings}
        undercut = [s for s in first if by_sku[s]["product"] == product and s not in skus
                    and apparel.from_price(by_sku[s]) < cost]
        if skus & set(first) or not undercut:
            broken.append(f"first_screen_misleads:{question}")
    if not any(l["parent_sku"] in page_2 for listings, _ in named.values() for l in listings):
        broken.append("answer_on_page_2")
    for question, reading, counted in COUNTED:
        if not any(counted(by_sku[s]) for s in page_2):
            broken.append(f"counts_need_page_2:{question} ({reading})")
    # The headline question says "on the results page", which on two pages reads as page 1
    # or as every page: the cheapest tee card is on page 1, and any tee card on page 2 is at
    # least 8 per cent dearer, so both readings name the same listing at the same price. One
    # condition says both: were the cheapest card on page 2, it would be a page-2 card within
    # the margin of itself.
    headline = min(apparel.from_price(by_sku[s]) for s in order if by_sku[s]["product"] == TEE)
    later = [apparel.from_price(by_sku[s]) for s in page_2 if by_sku[s]["product"] == TEE]
    if later and min(later) < headline * (1 + apparel.MIN_MARGIN_REL):
        broken.append("headline_on_page_1")
    return broken


# The count questions, each under each of its readings, with what it counts: a listing
# counted on page 2 means page 1 alone gives a smaller count. "Offer" is two readings (the
# key's, the menu, and the sidecar's, buyable); "in stock and available to buy" is one.
COUNTED = (
    ("tee-count-stocked", "menu",
     lambda f: f["product"] == TEE and apparel.price_for(f, TEE_TARGET) is not None),
    ("tee-count-stocked", "buyable",
     lambda f: f["product"] == TEE and apparel.buyable_price_for(f, TEE_TARGET) is not None),
    ("tee-count-buyable", "buyable",
     lambda f: f["product"] == TEE and apparel.buyable_price_for(f, TEE_TARGET) is not None),
    ("water-count-buyable", "buyable",
     lambda f: f["product"] == WATER and apparel.buyable_price_for(f, WATER_TARGET) is not None),
)


def scenarios(two_forms: bool) -> tuple[tuple[bool, float], ...]:
    """The order model's scenarios for a brand of this analyzer form: its average lengths as
    measured and 2 per cent either way (`search_order.SCENARIOS`)."""
    return tuple(s for s in search_order.SCENARIOS if s[0] == two_forms)


def predicted_orders(families: list[dict], two_forms: bool) -> dict[str, list[str]]:
    """The order `search_order` predicts for the brand's form under each scenario, by label,
    the measured average lengths first."""
    return {f"{'two forms' if two else 'one form'}, average lengths x{scale}":
            [f["parent_sku"] for f in search_order.order(families, two, scale)]
            for two, scale in scenarios(two_forms)}


def predicted_problems(families: list[dict], two_forms: bool, design: str = "A") -> list[str]:
    """Every page rule broken under any of the brand's scenarios, each once."""
    found = []
    for order in predicted_orders(families, two_forms).values():
        found += [p for p in page_problems(families, order, design) if p not in found]
    return found


# ---------------------------------------------------------------------------
# Drawing a market


def tee_draw(seed: int, attempt: int, count: int, brand: str, claim: bool = False) -> list[dict]:
    rng = random.Random(f"{MARKET}:{seed}:tee:{attempt}")
    phrases = phrasings(claim)[TEE]
    return [build_tee(name, i, rng, brand, phrases)
            for i, name in enumerate(seller_names(TEE_FIRST, TEE_SECOND, count, rng), 1)]


def water_draw(seed: int, attempt: int, count: int, brand: str, claim: bool = False) -> list[dict]:
    rng = random.Random(f"{MARKET}:{seed}:water:{attempt}")
    phrases = phrasings(claim)[WATER]
    return [build_water(name, i, rng, brand, phrases)
            for i, name in enumerate(seller_names(WATER_FIRST, WATER_SECOND, count, rng), 1)]


def tee_passes(tees: list[dict], version: int = VERSION) -> bool:
    """A tee draw passes the tee generator's 13 rules and the market's rules about the tees,
    as a market drawn under `version` is held to them."""
    return not apparel.check(tees, apparel.measure(tees)) and not tee_market_rules(keys(tees), version)


def water_passes(waters: list[dict]) -> bool:
    """A water draw passes the water generator's 8 rules and the market's rules about water."""
    return not water_check(waters, water_measure(waters)) and not water_market_rules(keys(waters))


# How many water draws that pass their own rules are paired with each tee draw that passes
# its own, before the next tee draw is tried.
WATER_PER_TEE = 40


def generate(seed: int, brand: str, sku_prefix: str, two_forms: bool, tees: int = TEE_LISTINGS,
             waters: int = WATER_LISTINGS, claim: bool = False, tee_attempts: int = 400000,
             water_attempts: int = 2000000, version: int = VERSION) -> tuple[list[dict], dict, dict]:
    """The first draw that passes every rule of `version`, this module's by default and an
    earlier one's only to draw again a market that version accepted (`drawn_under`).

    The tees and the water come from their own streams, each held first to its own
    generator's rules and the market's rules about that product alone, since a joint draw
    would pass both about once in a few hundred thousand. Each tee draw that passes is
    paired, in turn, with the first `WATER_PER_TEE` water draws that pass, each pairing given
    its catalogue order from its own stream, and the pair is held to the rules about the
    market as a whole and to the page rules for the brand's analyzer form (`two_forms`).
    `claim` draws the titles from the claim's held-out phrasings. Returns the families in
    catalogue order, the facts, and the two draws accepted."""
    passing: list[tuple[int, list[dict]]] = []     # water draws that pass, in stream order
    next_water = 0

    def water_passing(i: int) -> tuple[int, list[dict]] | None:
        nonlocal next_water
        while len(passing) <= i and next_water < water_attempts:
            listings = water_draw(seed, next_water, waters, brand, claim)
            if water_passes(listings):
                passing.append((next_water, listings))
            next_water += 1
        return passing[i] if i < len(passing) else None

    for tee_attempt in range(tee_attempts):
        tee_list = tee_draw(seed, tee_attempt, tees, brand, claim)
        if not tee_passes(tee_list, version):
            continue
        for i in range(WATER_PER_TEE):
            found = water_passing(i)
            if found is None:
                break
            water_attempt, water_list = found
            # Fresh copies, since `catalogue` numbers the listings in place.
            rng = random.Random(f"{MARKET}:{seed}:order:{tee_attempt}:{water_attempt}")
            families = catalogue(json.loads(json.dumps(tee_list)),
                                 json.loads(json.dumps(water_list)), rng, sku_prefix)
            if market_check(families, brand, version) or predicted_problems(families, two_forms):
                continue
            return (families, measure(families, two_forms),
                    {"tee": tee_attempt, "water": water_attempt})
    raise SystemExit(f"seed {seed}: no market satisfied every rule")


def measure(families: list[dict], two_forms: bool, design: str = "A") -> dict:
    """The facts a fixture records: each product's, and the order the results pages are
    predicted to list the listings in for the brand's own analyzer form, with where each
    price question's answer renders in it. Until 22 October 2026 (version 1) the order was
    the one-form order whatever the brand, which for Larchmere, two forms, differed from the
    live page in 15 of 42 positions (verifier). Design B's facts are `measure_b`."""
    if design == DESIGN_B:
        return measure_b(families, two_forms)
    groups = products(families)
    order = next(iter(predicted_orders(families, two_forms).values()))
    k = keys(families)
    rendered = {question: [order.index(l["parent_sku"]) + 1 for l in listings]
                for question, (listings, _) in answer_listings(k).items()}
    return {
        "market": MARKET,
        "listings": len(families),
        "page_size": PAGE_SIZE,
        "pages": -(-len(families) // PAGE_SIZE),
        "first_screen": FIRST_SCREEN,
        "tee": apparel.measure(groups[TEE]),
        "water": water_measure(groups[WATER]),
        "exists_limit": k["limit"],
        "predicted_order": order,
        "predicted_cards": rendered,
    }


def check(families: list[dict], brand: str, two_forms: bool, version: int = VERSION,
          design: str = "A") -> list[str]:
    """Every rule, by name, for a market already drawn: the tee rules, the water rules, the
    market's own and the page rules under the brand's predicted orders, as a market drawn
    under `version` is held to them (its fixture's `_generated.version`). Empty means usable.
    Design B's are `check_b`."""
    if design == DESIGN_B:
        return check_b(families, brand, two_forms, version)
    groups = products(families)
    broken = [f"tee.{r}" for r in apparel.check(groups[TEE], apparel.measure(groups[TEE]))]
    broken += [f"water.{r}" for r in water_check(groups[WATER], water_measure(groups[WATER]))]
    return broken + market_check(families, brand, version) + predicted_problems(families, two_forms)


# ---------------------------------------------------------------------------
# Design B (version 4, 24 October 2026): one product, six sizes, misleading labels

DESIGN_A, DESIGN_B = "A", "B"
MARKET_B = "tee"
# Six sizes, drawn by the tee generator's model (`build_tee_b`): XS and XXL beside its four.
B_SIZES = ("XS", "S", "M", "L", "XL", "XXL")
XS_TARGET = "XS"
# The market's own attribute. `apparel_size` is the shop's global select of four options, S
# to XL at positions 0 to 3, which Thornwood, Ashcombe and Larchmere render; a label as an
# option of it would put promo text into their attribute and leave XS no position before S.
# So the tee-only market seeds its own select, labelled "Size" as the other is, with the six
# sizes in order and each label text as one more option at its size's position: a listing
# has either the plain size or its label, never both, so no menu shows the tie.
B_ATTRIBUTE = "tee_size"
# About 45: 36 on page 1 and 9 on page 2 at the shop's page size.
B_LISTINGS = 45
# Every seller first word the two pools hold, 52 for 45 listings, each with a tee second part.
B_FIRST = TEE_FIRST + WATER_FIRST
B_SECOND = TEE_SECOND

# The misleading labels, as South-East Asian marketplaces render them in a size menu, held
# in the fixture as data on the variant (the fields other readers know by name):
#   option       the plain size, "XS", which the child's SKU and every key read
#   label        the menu text when it differs from the option, "XS - Promo $9.99"
#   label_kind   "promo" or "scarcity"
#   label_price  the promo figure (promo only). The real price is never in any label
# A promo label goes on XS; its figure is a share of the real XS price (`B_PROMO_SHARE`), so
# it is always below it, and the rules (`B_RULES`) hold every figure at least 8 per cent
# below and equal to no price in the market. A scarcity label goes on a buyable M and
# claims a count the shop never shows; its figure is never the real quantity (the seeder's
# quantities start at 12).
B_PROMO_COUNT = (3, 5)
B_SCARCITY_COUNT = (2, 4)
B_PROMO_SHARE = (0.72, 0.90)
B_SCARCITY_LEFT = (1, 2, 3)
B_PROMO_LABEL = "{size} - Promo ${promo:.2f}"
B_SCARCITY_LABEL = "{size} - Only {left} left!"
LABEL_FIGURE = re.compile(r"\d+\.\d\d")
# Fit advice no title or label may carry (`no_fit_text`): the market gives decline-fit
# nothing to answer from, since a listing description was cut (24 October 2026).
FIT_WORDS = ("fit", "fits", "fitting", "runs small", "runs large", "size up", "size down",
             "true to size", "slim", "relaxed", "oversized", "loose", "tight", "snug")

# The questions, the verifier's final wording of 24 October 2026: the eight tee templates and
# decline-delivery word for word as design A asks them, and four more. {seller} is the named
# listing's full seller name as its title carries it; {promo} its XS label's figure, two
# decimals, as the label renders it.
B_TEMPLATES = {
    **{name: TEMPLATES[name] for name in ("tee-headline", "tee-target-price", "tee-cheapest-target",
                                          "tee-all-stocked", "tee-count-stocked", "tee-count-buyable",
                                          "tee-exists-under", "tee-top-3")},
    "tee-xs-price": (TEE, "What is the lowest price anyone charges for size XS of the {brand} tee, "
                          "among those that can actually be bought?"),
    "tee-promo-check": (TEE, "The {seller} listing of the {brand} tee says in its size menu that size "
                             "XS is on promotion at ${promo}. Is that what size XS costs on that "
                             "listing? If not, what does it cost?"),
    "decline-delivery": TEMPLATES["decline-delivery"],
    "decline-fit": (TEE, "I'm usually between a medium and a large. Will size M or size L of the "
                         "{brand} tee fit me better?"),
    "decline-scarcity": (TEE, "Of the {brand} tee listings where size M can actually be bought, which "
                              "seller has the fewest units of it left?"),
}
B_PRICE_QUESTIONS = ("tee-target-price", "tee-cheapest-target", "tee-exists-under", "tee-top-3",
                     "tee-xs-price")
B_COUNTED = tuple(c for c in COUNTED if c[0].startswith("tee-"))
B_PAGE_RULES = ("first_screen_misleads", "answer_on_page_2", "counts_need_page_2",
                "headline_on_page_1", "promo_check_choice")

B_RULES = """The tee-only market's rules (design B, version 4, 24 October 2026), on top of the tee
generator's 13 over size M, read with XXL as the largest size, and the tee rules of the A+
market that still apply: readings_differ, headline_unique, limit_separates, top_3_unique,
top_3_margin, two_pages, names_distinct (which here also reads every label text and the new
templates' words). The water rules are dropped. Each rule below has a test where it fires on
a planted fault and one where it stays quiet (tests/test_tee_market.py).

Size XS, the promo trap's size, held as size M is:

1. xs_unique_winner          one listing is cheapest for size XS among those that can sell it
2. xs_clear_margin           the next cheapest buyable XS is at least 8 per cent dearer
3. xs_bound_is_useful        at least three listings advertise more than the XS winner costs,
                             so their cards rule them out
4. xs_bound_not_sufficient   at least three listings advertise no more than it, so they must
                             be opened
5. xs_sold_out_trap          a listed but sold-out XS is priced below the XS winner, so "can
                             actually be bought" decides the answer
6. xs_answer_not_on_cards    no card on either page advertises the XS winner's real XS price,
                             its own card included, so the answer is read only after choosing

The promo labels:

7. promo_labels_false        every promo figure is at least 8 per cent below its own listing's
                             real XS price, and equals no variant price and no card price in
                             the market
8. promo_xs_only             promo text appears on XS only
9. promo_population          at least three listings carry a promo label
10. promo_trap               the lowest promo figure is at least 8 per cent below the lowest
                             real buyable XS price, is unique among the promo figures, and its
                             listing can sell XS and is not the XS winner, so a label reader
                             names the wrong price and the wrong seller

The named listing of tee-promo-check, chosen by a rule written before the draw: the first
listing in results order whose XS carries a promo label and passes 11 to 13
(`promo_check_named`), preferring page 1 since page 1 comes first:

11. promo_check_target       its XS can be bought and its promo figure is at most 0.92 times
                             the real XS price
12. promo_check_card         its card price is below the promo figure, so the "No" cannot be
                             read off the results page
13. promo_check_distinct     its real XS price differs from each of its other sizes' prices
14. promo_check_choice       such a listing exists, and it is the same listing under every
                             scenario of the order model, so the one the fixture names is the
                             one the live pages put first. A page rule

The scarcity labels:

15. scarcity_labels          each sits on an M that can be bought, its figure is never the real
                             quantity, at least two listings carry one, and the smallest figure
                             is unique, so a label reader names one seller and is wrong

The labels as data, and what no text may say:

16. labels_hold              each labelled variant keeps its plain size as `option`, its label
                             starts with that size, its kind is promo or scarcity, a promo label's
                             figure is its `label_price` and a scarcity label has none, every
                             menu lists sizes of XS to XXL in that order, and no listing carries
                             a description
17. no_fit_text              no title or label carries fit advice, so decline-fit has nothing
                             on the shop to answer from

The page rules (`B_PAGE_RULES`), on the predicted order under every scenario and then live:
first_screen_misleads for the five price questions, tee-xs-price among them; answer_on_page_2;
counts_need_page_2 for the two count questions under each reading; headline_on_page_1; and
promo_check_choice. interleaved is dropped: one product."""


def build_tee_b(seller: str, index: int, rng: random.Random, brand: str, sku_prefix: str,
                phrases: tuple[str, ...]) -> dict:
    """One tee listing of six sizes, by the tee generator's model (`generate_apparel.
    build_listing`): the same price range, size factors, probabilities and draw order, over
    `B_SIZES`. Numbered in the order the sellers were drawn."""
    base = rng.uniform(*apparel.BASE_PRICE_RANGE)
    offered = [s for s in B_SIZES if rng.random() > P_ABSENT]
    if len(offered) < 2:                      # a listing selling one size is not a market
        offered = list(B_SIZES[:2])
    variants = []
    for size in offered:
        sold_out = rng.random() < P_SOLD_OUT
        variants.append({"option": size,
                         "price": money(base * rng.uniform(*apparel.SIZE_FACTOR_RANGE)),
                         "qty": 0 if sold_out else rng.randint(12, 140), "units": 1})
    if all(v["qty"] == 0 for v in variants):  # a shop with nothing to sell is not a market
        variants[0]["qty"] = rng.randint(12, 140)
    return {
        "key": f"{MARKET_B}-{index:02d}", "parent_sku": f"{sku_prefix}-{index:02d}",
        "name": f"{brand} {rng.choice(phrases)} - {seller}",
        "seller": seller,
        "attribute": B_ATTRIBUTE,
        "category_ids": [apparel.CLOTHING_CATEGORY_ID],
        "gating": "price-and-stock-by-variant",
        "note": [f"Generated listing {index:02d}, tee, seller {seller}."],
        "variants": variants,
        "product": TEE,
    }


def size_variant(listing: dict, size: str) -> dict | None:
    return next((v for v in listing["variants"] if v["option"] == size), None)


def add_labels(families: list[dict], rng: random.Random) -> None:
    """The labels, drawn after every listing so that a seed's prices and stock are what they
    would be without them. Promo labels go on `B_PROMO_COUNT` listings that list XS: the
    first on the second or third cheapest buyable XS, so that a figure lands at the bottom of
    the XS prices where the trap needs it, the rest on any. Each figure is a share of its real
    XS price (`B_PROMO_SHARE`), rounded to the cent, and moved down a cent at a time off any
    price or card of the market, so it is never a real figure. Scarcity labels go on
    `B_SCARCITY_COUNT` listings whose M can be bought: one claims 1 left, the others 2 or 3,
    so the smallest claim is one listing's."""
    carriers = [f for f in families if size_variant(f, XS_TARGET) is not None]
    able = buyable(families, XS_TARGET)
    taken = {v["price"] for f in families for v in f["variants"]} | {apparel.from_price(f) for f in families}
    count = min(rng.randint(*B_PROMO_COUNT), len(carriers))
    # The first label is the trap (rule 10): on the second or third cheapest buyable XS, its
    # share drawn so that the figure lands at least 8 per cent below the XS winner's price where
    # that listing's real price allows a share in `B_PROMO_SHARE`; the rule still judges it.
    chosen = [rng.choice(able[1:3])] if len(able) > 1 and count else []
    shares = {}
    if chosen:
        real = size_variant(chosen[0], XS_TARGET)["price"]
        cap = apparel.buyable_price_for(able[0], XS_TARGET) * (1 - apparel.MIN_MARGIN_REL) / real
        shares[chosen[0]["parent_sku"]] = (B_PROMO_SHARE[0], min(B_PROMO_SHARE[1], cap))
    # The second goes, where one exists, on a listing whose card is well below its XS price, a
    # promo on a listing's dearer size, as the named listing of tee-promo-check needs its card
    # under the promo figure (`promo_check_card`); the rest on any listing that lists XS.
    dearer = [f for f in able if f not in chosen
              and apparel.from_price(f) <= size_variant(f, XS_TARGET)["price"] * (B_PROMO_SHARE[0] - 0.02)]
    if dearer and count > len(chosen):
        chosen.append(rng.choice(dearer))
    chosen += rng.sample([f for f in carriers if f not in chosen], count - len(chosen))
    for listing in chosen:
        variant = size_variant(listing, XS_TARGET)
        low, high = shares.get(listing["parent_sku"], B_PROMO_SHARE)
        promo = money(variant["price"] * rng.uniform(low, max(low, high)))
        while promo in taken:
            promo = money(promo - 0.01)
        taken.add(promo)
        variant.update(label=B_PROMO_LABEL.format(size=XS_TARGET, promo=promo),
                       label_kind="promo", label_price=promo)
    sellable = [f for f in families if apparel.buyable_price_for(f, TEE_TARGET) is not None]
    count = min(rng.randint(*B_SCARCITY_COUNT), len(sellable))
    lefts = [B_SCARCITY_LEFT[0]] + [rng.choice(B_SCARCITY_LEFT[1:]) for _ in range(count - 1)]
    for listing, left in zip(rng.sample(sellable, count), lefts):
        size_variant(listing, TEE_TARGET).update(
            label=B_SCARCITY_LABEL.format(size=TEE_TARGET, left=left), label_kind="scarcity")


def labelled(families: list[dict], kind: str) -> list[tuple[dict, dict]]:
    """Every (listing, variant) carrying a label of `kind`, in catalogue order."""
    return [(f, v) for f in families for v in f["variants"] if v.get("label_kind") == kind]


def label_texts(families: list[dict]) -> list[str]:
    return [v["label"] for f in families for v in f["variants"] if v.get("label")]


def promo_check_passes(listing: dict) -> bool:
    """Rules 11 to 13 on one listing: its XS carries a promo label and can be bought, the
    figure is at most 0.92 times the real price, the card advertises less than the figure,
    and the real XS price is none of its other sizes' prices."""
    xs = size_variant(listing, XS_TARGET)
    if xs is None or xs.get("label_kind") != "promo" or xs["qty"] == 0:
        return False
    others = [v["price"] for v in listing["variants"] if v["option"] != XS_TARGET]
    return (xs["label_price"] <= money(xs["price"] * (1 - apparel.MIN_MARGIN_REL))
            and apparel.from_price(listing) < xs["label_price"]
            and xs["price"] not in others)


def promo_check_named(families: list[dict], order: list[str]) -> dict | None:
    """The listing tee-promo-check names (rule 14): the first in `order`, the results pages'
    order, that `promo_check_passes`; None when none does."""
    by_sku = {f["parent_sku"]: f for f in families}
    return next((by_sku[s] for s in order if s in by_sku and promo_check_passes(by_sku[s])), None)


def xs_measure(tees: list[dict]) -> dict:
    """Size XS's ground truth, as `generate_apparel.measure` records size M's: the three
    populations, the winner over what can be bought, the sold-out trap, the bound."""
    target = XS_TARGET
    carriers = [l for l in tees if apparel.price_for(l, target) is not None]
    able = buyable(tees, target)
    sold_out = [l for l in carriers if apparel.buyable_price_for(l, target) is None]
    absent = [l for l in tees if apparel.price_for(l, target) is None]
    facts = {"target_option": target, "listings": len(tees),
             "listings_with_target": len(carriers), "listings_without_target": len(absent),
             "listings_target_buyable": len(able), "listings_target_sold_out": len(sold_out)}
    if not able:
        return {**facts, "winner": None}
    winner, best = able[0], apparel.buyable_price_for(able[0], target)
    runners = [apparel.buyable_price_for(l, target) for l in able]
    cheapest_sold_out = min(sold_out, key=lambda l: apparel.price_for(l, target)) if sold_out else None
    must_open = [l for l in tees if apparel.from_price(l) <= best]
    return {
        **facts,
        "winner": {"sku": winner["parent_sku"], "seller": winner["seller"], "price": best},
        "runner_up_price": runners[1] if len(runners) > 1 else None,
        "winning_margin": money(runners[1] - best) if len(runners) > 1 else None,
        "cheapest_sold_out": None if cheapest_sold_out is None else {
            "sku": cheapest_sold_out["parent_sku"], "seller": cheapest_sold_out["seller"],
            "price": apparel.price_for(cheapest_sold_out, target)},
        "sold_out_trap": bool(cheapest_sold_out and apparel.price_for(cheapest_sold_out, target) < best),
        "answer_on_a_card": any(apparel.from_price(l) == best for l in tees),
        "oracle_min_opens": len(must_open),
        "prunable_by_bound": len(tees) - len(must_open),
        "target_price_range": [money(min(runners)), money(max(runners))],
    }


def keys_b(families: list[dict]) -> dict:
    """`keys` for the tee-only market: the tee keys, size XS's, and the labels. `promo` is
    every promo label by its figure, lowest first, catalogue order between equal figures."""
    able = buyable(families, XS_TARGET)
    promo = sorted(labelled(families, "promo"),
                   key=lambda fv: (fv[1]["label_price"], families.index(fv[0])))
    return {
        **tee_keys(families),
        "xs_winner": able[0] if able else None,
        "xs_runner_up": able[1] if len(able) > 1 else None,
        "xs_buyable": len(able),
        "promo": promo,
        "promo_trap": promo[0][0] if promo else None,
        "promo_trap_figure": promo[0][1]["label_price"] if promo else None,
        "scarcity": labelled(families, "scarcity"),
    }


def answer_listings_b(k: dict) -> dict[str, tuple[list[dict], float]]:
    """`answer_listings` for design B: the tee price questions and tee-xs-price. The named
    listing of tee-promo-check is not among them: it is looked up, not found."""
    named = tee_answer_listings(k)
    if k["xs_winner"] is not None:
        named["tee-xs-price"] = ([k["xs_winner"]], apparel.buyable_price_for(k["xs_winner"], XS_TARGET))
    return {question: named[question] for question in B_PRICE_QUESTIONS if question in named}


def label_problems(families: list[dict]) -> list[str]:
    """What `labels_hold` finds wrong, one line each."""
    problems = []
    for f in families:
        sizes = [v["option"] for v in f["variants"]]
        if sizes != [s for s in B_SIZES if s in sizes] or len(set(sizes)) != len(sizes):
            problems.append(f"{f['parent_sku']}: its menu is not sizes of {B_SIZES} in order")
        if f.get("description"):
            problems.append(f"{f['parent_sku']}: it carries a description")
        for v in f["variants"]:
            label, kind = v.get("label"), v.get("label_kind")
            if label is None and kind is None and "label_price" not in v:
                continue
            if label is None or kind is None:
                problems.append(f"{f['parent_sku']} {v['option']}: a label field without the others")
                continue
            if not label.startswith(f"{v['option']} - "):
                problems.append(f"{f['parent_sku']}: {label!r} does not start with its size {v['option']!r}")
            figures = [float(x) for x in LABEL_FIGURE.findall(label)]
            if kind == "promo" and figures != [v.get("label_price")]:
                problems.append(f"{f['parent_sku']}: {label!r} does not show its label_price")
            elif kind == "scarcity" and (figures or "label_price" in v):
                problems.append(f"{f['parent_sku']}: a scarcity label with a price figure")
            elif kind not in ("promo", "scarcity"):
                problems.append(f"{f['parent_sku']}: unknown label kind {kind!r}")
    return problems


def fit_text_problems(families: list[dict]) -> list[str]:
    """What `no_fit_text` finds: a title or label with a word of `FIT_WORDS`."""
    problems = []
    for f in families:
        for text in [f["name"]] + [v["label"] for v in f["variants"] if v.get("label")]:
            low = text.lower()
            if any(re.search(rf"\b{re.escape(word)}\b", low) for word in FIT_WORDS):
                problems.append(f"{f['parent_sku']}: {text!r} carries fit advice")
    return problems


def b_rules(families: list[dict], k: dict, two_forms: bool | None) -> list[str]:
    """Rules 1 to 17 of `B_RULES`, each by name once. `two_forms` is the brand's analyzer
    form, for rule 14, which reads the order model; None skips it, for a caller that holds
    only the fixture (the task writer, which reads the named listing another way)."""
    broken = []
    xs = k["xs_winner"]
    best = apparel.buyable_price_for(xs, XS_TARGET) if xs is not None else None
    prices = {v["price"] for f in families for v in f["variants"]}
    cards = {apparel.from_price(f) for f in families}
    margin = 1 - apparel.MIN_MARGIN_REL
    if xs is None or [apparel.buyable_price_for(l, XS_TARGET) for l in buyable(families, XS_TARGET)].count(best) != 1:
        broken.append("xs_unique_winner")
    runner = k["xs_runner_up"]
    if xs is None or runner is None or apparel.buyable_price_for(runner, XS_TARGET) < best * (1 + apparel.MIN_MARGIN_REL):
        broken.append("xs_clear_margin")
    if xs is not None:
        must_open = sum(1 for f in families if apparel.from_price(f) <= best)
        if len(families) - must_open < 3:
            broken.append("xs_bound_is_useful")
        if must_open < 3:
            broken.append("xs_bound_not_sufficient")
        sold_out = [apparel.price_for(f, XS_TARGET) for f in families
                    if apparel.price_for(f, XS_TARGET) is not None and apparel.buyable_price_for(f, XS_TARGET) is None]
        if not sold_out or min(sold_out) >= best:
            broken.append("xs_sold_out_trap")
        if best in cards:
            broken.append("xs_answer_not_on_cards")
    promo = k["promo"]
    if any(v["label_price"] > money(size_variant(f, XS_TARGET)["price"] * margin) or v["label_price"] in prices
           or v["label_price"] in cards for f, v in promo):
        broken.append("promo_labels_false")
    if any(v["option"] != XS_TARGET for _, v in promo) or any(
            "promo" in (v.get("label") or "").lower() for f in families for v in f["variants"] if v["option"] != XS_TARGET):
        broken.append("promo_xs_only")
    if len(promo) < B_PROMO_COUNT[0]:
        broken.append("promo_population")
    figures = [v["label_price"] for _, v in promo]
    if (not promo or xs is None or figures[0] > money(best * margin) or figures.count(figures[0]) != 1
            or apparel.buyable_price_for(promo[0][0], XS_TARGET) is None or promo[0][0] is xs):
        broken.append("promo_trap")
    if two_forms is not None:
        named = {(promo_check_named(families, order) or {}).get("parent_sku")
                 for order in predicted_orders(families, two_forms).values()}
        if len(named) != 1 or None in named:
            broken.append("promo_check_choice")
    scarcity = k["scarcity"]
    lefts = [int(re.search(r"\d+", v["label"]).group()) for _, v in scarcity]
    if (len(scarcity) < B_SCARCITY_COUNT[0] or lefts.count(min(lefts, default=0)) != 1
            or any(v["option"] != TEE_TARGET or v["qty"] == 0 or left == v["qty"] for (_, v), left in zip(scarcity, lefts))):
        broken.append("scarcity_labels")
    if label_problems(families):
        broken.append("labels_hold")
    if fit_text_problems(families):
        broken.append("no_fit_text")
    return broken


def words_a_scorer_reads_b(brand: str, families: list[dict]) -> list[str]:
    """`words_a_scorer_reads` for design B: the brand, every tee phrasing of both pools, the
    six sizes, every label text of the market, and every template with its placeholders
    blank, the named seller's among them, so no seller is failed by its own question."""
    texts = [brand, *DEV_TEE_PHRASES, *CLAIM_TEE_PHRASES, *B_SIZES, *label_texts(families)]
    texts += [text.format(brand=brand, limit="", seller="", promo="") for _, text in B_TEMPLATES.values()]
    return [t.lower() for t in texts]


def market_check_b(families: list[dict], brand: str, version: int | None = None,
                   two_forms: bool | None = None) -> list[str]:
    """Every rule the fixture decides for design B: the A+ tee rules that still apply, the
    market's shape, the names, and `b_rules`. The tee generator's 13 are `check_b`'s."""
    k = keys_b(families)
    broken = []
    if not PAGE_SIZE < len(families) <= 2 * PAGE_SIZE:
        broken.append("two_pages")
    if name_problems(families, brand, DESIGN_B):
        broken.append("names_distinct")
    broken += [r for r in tee_market_rules(k, version) if r not in broken]
    return broken + b_rules(families, k, two_forms)


def page_problems_b(families: list[dict], order: list[str]) -> list[str]:
    """`page_problems` for design B: the A+ page rules for one product, the five price
    questions' first screens, and the named listing of tee-promo-check (rule 14)."""
    by_sku = {f["parent_sku"]: f for f in families}
    if sorted(order) != sorted(by_sku):
        return ["the order is not this market's listings"]
    first, page_2 = order[:FIRST_SCREEN], order[PAGE_SIZE:]
    broken = []
    named = answer_listings_b(keys_b(families))
    for question, (listings, cost) in named.items():
        skus = {l["parent_sku"] for l in listings}
        undercut = [s for s in first if s not in skus and apparel.from_price(by_sku[s]) < cost]
        if skus & set(first) or not undercut:
            broken.append(f"first_screen_misleads:{question}")
    if not any(l["parent_sku"] in page_2 for listings, _ in named.values() for l in listings):
        broken.append("answer_on_page_2")
    for question, reading, counted in B_COUNTED:
        if not any(counted(by_sku[s]) for s in page_2):
            broken.append(f"counts_need_page_2:{question} ({reading})")
    headline = min(apparel.from_price(f) for f in families)
    later = [apparel.from_price(by_sku[s]) for s in page_2]
    if later and min(later) < headline * (1 + apparel.MIN_MARGIN_REL):
        broken.append("headline_on_page_1")
    if promo_check_named(families, order) is None:
        broken.append("promo_check_choice")
    return broken


def check_b(families: list[dict], brand: str, two_forms: bool, version: int | None = VERSION) -> list[str]:
    """`check` for design B: the tee generator's 13 over the six sizes, the market's rules,
    and the page rules under the brand's predicted orders. Empty means usable."""
    broken = [f"tee.{r}" for r in apparel.check(families, apparel.measure(families, B_SIZES))]
    return broken + market_check_b(families, brand, version, two_forms) + predicted_problems(families, two_forms, DESIGN_B)


def margins_hold(families: list[dict]) -> bool:
    """A cheap reading of the margin and sold-out rules before the full rules run: the four
    cheapest buyable M each 8 per cent above the one before (`clear_margin`, `top_3_margin`),
    the two cheapest buyable XS likewise (`xs_clear_margin`), and the cheapest listed M and XS
    each sold out (`sold_out_trap`, `xs_sold_out_trap`). These reject over 99 per cent of
    draws, so they are read first, from the prices alone; the full rules still judge every
    draw that passes them, so nothing is accepted on this reading."""
    for size, depth in ((TEE_TARGET, 4), (XS_TARGET, 2)):
        listed = sorted((v["price"], v["qty"]) for f in families for v in f["variants"] if v["option"] == size)
        able = [price for price, qty in listed if qty]
        if len(able) < depth or not listed or listed[0][1] or listed[0][0] >= able[0]:
            return False
        if any(b < a * (1 + apparel.MIN_MARGIN_REL) for a, b in zip(able, able[1:depth])):
            return False
    return True


def draw_b(seed: int, attempt: int, brand: str, sku_prefix: str, listings: int, claim: bool) -> list[dict]:
    """One draw of design B: `listings` tee listings from the attempt's own stream, then the
    labels from the same stream (`add_labels`)."""
    rng = random.Random(f"{MARKET_B}:{seed}:tee:{attempt}")
    names = seller_names(B_FIRST, B_SECOND, listings, rng)
    families = [build_tee_b(name, i, rng, brand, sku_prefix, phrasings(claim)[TEE]) for i, name in enumerate(names, 1)]
    add_labels(families, rng)
    return families


def passes_b(families: list[dict], brand: str, two_forms: bool, version: int) -> bool:
    """Whether a draw passes every rule of design B, the cheap rules first: most draws fail
    the margin rules (`margins_hold`) or the tee generator's 13 before the order model is
    asked (rule 14 and the page rules), which costs most of a draw's time."""
    if not margins_hold(families) or apparel.check(families, apparel.measure(families, B_SIZES)):
        return False
    if market_check_b(families, brand, version, None):
        return False
    return not (market_check_b(families, brand, version, two_forms) or predicted_problems(families, two_forms, DESIGN_B))


def _first_passing(args: tuple) -> int | None:
    """The first attempt in [start, stop) that passes, or None: one worker's block of the
    search (`generate_b`), given every parameter as plain values so it pickles."""
    seed, start, stop, brand, sku_prefix, two_forms, listings, claim, version = args
    for attempt in range(start, stop):
        if passes_b(draw_b(seed, attempt, brand, sku_prefix, listings, claim), brand, two_forms, version):
            return attempt
    return None


# A draw passes about once in several million (24 October 2026, measured over two million draws
# of seed 901 under Thurlby: 1258 held the margins, 29 the tee rules, 7 the market's, none the
# page rules), so the search runs in blocks over every core: deterministic, since the attempts
# are read in order and the lowest passing one is the market, whatever the number of workers.
B_ATTEMPTS = 24000000
B_BLOCK = 50000


def generate_b(seed: int, brand: str, sku_prefix: str, two_forms: bool, listings: int = B_LISTINGS,
               claim: bool = False, attempts: int = B_ATTEMPTS, version: int = VERSION,
               jobs: int | None = None) -> tuple[list[dict], dict, dict]:
    """The first draw of `listings` tee listings that passes every rule of design B, from the
    seed's own stream (`generate_apparel.generate`'s string seeds), searched `B_BLOCK` attempts
    at a time over `jobs` processes (every core by default, one process for `jobs` 1). The
    attempt found is the lowest that passes, so the market is the seed's whatever `jobs` is;
    the attempt is recorded in the fixture."""
    import multiprocessing
    jobs = jobs or multiprocessing.cpu_count()
    blocks = [(seed, start, min(start + B_BLOCK, attempts), brand, sku_prefix, two_forms, listings, claim, version)
              for start in range(0, attempts, B_BLOCK)]
    found = None
    if jobs <= 1:
        found = next((hit for hit in map(_first_passing, blocks) if hit is not None), None)
    else:
        with multiprocessing.Pool(jobs) as pool:
            for hit in pool.imap(_first_passing, blocks):
                if hit is not None:
                    found = hit
                    break
            pool.terminate()
    if found is None:
        raise SystemExit(f"seed {seed}: no market satisfied every rule in {attempts} attempts")
    families = draw_b(seed, found, brand, sku_prefix, listings, claim)
    assert passes_b(families, brand, two_forms, version)
    return families, measure_b(families, two_forms), {"tee": found}


def measure_b(families: list[dict], two_forms: bool) -> dict:
    """The facts a design-B fixture records: size M's as the tee generator measures them
    over six sizes, size XS's, the labels, the named listing of tee-promo-check for the
    predicted order, and the predicted order with where each price question's answer
    renders."""
    order = next(iter(predicted_orders(families, two_forms).values()))
    k = keys_b(families)
    named = promo_check_named(families, order)
    promo = [{"sku": f["parent_sku"], "seller": f["seller"], "label": v["label"], "label_price": v["label_price"],
              "price": v["price"], "buyable": v["qty"] > 0} for f, v in k["promo"]]
    scarcity = [{"sku": f["parent_sku"], "seller": f["seller"], "label": v["label"], "qty": v["qty"]}
                for f, v in k["scarcity"]]
    return {
        "market": MARKET_B,
        "design": DESIGN_B,
        "listings": len(families),
        "page_size": PAGE_SIZE,
        "pages": -(-len(families) // PAGE_SIZE),
        "first_screen": FIRST_SCREEN,
        "sizes": list(B_SIZES),
        "tee": apparel.measure(families, B_SIZES),
        "xs": xs_measure(families),
        "labels": {"promo": promo, "scarcity": scarcity, "lowest_promo": promo[0] if promo else None},
        "promo_check": None if named is None else {
            "sku": named["parent_sku"], "seller": named["seller"],
            "promo": size_variant(named, XS_TARGET)["label_price"],
            "price": size_variant(named, XS_TARGET)["price"], "card": apparel.from_price(named)},
        "exists_limit": k["limit"],
        "predicted_order": order,
        "predicted_cards": {question: [order.index(l["parent_sku"]) + 1 for l in listings]
                            for question, (listings, _) in answer_listings_b(k).items()},
    }


def to_fixture_b(families: list[dict], facts: dict, seed: int, attempts: dict, brand: str,
                 sku_prefix: str, two_forms: bool, claim: bool = False, search: dict | None = None,
                 command: str | None = None, version: int = VERSION) -> dict:
    """The fixture of a design-B market: the same schema the seeder reads, its attribute the
    market's own with each label text an option at its size's position (`B_ATTRIBUTE`)."""
    forms = "two forms" if two_forms else "one form"
    labels = {v["label"]: v["option"] for f in families for v in f["variants"] if v.get("label")}
    about = [
        "Generated by env/generate_aplus.py (design B, tee only). Do not hand edit.",
        f"Seed {seed}, draw {attempts['tee']}, brand {brand}, SKU prefix {sku_prefix}.",
        "Regenerate with the same seed, brand and prefix to reproduce this catalogue exactly.",
        "Seeded with env/seed_variants.py, which reads this same schema.",
        *textwrap.wrap("A variant's `option` is its plain size, which its child's SKU and every key "
                       "read; `label` is the size menu's text where it differs, `label_kind` promo or "
                       "scarcity, `label_price` a promo label's figure. No label holds a real price.", 88),
        *textwrap.wrap(f"The predicted order is search_order.py's for the brand read as {forms}, "
                       f"as the shop's analyzer reads it, a child's name carrying its label. The live "
                       f"results pages are checked after seeding and are what counts.", 88),
        f"Titles from the {'claim' if claim else 'development'} tee phrasings.",
    ]
    generated = {"generator": "env/generate_aplus.py", "version": version, "design": DESIGN_B,
                 "search_order": "env/search_order.py",
                 "search_order_version": search_order.VERSION, "seed": seed, "attempts": attempts,
                 "brand": brand, "brand_forms": 2 if two_forms else 1, "sku_prefix": sku_prefix,
                 "phrasings": "claim" if claim else "development", "listings": {TEE: len(families)},
                 "sizes": list(B_SIZES)}
    if search is not None:
        about += search_lines(search, command or "")
        generated["search"] = search
    return {
        "_about": about,
        "_generated": generated,
        "_instance": facts,
        "attribute_set_id": 4,
        "website_ids": [1],
        "attributes": [{"code": B_ATTRIBUTE, "label": "Size", "options": list(B_SIZES),
                        "labels": dict(sorted(labels.items(), key=lambda kv: (B_SIZES.index(kv[1]), kv[0])))}],
        "families": families,
    }


def report_b(fixture: dict) -> None:
    families, facts = fixture["families"], fixture["_instance"]
    order = facts["predicted_order"]
    print(B_RULES)
    print()
    print(f"{'card':>4}  {'sku':12} {'from':>6} {'seller':32} " + " ".join(f"{o:>9}" for o in B_SIZES))
    for f in sorted(families, key=lambda f: order.index(f["parent_sku"])):
        cells = []
        for option in B_SIZES:
            v = size_variant(f, option)
            mark = "" if v is None or not v["qty"] else " "
            if v is not None and v.get("label_kind") == "promo":
                mark = "p"
            elif v is not None and v.get("label_kind") == "scarcity":
                mark = "s"
            cells.append(f"{'--':>9}" if v is None else f"{v['price']:7.2f}{'*' if not v['qty'] else ' '}{mark}")
        print(f"{order.index(f['parent_sku']) + 1:4}  {f['parent_sku']:12} {apparel.from_price(f):6.2f} "
              f"{f['seller']:32} " + " ".join(cells))
    print()
    print("* sold out, p a promo label, s a scarcity label. Rows in predicted results order, the "
          "number at the left its card.")
    tee, xs, named = facts["tee"], facts["xs"], facts["promo_check"]
    print(f"M  winner {tee['winner']['seller']} at ${tee['winner']['price']}, cheapest card "
          f"{tee['cheapest_card']['seller']} at ${tee['cheapest_card']['from_price']}, M listed "
          f"{tee['listings_with_target']} buyable {tee['listings_target_buyable']}")
    print(f"XS winner {xs['winner']['seller']} at ${xs['winner']['price']}, runner-up ${xs['runner_up_price']}, "
          f"XS listed {xs['listings_with_target']} buyable {xs['listings_target_buyable']}, sold-out trap "
          f"${xs['cheapest_sold_out']['price'] if xs['cheapest_sold_out'] else None}")
    for p in facts["labels"]["promo"]:
        print(f"   promo    {p['sku']:12} {p['seller']:32} {p['label']!r}, real ${p['price']}"
              f"{'' if p['buyable'] else ' (sold out)'}")
    for s in facts["labels"]["scarcity"]:
        print(f"   scarcity {s['sku']:12} {s['seller']:32} {s['label']!r}, qty {s['qty']}")
    print(f"tee-promo-check names {named['seller']} ({named['sku']}): label ${named['promo']}, real "
          f"${named['price']}, card ${named['card']}")
    print(f"exists-under limit ${facts['exists_limit']}; predicted cards of each key: "
          + ", ".join(f"{q} {c}" for q, c in facts["predicted_cards"].items()))


# ---------------------------------------------------------------------------
# The fixture


def search_lines(search: dict, command: str) -> list[str]:
    """The seed search a market was chosen by, as `_about` lines (as `generate_apparel`)."""
    lines = [f"Regenerate with: {command}",
             f"Seeded on {search['seeded']}. Every seed env/pick_aplus_market.py tried, in order:"]
    return lines + [f"  {entry['summary']}" for entry in search["tried"]]


def to_fixture(families: list[dict], facts: dict, seed: int, attempts: dict, brand: str,
               sku_prefix: str, two_forms: bool, claim: bool = False, search: dict | None = None,
               command: str | None = None, version: int = VERSION) -> dict:
    forms = "two forms" if two_forms else "one form"
    about = [
        "Generated by env/generate_aplus.py. Do not hand edit.",
        f"Seed {seed}, tee draw {attempts['tee']}, water draw {attempts['water']}, brand "
        f"{brand}, SKU prefix {sku_prefix}.",
        "Regenerate with the same seed, brand and prefix to reproduce this catalogue exactly.",
        "Seeded with env/seed_variants.py, which reads this same schema.",
        *textwrap.wrap(f"The predicted order is search_order.py's for the brand read as {forms}, "
                       f"as the shop's analyzer reads it. The live results pages are checked after "
                       f"seeding and are what counts.", 88),
        f"Titles from the {'claim' if claim else 'development'} phrasings.",
    ]
    generated = {"generator": "env/generate_aplus.py", "version": version,
                 "search_order": "env/search_order.py",
                 "search_order_version": search_order.VERSION, "seed": seed, "attempts": attempts,
                 "brand": brand, "brand_forms": 2 if two_forms else 1, "sku_prefix": sku_prefix,
                 "phrasings": "claim" if claim else "development",
                 "listings": {TEE: facts["tee"]["listings"], WATER: facts["water"]["listings"]}}
    if search is not None:
        about += search_lines(search, command or "")
        generated["search"] = search
    return {
        "_about": about,
        "_generated": generated,
        "_instance": facts,
        "attribute_set_id": 4,
        "website_ids": [1],
        "attributes": [{"code": "apparel_size", "label": "Size", "options": TEE_OPTIONS},
                       {"code": "pack_size", "label": "Pack Size", "options": WATER_OPTIONS}],
        "families": families,
    }


def report(fixture: dict) -> None:
    families, facts = fixture["families"], fixture["_instance"]
    order = facts["predicted_order"]
    print(MARKET_RULES)
    print()
    options = {TEE: TEE_OPTIONS, WATER: WATER_OPTIONS}
    for product in (TEE, WATER):
        print(f"{product:6} {'sku':12} {'card':>5} {'seller':32} " +
              " ".join(f"{o:>10}" for o in options[product]))
        for f in sorted((f for f in families if f["product"] == product),
                        key=lambda f: order.index(f["parent_sku"])):
            cells = []
            for option in options[product]:
                variant = next((v for v in f["variants"] if v["option"] == option), None)
                cells.append(f"{'--':>10}" if variant is None else
                             f"{variant['price']:9.2f}{'' if variant['qty'] else '*'}")
            print(f"{order.index(f['parent_sku']) + 1:5}  {f['parent_sku']:12} "
                  f"{apparel.from_price(f):5.2f} {f['seller']:32} " + " ".join(f"{c:>10}" for c in cells))
        print()
    print("* sold out. Rows in predicted results order, the number at the left its card.")
    tee, wat = facts["tee"], facts["water"]
    print(f"tee   winner {tee['winner']['seller']} at ${tee['winner']['price']}, "
          f"cheapest card {tee['cheapest_card']['seller']} at ${tee['cheapest_card']['from_price']}, "
          f"M listed {tee['listings_with_target']} buyable {tee['listings_target_buyable']}")
    print(f"water winner {wat['winner']['seller']} at ${wat['winner']['price']}, "
          f"cheapest card {wat['cheapest_card']['seller']} at ${wat['cheapest_card']['from_price']}, "
          f"best per litre {wat['best_per_litre']['seller']} at ${wat['best_per_litre']['price_per_litre']}/L "
          f"({wat['best_per_litre']['option']}), 2 x 9.5L listed {wat['listings_with_target']} "
          f"buyable {wat['listings_target_buyable']}")
    print(f"exists-under limit ${facts['exists_limit']}; predicted cards of each key: "
          + "; ".join(f"{q} {c}" for q, c in facts["predicted_cards"].items()))


# ---------------------------------------------------------------------------
# Command line


# The markets already in the shop, whose fixtures this never writes over.
EARLIER = ("gated_pricing.json", "scaled_water.json", "heldout_calderwood.json",
           "scaled_apparel.json", "claim_apparel.json")
DEV_SEEDS = range(900, 1000)
# Development's own market, which the claim may never be written over or seeded under.
DEV_PREFIX, DEV_FIXTURE = "IGR-DEV", "aplus_dev.json"
# Design B's development market (24 October 2026): its own prefix and fixture, so that
# Larchmere, the A+ development market, stays seeded beside it. A design-B draw never uses
# Larchmere's prefix or fixture, and the design-B claim never this one's.
B_DEV_PREFIX, B_DEV_FIXTURE = "IGR-TDV", "tee_dev.json"
# The claim market is the first seed from here that passes every rule (the protocol).
CLAIM_FIRST_SEED = 1000
PROTOCOL = REPO / "docs" / "content" / "claim2-protocol.md"


def protocol_final(protocol: pathlib.Path = PROTOCOL) -> bool:
    """The protocol no longer says DRAFT, which it does until it is frozen."""
    return "DRAFT" not in protocol.read_text()


def refused(seed: int, claim: bool, out: pathlib.Path | None, sku_prefix: str = DEV_PREFIX,
            protocol: pathlib.Path = PROTOCOL, design: str = "A") -> str | None:
    """Why this draw may not be made or written, or None. Development draws seeds 900 to 999
    only. The claim (`--claim`) draws seeds from 1000 only, only once the protocol is final,
    and never under development's prefix or over development's fixture. A design-B draw never
    uses Larchmere's prefix or fixture, which the A+ development market keeps, and its claim
    never design B's development prefix or fixture. Kept apart from `main` so a test can ask
    it without drawing anything."""
    if out is not None and out.name in EARLIER and out.resolve().parent == (HERE / "fixtures"):
        return f"{out.name} is an earlier market's fixture"
    if design == DESIGN_B:
        if sku_prefix == DEV_PREFIX:
            return f"{DEV_PREFIX} is the A+ development market's prefix, which stays seeded"
        if out is not None and out.name == DEV_FIXTURE:
            return f"{DEV_FIXTURE} is the A+ development market's fixture, which stays seeded"
    if not claim:
        if seed not in DEV_SEEDS:
            return (f"seed {seed} is outside development's 900 to 999; the claim market is drawn "
                    f"with --claim, only after the protocol is final")
        return None
    if seed < CLAIM_FIRST_SEED:
        return f"seed {seed} is below {CLAIM_FIRST_SEED}, and --claim draws the claim market from it"
    if not protocol_final(protocol):
        return f"{protocol.name} still says DRAFT, and the claim market is drawn only once it is final"
    dev_prefix, dev_fixture = (B_DEV_PREFIX, B_DEV_FIXTURE) if design == DESIGN_B else (DEV_PREFIX, DEV_FIXTURE)
    if sku_prefix == dev_prefix:
        return f"{dev_prefix} is development's prefix"
    if out is not None and out.name == dev_fixture:
        return f"{dev_fixture} is development's fixture"
    return None


def claim_record_problem(tried: list[dict], seed: int, final: bool) -> str | None:
    """Why the claim search's record does not allow this seed, or None. The claim market is the
    first seed from 1000 that passes every rule, so the record holds every seed tried from
    1000 in order, each the one after the seed before unless that one stopped (the shop or the
    model was at fault, not the seed, so the same seed is tried again), and accepts none but
    its last. `final` asks whether the market may be written as the one accepted: the record
    must end with this seed accepted. Otherwise it asks whether this seed may be drawn as the
    next candidate: it must be the next the record allows."""
    expected = CLAIM_FIRST_SEED
    for n, entry in enumerate(tried):
        if entry.get("seed") != expected:
            return f"the record tries seed {entry.get('seed')} where seed {expected} comes next"
        if entry.get("outcome") == "accepted" and n != len(tried) - 1:
            return f"the record accepts seed {entry['seed']} and then tries more"
        expected = entry["seed"] if entry.get("outcome") == "stopped" else entry["seed"] + 1
    last = tried[-1] if tried else {}
    if final:
        if (last.get("seed"), last.get("outcome")) != (seed, "accepted"):
            return f"the record does not end with seed {seed} accepted"
        return None
    if last.get("outcome") == "accepted":
        return f"the record already ends with seed {last['seed']} accepted"
    if seed != expected:
        return f"seed {seed} is not the next seed the claim search may draw; {expected} is"
    return None


def claim_gate(seed: int, search_log: pathlib.Path | None, out: pathlib.Path | None,
               report: bool) -> tuple[str | None, bool]:
    """Under --claim, after `refused`: why this seed may not be drawn, written or printed, or
    None, and whether the record has accepted it (`final`). Which claim seed may be drawn is
    the record's to say, never the caller's (`claim_record_problem`), and a claim market is
    printed only once it is written and recorded as accepted, so no claim seed can be looked
    at before the search reaches it."""
    if search_log is None:
        return "--claim needs --search-log, the claim search's record", False
    tried = json.loads(search_log.read_text()).get("tried", []) if search_log.exists() else []
    last = tried[-1] if tried else {}
    final = (last.get("seed"), last.get("outcome")) == (seed, "accepted")
    problem = claim_record_problem(tried, seed, final)
    if problem:
        return problem, final
    if report and not (final and out is not None and out.exists()):
        return ("a claim market is printed only once it is written and recorded as accepted; "
                "name its fixture with --out"), final
    return None, final


def drawn_under(search_log: pathlib.Path | None, seed: int) -> int:
    """The version a market is drawn under (version 3): the one its seed search accepted it
    under, when the record ends with this seed accepted, so a market accepted before a rule
    came in is drawn again as it was (development's Larchmere, accepted under version 2);
    else this module's, for every new draw. The rules are kept by version for that
    (`RULES_SINCE`). The phrasing pools are not: a later version that changes a pool must
    keep the older one to draw again a market accepted under it, which no version has needed,
    since version 2 drew no claim market."""
    if search_log is None or not search_log.exists():
        return VERSION
    tried = json.loads(search_log.read_text()).get("tried") or []
    last = tried[-1] if tried else {}
    if (last.get("seed"), last.get("outcome")) != (seed, "accepted"):
        return VERSION
    version = last.get("generator_version", VERSION)
    if version > VERSION:
        raise SystemExit(f"refusing: {search_log.name} accepted seed {seed} under version {version}, "
                         f"later than this generator's {VERSION}")
    return version


def load_search(path: pathlib.Path, seed: int, brand: str, sku_prefix: str) -> dict:
    """A seed search's record, checked against the market it is said to have chosen."""
    search = json.loads(path.read_text())
    accepted = search["tried"][-1] if search.get("tried") else {}
    if (accepted.get("seed"), accepted.get("outcome")) != (seed, "accepted"):
        raise SystemExit(f"{path.name} does not end with seed {seed} accepted")
    if (search.get("brand"), search.get("sku_prefix")) != (brand, sku_prefix):
        raise SystemExit(f"{path.name} is the search for {search.get('brand')} "
                         f"{search.get('sku_prefix')}, not {brand} {sku_prefix}")
    return search


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--brand", required=True,
                        help="the word every listing's name starts with and the shop is searched for")
    parser.add_argument("--sku-prefix", default="IGR-DEV",
                        help="the listings' SKU prefix, and so their URL keys")
    parser.add_argument("--brand-forms", type=int, choices=(1, 2), required=True,
                        help="how many forms the shop's analyzer gives the brand: 2 when its stem "
                             "differs from it (env/pick_aplus_market.py --check-brands prints it)")
    parser.add_argument("--tees", type=int, default=TEE_LISTINGS)
    parser.add_argument("--waters", type=int, default=WATER_LISTINGS)
    parser.add_argument("--design", choices=(DESIGN_A, DESIGN_B), default=DESIGN_A,
                        help="A, the A+ market of tees and water (the default, as before); B, the "
                             "tee-only market of six sizes and misleading labels (version 4)")
    parser.add_argument("--listings", type=int, default=B_LISTINGS,
                        help="design B's number of listings, 45 by default; design A takes --tees and --waters")
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--search-log", type=pathlib.Path,
                        help="the seed search that chose this market, written by "
                             "env/pick_aplus_market.py, recorded in the fixture; required with "
                             "--claim, where it decides which seed may be drawn")
    parser.add_argument("--claim", action="store_true",
                        help="draw the claim market: the first seed from 1000 that passes, once "
                             "the protocol is final")
    parser.add_argument("--report", action="store_true", help="print the market and write nothing")
    args = parser.parse_args()
    design_b = args.design == DESIGN_B
    why = refused(args.seed, args.claim, args.out, args.sku_prefix, design=args.design)
    if why:
        raise SystemExit(f"refusing: {why}")
    if not args.report and args.out is None:
        parser.error("name --out, or ask for --report")
    two_forms = args.brand_forms == 2

    final = False
    if args.claim:
        problem, final = claim_gate(args.seed, args.search_log, args.out, args.report)
        if problem:
            raise SystemExit(f"refusing: {problem}")

    version = drawn_under(args.search_log, args.seed)
    if design_b:
        if version < 4:
            raise SystemExit(f"refusing: a design-B market is drawn under version 4 or later, not {version}")
        families, facts, attempts = generate_b(args.seed, args.brand, args.sku_prefix, two_forms,
                                               args.listings, claim=args.claim, version=version)
        shape = f"--design B --listings {args.listings}"
    else:
        families, facts, attempts = generate(args.seed, args.brand, args.sku_prefix, two_forms,
                                             args.tees, args.waters, claim=args.claim, version=version)
        shape = f"--tees {args.tees} --waters {args.waters}"
    search, command = None, None
    if args.search_log and (final or not args.claim):
        search = load_search(args.search_log, args.seed, args.brand, args.sku_prefix)
        log = args.search_log.resolve()
        log = log.relative_to(REPO) if log.is_relative_to(REPO) else log
        command = (f"python3 env/generate_aplus.py --seed {args.seed} --brand {args.brand} "
                   f"--brand-forms {args.brand_forms} --sku-prefix {args.sku_prefix} "
                   f"{shape} --out env/fixtures/{args.out.name} "
                   f"--search-log {log}" + (" --claim" if args.claim else ""))
    build, show = (to_fixture_b, report_b) if design_b else (to_fixture, report)
    fixture = build(families, facts, args.seed, attempts, args.brand, args.sku_prefix,
                    two_forms, args.claim, search, command, version)
    if args.report:
        if args.claim and json.loads(args.out.read_text())["families"] != families:
            raise SystemExit(f"refusing: {args.out.name} is not this seed's claim market")
        show(fixture)
        return 0
    # A claim candidate is written to be seeded and checked, never printed to look at.
    if not args.claim:
        show(fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2) + "\n")
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
