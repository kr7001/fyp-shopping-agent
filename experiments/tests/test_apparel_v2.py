"""The box v2 development batch's task file on Thornwood, `tasks_apparel_v2.json`.

Generated from the fixture by `env/generate_apparel_v2_tasks.py` (regeneration is checked
byte for byte in `test_catalogues.py`). Here: the pilot's six questions are carried over
unchanged and render the text the pilot's file renders, the market draw is the pilot's, the
generator's own checks fire on a planted fault, and each task's "box" field says what the
box does with it on a page built from the fixture, so a batch's box counts can be read off
the file before anything is spent. Nothing is fetched.
"""
import argparse
import copy
import json
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import box  # noqa: E402
import page  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402

sys.path.insert(0, str(paths.REPO / "env"))
import generate_apparel as apparel  # noqa: E402
import generate_apparel_v2_tasks as v2  # noqa: E402

V1 = paths.TASKS / "tasks_apparel.json"
V2 = paths.TASKS / "tasks_apparel_v2.json"
FIXTURE = paths.FIXTURES / "scaled_apparel.json"
REPEATS = 3


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def fixture_page(fixture: dict, base: str) -> page.Page:
    """The Thornwood results page as the box reads it, built from the fixture rather than
    fetched: each listing's seller, the price its card advertises (the cheapest in-stock
    variant, as Magento prints it) and the URL the shop gives its SKU. The dry run checks
    the live page says the same."""
    listings = [page.Listing(seller=f["seller"], title=f["name"],
                             url=f"{base}/{f['parent_sku'].lower()}.html",
                             advertised=apparel.from_price(f))
                for f in fixture["families"]]
    return page.Page(url=f"{base}/catalogsearch/result/?q={fixture['_generated']['brand']}",
                     listings=listings, total=len(listings), next_page=False)


class TaskFile(unittest.TestCase):
    def setUp(self):
        self.v1, self.spec, self.fixture = load(V1), load(V2), load(FIXTURE)
        self.base = self.spec["base_url"]
        self.page = fixture_page(self.fixture, self.base)

    def test_the_pilots_six_questions_come_first_and_unchanged(self):
        first = self.spec["tasks"][:len(self.v1["tasks"])]
        stripped = [{k: v for k, v in task.items() if k != "box"} for task in first]
        self.assertEqual(stripped, self.v1["tasks"])
        self.assertGreater(len(self.spec["tasks"]), len(self.v1["tasks"]))
        self.assertEqual(len({t["id"] for t in self.spec["tasks"]}), len(self.spec["tasks"]))

    def test_the_draw_is_the_pilots(self):
        # `_instance` and `_environment` are the fixture's own, so a batch on this file is
        # on the market draw of cells 1 to 5 and the pilot (LESSONS 7).
        self.assertEqual(suite.draw_id(self.spec), suite.draw_id(self.v1))
        self.assertEqual(self.spec["_instance"], self.fixture["_instance"])

    def test_the_readings_sidecar_carries_the_pilots_readings(self):
        self.assertEqual(score.readings_for(V2), score.readings_for(V1))
        self.assertNotEqual(score.readings_for(V2), {})

    def test_every_key_is_computed_and_the_generators_checks_fire(self):
        # Quiet on the fixture as it is.
        v2.keys(self.fixture)
        # A planted fault: the winner's size M sold out, so the cheapest buyable no longer
        # matches what `_instance` records, and the file must not be written.
        broken = copy.deepcopy(self.fixture)
        winner = next(f for f in broken["families"]
                      if f["parent_sku"] == broken["_instance"]["winner"]["sku"])
        next(v for v in winner["variants"] if v["option"] == "M")["qty"] = 0
        with self.assertRaises(SystemExit):
            v2.keys(broken)
        # A limit under which nobody sells the size, where exactly one must.
        limit = v2.LIMIT_YES
        try:
            v2.LIMIT_YES = v2.LIMIT_NO
            with self.assertRaises(SystemExit):
                v2.keys(self.fixture)
        finally:
            v2.LIMIT_YES = limit

    def test_the_comparison_pair_crosses_over_behind_the_menu(self):
        low, high = v2.comparison_pair(self.fixture["families"], "M")
        self.assertLess(apparel.from_price(low), apparel.from_price(high))
        self.assertGreater(apparel.buyable_price_for(low, "M"), apparel.buyable_price_for(high, "M"))
        for listing in (low, high):
            self.assertNotEqual(apparel.from_price(listing), apparel.buyable_price_for(listing, "M"))

    def question(self, task: dict) -> str:
        return task["query"].format(base=self.base)

    def decide(self, task: dict, reply: str | None = None) -> box.Decision:
        url = box.results_url(self.question(task), required=False)
        return box.decide(self.question(task), self.page if url else None, reply=reply)

    # What the box does since 20 October 2026 where it differs from the file's "box" field,
    # which records what the box did when the batch ran (box v6, form v4): a superlative on
    # an attribute the shop does not show is refused rather than planned by the fallback
    # (docs/content/box-v2-design.md, "Verification, five properties"). The file is the
    # frozen record of that batch, so the moved expectation lives here, dated.
    SINCE_20_OCT = {"apparel-softest": {"outcome": "refuse", "kind": None}}

    def expected_box(self, task: dict) -> dict:
        return self.SINCE_20_OCT.get(task["id"], task["box"])

    def test_the_box_does_what_each_task_expects(self):
        self.assertEqual(self.spec["tasks"][-3]["id"], "apparel-softest")
        self.assertEqual(self.spec["tasks"][-3]["box"], {"outcome": "fallback", "kind": "survey"})
        for task in self.spec["tasks"]:
            outcome, kind = self.expected_box(task)["outcome"], self.expected_box(task)["kind"]
            with self.subTest(task=task["id"], outcome=outcome):
                decision = self.decide(task)
                record = decision.record()
                if outcome == "plan":
                    self.assertEqual((decision.kind, record["asked"], record["fallback"],
                                      record["bypassed"], decision.refuse),
                                     (kind, False, False, False, None))
                    self.assertTrue(decision.query.startswith(self.question(task) + "\n\n"))
                elif outcome == "ask":
                    self.assertEqual((decision.query, decision.kind, record["asked"]),
                                     (None, None, True))
                    # A reading answers the "offer" question and plans it; nothing
                    # answers the ask for a price limit.
                    answered = self.decide(task, reply="menu")
                    self.assertEqual((answered.kind, answered.query is not None),
                                     (kind, kind is not None))
                elif outcome == "refuse":
                    self.assertTrue(decision.refuse)
                    self.assertEqual((decision.query, decision.kind), (None, None))
                elif outcome == "fallback":
                    self.assertEqual((decision.kind, record["fallback"], record["bypassed"]),
                                     (kind, True, False))
                    self.assertIsNotNone(decision.query)
                elif outcome == "bypass":
                    self.assertEqual((decision.bypass, decision.query, decision.page, decision.kind),
                                     (True, self.question(task), None, None))
                else:
                    self.fail(f"unknown outcome {outcome!r}")

    def expected_counts(self) -> tuple[dict, int, int]:
        """What the file's "box" fields say a batch of REPEATS repeats counts, and how many
        slots reach the agent without a reading and with one."""
        outcomes = [self.expected_box(t)["outcome"] for t in self.spec["tasks"]]
        answered = sum(1 for t in self.spec["tasks"]
                       if self.expected_box(t)["outcome"] == "ask" and self.expected_box(t)["kind"])
        counts = {"asked": outcomes.count("ask"), "refused": outcomes.count("refuse"),
                  "bypassed": outcomes.count("bypass"), "fallback": outcomes.count("fallback")}
        counts = {key: value * REPEATS for key, value in counts.items()}
        reach = sum(outcomes.count(key) for key in ("plan", "fallback", "bypass")) * REPEATS
        return counts, reach, reach + answered * REPEATS

    def test_a_batchs_box_counts_follow_from_the_file(self):
        counts, reach, reach_with_reading = self.expected_counts()
        total = len(self.spec["tasks"]) * REPEATS
        for reply, expected_reach in ((None, reach), ("menu", reach_with_reading)):
            with self.subTest(reading=reply):
                records = [self.decide(task, reply=reply).record() for task in self.spec["tasks"]]
                # The rows the paid loop would write: an asked or refused slot through
                # `asked_row`, every other slot carrying the box's record.
                rows = []
                for task, record in zip(self.spec["tasks"], records):
                    for repeat in range(1, REPEATS + 1):
                        rows.append(suite.asked_row(task, repeat, record) if record["query"] is None
                                    else {"box": record, "verdict": "correct"})
                self.assertEqual(suite.box_counts(rows), counts)
                self.assertEqual(suite.dry_summary(records, REPEATS),
                                 f"box: asked {counts['asked']}, refused {counts['refused']}, "
                                 f"bypassed {counts['bypassed']}, fallback {counts['fallback']}; "
                                 f"{expected_reach} of {total} runs would reach the agent")

    def test_the_six_old_questions_render_the_pilots_text(self):
        # The same page injected on both sides, so this is the text, not the fetch.
        url = box.results_url(self.question(self.v1["tasks"][0]))
        suite.PAGES[url] = self.page
        self.addCleanup(suite.PAGES.pop, url, None)
        by_id = {t["id"]: t for t in self.spec["tasks"]}
        for old in self.v1["tasks"]:
            for reading in (None, "menu", "buyable"):
                args = argparse.Namespace(box=True, reading=reading, targeting=False,
                                          exhaustive=False, confidence="off")
                with self.subTest(task=old["id"], reading=reading):
                    self.assertEqual(suite.build_query(by_id[old["id"]], self.spec, args)[0],
                                     suite.build_query(old, self.v1, args)[0])


class DrySummary(unittest.TestCase):
    """The dry run's last line under the box: the counts a batch would record and the slots
    that would reach the agent, so the task file's expectations can be checked for free."""

    def record(self, **over) -> dict:
        return {"asked": False, "refuse": None, "bypassed": False, "fallback": False,
                "query": "text", **over}

    def test_the_counts_and_the_reach(self):
        records = [self.record(asked=True, query=None), self.record(refuse="missing", query=None),
                   self.record(bypassed=True), self.record(fallback=True), self.record(),
                   self.record(asked=True, fallback=True, query=None)]
        self.assertEqual(suite.dry_summary(records, 2),
                         "box: asked 4, refused 2, bypassed 2, fallback 2; 6 of 12 runs would "
                         "reach the agent")

    def test_silent_without_the_box(self):
        self.assertIsNone(suite.dry_summary([None, None], 3))

    def test_the_dry_run_prints_it(self):
        # The two bypassed questions name no page, so nothing is fetched.
        command = [sys.executable, str(paths.EXPERIMENTS / "runners" / "suite.py"),
                   "--tasks", str(V2), "--repeats", "2", "--only", "bypass-poem", "bypass-capital",
                   "--dry-run"]
        run = subprocess.run(command + ["--box"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.endswith("box: asked 0, refused 0, bypassed 4, fallback 0; "
                                            "4 of 4 runs would reach the agent\n"), run.stdout[-200:])
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("box:", run.stdout)


if __name__ == "__main__":
    unittest.main()
