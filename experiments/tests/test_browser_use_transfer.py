"""Transfer-design tests with synthetic observations and parser replies only."""
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
import page


def question(name="tee-cheapest-target"):
    return {"id": name, "query": "Go to http://localhost:7770/catalogsearch/result/?q=Example . Which Example tee seller is cheapest for size M?",
            "start_url": "http://localhost:7770/catalogsearch/result/?q=Example"}


def observation():
    return page.Page(question()["start_url"], [page.Listing("A", "Example Tee - A", "http://localhost:7770/a.html", 9)],
                     total=1, next_page=False, reader="rendered")


class Transfer(unittest.TestCase):
    def test_exact32_grid_and_balance(self):
        questions = [question(t) for t in study.TASK_IDS]
        rows = study.schedule(questions)
        self.assertEqual(len(rows), 32)
        self.assertEqual(len({r["id"] for r in rows}), 32)
        for task in study.TASK_IDS:
            self.assertEqual(len([r for r in rows if r["question"]["id"] == task]), 4)
        for repeat in (1, 2):
            starts = [rows[i]["condition"] for i in range(0, len(rows), 2) if rows[i]["repeat"] == repeat]
            self.assertEqual(starts.count("baseline"), 4)
            self.assertEqual(starts.count("block"), 4)

    def test_questions_cannot_carry_keys_or_fixture(self):
        for key in ("expect", "_instance", "fixture", "answer", "hand_verdict"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "only"):
                study.validate_questions([{**question(), key: "SECRET_KEY"}])

    def test_baseline_has_exact_warning_and_no_parser_or_candidate_list(self):
        parser = mock.Mock(side_effect=AssertionError("must not call parser"))
        query, decision = study.build_query(question(), "baseline", observation(), parser)
        self.assertEqual(query, study.COMMON_BRIEFING + "\n\n" + question()["query"])
        self.assertIsNone(decision)
        parser.assert_not_called()
        self.assertNotIn("a.html", query)

    def test_block_calls_frozen_decision_on_original_question_and_observation_only(self):
        observed = observation()
        parser = lambda prompt: "synthetic reply"
        decision = mock.Mock(query="original question plus frozen plan")
        with mock.patch.object(study.box, "decide", return_value=decision) as decide:
            query, got = study.build_query(question(), "block", observed, parser)
        decide.assert_called_once_with(question()["query"], observed, reply=None, parser="model", call=parser, rate="bound")
        self.assertEqual(query, study.COMMON_BRIEFING + "\n\n" + decision.query)
        self.assertIs(got, decision)

    def test_closed_block_does_not_create_execution_text(self):
        with mock.patch.object(study.box, "decide", return_value=mock.Mock(query=None)):
            query, _ = study.build_query(question(), "block", observation(), lambda _: "")
        self.assertIsNone(query)

    def test_real_frozen_rules_fallback_can_be_exercised_with_bad_synthetic_parser(self):
        query, decision = study.build_query(question(), "block", observation(), lambda _: "not json")
        self.assertTrue(decision.record())
        if query:
            self.assertTrue(query.startswith(study.COMMON_BRIEFING))

    def test_incomplete_or_nonrendered_observation_rejected(self):
        good = observation()
        import dataclasses
        for bad in (dataclasses.replace(good, next_page=True), dataclasses.replace(good, total=2),
                    dataclasses.replace(good, reader="fetch"), dataclasses.replace(good, scope="other")):
            with self.assertRaises(ValueError):
                study.build_query(question(), "baseline", bad)

    def test_remote_shops_rejected(self):
        q = question()
        q = {k: v.replace("localhost:7770", "merchant.example") for k, v in q.items()}
        with self.assertRaisesRegex(ValueError, "local"):
            study.validate_questions([q])

    def test_preview_never_builds_or_scores_any_answer(self):
        config = {"stage": "pilot", "questions": [question("a"), question("b")], "repeats": [1]}
        with mock.patch.object(study.box, "decide", side_effect=AssertionError("paid parse")):
            result = study.preview(config)
        self.assertEqual(result["paid_calls"], 0)
        self.assertEqual(len(result["slots"]), 4)

    def test_preview_rejects_question_file_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "questions.json"
            source.write_text(json.dumps({"questions": [question("different")]}))
            with self.assertRaisesRegex(ValueError, "hash-bound"):
                study.preview({"stage": "pilot", "questions": [question("a"), question("b")],
                               "repeats": [1], "questions_file": str(source)})

    def test_formal_questions_cannot_be_selected_after_outcomes(self):
        with self.assertRaisesRegex(ValueError, "32"):
            study.preview({"stage": "formal", "questions": [question("a")], "repeats": [1, 2]})

    def test_recovery_repeats_original_paired_questions_in_original_order(self):
        result = study.preview({"stage": "pilot-recovery", "questions": [question("tee-cheapest-target"), question("tee-count-buyable")],
                                "repeats": [1], "clock_s": 1800})
        self.assertEqual([r["condition"] for r in result["slots"]], ["baseline", "block", "block", "baseline"])
        self.assertEqual([r["question"]["id"] for r in result["slots"]],
                         ["tee-cheapest-target", "tee-cheapest-target", "tee-count-buyable", "tee-count-buyable"])
        self.assertEqual(result["paid_calls"], 0)

    def test_recovery_rejects_other_task_repeat_or_time_limit(self):
        config = {"stage": "pilot-recovery", "questions": [question("tee-cheapest-target"), question("tee-count-buyable")],
                  "repeats": [1], "clock_s": 1800}
        for change in ({"questions": [question("tee-count-buyable")]}, {"questions": list(reversed(config["questions"]))},
                       {"repeats": [1, 2]}, {"clock_s": 900}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "recovery"):
                study.preview({**config, **change})

    def test_technical_gate_does_not_score_answers_and_rejects_operational_failures(self):
        record = {"answer": "Deliberately wrong synthetic answer", "outcome": "answered", "trace": {"measurement_valid": True}}
        clear = {"blocked_reason": None, "inflight": {}}
        self.assertTrue(study.technical_gate([record] * 4, clear)["passed"])
        for bad in ({**record, "answer": ""}, {**record, "error_type": "Failure"},
                    {**record, "trace": {"measurement_valid": False}}):
            self.assertFalse(study.technical_gate([record] * 3 + [bad], clear)["passed"])
        recovered = {**record, "agent_errors": [None, "Cannot select disabled option", None]}
        self.assertTrue(study.technical_gate([record] * 3 + [recovered], clear)["passed"])
        self.assertFalse(study.technical_gate([record] * 4, {**clear, "inflight": {"pending": {}}})["passed"])
        self.assertFalse(study.technical_gate([record] * 3, clear)["passed"])

    def test_no_duplicate_repeat_or_task(self):
        with self.assertRaises(ValueError):
            study.schedule([question()], [1, 1])
        with self.assertRaises(ValueError):
            study.schedule([question(), question()])

    def test_pilot_failed_timeout_and_invalid_measurement_cannot_continue(self):
        for record in ({"outcome": "failed"}, {"outcome": "timeout"},
                       {"outcome": "answered", "error_type": "BrowserError"},
                       {"outcome": "answered", "trace": {"measurement_valid": False}}):
            with self.subTest(record=record), self.assertRaises(study.Stop):
                study.validate_pilot_record(record)
        study.validate_pilot_record({"outcome": "answered", "trace": {"measurement_valid": True}})
        study.validate_pilot_record({"outcome": "closed by the block"})

    def test_formal_failure_continues_only_with_valid_measurements(self):
        for outcome in ("failed", "timeout"):
            study.validate_pilot_record({"outcome": outcome, "timeout_kind": "trial_clock",
                                         "trace": {"measurement_valid": True}}, "transfer")
        with self.assertRaisesRegex(study.Stop, "measurement"):
            study.validate_pilot_record({"outcome": "failed", "trace": {"measurement_valid": False}}, "transfer")

    def test_unknown_infrastructure_and_unmarked_timeouts_stop(self):
        base = {"outcome": "failed", "trace": {"measurement_valid": True}}
        for error in ("CDP connection closed", "APITimeoutError", "WebSocket disconnected", "unexpected unexplained error"):
            with self.subTest(error=error), self.assertRaisesRegex(study.Stop, "infrastructure or unknown"):
                study.validate_pilot_record({**base, "agent_errors": [error]}, "transfer")
        with self.assertRaisesRegex(study.Stop, "unclassified"):
            study.validate_pilot_record({**base, "outcome": "timeout"}, "transfer")
        for error in ("SyntaxError: Unexpected token (", "Cannot select disabled option", "StaleElementReferenceException", "Maximum steps reached"):
            study.validate_pilot_record({**base, "agent_errors": [error]}, "transfer")
        native = "JavaScript Execution Failed:\nJavaScript execution error: Uncaught\n\nValidated Code:\nfetch('http://localhost/test')"
        study.validate_pilot_record({**base, "agent_errors": [native]}, "transfer")
        with self.assertRaisesRegex(study.Stop, "infrastructure or unknown"):
            study.validate_pilot_record({**base, "agent_errors": [native.replace("Uncaught", "CDP disconnected")]}, "transfer")

    def test_completed_answer_retains_recovered_unknown_action_error_without_filtering(self):
        record = {"outcome": "answered", "answer": "Synthetic answer", "trace": {"measurement_valid": True},
                  "agent_errors": ["An unfamiliar tool mistake that was recovered"]}
        study.validate_pilot_record(record, "transfer")
        self.assertEqual(len(record["agent_errors"]), 1)
        with self.assertRaisesRegex(study.Stop, "infrastructure or unknown"):
            study.validate_pilot_record({**record, "error_type": "ConnectionError"}, "transfer")

    def test_monitored_diagnostic_gate_accepts_ordinary_failures_but_not_infrastructure(self):
        failed = {"outcome": "failed", "answer": None, "trace": {"measurement_valid": True}, "agent_errors": ["SyntaxError"]}
        clear = {"blocked_reason": None, "inflight": {}}
        self.assertTrue(study.technical_gate([failed, failed], clear, expected=2, allow_agent_failures=True)["passed"])
        bad = {**failed, "agent_errors": ["CDP disconnected"]}
        self.assertFalse(study.technical_gate([failed, bad], clear, expected=2, allow_agent_failures=True)["passed"])


class PilotIntegration(unittest.IsolatedAsyncioTestCase):
    async def run_overnight(self, empty_pilot_answer=False, formal_failures=False, unknown_formal_charge=False, monitored=False, pilot_failures=False):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            transfer = [question(name) for name in study.TASK_IDS]
            questions_path = Path(folder) / "questions.json"
            questions_path.write_text(json.dumps({"questions": transfer}))
            config = {"stage": "overnight-transfer", "questions": [question("tee-cheapest-target"), question("tee-count-buyable")],
                      "repeats": [1], "clock_s": 2700, "transfer_clock_s": 2700, "transfer_questions": transfer,
                      "transfer_questions_file": str(questions_path), "environment_file": "unused",
                      "ledger_path": "unused", "output_dir": str(output)}
            pilot_count = 2 if monitored else 4
            if monitored:
                config.update(stage="monitored-transfer", questions=[question("tee-count-buyable")])
            plan = study.preview(config)
            self.assertEqual(len(plan["slots"]), pilot_count + 16)
            self.assertEqual(len({r["id"] for r in plan["slots"]}), pilot_count + 16)
            if monitored:
                self.assertEqual([r["condition"] for r in plan["slots"][:2]], ["block", "baseline"])
            budgets = []
            def make_budget(*args):
                budget = types.SimpleNamespace(state={"calls": [], "inflight": {}, "blocked_reason": None})
                budgets.append(budget)
                return budget
            trials = []
            async def run_trial(trial, budget, **kwargs):
                trials.append(trial)
                outcome = ("failed" if len(trials) == 5 else "timeout") if formal_failures and len(trials) in (5, 6) else "answered"
                if pilot_failures and len(trials) <= pilot_count:
                    outcome = "failed"
                if unknown_formal_charge and len(trials) == 5:
                    budget.state["blocked_reason"] = "unknown charge"
                return {"outcome": outcome, "timeout_kind": "trial_clock", "cost_usd": 0, "trace": {"measurement_valid": True},
                        "answer": "" if empty_pilot_answer and len(trials) == 2 else "Synthetic unscored answer"}
            adapter = types.SimpleNamespace(create_llm=mock.Mock(), close_llm=mock.AsyncMock(),
                                            run_trial=run_trial, configure_private_runtime=mock.Mock())
            with mock.patch.dict(sys.modules, {"browser_use_runner": adapter, "browser_use.llm.messages": types.SimpleNamespace(UserMessage=mock.Mock())}), \
                 mock.patch.dict(study.os.environ, {"IGR_BROWSER_USE_GUARD": "test", "IGR_BROWSER_USE_CONFIG_SHA256": "hash"}), \
                 mock.patch.object(study, "validate_config", return_value=config), \
                 mock.patch.object(study, "sha", return_value="hash"), \
                 mock.patch.object(study, "read_key", return_value="SYNTHETIC"), \
                 mock.patch.object(study, "CallBudget", side_effect=make_budget), \
                 mock.patch.object(study, "read_observation", return_value=observation()), \
                 mock.patch.object(study, "build_query", return_value=("Synthetic query", None)):
                if empty_pilot_answer:
                    with self.assertRaisesRegex(study.Stop, "technical gate"):
                        await study.execute_study("unused")
                elif unknown_formal_charge:
                    with self.assertRaisesRegex(study.Stop, "unknown charge"):
                        await study.execute_study("unused")
                else:
                    await study.execute_study("unused")
            self.assertEqual(len(budgets), 1)
            gate = json.loads((output / "development-gate.json").read_text())
            self.assertEqual(gate["passed"], not empty_pilot_answer)
            self.assertEqual(gate["kind"], "technical_only")
            self.assertEqual(len(trials), pilot_count if empty_pilot_answer else 5 if unknown_formal_charge else pilot_count + 16)
            self.assertEqual([t["clock_s"] for t in trials], [2700] * len(trials))
            if formal_failures:
                rows = json.loads((output / "slot-status.json").read_text())["slots"]
                self.assertEqual(rows[plan["slots"][4]["id"]]["status"], "failed")
                self.assertEqual(rows[plan["slots"][5]["id"]]["status"], "timeout")

    async def test_overnight_runs20_slots_with_one_shared_budget_after_technical_gate(self):
        await self.run_overnight()

    async def test_failed_technical_gate_never_starts_transfer(self):
        await self.run_overnight(empty_pilot_answer=True)

    async def test_formal_failures_are_retained_and_schedule_continues_without_replay(self):
        await self.run_overnight(formal_failures=True)

    async def test_unknown_formal_charge_still_stops_immediately(self):
        await self.run_overnight(unknown_formal_charge=True)

    async def test_monitored_runs18_slots_after_two_valid_failed_diagnostics_without_replay(self):
        await self.run_overnight(monitored=True, pilot_failures=True)

    async def test_failed_slot_is_saved_and_stops_before_next_trial(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            config = {"stage": "pilot", "questions": [question("a"), question("b")], "repeats": [1],
                      "clock_s": 900, "environment_file": "unused", "ledger_path": "unused", "output_dir": str(output)}
            budget = types.SimpleNamespace(state={"calls": [], "inflight": {}, "blocked_reason": None})
            run = mock.AsyncMock(return_value={"outcome": "timeout", "cost_usd": 0, "answer": None})
            adapter = types.SimpleNamespace(create_llm=mock.Mock(), close_llm=mock.AsyncMock(),
                                            run_trial=run, configure_private_runtime=mock.Mock())
            messages = types.SimpleNamespace(UserMessage=mock.Mock())
            with mock.patch.dict(sys.modules, {"browser_use_runner": adapter, "browser_use.llm.messages": messages}), \
                 mock.patch.dict(study.os.environ, {"IGR_BROWSER_USE_GUARD": "test", "IGR_BROWSER_USE_CONFIG_SHA256": "hash"}), \
                 mock.patch.object(study, "validate_config", return_value=config), \
                 mock.patch.object(study, "sha", return_value="hash"), \
                 mock.patch.object(study, "read_key", return_value="SYNTHETIC"), \
                 mock.patch.object(study, "CallBudget", return_value=budget), \
                 mock.patch.object(study, "read_observation", return_value=observation()):
                with self.assertRaisesRegex(study.Stop, "pilot slot failed"):
                    await study.execute_study("unused")
            self.assertEqual(run.await_count, 1)
            saved = json.loads((output / "a-r1-baseline.json").read_text())
            self.assertEqual(saved["outcome"], "timeout")
            self.assertEqual(saved["total_cost_usd"], 0)
            self.assertFalse((output / "b-r1-block.json").exists())


if __name__ == "__main__":
    unittest.main()
