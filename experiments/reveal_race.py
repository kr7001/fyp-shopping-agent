#!/usr/bin/env python3
"""Reproduce the one run the gated shop's 60 ms price reveal decided.

In cell 2, target-price run 3, openJiuwen wrote its own script that changes the size menu
to M and reads the price box in the same instant. The gated theme writes the real price
60 milliseconds after a size changes (`setTimeout(show, 60)` in
`env/gated_theme/Magento_ConfigurableProduct/templates/product/view/type/options/configurable.phtml`),
so that Magento's own widget, which redraws the price box first, cannot overwrite it. The
agent's script reads before that, and gets the price shown with no size chosen.

This runs the agent's exact script on three listings, then reads the same price box a
second later. Local shop only, no model calls, no cost.

    .venv-naive/bin/python experiments/reveal_race.py
"""

from playwright.sync_api import sync_playwright

GATED_UA = "Mozilla/5.0 IGRGated/1.0"

# Copied from the run's log, unchanged.
AGENT_SCRIPT = """() => {
  const sizeSelect = document.querySelector('[name="options[size]"]') || document.querySelector('select');
  if (sizeSelect) {
    const options = Array.from(sizeSelect.options);
    const mOption = options.find(opt => opt.text.trim() === 'M');
    if (mOption && !mOption.disabled) {
      sizeSelect.value = mOption.value;
      sizeSelect.dispatchEvent(new Event('change', { bubbles: true }));
      const priceElement = document.querySelector('[data-price-type="finalPrice"]');
      const price = priceElement ? priceElement.textContent.trim() : 'Not found';
      return { available: true, price: price };
    }
    return { available: false };
  }
  return { error: 'Size select not found' };
}"""

# Listing, seller, and its true size M price from the fixture.
LISTINGS = [("igr-app-02", "Copperfield", "29.66"),
            ("igr-app-01", "Elmsworth", "28.96"),
            ("igr-app-11", "Northwick", "32.39")]


def main() -> int:
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        context = browser.new_context(viewport={"width": 1200, "height": 701},
                                      user_agent=GATED_UA)
        print(f"{'listing':12} {'seller':12} {'script returns':>14} "
              f"{'1 second later':>14} {'true M':>8}")
        for slug, seller, true_m in LISTINGS:
            page = context.new_page()
            page.goto(f"http://localhost:7770/{slug}.html", wait_until="networkidle")
            result = page.evaluate(AGENT_SCRIPT)
            page.wait_for_timeout(1000)
            later = page.eval_on_selector('[data-price-type="finalPrice"]',
                                          "e => e.textContent.trim()")
            print(f"{slug:12} {seller:12} {result.get('price', '?'):>14} {later:>14} "
                  f"{'$' + true_m:>8}")
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
