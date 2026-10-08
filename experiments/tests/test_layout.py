"""The folder layout holds together: every script compiles, imports, and names real paths.

Written when experiments/ was split into folders on 8 October 2026, so a file moved without
its references fails here, for free, rather than in the middle of a paid batch.
"""
import importlib
import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

SCRIPTS = sorted(p for folder in paths.CODE_FOLDERS
                 for p in (paths.EXPERIMENTS / folder).glob("*.py"))
ENV_SCRIPTS = sorted((paths.REPO / "env").glob("*.py"))

# These import a browser or the openJiuwen runtime at the top, so they run from their own
# interpreter (.venv-naive, or uv inside agent/agent-core) and are compiled but not imported.
OWN_INTERPRETER = {"run_browser_task", "naive_agent", "reveal_race"}

# A script or task file named in a usage line, such as `python experiments/box/planner.py`.
NAMED_PATH = re.compile(r"\b(?:experiments|env)/[\w./-]+\.(?:py|sh|json)\b")

# Provenance written into generated task files. Kept word for word, old path included, so a
# regenerated file stays byte-identical to the committed one.
PROVENANCE = {"experiments/make_scaled_tasks.py"}


def missing_paths(text: str) -> list[str]:
    return [p for p in NAMED_PATH.findall(text)
            if p not in PROVENANCE and not (paths.REPO / p).exists()]


class Layout(unittest.TestCase):
    def test_every_script_compiles(self):
        for path in SCRIPTS + ENV_SCRIPTS:
            with self.subTest(script=str(path.relative_to(paths.REPO))):
                compile(path.read_text(), str(path), "exec")

    def test_every_module_imports(self):
        for path in SCRIPTS:
            if path.stem in OWN_INTERPRETER:
                continue
            with self.subTest(module=path.stem):
                importlib.import_module(path.stem)

    def test_every_named_path_exists(self):
        for path in SCRIPTS + ENV_SCRIPTS + [paths.EXPERIMENTS / "runners" / "run.sh"]:
            with self.subTest(script=str(path.relative_to(paths.REPO))):
                self.assertEqual(missing_paths(path.read_text()), [])

    def test_the_path_check_catches_an_old_path(self):
        # The flat layout before 8 Oct 2026. If this stops being flagged the check is blind.
        self.assertEqual(missing_paths("python experiments/suite.py --tasks experiments/tasks.json"),
                         ["experiments/suite.py", "experiments/tasks.json"])

    def test_every_batch_finds_its_task_file(self):
        for suite_path in sorted(paths.RESULTS.glob("*/suite.json")):
            name = json.loads(suite_path.read_text()).get("tasks_file")
            if not name:
                continue  # the four oldest batches predate the field
            with self.subTest(batch=suite_path.parent.name):
                self.assertTrue((paths.TASKS / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
