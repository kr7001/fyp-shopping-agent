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
VERSION = 1

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

    def record(self) -> dict:
        return {"primitives_version": VERSION, "primitive": self.primitive, "kind": self.kind,
                "stop_rule": self.stop_rule, "filters": [f.record() for f in self.filters],
                "candidates": [{"seller": c.seller, "url": c.url} for c in self.candidates]}


# ---------------------------------------------------------------------------
# Verdicts, and what the answer and the page say

def ok(why: str) -> dict:
    return {"ok": True, "flag": None, "why": why}


def flag(name: str, why: str) -> dict:
    return {"ok": False, "flag": name, "why": why}


def affirms(answer: str) -> bool:
    return bool(sufficiency.AFFIRMS.match(answer or ""))


def denies(answer: str) -> bool:
    return bool(sufficiency.DENIES.match(answer or ""))


def named_in(answer: str, page: page_module.Page) -> list[page_module.Listing]:
    """The page's listings the answer names, by seller or by the last part of the URL. A
    stored answer on 18 September 2026 named its counterexample as "(igr-app-09.html)"."""
    low = (answer or "").lower()
    return [item for item in page.listings
            if item.seller.lower() in low or item.url.rsplit("/", 1)[-1].lower() in low]


def opened_all(page: page_module.Page, opened: set[str]) -> bool:
    return len(opened) >= len(page.listings)


def ceiling_of(form: form_module.Form) -> float | None:
    limit = form.filter("price")
    return float(limit.value) if limit is not None and limit.op == "<=" else None


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
    """Choose the option and look again, then check it can be bought. The same facts the v7
    availability strategy states, in the same words, since they were checked on the shop."""
    steps = [f"choose {option_phrase(form)}, then look at the page again and read the price it "
             "now shows. The price a listing shows before you choose is its cheapest option, "
             "not the one asked about, and the reply to choosing an option does not show the "
             "new price."]
    availability = form.filter("availability")
    if availability is not None and availability.value == "buyable":
        steps.append("Then check whether that option can actually be bought. An option can be "
                     "listed and still be unavailable, in which case it is shown as disabled or "
                     "greyed out and cannot be chosen, so it has no price you can use.")
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
        limit = ceiling_of(form)
        if limit is not None:
            text += (f" Count a listing only if the price you read for that option is at or "
                     f"below ${limit:.2f}.")
        return text

    @staticmethod
    def stop_rule(form: form_module.Form) -> str:
        return ""

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str) -> dict:
        """The price the answer names is within the limit the question set. A No is not held
        to it: the price it quotes is the one that failed."""
        limit = ceiling_of(form)
        if limit is None:
            return ok("no price limit to hold the answer to")
        prices = scoring.prices_in(answer)
        if not prices or denies(answer):
            return ok("the answer names no price above the limit")
        if prices[0] > limit + 0.005:
            return flag("answer_above_limit", f"names ${prices[0]:.2f} where the question "
                                              f"allows at most ${limit:.2f}")
        return ok(f"the price named is at or below ${limit:.2f}")


# ---------------------------------------------------------------------------
# The texts v1 did not have

def witness_text(form: form_module.Form) -> str:
    limit = ceiling_of(form)
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
        f"3. If the option is available and the price you read is at or below ${limit:.2f}, "
        "you are finished. Answer yes, name that listing and the price you read, and stop "
        "immediately. Do not open any others to confirm.\n"
        f"4. Skip every unopened listing whose advertised price is above ${limit:.2f}. "
        "Nothing it can sell costs less than its advertised price, so it cannot meet the "
        "condition.\n"
        f"5. Only when every listing advertised at or below ${limit:.2f} has been opened "
        "and none meets the condition may you answer no.\n"
        "In your answer, say how many listings you opened and which one settled it, or that "
        "none of those that could meet the condition did. Stopping after one opening is the "
        "correct outcome here, not a sign that you did too little." + QUARANTINE)


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
        "is each listing's cheapest option, so it bounds a price from below and cannot tell "
        "you which listing charges most for the option asked about: no listing can be "
        "skipped.\n"
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
              text: str) -> dict:
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
        return planner.STOP_RULES[form.kind()]

    @staticmethod
    def check(form: form_module.Form, page: page_module.Page, answer: str, opened: set[str],
              text: str) -> dict:
        """A yes needs its witness opened, or every candidate. A no needs every candidate
        the limit does not rule out opened."""
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
        if denies(answer):
            limit = ceiling_of(form)
            floor = (policy.at_or_below(page, limit, at_least=0) if limit is not None
                     else len(page.listings))
            if len(opened) < floor:
                return flag("existence_denied_without_coverage",
                            f"answers no having opened {len(opened)} of the {floor} listings "
                            f"the limit does not rule out")
            return ok("every listing the limit does not rule out was opened")
        return ok("neither a yes nor a no to hold to a witness")


class Counterexample:
    """A universal: any order, stop at the first candidate that fails.

    The check is stricter than v1's `refutation_without_evidence`, which only refused a No
    that opened nothing: a No must name a listing that was opened, or every listing must
    have been. Replayed over the stored clothing cells on 14 October 2026, before any run
    under v2: all 4 wrong Yes answers are caught, and 5 of 14 correct No answers, every one
    the bare word "No", would be refused for naming no listing. A sixth named its listing
    by URL and passes. Those cells were never told to name the listing. The refutation text
    the box sends says to name it as the evidence, so a run under the box that does not is
    refused rather than believed.
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
              text: str) -> dict:
        if affirms(answer) and not opened_all(page, opened):
            return flag("unverified_universal",
                        f"claims every one of {len(page.listings)} listings qualifies, "
                        f"having opened {len(opened)}")
        if denies(answer):
            named = named_in(answer, page)
            if any(sufficiency.listing_key(item.url) in opened for item in named):
                return ok("the counterexample named was opened")
            if opened_all(page, opened):
                return ok("every listing was opened")
            return flag("counterexample_not_opened",
                        f"answers no {'naming ' + named[0].seller if named else 'naming no listing'} "
                        f"without having opened it, having opened {len(opened)} of "
                        f"{len(page.listings)}")
        return ok("neither a yes nor a no to hold to a counterexample")


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
              text: str) -> dict:
        """`policy.page_floor`'s rule: every candidate advertised at or below the answered
        price was opened. For the k best, at or below the dearest of the k prices named;
        for the dearest of all, everything."""
        kind = form.kind()
        if kind == "results_page":
            return ok("answered from the results page, so nothing had to be opened")
        prices = scoring.prices_in(answer)
        if form.quantifier == "argmax":
            floor = len(page.listings)
        elif form.quantifier == "topk":
            floor = (len(page.listings) if len(prices) < form.k
                     else max(form.k, policy.at_or_below(page, max(prices[:form.k]))))
        else:
            floor = len(page.listings) if not prices else policy.at_or_below(page, prices[0])
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
              text: str) -> dict:
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
              text: str) -> dict:
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


def compose(form: form_module.Form, page: page_module.Page) -> Plan:
    """The plan for a form: the primitive its quantifier chooses, carrying the filters,
    rendered as the preamble and then the primitive's instruction."""
    primitive = primitive_for(form)
    instruction = primitive.instruction(form, page)
    return Plan(primitive=primitive.name, kind=form.kind(), filters=form.filters,
                candidates=tuple(candidates(form, page)), stop_rule=primitive.stop_rule(form),
                instruction=instruction, text=f"{preamble(page)}\n\n{instruction}")


def check(form: form_module.Form, page: page_module.Page, answer: str, text: str) -> dict:
    """The plan's own answer check: the primitive's, then the filters', in the verdict shape
    `sufficiency.check` uses. `text` is what the run observed; the listings it opened are
    read from it the way every scaffold's are."""
    opened = sufficiency.listings_opened(text)
    primitive = primitive_for(form)
    verdict = primitive.check(form, page, answer, opened, text)
    if verdict["ok"]:
        verdict = FilterModifier.check(form, page, answer, opened, text)
    return {**verdict, "primitive": primitive.name, "opened": len(opened)}
