#!/usr/bin/env python3
"""Build review questions whose answers are read out of the shop's own database.

Reviews are the second gating mechanism, and they gate differently from price. A price is
hidden behind one reversible click. A review is hidden behind depth: the listing serves ten
rows per page, it has no star filter and no sort control, and the only route to a complaint
is to page past everything in front of it. Measured in `notes/review-gating.md` on 13
September 2026, along with the fact that the ordering is not adversarial. Nobody buried
anything. A J shaped rating distribution meeting a ten row page cut is enough.

This generates the Type A questions from that note, the existence questions, because they
are the ones with an exact answer. "Does any buyer report this leaking" is settled by one
review saying so and is never settled by silence, so it has the same asymmetry as the
`all_stocked` refutation question and can be scored the same way.

The ground truth is a database count rather than a judgement, which is what makes these
usable. For each chosen product this records how many reviews mention the term, which page
of the listing the first mention falls on, and how many pages have to be turned to reach
it. That last number is the oracle floor for the question: an agent that answers yes after
reading fewer pages than that has not read the evidence it is citing.

Two kinds of instance are written, and the pair is the point:

  needle   the term appears, so the answer is yes and one hit settles it. The floor is the
           page the first hit sits on, which varies from 1 to 10 across the catalogue
  absent   the term never appears, so the answer is no and nothing short of every page
           establishes it. The floor is the whole listing

An agent that reads page one and answers confidently is right on a shallow needle, wrong on
a deep one, and unsound on both absent instances. That is the measurement.

    python env/generate_review_tasks.py --report
    python env/generate_review_tasks.py --out experiments/tasks/tasks_reviews.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_OUT = REPO / "experiments" / "tasks" / "tasks_reviews.json"
CONTAINER = "webarena-shopping"

# The review listing serves ten rows per page and ignores any limit parameter, so page count
# is arithmetic rather than something to discover. Verified by hand: `?limit=30` and
# `?limit=100` both still return ten.
PER_PAGE = 10

# Terms that occur rarely enough to be a needle and often enough to find instances of. Taken
# from the note's sampling rather than invented here.
# The term to match in the review text, and how to ask about it in English. Generating the
# phrasing from the term produced "does this product brokes", which is the sort of thing an
# agent could reasonably answer badly for reasons that have nothing to do with retrieval.
TERMS = {
    "leak": "leaks or arrives leaking",
    "broke": "arrives broken or breaks in use",
    "refund": "left them asking for a refund",
}

# Enough reviews that page one cannot be the whole story, which is the condition that makes
# the question gated at all.
MIN_REVIEWS = 40


def query(sql: str) -> list[list[str]]:
    """Run one read-only query inside the container and return its rows."""
    out = subprocess.run(
        ["docker", "exec", CONTAINER, "mysql", "-umagentouser", "-pMyPassword",
         "magentodb", "-N", "-B", "-e", sql],
        capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"query failed: {out.stderr.strip()[:300]}")
    return [line.split("\t") for line in out.stdout.strip().splitlines() if line]


def candidates(term: str) -> list[dict]:
    """Products where the term is a needle, with the position of its first mention.

    Position is by the listing's own order, `created_at DESC`, so the page number here is
    the page number a shopper turning pages would actually find it on.
    """
    rows = query(f"""
        SELECT x.pid, x.n, x.hits, x.first_rank, p.sku, v.value
        FROM (
          SELECT r.entity_pk_value AS pid,
                 COUNT(*) AS n,
                 SUM(d.detail LIKE '%{term}%') AS hits,
                 MIN(CASE WHEN d.detail LIKE '%{term}%' THEN rk.rank END) AS first_rank
          FROM review r
          JOIN review_detail d ON d.review_id = r.review_id
          JOIN (
            SELECT review_id, entity_pk_value,
                   ROW_NUMBER() OVER (PARTITION BY entity_pk_value
                                      ORDER BY created_at DESC, review_id DESC) AS rank
            FROM review WHERE status_id = 1
          ) rk ON rk.review_id = r.review_id
          WHERE r.status_id = 1
          GROUP BY r.entity_pk_value
          HAVING n >= {MIN_REVIEWS}
        ) x
        JOIN catalog_product_entity p ON p.entity_id = x.pid
        LEFT JOIN catalog_product_entity_varchar v
          ON v.entity_id = x.pid AND v.store_id = 0
         AND v.attribute_id = (SELECT attribute_id FROM eav_attribute
                               WHERE attribute_code = 'name' AND entity_type_id = 4)
        ORDER BY x.pid
    """)
    found = []
    for pid, n, hits, first_rank, sku, name in rows:
        hits = int(hits or 0)
        found.append({
            "product_id": int(pid),
            "sku": sku,
            "name": (name or sku).strip(),
            "reviews": int(n),
            "pages": -(-int(n) // PER_PAGE),
            "term": term,
            "mentions": hits,
            # The page a shopper reaches the first mention on, and therefore the fewest
            # pages any correct yes can have read.
            "first_page": (-(-int(first_rank) // PER_PAGE)) if first_rank not in (None, "NULL") else None,
        })
    return found


def choose(term: str, used: set[int], needles: int = 2,
           absents: int = 1) -> list[dict]:
    """A few needle instances at different depths, plus one where the term never appears.

    Depth is chosen deliberately rather than taken in catalogue order. A needle on page one
    is answerable by a glance and a needle on page eight is not, and a question set holding
    only one of those measures the market rather than the agent.
    """
    # No product is asked about twice, across terms as well as within one. Reusing a
    # product would measure the same pagination repeatedly and let one lucky page one
    # answer several questions.
    pool = [c for c in candidates(term) if c["product_id"] not in used]
    needle = [c for c in pool if 1 <= c["mentions"] <= 3 and c["first_page"]]
    absent = [c for c in pool if c["mentions"] == 0]

    shallow = [c for c in needle if c["first_page"] <= 2]
    deep = sorted((c for c in needle if c["first_page"] >= 5),
                  key=lambda c: -c["first_page"])
    picked = (shallow[:1] + deep[:needles - 1]) or needle[:needles]
    # The largest absent product, so "no" costs the most pages it can.
    picked += sorted(absent, key=lambda c: -c["reviews"])[:absents]
    used.update(c["product_id"] for c in picked)
    return picked


def task_for(item: dict) -> dict:
    """One question, with the answer and the floor the answer has to have paid for."""
    yes = item["mentions"] > 0
    listing = ("{base}/review/product/list/id/" + str(item["product_id"]) + "/")
    floor = item["first_page"] if yes else item["pages"]
    return {
        "id": f"review-{item['term']}-{item['product_id']}",
        "family": "reviews",
        "gated": True,
        "note": (
            f"{item['reviews']} reviews over {item['pages']} pages, ten per page, no star "
            f"filter and no sort. "
            + (f"{item['mentions']} mention {item['term']}, the first on page "
               f"{item['first_page']}, so a correct yes has turned at least "
               f"{floor} page{'s' if floor != 1 else ''}."
               if yes else
               f"No review mentions {item['term']}. Nothing short of all {item['pages']} "
               f"pages establishes that, so a confident no is unsound however it is "
               f"phrased.")),
        "query": (f"Go to {listing} . Do any buyers report that this product "
                  f"{TERMS[item['term']]}? Answer yes or no, and quote the review you are "
                  f"relying on if the answer is yes."),
        "expect": {"kind": "boolean", "value": yes},
        "oracle_pages": floor,
        "total_pages": item["pages"],
        "product": {"id": item["product_id"], "sku": item["sku"], "name": item["name"][:80]},
    }


def build() -> dict:
    items, used = [], set()
    for term in TERMS:
        items.extend(choose(term, used))
    tasks = [task_for(i) for i in items]
    return {
        "_about": [
            "Generated by env/generate_review_tasks.py from the shop's own review table.",
            "Do not hand edit. The answers are counts, not judgements, so they can be",
            "recomputed at any time and will not drift.",
        ],
        "_environment": [
            "WebArena's imported Amazon reviews, unmodified. Nothing here is seeded.",
            "The product page renders no review text at all, so the reviews live at their",
            "own URL and serve ten rows per page with no filter and no sort control.",
            "Ordering is created_at DESC and is not adversarial, measured 13 Sep 2026.",
        ],
        "base_url": "http://localhost:7770",
        "brand": "reviews",
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    spec = build()
    if args.report or not args.out:
        print(f"{'task':34} {'answer':7} {'pages':>6} {'floor':>6}  product")
        for task in spec["tasks"]:
            print(f"{task['id']:34} {str(task['expect']['value']):7} "
                  f"{task['total_pages']:6} {task['oracle_pages']:6}  "
                  f"{task['product']['name'][:44]}")
        print(f"\n{len(spec['tasks'])} questions")
    if args.out:
        args.out.write_text(json.dumps(spec, indent=2) + "\n")
        print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
