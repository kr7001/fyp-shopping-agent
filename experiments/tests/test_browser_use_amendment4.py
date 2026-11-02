"""Study A's stages under amendment 4, 2 November 2026: synthetic inputs only, no paid, model,
account or browser call. Attempt 3 continues the slots attempt 2 left never started, whatever
ended attempt 2, under Study A's USD 10 total cap, with a start cutoff read from its configuration
and point 5's rule on requests with no response. Each check is shown quiet on a good case and
firing on a planted fault."""
from contextlib import asynccontextmanager, contextmanager, redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401
import browser_use_transfer as study  # noqa: E402
import guarded_browser_use as guard  # noqa: E402
import fresh_market_launch as launch  # noqa: E402
import page  # noqa: E402
from test_browser_use_fresh import fresh_config  # noqa: E402
from test_browser_use_fresh_continuation import Attempt1, BOUND, PROVIDER  # noqa: E402

NOTES = guard.FRESH_NOTES
THIRD = guard.FRESH_ATTEMPT3_STAGE
CONTINUATION = guard.FRESH_CONTINUATION_STAGE
L1, L2 = guard.FRESH_LEDGER[guard.FRESH_STAGE], guard.FRESH_LEDGER[CONTINUATION]


class Attempt2Ended(Attempt1):
    """Attempt 1 as it stopped, attempt 2's command pinned as the real one is, and attempt 2
    ended by `end_attempt2`: by default stopped by its fourth no-response during its fourth
    slot, after three slots it ran (an answer, a clock timeout and a void)."""

    def setUp(self):
        super().setUp()
        self.continuation = {**self.cfg, "expected_head": "7148e83", "python": "/venv/python"}
        path = self.write("study-a-continuation-command.json", self.continuation)
        self.patch(guard, "FRESH_CONTINUATION_SHA256", guard.sha(path))
        self.continuation_sha = guard.sha(path)
        for name in ("amendment-3-2-nov.md", "amendment-4-2-nov.md"):
            self.write_text(f"{NOTES}/{name}", f"synthetic {name}\n")
        self.given = self.slots[5:]
        self.given_ids = [slot["id"] for slot in self.given]
        self.write_text(f"{NOTES}/a4-tests.log", "Ran 9 tests in 0.1s\n\nOK\n")
        self.write_text(f"{NOTES}/a4-packages.txt", "browser-use==0.13.14\n")
        self.preflight = self.write("study-a-a4-preflight.json", {
            "verdict": "PASS", "attempt": "amendment-4", "model_calls": 0,
            "synthetic_tests": {"log": f"{NOTES}/a4-tests.log"}, "installed_packages": f"{NOTES}/a4-packages.txt"})
        self.patch(launch, "head", lambda: "a4-head")
        self.end_attempt2()

    def end_attempt2(self, ran=("answered", "timeout", "failed"), stopped="interrupted", status="stopped",
                     reason="pilot worker did not complete", inflight=None, highwater=None):
        """Write attempt 2's files as its launcher and worker leave them: `ran` are the outcomes of
        the slots it saved a record for, in order; `stopped` the slot after them, interrupted or
        cut at the deadline (None when it ran every slot); every later slot not started."""
        results = self.notes / "study-a-continuation.results"
        if results.exists():
            for path in results.iterdir():
                path.unlink()
        statuses, completed = {}, []
        for i, slot in enumerate(self.given):
            if i < len(ran):
                row = {"phase": "transfer", "status": ran[i]}
                if ran[i] == "timeout":
                    row.update(disposition="timeout", reason="the trial clock: 2712 s against 2700 s")
                if ran[i] == "failed":
                    row.update(disposition="technical void", reason="no answer after 1 request(s) with no response")
                self.write(f"study-a-continuation.results/{slot['id']}.json", {
                    "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                    "condition": slot["condition"], "phase": "transfer", "stage": CONTINUATION, "attempt": 2,
                    "study_id": guard.FRESH_BUDGET, "batch_id": guard.FRESH_BUDGET,
                    "config_sha256": self.continuation_sha, "outcome": ran[i],
                    "answer": "Synthetic content never read for eligibility"})
                completed.append(slot["id"])
            elif i == len(ran) and stopped:
                row = {"phase": "transfer", "status": stopped, "reason": reason}
                if stopped == "interrupted":
                    self.write(f"study-a-continuation.results/{slot['id']}.interrupted.json", {"outcome": "failed"})
            else:
                row = {"phase": "transfer", "status": "not_started", "reason": reason}
            statuses[slot["id"]] = row
        self.write("study-a-continuation.results/schedule.json", {
            "study_id": guard.FRESH_BUDGET, "stage": CONTINUATION, "batch_id": guard.FRESH_BUDGET, "attempt": 2,
            "slots": self.given})
        self.write("study-a-continuation.results/slot-status.json", {"slots": statuses})
        self.write("study-a-continuation.results/completed.json", {"completed": completed, "expected": 27})
        self.statuses2 = statuses
        self.write("study-a-continuation.status.json", {"status": status, "config_sha256": self.continuation_sha,
                                                        **({"reason": reason} if status == "stopped" else {})})
        self.write("study-a-continuation.launch.json", {"study_budget_id": guard.FRESH_BUDGET, "attempt": 2,
                                                        "config_sha256": self.continuation_sha})
        # 40 charged calls, three settled at the bound, and the fourth with no response unsettled.
        calls = [{"reservation": f"call-{i:05d}", "role": "executor", "reserved_usd": BOUND, "cost_usd": 0.002,
                  "error": False} for i in range(1, 41)]
        calls += [{"reservation": f"call-{i:05d}", "role": "executor", "reserved_usd": BOUND, "cost_usd": None,
                   "settled_usd": BOUND, "settlement_kind": kind, "error": True}
                  for i, kind in ((41, "no response"), (42, "trial clock"), (43, "no response"))]
        calls.append({"reservation": "call-00044", "role": "executor", "reserved_usd": BOUND, "cost_usd": None,
                      "error": True, "settlement": "not settled: request 4 with no response stops the batch"})
        self.known2 = 40 * 0.002
        self.ledger2 = {"schema": 1, "charged_usd": self.known2, "inflight": inflight or {}, "calls": calls,
                        "blocked_reason": "a request ended with no response after 3 settlements; reconciliation required",
                        "start_usage": 101.0, "highwater_usage": highwater or 101.09,
                        "carryover_usd": self.carryover, "prior_unsettled_reserve_usd": BOUND,
                        "prior_ledger_files": [L1], "study_budget_id": guard.FRESH_BUDGET, "attempt": 2,
                        "shared_cap_usd": 3.0, "settled_usd": 3 * BOUND}
        self.write("study-a-continuation.ledger.json", self.ledger2)

    def build(self, **options):
        """Attempt 3's configuration as the launch tool writes it, moved away first if written."""
        for name in ("study-a-attempt3-command.json", "study-a-attempt3-command.argv.json",
                     "study-a-attempt3.approval.json", "study-a-attempt3-reconciliation.json"):
            (self.notes / name).unlink(missing_ok=True)
        output = self.notes / "study-a-attempt3-command.json"
        with redirect_stdout(io.StringIO()):
            launch.attempt3(output, self.preflight, **options)
        return json.loads(output.read_text())

    def expected_carryover(self, highwater=101.09):
        attempt1 = self.known + BOUND
        attempt2 = max(self.known2 + 4 * BOUND, highwater - 101.0)
        return attempt1 + attempt2


class Slots(Attempt2Ended):
    def test_picks_exactly_the_slots_attempt2_never_started_in_order(self):
        config = self.build()
        self.assertEqual(config["slot_ids"], self.given_ids[4:])
        self.assertEqual(guard.validate_fresh_attempt3(config), self.given_ids[4:])
        plan = study.preview(config)
        self.assertEqual(plan["slots"], self.given[4:])
        self.assertEqual((plan["stage"], plan["attempt"], plan["original_slot_count"]), (THIRD, 3, 32))
        # Never a slot attempt 1 or 2 ran or interrupted: the void after the 4th no-response included.
        self.assertFalse(set(self.ids[:5] + self.given_ids[:4]) & {slot["id"] for slot in plan["slots"]})

    def test_whatever_ended_attempt2(self):
        for case in ({"ran": (), "stopped": "interrupted"},                                   # its cap, in its first slot
                     {"ran": ("answered",) * 26, "stopped": "time_censored",
                      "reason": "absolute deadline reached"},                                     # the deadline, at its last
                     {"ran": ("failed", "timeout", "failed"), "stopped": None,
                      "reason": "3 slots in a row ended without an answer"},                     # its systemic stop
                     {"ran": ("answered",) * 27, "stopped": None, "status": "complete"}):        # done
            with self.subTest(case=case):
                self.end_attempt2(**case)
                config = self.build()
                skipped = len(case["ran"]) + (1 if case["stopped"] else 0)
                self.assertEqual(config["slot_ids"], self.given_ids[skipped:])
                self.assertEqual(guard.validate_fresh_attempt3(config), self.given_ids[skipped:])
                self.assertEqual(config["estimate_usd"] > 0, skipped < 27)

    def test_a_slot_list_other_than_the_unstarted_ones_is_refused(self):
        config = self.build()
        for slot_ids in (self.given_ids[3:], self.given_ids[5:], self.given_ids[4:][::-1],
                         self.given_ids[4:] + [self.ids[4]], []):
            with self.subTest(slot_ids=slot_ids[:2]), self.assertRaisesRegex(guard.Stop, "never started"):
                guard.validate_fresh_attempt3({**config, "slot_ids": slot_ids})

    def test_attempt2_still_running_or_unreadable_is_refused(self):
        config = self.build()
        self.write("study-a-continuation.status.json", {"status": "running", "config_sha256": self.continuation_sha})
        self.rebind(config)
        with self.assertRaisesRegex(guard.Stop, "terminal status"):
            guard.validate_fresh_attempt3(config)
        self.end_attempt2()
        running = copy.deepcopy(self.statuses2)
        running[self.given_ids[5]]["status"] = "running"
        self.write("study-a-continuation.results/slot-status.json", {"slots": running})
        with self.assertRaisesRegex(SystemExit, "still running"):
            self.build()
        self.end_attempt2()
        # A slot marked interrupted that has a saved record is ambiguous: a human rules on it.
        self.write(f"study-a-continuation.results/{self.given_ids[3]}.json", {"slot": self.given_ids[3]})
        with self.assertRaisesRegex(SystemExit, "has a saved record"):
            self.build()

    def rebind(self, config):
        config["hashes"] = {name: guard.sha(self.repo / name) for name in config["hashes"]}

    def test_evidence_changed_after_binding_or_unbound_is_refused(self):
        config = self.build()
        record = f"{NOTES}/study-a-continuation.results/{self.given_ids[0]}.json"
        data = json.loads((self.repo / record).read_text())
        (self.repo / record).write_text(json.dumps({**data, "answer": "Mutated synthetic answer"}))
        with self.assertRaisesRegex(guard.Stop, "changed after it was bound"):
            guard.validate_fresh_attempt3(config)
        (self.repo / record).write_text(json.dumps({**data, "condition": "other"}))
        self.rebind(config)
        with self.assertRaisesRegex(guard.Stop, "differs from its slot"):
            guard.validate_fresh_attempt3(config)
        (self.repo / record).write_text(json.dumps(data))
        self.rebind(config)
        guard.validate_fresh_attempt3(config)
        for name in (record, f"{NOTES}/amendment-4-2-nov.md",
                     f"{NOTES}/study-a-continuation.results/{self.given_ids[3]}.interrupted.json"):
            with self.subTest(unbound=name), self.assertRaisesRegex(guard.Stop, "hash-bound"):
                guard.validate_fresh_attempt3({**config, "hashes": {k: v for k, v in config["hashes"].items()
                                                                    if k != name}})

    def test_attempt2s_condition_command_and_files_are_kept(self):
        config = self.build()
        for change in ({"temperature": 0.5}, {"max_steps": 151}, {"clock_s": 5400}, {"repeats": [1, 2, 3]},
                       {"provider": {**PROVIDER, "allow_fallbacks": True}}):
            with self.subTest(change=change), self.assertRaisesRegex(guard.Stop, "condition unchanged"):
                guard.validate_fresh_attempt3({**config, **change})
        moved = {**config["hashes"], "experiments/runners/browser_use_runner.py": "0" * 64}
        with self.assertRaisesRegex(guard.Stop, "changed a file attempt 2 ran with"):
            guard.validate_fresh_attempt3({**config, "hashes": moved})
        for field in ("prior_config_file", "prior_slot_status_file"):
            with self.subTest(field=field), self.assertRaisesRegex(guard.Stop, "own files"):
                guard.validate_fresh_attempt3({**config, field: f"{NOTES}/other.json"})
        (self.notes / "study-a-continuation-command.json").write_text(json.dumps({**self.continuation, "top_p": 0.9}))
        with self.assertRaisesRegex(guard.Stop, "exact command"):
            guard.validate_fresh_attempt3(config)


class Carryover(Attempt2Ended):
    def test_attempts_1_and_2_as_the_guard_counts_them(self):
        config = self.build()
        # Attempt 1: its known charges and call-00253 at its bound. Attempt 2: its charges, its
        # three settlements and its unsettled fourth no-response, each at its bound.
        self.assertAlmostEqual(config["carryover_usd"], self.expected_carryover(), places=12)
        self.assertAlmostEqual(config["cap_usd"] + config["carryover_usd"], 10.0, places=12)
        recorded = json.loads((self.repo / guard.FRESH_A4_RECONCILIATION[THIRD]).read_text())
        self.assertEqual(recorded["prior_ledger_sha256"], {L1: guard.sha(self.repo / L1), L2: guard.sha(self.repo / L2)})
        self.assertEqual((recorded["carryover_usd"], recorded["shared_cap_usd"], recorded["model_calls"]),
                         (config["carryover_usd"], 10.0, 0))
        self.assertEqual(guard.recovery_limits(config)[0], config["carryover_usd"])

    def test_the_account_counts_when_it_shows_more(self):
        self.end_attempt2(highwater=103.0)
        config = self.build()
        self.assertAlmostEqual(config["carryover_usd"], self.expected_carryover(highwater=103.0), places=12)

    def test_a_request_in_flight_when_attempt2_stopped_counts_at_its_bound(self):
        self.end_attempt2(inflight={"call-00045": {"reserved_usd": BOUND, "role": "executor"}})
        config = self.build()
        self.assertAlmostEqual(config["carryover_usd"], self.expected_carryover() + BOUND, places=12)

    def test_a_carryover_other_than_the_counted_spend_is_refused(self):
        config = self.build()
        for carry in (config["carryover_usd"] - BOUND, config["carryover_usd"] + 0.01):
            with self.subTest(carry=carry):
                path = self.repo / guard.FRESH_A4_RECONCILIATION[THIRD]
                path.write_text(json.dumps({**json.loads(path.read_text()), "carryover_usd": carry}))
                changed = {**config, "carryover_usd": carry, "cap_usd": 10.0 - carry}
                self.rebind(changed)
                with self.assertRaises(guard.Stop):
                    guard.validate_fresh_attempt3(changed)
        # The reconciliation must bind both ledgers.
        self.build()
        path = self.repo / guard.FRESH_A4_RECONCILIATION[THIRD]
        data = json.loads(path.read_text())
        path.write_text(json.dumps({**data, "prior_ledger_sha256": {L1: data["prior_ledger_sha256"][L1]}}))
        with self.assertRaisesRegex(guard.Stop, "does not bind"):
            guard.recovery_limits(config)

    def rebind(self, config):
        config["hashes"] = {name: guard.sha(self.repo / name) for name in config["hashes"]}


class Budget(Attempt2Ended):
    def test_study_as_total_cap_is_ten_dollars_for_attempt3_and_three_for_attempt2(self):
        config = self.build()
        guard.validate_fresh_budget(config)
        self.assertEqual(guard.recovery_limits(config)[0], config["carryover_usd"])
        for change in ({"shared_cap_usd": 7.0, "cap_usd": 7.0 - config["carryover_usd"]},
                       {"shared_cap_usd": 3.0, "cap_usd": 3.0 - config["carryover_usd"]},
                       {"cap_usd": 10.0}, {"attempt": 2}, {"estimate_usd": 10.0},
                       {"prior_ledger_files": [L1]}, {"prior_ledger_files": [L2, L1]},
                       {"reconciliation_file": guard.FRESH_RECONCILIATION},
                       {"ledger_path": str(self.notes / "study-a-continuation.ledger.json")},
                       {"output_dir": str(self.notes / "study-a.results")},
                       {"deadline": "2026-11-03T12:00:01+08:00"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_fresh_budget({**config, **change})
        # Attempt 2's own configuration still validates under its USD 3, and not under USD 10.
        guard.validate_fresh_budget(self.cfg)
        self.assertEqual(len(guard.validate_fresh_continuation(self.cfg)), 27)
        with self.assertRaisesRegex(guard.Stop, r"shared \$3 cap"):
            guard.recovery_limits({**self.cfg, "shared_cap_usd": 10.0, "cap_usd": 10.0 - self.carryover})

    def test_the_cutoff_and_deadline_come_from_the_configuration(self):
        config = self.build()
        self.assertEqual((config["deadline"], config["start_cutoff"]),
                         ("2026-11-03T12:00:00+08:00", "2026-11-03T12:00:00+08:00"))
        earlier = self.build(deadline="2026-11-03T08:00:00+08:00", start_cutoff="2026-11-03T06:30:00+08:00")
        self.assertEqual((earlier["deadline"], earlier["start_cutoff"]),
                         ("2026-11-03T08:00:00+08:00", "2026-11-03T06:30:00+08:00"))
        guard.validate_fresh_budget(earlier)
        for change in ({"start_cutoff": "2026-11-03T08:00:01+08:00"}, {"start_cutoff": None},
                       {"start_cutoff": "2026-11-03T06:30:00"}):
            with self.subTest(change=change), self.assertRaises((guard.Stop, TypeError)):
                guard.validate_fresh_budget({**earlier, **change})
        with self.assertRaises(guard.Stop):
            self.build(deadline="2026-11-03T12:30:00+08:00")  # past the protocol's absolute stop

    def test_one_launch_claim_beside_the_earlier_ones(self):
        config = self.build()
        command = self.notes / "study-a-attempt3-command.json"
        guard.claim_repeat_launch(config, command)
        marker = json.loads((self.notes / "study-a-attempt3.launch.json").read_text())
        self.assertEqual((marker["attempt"], marker["config_sha256"]), (3, guard.sha(command)))
        with self.assertRaisesRegex(guard.Stop, "already claimed"):
            guard.claim_repeat_launch(config, command)

class Preflight(Attempt2Ended):
    def test_amendment_4s_receipt_is_written_where_asked_and_the_builder_needs_it(self):
        log = self.write_text(f"{NOTES}/a4-tests-2.log", "....\nRan 4 tests in 0.1s\n\nOK\n")
        shop = self.write_text(f"{NOTES}/live-check.log", "62 checks, 0 failed\n")
        lock = self.write_text("lock.txt", "browser-use==0.13.14\n")
        self.write("reference/attempt2-command.json", {"python": "python", "browser_executable": "chrome",
                                                       "preflight_browser_version": "156.0.8078.79",
                                                       "dependencies_lock": "lock.txt"})
        self.write("study-a-preflight.json", {"verdict": "PASS", "shop_check": {
            "checks": 62, "failed": 0, "log": f"{NOTES}/live-check.log", "log_sha256": guard.sha(shop)}})
        self.write_text("experiments/runners/browser_use_fetches.py", "listener\n")
        output = self.notes / "study-a-a4-preflight-2.json"
        with mock.patch.object(launch, "chrome_build", return_value="156.0.8078.79"):
            path = launch.continuation_preflight(log, packages=lock.read_text(), receipt_path=output,
                                                 attempt="amendment-4")
        receipt = json.loads(path.read_text())
        self.assertEqual((path, receipt["verdict"], receipt["attempt"], receipt["installed_packages"]),
                         (output, "PASS", "amendment-4", f"{NOTES}/study-a-a4-preflight-2-installed-packages.txt"))
        self.assertIn("amendment 4", receipt["scope"])
        self.assertFalse(launch.CONTINUATION_PREFLIGHT.exists())  # the continuation's own is not touched
        with self.assertRaisesRegex(SystemExit, "exists"):
            launch.continuation_preflight(log, packages="", receipt_path=output, attempt="amendment-4")
        # The builder takes only a passing receipt of amendment 4.
        self.write("study-a-a4-preflight.json", {**json.loads(self.preflight.read_text()), "attempt": 2})
        with self.assertRaisesRegex(SystemExit, "a4-preflight"):
            self.build()


class WholeConfiguration(unittest.TestCase):
    def test_the_whole_check_holds_ten_dollars_the_start_cutoff_and_attempt2s_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder).resolve()  # as the launcher resolves it (/private/var on macOS)
            base = repo / NOTES
            cfg = {**fresh_config(repo), "version": 1, "stage": THIRD, "attempt": 3, "carryover_usd": 2.5,
                   "shared_cap_usd": 10.0, "cap_usd": 7.5, "estimate_usd": 1.0,
                   "start_cutoff": "2026-11-03T12:00:00+08:00", "model": "test/model",
                   "provider": {"max_price": {"prompt": .2, "completion": .5, "request": 0}},
                   "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
                   "allowed_served_providers": ["Test"], "protocol_file": "protocol.md", "dependencies_lock": "lock.txt",
                   "runtime_input_files": [], "reference_config_file": "reference.json", "analysis_plan_file": "plan.md",
                   "preflight_receipt": "preflight.json", "tasks_file": "tasks.json", "market_files": ["fixture.json"],
                   "questions_file": str(repo / "questions.json"), "python": "python",
                   "prior_ledger_files": [L1, L2], "reconciliation_file": guard.FRESH_A4_RECONCILIATION[THIRD],
                   **{field: str(base / name) for field, name in guard.fresh_files(THIRD).items()}}
            (repo / "experiments/box").mkdir(parents=True)
            names = ["tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                     "experiments/runners/browser_use_runner.py", "protocol.md", "lock.txt", "reference.json", "plan.md",
                     "preflight.json", "experiments/paths.py", "experiments/runners/browser_use_fetches.py", "tasks.json",
                     "fixture.json", "questions.json", L1, L2, guard.FRESH_A4_RECONCILIATION[THIRD]]
            cfg["hashes"] = {name: "synthetic" for name in names}
            path = repo / "config.json"
            path.write_text(json.dumps(cfg))
            with mock.patch.object(guard, "ROOT", repo), \
                    mock.patch.object(guard.time, "time", return_value=guard.deadline_epoch("2026-11-02T20:00:00+08:00")), \
                    mock.patch.object(guard, "recovery_limits", return_value=(2.5, 1.0)), \
                    mock.patch.object(guard, "verify_identity", return_value="head"), \
                    mock.patch.object(guard, "validate_fresh_identity") as identity, \
                    mock.patch.object(guard, "validate_fresh_attempt3") as evidence:
                self.assertEqual(guard.validate_config(path)["cap_usd"], 7.5)  # over attempt 2's USD 3
                identity.assert_called_once()
                evidence.assert_called_once()
                for change, message in (({"cap_usd": 10.5, "carryover_usd": 0.5}, "cap"),
                                        ({"start_cutoff": "2026-11-02T20:00:10+08:00"}, "start cutoff leaves no"),
                                        ({"hashes": {k: v for k, v in cfg["hashes"].items() if k != L2}}, "hash-bound")):
                    with self.subTest(change=change):
                        path.write_text(json.dumps({**cfg, **change}))
                        with self.assertRaisesRegex(guard.Stop, message):
                            guard.validate_config(path)


class NothingLeft(Attempt2Ended):
    def test_with_no_slot_left_the_launch_ends_without_a_paid_call(self):
        self.end_attempt2(ran=("answered",) * 27, stopped=None, status="complete")
        config = self.build()
        self.assertEqual((config["slot_ids"], config["estimate_usd"]), ([], 0))
        path = self.notes / "study-a-attempt3-command.json"
        with mock.patch.object(guard, "validate_config", return_value=config) as checked, \
                mock.patch.object(guard, "account_snapshot", side_effect=AssertionError("no account read")), \
                mock.patch.object(guard, "read_key", side_effect=AssertionError("no key read")), \
                mock.patch.object(guard.subprocess, "Popen", side_effect=AssertionError("no worker")), \
                redirect_stdout(io.StringIO()) as said:
            guard.execute(path)
        self.assertIn("without a paid call", said.getvalue())
        checked.assert_called_once_with(path)  # checked in full, without an approval
        for name in ("study-a-attempt3.launch.json", "study-a-attempt3.ledger.json", "study-a-attempt3.status.json"):
            self.assertFalse((self.notes / name).exists(), name)

    def test_with_slots_left_the_launch_needs_its_approval(self):
        config = self.build()
        path = self.notes / "study-a-attempt3-command.json"
        with mock.patch.object(guard, "validate_config", side_effect=guard.Stop("concrete user approval is missing")) as checked:
            with self.assertRaisesRegex(guard.Stop, "approval"):
                guard.execute(path)
        checked.assert_called_once_with(path, require_approval=True)
        self.assertTrue(config["slot_ids"])


def a4_budget(folder, monotonic=None):
    """Attempt 3's spending guard, its prior evidence stood in for."""
    cfg = {"stage": THIRD, "attempt": 3, "cap_usd": 8.0, "minimum_balance_usd": 20.2117632,
           "deadline": "2099-01-01T00:00:00+08:00", "model": "deepseek/deepseek-v4-flash", "provider": PROVIDER,
           "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
           "allowed_served_providers": ["DeepInfra"], "prior_ledger_files": [L1, L2]}
    clock = {"monotonic": monotonic} if monotonic else {}
    with mock.patch.object(guard, "validate_fresh_budget"), \
            mock.patch.object(guard, "recovery_limits", return_value=(2.0, 1.0)):
        return guard.CallBudget(cfg, Path(folder) / "ledger.json", lambda: {"usage": 100.0, "remaining": 60.0},
                                **clock), cfg


class NoResponses(unittest.TestCase):
    """Point 5: the provider's no-responses are settled with no count limit; three executor
    requests in a row with no response stop the batch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = [1000.0]
        self.budget, self.cfg = a4_budget(self.tmp.name, monotonic=lambda: self.now[0])

    def meta(self, role="executor"):
        return {"model": self.cfg["model"], "provider": PROVIDER, "prompt_bytes": 1000,
                "max_output_tokens": 4096, "nontext_or_plugins": False, "role": role}

    def answered(self, role="executor"):
        self.budget.after_call(self.budget.before_call(self.meta(role)),
                               response_json={"id": "gen", "provider": "DeepInfra", "usage": {"cost": 0.001}})

    def no_response(self, error="CancelledError"):
        self.budget.after_call(self.budget.before_call(self.meta()), error=error)

    def test_no_limit_when_answers_come_between(self):
        for _ in range(6):  # well past amendment 3's limit of three
            self.no_response()
            self.no_response("ReadTimeout")
            self.answered()
        state = self.budget.state
        self.assertEqual((state["no_response_settlements"], state["no_response_run"], state["blocked_reason"]),
                         (12, 0, None))
        self.assertAlmostEqual(state["settled_usd"], 12 * BOUND, places=12)
        self.assertIsNone(state["no_response_settlement_limit"])
        self.assertIn("2 in a row of 3", state["calls"][-2]["settlement"])

    def test_three_in_a_row_are_settled_and_stop_the_batch(self):
        self.no_response()
        self.no_response()
        with self.assertRaisesRegex(guard.Stop, "3 executor requests in a row"):
            self.no_response()
        state = self.budget.state
        self.assertEqual((state["no_response_settlements"], state["no_response_run"]), (3, 3))
        self.assertAlmostEqual(state["settled_usd"], 3 * BOUND, places=12)
        self.assertEqual(state["calls"][-1]["settled_usd"], BOUND)  # counted at its bound, not left unknown
        with self.assertRaises(guard.Stop):
            self.budget.before_call(self.meta())
        saved = json.loads((Path(self.tmp.name) / "ledger.json").read_text())
        self.assertIn("provider outage", saved["blocked_reason"])

    def test_a_parser_answer_or_a_clock_settlement_neither_breaks_nor_extends_a_run(self):
        self.no_response()
        self.answered("parser")
        with self.budget.trial_clock(10):
            self.now[0] += 10
            self.no_response()  # the clock's
        self.assertEqual((self.budget.state["no_response_run"], self.budget.state["clock_settlements"]), (1, 1))
        self.no_response()
        with self.assertRaisesRegex(guard.Stop, "3 executor requests in a row"):
            self.no_response()

    def test_settlements_count_against_the_cap_and_every_other_unknown_still_blocks(self):
        self.budget.state["charged_usd"] = self.cfg["cap_usd"] - BOUND - BOUND / 2
        self.no_response()
        with self.assertRaisesRegex(guard.Stop, "cap would be exceeded"):
            self.budget.before_call(self.meta())
        for name, settle in (("a parser request with no response", None),
                             ("a response without usage",
                              lambda b, r: b.after_call(r, response_json={"id": "g", "provider": "DeepInfra"}))):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as folder:
                budget, _ = a4_budget(folder)
                reservation = budget.before_call(self.meta("parser" if settle is None else "executor"))
                with self.assertRaises(guard.Stop):
                    if settle is None:
                        budget.after_call(reservation, error="CancelledError")
                    else:
                        settle(budget, reservation)
                self.assertEqual(budget.state["settled_usd"], 0.0)


@contextmanager
def no_clock(clock_s):
    yield


async def run_attempt3(case, config, results=None, now=None):
    """Attempt 3's batch loop, every paid step stood in for. `results` maps a slot's index among
    those it runs to a record maker; `now`, when given, is the wall clock, which each trial
    moves on by an hour."""
    budget = types.SimpleNamespace(state={"calls": [], "inflight": {}, "blocked_reason": None}, trial_clock=no_clock)
    trials = []
    clock = None if now is None else types.SimpleNamespace(time=lambda: now[0], perf_counter=lambda: 0.0)

    async def run(trial, *_args, **_kwargs):
        trials.append(Path(trial["out_dir"]).name)
        if now is not None:
            now[0] += 3600
        make = (results or {}).get(len(trials) - 1)
        return make() if make else {"outcome": "answered", "answer": "synthetic answer", "agent_errors": [None],
                                    "trace": {"measurement_valid": True}, "elapsed_s": 300.0,
                                    "settings": {"clock_s": trial["clock_s"]}, "cost_usd": 0.001}

    @asynccontextmanager
    async def research_browser(config, recorder):
        yield types.SimpleNamespace(on=lambda *a: None), "cdp"

    adapter = types.SimpleNamespace(create_llm=mock.Mock(), close_llm=mock.AsyncMock(), run_trial=run,
                                    configure_private_runtime=mock.Mock(), research_browser=research_browser)
    observed = page.Page(config["questions"][0]["start_url"], [page.Listing(
        "A", "Rookmere tee", "http://localhost:7770/a.html", 9)], total=1, next_page=False, reader="rendered")
    patches = [mock.patch.dict(sys.modules, {"browser_use_runner": adapter, "browser_use.llm.messages":
                                             types.SimpleNamespace(UserMessage=mock.Mock())}),
               mock.patch.dict(study.os.environ, {"IGR_BROWSER_USE_GUARD": "t", "IGR_BROWSER_USE_CONFIG_SHA256": "h"}),
               mock.patch.object(study, "validate_config", return_value=config),
               mock.patch.object(study, "sha", return_value="h"),
               mock.patch.object(study, "read_key", return_value="SYNTHETIC"),
               mock.patch.object(study, "CallBudget", return_value=budget),
               mock.patch.object(study, "read_observation", return_value=observed),
               mock.patch.object(study, "verify_browser_version"),
               mock.patch.object(study, "build_query", return_value=("synthetic unchanged query", None))]
    if clock is not None:
        patches.append(mock.patch.object(study, "time", clock))
    error = None
    for patch in patches:
        patch.start()
    try:
        await study.execute_study("unused")
    except guard.Stop as stop:
        error = str(stop)
    finally:
        for patch in reversed(patches):
            patch.stop()
    output = Path(config["output_dir"])
    return types.SimpleNamespace(trials=trials, error=error, output=output,
                                 statuses=json.loads((output / "slot-status.json").read_text())["slots"])


class Batch(Attempt2Ended, unittest.IsolatedAsyncioTestCase):
    async def test_runs_the_unstarted_slots_beside_attempts_1_and_2(self):
        config = {**self.build(), "start_cutoff": "2099-01-01T00:00:00+08:00"}
        before = {path: guard.sha(path) for path in self.notes.rglob("*") if path.is_file()}

        def clock_timeout():
            return {"outcome": "timeout", "answer": None, "trace": {"measurement_valid": True},
                    "elapsed_s": 2702.0, "settings": {"clock_s": 2700}, "cost_usd": None}
        run = await run_attempt3(self, config, results={0: clock_timeout})
        self.assertIsNone(run.error)
        self.assertEqual(run.trials, self.given_ids[4:])
        self.assertEqual(run.output, self.notes / "study-a-attempt3.results")
        record = json.loads((run.output / f"{self.given_ids[4]}.json").read_text())
        self.assertEqual((record["stage"], record["attempt"], record["disposition"]), (THIRD, 3, "timeout"))
        after = {path: guard.sha(path) for path in before}
        self.assertEqual(after, before)  # attempts 1 and 2 untouched

    async def test_no_trial_starts_at_or_after_the_start_cutoff(self):
        cutoff = "2026-11-03T06:00:00+08:00"
        config = {**self.build(), "start_cutoff": cutoff}
        now = [guard.deadline_epoch(cutoff) - 3601]  # two trials start, the second a second before the cutoff
        run = await run_attempt3(self, config, now=now)
        self.assertEqual(run.error, guard.START_CUTOFF_REASON)
        self.assertEqual(run.trials, self.given_ids[4:6])
        rest = [run.statuses[slot_id] for slot_id in self.given_ids[6:]]
        self.assertTrue(all(row == {"phase": "transfer", "status": "not_started", "reason": guard.START_CUTOFF_REASON}
                            for row in rest))
        self.assertEqual(guard.worker_stop_reason(config, None), f"pilot worker did not complete: {guard.START_CUTOFF_REASON}")
        self.assertEqual(guard.worker_stop_reason(config, "3 executor requests in a row ended with no response"),
                         "pilot worker did not complete: 3 executor requests in a row ended with no response")


class AgentFacing(unittest.TestCase):
    def test_the_agent_facing_definitions_are_still_the_cohorts(self):
        source = (ROOT / "experiments/runners/browser_use_transfer.py").read_text()
        self.assertEqual(guard.agent_facing_digests(source), guard.AGENT_FACING)


if __name__ == "__main__":
    unittest.main()
