"""Free checks for tools/run_times.py, the wall-clock run times the report's threats table quotes.

Written 5 November 2026 with the tool. Each check has a test where it must fire on a planted
fault and one where it must stay quiet, on trial lists and run records written here. The last
class reads the committed trial list and run records and pins every figure the table quotes.
"""
import decimal
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/run_times.py"
spec = importlib.util.spec_from_file_location("run_times", MODULE)
run_times = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_times)

D = decimal.Decimal
OPEN = "open everything (product)"


def trial(arm, task, repeat=1):
    return {"batch": "B-" + re.sub(r"\W+", "-", arm), "task": task, "repeat": repeat, "arm": arm}


def study(trials, arms=None, h2=None):
    """A study as the trial list holds one: its arms in order, its trials, and H2's questions."""
    arms = arms or list(dict.fromkeys(t["arm"] for t in trials))
    out = {"study": "Synthetic", "arms": {arm: {} for arm in arms}, "trials": trials}
    if h2 is not None:
        out["h2"] = {"questions": h2}
    return out


def write(results, t, record):
    """A run record where the tool looks for it, as JSON or as the raw text given."""
    folder = results / t["batch"]
    folder.mkdir(exist_ok=True)
    text = record if isinstance(record, str) else json.dumps(record)
    (folder / f"{t['task']}-{t['repeat']}.json").write_text(text)


def times(s, seconds):
    """The study's rows, every trial on a gated question given the next time in `seconds`."""
    with tempfile.TemporaryDirectory() as tmp:
        for t, value in zip(s["trials"], seconds):
            write(Path(tmp), t, {"elapsed_s": value})
        return run_times.study_times(s, Path(tmp))


def row(out, arm):
    return next(r for r in out["rows"] if r["arm"] == arm)


class GatedQuestions(unittest.TestCase):
    def test_a_question_open_everything_never_ran_is_left_out(self):
        s = study([trial(OPEN, "q1"), trial("shipped", "q1"), trial("shipped", "headline")])
        out = times(s, [600, 100, 5000])
        self.assertEqual(out["gated"], ["q1"])
        self.assertEqual((row(out, "shipped")["questions"], row(out, "shipped")["trials"],
                          row(out, "shipped")["median_s"]), (1, 1, 100))

    def test_quiet_on_every_question_open_everything_ran(self):
        s = study([trial(OPEN, "q1"), trial(OPEN, "q2"), trial("shipped", "q1"), trial("shipped", "q2")])
        out = times(s, [600, 700, 100, 300])
        self.assertEqual(out["gated"], ["q1", "q2"])
        self.assertEqual((row(out, "shipped")["trials"], row(out, "shipped")["median_s"]), (2, 200))

    def test_stops_without_an_open_everything_arm(self):
        with self.assertRaises(ValueError):
            times(study([trial("shipped", "q1")]), [100])

    def test_stops_with_two_open_everything_arms(self):
        with self.assertRaises(ValueError):
            times(study([trial("open everything", "q1"), trial(OPEN, "q1")]), [100, 200])

    def test_quiet_on_either_name_of_the_open_everything_arm(self):
        for name in ("open everything", OPEN):
            with self.subTest(arm=name):
                self.assertEqual(times(study([trial(name, "q1")]), [100])["gated"], ["q1"])

    def test_stops_when_h2s_questions_differ(self):
        with self.assertRaises(ValueError):
            times(study([trial(OPEN, "q1")], h2=["q1", "q2"]), [100])

    def test_quiet_when_h2s_questions_are_the_same(self):
        out = times(study([trial(OPEN, "q2"), trial(OPEN, "q1")], h2=["q1", "q2"]), [100, 200])
        self.assertTrue(out["checked_against_h2"])
        self.assertIn("the same as H2's", run_times.render([out], Path("trials.json")))

    def test_says_so_when_there_are_no_h2_questions_to_check(self):
        out = times(study([trial(OPEN, "q1")]), [100])
        self.assertFalse(out["checked_against_h2"])
        self.assertIn("not checked", run_times.render([out], Path("trials.json")))

    def test_stops_on_a_trial_of_an_arm_the_study_does_not_list(self):
        s = study([trial(OPEN, "q1"), trial("shipped", "q1")], arms=[OPEN])
        with self.assertRaises(ValueError):
            times(s, [100, 200])


class Records(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.results = Path(self.tmp.name)
        self.trials = [trial(OPEN, "q1"), trial(OPEN, "q2"), trial(OPEN, "q3")]
        self.study = study(self.trials)

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, last):
        """The first two trials timed at 100 s and 300 s, the third given `last` as its record,
        or no record when `last` is None."""
        write(self.results, self.trials[0], {"elapsed_s": 100})
        write(self.results, self.trials[1], {"elapsed_s": 300.0})
        if last is not None:
            write(self.results, self.trials[2], last)
        trials = self.results / "trials.json"
        trials.write_text(json.dumps({"studies": [self.study]}))
        return run_times.run(trials, self.results)

    def assert_named(self, last, why):
        text, status = self.run_with(last)
        self.assertEqual(status, 1)
        self.assertIn("NO TIME, left out: B-open-everything-product-/q3-1", text)
        self.assertIn(why, text)
        out = run_times.study_times(self.study, self.results)
        self.assertEqual([m["task"] for m in out["missing"]], ["q3"])
        self.assertEqual((row(out, OPEN)["trials"], row(out, OPEN)["median_s"]), (2, 200))

    def test_a_missing_record_is_named_and_left_out(self):
        self.assert_named(None, "no record at")

    def test_a_record_without_elapsed_s_is_named(self):
        self.assert_named({"cost_usd": 0.1}, "has no elapsed_s")

    def test_a_null_time_is_named(self):
        self.assert_named({"elapsed_s": None}, "has no elapsed_s")

    def test_a_time_that_is_no_positive_number_is_named(self):
        for value in (0, 0.0, -4.2, "61.1", True, [61.1]):
            with self.subTest(elapsed_s=value):
                self.assert_named({"elapsed_s": value}, "not a positive number of seconds")

    def test_an_unreadable_record_is_named(self):
        self.assert_named('{"elapsed_s": 61.1', "cannot be read")

    def test_a_record_that_is_not_an_object_is_named(self):
        self.assert_named([61.1], "has no elapsed_s")

    def test_quiet_when_every_record_has_a_time(self):
        text, status = self.run_with({"elapsed_s": 61.1})
        self.assertEqual(status, 0)
        self.assertNotIn("NO TIME", text)
        self.assertIn("Every trial on the gated questions has a record with a positive elapsed_s.", text)


class Medians(unittest.TestCase):
    def test_an_even_count_averages_the_two_middle_times_exactly(self):
        # Quenby's shipped arm: its middle pair, 362.3 s and 387.6 s, has a float mean of
        # 374.95000000000005 and an exact mean of 374.95.
        out = times(study([trial(OPEN, "q1", r) for r in (1, 2, 3, 4)]), [362.3, 387.6, 100.1, 900.2])
        self.assertEqual((row(out, OPEN)["median_s"], row(out, OPEN)["median_min"]), (D("374.95"), D("6.2")))

    def test_minutes_round_half_up(self):
        # A tie: 15 s is 0.25 minutes exactly, 0.3 rounded half up and 0.2 rounded half to even.
        # No stored median sits on a tie, so this one is made here, alone and as a study's median.
        self.assertEqual(run_times.minutes(D("15")), D("0.3"))
        out = times(study([trial(OPEN, "q1", r) for r in (1, 2)]), [10, 20])
        self.assertEqual((row(out, OPEN)["median_s"], row(out, OPEN)["median_min"]), (D("15"), D("0.3")))
        # 189 s is 3.15 minutes exactly, which a float formats as 3.1.
        self.assertEqual(run_times.minutes(D("189.0")), D("3.2"))

    def test_minutes_below_the_half_round_down(self):
        self.assertEqual(run_times.minutes(D("188.9")), D("3.1"))
        self.assertEqual(run_times.minutes(D("374.95")), D("6.2"))

    def test_an_arm_with_no_trial_on_a_gated_question_shows_a_dash(self):
        out = times(study([trial(OPEN, "q1"), trial("shipped", "other")]), [100, 200])
        self.assertEqual((row(out, "shipped")["questions"], row(out, "shipped")["trials"],
                          row(out, "shipped")["median_s"]), (0, 0, None))
        line = next(l for l in run_times.render([out], Path("t.json")).splitlines() if "shipped" in l)
        self.assertEqual(line.split()[1:], ["0", "0", "-", "-"])

    def test_open_everything_first_then_the_files_order(self):
        arms = ["shipped", "the block (model)", OPEN, "the block (rules)"]
        out = times(study([trial(arm, "q1") for arm in arms], arms=arms), [1, 2, 3, 4])
        self.assertEqual([r["arm"] for r in out["rows"]], [OPEN, "shipped", "the block (model)", "the block (rules)"])


# What the docstring must not name: files that are not in the public repository.
PRIVATE = ("notes/", "private/", "report/", ".log", "analysis.json", "sheet", ".env", "PARKED",
           "WORKING-NOTES", "/Users/", "/tmp/")
NAMED_PATH = re.compile(r"\b(?:experiments|tools|docs|env)/[\w./-]+\.(?:py|json|md|csv)\b")


def private_names(text):
    return [marker for marker in PRIVATE if marker in text]


def missing_paths(text):
    return [p for p in NAMED_PATH.findall(text) if not (ROOT / p).exists()]


class Docstring(unittest.TestCase):
    def test_the_check_catches_a_private_file(self):
        self.assertEqual(private_names("as notes/replication-prep/x.md and claim.analysis.json say"),
                         ["notes/", "analysis.json"])

    def test_the_docstring_names_no_private_file(self):
        self.assertEqual(private_names(run_times.__doc__), [])

    def test_the_check_catches_a_path_that_does_not_exist(self):
        self.assertEqual(missing_paths("see experiments/artifacts/nowhere.json"),
                         ["experiments/artifacts/nowhere.json"])

    def test_every_path_the_docstring_names_exists(self):
        self.assertEqual(sorted(NAMED_PATH.findall(run_times.__doc__)),
                         ["experiments/artifacts/script-fetch-audit-4-nov.json",
                          "experiments/runners/run_browser_task.py", "tools/run_times.py"])
        self.assertEqual(missing_paths(run_times.__doc__), [])


# Every figure of the report's threats table: arm, gated questions it ran, trials, median minutes.
EXPECTED = {
    "Claim 1, Ashcombe, Claude Haiku 4.5": [
        ("open everything", 5, 15, "3.4"), ("shipped", 5, 15, "0.9"), ("the block (menu)", 5, 15, "1.9"),
        ("the block (buyable)", 2, 6, "1.0"), ("the block without its stop rule", 3, 9, "2.7")],
    "Claim 1, Ashcombe, DeepSeek V4 Flash": [
        ("open everything", 5, 15, "3.6"), ("shipped", 5, 15, "1.7"), ("the block (menu)", 5, 15, "2.0"),
        ("the block (buyable)", 2, 6, "1.2"), ("the block without its stop rule", 3, 9, "3.5")],
    "Claim 2, Wexcombe, DeepSeek V4 Flash": [
        ("open everything (product)", 8, 24, "11.1"), ("shipped", 8, 24, "3.5"),
        ("the block (model)", 8, 24, "2.3"), ("the block (rules)", 8, 24, "2.2")],
    "Quenby replication, DeepSeek V4 Flash": [
        ("open everything (product)", 8, 16, "11.2"), ("shipped", 6, 12, "6.2"),
        ("the block (model)", 8, 16, "2.8")],
}


class StoredRuns(unittest.TestCase):
    """The committed trial list and run records, as the report quotes them (5 November 2026)."""

    @classmethod
    def setUpClass(cls):
        listed = json.loads(run_times.TRIALS.read_text())["studies"]
        cls.studies = [run_times.study_times(s, run_times.paths.RESULTS) for s in listed]

    def test_every_figure_the_threats_table_quotes(self):
        got = {s["study"]: [(r["arm"], r["questions"], r["trials"], str(r["median_min"])) for r in s["rows"]]
               for s in self.studies}
        self.assertEqual(got, EXPECTED)

    def test_every_gated_set_is_h2s(self):
        self.assertEqual([s["checked_against_h2"] for s in self.studies], [True] * 4)

    def test_no_trial_on_a_gated_question_is_without_a_time(self):
        self.assertEqual([s["missing"] for s in self.studies], [[]] * 4)
        text, status = run_times.run(run_times.TRIALS, run_times.paths.RESULTS)
        self.assertEqual(status, 0)
        self.assertNotIn("NO TIME", text)

    def test_quenby_shipped_sits_just_under_the_rounding_line(self):
        # 374.95 s is 6.249 minutes: 0.05 s more would round to 6.3.
        quenby = self.studies[3]
        self.assertEqual(row(quenby, "shipped")["median_s"], D("374.95"))


if __name__ == "__main__":
    unittest.main()
