"""The box's front half: the question classifier and the planner.

The box may use only what the agent could see, the question and the pages. These tests pin
how every clothing question is classified, controls included (LESSONS 18), and check that
the box's code never reads an answer key.
"""
import contextlib
import io
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import planner  # noqa: E402
import targeting  # noqa: E402

BASE = "http://localhost:7770"


class Classifier(unittest.TestCase):
    EXPECTED = {
        "apparel-headline": "results_page",          # the control: answered on the results page
        "apparel-target-price": "availability_bound",
        "apparel-cheapest-target": "availability_bound",
        "apparel-all-stocked": "refutation",
        "apparel-count-stocked": "survey",
        "apparel-count-buyable": "survey",
    }

    def test_every_clothing_question(self):
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        self.assertEqual({t["id"] for t in spec["tasks"]}, set(self.EXPECTED))
        for task in spec["tasks"]:
            with self.subTest(task=task["id"]):
                self.assertEqual(targeting.classify(task["query"].format(base=BASE)),
                                 self.EXPECTED[task["id"]])


class Planner(unittest.TestCase):
    def test_regression_passes(self):
        # Every question in every task file: the plan renders the same text the strategy
        # table does, and every plan passes its own soundness check.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(planner.regression(), 0)

    def test_an_unsound_plan_is_caught(self):
        plan = planner.plan("Across the Thornwood listings, which seller is cheapest for size M?")
        self.assertEqual(planner.verify(plan), [])
        # Each break is a failure already paid for: pruning a market never listed, and a
        # bound's arithmetic reported as a price.
        for label, broken in (("not enumerated", {**plan, "enumerate_first": False}),
                              ("bound reportable", {**plan, "forbidden_claims": []})):
            with self.subTest(broken=label):
                self.assertNotEqual(planner.verify(broken), [])


class NoAnswerKey(unittest.TestCase):
    """The box decides from the question alone. It must never read what the answer is."""

    FORBIDDEN = ("_instance", '["expect"]', "fixtures")

    def test_box_code_reads_no_answers(self):
        for name in ("targeting.py", "planner.py"):
            text = (paths.EXPERIMENTS / "box" / name).read_text()
            for word in self.FORBIDDEN:
                with self.subTest(file=name, word=word):
                    self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
