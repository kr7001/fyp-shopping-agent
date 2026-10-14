"""The checks that decide which runs count and what they did.

Each one was added after a measurement went wrong without it (LESSONS.md 3, 9 and 15), so
each is tested on the fault it exists to find and on a case it must leave alone.
"""
import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import compare_cells  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402

PILOT = paths.RESULTS / "20261014T084322"
V2 = paths.TASKS / "tasks_apparel_v2.json"


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
    """Verifier finding, 14 Oct 2026, at 7d2ec2e: the report listed asked rows but said
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

    def test_a_batch_without_box_counts_prints_none(self):
        # The pilot ran under box v1, whose payload has no counts; its report is as before.
        without = json.loads(json.dumps(self.suite))
        del without["summary"]["box"]
        text, result = self.report(without)
        self.assertNotIn("box             ", text)
        self.assertEqual(result["problems"], [])


if __name__ == "__main__":
    unittest.main()
