"""Plain repeat scheduling and spending tests; synthetic inputs, no paid or browser calls."""
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
import paths
import browser_use_transfer as study
import guarded_browser_use as guard
import page


def question(name):
    url = "http://localhost:7770/catalogsearch/result/?q=Example"
    return {"id": name, "query": f"Go to {url} . Synthetic question {name}", "start_url": url}


def config(repo):
    base = Path(repo) / "notes/browser-use-repeat-1-nov"
    return {"stage": guard.REPEAT_STAGE, "study_budget_id": guard.REPEAT_BUDGET,
            "repo": str(repo), "attempt": 1, "carryover_usd": 0, "shared_cap_usd": 2,
            "cap_usd": 2, "estimate_usd": 1.6, "minimum_balance_usd": 20.2117632,
            "legacy_unsettled_reserve_usd": .2117632, "deadline": "2026-11-02T23:00:00+08:00",
            "questions": [question(t) for t in study.TASK_IDS], "repeats": [2, 3], "clock_s": 2700,
            **{field: str(base / name) for field, name in {
                "ledger_path": "attempt1.ledger.json", "status_path": "attempt1.status.json",
                "output_dir": "attempt1.results", "log_path": "attempt1.log"}.items()}}


class PlainRepeat(unittest.TestCase):
    def test32_fixed_slots_without_diagnostics_or_repeat1(self):
        plan = study.preview(config(ROOT))
        rows = plan["slots"]
        self.assertEqual(len(rows), 32)
        self.assertEqual(len({row["id"] for row in rows}), 32)
        self.assertEqual(plan["study_id"], study.STUDY_ID)
        self.assertEqual(plan["batch_id"], guard.REPEAT_BUDGET)
        self.assertTrue(all(row["phase"] == "transfer" and row["clock_s"] == 2700 for row in rows))
        self.assertEqual({row["repeat"] for row in rows}, {2, 3})
        for index in range(0, 16, 2):
            self.assertNotEqual(rows[index]["condition"], rows[index + 16]["condition"])
        for repeat in (2, 3):
            starts = [r["condition"] for r in rows[::2] if r["repeat"] == repeat]
            self.assertEqual(starts.count("baseline"), 4)
            self.assertEqual(starts.count("block"), 4)
        self.assertEqual(plan["paid_calls"], 0)

    def test_question_subset_repeat_or_clock_changes_rejected(self):
        original = config(ROOT)
        for change in ({"questions": original["questions"][:-1]}, {"repeats": [1, 2]},
                       {"repeats": [2]}, {"repeats": [3, 2]}, {"clock_s": 900}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "plain repeats"):
                study.preview({**original, **change})

    def test_budget_cannot_reset_reserve_or_create_recovery(self):
        original = config(ROOT)
        guard.validate_repeat_budget(original)
        for change in ({"attempt": 2}, {"carryover_usd": .1}, {"shared_cap_usd": 4}, {"cap_usd": 4},
                       {"minimum_balance_usd": 20}, {"legacy_unsettled_reserve_usd": 0},
                       {"prior_ledger_files": ["prior.json"]}, {"ledger_path": "/tmp/other.json"},
                       {"deadline": "2026-11-03T01:00:00+08:00"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_repeat_budget({**original, **change})

    def test_atomic_launch_claim_allows_one_worker_only(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(directory)
            Path(cfg["ledger_path"]).parent.mkdir(parents=True)
            command = Path(directory) / "command.json"
            command.write_text(json.dumps(cfg))
            def claim(_):
                try:
                    guard.claim_repeat_launch(cfg, command)
                    return "claimed"
                except guard.Stop:
                    return "denied"
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(claim, range(2)))
            self.assertCountEqual(outcomes, ["claimed", "denied"])
            marker = Path(cfg["ledger_path"]).with_name("attempt1.launch.json")
            self.assertEqual(json.loads(marker.read_text())["config_sha256"], guard.sha(command))
            with self.assertRaises(guard.Stop):
                guard.claim_repeat_launch(cfg, command)

    def test_monotonic_deadline_stops_after_wall_clock_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = {**config(directory), "model": "test/model", "provider": {"max_price": {
                "prompt": .2, "completion": .5, "request": 0}}, "maximum_input_tokens": 1048576,
                "max_input_bytes": 200000, "max_output_tokens": 4096}
            epoch = guard.deadline_epoch(cfg["deadline"])
            with mock.patch.object(guard.time, "monotonic", return_value=100):
                budget = guard.CallBudget(cfg, cfg["ledger_path"], lambda: {"usage": 10, "remaining": 50},
                                          clock=lambda: epoch - 100)
            budget.clock = lambda: epoch - 5000
            with mock.patch.object(guard.time, "monotonic", return_value=200):
                with self.assertRaisesRegex(guard.Stop, "deadline"):
                    budget.before_call({})
            self.assertEqual(budget.state["calls"], [])
            self.assertEqual(budget.state["study_budget_id"], guard.REPEAT_BUDGET)

    def test_browser_version_drift_rejected_and_historical_calls_unchanged(self):
        cfg = {**config(ROOT), "browser_executable": "synthetic", "preflight_browser_version": "156.0.8078.79"}
        with mock.patch.object(guard.subprocess, "run", return_value=types.SimpleNamespace(stdout="Chrome 156.0.8078.79")) as run:
            guard.verify_browser_version(cfg)
            guard.verify_browser_version({"stage": "monitored-transfer"})
            self.assertEqual(run.call_count, 1)
        for stdout in ("Chrome 157.0.0.0", "malformed"):
            with mock.patch.object(guard.subprocess, "run", return_value=types.SimpleNamespace(stdout=stdout)):
                with self.assertRaisesRegex(guard.Stop, "build changed"):
                    guard.verify_browser_version(cfg)


class FrozenIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.cfg = {**config(self.repo), "dependencies_lock": "requirements.lock",
                    "reference_config_file": "reference.json", "preflight_receipt": "preflight.json",
                    "preflight_browser_version": "156.0.8078.79"}
        files = ["experiments/runners/browser_use_runner.py", "tools/guarded_browser_use.py",
                 "experiments/runners/browser_use_transfer.py", "experiments/paths.py",
                 "experiments/box/parser.py", "requirements.lock"]
        for filename in files:
            target = self.repo / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("synthetic unchanged file\n")
        self.reference = {**self.cfg, "stage": "monitored-transfer", "transfer_questions": self.cfg["questions"],
                          "hashes": {name: guard.sha(self.repo / name) for name in files}}
        (self.repo / "reference.json").write_text(json.dumps(self.reference))
        self.receipt = {"verdict": "PASS", "study_id": guard.REPEAT_BUDGET, "model_calls": 0,
                        "browser_version": self.cfg["preflight_browser_version"],
                        "source_sha256": self.reference["hashes"]}
        (self.repo / "preflight.json").write_text(json.dumps(self.receipt))
        self.hash_patch = mock.patch.object(guard, "REFERENCE_CONFIG_SHA256", guard.sha(self.repo / "reference.json"))
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)
        self.version_patch = mock.patch.object(guard, "verify_browser_version")
        self.version_patch.start()
        self.addCleanup(self.version_patch.stop)

    def test_original_settings_and_runner_are_enforced(self):
        guard.validate_repeat_identity(self.cfg)
        for change in ({"temperature": .5}, {"model": "different"}, {"max_failures": 9},
                       {"questions": self.cfg["questions"][:-1]}, {"observation_contract": "variant-observation-v1"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_repeat_identity({**self.cfg, **change})
        runner = self.repo / "experiments/runners/browser_use_runner.py"
        runner.write_text("added observation fix")
        with self.assertRaisesRegex(guard.Stop, "frozen runner"):
            guard.validate_repeat_identity(self.cfg)

    def test_import_path_changes_fail_closed(self):
        (self.repo / "experiments/paths.py").write_text("different import paths")
        with self.assertRaisesRegex(guard.Stop, "frozen runner"):
            guard.validate_repeat_identity(self.cfg)

    def test_modified_reference_and_stale_preflight_fail_closed(self):
        (self.repo / "preflight.json").write_text(json.dumps({**self.receipt, "source_sha256": {}}))
        with self.assertRaisesRegex(guard.Stop, "predate"):
            guard.validate_repeat_identity(self.cfg)
        (self.repo / "reference.json").write_text("{}")
        with self.assertRaisesRegex(guard.Stop, "exact original"):
            guard.validate_repeat_identity(self.cfg)


class Execution(unittest.IsolatedAsyncioTestCase):
    async def test32_original_trials_no_pilot_no_observer_failures_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = {**config(directory), "environment_file": "unused"}
            budget = types.SimpleNamespace(state={"calls": [], "inflight": {}, "blocked_reason": None})
            trials = []
            async def run(trial, *_args, **_kwargs):
                trials.append(trial)
                outcome = {1: "failed", 2: "timeout"}.get(len(trials), "answered")
                return {"outcome": outcome, "timeout_kind": "trial_clock", "cost_usd": 0,
                        "trace": {"measurement_valid": True}, "answer": "synthetic answer"}
            adapter = types.SimpleNamespace(create_llm=mock.Mock(), close_llm=mock.AsyncMock(),
                                            run_trial=run, configure_private_runtime=mock.Mock())
            observed = page.Page(cfg["questions"][0]["start_url"], [page.Listing(
                "A", "Example tee", "http://localhost:7770/a.html", 9)], total=1, next_page=False, reader="rendered")
            with mock.patch.dict(sys.modules, {"browser_use_runner": adapter,
                   "browser_use.llm.messages": types.SimpleNamespace(UserMessage=mock.Mock())}), \
                 mock.patch.dict(study.os.environ, {"IGR_BROWSER_USE_GUARD": "test", "IGR_BROWSER_USE_CONFIG_SHA256": "hash"}), \
                 mock.patch.object(study, "validate_config", return_value=cfg), \
                 mock.patch.object(study, "sha", return_value="hash"), \
                 mock.patch.object(study, "read_key", return_value="SYNTHETIC"), \
                 mock.patch.object(study, "CallBudget", return_value=budget), \
                 mock.patch.object(study, "read_observation", return_value=observed), \
                 mock.patch.object(study, "verify_browser_version") as check_version, \
                 mock.patch.object(study, "technical_gate", side_effect=AssertionError("no new diagnostic gate")), \
                 mock.patch.object(study, "build_query", return_value=("synthetic unchanged query", None)):
                complete = await study.execute_study("unused")
            self.assertEqual(len(complete), 32)
            self.assertEqual(len(trials), 32)
            self.assertEqual(check_version.call_count, 32)
            self.assertTrue(all("observation_contract" not in trial for trial in trials))
            folder = Path(cfg["output_dir"])
            self.assertFalse((folder / "development-gate.json").exists())
            statuses = json.loads((folder / "slot-status.json").read_text())["slots"]
            self.assertEqual(statuses[complete[0]]["status"], "failed")
            self.assertEqual(statuses[complete[1]]["status"], "timeout")
            self.assertEqual(json.loads((folder / (complete[0] + ".json")).read_text())["batch_id"], guard.REPEAT_BUDGET)


if __name__ == "__main__":
    unittest.main()
