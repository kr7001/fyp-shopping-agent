"""The model parser's probe, `runners/parse_probe.py`, on fakes: nothing is sent.

The agreement test compares numbers as numbers and leaves the rules' silent default out, a
call that fails is recorded on its row and the probe goes on, and the result file is written
whatever stops the loop, with the commit that made it (verifier findings, 14 October 2026).
The paraphrase probe, `--questions` (20 October 2026): the file holds the audit's thirty
questions unchanged, the dry run prints the rules' half and the estimate and sends nothing,
the same twice, the tiers are the census table's, a faked model's planted replies reach the
tiers planted, and the census mode prints what it printed before.
Every rule has a case where it fires and one where it stays quiet (LESSONS 31).
"""
import contextlib
import hashlib
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401
import box  # noqa: E402
import form  # noqa: E402
import page  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import planner  # noqa: E402
import primitives  # noqa: E402
import targeting  # noqa: E402
from form import Filter, Form  # noqa: E402
from test_box import BASE, RESULTS_URL, answer_reads, copied_facts, synthetic_page  # noqa: E402

GO = f"Go to {RESULTS_URL} . "


class Agree(unittest.TestCase):
    def setUp(self):
        # "at most", which the rules read as <= 20 as the models below state it. Until form
        # v9 (20 Oct 2026) this said "under $20", which is now the strict < 20, and every
        # model here would disagree on the operator whatever else these tests vary.
        self.rules = form.from_rules(GO + "Is there any seller at most $20 for size M?")
        self.assertEqual(self.rules.filter("price"), Filter("price", "<=", 20.0))
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
        # "at most", so the price filter agrees and only the availability one can differ.
        worded = form.from_rules(GO + "Is there any seller at most $20 for size M in stock?")
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

    def run_main(self, call_model, folder: str | None = None) -> tuple[int | None, dict, str]:
        """The exit code (None when main raised), the file written, and what was printed.
        `folder` is where the probe writes; the test's own temporary folder by default."""
        out = io.StringIO()
        code = None
        folder = folder or self.tmp.name
        with mock.patch.object(parse_probe, "census", return_value=QUESTIONS), \
                mock.patch.object(page, "fetch", return_value=synthetic_page([12.25, 19.50])), \
                mock.patch.object(parse_probe, "call_model", call_model), \
                mock.patch.object(parse_probe, "RESULTS", pathlib.Path(folder)), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"), \
                mock.patch.object(plan_probe, "usage", return_value=None), \
                mock.patch.object(sys, "argv", ["parse_probe.py", "--model", "fake/model"]), \
                contextlib.redirect_stdout(out):
            try:
                code = parse_probe.main()
            except RuntimeError:
                pass
        files = list(pathlib.Path(folder).glob("parse-probe-*.json"))
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
        # A fresh folder for each fault: the probe names its file to the second
        # (parse_probe.py, `stamp`), so two subtests within one second in one folder would
        # leave one file for two runs and the count below would fail by timing (verifier
        # finding, 20 Oct 2026). A real probe is one invocation, minutes long, so the
        # naming is not a fault there.
        for fault in (requests.exceptions.HTTPError("429 Too Many Requests"),
                      requests.exceptions.Timeout("read timed out"),
                      requests.exceptions.ConnectionError("refused"),
                      requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)):
            with self.subTest(fault=type(fault).__name__), tempfile.TemporaryDirectory() as fresh:
                call_model, prompts = self.failing_on_the_second(fault)
                code, payload, printed = self.run_main(call_model, fresh)
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


class CensusUnchanged(unittest.TestCase):
    """The census mode prints what it printed before `--questions` existed: every census
    prompt and the call count, nothing of the paraphrase probe's. The same command's output
    was compared byte for byte before and after the change on 20 October 2026."""

    def test_the_census_dry_run_prints_the_census_prompts_and_nothing_else(self):
        questions = parse_probe.census()
        want = "".join(f"=== prompt {n} of {len(questions)}, {name}\n{form.prompt(question)}\n\n"
                       for n, (name, question) in enumerate(questions, 1))
        want += f"{len(questions)} calls to fake/model, text only, no browser. Nothing was sent.\n"
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["parse_probe.py", "--dry-run", "--model", "fake/model"]), \
                mock.patch.object(page, "fetch", side_effect=AssertionError("a dry run fetched")), \
                contextlib.redirect_stdout(out):
            self.assertEqual(parse_probe.main(), 0)
        self.assertEqual(out.getvalue(), want)


# ---------------------------------------------------------------------------
# Reworded questions, `--questions` (20 October 2026)

PARAPHRASES = paths.TASKS / "paraphrases_v1.json"
# The batch whose stored page the audit judged the paraphrases on.
THORNWOOD = paths.RESULTS / "20261014T213118" / "suite.json"
# The thirty entries, each as the audit's script holds it (id, template, label, expected
# outcome, text), copied by value on 20 October 2026. Pinned so that no question is edited
# after its result has been seen: a new set is a new file (the file's _about).
PARAPHRASES_DIGEST = "0737b62164b56cc15b3685786211d9597808d7fafc498bad7c706aa439c6976d"


def digest(entries: list[dict]) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ParaphraseFile(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(PARAPHRASES.read_text())
        self.entries = self.spec["paraphrases"]

    def test_thirty_entries_copied_from_the_audit_unchanged(self):
        self.assertEqual([entry["id"] for entry in self.entries], list(range(1, 31)))
        self.assertTrue({entry["label"] for entry in self.entries} <= {"clear", "ambiguous", None})
        self.assertEqual(digest(self.entries), PARAPHRASES_DIGEST)
        # One word changed is another set, and the pin says so.
        edited = [dict(entry) for entry in self.entries]
        edited[0]["text"] = edited[0]["text"].replace("lowest", "least")
        self.assertNotEqual(digest(edited), PARAPHRASES_DIGEST)

    def test_every_template_is_a_task_and_starts_with_the_lead(self):
        tasks = {task["id"]: task["query"].format(base=self.spec["base_url"]) for task in
                 json.loads((paths.TASKS / self.spec["templates"]).read_text())["tasks"]}
        for entry in self.entries:
            with self.subTest(id=entry["id"]):
                self.assertIn(entry["template"], tasks)
        spec, loaded = parse_probe.load_questions(PARAPHRASES)
        lead = spec["lead"].format(base=spec["base_url"])
        self.assertEqual(len(loaded), 30)
        for entry in loaded:
            with self.subTest(id=entry["id"]):
                self.assertEqual(entry["template_question"], tasks[entry["template"]])
                self.assertEqual(entry["question"], f"{lead} {entry['text']}")
                self.assertTrue(entry["template_question"].startswith(f"{lead} "))

    def written(self, **over) -> pathlib.Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = pathlib.Path(folder.name) / "paraphrases.json"
        path.write_text(json.dumps({**self.spec, **over}))
        return path

    def test_a_template_the_task_file_lacks_or_another_lead_is_refused(self):
        missing = [dict(self.entries[0], template="apparel-no-such-task")]
        with self.assertRaisesRegex(ValueError, "does not hold"):
            parse_probe.load_questions(self.written(paraphrases=missing))
        with self.assertRaisesRegex(ValueError, "does not start with the lead"):
            parse_probe.load_questions(self.written(lead="Go to {base}/catalogsearch/result/?q=Other ."))

    def test_audit_expected_is_the_templates_outcome_but_on_10_and_29(self):
        # What the file's _about says of audit_expected. On 10 and 29 the audit expected a
        # refutation where the template ("offer size M") is asked back on.
        page_ = parse_probe.stored_page(THORNWOOD)
        _, loaded = parse_probe.load_questions(PARAPHRASES)
        differ = [entry["id"] for entry in loaded if not parse_probe.meets_audit(
            entry["audit_expected"], parse_probe.outcome(entry["template_question"], page_))]
        self.assertEqual(differ, [10, 29])


class StoredPage(unittest.TestCase):
    def test_the_batch_holds_one_page_record_and_it_is_the_page_read(self):
        rows = json.loads(THORNWOOD.read_text())["rows"]
        spec = json.loads(PARAPHRASES.read_text())
        page_ = parse_probe.stored_page(THORNWOOD)
        self.assertEqual(page_.record(), rows[0]["box"]["page"])
        self.assertEqual(page_.url, box.results_url(spec["lead"].format(base=spec["base_url"])))

    def test_two_page_records_or_none_are_refused(self):
        rows = json.loads(THORNWOOD.read_text())["rows"]
        other = json.loads(json.dumps(rows[0]))
        other["box"]["page"]["listings"] = other["box"]["page"]["listings"][1:]
        for name, held in (("two", [rows[0], other]), ("none", [{"box": None}])):
            with self.subTest(held=name), tempfile.TemporaryDirectory() as folder:
                suite = pathlib.Path(folder) / "suite.json"
                suite.write_text(json.dumps({"rows": held}))
                with self.assertRaisesRegex(ValueError, "not one"):
                    parse_probe.stored_page(suite)

    def test_a_question_naming_another_page_is_refused(self):
        with mock.patch.object(parse_probe, "stored_page", return_value=synthetic_page([12.25])), \
                self.assertRaisesRegex(ValueError, "not the stored page"):
            parse_probe.probe_questions(PARAPHRASES, "fake/model", dry_run=True)


class Tiers(unittest.TestCase):
    """The census table's four tiers, each including those before it."""

    def setUp(self):
        self.expected = Form("argmin", "price", (Filter("size", "=", "M"), Filter("availability", "=", "buyable")),
                             evidence={"filter:size": "size M", "filter:availability": "in stock"})

    def got(self, **over) -> Form:
        fields = dict(quantifier="argmin", objective="price", population="results", k=None,
                      filters=(Filter("size", "=", "M"), Filter("availability", "=", "buyable")))
        fields.update(over)
        return Form(source="model", **fields)

    def test_each_tier_includes_those_before(self):
        cases = {
            "the same form": ({}, [True, True, True, True]),
            "another size": ({"filters": (Filter("size", "=", "L"), Filter("availability", "=", "buyable"))},
                             [True, True, True, False]),
            "another population": ({"population": "listing"}, [True, True, False, False]),
            "another objective": ({"objective": "rate"}, [True, False, False, False]),
            # The objective and population agree, the quantifier does not: no tier at all.
            "another quantifier": ({"quantifier": "argmax"}, [False, False, False, False]),
        }
        for name, (over, want) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(list(parse_probe.tiers(self.expected, self.got(**over)).values()), want)
        self.assertEqual(list(parse_probe.tiers(self.expected, None).values()), [False] * 4)

    def test_the_tiers_reproduce_the_census_table(self):
        # The table in docs/content/today.md, from the stored census: the same quantifier on
        # 34 of 37, with the objective 33, with the population 26, every field 5.
        census = json.loads((paths.RESULTS / parse_probe.CENSUS).read_text())
        counts = [0, 0, 0, 0]
        for row in census["rows"]:
            model = form.from_record(row["model"], "model") if row["model"] else None
            reached = parse_probe.tiers(form.from_record(row["rules"], "rules"), model)
            counts = [n + met for n, met in zip(counts, reached.values())]
        self.assertEqual((counts, len(census["rows"])), ([34, 33, 26, 5], 37))


class Outcomes(unittest.TestCase):
    """What `box.decide` does, in the task files' words, on a page of made-up listings."""

    def setUp(self):
        self.page = synthetic_page([31.40, 12.25, 19.50])

    def test_every_outcome_is_named(self):
        cases = {
            GO + "Which seller is cheapest for size M?": ("plan", "total_bound", None),
            GO + "Does every listing offer size M?": ("ask", "refutation", "reading"),
            GO + "Is there a cheap tee in size M?": ("ask", None, "price limit"),
            GO + "Which seller delivers fastest for size M?": ("refuse", None, None),
            "Write a four-line poem about shoes.": ("bypass", None, None),
            GO + "Tell me about the sellers.": ("fallback", "survey", None),
        }
        for question, want in cases.items():
            with self.subTest(question=question):
                found = parse_probe.outcome(question, self.page)
                self.assertEqual((found["outcome"], found["kind"], found["ask"]), want)

    def test_a_plan_decide_refuses_to_compose_is_an_error_row(self):
        with mock.patch.object(parse_probe.box, "decide",
                               side_effect=ValueError("refusing to execute an unsound plan: x")):
            found = parse_probe.outcome(GO + "Which seller is cheapest for size M?", self.page)
        self.assertEqual((found["outcome"], found["kind"]), ("error", None))
        self.assertIn("unsound", found["detail"])

    def test_the_audits_rule_and_the_strict_one(self):
        def found(outcome: str, kind: str | None = None, ask: str | None = None) -> dict:
            return {"outcome": outcome, "kind": kind, "ask": ask, "reading_by": None, "detail": None}

        reading, limit = found("ask", "refutation", "reading"), found("ask", None, "price limit")
        plan, fallback, refuse = found("plan", "refutation"), found("fallback", "survey"), found("refuse")
        # The audit's rule: any ask meets ASK, and a plan's kind its name, the fallback's too.
        for expected, outcome in (("ASK", reading), ("ASK", limit), ("refutation", plan),
                                  ("survey", fallback), ("REFUSE", refuse)):
            with self.subTest(expected=expected, met=outcome["outcome"]):
                self.assertTrue(parse_probe.meets_audit(expected, outcome))
        for expected, outcome in (("ASK", plan), ("refutation", reading), ("REFUSE", limit),
                                  ("survey", plan), ("BYPASS", refuse)):
            with self.subTest(expected=expected, unmet=outcome["outcome"]):
                self.assertFalse(parse_probe.meets_audit(expected, outcome))
        # The strict one: the same outcome, kind and ask.
        self.assertTrue(parse_probe.same_outcome(reading, dict(reading)))
        for other in (limit, plan, dict(reading, kind="survey")):
            with self.subTest(other=other):
                self.assertFalse(parse_probe.same_outcome(reading, other))


class QuestionsDryRun(unittest.TestCase):
    """`--questions --dry-run`: the prompts, the rules' half and the estimate, the same
    twice, and nothing sent, fetched or written."""

    def dry_run(self, model: str) -> str:
        out = io.StringIO()
        sent = mock.Mock(side_effect=AssertionError("a dry run sent or fetched something"))
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(parse_probe, "RESULTS", pathlib.Path(folder)), \
                mock.patch.object(page, "fetch", sent), \
                mock.patch.object(parse_probe, "call_model", sent), \
                mock.patch.object(plan_probe, "load_key", sent), \
                mock.patch.object(plan_probe, "usage", sent), \
                mock.patch.object(sys, "argv", ["parse_probe.py", "--questions", str(PARAPHRASES),
                                                "--dry-run", "--model", model]), \
                contextlib.redirect_stdout(out):
            self.assertEqual(parse_probe.main(), 0)
            self.assertEqual(list(pathlib.Path(folder).iterdir()), [], "a dry run writes no file")
        return out.getvalue()

    def test_the_same_twice_with_the_rules_half_and_the_estimate(self):
        total, calls, census_model = parse_probe.census_charge()
        first, second = self.dry_run(census_model), self.dry_run(census_model)
        self.assertEqual(first, second)
        self.assertIn("=== prompt 30 of 30, paraphrase 30 of apparel-headline\n", first)
        self.assertEqual(first.count("\n     rules:    "), 30)
        self.assertEqual(first.count("\n     box:      "), 30)
        self.assertNotIn("\n     model:    ", first)
        self.assertRegex(first, r"\n  same on every field +\d+ of 30\n")
        lines = first.splitlines()
        self.assertEqual(lines[-2], f"30 calls to {census_model}, text only, no browser. Nothing was sent.")
        self.assertTrue(lines[-1].startswith(f"estimate: ${30 * total / calls:.4f}, 30 calls at "), lines[-1])

    def test_the_estimate_says_when_the_census_priced_another_model(self):
        self.assertTrue(self.dry_run("fake/model").splitlines()[-1].startswith(
            "warning: the census called "))
        _, _, census_model = parse_probe.census_charge()
        self.assertNotIn("warning", self.dry_run(census_model))


# What the faked model does wrong, by paraphrase: every other one answers with the expected
# form itself, so it reaches every tier.
PLANTED = {2: "population", 3: "objective", 4: "quantifier", 5: "a filter", 6: "no form",
           7: "a failed call"}


def planted_reply(entry: dict, page_: page.Page) -> str:
    """The expected form as a model's JSON reply, with the fault planted for this entry."""
    expected = form.from_rules(entry["template_question"], page_).record()
    reply = {key: expected[key] for key in ("quantifier", "objective", "filters", "population",
                                            "k", "reading", "unknowns", "evidence")}
    fault = PLANTED.get(entry["id"])
    if fault == "population":
        reply["population"] = next(p for p in form.POPULATIONS if p != reply["population"])
    elif fault == "objective":
        reply["objective"] = next(o for o in ("price", "rate") if o != reply["objective"])
    elif fault == "quantifier":
        reply["quantifier"] = next(q for q in ("argmin", "argmax") if q != reply["quantifier"])
        reply["k"] = None
    elif fault == "a filter":
        reply["filters"] = reply["filters"] + [{"attribute": "colour", "op": "=", "value": "red"}]
    elif fault == "no form":
        return "I cannot parse that."
    elif fault == "a failed call":
        raise requests.exceptions.Timeout("read timed out")
    return json.dumps(reply)


class QuestionsFakedModel(unittest.TestCase):
    """A paid `--questions` run against a faked model, once for the class: the tiers each
    planted reply reaches, the rules held to the template rather than to themselves, the
    printed counts the kept ones, and every condition in the file."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.page = parse_probe.stored_page(THORNWOOD)
        by_question = {entry["question"]: entry for entry in parse_probe.load_questions(PARAPHRASES)[1]}

        def call_model(key, model, prompt):
            return planted_reply(by_question[prompt.rsplit("The question:\n", 1)[1]], cls.page), 0.001

        out = io.StringIO()
        with mock.patch.object(parse_probe, "RESULTS", pathlib.Path(cls.folder.name)), \
                mock.patch.object(page, "fetch", side_effect=AssertionError("the probe fetched")), \
                mock.patch.object(parse_probe, "call_model", call_model), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"), \
                mock.patch.object(plan_probe, "usage", return_value=None), \
                mock.patch.object(sys, "argv", ["parse_probe.py", "--questions", str(PARAPHRASES),
                                                "--model", "fake/model"]), \
                contextlib.redirect_stdout(out):
            cls.code = parse_probe.main()
        cls.printed = out.getvalue()
        cls.files = list(pathlib.Path(cls.folder.name).glob("parse-probe-paraphrases_v1-*.json"))
        cls.payload = json.loads(cls.files[0].read_text())

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_planted_replies_reach_the_tiers_planted(self):
        self.assertEqual((self.code, len(self.files)), (0, 1))
        rows = {row["id"]: row for row in self.payload["rows"]}
        want = {2: [True, True, False, False], 3: [True, False, False, False], 4: [False] * 4,
                5: [True, True, True, False], 6: [False] * 4, 7: [False] * 4}
        self.assertEqual(sorted(rows), list(range(1, 31)))
        for n, row in rows.items():
            with self.subTest(id=n):
                self.assertEqual(list(row["model_tiers"].values()), want.get(n, [True] * 4))
        self.assertEqual(self.payload["totals"]["model"],
                         {"quantifier": 27, "objective": 26, "population": 25, "every field": 24})
        self.assertEqual((rows[6]["call_failed"], rows[6]["cost_usd"], rows[6]["model"]), (False, 0.001, None))
        self.assertIn("no JSON object", rows[6]["model_problems"][0])
        self.assertEqual((rows[7]["call_failed"], rows[7]["cost_usd"], rows[7]["model"],
                          rows[7]["model_problems"]), (True, None, None, []))
        self.assertTrue(rows[7]["error"].startswith("request failed"))
        self.assertEqual(self.payload["calls_failed"], 1)
        self.assertAlmostEqual(self.payload["charged_usd"], 29 * 0.001)
        self.assertIn("calls failed: 1 of 30", self.printed)

    def test_the_rules_are_held_to_the_template_not_to_themselves(self):
        spec = json.loads(PARAPHRASES.read_text())
        tasks = {task["id"]: task["query"].format(base=spec["base_url"]) for task in
                 json.loads((paths.TASKS / spec["templates"]).read_text())["tasks"]}
        against_themselves = 0
        for row in self.payload["rows"]:
            with self.subTest(id=row["id"]):
                rules = form.from_rules(row["question"], self.page)
                want = parse_probe.tiers(form.from_rules(tasks[row["template"]], self.page), rules)
                self.assertEqual(row["rules_tiers"], want)
                against_themselves += want != parse_probe.tiers(rules, rules)
        self.assertGreater(against_themselves, 0, "held to itself, every form agrees on every field")

    def test_the_counts_printed_are_the_counts_kept(self):
        totals, rows = self.payload["totals"], self.payload["rows"]
        for tier, name in parse_probe.TIERS.items():
            with self.subTest(tier=tier):
                line = re.search(rf"\n  {re.escape(name)} +(\d+) +(\d+) +(\d+) +(\d+) of 30\n", self.printed)
                self.assertIsNotNone(line)
                self.assertEqual([int(n) for n in line.groups()],
                                 [totals[key][tier] for key in ("rules", "model", "model_only", "rules_only")])
                self.assertEqual(totals["model_only"][tier], sum(
                    1 for r in rows if r["model_tiers"][tier] and not r["rules_tiers"][tier]))
                self.assertEqual(totals["rules_only"][tier], sum(
                    1 for r in rows if r["rules_tiers"][tier] and not r["model_tiers"][tier]))
        self.assertEqual(sum(totals["box"].values()), 30)

    def test_the_file_names_every_condition(self):
        p = self.payload
        self.assertEqual((p["questions"], p["model"], p["temperature"], p["page_from"]),
                         ("paraphrases_v1.json", "fake/model", 0, "20261014T213118"))
        self.assertEqual((p["comparison_version"], p["form_version"], p["box_version"],
                          p["primitives_version"], p["planner_version"], p["strategy_version"]),
                         (parse_probe.COMPARISON_VERSION, form.VERSION, box.VERSION,
                          primitives.VERSION, planner.VERSION, targeting.VERSION))
        self.assertEqual(p["page"], json.loads(THORNWOOD.read_text())["rows"][0]["box"]["page"])
        self.assertRegex(p["commit"], r"^[0-9a-f]{40}$")


class ProbeReadsNoAnswer(unittest.TestCase):
    def test_the_probe_reads_no_answer_key_and_copies_no_market_fact(self):
        # It reads each template's id and query, never its answer, and names no seller or
        # price of its own. test_box.NoAnswerKey checks these two checks catch a planted read.
        source = (paths.EXPERIMENTS / "runners" / "parse_probe.py").read_text()
        self.assertEqual(answer_reads(source), [])
        self.assertEqual(copied_facts(source), [])


if __name__ == "__main__":
    unittest.main()
