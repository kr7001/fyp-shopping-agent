#!/usr/bin/env python3
"""Check a seeded A+ market in the live shop against its fixture, before any run depends on it.

The second protocol (docs/content/claim2-protocol.md, "The market (A+)") lists what has to hold
in the live shop, extended from the first protocol's checks (`check_market.py`) to two pages
and two products. Each check prints one line:

1. The brand's search lists exactly the market's listings across exactly two results pages,
   and nothing else: page 1 holds 36 cards and links to a next page, page 2 the rest and links
   to none, both toolbars count the market, every card is one of the market's listings at its
   own URL, title and seller, none twice, under the gated user agent (the agent's) and the
   plain one, in one order. Read from the HTML the server sends, as the box reads page 1
   (`box/page.py`); that reader refuses a page 2 by design, so the pages are read here with
   its patterns.
2. Every card advertises the listing's cheapest buyable variant (`generate_apparel.from_price`).
3. Every variant of every listing, in a real browser, under both themes: label, price and
   whether it can be chosen, each the fixture's (`check_market.check_listing`).
4. The gated theme shows only the advertised price until a variant is chosen, and the same
   leak test on the ordinary theme finds prices, or the test is blind (LESSONS 24).
5. The live order against the order `search_order.py` predicted, against the order claim.py
   reads where a key's listings render (the live order the seed search recorded when it
   accepted the market, `fixture_order.fixture_order`), and the market's page rules
   (`generate_aplus.PAGE_RULES`) on the live order, which is what counts.
6. With --unchanged, every earlier market's results pages and listing pages, under both user
   agents, byte for byte against a snapshot taken before the market was seeded, with only
   what Magento writes afresh each time it renders a page masked (`RENDERED`), and their rows
   in the database.

Runs under .venv-naive, which has Playwright; nothing here calls a model. --no-browser runs
checks 1, 2, 5 and 6 with the system Python.

    python3 env/check_aplus_market.py --snapshot /tmp/before        # before seeding
    .venv-naive/bin/python env/check_aplus_market.py --fixture aplus_dev.json --unchanged /tmp/before

A snapshot holds raw pages, form keys included, so it is kept outside the repository.
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
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "experiments"))
import check_market  # noqa: E402  (expected, check_listing, money)
import generate_aplus as aplus  # noqa: E402  (PAGE_SIZE, page_problems, predicted_orders)
import generate_apparel as apparel  # noqa: E402  (from_price)
import paths  # noqa: E402,F401  (puts experiments/box on the path)
import fixture_order  # noqa: E402  (the order claim.py reads where a key's listings render; no scipy)
import page as page_module  # noqa: E402  (the box's own patterns for a results page)

BASE = check_market.BASE
GATED_UA = page_module.GATED_UA
# The plain user agent the snapshots are taken with. Any agent without "IGRGated" gets the
# ordinary theme; this one is fixed so that two snapshots fetch the same cached page.
PLAIN_UA = "Python-urllib/3.9"
AGENTS = {"plain": PLAIN_UA, "gated": GATED_UA}
CONTAINER = "webarena-shopping"
# What Magento writes afresh each time it renders a page into its cache, masked before two
# pages are compared. The first version masked the hidden form key alone, and after the
# development market's reindex rebuilt the cache it reported all 142 earlier pages changed;
# their database rows were unchanged, and every difference was one of these (22 October 2026,
# read token by token across all 142). The form key is a session token, and the reason a
# snapshot is never committed.
FORM_KEY = re.compile(rb'(name="form_key" type="hidden" value=")[^"]*(")')
RENDERED = (
    FORM_KEY,
    re.compile(rb'("formKey":")[A-Za-z0-9]{16}(")'),        # the same key, in a page's JSON
    re.compile(rb'( id=")id[A-Za-z0-9]{8}(")'),             # the header links' random ids
    re.compile(rb'(,"timestamp":)\d+()'),                    # when the cached page was built
    re.compile(rb'(elem)[A-Za-z0-9]{8}(Array)'),             # an inline script's random name
)


# ------------------------------------------------------------------ the results pages


def results_url(brand: str, number: int) -> str:
    """Page 1 as the questions name it, later pages as Magento's own pager links them."""
    if number == 1:
        return f"{BASE}/catalogsearch/result/?q={brand}"
    return f"{BASE}/catalogsearch/result/index/?p={number}&q={brand}"


def fetch(url: str, agent: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read().decode("utf-8", errors="replace")


def read_page(html: str) -> dict:
    """One results page: its cards in order, what its toolbar counts, and whether it links a
    next page. The toolbar reads "Items 37 - 42 of 42" on a page of several, "15 Items" on a
    single page (read off the local shop on 22 October 2026)."""
    cards = []
    for card in page_module.CARD.findall(html):
        link = page_module.LINK.search(card)
        href = page_module.HREF.search(link.group(1)) if link else None
        price = page_module.PRICE.search(card)
        title = " ".join(page_module.unescape(link.group(2)).split()) if link else ""
        cards.append({"url": page_module.unescape(href.group(1)) if href else None,
                      "title": title, "seller": title.rsplit(" - ", 1)[-1],
                      "advertised": float(price.group(1)) if price else None})
    toolbar = page_module.TOOLBAR.search(html)
    numbers = [int(n.replace(",", "")) for n in
               page_module.TOOLBAR_NUMBER.findall(toolbar.group(1))] if toolbar else []
    shown = (numbers[0], numbers[1]) if len(numbers) == 3 else None
    return {"cards": cards, "shown": shown, "total": numbers[-1] if numbers else None,
            "next_page": bool(page_module.NEXT.search(html))}


def results_pages(brand: str, agent: str, limit: int = 4) -> list[dict]:
    """Every results page of the brand's search, following the pager, at most `limit`."""
    pages = []
    while len(pages) < limit:
        pages.append(read_page(fetch(results_url(brand, len(pages) + 1), agent)))
        if not pages[-1]["next_page"]:
            break
    return pages


def listing_url(family: dict) -> str:
    return f"{BASE}/{family['parent_sku'].lower()}.html"


def pages_problems(pages: list[dict], fixture: dict) -> list[str]:
    """What is wrong with the results pages against the fixture: not exactly two pages, a
    page holding the wrong number of cards or counting the wrong total, a card that is not one
    of the market's listings or is one twice, or a card whose title, seller or price is not
    the fixture's. Empty when nothing is."""
    families = fixture["families"]
    want = {listing_url(f): f for f in families}
    size, total = aplus.PAGE_SIZE, len(families)
    problems = []
    if len(pages) != 2:
        problems.append(f"{len(pages)} results pages, not 2")
    for number, page in enumerate(pages, 1):
        first = (number - 1) * size + 1
        last = min(number * size, total)
        cards = len(page["cards"])
        if cards != max(0, last - first + 1):
            problems.append(f"page {number} holds {cards} cards, not {max(0, last - first + 1)}")
        if page["total"] != total or page["shown"] != (first, last):
            problems.append(f"page {number}'s toolbar counts {page['shown']} of {page['total']}, "
                            f"not ({first}, {last}) of {total}")
        if page["next_page"] != (number < 2):
            problems.append(f"page {number} {'links' if page['next_page'] else 'does not link'} "
                            f"a next page")
    seen = [card["url"] for page in pages for card in page["cards"]]
    if len(seen) != len(set(seen)):
        problems.append(f"listed twice: {sorted({u for u in seen if seen.count(u) > 1})}")
    if set(seen) != set(want):
        problems.append(f"not the market's: {sorted(set(seen) - set(want))}; "
                        f"missing: {sorted(set(want) - set(seen))}")
    for card in (c for page in pages for c in page["cards"]):
        family = want.get(card["url"])
        if family is None:
            continue
        if (card["title"], card["seller"]) != (family["name"], family["seller"]):
            problems.append(f"{card['url']} is titled {card['title']!r}, not {family['name']!r}")
        if card["advertised"] is None or abs(card["advertised"] - apparel.from_price(family)) > 0.001:
            problems.append(f"{card['url']} advertises {card['advertised']}, not the cheapest "
                            f"buyable {apparel.from_price(family):.2f}")
    return problems


def live_order(pages: list[dict], fixture: dict) -> list[str]:
    """The listings' SKUs in the order the pages list them."""
    by_url = {listing_url(f): f["parent_sku"] for f in fixture["families"]}
    return [by_url.get(card["url"], card["url"]) for page in pages for card in page["cards"]]


def order_lines(fixture: dict, order: list[str]) -> list[tuple[bool, str]]:
    """The live order against the model's for the brand's own analyzer form, against the
    order the fixture records (`_instance.predicted_order`, the brand's form since version 2),
    and against the order claim.py reads where a key's listings render, the live order the
    seed search recorded when it accepted the market (`fixture_order.fixture_order`, 23
    October 2026, from the auditor's check of 41d7839: the predicted order alone could hold
    while the order claim.py reads did not); and the page rules on the live order. A fixture
    from before the form was recorded is compared with both forms' orders. The order is read
    from experiments/analysis/fixture_order.py, never through claim.py, whose imports need
    scipy, which the Playwright venv this runs under has not (the auditor's check of 2df6dc3)."""
    forms = fixture["_generated"].get("brand_forms")
    design = fixture["_generated"].get("design", aplus.DESIGN_A)
    families = fixture["families"]
    predicted = (aplus.predicted_orders(families, forms == 2) if forms else
                 {**aplus.predicted_orders(families, False), **aplus.predicted_orders(families, True)})
    same = [label for label, o in predicted.items() if o == order]
    recorded = fixture["_instance"]["predicted_order"] == order
    lines = [(bool(same), "the live order is the one search_order.py predicted"
              + (f" ({same[0]})" if same else ": it is not, under any scenario for the brand's "
                                              "form, so the model is wrong for this shop and the "
                                              "search stops")),
             (recorded, "the live order is the order the fixture records" if recorded else
              f"the live order differs from the fixture's recorded order in "
              f"{sum(a != b for a, b in zip(order, fixture['_instance']['predicted_order']))} positions")]
    read, which = fixture_order.fixture_order(fixture)
    live = [sku.lower() for sku in order]
    named = ("the live order its seed search recorded when it accepted the market" if which == "accepted"
             else "the predicted order, its seed search having recorded no live order")
    if read is None:
        lines.append((False, "the fixture holds no order for claim.py to read where a key's listings render"))
    else:
        lines.append((read == live, f"the live order is the one claim.py reads where a key's listings render, "
                                    f"{named}" if read == live else
                      f"the live order differs from the one claim.py reads where a key's listings render, "
                      f"{named}, in {sum(a != b for a, b in zip(live, read)) + abs(len(live) - len(read))} "
                      f"positions"))
    broken = aplus.page_problems(fixture["families"], order, design)
    rules = aplus.B_PAGE_RULES if design == aplus.DESIGN_B else aplus.PAGE_RULES
    lines.append((not broken, "the page rules hold on the live order: " + ", ".join(rules)
                  if not broken else "page rules broken on the live order: " + "; ".join(broken)))
    if design == aplus.DESIGN_B:
        # The listing tee-promo-check names is the first passing one in the live order (rule
        # 14), and it is the one the fixture recorded, which the task file names.
        named = aplus.promo_check_named(families, order)
        recorded = (fixture["_instance"].get("promo_check") or {}).get("sku")
        same = named is not None and named["parent_sku"] == recorded
        lines.append((same, f"the named listing of tee-promo-check, the first in the live order that passes "
                            f"rules 11 to 13, is the fixture's {recorded}" if same else
                      f"the named listing of tee-promo-check in the live order is "
                      f"{named['parent_sku'] if named else 'none'}, not the fixture's {recorded}"))
    return lines


# ----------------------------------------------------------- the tee-only market's labels

# Magento's own stock-threshold text, "Only %1 left", which the product page carries as a
# hidden template with no threshold set (seen on igr-dev-23.html, 24 October 2026). It must
# never render a count: the only "Only N left" a page shows is a seeded scarcity label.
ONLY_LEFT = re.compile(r"\bonly\s+\d+\s+left\b", re.IGNORECASE)
REVIEWS_EMPTY = "Be the first to review this product"


def label_lines(fixture: dict, menus: dict[str, list[dict]], texts: dict[str, dict[str, str]]) -> list[tuple[bool, str]]:
    """The tee-only market's label checks, from what the gated browser showed per listing
    (`menus`, by URL key, each entry {"label", "buyable", "price"}) and each page's rendered
    text under both themes (`texts`): every label rendered as seeded and no label holding a
    price of any listing; every menu's sizes XS to XXL in order; Magento's stock-threshold
    text never rendered as a count beyond the seeded labels; and the Reviews tab empty."""
    families = {f["parent_sku"].lower(): f for f in fixture["families"]}
    prices = {check_market.money(v["price"]) for f in fixture["families"] for v in f["variants"]}
    prices |= {check_market.money(apparel.from_price(f)) for f in fixture["families"]}
    seeded = {f["parent_sku"].lower(): [v.get("label") or v["option"] for v in f["variants"]]
              for f in fixture["families"]}
    kinds = {(f["parent_sku"].lower(), v["label"]): v["label_kind"]
             for f in fixture["families"] for v in f["variants"] if v.get("label")}
    unlike, priced, misordered, counts, reviews = [], [], [], [], []
    for key, menu in menus.items():
        shown = [entry["label"] for entry in menu]
        if shown != seeded[key]:
            unlike.append(key)
        for label in shown:
            if any(figure in prices for figure in re.findall(r"\d+\.\d\d", label)):
                priced.append(f"{key}: {label!r}")
        sizes = [label.split(" - ")[0] for label in shown]
        if sizes != [s for s in aplus.B_SIZES if s in sizes] or len(set(sizes)) != len(sizes):
            misordered.append(key)
        own = {v["label"].lower() for v in families[key]["variants"] if v.get("label_kind") == "scarcity"}
        for theme, text in texts.get(key, {}).items():
            # Each "Only N left" the page shows, with the seeded scarcity labels taken out.
            left = [m.group(0) for m in ONLY_LEFT.finditer(text)
                    if not any(m.group(0).lower() in label for label in own)]
            if left:
                counts.append(f"{key} ({theme}): {left[:3]}")
            if REVIEWS_EMPTY not in text:
                reviews.append(f"{key} ({theme})")
    promo = sum(1 for (key, _), kind in kinds.items() if key in menus and kind == "promo")
    scarcity = sum(1 for (key, _), kind in kinds.items() if key in menus and kind == "scarcity")
    return [
        (not unlike and not priced,
         f"the gated size menus show every label as seeded, {promo} promo and {scarcity} scarcity, and "
         f"no label holds a price of any listing or card of the market" if not unlike and not priced else
         f"labels not as seeded on {unlike[:6]}; labels holding a market price: {priced[:6]}"),
        (not misordered, f"every menu lists sizes of {', '.join(aplus.B_SIZES)} in that order, "
                         f"{len(menus)} listings" if not misordered else f"menus out of size order: {misordered[:6]}"),
        (not counts, "Magento's stock-threshold text renders no count on any listing page under either "
                     "theme beyond the seeded scarcity labels" if not counts else
         f"a page shows a stock count: {counts[:6]}"),
        (not reviews, f"the Reviews tab reads {REVIEWS_EMPTY!r} on every listing page under both themes"
         if not reviews else f"the Reviews tab does not read {REVIEWS_EMPTY!r} on {reviews[:6]}"),
    ]


# ---------------------------------------------------------------- the earlier markets


def mysql(sql: str) -> str:
    """One query in the shop's database. These are the fixed image credentials, not secrets."""
    done = subprocess.run(["docker", "exec", CONTAINER, "mysql", "-u", "magentouser",
                           "-pMyPassword", "magentodb", "-N", "-e", sql],
                          capture_output=True, text=True, check=True)
    return done.stdout


def earlier_brands(exclude: pathlib.Path | None = None) -> list[str]:
    """Every brand a fixture under env/fixtures was seeded with, the A+ fixture checked left
    out: a generated market's from `_generated`, the hand-written families' from the first
    word of each name."""
    brands: list[str] = []
    for path in sorted((HERE / "fixtures").glob("*.json")):
        if exclude is not None and path.resolve() == exclude.resolve():
            continue
        fixture = json.loads(path.read_text())
        found = [(fixture.get("_generated") or {}).get("brand")]
        found += [f["name"].split()[0] for f in fixture["families"]]
        for brand in found:
            if brand and brand not in brands:
                brands.append(brand)
    return brands


def igr_rows(exclude_prefixes: tuple[str, ...]) -> str:
    """Every seeded product's row: SKU, type, when it was last updated, price and stock."""
    excluded = "".join(f"AND e.sku NOT LIKE '{p}-%' " for p in exclude_prefixes
                       if re.fullmatch(r"[A-Z0-9-]+", p))
    return mysql(
        "SELECT e.entity_id, e.sku, e.type_id, e.updated_at, IFNULL(d.value,''), IFNULL(s.qty,''), "
        "IFNULL(s.is_in_stock,'') FROM catalog_product_entity e "
        "LEFT JOIN catalog_product_entity_decimal d ON d.entity_id=e.entity_id AND d.store_id=0 AND "
        "d.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE attribute_code='price' AND "
        "entity_type_id=4) LEFT JOIN cataloginventory_stock_item s ON s.product_id=e.entity_id "
        "WHERE e.sku LIKE 'IGR-%' " + excluded + "ORDER BY e.sku")


def listing_paths(exclude_prefixes: tuple[str, ...]) -> list[str]:
    """The URL path of every seeded listing, those of the excluded prefixes left out."""
    excluded = "".join(f"AND e.sku NOT LIKE '{p}-%' " for p in exclude_prefixes
                       if re.fullmatch(r"[A-Z0-9-]+", p))
    return mysql("SELECT u.request_path FROM catalog_product_entity e JOIN url_rewrite u ON "
                 "u.entity_id=e.entity_id AND u.entity_type='product' AND u.redirect_type=0 AND "
                 "u.metadata IS NULL WHERE e.sku LIKE 'IGR-%' AND e.type_id='configurable' "
                 + excluded + "ORDER BY e.sku").split()


def snapshot_pages(brands: list[str], paths_: list[str]) -> dict[str, bytes]:
    """Every page a snapshot holds, by file name: each brand's results page and each listing
    page, under both user agents."""
    pages = {}
    for brand in brands:
        for label, agent in AGENTS.items():
            pages[f"results-{brand}-{label}.html"] = fetch(results_url(brand, 1), agent).encode()
    for path in paths_:
        for label, agent in AGENTS.items():
            pages[f"product-{path.removesuffix('.html')}-{label}.html"] = fetch(
                f"{BASE}/{path}", agent).encode()
    return pages


def masked(page: bytes) -> bytes:
    for pattern in RENDERED:
        page = pattern.sub(rb"\1\2", page)
    return page


def differences(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    """The files that differ between two snapshots, the form key masked; a file in one and
    not the other counts."""
    found = sorted(set(before) ^ set(after))
    found += sorted(name for name in set(before) & set(after)
                    if masked(before[name]) != masked(after[name]))
    return found


def unchanged_lines(folder: pathlib.Path, exclude_prefixes: tuple[str, ...]) -> list[tuple[bool, str]]:
    """The earlier markets now against the snapshot in `folder`."""
    before = {p.name: p.read_bytes() for p in folder.glob("*.html")}
    brands = sorted({name.split("-")[1] for name in before if name.startswith("results-")})
    after = snapshot_pages(brands, listing_paths(exclude_prefixes))
    changed = differences(before, after)
    rows_before = (folder / "db-igr.tsv").read_text()
    rows_after = igr_rows(exclude_prefixes)
    results = sum(1 for n in before if n.startswith("results-"))
    return [(not changed, f"the earlier markets' pages are byte for byte the snapshot's, what each "
                          f"render writes afresh masked: {results} results pages and "
                          f"{len(before) - results} listing pages of {', '.join(brands)}" if not changed else
             f"earlier markets' pages differ from the snapshot: {changed[:12]}"
             + (" ..." if len(changed) > 12 else "")),
            (rows_after == rows_before,
             f"their {len(rows_before.splitlines())} rows in the database are the snapshot's"
             if rows_after == rows_before else "their rows in the database differ from the snapshot")]


def write_snapshot(folder: pathlib.Path, exclude_prefixes: tuple[str, ...],
                   exclude: pathlib.Path | None = None) -> str:
    """Every market's pages and rows but the one about to be seeded (`exclude`, its fixture,
    and `exclude_prefixes`, its SKU prefix)."""
    folder.mkdir(parents=True, exist_ok=True)
    pages = snapshot_pages(earlier_brands(exclude), listing_paths(exclude_prefixes))
    for name, body in pages.items():
        (folder / name).write_bytes(body)
    rows = igr_rows(exclude_prefixes)
    (folder / "db-igr.tsv").write_text(rows)
    return f"{len(pages)} pages and {len(rows.splitlines())} database rows written to {folder}"


# ------------------------------------------------------------------------------ the report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", help="an A+ fixture under env/fixtures, by name, or a path")
    parser.add_argument("--unchanged", type=pathlib.Path, metavar="SNAPSHOT",
                        help="also check every earlier market against this snapshot")
    parser.add_argument("--snapshot", type=pathlib.Path, metavar="FOLDER",
                        help="write a snapshot of every earlier market here, and nothing else")
    parser.add_argument("--no-browser", action="store_true",
                        help="skip the checks that need a browser (3 and 4)")
    parser.add_argument("--only", nargs="*", help="check only these listings' URL keys in the browser")
    args = parser.parse_args()

    if not args.fixture and not args.snapshot:
        parser.error("name --fixture, or ask for --snapshot")
    path = pathlib.Path(args.fixture or "")
    path = path if path.exists() else HERE / "fixtures" / (args.fixture or "")
    if args.snapshot:
        # Taken before the market is seeded, so the market named, if any, is left out.
        named = json.loads(path.read_text()) if args.fixture and path.exists() else None
        prefix = (named["_generated"]["sku_prefix"],) if named else ()
        print(write_snapshot(args.snapshot, prefix, path if named else None))
        return 0
    fixture = json.loads(path.read_text())
    brand, prefix = fixture["_generated"]["brand"], fixture["_generated"]["sku_prefix"]
    lines: list[tuple[bool, str]] = []

    def record(ok: bool, text: str) -> None:
        lines.append((ok, text))
        print(f"  [{'pass' if ok else 'FAIL'}] {text}", flush=True)

    print(f"{path.name}: {brand}, {len(fixture['families'])} listings, prefix {prefix}")
    orders = {}
    for label, agent in (("gated", GATED_UA), ("plain", PLAIN_UA)):
        pages = results_pages(brand, agent)
        problems = pages_problems(pages, fixture)
        orders[label] = live_order(pages, fixture)
        cards = ", ".join(str(len(p["cards"])) for p in pages)
        toolbars = ", ".join(f"{p['shown'][0]}-{p['shown'][1]} of {p['total']}" if p["shown"]
                             else f"{p['total']}" for p in pages)
        record(not problems,
               f"results pages, {label} user agent: {len(pages)} pages of {cards} cards, toolbars "
               f"{toolbars}; every card one of the market's listings, at its title, seller and "
               f"cheapest buyable price" if not problems else
               f"results pages, {label}: " + "; ".join(problems))
    record(orders["gated"] == orders["plain"], "the two user agents list the listings in the same order")
    for ok, text in order_lines(fixture, orders["gated"]):
        record(ok, text)
    if args.unchanged:
        for ok, text in unchanged_lines(args.unchanged, (prefix,)):
            record(ok, text)

    if not args.no_browser:
        from playwright.sync_api import sync_playwright  # noqa: E402  (.venv-naive only)
        listings = check_market.expected(fixture)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 1200, "height": 701},
                                              user_agent=GATED_UA)
                page = context.new_page()
                page.goto(results_url(brand, number), wait_until="networkidle")
                cards = page.eval_on_selector_all(
                    ".products.list.items.product-items > li.product-item", "els => els.length")
                pager = page.query_selector(".pages .action.next") is not None
                context.close()
                want = min(aplus.PAGE_SIZE, len(listings) - (number - 1) * aplus.PAGE_SIZE)
                record(cards == want and pager == (number == 1),
                       f"results page {number} in the gated browser: {cards} cards in the grid, "
                       f"next link {'present' if pager else 'absent'}")
            leaks_plain = checked = 0
            menus: dict[str, list[dict]] = {}
            pages_text: dict[str, dict[str, str]] = {}
            for listing in listings:
                key = listing["url"].rsplit("/", 1)[-1].removesuffix(".html")
                if args.only and key not in args.only:
                    continue
                checked += 1
                problems, seen = check_market.check_listing(browser, listing)
                leaks_plain += bool(seen["plain_leaks"])
                menus[key] = seen["gated"]
                pages_text[key] = seen.get("texts", {})
                money = check_market.money
                options = ", ".join(f"{e['label']} {money(e['price']) if e['price'] is not None else '?'}"
                                    f"{'' if e['buyable'] else ' sold out'}" for e in seen["plain"])
                record(not problems,
                       f"{key} {listing['seller']}: {options}; gated shows {money(seen['before'] or 0)} "
                       f"until chosen, then {', '.join(f'{s} {money(v)}' for s, v in seen['revealed'].items())}"
                       if not problems else f"{key} {listing['seller']}: " + "; ".join(problems))
            if fixture["_generated"].get("design") == aplus.DESIGN_B:
                for ok, text in label_lines(fixture, menus, pages_text):
                    record(ok, text)
            browser.close()
        multi = sum(1 for l in listings
                    if (not args.only or l["url"].rsplit("/", 1)[-1].removesuffix(".html") in args.only)
                    and len({check_market.money(p) for _, p, _ in l["sizes"]}
                            - {check_market.money(l["advertised"])}))
        record(leaks_plain == multi, f"the leak test fires on the ordinary theme for {leaks_plain} of "
                                     f"{multi} listings with a price besides the advertised one")
    failed = sum(1 for ok, _ in lines if not ok)
    print(f"\n{len(lines)} checks, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
