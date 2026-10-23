"""The reading test's questions from the claim market (23 October 2026): `parse_probe.py
--questions` with `--spec-from` and `--page-from`, for a paraphrase file that leaves its
templates, base, lead and page null, as the held-out paraphrases_v2.json does.

The held-out set is never opened here. A stand-in in its shape, in words written for these
tests, takes its place, and the pilot's market, Larchmere, with its task file and a stored
batch on it, stands in for the claim market. Each refusal has a case where it fires, and the
stand-in on the pilot's market is the case where every one stays quiet. Each fault named was
planted with a fresh bytecode cache and seen to fail its test (LESSONS 31, 39). Nothing here
calls a model or touches the shop.
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import page  # noqa: E402
import paraphrase_scores  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import provider_routing  # noqa: E402
from test_provider_routing import Posted  # noqa: E402  (requests.post as OpenRouter answers it)

sys.path.insert(0, str(paths.REPO / "env"))
import generate_aplus as aplus  # noqa: E402  (the protocol's templates, which template_text copies)
import generate_aplus_tasks as aplus_tasks  # noqa: E402

PILOT = paths.PILOT_TASKS / "tasks_pilot_v1rw_larchmere.json"
BATCH = paths.RESULTS / "20261023T112840"
BASE = "http://localhost:7770"
LEAD = f"Go to {BASE}/catalogsearch/result/?q=Larchmere ."
DEEPSEEK = "deepseek/deepseek-v4-flash"

# The stand-in's entries: id, template, text, expected outcome, label, and how the meaning
# differs where it does. Written for these tests on 23 October 2026, never the held-out texts.
WORDS = [
    (1, "tee-exists-under", "Can I buy a {brand} tee in size M for less than ${limit} right now? "
                            "Yes or no, and who sells it.", "plan", "clear", None),
    (2, "tee-headline", "On the {brand} results page, which tee card shows the lowest price, and "
                        "what is it?", "plan", "clear", None),
    (3, "tee-all-stocked", "Is size M on offer from every {brand} tee listing? Yes or no.", "ask",
     "ambiguous", None),
    (4, "decline-taste", "Which {brand} water has the nicest taste?", "decline", "clear", None),
    (5, "water-count-buyable", "How many {brand} water listings sell any pack at all?", "plan", "clear",
     "asks about any pack, not the 2 x 9.5L pack"),
    (6, "tee-target-price", "What does the dearest {brand} tee in size M cost, among those that can "
                            "be bought?", "plan", "clear", "asks for the highest price, not the lowest"),
]
# The held-out file's expected outcomes in the audit's words, typed here rather than read
# from parse_probe, so a wrong map there is caught.
AUDIT = {"plan": "PLAN", "ask": "ASK", "decline": "REFUSE"}


def standin(**over) -> dict:
    """A paraphrase file in the held-out file's shape: its four fields null, each entry with
    its template's wording as the protocol has it under template_text."""
    entries = []
    for n, template, text, expected, label, differs in WORDS:
        entry = {"id": n, "template": template, "template_text": aplus.TEMPLATES[template][1],
                 "text": text, "expected": expected, "expected_why": "written for these tests",
                 "label": label, "meaning_kept": differs is None}
        if differs:
            entry["meaning_differs"] = differs
        entries.append(entry)
    return {"_about": ["A stand-in for the held-out file's shape, in words written for the tests."],
            "templates": None, "base_url": None, "lead": None, "page_from": None,
            "paraphrases": entries, **over}


def changed(n: int, spec: dict | None = None, **over) -> dict:
    """The stand-in, or `spec`, with entry n changed."""
    spec = spec or standin()
    spec["paraphrases"] = [dict(e, **over) if e["id"] == n else e for e in spec["paraphrases"]]
    return spec


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def run(argv: list[str], folder: pathlib.Path, post=None, environ: dict | None = None) -> tuple[int, str]:
    """`parse_probe.main` with `argv` and what it printed, its result files in `folder`, the
    shop never read, and OpenRouter the given fake `requests.post`, or never called."""
    out = io.StringIO()
    sent = mock.Mock(side_effect=AssertionError("sent or fetched"))
    paid = post is not None
    with contextlib.ExitStack() as stack:
        for target, name, value in ((parse_probe, "RESULTS", folder), (page, "fetch", sent),
                                    (parse_probe.requests, "post", post or sent),
                                    (plan_probe, "load_key", mock.Mock(return_value="fake-key") if paid else sent),
                                    (plan_probe, "usage", mock.Mock(return_value=None) if paid else sent),
                                    (sys, "argv", ["parse_probe.py", *argv])):
            stack.enter_context(mock.patch.object(target, name, value))
        stack.enter_context(mock.patch.dict(os.environ, environ or {}))
        if provider_routing.ENV not in (environ or {}):
            os.environ.pop(provider_routing.ENV, None)
        stack.enter_context(contextlib.redirect_stdout(out))
        code = parse_probe.main()
    return code, out.getvalue()


class Market(unittest.TestCase):
    """Files written for one test, in a folder of its own."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name)
        self.pilot = load(PILOT)

    def write(self, name: str, content: dict) -> pathlib.Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content))
        return path

    def batch(self, name: str, **over) -> pathlib.Path:
        """The pilot batch's suite.json with `over` in place, in a folder of that name."""
        self.write(f"{name}/suite.json", {**load(BATCH / "suite.json"), **over})
        return self.folder / name

    def tasks(self, name: str, **queries: str) -> pathlib.Path:
        """The pilot task file with some tasks' queries replaced, each by its id with
        underscores, as `name`."""
        tasks = [dict(task, query=queries.get(task["id"].replace("-", "_"), task["query"]))
                 for task in self.pilot["tasks"]]
        return self.write(name, {**self.pilot, "tasks": tasks})

    def load(self, spec: dict | None = None, task_file: pathlib.Path = PILOT, batch: pathlib.Path = BATCH):
        return parse_probe.from_market(self.write("standin.json", spec or standin()), task_file, batch)

    def refused(self, cases) -> None:
        """Each case, a name, the keywords for `load` and the reason, refused for that reason."""
        for name, where, why in cases:
            with self.subTest(name), self.assertRaises(ValueError) as raised:
                self.load(**where)
            self.assertIn(why, str(raised.exception), name)


class FromMarket(Market):
    def test_the_questions_are_the_markets_and_the_texts_stay_as_written(self):
        spec, entries, page_ = self.load()
        templates = {task["id"]: task["query"].format(base=BASE) for task in self.pilot["tasks"]}
        # The generator's own limit, read here only to check the one read off the wording.
        limit = self.pilot["_instance"]["exists_limit"]
        self.assertEqual(spec["limit"], limit)
        self.assertEqual([entry["id"] for entry in entries], [n for n, *_ in WORDS])
        for entry, (n, template, text, expected, _, _) in zip(entries, WORDS):
            with self.subTest(id=n):
                self.assertEqual(entry["question"], f"{LEAD} {text.format(brand='Larchmere', limit=limit)}")
                self.assertEqual(entry["template_question"], templates[template])
                self.assertEqual(entry["audit_expected"], AUDIT[expected])
                self.assertEqual(entry["text"], text)
        self.assertIn(f"less than ${limit} right now", entries[0]["question"])
        self.assertEqual((spec["spec_from"], spec["page_from"], spec["draw"], spec["base_url"], spec["lead"]),
                         ("pilot/tasks_pilot_v1rw_larchmere.json", "20261023T112840", "Larchmere:fc5d5cb2df",
                          BASE, "Go to {base}/catalogsearch/result/?q=Larchmere ."))
        self.assertEqual(page_.record(), parse_probe.stored_page(BATCH / "suite.json").record())

    def test_the_limit_is_the_one_the_template_states(self):
        stated = aplus.TEMPLATES["tee-exists-under"][1].format(brand="Larchmere", limit=21)
        task_file = self.tasks("tasks_21.json", tee_exists_under=f"Go to {{base}}/catalogsearch/result/"
                                                                 f"?q=Larchmere . {stated}")
        spec, entries, _ = self.load(task_file=task_file)
        self.assertEqual(spec["limit"], 21)
        self.assertIn("less than $21 right now", entries[0]["question"])

    def test_a_file_that_names_its_own_fields_is_refused(self):
        self.refused((field, {"spec": standin(**{field: value})}, f"standin.json names its own {field}, ")
                     for field, value in (("templates", "tasks_aplus_dev.json"), ("base_url", BASE),
                                          ("lead", "Go to {base}/catalogsearch/result/?q=Larchmere ."),
                                          ("page_from", "20261023T112840")))
        self.assertEqual(len(self.load()[1]), 6)

    def test_a_task_file_of_another_brand_or_draw_is_refused(self):
        brand = "is the task file of {}, and batch {} ran on {}"
        # The market drawn again under the same brand: another answer key, another draw.
        redrawn = {**self.pilot, "_instance": {**self.pilot["_instance"], "exists_limit": 21}}
        self.refused((
            ("a task file of another brand",
             {"task_file": self.write("tasks_wexcombe.json", {**self.pilot, "brand": "Wexcombe"})},
             "tasks_wexcombe.json " + brand.format("Wexcombe", "20261023T112840", "Larchmere")),
            ("a task file with no brand",
             {"task_file": self.write("tasks_unbranded.json", {k: v for k, v in self.pilot.items() if k != "brand"})},
             "tasks_unbranded.json " + brand.format("no brand", "20261023T112840", "Larchmere")),
            ("a batch of another brand", {"batch": self.batch("wexcombe", draw="Wexcombe:0123456789")},
             brand.format("Larchmere", "wexcombe", "Wexcombe")),
            ("a batch that records no draw", {"batch": self.batch("undrawn", draw=None)},
             brand.format("Larchmere", "undrawn", "a market it does not record")),
            ("another draw in the batch", {"batch": self.batch("redrawn", draw="Larchmere:0000000000")},
             "batch redrawn ran on draw Larchmere:0000000000 of Larchmere's market, and "
             "tasks_pilot_v1rw_larchmere.json is draw Larchmere:fc5d5cb2df"),
            ("another draw in the task file", {"task_file": self.write("tasks_redrawn.json", redrawn)},
             "batch 20261023T112840 ran on draw Larchmere:fc5d5cb2df of Larchmere's market, and "
             "tasks_redrawn.json is draw Larchmere:"),
        ))

    def test_templates_not_as_their_authors_read_them_are_refused(self):
        top = "Which three sellers are cheapest for size M of the {brand} tee under ${limit}?"
        headline = aplus.TEMPLATES["tee-headline"][1]
        no_text = standin()
        del no_text["paraphrases"][3]["template_text"]
        self.refused((
            ("a template worded otherwise", {"spec": changed(2, template_text=headline.replace("lowest", "least"))},
             "paraphrase 2's template, tee-headline, is not worded in tasks_pilot_v1rw_larchmere.json as "
             "its author read it"),
            ("a template the task file lacks", {"spec": changed(3, template="tee-softest")},
             "paraphrase 3 rewords 'tee-softest', which tasks_pilot_v1rw_larchmere.json does not hold"),
            ("no template_text", {"spec": no_text}, "paraphrase 4 has no template_text"),
            ("a null template_text", {"spec": changed(4, template_text=None)}, "paraphrase 4 has no template_text"),
            ("another lead", {"task_file": self.tasks("tasks_other_lead.json", tee_headline=(
                f"Go to {{base}}/catalogsearch/result/?q=Other . {headline.format(brand='Larchmere')}"))},
             "the templates in tasks_other_lead.json do not share one lead"),
            ("two limits", {"spec": changed(2, template="tee-top-3", template_text=top),
                            "task_file": self.tasks("tasks_two_limits.json", tee_top_3=(
                                f"Go to {{base}}/catalogsearch/result/?q=Larchmere . "
                                f"{top.format(brand='Larchmere', limit=25)}"))},
             "the templates in tasks_two_limits.json state 2 different limits"),
        ))

    def test_a_text_that_cannot_be_filled_is_refused_without_its_words(self):
        cases = (
            ("another placeholder", changed(2, text="Which {brand} tee in {size} sells best?"),
             "paraphrase 2's text holds a placeholder other than {brand} and {limit}", "sells best"),
            ("a limit no template states",
             changed(2, spec=standin(paraphrases=standin()["paraphrases"][1:]), text="Is a {brand} tee under ${limit}?"),
             "paraphrase 2 needs a limit, and no template in tasks_pilot_v1rw_larchmere.json states one", "tee under"),
            ("an outcome the file does not use", changed(5, expected="maybe"),
             "paraphrase 5 expects 'maybe', not one of plan, ask, decline", "sell any pack"),
        )
        for name, spec, why, words in cases:
            with self.subTest(name), self.assertRaises(ValueError) as raised:
                self.load(spec)
            self.assertIn(why, str(raised.exception), name)
            self.assertNotIn(words, str(raised.exception), name)

    def test_a_question_in_other_words_than_its_task_is_refused(self):
        self.assertEqual(parse_probe.HELD_OUT_TASK, aplus_tasks.REWORDING_ID)
        templates = self.pilot["tasks"][:15]
        # The generator's own tasks for the stand-in's rewordings that keep their meaning, as
        # it writes them into a claim market's task file.
        reworded = aplus_tasks.reworded(templates, standin(), "Larchmere", self.pilot["_instance"]["exists_limit"])
        spec, entries, _ = self.load(task_file=self.write("tasks_claim.json", {**self.pilot, "tasks": templates + reworded}))
        self.assertEqual(spec["held_to_tasks"], 4)
        asked = {task["rewording"]: task["query"].format(base=BASE) for task in reworded}
        self.assertEqual({e["id"]: e["question"] for e in entries if e["id"] in asked}, asked)
        reworded[1] = dict(reworded[1], query=reworded[1]["query"].replace("lowest", "least"))
        edited = self.write("tasks_claim_edited.json", {**self.pilot, "tasks": templates + reworded})
        self.refused((("a task in other words", {"task_file": edited},
                       "paraphrase 2 would be parsed in other words than task rw-02 asked it"),))


class TheProbe(Market):
    def test_the_dry_run_says_where_the_fields_came_from_and_sends_nothing(self):
        results = self.folder / "results"
        results.mkdir()
        code, printed = run(["--dry-run", "--questions", str(self.write("standin.json", standin())),
                             "--spec-from", str(PILOT), "--page-from", str(BATCH), "--model", DEEPSEEK], results)
        self.assertEqual(code, 0)
        self.assertEqual(printed.splitlines()[:2], [
            "the market: pilot/tasks_pilot_v1rw_larchmere.json, draw Larchmere:fc5d5cb2df, for the "
            "templates, the base and the lead, and the limit they state, $20",
            "the page: batch 20261023T112840, http://localhost:7770/catalogsearch/result/?q=Larchmere; "
            "0 of 6 questions held to the words their tasks asked"])
        self.assertIn("=== prompt 6 of 6, paraphrase 6 of tee-target-price\n", printed)
        self.assertIn(f"The question:\n{LEAD} Can I buy a Larchmere tee in size M for less than $20 right now?",
                      printed)
        self.assertIn("=== the rules' half, free, on the page the box read in batch 20261023T112840\n", printed)
        self.assertEqual(list(results.iterdir()), [], "a dry run writes no file")

    def test_the_flags_go_together_and_need_questions(self):
        standin_file = str(self.write("standin.json", standin()))
        for argv in (["--questions", standin_file, "--spec-from", str(PILOT)],
                     ["--questions", standin_file, "--page-from", str(BATCH)],
                     ["--spec-from", str(PILOT), "--page-from", str(BATCH)]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as raised, \
                    contextlib.redirect_stderr(io.StringIO()):
                run(["--dry-run", *argv], self.folder)
            self.assertEqual(raised.exception.code, 2)

    def test_a_file_left_null_is_refused_without_the_flags(self):
        with self.assertRaisesRegex(ValueError, "standin.json leaves templates, base_url, lead, page_from "
                                                "null: give its market's task file with --spec-from"):
            run(["--dry-run", "--questions", str(self.write("standin.json", standin()))], self.folder)


class PaidRun(unittest.TestCase):
    """A paid run against a faked OpenRouter, routed and not: every call's body carries the
    routing when it is on and none when off, the result file names the market's task file,
    the batch and the draw and carries the routing, and each row the provider that served it
    and its entry's text as the file holds it, so the scores read it as it stands."""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        folder = pathlib.Path(cls.folder.name)
        questions = folder / "standin.json"
        questions.write_text(json.dumps(standin()))
        cls.posted, cls.written, cls.codes = {}, {}, []
        for name, environ in (("routed", {provider_routing.ENV: json.dumps(provider_routing.PROPOSED)}),
                              ("not routed", {})):
            results = folder / name
            results.mkdir()
            cls.posted[name] = Posted("GMICloud")
            code, _ = run(["--questions", str(questions), "--spec-from", str(PILOT), "--page-from", str(BATCH),
                           "--model", DEEPSEEK], results, post=cls.posted[name], environ=environ)
            cls.codes.append(code)
            cls.written[name] = [load(path) for path in results.glob("parse-probe-standin-*.json")]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_file_names_the_market_the_batch_and_the_draw(self):
        self.assertEqual(self.codes, [0, 0])
        for name, routing in (("routed", provider_routing.PROPOSED[DEEPSEEK]), ("not routed", None)):
            with self.subTest(name):
                self.assertEqual(len(self.written[name]), 1)
                p = self.written[name][0]
                self.assertEqual((p["questions"], p["spec_from"], p["page_from"], p["draw"], p["provider_routing"]),
                                 ("standin.json", "pilot/tasks_pilot_v1rw_larchmere.json", "20261023T112840",
                                  "Larchmere:fc5d5cb2df", routing))
                self.assertFalse(p["in_sample"])

    def test_every_call_is_routed_as_the_setting_says(self):
        for name, routing in (("routed", provider_routing.PROPOSED[DEEPSEEK]), ("not routed", None)):
            with self.subTest(name):
                bodies = self.posted[name].bodies
                self.assertEqual(len(bodies), 6)
                self.assertEqual([body.get("provider") for body in bodies], [routing] * 6)

    def test_each_row_has_its_provider_its_question_and_its_text_as_written(self):
        rows = self.written["routed"][0]["rows"]
        prompts = [body["messages"][0]["content"] for body in self.posted["routed"].bodies]
        self.assertEqual({row["provider"] for row in rows}, {"GMICloud"})
        for row, (n, _, text, expected, _, _) in zip(rows, WORDS):
            with self.subTest(id=n):
                self.assertEqual((row["id"], row["text"], row["audit_expected"]), (n, text, AUDIT[expected]))
                self.assertTrue(row["question"].startswith(f"{LEAD} "))
                self.assertTrue(prompts[n - 1].endswith(f"The question:\n{row['question']}"))

    def test_the_scores_read_the_result_as_the_file_stands(self):
        scored = paraphrase_scores.scores(self.written["routed"][0], standin())
        self.assertEqual(scored["meaning_kept"]["ids"], [1, 2, 3, 4])
        self.assertEqual([row["id"] for row in scored["meaning_differs"]["rows"]], [5, 6])
        self.assertEqual(scored["meaning_kept"]["totals"]["paraphrases"], 4)


class MeetsAudit(unittest.TestCase):
    def test_plan_is_met_by_any_plan_and_by_nothing_else(self):
        def found(outcome: str, kind: str | None = None, ask: str | None = None) -> dict:
            return {"outcome": outcome, "kind": kind, "ask": ask, "reading_by": None, "detail": None}

        for outcome in (found("plan", "availability_bound"), found("plan", "survey"), found("fallback", "survey")):
            with self.subTest(met=outcome["outcome"], kind=outcome["kind"]):
                self.assertTrue(parse_probe.meets_audit("PLAN", outcome))
        for outcome in (found("ask", "refutation", "reading"), found("ask", None, "price limit"), found("refuse"),
                        found("bypass"), found("error")):
            with self.subTest(unmet=outcome["outcome"]):
                self.assertFalse(parse_probe.meets_audit("PLAN", outcome))
        # Each of the held-out file's words is met by what the generator expects of its tasks.
        for word, outcome in aplus_tasks.EXPECTED.items():
            with self.subTest(word=word):
                self.assertTrue(parse_probe.meets_audit(parse_probe.EXPECTED[word], found(outcome, "survey")))


if __name__ == "__main__":
    unittest.main()
