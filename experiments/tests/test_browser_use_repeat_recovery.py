"""Synthetic single-continuation checks; no model, credentials or real answers."""
import concurrent.futures
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.tests.test_browser_use_repeat import config as initial_config
import browser_use_transfer as study
import guarded_browser_use as guard


class RepeatRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.prior_root = self.repo / "prior"
        self.results = self.prior_root / "attempt1.results"
        self.results.mkdir(parents=True)
        self.original = initial_config(self.repo)
        self.plan = study.preview(self.original)
        self.slots = self.plan["slots"]
        self.prior_config = self.write("prior/attempt1-command.json", self.original)
        self.source_sha = guard.sha(self.prior_config)
        patcher = mock.patch.object(guard, "REPEAT_ATTEMPT1_SHA256", self.source_sha)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write("prior/attempt1.status.json", {"status": "stopped", "config_sha256": self.source_sha})
        self.write("prior/attempt1.results/schedule.json", self.plan)
        statuses = {}
        for i, slot in enumerate(self.slots):
            outcome = ("failed" if i == 5 else "answered") if i < 6 else "not_started"
            statuses[slot["id"]] = {"phase": "transfer", "status": outcome}
            if i < 6:
                self.write("prior/attempt1.results/" + slot["id"] + ".json", {
                    "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                    "condition": slot["condition"], "phase": "transfer", "batch_id": guard.REPEAT_BUDGET,
                    "outcome": outcome, "answer": "Synthetic content never used for eligibility"})
        self.write("prior/attempt1.results/slot-status.json", {"slots": statuses})
        self.write("prior/attempt1.results/completed.json", {"completed": [s["id"] for s in self.slots[:6]], "expected": 32})
        self.ledger = {"study_budget_id": guard.REPEAT_BUDGET, "attempt": 1, "shared_cap_usd": 2,
                       "carryover_usd": 0, "inflight": {}, "blocked_reason": None, "calls": [
                           {"cost_usd": guard.REPEAT_CARRYOVER_USD / 424, "reserved_usd": .2117632} for _ in range(424)],
                       "charged_usd": guard.REPEAT_CARRYOVER_USD, "start_usage": 100,
                       "highwater_usage": 100 + guard.REPEAT_CARRYOVER_USD, "prior_ledger_files": []}
        self.write("prior/attempt1.ledger.json", self.ledger)
        self.write("reconciliation.json", {"prior_ledger_sha256": {
            "prior/attempt1.ledger.json": guard.sha(self.prior_root / "attempt1.ledger.json")},
            "carryover_usd": guard.REPEAT_CARRYOVER_USD})
        self.cfg = {**self.original, "stage": guard.REPEAT_RECOVERY_STAGE, "attempt": 2,
                    "carryover_usd": guard.REPEAT_CARRYOVER_USD, "cap_usd": 2-guard.REPEAT_CARRYOVER_USD,
                    "estimate_usd": 1.3, "prior_config_file": "prior/attempt1-command.json",
                    "prior_status_file": "prior/attempt1.status.json",
                    "prior_slot_status_file": "prior/attempt1.results/slot-status.json",
                    "prior_schedule_file": "prior/attempt1.results/schedule.json",
                    "prior_ledger_file": "prior/attempt1.ledger.json",
                    "prior_ledger_files": ["prior/attempt1.ledger.json"], "reconciliation_file": "reconciliation.json"}
        for field in ("ledger_path", "status_path", "output_dir", "log_path"):
            self.cfg[field] = self.cfg[field].replace("attempt1.", "attempt2.")
        self.refresh_hashes()

    def write(self, relative, data):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def refresh_hashes(self):
        self.cfg["hashes"] = {str(p.relative_to(self.repo)): guard.sha(p) for p in self.repo.rglob("*.json")}

    def test_exact_unstarted_suffix_preserves_all_six_terminal_records(self):
        guard.validate_repeat_budget(self.cfg)
        plan = study.preview(self.cfg)
        self.assertEqual(plan["slots"], self.slots[6:])
        self.assertEqual(len(plan["slots"]), 26)
        self.assertEqual(plan["prior_completed_count"], 6)
        self.assertEqual(plan["original_slot_count"], 32)
        self.assertEqual(plan["batch_id"], guard.REPEAT_BUDGET)
        failed = self.slots[5]["id"]
        self.assertNotIn(failed, [s["id"] for s in plan["slots"]])
        self.assertEqual(json.loads((self.results / (failed + ".json")).read_text())["outcome"], "failed")

    def test_replay_or_skipping_a_slot_is_rejected(self):
        status = json.loads((self.results / "slot-status.json").read_text())
        for index, replacement in ((5, "not_started"), (6, "answered"), (8, "running")):
            bad = copy.deepcopy(status)
            bad["slots"][self.slots[index]["id"]]["status"] = replacement
            self.write("prior/attempt1.results/slot-status.json", bad)
            self.refresh_hashes()
            with self.assertRaisesRegex(guard.Stop, "six terminal"):
                study.preview(self.cfg)

    def test_reordered_schedule_rejected_even_when_rehashed(self):
        changed = copy.deepcopy(self.plan)
        changed["slots"][6], changed["slots"][7] = changed["slots"][7], changed["slots"][6]
        self.write("prior/attempt1.results/schedule.json", changed)
        self.refresh_hashes()
        with self.assertRaisesRegex(guard.Stop, "prior schedule"):
            study.preview(self.cfg)

    def test_running_prior_or_wrong_config_binding_rejected(self):
        for status in ({"status": "running", "config_sha256": self.source_sha},
                       {"status": "stopped", "config_sha256": "wrong"}):
            self.write("prior/attempt1.status.json", status)
            self.refresh_hashes()
            with self.assertRaisesRegex(guard.Stop, "terminal stopped"):
                study.preview(self.cfg)

    def test_changed_record_or_missing_hash_rejected(self):
        relative = "prior/attempt1.results/" + self.slots[0]["id"] + ".json"
        self.cfg["hashes"].pop(relative)
        with self.assertRaisesRegex(guard.Stop, "hash-bound"):
            study.preview(self.cfg)
        self.refresh_hashes()
        path = self.repo / relative
        record = json.loads(path.read_text())
        record["answer"] = "Mutated synthetic answer"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(guard.Stop, "changed after"):
            study.preview(self.cfg)

    def test_unsettled_or_understated_charge_cannot_recover(self):
        for update in ({"inflight": {"pending": {"reserved_usd": .2117632}}},
                       {"calls": [{"cost_usd": None, "reserved_usd": .2117632}]},
                       {"charged_usd": guard.REPEAT_CARRYOVER_USD + .01}):
            self.write("prior/attempt1.ledger.json", {**self.ledger, **update})
            self.refresh_hashes()
            with self.assertRaises(guard.Stop):
                study.preview(self.cfg)

    def test_no_attempt3_budget_reset_or_increased_shared_cap(self):
        for change in ({"attempt": 3}, {"carryover_usd": 0}, {"cap_usd": 2}, {"shared_cap_usd": 4},
                       {"minimum_balance_usd": 20}, {"ledger_path": self.original["ledger_path"]}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_repeat_budget({**self.cfg, **change})

    def test_attempt2_exclusive_launch_marker(self):
        command = self.write("command.json", self.cfg)
        Path(self.cfg["ledger_path"]).parent.mkdir(parents=True, exist_ok=True)
        def claim(_):
            try:
                guard.claim_repeat_launch(self.cfg, command)
                return True
            except guard.Stop:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(claim, range(2))), [True, False])
        marker = Path(self.cfg["ledger_path"]).with_name("attempt2.launch.json")
        self.assertEqual(json.loads(marker.read_text())["attempt"], 2)


class IndependentReview(unittest.TestCase):
    def setUp(self):
        self.command = ["python", "guard.py", "--config", "synthetic.json", "--execute"]
        self.receipt = {"verdict": "PASS", "config_sha256": "synthetic-hash", "head": "synthetic-head",
                        "request_bound_verified": True, "verifier": "codex-independent",
                        "independent": True, "reviewer_identity": "browser_transfer_analysis",
                        "command": self.command}

    def check(self, receipt, stage=guard.REPEAT_RECOVERY_STAGE):
        guard.validate_review_receipt({"stage": stage}, receipt, "synthetic-head", "synthetic-hash", self.command)

    def test_actual_independent_recovery_reviewer_is_identified(self):
        self.check(self.receipt)
        for change in ({"verifier": "claude"}, {"reviewer_identity": "coder"}, {"independent": False}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                self.check({**self.receipt, **change})

    def test_receipt_cannot_authorize_another_command_or_unverified_bound(self):
        for change in ({"config_sha256": "other"}, {"head": "other"}, {"command": ["different"]},
                       {"verdict": "FAIL"}, {"request_bound_verified": False}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                self.check({**self.receipt, **change})

    def test_original_attempt_verifier_requirement_is_unchanged(self):
        self.check({**self.receipt, "verifier": "claude"}, guard.REPEAT_STAGE)
        with self.assertRaises(guard.Stop):
            self.check(self.receipt, guard.REPEAT_STAGE)


class ErrorClassification(unittest.TestCase):
    def test_exact_absent_node_messages_are_retained_as_ordinary_failures(self):
        for message in ("Element index -1 not found in browser state", "Element index 42 not found in browser state"):
            record = {"outcome": "failed", "trace": {"measurement_valid": True}, "agent_errors": [message]}
            study.validate_pilot_record(record, "transfer")
            self.assertEqual(record["outcome"], "failed")

    def test_infrastructure_and_near_matches_still_stop(self):
        for message in ("Element index -1 not found in browser state: CDP disconnected",
                        "CDP disconnected", "Element index -1 not found in browser state then crashed",
                        "Error: Element index -1 not found in browser state", "Unknown action failed"):
            record = {"outcome": "failed", "trace": {"measurement_valid": True}, "agent_errors": [message]}
            with self.subTest(message=message), self.assertRaisesRegex(study.Stop, "infrastructure or unknown"):
                study.validate_pilot_record(record, "transfer")


if __name__ == "__main__":
    unittest.main()
