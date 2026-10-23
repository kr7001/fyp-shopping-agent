"""The two fixes for the pilot after the verifier's FAIL at cce9ab0 (23 October 2026).

1. `form.parse_reply` reads a reply DeepSeek may give, which has never been the parser: a
   null content, a list of content parts, reasoning with braces before or after the form, a
   fenced form, and content of another type, refused as a ValueError so the box falls back
   to the rules. The first attempt is the one every stored parse was made by, and a replay of
   every stored form, re-written as the reply that would give it, parses the same under both.
2. `suite.py --reading own`: the scripted user answers each question with the reading its
   own key was written under, menu for a question with two readings and buyable for any other
   with a key. `score.under_reading` given the sidecar's `two_readings` holds "menu" to be the
   own reading of those alone, and `suite.unscorable` refuses a batch that would score a run
   told the menu reading against a key that counts what can be bought.

Every rule fires on a planted fault and stays quiet on the case it must leave alone, each
fault planted with a fresh bytecode cache (LESSONS 31, 39). Nothing here calls a model or
touches the shop, and nothing reads the held-out rewordings.
"""
import argparse
import json
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import box  # noqa: E402
import form  # noqa: E402
import page as page_module  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402
import voids  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402

PILOT = paths.PILOT_TASKS / "tasks_pilot_v1rw_larchmere.json"
FIXTURE = paths.FIXTURES / "aplus_dev.json"
TWO = ["tee-all-stocked", "tee-count-stocked", "water-all-stocked", "pv1-09", "pv1-12", "pv1-13", "pv1-14"]
# The pilot's 28 box slots, as the chain runs them.
SLOTS = ("tee-headline tee-target-price tee-cheapest-target tee-all-stocked tee-count-stocked "
         "tee-count-buyable tee-exists-under tee-top-3 water-target-price water-cheapest-target "
         "water-all-stocked water-count-buyable water-best-per-litre decline-delivery decline-taste "
         "pv1-01 pv1-02 pv1-03 pv1-04 pv1-06 pv1-07 pv1-09 pv1-12 pv1-13 pv1-15 pv1-16 pv1-19 pv1-20").split()
FORM = {"quantifier": "argmin", "objective": "price",
        "filters": [{"attribute": "size", "op": "=", "value": "M"},
                    {"attribute": "availability", "op": "=", "value": "buyable"}],
        "population": "results", "k": None, "negated": False, "reading": None, "unknowns": [],
        "ambiguities": [], "evidence": {"quantifier": "cheapest", "filters": "size M, can be bought"}}
REPLY = "Here is the form:\n" + json.dumps(FORM)


def old_parse_reply(reply, version: int = form.PROMPT_VERSION) -> form.Form:
    """`form.parse_reply` as it stood at cce9ab0, copied by value on 23 October 2026, the code
    every stored parse was made by."""
    block = re.search(r"\{.*\}", reply or "", re.DOTALL)
    if not block:
        raise ValueError(f"the model's reply holds no JSON object: {(reply or '')[:200]!r}")
    try:
        data = json.loads(block.group(0))
    except json.JSONDecodeError as error:
        raise ValueError(f"the model's JSON does not parse ({error}): {block.group(0)[:200]!r}")
    import dataclasses
    return dataclasses.replace(form.from_record(data, source="model"), prompt_version=version)


def outcome(parse, reply):
    """A parse's result, a form or the type and message it raised, so two can be compared."""
    try:
        return parse(reply)
    except Exception as fault:  # noqa: BLE001  (the type is what is compared)
        return (type(fault).__name__, str(fault))


def larchmere_page() -> page_module.Page:
    """Larchmere's two results pages as the box reads them, from the fixture, for a test only:
    each listing's seller, title and advertised price, cheapest buyable."""
    fixture = json.loads(FIXTURE.read_text())
    base = "http://localhost:7770"
    listings = [page_module.Listing(seller=f["seller"], title=f["name"], url=f"{base}/{f['parent_sku'].lower()}.html",
                                    advertised=min(v["price"] for v in f["variants"] if v["qty"] > 0))
                for f in fixture["families"]]
    first = f"{base}/catalogsearch/result/?q=Larchmere"
    return page_module.Page(url=first, listings=listings, total=len(listings), next_page=False,
                            pages=(first, f"{base}/catalogsearch/result/index/?p=2&q=Larchmere"), reader="rendered")


# ---------------------------------------------------------------------------
# 1. What a model's reply may be

class TheReplyAsText(unittest.TestCase):
    """Planted: `reply_text` letting content of another type through, a null not read as
    nothing, the text parts not joined, and the call site passing content as it came."""

    def test_none_is_nothing_and_a_list_is_its_text_parts(self):
        self.assertEqual(form.reply_text(None), "")
        self.assertEqual(form.reply_text("a"), "a")
        parts = [{"type": "reasoning", "text": "{not this}"}, {"type": "text", "text": "Here is the form:\n"},
                 {"type": "image_url", "image_url": {"url": "x"}}, {"type": "text", "text": json.dumps(FORM)}]
        self.assertEqual(form.reply_text(parts), REPLY)
        self.assertEqual(form.parse_reply(parts).filter("size").value, "M")
        self.assertEqual(form.reply_text(["a", {"type": "text", "text": "b"}, 3]), "ab")

    def test_any_other_type_is_a_value_error_that_names_it(self):
        for content, name in ((5, "int"), ({"text": "x"}, "dict"), (2.5, "float")):
            with self.subTest(content=content):
                with self.assertRaisesRegex(ValueError, f"of type {name}, not text"):
                    form.parse_reply(content)
        # The old code took None for nothing too; an int it did not survive.
        with self.assertRaises(TypeError):
            old_parse_reply(5)
        with self.assertRaisesRegex(ValueError, "holds no JSON object: ''"):
            form.parse_reply(None)

    def test_the_box_falls_back_and_goes_on(self):
        page = larchmere_page()
        question = json.loads(PILOT.read_text())["tasks"][1]["query"].format(base="http://localhost:7770")
        for content, words in ((5, "of type int"), (None, "holds no JSON object")):
            with self.subTest(content=content):
                decision = box.decide(question, page, parser="model", call=lambda prompt: content)
                parse = decision.record()["parse"]
                self.assertEqual(parse["used"], "rules")
                self.assertIn(words, parse["fallback_reason"])
                self.assertEqual(decision.kind, "availability_bound")
        listed = box.decide(question, page, parser="model",
                            call=lambda prompt: [{"type": "text", "text": REPLY}])
        self.assertEqual(listed.record()["parse"]["used"], "model")

    def test_the_call_site_reads_the_content_as_text(self):
        def answered(content):
            reply = mock.Mock()
            reply.raise_for_status = lambda: None
            reply.json = lambda: {"choices": [{"message": {"content": content}}],
                                  "usage": {"cost": 0.0002, "prompt_tokens": 5000, "completion_tokens": 90}}
            return mock.patch.object(parse_probe.requests, "post", return_value=reply)

        tokens = {"prompt": 5000, "completion": 90}
        for content, text in ((None, ""), ([{"type": "text", "text": REPLY}], REPLY), (REPLY, REPLY)):
            with self.subTest(content=str(content)[:20]), answered(content):
                self.assertEqual(parse_probe.call_model("k", "m", "p"), (text, 0.0002, tokens, None))
        with answered(7), self.assertRaises(parse_probe.UnexpectedReply) as raised:
            parse_probe.call_model("k", "m", "p")
        self.assertIn("of type int", str(raised.exception))
        self.assertEqual((raised.exception.cost, raised.exception.tokens), (0.0002, tokens))
        # Through the suite's call the charge is kept, and the box falls back.
        charges, counts = [], []
        with answered(7):
            call = suite.parser_call("m", "k", charges, counts)
            with self.assertRaises(parse_probe.UnexpectedReply):
                call("p")
        self.assertEqual((charges, counts), ([0.0002], [tokens]))


class ReasoningAroundTheForm(unittest.TestCase):
    """Planted: no second attempt, the second attempt run first, the first object taken for
    the last, and an object inside a form taken for one."""

    def test_braces_before_or_after_the_form(self):
        for label, reply in (
                ("before", "The user wants {size: M} and maybe {colour}. " + REPLY),
                ("after", REPLY + "\nNote: I left {title} out."),
                ("both", "Think {x}. " + REPLY + " Then {y}."),
                ("a fence", "```json\n" + json.dumps(FORM, indent=2) + "\n```"),
                ("a fence after braces", "I set {size} to M.\n```json\n" + json.dumps(FORM) + "\n```\nDone {z}.")):
            with self.subTest(reply=label):
                parsed = form.parse_reply(reply)
                self.assertEqual((parsed.kind(), parsed.filter("size").value), ("availability_bound", "M"))
                if label != "a fence":
                    # The first attempt alone, the old code, fails on it.
                    self.assertIsInstance(outcome(old_parse_reply, reply), tuple)

    def test_the_last_form_is_taken(self):
        draft = {**FORM, "filters": [{"attribute": "size", "op": "=", "value": "L"}]}
        reply = f"First thought: {json.dumps(draft)}\nOn reflection, the size asked is M: {json.dumps(FORM)}"
        self.assertEqual(form.parse_reply(reply).filter("size").value, "M")

    def test_an_object_inside_a_form_is_never_taken_for_it(self):
        # Evidence whose lines happen to read as a form, inside the real one.
        sly = {**FORM, "evidence": {"quantifier": "count", "objective": "availability", "population": "results"}}
        reply = "Reasoning {about it}. " + json.dumps(sly)
        parsed = form.parse_reply(reply)
        self.assertEqual((parsed.quantifier, parsed.filter("size").value), ("argmin", "M"))
        # Taking the last object a form accepts, inside ones included, would take the evidence.
        inner = json.dumps(sly["evidence"])
        self.assertEqual(form.from_record(json.loads(inner), "model").quantifier, "count")

    def test_a_reply_with_no_form_fails_as_it_did(self):
        for reply in ("no braces at all", "an {unclosed", "{\"quantifier\": \"argmin\"}",
                      "{not json} and {\"also\": \"not a form\"}"):
            with self.subTest(reply=reply):
                self.assertEqual(outcome(form.parse_reply, reply), outcome(old_parse_reply, reply))
                self.assertIsInstance(outcome(form.parse_reply, reply), tuple)


class EveryStoredFormParsesAsBefore(unittest.TestCase):
    """No stored model reply is kept as text: the two paraphrase and census probes kept the
    form each reply gave, and no batch has yet run under the model parser. So each stored form
    is written back as the replies that give it, in the shapes the prompts ask for, and with
    the worked examples every prompt sends, each must parse to the same form as under the
    code every stored parse was made by."""

    @classmethod
    def setUpClass(cls):
        fields = ("quantifier", "objective", "filters", "population", "k", "reading", "unknowns",
                  "evidence", "negated", "ambiguities")
        cls.forms = []
        for name in ("parse-probe-20261014T112047.json", "parse-probe-paraphrases_v1-20261020T223344.json"):
            for row in json.loads((paths.RESULTS / name).read_text())["rows"]:
                if row.get("model"):
                    cls.forms.append({key: row["model"][key] for key in fields if key in row["model"]})
        cls.forms += [example for _, _, example in form.EXAMPLES]

    def test_the_same_form_under_both(self):
        self.assertEqual(len(self.forms), 37 + 30 + len(form.EXAMPLES))
        replayed = 0
        for record in self.forms:
            body = json.dumps(record)
            for reply in (body, "Here is the form:\n" + body, "```json\n" + json.dumps(record, indent=2) + "\n```"):
                with self.subTest(reply=reply[:60]):
                    old, new = outcome(old_parse_reply, reply), outcome(form.parse_reply, reply)
                    self.assertEqual(new, old)
                    replayed += 1
        self.assertEqual(replayed, 3 * len(self.forms))


# ---------------------------------------------------------------------------
# 2. The scripted user answers with the question's own meaning

class TheOwnReading(unittest.TestCase):
    """Planted: "own" answering menu everywhere, a keyless question answered, two_readings
    ignored by `under_reading`, and the model's menu not checked."""

    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(PILOT.read_text())
        cls.by = {task["id"]: task for task in cls.spec["tasks"]}
        cls.readings = score.readings_for(PILOT)
        cls.two = score.two_readings_for(PILOT)

    def test_the_sidecar_names_the_seven(self):
        self.assertEqual(self.two, TWO)

    def test_each_question_gets_the_reading_its_key_was_written_under(self):
        expected = {"pv1-15": "buyable", "pv1-19": "buyable", "tee-count-buyable": "buyable",
                    "tee-count-stocked": "menu", "pv1-12": "menu", "water-all-stocked": "menu",
                    "decline-taste": None}
        for task_id, reply in expected.items():
            with self.subTest(task=task_id):
                self.assertEqual(suite.scripted_reply(self.by[task_id], "own", self.two), reply)
        for task in self.spec["tasks"]:
            with self.subTest(task=task["id"]):
                for flag in ("menu", "buyable", None):
                    self.assertEqual(suite.scripted_reply(task, flag, self.two), flag)
        # A sidecar that names no two_readings wrote every key under the menu reading.
        self.assertEqual(suite.scripted_reply(self.by["pv1-15"], "own", None), "menu")

    def test_under_reading_holds_menu_to_the_questions_that_have_two(self):
        task = self.by["pv1-15"]
        with self.assertRaises(score.NoKeyForReading):
            score.under_reading(task, "menu", self.readings, self.two)
        self.assertEqual(score.under_reading(task, "buyable", self.readings, self.two)["expect"],
                         self.readings["buyable"]["pv1-15"])
        self.assertIs(score.under_reading(task, None, self.readings, self.two), task)
        two = self.by["tee-count-stocked"]
        self.assertIs(score.under_reading(two, "menu", self.readings, self.two), two)
        self.assertEqual(score.under_reading(two, "buyable", self.readings, self.two)["expect"]["value"], 11)
        # A question with no key, and every caller that gives no two_readings, as before.
        decline = self.by["decline-taste"]
        self.assertIs(score.under_reading(decline, "menu", self.readings, self.two), decline)
        self.assertIs(score.under_reading(task, "menu", self.readings), task)

    def unscorable(self, parser: str, reading: str) -> list[str]:
        args = argparse.Namespace(box=True, box_exhaust=False, targeting=False, exhaustive=False,
                                  exhaustive_wording=None, confidence="off", reading=reading,
                                  parser=parser, page_reader="rendered", rate_plan="every")
        tasks = [self.by[task_id] for task_id in SLOTS]
        with mock.patch.object(suite, "results_page", return_value=larchmere_page()):
            return suite.unscorable(tasks, self.spec, args, self.readings, self.two)

    def test_unscorable_under_each_reading_and_parser(self):
        keyed_one = [t for t in SLOTS if t not in TWO and self.by[t]["expect"]["kind"] != "none"]
        self.assertEqual(len(keyed_one), 20)
        self.assertEqual(self.unscorable("rules", "menu"),
                         ["pv1-15 under the menu reading", "pv1-19 under the menu reading"])
        found = self.unscorable("model", "menu")
        self.assertEqual(sorted(entry.split()[0] for entry in found), sorted(keyed_one))
        self.assertTrue(all("the scripted reply if the model parser asks" in entry for entry in found
                            if entry.split()[0] not in ("pv1-15", "pv1-19")))
        for parser in ("rules", "model"):
            with self.subTest(parser=parser):
                self.assertEqual(self.unscorable(parser, "own"), [])
                self.assertEqual(self.unscorable(parser, "buyable"), [])
        # Without two_readings the check is what it was: menu is every question's own.
        args = argparse.Namespace(box=True, box_exhaust=False, targeting=False, exhaustive=False,
                                  exhaustive_wording=None, confidence="off", reading="menu",
                                  parser="model", page_reader="rendered", rate_plan="every")
        with mock.patch.object(suite, "results_page", return_value=larchmere_page()):
            self.assertEqual(suite.unscorable([self.by[t] for t in SLOTS], self.spec, args, self.readings), [])

    def test_a_run_told_menu_on_a_buyable_key_is_unscored(self):
        # Through the one scoring call (score v8, `score.score_run`), which suite.py's own
        # `score_run` gave way to, with the task file's keys.
        keys = score.keys_for(PILOT)
        self.assertEqual((keys.readings, keys.two_readings), (self.readings, self.two))
        task, right = self.by["pv1-15"], "11 listings can sell size M today."
        unscored = score.score_run(task, "menu", keys, right, True)
        self.assertEqual(unscored["verdict"], "unscored")
        self.assertEqual(score.score_run(task, "buyable", keys, right, True)["verdict"], "correct")
        # The menu question is scored under its own key, 17 listed.
        listed = self.by["tee-count-stocked"]
        self.assertEqual(score.score_run(listed, "menu", keys, "17 listings offer it.", True)["verdict"],
                         "correct")
        self.assertFalse(hasattr(suite, "score_run"))

    def test_a_batch_records_each_reply_and_a_voids_rerun_keeps_own(self):
        ran = run_suite("--tasks", str(PILOT), "--repeats", "1", "--box", "--reading", "own",
                        "--only", "pv1-15", "tee-count-stocked", "pv1-19", "tee-target-price",
                        page=larchmere_page(), answer="11 listings can sell size M today.")
        self.addCleanup(ran.owner.cleanup)
        self.assertEqual(ran.code, 0, ran.out)
        payload = json.loads((ran.batch / "suite.json").read_text())
        rows = {row["task"]: row for row in payload["rows"]}
        self.assertEqual(payload["reading"], "own")
        self.assertEqual({task: (row["reading"], row["reading_by"]) for task, row in rows.items()},
                         {"pv1-15": ("buyable", "user"), "tee-count-stocked": ("menu", "user"),
                          "pv1-19": ("buyable", "user"), "tee-target-price": (None, None)})
        self.assertEqual(rows["pv1-15"]["verdict"], "correct")
        self.assertIn("--reading own", voids.rerun_flags(ran.batch))

    def test_the_dry_run_says_each_reply(self):
        ran = run_suite("--tasks", str(PILOT), "--repeats", "1", "--box", "--reading", "own", "--dry-run",
                        "--rate-plan", "every", "--max-steps", "300", "--clock", "1800",
                        page=larchmere_page())
        self.addCleanup(ran.owner.cleanup)
        self.assertEqual(ran.code, 0, ran.out)
        said = dict(re.findall(r"^  (\S+)\s+gated=.*\nscripted reply under --reading own: (\w+), given", ran.out, re.M))
        self.assertEqual((said["pv1-15"], said["pv1-19"]), ("buyable", "buyable"))
        asked_two = {task: reply for task, reply in said.items() if task in TWO}
        self.assertEqual(set(asked_two.values()), {"menu"})
        self.assertEqual(sorted(asked_two), ["pv1-09", "pv1-14", "tee-all-stocked", "tee-count-stocked",
                                             "water-all-stocked"])
        # Under any other reading the dry run prints what it always printed.
        menu = run_suite("--tasks", str(PILOT), "--repeats", "1", "--box", "--reading", "buyable", "--dry-run",
                         "--only", "tee-count-stocked", page=larchmere_page())
        self.addCleanup(menu.owner.cleanup)
        self.assertNotIn("scripted reply", menu.out)

    def test_the_model_path_answers_its_own_ask_with_the_questions_reading(self):
        flag = {"quantifier": "count", "objective": "availability", "filters": [{"attribute": "size", "op": "=", "value": "M"}],
                "population": "results", "ambiguities": [{"word": "sell me", "readings": ["listed", "buyable"]}]}
        question = self.by["pv1-15"]["query"].format(base="http://localhost:7770")
        args = argparse.Namespace(box=True, box_exhaust=False, targeting=False, exhaustive=False,
                                  exhaustive_wording=None, confidence="off", reading="own", parser="model",
                                  page_reader="rendered", rate_plan="every", two_readings=self.two)
        with mock.patch.object(suite, "results_page", return_value=larchmere_page()):
            query, applied = suite.build_query(self.by["pv1-15"], self.spec, args, call=lambda prompt: json.dumps(flag))
        self.assertEqual((applied["box"]["parse"]["used"], applied["box"]["reading"], applied["box"]["reading_by"]),
                         ("model", "buyable", "user"))
        self.assertIn("so a sold-out size does not count", query)
        self.assertTrue(query.startswith(question))


if __name__ == "__main__":
    unittest.main()
