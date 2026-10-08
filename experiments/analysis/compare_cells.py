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


def load() -> tuple[dict, dict]:
    truth = verify_cells.ground_truth()
    cells = {}
    for name, batches in CELLS.items():
        runs = [run for batch in batches for run in load_batch(batch)]
        # A run the laptop slept through measures the machine, not the agent, and is left
        # out rather than counted as a failure. See `verify_cells.SUSPENDED_AFTER_S`.
        void = [r for r in runs if r["longest_silence_s"] > verify_cells.SUSPENDED_AFTER_S]
        if void:
            print(f"{name}: leaving out {len(void)} suspended runs "
                  f"{[r['task'].replace('apparel-', '') + '-' + str(r['repeat']) for r in void]}")
        cells[name] = [r for r in runs if r["gated"] and r not in void]
    return cells, truth


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
