"""The box's one look at the shop: the results page parser, on markup it must read, markup
it must refuse, and the live shop when it is up.

The page is the only input the box has besides the question, so a parser that read fewer
cards than the page holds would plan the agent over a market that is not there. Each rule
has a case where it fires and one where it stays quiet (LESSONS 24). The synthetic cards
use made-up sellers and prices, and a test checks they belong to no market the project has
generated, so a pass can never come from matching a real market by accident.
"""
import json
import pathlib
import re
import subprocess
import sys
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import box  # noqa: E402
import page  # noqa: E402
from test_box import market_listings, market_overlap  # noqa: E402

BASE = "http://localhost:7770"

# Seller, advertised price, slug. None of these is in any generated market.
CARDS = [("Harbour Lane Goods", "19.5", "harbour-lane-tee.html"),
         ("Mellow Fields", "12.25", "mellow-fields-tee.html"),
         ("Quarry Street Outfitters", "31.4", "quarry-street-tee.html")]

ONE_PAGE = '<span class="toolbar-number">3</span> Items'
# What Magento prints when the results run past one page.
PAGED = ('Items <span class="toolbar-number">1</span>-<span class="toolbar-number">3</span> of '
         '<span class="toolbar-number">40</span>')


def card(seller: str, amount: str | None, slug: str, name: str | None = None) -> str:
    """One product card in the shape Magento renders. No price block when amount is None."""
    name = name or f"Example Heavyweight Tee - {seller}"
    price = "" if amount is None else (
        '<span class="price-label">As low as</span>\n'
        f'<span id="product-price-1" data-price-amount="{amount}" data-price-type="finalPrice" '
        f'class="price-wrapper"><span class="price">${amount}</span></span>')
    return f'''
                <li class="item product product-item">
                <div class="product-item-info" data-container="product-grid">
                    <a href="{BASE}/{slug}" class="product photo product-item-photo" tabindex="-1">
                        <img class="product-image-photo" alt="{name}"/></a>
                    <div class="product details product-item-details">
                        <strong class="product name product-item-name">
                            <a class="product-item-link"
                               href="{BASE}/{slug}">
                                {name}                            </a>
                        </strong>
                        <div class="price-box price-final_price" data-role="priceBox">{price}</div>
                    </div>
                </div>
                            </li>'''


def results_page(cards: list[str], toolbar: str | None, next_link: bool = False) -> str:
    """A results page: the toolbar, the cards, a pager when asked for, and the compare
    sidebar template, which carries a product-item-link outside any card as the real page
    does (17 such anchors on the live page, 15 cards)."""
    toolbar_html = "" if toolbar is None else f'<p class="toolbar-amount" id="toolbar-amount">{toolbar}</p>'
    pager = ('<li class="item pages-item-next"><a class="action  next" href="?p=2" title="Next">'
             '<span class="label">Page</span><span>Next</span></a></li>' if next_link else "")
    sidebar = ('<ol id="compare-items" class="product-items product-items-names">'
               '<li class="product-item"><strong class="product-item-name">'
               '<a data-bind="attr: {href: product_url}, html: name" class="product-item-link"></a>'
               '</strong></li></ol>')
    return (f'<html><body>{toolbar_html}'
            f'<ol class="products list items product-items">{"".join(cards)}</ol>'
            f'<ul class="items pages-items">{pager}</ul>{sidebar}</body></html>')


class Parser(unittest.TestCase):
    def setUp(self):
        self.cards = [card(seller, amount, slug) for seller, amount, slug in CARDS]

    def test_the_synthetic_market_is_nobodys(self):
        for seller, _, slug in CARDS:
            with self.subTest(seller=seller):
                self.assertEqual(market_overlap(seller, f"{BASE}/{slug}"), [])

    def test_three_cards_parse_in_order(self):
        got = page.parse(results_page(self.cards, ONE_PAGE), "x")
        self.assertEqual([(item.seller, item.advertised, item.url) for item in got.listings],
                         [(seller, float(amount), f"{BASE}/{slug}")
                          for seller, amount, slug in CARDS])
        self.assertEqual(got.listings[0].title, "Example Heavyweight Tee - Harbour Lane Goods")
        self.assertEqual((got.total, got.next_page, got.url), (3, False, "x"))

    def test_the_sidebar_link_is_not_a_card(self):
        html = results_page(self.cards, ONE_PAGE)
        self.assertEqual(html.count('class="product-item-link"'), 4)
        self.assertEqual(len(page.parse(html, "x").listings), 3)

    def test_a_next_link_is_seen_and_the_total_is_the_last_toolbar_number(self):
        got = page.parse(results_page(self.cards, PAGED, next_link=True), "x")
        self.assertTrue(got.next_page)
        self.assertEqual((got.total, len(got.listings)), (40, 3))

    def test_a_card_without_a_price_is_refused(self):
        cards = self.cards[:2] + [card("Bramble Row", None, "bramble-row-tee.html")]
        with self.assertRaises(ValueError) as refused:
            page.parse(results_page(cards, ONE_PAGE), "x")
        self.assertIn("no price", str(refused.exception))

    def test_a_page_without_cards_is_refused(self):
        for html in (results_page([], '<span class="toolbar-number">0</span> Items'),
                     "<html><body><h1>Whoops, our bad...</h1></body></html>"):
            with self.subTest(html=html[:40]):
                with self.assertRaises(ValueError):
                    page.parse(html, "x")

    def test_a_toolbar_count_the_cards_do_not_add_up_to_is_refused(self):
        with self.assertRaises(ValueError):
            page.parse(results_page(self.cards, '<span class="toolbar-number">4</span> Items'), "x")
        # The same count with a next page is what a paged first page looks like, so it stands.
        got = page.parse(results_page(self.cards, '<span class="toolbar-number">4</span> Items',
                                      next_link=True), "x")
        self.assertEqual((got.total, len(got.listings)), (4, 3))

    def test_a_page_without_a_toolbar_has_no_total(self):
        got = page.parse(results_page(self.cards, None), "x")
        self.assertEqual((got.total, len(got.listings)), (None, 3))

    def test_the_seller_is_the_name_after_the_last_dash(self):
        cards = [card("", "22.1", "a.html", name="Plain Tee - Blue - Saltmarsh Trading"),
                 card("", "13.75", "b.html", name="Plain Tee Without A Seller"),
                 card("", "40.0", "c.html", name="Plain Tee - Kettle &amp; Hill Supply")]
        got = page.parse(results_page(cards, ONE_PAGE), "x")
        self.assertEqual([item.seller for item in got.listings],
                         ["Saltmarsh Trading", "Plain Tee Without A Seller", "Kettle & Hill Supply"])

    def test_by_price_sorts_by_price_then_seller(self):
        cards = [card("Kettle Hill Supply", "12.25", "kettle-hill-tee.html")] + self.cards
        got = page.parse(results_page(cards, '<span class="toolbar-number">4</span> Items'), "x")
        self.assertEqual([item.seller for item in got.by_price()],
                         ["Kettle Hill Supply", "Mellow Fields", "Harbour Lane Goods",
                          "Quarry Street Outfitters"])
        # The page itself keeps the order shown.
        self.assertEqual(got.listings[0].seller, "Kettle Hill Supply")
        self.assertEqual(got.listings[1].seller, "Harbour Lane Goods")

    def test_the_record_holds_what_the_verifier_checks(self):
        record = page.parse(results_page(self.cards, ONE_PAGE), "x").record()
        self.assertEqual((record["url"], record["count"], record["total"], record["next_page"]),
                         ("x", 3, 3, False))
        # The title too since 22 October 2026, so the model parser's title normalisation
        # can be replayed from a run record; a record from before keeps none and reads
        # back with none (`page.from_record`).
        self.assertEqual(record["listings"][1],
                         {"seller": "Mellow Fields", "advertised": 12.25,
                          "url": f"{BASE}/mellow-fields-tee.html",
                          "title": "Example Heavyweight Tee - Mellow Fields"})
        back = page.from_record(record)
        self.assertEqual((back.record(), back.listings[1].title), (record, "Example Heavyweight Tee - Mellow Fields"))
        old = {**record, "listings": [{k: v for k, v in item.items() if k != "title"} for item in record["listings"]]}
        self.assertEqual([item.title for item in page.from_record(old).listings], [None, None, None])


def shop_answers() -> bool:
    try:
        urllib.request.urlopen(BASE, timeout=2).close()
        return True
    except OSError:
        return False


# A second page's cards, made up too (`EveryPage.test_the_later_sellers_are_nobodys`).
LATER = [("Bramble Row Traders", "27.6", "bramble-row-tee.html"),
         ("Kettle Hill Supply", "14.85", "kettle-hill-tee.html")]
FIRST_URL = f"{BASE}/catalogsearch/result/?q=Example"
SECOND_URL = f"{BASE}/catalogsearch/result/index/?p=2&q=Example"


def paged(cards: list[str], first: int, last: int, total: int, next_href: str | None) -> str:
    """One page of a search of several, in Magento's shape: "Items 1-3 of 5", the cards and
    the pager's next link, whose address the HTML escapes, as the live shop's does."""
    toolbar = (f'Items <span class="toolbar-number">{first}</span>-<span class="toolbar-number">{last}'
               f'</span> of <span class="toolbar-number">{total}</span>')
    html = results_page(cards, toolbar)
    if next_href is None:
        return html
    pager = (f'<li class="item pages-item-next"><a class="action  next"\n   href="{next_href}"\n'
             f'   title="Next"><span class="label">Page</span><span>Next</span></a></li>')
    return html.replace('<ul class="items pages-items">', f'<ul class="items pages-items">{pager}')


def two_pages() -> dict[str, str]:
    """A search of 5 listings on two pages, by address."""
    one = [card(seller, amount, slug) for seller, amount, slug in CARDS]
    two = [card(seller, amount, slug) for seller, amount, slug in LATER]
    return {FIRST_URL: paged(one, 1, 3, 5, SECOND_URL.replace("&", "&amp;")),
            SECOND_URL: paged(two, 4, 5, 5, None)}


class EveryPage(unittest.TestCase):
    """Box v16 (22 October 2026): the box reads every results page of the search, following
    the pager's next link, by either reader, and holds each page to its own toolbar."""

    def test_the_later_sellers_are_nobodys(self):
        # By what a market's listing is, its seller, its address or its SKU, never by a price,
        # which two markets can share by chance (LESSONS 2): on 22 October 2026 the Larchmere
        # fixture gave a variant 14.85, the price of a made-up seller here.
        for seller, _, slug in LATER:
            with self.subTest(seller=seller):
                self.assertEqual(market_overlap(seller, f"{BASE}/{slug}"), [])
        # Fires on a market's own listing, by its seller, its address or its SKU.
        market = market_listings()
        seller, url = sorted(market["sellers"])[0], sorted(market["urls"])[0]
        self.assertEqual(market_overlap(seller, f"{BASE}/nobody.html"), [f"seller {seller!r}"])
        self.assertEqual(market_overlap("Nobody", url), [f"listing {url}"])
        self.assertEqual(market_overlap("Nobody", url.upper().replace("HTTP://LOCALHOST:7770", BASE)),
                         [f"listing {url.upper().replace('HTTP://LOCALHOST:7770', BASE)}"])

    def test_the_pages_are_read_to_the_end_as_one_search(self):
        site = two_pages()
        got = page.follow(FIRST_URL, site.__getitem__, "fetch")
        self.assertEqual([item.seller for item in got.listings],
                         [seller for seller, _, _ in CARDS + LATER])
        self.assertEqual((got.url, got.total, got.next_page, got.pages, got.reader),
                         (FIRST_URL, 5, False, (FIRST_URL, SECOND_URL), "fetch"))
        record = got.record()
        self.assertEqual((record["count"], record["pages"], record["reader"]), (5, [FIRST_URL, SECOND_URL], "fetch"))
        self.assertEqual(page.from_record(record), got)
        # The fetch reader is the same walk over HTTP.
        with mock.patch.object(page, "http_html", lambda url, user_agent, timeout: site[url]):
            self.assertEqual(page.read(FIRST_URL, "fetch"), got)

    def test_a_read_past_its_limit_records_the_page_it_left(self):
        got = page.follow(FIRST_URL, two_pages().__getitem__, "fetch", limit=1)
        self.assertEqual((len(got.listings), got.next_page, got.pages), (3, True, (FIRST_URL,)))

    def test_the_next_link_is_unescaped_and_made_whole(self):
        site = two_pages()
        self.assertEqual(page.next_url(site[FIRST_URL], FIRST_URL), SECOND_URL)
        self.assertIsNone(page.next_url(site[SECOND_URL], SECOND_URL))
        relative = results_page([card(*CARDS[0])], ONE_PAGE, next_link=True)
        self.assertEqual(page.next_url(relative, FIRST_URL), f"{BASE}/catalogsearch/result/?p=2")

    def test_each_page_is_held_to_its_own_toolbar(self):
        site = two_pages()
        # A later page whose range its cards do not fill.
        short = dict(site, **{SECOND_URL: paged([card(*LATER[0])], 4, 5, 5, None)})
        with self.assertRaisesRegex(ValueError, "shows items 4-5 but 1 cards were read"):
            page.follow(FIRST_URL, short.__getitem__, "fetch")
        # A later page that does not start where the last stopped.
        skipped = dict(site, **{SECOND_URL: paged([card(*c) for c in LATER], 5, 6, 6, None)})
        with self.assertRaisesRegex(ValueError, "starts at item 5, after 3 were read"):
            page.follow(FIRST_URL, skipped.__getitem__, "fetch")
        # Pages read to the end that do not add up to the total.
        counted = dict(site, **{FIRST_URL: site[FIRST_URL].replace(
            '<span class="toolbar-number">5</span>', '<span class="toolbar-number">6</span>')})
        with self.assertRaisesRegex(ValueError, "counts 6 items but 5 cards were read on 2 pages"):
            page.follow(FIRST_URL, counted.__getitem__, "fetch")
        # A pager that leads back.
        loop = dict(site, **{SECOND_URL: paged([card(*c) for c in LATER], 4, 5, 9, FIRST_URL)})
        with self.assertRaisesRegex(ValueError, "leads back to"):
            page.follow(FIRST_URL, loop.__getitem__, "fetch", limit=5)
        # Quiet: one page, "3 Items", read as it always was.
        one = page.follow(FIRST_URL, lambda url: results_page([card(*c) for c in CARDS], ONE_PAGE), "fetch")
        self.assertEqual((len(one.listings), one.total, one.next_page, one.pages), (3, 3, False, (FIRST_URL,)))

    def test_an_older_record_reads_back_as_one_page_and_no_reader(self):
        record = page.parse(results_page([card(*c) for c in CARDS], ONE_PAGE), "x").record()
        old = {key: value for key, value in record.items() if key not in ("pages", "reader")}
        back = page.from_record(old)
        self.assertEqual((back.pages, back.reader, back.record()["pages"]), (("x",), None, ["x"]))

    def test_a_reader_it_does_not_have_and_a_missing_venv_are_refused(self):
        with self.assertRaisesRegex(ValueError, "no reader 'browser'"):
            page.read(FIRST_URL, "browser")
        with mock.patch.object(page.paths, "NAIVE_PYTHON", pathlib.Path("/nowhere/python")), \
                self.assertRaisesRegex(RuntimeError, "read with the fetch reader instead"):
            page.read(FIRST_URL, "rendered")

    def test_the_rendered_reader_runs_in_the_venv_and_comes_back_as_its_record(self):
        got = page.follow(FIRST_URL, two_pages().__getitem__, "rendered")
        ran = []

        def child(command, capture_output, text, timeout):
            ran.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(got.record()), stderr="")

        with mock.patch.object(page.subprocess, "run", child):
            self.assertEqual(page.read(FIRST_URL, "rendered"), got)
        self.assertEqual(ran[0][:3], [str(paths.NAIVE_PYTHON), str(pathlib.Path(page.__file__).resolve()), FIRST_URL])
        self.assertEqual(ran[0][3:5], ["--reader", "rendered"])
        self.assertIn(page.GATED_UA, ran[0])

        def failing(command, capture_output, text, timeout):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="Traceback\nValueError: no product cards on x")

        with mock.patch.object(page.subprocess, "run", failing), \
                self.assertRaisesRegex(ValueError, "the rendered reader failed on .*: ValueError: no product cards on x"):
            page.read(FIRST_URL, "rendered")


class FakeTab:
    """A browser tab with a site behind it, which keeps every call made of it. It has only
    what `page.render_pages` may ask for; anything else, such as running a script in the page
    or querying it for an element, is an AttributeError."""

    def __init__(self, site: dict[str, str]):
        self.site, self.calls, self.at = site, [], None

    def goto(self, url, wait_until=None, timeout=None):
        self.calls.append(("goto", url))
        self.at = url

    def wait_for_selector(self, selector, timeout=None):
        self.calls.append(("wait_for_selector", selector))
        if page.CARD.search(self.site[self.at]) is None:
            raise TimeoutError(f'waiting for locator("{selector}") to be visible')

    def content(self):
        self.calls.append(("content", self.at))
        return self.site[self.at]


class NeverTheStore(unittest.TestCase):
    """The gated theme's encoded variant store (`data-igr`, `igr-variant-store`) holds every
    variant's price. The reader reads card fields and nothing else."""

    def store(self, decoy: str) -> str:
        return (f'<div id="igr-variant-store" data-igr="eyJ4IjogMX0=" hidden="hidden">{decoy}</div>')

    def test_a_store_in_a_card_is_never_read(self):
        # The store placed in the first card, ahead of its price, with a price of its own
        # and a card inside it. Read, the first listing's price is the store's 0.01, and
        # the card ends at the store's own. Planted: `parse` without `STORE.sub`, it was.
        decoy = ('<span data-price-amount="0.01"></span><li class="item product product-item">'
                 '<a class="product-item-link" href="http://localhost:7770/decoy.html">Decoy - Nobody</a>'
                 '<span data-price-amount="0.02"></span></li>')
        plain = [card(*c) for c in CARDS]
        stored = [plain[0].replace('<div class="price-box', self.store(decoy) + '<div class="price-box', 1)] + plain[1:]
        self.assertIn("igr-variant-store", stored[0])
        with_store = page.parse(results_page(stored, ONE_PAGE), "x")
        self.assertEqual(with_store, page.parse(results_page(plain, ONE_PAGE), "x"))
        self.assertEqual([item.advertised for item in with_store.listings], [19.5, 12.25, 31.4])
        # A data-igr attribute anywhere is gone too, the next link's included.
        attributed = results_page([plain[0].replace('class="price-box', 'data-igr="AAAA" class="price-box', 1)]
                                  + plain[1:], ONE_PAGE)
        self.assertNotIn("data-igr", page.STORE.sub("", attributed))

    def test_the_browser_is_asked_for_the_results_pages_and_nothing_else(self):
        # Every call made of the tab: the two results pages, a card waited for on each, the
        # DOM read. No listing visited, nothing run in the page, no element queried, and
        # nothing that names the store. Planted: `render_pages` reading the store with
        # `tab.evaluate`, it raised here.
        site = two_pages()
        site = {url: html.replace("</body>", self.store("") + "</body>") for url, html in site.items()}
        tab = FakeTab(site)
        got = page.render_pages(tab, FIRST_URL)
        self.assertEqual(tab.calls, [("goto", FIRST_URL), ("wait_for_selector", page.CARD_SELECTOR),
                                     ("content", FIRST_URL), ("goto", SECOND_URL),
                                     ("wait_for_selector", page.CARD_SELECTOR), ("content", SECOND_URL)])
        for call in tab.calls:
            self.assertFalse(any(word in str(call) for word in ("data-igr", "igr-variant-store")))
        self.assertEqual((len(got.listings), got.reader, got.pages), (5, "rendered", (FIRST_URL, SECOND_URL)))
        self.assertEqual(got.listings, page.follow(FIRST_URL, two_pages().__getitem__, "fetch").listings)
        # A page where no card appears is refused in the fetch reader's words.
        empty = FakeTab({FIRST_URL: "<html><body><p>Your search returned no results.</p></body></html>"})
        with self.assertRaisesRegex(ValueError, re.escape(f"no product cards on {FIRST_URL} within 20 s")):
            page.render_pages(empty, FIRST_URL)


def shop_and_browser() -> str | None:
    """Why the live readers cannot be compared here, or None when they can: the shop's
    results page answers, and the Playwright venv the rendered reader runs in is there."""
    if not paths.NAIVE_PYTHON.exists():
        return f"the Playwright venv is not at {paths.NAIVE_PYTHON}"
    try:
        urllib.request.urlopen(f"{BASE}/catalogsearch/result/?q=Thornwood", timeout=10).close()
    except OSError:
        return "the local shop did not answer within 10 s"
    return None


@unittest.skipIf(shop_and_browser(), shop_and_browser() or "")
class LiveReaders(unittest.TestCase):
    """The rendered reader against the fetch on the live shop (22 October 2026): the same
    listings, prices, URLs and titles, count, total, pager and pages, on the two clothing
    markets, and on two pages of a search that runs to many. Free: no model is called."""

    def same(self, url: str, limit: int = page.MAX_PAGES) -> tuple[page.Page, page.Page]:
        rendered, fetched = page.read(url, "rendered", limit=limit), page.read(url, "fetch", limit=limit)
        self.assertEqual((rendered.reader, fetched.reader), ("rendered", "fetch"))
        self.assertEqual([(i.seller, i.title, i.url, i.advertised) for i in rendered.listings],
                         [(i.seller, i.title, i.url, i.advertised) for i in fetched.listings])
        self.assertEqual((len(rendered.listings), rendered.total, rendered.next_page, rendered.pages),
                         (len(fetched.listings), fetched.total, fetched.next_page, fetched.pages))
        return rendered, fetched

    def test_thornwood_and_ashcombe_read_the_same_both_ways(self):
        for brand in ("Thornwood", "Ashcombe"):
            with self.subTest(brand=brand):
                url = f"{BASE}/catalogsearch/result/?q={brand}"
                rendered, _ = self.same(url)
                self.assertEqual((len(rendered.listings), rendered.total, rendered.next_page, rendered.pages),
                                 (15, 15, False, (url,)))
                # No results page holds the store, as fetched.
                html = page.http_html(url)
                self.assertFalse(any(word in html for word in ("data-igr", "igr-variant-store")))

    def test_two_pages_of_a_search_that_runs_to_many(self):
        url = f"{BASE}/catalogsearch/result/?q=jacket"
        rendered, _ = self.same(url, limit=2)
        self.assertEqual((len(rendered.listings), rendered.next_page, len(rendered.pages)), (72, True, 2))
        self.assertEqual(rendered.pages[1], f"{BASE}/catalogsearch/result/index/?p=2&q=jacket")


@unittest.skipUnless(shop_answers(), "the local shop did not answer within 2 s")
class LiveShop(unittest.TestCase):
    def test_the_clothing_results_page_reads_whole(self):
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        url = box.results_url(spec["tasks"][0]["query"].format(base=spec["base_url"]))
        got = page.fetch(url)
        # The market's size, 15 today. Read from the task file so a regenerated market
        # moves the test with it.
        self.assertEqual(len(got.listings), spec["_instance"]["listings"])
        self.assertEqual(got.total, len(got.listings))
        self.assertFalse(got.next_page)
        self.assertEqual(len({item.seller for item in got.listings}), len(got.listings))
        self.assertTrue(all(item.advertised > 0 for item in got.listings))
        self.assertTrue(all(item.url.startswith(spec["base_url"]) for item in got.listings))


if __name__ == "__main__":
    unittest.main()
