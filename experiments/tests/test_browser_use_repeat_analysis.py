"""Synthetic-only tests for repeat analysis gates, accounting and paired summaries."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import browser_use_repeat_analysis as analysis
from experiments.tests.test_browser_use_analysis import BrowserUseAnalysis


class RepeatAnalysis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Path(self.tmp.name)
        (self.bundle / "validated").mkdir()
        blank = [{"code": f"code{i}", "question": f"question{i}", "key": "{}", "answer": "synthetic",
                  "hand_verdict": "", "note": ""} for i in range(32)]
        self.sheet = self.bundle / analysis.blind.SHEET
        self.sheet.write_text(analysis.blind.review.csv_text(blank))
        self.reviewed = self.bundle / "validated/reviewed.csv"
        self.reviewed.write_text(analysis.blind.review.csv_text([{**r, "hand_verdict": "correct"} for r in blank]))
        self.manifest = {"study_id": analysis.blind.STUDY, "batch_id": analysis.blind.BATCH, "rows": 32,
                         "original_sheet_sha256": analysis.digest(self.sheet)}
        (self.bundle / "manifest.json").write_text(json.dumps(self.manifest))
        self.receipt = {**self.manifest, "complete": True, "arm_key_read": False, "scored": False,
                        "reviewed_sha256": analysis.digest(self.reviewed)}
        self.receipt_path = self.bundle / "validated/validation.json"
        self.receipt_path.write_text(json.dumps(self.receipt))

    def test_review_gate_succeeds_without_mapping_and_refuses_changed_receipt(self):
        self.assertEqual(len(analysis.completed_review(self.bundle)), 32)
        self.receipt_path.write_text(json.dumps({**self.receipt, "complete": False}))
        with self.assertRaises(ValueError):
            analysis.completed_review(self.bundle)

    def test_incomplete_review_never_opens_private_mapping(self):
        rows = analysis.blind.review.read_sheet(self.reviewed)
        rows[0]["hand_verdict"] = ""
        self.reviewed.write_text(analysis.blind.review.csv_text(rows))
        self.receipt_path.write_text(json.dumps({**self.receipt, "reviewed_sha256": analysis.digest(self.reviewed)}))
        with mock.patch.object(analysis, "read_json", side_effect=AssertionError("No mapping read")):
            with self.assertRaisesRegex(ValueError, "Complete all 32"):
                analysis.analyse(self.bundle)

    def test_failed_record_keeps_cost_and_valid_observed_openings(self):
        record = {**BrowserUseAnalysis.record(), "outcome": "failed", "answer": ""}
        measured = analysis.measure_record(record)
        self.assertEqual(measured["total_cost_usd"], .3)
        self.assertEqual(measured["openings"], 1)
        self.assertTrue(measured["navigation_measurement_valid"])

    def test_unknown_navigation_is_not_zero_and_does_not_discard_spending(self):
        record = BrowserUseAnalysis.record()
        record["trace"]["measurement_valid"] = False
        measured = analysis.measure_record(record)
        self.assertIsNone(measured["openings"])
        self.assertEqual(measured["total_cost_usd"], .3)
        self.assertFalse(measured["navigation_measurement_valid"])
        record["calls"][0]["cost_usd"] = None
        with self.assertRaises(ValueError):
            analysis.measure_record(record)

    def test_claimed_valid_but_inconsistent_navigation_refused(self):
        record = BrowserUseAnalysis.record()
        record["trace"]["opened"] = 2
        with self.assertRaises(ValueError):
            analysis.measure_record(record)

    @staticmethod
    def summary_rows():
        return [{"task": task, "condition": arm, "repeat": repeat, "human_verdict": "correct" if arm == "block" else "not correct",
                 "automatic_verdict": "wrong", "outcome": "answered", "total_cost_usd": .1 if arm == "block" else .2,
                 "executor_cost_usd": .09 if arm == "block" else .2, "parser_cost_usd": .01 if arm == "block" else 0,
                 "openings": 2 if arm == "block" else 4, "steps": 3, "elapsed_s": 5, "error_count": 0,
                 "providers": {"Synthetic": 1}} for task in analysis.blind.TASK_IDS for repeat in (2, 3) for arm in ("baseline", "block")]

    def test_pairing_retains_repeats_questions_unscorable_and_missing_measurements(self):
        rows = self.summary_rows()
        rows[0].update(human_verdict="unscorable", outcome="failed", openings=None)
        result = analysis.summarize(rows)
        self.assertEqual(len(result["paired"]), 16)
        self.assertEqual(len(result["questions"]), 8)
        self.assertEqual(result["arms"]["baseline"]["human_assessable"], 15)
        self.assertEqual(result["arms"]["baseline"]["outcomes"], {"failed": 1, "answered": 15})
        self.assertEqual(result["pair_counts"]["unscorable_pair"], 1)
        self.assertEqual(result["pair_counts"]["openings"]["valid_pairs"], 15)
        self.assertIsNone(result["arms"]["baseline"]["resources"]["openings"]["total"])
        self.assertEqual(result["arms"]["baseline"]["resources"]["total_cost_usd"]["total"], 3.2)
        self.assertEqual(result["equal_weight_question_summary"]["mean_opening_difference_block_minus_baseline"]["question_strata"], 7)
        self.assertEqual(len(result["human_unscorable_audit"]), 1)
        self.assertEqual(len(result["disagreements"]), 16)
        for repeat in ("2", "3"):
            self.assertEqual(result["by_repeat"][repeat]["arms"]["baseline"]["scheduled"], 8)

    def test_missing_duplicate_or_original_repeat1_rows_refused(self):
        rows = self.summary_rows()
        for bad in (rows[:-1], rows[:-1]+[rows[0]], [{**rows[0], "repeat": 1}, *rows[1:]]):
            with self.assertRaises(ValueError):
                analysis.summarize(bad)

    def test_ledger_requires_exact_call_coverage_and_identical_costs(self):
        calls = [{"generation_id": "id1", "role": "executor", "provider": "Synthetic", "cost_usd": .2},
                 {"generation_id": "id2", "role": "parser", "provider": "Synthetic", "cost_usd": .1}]
        records = [{"calls": calls}]
        ledger = {"study_budget_id": analysis.blind.BATCH, "attempt": 1, "inflight": {}, "blocked_reason": None,
                  "calls": calls, "charged_usd": .3}
        self.assertEqual(analysis.reconcile_calls(records, ledger, {}, 1)["charge_usd"], .3)
        for change in ({"calls": calls[:1]}, {"calls": calls+[calls[0]]}, {"charged_usd": .4},
                       {"inflight": {"pending": {}}}, {"attempt": 2}):
            with self.assertRaises(ValueError):
                analysis.reconcile_calls(records, {**ledger, **change}, {}, 1)
        changed = copy.deepcopy(calls); changed[0]["provider"] = "different"
        with self.assertRaises(ValueError):
            analysis.reconcile_calls(records, {**ledger, "calls": changed}, {}, 1)


if __name__ == "__main__":
    unittest.main()
