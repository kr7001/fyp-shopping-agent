"""Study A's one continuation on the fresh market, 2 November 2026: synthetic inputs only, no
paid, model, account or browser call. Attempt 1 stopped when Browser Use's LLM timeout cancelled
executor request call-00253, so its charge was unknown and the guard refused every later call.
Each check is shown quiet on a good case and firing on a planted fault."""
from contextlib import asynccontextmanager
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
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

CONTINUATION = guard.FRESH_CONTINUATION_STAGE
NOTES = guard.FRESH_NOTES
LEDGER = f"{NOTES}/study-a.ledger.json"
BOUND = 0.2117632  # (1048576 x 0.2 + 4096 x 0.5) / 1e6, every request's reservation
PROVIDER = {"order": ["deepinfra"], "allow_fallbacks": False, "quantizations": ["fp8"],
            "max_price": {"prompt": 0.2, "completion": 0.5, "request": 0}}
COHORT = "966e711a49660893edc93b6d34306df4f458df97"  # the repeats 2-3 cohort's commit
ATTEMPT1 = "b1c67c8aa9e5a5c3bd4d0f38f1be0f015c122717"  # the commit attempt 1 ran


def git_show(commit, name):
    shown = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=ROOT, capture_output=True)
    return shown.stdout if shown.returncode == 0 else None


class Attempt1(unittest.TestCase):
    """A synthetic checkout holding attempt 1 as the real one stopped: four answered slots, the
    fifth interrupted, 27 never started, and a ledger whose last request had no response."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        self.notes = self.repo / NOTES
        for name in ("experiments/runners/browser_use_runner.py", "tools/guarded_browser_use.py",
                     "experiments/runners/browser_use_transfer.py"):
            self.write_text(name, f"{name} as attempt 1 ran it\n")
        self.prior = {**fresh_config(self.repo), "version": 1, "deadline": "2026-11-02T23:59:00+08:00",
                      "environment_file": "unused", "runtime_input_files": [], "model": "deepseek/deepseek-v4-flash",
                      "provider": PROVIDER, "temperature": 0.2, "max_steps": 150,
                      "market": {"fixture": "env/fixtures/tee_fresh_2_nov.json", "brand": "Rookmere", "seed": 1002},
                      "hashes": {name: guard.sha(self.repo / name) for name in (
                          "experiments/runners/browser_use_runner.py", "tools/guarded_browser_use.py",
                          "experiments/runners/browser_use_transfer.py")}}
        prior_path = self.write("study-a-command.json", self.prior)
        self.prior_sha = guard.sha(prior_path)
        self.plan = study.preview(self.prior)
        self.slots = self.plan["slots"]
        self.ids = [slot["id"] for slot in self.slots]
        self.write("study-a.status.json", {"status": "stopped", "config_sha256": self.prior_sha,
                                           "reason": "pilot worker did not complete"})
        self.write("study-a.launch.json", {"study_budget_id": guard.FRESH_BUDGET, "attempt": 1,
                                           "config_sha256": self.prior_sha})
        self.write("study-a.results/schedule.json", self.plan)
        self.statuses = {}
        for i, slot in enumerate(self.slots):
            status = "answered" if i < 4 else "interrupted" if i == 4 else "not_started"
            self.statuses[slot["id"]] = {"phase": "transfer", "status": status}
            if i < 4:
                self.write(f"study-a.results/{slot['id']}.json", {
                    "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                    "condition": slot["condition"], "phase": "transfer", "stage": guard.FRESH_STAGE,
                    "study_id": guard.FRESH_BUDGET, "batch_id": guard.FRESH_BUDGET,
                    "config_sha256": self.prior_sha, "outcome": status,
                    "answer": "Synthetic content never read for eligibility"})
        self.write(f"study-a.results/{self.ids[4]}.interrupted.json", {"outcome": "failed", "answer": None})
        self.write("study-a.results/slot-status.json", {"slots": self.statuses})
        self.write("study-a.results/completed.json", {"completed": self.ids[:4], "expected": 32})
        calls = [{"reserved_usd": BOUND, "role": "executor", "requested_at": 1000.0 + i, "reservation": f"call-{i:05d}",
                  "cost_usd": 0.001, "generation_id": f"gen-{i}", "provider": "DeepInfra", "usage": {"cost": 0.001},
                  "completed_at": 1000.5 + i, "error": False} for i in range(1, 253)]
        calls.append({"reserved_usd": BOUND, "role": "executor", "requested_at": 1253.0, "reservation": "call-00253",
                      "cost_usd": None, "generation_id": None, "provider": None, "usage": None,
                      "completed_at": 1373.0, "error": True})
        self.known = sum(call["cost_usd"] for call in calls[:-1])
        self.ledger = {"schema": 1, "charged_usd": self.known, "inflight": {}, "calls": calls,
                       "blocked_reason": "a request has an unknown charge; reconciliation required",
                       "start_usage": 100.0, "highwater_usage": 100.2, "carryover_usd": 0.0,
                       "prior_unsettled_reserve_usd": 0.0, "prior_ledger_files": [],
                       "study_budget_id": guard.FRESH_BUDGET, "attempt": 1, "shared_cap_usd": 3.0}
        self.write("study-a.ledger.json", self.ledger)
        self.patch(guard, "FRESH_ATTEMPT1_SHA256", self.prior_sha)
        self.patch(guard, "FRESH_ATTEMPT1_LEDGER_SHA256", guard.sha(self.repo / LEDGER))
        for name, value in (("ROOT", self.repo), ("NOTES", self.notes),
                            ("CONTINUATION_PREFLIGHT", self.notes / "study-a-continuation-preflight.json"),
                            ("CONTINUATION_PACKAGES", self.notes / "study-a-continuation-installed-packages.txt")):
            self.patch(launch, name, value)
        # The reconciliation as the launch tool writes it, the account showing a little more
        # usage than the known charges.
        launch.reconcile(account={"usage": 100.0 + self.known + 0.002, "remaining": 60.0})
        self.carryover = self.known + BOUND
        self.cfg = {**self.prior, "stage": CONTINUATION, "attempt": 2, "carryover_usd": self.carryover,
                    "cap_usd": 3.0 - self.carryover, "estimate_usd": 1.3,
                    **{field: str(self.notes / name) for field, name in guard.FRESH_CONTINUATION_FILES.items()},
                    "prior_config_file": f"{NOTES}/study-a-command.json",
                    "prior_status_file": f"{NOTES}/study-a.status.json",
                    "prior_schedule_file": f"{NOTES}/study-a.results/schedule.json",
                    "prior_slot_status_file": f"{NOTES}/study-a.results/slot-status.json",
                    "prior_ledger_file": LEDGER, "prior_ledger_files": [LEDGER],
                    "reconciliation_file": guard.FRESH_RECONCILIATION}
        self.refresh_hashes()

    def patch(self, owner, name, value):
        patcher = mock.patch.object(owner, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_text(self, relative, text):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def write(self, name, data):
        return self.write_text(f"{NOTES}/{name}", json.dumps(data))

    def evidence(self):
        names = ["study-a-command.json", "study-a.status.json", "study-a.ledger.json", "study-a.launch.json",
                 "study-a.results/schedule.json", "study-a.results/slot-status.json",
                 "study-a.results/completed.json", f"study-a.results/{self.ids[4]}.interrupted.json",
                 "study-a-continuation-reconciliation.json"]
        names += [f"study-a.results/{slot_id}.json" for slot_id in self.ids[:4]]
        return [f"{NOTES}/{name}" for name in names]

    def refresh_hashes(self):
        self.cfg["hashes"] = {**self.prior["hashes"],
                              **{name: guard.sha(self.repo / name) for name in self.evidence()}}

    def reconciliation(self, **changes):
        path = self.repo / guard.FRESH_RECONCILIATION
        data = json.loads(path.read_text())
        path.write_text(json.dumps({**data, **changes}))


class Schedule(Attempt1):
    def test_runs_only_the_27_unstarted_slots_in_their_scheduled_order(self):
        guard.validate_fresh_budget(self.cfg)
        plan = study.preview(self.cfg)
        self.assertEqual(plan["slots"], self.slots[5:])
        self.assertEqual(len(plan["slots"]), 27)
        self.assertEqual((plan["study_id"], plan["batch_id"], plan["stage"], plan["paid_calls"]),
                         (guard.FRESH_BUDGET, guard.FRESH_BUDGET, CONTINUATION, 0))
        self.assertEqual((plan["attempt"], plan["prior_completed_count"], plan["prior_interrupted"],
                          plan["original_slot_count"]), (2, 4, [self.ids[4]], 32))
        self.assertFalse(set(self.ids[:5]) & {slot["id"] for slot in plan["slots"]})

    def test_refuses_to_replay_an_answered_or_interrupted_slot(self):
        for index, replacement in ((4, "not_started"), (0, "not_started"), (3, "not_started"),
                                   (4, "answered"), (5, "answered"), (6, "interrupted"), (31, "running")):
            with self.subTest(slot=index, status=replacement):
                changed = copy.deepcopy(self.statuses)
                changed[self.ids[index]]["status"] = replacement
                self.write("study-a.results/slot-status.json", {"slots": changed})
                self.refresh_hashes()
                with self.assertRaisesRegex(guard.Stop, "27 never started"):
                    study.preview(self.cfg)
        self.write("study-a.results/slot-status.json", {"slots": self.statuses})
        self.refresh_hashes()
        study.preview(self.cfg)
        # The interrupted slot counted as completed, or its record gone, is refused too.
        self.write("study-a.results/completed.json", {"completed": self.ids[:5], "expected": 32})
        self.refresh_hashes()
        with self.assertRaisesRegex(guard.Stop, "completed list"):
            study.preview(self.cfg)
        self.write("study-a.results/completed.json", {"completed": self.ids[:4], "expected": 32})
        (self.notes / f"study-a.results/{self.ids[4]}.interrupted.json").unlink()
        with self.assertRaisesRegex(guard.Stop, "interrupted record is missing"):
            study.preview(self.cfg)

    def test_a_status_changed_after_binding_is_refused(self):
        changed = copy.deepcopy(self.statuses)
        changed[self.ids[4]]["status"] = "not_started"
        self.write("study-a.results/slot-status.json", {"slots": changed})
        with self.assertRaises(guard.Stop):
            study.preview(self.cfg)

    def test_a_reordered_schedule_is_refused_even_when_rehashed(self):
        changed = copy.deepcopy(self.plan)
        changed["slots"][5], changed["slots"][6] = changed["slots"][6], changed["slots"][5]
        self.write("study-a.results/schedule.json", changed)
        self.refresh_hashes()
        with self.assertRaisesRegex(guard.Stop, "schedule"):
            study.preview(self.cfg)

    def test_attempt1_must_have_stopped_under_its_own_command(self):
        for status in ({"status": "running", "config_sha256": self.prior_sha},
                       {"status": "stopped", "config_sha256": "0" * 64}):
            with self.subTest(status=status):
                self.write("study-a.status.json", status)
                self.refresh_hashes()
                with self.assertRaisesRegex(guard.Stop, "terminal stopped"):
                    study.preview(self.cfg)

    def test_a_kept_record_changed_unbound_or_misfiled_is_refused(self):
        record = f"{NOTES}/study-a.results/{self.ids[0]}.json"
        self.cfg["hashes"].pop(record)
        with self.assertRaisesRegex(guard.Stop, "hash-bound"):
            study.preview(self.cfg)
        self.refresh_hashes()
        data = json.loads((self.repo / record).read_text())
        (self.repo / record).write_text(json.dumps({**data, "answer": "Mutated synthetic answer"}))
        with self.assertRaisesRegex(guard.Stop, "changed after it was bound"):
            study.preview(self.cfg)
        (self.repo / record).write_text(json.dumps({**data, "condition": "other"}))
        self.refresh_hashes()
        with self.assertRaisesRegex(guard.Stop, "differs from its slot"):
            study.preview(self.cfg)

    def test_the_condition_and_every_file_attempt1_ran_with_are_kept(self):
        study.preview(self.cfg)
        for change in ({"temperature": 0.5}, {"model": "other/model"}, {"max_steps": 151},
                       {"provider": {**PROVIDER, "allow_fallbacks": True}}, {"repeats": [1, 2, 3]},
                       {"deadline": "2026-11-03T00:00:00+08:00"}):
            with self.subTest(change=change), self.assertRaises((guard.Stop, ValueError)):
                study.preview({**self.cfg, **change})
        moved = {**self.cfg["hashes"], "experiments/runners/browser_use_runner.py": "0" * 64}
        with self.assertRaisesRegex(guard.Stop, "changed a file attempt 1 ran with"):
            study.preview({**self.cfg, "hashes": moved})
        # The launcher and the runner's scheduling code may change; their checks are elsewhere.
        renewed = {**self.cfg["hashes"], "tools/guarded_browser_use.py": "1" * 64,
                   "experiments/runners/browser_use_transfer.py": "2" * 64}
        study.preview({**self.cfg, "hashes": renewed})
        (self.notes / "study-a-command.json").write_text(json.dumps({**self.prior, "temperature": 0.3}))
        with self.assertRaisesRegex(guard.Stop, "exact command"):
            study.preview(self.cfg)

    def test_only_attempt1s_own_files_are_read(self):
        copy_of = self.notes / "copy-schedule.json"
        copy_of.write_text((self.notes / "study-a.results/schedule.json").read_text())
        for change in ({"prior_schedule_file": f"{NOTES}/copy-schedule.json"},
                       {"prior_ledger_files": [f"{NOTES}/other.json"], "prior_ledger_file": f"{NOTES}/other.json"},
                       {"reconciliation_file": f"{NOTES}/other.json"}):
            with self.subTest(change=change), self.assertRaisesRegex(guard.Stop, "own files"):
                guard.validate_fresh_continuation({**self.cfg, **change})


class Carryover(Attempt1):
    def test_known_charges_plus_the_no_response_request_at_its_bound(self):
        carryover, unsettled = guard.recovery_limits(self.cfg)
        self.assertEqual((carryover, unsettled), (self.known + BOUND, BOUND))
        recorded = json.loads((self.repo / guard.FRESH_RECONCILIATION).read_text())
        self.assertEqual((recorded["settled_usd"], recorded["carryover_usd"], recorded["model_calls"]),
                         ({"call-00253": BOUND}, self.known + BOUND, 0))
        self.assertEqual(recorded["prior_ledger_sha256"], {LEDGER: guard.sha(self.repo / LEDGER)})
        self.assertEqual(len(guard.validate_fresh_continuation(self.cfg)), 27)

    def test_refuses_a_carryover_that_does_not_match_the_bound_ledger(self):
        def refused(carryover=None, **reconciliation):
            carry = self.carryover if carryover is None else carryover
            self.reconciliation(**{"carryover_usd": carry, **reconciliation})
            self.refresh_hashes()
            config = {**self.cfg, "carryover_usd": carry, "cap_usd": 3.0 - carry}
            with self.assertRaises(guard.Stop):
                guard.validate_fresh_continuation(config)
            self.reconciliation(carryover_usd=self.carryover, settled_usd={"call-00253": BOUND},
                                prior_ledger_sha256={LEDGER: guard.sha(self.repo / LEDGER)},
                                account_usage_since_attempt1_usd=self.known + 0.002)
            self.refresh_hashes()
        guard.validate_fresh_continuation(self.cfg)
        refused(carryover=self.known)                         # the unknown request dropped
        refused(carryover=self.known + BOUND / 100)           # settled below its bound
        refused(carryover=self.known + BOUND + 0.01)          # more than the ledger holds
        refused(settled_usd={"call-00253": 0.0})
        refused(settled_usd={"call-00252": BOUND})
        refused(prior_ledger_sha256={LEDGER: "0" * 64})       # binds another ledger
        refused(account_usage_since_attempt1_usd=self.carryover + 0.01)
        guard.validate_fresh_continuation(self.cfg)
        # The configuration's carryover or cap apart from the reconciliation's.
        for change in ({"carryover_usd": self.carryover + 0.01}, {"cap_usd": 3.0}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_fresh_continuation({**self.cfg, **change})

    def test_a_ledger_changed_after_it_stopped_is_refused(self):
        settled = copy.deepcopy(self.ledger)
        settled["calls"][-1].update(cost_usd=0.0, usage={"cost": 0.0})
        self.write("study-a.ledger.json", settled)
        self.refresh_hashes()
        with self.assertRaises(guard.Stop):
            guard.validate_fresh_continuation(self.cfg)
        # Cheaper calls, reconciled again and bound consistently: only the pin can see it.
        cheaper = copy.deepcopy(self.ledger)
        for call in cheaper["calls"][:-1]:
            call.update(cost_usd=0.0005, usage={"cost": 0.0005})
        cheaper["charged_usd"] = known = sum(call["cost_usd"] for call in cheaper["calls"][:-1])
        self.write("study-a.ledger.json", cheaper)
        self.reconciliation(prior_ledger_sha256={LEDGER: guard.sha(self.repo / LEDGER)},
                            carryover_usd=known + BOUND, account_usage_since_attempt1_usd=known)
        self.refresh_hashes()
        config = {**self.cfg, "carryover_usd": known + BOUND, "cap_usd": 3.0 - (known + BOUND)}
        with self.assertRaisesRegex(guard.Stop, "ledger changed after it stopped"):
            guard.validate_fresh_continuation(config)
        with mock.patch.object(guard, "FRESH_ATTEMPT1_LEDGER_SHA256", guard.sha(self.repo / LEDGER)):
            self.assertEqual(len(guard.validate_fresh_continuation(config)), 27)

    def test_the_reconciliation_refuses_an_account_beyond_the_bound_or_another_ledger(self):
        (self.repo / guard.FRESH_RECONCILIATION).unlink()
        with self.assertRaisesRegex(SystemExit, "more usage"):
            launch.reconcile(account={"usage": 100.0 + self.known + BOUND + 0.01, "remaining": 60.0})
        launch.reconcile(account={"usage": 100.0 + self.known - 0.01, "remaining": 60.0})  # lagging: the bound stands
        recorded = json.loads((self.repo / guard.FRESH_RECONCILIATION).read_text())
        self.assertEqual(recorded["carryover_usd"], self.known + BOUND)
        (self.repo / guard.FRESH_RECONCILIATION).unlink()
        two = copy.deepcopy(self.ledger)
        two["calls"][0].update(cost_usd=None, usage=None, generation_id=None, provider=None, error=True)
        self.write("study-a.ledger.json", two)
        with self.assertRaisesRegex(SystemExit, "not the one"):
            launch.reconcile(account={"usage": 100.0, "remaining": 60.0})
        with mock.patch.object(guard, "FRESH_ATTEMPT1_LEDGER_SHA256", guard.sha(self.repo / LEDGER)), \
                self.assertRaisesRegex(SystemExit, "one request with no response"):
            launch.reconcile(account={"usage": 100.0, "remaining": 60.0})


class Budget(Attempt1):
    def test_its_own_paths_the_same_cap_and_one_continuation(self):
        guard.validate_fresh_budget(self.cfg)
        attempt1 = fresh_config(self.repo)
        for change in ({"attempt": 3}, {"attempt": 1}, {"carryover_usd": 0}, {"shared_cap_usd": 4},
                       {"cap_usd": 3.0}, {"estimate_usd": 0}, {"estimate_usd": 2.6},
                       {"minimum_balance_usd": 20}, {"study_budget_id": guard.REPEAT_BUDGET},
                       {"ledger_path": attempt1["ledger_path"]}, {"output_dir": attempt1["output_dir"]},
                       {"status_path": attempt1["status_path"]}, {"prior_ledger_files": []},
                       {"reconciliation_file": f"{NOTES}/other.json"},
                       {"deadline": "2026-11-03T12:00:01+08:00"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_fresh_budget({**self.cfg, **change})

    def test_shared_cap_is_three_dollars_for_the_continuation_only(self):
        self.assertEqual(guard.recovery_limits(self.cfg)[0], self.carryover)
        with self.assertRaisesRegex(guard.Stop, r"shared \$3 cap"):
            guard.recovery_limits({**self.cfg, "cap_usd": 3.0})
        with self.assertRaisesRegex(guard.Stop, r"shared \$2 cap"):
            guard.recovery_limits({**self.cfg, "stage": guard.REPEAT_RECOVERY_STAGE})

    def test_one_launch_claim_beside_attempt1s(self):
        command = self.write("command.json", self.cfg)
        guard.claim_repeat_launch(self.cfg, command)
        marker = json.loads((self.notes / "study-a-continuation.launch.json").read_text())
        self.assertEqual((marker["study_budget_id"], marker["attempt"], marker["config_sha256"]),
                         (guard.FRESH_BUDGET, 2, guard.sha(command)))
        with self.assertRaisesRegex(guard.Stop, "already claimed"):
            guard.claim_repeat_launch(self.cfg, command)
        self.assertEqual(json.loads((self.notes / "study-a.launch.json").read_text())["attempt"], 1)

    def test_the_verifiers_review_of_the_exact_command(self):
        command = ["python", "tools/guarded_browser_use.py", "--config", "c.json", "--execute"]
        receipt = {"verdict": "PASS", "config_sha256": "hash", "head": "head", "request_bound_verified": True,
                   "verifier": "claude", "independent": True, "command": command}
        guard.validate_review_receipt(self.cfg, receipt, "head", "hash", command)
        for change in ({"verifier": "codex-independent"}, {"command": command[:-1]}, {"config_sha256": "other"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_review_receipt(self.cfg, {**receipt, **change}, "head", "hash", command)


def settlement_budget(folder, stage=CONTINUATION, carryover=0.4):
    """A continuation's spending guard, its prior evidence stood in for."""
    cfg = {"stage": stage, "attempt": 2 if stage == CONTINUATION else 1, "cap_usd": 3.0 - carryover,
           "minimum_balance_usd": 20.2117632, "deadline": "2099-01-01T00:00:00+08:00",
           "model": "deepseek/deepseek-v4-flash", "provider": PROVIDER, "maximum_input_tokens": 1048576,
           "max_input_bytes": 200000, "max_output_tokens": 4096, "allowed_served_providers": ["DeepInfra"],
           "prior_ledger_files": [LEDGER], "temperature": 0.2, "frequency_penalty": 0.1, "top_p": None}
    limits = (carryover, BOUND) if stage == CONTINUATION else (0.0, 0.0)
    with mock.patch.object(guard, "validate_fresh_budget"), mock.patch.object(guard, "recovery_limits", return_value=limits):
        return guard.CallBudget(cfg, Path(folder) / "ledger.json", lambda: {"usage": 100.0, "remaining": 60.0}), cfg


class Settlement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.budget, self.cfg = settlement_budget(self.tmp.name)

    def meta(self, role="executor"):
        return {"model": self.cfg["model"], "provider": PROVIDER, "prompt_bytes": 1000,
                "max_output_tokens": 4096, "nontext_or_plugins": False, "role": role}

    def charged(self, budget, reservation, provider="DeepInfra", cost=0.001, error=None):
        budget.after_call(reservation, response_json={"id": "gen", "provider": provider, "usage": {"cost": cost}},
                          error=error)

    def test_a_request_with_no_response_is_settled_at_its_bound_and_the_batch_goes_on(self):
        reservation = self.budget.before_call(self.meta())
        self.budget.after_call(reservation, error="CancelledError")
        state = self.budget.state
        self.assertEqual((state["settled_usd"], state["no_response_settlements"], state["charged_usd"]), (BOUND, 1, 0.0))
        self.assertIsNone(state["blocked_reason"])
        call = state["calls"][0]
        self.assertEqual((call["cost_usd"], call["settled_usd"], call["error_name"], call["error"]),
                         (None, BOUND, "CancelledError", True))
        self.assertIn("1 of 3", call["settlement"])
        self.charged(self.budget, self.budget.before_call(self.meta()))
        self.assertEqual((state["charged_usd"], state["settled_usd"]), (0.001, BOUND))
        saved = json.loads((Path(self.tmp.name) / "ledger.json").read_text())
        self.assertEqual([c.get("settled_usd") for c in saved["calls"]], [BOUND, None])
        self.assertEqual(saved["no_response_settlement_limit"], 3)

    def test_settlements_count_against_the_cap(self):
        cap = self.cfg["cap_usd"]
        self.budget.after_call(self.budget.before_call(self.meta()), error="ReadTimeout")
        # Room for one more request without the settlement, none with it.
        self.budget.state["charged_usd"] = cap - BOUND - BOUND / 2
        with self.assertRaisesRegex(guard.Stop, "cap would be exceeded"):
            self.budget.before_call(self.meta())
        fresh, _ = settlement_budget(Path(self.tmp.name) / "other")
        fresh.state["charged_usd"] = cap - BOUND - BOUND / 2
        fresh.before_call(self.meta())

    def test_the_fourth_request_with_no_response_stops_the_batch(self):
        for _ in range(3):
            self.budget.after_call(self.budget.before_call(self.meta()), error="CancelledError")
        reservation = self.budget.before_call(self.meta())
        with self.assertRaisesRegex(guard.Stop, "after 3 settlements"):
            self.budget.after_call(reservation, error="CancelledError")
        state = self.budget.state
        self.assertAlmostEqual(state["settled_usd"], 3 * BOUND, places=12)
        self.assertEqual(state["no_response_settlements"], 3)
        self.assertNotIn("settled_usd", state["calls"][-1])
        self.assertIsNone(state["calls"][-1]["cost_usd"])
        self.assertIn("not settled", state["calls"][-1]["settlement"])
        with self.assertRaises(guard.Stop):
            self.budget.before_call(self.meta())

    def test_every_other_unknown_charge_still_blocks(self):
        cases = {
            "a response without usage": lambda b, r: b.after_call(r, response_json={"id": "g", "provider": "DeepInfra"}),
            "an error response without usage": lambda b, r: b.after_call(r, response_json={"error": {}}, error="HTTP_502"),
            "no response and no error": lambda b, r: b.after_call(r),
            "a parser request with no response": None,
            "attempt 1's own stage": None,
            "an unexpected provider": lambda b, r: self.charged(b, r, provider="Other"),
            "a failed request with a charge": lambda b, r: self.charged(b, r, error="HTTP_429"),
        }
        for name, settle in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as folder:
                stage = guard.FRESH_STAGE if name == "attempt 1's own stage" else CONTINUATION
                budget, _ = settlement_budget(folder, stage=stage)
                reservation = budget.before_call(self.meta("parser" if "parser" in name else "executor"))
                with self.assertRaises(guard.Stop):
                    if settle is None:
                        budget.after_call(reservation, error="CancelledError")
                    else:
                        settle(budget, reservation)
                self.assertTrue(budget.state["blocked_reason"])
                self.assertEqual(budget.state.get("settled_usd", 0.0), 0.0)
                with self.assertRaises(guard.Stop):
                    budget.before_call(self.meta())


@unittest.skipUnless(importlib.util.find_spec("browser_use") is not None,
                     "isolated pinned Browser Use environment required")
class TimedOutRequest(unittest.IsolatedAsyncioTestCase):
    """The 08:19 event through the frozen adapter's own transport: a request cancelled by a
    timeout while the provider has not answered, then an ordinary one, then three more."""

    async def test_cancelled_requests_are_settled_and_the_fourth_stops(self):
        import httpx
        import browser_use_runner as runner
        runner.configure_private_runtime()
        from browser_use.llm.messages import UserMessage
        sent = []

        async def respond(request):
            body = json.loads(request.content)
            sent.append(body["messages"][-1]["content"])
            if body["messages"][-1]["content"] == "slow":
                await asyncio.sleep(30)
            return httpx.Response(200, json={
                "id": "gen-offline", "object": "chat.completion", "created": 1, "model": body["model"],
                "provider": "DeepInfra",
                "usage": {"cost": 0.001, "prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "12"}, "finish_reason": "stop"}]})

        with tempfile.TemporaryDirectory() as folder:
            budget, cfg = settlement_budget(folder)
            llm = runner.create_llm(cfg, budget, "offline-fake-key", transport=httpx.MockTransport(respond))
            try:
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(llm.ainvoke([UserMessage(content="slow")]), 0.5)
                self.assertEqual((budget.state["no_response_settlements"], budget.state["blocked_reason"]), (1, None))
                self.assertEqual(llm.igr_calls[0]["error_type"], "CancelledError")
                self.assertEqual((await llm.ainvoke([UserMessage(content="fast")])).completion, "12")
                for _ in range(2):
                    with self.assertRaises(asyncio.TimeoutError):
                        await asyncio.wait_for(llm.ainvoke([UserMessage(content="slow")]), 0.5)
                with self.assertRaises(Exception):
                    await asyncio.wait_for(llm.ainvoke([UserMessage(content="slow")]), 0.5)
                self.assertIn("after 3 settlements", budget.state["blocked_reason"])
                with self.assertRaises(Exception):
                    await llm.ainvoke([UserMessage(content="fast")])
                self.assertEqual(sent, ["slow", "fast", "slow", "slow", "slow"])  # the last never sent
                self.assertAlmostEqual(budget.state["settled_usd"], 3 * BOUND, places=12)
                self.assertEqual(budget.state["charged_usd"], 0.001)
            finally:
                await runner.close_llm(llm)


class Execution(Attempt1, unittest.IsolatedAsyncioTestCase):
    async def test_runs_the_27_writes_beside_attempt1_and_keeps_settlements_apart(self):
        cfg = {**self.cfg, "expected_head": "head"}
        budget = types.SimpleNamespace(state={"calls": [], "inflight": {}, "blocked_reason": None})
        trials = []
        before = {path: guard.sha(path) for path in (self.notes / "study-a.results").rglob("*") if path.is_file()}

        async def run(trial, *_args, **_kwargs):
            trials.append(trial)
            if len(trials) == 2:  # a request settled at its bound, then an ordinary one
                budget.state["calls"] += [
                    {"reservation": "call-00001", "role": "executor", "cost_usd": None, "settled_usd": BOUND},
                    {"reservation": "call-00002", "role": "executor", "cost_usd": 0.001}]
            return {"outcome": "answered", "cost_usd": None, "trace": {"measurement_valid": True},
                    "answer": "synthetic answer", "agent_errors": [None]}

        @asynccontextmanager
        async def research_browser(config, recorder):
            yield types.SimpleNamespace(on=lambda *a: None), "cdp"

        adapter = types.SimpleNamespace(create_llm=mock.Mock(), close_llm=mock.AsyncMock(), run_trial=run,
                                        configure_private_runtime=mock.Mock(), research_browser=research_browser)
        observed = page.Page(cfg["questions"][0]["start_url"], [page.Listing(
            "A", "Rookmere tee", "http://localhost:7770/a.html", 9)], total=1, next_page=False, reader="rendered")
        with mock.patch.dict(sys.modules, {"browser_use_runner": adapter,
                                           "browser_use.llm.messages": types.SimpleNamespace(UserMessage=mock.Mock())}), \
                mock.patch.dict(study.os.environ, {"IGR_BROWSER_USE_GUARD": "test",
                                                   "IGR_BROWSER_USE_CONFIG_SHA256": "hash"}), \
                mock.patch.object(study, "validate_config", return_value=cfg), \
                mock.patch.object(study, "sha", return_value="hash"), \
                mock.patch.object(study, "read_key", return_value="SYNTHETIC"), \
                mock.patch.object(study, "CallBudget", return_value=budget), \
                mock.patch.object(study, "read_observation", return_value=observed), \
                mock.patch.object(study, "verify_browser_version"), \
                mock.patch.object(study, "technical_gate", side_effect=AssertionError("no diagnostic gate")), \
                mock.patch.object(study, "build_query", return_value=("synthetic unchanged query", None)):
            completed = await study.execute_study("unused")
        self.assertEqual(completed, self.ids[5:])
        output = self.notes / "study-a-continuation.results"
        self.assertEqual([Path(trial["out_dir"]) for trial in trials], [output / slot_id for slot_id in self.ids[5:]])
        schedule = json.loads((output / "schedule.json").read_text())
        self.assertEqual((schedule["attempt"], schedule["original_slot_count"], schedule["slots"]),
                         (2, 32, self.slots[5:]))
        settled = json.loads((output / f"{self.ids[6]}.json").read_text())
        self.assertEqual((settled["attempt"], settled["stage"], settled["config_sha256"], settled["total_cost_usd"],
                          settled["settled_bound_usd"], settled["no_response_settlements"]),
                         (2, CONTINUATION, "hash", None, BOUND, 1))
        plain = json.loads((output / f"{self.ids[5]}.json").read_text())
        self.assertEqual((plain["total_cost_usd"], plain["settled_bound_usd"], plain["no_response_settlements"]),
                         (0, 0, 0))
        after = {path: guard.sha(path) for path in (self.notes / "study-a.results").rglob("*") if path.is_file()}
        self.assertEqual(after, before)


class Charges(unittest.TestCase):
    def test_an_unknown_charge_leaves_the_total_unknown(self):
        self.assertEqual(study.charge_total([{"cost_usd": 0.25}, {"cost_usd": 0.5}]), 0.75)
        self.assertEqual(study.charge_total([]), 0)
        self.assertIsNone(study.charge_total([{"cost_usd": 0.25}, {"cost_usd": None}]))


class Inputs(Attempt1):
    def test_the_launch_tool_writes_a_configuration_the_guard_accepts(self):
        log = self.write_text(f"{NOTES}/tests.log", "....\nRan 4 tests in 0.1s\n\nOK\n")
        shop = self.write_text(f"{NOTES}/live-check.log", "62 checks, 0 failed\n")
        lock = self.write_text("lock.txt", "browser-use==0.13.14\n")
        reference = {"python": "python", "browser_executable": "chrome", "preflight_browser_version": "156.0.8078.79",
                     "dependencies_lock": "lock.txt"}
        self.write("reference/attempt2-command.json", reference)
        self.write("study-a-preflight.json", {"verdict": "PASS", "shop_check": {
            "checks": 62, "failed": 0, "log": f"{NOTES}/live-check.log", "log_sha256": guard.sha(shop)}})
        for name in ("experiments/runners/browser_use_fetches.py",):
            self.write_text(name, "listener\n")
        with mock.patch.object(launch, "chrome_build", return_value="156.0.8078.79"):
            receipt = json.loads(launch.continuation_preflight(log, packages=lock.read_text()).read_text())
        self.assertEqual((receipt["verdict"], receipt["attempt"], receipt["model_calls"],
                          receipt["shop_check"]["checks"]), ("PASS", 2, 0, 62))
        self.assertIn("not run again", receipt["shop_check"]["reused"])
        config = launch.config_continuation("head")
        self.assertEqual((config["stage"], config["attempt"], config["carryover_usd"], config["estimate_usd"]),
                         (CONTINUATION, 2, self.known + BOUND, launch.continuation_estimate(self.ledger, 27)))
        guard.validate_fresh_budget(config)
        self.assertEqual(guard.validate_fresh_continuation(config), self.ids[5:])
        self.assertEqual(study.preview(config)["slots"], self.slots[5:])
        # A file attempt 1 ran with, changed since, stops the builder.
        self.write_text("experiments/runners/browser_use_runner.py", "an observation fix\n")
        with self.assertRaisesRegex(SystemExit, "browser_use_runner.py"):
            launch.config_continuation("head")

    def test_a_failing_test_log_or_a_changed_shop_log_is_refused(self):
        self.write_text(f"{NOTES}/live-check.log", "62 checks, 0 failed\n")
        self.write("reference/attempt2-command.json", {"dependencies_lock": "lock.txt"})
        self.write("study-a-preflight.json", {"verdict": "PASS", "shop_check": {
            "failed": 0, "log": f"{NOTES}/live-check.log", "log_sha256": "0" * 64}})
        log = self.write_text(f"{NOTES}/tests.log", "Ran 4 tests in 0.1s\n\nFAILED (failures=1)\n")
        with self.assertRaisesRegex(SystemExit, "passing test run"):
            launch.continuation_preflight(log, packages="")
        log.write_text("Ran 4 tests in 0.1s\n\nOK\n")
        with self.assertRaisesRegex(SystemExit, "live shop check"):
            launch.continuation_preflight(log, packages="")
        self.assertFalse(launch.CONTINUATION_PACKAGES.exists())


class Estimate(unittest.TestCase):
    def test_the_estimate_is_attempt1s_charge_per_slot_started(self):
        self.assertEqual(launch.continuation_estimate({"calls": [{"cost_usd": 0.05}] * 4 + [{"cost_usd": None}]}, 27),
                         1.1)  # 0.2 / 5 x 27 = 1.08, up to 1.10
        real = ROOT / LEDGER
        if not real.exists() or guard.sha(real) != guard.FRESH_ATTEMPT1_LEDGER_SHA256:
            self.skipTest("attempt 1's ledger is local to the laptop that ran it")
        self.assertEqual(launch.continuation_estimate(json.loads(real.read_text()), 27), 1.3)


class AgentFacing(unittest.TestCase):
    """Nothing the agent receives changes: compared with the cohort's commit, 966e711, and with
    the commit attempt 1 ran, b1c67c8."""

    def test_agent_facing_code_is_the_cohorts_at_966e711(self):
        old = git_show(COHORT, "experiments/runners/browser_use_transfer.py")
        if old is None:
            self.skipTest("the cohort's commit is not in this clone")
        current = (ROOT / "experiments/runners/browser_use_transfer.py").read_text()
        self.assertEqual(guard.agent_facing_digests(current), guard.agent_facing_digests(old.decode()))
        self.assertEqual(guard.agent_facing_digests(current), guard.AGENT_FACING)

        def block(source):  # the block arm's parser settings and call, up to the query build
            start = source.index('            if slot["condition"] == "block":')
            return source[start:source.index("query, decision = await asyncio.to_thread(build_query", start)]
        self.assertEqual(block(current), block(old.decode()))
        listed = subprocess.run(["git", "ls-tree", "--name-only", COHORT, "experiments/box/"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.split()
        frozen = [name for name in listed if name.endswith(".py")]
        self.assertEqual(sorted(frozen), sorted(str(p.relative_to(ROOT)) for p in (ROOT / "experiments/box").glob("*.py")))
        for name in frozen + ["experiments/runners/browser_use_runner.py", "experiments/paths.py",
                              "experiments/browser-use-macos-py311.lock.txt"]:
            with self.subTest(name=name):
                self.assertEqual((ROOT / name).read_bytes(), git_show(COHORT, name))

    def test_the_listener_and_the_questions_are_the_ones_attempt1_ran(self):
        if git_show(ATTEMPT1, "experiments/runners/browser_use_fetches.py") is None:
            self.skipTest("attempt 1's commit is not in this clone")
        for name in ("experiments/runners/browser_use_fetches.py", "experiments/runners/browser_use_runner.py",
                     "experiments/tasks/tasks_tee_fresh_2_nov.json", "experiments/tasks/readings_tee_fresh_2_nov.json",
                     "env/fixtures/tee_fresh_2_nov.json"):
            with self.subTest(name=name):
                self.assertEqual((ROOT / name).read_bytes(), git_show(ATTEMPT1, name))


if __name__ == "__main__":
    unittest.main()
