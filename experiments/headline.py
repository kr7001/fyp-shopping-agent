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

Populations are split by catalogue draw and never added together. Until 13 Sep 2026 this
file excluded only policy and confidence suites, so the "15 listings" baseline counted the
exhaustive arm, targeting v1 and four runs from a superseded draw as the unmodified agent:
44 runs at 68%, where the unmodified agent on the current draw is 24 runs at 62.5%.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import arms
import suite

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


def current_draws() -> dict[str, str]:
    return {suite.draw_id(json.loads((HERE / name).read_text())): name
            for name in ("tasks.json", "tasks_scaled.json", "tasks_heldout.json")
            if (HERE / name).exists()}


def baseline_rows() -> list[dict]:
    """Every run of the agent as shipped, with nothing added and nothing asked of it."""
    spec = tasks()
    rows = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        if arms.arm_name(payload) != "unmodified":
            continue
        for row in payload["rows"]:
            task = spec.get(row["task"])
            if task is None:
                continue
            rows.append({**row, "gated": task["gated"],
                         "draw": payload.get("draw") or "unknown"})
    return rows


def main() -> int:
    rows = baseline_rows()
    current = current_draws()

    print("THE UNMODIFIED AGENT, ONE POPULATION PER CATALOGUE DRAW\n")
    print(f"{'draw':24} {'state':11} {'gated runs':>10} {'correct':>8} {'rate':>7}")
    print("-" * 64)
    for draw in sorted({r["draw"] for r in rows}):
        group = [r for r in rows if r["draw"] == draw and r["gated"]]
        if not group:
            continue
        right = sum(1 for r in group if r["verdict"] == "correct")
        state = "current" if draw in current else "superseded"
        print(f"{draw:24} {state:11} {len(group):>10} {right:>8} "
              f"{100 * right / len(group):>6.1f}%")

    print("\nQuote a rate only with its draw and denominator attached. The small fixture's")
    print("earlier draw had the answer notes on the page, and a superseded draw was scored")
    print("against answers that no longer exist, so no row here may be added to another.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
