"""Synthetic launcher checks: temporary git repository, fake account, no network."""
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[2] / "tools/guarded_replication.py"
spec = importlib.util.spec_from_file_location("guarded_replication", MODULE)
guarded = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guarded)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "frozen").write_text("unchanged")
        subprocess.run(["git", "add", "frozen"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "fixture"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root).decode().strip()
        self.config_path = self.root / "config.json"
        self.config = {"repo": str(self.root), "expected_head": self.head,
                       "deadline": "2026-10-28T08:00:00+08:00", "cap_usd": 20, "reserve_usd": 1,
                       "hashes": {"frozen": guarded.sha(self.root / "frozen")},
                       "verification_receipt": "receipt.json", "manifest": "run.manifest",
                       "status": "status.json", "log_dir": "logs", "results_dir": "results", "steps": []}

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))
        (self.root / "receipt.json").write_text(json.dumps({"status": "PASS", "head": self.head,
                                                          "config_sha256": guarded.sha(self.config_path)}))

    def instance(self, account=None):
        self.write_config()
        command = [sys.executable, "-c", account or 'print(\'{"usage":100,"remaining":74}\')']
        guard = guarded.Guard(self.config_path, account_command=command)
        # Synthetic process tests must remain valid after the real dated deadline.
        # Dedicated authorization tests below still check the configured date limits.
        guard.shutdown_epoch = time.time() + 120
        guard.shutdown_monotonic = time.monotonic() + 120
        guard.launch_window = 0
        guard.poll_interval = .05
        guard.account_timeout = .25
        guard.kill_grace = .2
        return guard

    def step(self, code, **kwargs):
        return {"id": "one", "kind": "preflight", "argv": [sys.executable, "-c", code],
                "max_seconds": 5, **kwargs}

    def status(self):
        return json.loads((self.root / "status.json").read_text())

    def prior_round(self, recorded=3.5, usage=103.5):
        config = {**self.config, "status": "prior.status.json", "steps": [{"id": "done"}]}
        config_path = self.root / "prior.config.json"
        config_path.write_text(json.dumps(config))
        status = {"status": "complete", "reason": None, "current_step": None,
                  "config_sha256": guarded.sha(config_path), "start_usage": 100,
                  "last_usage": usage, "recorded_usd": recorded,
                  "spent_usd": max(usage - 100, recorded), "completed_steps": ["done"]}
        status_path = self.root / "prior.status.json"
        status_path.write_text(json.dumps(status))
        self.config.update(round=2, deadline="2026-10-28T21:00:00+08:00", prior_round={
            "status": str(status_path), "status_sha256": guarded.sha(status_path),
            "config": str(config_path), "config_sha256": guarded.sha(config_path)})
        return status_path

    def test_round_two_deadline_needs_completed_prior_evidence(self):
        self.config["deadline"] = "2026-10-28T21:00:00+08:00"
        with self.assertRaises(guarded.Stop):
            self.instance()
        self.config["round"] = 2
        with self.assertRaises(guarded.Stop):
            self.instance()
        self.config.pop("round")
        self.prior_round()
        self.assertEqual(self.instance().deadline,
                         dt.datetime.fromisoformat("2026-10-28T21:00:00+08:00"))
        self.config["deadline"] = "2026-10-29T03:00:00+08:00"
        self.assertEqual(self.instance().deadline, guarded.ROUND2_DEADLINE)
        self.config["deadline"] = "2026-10-29T03:00:01+08:00"
        with self.assertRaises(guarded.Stop):
            self.instance()

    def test_round_two_carries_recorded_spend_when_account_lags(self):
        self.prior_round(recorded=18.8, usage=103.5)
        self.config["steps"] = [self.step('open("bad","w").write("bad")', kind="paid", estimate_usd=.2)]
        guard = self.instance('print(\'{"usage":103.5,"remaining":70}\')')
        self.assertEqual(guard.run(), 2)
        self.assertEqual(self.status()["start_usage"], 100)
        self.assertEqual(self.status()["prior_recorded_usd"], 18.8)
        self.assertIn("budget", self.status()["reason"])
        self.assertFalse((self.root / "bad").exists())

    def test_round_two_counts_account_movement_between_rounds(self):
        self.prior_round()
        self.config["steps"] = [self.step('open("bad","w").write("bad")', kind="paid", estimate_usd=.1)]
        guard = self.instance('print(\'{"usage":118.9,"remaining":60}\')')
        self.assertEqual(guard.run(), 2)
        self.assertAlmostEqual(self.status()["spent_usd"], 18.9)
        self.assertFalse((self.root / "bad").exists())

    def test_round_two_extra_reserve_covers_unrecorded_prior_charges_when_account_lags(self):
        self.prior_round()
        unrecorded_prior_charge = 2.190728057
        self.config["reserve_usd"] = 3.20
        code = ('import pathlib,json,time;p=pathlib.Path("results/batch");p.mkdir();'
                '(p/"q-2.json").write_text(json.dumps({"cost_usd":13.3}));'
                'time.sleep(4);open("bad","w").write("bad")')
        self.config["steps"] = [self.step(code, kind="paid", estimate_usd=.2)]
        guard = self.instance('print(\'{"usage":103.5,"remaining":70}\')')
        self.assertEqual(guard.run(), 2)
        result = self.status()
        self.assertAlmostEqual(result["aggregate_recorded_usd"], 16.8)
        self.assertAlmostEqual(result["spent_usd"], 16.8)
        # The account is stale and the prior interrupted charge has no result row.
        # The configured extra reserve still leaves the original $1 safety buffer.
        self.assertLessEqual(result["spent_usd"] + unrecorded_prior_charge, 20 - 1)
        self.assertIn("budget", result["reason"])
        self.assertFalse((self.root / "bad").exists())

    def test_round_two_status_separates_current_and_aggregate_charges(self):
        self.prior_round()
        code = ('import pathlib,json;p=pathlib.Path("results/batch");p.mkdir();'
                'r={"task":"q","repeat":2,"log":"run.log","cost_usd":0.2};'
                '(p/"q-2.json").write_text(json.dumps(r));'
                '(p/"suite.json").write_text(json.dumps({"rows":[r]}));'
                'print("full results: "+str(p.resolve()))')
        self.config["steps"] = [self.step(code, kind="paid", estimate_usd=.2,
                                          output_kind="suite", expected_tasks=["q"], repeat=2)]
        guard = self.instance('print(\'{"usage":103.5,"remaining":70}\')')
        self.assertEqual(guard.run(), 0)
        result = self.status()
        self.assertEqual(result["start_usage"], 100)
        self.assertEqual(result["round_start_usage"], 103.5)
        self.assertAlmostEqual(result["recorded_usd"], .2)
        self.assertAlmostEqual(result["round_spent_usd"], .2)
        self.assertAlmostEqual(result["aggregate_recorded_usd"], 3.7)
        self.assertAlmostEqual(result["spent_usd"], 3.7)
        self.assertIn("usage 103.5000000000", (self.root / "run.manifest").read_text().splitlines()[0])

    def test_round_two_rejects_account_below_prior_usage(self):
        self.prior_round()
        guard = self.instance('print(\'{"usage":103,"remaining":70}\')')
        self.assertEqual(guard.run(), 2)
        self.assertIn("below the completed prior round", self.status()["reason"])

    def test_round_two_rechecks_prior_bytes_before_launch(self):
        status_path = self.prior_round()
        guard = self.instance()
        status_path.write_text(status_path.read_text() + " ")
        self.assertEqual(guard.run(), 2)
        self.assertFalse((self.root / "run.manifest").exists())
        with self.assertRaisesRegex(guarded.Stop, "hash mismatch"):
            self.instance()

    def test_round_two_rejects_incomplete_or_inconsistent_prior_status(self):
        status_path = self.prior_round()
        original = json.loads(status_path.read_text())
        for change in [{"status": "stopped"}, {"completed_steps": []},
                       {"spent_usd": 0}, {"config_sha256": "wrong"},
                       {"last_usage": 99}]:
            with self.subTest(change=change):
                status_path.write_text(json.dumps({**original, **change}))
                self.config["prior_round"]["status_sha256"] = guarded.sha(status_path)
                with self.assertRaises(guarded.Stop):
                    self.instance()

    def test_completion_records_batch_and_only_metadata(self):
        code = ('import pathlib,json; p=pathlib.Path("results/batch");p.mkdir();'
                'r={"task":"q","repeat":1,"log":"run.log","cost_usd":0.2};'
                '(p/"q-1.json").write_text(json.dumps(r));'
                '(p/"suite.json").write_text(json.dumps({"rows":[r]}));'
                'print("PRIVATE ANSWER SHOULD STAY IN LOG");print("full results: "+str(p.resolve()/"suite.json"))')
        self.config["steps"] = [self.step(code, kind="paid", estimate_usd=.2, output_kind="suite",
                                          expected_tasks=["q"], repeat=1,
                                          manifest_line_template="batch|{batch}|--only q")]
        guard = self.instance()
        self.assertEqual(guard.run(), 0)
        self.assertEqual(self.status()["status"], "complete")
        self.assertEqual(self.status()["completed_steps"], ["one"])
        self.assertAlmostEqual(self.status()["recorded_usd"], .2)
        self.assertNotIn("PRIVATE ANSWER", (self.root / "status.json").read_text())
        self.assertIn("batch|", (self.root / "run.manifest").read_text())

    def test_nonzero_exit_stops_following_step(self):
        self.config["steps"] = [self.step('raise SystemExit(7)'), self.step('open("bad","w").write("bad")', id="two")]
        self.assertEqual(self.instance().run(), 2)
        self.assertEqual(self.status()["reason"], "step exited unsuccessfully")
        self.assertFalse((self.root / "bad").exists())

    def test_account_failure_stops_running_child(self):
        account = ('import pathlib; p=pathlib.Path("reads"); n=int(p.read_text()) if p.exists() else 0;'
                   'p.write_text(str(n+1));print(\'{"usage":100,"remaining":74}\') if n<2 else exit(2)')
        self.config["steps"] = [self.step('import time;time.sleep(2);open("bad","w").write("bad")')]
        guard = self.instance(account)
        self.assertEqual(guard.run(), 2)
        self.assertEqual(self.status()["reason"], "account visibility lost")
        self.assertFalse((self.root / "bad").exists())

    def test_hanging_account_times_out_before_any_trial(self):
        guard = self.instance('import time;time.sleep(10)')
        start = time.monotonic()
        self.assertEqual(guard.run(), 2)
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(self.status()["reason"], "account read timed out")

    def test_budget_double_estimate_stops_before_child(self):
        self.config["steps"] = [self.step('open("bad","w").write("bad")', kind="paid", estimate_usd=9.6)]
        self.assertEqual(self.instance().run(), 2)
        self.assertIn("budget", self.status()["reason"])
        self.assertFalse((self.root / "bad").exists())

    def test_account_spend_watchdog_stops_child(self):
        account = ('import pathlib,json; p=pathlib.Path("reads"); n=int(p.read_text()) if p.exists() else 0;'
                   'p.write_text(str(n+1));print(json.dumps({"usage":100 if n<2 else 119.1,"remaining":74}))')
        self.config["steps"] = [self.step('import time;time.sleep(2);open("bad","w").write("bad")')]
        self.assertEqual(self.instance(account).run(), 2)
        self.assertIn("budget", self.status()["reason"])
        self.assertFalse((self.root / "bad").exists())

    def test_account_corrections_preserve_usage_high_water_and_credit_low_water(self):
        account = ('import pathlib,json;p=pathlib.Path("reads");n=int(p.read_text()) if p.exists() else 0;'
                   'p.write_text(str(n+1));'
                   'v=[(100,74),(101,73),(100.9,73.1),(101.2,72.8)][n];'
                   'print(json.dumps({"usage":v[0],"remaining":v[1]}))')
        guard = self.instance(account)
        guard.start_usage = 100
        for usage, remaining in [(100,74),(101,73),(101,73),(101.2,72.8)]:
            guard.poll_account(required=True)
            self.assertAlmostEqual(guard.usage, usage)
            self.assertAlmostEqual(guard.remaining, remaining)
            self.assertAlmostEqual(guard.spent(), usage - 100)
        self.assertEqual(guard.usage_decrease_count, 1)
        self.assertEqual(guard.observed_usage, 101.2)
        self.assertEqual(guard.observed_remaining, 72.8)
        self.assertEqual(guard.last_usage_decrease, {"from": 101, "to": 100.9})
        guard.manifest_created = True
        guard.status("running")
        self.assertEqual(self.status()["last_usage_decrease"], {"from": 101, "to": 100.9})

    def test_account_correction_cannot_restore_budget_or_credit_headroom(self):
        account = ('import pathlib,json;p=pathlib.Path("reads");n=int(p.read_text()) if p.exists() else 0;'
                   'p.write_text(str(n+1));v=[(119.1,20.9),(118,74)][n];'
                   'print(json.dumps({"usage":v[0],"remaining":v[1]}))')
        guard = self.instance(account)
        guard.start_usage = 100
        guard.poll_account(required=True)
        guard.poll_account(required=True)
        self.assertEqual(guard.observed_usage, 118)
        self.assertEqual(guard.observed_remaining, 74)
        self.assertEqual(guard.usage_decrease_count, 1)
        with self.assertRaisesRegex(guarded.Stop, "budget"):
            guard.budget_check()
        # Isolate the credit check: the higher new balance must not restore headroom.
        guard.start_usage = 119
        with self.assertRaisesRegex(guarded.Stop, "account reserve"):
            guard.budget_check()
        guard.manifest_created = True
        guard.status("stopped", "synthetic correction")
        self.assertEqual(self.status()["last_usage"], 119.1)
        self.assertEqual(self.status()["last_observed_usage"], 118)
        self.assertEqual(self.status()["remaining_credit_low_water"], 20.9)
        self.assertEqual(self.status()["usage_decrease_count"], 1)

    def test_existing_manifest_and_bad_receipt_refused(self):
        guard = self.instance()
        (self.root / "run.manifest").write_text("original")
        self.assertEqual(guard.run(), 2)
        self.assertEqual((self.root / "run.manifest").read_text(), "original")
        (self.root / "run.manifest").unlink()
        (self.root / "receipt.json").write_text('{}')
        self.assertEqual(guard.run(), 2)
        self.assertFalse((self.root / "run.manifest").exists())

    def test_changed_config_or_frozen_bytes_refused(self):
        guard = self.instance()
        self.config_path.write_text(self.config_path.read_text() + " ")
        self.assertEqual(guard.run(), 2)
        self.assertFalse((self.root / "run.manifest").exists())
        guard = self.instance()
        (self.root / "frozen").write_text("changed")
        self.assertEqual(guard.run(), 2)
        self.assertFalse((self.root / "run.manifest").exists())

    def test_missing_output_and_wrong_task_refused(self):
        self.config["steps"] = [self.step('print("done")', kind="paid", estimate_usd=.1,
                                          output_kind="suite", expected_tasks=["q"])]
        self.assertEqual(self.instance().run(), 2)
        self.assertEqual(self.status()["reason"], "missing or ambiguous batch completion marker")

    def test_wrong_task_completion_refused(self):
        code = ('import pathlib,json;p=pathlib.Path("results/batch");p.mkdir();'
                '(p/"suite.json").write_text(json.dumps({"rows":[{"task":"other","repeat":1}]}));'
                'print("full results: "+str(p.resolve()))')
        self.config["steps"] = [self.step(code, kind="paid", estimate_usd=.1,
                                          output_kind="suite", expected_tasks=["q"])]
        self.assertEqual(self.instance().run(), 2)
        self.assertEqual(self.status()["reason"], "batch tasks or repeats do not match the command")

    def test_completed_batch_preserved_when_post_run_account_fails(self):
        code = ('import pathlib,json;p=pathlib.Path("results/batch");p.mkdir();'
                '(p/"suite.json").write_text(json.dumps({"rows":[{"task":"q","repeat":1,"log":"x"}]}));'
                'print("full results: "+str(p.resolve()))')
        self.config["steps"] = [self.step(code, kind="paid", estimate_usd=.1,
                                          output_kind="suite", expected_tasks=["q"],
                                          manifest_line_template="batch|{batch}|--only q")]
        account = ('import pathlib; p=pathlib.Path("reads"); n=int(p.read_text()) if p.exists() else 0;'
                   'p.write_text(str(n+1));print(\'{"usage":100,"remaining":74}\') if n<2 else exit(2)')
        guard = self.instance(account)
        guard.poll_interval = 60
        self.assertEqual(guard.run(), 2)
        self.assertIn("batch|", (self.root / "run.manifest").read_text())
        self.assertEqual(self.status()["completed_steps"], ["one"])
        self.assertEqual(self.status()["reason"], "account visibility lost")

    def test_missing_account_remaining_fails_closed(self):
        self.assertEqual(self.instance('print(\'{"usage":100}\')').run(), 2)
        self.assertEqual(self.status()["reason"], "account visibility lost")

    def test_recorded_charge_stops_when_account_lags(self):
        code = ('import pathlib,json,time;p=pathlib.Path("results/batch");p.mkdir();'
                '(p/"q-1.json").write_text(json.dumps({"cost_usd":19.2}));'
                'time.sleep(4);open("bad","w").write("bad")')
        self.config["steps"] = [self.step(code)]
        self.assertEqual(self.instance().run(), 2)
        self.assertGreaterEqual(self.status()["recorded_usd"], 19.2)
        self.assertIn("budget", self.status()["reason"])
        self.assertFalse((self.root / "bad").exists())

    def test_paid_launch_requires_full_trial_window(self):
        self.config["steps"] = [self.step('open("bad","w").write("bad")', kind="paid", estimate_usd=.1,
                                          max_seconds=1920)]
        guard = self.instance()
        guard.launch_window = None
        guard.shutdown_monotonic = time.monotonic() + 1900
        self.assertEqual(guard.run(), 2)
        self.assertIn("insufficient time", self.status()["reason"])
        self.assertFalse((self.root / "bad").exists())

    def test_deadline_kills_group_including_term_ignoring_descendant(self):
        # Child and grandchild both ignore TERM, requiring process-group KILL.
        nested = 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)'
        code = ('import os,signal,subprocess,sys,time,json;signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                f'p=subprocess.Popen([sys.executable,"-c",{nested!r}]);'
                'open("pids","w").write(json.dumps([os.getpid(),p.pid]));time.sleep(30)')
        self.config["steps"] = [self.step(code, max_seconds=30)]
        guard = self.instance()
        guard.shutdown_monotonic = time.monotonic() + .8
        start = time.monotonic()
        self.assertEqual(guard.run(), 2)
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(self.status()["reason"], "absolute deadline shutdown")
        for pid in json.loads((self.root / "pids").read_text()):
            try:
                status = subprocess.check_output(["ps", "-o", "stat=", "-p", str(pid)], stderr=subprocess.DEVNULL).decode().strip()
            except subprocess.CalledProcessError:
                status = ""
            self.assertTrue(not status or status.startswith("Z"), (pid, status))


class AccountProbeTests(unittest.TestCase):
    def test_transient_read_then_success_is_retried_without_secret_output(self):
        response = io.BytesIO(b'{"data":{"usage":100,"limit_remaining":74}}')
        failures = [guarded.urllib.error.URLError("synthetic transient failure"), response]
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-key"}), \
             mock.patch.object(guarded.urllib.request, "urlopen", side_effect=failures) as opened, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(guarded.account_probe("unused"), 0)
            self.assertEqual(json.loads(stdout.getvalue()), {"usage": 100, "remaining": 74})
            self.assertEqual(opened.call_count, 2)
            self.assertTrue(all(0 < call.kwargs["timeout"] <= 2 for call in opened.call_args_list))

    def test_three_transient_failures_return_no_output(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-key"}), \
             mock.patch.object(guarded.urllib.request, "urlopen",
                               side_effect=guarded.urllib.error.URLError("synthetic failure")) as opened, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(guarded.account_probe("unused"), 2)
            self.assertEqual(opened.call_count, 3)
            self.assertEqual(stdout.getvalue(), "")

    def test_invalid_balance_fails_without_retry(self):
        response = io.BytesIO(b'{"data":{"usage":100,"limit_remaining":-1}}')
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "synthetic-test-key"}), \
             mock.patch.object(guarded.urllib.request, "urlopen", return_value=response) as opened, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(guarded.account_probe("unused"), 2)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
