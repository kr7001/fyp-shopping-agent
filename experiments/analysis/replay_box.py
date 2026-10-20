#!/usr/bin/env python3
"""Replay the box's own answer check over every run of a batch made under the box, from
the stored page record, the stored form and the run's log alone.

A run record under the box keeps what the box read (the results page), what it parsed
(the form) and the exact text the agent got. Rebuilding the decision from those gives the
plan the agent had, checked byte for byte against the stored text, and `box.check` then
judges the stored answer against the log, as the suite does live. So a change to a check
is measured on stored runs before any paid run. Written on 20 October 2026 for the
counterexample check that reads the size menus, which until then refused five correct bare
"No" answers in the batches of 14 October.

Each run is also decided again today, from the same question and page with `box.decide`,
so a parser change that would now plan the question differently is listed rather than
hidden. Nothing here reads an answer key for the check; the key is read only to say which
runs were wrong, as `verify_cells` does.

    python3 experiments/analysis/replay_box.py experiments/results/<batch> [...]
    python3 experiments/analysis/replay_box.py experiments/results/<batch> --menus   # the reader against the fixture
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import box as box_module  # noqa: E402
import form as form_module  # noqa: E402
import page as page_module  # noqa: E402
import primitives  # noqa: E402
import score as scoring  # noqa: E402
import sufficiency  # noqa: E402
import verify_cells  # noqa: E402

WRONG = ("wrong", "ambiguous")


def stored_decision(row: dict) -> box_module.Decision:
    """The decision the box made for this row, rebuilt from its record: the page it read,
    the form it parsed and the plan composed from them again. The question is the first
    paragraph of the stored text, with any reading already written into it."""
    record = row["box"]
    page = page_module.from_record(record["page"]) if record.get("page") else None
    form = None
    if record.get("form"):
        form = form_module.from_record(record["form"], record["form"].get("source") or "rules")
    plan = primitives.compose(form, page) if record.get("plan") else None
    question = record["query"].split("\n\n", 1)[0]
    return box_module.Decision(question=question, kind=record["kind"], ask=None,
                               reading=record.get("reading"), query=record["query"],
                               plan=plan, page=page, form=form, refuse=record.get("refuse"),
                               bypass=bool(record.get("bypassed")))


def replay(batch: pathlib.Path) -> list[dict]:
    """One row per run the agent made under the box in this batch: the verdict under the
    current scorer, the box's check on the stored answer, whether the stored text is
    reproduced from the record, and whether the box would decide the same today."""
    suite = json.loads((batch / "suite.json").read_text())
    spec = json.loads((paths.TASKS / suite["tasks_file"]).read_text())
    tasks = {t["id"]: t for t in spec["tasks"]}
    readings = scoring.readings_for(paths.TASKS / suite["tasks_file"])
    rows = []
    for row in suite["rows"]:
        record = row.get("box")
        if not record or record.get("query") is None or not row.get("log"):
            continue    # the box asked or refused, so no agent ran
        run = json.loads((batch / f"{row['task']}-{row['repeat']}.json").read_text())
        result = run.get("result") or {}
        answer = str(result.get("final") or "")
        decision = stored_decision(row)
        reproduced = (decision.plan is None
                      or f"{decision.question}\n\n{decision.plan.text}" == record["query"])
        question = tasks[row["task"]]["query"].format(base=spec["base_url"])
        reply = row.get("reading") or suite.get("reading")
        today = box_module.decide(question, decision.page, reply=reply)
        verdict = box_module.check(decision, answer, batch / row["log"])
        rescored = verify_cells.rescore(tasks[row["task"]], answer,
                                        result.get("ok") in (True, "True"), row, suite, readings)
        rows.append({"batch": batch.name, "task": row["task"], "repeat": row["repeat"],
                     "verdict": rescored["verdict"], "ok": verdict["ok"],
                     "flag": verdict["flag"], "why": verdict["why"],
                     "opened": verdict.get("opened"), "primitive": verdict.get("primitive"),
                     "text_reproduced": reproduced, "same_today": today.query == record["query"]})
    return rows


def summary(rows: list[dict]) -> dict:
    """How the check did: the wrong runs it refused, and the others it refused."""
    wrong = [r for r in rows if r["verdict"] in WRONG]
    other = [r for r in rows if r["verdict"] not in WRONG]
    return {"runs": len(rows),
            "wrong": len(wrong), "wrong_refused": [tag(r) for r in wrong if not r["ok"]],
            "other": len(other), "other_refused": [tag(r) for r in other if not r["ok"]],
            "text_reproduced": sum(r["text_reproduced"] for r in rows),
            "same_today": sum(r["same_today"] for r in rows),
            "decided_differently_today": [tag(r) for r in rows if not r["same_today"]]}


def tag(row: dict) -> str:
    return f"{row['task']}-{row['repeat']}"


def menu_table(batch: pathlib.Path) -> list[dict]:
    """Every size menu reading in the batch's logs set against the fixture, one row per
    run and listing: what the run saw, whether it saw the whole menu, what the fixture
    says the menu is (its sizes in order, a sold-out size disabled), and whether the two
    agree, meaning a complete reading is the menu and a partial one is a prefix of it with
    the same disabled marks. The fixture is read here to validate the reader, never by the
    box (20 October 2026, after a find excerpt was read as a whole menu). It is the batch's
    own, named by its task file (`verify_cells.fixture_for`)."""
    suite = json.loads((batch / "suite.json").read_text())
    spec = json.loads((paths.TASKS / suite["tasks_file"]).read_text())
    truth = verify_cells.ground_truth(verify_cells.fixture_for(spec))
    rows = []
    for log_path in sorted(batch.glob("*.log")):
        for key, reading in sufficiency.size_menus(log_path).items():
            sku = key.split(":", 1)[1]
            fixture = {size: size in truth[sku]["buyable"] for size in truth[sku]["sizes"]} \
                if sku in truth else None
            seen = list(reading.options)
            if fixture is None:
                agrees = False
            elif reading.complete:
                agrees = reading.options == fixture
            else:
                agrees = seen == list(fixture)[:len(seen)] and all(
                    reading.options[size] == fixture[size] for size in seen)
            rows.append({"batch": batch.name, "run": log_path.stem, "listing": sku,
                         "reading": "complete" if reading.complete else "partial",
                         "seen": reading.options, "fixture": fixture, "agrees": agrees})
    return rows


def print_menu_table(rows: list[dict]) -> None:
    def menu(options: dict | None) -> str:
        return "?" if options is None else ", ".join(
            size + ("" if can else " [disabled]") for size, can in options.items())

    for r in rows:
        print(f"  {r['batch']} {r['run']:28} {r['listing']:12} {r['reading']:8} "
              f"{'ok ' if r['agrees'] else 'BAD'} saw {menu(r['seen'])}; fixture {menu(r['fixture'])}")
    complete = [r for r in rows if r["reading"] == "complete"]
    partial = [r for r in rows if r["reading"] == "partial"]
    print(f"{len(rows)} readings: {len(complete)} complete, {sum(r['agrees'] for r in complete)} equal "
          f"to the fixture's menu; {len(partial)} partial, {sum(r['agrees'] for r in partial)} a "
          f"prefix of it")


def report(rows: list[dict]) -> None:
    s = summary(rows)
    print(f"runs replayed {s['runs']}: stored text reproduced from the record "
          f"{s['text_reproduced']}, decided the same today {s['same_today']}")
    for name in ("wrong", "other"):
        refused = s[f"{name}_refused"]
        label = "wrong    " if name == "wrong" else "not wrong"
        print(f"{label}  {s[name]:>3} runs, refused by the check {len(refused)}"
              + (f": {', '.join(refused)}" if refused else ""))
    for r in rows:
        if not r["ok"]:
            print(f"  refused {r['batch']} {tag(r)} ({r['verdict']}): {r['flag']}, {r['why']}")
    for t in s["decided_differently_today"]:
        print(f"  decided differently today: {t}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", type=pathlib.Path)
    parser.add_argument("--rows", action="store_true", help="print every run's verdict and check")
    parser.add_argument("--menus", action="store_true",
                        help="print every size menu reading against the fixture, and nothing else")
    args = parser.parse_args()
    if args.menus:
        print_menu_table([r for batch in args.batches for r in menu_table(batch)])
        return 0
    rows = [r for batch in args.batches for r in replay(batch)]
    if args.rows:
        for r in rows:
            print(f"  {r['batch']} {tag(r):28} {r['verdict']:9} check {'ok' if r['ok'] else r['flag']:32} "
                  f"opened {r['opened']}  {r['why']}")
    report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
