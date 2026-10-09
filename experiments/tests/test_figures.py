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

# Every comparison the site's tests table shows: reading of "offer", measure, cell a, cell b,
# distinct runs only, the counts, p by question, p pooled.
TESTS = [
    ("menu", "correct", "2", "1", False, "11 of 15 against 4 of 15", 0.005, 0.02684),
    ("menu", "correct", "3", "1", True, "5 of 7 against 4 of 15", 0.125, 0.0743),
    ("menu", "correct", "3", "2", True, "5 of 7 against 11 of 15", 1.0, 1.0),
    ("menu", "correct", "5", "1", False, "11 of 15 against 4 of 15", 0.007, 0.02684),
    ("menu", "correct", "5", "2", False, "11 of 15 against 11 of 15", 1.0, 1.0),
    ("menu", "opened", "2", "1", False, "15 of 15 against 3 of 15", 0.00004, 0.00001),
    ("menu", "opened", "3", "1", True, "4 of 7 against 3 of 15", 0.03125, 0.14466),
    ("menu", "opened", "3", "2", True, "4 of 7 against 15 of 15", 0.1, 0.02273),
    ("menu", "opened", "5", "1", False, "15 of 15 against 3 of 15", 0.00004, 0.00001),
    ("menu", "opened", "5", "2", False, "15 of 15 against 15 of 15", 1.0, 1.0),
    ("buyable", "correct", "2", "1", False, "12 of 15 against 5 of 15", 0.0115, 0.02533),
    ("buyable", "correct", "3", "1", True, "6 of 7 against 5 of 15", 0.0625, 0.06347),
    ("buyable", "correct", "3", "2", True, "6 of 7 against 12 of 15", 1.0, 1.0),
    ("buyable", "correct", "5", "1", False, "14 of 15 against 5 of 15", 0.00155, 0.0017),
    ("buyable", "correct", "5", "2", False, "14 of 15 against 12 of 15", 0.6, 0.5977),
    ("buyable", "opened", "2", "1", False, "15 of 15 against 6 of 15", 0.0008, 0.0007),
    ("buyable", "opened", "3", "1", True, "7 of 7 against 6 of 15", 0.03125, 0.01668),
    ("buyable", "opened", "3", "2", True, "7 of 7 against 15 of 15", 1.0, 1.0),
    ("buyable", "opened", "5", "1", False, "15 of 15 against 6 of 15", 0.0008, 0.0007),
    ("buyable", "opened", "5", "2", False, "15 of 15 against 15 of 15", 1.0, 1.0),
]

# Every row of the site's error table: each kind of error and the runs it was found in.
ERRORS = {
    "1": {OPEN: ["cheapest-target-1", "cheapest-target-3", "count-buyable-1", "count-buyable-3",
                 "count-stocked-1", "count-stocked-3", "target-price-1", "target-price-2",
                 "target-price-3"],
          SELLER: ["cheapest-target-2"],
          OFFER: ["count-stocked-1", "count-stocked-2", "count-stocked-3"],
          REVEAL: ["cheapest-target-1", "cheapest-target-3", "target-price-1", "target-price-2",
                   "target-price-3"]},
    "2": {STEPS: ["target-price-1"], OFFER: ["count-stocked-1", "count-stocked-2"],
          REVEAL: ["target-price-3"]},
    "3": {OFFER: ["count-stocked-1"], REVEAL: ["cheapest-target-1"]},
    "5": {STEPS: ["count-buyable-3"], OFFER: ["count-stocked-1", "count-stocked-2", "count-stocked-3"]},
}

# The checks block: runs in each cell's batches, and which of them set the window limit
# themselves, or wrote a script that changes a size and reads the price in one go (with how
# many such scripts).
WINDOW = {"1": (18, []), "2": (18, []), "3": (18, []),
          "5": (18, ["all-stocked-1", "cheapest-target-3", "count-stocked-3", "count-buyable-1"])}
SAME_INSTANT = {"1": (18, [["cheapest-target-2", 11]]), "2": (18, [["target-price-3", 13]]),
                "3": (18, []), "5": (18, [])}
RESCORED = [{"batch": "20261007T115021", "run": "apparel-count-buyable-3", "from": "wrong",
             "to": "correct",
             "reason": "count rule no longer reads 'all 15' as the count, 8 Oct 2026"}]

# Every row of the site's silence table: the longest silence in each batch's logs in seconds,
# 0 where the log has no timestamps, the longest whole run there, and the suspended runs.
SILENCE = {
    "20261007T112057": (31, None, []),
    "20261007T115021": (31, None, []),
    "20261007T134621": (0, 85, []),
    "20261008T034455": (3018, None, [["count-buyable-2", 2962], ["target-price-1", 3018],
                                     ["target-price-2", 1056]]),
    "20261008T143724": (6, None, []),
    "20261008T144558": (6, None, []),
}


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
                self.assertEqual({v["of"] for v in per.values()}, {3})

    def test_section_c_every_comparison(self):
        got = [(t["reading"], t["measure"], t["a"], t["b"], t["distinct"], t["text"],
                round(t["p_question"], 5), round(t["p_pooled"], 5)) for t in self.f["tests"]]
        self.assertEqual(got, TESTS)

    def test_section_d_kinds_of_error(self):
        for label, kinds in ERRORS.items():
            got = {kind: runs for kind, runs in self.f["errors"][self.name[label]]}
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
        for label in "1235":
            name = self.name[label]
            with self.subTest(cell=label):
                window = self.f["agent_window"][name]
                self.assertEqual((window["of"], window["runs"]), WINDOW[label])
                scripts = self.f["same_instant"][name]
                self.assertEqual((scripts["of"], scripts["runs"]), SAME_INSTANT[label])
        self.assertEqual([self.f["batch_selections"][self.name[label]] for label in "1235"],
                         [5, 17, 0, 8])
        self.assertEqual(self.f["rescored"], RESCORED)
        got = {s["batch"]: (round(s["longest_silence_s"]),
                            None if s["longest_silence_s"] else round(s["longest_run_s"]),
                            [[run, round(x)] for run, x in s["suspended"]])
               for s in self.f["silence"]}
        self.assertEqual(got, SILENCE)

    def test_section_g_charges(self):
        charges = {c["batch"]: round(c["charges"], 4) for c in self.f["cost"]}
        self.assertEqual(charges, {"20261007T111945": 0.0393, "20261007T112057": 2.7192,
                                   "20261007T115021": 7.38, "20261007T134621": 1.9966,
                                   "20261008T034455": 8.0557, "20261008T143724": 1.6244,
                                   "20261008T144558": 0.3537})


if __name__ == "__main__":
    unittest.main()
