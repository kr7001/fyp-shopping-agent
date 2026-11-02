"""Study A's timeout reruns under amendment 4, 2 November 2026: synthetic inputs only, no paid,
model, account or browser call. Each slot whose primary record reached its 2700 s clock runs once
more with its clock doubled, in schedule order, as a record of its own that links to the primary
one and never replaces it. Each check is shown quiet on a good case and firing on a planted fault."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401
import browser_use_transfer as study  # noqa: E402
import guarded_browser_use as guard  # noqa: E402
import fresh_market_launch as launch  # noqa: E402
from test_browser_use_amendment4 import Attempt2Ended, run_attempt3  # noqa: E402
from test_browser_use_fresh_continuation import BOUND  # noqa: E402

NOTES = guard.FRESH_NOTES
RERUN = guard.FRESH_RERUN_STAGE
THIRD = guard.FRESH_ATTEMPT3_STAGE
L1, L2, L3 = (guard.FRESH_LEDGER[stage] for stage in (guard.FRESH_STAGE, guard.FRESH_CONTINUATION_STAGE, THIRD))
THIRD_SHA = "3" * 64  # attempt 3's command, as its status and records name it


class Ended(Attempt2Ended):
    """Attempt 2 ended after an answer, a clock timeout and a void, then stopped mid-slot; attempt 3
    then ran the 23 slots left: a clock timeout first, then answers."""

    def setUp(self):
        super().setUp()
        self.given3 = self.given[4:]
        self.end_attempt3()

    def end_attempt3(self, ran=("timeout",) + ("answered",) * 22, status="complete"):
        results = self.notes / "study-a-attempt3.results"
        if results.exists():
            for path in results.iterdir():
                path.unlink()
        statuses, completed = {}, []
        for i, slot in enumerate(self.given3):
            outcome = ran[i] if i < len(ran) else "not_started"
            row = {"phase": "transfer", "status": outcome}
            if outcome == "timeout":
                row.update(disposition="timeout", reason="the trial clock: 2705 s against 2700 s")
            if outcome != "not_started":
                self.write(f"study-a-attempt3.results/{slot['id']}.json", {
                    "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                    "condition": slot["condition"], "phase": "transfer", "stage": THIRD, "attempt": 3,
                    "study_id": guard.FRESH_BUDGET, "batch_id": guard.FRESH_BUDGET, "config_sha256": THIRD_SHA,
                    "outcome": outcome, "answer": "Synthetic content never read for eligibility",
                    "elapsed_s": 2705.0 if outcome == "timeout" else 600.0, "settings": {"clock_s": 2700},
                    **({"disposition": "timeout"} if outcome == "timeout" else {}),
                    "calls": [{"cost_usd": 0.03}, {"cost_usd": None, "settled_usd": BOUND}]})
                completed.append(slot["id"])
            statuses[slot["id"]] = row
        self.write("study-a-attempt3.results/schedule.json", {"study_id": guard.FRESH_BUDGET, "stage": THIRD,
                                                              "batch_id": guard.FRESH_BUDGET, "attempt": 3,
                                                              "slots": self.given3})
        self.write("study-a-attempt3.results/slot-status.json", {"slots": statuses})
        self.write("study-a-attempt3.results/completed.json", {"completed": completed, "expected": len(self.given3)})
        self.write("study-a-attempt3.status.json", {"status": status, "config_sha256": THIRD_SHA})
        self.write("study-a-attempt3.launch.json", {"study_budget_id": guard.FRESH_BUDGET, "attempt": 3,
                                                    "config_sha256": THIRD_SHA})
        self.ledger3 = {"schema": 1, "charged_usd": 0.5, "inflight": {}, "blocked_reason": None,
                        "calls": [{"reservation": "call-00001", "role": "executor", "reserved_usd": BOUND,
                                   "cost_usd": 0.5, "error": False},
                                  {"reservation": "call-00002", "role": "executor", "reserved_usd": BOUND,
                                   "cost_usd": None, "settled_usd": BOUND, "error": True}],
                        "start_usage": 102.0, "highwater_usage": 102.5, "carryover_usd": 1.0,
                        "prior_unsettled_reserve_usd": 5 * BOUND, "prior_ledger_files": [L1, L2],
                        "study_budget_id": guard.FRESH_BUDGET, "attempt": 3, "shared_cap_usd": 10.0}
        self.write("study-a-attempt3.ledger.json", self.ledger3)

    def build_rerun(self, **options):
        for name in ("study-a-rerun-command.json", "study-a-rerun-command.argv.json", "study-a-rerun.approval.json",
                     "study-a-rerun-reconciliation.json"):
            (self.notes / name).unlink(missing_ok=True)
        output = self.notes / "study-a-rerun-command.json"
        with redirect_stdout(io.StringIO()):
            launch.a_rerun(output, self.preflight, **options)
        return json.loads(output.read_text())

    def end_attempt2_with_its_timeout(self):
        """Attempt 2's timeout record as the worker writes it, with its clock and elapsed time."""
        slot = self.given[1]
        path = self.notes / f"study-a-continuation.results/{slot['id']}.json"
        record = json.loads(path.read_text())
        path.write_text(json.dumps({**record, "elapsed_s": 2711.7, "settings": {"clock_s": 2700},
                                    "disposition": "timeout", "calls": [{"cost_usd": 0.1}]}))

    def rebind(self, config):
        config["hashes"] = {name: guard.sha(self.repo / name) for name in config["hashes"]}


class Slots(Ended):
    def setUp(self):
        super().setUp()
        self.end_attempt2_with_its_timeout()

    def test_every_clock_timeout_of_attempts_2_and_3_once_in_schedule_order(self):
        config = self.build_rerun()
        rows = config["rerun_slots"]
        self.assertEqual([row["slot"] for row in rows], [self.given[1]["id"], self.given3[0]["id"]])
        self.assertEqual([(row["stage"], row["attempt"]) for row in rows],
                         [(guard.FRESH_CONTINUATION_STAGE, 2), (THIRD, 3)])
        self.assertEqual(rows[0]["record"], f"{NOTES}/study-a-continuation.results/{self.given[1]['id']}.json")
        self.assertEqual(rows[0]["record_sha256"], guard.sha(self.repo / rows[0]["record"]))
        self.assertEqual((config["clock_s"], config["rerun_clock_s"], config["attempt"]), (2700, 5400, "timeout-rerun"))
        plan = study.preview(config)
        self.assertEqual([slot["clock_s"] for slot in plan["slots"]], [5400, 5400])
        by_id = {slot["id"]: slot for slot in self.slots}
        for slot, row in zip(plan["slots"], rows):
            self.assertEqual(slot["rerun_of"], row)
            self.assertEqual({k: v for k, v in slot.items() if k not in ("clock_s", "rerun_of")},
                             {k: v for k, v in by_id[row["slot"]].items() if k != "clock_s"})
        self.assertEqual((plan["stage"], plan["attempt"], plan["rerun_clock_s"]), (RERUN, "timeout-rerun", 5400))
        # Twice the known charges of the timed-out records: 2 x (0.1 + 0.03), up to the next ten cents.
        self.assertEqual(config["estimate_usd"], 0.3)

    def test_a_timeout_before_its_clock_or_any_other_slot_is_not_rerun(self):
        # A timeout the frozen classification stopped the batch on has no disposition: a void.
        statuses = json.loads((self.notes / "study-a-attempt3.results/slot-status.json").read_text())["slots"]
        statuses[self.given3[0]["id"]].pop("disposition")
        self.write("study-a-attempt3.results/slot-status.json", {"slots": statuses})
        config = self.build_rerun()
        self.assertEqual([row["slot"] for row in config["rerun_slots"]], [self.given[1]["id"]])
        # A record that calls itself a clock timeout below its clock is not believed.
        statuses[self.given3[0]["id"]]["disposition"] = "timeout"
        self.write("study-a-attempt3.results/slot-status.json", {"slots": statuses})
        record = self.notes / f"study-a-attempt3.results/{self.given3[0]['id']}.json"
        record.write_text(json.dumps({**json.loads(record.read_text()), "elapsed_s": 2699.0}))
        with self.assertRaisesRegex(SystemExit, "does not show its 2700 s clock reached"):
            self.build_rerun()

    def test_refuses_a_slot_that_is_not_a_timeout_or_a_second_rerun(self):
        config = self.build_rerun()
        answered = {**config["rerun_slots"][0], "slot": self.given[0]["id"]}
        for rows, message in (([answered] + config["rerun_slots"], "is not a timeout"),
                              (config["rerun_slots"] + config["rerun_slots"][:1], "rerun once"),
                              (config["rerun_slots"][:1], "every timed-out slot"),
                              (config["rerun_slots"][::-1], "every timed-out slot")):
            with self.subTest(rows=[row["slot"] for row in rows]), self.assertRaisesRegex(guard.Stop, message):
                guard.validate_fresh_rerun({**config, "rerun_slots": rows})
        guard.validate_fresh_rerun(config)
        self.write("study-a-rerun.launch.json", {"attempt": "timeout-rerun"})  # the stage has been launched
        with self.assertRaisesRegex(guard.Stop, "rerun once"):
            guard.validate_fresh_rerun(config)
        # And attempt 3 can no longer run, since the reruns' carryover leaves it out.
        with self.assertRaisesRegex(guard.Stop, "before the timeout reruns"):
            guard.validate_fresh_attempt3({**config, "stage": THIRD})

    def test_the_clock_is_doubled_and_nothing_else_changes(self):
        config = self.build_rerun()
        for change, message in (({"rerun_clock_s": 2700}, "doubles"), ({"rerun_clock_s": 8100}, "doubles"),
                                ({"clock_s": 5400}, "doubles|condition unchanged"),
                                ({"temperature": 0.5}, "condition unchanged"),
                                ({"max_steps": 300}, "condition unchanged")):
            with self.subTest(change=change), self.assertRaisesRegex(guard.Stop, message):
                guard.validate_fresh_rerun({**config, **change})

    def test_a_primary_record_changed_after_binding_is_refused(self):
        config = self.build_rerun()
        record = self.repo / config["rerun_slots"][0]["record"]
        record.write_text(json.dumps({**json.loads(record.read_text()), "answer": "Mutated synthetic answer"}))
        # Its hash is in the rerun list and in the bound evidence: either refuses.
        with self.assertRaisesRegex(guard.Stop, "every timed-out slot|changed after it was bound"):
            guard.validate_fresh_rerun(config)
        config["rerun_slots"][0]["record_sha256"] = guard.sha(record)
        with self.assertRaisesRegex(guard.Stop, "changed after it was bound"):
            guard.validate_fresh_rerun(config)


class Carryover(Ended):
    def setUp(self):
        super().setUp()
        self.end_attempt2_with_its_timeout()

    def test_attempt3_is_carried_when_it_ran(self):
        config = self.build_rerun()
        self.assertEqual(config["prior_ledger_files"], [L1, L2, L3])
        names = [L1, L2, L3]
        expected = guard.carried_spend([self.repo / name for name in names], names)[0]
        self.assertEqual(config["carryover_usd"], expected)
        self.assertAlmostEqual(config["cap_usd"], 10.0 - expected, places=12)
        guard.validate_fresh_budget(config)
        for chain in ([L1, L2], [L1, L3, L2]):
            with self.subTest(chain=chain), self.assertRaises(guard.Stop):
                guard.validate_fresh_rerun({**config, "prior_ledger_files": chain})
        # A carryover above or below the counted spend, its reconciliation written to match.
        path = self.repo / guard.FRESH_A4_RECONCILIATION[RERUN]
        for carry in (expected + 0.01, expected - BOUND):
            with self.subTest(carry=carry):
                path.write_text(json.dumps({**json.loads(path.read_text()), "carryover_usd": carry}))
                changed = {**config, "carryover_usd": carry, "cap_usd": 10.0 - carry}
                self.rebind(changed)
                with self.assertRaises(guard.Stop):
                    guard.validate_fresh_rerun(changed)

    def test_without_attempt3_only_attempts_1_and_2_are_carried(self):
        for path in list((self.notes / "study-a-attempt3.results").iterdir()):
            path.unlink()
        (self.notes / "study-a-attempt3.results").rmdir()
        for name in ("status.json", "launch.json", "ledger.json"):
            (self.notes / f"study-a-attempt3.{name}").unlink()
        config = self.build_rerun()
        self.assertEqual(config["prior_ledger_files"], [L1, L2])
        self.assertEqual([row["slot"] for row in config["rerun_slots"]], [self.given[1]["id"]])

    def test_attempt3_must_have_ended(self):
        self.write("study-a-attempt3.status.json", {"status": "running", "config_sha256": THIRD_SHA})
        with self.assertRaisesRegex(SystemExit, "terminal status"):
            self.build_rerun()
        (self.notes / "study-a-attempt3.status.json").unlink()
        with self.assertRaisesRegex(SystemExit, "has not ended"):
            self.build_rerun()


class NothingToRerun(Ended):
    def test_with_no_timeout_the_launch_ends_without_a_paid_call(self):
        self.end_attempt2(ran=("answered", "answered", "failed"))
        self.end_attempt3(ran=("answered",) * 23)
        config = self.build_rerun()
        self.assertEqual((config["rerun_slots"], config["estimate_usd"]), ([], 0))
        path = self.notes / "study-a-rerun-command.json"
        with mock.patch.object(guard, "validate_config", return_value=config), \
                mock.patch.object(guard, "account_snapshot", side_effect=AssertionError("no account read")), \
                redirect_stdout(io.StringIO()) as said:
            guard.execute(path)
        self.assertIn("without a paid call", said.getvalue())
        self.assertFalse((self.notes / "study-a-rerun.launch.json").exists())


class Batch(Ended, unittest.IsolatedAsyncioTestCase):
    async def test_rerun_records_are_their_own_and_link_to_the_primary_ones(self):
        self.end_attempt2_with_its_timeout()
        config = {**self.build_rerun(), "start_cutoff": "2099-01-01T00:00:00+08:00"}
        before = {path: guard.sha(path) for path in self.notes.rglob("*") if path.is_file()}

        def long_timeout():
            return {"outcome": "timeout", "answer": None, "trace": {"measurement_valid": True},
                    "elapsed_s": 5403.0, "settings": {"clock_s": 5400}, "cost_usd": None}
        run = await run_attempt3(self, config, results={1: long_timeout})
        self.assertIsNone(run.error)
        self.assertEqual(run.output, self.notes / "study-a-rerun.results")
        self.assertEqual(run.trials, [row["slot"] for row in config["rerun_slots"]])
        first = json.loads((run.output / f"{config['rerun_slots'][0]['slot']}.json").read_text())
        self.assertEqual((first["stage"], first["attempt"], first["rerun_of"]),
                         (RERUN, "timeout-rerun", config["rerun_slots"][0]))
        second = json.loads((run.output / f"{config['rerun_slots'][1]['slot']}.json").read_text())
        self.assertEqual(second["disposition"], "timeout")
        self.assertIn("against 5400 s", second["disposition_reason"])
        after = {path: guard.sha(path) for path in before}
        self.assertEqual(after, before)  # every primary record and file untouched


class ConditionFields(unittest.TestCase):
    def test_the_condition_later_stages_keep_is_the_one_attempt2_was_held_to(self):
        import ast
        import inspect
        source = inspect.getsource(guard.validate_fresh_continuation)
        held = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", None) == "condition")
        self.assertEqual(ast.literal_eval(held.value), guard.FRESH_CONDITION)


if __name__ == "__main__":
    unittest.main()
