"""The model parser's probe, `runners/parse_probe.py`, on fakes: nothing is sent.

The agreement test compares numbers as numbers and leaves the rules' silent default out, a
call that fails is recorded on its row and the probe goes on, and the result file is written
whatever stops the loop, with the commit that made it (verifier findings, 14 October 2026).
Every rule has a case where it fires and one where it stays quiet (LESSONS 31).
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401
import form  # noqa: E402
import page  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
from form import Filter, Form  # noqa: E402
from test_box import BASE, RESULTS_URL, synthetic_page  # noqa: E402

GO = f"Go to {RESULTS_URL} . "


class Agree(unittest.TestCase):
    def setUp(self):
        self.rules = form.from_rules(GO + "Is there any seller under $20 for size M?")
        # Size and the limit came from the words. Availability is the silent default.
        self.assertEqual(self.rules.filter("availability"), Filter("availability", "=", "buyable"))
        self.assertNotIn("filter:availability", self.rules.evidence)
        self.assertIn("filter:size", self.rules.evidence)

    def model(self, *filters, **over) -> Form:
        fields = dict(quantifier="exists", objective="price", population="results", k=None)
        fields.update(over)
        return Form(filters=tuple(filters), source="model", **fields)

    def test_numbers_compare_as_numbers(self):
        # The rules hold 20.0; a model says 20, or "20". Until 14 Oct 2026 these differed.
        for value in (20, "20", 20.0):
            with self.subTest(value=value):
                self.assertTrue(parse_probe.agree(
                    self.rules, self.model(Filter("price", "<=", value), Filter("size", "=", "M"))))
        self.assertFalse(parse_probe.agree(
            self.rules, self.model(Filter("price", "<=", 25), Filter("size", "=", "M"))))

    def test_a_silent_default_may_be_left_out_but_not_contradicted(self):
        left_out = self.model(Filter("price", "<=", 20), Filter("size", "=", "M"))
        self.assertTrue(parse_probe.agree(self.rules, left_out))
        stated = self.model(Filter("price", "<=", 20), Filter("size", "=", "M"),
                            Filter("availability", "=", "buyable"))
        self.assertTrue(parse_probe.agree(self.rules, stated))
        contradicted = self.model(Filter("price", "<=", 20), Filter("size", "=", "M"),
                                  Filter("availability", "=", "listed"))
        self.assertFalse(parse_probe.agree(self.rules, contradicted))

    def test_a_filter_only_the_model_states_is_still_a_difference(self):
        # The stored census parse has five of these, a brand as a title filter among them.
        # They are what the DIFF lines are read for, so the fix must not hide them.
        invented = self.model(Filter("price", "<=", 20), Filter("size", "=", "M"),
                              Filter("title", "contains", "Thornwood"))
        self.assertFalse(parse_probe.agree(self.rules, invented))

    def test_a_filter_the_words_chose_has_to_be_there(self):
        self.assertFalse(parse_probe.agree(self.rules, self.model(Filter("price", "<=", 20))))
        self.assertFalse(parse_probe.agree(
            self.rules, self.model(Filter("price", ">=", 20), Filter("size", "=", "M"))))
        # With an availability word in the question the filter is derived, not a default.
        worded = form.from_rules(GO + "Is there any seller under $20 for size M in stock?")
        self.assertIn("filter:availability", worded.evidence)
        self.assertFalse(parse_probe.agree(
            worded, self.model(Filter("price", "<=", 20), Filter("size", "=", "M"))))

    def test_the_shape_has_to_match(self):
        same = (Filter("price", "<=", 20), Filter("size", "=", "M"))
        for over in (dict(quantifier="argmin"), dict(objective="availability"),
                     dict(population="listing"), dict(quantifier="topk", k=3)):
            with self.subTest(over=over):
                self.assertFalse(parse_probe.agree(self.rules, self.model(*same, **over)))

    def test_comparable(self):
        self.assertEqual(parse_probe.comparable(20), 20.0)
        self.assertEqual(parse_probe.comparable(" 20.0 "), 20.0)
        self.assertEqual(parse_probe.comparable("M"), "M")
        self.assertEqual(parse_probe.comparable(("Seller A", "Seller B")), frozenset({"Seller A", "Seller B"}))

    def test_an_in_filters_values_compare_as_a_set(self):
        # Verifier finding, 14 Oct 2026: seller in (B, C) and (C, B) were different filters.
        page_ = synthetic_page([31.40, 12.25, 19.50])
        rules = form.from_rules(GO + "Is Seller B cheaper than Seller C for size M?", page_)
        self.assertEqual(rules.filter("seller"), Filter("seller", "in", ("Seller B", "Seller C")))

        def model(*sellers: str) -> Form:
            return Form("lookup", "price", (Filter("seller", "in", sellers), Filter("size", "=", "M")),
                        source="model")

        self.assertTrue(parse_probe.agree(rules, model("Seller C", "Seller B")))
        self.assertTrue(parse_probe.agree(rules, model("Seller B", "Seller C")))
        self.assertFalse(parse_probe.agree(rules, model("Seller C", "Seller D")))
        self.assertFalse(parse_probe.agree(rules, model("Seller B")))


class ResultsPage(unittest.TestCase):
    """The rules get the results page a question names, fetched once per URL."""

    def setUp(self):
        parse_probe.PAGES.clear()
        self.addCleanup(parse_probe.PAGES.clear)

    def test_fetched_once_per_results_url_and_not_for_a_product_url(self):
        fetched = []

        def fetch(url, *args, **kwargs):
            fetched.append(url)
            return synthetic_page([12.25])

        with mock.patch.object(page, "fetch", fetch):
            first = parse_probe.results_page(GO + "Which seller is cheapest for size M?")
            second = parse_probe.results_page(GO + "Which seller is cheapest for size L?")
            self.assertIsNone(parse_probe.results_page(
                f"On {BASE}/example-tee-01.html what is the price of size XL?"))
            self.assertIsNone(parse_probe.results_page("Which seller is cheapest for size M?"))
        self.assertIs(first, second)
        self.assertEqual(fetched, [RESULTS_URL])

    def test_a_page_the_shop_cannot_serve_is_none_once_with_a_warning(self):
        def fetch(url, *args, **kwargs):
            raise ValueError(f"no product cards on {url}")

        with mock.patch.object(page, "fetch", fetch), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(parse_probe.results_page(GO + "Which seller is cheapest for size M?"))
            self.assertIsNone(parse_probe.results_page(GO + "Which seller is cheapest for size L?"))
        self.assertEqual(err.getvalue().count("could not be read"), 1)


QUESTIONS = [("fake.json", GO + "Which seller is cheapest for size M?"),
             ("fake.json", GO + "Which seller is cheapest for size M, the second time?"),
             # Names two sellers of the page: a lookup only when the rules were given it.
             ("fake.json", GO + "Is Seller A cheaper than Seller B for size M?")]
# What the fake model answers: the form the rules give each question, so the two agree.
CHEAPEST_REPLY = json.dumps({"quantifier": "argmin", "objective": "price", "population": "results",
                             "filters": [{"attribute": "size", "op": "=", "value": "M"}], "k": None,
                             "reading": None, "unknowns": [], "evidence": {"quantifier": "cheapest"}})
LOOKUP_REPLY = json.dumps({"quantifier": "lookup", "objective": "price", "population": "results",
                           "filters": [{"attribute": "seller", "op": "in", "value": ["Seller A", "Seller B"]},
                                       {"attribute": "size", "op": "=", "value": "M"}], "k": None,
                           "reading": None, "unknowns": [], "evidence": {"quantifier": "Seller A, Seller B"}})


def reply_for(prompt: str) -> str:
    return LOOKUP_REPLY if "Is Seller A cheaper" in prompt else CHEAPEST_REPLY


class Probe(unittest.TestCase):
    """`main` on fakes: a question whose call fails is a row with the error and no cost,
    the others are parsed, and the file is written however the loop ends."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parse_probe.PAGES.clear()
        self.addCleanup(parse_probe.PAGES.clear)

    def run_main(self, call_model) -> tuple[int | None, dict, str]:
        """The exit code (None when main raised), the file written, and what was printed."""
        out = io.StringIO()
        code = None
        with mock.patch.object(parse_probe, "census", return_value=QUESTIONS), \
                mock.patch.object(page, "fetch", return_value=synthetic_page([12.25, 19.50])), \
                mock.patch.object(parse_probe, "call_model", call_model), \
                mock.patch.object(parse_probe, "RESULTS", pathlib.Path(self.tmp.name)), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"), \
                mock.patch.object(plan_probe, "usage", return_value=None), \
                mock.patch.object(sys, "argv", ["parse_probe.py", "--model", "fake/model"]), \
                contextlib.redirect_stdout(out):
            try:
                code = parse_probe.main()
            except RuntimeError:
                pass
        files = list(pathlib.Path(self.tmp.name).glob("parse-probe-*.json"))
        self.assertEqual(len(files), 1, "the result file is written once, whatever happened")
        return code, json.loads(files[0].read_text()), out.getvalue()

    def failing_on_the_second(self, fault: Exception):
        prompts = []

        def call_model(key, model, prompt):
            prompts.append(prompt)
            if "second time" in prompt:
                raise fault
            return reply_for(prompt), 0.001

        return call_model, prompts

    def test_a_failed_call_is_recorded_and_the_probe_goes_on(self):
        # The last is what `reply.json()` raises for a 200 whose body is not JSON. It is a
        # ValueError too, and until 14 Oct 2026 was recorded as a model problem (verifier).
        for fault in (requests.exceptions.HTTPError("429 Too Many Requests"),
                      requests.exceptions.Timeout("read timed out"),
                      requests.exceptions.ConnectionError("refused"),
                      requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)):
            with self.subTest(fault=type(fault).__name__):
                call_model, prompts = self.failing_on_the_second(fault)
                code, payload, printed = self.run_main(call_model)
                self.assertEqual(code, 0)
                self.assertEqual(len(prompts), 3, "no retry: one call per question")
                rows = payload["rows"]
                self.assertEqual([r["call_failed"] for r in rows], [False, True, False])
                failed = rows[1]
                self.assertTrue(failed["error"].startswith("request failed"))
                self.assertEqual((failed["model"], failed["cost_usd"], failed["agree"],
                                  failed["model_problems"]), (None, None, False, []))
                for row in (rows[0], rows[2]):
                    self.assertEqual((row["agree"], row["cost_usd"], row["error"]), (True, 0.001, None))
                    self.assertEqual(row["model"]["quantifier"], row["rules"]["quantifier"])
                self.assertEqual((payload["calls_failed"], payload["charged_usd"]), (1, 0.002))
                self.assertIn("calls failed: 1 of 3", printed.splitlines()[-2])
                self.assertIn("no form: request failed", printed)

    def test_no_failure_counts_none(self):
        code, payload, printed = self.run_main(lambda key, model, prompt: (reply_for(prompt), 0.001))
        self.assertEqual((code, payload["calls_failed"]), (0, 0))
        self.assertEqual([r["agree"] for r in payload["rows"]], [True, True, True])
        self.assertIn("calls failed: 0 of 3", printed)
        self.assertIn("agree on 3 of 3 questions", printed)

    def test_a_reply_that_is_not_a_form_is_a_model_problem_not_a_failed_call(self):
        def call_model(key, model, prompt):
            return ("I cannot parse that.", 0.001) if "second time" in prompt else (reply_for(prompt), 0.001)

        code, payload, _ = self.run_main(call_model)
        row = payload["rows"][1]
        self.assertEqual((row["call_failed"], row["model"], row["cost_usd"]), (False, None, 0.001))
        self.assertIn("no JSON object", row["model_problems"][0])
        self.assertEqual(payload["calls_failed"], 0)

    class Reply:
        """What `requests.post` returns, reduced to what `call_model` reads."""

        def __init__(self, body, fault: Exception | None = None):
            self.body, self.fault = body, fault

        def raise_for_status(self) -> None:
            pass

        def json(self):
            if self.fault:
                raise self.fault
            return self.body

    def posting(self, second):
        """A fake `requests.post` that serves a completion for every prompt but the second,
        which gets `second`. The real `call_model` reads the replies."""
        def post(url, **request):
            prompt = request["json"]["messages"][0]["content"]
            if "second time" in prompt:
                return second
            return self.Reply({"choices": [{"message": {"content": reply_for(prompt)}}],
                               "usage": {"cost": 0.001}})
        return post

    def through_call_model(self, second) -> tuple[int | None, dict, str]:
        with mock.patch.object(parse_probe.requests, "post", self.posting(second)):
            result = self.run_main(parse_probe.call_model)
        # So that the next run in the same test is written once too, as `run_main` checks.
        for written in pathlib.Path(self.tmp.name).glob("parse-probe-*.json"):
            written.unlink()
        return result

    def test_a_reply_without_a_completion_is_a_failed_call_that_keeps_its_charge(self):
        # Verifier finding, 14 Oct 2026: a 200 whose body has no `choices` raised KeyError
        # out of the loop, which lost the row and whatever it had been charged.
        for body, cost in (({"usage": {"cost": 0.003}, "error": {"message": "overloaded"}}, 0.003),
                           ({"choices": []}, None),
                           ({"choices": [{"message": {}}], "usage": {"cost": 0.003}}, 0.003),
                           ([], None)):
            with self.subTest(body=body):
                code, payload, printed = self.through_call_model(self.Reply(body))
                self.assertEqual(code, 0)
                rows = payload["rows"]
                self.assertEqual([r["call_failed"] for r in rows], [False, True, False])
                failed = rows[1]
                self.assertTrue(failed["error"].startswith("reply not a completion"))
                self.assertEqual((failed["model"], failed["cost_usd"], failed["model_problems"]),
                                 (None, cost, []))
                self.assertEqual(payload["calls_failed"], 1)
                self.assertAlmostEqual(payload["charged_usd"], 0.002 + (cost or 0))
                self.assertIn("calls failed: 1 of 3", printed)

    def test_a_body_that_is_not_json_is_a_failed_call_through_the_real_call(self):
        broken = self.Reply(None, requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0))
        code, payload, _ = self.through_call_model(broken)
        self.assertEqual(code, 0)
        failed = payload["rows"][1]
        self.assertEqual((failed["call_failed"], failed["cost_usd"], failed["model"]), (True, None, None))
        self.assertTrue(failed["error"].startswith("request failed"))
        self.assertEqual(payload["calls_failed"], 1)
        # And a sound reply through the same path parses, with its charge.
        code, payload, _ = self.through_call_model(
            self.Reply({"choices": [{"message": {"content": CHEAPEST_REPLY}}], "usage": {"cost": 0.002}}))
        self.assertEqual((code, payload["calls_failed"], payload["rows"][1]["cost_usd"],
                          payload["rows"][1]["agree"]), (0, 0, 0.002, True))

    def test_the_file_is_written_when_something_else_stops_the_loop(self):
        def call_model(key, model, prompt):
            if "second time" in prompt:
                raise RuntimeError("the laptop fell over")
            return reply_for(prompt), 0.001

        code, payload, printed = self.run_main(call_model)
        self.assertIsNone(code)
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["charged_usd"], 0.001)
        self.assertIn("agree on 1 of 1 questions", printed)

    def test_the_file_says_which_commit_and_form_version_made_it(self):
        _, payload, _ = self.run_main(lambda key, model, prompt: (reply_for(prompt), 0.001))
        self.assertRegex(payload["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual((payload["form_version"], payload["model"], payload["temperature"]),
                         (form.VERSION, "fake/model", 0))
        with contextlib.redirect_stderr(io.StringIO()) as err, \
                mock.patch.object(parse_probe.paths, "REPO", pathlib.Path(self.tmp.name)):
            self.assertEqual(parse_probe.repository_commit(), "unknown")
        self.assertIn("warning", err.getvalue())

    def test_the_rules_see_the_page_the_question_names(self):
        # Until 14 Oct 2026 the probe parsed without the page, so the third question, which
        # names two of its sellers, fell to the survey fallback instead of a lookup.
        _, payload, _ = self.run_main(lambda key, model, prompt: (reply_for(prompt), 0.001))
        rules = payload["rows"][2]["rules"]
        self.assertEqual((rules["quantifier"], rules["kind"]), ("lookup", "named_lookup"))
        self.assertEqual(rules["filters"][0], {"attribute": "seller", "op": "in",
                                               "value": ["Seller A", "Seller B"]})
        self.assertEqual(payload["rows"][0]["rules"]["quantifier"], "argmin")


if __name__ == "__main__":
    unittest.main()
