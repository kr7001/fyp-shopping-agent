"""Free checks for the public measurements and primary-test reproduction path."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / "tools/reproduce_report.py"
spec = importlib.util.spec_from_file_location("reproduce_report", MODULE)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportMetricsTests(unittest.TestCase):
    def setUp(self):
        self.artifact = json.loads(report.DEFAULT.read_text())
        self.quenby = self.artifact["datasets"][1]
        self.protocol = json.loads((report.ROOT / self.quenby["protocol_path"]).read_text())
        self.tasks = json.loads((report.ROOT / self.quenby["tasks_path"]).read_text())

    def test_released_primary_counts_and_medians(self):
        wexcombe, quenby = report.reproduce(self.artifact)
        self.assertEqual(wexcombe["accuracy"]["block_model"]["correct"], 21)
        self.assertEqual(wexcombe["accuracy"]["shipped"]["correct"], 13)
        self.assertEqual(quenby["accuracy"]["block_model"]["correct"], 14)
        self.assertEqual(quenby["accuracy"]["shipped"]["correct"], 9)
        self.assertEqual(quenby["accuracy"]["shipped"]["scored"], 13)
        self.assertEqual(quenby["accuracy"]["shipped"]["trials"], 14)
        for result, opened, block_cost, exhaustive_cost, n in [
            (wexcombe, 5, .049683, .221002, 24), (quenby, 6, .046883, .215486, 16)
        ]:
            block, exhaustive = result["resources"]["block_model"], result["resources"]["exhaustive"]
            self.assertEqual(block["resource_trials"], n)
            self.assertEqual(block["median_opened"], opened)
            self.assertEqual(exhaustive["median_opened"], 45)
            self.assertAlmostEqual(block["median_cost_usd"], block_cost)
            self.assertAlmostEqual(exhaustive["median_cost_usd"], exhaustive_cost)

    def test_released_tests_match_frozen_human_analysis(self):
        wexcombe, quenby = report.reproduce(self.artifact)
        expected = [
            {"H1": (.002, .004), "H2": (3.125e-8, 1.25e-7),
             "H3": (2.55859375e-7, 7.67578125e-7), "H4": (1/280, .004)},
            {"H1": (1/12, 1/12), "H2": (1/2916, 1/972), "H3": (811/839808, 811/419904)},
        ]
        for result, values in zip((wexcombe, quenby), expected):
            self.assertEqual(result["holm_family_size"], len(values))
            for name, (raw, adjusted) in values.items():
                self.assertAlmostEqual(result["primary_tests"][name]["p"], raw, places=13)
                self.assertAlmostEqual(result["primary_tests"][name]["p_holm"], adjusted, places=13)
        self.assertEqual(wexcombe["primary_tests"]["H4"]["counts"], {"a": [36, 36], "b": [29, 36]})

    def test_exact_correctness_known_conditional_cases(self):
        self.assertAlmostEqual(report.exact_correctness([(3, 3, 0, 3)]), .1)
        self.assertAlmostEqual(report.exact_correctness([(3, 3, 0, 3), (3, 3, 0, 3)]), .005)
        self.assertEqual(report.exact_correctness([(2, 2, 2, 2)]), 1)

    def test_rank_ties_and_direction_symmetry(self):
        self.assertEqual(report.exact_ranks([([1, 1], [1, 1])]), 1)
        self.assertAlmostEqual(report.exact_ranks([([1, 2], [3, 4])]), 1/3)
        self.assertAlmostEqual(report.exact_ranks([([3, 4], [1, 2])]), 1/3)
        self.assertAlmostEqual(report.exact_ranks([([1, 1], [2, 2]), ([1, 1], [2, 2])]), 1/18)

    def test_holm_keeps_the_whole_family_and_monotonicity(self):
        self.assertEqual(report.holm({"a": .01, "b": .02, "c": .021, "d": .8}),
                         {"a": .04, "b": .06, "c": .06, "d": .8})
        del self.protocol["tests"]["H3"]
        with self.assertRaisesRegex(ValueError, "family"):
            report.summarize(self.quenby, self.protocol, self.tasks)

    def test_unscorable_is_preserved_and_not_turned_into_failure(self):
        run = next(r for r in self.quenby["runs"] if r["hand_verdict"] == "unscorable")
        self.assertIsNone(report.correct(run))
        original = report.summarize(self.quenby, self.protocol, self.tasks)
        run["hand_verdict"] = "not correct"
        changed = report.summarize(self.quenby, self.protocol, self.tasks)
        self.assertEqual(original["accuracy"]["shipped"]["unscorable"], 1)
        self.assertEqual(changed["accuracy"]["shipped"]["scored"], 14)
        self.assertNotEqual(original["primary_tests"]["H1"]["p"], changed["primary_tests"]["H1"]["p"])

    def test_automatic_grades_do_not_replace_human_grades(self):
        expected = report.summarize(self.quenby, self.protocol, self.tasks)
        for run in self.quenby["runs"]:
            run["automatic_verdict"] = "wrong" if run["automatic_verdict"] == "correct" else "correct"
        self.assertEqual(expected, report.summarize(self.quenby, self.protocol, self.tasks))

    def test_closed_slots_are_not_fabricated_human_grades(self):
        run = next(r for r in self.quenby["runs"] if r["arm"] == "block_model" and r["task"] == "tee-target-price")
        run.update(outcome=report.CLOSED, automatic_verdict=report.CLOSED, hand_verdict=None)
        result = report.summarize(self.quenby, self.protocol, self.tasks)
        self.assertEqual(result["accuracy"]["block_model"]["correct"], 13)
        self.assertEqual(result["accuracy"]["block_model"]["scored"], 14)
        self.assertEqual(result["resources"]["block_model"]["resource_trials"], 15)
        run["hand_verdict"] = "not correct"
        with self.assertRaisesRegex(ValueError, "no human"):
            report.summarize(self.quenby, self.protocol, self.tasks)

    def test_missing_duplicate_and_wrong_round_are_rejected(self):
        for action, message in [(lambda d: d["runs"].pop(), "grid"),
                                (lambda d: d["runs"].append(copy.deepcopy(d["runs"][0])), "duplicate"),
                                (lambda d: d.update(rounds=[1]), "rounds")]:
            data = copy.deepcopy(self.quenby)
            action(data)
            with self.assertRaisesRegex(ValueError, message):
                report.summarize(data, self.protocol, self.tasks)

    def test_answer_text_is_outside_the_public_metric_schema(self):
        self.quenby["runs"][0]["answer"] = "A private answer must not enter this artifact"
        with self.assertRaisesRegex(ValueError, "fields"):
            report.summarize(self.quenby, self.protocol, self.tasks)

    def test_invalid_grades_and_nonfinite_cost_are_rejected(self):
        for field, value in [("hand_verdict", None), ("cost_usd", float("nan")),
                             ("cost_usd", float("inf")), ("opened", True), ("repeat", True)]:
            data = copy.deepcopy(self.quenby)
            data["runs"][0][field] = value
            with self.assertRaises(ValueError):
                report.summarize(data, self.protocol, self.tasks)

    def test_separate_markets_and_source_integrity(self):
        self.artifact["datasets"].append(copy.deepcopy(self.quenby))
        with self.assertRaisesRegex(ValueError, "separate"):
            report.reproduce(self.artifact)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "fixture.json"
            file.write_text('{"original": true}')
            dataset = {"market": "Synthetic", "fixture_path": "fixture.json",
                       "fixture_sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
            self.assertEqual(report.checked_source(root, dataset, "fixture"), {"original": True})
            file.write_text('{"original": false}')
            with self.assertRaisesRegex(ValueError, "hash"):
                report.checked_source(root, dataset, "fixture")
            dataset["fixture_path"] = "../fixture.json"
            with self.assertRaisesRegex(ValueError, "relative"):
                report.checked_source(root, dataset, "fixture")


if __name__ == "__main__":
    unittest.main()
