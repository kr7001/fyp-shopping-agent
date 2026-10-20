#!/usr/bin/env python3
"""The retrieval primitives: what to open, in what order, when to stop, and what the answer
must show. Box v2's second step, 14 October 2026.

Every plan the box sends is one primitive applied to the form `form.py` parsed, with the
form's filters carried inside it. The stop rules are theorems about the quantifier rather
than judgements: a lower bound prunes, one witness proves an existence, one counterexample
refutes a universal, a count needs the whole population, a review question turns pages. The
answer check of each primitive is the same rule read backwards: did the run open what its
stop rule required.

For the seven kinds v1 had, the instruction is `targeting.BODIES[kind]`, the same bytes, so
the pilot measured under v1 stays a measurement of what v2 sends (`tests/test_box.py` pins
that against a fixture frozen from v1). New text exists only for the forms v1 could not
express: existence under a price limit, the k cheapest, named listings, the dearest. Every
statement in that text about the shop was checked against the live gated Thornwood results
page and a listing on 14 October 2026 (LESSONS 17). Each card advertises one price, which
is the cheapest option the listing can sell. A listing's size menu is filled from its page
config. The chosen size's price is written into the price box after it is chosen. A size
with no salable product is listed in the menu as a disabled option.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/, runners/, analysis/, water/ on the path)
import form as form_module
import page as page_module
import planner
import policy
import score as scoring
import sufficiency
import targeting

# Bumped when a primitive's text, stop rule or check changes. Runs made under different
# versions are different boxes and are never pooled.
#
#   1  14 October 2026. Seven primitives. The v1 kinds render their v7 bodies unchanged
#   2  14 October 2026. The witness and counterexample checks no longer pass an answer
#      that opens with neither yes nor no: one that names a listing is held to the
#      coverage its claim needs, and one that names nothing is flagged as unclear. The
#      bound check counts a tie at the answer's price once (`policy.bound_floor`)
#   3  14 October 2026. A denial is read however it starts, "None of the sellers" and
#      "Nobody" as well as "No" (`denies`), and an existence answer with neither yes nor
#      no owes what a no owes, whatever listing it names. The bound check's extra one is
#      for the answer's own listing only, and a seller is named only as a whole word
#      (`policy.bound_floor`, `policy.named_in`)
#   4  20 October 2026. The counterexample check reads the size menus the run saw: a No
#      is supported when an opened listing's observed menu lacks the size asked about, or
#      shows it disabled when the question is about buying, whether or not the answer
#      names it (`counterexample_seen`). Every check counts as opened only the market's
#      own listings, those on the page the box read (`sufficiency.listings_opened`)
#   5  20 October 2026. Absence of a size counts only from a complete menu reading; a
#      find excerpt cut inside the menu shows the sizes it lists and nothing else
#      (verifier finding: an excerpt of S, M was read as a menu without L and XL)
#   6  20 October 2026, the verifier's audit of the claim plan. A strict limit, "under
#      $27", is read as below $27.00 by the witness text, its stop rule, its check's floor
#      and the filter's sentence and check (`Limit`, form v9). The texts say what the shop
#      does: before choosing, a listing shows its cheapest size that can be bought, which
#      may be the one asked about, and stopping after one opening is right when that
#      listing settles it (strategy text v8). And a plan can be composed without its stop
#      rule, for the arm that isolates it (`exhaust_swaps`, `suite.py --box-exhaust`)
#   7  20 October 2026. A disabled size "cannot be chosen from the menu", where the text
#      said it could not be chosen at all: a script can force it (strategy text v9)
#   8  20 October 2026. Under the box without its stop rule the quarantine no longer opens
#      by saying the bound decides what to skip, since nothing is skipped there; it says
#      what the advertised price is (`QUARANTINE_LEAD`). The box's own text is unchanged
VERSION = 8

# The same hazard as every v1 bound strategy: a figure derived from a bound is not a price.
QUARANTINE = targeting.QUARANTINE


def preamble(page: page_module.Page) -> str:
    """What the box read from the results page, in the words the agent receives.

    The listings come sorted by advertised price because every bound strategy opens them
    in that order, and their URLs come with them. Finding those was the box's work: the
    cells it is compared with had to find them, and that is stated as a difference rather
    than hidden. Box v1's text, byte for byte.
    """
    pager = ("there is a next page, open it too before deciding." if page.next_page
             else "there is no next page.")
    lines = [f"The results page lists {len(page.listings)} listings on one page; {pager}",
             "Listings by advertised price, read from the results page:"]
    lines += [f"{n}. {item.seller}, advertised ${item.advertised:.2f}, {item.url}"
              for n, item in enumerate(page.by_price(), 1)]
    return "\n".join(lines)


@dataclasses.dataclass(frozen=True)
class Plan:
    primitive: str                                  # which primitive composed it
    kind: str                                       # the form's kind
    filters: tuple[form_module.Filter, ...]
    candidates: tuple[page_module.Listing, ...]     # in the order the primitive opens them
    stop_rule: str
    instruction: str                                # the primitive's text alone
    text: str                                       # the preamble, then the instruction
    exhaust: bool = False                           # composed without its stop rule, `exhaust_swaps`

    def record(self) -> dict:
        return {"primitives_version": VERSION, "primitive": self.primitive, "kind": self.kind,
                "stop_rule": self.stop_rule, "filters": [f.record() for f in self.filters],
                "candidates": [{"seller": c.seller, "url": c.url} for c in self.candidates],
                "exhaust": self.exhaust}


# ---------------------------------------------------------------------------
# Verdicts, and what the answer and the page say

def ok(why: str) -> dict:
    return {"ok": True, "flag": None, "why": why}


def flag(name: str, why: str) -> dict:
    return {"ok": False, "flag": name, "why": why}


def affirms(answer: str) -> bool:
    return bool(sufficiency.AFFIRMS.match(answer or ""))


# A denial that does not start with the word "no": "None of the sellers ...", "Nobody
# sells ...", "Not one.", "There is no seller ...". `sufficiency.DENIES` is `^\W*no\b`
# alone, which "No one" and "No seller sells" already match, and widening it would
# re-score every stored run, so the box's own checks read the union here (verifier
# finding, 14 October 2026: "None of the sellers, including Seller A at $25.00, sells size
# M under $20.00" was read as a yes through the listing it names). Run over the 446 stored
# answers on that day, it matched none, so no replay changes.
NEGATION = re.compile(r"^\W*(?:none|nobody|not\s+one|there\s+(?:is|are)\s+no)\b", re.IGNORECASE)


def denies(answer: str) -> bool:
    return bool(sufficiency.DENIES.match(answer or "") or NEGATION.match(answer or ""))


# The page's listings an answer names, as whole names. It lives beside the floor that
# needs it (`policy.bound_floor`) and keeps this name because the checks below call it.
named_in = policy.named_in


def opened_all(page: page_module.Page, opened: set[str]) -> bool:
    return len(opened) >= len(page.listings)


@dataclasses.dataclass(frozen=True)
class Limit:
    """The price limit a question set, and whether the figure itself is allowed: "under
    $27" is strict, below $27, and "at most $27" is not (form v9, 20 October 2026). The
    witness text, the filter's sentence, the witness check's floor and the filter's check
    all read the operator here, so they cannot disagree about a price at the limit."""
    value: float
    strict: bool

    def admits(self, price: float) -> bool:
        """Whether a price meets the limit, within half a cent, because the page's price
        is a float and an answer's is parsed text."""
        return price < self.value - 0.005 if self.strict else price <= self.value + 0.005

    @property
    def within(self) -> str:
        """How the text says a price meets the limit."""
        return "below" if self.strict else "at or below"

    @property
    def beyond(self) -> str:
        """How the text says an advertised price rules a listing out."""
        return "at or above" if self.strict else "above"


def limit_of(form: form_module.Form) -> Limit | None:
    limit = form.filter("price")
    if limit is None or limit.op not in ("<", "<="):
        return None
    return Limit(float(limit.value), strict=limit.op == "<")


def option_phrase(form: form_module.Form) -> str:
    """How the text names the variant: "size M", "the 2 x 9.5L pack", or the generic."""
    size = form.filter("size")
    if size is None:
        return "the option asked about"
    value = str(size.value)
    return f"size {value}" if value.isalnum() else f"the {value} pack"


def named_listings(form: form_module.Form, page: page_module.Page) -> list[tuple[str, str | None]]:
    """The listings a lookup names, as (label, URL): by URL, labelled with the seller when
    the page shows that URL, or by seller, with the URL the page shows for it."""
    named = []
    urls = form.filter("url")
    if urls is not None:
        by_url = {item.url: item for item in page.listings}
        named += [(by_url[url].seller if url in by_url else url, url) for url in urls.value]
    sellers = form.filter("seller")
    if sellers is not None:
        by_seller = {item.seller.lower(): item for item in page.listings}
        named += [(seller, by_seller[seller.lower()].url if seller.lower() in by_seller else None)
                  for seller in sellers.value]
    return named


# ---------------------------------------------------------------------------
# The filter modifier, applied inside the other primitives

def option_steps(form: form_module.Form) -> str:
    """Choose the option and look again, then check it can be bought. The same facts the
    availability strategy states, in the same words, since they were checked on the shop,
    and corrected with it in strategy text v8 (20 October 2026): before choosing, a listing
    shows its cheapest size that can be bought, which may be the one asked about."""
    steps = [f"choose {option_phrase(form)}, then look at the page again and read the price it "
             "now shows. The price a listing shows before you choose is its cheapest option "
             "that can be bought, not necessarily the one asked about, and the reply to "
             "choosing an option does not show the new price."]
    availability = form.filter("availability")
    if availability is not None and availability.value == "buyable":
        steps.append("Then check whether that option can actually be bought. An option can be "
                     "listed and still be unavailable, in which case it is shown as disabled or "
                     "greyed out and cannot be chosen from the menu, so it has no price you can "
                     "use.")
    elif availability is not None:
        steps.append("An option counts when it is in the listing's menu, whether or not it can "
                     "be chosen.")
    return " ".join(steps)


class FilterModifier:
    """Not a plan of its own: the sentences and the check the form's filters add to any of
    the primitives below. The witness folds the price limit into its own steps, so it takes
    `option_steps` alone, and the others take the whole instruction."""
    name = "filter"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        text = option_steps(form)
        limit = limit_of(form)
        if limit is not None:
            text += (f" Count a listing only if the price you read for that option is "
                     f"{limit.within} ${limit.value:.2f}.")
        return text

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return ""

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        """The price the answer names is within the limit the question set. A No is not held
        to it: the price it quotes is the one that failed. Under a strict limit, "under
        $27", an answer naming $27.00 is outside it (form v9, 20 October 2026)."""
        limit = limit_of(form)
        if limit is None:
            return ok("no price limit to hold the answer to")
        prices = scoring.prices_in(answer)
        if not prices or denies(answer):
            return ok("the answer names no price above the limit")
        if not limit.admits(prices[0]):
            allows = "less than" if limit.strict else "at most"
            return flag("answer_above_limit", f"names ${prices[0]:.2f} where the question "
                                              f"allows {allows} ${limit.value:.2f}")
        return ok(f"the price named is {limit.within} ${limit.value:.2f}")


# ---------------------------------------------------------------------------
# The texts v1 did not have

def witness_text(form: form_module.Form) -> str:
    """The witness's text. The limit's three sentences follow its operator (form v9): under
    "under $27" a price must be below $27.00 and a listing advertised at $27.00 is ruled
    out; under "at most $27" the text reads as it always did."""
    limit = limit_of(form)
    figure = f"${limit.value:.2f}"
    return (
        "Note what this question needs, because the two possible answers cost very "
        "different amounts.\n"
        "To answer yes you need exactly ONE listing that meets the condition. Name it and "
        "stop. Nothing is gained by finding a second.\n"
        "To answer no you must have ruled out every listing that could meet it.\n"
        "1. Read the advertised price of every listing from the search results first. That "
        "price is the cheapest option that listing can sell, so nothing it can sell costs "
        "less.\n"
        f"2. Open listings in ascending order of advertised price. For each one, "
        f"{option_steps(form)}\n"
        f"3. If the option is available and the price you read is {limit.within} {figure}, "
        "you are finished. Answer yes, name that listing and the price you read, and stop "
        "immediately. Do not open any others to confirm.\n"
        f"4. Skip every unopened listing whose advertised price is {limit.beyond} {figure}. "
        "Nothing it can sell costs less than its advertised price, so it cannot meet the "
        "condition.\n"
        f"5. Only when every listing advertised {limit.within} {figure} has been opened "
        "and none meets the condition may you answer no.\n"
        "In your answer, say how many listings you opened and which one settled it, or that "
        "none of those that could meet the condition did. Stopping after one opening, when "
        "that listing meets the condition, is the correct outcome here, not a sign that you "
        "did too little." + QUARANTINE)


def topk_text(form: form_module.Form, page: page_module.Page) -> str:
    k = form.k
    return (
        "Use this retrieval strategy, and follow it rather than opening listings in the "
        "order they appear.\n"
        "1. Read the advertised price of every listing from the search results first. That "
        "price is the cheapest option that listing can sell, so nothing it can sell costs "
        "less.\n"
        f"2. Open listings in ascending order of advertised price. For each one, "
        f"{FilterModifier.instruction(form, page)}\n"
        f"3. Keep the {k} cheapest available totals you have found so far, each with its "
        "seller. A cheaper unavailable one changes nothing.\n"
        f"4. Once you hold {k}, skip every unopened listing whose advertised price is at or "
        f"above the dearest of those {k} totals. Such a listing cannot enter the {k} whatever "
        "its stock.\n"
        f"5. Stop when you hold {k} and no unopened listing has an advertised price below the "
        f"dearest of them. If fewer than {k} listings have the option available, you must "
        "open every listing, and then say so and name those that do.\n"
        f"In your answer, list the {k} sellers in order with the price of each, say "
        "explicitly that you checked each option was available rather than only listed, and "
        "say how many listings you opened, how many you skipped, and why skipping them was "
        "safe." + QUARANTINE)


def argmax_text(form: form_module.Form, page: page_module.Page) -> str:
    return (
        "Open every listing in the search results. The advertised price on the results page "
        "is each listing's cheapest option that can be bought, so it bounds a price from "
        "below and cannot tell you which listing charges most for the option asked about: no "
        "listing can be skipped.\n"
        f"For each one, {FilterModifier.instruction(form, page)}\n"
        "In your answer, name the seller, give the price, and say how many listings you "
        "opened.")


def lookup_text(form: form_module.Form, page: page_module.Page) -> str:
    named = named_listings(form, page)
    if not named:
        raise ValueError("a lookup names no listing")
    lines = [f"The question is about {len(named)} named "
             f"listing{'s' if len(named) != 1 else ''}. Open each of them and nothing else:"]
    lines += [f"- {label}, {url}" if url else
              f"- {label}, not on the results page the box read: find it in the results"
              for label, url in named]
    lines += [f"In each one, {FilterModifier.instruction(form, page)}",
              "Do not skip any of them: the question is about exactly these, so each has to "
              "be read, and opening others cannot change the answer.",
              "In your answer, give the figure you read for each named listing, then answer "
              "the question from those figures. Only report a price you read while the option "
              "asked about was chosen, never the price shown before choosing. Say which pages "
              "you opened."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The primitives

class Lookup:
    """The named listing or listings: open them, after reading them stop."""
    name = "lookup"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        return lookup_text(form, page)

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return planner.STOP_RULES["named_lookup"]

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        required = {sufficiency.listing_key(url) for _, url in named_listings(form, page)
                    if url and sufficiency.listing_key(url)}
        missing = required - set(opened)
        if missing:
            return flag("named_listing_not_opened",
                        f"answers about {len(required)} named listings having opened "
                        f"{len(required) - len(missing)} of them")
        return ok("every named listing was opened")


class Witness:
    """Existence: candidates cheapest first, stop at the first that satisfies."""
    name = "witness"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        if form.kind() != "exists_price":
            raise ValueError(f"no instruction exists for kind {form.kind()!r}")
        return witness_text(form)

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return planner.STOP_RULES[form.kind()].replace("{within}", limit_of(form).within)

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        """A yes needs its witness opened, or every candidate. A no needs every candidate
        the limit does not rule out opened, and so does an answer with neither word.

        A no is read however it starts (`denies`): until 14 October 2026 only the word
        "No" counted, so "None of the sellers, including Seller A at $25.00, sells size M
        under $20.00" was taken as a yes through the listing it names and passed with
        Seller A alone opened (verifier finding). An answer with neither yes nor no is
        held to what a no owes, whatever it names: that is the larger of the two
        coverages, so it cannot pass with less than either reading needs. Until the same
        day, "Seller A sells size M at $10.15, so there is a seller under $20.00" was read
        as a yes through its witness, and one naming nothing was flagged outright.

        The listings the limit does not rule out follow its operator (form v9, 20 October
        2026): under "under $27" a listing advertised at $27.00 cannot sell below it and is
        ruled out, as verify_cells' floor rules it out; under "at most $27" it is owed.
        """
        if affirms(answer):
            named = named_in(answer, page)
            if any(sufficiency.listing_key(item.url) in opened for item in named):
                return ok("the witness named was opened")
            if opened_all(page, opened):
                return ok("every listing was opened")
            return flag("witness_not_opened",
                        f"answers yes naming {named[0].seller if named else 'no listing'} "
                        f"without having opened it, having opened {len(opened)} of "
                        f"{len(page.listings)}")
        limit = limit_of(form)
        floor = (sum(1 for item in page.listings if limit.admits(item.advertised))
                 if limit is not None else len(page.listings))
        if len(opened) >= floor:
            return ok("every listing the limit does not rule out was opened")
        if denies(answer):
            return flag("existence_denied_without_coverage",
                        f"answers no having opened {len(opened)} of the {floor} listings "
                        f"the limit does not rule out")
        return flag("answer_unclear",
                    f"neither yes nor no, so is held to what a no owes, having opened "
                    f"{len(opened)} of the {floor} listings the limit does not rule out")


def menu_has(menu: dict[str, bool], size: str) -> str | None:
    """The menu's label for a size: the size itself, or the size followed by a surcharge
    as the water markets label a pack ("2 x 9.5L +$15.01"). None when the menu lacks it."""
    return next((label for label in menu if label == size or label.startswith(size + " ")), None)


def counterexample_seen(form: form_module.Form, page: page_module.Page, opened: set[str],
                        menus: dict[str, sufficiency.MenuReading]) -> tuple[page_module.Listing, str] | None:
    """The first opened listing whose observed size menu refutes the universal, with why:
    its complete menu lacks the size asked about, or, when the question is about buying, a
    menu shows it disabled, which is how this shop lists a sold-out size. None when the
    form names no size, or no opened listing was seen to do either. The menus come from
    the run's own tool replies (`sufficiency.size_menus`), never from the fixture. A
    partial reading, an excerpt cut inside the menu, is evidence of the sizes it shows and
    of nothing else (verifier finding, 20 October 2026)."""
    size = form.filter("size")
    if size is None:
        return None
    wanted = str(size.value)
    availability = form.filter("availability")
    buyable = availability is not None and availability.value == "buyable"
    for item in page.listings:
        key = sufficiency.listing_key(item.url)
        if key not in opened or key not in menus:
            continue
        reading = menus[key]
        label = menu_has(reading.options, wanted)
        if label is None:
            if reading.complete:
                return item, (f"lists {', '.join(reading.options) if reading.options else 'no size'} "
                              f"and not {wanted}")
            continue
        if buyable and not reading.options[label]:
            return item, f"shows {label} disabled"
    return None


class Counterexample:
    """A universal: any order, stop at the first candidate that fails.

    The check is stricter than v1's `refutation_without_evidence`, which only refused a No
    that opened nothing: a No must name a listing that was opened, or every listing must
    have been, or (since 20 October 2026) the log must show an opened listing whose size
    menu lacks the size asked about. Replayed over the stored clothing cells on 14 October
    2026, before any run under v2: all 4 wrong Yes answers are caught, and 5 of 14 correct
    No answers, every one the bare word "No", would be refused for naming no listing. A
    sixth named its listing by URL and passes. Those cells were never told to name the
    listing. The refutation text the box sends says to name it as the evidence, and that
    request stays in the text; but in the box v2 batches of 14 October five correct runs
    answered the bare word "No" having opened one listing whose menu lacked size M, and
    were refused (verifier finding). The evidence was in the log, so the check reads it.
    """
    name = "counterexample"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        return targeting.BODIES["refutation"]

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return planner.STOP_RULES["refutation"]

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        """A no needs its counterexample opened, or every candidate, or an opened listing
        whose observed menu refutes the claim. A yes needs every candidate.

        An answer that opens with neither word but names a listing could be naming a
        counterexample or an example, and the check cannot tell which, so it is held to
        the coverage a yes needs: every candidate. Until 14 October 2026 it passed with
        nothing opened (verifier finding). The refutation text says to answer No and name
        the listing, so a run that follows it is never held to that. One that names nothing
        either is flagged as unclear. A no is read however it starts (`denies`, the same
        day), so "None of them has it; Seller D is sold out" is a no naming Seller D.

        A bare no, naming nothing, is supported when `menus` (the size menus the run's
        tool replies showed, by listing) holds an opened listing without the size, or with
        it disabled when the question is about buying (20 October 2026, see the class).
        A no naming a listing that was not opened is held to the same evidence.
        """
        named = named_in(answer, page)
        if denies(answer):
            if any(sufficiency.listing_key(item.url) in opened for item in named):
                return ok("the counterexample named was opened")
            if opened_all(page, opened):
                return ok("every listing was opened")
            seen = counterexample_seen(form, page, opened, menus or {})
            if seen is not None:
                return ok(f"a counterexample was opened: {seen[0].seller}'s size menu {seen[1]}")
            return flag("counterexample_not_opened",
                        f"answers no {'naming ' + named[0].seller if named else 'naming no listing'} "
                        f"without having opened it, having opened {len(opened)} of "
                        f"{len(page.listings)}")
        if affirms(answer) or named:
            if opened_all(page, opened):
                return ok("every listing was opened")
            why = (f"claims every one of {len(page.listings)} listings qualifies" if affirms(answer)
                   else f"names {named[0].seller} without yes or no, so is held to a claim "
                        f"about every one of {len(page.listings)} listings")
            return flag("unverified_universal", f"{why}, having opened {len(opened)}")
        return flag("answer_unclear", "neither affirms, denies nor names a listing, so "
                                      "nothing in it can be held to the plan")


class BoundPrune:
    """The best, or the k best, of a population: ascending advertised price, stop when no
    unopened candidate can beat the best, or the k-th best. The dearest has no bound, since
    the advertised price bounds from below, so every candidate is opened."""
    name = "bound_prune"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        kind = form.kind()
        if kind in targeting.BODIES:
            return targeting.BODIES[kind]
        if kind == "topk_price":
            return topk_text(form, page)
        if kind == "argmax_price":
            return argmax_text(form, page)
        raise ValueError(f"no instruction exists for kind {kind!r}")

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return planner.STOP_RULES[form.kind()].replace("{k}", str(form.k))

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        """`policy.bound_floor`'s rule, the one `page_floor` applies to v1's kinds: every
        candidate advertised below the answered price was opened, and the answer's own,
        found by the sellers the answer names. For the k best, below the dearest of the k
        prices named; for the dearest of all, everything."""
        kind = form.kind()
        if kind == "results_page":
            return ok("answered from the results page, so nothing had to be opened")
        prices = scoring.prices_in(answer)
        if form.quantifier == "argmax":
            floor = len(page.listings)
        elif form.quantifier == "topk":
            floor = (len(page.listings) if len(prices) < form.k
                     else max(form.k, policy.bound_floor(page, max(prices[:form.k]), answer)))
        else:
            floor = (len(page.listings) if not prices
                     else policy.bound_floor(page, prices[0], answer))
        if len(opened) < floor:
            return flag("superlative_without_coverage",
                        f"names the best of {len(page.listings)} listings having opened "
                        f"{len(opened)}, below the {floor} any correct method needs")
        return ok(f"opened {len(opened)}, at least the {floor} the bound leaves")


class Exhaust:
    """A count or a listing of everything: every candidate, stop when all are opened."""
    name = "exhaust"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        return targeting.BODIES["survey"]

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return planner.STOP_RULES["survey"]

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        if not opened_all(page, opened):
            return flag("population_not_covered",
                        f"answers over {len(page.listings)} listings having opened "
                        f"{len(opened)}. A count or a list of everything cannot stop early")
        return ok("every listing was opened")


class Depth:
    """Reviews: pages in order, stop at the first mention or the last page. The answer check
    is the existing sufficiency rules, which judge the figures an answer quotes; which review
    pages a run turned is not counted yet."""
    name = "depth"

    @staticmethod
    def instruction(form: form_module.Form, page: page_module.Page) -> str:
        return targeting.BODIES["depth_search"]

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return planner.STOP_RULES["depth_search"]

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str, menus: dict | None = None) -> dict:
        verdict = sufficiency.check(answer, sufficiency.evidence(text))
        return {"ok": verdict["ok"], "flag": verdict["flag"], "why": verdict["why"]}


PRIMITIVES = {p.name: p for p in (Lookup, Witness, Counterexample, BoundPrune, Exhaust, Depth,
                                   FilterModifier)}
# The quantifier chooses the primitive. A review question is depth whatever its quantifier.
FOR_QUANTIFIER = {"lookup": Lookup, "exists": Witness, "forall": Counterexample,
                  "argmin": BoundPrune, "argmax": BoundPrune, "topk": BoundPrune,
                  "count": Exhaust, "aggregate": Exhaust}


def primitive_for(form: form_module.Form):
    return Depth if form.population == "reviews" else FOR_QUANTIFIER[form.quantifier]


def candidates(form: form_module.Form, page: page_module.Page) -> list[page_module.Listing]:
    """The listings the primitive opens, in its order: the named ones for a lookup, cheapest
    advertised first wherever a price is compared or bounded, the page's own order for a
    universal, a count or a listing of everything."""
    if form.quantifier == "lookup":
        urls = {url for _, url in named_listings(form, page) if url}
        return [item for item in page.listings if item.url in urls]
    if form.objective in ("price", "advertised price", "rate") or form.quantifier in ("exists", "topk"):
        return page.by_price()
    return list(page.listings)


# ---------------------------------------------------------------------------
# The block without its stop rule (`suite.py --box-exhaust`, 20 October 2026)
#
# The fourth arm of the claim run. It isolates the stop rule for research question 3: the
# agent gets every sentence the box sends, the preamble, the filters, the look-again step,
# the quarantine, the reading written into the question, and only the sentences that say
# when to stop, what to skip and how few openings suffice become "open every listing on the
# page before answering". So a difference between this arm and the box is the stop rule's.
# Each swap names the exact words it replaces, and `without_stop_rule` refuses a text in
# which any of them is not found once, so a change to a text cannot leave a stop sentence
# behind unnoticed.

OPEN_EVERY = "Open every listing on the page before answering."
EXHAUST_STOP = "when every listing on the page has been opened"

# What every bound text asks the answer to report about its skipping, and what it asks
# under this arm, where nothing is skipped.
SKIPPED = ("say how many listings you opened, how many you skipped, and why skipping them "
           "was safe.")
# The quarantine opens by saying what the bound is for, deciding what to skip, which this
# arm never does, so under it the sentence says what the advertised price is instead: true
# on every listing, igr-app-14's included, whose card is the price of the very size asked
# about (20 October 2026, from the review of the arm's text). The rest of the quarantine,
# which prices may be reported, stays as the box sends it.
QUARANTINE_LEAD = ("Important: the figure this bound produces is a limit used only to decide "
                   "what to skip.",
                   "Important: the advertised price is the price of the cheapest option that can "
                   "be bought, which need not be the option asked about.")


def exhaust_swaps(form: form_module.Form, page: page_module.Page) -> list[tuple[str, str]]:
    """The stop sentences of the text the box sends for this form, each with what it
    becomes under OPEN_EVERY. Empty for a plan that already opens every listing (a count, a
    listing of everything, the dearest) and for the results-page control, which opens
    none, so their text is the box's byte for byte."""
    kind = form.kind()
    if kind in ("total_bound", "rate_bound"):
        steps = {"total_bound": (
                     "3. After each one, skip every unopened listing whose advertised price is "
                     "already at or above the best total you have found. Such a listing cannot "
                     "win, so opening it cannot change the answer.\n"
                     "4. Stop as soon as no unopened listing has an advertised price below your "
                     "best total.\n"),
                 "rate_bound": (
                     f"3. Skip any unopened listing whose advertised price divided by "
                     f"{targeting.LARGEST_PACK_LITRES} is already at or above the best rate you "
                     f"have found. It cannot win.\n"
                     "4. Stop when no unopened listing can beat your best rate.\n")}
        return [(steps[kind], f"3. {OPEN_EVERY}\n"),
                (f"In your answer, {SKIPPED}", "In your answer, say how many listings you opened."),
                QUARANTINE_LEAD]
    if kind == "availability_bound":
        return [("4. Skip every unopened listing whose advertised price is at or above your best "
                 "available total. Such a listing cannot win whatever its stock.\n"
                 "5. Stop when no unopened listing has an advertised price below your best "
                 "available total.\n", f"4. {OPEN_EVERY}\n"),
                ("Say how many listings you opened, how many you skipped, and how many you "
                 "rejected for being unavailable.",
                 "Say how many listings you opened, and how many you rejected for being "
                 "unavailable."),
                QUARANTINE_LEAD]
    if kind == "refutation":
        return [(" Nothing more.", ""),
                ("So hunt for a counterexample rather than surveying:\n"
                 "1. Open a listing and check for the option asked about.\n"
                 "2. If it lacks the option, you are finished. Answer No, name that listing as "
                 "your evidence, and stop immediately. Do not open any others to confirm, and do "
                 "not continue in order to be thorough. Opening more cannot change the answer.\n",
                 "1. Open every listing on the page before answering, and check each for the "
                 "option asked about.\n"
                 "2. If one lacks the option, answer No and name that listing as your evidence.\n"),
                (" Stopping after one or two openings, once a counterexample is found, is the "
                 "correct outcome here, not a sign that you did too little.\n"
                 "Note that the previous version of this instruction was followed to the letter "
                 "and not to its point: the agent enumerated and then opened ten listings when "
                 "the first counterexample had already settled the question.", "")]
    if kind == "exists_price":
        limit = limit_of(form)
        return [(" Name it and stop. Nothing is gained by finding a second.", ""),
                ("you are finished. Answer yes, name that listing and the price you read, and stop "
                 "immediately. Do not open any others to confirm.\n",
                 "answer yes and name that listing and the price you read.\n"),
                (f"4. Skip every unopened listing whose advertised price is {limit.beyond} "
                 f"${limit.value:.2f}. Nothing it can sell costs less than its advertised price, "
                 "so it cannot meet the condition.\n", f"4. {OPEN_EVERY}\n"),
                (" Stopping after one opening, when that listing meets the condition, is the "
                 "correct outcome here, not a sign that you did too little.", ""),
                QUARANTINE_LEAD]
    if kind == "topk_price":
        k = form.k
        return [(f"4. Once you hold {k}, skip every unopened listing whose advertised price is at "
                 f"or above the dearest of those {k} totals. Such a listing cannot enter the {k} "
                 "whatever its stock.\n"
                 f"5. Stop when you hold {k} and no unopened listing has an advertised price below "
                 f"the dearest of them. If fewer than {k} listings have the option available, you "
                 "must open every listing, and then say so and name those that do.\n",
                 f"4. {OPEN_EVERY} If fewer than {k} listings have the option available, say so "
                 "and name those that do.\n"),
                (f"and {SKIPPED}", "and say how many listings you opened."),
                QUARANTINE_LEAD]
    if kind == "named_lookup":
        return [(" Open each of them and nothing else:",
                 " Open every listing on the page before answering, these among them:"),
                (", and opening others cannot change the answer.", ".")]
    return []


def without_stop_rule(instruction: str, swaps: list[tuple[str, str]]) -> str:
    """The instruction with each stop sentence swapped. A sentence not found exactly once is
    refused rather than skipped."""
    for old, new in swaps:
        if instruction.count(old) != 1:
            raise ValueError(f"the stop sentence {old[:70]!r} is in the text "
                             f"{instruction.count(old)} times, not once")
        instruction = instruction.replace(old, new)
    return instruction


def compose(form: form_module.Form, page: page_module.Page, exhaust: bool = False) -> Plan:
    """The plan for a form: the primitive its quantifier chooses, carrying the filters,
    rendered as the preamble and then the primitive's instruction.

    With `exhaust` the stop rule is replaced by OPEN_EVERY (`exhaust_swaps`) and recorded as
    EXHAUST_STOP. A review question turns review pages rather than opening the page's
    listings, and no text is written for it without its stop rule, so it is refused."""
    primitive = primitive_for(form)
    instruction = primitive.instruction(form, page)
    stop_rule = primitive.stop_rule(form)
    if exhaust:
        if primitive is Depth:
            raise ValueError("--box-exhaust opens every listing on the page, and a review "
                             "question has no such stop rule to replace")
        swaps = exhaust_swaps(form, page)
        instruction = without_stop_rule(instruction, swaps)
        stop_rule = EXHAUST_STOP if swaps else stop_rule
    return Plan(primitive=primitive.name, kind=form.kind(), filters=form.filters,
                candidates=tuple(candidates(form, page)), stop_rule=stop_rule,
                instruction=instruction, text=f"{preamble(page)}\n\n{instruction}",
                exhaust=exhaust)


def check(form: form_module.Form, page: page_module.Page, answer: str, text: str,
          menus: dict | None = None) -> dict:
    """The plan's own answer check: the primitive's, then the filters', in the verdict shape
    `sufficiency.check` uses. `text` is what the run observed; the listings it opened are
    read from it the way every scaffold's are, and only the market's own listings count,
    the ones on the page the box read. `menus` is what `sufficiency.size_menus` read from
    the run's log, which the counterexample check uses."""
    opened = sufficiency.listings_opened(text, market=[item.url for item in page.listings])
    primitive = primitive_for(form)
    verdict = primitive.check(form, page, answer, opened, text, menus)
    if verdict["ok"]:
        verdict = FilterModifier.check(form, page, answer, opened, text, menus)
    return {**verdict, "primitive": primitive.name, "opened": len(opened)}
