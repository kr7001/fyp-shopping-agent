#!/usr/bin/env python3
"""Reanalyse the released Wexcombe and Quenby measurements, without API calls.

Python standard library only. This reproduces primary human-scored counts, medians
and exact tests from derived metrics; it does not recount private browser traces.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "experiments/artifacts/report-metrics-31-oct.json"
RUN_FIELDS = {"arm", "task", "repeat", "hand_verdict", "automatic_verdict", "outcome", "opened", "cost_usd"}
ARMS = {"the block (model)": "block_model", "the block (rules)": "block_rules",
        "shipped": "shipped", "open everything (product)": "exhaustive"}
CLOSED = "closed by the box"


def exact_correctness(strata):
    """Two-sided conditional test, stratified by question (or H4 template).

    Matches compare_cells.stratified_exact: convolve hypergeometric distributions,
    then sum outcomes no more probable than the observed total number correct.
    """
    distribution, observed = {0: 1.0}, 0
    for sa, na, sb, nb in strata:
        total, size = sa + sb, na + nb
        pmf = {k: math.comb(total, k) * math.comb(size - total, na - k) / math.comb(size, na)
               for k in range(max(0, total - nb), min(total, na) + 1)}
        following = defaultdict(float)
        for x, p in distribution.items():
            for y, q in pmf.items():
                following[x + y] += p * q
        distribution = following
        observed += sa
    observed_probability = distribution[observed]
    return min(1.0, sum(p for p in distribution.values() if p <= observed_probability * (1 + 1e-9)))


def exact_ranks(strata):
    """Equal-weight van Elteren test with mid-ranks and exact within-stratum splits.

    Matches claim.stratified_rank_test. Two-sided tail: absolute distance from
    the null mean. Costs are ranked as recorded, without rounding before testing.
    """
    distribution, observed, mean = {0.0: 1.0}, 0.0, 0.0
    for a, b in strata:
        ordered = sorted(a + b)
        ranks_by_value = {value: sum(i + 1 for i, x in enumerate(ordered) if x == value) / ordered.count(value)
                          for value in set(ordered)}
        ranks = [ranks_by_value[value] for value in a + b]
        observed += sum(ranks[:len(a)])
        splits = list(combinations(range(len(ranks)), len(a)))
        counts = Counter(round(sum(ranks[i] for i in subset), 6) for subset in splits)
        pmf = {value: count / len(splits) for value, count in counts.items()}
        mean += sum(value * p for value, p in pmf.items())
        following = defaultdict(float)
        for x, p in distribution.items():
            for y, q in pmf.items():
                following[round(x + y, 6)] += p * q
        distribution = following
    deviation = abs(observed - mean)
    p = sum(probability for value, probability in distribution.items() if abs(value - mean) >= deviation - 1e-9)
    return min(1.0, p)


def holm(pvalues):
    """Step-down adjustment across the complete prespecified family."""
    adjusted, running = {}, 0.0
    for i, name in enumerate(sorted(pvalues, key=pvalues.get)):
        running = max(running, min(1.0, (len(pvalues) - i) * pvalues[name]))
        adjusted[name] = running
    return adjusted


def correct(run):
    # A closed slot has no human answer grade. The frozen protocol counts it wrong.
    if run["outcome"] == CLOSED:
        return False
    if run["hand_verdict"] == "unscorable":
        return None
    return run["hand_verdict"] == "correct"


def validate_runs(runs, expected):
    seen = set()
    for run in runs:
        if set(run) != RUN_FIELDS:
            raise ValueError("unexpected or missing metric fields")
        if type(run["repeat"]) is not int or run["repeat"] < 1:
            raise ValueError("repeat must be a positive integer")
        key = run["arm"], run["task"], run["repeat"]
        if key in seen:
            raise ValueError("duplicate arm/task/repeat")
        seen.add(key)
        if run["outcome"] not in {"answered", "reported, not correct", CLOSED}:
            raise ValueError("unknown trial outcome")
        if run["outcome"] == CLOSED:
            if run["hand_verdict"] is not None or run["automatic_verdict"] != CLOSED:
                raise ValueError("a closed slot has no human answer grade")
        elif run["hand_verdict"] not in {"correct", "not correct", "unscorable"}:
            raise ValueError("a reviewed answer needs an explicit human verdict")
        if run["automatic_verdict"] not in {"correct", "wrong", "failed", "abstained", "unscored", CLOSED}:
            raise ValueError("unknown automatic verdict")
        if type(run["opened"]) is not int or run["opened"] < 0:
            raise ValueError("opened must be a nonnegative integer")
        charge = run["cost_usd"]
        if type(charge) not in (int, float) or not math.isfinite(charge) or charge < 0:
            raise ValueError("cost_usd must be finite and nonnegative")
    if seen != expected:
        raise ValueError("incomplete or unexpected arm/task/repeat grid")


def summarize(dataset, protocol, tasks):
    rounds = dataset["rounds"]
    if not rounds or len(set(rounds)) != len(rounds) or any(type(r) is not int or r < 1 for r in rounds):
        raise ValueError("rounds must be distinct positive integers")
    design = protocol["design"]["deepseek/deepseek-v4-flash"]
    declared_rounds = sorted({r for schedule in design["asks"].values()
                              for scope, repeats in schedule.items() if scope != "held_out" for r in repeats})
    if rounds != declared_rounds:
        raise ValueError("rounds differ from the frozen protocol")
    comparisons = {
        "accuracy": {"arms": ["block_model", "shipped"], "tasks": protocol["sets"]["reading_independent"]},
        "resources": {"arms": ["block_model", "exhaustive"], "tasks": protocol["sets"]["gated"]},
    }
    expected = {(arm, task, repeat) for c in comparisons.values() for arm in c["arms"]
                for task in c["tasks"] for repeat in rounds}
    validate_runs(dataset["runs"], expected)
    templates = {task["id"]: task["template"] for task in tasks["tasks"] if task.get("template") and task["expect"]["kind"] != "none"}
    parser_runs = dataset["parser_runs"]
    h4 = protocol["tests"].get("H4")
    parser_expected = {(arm, task, 1) for arm in ("block_model", "block_rules") for task in templates} if h4 else set()
    validate_runs(parser_runs, parser_expected)
    result = {"market": dataset["market"], "rounds": rounds, "status": dataset["status"]}
    for name, comparison in comparisons.items():
        result[name] = {}
        for arm in comparison["arms"]:
            selected = [r for r in dataset["runs"] if r["arm"] == arm and r["task"] in comparison["tasks"]]
            resource = [r for r in selected if r["outcome"] != CLOSED]
            grades = [correct(r) for r in selected]
            result[name][arm] = {
                "trials": len(selected), "scored": sum(g is not None for g in grades),
                "correct": sum(g is True for g in grades), "unscorable": grades.count(None),
                "resource_trials": len(resource), "closed": len(selected) - len(resource),
                "median_opened": median(r["opened"] for r in resource),
                "median_cost_usd": median(r["cost_usd"] for r in resource),
            }
    if set(protocol["tests"]) != set(design["tests"]):
        raise ValueError("primary test family differs from the frozen design")
    tests = {}
    for name, specification in protocol["tests"].items():
        if name not in {"H1", "H2", "H3", "H4"}:
            raise ValueError("unsupported primary test")
        use_templates = specification["strata"] == "template"
        if use_templates != (name == "H4"):
            raise ValueError("unexpected test strata")
        rows = parser_runs if use_templates else dataset["runs"]
        questions = sorted(set(templates.values())) if use_templates else protocol["sets"][specification["on"]]
        groups = []
        for question in questions:
            pair = []
            for side in ("a", "b"):
                arm = ARMS[specification[side]]
                selected = [r for r in rows if r["arm"] == arm and
                            (templates[r["task"]] if use_templates else r["task"]) == question]
                if specification["measure"] == "correct":
                    values = [correct(r) for r in selected if correct(r) is not None]
                else:
                    field = {"opened": "opened", "cost": "cost_usd"}[specification["measure"]]
                    values = [r[field] for r in selected if r["outcome"] != CLOSED]
                if not values:
                    raise ValueError("a test stratum has no assessable runs")
                pair.append(values)
            groups.append(pair)
        if specification["measure"] == "correct":
            strata = [(sum(a), len(a), sum(b), len(b)) for a, b in groups]
            p = exact_correctness(strata)
            counts = {side: [sum(sum(g[i]) for g in groups), sum(len(g[i]) for g in groups)]
                      for i, side in enumerate(("a", "b"))}
        else:
            p, counts = exact_ranks(groups), None
        tests[name] = {"measure": specification["measure"], "a": specification["a"], "b": specification["b"],
                       "strata": specification["strata"], "p": p}
        if counts is not None:
            tests[name]["counts"] = counts
    adjusted = holm({name: test["p"] for name, test in tests.items()})
    for name, test in tests.items():
        test["p_holm"] = adjusted[name]
    result["primary_tests"] = tests
    result["holm_family_size"] = len(tests)
    return result


def checked_source(root, dataset, kind):
    path = Path(dataset[f"{kind}_path"])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("source paths must be repository-relative")
    data = (root / path).read_bytes()
    if hashlib.sha256(data).hexdigest() != dataset[f"{kind}_sha256"]:
        raise ValueError(f"{dataset['market']}: {kind} hash differs from the recorded source")
    return json.loads(data)


def reproduce(artifact, root=ROOT):
    if artifact.get("schema_version") != 2:
        raise ValueError("unsupported artifact schema")
    datasets = artifact["datasets"]
    if len({d["market"] for d in datasets}) != len(datasets):
        raise ValueError("markets must remain separate and unique")
    results = []
    for dataset in datasets:
        protocol = checked_source(root, dataset, "protocol")
        tasks = checked_source(root, dataset, "tasks")
        checked_source(root, dataset, "fixture")
        results.append(summarize(dataset, protocol, tasks))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT)
    parser.add_argument("--json", action="store_true", help="emit computed summaries and primary tests as JSON")
    args = parser.parse_args()
    try:
        result = reproduce(json.loads(args.artifact.read_text()))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Cannot reproduce the results: {exc}\n")
    if args.json:
        print(json.dumps(result, indent=2, allow_nan=False))
        return
    print("Human correctness: seven shared templates. Resources: eight gated templates.")
    print("Markets stay separate. Provider USD per trial includes model parsing where used.\n")
    print("| Market | Correct: block | Correct: shipped | Resource trials/arm | Median opened: block / exhaustive | Median USD: block / exhaustive |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in result:
        a, b = row["accuracy"]["block_model"], row["accuracy"]["shipped"]
        c, d = row["resources"]["block_model"], row["resources"]["exhaustive"]
        print(f"| {row['market']} ({len(row['rounds'])} rounds) | {a['correct']}/{a['scored']} | {b['correct']}/{b['scored']} | {c['resource_trials']} / {d['resource_trials']} | {c['median_opened']:g} / {d['median_opened']:g} | {c['median_cost_usd']:.7f} / {d['median_cost_usd']:.7f} |")
        if b["unscorable"]:
            print(f"\n{row['market']}: {b['unscorable']} shipped answer marked unscorable by the human reader is excluded from correctness, as prespecified.\n")
    print("\n| Market | Primary test | Raw two-sided p | Holm-adjusted p |")
    print("| --- | --- | ---: | ---: |")
    for row in result:
        for name, test in row["primary_tests"].items():
            print(f"| {row['market']} | {name}: {test['measure']} | {test['p']:.9g} | {test['p_holm']:.9g} |")
    print("\nH1: model block vs shipped correctness; H2/H3: model block vs exhaustive openings/cost;")
    print("H4 (Wexcombe only): model vs rules on held-out wording, stratified by template.")
    print("Holm adjusts four Wexcombe tests and three Quenby tests separately.")
    print("Reanalysis of released measurements, not an independent audit of raw traces or human grades.")


if __name__ == "__main__":
    main()
