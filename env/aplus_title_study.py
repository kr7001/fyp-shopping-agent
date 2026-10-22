#!/usr/bin/env python3
"""Do the A+ market's rules select answer listings by how they are titled?

The verifier noticed that on Larchmere's first market all three cheapest buyable size M tees
were titled "Heavyweight Cotton Crew Neck Tee", the longest tee phrasing (22 October 2026).
The suspicion is a selection effect: the shop ranks a listing lower the longer its names
(`search_order.py`), and the page rules ask that answers render off the first screen and that
one renders on page 2, so a market that passes may be one whose answers have long titles. An
agent that learned "the longest title is the answer" would then be right for a reason that
has nothing to do with retrieval.

This draws development seeds, never seeds them, and compares the listings each price
question's key names with all the listings of their product: by title phrasing, by the words
of the seller's name, and by how many options a listing has. It writes what it drew, seed by
seed, to a record (`--out`), so the seeds looked at are on file.

    python3 env/aplus_title_study.py --seeds 901-920 --out env/manifests/aplus_dev-title-study.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_aplus as aplus  # noqa: E402

BRAND, PREFIX, TWO_FORMS = "Larchmere", aplus.DEV_PREFIX, True


def features(listing: dict) -> dict:
    title = listing["name"].rsplit(" - ", 1)[0].removeprefix(BRAND + " ")
    return {"phrasing": title, "seller_words": len(listing["seller"].split()),
            "options": len(listing["variants"])}


def one_seed(seed: int) -> dict:
    families, facts, attempts = aplus.generate(seed, BRAND, PREFIX, TWO_FORMS)
    named = aplus.answer_listings(aplus.keys(families))
    order = facts["predicted_order"]
    answers = {}
    for question, (listings, _) in named.items():
        answers[question] = [{"sku": l["parent_sku"], "card": order.index(l["parent_sku"]) + 1,
                              **features(l)} for l in listings]
    return {"seed": seed, "attempts": attempts,
            "generator_version": aplus.VERSION, "search_order_version": aplus.search_order.VERSION,
            "answers": answers,
            "all": {product: [features(f) for f in families if f["product"] == product]
                    for product in (aplus.TEE, aplus.WATER)}}


def shares(rows: list[dict], key: str) -> dict:
    counts = collections.Counter(row[key] for row in rows)
    return {str(value): round(counts[value] / len(rows), 3) for value in sorted(counts)}


def summary(results: list[dict]) -> dict:
    """Answer listings, each counted once per market, against every listing of the product."""
    out = {}
    for product, questions in ((aplus.TEE, ("tee-target-price", "tee-top-3")),
                               (aplus.WATER, ("water-target-price", "water-best-per-litre"))):
        answer_rows, all_rows = [], []
        for result in results:
            seen = {}
            for question in questions:
                for row in result["answers"].get(question, []):
                    seen[row["sku"]] = row
            answer_rows += list(seen.values())
            all_rows += result["all"][product]
        out[product] = {key: {"answers": shares(answer_rows, key), "all": shares(all_rows, key)}
                        for key in ("phrasing", "seller_words", "options")}
        out[product]["answer_listings"] = len(answer_rows)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", required=True, help="a range of development seeds, as 901-920")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    first, last = (int(n) for n in args.seeds.split("-"))
    seeds = list(range(first, last + 1))
    for seed in seeds:
        why = aplus.refused(seed, False, None)
        if why:
            raise SystemExit(f"refusing: {why}")
    results = []
    for seed in seeds:
        results.append(one_seed(seed))
        print(f"seed {seed}: drawn", flush=True)
    record = {"_about": ["Written by env/aplus_title_study.py. Development seeds drawn, never seeded,",
                         "to see whether the rules select answer listings by their titles."],
              "brand": BRAND, "brand_forms": 2 if TWO_FORMS else 1, "seeds": seeds,
              "summary": summary(results), "markets": results}
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
