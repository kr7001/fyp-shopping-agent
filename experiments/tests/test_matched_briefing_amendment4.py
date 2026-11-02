"""Study B's later stages under amendment 4, 2 November 2026: a synthetic primary run in a
temporary folder, a fake account, no network, no model and no credential. The continuation runs
the primary run's uncompleted step (slot 16) unchanged under a shared USD 4 cap that carries
the primary run's spend, and the reruns run their primary steps through a reviewed wrapper that
doubles the clock and changes nothing else. Each check is shown quiet on a good case and firing on a planted fault."""
import contextlib
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
# The primary run's recorded charges and account spend, as its status holds them on 2 November, and
# the charges of the two completions the synthetic partial run's log shows.
RECORDED, ACCOUNT, PARTIAL = 1.3311680000000004, 1.5038982959999885, 0.2
CARRY = RECORDED + PARTIAL  # the larger: recorded plus the partial run's charges
COMPLETION = "usage=CompletionUsage(completion_tokens=5, prompt_tokens=10, total_tokens=15), cost=0.1, is_byok=False\n"


def paid_step(slot, argv=None, python="python3.11"):
    args = ["--condition", slot["arm"], "--protocol", PROTOCOL, "--slot-id", str(slot["slot"]), "--tasks",
            "experiments/tasks/tasks_tee_fresh_2_nov.json", "--only", slot["task"], "--repeats", "1",
            "--repeat-start", str(slot["repeat"]), "--page-reader", "rendered", "--max-steps", "300",
            "--clock", "1800"]
    return {"id": f"slot-{slot['slot']:02d}-{slot['arm']}-{slot['task']}-r{slot['repeat']}", "kind": "paid",
            "study_slot": slot, "argv": argv or [python, "experiments/runners/matched_briefing_study.py", *args],
            "env": {"MODEL_NAME": "deepseek/deepseek-v4-flash"}, "max_seconds": 1920, "estimate_usd": 0.075,
            "output_kind": "suite", "expected_tasks": [slot["task"]], "repeat": slot["repeat"],
            "manifest_line_template": "batch|{batch}|" + " ".join(args)}


class Primary(unittest.TestCase):
    """The primary run as it stopped: the live check and slots 1 to 15 completed, slot 16
    started and stopped by the budget guard with no suite record, as on 2 November."""
    git_checks = [{"cwd": "agent/agent-core", "head": "a" * 40, "diff_sha256": "b" * 64}]
    live_argv = ["python", "env/check_aplus_market.py", "--fixture", "tee_fresh_2_nov.json", "--no-browser"]
    argv_for = {}  # a slot's own argv, where a test runs it
    python = "python3.11"
    # The primary records: slots 7 and 14 reached their 1800 s clock, as on 2 November; slot 3 is
    # a clock stop the void rules void, its log silent for longer than they allow.
    timeouts = {7: 1801.1, 14: 1800.7}
    silent_clock = {3}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.schedule = json.loads((paths.TASKS / "matched_briefing_29_oct.json").read_text())["schedule"]
        self.write(PROTOCOL, {"study_id": FRESH, "status": "frozen", "schedule": self.schedule})
        for name in FROZEN:
            self.write_text(name, f"synthetic {name}\n")
        self.write_text(f"{NOTES}/amendment-4-2-nov.md", "synthetic amendment 4\n")
        self.write_text(guarded.RERUN_RUNNER, (ROOT / guarded.RERUN_RUNNER).read_text())  # the reviewed wrapper
        steps = [{"id": "live-market-check", "kind": "preflight", "argv": self.live_argv, "max_seconds": 180,
                  "env": {}}]
        steps += [paid_step(slot, self.argv_for.get(slot["slot"]), self.python) for slot in self.schedule]
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
        # The replication guard's tests as they were then: they changed with its probe's retries.
        self.write_text("experiments/tests/test_guarded_replication.py", "synthetic tests, now\n")
        self.primary["hashes"]["experiments/tests/test_guarded_replication.py"] = "1" * 64
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

    def stop_primary(self, completed=15, partial=True, status="stopped", spent=ACCOUNT):
        """The primary run's manifest, status and launcher logs after `completed` slots."""
        lines = ["start 2026-11-02T03:16:06 usage 136.2722801760 cap 2.00", "study " + FRESH + " synthetic"]
        for slot in self.schedule[:completed]:
            folder = self.root / f"experiments/results/2026110200{slot['slot']:02d}"
            self.slot_record(folder, slot)
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
            self.write_text(f"experiments/results/{folder.name}/tee-count-buyable-2.log", "a run log\n" + 2 * COMPLETION)
            self.write_text(str(stray.relative_to(self.root)), "study: {}\n1 tasks x 1 repeats = 1 runs, repeats 2 to 2 "
                                                               f"-> {folder}\nlimits: max steps 300, clock 1800 s\n")
        self.write(self.primary["status"], {"status": status, "reason": "budget stop or insufficient budget for next step",
                                            "config_sha256": guarded.FRESH_PRIMARY_SHA256,
                                            "recorded_usd": RECORDED, "spent_usd": spent,
                                            "current_step": ids[completed + 1] if partial else None,
                                            "completed_steps": ids[:completed + 1]})

    def slot_record(self, folder, slot, timed_out=None):
        """One slot's suite row, run record and log, as the frozen runner writes them."""
        tag = f"{slot['task']}-{slot['repeat']}"
        clock = slot["slot"] in self.timeouts or slot["slot"] in self.silent_clock if timed_out is None else timed_out
        elapsed = self.timeouts.get(slot["slot"], 1800.4) if clock else 420.0
        ended = "task_timeout: exceeded 1800s" if clock else ""
        self.write(f"experiments/results/{folder.name}/suite.json", {"rows": [{
            "task": slot["task"], "repeat": slot["repeat"], "log": tag + ".log", "elapsed_s": elapsed,
            "error": ended or None}]})
        self.write(f"experiments/results/{folder.name}/{tag}.json", {
            "result": {"ok": not clock, "final": "" if clock else "Synthetic answer, never judged", "error": ended},
            "clock_s": 1800, "elapsed_s": elapsed, "cost_usd": 0.25 if clock else 0.05, "error": None})
        stamps = ("2026-11-02 04:00:00 | start\n2026-11-02 04:02:00 | step\n" if slot["slot"] in self.silent_clock
                  else "2026-11-02 04:00:00 | start\n2026-11-02 04:00:30 | step\n")
        self.write_text(f"experiments/results/{folder.name}/{tag}.log", stamps)

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
                         ("continuation", 4.0, 0.35, 4.0))
        # The recorded charges plus the partial run's, larger here than the account's spend.
        self.assertEqual(config["carryover_usd"], CARRY)
        self.assertEqual((config["partial_run"]["charges_usd"], config["partial_run"]["charged_calls"]), (PARTIAL, 2))
        self.assertIn("experiments/results/20261102T062351/tee-count-buyable-2.log", config["hashes"])
        self.assertEqual(config["declared_estimate_usd"], 0.45)
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

    def test_the_account_counts_when_it_shows_more(self):
        self.stop_primary(spent=1.6)  # more than the recorded charges plus the partial run's
        self.assertEqual(self.build()[1]["carryover_usd"], 1.6)

    def test_the_partial_runs_logs_must_be_bound(self):
        path, config = self.build()
        for name in ("experiments/results/20261102T062351/tee-count-buyable-2.log", f"{STEM}.logs/016.log"):
            with self.subTest(unbound=name), self.assertRaisesRegex(guarded.original.Stop, "hash-bound"):
                path.write_text(json.dumps({**config, "hashes": {k: v for k, v in config["hashes"].items() if k != name}}))
                guarded.validate_config(path)

    def test_a_partial_run_with_a_completion_without_its_charge_is_refused(self):
        log = self.root / "experiments/results/20261102T062351/tee-count-buyable-2.log"
        log.write_text(log.read_text() + "usage=CompletionUsage(completion_tokens=5, prompt_tokens=10, total_tokens=15)\n")
        with self.assertRaisesRegex(SystemExit, "without its charge"):
            self.build()

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
                                ({"carryover_usd": RECORDED}, "counted spend"),
                                ({"carryover_usd": ACCOUNT}, "counted spend"),
                                ({"declared_estimate_usd": 0.1}, "estimate"),
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
                         ("continuation", 4.0, 0.35, CARRY, 0.35))
        guard.start_usage, guard.usage, guard.recorded = 100.0, 100.4, 0.1
        self.assertAlmostEqual(guard.spent(), CARRY + 0.4, places=12)
        fields = guard.status_fields()
        self.assertEqual((fields["stage"], fields["running_trial_stop_usd"], fields["shared_cap_usd"]),
                         ("continuation", 3.65, 4.0))
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


class ThresholdRun(Primary):
    """A later stage run through the replication guard in a temporary git checkout with a fake
    account: the live check sleeps, and a slot's own argv, where given, only leaves a mark."""
    live_argv = [sys.executable, "-c", "import time; time.sleep(1.5)"]
    git_checks = []

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit",
                        "--allow-empty", "-qm", "fixture"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root).decode().strip()
        self.patch(guarded, "check_key_context", lambda root: None)

    def run_with(self, delta, build=None, mark="slot16-started"):
        """A later stage, the continuation unless `build` says otherwise, with the account's usage
        rising by `delta` once the live check runs."""
        for later in guarded.LATER.values():  # each run starts with no later stage launched
            for name in ("manifest", "status", "log_dir"):
                target = self.root / later[name]
                if target.is_dir():
                    for child in target.iterdir():
                        child.unlink()
                    target.rmdir()
                target.unlink(missing_ok=True)
        path, config = (build or self.build)()
        config.update(expected_head=self.head, verification_receipt=str(self.root / "receipt.json"))
        (self.root / mark).unlink(missing_ok=True)
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
        return code, status, (self.root / mark).exists()


class Thresholds(ThresholdRun):
    """The shared cap's two stops for the continuation: slot 16 only leaves a mark that it started."""
    argv_for = {16: [sys.executable, "-c", "open('slot16-started', 'w').write('x'); raise SystemExit(1)"]}

    def test_a_running_trial_stops_at_three_sixty_five_counted(self):
        code, status, started = self.run_with(2.12)  # 1.5312 carried + 2.12 seen = 3.6512
        self.assertEqual(code, 2)
        self.assertIn("budget", status["reason"])
        self.assertEqual((status["current_step"], status["completed_steps"], started), ("live-market-check", [], False))
        self.assertAlmostEqual(status["spent_usd"], CARRY + 2.12, places=9)
        self.assertEqual((status["stage"], status["running_trial_stop_usd"]), ("continuation", 3.65))

    def test_slot_16_starts_only_below_three_fifty(self):
        code, status, started = self.run_with(1.97)  # 3.5012 + 2 x 0.075 = 3.6512
        self.assertEqual((code, status["completed_steps"], started), (2, ["live-market-check"], False))
        self.assertIn("insufficient budget for next step", status["reason"])
        code, status, started = self.run_with(1.96)  # 3.4912 + 0.15 = 3.6412: slot 16 starts
        self.assertEqual((code, status["completed_steps"], started), (2, ["live-market-check"], True))
        self.assertIn("step exited unsuccessfully", status["reason"])



class Reruns(Primary):
    def build_rerun(self, **options):
        output = self.root / NOTES / "study-b-rerun-command.json"
        output.unlink(missing_ok=True)
        with redirect_stdout(io.StringIO()):
            launch.b_rerun(output, **options)
        return output, json.loads(output.read_text())

    def end_continuation(self, timed_out=True, status="stopped", spent=1.7):
        """The continuation as its guard leaves it: slot 16's record and its manifest, status and logs."""
        slot = self.schedule[15]
        folder = self.root / "experiments/results/20261102T1300"
        self.slot_record(folder, slot, timed_out=timed_out)
        later = guarded.LATER[guarded.CONTINUATION]
        self.write_text(later["manifest"], "start x\n" + paid_step(slot)["manifest_line_template"].format(batch=folder) + "\n")
        self.write_text(later["log_dir"] + "/000.log", "live check\n")
        self.write(later["status"], {"status": status, "stage": "continuation", "carryover_usd": CARRY,
                                     "spent_usd": spent, "stage_spent_usd": spent - CARRY})

    def test_every_clock_timeout_once_in_slot_order_with_only_the_clock_doubled(self):
        path, config = self.build_rerun()
        guarded.validate_config(path)
        paid = config["steps"][1:]
        self.assertEqual([step["rerun_of"]["slot"] for step in paid], [7, 14])  # slot 3's run is void
        self.assertEqual(config["steps"][0], self.primary["steps"][0])
        for step, slot in zip(paid, (7, 14)):
            primary = self.primary["steps"][slot]
            self.assertEqual((step["argv"][0], step["argv"][2:-1]), (primary["argv"][0], primary["argv"][2:-1]))
            self.assertEqual((primary["argv"][1], step["argv"][1]), (guarded.FROZEN_RUNNER, guarded.RERUN_RUNNER))
            self.assertEqual((primary["argv"][-1], step["argv"][-1]), ("1800", "3600"))
            self.assertEqual((step["max_seconds"], step["estimate_usd"], step["id"]),
                             (3720, 0.30, "rerun-" + primary["id"]))
            same = ("kind", "study_slot", "env", "output_kind", "expected_tasks", "repeat")
            self.assertEqual({k: step[k] for k in same}, {k: primary[k] for k in same})
            folder = self.root / f"experiments/results/2026110200{slot:02d}"
            self.assertEqual(step["rerun_of"]["batch"], str(folder))
            self.assertTrue(step["manifest_line_template"].startswith(
                f"rerun|{{batch}}|stage timeout-rerun|primary {folder}|"))
            self.assertTrue(step["manifest_line_template"].endswith("--clock 3600"))
        self.assertEqual((config["stage"], config["carryover_usd"], config["declared_estimate_usd"]),
                         ("timeout-rerun", CARRY, 1.0))  # 2 x (0.25 + 0.25)
        self.assertIn(guarded.RERUN_RUNNER, config["hashes"])
        self.assertEqual((config["manifest"], config["status"]),
                         (f"{STEM}.rerun.manifest", f"{STEM}.rerun.status.json"))

    def test_a_slot_that_is_not_a_timeout_or_listed_twice_is_refused(self):
        path, config = self.build_rerun()
        answered = guarded.rerun_step(self.primary["steps"][1], {**config["steps"][1]["rerun_of"], "slot": 1})
        for steps, message in ((config["steps"] + [answered], "slot 1 is not a timeout"),
                               (config["steps"] + config["steps"][1:2], "rerun once only"),
                               (config["steps"][:2], "every timed-out slot"),
                               ([config["steps"][0]] + config["steps"][1:][::-1], "every timed-out slot")):
            with self.subTest(message=message), self.assertRaisesRegex(guarded.original.Stop, message):
                path.write_text(json.dumps({**config, "steps": steps}))
                guarded.validate_config(path)
        clock = copy.deepcopy(config["steps"])
        clock[1]["argv"][-1] = "5400"
        path.write_text(json.dumps({**config, "steps": clock}))
        with self.assertRaisesRegex(guarded.original.Stop, "every timed-out slot"):
            guarded.validate_config(path)

    def test_a_second_rerun_and_any_stage_after_the_reruns_are_refused(self):
        path, config = self.build_rerun()
        continuation_path, continuation = self.build()
        self.write_text(f"{STEM}.rerun.manifest", "start x\n")  # the reruns have been launched
        for later in (path, continuation_path):
            with self.subTest(later=later.name), self.assertRaisesRegex(guarded.original.Stop, "rerun once only"):
                guarded.validate_config(later)
        with self.assertRaisesRegex(SystemExit, "rerun once"):
            self.build_rerun()

    def test_the_continuations_spend_and_its_timed_out_slot_are_carried(self):
        self.end_continuation(timed_out=True)
        path, config = self.build_rerun()
        self.assertEqual([step["rerun_of"]["slot"] for step in config["steps"][1:]], [7, 14, 16])
        self.assertEqual(config["carryover_usd"], 1.7)
        for name in (guarded.LATER[guarded.CONTINUATION]["status"], guarded.LATER[guarded.CONTINUATION]["manifest"]):
            self.assertIn(name, config["hashes"])
        path.write_text(json.dumps({**config, "carryover_usd": CARRY}))
        with self.assertRaisesRegex(guarded.original.Stop, "counted spend"):
            guarded.validate_config(path)
        self.end_continuation(timed_out=False)
        self.assertEqual([step["rerun_of"]["slot"] for step in self.build_rerun()[1]["steps"][1:]], [7, 14])
        self.end_continuation(status="running")
        with self.assertRaisesRegex(SystemExit, "terminal status"):
            self.build_rerun()

    def test_only_the_reviewed_wrapper_runs_a_rerun(self):
        path, config = self.build_rerun()
        self.write_text(guarded.RERUN_RUNNER, (ROOT / guarded.RERUN_RUNNER).read_text() + "# changed\n")
        with self.assertRaisesRegex(guarded.original.Stop, "not the reviewed one"):
            guarded.validate_config(path)
        self.write_text(guarded.RERUN_RUNNER, (ROOT / guarded.RERUN_RUNNER).read_text())
        guarded.validate_config(path)
        path.write_text(json.dumps({**config, "hashes": {k: v for k, v in config["hashes"].items()
                                                         if k != guarded.RERUN_RUNNER}}))
        with self.assertRaisesRegex(guarded.original.Stop, "hash-bound"):
            guarded.validate_config(path)
        frozen = copy.deepcopy(config["steps"])
        frozen[1]["argv"][1] = guarded.FROZEN_RUNNER  # the frozen runner would refuse its 3600 s
        path.write_text(json.dumps({**config, "steps": frozen}))
        with self.assertRaisesRegex(guarded.original.Stop, "every timed-out slot"):
            guarded.validate_config(path)
        self.assertEqual(guarded.original.sha(ROOT / guarded.RERUN_RUNNER), guarded.RERUN_RUNNER_SHA256)

    def test_a_primary_record_changed_after_binding_is_refused(self):
        path, config = self.build_rerun()
        record = self.root / config["steps"][1]["rerun_of"]["record"]
        record.write_text(record.read_text().replace("1800.4", "1800.5").replace("1801.1", "1801.2"))
        with self.assertRaisesRegex(guarded.original.Stop, "every timed-out slot|changed after it was bound"):
            guarded.validate_config(path)

    def test_nothing_to_rerun_writes_nothing(self):
        self.timeouts = {}
        self.stop_primary()
        with self.assertRaisesRegex(SystemExit, "nothing to rerun"):
            self.build_rerun()
        self.assertFalse((self.root / NOTES / "study-b-rerun-command.json").exists())

    def test_only_the_reruns_guard_allows_their_longer_wall_budget(self):
        path, _ = self.build_rerun()
        self.assertEqual(guarded.MatchedGuard(path, account_command=["unused"]).MAX_STEP_SECONDS, 3720)
        continuation_path, _ = self.build()
        self.assertEqual(guarded.MatchedGuard(continuation_path, account_command=["unused"]).MAX_STEP_SECONDS, 1920)
        self.assertEqual(guarded.original.Guard.MAX_STEP_SECONDS, 1920)


class RerunThresholds(ThresholdRun):
    """A rerun's estimate is USD 0.30, so it starts only below USD 3.05 counted. The wrapper is
    stood in for by one that leaves a mark with the arguments it was given, pinned in its place."""
    python = sys.executable

    def setUp(self):
        super().setUp()
        stub = self.write_text(guarded.RERUN_RUNNER, "import sys\nopen('slot7-started', 'w').write(' '.join(sys.argv[1:]))\n"
                                                     "raise SystemExit(1)\n")
        self.patch(guarded, "RERUN_RUNNER_SHA256", guarded.original.sha(stub))

    def build_rerun(self):
        return Reruns.build_rerun(self)

    def test_a_rerun_starts_below_three_oh_five_and_runs_with_its_longer_wall_budget(self):
        code, status, started = self.run_with(1.52, build=self.build_rerun, mark="slot7-started")  # 3.0512 + 0.60
        self.assertEqual((code, status["completed_steps"], started), (2, ["live-market-check"], False))
        self.assertIn("insufficient budget for next step", status["reason"])
        code, status, started = self.run_with(1.51, build=self.build_rerun, mark="slot7-started")  # 3.0412 + 0.60
        self.assertEqual((code, started), (2, True))
        self.assertIn("step exited unsuccessfully", status["reason"])  # not refused for its 3720 s budget
        self.assertEqual(status["stage"], "timeout-rerun")
        self.assertTrue((self.root / "slot7-started").read_text().endswith("--slot-id 7 --tasks "
                        "experiments/tasks/tasks_tee_fresh_2_nov.json --only tee-count-buyable --repeats 1 "
                        "--repeat-start 1 --page-reader rendered --max-steps 300 --clock 3600"))


def form(quantifier, k=None):
    """A model parser's reply in the form the recorded replies hold: no market in it."""
    return json.dumps({"quantifier": quantifier, "objective": "price", "population": "results", "k": k,
                       "filters": [{"attribute": "size", "op": "=", "value": "M"},
                                   {"attribute": "availability", "op": "=", "value": "buyable"}],
                       "negated": False, "reading": None, "unknowns": [], "ambiguities": [], "evidence": {}})


class WrapperDryRun(unittest.TestCase):
    """Every rerun's exact argv, free: through the wrapper with --dry-run (and parser replies for
    the full block), the page read and every model call stood in for, nothing written. From the
    committed protocol's slots 7 and 14 as the primary configuration's builder writes them, and,
    in a checkout that holds them, from the real primary configuration and manifest."""

    def dry_run(self, step, replies):
        import matched_briefing as matched
        import matched_briefing_rerun as wrapper
        import page
        import suite
        owner = tempfile.TemporaryDirectory()
        self.addCleanup(owner.cleanup)
        argv = step["argv"][2:] + ["--dry-run"]
        if step["study_slot"]["arm"] == "full-block":
            argv += ["--parser-replies", str(replies)]
        url = "http://localhost:7770/catalogsearch/result/?q=Rookmere"
        observed = page.Page(url, [page.Listing(name, f"Rookmere Tee - {name}", f"http://localhost:7770/r-{i}.html", price)
                                   for i, (name, price) in enumerate((("Ash", 12), ("Elm", 15), ("Oak", 9)), 1)],
                             3, False, (url,), "rendered")
        with contextlib.chdir(ROOT), \
                mock.patch.object(matched, "STUDY_ID", matched.STUDY_ID), \
                mock.patch.object(suite, "RESULTS", Path(owner.name)), \
                mock.patch.object(suite, "run_once", side_effect=AssertionError("no executor in a dry run")), \
                mock.patch.object(suite, "agent_model", return_value="deepseek/deepseek-v4-flash"), \
                mock.patch.object(suite, "agent_code_identity", return_value={"agent_core_commit": "b" * 40,
                                                                              "agent_core_patch": "c" * 40}), \
                mock.patch.object(page, "read", return_value=observed), \
                mock.patch.object(suite.plan_probe, "load_key", return_value="synthetic-key"), \
                mock.patch.object(suite.parse_probe, "call_model", side_effect=AssertionError("no parser call")), \
                redirect_stdout(io.StringIO()) as said, contextlib.redirect_stderr(io.StringIO()) as errors:
            try:
                code = wrapper.main(argv)
            except SystemExit as stop:
                code = stop.code
        text = said.getvalue() + errors.getvalue()
        self.assertEqual(code, 0, text[-600:])
        self.assertIn("clock 3600 s", text)
        self.assertEqual(list(Path(owner.name).iterdir()), [])  # nothing written

    def test_the_committed_schedules_timed_out_slots(self):
        protocol = json.loads((ROOT / PROTOCOL).read_text())
        replies = Path(tempfile.mkdtemp()) / "replies.json"
        self.addCleanup(lambda: replies.unlink(missing_ok=True))
        replies.write_text(json.dumps({"replies": {"tee-top-3": form("topk", 3), "tee-count-buyable": form("count")}}))
        for number in (7, 14):
            slot = next(slot for slot in protocol["schedule"] if slot["slot"] == number)
            step = guarded.rerun_step(paid_step(slot), {"slot": number, "batch": "primary-folder"})
            with self.subTest(slot=number):
                self.assertEqual(step["argv"][1:2] + step["argv"][-2:], [guarded.RERUN_RUNNER, "--clock", "3600"])
                self.dry_run(step, replies)

    def test_the_frozen_runner_alone_refuses_the_doubled_clock_and_the_wrapper_any_other(self):
        import matched_briefing_rerun as wrapper
        protocol = json.loads((ROOT / PROTOCOL).read_text())
        slot = next(slot for slot in protocol["schedule"] if slot["slot"] == 7)
        argv = guarded.rerun_step(paid_step(slot), {"slot": 7, "batch": "x"})["argv"][2:]
        self.assertEqual(wrapper.frozen_argv(argv)[-2:], ["--clock", "1800"])
        for bad in (argv[:-1] + ["5400"], argv[:-2], argv + ["--clock", "3600"], argv[:-2] + ["--clock=3600"]):
            with self.subTest(bad=bad[-2:]), self.assertRaisesRegex(SystemExit, "exactly once"):
                wrapper.frozen_argv(bad)

    @unittest.skipUnless((ROOT / guarded.FRESH_PRIMARY_CONFIG).exists()
                         and (ROOT / "experiments/results/matched-briefing-fresh-2-nov.manifest").exists(),
                         "the primary run's configuration and manifest are local to the laptop that ran it")
    def test_the_real_rerun_argv_from_the_real_manifest(self):
        primary = json.loads((ROOT / guarded.FRESH_PRIMARY_CONFIG).read_text())
        by_slot = {step["study_slot"]["slot"]: step for step in primary["steps"][1:]}
        replies = ROOT / "notes/fresh-market-2-nov/study-b-parser-replies.json"
        timeouts = guarded.primary_timeouts(ROOT, [primary["manifest"]])
        self.assertTrue(timeouts)
        for row in timeouts:
            with self.subTest(slot=row["slot"]):
                self.dry_run(guarded.rerun_step(by_slot[row["slot"]], row), replies)


if __name__ == "__main__":
    unittest.main()
