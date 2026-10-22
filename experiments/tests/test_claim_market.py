"""The claim market of 20 October 2026: drawn under its own brand, prefix and URL keys by the
generator and the picker, its questions written from its own fixture, and checked live.

Nothing here touches the shop: the picker's page rule and the live checker's comparisons are
tested on fixtures and planted readings, and every rule is shown firing on a known fault and
staying quiet on the correct case (LESSONS 24, 31).
"""
import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import box  # noqa: E402
import compare_cells  # noqa: E402
import page  # noqa: E402
import score  # noqa: E402
import sufficiency  # noqa: E402
import suite  # noqa: E402
import verify_cells  # noqa: E402

sys.path.insert(0, str(paths.REPO / "env"))
import check_market  # noqa: E402
import generate_apparel as apparel  # noqa: E402
import generate_apparel_v2_tasks as v2  # noqa: E402
import pick_apparel_market as pick  # noqa: E402

THORNWOOD = paths.FIXTURES / "scaled_apparel.json"
CLAIM = paths.FIXTURES / "claim_apparel.json"
CLAIM_TASKS = paths.TASKS / "tasks_claim_apparel.json"
CLAIM_READINGS = paths.TASKS / "readings_claim_apparel.json"
SEARCH_LOG = paths.REPO / "env" / "manifests" / "claim_apparel-search.json"
# The protocol's brand list, in its order (docs/content/claim-protocol.md, "Brand rule").
BRANDS = ("Ashcombe", "Hartwell", "Wyndham")


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def listing(seller: str, sizes: list[tuple[str, float, int]], sku: str = "IGR-TST-01") -> dict:
    return {"parent_sku": sku, "seller": seller, "name": f"Test Heavyweight Cotton Tee - {seller}",
            "variants": [{"option": o, "price": p, "qty": q, "units": 1} for o, p, q in sizes]}


class PageRule(unittest.TestCase):
    """The page rule reads what a card advertises: the cheapest size that can be bought.
    Until 20 October 2026 it took the cheapest of every size, sold out included (verifier's
    logic audit)."""

    def market(self) -> tuple[dict, list[str]]:
        # The answer costs $17.00. In the first row, a listing shaped like Thornwood's
        # igr-app-07: S and M sold out at $16.22 and $15.04, so its card shows $18.33.
        fairhaven = listing("Fairhaven Workwear", [("S", 16.22, 0), ("M", 15.04, 0),
                                                   ("L", 18.33, 64), ("XL", 18.58, 108)])
        dearer = listing("Dearer Supply", [("S", 21.00, 5), ("M", 22.00, 5)], "IGR-TST-02")
        cheaper = listing("Cheaper Threads", [("S", 16.50, 5), ("L", 30.00, 5)], "IGR-TST-03")
        answer = listing("Answer Apparel", [("M", 17.00, 5)], "IGR-TST-04")
        fixture = {"_instance": {"winner": {"seller": "Answer Apparel", "price": 17.00}},
                   "families": [fairhaven, dearer, cheaper, answer]}
        return fixture, ["Fairhaven Workwear", "Dearer Supply", "Cheaper Threads",
                         "Other Seller", "Answer Apparel"]

    def test_a_sold_out_size_below_the_answer_does_not_mislead(self):
        fixture, order = self.market()
        # Quiet on the corrected reading: the card shows $18.33, above the answer.
        self.assertEqual(pick.first_row_misleads(fixture, order), ["Cheaper Threads"])
        # The reading before 20 October counted it, through its sold-out M at $15.04, which
        # is the fault this test is here to catch.
        every_size = {f["seller"]: min(v["price"] for v in f["variants"])
                      for f in fixture["families"]}
        self.assertEqual(pick.first_row_misleads(fixture, order, every_size),
                         ["Fairhaven Workwear", "Cheaper Threads"])
        self.assertEqual(pick.card_prices(fixture)["Fairhaven Workwear"], 18.33)

    def test_the_live_card_price_decides_when_given(self):
        fixture, order = self.market()
        self.assertEqual(pick.first_row_misleads(fixture, order, {"Dearer Supply": 16.99}),
                         ["Dearer Supply"])

    def test_usable_needs_the_answer_off_the_first_row_and_a_misleading_card(self):
        self.assertTrue(pick.usable(5, ["X"]))
        self.assertFalse(pick.usable(4, ["X"]))
        self.assertFalse(pick.usable(9, []))
        self.assertFalse(pick.usable(None, ["X"]))

    def test_on_thornwood_both_readings_name_the_same_three(self):
        # Thornwood's first row as its stored page record lists it (20261014T213118).
        fixture = load(THORNWOOD)
        order = ["Copperfield Apparel", "Dunmore Apparel", "Marchmont Textiles",
                 "Fairhaven Workwear"]
        every_size = {f["seller"]: min(v["price"] for v in f["variants"])
                      for f in fixture["families"]}
        self.assertEqual(pick.first_row_misleads(fixture, order),
                         ["Copperfield Apparel", "Dunmore Apparel", "Fairhaven Workwear"])
        self.assertEqual(pick.first_row_misleads(fixture, order),
                         pick.first_row_misleads(fixture, order, every_size))

    def test_the_skus_the_seeder_writes(self):
        fixture = load(THORNWOOD)
        skus = pick.fixture_skus(fixture)
        self.assertEqual(len(skus), 15 + sum(len(f["variants"]) for f in fixture["families"]))
        self.assertIn("IGR-APP-07-M", skus)
        self.assertEqual(pick.listing_url(fixture["families"][6]),
                         "http://localhost:7770/igr-app-07.html")

    def test_thornwood_is_never_torn_down_unasked(self):
        # Asked of the guard alone, so a broken guard can never delete anything here.
        thornwood = load(THORNWOOD)
        self.assertIn("Thornwood's", pick.teardown_refused(pick.Market(), thornwood))
        self.assertIsNone(pick.teardown_refused(pick.Market(replace_thornwood=True), thornwood))
        # Nor a fixture whose listings are not the market's own prefix, asked or not.
        self.assertIn("not all IGR-CLM", pick.teardown_refused(
            pick.Market(sku_prefix="IGR-CLM", replace_thornwood=True), thornwood))
        claim = pick.Market(fixture=paths.FIXTURES / "claim_apparel.json", sku_prefix="IGR-CLM")
        candidate = {"families": [{"parent_sku": "IGR-CLM-01"}, {"parent_sku": "IGR-CLM-02"}]}
        self.assertIsNone(pick.teardown_refused(claim, candidate))

    def test_the_brand_must_be_no_seller_word(self):
        words = pick.seller_words()
        self.assertIn("kelsall", words)
        self.assertIn("outfitters", words)
        self.assertNotIn("ashcombe", words)


class Generator(unittest.TestCase):
    """Another brand and prefix change the names, SKUs and URL keys, and nothing else."""

    def test_a_seed_draws_the_same_market_under_any_brand(self):
        listings, facts, attempt = apparel.generate(15, 203)
        other, other_facts, other_attempt = apparel.generate(15, 203, brand="Ashcombe",
                                                             sku_prefix="IGR-CLM")
        self.assertEqual(attempt, other_attempt)
        for a, b in zip(listings, other):
            self.assertEqual((a["seller"], a["variants"]), (b["seller"], b["variants"]))
            self.assertEqual(b["name"], a["name"].replace("Thornwood", "Ashcombe"))
            self.assertEqual(b["parent_sku"], a["parent_sku"].replace("IGR-APP", "IGR-CLM"))

    def test_another_brand_never_writes_over_thornwood(self):
        # Asked of the guard alone, so a broken guard writes nothing here.
        tasks = paths.TASKS / "tasks_apparel.json"
        elsewhere = pathlib.Path(tempfile.gettempdir()) / "never-written.json"
        self.assertEqual(apparel.over_thornwood("Ashcombe", "IGR-CLM", apparel.DEFAULT_OUT, None),
                         ["scaled_apparel.json"])
        self.assertEqual(apparel.over_thornwood("Ashcombe", "IGR-CLM", elsewhere, tasks),
                         ["tasks_apparel.json"])
        self.assertEqual(apparel.over_thornwood("Ashcombe", "IGR-APP", elsewhere, None), [])
        # Thornwood's own regeneration writes its own files, as it always has.
        self.assertEqual(apparel.over_thornwood("Thornwood", "IGR-APP", apparel.DEFAULT_OUT, tasks), [])

    def test_a_searched_market_says_when_and_how_it_was_chosen(self):
        listings, facts, attempt = apparel.generate(15, 203, brand="Ashcombe",
                                                    sku_prefix="IGR-CLM")
        search = {"brand": "Ashcombe", "sku_prefix": "IGR-CLM", "seeded": "20 October 2026",
                  "page_rule": "Page rule: as stated.",
                  "tried": [{"seed": 203, "attempt": attempt, "outcome": "accepted",
                             "answer_card": 12, "summary": "seed 203: accepted"}]}
        fixture = apparel.to_fixture(listings, facts, 203, attempt, "Ashcombe", "IGR-CLM",
                                     search=search, command="python3 env/generate_apparel.py")
        self.assertEqual(fixture["_generated"]["sku_prefix"], "IGR-CLM")
        self.assertIn("  seed 203: accepted", fixture["_about"])
        spec = apparel.task_spec(fixture)
        environment = " ".join(spec["_environment"])
        self.assertIn("seeded on 20 October 2026", environment)
        self.assertIn("igr-clm-NN.html", environment)
        self.assertIn("rendered at card 12 of 15", environment)
        self.assertNotIn("18 September", environment)
        self.assertTrue(all("Ashcombe" in t["query"] for t in spec["tasks"]))
        # Thornwood's own lines are untouched.
        self.assertIn("Clothing, seeded 18 September 2026 alongside the water markets rather than",
                      apparel.task_spec(load(THORNWOOD))["_environment"])

    def test_a_search_record_must_end_with_this_seed_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "search.json"
            path.write_text(json.dumps({"brand": "Ashcombe", "sku_prefix": "IGR-CLM",
                                        "tried": [{"seed": 204, "outcome": "rejected"}]}))
            with self.assertRaises(SystemExit):
                apparel.load_search(path, 204, "Ashcombe", "IGR-CLM")
            path.write_text(json.dumps({"brand": "Hartwell", "sku_prefix": "IGR-CLM",
                                        "tried": [{"seed": 204, "outcome": "accepted"}]}))
            with self.assertRaises(SystemExit):
                apparel.load_search(path, 204, "Ashcombe", "IGR-CLM")


class FreshMarketQuestions(unittest.TestCase):
    """The v2 generator for a market with no pilot: its own six, the readings computed, the
    price limits by rule. Each rule reproduces Thornwood where Thornwood was set by hand."""

    def setUp(self):
        self.thornwood = load(THORNWOOD)

    def test_the_limit_rule_gives_thornwoods_limits(self):
        self.assertEqual(v2.price_limits(self.thornwood), (v2.LIMIT_YES, v2.LIMIT_NO))

    def test_the_limit_rule_fires_when_no_limit_separates_the_two_cheapest(self):
        # The two cheapest buyable M within a dollar of each other across a whole dollar:
        # 25.10 and 25.90 give a limit of 25, under which nobody sells it, so keys refuses.
        broken = copy.deepcopy(self.thornwood)
        runner = next(f for f in broken["families"] if f["parent_sku"] == "IGR-APP-01")
        next(v for v in runner["variants"] if v["option"] == "M")["price"] = 25.90
        winner = next(f for f in broken["families"] if f["parent_sku"] == "IGR-APP-14")
        next(v for v in winner["variants"] if v["option"] == "M")["price"] = 25.10
        broken["_instance"]["winner"]["price"] = 25.10
        self.assertEqual(v2.price_limits(broken), (25, 25))
        with self.assertRaises(SystemExit):
            v2.keys(broken, v2.price_limits(broken))

    def test_the_buyable_reading_computed_equals_thornwoods_hand_written_one(self):
        self.assertEqual(v2.buyable_reading(self.thornwood),
                         load(paths.TASKS / "readings_apparel.json")["readings"])
        # Fires when the variants and _instance disagree.
        broken = copy.deepcopy(self.thornwood)
        broken["_instance"]["listings_target_buyable"] += 1
        with self.assertRaises(SystemExit):
            v2.buyable_reading(broken)

    def test_the_largest_size_is_checked_like_with_like(self):
        # The cheapest XL listed sold out: _instance still names it, the key names the
        # cheapest that can be bought, and the file is written. Before 20 October the key
        # was compared with _instance and the file refused.
        market = copy.deepcopy(self.thornwood)
        ivybridge = next(f for f in market["families"] if f["parent_sku"] == "IGR-APP-08")
        next(v for v in ivybridge["variants"] if v["option"] == "XL")["qty"] = 0
        key = v2.keys(market)
        self.assertNotEqual(key["large_winner"]["seller"], "Ivybridge Collective")
        self.assertEqual(key["large_winner"]["seller"], "Fairhaven Workwear")
        # A real drift still fires: _instance naming a seller the variants do not.
        market["_instance"]["largest_size_winner"]["seller"] = "Jarrow Garments"
        with self.assertRaises(SystemExit):
            v2.keys(market)

    def test_a_pilot_from_another_market_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = copy.deepcopy(self.thornwood)
            other["_instance"]["winner"]["price"] = 1.0
            fixture = pathlib.Path(tmp) / "other.json"
            fixture.write_text(json.dumps(other))
            run = subprocess.run([sys.executable, "env/generate_apparel_v2_tasks.py",
                                  "--fixture", str(fixture), "--v1-tasks",
                                  str(paths.TASKS / "tasks_apparel.json"),
                                  "--out", str(pathlib.Path(tmp) / "t.json"),
                                  "--readings-out", str(pathlib.Path(tmp) / "r.json")],
                                 cwd=paths.REPO, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("is not other.json's market", run.stderr)

    def test_a_fresh_market_never_writes_over_thornwoods_v2_files(self):
        claim = paths.FIXTURES / "claim_apparel.json"
        elsewhere = pathlib.Path(tempfile.gettempdir())
        self.assertIn("over Thornwood's v2 files",
                      v2.own_market_refused(claim, v2.DEFAULT_OUT, elsewhere / "r.json"))
        self.assertIn("over Thornwood's v2 files",
                      v2.own_market_refused(claim, elsewhere / "t.json", v2.DEFAULT_READINGS_OUT))
        self.assertIn("under", v2.own_market_refused(elsewhere / "claim_apparel.json",
                                                     elsewhere / "t.json", elsewhere / "r.json"))
        self.assertIsNone(v2.own_market_refused(claim, elsewhere / "t.json", elsewhere / "r.json"))


class LiveCheckComparisons(unittest.TestCase):
    """`env/check_market.py`'s comparisons, on Thornwood's fixture and planted faults."""

    def setUp(self):
        self.fixture = load(THORNWOOD)
        self.listings = check_market.expected(self.fixture)
        self.record = {"url": "x", "count": 15, "total": 15, "next_page": False,
                       "listings": [{"seller": l["seller"], "advertised": l["advertised"],
                                     "url": l["url"]} for l in self.listings]}

    def test_a_correct_results_page_passes(self):
        self.assertEqual(check_market.results_problems(self.record, self.fixture), [])

    def test_each_planted_fault_on_the_results_page_fires(self):
        faults = {
            "a next page": lambda r: r.update(next_page=True),
            "a card at the cheapest of every size": lambda r: r["listings"][6].update(advertised=15.04),
            "a stale listing": lambda r: (r["listings"].append(
                {"seller": "Old Seller", "advertised": 9.99, "url": "http://localhost:7770/igr-clm-99.html"}),
                r.update(count=16, total=16)),
            "a seller under another URL": lambda r: r["listings"][0].update(seller="Someone Else"),
        }
        for name, plant in faults.items():
            with self.subTest(fault=name):
                record = copy.deepcopy(self.record)
                plant(record)
                self.assertTrue(check_market.results_problems(record, self.fixture))

    def test_a_menu_read_wrong_fires_and_a_right_one_does_not(self):
        fairhaven = self.listings[6]
        right = [{"label": s, "buyable": c, "price": p} for s, p, c in fairhaven["sizes"]]
        self.assertEqual(check_market.menu_problems(right, fairhaven, "gated"), [])
        for name, change in (("salability", {"buyable": True}), ("price", {"price": 15.05}),
                             ("label", {"label": "XS"})):
            with self.subTest(fault=name):
                wrong = copy.deepcopy(right)
                wrong[1].update(change)
                self.assertTrue(check_market.menu_problems(wrong, fairhaven, "gated"))

    def test_the_leak_test_finds_a_price_however_it_is_written(self):
        rookwood = self.listings[2]          # S 12.30, L 11.87, advertised 11.87
        self.assertEqual(check_market.leaked('"amount": 12.3}', rookwood), ["12.30"])
        self.assertEqual(check_market.leaked("As low as $12.30", rookwood), ["12.30"])
        self.assertEqual(check_market.leaked("As low as $11.87, 112.30, 12.305", rookwood), [])

    def test_the_ordinary_menu_reads_the_price_table_and_the_label(self):
        config = {"attributes": {"139": {"options": [
            {"label": "S", "products": ["1"]}, {"label": "M", "products": ["2"]}]}},
            "optionPrices": {"1": {"finalPrice": {"amount": 16.22}},
                             "2": {"finalPrice": {"amount": 15.04}}}}
        options = [{"text": "S -$2.11", "disabled": True, "value": "11"},
                   {"text": "M -$3.29", "disabled": False, "value": "12"}]
        menu = check_market.plain_menu(options, config, 18.33)
        self.assertEqual([(e["label"], e["price"], e["label_price"], e["buyable"]) for e in menu],
                         [("S", 16.22, 16.22, False), ("M", 15.04, 15.04, True)])
        html = ('<script type="text/x-magento-init">{"#product_addtocart_form": '
                '{"configurable": {"spConfig": {"optionPrices": {}}}}}</script>')
        self.assertEqual(check_market.spconfig_in(html), {"optionPrices": {}})
        self.assertIsNone(check_market.spconfig_in("<html></html>"))


def claim_page(fixture: dict, base: str) -> page.Page:
    """The claim market's results page as the box reads it, built from the fixture rather
    than fetched: each listing's seller, its card price and the URL its SKU gives it.
    `env/check_market.py` checks the live page says exactly this."""
    listings = [page.Listing(seller=f["seller"], title=f["name"],
                             url=f"{base}/{f['parent_sku'].lower()}.html",
                             advertised=apparel.from_price(f))
                for f in fixture["families"]]
    return page.Page(url=f"{base}/catalogsearch/result/?q={fixture['_generated']['brand']}",
                     listings=listings, total=len(listings), next_page=False)


class ClaimMarketFiles(unittest.TestCase):
    """The committed claim fixture, task file and sidecar are what the generators write,
    byte for byte, from the seed, the brand, the prefix and the seed search's record."""

    def setUp(self):
        self.fixture, self.spec = load(CLAIM), load(CLAIM_TASKS)

    def test_the_fixture_regenerates_from_its_seed_brand_prefix_and_search(self):
        generated = self.fixture["_generated"]
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / CLAIM.name
            subprocess.run([sys.executable, "env/generate_apparel.py", "--seed",
                            str(generated["seed"]), "--brand", generated["brand"],
                            "--sku-prefix", generated["sku_prefix"], "--out", str(out),
                            "--search-log", str(SEARCH_LOG.relative_to(paths.REPO))],
                           cwd=paths.REPO, check=True, capture_output=True)
            self.assertEqual(out.read_bytes(), CLAIM.read_bytes())
        self.assertEqual(generated["search"], load(SEARCH_LOG))

    def test_the_task_file_and_sidecar_regenerate_from_the_fixture_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks, readings = pathlib.Path(tmp) / CLAIM_TASKS.name, pathlib.Path(tmp) / CLAIM_READINGS.name
            subprocess.run([sys.executable, "env/generate_apparel_v2_tasks.py", "--fixture",
                            str(CLAIM.relative_to(paths.REPO)), "--out", str(tasks),
                            "--readings-out", str(readings)],
                           cwd=paths.REPO, check=True, capture_output=True)
            self.assertEqual(tasks.read_bytes(), CLAIM_TASKS.read_bytes())
            self.assertEqual(readings.read_bytes(), CLAIM_READINGS.read_bytes())

    def test_the_search_tried_204_first_and_accepted_the_last(self):
        search = self.fixture["_generated"]["search"]
        self.assertEqual(search["tried"][0]["seed"], 204)
        self.assertEqual([t["seed"] for t in search["tried"]],
                         list(range(204, 204 + len(search["tried"]))))
        self.assertEqual(search["tried"][-1]["outcome"], "accepted")
        self.assertTrue(all(t["outcome"] != "accepted" for t in search["tried"][:-1]))
        self.assertEqual(search["tried"][-1]["seed"], self.fixture["_generated"]["seed"])

    def test_the_brand_is_the_first_of_the_list_that_is_no_seller_word(self):
        brand = self.fixture["_generated"]["brand"]
        self.assertEqual(brand, next(b for b in BRANDS if b.lower() not in pick.seller_words()))
        for name in apparel.NAME_FIRST + apparel.NAME_SECOND:
            self.assertNotIn(brand.lower(), name.lower().split())
        # The listings are the claim market's own: its prefix, its brand, none of Thornwood's SKUs.
        thornwood = {f["parent_sku"] for f in load(THORNWOOD)["families"]}
        for family in self.fixture["families"]:
            self.assertTrue(family["parent_sku"].startswith("IGR-CLM-"))
            self.assertTrue(family["name"].startswith(f"{brand} Heavyweight Cotton Tee - "))
            self.assertNotIn(family["parent_sku"], thornwood)

    def test_the_six_are_thornwoods_words_with_the_brand(self):
        brand = self.fixture["_generated"]["brand"]
        pilot = load(paths.TASKS / "tasks_apparel.json")["tasks"]
        for mine, theirs in zip(self.spec["tasks"][:6], pilot):
            self.assertEqual(mine["id"], theirs["id"])
            self.assertEqual(mine["query"].replace(brand, "Thornwood"), theirs["query"])
            self.assertEqual(mine["box"], v2.box(*v2.V1_BOX[mine["id"]]))

    def test_every_key_of_the_six_is_the_fixtures(self):
        truth = verify_cells.ground_truth(CLAIM)
        by = {t["id"]: t["expect"] for t in self.spec["tasks"]}
        card = min(truth.values(), key=lambda t: t["from"])
        self.assertEqual(by["apparel-headline"], {"kind": "contains", "any": [card["seller"].split()[0]],
                                                  "price": card["from"]})
        best = min(t["buyable"]["M"] for t in truth.values() if "M" in t["buyable"])
        self.assertEqual(by["apparel-target-price"], {"kind": "price", "value": best})
        self.assertEqual(by["apparel-count-stocked"]["value"],
                         sum(1 for t in truth.values() if "M" in t["sizes"]))
        self.assertEqual(by["apparel-count-buyable"]["value"],
                         sum(1 for t in truth.values() if "M" in t["buyable"]))
        self.assertEqual(by["apparel-all-stocked"]["value"], False)
        winner = next(t for t in truth.values() if t["buyable"].get("M") == best)
        self.assertEqual(by["apparel-cheapest-target"]["any"], [winner["seller"].split()[0]])
        readings = score.readings_for(CLAIM_TASKS)["buyable"]
        self.assertEqual(readings["apparel-count-stocked"]["value"],
                         by["apparel-count-buyable"]["value"])

    def test_the_file_names_its_own_fixture_and_draws_a_new_market(self):
        self.assertEqual(self.spec["fixture"], CLAIM.name)
        self.assertEqual(verify_cells.fixture_for(self.spec), CLAIM)
        self.assertEqual(self.spec["_instance"], self.fixture["_instance"])
        thornwood = load(paths.TASKS / "tasks_apparel.json")
        self.assertNotEqual(suite.draw_id(self.spec), suite.draw_id(thornwood))
        self.assertTrue(suite.draw_id(self.spec).startswith("Ashcombe:"))

    def test_every_question_the_box_asks_about_has_its_other_reading(self):
        # So a --reading buyable batch never reaches the scorer's refusal mid-run.
        readings = score.readings_for(CLAIM_TASKS)
        asked = [t["id"] for t in self.spec["tasks"] if t["box"]["outcome"] == "ask" and t["box"]["kind"]]
        self.assertEqual(asked, ["apparel-all-stocked", "apparel-count-stocked"])
        for task_id in asked:
            self.assertIn(task_id, readings["buyable"])

    def test_the_box_does_what_each_claim_task_expects(self):
        base = self.spec["base_url"]
        market = claim_page(self.fixture, base)
        for task in self.spec["tasks"]:
            question = task["query"].format(base=base)
            url = box.results_url(question, required=False)
            decision = box.decide(question, market if url else None)
            record = decision.record()
            outcome, kind = task["box"]["outcome"], task["box"]["kind"]
            with self.subTest(task=task["id"], outcome=outcome):
                if outcome == "plan":
                    self.assertEqual((decision.kind, record["asked"], record["fallback"],
                                      record["bypassed"], decision.refuse),
                                     (kind, False, False, False, None))
                elif outcome == "ask":
                    self.assertEqual((decision.query, decision.kind, record["asked"]), (None, None, True))
                    answered = box.decide(question, market, reply="menu")
                    self.assertEqual((answered.kind, answered.query is not None), (kind, kind is not None))
                elif outcome == "refuse":
                    self.assertTrue(decision.refuse)
                elif outcome == "bypass":
                    self.assertTrue(decision.bypass)
                else:
                    self.fail(f"unexpected outcome {outcome!r}")


class ClaimListingCounter(unittest.TestCase):
    """On the claim market a listing counts as opened only when its URL is one of the
    market's own 15, in every arm, under the box or not (protocol, primary 2). Shown on a
    planted log with a known count (LESSONS 1): two claim listings, a Thornwood listing, a
    category page, the results page and a listing by id, of which two count."""

    LOG = "\n".join([
        "page.goto('http://localhost:7770/catalogsearch/result/?q=Ashcombe')",
        "page.goto('http://localhost:7770/igr-clm-03.html')",
        "Page URL: http://localhost:7770/igr-clm-07.html\\n- generic",
        "page.goto('http://localhost:7770/igr-app-07.html')",
        "Page URL: http://localhost:7770/electronics.html",
        "page.goto('http://localhost:7770/catalog/product/view/id/4242')",
        "page.goto('http://localhost:7770/igr-clm-03.html')",
    ])

    def setUp(self):
        self.spec = load(CLAIM_TASKS)
        self.market = verify_cells.market_urls(self.spec)

    def test_the_market_is_the_fixtures_fifteen_urls(self):
        self.assertEqual(len(self.market), 15)
        self.assertEqual(self.market[0], "http://localhost:7770/igr-clm-01.html")
        # Files before the field keep the counts they were reported with.
        self.assertIsNone(verify_cells.market_urls(load(paths.TASKS / "tasks_apparel_v2.json")))

    def test_two_listings_count_on_the_planted_log(self):
        self.assertEqual(sufficiency.listings_opened(self.LOG, self.market),
                         {"slug:igr-clm-03", "slug:igr-clm-07"})
        # The fault this guards against: without the market, the Thornwood listing and the
        # id path count too.
        self.assertEqual(sufficiency.listings_opened(self.LOG),
                         {"slug:igr-clm-03", "slug:igr-clm-07", "slug:igr-app-07", "id:4242"})

    def test_a_planted_run_of_any_arm_counts_by_membership_and_lists_the_rest(self):
        task = next(t for t in self.spec["tasks"] if t["id"] == "apparel-cheapest-target")
        truth = verify_cells.ground_truth(CLAIM)
        with tempfile.TemporaryDirectory() as tmp:
            record = pathlib.Path(tmp) / "apparel-cheapest-target-1.json"
            record.write_text(json.dumps({"scaffold": "naive", "shop": "gated",
                                          "user_agent": "Mozilla/5.0 IGRGated/1.0",
                                          "result": {"final": "Copperfield at $23.43", "ok": True}}))
            record.with_suffix(".log").write_text(self.LOG)
            # A shipped run, with no page record, and a run under the box, whose page record
            # lists the market: the count is the same.
            for stored in ({}, {"box": {"page": {"listings": [{"url": u} for u in self.market]}}}):
                with self.subTest(box=bool(stored)):
                    run = verify_cells.verify_run(record, task, truth, stored, market=self.market)
                    self.assertEqual((run["opened"], run["skus"]), (2, ["igr-clm-03", "igr-clm-07"]))
                    self.assertEqual(run["outside_market"], ["4242", "igr-app-07"])
                    self.assertEqual(run["unknown_pages"], [])


class ReadingsRefusal(unittest.TestCase):
    """`score.under_reading` refuses a reading it has no key for on a question with two
    readings, and keeps every other question's own key."""

    def setUp(self):
        self.spec = load(CLAIM_TASKS)
        self.by = {t["id"]: t for t in self.spec["tasks"]}
        self.readings = score.readings_for(CLAIM_TASKS)

    def test_the_claim_sidecar_gives_the_buyable_keys(self):
        self.assertEqual(score.under_reading(self.by["apparel-count-stocked"], "buyable",
                                             self.readings)["expect"], {"kind": "count", "value": 7})
        self.assertEqual(score.under_reading(self.by["apparel-all-stocked"], "buyable",
                                             self.readings)["expect"], {"kind": "boolean", "value": False})

    def test_it_fires_without_the_entry_or_without_a_sidecar(self):
        partial = {"buyable": {"apparel-count-stocked": {"kind": "count", "value": 7}}}
        for readings in ({}, partial):
            with self.subTest(readings=readings):
                with self.assertRaises(score.NoKeyForReading):
                    score.under_reading(self.by["apparel-all-stocked"], "buyable", readings)

    def test_it_stays_quiet_on_the_tasks_own_reading_and_fires_on_clear_questions_too(self):
        stocked = self.by["apparel-count-stocked"]
        self.assertIs(score.under_reading(stocked, "menu", {}), stocked)
        self.assertIs(score.under_reading(stocked, None, {}), stocked)
        # Since score.py v4 (22 October 2026) a clear question answered under the buyable
        # reading needs its key too: the reading is the run's, taken from what the box did,
        # and a model's ask can put it on a question the word list reads as clear. Until
        # then these fell back to their own keys (verifier finding).
        for task_id in ("apparel-headline", "apparel-target-price", "apparel-count-buyable",
                        "apparel-exists-under-24", "apparel-named-pair"):
            with self.subTest(task=task_id):
                with self.assertRaises(score.NoKeyForReading):
                    score.under_reading(self.by[task_id], "buyable", {})
                self.assertIs(score.under_reading(self.by[task_id], None, {}), self.by[task_id])

    def test_the_buyable_count_comes_from_the_runs_own_sidecar(self):
        run = {"task": "apparel-count-stocked", "answer": "7 listings", "ok": True,
               "rescored": "wrong", "buyable_key": {"kind": "count", "value": 7}}
        self.assertTrue(compare_cells.correct(run, "buyable"))
        # Thornwood's figure, the 5 this used to be typed as, would judge it wrong.
        self.assertFalse(compare_cells.correct({**run, "buyable_key": {"kind": "count", "value": 5}},
                                               "buyable"))
        with self.assertRaises(score.NoKeyForReading):
            compare_cells.correct({**run, "buyable_key": None}, "buyable")
        self.assertFalse(compare_cells.correct(run, "menu"))


if __name__ == "__main__":
    unittest.main()
