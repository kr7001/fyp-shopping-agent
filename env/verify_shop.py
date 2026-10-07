#!/usr/bin/env python3
"""Check the shop is in the state an experiment assumes, before any money is spent.

Written on 7 Oct 2026 after a two week break, during which the machine restarted. Every
check below has failed at least once in this project's history, and each failure wasted
either a batch of paid runs or an afternoon:

  the container stops                  nothing runs
  Elasticsearch reports healthy and    the catalogue looks almost empty and search returns
    is not                               nothing, silently
  the search index goes stale          seeded products exist and do not appear in results
  the suppressing theme is missing     prices leak and the runs measure the wrong shop
  the page size resets                 only 12 of 15 listings render, which changes the
                                         thing being measured

    python env/verify_shop.py
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
CONTAINER = "webarena-shopping"
BASE = "http://localhost:7770"
GATED_UA = "Mozilla/5.0 IGRGated/1.0"

PASS, FAIL, SKIP = "pass", "FAIL", "skip"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str) -> bool:
    results.append((PASS if ok else (SKIP if ok is None else FAIL), name, detail))
    return bool(ok)


def fetch(path: str, ua: str | None = None, timeout: int = 20) -> str | None:
    request = urllib.request.Request(BASE + path)
    if ua:
        request.add_header("User-Agent", ua)
    try:
        return urllib.request.urlopen(request, timeout=timeout).read().decode(errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def docker(*args: str) -> tuple[int, str]:
    out = subprocess.run(["docker", *args], capture_output=True, text=True)
    return out.returncode, (out.stdout or out.stderr).strip()


def main() -> int:
    code, _ = docker("info")
    if code:
        record("docker engine running", False, "docker info failed, start Docker Desktop")
        report()
        return 1
    record("docker engine running", True, "")

    code, out = docker("ps", "--filter", f"name={CONTAINER}", "--format", "{{.Status}}")
    if code or not out:
        record("shop container running", False,
               f"not running. Start it with: docker start {CONTAINER}")
        report()
        return 1
    record("shop container running", True, out)

    home = fetch("/")
    if home is None:
        record("storefront answers", False, f"no response from {BASE}")
        report()
        return 1
    record("storefront answers", True, f"{len(home):,} bytes")

    # Elasticsearch is the one that fails silently, so ask the shop rather than the daemon.
    code, out = docker("exec", CONTAINER, "curl", "-s", "-m", "5",
                       "http://localhost:9200/_cluster/health")
    status = ""
    if not code and out.strip().startswith("{"):
        try:
            status = json.loads(out).get("status", "")
        except json.JSONDecodeError:
            status = ""
    record("search engine healthy", status in {"green", "yellow"},
           f"cluster status {status or 'unreadable'}")

    # Every market this project can run, checked by asking the shop for it.
    fixtures = {
        "Rivenhall": "scaled_water.json",
        "Calderwood": "heldout_calderwood.json",
        "Thornwood": "scaled_apparel.json",
    }
    for brand, fixture in fixtures.items():
        path = REPO / "env" / "fixtures" / fixture
        if not path.exists():
            record(f"market {brand}", None, "fixture file missing")
            continue
        want = len(json.loads(path.read_text())["families"])
        page = fetch(f"/catalogsearch/result/?q={brand}")
        if page is None:
            record(f"market {brand}", False, "search page did not answer")
            continue
        shown = re.search(r"Items\s+(\d+)-(\d+) of (\d+)", page)
        found = len(set(re.findall(rf"{brand}[^<]*? - ([A-Za-z][A-Za-z ]+?)\s*<", page)))
        total = int(shown.group(3)) if shown else found
        detail = f"{found} sellers rendered, shop reports {total}, fixture has {want}"
        record(f"market {brand}", found == want and total == want, detail)

    # All fifteen on one page, which is what makes "the agent read four" a clean claim.
    # Magento prints "Items 1-12 of 15" when it paginates and a bare "15 Items" when it
    # does not, so the absence of a range is the thing to look for. An earlier version of
    # this check looked for "Items 1-15 of 15", a string the shop never produces, and
    # reported a healthy shop as broken.
    page = fetch("/catalogsearch/result/?q=Thornwood") or ""
    ranged = re.search(r"Items\s*<[^>]*>\s*\d+\s*</[^>]*>\s*-", page)
    # Count inside the results grid only. Counting every `product-item-info` in the page
    # gives 16, because Magento also ships an empty Knockout template for the wishlist
    # sidebar that uses the same class. It is hidden and holds no product, but a count that
    # includes it is a count that will be wrong by one in some future table.
    grid = page[page.find('class="products list items product-items"'):]
    grid = grid[:grid.find("</ol>")] if "</ol>" in grid else grid
    cards = len(re.findall(r'class="[^"]*product-item-info', grid))
    record("all 15 render on one page", not ranged and cards == 15,
           f"{cards} cards in the results grid, pager {'present' if ranged else 'absent'}")

    # The suppressing theme. This has to be done in a real browser: the surcharge labels
    # are written into the menu by the page's own JavaScript, so fetching the HTML can
    # never see them. The first version of this check used a plain fetch, found nothing in
    # either shop, and called a working theme broken.
    record(*theme_check())

    report()
    return 0 if all(r[0] != FAIL for r in results) else 1


def theme_check() -> tuple[str, bool | None, str]:
    """Open one product page twice in a real browser and compare the size menu."""
    script = REPO / "env" / "_theme_probe.py"
    venv = REPO / ".venv-naive" / "bin" / "python"
    if not venv.exists():
        return ("gated theme serving", None, "no browser environment, skipped")
    out = subprocess.run([str(venv), str(script)], capture_output=True, text=True,
                         cwd=str(REPO))
    if out.returncode or not out.stdout.strip():
        return ("gated theme serving", False,
                (out.stderr or out.stdout).strip().splitlines()[-1][:120] if (out.stderr or out.stdout) else "probe failed")
    try:
        data = json.loads(out.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return ("gated theme serving", False, "probe output unreadable")
    leaks, sealed = data["plain"], data["gated"]
    ok = leaks > 0 and sealed == 0
    return ("gated theme serving", ok,
            f"ordinary menu shows {leaks} surcharges, gated shows {sealed}")


def report() -> None:
    print()
    width = max(len(name) for _, name, _ in results) + 2
    for state, name, detail in results:
        print(f"  [{state:4}] {name:{width}} {detail}")
    bad = [r for r in results if r[0] == FAIL]
    print()
    print(f"{len(results)} checks, {len(bad)} failed")
    if bad:
        print("The shop is not ready. Fix the failures above before spending anything.")


if __name__ == "__main__":
    sys.exit(main())
