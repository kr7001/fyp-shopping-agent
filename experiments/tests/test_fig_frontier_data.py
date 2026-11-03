"""Free checks for tools/fig_frontier_data.py, the data and TikZ of the report's Figure 6.

Written 3 November 2026 with the redrawn figure. Each check in the script has a test where it
must fire on a planted fault and one where it must stay quiet. The last class reads the stored
analysis files and is skipped where the private ones are not on the machine.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / "tools/fig_frontier_data.py"
spec = importlib.util.spec_from_file_location("fig_frontier_data", MODULE)
fig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fig)

H3 = [f"q{i}" for i in range(1, 9)]


def run(arm, task, repeat=1, cost=0.01, closed=False):
    return {"arm": arm, "task": task, "repeat": repeat, "cost": cost, "closed": closed}


def study(shipped_questions, repeats=(1, 2)):
    runs = [run(arm, q, r, cost=0.01 * (i + 1) + 0.001 * r)
            for i, arm in enumerate(fig.ARMS) for q in (shipped_questions if arm == "shipped" else H3)
            for r in repeats]
    return {"name": "Synthetic", "runs": runs,
            "h3": {"questions": H3, "block": 0.0115, "exhaustive": 0.0315}}


class PlottedSet(unittest.TestCase):
    def test_quiet_when_the_shipped_agent_ran_most_questions(self):
        ran = {"block": set(H3), "shipped": set(H3[:6]), "exhaustive": set(H3)}
        self.assertEqual(fig.plotted_set(H3, ran), (H3[:6], []))

    def test_quiet_when_every_arm_ran_every_question(self):
        ran = {arm: set(H3) for arm in fig.ARMS}
        self.assertEqual(fig.plotted_set(H3, ran), (H3, []))

    def test_fires_when_the_common_set_falls_below_half(self):
        ran = {"block": set(H3), "shipped": set(H3[:3]), "exhaustive": set(H3)}
        self.assertEqual(fig.plotted_set(H3, ran), (H3, ["shipped"]))

    def test_never_leaves_out_the_block(self):
        ran = {"block": set(H3[:2]), "shipped": set(H3), "exhaustive": set(H3)}
        questions, left_out = fig.plotted_set(H3, ran)
        self.assertNotIn("block", left_out)
        self.assertEqual(questions, H3[:2])


class Checks(unittest.TestCase):
    def test_table19_quiet_on_equal_medians(self):
        fig.check_table19({"block": {"median": 0.049683}, "exhaustive": {"median": 0.221002}},
                          {"block": 0.049683, "exhaustive": 0.221002})

    def test_table19_fires_on_a_rounded_median(self):
        with self.assertRaisesRegex(ValueError, "Table 19"):
            fig.check_table19({"block": {"median": 0.0497}, "exhaustive": {"median": 0.221002}},
                              {"block": 0.049683, "exhaustive": 0.221002})

    def test_grid_quiet_on_a_complete_grid(self):
        fig.check_grid(study(H3)["runs"], fig.ARMS, H3)

    def test_grid_fires_on_a_missing_repeat(self):
        runs = [r for r in study(H3)["runs"] if not (r["arm"] == "shipped" and r["task"] == "q4" and r["repeat"] == 2)]
        with self.assertRaisesRegex(ValueError, "repeats"):
            fig.check_grid(runs, fig.ARMS, H3)

    def test_index_fires_on_a_repeat_counted_twice(self):
        with self.assertRaisesRegex(ValueError, "twice"):
            fig.index([run("block", "q1"), run("block", "q1")])

    def test_charge_group_on_the_whole_set_checks_table19(self):
        group = fig.charge_group(study(H3))
        self.assertTrue(group["whole"])
        self.assertEqual({a: v["n"] for a, v in group["values"].items()}, {a: 16 for a in fig.ARMS})
        planted = study(H3)
        planted["h3"]["block"] = 0.5
        with self.assertRaisesRegex(ValueError, "Table 19"):
            fig.charge_group(planted)

    def test_charge_group_on_a_smaller_set_does_not_check_table19(self):
        planted = study(H3[:6])
        planted["h3"]["exhaustive"] = 0.5  # would fire if the set were the whole H3 set
        group = fig.charge_group(planted)
        self.assertEqual(group["questions"], H3[:6])
        self.assertFalse(group["whole"])

    def test_a_closed_slot_has_no_charge(self):
        planted = study(H3)
        planted["runs"][0]["closed"] = True
        planted["h3"]["block"] = fig.median([r["cost"] for r in planted["runs"][1:] if r["arm"] == "block"])
        group = fig.charge_group(planted)
        self.assertEqual((group["values"]["block"]["n"], group["values"]["block"]["closed"]), (15, 1))


class Claim2Sources(unittest.TestCase):
    """The private analysis must be the one the release came from, and agree with it run for run."""

    MODEL = "deepseek/deepseek-v4-flash"
    PROTOCOL = "experiments/tasks/claim2_replication_28_oct.json"
    ARMS = {"block_model": "the block (model)", "shipped": "shipped", "exhaustive": "open everything (product)"}

    def make(self, folder, *, released_cost=0.02, recorded_hash=None):
        released = [{"arm": "block_model", "task": "tee-top-3", "repeat": 1, "cost_usd": released_cost,
                     "outcome": "answered"},
                    {"arm": "exhaustive", "task": "tee-top-3", "repeat": 1, "cost_usd": 0.2, "outcome": "answered"}]
        private = {"models": {self.MODEL: {"runs": [
            {"arm": "the block (model)", "task": "tee-top-3", "repeat": 1, "cost": 0.02, "outcome": "answered"},
            {"arm": "open everything (product)", "task": "tee-top-3", "repeat": 1, "cost": 0.2, "outcome": "answered"},
            {"arm": "shipped", "task": "tee-top-3", "repeat": 1, "cost": 0.03, "outcome": "answered"}]}}}
        raw = json.dumps(private).encode()
        (Path(folder) / fig.CLAIM2["Quenby"]).write_bytes(raw)
        dataset = {"market": "Quenby", "rounds": [1], "protocol_path": self.PROTOCOL, "runs": released,
                   "source_hashes": {"analysis_json": recorded_hash or hashlib.sha256(raw).hexdigest()}}
        summary = {"accuracy": {"block_model": {"correct": 1, "scored": 1, "unscorable": 0},
                                "shipped": {"correct": 0, "scored": 1, "unscorable": 0}},
                   "resources": {"block_model": {"median_cost_usd": 0.02}, "exhaustive": {"median_cost_usd": 0.2}}}
        return dataset, summary

    def test_quiet_when_the_sources_agree(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset, summary = self.make(folder)
            row = fig.claim2_study(dataset, summary, self.MODEL, Path(folder))
        self.assertEqual(sorted(r["arm"] for r in row["runs"]), ["block", "exhaustive", "shipped"])
        self.assertEqual(row["h1"]["block"], (1, 1))

    def test_fires_on_a_different_private_file(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset, summary = self.make(folder, recorded_hash="0" * 64)
            with self.assertRaisesRegex(ValueError, "exported from"):
                fig.claim2_study(dataset, summary, self.MODEL, Path(folder))

    def test_fires_when_a_released_charge_differs(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset, summary = self.make(folder, released_cost=0.021)
            with self.assertRaisesRegex(ValueError, "differs"):
                fig.claim2_study(dataset, summary, self.MODEL, Path(folder))

    def test_fires_when_the_private_file_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset, summary = self.make(folder)
            (Path(folder) / fig.CLAIM2["Quenby"]).unlink()
            with self.assertRaises(OSError):
                fig.claim2_study(dataset, summary, self.MODEL, Path(folder))


class Tikz(unittest.TestCase):
    def rows(self):
        rows = []
        for i, left_out in enumerate(([], ["shipped"])):
            values = {a: {"median": 0.01 * (i + 1) * (j + 1), "n": 6, "closed": 0}
                      for j, a in enumerate(fig.ARMS) if a not in left_out}
            rows.append({"name": f"Row {i}", "short": f"Row {i}", "h1": {"block": (6, 6), "shipped": (2, 6)},
                         "charge": {"values": values}})
        return rows

    def test_every_value_is_drawn_and_a_left_out_arm_is_not(self):
        text = fig.tikz(self.rows())
        plots = re.findall(r"\\addplot\[([^,]+),.*?coordinates \{(.*?)\};", text, re.S)
        points = {}
        for colour, body in plots:
            points.setdefault(colour, []).append(re.findall(r"\(([\d.]+),([\d.]+)\) \[([^\]]+)\]", body))
        # Panel (a): shipped then block, both rows. Panel (b): open everything, shipped, block.
        self.assertEqual([len(p) for p in points["figorange"]], [2, 1])
        self.assertEqual([len(p) for p in points["figblue"]], [2, 2])
        self.assertEqual([len(p) for p in points["black!45"]], [2])
        self.assertEqual(points["figorange"][0][0], ("33.3", "1.86", "2/6"))
        self.assertEqual(points["black!45"][0][1], ("0.0600", "0.75", "0.06"))
        self.assertIn("yticklabels={{Row 1},{Row 0}}", text)


PRIVATE = [fig.paths.RESULTS / name for name in fig.CLAIM2.values()]


@unittest.skipUnless(all(p.exists() for p in PRIVATE), "the claim 2 analysis files live on the laptop, not in git")
class StoredResults(unittest.TestCase):
    """The figure's values are Table 19's where the sets are the same (3 November 2026)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {row["name"]: row for row in fig.studies()}

    def test_four_rows_in_table19_order(self):
        self.assertEqual(list(self.rows), ["Ashcombe, Claude Haiku 4.5", "Ashcombe, DeepSeek V4 Flash",
                                           "Wexcombe, DeepSeek V4 Flash", "Quenby, DeepSeek V4 Flash"])

    def test_h1_counts_are_table19s(self):
        self.assertEqual([(r["h1"]["block"], r["h1"]["shipped"]) for r in self.rows.values()],
                         [((12, 12), (4, 12)), ((12, 12), (5, 12)), ((21, 21), (13, 21)), ((14, 14), (9, 13))])

    def test_charge_sets_and_medians(self):
        expected = {"Ashcombe, Claude Haiku 4.5": (5, True, 0.196911, 0.404873, 15),
                    "Ashcombe, DeepSeek V4 Flash": (5, True, 0.027952, 0.109448, 15),
                    "Wexcombe, DeepSeek V4 Flash": (8, True, 0.049683, 0.221002, 24),
                    "Quenby, DeepSeek V4 Flash": (6, False, 0.046883, 0.2980015, 12)}
        for name, (size, whole, block, exhaustive, n) in expected.items():
            with self.subTest(study=name):
                group = self.rows[name]["charge"]
                self.assertEqual((len(group["questions"]), group["whole"], group["left_out"]), (size, whole, []))
                self.assertAlmostEqual(group["values"]["block"]["median"], block, places=9)
                self.assertAlmostEqual(group["values"]["exhaustive"]["median"], exhaustive, places=9)
                self.assertEqual({v["n"] for v in group["values"].values()}, {n})

    def test_quenby_leaves_out_only_the_questions_the_shipped_agent_never_ran(self):
        group = self.rows["Quenby, DeepSeek V4 Flash"]["charge"]
        self.assertEqual(sorted(set(self.rows["Quenby, DeepSeek V4 Flash"]["h3"]["questions"]) - set(group["questions"])),
                         ["tee-all-stocked", "tee-count-stocked"])


if __name__ == "__main__":
    unittest.main()
