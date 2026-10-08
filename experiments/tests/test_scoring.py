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
        answer = "3 listings have it, the cheapest at $12.50."
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
