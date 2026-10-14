"""The logical form, box v2: the record, the rules parser held to v1's classifier and to the
new forms, the five properties, the primitives' choice, text and answer checks, and the
model parser on a fake call.

Every rule has a case where it fires and one where it stays quiet (LESSONS 24 and 31), and
the synthetic page belongs to no generated market, which `test_box.Decide` checks.
"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import form  # noqa: E402
import page  # noqa: E402
import planner  # noqa: E402
import primitives  # noqa: E402
import sufficiency  # noqa: E402
import targeting  # noqa: E402
from form import Filter, Form  # noqa: E402
from test_box import BASE, RESULTS_URL, clothing_questions, synthetic_page  # noqa: E402

GO = f"Go to {RESULTS_URL} . "
CHEAPEST_M = GO + "Across the listings, which seller is cheapest for size M, and what is that price?"


def census() -> list[tuple[str, str]]:
    return planner.questions()


class Vocabulary(unittest.TestCase):
    def test_a_form_outside_the_vocabulary_is_refused(self):
        for label, build in {
            "quantifier": lambda: Form("sometimes", "price"),
            "population": lambda: Form("argmin", "price", population="basket"),
            "objective": lambda: Form("argmin", "delivery"),
            "empty attribute": lambda: Form("argmin", "attribute:"),
            "topk without k": lambda: Form("topk", "price"),
            "k on argmin": lambda: Form("argmin", "price", k=3),
            "k of zero": lambda: Form("topk", "price", k=0),
            "source": lambda: Form("argmin", "price", source="guess"),
            "filter op": lambda: Filter("price", "~", 20),
            "in without a tuple": lambda: Filter("seller", "in", "A"),
            "tuple without in": lambda: Filter("seller", "=", ("A",)),
        }.items():
            with self.subTest(fault=label):
                with self.assertRaises(ValueError):
                    build()
        # And the same values inside the vocabulary build.
        Form("topk", "price", k=3)
        Form("argmin", "attribute:delivery time")
        Filter("seller", "in", ("A", "B"))

    def test_the_record_round_trips(self):
        parsed = form.from_rules(GO + "Is there any seller under $20 for size M?")
        record = parsed.record()
        self.assertEqual((record["form_version"], record["kind"]), (form.VERSION, "exists_price"))
        self.assertEqual(form.from_record(record, "rules"), parsed)
        self.assertEqual(form.from_record(record, "model").source, "model")


class RulesAgainstV1(unittest.TestCase):
    """`from_rules` keeps every v1 kind. The eight single-listing questions in tasks.json
    are the exception, and a pinned one: v1 only ever reached them through its fallback,
    "survey", which tells the agent to open every listing in a search it was never sent
    to. v2 reads them as what they are, a lookup on the one listing the URL names."""

    def test_every_question_keeps_its_v1_kind_or_is_a_single_listing_lookup(self):
        lookups = []
        for name, question in census():
            parsed = form.from_rules(question)
            v1 = targeting.classify(question)
            with self.subTest(question=question[:60]):
                if parsed.kind() == v1:
                    continue
                self.assertEqual((v1, parsed.kind(), parsed.quantifier, parsed.population),
                                 ("survey", "named_lookup", "lookup", "listing"))
                lookups.append(name)
        self.assertEqual(len(census()), 37)
        self.assertEqual(lookups, ["tasks.json"] * 8)

    def test_the_plan_dict_is_the_planners_own_plan(self):
        # The assembly lives in two places and the planner's tables in one. This is what
        # keeps the two from drifting.
        checked = 0
        for _, question in census():
            parsed = form.from_rules(question)
            if parsed.kind() != targeting.classify(question):
                continue
            with self.subTest(question=question[:60]):
                self.assertEqual(form.plan_dict(parsed), planner.plan(question))
            checked += 1
        self.assertEqual(checked, 29)

    def test_every_census_question_verifies_and_needs_nothing_the_shop_lacks(self):
        for _, question in census():
            with self.subTest(question=question[:60]):
                parsed = form.from_rules(question)
                self.assertEqual(form.not_shown(parsed), [])
                self.assertEqual(form.verify(parsed), [])
                self.assertEqual(parsed.unknowns, ())

    def test_the_six_clothing_forms(self):
        questions = clothing_questions()
        size_m = Filter("size", "=", "M")
        buyable = Filter("availability", "=", "buyable")
        expected = {
            "apparel-headline": ("argmin", "advertised price", (), "results_page"),
            "apparel-target-price": ("argmin", "price", (size_m, buyable), "availability_bound"),
            "apparel-cheapest-target": ("argmin", "price", (size_m, buyable), "availability_bound"),
            "apparel-all-stocked": ("forall", "availability", (size_m,), "refutation"),
            "apparel-count-stocked": ("count", "availability", (size_m,), "survey"),
            "apparel-count-buyable": ("count", "availability", (size_m, buyable), "survey"),
        }
        for task_id, (quantifier, objective, filters, kind) in expected.items():
            with self.subTest(task=task_id):
                parsed = form.from_rules(questions[task_id])
                self.assertEqual((parsed.quantifier, parsed.objective, parsed.filters,
                                  parsed.kind(), parsed.population, parsed.reading),
                                 (quantifier, objective, filters, kind, "results", None))

    def test_the_reading_is_read_back_from_the_sentence_the_box_wrote(self):
        question = clothing_questions()["apparel-count-stocked"]
        asked = ambiguity.ask(question)
        menu = form.from_rules(ambiguity.with_reading(question, asked, "menu"))
        buyable = form.from_rules(ambiguity.with_reading(question, asked, "buyable"))
        self.assertEqual((menu.reading, menu.filter("availability").value), ("menu", "listed"))
        self.assertEqual((buyable.reading, buyable.filter("availability").value),
                         ("buyable", "buyable"))
        self.assertEqual(menu.kind(), "survey")

    def test_evidence_names_the_words_that_chose_each_field(self):
        parsed = form.from_rules(clothing_questions()["apparel-cheapest-target"])
        self.assertEqual(parsed.evidence["quantifier"], "cheapest")
        self.assertEqual(parsed.evidence["filter:size"], "size M")
        self.assertEqual(parsed.evidence["filter:availability"], "supply")
        self.assertEqual(parsed.evidence["population"], "the results URL")


class NewForms(unittest.TestCase):
    """Each form v1 lacked, from two phrasings, with a near miss that stays quiet."""

    def test_existence_under_a_limit(self):
        for question in (GO + "Is there any seller under $20 for size M?",
                         GO + "Does any seller charge less than $20 for size M?"):
            with self.subTest(question=question):
                parsed = form.from_rules(question)
                self.assertEqual((parsed.quantifier, parsed.objective, parsed.kind(), parsed.reading),
                                 ("exists", "price", "exists_price", "buyable"))
                self.assertEqual(parsed.filter("price"), Filter("price", "<=", 20.0))
                self.assertEqual(parsed.filter("size"), Filter("size", "=", "M"))
                self.assertEqual(parsed.filter("availability"), Filter("availability", "=", "buyable"))
        # "$20 or less" is the same limit.
        self.assertEqual(form.from_rules(GO + "Is anyone at $20 or less for size M?").filter("price"),
                         Filter("price", "<=", 20.0))
        # Near misses: "cheapest" without "any" is the best of the market, "anyone" under a
        # superlative is too, and an existence question with no limit has no witness rule.
        self.assertEqual(form.from_rules(GO + "Which seller is cheapest for size M under $20?").kind(),
                         "total_bound")
        self.assertEqual(form.from_rules(GO + "What is the lowest price anyone charges for size M?").kind(),
                         "total_bound")
        self.assertEqual(form.from_rules(GO + "Does any seller have size M in stock?").quantifier,
                         "aggregate")

    def test_the_k_cheapest(self):
        for question, k in ((GO + "Which are the three cheapest sellers for size M?", 3),
                            (GO + "List the top 3 sellers by price for size M.", 3),
                            (GO + "Name the cheapest three sellers for size M.", 3),
                            (GO + "Which are the 5 cheapest sellers for size L?", 5)):
            with self.subTest(question=question):
                parsed = form.from_rules(question)
                self.assertEqual((parsed.quantifier, parsed.objective, parsed.k, parsed.kind()),
                                 ("topk", "price", k, "topk_price"))
                self.assertEqual(parsed.filter("availability"), Filter("availability", "=", "buyable"))
        # "three listings" is not a top three, and "cheapest" alone is the best of the market.
        self.assertEqual(form.from_rules(GO + "Name three listings that have size M in stock.").quantifier,
                         "aggregate")
        self.assertEqual(form.from_rules(CHEAPEST_M).quantifier, "argmin")

    def test_a_named_comparison(self):
        two_urls = (f"Two sellers list it: {BASE}/example-tee-01.html (Seller A) and "
                    f"{BASE}/example-tee-02.html (Seller B). Which is cheaper for size M?")
        parsed = form.from_rules(two_urls)
        self.assertEqual((parsed.quantifier, parsed.population, parsed.kind()),
                         ("lookup", "listing", "named_lookup"))
        self.assertEqual(parsed.filter("url"),
                         Filter("url", "in", (f"{BASE}/example-tee-01.html", f"{BASE}/example-tee-02.html")))
        # Two sellers named on the page the box read.
        page_ = synthetic_page([31.40, 12.25, 19.50])
        parsed = form.from_rules(GO + "Is Seller B cheaper than Seller C for size M?", page_)
        self.assertEqual((parsed.quantifier, parsed.population), ("lookup", "results"))
        self.assertEqual(parsed.filter("seller"), Filter("seller", "in", ("Seller B", "Seller C")))
        # Two capitalised names in a comparison frame, with no page.
        parsed = form.from_rules("Of Harbour Lane Goods and Mellow Fields, which is cheaper for size M?")
        self.assertEqual(parsed.filter("seller"),
                         Filter("seller", "in", ("Harbour Lane Goods", "Mellow Fields")))
        # Near misses: no seller named, and a seller named inside a cheapest question, which
        # is still the best of the whole market.
        self.assertEqual(form.from_rules(CHEAPEST_M, page_).quantifier, "argmin")
        parsed = form.from_rules(GO + "Is Seller B the cheapest for size M?", page_)
        self.assertEqual((parsed.quantifier, parsed.filter("seller")), ("argmin", None))

    def test_a_filtered_cheapest(self):
        rated = form.from_rules(CHEAPEST_M[:-1] + " with rating at least 4.5?")
        self.assertEqual((rated.quantifier, rated.kind()), ("argmin", "total_bound"))
        self.assertEqual(rated.filter("rating"), Filter("rating", ">=", 4.5))
        white = form.from_rules(GO + "Which seller is cheapest for a tee in white, size M?")
        self.assertEqual(white.filter("colour"), Filter("colour", "=", "white"))
        capped = form.from_rules(CHEAPEST_M[:-1] + " under $30?")
        self.assertEqual(capped.filter("price"), Filter("price", "<=", 30.0))
        self.assertEqual(form.verify(capped), [])
        # Plain cheapest carries no such filter.
        plain = form.from_rules(CHEAPEST_M)
        self.assertEqual([f.attribute for f in plain.filters], ["size"])

    def test_a_single_listing_lookup(self):
        parsed = form.from_rules(f"On {BASE}/example-tee-01.html what is the price of size XL?")
        self.assertEqual((parsed.quantifier, parsed.objective, parsed.population, parsed.kind()),
                         ("lookup", "price", "listing", "named_lookup"))
        self.assertEqual(parsed.filters, (Filter("url", "in", (f"{BASE}/example-tee-01.html",)),
                                          Filter("size", "=", "XL")))
        stock = form.from_rules(f"On {BASE}/example-tee-01.html is size M available to buy?")
        self.assertEqual((stock.quantifier, stock.objective), ("lookup", "availability"))
        # A results URL is a market, not a listing.
        self.assertEqual(form.from_rules(CHEAPEST_M).population, "results")

    def test_the_dearest(self):
        parsed = form.from_rules(GO + "Which seller is the most expensive for size M?")
        self.assertEqual((parsed.quantifier, parsed.kind()), ("argmax", "argmax_price"))
        self.assertEqual(form.from_rules(CHEAPEST_M).quantifier, "argmin")

    def test_a_price_word_with_no_figure_is_an_unknown(self):
        vague = form.from_rules(GO + "Which seller has a cheap tee in M?")
        self.assertEqual((vague.unknowns, vague.evidence["unknowns"]), (("price limit",), "cheap"))
        self.assertEqual(vague.filter("size"), Filter("size", "=", "M"))
        for question in (GO + "Is there any seller under $20 for size M?",
                         GO + "Which seller is cheapest for size M?",
                         GO + "Is there a cheap tee in M under $20?"):
            with self.subTest(question=question):
                self.assertEqual(form.from_rules(question).unknowns, ())

    def test_a_review_question_carries_its_mention(self):
        parsed = form.from_rules(f"Go to {BASE}/review/product/list/id/230/ . Do any buyers report "
                                 "that this product leaks or arrives leaking? Answer yes or no.")
        self.assertEqual((parsed.quantifier, parsed.objective, parsed.population, parsed.kind()),
                         ("exists", "mention", "reviews", "depth_search"))
        self.assertEqual(parsed.filters, (Filter("review text", "contains", "leaks or arrives leaking"),))


class Shown(unittest.TestCase):
    """Property 5: what the shop shows, and a refusal for what it does not."""

    def test_what_the_shop_shows(self):
        self.assertEqual(form.attributes_shown(), {"seller", "title", "url", "advertised price",
                                                   "size", "price", "availability",
                                                   "review text", "review rating", "review page"})
        self.assertEqual(form.attributes_shown(synthetic_page([12.25])), form.attributes_shown())
        # The results-page part is the parser's own record of a listing.
        self.assertEqual({f.name for f in page.Listing.__dataclass_fields__.values()},
                         {"seller", "title", "url", "advertised"})

    def test_an_attribute_the_shop_does_not_show_fires(self):
        for question, missing in ((GO + "Which seller delivers fastest?", ["delivery time"]),
                                  (CHEAPEST_M[:-1] + " with free shipping?", ["shipping cost"]),
                                  (CHEAPEST_M[:-1] + " with rating at least 4.5?", ["rating"]),
                                  (GO + "Which seller is cheapest for a tee in white, size M?", ["colour"]),
                                  (GO + "Which seller gives the longest warranty?", ["warranty"])):
            with self.subTest(question=question):
                parsed = form.from_rules(question)
                self.assertEqual(form.not_shown(parsed), missing)
                self.assertIn(f"the shop does not show {missing[0]}", form.verify(parsed))
        fastest = form.from_rules(GO + "Which seller delivers fastest?")
        self.assertEqual((fastest.quantifier, fastest.objective), ("argmin", "attribute:delivery time"))

    def test_a_sold_out_size_has_no_price(self):
        listed = Form("argmin", "price", (Filter("availability", "=", "listed"),))
        self.assertEqual(form.not_shown(listed), ["the price of a sold-out size"])
        buyable = Form("argmin", "price", (Filter("availability", "=", "buyable"),))
        self.assertEqual(form.not_shown(buyable), [])
        count_listed = Form("count", "availability", (Filter("availability", "=", "listed"),))
        self.assertEqual(form.not_shown(count_listed), [])

    def test_the_refusal_names_what_is_missing_and_what_is_shown(self):
        text = form.refusal(["delivery time"])
        self.assertTrue(text.startswith("The shop does not show delivery time, so"))
        self.assertIn("advertised price", text)
        self.assertIn("review", text)


class Verify(unittest.TestCase):
    def test_the_four_properties_still_fire_through_the_planner(self):
        plan = form.plan_dict(form.from_rules(CHEAPEST_M))
        self.assertEqual(planner.properties(plan), [])
        self.assertNotEqual(planner.properties({**plan, "enumerate_first": False}), [])
        self.assertNotEqual(planner.properties({**plan, "forbidden_claims": []}), [])
        # `verify` is the same four plus the v1 text check, as before.
        self.assertEqual(planner.verify(plan), [])
        self.assertEqual(planner.verify({**plan, "kind": "exists_price"}),
                         ["no strategy text exists for kind 'exists_price'"])

    def test_the_new_kinds_have_sound_plans(self):
        for question in (GO + "Is there any seller under $20 for size M?",
                         GO + "Which are the three cheapest sellers for size M?",
                         GO + "Which seller is the most expensive for size M?",
                         f"On {BASE}/example-tee-01.html what is the price of size XL?"):
            with self.subTest(question=question):
                self.assertEqual(form.verify(form.from_rules(question)), [])

    def test_a_combination_no_primitive_plans_is_refused(self):
        self.assertEqual(form.verify(Form("exists", "rate")), ["no plan exists for kind 'exists_rate'"])
        self.assertEqual(form.verify(Form("lookup", "price")), ["a lookup names no listing"])


class Compose(unittest.TestCase):
    def setUp(self):
        self.page = synthetic_page([31.40, 12.25, 19.50])

    def test_the_quantifier_chooses_the_primitive(self):
        for quantifier, name in (("lookup", "lookup"), ("exists", "witness"),
                                 ("forall", "counterexample"), ("argmin", "bound_prune"),
                                 ("argmax", "bound_prune"), ("topk", "bound_prune"),
                                 ("count", "exhaust"), ("aggregate", "exhaust")):
            with self.subTest(quantifier=quantifier):
                built = Form(quantifier, "price", k=3 if quantifier == "topk" else None)
                self.assertEqual(primitives.primitive_for(built).name, name)
        reviews = Form("exists", "mention", population="reviews")
        self.assertEqual(primitives.primitive_for(reviews).name, "depth")
        self.assertEqual(set(primitives.PRIMITIVES), {"lookup", "witness", "counterexample",
                                                      "bound_prune", "exhaust", "depth", "filter"})

    def test_v1_kinds_render_their_v7_bodies_under_the_preamble(self):
        for task_id, question in clothing_questions().items():
            asked = ambiguity.ask(question)
            for reading in ((None,) if asked is None else ("menu", "buyable")):
                with self.subTest(task=task_id, reading=reading):
                    text = question if reading is None else ambiguity.with_reading(question, asked, reading)
                    plan = primitives.compose(form.from_rules(text, self.page), self.page)
                    self.assertEqual(plan.instruction, targeting.BODIES[plan.kind])
                    self.assertEqual(plan.text, f"{box.preamble(self.page)}\n\n{plan.instruction}")
                    self.assertEqual(plan.stop_rule, planner.STOP_RULES[plan.kind])

    def test_the_new_texts_carry_their_stop_rule_and_the_quarantine(self):
        exists = primitives.compose(form.from_rules(GO + "Is there any seller under $20 for size M?"), self.page)
        self.assertEqual(exists.primitive, "witness")
        self.assertIn("at or below $20.00", exists.instruction)
        self.assertIn("choose size M, then look at the page again", exists.instruction)
        self.assertIn("disabled or greyed out", exists.instruction)
        self.assertTrue(exists.instruction.endswith(targeting.QUARANTINE))
        top3 = primitives.compose(form.from_rules(GO + "Which are the three cheapest sellers for size M?"), self.page)
        self.assertEqual((top3.primitive, top3.kind), ("bound_prune", "topk_price"))
        self.assertIn("Keep the 3 cheapest available totals", top3.instruction)
        self.assertEqual(top3.stop_rule, planner.STOP_RULES["topk_price"].replace("{k}", "3"))
        self.assertTrue(top3.instruction.endswith(targeting.QUARANTINE))
        dearest = primitives.compose(form.from_rules(GO + "Which seller is the most expensive for size M?"), self.page)
        self.assertIn("no listing can be skipped", dearest.instruction)
        self.assertNotIn(targeting.QUARANTINE, dearest.instruction)
        named = primitives.compose(form.from_rules(GO + "Is Seller B cheaper than Seller C for size M?", self.page), self.page)
        self.assertEqual(named.primitive, "lookup")
        self.assertIn(f"- Seller B, {BASE}/example-tee-02.html", named.instruction)
        self.assertIn(f"- Seller C, {BASE}/example-tee-03.html", named.instruction)
        self.assertNotIn("Seller A", named.instruction.split("\n", 1)[1].split("In each one", 1)[0])
        self.assertNotIn(targeting.QUARANTINE, named.instruction)
        # Every new text starts with the same account of the market v1 gives.
        for plan in (exists, top3, dearest, named):
            self.assertTrue(plan.text.startswith(box.preamble(self.page) + "\n\n"))

    def test_candidates_follow_the_primitive(self):
        cheapest = primitives.compose(form.from_rules(CHEAPEST_M), self.page)
        self.assertEqual([c.seller for c in cheapest.candidates], ["Seller B", "Seller C", "Seller A"])
        named = primitives.compose(form.from_rules(GO + "Is Seller B cheaper than Seller C for size M?", self.page), self.page)
        self.assertEqual([c.seller for c in named.candidates], ["Seller B", "Seller C"])
        every = primitives.compose(form.from_rules(GO + "How many listings have size M in stock?"), self.page)
        self.assertEqual([c.seller for c in every.candidates], ["Seller A", "Seller B", "Seller C"])
        record = cheapest.record()
        self.assertEqual((record["primitives_version"], record["primitive"], record["kind"]),
                         (primitives.VERSION, "bound_prune", "total_bound"))
        self.assertEqual(record["candidates"][0], {"seller": "Seller B", "url": f"{BASE}/example-tee-02.html"})
        self.assertEqual(record["filters"], [{"attribute": "size", "op": "=", "value": "M"}])


class Checks(unittest.TestCase):
    """Each primitive's answer check on a fault it exists to find, and on a case it must
    leave alone. The page: 15 listings at $10.15, $11.15 ... $24.15, Seller A the cheapest."""

    def setUp(self):
        self.page = synthetic_page([round(10.15 + n, 2) for n in range(15)])
        self.by_seller = {item.seller: item for item in self.page.listings}

    def observed(self, *sellers: str) -> str:
        """What a run that landed on these listings reports, in the shape `listings_opened` reads."""
        return "\n".join(f"Page URL: {self.by_seller[s].url}\nPrice: $12.00" for s in sellers)

    def all_but(self, *sellers: str) -> str:
        return self.observed(*[item.seller for item in self.page.listings if item.seller not in sellers])

    def check(self, question: str, answer: str, text: str) -> dict:
        return primitives.check(form.from_rules(question, self.page), self.page, answer, text)

    def test_witness(self):
        exists = GO + "Is there any seller under $15 for size M?"
        yes = "Yes. Seller C has size M at $12.15."
        self.assertEqual(self.check(exists, yes, self.observed("Seller A", "Seller B"))["flag"],
                         "witness_not_opened")
        self.assertTrue(self.check(exists, yes, self.observed("Seller A", "Seller B", "Seller C"))["ok"])
        self.assertTrue(self.check(exists, "Yes, one is.", self.all_but())["ok"])
        # A no owes every listing the limit does not rule out: five are advertised at or below $15.
        no = "No. None of the sellers has size M under $15."
        self.assertEqual(self.check(exists, no, self.observed("Seller A", "Seller B", "Seller C"))["flag"],
                         "existence_denied_without_coverage")
        self.assertTrue(self.check(exists, no, self.observed("Seller A", "Seller B", "Seller C",
                                                             "Seller D", "Seller E"))["ok"])

    def test_bound_and_prune_for_the_k_cheapest(self):
        top3 = GO + "Which are the three cheapest sellers for size M?"
        answer = "1. Seller A $12.00, 2. Seller B $13.00, 3. Seller C $16.00."
        # The third's bound: six listings advertise at or below $16.00.
        opened_four = self.observed("Seller A", "Seller B", "Seller C", "Seller D")
        self.assertEqual(self.check(top3, answer, opened_four)["flag"], "superlative_without_coverage")
        opened_six = self.observed(*[f"Seller {c}" for c in "ABCDEF"])
        self.assertTrue(self.check(top3, answer, opened_six)["ok"])
        # Fewer than three prices named: the whole page is owed.
        self.assertEqual(self.check(top3, "Seller A $12.00 and Seller B $13.00.", opened_six)["flag"],
                         "superlative_without_coverage")

    def test_bound_and_prune_for_the_cheapest_and_the_dearest(self):
        answer = "Seller F is cheapest at $15.15 for size M."
        self.assertEqual(self.check(CHEAPEST_M, answer, self.observed("Seller A", "Seller B", "Seller C"))["flag"],
                         "superlative_without_coverage")
        self.assertTrue(self.check(CHEAPEST_M, answer, self.observed(*[f"Seller {c}" for c in "ABCDEF"]))["ok"])
        dearest = GO + "Which seller is the most expensive for size M?"
        self.assertEqual(self.check(dearest, "Seller O at $30.00.", self.all_but("Seller A"))["flag"],
                         "superlative_without_coverage")
        self.assertTrue(self.check(dearest, "Seller O at $30.00.", self.all_but())["ok"])
        headline = GO + "Which one advertises the lowest price on the results page?"
        self.assertTrue(self.check(headline, "Seller A at $10.15.", "")["ok"])

    def test_lookup(self):
        named = GO + "Is Seller B cheaper than Seller C for size M?"
        self.assertEqual(self.check(named, "Seller B, $13.00 against $14.00.", self.observed("Seller B"))["flag"],
                         "named_listing_not_opened")
        self.assertTrue(self.check(named, "Seller B, $13.00 against $14.00.",
                                   self.observed("Seller B", "Seller C"))["ok"])

    def test_counterexample(self):
        every = GO + "Does every listing have size M in stock? Answer yes or no."
        self.assertEqual(self.check(every, "No. Seller D lacks size M.", self.all_but("Seller D"))["flag"],
                         "counterexample_not_opened")
        self.assertTrue(self.check(every, "No. Seller D lacks size M.", self.observed("Seller D"))["ok"])
        self.assertEqual(self.check(every, "No.", self.observed("Seller A"))["flag"], "counterexample_not_opened")
        self.assertTrue(self.check(every, "No.", self.all_but())["ok"])
        # Naming the listing by its URL counts as naming it.
        self.assertTrue(self.check(every, "No. example-tee-04.html lacks M.", self.observed("Seller D"))["ok"])
        self.assertEqual(self.check(every, "No. example-tee-04.html lacks M.", self.observed("Seller A"))["flag"],
                         "counterexample_not_opened")
        self.assertEqual(self.check(every, "Yes, all of them.", self.all_but("Seller D"))["flag"],
                         "unverified_universal")
        self.assertTrue(self.check(every, "Yes, all of them.", self.all_but())["ok"])

    def test_exhaust(self):
        count = GO + "How many listings have size M in stock?"
        self.assertEqual(self.check(count, "5 of 15.", self.all_but("Seller D"))["flag"], "population_not_covered")
        self.assertTrue(self.check(count, "5 of 15.", self.all_but())["ok"])

    def test_the_filter_holds_the_answer_to_the_limit(self):
        exists = GO + "Is there any seller under $15 for size M?"
        above = self.check(exists, "Yes. Seller A has size M at $16.00.", self.observed("Seller A"))
        self.assertEqual((above["flag"], above["primitive"]), ("answer_above_limit", "witness"))
        self.assertTrue(self.check(exists, "Yes. Seller A has size M at $14.00.", self.observed("Seller A"))["ok"])
        self.assertTrue(self.check(exists, "No. The cheapest M is Seller A at $16.00.",
                                   self.observed(*[f"Seller {c}" for c in "ABCDE"]))["ok"])

    def test_depth_defers_to_the_sufficiency_rules(self):
        reviews = (f"Go to {BASE}/review/product/list/id/230/ . Do any buyers report that this "
                   "product leaks or arrives leaking? Answer yes or no.")
        verdict = self.check(reviews, "Yes: 'it leaked everywhere', page 2.", "Page URL: x\nit leaked everywhere")
        self.assertEqual((verdict["ok"], verdict["primitive"]), (True, "depth"))
        self.assertEqual(self.check(reviews, "Yes, and they got a $999.99 refund.", "nothing of the sort")["flag"],
                         "unsupported_number")


class ModelParser(unittest.TestCase):
    QUESTION = GO + "Is there any seller under $20 for size M?"

    def test_a_fake_call_returns_the_models_form(self):
        seen = []

        def call(prompt: str) -> str:
            seen.append(prompt)
            return "Here is the form:\n" + json.dumps({
                "quantifier": "exists", "objective": "price",
                "filters": [{"attribute": "price", "op": "<=", "value": 20},
                            {"attribute": "size", "op": "=", "value": "M"}],
                "population": "results", "k": None, "reading": None, "unknowns": [],
                "evidence": {"quantifier": "Is there any", "filters": "under $20, size M"}})

        parsed = form.from_model(self.QUESTION, None, call)
        self.assertEqual((parsed.source, parsed.quantifier, parsed.kind()), ("model", "exists", "exists_price"))
        self.assertEqual(parsed.filters, (Filter("price", "<=", 20), Filter("size", "=", "M")))
        self.assertEqual(parsed.evidence["quantifier"], "Is there any")
        # One call, carrying the question, the schema, the attributes and the properties.
        self.assertEqual(len(seen), 1)
        for needle in (self.QUESTION, '"quantifier"', "advertised price", "review rating",
                       "5. Every attribute", "delivery time"):
            self.assertIn(needle, seen[0])

    def test_a_malformed_reply_raises_with_the_fault_named(self):
        for reply, fault in (("I cannot parse that.", "no JSON object"),
                             ("{not json}", "does not parse"),
                             (json.dumps({"quantifier": "exists", "objective": "price"}), "lacks population"),
                             (json.dumps({"quantifier": "maybe", "objective": "price", "population": "results"}),
                              "quantifier 'maybe'"),
                             (json.dumps({"quantifier": "exists", "objective": "price", "population": "results",
                                          "filters": ["price under 20"]}), "a filter needs"),
                             (json.dumps({"quantifier": "topk", "objective": "price", "population": "results"}),
                              "k is None"),
                             (json.dumps([1, 2]), "JSON object")):
            with self.subTest(reply=reply):
                with self.assertRaises(ValueError) as refused:
                    form.from_model(self.QUESTION, None, lambda prompt: reply)
                self.assertIn(fault, str(refused.exception))


if __name__ == "__main__":
    unittest.main()
