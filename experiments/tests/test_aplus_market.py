"""The A+ market of the second claim protocol (docs/content/claim2-protocol.md): its generator,
the order model it relies on, its questions and keys, and the live checker's comparisons.

Nothing here touches the shop. Every rule is shown firing on a planted fault and staying quiet
on the development market (LESSONS 24, 31), and the order model is checked against the
results pages two batches stored.
"""
import argparse
import copy
import json
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import ambiguity  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402

sys.path.insert(0, str(paths.REPO / "env"))
import check_aplus_market as live  # noqa: E402
import check_market  # noqa: E402
import generate_aplus as aplus  # noqa: E402
import generate_aplus_tasks as aplus_tasks  # noqa: E402
import generate_apparel as apparel  # noqa: E402
import pick_aplus_market as picker  # noqa: E402
import pick_apparel_market as pick  # noqa: E402
import search_order  # noqa: E402

DEV = paths.FIXTURES / "aplus_dev.json"
DEV_TASKS = paths.TASKS / "tasks_aplus_dev.json"
DEV_READINGS = paths.TASKS / "readings_aplus_dev.json"
DEV_SEARCH = paths.REPO / "env" / "manifests" / "aplus_dev-search.json"
DEV_V1_ORDER = paths.REPO / "env" / "manifests" / "aplus_dev-v1-order.json"
HELD_OUT = paths.TASKS / "paraphrases_v2.json"
BRAND = "Larchmere"
TWO_FORMS = True                   # Larchmere's, as the shop's analyzer reads it


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def by_sku(families: list[dict], sku: str) -> dict:
    return next(f for f in families if f["parent_sku"] == sku)


def variant(family: dict, option: str) -> dict:
    return next(v for v in family["variants"] if v["option"] == option)


class OrderModel(unittest.TestCase):
    """`search_order.py` against what the shop showed. Its scores were checked against
    Elasticsearch's own on 22 October 2026 (`search_order.py --validate`, live); here its order
    is checked against the page records two batches stored, without the shop."""

    def test_the_order_is_the_stored_results_pages(self):
        for fixture_name, batch in (("scaled_apparel.json", "20261014T213118"),
                                    ("claim_apparel.json", "20261020T203740")):
            with self.subTest(market=fixture_name):
                fixture = load(paths.FIXTURES / fixture_name)
                stored = check_market.stored_page(paths.RESULTS / batch)["listings"]
                want = [item["url"].rsplit("/", 1)[-1].removesuffix(".html").upper() for item in stored]
                # Thornwood's brand is one form to the analyzer, Ashcombe's two.
                two = fixture_name == "claim_apparel.json"
                got = [f["parent_sku"] for f in search_order.order(fixture["families"], two)]
                self.assertEqual(got, want)
                # The fault this guards against: catalogue order, which the first picker's
                # rules were once written against and which does not decide the page.
                self.assertNotEqual([f["parent_sku"] for f in fixture["families"]], want)

    def test_the_order_is_the_development_markets_live_order(self):
        # Larchmere is two forms to the analyzer. The market as the record's last accepted
        # attempt saw it live, and its first market, kept with the order the shop served for
        # it (env/manifests/aplus_dev-v1-order.json): the case that showed the model wrong.
        accepted = load(DEV_SEARCH)["tried"][-1]
        self.assertEqual(accepted["outcome"], "accepted")
        families = load(DEV)["families"]
        self.assertEqual([f["parent_sku"] for f in search_order.order(families, True)],
                         accepted["live_order"])
        first = load(DEV_V1_ORDER)
        self.assertEqual([f["parent_sku"] for f in search_order.order(first["listings"], True)],
                         first["live_order"])

        # The fault: the phrase prefix split into both forms, as a query without Magento's
        # prefix_search analyzer reads it. Thornwood's and Ashcombe's stored pages cannot tell
        # the two apart; Larchmere's first market can.
        def split(family):
            freq, name, search = search_order.lengths(family)
            tf = search_order._tf
            return (6 * tf(2 * freq, name, search_order.AVGDL_NAME)
                    + 2 * 2 * tf(freq, name, search_order.AVGDL_NAME)
                    + 4 * tf(2 * freq, search, search_order.AVGDL_SEARCH))
        self.assertNotEqual([f["parent_sku"] for f in sorted(first["listings"], key=lambda f: -round(split(f), 9))],
                            first["live_order"])
        ashcombe = load(paths.FIXTURES / "claim_apparel.json")["families"]
        self.assertEqual(sorted(ashcombe, key=lambda f: -round(split(f), 9)),
                         search_order.order(ashcombe, True))

    def test_lengths_are_stored_as_the_index_stores_them(self):
        # Read off the explain output on 22 October 2026: 59 words kept as 56, 47 as 46.
        self.assertEqual([search_order.stored_length(n) for n in (23, 34, 39, 47, 59, 88)],
                         [23, 34, 39, 46, 56, 88])

    def test_a_listing_counts_what_the_index_counts(self):
        # Thornwood's IGR-APP-02, read with the term-vectors API: name 34, _search 59.
        listing = by_sku(load(paths.FIXTURES / "scaled_apparel.json")["families"], "IGR-APP-02")
        self.assertEqual(search_order.lengths(listing), (5, 34, 59))
        self.assertEqual(search_order.child_sku({"parent_sku": "IGR-DEV-07"}, {"option": "2 x 9.5L"}),
                         "IGR-DEV-07-2-X-9-5L")

    def test_under_the_earlier_titles_every_water_listing_scores_below_every_tee(self):
        # The generator's reason for the A+ titles: at one seller-name length, under either
        # reading of the brand, every water listing scores below every tee at every option
        # count, and the earlier name lists give nine sellers in ten the same length.
        def listing(phrase, option_names, seller_words):
            seller = "Seller" + " Word" * (seller_words - 1)
            return {"name": f"Brand {phrase} - {seller}", "parent_sku": "IGR-DEV-01",
                    "variants": [{"option": o} for o in option_names]}
        for two in (False, True):
            for words in (2, 3):
                with self.subTest(two_forms=two, seller_words=words):
                    tees = [search_order.score(listing("Heavyweight Cotton Tee", apparel.SIZES[:n],
                                                       words), two) for n in (2, 3, 4)]
                    waters = [search_order.score(listing("Still Spring Water, Multipack",
                                                         aplus.WATER_OPTIONS[:n], words), two)
                              for n in (2, 3, 4)]
                    self.assertLess(max(waters), min(tees))
                    # Quiet under the A+ water title: a water listing outscores a tee.
                    ours = search_order.score(listing("Spring Water", aplus.WATER_OPTIONS, words), two)
                    self.assertGreater(ours, min(tees))
        for seconds in (apparel.NAME_SECOND, aplus.water.NAME_SECOND):
            self.assertEqual(sum(len(s.split()) == 1 for s in seconds), 9)
            self.assertEqual(len(seconds), 10)

    def test_equal_scores_keep_catalogue_order(self):
        twins = [{"name": f"Brand Spring Water - {s} Direct", "parent_sku": f"IGR-DEV-0{i}",
                  "variants": [{"option": "24 x 350ml"}, {"option": "12 x 550ml"}]}
                 for i, s in ((1, "Zed"), (2, "Abe"))]
        self.assertEqual([f["parent_sku"] for f in search_order.order(twins)],
                         ["IGR-DEV-01", "IGR-DEV-02"])


class DevMarket(unittest.TestCase):
    def setUp(self):
        self.fixture = load(DEV)
        self.families = self.fixture["families"]
        self.groups = aplus.products(self.families)


class ProductRules(DevMarket):
    """The tees keep the tee generator's 13 rules and the water the water generator's 8,
    read over what can be bought."""

    def test_the_development_market_passes_every_rule(self):
        self.assertEqual(aplus.check(self.families, BRAND, TWO_FORMS), [])
        self.assertEqual(len(self.groups[aplus.TEE]), aplus.TEE_LISTINGS)
        self.assertEqual(len(self.groups[aplus.WATER]), aplus.WATER_LISTINGS)
        self.assertEqual(self.fixture["_generated"]["version"], aplus.VERSION)

    def test_a_tee_draw_is_the_tee_generators(self):
        # Same model, same draws: the A+ tee is generate_apparel.build_listing, then a title.
        rng_a, rng_b = random.Random("same"), random.Random("same")
        ours = aplus.build_tee("Haldane Threads", 3, rng_a, BRAND)
        theirs = apparel.build_listing("Haldane Threads", 3, rng_b, BRAND, sku_prefix="TEE")
        self.assertEqual(ours["variants"], theirs["variants"])
        self.assertIn(ours["name"].split(" - ")[0].removeprefix(BRAND + " "), aplus.DEV_TEE_PHRASES)

    def test_the_claims_titles_change_nothing_else(self):
        # A seed's prices and stock are the same under either pool; only the titles differ,
        # each from its own pool. Development seed 901's first draw of five listings, not a
        # market (the seed is among those the title study records).
        dev, claim = (aplus.tee_draw(901, 0, 5, BRAND, pool) for pool in (False, True))
        wdev, wclaim = (aplus.water_draw(901, 0, 5, BRAND, pool) for pool in (False, True))
        for a, b, pool in ((dev, claim, aplus.CLAIM_TEE_PHRASES), (wdev, wclaim, aplus.CLAIM_WATER_PHRASES)):
            self.assertEqual([x["variants"] for x in a], [y["variants"] for y in b])
            self.assertEqual([x["seller"] for x in a], [y["seller"] for y in b])
            self.assertTrue(all(y["name"].split(" - ")[0].removeprefix(BRAND + " ") in pool for y in b))
        self.assertEqual(self.fixture["_generated"]["phrasings"], "development")
        titles = {f["name"].split(" - ")[0].removeprefix(BRAND + " ") for f in self.families}
        self.assertLessEqual(titles, set(aplus.DEV_TEE_PHRASES + aplus.DEV_WATER_PHRASES))

    def test_each_tee_rule_fires_on_its_fault(self):
        # The tee generator's 13, unchanged, on the A+ tees: each shown firing on its fault.
        target = aplus.TEE_TARGET
        cheapest_buyable = lambda t: min((v for v in t["variants"] if v["qty"]), key=lambda v: v["price"])  # noqa: E731

        def winner(ts, f):
            return by_sku(ts, f["winner"]["sku"])

        def tie(ts, f):
            variant(aplus.buyable(ts, target)[1], target)["price"] = f["winner"]["price"]

        def winner_cheapest_card(ts, f):
            for v in winner(ts, f)["variants"]:
                if v["option"] != target and v["qty"]:
                    v["price"] = 1.0

        def no_absent_trap(ts, f):
            for t in ts:
                if apparel.price_for(t, target) is None:
                    for v in t["variants"]:
                        v["price"] += 100

        def nothing_prunable(ts, f):
            for t in ts:
                others = [v for v in t["variants"] if v["qty"] and v["option"] != target]
                if others and t["parent_sku"] != f["winner"]["sku"]:
                    min(others, key=lambda v: v["price"])["price"] = 1.0

        def only_the_winner_to_open(ts, f):
            for t in ts:
                if t["parent_sku"] != f["winner"]["sku"]:
                    for v in t["variants"]:
                        v["price"] += 500

        def every_listing_lists_m(ts, f):
            for t in ts:
                if apparel.price_for(t, target) is None:
                    t["variants"].append({"option": target, "price": 99.0, "qty": 0, "units": 1})

        def winner_cheapest_xl(ts, f):
            xl = next((v for v in winner(ts, f)["variants"] if v["option"] == "XL"), None)
            if xl is None:
                winner(ts, f)["variants"].append({"option": "XL", "price": 1.0, "qty": 10, "units": 1})
            else:
                xl["price"] = 1.0

        def sold_out_m_dearer(ts, f):
            for t in ts:
                m = next((v for v in t["variants"] if v["option"] == target), None)
                if m is not None and m["qty"] == 0:
                    m["price"] += 100

        def close_runner_up(ts, f):
            variant(aplus.buyable(ts, target)[1], target)["price"] = round(f["winner"]["price"] * 1.05, 2)

        def floor_of_three(ts, f):
            # Keep the winner and the two other cheapest cards open; price everything else out.
            keep = {f["winner"]["sku"]} | {t["parent_sku"] for t in sorted(
                (t for t in ts if t["parent_sku"] != f["winner"]["sku"]), key=apparel.from_price)[:2]}
            for t in ts:
                if t["parent_sku"] not in keep:
                    for v in t["variants"]:
                        v["price"] += 500
            for t in ts:
                if t["parent_sku"] in keep and t["parent_sku"] != f["winner"]["sku"]:
                    cheapest_buyable(t)["price"] = min(cheapest_buyable(t)["price"], f["winner"]["price"] - 0.5)

        def one_sold_out(ts, f):
            sold = sorted((t for t in ts if apparel.price_for(t, target) is not None
                           and apparel.buyable_price_for(t, target) is None),
                          key=lambda t: apparel.price_for(t, target))
            for t in sold[1:]:
                variant(t, target).update(qty=10, price=variant(t, target)["price"] + 100)

        def two_buyable(ts, f):
            for t in aplus.buyable(ts, target)[2:]:
                variant(t, target)["qty"] = 0

        plants = {"unique_winner": tie, "card_probe_wrong": winner_cheapest_card,
                  "absent_trap": no_absent_trap, "bound_is_useful": nothing_prunable,
                  "bound_not_sufficient": only_the_winner_to_open,
                  "some_missing_target": every_listing_lists_m, "crossover": winner_cheapest_xl,
                  "four_answers": sold_out_m_dearer, "clear_margin": close_runner_up,
                  "floor_is_real": floor_of_three, "sold_out_trap": sold_out_m_dearer,
                  "sold_out_population": one_sold_out, "enough_buyable": two_buyable}
        self.assertEqual(len(plants), 13)
        for rule, plant in plants.items():
            with self.subTest(rule=rule):
                tees = copy.deepcopy(self.groups[aplus.TEE])
                plant(tees, apparel.measure(tees))
                self.assertIn(rule, apparel.check(tees, apparel.measure(tees)))

    def plant_water(self, change) -> list[str]:
        waters = copy.deepcopy(self.groups[aplus.WATER])
        change(waters, aplus.water_measure(waters))
        return aplus.water_check(waters, aplus.water_measure(waters))

    def test_each_water_rule_fires_on_its_fault(self):
        facts = aplus.water_measure(self.groups[aplus.WATER])
        winner, card = facts["winner"]["sku"], facts["cheapest_card"]["sku"]
        unit = facts["best_per_litre"]["sku"]
        target = aplus.WATER_TARGET

        def tie(ws, f):          # another buyable 2 x 9.5L at the winner's price
            other = next(w for w in aplus.buyable(ws, target)[1:])
            variant(other, target)["price"] = f["winner"]["price"]

        def winner_cheapest_card(ws, f):
            for v in by_sku(ws, winner)["variants"]:
                if v["qty"]:
                    v["price"] = round(v["price"], 2) if v["option"] == target else 0.5

        def nothing_prunable(ws, f):
            for w in ws:
                cheapest = min((v for v in w["variants"] if v["qty"]), key=lambda v: v["price"])
                if w["parent_sku"] != winner and cheapest["option"] != target:
                    cheapest["price"] = 1.0

        def nothing_to_open(ws, f):
            for w in ws:
                if w["parent_sku"] != winner:
                    for v in w["variants"]:
                        v["price"] = v["price"] + 500

        def every_listing_lists_it(ws, f):
            for w in ws:
                if apparel.price_for(w, target) is None:
                    w["variants"].append({"option": target, "price": 999.0, "qty": 0,
                                          "units": 2, "volume_ml": 9500})

        def close_runner_up(ws, f):
            runner = aplus.buyable(ws, target)[1]
            variant(runner, target)["price"] = round(f["winner"]["price"] * 1.05, 2)

        def card_best_per_litre(ws, f):   # the cheapest card's own pack the best per litre
            cheapest = min((v for v in by_sku(ws, card)["variants"] if v["qty"]), key=lambda v: v["price"])
            cheapest["price"] = 0.10

        def winner_best_per_litre(ws, f):
            variant(by_sku(ws, winner), target)["price"] = 1.0

        plants = {"unique_winner": tie, "card_probe_wrong": winner_cheapest_card,
                  "bound_is_useful": nothing_prunable, "bound_not_sufficient": nothing_to_open,
                  "some_missing_target": every_listing_lists_it, "clear_margin": close_runner_up,
                  "unit_probe_wrong": card_best_per_litre, "three_answers": winner_best_per_litre}
        self.assertNotEqual(unit, winner)
        for rule, plant in plants.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, self.plant_water(plant))


class MarketRules(DevMarket):
    """The protocol's rules the fixture alone decides, the market's shape, and what every key
    needs to be one answer."""

    def broken(self, change) -> list[str]:
        families = copy.deepcopy(self.families)
        change(families)
        return aplus.market_check(families, BRAND)

    def test_quiet_on_the_development_market(self):
        self.assertEqual(aplus.market_check(self.families, BRAND), [])

    def test_each_rule_fires_on_its_fault(self):
        k = aplus.keys(self.families)
        tee_winner, water_winner = k["tee_winner"]["parent_sku"], k["water_winner"]["parent_sku"]

        def no_sold_out(product, option):
            def change(families):
                for f in families:
                    if f["product"] == product:
                        for v in f["variants"]:
                            if v["option"] == option and v["qty"] == 0:
                                v["qty"] = 10
            return change

        def per_litre_at_the_winner(families):
            variant(by_sku(families, water_winner), aplus.WATER_TARGET)["price"] = 1.0

        def too_few(families):
            del families[aplus.PAGE_SIZE:]

        def too_many(families):
            extra = copy.deepcopy(families[:aplus.PAGE_SIZE + 1])
            for n, f in enumerate(extra, len(families) + 1):
                f["parent_sku"] = f"IGR-DEV-{n:02d}"
            families += extra

        def shared_first_word(families):
            families[1]["seller"] = families[0]["seller"].split()[0] + " Direct"

        def first_word_in_a_name(families):     # "Cellar" inside "... Cellars": the reason it went
            families[0]["seller"], families[1]["seller"] = "Cellar Direct", "Oakfield Cellars"

        def first_word_in_a_question(families):
            families[0]["seller"] = "Litre Supply"

        def product_word_in_a_name(families):
            families[0]["seller"] = families[0]["seller"].split()[0] + " Water Company"

        def tied_headline(families):
            cards = sorted((f for f in families if f["product"] == aplus.TEE), key=apparel.from_price)
            low = min((v for v in cards[1]["variants"] if v["qty"]), key=lambda v: v["price"])
            low["price"] = apparel.from_price(cards[0])

        def no_witness(families):
            # The two cheapest twenty cents apart inside one dollar, x.60 and x.80: the limit,
            # the whole-dollar part of x.70, is below both, so nobody sells size M under it.
            whole = int(apparel.buyable_price_for(k["tee_winner"], aplus.TEE_TARGET))
            variant(by_sku(families, tee_winner), aplus.TEE_TARGET)["price"] = whole + 0.60
            variant(by_sku(families, k["tee_runner_up"]["parent_sku"]),
                    aplus.TEE_TARGET)["price"] = whole + 0.80

        def fourth_ties_third(families):
            third = apparel.buyable_price_for(k["top"][-1], aplus.TEE_TARGET)
            variant(by_sku(families, k["top_next"]["parent_sku"]), aplus.TEE_TARGET)["price"] = third

        def per_litre_tie(families):
            # Another listing selling the winning pack, buyable, at the winning price.
            pack = k["per_litre_pack"]
            other = next(f for f in families if f["product"] == aplus.WATER
                         and f["parent_sku"] != k["per_litre"]["parent_sku"]
                         and apparel.price_for(f, pack["option"]) is not None)
            variant(other, pack["option"]).update(price=pack["price"], qty=10)

        def per_litre_close(families):
            # The next seller's best pack priced 5 per cent above the best rate: inside 8.
            runner = by_sku(families, k["per_litre_runner_up"]["parent_sku"])
            best = min((v for v in runner["variants"] if v["qty"]), key=lambda v: v["price"] / aplus.litres(v))
            best["price"] = round(k["per_litre_rate"] * 1.05 * aplus.litres(best), 2)

        def sold_out_dearer(families):
            # Every sold-out 2 x 9.5L above the winner's price: "can be bought" no longer matters.
            for f in families:
                if f["product"] == aplus.WATER and apparel.price_for(f, aplus.WATER_TARGET) is not None \
                        and apparel.buyable_price_for(f, aplus.WATER_TARGET) is None:
                    variant(f, aplus.WATER_TARGET)["price"] = \
                        apparel.buyable_price_for(k["water_winner"], aplus.WATER_TARGET) + 500

        def sold_out_dearer_per_litre(families):
            for f in families:
                if f["product"] == aplus.WATER:
                    for v in f["variants"]:
                        if v["qty"] == 0:
                            v["price"] = round(v["price"] * 10, 2)

        plants = {
            "readings_differ (tee)": ("readings_differ", no_sold_out(aplus.TEE, aplus.TEE_TARGET)),
            "readings_differ (water)": ("readings_differ", no_sold_out(aplus.WATER, aplus.WATER_TARGET)),
            "per_litre_not_target": ("per_litre_not_target", per_litre_at_the_winner),
            "two_pages, one page": ("two_pages", too_few),
            "two_pages, three pages": ("two_pages", too_many),
            "names_distinct, a first word twice": ("names_distinct", shared_first_word),
            "names_distinct, inside a name": ("names_distinct", first_word_in_a_name),
            "names_distinct, inside a question": ("names_distinct", first_word_in_a_question),
            "names_distinct, a product word": ("names_distinct", product_word_in_a_name),
            "headline_unique": ("headline_unique", tied_headline),
            "limit_separates": ("limit_separates", no_witness),
            "top_3_unique": ("top_3_unique", fourth_ties_third),
            "per_litre_margin, a tie": ("per_litre_margin", per_litre_tie),
            "per_litre_margin, 5 per cent": ("per_litre_margin", per_litre_close),
            "water_sold_out_trap": ("water_sold_out_trap", sold_out_dearer),
            "per_litre_sold_out_trap": ("per_litre_sold_out_trap", sold_out_dearer_per_litre),
        }
        for label, (rule, plant) in plants.items():
            with self.subTest(fault=label):
                self.assertIn(rule, self.broken(plant))

    def test_the_margin_and_the_traps_hold_on_the_development_market(self):
        # Quiet, and by what margin: the figures each rule reads.
        k = aplus.keys(self.families)
        self.assertGreaterEqual(k["per_litre_runner_up_rate"] - k["per_litre_rate"], 0.08 * k["per_litre_rate"])
        self.assertLess(apparel.price_for(k["water_sold_out_trap"], aplus.WATER_TARGET),
                        apparel.buyable_price_for(k["water_winner"], aplus.WATER_TARGET))
        self.assertLess(k["sold_out_rate"], k["per_litre_rate"])

    def test_the_per_litre_key_ignores_sold_out_packs(self):
        # A pack listed but sold out at a tenth of a cent a litre changes neither the key nor
        # the facts: the best price per litre is over packs that can be bought.
        k = aplus.keys(self.families)
        families = copy.deepcopy(self.families)
        other = next(f for f in families if f["product"] == aplus.WATER
                     and f["parent_sku"] != k["per_litre"]["parent_sku"])
        other["variants"][0].update(qty=0, price=0.02)
        planted = aplus.keys(families)
        self.assertEqual((planted["per_litre"]["parent_sku"], planted["per_litre_rate"]),
                         (k["per_litre"]["parent_sku"], k["per_litre_rate"]))
        self.assertEqual(aplus.water_measure(aplus.products(families)[aplus.WATER])["best_per_litre"]["sku"],
                         k["per_litre"]["parent_sku"])
        self.assertIsNone(aplus.best_rate({"variants": [{"price": 1.0, "qty": 0, "units": 2, "volume_ml": 9500}]}))

    def test_each_names_check_reports_its_own_fault(self):
        # First words used nowhere else in this market, so each plant meets one check only.
        plants = {
            "a seller first word is used twice": lambda fs: fs[1].update(
                seller=fs[0]["seller"].split()[0] + " Direct"),
            "its first word is inside another seller's name": lambda fs: (
                fs[0].update(seller="Cellar Direct"), fs[1].update(seller="Zennor Cellars")),
            "its first word is inside a text the scorer reads": lambda fs: fs[0].update(seller="Litre Supply"),
            "it holds a product's own word": lambda fs: fs[0].update(seller="Zennor Water Company"),
        }
        for words, plant in plants.items():
            with self.subTest(check=words):
                families = copy.deepcopy(self.families)
                plant(families)
                self.assertIn(words, "; ".join(aplus.name_problems(families, BRAND)))

    def test_the_claims_words_are_held_to_the_names_rule(self):
        # The claim's held-out phrasings are text a scorer reads too, and their words are
        # product words, though development never draws them.
        for seller, words in (("Alpine Direct", "inside a text the scorer reads"),
                              ("Zennor Mineral Co", "it holds a product's own word")):
            with self.subTest(seller=seller):
                families = copy.deepcopy(self.families)
                families[0]["seller"] = seller
                self.assertIn(words, "; ".join(aplus.name_problems(families, BRAND)))

    def test_the_brand_is_held_to_the_names_rule_too(self):
        self.assertEqual(aplus.name_problems(self.families, BRAND), [])
        self.assertTrue(aplus.name_problems(self.families, "Haldanes"))      # a first word inside it
        self.assertTrue(aplus.name_problems(self.families, "Official"))      # a seller name's word

    def test_the_pools_collide_with_nothing(self):
        firsts = [w.lower() for w in aplus.TEE_FIRST + aplus.WATER_FIRST]
        self.assertEqual(len(firsts), len(set(firsts)))
        texts = aplus.words_a_scorer_reads(BRAND)
        seconds = [s.lower() for s in aplus.TEE_SECOND + aplus.WATER_SECOND]
        for first in firsts:
            others = [f for f in firsts if f != first]
            with self.subTest(first=first):
                self.assertFalse([t for t in texts + seconds + others if first in t])
        self.assertFalse(aplus.product_words() & {w.lower() for s in seconds for w in s.split()})
        self.assertGreaterEqual(min(len(aplus.TEE_FIRST), len(aplus.WATER_FIRST)), aplus.TEE_LISTINGS)


class Phrasings(unittest.TestCase):
    """Every title's head noun is its product's, and the claim's phrasings are held out."""

    def test_the_pools_keep_the_rule(self):
        self.assertEqual(aplus.phrase_problems(), [])
        for phrase in aplus.ALL_PHRASES:
            with self.subTest(phrase=phrase):
                # As the box reads a title (box.head_noun): the last word before any comma.
                self.assertIn(aplus.head_noun(phrase), aplus.HEAD_NOUNS.values())
        self.assertEqual(aplus.phrasings(True), {aplus.TEE: aplus.CLAIM_TEE_PHRASES,
                                                 aplus.WATER: aplus.CLAIM_WATER_PHRASES})
        self.assertEqual(aplus.phrasings(False), {aplus.TEE: aplus.DEV_TEE_PHRASES,
                                                  aplus.WATER: aplus.DEV_WATER_PHRASES})

    def test_each_fault_in_a_pool_fires(self):
        faults = {
            "its head noun is not 'Tee'": ("CLAIM_TEE_PHRASES", ("Classic Organic Tee", "Relaxed Fit Basic Tee",
                                                                 "Organic Tee Shirt, Ringspun")),
            "share ['cotton']": ("CLAIM_TEE_PHRASES", ("Classic Organic Tee", "Relaxed Fit Cotton Tee",
                                                        "Organic Ringspun Tee, Short Sleeve")),
            "word counts are not development's": ("CLAIM_WATER_PHRASES", ("Mineral Water", "Alpine Mineral Water",
                                                                          "Mineral Water")),
            "holds the other product's noun": ("CLAIM_WATER_PHRASES", ("Mineral Water", "Alpine Mineral Water",
                                                                       "Tee Shop Mineral Water")),
        }
        for words, (pool, value) in faults.items():
            with self.subTest(fault=words), mock.patch.object(aplus, pool, value):
                self.assertIn(words, "; ".join(aplus.phrase_problems()))


class PageRules(DevMarket):
    """The page rules, on the predicted order of the development market and on planted
    orders. The live check applies the same function to the live pages."""

    def setUp(self):
        super().setUp()
        self.order = self.fixture["_instance"]["predicted_order"]
        self.k = aplus.keys(self.families)

    def test_quiet_on_every_predicted_order(self):
        for label, order in aplus.predicted_orders(self.families, TWO_FORMS).items():
            with self.subTest(scenario=label):
                self.assertEqual(aplus.page_problems(self.families, order), [])

    def test_the_recorded_order_is_the_brands_own(self):
        # Two forms for Larchmere: the order recorded, and every card it gives, are the
        # two-form order's, which is the live one. Version 1 recorded the one-form order.
        self.assertEqual(self.fixture["_generated"]["brand_forms"], 2)
        two = aplus.predicted_orders(self.families, True)["two forms, average lengths x1.0"]
        one = aplus.predicted_orders(self.families, False)["one form, average lengths x1.0"]
        self.assertEqual(self.order, two)
        self.assertEqual(self.order, load(DEV_SEARCH)["tried"][-1]["live_order"])
        cards = {q: [two.index(l["parent_sku"]) + 1 for l in ls]
                 for q, (ls, _) in aplus.answer_listings(self.k).items()}
        self.assertEqual(self.fixture["_instance"]["predicted_cards"], cards)
        # What the generator records for each form: the brand's own order and its cards.
        measured = aplus.measure(self.families, True)
        self.assertEqual((measured["predicted_order"], measured["predicted_cards"]), (two, cards))
        # The fault: the one-form order, as version 1 recorded it, differs here.
        self.assertNotEqual(one, two)
        self.assertEqual(aplus.measure(self.families, False)["predicted_order"], one)
        self.assertNotIn("predicted_order_two_forms", self.fixture["_instance"])

    def moved(self, sku: str, to: int) -> list[str]:
        order = [s for s in self.order if s != sku]
        order.insert(to, sku)
        return aplus.page_problems(self.families, order)

    def test_interleaved_fires_when_a_product_is_one_block(self):
        tees = [s for s in self.order if by_sku(self.families, s)["product"] == aplus.TEE]
        waters = [s for s in self.order if s not in tees]
        self.assertIn("interleaved", aplus.page_problems(self.families, tees + waters))
        # Both products on the first screen but one product alone on page 2.
        mixed = self.order[:aplus.FIRST_SCREEN]
        rest = [s for s in tees + waters if s not in mixed]
        self.assertIn("interleaved", aplus.page_problems(self.families, mixed + rest))

    def test_first_screen_fires_when_an_answer_renders_on_it(self):
        # The tee winner is the witness and the first of the three, so all four tee keys fire.
        expect = {"tee-target-price", "tee-cheapest-target", "tee-exists-under", "tee-top-3"}
        broken = self.moved(self.k["tee_winner"]["parent_sku"], 0)
        self.assertLessEqual(expect, {p.split(":")[1] for p in broken if p.startswith("first_screen")})
        broken = self.moved(self.k["per_litre"]["parent_sku"], 1)
        self.assertIn("first_screen_misleads:water-best-per-litre", broken)
        broken = self.moved(self.k["water_winner"]["parent_sku"], 2)
        self.assertIn("first_screen_misleads:water-cheapest-target", broken)

    def test_first_screen_fires_when_no_card_there_undercuts(self):
        families = copy.deepcopy(self.families)
        for sku in self.order[:aplus.FIRST_SCREEN]:
            for v in by_sku(families, sku)["variants"]:
                v["price"] += 300
        broken = aplus.page_problems(families, self.order)
        for question in aplus.PRICE_QUESTIONS:
            with self.subTest(question=question):
                self.assertIn(f"first_screen_misleads:{question}", broken)

    def test_answer_on_page_2_fires_when_page_2_holds_none(self):
        named = {l["parent_sku"] for listings, _ in aplus.answer_listings(self.k).values()
                 for l in listings}
        self.assertTrue(named & set(self.order[aplus.PAGE_SIZE:]))
        keep = [s for s in self.order if s not in named]
        order = keep[:aplus.PAGE_SIZE - len(named)] + sorted(named) + keep[aplus.PAGE_SIZE - len(named):]
        self.assertIn("answer_on_page_2", aplus.page_problems(self.families, order))

    def counted_off_page_2(self, counted) -> list[str]:
        """The order with every listing `counted` moved to the front, so page 2 holds none."""
        moved = [s for s in self.order if counted(by_sku(self.families, s))]
        return moved + [s for s in self.order if s not in moved]

    def test_counts_need_page_2_fires_for_each_count_and_reading(self):
        # Every count question under each of its readings, read from the templates and the
        # task writer's two-reading list, so a reading dropped from COUNTED is noticed.
        counts = [q for q in aplus.TEMPLATES if "-count-" in q]
        expected = {(q, r) for q in counts
                    for r in (("menu", "buyable") if q in aplus_tasks.TWO_READINGS else ("buyable",))}
        self.assertEqual({(q, r) for q, r, _ in aplus.COUNTED}, expected)
        self.assertEqual(len(expected), 4)
        for question, reading, counted in aplus.COUNTED:
            with self.subTest(question=question, reading=reading):
                # Quiet on the development market: page 2 holds a listing each counts.
                self.assertTrue(any(counted(by_sku(self.families, s)) for s in self.order[aplus.PAGE_SIZE:]))
                broken = aplus.page_problems(self.families, self.counted_off_page_2(counted))
                self.assertIn(f"counts_need_page_2:{question} ({reading})", broken)

    def test_headline_on_page_1_fires_off_page_1_and_without_its_margin(self):
        tees = sorted((f for f in self.families if f["product"] == aplus.TEE), key=apparel.from_price)
        headline = tees[0]["parent_sku"]
        self.assertNotIn(headline, self.order[aplus.PAGE_SIZE:])
        # The cheapest card moved to page 2: a reader of page 1 names another listing.
        self.assertIn("headline_on_page_1", self.moved(headline, len(self.order) - 1))
        # A tee card on page 2 within 8 per cent of it: "every page" might be read otherwise
        # by one who rounds, and the rule asks for a clear margin.
        families = copy.deepcopy(self.families)
        later = next(s for s in self.order[aplus.PAGE_SIZE:] if by_sku(families, s)["product"] == aplus.TEE)
        low = min((v for v in by_sku(families, later)["variants"] if v["qty"]), key=lambda v: v["price"])
        low["price"] = round(apparel.from_price(tees[0]) * 1.04, 2)
        self.assertIn("headline_on_page_1", aplus.page_problems(families, self.order))
        # And at 8 per cent or more it is quiet.
        low["price"] = round(apparel.from_price(tees[0]) * 1.09, 2)
        self.assertNotIn("headline_on_page_1", aplus.page_problems(families, self.order))

    def test_no_order_can_hold_the_every_listing_questions_to_page_2(self):
        # Why rule 2 leaves them out, as MARKET_RULES says: each answers no, and a no needs
        # page 2 only when every listing without the variant renders there, beside the tee
        # and the water the counts put on page 2. The fewest the rules allow, by planting.
        def fewest_absent(product: str, option: str, check) -> int:
            for n in range(len(self.groups[product]) + 1):
                # All but n of the listings without the option given it, listed but sold out.
                draw = copy.deepcopy(self.groups[product])
                like = next(v for listing in draw for v in listing["variants"] if v["option"] == option)
                for listing in [l for l in draw if apparel.price_for(l, option) is None][n:]:
                    listing["variants"].append(dict(like, price=999.0, qty=0))
                if "some_missing_target" not in check(draw):
                    return n
            raise AssertionError(f"some_missing_target fires on every {product} draw")

        tee = fewest_absent(aplus.TEE, aplus.TEE_TARGET, lambda d: apparel.check(d, apparel.measure(d)))
        water = fewest_absent(aplus.WATER, aplus.WATER_TARGET,
                              lambda d: aplus.water_check(d, aplus.water_measure(d)))
        self.assertEqual((tee, water), (4, 1))
        # The listings the buyable counts need on page 2 are none of those.
        counted = {(q, r): c for q, r, c in aplus.COUNTED}
        for question, product, option in (("tee-count-buyable", aplus.TEE, aplus.TEE_TARGET),
                                          ("water-count-buyable", aplus.WATER, aplus.WATER_TARGET)):
            without = [l for l in self.groups[product] if apparel.buyable_price_for(l, option) is None]
            self.assertFalse(any(counted[(question, "buyable")](l) for l in without))
        # Read as what can be bought, readings_differ's sold-out listing of each is one more.
        menu, bought, page_2 = tee + water + 2, tee + water + 4, len(self.families) - aplus.PAGE_SIZE
        self.assertGreater(menu, page_2)
        words = dict(enumerate("zero one two three four five six seven eight nine ten".split()))
        self.assertIn(f"That is {words[menu]} listings, {words[bought]} read as what can be bought, "
                      f"and page 2 holds {words[page_2]}.", " ".join(aplus.MARKET_RULES.split()))


class Guards(unittest.TestCase):
    """What the generator, the picker and the task writer refuse, asked without drawing,
    seeding or writing anything."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = pathlib.Path(self.tmp.name)
        # A protocol as it will read once frozen, and the draft as it reads now.
        self.final = folder / "claim2-protocol.md"
        self.final.write_text("# The second claim run, protocol (FINAL)\n")
        self.claim_out = folder / "claim2_aplus.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_development_seeds_only_unless_the_claim(self):
        self.assertIsNone(aplus.refused(900, False, None))
        self.assertIsNone(aplus.refused(999, False, None))
        self.assertIn("outside development", aplus.refused(1000, False, None))
        self.assertIn("outside development", aplus.refused(899, False, None))

    def test_the_claim_draws_from_1000_once_final_and_never_as_development(self):
        ok = dict(sku_prefix="IGR-CL2", protocol=self.final)
        self.assertIsNone(aplus.refused(1000, True, self.claim_out, **ok))
        for seed in (999, 950, 900, 0):
            with self.subTest(seed=seed):
                self.assertIn("below 1000", aplus.refused(seed, True, self.claim_out, **ok))
        # The protocol as it stands says DRAFT, so the claim is refused today.
        self.assertTrue("DRAFT" in aplus.PROTOCOL.read_text())
        self.assertIn("still says DRAFT", aplus.refused(1000, True, self.claim_out, "IGR-CL2"))
        self.assertIn("development's prefix", aplus.refused(1000, True, self.claim_out, "IGR-DEV", self.final))
        self.assertIn("development's fixture", aplus.refused(1000, True, DEV, "IGR-CL2", self.final))

    def test_the_claims_record_decides_its_seed(self):
        rejected = lambda s: {"seed": s, "outcome": "rejected"}  # noqa: E731
        problem = aplus.claim_record_problem
        self.assertIsNone(problem([], 1000, False))
        self.assertIn("1000 is", problem([], 1001, False))
        self.assertIsNone(problem([rejected(1000)], 1001, False))
        self.assertIn("1001 is", problem([rejected(1000)], 1000, False))
        self.assertIn("1001 is", problem([rejected(1000)], 1002, False))
        # A stop is the shop's or the model's fault, so the same seed is tried again.
        self.assertIsNone(problem([{"seed": 1000, "outcome": "stopped"}], 1000, False))
        self.assertIsNone(problem([{"seed": 1000, "outcome": "no instance"}], 1001, False))
        accepted = [rejected(1000), {"seed": 1001, "outcome": "accepted"}]
        self.assertIsNone(problem(accepted, 1001, True))
        self.assertIn("already ends", problem(accepted, 1002, False))
        self.assertIn("does not end with seed 1002", problem(accepted, 1002, True))
        self.assertIn("where seed 1000 comes next", problem([rejected(1001)], 1002, False))
        self.assertIn("accepts seed 1000 and then", problem(
            [{"seed": 1000, "outcome": "accepted"}, rejected(1001)], 1002, False))

    def test_a_claim_market_is_printed_only_written_and_recorded(self):
        record = pathlib.Path(self.tmp.name) / "claim2_aplus-search.json"
        gate = aplus.claim_gate
        self.assertIn("needs --search-log", gate(1000, None, self.claim_out, False)[0])
        # No record yet: seed 1000 may be drawn as a candidate, not printed.
        self.assertEqual(gate(1000, record, self.claim_out, False), (None, False))
        self.assertIn("printed only once", gate(1000, record, self.claim_out, True)[0])
        record.write_text(json.dumps({"tried": [{"seed": 1000, "outcome": "accepted"}]}))
        # Accepted but its fixture not written: still not printed.
        self.assertIn("printed only once", gate(1000, record, self.claim_out, True)[0])
        self.claim_out.write_text("{}")
        self.assertEqual(gate(1000, record, self.claim_out, True), (None, True))
        self.assertIn("already ends", gate(1001, record, self.claim_out, False)[0])

    def test_the_command_line_refuses_before_drawing(self):
        for args, words in ((["--seed", "1000", "--claim", "--report"], "still says DRAFT"),
                            (["--seed", "999", "--claim", "--report"], "below 1000"),
                            (["--seed", "1000", "--report"], "outside development")):
            with self.subTest(args=args):
                run = subprocess.run([sys.executable, "env/generate_aplus.py", "--brand", BRAND,
                                      "--brand-forms", "2", "--sku-prefix", "IGR-CL2", *args],
                                     cwd=paths.REPO, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn(words, run.stderr)
                self.assertEqual(run.stdout, "")

    def test_no_earlier_market_is_written_over(self):
        for name in aplus.EARLIER:
            with self.subTest(fixture=name):
                self.assertIn("earlier market", aplus.refused(900, False, paths.FIXTURES / name))
        self.assertIsNone(aplus.refused(900, False, DEV))

    def test_the_picker_keeps_off_earlier_prefixes_and_markets(self):
        for prefix in picker.EARLIER_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertIsNotNone(picker.prefix_refused(prefix))
        self.assertIsNone(picker.prefix_refused("IGR-DEV"))
        self.assertIsNotNone(picker.prefix_refused("IGR-APP-X"))
        market = picker.Market(fixture=DEV, brand=BRAND, sku_prefix="IGR-DEV")
        self.assertIsNone(picker.teardown_refused(market, load(DEV)))
        self.assertIn("not an A+", picker.teardown_refused(market, load(paths.FIXTURES / "claim_apparel.json")))
        other = picker.Market(fixture=DEV, brand="Quenby", sku_prefix="IGR-DEV")
        self.assertIn("not Quenby", picker.teardown_refused(other, load(DEV)))

    def test_the_picker_names_children_as_the_seeder_does(self):
        skus = picker.fixture_skus(load(DEV))
        self.assertEqual(len(skus), 42 + sum(len(f["variants"]) for f in load(DEV)["families"]))
        water = next(f for f in load(DEV)["families"] if f["product"] == aplus.WATER
                     and apparel.price_for(f, aplus.WATER_TARGET) is not None)
        self.assertIn(f"{water['parent_sku']}-2-X-9-5L", skus)
        # The fault it avoids: the first picker's naming, right for sizes only.
        self.assertIn(f"{water['parent_sku']}-2 X 9.5L", pick.fixture_skus({"families": [water]}))

    def test_the_task_writer_refuses_another_markets_files(self):
        fixture = load(DEV)
        claim = paths.FIXTURES / "claim_apparel.json"
        self.assertIn("not an A+", aplus_tasks.refused(claim, load(claim), DEV_TASKS, DEV_READINGS))
        self.assertIn("task file of claim_apparel.json", aplus_tasks.refused(
            DEV, fixture, paths.TASKS / "tasks_claim_apparel.json", DEV_READINGS))
        self.assertIn("readings of another market", aplus_tasks.refused(
            DEV, fixture, DEV_TASKS, paths.TASKS / "readings_claim_apparel.json"))
        self.assertIsNone(aplus_tasks.refused(DEV, fixture, DEV_TASKS, DEV_READINGS))

    def test_the_first_screen_is_the_first_protocols(self):
        self.assertEqual(aplus.FIRST_SCREEN, pick.FIRST_ROW)

    def test_the_picker_continues_a_record_only_across_a_change_of_rules(self):
        record = pathlib.Path(self.tmp.name) / "search.json"
        market = picker.Market(fixture=DEV, brand=BRAND, sku_prefix="IGR-DEV")
        accepted = {"seed": 900, "outcome": "accepted", **picker.versions()}
        record.write_text(json.dumps({"brand": BRAND, "sku_prefix": "IGR-DEV", "tried": [accepted]}))
        with self.assertRaises(SystemExit):                 # accepted under the code that runs now
            picker.earlier_tries(market, record)
        older = {**accepted, "generator_version": aplus.VERSION - 1}
        record.write_text(json.dumps({"brand": BRAND, "sku_prefix": "IGR-DEV", "tried": [older]}))
        self.assertEqual(picker.earlier_tries(market, record), [older])
        claim = picker.Market(fixture=self.claim_out, brand=BRAND, sku_prefix="IGR-DEV", claim=True)
        with self.assertRaises(SystemExit):                 # a claim record never continues
            picker.earlier_tries(claim, record)
        other = picker.Market(fixture=DEV, brand="Quenby", sku_prefix="IGR-DEV")
        with self.assertRaises(SystemExit):
            picker.earlier_tries(other, record)

    def test_the_picker_judges_the_live_order_by_the_brands_form(self):
        fixture = load(DEV)
        live_order = load(DEV_SEARCH)["tried"][-1]["live_order"]
        self.assertEqual(picker.order_match(fixture["families"], live_order, True),
                         ("two forms, average lengths x1.0", None))
        # The same live order judged as if the brand were one form: the form is wrong.
        matched, problem = picker.order_match(fixture["families"], live_order, False)
        self.assertIsNone(matched)
        self.assertIn("the form measured is wrong", problem)
        # An order the model gives for neither form: the model is wrong.
        swapped = live_order[:]
        swapped[0], swapped[-1] = swapped[-1], swapped[0]
        self.assertIn("the order model is wrong", picker.order_match(fixture["families"], swapped, True)[1])

    def test_the_picker_passes_the_brands_form_and_the_claims_record(self):
        market = picker.Market(fixture=DEV, brand=BRAND, sku_prefix="IGR-DEV", two_forms=True)
        command = picker.generate_command(900, market)
        self.assertEqual(command[command.index("--brand-forms") + 1], "2")
        self.assertNotIn("--claim", command)
        claim = picker.Market(fixture=self.claim_out, brand="Quenby", sku_prefix="IGR-CL2", claim=True)
        command = picker.generate_command(1000, claim, pathlib.Path("record.json"))
        self.assertEqual(command[-3:], ["--claim", "--search-log", "record.json"])
        self.assertEqual(command[command.index("--brand-forms") + 1], "1")


class Files(unittest.TestCase):
    """The committed fixture, task file and sidecar are what the generators write, byte for
    byte, from the seed, the brand, the prefix and the seed search's record."""

    def test_the_fixture_regenerates(self):
        generated = load(DEV)["_generated"]
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / DEV.name
            subprocess.run([sys.executable, "env/generate_aplus.py", "--seed", str(generated["seed"]),
                            "--brand", generated["brand"], "--brand-forms", str(generated["brand_forms"]),
                            "--sku-prefix", generated["sku_prefix"],
                            "--out", str(out), "--search-log", str(DEV_SEARCH.relative_to(paths.REPO))],
                           cwd=paths.REPO, check=True, capture_output=True)
            self.assertEqual(out.read_bytes(), DEV.read_bytes())
        self.assertEqual(generated["search"], load(DEV_SEARCH))

    def test_the_task_file_and_sidecar_regenerate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks, readings = pathlib.Path(tmp) / DEV_TASKS.name, pathlib.Path(tmp) / DEV_READINGS.name
            subprocess.run([sys.executable, "env/generate_aplus_tasks.py", "--fixture",
                            str(DEV.relative_to(paths.REPO)), "--out", str(tasks),
                            "--readings-out", str(readings)], cwd=paths.REPO, check=True,
                           capture_output=True)
            self.assertEqual(tasks.read_bytes(), DEV_TASKS.read_bytes())
            self.assertEqual(readings.read_bytes(), DEV_READINGS.read_bytes())

    def test_the_search_record_ends_with_the_accepted_seed(self):
        search = load(DEV_SEARCH)
        last = search["tried"][-1]
        self.assertEqual((last["outcome"], last["generator_version"], last["search_order_version"]),
                         ("accepted", aplus.VERSION, search_order.VERSION))
        self.assertEqual(last["seed"], load(DEV)["_generated"]["seed"])
        self.assertTrue(all(t["seed"] in aplus.DEV_SEEDS for t in search["tried"]))

    def test_the_record_holds_every_attempt_at_seed_900(self):
        # Seed 900's first attempt stopped on the order model's fault, its second was
        # interrupted by hand, its third was accepted under version 1; then version 2's.
        tried = load(DEV_SEARCH)["tried"]
        self.assertEqual([(t["seed"], t["outcome"], t["generator_version"]) for t in tried[:3]],
                         [(900, "stopped", 1), (900, "interrupted", 1), (900, "accepted", 1)])
        self.assertEqual(tried[0]["search_order_version"], 0)
        # Each attempt that seeded names its manifest, and the manifest is the market's.
        for entry in tried:
            name = entry.get("seeding_manifest")
            with self.subTest(attempt=entry["summary"][:40]):
                if entry["outcome"] in ("accepted", "rejected") or (entry["outcome"] == "stopped" and name):
                    manifest = load(paths.REPO / "env" / "manifests" / name)
                    self.assertEqual(manifest["fixture"], DEV.name)
        # The stopped attempt's live order is the one its market was later accepted with.
        self.assertEqual(tried[0]["live_order"], tried[2]["live_order"])
        self.assertEqual(tried[2]["live_order"], load(DEV_V1_ORDER)["live_order"])


class Keys(DevMarket):
    """Every key is the fixture's, recomputed here a second way, from the variants."""

    def setUp(self):
        super().setUp()
        self.spec = load(DEV_TASKS)
        self.by = {t["id"]: t for t in self.spec["tasks"]}

    def test_the_questions_are_the_protocols_templates(self):
        self.assertEqual(list(self.by), list(aplus.TEMPLATES))
        for task_id, (_, template) in aplus.TEMPLATES.items():
            with self.subTest(task=task_id):
                query = self.by[task_id]["query"]
                self.assertTrue(query.startswith(f"Go to {{base}}/catalogsearch/result/?q={BRAND} . "))
                limit = self.fixture["_instance"]["exists_limit"]
                self.assertTrue(query.endswith(template.format(brand=BRAND, limit=limit)))

    def test_the_tee_keys(self):
        tees = self.groups[aplus.TEE]
        listed = [t for t in tees if any(v["option"] == "M" for v in t["variants"])]
        able = sorted((t for t in tees if any(v["option"] == "M" and v["qty"] for v in t["variants"])),
                      key=lambda t: variant(t, "M")["price"])
        card = min(tees, key=lambda t: min(v["price"] for v in t["variants"] if v["qty"]))
        first = lambda t: t["seller"].split()[0]  # noqa: E731
        self.assertEqual(self.by["tee-headline"]["expect"],
                         {"kind": "contains", "any": [first(card)],
                          "price": min(v["price"] for v in card["variants"] if v["qty"])})
        self.assertEqual(self.by["tee-target-price"]["expect"],
                         {"kind": "price", "value": variant(able[0], "M")["price"]})
        self.assertEqual(self.by["tee-cheapest-target"]["expect"]["any"], [first(able[0])])
        self.assertEqual(self.by["tee-count-stocked"]["expect"]["value"], len(listed))
        self.assertEqual(self.by["tee-count-buyable"]["expect"]["value"], len(able))
        self.assertEqual(self.by["tee-all-stocked"]["expect"]["value"], len(listed) == len(tees))
        self.assertEqual([i["any"][0] for i in self.by["tee-top-3"]["expect"]["items"]],
                         [first(t) for t in able[:3]])
        # The limit leaves exactly the winner under it.
        limit = self.fixture["_instance"]["exists_limit"]
        under = [t for t in able if variant(t, "M")["price"] < limit]
        self.assertEqual([first(t) for t in under], self.by["tee-exists-under"]["expect"]["any"])
        self.assertEqual(under, able[:1])

    def test_the_water_keys(self):
        waters = self.groups[aplus.WATER]
        pack = "2 x 9.5L"
        listed = [w for w in waters if any(v["option"] == pack for v in w["variants"])]
        able = sorted((w for w in waters if any(v["option"] == pack and v["qty"] for v in w["variants"])),
                      key=lambda w: variant(w, pack)["price"])
        rates = sorted(((v["price"] / (v["units"] * v["volume_ml"] / 1000), w["seller"])
                        for w in waters for v in w["variants"] if v["qty"]))
        first = lambda w: w["seller"].split()[0]  # noqa: E731
        self.assertEqual(self.by["water-target-price"]["expect"]["value"], variant(able[0], pack)["price"])
        self.assertEqual(self.by["water-cheapest-target"]["expect"]["any"], [first(able[0])])
        self.assertEqual(self.by["water-count-buyable"]["expect"]["value"], len(able))
        self.assertEqual(self.by["water-all-stocked"]["expect"]["value"], len(listed) == len(waters))
        self.assertEqual(self.by["water-best-per-litre"]["expect"]["any"], [rates[0][1].split()[0]])
        # The seller whose sold-out pack is cheaper per litre than the answer is excluded by
        # name, the trap per_litre_sold_out_trap puts there.
        sold = min(((v["price"] / (v["units"] * v["volume_ml"] / 1000), w["seller"])
                    for w in waters for v in w["variants"] if not v["qty"]))
        self.assertLess(sold[0], rates[0][0])
        if sold[1] != rates[0][1]:
            self.assertIn(sold[1].split()[0], self.by["water-best-per-litre"]["expect"]["not_any"])
        # Per litre by each pack's own litres: the 2 x 9.5L holds 19, the 24 x 350ml 8.4.
        self.assertEqual([aplus.litres(p) for p in aplus.water.PACKS], [8.4, 6.6, 7.5, 19.0])

    def test_both_readings_differ_where_the_box_asks(self):
        readings = score.readings_for(DEV_TASKS)["buyable"]
        asked = [t["id"] for t in self.spec["tasks"]
                 if ambiguity.ask(t["query"].format(base=self.spec["base_url"]))]
        self.assertEqual(asked, list(aplus_tasks.TWO_READINGS))
        self.assertEqual(load(DEV_READINGS)["two_readings"], asked)
        stocked, buyable = self.by["tee-count-stocked"]["expect"]["value"], readings["tee-count-stocked"]["value"]
        self.assertGreater(stocked, buyable)      # readings_differ: the sold-out are the difference
        # Each buyable key recounted from the variants: a size or pack counts if it can be bought.
        can = lambda f, option: any(v["option"] == option and v["qty"] for v in f["variants"])  # noqa: E731
        tees, waters = self.groups[aplus.TEE], self.groups[aplus.WATER]
        self.assertEqual({task_id: readings[task_id] for task_id in asked}, {
            "tee-count-stocked": {"kind": "count", "value": sum(can(t, "M") for t in tees)},
            "tee-all-stocked": {"kind": "boolean", "value": all(can(t, "M") for t in tees)},
            "water-all-stocked": {"kind": "boolean", "value": all(can(w, "2 x 9.5L") for w in waters)}})
        # And the writer computes them so now, over the market as bought.
        self.assertEqual(aplus_tasks.buyable_reading(self.fixture)["buyable"], readings)
        for task_id in asked:
            with self.subTest(task=task_id):
                self.assertIs(score.under_reading(self.by[task_id], "menu", readings), self.by[task_id])
                self.assertEqual(score.under_reading(self.by[task_id], "buyable", {"buyable": readings})["expect"],
                                 readings[task_id])

    def test_every_keyed_question_has_a_buyable_key(self):
        # The model parser can lead any question it reads to the buyable reading, so suite.py
        # refuses a batch under it with a question that has none (22 October 2026).
        readings = score.readings_for(DEV_TASKS)
        keyed = [t["id"] for t in self.spec["tasks"] if t["expect"]["kind"] != "none"]
        self.assertEqual((list(readings["buyable"]), len(keyed)), (keyed, 13))
        for task in self.spec["tasks"]:
            with self.subTest(task=task["id"]):
                under = score.under_reading(task, "buyable", readings)       # raises on none
                if task["id"] not in aplus_tasks.TWO_READINGS:
                    # Its words settle the reading, so its buyable key is its own.
                    self.assertEqual(under["expect"], task["expect"])
        # The suite's own check, every question read off a page by the model. The box's
        # decision on the live page is not this test's, so build_query is stubbed.
        args = argparse.Namespace(parser="model", reading=None)
        ran = mock.patch.object(suite, "build_query", return_value=("a query", {"box": None, "page": "a page"}))
        three = {"buyable": {task_id: readings["buyable"][task_id] for task_id in aplus_tasks.TWO_READINGS}}
        with ran:
            self.assertEqual(suite.unscorable(self.spec["tasks"], self.spec, args, readings), [])
            # Fires on a sidecar of the three alone, as written until this change.
            self.assertEqual(len(suite.unscorable(self.spec["tasks"], self.spec, args, three)), 10)

    def test_a_one_reading_key_is_its_own_over_the_market_as_bought(self):
        k = aplus_tasks.checked_keys(self.fixture)
        n = len(self.groups[aplus.TEE]), len(self.groups[aplus.WATER])
        own = aplus_tasks.expects_from(k, k, *n)
        bought = aplus_tasks.expects_from(aplus.keys(aplus_tasks.as_bought(self.families)), k, *n)
        self.assertEqual(own, {task["id"]: task["expect"] for task in self.spec["tasks"]})
        self.assertEqual(aplus_tasks.reading_problems(own, bought), [])
        # Planted: the count of tees that can sell M now keyed as the menu's count.
        planted = {**own, "tee-count-buyable": {"kind": "count", "value": k["tee_listed"]}}
        self.assertEqual(aplus_tasks.reading_problems(planted, bought), ["tee-count-buyable"])
        # Planted: the best per litre read over every pack, the sold-out one included.
        sold = k["sold_out_rate_listing"]["seller"].split()[0]
        planted = {**own, "water-best-per-litre": {**own["water-best-per-litre"], "any": [sold]}}
        self.assertEqual(aplus_tasks.reading_problems(planted, bought), ["water-best-per-litre"])
        # Quiet where the per-litre answer is also the listing whose sold-out pack is cheapest
        # per litre: over the market as bought it is a copy, and still never its own trap.
        families = copy.deepcopy(self.families)
        best = by_sku(families, k["per_litre"]["parent_sku"])
        other = next(v for v in best["variants"] if v["option"] != k["per_litre_pack"]["option"])
        other.update(qty=0, price=0.01)
        shown = aplus.keys(families)
        self.assertEqual(shown["sold_out_rate_listing"]["parent_sku"], best["parent_sku"])
        own = aplus_tasks.expects_from(shown, shown, *n)
        bought = aplus_tasks.expects_from(aplus.keys(aplus_tasks.as_bought(families)), shown, *n)
        self.assertEqual(aplus_tasks.reading_problems(own, bought), [])
        self.assertNotIn(best["seller"].split()[0], bought["water-best-per-litre"]["not_any"])

    def test_the_file_names_its_fixture_and_its_own_draw(self):
        self.assertEqual(self.spec["fixture"], DEV.name)
        self.assertEqual(self.spec["_instance"], self.fixture["_instance"])
        self.assertTrue(suite.draw_id(self.spec).startswith(f"{BRAND}:"))
        self.assertNotEqual(suite.draw_id(self.spec), suite.draw_id(load(paths.TASKS / "tasks_claim_apparel.json")))


class Rewordings(DevMarket):
    """The held-out rewordings as `--rewordings` writes them (task F, 22 October 2026), on the
    development market until the claim's exists. Another agent wrote them blind, so they are
    handled here by id, template and their flags: no assertion shows a rewording's text, a
    failure names its id, and no rule or model is put to one (the held-out file's _about)."""

    def setUp(self):
        super().setUp()
        self.held = load(HELD_OUT)
        self.spec = aplus_tasks.spec(self.fixture, DEV.name, self.held)
        self.sidecar = aplus_tasks.readings(self.fixture, DEV.name, DEV_TASKS.name, self.held)
        self.by = {t["id"]: t for t in self.spec["tasks"]}
        self.kept = [e for e in self.held["paraphrases"] if e["meaning_kept"]]

    def test_each_rewording_that_keeps_its_meaning_follows_the_templates(self):
        self.assertEqual(self.spec["tasks"][:15], load(DEV_TASKS)["tasks"])
        self.assertEqual([t["id"] for t in self.spec["tasks"][15:]], [f"rw-{e['id']:02d}" for e in self.kept])
        # Thirty of the thirty-six: the six that change their template's meaning are not tasks.
        self.assertEqual((len(self.kept), len(self.spec["tasks"])), (30, 45))

    def test_a_rewording_carries_its_templates_keys(self):
        for entry in self.kept:
            task, template = self.by[f"rw-{entry['id']:02d}"], self.by[entry["template"]]
            with self.subTest(rewording=entry["id"]):
                self.assertEqual((task["template"], task["rewording"]), (entry["template"], entry["id"]))
                for field in ("family", "product", "gated", "expect", "box"):
                    self.assertEqual(task[field], template[field], field)
                # The template's lead, then the rewording with the market's brand and limit in
                # it and no placeholder left but the suite's {base}. Checked without showing it.
                lead = template["query"].split(" . ", 1)[0]
                rest = task["query"][len(lead) + 3:]
                self.assertTrue(task["query"].startswith(lead + " . "), entry["id"])
                self.assertFalse("{" in rest or "}" in rest, entry["id"])
                self.assertFalse(rest == template["query"][len(lead) + 3:], entry["id"])

    def test_the_sidecar_gives_each_its_templates_buyable_key_and_readings(self):
        committed = load(DEV_READINGS)
        own, buyable = committed["readings"]["buyable"], self.sidecar["readings"]["buyable"]
        for entry in self.kept:
            task_id = f"rw-{entry['id']:02d}"
            with self.subTest(rewording=entry["id"]):
                if entry["template"] in own:
                    self.assertEqual(buyable[task_id], own[entry["template"]])
                else:
                    self.assertNotIn(task_id, buyable)       # a decline's template has no key
        # Every keyed question has a buyable key, the thirteen templates and 26 rewordings, as
        # suite.py's check under the model parser needs (build_query stubbed, as in Keys).
        keyed = [t["id"] for t in self.spec["tasks"] if t["expect"]["kind"] != "none"]
        self.assertEqual((sorted(buyable), len(keyed)), (sorted(keyed), 39))
        args = argparse.Namespace(parser="model", reading=None)
        with mock.patch.object(suite, "build_query", return_value=("a query", {"box": None, "page": "a page"})):
            self.assertEqual(suite.unscorable(self.spec["tasks"], self.spec, args, self.sidecar["readings"]), [])
        # Two readings where the template has them: the six the held-out file expects an ask on.
        asked = [f"rw-{e['id']:02d}" for e in self.kept if e["expected"] == "ask"]
        self.assertEqual(asked, ["rw-07", "rw-09", "rw-10", "rw-21", "rw-33", "rw-36"])
        self.assertEqual(self.sidecar["two_readings"], committed["two_readings"] + asked)
        # Under the menu reading a rewording is scored by its own key, its template's.
        for task_id in asked:
            with self.subTest(task=task_id):
                task = self.by[task_id]
                self.assertIs(score.under_reading(task, "menu", self.sidecar["readings"]), task)
                self.assertEqual(score.under_reading(task, "buyable", self.sidecar["readings"])["expect"],
                                 own[task["template"]])

    def test_a_rewording_its_keys_may_not_fit_is_refused_by_its_id(self):
        first = self.kept[0]
        asks = next(e for e in self.kept if e["template"] in aplus_tasks.TWO_READINGS)
        for label, entry, change, words in (
                ("its template reworded since", first,
                 lambda e: e.update(template_text=e["template_text"] + " Now."), "is not worded as its author"),
                ("a template the file does not hold", first,
                 lambda e: e.update(template="tee-colour"), "which the task file does not hold"),
                ("expected to plan where its template asks", asks,
                 lambda e: e.update(expected="plan"), "for a person to decide")):
            with self.subTest(fault=label):
                broken = copy.deepcopy(self.held)
                planted = next(e for e in broken["paraphrases"] if e["id"] == entry["id"])
                change(planted)
                for write in (lambda h: aplus_tasks.spec(self.fixture, DEV.name, h),
                              lambda h: aplus_tasks.readings(self.fixture, DEV.name, DEV_TASKS.name, h)):
                    with self.assertRaises(SystemExit) as raised:
                        write(broken)
                    message = str(raised.exception)
                    self.assertIn(f"rewording {entry['id']}", message)
                    self.assertIn(words, message)
                    self.assertFalse(entry["text"] in message or entry["template_text"] in message)

    def test_one_command_writes_both_and_shows_no_rewording(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks, readings = pathlib.Path(tmp) / DEV_TASKS.name, pathlib.Path(tmp) / DEV_READINGS.name
            ran = subprocess.run([sys.executable, "env/generate_aplus_tasks.py", "--fixture",
                                  str(DEV.relative_to(paths.REPO)), "--out", str(tasks),
                                  "--readings-out", str(readings), "--rewordings",
                                  str(HELD_OUT.relative_to(paths.REPO))],
                                 cwd=paths.REPO, check=True, capture_output=True, text=True)
            # Compared whole without a diff, which would show the queries.
            self.assertTrue(load(tasks) == self.spec, "the command's task file is not spec()'s")
            self.assertEqual(load(readings), self.sidecar)
        printed = ran.stdout + ran.stderr
        self.assertIn("(45 tasks)", printed)
        self.assertFalse(any(e["text"] in printed for e in self.held["paraphrases"]))

    def test_never_beside_the_development_markets_questions(self):
        # Fires on the committed development files, which the free tests read; quiet on a
        # file outside experiments/tasks/, and on the same files without the rewordings.
        self.assertIn("would put the held-out rewordings", aplus_tasks.refused(
            DEV, self.fixture, DEV_TASKS, DEV_READINGS, rewordings=True))
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            self.assertIn("would put the held-out rewordings", aplus_tasks.refused(
                DEV, self.fixture, out / DEV_TASKS.name, DEV_READINGS, rewordings=True))
            self.assertIsNone(aplus_tasks.refused(DEV, self.fixture, out / DEV_TASKS.name,
                                                  out / DEV_READINGS.name, rewordings=True))
        self.assertIsNone(aplus_tasks.refused(DEV, self.fixture, DEV_TASKS, DEV_READINGS))
        # A claim market's may hold them: the same fixture, drawn from the claim's phrasings.
        claim = copy.deepcopy(self.fixture)
        claim["_generated"]["phrasings"] = "claim"
        self.assertIsNone(aplus_tasks.refused(DEV, claim, DEV_TASKS, DEV_READINGS, rewordings=True))

    def test_the_command_refuses_before_writing(self):
        # The command line asks the same rule. A temporary folder stands for experiments/tasks/,
        # so a command that did not ask would write there and not over the committed files.
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            argv = ["generate_aplus_tasks.py", "--fixture", str(DEV), "--out", str(folder / DEV_TASKS.name),
                    "--readings-out", str(folder / DEV_READINGS.name), "--rewordings", str(HELD_OUT)]
            with mock.patch.object(aplus_tasks, "TASKS", folder), mock.patch.object(sys, "argv", argv), \
                    self.assertRaises(SystemExit) as raised:
                aplus_tasks.main()
            self.assertIn("would put the held-out rewordings", str(raised.exception))
            self.assertEqual(list(folder.iterdir()), [])


class LiveCheckComparisons(DevMarket):
    """`check_aplus_market.py`'s comparisons, on the development market's predicted pages and
    planted faults, without the shop."""

    def setUp(self):
        super().setUp()
        order = self.fixture["_instance"]["predicted_order"]
        cards = [{"url": live.listing_url(by_sku(self.families, s)), "title": by_sku(self.families, s)["name"],
                  "seller": by_sku(self.families, s)["seller"],
                  "advertised": apparel.from_price(by_sku(self.families, s))} for s in order]
        size, total = aplus.PAGE_SIZE, len(cards)
        self.pages = [{"cards": cards[:size], "shown": (1, size), "total": total, "next_page": True},
                      {"cards": cards[size:], "shown": (size + 1, total), "total": total,
                       "next_page": False}]

    def test_the_order_lines_judge_the_brands_form_and_the_record(self):
        order = self.fixture["_instance"]["predicted_order"]
        lines = live.order_lines(self.fixture, order)
        self.assertEqual([ok for ok, _ in lines], [True, True, True])
        swapped = order[:]
        swapped[1], swapped[2] = swapped[2], swapped[1]
        lines = live.order_lines(self.fixture, swapped)
        self.assertFalse(lines[1][0])
        self.assertIn("differs from the fixture's recorded order in 2 positions", lines[1][1])

    def test_correct_pages_pass(self):
        self.assertEqual(live.pages_problems(self.pages, self.fixture), [])
        self.assertEqual(live.live_order(self.pages, self.fixture), self.fixture["_instance"]["predicted_order"])

    def test_each_planted_fault_fires_its_own_check(self):
        # Each fault with the words of the check that must report it, so a check removed
        # fails here even when another check also notices the fault.
        thornwood = "http://localhost:7770/igr-app-07.html"
        first = by_sku(self.families, self.fixture["_instance"]["predicted_order"][0])
        faults = {
            # A third page each page's own checks would pass: only the page count sees it.
            "a third page": (lambda p: p.append({"cards": [], "shown": (73, 42), "total": 42,
                                                 "next_page": False}), "3 results pages, not 2"),
            "page 1 without a next link": (lambda p: p[0].update(next_page=False),
                                           "page 1 does not link a next page"),
            "a toolbar counting another total": (lambda p: p[1].update(total=43),
                                                 "page 2's toolbar counts (37, 42) of 43"),
            "a listing missing": (lambda p: p[1]["cards"].pop(), "page 2 holds 5 cards, not 6"),
            "another market's listing": (lambda p: p[1]["cards"][0].update(url=thornwood),
                                         f"not the market's: ['{thornwood}']"),
            "a listing twice": (lambda p: p[1]["cards"].__setitem__(0, dict(p[0]["cards"][0])),
                                "listed twice"),
            "a card at the cheapest of every variant": (
                lambda p: p[0]["cards"][0].update(advertised=min(v["price"] for v in first["variants"]) - 0.01),
                "not the cheapest buyable"),
            "a title not the fixture's": (lambda p: p[0]["cards"][1].update(title="Larchmere Water - X"),
                                          "is titled 'Larchmere Water - X'"),
        }
        for name, (plant, words) in faults.items():
            with self.subTest(fault=name):
                pages = copy.deepcopy(self.pages)
                plant(pages)
                self.assertIn(words, "; ".join(live.pages_problems(pages, self.fixture)))

    def test_a_page_2_is_read_as_the_shop_prints_it(self):
        # The toolbar of a later page, as Magento writes it (q=water, 22 October 2026).
        html = ('<p class="toolbar-amount" id="toolbar-amount">Items <span class="toolbar-number">37</span>'
                '-<span class="toolbar-number">42</span> of <span class="toolbar-number">42</span></p>'
                '<li class="item product product-item"><a class="product-item-link" '
                'href="http://localhost:7770/igr-dev-08.html">Larchmere Spring Water - Bramley Supply Co</a>'
                '<span data-price-amount="24.36"></span></li>')
        page = live.read_page(html)
        self.assertEqual((page["shown"], page["total"], page["next_page"]), ((37, 42), 42, False))
        self.assertEqual(page["cards"], [{"url": "http://localhost:7770/igr-dev-08.html",
                                          "title": "Larchmere Spring Water - Bramley Supply Co",
                                          "seller": "Bramley Supply Co", "advertised": 24.36}])
        self.assertEqual(live.results_url(BRAND, 2),
                         "http://localhost:7770/catalogsearch/result/index/?p=2&q=Larchmere")

    def test_a_pack_label_is_read_whole_and_is_no_leak(self):
        options = [{"text": "2 x 9.5L +$32.50", "disabled": False, "value": "1"},
                   {"text": "M -$3.29", "disabled": True, "value": "2"}]
        menu = check_market.plain_menu(options, None, 9.80)
        self.assertEqual([(e["label"], e["label_price"], e["buyable"]) for e in menu],
                         [("2 x 9.5L", 42.30, True), ("M", 6.51, False)])
        listing = {"advertised": 9.80, "sizes": [("24 x 350ml", 9.80, True), ("2 x 9.5L", 9.50, True)]}
        self.assertEqual(check_market.leaked("Pack Size 2 x 9.5L, 6 x 1.25L", listing), [])
        self.assertEqual(check_market.leaked('"amount": 9.5}', listing), ["9.50"])
        self.assertEqual(check_market.leaked("As low as $9.50", listing), ["9.50"])
        # A tee price before the size L is still a price.
        tee = {"advertised": 11.87, "sizes": [("S", 12.30, True), ("L", 11.87, True)]}
        self.assertEqual(check_market.leaked("$12.30 L", tee), ["12.30"])

    def test_what_a_render_writes_afresh_is_no_change_and_content_is(self):
        # Each of the five, as Magento writes them (read off the stored pages, 22 October 2026).
        page = (b'<input name="form_key" type="hidden" value="abc123" />'
                b'"formKey":"QHemFUc0E8ZinkjF"'
                b'<a href="http://localhost:7770/customer/account/" id="idJeaw320G" >My Account</a>'
                b'"\\/captcha\\/refresh\\/","isRequired":false,"timestamp":1792662848}'
                b'var elemgEYdz19LArray = [];'
                b'<p>Thornwood</p>"finalPrice":{"amount":15.04}')
        rendered_again = (page.replace(b"abc123", b"zzz999").replace(b"QHemFUc0E8ZinkjF", b"vQ6SCwu762zuNkb6")
                          .replace(b"idJeaw320G", b"idhkaxFvM7").replace(b"1792662848", b"1792667330")
                          .replace(b"elemgEYdz19LArray", b"elemZ7fLhKtzArray"))
        self.assertEqual(live.differences({"a.html": page}, {"a.html": rendered_again}), [])
        for change in ((b"Thornwood", b"Thornw00d"), (b"15.04", b"15.05"), (b"My Account", b"My Acount")):
            with self.subTest(change=change):
                self.assertEqual(live.differences({"a.html": page}, {"a.html": rendered_again.replace(*change)}),
                                 ["a.html"])
        self.assertEqual(live.differences({"a.html": page}, {}), ["a.html"])


if __name__ == "__main__":
    unittest.main()
