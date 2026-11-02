"""Study A's pre-registered analysis (2 November 2026), on synthetic batches only: no trial data,
model, browser or shop. The test plays the student, grading through the private key, so the
expected counts are known; each check passes a good batch and refuses or flags a planted fault."""
from collections import Counter, defaultdict
import contextlib
from fractions import Fraction
import io
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools"))
import fresh_batch  # noqa: E402
import browser_use_fresh_analysis as analysis  # noqa: E402
import browser_use_fresh_review as blind  # noqa: E402
import guarded_browser_use as guard  # noqa: E402

CORRECT = ("answered", "answered-settled", "answered-error-reply")  # the kinds whose answer names the key's price


def enumerated_p(strata):
    """The two-sided exact p by enumerating every relabelling within each stratum, in exact
    fractions: no formula shared with compare_cells.stratified_exact."""
    total = {0: Fraction(1)}
    for sa, na, sb, nb in strata:
        outcomes = [1] * (sa + sb) + [0] * (na + nb - sa - sb)
        counts = Counter(sum(outcomes[i] for i in chosen) for chosen in itertools.combinations(range(na + nb), na))
        step = defaultdict(Fraction)
        for t, p in total.items():
            for k, n in counts.items():
                step[t + k] += p * Fraction(n, sum(counts.values()))
        total = step
    observed = total[sum(s[0] for s in strata)]
    return float(sum(p for p in total.values() if p <= observed))


class Case(unittest.TestCase):
    """A synthetic batch, prepared, graded by the test as the student and validated."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"

    def make(self, kinds, grades=None, before_prepare=None):
        self.batch = fresh_batch.Batch(self.root / "repo", kinds)
        self.study = self.batch.study
        if before_prepare:
            before_prepare(self.batch)
        blind.prepare(self.study, self.batch.stage_args(), self.bundle)
        if grades is not False:
            self.grade(grades or {})

    def index(self, slot_id):
        return next(i for i, s in enumerate(self.batch.slots) if s["id"] == slot_id)

    def kind_of(self, mapped):
        """The stage that saved a trial, and the kind of trial the fixture wrote there."""
        stage = next(s for s in self.batch.stages if s.spec.stage == mapped["stage"])
        return stage, stage.kinds[stage.index(mapped["slot"])]

    def grade(self, special, save=True):
        """Answers of a correct kind graded correct, the rest not correct, except `special`: attempt
        1's slots by schedule index, any other trial by (stage, slot id)."""
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        rows = blind.review.read_sheet(self.bundle / self.study.sheet)
        for row in rows:
            mapped = key["codes"][row["code"]]
            stage, kind = self.kind_of(mapped)
            name = self.index(mapped["slot"]) if stage is self.batch else (mapped["stage"], mapped["slot"])
            row["hand_verdict"] = special.get(name, "correct" if kind in CORRECT else "not correct")
        incoming = self.root / "download.csv"
        incoming.write_text(blind.review.csv_text(rows), encoding="utf-8-sig", newline="")
        if save:
            blind.validate(self.study, self.bundle, incoming, save=True)
        return incoming

    def run_analysis(self):
        return analysis.analyse(self.study, self.bundle)

    def slot(self, result, index):
        return result["slots"][index]


class Gate(Case):
    def test_no_validated_review_refuses_before_the_private_key_is_read(self):
        self.make(fresh_batch.kinds_with({}), grades=False)
        reads = []
        real = blind.read_json

        def watched(path):
            reads.append(Path(path).name)
            return real(path)
        with mock.patch.object(blind, "read_json", side_effect=watched):
            with self.assertRaisesRegex(analysis.Refused, "No validated review"):
                self.run_analysis()
            self.grade({}, save=False)
            with self.assertRaisesRegex(analysis.Refused, "No validated review"):
                self.run_analysis()
        self.assertNotIn("private-arm-key.json", reads)

    def test_an_incomplete_or_changed_review_is_refused(self):
        self.make(fresh_batch.kinds_with({}))
        reviewed = self.bundle / "validated/reviewed.csv"
        original = reviewed.read_bytes()
        rows = blind.review.read_sheet(reviewed)
        rows[0]["hand_verdict"] = ""
        reviewed.write_text(blind.review.csv_text(rows), encoding="utf-8", newline="")
        with mock.patch.object(analysis.blind, "load_study", side_effect=AssertionError("no batch read")):
            with self.assertRaisesRegex(analysis.Refused, "Complete all 32"):
                self.run_analysis()
        rows[0]["hand_verdict"] = "not correct"  # complete, but not what the receipt bound
        reviewed.write_text(blind.review.csv_text(rows), encoding="utf-8", newline="")
        with self.assertRaisesRegex(analysis.Refused, "changed after its receipt"):
            self.run_analysis()
        reviewed.write_bytes(original)
        receipt = self.bundle / "validated/validation.json"
        fresh_batch.put(receipt, {**json.loads(receipt.read_text()), "arm_key_read": True})
        with self.assertRaisesRegex(analysis.Refused, "pre-unblinding"):
            self.run_analysis()

    def test_a_changed_input_or_private_key_is_refused(self):
        self.make(fresh_batch.kinds_with({}))
        self.run_analysis()  # the good case
        record = self.batch.path(4)
        original = record.read_bytes()
        record.write_bytes(original + b" ")
        with self.assertRaisesRegex(analysis.Refused, "bound at preparation changed"):
            self.run_analysis()
        record.write_bytes(original)
        key = self.bundle / "private-arm-key.json"
        key.write_bytes(key.read_bytes() + b" ")
        with self.assertRaisesRegex(analysis.Refused, "private key changed"):
            self.run_analysis()

    def test_a_file_added_after_preparation_is_refused(self):
        self.make(fresh_batch.kinds_with({}, ran=20))
        fresh_batch.put(self.batch.results / "stray.json", {})
        with self.assertRaisesRegex(analysis.Refused, "replayed"):
            self.run_analysis()


class Complete(Case):
    """All 32 slots ran: a failed trial graded correct, another graded unscorable, a closure and
    an unscorable answer."""

    def setUp(self):
        super().setUp()
        batch = fresh_batch.Batch(self.root / "probe", [])
        self.closed = fresh_batch.block_index(batch, "tee-top-3")
        baseline = [i for i, s in enumerate(batch.slots) if s["condition"] == "baseline"]
        self.failed, self.unscorable = baseline[0], fresh_batch.block_index(batch, "tee-headline", repeat=2)
        self.failed_unscorable = fresh_batch.block_index(batch, "tee-xs-price", repeat=2)
        kinds = {i: "wrong" for i in baseline[1:10]}
        kinds.update({self.failed: "failed", self.closed: "closed", self.failed_unscorable: "failed"})
        self.make(fresh_batch.kinds_with(kinds), grades={
            self.failed: "correct", self.unscorable: "unscorable", self.failed_unscorable: "unscorable"})
        self.result = self.run_analysis()

    def expected_strata(self, leave_out_unscorable=False):
        strata = []
        for task in self.study.task_ids:
            stratum = []
            for arm in ("block", "baseline"):
                indices = [i for i, s in enumerate(self.batch.slots) if s["question"]["id"] == task
                           and s["condition"] == arm and not (leave_out_unscorable and i == self.unscorable)]
                stratum += [sum(self.batch.kinds[i] == "answered" and i != self.unscorable for i in indices), len(indices)]
            strata.append(tuple(stratum))
        return strata

    def test_the_primary_test_is_the_planned_one(self):
        primary = self.result["primary_test"]
        strata = self.expected_strata()
        self.assertEqual([(s["block_correct"], s["block_trials"], s["baseline_correct"], s["baseline_trials"])
                          for s in primary["strata"]], strata)
        self.assertAlmostEqual(primary["p"], enumerated_p(strata), places=12)
        self.assertEqual((primary["slots_in_test"], primary["planned_slots"], primary["complete_against_plan"]),
                         (32, 32, True))
        self.assertEqual(primary["block_correct_of_trials"], [sum(s[0] for s in strata), 16])
        self.assertEqual(primary["left_out"], [])
        expected = "difference claimed: the block arm" if primary["p"] < .05 else "no difference claimed"
        self.assertTrue(primary["decision"].startswith(expected))

    def test_failed_and_closed_slots_count_zero_whatever_their_grade(self):
        failed, closed = self.slot(self.result, self.failed), self.slot(self.result, self.closed)
        self.assertEqual((failed["disposition"], failed["human_verdict"], failed["counted"], failed["in_test"]),
                         ("failed", "correct", 0, True))
        self.assertEqual((closed["disposition"], closed["human_verdict"], closed["counted"], closed["code"]),
                         (blind.CLOSED, None, 0, None))
        self.assertEqual({r["slot"] for r in self.result["graded_but_decided_by_disposition"]},
                         {failed["slot"], self.batch.slots[self.failed_unscorable]["id"]})

    def test_the_sensitivity_leaves_out_only_the_unscorable_answer(self):
        # The failed trial graded unscorable gave no final answer: it stays in, counted 0.
        sensitivity = self.result["sensitivity"]
        self.assertEqual([r["slot"] for r in sensitivity["left_out"]], [self.batch.slots[self.unscorable]["id"]])
        strata = self.expected_strata(leave_out_unscorable=True)
        self.assertAlmostEqual(sensitivity["p"], enumerated_p(strata), places=12)
        self.assertEqual(sensitivity["slots_in_test"], 31)
        self.assertIn("not a second primary", sensitivity["role"])
        self.assertEqual(self.slot(self.result, self.failed_unscorable)["counted"], 0)

    def test_both_denominators_and_repeats_are_reported(self):
        arms = self.result["arms"]
        block_correct = sum(self.batch.kinds[i] == "answered" and i != self.unscorable
                            for i, s in enumerate(self.batch.slots) if s["condition"] == "block")
        self.assertEqual(arms["block"]["correct_of_scheduled"], [block_correct, 16])
        self.assertEqual(arms["block"]["correct_of_in_test"], [block_correct, 16])
        self.assertEqual(arms["block"]["correct_of_sensitivity"], [block_correct, 15])
        self.assertEqual(arms["baseline"]["dispositions"], {"failed": 1, "answered": 15})
        self.assertEqual(arms["block"]["dispositions"], {"failed": 1, "answered": 14, blind.CLOSED: 1})
        for repeat in ("1", "2"):
            self.assertEqual(self.result["by_repeat"][repeat]["arms"]["baseline"]["scheduled"], 8)
        self.assertEqual(sum(self.result["by_repeat"][r]["arms"]["block"]["correct_of_scheduled"][0] for r in ("1", "2")),
                         block_correct)

    def test_charges_include_the_parser_and_match_the_ledger(self):
        ledger = json.loads(Path(self.batch.config["ledger_path"]).read_text())
        accounting = self.result["accounting"]
        self.assertAlmostEqual(accounting["total_charge_usd"], ledger["charged_usd"], places=12)
        in_test = accounting["charge_in_test_usd"]
        self.assertAlmostEqual(in_test["block"] + in_test["baseline"], ledger["charged_usd"], places=12)
        block = self.result["arms"]["block"]
        parser = 16 * fresh_batch.PARSER_USD
        self.assertAlmostEqual(block["measures_in_test"]["parser_charge_usd"]["total"], parser, places=12)
        self.assertAlmostEqual(block["parser_share_of_charge"], parser / in_test["block"], places=12)
        closed = self.slot(self.result, self.closed)
        self.assertAlmostEqual(closed["charge_usd"], fresh_batch.PARSER_USD, places=12)
        self.assertEqual(self.result["arms"]["baseline"]["measures_in_test"]["parser_charge_usd"]["total"], 0.0)

    def test_openings_and_script_fetches_sit_beside_each_other(self):
        closed, base = self.slot(self.result, self.closed), self.slot(self.result, self.failed)
        self.assertEqual((closed["openings"], closed["script_fetches"], closed["steps"]), (0, 0, 0))
        self.assertIn("closed by the block", closed["openings_basis"])
        self.assertEqual((base["openings"], base["script_fetches"]), (4, 1))
        block = self.result["arms"]["block"]["measures_in_test"]
        self.assertEqual((block["openings"]["total"], block["script_fetches"]["total"]), (2 * 15, 0))
        counts = self.result["pair_counts"]
        self.assertEqual(counts["openings"]["block opened fewer"], 16)
        self.assertEqual(counts["script_fetches"]["block fetched fewer"], 16)
        self.assertEqual(sum(counts["correctness"].values()), 16)

    def test_automatic_scores_are_secondary_with_every_disagreement_listed(self):
        failed = self.slot(self.result, self.failed)
        self.assertEqual(failed["automatic_verdict"], "failed")
        self.assertEqual([r["slot"] for r in self.result["disagreements"]], [failed["slot"]])
        self.assertCountEqual([r["slot"] for r in self.result["human_unscorable"]],
                              [self.batch.slots[i]["id"] for i in (self.unscorable, self.failed_unscorable)])
        wrong = next(r for r in self.result["slots"] if self.batch.kinds[r["index"]] == "wrong")
        self.assertEqual((wrong["automatic_verdict"], wrong["human_verdict"], wrong["counted"]), ("wrong", "not correct", 0))
        self.assertEqual(self.result["automatic_scoring"]["version"], 10)

    def test_no_clean_answer_is_listed_as_naming_its_arm(self):
        self.assertEqual(self.result["answers_naming_an_arm"], [])
        self.assertTrue(all(r["answer_names_an_arm"] is False for r in self.result["slots"] if r["code"]))

    def test_the_command_writes_both_outputs_once(self):
        output, table = self.root / "analysis.json", self.root / "analysis.tsv"
        argv = ["browser_use_fresh_analysis.py", "--bundle", str(self.bundle), "--output", str(output), "--table", str(table)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(analysis.main(self.study), 0)
        self.assertEqual(json.loads(output.read_text())["primary_test"]["p"], self.result["primary_test"]["p"])
        self.assertEqual(len(table.read_text().splitlines()), 33)
        self.assertIn('"decision"', out.getvalue())
        with mock.patch.object(sys, "argv", argv), self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                analysis.main(self.study)


class Known(Case):
    """A p-value known in closed form: in each of 8 strata the block's 2 of 2 against 0 of 2 has
    probability 1/6 under H0, and only it and its mirror are that unlikely, so p = 2 / 6^8."""

    def setUp(self):
        super().setUp()
        probe = fresh_batch.Batch(self.root / "probe", [])
        self.kinds = fresh_batch.kinds_with({i: "wrong" for i, s in enumerate(probe.slots) if s["condition"] == "baseline"})

    def test_eight_strata_of_two_right_against_two_wrong(self):
        self.make(self.kinds)
        primary = self.run_analysis()["primary_test"]
        self.assertTrue(all((s["block_correct"], s["block_trials"], s["baseline_correct"], s["baseline_trials"])
                            == (2, 2, 0, 2) for s in primary["strata"]))
        self.assertAlmostEqual(primary["p"], 2 / 6 ** 8, places=15)
        self.assertTrue(primary["decision"].startswith("difference claimed: the block arm"))


class Stopped(Case):
    def test_a_trial_clock_timeout_counts_zero_and_the_test_is_incomplete(self):
        self.make(fresh_batch.kinds_with({17: "timeout"}, ran=18))
        result = self.run_analysis()
        timeout = self.slot(result, 17)
        self.assertEqual((timeout["disposition"], timeout["in_test"], timeout["counted"]), ("timeout", True, 0))
        self.assertIn("trial clock", timeout["disposition_reason"])
        self.assertIsNone(timeout["steps"])
        primary = result["primary_test"]
        self.assertEqual((primary["slots_in_test"], primary["planned_slots"], primary["complete_against_plan"]),
                         (18, 32, False))
        self.assertEqual(Counter(r["disposition"] for r in primary["left_out"]), {"not started": 14})

    def test_a_short_timeout_or_an_infrastructure_error_is_a_technical_void(self):
        for kind, reason in (("short", "unclassified or infrastructure timeout"), ("infra", "infrastructure or unknown")):
            with self.subTest(kind=kind):
                self.root = Path(self.tmp.name) / kind
                self.bundle = self.root / "bundle"
                self.make(fresh_batch.kinds_with({6: kind}, ran=7))
                result = self.run_analysis()
                void = self.slot(result, 6)
                self.assertEqual((void["disposition"], void["in_test"], void["counted"]), ("technical void", False, None))
                self.assertIn(reason, void["disposition_reason"])
                self.assertIn(void["slot"], [r["slot"] for r in result["primary_test"]["left_out"]])
                self.assertEqual(result["primary_test"]["slots_in_test"], 6)

    def test_a_guard_interruption_is_a_void_whose_calls_are_still_charged(self):
        self.make(fresh_batch.kinds_with({10: "interrupted"}, ran=11))
        result = self.run_analysis()
        void, accounting = self.slot(result, 10), result["accounting"]["stages"][0]
        self.assertEqual((void["disposition"], void["openings"], void["script_fetches"], void["code"]),
                         ("technical void", None, None, None))
        self.assertIn("guard stopped", void["disposition_reason"])
        calls = 3 if self.batch.slots[10]["condition"] == "block" else 2
        self.assertEqual((accounting["calls_after_last_saved_record"], accounting["their_slot"]), (calls, void["slot"]))
        leftover = json.loads(Path(self.batch.config["ledger_path"]).read_text())["calls"][-calls:]
        self.assertAlmostEqual(void["charge_usd"], sum(c["cost_usd"] for c in leftover), places=12)
        ledger_total = json.loads(Path(self.batch.config["ledger_path"]).read_text())["charged_usd"]
        self.assertAlmostEqual(accounting["total_charge_usd"], ledger_total, places=12)
        self.assertAlmostEqual(result["accounting"]["total_charge_usd"], ledger_total, places=12)


class Unblinded(Case):
    def test_an_answer_naming_its_arm_is_listed_beside_its_verdict(self):
        def plant(batch):
            batch.edit(2, answer=f"Saved in {batch.slots[2]['id']}/agent-files/notes.pdf. The answer is $12.50.")
        self.make(fresh_batch.kinds_with({}), before_prepare=plant)
        listed = self.run_analysis()["answers_naming_an_arm"]
        self.assertEqual([(r["slot"], r["human_verdict"]) for r in listed], [(self.batch.slots[2]["id"], "correct")])


class Unknown(Case):
    def test_a_lost_listener_reading_or_an_unknown_charge_stays_unknown(self):
        def plant(batch):
            batch.edit(2, script_fetches={**json.loads(batch.path(2).read_text())["script_fetches"],
                                          "complete": False, "script_errors": ["RuntimeError"]})
            batch.edit(3, cost_usd=None)  # the adapter's null executor sum is not a fault
            ledger = json.loads(Path(batch.config["ledger_path"]).read_text())
            ledger["inflight"] = {"call-99999": {"reserved_usd": 0.2117632, "role": "executor", "requested_at": 1.0}}
            fresh_batch.put(batch.config["ledger_path"], ledger)
        self.make(fresh_batch.kinds_with({}), before_prepare=plant)
        result = self.run_analysis()
        lost = self.slot(result, 2)
        self.assertIsNone(lost["script_fetches"])
        self.assertIn("unknown, not zero", lost["script_fetches_basis"])
        arm = result["arms"][lost["condition"]]["measures_in_test"]["script_fetches"]
        self.assertEqual((arm["unknown"], arm["total"], arm["median"]), (1, None, None))
        pair = next(p for p in result["pairs"] if lost["slot"] in (p["block_slot"], p["baseline_slot"]))
        self.assertIsNone(pair["block_minus_baseline"]["script_fetches"])
        self.assertIsNotNone(self.slot(result, 3)["charge_usd"])
        accounting = result["accounting"]
        self.assertEqual((accounting["unsettled_requests"], accounting["total_charge_usd"]), (1, None))
        self.assertAlmostEqual(accounting["stages"][0]["reserved_bound_of_unknown_usd"], 0.2117632, places=12)


class FrozenCode(unittest.TestCase):
    def test_the_pins_are_the_repositorys_code(self):
        self.assertEqual(blind.digest(ROOT / "experiments/analysis/score.py"), analysis.SCORE_SHA256)
        for (name, function), wanted in analysis.FUNCTIONS.items():
            with self.subTest(function=function):
                self.assertEqual(analysis.function_digest(ROOT / name, function), wanted)

    def test_a_changed_function_moves_its_pin(self):
        source = (ROOT / "experiments/analysis/compare_cells.py").read_text()
        old = "return sum(p for p in dist.values() if p <= p_obs * (1 + 1e-9))"
        self.assertEqual(source.count(old), 1)
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / "compare_cells.py"
            changed.write_text(source.replace(old, "return 2 * p_obs"))
            self.assertNotEqual(analysis.function_digest(changed, "stratified_exact"),
                                analysis.FUNCTIONS[("experiments/analysis/compare_cells.py", "stratified_exact")])

    def test_changed_code_is_refused(self):
        config = {"hashes": {name: blind.digest(ROOT / name) for name in analysis.RAN_WITH}}
        analysis.frozen_code([config, config])  # quiet on the repository's own code
        with mock.patch.object(analysis, "SCORE_SHA256", "0" * 64), \
                self.assertRaisesRegex(analysis.Refused, "scorer changed"):
            analysis.frozen_code([config])
        for key in analysis.FUNCTIONS:
            with self.subTest(function=key[1]), mock.patch.dict(analysis.FUNCTIONS, {key: "0" * 64}), \
                    self.assertRaisesRegex(analysis.Refused, key[1] + " in .* changed"):
                analysis.frozen_code([config])
        # Every stage's own binding counts, not only attempt 1's.
        with self.assertRaisesRegex(analysis.Refused, "the file a stage ran with"):
            analysis.frozen_code([config, {"hashes": {**config["hashes"], "experiments/paths.py": "0" * 64}}])


class Faults(Case):
    """A count that disagrees with its own evidence is a fault, not a measurement."""

    def refused(self, plant, pattern):
        self.make(fresh_batch.kinds_with({}), before_prepare=plant)
        with self.assertRaisesRegex(analysis.Refused, pattern):
            self.run_analysis()

    def test_an_opened_count_without_its_navigations_is_refused(self):
        def plant(batch):
            trace = json.loads(batch.path(5).read_text())["trace"]
            batch.edit(5, trace={**trace, "opened": trace["opened"] + 1})
        self.refused(plant, "opened count")

    def test_a_navigation_to_a_page_outside_the_results_is_refused(self):
        def plant(batch):
            trace = json.loads(batch.path(5).read_text())["trace"]
            other = fresh_batch.SHOP + "/electronics.html"
            trace["navigation_events"].append({"url": other, "status": 200, "main_document": True, "page_id": "1",
                                               "candidate": True, "product_document": True, "counted": True})
            batch.edit(5, trace=trace)
        self.refused(plant, "navigation event")

    def test_a_script_fetch_count_without_its_events_is_refused(self):
        def plant(batch):
            seen = json.loads(batch.path(0).read_text())["script_fetches"]
            batch.edit(0, script_fetches={**seen, "script_fetched": seen["script_fetched"] + 1})
        self.refused(plant, "script-fetch count")

    def test_a_call_that_is_not_the_ledgers_is_refused(self):
        def plant(batch):
            # A baseline trial whose own sums agree with its changed call: only the ledger differs.
            record = json.loads(batch.path(7).read_text())
            assert record["condition"] == "baseline"
            record["calls"][0]["cost_usd"] += 0.01
            charged = sum(c["cost_usd"] for c in record["calls"])
            batch.edit(7, calls=record["calls"], total_cost_usd=charged, cost_usd=charged)
        self.refused(plant, "ledger's own")

    def test_a_ledger_total_that_is_not_its_calls_is_refused(self):
        def plant(batch):
            ledger = json.loads(Path(batch.config["ledger_path"]).read_text())
            fresh_batch.put(batch.config["ledger_path"], {**ledger, "charged_usd": ledger["charged_usd"] + 0.01})
        self.refused(plant, "charged total")

    def test_a_record_whose_own_sums_disagree_with_its_calls_is_refused(self):
        self.refused(lambda batch: batch.edit(9, total_cost_usd=1.0), "total_cost_usd")


# What each kind of trial is under the plan and amendments 2 to 4, written out here apart from
# the code under test (fresh_batch's kinds; a "short" timeout and an infrastructure error are the
# frozen classification's voids, an interrupted slot the guard's).
DISPOSITION = {"answered": "answered", "wrong": "answered", "answered-settled": "answered", "failed": "failed",
               "answered-error-reply": "answered", "void-error-reply": "technical void",
               "timeout": "timeout", "closed": blind.CLOSED, "void-settled": "technical void",
               "short": "technical void", "infra": "technical void", "interrupted": "technical void"}
# Attempt 2's frozen void sits in another question than its settled void, so the two voids'
# strata differ and a view that took one for the other would show it.
SECOND = ["timeout", "answered", "void-settled", "answered-settled", "wrong", "answered", "timeout"] \
    + ["answered"] * 9 + ["short"]


class Staged(Case):
    """Attempt 1 stopped on its interrupted fifth slot; attempt 2 ran 17 slots (two clock timeouts,
    a void and an answer after settled requests, two answers whose conversation holds "Full
    path:") and stopped on a frozen void; attempt 3 ran the 10 left, the last a clock timeout; the
    reruns ran the three timeouts once each, the second timing out again. The test grades one
    timeout correct (it still counts 0) and one answer unscorable."""

    def build(self, attempt3=True, rerun=True, second=SECOND, third=("answered",) * 9 + ("timeout",),
              reruns=("answered", "timeout", "answered"), unstarted_reason=None):
        self.batch = fresh_batch.Batch(self.root / "repo", ["answered"] * 4 + ["interrupted"])
        self.study = self.batch.study
        self.second = self.batch.later(blind.ATTEMPT2, second, full_path={1, 5})
        if attempt3:
            self.third = self.batch.later(blind.ATTEMPT3, list(third))
        if rerun:
            self.reruns = self.batch.later(blind.RERUN, list(reruns), unstarted_reason=unstarted_reason)
        blind.prepare(self.study, self.batch.stage_args(), self.bundle)
        stage2 = guard.FRESH_CONTINUATION_STAGE
        self.special = {(stage2, self.second.slots[0]["id"]): "correct",
                        (stage2, self.second.slots[7]["id"]): "unscorable"}
        self.grade(self.special)
        return self.run_analysis()

    def expected(self):
        """Each of the 32 slots, from the kinds alone: (task, arm, disposition, counted, timeout's
        rerun count or None, settled by no-response, settled by any, full path, graded unscorable)."""
        held, reruns = {}, {}
        for stage in self.batch.stages:
            for i, slot in enumerate(stage.slots):
                if i < len(stage.kinds) and stage.path(i).exists() or stage.path(i, ".interrupted.json").exists():
                    kind = stage.kinds[i]
                    (held if stage.spec.primary else reruns)[slot["id"]] = (stage, i, kind)
        rows = []
        for slot in self.batch.slots:
            stage, i, kind = held.get(slot["id"], (None, None, None))
            state = DISPOSITION[kind] if kind else "not started"
            grade = self.special.get((stage.spec.stage, slot["id"]) if stage and stage is not self.batch else None,
                                     "correct" if kind in CORRECT else "not correct")
            rerun = reruns.get(slot["id"])
            settling = stage is not None and stage.spec.stage in blind.SETTLING
            rows.append({"task": slot["question"]["id"], "condition": slot["condition"], "disposition": state,
                         "counted": int(state == "answered" and grade == "correct"),
                         "rerun": None if rerun is None else int(DISPOSITION[rerun[2]] == "answered"
                                                                   and rerun[2] in CORRECT),
                         "no_response": kind in ("answered-settled", "void-settled"),
                         "settled": kind in ("answered-settled", "void-settled") or (settling and kind == "timeout"),
                         "full_path": stage is self.second and i in (1, 5), "unscorable": grade == "unscorable"})
        return rows

    def strata(self, rows, keep, score=lambda r: r["counted"]):
        out = []
        for task in self.study.task_ids:
            stratum = []
            for arm in ("block", "baseline"):
                used = [r for r in rows if r["task"] == task and r["condition"] == arm and keep(r)]
                stratum += [sum(score(r) for r in used), len(used)]
            out.append(tuple(stratum))
        return out

    def check(self, view, strata):
        self.assertEqual([(s["block_correct"], s["block_trials"], s["baseline_correct"], s["baseline_trials"])
                          for s in view["strata"]], strata)
        self.assertAlmostEqual(view["p"], enumerated_p(strata), places=12)

    def test_every_view_of_the_staged_slots(self):
        result = self.build()
        rows = self.expected()
        ran = lambda r: r["disposition"] in ("answered", "failed", "timeout", blind.CLOSED)  # noqa: E731
        timeout = lambda r: r["disposition"] == "timeout"  # noqa: E731
        self.assertEqual([r["disposition"] for r in result["slots"]], [r["disposition"] for r in rows])
        self.assertEqual(Counter(r["disposition"] for r in rows), {"answered": 26, "timeout": 3, "technical void": 3})
        primary = result["primary_test"]
        self.check(primary, self.strata(rows, ran))
        self.assertEqual((primary["slots_in_test"], primary["complete_against_plan"]), (29, False))
        self.assertEqual(sorted(r["reason"].split(":")[0] for r in primary["left_out"]),
                         ["no answer after 1 request(s) with no response, settled at the bound; the frozen "
                          "classification", "the frozen classification",
                          "the guard stopped the slot while it ran (interrupted)"])
        views = result["sensitivities"]
        self.check(views["unscorable_left_out"], self.strata(rows, lambda r: ran(r) and not r["unscorable"]))
        self.check(views["timeouts_left_out"], self.strata(rows, lambda r: ran(r) and not timeout(r)))
        self.check(views["timeouts_replaced_by_rerun"],
                   self.strata(rows, ran, lambda r: r["rerun"] if timeout(r) else r["counted"]))
        self.check(views["voids_after_settlement_not_correct"],
                   self.strata(rows, lambda r: ran(r) or r["no_response"], lambda r: r["counted"] if ran(r) else 0))
        self.assertEqual({r["slot"] for r in views["voids_after_settlement_not_correct"]["left_out"]},
                         {self.batch.slots[4]["id"], self.second.slots[16]["id"]})  # the guard's and the frozen void
        self.check(views["settled_request_slots_left_out"], self.strata(rows, lambda r: ran(r) and not r["settled"]))
        self.check(views["no_response_slots_left_out"], self.strata(rows, lambda r: ran(r) and not r["no_response"]))
        self.check(views["full_path_slots_left_out"], self.strata(rows, lambda r: ran(r) and not r["full_path"]))
        # The views differ from the primary, so each one's arithmetic is really exercised.
        for name in ("timeouts_left_out", "settled_request_slots_left_out", "full_path_slots_left_out",
                     "voids_after_settlement_not_correct", "unscorable_left_out", "no_response_slots_left_out"):
            self.assertNotEqual(views[name]["slots_in_test"], primary["slots_in_test"], name)
        self.assertNotEqual(views["timeouts_replaced_by_rerun"]["block_correct_of_trials"]
                            + views["timeouts_replaced_by_rerun"]["baseline_correct_of_trials"],
                            primary["block_correct_of_trials"] + primary["baseline_correct_of_trials"])

    def test_timeouts_reruns_settlements_and_full_paths_are_listed(self):
        result = self.build()
        rows = self.expected()
        for arm in ("block", "baseline"):
            self.assertEqual(result["timeouts_per_arm"][arm]["timeouts"],
                             sum(r["disposition"] == "timeout" for r in rows if r["condition"] == arm))
        timed_out = [r for r in result["slots"] if r["disposition"] == "timeout"]
        graded = next(r for r in timed_out if r["human_verdict"] == "correct")
        self.assertEqual(graded["counted"], 0)  # a timeout scores 0 whatever its grade
        self.assertIn(graded["slot"], [r["slot"] for r in result["graded_but_decided_by_disposition"]])
        substituted = result["sensitivities"]["timeouts_replaced_by_rerun"]["substituted"]
        self.assertEqual([s["slot"] for s in substituted], [r["slot"] for r in timed_out])
        self.assertEqual([s["used"] for s in substituted], [1, 0, 1])
        self.assertTrue(all("5400 s" in s["label"] for s in substituted))
        reruns = result["reruns"]["trials"]
        self.assertEqual([(r["rerun"], r["clock_s"], r["disposition"]) for r in reruns],
                         [(True, 5400, "answered"), (True, 5400, "timeout"), (True, 5400, "answered")])
        self.assertEqual(sum(v["rerun"] for v in result["reruns"]["by_arm"].values()), 3)
        # Never pooled: the arms count only the 32 primary slots.
        self.assertEqual(sum(a["scheduled"] for a in result["arms"].values()), 32)
        voids = self.batch.slots[7]["id"]  # attempt 2's third slot, a void after a settled request
        self.assertEqual(result["sensitivities"]["voids_after_settlement_not_correct"]["counted_not_correct"], [voids])
        listed = {(r["slot"], r["stage"]) for r in result["settled_request_slots"]}
        settled = {(self.second.slots[i]["id"], "attempt 2") for i in (0, 2, 3, 6)}
        settled |= {(self.third.slots[9]["id"], "attempt 3")}
        settled |= {(self.reruns.slots[1]["id"], "timeout rerun")}  # the rerun that timed out again
        self.assertEqual(listed, settled)
        paths = result["full_path_slots"]
        self.assertEqual({r["slot"] for r in paths["slots"]}, {self.second.slots[i]["id"] for i in (1, 5)})
        self.assertEqual(paths["count_primary"], 2)
        self.assertEqual(sum(paths["by_arm_primary"].values()), 2)

    def test_each_stage_reconciles_with_its_own_ledger(self):
        result = self.build()
        stages = {a["stage"]: a for a in result["accounting"]["stages"]}
        self.assertEqual(list(stages), ["attempt 1", "attempt 2", "attempt 3", "timeout rerun"])
        # Each stage's share of the total cap, as its configuration bound it (amendment 4 point 6).
        self.assertEqual([a["shared_cap_usd"] for a in stages.values()], [3.0, 3.0, 10.0, 15.0])
        self.assertEqual(stages["attempt 1"]["their_slot"], self.batch.slots[4]["id"])
        self.assertEqual(stages["attempt 2"]["settled_calls"], 4)  # 2 clock, 2 no-response
        self.assertAlmostEqual(stages["attempt 2"]["settled_bound_usd"], 4 * fresh_batch.BOUND, places=12)
        self.assertIsNone(stages["attempt 2"]["total_charge_usd"])  # a settled request has no provider charge
        self.assertIsNotNone(stages["attempt 1"]["total_charge_usd"])
        for stage in self.batch.stages:
            ledger = json.loads(Path(stage.config["ledger_path"]).read_text())
            self.assertAlmostEqual(stages[stage.spec.name]["known_charge_usd"], ledger["charged_usd"], places=12)
        self.assertIsNone(result["accounting"]["total_charge_usd"])
        settled = next(r for r in result["slots"] if r["slot"] == self.second.slots[3]["id"])
        self.assertEqual((settled["charge_usd"], settled["settled_calls"], settled["no_response_settlements"]),
                         (None, 1, 1))
        self.assertIsNotNone(settled["charge_known_part_usd"])

    def test_a_rerun_the_deadline_left_no_time_for_keeps_its_primary_zero(self):
        # The rerun stage's deadline-fit check stopped it before its last slot (amendment 4 point 6).
        result = self.build(reruns=("answered", "timeout"), unstarted_reason=guard.NO_TIME_REASON)
        rows = self.expected()
        ran = lambda r: r["disposition"] in ("answered", "failed", "timeout", blind.CLOSED)  # noqa: E731
        view = result["sensitivities"]["timeouts_replaced_by_rerun"]
        self.check(view, self.strata(rows, ran, lambda r: r["rerun"] if r["disposition"] == "timeout"
                                     and r["rerun"] is not None else r["counted"]))
        last = view["substituted"][-1]
        self.assertEqual((last["rerun_disposition"], last["used"]), ("not started", None))
        self.assertIn(guard.NO_TIME_REASON, last["label"])
        self.assertIn("The primary timeout is kept, counted 0", last["label"])
        self.assertEqual([s["used"] for s in view["substituted"]], [1, 0, None])
        self.assertEqual(result["reruns"]["trials"][-1]["disposition"], "not started")

    def test_attempt_2_as_it_ended_its_interrupted_slot_is_a_void_charged_its_calls(self):
        result = self.build(second=["timeout", "answered", "answered", "timeout", "answered", "answered", "interrupted"], third=("answered",) * 20, reruns=("answered", "answered"))
        slot_id = self.second.slots[6]["id"]
        void = next(r for r in result["slots"] if r["slot"] == slot_id)
        self.assertEqual((void["stage"], void["disposition"], void["code"], void["in_test"]),
                         ("attempt 2", "technical void", None, False))
        self.assertIn("the guard stopped the slot while it ran (interrupted)", void["disposition_reason"])
        stages = {a["stage"]: a for a in result["accounting"]["stages"]}
        self.assertEqual(stages["attempt 2"]["their_slot"], slot_id)
        calls = 3 if self.second.slots[6]["condition"] == "block" else 2
        self.assertEqual(stages["attempt 2"]["calls_after_last_saved_record"], calls)
        self.assertEqual(void["provider_calls"], calls)  # its calls are charged to it, never dropped
        self.assertIn(slot_id, [r["slot"] for r in result["primary_test"]["left_out"]])
        self.assertEqual(result["primary_test"]["slots_in_test"], 4 + 6 + 20)
        self.assertEqual(result["timeouts_per_arm"]["block"]["timeouts"] + result["timeouts_per_arm"]["baseline"]["timeouts"], 2)

    def test_attempt_4s_error_reply_settlements_count_in_both_settled_views(self):
        # Amendment 6: attempt 3 left five slots, attempt 4 ran them, one answering after an error
        # reply without usage was settled and one failing after another, a void.
        self.batch = fresh_batch.Batch(self.root / "repo", ["answered"] * 4 + ["interrupted"])
        self.study = self.batch.study
        self.second = self.batch.later(blind.ATTEMPT2, SECOND, full_path={1, 5})
        self.third = self.batch.later(blind.ATTEMPT3, ["answered", "timeout", "answered", "interrupted"])
        fourth = self.batch.later(blind.ATTEMPT4, ["answered-error-reply", "answered", "timeout", "void-error-reply",
                                                   "answered", "answered"])
        self.batch.later(blind.RERUN, ["answered"] * 4)
        blind.prepare(self.study, self.batch.stage_args(), self.bundle)
        self.grade({})
        result = self.run_analysis()
        replied, void = fourth.slots[0]["id"], fourth.slots[3]["id"]
        row = next(r for r in result["slots"] if r["slot"] == replied)
        self.assertEqual((row["stage"], row["disposition"], row["error_reply_settlements"], row["no_response_settlements"]),
                         ("attempt 4", "answered", 1, 1))  # the runner counts it with the no-responses
        views = result["sensitivities"]
        for name in ("settled_request_slots_left_out", "no_response_slots_left_out"):
            self.assertIn(replied, [r["slot"] for r in views[name]["left_out"]], name)
        self.assertIn("error reply without usage", views["no_response_slots_left_out"]["role"])
        self.assertIn(void, views["voids_after_settlement_not_correct"]["counted_not_correct"])
        listed = {r["slot"]: r["error_reply_settlements"] for r in result["settled_request_slots"]}
        self.assertEqual((listed[replied], listed[void]), (1, 1))
        self.assertEqual(result["slots_run_by_stage"]["attempt 4"], 6)
        # Quiet elsewhere: no slot of attempts 1 to 3 has an error-reply settlement.
        self.assertTrue(all(r["error_reply_settlements"] == 0 for r in result["slots"] if r["stage"] != "attempt 4"))

    def test_without_reruns_the_timeouts_keep_their_zero_in_sensitivity_2(self):
        result = self.build(rerun=False)
        rows = self.expected()
        ran = lambda r: r["disposition"] in ("answered", "failed", "timeout", blind.CLOSED)  # noqa: E731
        view = result["sensitivities"]["timeouts_replaced_by_rerun"]
        self.check(view, self.strata(rows, ran))
        self.assertTrue(all(s["used"] is None and "it was not rerun" in s["label"] for s in view["substituted"]))
        self.assertEqual(result["reruns"]["trials"], [])

    def test_without_attempt_3_its_slots_are_not_started_and_the_test_incomplete(self):
        result = self.build(attempt3=False, rerun=False)  # no reruns before attempt 3 (point 6)
        left = Counter(r["disposition"] for r in result["primary_test"]["left_out"])
        self.assertEqual(left, {"technical void": 3, "not started": 10})
        self.assertEqual(result["primary_test"]["slots_in_test"], 19)
        self.assertEqual(result["slots_run_by_stage"], {"attempt 1": 5, "attempt 2": 17})

    def test_attempt_2_ran_everything_so_no_attempt_3(self):
        second = ["timeout"] + ["answered"] * 26
        result = self.build(attempt3=False, second=second)
        self.assertEqual(result["primary_test"]["slots_in_test"], 31)
        self.assertEqual([r["disposition"] for r in result["primary_test"]["left_out"]], ["technical void"])
        self.assertEqual(len(result["reruns"]["trials"]), 1)


if __name__ == "__main__":
    unittest.main()
