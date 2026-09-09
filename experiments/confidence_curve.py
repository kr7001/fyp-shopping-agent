#!/usr/bin/env python3
"""Does the agent's stated confidence separate its right answers from its wrong ones?

This evaluates the obvious alternative to the whole project: ask the agent how confident
it is, and abstain below a threshold. It is the first thing a reviewer will propose, so
it is measured here rather than argued away with a citation.

The comparison is deliberately generous to the baseline. Rather than fixing a threshold in
advance, every threshold is swept and the baseline is credited with its own best one,
chosen after seeing the answers. A method allowed to pick its threshold with hindsight and
still losing has lost properly.

    python experiments/confidence_curve.py --suite <results dir>

Reported for each threshold: how many runs still get answered (coverage), and how many of
those are right (selective accuracy). A useful confidence signal raises accuracy as
coverage falls. A useless one leaves accuracy flat, because it is discarding right and
wrong answers at the same rate.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import policy as policy_module
import score as scoring

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load(suite_dir: pathlib.Path) -> tuple[list[dict], dict]:
    payload = json.loads((suite_dir / "suite.json").read_text())
    spec_path = HERE / payload.get("tasks_file", "tasks.json")
    spec = json.loads(spec_path.read_text())
    tasks = {t["id"]: t for t in spec["tasks"]}

    rows = []
    for row in payload["rows"]:
        task = tasks.get(row["task"])
        log = suite_dir / (row.get("log") or "")
        if task is None or not log.exists():
            continue
        record = suite_dir / f"{row['task']}-{row['repeat']}.json"
        answer = row.get("answer") or ""
        if record.exists():
            result = json.loads(record.read_text()).get("result") or {}
            answer = policy_module.strip_confidence(str(result.get("final") or ""))
        check = policy_module.gate(task, spec, answer, log)
        rows.append({
            "task": row["task"], "repeat": row["repeat"],
            "verdict": row["verdict"],
            "confidence": row.get("confidence"),
            "flag": check["flag"],
        })
    return rows, payload


def distribution(rows: list[dict]) -> None:
    stated = [r for r in rows if r["confidence"] is not None]
    missing = len(rows) - len(stated)
    print(f"runs {len(rows)}, confidence stated in {len(stated)}, missing in {missing}\n")
    if not stated:
        return

    print(f"{'verdict':10} {'runs':>5} {'mean':>7} {'median':>7} {'min':>5} {'max':>5}")
    print("-" * 44)
    for verdict in ("correct", "wrong", "abstained", "failed"):
        group = [r["confidence"] for r in stated if r["verdict"] == verdict]
        if not group:
            continue
        print(f"{verdict:10} {len(group):>5} {statistics.mean(group):>7.1f} "
              f"{statistics.median(group):>7.1f} {min(group):>5} {max(group):>5}")

    right = [r["confidence"] for r in stated if r["verdict"] == "correct"]
    wrong = [r["confidence"] for r in stated if r["verdict"] == "wrong"]
    if right and wrong:
        print(f"\nseparation: correct answers average {statistics.mean(right):.1f}, "
              f"wrong answers average {statistics.mean(wrong):.1f}, "
              f"gap {statistics.mean(right) - statistics.mean(wrong):+.1f}")
        # The probability that a randomly drawn correct run is rated above a randomly
        # drawn wrong one. 0.5 is a coin flip, which is what a useless signal gives.
        wins = sum((a > b) + 0.5 * (a == b) for a in right for b in wrong)
        print(f"AUROC     : {wins / (len(right) * len(wrong)):.3f}   "
              f"(0.5 is no signal at all)")


def sweep(rows: list[dict]) -> None:
    stated = [r for r in rows if r["confidence"] is not None]
    if not stated:
        return
    base_wrong = sum(1 for r in stated if r["verdict"] == "wrong")
    print(f"\n{'threshold':>9} {'answered':>9} {'correct':>8} {'wrong':>6} "
          f"{'accuracy':>9} {'right lost':>11}")
    print("-" * 58)
    for threshold in range(0, 101, 10):
        kept = [r for r in stated if r["confidence"] >= threshold]
        correct = sum(1 for r in kept if r["verdict"] == "correct")
        wrong = sum(1 for r in kept if r["verdict"] == "wrong")
        lost = sum(1 for r in stated
                   if r["verdict"] == "correct" and r["confidence"] < threshold)
        accuracy = f"{correct / len(kept):.2f}" if kept else "n/a"
        print(f"{threshold:>9} {len(kept):>9} {correct:>8} {wrong:>6} "
              f"{accuracy:>9} {lost:>11}")
    print(f"\nwrong answers with no threshold applied: {base_wrong}")


def head_to_head(rows: list[dict]) -> None:
    """The baseline at its best possible threshold, against the sufficiency check."""
    stated = [r for r in rows if r["confidence"] is not None]
    if not stated:
        return

    best = None
    for threshold in range(0, 101, 5):
        suppressed = sum(1 for r in stated
                         if r["verdict"] == "wrong" and r["confidence"] < threshold)
        lost = sum(1 for r in stated
                   if r["verdict"] == "correct" and r["confidence"] < threshold)
        # Rank by wrong answers stopped, breaking ties towards losing fewer right ones.
        key = (suppressed, -lost)
        if best is None or key > best[0]:
            best = (key, threshold, suppressed, lost)

    _, threshold, suppressed, lost = best
    gate_caught = sum(1 for r in rows if r["verdict"] == "wrong" and r["flag"])
    gate_lost = sum(1 for r in rows if r["verdict"] == "correct" and r["flag"])
    total_wrong = sum(1 for r in rows if r["verdict"] == "wrong")
    total_right = sum(1 for r in rows if r["verdict"] == "correct")

    print(f"\n{'method':34} {'wrong stopped':>14} {'right blocked':>14}")
    print("-" * 64)
    print(f"{'stated confidence, best threshold ' + str(threshold):34} "
          f"{str(suppressed) + ' of ' + str(total_wrong):>14} "
          f"{str(lost) + ' of ' + str(total_right):>14}")
    print(f"{'sufficiency check':34} "
          f"{str(gate_caught) + ' of ' + str(total_wrong):>14} "
          f"{str(gate_lost) + ' of ' + str(total_right):>14}")
    print("\nThe threshold above was chosen after seeing the answers, which no deployable "
          "system could do.\nIt is the most favourable reading of the baseline available.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", help="results directory, default the newest with "
                                        "confidence recorded")
    args = parser.parse_args()

    if args.suite:
        suite_dir = RESULTS / args.suite
    else:
        candidates = [p.parent for p in sorted(RESULTS.glob("*/suite.json"))
                      if json.loads(p.read_text()).get("confidence", "off") != "off"]
        if not candidates:
            print("no suite has confidence recorded. Run:\n"
                  "  python experiments/suite.py --tasks experiments/tasks_scaled.json "
                  "--confidence plain --repeats 3")
            return 1
        suite_dir = candidates[-1]

    rows, payload = load(suite_dir)
    print(f"suite {suite_dir.name}, wording '{payload.get('confidence')}'\n")
    distribution(rows)
    sweep(rows)
    head_to_head(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
