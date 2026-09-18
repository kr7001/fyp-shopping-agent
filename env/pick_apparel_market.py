#!/usr/bin/env python3
"""Seed clothing markets until one lands the right way round on the results page.

A market is only a trap if the trap is where the glance lands. The answer has to sit outside
the first row of search results, and the wrong answer has to sit inside it, or the questions
measure something other than retrieval. The clothing market got this wrong twice: the first
draw put the answer at card 4 and the agent scored 3 of 3 by glancing, and the second put the
trap at card 11 so a glance found neither and the control question stopped being a control.

Both times the fix was a rule on the listing's index in the catalogue, and both times that
failed, because **catalogue index barely predicts page position**. Magento orders search
results by its own relevance, and the third draw put index 1 at card 12 and index 11 at card
4. There is no arrangement of the fixture that reliably decides where a listing renders.

So this stops predicting and starts measuring. It generates a market, seeds it, rebuilds the
search index, reads the rendered results page, and keeps the market only if the real page has
the trap in the first four cards and the answer outside them. Otherwise it tries the next
seed. Nothing here costs money, only time: a cycle is about three minutes, and roughly one
draw in five lands correctly.

    python env/pick_apparel_market.py --seeds 11 12 13 14 15 16
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


def usable(trap: int | None, answer: int | None) -> bool:
    return bool(trap and trap <= FIRST_ROW and answer and answer > FIRST_ROW)


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
    instance = fixture["_instance"]
    ok = usable(trap, answer)
    note = (f"seed {seed}: trap {instance['cheapest_card']['seller']} at card {trap}, "
            f"answer {instance['winner']['seller']} at card {answer}, "
            f"floor {instance['oracle_min_opens']}")
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
        print(f"cards 1 to 4: {order[:4]}")
        print(f"trap   at card {trap}")
        print(f"answer at card {answer}")
        print("usable" if usable(trap, answer) else "not usable")
        return 0 if usable(trap, answer) else 1

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
