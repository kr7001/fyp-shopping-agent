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


if __name__ == "__main__":
    unittest.main()
