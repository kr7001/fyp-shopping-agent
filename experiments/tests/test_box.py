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
import replay_box  # noqa: E402
import score  # noqa: E402
import sufficiency  # noqa: E402
import suite  # noqa: E402
import targeting  # noqa: E402
import trace_stats  # noqa: E402

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
        for item in self.page.listings:
            self.assertEqual(market_overlap(item.seller, item.url), [])

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
        # without the enumeration step the box has already done. Since box v19 (24 October
        # 2026) the body is followed by the one sentence on size labels, on its own line.
        self.assertEqual(decision.query,
                         f"{q}\n\n{box.preamble(self.page)}\n\n{targeting.BODIES[decision.kind]}\n"
                         f"{primitives.LABEL_NOTE}")
        self.assertNotIn(targeting.ENUMERATE, decision.query)

    def test_a_page_with_a_later_page_unread_is_not_planned_over(self):
        # Until box v16 the agent was told "there is a next page, open it too before
        # deciding" and planned over the first page alone. Since then the box reads every
        # page, and property 1 holds over all of them: a read that stopped with a page
        # unread is no enumeration. Planted: the check removed, the headline was planned
        # over 3 listings of 40.
        paged = page.Page(url=RESULTS_URL, listings=self.page.listings, total=40, next_page=True)
        for task_id in ("apparel-headline", "apparel-target-price", "apparel-count-buyable"):
            with self.subTest(task=task_id), self.assertRaisesRegex(
                    ValueError, "the population is not enumerated first: the search runs to a "
                                "results page the box did not read"):
                box.decide(self.questions[task_id], paged, reply="menu")

    def test_every_listing_of_every_page_is_in_the_plan(self):
        # Two pages read to the end: one population, said to be on two pages, every listing
        # in the plan by advertised price, and the bound over all of them.
        later = [page.Listing(seller=f"Seller {chr(68 + n)}", title=f"Example Tee - Seller {chr(68 + n)}",
                              url=f"{BASE}/example-tee-{n + 4:02d}.html", advertised=price)
                 for n, price in enumerate([11.10, 40.00])]
        both = page.Page(url=RESULTS_URL, listings=self.page.listings + later, total=5, next_page=False,
                         pages=(RESULTS_URL, f"{BASE}/catalogsearch/result/index/?p=2&q=Example"))
        decision = box.decide(self.questions["apparel-target-price"], both)
        self.assertIn("The search results list 5 listings on 2 pages; there is no further page.\n"
                      "Listings by advertised price, read from the results pages:\n"
                      "1. Seller D, advertised $11.10, http://localhost:7770/example-tee-04.html\n"
                      "2. Seller B, advertised $12.25, http://localhost:7770/example-tee-02.html\n", decision.query)
        self.assertIn("5. Seller E, advertised $40.00, http://localhost:7770/example-tee-05.html", decision.query)
        self.assertEqual([c.seller for c in decision.plan.candidates],
                         ["Seller D", "Seller B", "Seller C", "Seller A", "Seller E"])
        self.assertEqual(form_module.verify(decision.form, both), [])
        # One page keeps v1's sentence, byte for byte.
        one = box.decide(self.questions["apparel-target-price"], self.page)
        self.assertIn("The results page lists 3 listings on one page; there is no next page.\n"
                      "Listings by advertised price, read from the results page:\n", one.query)
        # A seller on the second page is found, and one on neither is asked about over both.
        # Planted: the ask's text for one page kept for two, "the results page" said it.
        pair = f"Go to {RESULTS_URL} . Between Seller E and Seller B, who is cheaper for size M?"
        self.assertEqual(box.decide(pair, both).kind, "named_lookup")
        missing = box.decide(pair.replace("Seller E", "Seller Q"), both)
        self.assertEqual(missing.ask.text, "Your question names Seller Q, which the 2 results pages do not "
                                           "list among their 5 listings. Which of them do you mean?")
        self.assertEqual(box.decide(pair.replace("Seller E", "Seller Q"), self.page).ask.text,
                         "Your question names Seller Q, which the results page does not list among its 3 "
                         "listings. Which of them do you mean?")

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
        # Verifier finding, 14 Oct 2026: "sells" was not a market word, so "Who sells the
        # softest tee?" bypassed. Since 20 Oct that question is refused for its superlative
        # (`Refusal`), so the market word is checked on one without a superlative.
        decision = box.decide("Who sells the Thornwood tee?", self.page)
        self.assertFalse(decision.bypass)
        self.assertEqual((decision.kind, decision.record()["fallback"]), ("survey", True))
        self.assertIn("a market word: sells", decision.form.evidence["fallback"])
        softest = box.decide("Who sells the softest tee?", self.page)
        self.assertEqual((softest.bypass, softest.kind, softest.record()["fallback"]), (False, None, False))
        self.assertTrue(softest.refuse)
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
    measurement of the text v2 sends.

    Amended on 20 October 2026 for strategy texts v8 and v9 (box v10 and v11): five
    sentences of the v1 text were not true of the gated shop, and the fixture's entries
    were rewritten with them reworded, deliberately, with a dated note in its `_about`.
    Every other byte is still v1's, which `test_claim_arms.V1Amendment` checks against the
    v1 queries' sha1. So since box v10 the pilot measured a text that differs from today's
    in those five. Amended again on 24 October 2026 for box v19: every plan that opens a
    listing ends with one sentence on size labels (`primitives.LABEL_NOTE`, `box.ADDED`)."""

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
        # The entries are the question, the preamble and the v7 body, nothing else, but the
        # label sentence box v19 appends to a plan that opens a listing (the fixture's
        # amendment of 24 October 2026), which `box.as_sent_by` takes off again.
        frozen = json.loads((FIXTURES / "v1_clothing_queries.json").read_text())
        page_ = synthetic_page([31.40, 12.25, 19.50])
        for row in frozen["queries"]:
            if row["query"] is None:
                continue
            with self.subTest(task=row["task"], reading=row["reading"]):
                body = box.as_sent_by(row["query"], 18).split(f"\n\n{box.preamble(page_)}\n\n", 1)[1]
                self.assertIn(body, targeting.BODIES.values())
                self.assertEqual(row["query"].endswith(f"\n{primitives.LABEL_NOTE}"),
                                 body != targeting.BODIES["results_page"])


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

    def test_a_superlative_on_an_attribute_the_shop_does_not_show_is_refused_whatever_the_word(self):
        # 20 Oct 2026: "Who sells the softest Thornwood tee?" was planned by the fallback
        # and opened all 15 listings for an attribute no page shows (verifier finding).
        decision = box.decide(self.go + "Who sells the softest Thornwood tee?", self.page)
        self.assertTrue(decision.refuse.startswith("The shop does not show what 'softest' ranks by"))
        self.assertEqual((decision.query, decision.plan, decision.kind, decision.record()["fallback"]),
                         (None, None, None, False))
        # A refusal comes before an ask: no limit the user could give would answer it.
        both = box.decide(self.go + "Is there a cheap tee that is the softest?", self.page)
        self.assertTrue(both.refuse)
        self.assertIsNone(both.ask)
        asks = box.decide(self.go + "Is there a cheap Thornwood tee in size M?", self.page)
        self.assertIsNotNone(asks.ask)
        self.assertIsNone(asks.refuse)

    def test_a_refusal_comes_before_the_ambiguity_ask(self):
        # Verifier finding, 20 Oct 2026: these asked which reading of "offer" was meant and
        # refused after the reply, spending a user turn on a question the shop cannot answer.
        for q in ("Does every listing offer the softest tee in size M?",
                  "Which seller offers the most comfortable tee in size M?"):
            with self.subTest(question=q):
                self.assertIsNotNone(ambiguity.ask(self.go + q))
                decision = box.decide(self.go + q, self.page)
                self.assertTrue(decision.refuse)
                self.assertEqual((decision.ask, decision.query, decision.record()["asked"]),
                                 (None, None, False))
        # The one refusal that depends on the reading (the price of a sold-out size) is
        # not raised before the ask: a price question with an ambiguous verb is read the
        # one way the shop can answer (`test_a_reading_the_shop_cannot_answer_is_not_asked_about`),
        # and the user's own menu reply is still refused.
        depends = self.go + ("Across the listings, which seller is cheapest for size M among "
                             "those that stock size M?")
        chosen = box.decide(depends, self.page)
        self.assertEqual((chosen.ask, chosen.refuse, chosen.reading, chosen.reading_by),
                         (None, None, "buyable", "box"))
        self.assertEqual(box.decide(depends, self.page, reply="menu").query, chosen.query)
        # The menu reading of such a question is refused when the question settles it
        # itself, with one of the menu phrases, so there is nothing to ask.
        settled = box.decide(depends.replace("stock size M", "stock size M, sold out or not"), self.page)
        self.assertIsNone(ambiguity.ask(settled.question))
        self.assertTrue(settled.refuse.startswith("The shop does not show the price of a sold-out size"))
        # A question answerable under both readings still asks.
        plain = box.decide(self.go + "Does every listing offer size M?", self.page)
        self.assertEqual((plain.ask is not None, plain.refuse), (True, None))

    def test_a_reading_the_shop_cannot_answer_is_not_asked_about(self):
        # 20 Oct 2026: "has size M" is the menu-or-buyable ambiguity, but a price exists
        # only for a size that can be sold, so the box reads the question as buyable and
        # says so instead of asking and refusing after the reply.
        q = self.go + "Which seller has the best price for size M?"
        self.assertIsNotNone(ambiguity.ask(q))
        decision = box.decide(q, self.page)
        self.assertEqual((decision.ask, decision.reading, decision.reading_by, decision.kind),
                         (None, "buyable", "box", "availability_bound"))
        self.assertEqual((decision.record()["asked"], decision.record()["reading_by"]), (False, "box"))
        self.assertIn("By 'has the best price for size M' I mean listings that can sell it now",
                      decision.query)
        # A reply to a question the box does not put is ignored, the scripted user's
        # --reading included: the box's choice stands either way.
        for reply in ("buyable", "menu"):
            with self.subTest(reply=reply):
                replied = box.decide(q, self.page, reply=reply)
                self.assertEqual((replied.reading, replied.reading_by, replied.refuse, replied.ask),
                                 ("buyable", "box", None, None))
                self.assertEqual(replied.query, decision.query)
        # Both readings answerable: the box asks, as before, and records no reading.
        for q in (self.go + "Which seller has the best availability for size M?",
                  self.go + "Does every listing offer size M?"):
            with self.subTest(question=q):
                asks = box.decide(q, self.page)
                self.assertEqual((asks.ask is not None, asks.reading, asks.reading_by), (True, None, None))
                self.assertEqual(box.decide(q, self.page, reply="menu").reading_by, "user")


class PageRecord(unittest.TestCase):
    def test_a_page_comes_back_from_its_record(self):
        # The record keeps no title; the replay reads sellers, URLs and prices only.
        original = synthetic_page([31.40, 12.25, 19.50])
        back = page.from_record(original.record())
        self.assertEqual(back.record(), original.record())
        self.assertEqual([i.seller for i in back.by_price()], [i.seller for i in original.by_price()])
        self.assertEqual((back.total, back.next_page), (3, False))


def openjiuwen_log(folder: str, name: str, urls: list[str], seen: str = "") -> pathlib.Path:
    """A log whose tool replies report landing on these URLs, in the form
    `sufficiency.observed_text` and `listings_opened` read."""
    messages = [{"role": "user", "content": "the task"}]
    messages += [{"role": "tool", "tool_call_id": "c", "content": f"Page URL: {url}\n{seen}"}
                 for url in urls]
    path = pathlib.Path(folder) / f"{name}.log"
    path.write_text(json.dumps({"event_id": "e1", "messages": messages}) + "\n")
    return path


def menu_log(folder: str, name: str, pages: list[tuple]) -> pathlib.Path:
    """A log whose tool replies report landing on each URL and show its size menu, in the
    form the runtime stores (a Python repr inside JSON, so a newline is backslash and n),
    which `sufficiency.size_menus` reads. Each entry is (URL, menu) for a snapshot of the
    page, or (URL, menu, how) with `how` "excerpt" for a navigation followed by a find
    reply cut inside the option block, as the real logs hold them, or "excerpt-closed" for
    a find reply whose block is followed by another line. The menu maps each label to
    whether it can be chosen."""
    messages = [{"role": "user", "content": "the task"}]
    calls = 0

    def reply(tool: str, text: str) -> None:
        nonlocal calls
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{calls}", "function": {"name": f"mcp_playwright-official_{tool}",
                                             "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{calls}",
                         "content": [{"type": "text", "text": text}]})
        calls += 1

    for entry in pages:
        url, menu, how = (*entry, "snapshot")[:3]
        options = "".join(f'\\n  - option "{label}"' + ("" if can else " [disabled]")
                          for label, can in menu.items())
        block = ('- combobox "Size *" [ref=f1e89]:\\n  - option "Choose an Option..." [selected]'
                 + options)
        if how == "depth-cut":
            # A snapshot taken with a depth that ends at the combobox: a leaf, no colon, no
            # option lines, its sibling next (20260910T133605/scaled-cheapest-target-1.log).
            block = '- combobox "Size *" [ref=f1e89]\\n- generic [ref=f1e92]:'
        if how == "excerpt-front":
            # A find window that starts inside the option block: the head, then the options
            # from the match's window on, without the placeholder, then the next tree line
            # (20261014T220116/apparel-cheapest-xl-1, igr-app-08, a find for "XL").
            block = '- combobox "Size *" [ref=f1e89]:' + options
        if how in ("snapshot", "depth-cut"):
            reply("browser_snapshot", "{'result': '### Page\\n- Page URL: " + url
                  + "\\n### Snapshot\\n```yaml\\n" + block + "\\n```'}")
            continue
        reply("browser_navigate", "{'result': \"### Ran Playwright code\\n```js\\nawait page.goto('"
              + url + "');\\n```\\n### Page\\n- Page URL: " + url + "\\n### Snapshot\\n- [Snapshot](x.yml)\"}")
        tail = "" if how == "excerpt" else "\\n- generic [ref=f1e92]:"
        reply("browser_find", "{'result': '### Result\\nFound 2 matches for \"Size\":\\n\\n"
              "- generic [ref=f1e87]: Size *\\n" + block + tail + "'}")
    path = pathlib.Path(folder) / f"{name}.log"
    path.write_text(json.dumps({"event_id": "e1", "messages": messages}) + "\n")
    return path


class ListingsOpened(unittest.TestCase):
    """The listing counter since 20 Oct 2026 (LESSONS 2, a fourth time: a category page,
    `electronics.html`, had counted as a listing). A page is a listing by what it is: one of
    the market's listings when the page the box read is given, else a product page of a
    generated market or Magento's id path. Never a category or home page."""

    TEXT = "\n".join(f"Page URL: {url}" for url in (
        "http://localhost:7770/electronics.html", "http://localhost:7770/",
        "http://localhost:7770/igr-app-03.html", "http://localhost:7770/igr-rvn-07.html",
        "http://localhost:7770/catalog/product/view/id/230",
        "http://localhost:7770/calderwood-still-spring-water-multipack-chandler-direct.html",
        "http://localhost:7770/catalogsearch/result/?q=Thornwood"))

    def test_without_a_market_the_generated_markets_product_pages_count(self):
        self.assertEqual(sufficiency.listings_opened(self.TEXT),
                         {"slug:igr-app-03", "slug:igr-rvn-07", "id:230"})
        # The fault, planted: the old rule, any single-segment .html path, read the
        # category page and the name slug as listings too.
        old = {sufficiency._listing_key(url) for url in sufficiency.PAGE_MARKER.findall(self.TEXT)}
        self.assertEqual(old - {None}, {"slug:electronics", "slug:igr-app-03", "slug:igr-rvn-07",
                                        "id:230",
                                        "slug:calderwood-still-spring-water-multipack-chandler-direct"})

    def test_with_a_market_only_its_listings_count(self):
        market = ["http://localhost:7770/igr-app-03.html", "http://localhost:7770/igr-app-04.html"]
        self.assertEqual(sufficiency.listings_opened(self.TEXT, market), {"slug:igr-app-03"})
        self.assertEqual(sufficiency.listings_opened(self.TEXT, []), set())
        # A market's listings count by membership, however their URLs are spelled.
        synthetic = synthetic_page([10.15, 11.15])
        text = "\n".join(f"Page URL: {item.url}" for item in synthetic.listings)
        self.assertEqual(sufficiency.listings_opened(text, [item.url for item in synthetic.listings]),
                         {sufficiency.listing_key(item.url) for item in synthetic.listings})
        self.assertEqual(sufficiency.listings_opened(text), set())


class CounterexampleFromTheMenu(unittest.TestCase):
    """20 Oct 2026: a bare "No" to "does every listing offer size M" is supported by an
    opened listing whose observed size menu lacks M, whether or not the answer names it.
    Five correct bare "No" runs of the 14 October batches were refused without this. The
    plan text still asks the agent to name the listing."""

    def setUp(self):
        self.page = synthetic_page([10.15, 11.15, 12.15])
        self.urls = [item.url for item in self.page.listings]
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.question = f"Go to {RESULTS_URL} . Does every listing offer size M? Answer yes or no."

    def decision(self, reply: str = "menu") -> box.Decision:
        return box.decide(self.question, self.page, reply=reply)

    def why(self, decision: box.Decision, answer: str, log: pathlib.Path) -> str:
        """The counterexample check's own reason. `box.check` keeps its verdict and then
        reports the filter check's reason, as it always has."""
        text = sufficiency.observed_text(log)
        opened = sufficiency.listings_opened(text, [item.url for item in self.page.listings])
        return primitives.Counterexample.check(decision.form, decision.page, answer, opened, text,
                                               sufficiency.size_menus(log))["why"]

    def test_a_bare_no_is_supported_by_an_opened_listing_without_the_size(self):
        log = menu_log(self.tmp.name, "lacks", [(self.urls[0], {"S": True, "L": True})])
        self.assertEqual(sufficiency.size_menus(log),
                         {sufficiency.listing_key(self.urls[0]):
                          sufficiency.MenuReading({"S": True, "L": True}, True)})
        verdict = box.check(self.decision(), "No", log)
        self.assertEqual((verdict["ok"], verdict["opened"], verdict["primitive"]),
                         (True, 1, "counterexample"))
        self.assertEqual(self.why(self.decision(), "No", log),
                         "a counterexample was opened: Seller A's size menu lists S, L and not M")

    def test_a_bare_no_with_only_a_listing_that_has_the_size_opened_is_refused(self):
        log = menu_log(self.tmp.name, "has", [(self.urls[0], {"S": True, "M": True, "L": True})])
        self.assertEqual(box.check(self.decision(), "No", log)["flag"], "counterexample_not_opened")

    def test_a_bare_no_with_nothing_opened_is_refused(self):
        log = openjiuwen_log(self.tmp.name, "nothing", [])
        self.assertFalse(box.check(self.decision(), "No", log)["ok"])

    def test_a_disabled_size_refutes_the_buying_reading_only(self):
        log = menu_log(self.tmp.name, "disabled", [(self.urls[0], {"S": True, "M": False, "L": True})])
        self.assertTrue(box.check(self.decision(reply="buyable"), "No", log)["ok"])
        self.assertEqual(self.why(self.decision(reply="buyable"), "No", log),
                         "a counterexample was opened: Seller A's size menu shows M disabled")
        self.assertEqual(box.check(self.decision(reply="menu"), "No", log)["flag"],
                         "counterexample_not_opened")

    def test_the_fault_planted(self):
        # The check without the menus is the check as it was: the same log and the same
        # No, refused (LESSONS 31).
        log = menu_log(self.tmp.name, "planted", [(self.urls[0], {"S": True, "L": True})])
        decision = self.decision()
        text = sufficiency.observed_text(log)
        without = primitives.check(decision.form, decision.page, "No", text)
        self.assertEqual(without["flag"], "counterexample_not_opened")
        self.assertTrue(primitives.check(decision.form, decision.page, "No", text,
                                         menus=sufficiency.size_menus(log))["ok"])

    def test_naming_an_opened_listing_passes_as_before(self):
        log = menu_log(self.tmp.name, "named", [(self.urls[0], {"S": True, "M": True})])
        self.assertTrue(box.check(self.decision(), "No. Seller A lacks it.", log)["ok"])
        self.assertEqual(self.why(self.decision(), "No. Seller A lacks it.", log),
                         "the counterexample named was opened")

    def test_a_pack_label_with_a_surcharge_is_the_pack(self):
        # The water markets label a pack "2 x 9.5L +$15.01"; the size is still in the menu.
        self.assertEqual(primitives.menu_has({"2 x 9.5L +$15.01": True}, "2 x 9.5L"), "2 x 9.5L +$15.01")
        self.assertIsNone(primitives.menu_has({"12 x 550ml": True, "9.5L": True}, "2 x 9.5L"))

    def test_an_excerpt_cut_inside_the_menu_shows_presence_only(self):
        # Verifier finding, 20 Oct 2026: a find reply is an excerpt, cut wherever its three
        # lines end, and one ending after S and M was read as a menu without L and XL.
        key = sufficiency.listing_key(self.urls[0])
        xl = box.decide(f"Go to {RESULTS_URL} . Does every listing offer size XL? Answer yes or no.",
                        self.page, reply="menu")
        cut = menu_log(self.tmp.name, "cut", [(self.urls[0], {"S": True, "M": True}, "excerpt")])
        reading = sufficiency.size_menus(cut)[key]
        self.assertEqual((reading.options, reading.complete), ({"S": True, "M": True}, False))
        self.assertEqual(box.check(xl, "No", cut)["flag"], "counterexample_not_opened")
        # The fault, planted: taken as complete, the same excerpt would refute XL.
        forced = {key: sufficiency.MenuReading(dict(reading.options), True)}
        self.assertIsNotNone(primitives.counterexample_seen(xl.form, self.page, {key}, forced))
        self.assertIsNone(primitives.counterexample_seen(xl.form, self.page, {key}, {key: reading}))
        # The same two sizes seen whole, in a snapshot or in an excerpt whose block ends
        # before the excerpt does, do refute XL.
        for how in ("snapshot", "excerpt-closed"):
            with self.subTest(how=how):
                whole = menu_log(self.tmp.name, f"whole-{how}", [(self.urls[0], {"S": True, "M": True}, how)])
                self.assertTrue(sufficiency.size_menus(whole)[key].complete)
                self.assertTrue(box.check(xl, "No", whole)["ok"])
        # Presence still counts from an excerpt: M seen disabled refutes the buying reading.
        disabled = menu_log(self.tmp.name, "cut-disabled", [(self.urls[0], {"S": True, "M": False}, "excerpt")])
        self.assertFalse(sufficiency.size_menus(disabled)[key].complete)
        self.assertTrue(box.check(self.decision(reply="buyable"), "No", disabled)["ok"])
        self.assertEqual(self.why(self.decision(reply="buyable"), "No", disabled),
                         "a counterexample was opened: Seller A's size menu shows M disabled")
        # A later complete reading of the same listing completes it.
        both = menu_log(self.tmp.name, "both", [(self.urls[0], {"S": True, "M": True}, "excerpt"),
                                                (self.urls[0], {"S": True, "M": True})])
        self.assertTrue(sufficiency.size_menus(both)[key].complete)

    def test_a_depth_cut_snapshot_gives_no_reading(self):
        # Verifier finding, 20 Oct 2026: a snapshot taken with a depth prints the combobox
        # as a leaf, no colon and no option lines, and carries the page URL, which the first
        # rule took for a complete reading with no sizes: a bare No against a listing whose
        # menu was never seen.
        key = sufficiency.listing_key(self.urls[0])
        cut = menu_log(self.tmp.name, "depth", [(self.urls[0], {}, "depth-cut")])
        self.assertEqual(sufficiency.size_menus(cut), {})
        self.assertEqual(box.check(self.decision(), "No", cut)["flag"], "counterexample_not_opened")
        # The fault, planted: the reading the first rule made of this snapshot, complete
        # with no sizes, refutes every size; no text gives that reading now, a head with
        # a colon and no option lines included.
        forced = {key: sufficiency.MenuReading({}, True)}
        self.assertIsNotNone(primitives.counterexample_seen(self.decision().form, self.page, {key}, forced))
        text = cut.read_text().replace('[ref=f1e89]\\\\n', '[ref=f1e89]:\\\\n')
        planted = pathlib.Path(self.tmp.name) / "planted.log"
        planted.write_text(text)
        self.assertEqual(sufficiency.size_menus(planted), {})
        # A whole snapshot, head with a colon, options, then a tree line, still refutes.
        whole = menu_log(self.tmp.name, "whole", [(self.urls[0], {"S": True, "L": True})])
        self.assertTrue(box.check(self.decision(), "No", whole)["ok"])

    def test_a_find_window_that_starts_inside_the_menu_shows_presence_only(self):
        # Verifier finding, 20 Oct 2026: the find renderer prints three lines around a
        # match with no mark of what it dropped before them, so a block whose first option
        # is not the placeholder may have lost options in front of the window.
        key = sufficiency.listing_key(self.urls[0])
        xs = box.decide(f"Go to {RESULTS_URL} . Does every listing offer size XS? Answer yes or no.",
                        self.page, reply="menu")
        seen = {"S": True, "M": True, "L": True, "XL": True}        # a find on XL: options 2 to 5
        front = menu_log(self.tmp.name, "front", [(self.urls[0], seen, "excerpt-front")])
        reading = sufficiency.size_menus(front)[key]
        self.assertEqual((reading.options, reading.complete), (seen, False))
        self.assertEqual(box.check(xs, "No", front)["flag"], "counterexample_not_opened")
        # The fault, planted: the block read as complete refutes XS.
        forced = {key: sufficiency.MenuReading(dict(seen), True)}
        self.assertIsNotNone(primitives.counterexample_seen(xs.form, self.page, {key}, forced))
        # The same block beginning with the placeholder is the whole menu and refutes XS.
        whole = menu_log(self.tmp.name, "front-whole", [(self.urls[0], seen, "excerpt-closed")])
        self.assertTrue(sufficiency.size_menus(whole)[key].complete)
        self.assertTrue(box.check(xs, "No", whole)["ok"])
        # Presence still counts: a size seen disabled in the window refutes the buying reading.
        disabled = menu_log(self.tmp.name, "front-disabled",
                            [(self.urls[0], {"M": False, "L": True}, "excerpt-front")])
        self.assertTrue(box.check(self.decision(reply="buyable"), "No", disabled)["ok"])


V2_BATCHES = compare_cells.DEVELOPMENT["box v2 development, Thornwood, in-sample"]
HAVE_V2_LOGS = all(any((paths.RESULTS / batch).glob("*.log")) for batch in V2_BATCHES)


@unittest.skipUnless(HAVE_V2_LOGS, "the raw logs live on the laptop, not in git")
class BoxBatchesReplayed(unittest.TestCase):
    """The box's own check replayed over the three batches of 14 October 2026 from the
    stored page record and the logs (`replay_box`). The figures the verifier asked for on
    20 Oct: no wrong run refused, and no other run refused either, where five correct bare
    "No" runs were refused before the menu evidence was read."""

    @classmethod
    def setUpClass(cls):
        cls.rows = [r for batch in V2_BATCHES for r in replay_box.replay(paths.RESULTS / batch)]

    def test_the_check_refuses_no_wrong_run_and_one_other_whose_menu_was_an_excerpt(self):
        s = replay_box.summary(self.rows)
        self.assertEqual((s["runs"], s["wrong"], s["wrong_refused"], s["other"]), (32, 3, [], 29))
        # The one correct run refused saw igr-app-03's menu in a find excerpt only, which
        # shows S and L and cannot say M is absent (20 Oct 2026, the sound reader).
        self.assertEqual([(r["batch"], replay_box.tag(r)) for r in self.rows if not r["ok"]],
                         [("20261014T222007", "apparel-all-stocked-1")])
        reading = sufficiency.size_menus(paths.RESULTS / "20261014T222007" / "apparel-all-stocked-1.log")
        self.assertEqual(reading, {"slug:igr-app-03": sufficiency.MenuReading({"S": True, "L": True}, False)})
        # All 32 stored texts are reproduced under the box version they ran under, v6: each
        # run's stored form is recomposed with today's code and the rewordings made since
        # (box v10 and v11, `box.REWORDED`) are swapped back first (20 Oct 2026). Until
        # then the comparison was with today's words, and 17 runs differed by them alone.
        self.assertEqual((s["text_reproduced"], s["not_reproduced"]), (32, []))
        # 29 are decided the same today. The other three differ by deliberate changes,
        # named: the two "under $" questions read their limit strictly since form v9, and
        # today's form with the old operator renders each stored text exactly, so the
        # operator is the whole difference; the softest question is refused since box v7.
        # Nothing differs for any other reason.
        self.assertEqual(s["same_today"], 29)
        self.assertEqual(s["expected_today"], [
            "apparel-exists-under-27-1: the limit is strict since form v9 (price < 27)",
            "apparel-exists-under-25-1: the limit is strict since form v9 (price < 25)",
            "apparel-softest-1: refused today: The shop does not show what 'softest' ranks by"])
        self.assertEqual((s["decided_differently_today"], s["unexpected_today"]), ([], []))

    def test_every_menu_reading_agrees_with_the_fixture(self):
        # The reader validated against the fixture over every run of the three batches: a
        # complete reading is the fixture's menu, a partial one a prefix of it.
        rows = [r for batch in V2_BATCHES for r in replay_box.menu_table(paths.RESULTS / batch)]
        complete = [r for r in rows if r["reading"] == "complete"]
        partial = [r for r in rows if r["reading"] == "partial"]
        self.assertEqual((len(rows), len(complete), len(partial)), (180, 109, 71))
        self.assertEqual([r for r in rows if not r["agrees"]], [])
        # The one stored find block without the placeholder (cheapest-xl-1, igr-app-08, a
        # find for "XL" printing S, M, L, XL) is partial on its own; the run's two snapshots
        # of that listing keep its merged reading complete.
        log = paths.RESULTS / "20261014T220116" / "apparel-cheapest-xl-1.log"
        finds = [sufficiency.menu_blocks(text, whole_page=False)
                 for tool, text, _ in trace_stats.tool_replies(log).values() if tool == "browser_find"]
        self.assertEqual([b for blocks in finds for b in blocks],
                         [({"S": False, "M": False, "L": True, "XL": True}, False)])
        self.assertTrue(sufficiency.size_menus(log)["slug:igr-app-08"].complete)
        # The verifier's case: on count-stocked-2 of 20261014T213118 a No to "every listing
        # offers XL" is refuted by the one complete reading, igr-app-03's menu of S and L,
        # and not by igr-app-02's excerpt of S and M.
        batch = paths.RESULTS / "20261014T213118"
        suite_payload = json.loads((batch / "suite.json").read_text())
        market = page.from_record(next(r["box"]["page"] for r in suite_payload["rows"] if r.get("box")))
        menus = sufficiency.size_menus(batch / "apparel-count-stocked-2.log")
        self.assertEqual((menus["slug:igr-app-02"].options, menus["slug:igr-app-02"].complete),
                         ({"S": True, "M": True}, False))
        decision = box.decide(f"Go to {market.url} . Does every listing offer size XL? Answer yes or no.",
                              market, reply="menu")
        seen = primitives.counterexample_seen(decision.form, market, set(menus), menus)
        self.assertTrue(seen[0].url.endswith("/igr-app-03.html"))
        self.assertEqual(seen[1], "lists S, L and not XL")

    def test_without_the_menus_the_five_bare_no_runs_are_refused(self):
        original = sufficiency.size_menus
        sufficiency.size_menus = lambda log_path: {}
        try:
            rows = [r for batch in V2_BATCHES for r in replay_box.replay(paths.RESULTS / batch)]
        finally:
            sufficiency.size_menus = original
        s = replay_box.summary(rows)
        self.assertEqual(s["wrong_refused"], [])
        self.assertEqual(sorted(s["other_refused"]),
                         sorted(["apparel-all-stocked-1", "apparel-all-stocked-3",
                                 "apparel-all-stocked-1", "apparel-all-stocked-2",
                                 "apparel-all-stocked-3"]))

    def test_the_menus_read_from_a_real_log(self):
        batch = paths.RESULTS / "20261014T213118"
        self.assertEqual(sufficiency.size_menus(batch / "apparel-all-stocked-1.log"),
                         {"slug:igr-app-03": sufficiency.MenuReading({"S": True, "L": True}, True)})
        menus = sufficiency.size_menus(batch / "apparel-cheapest-target-2.log")
        self.assertEqual(menus["slug:igr-app-07"],
                         sufficiency.MenuReading({"S": False, "M": False, "L": True, "XL": True}, True))
        self.assertEqual(menus["slug:igr-app-02"],
                         sufficiency.MenuReading({"S": True, "M": True, "L": True, "XL": True}, True))

    def test_the_counter_on_the_run_that_wandered_to_a_category_page(self):
        text = sufficiency.observed_text(paths.RESULTS / "20261014T213118" / "apparel-all-stocked-2.log")
        self.assertEqual(sufficiency.listings_opened(text), {"slug:igr-app-03"})
        old = {sufficiency._listing_key(url) for url in
               sufficiency.PRODUCT_NAV.findall(text) + sufficiency.PAGE_MARKER.findall(text)}
        self.assertEqual(old - {None}, {"slug:electronics", "slug:igr-app-03"})


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
                # "under" is a strict limit since form v9 (20 Oct 2026), so the text says
                # below and never at or below; `test_claim_arms.StrictUnder`.
                self.assertIn("the price you read is below $20.00", decision.plan.instruction)
                self.assertNotIn("at or below $20.00", decision.plan.instruction)
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


class PackMenus(unittest.TestCase):
    """The menu reader on the water's pack menu, the combobox "Pack Size *" (sufficiency
    rules v5, 22 October 2026), on two live Larchmere listings' snapshots kept in
    `fixtures/larchmere_water_menus.json`, each held to the menu its page's own select
    holds."""

    @classmethod
    def setUpClass(cls):
        cls.listings = json.loads((FIXTURES / "larchmere_water_menus.json").read_text())["listings"]

    def dom(self, name: str) -> dict[str, bool]:
        return {label: enabled for label, enabled in self.listings[name]["dom"]
                if label != sufficiency.MENU_PLACEHOLDER}

    def test_a_filled_pack_menu_reads_whole_as_the_page_holds_it(self):
        # Planted: the head read as a size menu's alone, no reading at all.
        for name in self.listings:
            with self.subTest(listing=name):
                blocks = sufficiency.menu_blocks(self.listings[name]["populated"], whole_page=True)
                self.assertEqual(blocks, [(self.dom(name), True)])
                self.assertEqual(list(blocks[0][0]), list(self.dom(name)))     # in the page's order
        self.assertEqual(self.dom("igr-dev-23.html")["6 x 1.25L"], False)      # sold out, disabled
        self.assertNotIn("2 x 9.5L", self.dom("igr-dev-16.html"))              # not in its menu

    def test_the_browser_tools_own_form_reads_the_same(self):
        # The tool writes [ref=...] after every node; the reader takes those as it always has.
        name = "igr-dev-23.html"
        text = self.listings[name]["populated"]
        refs = iter(range(70, 200))
        tooled = "\n".join(re.sub(r'^(\s*- (?:combobox|option) "[^"]*")', lambda m: f"{m.group(1)} [ref=e{next(refs)}]",
                                  line) for line in text.splitlines())
        self.assertIn('- combobox "Pack Size *" [ref=e', tooled)
        self.assertEqual(sufficiency.menu_blocks(tooled, whole_page=True), [(self.dom(name), True)])

    def test_a_menu_not_yet_filled_in_is_no_reading(self):
        # Just after loading, every water listing's menu holds its placeholder alone. Read as
        # complete, it lacked every pack, a counterexample for every question. Planted: the
        # guard removed, it was ({}, True).
        for name in self.listings:
            with self.subTest(listing=name):
                self.assertEqual(sufficiency.menu_blocks(self.listings[name]["early"], whole_page=True),
                                 [({}, False)])
        # And a head with no colon, a node past a snapshot's depth, gives none (sufficiency
        # rules' note, 20260910T133605/scaled-cheapest-target-1.log).
        self.assertEqual(sufficiency.menu_blocks('- combobox "Pack Size *" [ref=f3e89]\n- text: Qty', True), [])
        # A size menu reads as before.
        sized = '- combobox "Size *" [ref=e1]:\n  - option "Choose an Option..." [selected]\n  - option "M"\n- text: Qty'
        self.assertEqual(sufficiency.menu_blocks(sized, True), [({"M": True}, True)])


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

    def test_under_reading_uses_the_sidecar_key_and_never_falls_back_to_the_tasks_own(self):
        stocked = next(t for t in self.spec["tasks"] if t["id"] == "apparel-count-stocked")
        headline = next(t for t in self.spec["tasks"] if t["id"] == "apparel-headline")
        self.assertEqual(score.under_reading(stocked, "buyable", self.readings)["expect"],
                         {"kind": "count", "value": 5})
        self.assertEqual(score.under_reading(stocked, "menu", self.readings)["expect"]["value"], 10)
        self.assertIs(score.under_reading(stocked, None, self.readings), stocked)
        # A run answered under the buyable reading with no key for it is unscored, never
        # scored under the task's own key, whatever the word list makes of the question
        # (score.py v4, 22 October 2026; until then a clear question fell back to its own).
        with self.assertRaises(score.NoKeyForReading):
            score.under_reading(headline, "buyable", self.readings)
        self.assertEqual(score.score_under(headline, "buyable", self.readings, "Seller A at $1.00.", True)
                         ["verdict"], "unscored")
        self.assertIs(score.under_reading(headline, None, self.readings), headline)
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
                fields = suite.box_fields(applied["box"])
                asked = task["id"] in Decide.AMBIGUOUS
                self.assertEqual(fields["box"]["asked"], asked)
                self.assertEqual((fields["reading"], fields["reading_by"]),
                                 ("menu", "user") if asked else (None, None))
                self.assertEqual(suite.reading_answered(applied["box"], args.reading),
                                 "menu" if asked else None)

    def test_a_reading_the_box_took_is_recorded_printed_and_scored_under_its_key(self):
        # Verifier finding, 20 Oct 2026: a run the box read as buyable recorded no reading
        # and was scored under the menu key, the flag's.
        task = {"id": "best-price", "family": "apparel", "gated": True,
                "query": "Go to {base}/catalogsearch/result/?q=Example . Which seller has the "
                         "best price for size M?",
                "expect": {"kind": "contains", "any": ["Seller B"], "price": 12.25}}
        # The made-up page, injected: until 22 October 2026 this read the live shop's own
        # search for "Example", whose first page then stood in for it.
        suite.PAGES[RESULTS_URL] = self.page
        self.addCleanup(suite.PAGES.pop, RESULTS_URL, None)
        query, applied = suite.build_query(task, self.spec, self.args(box=True, reading="menu"))
        fields = suite.box_fields(applied["box"])
        self.assertEqual((fields["reading"], fields["reading_by"], fields["box"]["asked"]),
                         ("buyable", "box", False))
        self.assertEqual(suite.reading_answered(applied["box"], "menu"), "buyable")
        self.assertIsNone(suite.reading_answered(None, None))
        # The dry run says so, before the text.
        with contextlib.redirect_stdout(io.StringIO()) as out:
            suite.print_dry_task(task, query, applied)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[1], "reading taken by the box: buyable")
        self.assertTrue(lines[2].startswith("Go to "))
        # Scored under the buyable sidecar key, where the task has one: the clothing count
        # question's key is 10 under the menu reading and 5 under buyable.
        count = next(t for t in self.spec["tasks"] if t["id"] == "apparel-count-stocked")
        readings = score.readings_for(paths.TASKS / "tasks_apparel.json")
        taken = {"reading": "buyable", "reading_by": "box"}
        self.assertEqual(score.under_reading(count, suite.reading_answered(taken, "menu"), readings)["expect"],
                         {"kind": "count", "value": 5})
        asked = {"reading": "menu", "reading_by": "user"}
        self.assertEqual(score.under_reading(count, suite.reading_answered(asked, "menu"), readings)["expect"],
                         count["expect"])
        clear = {"reading": None, "reading_by": None}
        self.assertEqual(score.under_reading(count, suite.reading_answered(clear, "menu"), readings)["expect"],
                         count["expect"])
        # A plain task prints no such line.
        plain = next(t for t in self.spec["tasks"] if t["id"] == "apparel-headline")
        query, applied = suite.build_query(plain, self.spec, self.args(box=True))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            suite.print_dry_task(plain, query, applied)
        self.assertNotIn("reading taken by the box", out.getvalue())

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
        # The header says what the browser may request and the flags it runs with, as the
        # payload of a paid run does.
        self.assertIn(f"browser: browser_tool={suite.BROWSER_TOOL} "
                      f"browser_origins={suite.ALLOWED_ORIGINS} "
                      f"browser_flags={suite.BROWSER_FLAGS}\n", run.stdout)
        self.assertEqual(tasks.read_bytes(), before)

    def test_the_box_and_a_strategy_flag_are_refused(self):
        run = subprocess.run(
            [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
             "--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
             "--box", "--targeting", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("--box cannot be combined with --targeting or --exhaustive", run.stderr)

    def test_an_unknown_task_id_in_only_is_refused_by_name(self):
        # Verifier finding, 14 Oct 2026, at 39f15e9: an id that named no task was dropped
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
        self.assertIn("browser: browser_tool=None browser_origins=None browser_flags=None\n", run.stdout)
        self.assertNotIn("Listings by advertised price", run.stdout)

    def test_the_browser_tool_is_pinned_and_the_user_agent_defined_once(self):
        self.assertIn(f"@playwright/mcp@{suite.BROWSER_TOOL}", suite.MCP_ARGS_GATED)
        self.assertNotIn("latest", suite.MCP_ARGS_GATED)
        self.assertIn(page.GATED_UA, suite.MCP_ARGS_GATED)
        self.assertIs(suite.GATED_UA, page.GATED_UA)

    def test_the_browser_may_request_only_the_shop_on_the_gated_shop(self):
        # A bypassed question names no shop page, so the browser is confined to the shop
        # (verifier finding, 14 Oct 2026), and since 20 Oct service workers are blocked
        # beside it, so every page the agent reads is one the shop served. The agent splits
        # the string with shlex.
        words = shlex.split(suite.browser_env("gated")["PLAYWRIGHT_MCP_ARGS"])
        self.assertEqual(words.count("--allowed-origins"), 1)
        self.assertEqual(words[words.index("--allowed-origins") + 1], "http://localhost:7770")
        self.assertEqual(words.count("--block-service-workers"), 1)
        # Since 20 Oct 2026 the profile is in memory too (`--isolated`, verifier finding:
        # every run had shared one profile on disk); `test_claim_arms.IsolatedProfile`.
        self.assertEqual(suite.BROWSER_FLAGS, "--block-service-workers --isolated")
        self.assertEqual(words[words.index("--user-agent") + 1], page.GATED_UA)
        self.assertEqual(words[:2], ["-y", f"@playwright/mcp@{suite.BROWSER_TOOL}"])
        # The default shop sets no MCP arguments, so it is not confined, and says so; the
        # naive loop drives its own browser and gets neither flag.
        self.assertNotIn("PLAYWRIGHT_MCP_ARGS", suite.browser_env("default"))
        self.assertNotIn("PLAYWRIGHT_MCP_ARGS", suite.browser_env("default", "viewport"))
        self.assertEqual(suite.browser_conditions("openjiuwen", "gated"),
                         {"browser_tool": "0.0.83", "browser_origins": "http://localhost:7770",
                          "browser_flags": "--block-service-workers --isolated"})
        for scaffold, shop in (("openjiuwen", "default"), ("naive", "gated"), ("naive", "default")):
            with self.subTest(scaffold=scaffold, shop=shop):
                self.assertEqual(suite.browser_conditions(scaffold, shop),
                                 {"browser_tool": None, "browser_origins": None,
                                  "browser_flags": None})


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
        # The same two figures taken independently: the digest is of the bytes git prints
        # with full blob ids, so an empty diff would give the sha1 of nothing, and the
        # machine's abbreviation setting changes nothing (verifier finding, 20 Oct 2026).
        self.assertEqual(identity["agent_core_commit"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(identity["agent_core_patch"],
                         hashlib.sha1(self.git("diff", "--full-index")).hexdigest())
        self.assertNotEqual(identity["agent_core_patch"], hashlib.sha1(self.git("diff")).hexdigest())
        # The committed patch is that diff, so its own sha1 is the figure a batch records.
        patch = paths.REPO / "agent" / "openjiuwen-local.patch"
        self.assertEqual(hashlib.sha1(patch.read_bytes()).hexdigest(), identity["agent_core_patch"])
        self.assertIn(b"index abc17b21aef8bb0b2ae1e63424d455b0be037bb0..", patch.read_bytes())

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
# normalise.py joined on 22 October 2026, with the model's front door: it reads the form,
# the question and the page, and nothing else.
BEFORE_THE_AGENT = ("targeting.py", "planner.py", "page.py", "ambiguity.py", "box.py",
                    "form.py", "primitives.py", "normalise.py")


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


def market_listings() -> dict[str, set[str]]:
    """What makes a listing a generated market's: its seller, its address on the shop and its
    SKU, from every fixture. A made-up page is nobody's when none of its listings is one of
    these, by what it is (LESSONS 2). Until 22 October 2026 the made-up pages were held to
    every market's prices too, and a price two markets can share by chance is not what a
    listing is: the Larchmere fixture gave a variant the 14.85 of a made-up seller."""
    found: dict[str, set[str]] = {"sellers": set(), "urls": set(), "skus": set()}
    for fixture in paths.FIXTURES.glob("*.json"):
        for family in json.loads(fixture.read_text())["families"]:
            sku = family["parent_sku"].lower()
            found["skus"].add(sku)
            found["urls"].add(f"{BASE}/{sku}.html")
            found["sellers"].add(family.get("seller") or family["name"].rsplit(" - ", 1)[-1])
    return found


def market_overlap(seller: str, url: str) -> list[str]:
    """What of a made-up listing, its seller or its address, is a generated market's own."""
    market = market_listings()
    sku = url.rsplit("/", 1)[-1].lower().removesuffix(".html")
    return ([f"seller {seller!r}"] if seller in market["sellers"] else []) + \
           ([f"listing {url}"] if url in market["urls"] or sku in market["skus"] else [])


def market_facts() -> tuple[set[str], set[str]]:
    """Every seller and every price in every market this project has generated, for the
    checks that no seller or price is copied into the box's own code (`copied_facts`)."""
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
        for name in ("page.py", "ambiguity.py", "box.py", "targeting.py", "form.py", "primitives.py",
                     "normalise.py"):
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
