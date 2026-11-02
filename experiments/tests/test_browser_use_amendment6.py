"""Study A under amendment 6, 2 November 2026: synthetic inputs only, no paid, model, account or
browser call. Attempt 3 stopped at 17:31 on an executor's error reply without usage. Attempt 4
runs only the slots attempt 3 never started; in attempt 4 and the reruns such a reply is settled
at its bound and counted toward the run of 3 that stops the batch; the reruns wait for attempt 4.
Each check is shown quiet on a good case and firing on a planted fault."""
import contextlib
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401
import browser_use_transfer as study  # noqa: E402
import guarded_browser_use as guard  # noqa: E402
import fresh_market_launch as launch  # noqa: E402
from test_browser_use_amendment4 import run_attempt3  # noqa: E402
from test_browser_use_amendment4_rerun import Ended  # noqa: E402
from test_browser_use_fresh_continuation import BOUND, PROVIDER  # noqa: E402

NOTES = guard.FRESH_NOTES
FOURTH = guard.FRESH_ATTEMPT4_STAGE
L1, L2, L3, L4 = (guard.FRESH_LEDGER[stage] for stage in (guard.FRESH_STAGE, guard.FRESH_CONTINUATION_STAGE,
                                                          guard.FRESH_ATTEMPT3_STAGE, FOURTH))
# Attempt 3 as it ended: its slots answered, then one interrupted, then four never started.
ENDED = ("answered",) * 18 + ("interrupted",)


class Attempt3Ended(Ended):
    """Attempt 3 built by its own builder, pinned as the real one is, and ended as it did at 17:31."""

    def setUp(self):
        super().setUp()
        self.end_attempt2_with_its_timeout()  # before attempt 3's command binds attempt 2's records
        self.third = self.build()  # study-a-attempt3-command.json, as the launch tool writes it
        self.patch(guard, "FRESH_ATTEMPT3_SHA256", guard.sha(self.notes / "study-a-attempt3-command.json"))
        self.end_attempt3(ran=ENDED, status="stopped", sha=guard.FRESH_ATTEMPT3_SHA256,
                          carryover=self.third["carryover_usd"])
        self.ids3 = [slot["id"] for slot in self.given3]

    def build4(self, **options):
        for name in ("study-a-attempt4-command.json", "study-a-attempt4-command.argv.json",
                     "study-a-attempt4.approval.json", "study-a-attempt4-reconciliation.json"):
            (self.notes / name).unlink(missing_ok=True)
        output = self.notes / "study-a-attempt4-command.json"
        with redirect_stdout(io.StringIO()):
            launch.attempt4(output, self.preflight, **options)
        return json.loads(output.read_text())

    def end_attempt4(self, config, outcomes=("answered",) * 4):
        """Attempt 4's files as its launcher and worker leave them, every slot it was given run."""
        sha4 = guard.sha(self.notes / "study-a-attempt4-command.json")
        given = [slot for slot in self.slots if slot["id"] in config["slot_ids"]]
        for slot, outcome in zip(given, outcomes):
            self.write(f"study-a-attempt4.results/{slot['id']}.json", {
                "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                "condition": slot["condition"], "phase": "transfer", "stage": FOURTH, "attempt": 4,
                "study_id": guard.FRESH_BUDGET, "batch_id": guard.FRESH_BUDGET, "config_sha256": sha4,
                "outcome": outcome, "elapsed_s": 2704.0 if outcome == "timeout" else 300.0,
                "settings": {"clock_s": 2700}, **({"disposition": "timeout"} if outcome == "timeout" else {}),
                "calls": [{"cost_usd": 0.02}]})
        statuses = {slot["id"]: {"phase": "transfer", "status": outcome,
                                 **({"disposition": "timeout"} if outcome == "timeout" else {})}
                    for slot, outcome in zip(given, outcomes)}
        self.write("study-a-attempt4.results/schedule.json", {"study_id": guard.FRESH_BUDGET, "stage": FOURTH,
                                                              "batch_id": guard.FRESH_BUDGET, "attempt": 4,
                                                              "slots": given})
        self.write("study-a-attempt4.results/slot-status.json", {"slots": statuses})
        self.write("study-a-attempt4.results/completed.json", {"completed": [s["id"] for s in given], "expected": 4})
        self.write("study-a-attempt4.status.json", {"status": "complete", "config_sha256": sha4})
        self.write("study-a-attempt4.launch.json", {"study_budget_id": guard.FRESH_BUDGET, "attempt": 4,
                                                    "config_sha256": sha4})
        self.write("study-a-attempt4.ledger.json", {
            "schema": 1, "charged_usd": 0.08, "inflight": {}, "blocked_reason": None,
            "calls": [{"reservation": "call-00001", "role": "executor", "reserved_usd": BOUND, "cost_usd": 0.08,
                       "error": False}], "start_usage": 103.0, "highwater_usage": 103.08,
            "carryover_usd": config["carryover_usd"], "prior_unsettled_reserve_usd": 0.0,
            "prior_ledger_files": [L1, L2, L3], "study_budget_id": guard.FRESH_BUDGET, "attempt": 4})


class Attempt4Slots(Attempt3Ended):
    def test_picks_exactly_the_four_attempt3_never_started_in_order(self):
        config = self.build4()
        self.assertEqual(config["slot_ids"], self.ids3[19:])
        self.assertEqual(len(config["slot_ids"]), 4)
        self.assertNotIn(self.ids3[18], config["slot_ids"])  # interrupted: a technical void, never re-run
        self.assertEqual(guard.validate_fresh_attempt4(config), self.ids3[19:])
        plan = study.preview(config)
        self.assertEqual(([slot["id"] for slot in plan["slots"]], plan["attempt"], plan["stage"]),
                         (self.ids3[19:], 4, FOURTH))
        self.assertEqual((config["attempt"], config["shared_cap_usd"], config["prior_ledger_files"]),
                         (4, 10.0, [L1, L2, L3]))
        names = [L1, L2, L3]
        self.assertEqual(config["carryover_usd"], guard.carried_spend([self.repo / n for n in names], names)[0])
        self.assertAlmostEqual(config["cap_usd"], 10.0 - config["carryover_usd"], places=12)
        guard.validate_fresh_budget(config)
        for name in ("amendment-6-2-nov.md", f"study-a-attempt3.results/{self.ids3[18]}.interrupted.json",
                     "study-a-attempt3-command.json"):
            self.assertIn(f"{NOTES}/{name}", config["hashes"])

    def test_other_slots_another_command_or_an_unbound_record_are_refused(self):
        config = self.build4()
        for slot_ids in (self.ids3[18:], self.ids3[20:], self.ids3[19:][::-1], []):
            with self.subTest(slot_ids=len(slot_ids)), self.assertRaisesRegex(guard.Stop, "never started"):
                guard.validate_fresh_attempt4({**config, "slot_ids": slot_ids})
        for change, message in (({"temperature": 0.5}, "condition unchanged"),
                                ({"prior_config_file": f"{NOTES}/study-a-continuation-command.json"}, "own files"),
                                ({"prior_ledger_files": [L1, L2]}, "carryover|chain|prior")):
            with self.subTest(change=change), self.assertRaisesRegex(guard.Stop, message):
                guard.validate_fresh_attempt4({**config, **change})
        # A carryover above or below the counted spend, its reconciliation written to match.
        path = self.repo / guard.FRESH_A4_RECONCILIATION[FOURTH]
        for carry in (config["carryover_usd"] + 0.01, config["carryover_usd"] - BOUND):
            with self.subTest(carry=carry):
                path.write_text(json.dumps({**json.loads(path.read_text()), "carryover_usd": carry}))
                changed = {**config, "carryover_usd": carry, "cap_usd": 10.0 - carry}
                changed["hashes"] = {**config["hashes"], guard.FRESH_A4_RECONCILIATION[FOURTH]: guard.sha(path)}
                with self.assertRaises(guard.Stop):
                    guard.validate_fresh_attempt4(changed)
        path.write_text(json.dumps({**json.loads(path.read_text()), "carryover_usd": config["carryover_usd"]}))
        with self.assertRaisesRegex(guard.Stop, "hash-bound"):
            interrupted = f"{NOTES}/study-a-attempt3.results/{self.ids3[18]}.interrupted.json"
            guard.validate_fresh_attempt4({**config, "hashes": {k: v for k, v in config["hashes"].items()
                                                                 if k != interrupted}})
        third = self.notes / "study-a-attempt3-command.json"
        third.write_text(third.read_text().replace('"attempt": 3', '"attempt": 3 '))
        with self.assertRaisesRegex(guard.Stop, "exact command"):
            guard.validate_fresh_attempt4(config)
        # Attempt 3's own slots are held to the ones attempt 2 left never started.
        third.write_text(json.dumps({**self.third, "slot_ids": self.third["slot_ids"][:-1]}))
        with mock.patch.object(guard, "FRESH_ATTEMPT3_SHA256", guard.sha(third)), \
                self.assertRaisesRegex(guard.Stop, "attempt 3's slots are not the ones attempt 2 left"):
            guard.validate_fresh_attempt4(config)

    def test_with_no_slot_left_the_launch_ends_without_a_paid_call(self):
        self.end_attempt3(ran=("answered",) * 23, status="complete", sha=guard.FRESH_ATTEMPT3_SHA256,
                          carryover=self.third["carryover_usd"])
        config = self.build4()
        self.assertEqual((config["slot_ids"], config["estimate_usd"]), ([], 0))
        with mock.patch.object(guard, "validate_config", return_value=config), \
                mock.patch.object(guard, "account_snapshot", side_effect=AssertionError("no account read")), \
                redirect_stdout(io.StringIO()) as said:
            guard.execute(self.notes / "study-a-attempt4-command.json")
        self.assertIn("without a paid call", said.getvalue())
        self.assertFalse(guard.launched(self.repo, FOURTH))

    def test_the_builder_takes_a_relative_output_path(self):
        rel = Path(NOTES) / "study-a-attempt4-command.json"
        argv = ["fresh_market_launch.py", "attempt4", "--preflight", str(Path(NOTES) / "study-a-a4-preflight.json"),
                "--output", str(rel)]
        with contextlib.chdir(self.repo), mock.patch.object(sys, "argv", argv), \
                redirect_stdout(io.StringIO()) as said:
            self.assertEqual(launch.main(), 0)
        self.assertIn(f"written {rel}  sha256", said.getvalue())


class Batch(Attempt3Ended, unittest.IsolatedAsyncioTestCase):
    async def test_runs_the_four_and_counts_error_replies_in_their_records(self):
        config = {**self.build4(), "start_cutoff": "2099-01-01T00:00:00+08:00"}

        def after_an_error_reply():  # the guard settled an error reply during this trial
            study.CallBudget.return_value.state["calls"].append(
                {"reservation": "call-00007", "role": "executor", "cost_usd": None, "settled_usd": BOUND,
                 "settlement_kind": "error reply without usage", "error": True})
            return {"outcome": "answered", "answer": "synthetic answer", "agent_errors": [None],
                    "trace": {"measurement_valid": True}, "elapsed_s": 300.0, "settings": {"clock_s": 2700},
                    "cost_usd": None}
        run = await run_attempt3(self, config, results={0: after_an_error_reply})
        self.assertIsNone(run.error)
        self.assertEqual((run.trials, run.output), (self.ids3[19:], self.notes / "study-a-attempt4.results"))
        record = json.loads((run.output / f"{self.ids3[19]}.json").read_text())
        self.assertEqual((record["stage"], record["attempt"], record["error_reply_settlements"],
                          record["no_response_settlements"], record["settled_bound_usd"]), (FOURTH, 4, 1, 1, BOUND))


class Order(Attempt3Ended):
    def test_the_reruns_wait_for_attempt4_and_then_carry_it(self):
        with self.assertRaisesRegex(SystemExit, "attempt 3 left slots never started and attempt 4 has not run"):
            self.build_rerun()
        config4 = self.build4()
        self.end_attempt4(config4, outcomes=("answered", "timeout", "answered", "answered"))
        rerun = self.build_rerun()
        self.assertEqual(rerun["prior_ledger_files"], [L1, L2, L3, L4])
        self.assertIn(config4["slot_ids"][1], [row["slot"] for row in rerun["rerun_slots"]])
        self.assertEqual([row["attempt"] for row in rerun["rerun_slots"]][-1:], [4])
        guard.validate_fresh_budget(rerun)
        # Attempt 4 is refused once the reruns have been launched.
        self.write("study-a-rerun.launch.json", {"attempt": "timeout-rerun"})
        with self.assertRaisesRegex(guard.Stop, "before the timeout reruns"):
            guard.validate_fresh_attempt4(config4)

    def test_attempt4_must_have_ended(self):
        config4 = self.build4()
        self.end_attempt4(config4)
        self.write("study-a-attempt4.status.json", {"status": "running", "config_sha256": "x"})
        with self.assertRaisesRegex(SystemExit, "attempt 4: a later stage needs this stage's terminal status"):
            self.build_rerun()


def stage_budget(folder, stage):
    """A stage's spending guard, its prior evidence stood in for."""
    cfg = {"stage": stage, "attempt": 4, "cap_usd": 8.0, "minimum_balance_usd": 20.2117632,
           "deadline": "2099-01-01T00:00:00+08:00", "model": "deepseek/deepseek-v4-flash", "provider": PROVIDER,
           "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
           "allowed_served_providers": ["DeepInfra"], "prior_ledger_files": [L1, L2]}
    with mock.patch.object(guard, "validate_fresh_budget"), \
            mock.patch.object(guard, "recovery_limits", return_value=(2.0, 1.0)):
        return guard.CallBudget(cfg, Path(folder) / "ledger.json", lambda: {"usage": 100.0, "remaining": 60.0}), cfg


ERROR_REPLY = {"error": {"message": "Provider returned error", "code": 502}}


class ErrorReplies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def meta(self, budget, role="executor"):
        return {"model": "deepseek/deepseek-v4-flash", "provider": PROVIDER, "prompt_bytes": 1000,
                "max_output_tokens": 4096, "nontext_or_plugins": False, "role": role}

    def budget(self, stage, name="ledger"):
        folder = Path(self.tmp.name) / f"{name}-{stage}"
        folder.mkdir()
        return stage_budget(folder, stage)[0]

    def test_an_error_reply_without_usage_is_settled_in_attempt4_and_the_reruns(self):
        for stage in (FOURTH, guard.FRESH_RERUN_STAGE):
            for reply, error in ((ERROR_REPLY, "HTTP_502"),
                                 ({**ERROR_REPLY, "usage": {"prompt_tokens": 3}}, "HTTP_502"),  # usage without cost
                                 ({"error": "upstream reset"}, None)):                        # an error body, status 200
                with self.subTest(stage=stage, reply=reply):
                    budget = self.budget(stage, name=str(len(list(Path(self.tmp.name).iterdir()))))
                    budget.after_call(budget.before_call(self.meta(budget)), response_json=reply, error=error)
                    call, state = budget.state["calls"][-1], budget.state
                    self.assertEqual((call["settled_usd"], call["settlement_kind"], call["cost_usd"]),
                                     (BOUND, "error reply without usage", None))
                    self.assertIn(call["error_reply"], ("Provider returned error", "upstream reset"))
                    self.assertEqual(call["error_name"], error)
                    self.assertEqual((state["error_reply_settlements"], state["no_response_run"], state["blocked_reason"]),
                                     (1, 1, None))
                    self.assertAlmostEqual(state["settled_usd"], BOUND, places=12)

    def test_it_still_blocks_in_attempts_1_to_3_and_for_every_other_case(self):
        for stage in (guard.FRESH_STAGE, guard.FRESH_CONTINUATION_STAGE, guard.FRESH_ATTEMPT3_STAGE):
            with self.subTest(stage=stage):
                budget = self.budget(stage)
                with self.assertRaisesRegex(guard.Stop, "unknown charge"):
                    budget.after_call(budget.before_call(self.meta(budget)), response_json=ERROR_REPLY, error="HTTP_502")
        cases = {"a parser's error reply": ("parser", ERROR_REPLY, "HTTP_502", "unknown charge"),
                 "an unexpected provider": ("executor", {**ERROR_REPLY, "provider": "Other"}, "HTTP_502", "unknown charge"),
                 "a reply that is not an error": ("executor", {"id": "g", "provider": "DeepInfra"}, None, "unknown charge"),
                 "an error reply with a charge": ("executor", {**ERROR_REPLY, "provider": "DeepInfra",
                                                                "usage": {"cost": 0.001}}, "HTTP_502", "request failed")}
        for name, (role, reply, error, message) in cases.items():
            with self.subTest(case=name):
                budget = self.budget(FOURTH, name=name.replace(" ", "-").replace("'", ""))
                with self.assertRaisesRegex(guard.Stop, message):
                    budget.after_call(budget.before_call(self.meta(budget, role)), response_json=reply, error=error)
                self.assertEqual(budget.state["settled_usd"], 0.0)

    def test_three_in_a_row_mixed_stop_and_an_answer_breaks_the_run(self):
        budget = self.budget(FOURTH)

        def no_response():
            budget.after_call(budget.before_call(self.meta(budget)), error="CancelledError")

        def error_reply():
            budget.after_call(budget.before_call(self.meta(budget)), response_json=ERROR_REPLY, error="HTTP_502")

        def answered():
            budget.after_call(budget.before_call(self.meta(budget)),
                              response_json={"id": "g", "provider": "DeepInfra", "usage": {"cost": 0.001}})
        error_reply(), no_response(), answered(), no_response(), error_reply()
        self.assertEqual((budget.state["no_response_run"], budget.state["blocked_reason"]), (2, None))
        with self.assertRaisesRegex(guard.Stop, "no response or an error reply without usage"):
            error_reply()
        kinds = [call.get("settlement_kind") for call in budget.state["calls"]]
        self.assertEqual(kinds, ["error reply without usage", "no response", None, "no response",
                                 "error reply without usage", "error reply without usage"])
        self.assertEqual((budget.state["error_reply_settlements"], budget.state["no_response_settlements"]), (3, 2))


if __name__ == "__main__":
    unittest.main()
