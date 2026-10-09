"""Every clothing-cell figure the site shows, recomputed from the raw runs.

The site and `make facts` both read `cell_facts.facts()`, so pinning its output pins both. A
change here is a change to a published result. If a scorer or checker fix moves one of these
numbers, update this file, regenerate the site (`make site`) and add a dated entry to the
README decision log in the same commit, so the change is visible rather than silent.

The raw logs (about 400 MB for these four cells) stay on the laptop and are not in git, so on
a fresh clone these tests are skipped rather than failed. The September water table is built
by docs/build_site.py and is not pinned here.
"""
import contextlib
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import cell_facts  # noqa: E402
import compare_cells as cc  # noqa: E402

HAVE_LOGS = all(any((paths.RESULTS / batch).glob("*.log"))
                for batches in cc.CELLS.values() for batch in batches)

OPEN = "did not open what the answer needs"
SELLER = "named a seller that cannot sell M"
OFFER = 'read "offer" as "can sell it now"'
REVEAL = "read the price before the page revealed it"
STEPS = "ran out of its 100 steps"


@unittest.skipUnless(HAVE_LOGS, "the raw logs live on the laptop, not in git")
class CellFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.f = cell_facts.facts(account=False)
        cls.name = {n.split()[0]: n for n in cls.f["names"]}

    def per_cell(self, key) -> list:
        return [self.f["cells"][self.name[label]][key] for label in "1235"]

    def p(self, a, b, measure, reading="menu", distinct=False) -> float:
        test = next(t for t in self.f["tests"] if t["a"] == a and t["b"] == b and
                    t["measure"] == measure and t["reading"] == reading and
                    t["distinct"] == distinct)
        return round(test["p_question"], 5)

    def test_section_a(self):
        self.assertEqual(self.per_cell("runs"), [15, 15, 15, 15])
        self.assertEqual(self.per_cell("distinct"), [15, 15, 7, 15])
        self.assertEqual(self.per_cell("right"), [4, 11, 9, 11])
        self.assertEqual(self.per_cell("right_buyable"), [5, 12, 12, 14])
        self.assertEqual(self.per_cell("opened"), [3, 15, 12, 15])
        self.assertEqual(self.per_cell("opened_buyable"), [6, 15, 15, 15])
        self.assertEqual(self.per_cell("median_opened"), [4, 15, 15, 15])
        self.assertEqual([round(x) for x in self.per_cell("calls")], [23, 51, 17, 57])
        self.assertEqual([round(x, 3) for x in self.per_cell("cost")],
                         [0.176, 0.485, 0.132, 0.524])

    def test_control_question(self):
        self.assertEqual(self.per_cell("control"), [{"correct": 2, "of": 3},
                                                    {"correct": 3, "of": 3},
                                                    {"correct": 3, "of": 3}, None])

    def test_section_b_each_question(self):
        want = {  # correct / opened what it needs, of 3, under the answer key
            "1": {"all-stocked": (3, 0), "cheapest-target": (0, 1), "count-buyable": (1, 1),
                  "count-stocked": (0, 1), "target-price": (0, 0)},
            "2": {"all-stocked": (3, 3), "cheapest-target": (3, 3), "count-buyable": (3, 3),
                  "count-stocked": (1, 3), "target-price": (1, 3)},
            "3": {"all-stocked": (3, 0), "cheapest-target": (0, 3), "count-buyable": (3, 3),
                  "count-stocked": (0, 3), "target-price": (3, 3)},
            "5": {"all-stocked": (3, 3), "cheapest-target": (3, 3), "count-buyable": (2, 3),
                  "count-stocked": (0, 3), "target-price": (3, 3)},
        }
        for label, questions in want.items():
            per = self.f["cells"][self.name[label]]["per_question"]
            got = {q.replace("apparel-", ""): (v["correct"], v["covered"]) for q, v in per.items()}
            with self.subTest(cell=label):
                self.assertEqual(got, questions)

    def test_section_c_the_tests(self):
        self.assertEqual(self.p("2", "1", "correct"), 0.005)
        self.assertEqual(self.p("5", "1", "correct"), 0.007)
        self.assertEqual(self.p("5", "2", "correct"), 1.0)
        self.assertEqual(self.p("2", "1", "opened"), 0.00004)
        self.assertEqual(self.p("5", "1", "opened"), 0.00004)
        self.assertEqual(self.p("3", "1", "opened", distinct=True), 0.03125)
        self.assertEqual(self.p("2", "1", "correct", "buyable"), 0.0115)
        self.assertEqual(self.p("5", "1", "correct", "buyable"), 0.00155)

    def test_section_d_kinds_of_error(self):
        want = {"1": {OPEN: 9, SELLER: 1, OFFER: 3, REVEAL: 5},
                "2": {STEPS: 1, OFFER: 2, REVEAL: 1},
                "3": {OFFER: 1, REVEAL: 1},
                "5": {STEPS: 1, OFFER: 3}}
        for label, kinds in want.items():
            got = {kind: len(runs) for kind, runs in self.f["errors"][self.name[label]]}
            with self.subTest(cell=label):
                self.assertEqual(got, kinds)

    def test_section_e_refusal_replay(self):
        want = {"1": (11, 9, 4, 0), "2": (4, 0, 11, 0), "5": (4, 0, 11, 0)}
        for label, (wrong, refused, right, right_refused) in want.items():
            got = self.f["refusal"][self.name[label]]
            with self.subTest(cell=label):
                self.assertEqual((got["wrong"], got["refused"], got["right"],
                                  got["right_refused"]), (wrong, refused, right, right_refused))

    def test_section_f_how_runs_were_checked(self):
        window = [len(self.f["agent_window"][self.name[label]]["runs"]) for label in "1235"]
        self.assertEqual(window, [0, 0, 0, 4])
        self.assertEqual([self.f["batch_selections"][self.name[label]] for label in "1235"],
                         [5, 17, 0, 8])
        self.assertEqual([len(self.f["same_instant"][self.name[label]]["runs"]) for label in "1235"],
                         [1, 1, 0, 0])
        suspended = {s["batch"]: [run for run, _ in s["suspended"]] for s in self.f["silence"]}
        self.assertEqual(suspended["20261008T034455"],
                         ["count-buyable-2", "target-price-1", "target-price-2"])
        self.assertEqual(sum(len(v) for v in suspended.values()), 3)

    def test_section_g_charges(self):
        charges = {c["batch"]: round(c["charges"], 4) for c in self.f["cost"]}
        self.assertEqual(charges, {"20261007T111945": 0.0393, "20261007T112057": 2.7192,
                                   "20261007T115021": 7.38, "20261007T134621": 1.9966,
                                   "20261008T034455": 8.0557, "20261008T143724": 1.6244,
                                   "20261008T144558": 0.3537})


if __name__ == "__main__":
    unittest.main()
