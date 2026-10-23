"""The fixes from the verifier's fairness audit of d357c72 (box v18, form v12, primitives v12,
23 October 2026), each shown firing on the case it was written for and quiet on the texts it
must leave alone, and each fault named planted with a fresh bytecode cache and seen to fail
(LESSONS 31, 39).

1. Under a scope the texts say to open or read the listings above, and over several pages
   every results page, where they said every listing in the search results or on the page
   after the preamble had said only one product's are part of the question.
2. A rate question can be planned with no bound (`rate="every"`), recorded in the decision,
   the plan, the batch and a void's re-run, since the bound's largest pack is a figure of the
   fixture. The bound stays the default, and both per-litre texts say to choose each pack and
   look again.
3. A pack is asked about as a pack, and its reading read back from the question.
4. A decline names the attribute a generic superlative ranks by when a word beside it names
   one: "tastes best" is taste.
5. Open everything naming the product checks every option the question needs.
6. The parse call's tokens are recorded per run, beside the agent's and added to the run's,
   so a comparison on tokens counts the parse too (suite.py, claim.py).

Nothing here calls a model or touches the shop.
"""
import argparse
import dataclasses
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import ambiguity  # noqa: E402
import box  # noqa: E402
import claim  # noqa: E402
import form  # noqa: E402
import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import page as page_module  # noqa: E402
import policy  # noqa: E402
import primitives  # noqa: E402
import replay_box  # noqa: E402
import suite  # noqa: E402
import targeting  # noqa: E402
import voids  # noqa: E402
from test_box import BASE, RESULTS_URL, thornwood_page  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402
from test_model_parser import PARSE_TOKENS, keyed_tasks, replying  # noqa: E402

GO = f"Go to {RESULTS_URL} . "
SECOND = f"{BASE}/catalogsearch/result/index/?p=2&q=Example"
# What a text may not say of the listings to open or read under a scope or over two pages.
UNSCOPED = ("every listing in the search results", "every listing from the search results",
            "every listing on the page", "the whole results page", "search results page alone")


def two_products(pages: int = 2) -> page_module.Page:
    """A search for "Example" holding a tee and a water, made-up sellers and prices, titled
    the way the shop titles the A+ market's listings, on `pages` results pages."""
    listings = []
    for n in range(6):
        noun, name = (("Tee", "Example Heavyweight Cotton Tee") if n % 2 == 0
                      else ("Water", "Example Natural Spring Water, Still"))
        seller = f"Seller {chr(65 + n)}"
        listings.append(page_module.Listing(seller=seller, title=f"{name} - {seller}",
                                            url=f"{BASE}/example-{noun.lower()}-{n + 1:02d}.html",
                                            advertised=10.0 + n))
    return page_module.Page(url=RESULTS_URL, listings=listings, total=len(listings), next_page=False,
                            pages=(RESULTS_URL, SECOND)[:pages], reader="rendered")


# One question of each plannable kind about the tee, and the two about the water.
TEE = {
    "results_page": "Of the Example tee listings shown, which one advertises the lowest price on the "
                    "results page, and what is that price?",
    "availability_bound": "What is the lowest price anyone charges for size M of the Example tee, among "
                          "those that can actually be bought?",
    "survey": "How many of the Example tee listings have size M in stock and available to buy right now?",
    "refutation": "Does every Example tee listing offer size M? Answer yes or no.",
    "exists_price": "Is there any Example tee listing with size M available to buy for under $20? Answer "
                    "yes or no, and name the seller if yes.",
    "topk_price": "Which three sellers are cheapest for size M of the Example tee among listings that can "
                  "actually supply it, and at what prices?",
    "argmax_price": "Which tee seller is the most expensive for size M?",
}
PER_LITRE = GO + ("Across all the Example water listings and all their pack sizes, which seller offers the "
                  "lowest price per litre among packs that can actually be bought?")
PACK = GO + "Does every Example water listing stock the 2 x 9.5L pack? Answer yes or no."


class TheTextsFollowTheScope(unittest.TestCase):
    """Fix 1. Planted: `in_scope` returning its instruction unchanged, and applying its
    swaps on every page."""

    def test_under_a_scope_over_two_pages_no_text_points_past_the_listings_above(self):
        page = two_products()
        for kind, words in TEE.items():
            for exhaust in (False, True):
                with self.subTest(kind=kind, exhaust=exhaust):
                    decision = box.decide(GO + words, page, reply="menu", exhaust=exhaust)
                    self.assertEqual((decision.kind, decision.scope.applied), (kind, True))
                    for words_unscoped in UNSCOPED:
                        self.assertNotIn(words_unscoped, decision.query)
        survey = box.decide(GO + TEE["survey"], page)
        self.assertIn("Open every listing above and check the relevant option", survey.query)
        bound = box.decide(GO + TEE["availability_bound"], page)
        self.assertIn("1. Read the advertised price of every listing above first.", bound.query)
        headline = box.decide(GO + TEE["results_page"], page)
        self.assertIn("from the search results pages alone", headline.query)
        self.assertIn("Read every results page, not only the first screen", headline.query)

    def test_over_two_pages_of_one_product_only_the_pages_are_said_again(self):
        one = dataclasses.replace(two_products(), listings=two_products().listings[::2])
        headline = box.decide(GO + TEE["results_page"], one)
        self.assertFalse(headline.scope.applied)
        self.assertIn("Read every results page", headline.query)
        survey = box.decide(GO + TEE["survey"], one)
        # True of a search on two pages: every listing of both is in its results.
        self.assertIn("Open every listing in the search results", survey.query)

    def test_on_one_page_of_one_product_every_text_is_unchanged(self):
        page = thornwood_page()
        for kind, words in TEE.items():
            for exhaust in (False, True):
                with self.subTest(kind=kind, exhaust=exhaust):
                    decision = box.decide(GO + words.replace("Example ", ""), page, reply="menu",
                                          exhaust=exhaust)
                    plan = decision.plan
                    self.assertEqual(primitives.in_scope(plan.instruction, page), plan.instruction)
                    if kind in targeting.BODIES and not exhaust and kind != "rate_bound":
                        self.assertEqual(plan.instruction, targeting.BODIES[kind])
        headline = box.decide(GO + TEE["results_page"], page)
        self.assertIn("Read the whole results page, not only the first screen", headline.query)


class TheRatePlan(unittest.TestCase):
    """Fix 2. Planted: `every_rate` ignoring its rate, the default made "every", the record
    without the field, and the void's re-run without the flag."""

    def setUp(self):
        self.page = two_products()

    def test_by_default_the_bound_stays_and_says_to_look_again(self):
        decision = box.decide(PER_LITRE, self.page)
        self.assertEqual((decision.kind, decision.rate, decision.plan.primitive), ("rate_bound", "bound",
                                                                                   "bound_prune"))
        self.assertIn(f"divided by {targeting.LARGEST_PACK_LITRES}", decision.query)
        self.assertIn("choose each pack size in turn, then look at the page again", decision.query)
        self.assertIn("Count only a pack that can actually be bought.", decision.query)
        self.assertEqual((decision.record()["rate_plan"], decision.plan.record()["rate_plan"]),
                         ("bound", "bound"))
        # The arm without the stop rule still finds the bound's sentences to swap.
        exhaust = box.decide(PER_LITRE, self.page, exhaust=True)
        self.assertIn(primitives.OPEN_EVERY.replace("on the page", "above"), exhaust.query)
        self.assertNotIn("Skip any unopened listing", exhaust.query)

    def test_every_listing_with_no_bound_and_held_to_every_listing(self):
        decision = box.decide(PER_LITRE, self.page, rate="every")
        self.assertEqual((decision.kind, decision.rate, decision.plan.primitive, decision.plan.stop_rule),
                         ("rate_bound", "every", "exhaust", primitives.RATE_EVERY_STOP))
        for bound_words in (str(targeting.LARGEST_PACK_LITRES), "largest pack", "Skip", "bound"):
            self.assertNotIn(bound_words, decision.plan.instruction)
        self.assertIn("Open every listing above.", decision.query)
        self.assertIn("choose each pack size in turn, then look at the page again", decision.query)
        self.assertEqual((decision.record()["rate_plan"], decision.plan.record()["rate_plan"]),
                         ("every", "every"))
        # The arm without the stop rule sends the same text: there is no stop sentence in it.
        self.assertEqual(box.decide(PER_LITRE, self.page, rate="every", exhaust=True).query, decision.query)
        # Its check is every listing of the water: fires on one opened, quiet on all three.
        planned = decision.planned
        waters = [item.url for item in planned.listings]
        answer = "Seller B, 6 x 1.25L at $11.00, $1.47 a litre."
        one = primitives.check(decision.form, planned, answer, f"Page URL: {waters[0]}", rate="every")
        every = primitives.check(decision.form, planned, answer, "\n".join(f"Page URL: {u}" for u in waters),
                                 rate="every")
        # Under the bound the same form is held to another primitive's check, the bound's.
        bound = primitives.check(decision.form, planned, answer, f"Page URL: {waters[0]}")
        self.assertNotEqual(bound["primitive"], one["primitive"])
        self.assertEqual((one["ok"], one["flag"], every["ok"]), (False, "population_not_covered", True))

    def test_any_other_question_is_planned_as_before(self):
        for words in TEE.values():
            with self.subTest(question=words[:40]):
                bound = box.decide(GO + words, self.page, reply="menu")
                every = box.decide(GO + words, self.page, reply="menu", rate="every")
                self.assertEqual((every.query, every.rate), (bound.query, "every"))
        with self.assertRaises(ValueError):
            box.decide(PER_LITRE, self.page, rate="no bound")

    def test_the_batch_and_a_voids_rerun_carry_it(self):
        # Refused without the box, recorded with it, and None without it.
        refused = run_suite("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                            "--only", "apparel-headline", "--rate-plan", "every")
        self.addCleanup(refused.owner.cleanup)
        self.assertEqual(refused.code, 2)
        self.assertIn("--rate-plan is how the box plans a rate question", refused.out)
        for flags, recorded in ((["--box", "--rate-plan", "every"], "every"), (["--box"], "bound"), ([], None)):
            with self.subTest(flags=flags):
                ran = run_suite("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                                "--only", "apparel-headline", *flags, page=thornwood_page())
                self.addCleanup(ran.owner.cleanup)
                self.assertEqual(ran.code, 0, ran.out)
                payload = json.loads((ran.batch / "suite.json").read_text())
                self.assertEqual(payload["rate_plan"], recorded)
                self.assertEqual("rate plan: every" in ran.out, recorded == "every")
                rerun = voids.rerun_flags(ran.batch)
                self.assertEqual("--rate-plan every" in rerun, recorded == "every")
                if recorded:
                    self.assertEqual(payload["rows"][0]["box"]["rate_plan"], recorded)
        self.assertIn("rate_plan", claim.PROTOCOL_CONDITIONS)
        self.assertIn("rate_plan", claim.PROTOCOL_ARM_CONDITIONS)

    def test_a_stored_plan_is_recomposed_under_its_own(self):
        decision = box.decide(PER_LITRE, self.page, rate="every")
        stored = replay_box.stored_decision({"box": decision.record()})
        self.assertEqual((stored.rate, stored.plan.text), ("every", decision.plan.text))
        # A record from before the field was planned with the bound.
        old = {key: value for key, value in box.decide(PER_LITRE, self.page).record().items()
               if key != "rate_plan"}
        self.assertEqual(replay_box.stored_decision({"box": old}).rate, "bound")


class APackIsAskedAboutAsAPack(unittest.TestCase):
    """Fix 3. Planted: the pack's words never chosen, and its reading not read back."""

    def test_the_rules_ask_about_a_pack_in_its_menus_words(self):
        asked = ambiguity.ask(PACK)
        self.assertTrue(asked.text.startswith("Your question says 'stock'. On this shop a pack can be"))
        self.assertIn("pack size menu includes it", asked.readings["menu"].sentence)
        self.assertIn("a sold-out pack does not count", asked.readings["buyable"].sentence)
        for words in (asked.text, asked.readings["menu"].sentence, asked.readings["buyable"].sentence):
            self.assertNotIn("size can", words)
            self.assertNotIn("sold-out size", words)
        # A size reads as it always did, to the byte.
        size = ambiguity.ask(GO + "Does every listing offer size M?")
        self.assertEqual(size.text, ambiguity.ASK.format(verb="offer"))
        self.assertEqual(size.readings["menu"].sentence,
                         ambiguity.READINGS["menu"][1].format(phrase="offer size M"))

    def test_the_reading_is_read_back_from_a_packs_sentence(self):
        page = two_products()
        for reply, value in (("menu", "listed"), ("buyable", "buyable")):
            with self.subTest(reply=reply):
                decision = box.decide(PACK, page, reply=reply)
                self.assertEqual((decision.reading, decision.form.filter("availability").value),
                                 (reply, value))

    def test_the_model_path_asks_in_a_packs_words_when_its_option_is_a_pack(self):
        flagged = ambiguity.availability_ask("carry", pack=True)
        self.assertIn("a pack can be", flagged.text)
        self.assertEqual(ambiguity.availability_ask("carry").text, ambiguity.ASK.format(verb="carry"))


class ADeclineNamesWhatTheQuestionRanksBy(unittest.TestCase):
    """Fix 4. Planted: the words beside a generic superlative never read."""

    def test_tastes_best_is_taste(self):
        for words, named in (("Which Example water tastes best?", "taste"),
                             ("Which Example water smells best?", "smell"),
                             ("Which Example tee fits best?", "fit")):
            with self.subTest(words=words):
                question = GO + words
                self.assertEqual(form.graded_unknown(question)[0], named)
                refused = box.decide(question, two_products())
                self.assertTrue(refused.refuse.startswith(f"The shop does not show {named}, so this "
                                                          f"question cannot be answered"), refused.refuse)

    def test_a_word_that_names_nothing_keeps_the_old_name(self):
        for words, name in (("Who sells the softest Example tee?", "what 'softest' ranks by"),
                            ("Which Example seller is the best?", "what 'best' ranks by")):
            with self.subTest(words=words):
                self.assertEqual(form.graded_unknown(GO + words)[0], name)
        # And a shown attribute beside "best" is no unknown at all.
        self.assertIsNone(form.graded_unknown(GO + "Which Example water is the best value?"))

    def test_over_every_question_in_the_task_files_only_taste_is_renamed(self):
        questions = []
        for path in sorted(paths.TASKS.glob("tasks*.json")) + sorted(paths.PILOT_TASKS.glob("tasks*.json")):
            spec = json.loads(path.read_text())
            questions += [task["query"].format(base=BASE) for task in spec["tasks"]]
        with mock.patch.dict(form.NAMED_BESIDE, clear=True):
            before = [form.graded_unknown(q) for q in questions]
        after = [form.graded_unknown(q) for q in questions]
        changed = sorted({q.split(" . ", 1)[-1] for q, b, a in zip(questions, before, after) if b != a})
        self.assertEqual(changed, ["Which Larchmere water tastes best?"])


class OpenEverythingByProduct(unittest.TestCase):
    """Fix 5. The product wording checks every option the question needs; the default
    wording, which every open-everything batch before was sent, is unchanged."""

    def test_the_wordings(self):
        named = policy.exhaustive_query("Q?", "water")
        self.assertIn("open every water listing in the search results, including any on later pages, "
                      "and check every option the question needs on each one.", named)
        self.assertNotIn("the relevant option", named)
        self.assertEqual(policy.exhaustive_query("Q?"), "Q?" + policy.EXHAUSTIVE)
        self.assertIn("check the relevant option on each one", policy.EXHAUSTIVE)
        self.assertEqual(policy.EXHAUSTIVE_PRODUCT_VERSION, 2)

    def test_the_batch_records_the_wordings_version(self):
        spec = json.loads((paths.TASKS / "tasks_aplus_dev.json").read_text())
        self.assertTrue(all(task.get("product") for task in spec["tasks"]))
        for flags, recorded in ((["--exhaustive", "--exhaustive-wording", "product"], 2),
                                (["--exhaustive"], None), ([], None)):
            with self.subTest(flags=flags):
                ran = run_suite("--tasks", str(paths.TASKS / "tasks_aplus_dev.json"), "--repeats", "1",
                                "--only", "water-best-per-litre", *flags)
                self.addCleanup(ran.owner.cleanup)
                self.assertEqual(ran.code, 0, ran.out)
                payload = json.loads((ran.batch / "suite.json").read_text())
                self.assertEqual(payload["exhaustive_wording_version"], recorded)
        self.assertIn("exhaustive_wording_version", claim.PROTOCOL_CONDITIONS)


class TheParsesTokens(unittest.TestCase):
    """Fix 6. Planted: the call's tokens never collected, the record without the run's
    tokens, an unknown count read as zero, a stated count passed over by the analysis, and
    a closed slot's parse counted as nothing."""

    def test_a_calls_tokens_are_the_providers_count(self):
        usage = {"cost": 0.004, "prompt_tokens": 5200, "completion_tokens": 140}
        self.assertEqual(parse_probe.tokens_of(usage), {"prompt": 5200, "completion": 140})
        for broken in (None, {}, {"prompt_tokens": 5200}, {"prompt_tokens": "5200", "completion_tokens": 140},
                       {"prompt_tokens": True, "completion_tokens": 140}):
            with self.subTest(usage=broken):
                self.assertIsNone(parse_probe.tokens_of(broken))

        def answered(body):
            reply = mock.Mock()
            reply.raise_for_status = lambda: None
            reply.json = lambda: body
            return mock.patch.object(parse_probe.requests, "post", return_value=reply)

        with answered({"choices": [{"message": {"content": "a form"}}], "usage": usage}):
            self.assertEqual(parse_probe.call_model("k", "m", "p"), ("a form", 0.004, PARSE_TOKENS, None))
        with answered({"usage": usage}), self.assertRaises(parse_probe.UnexpectedReply) as raised:
            parse_probe.call_model("k", "m", "p")
        self.assertEqual((raised.exception.cost, raised.exception.tokens), (0.004, PARSE_TOKENS))

    def test_a_runs_parse_is_summed_and_unknown_stays_unknown(self):
        two = suite.parse_tokens([{"prompt": 10, "completion": 2}, {"prompt": 5, "completion": 1}])
        self.assertEqual(two, {"prompt": 15, "completion": 3, "total": 18, "calls": 2})
        self.assertEqual(suite.parse_tokens([]), {"prompt": 0, "completion": 0, "total": 0, "calls": 0})
        self.assertIsNone(suite.parse_tokens([{"prompt": 10, "completion": 2}, None]))
        self.assertEqual(suite.run_tokens({"prompt": 100, "completion": 10, "total": 110, "calls": 3}, two),
                         {"prompt": 115, "completion": 13, "total": 128})
        self.assertIsNone(suite.run_tokens({"prompt": 100, "completion": 10}, None))
        self.assertIsNone(suite.run_tokens(None, two))

    def batch(self, *flags: str, call=None) -> tuple[dict, dict]:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        tasks = keyed_tasks(pathlib.Path(folder.name))
        with mock.patch.object(parse_probe, "call_model", call or replying()), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"):
            run = run_suite("--tasks", str(tasks), "--repeats", "1", "--only", "apparel-cheapest-target",
                            "apparel-all-stocked", "--box", *flags, page=thornwood_page())
        self.addCleanup(run.owner.cleanup)
        self.assertEqual(run.code, 0, run.out)
        payload = json.loads((run.batch / "suite.json").read_text())
        record = json.loads((run.batch / "apparel-cheapest-target-1.json").read_text())
        return payload, record

    def test_a_batch_records_them_beside_the_agents(self):
        payload, record = self.batch("--parser", "model")
        rows = {row["task"]: row for row in payload["rows"]}
        one = {**PARSE_TOKENS, "total": 5340, "calls": 1}
        self.assertEqual((rows["apparel-cheapest-target"]["parse_tokens"], rows["apparel-all-stocked"]["parse_tokens"]),
                         (one, one))
        agent = record["trace"]["tokens"]
        self.assertEqual((record["agent_tokens"], record["parse_tokens"]), (agent, one))
        self.assertEqual(record["tokens"], {"prompt": agent["prompt"] + 5200, "completion": agent["completion"] + 140,
                                            "total": agent["prompt"] + agent["completion"] + 5340})
        self.assertEqual(claim.stated_tokens(record), record["tokens"])
        # The asked slot ran no agent: its tokens are its parse's.
        self.assertEqual(claim.closed_tokens(rows["apparel-all-stocked"]), (5340, (5200, 140)))
        self.assertEqual((payload["parse_tokens"], payload["parse_tokens_unknown"]),
                         ({"prompt": 10400, "completion": 280, "total": 10680, "calls": 2}, 0))

    def test_an_unknown_count_is_unknown_and_the_rules_count_none(self):
        payload, record = self.batch("--parser", "model", call=replying(tokens=None))
        rows = {row["task"]: row for row in payload["rows"]}
        self.assertEqual((rows["apparel-cheapest-target"]["parse_tokens"], record["tokens"]), (None, None))
        self.assertIsNone(claim.stated_tokens(record))
        self.assertEqual(claim.closed_tokens(rows["apparel-all-stocked"]), (None, (None, None)))
        self.assertEqual(payload["parse_tokens_unknown"], 2)
        payload, record = self.batch()
        rows = {row["task"]: row for row in payload["rows"]}
        self.assertNotIn("parse_tokens", rows["apparel-cheapest-target"])
        self.assertNotIn("tokens", record)
        self.assertEqual(claim.stated_tokens(record), record["trace"]["tokens"])
        self.assertEqual(claim.closed_tokens(rows["apparel-all-stocked"]), (0, (None, None)))
        self.assertIsNone(payload["parse_tokens"])


class TheVersions(unittest.TestCase):
    def test_they_moved_together(self):
        self.assertEqual((box.VERSION, primitives.VERSION, form.VERSION, targeting.VERSION),
                         (18, 12, 13, 9))


if __name__ == "__main__":
    unittest.main()
