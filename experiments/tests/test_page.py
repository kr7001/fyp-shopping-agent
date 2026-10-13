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
import sys
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import box  # noqa: E402
import page  # noqa: E402
from test_box import market_facts  # noqa: E402

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
        sellers, prices = market_facts()
        for seller, amount, _ in CARDS:
            with self.subTest(seller=seller):
                self.assertNotIn(seller, sellers)
                self.assertNotIn(f"{float(amount):.2f}", prices)

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
        self.assertEqual(record["listings"][1],
                         {"seller": "Mellow Fields", "advertised": 12.25,
                          "url": f"{BASE}/mellow-fields-tee.html"})


def shop_answers() -> bool:
    try:
        urllib.request.urlopen(BASE, timeout=2).close()
        return True
    except OSError:
        return False


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
