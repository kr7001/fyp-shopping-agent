"""The pilot's gate (24 October 2026): experiments/analysis/pilot_check.py's four rules, each
with a case where it fires and one where it stays quiet, its projection by hand, its proposed
fixes, and that it never reads whether an answer is right.

The pilot's batches are written here in the shape suite.py writes them (a suite.json and one
record per run), with a manifest in the chain's shape, in a folder of their own. Each fault
named was planted with a fresh bytecode cache and seen to fail its test (LESSONS 31, 39).
Nothing here calls a model or touches the shop.
"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import pilot_check  # noqa: E402
import stage_plan  # noqa: E402
import stage_stubs  # noqa: E402

DEEPSEEK = stage_stubs.DEEPSEEK
# The pilot's plan by the suite's arm names, as stage_plan fixes it.
PLAN = stage_plan.PILOT_PLAN
# A full run's figures, well within the limits of 300 steps and 1800 s.
QUIET = {"cost": 0.10, "calls": 40, "elapsed": 200.0}


class Pilot:
    """A pilot's results folder: batches written as suite.py writes them, and the manifest."""

    def __init__(self, folder: pathlib.Path):
        self.folder = folder
        self.analysis = stage_stubs.analysis_file()
        self.by_suite = stage_plan.arms_by_suite_name(self.analysis)
        self.dev = stage_stubs.task_file("Devbrand", held=False)
        self.claim = stage_stubs.task_file("Wexcombe", held=True)
        (folder / "experiments/tasks").mkdir(parents=True)
        for name, content in (("claim2_analysis.json", self.analysis), ("tasks_dev.json", self.dev),
                              ("tasks_claim.json", self.claim),
                              ("paraphrases_v2.json", stage_stubs.paraphrase_file(
                                  [(3, "tee-target-price"), (17, "water-target-price"), (27, "decline-delivery")])),
                              ("paraphrases_v3.json", stage_stubs.paraphrase_file([(1, "tee-xs-price"), (3, None)]))):
            (folder / "experiments/tasks" / name).write_text(json.dumps(content))
        self.lines = ["start 2026-10-24T10:00:00 usage 100.0000 cap 6.00"]
        self.n = 0

    def path(self, name: str) -> pathlib.Path:
        return self.folder / "experiments/tasks" / name

    def probe(self, charged: float = 0.012, rows: int = 30) -> None:
        path = self.folder / "parse-probe-paraphrases_v1-stub.json"
        path.write_text(json.dumps({"charged_usd": charged, "rows": [{"provider": "GMICloud"}] * rows}))
        self.lines.append(f"probe|{path}|model={DEEPSEEK} routing check")

    def batch(self, arm: str, task: str, **over) -> pathlib.Path:
        """One batch of one run under the suite arm `arm`, with `over` changing the run's
        cost, calls, elapsed, verdict, error, final, ok or limits."""
        self.n += 1
        folder = self.folder / f"2026102410{self.n:04d}"
        folder.mkdir()
        run = {**QUIET, "verdict": "correct", "error": None, "final": "an answer", "ok": True,
               "max_steps": 300, "clock_s": 1800, "record": True, **over}
        if run["record"]:
            (folder / f"{task}-1.json").write_text(json.dumps({
                "model": DEEPSEEK, "elapsed_s": run["elapsed"], "cost_usd": run["cost"], "max_steps": run["max_steps"],
                "clock_s": run["clock_s"], "error": run["error"], "result": {"ok": run["ok"], "final": run["final"]},
                "trace": {"tool_calls_total": run["calls"]}}))
        (folder / "suite.json").write_text(json.dumps({
            "arm": arm, "model": DEEPSEEK, "max_steps": run["max_steps"], "clock_s": run["clock_s"], "policy": "off",
            "tasks_file": "tasks_dev.json", "provider_routing": {"agent": None, "parser": None},
            "rows": [{"task": task, "repeat": 1, "verdict": run["verdict"], "cost_usd": run["cost"],
                      "tool_calls": run["calls"], "elapsed_s": run["elapsed"], "error": run["error"],
                      "answer": run["final"]}]}))
        self.lines.append(f"batch|{folder}|model={DEEPSEEK} arm={self.by_suite[arm]} round=1 --repeats 1 "
                          f"--repeat-start 1 --only {task}")
        return folder

    def whole(self, over: dict | None = None) -> None:
        """Every run of the pilot's plan, quiet unless `over` says otherwise."""
        for arm, tasks in PLAN.items():
            for task in tasks:
                self.batch(arm, task, **(over or {}).get((arm, task), {}))

    def end(self, usage: float = 101.2) -> None:
        self.lines.append(f"end 2026-10-24T10:40:00 usage {usage:.4f}")

    def manifest(self) -> pathlib.Path:
        path = self.folder / "pilot.manifest"
        path.write_text("\n".join(self.lines) + "\n")
        return path

    def check(self, cap: float = 69.0) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pilot_check.main(["--manifest", str(self.manifest()), "--protocol", str(self.path("claim2_analysis.json")),
                                     "--pilot-tasks", str(self.path("tasks_dev.json")),
                                     "--stage1-tasks", str(self.path("tasks_claim.json")), "--stage1-cap", str(cap),
                                     "--reading-files", str(self.path("paraphrases_v2.json")),
                                     str(self.path("paraphrases_v3.json"))])
        return code, out.getvalue()


class Rules(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.pilot = Pilot(pathlib.Path(folder.name))
        self.pilot.probe()

    def lines(self, out: str, n: int) -> str:
        return next(l for l in out.splitlines() if l.startswith(f"{n} "))

    def test_a_quiet_pilot_passes_every_rule_with_its_numbers(self):
        self.pilot.whole()
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.lines(out, 1), "1 PASS no harness error and no void: 12 runs, 0 void, 0 with a harness error")
        self.assertEqual(self.lines(out, 2), "2 PASS no run at or within 80% of its step or clock limit: the most steps 40 "
                                             "of 300, the longest 200 s of 1800; 0 runs at or within 80%")
        self.assertEqual(self.lines(out, 3), "3 PASS every answer to a keyed question keyable: 0 unscored rows among 11 "
                                             "on keyed questions; keyless declines excepted")
        self.assertIn("4 PASS the projected stage-1 cost within the stage-1 cap: projected $", self.lines(out, 4))
        self.assertIn("the pilot cost $1.2000 by its records, $1.2000 by the account", out)
        self.assertTrue(out.rstrip().endswith("verdict: PASS"))

    def test_rule_1_fires_on_a_void_and_on_a_harness_error(self):
        self.pilot.whole({("box-model", "tee-xs-price"): {"final": "", "ok": False,
                                                             "error": "model call failed, reason: 429"},
                            ("none", "tee-promo-check"): {"error": "RuntimeError: the runner fell over"}})
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 1)
        self.assertIn("1 FAIL no harness error and no void: 12 runs, 1 void, 2 with a harness error", out)
        self.assertIn("tee-xs-price-1: provider error, no final", out)
        self.assertIn("fix: look at the fault before stage 1; this rule proposes no change of limit or cap", out)
        # A limit marker is rule 2's, not a harness error.
        quiet = Pilot(self.pilot.folder / "again")
        quiet.probe()
        quiet.whole({("none", "tee-xs-price"): {"error": "max_iterations_reached", "final": "Max iterations reached without completion"}})
        quiet.end()
        self.assertIn("12 runs, 0 void, 0 with a harness error", quiet.check()[1])

    def test_rule_2_fires_at_80_percent_of_either_limit_and_proposes_both_raised(self):
        self.pilot.whole({("exhaustive-product", "tee-count-buyable"): {"calls": 240},
                            ("box-model", "tee-count-buyable"): {"elapsed": 1500.0}})
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 1)
        self.assertIn("2 FAIL no run at or within 80% of its step or clock limit: the most steps 240 of 300, the "
                      "longest 1500 s of 1800; 2 runs at or within 80%", out)
        self.assertIn("open everything (product) tee-count-buyable-1: 240 of 300 steps", out)
        self.assertIn("the block (model) tee-count-buyable-1: 1500 of 1800 s", out)
        # 240 / 0.8 = 300 -> 300; 1500 / 0.8 = 1875 -> 2100: the first multiples of 50 and 300.
        self.assertIn("fix: raise both limits for every arm alike, to --max-steps 300 --clock 2100", out)
        # Just under stays quiet: 239 of 300 and 1439 of 1800.
        quiet = Pilot(self.pilot.folder / "again")
        quiet.probe()
        quiet.whole({("exhaustive-product", "tee-count-buyable"): {"calls": 239, "elapsed": 1439.0}})
        quiet.end()
        self.assertIn("2 PASS", quiet.check()[1])

    def test_rule_2_never_lowers_a_limit(self):
        self.pilot.whole({("none", "tee-xs-price"): {"calls": 280}})
        self.pilot.end()
        _, out = self.pilot.check()
        self.assertIn("--max-steps 350 --clock 1800", out)
        # The clock alone fires: the step limit stays 300, never the 50 the quiet runs would give.
        clock = Pilot(self.pilot.folder / "clock")
        clock.probe()
        clock.whole({("none", "tee-xs-price"): {"elapsed": 1500.0}})
        clock.end()
        self.assertIn("--max-steps 300 --clock 2100", clock.check()[1])

    def test_rule_3_fires_on_an_unscored_keyed_row_and_excepts_the_keyless_declines(self):
        self.pilot.whole({("box-model", "tee-count-stocked"): {"verdict": "unscored"},
                            ("box-model", "decline-fit"): {"verdict": "unscored"}})
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 1)
        self.assertIn("3 FAIL every answer to a keyed question keyable: 1 unscored rows among 11 on keyed questions", out)
        self.assertIn("the block (model) tee-count-stocked-1", out)
        self.assertNotIn("decline-fit-1", out)
        self.assertIn("fix: give the task file's sidecar a key", out)
        # A closed slot, refused or asked, is not an unscored row.
        quiet = Pilot(self.pilot.folder / "again")
        quiet.probe()
        quiet.whole({("box-model", "tee-count-stocked"): {"verdict": "asked"}})
        quiet.end()
        self.assertIn("3 PASS", quiet.check()[1])

    def test_rule_4_prices_stage_1_by_arm_and_kind_with_the_fixed_rules(self):
        # Distinct costs by arm and kind, so each priced line can be checked by hand.
        costs = {("box-model", "tee-xs-price"): 0.30, ("box-model", "tee-cheapest-target"): 0.20,
                 ("box-model", "tee-count-buyable"): 0.50, ("box-model", "tee-count-stocked"): 0.10,
                 ("box-model", "tee-promo-check"): 0.04, ("box-model", "decline-fit"): 0.001,
                 ("box", "tee-xs-price"): 0.26, ("box", "tee-promo-check"): 0.03,
                 ("exhaustive-product", "tee-count-buyable"): 0.90, ("exhaustive-product", "tee-xs-price"): 0.70,
                 ("none", "tee-xs-price"): 0.12, ("none", "tee-promo-check"): 0.08}
        self.pilot.whole({pair: {"cost": cost} for pair, cost in costs.items()})
        self.pilot.end()
        code, out = self.pilot.check(cap=69.0)
        self.assertEqual(code, 0, out)
        # The means: box-model bound (0.30 + 0.20) / 2, count (0.50 + 0.10) / 2.
        self.assertIn("box-model            bound     $0.2500", out)
        self.assertIn("box-model            count     $0.3000", out)
        # Stage 1 (stage_stubs' design): shipped 13 templates x 3 rounds at its mean 0.10;
        # open everything 8 gated x 3 rounds at its dearest kind 0.90 (24 runs = $21.60);
        # the block (model) 13 x 3 + 12 held-out; the block (rules) likewise, by the rules.
        self.assertIn("shipped                      headline    3 x $0.1000 = $   0.30; d: shipped's mean", out)
        self.assertIn("open everything (product)    bound      15 x $0.7000 = $  10.50; measured", out)
        self.assertIn("open everything (product)    count       9 x $0.9000 = $   8.10; measured", out)
        self.assertIn("shipped                      bound      15 x $0.1200 = $   1.80; measured", out)
        self.assertIn("the block (model)            headline    4 x $0.0400 = $   0.16; a: headline as lookup", out)
        self.assertIn("the block (rules)            count      12 x $0.3000 = $   3.60; b: the block (model)'s (measured)", out)
        self.assertIn("the block (rules)            bound      20 x $0.2600 = $   5.20; measured", out)
        # The extras: the gate at the probe's charge, the reading tests at its charge per call
        # over the 4 entries the market keeps (v2's 3 and 27, v3's 1 and 3), and Haiku's.
        self.assertIn("routing gate: $0.0120", out)
        self.assertIn(f"reading tests, {DEEPSEEK} (4 entries at $0.00040 a call, from parse-probe-paraphrases_v1-stub.json): $0.0016", out)
        self.assertIn(f"from {stage_plan.HAIKU_PROBE}", out)
        total = sum(float(l.split("= $")[1].split(";")[0]) for l in out.splitlines() if "= $" in l)
        self.assertIn(f"runs ${total:.2f} over 165 questions", out)

    def test_rule_c_prices_an_unmeasured_open_everything_kind_by_its_dearest(self):
        for arm, tasks in PLAN.items():
            for task in tasks:
                if (arm, task) != ("exhaustive-product", "tee-xs-price"):
                    self.pilot.batch(arm, task, cost=0.90 if arm == "exhaustive-product" else 0.10)
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 0, out)
        self.assertIn("open everything (product)    bound      15 x $0.9000 = $  13.50; c: open everything's dearest kind", out)

    def test_rule_4_fires_over_the_cap_and_proposes_a_cap_or_fewer_rounds(self):
        self.pilot.whole({(arm, task): {"cost": 1.0} for arm, tasks in PLAN.items() for task in tasks})
        self.pilot.end()
        code, out = self.pilot.check(cap=69.0)
        self.assertEqual(code, 1)
        line = self.lines(out, 4)
        self.assertTrue(line.startswith("4 FAIL the projected stage-1 cost within the stage-1 cap: projected $165."), line)
        self.assertIn("fix: a stage-1 cap of $182.00 (the projection plus 10%, to the dollar); or fewer open-everything "
                      "rounds: without round 3 $157.", out)
        self.assertIn("without round 2 $149.", out)
        self.assertIn("without round 1 $141.", out)
        self.assertIn("a changed stage-1 command needs a new dry run and stamp before tap 2", out)

    def test_rule_4_fails_when_a_pair_cannot_be_priced(self):
        # No shipped run at all: every shipped question is unpriceable by rules a to e.
        for arm, tasks in PLAN.items():
            if arm != "none":
                for task in tasks:
                    self.pilot.batch(arm, task)
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 1)
        self.assertIn("unpriceable: shipped, headline (tee-headline)", out)
        self.assertIn("fix: price the unpriceable pairs by hand before stage 1", out)

    def test_an_invocation_that_wrote_no_batch_fails_rule_1(self):
        self.pilot.whole()
        self.pilot.lines.append(f"batch||model={DEEPSEEK} arm=shipped round=1 --repeats 1 --repeat-start 1 --only tee-headline")
        self.pilot.end()
        code, out = self.pilot.check()
        self.assertEqual(code, 1)
        self.assertIn("shipped: the invocation wrote no batch", out)

    def test_the_verdicts_of_right_and_wrong_change_nothing(self):
        self.pilot.whole()
        self.pilot.end()
        _, before = self.pilot.check()
        flipped = Pilot(self.pilot.folder / "flipped")
        flipped.probe()
        flipped.whole({(arm, task): {"verdict": "wrong", "final": "another answer"}
                         for arm, tasks in PLAN.items() for task in tasks})
        flipped.end()
        _, after = flipped.check()
        strip = lambda text: "\n".join(l for l in text.splitlines() if not l.startswith("pilot check v"))  # noqa: E731
        self.assertEqual(strip(before), strip(after))
        for word in ("correct", "wrong"):
            self.assertNotIn(word, before)

    def test_the_end_line_may_be_missing(self):
        self.pilot.whole()
        _, out = self.pilot.check()
        self.assertIn("the account's end figure not yet written", out)


if __name__ == "__main__":
    unittest.main()
