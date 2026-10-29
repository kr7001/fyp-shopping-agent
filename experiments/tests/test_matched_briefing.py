"""Synthetic wrapper regressions: no browser, account, credential or model access."""
import argparse
import contextlib
import dataclasses
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths
import form
import matched_briefing as matched
import page
import primitives
import suite

BASE = "http://localhost:7770"
URL = BASE + "/catalogsearch/result/?q=Example"
QUESTION = "Go to {base}/catalogsearch/result/?q=Example . Which seller is cheapest for size M among listings that can actually supply it?"


def observed():
    items = [page.Listing(name, f"Example Tee - {name}", f"{BASE}/example-{i}.html", price)
             for i, (name, price) in enumerate((("Zed", 20), ("Ash", 10), ("Elm", 15)), 1)]
    return page.Page(URL, items, 3, False, (URL, URL + "&p=2"), "rendered")


def reply():
    return json.dumps({"quantifier": "argmin", "objective": "price", "population": "results",
                       "filters": [{"attribute": "size", "op": "=", "value": "M"},
                                   {"attribute": "availability", "op": "=", "value": "buyable"}],
                       "k": None, "negated": False, "reading": "buyable", "unknowns": [],
                       "ambiguities": [], "evidence": {}})


def metadata(condition="matched-briefing"):
    return {"study_id": matched.STUDY_ID, "protocol_id": matched.STUDY_ID,
            "protocol_sha256": "a" * 64, "wrapper_id": matched.WRAPPER_ID,
            "condition": condition, "slot_id": 1}


class PromptTests(unittest.TestCase):
    def test_only_question_page_and_fixed_facts(self):
        question = QUESTION.format(base=BASE)
        with mock.patch.object(form, "from_rules", side_effect=AssertionError("classifier")), \
                mock.patch.object(suite, "parser_call", side_effect=AssertionError("parser")):
            query = matched.factual_query(question, observed())
        self.assertTrue(query.startswith(question + "\n\n"))
        self.assertEqual(query.count(primitives.preamble(observed())), 1)
        self.assertTrue(query.endswith(primitives.LABEL_NOTE))
        self.assertLess(query.index("Ash, advertised"), query.index("Elm, advertised"))
        self.assertLess(query.index("Elm, advertised"), query.index("Zed, advertised"))
        for word in ("skip", "stop", "open every", "ascending", "plan:", "objective:",
                     "fewest", "threshold", "best so far"):
            self.assertNotIn(word, query[len(question):].lower())
        self.assertIn("lower bound", query)
        self.assertIn("does not show the new price", query)

    def test_incomplete_or_filtered_pages_refused(self):
        for changed in (dict(next_page=True), dict(reader="fetch"), dict(total=4),
                        dict(total=None), dict(scope="tee", of=4), dict(listings=[])):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                matched.factual_query("question", dataclasses.replace(observed(), **changed))

    def test_frozen_full_block_query_unchanged_and_one_parse(self):
        task = {"id": "t", "query": QUESTION, "expect": {"kind": "price", "value": 12}}
        spec = {"base_url": BASE}
        args = argparse.Namespace(box=True, box_exhaust=False, reading="own", parser="model",
                                  two_readings=[], page_reader="rendered", rate_plan="bound",
                                  targeting=False, exhaustive=False, confidence="off")
        with mock.patch.object(suite, "results_page", return_value=observed()):
            frozen, _ = suite.build_query(task, spec, args, call=lambda prompt: reply())
        session = matched.Session(metadata("full-block"))
        parser = mock.Mock(return_value=reply())
        before = (paths.EXPERIMENTS / "runners/suite.py").read_bytes()
        with mock.patch.object(page, "read", return_value=observed()), session.install():
            actual, _ = suite.build_query(task, spec, args, call=parser)
        self.assertEqual(actual.encode(), frozen.encode())
        parser.assert_called_once()
        self.assertIn(primitives.preamble(observed()), actual)
        self.assertEqual((paths.EXPERIMENTS / "runners/suite.py").read_bytes(), before)

    def test_first_read_time_is_counted_once(self):
        session = matched.Session(metadata())
        task = {"id": "t", "query": QUESTION}
        original_build, original_page_cache = suite.build_query, suite.PAGES
        with mock.patch.object(page, "read", return_value=observed()), \
                mock.patch.object(matched.time, "perf_counter", side_effect=[10, 11, 12, 15]), \
                session.install():
            suite.build_query(task, {"base_url": BASE}, argparse.Namespace())
            record = session.decorate({"elapsed_s": 2})
        self.assertEqual(record["briefing"]["pre_read_elapsed_s"], 1)
        self.assertEqual(record["briefing"]["query_build_elapsed_s"], 4)
        self.assertEqual(record["elapsed_with_briefing_s"], 7)
        self.assertIs(suite.build_query, original_build)
        self.assertIs(suite.PAGES, original_page_cache)


class InvocationTests(unittest.TestCase):
    def run_slot(self, condition="matched-briefing", dry=False, status="frozen", closed=False):
        owner = tempfile.TemporaryDirectory()
        self.addCleanup(owner.cleanup)
        root = pathlib.Path(owner.name)
        task = {"id": "test", "query": QUESTION, "family": "synthetic", "gated": True,
                "expect": {"kind": "price", "value": 12}, "secret_fixture_key": "MUST_NOT_REACH_EXECUTOR"}
        task_path = root / "synthetic.json"
        task_path.write_text(json.dumps({"base_url": BASE, "tasks": [task]}))
        protocol = root / "protocol.json"
        protocol.write_text(json.dumps({"study_id": matched.STUDY_ID, "status": status,
            "tasks_file": "synthetic.json", "schedule": [
                {"slot": 1, "arm": condition, "task": "test", "repeat": 1}]}))
        argv = ["--condition", condition, "--protocol", str(protocol), "--slot-id", "1",
                "--tasks", str(task_path), "--only", "test", "--repeat-start", "1",
                "--page-reader", "rendered"] + (["--dry-run"] if dry else [])
        results = root / "results"
        results.mkdir()
        commands = []

        def run_once(runtime_task, base, out_dir, tag, **kwargs):
            commands.append((runtime_task, kwargs))
            record = {"model": "fake/model", "elapsed_s": 2, "cost_usd": 0.1,
                      "log": tag + ".log", "result": {"ok": True, "final": "The price is $12."},
                      "trace": {"tokens": {"prompt": 7, "completion": 3}, "providers": {"fake": 1}}}
            (out_dir / (tag + ".json")).write_text(json.dumps(record))
            (out_dir / (tag + ".log")).write_text("synthetic log\n")
            return record

        # No code in this test can load a real key, model name from .env, account,
        # rendered browser or executor. One parser stub exercises accounting.
        with mock.patch.object(suite, "RESULTS", results), \
                mock.patch.object(suite, "run_once", run_once), \
                mock.patch.object(suite, "agent_model", return_value="fake/model"), \
                mock.patch.object(suite, "agent_code_identity", return_value={
                    "agent_core_commit": "b" * 40, "agent_core_patch": "c" * 40}), \
                mock.patch.object(suite.scoring, "keys_for", return_value=suite.scoring.Keys(
                    {"buyable": {"test": task["expect"]}}, [], [])), \
                mock.patch.object(page, "read", return_value=observed()) as reader, \
                mock.patch.object(suite.plan_probe, "load_key", return_value="synthetic-key") as key, \
                mock.patch.object(suite.provider_routing, "routing_for", return_value=(
                    {"order": ["fake"]} if closed else None)), \
                mock.patch.object(suite.parse_probe, "call_model", return_value=(
                    reply(), 0.01, {"prompt": 5, "completion": 5}, "fake"),
                    side_effect=RuntimeError("synthetic parse failure") if closed else None) as parse, \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            try:
                code = matched.main(argv)
            except SystemExit as exc:
                code = exc.code
        batches = list(results.glob("*/suite.json"))
        payload = json.loads(batches[0].read_text()) if batches else None
        record_path = batches[0].parent / "test-1.json" if batches else None
        record = json.loads(record_path.read_text()) if record_path and record_path.exists() else None
        return dict(code=code, payload=payload, record=record, commands=commands,
                    reader_calls=reader.call_count, parse_calls=parse.call_count,
                    key_calls=key.call_count, output=output.getvalue() + errors.getvalue(),
                    results=results)

    def test_baseline_actual_suite_validation_and_identity(self):
        result = self.run_slot()
        self.assertEqual(result["code"], 0, result["output"])
        payload, record = result["payload"], result["record"]
        self.assertEqual((payload["arm"], payload["box"], payload["parser"], payload["page_reader"]),
                         ("matched-briefing", False, None, None))
        self.assertEqual(payload["briefing_page_reader"], "rendered")
        self.assertEqual((result["parse_calls"], result["key_calls"], result["reader_calls"]), (0, 0, 1))
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(set(result["commands"][0][0]), {"id", "query"})
        for obj in (payload, payload["rows"][0], record):
            self.assertEqual(obj["study_id"], matched.STUDY_ID)
            self.assertEqual(obj["condition"], "matched-briefing")
            self.assertEqual(obj["slot_id"], 1)
        self.assertEqual(record["parse_tokens"]["calls"], 0)
        self.assertEqual(record["briefing"]["query_sha256"], matched.sha256(record["briefing"]["query"]))
        self.assertEqual(record["briefing"]["page_sha256"], matched.page_digest(record["briefing"]["page"]))
        self.assertEqual(payload["rows"][0]["briefing"], record["briefing"])
        self.assertIn("full results:", result["output"])

    def test_full_block_keeps_parser_charge_and_original_arm(self):
        result = self.run_slot("full-block")
        self.assertEqual(result["code"], 0, result["output"])
        self.assertEqual((result["parse_calls"], result["key_calls"], result["reader_calls"]), (1, 1, 1))
        payload, record = result["payload"], result["record"]
        self.assertEqual((payload["arm"], payload["box"], payload["parser"], payload["rate_plan"]),
                         ("box-model", True, "model", "bound"))
        self.assertEqual((record["agent_cost_usd"], record["parse_cost_usd"], record["cost_usd"]),
                         (0.1, 0.01, 0.11))
        self.assertEqual(record["parse_tokens"]["calls"], 1)
        # The guard scans only cost_usd in direct batch JSONs (not caches), then
        # parser-only rows without a log. The wrapper must introduce no cost file.
        scanned = sum(json.loads(p.read_text()).get("cost_usd", 0)
                      for p in result["results"].glob("*/*.json") if p.name != "suite.json")
        self.assertEqual(scanned, 0.11)

    def test_dry_runs_call_neither_parser_nor_executor(self):
        for condition in matched.ARMS:
            with self.subTest(condition=condition):
                result = self.run_slot(condition, dry=True, status="preparation")
                self.assertEqual(result["code"], 0, result["output"])
                self.assertEqual((result["parse_calls"], result["key_calls"], result["commands"]), (0, 0, []))
                self.assertIsNone(result["payload"])

    def test_unfrozen_protocol_refuses_before_model_or_reader(self):
        result = self.run_slot(status="preparation")
        self.assertEqual(result["code"], 2)
        self.assertEqual((result["parse_calls"], result["reader_calls"], result["commands"]), (0, 0, []))

    def test_no_executor_slot_still_records_actual_shop_and_probe(self):
        result = self.run_slot("full-block", closed=True)
        self.assertEqual(result["code"], 0, result["output"])
        self.assertEqual(result["commands"], [])
        self.assertIsNone(result["record"])
        self.assertEqual(result["payload"]["rows"][0]["verdict"], "void")
        for obj in (result["payload"], result["payload"]["rows"][0]):
            self.assertEqual((obj["shop"], obj["probe"]), ("gated", "viewport"))
            self.assertEqual(obj["study_id"], matched.STUDY_ID)


if __name__ == "__main__":
    unittest.main()
