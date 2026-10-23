#!/usr/bin/env python3
"""Re-apply scoring to a finished suite directory, without re-running anything.

Scoring rules get corrected as failure modes are understood; the runs themselves
are expensive and unchanged. This reads the per-run records already on disk and
rewrites suite.json, keeping the previous verdicts alongside so a change in the
rules is visible rather than silent.

A suite run under the gate is rescored through the gate, exactly as `suite.py` scored it
live. The gate issues no browser action, so replaying it with a corrected checker gives the
verdict the corrected checker would have given, at no cost. A retry or investigate suite
cannot be rescored: its second attempt was a new browser run that a corrected checker might
never have triggered, and no replay can undo a run that happened.

    python experiments/analysis/rescore.py experiments/results/<stamp> --reason "why"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import policy as policy_module
import score as scoring
import suite
import verify_cells  # noqa: E402  (run_reading, the reading a stored run answered under)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results_dir", type=pathlib.Path)
    parser.add_argument("--tasks", type=pathlib.Path,
                        help="task file, default the one the suite recorded")
    parser.add_argument("--reason", required=True,
                        help="what changed in the scoring, recorded in suite.json")
    args = parser.parse_args()

    payload = json.loads((args.results_dir / "suite.json").read_text())
    policy = payload.get("policy") or "off"
    if policy not in ("off", "gate"):
        print(f"refusing: a {policy} suite made second runs that rescoring cannot undo")
        return 1

    tasks_path = args.tasks or paths.TASKS / (payload.get("tasks_file") or "tasks.json")
    spec = json.loads(tasks_path.read_text())
    tasks = {t["id"]: t for t in spec["tasks"]}
    keys = scoring.keys_for(tasks_path)
    confidence = payload.get("confidence") or "off"

    changes = []
    for row in payload["rows"]:
        record_path = args.results_dir / f"{row['task']}-{row['repeat']}.json"
        if not record_path.exists():
            continue
        result = json.loads(record_path.read_text()).get("result") or {}
        task = tasks[row["task"]]
        answer = str(result.get("final") or "")
        if confidence != "off":
            answer = policy_module.strip_confidence(answer)

        if policy == "gate":
            check = policy_module.gate(task, spec, answer, args.results_dir / row["log"])
            if not check["ok"]:
                answer = policy_module.abstention_for(check)
            row.update({"flag": check.get("flag"), "flag_why": check.get("why"),
                        "opened": check.get("opened")})
            row["answer"] = answer[:300]

        # The one scoring call, under the reading the run answered and the task file's keys
        # (score v8, `score.score_run`): until 23 October 2026 this scored every run under its
        # task's own key, whatever reading it was answered under (LESSONS 29).
        verdict = scoring.score_run(task, verify_cells.run_reading(row, payload), keys, answer,
                                    bool(result.get("ok")))
        if verdict["verdict"] != row["verdict"]:
            changes.append({"task": row["task"], "repeat": row["repeat"],
                            "from": row["verdict"], "to": verdict["verdict"]})
            row["previous_verdict"] = row["verdict"]
        row["verdict"], row["why"] = verdict["verdict"], verdict["why"]

    # `rescored` was once a bare True, which says a change happened and not what it was.
    # It is now a list, one entry per rescore, so the history of a figure can be read back.
    history = payload.get("rescored")
    if not isinstance(history, list):
        history = [] if not history else [{"on": "unrecorded", "reason": "earlier rescore"}]
    history.append({"on": dt.date.today().isoformat(), "reason": args.reason,
                    "changed": changes})
    payload["rescored"] = history
    # The rows now carry the verdicts of this scorer, so the payload says so (LESSONS 10);
    # until 20 October 2026 a rescored batch kept the version of the scorer that first
    # judged it.
    payload["scorer_version"] = scoring.VERSION
    payload["summary"] = suite.summarise(payload["rows"])
    (args.results_dir / "suite.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print(f"{len(changes)} verdicts changed")
    for c in changes:
        print(f"  {c['task']}-{c['repeat']}: {c['from']} -> {c['to']}")
    suite.print_summary(payload["summary"], payload["rows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
