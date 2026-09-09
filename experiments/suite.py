#!/usr/bin/env python3
"""Run the RQ2 baseline suite: every task, several times, scored.

One run per task is not enough. The same model on the same page has been observed
answering correctly twice and fabricating a price on the third attempt, so a single
sample would have recorded that task as solved. This runs each task `--repeats`
times and reports the distribution.

    python experiments/suite.py --repeats 5
    python experiments/suite.py --repeats 1 --only water-a-9l5-price
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score as scoring
import trace_stats

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
AGENT_CORE = REPO / "agent" / "agent-core"
RUNNER = HERE / "run_browser_task.py"
RESULTS = HERE / "results"


def run_once(task: dict, base_url: str, out_dir: pathlib.Path, tag: str) -> dict:
    """Execute one task once and return its record, enriched with trace counts."""
    query = task["query"].format(base=base_url)
    record_path = out_dir / f"{tag}.json"
    log_path = out_dir / f"{tag}.log"

    with log_path.open("w") as log:
        subprocess.run(
            ["uv", "run", "python", str(RUNNER), query, "--out", str(record_path)],
            cwd=AGENT_CORE, stdout=log, stderr=subprocess.STDOUT, check=False,
        )

    if not record_path.exists():
        return {"error": "runner wrote no record", "log": log_path.name}

    # The counts are written back into the run record, not just carried in memory.
    # A per-run file that lacks them is not self-describing, and the whole point of
    # keeping every record is that a result can be re-examined later on its own.
    record = json.loads(record_path.read_text())
    record["trace"] = trace_stats.stats(log_path)
    record["log"] = log_path.name
    record_path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--tasks", type=pathlib.Path, default=HERE / "tasks.json")
    parser.add_argument("--only", nargs="*", help="task ids to run, default all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    spec = json.loads(args.tasks.read_text())
    tasks = [t for t in spec["tasks"] if not args.only or t["id"] in args.only]
    if not tasks:
        print("no matching tasks")
        return 1

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = RESULTS / stamp
    total = len(tasks) * args.repeats
    print(f"{len(tasks)} tasks x {args.repeats} repeats = {total} runs -> {out_dir}")

    if args.dry_run:
        for task in tasks:
            print(f"  {task['id']:26} gated={task['gated']}  {task['expect']['kind']}")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    rows, done = [], 0
    for task in tasks:
        for repeat in range(1, args.repeats + 1):
            done += 1
            tag = f"{task['id']}-{repeat}"
            record = run_once(task, spec["base_url"], out_dir, tag)
            result = record.get("result") or {}
            verdict = scoring.score(task, str(result.get("final") or ""),
                                    bool(result.get("ok")))
            trace = record.get("trace") or {}
            row = {
                "task": task["id"], "family": task["family"], "gated": task["gated"],
                "repeat": repeat,
                "verdict": verdict["verdict"], "why": verdict["why"],
                "answer": str(result.get("final") or "")[:300],
                "tool_calls": trace.get("tool_calls_total"),
                "actions": trace.get("actions"),
                "observations": trace.get("observations"),
                "cost_usd": record.get("cost_usd"),
                "elapsed_s": record.get("elapsed_s"),
                "error": record.get("error") or result.get("error"),
                "log": record.get("log"),
            }
            rows.append(row)
            print(f"[{done}/{total}] {tag:32} {row['verdict']:10} "
                  f"calls={row['tool_calls']} act={row['actions']} "
                  f"${row['cost_usd']} {row['elapsed_s']}s")

    summary = summarise(rows)
    payload = {"ran_at": dt.datetime.now().isoformat(timespec="seconds"),
               "repeats": args.repeats, "summary": summary, "rows": rows}
    (out_dir / "suite.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print_summary(summary, rows)
    print(f"\nfull results: {out_dir / 'suite.json'}")
    return 0


def summarise(rows: list[dict]) -> dict:
    by_task: dict[str, dict] = {}
    for row in rows:
        entry = by_task.setdefault(row["task"], {
            "gated": row["gated"], "verdicts": collections.Counter(),
            "actions": [], "tool_calls": [], "cost": []})
        entry["verdicts"][row["verdict"]] += 1
        for key, field in (("actions", "actions"), ("tool_calls", "tool_calls"),
                           ("cost", "cost_usd")):
            if row[field] is not None:
                entry[key].append(row[field])

    for entry in by_task.values():
        entry["verdicts"] = dict(entry["verdicts"])
        entry["mean_actions"] = mean(entry["actions"])
        entry["mean_tool_calls"] = mean(entry["tool_calls"])
        entry["total_cost"] = round(sum(entry["cost"]), 4) if entry["cost"] else None

    overall = collections.Counter(row["verdict"] for row in rows)
    return {"by_task": by_task, "overall": dict(overall),
            "total_cost": round(sum(r["cost_usd"] for r in rows if r["cost_usd"]), 4)}


def mean(values: list) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def print_summary(summary: dict, rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print(f"{'task':28} {'gated':5} {'verdicts':28} {'acts':>5} {'calls':>6}")
    print("-" * 78)
    for task_id, entry in summary["by_task"].items():
        verdicts = " ".join(f"{k}:{v}" for k, v in sorted(entry["verdicts"].items()))
        print(f"{task_id:28} {str(entry['gated']):5} {verdicts:28} "
              f"{str(entry['mean_actions']):>5} {str(entry['mean_tool_calls']):>6}")
    print("-" * 78)
    print("overall:", summary["overall"])
    print("total cost: $", summary["total_cost"])

    gated = [r for r in rows if r["gated"] and r["actions"] is not None]
    correct = [r["actions"] for r in gated if r["verdict"] == "correct"]
    wrong = [r["actions"] for r in gated if r["verdict"] == "wrong"]
    if correct and wrong:
        print(f"\ngated tasks, mean actions: correct {mean(correct)}, wrong {mean(wrong)}")


if __name__ == "__main__":
    raise SystemExit(main())
