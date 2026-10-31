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


class PilotIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_failed_slot_is_saved_and_stops_before_next_trial(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            config = {"stage": "pilot", "questions": [question("a"), question("b")], "repeats": [1],
                      "environment_file": "unused", "ledger_path": "unused", "output_dir": str(output)}
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
