#!/usr/bin/env python3
"""Score every stored run under two scorers and list every verdict or reason that differs.

A scorer change re-scores every stored run (LESSONS 4, 34), and an additive change must move
none. `rescore.py` rewrites a batch's suite.json; this reads the same records and writes
nothing, so the check can be made against the committed scorer before anything is committed:

    git show HEAD:experiments/analysis/score.py > /tmp/score_before.py
    python3 experiments/analysis/scorer_moves.py /tmp/score_before.py

Written 24 October 2026 for score v10, whose check read 599 records in 86 batches: 0 verdicts
moved, 0 reasons changed. A batch is read as rescore.py reads it: the task file it recorded,
the answer from each run's record, the reading the run answered under (`verify_cells.
run_reading`), and for a gated batch the answer the gate left, as stored.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import policy  # noqa: E402
import score as current  # noqa: E402
import verify_cells  # noqa: E402


def load_scorer(path: pathlib.Path):
    """Another version of score.py, imported under its own name (a dataclass inside it needs
    the module registered before its body runs)."""
    spec = importlib.util.spec_from_file_location("score_before", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["score_before"] = module
    spec.loader.exec_module(module)
    return module


def differences(before, after) -> tuple[int, int, list[tuple], list[tuple]]:
    """(records, batches, verdicts moved, reasons changed) over every stored batch whose task
    file is still in experiments/tasks/."""
    records = batches = 0
    moves, reasons = [], []
    for suite_path in sorted(paths.RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        name = payload.get("tasks_file")
        if not name or not (paths.TASKS / name).exists():
            continue
        tasks_path = paths.TASKS / name
        tasks = {t["id"]: t for t in json.loads(tasks_path.read_text())["tasks"]}
        keys = (before.keys_for(tasks_path), after.keys_for(tasks_path))
        batches += 1
        for row in payload["rows"]:
            record = suite_path.parent / f"{row['task']}-{row['repeat']}.json"
            if not record.exists() or row["task"] not in tasks:
                continue
            result = json.loads(record.read_text()).get("result") or {}
            answer = str(result.get("final") or "")
            if (payload.get("confidence") or "off") != "off":
                answer = policy.strip_confidence(answer)
            if (payload.get("policy") or "off") == "gate":
                answer = row.get("answer") or answer
            reading = verify_cells.run_reading(row, payload)
            a, b = (scorer.score_run(tasks[row["task"]], reading, k, answer, bool(result.get("ok")))
                    for scorer, k in zip((before, after), keys))
            records += 1
            where = (suite_path.parent.name, row["task"], row["repeat"])
            if a["verdict"] != b["verdict"]:
                moves.append((*where, a["verdict"], b["verdict"]))
            elif a["why"] != b["why"]:
                reasons.append((*where, a["why"], b["why"]))
    return records, batches, moves, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("before", type=pathlib.Path, help="the scorer to compare the working one with")
    args = parser.parse_args()
    before = load_scorer(args.before)
    records, batches, moves, reasons = differences(before, current)
    print(f"{records} records in {batches} batches scored under score v{before.VERSION} and v{current.VERSION}: "
          f"{len(moves)} verdicts move, {len(reasons)} reasons change")
    for move in moves:
        print("  move  ", *move)
    for reason in reasons:
        print("  reason", *reason)
    return 1 if moves or reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
