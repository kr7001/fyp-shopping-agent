"""Synthetic-only checks for transfer review generation and blind validation."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import browser_use_review as transfer  # noqa: E402


class BrowserUseReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.backup = self.folder / "backup"
        self.results = self.backup / "monitored-1-nov.results"
        self.results.mkdir(parents=True)
        self.bundle = self.folder / "review"
        self.task_file = self.folder / "tasks.json"
        self.incoming = self.folder / "download.csv"
        self.completed = self.folder / "validated"
        self.questions = [{"id": task, "query": f"Go to http://localhost:7770 . Question {i}?",
                           "start_url": "http://localhost:7770"}
                          for i, task in enumerate(transfer.TASK_IDS)]
        self.config_file = self.backup / "monitored-command-1-nov.json"
        self.put(self.config_file, {"stage": "monitored-transfer", "transfer_questions": self.questions})
        self.config_sha = transfer.digest(self.config_file)
        self.put(self.backup / "monitored-1-nov.status.json",
                 {"status": "complete", "config_sha256": self.config_sha})
        self.put(self.task_file, {"base_url": "http://localhost:7770", "tasks": [
            {"id": question["id"], "query": f"Go to {{base}} . Question {i}?",
             "expect": {"kind": "price", "value": i + 0.25}}
            for i, question in enumerate(self.questions)]})
        self.tasks_sha = transfer.digest(self.task_file)
        self.formal, self.answers, statuses = [], [], {}
        for i, question in enumerate(self.questions):
            arms = ("baseline", "block") if i % 2 == 0 else ("block", "baseline")
            for arm in arms:
                slot = {"id": f"transfer-{question['id']}-r1-{arm}", "question": question,
                        "condition": arm, "repeat": 1, "phase": "transfer", "clock_s": 2700}
                self.formal.append(slot)
                answer = f'Answer {len(self.answers)}: café, "yes".\nLiteral </script><img src=x>.'
                self.answers.append(answer)
                self.put(self.results / (slot["id"] + ".json"), {
                    "study_id": transfer.STUDY, "stage": "monitored-transfer", "phase": "transfer",
                    "slot": slot["id"], "condition": arm, "repeat": 1, "task": question["id"],
                    "question": question["query"], "outcome": "answered", "answer": answer,
                    "sent_query": "PRIVATE_SENT_QUERY", "box": "PRIVATE_BOX",
                    "total_cost_usd": "PRIVATE_COST", "trace": "PRIVATE_TRACE",
                    "automatic_verdict": "PRIVATE_VERDICT"})
                statuses[slot["id"]] = {"phase": "transfer", "status": "answered"}
        # No diagnostic record exists: generation must never attempt to read it.
        pilot = {"id": "pilot-synthetic", "phase": "pilot"}
        statuses[pilot["id"]] = {"phase": "pilot", "status": "answered"}
        self.schedule_file = self.results / "schedule.json"
        self.put(self.schedule_file, {"study_id": transfer.STUDY, "stage": "monitored-transfer",
                                      "slots": [pilot, *self.formal]})
        self.put(self.results / "slot-status.json", {"slots": statuses})

    @staticmethod
    def put(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def prepare(self):
        return transfer.prepare(self.backup, self.task_file, self.bundle, self.config_sha, self.tasks_sha)

    def rows(self):
        return transfer.review.read_sheet(self.bundle / transfer.SHEET)

    def download(self, rows):
        self.incoming.write_text(transfer.review.csv_text(rows), encoding="utf-8-sig", newline="")

    def reviewed(self):
        return [{**row, "hand_verdict": ("correct", "not correct", "unscorable")[i % 3],
                 "note": 'My note, "quoted"\nwith a new line.'} for i, row in enumerate(self.rows())]

    def test_prepare_copies_all_answers_verbatim_and_only_safe_payload(self):
        self.assertEqual(self.prepare(), 16)
        rows = self.rows()
        self.assertEqual(len(rows), 16)
        self.assertCountEqual([row["answer"] for row in rows], self.answers)
        self.assertEqual(len({row["code"] for row in rows}), 16)
        self.assertTrue(all(len(row["code"]) == 12 and not row["hand_verdict"] and not row["note"]
                            for row in rows))
        html = (self.bundle / "review.html").read_text()
        payload = json.loads(html.split("const payload = ", 1)[1].split(";\nconst columns", 1)[0])
        self.assertEqual(set(payload), {"rows", "filename", "identity", "rules"})
        self.assertEqual(payload["rows"], rows)
        self.assertTrue(all(set(row) == set(transfer.review.COLUMNS) for row in rows))
        self.assertNotIn("PRIVATE_", html)
        self.assertNotIn(str(self.backup), html)
        self.assertNotIn("Literal </script>", html)
        self.assertIn("Literal \\u003c/script>", html)
        self.assertIn("connect-src 'none'", html)

    def test_existing_bundle_never_regenerates_random_codes(self):
        self.prepare()
        before = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        with patch.object(transfer.secrets, "token_hex") as random_code:
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.prepare()
            random_code.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.bundle.iterdir()})

    def test_missing_duplicate_reordered_or_altered_schedule_is_refused(self):
        original = json.loads(self.schedule_file.read_text())
        slots = original["slots"]
        altered = copy.deepcopy(slots)
        altered[1]["repeat"] = 2
        for bad in (slots[:-1], slots + [slots[-1]], [slots[0], *reversed(slots[1:])], altered):
            with self.subTest(schedule=bad), self.assertRaisesRegex(ValueError, "Formal schedule"):
                self.put(self.schedule_file, {**original, "slots": bad})
                self.prepare()
            self.assertFalse(self.bundle.exists())

    def test_record_identity_or_task_wording_mismatch_is_refused(self):
        record_file = self.results / (self.formal[0]["id"] + ".json")
        original = json.loads(record_file.read_text())
        for field, wrong in (("task", "foreign"), ("condition", "foreign"), ("question", "wrong")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Trial metadata"):
                self.put(record_file, {**original, field: wrong})
                self.prepare()
        self.put(record_file, original)
        tasks = json.loads(self.task_file.read_text())
        tasks["tasks"][0]["query"] += " altered"
        self.put(self.task_file, tasks)
        self.tasks_sha = transfer.digest(self.task_file)
        with self.assertRaisesRegex(ValueError, "Frozen task wording"):
            self.prepare()

    def test_changed_expected_answer_key_checksum_is_refused(self):
        tasks = json.loads(self.task_file.read_text())
        tasks["tasks"][0]["expect"]["value"] = 999.99
        self.put(self.task_file, tasks)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_nonanswer_is_refused_never_filtered_out(self):
        record_file = self.results / (self.formal[0]["id"] + ".json")
        record = json.loads(record_file.read_text())
        self.put(record_file, {**record, "outcome": "failed"})
        with self.assertRaisesRegex(ValueError, "Non-answer trial"):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_incomplete_review_reports_progress_but_cannot_save_receipt(self):
        self.prepare()
        rows = self.rows()
        rows[0]["hand_verdict"] = "correct"
        self.download(rows)
        self.assertEqual(transfer.validate(self.bundle, self.incoming), (1, 16))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            transfer.validate(self.bundle, self.incoming, self.completed)
        self.assertFalse(self.completed.exists())

    def test_changed_immutable_missing_duplicate_or_invalid_rows_are_refused(self):
        self.prepare()
        rows = self.reviewed()
        bad_cases = [rows[:-1], rows + [rows[-1]], [{**rows[0], "hand_verdict": "maybe"}, *rows[1:]]]
        for field in transfer.review.IMMUTABLE:
            changed = copy.deepcopy(rows)
            changed[0][field] += " altered"
            bad_cases.append(changed)
        for i, bad in enumerate(bad_cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.download(bad)
                transfer.validate(self.bundle, self.incoming, self.completed)
            self.assertFalse(self.completed.exists())

    def test_completed_validation_without_raw_records_or_arm_key_preserves_original(self):
        self.prepare()
        original = (self.bundle / transfer.SHEET).read_bytes()
        rows = self.reviewed()
        self.download(list(reversed(rows)))
        (self.bundle / "private-arm-key.json").unlink()
        shutil.rmtree(self.backup)
        with patch.object(transfer.review.subprocess, "run", side_effect=AssertionError("No scorer allowed")):
            self.assertEqual(transfer.validate(self.bundle, self.incoming, self.completed), (16, 16))
        self.assertEqual(transfer.review.read_sheet(self.completed / "reviewed.csv"), rows)
        self.assertEqual((self.bundle / transfer.SHEET).read_bytes(), original)
        receipt = json.loads((self.completed / "validation.json").read_text())
        self.assertTrue(receipt["complete"])
        self.assertFalse(receipt["arm_key_read"])
        self.assertFalse(receipt["scored"])
        before = (self.completed / "reviewed.csv").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            transfer.validate(self.bundle, self.incoming, self.completed)
        self.assertEqual((self.completed / "reviewed.csv").read_bytes(), before)

    def test_modified_original_sheet_is_refused(self):
        self.prepare()
        self.download(self.reviewed())
        original = self.bundle / transfer.SHEET
        original.write_bytes(original.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Original blank sheet changed"):
            transfer.validate(self.bundle, self.incoming)

    def test_module_does_not_import_a_scorer(self):
        result = subprocess.run([sys.executable, "-c",
                                 "import sys; sys.path.insert(0, 'tools'); import browser_use_review; "
                                 "assert 'score' not in sys.modules; assert 'claim' not in sys.modules"],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
