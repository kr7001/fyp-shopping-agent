"""Study A's blind review (2 November 2026), on synthetic batches only: no trial data, model,
browser or shop. Each check is shown passing a good batch and refusing a planted fault."""
from collections import Counter
import contextlib
import copy
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
sys.path.insert(0, str(ROOT / "tools"))
import fresh_batch  # noqa: E402
import browser_use_fresh_review as blind  # noqa: E402
import browser_use_transfer as transfer  # noqa: E402
import guarded_browser_use as guard  # noqa: E402


class StudyA(unittest.TestCase):
    """The real study's bindings, against the repository."""

    def test_pinned_files_are_the_committed_ones(self):
        for name, wanted in blind.STUDY_A.files.items():
            with self.subTest(name=name):
                self.assertEqual(blind.digest(ROOT / name), wanted)
        self.assertEqual(blind.digest(blind.RULES), blind.STUDY_A.rules_sha256)
        self.assertEqual(blind.STUDY_A.task_ids, transfer.TASK_IDS)
        self.assertEqual(blind.STUDY_A.study_id, guard.FRESH_BUDGET)
        # Attempts 1 and 2 ran under the commands the launcher pins; the later stages are named.
        self.assertEqual(blind.STUDY_A.pinned, {"attempt 1": guard.FRESH_ATTEMPT1_SHA256,
                                                "attempt 2": guard.FRESH_CONTINUATION_SHA256,
                                                "attempt 3": guard.FRESH_ATTEMPT3_SHA256})
        self.assertEqual([(s.stage, s.attempt, s.prefix) for s in blind.STAGES],
                         [(stage, attempt, guard.FRESH_PREFIX[stage]) for stage, attempt in (
                             (guard.FRESH_STAGE, 1), (guard.FRESH_CONTINUATION_STAGE, 2),
                             (guard.FRESH_ATTEMPT3_STAGE, 3), (guard.FRESH_ATTEMPT4_STAGE, 4),
                             (guard.FRESH_RERUN_STAGE, guard.FRESH_RERUN_ATTEMPT))])
        # Attempt 4 as amendment 6 names it, its records under the same settling rules.
        self.assertEqual((blind.ATTEMPT4.stage, blind.ATTEMPT4.prefix), ("fresh-market-attempt-4", "study-a-attempt4"))
        self.assertIn(blind.ATTEMPT4.stage, blind.SETTLING)
        self.assertEqual(blind.PRIMARY[-1], blind.ATTEMPT4)
        self.assertEqual(blind.ERROR_REPLY_STAGES, {blind.ATTEMPT4.stage, blind.RERUN.stage})

    def test_the_error_reply_label_is_the_launchers_and_the_runners(self):
        # The label is a literal in both files, so a change in either would leave this review behind.
        for name in ("tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py"):
            with self.subTest(name=name):
                self.assertIn(f'settlement_kind="{blind.ERROR_REPLY_KIND}"'
                              if name.startswith("tools") else f'== "{blind.ERROR_REPLY_KIND}"',
                              (ROOT / name).read_text())

    def test_rookmere_keys_do_not_depend_on_the_reading(self):
        tasks = json.loads((ROOT / blind.STUDY_A.tasks_file).read_text())
        readings = json.loads((ROOT / blind.STUDY_A.readings_file).read_text())
        expect = {task["id"]: task["expect"] for task in tasks["tasks"]}
        for task_id in blind.STUDY_A.task_ids:
            with self.subTest(task=task_id):
                self.assertNotIn(task_id, readings["two_readings"])
                self.assertEqual(readings["readings"]["buyable"][task_id], expect[task_id])
        # The questions with two readings do differ, so the check can fire.
        self.assertNotEqual(readings["readings"]["buyable"]["tee-count-stocked"], expect["tee-count-stocked"])

    def test_the_expected_schedule_is_the_runners_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            batch = fresh_batch.Batch(folder, [])
            made = blind.expected_slots(batch.questions, (1, 2), 2700)
            self.assertEqual(made, transfer.preview(batch.config)["slots"])
            self.assertEqual(len(made), 32)
            # Repeat 2 reverses repeat 1, so swapping the repeats changes the order.
            self.assertNotEqual(blind.expected_slots(batch.questions, (2, 1), 2700)[0]["condition"], made[0]["condition"])


class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.batch = fresh_batch.Batch(self.root / "repo", [])
        closed = fresh_batch.block_index(self.batch, "tee-top-3")
        self.kinds = fresh_batch.kinds_with({0: "failed", 5: "wrong", closed: "closed"})
        self.batch = self.rebuild(self.kinds)
        self.bundle = self.root / "bundle"

    def rebuild(self, kinds, **options):
        shutil.rmtree(self.root / "repo", ignore_errors=True)
        return fresh_batch.Batch(self.root / "repo", kinds, **options)

    def prepare(self):
        rows, _ = blind.prepare(self.batch.study, self.batch.stage_args(), self.bundle)
        return rows

    def refused(self, pattern):
        with self.assertRaisesRegex(blind.Refused, pattern):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_every_trial_the_agent_ran_is_a_blank_row_and_the_closure_is_off_the_sheet(self):
        self.assertEqual(self.prepare(), 31)
        rows = blind.review.read_sheet(self.bundle / self.batch.study.sheet)
        records = [json.loads(self.batch.path(i).read_text()) for i in range(32)]
        self.assertCountEqual([r["answer"] for r in rows],
                              [r["answer"] or "" for r in records if r["outcome"] != blind.CLOSED])
        self.assertTrue(any(r["answer"].startswith("Partial text") for r in rows))  # the failed trial's text
        self.assertEqual(len({r["code"] for r in rows}), 31)
        self.assertTrue(all(not r["hand_verdict"] and not r["note"] for r in rows))
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        self.assertEqual([v["outcome"] for v in key["off_sheet"]], [blind.CLOSED])
        self.assertEqual(sorted(v["outcome"] for v in key["codes"].values()).count("failed"), 1)
        for code, mapped in key["codes"].items():
            row = next(r for r in rows if r["code"] == code)
            task = transfer.TASK_IDS.index(mapped["task"])
            self.assertEqual(json.loads(row["key"]), {"kind": "price", "value": fresh_batch.price(task)})
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertEqual((manifest["rows"], manifest["trials_scheduled"], manifest["stages_sha256"]),
                         (31, 32, {"attempt 1": self.batch.config_sha}))

    def test_the_reader_shows_only_question_key_and_answer(self):
        self.prepare()
        html = (self.bundle / "review.html").read_text()
        payload = json.loads(html.split("const payload = ")[1].split(";\nconst columns")[0])
        self.assertEqual(set(payload), {"rows", "filename", "identity", "rules"})
        self.assertTrue(all(set(row) == set(blind.review.COLUMNS) for row in payload["rows"]))
        self.assertEqual(payload["rows"], blind.review.read_sheet(self.bundle / self.batch.study.sheet))
        self.assertTrue(payload["identity"].startswith(guard.FRESH_BUDGET + "-"))
        self.assertTrue(payload["rules"].startswith(blind.NOTE))
        for private in ("transfer-tee-", "-r1-block", "-r2-baseline", str(self.batch.results), "cost_usd",
                        "closed by the block", "The shop does not show that", "synthetic-head"):
            self.assertNotIn(private, html)
        self.assertNotIn("Literal </script>", html)
        self.assertIn("Literal \\u003c/script>", html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn("<code>private-arm-key.json</code>", html)
        self.assertNotIn("ask Codex", html)

    def test_rows_are_not_in_schedule_order(self):
        # A shuffle of 31 rows leaves the schedule's order with probability 1 / 31!.
        self.prepare()
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        order = [key["codes"][r["code"]]["slot"] for r in blind.review.read_sheet(self.bundle / self.batch.study.sheet)]
        self.assertNotEqual(order, [s["id"] for s in self.batch.slots if s["id"] in order])

    def test_an_answer_naming_its_arm_is_copied_unchanged_and_flagged(self):
        index = 3
        leaked = (f"Saved to {self.batch.results / self.batch.slots[index]['id']}/agent-files/report.pdf. "
                  "The answer is $13.75.")
        self.batch.edit(index, answer=leaked)
        rows, named = blind.prepare(self.batch.study, self.batch.stage_args(), self.bundle)
        self.assertEqual((rows, named), (31, 1))  # quiet on the 30 other answers
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        flagged = [v["slot"] for v in key["codes"].values() if v["answer_names_an_arm"]]
        self.assertEqual(flagged, [self.batch.slots[index]["id"]])
        self.assertIn(leaked, [r["answer"] for r in blind.review.read_sheet(self.bundle / self.batch.study.sheet)])
        for text, named in (("Westmere Threads at $12.50 (block 2 of the results)", False),
                            ("see transfer-tee-top-3-R2-BASELINE/agent-files", True)):
            self.assertEqual(bool(blind.ARM_LABEL.search(text)), named)

    def test_an_absent_answer_is_a_blank_row_with_no_verdict(self):
        self.batch.edit(0, answer=None)
        self.prepare()
        rows = blind.review.read_sheet(self.bundle / self.batch.study.sheet)
        self.assertEqual(sum(r["answer"] == "" for r in rows), 1)

    def test_the_bundle_is_never_drawn_again(self):
        self.prepare()
        before = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        with mock.patch.object(blind.secrets, "token_hex") as random:
            with self.assertRaisesRegex(blind.Refused, "already exists"):
                self.prepare()
            random.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.bundle.iterdir()})

    def test_another_configuration_or_an_unverified_batch_is_refused(self):
        with self.assertRaisesRegex(blind.Refused, "not the one named"):
            blind.prepare(self.batch.study, {"attempt 1": (self.batch.config_path, "0" * 64)}, self.bundle)
        pinned = blind.dataclasses.replace(self.batch.study, pinned={"attempt 1": "0" * 64})
        with self.assertRaisesRegex(blind.Refused, "not the configuration this study ran"):
            blind.prepare(pinned, self.batch.stage_args(), self.bundle)
        for name, change, pattern in (
                ("study-a.verification.json", {"verdict": "FAIL"}, "verifier"),
                ("study-a.approval.json", {"approved": False}, "approval"),
                ("study-a.launch.json", {"config_sha256": "0" * 64}, "launch claim"),
                ("study-a.status.json", {"status": "running"}, "not ended"),
                ("study-a.ledger.json", {"study_budget_id": guard.REPEAT_BUDGET}, "ledger")):
            with self.subTest(name=name):
                path = self.batch.notes / name
                original = path.read_bytes()
                fresh_batch.put(path, {**json.loads(original), **change})
                self.refused(pattern)
                path.write_bytes(original)
        self.assertEqual(self.prepare(), 31)

    def test_a_changed_frozen_file_or_study_is_refused(self):
        tasks = self.batch.repo / fresh_batch.TASKS_FILE
        original = tasks.read_bytes()
        tasks.write_bytes(original + b"\n")
        self.refused("not the frozen file")
        tasks.write_bytes(original)
        other = blind.dataclasses.replace(self.batch.study, repeats=(2, 3))
        with self.assertRaisesRegex(blind.Refused, "not this study's"):
            blind.prepare(other, self.batch.stage_args(), self.bundle)

    def test_a_key_that_depends_on_the_reading_is_refused(self):
        readings = json.loads((self.batch.repo / fresh_batch.READINGS_FILE).read_text())
        readings["readings"]["buyable"]["tee-top-3"] = {"kind": "price", "value": 99.0}
        self.batch = self.rebuild(self.kinds, readings=readings)
        self.refused("depends on its reading")

    def test_a_changed_schedule_is_refused(self):
        path = self.batch.results / "schedule.json"
        plan = json.loads(path.read_text())
        for slots in (plan["slots"][1:], plan["slots"] + plan["slots"][:1], plan["slots"][::-1],
                      [{**plan["slots"][0], "clock_s": 1800}] + plan["slots"][1:]):
            with self.subTest(slots=len(slots)):
                fresh_batch.put(path, {**plan, "slots": slots})
                self.refused("planned order")
        fresh_batch.put(path, plan)
        self.assertEqual(self.prepare(), 31)

    def test_a_record_that_is_not_its_slots_is_refused(self):
        index = 3
        original = self.batch.path(index).read_bytes()
        for change, pattern in (({"condition": "block" if self.batch.slots[index]["condition"] == "baseline" else "baseline"}, "scheduled slot"),
                                ({"market": {**fresh_batch.MARKET, "brand": "Quenby"}}, "scheduled slot"),
                                ({"config_sha256": "0" * 64}, "scheduled slot"),
                                ({"repeat": 3}, "scheduled slot"),
                                ({"sent_query": "Another question"}, "warning"),
                                ({"model": "another/model"}, "adapter"),
                                ({"browser_version": "157.0.0.1"}, "browser build"),
                                ({"answer": 12.5}, "answer value")):
            with self.subTest(change=change):
                self.batch.edit(index, **change)
                self.refused(pattern)
                self.batch.path(index).write_bytes(original)
        record = json.loads(original)
        self.batch.edit(index, settings={**record["settings"], "temperature": 0.7})
        self.refused("settings")

    def test_a_replayed_or_stray_trial_file_is_refused(self):
        self.batch = self.rebuild(fresh_batch.kinds_with({}, ran=20))
        shutil.copy(self.batch.path(0), self.batch.path(25))
        self.refused("replayed")
        self.batch.path(25).unlink()
        (self.batch.results / "notes.json").write_text("{}")
        self.refused("replayed")
        (self.batch.results / "notes.json").unlink()
        (self.batch.results / ".DS_Store").write_text("")  # the operating system's own file
        self.assertEqual(self.prepare(), 20)

    def test_slot_statuses_that_are_not_one_sequential_run_are_refused(self):
        self.batch = self.rebuild(fresh_batch.kinds_with({}, ran=20))
        path = self.batch.results / "slot-status.json"
        statuses = json.loads(path.read_text())
        # One slot at a time: only the slot after the last saved one can have been stopped.
        for changes in ({25: "interrupted"}, {5: "not_started"}, {25: "running"},
                        {20: "interrupted", 21: "interrupted"}):
            with self.subTest(changes=changes):
                changed = copy.deepcopy(statuses)
                for index, status in changes.items():
                    changed["slots"][self.batch.slots[index]["id"]]["status"] = status
                fresh_batch.put(path, changed)
                self.refused("one sequential run")
        changed = copy.deepcopy(statuses)
        changed["slots"][self.batch.slots[20]["id"]]["status"] = "interrupted"
        fresh_batch.put(path, changed)
        self.assertEqual(self.prepare(), 20)  # the good case: one slot stopped while it ran
        shutil.rmtree(self.bundle)
        fresh_batch.put(path, statuses)
        done = self.batch.results / "completed.json"
        listed = json.loads(done.read_text())
        fresh_batch.put(done, {**listed, "completed": listed["completed"][::-1]})
        self.refused("out of order")

    def test_a_batch_that_stopped_keeps_only_the_slots_that_ran(self):
        self.batch = self.rebuild(fresh_batch.kinds_with({17: "timeout"}, ran=18))
        self.assertEqual(self.prepare(), 18)
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        self.assertIn("timeout", [v["outcome"] for v in key["codes"].values()])
        self.assertTrue(all(v["slot"] in [s["id"] for s in self.batch.slots[:18]] for v in key["codes"].values()))

    def test_an_interrupted_slot_is_bound_but_not_a_row(self):
        self.batch = self.rebuild(fresh_batch.kinds_with({10: "interrupted"}, ran=11))
        self.assertEqual(self.prepare(), 10)
        key = json.loads((self.bundle / "private-arm-key.json").read_text())
        self.assertIn(str(self.batch.path(10, ".interrupted.json").resolve()), key["inputs"])
        self.assertNotIn(self.batch.slots[10]["id"], [v["slot"] for v in key["codes"].values()])

    def test_a_batch_where_nothing_ran_has_nothing_to_review(self):
        self.batch = self.rebuild([])
        self.refused("nothing to review")


class Validate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.batch = fresh_batch.Batch(self.root / "repo", fresh_batch.kinds_with({0: "failed"}))
        self.study, self.bundle = self.batch.study, self.root / "bundle"
        blind.prepare(self.study, self.batch.stage_args(), self.bundle)
        self.incoming = self.root / "download.csv"

    def rows(self):
        return blind.review.read_sheet(self.bundle / self.study.sheet)

    def download(self, rows):
        # As the reader page saves it, with a byte-order mark.
        self.incoming.write_text(blind.review.csv_text(rows), encoding="utf-8-sig", newline="")

    def test_an_incomplete_review_writes_no_receipt(self):
        rows = self.rows()
        rows[0]["hand_verdict"] = "correct"
        self.download(rows)
        self.assertEqual(blind.validate(self.study, self.bundle, self.incoming), (1, 32))
        with self.assertRaisesRegex(blind.Refused, "incomplete"):
            blind.validate(self.study, self.bundle, self.incoming, save=True)
        self.assertFalse((self.bundle / "validated").exists())

    def test_a_complete_review_is_validated_blind_and_kept_once(self):
        before = (self.bundle / self.study.sheet).read_bytes()
        rows = [{**r, "hand_verdict": ("correct", "not correct", "unscorable")[i % 3], "note": "Student note"}
                for i, r in enumerate(self.rows())]
        self.download(list(reversed(rows)))
        # Validation needs no private key, record, configuration, ledger or scorer.
        (self.bundle / "private-arm-key.json").unlink()
        shutil.rmtree(self.root / "repo")
        with mock.patch.object(blind.review.subprocess, "run", side_effect=AssertionError("no scoring")):
            self.assertEqual(blind.validate(self.study, self.bundle, self.incoming, save=True), (32, 32))
        self.assertEqual(blind.review.read_sheet(self.bundle / "validated/reviewed.csv"), rows)
        receipt = json.loads((self.bundle / "validated/validation.json").read_text())
        self.assertEqual((receipt["complete"], receipt["arm_key_read"], receipt["scored"], receipt["rows"]),
                         (True, False, False, 32))
        self.assertEqual((self.bundle / self.study.sheet).read_bytes(), before)
        with self.assertRaisesRegex(blind.Refused, "already exists"):
            blind.validate(self.study, self.bundle, self.incoming, save=True)

    def test_changed_columns_codes_and_verdicts_are_refused(self):
        rows = [{**r, "hand_verdict": "correct"} for r in self.rows()]
        cases = [rows[:-1], rows + [rows[-1]], [{**rows[0], "hand_verdict": "maybe"}, *rows[1:]]]
        for field in blind.review.IMMUTABLE:
            bad = copy.deepcopy(rows)
            bad[0][field] += " changed"
            cases.append(bad)
        for bad in cases:
            self.download(bad)
            with self.assertRaises(blind.Refused):
                blind.validate(self.study, self.bundle, self.incoming, save=True)
            self.assertFalse((self.bundle / "validated").exists())

    def test_a_changed_blank_sheet_or_another_studys_bundle_is_refused(self):
        self.download([{**r, "hand_verdict": "correct"} for r in self.rows()])
        sheet = self.bundle / self.study.sheet
        original = sheet.read_bytes()
        sheet.write_bytes(original + b"\n")
        with self.assertRaisesRegex(blind.Refused, "blank sheet changed"):
            blind.validate(self.study, self.bundle, self.incoming)
        sheet.write_bytes(original)
        other = blind.dataclasses.replace(self.study, study_id="another-study")
        with self.assertRaisesRegex(blind.Refused, "Not this study's"):
            blind.validate(other, self.bundle, self.incoming)

    def test_a_refusal_on_the_command_line_shows_no_answer_text(self):
        rows = self.rows()
        secret = next(r["answer"] for r in rows if r["answer"])
        bad = [{**r, "hand_verdict": "correct"} for r in rows]
        bad[0]["answer"] += " changed"
        self.download(bad)
        argv = ["browser_use_fresh_review.py", "validate", "--bundle", str(self.bundle), "--reviewed", str(self.incoming)]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(blind.main(self.study), 1)
        self.assertIn("refused", err.getvalue())
        self.assertNotIn(secret[:20], err.getvalue())


class Stages(unittest.TestCase):
    """Attempt 1 stopped on an interrupted fifth slot, as on 2 November; attempt 2 ran a clock
    timeout, a void and an answer after settled requests, then stopped on a frozen void; attempt
    3 ran what was left; and the timeout reruns ran each primary timeout once (amendments 3, 4)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"

    def build(self, attempt3=True, rerun=True, full_path=(), **attempt2):
        self.batch = fresh_batch.Batch(self.root / "repo", ["answered"] * 4 + ["interrupted"])
        kinds = attempt2.pop("kinds", ["timeout", "answered", "void-settled", "answered-settled", "wrong",
                                       "answered", "timeout"] + ["answered"] * 10 + ["short"])
        self.second = self.batch.later(blind.ATTEMPT2, kinds, full_path=full_path, **attempt2)
        if attempt3:
            self.third = self.batch.later(blind.ATTEMPT3, ["answered"] * 8 + ["timeout"])
        if rerun:
            self.reruns = self.batch.later(blind.RERUN, ["answered", "timeout", "answered"])
        return self.batch

    def prepare(self, stages=None):
        return blind.prepare(self.batch.study, stages or self.batch.stage_args(), self.bundle)

    def key(self):
        return json.loads((self.bundle / "private-arm-key.json").read_text())

    def test_every_stage_and_rerun_answer_is_on_one_sheet(self):
        self.build()
        rows, _ = self.prepare()
        saved = [(stage.spec.stage, slot["id"]) for stage in self.batch.stages for slot in stage.slots
                 if stage.path(stage.index(slot["id"])).exists()]
        self.assertEqual(rows, len(saved))  # no closure here, so every saved record is a row
        key = self.key()
        self.assertCountEqual([(v["stage"], v["slot"]) for v in key["codes"].values()], saved)
        self.assertEqual(sum(v["rerun"] for v in key["codes"].values()), 3)
        self.assertEqual({v["stage"] for v in key["codes"].values() if v["rerun"]}, {guard.FRESH_RERUN_STAGE})
        # The three timed-out primary slots, rerun once each in schedule order.
        reruns = [s["id"] for s in self.reruns.slots]
        order = [s["id"] for s in self.batch.slots]
        self.assertEqual(reruns, sorted(reruns, key=order.index))
        self.assertEqual(len(reruns), 3)
        # A failed, timed-out or voided trial keeps whatever text it recorded, as a row.
        outcomes = Counter(v["outcome"] for v in key["codes"].values())
        # Timeouts: attempt 2's two at the clock and its short one, attempt 3's, one rerun's.
        self.assertEqual((outcomes["timeout"], outcomes["failed"]), (5, 1))
        self.assertEqual(sum(v["disposition"] == "technical void" for v in key["codes"].values()), 1)
        self.assertEqual(set(key["stages"]), {"attempt 1", "attempt 2", "attempt 3", "timeout rerun"})
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertEqual(manifest["trials_scheduled"], 35)

    def test_the_sheet_and_reader_carry_no_stage_rerun_arm_or_outcome(self):
        self.build(full_path={1})
        self.prepare()
        sheet = (self.bundle / self.batch.study.sheet).read_text()
        html = (self.bundle / "review.html").read_text()
        payload = json.loads(html.split("const payload = ")[1].split(";\nconst columns")[0])
        self.assertTrue(all(set(row) == set(blind.review.COLUMNS) for row in payload["rows"]))
        rows_text = json.dumps(payload["rows"])
        forbidden = [guard.FRESH_STAGE, guard.FRESH_CONTINUATION_STAGE, guard.FRESH_ATTEMPT3_STAGE,
                     guard.FRESH_RERUN_STAGE, "study-a-", "transfer-tee-", "-r1-block", "-r2-baseline",
                     "technical void", "closed by the block", "settled", "cost_usd", "synthetic-head",
                     "Full path", str(self.batch.notes)]
        forbidden += [stage.config_sha for stage in self.batch.stages]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, sheet)
                self.assertNotIn(text, rows_text)
                self.assertNotIn(text, html.replace(blind.NOTE.replace("\n", "\\n"), ""))
        for word in ("rerun", "attempt", "timeout", "disposition", "answered", "failed"):
            self.assertNotIn(word, rows_text.lower().replace("literal", ""))
        # The rows are shuffled whole: with the shuffle replaced by a reversal, the reruns, built
        # last, come first, so they are mixed in with the primary rows, not appended.
        shutil.rmtree(self.bundle)

        class Reversal:
            def shuffle(self, rows):
                rows.reverse()
        with mock.patch.object(blind.secrets, "SystemRandom", Reversal):
            self.prepare()
        key = self.key()
        order = [key["codes"][row["code"]]["rerun"] for row in blind.review.read_sheet(self.bundle / self.batch.study.sheet)]
        self.assertEqual(order[:3], [True, True, True])

    def test_a_launched_stage_must_be_named(self):
        self.build()
        for left_out in ("attempt 2", "attempt 3", "timeout rerun"):
            with self.subTest(left_out=left_out):
                stages = {k: v for k, v in self.batch.stage_args().items() if k != left_out}
                with self.assertRaisesRegex(blind.Refused, f"{left_out} was launched"):
                    self.prepare(stages)
                self.assertFalse(self.bundle.exists())
        self.assertEqual(self.prepare()[0], 4 + 18 + 9 + 3)  # quiet when every stage is named

    def test_attempt_3_absent_or_stopped_before_its_worker(self):
        # Attempt 2 ran every slot it was given: no attempt 3, and the reruns follow attempt 2.
        self.build(attempt3=False, kinds=["timeout"] + ["answered"] * 26)
        rows, _ = self.prepare()
        self.assertEqual(rows, 4 + 27 + 1)
        shutil.rmtree(self.root)
        self.root.mkdir()
        # Attempt 3 refused before its worker started: its slots stay not started, no rows.
        self.build(attempt3=False, rerun=False)
        self.batch.later(blind.ATTEMPT3, [], before_worker=True)
        rows, _ = self.prepare()
        self.assertEqual(rows, 4 + 18)
        loaded = blind.load_study(self.batch.study, self.batch.stage_args())
        unstarted = [sid for sid, entry in loaded["held"].items() if entry["status"]["status"] == "not_started"]
        self.assertEqual(len(unstarted), 9)
        self.assertTrue(all(loaded["held"][sid]["spec"] is blind.ATTEMPT3 for sid in unstarted))
        # The launcher refused its balance check after its launch claim, before any status.
        shutil.rmtree(self.root)
        self.root.mkdir()
        self.build(attempt3=False, rerun=False)
        third = self.batch.later(blind.ATTEMPT3, [], before_worker="claim only")
        self.assertFalse(Path(third.config["status_path"]).exists())
        self.assertEqual(self.prepare()[0], 4 + 18)
        loaded = blind.load_study(self.batch.study, self.batch.stage_args())
        reasons = {entry["status"]["reason"] for entry in loaded["held"].values() if entry["spec"] is blind.ATTEMPT3}
        self.assertEqual(reasons, {"the launcher refused before its first trial: a launch claim and no status"})
        shutil.rmtree(self.bundle)
        fresh_batch.put(third.config["ledger_path"], {"calls": []})  # a ledger with no status: inspect it
        with self.assertRaisesRegex(blind.Refused, "no status"):
            self.prepare()

    def test_the_reruns_come_after_attempt_3_when_attempt_2_left_slots(self):
        # Amendment 4 point 6: attempt 2 left nine slots never started, so the reruns may start
        # only once attempt 3 has ended.
        self.build(attempt3=False)
        with self.assertRaisesRegex(blind.Refused, "reruns ran before the last attempt"):
            self.prepare()
        self.assertFalse(self.bundle.exists())
        shutil.rmtree(self.root)
        self.root.mkdir()
        self.build(attempt3=False, kinds=["timeout"] + ["answered"] * 26)  # attempt 2 left none
        self.assertEqual(self.prepare()[0], 4 + 27 + 1)

    def build4(self, attempt4=True, rerun=True):
        """Amendment 6: attempt 3 answered, then the guard stopped a slot (an error reply without
        usage), and five slots never started; attempt 4 runs those five, one after an error reply."""
        self.build(attempt3=False, rerun=False)
        self.third = self.batch.later(blind.ATTEMPT3, ["answered", "timeout", "answered", "interrupted"])
        if attempt4:
            self.fourth = self.batch.later(blind.ATTEMPT4, ["answered-error-reply", "answered", "timeout",
                                                            "void-error-reply", "answered"])
        if rerun:
            self.reruns = self.batch.later(blind.RERUN, ["answered"] * 4)

    def test_attempt_4_runs_exactly_attempt_3s_unstarted_slots(self):
        self.build4()
        rows, _ = self.prepare()
        self.assertEqual(rows, 4 + 18 + 3 + 5 + 4)  # every saved record; attempt 3's interrupted slot is not a row
        loaded = blind.load_study(self.batch.study, self.batch.stage_args())
        held = Counter(entry["spec"].name for entry in loaded["held"].values())
        self.assertEqual(held, {"attempt 1": 5, "attempt 2": 18, "attempt 3": 4, "attempt 4": 5})
        interrupted = self.third.slots[3]["id"]
        self.assertEqual((loaded["held"][interrupted]["spec"], loaded["held"][interrupted]["status"]["status"]),
                         (blind.ATTEMPT3, "interrupted"))  # a void that stays attempt 3's, never rerun
        self.assertEqual([s["id"] for s in self.fourth.slots], [s["id"] for s in self.third.slots[4:]])
        # The reruns are every primary timeout: attempt 2's two, attempt 3's and attempt 4's.
        self.assertEqual(Counter(row["stage"] for row in loaded["timeouts"]),
                         {guard.FRESH_CONTINUATION_STAGE: 2, guard.FRESH_ATTEMPT3_STAGE: 1, blind.ATTEMPT4.stage: 1})
        key = self.key()
        self.assertEqual(sum(v["stage"] == blind.ATTEMPT4.stage for v in key["codes"].values()), 5)

    def test_error_reply_settlements_are_held_to_the_calls_and_the_stage(self):
        self.build4()
        index = 0  # attempt 4's first slot answered after an error reply without usage
        record = json.loads(self.fourth.path(index).read_text())
        self.assertEqual((record["error_reply_settlements"], record["no_response_settlements"]), (1, 1))
        self.assertEqual(self.prepare()[0], 4 + 18 + 3 + 5 + 4)  # quiet as the runner writes it
        shutil.rmtree(self.bundle)
        original = self.fourth.path(index).read_bytes()
        for change in ({"error_reply_settlements": 0}, {"error_reply_settlements": None}):
            with self.subTest(change=change):
                self.fourth.edit(index, **change)
                with self.assertRaisesRegex(blind.Refused, "error-reply settlements"):
                    self.prepare()
                self.fourth.path(index).write_bytes(original)
        # An attempt 3 record may not carry the count: attempt 3 settled no error reply.
        self.third.edit(0, error_reply_settlements=0)
        with self.assertRaisesRegex(blind.Refused, "error-reply settlements"):
            self.prepare()

    def test_an_attempt_after_one_that_left_nothing_is_refused(self):
        # Attempt 2 ran every slot it was given, so an attempt 3 has nothing it may run.
        self.build(attempt3=False, rerun=False, kinds=["answered"] * 27)
        self.assertEqual(self.prepare()[0], 4 + 27)  # quiet without it
        shutil.rmtree(self.bundle)
        self.batch.later(blind.ATTEMPT3, [])
        with self.assertRaisesRegex(blind.Refused, "attempt 3 ran though the attempt before it left no slot"):
            self.prepare()

    def test_attempt_4_must_be_named_and_come_before_the_reruns(self):
        self.build4()
        stages = {k: v for k, v in self.batch.stage_args().items() if k != "attempt 4"}
        with self.assertRaisesRegex(blind.Refused, "attempt 4 was launched"):
            self.prepare(stages)
        shutil.rmtree(self.root)
        self.root.mkdir()
        self.build4(attempt4=False)  # the reruns ran with attempt 3's five slots never started
        with self.assertRaisesRegex(blind.Refused, "reruns ran before the last attempt"):
            self.prepare()
        self.assertFalse(self.bundle.exists())

    def test_reruns_absent_leave_the_timeouts_unrerun(self):
        self.build(rerun=False)
        rows, _ = self.prepare()
        self.assertEqual(rows, 4 + 18 + 9)
        self.assertFalse(any(v["rerun"] for v in self.key()["codes"].values()))

    def test_the_reruns_must_be_every_primary_timeout_once(self):
        self.build(rerun=False)
        derived = self.batch.later(blind.RERUN, [], bind=False).slots
        shutil.rmtree(self.batch.notes / "study-a-rerun.results")
        self.batch.stages.pop()
        for given in (derived[:-1], derived + derived[:1], derived[::-1]):
            with self.subTest(slots=[s["id"] for s in given]):
                self.batch.stages = self.batch.stages[:3]
                for name in ("results",):
                    shutil.rmtree(self.batch.notes / f"study-a-rerun.{name}", ignore_errors=True)
                stage = fresh_batch.Stage(self.batch, blind.RERUN, ["answered"] * len(given), given=given)
                self.batch.stages.append(stage)
                with self.assertRaisesRegex(blind.Refused, "slots this stage was given"):
                    self.prepare()

    def test_a_record_whose_disposition_or_settlements_differ_from_the_runner_is_refused(self):
        self.build(attempt3=False, rerun=False, bind=False)
        index = 0  # attempt 2's first slot, a clock timeout
        original = self.second.path(index).read_bytes()
        for change, pattern in (({"disposition": None}, "disposition differs"),
                                ({"disposition": "technical void"}, "disposition differs"),
                                ({"no_response_settlements": 1}, "settlement counts"),
                                ({"clock_settlements": 0}, "settlement counts"),
                                ({"attempt": 3}, "scheduled slot")):
            with self.subTest(change=change):
                self.second.edit(index, **change)
                with self.assertRaisesRegex(blind.Refused, pattern):
                    self.prepare()
                self.second.path(index).write_bytes(original)
        self.assertEqual(self.prepare()[0], 4 + 18)

    def test_a_file_a_later_stage_bound_may_not_change(self):
        self.build(attempt3=False, rerun=False)
        status = self.batch.notes / "study-a.status.json"
        fresh_batch.put(status, {**json.loads(status.read_text()), "note": "edited after attempt 2 was prepared"})
        with self.assertRaisesRegex(blind.Refused, "attempt 2: a file it bound has changed"):
            self.prepare()

    def test_a_rerun_record_names_the_primary_record_it_reruns(self):
        self.build()
        index = 0
        rerun_of = json.loads(self.reruns.path(index).read_text())["rerun_of"]
        self.reruns.edit(index, rerun_of={**rerun_of, "record_sha256": "0" * 64})
        with self.assertRaisesRegex(blind.Refused, "scheduled slot"):
            self.prepare()

    def test_the_command_line_names_each_stage_and_shows_no_answer(self):
        self.build()
        argv = ["browser_use_fresh_review.py", "prepare", "--bundle", str(self.bundle)]
        for flag, stage in (("--attempt1", "attempt 1"), ("--attempt2", "attempt 2"), ("--attempt3", "attempt 3"),
                            ("--rerun", "timeout rerun")):
            path, sha = self.batch.stage_args()[stage]
            argv += [flag, str(path), sha]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            self.assertEqual(blind.main(self.batch.study), 0)
        self.assertIn("Prepared 34 blank review rows", out.getvalue())
        self.assertNotIn("The answer is", out.getvalue())
        shutil.rmtree(self.bundle)
        err = io.StringIO()
        with mock.patch.object(sys, "argv", argv[:4] + argv[4:7]), contextlib.redirect_stderr(err):
            self.assertEqual(blind.main(self.batch.study), 1)  # attempt 1 alone: the later stages exist
        self.assertIn("attempt 2 was launched", err.getvalue())

    def test_attempt_2_as_it_ended_its_interrupted_slot_is_a_bound_void_not_a_row(self):
        # 2 November: four answers, two clock timeouts, then the guard stopped the seventh slot
        # (an account check failed), leaving its record as .interrupted.json and 20 not started.
        self.build(kinds=["timeout", "answered", "answered", "timeout", "answered", "answered", "interrupted"], attempt3=False, rerun=False)
        third = self.batch.later(blind.ATTEMPT3, ["answered"] * 20)
        reruns = self.batch.later(blind.RERUN, ["answered", "answered"])
        rows, _ = self.prepare()
        self.assertEqual(rows, 4 + 6 + 20 + 2)
        interrupted = self.second.path(6, ".interrupted.json")
        self.assertTrue(interrupted.exists())
        key = self.key()
        self.assertIn(str(interrupted.resolve()), key["inputs"])  # bound by its SHA-256
        slot_id = self.second.slots[6]["id"]
        self.assertNotIn(slot_id, [v["slot"] for v in key["codes"].values()])  # a void: no row to grade
        loaded = blind.load_study(self.batch.study, self.batch.stage_args())
        held = loaded["held"][slot_id]
        self.assertEqual((held["spec"], held["status"]["status"], held["record"] is None, held["interrupted"] is not None),
                         (blind.ATTEMPT2, "interrupted", True, True))
        self.assertEqual(len(third.slots), 20)
        self.assertEqual([s["id"] for s in reruns.slots], [self.second.slots[0]["id"], self.second.slots[3]["id"]])

    def test_full_path_in_a_conversation_is_flagged_in_the_private_key_only(self):
        self.build(full_path={1, 5})
        self.prepare()
        flagged = {(v["stage"], v["slot"]) for v in self.key()["codes"].values() if v["conversation"]["full_path"]}
        expected = {(guard.FRESH_CONTINUATION_STAGE, self.second.slots[i]["id"]) for i in (1, 5)}
        self.assertEqual(flagged, expected)  # quiet on every other conversation
        self.assertTrue(all(v["conversation"]["files"] == 2 for v in self.key()["codes"].values()))


if __name__ == "__main__":
    unittest.main()
