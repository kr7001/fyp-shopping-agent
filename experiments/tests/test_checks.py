"""The checks that decide which runs count and what they did.

Each one was added after a measurement went wrong without it (LESSONS.md 3, 9 and 15), so
each is tested on the fault it exists to find and on a case it must leave alone.
"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401
import compare_cells  # noqa: E402
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
