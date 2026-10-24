"""Box v19 for the second claim run's design B (24 October 2026, docs/content/claim2-handover.md,
section 5): decision 11, the word list against the model; why each ask was put; at most one ask
a question; and the size labels that carry the seller's own text, read as their size, their
figure never a price and their claim never stock, with the one plan sentence about them.

Every model reply here is a stub, and nothing is sent. Every rule has a case where it fires and
one where it stays quiet, and each fault named in a comment was planted in the code with a fresh
bytecode cache (LESSONS 39) and seen to fail its test before the code was put back (LESSONS 31).
"""
import argparse
import dataclasses
import json
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import form  # noqa: E402
import normalise  # noqa: E402
import page  # noqa: E402
import policy  # noqa: E402
import primitives  # noqa: E402
import replay_box  # noqa: E402
import suite  # noqa: E402
import sufficiency  # noqa: E402
from test_box import menu_log, thornwood_page  # noqa: E402
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


# ---------------------------------------------------------------------------
# 4. Size labels: read as their size, their figure never a price, their claim never stock

# A design B size menu as the agent's snapshot prints it (handover section 3): a promotion's
# figure on XS, a claim of stock on a buyable M, and the plain sizes around them.
LABELLED = {"XS - Promo $9.99": True, "S": True, "M - Only 2 left!": True, "L": False, "XL": True,
            "XXL": False}
TEE_URL = "http://localhost:7770/example-tee-01.html"


class SizeLabels(unittest.TestCase):
    def test_a_label_reads_as_the_whole_size_it_opens_with(self):
        # Planted, each in `sufficiency.SIZE_LABEL`, unanchored and without its boundary: with
        # XS left out of the sizes, "XS - Promo" read as S; with XXL left out, "XXL" as XL;
        # with XL left out, "XL" as L.
        for label, size in (("XS - Promo $9.99", "XS"), ("M - Only 2 left!", "M"), ("XS", "XS"), ("S", "S"),
                            ("XL", "XL"), ("XXL", "XXL"), ("L", "L"), ("XXL - Promo $5.00", "XXL"),
                            ("XL – Promo $5.00", "XL"), ("S (Promo $5.00)", "S")):
            with self.subTest(label=label):
                self.assertEqual(sufficiency.label_size(label), size)
        # Quiet: what opens with no size is kept whole, a pack with its surcharge included.
        for label in ("2 x 9.5L +$15.01", "Medium", "Choose an Option...", "SALE", "XLarge", "Small - Promo"):
            with self.subTest(whole=label):
                self.assertEqual(sufficiency.label_size(label), label)

    def test_the_menu_reader_reads_each_label_as_its_size(self):
        # Planted: `menu_blocks` keyed by the label again, the menu came back with the labels.
        with tempfile.TemporaryDirectory() as folder:
            log = menu_log(folder, "labelled", [(TEE_URL, LABELLED)])
            menus = sufficiency.size_menus(log)
        self.assertEqual(menus, {"slug:example-tee-01": sufficiency.MenuReading(
            {"XS": True, "S": True, "M": True, "L": False, "XL": True, "XXL": False}, True)})

    def test_a_whole_size_is_matched_and_never_one_inside_it(self):
        # The coordinator's finding of 24 October 2026: S is inside XS, L inside XL and XXL,
        # and XL inside XXL. Planted, each in turn: `primitives.menu_has` matching a size
        # anywhere in a label, and `normalise.sizes_named` without its boundaries.
        menu = {"XS": True, "XL": True, "XXL": False}
        self.assertEqual([primitives.menu_has(menu, size) for size in ("S", "L", "XL", "XXL", "XS")],
                         [None, None, "XL", "XXL", "XS"])
        for question, named in ((GO + "Who sells size XS cheapest?", {"XS"}),
                                (GO + "Who sells size XXL cheapest?", {"XXL"}),
                                (GO + "Who sells size XL cheapest?", {"XL"})):
            with self.subTest(question=question[-30:]):
                self.assertEqual(normalise.sizes_named(question) & {"S", "L", "XL", "XXL", "XS"} - named, set())

    def test_a_scarcity_label_is_never_checked_stock(self):
        # Whether a size can be bought is its disabled mark alone: a claim of two left on an M
        # that is disabled is a sold-out M, and on one that is not, an M that can be bought,
        # whatever the claim. Nothing the reader returns holds a count.
        with tempfile.TemporaryDirectory() as folder:
            enabled = sufficiency.size_menus(menu_log(folder, "on", [(TEE_URL, {"M - Only 2 left!": True})]))
            disabled = sufficiency.size_menus(menu_log(folder, "off", [(TEE_URL, {"M - Only 2 left!": False})]))
        self.assertEqual((enabled["slug:example-tee-01"].options, disabled["slug:example-tee-01"].options),
                         ({"M": True}, {"M": False}))
        self.assertEqual([field.name for field in dataclasses.fields(sufficiency.MenuReading)], ["options", "complete"])
        # The page's hidden stock template, "Only %1 left" with no threshold set, is read by
        # no reader: no menu, no figure.
        hidden = ("{'result': '### Page\\n- Page URL: " + TEE_URL + "\\n### Snapshot\\n```yaml\\n"
                  "- generic [ref=f1e70]: Only %1 left\\n```'}")
        self.assertEqual(sufficiency.menu_blocks(hidden, whole_page=True), [])
        self.assertEqual(sufficiency.evidence(hidden), {"deltas": set(), "absolutes": set(), "any": set()})
        # And the buying universal is refuted by a disabled M alone, never by its label.
        page_ = page.Page(url=GO.split()[2], total=1, next_page=False, listings=[
            page.Listing(seller="Harbour Lane Goods", title="Example Tee - Harbour Lane Goods", url=TEE_URL,
                         advertised=12.25)])
        every = form.Form("forall", "availability", filters=(form.Filter("size", "=", "M"),
                                                             form.Filter("availability", "=", "buyable")))
        opened = {"slug:example-tee-01"}
        self.assertIsNone(primitives.counterexample_seen(every, page_, opened, enabled))
        self.assertIsNotNone(primitives.counterexample_seen(every, page_, opened, disabled))


class LabelFigures(unittest.TestCase):
    def test_a_labels_figure_is_never_a_price_seen(self):
        # Planted: `evidence` reading the text as it is, $9.99 was seen.
        snapshot = ('- combobox "Size *" [ref=e1]:\n  - option "Choose an Option..." [selected]\n'
                    '  - option "XS - Promo $9.99"\n  - option "M - Only 2 left!"\n- generic: $14.20')
        escaped = json.dumps(snapshot)      # the runtime's JSON, quotes escaped
        for label, text in (("as printed", snapshot), ("escaped", escaped)):
            with self.subTest(text=label):
                seen = sufficiency.evidence(text)
                self.assertNotIn(999, seen["absolutes"] | seen["any"])
                self.assertIn(1420, seen["absolutes"])
        # A promotion's figure in the page's text is a claim too.
        self.assertNotIn(999, sufficiency.evidence("XS on promotion at $9.99. $14.20")["absolutes"])
        # Quiet: a surcharge in a pack's label is still a surcharge, and still a figure seen.
        pack = sufficiency.evidence('option "2 x 9.5L +$15.01"')
        self.assertEqual((pack["deltas"], 1501 in pack["any"], pack["absolutes"]), ({1501}, True, set()))
        self.assertEqual(sufficiency.evidence("$9.99")["absolutes"], {999})

    def test_an_answer_quoting_a_label_claims_no_price_and_one_taking_it_is_caught(self):
        # Planted: `check` reading the answer as it is, the careful answer was refused for $9.99.
        seen = sufficiency.evidence('option "XS - Promo $9.99"\n- generic: $14.20')
        careful = "The XS label says Promo $9.99, but XS costs $14.20 there once chosen."
        self.assertTrue(sufficiency.check(careful, seen)["ok"])
        taken = sufficiency.check("XS costs $9.99 at Harbour Lane Goods.", seen)
        self.assertEqual((taken["ok"], taken["flag"]), (False, "unsupported_number"))
        # The box's own checks read the price an answer names the same way. Planted:
        # `primitives.answer_prices` and `policy.page_floor` without the blanking, each named $9.99.
        self.assertEqual(primitives.answer_prices(careful), [14.20])
        listings = [page.Listing(seller=f"Seller {c}", title=f"Example Tee - Seller {c}",
                                 url=f"http://localhost:7770/example-tee-0{n}.html", advertised=price)
                    for n, (c, price) in enumerate(zip("ABC", (9.50, 11.00, 13.00)), 1)]
        page_ = page.Page(url=GO.split()[2], total=3, next_page=False, listings=listings)
        across = GO + "Across all the listings, which seller is cheapest for size XS?"
        self.assertEqual(policy.page_floor(across, page_, careful), 3)
        self.assertEqual(policy.page_floor(across, page_, "Seller A charges $9.99 for XS."), 1)


class LabelSentence(unittest.TestCase):
    def setUp(self):
        self.page = thornwood_page()

    def test_every_plan_that_opens_a_listing_ends_with_it_and_no_other_does(self):
        # Planted: the sentence appended to every plan, the results page's included.
        note = f"\n{primitives.LABEL_NOTE}"
        opens = {"availability_bound": THORNWOOD + "Which seller is cheapest for size M among those that can supply it?",
                 "total_bound": CHEAPEST_M,
                 "survey": THORNWOOD + "How many of the Thornwood listings have size M in stock?",
                 "exists_price": THORNWOOD + "Is there any seller under $20 for size M?",
                 "topk_price": THORNWOOD + "Which are the three cheapest sellers for size M?",
                 "argmax_price": THORNWOOD + "Which seller is the most expensive for size M?"}
        for kind, question in opens.items():
            for exhaust in (False, True):
                with self.subTest(kind=kind, exhaust=exhaust):
                    decision = box.decide(question, self.page, exhaust=exhaust)
                    self.assertEqual(decision.kind, kind)
                    self.assertTrue(decision.query.endswith(note))
                    self.assertEqual(decision.query.count(primitives.LABEL_NOTE), 1)
        refutation = box.decide(THORNWOOD + "Does every Thornwood listing offer size M?", self.page, reply="menu")
        self.assertTrue(refutation.query.endswith(note))
        headline = box.decide(THORNWOOD + "Which listing advertises the lowest price on the results page?", self.page)
        self.assertEqual(headline.kind, "results_page")
        self.assertNotIn(primitives.LABEL_NOTE, headline.query)

    def test_it_is_one_sentence_of_retrieval_guidance(self):
        sentence = primitives.LABEL_NOTE
        self.assertEqual(re.findall(r"[.!?](?=\s|$)", sentence), ["."])
        for words in ("label", "promotional or stock text", "the price is the one shown after the size is chosen",
                      "not a checked fact"):
            self.assertIn(words, sentence)
        self.assertIsNone(re.search(r"\d", sentence))     # no figure, so no arithmetic

    def test_a_text_sent_before_it_was_added_is_reproduced_without_it(self):
        # Planted: `box.ADDED` emptied, a box v18 text was not reproduced.
        decision = box.decide(CHEAPEST_M, self.page)
        old = box.as_sent_by(decision.query, 18)
        self.assertNotIn(primitives.LABEL_NOTE, old)
        self.assertEqual(old + f"\n{primitives.LABEL_NOTE}", decision.query)
        self.assertEqual(box.as_sent_by(decision.query, 19), decision.query)
        record = {**decision.record(), "box_version": 18, "query": old}
        self.assertEqual(replay_box.reproduction(replay_box.stored_decision({"box": record}), record), "")


# ---------------------------------------------------------------------------
# 5. Size XS as a target, and the promo check

# The two templates as the verifier finalised them on 24 October 2026, filled for the made-up
# Example search of `named_page`: a seller its titles name in full, and a promotion's figure.
XS_PRICE = GO + ("What is the lowest price anyone charges for size XS of the Example tee, among those that "
                 "can actually be bought?")
PROMO_CHECK = GO + ("The Mellow Fields listing of the Example tee says in its size menu that size XS is on "
                    "promotion at $9.99. Is that what size XS costs on that listing? If not, what does it cost?")


class SizeXS(unittest.TestCase):
    def setUp(self):
        self.page = named_page()

    def test_the_six_sizes_and_their_words(self):
        # Planted: the four sizes of normalisation v4 again, "extra small" and XXL were none.
        self.assertEqual(normalise.SIZES, ("XS", "S", "M", "L", "XL", "XXL"))
        for value, size in (("xs", "XS"), ("XS", "XS"), ("extra small", "XS"), ("extra-small", "XS"),
                            ("x-small", "XS"), ("size XS", "XS"), ("xxl", "XXL"), ("2XL", "XXL"),
                            ("xx-large", "XXL"), ("double extra large", "XXL"), ("XS - Promo $9.99", "XS"),
                            ("M - Only 2 left!", "M"), ("medium", "M")):
            with self.subTest(value=value):
                self.assertEqual(normalise.size_of(value), size)
        self.assertIsNone(normalise.size_of("2 x 9.5L"))
        # A word names its size only where no longer word holds it. Planted: every word read
        # where it stands, "extra small" named S as well.
        for words, named in (("an extra small tee", {"XS"}), ("a double extra large tee", {"XXL"}),
                             ("an extra large tee", {"XL"}), ("a small tee", {"S"}), ("size XS or S", {"XS", "S"})):
            with self.subTest(words=words):
                self.assertEqual(normalise.sizes_named(GO + words), named)

    def test_the_xs_question_plans_its_own_size(self):
        rules = box.decide(XS_PRICE, self.page)
        self.assertEqual((rules.kind, rules.form.filter("size").value, rules.form.filter("availability").value),
                         ("availability_bound", "XS", "buyable"))
        self.assertNotIn("size M", rules.query)
        for label, value in (("XS", "XS"), ("its word", "extra small"), ("its label", "XS - Promo $9.99")):
            with self.subTest(model=label):
                model = box.decide(XS_PRICE, self.page, parser="model", call=stub(reply(filters=[
                    f("size", "=", value), BUYABLE])))
                self.assertEqual((model.parse.used, model.kind, model.form.filter("size").value),
                                 ("model", "availability_bound", "XS"))
        # Quiet the other way: a model that reads another size falls back.
        wrong = box.decide(XS_PRICE, self.page, parser="model", call=stub(reply(filters=[f("size", "=", "S"), BUYABLE])))
        self.assertEqual(wrong.parse.used, "rules")
        self.assertIn("the form asks about size S, which the question does not name", wrong.parse.fallback_reason)

    def test_no_size_is_fixed_the_size_comes_from_the_question(self):
        for size in normalise.SIZES:
            with self.subTest(size=size):
                decision = box.decide(XS_PRICE.replace("size XS", f"size {size}"), self.page)
                self.assertEqual((decision.kind, decision.form.filter("size").value), ("availability_bound", size))


class PromoCheck(unittest.TestCase):
    def setUp(self):
        self.page = named_page()

    def test_it_is_a_lookup_on_the_named_listing(self):
        decision = box.decide(PROMO_CHECK, self.page)
        mellow = next(item for item in self.page.listings if item.seller == "Mellow Fields")
        self.assertEqual((decision.kind, decision.plan.primitive, [c.url for c in decision.plan.candidates]),
                         ("named_lookup", "lookup", [mellow.url]))
        self.assertEqual((decision.form.filter("seller").value, decision.form.filter("size").value,
                          decision.form.filter("price")), (("Mellow Fields",), "XS", None))
        for words in ("Open each of them and nothing else", f"- Mellow Fields, {mellow.url}",
                      "choose size XS, then look at the page again and read the price it now shows",
                      "give the figure you read for each named listing, then answer the question from those figures",
                      primitives.LABEL_NOTE):
            self.assertIn(words, decision.query)
        # Held to every soundness property, as every plan is (LESSONS 35).
        self.assertEqual(form.verify(decision.form, self.page), [])
        # The claim the answer quotes back is the question's own figure, not an invented price.
        self.assertIn(999, box.stated_figures(decision))
        # The model's lookup is used as it is.
        model = box.decide(PROMO_CHECK, self.page, parser="model", call=stub(reply(
            quantifier="lookup", filters=[f("seller", "in", ["Mellow Fields"]), f("size", "=", "XS")])))
        self.assertEqual((model.parse.used, model.query), ("model", decision.query))

    def test_a_promotions_figure_is_never_made_a_limit(self):
        # Planted: the check left out of `normalise.conflicts`, the model's limit at $9.99 was
        # used and the plan counted the listing only at or below the label's figure.
        limited = reply(quantifier="lookup", filters=[f("seller", "in", ["Mellow Fields"]), f("size", "=", "XS"),
                                                      f("price", "<=", 9.99)])
        decision = box.decide(PROMO_CHECK, self.page, parser="model", call=stub(limited))
        self.assertEqual((decision.parse.used, decision.kind), ("rules", "named_lookup"))
        self.assertIn("the form sets a price limit of 9.99, a figure the question gives as a promotion's claim, "
                      "not a limit", decision.parse.fallback_reason)
        self.assertNotIn("9.99", decision.plan.instruction)
        # Quiet: a limit the question's own words set, beside a promotion's other figure; and
        # a figure that stands once as a claim and once as a limit. Planted: `promoted` true
        # wherever the figure stands as a claim once, the second was refused.
        self.assertTrue(normalise.promoted(PROMO_CHECK, 9.99))
        self.assertFalse(normalise.promoted(GO + "Is size XS under $9.99 anywhere?", 9.99))
        both = GO + "One listing says XS is on promotion at $9.99. Can I get XS under $9.99 anywhere?"
        self.assertFalse(normalise.promoted(both, 9.99))
        under = box.decide(both, self.page, parser="model", call=stub(reply(
            quantifier="exists", filters=[f("size", "=", "XS"), f("price", "<", 9.99), BUYABLE])))
        self.assertEqual(under.parse.used, "model", under.parse.fallback_reason)


if __name__ == "__main__":
    unittest.main()
