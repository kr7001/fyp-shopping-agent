"""The scorer's rules, each on the answer that once broke it and on one it must leave alone.

A rule with only a passing case is not tested: it might pass everything. So every rule here
has a case where it must fire and a case where it must stay quiet (LESSONS.md, 1 and 24).
"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import policy  # noqa: E402
import score  # noqa: E402


def verdict(expect: dict, answer: str) -> str:
    return score.score({"expect": expect}, answer, True)["verdict"]


class CountRule(unittest.TestCase):
    """LESSONS 4: a number saying how many listings were looked at is not the count."""

    def test_number_of_listings_checked_is_skipped(self):
        answer = "After checking all 15 listings, I found that 5 products have size M."
        self.assertEqual(verdict({"kind": "count", "value": 5}, answer), "correct")
        self.assertEqual(verdict({"kind": "count", "value": 15}, answer), "wrong")

    def test_a_lone_coverage_number_is_still_the_count(self):
        self.assertEqual(verdict({"kind": "count", "value": 15}, "All 15 listings offer it."),
                         "correct")

    def test_digits_inside_a_price_are_not_a_count(self):
        # The price comes first on purpose. With it last, a scorer that read a price's digits
        # as the count would still meet the 3 first and pass, so the test could not fail.
        # Found on 9 Oct 2026 by removing the exclusion and running the tests again.
        answer = "The cheapest is $12.50, and 3 listings have it."
        self.assertEqual(verdict({"kind": "count", "value": 3}, answer), "correct")


class PriceRule(unittest.TestCase):
    EXPECT = {"kind": "price", "value": 22.50, "trap": 10.90}

    def test_working_that_resolves_to_the_price_is_correct(self):
        answer = "$22.50 (base $10.90 + charge $11.60)"
        self.assertEqual(verdict(self.EXPECT, answer), "correct")

    def test_the_trap_price_alone_is_wrong(self):
        self.assertEqual(verdict(self.EXPECT, "It costs $10.90."), "wrong")

    def test_both_prices_unresolved_is_ambiguous(self):
        self.assertEqual(verdict(self.EXPECT, "It is either $22.50 or $10.90."), "ambiguous")


class BooleanRule(unittest.TestCase):
    def test_not_available_reads_as_no(self):
        # "not available" contains "available", so the negative is checked first.
        answer = "Size M is not available in that listing."
        self.assertEqual(verdict({"kind": "boolean", "value": False}, answer), "correct")
        self.assertEqual(verdict({"kind": "boolean", "value": True}, answer), "wrong")

    def test_a_leading_yes_decides(self):
        answer = "Yes, every listing has it, though one is not available in black."
        self.assertEqual(verdict({"kind": "boolean", "value": True}, answer), "correct")

    def test_a_yes_that_must_name_its_witness(self):
        # "Name the seller if yes" (the box v2 batch, 14 Oct 2026): the witness named is
        # correct, an excluded seller instead is wrong, nobody named is unfinished.
        expect = {"kind": "boolean", "value": True, "any": ["Harbour"], "not_any": ["Quiet"]}
        self.assertEqual(verdict(expect, "Yes. Harbour Lane has size M at $12.15."), "correct")
        self.assertEqual(verdict(expect, "Yes, Quiet Oak at $9.15, though its M is sold out."), "wrong")
        self.assertEqual(verdict(expect, "Yes."), "ambiguous")
        # A no is judged as before, whoever it names, and so is a key without names.
        self.assertEqual(verdict(expect, "No. Quiet Oak is the cheapest and is sold out."), "wrong")
        self.assertEqual(verdict({**expect, "value": False}, "No. Quiet Oak is sold out."), "correct")
        self.assertEqual(verdict({"kind": "boolean", "value": True}, "Yes."), "correct")


class RankedRule(unittest.TestCase):
    """The ranked kind (14 Oct 2026): k sellers in order, each with its own price."""

    TOP3 = {"kind": "ranked", "items": [{"any": ["Harbour Lane"], "price": 12.15},
                                        {"any": ["Mellow Fields"], "price": 13.15},
                                        {"any": ["Quiet Oak"], "price": 14.15}]}
    PAIR = {"kind": "ranked", "items": [{"any": ["Mellow Fields"], "price": 13.15},
                                        {"any": ["Harbour Lane"], "price": 15.15, "optional": True}]}

    def test_the_right_ranking_in_different_wordings(self):
        for answer in (
            "1. Harbour Lane at $12.15, 2. Mellow Fields at $13.15, 3. Quiet Oak at $14.15. "
            "I opened six listings and checked M was available in each.",
            "The three cheapest are Harbour Lane ($12.15), Mellow Fields ($13.15) and Quiet Oak "
            "($14.15); I skipped nine listings advertised at or above $14.15.",
            "$12.15 from Harbour Lane, $13.15 from Mellow Fields, $14.15 from Quiet Oak.",
            # The listings opened are narrated first, in another order; the ranking decides.
            "I opened Quiet Oak, Mellow Fields, Harbour Lane and three others. Cheapest "
            "three with M available: Harbour Lane $12.15, Mellow Fields $13.15, Quiet Oak $14.15.",
            "Harbour Lane\n$12.15\nMellow Fields\n$13.15\nQuiet Oak\n$14.15",
            # In another order (score v7): the template asks which three, not in what order.
            # Planted: the order check restored, this was wrong.
            "Mellow Fields $13.15, Harbour Lane $12.15, Quiet Oak $14.15.",
            "The three cheapest are Quiet Oak ($14.15), Mellow Fields ($13.15) and Harbour Lane ($12.15).",
        ):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.TOP3, answer), "correct")

    def test_a_missing_seller_and_a_wrong_price_fire(self):
        cases = {
            "Harbour Lane $12.15 and Quiet Oak $14.15.": "wrong",
            "Harbour Lane $12.15, Mellow Fields $11.15, Quiet Oak $14.15.": "wrong",
            # Two sellers' prices swapped, and a neighbour's price given for a seller's own.
            "Harbour Lane $13.15, Mellow Fields $12.15, Quiet Oak $14.15.": "wrong",
            "Harbour Lane $12.15, Mellow Fields, Quiet Oak $14.15.": "wrong",
            # The right sellers in the right order and no prices at all: unfinished.
            "Harbour Lane, Mellow Fields, Quiet Oak.": "ambiguous",
        }
        for answer, expected in cases.items():
            with self.subTest(answer=answer):
                self.assertEqual(verdict(self.TOP3, answer), expected)

    def test_a_comparison_holds_the_optional_loser_to_its_own_price(self):
        for answer in ("Mellow Fields is cheaper for size M, at $13.15.",
                       "Between Harbour Lane and Mellow Fields, Mellow Fields is cheaper at "
                       "$13.15; Harbour Lane charges $15.15 for M.",
                       "Mellow Fields: $13.15. Harbour Lane: $15.15. So Mellow Fields."):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.PAIR, answer), "correct")
        # The loser quoted at its advertised price, which the results page shows and the
        # size menu does not, and the winner never named.
        self.assertEqual(verdict(self.PAIR, "Harbour Lane is cheaper at $10.15 versus Mellow "
                                            "Fields at $13.15."), "wrong")
        self.assertEqual(verdict(self.PAIR, "Harbour Lane, at $10.15."), "wrong")


class NoKey(unittest.TestCase):
    """The none kind (14 Oct 2026): a question the box is expected to ask on, refuse or
    bypass has no key, and an answer to it is unscored rather than wrong or abstained."""

    def test_an_answer_is_unscored_and_so_is_a_run_that_did_not_finish(self):
        self.assertEqual(verdict({"kind": "none"}, "Lisbon."), "unscored")
        self.assertEqual(verdict({"kind": "none"}, "I could not determine this."), "unscored")
        # A keyless run that ended without ok has no key to fail against either. Until
        # 20 Oct 2026 (scorer v3) it was "failed", and verify_cells counted it as a wrong
        # control answer (verifier finding on 20261014T220116, apparel-softest-1).
        self.assertEqual(score.score({"expect": {"kind": "none"}}, "", False)["verdict"], "unscored")
        self.assertEqual(score.score({"expect": {"kind": "none"}}, "No softness found.", False)["verdict"],
                         "unscored")
        # Any other kind is still judged, and still fails without an answer.
        self.assertEqual(verdict({"kind": "contains", "any": ["Lisbon"]}, "Lisbon."), "correct")
        self.assertEqual(score.score({"expect": {"kind": "contains", "any": ["Lisbon"]}}, "", False)["verdict"],
                         "failed")


class Abstention(unittest.TestCase):
    def test_the_gate_refusal_scores_as_abstained(self):
        # policy.py words its refusal so the scorer can see it. If either side changes,
        # refusals would be scored as wrong answers and hide the effect being measured.
        refusal = policy.abstention_for({"why": "two of the fifteen listings were never opened"})
        self.assertEqual(verdict({"kind": "count", "value": 5}, refusal), "abstained")

    def test_a_plain_answer_is_not_an_abstention(self):
        self.assertFalse(score.abstained("The cheapest size M is $12.40 from Hollis & Vane."))


class VariantLabels(unittest.TestCase):
    """Score v5, 22 October 2026: a variant's own label is never a price or a count. The water
    of the second claim market is sold by the pack, and its labels hold figures."""

    def test_a_pack_is_not_a_count(self):
        # Planted: `without_labels` returning the answer as it is, the count read was 2.
        self.assertEqual(verdict({"kind": "count", "value": 9}, "The 2 x 9.5L pack is in stock at 9 listings."),
                         "correct")
        self.assertEqual(verdict({"kind": "count", "value": 3}, "24 x 350ml: 3 listings can sell it now."),
                         "correct")
        # Quiet: a count with no label, and one after a coverage number, as before.
        self.assertEqual(verdict({"kind": "count", "value": 9}, "9 listings have the pack."), "correct")
        self.assertEqual(verdict({"kind": "count", "value": 2}, "Of the 21 listings, 2 stock it."), "correct")

    def test_a_volume_is_not_a_price(self):
        # Planted: the same, 1.25 was read as a price.
        self.assertEqual(score.prices_in("The 6 x 1.25L pack is $6.84."), [6.84])
        for written in ("6 x 1.25L", "6x1.25L", "6 × 1.25 L", "6 X 1.25l", "1.25L", "1.25 L", "1.25 litres",
                        "1.25-litre", "350 ml", "12 x 550ml"):
            with self.subTest(label=written):
                self.assertEqual(score.prices_in(f"{written} at $6.84, not $7.10"), [6.84, 7.10])
        # Quiet: money is still money, and a count of size L is no volume.
        self.assertEqual(score.prices_in("$12.50 and 9.99"), [12.50, 9.99])
        self.assertEqual(verdict({"kind": "count", "value": 3}, "3 L tees are left, and 12.50 is the price."),
                         "correct")

    def test_every_water_question_of_the_development_market(self):
        # One right and one wrong answer to each, written with the packs' labels from the
        # task file's own keys, so they follow the market when it is drawn again. Each
        # wrong one is wrong for the reason its key gives.
        spec = json.loads((paths.TASKS / "tasks_aplus_dev.json").read_text())
        keys = {task["id"]: task for task in spec["tasks"] if task["id"].startswith("water-")}

        def expect(task_id: str) -> dict:
            return keys[task_id]["expect"]

        price, cheapest, every = expect("water-target-price"), expect("water-cheapest-target"), \
            expect("water-all-stocked")
        count, litre = expect("water-count-buyable"), expect("water-best-per-litre")
        winner, loser = litre["any"][0], litre["not_any"][-1]
        answers = {
            "water-target-price": (f"The lowest price for the 2 x 9.5L pack that can be bought is "
                                   f"${price['value']:.2f}; the 6 x 1.25L pack is not the one asked about.",
                                   f"The cheapest pack is the 6 x 1.25L at ${price['trap']:.2f}."),
            "water-cheapest-target": (f"{cheapest['any'][0]} is the cheapest for the 2 x 9.5L pack, at "
                                      f"${cheapest['price']:.2f}.",
                                      f"{cheapest['not_any'][0]} is the cheapest for the 2 x 9.5L pack."),
            "water-all-stocked": ("No. Some water listings have no 2 x 9.5L pack in their menu."
                                  if not every["value"] else "Yes, every listing stocks the 2 x 9.5L pack.",
                                  "Yes, every listing lists the 2 x 9.5L pack." if not every["value"]
                                  else "No. Some water listings have no 2 x 9.5L pack."),
            "water-count-buyable": (f"The 2 x 9.5L pack is in stock and can be bought at {count['value']} listings.",
                                    f"The 2 x 9.5L pack is in stock at {count['value'] + 4} listings."),
            "water-best-per-litre": (f"{winner}'s 6 x 1.25L pack has the lowest price per litre; {loser}'s "
                                     f"2 x 9.5L is close behind.",
                                     f"{loser}'s 2 x 9.5L pack is the best value per litre; {winner}'s "
                                     f"6 x 1.25L is close behind."),
        }
        self.assertEqual(sorted(answers), sorted(keys))
        for task_id, (right, wrong) in answers.items():
            with self.subTest(task=task_id):
                self.assertEqual(score.score(keys[task_id], right, True)["verdict"], "correct")
                self.assertEqual(score.score(keys[task_id], wrong, True)["verdict"], "wrong")
        # The count's right answer was 2 until score v5, its pack's figure.
        self.assertEqual(score.without_labels("The 2 x 9.5L pack")[:4], "The ")


class NamedBest(unittest.TestCase):
    """Score v6, 22 October 2026: an answer naming both the expected option and an excluded
    one is held to the one it says is the best."""
    PER_LITRE = {"kind": "contains", "any": ["Ambleside"], "not_any": ["Pembroke", "Chandler"]}

    def test_the_best_named_decides_where_both_are_named(self):
        # The verifier's case. Planted: `named_best` never consulted, it was correct.
        self.assertEqual(verdict(self.PER_LITRE, "Chandler Direct's 2 x 9.5L is the best value; Ambleside's "
                                                 "6 x 1.25L is close behind."), "wrong")
        for answer in ("Ambleside offers the lowest price per litre; Chandler Direct is second.",
                       "I opened all 21. Pembroke: $1.20/L, Chandler: $0.93/L, Ambleside: $0.91/L. "
                       "Ambleside is the cheapest per litre.",
                       "Chandler at $0.93/L is beaten by Ambleside, the best at $0.91/L."):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.PER_LITRE, answer), "correct")

    def test_the_first_claim_of_a_best_decides(self):
        # The answer's conclusion, then a claim about something else. Planted: the last
        # claim deciding, this was wrong.
        answer = ("Ambleside has the lowest price per litre, $0.91/L. Chandler Direct has the best price "
                  "for the 2 x 9.5L pack itself.")
        self.assertEqual(score.named_best(answer, ["Ambleside"], ["Chandler"]), "wanted")
        self.assertEqual(verdict(self.PER_LITRE, answer), "correct")

    def test_one_side_named_is_scored_as_before(self):
        self.assertEqual(verdict(self.PER_LITRE, "Ambleside, at $0.91 per litre."), "correct")
        self.assertEqual(verdict(self.PER_LITRE, "Chandler Direct is the best value."), "wrong")
        # Naming both with no claim of a best is read as before: the expected one is named.
        self.assertEqual(verdict(self.PER_LITRE, "Ambleside $0.91/L, Chandler $0.93/L."), "correct")
        self.assertIsNone(score.named_best("Ambleside $0.91/L, Chandler $0.93/L.", ["Ambleside"], ["Chandler"]))

    def test_the_stored_answer_it_changes(self):
        # The one stored verdict v6 moves (20260914T034338 scaled-cheapest-target-2): it named
        # Hillside the cheapest and the key, Redhill, only in a note.
        answer = ("The cheapest seller for the 2 x 9.5L Rivenhall pack is Hillside Wholesale at $19.26 (base "
                  "price $6.44 + pack surcharge $12.82). Note: Redhill Stores offers $17.68, but Hillside "
                  "Wholesale at $19.26 represents the best overall value.")
        expect = {"kind": "contains", "any": ["Redhill"], "not_any": ["Hillside"]}
        self.assertEqual(verdict(expect, answer), "wrong")


# The A+ development market's facts the audit's answers below are written from: who sells
# what at which price. Pinned so that a redrawn market fails here, by name, rather than as a
# misscore (the market is development's, Larchmere, seed 900).
LARCHMERE = {"tee-target-price": {"kind": "price", "value": 19.17},
             "water-target-price": {"kind": "price", "value": 20.3, "trap": 6.93},
             "tee-top-3": [("Elmsworth", 19.17), ("Everleigh", 21.54), ("Bexhill", 21.71)]}

# The verifier's fairness audit of 23 October 2026, its three batteries of synthetic answers
# word for word, each with what it is: every one a reader would judge right or wrong at a
# glance. Under v6, 21 of the 51 were misscored.
AUDIT = [
    ("tee-headline", "right", "Brindle Clothing Co advertises the lowest price, $14.18."),
    ("tee-headline", "wrong", "Haldane Garment Works is the cheapest at $17.97; Brindle Clothing Co shows $14.18 further down."),
    ("tee-target-price", "right", "The lowest price for size M that can be bought is $19.17 (Elmsworth Apparel)."),
    ("tee-target-price", "wrong", "The lowest is $16.62 at Lymington Uniform Supply. Elmsworth Apparel charges $19.17 and Everleigh $21.54."),
    ("tee-target-price", "wrong", "Lowest buyable M: Haldane Garment Works at $17.97. I also saw Elmsworth at $19.17."),
    ("tee-cheapest-target", "right", "Elmsworth Apparel is cheapest at $19.17. Lymington lists M at $16.62 but it is sold out."),
    ("tee-cheapest-target", "right", "Lymington Uniform Supply has the lowest listed M at $16.62, but it is sold out, so the cheapest that can supply it is Elmsworth Apparel at $19.17."),
    ("tee-cheapest-target", "wrong", "Haldane Garment Works is the cheapest for size M at $17.97. Elmsworth Apparel is next at $19.17."),
    ("tee-count-stocked", "right", "17 of the 21 tee listings offer size M."),
    ("tee-count-stocked", "right", "There are 21 Larchmere tee listings, and 17 of them offer size M."),
    ("tee-count-stocked", "right", "Across the 2 results pages, 17 tee listings offer size M."),
    ("tee-count-stocked", "right", "The search shows 42 listings on 2 pages; 21 are tees. 17 of them offer size M."),
    ("tee-count-buyable", "right", "I opened 21 tee listings. 11 have size M in stock."),
    ("tee-count-buyable", "right", "21 tee listings checked: 11 have size M available to buy, 6 list it sold out and 4 do not offer it."),
    ("tee-count-buyable", "wrong", "6 of the tee listings have M sold out, so 15 can sell it."),
    ("tee-exists-under", "right", "Yes. Elmsworth Apparel sells size M for $19.17. Brindle advertises $14.18 but has no M."),
    ("tee-exists-under", "wrong", "Yes, Haldane Garment Works at $17.97."),
    ("tee-top-3", "right", "1. Elmsworth Apparel $19.17 2. Everleigh Threads $21.54 3. Bexhill Textiles Official Store $21.71"),
    ("tee-top-3", "right", "The three cheapest are Bexhill Textiles Official Store ($21.71), Everleigh Threads ($21.54) and Elmsworth Apparel ($19.17)."),
    ("tee-top-3", "right", "Everleigh Threads at $21.54, Elmsworth Apparel at $19.17 and Bexhill Textiles Official Store at $21.71 are the three cheapest that can supply M."),
    ("water-target-price", "right", "The lowest buyable 2 x 9.5L is $20.30, from Dalston Trading Company."),
    ("water-target-price", "right", "Oakfield's $6.93 card is for a smaller pack; the lowest 2 x 9.5L that can be bought is $20.30 at Dalston Trading Company."),
    ("water-target-price", "wrong", "The lowest 2 x 9.5L is $17.44 at Westmere. Dalston charges $20.30."),
    ("water-cheapest-target", "right", "Dalston Trading Company, $20.30 for the 2 x 9.5L pack."),
    ("water-cheapest-target", "right", "Westmere Beverage Supply Co has the lowest listed 2 x 9.5L at $17.44 but it is sold out, so the cheapest that can supply it is Dalston Trading Company at $20.30."),
    ("water-cheapest-target", "wrong", "Ashgrove Provisions is cheapest for the 2 x 9.5L at $8.71. Dalston is $20.30."),
    ("water-count-buyable", "right", "13 water listings have the 2 x 9.5L pack in stock."),
    ("water-count-buyable", "right", "The 2 x 9.5-litre pack is in stock at 13 of the 21 water listings."),
    ("water-count-buyable", "right", "The 2-pack (2 x 9.5L) is buyable at 13 listings."),
    ("water-count-buyable", "right", "2 x 9.5 litres: 13 listings can sell it now."),
    ("water-best-per-litre", "right", "Crowhurst Pantry Stores, about $0.95 a litre for its 24 x 350ml at $7.94."),
    ("water-best-per-litre", "right", "Westmere's 2 x 9.5L is the lowest per litre at $0.92 but it is sold out; among packs that can be bought, Crowhurst Pantry Stores is best at $0.95 a litre."),
    ("water-best-per-litre", "wrong", "Ashgrove Provisions offers the best price per litre. Crowhurst is a close second."),
    ("water-all-stocked", "right", "No. Fenwick Beverage Supply does not offer the 2 x 9.5L pack."),
    ("tee-all-stocked", "right", "Not every listing does: Brindle Clothing Co has no size M. So no."),
    ("tee-count-buyable", "right", "I opened all 21 tee listings (20 on page 1 and 1 on page 2). 11 have size M in stock and available to buy."),
    ("tee-count-buyable", "right", "11 tee listings have size M in stock and available to buy right now. I opened all 21 tee listings across both results pages."),
    ("tee-count-buyable", "right", "I opened every tee listing on pages 1 and 2: 11 can sell size M now."),
    ("water-count-buyable", "right", "I opened all 21 water listings across the 2 results pages; 13 have the 2 x 9.5L pack in stock."),
    ("water-count-buyable", "right", "Page 2 held 5 of the water listings. In total 13 have the 2 x 9.5L pack in stock."),
    ("tee-count-stocked", "right", "I opened all 21 tee listings. 17 offer size M (11 in stock, 6 sold out)."),
    ("tee-all-stocked", "wrong", "Yes, every Larchmere tee listing offers size M."),
    ("tee-all-stocked", "right", "Actually, no: Brindle Clothing Co has no size M."),
    ("water-all-stocked", "wrong", "Yes. All 21 water listings have the 2 x 9.5L option in their menu."),
    ("water-all-stocked", "right", "No - Fenwick Beverage Supply has no 2 x 9.5L pack (the 2 x 9.5L is available elsewhere)."),
    ("tee-count-stocked", "wrong", "11 tee listings offer size M."),
    ("water-count-buyable", "wrong", "17 water listings have the 2 x 9.5L pack."),
    ("tee-exists-under", "wrong", "No, no tee listing sells size M under $20."),
    ("tee-top-3", "wrong", "1. Lymington Uniform Supply $16.62 2. Elmsworth Apparel $19.17 3. Everleigh Threads $21.54"),
    ("tee-top-3", "wrong", "1. Elmsworth Apparel $19.17 2. Everleigh Threads $21.54 3. Bexhill Textiles Official Store $16.75"),
    ("water-best-per-litre", "wrong", "Westmere Beverage Supply Co, at $0.92 a litre for the 2 x 9.5L."),
]
# The four that only the market's sellers decide: each names a winner the key never excluded.
NEEDS_THE_MARKET = {2, 8, 26, 33}      # 1-based positions in AUDIT


class TheAudit(unittest.TestCase):
    """Score v7 on the verifier's audit of 23 October 2026: every answer judged as a reader
    would, with the market's sellers; without them, only the four that need them are not."""

    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((paths.TASKS / "tasks_aplus_dev.json").read_text())
        cls.tasks = {task["id"]: task for task in cls.spec["tasks"]}
        cls.sellers = score.market_sellers(cls.spec)

    def test_the_market_the_answers_are_written_from(self):
        for task_id in ("tee-target-price", "water-target-price"):
            self.assertEqual(self.tasks[task_id]["expect"], LARCHMERE[task_id])
        self.assertEqual([(item["any"][0], item["price"]) for item in self.tasks["tee-top-3"]["expect"]["items"]],
                         LARCHMERE["tee-top-3"])
        self.assertEqual(len(self.sellers), 42)
        for name in ("Haldane Garment Works", "Ashgrove Provisions", "Lymington Uniform Supply"):
            self.assertIn(name, self.sellers)

    def test_every_answer_with_the_market(self):
        for n, (task_id, truth, answer) in enumerate(AUDIT, 1):
            with self.subTest(case=n, answer=answer[:60]):
                got = score.score(self.tasks[task_id], answer, True, self.sellers)["verdict"]
                self.assertEqual(got == "correct", truth == "right", got)

    def test_without_the_market_only_the_four_that_need_it_differ(self):
        wrong = [n for n, (task_id, truth, answer) in enumerate(AUDIT, 1)
                 if (score.score(self.tasks[task_id], answer, True)["verdict"] == "correct") != (truth == "right")]
        self.assertEqual(set(wrong), NEEDS_THE_MARKET)
        self.assertEqual(score.VERSION, 7)


class CountCoverage(unittest.TestCase):
    """Score v7: a page's number and a statement of the market's size are coverage."""
    COUNT = {"kind": "count", "value": 11}

    def test_page_numbers_are_not_the_count(self):
        # Planted: `PAGE_NUMBERS` matching nothing, these read 20, 1, 2 and 5.
        for answer in ("I opened all 21 tee listings (20 on page 1 and 1 on page 2). 11 have size M.",
                       "I opened every tee listing on pages 1 and 2: 11 can sell size M now.",
                       "Page 1 of 2 showed most of them; 11 can sell size M.",
                       "Page 2 held 5 of the tee listings. In total 11 have size M in stock.",
                       "Across the 2 results pages, 11 tee listings have size M."):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.COUNT, answer), "correct")

    def test_the_markets_size_is_not_the_count(self):
        # Planted: `MARKET_SIZE` matching nothing, these read 21 or 42.
        for answer in ("There are 21 Larchmere tee listings, and 11 of them have size M in stock.",
                       "The search shows 42 listings on 2 pages; 21 are tees. 11 of them have size M.",
                       "21 tee listings checked: 11 have size M available to buy, 6 list it sold out.",
                       "The search returned 42 results. 11 tee listings have M in stock."):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.COUNT, answer), "correct")

    def test_a_count_that_looks_like_them_is_still_the_count(self):
        # Quiet: a stored answer (20261020T223345, count-buyable) where "There are 8" is the
        # count, with what it counts after it, and the same with a second number after it,
        # which a rule that set the 8 aside would read instead (the stored answer alone falls
        # back to its only number, so it could not show that fault); a count followed by its
        # pages; a number that stands alone; and a page number in a different sentence.
        self.assertEqual(verdict({"kind": "count", "value": 8},
                                 "There are 8 Ashcombe listings with size M in stock and available to buy right now."),
                         "correct")
        self.assertEqual(verdict({"kind": "count", "value": 8},
                                 "There are 8 Ashcombe listings with size M in stock; 7 more list it sold out."),
                         "correct")
        self.assertEqual(verdict(self.COUNT, "11 listings have size M: 9 on page 1 and 2 on page 2."), "correct")
        self.assertEqual(verdict(self.COUNT, "11"), "correct")
        self.assertEqual(verdict(self.COUNT, "On page 2, 11 more listings have it."), "correct")
        self.assertEqual(verdict({"kind": "count", "value": 15}, "All 15 listings offer it."), "correct")

    def test_a_pack_named_two_more_ways(self):
        # Planted: `PACK_LABEL` matching nothing, both read 2.
        for answer in ("The 2 x 9.5-litre pack is in stock at 13 of the 21 water listings.",
                       "The 2-pack (2 x 9.5L) is buyable at 13 listings."):
            with self.subTest(answer=answer[:40]):
                self.assertEqual(verdict({"kind": "count", "value": 13}, answer), "correct")
        # Quiet, and the label leaves the prices alone: `prices_in` reads them as before.
        self.assertEqual(score.prices_in("The 2-pack is $20.30; the 2 x 9.5-litre is $21.00."), [20.30, 21.00])

    def test_a_lists_numbering_is_not_the_count(self):
        # Planted: `ENUMERATOR` matching nothing, the stored answer of 20260918T105704
        # count-stocked-3 read 1; it says 4, its market's size as the agent saw it.
        answer = ("All 4 Thornwood listings offer size M. The listings are: (1) Thornwood Heavyweight Cotton "
                  "Tee - Quarles Supply, (2) Thornwood Heavyweight Cotton Tee - Elmsworth Collective.")
        self.assertEqual(score.score({"expect": {"kind": "count", "value": 4}}, answer, True)["why"], "counted 4")
        # Quiet: a count in parentheses that numbers nothing.
        self.assertEqual(verdict({"kind": "count", "value": 17}, "Listings offering M (17): every one but four."),
                         "correct")


class PriceAsAnswer(unittest.TestCase):
    """Score v7: the price kind judges the price the answer gives as its answer."""
    WATER = {"kind": "price", "value": 20.30, "trap": 6.93}

    def test_another_price_named_beside_the_answer_does_not_decide(self):
        # Planted: `answer_price` returning None, the first was ambiguous and the others correct.
        self.assertEqual(verdict(self.WATER, "Oakfield's $6.93 card is for a smaller pack; the lowest 2 x 9.5L "
                                             "that can be bought is $20.30 at Dalston Trading Company."), "correct")
        self.assertEqual(verdict(self.WATER, "The lowest 2 x 9.5L is $17.44 at Westmere. Dalston charges $20.30."),
                         "wrong")
        self.assertEqual(verdict({"kind": "price", "value": 19.17},
                                 "Lowest buyable M: Haldane Garment Works at $17.97. I also saw Elmsworth at $19.17."),
                         "wrong")

    def test_the_trap_given_as_the_answer(self):
        got = score.score({"expect": self.WATER}, "The lowest 2 x 9.5L is $6.93.", True)
        self.assertEqual((got["verdict"], got["why"]), ("wrong", "gave the trap price 6.93 as its answer"))

    def test_working_resolves_to_its_total(self):
        # Quiet: the stored kind of answer that shows Magento's surcharge, in the claim's
        # sentence, with the total first or last.
        expect = {"kind": "price", "value": 22.50, "trap": 10.90}
        self.assertEqual(verdict(expect, "The lowest is $22.50 (base $10.90 + charge $11.60)."), "correct")
        self.assertEqual(verdict(expect, "The lowest, $10.90 base + $11.60 for the pack, comes to $22.50."),
                         "correct")
        self.assertEqual(score.answer_price("The cheapest, $10.90 + $11.60, is $22.50."), 22.50)

    def test_price_spans_reads_the_prices_prices_in_reads(self):
        for text in ("6 x 1.25L at $6.84, not $7.10", "$12.50 and 9.99", "The 2-pack is $20.30.",
                     "base $10.90 + $11.60 = $22.50", "24x350ml $7.94; 12 x 550ml $8.10", "no price here"):
            with self.subTest(text=text):
                self.assertEqual([value for _, _, value in score.price_spans(text)], score.prices_in(text))

    def test_an_answer_that_claims_no_lowest_is_read_as_before(self):
        # Quiet: no claim of a lowest, so the v6 rule: the key's price present, the trap
        # resolved by working or not.
        self.assertIsNone(score.answer_price("The price of the 2 x 9.5L pack is $22.50 (base $10.90 + $11.60)."))
        self.assertEqual(verdict({"kind": "price", "value": 22.50, "trap": 10.90},
                                 "The price of the 2 x 9.5L pack is $22.50 (base $10.90 + $11.60)."), "correct")
        self.assertEqual(verdict({"kind": "price", "value": 22.50, "trap": 10.90}, "It is either $22.50 or $10.90."),
                         "ambiguous")


class TakenBack(unittest.TestCase):
    """Score v7: a claim of a best that its sentence takes back names nothing."""
    CHEAPEST = {"kind": "contains", "any": ["Elmsworth"], "not_any": ["Brindle", "Lymington"], "price": 19.17}

    def test_a_sold_out_lowest_set_aside_in_the_same_sentence(self):
        # Planted: `taken_back` returning False, each was wrong (Lymington named the best) or
        # gave 16.62 as its answer.
        for answer in ("Lymington Uniform Supply has the lowest listed M at $16.62, but it is sold out, so the "
                       "cheapest that can supply it is Elmsworth Apparel at $19.17.",
                       "Lymington's M is the lowest listed, $16.62, which cannot be bought; the cheapest that "
                       "can is Elmsworth Apparel at $19.17.",
                       "Brindle Clothing Co advertises the lowest price, $14.18, but has no M, so Elmsworth "
                       "Apparel is the cheapest at $19.17."):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.CHEAPEST, answer), "correct")
        self.assertEqual(score.answer_price("The lowest listed M is $16.62 but it is sold out, so the cheapest "
                                            "that can be bought is $19.17."), 19.17)

    def test_a_rejection_of_another_listing_or_a_negated_one_takes_nothing_back(self):
        # Quiet: the rejection is about the listing named after the claim's, or negated.
        for answer, side in (
                ("Lymington is the cheapest at $16.62, since Elmsworth's M is sold out.", "excluded"),
                ("Lymington is the cheapest at $16.62 and is not sold out.", "excluded"),
                ("Lymington is the cheapest, its M not disabled/sold out.", "excluded"),
                ("Elmsworth Apparel is the cheapest at $19.17, since Lymington's M is sold out.", "wanted")):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(score.named_best(answer, ["Elmsworth"], ["Lymington"]), side)
        self.assertEqual(verdict(self.CHEAPEST, "Lymington is the cheapest at $16.62, since Elmsworth's M is sold "
                                                "out."), "wrong")


class MarketSellers(unittest.TestCase):
    """Score v7: a best is judged against every seller of the market, read from the fixture a
    task file names, and only when it names one."""

    def test_the_market_a_task_file_names(self):
        aplus = json.loads((paths.TASKS / "tasks_aplus_dev.json").read_text())
        fixture = json.loads((paths.FIXTURES / "aplus_dev.json").read_text())
        self.assertEqual(score.market_sellers(aplus), [f["seller"] for f in fixture["families"]])
        # Quiet: a file that names no fixture, Thornwood's, is scored as before.
        self.assertIsNone(score.market_sellers(json.loads((paths.TASKS / "tasks_apparel.json").read_text())))
        # Fires: a fixture that is not the file's own market is refused.
        with self.assertRaises(ValueError):
            score.market_sellers({**aplus, "_instance": {"market": "another"}})

    def test_the_wanted_seller_and_sellers_it_cannot_be_told_from_are_left_out(self):
        sellers = ["Elmsworth Apparel", "Haldane Garment Works", "Haldane Supply", "Elm Threads", "Ashgrove Provisions"]
        # Haldane is shared, so neither is told apart by it; "elm" is inside the wanted token.
        self.assertEqual(score.other_sellers(sellers, ["Elmsworth"]), ["ashgrove"])
        expect = {"kind": "contains", "any": ["Elmsworth"], "not_any": []}
        answer = "Ashgrove Provisions is the cheapest at $8.71; Elmsworth Apparel charges $19.17."
        self.assertEqual(score.score({"expect": expect}, answer, True, sellers)["verdict"], "wrong")
        self.assertEqual(score.score({"expect": expect}, answer, True)["verdict"], "correct")


if __name__ == "__main__":
    unittest.main()
