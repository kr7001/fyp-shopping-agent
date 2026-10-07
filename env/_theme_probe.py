#!/usr/bin/env python3
"""Open one product page as an ordinary browser and as the gated one, and count surcharges.

Separate from verify_shop.py because it needs Playwright, which lives in its own
environment. Prints one line of JSON so the caller does not have to parse prose.
"""
import json
from playwright.sync_api import sync_playwright

URL = "http://localhost:7770/igr-app-07.html"
GATED = "Mozilla/5.0 IGRGated/1.0"


def menu(page):
    return page.eval_on_selector_all(
        ".super-attribute-select option",
        "els => els.map(e => e.textContent.trim())")


with sync_playwright() as p:
    browser = p.chromium.launch()
    out = {}
    for label, ua in (("plain", None), ("gated", GATED)):
        ctx = browser.new_context(viewport={"width": 1200, "height": 701},
                                  **({"user_agent": ua} if ua else {}))
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1500)
        options = menu(page)
        out[label] = sum(1 for o in options if "+$" in o or "-$" in o)
        out[label + "_options"] = options
        ctx.close()
    browser.close()
    print(json.dumps(out))
