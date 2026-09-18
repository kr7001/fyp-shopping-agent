#!/usr/bin/env python3
"""Show the gate, side by side, in two real browser windows.

The hardest thing to convey about this project in conversation is that the price is *there*
and the agent still cannot see it. This shows it instead. Two windows open on the same
product page of the same shop. The left one is an ordinary browser. The right one reports a
user agent that makes Magento serve a theme with the variant pricing suppressed, which is
the environment the experiments now use.

Watch the size menu. On the left every option carries its surcharge, so the price of the
2 x 9.5L pack can be read without touching anything. On the right the options are bare, and
the price appears only when one is chosen. Both end on the same true price.

Costs nothing and touches no model. Takes about twenty seconds.

    python env/demo_gate.py                 # both windows, pausing so it can be narrated
    python env/demo_gate.py --headless      # no windows, prints what each side showed
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
VENV = REPO / ".venv-naive" / "bin" / "python"
PRODUCT = "http://localhost:7770/igr-cal-01.html"
ORDINARY = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
GATED = ORDINARY + " IGRGated/1.0"

SCRIPT = '''
import sys, time
from playwright.sync_api import sync_playwright

URL, ORDINARY, GATED, HEADLESS, PAUSE = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1", float(sys.argv[5])

def open_one(browser, agent, x):
    context = browser.new_context(user_agent=agent, viewport={"width": 720, "height": 850})
    page = context.new_page()
    page.goto(URL, wait_until="networkidle")
    if not HEADLESS:
        try:
            page.evaluate(f"window.moveTo({x}, 40)")
        except Exception:
            pass
    return page

def labels(page):
    return page.eval_on_selector_all(
        ".super-attribute-select option",
        "els => els.map(e => e.textContent.trim()).filter(t => t && !t.startsWith('Choose'))")

def price(page):
    return " ".join(page.inner_text(".price-box").split())

with sync_playwright() as driver:
    browser = driver.chromium.launch(headless=HEADLESS, args=["--window-size=720,850"])
    left = open_one(browser, ORDINARY, 0)
    right = open_one(browser, GATED, 740)

    print("\\n  ORDINARY BROWSER")
    print("    size menu :", labels(left))
    print("    price     :", price(left))
    print("\\n  BROWSER THE EXPERIMENTS USE")
    print("    size menu :", labels(right))
    print("    price     :", price(right))
    print("\\n  the price of the 2 x 9.5L pack is readable on the left and not on the right")
    time.sleep(PAUSE)

    for page in (left, right):
        options = page.query_selector_all(".super-attribute-select option")
        for option in options:
            if "9.5L" in (option.text_content() or ""):
                page.select_option(".super-attribute-select", option.get_attribute("value"))
                break
        page.wait_for_timeout(1200)

    print("\\n  after choosing 2 x 9.5L on both")
    print("    ordinary  :", price(left))
    print("    suppressed:", price(right))
    print("\\n  same true price. The difference is whether it could be read without asking\\n")
    time.sleep(PAUSE)
    browser.close()
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--url", default=PRODUCT)
    parser.add_argument("--pause", type=float, default=6.0,
                        help="seconds to hold each stage, so it can be talked over")
    args = parser.parse_args()

    if not VENV.exists():
        print("needs the browser environment:")
        print("  python3 -m venv .venv-naive && .venv-naive/bin/pip install playwright")
        print("  .venv-naive/bin/playwright install chromium")
        return 1

    return subprocess.run(
        [str(VENV), "-c", SCRIPT, args.url, ORDINARY, GATED,
         "1" if args.headless else "0", str(0 if args.headless else args.pause)],
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
