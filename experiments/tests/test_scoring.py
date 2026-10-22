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
        ):
            with self.subTest(answer=answer[:50]):
                self.assertEqual(verdict(self.TOP3, answer), "correct")

    def test_a_wrong_order_a_missing_seller_and_a_wrong_price_fire(self):
        cases = {
            "Mellow Fields $13.15, Harbour Lane $12.15, Quiet Oak $14.15.": "wrong",
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
        self.assertEqual(score.VERSION, 6)


if __name__ == "__main__":
    unittest.main()
