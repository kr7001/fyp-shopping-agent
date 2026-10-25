"""`experiments/analysis/reader_agreement.py`: the share of rows two hand readers read alike and
Cohen's kappa between them (docs/content/claim2-protocol.md, "Measures and scoring").

Every file here is made up in a temporary folder. Nothing reads the real sheet, its key or any
analysis file. Each refusal is shown firing on a planted fault, and the same files without the
fault are shown to pass (LESSONS 31). Nothing here reaches a model.
"""
import contextlib
import csv
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (also puts the code folders on sys.path)

import reader_agreement as ra  # noqa: E402

SCRIPT = paths.EXPERIMENTS / "analysis" / "reader_agreement.py"

C, N, U = "correct", "not correct", "unscorable"
SECRET = "SECRET-ANSWER-TEXT"


class Case(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.dir = pathlib.Path(self._dir.name)

    def files(self, student: dict, second: dict, listed=None, extra_sheet_rows=2):
        """A sheet, a second reader's file and a codes file. The sheet has cells with newlines
        and a secret in question, key and answer, and rows beyond the listed ones with no verdict."""
        listed = list(student) if listed is None else listed
        sheet, other, codes = self.dir / "s.csv", self.dir / "o.csv", self.dir / "s.second-reader.json"
        with sheet.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["code", "question", "key", "answer", "hand_verdict", "note"])
            for code, verdict in student.items():
                writer.writerow([code, f"which?\n{SECRET}", f"key\n{SECRET}", f"line one\nline two {SECRET}",
                                 verdict, "a note,\nwith a comma"])
            for i in range(extra_sheet_rows):
                writer.writerow([f"X{i}", "q", "k", "a", "", ""])
        with other.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["code", "verdict", "note"])
            for code, verdict in second.items():
                writer.writerow([code, verdict, ""])
        codes.write_text(json.dumps({"_about": "x", "rows": len(listed), "codes": listed}))
        return sheet, other, codes

    def run_main(self, student, second, listed=None):
        sheet, other, codes = self.files(student, second, listed)
        return ra.main(["--sheet", str(sheet), "--second", str(other), "--codes", str(codes)])

    def refusal(self, student, second, listed=None) -> str:
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            self.run_main(student, second, listed)
        return str(caught.exception)


class Figures(Case):
    def test_perfect_agreement_is_kappa_one(self):
        both = {"A1": C, "A2": C, "A3": C, "A4": N, "A5": N, "A6": U}
        result = ra.agreement(both, dict(both))
        self.assertEqual((result["n"], result["alike"], result["share_alike"]), (6, 6, 1.0))
        self.assertEqual(result["kappa"], 1.0)
        self.assertEqual(result["differ"], [])

    def test_kappa_worked_by_hand(self):
        # Student on the rows, second reader on the columns, n = 10:
        #              correct  not correct  unscorable
        #   correct       4          1            0       row total 5
        #   not correct   1          3            0       row total 4
        #   unscorable    0          0            1       row total 1
        # column totals   5          4            1
        # alike 8, so po = 0.8. pe = (5*5 + 4*4 + 1*1) / 100 = 0.42. kappa = 0.38 / 0.58 = 19 / 29.
        pairs = [(C, C)] * 4 + [(C, N), (N, C)] + [(N, N)] * 3 + [(U, U)]
        student = {f"A{i}": a for i, (a, _) in enumerate(pairs)}
        second = {f"A{i}": b for i, (_, b) in enumerate(pairs)}
        result = ra.agreement(student, second)
        self.assertEqual((result["n"], result["alike"]), (10, 8))
        self.assertAlmostEqual(result["share_alike"], 0.8)
        self.assertAlmostEqual(result["kappa"], 19 / 29)
        self.assertEqual(result["table"][C], {C: 4, N: 1, U: 0})
        self.assertEqual(result["table"][N], {C: 1, N: 3, U: 0})
        self.assertEqual([d["code"] for d in result["differ"]], ["A4", "A5"])
        self.assertEqual(result["differ"][0], {"code": "A4", "student": C, "second": N})

    def test_kappa_is_below_one_where_the_readers_split_on_a_single_category_pair(self):
        # Not a quiet-by-accident case: one reader all correct, the other mixed, gives kappa 0, not undefined.
        student = {f"A{i}": C for i in range(4)}
        second = {"A0": C, "A1": C, "A2": N, "A3": N}
        result = ra.agreement(student, second)
        self.assertEqual(result["kappa"], 0.0)

    def test_kappa_is_undefined_where_chance_agreement_is_one(self):
        same = {f"A{i}": C for i in range(5)}
        result = ra.agreement(same, dict(same))
        self.assertIsNone(result["kappa"])
        self.assertEqual(result["share_alike"], 1.0)
        self.assertIn("undefined", ra.render(result))
        self.assertNotIn("undefined", ra.render(ra.agreement({"A": C, "B": N}, {"A": C, "B": N})))


class Refusals(Case):
    OK = {"A1": C, "A2": N, "A3": U}

    def test_files_without_a_fault_pass(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.run_main(dict(self.OK), dict(self.OK))     # the other tests plant one fault each

    def test_cells_are_cleaned_before_they_are_compared(self):
        loose = {"A1": "  Correct ", "A2": "NOT   correct", "A3": "Unscorable\n"}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.run_main(loose, dict(self.OK))
        self.assertIn("read alike: 3 of 3", out.getvalue())

    def test_a_listed_code_missing_from_the_second_file_is_refused(self):
        message = self.refusal(dict(self.OK), {"A1": C, "A2": N})
        self.assertIn("A3", message)
        self.assertIn("missing", message)

    def test_a_listed_code_missing_from_the_sheet_is_refused(self):
        message = self.refusal({"A1": C, "A2": N}, dict(self.OK), listed=["A1", "A2", "A3"])
        self.assertIn("s.csv", message)
        self.assertIn("A3", message)

    def test_a_blank_verdict_is_refused_in_either_file(self):
        self.assertIn("A2 has no verdict", self.refusal({"A1": C, "A2": "  ", "A3": U}, dict(self.OK)))
        self.assertIn("A2 has no verdict", self.refusal(dict(self.OK), {"A1": C, "A2": "", "A3": U}))

    def test_a_code_outside_the_list_in_the_second_file_is_refused(self):
        message = self.refusal(dict(self.OK), {**self.OK, "ZZ9": C})
        self.assertIn("ZZ9", message)
        self.assertIn("not on the list", message)

    def test_rows_of_the_sheet_outside_the_list_are_left_alone(self):
        # The sheet holds every row of the market. Its X0 and X1 have no verdict and are not asked for.
        sheet, other, codes = self.files(dict(self.OK), dict(self.OK), extra_sheet_rows=5)
        ra.read_verdicts(sheet, "hand_verdict", list(self.OK), strict_codes=False)

    def test_a_verdict_that_is_not_one_of_the_three_is_refused_by_code(self):
        for bad in ("incorrect", "yes", "correct?", "not_correct"):
            message = self.refusal({**self.OK, "A2": bad}, dict(self.OK))
            self.assertIn("A2", message)
            self.assertIn("not one of", message)
            self.refusal(dict(self.OK), {**self.OK, "A3": bad})

    def test_a_code_twice_is_refused(self):
        sheet, other, codes = self.files(dict(self.OK), dict(self.OK))
        with other.open("a", newline="") as handle:
            csv.writer(handle).writerow(["A1", N, ""])
        with self.assertRaises(SystemExit) as caught:
            ra.read_verdicts(other, "verdict", list(self.OK), strict_codes=True)
        self.assertIn("A1 is there twice", str(caught.exception))

    def test_a_codes_file_with_no_codes_is_refused(self):
        path = self.dir / "empty.json"
        path.write_text(json.dumps({"rows": 40}))
        with self.assertRaises(SystemExit):
            ra.load_codes(path)
        path.write_text(json.dumps({"rows": 3, "codes": ["A1", "A2"]}))
        with self.assertRaises(SystemExit):
            ra.load_codes(path)
        path.write_text(json.dumps({"rows": ["A1", "A2"]}))        # a list under "rows" is read too
        self.assertEqual(ra.load_codes(path), ["A1", "A2"])


class Command(Case):
    def command(self, *extra):
        sheet, other, codes = self.files({"A1": C, "A2": N, "A3": U, "A4": C}, {"A1": C, "A2": C, "A3": U, "A4": C})
        return subprocess.run([sys.executable, str(SCRIPT), "--sheet", str(sheet), "--second", str(other),
                               "--codes", str(codes), *extra], capture_output=True, text=True)

    def test_the_text_output_names_codes_and_never_prints_the_sheet_text(self):
        done = self.command()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("read alike: 3 of 4 (75.0%)", done.stdout)
        self.assertIn("A2: student not correct, second correct", done.stdout)
        self.assertNotIn(SECRET, done.stdout + done.stderr)
        self.assertNotIn("which?", done.stdout)

    def test_json_holds_the_same_figures(self):
        done = self.command("--json")
        result = json.loads(done.stdout)
        self.assertEqual((result["n"], result["alike"]), (4, 3))
        self.assertEqual(result["differ"], [{"code": "A2", "student": N, "second": C}])
        # Row totals 2, 1, 1 and column totals 3, 0, 1 give pe = 7 / 16, po = 3 / 4, kappa = 5 / 9.
        self.assertAlmostEqual(result["kappa"], 5 / 9)
        self.assertNotIn(SECRET, done.stdout)

    def test_a_refusal_exits_non_zero_with_a_message_and_prints_nothing_else(self):
        sheet, other, codes = self.files({"A1": C, "A2": N}, {"A1": C})
        done = subprocess.run([sys.executable, str(SCRIPT), "--sheet", str(sheet),
                               "--second", str(other), "--codes", str(codes)], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("A2", done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertNotIn(SECRET, done.stderr)


if __name__ == "__main__":
    unittest.main()
