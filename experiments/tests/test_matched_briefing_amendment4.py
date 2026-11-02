"""Study B's later stages under amendment 4, 2 November 2026: a synthetic primary run in a
temporary folder, a fake account, no network, no model and no credential. The continuation runs
the primary run's uncompleted step (slot 16) unchanged under a shared USD 2.75 cap that carries
the primary run's spend. Each check is shown quiet on a good case and firing on a planted fault."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import guarded_matched_briefing as guarded  # noqa: E402
import fresh_market_launch as launch  # noqa: E402

FRESH = guarded.FRESH
STEM = guarded.FRESH_STEM
PROTOCOL = "experiments/tasks/matched_briefing_2_nov.json"
NOTES = "notes/fresh-market-2-nov"
FROZEN = ["experiments/runners/matched_briefing_study.py", "experiments/analysis/voids.py", ".env",
          "tools/guarded_matched_briefing.py", "tools/guarded_replication.py"]


def paid_step(slot, argv=None):
    args = ["--condition", slot["arm"], "--protocol", PROTOCOL, "--slot-id", str(slot["slot"]), "--tasks",
            "experiments/tasks/tasks_tee_fresh_2_nov.json", "--only", slot["task"], "--repeats", "1",
            "--repeat-start", str(slot["repeat"]), "--page-reader", "rendered", "--max-steps", "300",
            "--clock", "1800"]
    return {"id": f"slot-{slot['slot']:02d}-{slot['arm']}-{slot['task']}-r{slot['repeat']}", "kind": "paid",
            "study_slot": slot, "argv": argv or ["python3.11", "experiments/runners/matched_briefing_study.py", *args],
            "env": {"MODEL_NAME": "deepseek/deepseek-v4-flash"}, "max_seconds": 1920, "estimate_usd": 0.075,
            "output_kind": "suite", "expected_tasks": [slot["task"]], "repeat": slot["repeat"],
            "manifest_line_template": "batch|{batch}|" + " ".join(args)}


class Primary(unittest.TestCase):
    """The primary run as it stopped: the live check and slots 1 to 15 completed, slot 16
    started and stopped by the budget guard with no suite record, as on 2 November."""
    git_checks = [{"cwd": "agent/agent-core", "head": "a" * 40, "diff_sha256": "b" * 64}]
    live_argv = ["python", "env/check_aplus_market.py", "--fixture", "tee_fresh_2_nov.json", "--no-browser"]
    slot16_argv = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.schedule = json.loads((paths.TASKS / "matched_briefing_29_oct.json").read_text())["schedule"]
        self.write(PROTOCOL, {"study_id": FRESH, "status": "frozen", "schedule": self.schedule})
        for name in FROZEN:
            self.write_text(name, f"synthetic {name}\n")
        self.write_text(f"{NOTES}/amendment-4-2-nov.md", "synthetic amendment 4\n")
        steps = [{"id": "live-market-check", "kind": "preflight", "argv": self.live_argv, "max_seconds": 180,
                  "env": {}}]
        steps += [paid_step(slot, self.slot16_argv if slot["slot"] == 16 else None) for slot in self.schedule]
        self.primary = {"repo": str(self.root), "expected_head": "b1c67c8", "study_id": FRESH, "protocol": PROTOCOL,
                        "round": 1, "deadline": "2026-11-02T23:59:00+08:00", "cap_usd": 2.0, "reserve_usd": 0.5,
                        "manifest": f"{STEM}.manifest", "status": f"{STEM}.status.json", "log_dir": f"{STEM}.logs",
                        "results_dir": "experiments/results", "verification_receipt": f"{NOTES}/study-b.verification.json",
                        "review_sheet": f"{STEM}.sheet.csv", "review_html": f"{NOTES}/study-b-review.html",
                        "preparation_log": f"{STEM}.preparation.log",
                        "preparation_status": f"{STEM}.preparation.status.json",
                        "git_checks": self.git_checks, "manifest_header": ["study " + FRESH + " synthetic"],
                        "declared_estimate_usd": 1.2,
                        "hashes": {name: guarded.original.sha(self.root / name) for name in FROZEN + [PROTOCOL]},
                        "steps": steps}
        self.primary["hashes"]["tools/guarded_matched_briefing.py"] = "0" * 64  # the launcher as it ran then
        path = self.write(guarded.FRESH_PRIMARY_CONFIG, self.primary)
        self.patch(guarded, "FRESH_PRIMARY_SHA256", guarded.original.sha(path))
        self.stop_primary()
        for name, value in (("ROOT", self.root), ("NOTES", self.root / NOTES)):
            self.patch(launch, name, value)
        self.patch(launch, "head", lambda: "a4-head")
        self.patch(launch, "agent_check", lambda: self.git_checks)
        self.patch(launch, "chrome_build", lambda executable: "156.0.8078.79")

    def patch(self, owner, name, value):
        patcher = mock.patch.object(owner, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_text(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def write(self, relative, data):
        return self.write_text(relative, json.dumps(data))

    def stop_primary(self, completed=15, partial=True, status="stopped"):
        """The primary run's manifest, status and launcher logs after `completed` slots."""
        lines = ["start 2026-11-02T03:16:06 usage 136.2722801760 cap 2.00", "study " + FRESH + " synthetic"]
        for slot in self.schedule[:completed]:
            folder = self.root / f"experiments/results/2026110200{slot['slot']:02d}"
            self.write(f"experiments/results/{folder.name}/suite.json", {"rows": [{"task": slot["task"]}]})
            lines.append(paid_step(slot)["manifest_line_template"].format(batch=folder))
        lines.append("STOP budget stop or insufficient budget for next step")
        self.write_text(self.primary["manifest"], "\n".join(lines) + "\n")
        ids = [step["id"] for step in self.primary["steps"]]
        for i in range(completed + 1):
            self.write_text(f"{STEM}.logs/{i:03d}.log", "synthetic launcher log\n")
        stray = self.root / f"{STEM}.logs/{completed + 1:03d}.log"
        stray.unlink(missing_ok=True)
        if partial:
            folder = self.root / "experiments/results/20261102T062351"
            self.write_text(f"experiments/results/{folder.name}/tee-count-buyable-2.log", "a run log\n")
            self.write_text(str(stray.relative_to(self.root)), "study: {}\n1 tasks x 1 repeats = 1 runs, repeats 2 to 2 "
                                                               f"-> {folder}\nlimits: max steps 300, clock 1800 s\n")
        self.write(self.primary["status"], {"status": status, "reason": "budget stop or insufficient budget for next step",
                                            "config_sha256": guarded.FRESH_PRIMARY_SHA256,
                                            "recorded_usd": 1.3311680000000004, "spent_usd": 1.5038982959999885,
                                            "current_step": ids[completed + 1] if partial else None,
                                            "completed_steps": ids[:completed + 1]})

    def build(self, ruling="The student's synthetic ruling", **options):
        output = self.root / NOTES / "study-b-continuation-command.json"
        output.unlink(missing_ok=True)
        with redirect_stdout(io.StringIO()):
            launch.b_continuation(output, ruling, **options)
        return output, json.loads(output.read_text())


class Continuation(Primary):
    def test_runs_slot_16_unchanged_after_the_same_live_check(self):
        path, config = self.build()
        validated, _ = guarded.validate_config(path)
        self.assertEqual(validated["steps"], [self.primary["steps"][0], self.primary["steps"][16]])
        self.assertEqual(validated["steps"][1]["argv"][-2:], ["--clock", "1800"])
        self.assertEqual((config["stage"], config["cap_usd"], config["reserve_usd"], config["shared_cap_usd"]),
                         ("continuation", 2.75, 0.25, 2.75))
        self.assertEqual(config["carryover_usd"], 1.5038982959999885)  # the larger of recorded and account spend
        self.assertEqual((config["deadline"], config["start_cutoff"]),
                         ("2026-11-03T12:00:00+08:00", "2026-11-03T12:00:00+08:00"))
        self.assertEqual((config["manifest"], config["status"], config["log_dir"]),
                         (f"{STEM}.continuation.manifest", f"{STEM}.continuation.status.json",
                          f"{STEM}.continuation.logs"))
        self.assertNotIn("review_sheet", config)
        self.assertEqual(config["git_checks"], self.primary["git_checks"])
        for name in (guarded.FRESH_PRIMARY_CONFIG, self.primary["status"], self.primary["manifest"],
                     f"{STEM}.logs/016.log", guarded.AMENDMENT):
            self.assertIn(name, config["hashes"])

    def test_a_started_slot_needs_a_recorded_ruling(self):
        with self.assertRaisesRegex(SystemExit, "started slot-16.*amendment 4 point 4"):
            self.build(ruling=None)
        path, config = self.build()
        self.assertEqual(config["partial_run"]["step"], "slot-16-matched-briefing-tee-count-buyable-r2")
        self.assertEqual((config["partial_run"]["suite_written"], config["partial_run"]["results_files"]),
                         (False, ["tee-count-buyable-2.log"]))
        for change in ({"partial_run_ruling": " "}, {"partial_run": None},
                       {"partial_run": {**config["partial_run"], "log_sha256": "0" * 64}}):
            with self.subTest(change=change), self.assertRaisesRegex(guarded.original.Stop, "ruling"):
                path.write_text(json.dumps({**config, **change}))
                guarded.validate_config(path)
        # Without a started step there is nothing to rule on, and naming one is refused.
        self.stop_primary(partial=False)
        path, config = self.build(ruling=None)
        self.assertNotIn("partial_run", config)
        path.write_text(json.dumps({**config, "partial_run": {"step": "invented"}}))
        with self.assertRaisesRegex(guarded.original.Stop, "names a partial run"):
            guarded.validate_config(path)

    def test_other_steps_changed_steps_or_a_slot_with_a_result_are_refused(self):
        path, config = self.build()
        clocked = copy.deepcopy(config["steps"])
        clocked[1]["argv"][-1] = "3600"
        for steps in (clocked, config["steps"] + [self.primary["steps"][15]], config["steps"][:1],
                      [self.primary["steps"][15], config["steps"][1]]):
            with self.subTest(steps=[s["id"] for s in steps]), self.assertRaisesRegex(guarded.original.Stop, "uncompleted steps"):
                path.write_text(json.dumps({**config, "steps": steps}))
                guarded.validate_config(path)
        # Slot 16 with a line in the primary manifest has a result and is never run again.
        path.write_text(json.dumps(config))
        manifest = self.root / self.primary["manifest"]
        manifest.write_text(manifest.read_text() + paid_step(self.schedule[15])["manifest_line_template"].format(
            batch=self.root / "experiments/results/x") + "\n")
        config["hashes"][self.primary["manifest"]] = guarded.original.sha(manifest)
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(guarded.original.Stop, "has a result"):
            guarded.validate_config(path)

    def test_the_cap_reserve_carryover_paths_and_cutoff_are_fixed(self):
        path, config = self.build()
        for change, message in (({"cap_usd": 2.0}, "cap differs"), ({"cap_usd": 3.0}, "cap differs"),
                                ({"reserve_usd": 0.5}, "reserve"), ({"shared_cap_usd": 3.0}, "reserve"),
                                ({"carryover_usd": 1.3311680000000004}, "counted spend"),
                                ({"manifest": self.primary["manifest"]}, "own manifest"),
                                ({"status": self.primary["status"]}, "own manifest"),
                                ({"start_cutoff": "2026-11-03T12:00:01+08:00"}, "start cutoff"),
                                ({"deadline": "2026-11-03T12:00:01+08:00"}, "deadline"),
                                ({"git_checks": [{**self.git_checks[0], "head": "c" * 40}]}, "agent"),
                                ({"stage": "replay"}, "later stages"),
                                ({"study_id": guarded.STUDY}, "later stages")):
            with self.subTest(change=change), self.assertRaisesRegex(guarded.original.Stop, message):
                path.write_text(json.dumps({**config, **change}))
                guarded.validate_config(path)
        earlier = self.build(deadline="2026-11-03T08:00:00+08:00", start_cutoff="2026-11-03T07:00:00+08:00")[1]
        self.assertEqual((earlier["deadline"], earlier["start_cutoff"]),
                         ("2026-11-03T08:00:00+08:00", "2026-11-03T07:00:00+08:00"))

    def test_the_primary_run_must_have_ended_and_its_files_kept(self):
        path, config = self.build()
        self.write_text("experiments/runners/matched_briefing_study.py", "an executor change\n")
        with self.assertRaisesRegex(SystemExit, "matched_briefing_study.py"):
            self.build()
        path.write_text(json.dumps(config))
        moved = {**config["hashes"], "experiments/runners/matched_briefing_study.py": "1" * 64}
        path.write_text(json.dumps({**config, "hashes": moved}))
        with self.assertRaisesRegex(guarded.original.Stop, "changed a file the primary run ran with"):
            guarded.validate_config(path)
        self.write_text("experiments/runners/matched_briefing_study.py", "synthetic experiments/runners/matched_briefing_study.py\n")
        # The launchers themselves may change.
        renewed = {**config["hashes"], "tools/guarded_matched_briefing.py": "2" * 64}
        path.write_text(json.dumps({**config, "hashes": renewed}))
        guarded.validate_config(path)
        self.stop_primary(status="running")
        with self.assertRaisesRegex(SystemExit, "not ended"):
            self.build()
        rebound = {name: guarded.original.sha(self.root / name) for name in config["hashes"]}
        path.write_text(json.dumps({**config, "hashes": rebound}))  # only the status itself says it
        with self.assertRaisesRegex(guarded.original.Stop, "terminal status"):
            guarded.validate_config(path)

    def test_the_primary_runs_own_configuration_still_validates(self):
        path = self.root / guarded.FRESH_PRIMARY_CONFIG
        cfg, _ = guarded.validate_config(path)
        self.assertEqual((cfg["cap_usd"], cfg.get("stage")), (2.0, None))


class Guard(Primary):
    def test_reserve_carryover_cutoff_and_status_of_a_later_stage(self):
        path, config = self.build()
        guard = guarded.MatchedGuard(path, account_command=["unused-synthetic"])
        self.assertEqual((guard.stage, guard.cap, guard.reserve, guard.carryover, guard.MIN_RESERVE_USD),
                         ("continuation", 2.75, 0.25, 1.5038982959999885, 0.25))
        guard.start_usage, guard.usage, guard.recorded = 100.0, 100.4, 0.1
        self.assertAlmostEqual(guard.spent(), 1.5038982959999885 + 0.4, places=12)
        fields = guard.status_fields()
        self.assertEqual((fields["stage"], fields["running_trial_stop_usd"], fields["shared_cap_usd"]),
                         ("continuation", 2.5, 2.75))
        self.assertAlmostEqual(fields["stage_spent_usd"], 0.4, places=12)
        with mock.patch.object(guarded.time, "time", return_value=guard.start_cutoff), \
                mock.patch.object(guarded.original.Guard, "execute_step") as parent:
            with self.assertRaisesRegex(guarded.original.Stop, "start cutoff"):
                guard.execute_step(config["steps"][1])
            guard.execute_step(config["steps"][0])  # the free live check is not a trial
            parent.assert_called_once()
        with mock.patch.object(guarded.time, "time", return_value=guard.start_cutoff - 1), \
                mock.patch.object(guarded.original.Guard, "execute_step") as parent:
            guard.execute_step(config["steps"][1])
            parent.assert_called_once()
        path.write_text(json.dumps({**config, "reserve_usd": 0.2}))
        with self.assertRaises(guarded.original.Stop):
            guarded.MatchedGuard(path, account_command=["unused-synthetic"])

    def test_a_later_stage_prepares_no_review_sheet_and_the_primary_still_does(self):
        for stage, sheet in (("continuation", False), (None, True)):
            with self.subTest(stage=stage), \
                    mock.patch.object(guarded, "validate_config", return_value=({"repo": str(self.root)}, {})), \
                    mock.patch.object(guarded, "check_key_context"), \
                    mock.patch.object(guarded, "MatchedGuard") as made, \
                    mock.patch.object(guarded, "prepare_review", return_value=0) as review, \
                    mock.patch.object(sys, "argv", ["guarded_matched_briefing.py", "--config", "c.json"]):
                made.return_value.stage, made.return_value.run.return_value = stage, 0
                self.assertEqual(guarded.main(), 0)
                self.assertEqual(review.called, sheet)

    def test_the_primary_runs_guard_is_unchanged(self):
        guard = guarded.MatchedGuard(self.root / guarded.FRESH_PRIMARY_CONFIG, account_command=["unused-synthetic"])
        self.assertEqual((guard.stage, guard.carryover, guard.start_cutoff, guard.MIN_RESERVE_USD), (None, 0.0, None, 0.5))
        guard.start_usage, guard.usage, guard.recorded = 100.0, 100.4, 0.1
        self.assertEqual((guard.spent(), guard.status_fields()), (guarded.original.Guard.spent(guard), {}))


class Thresholds(Primary):
    """The shared cap's two stops, run through the replication guard in a temporary git checkout
    with a fake account: the live check sleeps, slot 16 only leaves a mark that it started."""
    live_argv = [sys.executable, "-c", "import time; time.sleep(1.5)"]
    slot16_argv = [sys.executable, "-c", "open('slot16-started', 'w').write('x'); raise SystemExit(1)"]
    git_checks = []

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit",
                        "--allow-empty", "-qm", "fixture"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root).decode().strip()
        self.patch(guarded, "check_key_context", lambda root: None)

    def run_with(self, delta):
        """The continuation with the account's usage rising by `delta` once the live check runs."""
        path, config = self.build()
        config.update(expected_head=self.head, verification_receipt=str(self.root / "receipt.json"))
        for name in ("manifest", "status", "log_dir"):
            target = self.root / config[name]
            if target.is_dir():
                for child in target.iterdir():
                    child.unlink()
                target.rmdir()
            target.unlink(missing_ok=True)
        (self.root / "slot16-started").unlink(missing_ok=True)
        path.write_text(json.dumps(config))
        (self.root / "receipt.json").write_text(json.dumps({"status": "PASS", "head": self.head,
                                                            "config_sha256": guarded.original.sha(path)}))
        account = ("import pathlib,json;p=pathlib.Path('reads');n=int(p.read_text()) if p.exists() else 0;"
                   f"p.write_text(str(n+1));print(json.dumps({{'usage':100 if n<2 else 100+{delta},'remaining':74}}))")
        (self.root / "reads").unlink(missing_ok=True)
        guard = guarded.MatchedGuard(path, account_command=[sys.executable, "-c", account])
        guard.shutdown_epoch, guard.shutdown_monotonic = time.time() + 120, time.monotonic() + 120
        guard.start_cutoff = time.time() + 120  # valid after the real cutoff has passed
        guard.launch_window, guard.poll_interval, guard.account_timeout, guard.kill_grace = 0, .05, .5, .2
        code = guard.run()
        status = json.loads((self.root / config["status"]).read_text())
        return code, status, (self.root / "slot16-started").exists()

    def test_a_running_trial_stops_at_two_fifty_counted(self):
        code, status, started = self.run_with(1.0)  # 1.5039 carried + 1.0 seen
        self.assertEqual(code, 2)
        self.assertIn("budget", status["reason"])
        self.assertEqual((status["current_step"], status["completed_steps"], started), ("live-market-check", [], False))
        self.assertAlmostEqual(status["spent_usd"], 2.5038982959999885, places=9)
        self.assertEqual((status["stage"], status["running_trial_stop_usd"]), ("continuation", 2.5))

    def test_no_trial_starts_once_spend_plus_twice_its_estimate_reaches_two_fifty(self):
        code, status, started = self.run_with(0.85)  # 2.3539 + 2 x 0.075 = 2.5039
        self.assertEqual((code, status["completed_steps"], started), (2, ["live-market-check"], False))
        self.assertIn("insufficient budget for next step", status["reason"])
        code, status, started = self.run_with(0.84)  # 2.3439 + 0.15 = 2.4939: slot 16 starts
        self.assertEqual((code, status["completed_steps"], started), (2, ["live-market-check"], True))
        self.assertIn("step exited unsuccessfully", status["reason"])


if __name__ == "__main__":
    unittest.main()
