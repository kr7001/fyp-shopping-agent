#!/usr/bin/env python3
"""Read the first results page: how many listings there are, each seller, its advertised
price and URL, and whether there is a next page.

This is the box's one look at the shop before the agent starts, and the only module in
`box/` that does I/O. It fetches one page over HTTP with the same user agent the agent's
browser uses, because `env/install_gated_theme.py` picks the price-suppressing theme by
that header, and parses it without a browser, because Magento renders the cards on the
server. Checked on 14 October 2026 against the gated Thornwood results page: 15
`<li class="item product product-item">` blocks, each with one `product-item-link` and one
`data-price-amount` labelled "As low as", a toolbar count of 15 and no pager, and the
agent's own whole-page card probe returns the same 15 prices in the same order. A shop that
draws its cards with JavaScript would need a browser fetch instead, which is a stated limit.

It reads HTTP and nothing else: never a task file, an answer key or a generated catalogue.

    python experiments/box/page.py "http://localhost:7770/catalogsearch/result/?q=Thornwood"
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import urllib.request
from html import unescape

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
# later page exists. Read off a paged search of the local shop on 14 October 2026.
NEXT = re.compile(r'class="action\s+next"')


@dataclasses.dataclass(frozen=True)
class Listing:
    seller: str
    title: str | None   # None only for a listing read back from a record that kept no title
    url: str
    advertised: float   # the price the card shows, the cheapest option the listing has


@dataclasses.dataclass(frozen=True)
class Page:
    url: str
    listings: list[Listing]     # in the order the page shows them
    total: int | None           # the toolbar's count, None when the page prints none
    next_page: bool

    def record(self) -> dict:
        """What the box read, for the run record, so the verifier can check it against
        the live shop. Each listing's title since 22 October 2026, so the model parser's
        title normalisation can be replayed from the record; null in a page read back from
        an older record, which kept none."""
        return {"url": self.url, "count": len(self.listings), "total": self.total,
                "next_page": self.next_page,
                "listings": [{"seller": item.seller, "advertised": item.advertised,
                              "url": item.url, "title": item.title} for item in self.listings]}

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
                next_page=bool(data.get("next_page")))


def parse(html: str, url: str) -> Page:
    """The page's listings in the order shown, the toolbar total and the pager state.

    Raises ValueError rather than returning less than the page holds. A page with no cards,
    a card with no price, or a toolbar count the cards do not add up to would otherwise
    have the agent planned over a market that is not there.
    """
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
    toolbar = TOOLBAR.search(html)
    numbers = TOOLBAR_NUMBER.findall(toolbar.group(1)) if toolbar else []
    total = int(numbers[-1].replace(",", "")) if numbers else None
    next_page = bool(NEXT.search(html))
    if total is not None and not next_page and total != len(listings):
        raise ValueError(f"the toolbar on {url} counts {total} items but {len(listings)} "
                         f"cards were read")
    return Page(url=url, listings=listings, total=total, next_page=next_page)


def fetch(url: str, user_agent: str = GATED_UA, timeout: int = 20) -> Page:
    """One HTTP request for the results page, as the agent's browser would make it."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    return parse(html, url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="the results page to read")
    args = parser.parse_args()
    print(json.dumps(fetch(args.url).record(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
