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
    page = fetch("/catalogsearch/result/?q=Thornwood") or ""
    one_page = bool(re.search(r"Items\s+1-15 of 15", page))
    record("all 15 render on one page", one_page,
           "page size is 36" if one_page else "page size may have reset to 12")

    # The suppressing theme, asked for the way a run asks for it.
    product = "/igr-app-07.html"
    plain = fetch(product) or ""
    gated = fetch(product, ua=GATED_UA) or ""
    if not plain or not gated:
        record("gated theme serving", False, "product page did not answer")
    else:
        leak = re.findall(r"\+\$\d+\.\d\d", plain)
        sealed = re.findall(r"\+\$\d+\.\d\d", gated)
        # The ordinary shop should leak and the gated one should not. If neither leaks the
        # theme cannot be told apart from a broken page, so that is a failure too.
        record("ordinary shop still leaks, as expected", bool(leak),
               f"{len(leak)} surcharge labels in the plain page")
        record("gated shop hides the surcharge", bool(leak) and not sealed,
               f"{len(sealed)} surcharge labels under {GATED_UA}")

    report()
    return 0 if all(r[0] != FAIL for r in results) else 1


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
