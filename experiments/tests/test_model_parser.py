"""The model's front door, box v13 (22 October 2026): prompt version 2, the form's three new
fields, normalisation after the model, the checks a model's form must pass, `box.decide`
with the model parser, the negated universal, and what the suite, the probe and the
verifier's tools do with them.

Every model reply here is a stub, and nothing is sent. Every rule has a case where it fires
and one where it stays quiet, and the faults named here were planted in the code and seen to
fail these tests before the code was put back (LESSONS 31).
"""
import argparse
import contextlib
import dataclasses
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
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import claim  # noqa: E402
import form  # noqa: E402
import normalise  # noqa: E402
import page  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import planner  # noqa: E402
import primitives  # noqa: E402
import suite  # noqa: E402
import sufficiency  # noqa: E402
import targeting  # noqa: E402
import verify_cells  # noqa: E402
from form import Ambiguity, Filter, Form  # noqa: E402
from test_box import (BASE, FIXTURES, RESULTS_URL, clothing_questions, market_facts,  # noqa: E402
                      menu_log, openjiuwen_log, synthetic_page, thornwood_page)
from test_claim_arms import run_suite  # noqa: E402

GO = f"Go to {RESULTS_URL} . "
THORNWOOD = paths.RESULTS / "20261014T213118" / "suite.json"
PARAPHRASES = paths.TASKS / "paraphrases_v1.json"
# The question the student asked to see under both parsers.
MEDIUM = ("Go to http://localhost:7770/catalogsearch/result/?q=Thornwood . Which seller is "
          "cheapest for size medium among the Thornwood listings?")
# Prompt version 1 for the question below, as it was sent before version 2 existed: the
# sha256 of `form.prompt` at 447d285, taken on 22 October 2026 before form.py changed.
V1_QUESTION = GO + "Is there any seller under $20 for size M?"
V1_PROMPT_SHA256 = "e1d59dbf5fb4e72f3ee7e76fcbdfaec6277cd8a56242e8b4f0f040603986795b"
# Prompt version 2 for the same question: the sha256 of `form.prompt` at 39e747b, whose form.py
# is d357c72's, taken on 23 October 2026 before version 3 existed, so the probes and runs made
# under it can be reproduced.
V2_PROMPT_SHA256 = "96ff5fa3777250082e55bf4b82ff83dec20e7f6dbaa2d071d89504266b182b2b"


def reply(**fields) -> str:
    """A model's reply in prompt version 2's schema: the fields given, the rest empty."""
    data = {"quantifier": "argmin", "objective": "price", "filters": [], "population": "results",
            "k": None, "negated": False, "reading": None, "unknowns": [], "ambiguities": [],
            "evidence": {}}
    data.update(fields)
    return "Here is the form:\n" + json.dumps(data)


def f(attribute: str, op: str, value) -> dict:
    return {"attribute": attribute, "op": op, "value": value}


def stub(text: str):
    """A call that answers every prompt with `text`, keeping each prompt it was sent."""
    def call(prompt: str) -> str:
        call.prompts.append(prompt)
        return text
    call.prompts = []
    return call


def never(prompt: str) -> str:
    raise AssertionError("the model was called")


def named_page() -> page.Page:
    """Made-up sellers on a search for "Example", two of whose names share a word, each
    titled the way the shop titles its listings. `ModelPath` checks they are nobody's."""
    names = ["Harbour Lane Goods", "Harbour Mill Supply", "Mellow Fields", "Quarry Street Outfitters"]
    prices = [21.40, 12.25, 19.50, 15.75]
    listings = [page.Listing(seller=name, title=f"Example Heavyweight Tee - {name}",
                             url=f"{BASE}/example-tee-{n + 1:02d}.html", advertised=price)
                for n, (name, price) in enumerate(zip(names, prices))]
    return page.Page(url=RESULTS_URL, listings=listings, total=len(listings), next_page=False)


def stored_thornwood() -> page.Page:
    """The Thornwood results page as the box read it in batch 20261014T213118."""
    return parse_probe.stored_page(THORNWOOD)


def every_question() -> list[str]:
    """Every question the project holds: the task files, the census and the paraphrases."""
    found = [question for _, question in planner.questions()]
    for name in ("tasks_apparel_v2.json", "tasks_claim_apparel.json"):
        spec = json.loads((paths.TASKS / name).read_text())
        found += [task["query"].format(base=spec["base_url"]) for task in spec["tasks"]]
    found += [entry["question"] for entry in parse_probe.load_questions(PARAPHRASES)[1]]
    return found


# ---------------------------------------------------------------------------
# 1. The form's three new fields

class FormV10(unittest.TestCase):
    def test_an_ambiguity_needs_its_words_and_two_distinct_readings(self):
        self.assertEqual(Ambiguity("offer", ("listed", "buyable")).record(),
                         {"word": "offer", "readings": ["listed", "buyable"]})
        for label, build in {
            "no words": lambda: Ambiguity("  ", ("listed", "buyable")),
            "words that are not text": lambda: Ambiguity(None, ("listed", "buyable")),
            "one reading": lambda: Ambiguity("offer", ("listed",)),
            "readings not a tuple": lambda: Ambiguity("offer", ["listed", "buyable"]),
            "an empty reading": lambda: Ambiguity("offer", ("listed", " ")),
            "a reading that is not text": lambda: Ambiguity("offer", ("listed", 2)),
            "the same reading twice": lambda: Ambiguity("offer", ("Listed", "listed")),
            "a dict for an Ambiguity": lambda: Form("argmin", "price", ambiguities=({"word": "x"},)),
            "a list of them": lambda: Form("argmin", "price", ambiguities=[]),
        }.items():
            with self.subTest(fault=label), self.assertRaises(ValueError):
                build()

    def test_a_reply_with_a_malformed_ambiguity_is_refused_by_name(self):
        for bad, words in ((["offer"], "needs a word and a list of readings"),
                           ([{"word": "offer", "readings": "listed or buyable"}], "needs a word and a list"),
                           ([{"word": "offer", "readings": ["listed"]}], "two or more readings"),
                           ({"word": "offer"}, "ambiguities must be a list")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, words):
                form.parse_reply(reply(ambiguities=bad))
        parsed = form.parse_reply(reply(ambiguities=[{"word": "offer", "readings": ["listed", "buyable"]}]))
        self.assertEqual(parsed.ambiguities, (Ambiguity("offer", ("listed", "buyable")),))

    def test_negated_is_for_a_universal_and_is_true_or_false(self):
        self.assertEqual(Form("forall", "availability", negated=True).kind(), "negated_refutation")
        self.assertEqual(Form("forall", "availability").kind(), "refutation")
        for label, build in {
            "an existence question": lambda: Form("exists", "price", negated=True),
            "a word for true": lambda: Form("forall", "availability", negated="yes"),
            "a reply's string": lambda: form.parse_reply(reply(quantifier="forall", objective="availability",
                                                               negated="false")),
        }.items():
            with self.subTest(fault=label), self.assertRaises(ValueError):
                build()
        # A null is read as false, as a missing field is.
        self.assertFalse(form.parse_reply(reply(negated=None)).negated)

    def test_the_prompt_version_is_recorded(self):
        question = GO + "Which seller is cheapest for size M?"
        self.assertEqual(form.from_model(question, None, stub(reply())).prompt_version, form.PROMPT_VERSION)
        self.assertEqual(form.PROMPT_VERSION, 4)     # 4 since 24 October 2026 (test_design_b.PromptV4)
        self.assertEqual(form.parse_reply(reply(), version=1).prompt_version, 1)
        self.assertIsNone(form.from_rules(question).prompt_version)
        for bad in (0, True, "2"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Form("argmin", "price", prompt_version=bad)

    def test_a_record_written_before_v10_reads_as_before_and_a_v10_one_round_trips(self):
        rows = json.loads(THORNWOOD.read_text())["rows"]
        stored = next(row["box"]["form"] for row in rows if (row.get("box") or {}).get("form"))
        self.assertNotIn("negated", stored)
        old = form.from_record(stored, "rules")
        self.assertEqual((old.negated, old.ambiguities, old.prompt_version), (False, (), None))
        new = Form("forall", "availability", (Filter("size", "=", "M"),), negated=True, source="model",
                   ambiguities=(Ambiguity("have", ("listed", "buyable")),), prompt_version=2)
        self.assertEqual(form.from_record(new.record(), "model"), new)
        self.assertEqual((new.record()["kind"], new.record()["negated"]), ("negated_refutation", True))

    def test_the_rules_never_set_them(self):
        page_ = stored_thornwood()
        for question in every_question():
            with self.subTest(question=question[-60:]):
                parsed = form.from_rules(question, page_)
                self.assertEqual((parsed.negated, parsed.ambiguities, parsed.prompt_version), (False, (), None))

    def test_a_negated_universal_is_planned_only_over_a_sizes_availability(self):
        why = "a negated universal is planned only over the availability of a size it names"
        self.assertEqual(form.verify(Form("forall", "availability", (Filter("size", "=", "M"),), negated=True)), [])
        for broken in (Form("forall", "availability", negated=True),
                       Form("forall", "price", (Filter("size", "=", "M"),), negated=True)):
            with self.subTest(form=broken):
                self.assertIn(why, form.verify(broken))
        # Not negated, the same forms are judged as they always were.
        self.assertNotIn(why, form.verify(Form("forall", "availability")))


# ---------------------------------------------------------------------------
# 2. Prompt version 2

class PromptV3(unittest.TestCase):
    """Version 3 (23 October 2026, the verifier's fairness audit of d357c72): version 2 with
    the two sentences of its context that were false of the shop made true."""

    def test_version_2_is_kept_byte_for_byte(self):
        sent = form.prompt(V1_QUESTION, version=2)
        self.assertEqual(hashlib.sha256(sent.encode()).hexdigest(), V2_PROMPT_SHA256)
        self.assertTrue(sent.startswith(form.CONTEXT + "\n\n"))

    def test_version_3_is_version_2_with_its_context_corrected(self):
        two, three = form.prompt(V1_QUESTION, version=2), form.prompt(V1_QUESTION, version=3)
        self.assertEqual(three, form.CONTEXT_V3 + two[len(form.CONTEXT):])
        for false in ("lists competing listings for one product", "Reviews of a listing are on their own pages"):
            with self.subTest(sentence=false):
                self.assertIn(false, two)
                self.assertNotIn(false, three)
        for true in ("for one product or for several", "A listing that has reviews has them on their own "
                     "pages", "many listings have none"):
            with self.subTest(sentence=true):
                self.assertIn(true, three)
        # It names no market: no brand the shop's generated markets were seeded under.
        for brand in ("Larchmere", "Thornwood", "Ashcombe", "Rivenhall", "Calderwood"):
            self.assertNotIn(brand, form.CONTEXT_V3)


class PromptV2(unittest.TestCase):
    def test_version_1_is_kept_byte_for_byte(self):
        sent = form.prompt(V1_QUESTION, version=1)
        self.assertEqual(hashlib.sha256(sent.encode()).hexdigest(), V1_PROMPT_SHA256)
        self.assertNotIn("Worked examples", sent)
        with self.assertRaises(ValueError):
            form.prompt(V1_QUESTION, version=5)

    def test_version_2_says_what_the_task_asked_and_ends_with_the_question(self):
        # Version 3's words, the current prompt until version 4 (24 October 2026).
        sent = form.prompt(V1_QUESTION, version=3)
        self.assertEqual(sent, form.prompt(V1_QUESTION, stored_thornwood(), version=3))
        self.assertTrue(sent.endswith(f"\n\nThe question:\n{V1_QUESTION}"))
        self.assertEqual(sent.count("The question:\n"), 1)
        for needle in ("name their sizes S, M, L and XL",
                       "small is S, medium is M, large is L and extra large is XL",
                       '"price limit"', "do not make it a filter", '"ambiguities"', '"negated"',
                       '["listed", "buyable"]', "No other kind has a plan", "5. Every attribute",
                       "restates the product or the brand", '"listing" only when it gives product page URLs'):
            with self.subTest(needle=needle):
                self.assertIn(needle, sent)

    def test_the_kinds_listed_are_the_kinds_the_planner_plans(self):
        self.assertEqual(sorted(kind for kind, _, _ in form.PLANNABLE), sorted(planner.QUANTIFIERS))
        sent = form.prompt(V1_QUESTION)
        for _, what, shape in form.PLANNABLE:
            self.assertIn(f"- {what}: {shape}\n", sent)

    def test_every_kind_has_a_worked_example_and_each_is_its_kind(self):
        sent = form.prompt(V1_QUESTION)
        self.assertEqual(set(planner.QUANTIFIERS) - {kind for kind, _, _ in form.EXAMPLES}, set())
        for kind, question, example in form.EXAMPLES:
            with self.subTest(question=question[-60:]):
                self.assertEqual(form.from_record(example, "model").kind(), kind)
                self.assertIn(f"Question: {question}\nForm: {json.dumps(example)}\n", sent)

    def test_every_example_is_what_the_box_does_with_it(self):
        # Each example's form, given to the box as the reply to its own question on a page
        # with the example's sellers, is used as written, unchanged, and gives the outcome
        # the example is there to show: a plan of its kind, an ask, or, for the attribute
        # the shop does not show, the rules' refusal. The page also lists the jacket the
        # URL example names, since a lookup of a listing the page does not list is asked
        # about (box v14, `box.unlisted`).
        page_ = named_page()
        jacket = page.Listing(seller="Quarry Street Outfitters", title="Example Jacket - Quarry Street Outfitters",
                              url="http://localhost:7770/example-jacket-04.html", advertised=48.00)
        page_ = dataclasses.replace(page_, listings=page_.listings + [jacket], total=page_.total + 1)
        asks = {"Is size L offered by every Example listing?": "reading",
                "How many Example listings carry an extra large?": "reading",
                "Find me an inexpensive Example jacket in size M.": "price limit",
                "What is the price of the Example jacket in size M?": "other"}
        for kind, question, example in form.EXAMPLES:
            with self.subTest(question=question[-60:]):
                found = parse_probe.outcome(question, page_, reply=json.dumps(example))
                decision = box.decide(question, page_, parser="model", call=stub(json.dumps(example)))
                self.assertEqual(decision.parse.changes, ())
                words = question.split(" . ", 1)[-1]
                if words in asks:
                    self.assertEqual((found["outcome"], found["ask"], found["parsed_by"]),
                                     ("ask", asks[words], "model"))
                elif kind == "argmin_delivery_time":
                    # Refused, by the rules: the example's question says "ships", which the
                    # rules read as availability = buyable, and its form leaves that out, so
                    # since box v15 it is not a form the model may decline on, which needs
                    # nothing else wrong with it (`test_model_decline`).
                    self.assertEqual((found["outcome"], found["parsed_by"], found["declined"]),
                                     ("refuse", "rules", False))
                    self.assertIn("the shop does not show delivery time", found["fallback_reason"])
                    self.assertIn("the question's 'ships' gives availability = 'buyable'", found["fallback_reason"])
                else:
                    self.assertEqual((found["outcome"], found["kind"], found["parsed_by"]),
                                     ("plan", kind, "model"))

    def test_no_example_copies_a_reworded_question(self):
        # The examples may be written from the templates, never from paraphrases_v1.json:
        # every run of four words an example shares with a paraphrase is a template's own.
        def grams(text: str) -> set[tuple[str, ...]]:
            words = re.findall(r"[a-z0-9$]+", text.lower())
            return {tuple(words[n:n + 4]) for n in range(len(words) - 3)}

        templates = set()
        for name in ("tasks_apparel.json", "tasks_apparel_v2.json"):
            for task in json.loads((paths.TASKS / name).read_text())["tasks"]:
                templates |= grams(task["query"])
        reworded = [entry["text"] for entry in json.loads(PARAPHRASES.read_text())["paraphrases"]]
        for _, question, _ in form.EXAMPLES:
            for text in reworded:
                with self.subTest(example=question[-50:], paraphrase=text[:50]):
                    self.assertEqual((grams(question) & grams(text)) - templates, set())
        # The check finds a copy: a paraphrase with its brand changed shares its every four words.
        copied = reworded[6].replace("Thornwood", "Example")
        self.assertTrue((grams(copied) & grams(reworded[6])) - templates)

    def test_the_examples_name_no_market_seller_or_price(self):
        sellers, prices = market_facts()
        text = form.worked_examples()
        self.assertEqual([seller for seller in sellers if seller in text], [])
        self.assertEqual([p for p in prices if re.search(rf"(?<![\d.]){re.escape(p)}(?!\d)", text)], [])
        # Made-up pages in these tests are nobody's either.
        for item in named_page().listings:
            self.assertNotIn(item.seller, sellers)
            self.assertNotIn(f"{item.advertised:.2f}", prices)

    def test_the_size_words_are_the_generated_clothing_markets(self):
        # Prompts 2 and 3 say the listings whose price depends on the size name their sizes S,
        # M, L and XL. Checked here against both clothing markets the shop was seeded from;
        # the box itself never reads a fixture. Since normalisation v5 (24 October 2026) the
        # shop's sizes are six, XS and XXL the design B markets' too, so each of those
        # markets' sizes is among them (tests/test_design_b.py, SizeXS).
        for name in ("scaled_apparel.json", "claim_apparel.json"):
            with self.subTest(market=name):
                fixture = json.loads((paths.FIXTURES / name).read_text())
                options = {v["option"] for family in fixture["families"] for v in family["variants"]}
                self.assertEqual(options, {"S", "M", "L", "XL"})
                self.assertLessEqual(options, set(normalise.SIZES))
        self.assertIn("S, M, L and XL", form.SIZES)


# ---------------------------------------------------------------------------
# 3. Normalisation

class Normalise(unittest.TestCase):
    def setUp(self):
        self.page = named_page()

    def normalised(self, question: str | None = None, page_=None, **fields) -> tuple[Form, list[str]]:
        raw = form.parse_reply(reply(**fields))
        return normalise.normalise(raw, question or GO + "Which seller is cheapest?",
                                   self.page if page_ is None else page_)

    def test_sizes_take_the_shops_names(self):
        for value, op, want in (("medium", "=", "M"), ("Medium", "=", "M"), ("small", "=", "S"),
                                ("large", "=", "L"), ("extra large", "=", "XL"), ("extra-large", "=", "XL"),
                                ("m", "=", "M"), ("xl", "=", "XL"), ("size L", "=", "L"),
                                ("M", "contains", "M"), (["M"], "in", "M")):
            with self.subTest(value=value, op=op):
                got, changes = self.normalised(filters=[f("size", op, value)])
                self.assertEqual(got.filter("size"), Filter("size", "=", want))
                self.assertEqual(len(changes), 1)
                self.assertEqual(got.evidence["normalised:size"], changes[0])
        # The shop's own words and a pack size stay as they are, with nothing recorded.
        for value in ("M", "XL", "2 x 9.5L"):
            with self.subTest(value=value):
                got, changes = self.normalised(filters=[f("size", "=", value)])
                self.assertEqual((got.filter("size").value, changes), (value, []))
                self.assertNotIn("normalised:size", got.evidence)
        # Two sizes stay two, for the checks to refuse.
        got, _ = self.normalised(filters=[f("size", "in", ["M", "L"])])
        self.assertEqual(got.filter("size"), Filter("size", "in", ("M", "L")))

    def test_sellers_take_the_pages_names(self):
        lookup = dict(quantifier="lookup")
        for value, want, how in ((["harbour lane goods"], ("Harbour Lane Goods",), "matched by case"),
                                 (["Mellow"], ("Mellow Fields",), "matched as whole words"),
                                 (["Quarry Street Outfitters listing"], ("Quarry Street Outfitters",),
                                  "matched as whole words"),
                                 (["Harbour"], ("Harbour",), "unmatched: 'Harbour' matches 2 of the page's sellers"),
                                 (["Seller Z"], ("Seller Z",), "unmatched: 'Seller Z' matches no seller on the page"),
                                 (["Mellow", "mellow fields"], ("Mellow Fields",), "matched as whole words")):
            with self.subTest(value=value):
                got, changes = self.normalised(filters=[f("seller", "in", value)], **lookup)
                self.assertEqual(got.filter("seller").value, want)
                self.assertIn(how, " ".join(changes))
                self.assertIn("normalised:seller", got.evidence)
        # One seller written with "=" is a set of one, the shape every plan reads.
        got, changes = self.normalised(filters=[f("seller", "=", "Mellow Fields")], **lookup)
        self.assertEqual(got.filter("seller"), Filter("seller", "in", ("Mellow Fields",)))
        self.assertEqual(len(changes), 1)
        # The page's own names: nothing to change.
        got, changes = self.normalised(filters=[f("seller", "in", ["Mellow Fields", "Harbour Lane Goods"])], **lookup)
        self.assertEqual((got.filter("seller").value, changes), (("Mellow Fields", "Harbour Lane Goods"), []))
        # With no page there is nothing to match against, and the record says so.
        raw = form.parse_reply(reply(filters=[f("seller", "in", ["mellow fields"])], **lookup))
        got, changes = normalise.normalise(raw, GO + "x", None)
        self.assertEqual((got.filter("seller").value, changes),
                         (("mellow fields",), ["seller: unmatched: 'mellow fields' no page to match against"]))

    def test_a_url_is_a_set(self):
        url = f"{BASE}/example-tee-01.html"
        got, changes = self.normalised(quantifier="lookup", population="listing", filters=[f("url", "=", url)])
        self.assertEqual((got.filter("url"), len(changes)), (Filter("url", "in", (url,)), 1))
        got, changes = self.normalised(quantifier="lookup", population="listing", filters=[f("url", "in", [url])])
        self.assertEqual((got.filter("url"), changes), (Filter("url", "in", (url,)), []))

    def test_a_title_filter_that_restates_the_page_is_dropped(self):
        # On a search for Example, every listing an Example Heavyweight Tee.
        for value in ("Example", "tee", "Tees", "Example Heavyweight Tee", "the Example tee"):
            with self.subTest(value=value):
                got, changes = self.normalised(filters=[f("title", "contains", value), f("size", "=", "M")])
                self.assertEqual([c.attribute for c in got.filters], ["size"])
                self.assertEqual(len(changes), 1)
                self.assertIn(f"dropped title contains {value!r}", changes[0])
                self.assertEqual(got.evidence["normalised:title"], changes[0])
        _, changes = self.normalised(filters=[f("title", "contains", "Example")])
        self.assertEqual(changes, ["dropped title contains 'Example': every listing's title names "
                                   "'example heavyweight tee' and the results page is the search for 'Example'"])
        # A word some listing's title lacks narrows the market: kept, for the checks to refuse.
        for value in ("v-neck", "cotton", "Example v-neck"):
            with self.subTest(value=value):
                got, changes = self.normalised(filters=[f("title", "contains", value)])
                self.assertEqual((got.filter("title").value, changes), (value, []))
        # A page read back from a run record keeps no titles: only the search words restate.
        stored = stored_thornwood()
        got, _ = self.normalised(filters=[f("title", "contains", "Thornwood")], page_=stored)
        self.assertIsNone(got.filter("title"))
        got, _ = self.normalised(filters=[f("title", "contains", "tee")], page_=stored)
        self.assertEqual(got.filter("title").value, "tee")
        # With no page nothing is known to restate.
        raw = form.parse_reply(reply(filters=[f("title", "contains", "Example")]))
        self.assertEqual(normalise.normalise(raw, GO + "x", None)[0].filter("title").value, "Example")

    def test_a_listing_population_with_no_product_page_is_the_results_page(self):
        got, changes = self.normalised(population="listing", filters=[f("size", "=", "M")])
        self.assertEqual(got.population, "results")
        self.assertTrue(changes[0].startswith("population listing is results"))
        url = f"{BASE}/example-tee-01.html"
        for population, filters in (("listing", [f("url", "in", [url])]), ("results", []), ("reviews", [])):
            with self.subTest(population=population):
                got, changes = self.normalised(quantifier="lookup", population=population, filters=filters)
                self.assertEqual((got.population, changes), (population, []))

    def test_a_price_word_with_no_figure_is_the_price_limit(self):
        question = GO + "Is there an affordable tee in size M?"
        exists = dict(quantifier="exists", filters=[f("size", "=", "M")])
        for unknowns in (["affordable"], ["price threshold for affordability"], ["affordable", "price limit"]):
            with self.subTest(unknowns=unknowns):
                got, changes = self.normalised(question, unknowns=unknowns, **exists)
                self.assertEqual((got.unknowns, got.evidence["unknowns"]), (("price limit",), "affordable"))
                self.assertTrue(changes)
        # An ambiguity that is only a price word is the price limit too.
        got, changes = self.normalised(question, ambiguities=[{"word": "affordable",
                                                               "readings": ["under $20", "under $30"]}], **exists)
        self.assertEqual((got.unknowns, got.ambiguities, got.evidence["unknowns"]), (("price limit",), (), "affordable"))
        # The word quoted is the question's own, not the model's.
        got, changes = self.normalised(question, unknowns=["price limit"], evidence={"unknowns": "cheap"}, **exists)
        self.assertEqual(got.evidence["unknowns"], "affordable")
        self.assertIn("not 'cheap'", changes[0])
        # Quiet: another unknown, and a limit quoted from the question already.
        for unknowns, evidence in ((["delivery time"], {}), (["price limit"], {"unknowns": "affordable"})):
            with self.subTest(unknowns=unknowns):
                got, changes = self.normalised(question, unknowns=unknowns, evidence=evidence, **exists)
                self.assertEqual((got.unknowns, changes), (tuple(unknowns), []))

    def test_a_limit_written_as_text_is_a_number(self):
        for value in ("20", "$20", "20.00", " 20 "):
            with self.subTest(value=value):
                got, changes = self.normalised(quantifier="exists", filters=[f("price", "<", value)])
                self.assertEqual((got.filter("price"), len(changes)), (Filter("price", "<", 20.0), 1))
        for value in (20, 20.5, "affordable"):
            with self.subTest(value=value):
                got, changes = self.normalised(quantifier="exists", filters=[f("price", "<", value)])
                self.assertEqual((got.filter("price").value, changes), (value, []))

    def test_the_fault_planted(self):
        # With the size words silenced, "medium" stays, and the counterexample check reads a
        # complete size menu that has M as one that lacks the size asked about, so a bare No
        # to "does every listing have a medium" would pass on a listing that has it
        # (LESSONS 31).
        raw = form.parse_reply(reply(quantifier="forall", objective="availability",
                                     filters=[f("size", "=", "medium")]))
        key = sufficiency.listing_key(self.page.listings[0].url)
        menus = {key: sufficiency.MenuReading({"S": True, "M": True}, True)}
        with mock.patch.object(normalise, "size_of", lambda value: None):
            planted, changes = normalise.normalise(raw, MEDIUM, self.page)
        self.assertEqual((planted.filter("size").value, changes), ("medium", []))
        self.assertIsNotNone(primitives.counterexample_seen(planted, self.page, {key}, menus))
        fixed, _ = normalise.normalise(raw, MEDIUM, self.page)
        self.assertIsNone(primitives.counterexample_seen(fixed, self.page, {key}, menus))


# ---------------------------------------------------------------------------
# 4. The checks a model's form must pass

class Checks(unittest.TestCase):
    def setUp(self):
        self.page = named_page()

    def problems(self, question: str, **fields) -> list[str]:
        got, _ = normalise.normalise(form.parse_reply(reply(**fields)), question, self.page)
        return normalise.problems(got, question, self.page)

    def test_what_an_ask_needs(self):
        affordable = GO + "Is there an affordable tee in size M?"
        exists = dict(quantifier="exists", filters=[f("size", "=", "M")])
        fires = {
            "an attribute the shop does not show": (GO + "Which seller ships quickest?",
                                                    dict(objective="attribute:delivery time"),
                                                    "the shop does not show delivery time"),
            "an ambiguous word the question lacks": (GO + "Which seller is cheapest for size M?",
                                                     dict(filters=[f("size", "=", "M")], ambiguities=[
                                                         {"word": "offer", "readings": ["listed", "buyable"]}]),
                                                     "the ambiguous word 'offer' is not the question's"),
            "a price limit with no price word": (GO + "Is there a tee in size M?",
                                                 dict(unknowns=["price limit"], **exists),
                                                 "no price word of the question"),
            "a price limit beside a figure": (GO + "Is there an affordable tee in size M under $20?",
                                              dict(unknowns=["price limit"], **exists),
                                              "the question gives a figure"),
        }
        for label, (question, fields, words) in fires.items():
            with self.subTest(fault=label):
                self.assertTrue(any(words in p for p in self.problems(question, **fields)),
                                self.problems(question, **fields))
        # Quiet: a price limit the question names, whose plan waits on the user's figure.
        self.assertEqual(self.problems(affordable, unknowns=["price limit"],
                                       evidence={"unknowns": "affordable"}, **exists), [])
        self.assertEqual(self.problems(GO + "Does every listing offer size M?", quantifier="forall",
                                       objective="availability", filters=[f("size", "=", "M")],
                                       ambiguities=[{"word": "offer", "readings": ["listed", "buyable"]}]), [])

    def test_what_a_plan_needs_of_its_filters(self):
        question = GO + "Which seller is cheapest for size M?"
        size = f("size", "=", "M")
        fires = {
            "a seller on the cheapest of the market": (dict(filters=[f("seller", "in", ["Mellow Fields"]), size]),
                                                       "a total_bound plan does not carry a filter on seller"),
            "a size on the results page": (dict(objective="advertised price", filters=[size]),
                                           "a results_page plan does not carry a filter on size"),
            "a title that narrows": (dict(filters=[f("title", "contains", "v-neck"), size]),
                                     "does not carry a filter on title"),
            "review text off the reviews": (dict(filters=[f("review text", "contains", "leak"), size]),
                                            "does not carry a filter on review text"),
            "a floor for a limit": (dict(filters=[f("price", ">=", 20), size]),
                                    "a price filter is a limit below a figure, not price >= 20"),
            "a limit that is no number": (dict(filters=[f("price", "<=", "affordable"), size]),
                                          "a price filter is a limit below a figure"),
            "an existence with no limit": (dict(quantifier="exists", filters=[size]),
                                           "an existence question about a price names no price limit"),
            "two sizes": (dict(filters=[f("size", "in", ["M", "L"])]), "a size filter names one size"),
            "availability in other words": (dict(filters=[size, f("availability", "=", "in stock")]),
                                            "availability is listed or buyable"),
            "a size twice": (dict(filters=[size, f("size", "=", "L")]), "the form filters on size twice"),
            "a kind no plan exists for": (dict(quantifier="exists", objective="attribute:seller", filters=[size]),
                                          "no plan exists for kind"),
        }
        for label, (fields, words) in fires.items():
            with self.subTest(fault=label):
                found = self.problems(question, **fields)
                self.assertTrue(any(words in p for p in found), found)
        # Quiet: the plans the rules make, written by a model, each for a question that says
        # what the form holds (since normalisation v2 a form must not state what its question
        # does not: `Conflicts`).
        for asked, fields in (
                (question, dict(filters=[size])),
                (GO + "Which seller is cheapest for size M in stock?",
                 dict(filters=[size, f("availability", "=", "buyable")])),
                (GO + "Is there any seller under $20 for size M?",
                 dict(quantifier="exists", filters=[size, f("price", "<", 20)])),
                (GO + "Is Mellow Fields cheaper than Harbour Lane Goods for size M?",
                 dict(quantifier="lookup", filters=[f("seller", "in", ["Mellow Fields", "Harbour Lane Goods"]),
                                                    size])),
                (GO + "Which listing advertises the lowest price on the results page?",
                 dict(objective="advertised price"))):
            with self.subTest(sound=fields):
                self.assertEqual(self.problems(asked, **fields), [])

    def test_the_rules_own_forms_pass_every_check(self):
        # The checks hold a model's form to what the rules' forms already are: every form
        # the rules plan, on every question the project holds and under each reading, has no
        # problem the five properties do not already name.
        page_ = stored_thornwood()
        planned = 0
        for question in every_question():
            for reading in (None, "menu", "buyable"):
                try:
                    decision = box.decide(question, page_, reply=reading)
                except ValueError:
                    continue
                if decision.plan is None:
                    continue
                planned += 1
                with self.subTest(question=question[-60:], reading=reading):
                    self.assertEqual(normalise.plan_problems(decision.form, page_), [])
        self.assertGreater(planned, 100)


# ---------------------------------------------------------------------------
# 5. box.decide with the model parser

class ModelPath(unittest.TestCase):
    def setUp(self):
        self.thornwood = stored_thornwood()
        self.page = named_page()

    def test_a_sound_model_form_is_used_and_both_forms_are_recorded(self):
        call = stub(reply(filters=[f("size", "=", "medium"), f("title", "contains", "Thornwood")],
                          population="listing", evidence={"quantifier": "cheapest"}))
        decision = box.decide(MEDIUM, self.thornwood, parser="model", call=call)
        self.assertEqual(call.prompts, [form.prompt(MEDIUM, self.thornwood)])
        self.assertEqual((decision.kind, decision.form.source, decision.form.filters, decision.form.population),
                         ("total_bound", "model", (Filter("size", "=", "M"),), "results"))
        record = decision.record()
        parse = record["parse"]
        self.assertEqual((parse["parser"], parse["used"], parse["fallback_reason"], parse["prompt_version"],
                          parse["normalise_version"]), ("model", "model", None, form.PROMPT_VERSION,
                                                       normalise.VERSION))
        self.assertEqual(parse["model_form"], record["form"])
        self.assertEqual(parse["rules_form"], form.from_rules(MEDIUM, self.thornwood).record())
        self.assertEqual(parse["model_raw"]["filters"], [f("size", "=", "medium"), f("title", "contains", "Thornwood")])
        self.assertEqual(parse["changes"], [
            "size = 'medium' is size = 'M'",
            "dropped title contains 'Thornwood': the results page is the search for 'Thornwood'",
            "population listing is results: the question names no product page, so the listings it "
            "means are the results page's"])
        self.assertEqual(parse["reply"], call(""))
        # The rules read no size here and plan the same kind; the fixed text of the bound is
        # the same bytes either way, and the forms are what differ.
        rules = box.decide(MEDIUM, self.thornwood)
        self.assertEqual((rules.kind, rules.form.filter("size"), rules.query), ("total_bound", None, decision.query))

    def test_a_model_that_fails_leaves_the_rules_decision_and_says_why(self):
        rules = box.decide(MEDIUM, self.thornwood)

        def raising(prompt: str) -> str:
            raise requests.exceptions.Timeout("read timed out")

        cases = {
            "a call that fails": (raising, "the model call failed: Timeout: read timed out", False),
            "a reply that holds no JSON": (stub("I cannot parse that."),
                                           "the model's reply is not a form: the model's reply holds no JSON", False),
            "a reply outside the vocabulary": (stub(reply(quantifier="sometimes")),
                                               "the model's reply is not a form: quantifier 'sometimes'", False),
            "a form that needs what the shop lacks": (stub(reply(objective="attribute:delivery time")),
                                                      "the shop does not show delivery time", True),
            "a form no plan carries": (stub(reply(filters=[f("seller", "in", ["Rookwood Uniforms"]),
                                                           f("size", "=", "M")])),
                                       "a total_bound plan does not carry a filter on seller", True),
            "a kind no plan exists for": (stub(reply(quantifier="topk", k=3, objective="advertised price")),
                                          "no plan exists for kind 'topk_advertised_price'", True),
        }
        for label, (call, words, has_form) in cases.items():
            with self.subTest(fault=label):
                decision = box.decide(MEDIUM, self.thornwood, parser="model", call=call)
                self.assertEqual((decision.query, decision.kind, decision.form), (rules.query, rules.kind, rules.form))
                parse = decision.record()["parse"]
                self.assertEqual((parse["parser"], parse["used"], parse["prompt_version"]),
                                 ("model", "rules", form.PROMPT_VERSION))
                self.assertIn(words, parse["fallback_reason"])
                self.assertEqual(parse["model_form"] is not None, has_form)
                self.assertEqual(parse["rules_form"], rules.form.record())

    def test_a_form_with_no_text_under_the_arm_is_the_rules_too(self):
        # A review question has no text without its stop rule, and `compose` refuses it
        # there; under the model parser that is the model's form failing, so the rules
        # decide, rather than the batch stopping after the parse was paid for.
        # The question is one the rules read as a survey of the listings, not of reviews, so
        # their form has a text under the arm.
        question = ("Go to http://localhost:7770/catalogsearch/result/?q=Thornwood . "
                    "Does the Thornwood tee shrink in the wash?")
        reviews = stub(reply(quantifier="exists", objective="mention", population="reviews",
                             filters=[f("review text", "contains", "shrink")]))
        decision = box.decide(question, self.thornwood, parser="model", call=reviews, exhaust=True)
        self.assertEqual((decision.parse.used, decision.kind, decision.plan.exhaust), ("rules", "survey", True))
        self.assertIn("no plan can be composed from it: --box-exhaust opens every listing",
                      decision.parse.fallback_reason)
        # The same form with the stop rule is planned as the model read it.
        self.assertEqual(box.decide(question, self.thornwood, parser="model", call=reviews).kind, "depth_search")
        # On a question that never mentions reviews the same form is refused before it gets
        # that far, for words the question does not use (normalisation v2, `conflicts`).
        misread = box.decide(MEDIUM, self.thornwood, parser="model", call=stub(reply(
            quantifier="exists", objective="mention", population="reviews",
            filters=[f("review text", "contains", "leaks")])), exhaust=True)
        self.assertEqual((misread.parse.used, misread.kind), ("rules", "total_bound"))
        self.assertIn("looks for 'leaks' in the reviews, words the question does not use",
                      misread.parse.fallback_reason)

    def test_no_call_is_made_without_a_page_or_a_shopping_question(self):
        poem = "Write a short poem about shoes."
        for page_, why in ((None, "the question names no results page"),
                           (self.page, "the rules found no shopping question")):
            with self.subTest(page=page_ is not None):
                decision = box.decide(poem, page_, parser="model", call=never)
                self.assertEqual((decision.bypass, decision.query), (True, poem))
                self.assertEqual((decision.parse.used, decision.parse.prompt_version), ("rules", None))
                self.assertTrue(decision.parse.fallback_reason.startswith(why))
        with self.assertRaisesRegex(ValueError, "names no results page"):
            box.decide("Which seller is cheapest for size M?", None, parser="model", call=never)

    def test_a_parser_the_box_has_not_and_a_model_with_no_call_are_refused(self):
        with self.assertRaisesRegex(ValueError, "parser 'magic' is not one of"):
            box.decide(MEDIUM, self.thornwood, parser="magic")
        with self.assertRaisesRegex(ValueError, "needs a call"):
            box.decide(MEDIUM, self.thornwood, parser="model")

    def test_the_shops_ambiguity_is_asked_with_the_offer_template(self):
        question = clothing_questions()["apparel-all-stocked"]
        call = stub(reply(quantifier="forall", objective="availability", filters=[f("size", "=", "M")],
                          ambiguities=[{"word": "offer", "readings": ["listed", "buyable"]}]))
        asked = box.decide(question, self.thornwood, parser="model", call=call)
        self.assertEqual((asked.query, asked.ask), (None, box.decide(question, self.thornwood).ask))
        self.assertEqual(asked.record()["parse"]["model_form"]["ambiguities"],
                         [{"word": "offer", "readings": ["listed", "buyable"]}])
        # The scripted reply answers it, and the reading is applied to the model's form in
        # code: the text is the rules', and no second call is made.
        for key, value in (("menu", "listed"), ("buyable", "buyable")):
            with self.subTest(reading=key):
                answered = box.decide(question, self.thornwood, reply=key, parser="model", call=call)
                self.assertEqual((answered.kind, answered.reading, answered.reading_by, answered.form.source,
                                  answered.form.filter("availability").value, answered.form.ambiguities),
                                 ("refutation", key, "user", "model", value, ()))
                self.assertEqual(answered.query, box.decide(question, self.thornwood, reply=key).query)
        self.assertEqual(len(call.prompts), 3)

    def test_an_ambiguity_only_the_model_sees_is_asked_with_its_word(self):
        question = GO + "How many listings stock a medium?"
        self.assertIsNone(ambiguity.ask(question))
        call = stub(reply(quantifier="count", objective="availability", filters=[f("size", "=", "medium")],
                          ambiguities=[{"word": "stock", "readings": ["in the size menu, sold out or not",
                                                                      "can be bought now"]}]))
        asked = box.decide(question, self.page, parser="model", call=call)
        self.assertEqual(asked.ask.text, ambiguity.ASK.format(verb="stock"))
        self.assertEqual(asked.ask.readings["menu"].sentence,
                         "By 'stock' I mean listings whose size menu includes it, whether or not it is sold out.")
        answered = box.decide(question, self.page, reply="buyable", parser="model", call=call)
        self.assertEqual((answered.kind, answered.form.filters, answered.reading_by),
                         ("survey", (Filter("size", "=", "M"), Filter("availability", "=", "buyable")), "user"))
        self.assertTrue(answered.query.startswith(f"{question} By 'stock' I mean listings that can sell it now, "
                                                  "so a sold-out size does not count.\n\n"))
        # Quiet: the same form with no ambiguity is planned without asking.
        plain = box.decide(question, self.page, parser="model",
                           call=stub(reply(quantifier="count", objective="availability",
                                           filters=[f("size", "=", "M")])))
        self.assertEqual((plain.ask, plain.kind), (None, "survey"))

    def test_the_box_takes_the_one_reading_the_shop_can_answer(self):
        # A price exists only for a size that can be bought, so the menu reading of a price
        # question has no answer here, and the box reads it as buyable without asking.
        question = GO + "Which seller carrying a medium is cheapest?"
        call = stub(reply(filters=[f("size", "=", "M")],
                          ambiguities=[{"word": "carrying", "readings": ["listed", "buyable"]}]))
        decision = box.decide(question, self.page, parser="model", call=call)
        self.assertEqual((decision.ask, decision.reading, decision.reading_by, decision.kind),
                         (None, "buyable", "box", "availability_bound"))
        self.assertIn("By 'carrying' I mean listings that can sell it now", decision.query)

    def test_a_question_that_settles_its_own_reading_is_not_asked(self):
        question = GO + "How many listings have size M in stock?"
        flagged = reply(quantifier="count", objective="availability",
                        filters=[f("size", "=", "M"), f("availability", "=", "buyable")],
                        ambiguities=[{"word": "have", "readings": ["listed", "buyable"]}])
        decision = box.decide(question, self.page, parser="model", call=stub(flagged))
        self.assertEqual((decision.ask, decision.kind, decision.form.ambiguities), (None, "survey", ()))
        settled = "ambiguity 'have' is settled by the question's 'in stock': availability = buyable"
        self.assertIn(settled, decision.parse.changes)
        self.assertIn("normalised:ambiguities", decision.form.evidence)
        # The settled reading is applied, not only the flag dropped. The prompt tells a model
        # that flags the ambiguity to leave availability out, and until normalisation v2 a
        # reply that did so lost "in stock": a count of what can be bought became a count of
        # what is listed (verifier finding, 22 October 2026). Planted: `settle` dropping the
        # flag and keeping the form's filters, the reply that omits availability lost it and
        # the box fell back to the rules.
        omitted = reply(quantifier="count", objective="availability", filters=[f("size", "=", "M")],
                        ambiguities=[{"word": "have", "readings": ["listed", "buyable"]}])
        for text in (flagged, omitted):
            with self.subTest(reply=text):
                decision = box.decide(question, self.page, parser="model", call=stub(text))
                self.assertEqual((decision.parse.used, decision.ask, decision.form.filters),
                                 ("model", None, (Filter("size", "=", "M"), Filter("availability", "=", "buyable"))))
                self.assertEqual(decision.form.filters, box.decide(question, self.page).form.filters)
                self.assertEqual(decision.form.evidence["filter:availability"], "in stock")
        # A menu phrase settles it the other way, as the rules read one.
        menu = GO + "How many listings have size M listed, sold out or not?"
        listed = box.decide(menu, self.page, parser="model", call=stub(omitted))
        self.assertEqual((listed.parse.used, listed.ask, listed.form.filters),
                         ("model", None, (Filter("size", "=", "M"), Filter("availability", "=", "listed"))))
        self.assertEqual(listed.form.filters, box.decide(menu, self.page).form.filters)
        # The same flag where the question does not settle it is asked about, and a flag on a
        # word the question never uses settles nothing (`settle` reads only the question's).
        unsettled = GO + "How many listings have a medium?"
        self.assertIsNotNone(box.decide(unsettled, self.page, parser="model", call=stub(flagged)).ask)
        elsewhere = reply(quantifier="count", objective="availability", filters=[f("size", "=", "M")],
                          ambiguities=[{"word": "sell", "readings": ["listed", "buyable"]}])
        self.assertNotIn(settled.replace("'have'", "'sell'"),
                         box.decide(question, self.page, parser="model", call=stub(elsewhere)).parse.changes)

    def test_any_other_ambiguity_is_asked_with_a_template_quoting_the_models_readings(self):
        question = GO + "What is the price of the tee in size M?"
        call = stub(reply(filters=[f("size", "=", "M")], ambiguities=[
            {"word": "the price", "readings": ["the lowest price any listing charges", "the price each listing charges"]}]))
        decision = box.decide(question, self.page, parser="model", call=call)
        self.assertEqual(decision.ask.text, "Your question says 'the price', which could mean the lowest price "
                                            "any listing charges or the price each listing charges. Which do you mean?")
        self.assertEqual((decision.ask.readings, decision.query, decision.plan, decision.kind,
                          decision.record()["asked"]), ({}, None, None, None, True))
        # No scripted reply answers it, so the run ends as asked, as on the threshold ask.
        self.assertIsNone(box.decide(question, self.page, reply="menu", parser="model", call=call).query)
        self.assertEqual(suite.asked_row({"id": "t", "family": "f", "gated": True}, 1, decision.record())["verdict"],
                         "asked")
        self.assertEqual(ambiguity.generic_ask("x", ("a", "b", "c")).text,
                         "Your question says 'x', which could mean a, b or c. Which do you mean?")
        # Quiet: the same form without the ambiguity is planned.
        self.assertEqual(box.decide(question, self.page, parser="model",
                                    call=stub(reply(filters=[f("size", "=", "M")]))).kind, "total_bound")

    def test_a_vague_price_word_gets_the_threshold_ask(self):
        question = GO + "Is there an affordable tee in size M?"
        exists = dict(quantifier="exists", filters=[f("size", "=", "M")])
        for label, text in (("an unknown", reply(unknowns=["affordable"], **exists)),
                            ("an ambiguity", reply(ambiguities=[{"word": "affordable",
                                                                 "readings": ["under $20", "under $30"]}], **exists))):
            with self.subTest(flagged=label):
                decision = box.decide(question, self.page, parser="model", call=stub(text))
                self.assertEqual((decision.ask.text, decision.ask.readings, decision.query),
                                 (ambiguity.THRESHOLD.format(word="affordable"), {}, None))
                self.assertEqual(decision.parse.used, "model")
        # With a figure the model's form names a limit and is planned.
        priced = box.decide(GO + "Is there a tee in size M under $20?", self.page, parser="model",
                            call=stub(reply(quantifier="exists", filters=[f("size", "=", "M"), f("price", "<", 20)])))
        self.assertEqual((priced.ask, priced.kind), (None, "exists_price"))
        # A missing limit claimed beside a figure would make the ask say what is false: the
        # rules decide instead.
        both = box.decide(GO + "Is there an affordable tee in size M under $20?", self.page, parser="model",
                          call=stub(reply(unknowns=["price limit"], evidence={"unknowns": "affordable"}, **exists)))
        self.assertEqual(both.parse.used, "rules")
        self.assertIn("the question gives a figure", both.parse.fallback_reason)

    def test_the_refusal_that_depends_on_the_reading_is_the_rules(self):
        question = GO + "Which seller is cheapest for size M, sold out or not?"
        decision = box.decide(question, self.page, parser="model", call=stub(
            reply(filters=[f("size", "=", "M"), f("availability", "=", "listed")])))
        self.assertTrue(decision.refuse.startswith("The shop does not show the price of a sold-out size"))
        self.assertEqual(decision.parse.used, "rules")
        self.assertIn("the shop does not show the price of a sold-out size", decision.parse.fallback_reason)

    def test_the_rules_path_is_unchanged(self):
        page_ = synthetic_page([31.40, 12.25, 19.50])
        default = {"parser": "rules", "used": "rules", "fallback_reason": None, "declined": False,
                   "prompt_version": None, "normalise_version": None, "rules_form": None, "model_form": None,
                   "model_raw": None, "changes": [], "reply": None}
        for task_id, question in clothing_questions().items():
            for reading in (None, "menu", "buyable"):
                with self.subTest(task=task_id, reading=reading):
                    plain = box.decide(question, page_, reply=reading)
                    named = box.decide(question, page_, reply=reading, parser="rules", call=never)
                    self.assertEqual(plain.record(), named.record())
                    self.assertEqual(plain.record()["parse"], default)
        frozen = json.loads((FIXTURES / "v1_clothing_queries.json").read_text())
        questions = clothing_questions()
        for row in frozen["queries"]:
            with self.subTest(task=row["task"], reading=row["reading"]):
                self.assertEqual(box.decide(questions[row["task"]], page_, reply=row["reading"], parser="rules").query,
                                 row["query"])


# ---------------------------------------------------------------------------
# 6. The negated universal

NEGATED = GO + "Is there a listing that does not have size M?"


class Negation(unittest.TestCase):
    def setUp(self):
        self.page = synthetic_page([10.15, 11.15, 12.15])
        self.urls = [item.url for item in self.page.listings]
        self.call = stub(reply(quantifier="forall", objective="availability", filters=[f("size", "=", "M")],
                               negated=True, ambiguities=[{"word": "have", "readings": ["listed", "buyable"]}]))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def decision(self, reading: str = "menu", exhaust: bool = False) -> box.Decision:
        return box.decide(NEGATED, self.page, reply=reading, parser="model", call=self.call, exhaust=exhaust)

    def test_it_is_asked_about_then_planned_as_a_search_with_yes_and_no_turned_over(self):
        asked = box.decide(NEGATED, self.page, parser="model", call=self.call)
        self.assertEqual((asked.ask.verb, asked.query), ("have", None))
        decision = self.decision()
        self.assertEqual((decision.kind, decision.plan.primitive, decision.plan.stop_rule),
                         ("negated_refutation", "counterexample", planner.STOP_RULES["negated_refutation"]))
        # The search's own text, and since box v19 the label sentence on its own line.
        self.assertEqual(decision.plan.instruction, f"{primitives.NEGATED_REFUTATION}\n{primitives.LABEL_NOTE}")
        self.assertEqual(decision.query, f"{decision.question}\n\n{box.preamble(self.page)}\n\n"
                                         f"{primitives.NEGATED_REFUTATION}\n{primitives.LABEL_NOTE}")
        for needle in ("To answer Yes you need exactly ONE listing that lacks the option.",
                       "Answer Yes, name that listing as your evidence, and stop immediately.",
                       "To answer No you must have opened every single one.",
                       "without finding one may you answer No."):
            self.assertIn(needle, decision.plan.instruction)
        for wrong in ("Answer No, name that listing", "To answer No you need exactly ONE",
                      "previous version of this instruction"):
            self.assertNotIn(wrong, decision.plan.instruction)
        self.assertEqual([c.seller for c in decision.plan.candidates], ["Seller A", "Seller B", "Seller C"])
        self.assertEqual(form.verify(decision.form, self.page), [])
        # The universal it negates keeps v1's text, word for word, and the label sentence.
        universal = box.decide(GO + "Does every listing have size M?", self.page, reply="menu")
        self.assertEqual(universal.plan.instruction, f"{targeting.BODIES['refutation']}\n{primitives.LABEL_NOTE}")

    def verdict(self, answer: str, log: pathlib.Path, reading: str = "menu") -> dict:
        return box.check(self.decision(reading), answer, log)

    def test_a_yes_needs_the_listing_that_lacks_the_size(self):
        lacks = menu_log(self.tmp.name, "lacks", [(self.urls[1], {"S": True, "L": True})])
        has = menu_log(self.tmp.name, "has", [(self.urls[0], {"S": True, "M": True})])
        named = self.verdict("Yes. Seller B has no size M.", lacks)
        self.assertEqual((named["ok"], named["primitive"]), (True, "counterexample"))
        self.assertTrue(self.verdict("Yes", lacks)["ok"])
        self.assertEqual(self.verdict("Yes. Seller C lacks it.", has)["flag"], "counterexample_not_opened")
        self.assertEqual(self.verdict("Yes", has)["flag"], "counterexample_not_opened")
        # Under the buying reading a disabled M is a listing that lacks it; under the menu, not.
        disabled = menu_log(self.tmp.name, "disabled", [(self.urls[0], {"S": True, "M": False})])
        self.assertTrue(self.verdict("Yes", disabled, reading="buyable")["ok"])
        self.assertEqual(self.verdict("Yes", disabled, reading="menu")["flag"], "counterexample_not_opened")

    def test_a_no_needs_every_listing(self):
        one = openjiuwen_log(self.tmp.name, "one", self.urls[:1])
        every = openjiuwen_log(self.tmp.name, "every", self.urls)
        for answer in ("No, every listing has size M.", "None of them lacks it.", "Seller A has size M."):
            with self.subTest(answer=answer):
                self.assertEqual(self.verdict(answer, one)["flag"], "unverified_universal")
                self.assertTrue(self.verdict(answer, every)["ok"])
        self.assertEqual(self.verdict("Availability varies.", every)["flag"], "answer_unclear")

    def test_the_fault_planted(self):
        # The check without its turn is the universal's, which takes the correct yes for a
        # claim about every listing and refuses it (LESSONS 31).
        decision = self.decision()
        lacks = menu_log(self.tmp.name, "planted", [(self.urls[1], {"S": True, "L": True})])
        text, menus = sufficiency.observed_text(lacks), sufficiency.size_menus(lacks)
        answer = "Yes. Seller B has no size M."
        self.assertTrue(primitives.check(decision.form, self.page, answer, text, menus=menus)["ok"])
        unturned = dataclasses.replace(decision.form, negated=False)
        self.assertEqual(primitives.check(unturned, self.page, answer, text, menus=menus)["flag"],
                         "unverified_universal")

    def test_without_its_stop_rule(self):
        decision = self.decision(exhaust=True)
        self.assertEqual((decision.plan.exhaust, decision.plan.stop_rule), (True, primitives.EXHAUST_STOP))
        self.assertIn("1. Open every listing on the page before answering", decision.plan.instruction)
        self.assertIn("answer Yes and name that listing as your evidence", decision.plan.instruction)
        for stop in ("stop immediately", "Stopping after", "cannot change the answer", "Do not open any others",
                     "rather than surveying", "Nothing more"):
            self.assertNotIn(stop.lower(), decision.plan.instruction.lower())

    def test_the_rules_do_not_read_the_negation_and_an_unplannable_one_falls_back(self):
        parsed = form.from_rules(NEGATED, self.page)
        self.assertEqual((parsed.negated, parsed.kind(), parsed.fallback), (False, "survey", True))
        call = stub(reply(quantifier="forall", objective="price", filters=[f("price", "<", 20)], negated=True))
        decision = box.decide(GO + "Is there a listing that does not sell anything under $20?", self.page,
                              parser="model", call=call)
        self.assertEqual(decision.parse.used, "rules")
        self.assertIn("a negated universal is planned only over the availability of a size it names",
                      decision.parse.fallback_reason)


# ---------------------------------------------------------------------------
# 7. The suite under `--parser model`

TASKS = ("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1")
CHEAPEST_REPLY = reply(filters=[f("size", "=", "M"), f("availability", "=", "buyable")],
                       evidence={"quantifier": "cheapest"})
OFFER_REPLY = reply(quantifier="forall", objective="availability", filters=[f("size", "=", "M")],
                    ambiguities=[{"word": "offer", "readings": ["listed", "buyable"]}])


# The tokens a faked call says it used (23 October 2026), a count of no real call.
PARSE_TOKENS = {"prompt": 5200, "completion": 140}


def replying(cost: float | None = 0.004, tokens: dict | None = PARSE_TOKENS, served: str | None = None):
    """A faked `parse_probe.call_model`: the cheapest question gets CHEAPEST_REPLY, every
    other OFFER_REPLY, each charged `cost`, counted `tokens` and served by `served`."""
    def call_model(key, model, prompt):
        question = prompt.rsplit("The question:\n", 1)[1]
        return (CHEAPEST_REPLY if "cheapest" in question else OFFER_REPLY), cost, tokens, served
    return call_model


def keyed_tasks(folder: pathlib.Path) -> pathlib.Path:
    """tasks_apparel.json copied with a sidecar holding a buyable key for every task, which a
    model-parser batch needs (score v4, `suite.unscorable`): the clothing file's own sidecar
    holds one for its two questions with two readings only. The added keys are each task's
    own, a stand-in that lets the batch start; these tests check charges and records, never
    a verdict."""
    tasks = folder / "tasks_keyed.json"
    tasks.write_text((paths.TASKS / "tasks_apparel.json").read_text())
    own = json.loads((paths.TASKS / "readings_apparel.json").read_text())["readings"]["buyable"]
    spec = json.loads(tasks.read_text())
    keys = {task["id"]: own.get(task["id"], task["expect"]) for task in spec["tasks"]}
    (folder / "readings_keyed.json").write_text(json.dumps({"readings": {"buyable": keys}}))
    return tasks


class SuiteParser(unittest.TestCase):
    def setUp(self):
        folder = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.keyed = ("--tasks", str(keyed_tasks(folder)), "--repeats", "1")

    def run_model(self, *argv, call_model=None) -> tuple:
        with mock.patch.object(parse_probe, "call_model", call_model or replying()), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"):
            run = run_suite(*argv, page=thornwood_page())
        self.addCleanup(run.owner.cleanup)
        payload = json.loads((run.batch / "suite.json").read_text()) if run.batch else None
        return run, payload

    def test_the_flags_it_needs(self):
        only = self.keyed + ("--only", "apparel-headline")
        for argv, words in (((*only, "--parser", "model", "--dry-run"), "--parser model reads the question for the box"),
                            ((*only, "--box", "--parser-model", "x/y", "--dry-run"),
                             "--parser-model names the model of --parser model"),
                            ((*only, "--box", "--parser", "model", "--parser-replies", "r.json"),
                             "--parser-replies stands in for the model's replies in a dry run")):
            with self.subTest(argv=argv[-3:]):
                run, _ = self.run_model(*argv)
                self.assertEqual(run.code, 2)
                self.assertIn(words, run.out)
        run, _ = self.run_model(*only, "--box", "--parser", "model", "--dry-run")
        self.assertEqual(run.code, 0)
        self.assertIn("arm: box-model\n", run.out)
        self.assertIn(f"parser: model {suite.agent_model()}, temperature 0, prompt v{form.PROMPT_VERSION}, normalisation "
                      f"v{normalise.VERSION}\n", run.out)
        # Under the rules the header is what it always was.
        run, _ = self.run_model(*only, "--box", "--dry-run")
        self.assertIn("arm: box\n", run.out)
        self.assertNotIn("parser:", run.out)

    def test_the_dry_run_shows_both_parsers_from_a_stubbed_reply_and_sends_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = pathlib.Path(tmp) / "tasks_medium.json"
            tasks.write_text(json.dumps({"base_url": BASE, "tasks": [{
                "id": "medium", "family": "apparel", "gated": True, "expect": {"kind": "none"},
                "query": MEDIUM.replace(BASE, "{base}")}]}))
            replies = pathlib.Path(tmp) / "replies.json"
            replies.write_text(json.dumps({"replies": {"medium": reply(
                filters=[f("size", "=", "medium"), f("title", "contains", "Thornwood")], population="listing")}}))
            sent = mock.Mock(side_effect=AssertionError("a dry run called the model"))
            run, _ = self.run_model("--tasks", str(tasks), "--repeats", "1", "--box", "--parser", "model",
                                    "--parser-replies", str(replies), "--dry-run", call_model=sent)
        self.assertEqual(run.code, 0, run.out)
        sent.assert_not_called()
        self.assertIn("parser rules: argmin price over results, filters: none\n", run.out)
        self.assertIn(f"parser model (prompt v{form.PROMPT_VERSION}, normalisation v{normalise.VERSION}), reply from replies.json: "
                      "argmin price over results, filters: size = M\n", run.out)
        self.assertIn("  normalised: size = 'medium' is size = 'M'\n", run.out)
        self.assertEqual(run.out.count(f"{MEDIUM}\n\nThe results page lists 15 listings"), 2)
        self.assertIn("the counts take the model parser's decision on the 1 tasks a reply was given for", run.out)
        # Without a replies file the model's half says there is nothing to show.
        run, _ = self.run_model(*self.keyed, "--only", "apparel-headline", "--box", "--parser", "model", "--dry-run",
                                call_model=sent)
        self.assertIn("no reply, since a dry run sends nothing", run.out)
        sent.assert_not_called()

    def test_a_paid_run_charges_each_run_its_parse_and_records_both_parsers(self):
        run, payload = self.run_model(*self.keyed, "--only", "apparel-cheapest-target", "apparel-all-stocked",
                                      "--box", "--parser", "model")
        self.assertEqual((run.code, run.calls), (0, 1))
        rows = {row["task"]: row for row in payload["rows"]}
        ran = rows["apparel-cheapest-target"]
        self.assertEqual((ran["cost_usd"], ran["parse_cost_usd"], ran["box"]["parse"]["used"]), (0.004, 0.004, "model"))
        self.assertEqual(ran["box"]["parse"]["model_form"]["filters"],
                         [f("size", "=", "M"), f("availability", "=", "buyable")])
        self.assertIsNotNone(ran["box"]["parse"]["rules_form"])
        record = json.loads((run.batch / "apparel-cheapest-target-1.json").read_text())
        self.assertEqual((record["agent_cost_usd"], record["parse_cost_usd"], record["cost_usd"]), (0.0, 0.004, 0.004))
        # The offer question is asked about: no agent ran, and the parse was spent.
        asked = rows["apparel-all-stocked"]
        self.assertEqual((asked["verdict"], asked["cost_usd"], asked["parse_cost_usd"]), ("asked", 0.004, 0.004))
        self.assertEqual((payload["arm"], payload["parser"], payload["parser_model"], payload["parser_temperature"],
                          payload["prompt_version"], payload["normalise_version"], payload["parse_charged_usd"],
                          payload["parse_charges_unknown"]),
                         ("box-model", "model", suite.agent_model(), 0, form.PROMPT_VERSION,
                          normalise.VERSION, 0.008, 0))
        self.assertEqual(payload["summary"]["total_cost"], 0.008)
        self.assertIn("[parsed by the model, $0.004]", run.out)
        # The same batch under the rules: no parse, no charge, and the parser named.
        run, payload = self.run_model(*self.keyed, "--only", "apparel-cheapest-target", "apparel-all-stocked", "--box")
        rows = {row["task"]: row for row in payload["rows"]}
        self.assertEqual((payload["arm"], payload["parser"], payload["parser_model"], payload["prompt_version"]),
                         ("box", "rules", None, None))
        self.assertEqual((rows["apparel-cheapest-target"]["cost_usd"], rows["apparel-all-stocked"]["cost_usd"]), (0.0, 0))
        self.assertNotIn("parse_cost_usd", rows["apparel-cheapest-target"])

    def test_a_parse_that_fails_or_is_not_priced(self):
        def timing_out(key, model, prompt):
            raise requests.exceptions.Timeout("read timed out")

        def not_a_completion(key, model, prompt):
            raise parse_probe.UnexpectedReply("the reply holds no choices", 0.002)

        only = (*self.keyed, "--only", "apparel-cheapest-target", "--box", "--parser", "model")
        # A request that fails may still have been charged, and nothing says how much, so its
        # cost is unknown, never $0 (verifier finding, 22 October 2026). Planted: `parser_call`
        # recording 0.0 for it, the first case failed. A reply that is no completion states
        # its charge, which is kept.
        for label, call_model, cost, words in (
                ("a request that fails", timing_out, None, "the model call failed: Timeout: read timed out"),
                ("a reply that is no completion", not_a_completion, 0.002,
                 "the model call failed: UnexpectedReply: the reply holds no choices")):
            with self.subTest(fault=label):
                run, payload = self.run_model(*only, call_model=call_model)
                row = payload["rows"][0]
                self.assertEqual((row["cost_usd"], row["parse_cost_usd"], payload["parse_charges_unknown"]),
                                 (cost, cost, int(cost is None)))
                self.assertEqual(row["box"]["parse"]["used"], "rules")
                self.assertIn(words, row["box"]["parse"]["fallback_reason"])
                self.assertEqual(payload["summary"]["cost_unknown_runs"], int(cost is None))
                self.assertEqual("runs whose cost is unknown are not in it" in run.out, cost is None)
        # A charge the provider did not state makes the run's cost unknown, not the agent's alone.
        _, payload = self.run_model(*only, call_model=replying(cost=None))
        row = payload["rows"][0]
        self.assertEqual((row["cost_usd"], row["parse_cost_usd"], payload["parse_charges_unknown"]), (None, None, 1))

    def test_charging_a_parse(self):
        self.assertEqual((suite.parse_cost([]), suite.parse_cost([0.001, 0.002]), suite.parse_cost([0.001, None])),
                         (0, 0.003, None))
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "run.json"
            path.write_text("{}")
            got = suite.charge_parse({"cost_usd": 0.05, "model": "m"}, 0.004, path)
            self.assertEqual((got["cost_usd"], got["agent_cost_usd"], got["parse_cost_usd"], got["model"]),
                             (0.054, 0.05, 0.004, "m"))
            self.assertEqual(json.loads(path.read_text()), got)
            self.assertIsNone(suite.charge_parse({"cost_usd": None}, 0.004, path)["cost_usd"])
            self.assertIsNone(suite.charge_parse({"cost_usd": 0.05}, None, path)["cost_usd"])
            missing = pathlib.Path(tmp) / "none.json"
            suite.charge_parse({"cost_usd": 0.05}, 0.004, missing)
            self.assertFalse(missing.exists())

    def test_a_model_batch_needs_the_buyable_key_of_every_question_the_model_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = pathlib.Path(tmp) / "tasks_nokeys.json"
            copy.write_text((paths.TASKS / "tasks_apparel.json").read_text())
            run, _ = self.run_model("--tasks", str(copy), "--repeats", "1", "--box", "--parser", "model", "--dry-run")
            self.assertEqual(run.code, 2)
            self.assertIn("apparel-all-stocked under the buyable reading, which the model parser can lead any "
                          "question it reads to", run.out)
            # The same copy under the rules, which ask and run nothing without a reading.
            run, _ = self.run_model("--tasks", str(copy), "--repeats", "1", "--box", "--dry-run")
            self.assertEqual(run.code, 0, run.out)
        # The clothing file's sidecar holds the buyable keys of its two questions with two
        # readings, and the model can lead any question it reads to that reading, whatever
        # the word list makes of it (verifier finding, 22 October 2026). So a model batch on
        # it is refused for the other four, by name, and one with a key for every question
        # starts. Planted: the check reading the word list's two-reading questions only, the
        # refusal did not come.
        run, _ = self.run_model(*TASKS, "--box", "--parser", "model", "--dry-run")
        self.assertEqual(run.code, 2)
        for task in ("apparel-headline", "apparel-target-price", "apparel-cheapest-target", "apparel-count-buyable"):
            self.assertIn(f"{task} under the buyable reading", run.out)
        for task in ("apparel-all-stocked", "apparel-count-stocked"):
            self.assertNotIn(f"{task} under the buyable reading", run.out)
        run, _ = self.run_model(*self.keyed, "--box", "--parser", "model", "--dry-run")
        self.assertEqual(run.code, 0, run.out)

    def test_the_arm_names_the_parser_and_no_reader_pools_the_two(self):
        def namespace(**over):
            return argparse.Namespace(**{"box": False, "box_exhaust": False, "targeting": False,
                                         "exhaustive": False, **over})

        self.assertEqual([suite.arm_of(namespace(box=True, parser="model")),
                          suite.arm_of(namespace(box_exhaust=True, parser="model")),
                          suite.arm_of(namespace(box=True, parser="rules")), suite.arm_of(namespace(box=True))],
                         ["box-model", "box-exhaust-model", "box", "box"])
        self.assertEqual((claim.flagged_arm({"box": True, "parser": "model"}), claim.flagged_arm({"box": True})),
                         ("box-model", "box"))
        self.assertTrue(claim.arm_of({"arm": "box-model", "box": True, "parser": "model",
                                      "reading": "menu"}).startswith("other: arm box-model"))
        self.assertEqual(claim.arm_of({"arm": "box", "box": True, "reading": "menu"}), claim.BLOCK)


# ---------------------------------------------------------------------------
# 8. The verifier's re-sum of a run's cost

class VerifyCellsCost(unittest.TestCase):
    def test_the_log_resums_to_the_agents_part_of_the_cost(self):
        spec = json.loads((paths.TASKS / "tasks_apparel_v2.json").read_text())
        task = next(t for t in spec["tasks"] if t["id"] == "apparel-cheapest-target")
        truth = verify_cells.ground_truth()
        with tempfile.TemporaryDirectory() as tmp:
            record = pathlib.Path(tmp) / "apparel-cheapest-target-1.json"
            record.with_suffix(".log").write_text("2026-10-22 12:00:00 | usage cost=0.01, is_byok=False\n")

            def verified(**costs) -> dict:
                record.write_text(json.dumps({"result": {"ok": True, "final": "Seller A at $10.00."},
                                              "scaffold": "openjiuwen", "shop": "gated", **costs}))
                return verify_cells.verify_run(record, task, truth, {})

            # A model-parser run: the record's cost holds the parse, and its agent part is the log's.
            charged = verified(cost_usd=0.014, agent_cost_usd=0.01, parse_cost_usd=0.004)
            self.assertEqual((charged["cost"], charged["agent_cost"], charged["parse_cost"], charged["cost_resummed"]),
                             (0.014, 0.01, 0.004, 0.01))
            self.assertFalse(verify_cells.cost_differs(charged))
            self.assertTrue(verify_cells.cost_differs(verified(cost_usd=0.014, agent_cost_usd=0.012,
                                                               parse_cost_usd=0.002)))
            # A record from before: its cost is the agent's, held to the log as it always was.
            self.assertFalse(verify_cells.cost_differs(verified(cost_usd=0.01)))
            self.assertTrue(verify_cells.cost_differs(verified(cost_usd=0.014)))


if __name__ == "__main__":
    unittest.main()
