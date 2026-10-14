"""The scorer's rules, each on the answer that once broke it and on one it must leave alone.

A rule with only a passing case is not tested: it might pass everything. So every rule here
has a case where it must fire and a case where it must stay quiet (LESSONS.md, 1 and 24).
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401
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

    def test_an_answer_is_unscored_and_a_failed_run_still_fails(self):
        self.assertEqual(verdict({"kind": "none"}, "Lisbon."), "unscored")
        self.assertEqual(verdict({"kind": "none"}, "I could not determine this."), "unscored")
        self.assertEqual(score.score({"expect": {"kind": "none"}}, "", False)["verdict"], "failed")
        # Any other kind is still judged.
        self.assertEqual(verdict({"kind": "contains", "any": ["Lisbon"]}, "Lisbon."), "correct")


class Abstention(unittest.TestCase):
    def test_the_gate_refusal_scores_as_abstained(self):
        # policy.py words its refusal so the scorer can see it. If either side changes,
        # refusals would be scored as wrong answers and hide the effect being measured.
        refusal = policy.abstention_for({"why": "two of the fifteen listings were never opened"})
        self.assertEqual(verdict({"kind": "count", "value": 5}, refusal), "abstained")

    def test_a_plain_answer_is_not_an_abstention(self):
        self.assertFalse(score.abstained("The cheapest size M is $12.40 from Hollis & Vane."))


if __name__ == "__main__":
    unittest.main()
