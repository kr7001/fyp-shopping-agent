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
import policy as policy_module
import score as scoring
import trace_stats

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
AGENT_CORE = REPO / "agent" / "agent-core"
RUNNER = HERE / "run_browser_task.py"
RESULTS = HERE / "results"


def run_once(task: dict, base_url: str, out_dir: pathlib.Path, tag: str,
             query: str | None = None) -> dict:
    """Execute one task once and return its record, enriched with trace counts.

    `query` overrides the task text, which is how a policy retry re-asks the same task
    with the reason its first answer was rejected.
    """
    query = query if query is not None else task["query"].format(base=base_url)
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


def add(*values) -> float | int | None:
    """Sum what is present. A missing cost is unknown, not zero."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def apply_policy(mode: str, task: dict, spec: dict, answer: str, record: dict,
                 out_dir: pathlib.Path, tag: str, confidence: str = "off",
                 reason: str | None = None) -> tuple:
    """Run the sufficiency check and act on it.

    Cost and interaction counts are reported for the arm as a whole, both attempts
    included. A policy that buys accuracy with a second full run has to be charged for
    it, or the comparison against the baseline is not a comparison.
    """
    result = record.get("result") or {}
    trace = record.get("trace") or {}
    check = policy_module.gate(task, spec, answer, out_dir / f"{tag}.log")

    if check["ok"] or mode == "gate":
        if not check["ok"]:
            answer = policy_module.abstention_for(check)
        return answer, record, result, trace, check

    query = policy_module.retry_query(
        task["query"].format(base=spec["base_url"]), check, reason=reason)
    if confidence != "off":
        query = policy_module.confidence_query(query, confidence)
    tag2 = f"{tag}-retry"
    second = run_once(task, spec["base_url"], out_dir, tag2, query=query)
    result2 = second.get("result") or {}
    answer2 = str(result2.get("final") or "")
    trace2 = second.get("trace") or {}
    check2 = policy_module.gate(task, spec, answer2, out_dir / f"{tag2}.log")

    # Still unverified after being told why: abstain rather than emit it a second time.
    final_answer = answer2 if check2["ok"] else policy_module.abstention_for(check2)
    merged = {**second,
              "cost_usd": add(record.get("cost_usd"), second.get("cost_usd")),
              "elapsed_s": add(record.get("elapsed_s"), second.get("elapsed_s"))}
    merged_trace = {key: add(trace.get(key), trace2.get(key))
                    for key in ("tool_calls_total", "actions", "observations")}
    return final_answer, merged, result2, merged_trace, {
        **check2, "retried": True, "first_flag": check["flag"],
        "first_why": check["why"], "first_answer": answer[:300]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--tasks", type=pathlib.Path, default=HERE / "tasks.json")
    parser.add_argument("--only", nargs="*", help="task ids to run, default all")
    parser.add_argument("--confidence", choices=("off", "plain", "retrieval"), default="off",
                        help="ask the agent to state a confidence with its answer. This is "
                             "the verbalised-confidence baseline, not part of the "
                             "contribution, and is measured to answer the obvious "
                             "objection rather than to be used")
    parser.add_argument("--policy", choices=("off", "gate", "retry"), default="off",
                        help="off is the unmodified baseline; gate abstains on a failed "
                             "sufficiency check; retry re-asks once with the reason")
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
            query = task["query"].format(base=spec["base_url"])
            if args.confidence != "off":
                query = policy_module.confidence_query(query, args.confidence)
            record = run_once(task, spec["base_url"], out_dir, tag, query=query)
            result = record.get("result") or {}
            answer = str(result.get("final") or "")
            trace = record.get("trace") or {}

            # Read the stated confidence, then take it out of the answer. The scorer looks
            # for money and a two-digit percentage sitting in the text can be read as one.
            confidence, reason = None, None
            if args.confidence != "off":
                confidence = policy_module.parse_confidence(answer)
                reason = policy_module.parse_reason(answer)
                answer = policy_module.strip_confidence(answer)

            check = None
            if args.policy != "off":
                answer, record, result, trace, check = apply_policy(
                    args.policy, task, spec, answer, record, out_dir, tag,
                    confidence=args.confidence, reason=reason)

            verdict = scoring.score(task, answer, bool(result.get("ok")))
            row = {
                "task": task["id"], "family": task["family"], "gated": task["gated"],
                "repeat": repeat,
                "verdict": verdict["verdict"], "why": verdict["why"],
                "answer": answer[:300],
                "tool_calls": trace.get("tool_calls_total"),
                "actions": trace.get("actions"),
                "observations": trace.get("observations"),
                "cost_usd": record.get("cost_usd"),
                "elapsed_s": record.get("elapsed_s"),
                "error": record.get("error") or result.get("error"),
                "log": record.get("log"),
            }
            if args.confidence != "off":
                row["confidence"] = confidence
                row["confidence_reason"] = reason
                row["confidence_wording"] = args.confidence
            if check is not None:
                row.update({"policy": args.policy, "flag": check.get("flag"),
                            "flag_why": check.get("why"),
                            "opened": check.get("opened"),
                            "retried": bool(check.get("retried")),
                            "first_flag": check.get("first_flag"),
                            "first_why": check.get("first_why"),
                            "first_answer": check.get("first_answer")})
            rows.append(row)
            conf = f" conf={row.get('confidence')}" if args.confidence != "off" else ""
            print(f"[{done}/{total}] {tag:32} {row['verdict']:10} "
                  f"calls={row['tool_calls']} act={row['actions']}{conf} "
                  f"${row['cost_usd']} {row['elapsed_s']}s")

    summary = summarise(rows)
    payload = {"ran_at": dt.datetime.now().isoformat(timespec="seconds"),
               "repeats": args.repeats, "policy": args.policy,
               "confidence": args.confidence,
               "tasks_file": args.tasks.name,
               # The ground truth this suite was scored against. The catalogue is
               # regenerated between rounds, so without it an old result cannot be told
               # apart from a wrong one.
               "instance": spec.get("_instance"),
               "summary": summary, "rows": rows}
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
