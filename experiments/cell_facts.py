#!/usr/bin/env python3
"""Print every figure the catch-up page reports about the clothing cells, from the raw runs.

The page's numbers are typed into HTML by hand, and on 7 October three of them were wrong.
This is the one command that recomputes all of them, so the page can be checked against it
line by line, before it is published and by anyone afterwards. It reads run files only,
plus one optional call to the provider's account endpoint for the cost cross-check.

    python experiments/cell_facts.py
    python experiments/cell_facts.py --no-account     # skip the account lookup

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

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_cells  # noqa: E402
import policy  # noqa: E402
import score  # noqa: E402
import trace_stats  # noqa: E402

verify_cells = compare_cells.verify_cells
RESULTS = compare_cells.RESULTS
SPEC = json.loads((HERE / "tasks_apparel.json").read_text())
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
        env = (HERE.parent / ".env").read_text().splitlines()
        key = next(line.split("=", 1)[1].strip() for line in env
                   if line.startswith("OPENROUTER_API_KEY="))
        reply = requests.get("https://openrouter.ai/api/v1/key",
                             headers={"Authorization": f"Bearer {key}"}, timeout=20)
        return float(reply.json()["data"]["usage"])
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-account", action="store_true")
    args = parser.parse_args()

    cells, truth = compare_cells.load()
    m_price = m_prices()
    names = list(cells)
    label = {name: name.split()[0] for name in names}

    # Every run in each cell's batches, control and suspended runs included, for costs and
    # for the checks that are about the batch rather than about the gated results.
    everything = {name: [run for batch in batches for run in compare_cells.load_batch(batch)]
                  for name, batches in compare_cells.CELLS.items()}

    print("\nA. EACH CELL, THE FIVE GATED QUESTIONS")
    print(f"{'cell':32} {'runs':>4} {'diff':>4} {'right':>6} {'right*':>6} {'opened':>6} "
          f"{'opened*':>7} {'median':>6} {'calls':>5} {'$/run':>6}")
    for name in names:
        runs = cells[name]
        n = len(runs)
        print(f"{name:32} {n:>4} {len(compare_cells.distinct(runs)):>4} "
              f"{sum(compare_cells.correct(r, 'menu') for r in runs):>6} "
              f"{sum(compare_cells.correct(r, 'buyable') for r in runs):>6} "
              f"{sum(compare_cells.covered(r, 'menu', truth) for r in runs):>6} "
              f"{sum(compare_cells.covered(r, 'buyable', truth) for r in runs):>7} "
              f"{statistics.median(r['opened'] for r in runs):>6} "
              f"{statistics.mean(r['tool_calls'] or 0 for r in runs):>5.0f} "
              f"{statistics.mean(r['cost'] or 0 for r in runs):>6.3f}")
    print("right = correct under the answer key, right* = under the 'can sell it now' reading")
    print("opened = opened every listing the answer needs, opened* = the same under that reading")
    print("diff = runs that are not a replay of another run, same tokens and same answer")
    print("\nthe control question, answerable from the results page")
    for name in names:
        control = [r for r in everything[name] if not r["gated"]]
        if control:
            print(f"  {name:32} {sum(r['rescored'] == 'correct' for r in control)} of "
                  f"{len(control)}")
    print("\nwhole batches, every run, control and suspended runs included")
    for name in names:
        rows = everything[name]
        void = [r for r in rows if r["longest_silence_s"] > verify_cells.SUSPENDED_AFTER_S]
        print(f"  {name:32} {len(rows)} runs, ${sum(r['cost'] or 0 for r in rows):.4f}"
              + (f", of which {len(void)} suspended ${sum(r['cost'] or 0 for r in void):.4f}"
                 if void else ""))

    print("\nB. EACH QUESTION, correct / opened what the answer needs, the answer key")
    questions = sorted({r["task"] for r in cells[names[0]]})
    print(f"{'cell':32} " + " ".join(f"{q.replace('apparel-', ''):>17}" for q in questions))
    for name in names:
        runs = cells[name]
        cols = []
        for q in questions:
            rows = [r for r in runs if r["task"] == q]
            cols.append(f"{sum(compare_cells.correct(r, 'menu') for r in rows)}/"
                        f"{sum(r['covered'] for r in rows)} of {len(rows)}")
        print(f"{name:32} " + " ".join(f"{c:>17}" for c in cols))

    print("\nC. TESTS, two sided exact. 'by question' compares within each question first")
    by = dict(zip(["1", "2", "3", "5"], names))
    pairs = [("2", "1", False), ("3", "1", True), ("3", "2", True), ("5", "1", False),
             ("5", "2", False)]
    for reading in compare_cells.READINGS:
        print(f"  reading of offer: {reading}")
        for what, measure in (("correct", lambda r: compare_cells.correct(r, reading)),
                              ("opened", lambda r: compare_cells.covered(r, reading, truth))):
            for x, y, collapse in pairs:
                a, b = cells[by[x]], cells[by[y]]
                if collapse:
                    a, b = compare_cells.distinct(a), compare_cells.distinct(b)
                text, pooled, strat = compare_cells.compare(a, b, measure)
                print(f"    {x} vs {y} {what:8} {text:26} by question p={strat:.5f}  "
                      f"pooled p={pooled:.5f}" + ("   (distinct runs)" if collapse else ""))

    print("\nD. KINDS OF ERROR, every gated run that was not correct. Cell 3 counts distinct "
          "runs")
    for name in names:
        runs = compare_cells.distinct(cells[name])
        tally = collections.defaultdict(list)
        for run in runs:
            for kind in error_kinds(run, truth, m_price):
                tally[kind].append(short(run))
        print(f"  {name}")
        for kind, which in sorted(tally.items()):
            print(f"    {len(which):>2}  {kind:44} {', '.join(which)}")

    print("\nE. THE REFUSAL CHECK, replayed over finished runs")
    for name in names:
        runs = cells[name]
        if label[name] == "3":
            continue
        wrong = refused = right_refused = right = 0
        for run in runs:
            verdict = policy.gate(TASKS[run["task"]], SPEC, run["answer"],
                                  RESULTS / run["batch"] / f"{run['task']}-{run['repeat']}.log")
            if run["rescored"] == "correct":
                right += 1
                right_refused += bool(verdict["flag"])
            else:
                wrong += 1
                refused += bool(verdict["flag"])
        print(f"  {name:32} not correct {wrong:>2}, refused {refused:>2}   "
              f"correct {right:>2}, refused {right_refused}")

    print("\nF. HOW THE RUNS WERE CHECKED")
    for name in names:
        for batch in compare_cells.CELLS[name]:
            suite = json.loads((RESULTS / batch / "suite.json").read_text())
            for entry in suite.get("rescored") or []:
                for change in entry["changed"]:
                    print(f"  re-scored {batch} {change['task']}-{change['repeat']}: "
                          f"{change['from']} -> {change['to']}  ({entry['reason']})")
    print("  problems the checker finds, per batch (suspended runs are expected in cell 5)")
    for name in names:
        for batch in compare_cells.CELLS[name]:
            rows = [r for r in everything[name] if r["batch"] == batch]
            silent = max(r["longest_silence_s"] for r in rows)
            void = [f"{short(r)} {r['longest_silence_s']:.0f}s" for r in rows
                    if r["longest_silence_s"] > verify_cells.SUSPENDED_AFTER_S]
            # The second agent's log has no timestamps, so silence cannot be measured there.
            # Its whole runs are short, so a suspension would show in their durations.
            gap = (f"longest silence {silent:.0f}s" if silent else
                   f"no timestamps in this log, longest whole run "
                   f"{max(r['elapsed_s'] or 0 for r in rows):.0f}s")
            print(f"    {batch} ({label[name]})  {gap}"
                  + (f"  suspended: {', '.join(void)}" if void else "  none suspended"))
    print("  the agent passed viewport_only itself, runs")
    for name in names:
        rows = [short(r) for r in everything[name] if r.get("agent_set_window")]
        print(f"    {name:32} {len(rows)} of {len(everything[name])}"
              + (f": {', '.join(rows)}" if rows else ""))
    print("  sizes chosen inside batch steps, every run in the cell's batches")
    for name in names:
        rows = everything[name]
        total = sum(batch_selections(RESULTS / r["batch"] / f"{r['task']}-{r['repeat']}.log")
                    for r in rows)
        print(f"    {name:32} {total}")
    print("  scripts that change a size and read the price in one go, runs that wrote them")
    for name in names:
        rows = [(short(r), same_instant_scripts(
                    RESULTS / r["batch"] / f"{r['task']}-{r['repeat']}.log"))
                for r in everything[name]]
        rows = [f"{t} ({n})" for t, n in rows if n]
        print(f"    {name:32} {len(rows)} of {len(everything[name])}"
              + (f": {', '.join(rows)}" if rows else ""))
    print("  distinct runs among each question's three repeats")
    for name in names:
        rows = [r for r in everything[name] if r["longest_silence_s"]
                <= verify_cells.SUSPENDED_AFTER_S]
        per = collections.Counter()
        for run in compare_cells.distinct(rows):
            per[run["task"].replace("apparel-", "")] += 1
        print(f"    {name:32} " + "  ".join(f"{k} {v}" for k, v in sorted(per.items())))

    print("\nG. COST, the provider's charge per call summed, against the account itself")
    order = [PILOT] + [b for name in names for b in compare_cells.CELLS[name]]
    order = sorted(set(order))
    first = {}
    totals = {}
    for batch in order:
        records = [json.loads(p.read_text()) for p in (RESULTS / batch).glob("apparel-*.json")]
        befores = [r["spend_before_usd"] for r in records if r.get("spend_before_usd")]
        first[batch] = min(befores) if befores else None
        totals[batch] = sum(r.get("cost_usd") or 0 for r in records)
    now = None if args.no_account else account_usage()
    for i, batch in enumerate(order):
        nxt = first[order[i + 1]] if i + 1 < len(order) else now
        moved = (nxt - first[batch]) if nxt is not None and first[batch] is not None else None
        print(f"  {batch}  charges ${totals[batch]:.4f}   account moved "
              + (f"${moved:.4f}   difference ${moved - totals[batch]:+.4f}" if moved is not None
                 else "(no account reading)"))
    if now is not None:
        print(f"  account used now ${now:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
