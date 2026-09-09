#!/usr/bin/env python3
"""Decide whether a run's answer is supported by what the run actually observed.

Two failure modes appeared in the baseline, and they need different tests.

**Delta read as an absolute.** Magento labels variant options with a surcharge, so the
option reads `2 x 9.5L +$15.01` against a $9.89 base. A run that reports $15.01 as the
price has retrieved the right token and misread its semantics. Asking whether the field
was observed does not catch this: it was observed. What catches it is arithmetic. A price
that appears among the observed deltas but never as an observed absolute is a delta being
passed off as a total.

**A number that was never seen at all.** Distinct from the above and genuinely
unsupported, whatever produced it.

Both tests read only what the run already recorded, so neither costs a page fetch. That
is the point: this is meant to run inside the agent before it answers, where the budget
for checking is close to zero.

This module is deliberately evaluated offline first. Running it over the existing runs
says how many failures it would catch and how many correct answers it would wrongly
block, before any of it is wired into the agent and paid for.

    python experiments/sufficiency.py --evaluate
    python experiments/sufficiency.py --log experiments/results/<dir>/<run>.log --answer "..."
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import trace_stats

RESULTS = pathlib.Path(__file__).resolve().parent / "results"

# Money is handled in integer cents throughout. Comparing prices as floats invites a
# value that does not round-trip to slip past an equality test, and the whole check rests
# on equality tests.
MONEY = r"(\d{1,5}\.\d{1,2})"

# A surcharge label, "+$15.01" or "+15.01". The plus is what makes it relative.
DELTA = re.compile(r"\+\s*\$?" + MONEY + r"(?![\d])")
# A money figure not preceded by a plus, so it reads as a total.
ABSOLUTE = re.compile(r"(?<!\+)(?<!\+ )\$" + MONEY + r"(?![\d])")
# Any decimal at all. Prices reach the agent both as rendered text and as JSON, where
# they carry one decimal place, so this deliberately accepts either.
ANY_DECIMAL = re.compile(r"(?<![\d.])" + MONEY + r"(?![\d])")

# A figure carrying a per-unit denominator is derived by the agent, not read off the
# page, so it can be correct while appearing nowhere in the observations.
RATE = re.compile(MONEY + r"\s*(?:/\s*(?:l|kg|litre|liter|kilogram)\b|"
                          r"per\s+(?:litre|liter|kg|kilogram|l)\b)", re.IGNORECASE)

# An answer that announces it has produced a list, and contains no figures.
COMPLETION_CLAIM = re.compile(
    r"\b(successfully\s+(?:listed|extracted|retrieved|gathered)|"
    r"(?:listed|extracted)\s+all\b|here (?:are|is) the)", re.IGNORECASE)

# Below this, a figure in this catalogue is a per-unit rate rather than a total. Rates
# are computed by the agent and correctly absent from the page, so the unsupported test
# does not apply to them. A stated domain assumption: the cheapest total in these
# fixtures is $6.37 and the dearest rate is $1.65 per litre.
RATE_CEILING_CENTS = 500


def cents(value: str | float) -> int:
    """Money as an integer number of cents."""
    return int(round(float(value) * 100))


def observed_text(log_path: pathlib.Path) -> str:
    """Everything the agent actually read back from the browser.

    Only tool results count. The assistant's own messages are what it said, not what it
    saw, and treating its claims as evidence would make the check circular.
    """
    parts = []
    for message in trace_stats.final_messages(log_path):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        parts.append(content if isinstance(content, str) else json.dumps(content))
    return "\n".join(parts)


def evidence(text: str) -> dict[str, set[int]]:
    return {
        "deltas": {cents(m) for m in DELTA.findall(text)},
        "absolutes": {cents(m) for m in ABSOLUTE.findall(text)},
        "any": {cents(m) for m in ANY_DECIMAL.findall(text)},
    }


def prices_in(text: str) -> list[int]:
    return [cents(m) for m in ANY_DECIMAL.findall(text or "")]


def rate_values(text: str) -> set[int]:
    return {cents(m) for m in RATE.findall(text or "")}


def verified_compositions(amounts: list[int], seen: dict[str, set[int]]) -> set[int]:
    """Figures exonerated by arithmetic the observations actually support.

    An answer reading "$17.68 (base $6.82 + upgrade $10.86)" states its own working, and
    punishing it would penalise exactly the behaviour this check exists to encourage.

    The sum alone is not enough. An earlier version accepted any three figures where two
    summed to a third, which let a wrong answer clear itself by inventing a plausible
    breakdown: "$15.01 (base $9.89 + upgrade $5.12)" passed while $5.12 was never seen.
    So the base has to have been observed as a total and the delta as a surcharge.
    """
    justified: set[int] = set()
    for base in amounts:
        for delta in amounts:
            if base == delta:
                continue
            total = base + delta
            if total in amounts and base in seen["absolutes"] and delta in seen["deltas"]:
                justified.update({base, delta, total})
    return justified


def check(answer: str, seen: dict[str, set[int]]) -> dict:
    """Verdict for one answer against one run's observations.

    `ok` means nothing was detected, not that the answer is right. This is a filter for
    specific, mechanically checkable faults, not a correctness oracle.

    Every figure presented as an amount is tested, not only the first. Testing the first
    let a wrong value escape by appearing later in the sentence, which made word order
    decide whether the answer was checked at all.
    """
    claimed = prices_in(answer)
    rates = rate_values(answer)
    amounts = [v for v in claimed if v not in rates]

    if COMPLETION_CLAIM.search(answer) and not amounts:
        return {"flag": "claim_without_content", "ok": False,
                "why": "the answer announces a completed list and contains no figures",
                "claimed": claimed}
    if not amounts:
        return {"flag": None, "ok": True, "why": "no price claimed as an amount",
                "claimed": claimed}

    justified = verified_compositions(amounts, seen)

    for value in amounts:
        if value in justified:
            continue
        if value in seen["deltas"] and value not in seen["absolutes"]:
            return {"flag": "delta_as_absolute", "ok": False,
                    "why": f"${value / 100:.2f} was observed only as a surcharge, never as a total",
                    "claimed": claimed}

    for value in amounts:
        if value in justified or value < RATE_CEILING_CENTS:
            continue
        if value not in seen["any"]:
            return {"flag": "unsupported_number", "ok": False,
                    "why": f"${value / 100:.2f} does not appear anywhere the run looked",
                    "claimed": claimed}

    return {"flag": None, "ok": True, "why": "every figure is observed or arithmetically justified",
            "claimed": claimed}


def evaluate() -> int:
    """Replay the check over every recorded run and report what it would have done."""
    rows = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        for row in payload["rows"]:
            log_path = suite_path.parent / (row.get("log") or "")
            if not row.get("log") or not log_path.exists():
                continue
            verdict = check(row.get("answer") or "", evidence(observed_text(log_path)))
            rows.append({**row, "suite": suite_path.parent.name, **{
                "flag": verdict["flag"], "flag_why": verdict["why"]}})

    if not rows:
        print("no runs with traces on disk. Logs are gitignored, so this needs a local run.")
        return 1

    table = collections.Counter((r["verdict"], r["flag"] or "clean") for r in rows)
    scored = [r for r in rows if r["verdict"] in ("correct", "wrong", "ambiguous")]
    wrong = [r for r in scored if r["verdict"] in ("wrong", "ambiguous")]
    right = [r for r in scored if r["verdict"] == "correct"]
    caught = [r for r in wrong if r["flag"]]
    false_flags = [r for r in right if r["flag"]]

    print(f"runs with traces: {len(rows)}\n")
    print(f"{'scored verdict':16} {'flag raised':20} {'runs':>5}")
    print("-" * 44)
    for (verdict, flag), n in sorted(table.items()):
        print(f"{verdict:16} {flag:20} {n:>5}")

    print(f"\ncaught      {len(caught)} of {len(wrong)} wrong or ambiguous runs")
    print(f"false flags {len(false_flags)} of {len(right)} correct runs")

    if caught:
        print("\ncaught:")
        for r in caught:
            print(f"  {r['task']}-{r['repeat']:<2} {r['flag']:20} {r['flag_why']}")
    if false_flags:
        print("\nfalse flags, these would be blocked wrongly:")
        for r in false_flags:
            print(f"  {r['task']}-{r['repeat']:<2} {r['flag']:20} {r['flag_why']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evaluate", action="store_true",
                        help="replay the check over every recorded run")
    parser.add_argument("--log", type=pathlib.Path)
    parser.add_argument("--answer")
    args = parser.parse_args()

    if args.evaluate:
        return evaluate()
    if not args.log or args.answer is None:
        parser.error("give --evaluate, or both --log and --answer")

    seen = evidence(observed_text(args.log))
    print(f"observed deltas    {sorted(seen['deltas'])}")
    print(f"observed absolutes {sorted(seen['absolutes'])}")
    print(json.dumps(check(args.answer, seen), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
