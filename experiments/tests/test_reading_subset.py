"""The reading test on the tee-only market (24 October 2026): `parse_probe.py --only-templates`,
entries with no template, their `ask_kind`, the {seller} and {promo} placeholders, the held-task
match across two held-out files, and `paraphrase_scores`' third group.

As tests/test_reading_test.py: the held-out files are never opened; a stand-in in their shape,
in words written for these tests, takes their place on the pilot's market, Larchmere, with its
task file and a stored batch. Each rule has a case where it fires and one where it stays
quiet, and each fault named was planted with a fresh bytecode cache and seen to fail its test
(LESSONS 31, 39). Nothing here calls a model or touches the shop.
"""
import contextlib
import io
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import paraphrase_scores  # noqa: E402
import parse_probe  # noqa: E402
from test_provider_routing import Posted  # noqa: E402
from test_reading_test import BASE, BATCH, DEEPSEEK, LEAD, PILOT, Market, run, standin  # noqa: E402

# The promo-check template as the verifier fixed it on 24 October 2026, and the market's
# wording of it for one listing.
PROMO = ("The {seller} listing of the {brand} tee says in its size menu that size XS is on promotion at "
         "${promo}. Is that what size XS costs on that listing? If not, what does it cost?")
SELLER, FIGURE = "Alderney Supply", "9.99"
# The market's templates, as the chain lists them: the pilot market's tee templates, the
# promo check added here and decline-delivery. It lacks tee-xs-price, which stands for a
# template the market does not hold (as the water templates do for the real tee-only market).
MARKET_TEMPLATES = ["tee-headline", "tee-target-price", "tee-cheapest-target", "tee-all-stocked", "tee-count-stocked",
                    "tee-count-buyable", "tee-exists-under", "tee-top-3", "tee-promo-check", "decline-delivery"]


def entry(n, template, text, expected="plan", label="clear", template_text=None, **more) -> dict:
    found = {"id": n, "template": template, "text": text, "expected": expected, "expected_why": "for the tests",
             "label": label, "meaning_kept": True, **more}
    if template is not None:
        found["template_text"] = template_text
    return found


class PromoMarket(Market):
    """The pilot's market with a tee-promo-check task added, worded for one listing. The task
    file's draw hashes its `_instance`, so an added task leaves it the batch's."""

    def market(self, name: str = "tasks_promo.json", promo_wording: str | None = None, extra: list | None = None):
        wording = promo_wording or PROMO.format(seller=SELLER, brand="Larchmere", promo=FIGURE)
        promo = {"id": "tee-promo-check", "family": "aplus", "product": "tee", "gated": True,
                 "query": f"Go to {{base}}/catalogsearch/result/?q=Larchmere . {wording}",
                 "expect": {"kind": "price", "target": 12.5}, "box": {"outcome": "plan", "kind": "lookup"}}
        return self.write(name, {**self.pilot, "tasks": self.pilot["tasks"] + [promo] + (extra or [])})

    def promo_entries(self) -> list[dict]:
        return [entry(1, "tee-promo-check", "Is XS of the {brand} tee really ${promo} at {seller}, as its menu says?",
                      template_text=PROMO),
                entry(2, "tee-headline", "Which {brand} tee card shows the lowest price?",
                      template_text="Of the {brand} tee listings shown, which one advertises the lowest price on the "
                                    "results page, and what is that price?"),
                entry(3, None, "Does {seller} really sell XS of the {brand} tee for ${promo}?", expected="ask",
                      label="ambiguous", ask_kind="threshold"),
                entry(4, "tee-xs-price", "What does the cheapest buyable extra-small {brand} tee go for?",
                      template_text="What is the lowest price anyone charges for size XS of the {brand} tee, among "
                                    "those that can actually be bought?")]


class StatedValues(unittest.TestCase):
    def test_every_placeholder_is_read_off_the_wording(self):
        copy = PROMO.replace("{brand}", "Larchmere")
        self.assertEqual(parse_probe.stated_values(copy, PROMO.format(seller=SELLER, brand="Larchmere", promo=FIGURE)),
                         {"seller": SELLER, "promo": FIGURE})
        self.assertEqual(parse_probe.stated_values("Is there a {brand} tee under ${limit}?", "Is there a Larchmere tee under $20?"),
                         {"brand": "Larchmere", "limit": "20"})

    def test_another_wording_or_figure_shape_is_none(self):
        copy = PROMO.replace("{brand}", "Larchmere")
        for wording in (PROMO.format(seller=SELLER, brand="Larchmere", promo="9.9"),     # not two decimals
                        PROMO.format(seller=SELLER, brand="Larchmere", promo=FIGURE).replace("promotion", "sale"),
                        "Is there a Larchmere tee under $20.50?"):
            with self.subTest(wording=wording[:40]):
                self.assertIsNone(parse_probe.stated_values(copy if "promotion" in wording or "sale" in wording
                                                            else "Is there a {brand} tee under ${limit}?", wording))

    def test_a_repeated_placeholder_must_repeat_its_value(self):
        copy = "{seller} sells it; does {seller} also ship?"
        self.assertEqual(parse_probe.stated_values(copy, "Alder sells it; does Alder also ship?"), {"seller": "Alder"})
        self.assertIsNone(parse_probe.stated_values(copy, "Alder sells it; does Birch also ship?"))


class TheFilter(PromoMarket):
    def test_only_templates_keeps_the_markets_entries_and_the_template_less_ones(self):
        spec, entries, _ = self.load(standin(paraphrases=self.promo_entries()), task_file=self.market(),
                                     only_templates=MARKET_TEMPLATES)
        self.assertEqual([e["id"] for e in entries], [1, 2, 3])
        self.assertEqual(spec["left_out"], [{"id": 4, "template": "tee-xs-price"}])
        self.assertEqual((spec["only_templates"], spec["without_template"]), (MARKET_TEMPLATES, 1))

    def test_without_the_filter_a_template_the_market_lacks_is_refused_as_before(self):
        with self.assertRaisesRegex(ValueError, "paraphrase 4 rewords 'tee-xs-price', which tasks_promo.json "
                                                "does not hold"):
            self.load(standin(paraphrases=self.promo_entries()), task_file=self.market())

    def test_the_printed_lines_name_the_left_out_by_id_and_template_and_no_text(self):
        results = self.folder / "results"
        results.mkdir()
        questions = self.write("standin.json", standin(paraphrases=self.promo_entries()))
        texts = [e["text"] for e in self.promo_entries()]
        code, printed = run(["--dry-run", "--questions", str(questions), "--spec-from", str(self.market()),
                             "--page-from", str(BATCH), "--model", DEEPSEEK, "--only-templates", *MARKET_TEMPLATES], results)
        self.assertEqual(code, 0)
        line = next(l for l in printed.splitlines() if l.startswith("--only-templates keeps"))
        self.assertEqual(line, "--only-templates keeps 3 entries and leaves out 1: 4 (tee-xs-price)")
        self.assertNotIn(texts[3].split("{brand}")[0].strip(), line)
        self.assertIn("1 with no template, compared with the expected outcome alone", printed)
        # The dry run prints the kept questions, filled: the seller and the promo figure.
        self.assertIn(f"Is XS of the Larchmere tee really ${FIGURE} at {SELLER}, as its menu says?", printed)
        self.assertNotIn("extra-small", printed)

    def test_the_flag_needs_questions_and_an_empty_subset_is_refused(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            run(["--dry-run", "--only-templates", "tee-headline"], self.folder)
        with self.assertRaisesRegex(ValueError, "no entry left to probe under --only-templates"):
            self.load(standin(paraphrases=self.promo_entries()[3:]), task_file=self.market(),
                      only_templates=["tee-headline"])


class Placeholders(PromoMarket):
    def test_seller_and_promo_come_from_the_task_files_wording(self):
        spec, entries, _ = self.load(standin(paraphrases=self.promo_entries()[:1]), task_file=self.market())
        self.assertEqual(spec["placeholders"], {"brand": "Larchmere", "seller": SELLER, "promo": FIGURE})
        self.assertEqual(entries[0]["question"],
                         f"{LEAD} Is XS of the Larchmere tee really ${FIGURE} at {SELLER}, as its menu says?")
        self.assertIsNone(spec["limit"], "no entry's template states a limit")

    def test_a_template_less_entry_takes_values_the_other_templates_state(self):
        spec, entries, _ = self.load(standin(paraphrases=self.promo_entries()[:3]), task_file=self.market())
        self.assertEqual(entries[2]["question"], f"{LEAD} Does {SELLER} really sell XS of the Larchmere tee for ${FIGURE}?")
        self.assertIsNone(entries[2]["template_question"])

    def test_a_value_no_template_states_and_two_values_are_refused(self):
        with self.assertRaisesRegex(ValueError, "paraphrase 3 needs a promo and a seller, and no template in "
                                                "tasks_promo.json states them"):
            self.load(standin(paraphrases=[self.promo_entries()[1], self.promo_entries()[2]]), task_file=self.market())
        other = entry(5, "tee-promo-check", "Is {seller} honest about XS?", template_text=PROMO)
        two = {**self.pilot["tasks"][0], "id": "tee-promo-again", "query": f"Go to {{base}}/catalogsearch/result/"
               f"?q=Larchmere . {PROMO.format(seller='Birch Goods', brand='Larchmere', promo='8.49')}"}
        with self.assertRaisesRegex(ValueError, "state 2 different sellers"):
            self.load(standin(paraphrases=[self.promo_entries()[0], dict(other, template="tee-promo-again")]),
                      task_file=self.market(extra=[two]))

    def test_the_promo_wording_otherwise_is_refused_without_its_words(self):
        with self.assertRaises(ValueError) as raised:
            self.load(standin(paraphrases=self.promo_entries()[:1]),
                      task_file=self.market(promo_wording=PROMO.format(seller=SELLER, brand="Larchmere", promo=FIGURE)
                                            .replace("promotion", "sale")))
        self.assertIn("paraphrase 1's template, tee-promo-check, is not worded in tasks_promo.json", str(raised.exception))
        self.assertNotIn("really", str(raised.exception))


class TemplateLess(PromoMarket):
    def test_a_template_less_entry_has_no_form_no_tiers_and_its_ask_kind(self):
        _, entries, page = self.load(standin(paraphrases=self.promo_entries()[:3]), task_file=self.market())
        row, expected = parse_probe.rules_half(entries[2], page)
        self.assertIsNone(expected)
        self.assertEqual((row["expected"], row["rules_tiers"], row["template_box"], row["ask_kind"]),
                         (None, None, None, "threshold"))
        self.assertIsNotNone(row["rules"])
        templated, _ = parse_probe.rules_half(entries[0], page)
        self.assertIsNotNone(templated["rules_tiers"])

    def test_an_ask_kind_the_file_does_not_know_is_refused(self):
        bad = dict(self.promo_entries()[2], ask_kind="vibes")
        with self.assertRaisesRegex(ValueError, "paraphrase 3 names the ask kind 'vibes', not one of availability, threshold, other"):
            self.load(standin(paraphrases=[self.promo_entries()[0], bad]), task_file=self.market())

    def test_the_totals_count_tiers_over_the_templated_rows_and_the_audit_over_all(self):
        _, entries, page = self.load(standin(paraphrases=self.promo_entries()[:3]), task_file=self.market())
        rows = [parse_probe.rules_half(e, page)[0] for e in entries]
        totals = parse_probe.question_totals(rows, with_model=False)
        self.assertEqual((totals["paraphrases"], totals["with_template"], totals["without_template"]), (3, 2, 1))
        self.assertLessEqual(totals["rules"]["quantifier"], 2)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            parse_probe.print_totals(totals, with_model=False)
            for row in rows:
                parse_probe.print_paraphrase(row)
        self.assertIn("3 paraphrases, 2 with a template:", out.getvalue())
        self.assertIn(" 3 no template, labelled ambiguous (threshold ask):", out.getvalue())
        self.assertIn("no form: compared with the expected outcome alone", out.getvalue())


class AskKinds(unittest.TestCase):
    def found(self, outcome, ask=None):
        return {"outcome": outcome, "kind": None, "ask": ask, "reading_by": None, "detail": None}

    def test_only_the_named_ask_meets_an_entry_with_an_ask_kind(self):
        reading, limit, other, unlisted = (self.found("ask", a) for a in ("reading", "price limit", "other", "unlisted"))
        self.assertTrue(parse_probe.meets_audit("ASK", limit, "threshold"))
        self.assertFalse(parse_probe.meets_audit("ASK", reading, "threshold"), "a menu-or-buyable ask is not a threshold ask")
        self.assertTrue(parse_probe.meets_audit("ASK", reading, "availability"))
        self.assertFalse(parse_probe.meets_audit("ASK", limit, "availability"))
        for found in (other, unlisted):
            self.assertTrue(parse_probe.meets_audit("ASK", found, "other"))
        self.assertFalse(parse_probe.meets_audit("ASK", reading, "other"))
        self.assertFalse(parse_probe.meets_audit("ASK", self.found("plan"), "threshold"))

    def test_without_an_ask_kind_any_ask_meets_as_before(self):
        for ask in ("reading", "price limit", "other", "unlisted"):
            self.assertTrue(parse_probe.meets_audit("ASK", self.found("ask", ask)))
            self.assertTrue(parse_probe.meets_audit("ASK", self.found("ask", ask), None))
        self.assertEqual(parse_probe.COMPARISON_VERSION, 3)
        self.assertEqual(parse_probe.READ_AGAIN, (1, 2))


class HeldTask(unittest.TestCase):
    """Which task a held-out entry is held to, across v2 and v3 numbered alike."""

    def task(self, tid, template, rewording, note):
        return {"id": tid, "template": template, "rewording": rewording, "note": note, "query": "q"}

    def test_a_task_from_another_file_is_never_the_entrys(self):
        tasks = {"rw-05": self.task("rw-05", "tee-headline", 5, "Held-out rewording 5 of tee-headline (paraphrases_v2.json), kept."),
                 "rw3-05": self.task("rw3-05", "tee-headline", 5, "Held-out rewording 5 of tee-headline (paraphrases_v3.json)."),
                 "pv1-05": self.task("pv1-05", "tee-headline", 5, "Development rewording 5 (paraphrases_v1.json, in sample)")}
        held = parse_probe.held_task({"id": 5, "template": "tee-headline"}, tasks, "paraphrases_v3.json")
        self.assertEqual(held["id"], "rw3-05")
        self.assertEqual(parse_probe.held_task({"id": 5, "template": "tee-headline"}, tasks, "paraphrases_v2.json")["id"], "rw-05")
        self.assertIsNone(parse_probe.held_task({"id": 5, "template": "tee-top-3"}, tasks, "paraphrases_v2.json"))

    def test_two_tasks_that_fit_alike_take_none_and_an_unnamed_source_may_fit(self):
        tasks = {"a": self.task("a", "tee-headline", 5, "no file named here"),
                 "b": self.task("b", "tee-headline", 5, "nor here")}
        self.assertIsNone(parse_probe.held_task({"id": 5, "template": "tee-headline"}, tasks, "paraphrases_v3.json"))
        self.assertEqual(parse_probe.held_task({"id": 5, "template": "tee-headline"}, {"a": tasks["a"]}, "x.json")["id"], "a")
        self.assertEqual(parse_probe.named_source({"rewordings": "paraphrases_v3.json", "note": "(paraphrases_v2.json)"}),
                         "paraphrases_v3.json")


class ScoresWithoutTemplate(PromoMarket):
    """A paid run against a faked OpenRouter whose result holds a template-less row: the file
    records the filter, and paraphrase_scores reads the three groups."""

    def test_the_result_file_and_the_scores(self):
        results = self.folder / "results"
        results.mkdir()
        spec = standin(paraphrases=self.promo_entries())
        questions = self.write("standin.json", spec)
        code, _ = run(["--questions", str(questions), "--spec-from", str(self.market()), "--page-from", str(BATCH),
                       "--model", DEEPSEEK, "--only-templates", *MARKET_TEMPLATES], results, post=Posted("GMICloud"))
        self.assertEqual(code, 0)
        written = json.loads(next(results.glob("parse-probe-standin-*.json")).read_text())
        self.assertEqual((written["only_templates"], written["left_out"], written["placeholders"]),
                         (MARKET_TEMPLATES, [{"id": 4, "template": "tee-xs-price"}],
                          {"brand": "Larchmere", "seller": SELLER, "promo": FIGURE}))
        rows = {row["id"]: row for row in written["rows"]}
        self.assertEqual(sorted(rows), [1, 2, 3])
        self.assertIsNone(rows[3]["model_tiers"])
        self.assertIsNotNone(rows[1]["model_tiers"])
        self.assertIn("model_box_as_audit_expected", written["totals"])
        self.assertEqual(written["totals"]["without_template"], 1)
        scored = paraphrase_scores.scores(written, {**spec, "paraphrases": [e for e in spec["paraphrases"] if e["id"] != 4]})
        self.assertEqual(scored["without_template"]["ids"], [3])
        self.assertEqual(scored["meaning_kept"]["ids"], [1, 2])
        self.assertEqual(scored["without_template"]["totals"]["paraphrases"], 1)
        self.assertEqual(scored["problems"], [], "a template-less row has no tiers to recompute")
        self.assertIn("1 with no template, compared with the expected outcome alone", paraphrase_scores.render(scored))
        self.assertEqual(paraphrase_scores.VERSION, 3)

    def test_a_template_less_entry_needs_no_meaning_kept_flag(self):
        spec = standin(paraphrases=[dict(self.promo_entries()[2], meaning_kept=None)])
        result = {"questions": "standin.json", "comparison_version": parse_probe.COMPARISON_VERSION, "rows": [],
                  "model": "fake", "temperature": 0, "calls_failed": 0}
        self.assertEqual(paraphrase_scores.scores(result, spec)["without_template"]["no_row"], [3])
        with self.assertRaisesRegex(SystemExit, "does not say whether entries \\[1\\] keep"):
            paraphrase_scores.scores(result, standin(paraphrases=[dict(self.promo_entries()[0], meaning_kept=None)]))


if __name__ == "__main__":
    unittest.main()
