#!/usr/bin/env python3
"""Re-apply scoring to a finished suite directory, without re-running anything.

Scoring rules get corrected as failure modes are understood; the runs themselves
are expensive and unchanged. This reads the per-run records already on disk and
rewrites suite.json, keeping the previous verdicts alongside so a change in the
rules is visible rather than silent.

    python experiments/rescore.py experiments/results/<stamp>
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score as scoring
import suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results_dir", type=pathlib.Path)
    parser.add_argument("--tasks", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parent / "tasks.json")
    args = parser.parse_args()

    tasks = {t["id"]: t for t in json.loads(args.tasks.read_text())["tasks"]}
    payload = json.loads((args.results_dir / "suite.json").read_text())

    changed = 0
    for row in payload["rows"]:
        record_path = args.results_dir / f"{row['task']}-{row['repeat']}.json"
        if not record_path.exists():
            continue
        result = json.loads(record_path.read_text()).get("result") or {}
        verdict = scoring.score(tasks[row["task"]], str(result.get("final") or ""),
                                bool(result.get("ok")))
        if verdict["verdict"] != row["verdict"]:
            row["previous_verdict"] = row["verdict"]
            changed += 1
        row["verdict"], row["why"] = verdict["verdict"], verdict["why"]

    payload["summary"] = suite.summarise(payload["rows"])
    payload["rescored"] = True
    (args.results_dir / "suite.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print(f"{changed} verdicts changed")
    suite.print_summary(payload["summary"], payload["rows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
