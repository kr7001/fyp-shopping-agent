#!/usr/bin/env python3
"""Read every results page of a search: how many listings there are, each seller, its
advertised price and URL, page after page until the pager has no next link.

This is the box's one look at the shop before the agent starts, and the only module in
`box/` that does I/O. Each page is read with the same user agent the agent's browser uses,
because `env/install_gated_theme.py` picks the price-suppressing theme by that header, in
one of two ways (`READERS`, box v16, 22 October 2026):

- rendered, the default: in a headless browser, as the agent sees it. The browser waits
  for the cards, and the rendered DOM is parsed by the card parser below. Playwright is
  in the project's own Playwright venv (`paths.NAIVE_PYTHON`), not the suite's
  interpreter, so the reading runs there, as `page.py URL --reader rendered`.
- fetch: the page's HTML over HTTP, parsed without a browser, which is how the box read
  the first results page alone until box v16. Magento renders the cards on the server.

Checked on 14 October 2026 against the gated Thornwood results page: 15
`<li class="item product product-item">` blocks, each with one `product-item-link` and one
`data-price-amount` labelled "As low as", a toolbar count of 15 and no pager, and the
agent's own whole-page card probe returns the same 15 prices in the same order. On 22
October 2026 the two readers gave the same listings, prices, URLs, count and pager on
Thornwood, Ashcombe and two pages of a paged search (`tests/test_page.py`, `LiveShop`).

It reads the results pages and nothing else: never a listing, a task file, an answer key or
a generated catalogue, and never the gated theme's encoded variant store (`STORE`).

    python experiments/box/page.py "http://localhost:7770/catalogsearch/result/?q=Thornwood" --reader fetch
    .venv-naive/bin/python experiments/box/page.py "http://localhost:7770/catalogsearch/result/?q=Thornwood"
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from html import unescape

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (where the Playwright venv is)

# Which shop a fetch sees is decided by the user agent, because `env/install_gated_theme.py`
# selects the price-suppressing theme that way. Defined once, here, and imported by the
# suite, so the box and the agent's browser cannot drift onto different shops.
GATED_UA = "Mozilla/5.0 IGRGated/1.0"

# One product card. Magento wraps every result in this `<li>` and uses the class nowhere
# else, so the two `product-item-link` anchors outside the cards, in the compare and
# wishlist sidebar templates, are never read: everything below is matched inside a card.
CARD = re.compile(r'<li class="item product product-item">(.*?)</li>', re.S)
LINK = re.compile(r'<a\b([^>]*\bclass="product-item-link"[^>]*)>(.*?)</a>', re.S)
HREF = re.compile(r'\bhref="([^"]+)"')
# The first price in a card is the one the card advertises, "As low as" on a listing with
# several sizes. A card without one is a parse failure, not a free listing.
PRICE = re.compile(r'\bdata-price-amount="([^"]+)"')
# "15 Items" on a single page, "Items 1-36 of 8535" when paged, so the total is the last
# number in the first toolbar block. Both read off the local shop on 14 October 2026.
TOOLBAR = re.compile(r'<p class="toolbar-amount"[^>]*>(.*?)</p>', re.S)
TOOLBAR_NUMBER = re.compile(r'<span class="toolbar-number">\s*([\d,]+)\s*</span>')
# Magento's pager link, `<a class="action  next"` with two spaces, rendered only when a
# later page exists. Read off a paged search of the local shop on 14 October 2026, with its
# address, escaped as the HTML writes it, on 22 October 2026:
# `href="http://localhost:7770/catalogsearch/result/index/?p=2&amp;q=jacket"`.
NEXT = re.compile(r'class="action\s+next"')
NEXT_LINK = re.compile(r'<a\b[^>]*\bclass="action\s+next"[^>]*>', re.S)
# "Items 37-72 of 4120" on a later page, "15 Items" on the only one: the first and last
# item a page shows, read so each page is held to its own cards (22 October 2026).
TOOLBAR_RANGE = re.compile(r'<span class="toolbar-number">\s*([\d,]+)\s*</span>\s*-\s*'
                           r'<span class="toolbar-number">\s*([\d,]+)\s*</span>')
# The gated theme's encoded variant store, every variant's price in a hidden attribute of a
# listing page (`env/gated_theme/.../configurable.phtml`), which an agent that runs its own
# JavaScript could decode. No results page holds it (checked on Thornwood and Ashcombe,
# rendered and fetched, 22 October 2026), and the reader removes any it finds before reading
# a card, so a card field is all it ever reads: the store's element, and any `data-igr`
# attribute anywhere. `analysis/leaks.py` looks for the same two words in the agent's logs.
STORE = re.compile(r'<div\b[^>]*\bid="igr-variant-store"[^>]*>.*?</div>|\sdata-igr(?:-[\w-]+)?="[^"]*"',
                   re.S)
# The two readers, the default first, and how many results pages one read follows at most.
# The claim markets span two at the shop's 36 a page. A search that runs past the limit is
# read up to it and recorded with its next page unread, which no plan is made over (`form.
# verify`, property 1 over every page).
READERS = ("rendered", "fetch")
MAX_PAGES = 5
# What the browser waits for before the rendered DOM is read: one product card.
CARD_SELECTOR = "li.item.product.product-item"


@dataclasses.dataclass(frozen=True)
class Listing:
    seller: str
    title: str | None   # None only for a listing read back from a record that kept no title
    url: str
    advertised: float   # the price the card shows, the cheapest option the listing has


@dataclasses.dataclass(frozen=True)
class Page:
    url: str                    # the first results page
    listings: list[Listing]     # in the order the pages show them, page after page
    total: int | None           # the toolbar's count, None when the page prints none
    next_page: bool             # a later results page exists that was not read
    pages: tuple[str, ...] = ()     # every results page read, in order (box v16)
    reader: str | None = None       # which of `READERS` read them, None for an older record
    # The product the box kept the listings of, and how many the pages held, when a plan
    # ranges over one product of several (`box.Scope`, box v17). None on every page read.
    scope: str | None = None
    of: int | None = None

    def record(self) -> dict:
        """What the box read, for the run record, so the verifier can check it against
        the live shop. Each listing's title since 22 October 2026, so the model parser's
        title normalisation can be replayed from the record; null in a page read back from
        an older record, which kept none. And since box v16 every results page read, and
        which reader read them. A run record holds the page as read; a page the box kept
        one product's listings of says so, should one ever be recorded."""
        record = {"url": self.url, "count": len(self.listings), "total": self.total,
                  "next_page": self.next_page, "pages": list(self.pages or (self.url,)),
                  "reader": self.reader,
                  "listings": [{"seller": item.seller, "advertised": item.advertised,
                                "url": item.url, "title": item.title} for item in self.listings]}
        if self.scope is not None:
            record.update(scope=self.scope, of=self.of)
        return record

    def by_price(self) -> list[Listing]:
        """Cheapest advertised first, the order every bound strategy opens listings in."""
        return sorted(self.listings, key=lambda item: (item.advertised, item.seller))


def from_record(data: dict) -> Page:
    """The page back from the record `Page.record` wrote into a run record, so a stored
    run's check can be replayed on the page the box read (20 October 2026). A record written
    before 22 October 2026 kept no title, and its listings come back with none, None, where
    until then they took their seller's name; no plan reads a title, and the model parser's
    title normalisation knows there is none to read (`normalise.titles_kept`)."""
    listings = [Listing(seller=item["seller"], title=item.get("title"), url=item["url"],
                        advertised=float(item["advertised"])) for item in data["listings"]]
    return Page(url=data["url"], listings=listings, total=data.get("total"),
                next_page=bool(data.get("next_page")),
                pages=tuple(data.get("pages") or (data["url"],)), reader=data.get("reader"))


def parse(html: str, url: str) -> Page:
    """The page's listings in the order shown, the toolbar total and the pager state.

    Raises ValueError rather than returning less than the page holds. A page with no cards,
    a card with no price, or a toolbar count the cards do not add up to would otherwise
    have the agent planned over a market that is not there. A page of several is held to
    its own range, "Items 37-72 of 4120", and the only page to its count, "15 Items". Any
    encoded variant store is removed first, so nothing but a card's fields is read.
    """
    html = STORE.sub("", html)
    cards = CARD.findall(html)
    if not cards:
        raise ValueError(f"no product cards on {url}")
    listings = []
    for n, card in enumerate(cards, 1):
        link = LINK.search(card)
        href = HREF.search(link.group(1)) if link else None
        if not link or not href:
            raise ValueError(f"card {n} on {url} has no product link")
        name = " ".join(unescape(link.group(2)).split())
        price = PRICE.search(card)
        if not price:
            raise ValueError(f"card {n} ({name}) on {url} shows no price")
        # The seller is what follows the last " - " in the name, as this shop writes it,
        # or the whole name when there is none.
        listings.append(Listing(seller=name.rsplit(" - ", 1)[-1], title=name,
                                url=unescape(href.group(1)), advertised=float(price.group(1))))
    first, last, total = item_range(html)
    next_page = bool(NEXT.search(html))
    if first is not None and last - first + 1 != len(listings):
        raise ValueError(f"the toolbar on {url} shows items {first}-{last} but {len(listings)} "
                         f"cards were read")
    if first is None and total is not None and not next_page and total != len(listings):
        raise ValueError(f"the toolbar on {url} counts {total} items but {len(listings)} "
                         f"cards were read")
    return Page(url=url, listings=listings, total=total, next_page=next_page, pages=(url,))


def item_range(html: str) -> tuple[int | None, int | None, int | None]:
    """The first and last item the page shows and the toolbar's total: (37, 72, 4120) for
    "Items 37-72 of 4120", (None, None, 15) for "15 Items", and all None with no toolbar."""
    toolbar = TOOLBAR.search(html)
    if not toolbar:
        return None, None, None
    numbers = [int(n.replace(",", "")) for n in TOOLBAR_NUMBER.findall(toolbar.group(1))]
    shown = TOOLBAR_RANGE.search(toolbar.group(1))
    total = numbers[-1] if numbers else None
    if not shown:
        return None, None, total
    return int(shown.group(1).replace(",", "")), int(shown.group(2).replace(",", "")), total


def next_url(html: str, url: str) -> str | None:
    """The pager's next link, unescaped and made absolute against `url`, or None."""
    tag = NEXT_LINK.search(STORE.sub("", html))
    href = HREF.search(tag.group(0)) if tag else None
    return urllib.parse.urljoin(url, unescape(href.group(1))) if href else None


def follow(url: str, html_of, reader: str, limit: int = MAX_PAGES) -> Page:
    """Every results page from `url`, each read by `html_of(page_url) -> html`, following
    the pager's next link until there is none or `limit` pages are read, as one Page: the
    listings page after page, the first page's total, every page read, and the next page
    left unread, if any. Each later page must start where the last one stopped, and the
    pages read to the end must hold the total, or this raises, as `parse` does for one."""
    pages: list[Page] = []
    while url is not None and len(pages) < limit:
        if url in (page.url for page in pages):
            raise ValueError(f"the pager leads back to {url}, already read")
        html = html_of(url)
        one = parse(html, url)
        read = sum(len(page.listings) for page in pages)
        first, _, _ = item_range(html)
        if pages and first != read + 1:
            raise ValueError(f"results page {len(pages) + 1} ({url}) starts at item {first}, "
                             f"after {read} were read")
        pages.append(one)
        url = next_url(html, url) if one.next_page else None
        if one.next_page and url is None:
            raise ValueError(f"results page {len(pages)} shows a next page with no address")
    listings = [item for page in pages for item in page.listings]
    unread = url is not None
    total = pages[0].total
    if total is not None and not unread and total != len(listings):
        raise ValueError(f"the toolbar counts {total} items but {len(listings)} cards were read "
                         f"on {len(pages)} pages")
    return Page(url=pages[0].url, listings=listings, total=total, next_page=unread,
                pages=tuple(page.url for page in pages), reader=reader)


def http_html(url: str, user_agent: str = GATED_UA, timeout: int = 20) -> str:
    """One HTTP request for a page, as the agent's browser would make it."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch(url: str, user_agent: str = GATED_UA, timeout: int = 20) -> Page:
    """One results page over HTTP, the box's reader until box v16, kept for the market
    check (`env/check_market.py`) and the parse probe, which read one page."""
    return dataclasses.replace(parse(http_html(url, user_agent, timeout), url), reader="fetch")


def render_pages(tab, url: str, timeout: int = 20, limit: int = MAX_PAGES) -> Page:
    """Every results page from `url` in a browser tab: go to the page, wait for a card,
    read the rendered DOM, follow the next link. Nothing is clicked, typed or run in the
    page, and no other page is visited: `tab` is asked only for `goto`, `wait_for_selector`
    and `content`."""
    def html_of(page_url: str) -> str:
        tab.goto(page_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        try:
            tab.wait_for_selector(CARD_SELECTOR, timeout=timeout * 1000)
        except Exception as fault:  # noqa: BLE001  Playwright's TimeoutError, the venv's own
            if type(fault).__name__ != "TimeoutError":
                raise
            # The fetch reader's refusal, in the same words: the page has no card.
            raise ValueError(f"no product cards on {page_url} within {timeout} s") from fault
        return tab.content()
    return follow(url, html_of, "rendered", limit)


def render(url: str, user_agent: str = GATED_UA, timeout: int = 20, limit: int = MAX_PAGES) -> Page:
    """`render_pages` in a fresh headless Chromium with the gated user agent, in this
    interpreter, which must have Playwright (the project's venv, `paths.NAIVE_PYTHON`)."""
    from playwright.sync_api import sync_playwright  # noqa: E402  (the Playwright venv only)
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            tab = browser.new_context(user_agent=user_agent).new_page()
            return render_pages(tab, url, timeout, limit)
        finally:
            browser.close()


def read(url: str, reader: str = READERS[0], user_agent: str = GATED_UA, timeout: int = 20,
         limit: int = MAX_PAGES) -> Page:
    """Every results page of the search `url` begins, by the reader named. The rendered
    reader runs in the project's Playwright venv, a child process that prints the record,
    since the suite's interpreter has no Playwright."""
    if reader == "fetch":
        return follow(url, lambda page_url: http_html(page_url, user_agent, timeout), "fetch", limit)
    if reader != "rendered":
        raise ValueError(f"no reader {reader!r}: one of {READERS}")
    if not paths.NAIVE_PYTHON.exists():
        raise RuntimeError(f"the rendered reader runs in the Playwright venv, {paths.NAIVE_PYTHON}, "
                           f"which is not there; read with the fetch reader instead")
    command = [str(paths.NAIVE_PYTHON), str(pathlib.Path(__file__).resolve()), url,
               "--reader", "rendered", "--user-agent", user_agent, "--timeout", str(timeout),
               "--limit", str(limit)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout * (limit + 2) + 60)
    if done.returncode != 0:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise ValueError(f"the rendered reader failed on {url}: {lines[-1] if lines else done.returncode}")
    return from_record(json.loads(done.stdout))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="the first results page to read")
    parser.add_argument("--reader", choices=READERS, default=READERS[0],
                        help="rendered, the default: in a headless browser, which needs "
                             "Playwright, so run it with .venv-naive/bin/python. fetch: over "
                             "HTTP")
    parser.add_argument("--user-agent", default=GATED_UA)
    parser.add_argument("--timeout", type=int, default=20, help="seconds per page")
    parser.add_argument("--limit", type=int, default=MAX_PAGES, help="results pages at most")
    args = parser.parse_args()
    # Run as the rendered reader's child, this interpreter renders; any other way, `read`.
    reading = (render(args.url, args.user_agent, args.timeout, args.limit) if args.reader == "rendered"
               else read(args.url, "fetch", args.user_agent, args.timeout, args.limit))
    print(json.dumps(reading.record(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
