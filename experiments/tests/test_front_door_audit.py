"""The verifier's audit of box v13 (22 October 2026): two blockers and five findings, fixed
in box v14, form v11, normalisation v2, primitives v10 and score v4. Each has a case where
the fault the verifier reproduced fires and one where the check stays quiet, and each fault
named here was planted in the code, with a fresh bytecode cache (LESSONS 39), and seen to
fail its test before the code was put back (LESSONS 31).

The costs (finding 5) are tested beside the code they changed: a failed parse in
`test_model_parser.SuiteParser`, the verifier's cost line and section G in `test_checks`.

Every model reply is a stub, every agent run is the fake runner of `test_claim_arms`, and
nothing is sent anywhere.
"""
import dataclasses
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import arms  # noqa: E402
import box  # noqa: E402
import claim  # noqa: E402
import form  # noqa: E402
import normalise  # noqa: E402
import page  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import primitives  # noqa: E402
import replay_box  # noqa: E402
import score  # noqa: E402
import verify_cells  # noqa: E402
import voids  # noqa: E402
from form import Filter, Form  # noqa: E402
from test_box import BASE, synthetic_page, thornwood_page  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402
from test_model_parser import GO, NEGATED, every_question, f, named_page, reply, stub  # noqa: E402

THORNWOOD = "Go to http://localhost:7770/catalogsearch/result/?q=Thornwood . "


def model_batch(test: unittest.TestCase, *argv: str, replies, page_: page.Page, answer: str):
    """`suite.main()` with the parse faked: `replies(prompt)` gives each reply, charged
    $0.003. Returns the run, its folder kept until `test` ends, and its payload, None when
    nothing ran."""
    def call_model(key, model, prompt):
        return replies(prompt), 0.003

    with mock.patch.object(parse_probe, "call_model", call_model), \
            mock.patch.object(plan_probe, "load_key", return_value="fake-key"):
        run = run_suite(*argv, page=page_, answer=answer)
    test.addCleanup(run.owner.cleanup)
    payload = json.loads((run.batch / "suite.json").read_text()) if run.batch else None
    return run, payload


# ---------------------------------------------------------------------------
# 1. Blocker: a run is scored under the reading its own box record holds

OPTION = THORNWOOD + "How many Thornwood listings is size M an option on?"
# The model reads "an option" two ways, where the word list reads the question as clear.
FLAGGED = reply(quantifier="count", objective="availability", filters=[f("size", "=", "M")],
                ambiguities=[{"word": "an option", "readings": ["listed", "buyable"]}])
UNFLAGGED = reply(quantifier="count", objective="availability", filters=[f("size", "=", "M")])


def option_tasks(folder: pathlib.Path, buyable: int | None) -> pathlib.Path:
    """One count question whose own key, written under the menu reading as every own key
    is (`score.OWN_READING`), is 10, and with `buyable` a sidecar key of that figure for the
    buyable reading. Both figures are made up: these tests check which key is used."""
    tasks = folder / "tasks_option.json"
    tasks.write_text(json.dumps({"base_url": BASE, "tasks": [{
        "id": "option-count", "family": "apparel", "gated": True,
        "query": OPTION.replace(BASE, "{base}"), "expect": {"kind": "count", "value": 10}}]}))
    if buyable is not None:
        (folder / "readings_option.json").write_text(json.dumps(
            {"readings": {"buyable": {"option-count": {"kind": "count", "value": buyable}}}}))
    return tasks


class ScoredByTheRunsOwnRecord(unittest.TestCase):
    """Until score v4 the reading a run was scored under was chosen by the word list, so a
    model's ask on a question the word list reads as clear, answered as buyable, was scored
    under the menu key: a correct 7 marked wrong against the menu's 10 (verifier finding,
    `ver/score/drive.py`). Planted: `score.under_reading` keeping the task's own key when
    the sidecar has none and the word list finds no ask, as it did until then: the batch
    with no key ran, and the verifier's re-score of such a run was not unscored."""

    def setUp(self):
        self.folder = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.page = thornwood_page()
        self.assertIsNone(box.ambiguity.ask(OPTION))     # the word list reads it as clear

    def batch(self, *flags, replies=lambda prompt: FLAGGED, answer="7 listings can sell size M now."):
        tasks = self.folder / "tasks_option.json"
        return model_batch(self, "--tasks", str(tasks), "--repeats", "1", "--box", *flags,
                           replies=replies, page_=self.page, answer=answer)

    def test_a_models_ask_answered_as_buyable_is_scored_under_the_buyable_key(self):
        option_tasks(self.folder, buyable=7)
        run, payload = self.batch("--parser", "model", "--reading", "buyable")
        self.assertEqual((run.code, run.calls), (0, 1), run.out)
        row = payload["rows"][0]
        self.assertEqual((row["box"]["reading"], row["box"]["parse"]["used"], row["verdict"]),
                         ("buyable", "model", "correct"))
        # The verifier re-scores it the same way, from the row's box record.
        readings = score.readings_for(self.folder / "tasks_option.json")
        task = json.loads((self.folder / "tasks_option.json").read_text())["tasks"][0]
        self.assertEqual(verify_cells.rescore(task, row["answer"], True, row, payload, readings)["verdict"],
                         "correct")

    def test_with_no_key_for_that_reading_the_batch_is_refused_before_anything_runs(self):
        option_tasks(self.folder, buyable=None)
        run, payload = self.batch("--parser", "model", "--reading", "buyable")
        self.assertEqual((run.code, run.calls, payload), (2, 0, None))
        self.assertIn("option-count under the buyable reading, which the model parser can lead any "
                      "question it reads to", run.out)
        # Under the menu reading too: the box can take the buyable reading itself.
        run, _ = self.batch("--parser", "model", "--reading", "menu")
        self.assertEqual((run.code, run.calls), (2, 0))

    def test_a_run_the_box_took_no_reading_on_keeps_its_own_key_whatever_the_flag(self):
        # The batch flag is a reply only where the box asked. Here the model reads the
        # question as clear, so the run is scored under the task's own key, 10, though the
        # batch ran with --reading buyable. Planted: the suite scoring by the flag, this run
        # was scored under the buyable key and marked wrong.
        option_tasks(self.folder, buyable=7)
        run, payload = self.batch("--parser", "model", "--reading", "buyable",
                                  replies=lambda prompt: UNFLAGGED, answer="10 listings have size M.")
        row = payload["rows"][0]
        self.assertEqual((run.code, row["box"]["reading"], row["verdict"]), (0, None, "correct"))
        self.assertIsNone(verify_cells.run_reading(row, payload))
        self.assertEqual(payload["reading"], "buyable")

    def test_under_the_rules_the_clear_question_runs_on_its_own_key(self):
        option_tasks(self.folder, buyable=None)
        run, payload = self.batch(answer="10 listings have size M.")
        row = payload["rows"][0]
        self.assertEqual((run.code, run.calls, row["box"]["reading"], row["verdict"]), (0, 1, None, "correct"))

    def test_run_reading_reads_the_record_and_only_a_row_without_one_the_flags(self):
        self.assertEqual(verify_cells.run_reading({"box": {"reading": "buyable"}}, {"reading": "menu"}), "buyable")
        self.assertIsNone(verify_cells.run_reading({"box": {"reading": None}, "reading": "menu"}, {"reading": "menu"}))
        self.assertEqual(verify_cells.run_reading({"reading": "menu"}, {"reading": "buyable"}), "menu")
        self.assertEqual(verify_cells.run_reading({}, {"reading": "buyable"}), "buyable")
        task = {"id": "option-count", "expect": {"kind": "count", "value": 10}}
        got = verify_cells.rescore(task, "7 listings", True, {"box": {"reading": "buyable"}}, {}, {})
        self.assertEqual(got["verdict"], "unscored")
        self.assertIn("no answer key for this run: option-count was answered under the 'buyable' reading",
                      got["why"])


# ---------------------------------------------------------------------------
# 3. A model form that contradicts the question's words is not used

LIMIT = THORNWOOD + "Is there any Thornwood listing with size M available to buy for under $24?"
SIZE = THORNWOOD + "Who charges the least for a medium Thornwood tee?"
THREE = (THORNWOOD + "Which three sellers are cheapest for size M among listings that can "
         "actually supply it, and at what prices?")
CHEAPEST = (THORNWOOD + "Across the Thornwood listings, which seller is cheapest for size XL, and "
            "what is that price? Only count a listing that can sell it now.")
IN_STOCK = THORNWOOD + "How many of the Thornwood listings have size M in stock and available to buy right now?"
LACKS = THORNWOOD + "Is there a Thornwood seller that doesn't have size M?"
EVERY = THORNWOOD + "Does every Thornwood listing offer size M? Answer yes or no."
BUYABLE = f("availability", "=", "buyable")

# The verifier's cases (`ver/norm.py`, `ver/polarity.py`): each question, a form that
# contradicts it, the words the box gives for refusing it, and the form that reads it right.
CONTRADICTIONS = {
    "30 for under $24": (LIMIT, dict(quantifier="exists", filters=[f("size", "=", "M"), f("price", "<", 30), BUYABLE]),
                         "the form sets a price limit of 30, a figure the question does not state",
                         dict(quantifier="exists", filters=[f("size", "=", "M"), f("price", "<", 24), BUYABLE])),
    "<= for under": (LIMIT, dict(quantifier="exists", filters=[f("size", "=", "M"), f("price", "<=", 24), BUYABLE]),
                     "the question's 'under $24' gives price < 24.0, where the form says price <= 24",
                     dict(quantifier="exists", filters=[f("size", "=", "M"), f("price", "<", 24.0), BUYABLE])),
    "L for medium": (SIZE, dict(filters=[f("size", "=", "L")]),
                     "the form asks about size L, which the question does not name",
                     dict(filters=[f("size", "=", "medium")])),
    "five for three": (THREE, dict(quantifier="topk", k=5, filters=[f("size", "=", "M"), BUYABLE]),
                       "the form asks for the 5 cheapest, a number the question does not state",
                       dict(quantifier="topk", k=3, filters=[f("size", "=", "M"), BUYABLE])),
    "one for three": (THREE, dict(filters=[f("size", "=", "M"), BUYABLE]),
                      "the question's 'three sellers' asks for 3, where the form asks for none in particular",
                      dict(quantifier="topk", k=3, filters=[f("size", "=", "M"), BUYABLE])),
    "dearest for cheapest": (CHEAPEST, dict(quantifier="argmax", filters=[f("size", "=", "XL"), BUYABLE]),
                             "asks for the cheapest, where the form asks for the dearest",
                             dict(filters=[f("size", "=", "XL"), BUYABLE])),
    "listed for in stock": (IN_STOCK, dict(quantifier="count", objective="availability",
                                           filters=[f("size", "=", "M"), f("availability", "=", "listed")]),
                            "the question's 'in stock' gives availability = 'buyable', where the form says "
                            "availability = 'listed'",
                            dict(quantifier="count", objective="availability", filters=[f("size", "=", "M"), BUYABLE])),
    "a negation dropped": (LACKS, dict(quantifier="forall", objective="availability", filters=[f("size", "=", "M")]),
                           "the question's \"n't\" is a negation, which the form's universal drops",
                           dict(quantifier="forall", objective="availability", filters=[f("size", "=", "M")],
                                negated=True)),
    "a negation invented": (EVERY, dict(quantifier="forall", objective="availability", filters=[f("size", "=", "M")],
                                        negated=True),
                            "the form is negated, where the question does not ask whether some listing lacks",
                            dict(quantifier="forall", objective="availability", filters=[f("size", "=", "M")])),
}


class ConflictsWithTheQuestion(unittest.TestCase):
    def setUp(self):
        self.page = thornwood_page()

    def test_each_contradiction_falls_back_to_the_rules_and_the_right_reading_is_used(self):
        # Planted: `conflicts` left out of `normalise.problems`, every case came back used by
        # the model. And each of its checks removed alone, every case that check alone
        # catches came back used; "30 for under $24" is caught by two, the rules' limit and
        # the figure the question does not state, and came back only with both gone.
        for label, (question, wrong, words, right) in CONTRADICTIONS.items():
            with self.subTest(fault=label):
                decision = box.decide(question, self.page, parser="model", call=stub(reply(**wrong)))
                self.assertEqual(decision.parse.used, "rules")
                self.assertIn(words, decision.parse.fallback_reason)
                rules = box.decide(question, self.page)
                self.assertEqual((decision.kind, decision.query, decision.ask), (rules.kind, rules.query, rules.ask))
            with self.subTest(sound=label):
                decision = box.decide(question, self.page, parser="model", call=stub(reply(**right)))
                self.assertEqual(decision.parse.used, "model", decision.parse.fallback_reason)

    def test_the_rules_own_form_never_contradicts_its_question(self):
        # Quiet over every question the project holds, on three pages and with none: the
        # checks hold a model to what the rules already read from the words.
        for name, page_ in (("Thornwood", self.page), ("named", named_page()), ("no page", None)):
            for question in dict.fromkeys(every_question()):
                with self.subTest(page=name, question=question[-60:]):
                    self.assertEqual(normalise.conflicts(form.from_rules(question, page_), question, page_), [])

    def test_a_negation_is_read_where_the_question_asks(self):
        # "name any size that is not" says how to answer, and negates nothing the form holds.
        # Planted: the whole text read again, the plain universal was refused.
        question = ("On http://localhost:7770/igr-tee-a.html is every size currently in stock? "
                    "Answer yes or no, and name any size that is not.")
        universal = Form("forall", "availability", filters=(Filter("availability", "=", "buyable"),))
        self.assertEqual(normalise.conflicts(universal, question, None), [])
        self.assertEqual(normalise.asking(question), "On   is every size currently in stock?")
        asked = "Is there a listing that does not have size M? Answer yes or no."
        dropped = Form("forall", "availability", filters=(Filter("size", "=", "M"),))
        self.assertEqual(normalise.conflicts(dropped, asked, None),
                         ["the question's 'not' is a negation, which the form's universal drops"])
        # With no question mark the whole text is read.
        self.assertEqual(normalise.asking("Count the listings without size M."), "Count the listings without size M.")


# ---------------------------------------------------------------------------
# 4. Sellers the question names, and values that are not words

# On `named_page` "Quarry" is one seller's first word, Quarry Street Outfitters, and the
# first question below names another seller with it, Quarry Lane Traders, which the page
# does not list: the shape of the verifier's Rookwood case, with made-up names.
PAIR = GO + "Between Quarry Lane Traders and Mellow Fields, who is cheaper for size M?"
LISTED_PAIR = GO + "Between Quarry Street Outfitters and Mellow Fields, who is cheaper for size M?"


def lookup(*filters) -> str:
    return reply(quantifier="lookup", filters=list(filters))


class SellersTheQuestionNames(unittest.TestCase):
    def setUp(self):
        self.page = named_page()
        self.unlisted = ("Your question names Quarry Lane Traders, which the results page does not list "
                         "among its 4 listings. Which of them do you mean?")

    def test_a_shortened_seller_matched_to_another_seller_is_refused(self):
        # The verifier's Rookwood case: "Rookwood" was matched to Rookwood Outfitters where
        # the question named Rookwood Uniforms. Planted: the "named in full" check removed,
        # the model's form was used and the plan opened Quarry Street Outfitters.
        decision = box.decide(PAIR, self.page, parser="model",
                              call=stub(lookup(f("seller", "in", ["Quarry", "Mellow Fields"]), f("size", "=", "M"))))
        self.assertEqual(decision.parse.used, "rules")
        self.assertIn("the form names the seller 'Quarry Street Outfitters', which the question does not "
                      "name in full", decision.parse.fallback_reason)
        self.assertIn("seller: 'Quarry' is 'Quarry Street Outfitters', matched as whole words",
                      decision.parse.changes)
        # The rules then ask about the seller the page does not list, and plan nothing.
        self.assertEqual((decision.ask.text, decision.query), (self.unlisted, None))
        # Quiet: the same shortening where the question names that seller in full.
        decision = box.decide(LISTED_PAIR, self.page, parser="model",
                              call=stub(lookup(f("seller", "in", ["Quarry", "Mellow Fields"]), f("size", "=", "M"))))
        self.assertEqual((decision.parse.used, decision.kind, decision.ask), ("model", "named_lookup", None))
        self.assertEqual({c.seller for c in decision.plan.candidates}, {"Quarry Street Outfitters", "Mellow Fields"})

    def test_a_seller_or_url_the_page_does_not_list_is_asked_about_under_either_parser(self):
        # Until box v14 the plan sent such a seller as "not on the results page the box read:
        # find it in the results", which was false: the box reads the whole page. Planted:
        # `box.unlisted` returning nothing, the box raised from `primitives.lookup_text`
        # rather than ask.
        model = box.decide(PAIR, self.page, parser="model", call=stub(lookup(
            f("seller", "in", ["Quarry Lane Traders", "Mellow Fields"]), f("size", "=", "M"))))
        self.assertEqual((model.parse.used, model.ask.text, model.query), ("model", self.unlisted, None))
        self.assertEqual(model.ask.readings, {})
        rules = box.decide(PAIR, self.page)
        self.assertEqual((rules.ask.text, rules.query), (self.unlisted, None))
        url = f"{BASE}/example-jacket-09.html"
        linked = box.decide(GO + f"On {url}, can size M be bought now?", self.page, parser="model",
                            call=stub(reply(quantifier="lookup", objective="availability", population="listing",
                                            filters=[f("url", "in", [url]), f("size", "=", "M"), BUYABLE])))
        self.assertEqual(linked.ask.text, f"Your question names {url}, which the results page does not list "
                                          f"among its 4 listings. Which of them do you mean?")
        # Quiet: both on the page, planned with both.
        listed = box.decide(LISTED_PAIR, self.page)
        self.assertEqual((listed.ask, listed.kind), (None, "named_lookup"))
        self.assertEqual(box.unlisted(listed.form, LISTED_PAIR, self.page), [])

    def test_no_text_the_box_writes_sends_the_agent_to_find_a_listing(self):
        # Planted: `box.unlisted` returning nothing and the old line put back in
        # `primitives.lookup_text`, the pair questions on these pages sent it again.
        for question in dict.fromkeys(every_question() + [PAIR, LISTED_PAIR]):
            for page_ in (self.page, thornwood_page()):
                for reading in (None, "menu", "buyable"):
                    try:
                        decision = box.decide(question, page_, reply=reading)
                    except ValueError:
                        continue
                    with self.subTest(question=question[-50:], reading=reading):
                        self.assertNotIn("find it in the results", decision.query or "")
                        self.assertNotIn("not on the results page the box read", decision.query or "")
        # And a lookup of a listing the page does not list has no text at all.
        unlisted = Form("lookup", "price", filters=(Filter("seller", "in", ("Quarry Lane Traders",)),
                                                    Filter("size", "=", "M")))
        with self.assertRaisesRegex(ValueError, "a lookup names a listing the results page does not list"):
            primitives.compose(unlisted, self.page)

    def test_a_value_that_is_not_a_word_is_no_form(self):
        # The verifier's malformed replies (`ver/malformed.py`): each was read as a form, and
        # some planned a listing called "None" or "123". Planted: `Filter` without its value
        # check, five of them raised from the checks, the null and numeric sellers and URLs
        # and the nested seller; the other seven are refused by a check of their own too.
        both = f("seller", "in", ["Quarry Street Outfitters", "Mellow Fields"])
        for label, filters in {
                "a null seller": [f("seller", "in", [None, "Mellow Fields"]), f("size", "=", "M")],
                "a seller that is a number": [f("seller", "in", [123, "Mellow Fields"]), f("size", "=", "M")],
                "a seller that is a dict": [f("seller", "=", {"a": 1}), f("size", "=", "M")],
                "a seller in a list in a list": [f("seller", "in", [["Mellow Fields"]]), f("size", "=", "M")],
                "a size in a list in a list": [both, f("size", "in", [["M"]])],
                "a null size": [both, f("size", "=", None)],
                "a null url": [f("url", "in", [None]), f("size", "=", "M")],
                "a url that is a number": [f("url", "in", [7]), f("size", "=", "M")],
                "no sellers at all": [f("seller", "in", []), f("size", "=", "M")],
                "a price that is true": [both, f("size", "=", "M"), f("price", "<", True)],
                "a size that is a number": [both, f("size", "=", 5)],
                "a seller written as a number": [f("seller", "=", 12), f("size", "=", "M")]}.items():
            with self.subTest(fault=label):
                decision = box.decide(LISTED_PAIR, self.page, parser="model", call=stub(lookup(*filters)))
                self.assertEqual(decision.parse.used, "rules")
                self.assertIsNotNone(decision.parse.fallback_reason)
        # Quiet: words, and a number where a number belongs.
        sound = box.decide(LISTED_PAIR, self.page, parser="model", call=stub(lookup(both, f("size", "=", "M"))))
        self.assertEqual(sound.parse.used, "model")
        self.assertEqual(Filter("price", "<", 24).value, 24)
        self.assertEqual(Filter("seller", "in", ("Mellow Fields",)).value, ("Mellow Fields",))


# ---------------------------------------------------------------------------
# 6. The older scripts know the parser (LESSONS 29)

class OlderScriptsKnowTheParser(unittest.TestCase):
    def payload_folder(self, **payload) -> pathlib.Path:
        folder = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        (folder / "suite.json").write_text(json.dumps({"tasks_file": "tasks_claim_apparel.json", **payload}))
        return folder

    def test_a_rerun_line_carries_the_parser_and_its_model(self):
        # Planted: `rerun_flags` without the parser, a model batch's re-run line was a rules one.
        model = self.payload_folder(box=True, reading="menu", parser="model", parser_model="vendor/parser-x")
        # With the page reader each batch's own, by box v16's rule: none recorded is the fetch.
        self.assertEqual(voids.rerun_flags(model), "--tasks experiments/tasks/tasks_claim_apparel.json --repeats 1 "
                                                   "--box --reading menu --parser model --parser-model vendor/parser-x "
                                                   "--page-reader fetch")
        rules = self.payload_folder(box=True, reading="menu", parser="rules", parser_model=None)
        self.assertNotIn("--parser", voids.rerun_flags(rules))
        before = self.payload_folder(box=True)
        self.assertEqual(voids.rerun_flags(before), "--tasks experiments/tasks/tasks_claim_apparel.json --repeats 1 --box "
                                                    "--page-reader fetch")

    def test_a_batch_line_under_the_model_parser_is_its_own_arm(self):
        # Planted: `intended` without the parser, the model's line stood for the box's.
        line = "--tasks experiments/tasks/tasks_claim_apparel.json --repeats 1 {} --only apparel-all-stocked"
        self.assertEqual(claim.intended(line.format("--box --parser model --reading menu")),
                         ("box-model", "menu", [("apparel-all-stocked", 1)]))
        self.assertEqual(claim.intended(line.format("--box-exhaust --parser model"))[0], "box-exhaust-model")
        for flags in ("--box", "--box --parser rules", "--box --reading menu"):
            with self.subTest(flags=flags):
                self.assertEqual(claim.intended(line.format(flags))[0], "box")
        self.assertEqual(claim.intended(line.format("--exhaustive --parser model"))[0], "exhaustive")

    def test_the_site_names_a_box_batch_as_the_box(self):
        # 20261014T213118 is a box batch, which the site's batch table called "unmodified".
        # Planted: `arm_name` without its box case, the stored batch was "unmodified" again.
        stored = json.loads((paths.RESULTS / "20261014T213118" / "suite.json").read_text())
        self.assertEqual(arms.arm_name(stored), "box")
        self.assertEqual([arms.arm_name(p) for p in (
            {"box": True, "parser": "model"}, {"box_exhaust": True}, {"box_exhaust": True, "parser": "model"},
            {"arm": "box-model", "box": True, "parser": "model"})],
            ["box-model", "box-exhaust", "box-exhaust-model", "box-model"])
        # Quiet: every arm without the box is named as it was.
        self.assertEqual([arms.arm_name(p) for p in (
            {}, {"policy": "gate"}, {"exhaustive": True}, {"targeting": True}, {"confidence": "plain"})],
            ["unmodified", "gate", "exhaustive", "targeting v1", "confidence:plain"])

    def test_a_model_batch_is_replayed_from_its_stored_reply(self):
        # The model reads the negation, which the rules do not (they plan a survey), so a
        # replay by the rules would not decide the run as it was decided. Planted:
        # `parsed_by` returning {}, the run was decided differently today. Nothing is
        # called: the reply is the stored one.
        folder = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        tasks = folder / "tasks_negated.json"
        tasks.write_text(json.dumps({"base_url": BASE, "tasks": [{
            "id": "negated", "family": "apparel", "gated": True, "expect": {"kind": "none"},
            "query": NEGATED.replace(BASE, "{base}")}]}))
        negated = reply(quantifier="forall", objective="availability", filters=[f("size", "=", "M")],
                        negated=True, ambiguities=[{"word": "have", "readings": ["listed", "buyable"]}])
        run, payload = model_batch(self, "--tasks", str(tasks), "--repeats", "1", "--box", "--parser", "model",
                                   "--reading", "menu", replies=lambda prompt: negated,
                                   page_=synthetic_page([10.15, 11.15, 12.15]), answer="Yes. Seller B lacks it.")
        record = payload["rows"][0]["box"]
        self.assertEqual((run.code, record["parse"]["used"], record["kind"], record["parse"]["reply"]),
                         (0, "model", "negated_refutation", negated))
        self.assertEqual(box.decide(NEGATED, page.from_record(record["page"]), reply="menu").kind, "survey")
        with mock.patch.object(paths, "TASKS", folder), mock.patch.object(replay_box.paths, "TASKS", folder):
            rows = replay_box.replay(run.batch)
        self.assertEqual([(r["text_reproduced"], r["today"]) for r in rows], [(True, "same")])
        # Quiet: a record of the rules is replayed by the rules, as every batch before was.
        self.assertEqual(replay_box.parsed_by({"parse": {"parser": "rules"}}), {})
        self.assertEqual(replay_box.parsed_by({}), {})
        failed = replay_box.parsed_by({"parse": {"parser": "model", "reply": None}})
        with self.assertRaisesRegex(RuntimeError, "holds no reply"):
            failed["call"]("a prompt")


# ---------------------------------------------------------------------------
# 7. The probe compares the negation

class ProbeComparesTheNegation(unittest.TestCase):
    def test_a_negated_universal_is_not_the_plain_one(self):
        # "Is there a listing without M" is not "does every listing have M". Planted: `agree`
        # and `tiers` without `negated`, the two agreed in every tier.
        plain = Form("forall", "availability", filters=(Filter("size", "=", "M"),),
                     evidence={"filter:size": "size M"})
        turned = dataclasses.replace(plain, negated=True)
        self.assertFalse(parse_probe.agree(plain, turned))
        self.assertEqual(parse_probe.tiers(plain, turned),
                         {"quantifier": False, "objective": False, "population": False, "every field": False})
        # Quiet: each agrees with itself.
        for one in (plain, turned):
            self.assertTrue(parse_probe.agree(one, one))
            self.assertTrue(all(parse_probe.tiers(one, one).values()))
        self.assertEqual(parse_probe.COMPARISON_VERSION, 2)


if __name__ == "__main__":
    unittest.main()
