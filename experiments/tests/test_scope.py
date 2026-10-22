"""The product a question asks about (box v17, normalisation v4, primitives v11, 22 October
2026, for the second claim run): on a page of a tee and a water under one brand, a plan
over the results ranges over the listings of the product the question names, by the
titles' head nouns, under either parser, and the record keeps the listing set and why.

Every rule has a case where it fires and one where it stays quiet, and each fault named was
planted in the code, with a fresh bytecode cache (LESSONS 39), and seen to fail its test
before the code was put back (LESSONS 31). The made-up market's sellers and prices belong to
no generated market. The live test reads the development market, Larchmere, and skips when
the shop or its fixture is not here. Every model reply is a stub; nothing is sent.
"""
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import box  # noqa: E402
import form  # noqa: E402
import page  # noqa: E402
import replay_box  # noqa: E402
from form import Filter  # noqa: E402
from test_box import BASE, market_facts, openjiuwen_log  # noqa: E402
from test_model_parser import f, reply, stub  # noqa: E402

URL = f"{BASE}/catalogsearch/result/?q=Example"
SECOND = f"{BASE}/catalogsearch/result/index/?p=2&q=Example"
GO = f"Go to {URL} . "
# The development market's six phrasings, with the made-up brand: three of the tee, three of
# the water, in an order that mixes them over two pages.
LISTINGS = [("Example Heavyweight Cotton Tee", "Bramwell Knitwear", 14.20),
            ("Example Spring Water", "Fenwick Springs Trading", 9.10),
            ("Example Heavyweight Cotton Crew Neck Tee", "Ormsby Garment Co", 12.60),
            ("Example Natural Spring Water, Still", "Tolland Drinks Supply", 8.40),
            ("Example Heavyweight Cotton Tee, Unisex", "Wexcombe Apparel", 15.90),
            ("Example Still Spring Water", "Halsey Beverage Traders", 10.30)]
TEES = [f"{BASE}/example-{n:02d}.html" for n in (1, 3, 5)]
WATERS = [f"{BASE}/example-{n:02d}.html" for n in (2, 4, 6)]
TEE = GO + "What is the lowest price anyone charges for size M of the Example tee, among those that can actually be bought?"
WATER = (GO + "What is the lowest price anyone charges for the 2 x 9.5L pack of Example water, among "
         "those that can actually be bought?")


def two_products() -> page.Page:
    listings = [page.Listing(seller=seller, title=f"{name} - {seller}", url=f"{BASE}/example-{n:02d}.html",
                             advertised=price) for n, (name, seller, price) in enumerate(LISTINGS, 1)]
    return page.Page(url=URL, listings=listings, total=6, next_page=False, pages=(URL, SECOND), reader="fetch")


class TheProductScope(unittest.TestCase):
    def setUp(self):
        self.page = two_products()

    def test_the_made_up_market_is_nobodys(self):
        sellers, prices = market_facts()
        for _, seller, price in LISTINGS:
            self.assertNotIn(seller, sellers)
            self.assertNotIn(f"{price:.2f}", prices)

    def test_a_question_naming_one_product_is_planned_over_its_listings_alone(self):
        # Planted: `Scope.for_form` never applying, both plans ranged over all six.
        for question, kept, product in ((TEE, TEES, "tee"), (WATER, WATERS, "water")):
            with self.subTest(product=product):
                decision = box.decide(question, self.page)
                self.assertEqual(sorted(c.url for c in decision.plan.candidates), kept)
                self.assertEqual((decision.scope.product, decision.scope.applied, list(decision.scope.kept)),
                                 (product, True, kept))
                record = decision.record()["scope"]
                self.assertEqual((record["product"], record["kept"], record["urls"], record["products"]),
                                 (product, 3, kept, ["tee", "water"]))
                self.assertIn(f"the question names the {product}, the product of 3 of the 6 listings",
                              record["reason"])
                # The page recorded is the page read, whole.
                self.assertEqual(decision.record()["page"]["count"], 6)
        tee = box.decide(TEE, self.page).query
        self.assertIn("The search results list 6 listings on 2 pages; there is no further page. 3 of them are "
                      "the tee the question asks about, by their titles, and only those are part of the "
                      "question.\nListings of the tee by advertised price, read from the results pages:\n"
                      "1. Ormsby Garment Co, advertised $12.60, http://localhost:7770/example-03.html\n"
                      "2. Bramwell Knitwear, advertised $14.20, http://localhost:7770/example-01.html\n"
                      "3. Wexcombe Apparel, advertised $15.90, http://localhost:7770/example-05.html\n", tee)
        self.assertNotIn("Fenwick Springs Trading", tee)

    def test_the_same_step_under_the_model_parser(self):
        # Planted: the model's path planning over the whole page, its plan ranged over six.
        call = stub(reply(filters=[f("size", "=", "M"), f("availability", "=", "buyable")]))
        model = box.decide(TEE, self.page, parser="model", call=call)
        rules = box.decide(TEE, self.page)
        self.assertEqual((model.parse.used, model.scope.applied), ("model", True))
        self.assertEqual([c.url for c in model.plan.candidates], [c.url for c in rules.plan.candidates])
        self.assertEqual(model.scope, rules.scope)
        # And when the model's form falls back, the rules' plan is scoped the same.
        fallen = box.decide(TEE, self.page, parser="model", call=stub("no form here"))
        self.assertEqual((fallen.parse.used, fallen.scope.applied, len(fallen.plan.candidates)), ("rules", True, 3))

    def test_no_product_or_both_is_every_listing_and_says_why(self):
        # Planted: the first product named taken when the question names both, the second
        # case was planned over the tee alone.
        for question, words in (
                (GO + "Which listing advertises the lowest price on the results page?",
                 "the question names none of the products the titles name (tee, water)"),
                (GO + "Which is cheaper, the Example tee or the Example water, on the results page?",
                 "the question names tee and water, so every listing is planned over")):
            with self.subTest(question=question[-50:]):
                decision = box.decide(question, self.page)
                self.assertEqual((decision.scope.product, decision.scope.applied), (None, False))
                self.assertIn(words, decision.scope.reason)
                self.assertEqual(len(decision.plan.candidates), 6)
                self.assertIn("The search results list 6 listings on 2 pages;", decision.query)

    def test_a_plural_names_the_product_and_another_title_word_does_not(self):
        tees = box.decide(GO + "Which of the Example tees is cheapest for size M?", self.page)
        self.assertEqual((tees.scope.product, len(tees.plan.candidates)), ("tee", 3))
        # "still" is a word of two water titles, not a product: the water's three are kept.
        # Planted: the scope matched any title word, it kept two.
        still = box.decide(GO + "Does every Example water listing still stock the 2 x 9.5L pack? Answer yes or "
                                "no.", self.page, reply="menu")
        self.assertEqual(sorted(c.url for c in still.plan.candidates), WATERS)

    def test_a_page_of_one_product_or_without_titles_is_never_scoped(self):
        one = page.Page(url=URL, listings=[item for item in self.page.listings if item.url in TEES],
                        total=3, next_page=False, pages=(URL,))
        decision = box.decide(TEE, one)
        self.assertEqual((decision.scope.product, decision.scope.applied), (None, False))
        self.assertEqual(decision.scope.reason, "every listing's title names the same product, the tee")
        self.assertIn("The results page lists 3 listings on one page; there is no next page.\n"
                      "Listings by advertised price, read from the results page:\n", decision.query)
        untitled = page.from_record({**self.page.record(), "listings": [
            {k: v for k, v in item.items() if k != "title"} for item in self.page.record()["listings"]]})
        decision = box.decide(TEE, untitled)
        self.assertEqual((decision.scope.product, len(decision.plan.candidates)), (None, 6))
        self.assertIn("kept no titles", decision.scope.reason)

    def test_a_lookup_names_its_own_listings_and_is_not_scoped(self):
        pair = GO + "Between Fenwick Springs Trading and Bramwell Knitwear, who is cheaper for size M of the tee?"
        decision = box.decide(pair, self.page)
        self.assertEqual((decision.kind, decision.scope.product, decision.scope.applied), ("named_lookup", "tee", False))
        self.assertIn("Fenwick Springs Trading", decision.query)

    def test_neither_parser_reads_the_question_differently(self):
        # The rules' form is read from the whole page, as before box v17: the scope is a step
        # of the block after the parse. A question naming a seller of the other product shows
        # it: read from the tee's listings alone, the rules would not find the seller.
        # Planted: the rules reading the scoped page, the third form differed.
        named = GO + "Is Fenwick Springs Trading the cheapest seller of the Example tee in size M?"
        for question in (TEE, WATER, named):
            with self.subTest(question=question[-50:]):
                decision = box.decide(question, self.page)
                self.assertEqual(decision.form, form.from_rules(decision.question, self.page))
        scoped = box.decide(named, self.page).planned
        self.assertEqual(len(scoped.listings), 3)
        self.assertNotEqual(form.from_rules(named, scoped), form.from_rules(named, self.page))
        self.assertEqual(form.from_rules(named, self.page).evidence["filter:seller"], "Fenwick Springs Trading")

    def test_a_title_filter_is_held_to_the_listings_planned_over(self):
        # On a tee question the model's "tee" restates the tee listings and is dropped; on a
        # question naming no product it tells the products apart on the whole page and is
        # kept, so the form, with a filter no plan carries, is the rules' to decide.
        # Planted: the restatement read from the whole page, the first was kept.
        titled = reply(filters=[f("size", "=", "M"), f("availability", "=", "buyable"), f("title", "contains", "tee")])
        decision = box.decide(TEE, self.page, parser="model", call=stub(titled))
        self.assertEqual((decision.parse.used, decision.form.filter("title")), ("model", None))
        self.assertIn("dropped title contains 'tee': every listing of the tee the question names has "
                      "'example heavyweight cotton tee' in its title", " ".join(decision.parse.changes))
        plain = GO + "What is the lowest price anyone charges for size M, among those that can actually be bought?"
        kept = box.decide(plain, self.page, parser="model", call=stub(titled))
        self.assertEqual((kept.parse.used, kept.scope.product), ("rules", None))
        self.assertIsNotNone(kept.parse.model_form.filter("title"))

    def test_the_check_counts_the_product_planned_over(self):
        # A tee run that opened every listing has opened three of its market, not six.
        # Planted: `box.check` reading the whole page, it counted six.
        decision = box.decide(TEE, self.page)
        with tempfile.TemporaryDirectory() as tmp:
            log = openjiuwen_log(tmp, "run", TEES + WATERS)
            verdict = box.check(decision, "Ormsby Garment Co, $12.60.", log)
        self.assertEqual(verdict["opened"], 3)

    def test_a_stored_plan_is_replayed_over_the_listings_it_ranged_over(self):
        # Planted: `stored_decision` without the scope, the text did not reproduce.
        record = box.decide(TEE, self.page).record()
        rebuilt = replay_box.stored_decision({"box": record})
        self.assertEqual(f"{rebuilt.question}\n\n{rebuilt.plan.text}", record["query"])
        self.assertEqual(box.Scope.from_record(record["scope"]), box.decide(TEE, self.page).scope)
        self.assertIsNone(box.Scope.from_record(None))


def larchmere() -> tuple[str | None, page.Page | None, dict]:
    """Why the live test cannot run, or the development market's page and each listing's
    product by its fixture, which the test reads and the box never does."""
    fixture = paths.FIXTURES / "aplus_dev.json"
    if not fixture.exists():
        return "the development market's fixture, aplus_dev.json, is not in env/fixtures", None, {}
    url = f"{BASE}/catalogsearch/result/?q=Larchmere"
    try:
        urllib.request.urlopen(url, timeout=10).close()
    except OSError:
        return "the local shop did not answer within 10 s", None, {}
    families = json.loads(fixture.read_text())["families"]
    return None, page.read(url, "fetch"), {f"{BASE}/{fam['parent_sku'].lower()}.html": fam["product"]
                                          for fam in families}


class Larchmere(unittest.TestCase):
    """The development market, live: 21 tees and 21 waters on two results pages."""

    @classmethod
    def setUpClass(cls):
        why, cls.page, cls.product = larchmere()
        if why:
            raise unittest.SkipTest(why)

    def test_a_tee_question_plans_the_21_tees_and_a_water_question_the_21_waters(self):
        self.assertEqual((len(self.page.listings), len(self.page.pages)), (42, 2))
        second = set(self.page.listings[36:])
        go = f"Go to {self.page.url} . "
        for question, product in ((go + "What is the lowest price anyone charges for size M of the Larchmere tee, "
                                        "among those that can actually be bought?", "tee"),
                                  (go + "Across the Larchmere water listings, which seller is cheapest for the 2 x "
                                        "9.5L pack, and what is that price? Only count a listing that can actually "
                                        "supply that pack.", "water")):
            with self.subTest(product=product):
                want = {url for url, kind in self.product.items() if kind == product}
                for parser, call in (("rules", None), ("model", stub(reply(filters=[
                        f("size", "=", "M" if product == "tee" else "2 x 9.5L"), f("availability", "=", "buyable")])))):
                    decision = box.decide(question, self.page, parser=parser, call=call)
                    planned = {c.url for c in decision.plan.candidates}
                    self.assertEqual((len(planned), planned), (21, want))
                    self.assertTrue(planned & {item.url for item in second})   # across both pages
                    listed = [line for line in decision.query.splitlines() if line[:1].isdigit() and "advertised $" in line]
                    self.assertEqual(len(listed), 21)


if __name__ == "__main__":
    unittest.main()
