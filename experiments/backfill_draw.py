#!/usr/bin/env python3
"""Record which catalogue draw each finished suite ran against.

`suite.py` writes a `draw` for every suite from 13 Sep 2026 on. Suites written before then
carry none, and `arms.py` pooled them by condition alone, which put four runs from a
catalogue that no longer exists into the unmodified baseline. This assigns each older suite
its draw once, and writes down how it was decided, so the assignment can be checked rather
than trusted.

Three ways a draw is decided, in order of strength:

1. The suite recorded its ground truth (`instance`), so the draw is computed from that.
2. It did not, and it started after the draw now in the shop was seeded, so it ran on that.
3. It did not, and it started before, so it ran on a draw since replaced.

Seeding times come from `catalog_product_entity.created_at` (UTC), converted to local time
to match the suite directory stamps, which are local.

    python experiments/backfill_draw.py          # show what would be written
    python experiments/backfill_draw.py --write
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import suite

HERE = pathlib.Path(__file__).resolve().parent

# The current Rivenhall draw was seeded at 2026-09-08 18:01:59 UTC. The pilot suite at
# 01:50 local named Yarrow Merchants at $16.84 as the winner; neither exists in the current
# catalogue, which confirms it ran on the draw this one replaced.
RIVENHALL_SEEDED = "20260909T020159"

# Authoring notes were blanked from the small fixture's descriptions at 2026-09-13
# 15:30:28 UTC. Every small-fixture suite before this read a page carrying them.
SMALL_NOTES_REMOVED = "20260913T233028"


def spec(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def assign(stamp: str, payload: dict) -> tuple[str, str]:
    scaled = any(r["task"].startswith("scaled-") for r in payload["rows"])

    if payload.get("instance"):
        brand = payload.get("brand")
        return (suite.draw_id({"brand": brand, "_instance": payload["instance"]}),
                "computed from the instance recorded in this suite")

    if scaled:
        if stamp >= RIVENHALL_SEEDED:
            return (suite.draw_id(spec("tasks_scaled.json")),
                    f"no instance recorded; started after the current Rivenhall draw was "
                    f"seeded at {RIVENHALL_SEEDED} local")
        return ("Rivenhall:superseded",
                f"no instance recorded; started before the current Rivenhall draw was "
                f"seeded at {RIVENHALL_SEEDED} local. Answers name Yarrow Merchants at "
                f"$16.84, absent from the current catalogue")

    small = spec("tasks.json")
    if stamp >= SMALL_NOTES_REMOVED:
        return suite.draw_id(small), "small fixture, after the authoring notes were removed"
    before = {k: v for k, v in small.items() if k != "_environment"}
    return (suite.draw_id(before),
            "small fixture, before 13 Sep 2026: authoring notes, two of them stating the "
            "answer, were in the product descriptions the agent read")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    for path in sorted(suite.RESULTS.glob("*/suite.json")):
        payload = json.loads(path.read_text())
        if payload.get("draw"):
            print(f"{path.parent.name}  {payload['draw']:22} already recorded")
            continue
        draw, basis = assign(path.parent.name, payload)
        print(f"{path.parent.name}  {draw:22} {basis}")
        if args.write:
            payload["draw"], payload["draw_basis"] = draw, basis
            path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    if not args.write:
        print("\nnothing written; re-run with --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
