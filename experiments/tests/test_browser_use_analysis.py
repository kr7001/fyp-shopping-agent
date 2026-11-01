"""Synthetic-only checks for validated review gates and transfer arithmetic."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import browser_use_review as review  # noqa: E402
import browser_use_analysis as analysis  # noqa: E402


class BrowserUseAnalysis(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name)
        self.validated = self.bundle / "validated"
        self.validated.mkdir()
        self.rows = [{"code": f"synthetic-{i:02}", "question": f"Question {i}?",
                      "key": '{"kind":"price","value":1}', "answer": "Synthetic answer.",
                      "hand_verdict": "", "note": ""} for i in range(16)]
        original = self.bundle / review.SHEET
        original.write_text(review.review.csv_text(self.rows), encoding="utf-8", newline="")
        self.original_sha = review.digest(original)
        self.put(self.bundle / "manifest.json", {"study_id": review.STUDY, "rows": 16,
            "original_sheet_sha256": self.original_sha})
        self.save_completed([{**row, "hand_verdict": "correct", "note": "My judgement."}
                             for row in self.rows])

    @staticmethod
    def put(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def save_completed(self, rows):
        path = self.validated / "reviewed.csv"
        path.write_text(review.review.csv_text(rows), encoding="utf-8", newline="")
        self.put(self.validated / "validation.json", {
            "study_id": review.STUDY, "rows": 16, "complete": True,
            "original_sheet_sha256": self.original_sha,
            "reviewed_sha256": review.digest(path), "arm_key_read": False, "scored": False})

    @staticmethod
    def record():
        url = "http://localhost:7770/product-one.html"
        return {"calls": [{"role": "parser", "cost_usd": 0.1},
                          {"role": "executor", "cost_usd": 0.2}],
                "total_cost_usd": 0.3, "parse_cost_usd": 0.1, "cost_usd": 0.2,
                "steps": 3, "elapsed_s": 9.0, "elapsed_with_parser_s": 10.0,
                "agent_errors": [None, "Synthetic action error"],
                "measurement_status": "complete", "page": {"listings": [{"url": url}]},
                "trace": {"opened": 1, "opened_urls": [url], "measurement_valid": True,
                    "observation_errors": [], "navigation_events": [
                        {"url": url, "status": 200, "main_document": True,
                         "candidate": True, "product_document": True, "counted": True}]}}

    def test_completed_review_needs_no_arm_key_or_records(self):
        self.assertFalse((self.bundle / "private-arm-key.json").exists())
        result = analysis.completed_review(self.bundle)
        self.assertEqual(len(result), 16)
        self.assertTrue(all(row["hand_verdict"] == "correct" for row in result))

    def test_incomplete_review_refused_even_if_receipt_claims_complete(self):
        self.save_completed([{**row, "hand_verdict": "correct" if i else ""}
                             for i, row in enumerate(self.rows)])
        with self.assertRaises(ValueError):
            analysis.completed_review(self.bundle)

    def test_changed_download_or_receipt_is_refused(self):
        path = self.validated / "reviewed.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            analysis.completed_review(self.bundle)
        self.save_completed([{**row, "hand_verdict": "correct"} for row in self.rows])
        receipt = self.validated / "validation.json"
        data = json.loads(receipt.read_text())
        self.put(receipt, {**data, "complete": False})
        with self.assertRaises(ValueError):
            analysis.completed_review(self.bundle)

    def test_changed_answer_refused_even_with_refreshed_receipt(self):
        changed = [{**row, "hand_verdict": "correct"} for row in self.rows]
        changed[0]["answer"] = "Replacement answer after review"
        self.save_completed(changed)
        with self.assertRaises(ValueError):
            analysis.completed_review(self.bundle)

    def test_provider_cost_is_sum_including_parser_and_executor(self):
        measured = analysis.measure_record(self.record())
        self.assertEqual(measured["openings"], 1)
        self.assertAlmostEqual(measured["total_cost_usd"], 0.3)
        self.assertAlmostEqual(measured["parser_cost_usd"], 0.1)
        self.assertAlmostEqual(measured["executor_cost_usd"], 0.2)
        self.assertEqual(measured["error_count"], 1)

    def test_missing_invalid_or_unreconciled_charge_is_refused(self):
        for value in (None, -0.1, float("nan"), float("inf"), True):
            bad = self.record()
            bad["calls"][0]["cost_usd"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                analysis.measure_record(bad)
        for field in ("total_cost_usd", "parse_cost_usd", "cost_usd"):
            bad = self.record()
            bad[field] += 0.01
            with self.subTest(field=field), self.assertRaises(ValueError):
                analysis.measure_record(bad)

    def test_openings_require_distinct_successful_candidate_evidence(self):
        bad_cases = []
        bad = self.record()
        bad["trace"]["opened_urls"] *= 2
        bad["trace"]["opened"] = 2
        bad_cases.append(bad)
        for field, value in (("status", 404), ("product_document", False),
                             ("main_document", False), ("counted", False)):
            bad = self.record()
            bad["trace"]["navigation_events"][0][field] = value
            bad_cases.append(bad)
        bad = self.record()
        bad["page"]["listings"][0]["url"] = "http://localhost:7770/other.html"
        bad_cases.append(bad)
        bad = self.record()
        bad["trace"]["measurement_valid"] = False
        bad_cases.append(bad)
        for i, bad in enumerate(bad_cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                analysis.measure_record(bad)

    @staticmethod
    def summary_rows():
        rows = []
        for i, task in enumerate(review.TASK_IDS):
            for arm in ("baseline", "block"):
                human = ("correct" if i < 4 else "unscorable" if i == 7 else "not correct")
                if arm == "block":
                    human = "correct" if i < 5 else "not correct"
                rows.append({"task": task, "condition": arm, "human_verdict": human,
                             "automatic_verdict": "correct" if arm == "baseline" else "wrong",
                             "openings": 10 if arm == "baseline" else 4,
                             "total_cost_usd": 1.0 if arm == "baseline" else 0.25,
                             "executor_cost_usd": 1.0 if arm == "baseline" else 0.2,
                             "parser_cost_usd": 0.0 if arm == "baseline" else 0.05,
                             "steps": 10, "elapsed_s": 20.0, "error_count": 0})
        return rows

    def test_summary_preserves_human_automatic_and_unscorable_separately(self):
        result = analysis.summarize(self.summary_rows())
        baseline, block = result["arms"]["baseline"], result["arms"]["block"]
        self.assertEqual((baseline["human_correct"], baseline["human_assessable"]), (4, 7))
        self.assertEqual((block["human_correct"], block["human_assessable"]), (5, 8))
        self.assertEqual(baseline["human"]["unscorable"], 1)
        self.assertEqual(baseline["automatic"], {"correct": 8})
        self.assertEqual(block["automatic"], {"wrong": 8})
        self.assertEqual(len(result["disagreements"]), 9)
        self.assertEqual(len(result["paired"]), 8)
        self.assertEqual(result["block_cheaper_pairs"], 8)
        self.assertEqual(result["block_fewer_openings_pairs"], 8)
        self.assertEqual(result["equal_openings_pairs"], 0)
        self.assertAlmostEqual(result["block_cost_reduction_fraction"], 0.75)
        self.assertEqual((baseline["total_openings"], block["total_openings"]), (80, 32))
        self.assertAlmostEqual(block["parser_cost_usd"], 0.4)

    def test_summary_rejects_missing_duplicate_or_foreign_pairs(self):
        rows = self.summary_rows()
        for bad in (rows[:-1], rows[:-1] + [rows[0]],
                    [{**rows[0], "task": "other-market"}, *rows[1:]]):
            with self.assertRaises(ValueError):
                analysis.summarize(bad)


if __name__ == "__main__":
    unittest.main()
