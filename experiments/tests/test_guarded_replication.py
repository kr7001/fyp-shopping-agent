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
