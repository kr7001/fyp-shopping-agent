"""The front door's pilot (23 October 2026): its task file of the development rewordings on
the development market, the generator's narrow exception that lets it be written, and the
task file's path in a batch's record, which every reader opens again.

The development rewordings are experiments/tasks/paraphrases_v1.json, in sample since the
model parser's prompt v2 was written from them, so their texts may be read here. The held-out
set, paraphrases_v2.json, is never opened by these tests. Each rule has a case where it fires
and one where it stays quiet, and each fault named was planted with a fresh bytecode cache
and seen to fail its test (LESSONS 31, 39). Nothing here calls a model or touches the shop.
"""
import argparse
import contextlib
import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import score  # noqa: E402
import suite  # noqa: E402
import voids  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402
from test_probe import PARAPHRASES_DIGEST  # noqa: E402

sys.path.insert(0, str(paths.REPO / "env"))
import generate_aplus_tasks as aplus_tasks  # noqa: E402

DEV = paths.FIXTURES / "aplus_dev.json"
DEV_TASKS = paths.TASKS / "tasks_aplus_dev.json"
DEV_READINGS = paths.TASKS / "readings_aplus_dev.json"
V1 = paths.TASKS / "paraphrases_v1.json"
PILOT = paths.PILOT_TASKS / "tasks_pilot_v1rw_larchmere.json"
PILOT_READINGS = paths.PILOT_TASKS / "readings_pilot_v1rw_larchmere.json"
# The development rewordings that are tasks, by id, and those that are not, with why in the
# file's _skipped: six do not keep their template's meaning, six reword a question this
# market does not ask of its tee, and two would be scored wrong by their template's key.
TASKED = [1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 19, 20]
SKIPPED = [10, 11, 17, 18, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


class PilotFile(unittest.TestCase):
    """The committed pilot files are what the one command writes, and hold what they say."""

    @classmethod
    def setUpClass(cls):
        cls.v1, cls.spec, cls.sidecar = load(V1), load(PILOT), load(PILOT_READINGS)
        cls.by = {task["id"]: task for task in cls.spec["tasks"]}

    def test_the_command_writes_the_committed_files_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks, readings = pathlib.Path(tmp) / PILOT.name, pathlib.Path(tmp) / PILOT_READINGS.name
            ran = subprocess.run([sys.executable, "env/generate_aplus_tasks.py", "--fixture",
                                  str(DEV.relative_to(paths.REPO)), "--out", str(tasks),
                                  "--readings-out", str(readings), "--rewordings", str(V1.relative_to(paths.REPO))],
                                 cwd=paths.REPO, check=True, capture_output=True, text=True)
            self.assertEqual(tasks.read_bytes(), PILOT.read_bytes())
            self.assertEqual(readings.read_bytes(), PILOT_READINGS.read_bytes())
        self.assertIn("(31 tasks)", ran.stdout)
        self.assertEqual(ran.stdout.count("skipped: rewording "), len(SKIPPED))

    def test_its_templates_and_market_are_the_development_markets(self):
        dev = load(DEV_TASKS)
        self.assertEqual(self.spec["tasks"][:15], dev["tasks"])
        for field in ("_environment", "base_url", "brand", "fixture", "_instance"):
            self.assertEqual(self.spec[field], dev[field], field)
        self.assertEqual(suite.draw_id(self.spec), suite.draw_id(dev))

    def test_every_development_rewording_is_a_task_or_skipped_with_why(self):
        rewordings = self.spec["tasks"][15:]
        self.assertEqual([task["rewording"] for task in rewordings], TASKED)
        self.assertEqual([task["id"] for task in rewordings], [f"pv1-{n:02d}" for n in TASKED])
        self.assertEqual([left["rewording"] for left in self.spec["_skipped"]], SKIPPED)
        self.assertTrue(all(left["why"] for left in self.spec["_skipped"]))
        self.assertEqual(sorted(TASKED + SKIPPED), [entry["id"] for entry in self.v1["paraphrases"]])

    def test_a_rewording_is_its_template_rebranded_with_its_keys(self):
        entries = {entry["id"]: entry for entry in self.v1["paraphrases"]}
        for task in self.spec["tasks"][15:]:
            entry, template = entries[task["rewording"]], self.by[task["template"]]
            with self.subTest(task=task["id"]):
                self.assertTrue(entry["meaning_kept"])
                self.assertEqual(task["template"], "tee-" + entry["template"][len("apparel-"):])
                for field in ("family", "product", "gated", "expect", "box"):
                    self.assertEqual(task[field], template[field], field)
                lead = template["query"].split(" . ", 1)[0]
                self.assertEqual(task["query"], f"{lead} . {entry['text'].replace('Thornwood', 'Larchmere')}")
        self.assertNotIn("Thornwood", json.dumps([task["query"] for task in self.spec["tasks"]]))

    def test_the_sidecar_keys_every_question_under_either_reading(self):
        committed = load(DEV_READINGS)
        buyable = self.sidecar["readings"]["buyable"]
        for task in self.spec["tasks"]:
            with self.subTest(task=task["id"]):
                if task["expect"]["kind"] == "none":
                    self.assertNotIn(task["id"], buyable)
                else:
                    self.assertEqual(buyable[task["id"]],
                                     committed["readings"]["buyable"][task.get("template", task["id"])])
        self.assertEqual(self.sidecar["two_readings"],
                         committed["two_readings"] + ["pv1-09", "pv1-12", "pv1-13", "pv1-14"])
        self.assertEqual(score.readings_for(PILOT), self.sidecar["readings"])
        # suite.py's check before a batch under the model parser finds a key for every
        # reading a run could be answered under (build_query stubbed, as in
        # test_aplus_market's Rewordings), and misses one when a rewording's is taken out.
        args = argparse.Namespace(parser="model", reading="menu")
        partial = copy.deepcopy(self.sidecar["readings"])
        del partial["buyable"]["pv1-07"]
        with mock.patch.object(suite, "build_query", return_value=("a query", {"box": None, "page": "a page"})):
            self.assertEqual(suite.unscorable(self.spec["tasks"], self.spec, args, self.sidecar["readings"]), [])
            missing = suite.unscorable(self.spec["tasks"], self.spec, args, partial)
        self.assertEqual(len(missing), 1)
        self.assertTrue(missing[0].startswith("pv1-07 under the buyable reading"), missing[0])


class DevelopmentSet(unittest.TestCase):
    """The development set is known by its entries' digest, and each rule that makes a task
    of one of its rewordings fires on a planted fault and stays quiet on the set as it is."""

    def setUp(self):
        self.v1 = load(V1)
        self.templates = aplus_tasks.tasks(load(DEV))

    def reworded(self, development: dict) -> tuple[list[dict], dict[int, str]]:
        tasks, skipped = aplus_tasks.development_reworded(self.templates, development, "Larchmere")
        return tasks, {left["rewording"]: left["why"] for left in skipped}

    def test_known_by_its_entries_and_never_by_its_name(self):
        self.assertEqual(aplus_tasks.DEVELOPMENT_DIGEST, PARAPHRASES_DIGEST)
        self.assertTrue(aplus_tasks.is_development(self.v1))
        edited = copy.deepcopy(self.v1)
        edited["paraphrases"][0]["text"] = edited["paraphrases"][0]["text"].replace("lowest", "least")
        self.assertFalse(aplus_tasks.is_development(edited))
        self.assertFalse(aplus_tasks.is_development({**self.v1, "paraphrases": self.v1["paraphrases"][:29]}))
        # Another set in the development set's shape is refused, not read as held out.
        with self.assertRaisesRegex(SystemExit, "not the development set"):
            aplus_tasks.rewordings_of(self.templates, edited, "Larchmere", 20)

    def test_a_rewording_whose_templates_key_does_not_fit_is_skipped(self):
        tasks, why = self.reworded(self.v1)
        for n in (11, 30):
            self.assertIn("key does not fit", why[n])
        self.assertFalse({11, 30} & {task["rewording"] for task in tasks})
        # Without the table both would be tasks: each keeps its template's meaning and maps.
        with mock.patch.dict(aplus_tasks.KEY_DOES_NOT_FIT, clear=True):
            tasks, why = self.reworded(self.v1)
        self.assertEqual(sorted({11, 30} & {task["rewording"] for task in tasks}), [11, 30])

    def test_a_rewording_that_changes_its_meaning_or_has_no_tee_template_is_skipped(self):
        _, why = self.reworded(self.v1)
        self.assertIn("does not keep its template's meaning", why[27])
        self.assertIn("asks no tee-named-pair", why[21])
        self.assertIn("asks no tee-exists-under-27", why[17])
        # Quiet when the meaning is kept and the template maps: 27 is then a task.
        kept = copy.deepcopy(self.v1)
        next(e for e in kept["paraphrases"] if e["id"] == 27)["meaning_kept"] = True
        tasks, _ = self.reworded(kept)
        self.assertIn(27, [task["rewording"] for task in tasks])

    def test_a_rewording_its_keys_may_not_fit_is_refused_by_its_id(self):
        for label, change, words in (
                ("names no Thornwood", lambda e: e.update(text=e["text"].replace("Thornwood", "Other")),
                 "does not name Thornwood"),
                ("its audit expected another plan", lambda e: e.update(audit_expected="survey"),
                 "for a person to decide"),
                ("its audit expected an ask", lambda e: e.update(audit_expected="ASK"),
                 "for a person to decide")):
            with self.subTest(fault=label):
                broken = copy.deepcopy(self.v1)
                change(next(e for e in broken["paraphrases"] if e["id"] == 3))
                with self.assertRaises(SystemExit) as raised:
                    self.reworded(broken)
                self.assertIn("rewording 3", str(raised.exception))
                self.assertIn(words, str(raised.exception))
        broken = copy.deepcopy(self.v1)
        broken["lead"] = "Go to {base}/ ."
        with self.assertRaisesRegex(SystemExit, "searches for no brand"):
            self.reworded(broken)


class OnlyIntoAPilot(unittest.TestCase):
    """The generator's guard (`refused`): the development rewordings go into a pilot's files
    in experiments/tasks/pilot/ on a development market, nowhere else under
    experiments/tasks/, and never into a claim market's task file. Every other set keeps the
    rule it had."""

    def setUp(self):
        self.fixture = load(DEV)

    def refused(self, out, readings, development=True, fixture=None):
        return aplus_tasks.refused(DEV, fixture or self.fixture, out, readings,
                                   rewordings=True, development=development)

    def test_a_pilots_files_may_hold_them(self):
        self.assertIsNone(self.refused(PILOT, PILOT_READINGS))
        with tempfile.TemporaryDirectory() as tmp:      # a test's, outside experiments/tasks/
            folder = pathlib.Path(tmp)
            self.assertIsNone(self.refused(folder / PILOT.name, folder / PILOT_READINGS.name))

    def test_anywhere_else_under_experiments_tasks_they_are_refused(self):
        for out, readings in ((DEV_TASKS, DEV_READINGS), (paths.TASKS / PILOT.name, PILOT_READINGS),
                              (paths.PILOT_TASKS / "deeper" / PILOT.name, PILOT_READINGS)):
            with self.subTest(out=str(out.relative_to(paths.TASKS))):
                self.assertIn("would put the development rewordings", self.refused(out, readings))

    def test_never_into_a_claim_markets(self):
        claim = copy.deepcopy(self.fixture)
        claim["_generated"]["phrasings"] = "claim"
        with tempfile.TemporaryDirectory() as tmp:
            elsewhere = (pathlib.Path(tmp) / "tasks_x.json", pathlib.Path(tmp) / "readings_x.json")
            for out, readings in ((PILOT, PILOT_READINGS), (DEV_TASKS, DEV_READINGS), elsewhere):
                self.assertIn("never go into a claim market", self.refused(out, readings, fixture=claim))
        # A claim market's held-out rewordings keep their rule: allowed there.
        self.assertIsNone(self.refused(DEV_TASKS, DEV_READINGS, development=False, fixture=claim))

    def test_any_other_set_is_held_to_the_held_out_rule_in_a_pilots_folder_too(self):
        self.assertIn("would put the held-out rewordings", self.refused(PILOT, PILOT_READINGS, development=False))

    def test_the_command_writes_only_into_a_pilots_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_folder = pathlib.Path(tmp)
            pilot = tasks_folder / "pilot"
            pilot.mkdir()

            def command(folder: pathlib.Path) -> int:
                argv = ["generate_aplus_tasks.py", "--fixture", str(DEV), "--out", str(folder / PILOT.name),
                        "--readings-out", str(folder / PILOT_READINGS.name), "--rewordings", str(V1)]
                with mock.patch.object(aplus_tasks, "TASKS", tasks_folder), \
                        mock.patch.object(aplus_tasks.paths, "PILOT_TASKS", pilot), \
                        mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                    return aplus_tasks.main()

            with self.assertRaises(SystemExit) as raised:
                command(tasks_folder)
            self.assertIn("would put the development rewordings", str(raised.exception))
            self.assertEqual([p.name for p in tasks_folder.iterdir()], ["pilot"])
            self.assertEqual(list(pilot.iterdir()), [])
            self.assertEqual(command(pilot), 0)
            self.assertEqual((pilot / PILOT.name).read_bytes(), PILOT.read_bytes())


class TheBatchRecordsWhereItsTaskFileIs(unittest.TestCase):
    """`suite.tasks_file_name`: a batch records its task file as its path under
    experiments/tasks/, which every reader opens again as paths.TASKS / tasks_file."""

    def test_a_file_directly_in_experiments_tasks_keeps_its_name(self):
        for path in sorted(paths.TASKS.glob("*.json")):
            with self.subTest(file=path.name):
                self.assertEqual(suite.tasks_file_name(path), path.name)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(suite.tasks_file_name(pathlib.Path(tmp) / "tasks_x.json"), "tasks_x.json")
            # A test's link to one of ours keeps its own name, as before.
            link = pathlib.Path(tmp) / "tasks_linked.json"
            link.symlink_to(PILOT)
            self.assertEqual(suite.tasks_file_name(link), "tasks_linked.json")

    def test_a_pilots_batch_records_a_path_its_readers_find(self):
        ran = run_suite("--tasks", str(PILOT), "--repeats", "1", "--only", "tee-headline")
        self.addCleanup(ran.owner.cleanup)
        self.assertEqual(ran.code, 0, ran.out)
        payload = json.loads((ran.batch / "suite.json").read_text())
        # The name alone, as a batch recorded it before, is a file no reader finds.
        self.assertFalse((paths.TASKS / PILOT.name).exists())
        self.assertEqual(payload["tasks_file"], "pilot/tasks_pilot_v1rw_larchmere.json")
        self.assertEqual(paths.TASKS / payload["tasks_file"], PILOT)
        self.assertEqual(score.readings_for(paths.TASKS / payload["tasks_file"]), load(PILOT_READINGS)["readings"])
        # A void's re-run names the file where it is.
        flags = voids.rerun_flags(ran.batch)
        self.assertIn("--tasks experiments/tasks/pilot/tasks_pilot_v1rw_larchmere.json --repeats 1", flags)


if __name__ == "__main__":
    unittest.main()
