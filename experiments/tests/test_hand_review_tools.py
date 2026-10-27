"""Synthetic-only checks for blind review persistence and CSV interoperability."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "experiments"))
import paths  # noqa: F401,E402
import claim  # noqa: E402
import hand_review as review  # noqa: E402


class ReviewTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = pathlib.Path(self.temp.name)
        self.rows = [{"code": "001abc", "question": 'Which "M", please?\nPrice?',
                      "key": '{"kind":"price","value":12.34}',
                      "answer": 'It costs $12.34.\nLiteral </script><img src=x>. Café.',
                      "hand_verdict": "", "note": ""}]

    def test_bom_quotes_newlines_unicode_and_leading_zero_survive(self):
        file = self.folder / "sheet.csv"
        file.write_text(review.csv_text(self.rows), encoding="utf-8-sig", newline="")
        self.assertEqual(review.read_sheet(file), self.rows)

    def test_import_preserves_evidence_and_allows_only_verdict_note(self):
        incoming = copy.deepcopy(self.rows)
        incoming[0].update(hand_verdict="correct", note='A note, with "quotes"\nand a newline')
        merged = review.merge_verdicts(self.rows, incoming)
        self.assertEqual(merged, incoming)
        for field in review.IMMUTABLE:
            bad = copy.deepcopy(incoming)
            bad[0][field] += "changed"
            with self.subTest(field=field), self.assertRaises(ValueError):
                review.merge_verdicts(self.rows, bad)

    def test_missing_duplicate_and_unknown_verdict_refused(self):
        file = self.folder / "sheet.csv"
        for rows in ([], self.rows * 2, [{**self.rows[0], "hand_verdict": "maybe"}]):
            file.write_text(review.csv_text(rows))
            with self.assertRaises(ValueError):
                review.read_sheet(file)
        with self.assertRaises(ValueError):
            review.merge_verdicts(self.rows, [])

    def test_old_partial_download_cannot_erase_completed_verdict(self):
        completed = [{**self.rows[0], "hand_verdict": "correct"}]
        with self.assertRaisesRegex(ValueError, "lose a completed verdict"):
            review.merge_verdicts(completed, self.rows)

    def test_incomplete_score_never_starts_subprocess(self):
        with patch.object(review.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "finish every row"):
                review.score(review.DEFAULT, self.rows)
            run.assert_not_called()

    def test_html_keeps_script_markup_inert_and_has_no_arm_key(self):
        html = review.make_html(self.rows, self.folder / "sheet.csv")
        self.assertNotIn('Literal </script><img', html)
        self.assertIn('Literal \\u003c/script>', html)
        self.assertIn("connect-src 'none'", html)
        payload = html.split("const payload = ", 1)[1].split(";\nconst columns", 1)[0]
        self.assertEqual(json.loads(payload)["rows"], self.rows)
        self.assertEqual(set(json.loads(payload)), {"rows", "filename", "identity", "rules"})

    def test_claim_accepts_excel_utf8_bom_without_changing_verdict(self):
        file = self.folder / "synthetic.csv"
        rows = [{**self.rows[0], "hand_verdict": "correct"}]
        file.write_text(review.csv_text(rows), encoding="utf-8-sig", newline="")
        (self.folder / "synthetic.key.json").write_text(json.dumps({"codes": {"001abc": {}}}))
        result = claim.read_hand_sheet(file)
        self.assertEqual(result["rows"]["001abc"]["hand"], "correct")

    def test_updated_csv_gets_new_cache_so_stale_grades_cannot_replace_it(self):
        def identity(rows):
            html = review.make_html(rows, "sheet.csv")
            return json.loads(html.split("const payload = ", 1)[1].split(";\nconst columns", 1)[0])["identity"]
        original = identity(self.rows)
        updated = [{**self.rows[0], "hand_verdict": "correct", "note": "new judgement"}]
        self.assertNotEqual(original, identity(updated))


if __name__ == "__main__":
    unittest.main()
