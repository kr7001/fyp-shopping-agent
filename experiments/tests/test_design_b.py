"""Box v19 for the second claim run's design B (24 October 2026, docs/content/claim2-handover.md,
section 5): decision 11, the word list against the model; why each ask was put; and at most one
ask a question.

Every model reply here is a stub, and nothing is sent. Every rule has a case where it fires and
one where it stays quiet, and each fault named in a comment was planted in the code with a fresh
bytecode cache (LESSONS 39) and seen to fail its test before the code was put back (LESSONS 31).
"""
import argparse
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import form  # noqa: E402
import normalise  # noqa: E402
import page  # noqa: E402
import suite  # noqa: E402
from test_box import thornwood_page  # noqa: E402
from test_model_parser import GO, every_question, f, named_page, reply, stub  # noqa: E402

THORNWOOD = "Go to http://localhost:7770/catalogsearch/result/?q=Thornwood . "
# The front door's pilot of 23 October 2026, whose one model miss was pv1-01 (LESSONS 44).
PILOT = paths.RESULTS / "20261023T112840" / "suite.json"
SIZE_M = f("size", "=", "M")
BUYABLE, LISTED = f("availability", "=", "buyable"), f("availability", "=", "listed")
# A count whose words settle the buying reading, a price question whose word list reads "lists"
# as the menu, a question with no availability word, and one that needs two asks.
COUNT_IN_STOCK = THORNWOOD + "How many of the Thornwood listings have size M in stock and available to buy right now?"
LISTS_LOWEST = THORNWOOD + "Which Thornwood seller lists the lowest price for size M among sellers who can ship it today?"
CHEAPEST_M = THORNWOOD + "Which seller is cheapest for size M among the Thornwood listings?"
CHEAP_OFFER = THORNWOOD + "Does every Thornwood listing offer a cheap tee in size M?"


def count(*filters) -> str:
    return reply(quantifier="count", objective="availability", filters=list(filters))


def pilot_row(task_id: str) -> tuple[str, page.Page, str]:
    """One run of the pilot: its question, the page its box read and the model's stored reply."""
    batch = json.loads(PILOT.read_text())
    spec = json.loads((paths.TASKS / batch["tasks_file"]).read_text())
    row = next(r for r in batch["rows"] if r["task"] == task_id)
    task = next(t for t in spec["tasks"] if t["id"] == task_id)
    return (task["query"].format(base=spec["base_url"]), page.from_record(row["box"]["page"]),
            row["box"]["parse"]["reply"])


# ---------------------------------------------------------------------------
# 1. Decision 11: the word list against the model

class Decision11(unittest.TestCase):
    def setUp(self):
        self.page = thornwood_page()

    def test_pv1_01_is_planned_on_the_models_form(self):
        # Planted: the clash read as a failure again (`normalise.read`), the rules' form was
        # used and refused, as on 23 October. And the advertised price's menu reading taken
        # as answerable (`normalise.reading_problems`), the box asked instead of planning.
        question, page_, stored = pilot_row("pv1-01")
        self.assertIsNotNone(box.decide(question, page_).refuse)
        decision = box.decide(question, page_, parser="model", call=stub(stored))
        self.assertEqual((decision.kind, decision.parse.used, decision.parse.fallback_reason, decision.refuse),
                         ("results_page", "model", None, None))
        # The menu reading of an advertised price asks for a sold-out size's price, so the box
        # takes the buying reading itself and asks nothing; it is written into the question.
        self.assertEqual((decision.ask, decision.ask_reason, decision.reading, decision.reading_by),
                         (None, None, "buyable", "box"))
        self.assertIn(ambiguity.READINGS["buyable"][1].format(phrase="listed"), decision.query)
        self.assertNotIn({"attribute": "availability", "op": "=", "value": "buyable"},
                         decision.record()["form"]["filters"])
        clash = decision.record()["clash"]
        self.assertEqual((clash["words"], clash["rules"], clash["model"], clash["line"]),
                         ("listed", "listed", None, "the question's 'listed' gives availability = 'listed', "
                                                    "and the form has no availability filter"))
        # Both forms as they stood at the clash, before any reading.
        self.assertIn({"attribute": "availability", "op": "=", "value": "listed"}, clash["rules_form"]["filters"])
        self.assertEqual((clash["model_form"]["objective"], clash["model_form"]["filters"]), ("advertised price", []))

    def test_a_clash_on_a_count_is_asked_in_the_word_lists_words(self):
        # Until box v19 a model form that dropped or turned over "in stock" fell back to the
        # rules' form (tests/test_front_door_audit.py, whose "listed for in stock" moved here).
        # Planted: the clash's ask reason left "ambiguous", the reason below failed.
        asked = ambiguity.availability_ask("in stock").text
        for label, filters in (("dropped", [SIZE_M]), ("turned over", [SIZE_M, LISTED])):
            with self.subTest(model=label):
                decision = box.decide(COUNT_IN_STOCK, self.page, parser="model", call=stub(count(*filters)))
                self.assertEqual((decision.query, decision.ask.text, decision.ask_reason, decision.parse.used),
                                 (None, asked, "clash", "model"))
                self.assertEqual((decision.clash["words"], decision.clash["rules"], decision.clash["model"]),
                                 ("in stock", "buyable", None if label == "dropped" else "listed"))
                for answer, value in (("menu", "listed"), ("buyable", "buyable")):
                    planned = box.decide(COUNT_IN_STOCK, self.page, reply=answer, parser="model",
                                         call=stub(count(*filters)))
                    self.assertEqual((planned.kind, planned.parse.used, planned.reading, planned.reading_by,
                                      planned.ask.text, planned.ask_reason),
                                     ("survey", "model", answer, "user", asked, "clash"))
                    self.assertEqual(planned.form.filter("availability").value, value)
        # The rules alone read "in stock" and ask nothing, as before.
        rules = box.decide(COUNT_IN_STOCK, self.page)
        self.assertEqual((rules.ask, rules.ask_reason, rules.clash, rules.kind), (None, None, None, "survey"))

    def test_a_price_question_takes_the_one_reading_the_shop_can_answer(self):
        # "lists" is the menu to the word list, so the rules refuse the price of a sold-out
        # size; the model reads buying, and the box takes it without asking.
        self.assertIsNotNone(box.decide(LISTS_LOWEST, self.page).refuse)
        decision = box.decide(LISTS_LOWEST, self.page, parser="model", call=stub(reply(filters=[SIZE_M, BUYABLE])))
        self.assertEqual((decision.kind, decision.parse.used, decision.ask, decision.ask_reason, decision.reading,
                          decision.reading_by), ("availability_bound", "model", None, None, "buyable", "box"))
        self.assertEqual((decision.clash["words"], decision.clash["rules"], decision.clash["model"]),
                         ("lists", "listed", "buyable"))

    def test_quiet_where_the_readers_agree_or_the_words_give_no_availability(self):
        # The model holds the word list's reading: no clash, nothing asked.
        same = box.decide(COUNT_IN_STOCK, self.page, parser="model", call=stub(count(SIZE_M, BUYABLE)))
        self.assertEqual((same.clash, same.ask, same.ask_reason, same.parse.used, same.kind),
                         (None, None, None, "model", "survey"))
        # No availability word in the question: the model's form is used as it is.
        none = box.decide(CHEAPEST_M, self.page, parser="model", call=stub(reply(filters=[SIZE_M])))
        self.assertEqual((none.clash, none.ask, none.reading, none.kind), (None, None, None, "total_bound"))
        # The rules' silent default, buying on an existence question, is not the question's words.
        under = THORNWOOD + "Is there any seller under $20 for size M?"
        quiet = box.decide(under, self.page, parser="model", call=stub(reply(
            quantifier="exists", filters=[SIZE_M, f("price", "<", 20)])))
        self.assertEqual((quiet.clash, quiet.parse.used, quiet.kind), (None, "model", "exists_price"))
        # The rules never clash with anything.
        for question in (COUNT_IN_STOCK, LISTS_LOWEST, CHEAPEST_M):
            self.assertIsNone(box.decide(question, self.page).clash)

    def test_a_clash_with_another_fault_falls_back_as_before(self):
        # The clash is no failure only when it is the one thing wrong; with another, its line
        # stays among the reasons and the rules decide, as under box v18.
        wrong = count(f("size", "=", "L"), LISTED)
        decision = box.decide(COUNT_IN_STOCK, self.page, parser="model", call=stub(wrong))
        self.assertEqual((decision.parse.used, decision.clash, decision.ask), ("rules", None, None))
        self.assertIn("the question's 'in stock' gives availability = 'buyable', where the form says "
                      "availability = 'listed'", decision.parse.fallback_reason)
        self.assertIn("the form asks about size L, which the question does not name", decision.parse.fallback_reason)
        read = normalise.read(COUNT_IN_STOCK, self.page, stub(wrong))
        self.assertEqual((read.clash, read.declines), (None, ()))
        alone = normalise.read(COUNT_IN_STOCK, self.page, stub(count(SIZE_M, LISTED)))
        self.assertEqual((alone.failure, alone.clash.words, alone.clash.rules, alone.clash.model),
                         (None, "in stock", "buyable", "listed"))
        # The line is the one `conflicts` writes, so a model form that drops the words' buying
        # never declines on it either (tests/test_model_decline.py, "ship ... the quickest").
        self.assertIn(alone.clash.line, normalise.conflicts(alone.form, COUNT_IN_STOCK, self.page))


# ---------------------------------------------------------------------------
# 2. Why each ask was put

class AskReason(unittest.TestCase):
    def setUp(self):
        self.page = thornwood_page()

    def test_every_ask_says_why(self):
        offer = THORNWOOD + "Does every Thornwood listing offer size M?"
        affordable = THORNWOOD + "Is there an affordable Thornwood tee in medium?"
        unlisted = GO + "Between Quarry Lane Traders and Mellow Fields, who is cheaper for size M?"
        other = reply(ambiguities=[{"word": "the price", "readings": ["the lowest", "each listing's"]}],
                      filters=[SIZE_M])
        # pv1-13's words, which no verb of the lexicon governs, so only the model flags them.
        find = THORNWOOD + "In how many of the Thornwood listings can you find size M?"
        self.assertIsNone(ambiguity.ask(find))
        flagged = reply(quantifier="count", objective="availability", filters=[SIZE_M],
                        ambiguities=[{"word": "can you find", "readings": ["listed", "buyable"]}])
        cases = (("the word list's reading ask", box.decide(offer, self.page)),
                 ("a price word with no figure", box.decide(affordable, self.page)),
                 ("a seller the page does not list", box.decide(unlisted, named_page())),
                 ("the model's other reading", box.decide(THORNWOOD + "What is the price of the Thornwood tee in size M?",
                                                          self.page, parser="model", call=stub(other))),
                 ("the model's own flag", box.decide(find, self.page, parser="model", call=stub(flagged))))
        for label, decision in cases:
            with self.subTest(ask=label):
                self.assertIsNotNone(decision.ask)
                self.assertEqual(decision.ask_reason, "ambiguous")
                self.assertEqual(decision.record()["ask_reason"], "ambiguous")
        # No ask, no reason: a plan, a reading the box took itself, a refusal.
        for label, decision in (
                ("a plan", box.decide(CHEAPEST_M, self.page)),
                ("a reading the box took", box.decide(LISTS_LOWEST, self.page, parser="model",
                                                      call=stub(reply(filters=[SIZE_M, BUYABLE])))),
                ("a refusal", box.decide(THORNWOOD + "Which seller delivers fastest?", self.page))):
            with self.subTest(outcome=label):
                self.assertEqual((decision.ask, decision.ask_reason, decision.record()["ask_reason"]),
                                 (None, None, None))
        self.assertEqual(box.ASK_REASONS, ("ambiguous", "clash"))

    def test_an_ask_without_its_reason_is_refused(self):
        # Planted: the check in `Decision.__post_init__` removed, each of these was built.
        asked = ambiguity.availability_ask("offer")
        for label, fields in (("an ask with no reason", dict(ask=asked)),
                              ("a reason with no ask", dict(ask_reason="clash")),
                              ("a reason not on the list", dict(ask=asked, ask_reason="unclear"))):
            with self.subTest(fault=label), self.assertRaises(ValueError):
                box.Decision(question="q", kind=None, reading=None, query=None, plan=None, page=None,
                             **{"ask": None, **fields})


# ---------------------------------------------------------------------------
# 3. At most one ask a question

class AskCap(unittest.TestCase):
    def setUp(self):
        self.page = thornwood_page()

    def test_a_question_that_needs_two_asks_is_asked_once(self):
        # "offer" asks for a reading and "cheap" for a limit. Until box v19 a reply to the first
        # was followed by the second; now the one no reading answers is asked, alone.
        # Planted: the early ask taken out of `decide_by_rules`, the reply was followed by it.
        threshold = ambiguity.threshold_ask("cheap").text
        model = reply(quantifier="forall", objective="availability", filters=[SIZE_M], unknowns=["price limit"],
                      evidence={"unknowns": "cheap"}, ambiguities=[{"word": "offer", "readings": ["listed", "buyable"]}])
        for parser, extra in (("rules", {}), ("model", {"parser": "model", "call": stub(model)})):
            for answer in (None, "menu", "buyable"):
                with self.subTest(parser=parser, reply=answer):
                    decision = box.decide(CHEAP_OFFER, self.page, reply=answer, **extra)
                    self.assertEqual((decision.ask.text, decision.ask_reason, decision.reading,
                                      decision.reading_by, decision.query),
                                     (threshold, "ambiguous", None, None, None))

    def test_no_decision_follows_a_reply_with_another_ask(self):
        # Over every question the project holds, with every reply: a reading the user gave is
        # the answer to the decision's own ask, and an ask no reading answers has no reply.
        questions = list(dict.fromkeys(every_question()))
        self.assertGreaterEqual(len(questions), 91)     # 91 distinct on 24 October 2026
        for question in questions:
            page_ = self.page if box.results_url(question, required=False) else None
            for answer in (None, "menu", "buyable"):
                try:
                    decision = box.decide(question, page_, reply=answer)
                except ValueError:
                    continue    # a plan the box refuses to compose, as before
                with self.subTest(question=question[-60:], reply=answer):
                    if decision.reading_by == "user":
                        self.assertIn(decision.reading, decision.ask.readings)
                    if decision.ask is not None and not decision.ask.readings:
                        self.assertIsNone(decision.reading)
                    self.assertEqual(decision.ask is None, decision.ask_reason is None)

    def test_an_ask_left_unanswered_closes_the_slot_and_is_reported(self):
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        task = next(t for t in spec["tasks"] if t["id"] == "apparel-all-stocked")
        page_ = thornwood_page()
        url = box.results_url(task["query"].format(base=spec["base_url"]))
        suite.PAGES[url] = page_
        self.addCleanup(suite.PAGES.pop, url, None)
        args = argparse.Namespace(box=True, reading=None, targeting=False, exhaustive=False, confidence="off")
        query, applied = suite.build_query(task, spec, args)
        self.assertIsNone(query)
        row = suite.asked_row(task, 1, applied["box"])
        self.assertEqual((row["verdict"], row["answer"], row["box"]["ask_reason"], row["cost_usd"]),
                         ("asked", applied["box"]["ask"], "ambiguous", 0))
        self.assertEqual(suite.box_counts([row])["asked"], 1)
        # With the scripted reply the same slot runs, asked once.
        args.reading = "menu"
        query, applied = suite.build_query(task, spec, args)
        self.assertIsNotNone(query)
        self.assertEqual((applied["box"]["asked"], applied["box"]["reading_by"], applied["box"]["ask_reason"]),
                         (True, "user", "ambiguous"))


if __name__ == "__main__":
    unittest.main()
