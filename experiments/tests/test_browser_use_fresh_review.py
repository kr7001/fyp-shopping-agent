"""Study A's blind review (2 November 2026), on synthetic batches only: no trial data, model,
browser or shop. Each check is shown passing a good batch and refusing a planted fault."""
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
        self.assertEqual((blind.STUDY_A.study_id, blind.STUDY_A.stage), (guard.FRESH_BUDGET, guard.FRESH_STAGE))

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
        rows, _ = blind.prepare(self.batch.study, self.batch.config_path, self.batch.config_sha, self.bundle)
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
        self.assertEqual([v["outcome"] for v in key["off_sheet"].values()], [blind.CLOSED])
        self.assertEqual(sorted(v["outcome"] for v in key["codes"].values()).count("failed"), 1)
        for code, mapped in key["codes"].items():
            row = next(r for r in rows if r["code"] == code)
            task = transfer.TASK_IDS.index(mapped["task"])
            self.assertEqual(json.loads(row["key"]), {"kind": "price", "value": fresh_batch.price(task)})
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertEqual((manifest["rows"], manifest["slots_scheduled"], manifest["config_sha256"]),
                         (31, 32, self.batch.config_sha))

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
        rows, named = blind.prepare(self.batch.study, self.batch.config_path, self.batch.config_sha, self.bundle)
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
            blind.prepare(self.batch.study, self.batch.config_path, "0" * 64, self.bundle)
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
            blind.prepare(other, self.batch.config_path, self.batch.config_sha, self.bundle)

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
                self.refused("planned 32 slots")
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
        blind.prepare(self.study, self.batch.config_path, self.batch.config_sha, self.bundle)
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


if __name__ == "__main__":
    unittest.main()
