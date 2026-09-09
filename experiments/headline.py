#!/usr/bin/env python3
"""The canonical figures, computed from the runs rather than remembered.

Two documents carried different headline percentages for what read as the same claim.
Both came from real runs and neither was wrong on its own denominator, which is exactly
how that happens: a figure gets quoted once, the population grows, and the figure stays.

The fix is not to pick one. It is to stop writing them by hand. Every headline number in
the report and on the pages should come from here, with its denominator attached.

    python experiments/headline.py

Only unmodified runs count towards the baseline. A run whose prompt was altered to request
a confidence figure is a different condition and is excluded, even though the agent and
the environment are the same.
"""

from __future__ import annotations

import collections
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"


def tasks() -> dict[str, dict]:
    out = {}
    for name in ("tasks.json", "tasks_scaled.json"):
        path = HERE / name
        if path.exists():
            for task in json.loads(path.read_text())["tasks"]:
                out[task["id"]] = task
    return out


def baseline_rows() -> list[dict]:
    """Every run of the agent as shipped, with nothing added and nothing asked of it."""
    spec = tasks()
    rows = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        if payload.get("policy", "off") != "off":
            continue
        if payload.get("confidence", "off") != "off":
            continue
        for row in payload["rows"]:
            task = spec.get(row["task"])
            if task is None:
                continue
            rows.append({**row, "gated": task["gated"],
                         "fixture": "scaled" if row["task"].startswith("scaled-") else "small"})
    return rows


def main() -> int:
    rows = baseline_rows()
    gated = [r for r in rows if r["gated"]]

    print("THE UNMODIFIED AGENT\n")
    print(f"{'population':26} {'runs':>6} {'correct':>8} {'rate':>7}")
    print("-" * 50)

    for key, label in (("small", "4 listings, RQ2 fixture"),
                       ("scaled", "15 listings, scaled")):
        group = [r for r in gated if r["fixture"] == key]
        if not group:
            continue
        right = sum(1 for r in group if r["verdict"] == "correct")
        print(f"{label:26} {len(group):>6} {right:>8} {100 * right / len(group):>6.0f}%")

    right = sum(1 for r in gated if r["verdict"] == "correct")
    print("-" * 50)
    print(f"{'all gated runs':26} {len(gated):>6} {right:>8} {100 * right / len(gated):>6.0f}%")
    print(f"{'all runs, gated or not':26} {len(rows):>6} "
          f"{sum(1 for r in rows if r['verdict'] == 'correct'):>8}")

    abstained = sum(1 for r in rows if r["verdict"] == "abstained")
    print(f"\nabstentions: {abstained} of {len(rows)}")

    print("\nQuote a rate only with its fixture and denominator attached. The two are not")
    print("interchangeable: the gap between them is the scale finding, not noise.")

    verdicts = collections.Counter(r["verdict"] for r in rows)
    print(f"\nverdicts: {dict(verdicts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
