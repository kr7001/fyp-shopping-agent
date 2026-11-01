"""Synthetic guard checks; no key or model request is read or sent."""
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("guarded_browser_use", ROOT / "tools/guarded_browser_use.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class Budget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {"cap_usd": 2, "minimum_balance_usd": 20, "deadline": "2099-01-01T00:00:00+08:00",
                       "model": "test/model", "provider": {"order": ["test"], "allow_fallbacks": False,
                       "max_price": {"prompt": .2, "completion": .5, "request": 0}},
                       "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
                       "allowed_served_providers": ["Test"]}
        self.snapshot = {"usage": 100, "remaining": 50}
        self.budget = guard.CallBudget(self.config, Path(self.tmp.name) / "ledger.json", lambda: dict(self.snapshot))
        self.metadata = {"model": "test/model", "provider": self.config["provider"],
                         "prompt_bytes": 1000, "max_output_tokens": 4096, "nontext_or_plugins": False}

    def response(self, cost=.02, provider="Test"):
        return {"id": "generation-1", "provider": provider, "usage": {"cost": cost, "prompt_tokens": 100}}

    def test_full_context_bound_and_actual_provider_charge(self):
        self.assertAlmostEqual(guard.request_bound(self.config, self.metadata), .2117632)
        ref = self.budget.before_call(self.metadata)
        self.budget.after_call(ref, self.response())
        self.assertEqual(self.budget.state["charged_usd"], .02)
        saved = json.loads(self.budget.path.read_text())
        self.assertEqual(saved["calls"][0]["generation_id"], "generation-1")

    def test_inflight_reservations_prevent_overlapping_overspend(self):
        self.budget.cap = .3
        self.budget.before_call(self.metadata)
        with self.assertRaisesRegex(guard.Stop, "cap"):
            self.budget.before_call(self.metadata)
        self.assertEqual(len(self.budget.state["inflight"]), 1)

    def test_actual_charges_count_even_when_account_lags(self):
        self.budget.cap = .23
        ref = self.budget.before_call(self.metadata)
        self.budget.after_call(ref, self.response())
        with self.assertRaisesRegex(guard.Stop, "cap"):
            self.budget.before_call(self.metadata)

    def test_account_decrease_cannot_restore_budget(self):
        self.budget.cap = .3
        self.snapshot["usage"] = 100.15
        with self.assertRaisesRegex(guard.Stop, "cap"):
            self.budget.before_call(self.metadata)
        self.snapshot["usage"] = 99
        with self.assertRaises(guard.Stop):
            self.budget.before_call(self.metadata)

    def test_highwater_remains_monotonic_without_prior_stop(self):
        self.snapshot["usage"] = 100.1
        ref = self.budget.before_call(self.metadata)
        self.budget.after_call(ref, self.response())
        self.snapshot.update(usage=99, remaining=80)
        self.budget.before_call(self.metadata)
        self.assertEqual(self.budget.state["highwater_usage"], 100.1)
        self.assertEqual(self.budget.state["minimum_remaining"], 50)
        self.assertEqual(self.budget.state["account_decreases"], 1)

    def test_unknown_charge_stops_even_retry(self):
        ref = self.budget.before_call(self.metadata)
        with self.assertRaisesRegex(guard.Stop, "unknown charge"):
            self.budget.after_call(ref, {"provider": "Test", "usage": {}})
        with self.assertRaisesRegex(guard.Stop, "unknown charge"):
            self.budget.before_call(self.metadata)

    def test_failed_call_with_known_charge_still_stops(self):
        ref = self.budget.before_call(self.metadata)
        with self.assertRaisesRegex(guard.Stop, "failed"):
            self.budget.after_call(ref, self.response(), error="HTTP error")
        self.assertEqual(self.budget.state["charged_usd"], .02)

    def test_request_cannot_exceed_input_output_or_model(self):
        for update in [{"prompt_bytes": 200001}, {"max_output_tokens": 4097}, {"model": "other"},
                       {"provider": {}}, {"nontext_or_plugins": True}]:
            with self.subTest(update=update), self.assertRaises(guard.Stop):
                guard.request_bound(self.config, {**self.metadata, **update})

    def test_wrong_price_wire_keys_are_rejected(self):
        bad = {**self.config, "provider": {"max_price": {"input": .2, "output": .5}}}
        with self.assertRaises(guard.Stop):
            guard.request_bound(bad, {**self.metadata, "provider": bad["provider"]})

    def test_missing_context_bound_is_rejected(self):
        with self.assertRaises(guard.Stop):
            guard.request_bound({**self.config, "maximum_input_tokens": None}, self.metadata)

    def test_reserve_is_separate_from_budget(self):
        self.snapshot["remaining"] = 20.2
        with self.assertRaisesRegex(guard.Stop, "reserve"):
            self.budget.before_call(self.metadata)

    def test_unknown_or_mismatched_provider_does_not_hide_charge(self):
        ref = self.budget.before_call(self.metadata)
        with self.assertRaisesRegex(guard.Stop, "provider"):
            self.budget.after_call(ref, self.response(provider="Other"))
        self.assertEqual(self.budget.state["charged_usd"], .02)

    def test_charge_exceeding_bound_blocks_subsequent_calls(self):
        ref = self.budget.before_call(self.metadata)
        with self.assertRaisesRegex(guard.Stop, "exceeded"):
            self.budget.after_call(ref, self.response(cost=.3))
        self.assertEqual(self.budget.state["charged_usd"], .3)

    def test_deadline_blocks_before_call(self):
        self.budget.clock = lambda: self.budget.deadline
        with self.assertRaisesRegex(guard.Stop, "deadline"):
            self.budget.before_call(self.metadata)

    def test_account_failure_blocks_before_call(self):
        def fail():
            raise RuntimeError("do not expose anything")
        self.budget.account_reader = fail
        with self.assertRaisesRegex(guard.Stop, "account or request validation failed"):
            self.budget.before_call(self.metadata)
        self.assertEqual(self.budget.state["calls"], [])

    def test_no_implicit_resume(self):
        with self.assertRaisesRegex(guard.Stop, "resume"):
            guard.CallBudget(self.config, self.budget.path, lambda: self.snapshot)

    def test_no_double_settlement(self):
        ref = self.budget.before_call(self.metadata)
        self.budget.after_call(ref, self.response())
        with self.assertRaisesRegex(guard.Stop, "settled"):
            self.budget.after_call(ref, self.response())

    def test_only_owned_process_group_is_terminated(self):
        child = mock.Mock(pid=12345)
        child.poll.return_value = None
        with mock.patch.object(guard.os, "killpg") as kill:
            guard.terminate_owned(child)
        kill.assert_called_once_with(12345, guard.signal.SIGTERM)

    def test_source_drift_is_checked_before_request(self):
        with mock.patch.object(guard, "verify_identity", side_effect=guard.Stop("source hash mismatch")):
            with self.assertRaisesRegex(guard.Stop, "source hash"):
                self.budget.before_call(self.metadata)
        self.assertFalse(self.budget.state["calls"])


class Account(unittest.TestCase):
    def test_effective_remaining_uses_smaller_of_key_allowance_and_actual_credit(self):
        for key_remaining, credit_remaining in [(50, 10), (10, 50)]:
            with self.subTest(key_remaining=key_remaining):
                responses = [io.BytesIO(json.dumps({"data": {"usage": 100, "limit_remaining": key_remaining}}).encode()),
                             io.BytesIO(json.dumps({"data": {"total_credits": 200, "total_usage": 200-credit_remaining}}).encode())]
                with mock.patch.object(guard.urllib.request, "urlopen", side_effect=responses) as get:
                    result = guard.account_snapshot("SYNTHETIC")
                self.assertEqual(result, {"usage": 100, "remaining": 10})
                self.assertEqual([c.args[0].full_url for c in get.call_args_list],
                                 ["https://openrouter.ai/api/v1/key", "https://openrouter.ai/api/v1/credits"])

    def test_unavailable_credit_balance_fails_closed_without_exposing_error(self):
        responses = [io.BytesIO(b'{"data":{"usage":100,"limit_remaining":50}}'), RuntimeError("PRIVATE")]
        with mock.patch.object(guard.urllib.request, "urlopen", side_effect=responses):
            with self.assertRaisesRegex(guard.Stop, "^account check failed; no further model call permitted$"):
                guard.account_snapshot("SYNTHETIC")


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.prior = {"charged_usd": .06264520106, "start_usage": 100, "highwater_usage": 100.07,
                      "inflight": {}, "calls": [{"cost_usd": .06264520106, "reserved_usd": .2117632},
                                                  {"cost_usd": None, "reserved_usd": .2117632}]}
        guard.atomic_json(self.repo / "prior.json", self.prior)
        guard.atomic_json(self.repo / "reconciliation.json", {
            "prior_ledger_sha256": guard.sha(self.repo / "prior.json"), "carryover_usd": .27440840106})
        self.config = {"stage": "pilot-recovery", "repo": str(self.repo), "prior_ledger_file": "prior.json",
                       "reconciliation_file": "reconciliation.json", "carryover_usd": .27440840106,
                       "shared_cap_usd": 2, "cap_usd": 1.70, "minimum_balance_usd": 20,
                       "deadline": "2099-01-01T00:00:00+08:00", "model": "test/model",
                       "provider": {"max_price": {"prompt": .2, "completion": .5, "request": 0}},
                       "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096}
        self.metadata = {"model": "test/model", "provider": self.config["provider"],
                         "prompt_bytes": 1000, "max_output_tokens": 4096, "nontext_or_plugins": False}

    def test_carryover_keeps_unknown_cost_as_reservation_not_charge(self):
        carry, reserve = guard.recovery_limits(self.config)
        self.assertAlmostEqual(carry, .27440840106)
        self.assertAlmostEqual(reserve, .2117632)
        self.assertIsNone(json.loads((self.repo / "prior.json").read_text())["calls"][1]["cost_usd"])

    def test_overnight_uses_same_prior_cost_not_a_new_budget(self):
        self.assertEqual(guard.recovery_limits({**self.config, "stage": "overnight-transfer"}),
                         guard.recovery_limits(self.config))

    def chain_config(self):
        second = {"charged_usd": .0579932904, "start_usage": 101, "highwater_usage": 101.05,
                  "inflight": {}, "calls": [{"cost_usd": .0579932904, "reserved_usd": .2117632}],
                  "carryover_usd": .27440840106, "prior_unsettled_reserve_usd": .2117632,
                  "prior_ledger_files": ["prior.json"]}
        guard.atomic_json(self.repo / "second.json", second)
        names = ["prior.json", "second.json"]
        carry = .33240169146
        guard.atomic_json(self.repo / "reconciliation.json", {
            "prior_ledger_sha256": {name: guard.sha(self.repo / name) for name in names}, "carryover_usd": carry})
        return {**self.config, "prior_ledger_files": names, "carryover_usd": carry, "cap_usd": 1.60}

    def test_multiple_prior_ledgers_carry_all_costs_without_double_counting_inherited_carry(self):
        config = self.chain_config()
        carry, pending = guard.recovery_limits(config)
        self.assertAlmostEqual(carry, .33240169146)
        self.assertAlmostEqual(pending, .2117632)
        budget = guard.CallBudget(config, self.repo / "new.json", lambda: {"usage": 102, "remaining": 50})
        self.assertEqual(budget.state["charged_usd"], 0)
        self.assertEqual(budget.state["prior_ledger_files"], ["prior.json", "second.json"])

    def test_missing_earlier_attempt_and_duplicate_ledgers_are_rejected(self):
        config = self.chain_config()
        del config["prior_ledger_file"]
        with self.assertRaisesRegex(guard.Stop, "earlier attempt"):
            guard.recovery_limits({**config, "prior_ledger_files": ["second.json"]})
        with self.assertRaisesRegex(guard.Stop, "unique"):
            guard.recovery_limits({**config, "prior_ledger_files": ["prior.json", "prior.json"]})

    def test_multiledger_reconciliation_binds_every_hash(self):
        config = self.chain_config()
        data = json.loads((self.repo / "reconciliation.json").read_text())
        del data["prior_ledger_sha256"]["second.json"]
        guard.atomic_json(self.repo / "reconciliation.json", data)
        with self.assertRaisesRegex(guard.Stop, "reconciliation"):
            guard.recovery_limits(config)

    def test_deadline_marks_running_and_unstarted_slots_without_changing_completed(self):
        output = self.repo / "output"
        guard.atomic_json(output / "slot-status.json", {"slots": {
            "done": {"status": "answered"}, "active": {"status": "running"}, "later": {"status": "scheduled"}}})
        guard.mark_unfinished({"output_dir": str(output)}, "absolute deadline reached")
        rows = json.loads((output / "slot-status.json").read_text())["slots"]
        self.assertEqual([rows[name]["status"] for name in ("done", "active", "later")],
                         ["answered", "time_censored", "not_started"])

    def test_shared_cap_cannot_be_reset(self):
        with self.assertRaisesRegex(guard.Stop, "shared"):
            guard.recovery_limits({**self.config, "cap_usd": 2})

    def test_understated_prior_cost_is_rejected(self):
        with self.assertRaisesRegex(guard.Stop, "omits"):
            guard.recovery_limits({**self.config, "carryover_usd": .07})

    def test_changed_prior_ledger_requires_new_reconciliation(self):
        self.prior["highwater_usage"] = 100.08
        guard.atomic_json(self.repo / "prior.json", self.prior)
        with self.assertRaisesRegex(guard.Stop, "reconciliation"):
            guard.recovery_limits(self.config)

    def test_late_prior_charge_is_reserved_against_account_balance(self):
        budget = guard.CallBudget(self.config, self.repo / "new.json", lambda: {"usage": 100.07, "remaining": 20.3})
        self.assertEqual(budget.state["charged_usd"], 0)
        with self.assertRaisesRegex(guard.Stop, "account reserve"):
            budget.before_call(self.metadata)

    def test_new_account_movement_cannot_hide_behind_carryover(self):
        snapshot = {"usage": 100.07, "remaining": 50}
        budget = guard.CallBudget(self.config, self.repo / "new.json", lambda: snapshot.copy())
        snapshot["usage"] += 1.5
        with self.assertRaisesRegex(guard.Stop, "spending cap"):
            budget.before_call(self.metadata)
        self.assertEqual(budget.state["charged_usd"], 0)
        self.assertAlmostEqual(budget.state["carryover_usd"], .27440840106)


if __name__ == "__main__":
    unittest.main()
