"""The tee-only market of design B (env/generate_aplus.py version 4, 24 October 2026, docs/content/
claim2-handover.md section 3): its generator's rules, labels and guards, the order model's reading
of a label, the seeder's writing of one, and the live checker's label lines.

Nothing here touches the shop. Every rule is shown firing on a planted fault and staying quiet on
the development market (LESSONS 24, 31). Design A is shown unchanged: its own tests in
test_aplus_market.py still pass, and here a family without labels counts in the order model as it
did.
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

sys.path.insert(0, str(paths.REPO / "env"))
import check_aplus_market as live  # noqa: E402
import check_market  # noqa: E402
import generate_aplus as aplus  # noqa: E402
import generate_apparel as apparel  # noqa: E402
import pick_aplus_market as picker  # noqa: E402
import search_order  # noqa: E402
import seed_variants  # noqa: E402

DEV = paths.FIXTURES / aplus.B_DEV_FIXTURE
DEV_SEARCH = paths.REPO / "env" / "manifests" / "tee_dev-search.json"
LARCHMERE = paths.FIXTURES / "aplus_dev.json"
XS, M = aplus.XS_TARGET, aplus.TEE_TARGET
# The development market is drawn in the night's second phase; until its fixture exists the
# classes that read it are skipped, and the generator's own tests run.
needs_market = unittest.skipUnless(DEV.exists(), "the tee-only development market is not drawn yet")


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def by_sku(families: list[dict], sku: str) -> dict:
    return next(f for f in families if f["parent_sku"] == sku)


def variant(family: dict, option: str) -> dict:
    return next(v for v in family["variants"] if v["option"] == option)


def price(listing: dict, size: str) -> float:
    return apparel.buyable_price_for(listing, size)


class DevMarket(unittest.TestCase):
    def setUp(self):
        self.fixture = load(DEV)
        self.families = self.fixture["families"]
        self.brand = self.fixture["_generated"]["brand"]
        self.two_forms = self.fixture["_generated"]["brand_forms"] == 2
        self.k = aplus.keys_b(self.families)


class Templates(unittest.TestCase):
    def test_the_eight_tee_templates_and_decline_delivery_are_design_as_word_for_word(self):
        same = ("tee-headline", "tee-target-price", "tee-cheapest-target", "tee-all-stocked",
                "tee-count-stocked", "tee-count-buyable", "tee-exists-under", "tee-top-3", "decline-delivery")
        for name in same:
            with self.subTest(template=name):
                self.assertEqual(aplus.B_TEMPLATES[name], aplus.TEMPLATES[name])
        self.assertEqual(list(aplus.B_TEMPLATES), [*same[:8], "tee-xs-price", "tee-promo-check",
                                                   "decline-delivery", "decline-fit", "decline-scarcity"])
        self.assertNotIn("water", " ".join(t for _, t in aplus.B_TEMPLATES.values()).lower())
        self.assertEqual(aplus.B_PRICE_QUESTIONS, (*aplus.PRICE_QUESTIONS[:4], "tee-xs-price"))
        self.assertEqual([(q, r) for q, r, _ in aplus.B_COUNTED],
                         [("tee-count-stocked", "menu"), ("tee-count-stocked", "buyable"), ("tee-count-buyable", "buyable")])

    def test_the_templates_words_format_without_a_seller(self):
        # words_a_scorer_reads for design B blanks {seller} and {promo} too (the verifier's check).
        texts = aplus.words_a_scorer_reads_b("Thurlby", [])
        self.assertIn("thurlby", texts)
        self.assertTrue(any("on promotion at $." in t for t in texts))
        self.assertFalse(any("{" in t for t in texts))


@needs_market
class Rules(DevMarket):
    """`B_RULES` 1 to 17, the tee rules over six sizes, and the A+ tee rules kept."""

    def test_quiet_on_the_development_market(self):
        version = self.fixture["_generated"]["version"]
        self.assertGreaterEqual(version, 4)
        self.assertEqual(aplus.check(self.families, self.brand, self.two_forms, version, aplus.DESIGN_B), [])
        self.assertEqual(aplus.check_b(self.families, self.brand, self.two_forms, version), [])
        self.assertEqual(aplus.market_check(self.families, self.brand, version, aplus.DESIGN_B), [])
        self.assertEqual(aplus.label_problems(self.families), [])
        self.assertEqual(aplus.fit_text_problems(self.families), [])
        self.assertEqual(len(self.families), aplus.B_LISTINGS)
        self.assertTrue(all(f["attribute"] == aplus.B_ATTRIBUTE and f["product"] == aplus.TEE for f in self.families))
        self.assertTrue(all(len(f["variants"]) <= 6 for f in self.families))
        self.assertTrue(aplus.margins_hold(self.families))

    def test_the_tee_rules_read_xxl_as_the_largest_size(self):
        facts = apparel.measure(self.families, aplus.B_SIZES)
        self.assertEqual(facts["largest_size"], "XXL")
        self.assertEqual(apparel.check(self.families, facts), [])
        # The default reads XL, as every market before: the parameter is what changes it.
        self.assertEqual(apparel.measure(self.families)["largest_size"], "XL")
        self.assertEqual(apparel.measure(load(LARCHMERE)["families"][:1] and
                                         aplus.products(load(LARCHMERE)["families"])[aplus.TEE])["largest_size"], "XL")
        # Fires: the M winner also cheapest for XXL.
        families = copy.deepcopy(self.families)
        winner = by_sku(families, facts["winner"]["sku"])
        xxl = next((v for v in winner["variants"] if v["option"] == "XXL"), None)
        if xxl is None:
            winner["variants"].append({"option": "XXL", "price": 1.0, "qty": 10, "units": 1})
        else:
            xxl["price"] = 1.0
        self.assertIn("crossover", apparel.check(families, apparel.measure(families, aplus.B_SIZES)))

    def broken(self, change, two_forms=None) -> list[str]:
        families = copy.deepcopy(self.families)
        change(families)
        return aplus.market_check_b(families, self.brand, aplus.VERSION, two_forms)

    def test_each_xs_rule_fires_on_its_fault(self):
        k = self.k
        winner, runner = k["xs_winner"]["parent_sku"], k["xs_runner_up"]["parent_sku"]
        best = price(k["xs_winner"], XS)

        def tie(fs):
            variant(by_sku(fs, runner), XS)["price"] = best

        def close(fs):
            variant(by_sku(fs, runner), XS)["price"] = round(best * 1.05, 2)

        def nothing_prunable(fs):
            for f in fs:
                if f["parent_sku"] != winner:
                    min((v for v in f["variants"] if v["qty"]), key=lambda v: v["price"])["price"] = 1.0

        def only_the_winner_to_open(fs):
            for f in fs:
                if f["parent_sku"] != winner:
                    for v in f["variants"]:
                        v["price"] += 500

        def sold_out_xs_dearer(fs):
            for f in fs:
                xs = next((v for v in f["variants"] if v["option"] == XS), None)
                if xs is not None and xs["qty"] == 0:
                    xs["price"] += 100

        def answer_on_a_card(fs):
            other = next(f for f in fs if f["parent_sku"] not in (winner,) and
                         price(f, XS) is None)
            min((v for v in other["variants"] if v["qty"]), key=lambda v: v["price"])["price"] = best

        def answer_on_its_own_card(fs):
            for v in by_sku(fs, winner)["variants"]:
                if v["option"] != XS:
                    v["price"] = round(best + 5, 2)

        plants = {"xs_unique_winner": tie, "xs_clear_margin": close, "xs_bound_is_useful": nothing_prunable,
                  "xs_bound_not_sufficient": only_the_winner_to_open, "xs_sold_out_trap": sold_out_xs_dearer,
                  "xs_answer_not_on_cards": answer_on_a_card}
        for rule, plant in plants.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, self.broken(plant))
        with self.subTest(rule="xs_answer_not_on_cards, its own card"):
            self.assertIn("xs_answer_not_on_cards", self.broken(answer_on_its_own_card))

    def promo(self, families: list[dict]) -> list[tuple[dict, dict]]:
        return aplus.labelled(families, "promo")

    def test_each_promo_rule_fires_on_its_fault(self):
        k = self.k
        best = price(k["xs_winner"], XS)

        def within_margin(fs):
            f, v = self.promo(fs)[-1]
            v["label_price"] = round(v["price"] * 0.95, 2)
            v["label"] = aplus.B_PROMO_LABEL.format(size=XS, promo=v["label_price"])

        def a_market_price(fs):
            f, v = self.promo(fs)[-1]
            other = next(g for g in fs if g is not f)
            v["label_price"] = other["variants"][0]["price"]
            v["label"] = aplus.B_PROMO_LABEL.format(size=XS, promo=v["label_price"])

        def a_card_price(fs):
            f, v = self.promo(fs)[-1]
            dearest = max(fs, key=apparel.from_price)
            v["label_price"] = apparel.from_price(dearest)
            v["label"] = aplus.B_PROMO_LABEL.format(size=XS, promo=v["label_price"])

        def on_s(fs):
            f = next(g for g in fs if variant(g, "S") if "S" in [v["option"] for v in g["variants"]])
            s = variant(f, "S")
            s.update(label=aplus.B_PROMO_LABEL.format(size="S", promo=round(s["price"] * 0.8, 2)),
                     label_kind="promo", label_price=round(s["price"] * 0.8, 2))

        def promo_text_on_m(fs):
            f, v = aplus.labelled(fs, "scarcity")[0]
            v["label"] = "M - Promo today"

        def two_labels(fs):
            for f, v in self.promo(fs)[2:]:
                for field in ("label", "label_kind", "label_price"):
                    del v[field]

        def trap_not_below_the_winner(fs):
            for f, v in self.promo(fs):
                v["label_price"] = round(best * 0.95, 2) + 0.01 * fs.index(f)
                v["label"] = aplus.B_PROMO_LABEL.format(size=XS, promo=v["label_price"])

        def trap_sold_out(fs):
            f, v = aplus.keys_b(fs)["promo"][0]
            v["qty"] = 0

        def trap_is_the_winner(fs):
            w = by_sku(fs, k["xs_winner"]["parent_sku"])
            variant(w, XS).update(label=aplus.B_PROMO_LABEL.format(size=XS, promo=1.01), label_kind="promo",
                                  label_price=1.01)

        def trap_figure_twice(fs):
            promo = aplus.keys_b(fs)["promo"]
            (_, first), (_, second) = promo[0], promo[1]
            second["label_price"] = first["label_price"]
            second["label"] = first["label"]

        plants = {
            "promo_labels_false, within 8 per cent": ("promo_labels_false", within_margin),
            "promo_labels_false, a variant price": ("promo_labels_false", a_market_price),
            "promo_labels_false, a card price": ("promo_labels_false", a_card_price),
            "promo_xs_only, a promo label on S": ("promo_xs_only", on_s),
            "promo_xs_only, promo text on M": ("promo_xs_only", promo_text_on_m),
            "promo_population": ("promo_population", two_labels),
            "promo_trap, not below the winner": ("promo_trap", trap_not_below_the_winner),
            "promo_trap, its XS sold out": ("promo_trap", trap_sold_out),
            "promo_trap, on the winner": ("promo_trap", trap_is_the_winner),
            "promo_trap, the figure twice": ("promo_trap", trap_figure_twice),
        }
        for label, (rule, plant) in plants.items():
            with self.subTest(fault=label):
                self.assertIn(rule, self.broken(plant))

    def test_the_named_listings_rules_each_clause(self):
        # `promo_check_passes` on the fixture's own named listing, then with one clause broken.
        named = by_sku(self.families, self.fixture["_instance"]["promo_check"]["sku"])
        self.assertTrue(aplus.promo_check_passes(named))
        xs = variant(named, XS)
        for label, change in (
                ("XS sold out", lambda l: variant(l, XS).update(qty=0)),
                ("no promo label", lambda l: variant(l, XS).pop("label_kind")),
                ("figure above 0.92 of the real price",
                 lambda l: variant(l, XS).update(label_price=round(xs["price"] * 0.95, 2))),
                ("card not below the figure",
                 lambda l: [v.update(price=xs["price"] + 50) for v in l["variants"] if v["option"] != XS]),
                ("real XS price equal to another size",
                 lambda l: next(v for v in l["variants"] if v["option"] != XS).update(price=xs["price"]))):
            with self.subTest(clause=label):
                listing = copy.deepcopy(named)
                change(listing)
                self.assertFalse(aplus.promo_check_passes(listing))
        # The named listing is the first passing one in the predicted order, and the fixture's.
        order = self.fixture["_instance"]["predicted_order"]
        self.assertEqual(aplus.promo_check_named(self.families, order)["parent_sku"], named["parent_sku"])
        self.assertEqual(self.fixture["_instance"]["promo_check"]["promo"], xs["label_price"])
        self.assertEqual(self.fixture["_instance"]["promo_check"]["price"], xs["price"])
        self.assertLess(apparel.from_price(named), xs["label_price"])
        self.assertLessEqual(xs["label_price"], xs["price"] * 0.92 + 0.005)

    def test_promo_check_choice_fires_when_no_listing_passes_or_the_scenarios_disagree(self):
        def none_pass(fs):
            for f, v in self.promo(fs):
                for other in f["variants"]:
                    if other["option"] != XS:
                        other["price"] = v["price"] + 50
        self.assertIn("promo_check_choice", self.broken(none_pass, self.two_forms))
        self.assertNotIn("promo_check_choice", self.broken(none_pass, None))   # not asked without the form
        order = self.fixture["_instance"]["predicted_order"]
        self.assertIn("promo_check_choice", aplus.page_problems_b(copy.deepcopy(self.families), order)
                      if none_pass(fs := copy.deepcopy(self.families)) or True else [])
        self.assertIn("promo_check_choice", aplus.page_problems_b(fs, order))
        # Two scenarios whose first passing listing differs: the reversed order puts another first.
        passing = [s for s in order if aplus.promo_check_passes(by_sku(self.families, s))]
        if len(passing) > 1:
            with mock.patch.object(aplus, "predicted_orders", return_value={"a": order, "b": order[::-1]}):
                self.assertIn("promo_check_choice", aplus.b_rules(self.families, self.k, self.two_forms))
        with mock.patch.object(aplus, "predicted_orders", return_value={"a": order, "b": order}):
            self.assertNotIn("promo_check_choice", aplus.b_rules(self.families, self.k, self.two_forms))

    def test_scarcity_labels_fires_on_each_fault(self):
        def on_sold_out(fs):
            f, v = aplus.labelled(fs, "scarcity")[0]
            v["qty"] = 0

        def figure_is_the_quantity(fs):
            f, v = aplus.labelled(fs, "scarcity")[0]
            v["qty"] = int(v["label"].split("Only ")[1].split()[0])

        def smallest_twice(fs):
            labels = aplus.labelled(fs, "scarcity")
            smallest = min(labels, key=lambda fv: int(fv[1]["label"].split("Only ")[1].split()[0]))[1]["label"]
            for f, v in labels:
                v["label"] = smallest

        def one_label(fs):
            for f, v in aplus.labelled(fs, "scarcity")[1:]:
                del v["label"], v["label_kind"]

        for label, plant in (("on a sold-out M", on_sold_out), ("the figure is the quantity", figure_is_the_quantity),
                             ("the smallest figure twice", smallest_twice), ("one label", one_label)):
            with self.subTest(fault=label):
                self.assertIn("scarcity_labels", self.broken(plant))
        # The shop's quantities start at 12, so no figure of 1 to 3 is ever a real quantity.
        self.assertTrue(all(v["qty"] >= 12 for f in self.families for v in f["variants"] if v["qty"]))

    def test_labels_hold_fires_on_each_fault(self):
        promo = self.promo(self.families)[0]
        scarcity = aplus.labelled(self.families, "scarcity")[0]
        faults = {
            "the label as the option": lambda fs: variant(by_sku(fs, promo[0]["parent_sku"]), XS).update(option=promo[1]["label"]),
            "a label not starting with its size": lambda fs: variant(by_sku(fs, promo[0]["parent_sku"]), XS).update(label="Promo $9.99 - XS"),
            "a kind without a label": lambda fs: variant(by_sku(fs, promo[0]["parent_sku"]), XS).pop("label"),
            "an unknown kind": lambda fs: variant(by_sku(fs, promo[0]["parent_sku"]), XS).update(label_kind="bestseller"),
            "a promo label whose figure is not its label_price": lambda fs: variant(by_sku(fs, promo[0]["parent_sku"]), XS).update(label_price=1.11),
            "a scarcity label with a price": lambda fs: variant(by_sku(fs, scarcity[0]["parent_sku"]), M).update(label_price=2.0),
            "a description": lambda fs: fs[0].update(description="Runs small; consider a size up."),
            "a menu out of size order": lambda fs: fs[0]["variants"].reverse(),
        }
        for label, plant in faults.items():
            with self.subTest(fault=label):
                families = copy.deepcopy(self.families)
                plant(families)
                self.assertTrue(aplus.label_problems(families), label)
                self.assertIn("labels_hold", aplus.market_check_b(families, self.brand, aplus.VERSION))

    def test_no_fit_text_fires_on_a_title_or_label(self):
        for label, plant in (("a title", lambda fs: fs[0].update(name=fs[0]["name"].replace(" Tee", " Slim Fit Tee"))),
                             ("a label", lambda fs: aplus.labelled(fs, "scarcity")[0][1].update(label="M - Runs small"))):
            with self.subTest(where=label):
                families = copy.deepcopy(self.families)
                plant(families)
                self.assertTrue(aplus.fit_text_problems(families))
                self.assertIn("no_fit_text", aplus.market_check_b(families, self.brand, aplus.VERSION))

    def test_names_distinct_reads_the_labels_and_the_new_templates(self):
        for seller, words in (("Promo Outfitters", "inside a text the scorer reads"),      # a label's word
                              ("Medium Apparel", "inside a text the scorer reads"),        # decline-fit's word
                              ("Fewest Threads", "inside a text the scorer reads")):       # decline-scarcity's word
            with self.subTest(seller=seller):
                families = copy.deepcopy(self.families)
                families[0]["seller"] = seller
                self.assertIn(words, "; ".join(aplus.name_problems(families, self.brand, aplus.DESIGN_B)))
                self.assertIn("names_distinct", aplus.market_check_b(families, self.brand, aplus.VERSION))
        self.assertEqual(aplus.name_problems(self.families, self.brand, aplus.DESIGN_B), [])
        # The pools: 52 first words, each in no label, size, phrasing, template or other name.
        firsts = [w.lower() for w in aplus.B_FIRST]
        self.assertEqual((len(firsts), len(set(firsts))), (52, 52))
        texts = aplus.words_a_scorer_reads_b(self.brand, self.families) + [s.lower() for s in aplus.B_SECOND]
        for first in firsts:
            with self.subTest(first=first):
                self.assertFalse([t for t in texts if first in t])

    def test_the_kept_a_plus_tee_rules_fire(self):
        k = self.k

        def no_sold_out_m(fs):
            for f in fs:
                for v in f["variants"]:
                    if v["option"] == M and v["qty"] == 0:
                        v["qty"] = 10

        def tied_headline(fs):
            cards = sorted(fs, key=apparel.from_price)
            min((v for v in cards[1]["variants"] if v["qty"]), key=lambda v: v["price"])["price"] = apparel.from_price(cards[0])

        def fourth_ties_third(fs):
            variant(by_sku(fs, k["top_next"]["parent_sku"]), M)["price"] = price(k["top"][-1], M)

        def fourth_close(fs):
            variant(by_sku(fs, k["top_next"]["parent_sku"]), M)["price"] = round(price(k["top"][-1], M) * 1.04, 2)

        def too_few(fs):
            del fs[aplus.PAGE_SIZE:]

        for rule, plant in (("readings_differ", no_sold_out_m), ("headline_unique", tied_headline),
                            ("top_3_unique", fourth_ties_third), ("top_3_margin", fourth_close),
                            ("two_pages", too_few)):
            with self.subTest(rule=rule):
                self.assertIn(rule, self.broken(plant))

    def test_the_pre_check_never_rejects_a_draw_the_rules_accept(self):
        # `margins_hold` reads the margin and sold-out rules cheaply; a draw it rejects must fail
        # the full rules, and the development market passes it. Fires: the runner-up M at 5 per
        # cent, which the full rules refuse too.
        self.assertTrue(aplus.margins_hold(self.families))
        for attempt in range(300):
            rng = random.Random(f"test:{attempt}")
            names = aplus.seller_names(aplus.B_FIRST, aplus.B_SECOND, aplus.B_LISTINGS, rng)
            families = [aplus.build_tee_b(n, i, rng, self.brand, "IGR-TST", aplus.DEV_TEE_PHRASES)
                        for i, n in enumerate(names, 1)]
            if not aplus.margins_hold(families):
                aplus.add_labels(families, rng)
                self.assertTrue(apparel.check(families, apparel.measure(families, aplus.B_SIZES))
                                or aplus.market_check_b(families, self.brand, aplus.VERSION), attempt)
        families = copy.deepcopy(self.families)
        variant(by_sku(families, self.k["tee_runner_up"]["parent_sku"]), M)["price"] = round(price(self.k["tee_winner"], M) * 1.05, 2)
        self.assertFalse(aplus.margins_hold(families))
        self.assertIn("clear_margin", apparel.check(families, apparel.measure(families, aplus.B_SIZES)))

    def test_the_labels_are_drawn_after_the_prices(self):
        # A seed's prices and stock are what they would be without labels: the same draw with
        # add_labels left out has the same variants but for the label fields.
        generated = self.fixture["_generated"]
        rng = random.Random(f"{aplus.MARKET_B}:{generated['seed']}:tee:{generated['attempts']['tee']}")
        names = aplus.seller_names(aplus.B_FIRST, aplus.B_SECOND, len(self.families), rng)
        bare = [aplus.build_tee_b(n, i, rng, self.brand, generated["sku_prefix"], aplus.DEV_TEE_PHRASES)
                for i, n in enumerate(names, 1)]
        stripped = [[{k: v for k, v in var.items() if not k.startswith("label")} for var in f["variants"]]
                    for f in self.families]
        self.assertEqual([f["variants"] for f in bare], stripped)
        self.assertEqual([f["name"] for f in bare], [f["name"] for f in self.families])


@needs_market
class PageRules(DevMarket):
    def setUp(self):
        super().setUp()
        self.order = self.fixture["_instance"]["predicted_order"]

    def test_quiet_on_every_predicted_order_and_the_recorded_one(self):
        for label, order in aplus.predicted_orders(self.families, self.two_forms).items():
            with self.subTest(scenario=label):
                self.assertEqual(aplus.page_problems(self.families, order, aplus.DESIGN_B), [])
        self.assertEqual(self.order, aplus.predicted_orders(self.families, self.two_forms)[
            f"{'two forms' if self.two_forms else 'one form'}, average lengths x1.0"])
        self.assertEqual(self.order, load(DEV_SEARCH)["tried"][-1]["live_order"])
        cards = {q: [self.order.index(l["parent_sku"]) + 1 for l in ls]
                 for q, (ls, _) in aplus.answer_listings_b(self.k).items()}
        self.assertEqual(self.fixture["_instance"]["predicted_cards"], cards)
        self.assertIn("tee-xs-price", cards)
        self.assertNotIn("interleaved", aplus.B_PAGE_RULES)

    def moved(self, sku: str, to: int) -> list[str]:
        order = [s for s in self.order if s != sku]
        order.insert(to, sku)
        return aplus.page_problems_b(self.families, order)

    def test_first_screen_fires_when_an_answer_renders_on_it(self):
        broken = self.moved(self.k["xs_winner"]["parent_sku"], 0)
        self.assertIn("first_screen_misleads:tee-xs-price", broken)
        broken = self.moved(self.k["tee_winner"]["parent_sku"], 0)
        self.assertLessEqual({"tee-target-price", "tee-cheapest-target"},
                             {p.split(":")[1] for p in broken if p.startswith("first_screen")})

    def test_first_screen_fires_when_no_card_there_undercuts(self):
        families = copy.deepcopy(self.families)
        for sku in self.order[:aplus.FIRST_SCREEN]:
            for v in by_sku(families, sku)["variants"]:
                v["price"] += 300
        broken = aplus.page_problems_b(families, self.order)
        for question in aplus.B_PRICE_QUESTIONS:
            with self.subTest(question=question):
                self.assertIn(f"first_screen_misleads:{question}", broken)

    def test_answer_on_page_2_fires_when_page_2_holds_none(self):
        named = {l["parent_sku"] for listings, _ in aplus.answer_listings_b(self.k).values() for l in listings}
        self.assertTrue(named & set(self.order[aplus.PAGE_SIZE:]))
        keep = [s for s in self.order if s not in named]
        order = keep[:aplus.PAGE_SIZE - len(named)] + sorted(named) + keep[aplus.PAGE_SIZE - len(named):]
        self.assertIn("answer_on_page_2", aplus.page_problems_b(self.families, order))

    def test_counts_need_page_2_fires_for_each_count_and_reading(self):
        for question, reading, counted in aplus.B_COUNTED:
            with self.subTest(question=question, reading=reading):
                self.assertTrue(any(counted(by_sku(self.families, s)) for s in self.order[aplus.PAGE_SIZE:]))
                moved = [s for s in self.order if counted(by_sku(self.families, s))]
                order = moved + [s for s in self.order if s not in moved]
                self.assertIn(f"counts_need_page_2:{question} ({reading})", aplus.page_problems_b(self.families, order))

    def test_headline_on_page_1_fires_off_page_1_and_without_its_margin(self):
        headline = min(self.families, key=apparel.from_price)["parent_sku"]
        self.assertNotIn(headline, self.order[aplus.PAGE_SIZE:])
        self.assertIn("headline_on_page_1", self.moved(headline, len(self.order) - 1))
        families = copy.deepcopy(self.families)
        later = by_sku(families, self.order[aplus.PAGE_SIZE])
        low = min((v for v in later["variants"] if v["qty"]), key=lambda v: v["price"])
        low["price"] = round(apparel.from_price(by_sku(families, headline)) * 1.04, 2)
        self.assertIn("headline_on_page_1", aplus.page_problems_b(families, self.order))

    def test_an_order_of_other_listings_is_refused(self):
        self.assertEqual(aplus.page_problems_b(self.families, self.order[1:]), ["the order is not this market's listings"])


class OrderModel(unittest.TestCase):
    """A label's words count in a child's name; a family without labels counts as it did."""

    def test_a_label_lengthens_the_name_as_the_index_holds_it(self):
        tee = aplus.products(load(LARCHMERE)["families"])[aplus.TEE][0]
        freq, name, search = search_order.lengths(tee)
        labelled = copy.deepcopy(tee)
        labelled["variants"][0]["label"] = f"{labelled['variants'][0]['option']} - Promo $9.99"
        self.assertEqual(search_order.lengths(labelled), (freq, name + 2, search + 2))
        labelled["variants"][1]["label"] = f"{labelled['variants'][1]['option']} - Only 2 left!"
        self.assertEqual(search_order.lengths(labelled), (freq, name + 5, search + 5))
        self.assertEqual(search_order.menu_label(labelled["variants"][0]), f"{tee['variants'][0]['option']} - Promo $9.99")
        self.assertEqual(search_order.menu_label(tee["variants"][0]), tee["variants"][0]["option"])
        # The child's SKU keeps the plain option.
        self.assertEqual(search_order.child_sku(labelled, labelled["variants"][0]),
                         f"{tee['parent_sku']}-{tee['variants'][0]['option']}")
        # Thornwood's IGR-APP-02, as before: name 34, _search 59.
        listing = by_sku(load(paths.FIXTURES / "scaled_apparel.json")["families"], "IGR-APP-02")
        self.assertEqual(search_order.lengths(listing), (5, 34, 59))

    @needs_market
    def test_a_labelled_listing_renders_later_than_its_unlabelled_twin(self):
        families = load(DEV)["families"]
        labelled = next(f for f in families if any(v.get("label") for v in f["variants"]))
        twin = copy.deepcopy(labelled)
        for v in twin["variants"]:
            v.pop("label", None)
        self.assertLess(search_order.score(labelled, True), search_order.score(twin, True))


class Seeder(unittest.TestCase):
    """The seeder writes each label as an option at its size's position, and into its child's
    name, without a shop: a fake Magento records what it would post."""

    class FakeMagento:
        def __init__(self):
            self.options = {"tee_size": [{"label": "", "value": "0"}]}
            self.posts = []
            self.base_url = "http://fake"

        def attribute(self, code):
            return {"attribute_code": code, "attribute_id": 7, "default_frontend_label": "Size"}

        def get(self, path):
            code = path.split("/")[3]
            return self.options[code]

        def post(self, path, body):
            self.posts.append((path, body))
            if path.endswith("/options"):
                code = path.split("/")[3]
                option = body["option"]
                self.options[code].append({"label": option["label"], "value": str(len(self.options[code]))})
                return {}
            return {"id": 1}

        def product(self, sku):
            return None

        def attribute_set_groups(self, set_id):
            return [{"attribute_group_name": "Product Details", "attribute_group_id": "7"}]

    @needs_market
    def test_label_options_at_their_sizes_position_and_in_the_childs_name(self):
        fixture = load(DEV)
        m = self.FakeMagento()
        seed_variants._option_cache.clear()
        spec = fixture["attributes"][0]
        self.assertEqual((spec["code"], spec["options"]), (aplus.B_ATTRIBUTE, list(aplus.B_SIZES)))
        seed_variants.ensure_attribute(m, spec)
        posted = {b["option"]["label"]: b["option"]["sort_order"] for p, b in m.posts if p.endswith("/options")}
        self.assertEqual([posted[s] for s in aplus.B_SIZES], list(range(6)))
        for label, size in spec["labels"].items():
            with self.subTest(label=label):
                self.assertEqual(posted[label], aplus.B_SIZES.index(size))
        # Every label of the market is an option, and every option of the labels is a label.
        labels = {v["label"] for f in fixture["families"] for v in f["variants"] if v.get("label")}
        self.assertEqual(set(spec["labels"]), labels)
        # A child takes its label as its attribute value and its name; its SKU the plain size.
        family = next(f for f in fixture["families"] if any(v.get("label") for v in f["variants"]))
        family = seed_variants.expand_skus({"families": [copy.deepcopy(family)]})["families"][0]
        labelled = next(v for v in family["variants"] if v.get("label"))
        index = seed_variants.option_index(m, "tee_size", refresh=True)
        seed_variants.ensure_child(m, family, labelled, index[labelled["label"]], fixture)
        body = m.posts[-1][1]["product"]
        self.assertEqual(body["name"], f"{family['name']} - {labelled['label']}")
        self.assertEqual(body["sku"], f"{family['parent_sku']}-{labelled['option']}")
        self.assertEqual(body["custom_attributes"][0], {"attribute_code": "tee_size", "value": index[labelled["label"]]})
        self.assertEqual(seed_variants.menu_label(labelled), labelled["label"])
        plain = next(v for v in family["variants"] if not v.get("label"))
        self.assertEqual(seed_variants.menu_label(plain), plain["option"])
        self.assertEqual(search_order.menu_label(labelled), seed_variants.menu_label(labelled))

    def test_a_fixture_without_labels_seeds_as_before(self):
        fixture = load(LARCHMERE)
        m = self.FakeMagento()
        m.options["apparel_size"] = [{"label": "", "value": "0"}]
        seed_variants._option_cache.clear()
        seed_variants.ensure_attribute(m, fixture["attributes"][0])
        self.assertEqual([b["option"]["label"] for p, b in m.posts if p.endswith("/options")], ["S", "M", "L", "XL"])


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.final = pathlib.Path(self.tmp.name) / "claim2-protocol.md"
        self.final.write_text("# The second claim run, protocol (FINAL)\n")
        self.claim_out = pathlib.Path(self.tmp.name) / "claim2_tee.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_design_b_never_uses_larchmeres_prefix_or_fixture(self):
        B = aplus.DESIGN_B
        self.assertIn("A+ development market's prefix", aplus.refused(900, False, DEV, "IGR-DEV", design=B))
        self.assertIn("A+ development market's fixture", aplus.refused(900, False, LARCHMERE, "IGR-TDV", design=B))
        self.assertIsNone(aplus.refused(900, False, DEV, "IGR-TDV", design=B))
        self.assertIn("outside development", aplus.refused(1000, False, DEV, "IGR-TDV", design=B))
        # Design A as before: Larchmere's own prefix and fixture are development's.
        self.assertIsNone(aplus.refused(900, False, LARCHMERE, "IGR-DEV"))

    def test_the_design_b_claim_refuses_its_development_market_and_the_draft(self):
        B = aplus.DESIGN_B
        self.assertIn("still says DRAFT", aplus.refused(1000, True, self.claim_out, "IGR-CL2", design=B))
        self.assertTrue("DRAFT" in aplus.PROTOCOL.read_text())
        self.assertIn("development's prefix", aplus.refused(1000, True, self.claim_out, "IGR-TDV", self.final, B))
        self.assertIn("development's fixture", aplus.refused(1000, True, DEV, "IGR-CL2", self.final, B))
        self.assertIsNone(aplus.refused(1000, True, self.claim_out, "IGR-CL2", self.final, B))
        self.assertIn("below 1000", aplus.refused(999, True, self.claim_out, "IGR-CL2", self.final, B))

    def test_the_command_line_refuses_before_drawing(self):
        for args, words in ((["--seed", "1000", "--claim", "--report"], "still says DRAFT"),
                            (["--seed", "900", "--sku-prefix", "IGR-DEV", "--report"], "A+ development market's prefix"),
                            (["--seed", "1000", "--report"], "outside development")):
            with self.subTest(args=args):
                run = subprocess.run([sys.executable, "env/generate_aplus.py", "--brand", "Quenby", "--brand-forms", "2",
                                      "--design", "B", *(args if "--sku-prefix" in args else ["--sku-prefix", "IGR-CL2", *args])],
                                     cwd=paths.REPO, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn(words, run.stderr)
                self.assertEqual(run.stdout, "")

    @needs_market
    def test_the_picker_passes_the_design(self):
        market = picker.Market(fixture=DEV, brand="Thurlby", sku_prefix="IGR-TDV", two_forms=True, design=aplus.DESIGN_B)
        command = picker.generate_command(900, market)
        self.assertEqual(command[command.index("--design") + 1], "B")
        self.assertEqual(command[command.index("--listings") + 1], str(aplus.B_LISTINGS))
        self.assertNotIn("--tees", command)
        self.assertNotIn("--waters", command)
        a_plus = picker.generate_command(900, picker.Market(fixture=LARCHMERE, brand="Larchmere", sku_prefix="IGR-DEV", two_forms=True))
        self.assertNotIn("--design", a_plus)
        self.assertIn("--tees", a_plus)
        self.assertIsNone(picker.prefix_refused("IGR-TDV"))
        self.assertIsNone(picker.teardown_refused(market, load(DEV)))
        self.assertIn("not Thurlby", picker.teardown_refused(
            picker.Market(fixture=DEV, brand="Thurlby", sku_prefix="IGR-TDV", design=aplus.DESIGN_B), load(LARCHMERE)))


@needs_market
class Files(unittest.TestCase):
    """The committed fixture is what the generator writes, byte for byte, and records its design."""

    def test_the_fixture_regenerates(self):
        generated = load(DEV)["_generated"]
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / DEV.name
            subprocess.run([sys.executable, "env/generate_aplus.py", "--seed", str(generated["seed"]),
                            "--brand", generated["brand"], "--brand-forms", str(generated["brand_forms"]),
                            "--sku-prefix", generated["sku_prefix"], "--design", "B", "--listings",
                            str(generated["listings"]["tee"]), "--out", str(out),
                            "--search-log", str(DEV_SEARCH.relative_to(paths.REPO))],
                           cwd=paths.REPO, check=True, capture_output=True, timeout=3600)
            self.assertEqual(out.read_bytes(), DEV.read_bytes())
        self.assertEqual(generated["search"], load(DEV_SEARCH))

    def test_the_fixture_records_its_design_and_the_search_its_versions(self):
        fixture = load(DEV)
        generated = fixture["_generated"]
        self.assertEqual((generated["design"], generated["version"] >= 4, generated["sizes"]), ("B", True, list(aplus.B_SIZES)))
        self.assertNotEqual(generated["sku_prefix"], "IGR-DEV")
        self.assertNotIn(generated["brand"], ("Larchmere", "Thornwood", "Ashcombe", "Calderwood", "Rivenhall", "Wexcombe",
                                              "Penhallow", "Tarnbrook", "Quillfield", "Brackwater"))
        self.assertIn(generated["seed"], aplus.DEV_SEEDS)
        self.assertEqual(fixture["_instance"]["design"], "B")
        self.assertNotIn("water", fixture["_instance"])
        self.assertEqual(generated["listings"], {"tee": len(fixture["families"])})
        last = load(DEV_SEARCH)["tried"][-1]
        self.assertEqual((last["outcome"], last["seed"], last["generator_version"], last["design"]),
                         ("accepted", generated["seed"], generated["version"], "B"))
        self.assertTrue(all(t["seed"] in aplus.DEV_SEEDS for t in load(DEV_SEARCH)["tried"]))
        self.assertEqual(aplus.drawn_under(DEV_SEARCH, generated["seed"]), generated["version"])
        # Larchmere is still drawn under version 2, and still passes its own version's rules.
        larchmere = load(LARCHMERE)
        self.assertEqual(aplus.drawn_under(paths.REPO / "env" / "manifests" / "aplus_dev-search.json", 900), 2)
        self.assertEqual(aplus.check(larchmere["families"], "Larchmere", True, 2), [])

    def test_the_instance_is_the_variants(self):
        fixture = load(DEV)
        families = fixture["families"]
        inst = fixture["_instance"]
        self.assertEqual(inst["tee"], apparel.measure(families, aplus.B_SIZES))
        self.assertEqual(inst["xs"], aplus.xs_measure(families))
        k = aplus.keys_b(families)
        self.assertEqual(inst["labels"]["lowest_promo"]["sku"], k["promo_trap"]["parent_sku"])
        self.assertEqual(inst["labels"]["lowest_promo"]["label_price"], k["promo_trap_figure"])
        self.assertEqual(len(inst["labels"]["promo"]), len(k["promo"]))
        self.assertEqual(len(inst["labels"]["scarcity"]), len(k["scarcity"]))
        self.assertTrue(inst["xs"]["sold_out_trap"])
        self.assertFalse(inst["xs"]["answer_on_a_card"])
        self.assertEqual(inst["exists_limit"], k["limit"])


@needs_market
class LiveCheckComparisons(DevMarket):
    """`check_aplus_market.py`'s design-B lines, on the fixture's own menus and planted faults."""

    def menus(self) -> dict:
        return {f["parent_sku"].lower(): [{"label": v.get("label") or v["option"], "buyable": v["qty"] > 0, "price": None}
                                          for v in f["variants"]] for f in self.families}

    def texts(self) -> dict:
        return {f["parent_sku"].lower(): {theme: " ".join([v.get("label") or v["option"] for v in f["variants"]]
                                                           + [live.REVIEWS_EMPTY]) for theme in ("plain", "gated")}
                for f in self.families}

    def test_quiet_on_the_fixtures_own_menus(self):
        lines = live.label_lines(self.fixture, self.menus(), self.texts())
        self.assertEqual([ok for ok, _ in lines], [True] * 4, lines)
        promo, scarcity = len(self.k["promo"]), len(self.k["scarcity"])
        self.assertIn(f"{promo} promo and {scarcity} scarcity", lines[0][1])

    def test_each_planted_fault_fires_its_line(self):
        key = self.k["promo"][0][0]["parent_sku"].lower()
        label = self.k["promo"][0][1]["label"]
        a_price = check_market.money(self.families[0]["variants"][0]["price"])
        faults = {
            "a label not as seeded": (0, lambda m, t: m[key].__setitem__(0, {**m[key][0], "label": "XS"}) if m[key][0]["label"] == label
                                      else [e.update(label="XS") for e in m[key] if e["label"] == label]),
            "a label holding a market price": (0, lambda m, t: [e.update(label=f"XS - Promo ${a_price}") for e in m[key] if e["label"] == label]),
            "a menu out of size order": (1, lambda m, t: m[key].reverse()),
            "a stock count rendered": (2, lambda m, t: t[key].update(gated=t[key]["gated"] + " Only 5 left")),
            "the reviews tab not empty": (3, lambda m, t: t[key].update(plain=t[key]["plain"].replace(live.REVIEWS_EMPTY, "1 Review"))),
        }
        for name, (line, plant) in faults.items():
            with self.subTest(fault=name):
                menus, texts = self.menus(), self.texts()
                plant(menus, texts)
                lines = live.label_lines(self.fixture, menus, texts)
                self.assertFalse(lines[line][0], lines[line][1])
                others = [ok for i, (ok, _) in enumerate(lines) if i != line]
                self.assertTrue(all(others), name)
        # Quiet: a seeded scarcity label is the one "Only N left" a page may show.
        menus, texts = self.menus(), self.texts()
        self.assertTrue(live.label_lines(self.fixture, menus, texts)[2][0])

    def test_the_order_lines_name_the_promo_check_listing(self):
        order = self.fixture["_instance"]["predicted_order"]
        lines = live.order_lines(self.fixture, order)
        self.assertEqual([ok for ok, _ in lines], [True] * 5, lines)
        self.assertIn(self.fixture["_instance"]["promo_check"]["sku"], lines[4][1])
        self.assertIn("promo_check_choice", lines[3][1])
        # A live order in which no listing passes first: the fixture's named listing moved last
        # behind one that does not pass changes nothing; one that passes moved before it fires.
        passing = [s for s in order if aplus.promo_check_passes(by_sku(self.families, s))]
        if len(passing) > 1:
            swapped = [s for s in order if s != passing[1]]
            swapped.insert(0, passing[1])
            self.assertFalse(live.order_lines(self.fixture, swapped)[4][0])
        # The fixture read with another design's rules would not know the line.
        a_plus = load(LARCHMERE)
        self.assertEqual(len(live.order_lines(a_plus, a_plus["_instance"]["predicted_order"])), 4)

    def test_expected_names_a_size_as_the_menu_shows_it(self):
        listings = check_market.expected(self.fixture)
        labelled = next(l for l, f in zip(listings, self.families) if any(v.get("label") for v in f["variants"]))
        self.assertTrue(any(" - " in size for size, _, _ in labelled["sizes"]))
        # The plain theme's label with its surcharge is read whole, the surcharge apart.
        menu = check_market.plain_menu([{"text": "XS - Promo $9.99 +$2.30", "disabled": False, "value": "1"},
                                        {"text": "M - Only 2 left! -$1.05", "disabled": True, "value": "2"},
                                        {"text": "XXL", "disabled": False, "value": "3"}], None, 10.00)
        self.assertEqual([(e["label"], e["label_price"], e["buyable"]) for e in menu],
                         [("XS - Promo $9.99", 12.30, True), ("M - Only 2 left!", 8.95, False), ("XXL", 10.00, True)])
        # A promo figure is not a leak of the listing's prices, since no label holds one.
        listing = {"advertised": 10.00, "sizes": [("XS - Promo $9.99", 12.30, True), ("M", 10.00, True)]}
        self.assertEqual(check_market.leaked("Size XS - Promo $9.99", listing), [])
        self.assertEqual(check_market.leaked("Size XS - Promo $9.99 $12.30", listing), ["12.30"])
        # Larchmere's sizes read as before.
        self.assertEqual(check_market.expected(load(LARCHMERE))[0]["sizes"][0][0], load(LARCHMERE)["families"][0]["variants"][0]["option"])


if __name__ == "__main__":
    unittest.main()
