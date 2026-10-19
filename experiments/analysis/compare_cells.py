#!/usr/bin/env python3
"""Compare cells of the clothing matrix with tests that fit how the runs were made.

Two things were wrong with the comparisons first reported on 7 October 2026, and this is
the replacement for them.

**The runs are grouped by question.** Each cell asks the same five gated questions three
times, and the questions differ enormously in difficulty. Pooling fifteen runs into one
proportion and testing it with Fisher's exact test ignores that grouping. The test that
matches the design compares the cells within each question and combines the strata, the
exact conditional test for a common odds ratio of one. Both are printed, the pooled one
for continuity with what was reported.

**Some repeats are not repeats.** The second agent samples at temperature 0 and its page
text carries nothing that varies between runs, so on five of six questions its three
repeats are the same run three times, down to the token. Counting them as three
observations triples the evidence they carry. So repeats that are identical in token
counts and answer are collapsed before testing, and the run count that remains is printed.

The answer key is the one fixed before any run. A second key is printed beside it for the
two questions whose wording turned out to be ambiguous, see `READINGS`, as a sensitivity
check rather than a replacement.

    python experiments/analysis/compare_cells.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys
from math import comb

from scipy.stats import fisher_exact

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import verify_cells  # noqa: E402

RESULTS = paths.RESULTS

# Each cell is one batch, except where runs had to be replaced. Cell 5's first batch lost
# three runs to the laptop sleeping, see `verify_cells.SUSPENDED_AFTER_S`. Those three were
# re-run on the same day with byte-identical question text into batches of their own, and
# the suspended originals are left out by the same rule that found them, never by hand.
CELLS = {
    "1 openJiuwen, limit on": ["20261007T112057"],
    "2 openJiuwen, limit off": ["20261007T115021"],
    "3 second agent": ["20261007T134621"],
    "5 openJiuwen, open everything": ["20261008T034455", "20261008T143724", "20261008T144558"],
}

# The box's development cell: the three batches of 14 October 2026 under box v2 on
# Thornwood, the market the box was designed and tuned on, so in-sample and no claim
# (LESSONS 19). Kept apart from CELLS, which are the four claim-grade cells on one task
# file and one key: these batches ask tasks_apparel_v2.json, and the third answered the two
# "offer" questions under the other reading, so pooling them with the first would mix two
# keys. The tests against cells 1 and 5 use only the runs on the five questions those cells
# asked, scored under the key fixed before any run (`in_sample`); the other runs are listed.
DEVELOPMENT = {
    "box v2 development, Thornwood, in-sample": ["20261014T213118", "20261014T220116",
                                                 "20261014T222007"],
}

# "Does every listing offer size M" and "how many listings offer size M" both turn on the
# word offer. The key fixed before the runs reads it as "has M in its size menu", sold out
# or not, so the count is 10. Every agent that explained itself read it as "can sell M
# now", which makes the count 5 and makes a sold out M a counterexample. One run in cell 2
# listed all three groups correctly, 5 buyable, 5 sold out, 5 absent, and answered 5.
READINGS = ("menu", "buyable")


def correct(run: dict, reading: str) -> bool:
    if reading == "buyable" and run["task"] == "apparel-count-stocked":
        return verify_cells.scoring.score(
            {"expect": {"kind": "count", "value": 5}}, run["answer"], run["ok"]
        )["verdict"] == "correct"
    return run["rescored"] == "correct"


def covered(run: dict, reading: str, truth: dict) -> bool:
    """Opened what the answer depends on. Under the buyable reading a listing whose M is
    sold out is also a counterexample to "every listing offers M"."""
    if reading == "buyable" and run["task"] == "apparel-all-stocked":
        return any(truth[s]["m"] != "buyable" for s in run["skus"] if s in truth)
    return run["covered"]


def distinct(runs: list[dict]) -> list[dict]:
    """Drop repeats that are the same run again: same tokens, same answer."""
    seen, out = set(), []
    for run in runs:
        key = (run["task"], run["tokens"], run["answer"])
        if key in seen:
            continue
        seen.add(key)
        out.append(run)
    return out


def stratified_exact(strata: list[tuple[int, int, int, int]]) -> float:
    """Two sided exact conditional test of no difference within any stratum.

    Each stratum is (successes in A, runs in A, successes in B, runs in B). Within a
    stratum the successes in A are hypergeometric given the stratum's total, and the
    statistic is their sum across strata. Two sided in the same sense as Fisher's test:
    the probability of every outcome no more likely than the one observed.
    """
    dist = {0: 1.0}
    observed = 0
    for sa, na, sb, nb in strata:
        total, size = sa + sb, na + nb
        pmf = {k: comb(total, k) * comb(size - total, na - k) / comb(size, na)
               for k in range(max(0, total - nb), min(total, na) + 1)}
        nxt: dict[int, float] = collections.defaultdict(float)
        for t, p in dist.items():
            for k, q in pmf.items():
                nxt[t + k] += p * q
        dist = nxt
        observed += sa
    p_obs = dist[observed]
    return sum(p for p in dist.values() if p <= p_obs * (1 + 1e-9))


def load_batch(batch: str) -> list[dict]:
    """Every run in one batch, checked, with its token counts and its batch attached."""
    _, found = verify_cells.verify_batch(RESULTS / batch)
    for run in found:
        record = json.loads((RESULTS / batch / f"{run['task']}-{run['repeat']}.json")
                            .read_text())
        tokens = record.get("tokens") or (record.get("trace") or {}).get("tokens") or {}
        run["tokens"] = (tokens.get("prompt"), tokens.get("completion"))
        run["batch"] = batch
    return found


def load(which: dict[str, list[str]] | None = None) -> tuple[dict, dict]:
    """The gated runs of each cell in `which`, CELLS by default, with the fixture's truth."""
    truth = verify_cells.ground_truth()
    cells = {}
    for name, batches in (CELLS if which is None else which).items():
        runs = [run for batch in batches for run in load_batch(batch)]
        # A run the laptop slept through measures the machine, not the agent, and is left
        # out rather than counted as a failure. See `verify_cells.SUSPENDED_AFTER_S`.
        void = [r for r in runs if r["longest_silence_s"] > verify_cells.SUSPENDED_AFTER_S]
        if void:
            print(f"{name}: leaving out {len(void)} suspended runs "
                  f"{[r['task'].replace('apparel-', '') + '-' + str(r['repeat']) for r in void]}")
        cells[name] = [r for r in runs if r["gated"] and r not in void]
    return cells, truth


def in_sample(runs: list[dict], against: list[dict]) -> list[dict]:
    """The runs of a development cell that can be set against another cell: those on the
    questions the other cell asked, scored under the task's own key, the one fixed before
    any run. A run scored under a sidecar reading (`scored_under`) answered a different
    question and is left out (LESSONS 7)."""
    questions = {r["task"] for r in against}
    return [r for r in runs if r["task"] in questions and r.get("scored_under") is None]


def print_development(cells: dict, truth: dict) -> None:
    """The development cell after the four cells: every run by question, then the tests
    against cells 1 and 5 on the shared questions. In-sample, so no claim."""
    names = list(cells)
    development, _ = load(DEVELOPMENT)
    for name, runs in development.items():
        batches = DEVELOPMENT[name]
        suite = json.loads((RESULTS / batches[0] / "suite.json").read_text())
        questions = sorted({r["task"] for r in runs})
        print(f"\n=== {name}")
        print(f"In-sample, no claim: the box was designed and tuned on Thornwood (LESSONS 19), so "
              f"these are development figures,\nnot the claim, which needs a market the box was "
              f"not tuned on. Batches {', '.join(batches)} under box v{suite['box_version']}, "
              f"form v{suite['form_version']}, primitives v{suite['primitives_version']}:\n"
              f"{len(runs)} gated runs over {len(questions)} questions. The tests use the runs on "
              f"the questions cells 1 and 5 asked, scored under the key fixed before the runs;\n"
              f"a run scored under the other reading of 'offer' is listed, not tested.")
        print(f"\n  {'question':20} {'batch':16} {'key':9} correct  covered  opened")
        groups: dict[tuple, list[dict]] = collections.defaultdict(list)
        for run in runs:
            groups[(run["task"], run["batch"], run.get("scored_under") or "own")].append(run)
        for (task, batch, key), group in sorted(groups.items()):
            print(f"  {task.replace('apparel-', ''):20} {batch:16} {key:9} {sum(r['rescored'] == 'correct' for r in group)}/{len(group)}"
                  f"      {sum(r['covered'] for r in group)}/{len(group)}      {[r['opened'] for r in group]}")
        sample = in_sample(runs, cells[names[0]])
        shared = sorted({r["task"] for r in sample})
        opened = sorted(r["opened"] for r in sample)
        print(f"\n  on the {len(shared)} questions cells 1 and 5 asked, under the key fixed before "
              f"the runs: {len(sample)} runs, "
              f"{sum(correct(r, 'menu') for r in sample)} correct, "
              f"{sum(covered(r, 'menu', truth) for r in sample)} covered, "
              f"median {statistics.median(opened) if opened else '-'} opened, "
              f"${sum(r['cost'] or 0 for r in sample) / max(1, len(sample)):.3f} a run, "
              f"{sum(r['tool_calls'] or 0 for r in sample) / max(1, len(sample)):.0f} calls a run")
        for reading in READINGS:
            for label, measure in (("correct", lambda r: correct(r, reading)),
                                   ("covered", lambda r: covered(r, reading, truth))):
                for other in (names[0], names[3]):
                    text, pooled, strat = compare(sample, cells[other], measure)
                    print(f"    {reading:8} {label:8} box vs {other[:1]}  {text:26} "
                          f"pooled Fisher p={pooled:.5f}  by question p={strat:.5f}")


def compare(a: list[dict], b: list[dict], measure) -> tuple[str, float, float]:
    sa, sb = sum(map(measure, a)), sum(map(measure, b))
    pooled = fisher_exact([[sa, len(a) - sa], [sb, len(b) - sb]])[1]
    strata = []
    for task in sorted({r["task"] for r in a} | {r["task"] for r in b}):
        ra = [r for r in a if r["task"] == task]
        rb = [r for r in b if r["task"] == task]
        strata.append((sum(map(measure, ra)), len(ra), sum(map(measure, rb)), len(rb)))
    return f"{sa} of {len(a)} against {sb} of {len(b)}", pooled, stratified_exact(strata)


def main() -> int:
    cells, truth = load()
    names = list(cells)
    for name in names:
        unique = distinct(cells[name])
        runs = cells[name]
        cost = sum(r["cost"] or 0 for r in runs)
        print(f"{name:30} {len(runs)} gated runs, {len(unique)} distinct, "
              f"${cost / len(runs):.3f} a run, {sum(r['tool_calls'] or 0 for r in runs) / len(runs):.0f} calls a run")

    pairs = [(names[1], names[0]), (names[2], names[0]), (names[2], names[1]),
             (names[3], names[0]), (names[3], names[1])]
    for reading in READINGS:
        print(f"\n=== reading of 'offer': {reading}"
              + ("  (the key fixed before the runs)" if reading == "menu" else
                 "  (sensitivity check)"))
        for label, measure in (("correct", lambda r: correct(r, reading)),
                               ("covered", lambda r: covered(r, reading, truth))):
            print(f"\n  {label}")
            for name in names:
                runs = cells[name]
                per_q = {t: sum(measure(r) for r in runs if r["task"] == t)
                         for t in sorted({r["task"] for r in runs})}
                print(f"    {name:26} {sum(per_q.values()):>2} of {len(runs)}   "
                      + "  ".join(f"{t.replace('apparel-', '')} {v}" for t, v in per_q.items()))
            for x, y in pairs:
                for collapse in (False, True):
                    a = distinct(cells[x]) if collapse else cells[x]
                    b = distinct(cells[y]) if collapse else cells[y]
                    if collapse and len(a) == len(cells[x]) and len(b) == len(cells[y]):
                        continue
                    text, pooled, strat = compare(a, b, measure)
                    tag = "distinct runs only" if collapse else "every run"
                    print(f"    {x[:1]} vs {y[:1]}  {text:24} pooled Fisher p={pooled:.5f}  "
                          f"by question p={strat:.5f}   ({tag})")
    print_development(cells, truth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
