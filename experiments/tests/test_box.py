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
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import page  # noqa: E402
import planner  # noqa: E402
import policy  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402
import targeting  # noqa: E402

BASE = "http://localhost:7770"
RESULTS_URL = f"{BASE}/catalogsearch/result/?q=Example"


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
        # Controls included (LESSONS 18). The two clothing "offer" questions, the two water
        # "stock the pack" questions, and the two water "which seller offers the lowest
        # price per litre" questions ask. The other 31 do not.
        asking, total = [], 0
        for name in ("tasks.json", "tasks_scaled.json", "tasks_heldout.json",
                     "tasks_apparel.json", "tasks_reviews.json"):
            spec = json.loads((paths.TASKS / name).read_text())
            total += len(spec["tasks"])
            asking += [(name, t["id"]) for t in spec["tasks"] if ambiguity.ask(t["query"])]
        self.assertEqual(total, 37)
        self.assertEqual(asking, [("tasks_scaled.json", "scaled-all-stocked"),
                                  ("tasks_scaled.json", "scaled-best-per-litre"),
                                  ("tasks_heldout.json", "scaled-all-stocked"),
                                  ("tasks_heldout.json", "scaled-best-per-litre"),
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
                    self.assertEqual(planner.verify(decision.plan), [])
                    self.assertTrue(decision.query.startswith(q + "\n\n"))
                    self.assertEqual(decision.record()["asked"], False)

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

    def test_the_record_carries_the_versions_and_the_page(self):
        decision = box.decide(self.questions["apparel-target-price"], self.page)
        record = decision.record()
        self.assertEqual(record["box_version"], box.VERSION)
        self.assertEqual(record["page"], self.page.record())
        self.assertEqual(record["kind"], "availability_bound")
        self.assertEqual((decision.plan["planner_version"], decision.plan["strategy_version"]),
                         (planner.VERSION, targeting.VERSION))

    def test_results_url_is_the_first_url_in_the_question(self):
        self.assertEqual(box.results_url(self.questions["apparel-headline"]),
                         f"{BASE}/catalogsearch/result/?q=Thornwood")
        self.assertEqual(box.results_url(f"See {BASE}/a.html."), f"{BASE}/a.html")
        with self.assertRaises(ValueError):
            box.results_url("Which seller is cheapest for size M?")


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

    def test_the_floor_counts_listings_advertised_at_or_below_the_price_named(self):
        # Six at or below, the equal one included.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$15.15"), 6)
        # The first price named is the one that counts.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$12.15, not $24.15"), 3)
        # Below every advertised price: at least the one named.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "$9.00"), 1)
        # No price named: the whole page.
        self.assertEqual(policy.page_floor(self.CHEAPEST, self.page, "Seller F, I think"), 15)
        # Not a superlative over the market: no floor of this kind.
        self.assertIsNone(policy.page_floor(self.COUNT, self.page, "$15.15"))


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
                                           "page": self.page})
                query, applied = suite.build_query(task, self.spec, self.args(box=True, reading="menu"))
                self.assertEqual(query, box.decide(q, self.page, reply="menu").query)
                self.assertIsNotNone(query)

    def test_without_the_box_the_text_is_as_before(self):
        task = next(t for t in self.spec["tasks"] if t["id"] == "apparel-all-stocked")
        q = self.question(task)
        self.assertEqual(suite.build_query(task, self.spec, self.args()),
                         (q, {"strategy": None, "box": None, "page": None}))
        self.assertEqual(suite.build_query(task, self.spec, self.args(targeting=True)),
                         (planner.planned_query(q)[0],
                          {"strategy": "refutation", "box": None, "page": None}))
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

    def test_the_box_and_a_strategy_flag_are_refused(self):
        run = subprocess.run(
            [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
             "--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
             "--box", "--targeting", "--dry-run"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("--box cannot be combined with --targeting or --exhaustive", run.stderr)

    def test_the_browser_tool_is_pinned_and_the_user_agent_defined_once(self):
        self.assertIn(f"@playwright/mcp@{suite.BROWSER_TOOL}", suite.MCP_ARGS_GATED)
        self.assertNotIn("latest", suite.MCP_ARGS_GATED)
        self.assertIn(page.GATED_UA, suite.MCP_ARGS_GATED)
        self.assertIs(suite.GATED_UA, page.GATED_UA)


# What a piece of code can read an answer through: the keys of a task's answer, of a market's
# instance and of the seeder's manifests, and the fixture and manifest files themselves. Not
# covered: a bare number such as the market's size, which no test can tell from any other 15.
ANSWER_KEYS = {"_instance", "expect", "oracle_min_opens", "ground_truth"}
BEFORE_THE_AGENT = ("targeting.py", "planner.py", "page.py", "ambiguity.py", "box.py")


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
        for name in ("page.py", "ambiguity.py", "box.py", "targeting.py"):
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
