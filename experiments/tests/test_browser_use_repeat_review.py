"""Synthetic-only checks for the separate failure-preserving 32-slot reader."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import browser_use_repeat_review as repeat


class RepeatReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.backups = [self.root / "attempt1", self.root / "attempt2"]
        self.results = [p / f"attempt{i}.results" for i, p in enumerate(self.backups, 1)]
        for p in self.results:
            p.mkdir(parents=True)
        self.bundle = self.root / "bundle"
        self.incoming, self.validated = self.root / "reviewed.csv", self.root / "validated"
        self.tasks_file = self.root / "tasks.json"
        self.questions = [{"id": task, "query": f"Go to http://localhost:7770 . Question {i}?",
                           "start_url": "http://localhost:7770"} for i, task in enumerate(repeat.TASK_IDS)]
        self.put(self.tasks_file, {"base_url": "http://localhost:7770", "tasks": [
            {"id": q["id"], "query": f"Go to {{base}} . Question {i}?", "expect": {"kind": "price", "value": i+.25}}
            for i, q in enumerate(self.questions)]})
        self.tasks_sha = repeat.digest(self.tasks_file)
        self.slots = repeat.expected_schedule(self.questions)
        self.answers = []
        self.configs = []
        for n, backup in enumerate(self.backups, 1):
            stage = ("plain-repeat-transfer", "plain-repeat-recovery")[n-1]
            cfg = {"stage": stage, "attempt": n, "study_budget_id": repeat.BATCH,
                   "repeats": [2, 3], "questions": self.questions}
            self.configs.append(cfg)
            schedule = {"stage": stage, "study_id": repeat.STUDY, "batch_id": repeat.BATCH,
                        "slots": self.slots if n == 1 else self.slots[6:]}
            if n == 2:
                schedule.update(prior_completed_count=6, original_slot_count=32)
            self.put(self.results[n-1] / "schedule.json", schedule)
            statuses = {}
            for i, slot in enumerate(self.slots):
                if n == 2 and i < 6:
                    continue
                outcome = "not_started" if n == 1 and i >= 6 else "failed" if i == 5 else "answered"
                statuses[slot["id"]] = {"phase": "transfer", "status": outcome}
                if outcome == "not_started":
                    continue
                answer = "" if i == 5 else f'Answer {i}: café, "yes".\nLiteral </script><img src=x>.'
                self.answers.append(answer)
                self.put(self.results[n-1] / (slot["id"] + ".json"), {
                    "stage": stage, "study_id": repeat.STUDY, "batch_id": repeat.BATCH, "phase": "transfer",
                    "slot": slot["id"], "task": slot["question"]["id"], "condition": slot["condition"],
                    "repeat": slot["repeat"], "question": slot["question"]["query"], "outcome": outcome,
                    "answer": answer, "trace": "PRIVATE_TRACE", "total_cost_usd": "PRIVATE_COST",
                    "automatic_verdict": "PRIVATE_GRADE", "sent_query": "PRIVATE_PROMPT"})
            self.put(self.results[n-1] / "slot-status.json", {"slots": statuses})
            expected = self.slots[:6] if n == 1 else self.slots[6:]
            self.put(self.results[n-1] / "completed.json", {"completed": [s["id"] for s in expected],
                                                           "expected": 32 if n == 1 else 26})
        self.refresh_bindings()

    @staticmethod
    def put(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def refresh_bindings(self):
        self.put(self.backups[0] / "attempt1-command.json", self.configs[0])
        sha1 = repeat.digest(self.backups[0] / "attempt1-command.json")
        self.put(self.backups[0] / "attempt1.status.json", {"status": "stopped", "config_sha256": sha1})
        prior = {"prior_config_file": "prior/attempt1-command.json", "prior_status_file": "prior/attempt1.status.json",
                 "prior_schedule_file": "prior/attempt1.results/schedule.json",
                 "prior_slot_status_file": "prior/attempt1.results/slot-status.json"}
        prior["hashes"] = {"prior/" + str(p.relative_to(self.backups[0])): repeat.digest(p)
                           for p in self.backups[0].rglob("*.json")}
        self.configs[1].update(prior)
        self.put(self.backups[1] / "attempt2-command.json", self.configs[1])
        sha2 = repeat.digest(self.backups[1] / "attempt2-command.json")
        self.config_shas = (sha1, sha2)
        self.put(self.backups[1] / "attempt2.status.json", {"status": "complete", "config_sha256": sha2})
        self.refresh_checksums()

    def refresh_checksums(self):
        values = {}
        for n, backup in enumerate(self.backups, 1):
            values.update({("prior/" if n == 1 else "") + str(p.relative_to(backup)): repeat.digest(p)
                           for p in backup.rglob("*.json")})
        path = self.root / "attempt2-backup-sha256.json"
        self.put(path, values)
        self.checksums_sha = repeat.digest(path)

    def prepare(self):
        return repeat.prepare(*self.backups, self.tasks_file, self.bundle,
                              self.config_shas, self.tasks_sha, self.checksums_sha)

    def rows(self):
        return repeat.review.read_sheet(self.bundle / repeat.SHEET)

    def download(self, rows):
        self.incoming.write_text(repeat.review.csv_text(rows), encoding="utf-8-sig", newline="")

    def test_all32_including_empty_reply_preserved_with_blank_grades_and_safe_html(self):
        self.assertEqual(self.prepare(), 32)
        rows = self.rows()
        self.assertCountEqual([r["answer"] for r in rows], self.answers)
        self.assertEqual(sum(r["answer"] == "" for r in rows), 1)
        self.assertEqual(len({r["code"] for r in rows}), 32)
        self.assertTrue(all(not r["hand_verdict"] and not r["note"] for r in rows))
        html = (self.bundle / "review.html").read_text()
        payload = json.loads(html.split("const payload = ")[1].split(";\nconst columns")[0])
        self.assertEqual(set(payload), {"rows", "filename", "identity", "rules"})
        self.assertEqual(payload["rows"], rows)
        self.assertTrue(payload["identity"].startswith(repeat.BATCH + "-"))
        self.assertTrue(all(set(row) == set(repeat.review.COLUMNS) for row in rows))
        self.assertNotIn("PRIVATE_", html)
        self.assertNotIn(str(self.backups[0]), html)
        self.assertNotIn("Literal </script>", html)
        self.assertIn("Literal \\u003c/script>", html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn(".primary:hover{background:#23695c;color:#fff}", html)
        self.assertIn("<code>private-arm-key.json</code>", html)
        self.assertIn("have that CSV validated and imported before scoring.", html)
        self.assertNotIn("ask Codex to validate", html)
        mapping = repeat.read_json(self.bundle / "private-arm-key.json")["codes"]
        self.assertEqual(sum(v["outcome"] == "failed" for v in mapping.values()), 1)

    def test_absent_final_answer_is_blank_without_a_generated_verdict(self):
        path = self.results[0] / (self.slots[5]["id"] + ".json")
        record = repeat.read_json(path)
        self.put(path, {**record, "answer": None})
        self.refresh_bindings()
        self.prepare()
        empty = [row for row in self.rows() if row["answer"] == ""]
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0]["hand_verdict"], "")
        self.assertEqual(empty[0]["note"], "")

    def test_original_bundle_cannot_be_regenerated(self):
        self.prepare()
        before = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        with patch.object(repeat.secrets, "token_hex") as random:
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.prepare()
            random.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.bundle.iterdir()})

    def test_overlapping_missing_or_reordered_schedule_rejected(self):
        path = self.results[1] / "schedule.json"
        original = repeat.read_json(path)
        for slots in (self.slots[5:], self.slots[7:], list(reversed(self.slots[6:]))):
            self.put(path, {**original, "slots": slots})
            self.refresh_checksums()
            with self.assertRaisesRegex(ValueError, "disjoint coverage"):
                self.prepare()
            self.assertFalse(self.bundle.exists())

    def test_replayed_record_outside_schedule_rejected(self):
        source = self.results[0] / (self.slots[0]["id"] + ".json")
        shutil.copyfile(source, self.results[1] / source.name)
        self.refresh_checksums()
        with self.assertRaisesRegex(ValueError, "replayed"):
            self.prepare()

    def test_record_metadata_tampering_and_raw_checksum_mismatch_rejected(self):
        path = self.results[1] / (self.slots[6]["id"] + ".json")
        record = repeat.read_json(path)
        self.put(path, {**record, "condition": "changed"})
        with self.assertRaisesRegex(ValueError, "backup checksum"):
            self.prepare()
        self.refresh_checksums()
        with self.assertRaisesRegex(ValueError, "Trial metadata"):
            self.prepare()

    def test_prior_record_must_match_hash_bound_recovery_evidence(self):
        path = self.results[0] / (self.slots[0]["id"] + ".json")
        record = repeat.read_json(path)
        self.put(path, {**record, "answer": "Mutated synthetic answer"})
        self.refresh_checksums()
        with self.assertRaisesRegex(ValueError, "Retained first-attempt"):
            self.prepare()

    def test_incomplete_review_cannot_write_receipt(self):
        self.prepare()
        rows = self.rows()
        rows[0]["hand_verdict"] = "correct"
        self.download(rows)
        self.assertEqual(repeat.validate(self.bundle, self.incoming), (1, 32))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            repeat.validate(self.bundle, self.incoming, self.validated)
        self.assertFalse(self.validated.exists())

    def test_full_validation_is_blind_and_preserves_original(self):
        self.prepare()
        before = (self.bundle / repeat.SHEET).read_bytes()
        rows = [{**r, "hand_verdict": ("correct", "not correct", "unscorable")[i % 3], "note": "Student note"}
                for i, r in enumerate(self.rows())]
        self.download(list(reversed(rows)))
        (self.bundle / "private-arm-key.json").unlink()
        for p in self.backups:
            shutil.rmtree(p)
        self.tasks_file.unlink()
        with patch.object(repeat.review.subprocess, "run", side_effect=AssertionError("No scoring")):
            self.assertEqual(repeat.validate(self.bundle, self.incoming, self.validated), (32, 32))
        self.assertEqual(repeat.review.read_sheet(self.validated / "reviewed.csv"), rows)
        receipt = repeat.read_json(self.validated / "validation.json")
        self.assertTrue(receipt["complete"])
        self.assertFalse(receipt["arm_key_read"])
        self.assertFalse(receipt["scored"])
        self.assertEqual((self.bundle / repeat.SHEET).read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "already exists"):
            repeat.validate(self.bundle, self.incoming, self.validated)

    def test_immutable_changes_duplicates_missing_codes_and_invalid_verdicts_rejected(self):
        self.prepare()
        rows = [{**r, "hand_verdict": "correct"} for r in self.rows()]
        cases = [rows[:-1], rows + [rows[-1]], [{**rows[0], "hand_verdict": "maybe"}, *rows[1:]]]
        for field in repeat.review.IMMUTABLE:
            bad = copy.deepcopy(rows)
            bad[0][field] += " changed"
            cases.append(bad)
        for bad in cases:
            self.download(bad)
            with self.assertRaises(ValueError):
                repeat.validate(self.bundle, self.incoming, self.validated)
            self.assertFalse(self.validated.exists())


if __name__ == "__main__":
    unittest.main()
