"""The clothing-cell figures the site reports, recomputed from the raw runs.

A change here is a change to a published result. If a scorer or checker fix moves one of
these numbers, update this file, regenerate the site (`make site`) and add a dated entry to
the README decision log in the same commit, so the change is visible rather than silent.

The raw logs (about 400 MB for these four cells) stay on the laptop and are not in git, so
on a fresh clone these tests are skipped rather than failed.
"""
import contextlib
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import compare_cells as cc  # noqa: E402

HAVE_LOGS = all(any((paths.RESULTS / batch).glob("*.log"))
                for batches in cc.CELLS.values() for batch in batches)


@unittest.skipUnless(HAVE_LOGS, "the raw logs live on the laptop, not in git")
class CellFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.cells, cls.truth = cc.load()
        cls.one, cls.two, cls.three, cls.five = (cls.cells[n] for n in cc.CELLS)

    def total(self, reading: str, measure: str) -> list[int]:
        def hit(run):
            return (cc.correct(run, reading) if measure == "correct"
                    else cc.covered(run, reading, self.truth))
        return [sum(map(hit, runs)) for runs in self.cells.values()]

    def p_by_question(self, a, b, reading, measure) -> float:
        def hit(run):
            return (cc.correct(run, reading) if measure == "correct"
                    else cc.covered(run, reading, self.truth))
        return round(cc.compare(a, b, hit)[2], 5)

    def test_fifteen_valid_gated_runs_in_every_cell(self):
        self.assertEqual([len(runs) for runs in self.cells.values()], [15, 15, 15, 15])

    def test_correct_under_the_key_fixed_before_the_runs(self):
        self.assertEqual(self.total("menu", "correct"), [4, 11, 9, 11])

    def test_correct_under_the_can_sell_reading(self):
        self.assertEqual(self.total("buyable", "correct"), [5, 12, 12, 14])

    def test_covered(self):
        self.assertEqual(self.total("menu", "covered"), [3, 15, 12, 15])

    def test_second_agent_repeats(self):
        self.assertEqual(len(cc.distinct(self.three)), 7)

    def test_the_tests_quoted_on_the_site(self):
        self.assertEqual(self.p_by_question(self.two, self.one, "menu", "correct"), 0.005)
        self.assertEqual(self.p_by_question(self.five, self.one, "menu", "correct"), 0.007)
        self.assertEqual(self.p_by_question(self.two, self.one, "menu", "covered"), 0.00004)
        self.assertEqual(self.p_by_question(self.five, self.one, "menu", "covered"), 0.00004)
        self.assertEqual(self.p_by_question(self.five, self.two, "menu", "correct"), 1.0)
        self.assertEqual(self.p_by_question(cc.distinct(self.three), self.one, "menu", "covered"),
                         0.03125)


if __name__ == "__main__":
    unittest.main()
