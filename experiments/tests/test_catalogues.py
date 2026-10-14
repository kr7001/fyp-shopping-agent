"""Every committed catalogue and task file regenerates byte for byte from its seed.

Answers are computed from the catalogue, never typed, so a task file is only trustworthy if
running its generator again gives the same bytes. This is that check, with no shop needed.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

# (what is checked, generator and its arguments, files it writes -> committed files)
CASES = [
    ("clothing market, Thornwood", ["env/generate_apparel.py", "--seed", "203"],
     {"--out": paths.FIXTURES / "scaled_apparel.json",
      "--tasks": paths.TASKS / "tasks_apparel.json"}),
    ("water market, Rivenhall", ["env/generate_catalogue.py", "--seed", "7",
                                 "--brand", "Rivenhall", "--sku-prefix", "IGR-RVN"],
     {"--out": paths.FIXTURES / "scaled_water.json"}),
    ("held-out water market, Calderwood", ["env/generate_catalogue.py", "--seed", "41",
                                           "--brand", "Calderwood", "--sku-prefix", "IGR-CAL"],
     {"--out": paths.FIXTURES / "heldout_calderwood.json"}),
    ("Rivenhall questions", ["experiments/water/make_scaled_tasks.py",
                             "--fixture", "env/fixtures/scaled_water.json"],
     {"--out": paths.TASKS / "tasks_scaled.json"}),
    ("Calderwood questions", ["experiments/water/make_scaled_tasks.py",
                              "--fixture", "env/fixtures/heldout_calderwood.json"],
     {"--out": paths.TASKS / "tasks_heldout.json"}),
    # The box v2 batch's questions, from the Thornwood fixture and the pilot's two files.
    ("Thornwood v2 questions", ["env/generate_apparel_v2_tasks.py"],
     {"--out": paths.TASKS / "tasks_apparel_v2.json",
      "--readings-out": paths.TASKS / "readings_apparel_v2.json"}),
]


class Regenerate(unittest.TestCase):
    def test_every_generated_file(self):
        for label, command, outputs in CASES:
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                args = list(command)
                for flag, committed in outputs.items():
                    args += [flag, str(pathlib.Path(tmp) / committed.name)]
                subprocess.run([sys.executable, *args], cwd=paths.REPO, check=True,
                               capture_output=True)
                for committed in outputs.values():
                    fresh = (pathlib.Path(tmp) / committed.name).read_bytes()
                    self.assertEqual(fresh, committed.read_bytes(), committed.name)


if __name__ == "__main__":
    unittest.main()
