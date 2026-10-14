"""The box: the question classifier, the planner, the ambiguity lexicon, the decision, the
page-derived refusal check, and the suite's one query builder.

The box may use only what the agent could see, the question and the pages. These tests pin
how every clothing question is classified, controls included (LESSONS 18), check that the
code which runs before the agent never reads an answer key, and keep the two answer checks
that do read one from being taken for part of the box. Every rule has a case where it must
fire and one where it must stay quiet (LESSONS 24 and 31).
"""
import argparse
import ast
import contextlib
import hashlib
import io
import json
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import compare_cells  # noqa: E402
import form as form_module  # noqa: E402
import page  # noqa: E402
import planner  # noqa: E402
import policy  # noqa: E402
import primitives  # noqa: E402
import score  # noqa: E402
import sufficiency  # noqa: E402
import suite  # noqa: E402
import targeting  # noqa: E402

BASE = "http://localhost:7770"
RESULTS_URL = f"{BASE}/catalogsearch/result/?q=Example"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
# The box v1 pilot, the one stored batch whose rows carry the page the box read.
PILOT = paths.RESULTS / "20261014T084322" / "suite.json"


def clothing_questions() -> dict[str, str]:
    spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
    return {t["id"]: t["query"].format(base=BASE) for t in spec["tasks"]}


def synthetic_page(prices: list[float]) -> page.Page:
    """A results page of made-up listings, one per price, in the order given. The sellers
    and prices belong to no generated market, which `Decide` checks."""
    listings = [page.Listing(seller=f"Seller {chr(65 + n)}", title=f"Example Tee - Seller {chr(65 + n)}",
                             url=f"{BASE}/example-tee-{n + 1:02d}.html", advertised=price)
                for n, price in enumerate(prices)]
    return page.Page(url=RESULTS_URL, listings=listings, total=len(listings), next_page=False)


class Classifier(unittest.TestCase):
    EXPECTED = {
        "apparel-headline": "results_page",          # the control: answered on the results page
        "apparel-target-price": "availability_bound",
        "apparel-cheapest-target": "availability_bound",
        "apparel-all-stocked": "refutation",
        "apparel-count-stocked": "survey",
        "apparel-count-buyable": "survey",
    }

    def test_every_clothing_question(self):
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        self.assertEqual({t["id"] for t in spec["tasks"]}, set(self.EXPECTED))
        for task in spec["tasks"]:
            with self.subTest(task=task["id"]):
                self.assertEqual(targeting.classify(task["query"].format(base=BASE)),
                                 self.EXPECTED[task["id"]])


class Planner(unittest.TestCase):
    def test_regression_passes(self):
        # Every question in every task file: the plan renders the same text the strategy
        # table does, and every plan passes its own soundness check.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(planner.regression(), 0)

    def test_an_unsound_plan_is_caught(self):
        plan = planner.plan("Across the Thornwood listings, which seller is cheapest for size M?")
        self.assertEqual(planner.verify(plan), [])
        # Each break is a failure already paid for: pruning a market never listed, and a
        # bound's arithmetic reported as a price.
        for label, broken in (("not enumerated", {**plan, "enumerate_first": False}),
                              ("bound reportable", {**plan, "forbidden_claims": []})):
            with self.subTest(broken=label):
                self.assertNotEqual(planner.verify(broken), [])


class Bodies(unittest.TestCase):
    """The box sends the strategy without its enumeration step, and the strategy table the
    recorded runs received is built from the same bodies, so neither can drift."""

    def test_strategies_are_the_bodies_with_the_enumeration_step_where_it_belongs(self):
        self.assertEqual(set(targeting.BODIES), set(targeting.STRATEGIES))
        self.assertEqual(set(targeting.ENUMERATED),
                         {"total_bound", "refutation", "rate_bound", "availability_bound", "survey"})
        for kind, text in targeting.STRATEGIES.items():
            with self.subTest(kind=kind):
                if kind in targeting.ENUMERATED:
                    self.assertEqual(text, targeting.ENUMERATE + targeting.BODIES[kind])
                else:
                    self.assertEqual(text, targeting.BODIES[kind])
                self.assertNotIn(targeting.ENUMERATE, targeting.BODIES[kind])


class Ambiguity(unittest.TestCase):
    """LESSONS 16: the two readings of "offer" are caught before anything is spent."""

    ASK = ("Your question says 'offer'. On this shop a size can be in a listing's menu but "
           "sold out. Do you mean listings whose menu lists the size, sold out or not, or "
           "listings that can sell it now?")

    def test_asks_on_the_two_offer_questions_and_on_none_of_the_four_clear_ones(self):
        asking = sorted(task_id for task_id, q in clothing_questions().items() if ambiguity.ask(q))
        self.assertEqual(asking, ["apparel-all-stocked", "apparel-count-stocked"])

    def test_the_verb_and_the_users_own_phrase_are_quoted_back(self):
        asked = ambiguity.ask(clothing_questions()["apparel-count-stocked"])
        self.assertEqual(asked.verb, "offer")
        self.assertEqual(asked.text, self.ASK)
        self.assertEqual(sorted(asked.readings), ["buyable", "menu"])
        self.assertEqual(asked.readings["menu"].sentence,
                         "By 'offer size M' I mean listings whose size menu includes it, "
                         "whether or not it is sold out.")
        self.assertEqual(asked.readings["buyable"].sentence,
                         "By 'offer size M' I mean listings that can sell it now, so a "
                         "sold-out size does not count.")

    def test_seller_is_not_sell(self):
        self.assertIsNone(ambiguity.ask("Across all the listings, which seller is cheapest for "
                                        "the 2 x 9.5L pack, and what is that price?"))

    def test_a_question_without_a_variant_word_is_clear(self):
        self.assertIsNone(ambiguity.ask("Do any buyers report that this product leaks or "
                                        "arrives leaking?"))
        # An ambiguous verb with nothing it could be ambiguous about.
        self.assertIsNone(ambiguity.ask("Does every listing have reviews?"))

    def test_carry_the_pack_asks(self):
        asked = ambiguity.ask("Does every listing carry the 500 g pack?")
        self.assertEqual(asked.verb, "carry")
        self.assertTrue(asked.readings["buyable"].sentence.startswith("By 'carry the 500 g pack' I mean"))

    def test_in_stock_settles_it(self):
        self.assertIsNone(ambiguity.ask("Is size M in stock?"))

    def test_the_verb_must_govern_the_variant(self):
        # Found 14 Oct 2026: "offers" here takes a price, and the second draft asked on it.
        self.assertIsNone(ambiguity.ask("Across all their pack sizes, which seller offers "
                                        "the lowest price?"))
        self.assertIsNone(ambiguity.ask("Across all the Rivenhall listings and all their pack "
                                        "sizes, which seller offers the lowest price per litre?"))
        # The variant word must follow the verb within WINDOW words. Punctuation ends it.
        self.assertIsNone(ambiguity.ask("Do they offer, for anyone who asks and wants one in "
                                        "a hurry, size M?"))
        self.assertIsNone(ambiguity.ask("Do they offer to anyone who asks and wants one "
                                        "size M?"))                       # seven words between
        asked = ambiguity.ask("Do they offer anyone who asks and wants one size M?")  # six
        self.assertEqual((asked.verb, asked.readings["menu"].sentence.split("'")[1]),
                         ("offer", "offer anyone who asks and wants one size M"))
        asked = ambiguity.ask("Does every Rivenhall listing stock the 2 x 9.5L pack?")
        self.assertEqual((asked.verb, asked.readings["menu"].sentence.split("'")[1]),
                         ("stock", "stock the 2 x 9.5L pack"))
        # The governing verb is the one quoted, not the first verb in the question.
        asked = ambiguity.ask("Listings that have reviews: does every one offer size M?")
        self.assertEqual(asked.verb, "offer")

    def test_every_clear_phrase_silences_an_ask(self):
        base = "Does every listing offer size M"
        self.assertIsNotNone(ambiguity.ask(base + "?"))
        for phrase in ambiguity.BUYABLE + ambiguity.MENU:
            with self.subTest(phrase=phrase):
                self.assertIsNone(ambiguity.ask(f"{base}, {phrase}?"))

    def test_every_verb_and_variant_word_fires_and_only_as_a_whole_word(self):
        for verb in ambiguity.VERBS:
            with self.subTest(verb=verb):
                self.assertEqual(ambiguity.ask(f"Does every listing {verb} size M?").verb, verb)
        for variant in ambiguity.VARIANTS:
            with self.subTest(variant=variant):
                self.assertIsNotNone(ambiguity.ask(f"Does every listing offer the {variant}?"))
        # A verb or variant word inside a longer word is not one.
        self.assertIsNone(ambiguity.ask("Is the offering sizeable?"))
        self.assertIsNone(ambiguity.ask("Which seller is cheapest for the pack?"))

    def test_with_reading_appends_the_sentence_and_refuses_an_unknown_one(self):
        q = "Does every listing offer size M?"
        asked = ambiguity.ask(q)
        self.assertEqual(ambiguity.with_reading(q, asked, "menu"),
                         q + " " + asked.readings["menu"].sentence)
        with self.assertRaises(ValueError):
            ambiguity.with_reading(q, asked, "maybe")

    def test_over_every_question_the_project_asks(self):
        # Controls included (LESSONS 18). The two clothing "offer size M" questions and the
        # two water "stock the 2 x 9.5L pack" questions ask. The other 33 do not, the two
        # "which seller offers the lowest price per litre" questions among them.
        asking, total = [], 0
        for name in ("tasks.json", "tasks_scaled.json", "tasks_heldout.json",
                     "tasks_apparel.json", "tasks_reviews.json"):
            spec = json.loads((paths.TASKS / name).read_text())
            total += len(spec["tasks"])
            asking += [(name, t["id"]) for t in spec["tasks"] if ambiguity.ask(t["query"])]
        self.assertEqual(total, 37)
        self.assertEqual(asking, [("tasks_scaled.json", "scaled-all-stocked"),
                                  ("tasks_heldout.json", "scaled-all-stocked"),
                                  ("tasks_apparel.json", "apparel-all-stocked"),
                                  ("tasks_apparel.json", "apparel-count-stocked")])


class Decide(unittest.TestCase):
    AMBIGUOUS = {"apparel-all-stocked", "apparel-count-stocked"}

    def setUp(self):
        self.questions = clothing_questions()
        self.page = synthetic_page([31.40, 12.25, 19.50])

    def test_the_synthetic_market_is_nobodys(self):
        sellers, prices = market_facts()
        for item in self.page.listings:
            self.assertNotIn(item.seller, sellers)
            self.assertNotIn(f"{item.advertised:.2f}", prices)

    def test_clear_questions_plan_and_ambiguous_ones_ask(self):
        for task_id, q in self.questions.items():
            with self.subTest(task=task_id):
                decision = box.decide(q, self.page)
                if task_id in self.AMBIGUOUS:
                    self.assertIsNone(decision.query)
                    self.assertIsNone(decision.kind)
                    self.assertIsNone(decision.plan)
                    self.assertEqual(decision.ask.text, Ambiguity.ASK)
                    self.assertEqual(decision.record()["asked"], True)
                    self.assertEqual(decision.record()["query"], None)
                else:
                    self.assertEqual(decision.kind, targeting.classify(q))
                    self.assertIsNone(decision.ask)
                    self.assertEqual(form_module.verify(decision.form, self.page), [])
                    self.assertEqual(decision.plan.kind, decision.kind)
                    self.assertTrue(decision.query.startswith(q + "\n\n"))
                    self.assertEqual(decision.record()["asked"], False)
                    self.assertIsNone(decision.refuse)

    def test_a_reply_plans_the_ambiguous_questions_under_that_reading(self):
        for task_id in self.AMBIGUOUS:
            q = self.questions[task_id]
            for reply in ("menu", "buyable"):
                with self.subTest(task=task_id, reply=reply):
                    decision = box.decide(q, self.page, reply=reply)
                    # The reading sentence changes nothing the classifier reads.
                    self.assertEqual(decision.kind, targeting.classify(q))
                    self.assertEqual(decision.reading, reply)
                    sentence = decision.ask.readings[reply].sentence
                    self.assertTrue(decision.query.startswith(f"{q} {sentence}\n\n"))
                    record = decision.record()
                    self.assertEqual((record["asked"], record["reading"], record["query"]),
                                     (True, reply, decision.query))

    def test_the_query_states_the_market_and_lists_sellers_by_advertised_price(self):
        q = self.questions["apparel-cheapest-target"]
        decision = box.decide(q, self.page)
        self.assertIn("The results page lists 3 listings on one page; there is no next page.",
                      decision.query)
        self.assertIn("Listings by advertised price, read from the results page:\n"
                      "1. Seller B, advertised $12.25, http://localhost:7770/example-tee-02.html\n"
                      "2. Seller C, advertised $19.50, http://localhost:7770/example-tee-03.html\n"
                      "3. Seller A, advertised $31.40, http://localhost:7770/example-tee-01.html",
                      decision.query)
        # The question, a blank line, the preamble, a blank line, the body: the v7 text
        # without the enumeration step the box has already done.
        self.assertEqual(decision.query,
                         f"{q}\n\n{box.preamble(self.page)}\n\n{targeting.BODIES[decision.kind]}")
        self.assertNotIn(targeting.ENUMERATE, decision.query)

    def test_a_next_page_is_told_to_the_agent(self):
        paged = page.Page(url=RESULTS_URL, listings=self.page.listings, total=40, next_page=True)
        decision = box.decide(self.questions["apparel-headline"], paged)
        self.assertIn("The results page lists 3 listings on one page; there is a next page, "
                      "open it too before deciding.", decision.query)
        self.assertNotIn("there is no next page", decision.query)

    def test_an_unknown_reply_raises(self):
        with self.assertRaises(ValueError):
            box.decide(self.questions["apparel-all-stocked"], self.page, reply="maybe")

    def test_a_reply_to_a_clear_question_is_ignored(self):
        q = self.questions["apparel-headline"]
        decision = box.decide(q, self.page, reply="buyable")
        self.assertIsNone(decision.ask)
        self.assertIsNone(decision.reading)
        self.assertEqual(decision.query, box.decide(q, self.page).query)

    def test_the_record_carries_the_versions_the_page_the_form_and_the_plan(self):
        decision = box.decide(self.questions["apparel-target-price"], self.page)
        record = decision.record()
        self.assertEqual((record["box_version"], record["form_version"], record["primitives_version"]),
                         (box.VERSION, form_module.VERSION, primitives.VERSION))
        self.assertEqual(record["page"], self.page.record())
        self.assertEqual(record["kind"], "availability_bound")
        self.assertEqual(record["form"], decision.form.record())
        self.assertEqual((record["form"]["kind"], record["form"]["quantifier"], record["form"]["source"]),
                         ("availability_bound", "argmin", "rules"))
        self.assertEqual(record["plan"], decision.plan.record())
        self.assertEqual(record["plan"]["primitive"], "bound_prune")
        self.assertIsNone(record["refuse"])
        # The plan the form composes to is the planner's, at the planner's versions.
        plan = form_module.plan_dict(decision.form)
        self.assertEqual((plan["planner_version"], plan["strategy_version"]),
                         (planner.VERSION, targeting.VERSION))

    def test_results_url_is_the_first_url_in_the_question(self):
        self.assertEqual(box.results_url(self.questions["apparel-headline"]),
                         f"{BASE}/catalogsearch/result/?q=Thornwood")
        self.assertEqual(box.results_url(f"See {BASE}/a.html."), f"{BASE}/a.html")
        with self.assertRaises(ValueError):
            box.results_url("Which seller is cheapest for size M?")
        self.assertIsNone(box.results_url("Which seller is cheapest for size M?", required=False))


UNRELATED = ("What is the weather in Singapore today?",
             "Write a short poem about shoes.",
             "Who founded the Thornwood brand and when?")


class Bypass(unittest.TestCase):
    """A question with no shopping shape and no shopping signal goes to the agent unchanged,
    and the record says so (14 Oct 2026, at the student's request). A shopping question the
    rules can only survey runs and is recorded as a fallback. One about an attribute the
    shop lacks keeps its refusal. The six clothing questions are none of these."""

    def setUp(self):
        self.page = synthetic_page([31.40, 12.25, 19.50])

    def test_an_unrelated_question_bypasses_the_box(self):
        for question in UNRELATED:
            for page_ in (None, self.page):
                with self.subTest(question=question, page=page_ is not None):
                    decision = box.decide(question, page_)
                    self.assertTrue(decision.bypass)
                    self.assertEqual((decision.query, decision.kind, decision.plan, decision.ask,
                                      decision.refuse), (question, None, None, None, None))
                    record = decision.record()
                    self.assertEqual((record["bypassed"], record["bypass_reason"], record["fallback"],
                                      record["query"], record["asked"], record["refuse"], record["plan"]),
                                     (True, "no shopping shape recognised", False, question, False,
                                      None, None))
                    self.assertEqual(record["page"], None if page_ is None else page_.record())
                    self.assertEqual(record["form"]["quantifier"], "unknown")

    def test_a_shopping_question_with_no_shape_runs_as_a_recorded_fallback(self):
        question = f"Go to {RESULTS_URL} . Tell me about the Thornwood tee listings."
        decision = box.decide(question, self.page)
        self.assertFalse(decision.bypass)
        self.assertEqual((decision.kind, decision.plan.primitive), ("survey", "exhaust"))
        self.assertTrue(decision.query.startswith(question + "\n\n" + box.preamble(self.page)))
        self.assertEqual((decision.record()["bypassed"], decision.record()["fallback"]), (False, True))

    def test_a_pushed_back_question_keeps_its_refusal(self):
        decision = box.decide(f"Go to {RESULTS_URL} . Which seller delivers fastest?", self.page)
        self.assertFalse(decision.bypass)
        self.assertTrue(decision.refuse.startswith("The shop does not show delivery time"))
        self.assertIsNone(decision.query)

    def test_a_shopping_question_with_no_page_is_an_error_not_a_bypass(self):
        with self.assertRaises(ValueError):
            box.decide("Which seller is cheapest for size M?", None)

    def test_who_sells_is_a_fallback_not_a_bypass(self):
        # Verifier finding, 14 Oct 2026: "sells" was not a market word, so this bypassed.
        decision = box.decide("Who sells the softest tee?", self.page)
        self.assertFalse(decision.bypass)
        self.assertEqual((decision.kind, decision.record()["fallback"]), ("survey", True))
        self.assertIn("a market word: sells", decision.form.evidence["fallback"])
        for question in UNRELATED:
            with self.subTest(question=question):
                self.assertTrue(box.decide(question, self.page).bypass)

    def test_the_clothing_questions_and_the_census_are_neither(self):
        for task_id, question in clothing_questions().items():
            with self.subTest(task=task_id):
                record = box.decide(question, self.page, reply="menu").record()
                self.assertEqual((record["bypassed"], record["fallback"]), (False, False))
        for _, question in planner.questions():
            with self.subTest(question=question[:60]):
                # The ambiguous water questions come back as asks, which is not a bypass.
                decision = box.decide(question, self.page)
                self.assertFalse(decision.bypass)
                self.assertFalse(decision.record()["bypassed"])


class V1Bytes(unittest.TestCase):
    """The six clothing questions render byte for byte what box v1 rendered, frozen in
    `fixtures/v1_clothing_queries.json` from the v1 code before box.py changed, under no
    reading and under each scripted reading. So the pilot measured under v1 is a
    measurement of the text v2 sends."""

    def test_every_frozen_entry_is_reproduced(self):
        frozen = json.loads((FIXTURES / "v1_clothing_queries.json").read_text())
        self.assertIn("box.VERSION 1", " ".join(frozen["_about"]))
        questions = clothing_questions()
        page_ = synthetic_page([31.40, 12.25, 19.50])
        self.assertEqual(len(frozen["queries"]), 18)
        self.assertEqual({row["task"] for row in frozen["queries"]}, set(questions))
        for row in frozen["queries"]:
            with self.subTest(task=row["task"], reading=row["reading"]):
                decision = box.decide(questions[row["task"]], page_, reply=row["reading"])
                self.assertEqual(decision.query, row["query"])
                self.assertEqual(decision.ask.text if decision.ask else None, row["ask"])

    def test_the_fixture_is_the_v1_text_and_not_a_copy_of_v2s(self):
        # The entries are the question, the preamble and the v7 body, nothing else.
        frozen = json.loads((FIXTURES / "v1_clothing_queries.json").read_text())
        page_ = synthetic_page([31.40, 12.25, 19.50])
        for row in frozen["queries"]:
            if row["query"] is None:
                continue
            with self.subTest(task=row["task"], reading=row["reading"]):
                body = row["query"].split(f"\n\n{box.preamble(page_)}\n\n", 1)[1]
                self.assertIn(body, targeting.BODIES.values())


class NumericalAsk(unittest.TestCase):
    """Box v2: a price word with no figure asks for the threshold, and nothing is planned."""

    def setUp(self):
        self.page = synthetic_page([31.40, 12.25, 19.50])
        self.go = f"Go to {RESULTS_URL} . "

    def test_a_cheap_tee_asks_for_a_limit(self):
        decision = box.decide(self.go + "Which seller has a cheap tee in M?", self.page)
        self.assertIsNotNone(decision.ask)
        self.assertEqual(decision.ask.verb, "cheap")
        self.assertEqual(decision.ask.readings, {})
        self.assertIn("gives no figure", decision.ask.text)
        self.assertEqual((decision.query, decision.plan, decision.kind), (None, None, None))
        record = decision.record()
        self.assertEqual((record["asked"], record["query"], record["form"]["unknowns"]),
                         (True, None, ["price limit"]))
        # A scripted reading cannot answer a threshold, so the ask stands.
        self.assertIsNone(box.decide(self.go + "Which seller has a cheap tee in M?", self.page,
                                     reply="menu").query)

    def test_a_figure_settles_it(self):
        for question in (self.go + "Is there any seller under $20 for size M?",
                         self.go + "Which seller is cheapest for size M?"):
            with self.subTest(question=question):
                decision = box.decide(question, self.page)
                self.assertIsNone(decision.ask)
                self.assertIsNotNone(decision.query)


class Refusal(unittest.TestCase):
    """Box v2: a question needing an attribute the shop does not show gets no plan and no
    agent run. The box says what is missing."""

    def setUp(self):
        self.page = synthetic_page([31.40, 12.25, 19.50])
        self.go = f"Go to {RESULTS_URL} . "

    def test_delivery_and_shipping_are_refused(self):
        for question, missing in ((self.go + "Which seller delivers fastest?", "delivery time"),
                                  (self.go + "Which seller is cheapest for size M with free shipping?",
                                   "shipping cost")):
            with self.subTest(question=question):
                decision = box.decide(question, self.page)
                self.assertTrue(decision.refuse.startswith(f"The shop does not show {missing}"))
                self.assertEqual((decision.query, decision.plan, decision.kind, decision.ask),
                                 (None, None, None, None))
                record = decision.record()
                self.assertEqual((record["refuse"], record["asked"], record["query"]),
                                 (decision.refuse, False, None))
                self.assertIsNotNone(record["form"])

    def test_a_question_the_shop_can_answer_is_not_refused(self):
        for q in clothing_questions().values():
            with self.subTest(question=q[:60]):
                decision = box.decide(q, self.page, reply="menu")
                self.assertIsNone(decision.refuse)
                self.assertIsNotNone(decision.query)


def openjiuwen_log(folder: str, name: str, urls: list[str], seen: str = "") -> pathlib.Path:
    """A log whose tool replies report landing on these URLs, in the form
    `sufficiency.observed_text` and `listings_opened` read."""
    messages = [{"role": "user", "content": "the task"}]
    messages += [{"role": "tool", "tool_call_id": "c", "content": f"Page URL: {url}\n{seen}"}
                 for url in urls]
    path = pathlib.Path(folder) / f"{name}.log"
    path.write_text(json.dumps({"event_id": "e1", "messages": messages}) + "\n")
    return path


class BoxCheck(unittest.TestCase):
    """Box v2's answer check: v1's page-derived check for a v1 kind, then the plan's own."""

    def setUp(self):
        self.page = synthetic_page([round(10.15 + n, 2) for n in range(15)])
        self.go = f"Go to {RESULTS_URL} . "
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def urls(self, n: int) -> list[str]:
        return [item.url for item in self.page.by_price()[:n]]

    def test_a_v1_kind_keeps_v1s_verdict_and_adds_the_primitives(self):
        question = self.go + ("Across all the listings, which seller is cheapest for size M, and "
                              "what is that price? Only count a listing that can actually supply it.")
        decision = box.decide(question, self.page)
        answer = "Seller F is cheapest at $15.15 for size M."
        few = box.check(decision, answer, openjiuwen_log(self.tmp.name, "few", self.urls(3), "Price: $15.15"))
        self.assertEqual((few["flag"], few["floor"], few["opened"], few["floor_from"]),
                         ("superlative_without_coverage", 6, 3, "page"))
        self.assertEqual(few, policy.gate_from_page(question, self.page, answer,
                                                    openjiuwen_log(self.tmp.name, "few2", self.urls(3),
                                                                   "Price: $15.15")))
        enough = box.check(decision, answer, openjiuwen_log(self.tmp.name, "enough", self.urls(6), "Price: $15.15"))
        self.assertEqual((enough["ok"], enough["primitive"]), (True, "bound_prune"))

    def test_a_new_kind_exempts_the_questions_own_figure_and_runs_its_primitive(self):
        question = self.go + "Is there any seller under $20.00 for size M?"
        decision = box.decide(question, self.page)
        self.assertEqual(decision.kind, "exists_price")
        answer = "No. No seller is under $20.00 for size M."
        # Ten listings advertise at or below $20.00, and the $20.00 is the question's own.
        covered = box.check(decision, answer, openjiuwen_log(self.tmp.name, "covered", self.urls(10)))
        self.assertEqual((covered["ok"], covered["primitive"], covered["opened"]), (True, "witness", 10))
        short = box.check(decision, answer, openjiuwen_log(self.tmp.name, "short", self.urls(3)))
        self.assertEqual(short["flag"], "existence_denied_without_coverage")
        # A figure that is neither the question's nor on any page is still unsupported.
        invented = box.check(decision, "No. The cheapest M is $21.00.",
                             openjiuwen_log(self.tmp.name, "invented", self.urls(10)))
        self.assertEqual(invented["flag"], "unsupported_number")

    def test_a_limit_written_without_decimals_is_still_the_questions_own(self):
        # Verifier finding, 14 Oct 2026: `sufficiency.prices_in` needs decimals, so a
        # question written "under $20" exempted nothing, while the witness text wrote the
        # limit as "$20.00" and an answer echoing it was refused as an invented price.
        three = synthetic_page([10.15, 15.00, 25.00])
        opened = [item.url for item in three.listings[:2]]     # the two the limit allows
        answer = "No. No seller is under $20.00 for size M."
        for n, written in enumerate(("$20", "$20.00")):
            with self.subTest(written=written):
                decision = box.decide(self.go + f"Is there any seller under {written} for size M?", three)
                self.assertEqual(decision.kind, "exists_price")
                self.assertIn("at or below $20.00", decision.plan.instruction)
                verdict = box.check(decision, answer, openjiuwen_log(self.tmp.name, f"limit-{n}", opened))
                self.assertEqual((verdict["ok"], verdict["flag"], verdict.get("primitive"), verdict["opened"]),
                                 (True, None, "witness", 2))
                self.assertEqual(box.stated_figures(decision), {2000})
                # A figure that is neither the limit nor on any page is still unsupported.
                invented = box.check(decision, "No. The cheapest M is $21.00.",
                                     openjiuwen_log(self.tmp.name, f"invented-{n}", opened))
                self.assertEqual(invented["flag"], "unsupported_number")
        # The exemption is the question's own limit and nothing else: on a question that
        # sets none, "$20.00" is as unsupported as any other figure the run never saw.
        no_limit = box.decide(self.go + "Which three sellers are cheapest for size M?", three)
        self.assertEqual((no_limit.kind, box.stated_figures(no_limit)), ("topk_price", set()))
        verdict = box.check(no_limit, "Seller A at $20.00.", openjiuwen_log(self.tmp.name, "no-limit", opened))
        self.assertEqual(verdict["flag"], "unsupported_number")


class GateFromPage(unittest.TestCase):
    """LESSONS 32: the refusal check reads the market size and the floor from the page."""

    CHEAPEST = (f"Go to {RESULTS_URL} . Across all the listings, which seller is cheapest for "
                "size M, and what is that price?")
    COUNT = f"Go to {RESULTS_URL} . How many of the listings offer size M?"

    def setUp(self):
        # 15 listings advertised at 10.15, 11.15, ... 24.15. Six are at or below 15.15.
        self.page = synthetic_page([round(10.15 + n, 2) for n in range(15)])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def log(self, opened: int, seen: str = "") -> pathlib.Path:
        """An openJiuwen-shaped log whose tool replies report landing on the first `opened`
        listings, in the form `sufficiency.observed_text` and `listings_opened` read."""
        messages = [{"role": "user", "content": "the task"}]
        for item in self.page.listings[:opened]:
            messages.append({"role": "tool", "tool_call_id": "c",
                             "content": f"Page URL: {item.url}\n{seen}"})
        path = pathlib.Path(self.tmp.name) / f"run-{opened}.log"
        path.write_text(json.dumps({"event_id": "e1", "messages": messages}) + "\n")
        return path

    def test_a_cheapest_answer_with_too_few_opened_is_refused(self):
        answer = "Seller F is cheapest at $15.15 for size M."
        verdict = policy.gate_from_page(self.CHEAPEST, self.page, answer,
                                        self.log(3, seen="Price: $15.15"))
        self.assertEqual(verdict["flag"], "superlative_without_coverage")
        self.assertEqual((verdict["population"], verdict["floor"], verdict["opened"],
                          verdict["floor_from"]), (15, 6, 3, "page"))

    def test_a_cheapest_answer_that_covered_its_bound_passes(self):
        answer = "Seller F is cheapest at $15.15 for size M."
        verdict = policy.gate_from_page(self.CHEAPEST, self.page, answer,
                                        self.log(6, seen="Price: $15.15"))
        self.assertTrue(verdict["ok"])
        self.assertEqual((verdict["floor"], verdict["opened"]), (6, 6))

    def test_a_count_without_the_whole_page_is_refused(self):
        verdict = policy.gate_from_page(self.COUNT, self.page, "5 of the 15 listings offer it.",
                                        self.log(3))
        self.assertEqual(verdict["flag"], "count_without_coverage")
        self.assertEqual((verdict["population"], verdict["floor"]), (15, None))

    def test_a_count_over_the_whole_page_passes(self):
        verdict = policy.gate_from_page(self.COUNT, self.page, "5 of the 15 listings offer it.",
                                        self.log(15))
        self.assertTrue(verdict["ok"])

    def test_the_floor_is_the_listings_advertised_below_the_price_named_plus_its_own(self):
        # Five below, plus the listing advertised at the price itself: six.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$15.15"), 6)
        # The first price named is the one that counts.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$12.15, not $24.15"), 3)
        # Below every advertised price: at least the one named.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$9.00"), 1)
        # No price named: the whole page.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "Seller F, I think"), 15)
        # Not a superlative over the market: no floor of this kind.
        self.assertIsNone(policy.page_floor(self.COUNT, self.page, "$15.15"))
        # A price no card advertises: the answer's own listing is among those below it, so
        # nothing is added. Three are advertised below $12.50.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$12.50"), 3)

    def test_a_tie_at_the_price_named_is_counted_once(self):
        # Verifier finding, 14 Oct 2026: two listings advertised at the answer's price. The
        # text says to skip a listing advertised at or above the best total, so a run that
        # followed it opened the three advertised at or below it and skipped the other at
        # that price. The old floor of four refused it.
        tie = synthetic_page([10.15, 11.15, 12.15, 12.15, 13.15])
        self.assertEqual(policy.page_floor(self.CHEAPEST, tie, "Seller C at $12.15"), 3)
        self.assertEqual(policy.bound_floor(tie, 12.15), 3)
        self.assertEqual(policy.bound_floor(tie, 12.50), 4)
        answer = "Seller C is cheapest at $12.15 for size M."
        three = openjiuwen_log(self.tmp.name, "tie-3", [i.url for i in tie.listings[:3]], "Price: $12.15")
        verdict = policy.gate_from_page(self.CHEAPEST, tie, answer, three)
        self.assertEqual((verdict["ok"], verdict["floor"], verdict["opened"]), (True, 3, 3))
        two = openjiuwen_log(self.tmp.name, "tie-2", [i.url for i in tie.listings[:2]], "Price: $12.15")
        self.assertEqual(policy.gate_from_page(self.CHEAPEST, tie, answer, two)["flag"],
                         "superlative_without_coverage")

    def test_the_extra_one_is_for_the_answers_own_listing(self):
        # Verifier finding, 14 Oct 2026: the answer's own listing is advertised at $8 and
        # sells size M at $12.00, and two other listings are advertised at $12. A run that
        # followed the text opened the two advertised below its answer and skipped the
        # two at it. The old rule added one for any listing at the price and refused it.
        tie = synthetic_page([8.00, 9.00, 12.00, 12.00, 20.00])
        answer = "Seller A is cheapest at $12.00 for size M."
        self.assertEqual(policy.bound_floor(tie, 12.00, answer), 2)
        self.assertEqual(policy.page_floor(self.CHEAPEST, tie, answer), 2)
        two = openjiuwen_log(self.tmp.name, "own-2", [i.url for i in tie.listings[:2]], "Price: $12.00")
        verdict = policy.gate_from_page(self.CHEAPEST, tie, answer, two)
        self.assertEqual((verdict["ok"], verdict["floor"], verdict["opened"]), (True, 2, 2))
        one = openjiuwen_log(self.tmp.name, "own-1", [tie.listings[0].url], "Price: $12.00")
        self.assertEqual(policy.gate_from_page(self.CHEAPEST, tie, answer, one)["flag"],
                         "superlative_without_coverage")
        # The answer's own listing advertised at the price: the one is added, as before.
        self.assertEqual(policy.bound_floor(tie, 12.00, "Seller C is cheapest at $12.00."), 3)
        # No seller named: the old rule, one for any listing advertised at the price.
        self.assertEqual(policy.bound_floor(tie, 12.00, "$12.00"), 3)
        self.assertEqual(policy.bound_floor(tie, 12.00), 3)
        # A seller the page does not have is no seller named.
        self.assertEqual(policy.bound_floor(tie, 12.00, "Seller Z at $12.00"), 3)


class NamedIn(unittest.TestCase):
    """The listings an answer names, as whole names (verifier finding, 14 Oct 2026: the
    substring "seller a" was found inside "seller and")."""

    def setUp(self):
        self.page = page.Page(url=RESULTS_URL, total=3, next_page=False, listings=[
            page.Listing(seller="Seller And Sons", title="t", url=f"{BASE}/example-tee-01.html", advertised=10.0),
            page.Listing(seller="Seller A", title="t", url=f"{BASE}/example-tee-02.html", advertised=11.0),
            page.Listing(seller="Sons & Co.", title="t", url=f"{BASE}/example-tee-03.html", advertised=12.0)])

    def sellers(self, answer: str) -> list[str]:
        return [item.seller for item in policy.named_in(answer, self.page)]

    def test_a_name_counts_only_as_a_whole(self):
        self.assertEqual(self.sellers("Seller And Sons is cheapest at $12.00."), ["Seller And Sons"])
        self.assertEqual(self.sellers("Seller A is cheapest at $12.00."), ["Seller A"])
        self.assertEqual(self.sellers("seller a, at $12.00"), ["Seller A"])
        self.assertEqual(self.sellers("Seller Andrew is cheapest."), [])
        self.assertEqual(self.sellers("Seller AB is cheapest."), [])
        # A name ending in punctuation still matches before a space or a full stop.
        self.assertEqual(self.sellers("Sons & Co. is cheapest."), ["Sons & Co."])
        self.assertEqual(self.sellers("Cheapest: Sons & Co.."), ["Sons & Co."])
        self.assertEqual(self.sellers("Sons & Company is cheapest."), [])
        # By the last part of the URL, as a stored answer wrote it.
        self.assertEqual(self.sellers("The counterexample is (example-tee-02.html)."), ["Seller A"])
        self.assertEqual(self.sellers("See example-tee-02.html5."), [])
        self.assertEqual(self.sellers(""), [])
        self.assertEqual(self.sellers(None), [])
        # The primitives call it under its old name.
        self.assertIs(primitives.named_in, policy.named_in)


def thornwood_page() -> page.Page:
    """The Thornwood results page as the box recorded it in the pilot: what the box read
    from the shop, never the answer key."""
    record = json.loads(PILOT.read_text())["rows"][0]["box"]["page"]
    listings = [page.Listing(seller=item["seller"], title=item["seller"], url=item["url"],
                             advertised=item["advertised"]) for item in record["listings"]]
    return page.Page(url=record["url"], listings=listings, total=record["total"],
                     next_page=record["next_page"])


@unittest.skipUnless(PILOT.exists(), "the pilot batch's record is not here")
class FloorOnStoredBatches(unittest.TestCase):
    """The floor from the page counts a tie at the answer's price once (14 Oct 2026). On
    Thornwood, whose fifteen advertised prices are distinct, that is the old figure, every
    listing advertised at or below the answer, for every stored answer: so the pilot's
    recorded floor and the refusal replays over cells 1, 2 and 5 stand."""

    def test_every_stored_superlative_row_keeps_its_floor(self):
        page_ = thornwood_page()
        prices = [item.advertised for item in page_.listings]
        self.assertEqual((len(prices), len(set(prices))), (15, 15))
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        questions = {t["id"]: t["query"].format(base=spec["base_url"]) for t in spec["tasks"]}
        batches = [b for cell in compare_cells.CELLS.values() for b in cell] + [PILOT.parent.name]
        rows = 0
        for batch in batches:
            for row in json.loads((paths.RESULTS / batch / "suite.json").read_text())["rows"]:
                question = questions[row["task"]]
                if not sufficiency.superlative_over_population(question):
                    continue
                rows += 1
                named = score.prices_in(row["answer"])
                old = (len(prices) if not named
                       else max(1, sum(1 for p in prices if p <= named[0] + 0.005)))
                with self.subTest(batch=batch, run=f"{row['task']}-{row['repeat']}"):
                    self.assertEqual(policy.page_floor(question, page_, row["answer"]), old)
        self.assertEqual(rows, 27)
        pilot = json.loads(PILOT.read_text())["rows"][0]
        self.assertEqual(policy.page_floor(questions[pilot["task"]], page_, pilot["answer"]),
                         pilot["floor"])


class ReadingsSidecar(unittest.TestCase):
    """The scripted user's second reading: real tasks, valid keys, the catalogue's own count."""

    def setUp(self):
        self.spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        self.readings = score.readings_for(paths.TASKS / "tasks_apparel.json")

    def test_the_sidecar_names_real_tasks_with_keys_the_scorer_accepts(self):
        self.assertEqual(sorted(self.readings), ["buyable"])
        ids = {t["id"] for t in self.spec["tasks"]}
        for task_id, expect in self.readings["buyable"].items():
            with self.subTest(task=task_id):
                self.assertIn(task_id, ids)
                self.assertIn(expect["kind"], ("price", "contains", "boolean", "count", "all_prices"))
                score.score({"expect": expect}, "an answer", True)
        # The buyable count is the catalogue's own figure, and the universal is No under
        # both readings.
        self.assertEqual(self.readings["buyable"]["apparel-count-stocked"]["value"],
                         self.spec["_instance"]["listings_target_buyable"])
        self.assertEqual(self.readings["buyable"]["apparel-all-stocked"]["value"], False)

    def test_under_reading_uses_the_sidecar_key_and_falls_back_to_the_tasks_own(self):
        stocked = next(t for t in self.spec["tasks"] if t["id"] == "apparel-count-stocked")
        headline = next(t for t in self.spec["tasks"] if t["id"] == "apparel-headline")
        self.assertEqual(score.under_reading(stocked, "buyable", self.readings)["expect"],
                         {"kind": "count", "value": 5})
        self.assertEqual(score.under_reading(stocked, "menu", self.readings)["expect"]["value"], 10)
        self.assertIs(score.under_reading(stocked, None, self.readings), stocked)
        self.assertIs(score.under_reading(headline, "buyable", self.readings), headline)
        self.assertEqual(score.readings_for(paths.TASKS / "tasks.json"), {})


class SuiteQuery(unittest.TestCase):
    """LESSONS 17: the dry run and the paid loop build the text through one function."""

    def setUp(self):
        self.spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        self.page = synthetic_page([31.40, 12.25, 19.50])
        url = box.results_url(self.spec["tasks"][0]["query"].format(base=self.spec["base_url"]))
        suite.PAGES[url] = self.page    # injected, so nothing is fetched
        self.addCleanup(suite.PAGES.pop, url, None)

    def args(self, **over) -> argparse.Namespace:
        base = dict(box=False, reading=None, targeting=False, exhaustive=False, confidence="off")
        return argparse.Namespace(**{**base, **over})

    def question(self, task: dict) -> str:
        return task["query"].format(base=self.spec["base_url"])

    def test_the_box_asks_without_a_reading_and_plans_with_one(self):
        for task in self.spec["tasks"]:
            q = self.question(task)
            with self.subTest(task=task["id"]):
                query, applied = suite.build_query(task, self.spec, self.args(box=True))
                decision = box.decide(q, self.page)
                self.assertEqual(query, decision.query)
                self.assertEqual(applied, {"strategy": decision.kind, "box": decision.record(),
                                           "page": self.page, "decision": decision})
                query, applied = suite.build_query(task, self.spec, self.args(box=True, reading="menu"))
                self.assertEqual(query, box.decide(q, self.page, reply="menu").query)
                self.assertIsNotNone(query)

    def test_without_the_box_the_text_is_as_before(self):
        task = next(t for t in self.spec["tasks"] if t["id"] == "apparel-all-stocked")
        q = self.question(task)
        self.assertEqual(suite.build_query(task, self.spec, self.args()),
                         (q, {"strategy": None, "box": None, "page": None, "decision": None}))
        self.assertEqual(suite.build_query(task, self.spec, self.args(targeting=True)),
                         (planner.planned_query(q)[0],
                          {"strategy": "refutation", "box": None, "page": None, "decision": None}))
        self.assertEqual(suite.build_query(task, self.spec, self.args(exhaustive=True))[0],
                         policy.exhaustive_query(q))
        self.assertEqual(suite.build_query(task, self.spec, self.args(confidence="plain"))[0],
                         policy.confidence_query(q, "plain"))
        self.assertEqual(suite.build_query(task, self.spec, self.args(box=True, reading="menu",
                                                                      confidence="plain"))[0],
                         policy.confidence_query(box.decide(q, self.page, reply="menu").query, "plain"))

    def test_an_asked_row_spends_nothing_and_runs_nothing(self):
        task = next(t for t in self.spec["tasks"] if t["id"] == "apparel-all-stocked")
        record = box.decide(self.question(task), self.page).record()
        row = suite.asked_row(task, 2, record)
        self.assertEqual((row["task"], row["repeat"], row["verdict"], row["cost_usd"],
                          row["log"], row["tool_calls"]),
                         ("apparel-all-stocked", 2, "asked", 0, None, None))
        self.assertEqual(row["answer"], Ambiguity.ASK)
        self.assertEqual(row["box"], record)

    def test_a_refused_row_spends_nothing_and_says_what_was_missing(self):
        task = next(t for t in self.spec["tasks"] if t["id"] == "apparel-headline")
        decision = box.decide(f"Go to {RESULTS_URL} . Which seller delivers fastest?", self.page)
        row = suite.asked_row(task, 1, decision.record())
        self.assertEqual((row["verdict"], row["cost_usd"], row["log"]), ("refused", 0, None))
        self.assertTrue(row["answer"].startswith("The shop does not show delivery time"))
        self.assertIn("refused", row["why"])

    def test_the_reading_is_recorded_only_on_a_row_the_box_asked_on(self):
        # Verifier finding, 14 Oct 2026: under --reading menu every row said "menu", the
        # four clear questions included, where the box had asked nothing.
        args = self.args(box=True, reading="menu")
        for task in self.spec["tasks"]:
            with self.subTest(task=task["id"]):
                query, applied = suite.build_query(task, self.spec, args)
                self.assertIsNotNone(query)
                fields = suite.box_fields(applied["box"], args.reading)
                asked = task["id"] in Decide.AMBIGUOUS
                self.assertEqual(fields["box"]["asked"], asked)
                self.assertEqual(fields["reading"], "menu" if asked else None)

    def unrelated_task(self) -> dict:
        return {"id": "unrelated-weather", "family": "apparel", "gated": False,
                "query": UNRELATED[0], "expect": {"kind": "contains", "any": ["sunny"]}}

    def test_a_bypassed_question_is_built_without_a_page_and_sent_unchanged(self):
        task = self.unrelated_task()
        query, applied = suite.build_query(task, self.spec, self.args(box=True))
        self.assertEqual(query, UNRELATED[0])
        self.assertEqual((applied["strategy"], applied["page"], applied["box"]["bypassed"],
                          applied["decision"].bypass), (None, None, True, True))
        # Anything applied after the box still applies, as to any run.
        self.assertEqual(suite.build_query(task, self.spec, self.args(box=True, confidence="plain"))[0],
                         policy.confidence_query(UNRELATED[0], "plain"))

    def test_the_check_on_a_bypassed_run_is_the_figure_rules_alone(self):
        task = self.unrelated_task()
        _, applied = suite.build_query(task, self.spec, self.args(box=True))
        with tempfile.TemporaryDirectory() as tmp:
            log = openjiuwen_log(tmp, "bypass", [], "It is 31 degrees.")
            fine = suite.gate_for(task, self.spec, "Sunny, 31 degrees.", log,
                                  applied["page"], applied["decision"])
            invented = suite.gate_for(task, self.spec, "Sunny, and it costs $999.99.", log,
                                      applied["page"], applied["decision"])
        self.assertEqual((fine["ok"], fine["population"], fine["floor"], fine["floor_from"],
                          fine["opened"]), (True, None, None, None, 0))
        self.assertEqual(invented["flag"], "unsupported_number")

    def test_the_batch_counts_what_the_box_did(self):
        def row(verdict: str, **box_record) -> dict:
            # A row the box closed, asked or refused, has no query; every other row ran.
            ran = verdict not in ("asked", "refused")
            record = {"asked": False, "refuse": None, "bypassed": False, "fallback": False,
                      "query": "the text the agent got" if ran else None, **box_record}
            return {"task": "t", "family": "f", "gated": True, "repeat": 1, "verdict": verdict,
                    "why": "", "answer": "", "tool_calls": None, "actions": None,
                    "observations": None, "cost_usd": 0, "elapsed_s": 0, "error": None,
                    "log": None, "box": record}
        rows = [row("asked", asked=True), row("asked", asked=True),
                row("correct", asked=True),        # asked, and a --reading answered it
                row("refused", refuse="The shop does not show delivery time"),
                row("wrong", bypassed=True), row("correct", fallback=True), row("correct"),
                # Planned by the fallback and then refused, or asked on with no reading:
                # nothing ran, so refused or asked alone (verifier finding, 14 Oct 2026:
                # a refused fallback was counted twice).
                row("refused", refuse="The shop does not show shipping cost", fallback=True),
                row("asked", asked=True, fallback=True)]
        summary = suite.summarise(rows)
        self.assertEqual(summary["box"], {"asked": 4, "refused": 2, "bypassed": 1, "fallback": 1})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            suite.print_summary(summary, rows)
        self.assertIn("box: asked 4, refused 2, bypassed 1, fallback 1", out.getvalue())
        # A refused fallback is what the box records for a shapeless question about an
        # attribute the shop lacks, so the row above is a real shape, not an invented one.
        refused = box.decide(f"Go to {RESULTS_URL} . Tell me about the shipping of the listings.",
                             self.page).record()
        self.assertEqual((refused["fallback"], bool(refused["refuse"]), refused["query"]),
                         (True, True, None))
        # Without the box there is nothing to count, and no line.
        plain = [{k: v for k, v in r.items() if k != "box"} for r in rows]
        self.assertIsNone(suite.summarise(plain)["box"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            suite.print_summary(suite.summarise(plain), plain)
        self.assertNotIn("box:", out.getvalue())

    def test_the_dry_run_prints_bypass_for_an_unrelated_question(self):
        # In a temporary copy of the clothing task file, with --only so that nothing is
        # fetched. The task file under experiments/tasks/ must not change.
        tasks = paths.TASKS / "tasks_apparel.json"
        before = tasks.read_bytes()
        spec = json.loads(before)
        spec["tasks"].append(self.unrelated_task())
        with tempfile.TemporaryDirectory() as tmp:
            temporary = pathlib.Path(tmp) / "tasks_temporary.json"
            temporary.write_text(json.dumps(spec, indent=2))
            run = subprocess.run(
                [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
                 "--tasks", str(temporary), "--repeats", "1", "--box",
                 "--only", "unrelated-weather", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(f"BYPASS: {UNRELATED[0]}", run.stdout)
        self.assertNotIn("Listings by advertised price", run.stdout)
        # The header says what the browser may request, as the payload of a paid run does.
        self.assertIn(f"browser: browser_tool={suite.BROWSER_TOOL} "
                      f"browser_origins={suite.ALLOWED_ORIGINS}\n", run.stdout)
        self.assertEqual(tasks.read_bytes(), before)

    def test_the_box_and_a_strategy_flag_are_refused(self):
        run = subprocess.run(
            [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
             "--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
             "--box", "--targeting", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("--box cannot be combined with --targeting or --exhaustive", run.stderr)

    def test_an_unknown_task_id_in_only_is_refused_by_name(self):
        # Verifier finding, 14 Oct 2026, at 7d2ec2e: an id that named no task was dropped
        # without a word, so a misspelt --only ran the rest as if nothing were missing.
        command = [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
                   "--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                   "--dry-run", "--only", "apparel-headline"]
        run = subprocess.run(command + ["apparel-headlnie"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("apparel-headlnie", run.stderr)
        self.assertNotIn("Go to", run.stdout)
        # The same list without the misspelling runs as before.
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("1 tasks x 1 repeats = 1 runs", run.stdout)

    def test_the_box_and_the_naive_scaffold_are_refused_until_its_browser_is_confined(self):
        # The naive loop launches its own browser with a user agent and nothing else
        # (`naive_agent.py`), so a question the box bypasses could take it off the shop.
        command = [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
                   "--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                   "--only", "apparel-headline", "--scaffold", "naive", "--dry-run"]
        run = subprocess.run(command + ["--box"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("the second agent's browser is not confined to the shop", run.stderr)
        self.assertNotIn("Listings by advertised price", run.stdout)
        # Without the box the second agent's dry run is as before.
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("1 tasks x 1 repeats = 1 runs", run.stdout)
        self.assertIn("browser: browser_tool=None browser_origins=None\n", run.stdout)
        self.assertNotIn("Listings by advertised price", run.stdout)

    def test_the_browser_tool_is_pinned_and_the_user_agent_defined_once(self):
        self.assertIn(f"@playwright/mcp@{suite.BROWSER_TOOL}", suite.MCP_ARGS_GATED)
        self.assertNotIn("latest", suite.MCP_ARGS_GATED)
        self.assertIn(page.GATED_UA, suite.MCP_ARGS_GATED)
        self.assertIs(suite.GATED_UA, page.GATED_UA)

    def test_the_browser_may_request_only_the_shop_on_the_gated_shop(self):
        # A bypassed question names no shop page, so the browser is confined to the shop
        # (verifier finding, 14 Oct 2026). The agent splits the string with shlex.
        words = shlex.split(suite.browser_env("gated")["PLAYWRIGHT_MCP_ARGS"])
        self.assertEqual(words.count("--allowed-origins"), 1)
        self.assertEqual(words[words.index("--allowed-origins") + 1], "http://localhost:7770")
        self.assertEqual(words[words.index("--user-agent") + 1], page.GATED_UA)
        self.assertEqual(words[:2], ["-y", f"@playwright/mcp@{suite.BROWSER_TOOL}"])
        # The default shop sets no MCP arguments, so it is not confined, and says so.
        self.assertNotIn("PLAYWRIGHT_MCP_ARGS", suite.browser_env("default"))
        self.assertEqual(suite.browser_conditions("openjiuwen", "gated"),
                         {"browser_tool": "0.0.83", "browser_origins": "http://localhost:7770"})
        for scaffold, shop in (("openjiuwen", "default"), ("naive", "gated"), ("naive", "default")):
            with self.subTest(scaffold=scaffold, shop=shop):
                self.assertEqual(suite.browser_conditions(scaffold, shop),
                                 {"browser_tool": None, "browser_origins": None})


class AgentCode(unittest.TestCase):
    """Every batch says which openJiuwen code answered: the submodule's commit and the
    sha1 of the uncommitted patch on it (verifier finding, 14 Oct 2026: the patch was a
    held-constant condition that no record named)."""

    HEX40 = r"^[0-9a-f]{40}$"

    @staticmethod
    def git(*args: str) -> bytes:
        return subprocess.run(["git", "-C", str(paths.AGENT_CORE), *args],
                              capture_output=True, check=True).stdout

    def test_this_checkout_gives_the_commit_and_the_patch_digest(self):
        identity = suite.agent_code_identity()
        self.assertRegex(identity["agent_core_commit"], self.HEX40)
        self.assertRegex(identity["agent_core_patch"], self.HEX40)
        # The same two figures taken independently: the digest is of the bytes git prints,
        # so an empty diff would give the sha1 of nothing.
        self.assertEqual(identity["agent_core_commit"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(identity["agent_core_patch"], hashlib.sha1(self.git("diff")).hexdigest())

    def test_without_git_the_batch_records_unknown_and_warns(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            identity = suite.agent_code_identity(git="/nonexistent/git")
        self.assertEqual(identity, {"agent_core_commit": "unknown", "agent_core_patch": "unknown"})
        self.assertIn("warning", err.getvalue())
        self.assertIn("unknown", err.getvalue())

    def test_a_folder_that_is_not_its_own_repository_is_unknown_not_the_parents_commit(self):
        # An uninitialised submodule is an empty folder, and git answers for the nearest
        # repository around it: this one. That must read as unknown, not as our commit.
        with contextlib.redirect_stderr(io.StringIO()) as err:
            identity = suite.agent_code_identity(where=paths.EXPERIMENTS)
        self.assertEqual(identity["agent_core_commit"], "unknown")
        self.assertIn("not its own repository", err.getvalue())


# What a piece of code can read an answer through: the keys of a task's answer, of a market's
# instance and of the seeder's manifests, and the fixture and manifest files themselves. Not
# covered: a bare number such as the market's size, which no test can tell from any other 15.
ANSWER_KEYS = {"_instance", "expect", "oracle_min_opens", "ground_truth"}
BEFORE_THE_AGENT = ("targeting.py", "planner.py", "page.py", "ambiguity.py", "box.py",
                    "form.py", "primitives.py")


def code_values(source: str) -> tuple[list[str], list[float], set[str]]:
    """The strings, decimal numbers and names a piece of code uses, leaving out comments and
    docstrings, which may quote a past failure without reading anything."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
               and isinstance(n.value, str) and id(n) not in docstrings]
    floats = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, float)]
    names = ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
             | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)})
    return strings, floats, names


def answer_reads(source: str) -> list[str]:
    strings, _, names = code_values(source)
    found = [s for s in strings if s in ANSWER_KEYS or "fixtures" in s.lower()
             or "manifest" in s.lower()]
    return found + sorted(n for n in names if n == "FIXTURES")


def market_facts() -> tuple[set[str], set[str]]:
    """Every seller and every price in every market this project has generated."""
    sellers, prices = set(), set()
    for fixture in paths.FIXTURES.glob("*.json"):
        for family in json.loads(fixture.read_text())["families"]:
            if family.get("seller"):
                sellers.add(family["seller"])
            prices.update(f"{v['price']:.2f}" for v in family["variants"])
    return sellers, prices


def copied_facts(source: str) -> list[str]:
    sellers, prices = market_facts()
    strings, floats, _ = code_values(source)
    text = "\n".join(strings)
    found = sorted(s for s in sellers if s in text)
    found += sorted(p for p in prices if re.search(rf"(?<![\d.]){re.escape(p)}(?!\d)", text))
    found += sorted(f"{x:.2f}" for x in floats if f"{x:.2f}" in prices)
    return found


class NoAnswerKey(unittest.TestCase):
    """The parts of the box that run before the agent decide from the question and the page.

    Checked by what the code uses rather than by how one file happens to be spelled: the
    keys an answer is read through, the fixture files, and any seller or price copied in.
    """

    def source(self, name: str) -> str:
        return (paths.EXPERIMENTS / "box" / name).read_text()

    def test_reads_no_answer_key_or_fixture(self):
        for name in BEFORE_THE_AGENT:
            with self.subTest(file=name):
                self.assertEqual(answer_reads(self.source(name)), [])

    def test_copies_no_seller_or_price(self):
        for name in BEFORE_THE_AGENT:
            with self.subTest(file=name):
                self.assertEqual(copied_facts(self.source(name)), [])

    def test_the_checks_catch_a_planted_read(self):
        seller = sorted(market_facts()[0])[0]
        planted = {
            'x = spec["_instance"]["winner"]': answer_reads,
            "x = task['expect']": answer_reads,
            'x = task.get("expect")': answer_reads,
            'x = paths.FIXTURES / "scaled_apparel.json"': answer_reads,
            'x = json.load(open("env/manifests/run.json"))["ground_truth"]': answer_reads,
            f'x = "{seller}"': copied_facts,
            "x = 25.77": copied_facts,
        }
        for code, check in planted.items():
            with self.subTest(planted=code):
                self.assertNotEqual(check(code), [])

    def test_only_the_page_module_fetches(self):
        # `page.py` is the one box module that reads anything, and it reads HTTP only. The
        # decision modules read nothing at all. (`planner.py` is not held to this: its
        # `--regression` reads every task file's questions, and `answer_reads` above checks
        # that it reads none of their answers.)
        for name in ("page.py", "ambiguity.py", "box.py", "targeting.py", "form.py", "primitives.py"):
            with self.subTest(file=name):
                _, _, names = code_values(self.source(name))
                if name == "page.py":
                    self.assertIn("urlopen", names)
                    self.assertFalse({"open", "read_text", "requests"} & names)
                else:
                    self.assertFalse({"urlopen", "open", "read_text", "requests"} & names)

    def test_only_the_answer_checks_read_the_answer_key(self):
        # sufficiency.py and policy.gate judge a finished answer against the answer key's
        # market size and floor, and are evaluation tools for that reason. policy.gate_from_page
        # takes both from the page instead. No other file here may join the two readers.
        readers = sorted(p.name for p in (paths.EXPERIMENTS / "box").glob("*.py")
                         if answer_reads(p.read_text()))
        self.assertEqual(readers, ["policy.py", "sufficiency.py"])


if __name__ == "__main__":
    unittest.main()
