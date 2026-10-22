"""The model may decline a question, only when the rules confirm it (box v15, normalisation
v3, 22 October 2026, for the second claim run, docs/content/claim2-protocol.md).

Under the model parser a form whose one failure is an attribute the shop does not show, by
the rules' own check of the page's attributes, declines the question with the usual
statement of what the shop shows, and the record says the model's form declined. Any other
failure still falls back to the rules. Every rule here has a case where it fires and one
where it stays quiet, and each fault named was planted in the code, with a fresh bytecode
cache (LESSONS 39), and seen to fail its test before the code was put back (LESSONS 31).

Every model reply is a stub, every agent run is the fake runner of `test_claim_arms`, and
nothing is sent anywhere.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401
import box  # noqa: E402
import form  # noqa: E402
import normalise  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
from form import Filter, Form  # noqa: E402
from test_box import BASE, thornwood_page  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402
from test_model_parser import f, reply, stub  # noqa: E402

THORNWOOD = "Go to http://localhost:7770/catalogsearch/result/?q=Thornwood . "
# The protocol's decline question, and a rewording of it the rules plan as a survey of what
# can be bought, since nothing in it is a word their lexicon of what the shop does not show
# knows.
FASTEST = THORNWOOD + "Which Thornwood seller delivers fastest for size M of the tee?"
FIRST = THORNWOOD + "Which seller would get a size M Thornwood tee to me first?"
SIZE_M = f("size", "=", "M")
REFUSAL = form.refusal(["delivery time"])


def delivery(**over) -> str:
    """A model's reply that reads the question as the soonest delivery of size M."""
    return reply(**{"objective": "attribute:delivery time", "filters": [SIZE_M],
                    "unknowns": ["delivery time"], "evidence": {"objective": "get ... to me first"},
                    **over})


class TheModelDeclines(unittest.TestCase):
    def setUp(self):
        self.page = thornwood_page()

    def test_a_model_form_needing_what_the_shop_does_not_show_declines(self):
        # Planted: `normalise.declines` returning nothing, the box fell back to the rules
        # and the record said nothing of the model's form.
        decision = box.decide(FASTEST, self.page, parser="model", call=stub(delivery()))
        self.assertEqual((decision.refuse, decision.kind, decision.query, decision.ask),
                         (REFUSAL, None, None, None))
        self.assertEqual((decision.parse.used, decision.parse.declined, decision.parse.fallback_reason),
                         ("model", True, None))
        record = decision.record()
        self.assertEqual((record["refuse"], record["parse"]["declined"], record["parse"]["used"]),
                         (REFUSAL, True, "model"))
        self.assertEqual(record["form"]["objective"], "attribute:delivery time")
        self.assertIsNotNone(record["parse"]["rules_form"])
        # The rules refuse it too, in the same words.
        self.assertEqual(box.decide(FASTEST, self.page).refuse, REFUSAL)

    def test_a_rewording_the_rules_plan_is_declined_on_the_models_form(self):
        rules = box.decide(FIRST, self.page)
        self.assertEqual((rules.kind, rules.refuse), ("survey", None))
        model = box.decide(FIRST, self.page, parser="model", call=stub(delivery()))
        self.assertEqual((model.refuse, model.parse.declined, model.query), (REFUSAL, True, None))

    def test_no_decline_when_the_attribute_is_one_the_shop_shows(self):
        # The seller is shown: the form fails for having no plan, and falls back. And a
        # price is shown: that form is planned.
        seller = box.decide(FIRST, self.page, parser="model", call=stub(delivery(objective="attribute:seller")))
        self.assertEqual((seller.parse.used, seller.parse.declined, seller.refuse, seller.kind),
                         ("rules", False, None, "survey"))
        self.assertIn("no plan exists for kind 'argmin_seller'", seller.parse.fallback_reason)
        price = box.decide(FIRST, self.page, parser="model", call=stub(delivery(objective="price", unknowns=[])))
        self.assertEqual((price.parse.used, price.parse.declined, price.refuse), ("model", False, None))
        self.assertIsNotNone(price.query)
        self.assertEqual(normalise.declines(form.from_record(json.loads(delivery(objective="price").split(
            "\n", 1)[1]), "model"), [], self.page), [])

    def test_any_other_failure_falls_back(self):
        # Planted: `declines` ignoring the other failures, each of these declined.
        for label, question, text, words in (
                ("the size the question names left out", FIRST, delivery(filters=[]),
                 "the question's 'size M' gives size = 'M', and the form has no size filter"),
                ("a size the question never names", FIRST, delivery(filters=[f("size", "=", "L")]),
                 "the form asks about size L, which the question does not name"),
                ("an availability the question's words give left out",
                 THORNWOOD + "Who can ship me a size M Thornwood tee the quickest?", delivery(),
                 "the question's 'ship' gives availability = 'buyable', and the form has no availability filter"),
                ("an ambiguous word that is not the question's", FIRST,
                 delivery(ambiguities=[{"word": "offer", "readings": ["listed", "buyable"]}]),
                 "the ambiguous word 'offer' is not the question's")):
            with self.subTest(fault=label):
                decision = box.decide(question, self.page, parser="model", call=stub(text))
                self.assertEqual((decision.parse.used, decision.parse.declined), ("rules", False))
                self.assertIn(words, decision.parse.fallback_reason)
                self.assertIn("the shop does not show delivery time", decision.parse.fallback_reason)

    def test_a_question_whose_words_ask_about_a_price_is_never_declined(self):
        # A model could decline any question about a price by naming an attribute the shop
        # does not show, so the form must ask about a price where the question's words do
        # (normalisation v3). Planted: that check removed, "cheapest" was declined.
        cheapest = THORNWOOD + "Which seller is cheapest for size M among the Thornwood listings?"
        decision = box.decide(cheapest, self.page, parser="model", call=stub(delivery()))
        self.assertEqual((decision.parse.used, decision.parse.declined, decision.refuse), ("rules", False, None))
        self.assertIn("the question's 'cheapest' asks about a price, where the form asks about "
                      "'attribute:delivery time'", decision.parse.fallback_reason)
        self.assertEqual(decision.kind, box.decide(cheapest, self.page).kind)
        under = THORNWOOD + "Is there any Thornwood listing with size M available to buy for under $24?"
        found = normalise.conflicts(Form("exists", "attribute:delivery time", filters=(
            Filter("size", "=", "M"), Filter("price", "<", 24), Filter("availability", "=", "buyable"))),
            under, self.page)
        self.assertIn("the question's 'under $24' asks about a price, where the form asks about "
                      "'attribute:delivery time'", found)
        # Quiet: the rules' price by default, which no word of the question chose, holds
        # nothing; nor does a question the rules read as about anything but a price.
        default = form.from_rules(THORNWOOD + "Does the Thornwood tee shrink in the wash?", self.page)
        self.assertEqual((default.objective, default.evidence["objective"]),
                         ("price", "nothing but a price is asked about"))
        shrink = Form("exists", "mention", filters=(Filter("review text", "contains", "shrink"),),
                      population="reviews")
        self.assertEqual(normalise.conflicts(shrink, THORNWOOD + "Does the Thornwood tee shrink in the wash?",
                                             self.page), [])
        self.assertEqual(normalise.conflicts(form.from_record(json.loads(delivery().split("\n", 1)[1]), "model"),
                                             FIRST, self.page), [])

    def test_the_price_of_a_sold_out_size_is_a_reading_and_never_declines(self):
        # The menu reading of a price question asks for a figure the page never prints, a
        # refusal of the rules' own after the reading; it is no attribute the shop lacks.
        # Planted: `declines` reading `form.not_shown`, which holds it, this one declined.
        offer = THORNWOOD + "Which seller is cheapest for size M among the Thornwood listings that offer it?"
        decision = box.decide(offer, self.page, parser="model", call=stub(reply(
            filters=[SIZE_M, f("availability", "=", "listed")])))
        self.assertFalse(decision.parse.declined)
        self.assertIn("the shop does not show the price of a sold-out size", decision.parse.fallback_reason)
        rules = box.decide(offer, self.page)
        self.assertEqual((decision.ask, decision.kind, decision.query), (rules.ask, rules.kind, rules.query))

    def test_the_rules_path_never_declines_on_a_models_form(self):
        decision = box.decide(FIRST, self.page)
        self.assertEqual((decision.parse, decision.record()["parse"]["declined"]), (None, False))


class TheSuiteAndTheProbe(unittest.TestCase):
    def test_a_declined_slot_is_refused_with_its_parse_charged_and_said_so(self):
        folder = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        tasks = folder / "tasks_decline.json"
        tasks.write_text(json.dumps({"base_url": BASE, "tasks": [{
            "id": "decline-first", "family": "apparel", "gated": True, "expect": {"kind": "none"},
            "query": FIRST.replace(BASE, "{base}")}]}))
        with mock.patch.object(parse_probe, "call_model", lambda key, model, prompt: (delivery(), 0.002)), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"):
            run = run_suite("--tasks", str(tasks), "--repeats", "1", "--box", "--parser", "model",
                            page=thornwood_page())
        self.addCleanup(run.owner.cleanup)
        self.assertEqual((run.code, run.calls), (0, 0), run.out)
        row = json.loads((run.batch / "suite.json").read_text())["rows"][0]
        self.assertEqual((row["verdict"], row["cost_usd"], row["parse_cost_usd"], row["answer"]),
                         ("refused", 0.002, 0.002, REFUSAL[:300]))
        self.assertEqual((row["box"]["parse"]["used"], row["box"]["parse"]["declined"]), ("model", True))
        self.assertIn("refused    the box refused on the model's form", run.out)
        # The dry run shows it from a stubbed reply.
        replies = folder / "replies.json"
        replies.write_text(json.dumps({"replies": {"decline-first": delivery()}}))
        with mock.patch.object(plan_probe, "load_key", return_value="fake-key"):
            run = run_suite("--tasks", str(tasks), "--repeats", "1", "--box", "--parser", "model",
                            "--parser-replies", str(replies), "--dry-run", page=thornwood_page())
        self.addCleanup(run.owner.cleanup)
        self.assertIn("  declined on the model's form: what it needs is not shown, by the rules' check of "
                      "the page's attributes\nREFUSES: The shop does not show delivery time", run.out)
        self.assertIn("parser rules: aggregate availability over results", run.out)

    def test_the_probe_says_whose_refusal_it_was(self):
        page_ = thornwood_page()
        declined = parse_probe.outcome(FIRST, page_, reply=delivery())
        self.assertEqual((declined["outcome"], declined["parsed_by"], declined["declined"]),
                         ("refuse", "model", True))
        self.assertEqual(parse_probe.outcome_words(declined), "refuse, declined on the model's form")
        by_rules = parse_probe.outcome(FASTEST, page_, reply=delivery(filters=[]))
        self.assertEqual((by_rules["outcome"], by_rules["parsed_by"], by_rules["declined"]),
                         ("refuse", "rules", False))
        self.assertEqual(parse_probe.outcome_words(by_rules), "refuse")
        self.assertNotIn("declined", parse_probe.outcome(FIRST, page_))


if __name__ == "__main__":
    unittest.main()
