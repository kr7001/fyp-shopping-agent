#!/usr/bin/env python3
"""Runs that read the prices the gated theme keeps out of the agent's observation.

The gated theme writes every size's price into the page source so its own script can show
the chosen size's price, and the observation the agent takes shows none of them until a
size is chosen; a sold-out size cannot be chosen from the menu (Playwright's selectOption
waits on a disabled option and times out, checked on igr-app-07 on 20 October 2026). An
agent that runs JavaScript of its own can still reach them, which the theme's template
says plainly, and found two ways in the stored runs: it set the menu's value to a sold-out
size by script and fired a change, and the theme's own reveal script, which does not ask
whether the size can be bought, printed that size's price ("As low as $15.04" for
igr-app-07's M, 20261007T115021/apparel-target-price-1); or it returned the page's HTML,
blob and all (20261014T220116/apparel-softest-1). This counts the runs that did either.

How they are kept, from env/gated_theme/Magento_ConfigurableProduct/templates/product/view/
type/options/configurable.phtml and from one listing's source fetched under the gated user
agent on 20 October 2026, a GET of igr-app-07: a hidden `<div id="igr-variant-store"
data-igr="...">`, the attribute holding `base64_encode(json_encode($optionPrices))`, keyed
by child product id, with "=" written as "&#x3D;". igr-app-07's decodes to S 16.22, M 15.04,
L 18.33 and XL 18.58, as the fixture has them; S and M are sold out, and outside the blob
the page prints 18.33 alone, its card's price.

A run counts as a leak when its log holds any of three things:

  the store        the words `data-igr` or `igr-variant-store`, anywhere in the log
  the blob         base64 of the blob's own keys, `"finalPrice":{"amount":` or
                   `"baseOldPrice":{"amount":`, in any of the three byte alignments, so any
                   listing's blob is found whatever its child ids, and a cut-off copy too
  a hidden price   in a tool reply, the price of a size that is sold out, on a market whose
                   fixture is the batch's own and whose run was on the gated shop. Only the
                   prices no listing shows as a card or as a size that can be bought count,
                   so a figure a page legitimately printed is never taken for one

    python3 experiments/analysis/leaks.py experiments/results/<batch> [...]
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import suite as suite_module  # noqa: E402  (draw_id, the one rule for which market a file is)
import sufficiency  # noqa: E402
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402  (fixture_for, the one rule for a task file's fixture)

STORE = ("data-igr", "igr-variant-store")
# Keys every listing's blob holds, as PHP's json_encode writes them, without spaces.
BLOB_KEYS = (b'"finalPrice":{"amount":', b'"baseOldPrice":{"amount":')


def signatures(needle: bytes) -> list[str]:
    """Base64 text that every encoding of a byte string holding `needle` contains, one for
    each of the three positions the needle can start at within a 3-byte group: the groups
    that are wholly the needle's, without the first when it shares bytes with what comes
    before, and without the last when it shares bytes with what follows."""
    found = []
    for lead in range(3):
        padded = b"\0" * lead + needle
        whole = len(padded) // 3 * 3
        encoded = base64.b64encode(padded[:whole]).decode()
        found.append(encoded[4:] if lead else encoded)
    return found


SIGNATURES = tuple(dict.fromkeys(sig for key in BLOB_KEYS for sig in signatures(key)))


@dataclasses.dataclass(frozen=True)
class Market:
    """A market's sizes that are sold out, by price in cents, for the ones whose price no
    listing shows as its card or as a size that can be bought."""
    name: str
    hidden: dict[int, list[str]]           # cents -> ["igr-app-07 M", ...]
    shown_too: list[str]                   # sold-out sizes left out, a shown price their own


def market_of(fixture_path: pathlib.Path) -> Market:
    fixture = json.loads(fixture_path.read_text())
    shown, sold_out = set(), []
    for family in fixture["families"]:
        buyable = [v for v in family["variants"] if v["qty"] > 0]
        shown.update(sufficiency.cents(v["price"]) for v in buyable)
        sold_out += [(family["parent_sku"].lower(), v["option"], sufficiency.cents(v["price"]))
                     for v in family["variants"] if v["qty"] <= 0]
    hidden: dict[int, list[str]] = {}
    for sku, size, cents in sold_out:
        if cents not in shown:
            hidden.setdefault(cents, []).append(f"{sku} {size}")
    return Market(fixture_path.name, hidden,
                  [f"{sku} {size}" for sku, size, cents in sold_out if cents in shown])


def batch_market(payload: dict) -> tuple[Market | None, str]:
    """The batch's own market, or None and why not: its task file must name a generated
    fixture of its own brand (`verify_cells.fixture_for`), and the file's draw must be the
    batch's, or the fixture would describe another market than the one the runs saw."""
    name = payload.get("tasks_file")
    if not name or not (paths.TASKS / name).exists():
        return None, "the batch names no task file here"
    spec = json.loads((paths.TASKS / name).read_text())
    if not spec.get("brand"):
        return None, f"{name} names no brand, so no generated clothing fixture is its market"
    fixture_path = verify_cells.fixture_for(spec)
    fixture = json.loads(fixture_path.read_text())
    if (fixture.get("_generated") or {}).get("brand") != spec["brand"]:
        return None, f"{fixture_path.name} is not {spec['brand']}'s fixture"
    if suite_module.draw_id(spec) != payload.get("draw"):
        return None, f"the batch's draw {payload.get('draw')} is not {name}'s {suite_module.draw_id(spec)}"
    return market_of(fixture_path), ""


def tool_text(log_path: pathlib.Path, log: str) -> str:
    """What the browser's tools replied, and nothing the agent wrote: openJiuwen's replies
    from its trace, each in full, or for the second agent the log without its tool-call
    lines, which carry the agent's own arguments and its answer."""
    replies = trace_stats.tool_replies(log_path)
    if replies:
        return "\n".join(text for _, text, _ in replies.values())
    return trace_stats.NAIVE_STEP.sub("", log)


def leaks_in(log: str, replies: str, market: Market | None) -> list[str]:
    """Every sign in one run that it read what the theme hides, each with its context."""
    found = []
    for word in STORE:
        at = log.find(word)
        if at >= 0:
            found.append(f"the store, {word!r}: ...{log[max(0, at - 60):at + 60]!r}...")
    for sig in SIGNATURES:
        at = log.find(sig)
        if at >= 0:
            found.append(f"the blob, base64 {sig!r}: ...{log[max(0, at - 40):at + 60]!r}...")
    if market is not None:
        for match in sufficiency.ANY_DECIMAL.finditer(replies):
            cents = sufficiency.cents(match.group(1))
            if cents in market.hidden:
                found.append(f"a hidden price, ${cents / 100:.2f} ({', '.join(market.hidden[cents])}): "
                             f"...{replies[max(0, match.start() - 60):match.end() + 40]!r}...")
    return found


@dataclasses.dataclass(frozen=True)
class RunLeaks:
    run: str
    shop: str | None
    priced: bool                     # whether the hidden prices were looked for
    found: list[str]


def batch_leaks(folder: pathlib.Path) -> tuple[list[RunLeaks], str]:
    """Every run of a batch with a log here, and why the hidden prices were not looked for
    in it when they were not."""
    suite_path = folder / "suite.json"
    payload = json.loads(suite_path.read_text()) if suite_path.exists() else {}
    market, why = batch_market(payload) if payload else (None, "no suite.json")
    runs = []
    for log_path in sorted(folder.glob("*.log")):
        record_path = log_path.with_suffix(".json")
        record = json.loads(record_path.read_text()) if record_path.exists() else {}
        shop = record.get("shop")
        log = log_path.read_text(errors="replace")
        priced = market is not None and shop == "gated"
        runs.append(RunLeaks(log_path.stem, shop, priced,
                             leaks_in(log, tool_text(log_path, log), market if priced else None)))
    return runs, why


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", type=pathlib.Path)
    args = parser.parse_args()
    total = leaked = priced = 0
    for folder in args.batches:
        if not folder.is_dir():
            continue
        runs, why = batch_leaks(folder)
        if not runs:
            continue
        bad = [run for run in runs if run.found]
        checked = sum(run.priced for run in runs)
        total, leaked, priced = total + len(runs), leaked + len(bad), priced + checked
        note = "" if checked == len(runs) else (
            f"; hidden prices looked for in {checked}" + (f" ({why})" if why else
                                                         ", the rest not on the gated shop"))
        print(f"{folder.name}: {len(runs)} runs, {len(bad)} with a leak{note}")
        for run in bad:
            for finding in run.found:
                print(f"  {run.run}: {finding}")
    print(f"\n{total} runs with a log, {leaked} with a leak; the hidden prices were looked for "
          f"in {priced}, those on the gated shop whose market's fixture is the batch's own")
    return 1 if leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
