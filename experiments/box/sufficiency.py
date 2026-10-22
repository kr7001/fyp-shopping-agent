#!/usr/bin/env python3
"""Decide whether a run's answer is supported by what the run actually observed.

Two failure modes appeared in the baseline, and they need different tests.

**Delta read as an absolute.** Magento labels variant options with a surcharge, so the
option reads `2 x 9.5L +$15.01` against a $9.89 base. A run that reports $15.01 as the
price has retrieved the right token and misread its semantics. Asking whether the field
was observed does not catch this: it was observed. What catches it is arithmetic. A price
that appears among the observed deltas but never as an observed absolute is a delta being
passed off as a total.

**A number that was never seen at all.** Distinct from the above and genuinely
unsupported, whatever produced it.

Both tests read only what the run already recorded, so neither costs a page fetch. That
is the point: this is meant to run inside the agent before it answers, where the budget
for checking is close to zero.

This module is deliberately evaluated offline first. Running it over the existing runs
says how many failures it would catch and how many correct answers it would wrongly
block, before any of it is wired into the agent and paid for.

    python experiments/box/sufficiency.py --evaluate
    python experiments/box/sufficiency.py --log experiments/results/<dir>/<run>.log --answer "..."
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import pathlib
import re
import sys
from typing import Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import trace_stats

RESULTS = paths.RESULTS

# Which rule set scored a run. Bumped when a rule is added or its decision changes, so a
# recorded verdict says what judged it rather than leaving it to be inferred from a date.
#
#   1  the six rules frozen at c736bc0 and measured on two held-out batches
#   2  adds superlative_without_coverage, written 17 September 2026 from the principle
#      rather than from the runs it would catch, and frozen before the next market exists
#   3  adds count_without_coverage, written 18 September 2026 alongside the clothing market
#      and before any run of it. No existing question is a counting question, so this
#      changes no recorded verdict
#   4  20 October 2026. The rules are the same; the listing count they are given changes.
#      `listings_opened` counts the market's own listings when the page record names them,
#      and otherwise a generated market's product page or Magento's id path, never a
#      category or home page. Replayed over every stored run of the clothing cells, the
#      pilot and the three box v2 batches, one count changes: 20261014T213118
#      apparel-all-stocked-2, 2 to 1, where `electronics.html` had been counted. No
#      verdict changes
#   5  22 October 2026, for the second claim market's water. The menu reader reads a pack
#      menu, the combobox "Pack Size *", as it reads a size menu (`MENU_HEAD`); until v5 no
#      log reader saw a water menu at all. Checked on every stored water log's readings
#      against its own fixture, and on a live Larchmere water listing's snapshot
#      (`tests/test_box.py`, `PackMenus`). And a menu holding its placeholder alone, a page
#      whose script had not yet filled it in, is no reading, where it was a complete menu
#      lacking every variant; no stored log holds one. No stored box run is on water, so
#      no verdict of the box's check changes
#
# Runs scored under different versions are different measurements. A figure quoted from
# version 1 runs stays a version 1 figure, and the effect of version 2 on them is reported
# by replay, separately, never by restating the original number.
RULES_VERSION = 5

# Money is handled in integer cents throughout. Comparing prices as floats invites a
# value that does not round-trip to slip past an equality test, and the whole check rests
# on equality tests.
MONEY = r"(\d{1,5}\.\d{1,2})"

# A surcharge label, "+$15.01" or "+15.01". The plus is what makes it relative.
DELTA = re.compile(r"\+\s*\$?" + MONEY + r"(?![\d])")
# A money figure not preceded by a plus, so it reads as a total.
ABSOLUTE = re.compile(r"(?<!\+)(?<!\+ )\$" + MONEY + r"(?![\d])")
# Any decimal at all. Prices reach the agent both as rendered text and as JSON, where
# they carry one decimal place, so this deliberately accepts either.
ANY_DECIMAL = re.compile(r"(?<![\d.])" + MONEY + r"(?![\d])")

# A figure with a unit attached is a quantity, not a price. "8.4 litres" says how much, not
# how much it costs, and the money patterns below cannot tell the difference on their own.
# This was found on the held-out run: two correct answers were refused because they showed
# their working, "24 x 350ml (8.4 litres total)", and 8.4 was read as an unsupported $8.40.
# The same family as the delta misread that started this project, a number meaning
# something other than money, this time in my own checker rather than the agent's answer.
QUANTITY = re.compile(
    MONEY + r"\s*(?:l\b|litres?|liters?|ml\b|kg\b|g\b|kilograms?|grams?|"
            r"bottles?|packs?|units?|items?)", re.IGNORECASE)

# A figure carrying a per-unit denominator is derived by the agent, not read off the
# page, so it can be correct while appearing nowhere in the observations.
RATE = re.compile(MONEY + r"\s*(?:/\s*(?:l|kg|litre|liter|kilogram)\b|"
                          r"per\s+(?:litre|liter|kg|kilogram|l)\b)", re.IGNORECASE)

# An answer that announces it has produced a list, and contains no figures.
COMPLETION_CLAIM = re.compile(
    r"\b(successfully\s+(?:listed|extracted|retrieved|gathered)|"
    r"(?:listed|extracted)\s+all\b|here (?:are|is) the)", re.IGNORECASE)

# A universal claim, "every listing stocks it", is only supportable if the run looked at
# every listing. Its negation is not: one counterexample settles it. That asymmetry is
# what makes this checkable without knowing the right answer.
UNIVERSAL_QUESTION = re.compile(r"\b(every|all)\b", re.IGNORECASE)

# "How many listings stock it" is a claim about a population that no bound can shorten and
# no single observation can settle. Its answer is only determined by the evidence if the
# evidence covers every member, so it is the one question kind where opening everything is
# the honest plan rather than a failure to be efficient. Written from that principle at the
# same time as the clothing market it will first be asked in, and before any run of it.
COUNTING_QUESTION = re.compile(r"\bhow many\b", re.IGNORECASE)
AFFIRMS = re.compile(r"^\W*yes\b", re.IGNORECASE)
DENIES = re.compile(r"^\W*no\b", re.IGNORECASE)

# An answer that states the size of the set it considered can be checked against the size
# of the set that exists. "analysing all 4 sellers" is a comparison over 4 of 15, stated
# by the agent itself. This needs no ground truth about the right answer, only the
# population, and it catches a failure the arithmetic rules cannot see: every figure can
# be correctly observed and correctly combined and the comparison still be over the wrong
# set. The count is written both ways, so both are read.
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
COVERAGE_CLAIM = re.compile(
    r"\ball\s+(?:the\s+)?(\d{1,3}|" + "|".join(NUMBER_WORDS) + r")\s+"
    r"(?:\w+\s+){0,2}?(sellers?|listings?|products?|results?|items?|options?)\b",
    re.IGNORECASE)

# A superlative asserted over a whole market. "Which seller is cheapest across all the
# listings" is a claim about a population, and it is only determined by what was retrieved
# if the retrieval covered enough of that population to rule the rest out. The scope marker
# is required as well as the superlative, so that a question about the packs inside one
# listing, or about what the results page advertises, does not match.
SUPERLATIVE = re.compile(
    r"\b(cheapest|dearest|lowest\s+(?:price|cost|rate)?|highest|best\s+value|"
    r"most\s+expensive|least\s+expensive)\b", re.IGNORECASE)
MARKET_SCOPE = re.compile(
    r"\b(across\s+all|all\s+the\s+listings|all\s+listings|every\s+listing|"
    r"all\s+sellers|every\s+seller|which\s+seller|anyone\s+charges|any\s+seller)\b",
    re.IGNORECASE)
# Answerable from the results page without opening anything, so coverage of the listings
# is not what makes it sound. The control question is of this shape.
ON_RESULTS_PAGE = re.compile(r"\b(advertis\w+|on the results page)\b", re.IGNORECASE)

# Which listings a run opened, read from the record of where the browser went.
#
# This is the one measure meant to survive a change of agent, and it has been wrong three
# times, each time because it recognised one URL shape rather than the idea of a product
# page. It matched `page.goto` only, and missed listings opened by clicking a card. It
# matched `igr-*.html` only, and read zero for a store view serving Magento's id form. Then
# the second scaffold followed the site's own links, which are named after the product,
# `calderwood-still-spring-water-multipack-chandler-direct.html`, and it read zero again.
#
# Magento serves product pages as a single path segment ending in .html, or as an id path.
# Search results carry a query string and live under catalogsearch. But a category page is
# a single-segment .html path too (`electronics.html`), and on 14 October 2026 a run that
# wandered to one was counted as having opened a listing, the fourth time the counter read
# a shape rather than the thing (LESSONS 2). So since 20 October a page is a listing by
# what it is: one of the market's own listings when the results page the box read names
# them (`listings_opened(text, market)`), and otherwise a product page of one of the
# generated markets, whose URL key is its SKU (`igr-app-07`, `igr-rvn-03`, `igr-cal-11`,
# `igr-water-a`), or Magento's id path. Every stored batch but two void ones from September
# used one of those two forms, so no stored count changes but the one above.
PAGE_MARKER = re.compile(r"Page URL:\s*(\S+)")
PRODUCT_NAV = re.compile(r"page\.goto\('([^']+)'\)")
PRODUCT_PATH = re.compile(r"^/[a-z0-9][a-z0-9-]*\.html$", re.IGNORECASE)
PRODUCT_BY_ID = re.compile(r"^/catalog/product/view/id/(\d+)")
GENERATED_SLUG = re.compile(r"^slug:igr-", re.IGNORECASE)

# A listing's size menu as the agent's own snapshot of the page reports it, read from the
# box v2 batches' logs on 20 October 2026 (20261014T213118/apparel-all-stocked-1.log,
# igr-app-03): a `combobox "Size *"` line, then one `option "..."` line per entry of the
# menu, the placeholder first and a sold-out size marked `[disabled]`. The runtime stores
# the reply as a Python repr inside JSON, so in the text a newline is the two characters
# backslash and n, and a quote carries a backslash; `size_menus` undoes that before reading.
#
# A `browser_find` reply is an excerpt, the matched line and three more, cut wherever that
# falls: in 20261014T213118/apparel-count-stocked-2.log the find for "Size" on igr-app-08
# ends after `option "S"` and `option "M"` where the menu is S, M, L, XL, and the first
# reader took that for the whole menu (verifier finding, 20 October 2026). So each reading
# says whether it is complete: a reply that carries the page URL (a navigation or a
# snapshot) shows the whole page, and so does an option block followed by a line that is
# not an option. An excerpt that ends inside the block is partial: the sizes it shows are
# seen, disabled or not, and nothing can be said about the sizes it does not show.
#
# A snapshot taken with a `depth` prints a node beyond it as a leaf, with no children and
# no mark that any were dropped: 20260910T133605/scaled-cheapest-target-1.log (depth 6)
# prints `- combobox "Pack Size *" [ref=f3e89]` with no colon and no option lines, and the
# next line is its sibling. So a head line without a trailing colon has no rendered
# children and gives no reading at all; with one, the block rule applies. The verifier
# checked this on every combobox head in every stored tool reply under experiments/results
# and experiments/runs on 20 October 2026: 5,574
# heads; 3,646 with a colon and a child line after it; 1,924 with no colon and no child;
# 4 with a colon and no child, "Sort By" heads at the end of a find window, which match
# no Size head and give no reading.
#
# The find renderer prints windows of three lines around each match under the ancestor
# chain, with no gap marker before a window that starts inside the option block, so a
# find block whose first option line is not the menu's placeholder may have lost options
# before its window (20261014T220116/apparel-cheapest-xl-1, igr-app-08: a find for "XL"
# prints the head and S, M, L, XL without the placeholder). Such a block is partial at the
# front and shows presence only, whatever follows it.
# The variant menu's combobox: "Size *" on the clothing listings, "Pack Size *" on the water's,
# read off the live shop (since v5, 22 October 2026; until then the water's was never read).
MENU_HEAD = re.compile(r'combobox "(?:Pack )?Size[^"]*"')
MENU_LINE = re.compile(r'^[ \t]*- option "([^"]*)"((?: \[[^\]]*\])*)[ \t]*$')
MENU_OPTION = re.compile(r'option "([^"]*)"((?: \[[^\]]*\])*)')
MENU_PLACEHOLDER = "Choose an Option..."


@dataclasses.dataclass
class MenuReading:
    """What a run saw of one listing's size menu: each size shown and whether it could be
    chosen, and whether the whole menu was seen. Absence of a size is evidence only from a
    complete reading; presence, disabled or not, from any."""
    options: dict[str, bool] = dataclasses.field(default_factory=dict)
    complete: bool = False

    def merge(self, options: dict[str, bool], complete: bool) -> None:
        self.options.update(options)
        self.complete = self.complete or complete


def _listing_key(url: str) -> str | None:
    """One listing, however it was addressed, or None when the page is not a listing.

    Magento serves the same product under a SKU slug, a name slug and an id path, and a run
    may use more than one of them. The id is the only part all three share, so it wins when
    it is there.

    A product outside the searched market counts as a page opened, because it is one. Runs
    stay inside the market they were sent to, so in practice this is the market's own
    listings, and the one exception on record is a naive run that wandered to product id 1.
    """
    # Logs escape their content, so a captured URL can carry trailing junk such as `\n-`.
    url = re.split(r"[\\\s\"'<>]", url)[0].rstrip("/")
    if "?" in url or "catalogsearch" in url:
        return None
    path = url.split("localhost:7770", 1)[-1] if "localhost:7770" in url else url
    if not path.startswith("/"):
        return None
    by_id = PRODUCT_BY_ID.match(path)
    if by_id:
        return f"id:{by_id.group(1)}"
    if PRODUCT_PATH.match(path):
        return "slug:" + path[1:].removesuffix(".html")
    return None


def listing_key(url: str) -> str | None:
    """`_listing_key`, for the box: the key a listing's URL is counted under when a run
    opens it, so a plan can say which of the listings it named were opened (14 Oct 2026)."""
    return _listing_key(url)


# Below this, a figure in this catalogue is a per-unit rate rather than a total. Rates
# are computed by the agent and correctly absent from the page, so the unsupported test
# does not apply to them. A stated domain assumption: the cheapest total in these
# fixtures is $6.37 and the dearest rate is $1.65 per litre.
RATE_CEILING_CENTS = 500


def cents(value: str | float) -> int:
    """Money as an integer number of cents."""
    return int(round(float(value) * 100))


def observed_text(log_path: pathlib.Path) -> str:
    """Everything the agent actually read back from the browser.

    Only tool results count. The assistant's own messages are what it said, not what it
    saw, and treating its claims as evidence would make the check circular.
    """
    parts = []
    for message in trace_stats.final_messages(log_path):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        parts.append(content if isinstance(content, str) else json.dumps(content))
    if parts:
        return "\n".join(parts)

    # A log that holds no openJiuwen trace belongs to another scaffold, which writes what it
    # observed as plain text. Reading it whole is right there and wrong for openJiuwen, whose
    # log also carries the model's own claims, and treating those as evidence would make the
    # check circular. So this is a fallback rather than the rule.
    try:
        return log_path.read_text(errors="replace")
    except OSError:
        return ""


def evidence(text: str) -> dict[str, set[int]]:
    return {
        "deltas": {cents(m) for m in DELTA.findall(text)},
        "absolutes": {cents(m) for m in ABSOLUTE.findall(text)},
        "any": {cents(m) for m in ANY_DECIMAL.findall(text)},
    }


def listings_opened(text: str, market: Iterable[str] | None = None) -> set[str]:
    """Distinct listings the run landed on, however it got there.

    Reads both the addresses the run navigated to and the addresses its observations report
    it was at, so a listing opened by clicking a card counts the same as one opened by
    typing its URL.

    `market` is the listing URLs of the results page the box read. When it is given, only
    those listings count: they are the market the run was sent to, which is what a listing
    is rather than how its address is spelled (LESSONS 2). Without it, a product page of a
    generated market or Magento's id path counts, and a category or home page never does
    (20 October 2026; until then any single-segment .html path counted, and all-stocked-2
    of 20261014T213118 read 2 listings for one listing and `electronics.html`). A market
    given as slugs does not recognise the id path of one of its own listings, which no run
    under the box has used.
    """
    found = set()
    for url in PRODUCT_NAV.findall(text) + PAGE_MARKER.findall(text):
        key = _listing_key(url)
        if key:
            found.add(key)
    if market is not None:
        return found & {key for key in map(listing_key, market) if key}
    return {key for key in found if key.startswith("id:") or GENERATED_SLUG.match(key)}


def menu_blocks(text: str, whole_page: bool) -> list[tuple[dict[str, bool], bool]]:
    """Every size menu in one reply's text, as (the options seen, whether the reading is
    complete). The block is the option lines after a Size combobox line that ends with a
    colon; it is complete when it begins with the menu's placeholder and either the reply
    shows the whole page or a line of the page's tree follows the block. A block that does
    not begin with the placeholder may have lost options before a find window, and a line
    that starts as an option and is cut short still shows its size; both are partial."""
    plain = text.replace("\\\\n", "\n").replace("\\n", "\n").replace('\\"', '"')
    lines = plain.split("\n")
    found = []
    for n, line in enumerate(lines):
        if not MENU_HEAD.search(line):
            continue
        if not line.rstrip().endswith(":"):
            continue      # a leaf: its children were not rendered, so nothing was seen
        options: dict[str, bool] = {}
        complete = whole_page
        first = None
        for later in lines[n + 1:]:
            whole = MENU_LINE.match(later)
            if whole:
                label, flags = whole.group(1), whole.group(2)
            else:
                cut = MENU_OPTION.search(later) if later.lstrip().startswith('- option "') else None
                if cut is None:
                    # The block ended before the text did, when what follows is another
                    # line of the page's tree or the end of the yaml, not the reply's
                    # closing characters.
                    if later.lstrip().startswith("- ") or later.strip().startswith("```"):
                        complete = True
                    break
                label, flags = cut.group(1), cut.group(2)
            first = label if first is None else first
            if label != MENU_PLACEHOLDER:
                options[label] = "[disabled]" not in flags
            if not whole:
                break                     # a cut line is where an excerpt ended
        if first != MENU_PLACEHOLDER:
            complete = False              # options before the window may be missing
        if not options:
            # The placeholder alone: the page's script had not yet filled the menu in when
            # the snapshot was taken, and a listing always has a variant, so this shows
            # nothing (v5, 22 October 2026: every live Larchmere water listing read this
            # way just after loading, a complete menu lacking every pack until then).
            complete = False
        found.append((options, complete))
    return found


def size_menus(log_path: pathlib.Path) -> dict[str, MenuReading]:
    """The size menu each opened listing showed the run, from the tool replies alone: for
    each listing key, the sizes seen in its menu, whether each could be chosen (False when
    the option is marked disabled, which is how this shop lists a sold-out size), and
    whether the whole menu was seen.

    A reply that reports a page URL says where the browser was; a reply without one, such
    as a find, belongs to the page reported last, since the browser is at one page at a
    time. Only openJiuwen's logs carry these replies; another scaffold's log gives nothing
    here. Added 20 October 2026 for the counterexample check: a bare "No" is supported when
    an opened listing's complete menu lacks the size asked about, whether or not the answer
    names it.
    """
    menus: dict[str, MenuReading] = {}
    current = None
    for _tool, text, _args in trace_stats.tool_replies(log_path).values():
        located = PAGE_MARKER.search(text)
        if located:
            current = _listing_key(located.group(1))
        if current is None:
            continue
        for options, complete in menu_blocks(text, whole_page=located is not None):
            if options or complete:
                menus.setdefault(current, MenuReading()).merge(options, complete)
    return menus


def prices_in(text: str) -> list[int]:
    return [cents(m) for m in ANY_DECIMAL.findall(text or "")]


def rate_values(text: str) -> set[int]:
    return {cents(m) for m in RATE.findall(text or "")}


def quantity_values(text: str) -> set[int]:
    """Figures that are measurements rather than money."""
    return {cents(m) for m in QUANTITY.findall(text or "")}


def verified_compositions(amounts: list[int], seen: dict[str, set[int]]) -> set[int]:
    """Figures exonerated by arithmetic the observations actually support.

    An answer reading "$17.68 (base $6.82 + upgrade $10.86)" states its own working, and
    punishing it would penalise exactly the behaviour this check exists to encourage.

    The sum alone is not enough. An earlier version accepted any three figures where two
    summed to a third, which let a wrong answer clear itself by inventing a plausible
    breakdown: "$15.01 (base $9.89 + upgrade $5.12)" passed while $5.12 was never seen.
    So the base has to have been observed as a total and the delta as a surcharge.
    """
    justified: set[int] = set()
    for base in amounts:
        for delta in amounts:
            if base == delta:
                continue
            total = base + delta
            if total in amounts and base in seen["absolutes"] and delta in seen["deltas"]:
                justified.update({base, delta, total})

    # The loop above only exonerates an answer that states its own working. An answer
    # that gives the total alone has nothing to compose, and was being called
    # unsupported even when the observations fully justified it. That cost a correct
    # answer in the retry arm: "$17.68, Redhill Stores" is right, and $17.68 is never
    # printed on the page, because it is the $6.82 base plus the $10.86 surcharge. Both
    # parts were observed. Showing the arithmetic is a virtue, not a precondition for
    # being believed, so the composition is checked against what was observed too.
    for base in seen["absolutes"]:
        for delta in seen["deltas"]:
            total = base + delta
            if total in amounts:
                justified.update({total})
    return justified


def superlative_over_population(question: str) -> bool:
    """Does this question ask for the best item in a whole market."""
    return bool(SUPERLATIVE.search(question) and MARKET_SCOPE.search(question)
                and not ON_RESULTS_PAGE.search(question))


def check(answer: str, seen: dict[str, set[int]], *, question: str = "",
          population: int | None = None, opened: int | None = None,
          floor: int | None = None) -> dict:
    """Verdict for one answer against one run's observations.

    `ok` means nothing was detected, not that the answer is right. This is a filter for
    specific, mechanically checkable faults, not a correctness oracle.

    Every figure presented as an amount is tested, not only the first. Testing the first
    let a wrong value escape by appearing later in the sentence, which made word order
    decide whether the answer was checked at all.
    """
    # A universal claim is checked first, because it can be unsupported while containing
    # no figures at all. "Yes" is the whole answer in the cases this catches.
    if (question and population and opened is not None
            and UNIVERSAL_QUESTION.search(question) and AFFIRMS.match(answer)
            and opened < population):
        return {"flag": "unverified_universal", "ok": False,
                "why": (f"claims every one of {population} listings qualifies, "
                        f"having opened {opened}"),
                "claimed": []}

    # A stated coverage smaller than the population, checked before the figures, because
    # the figures can all be sound while the comparison is over the wrong set.
    if population:
        for count, _noun in COVERAGE_CLAIM.findall(answer):
            size = NUMBER_WORDS.get(count.lower(), None)
            size = int(count) if size is None and count.isdigit() else size
            if size is not None and size < population:
                return {"flag": "understated_population", "ok": False,
                        "why": (f"claims to have covered all {size}, where the result "
                                f"set holds {population}"),
                        "claimed": prices_in(answer)}

    # A superlative over a market, asserted after opening fewer listings than any correct
    # method would need.
    #
    # Written from the principle rather than from the runs. The three rules above all read
    # something the agent said about itself, so an agent that says less about itself is
    # checked less, which is a ceiling on the method rather than a bug in it. This rule
    # reads the question and the trace instead, and needs the answer to volunteer nothing.
    #
    # The principle: a claim about the best item in a population is determined by what was
    # retrieved only if what was retrieved rules out the rest of that population. The
    # generator already computes the fewest listings any correct method could open, after
    # pruning everything the published prices allow, and calls it the oracle floor. Below
    # that floor an answer may still be right, but it was not determined by the evidence,
    # and the project reports earned separately from right for exactly this reason.
    #
    # Deliberately not written while looking at which runs it would catch. Six of the nine
    # failures on the held-out market are of this shape and none of the rules above sees
    # them, which is what prompted a rule, but fitting the threshold to those six would
    # spend the held-out market. The threshold is the floor the generator computes, and the
    # next market is where it gets tested.
    #
    # The floor recorded in these fixtures is computed for the target-pack comparison. The
    # per-litre question ranges over every pack of every listing, so its true floor is at
    # least as high, which makes this a conservative test on that question rather than an
    # aggressive one.
    if (question and opened is not None and superlative_over_population(question)
            and (floor or population)):
        required = floor or population
        if opened < required:
            return {"flag": "superlative_without_coverage", "ok": False,
                    "why": (f"names the best of {population or required} listings having "
                            f"opened {opened}, below the {required} any correct method "
                            f"needs"),
                    "claimed": prices_in(answer)}

    # A count asserted without having seen the population it counts over.
    if (question and opened is not None and population
            and COUNTING_QUESTION.search(question) and re.search(r"\d", answer or "")
            and opened < population):
        return {"flag": "count_without_coverage", "ok": False,
                "why": (f"states how many of {population} listings qualify, having opened "
                        f"{opened}. A count cannot be bounded or settled early"),
                "claimed": prices_in(answer)}

    # The mirror of the rule above, and it was missing. Refuting a claim about every
    # listing is cheap precisely because one counterexample settles it, but a
    # counterexample has to have been seen. A run that answered "No" having opened no
    # listing at all was right, and right by luck, and passed this check clean because the
    # coverage rule only ever looked at affirmations.
    if (question and opened is not None and UNIVERSAL_QUESTION.search(question)
            and DENIES.match(answer) and opened == 0):
        return {"flag": "refutation_without_evidence", "ok": False,
                "why": ("denies a claim about every listing without having opened any, so "
                        "no counterexample was observed"),
                "claimed": prices_in(answer)}

    claimed = prices_in(answer)
    rates = rate_values(answer)
    quantities = quantity_values(answer)
    amounts = [v for v in claimed if v not in rates and v not in quantities]

    if COMPLETION_CLAIM.search(answer) and not amounts:
        return {"flag": "claim_without_content", "ok": False,
                "why": "the answer announces a completed list and contains no figures",
                "claimed": claimed}
    if not amounts:
        return {"flag": None, "ok": True, "why": "no price claimed as an amount",
                "claimed": claimed}

    justified = verified_compositions(amounts, seen)

    for value in amounts:
        if value in justified:
            continue
        if value in seen["deltas"] and value not in seen["absolutes"]:
            return {"flag": "delta_as_absolute", "ok": False,
                    "why": f"${value / 100:.2f} was observed only as a surcharge, never as a total",
                    "claimed": claimed}

    for value in amounts:
        if value in justified or value < RATE_CEILING_CENTS:
            continue
        if value not in seen["any"]:
            return {"flag": "unsupported_number", "ok": False,
                    "why": f"${value / 100:.2f} does not appear anywhere the run looked",
                    "claimed": claimed}

    return {"flag": None, "ok": True, "why": "every figure is observed or arithmetically justified",
            "claimed": claimed}


def evaluate() -> int:
    """Replay the check over every recorded run and report what it would have done."""
    tasks: dict[str, dict] = {}
    populations: dict[str, int] = {}
    floors: dict[str, int] = {}
    for spec_path in (paths.TASKS / "tasks.json", paths.TASKS / "tasks_scaled.json"):
        if not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text())
        instance = spec.get("_instance") or {}
        size = instance.get("listings")
        floor = instance.get("oracle_min_opens")
        for task in spec["tasks"]:
            tasks[task["id"]] = task
            if size:
                populations[task["id"]] = size
            if floor:
                floors[task["id"]] = floor

    rows = []
    for suite_path in sorted(RESULTS.glob("*/suite.json")):
        payload = json.loads(suite_path.read_text())
        for row in payload["rows"]:
            log_path = suite_path.parent / (row.get("log") or "")
            if not row.get("log") or not log_path.exists():
                continue
            text = observed_text(log_path)
            task = tasks.get(row["task"], {})
            verdict = check(row.get("answer") or "", evidence(text),
                            question=task.get("query", ""),
                            population=populations.get(row["task"]),
                            opened=len(listings_opened(text)),
                            floor=floors.get(row["task"]))
            opened = len(listings_opened(text))
            # The oracle floor belongs to comparison questions only. Naming the single
            # best across every listing requires opening everything the published prices
            # cannot rule out. A universal yes/no does not: refuting "every listing
            # stocks it" takes one counterexample, so scoring it against a floor of
            # eleven would call a sound answer unearned.
            query = task.get("query", "").lower()
            is_comparison = any(w in query for w in
                                ("cheapest", "lowest", "best value", "which seller"))
            is_global = is_comparison and ("across all" in query or "all the" in query)
            rows.append({**row, "suite": suite_path.parent.name,
                         "flag": verdict["flag"], "flag_why": verdict["why"],
                         "opened": opened,
                         "population": populations.get(row["task"]),
                         "floor": floors.get(row["task"]) if is_global else None})

    if not rows:
        print("no runs with traces on disk. Logs are gitignored, so this needs a local run.")
        return 1

    table = collections.Counter((r["verdict"], r["flag"] or "clean") for r in rows)
    scored = [r for r in rows if r["verdict"] in ("correct", "wrong", "ambiguous")]
    wrong = [r for r in scored if r["verdict"] in ("wrong", "ambiguous")]
    right = [r for r in scored if r["verdict"] == "correct"]
    caught = [r for r in wrong if r["flag"]]
    false_flags = [r for r in right if r["flag"]]

    print(f"runs with traces: {len(rows)}\n")
    print(f"{'scored verdict':16} {'flag raised':20} {'runs':>5}")
    print("-" * 44)
    for (verdict, flag), n in sorted(table.items()):
        print(f"{verdict:16} {flag:20} {n:>5}")

    print(f"\ncaught      {len(caught)} of {len(wrong)} wrong or ambiguous runs")
    print(f"false flags {len(false_flags)} of {len(right)} correct runs")
    report_soundness(rows)

    if caught:
        print("\ncaught:")
        for r in caught:
            print(f"  {r['task']}-{r['repeat']:<2} {r['flag']:20} {r['flag_why']}")
    if false_flags:
        print("\nfalse flags, these would be blocked wrongly:")
        for r in false_flags:
            print(f"  {r['task']}-{r['repeat']:<2} {r['flag']:20} {r['flag_why']}")
    return 0


def report_soundness(rows: list[dict]) -> None:
    """Correct answers that were not actually earned.

    Coverage deliberately does not gate the global comparison questions, because it does
    not separate right from wrong on them: one correct run opened 4 of 15 listings and
    one wrong run opened 4 as well. Blocking on coverage would reject a correct answer.

    That is not a reason to ignore the signal. The agent has no pruning logic, and the
    oracle floor for these questions is 11 listings, so a correct answer after 4 opens
    was not reasoned to, it was landed on. Correctness and soundness are different
    properties, and an accuracy-only baseline cannot tell them apart. A policy that
    abstains here scores worse on accuracy and is better in expectation, which is an
    argument RQ3 has to be able to make with numbers.
    """
    unearned = [r for r in rows
                if r["verdict"] == "correct" and r.get("floor")
                and r.get("opened") is not None and r["opened"] < r["floor"]]
    scoped = [r for r in rows if r["verdict"] == "correct" and r.get("floor")]
    if not scoped:
        return
    print(f"\nunearned    {len(unearned)} of {len(scoped)} correct answers to global "
          f"comparison questions were reached with less evidence than any correct "
          f"policy needs")
    for r in unearned:
        print(f"  {r['task']}-{r['repeat']:<2} opened {r['opened']} of "
              f"{r['population']}, oracle floor {r['floor']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evaluate", action="store_true",
                        help="replay the check over every recorded run")
    parser.add_argument("--log", type=pathlib.Path)
    parser.add_argument("--answer")
    args = parser.parse_args()

    if args.evaluate:
        return evaluate()
    if not args.log or args.answer is None:
        parser.error("give --evaluate, or both --log and --answer")

    seen = evidence(observed_text(args.log))
    print(f"observed deltas    {sorted(seen['deltas'])}")
    print(f"observed absolutes {sorted(seen['absolutes'])}")
    print(json.dumps(check(args.answer, seen), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
