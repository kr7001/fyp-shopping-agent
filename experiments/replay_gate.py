#!/usr/bin/env python3
"""Replay the gate arm over runs already on disk.

The gate never issues a browser action, so applying it to a finished run gives exactly
the verdict it would have given live. That makes the whole gate arm free: every run
recorded so far can be re-scored under it without paying for a single new token.

Only the retry arm needs new runs, because only the retry arm changes what the agent
does. Keeping the two separate is the point. It says how much of the effect comes from
being allowed to refuse, and how much from being told why and trying again.

    python experiments/replay_gate.py
    python experiments/replay_gate.py --suite 20260909T120000

`--suite` restricts the replay to one results directory. That is how a held-out
measurement is taken: freeze the rules, run a fresh baseline, and replay only that
suite, so runs the rules were written against cannot flatter the figure.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import policy as policy_module
import score as scoring
import suite

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"
SPECS = {"tasks.json": HERE / "tasks.json",
         "tasks_scaled.json": HERE / "tasks_scaled.json",
         "tasks_heldout.json": HERE / "tasks_heldout.json"}


def specs() -> list[dict]:
    return [json.loads(path.read_text()) for path in SPECS.values() if path.exists()]


def spec_by_file() -> dict[str, dict]:
    return {name: json.loads(path.read_text())
            for name, path in SPECS.items() if path.exists()}


def task_index() -> dict[str, tuple[dict, dict]]:
    """Map each task id to its definition and the spec it came from.

    Only for suites written before `tasks_file` was recorded, which are all on the small
    and Rivenhall markets, where ids are unique across the two files. The held-out market
    reuses the Rivenhall ids deliberately, so that it asks the same questions of a
    different catalogue, and it must never be resolved this way: `scaled-target-price`
    exists in both and expects a different answer in each. Suites that record their task
    file are resolved from it instead.
    """
    index = {}
    for name, spec in spec_by_file().items():
        if name == "tasks_heldout.json":
            continue
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


def replay(only_suite: str | None = None) -> int:
    index = task_index()
    by_file = spec_by_file()
    current = {suite.draw_id(spec) for spec in specs()}
    rows: list[dict] = []
    stale: list[str] = []
    superseded: list[str] = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        # A suite already run under a policy is not a baseline, so replaying the gate over
        # it would be measuring the gate on top of itself. The same goes for every other
        # condition that changes what the agent was asked to do. This filter has had to be
        # widened three times as arms accumulated, each time after a figure came out wrong,
        # so it is now written as an explicit list of everything that makes a suite not a
        # baseline rather than as a test of the one flag that existed when it was written.
        not_baseline = (
            payload.get("policy", "off") != "off"     # gate or retry already applied
            or payload.get("confidence", "off") != "off"  # prompt asked for a confidence
            or payload.get("exhaustive")              # told to open everything
            or payload.get("targeting")               # given a retrieval strategy
        )
        if not_baseline:
            continue
        if only_suite and suite_path.parent.name != only_suite:
            continue
        # By default only suites on a draw the task files still describe. A suite from an
        # earlier draw is replayed only when named with --suite, so it is never pooled with
        # the current one by accident. The small fixture's earlier draw carried the answer
        # notes on its product pages, which is reason enough to keep it out of any total.
        if not only_suite and payload.get("draw") not in current:
            superseded.append(f"{suite_path.parent.name} ({payload.get('draw')})")
            continue
        # A suite that recorded its task file is resolved from it. Task ids alone are not
        # unique across markets: the held-out market asks the same questions of a different
        # catalogue, so resolving by id would score a Calderwood run against Rivenhall's
        # answer key. Suites older than the field fall back to the id index, which covers
        # only the two markets whose ids do not collide.
        named = by_file.get(payload.get("tasks_file") or "")
        named_tasks = {t["id"]: t for t in named["tasks"]} if named else {}
        for row in payload["rows"]:
            log_path = suite_path.parent / (row.get("log") or "")
            if named:
                task = named_tasks.get(row["task"])
                spec = named
            else:
                task, spec = index.get(row["task"], (None, None))
            if not row.get("log") or not log_path.exists() or task is None:
                continue
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
                         "draw": payload.get("draw") or "unrecorded",
                         "cost_usd": row.get("cost_usd")})

    if not rows:
        print("no baseline runs with traces on disk")
        return 1

    suites = sorted({r["suite"] for r in rows})
    print(f"suites: {', '.join(suites)}")

    before = collections.Counter(r["before"] for r in rows)
    after = collections.Counter(r["after"] for r in rows)
    print(f"{len(rows)} baseline runs replayed under the gate")
    if superseded:
        print(f"{len(superseded)} suites on a superseded draw left out, replay one with "
              f"--suite: {', '.join(superseded)}")
    if stale:
        print(f"{len(stale)} skipped, scored against a catalogue that has since been "
              f"regenerated")
    # One table per draw, because runs scored against different answer keys are different
    # measurements. A single pooled figure over three markets is the same mistake the draw
    # id was introduced to stop, and the markets do not behave alike: the gate withdraws a
    # different share of the wrong answers on each.
    for draw in sorted({r["draw"] for r in rows}):
        part = [r for r in rows if r["draw"] == draw]
        b = collections.Counter(r["before"] for r in part)
        a = collections.Counter(r["after"] for r in part)
        print()
        print(f"{draw}, {len(part)} runs")
        print(f"{'verdict':12} {'baseline':>9} {'gate':>7}")
        print("-" * 31)
        for verdict in sorted(set(b) | set(a)):
            print(f"{verdict:12} {b[verdict]:>9} {a[verdict]:>7}")
        withdrawn = sum(1 for r in part if r["before"] != r["after"]
                        and r["before"] in ("wrong", "ambiguous"))
        print(f"wrong withdrawn: {withdrawn} of {b['wrong'] + b['ambiguous']}")
    print()
    print(f"all draws, {len(rows)} runs")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", help="replay only this results directory")
    args = parser.parse_args()
    return replay(args.suite)


if __name__ == "__main__":
    raise SystemExit(main())
