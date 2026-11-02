"""Study B's blind review and analysis under amendment 4 (2 November 2026), on synthetic stages
only: no result file, browser, model or API call. Each check is shown passing a good study and
refusing or flagging a planted fault."""
from collections import Counter
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import fresh_b_batch  # noqa: E402
import matched_briefing_fresh_review as review  # noqa: E402

frozen, voids = review.frozen, review.voids
MEASURED = {"opened": 2, "elapsed_s": 4, "answer_matches_suite": True, "answer": "3 listings.", "ok": True,
            "skus": ["a", "b"], "selections": []}


class Reversal:
    """A known permutation in place of the random shuffle."""

    def shuffle(self, rows):
        rows.reverse()


def readers():
    """The frozen trace readers patched as the frozen reader's own tests patch them."""
    return [mock.patch.object(review.verify_cells, "ground_truth", return_value={}),
            mock.patch.object(review.verify_cells, "fixture_for", return_value=Path("synthetic")),
            mock.patch.object(review.verify_cells, "market_urls", return_value=[]),
            mock.patch.object(review.verify_cells, "verify_run", return_value=MEASURED),
            mock.patch.object(review.claim, "answer_check", side_effect=lambda arms, order: {order[0]: "checked"})]


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"

    def build(self, kinds=None, continuation=False, rerun=False, ran=15, **options):
        shutil.rmtree(self.root / "repo", ignore_errors=True)
        self.b = fresh_b_batch.StudyB(self.root / "repo", kinds, ran=ran)
        patcher = mock.patch.object(paths, "TASKS", self.b.tasks_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        if continuation:
            self.b.continuation(**options)
        if rerun:
            self.b.rerun()
        return self.b

    def prepare(self, **stages):
        args = self.b.args()
        args.update(stages)
        return review.prepare(self.b.study, self.bundle, args.get("continuation"), args.get("timeout-rerun"))

    def key(self):
        return json.loads((self.bundle / "private-arm-key.json").read_text())

    def grade(self, special=None, save=True):
        """The test plays the student: answers of a correct run correct, the rest not correct,
        except `special`, by (stage, slot)."""
        special = special or {}
        key = self.key()
        rows = review.blind.review.read_sheet(self.bundle / self.b.study.sheet)
        for row in rows:
            mapped = key["codes"][row["code"]]
            prefix = {"primary": "P", "continuation": "C", "timeout-rerun": "R"}[mapped["stage"]]
            kind = self.b.kinds.get((prefix, mapped["slot"]), "answered")
            row["hand_verdict"] = special.get((mapped["stage"], mapped["slot"]),
                                              "correct" if kind == "answered" else "not correct")
        incoming = self.root / "download.csv"
        incoming.write_text(review.blind.review.csv_text(rows), encoding="utf-8-sig", newline="")
        if save:
            review.blind.validate(self.b.study, self.bundle, incoming, save=True)
        return incoming

    def analyse(self):
        patches = readers()
        for patch in patches:
            patch.start()
        try:
            return review.analyse(self.b.study, self.bundle)
        finally:
            for patch in patches:
                patch.stop()


class Slot16(Case):
    def test_slot_16_void_is_off_the_sheet_and_reported_with_its_evidence(self):
        self.build()
        rows, integrity = self.prepare()
        self.assertEqual(rows, 15)
        self.assertEqual((integrity["slots_checked"], integrity["slots_not_run"], integrity["one_preamble"]),
                         (list(range(1, 16)), [16], True))
        self.assertEqual(integrity["listings_in_briefing"], [45])
        self.assertNotIn(16, [v["slot"] for v in self.key()["codes"].values()])
        self.grade()
        result = self.analyse()
        slot16 = result["slot_16"]
        self.assertEqual((slot16["state"], slot16["ruling"]), (voids.VOID, None))
        self.assertFalse(slot16["partial_run"]["suite_written"])
        self.assertTrue(slot16["partial_run"]["results_folder"].endswith("started-16"))
        self.assertEqual(result["primary"]["per_arm"]["matched-briefing"]["in_table"], 7)
        self.assertEqual(result["primary"]["per_arm"]["full-block"]["in_table"], 8)
        pair = next(p for p in result["paired_by_task_repeat"] if (p["task"], p["repeat"]) == ("tee-count-buyable", 2))
        self.assertIn("not comparable", pair["comparable"])
        self.assertTrue(all(v is None for v in pair["full_block_minus_matched"].values()))
        # Slot 16 has no record: its charges come from its own run log only.
        self.assertEqual(result["charges"]["slots_without_a_record"],
                         [{"slot": 16, "logged_charges_usd": 0.1757, "logged_charged_calls": 1}])
        self.assertEqual(slot16["partial_run"]["run_logs"], ["experiments/results/started-16/tee-count-buyable-2.log"])

    def test_the_started_slots_run_log_is_bound_at_preparation(self):
        self.build()
        self.prepare()
        self.grade()
        log = self.b.results / "started-16/tee-count-buyable-2.log"
        log.write_text(log.read_text() + "a line added after preparation\n")
        with self.assertRaisesRegex(review.Refused, "bound at preparation changed"):
            self.analyse()

    def test_a_started_slot_whose_log_has_a_completion_without_its_charge_is_refused(self):
        self.build({"started_log": "CompletionUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30)\n"})
        with self.assertRaisesRegex(review.Refused, "started slot cannot be accounted"):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_slot_16_run_on_the_students_ruling_is_on_the_sheet_and_labelled(self):
        self.build(continuation=True, ruling="Run slot 16 again: the budget stop was ours.")
        rows, integrity = self.prepare()
        self.assertEqual(rows, 16)
        self.assertEqual(integrity["slots_checked"], list(range(1, 17)))
        mapped = next(v for v in self.key()["codes"].values() if v["slot"] == 16)
        self.assertEqual(mapped["stage"], "continuation")
        self.grade()
        result = self.analyse()
        self.assertEqual(result["slot_16"]["state"], "run again on the student's ruling, labelled")
        self.assertEqual(result["slot_16"]["ruling"], "Run slot 16 again: the budget stop was ours.")
        self.assertEqual(result["slot_16"]["stage"], "continuation")
        self.assertEqual(result["primary"]["per_arm"]["matched-briefing"]["in_table"], 8)

    def test_a_continuation_must_be_named_and_carry_the_ruling(self):
        self.build(continuation=True)
        with self.assertRaisesRegex(review.Refused, "continuation stage was launched"):
            review.prepare(self.b.study, self.bundle)
        self.build(continuation=True, ruling="  ")
        with self.assertRaisesRegex(review.Refused, "without the student's ruling"):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_a_continuation_that_replays_a_primary_slot_is_refused(self):
        b = self.build()
        b.later("continuation", [b.steps[3]], [b.run_line(b.schedule[2], prefix="C")],
                {"partial_run": review.guard.partial_run(b.root, json.loads(b.config_path.read_text()), b.status),
                 "partial_run_ruling": "yes"})
        with self.assertRaisesRegex(review.Refused, "replay a primary slot"):
            self.prepare()


class Reruns(Case):
    """Slots 7 and 14 reached their clock in the primary run, as on 2 November."""

    KINDS = {("P", 7): "timeout", ("P", 14): "timeout", ("P", 5): "closed", ("P", 2): "wrong", ("R", 14): "timeout"}

    def test_every_answer_on_one_sheet_with_reruns_under_random_codes(self):
        self.build(self.KINDS, continuation=True, rerun=True)
        rows, integrity = self.prepare()
        self.assertEqual(rows, 16 - 1 + 2)  # the closure off the sheet, both reruns on it
        key = self.key()
        self.assertEqual(sorted((v["slot"], v["rerun"]) for v in key["codes"].values() if v["rerun"]),
                         [(7, True), (14, True)])
        self.assertEqual([v["slot"] for v in key["off_sheet"]], [5])
        self.assertEqual(integrity["reruns_checked"], [7, 14])
        sheet = (self.bundle / self.b.study.sheet).read_text()
        html = (self.bundle / "review.html").read_text()
        payload = json.loads(html.split("const payload = ")[1].split(";\nconst columns")[0])
        rows_text = json.dumps(payload["rows"])
        forbidden = ["full-block", "matched-briefing", "box-model", "timeout-rerun", "continuation", "primary",
                     "P07", "R14", "C16", "slot", "cost", "task_timeout", str(self.b.results)]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, sheet)
                self.assertNotIn(text, rows_text)
        self.assertTrue(all(set(row) == set(review.blind.review.COLUMNS) for row in payload["rows"]))
        # The rows are shuffled whole: with the shuffle replaced by a reversal, the reruns, built
        # last, come first, so they are mixed in with the primary rows, not appended.
        shutil.rmtree(self.bundle)
        with mock.patch.object(review.blind.secrets, "SystemRandom", Reversal):
            self.prepare()
        key = self.key()
        rows = review.blind.review.read_sheet(self.bundle / self.b.study.sheet)
        self.assertEqual([key["codes"][row["code"]]["rerun"] for row in rows][:2], [True, True])

    def test_timeouts_and_both_sensitivities(self):
        self.build(self.KINDS, continuation=True, rerun=True)
        self.prepare()
        # The student grades slot 7's timeout correct: amendment 4 still scores it 0.
        self.grade({("primary", 7): "correct", ("primary", 3): "unscorable"})
        result = self.analyse()
        # Slot 7 is the matched briefing, slot 14 the full block (the frozen schedule).
        self.assertEqual({arm: v["slots"] for arm, v in result["timeouts_per_arm"].items()},
                         {"full-block": [14], "matched-briefing": [7]})
        primary = result["primary"]["per_task"]
        self.assertEqual(primary["tee-count-buyable"]["matched-briefing"]["correct"], 1)  # slot 16 only
        self.assertEqual(primary["tee-count-buyable"]["matched-briefing"]["timeouts"], 1)
        self.assertEqual(primary["tee-top-3"]["full-block"]["correct"], 0)  # closed 5, timed out 14
        self.assertEqual(primary["tee-top-3"]["full-block"]["closed"], 1)
        self.assertEqual(primary["tee-xs-price"]["matched-briefing"]["assessable"], 1)  # slot 3 unscorable
        listed = result["graded_correct_but_reported_not_correct"]
        self.assertEqual([(r["slot"], r["counted"]) for r in listed], [(7, 0)])
        sens1 = result["sensitivity_1_timeouts_left_out"]["per_task"]
        self.assertEqual(sens1["tee-count-buyable"]["matched-briefing"]["in_table"], 1)
        self.assertEqual(sens1["tee-top-3"]["full-block"]["in_table"], 1)
        sens2 = result["sensitivity_2_timeouts_replaced_by_rerun"]
        # Slot 7's rerun answered correctly; slot 14's rerun timed out again and counts 0.
        self.assertEqual(sens2["per_task"]["tee-count-buyable"]["matched-briefing"]["correct"], 2)
        self.assertEqual(sens2["per_task"]["tee-top-3"]["full-block"]["correct"], 0)
        self.assertEqual(sens2["per_task"]["tee-top-3"]["full-block"]["timeouts"], 1)
        self.assertEqual([(s["slot"], s["rerun_outcome"]) for s in sens2["substituted"]],
                         [(7, voids.ANSWERED), (14, voids.NOT_CORRECT)])
        self.assertTrue(all("3600 s" in s["used"] for s in sens2["substituted"]))
        # Never pooled: the reruns sit apart from the 16 slots.
        self.assertEqual(len(result["slots"]), 16)
        self.assertEqual([t["slot"] for t in result["reruns"]["trials"]], [7, 14])

    def test_without_reruns_sensitivity_2_keeps_each_timeout_at_zero(self):
        self.build(self.KINDS, continuation=True)
        self.prepare()
        self.grade()
        result = self.analyse()
        sens2 = result["sensitivity_2_timeouts_replaced_by_rerun"]
        self.assertEqual(sens2["per_arm"], result["primary"]["per_arm"])
        self.assertTrue(all("primary timeout kept" in s["used"] for s in sens2["substituted"]))

    def test_the_reruns_must_be_every_timeout_once_with_its_clock_doubled(self):
        b = self.build(self.KINDS, continuation=True)
        timeouts = review.guard.primary_timeouts(b.root, [str(b.manifest.relative_to(b.root)),
                                                         review.guard.LATER["continuation"]["manifest"]])
        self.assertEqual([row["slot"] for row in timeouts], [7, 14])
        by_slot = {s["slot"]: s for s in b.schedule}
        cases = [("only one", [timeouts[0]], 3600, timeouts[0], "every primary timeout"),
                 ("wrong primary", timeouts, 3600, timeouts[1], "timed-out primary run"),
                 ("clock kept", timeouts, 1800, timeouts[0], "doubled clock")]
        for label, rows, clock, named, pattern in cases:
            with self.subTest(label):
                if ("R", 7) in b.folders:
                    shutil.rmtree(b.folders.pop(("R", 7)))
                b.later("timeout-rerun", b.rerun_steps(rows), [b.run_line(by_slot[7], clock, "R", named["batch"])],
                        hashes=b.wrapper())
                with self.assertRaisesRegex(review.Refused, pattern):
                    self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_the_reruns_ran_through_the_reviewed_wrapper(self):
        b = self.build(self.KINDS, continuation=True, rerun=True)
        self.assertEqual(self.prepare()[0], 17)  # quiet on the reruns as the launcher builds them
        shutil.rmtree(self.bundle)
        timeouts = [step["rerun_of"] for step in json.loads(b.stages["timeout-rerun"][0].read_text())["steps"][1:]]
        frozen_steps = [{**step, "argv": [step["argv"][0], review.guard.FROZEN_RUNNER, *step["argv"][2:]]}
                        for step in b.rerun_steps(timeouts)]
        lines = (b.root / review.guard.LATER["timeout-rerun"]["manifest"]).read_text().splitlines()[2:-1]
        for label, steps, hashes in (("the frozen runner", frozen_steps, b.wrapper()),
                                     ("another wrapper", b.rerun_steps(timeouts), {review.guard.RERUN_RUNNER: "0" * 64}),
                                     ("no binding", b.rerun_steps(timeouts), {})):
            with self.subTest(label):
                b.later("timeout-rerun", steps, lines, hashes=hashes)
                with self.assertRaisesRegex(review.Refused, "reviewed wrapper"):
                    self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_a_rerun_line_whose_run_is_not_at_the_doubled_clock_is_refused_by_the_frozen_reader(self):
        b = self.build(self.KINDS, continuation=True, rerun=True)
        self.assertEqual(self.prepare()[0], 17)  # quiet on the reruns as run
        shutil.rmtree(self.bundle)
        # The rerun's own record says it ran at the primary run's 1800 s clock.
        record = next(p for p in b.folders[("R", 7)].glob("*.json") if p.name != "suite.json")
        record.write_text(json.dumps({**json.loads(record.read_text()), "clock_s": 1800}))
        with self.assertRaisesRegex(review.Refused, "frozen reader refused.*clock_s"):
            self.prepare()


class Integrity(Case):
    def test_the_code_run_is_the_code_the_primary_run_bound(self):
        self.build()
        self.assertEqual(self.prepare()[0], 15)  # quiet on the repository's own code
        shutil.rmtree(self.bundle)
        config = json.loads(self.b.config_path.read_text())
        for name in ("experiments/analysis/score.py", "tools/hand_review.html"):
            with self.subTest(name=name):
                changed = {**config, "hashes": {**config["hashes"], name: "0" * 64}}
                self.b.config_path.write_text(json.dumps(changed))
                study = review.dataclasses.replace(self.b.study, primary_sha256=fresh_b_batch.sha(self.b.config_path))
                with self.assertRaisesRegex(review.Refused, f"{name} is not the file"):
                    review.prepare(study, self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_rule_5_flags_a_second_preamble(self):
        kinds = {**Reruns.KINDS, ("R", 7, "preamble"): "Another briefing"}
        self.build(kinds, continuation=True, rerun=True)
        _, integrity = self.prepare()
        self.assertFalse(integrity["one_preamble"])
        self.assertEqual(len(integrity["preamble_sha256"]), 2)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertFalse(manifest["preamble_check"]["one_preamble"])  # recorded before the sheet is opened

    def test_reporting_rule_3_calls_one_answer_no_difference(self):
        kinds = {("P", 2): "wrong", ("P", 9): "wrong", ("P", 3): "wrong"}
        self.build(kinds, continuation=True)
        self.prepare()
        self.grade()
        result = self.analyse()
        cheapest = result["primary"]["per_task"]["tee-cheapest-target"]
        self.assertEqual((cheapest["full_block_minus_matched_correct"], cheapest["reading"]),
                         (2, "full block correct more often by 2"))
        xs = result["primary"]["per_task"]["tee-xs-price"]
        self.assertEqual((xs["full_block_minus_matched_correct"], xs["reading"]), (1, "no observable difference"))
        self.assertNotIn("p", json.dumps(result["primary"]["per_arm"]))

    def test_the_analysis_waits_for_a_validated_review_and_reads_no_key_before(self):
        self.build(continuation=True)
        self.prepare()
        reads = []
        real = review.blind.read_json

        def watched(path):
            reads.append(Path(path).name)
            return real(path)
        with mock.patch.object(review.blind, "read_json", side_effect=watched):
            with self.assertRaisesRegex(review.Refused, "No validated review"):
                review.analyse(self.b.study, self.bundle)
            self.grade(save=False)
            with self.assertRaisesRegex(review.Refused, "No validated review"):
                review.analyse(self.b.study, self.bundle)
        self.assertNotIn("private-arm-key.json", reads)

    def test_a_changed_run_after_preparation_is_refused(self):
        self.build(continuation=True)
        self.prepare()
        self.grade()
        record = next(self.b.folders[("P", 4)].glob("tee-*.json"))
        record.write_text(record.read_text() + " ")
        with self.assertRaisesRegex(review.Refused, "bound at preparation changed"):
            self.analyse()


class CommandLine(Case):
    def test_prepare_validate_and_analysis_from_the_command_line(self):
        self.build(Reruns.KINDS, continuation=True, rerun=True)
        argv = ["matched_briefing_fresh_review.py", "prepare", "--bundle", str(self.bundle)]
        for flag, stage in (("--continuation", "continuation"), ("--rerun", "timeout-rerun")):
            path, sha = self.b.stages[stage]
            argv += [flag, str(path), sha]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            self.assertEqual(review.main(self.b.study), 0)
        self.assertIn("Prepared 17 blank review rows", out.getvalue())
        self.assertIn("16 slots and 2 reruns carry 1 preamble_sha256 (one briefing)", out.getvalue())
        incoming = self.grade(save=False)
        output = self.root / "analysis.json"
        analysis = ["matched_briefing_fresh_review.py", "analysis", "--bundle", str(self.bundle), "--output", str(output)]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", analysis), contextlib.redirect_stderr(err):
            self.assertEqual(review.main(self.b.study), 1)  # before validation: refused
        self.assertIn("No validated review", err.getvalue())
        validate = ["matched_briefing_fresh_review.py", "validate", "--bundle", str(self.bundle),
                    "--reviewed", str(incoming), "--save"]
        with mock.patch.object(sys, "argv", validate), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(review.main(self.b.study), 0)
        patches = readers()
        for patch in patches:
            patch.start()
        try:
            with mock.patch.object(sys, "argv", analysis), contextlib.redirect_stdout(io.StringIO()) as shown:
                self.assertEqual(review.main(self.b.study), 0)
        finally:
            for patch in patches:
                patch.stop()
        result = json.loads(output.read_text())
        self.assertEqual(result["timeouts_per_arm"]["full-block"]["slots"], [14])
        self.assertNotIn("listings can sell", shown.getvalue())  # no answer text printed


class SameAsFrozen(Case):
    def test_each_runs_measurements_are_the_frozen_analysis_own(self):
        """On a complete 16-slot study the per-run items equal matched_briefing_analysis.analyse's,
        so the two cannot drift."""
        self.build({("P", 5): "closed", ("P", 2): "wrong"}, continuation=True)
        self.prepare()
        self.grade()
        result = self.analyse()
        loaded = review.load_study(self.b.study, self.b.stages["continuation"])
        study = {"config": loaded["protocol"], "runs": loaded["runs"], "spec": loaded["spec"],
                 "tasks": {t["id"]: t for t in loaded["spec"]["tasks"]}, "ended": True, "stops": [],
                 "protocol_sha256": "", "manifest_sha256": "", "tasks_sha256": ""}
        key = self.key()
        human = {r["code"]: r for r in review.blind.review.read_sheet(self.bundle / "validated/reviewed.csv")}
        hand = {v["slot"]: {"code": c, "hand_verdict": human[c]["hand_verdict"], "note": human[c]["note"]}
                for c, v in key["codes"].items()}
        patches = readers()
        for patch in patches:
            patch.start()
        try:
            expected = frozen.analyse(study, hand)
        finally:
            for patch in patches:
                patch.stop()
        theirs = {item["slot"]: item for pair in expected["paired_by_task_repeat"] for item in pair["arms"].values()}
        for item in result["slots"]:
            with self.subTest(slot=item["slot"]):
                self.assertEqual({k: item[k] for k in theirs[item["slot"]]}, theirs[item["slot"]])
        self.assertEqual(Counter(len(p["arms"]) for p in expected["paired_by_task_repeat"]), {2: 8})


if __name__ == "__main__":
    unittest.main()
