"""The live check's search-terms reading and its cache flush (24 October 2026, the verifier's
logic audit at cd49128): the brand's search_query rows, which the claim chain writes to its
manifest before and after each invocation, and the flush before a snapshot is taken or compared.
No shop is touched: the database call and the flush are mocked."""
import contextlib
import io
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

sys.path.insert(0, str(paths.REPO / "env"))
import check_aplus_market as check  # noqa: E402


class SearchTerms(unittest.TestCase):
    def test_the_query_names_the_table_and_the_brand_and_takes_one_word_only(self):
        sql = check.search_terms_sql("Wexcombe")
        self.assertIn("FROM search_query", sql)
        self.assertIn("LIKE '%Wexcombe%'", sql)
        self.assertIn("ORDER BY query_id", sql)
        for bad in ("Wexcombe tee", "x'; DROP TABLE search_query; --", "", "IGR-TDV"):
            with self.subTest(brand=bad), self.assertRaises(ValueError):
                check.search_terms_sql(bad)

    def test_the_option_prints_the_rows_and_nothing_else(self):
        rows = "wexcombe tee\t45\t3\t2026-10-24 10:00:00\n"
        with mock.patch.object(check, "mysql", return_value=rows) as mysql, \
                mock.patch.object(sys, "argv", ["check_aplus_market.py", "--search-terms", "Wexcombe"]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check.main(), 0)
        self.assertEqual(out.getvalue(), rows)
        self.assertEqual(mysql.call_args.args[0], check.search_terms_sql("Wexcombe"))

    def test_a_snapshot_is_taken_and_compared_after_a_cache_flush(self):
        # Both readings flush first, so the pages compared are both fresh renders.
        with mock.patch.object(check, "flush_cache") as flush, \
                mock.patch.object(check, "snapshot_pages", return_value={}), \
                mock.patch.object(check, "listing_paths", return_value=[]), \
                mock.patch.object(check, "earlier_brands", return_value=[]), \
                mock.patch.object(check, "igr_rows", return_value=""):
            with mock.patch.object(pathlib.Path, "mkdir"), mock.patch.object(pathlib.Path, "write_text"):
                check.write_snapshot(pathlib.Path("/nowhere/snapshot"), ())
            self.assertEqual(flush.call_count, 1)
            with mock.patch.object(pathlib.Path, "glob", return_value=[]), \
                    mock.patch.object(pathlib.Path, "read_text", return_value=""):
                check.unchanged_lines(pathlib.Path("/nowhere/snapshot"), ())
            self.assertEqual(flush.call_count, 2)

    def test_the_flush_is_magentos_own_command_in_the_container(self):
        with mock.patch.object(check.subprocess, "run") as run:
            check.flush_cache()
        self.assertEqual(run.call_args.args[0][:3], ["docker", "exec", check.CONTAINER])
        self.assertEqual(run.call_args.args[0][-1], "cache:flush")


if __name__ == "__main__":
    unittest.main()
