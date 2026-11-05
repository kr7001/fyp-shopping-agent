#!/usr/bin/env python3
"""Wall-clock run times of the primary studies, by arm, on the gated questions. Free.

Written 5 November 2026 for the final report's table of threats to validity, which quotes these
medians.

The time. Each run record, `experiments/results/<batch>/<task>-<repeat>.json`, holds
`elapsed_s`: the runner's own clock around one agent run, from just before the browser runtime
starts to the end of the agent's run, in seconds to one decimal place
(`experiments/runners/run_browser_task.py`). The block's work before the run, reading the
results page and, in a model arm, the parse call, is outside it.

The trials. The trial list of the script-fetch audit,
`experiments/artifacts/script-fetch-audit-4-nov.json`, by study, each trial with its batch,
task, repeat and arm. For each of the four primary comparisons it holds the agent trials its
analysis counts, a technical void replaced by its re-run. A slot the block closed by asking
back or declining ran no agent and is not in the list.

The gated questions. In each study, the questions its open-everything arm ran. Where the file
also gives the questions of the study's H2 test (listings opened, the block against open
everything), the two sets must be the same, or this stops. An arm that ran only some of the
gated questions has its median over those. The `questions` column says how many it ran, and
such a median does not compare question for question with an arm that ran them all.

Each arm's median is over its trials on the gated questions, taken in exact decimals, and
shown in seconds and in minutes, the minutes rounded half up to one decimal place. A trial
whose record is missing or unreadable, or holds no positive `elapsed_s`, is named, left out of
its median, and makes the command exit with status 1. None is skipped silently.

Reads committed files only, never a model, the shop or the network.

    python3 tools/run_times.py
"""
from __future__ import annotations

import argparse
import decimal
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import paths  # noqa: E402

# Bumped when a figure this prints would change for the same files.
#   1  5 November 2026, the first version
VERSION = 1

# Every agent trial of the four primary comparisons, as the script-fetch audit listed them.
# The folder is named here, not in paths.py: the Browser Use cohorts pin paths.py byte for
# byte as agent-facing code (test_browser_use_fresh, test_browser_use_fresh_continuation), and
# a new line there fails both.
TRIALS = paths.EXPERIMENTS / "artifacts" / "script-fetch-audit-4-nov.json"

# The open-everything arm is named "open everything" in claim 1 and "open everything
# (product)" in claim 2 and the replication.
OPEN = "open everything"

MINUTE = 60
TENTH = decimal.Decimal("0.1")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def shown(path: pathlib.Path) -> str:
    return str(path.relative_to(paths.REPO)) if path.is_relative_to(paths.REPO) else str(path)


def read_time(results: pathlib.Path, trial: dict) -> tuple[decimal.Decimal | None, str | None]:
    """A trial's `elapsed_s` as written in its record, or why it has none. Read as a decimal,
    so a median of two tenths stays exact."""
    path = results / trial["batch"] / f"{trial['task']}-{trial['repeat']}.json"
    try:
        record = json.loads(path.read_text(), parse_float=decimal.Decimal)
    except FileNotFoundError:
        return None, f"no record at {shown(path)}"
    except (OSError, ValueError) as exc:
        return None, f"{shown(path)} cannot be read ({type(exc).__name__})"
    value = record.get("elapsed_s") if isinstance(record, dict) else None
    if value is None:
        return None, f"{shown(path)} has no elapsed_s"
    # A bool is an int to Python, and an agent run never takes no time.
    if isinstance(value, bool) or not isinstance(value, (int, decimal.Decimal)) or value <= 0:
        return None, f"{shown(path)} has elapsed_s {value!r}, not a positive number of seconds"
    return decimal.Decimal(value), None


def minutes(seconds: decimal.Decimal) -> decimal.Decimal:
    """Seconds as minutes to one decimal place, rounded half up as a reader rounds. A float
    would turn 189 s, 3.15 minutes exactly, into 3.1."""
    return (seconds / MINUTE).quantize(TENTH, rounding=decimal.ROUND_HALF_UP)


def study_times(study: dict, results: pathlib.Path) -> dict:
    """One study: its gated questions, then each arm, the open-everything arm first and the
    rest in the file's order, with its trials on those questions and their median time."""
    name, arms = study["study"], list(study["arms"])
    open_arms = [arm for arm in arms if arm.startswith(OPEN)]
    require(len(open_arms) == 1, f"{name}: {len(open_arms)} open-everything arms {open_arms}, not one")
    unknown = sorted({t["arm"] for t in study["trials"]} - set(arms))
    require(not unknown, f"{name}: trials of arms the study does not list: {unknown}")
    gated = sorted({t["task"] for t in study["trials"] if t["arm"] == open_arms[0]})
    h2 = (study.get("h2") or {}).get("questions")
    if h2 is not None:
        require(sorted(h2) == gated, f"{name}: the open-everything arm ran {gated}, H2's questions "
                                     f"are {sorted(h2)}")
    rows, missing = [], []
    for arm in open_arms + [arm for arm in arms if arm not in open_arms]:
        mine = [t for t in study["trials"] if t["arm"] == arm and t["task"] in gated]
        times = []
        for trial in mine:
            seconds, why = read_time(results, trial)
            if seconds is None:
                missing.append({**{k: trial[k] for k in ("batch", "task", "repeat", "arm")}, "why": why})
            else:
                times.append(seconds)
        median = statistics.median(times) if times else None
        rows.append({"arm": arm, "questions": len({t["task"] for t in mine}), "trials": len(times),
                     "median_s": median, "median_min": None if median is None else minutes(median)})
    return {"study": name, "gated": gated, "checked_against_h2": h2 is not None,
            "rows": rows, "missing": missing}


def render(studies: list[dict], trials: pathlib.Path) -> str:
    lines = [f"Run times on the gated questions, run_times v{VERSION}",
             f"Trials: {shown(trials)}. Time: elapsed_s in each run record.",
             "Gated questions: in each study, the questions its open-everything arm ran.",
             "Median over an arm's trials on the gated questions it ran, in seconds, and in minutes "
             "rounded half up to one decimal place.", ""]
    for s in studies:
        check = ", the same as H2's" if s["checked_against_h2"] else ", not checked: the file gives no H2 questions"
        lines.append(f"{s['study']}: {len(s['gated'])} gated questions{check}")
        lines.append(f"  {'arm':34} {'questions':>10} {'trials':>7} {'median (s)':>11} {'median (min)':>13}")
        for r in s["rows"]:
            seconds = "-" if r["median_s"] is None else f"{r['median_s']:.2f}"
            mins = "-" if r["median_min"] is None else str(r["median_min"])
            lines.append(f"  {r['arm']:34} {r['questions']:>10} {r['trials']:>7} {seconds:>11} {mins:>13}")
        for m in s["missing"]:
            lines.append(f"  NO TIME, left out: {m['batch']}/{m['task']}-{m['repeat']} [{m['arm']}]: {m['why']}")
        lines.append("")
    count = sum(len(s["missing"]) for s in studies)
    lines.append("Every trial on the gated questions has a record with a positive elapsed_s." if not count
                 else f"{count} trials on the gated questions have no time, named above and left out of their medians.")
    return "\n".join(lines)


def run(trials: pathlib.Path, results: pathlib.Path) -> tuple[str, int]:
    """The printed table, and the exit status: 1 when a trial on the gated questions has no time."""
    studies = [study_times(study, results) for study in json.loads(trials.read_text())["studies"]]
    return render(studies, trials), 1 if any(s["missing"] for s in studies) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    try:
        text, status = run(TRIALS, paths.RESULTS)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Cannot compute the run times: {exc}\n")
    print(text)
    return status


if __name__ == "__main__":
    sys.exit(main())
