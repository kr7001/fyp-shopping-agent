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
        blind.prepare(self.study, self.batch.config_path, self.batch.config_sha, self.bundle)
        if grades is not False:
            self.grade(grades or {})

    def index(self, slot_id):
        return next(i for i, s in enumerate(self.batch.slots) if s["id"] == slot_id)

    def grade(self, special, save=True):
        """Answers of kind "answered" correct, the rest not correct, except `special` by index."""
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        rows = blind.review.read_sheet(self.bundle / self.study.sheet)
        for row in rows:
            index = self.index(key["codes"][row["code"]]["slot"])
            kind = self.batch.kinds[index]
            row["hand_verdict"] = special.get(index, "correct" if kind == "answered" else "not correct")
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
        with mock.patch.object(analysis.blind, "load_batch", side_effect=AssertionError("no batch read")):
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
        void, accounting = self.slot(result, 10), result["accounting"]
        self.assertEqual((void["disposition"], void["openings"], void["script_fetches"], void["code"]),
                         ("technical void", None, None, None))
        self.assertIn("guard stopped", void["disposition_reason"])
        calls = 3 if self.batch.slots[10]["condition"] == "block" else 2
        self.assertEqual((accounting["calls_after_last_saved_record"], accounting["their_slot"]), (calls, void["slot"]))
        leftover = json.loads(Path(self.batch.config["ledger_path"]).read_text())["calls"][-calls:]
        self.assertAlmostEqual(void["charge_usd"], sum(c["cost_usd"] for c in leftover), places=12)
        ledger_total = json.loads(Path(self.batch.config["ledger_path"]).read_text())["charged_usd"]
        self.assertAlmostEqual(accounting["total_charge_usd"], ledger_total, places=12)


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
        self.assertAlmostEqual(accounting["reserved_bound_of_unknown_usd"], 0.2117632, places=12)


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
        analysis.frozen_code(config)  # quiet on the repository's own code
        with mock.patch.object(analysis, "SCORE_SHA256", "0" * 64), \
                self.assertRaisesRegex(analysis.Refused, "scorer changed"):
            analysis.frozen_code(config)
        with mock.patch.dict(analysis.FUNCTIONS, {key: "0" * 64 for key in analysis.FUNCTIONS}), \
                self.assertRaisesRegex(analysis.Refused, "changed"):
            analysis.frozen_code(config)
        with self.assertRaisesRegex(analysis.Refused, "the file the batch ran with"):
            analysis.frozen_code({"hashes": {**config["hashes"], "experiments/paths.py": "0" * 64}})


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


if __name__ == "__main__":
    unittest.main()
