#!/usr/bin/env python3
"""Seed clothing markets until one lands the right way round on the results page.

A market is only a trap if the glance is wrong. The answer has to sit outside the first row
of search results, and something inside that row has to look cheaper than the answer, or the
questions measure something other than retrieval. The clothing market got this wrong twice:
the first draw put the answer at card 4 and the agent scored 3 of 3 by glancing, and the
second put the cheapest listing at card 11 so a glance found nothing misleading at all and
the control question stopped being a control.

Both times the fix was a rule on the listing's index in the catalogue, and both times it
failed. **Catalogue index does not decide where a listing renders. Variant count does.**
Measured on 18 September 2026 across eight generated markets: Magento's fulltext relevance
indexes every child product, so a listing offering four sizes carries the brand name four
times and outranks one offering two. In the market measured, every listing in cards 1 to 8
had four sizes, cards 9 to 11 had three, and cards 13 to 15 had two.

That made the old condition unsatisfiable rather than merely unlucky. The cheapest advertised
listing is the one missing the target size, so it has fewer variants by construction, so it
renders late by construction. Eight consecutive seeds were rejected with it at cards 8, 12,
8, 14, 10, 15, 12 and 13, never once in the first four.

So the condition is now the one that actually matters, and it is weaker in the right way: the
answer must render outside the first row, and at least one listing inside the first row must
advertise a price below what the answer costs. A shopper glancing at the first screen then
sees something that looks like a better deal and is not. Which particular listing plays that
role does not matter.

Nothing here costs money, only time: a cycle is about five minutes, most of it reindexing.

    python env/pick_apparel_market.py --seeds 201 202 203
    python env/pick_apparel_market.py --check-only     # just measure what is seeded now
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
FIXTURE = HERE / "fixtures" / "scaled_apparel.json"
TASKS = REPO / "experiments" / "tasks_apparel.json"
CONTAINER = "webarena-shopping"
MAGE = "/var/www/magento2/bin/magento"
FIRST_ROW = 4


def run(command: list[str], quiet: bool = True) -> int:
    return subprocess.run(command, cwd=REPO,
                          capture_output=quiet, text=True).returncode


def rendered_order(brand: str) -> list[str]:
    """The sellers as the results page actually lists them, in order."""
    url = f"http://localhost:7770/catalogsearch/result/?q={brand}"
    html = urllib.request.urlopen(url).read().decode()
    seen: list[str] = []
    for match in re.finditer(rf"{brand} Heavyweight Cotton Tee - ([A-Za-z ]+?)\s*<", html):
        seller = match.group(1).strip()
        if seller not in seen:
            seen.append(seller)
    return seen


def positions(fixture: dict) -> tuple[int | None, int | None, list[str]]:
    instance = fixture["_instance"]
    order = rendered_order(fixture["_generated"]["brand"])
    def place(name: str) -> int | None:
        return order.index(name) + 1 if name in order else None
    return (place(instance["cheapest_card"]["seller"]),
            place(instance["winner"]["seller"]), order)


def first_row_misleads(fixture: dict, order: list[str]) -> list[str]:
    """Listings in the visible row that advertise less than the real answer costs.

    This replaces asking where one particular listing rendered. What has to be true is
    that a glance at the first row is actively misleading, and that holds whenever any
    visible listing advertises a price below what the answer actually costs. Requiring it
    of the single cheapest listing was both stronger than needed and, as it turned out,
    unsatisfiable: the cheapest listing is the one missing the target size, which gives it
    fewer variants, and Magento ranks a listing with fewer variants lower.
    """
    instance = fixture["_instance"]
    answer_price = instance["winner"]["price"]
    advertised = {f["seller"]: min(v["price"] for v in f["variants"])
                  for f in fixture["families"]}
    return [seller for seller in order[:FIRST_ROW]
            if advertised.get(seller, float("inf")) < answer_price]


def usable(answer: int | None, misleading: list[str]) -> bool:
    """The answer is out of reach of a glance, and a glance is actively wrong."""
    return bool(answer and answer > FIRST_ROW and misleading)


def reindex() -> None:
    # Stock as well as search, since 18 Sep 2026. A market now seeds variants with qty 0 on
    # purpose, and without the stock index Magento keeps serving the old availability, so a
    # sold out size still renders as buyable and the draw is measured against a page that
    # does not exist.
    run(["docker", "exec", CONTAINER, "php", MAGE, "indexer:reindex",
         "catalogsearch_fulltext", "cataloginventory_stock"])
    run(["docker", "exec", CONTAINER, "php", MAGE, "cache:flush"])


def attempt(seed: int) -> tuple[bool, str]:
    run([sys.executable, "env/seed_variants.py", "teardown",
         "--fixture", FIXTURE.name, "--yes"])
    if run([sys.executable, "env/generate_apparel.py", "--seed", str(seed),
            "--out", str(FIXTURE), "--tasks", str(TASKS)]):
        return False, f"seed {seed}: no instance satisfied the rules"
    if run([sys.executable, "env/seed_variants.py", "seed", "--fixture", FIXTURE.name]):
        return False, f"seed {seed}: seeding failed"
    reindex()

    fixture = json.loads(FIXTURE.read_text())
    trap, answer, order = positions(fixture)
    misleading = first_row_misleads(fixture, order)
    instance = fixture["_instance"]
    ok = usable(answer, misleading)
    note = (f"seed {seed}: answer {instance['winner']['seller']} at card {answer}, "
            f"{len(misleading)} of the first {FIRST_ROW} cards advertise below "
            f"${instance['winner']['price']}, floor {instance['oracle_min_opens']}")
    if ok and len(order) < 5:
        return False, note + "  (too few listings rendered)"
    return ok, note


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="*",
                        default=[11, 12, 13, 14, 15, 16, 17, 18])
    parser.add_argument("--check-only", action="store_true",
                        help="measure the market already seeded and write nothing")
    args = parser.parse_args()

    if args.check_only:
        fixture = json.loads(FIXTURE.read_text())
        trap, answer, order = positions(fixture)
        misleading = first_row_misleads(fixture, order)
        print(f"cards 1 to {FIRST_ROW}: {order[:FIRST_ROW]}")
        print(f"answer at card {answer}, costing "
              f"${fixture['_instance']['winner']['price']}")
        print(f"misleading in the first row: {misleading}")
        print("usable" if usable(answer, misleading) else "not usable")
        return 0 if usable(answer, misleading) else 1

    for seed in args.seeds:
        ok, note = attempt(seed)
        print(("KEPT  " if ok else "reject") + "  " + note, flush=True)
        if ok:
            print(f"\nseeded and usable. Fixture and tasks written for seed {seed}.")
            return 0
    print("\nno seed landed the right way round. Try more seeds.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
