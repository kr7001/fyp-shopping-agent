#!/usr/bin/env python3
"""Print every figure the catch-up page reports about the clothing cells, from the raw runs.

The page's numbers are typed into HTML by hand, and on 7 October three of them were wrong.
This is the one command that recomputes all of them, so the page can be checked against it
line by line, before it is published and by anyone afterwards. It reads run files only,
plus one optional call to the provider's account endpoint for the cost cross-check.

    python experiments/analysis/cell_facts.py
    python experiments/analysis/cell_facts.py --no-account     # skip the account lookup

Sections A to G match the page: A and B the results, C the tests, D the kinds of error,
E the refusal check replayed, F how the runs were checked, G cost against the account.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import compare_cells  # noqa: E402
import policy  # noqa: E402
import score  # noqa: E402
import trace_stats  # noqa: E402

verify_cells = compare_cells.verify_cells
RESULTS = compare_cells.RESULTS
SPEC = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
TASKS = {t["id"]: t for t in SPEC["tasks"]}
PRICE_TASKS = ("apparel-target-price", "apparel-cheapest-target")
# The batch run just before cell 1, kept only because its charge settled inside cell 1.
PILOT = "20261007T111945"


def m_prices() -> dict[str, float | None]:
    """Each listing's price for size M, whether or not it can be bought."""
    fixture = json.loads(verify_cells.FIXTURE.read_text())
    out = {}
    for family in fixture["families"]:
        m = next((v for v in family["variants"] if v["option"] == "M"), None)
        out[family["parent_sku"].lower()] = m["price"] if m else None
    return out


def first_seller(answer: str, truth: dict) -> str | None:
    """The listing whose seller the answer names first, by the seller's first word."""
    low = answer.lower()
    hits = [(low.find(t["seller"].split()[0].lower()), sku) for sku, t in truth.items()]
    hits = [h for h in hits if h[0] >= 0]
    return min(hits)[1] if hits else None


def error_kinds(run: dict, truth: dict, m_price: dict) -> list[str]:
    """What went wrong in a run that was not correct, by written rules, not by eye.

    A run can have more than one kind. A run that fits none is reported as "other", so
    that nothing is dropped silently.
    """
    if run["rescored"] == "correct":
        return []
    kinds = []
    if not run["covered"]:
        kinds.append("did not open what the answer needs")
    if run["task"] in PRICE_TASKS:
        sku = first_seller(run["answer"], truth)
        prices = score.prices_in(run["answer"])
        if sku and truth[sku]["m"] != "buyable":
            kinds.append("named a seller that cannot sell M")
        elif sku and prices and abs(prices[0] - truth[sku]["from"]) < 0.005 \
                and abs(prices[0] - (m_price[sku] or 0)) >= 0.005:
            kinds.append("read the price before the page revealed it")
    if run["task"] == "apparel-count-stocked":
        opened = [s for s in run["skus"] if s in truth]
        sellable = sum(1 for s in opened if truth[s]["m"] == "buyable")
        if score.score({"expect": {"kind": "count", "value": sellable}}, run["answer"],
                       run["ok"])["verdict"] == "correct":
            kinds.append('read "offer" as "can sell it now"')
    if "max_iterations" in str(run["error"] or ""):
        kinds.append("ran out of its 100 steps")
    return kinds or ["other"]


def same_instant_scripts(log_path: pathlib.Path) -> int:
    """Scripts the agent wrote that change an option and read a price in one go."""
    count = 0
    for tool, _text, args in verify_cells.tool_replies(log_path).values():
        code = str(args.get("function", ""))
        if (tool == "browser_evaluate" and "dispatchEvent" in code
                and re.search(r"price", code, re.I)
                and "setTimeout" not in code and "await" not in code):
            count += 1
    return count


def batch_selections(log_path: pathlib.Path) -> int:
    """Sizes chosen inside browser_batch_interact steps."""
    total = 0
    for message in trace_stats.final_messages(log_path):
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if trace_stats.normalise(function.get("name") or "") == "browser_batch_interact":
                total += sum(1 for op in trace_stats.batch_ops(function.get("arguments"))
                             if op["op"] in trace_stats.SELECT_OPS)
    return total


def short(run: dict) -> str:
    return f"{run['task'].replace('apparel-', '')}-{run['repeat']}"


def account_usage() -> float | None:
    """Lifetime spend on the OpenRouter key, or None if it cannot be read."""
    try:
        import requests
        env = paths.ENV_FILE.read_text().splitlines()
        key = next(line.split("=", 1)[1].strip() for line in env
                   if line.startswith("OPENROUTER_API_KEY="))
        reply = requests.get("https://openrouter.ai/api/v1/key",
                             headers={"Authorization": f"Bearer {key}"}, timeout=20)
        return float(reply.json()["data"]["usage"])
    except Exception:
        return None


def facts(account: bool = True) -> dict:
    """Every figure in sections A to G, as data.

    `main` prints it and `docs/build_site.py` renders it on the site, so the command and the
    page are one computation and cannot disagree. Split out of `main` on 8 October 2026.
    """
    cells, truth = compare_cells.load()
    m_price = m_prices()
    names = list(cells)
    label = {name: name.split()[0] for name in names}
    questions = sorted({r["task"] for r in cells[names[0]]})
    suspended_after = verify_cells.SUSPENDED_AFTER_S

    # Every run in each cell's batches, control and suspended runs included, for costs and
    # for the checks that are about the batch rather than about the gated results.
    everything = {name: [run for batch in batches for run in compare_cells.load_batch(batch)]
                  for name, batches in compare_cells.CELLS.items()}

    out = {"names": names, "labels": label, "questions": questions, "cells": {},
           "tests": [], "errors": {}, "refusal": {}, "rescored": [], "silence": [],
           "agent_window": {}, "batch_selections": {}, "same_instant": {},
           "distinct_per_question": {}, "cost": [], "account_now": None}

    # A and B
    for name in names:
        runs, rows = cells[name], everything[name]
        control = [r for r in rows if not r["gated"]]
        void = [r for r in rows if r["longest_silence_s"] > suspended_after]
        out["cells"][name] = {
            "runs": len(runs),
            "distinct": len(compare_cells.distinct(runs)),
            "right": sum(compare_cells.correct(r, "menu") for r in runs),
            "right_buyable": sum(compare_cells.correct(r, "buyable") for r in runs),
            "opened": sum(compare_cells.covered(r, "menu", truth) for r in runs),
            "opened_buyable": sum(compare_cells.covered(r, "buyable", truth) for r in runs),
            "median_opened": statistics.median(r["opened"] for r in runs),
            "calls": statistics.mean(r["tool_calls"] or 0 for r in runs),
            "cost": statistics.mean(r["cost"] or 0 for r in runs),
            "control": ({"correct": sum(r["rescored"] == "correct" for r in control),
                         "of": len(control)} if control else None),
            "batch_runs": len(rows),
            "batch_cost": sum(r["cost"] or 0 for r in rows),
            "suspended": len(void),
            "suspended_cost": sum(r["cost"] or 0 for r in void),
            "per_question": {
                q: {"correct": sum(compare_cells.correct(r, "menu") for r in runs if r["task"] == q),
                    "covered": sum(r["covered"] for r in runs if r["task"] == q),
                    "of": sum(1 for r in runs if r["task"] == q)}
                for q in questions},
        }

    # C
    by = dict(zip(["1", "2", "3", "5"], names))
    pairs = [("2", "1", False), ("3", "1", True), ("3", "2", True), ("5", "1", False),
             ("5", "2", False)]
    for reading in compare_cells.READINGS:
        for what, measure in (("correct", lambda r: compare_cells.correct(r, reading)),
                              ("opened", lambda r: compare_cells.covered(r, reading, truth))):
            for x, y, collapse in pairs:
                a, b = cells[by[x]], cells[by[y]]
                if collapse:
                    a, b = compare_cells.distinct(a), compare_cells.distinct(b)
                text, pooled, strat = compare_cells.compare(a, b, measure)
                out["tests"].append({"reading": reading, "measure": what, "a": x, "b": y,
                                     "distinct": collapse, "text": text,
                                     "p_question": strat, "p_pooled": pooled})

    # D
    for name in names:
        tally = collections.defaultdict(list)
        for run in compare_cells.distinct(cells[name]):
            for kind in error_kinds(run, truth, m_price):
                tally[kind].append(short(run))
        out["errors"][name] = sorted(tally.items())

    # E
    for name in names:
        if label[name] == "3":
            continue
        wrong = refused = right_refused = right = 0
        for run in cells[name]:
            verdict = policy.gate(TASKS[run["task"]], SPEC, run["answer"],
                                  RESULTS / run["batch"] / f"{run['task']}-{run['repeat']}.log")
            if run["rescored"] == "correct":
                right += 1
                right_refused += bool(verdict["flag"])
            else:
                wrong += 1
                refused += bool(verdict["flag"])
        out["refusal"][name] = {"wrong": wrong, "refused": refused, "right": right,
                                "right_refused": right_refused}

    # F
    for name in names:
        for batch in compare_cells.CELLS[name]:
            suite = json.loads((RESULTS / batch / "suite.json").read_text())
            for entry in suite.get("rescored") or []:
                for change in entry["changed"]:
                    out["rescored"].append({"batch": batch,
                                            "run": f"{change['task']}-{change['repeat']}",
                                            "from": change["from"], "to": change["to"],
                                            "reason": entry["reason"]})
    for name in names:
        for batch in compare_cells.CELLS[name]:
            rows = [r for r in everything[name] if r["batch"] == batch]
            out["silence"].append({
                "batch": batch, "cell": label[name],
                "longest_silence_s": max(r["longest_silence_s"] for r in rows),
                "longest_run_s": max(r["elapsed_s"] or 0 for r in rows),
                "suspended": [[short(r), r["longest_silence_s"]] for r in rows
                              if r["longest_silence_s"] > suspended_after]})
    for name in names:
        rows = everything[name]
        out["agent_window"][name] = {
            "runs": [short(r) for r in rows if r.get("agent_set_window")], "of": len(rows)}
        out["batch_selections"][name] = sum(
            batch_selections(RESULTS / r["batch"] / f"{r['task']}-{r['repeat']}.log")
            for r in rows)
        scripts = [(short(r), same_instant_scripts(
                        RESULTS / r["batch"] / f"{r['task']}-{r['repeat']}.log"))
                   for r in rows]
        out["same_instant"][name] = {"runs": [[t, n] for t, n in scripts if n], "of": len(rows)}
        per = collections.Counter()
        for run in compare_cells.distinct([r for r in rows
                                           if r["longest_silence_s"] <= suspended_after]):
            per[run["task"].replace("apparel-", "")] += 1
        out["distinct_per_question"][name] = dict(sorted(per.items()))

    # G
    order = sorted(set([PILOT] + [b for name in names for b in compare_cells.CELLS[name]]))
    first, totals = {}, {}
    for batch in order:
        records = [json.loads(p.read_text()) for p in (RESULTS / batch).glob("apparel-*.json")]
        befores = [r["spend_before_usd"] for r in records if r.get("spend_before_usd")]
        first[batch] = min(befores) if befores else None
        totals[batch] = sum(r.get("cost_usd") or 0 for r in records)
    now = account_usage() if account else None
    for i, batch in enumerate(order):
        nxt = first[order[i + 1]] if i + 1 < len(order) else now
        moved = (nxt - first[batch]) if nxt is not None and first[batch] is not None else None
        out["cost"].append({"batch": batch, "charges": totals[batch], "moved": moved})
    out["account_now"] = now
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-account", action="store_true")
    args = parser.parse_args()

    f = facts(account=not args.no_account)
    names, label, cells = f["names"], f["labels"], f["cells"]

    print("\nA. EACH CELL, THE FIVE GATED QUESTIONS")
    print(f"{'cell':32} {'runs':>4} {'diff':>4} {'right':>6} {'right*':>6} {'opened':>6} "
          f"{'opened*':>7} {'median':>6} {'calls':>5} {'$/run':>6}")
    for name in names:
        c = cells[name]
        print(f"{name:32} {c['runs']:>4} {c['distinct']:>4} {c['right']:>6} "
              f"{c['right_buyable']:>6} {c['opened']:>6} {c['opened_buyable']:>7} "
              f"{c['median_opened']:>6} {c['calls']:>5.0f} {c['cost']:>6.3f}")
    print("right = correct under the answer key, right* = under the 'can sell it now' reading")
    print("opened = opened every listing the answer needs, opened* = the same under that reading")
    print("diff = runs that are not a replay of another run, same tokens and same answer")
    print("\nthe control question, answerable from the results page")
    for name in names:
        if cells[name]["control"]:
            print(f"  {name:32} {cells[name]['control']['correct']} of "
                  f"{cells[name]['control']['of']}")
    print("\nwhole batches, every run, control and suspended runs included")
    for name in names:
        c = cells[name]
        print(f"  {name:32} {c['batch_runs']} runs, ${c['batch_cost']:.4f}"
              + (f", of which {c['suspended']} suspended ${c['suspended_cost']:.4f}"
                 if c["suspended"] else ""))

    print("\nB. EACH QUESTION, correct / opened what the answer needs, the answer key")
    questions = f["questions"]
    print(f"{'cell':32} " + " ".join(f"{q.replace('apparel-', ''):>17}" for q in questions))
    for name in names:
        per = cells[name]["per_question"]
        cols = [f"{per[q]['correct']}/{per[q]['covered']} of {per[q]['of']}" for q in questions]
        print(f"{name:32} " + " ".join(f"{c:>17}" for c in cols))

    print("\nC. TESTS, two sided exact. 'by question' compares within each question first")
    for reading in compare_cells.READINGS:
        print(f"  reading of offer: {reading}")
        for t in (t for t in f["tests"] if t["reading"] == reading):
            print(f"    {t['a']} vs {t['b']} {t['measure']:8} {t['text']:26} "
                  f"by question p={t['p_question']:.5f}  pooled p={t['p_pooled']:.5f}"
                  + ("   (distinct runs)" if t["distinct"] else ""))

    print("\nD. KINDS OF ERROR, every gated run that was not correct. Cell 3 counts distinct "
          "runs")
    for name in names:
        print(f"  {name}")
        for kind, which in f["errors"][name]:
            print(f"    {len(which):>2}  {kind:44} {', '.join(which)}")

    print("\nE. THE REFUSAL CHECK, replayed over finished runs")
    for name, r in f["refusal"].items():
        print(f"  {name:32} not correct {r['wrong']:>2}, refused {r['refused']:>2}   "
              f"correct {r['right']:>2}, refused {r['right_refused']}")

    print("\nF. HOW THE RUNS WERE CHECKED")
    for r in f["rescored"]:
        print(f"  re-scored {r['batch']} {r['run']}: {r['from']} -> {r['to']}  ({r['reason']})")
    print("  problems the checker finds, per batch (suspended runs are expected in cell 5)")
    for s in f["silence"]:
        # The second agent's log has no timestamps, so silence cannot be measured there.
        # Its whole runs are short, so a suspension would show in their durations.
        gap = (f"longest silence {s['longest_silence_s']:.0f}s" if s["longest_silence_s"] else
               f"no timestamps in this log, longest whole run {s['longest_run_s']:.0f}s")
        void = [f"{run} {silent:.0f}s" for run, silent in s["suspended"]]
        print(f"    {s['batch']} ({s['cell']})  {gap}"
              + (f"  suspended: {', '.join(void)}" if void else "  none suspended"))
    print("  the agent passed viewport_only itself, runs")
    for name in names:
        w = f["agent_window"][name]
        print(f"    {name:32} {len(w['runs'])} of {w['of']}"
              + (f": {', '.join(w['runs'])}" if w["runs"] else ""))
    print("  sizes chosen inside batch steps, every run in the cell's batches")
    for name in names:
        print(f"    {name:32} {f['batch_selections'][name]}")
    print("  scripts that change a size and read the price in one go, runs that wrote them")
    for name in names:
        s = f["same_instant"][name]
        rows = [f"{t} ({n})" for t, n in s["runs"]]
        print(f"    {name:32} {len(rows)} of {s['of']}"
              + (f": {', '.join(rows)}" if rows else ""))
    print("  distinct runs among each question's three repeats")
    for name in names:
        print(f"    {name:32} " + "  ".join(f"{k} {v}" for k, v in
                                           f["distinct_per_question"][name].items()))

    print("\nG. COST, the provider's charge per call summed, against the account itself")
    for c in f["cost"]:
        print(f"  {c['batch']}  charges ${c['charges']:.4f}   account moved "
              + (f"${c['moved']:.4f}   difference ${c['moved'] - c['charges']:+.4f}"
                 if c["moved"] is not None else "(no account reading)"))
    if f["account_now"] is not None:
        print(f"  account used now ${f['account_now']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
