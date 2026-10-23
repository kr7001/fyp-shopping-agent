"""Where everything in the repository lives, in one place.

Scripts sit in folders by job (`box/`, `runners/`, `analysis/`, `water/`) but import each
other by plain module name, as they did when they all sat in one folder. Importing this
module puts every one of those folders on the import path, so `import score` works from
anywhere. A script reaches it with two lines:

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import paths

Moved here from per-script constants on 8 October 2026, when the folder was reorganised.
"""
from __future__ import annotations

import pathlib
import sys

EXPERIMENTS = pathlib.Path(__file__).resolve().parent
REPO = EXPERIMENTS.parent

TASKS = EXPERIMENTS / "tasks"          # question files with their answer keys
# A pilot's question files (23 October 2026): development questions on a development market,
# for a small paid run before a big one, never a claim's. The planner's census and the parse
# probes do not read this folder.
PILOT_TASKS = TASKS / "pilot"
RESULTS = EXPERIMENTS / "results"      # one folder per batch: suite.json, run records, logs
RUNS = EXPERIMENTS / "runs"            # single runs made outside a batch
FIXTURES = REPO / "env" / "fixtures"   # the generated catalogues the shop was seeded from
AGENT_CORE = REPO / "agent" / "agent-core"
NAIVE_PYTHON = REPO / ".venv-naive" / "bin" / "python"
ENV_FILE = REPO / ".env"

CODE_FOLDERS = ("box", "runners", "analysis", "water")

# Near the front, as the scripts' own folder was before, so an installed package that
# happens to share a name (`policy`, `score`) can never shadow ours.
for folder in reversed(CODE_FOLDERS):
    path = str(EXPERIMENTS / folder)
    if path not in sys.path:
        sys.path.insert(1, path)
