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

A stored text is compared under the version that ran (20 October 2026): the plan is
recomposed with today's code from the stored form, with the stored run's own box-exhaust
flag, and every rewording made since its box version is swapped back (`box.as_sent_by`)
before the comparison, so a reworded sentence is not taken for a plan that changed. A text
that still differs is listed with its first differing line. Today's decision is the same,
or differs for a deliberate change named here (a question the box now refuses, a limit
read strictly since form v9, checked to be the only difference), or differs unexpectedly,
which is listed with its first differing line.

    python3 experiments/analysis/replay_box.py experiments/results/<batch> [...]
    python3 experiments/analysis/replay_box.py experiments/results/<batch> --menus   # the reader against the fixture
"""

from __future__ import annotations

import argparse
import dataclasses
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
    the form it parsed and the plan composed from them again, without its stop rule when
    the run was the box without its stop rule (`--box-exhaust`), and over the one product's
    listings the record's scope kept, when it kept some (box v17). The question is the first
    paragraph of the stored text, with any reading already written into it."""
    record = row["box"]
    page = page_module.from_record(record["page"]) if record.get("page") else None
    form = None
    if record.get("form"):
        form = form_module.from_record(record["form"], record["form"].get("source") or "rules")
    exhaust = bool(record.get("exhaust"))
    # Over the listings the plan ranged over (box v17): one product's, when it was scoped.
    scope = box_module.Scope.from_record(record.get("scope"))
    planned = scope.apply(page) if scope is not None else page
    # With the rate plan it ran under (box v18); a record before the field had the bound.
    rate = record.get("rate_plan") or "bound"
    plan = primitives.compose(form, planned, exhaust=exhaust, rate=rate) if record.get("plan") else None
    question = record["query"].split("\n\n", 1)[0]
    return box_module.Decision(question=question, kind=record["kind"], ask=None,
                               reading=record.get("reading"), query=record["query"],
                               plan=plan, page=page, form=form, refuse=record.get("refuse"),
                               bypass=bool(record.get("bypassed")), exhaust=exhaust, scope=scope,
                               rate=rate)


def parsed_by(record: dict) -> dict:
    """How the run's question is read again today: by the rules, as every batch before 22
    October 2026 was, or, for a run made under the model parser, by the model parser with
    the run's own stored reply as its call, so the decision is made again with no call
    (LESSONS 29). A run whose call failed has no reply, and fails again the same way."""
    parse = record.get("parse") or {}
    if parse.get("parser") != "model":
        return {}
    stored = parse.get("reply")

    def call(prompt: str) -> str:
        if stored is None:
            raise RuntimeError("the stored run's parse call failed, so it holds no reply")
        return stored

    return {"parser": "model", "call": call}


def first_difference(stored: str | None, today: str | None) -> str:
    """The first line where two texts differ, both sides quoted from just before the first
    character that differs, for a text that should have reproduced and did not."""
    old, new = (stored or "").split("\n"), (today or "").split("\n")
    for n, (a, b) in enumerate(zip(old, new)):
        if a != b:
            at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            start = max(0, at - 40)
            lead = "..." if start else ""
            return f"line {n + 1}: stored {lead}{a[start:at + 100]!r}, today {lead}{b[start:at + 100]!r}"
    if len(old) != len(new):
        return f"stored {len(old)} lines, today {len(new)}"
    return "no line differs"


def as_sent(text: str | None, record: dict) -> str | None:
    """Today's text in the words of the box version the stored run was sent under."""
    return box_module.as_sent_by(text, record.get("box_version"))


def reproduction(decision: box_module.Decision, record: dict) -> str:
    """Empty when the stored text is reproduced from the record under its version, else the
    first line that differs. A bypassed run's text is the question itself."""
    if decision.plan is None:
        return ""
    rendered = as_sent(f"{decision.question}\n\n{decision.plan.text}", record)
    return "" if rendered == record["query"] else first_difference(record["query"], rendered)


def compared_today(today: box_module.Decision, record: dict) -> tuple[str, str]:
    """("same", ""), ("expected", the deliberate change), or ("unexpected", the first line
    that differs): today's decision on the stored question and page, against the stored one.

    Two changes are deliberate and named. A question the box now refuses for an attribute
    the shop does not show (box v7, form v5, 20 October 2026). And a price limit read
    strictly since form v9 (box v10): only when the stored form read it as "<=", today's as
    "<", and today's form with the old operator renders the stored text exactly, so the
    operator is shown to be the only difference."""
    if today.query is not None and as_sent(today.query, record) == record["query"]:
        return "same", ""
    if today.refuse and not record.get("refuse"):
        return "expected", f"refused today: {today.refuse.split(',')[0]}"
    stored_limit = next((f for f in (record.get("form") or {}).get("filters") or []
                         if f.get("attribute") == "price"), None)
    limit = today.form.filter("price") if today.form is not None else None
    if stored_limit and stored_limit.get("op") == "<=" and limit is not None and limit.op == "<":
        old = dataclasses.replace(today.form, filters=tuple(
            dataclasses.replace(f, op="<=") if f is limit else f for f in today.form.filters))
        plan = primitives.compose(old, today.planned, exhaust=today.exhaust, rate=today.rate)
        if as_sent(f"{today.question}\n\n{plan.text}", record) == record["query"]:
            return "expected", f"the limit is strict since form v9 (price < {limit.value:g})"
    return "unexpected", first_difference(record["query"], as_sent(today.query, record))


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
        differs = reproduction(decision, record)
        question = tasks[row["task"]]["query"].format(base=spec["base_url"])
        reply = row.get("reading") or suite.get("reading")
        today = box_module.decide(question, decision.page, reply=reply, exhaust=decision.exhaust,
                                  rate=decision.rate, **parsed_by(record))
        status, change = compared_today(today, record)
        verdict = box_module.check(decision, answer, batch / row["log"])
        rescored = verify_cells.rescore(tasks[row["task"]], answer,
                                        result.get("ok") in (True, "True"), row, suite, readings)
        rows.append({"batch": batch.name, "task": row["task"], "repeat": row["repeat"],
                     "verdict": rescored["verdict"], "ok": verdict["ok"],
                     "flag": verdict["flag"], "why": verdict["why"],
                     "opened": verdict.get("opened"), "primitive": verdict.get("primitive"),
                     "text_reproduced": not differs, "differs": differs,
                     "same_today": status == "same", "today": status, "change": change})
    return rows


def summary(rows: list[dict]) -> dict:
    """How the check did: the wrong runs it refused, and the others it refused. Then how
    the replay did: the stored texts reproduced under their version, with any that were not
    and the line where each first differs; the runs decided the same today; those that
    differ today for a deliberate change, with the change; and those that differ for any
    other reason (`decided_differently_today`), each of which wants explaining."""
    wrong = [r for r in rows if r["verdict"] in WRONG]
    other = [r for r in rows if r["verdict"] not in WRONG]
    return {"runs": len(rows),
            "wrong": len(wrong), "wrong_refused": [tag(r) for r in wrong if not r["ok"]],
            "other": len(other), "other_refused": [tag(r) for r in other if not r["ok"]],
            "text_reproduced": sum(r["text_reproduced"] for r in rows),
            "not_reproduced": [f"{tag(r)}: {r['differs']}" for r in rows if not r["text_reproduced"]],
            "same_today": sum(r["same_today"] for r in rows),
            "expected_today": [f"{tag(r)}: {r['change']}" for r in rows if r["today"] == "expected"],
            "decided_differently_today": [tag(r) for r in rows if r["today"] == "unexpected"],
            "unexpected_today": [f"{tag(r)}: {r['change']}" for r in rows if r["today"] == "unexpected"]}


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
    for t in s["not_reproduced"]:
        print(f"  stored text not reproduced: {t}")
    for t in s["expected_today"]:
        print(f"  decided differently today, as expected: {t}")
    for t in s["unexpected_today"]:
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
