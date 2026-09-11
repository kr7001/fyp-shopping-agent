#!/usr/bin/env python3
"""Compare every arm on the same four gated questions.

The point of this file is comparability. Arms were run on different days with different
task subsets and different repeat counts, and quoting them side by side without matching
the questions would be the denominator problem again. So this restricts every arm to the
gated scaled tasks, states the run count for each, and reports cost per run rather than
suite totals.

Reading the result: exhaustive retrieval is the upper bound, correct and expensive. The
unmodified agent is the lower bound, cheap and sometimes wrong. Any policy worth having
lives between them, and the gap between those two points is the space this project has to
work in.

    python experiments/arms.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import policy as policy_module
import score as scoring

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"

# The gated questions of the scaled fixture. The control is excluded because its answer is
# on the results page, so an exhaustive arm has nothing to be exhaustive about and would
# only add cost that no arm can act on.
GATED = ("scaled-cheapest-target", "scaled-target-price",
         "scaled-all-stocked", "scaled-best-per-litre")


def market_suffix(payload: dict) -> str:
    """Which market a suite ran against, when it is not the development one."""
    tasks_file = payload.get("tasks_file", "tasks.json")
    brand = payload.get("brand")
    if brand and brand != "Rivenhall":
        return f" [{brand}]"
    if "heldout" in tasks_file:
        return " [held-out]"
    return ""


def arm_name(payload: dict) -> str:
    if payload.get("targeting"):
        policy = payload.get("policy", "off")
        # A suite predating the version field ran the strategies that pruned within the
        # first screen without enumerating, which is a different policy, not a repeat.
        version = payload.get("targeting_version", 1)
        base = "targeting" if policy == "off" else f"targeting+{policy}"
        # Runs on different markets are different measurements, not more repeats of one.
        # This is the fifth time a figure has come out wrong from pooling things that only
        # looked alike, so the market is now part of the arm's identity rather than an
        # assumption that every suite used the development fixture.
        return f"{base} v{version}{market_suffix(payload)}"
    if payload.get("exhaustive"):
        return "exhaustive"
    if payload.get("confidence", "off") != "off":
        return f"confidence:{payload['confidence']}"
    policy = payload.get("policy", "off")
    return "unmodified" if policy == "off" else policy


def collect() -> dict[str, list[dict]]:
    arms: dict[str, list[dict]] = collections.defaultdict(list)
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        rows = [r for r in payload["rows"] if r["task"] in GATED]
        if not rows:
            continue
        arms[arm_name(payload)].extend(rows)
    return arms


def replayed_gate(arms: dict[str, list[dict]]) -> list[dict]:
    """The gate arm, derived from the unmodified runs rather than run separately.

    The gate issues no browser action, so applying it to a finished run gives exactly the
    verdict it would have given live, at exactly the cost that run already incurred. It
    belongs in this table at the unmodified arm's cost, which is the point: it is the only
    arm that changes the outcome without changing the spend.
    """
    spec = json.loads((HERE / "tasks_scaled.json").read_text())
    tasks = {t["id"]: t for t in spec["tasks"]}
    out = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        if payload.get("policy", "off") != "off" or payload.get("exhaustive"):
            continue
        if payload.get("targeting"):
            continue
        if payload.get("confidence", "off") != "off":
            continue
        for row in payload["rows"]:
            if row["task"] not in GATED:
                continue
            log = suite_path.parent / (row.get("log") or "")
            record = suite_path.parent / f"{row['task']}-{row['repeat']}.json"
            if not log.exists() or not record.exists():
                continue
            result = json.loads(record.read_text()).get("result") or {}
            answer = str(result.get("final") or "")
            task = tasks[row["task"]]
            # A run scored against a catalogue since regenerated cannot be compared.
            if scoring.score(task, answer, True)["verdict"] != row["verdict"]:
                continue
            check = policy_module.gate(task, spec, answer, log)
            verdict = (row["verdict"] if check["ok"]
                       else scoring.score(task, policy_module.abstention_for(check),
                                          True)["verdict"])
            out.append({**row, "verdict": verdict})
    return out


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def main() -> int:
    arms = collect()
    arms["gate"] = replayed_gate(arms)
    order = ["unmodified", "confidence:plain", "gate", "retry", "exhaustive",
             "targeting v1", "targeting+gate v1", "targeting+gate v2",
             "targeting+gate v3", "targeting+gate v3 [Calderwood]"]
    order += [k for k in arms if k not in order]

    print("EVERY ARM, ON THE SAME FOUR GATED QUESTIONS\n")
    print(f"{'arm':18} {'runs':>5} {'correct':>8} {'refused':>8} {'wrong':>6} "
          f"{'rate':>6} {'actions':>8} {'cost/run':>9}")
    print("-" * 78)

    for name in order:
        rows = arms.get(name)
        if not rows:
            continue
        verdicts = collections.Counter(r["verdict"] for r in rows)
        answered = len(rows) - verdicts["abstained"]
        rate = verdicts["correct"] / answered if answered else 0
        print(f"{name:18} {len(rows):>5} {verdicts['correct']:>8} "
              f"{verdicts['abstained']:>8} {verdicts['wrong']:>6} "
              f"{rate:>5.0%} {str(round(mean(r.get('actions') for r in rows) or 0, 1)):>8} "
              f"${mean(r.get('cost_usd') for r in rows) or 0:>8.3f}"
              + ("   replayed, no extra spend" if name == "gate" else ""))

    print("\nrate is correct as a share of questions the arm actually answered, so an arm")
    print("that refuses is not rewarded for the refusals nor punished for them here.")

    # The gate is a replay of baseline runs, so its cost and actions are those runs' own
    # figures. It reads lower than the unmodified row only because the replay drops runs
    # whose recorded verdict no longer reproduces, and one of those three was expensive.
    # Presenting that difference as a saving would be wrong: the gate issues no browser
    # action, so it cannot change cost at all. Paired against exactly the runs it replayed,
    # the cost is identical by construction and the verdicts are the only thing that moves.
    gate = arms.get("gate") or []
    if gate:
        keys = {(r["task"], r["repeat"], round(r["cost_usd"], 6)) for r in gate}
        paired = [r for r in arms.get("unmodified", [])
                  if (r["task"], r["repeat"], round(r["cost_usd"], 6)) in keys]
        if paired:
            pw = sum(1 for r in paired if r["verdict"] == "wrong")
            gw = sum(1 for r in gate if r["verdict"] == "wrong")
            print(f"\ngate, paired against the same {len(paired)} runs it replays")
            print(f"  cost     ${mean(r['cost_usd'] for r in paired):.3f} either way, "
                  f"identical by construction")
            print(f"  actions  {mean(r['actions'] for r in paired):.1f} either way")
            print(f"  wrong    {pw} without it, {gw} with it")

    low = arms.get("unmodified")
    high = arms.get("exhaustive")
    if low and high:
        lc = mean(r.get("cost_usd") for r in low)
        hc = mean(r.get("cost_usd") for r in high)
        la = mean(r.get("actions") for r in low)
        ha = mean(r.get("actions") for r in high)
        lr = sum(1 for r in low if r["verdict"] == "correct") / len(low)
        hr = sum(1 for r in high if r["verdict"] == "correct") / len(high)
        print(f"\nthe axis a policy has to live on")
        print(f"  unmodified   {lr:>5.0%} correct   {la:>5.1f} actions   ${lc:.3f} per run")
        print(f"  exhaustive   {hr:>5.0%} correct   {ha:>5.1f} actions   ${hc:.3f} per run")
        print(f"  exhaustive costs {hc / lc:.1f}x the unmodified agent and gets "
              f"{hr - lr:+.0%} accuracy")
        aim_name = next((k for k in ("targeting+gate v2", "targeting+gate v1",
                                     "targeting v1") if arms.get(k)), None)
        aim = arms.get(aim_name) if aim_name else None
        if not aim:
            print("\nA targeting policy has to beat exhaustive on cost while matching it")
            print("on accuracy. That is the claim RQ3 makes and the one still unmeasured.")
        else:
            ac = mean(r.get("cost_usd") for r in aim)
            aa = mean(r.get("actions") for r in aim)
            ar = sum(1 for r in aim if r["verdict"] == "correct") / len(aim)
            answered = len(aim) - sum(1 for r in aim if r["verdict"] == "abstained")
            ar = (sum(1 for r in aim if r["verdict"] == "correct") / answered
                  if answered else 0)
            print(f"  {aim_name:12} {ar:>5.0%} correct   {aa:>5.1f} actions   "
                  f"${ac:.3f} per run"
                  + (f"   of {answered} answered, {len(aim) - answered} refused"
                     if answered != len(aim) else ""))
            print(f"\n{aim_name} against the exhaustive upper bound it has to beat")
            print(f"  accuracy {ar:.0%} against {hr:.0%}")
            print(f"  cost     ${ac:.3f} against ${hc:.3f}, "
                  f"{100 * (1 - ac / hc):+.0f}% ")
            print(f"  actions  {aa:.1f} against {ha:.1f}, {100 * (1 - aa / ha):+.0f}%")
            if ar >= hr and ac < hc:
                print("\nMatches the upper bound on accuracy for less. That is the RQ3 "
                      "claim, met.")
            elif ar < hr:
                print("\nCheaper but less accurate. The saving was bought with correctness, "
                      "which is not the claim.")
            else:
                print("\nAs accurate but not cheaper. The strategy did not reduce work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
