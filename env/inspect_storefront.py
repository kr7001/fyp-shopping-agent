#!/usr/bin/env python3
"""Report how a seeded catalogue actually appears on the storefront.

The fixture says what was created. This says what a shopper, or an agent, actually
sees, and the two can differ in ways that quietly change what a task measures.

The case that prompted it: Magento paginates search at 12 results, so a 15 listing
catalogue arrives as 12 plus 3. Pagination is a second gating mechanism layered on top
of the variant gating under study. If the cheapest seller sits on page two, a task
scored as "did the agent retrieve the gated price" is really scoring "did the agent
think to paginate", and the interaction counts stop meaning what they appear to mean.

Nothing here fixes that. It reports it, so the experiment can either control for it or
state it.

    python env/inspect_storefront.py --query Rivenhall
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.parse

import requests

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_FIXTURE = HERE / "fixtures" / "scaled_water.json"

SKU_PATTERN = re.compile(r"IGR-[A-Z]+-\d+")
COUNT_PATTERN = re.compile(r'toolbar-number">(\d+)')


def fetch_page(base_url: str, query: str, page: int, timeout: int) -> str:
    url = (f"{base_url}/catalogsearch/result/?q={urllib.parse.quote(query)}"
           + (f"&p={page}" if page > 1 else ""))
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def scan(base_url: str, query: str, max_pages: int, timeout: int) -> dict:
    """Walk the result pages, recording which listing appears where.

    Stops when a page repeats the previous page's SKUs, which is how Magento responds
    to a page number past the end rather than returning an error.
    """
    pages: dict[int, list[str]] = {}
    total = None
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        html = fetch_page(base_url, query, page, timeout)
        skus = sorted(set(SKU_PATTERN.findall(html)))
        if not skus or set(skus) <= seen:
            break
        numbers = COUNT_PATTERN.findall(html)
        if total is None and len(numbers) >= 3:
            total = int(numbers[2])
        pages[page] = skus
        seen.update(skus)

    return {
        "query": query,
        "reported_total": total,
        "pages": pages,
        "per_page": len(pages.get(1, [])),
        "found": sorted(seen),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:7770")
    parser.add_argument("--query", default="Rivenhall")
    parser.add_argument("--fixture", type=pathlib.Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    result = scan(args.base_url, args.query, args.max_pages, args.timeout)
    fixture = json.loads(args.fixture.read_text()) if args.fixture.exists() else None

    print(f"query            {result['query']}")
    print(f"reported total   {result['reported_total']}")
    print(f"results per page {result['per_page']}")
    print(f"pages            {len(result['pages'])}")
    print(f"listings found   {len(result['found'])}")

    if fixture is None:
        return 0

    facts = fixture["_instance"]
    expected = {f["parent_sku"] for f in fixture["families"]}
    missing = sorted(expected - set(result["found"]))

    page_of = {sku: page for page, skus in result["pages"].items() for sku in skus}
    winner = facts["winner"]["sku"]
    card = facts["cheapest_card"]["sku"]

    print()
    print(f"seeded listings  {len(expected)}")
    print(f"not searchable   {missing if missing else 'none'}")
    print(f"winner {winner:<12} page {page_of.get(winner, 'ABSENT')}  ({facts['winner']['seller']})")
    print(f"lowest card {card:<7} page {page_of.get(card, 'ABSENT')}  ({facts['cheapest_card']['seller']})")

    beyond = [sku for sku, page in page_of.items() if page > 1]
    print(f"beyond page 1    {len(beyond)} listings {sorted(beyond)}")

    print()
    if missing:
        print("PROBLEM. Seeded listings are not returned by search. Reindex, or the "
              "task cannot be answered from the search page at all.")
    elif page_of.get(winner, 99) > 1:
        print("CAUTION. The cheapest seller is past page 1, so the task now measures "
              "pagination as well as variant retrieval. Either state that, or reseed "
              "so the winner is reachable without paging.")
    else:
        print("Winner is reachable on page 1, so a failure on the headline task is a "
              "retrieval failure rather than a pagination failure. Pagination remains "
              "a real cost for the exhaustive and per litre tasks, which need every "
              "listing, and that is worth reporting alongside the interaction counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
