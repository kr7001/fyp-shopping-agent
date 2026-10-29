"""Synthetic study only: no existing result files, browser, model or API calls."""
import contextlib
import copy
import csv
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths
import matched_briefing_analysis as analysis


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class MatchedBriefingAnalysis(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.tasks = self.root / "tasks.json"
        self.protocol = self.root / "protocol.json"
        self.manifest = self.root / "study.manifest"
        self.sheet = self.root / "blind.csv"
        self.patcher = mock.patch.object(paths, "TASKS", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        tasks = [{"id": task, "query": f"How many buyable size M listings? {task} {{base}}/search",
                  "gated": True, "expect": {"kind": "count", "value": 3}} for task in analysis.TASKS]
        self.tasks.write_text(json.dumps({"base_url": "http://localhost:7770", "tasks": tasks}))
        schedule = [{"slot": n + 1, "arm": arm, "task": task, "repeat": repeat}
                    for n, (task, repeat, arm) in enumerate(
                        (task, repeat, arm) for task in analysis.TASKS for repeat in (1, 2) for arm in analysis.ARMS)]
        self.config = {"study_id": "matched-briefing-2026-10-29", "model": "synthetic/model",
                       "tasks_file": "tasks.json", "tasks": list(analysis.TASKS), "repeats": [1, 2],
                       "arms": {arm: {"payload_arm": value} for arm, value in analysis.ARMS.items()},
                       "schedule": schedule, "require": {"max_steps": 300, "clock_s": 1800},
                       "provider_routing": {"synthetic/model": {"order": ["fake"], "allow_fallbacks": False}}}
        self.protocol.write_text(json.dumps(self.config))
        # The guarded launcher's real header lines (manifest_header in the command config).
        lines = ["start 2026-10-29T22:00:00 usage 0 cap 10",
                 "study matched-briefing-2026-10-29 exploratory already-observed Quenby mechanism audit; no pooling with primary tests",
                 "conditions commit 0000000 browser synthetic; frozen executor and model parser; separate matched factual briefing",
                 "WATCHDOG USD10 new study cap; USD1.25 inflight reserve; preserve USD20 key credit; no automatic retries"]
        self.folders = []
        for slot in schedule:
            folder = self.root / f"batch-{slot['slot']}"
            folder.mkdir()
            self.folders.append(folder)
            arm, task, repeat = (slot[k] for k in ("arm", "task", "repeat"))
            identity = {"study_id": self.config["study_id"], "protocol_sha256": analysis.digest(self.protocol),
                        "wrapper_id": "matched-briefing-v1", "condition": arm, "slot_id": slot["slot"],
                        "arm": analysis.ARMS[arm]}
            original = next(t["query"] for t in tasks if t["id"] == task).format(base="http://localhost:7770")
            page = {"listings": [{"url": "http://localhost:7770/a.html", "price": 1}],
                    "reader": "rendered", "next_page": False, "total": 1, "count": 1}
            briefing = {"query": original, "query_sha256": sha(original), "original_query": original,
                        "original_query_sha256": sha(original), "preamble": "Same factual briefing",
                        "preamble_sha256": sha("Same factual briefing"), "page": page,
                        "page_sha256": sha(json.dumps(page, sort_keys=True, separators=(",", ":"))),
                        "pre_read_elapsed_s": 2, "pre_read_cached": True, "query_build_elapsed_s": 1}
            final = "3 buyable listings. " + "Supporting explanation. " * 30
            token = {"prompt": 20, "completion": 10, "total": 30, "calls": 1}
            cost = 0.11 if arm == "full-block" else 0.10
            record = {**identity, "briefing": briefing, "query": original, "cost_usd": cost,
                      "elapsed_s": 4, "model": "synthetic/model", "scaffold": "openjiuwen", "shop": "gated",
                      "probe": "viewport", "max_steps": 300, "clock_s": 1800,
                      "provider_routing": self.config["provider_routing"]["synthetic/model"],
                      "result": {"ok": True, "final": final, "error": None},
                      "tokens": token, "trace": {"tool_calls_total": 0, "actions": 0, "tokens": token}}
            row = {**identity, "briefing": briefing, "task": task, "repeat": repeat, "cost_usd": cost,
                   "answer": final[:300], "verdict": "correct", "elapsed_s": 4}
            if arm == "full-block":
                record.update(agent_cost_usd=.1, parse_cost_usd=.01, parse_tokens=token, parse_provider="fake")
                record["tokens"] = {"prompt": 40, "completion": 20, "total": 60}
                row.update(parse_cost_usd=.01, parse_tokens=token, parse_provider="fake", box={"query": None})
            else:
                for item in (row, record):
                    item.update(parse_cost_usd=0, parse_tokens={"prompt": 0, "completion": 0, "total": 0, "calls": 0},
                                parse_provider=None)
            payload = {**identity, "arm": analysis.ARMS[arm], "box": arm == "full-block", "box_exhaust": False,
                       "parser": "model" if arm == "full-block" else None, "repeats": 1, "repeat_start": repeat,
                       "tasks_file": "tasks.json", "model": "synthetic/model", "max_steps": 300, "clock_s": 1800,
                       "briefing_page_reader": "rendered", "rows": [row], "provider_routing": {
                           "agent": self.config["provider_routing"]["synthetic/model"],
                           "parser": self.config["provider_routing"]["synthetic/model"] if arm == "full-block" else None}}
            (folder / "suite.json").write_text(json.dumps(payload))
            (folder / f"{task}-{repeat}.json").write_text(json.dumps(record))
            (folder / f"{task}-{repeat}.log").write_text(
                "2026-10-29 22:00:00 | start\nCompletionUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30) "
                "cost=0.1, is_byok=False, provider='fake'\n2026-10-29 22:00:04 | end\n")
            lines.append(f"batch|{folder}|--condition {arm} --slot-id {slot['slot']} --only {task} --repeat-start {repeat} --repeats 1")
        lines.append("end 2026-10-29T22:10:00 usage 1.68")
        self.manifest.write_text("\n".join(lines) + "\n")

    def load(self, partial=False):
        return analysis.load_study(self.protocol, self.manifest, partial)

    def edit_json(self, path, edit):
        obj = json.loads(path.read_text())
        edit(obj)
        path.write_text(json.dumps(obj))

    def record_path(self, index=0):
        return next(p for p in self.folders[index].glob("*.json") if p.name != "suite.json")

    def fill(self, verdict="correct"):
        with self.sheet.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["hand_verdict"] = verdict
        self.write_rows(rows)
        return rows

    def write_rows(self, rows):
        with self.sheet.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=analysis.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_operational_check_never_calls_scorer_or_displays_answers(self):
        with mock.patch.object(analysis.score, "score_run", side_effect=AssertionError("scorer called")):
            study = self.load()
            summary = analysis.check_summary(study)
        self.assertEqual(summary["recorded_slots"], 16)
        self.assertAlmostEqual(summary["charges_all_attempts"]["cost_usd"], 1.68)
        text = json.dumps(summary)
        for forbidden in ("Supporting", "verdict", "correct", "shipped"):
            self.assertNotIn(forbidden, text)

    def test_sheet_full_answers_random_codes_and_no_regeneration(self):
        with mock.patch.object(analysis.score, "score_run", side_effect=AssertionError("scorer called")):
            self.assertEqual(analysis.write_sheet(self.load(), self.sheet), 16)
        with self.sheet.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(list(rows[0]), list(analysis.COLUMNS))
        self.assertGreater(len(rows[0]["answer"]), 300)
        self.assertEqual(len({r["code"] for r in rows}), 16)
        self.assertTrue(all(not r["hand_verdict"] for r in rows))
        with self.assertRaisesRegex(analysis.Invalid, "regenerate"):
            analysis.write_sheet(self.load(), self.sheet)

    def test_incomplete_hand_refused_before_key_or_source_load(self):
        analysis.write_sheet(self.load(), self.sheet)
        with mock.patch.object(analysis, "load_study", side_effect=AssertionError("raw records read")):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(analysis.main([str(self.manifest), "--protocol", str(self.protocol),
                                               "--hand", str(self.sheet)]), 2)

    def test_completed_review_binds_original_fields_and_source(self):
        study = self.load()
        analysis.write_sheet(study, self.sheet)
        rows = self.fill()
        self.assertEqual(len(analysis.bind_review(study, self.sheet, analysis.completed_sheet(self.sheet))), 16)
        for field in ("answer", "question", "key"):
            changed = copy.deepcopy(rows)
            changed[0][field] += " changed"
            self.write_rows(changed)
            with self.assertRaisesRegex(analysis.Invalid, "original full answer changed"):
                analysis.bind_review(study, self.sheet, analysis.completed_sheet(self.sheet))
        self.write_rows(rows)
        self.edit_json(self.record_path(), lambda record: record.update(elapsed_s=5))
        with self.assertRaisesRegex(analysis.Invalid, "raw source changed"):
            analysis.bind_review(self.load(), self.sheet, analysis.completed_sheet(self.sheet))

    def test_missing_duplicate_and_out_of_schedule_manifest_refused(self):
        original = self.manifest.read_text()
        lines = original.splitlines()
        self.manifest.write_text("\n".join(lines[:-2] + lines[-1:]))
        with self.assertRaisesRegex(analysis.Invalid, "all 16"):
            self.load()
        self.assertEqual(len(self.load(partial=True)["runs"]), 15)
        first = next(i for i, line in enumerate(lines) if line.startswith("batch|"))
        lines[first], lines[first + 1] = lines[first + 1], lines[first]
        self.manifest.write_text("\n".join(lines))
        with self.assertRaisesRegex(analysis.Invalid, "schedule"):
            self.load()
        lines = original.splitlines()
        lines[first + 1] = lines[first]
        self.manifest.write_text("\n".join(lines))
        with self.assertRaisesRegex(analysis.Invalid, "duplicate"):
            self.load()

    def test_launcher_study_header_required_once_and_for_this_study(self):
        original = self.manifest.read_text().splitlines()
        study = next(i for i, line in enumerate(original) if line.startswith("study "))
        for label, lines in (
                ("missing", original[:study] + original[study + 1:]),
                ("duplicate", original[:study + 1] + original[study:]),
                ("foreign", original[:study] + ["study another-study-2026-10-29 synthetic"] + original[study + 1:])):
            with self.subTest(label):
                self.manifest.write_text("\n".join(lines) + "\n")
                with self.assertRaisesRegex(analysis.Invalid, "study header"):
                    self.load()
        self.manifest.write_text("\n".join(original + ["study matched-briefing-2026-10-29 again"]) + "\n")
        with self.assertRaisesRegex(analysis.Invalid, "study header"):
            self.load()

    def test_foreign_identity_arm_and_missing_cost_metrics_refused(self):
        path = self.record_path()
        original = path.read_text()
        faults = [("cost_usd", None, "cost_usd"), ("trace", {}, "trace"),
                  ("study_id", "foreign", "identity"), ("model", "another", "model")]
        for field, value, message in faults:
            with self.subTest(field=field):
                path.write_text(original)
                self.edit_json(path, lambda record: record.update({field: value}))
                with self.assertRaisesRegex(analysis.Invalid, message):
                    self.load()
        path.write_text(original)
        self.edit_json(self.folders[0] / "suite.json", lambda payload: payload.update(arm="none"))
        with self.assertRaisesRegex(analysis.Invalid, "arm"):
            self.load()

    def test_wrong_protocol_routing_fails_even_if_run_agrees(self):
        wrong = {"order": ["unexpected"], "allow_fallbacks": True}
        self.edit_json(self.folders[0] / "suite.json", lambda p: p["provider_routing"].update(agent=wrong))
        self.edit_json(self.record_path(), lambda r: r.update(provider_routing=wrong))
        with self.assertRaisesRegex(analysis.Invalid, "routing differs from protocol"):
            self.load()

    def test_missing_raw_charge_cannot_be_zero(self):
        log = self.record_path().with_suffix(".log")
        log.write_text(log.read_text().replace("cost=0.1, is_byok=False, ", ""))
        with self.assertRaisesRegex(analysis.Invalid, "provider charges"):
            self.load()

    def test_briefing_digest_and_equal_facts_are_enforced(self):
        self.edit_json(self.folders[1] / "suite.json", lambda p: p["rows"][0]["briefing"].update(preamble="changed"))
        with self.assertRaisesRegex(analysis.Invalid, "digest differs"):
            self.load()
        changed = "changed but honestly hashed"
        for path in (self.folders[1] / "suite.json", self.record_path(1)):
            self.edit_json(path, lambda p: (p["rows"][0] if "rows" in p else p)["briefing"].update(
                preamble=changed, preamble_sha256=sha(changed)))
        with self.assertRaisesRegex(analysis.Invalid, "paired briefing facts differ"):
            self.load()

    def test_original_technical_rule_retains_clock_and_steps(self):
        path = self.record_path()
        for error in ("task_timeout: exceeded 1800s", "max_iterations_reached"):
            self.edit_json(path, lambda r: r["result"].update(ok=False, final="", error=error))
            self.assertNotEqual(self.load()["runs"][0]["outcome"], analysis.voids.VOID)
        self.edit_json(path, lambda r: r["result"].update(ok=False, final="", error="Error code: 429"))
        study = self.load()
        self.assertEqual(study["runs"][0]["outcome"], analysis.voids.VOID)
        summary = analysis.check_summary(study)
        self.assertEqual(summary["technical_voids"], [{"slot": 1, "reason": "provider error"}])
        self.assertAlmostEqual(summary["charges_all_attempts"]["cost_usd"], 1.68)
        self.assertEqual(analysis.write_sheet(study, self.sheet), 15)

    def test_post_review_descriptive_pairs_keep_human_and_automatic_separate(self):
        study = self.load()
        analysis.write_sheet(study, self.sheet)
        self.fill("not correct")
        hand = analysis.bind_review(study, self.sheet, analysis.completed_sheet(self.sheet))
        measured = {"opened": 2, "elapsed_s": 4, "answer_matches_suite": True,
                    "answer": "3 buyable listings.", "ok": True, "skus": ["a", "b"], "selections": []}
        with mock.patch.object(analysis.verify_cells, "ground_truth", return_value={}), \
                mock.patch.object(analysis.verify_cells, "fixture_for", return_value=self.tasks), \
                mock.patch.object(analysis.verify_cells, "market_urls", return_value=[]), \
                mock.patch.object(analysis.verify_cells, "verify_run", return_value=measured), \
                mock.patch.object(analysis.claim, "answer_check", return_value={"full-block": None}):
            result = analysis.analyse(study, hand)
        self.assertEqual(len(result["paired_by_task_repeat"]), 8)
        self.assertEqual(len(result["human_automatic_disagreements"]), 16)
        self.assertNotIn("shipped", json.dumps(result))
        self.assertNotIn("p_value", json.dumps(result))
        count = result["per_task_counts"][analysis.TASKS[0]]["full-block"]
        self.assertEqual((count["human_correct"], count["automatic_correct"]), (0, 2))

    def test_real_trace_and_scorer_readers_on_synthetic_fixture(self):
        fixture = self.root / "fixture.json"
        fixture.write_text(json.dumps({"_instance": {"id": "synthetic"}, "families": [
            {"parent_sku": name, "seller": name.upper(), "variants": [
                {"option": "M", "qty": 1, "price": 10}, {"option": "XS", "qty": 1, "price": 8}]}
            for name in ("a", "b", "c")]}))
        self.edit_json(self.tasks, lambda spec: spec.update(fixture=str(fixture), _instance={"id": "synthetic"}))
        for folder in self.folders:
            record = next(p for p in folder.glob("*.json") if p.name != "suite.json")
            log = record.with_suffix(".log")
            messages = [{"role": "assistant", "content": "", "tool_calls": [
                {"id": "call-a", "function": {"name": "browser_navigate", "arguments": json.dumps({"url": "http://localhost:7770/a.html"})}}]},
                {"role": "tool", "tool_call_id": "call-a", "content": "Page URL: http://localhost:7770/a.html"}]
            event = "2026-10-29 22:00:01 | x | y | INFO | " + json.dumps({"event_id": "e1", "messages": messages})
            log.write_text(log.read_text().replace("2026-10-29 22:00:04", event + "\n2026-10-29 22:00:04"))
        study = self.load()
        analysis.write_sheet(study, self.sheet)
        self.fill()
        hand = analysis.bind_review(study, self.sheet, analysis.completed_sheet(self.sheet))
        result = analysis.analyse(study, hand)
        pair = result["paired_by_task_repeat"][0]
        for arm in analysis.ARMS:
            self.assertEqual(pair["arms"][arm]["opened"], 1)
            self.assertEqual(pair["arms"][arm]["automatic_verdict"], "correct")
        self.assertAlmostEqual(pair["paired_differences_full_block_minus_matched"]["cost_usd"], .01)
        self.assertEqual(result["human_automatic_disagreements"], [])

    def test_closed_full_block_kept_as_non_success_with_known_parser_cost(self):
        record = self.record_path()
        record.with_suffix(".log").unlink()
        record.unlink()
        def close_slot(payload):
            row = payload["rows"][0]
            row.update(verdict="asked", cost_usd=.01, elapsed_s=0, log=None,
                       box={"asked": True, "query": None})
            row["briefing"].update(query=None, query_sha256=None)
        self.edit_json(self.folders[0] / "suite.json", close_slot)
        study = self.load()
        self.assertEqual(study["runs"][0]["outcome"], analysis.voids.CLOSED)
        self.assertEqual(study["runs"][0]["agent_cost_usd"], 0)
        self.assertEqual(analysis.write_sheet(study, self.sheet), 15)
        self.fill()
        hand = analysis.bind_review(study, self.sheet, analysis.completed_sheet(self.sheet))
        measured = {"opened": 2, "elapsed_s": 4, "answer_matches_suite": True,
                    "answer": "3 buyable listings.", "ok": True, "skus": ["a", "b"], "selections": []}
        with mock.patch.object(analysis.verify_cells, "ground_truth", return_value={}), \
                mock.patch.object(analysis.verify_cells, "fixture_for", return_value=self.tasks), \
                mock.patch.object(analysis.verify_cells, "market_urls", return_value=[]), \
                mock.patch.object(analysis.verify_cells, "verify_run", return_value=measured), \
                mock.patch.object(analysis.claim, "answer_check", return_value={"full-block": None}):
            result = analysis.analyse(study, hand)
        counts = result["per_task_counts"][analysis.TASKS[0]]["full-block"]
        self.assertEqual((counts["scheduled"], counts["closed"], counts["human_correct"]), (2, 1, 1))
        self.assertAlmostEqual(result["charges_all_attempts"]["cost_usd"], 1.58)

    def test_closed_row_with_surviving_log_never_gets_zero_agent_charge(self):
        self.record_path().unlink()
        def close_slot(payload):
            row = payload["rows"][0]
            row.update(verdict="asked", cost_usd=.01, elapsed_s=0, log=None,
                       box={"asked": True, "query": None})
            row["briefing"].update(query=None, query_sha256=None)
        self.edit_json(self.folders[0] / "suite.json", close_slot)
        with self.assertRaisesRegex(analysis.Invalid, "technical void.*missing run record"):
            self.load()

    def test_closed_row_with_executor_clock_never_gets_zero_agent_charge(self):
        record = self.record_path()
        record.with_suffix(".log").unlink()
        record.unlink()
        def close_slot(payload):
            row = payload["rows"][0]
            row.update(verdict="refused", cost_usd=.01, elapsed_s=12, log=None,
                       box={"refuse": "synthetic", "query": None})
            row["briefing"].update(query=None, query_sha256=None)
        self.edit_json(self.folders[0] / "suite.json", close_slot)
        with self.assertRaisesRegex(analysis.Invalid, "technical void.*missing run record"):
            self.load()

    def test_identified_parser_only_failure_keeps_known_cost_but_not_unknown_cost(self):
        record = self.record_path()
        record.with_suffix(".log").unlink()
        record.unlink()
        def parser_failure(payload):
            payload["rows"][0].update(verdict="void", cost_usd=.01, elapsed_s=0, log=None,
                box={"parse": {"fallback_reason": "the model call failed: synthetic provider error"}})
        self.edit_json(self.folders[0] / "suite.json", parser_failure)
        study = self.load()
        self.assertEqual(study["runs"][0]["outcome"], analysis.voids.VOID)
        self.assertEqual(study["runs"][0]["agent_cost_usd"], 0)
        self.assertAlmostEqual(analysis.check_summary(study)["charges_all_attempts"]["cost_usd"], 1.58)
        self.edit_json(self.folders[0] / "suite.json", lambda p: p["rows"][0].update(parse_cost_usd=None))
        with self.assertRaisesRegex(analysis.Invalid, "technical void.*parse_cost_usd"):
            self.load()


if __name__ == "__main__":
    unittest.main()
