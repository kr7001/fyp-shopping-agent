#!/usr/bin/env python3
"""The order the shop's search lists one brand's listings in, predicted from their names and
options alone.

A generated market is only a trap if the results page is the right way round, and until now
that could only be learned by seeding a draw and reading the page (`pick_apparel_market.py`,
about five minutes a seed). The A+ market (docs/content/claim2-protocol.md) has rules on
where its answers render across two pages and two products, so a seed search by reading the
page would take hours. This predicts the page instead, so the generator can reject a draw
before it is seeded. The live page is still checked after seeding, every time
(`pick_aplus_market.py`, `check_aplus_market.py`), and a page that differs from the
prediction stops the search rather than being accepted.

**How the shop orders a brand's search**, read off the running shop on 22 October 2026
(Magento 2.4.6, Elasticsearch 7, index magento2_product_1_v41, 104,432 documents):

- The quick search, as Magento's own mapper builds it (`Magento\\Elasticsearch7\\SearchAdapter\\
  Mapper` on `quick_search_container`, printed from inside the container): the catch-all
  `_search` field twice, every searchable attribute at its weight (sku 6, name 5, the rest 1,
  as `catalog_eav_attribute.search_weight` holds them), and a phrase prefix on `name` read
  with Magento's `prefix_search` analyzer, each boost one more than its weight, under a
  visibility filter that adds 1 to every listing. A brand word appears only in `name` and
  `_search`, so for a word whose stem is itself Lucene merges the clauses into `name` at
  6 + 2 = 8 and `_search` at 2 + 2 = 4. For a word whose stem differs (Rivenhall, Ashcombe,
  Larchmere), `name` and `_search` become synonym queries that count the word and its stem
  together, and the phrase prefix, which its analyzer leaves unstemmed, stays one term
  clause at 2. (22 October 2026: the first version of this model split the phrase prefix
  into both forms, as the query does without Magento's analyzer, and was checked against
  that query rather than Magento's. The development market's first seed rendered in an order
  it did not predict, in four places, and Magento's own request showed the analyzer.)
- A configurable listing's `name` field holds its own name and every child's ("... - M"), so
  the brand occurs once per name, one more than its options, and the field grows with every
  option. `_search` holds the same names, the parent's SKU twice, each child's SKU, and three
  status words ("enabled", "taxable goods"). Read with the term-vectors API.
- BM25 with k1 1.2 and b 0.75 against the index's average field lengths, a field's length
  kept in one byte (exact below 24, four significant bits above), and a stem that shares its
  word's position not counted.
- Equal scores keep catalogue order.

**Checked** on the four stored markets (Thornwood, Ashcombe, Rivenhall, Calderwood) and the
A+ development market: `--validate` scores each through Elasticsearch with Magento's own
query, prints the largest gap from this model with the index's averages as they stand, and
whether the order this model gives with its constants equals the live results pages. On
22 October 2026, with the development market seeded, every gap was below 0.0001 and every
order equal. The two water markets were seeded before 13 September 2026 with their authoring
note as description, which the index still holds, so their note's words are added there.
`tests/test_aplus_market.py` checks the order offline against the page records two batches
stored.

**What it cannot see.** The index's average lengths move a little when products are added,
so `SCENARIOS` lets the generator require its page rules under 2 per cent either way, and
under either reading of the brand, so the market does not depend on the model's last
decimal. Any other change to the shop's search, a new searchable attribute or a synonym
list, would need the model measured again; the live check is what would show it.

    python3 env/search_order.py --fixture env/fixtures/aplus_dev.json
    python3 env/search_order.py --validate      # against the live index, read only
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import subprocess
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent

# Bumped whenever the order it predicts would change, since the A+ generator accepts or
# rejects a draw by it. Recorded in every A+ fixture's `_generated`.
#   1  22 October 2026, with the phrase prefix of a two-form brand as one term (the module
#      docstring). Since 24 October 2026 a variant's menu label is counted in its child's
#      name where a fixture gives one (`menu_label`, `lengths`), for the tee-only market
#      (generate_aplus.py version 4). No market before it had a label, so no order predicted
#      for any earlier market changes, and the version stays
VERSION = 1

K1, B = 1.2, 0.75
# The index's average field lengths, from the explain output on 22 October 2026.
AVGDL_NAME = 23.627682
AVGDL_SEARCH = 1468.8053
# "enabled" and "taxable goods": every listing's status and tax class, in `_search`.
STATUS_WORDS = 3
# A word as the standard tokenizer cuts it: letters and digits, a decimal kept whole with
# any unit after it ("9.5L"), punctuation and the dash dropped, no stopwords removed.
WORD = re.compile(r"[A-Za-z0-9]+(?:\.[0-9]+[A-Za-z]*)?")
# The cases the generator's page rules must hold under: the brand read as one form or two,
# and both average lengths 2 per cent either way.
SCENARIOS = tuple((two_forms, scale) for two_forms in (False, True)
                  for scale in (1.0, 0.98, 1.02))


def _long_to_int4(i: int) -> int:
    bits = i.bit_length()
    if bits < 4:
        return i
    shift = bits - 4
    return ((i >> shift) & 0x07) | ((shift + 1) << 3)


def _int4_to_long(i: int) -> int:
    bits, shift = i & 0x07, (i >> 3) - 1
    return bits if shift == -1 else (bits | 0x08) << shift


# Lucene 8's SmallFloat.intToByte4: lengths below this are kept exactly.
_EXACT_BELOW = 255 - _long_to_int4(2 ** 31 - 1)


def stored_length(length: int) -> int:
    """A field's length as BM25 reads it back from its one-byte norm."""
    if length < _EXACT_BELOW:
        return length
    return _EXACT_BELOW + _int4_to_long(_long_to_int4(length - _EXACT_BELOW))


def words(text: str) -> int:
    return len(WORD.findall(text))


def child_sku(family: dict, variant: dict) -> str:
    """The SKU `seed_variants.expand_skus` gives a child."""
    option = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", variant["option"].lower())).strip("-")
    return variant.get("sku") or f"{family['parent_sku']}-{option.upper()}"


def menu_label(variant: dict) -> str:
    """What the size menu shows for a variant, and so what the seeder puts in its child's
    name: its `label` where the fixture gives one ("XS - Promo $9.99", the tee-only market
    of 24 October 2026, `generate_aplus.add_labels`), else its plain option."""
    return variant.get("label") or variant["option"]


def lengths(family: dict, description_words: int = 0) -> tuple[int, int, int]:
    """(how often the brand occurs, the `name` length, the `_search` length) of one listing
    as the index holds it. A child's name carries its menu label (`menu_label`), so a label
    with words in it lengthens the `name` field and renders the listing later; a listing
    without labels counts as it did under every market before. `description_words` is for a
    listing seeded with a description, which the seeder no longer writes."""
    names = [family["name"]] + [f"{family['name']} - {menu_label(v)}" for v in family["variants"]]
    name = sum(words(n) for n in names)
    skus = 2 * len(family["parent_sku"].split("-")) + sum(
        len(child_sku(family, v).split("-")) for v in family["variants"])
    return len(names), name, name + skus + STATUS_WORDS + description_words


def _tf(freq: int, length: int, average: float) -> float:
    return freq / (freq + K1 * (1 - B + B * stored_length(length) / average))


def score(family: dict, two_forms: bool = False, scale: float = 1.0,
          description_words: int = 0, averages: tuple[float, float] | None = None) -> float:
    """The listing's score for its brand, divided by what every listing of one brand shares
    (2.2 times the brand's idf). `scale` multiplies both average lengths; `averages` replaces
    them, for comparing with the index as it stands."""
    freq, name, search = lengths(family, description_words)
    on_name, on_search = averages or (AVGDL_NAME * scale, AVGDL_SEARCH * scale)
    if two_forms:
        return (6 * _tf(2 * freq, name, on_name) + 2 * _tf(freq, name, on_name)
                + 4 * _tf(2 * freq, search, on_search))
    return 8 * _tf(freq, name, on_name) + 4 * _tf(freq, search, on_search)


def idf(listings: int, documents: int = 104432) -> float:
    """The brand's idf, for comparing `score` with Elasticsearch's own figure."""
    return math.log(1 + (documents - listings + 0.5) / (listings + 0.5))


def order(families: list[dict], two_forms: bool = False, scale: float = 1.0) -> list[dict]:
    """The listings as the results pages would list them: highest score first, equal scores
    in catalogue order. Rounded so that two listings the shop scores alike compare equal
    here, whatever the last bits of a float."""
    return sorted(families, key=lambda f: -round(score(f, two_forms, scale), 9))


# ---------------------------------------------------------------------------
# Against the live index (read only)

# The stored markets the model is checked on, and whether each was seeded with its authoring
# note as description (before 13 September 2026), which the index still holds in `_search`.
STORED = (("scaled_apparel.json", False), ("claim_apparel.json", False),
          ("scaled_water.json", True), ("heldout_calderwood.json", True))
CONTAINER = "webarena-shopping"
INDEX = "magento2_product_1"      # the store's alias, which a reindex moves to its new index


def _es(path: str, body: dict) -> dict:
    out = subprocess.run(["docker", "exec", CONTAINER, "curl", "-s", "-m", "60", "-H",
                          "Content-Type: application/json", f"http://localhost:9200/{INDEX}/{path}",
                          "-d", json.dumps(body)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# The clauses of Magento's quick search for one word, as its mapper printed them on 22 October
# 2026, in its order: field and boost, then the two phrase prefixes with their analyzers.
SHOP_MATCHES = (("_search", 2), ("name", 6), ("sku", 7), ("description", 2),
                ("short_description", 2), ("manufacturer_value", 2), ("color_value", 2),
                ("status_value", 2), ("url_key", 2), ("tax_class_id_value", 2), ("_search", 2))
SHOP_PREFIXES = (("name", "prefix_search"), ("sku", "sku_prefix_search"))
# What the visibility filter adds to every listing's score.
VISIBILITY = 1.0


def shop_query(term: str) -> dict:
    """Magento's quick-search body for one word (the module docstring)."""
    should = [{"match": {field: {"query": term, "boost": boost}}} for field, boost in SHOP_MATCHES]
    should += [{"match_phrase_prefix": {field: {"query": term, "boost": 2, "analyzer": analyzer}}}
               for field, analyzer in SHOP_PREFIXES]
    return {"size": 200, "_source": ["sku"],
            "query": {"bool": {"must": [{"terms": {"visibility": ["3", "4"]}}],
                               "should": should, "minimum_should_match": 1}}}


def forms(brand: str) -> int:
    """How many forms the index's analyzer gives a word: two when its stem differs."""
    tokens = _es("_analyze", {"field": "name", "text": brand})["tokens"]
    return len({t["token"] for t in tokens})


def live_skus(brand: str, user_agent: str = "Mozilla/5.0 IGRGated/1.0") -> list[str]:
    """The listings' SKUs in the order the live results pages list them, following the pager."""
    keys: list[str] = []
    url = f"http://localhost:7770/catalogsearch/result/?q={brand}"
    while url:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        html = urllib.request.urlopen(request, timeout=180).read().decode()
        keys += re.findall(r'class="product-item-link"\s+href="http://localhost:7770/([^"/]+)\.html"', html)
        following = re.search(r'class="action\s+next"\s+href="([^"]+)"', html)
        url = following.group(1).replace("&amp;", "&") if following else None
    return [k.upper() for k in dict.fromkeys(keys)]


def index_statistics(document_id: str) -> tuple[int, float, float]:
    """The index as it stands: how many documents hold a name, and the average `name` and
    `_search` lengths BM25 divides by, read with the term-vectors API."""
    out = subprocess.run(["docker", "exec", CONTAINER, "curl", "-s", "-m", "60",
                          f"http://localhost:9200/{INDEX}/_termvectors/{document_id}?fields=name,"
                          "_search&field_statistics=true&positions=false&offsets=false"],
                         capture_output=True, text=True, check=True).stdout
    stats = {field: v["field_statistics"] for field, v in json.loads(out)["term_vectors"].items()}
    return (stats["name"]["doc_count"], stats["name"]["sum_ttf"] / stats["name"]["doc_count"],
            stats["_search"]["sum_ttf"] / stats["_search"]["doc_count"])


def validate(extra: tuple[pathlib.Path, ...] = ()) -> list[str]:
    """For each stored market, and any fixture named: the largest gap between the model's
    score, with the index's averages as they stand, and Elasticsearch's under Magento's own
    query; and whether the order the model gives with the constants the generator uses is
    the live pages'. One line each. Reads the shop and changes nothing."""
    lines = []
    for path, noted in [(HERE / "fixtures" / name, noted) for name, noted in STORED] + \
                       [(p, False) for p in extra]:
        fixture = json.loads(path.read_text())
        brand = fixture["_generated"]["brand"]
        two = forms(brand.lower()) == 2
        body = shop_query(brand.lower())
        body["_source"] = ["sku"]
        hits = _es("_search", body)["hits"]["hits"]
        shop = {h["_source"]["sku"]: h["_score"] - VISIBILITY for h in hits}
        total, on_name, on_search = index_statistics(hits[0]["_id"])
        unit = 2.2 * idf(len(fixture["families"]), total)
        gap = max(abs(score(f, two, averages=(on_name, on_search),
                            description_words=words(" ".join(f["note"])) if noted else 0)
                      * unit - shop[f["parent_sku"]]) for f in fixture["families"])
        same = [f["parent_sku"] for f in order(fixture["families"], two)] == live_skus(brand)
        lines.append(f"{brand:11} {'two forms' if two else 'one form '}: largest gap {gap:.6f} over "
                     f"{len(fixture['families'])} listings; order equals the live pages: {same}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", type=pathlib.Path)
    parser.add_argument("--two-forms", action="store_true",
                        help="score the brand as a word whose stem differs from it")
    parser.add_argument("--validate", action="store_true",
                        help="check the model against the live index and results pages, read only")
    args = parser.parse_args()
    if args.validate:
        print("\n".join(validate((args.fixture,) if args.fixture else ())))
        return 0
    if args.fixture is None:
        parser.error("name --fixture, or ask for --validate")
    families = json.loads(args.fixture.read_text())["families"]
    for n, family in enumerate(order(families, args.two_forms), 1):
        freq, name, search = lengths(family)
        print(f"{n:3} {family['parent_sku']:12} {score(family, args.two_forms):.6f} "
              f"options {freq - 1} name {name} _search {search}  {family['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
