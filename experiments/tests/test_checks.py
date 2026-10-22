"""The checks that decide which runs count and what they did.

Each one was added after a measurement went wrong without it (LESSONS.md 3, 9 and 15), so
each is tested on the fault it exists to find and on a case it must leave alone.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import cell_facts  # noqa: E402
import compare_cells  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402

sys.path.insert(0, str(paths.REPO / "env"))
import generate_apparel as apparel  # noqa: E402
import generate_apparel_v2_tasks as v2  # noqa: E402

PILOT = paths.RESULTS / "20261014T084322"
V2 = paths.TASKS / "tasks_apparel_v2.json"
FIXTURE = paths.FIXTURES / "scaled_apparel.json"


class SuspendedRun(unittest.TestCase):
    """LESSONS 15: a log silent for more than 60 seconds means the laptop slept. Void."""

    def test_a_long_silence_is_found(self):
        log = "2026-10-08 03:50:00 | step\n2026-10-08 04:39:22 | step\n"
        self.assertEqual(verify_cells.longest_silence(log), 2962.0)
        self.assertGreater(verify_cells.longest_silence(log), verify_cells.SUSPENDED_AFTER_S)

    def test_a_steady_log_passes(self):
        log = "".join(f"2026-10-08 03:5{m}:{s:02d} | step\n" for m in range(3) for s in (0, 30))
        self.assertLessEqual(verify_cells.longest_silence(log), verify_cells.SUSPENDED_AFTER_S)


class Selections(unittest.TestCase):
    """LESSONS 3: a size chosen inside a batch call is a selection too."""

    def batch(self, steps, as_string=False) -> list[dict]:
        payload = {"steps": json.dumps(steps) if as_string else steps}
        return [{"tool": "browser_batch_interact", "target": "",
                 "batch": trace_stats.batch_ops(json.dumps(payload))}]

    def test_a_size_chosen_in_a_batch_is_counted(self):
        steps = [{"op": "select_option", "option_text": "M"}, {"op": "click", "selector": "#buy"}]
        self.assertEqual(trace_stats.selections(self.batch(steps)), ["M"])

    def test_steps_sent_as_a_string_are_read(self):
        steps = [{"op": "select_visible_text", "choose_text": "L"}]
        self.assertEqual(trace_stats.selections(self.batch(steps, as_string=True)), ["L"])

    def test_navigation_is_not_a_selection(self):
        steps = [{"op": "navigate", "url": "http://localhost:7770/tee.html"}, {"op": "click", "ref": "e12"}]
        self.assertEqual(trace_stats.selections(self.batch(steps)), [])


class Repeats(unittest.TestCase):
    """LESSONS 9: three repeats that are the same run are one piece of evidence."""

    def test_identical_repeats_collapse(self):
        runs = [{"task": "q", "tokens": (900, 40), "answer": "5"},
                {"task": "q", "tokens": (900, 40), "answer": "5"},
                {"task": "q", "tokens": (950, 41), "answer": "5"}]
        self.assertEqual(len(compare_cells.distinct(runs)), 2)

    def test_the_same_answer_on_different_questions_is_kept(self):
        runs = [{"task": "q1", "tokens": (900, 40), "answer": "5"},
                {"task": "q2", "tokens": (900, 40), "answer": "5"}]
        self.assertEqual(len(compare_cells.distinct(runs)), 2)


class StratifiedTest(unittest.TestCase):
    """LESSONS 8: compare within each question, then combine."""

    def test_one_question_is_fishers_test(self):
        for table in [(3, 3, 0, 3), (11, 15, 4, 15), (1, 5, 4, 5), (2, 3, 2, 3)]:
            sa, na, sb, nb = table
            with self.subTest(table=table):
                self.assertAlmostEqual(compare_cells.stratified_exact([table]),
                                       fisher_exact([[sa, na - sa], [sb, nb - sb]])[1], places=9)

    def test_no_difference_anywhere_gives_one(self):
        self.assertAlmostEqual(compare_cells.stratified_exact([(2, 3, 2, 3), (0, 3, 0, 3)]), 1.0)

    def test_a_consistent_difference_is_detected(self):
        # Five questions, three runs each, one arm always right and the other always wrong.
        self.assertLess(compare_cells.stratified_exact([(3, 3, 0, 3)] * 5), 0.001)


class ReadingKey(unittest.TestCase):
    """A batch scored under the scripted user's second reading is re-scored under it too,
    otherwise every such run would be reported as a stored-against-re-scored mismatch."""

    def setUp(self):
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        self.task = next(t for t in spec["tasks"] if t["id"] == "apparel-count-stocked")
        self.readings = score.readings_for(paths.TASKS / "tasks_apparel.json")

    def verdict(self, answer: str, row: dict, suite: dict) -> str:
        return verify_cells.rescore(self.task, answer, True, row, suite, self.readings)["verdict"]

    def test_the_rows_reading_uses_the_sidecar_key(self):
        self.assertEqual(self.verdict("5 listings", {"reading": "buyable"}, {}), "correct")
        self.assertEqual(self.verdict("10 listings", {"reading": "buyable"}, {}), "wrong")

    def test_without_a_reading_the_tasks_own_key_stands(self):
        self.assertEqual(self.verdict("10 listings", {}, {}), "correct")
        self.assertEqual(self.verdict("5 listings", {}, {}), "wrong")

    def test_a_reading_the_box_took_scores_under_its_own_key(self):
        # 20 Oct 2026: a row the box read as buyable carries that reading, so the re-score
        # uses the buyable key even under a batch run with --reading menu.
        self.assertEqual(self.verdict("5 listings", {"reading": "buyable", "reading_by": "box"},
                                      {"reading": "menu"}), "correct")
        self.assertEqual(self.verdict("5 listings", {"reading": "menu", "reading_by": "user"},
                                      {"reading": "menu"}), "wrong")
        self.assertEqual(self.verdict("5 listings", {"reading": None, "reading_by": None},
                                      {"reading": "menu"}), "wrong")

    def test_the_batch_reading_applies_when_the_row_has_none(self):
        self.assertEqual(self.verdict("5 listings", {}, {"reading": "buyable"}), "correct")
        # The menu reading is the task's own key.
        self.assertEqual(self.verdict("10 listings", {"reading": "menu"}, {}), "correct")


REFUSAL = "The shop does not show delivery time, so the question cannot be answered from it."
ASK = "What price counts as cheap? Give a figure."
POEM = "Laces loop and soles that sing,\nshoes carry me through everything."
SOFTEST = "No listing says how soft the tee is, so nobody can be named."


def scratch_batch(folder: str) -> pathlib.Path:
    """The pilot batch's two runs plus one row of each kind box v2 adds, in a scratch
    folder rather than under experiments/results.

    The pilot's records and suite rows are copied as they are. Its logs stay on the laptop
    (gitignored), so each record gets an empty stand-in log: the figures read from a log
    are then zero, which is fine here, since these tests are about how the report counts
    rows, not what the pilot opened. The batch is pointed at `tasks_apparel_v2.json`,
    which carries the pilot's questions unchanged and adds the keyless ones. Added by
    hand, in the shape the suite writes: a refused row and an asked row through
    `suite.asked_row`, and two runs with no answer key, one the box bypassed and one its
    fallback planned, each with a record and a stand-in log.
    """
    batch = pathlib.Path(folder) / "scratch"
    batch.mkdir()
    payload = json.loads((PILOT / "suite.json").read_text())
    payload["tasks_file"] = V2.name
    for record in PILOT.glob("*.json"):
        if record.name != "suite.json":
            shutil.copy(record, batch / record.name)
            stand_in_log(batch, record.stem)
    tasks = {t["id"]: t for t in json.loads(V2.read_text())["tasks"]}

    def box_record(**over) -> dict:
        return {"asked": False, "ask": None, "refuse": None, "bypassed": False,
                "fallback": False, "query": "the text the agent got", **over}

    rows = payload["rows"]
    rows.append(suite.asked_row(tasks["apparel-delivery"], 1,
                                box_record(refuse=REFUSAL, query=None)))
    rows.append(suite.asked_row(tasks["apparel-cheap-no-figure"], 1,
                                box_record(asked=True, ask=ASK, query=None)))
    for task_id, answer, over in (("bypass-poem", POEM, {"bypassed": True}),
                                  ("apparel-softest", SOFTEST, {"fallback": True})):
        tag = f"{task_id}-1"
        (batch / f"{tag}.json").write_text(json.dumps({
            "model": payload["model"], "query": tasks[task_id]["query"], "elapsed_s": 5.0,
            "cost_usd": 0.01, "error": None, "result": {"ok": True, "final": answer},
            "trace": {"tool_calls_total": 1, "actions": 0, "observations": 1, "selections": []},
            "log": f"{tag}.log", "shop": "gated", "probe": "viewport", "scaffold": "openjiuwen"}))
        stand_in_log(batch, tag)
        rows.append({"task": task_id, "family": tasks[task_id]["family"],
                     "gated": tasks[task_id]["gated"], "repeat": 1, "verdict": "unscored",
                     "why": "no answer key for this question", "answer": answer[:300],
                     "tool_calls": 1, "actions": 0, "observations": 1, "cost_usd": 0.01,
                     "elapsed_s": 5.0, "error": None, "log": f"{tag}.log",
                     "box": box_record(**over), "reading": None})
    payload["summary"]["box"] = suite.box_counts(rows)
    (batch / "suite.json").write_text(json.dumps(payload))
    return batch


def stand_in_log(batch: pathlib.Path, tag: str) -> None:
    (batch / f"{tag}.log").write_text("")
    (batch / "caches" / tag).mkdir(parents=True)    # the per-run cache the report checks for


class BoxRowsInTheReport(unittest.TestCase):
    """Verifier finding, 14 Oct 2026, at 39f15e9: the report listed asked rows but said
    nothing of refused ones, and showed a run with no answer key (score.py v2's "none"
    kind, verdict "unscored") as 0 of 1 correct. Each case is on the scratch batch above,
    with the pilot's two scored runs beside the new rows, so what must stay as it was is
    checked in the same output."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.batch = scratch_batch(cls.tmp.name)
        cls.suite, cls.runs = verify_cells.verify_batch(cls.batch)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def report(self, suite_payload: dict | None = None, answers: bool = False) -> tuple[str, dict]:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = verify_cells.report(self.batch, suite_payload or self.suite, self.runs, answers)
        return out.getvalue(), result

    def test_the_scratch_batch_is_what_it_says(self):
        self.assertEqual(sorted(r["task"] for r in self.runs),
                         ["apparel-cheapest-target", "apparel-count-buyable", "apparel-softest",
                          "bypass-poem"])
        self.assertEqual(sorted(row["verdict"] for row in self.suite["rows"]),
                         ["asked", "correct", "correct", "refused", "unscored", "unscored"])
        self.assertEqual({r["task"]: r["rescored"] for r in self.runs},
                         {"apparel-cheapest-target": "correct", "apparel-count-buyable": "correct",
                          "apparel-softest": "unscored", "bypass-poem": "unscored"})
        self.assertNotIn(paths.RESULTS, self.batch.parents)

    def test_refused_rows_are_listed_like_asked_rows(self):
        text, _ = self.report()
        self.assertIn("refused         1 rows: the box refused and no agent ran\n"
                      f"  apparel-delivery-1: {REFUSAL}\n", text)
        self.assertIn("asked           1 rows: the box asked the user and no agent ran\n"
                      f"  apparel-cheap-no-figure-1: {ASK}\n", text)

    def test_unscored_runs_are_counted_apart_and_never_in_a_ratio(self):
        text, _ = self.report()
        self.assertIn("unscored        2 runs: no answer key, read by hand with --answers: "
                      "apparel-softest-1, bypass-poem-1\n", text)
        # The two keyless runs are control rows, so the old report said "0 of 2" here.
        self.assertIn("control correct stored 0 of 0, re-scored 0 of 0\n", text)
        self.assertIn("gated correct   stored 2 of 2, re-scored 2 of 2\n", text)
        per_question = {line.split()[0]: line for line in text.splitlines()
                        if line.startswith("  ") and line.split()[0] in
                        ("bypass-poem", "apparel-softest", "apparel-count-buyable")}
        self.assertIn("unscored", per_question["bypass-poem"])
        self.assertIn("unscored", per_question["apparel-softest"])
        self.assertNotIn("0/1", per_question["bypass-poem"])
        self.assertNotIn("0/1", per_question["apparel-softest"])
        self.assertIn("1/1", per_question["apparel-count-buyable"])
        self.assertNotIn("unscored", per_question["apparel-count-buyable"])
        # With --answers the keyless answers are printed in full, like every other.
        text, _ = self.report(answers=True)
        self.assertIn("[bypass-poem-1] unscored (no answer key for this question)", text)
        self.assertIn("  " + POEM.replace("\n", "\n  "), text)

    def test_box_counts_come_from_the_payload_and_are_checked_against_the_rows(self):
        text, result = self.report()
        self.assertIn("box             asked 1, refused 1, bypassed 1, fallback 1\n", text)
        self.assertEqual(result["problems"], [])
        # A payload whose counts are not what its rows say is a problem, not a figure.
        planted = json.loads(json.dumps(self.suite))
        planted["summary"]["box"]["asked"] = 3
        text, result = self.report(planted)
        self.assertIn("box             asked 3, refused 1, bypassed 1, fallback 1   (the rows say "
                      "asked 1, refused 1, bypassed 1, fallback 1)\n", text)
        self.assertEqual(len(result["problems"]), 1)
        self.assertIn("box counts", result["problems"][0])

    def test_the_parse_of_a_slot_the_box_closed_is_in_the_cost(self):
        # Under the model parser an ask or a refusal ran no agent but paid for its parse,
        # which only its row holds, so `make verify` and section G missed it (verifier
        # finding, 22 October 2026). Planted: `closed_parse_charges` returning nothing, the
        # charged figures below came out as the records' alone.
        text, result = self.report()
        records = sum(r["cost"] or 0 for r in self.runs)
        self.assertAlmostEqual(result["cost"], records)
        line = next(l for l in text.splitlines() if l.startswith("cost "))
        self.assertNotIn("slots the box closed", line)
        charged = json.loads(json.dumps(self.suite))
        closed = [row for row in charged["rows"] if row["verdict"] in ("asked", "refused")]
        closed[0]["parse_cost_usd"], closed[1]["parse_cost_usd"] = 0.003, None
        text, result = self.report(charged)
        self.assertAlmostEqual(result["cost"], records + 0.003)
        self.assertIn("; it holds the parse of 2 slots the box closed, $0.0030, 1 of them unknown\n", text)
        # Section G reads each batch's charges the same way.
        self.assertAlmostEqual(cell_facts.charges(self.batch),
                               sum(json.loads(p.read_text()).get("cost_usd") or 0
                                   for p in self.batch.glob("apparel-*.json")))
        with tempfile.TemporaryDirectory() as tmp:
            copy = pathlib.Path(tmp) / "scratch"
            shutil.copytree(self.batch, copy)
            (copy / "suite.json").write_text(json.dumps(charged))
            self.assertAlmostEqual(cell_facts.charges(copy), cell_facts.charges(self.batch) + 0.003)

    def test_a_batch_without_box_counts_prints_none(self):
        # The pilot ran under box v1, whose payload has no counts; its report is as before.
        without = json.loads(json.dumps(self.suite))
        del without["summary"]["box"]
        text, result = self.report(without)
        self.assertNotIn("box             ", text)
        self.assertEqual(result["problems"], [])

    def test_a_run_with_no_floor_rule_is_a_problem_not_a_crash(self):
        # A gated question no rule covers gets no floor, and the report says so by task
        # rather than raising, which it did until 14 Oct 2026 on four v2 questions.
        runs = json.loads(json.dumps(self.runs))
        runs[0].update(task="argmax-question", floor=None, met_floor=False)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = verify_cells.report(self.batch, self.suite, runs, False)
        self.assertEqual(result["problems"], ["argmax-question-1: no floor rule for argmax-question"])
        self.assertIn("  argmax-question              -  0/1", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify_cells.report(self.batch, self.suite, self.runs, False)["problems"], [])


class VerifyRunFields(unittest.TestCase):
    """What `verify_run` reads since 20 Oct 2026: the market's listings from the row's page
    record (so a category page is never counted, and a product page outside the market is
    named), the kind of key, how many sellers a ranked key expects, and the sidecar reading
    the run was scored under."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.batch = scratch_batch(cls.tmp.name)
        cls.payload = json.loads((cls.batch / "suite.json").read_text())
        cls.tasks = {t["id"]: t for t in json.loads(V2.read_text())["tasks"]}
        cls.truth = verify_cells.ground_truth()
        cls.readings = score.readings_for(V2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def verify(self, task_id: str, stored: dict, suite_payload: dict, log_text: str) -> dict:
        record = self.batch / "apparel-cheapest-target-1.json"
        record.with_suffix(".log").write_text(log_text)
        return verify_cells.verify_run(record, self.tasks[task_id], self.truth, stored,
                                       suite_payload, self.readings)

    def test_opened_counts_the_markets_listings_and_names_the_rest(self):
        row = next(r for r in self.payload["rows"] if r["task"] == "apparel-cheapest-target")
        self.assertTrue(row["box"]["page"]["listings"])     # the pilot's rows carry the page
        log = "\n".join(f"Page URL: {url}" for url in (
            "http://localhost:7770/electronics.html", "http://localhost:7770/igr-app-03.html",
            "http://localhost:7770/igr-rvn-01.html"))
        run = self.verify("apparel-cheapest-target", row, self.payload, log)
        self.assertEqual((run["opened"], run["skus"], run["outside_market"], run["unknown_pages"]),
                         (1, ["igr-app-03"], ["igr-rvn-01"], []))
        self.assertEqual((run["key_kind"], run["ranked"], run["scored_under"]), ("contains", None, None))
        with contextlib.redirect_stdout(io.StringIO()):
            problems = verify_cells.report(self.batch, self.payload, [run], False)["problems"]
        self.assertIn("apparel-cheapest-target-1: opened product pages outside the market "
                      "['igr-rvn-01']", problems)
        # Without a page record the counter's own rule applies: the category page is still
        # not a listing, and the other market's product page counts as opened.
        plain = self.verify("apparel-cheapest-target", {k: v for k, v in row.items() if k != "box"},
                            {}, log)
        self.assertEqual((plain["opened"], plain["skus"], plain["outside_market"], plain["unknown_pages"]),
                         (2, ["igr-app-03", "igr-rvn-01"], [], ["igr-rvn-01"]))

    def test_the_key_a_run_was_scored_under(self):
        row = {"reading": "buyable"}
        self.assertEqual(self.verify("apparel-count-stocked", row, {}, "")["scored_under"], "buyable")
        self.assertEqual(self.verify("apparel-count-stocked", {}, {"reading": "buyable"}, "")["scored_under"],
                         "buyable")
        # The menu reading is the task's own key, and a task without a sidecar key is scored
        # on its own key under any reading.
        self.assertIsNone(self.verify("apparel-count-stocked", {}, {"reading": "menu"}, "")["scored_under"])
        self.assertIsNone(self.verify("apparel-cheapest-target", row, {}, "")["scored_under"])
        ranked = self.verify("apparel-top-3", {}, {}, "")
        self.assertEqual((ranked["key_kind"], ranked["ranked"]), ("ranked", 3))


class Rescore(unittest.TestCase):
    """`rescore.py` writes the scorer's version into the payload it rewrites (20 Oct 2026;
    until then a rescored batch kept the version of the scorer that first judged it), keeps
    the previous verdict beside the new one, and changes nothing else."""

    def test_a_rescore_writes_the_scorers_version_and_keeps_the_previous_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = scratch_batch(tmp)
            payload = json.loads((batch / "suite.json").read_text())
            # The fault scorer v3 fixed, planted: a keyless run that did not finish, stored
            # as failed by v2.
            record = json.loads((batch / "apparel-softest-1.json").read_text())
            record["result"]["ok"] = False
            (batch / "apparel-softest-1.json").write_text(json.dumps(record))
            next(r for r in payload["rows"] if r["task"] == "apparel-softest")["verdict"] = "failed"
            payload["scorer_version"] = 2
            # The pilot ran under the gate, which a rescore replays; the scratch batch's
            # stand-in logs are empty, so the gate would abstain every run. This test is
            # about the scorer, so the batch is rescored as one without a policy.
            payload["policy"] = "off"
            (batch / "suite.json").write_text(json.dumps(payload))
            run = subprocess.run([sys.executable, str(paths.EXPERIMENTS / "analysis" / "rescore.py"),
                                  str(batch), "--reason", "the test's reason"],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            after = json.loads((batch / "suite.json").read_text())
            self.assertEqual(after["scorer_version"], score.VERSION)
            row = next(r for r in after["rows"] if r["task"] == "apparel-softest")
            self.assertEqual((row["verdict"], row["previous_verdict"]), ("unscored", "failed"))
            self.assertEqual(after["rescored"][-1]["reason"], "the test's reason")
            self.assertEqual(after["rescored"][-1]["changed"],
                             [{"task": "apparel-softest", "repeat": 1, "from": "failed", "to": "unscored"}])
            others = {(r["task"], r["repeat"]): r["verdict"] for r in after["rows"]
                      if r["task"] != "apparel-softest"}
            self.assertEqual(others, {(r["task"], r["repeat"]): r["verdict"] for r in payload["rows"]
                                      if r["task"] != "apparel-softest"})
            self.assertNotIn(paths.RESULTS, batch.parents)


def steps_log(folder: str, name: str, steps: list[tuple[str, dict]]) -> pathlib.Path:
    """A log whose trace holds these tool calls in order, as `trace_stats.tool_steps` reads them."""
    messages = [{"role": "user", "content": "the task"}]
    for n, (tool, arguments) in enumerate(steps):
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{n}", "function": {"name": f"mcp_playwright-official_{tool}",
                                         "arguments": json.dumps(arguments)}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{n}", "content": "ok"})
    path = pathlib.Path(folder) / f"{name}.log"
    path.write_text(json.dumps({"event_id": "e1", "messages": messages}) + "\n")
    return path


V2_BATCHES = compare_cells.DEVELOPMENT["box v2 development, Thornwood, in-sample"]
HAVE_V2_LOGS = all(any((paths.RESULTS / batch).glob("*.log")) for batch in V2_BATCHES)


class ErrorKinds(unittest.TestCase):
    """Two kinds written 20 Oct 2026 from the box v2 batches: a ranked answer's sellers are
    each read for the two seller faults, not only the first; and a listing judged by a
    search for the word "disabled" alone, never reading its menu. Each fires on its fault
    and stays quiet otherwise, with the fixture's facts read from the fixture."""

    @classmethod
    def setUpClass(cls):
        cls.truth = verify_cells.ground_truth()
        cls.m_price = cell_facts.m_prices()
        cls.name = {sku: t["seller"] for sku, t in cls.truth.items()}
        buyable = {sku: t["buyable"]["M"] for sku, t in cls.truth.items() if "M" in t["buyable"]}
        cls.winner = min(buyable, key=buyable.get)
        cls.no_m = next(sku for sku, t in sorted(cls.truth.items()) if t["m"] is None)
        cls.hidden = next(sku for sku, t in sorted(cls.truth.items())
                          if t["m"] == "buyable" and abs(t["from"] - cls.m_price[sku]) > 0.01)

    def run_dict(self, answer: str, **over) -> dict:
        return {"task": "apparel-top-3", "repeat": 1, "rescored": "wrong", "covered": True,
                "answer": answer, "ok": True, "error": None, "skus": [], "key_kind": "ranked",
                "ranked": 3, **over}

    def test_every_ranked_seller_is_read(self):
        ranked = (f"1. {self.name[self.winner]} - ${self.m_price[self.winner]:.2f} "
                  f"2. {self.name[self.no_m]} - ${self.truth[self.no_m]['from']:.2f} "
                  f"3. {self.name[self.hidden]} - ${self.truth[self.hidden]['from']:.2f}")
        self.assertEqual(cell_facts.error_kinds(self.run_dict(ranked), self.truth, self.m_price),
                         [cell_facts.SELLER, cell_facts.REVEAL])
        # The fault, planted: read for the first seller only, the ranking is clean.
        self.assertIsNone(cell_facts.seller_kind(self.winner, [self.m_price[self.winner]],
                                                 self.truth, self.m_price))
        self.assertEqual(cell_facts.error_kinds(self.run_dict(ranked, key_kind="contains", ranked=None),
                                                self.truth, self.m_price), ["other"])
        # Quiet: the right sellers at their size M prices, and a seller narrated after the
        # ranking is not one of the ranked.
        right = (f"1. {self.name[self.winner]} - ${self.m_price[self.winner]:.2f} "
                 f"2. {self.name[self.hidden]} - ${self.m_price[self.hidden]:.2f}. "
                 f"I skipped {self.name[self.no_m]} at ${self.truth[self.no_m]['from']:.2f}.")
        self.assertEqual(cell_facts.error_kinds(self.run_dict(right, ranked=2), self.truth, self.m_price),
                         ["other"])
        self.assertEqual([sku for sku, _ in cell_facts.ranked_sellers(right, 2, self.truth)],
                         [self.winner, self.hidden])

    def test_a_listing_judged_by_a_search_for_disabled_alone(self):
        listing = lambda n: {"url": f"http://localhost:7770/igr-app-{n:02d}.html"}
        with tempfile.TemporaryDirectory() as tmp:
            fires = steps_log(tmp, "fires", [
                ("browser_navigate", listing(7)), ("browser_find", {"query": "disabled"}),
                ("browser_navigate", listing(8)), ("browser_snapshot", {}),
                ("browser_find", {"query": "disabled"}),
                ("browser_navigate", listing(9)), ("browser_find", {"text": "disabled"}),
                ("browser_take_screenshot", {})])
            self.assertEqual(cell_facts.menu_unread(fires), 2)
            quiet = steps_log(tmp, "quiet", [
                ("browser_navigate", listing(7)), ("browser_snapshot", {}),
                ("browser_navigate", listing(8)), ("browser_find", {"query": "Size"}),
                ("browser_navigate", {"url": "http://localhost:7770/catalogsearch/result/?q=T"}),
                ("browser_find", {"query": "disabled"})])
            self.assertEqual(cell_facts.menu_unread(quiet), 0)

    @unittest.skipUnless(HAVE_V2_LOGS, "the raw logs live on the laptop, not in git")
    def test_on_the_batches(self):
        results = paths.RESULTS
        self.assertEqual(cell_facts.menu_unread(results / "20261014T213118" / "apparel-count-buyable-2.log"), 12)
        self.assertEqual(cell_facts.menu_unread(results / "20261014T213118" / "apparel-count-buyable-1.log"), 0)
        development, truth = compare_cells.load(compare_cells.DEVELOPMENT)
        kinds = {f"{r['batch']}/{r['task']}-{r['repeat']}": cell_facts.error_kinds(r, truth, self.m_price)
                 for runs in development.values() for r in runs}
        self.assertEqual({k: v for k, v in kinds.items() if v},
                         {"20261014T213118/apparel-cheapest-target-1":
                              ["did not open what the answer needs", cell_facts.REVEAL],
                          "20261014T213118/apparel-count-buyable-2": [cell_facts.MENU_UNREAD],
                          "20261014T220116/apparel-top-3-1": [cell_facts.SELLER]})


class DevelopmentCell(unittest.TestCase):
    """The box v2 development cell (20 Oct 2026): three batches as one cell, in-sample, kept
    apart from the four claim-grade cells, and compared with cells 1 and 5 only on the
    questions those cells asked and only under the key fixed before the runs."""

    def test_in_sample_keeps_the_shared_questions_under_the_own_key(self):
        against = [{"task": "apparel-all-stocked"}, {"task": "apparel-count-stocked"}]
        runs = [{"task": "apparel-all-stocked", "scored_under": None},
                {"task": "apparel-all-stocked", "scored_under": "buyable"},
                {"task": "apparel-top-3", "scored_under": None},
                {"task": "apparel-count-stocked", "scored_under": None}]
        self.assertEqual(compare_cells.in_sample(runs, against), [runs[0], runs[3]])
        self.assertEqual(compare_cells.in_sample(runs, []), [])

    @unittest.skipUnless(HAVE_V2_LOGS, "the raw logs live on the laptop, not in git")
    def test_the_figures_against_cells_1_and_5(self):
        with contextlib.redirect_stdout(io.StringIO()):
            facts = cell_facts.facts(account=False)
        d = facts["development"]["box v2 development, Thornwood, in-sample"]
        self.assertEqual((d["batches"], d["runs"], len(d["questions"])), (V2_BATCHES, 26, 10))
        s = d["in_sample"]
        self.assertEqual((s["runs"], s["right"], s["opened"], s["median_opened"], round(s["cost"], 3)),
                         (15, 13, 14, 8, 0.258))
        tests = {(t["reading"], t["measure"], t["b"]): (t["text"], round(t["p_question"], 5))
                 for t in d["tests"]}
        self.assertEqual(tests[("menu", "correct", "1")], ("13 of 15 against 4 of 15", 0.00155))
        self.assertEqual(tests[("menu", "opened", "1")], ("14 of 15 against 3 of 15", 0.00034))
        self.assertEqual(tests[("menu", "correct", "5")], ("13 of 15 against 11 of 15", 0.63))
        self.assertEqual(tests[("menu", "opened", "5")], ("14 of 15 against 15 of 15", 1.0))
        self.assertEqual(d["check"]["wrong"], 3)
        self.assertEqual(d["check"]["wrong_refused"], [])
        # The one correct run refused saw its counterexample's menu in a find excerpt
        # only, so the sound reader cannot say the size is absent (20 Oct 2026; the run is
        # 20261014T222007 apparel-all-stocked-1, see test_box.BoxBatchesReplayed).
        self.assertEqual((d["check"]["other"], d["check"]["other_refused"]), (29, ["apparel-all-stocked-1"]))
        # The four cells are the four cells still, and the site's tests table is theirs alone.
        self.assertEqual([n.split()[0] for n in facts["names"]], ["1", "2", "3", "5"])
        self.assertEqual({t["a"] for t in facts["tests"]}, {"2", "3", "5"})


class OwnFloor(unittest.TestCase):
    """The coverage floor of each v2 question shape, written down in `verify_cells.own_floor`
    on 14 Oct 2026 (LESSONS 5) after the verifier found the four new shapes raised. Every
    expected figure here is recomputed from the fixture with the generator's own helpers,
    never typed, and each rule has a case where it must fire and one where it must stay
    quiet: the six v1 questions keep their floors, and a wrong set of listings is not
    covered even when it is the right size."""

    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(V2.read_text())
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.instance = cls.fixture["_instance"]
        cls.listings = cls.fixture["families"]
        cls.truth = verify_cells.ground_truth()
        cls.tasks = {t["id"]: t for t in cls.spec["tasks"]}

    def floor(self, task_id: str) -> verify_cells.Floor:
        return verify_cells.own_floor(self.tasks[task_id], self.truth)

    def sku(self, listing: dict) -> str:
        return listing["parent_sku"].lower()

    def advertised_at_or_below(self, price: float) -> frozenset[str]:
        return frozenset(self.sku(l) for l in self.listings if apparel.from_price(l) <= price)

    def test_the_truth_is_the_fixture_read_with_the_generators_helpers(self):
        for listing in self.listings:
            entry = self.truth[self.sku(listing)]
            self.assertEqual(entry["from"], apparel.from_price(listing))
            for size in apparel.SIZES:
                self.assertEqual(entry["sizes"].get(size), apparel.price_for(listing, size))
                self.assertEqual(entry["buyable"].get(size), apparel.buyable_price_for(listing, size))

    def test_the_six_v1_floors_are_unchanged(self):
        # 0, 8, 8, 1, 15, 15 on Thornwood, as every stored clothing batch was verified with.
        inst = self.instance
        expected = {"apparel-headline": 0, "apparel-target-price": inst["oracle_min_opens"],
                    "apparel-cheapest-target": inst["oracle_min_opens"], "apparel-all-stocked": 1,
                    "apparel-count-stocked": inst["listings"], "apparel-count-buyable": inst["listings"]}
        self.assertEqual({task_id: self.floor(task_id).count for task_id in expected}, expected)
        self.assertEqual(self.floor("apparel-count-buyable").all_of, frozenset(self.truth))
        self.assertEqual(self.floor("apparel-all-stocked").one_of,
                         frozenset(s for s, t in self.truth.items() if t["m"] is None))

    def test_cheapest_for_a_size_reads_the_size_from_the_question(self):
        for_m = self.floor("apparel-cheapest-target")
        self.assertEqual(for_m.all_of, self.advertised_at_or_below(self.instance["winner"]["price"]))
        self.assertEqual(for_m.count, self.instance["oracle_min_opens"])
        # Size XL: the XL winner's price, which `_instance` records as the largest size's,
        # and the listings advertised at or below it. Until 14 Oct 2026 this returned the
        # M floor, read from `_instance` rather than from the question.
        winner = min((apparel.buyable_price_for(l, "XL") for l in self.listings
                      if apparel.buyable_price_for(l, "XL") is not None))
        self.assertEqual(winner, self.instance["largest_size_winner"]["price"])
        for_xl = self.floor("apparel-cheapest-xl")
        self.assertEqual(for_xl.all_of, self.advertised_at_or_below(winner))
        self.assertEqual(for_xl.count, len(for_xl.all_of))
        self.assertNotEqual(for_xl.count, for_m.count)
        self.assertIn("igr-app-08", for_xl.all_of)      # Ivybridge, the XL winner

    def test_exists_with_a_witness_needs_the_witness_itself(self):
        witnesses = frozenset(self.sku(l) for l in v2.witnesses(self.listings, "M", v2.LIMIT_YES))
        floor = self.floor("apparel-exists-under-27")
        self.assertEqual((floor.count, floor.all_of, floor.one_of), (1, frozenset(), witnesses))
        self.assertEqual(len(witnesses), 1)
        witness = next(iter(witnesses))
        other = next(s for s in self.truth if s != witness)
        self.assertTrue(verify_cells.covered(floor, {witness}))
        self.assertFalse(verify_cells.covered(floor, {other}))          # one listing, not the one
        self.assertTrue(verify_cells.covered(floor, {other, witness}))

    def test_exists_without_a_witness_needs_every_listing_under_the_limit(self):
        self.assertEqual(v2.witnesses(self.listings, "M", v2.LIMIT_NO), [])
        under = frozenset(self.sku(l) for l in self.listings if apparel.from_price(l) < v2.LIMIT_NO)
        floor = self.floor("apparel-exists-under-25")
        self.assertEqual((floor.count, floor.all_of, floor.one_of), (len(under), under, frozenset()))
        self.assertGreater(floor.count, 0)
        self.assertNotIn("igr-app-14", under)    # Alderney, advertised above the limit
        self.assertTrue(verify_cells.covered(floor, set(under)))
        short = set(under) - {next(iter(under))}
        self.assertFalse(verify_cells.covered(floor, short | {"igr-app-14"}))  # right size, wrong set

    def test_top_k_needs_every_listing_at_or_below_the_kth_price(self):
        able = v2.buyable(self.listings, "M")
        kth = apparel.buyable_price_for(able[v2.TOP_K - 1], "M")
        floor = self.floor("apparel-top-3")
        self.assertEqual(floor.all_of, self.advertised_at_or_below(kth))
        self.assertEqual((floor.count, floor.one_of), (len(floor.all_of), frozenset()))
        self.assertGreater(floor.count, self.floor("apparel-cheapest-target").count)
        self.assertLess(floor.count, len(self.truth))

    def test_a_named_pair_needs_both_named_listings(self):
        low, high = v2.comparison_pair(self.listings, "M")
        pair = frozenset((self.sku(low), self.sku(high)))
        floor = self.floor("apparel-named-pair")
        self.assertEqual((floor.count, floor.all_of, floor.one_of), (2, pair, frozenset()))
        self.assertTrue(verify_cells.covered(floor, set(pair)))
        self.assertFalse(verify_cells.covered(floor, {self.sku(low), "igr-app-14"}))

    def test_a_shape_with_no_rule_gets_none_rather_than_raising(self):
        task = {**self.tasks["apparel-cheapest-target"], "id": "argmax-question",
                "query": "Go to {base}/catalogsearch/result/?q=Thornwood . Which Thornwood seller "
                         "is the most expensive for size M?"}
        floor = verify_cells.own_floor(task, self.truth)
        self.assertEqual((floor.count, floor.all_of, floor.one_of, floor.rule),
                         (None, frozenset(), frozenset(), "none"))
        self.assertFalse(verify_cells.covered(floor, set(self.truth)))

    def test_every_v2_task_has_a_floor_or_is_not_gated(self):
        for task in self.spec["tasks"]:
            with self.subTest(task=task["id"]):
                floor = verify_cells.own_floor(task, self.truth)
                if task["gated"]:
                    self.assertIsNotNone(floor.count)
                else:
                    self.assertEqual((floor.count, floor.rule), (0, "not gated"))

    def test_the_floor_table_prints_every_task(self):
        run = subprocess.run([sys.executable, str(paths.EXPERIMENTS / "analysis" / "verify_cells.py"),
                              "--floors", str(V2)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        for task in self.spec["tasks"]:
            self.assertIn(task["id"], run.stdout)
        self.assertIn("apparel-exists-under-27", run.stdout)


if __name__ == "__main__":
    unittest.main()
