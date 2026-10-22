"""`experiments/analysis/paraphrase_scores.py`: a paraphrase probe's figures over the entries
whose meaning is the template's, and the others listed, as paraphrases_v1.json fixed before
any model call (37a8f66). Written on 20 October 2026, before the first paid paraphrase run.

Two kinds of test. A synthetic result file whose every count is worked out by hand in the
comments. And the rules' half of the real probe, made by parse_probe's own loop with a faked
model, which must give over the 24 what the dry run gives for them, pinned here. Every rule
has a case where it fires and one where it stays quiet, and the faults were planted and seen
to fail these tests (LESSONS 31). Nothing here reaches a model.
"""
import contextlib
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
import form  # noqa: E402
import page  # noqa: E402
import parse_probe  # noqa: E402
import paraphrase_scores  # noqa: E402
import plan_probe  # noqa: E402
from form import Filter, Form  # noqa: E402

PARAPHRASES = paths.TASKS / "paraphrases_v1.json"
THORNWOOD = paths.RESULTS / "20261014T213118" / "suite.json"
DIFFER = [10, 22, 25, 27, 28, 29]


# ---------------------------------------------------------------------------
# 1. A synthetic result file

EXPECTED = Form("argmin", "price", (Filter("size", "=", "M"), Filter("availability", "=", "buyable")),
                evidence={"filter:size": "size M", "filter:availability": "in stock"})


def variant(source: str, **over) -> Form:
    """The expected form with some fields changed, as the rules' or a model's form."""
    fields = dict(quantifier="argmin", objective="price", population="results", k=None,
                  filters=EXPECTED.filters, evidence=dict(EXPECTED.evidence))
    fields.update(over)
    return Form(source=source, **fields)


SAME = {}                                                                 # every tier
SIZE_L = {"filters": (Filter("size", "=", "L"), Filter("availability", "=", "buyable"))}   # all but every field
LISTING = {"population": "listing"}                                       # quantifier, objective
RATE = {"objective": "rate"}                                              # quantifier
ARGMAX = {"quantifier": "argmax"}                                         # nothing


def outcome(name: str, kind: str | None = None, ask: str | None = None) -> dict:
    return {"outcome": name, "kind": kind, "ask": ask, "reading_by": None, "detail": None}


def synthetic_row(n: int, rules: dict, model: dict | None, box: dict, template_box: dict,
                  label: str | None, audit: str, model_problems: tuple = ()) -> dict:
    """A row as parse_probe's paid loop writes one, its tiers by parse_probe.tiers."""
    rules_form = variant("rules", **rules)
    model_form = variant("model", **model) if model is not None else None
    return {"id": n, "template": "apparel-target-price", "label": label, "audit_expected": audit,
            "text": f"Paraphrase number {n}?", "question": f"Go to there . Paraphrase number {n}?",
            "expected": EXPECTED.record(), "rules": rules_form.record(), "rules_problems": [],
            "rules_tiers": parse_probe.tiers(EXPECTED, rules_form), "box": box, "template_box": template_box,
            "model": model_form.record() if model_form else None, "model_problems": list(model_problems),
            "model_tiers": parse_probe.tiers(EXPECTED, model_form),
            "error": None if model_form else "request failed: read timed out",
            "call_failed": model_form is None, "cost_usd": 0.001 if model_form else None}


def synthetic() -> tuple[dict, dict]:
    """Four paraphrases that keep the template's meaning and two that do not.

        id  kept  rules  model   box                          template's     label      audit
        1   yes   all    all     plan availability_bound      the same       -          availability_bound
        2   yes   q,o,p  all     plan total_bound             plan a._bound  clear      availability_bound
        3   yes   q,o    q       ask for a reading, refut.    the same       ambiguous  ASK
        4   yes   none   failed  refuse                       the same       -          REFUSE
        5   no    all    q,o,p   plan availability_bound      ask            -          ASK
        6   no    none   all     fallback survey              plan a._bound  clear      availability_bound

    Over the four: the rules reach the quantifier on 1, 2, 3, the objective on 1, 2, 3, the
    population on 1, 2 and every field on 1, so 3, 3, 2, 1. The model reaches 3, 2, 2, 2
    (1, 2, 3; 1, 2; 1, 2; 1, 2). Only the model: every field on 2. Only the rules: the
    objective on 3. The box: plan 2, ask 1, refuse 1; the same as the template's on 1, 3
    and 4; the audit's expectation met on 1, 3, 4; one ambiguous, asked; one clear, not.
    Counting all six instead would give the rules 2 on every field and the model 3."""
    rows = [
        synthetic_row(1, SAME, SAME, outcome("plan", "availability_bound"), outcome("plan", "availability_bound"),
                      None, "availability_bound"),
        synthetic_row(2, SIZE_L, SAME, outcome("plan", "total_bound"), outcome("plan", "availability_bound"),
                      "clear", "availability_bound"),
        synthetic_row(3, LISTING, RATE, outcome("ask", "refutation", "reading"),
                      outcome("ask", "refutation", "reading"), "ambiguous", "ASK",
                      model_problems=("a planted problem",)),
        synthetic_row(4, ARGMAX, None, outcome("refuse"), outcome("refuse"), None, "REFUSE"),
        synthetic_row(5, SAME, SIZE_L, outcome("plan", "availability_bound"), outcome("ask", "refutation", "reading"),
                      None, "ASK"),
        synthetic_row(6, ARGMAX, SAME, outcome("fallback", "survey"), outcome("plan", "availability_bound"),
                      "clear", "availability_bound"),
    ]
    spec = {"paraphrases": [{"id": row["id"], "template": row["template"], "text": row["text"],
                             "meaning_kept": row["id"] <= 4} for row in rows]}
    spec["paraphrases"][4]["meaning_differs"] = "asks about size L, where the template asks about size M"
    spec["paraphrases"][5]["meaning_differs"] = "asks one named seller's price"
    result = {"questions": "synthetic.json", "comparison_version": parse_probe.COMPARISON_VERSION,
              "model": "fake/model", "temperature": 0, "calls_failed": 1, "rows": rows}
    return result, spec


class SyntheticCounts(unittest.TestCase):
    def setUp(self):
        self.result, self.spec = synthetic()

    def test_the_tiers_planted(self):
        tiers = {row["id"]: (list(row["rules_tiers"].values()), list(row["model_tiers"].values()))
                 for row in self.result["rows"]}
        all_, qop, qo, q, none = [True] * 4, [True, True, True, False], [True, True, False, False], \
            [True, False, False, False], [False] * 4
        self.assertEqual(tiers, {1: (all_, all_), 2: (qop, all_), 3: (qo, q), 4: (none, none),
                                 5: (all_, qop), 6: (none, all_)})

    def test_the_counts_over_the_four_by_hand(self):
        found = paraphrase_scores.scores(self.result, self.spec)
        kept = found["meaning_kept"]
        self.assertEqual((kept["ids"], kept["entries"], kept["no_row"]), ([1, 2, 3, 4], 4, []))
        t = kept["totals"]
        self.assertEqual(t["paraphrases"], 4)
        self.assertEqual(t["rules"], {"quantifier": 3, "objective": 3, "population": 2, "every field": 1})
        self.assertEqual(t["model"], {"quantifier": 3, "objective": 2, "population": 2, "every field": 2})
        self.assertEqual(t["model_only"], {"quantifier": 0, "objective": 0, "population": 0, "every field": 1})
        self.assertEqual(t["rules_only"], {"quantifier": 0, "objective": 1, "population": 0, "every field": 0})
        self.assertEqual(t["box"], {"plan": 2, "fallback": 0, "ask": 1, "refuse": 1, "bypass": 0, "error": 0})
        self.assertEqual((t["box_as_template"], t["box_as_audit_expected"]), (3, 3))
        self.assertEqual((t["labelled_ambiguous"], t["labelled_clear"]),
                         ({"paraphrases": 1, "asked": 1}, {"paraphrases": 1, "asked": 0}))
        self.assertEqual((kept["model_forms_failing_verification"], kept["calls_failed"]), (1, 1))
        self.assertEqual(found["problems"], [])

    def test_the_two_are_listed_with_why_and_never_counted(self):
        found = paraphrase_scores.scores(self.result, self.spec)
        differ = found["meaning_differs"]
        self.assertEqual([row["id"] for row in differ["rows"]], [5, 6])
        self.assertEqual(differ["rows"][0]["meaning_differs"], "asks about size L, where the template asks about size M")
        text = paraphrase_scores.render(found)
        block = text.split("never counted\n", 1)[1]
        lines = block.splitlines()
        self.assertTrue(lines[0].startswith(" 5 apparel-target-price, labelled -: Paraphrase number 5?"))
        self.assertEqual(lines[1], "     meaning differs: asks about size L, where the template asks about size M")
        self.assertIn("     rules:    argmin price over results, filters: size = M, availability = buyable", block)
        self.assertIn("     model:    argmin price over results, filters: size = L, availability = buyable", block)
        self.assertIn("     meaning differs: asks one named seller's price", block)
        # Counted with the four, every field would read 2 for the rules and 3 for the model.
        self.assertRegex(text, r"\n  same on every field +1 +2 +1 +0 of 4\n")

    def test_a_stored_tier_today_computes_otherwise_is_reported(self):
        self.result["rows"][0]["rules_tiers"]["every field"] = False
        found = paraphrase_scores.scores(self.result, self.spec)
        self.assertEqual(len(found["problems"]), 1)
        self.assertIn("paraphrase 1: the file stores the rules' tiers", found["problems"][0])
        # The stored figure is the one counted, beside the problem.
        self.assertEqual(found["meaning_kept"]["totals"]["rules"]["every field"], 0)

    def test_a_run_that_stopped_early_is_scored_on_the_rows_it_has(self):
        self.result["rows"] = [row for row in self.result["rows"] if row["id"] != 2]
        kept = paraphrase_scores.scores(self.result, self.spec)["meaning_kept"]
        self.assertEqual((kept["ids"], kept["no_row"]), ([1, 3, 4], [2]))
        self.assertEqual(kept["totals"]["rules"], {"quantifier": 2, "objective": 2, "population": 1, "every field": 1})

    def test_what_is_refused(self):
        cases = {
            "another comparison version": (lambda r, s: r.update(comparison_version=0), "not scored together"),
            "an entry with no flag": (lambda r, s: s["paraphrases"][1].pop("meaning_kept"),
                                      "does not say whether entries [2]"),
            "a reworded entry": (lambda r, s: s["paraphrases"][2].update(text="Another question?"), "is not entry 3"),
            "another template": (lambda r, s: s["paraphrases"][0].update(template="apparel-headline"),
                                 "is not entry 1"),
            "a row the file lacks": (lambda r, s: s["paraphrases"].pop(), "is not entry 6"),
            "a row twice": (lambda r, s: r["rows"].append(dict(r["rows"][0])), "rows [1] more than once"),
        }
        for name, (change, words) in cases.items():
            with self.subTest(case=name):
                result, spec = synthetic()
                change(result, spec)
                with self.assertRaises(SystemExit) as refused:
                    paraphrase_scores.scores(result, spec)
                self.assertIn(words, str(refused.exception))
        # Unchanged, nothing is refused.
        self.assertEqual(paraphrase_scores.scores(*synthetic())["problems"], [])


# ---------------------------------------------------------------------------
# 2. The real probe's rules' half, through parse_probe's own loop with a faked model

# What the dry run gives for the 24 entries with meaning_kept, computed on 20 October 2026
# from the rules' half the dry run prints (`parse_probe.rules_half` on the page of
# 20261014T213118) with `parse_probe.question_totals`, and pinned. Over all 30 the dry run
# prints 20, 17, 17, 10; 10, 22, 28 and 29 reach the quantifier, and 22, 28 and 29 the
# objective and population too, and none of the six every field.
RULES_OVER_THE_24 = {"quantifier": 17, "objective": 14, "population": 14, "every field": 10}
BOX_OVER_THE_24 = {"plan": 14, "fallback": 1, "ask": 6, "refuse": 3, "bypass": 0, "error": 0}
# The same outcome and kind as the template's: 15 of 30 in the dry run, less 22 and 28.
BOX_AS_TEMPLATE_OVER_THE_24 = 13
# The faked model answers with the expected form but where a fault is planted. Among the 24:
# 2 another population (quantifier, objective), 3 another objective (quantifier), 4 another
# quantifier, 5 a filter added (all but every field), 6 no form, 7 a failed call; the other
# 18 reach every tier. So 18 + 3 = 21, 18 + 2 = 20, 18 + 1 = 19 and 18. Two of the six get
# a fault too, 22 another quantifier and 27 a failed call, and are listed, not counted.
PLANTED = {2: "population", 3: "objective", 4: "quantifier", 5: "a filter", 6: "no form",
           7: "a failed call", 22: "quantifier", 27: "a failed call"}
MODEL_OVER_THE_24 = {"quantifier": 21, "objective": 20, "population": 19, "every field": 18}
# Against the rules' tiers per paraphrase, read off the dry run: the rules miss the
# quantifier on 1, 3, 6, 11, 14, 19 and 24, where the model reaches it on all but 6; the
# objective (and the population) also on 2, 12 and 26, where the model reaches the
# objective on all but 3 and 6, and the population on all but 2, 3 and 6; every field also
# on 5, 7, 15 and 23, where the model reaches it on all but 2, 3, 5, 6 and 7. The model
# misses what the rules reach on 4 and 7 (quantifier, objective, population) and 4 (every
# field).
MODEL_ONLY_OVER_THE_24 = {"quantifier": 6, "objective": 8, "population": 7, "every field": 9}
RULES_ONLY_OVER_THE_24 = {"quantifier": 2, "objective": 2, "population": 2, "every field": 1}


def planted_reply(entry: dict, page_: page.Page) -> str:
    """The expected form as a model's JSON reply, with the fault planted for this entry."""
    expected = form.from_rules(entry["template_question"], page_).record()
    reply = {key: expected[key] for key in ("quantifier", "objective", "filters", "population",
                                            "k", "reading", "unknowns", "evidence")}
    fault = PLANTED.get(entry["id"])
    if fault == "population":
        # "reviews" rather than "listing" since 22 October 2026: the probe normalises the
        # model's form as the box would use it, and a "listing" with no product page named
        # is put back to the results page, which would plant nothing (test_probe.py says the
        # same of its own planted fault).
        reply["population"] = "reviews"
    elif fault == "objective":
        reply["objective"] = next(o for o in ("price", "rate") if o != reply["objective"])
    elif fault == "quantifier":
        reply["quantifier"] = next(q for q in ("argmin", "argmax") if q != reply["quantifier"])
        reply["k"] = None
    elif fault == "a filter":
        reply["filters"] = reply["filters"] + [{"attribute": "colour", "op": "=", "value": "red"}]
    elif fault == "no form":
        return "I cannot parse that."
    elif fault == "a failed call":
        raise requests.exceptions.Timeout("read timed out")
    return json.dumps(reply)


class TheRealRulesHalf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.page = parse_probe.stored_page(THORNWOOD)
        by_question = {entry["question"]: entry for entry in parse_probe.load_questions(PARAPHRASES)[1]}

        def call_model(key, model, prompt):
            return planted_reply(by_question[prompt.rsplit("The question:\n", 1)[1]], cls.page), 0.001

        with mock.patch.object(parse_probe, "RESULTS", pathlib.Path(cls.folder.name)), \
                mock.patch.object(page, "fetch", side_effect=AssertionError("the probe fetched")), \
                mock.patch.object(parse_probe, "call_model", call_model), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"), \
                mock.patch.object(plan_probe, "usage", return_value=None), \
                mock.patch.object(sys, "argv", ["parse_probe.py", "--questions", str(PARAPHRASES),
                                                "--model", "fake/model"]), \
                contextlib.redirect_stdout(io.StringIO()):
            cls.code = parse_probe.main()
        cls.path = next(pathlib.Path(cls.folder.name).glob("parse-probe-paraphrases_v1-*.json"))
        cls.result = json.loads(cls.path.read_text())
        cls.found = paraphrase_scores.scores(cls.result, paraphrase_scores.paraphrase_file(cls.result))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_rules_over_the_24_are_the_dry_runs(self):
        totals = self.found["meaning_kept"]["totals"]
        self.assertEqual(self.found["meaning_kept"]["ids"], [n for n in range(1, 31) if n not in DIFFER])
        self.assertEqual(totals["rules"], RULES_OVER_THE_24)
        self.assertEqual(totals["box"], BOX_OVER_THE_24)
        self.assertEqual(totals["box_as_template"], BOX_AS_TEMPLATE_OVER_THE_24)
        # And they are the dry run's own rows, restricted to the 24, counted by parse_probe.
        spec, entries = parse_probe.load_questions(PARAPHRASES)
        dry = [parse_probe.rules_half(entry, self.page)[0] for entry in entries]
        self.assertEqual(parse_probe.question_totals(dry, with_model=False)["rules"],
                         {"quantifier": 20, "objective": 17, "population": 17, "every field": 10})
        over_24 = parse_probe.question_totals([row for row in dry if row["id"] not in DIFFER], with_model=False)
        for key in ("rules", "box", "box_as_template", "box_as_audit_expected", "labelled_ambiguous",
                    "labelled_clear"):
            with self.subTest(key=key):
                self.assertEqual(totals[key], over_24[key])

    def test_the_model_over_the_24_by_hand(self):
        self.assertEqual(self.code, 0)
        totals = self.found["meaning_kept"]["totals"]
        self.assertEqual(totals["model"], MODEL_OVER_THE_24)
        self.assertEqual(totals["model_only"], MODEL_ONLY_OVER_THE_24)
        self.assertEqual(totals["rules_only"], RULES_ONLY_OVER_THE_24)
        # Each tier: the rules' count, plus where only the model reaches it, less where only
        # the rules do.
        for tier in parse_probe.TIERS:
            with self.subTest(tier=tier):
                self.assertEqual(totals["model"][tier],
                                 totals["rules"][tier] + totals["model_only"][tier] - totals["rules_only"][tier])
        # Failing verification among the 24: 5's added colour filter (the shop shows no
        # colour), 6's reply that is no form, and 24's form, the expected one, since the shop
        # shows no delivery time. Among the six 25's fails too. 7's call failed, and 27's,
        # one of the six. Counted over all thirty these would read 4 and 2.
        kept = self.found["meaning_kept"]
        self.assertEqual((kept["model_forms_failing_verification"], kept["calls_failed"]), (3, 1))
        self.assertEqual(self.result["calls_failed"], 2)
        self.assertEqual(self.found["problems"], [])

    def test_the_six_listed_with_why(self):
        differ = self.found["meaning_differs"]["rows"]
        spec = json.loads(PARAPHRASES.read_text())
        why = {entry["id"]: entry["meaning_differs"] for entry in spec["paraphrases"] if not entry["meaning_kept"]}
        self.assertEqual([row["id"] for row in differ], DIFFER)
        self.assertEqual({row["id"]: row["meaning_differs"] for row in differ}, why)
        text = paraphrase_scores.render(self.found)
        for n in DIFFER:
            with self.subTest(id=n):
                self.assertIn(f"\n     meaning differs: {why[n]}\n", text)
        # 22's model form is listed with its planted quantifier, and reaches no tier; 27's call
        # failed, and it is listed with no form.
        self.assertEqual([row["model"]["quantifier"] for row in differ if row["id"] == 22], ["argmin"])
        self.assertEqual([(row["call_failed"], row["model"]) for row in differ if row["id"] == 27], [(True, None)])
        self.assertIn("     model:    no form: request failed: read timed out", text)
        self.assertRegex(text, r"\n  same quantifier +17 +21 +\d+ +\d+ of 24\n")
        self.assertRegex(text, r"\n  same on every field +10 +18 +\d+ +\d+ of 24\n")
        self.assertIn("  the same outcome and kind as its template's  13 of 24", text)

    def test_the_command_prints_and_writes_the_same_figures(self):
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / "scores.json"
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(paraphrase_scores.main([str(self.path), "--json", str(target)]), 0)
            written = json.loads(target.read_text())
        self.assertEqual(written, json.loads(json.dumps(self.found)))
        self.assertTrue(out.getvalue().startswith(
            "The paraphrase probe, scored as paraphrases_v1.json fixed before any call"))
        self.assertIn("model fake/model; temperature 0", out.getvalue())


class FlagsFixedBeforeAnyCall(unittest.TestCase):
    def test_the_file_flags_24_and_explains_the_6(self):
        spec = json.loads(PARAPHRASES.read_text())
        kept = [entry["id"] for entry in spec["paraphrases"] if entry["meaning_kept"] is True]
        differ = [entry["id"] for entry in spec["paraphrases"] if entry["meaning_kept"] is False]
        self.assertEqual((len(kept), differ), (24, DIFFER))
        self.assertTrue(all(entry.get("meaning_differs") for entry in spec["paraphrases"]
                            if not entry["meaning_kept"]))
        self.assertTrue(re.search(r"reported over the 24 entries with meaning_kept true", " ".join(spec["_about"])))


if __name__ == "__main__":
    unittest.main()
