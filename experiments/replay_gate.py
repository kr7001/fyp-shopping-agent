#!/usr/bin/env python3
"""Replay the gate arm over runs already on disk.

The gate never issues a browser action, so applying it to a finished run gives exactly
the verdict it would have given live. That makes the whole gate arm free: every run
recorded so far can be re-scored under it without paying for a single new token.

Only the retry arm needs new runs, because only the retry arm changes what the agent
does. Keeping the two separate is the point. It says how much of the effect comes from
being allowed to refuse, and how much from being told why and trying again.

    python experiments/replay_gate.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import policy as policy_module
import score as scoring

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
SPECS = {"tasks.json": HERE / "tasks.json", "tasks_scaled.json": HERE / "tasks_scaled.json"}


def specs() -> list[dict]:
    return [json.loads(path.read_text()) for path in SPECS.values() if path.exists()]


def task_index() -> dict[str, tuple[dict, dict]]:
    """Map each task id to its definition and the spec it came from."""
    index = {}
    for spec in specs():
        for task in spec["tasks"]:
            index[task["id"]] = (task, spec)
    return index


def full_answer(suite_dir: pathlib.Path, row: dict) -> str:
    """The answer as given, not as summarised.

    Suite rows keep the answer truncated to 300 characters for readability. Scoring the
    truncated text is not the same as scoring the answer: a long answer can lose the
    figure that decided its verdict, which shows up as a verdict change the gate did not
    cause. The per-run record holds the full text, so read it from there.
    """
    record = suite_dir / f"{row['task']}-{row['repeat']}.json"
    if record.exists():
        result = json.loads(record.read_text()).get("result") or {}
        return str(result.get("final") or "")
    return row.get("answer") or ""


def replay() -> int:
    index = task_index()
    rows: list[dict] = []
    stale: list[str] = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        # A suite already run under a policy is not a baseline, so replaying the gate
        # over it would be measuring the gate on top of itself.
        if payload.get("policy", "off") != "off":
            continue
        for row in payload["rows"]:
            log_path = suite_path.parent / (row.get("log") or "")
            entry = index.get(row["task"])
            if not row.get("log") or not log_path.exists() or entry is None:
                continue
            task, spec = entry
            answer = full_answer(suite_path.parent, row)

            # The catalogue is regenerated between rounds, so a run made against an
            # earlier fixture is scored against ground truth that no longer holds. Such a
            # run cannot be compared with itself, let alone against the gate. Detect it
            # by rescoring the untouched answer: if today's scorer disagrees with the
            # verdict stored at the time, the fixture moved underneath it.
            before = scoring.score(task, answer, True)["verdict"]
            if before != row["verdict"]:
                stale.append(row["task"])
                continue

            check = policy_module.gate(task, spec, answer, log_path)
            gated_answer = answer if check["ok"] else policy_module.abstention_for(check)
            after = scoring.score(task, gated_answer, True)["verdict"]
            rows.append({"suite": suite_path.parent.name, "task": row["task"],
                         "repeat": row["repeat"], "before": before,
                         "after": after, "flag": check["flag"],
                         "cost_usd": row.get("cost_usd")})

    if not rows:
        print("no baseline runs with traces on disk")
        return 1

    before = collections.Counter(r["before"] for r in rows)
    after = collections.Counter(r["after"] for r in rows)
    print(f"{len(rows)} baseline runs replayed under the gate")
    if stale:
        print(f"{len(stale)} skipped, scored against a catalogue that has since been "
              f"regenerated")
    print()
    print(f"{'verdict':12} {'baseline':>9} {'gate':>7}")
    print("-" * 31)
    for verdict in sorted(set(before) | set(after)):
        print(f"{verdict:12} {before[verdict]:>9} {after[verdict]:>7}")

    moved = [r for r in rows if r["before"] != r["after"]]
    lost = [r for r in moved if r["before"] == "correct"]
    saved = [r for r in moved if r["before"] in ("wrong", "ambiguous")]
    print(f"\nwrong answers withdrawn   {len(saved)} of "
          f"{before['wrong'] + before['ambiguous']}")
    print(f"correct answers withdrawn {len(lost)} of {before['correct']}")
    print("added model cost          $0.00, the gate issues no browser action")

    if lost:
        print("\ncorrect answers the gate would have withheld:")
        for r in lost:
            print(f"  {r['task']}-{r['repeat']:<2} {r['flag']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(replay())
