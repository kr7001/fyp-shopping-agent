#!/usr/bin/env python3
"""Check a seeded market in the live shop against its fixture, before any run depends on it.

The claim protocol (docs/content/claim-protocol.md, "The market") lists what has to hold in
the live shop before the first claim run, and LESSONS 14 says to check an environment
property in a real browser rather than infer it. Each check prints one line:

1. The brand's results page lists exactly the fixture's listings, every one at its own URL
   with its own seller, with no next page, as the box reads it (`box/page.py`, gated user
   agent) and as the page rule reads it (urllib's own user agent), in one order.
2. Every card advertises the fixture's lowest buyable price for its listing, the bound the
   block's pruning relies on (`generate_apparel.from_price`).
3. Every size of every listing, in a real browser: under the ordinary theme its label, its
   price (the page's own price table, and the surcharge its label prints) and whether it can
   be chosen; under the gated theme its label, no surcharge, and whether it can be chosen.
   Each must be the fixture's.
4. The gated theme shows only the advertised price until a size is chosen: no other price of
   the listing's sizes anywhere in the page, and the price box at the advertised price. Then
   each size that can be bought is chosen and the price box must show its price. The same
   leak test run on the ordinary theme must find prices, or the test is blind (LESSONS 24).
5. With --page-record, the results page equals the page record a batch stored, every seller,
   advertised price and URL, in order.

Runs under .venv-naive, which has Playwright; nothing here calls a model.

    .venv-naive/bin/python env/check_market.py --fixture claim_apparel.json
    .venv-naive/bin/python env/check_market.py --fixture scaled_apparel.json \
        --page-record experiments/results/20261014T213118
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "experiments"))
import generate_apparel as apparel  # noqa: E402  (from_price, price_for, buyable_price_for)
import paths  # noqa: E402,F401  (puts experiments/box on the path)
import page as page_module  # noqa: E402  (the box's own reading of the results page)

BASE = "http://localhost:7770"
GATED_UA = page_module.GATED_UA
# The reveal waits 60 ms after a size changes (LESSONS 13); the check waits far longer.
REVEAL_WAIT_MS = 600
# A size's label on the ordinary theme: the size, then the surcharge against the price box.
# The size may hold spaces since 22 October 2026, for a pack such as "2 x 9.5L +$32.50": the
# first version took the label up to its first space, so it read that one as a pack with no
# surcharge. A tee's label reads as it did.
LABEL = re.compile(r"^(?P<size>.+?)(?:\s+(?P<sign>[+-])\$(?P<amount>\d+\.\d\d))?$")
SURCHARGE = re.compile(r"[+-]\$\d")
# The page's own configuration blocks. Magento's loader removes them from the document once
# it has applied them, so they are read from the HTML the server sent, never from the DOM
# a browser holds afterwards: the first version of this check read the DOM, found no price
# table and no leak on either theme, and passed a blind check (20 October 2026).
INIT = re.compile(r'<script type="text/x-magento-init">(.*?)</script>', re.S)


# ------------------------------------------------------------------ what the fixture says


def expected(fixture: dict) -> list[dict]:
    """Per listing, in fixture order: its URL, seller, advertised price, and every size in
    menu order with its price and whether it can be bought."""
    out = []
    for family in fixture["families"]:
        out.append({"url": f"{BASE}/{family['parent_sku'].lower()}.html",
                    "name": family["name"], "seller": family["seller"],
                    "advertised": apparel.from_price(family),
                    "sizes": [(v["option"], v["price"], v["qty"] > 0)
                              for v in family["variants"]]})
    return out


def money(value: float) -> str:
    return f"{value:.2f}"


# --------------------------------------------------------------- comparisons, no browser


def results_problems(record: dict, fixture: dict) -> list[str]:
    """What is wrong with a results page record (`page.Page.record()`) against the fixture:
    a count, total or pager that is not the fixture's, a URL missing or extra, a seller
    under the wrong URL, a card price that is not the listing's lowest buyable price."""
    want = {item["url"]: item for item in expected(fixture)}
    got = {item["url"]: item for item in record["listings"]}
    problems = []
    if record["count"] != len(want) or record["total"] != len(want):
        problems.append(f"{record['count']} cards and a total of {record['total']}, not {len(want)}")
    if record["next_page"]:
        problems.append("a next page")
    if set(got) != set(want):
        problems.append(f"URLs missing {sorted(set(want) - set(got))}, "
                        f"extra {sorted(set(got) - set(want))}")
    for url in sorted(set(got) & set(want)):
        if got[url]["seller"] != want[url]["seller"]:
            problems.append(f"{url} is {got[url]['seller']}, not {want[url]['seller']}")
        if abs(got[url]["advertised"] - want[url]["advertised"]) > 0.001:
            problems.append(f"{url} advertises {money(got[url]['advertised'])}, not the lowest "
                            f"buyable {money(want[url]['advertised'])}")
    return problems


def menu_problems(seen: list[dict], listing: dict, theme: str) -> list[str]:
    """What is wrong with one listing's size menu as a browser read it, against the
    fixture: each entry is {"label", "buyable", "price"}, the price None where the theme
    shows none. Sizes and order, salability, and any price shown must all be the fixture's."""
    want = listing["sizes"]
    problems = []
    if [s["label"] for s in seen] != [size for size, _, _ in want]:
        problems.append(f"{theme} menu {[s['label'] for s in seen]}, not "
                        f"{[size for size, _, _ in want]}")
        return problems
    for entry, (size, price, can) in zip(seen, want):
        if entry["buyable"] != can:
            problems.append(f"{theme} {size} {'can' if entry['buyable'] else 'cannot'} be "
                            f"chosen, the fixture says {'buyable' if can else 'sold out'}")
        if entry["price"] is not None and abs(entry["price"] - price) > 0.001:
            problems.append(f"{theme} {size} at {money(entry['price'])}, not {money(price)}")
    return problems


def leaked(text: str, listing: dict) -> list[str]:
    """This listing's size prices, other than its advertised price, found in a page's text
    as figures. Under the gated theme there must be none before a size is chosen.

    A price is looked for as the page prints it, "12.30", and as its price table writes it
    in JSON, "12.3": on Thornwood the ordinary theme's table had 12.3 and 31.6, and the
    first version of this, looking for two decimals only, missed both (20 October 2026).

    A figure with a volume written straight after it is a pack, not a price: a water
    listing selling a pack at $9.50 would otherwise leak through its own "2 x 9.5L" label
    (22 October 2026, LESSONS 24's "8.4 litres" read as $8.40). Only a unit joined to the
    figure is skipped, so "$12.30 L" on a tee page, a price then the size L, still counts."""
    advertised = money(listing["advertised"])
    found = []
    for _, price, _ in listing["sizes"]:
        if money(price) == advertised or money(price) in found:
            continue
        forms = {money(price), repr(round(price, 2))}
        if any(re.search(rf"(?<![\d.]){re.escape(form)}(?!\d|L\b|ml\b)", text) for form in forms):
            found.append(money(price))
    return sorted(found)


def spconfig_in(html: str) -> dict | None:
    """The configurable widget's configuration, from the HTML the server sent."""
    for block in INIT.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for value in data.values():
            if isinstance(value, dict) and (value.get("configurable") or {}).get("spConfig"):
                return value["configurable"]["spConfig"]
    return None


def plain_menu(options: list[dict], config: dict | None, base: float) -> list[dict]:
    """The ordinary theme's menu: each option's size, whether it can be chosen, and its
    price from the page's own price table (`spConfig.optionPrices`, by the option's child
    product). The surcharge its label prints must agree with that price against the price
    box, or the entry carries a `label_price` that does not."""
    table = (config or {}).get("optionPrices", {})
    by_label = {}
    for attribute in ((config or {}).get("attributes") or {}).values():
        for option in attribute.get("options", []):
            amounts = {table.get(str(p), {}).get("finalPrice", {}).get("amount")
                       for p in option.get("products", [])}
            by_label[option["label"]] = amounts.pop() if len(amounts) == 1 else None
    out = []
    for option in options:
        match = LABEL.match(option["text"])
        size = match.group("size") if match else option["text"]
        delta = 0.0
        if match and match.group("amount"):
            delta = float(match.group("amount")) * (1 if match.group("sign") == "+" else -1)
        entry = {"label": size, "buyable": not option["disabled"], "price": by_label.get(size)}
        entry["label_price"] = round(base + delta, 2)
        out.append(entry)
    return out


# --------------------------------------------------------------------------- the browser


def menu_options(page) -> list[dict]:
    """The size menu's real options, the placeholder left out."""
    options = page.eval_on_selector_all(
        ".super-attribute-select option",
        "els => els.map(e => ({text: e.textContent.trim(), disabled: e.disabled, value: e.value}))")
    return [o for o in options if o["value"]]


def server_html(url: str, user_agent: str | None) -> str:
    """The product page as the server sends it, before any script runs."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent or "Python-urllib/3"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", errors="replace")


def price_box(page) -> float | None:
    text = page.inner_text(".product-info-main .price-box .price")
    found = re.search(r"\d+\.\d\d", text.replace(",", ""))
    return float(found.group(0)) if found else None


def open_listing(context, url: str):
    page = context.new_page()
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1500)
    return page


def check_listing(browser, listing: dict) -> tuple[list[str], dict]:
    """Every size of one listing under both themes, and the gated reveal. Returns the
    problems and what was read, for the line printed."""
    problems, seen = [], {}
    sent = server_html(listing["url"], None)
    plain = browser.new_context(viewport={"width": 1200, "height": 701})
    page = open_listing(plain, listing["url"])
    base = price_box(page)
    menu = plain_menu(menu_options(page), spconfig_in(sent), base or 0.0)
    plain_text = page.inner_text("body") + "\n" + sent
    plain.close()
    problems += menu_problems(menu, listing, "plain")
    # The ordinary theme publishes every size's price twice, in its price table and as the
    # surcharge on the label: a size with no price in the table is a blind check, not a pass.
    for entry, (size, price, _) in zip(menu, listing["sizes"]):
        if entry["price"] is None:
            problems.append(f"plain {entry['label']} has no price in the page's price table")
        if abs(entry["label_price"] - price) > 0.001:
            problems.append(f"plain {entry['label']} label reads {money(entry['label_price'])}, "
                            f"not {money(price)}")
    seen["plain"] = menu
    seen["plain_leaks"] = leaked(plain_text, listing)

    gated = browser.new_context(viewport={"width": 1200, "height": 701}, user_agent=GATED_UA)
    page = open_listing(gated, listing["url"])
    title = " ".join(page.inner_text("h1.page-title").split())
    if title != listing["name"]:
        problems.append(f"the page is titled {title!r}, not {listing['name']!r}")
    options = menu_options(page)
    if any(SURCHARGE.search(o["text"]) for o in options):
        problems.append("gated menu labels carry a surcharge")
    menu = [{"label": o["text"], "buyable": not o["disabled"], "price": None} for o in options]
    problems += menu_problems(menu, listing, "gated")
    before = price_box(page)
    if before is None or abs(before - listing["advertised"]) > 0.001:
        problems.append(f"gated price box {before} before a size is chosen, not the advertised "
                        f"{money(listing['advertised'])}")
    # What the page shows and what the server sent, both: the text a browser renders, the
    # document after scripts ran, and the HTML before they did.
    shown = leaked("\n".join((page.inner_text("body"), page.content(),
                              server_html(listing["url"], GATED_UA))), listing)
    if shown:
        problems.append(f"gated page shows {shown} before a size is chosen")
    revealed = {}
    for option, (size, price, can) in zip(options, listing["sizes"]):
        if option["disabled"] or not can:
            continue
        page.select_option(".super-attribute-select", value=option["value"])
        page.wait_for_timeout(REVEAL_WAIT_MS)
        revealed[size] = price_box(page)
        if revealed[size] is None or abs(revealed[size] - price) > 0.001:
            problems.append(f"gated {size} chosen shows {revealed[size]}, not {money(price)}")
    gated.close()
    seen.update(gated=menu, before=before, revealed=revealed)
    return problems, seen


def results_in_browser(browser, brand: str) -> tuple[int, bool]:
    """The cards in the results grid and whether a pager's next link exists, as the gated
    browser renders the page."""
    context = browser.new_context(viewport={"width": 1200, "height": 701}, user_agent=GATED_UA)
    page = context.new_page()
    page.goto(f"{BASE}/catalogsearch/result/?q={brand}", wait_until="networkidle")
    cards = page.eval_on_selector_all(".products.list.items.product-items > li.product-item",
                                      "els => els.length")
    pager = page.query_selector(".pages .action.next") is not None
    context.close()
    return cards, pager


# ------------------------------------------------------------------------------ the report


def page_differences(live: dict, stored: dict) -> list[str]:
    """How the live results page differs from a page record a batch stored, on the fields
    the stored record kept, empty when they agree. A record written before 22 October 2026
    kept no listing titles, so a title is compared only where the stored record has one;
    until this day the two were compared whole, and every record before box v14 differed
    from the live page by its titles alone. Which reader read a page is a condition of the
    run, not a property of the shop, so it is never compared."""
    found = [f"{key}: {stored[key]!r} stored, {live.get(key)!r} live"
             for key in ("url", "count", "total", "next_page", "pages")
             if key in stored and live.get(key) != stored[key]]
    if len(live["listings"]) != len(stored["listings"]):
        found.append(f"{len(stored['listings'])} listings stored, {len(live['listings'])} live")
    for n, (old, new) in enumerate(zip(stored["listings"], live["listings"]), 1):
        kept = {key: new.get(key) for key in old}
        if kept != old:
            found.append(f"listing {n}: {old} stored, {kept} live")
    return found


def stored_page(batch: pathlib.Path) -> dict:
    """The page record a batch stored, the same on every row that has one, or refused."""
    suite = json.loads((batch / "suite.json").read_text())
    pages = [row["box"]["page"] for row in suite["rows"] if (row.get("box") or {}).get("page")]
    if not pages or any(p != pages[0] for p in pages):
        raise SystemExit(f"{batch.name} has no single stored page record")
    return pages[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", required=True,
                        help="a fixture under env/fixtures, by name, or a path to one")
    parser.add_argument("--page-record", type=pathlib.Path, metavar="BATCH",
                        help="also compare the results page with the page record this batch stored")
    parser.add_argument("--only", nargs="*", help="check only these listing URLs' keys, e.g. igr-clm-03")
    args = parser.parse_args()
    path = pathlib.Path(args.fixture)
    path = path if path.exists() else HERE / "fixtures" / args.fixture
    fixture = json.loads(path.read_text())
    brand = fixture["_generated"]["brand"]
    url = f"{BASE}/catalogsearch/result/?q={brand}"
    lines: list[tuple[bool, str]] = []

    def record(ok: bool, text: str) -> None:
        lines.append((ok, text))
        print(f"  [{'pass' if ok else 'FAIL'}] {text}", flush=True)

    print(f"{path.name}: {brand}, {len(fixture['families'])} listings")
    orders = {}
    for label, agent in (("gated", GATED_UA), ("plain", "Python-urllib/3")):
        live = page_module.fetch(url, user_agent=agent).record()
        orders[label] = [item["url"] for item in live["listings"]]
        problems = results_problems(live, fixture)
        record(not problems, f"results page, {label} user agent: {live['count']} cards, total "
                             f"{live['total']}, next page {live['next_page']}; every URL, seller and "
                             f"card price the fixture's" if not problems else
                             f"results page, {label}: " + "; ".join(problems))
        if label == "gated" and args.page_record:
            stored = stored_page(args.page_record)
            differences = page_differences(live, stored)
            record(not differences, f"results page equals the page record of {args.page_record.name}: "
                                    f"{len(stored['listings'])} sellers, advertised prices and URLs in order"
                   if not differences else f"results page differs from {args.page_record.name}: "
                                           + "; ".join(differences))
    record(orders["gated"] == orders["plain"],
           "the two user agents list the listings in the same order")

    from playwright.sync_api import sync_playwright  # noqa: E402  (.venv-naive only)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        cards, pager = results_in_browser(browser, brand)
        record(cards == len(fixture["families"]) and not pager,
               f"results page in the gated browser: {cards} cards in the grid, pager "
               f"{'present' if pager else 'absent'}")
        leaks_plain = 0
        for listing in expected(fixture):
            key = listing["url"].rsplit("/", 1)[-1].removesuffix(".html")
            if args.only and key not in args.only:
                continue
            problems, seen = check_listing(browser, listing)
            leaks_plain += bool(seen["plain_leaks"])
            sizes = ", ".join(f"{e['label']} {money(e['price']) if e['price'] is not None else '?'}"
                              f"{'' if e['buyable'] else ' sold out'}" for e in seen["plain"])
            record(not problems,
                   f"{key} {listing['seller']}: {sizes}; gated shows {money(seen['before'] or 0)} "
                   f"until chosen, then {', '.join(f'{s} {money(v)}' for s, v in seen['revealed'].items())}"
                   if not problems else f"{key} {listing['seller']}: " + "; ".join(problems))
        browser.close()
    # The leak test is only worth something if it finds the prices the ordinary theme
    # publishes: run on that theme it must fire on every listing with a second price.
    multi = sum(1 for l in expected(fixture)
                if (not args.only or l["url"].rsplit("/", 1)[-1].removesuffix(".html") in args.only)
                and len({money(p) for _, p, _ in l["sizes"]} - {money(l["advertised"])}))
    record(leaks_plain == multi, f"the leak test fires on the ordinary theme for {leaks_plain} of "
                                 f"{multi} listings with a price besides the advertised one")
    failed = sum(1 for ok, _ in lines if not ok)
    print(f"\n{len(lines)} checks, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
