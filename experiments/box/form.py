#!/usr/bin/env python3
"""The logical form of a shopping question: what is asked, over what, under which conditions.

Box v1 chose one of seven strategies by keyword and sent that strategy's text. That covers
the questions the project had met and nothing past them. The form is the record those
strategies approximated: a quantifier (the best of a market, one witness, every member, a
count), the attribute compared, the conditions a candidate must meet, the population ranged
over, and what the question leaves unsaid. The plan is composed from it (`primitives.py`),
the soundness check reads it (`verify`), and the run record stores it, so every plan can be
reproduced and a verifier can see what the box believed.

Two parsers produce it. `from_rules` is deterministic, built on `targeting.py`'s patterns so
every question the project has run keeps the kind v1 gave it, and extended for the forms the
research census found v1 lacked: existence under a price limit, the k cheapest, a comparison
of named listings, a filtered cheapest, a lookup on one listing. `from_model` asks a model
through a `call` the caller injects, so this module does no I/O and the tests use a fake. A
real call goes through the spend guard (`runners/parse_probe.py`, `runners/suite.py
--parser model`). Since form v10 (22 October 2026) a form may also be negated, a universal
the question asks to break, carry the words a model reads two ways, and say which prompt
produced it; the box normalises a model's form and checks it before using it
(`normalise.py`).

It reads the question, and the page only for the sellers named on it. Never a task file's
answers, a market's instance record or a fixture: `tests/test_box.py` checks that.

    python experiments/box/form.py "Is there any seller under $20 for size M?"
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/, runners/, analysis/, water/ on the path)
import ambiguity
import page as page_module
import planner
import sufficiency
import targeting

# Bumped when the vocabulary or a rule changes what a question parses to. Runs made under
# different versions are different boxes and are never pooled.
#
#   1  14 October 2026. The record, the rules parser, the five-property check and the
#      model parser's prompt
#   2  14 October 2026. A count before "sellers" or "listings" with "cheapest" anywhere is
#      a top-k, so "which three sellers offer size M cheapest" keeps its k
#   3  14 October 2026. A question with no recognised shape and no shopping signal parses
#      to the quantifier "unknown", which the box bypasses. One with a signal keeps the
#      survey fallback and says so in its evidence
#   4  14 October 2026. "sell", "sells", "sold" and "selling" are market words, so "Who
#      sells the softest tee?" is a fallback rather than a bypass
#   5  20 October 2026. A superlative or comparative whose attribute the shop does not
#      show names that attribute in the form (`graded_unknown`): as the objective when the
#      question has no other shape, as a filter when it has one. Property 5 then refuses
#      the question whatever the word, so "Who sells the softest tee?" is refused rather
#      than planned by the fallback. The fallback is only for a shopping question with no
#      shape whose attributes are all shown
#   6  20 October 2026, from the verifier's probe of the rule: "availability" is a shown
#      attribute's word, "the widest range of sizes" and "most sizes" rank by size, and
#      "the top tee" is read like "the best tee" while "the top 3" stays a count
#   7  20 October 2026. "best price", "top price" and "best deal" are the cheapest in shop
#      vocabulary (`BEST_PRICE`), so "Which seller has the best price for size M?" is the
#      best of the market by price rather than the survey fallback
#   8  20 October 2026. "top price" is dropped from `BEST_PRICE` (verifier): it can mean
#      the highest, so it asks or is refused like any graded word, never the cheapest
#   9  20 October 2026. "under", "below", "less than" and "cheaper than" set a strict
#      limit, price < L, where "at most", "no more than", "not more than", "up to",
#      "within" and "$L or less" keep price <= L (`CEILING`, the op "<"). Until now every
#      one read as at or below, while the coverage floor in verify_cells and the
#      generator's witnesses read "under $27" as strictly below (verifier finding)
#  10  22 October 2026, the model's front door. Three fields join the record: `negated`, a
#      universal the question asks to break ("is there a listing without size M", kind
#      "negated_refutation"), `ambiguities`, a word a model reads two ways, and
#      `prompt_version`, which prompt produced a model's form. The model parser's prompt
#      is version 2 (`PROMPT_VERSION`). The rules parse every question as they did: they
#      never set the new fields
#  11  22 October 2026, from the verifier's audit of v10. A filter's value is a word or a
#      number, and the values of "in" are words; a model's null, dict or nested list is
#      refused rather than printed into a word, and so is a list of filters that is not a
#      list. The rules write only such values, so they parse every question as they did
#  12  23 October 2026, from the verifier's fairness audit of d357c72. A generic superlative
#      whose attribute the shop does not show is named by the word beside it that names one,
#      "tastes best" by taste (`NAMED_BESIDE`), where the refusal said "what 'best' ranks
#      by"; the question is refused as before. The reading a user chose is read back from a
#      pack's sentences as from a size's (`PACK_READING_MARKS`)
#  13  23 October 2026, from the verifier's FAIL at cce9ab0, before DeepSeek first reads a
#      question. A model's reply is read as text, None as nothing and a list of content parts
#      by its text parts, and any other content refused with its type, never a TypeError
#      (`reply_text`). When the first '{' to the last '}' is not one form, each object in the
#      reply is tried and the last that is a form taken (`last_form`), for reasoning with
#      braces in it. Every reply the first attempt parsed parses to the same form
#  14  24 October 2026, box v19, for the second claim run's design B and its two declines.
#      The rules name two attributes the shop does not show where until now they planned a
#      survey of every listing (LESSONS 35): fit, which size suits the shopper ("Will size M
#      or size L fit me better?", "which size should I buy", "between a medium and a large",
#      "runs small"), and stock quantity, read in more words ("the fewest units of it left",
#      "running out", "sell out", "low stock", "only 2 left"). The decline says, for fit,
#      that the shop cannot know the shopper's size, and for stock, that the shop does not
#      display stock counts and a label's claim of one is no checked count (`refusal`)
#  15  24 October 2026, the verifier's audit at cd49128 (FAIL, blocker 1). Two sentences of
#      every refusal were false of the design B market. "On a review page, the text, rating
#      and page of each review" is gone: every one of its 45 listings says "Be the first to
#      review this product", and the box reads no review page. And stock is no longer said
#      to be unanswerable: the cart refuses a quantity above stock (checked live), so a count
#      could be bounded by probing a cart. A decline on stock says the shop displays no stock
#      counts, that finding one would mean probing a cart, which is out of scope, and that a
#      label's claim of one is no checked count; stock is not named among what the shop "does
#      not show". Every other refusal reads as before, less the review sentence
VERSION = 15

# The model parser's prompt, recorded in every form a model proposes. Runs made under
# different prompts are different parsers and are never pooled.
#
#   1  14 October 2026. The shop, the attributes it shows, the five properties and the
#      schema. The census and the paraphrase probe of 20 October ran under it
#   2  22 October 2026. Adds the shop's size words, the kinds of question that have a
#      plan, how to fill each field, the two new fields and one worked example for each
#      kind. The examples are written from the six clothing templates and the shapes added
#      since, about a made-up brand, and copy no question of tasks/paraphrases_v1.json,
#      whose failures named what to teach: medium kept as a size, title filters restating
#      the brand, the population "listing" for a results page, a negation read as an
#      existence, and "affordable" made a filter (22 October 2026)
#   3  23 October 2026, from the verifier's fairness audit of d357c72. Version 2 with two
#      sentences of its context made true of the shop (`CONTEXT_V3`): a search lists one
#      product or several, and a listing has reviews only when it has any. Version 2 is kept
#      byte for byte (tests/test_model_parser.py pins its sha256)
#   4  24 October 2026, box v19, for design B, written on the practice questions of
#      tasks/paraphrases_dev2.json and paraphrases_v1.json alone. Version 3 with: a size's
#      label can carry the seller's text and its claim is not checked (`CONTEXT_V4`); fit
#      and stock counts among what the shop does not show (`SHOWN_V4`); the six sizes XS to
#      XXL (`SIZES_V4`); how to fill a promotion's claim, a listed price, fit and stock left
#      (`FILLING_V4`); and four worked examples more (`EXAMPLES_V4`). The reply's format is
#      version 2's. Version 3 is kept byte for byte (tests/test_design_b.py pins its sha256)
PROMPT_VERSION = 4

# The vocabulary. A form outside it is refused when it is built, so a model's reply cannot
# smuggle in a quantifier nothing knows how to plan. "unknown" is the rules' answer to a
# question that is not about the shop at all (14 October 2026): no primitive plans it, and
# the box hands the question to the agent unchanged.
QUANTIFIERS = ("lookup", "exists", "forall", "argmin", "argmax", "topk", "count", "aggregate",
               "unknown")
POPULATIONS = ("listing", "results", "reviews")
# "advertised price" is the one the results page prints, the cheapest option a listing can
# sell. "price" is the price of the option asked about, shown only after it is chosen. The
# control question compares the first and is answered without opening anything, so the two
# have to be told apart. Any other attribute is "attribute:<name>". "none" goes with the
# quantifier "unknown" and with nothing else.
OBJECTIVES = ("price", "advertised price", "rate", "availability", "size", "mention", "none")
OPS = ("=", "<", "<=", ">=", "in", "contains")
SOURCES = ("rules", "model")

# What an objective needs to read. A rate is a price over a pack size, and a mention is
# found in a review's text.
NEEDS = {"price": ("price",), "advertised price": ("advertised price",),
         "rate": ("price", "size"), "availability": ("availability",), "size": ("size",),
         "mention": ("review text",), "none": ()}

# What a product page of this shop shows, checked on 14 October 2026 against the gated
# Thornwood listings (igr-app-02.html among them): a Size menu filled from the page's
# spConfig (S, M, L, XL), the price of the chosen size written into the price box 60 ms
# after it is chosen (env/gated_theme), and whether a size can be bought, since the
# configurable widget lists a size with no salable product as a disabled option. Not shown:
# delivery time, shipping cost, warranty, stock quantity (the "Only N left" block is an
# unfilled template), a seller rating, a rating summary (printed only for a product with
# reviews, which no generated listing has) and, on the Thornwood listings, any description
# block at all (the Rivenhall ones print a one-line generated note), so none of those is
# an attribute a plan may rely on.
LISTING_PAGE_SHOWS = frozenset({"size", "price", "availability"})
# What a review page shows, checked the same day on /review/product/list/id/230/: the text
# of each review, a rating per review, and the page number, ten reviews to a page.
REVIEW_PAGE_SHOWS = frozenset({"review text", "review rating", "review page"})
# The results page's attributes are whatever `page.py` reads for every card, named here
# the way a question names them.
RESULTS_PAGE_NAMES = {"advertised": "advertised price"}


@dataclasses.dataclass(frozen=True)
class Filter:
    """One condition a candidate must meet: size = M, price <= 20, seller in (A, B)."""
    attribute: str
    op: str
    value: str | float | tuple[str, ...]

    def __post_init__(self):
        if self.op not in OPS:
            raise ValueError(f"filter op {self.op!r} is not one of {OPS}")
        if (self.op == "in") != isinstance(self.value, tuple):
            raise ValueError(f"filter {self.attribute} {self.op}: 'in' takes a tuple of values "
                             f"and nothing else does, got {self.value!r}")
        # A value is a word or a number, and the values of "in" are words (form v11, 22
        # October 2026). Until then a model's null, dict or nested list was turned into its
        # printed form, and "- None, None" reached the agent as a listing (verifier finding).
        # Every value the rules write, and every value in every stored record, is one of these.
        if isinstance(self.value, tuple):
            if not self.value or not all(isinstance(v, str) and v.strip() for v in self.value):
                raise ValueError(f"filter {self.attribute} in: the values are words, got {self.value!r}")
        elif isinstance(self.value, bool) or not isinstance(self.value, (str, int, float)):
            raise ValueError(f"filter {self.attribute} {self.op}: the value is a word or a number, "
                             f"got {self.value!r}")

    def record(self) -> dict:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {"attribute": self.attribute, "op": self.op, "value": value}


@dataclasses.dataclass(frozen=True)
class Ambiguity:
    """A word of the question that a model reads two or more ways, each giving a different
    answer on this shop (form v10, 22 October 2026): the words as the question writes them,
    and each reading in the model's words. The rules never propose one; the box maps the
    readings onto those it knows, or asks with a template that quotes them (`box.decide`)."""
    word: str
    readings: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.word, str) or not self.word.strip():
            raise ValueError(f"an ambiguity names the words it is about, got {self.word!r}")
        if not isinstance(self.readings, tuple) or len(self.readings) < 2 or not all(
                isinstance(reading, str) and reading.strip() for reading in self.readings):
            raise ValueError(f"an ambiguity of {self.word!r} needs two or more readings, each "
                             f"a phrase, got {self.readings!r}")
        if len({reading.strip().lower() for reading in self.readings}) != len(self.readings):
            raise ValueError(f"the readings of {self.word!r} repeat one another: {self.readings!r}")

    def record(self) -> dict:
        return {"word": self.word, "readings": list(self.readings)}


@dataclasses.dataclass(frozen=True)
class Form:
    quantifier: str
    objective: str
    filters: tuple[Filter, ...] = ()
    population: str = "results"
    k: int | None = None                 # for topk
    reading: str | None = None           # which reading of an ambiguous word was chosen
    unknowns: tuple[str, ...] = ()       # what the question leaves unsaid or the page lacks
    source: str = "rules"
    evidence: dict = dataclasses.field(default_factory=dict)   # field -> the words that chose it
    # Form v10, 22 October 2026. Last, so every form built by position builds as before.
    negated: bool = False                # forall only: the question asks whether some listing fails it
    ambiguities: tuple[Ambiguity, ...] = ()   # words a model reads two ways
    prompt_version: int | None = None    # the model prompt that produced it, None for the rules

    def __post_init__(self):
        if self.quantifier not in QUANTIFIERS:
            raise ValueError(f"quantifier {self.quantifier!r} is not one of {QUANTIFIERS}")
        if self.population not in POPULATIONS:
            raise ValueError(f"population {self.population!r} is not one of {POPULATIONS}")
        if self.objective not in OBJECTIVES and not (
                self.objective.startswith("attribute:") and len(self.objective) > len("attribute:")):
            raise ValueError(f"objective {self.objective!r} is not one of {OBJECTIVES} or "
                             f"'attribute:<name>'")
        if (self.quantifier == "topk") != (self.k is not None):
            raise ValueError(f"k is {self.k!r} for quantifier {self.quantifier!r}: topk takes "
                             f"a k and nothing else does")
        if (self.quantifier == "unknown") != (self.objective == "none"):
            raise ValueError(f"objective {self.objective!r} with quantifier {self.quantifier!r}: "
                             f"an unknown question has the objective 'none' and nothing else has")
        if self.k is not None and (not isinstance(self.k, int) or self.k < 1):
            raise ValueError(f"k must be a whole number of at least 1, got {self.k!r}")
        if not all(isinstance(f, Filter) for f in self.filters):
            raise ValueError("filters must be Filter records")
        if self.source not in SOURCES:
            raise ValueError(f"source {self.source!r} is not one of {SOURCES}")
        if not isinstance(self.negated, bool):
            raise ValueError(f"negated is true or false, got {self.negated!r}")
        if self.negated and self.quantifier != "forall":
            raise ValueError(f"negated is for a universal, a question whether some listing fails "
                             f"it, not for quantifier {self.quantifier!r}")
        if not isinstance(self.ambiguities, tuple) or not all(
                isinstance(a, Ambiguity) for a in self.ambiguities):
            raise ValueError("ambiguities must be a tuple of Ambiguity records")
        if self.prompt_version is not None and (isinstance(self.prompt_version, bool) or not isinstance(
                self.prompt_version, int) or self.prompt_version < 1):
            raise ValueError(f"prompt_version is a whole number of at least 1 or None, got "
                             f"{self.prompt_version!r}")

    def filter(self, attribute: str) -> Filter | None:
        return next((f for f in self.filters if f.attribute == attribute), None)

    def kind(self) -> str:
        """The name of the plan this form composes to.

        The seven v1 names keep their meaning, so the planner regression and every run
        recorded under them stay comparable: a universal is "refutation" whatever it
        checks, a count or a listing of everything is "survey", a review question is
        "depth_search". A form v1 had no strategy for gets a new name: "exists_price",
        "topk_price", "named_lookup", "argmax_price". A combination no primitive plans,
        such as an existence question about a rate, gets a name the planner has no row
        for, and `verify` refuses it. An unknown question is "unknown", which no row plans.
        A universal the question asks to break, "is there a listing without size M", is
        "negated_refutation" (form v10): the same hunt for one counterexample, with the
        answer's yes and no the other way round.
        """
        if self.quantifier == "unknown":
            return "unknown"
        if self.population == "reviews":
            return "depth_search"
        if self.quantifier == "lookup":
            return "named_lookup"
        if self.quantifier == "forall":
            return "negated_refutation" if self.negated else "refutation"
        if self.quantifier in ("count", "aggregate"):
            return "survey"
        if self.quantifier == "argmin":
            if self.objective == "advertised price":
                return "results_page"
            if self.objective == "rate":
                return "rate_bound"
            if self.objective == "price":
                return "availability_bound" if self.filter("availability") else "total_bound"
        word = self.objective.removeprefix("attribute:").replace(" ", "_")
        return f"{self.quantifier}_{word}"

    def attributes(self) -> set[str]:
        """Every attribute the form compares or filters on, for the fifth property."""
        needed = NEEDS[self.objective] if self.objective in NEEDS \
            else (self.objective.removeprefix("attribute:"),)
        return set(needed) | {f.attribute for f in self.filters}

    @property
    def fallback(self) -> bool:
        """Whether the rules found a shopping signal but no shape, and fell back to listing
        everything. Recorded in the evidence by `from_rules`, so a record keeps it."""
        return "fallback" in self.evidence

    def record(self) -> dict:
        return {"form_version": VERSION, "kind": self.kind(), "quantifier": self.quantifier,
                "objective": self.objective, "filters": [f.record() for f in self.filters],
                "population": self.population, "k": self.k, "reading": self.reading,
                "unknowns": list(self.unknowns), "source": self.source,
                "evidence": dict(self.evidence), "negated": self.negated,
                "ambiguities": [a.record() for a in self.ambiguities],
                "prompt_version": self.prompt_version}


def from_record(data: dict, source: str) -> Form:
    """A form from its record, or from a model's reply, refused with the field named when a
    value is outside the vocabulary. A record written before form v10 has no `negated`,
    `ambiguities` or `prompt_version`, and reads as a form without them."""
    if not isinstance(data, dict):
        raise ValueError(f"a form is a JSON object, got {type(data).__name__}")
    missing = [key for key in ("quantifier", "objective", "population") if key not in data]
    if missing:
        raise ValueError(f"the form lacks {', '.join(missing)}")
    filters = []
    entries = data.get("filters") or []
    if not isinstance(entries, list):
        raise ValueError(f"filters must be a list, got {entries!r}")
    for entry in entries:
        if not isinstance(entry, dict) or not {"attribute", "op", "value"} <= set(entry):
            raise ValueError(f"a filter needs attribute, op and value, got {entry!r}")
        # A list's members are kept as they are, for `Filter` to refuse any that is not a
        # word, rather than printed into words (form v11).
        value = tuple(entry["value"]) if isinstance(entry["value"], list) else entry["value"]
        filters.append(Filter(str(entry["attribute"]), str(entry["op"]), value))
    k = data.get("k")
    if isinstance(k, float) and k.is_integer():
        k = int(k)
    evidence = data.get("evidence") or {}
    if not isinstance(evidence, dict):
        raise ValueError(f"evidence must map each field to the words that chose it, got {evidence!r}")
    unknowns = data.get("unknowns") or []
    if not isinstance(unknowns, list) or not all(isinstance(u, str) for u in unknowns):
        raise ValueError(f"unknowns must be a list of words, got {unknowns!r}")
    if data.get("reading") is not None and not isinstance(data["reading"], str):
        raise ValueError(f"reading is a word or null, got {data['reading']!r}")
    # A null is read as false, as a missing field is; anything else that is not true or
    # false is refused by the form itself.
    negated = data.get("negated")
    ambiguities = data.get("ambiguities") or []
    if not isinstance(ambiguities, list):
        raise ValueError(f"ambiguities must be a list, got {ambiguities!r}")
    read = []
    for entry in ambiguities:
        if not isinstance(entry, dict) or not {"word", "readings"} <= set(entry) \
                or not isinstance(entry["readings"], list):
            raise ValueError(f"an ambiguity needs a word and a list of readings, got {entry!r}")
        read.append(Ambiguity(entry["word"], tuple(entry["readings"])))
    return Form(quantifier=str(data["quantifier"]), objective=str(data["objective"]),
                filters=tuple(filters), population=str(data["population"]), k=k,
                reading=data.get("reading") or None,
                unknowns=tuple(unknowns), source=source,
                evidence={str(key): str(words) for key, words in evidence.items()},
                negated=False if negated is None else negated, ambiguities=tuple(read),
                prompt_version=data.get("prompt_version"))


# ---------------------------------------------------------------------------
# What the shop shows, and the five properties

def attributes_shown(page: page_module.Page | None = None) -> set[str]:
    """Every attribute a plan may compare or filter on: what the results page the box read
    prints for each listing (the parser's own fields, so a field added to `page.py` is shown
    here too), plus the two short lists above of what a listing page and a review page show.
    """
    listing = type(page.listings[0]) if page is not None and page.listings else page_module.Listing
    results = {RESULTS_PAGE_NAMES.get(f.name, f.name) for f in dataclasses.fields(listing)}
    return results | set(LISTING_PAGE_SHOWS) | set(REVIEW_PAGE_SHOWS)


def not_shown(form: Form, page: page_module.Page | None = None) -> list[str]:
    """Property 5: the attributes the form needs that this shop does not show, in order."""
    missing = form.attributes() - attributes_shown(page)
    # A size in the menu that cannot be bought has no price on this shop: the gated page
    # writes a price only for the chosen size, and a disabled size cannot be chosen. So a
    # price question under the menu reading asks for a figure the page never prints.
    availability = form.filter("availability")
    if availability is not None and availability.value == "listed" and (
            form.objective in ("price", "rate") or form.filter("price") is not None):
        missing.add("the price of a sold-out size")
    return sorted(missing)


# What a decline adds for the two attributes design B's declines ask about (form v14, 24
# October 2026), by the attribute's name, the rules' or a model's. Fit: nothing on the shop
# knows the shopper's size. Stock: no page of the shop displays a stock count, the product
# page's "Only %1 left" block being a template with no threshold set (checked by the verifier
# that day), and design B's labels can claim one ("M - Only 2 left!"), which is no checked
# count. Since form v15 the decline also says a count could only be found by probing a cart,
# which the cart allows (it refuses a quantity above stock: checked live on 24 October 2026, by
# the generator coder, a quantity of 518 against a stock of 18 refused, and then the verifier,
# 19 refused and 18 accepted on IGR-TDV-06 size M) and which is out of scope.
FIT_NAMED = re.compile(r"\bfit", re.IGNORECASE)
STOCK_NAMED = re.compile(r"\bstock\b|\binventor\w*|\bunits?\b|\bleft\b|\bremaining\b", re.IGNORECASE)
REFUSAL_FIT = " The shop cannot know your size, so it cannot say which size will fit you."
REFUSAL_STOCK = (" The shop displays no stock counts; finding one would mean probing a cart, which is "
                 "out of scope, and a size's label that claims one is not a checked count.")


def refusal(missing: list[str]) -> str:
    """What the box says instead of planning: what is missing, and what the shop does show,
    and since form v14 a sentence for fit and one for stock when they are missing. Since form
    v15 stock is not named among what the shop "does not show", since a cart probe could bound
    it (`REFUSAL_STOCK` says so), and nothing is said of review pages, which the box does not
    read and design B's listings do not have (the verifier's audit at cd49128)."""
    stock = [name for name in missing if STOCK_NAMED.search(name)]
    others = [name for name in missing if name not in stock]
    text = (f"The shop does not show {', '.join(others)}, so this question cannot be answered "
            "from it." if others else "This question cannot be answered from what the shop shows.")
    text += (" What it shows: on the results page, each listing's seller, title, URL and "
             "advertised price. On a listing, its size menu, the price of a size once chosen and "
             "whether a size can be bought.")
    if any(FIT_NAMED.search(name) for name in others):
        text += REFUSAL_FIT
    if stock:
        text += REFUSAL_STOCK
    return text


def plan_dict(form: Form) -> dict | None:
    """The planner's plan for this form, assembled from `planner.py`'s tables, which stay the
    one source of truth for the four v1 properties. None when no row plans the form's kind.

    The same shape `planner.plan` builds for a question. Here the kind is the form's rather
    than the keyword classifier's, and `tests/test_form.py` checks the two agree on every
    question v1 classified.
    """
    kind = form.kind()
    if kind not in planner.QUANTIFIERS:
        return None
    return {
        "planner_version": planner.VERSION,
        "strategy_version": targeting.VERSION,
        "kind": kind,
        "quantifier": planner.QUANTIFIERS[kind],
        "population": "every listing in the search results, including later pages",
        "evidence_source": "results page" if kind == "results_page" else "listing pages",
        "enumerate_first": True,
        "bound": planner.BOUNDS[kind],
        "stop_rule": planner.STOP_RULES[kind],
        "evidence_required": planner.EVIDENCE[kind],
        "forbidden_claims": planner.FORBIDDEN_WITH_BOUND if planner.BOUNDS[kind] else [],
    }


def verify(form: Form, page: page_module.Page | None = None) -> list[str]:
    """Why this form must not be planned, empty when it may be.

    The planner's four properties, read from the plan the form composes to, and the fifth:
    every attribute compared or filtered on is one the shop shows. The 18 September probe's
    one unsound plan compared a delivery time the shop does not publish, and only a check
    against the page catches that.

    A negated universal (form v10) is planned only over an option's availability, the one
    thing its counterexample search and its check read: the size menu of each listing
    opened. The rules never negate a form, so for them this never fires.
    """
    plan = plan_dict(form)
    problems = ([f"no plan exists for kind {form.kind()!r}"] if plan is None
                else planner.properties(plan))
    if form.quantifier == "lookup" and not (form.filter("url") or form.filter("seller")):
        problems.append("a lookup names no listing")
    if form.negated and (form.objective != "availability" or form.filter("size") is None):
        problems.append("a negated universal is planned only over the availability of a size "
                        "it names")
    # Property 1 over every results page (box v16, 22 October 2026). The box's enumeration
    # is the pages it read, and a plan lists every listing it holds, so a read that stopped
    # with a later page unread enumerates the population in part. The box reads every page
    # (`page.read`), so this fires only past its page limit, or on a page made by hand.
    if page is not None and page.next_page and form.population == "results":
        problems.append("the population is not enumerated first: the search runs to a "
                        "results page the box did not read")
    problems += [f"the shop does not show {attribute}" for attribute in not_shown(form, page)]
    return problems


# ---------------------------------------------------------------------------
# The rules parser

URL = re.compile(r"https?://\S+")
RESULTS_URL = re.compile(r"catalogsearch")

# The k of a top-k question: "three cheapest", "the cheapest three", "top 3". "three
# listings" is not one, and "cheapest" alone is the best of the market.
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten".split())}
COUNT_WORD = r"(?:two|three|four|five|six|seven|eight|nine|ten|\d{1,2})"
TOPK = re.compile(rf"\b(?:(?P<before>{COUNT_WORD})\s+cheapest|cheapest\s+(?P<after>{COUNT_WORD})"
                  rf"|top\s+(?P<top>{COUNT_WORD}))\b", re.IGNORECASE)
# "Which three sellers offer size M cheapest?" parsed as the single cheapest until
# 14 October 2026 (verifier finding): the count sits before "sellers" or "listings" and
# the superlative anywhere else, so this is read only when `targeting.CHEAPEST` matches
# too. "Of the three listings, which is cheapest" names a population, not a k, so a count
# after "the", "these" or "those" is not one.
TOPK_COUNT = re.compile(rf"\b(?<!\bthe\s)(?<!\bthese\s)(?<!\bthose\s)(?P<count>{COUNT_WORD})"
                        r"\s+(?:sellers?|listings?)\b", re.IGNORECASE)
# An existence question. "anyone" in "the lowest price anyone charges" is a superlative, so
# `targeting.CHEAPEST` is checked first and wins.
EXISTS = re.compile(r"\b(?:is|are)\s+there\s+(?:any|a|an|one)\b"
                    r"|\b(?:does|do|is|are|can|could|will|would)\s+any(?:one|body)?\b"
                    r"|\banyone\b", re.IGNORECASE)
# A price limit, and whether the figure itself is allowed (form v9, 20 October 2026).
# "under $20", "below", "less than" and "cheaper than" are strict: a price must be below
# 20 (`strict`, the op "<"). "at most $20", "no more than", "not more than", "up to" and
# "within" allow 20 itself (`upto`), and so does "$20 or less", "or under", "or below" and
# "or cheaper", which name the figure as one of the prices allowed (`orless`); those are
# the op "<=". Until v9 all of them read as at or below.
CEILING = re.compile(r"\b(?:under|below|less than|cheaper than)\s*\$?\s*"
                     r"(?P<strict>\d+(?:\.\d{1,2})?)\b"
                     r"|\b(?:at most|no more than|not more than|up to|within)\s*\$?\s*"
                     r"(?P<upto>\d+(?:\.\d{1,2})?)\b"
                     r"|\$?(?P<orless>\d+(?:\.\d{1,2})?)\s+or\s+(?:less|under|below|cheaper)\b",
                     re.IGNORECASE)
RATING = re.compile(r"\brat(?:ing|ed)\s+(?:of\s+)?(?:at\s+least|above|over|no\s+less\s+than)\s+"
                    r"(?P<a>\d(?:\.\d)?)\b"
                    r"|\brated\s+(?P<b>\d(?:\.\d)?)\s+or\s+(?:higher|more|better|above)\b"
                    r"|\b(?P<c>\d(?:\.\d)?)\s+stars?\s+(?:or\s+(?:more|higher|better|above)|and\s+up)\b"
                    r"|\bat\s+least\s+(?P<d>\d(?:\.\d)?)\s+stars?\b", re.IGNORECASE)
COLOUR = re.compile(r"\bin\s+(white|black|blue|red|green|grey|gray|navy|yellow|pink|purple|"
                    r"orange|brown|beige|cream)\b", re.IGNORECASE)
FREE_SHIPPING = re.compile(r"\bfree\s+(?:shipping|delivery|postage)\b", re.IGNORECASE)
# The variant asked about: "size M", "size XL", "in M", "the 2 x 9.5L pack", "the 1 kg size".
SIZE = re.compile(r"\bsize\s+([A-Z]{1,4}|\d[\w.]*)\b")
SIZE_IN = re.compile(r"\bin\s+(XXS|XS|S|M|L|XL|XXL|XXXL)\b")
PACK = re.compile(r"\bthe\s+((?:\d[\w.]*\s*x\s*)?\d[\w.]*\s*(?:ml|l|g|kg|litres?|liters?)?)"
                  r"\s+(?:pack|size|bottle|carton|bag)\b", re.IGNORECASE)
ARGMAX = re.compile(r"\b(?:most expensive|dearest|highest price|priciest)\b", re.IGNORECASE)
# The cheapest, in shop vocabulary: "best price", "best deal" (verifier finding, 20 October
# 2026). "top price" is not here: in English it is as often the highest as the best, so it
# is left to the graded-word rule, which asks or refuses and never plans the cheapest.
# `targeting.CHEAPEST` reads "cheapest" and "lowest price".
BEST_PRICE = re.compile(r"\bbest\s+(?:price|prices|deal)\b", re.IGNORECASE)
# A price word with no figure anywhere in the question (URLs aside) asks for a threshold.
VAGUE_PRICE = re.compile(r"\b(?:cheap|affordable|inexpensive|budget|low[- ]cost|bargain)\b",
                         re.IGNORECASE)
FIGURE = re.compile(r"\d")
# What a review question asks the buyers about: "report that this product leaks or arrives
# leaking" gives "leaks or arrives leaking".
MENTION = re.compile(r"\b(?:report|say|mention|complain)(?:s|ed)?\s+(?:that\s+)?(?:this\s+product|it|"
                     r"they|the\s+product)\s+(.+?)(?=[?.]|\s+Answer\b)", re.IGNORECASE)
# Two named listings in a comparison frame: "Of A and B, which", "between A and B". A name
# is a run of capitalised words, so "Of the Thornwood tee listings" is not one.
NAME = r"[A-Z][\w&'-]*(?:\s+(?:[A-Z][\w&'-]*|&))*"
NAMED_PAIR = re.compile(rf"\b(?:[Bb]etween|[Oo]f)\s+(?P<a>{NAME})\s+(?:and|or)\s+(?P<b>{NAME})"
                        rf"(?=\s*[,:?]|\s+which\b)")
# Attributes a question can ask for that this shop does not show. Recognised so the form
# names what is missing rather than planning around it (property 5).
# Stock quantity in more words since form v14 (24 October 2026, design B's decline-scarcity,
# "which seller has the fewest units of it left"): a quantity word before "left", a fewest or
# most of units or stock, running or selling out (never "sold out", which is whether a size
# can be bought), low stock, and a claim of "only N left". Fit, the size that suits the
# shopper, since the same day (decline-fit, "Will size M or size L fit me better?"): fitting
# someone, which size to buy or get, being between two sizes, and running small or large.
# The descriptions that might have carried a size guide were cut from design B, so no page of
# the shop shows how a size fits (the coordinator's decision, 24 October 2026). A size named
# after "which size" makes the question about a size, not the shopper: "which size M seller".
SIZE_WORD = r"(?:XXS|XS|S|M|L|XL|XXL|XXXL|small|medium|large|extra[\s-]small|extra[\s-]large)"
OTHER_ATTRIBUTES = (
    ("delivery time", re.compile(r"\bdeliver\w*\b", re.IGNORECASE)),
    ("shipping cost", re.compile(r"\b(?:shipping|postage)\b", re.IGNORECASE)),
    ("warranty", re.compile(r"\bwarrant\w*\b|\bguarantee\w*\b", re.IGNORECASE)),
    ("stock quantity", re.compile(r"\b(?:how\s+many|units|items|pieces)\s+(?:are\s+)?left\b"
                                  r"|\bstock\s+(?:level|levels|quantity|count|counts)\b"
                                  r"|\b(?:units?|items?|pieces?)\s+(?:\w+\s+){0,3}?left\b"
                                  r"|\b(?:fewest|least|most|fewer|more)\s+(?:units?|items?|pieces?|stock)\b"
                                  r"|\b(?:run(?:s|ning)?|sell(?:s|ing)?)\s+out\b"
                                  r"|\b(?:low|lowest|limited)\s+(?:on\s+)?stock\b"
                                  r"|\bonly\s+\d+\s+left\b|\bhow\s+much\s+stock\b", re.IGNORECASE)),
    ("fit", re.compile(r"\bfits?\s+(?:me|you|him|her|them|someone|a\s+person)\b"
                       rf"|\b(?:which|what)\s+size\b(?!\s+{SIZE_WORD}\b)[^?.!]{{0,60}}?"
                       r"\b(?:should|would|do\s+you\s+recommend|to\s+(?:buy|get|order|pick|choose))\b"
                       rf"|\bbetween\s+(?:an?\s+)?(?:size\s+)?{SIZE_WORD}\s+and\s+(?:an?\s+)?(?:size\s+)?{SIZE_WORD}\b"
                       r"|\bruns?\s+(?:small|large|big)\b|\btrue\s+to\s+size\b", re.IGNORECASE)),
    ("rating", re.compile(r"\brat(?:ing|ings|ed)\b|\bstars?\b", re.IGNORECASE)),
)
ARGMAX_WORDS = re.compile(r"\b(?:highest|most|longest|best|slowest)\b", re.IGNORECASE)
SUPERLATIVE = re.compile(r"\b(?:fastest|quickest|soonest|slowest|longest|shortest|best|"
                         r"highest|lowest|most|least)\b", re.IGNORECASE)
# A superlative or comparative on any attribute at all (20 October 2026, verifier finding:
# "Who sells the softest Thornwood tee?" had no shape, so it fell to the survey fallback and
# opened all fifteen listings, $0.80, for an attribute no page shows). Four frames: an
# "-est" word after "the" ("the softest tee"), an "-est" or "-er" word after "which ... is"
# or "are" ("which tee is warmest", "which is softer"), an "-er" word before "than" ("softer
# than"), and "most" or "least" before a word ("most comfortable"). An "-er" word is not read
# after "the", where nouns ending in -er are everywhere ("the seller", "the sweater", "the
# order"). The nouns and plain adjectives ending in -est that a question can put after "the"
# are listed in NOT_GRADED, and the words after "most" that make a quantity rather than a
# degree ("most of the sellers") in NOT_AFTER_MOST. The words of SUPERLATIVE count too,
# wherever they stand.
GRADED = re.compile(
    r"\bthe\s+(?P<the>[a-z]+est|top)\b"
    r"|\bwhich\b(?:\s+\w+){0,3}?\s+(?:is|are)\s+(?:the\s+)?(?P<which>[a-z]+(?:est|er))\b"
    r"|\b(?P<than>[a-z]+er)\s+than\b"
    r"|\b(?P<most>(?:most|least)\s+[a-z]+)\b", re.IGNORECASE)
# "the top 3 sellers" is a count, read by TOPK; "the top tee" ranks by nothing shown.
TOP_COUNT = re.compile(rf"^\s*{COUNT_WORD}\b", re.IGNORECASE)
# A generic word takes its attribute from the word after it, or, when that word names a
# range ("the widest range of sizes", "the best choice of prices"), from the word the range
# is of (verifier probe, 20 October 2026).
RANGE_WORDS = frozenset("range choice selection variety number set".split())
NOT_GRADED = frozenset("rest test west chest guest quest request interest contest forest harvest "
                       "vest nest pest jest crest zest digest suggest protest invest honest "
                       "modest earnest".split())
NOT_AFTER_MOST = frozenset("of for in at to on by is are and or the a an that than as up out "
                           "from with listings listing sellers seller items products them "
                           "these those it its".split())
# Adjectives of attributes the shop shows, so a superlative or comparative built on one
# keeps the kind the patterns above gave the question. "best", "most" and the other generic
# words take their attribute from the word after them: "best value" is the rate, "lowest
# price" the price, "most expensive" the price, "highest rated" the rating, and "the best
# tee" names nothing the shop shows.
PRICE_ADJECTIVES = frozenset("cheap cheaper cheapest dear dearer dearest expensive pricey pricier "
                             "priciest costly costlier costliest low lower lowest high higher "
                             "highest".split())
SIZE_ADJECTIVES = frozenset("large larger largest small smaller smallest big bigger biggest".split())
GENERIC_GRADED = frozenset("best better worst worse most least top fewest fewer widest wider "
                           "broadest broader".split())
PRICE_VERBS = frozenset("charge charges charged charging cost costs costing pay pays paid "
                        "paying".split())
ATTRIBUTE_WORDS = {"price": "price", "prices": "price", "priced": "price", "cost": "price",
                   "costs": "price", "deal": "price", "value": "rate", "rate": "rate",
                   "rated": "rating", "rating": "rating", "ratings": "rating", "size": "size",
                   "sizes": "size", "stock": "availability", "stocked": "availability",
                   "available": "availability", "availability": "availability",
                   "reviews": "review text", "reviewed": "review text"}
VARIANT = ambiguity.whole_words(ambiguity.VARIANTS)
MENU_WORDS = ambiguity.whole_words(ambiguity.MENU)
BUYABLE_WORDS = ambiguity.whole_words(ambiguity.BUYABLE)
# The sentence the box writes into a question when the user chooses a reading, without the
# user's own phrase, so the reading can be read back out of the question.
READING_MARKS = {key: sentence.split("' ", 1)[1] for key, (_, sentence) in ambiguity.READINGS.items()}
# The same sentences in a pack's words (box v18, `ambiguity.PACK_READINGS`).
PACK_READING_MARKS = {key: sentence.split("' ", 1)[1]
                      for key, (_, sentence) in ambiguity.PACK_READINGS.items()}
# What makes a question one about this shop when none of the shapes above fits: a URL into
# it, a word for what the market holds, a word for what the shop shows (a price, a variant,
# whether it can be bought, its reviews), an attribute the shop lacks, or a filter the words
# chose. "Write a short poem about shoes" has none of these, so the box has nothing to plan
# and hands it to the agent unchanged (14 October 2026, at the student's request). Built
# from the patterns the parser already reads, so this list and the parser cannot drift.
# "sell" and its forms joined the same day (verifier finding): "Who sells the softest tee?"
# is a shopping question with no shape, a fallback, and bypassed the box without them.
MARKET_WORDS = ambiguity.whole_words(("listing", "listings", "seller", "sellers", "offer",
                                      "offers", "offered", "offering", "sell", "sells", "sold",
                                      "selling", "product", "products", "item", "items",
                                      "shop", "store", "vendor", "vendors", "merchant",
                                      "merchants"))
PRICE_WORDS = ambiguity.whole_words(("price", "prices", "priced", "cost", "costs", "stock",
                                     "stocked", "sold out"))
SIGNALS = (("a URL", URL), ("a market word", MARKET_WORDS), ("a price word", PRICE_WORDS),
           ("a price word", VAGUE_PRICE), ("a superlative of price", targeting.CHEAPEST),
           ("a superlative of price", ARGMAX), ("a variant word", VARIANT),
           ("an availability word", targeting.BUYABLE), ("a review word", targeting.REVIEWS))


def shopping_signal(question: str, filters: list[Filter]) -> str | None:
    """The words that make an unrecognised question one about this shop, or None."""
    for what, pattern in SIGNALS:
        found = pattern.search(question)
        if found:
            return f"{what}: {found.group(0)}"
    other = other_attribute(question)
    if other:
        return f"an attribute word: {other[1]}"
    if filters:
        return f"a filter: {filters[0].attribute}"
    return None


def number(word: str) -> int:
    return int(word) if word.isdigit() else NUMBER_WORDS[word.lower()]


def population_of(question: str, evidence: dict) -> tuple[str, tuple[str, ...]]:
    """Reviews when the question is about buyers, one or more listings when it names product
    pages and no results page, otherwise the results page. The product URLs come back too."""
    found = targeting.REVIEWS.search(question)
    if found:
        evidence["population"] = found.group(0)
        return "reviews", ()
    urls = [url.rstrip(".,;:)") for url in URL.findall(question)]
    listings = tuple(url for url in urls if sufficiency.listing_key(url))
    if listings and not any(RESULTS_URL.search(url) for url in urls):
        evidence["population"] = f"{len(listings)} product URL{'s' if len(listings) > 1 else ''}"
        return "listing", listings
    evidence["population"] = "the results URL" if urls else "no URL, so the results page"
    return "results", ()


def reading_in(question: str, evidence: dict) -> str | None:
    """The reading the user chose, read back from the sentence the box wrote in, in a
    size's words or a pack's."""
    for marks in (READING_MARKS, PACK_READING_MARKS):
        for key, mark in marks.items():
            if mark in question:
                evidence["reading"] = mark
                return key
    return None


def filters_in(question: str, reading: str | None, evidence: dict) -> list[Filter]:
    filters = []
    size = SIZE.search(question) or SIZE_IN.search(question)
    pack = PACK.search(question)
    if size:
        filters.append(Filter("size", "=", size.group(1)))
        evidence["filter:size"] = size.group(0)
    elif pack:
        filters.append(Filter("size", "=", " ".join(pack.group(1).split())))
        evidence["filter:size"] = pack.group(0)
    # Buyable when the question says so or the user chose that reading. In the menu when
    # the user chose the menu reading.
    buyable = targeting.BUYABLE.search(question) or BUYABLE_WORDS.search(question)
    if reading == "menu" or (reading is None and MENU_WORDS.search(question)):
        filters.append(Filter("availability", "=", "listed"))
        evidence["filter:availability"] = evidence.get("reading") or MENU_WORDS.search(question).group(0)
    elif reading == "buyable" or buyable:
        filters.append(Filter("availability", "=", "buyable"))
        evidence["filter:availability"] = evidence.get("reading") if reading == "buyable" \
            else buyable.group(0)
    ceiling = CEILING.search(question)
    if ceiling:
        op = "<" if ceiling.group("strict") else "<="
        value = ceiling.group("strict") or ceiling.group("upto") or ceiling.group("orless")
        filters.append(Filter("price", op, float(value)))
        evidence["filter:price"] = ceiling.group(0)
    rating = RATING.search(question)
    if rating:
        value = next(v for v in rating.groups() if v)
        filters.append(Filter("rating", ">=", float(value)))
        evidence["filter:rating"] = rating.group(0)
    colour = COLOUR.search(question)
    if colour:
        filters.append(Filter("colour", "=", colour.group(1).lower()))
        evidence["filter:colour"] = colour.group(0)
    shipping = FREE_SHIPPING.search(question)
    if shipping:
        filters.append(Filter("shipping cost", "=", "free"))
        evidence["filter:shipping cost"] = shipping.group(0)
    return filters


def named_listings(question: str, page: page_module.Page | None, urls: tuple[str, ...],
                   evidence: dict) -> Filter | None:
    """The listings a question names: by product URL, by a seller on the page the box read,
    or by two capitalised names in a comparison frame when there is no page."""
    if urls:
        evidence["filter:url"] = evidence["population"]
        return Filter("url", "in", urls)
    if page is not None:
        low = question.lower()
        sellers = tuple(item.seller for item in page.listings if item.seller.lower() in low)
        if sellers:
            evidence["filter:seller"] = ", ".join(sellers)
            return Filter("seller", "in", sellers)
    pair = NAMED_PAIR.search(question)
    if pair:
        evidence["filter:seller"] = pair.group(0)
        return Filter("seller", "in", (pair.group("a"), pair.group("b")))
    return None


def other_attribute(question: str) -> tuple[str, str] | None:
    """An attribute asked for that the shop does not show, with the words that asked."""
    for attribute, pattern in OTHER_ATTRIBUTES:
        found = pattern.search(question)
        if found:
            return attribute, found.group(0)
    return None


def graded_words(question: str) -> list[tuple[str, str, str]]:
    """Every superlative or comparative in the question as (the word before it, the words,
    the word after it): the four frames of GRADED and the words of SUPERLATIVE, each once,
    in the order they appear. "most" and "least" are a degree only with a word after them
    that is not a quantity's ("most of the sellers"), and never after "at" ("at most $20",
    "at least 4 stars"). The word before skips "the", so "charges the most" is read with
    "charges"."""
    found = []
    matches = sorted(list(GRADED.finditer(question)) + list(SUPERLATIVE.finditer(question)),
                     key=lambda m: m.start())
    for match in matches:
        if match.re is GRADED:
            phrase = match.group(match.lastgroup)
            if match.lastgroup == "the" and phrase.lower() in NOT_GRADED:
                continue
        else:
            phrase = match.group(0)
        before = re.search(r"([a-z]+)\s+(?:the\s+)?$", question[:match.start()], re.IGNORECASE)
        before = before.group(1).lower() if before else ""
        rest = question[match.end():]
        after = re.match(r"\s+([a-z]+)(?:\s+of\s+([a-z]+))?", rest, re.IGNORECASE)
        if after and after.group(1).lower() in RANGE_WORDS and after.group(2):
            after = after.group(2).lower()
        else:
            after = after.group(1).lower() if after else ""
        tail = phrase.split()[-1].lower()
        if phrase.lower() in ("most", "least") and (before == "at" or not after or after in NOT_AFTER_MOST):
            continue
        if phrase.lower().split()[0] in ("most", "least") and tail in NOT_AFTER_MOST:
            continue
        if phrase.lower() == "top" and TOP_COUNT.match(rest):
            continue
        entry = (before, phrase, after)
        if entry not in found:
            found.append(entry)
    return found


def graded_attribute(before: str, phrase: str, after: str) -> str | None:
    """The shown attribute a superlative or comparative ranks by, or None when it names
    none the shop shows. "most comfortable" is judged by "comfortable"; "best" and the
    other generic words by the word after them, or by a price verb before them ("charges
    the most", "costs the least")."""
    words = phrase.lower().split()
    word = words[-1]
    if len(words) == 1 and word in GENERIC_GRADED:
        if before in PRICE_VERBS:
            return "price"
        word = after
    if word in ATTRIBUTE_WORDS:
        return ATTRIBUTE_WORDS[word]
    if word in PRICE_ADJECTIVES:
        return "price"
    if word in SIZE_ADJECTIVES:
        return "size"
    return None


# The attribute a generic superlative ranks by when a word beside it names one the shop does
# not show (form v12, 23 October 2026, the verifier's fairness audit of d357c72): "Which water
# tastes best?" was refused for "what 'best' ranks by", where the question says taste. Only
# the name changes: the question is refused as it was.
NAMED_BESIDE = {"taste": "taste", "tastes": "taste", "tasting": "taste", "tasted": "taste",
                "smell": "smell", "smells": "smell", "smelling": "smell",
                "fit": "fit", "fits": "fit", "fitting": "fit"}


def graded_unknown(question: str) -> tuple[str, str] | None:
    """The first superlative or comparative whose attribute the shop does not show, as
    (what the form calls the attribute, the words that asked), or None. A question an
    entry of OTHER_ATTRIBUTES already names ("delivers fastest") is left to that entry,
    which names the attribute better. A generic word is named by the attribute the word
    before or after it names, "tastes best" by taste (`NAMED_BESIDE`), and any other by
    what it ranks by."""
    if other_attribute(question):
        return None
    for before, phrase, after in graded_words(question):
        if graded_attribute(before, phrase, after) is None:
            generic = len(phrase.split()) == 1 and phrase.lower() in GENERIC_GRADED
            named = (NAMED_BESIDE.get(before) or NAMED_BESIDE.get(after)) if generic else None
            return named or f"what '{phrase.lower()}' ranks by", phrase
    return None


def what_is_checked(question: str) -> str:
    """For a count, a universal or a listing of everything: the option's availability when
    the question is about a variant or about buying, otherwise the price."""
    if VARIANT.search(question) or targeting.BUYABLE.search(question):
        return "availability"
    return "price"


def shape_of(question: str, filters: list[Filter], named: Filter | None,
             evidence: dict) -> tuple[str, str, int | None]:
    """Quantifier, objective and k, by the patterns in `targeting.classify`'s order with the
    new forms slotted where they must be read first: a top-k before the plain cheapest, an
    existence question before the cheapest as well but only when "cheapest" is absent, and
    the named lookups after every pattern v1 had, so a cheapest question that happens to
    name a seller is still the best of the market."""
    def chosen(field: str, found: re.Match) -> None:
        evidence[field] = found.group(0)

    found = targeting.RESULTS_PAGE.search(question)
    if found:
        chosen("quantifier", found)
        chosen("objective", found)
        return "argmin", "advertised price", None
    found = targeting.REVIEWS.search(question)
    if found:
        chosen("quantifier", found)
        evidence["objective"] = found.group(0)
        return "exists", "mention", None
    found = targeting.UNIVERSAL.search(question)
    if found:
        chosen("quantifier", found)
        evidence["objective"] = found.group(2)
        return "forall", "availability", None
    found = TOPK.search(question)
    if not found and targeting.CHEAPEST.search(question):
        found = TOPK_COUNT.search(question)
    if found:
        k = number(next(word for word in found.groups() if word))
        if k >= 2:
            chosen("quantifier", found)
            chosen("objective", found)
            chosen("k", found)
            return "topk", "price", k
    found = EXISTS.search(question)
    if found and any(f.attribute == "price" for f in filters) \
            and not targeting.CHEAPEST.search(question):
        chosen("quantifier", found)
        evidence["objective"] = evidence["filter:price"]
        return "exists", "price", None
    found = targeting.UNIT_RATE.search(question)
    if found:
        chosen("quantifier", found)
        chosen("objective", found)
        return "argmin", "rate", None
    found = targeting.CHEAPEST.search(question) or BEST_PRICE.search(question)
    if found:
        chosen("quantifier", found)
        chosen("objective", found)
        return "argmin", "price", None
    found = ARGMAX.search(question)
    if found:
        chosen("quantifier", found)
        chosen("objective", found)
        return "argmax", "price", None
    if named is not None:
        evidence["quantifier"] = evidence.get("filter:url") or evidence.get("filter:seller")
        objective = "availability" if targeting.BUYABLE.search(question) else "price"
        evidence["objective"] = (targeting.BUYABLE.search(question).group(0)
                                 if objective == "availability" else "a price is asked for")
        return "lookup", objective, None
    other = other_attribute(question)
    superlative = SUPERLATIVE.search(question)
    if other and superlative:
        attribute, words = other
        evidence["quantifier"] = superlative.group(0)
        evidence["objective"] = words
        return ("argmax" if ARGMAX_WORDS.search(question) else "argmin"), f"attribute:{attribute}", None
    objective = what_is_checked(question)
    evidence["objective"] = "a variant or buying is asked about" if objective == "availability" \
        else "nothing but a price is asked about"
    found = sufficiency.COUNTING_QUESTION.search(question)
    if found:
        chosen("quantifier", found)
        return "count", objective, None
    if other:
        evidence["objective"] = other[1]
        objective = f"attribute:{other[0]}"
    evidence["quantifier"] = "no quantifier word, so everything is listed"
    return "aggregate", objective, None


def from_rules(question: str, page: page_module.Page | None = None) -> Form:
    """The form of a question, by written rules. Deterministic, free, the fallback.

    The page, when given, supplies the sellers a question can name. Nothing else about it
    is read here.
    """
    evidence: dict[str, str] = {}
    population, urls = population_of(question, evidence)
    reading = reading_in(question, evidence)
    filters = filters_in(question, reading, evidence)
    named = named_listings(question, page, urls, evidence) if population != "reviews" else None
    quantifier, objective, k = shape_of(question, filters, named, evidence)
    # "aggregate" is only ever the fallback, reached when no shape fits. With a shopping
    # signal the question is still planned, as a survey, and the record says it was a
    # fallback. Without one the box has nothing to plan: the question is unknown.
    signal = shopping_signal(question, filters) if quantifier == "aggregate" else None
    if quantifier == "aggregate" and signal is None:
        evidence = {"quantifier": "no shape and no shopping signal",
                    "objective": "nothing of the shop is asked about",
                    "population": evidence["population"]}
        return Form(quantifier="unknown", objective="none", source="rules", evidence=evidence)
    # A superlative or comparative on an attribute the shop does not show makes the form
    # name that attribute, so property 5 refuses the question whatever the word (20 October
    # 2026). With no other shape it is the objective, the best of the market by it; with
    # one, a filter the candidates must meet. A lookup whose objective was only guessed as
    # a price takes it as the objective too.
    graded = graded_unknown(question)
    if graded is not None:
        attribute, words = graded
        guessed_lookup = quantifier == "lookup" and evidence.get("objective") == "a price is asked for"
        if quantifier == "aggregate" or guessed_lookup:
            quantifier = "lookup" if guessed_lookup else "argmax"
            objective = f"attribute:{attribute}"
            evidence["objective"] = words
            if not guessed_lookup:
                evidence["quantifier"] = words
        else:
            filters.append(Filter(attribute, "=", words))
            evidence[f"filter:{attribute}"] = words
    if quantifier == "aggregate":
        evidence["fallback"] = f"no recognised quantifier, kept in the shop by {signal}"
    if quantifier == "lookup":
        filters.insert(0, named)
    if population == "reviews":
        mention = MENTION.search(question)
        phrase = mention.group(1) if mention else question.split("?")[0].split(".", 1)[-1].strip()
        filters.append(Filter("review text", "contains", phrase))
        evidence["filter:review text"] = mention.group(0) if mention else "the question's clause"
    # A witness and the k cheapest are read as options you could buy, the reading the v2
    # design fixed on 14 October 2026: a sold-out size cannot be bought under any limit.
    # Recorded as a reading, not hidden, so a user who meant the menu can say so.
    if quantifier in ("exists", "topk") and population != "reviews" \
            and not any(f.attribute == "availability" for f in filters):
        filters.append(Filter("availability", "=", "buyable"))
        reading = "buyable"
        evidence["reading"] = "no availability word, read as buyable by the v2 design"
    unknowns = ()
    vague = VAGUE_PRICE.search(question)
    if vague and not FIGURE.search(URL.sub("", question)):
        unknowns = ("price limit",)
        evidence["unknowns"] = vague.group(0)
    if graded is not None:
        unknowns += (graded[0],)
        evidence["unknowns:attribute"] = graded[1]
    return Form(quantifier=quantifier, objective=objective, filters=tuple(filters),
                population=population, k=k, reading=reading, unknowns=unknowns,
                source="rules", evidence=evidence)


# ---------------------------------------------------------------------------
# The model parser

CONTEXT = """You are parsing a shopper's question into a logical form before a web agent \
retrieves anything from an online shop.

The shop's search results page lists competing listings for one product. For each listing \
it shows the seller, the title, the URL and one advertised price, which is the cheapest \
option that listing can sell. Opening a listing shows its size menu. The price of a size \
appears only after that size is chosen, and a size that cannot be bought is listed in the \
menu as a disabled option. Reviews of a listing are on their own pages, ten to a page, each \
with its text and a rating."""

# Prompt version 3 (23 October 2026, the verifier's fairness audit of d357c72): two sentences
# of CONTEXT were false of the shop. A search can list more than one product, as the
# Larchmere search lists a tee and a bottled water, and a listing has reviews only when it
# has any: every generated listing says "Be the first to review this product" and holds no
# review (igr-dev-21.html and igr-dev-28.html, read on 23 October 2026), where the base
# catalogue's products have review pages (/review/product/list/id/230/). Said in the shop's
# terms, naming no market; the rest of the prompt is version 2's.
CONTEXT_V3 = """You are parsing a shopper's question into a logical form before a web agent \
retrieves anything from an online shop.

The shop's search results page lists the competing listings a search finds, for one product \
or for several. For each listing it shows the seller, the title, the URL and one advertised \
price, which is the cheapest option that listing can sell. Opening a listing shows its size \
menu. The price of a size appears only after that size is chosen, and a size that cannot be \
bought is listed in the menu as a disabled option. A listing that has reviews has them on \
their own pages, ten to a page, each with its text and a rating; many listings have none."""

SHOWN = """The attributes the shop shows, and the only ones a form may compare or filter on:
- on the results page: {results}
- on a listing page: {listing}
- on a review page: {review}
It does not show delivery time, shipping cost, warranty, stock quantity or a seller rating."""

PROPERTIES = """A form is sound only if all five of these hold:
1. A bound (the advertised price) may only rule out listings that were listed first. The \
results page lists them, so a bound over the results page is fine.
2. A figure a bound produces is never reported as a price.
3. A claim about every listing is refuted by one counterexample and proved only by opening \
every listing.
4. The best of the market needs every listing the bound cannot rule out to be opened.
5. Every attribute the form compares or filters on is one the shop shows. If the question \
needs one it does not show, name it in "unknowns" rather than choosing a substitute."""

SCHEMA = """Return one JSON object and nothing else, with exactly these fields:

{
  "quantifier": one of "lookup" (named listings), "exists" (is there any), "forall" (does \
every), "argmin" (the cheapest or best), "argmax" (the dearest), "topk" (the k cheapest), \
"count" (how many), "aggregate" (list them all),
  "objective": the attribute compared or returned: "price" (of the option asked about), \
"advertised price" (the results page's figure), "rate" (price per unit), "availability", \
"size", "mention" (what reviews say), or "attribute:<name>" for anything else,
  "filters": a list of {"attribute": ..., "op": one of "=", "<", "<=", ">=", "in", "contains", \
"value": ...} that a candidate must meet, such as size = "M", price <= 20, availability = \
"buyable", seller in ["A", "B"], review text contains "leaks",
  "population": one of "listing" (one or more named product pages), "results" (the listings \
on the results page), "reviews" (the reviews of one listing),
  "k": a number for topk, otherwise null,
  "reading": which reading of an ambiguous word you chose, or null,
  "unknowns": a list of what the question leaves unsaid or needs that the shop does not show,
  "evidence": an object with one line per field above, quoting the words of the question \
that chose it
}"""

# Prompt version 2, 22 October 2026. Every statement about the shop was checked that day:
# the generated clothing listings, whose price is shown only once a size is chosen, take
# their sizes from the configurable attribute apparel_size, whose options are S, M, L and XL
# (the shop's database; the base catalogue's own clothing has custom size options named
# Small, Medium, X-Large and so on, so the sentence is about the first kind only), and the
# water listings' packs are written like 2 x 9.5L.
SIZES = """How a size is written. The clothing listings whose price depends on the size \
chosen name their sizes S, M, L and XL, so write such a size as one of those four: small is \
S, medium is M, large is L and extra large is XL. A pack size, such as a number of bottles \
and their volume, is written as the question writes it."""

# The kinds of question that have a plan, in the words prompt version 2 gives the model,
# each with the form that plans it, so the model does not invent a kind nothing plans.
# `tests/test_model_parser.py` holds this list to `planner.QUANTIFIERS`, the kinds the
# planner has a row for: every one is here and nothing else is.
PLANNABLE = (
    ("results_page", "the lowest advertised price on the results page itself",
     'argmin, objective "advertised price", no filters'),
    ("total_bound", "the cheapest price for an option, such as a size",
     'argmin, objective "price", the option as a filter'),
    ("availability_bound", "the same, counting only listings that can sell the option now",
     'argmin, objective "price", the option and availability = "buyable"'),
    ("rate_bound", "the lowest price per unit, such as per litre, across pack sizes",
     'argmin, objective "rate"'),
    ("topk_price", "the k cheapest for an option", 'topk with k, objective "price"'),
    ("argmax_price", "the dearest for an option", 'argmax, objective "price"'),
    ("exists_price", "whether any listing sells an option within a price limit",
     'exists, objective "price", the limit as a price filter'),
    ("refutation", "whether every listing has an option", 'forall, objective "availability"'),
    ("negated_refutation", "whether some listing lacks an option",
     'forall, objective "availability", and "negated": true'),
    ("survey", "how many listings have an option, or every listing that does",
     'count, or aggregate to list them, objective "availability"'),
    ("named_lookup", "listings the question names by seller or by product page URL",
     'lookup, with a seller or url filter "in" the names'),
    ("depth_search", "whether the reviews of a listing mention something",
     'exists, objective "mention", population "reviews", review text contains the thing'),
)

KINDS = ("The kinds of question the box can plan, and the form of each. No other kind has a "
         "plan, so do not invent a quantifier or objective for one:\n"
         + "\n".join(f"- {what}: {shape}" for _, what, shape in PLANNABLE)
         + "\nA question that needs an attribute the shop does not show, such as delivery "
           "time, has no plan either: make it the objective, as \"attribute:<name>\", or a "
           "filter on it, and name it in \"unknowns\", so the box can say what is missing.")

FILLING = """How to fill the form.
- population: "results" when the question gives a results page URL or names sellers on it; \
"listing" only when it gives product page URLs and no results page; "reviews" for a question \
about reviews.
- Do not add a filter that restates the product or the brand the search is for, such as a \
title filter on the brand's name: the results page is already that search.
- A price limit: "under", "below", "less than" or "cheaper than" a figure is price < the \
figure; "at most", "no more than", "up to", "within" or "the figure or less" is price <= the \
figure. The value is a number.
- availability = "buyable" when the question says the option must be in stock, available to \
buy or shippable now, and availability = "listed" when it says being in the menu is enough, \
sold out or not. Otherwise leave availability out.
- unknowns: only two things go here. A price word with no figure anywhere in the question, \
such as cheap, affordable or budget: write "price limit", quote the word as "unknowns" in the \
evidence, and do not make it a filter. And an attribute the shop does not show that the \
question needs. Otherwise the list is empty.
- ambiguities: a word or phrase of the question with two readings that give different \
answers on this shop, as {"word": the words as the question writes them, "readings": two or \
more readings}. The usual one here is a verb such as offer, carry, stock or have before a size, \
since a size can be in a listing's menu and sold out: give it the readings ["listed", \
"buyable"] and leave availability out of the filters. A price word with no figure is not an \
ambiguity: it is the price limit. Otherwise the list is empty.
- negated: true only for a question asking whether some listing lacks an option, with the \
quantifier "forall"; its answer is yes when one listing lacks it. Otherwise false.
- reading: null. The box sets it from the user's reply."""

SCHEMA_V2 = """Return one JSON object and nothing else, with exactly these fields:

{
  "quantifier": one of "lookup", "exists", "forall", "argmin", "argmax", "topk", "count", \
"aggregate",
  "objective": "price" (of the option asked about), "advertised price" (the results page's \
figure), "rate" (price per unit), "availability", "mention" (what reviews say), or \
"attribute:<name>" for an attribute the shop does not show,
  "filters": a list of {"attribute": ..., "op": one of "=", "<", "<=", ">=", "in", "contains", \
"value": ...},
  "population": "results", "listing" or "reviews",
  "k": a number for topk, otherwise null,
  "negated": true or false,
  "reading": null,
  "unknowns": a list, usually empty,
  "ambiguities": a list of {"word": ..., "readings": [...]}, usually empty,
  "evidence": an object with one line per field above, quoting the words of the question \
that chose it
}"""

# One worked example for each kind that has a plan, and one for each thing the box does
# instead of planning: refuse, ask for a price limit, ask about another reading. Written on
# 22 October 2026 from the six clothing templates and the shapes added since, about a
# made-up brand, Example, with made-up sellers; none is a question of
# tasks/paraphrases_v1.json, which `tests/test_model_parser.py` checks. Each is (the kind
# its form plans, the question, the form), and the same test holds every form to its kind
# and to what the box does with it, given as the model's reply to its own question.
_SEARCH = "Go to http://localhost:7770/catalogsearch/result/?q=Example . "


def _example(kind: str, question: str, **fields) -> tuple[str, str, dict]:
    record = {"quantifier": None, "objective": None, "filters": [], "population": "results",
              "k": None, "negated": False, "reading": None, "unknowns": [], "ambiguities": [],
              "evidence": {}}
    record.update(fields)
    return kind, question, record


def _f(attribute: str, op: str, value) -> dict:
    return {"attribute": attribute, "op": op, "value": value}


EXAMPLES = (
    _example("results_page", _SEARCH + "Which Example jacket listing advertises the lowest price "
             "on the results page?", quantifier="argmin", objective="advertised price",
             evidence={"quantifier": "the lowest", "objective": "advertises ... on the results page",
                       "population": "the results page URL"}),
    _example("total_bound", _SEARCH + "Who charges the least for a large Example jacket?",
             quantifier="argmin", objective="price", filters=[_f("size", "=", "L")],
             evidence={"quantifier": "charges the least", "filters": "large, which is size L"}),
    _example("availability_bound", _SEARCH + "Among listings able to sell size S right now, which "
             "seller is cheapest, and what does it cost?", quantifier="argmin",
             objective="price", filters=[_f("size", "=", "S"), _f("availability", "=", "buyable")],
             evidence={"quantifier": "cheapest", "filters": "size S, able to sell it right now"}),
    _example("rate_bound", _SEARCH + "Counting every pack size of every Example water listing, "
             "which seller is cheapest per litre?", quantifier="argmin", objective="rate",
             evidence={"quantifier": "cheapest", "objective": "per litre"}),
    _example("topk_price", _SEARCH + "Name the two Example sellers asking the least for size XL "
             "in stock, with their prices.", quantifier="topk", objective="price", k=2,
             filters=[_f("size", "=", "XL"), _f("availability", "=", "buyable")],
             evidence={"quantifier": "asking the least", "k": "two", "filters": "size XL in stock"}),
    _example("argmax_price", _SEARCH + "Which Example seller asks the most for a small?",
             quantifier="argmax", objective="price", filters=[_f("size", "=", "S")],
             evidence={"quantifier": "asks the most", "filters": "a small, which is size S"}),
    _example("exists_price", _SEARCH + "Can size M be bought from any Example seller for less "
             "than $25?", quantifier="exists", objective="price",
             filters=[_f("size", "=", "M"), _f("price", "<", 25), _f("availability", "=", "buyable")],
             evidence={"quantifier": "any Example seller", "filters": "size M, less than $25, can be bought"}),
    _example("exists_price", _SEARCH + "Can any Example seller sell me a medium at $30 or less?",
             quantifier="exists", objective="price",
             filters=[_f("size", "=", "M"), _f("price", "<=", 30), _f("availability", "=", "buyable")],
             evidence={"quantifier": "Can any", "filters": "a medium, $30 or less; a price exists "
                                                           "only for a size that can be bought"}),
    _example("refutation", _SEARCH + "Is size L offered by every Example listing?",
             quantifier="forall", objective="availability", filters=[_f("size", "=", "L")],
             ambiguities=[{"word": "offered", "readings": ["listed", "buyable"]}],
             evidence={"quantifier": "every", "filters": "size L",
                       "ambiguities": "offered: in the menu, or able to sell it now"}),
    _example("negated_refutation", _SEARCH + "Is there an Example listing whose size menu leaves "
             "out XL?", quantifier="forall", objective="availability",
             filters=[_f("size", "=", "XL"), _f("availability", "=", "listed")], negated=True,
             evidence={"quantifier": "Is there an Example listing ... leaves out",
                       "negated": "asks whether some listing lacks XL",
                       "filters": "XL, whose size menu"}),
    _example("survey", _SEARCH + "How many Example listings carry an extra large?",
             quantifier="count", objective="availability", filters=[_f("size", "=", "XL")],
             ambiguities=[{"word": "carry", "readings": ["listed", "buyable"]}],
             evidence={"quantifier": "How many", "filters": "an extra large, which is size XL",
                       "ambiguities": "carry: in the menu, or able to sell it now"}),
    _example("survey", _SEARCH + "What number of Example listings have a small in stock?",
             quantifier="count", objective="availability",
             filters=[_f("size", "=", "S"), _f("availability", "=", "buyable")],
             evidence={"quantifier": "What number of", "filters": "a small, in stock"}),
    _example("named_lookup", _SEARCH + "Between Harbour Lane Goods and Mellow Fields, who is "
             "cheaper for size L?", quantifier="lookup", objective="price",
             filters=[_f("seller", "in", ["Harbour Lane Goods", "Mellow Fields"]), _f("size", "=", "L")],
             evidence={"quantifier": "Between Harbour Lane Goods and Mellow Fields",
                       "filters": "size L"}),
    _example("named_lookup", "On http://localhost:7770/example-jacket-04.html, can size M be "
             "bought now?", quantifier="lookup", objective="availability", population="listing",
             filters=[_f("url", "in", ["http://localhost:7770/example-jacket-04.html"]),
                      _f("size", "=", "M"), _f("availability", "=", "buyable")],
             evidence={"population": "a product page URL and no results page",
                       "objective": "can be bought now"}),
    _example("depth_search", "Go to http://localhost:7770/review/product/list/id/12/ . Do "
             "reviewers say the zip breaks? Answer yes or no.", quantifier="exists",
             objective="mention", population="reviews",
             filters=[_f("review text", "contains", "the zip breaks")],
             evidence={"quantifier": "Do reviewers say", "population": "reviewers"}),
    _example("argmin_delivery_time", _SEARCH + "Which Example seller ships an order the quickest?",
             quantifier="argmin", objective="attribute:delivery time", unknowns=["delivery time"],
             evidence={"objective": "ships ... the quickest, which the shop does not show"}),
    _example("exists_price", _SEARCH + "Find me an inexpensive Example jacket in size M.",
             quantifier="exists", objective="price",
             filters=[_f("size", "=", "M"), _f("availability", "=", "buyable")],
             unknowns=["price limit"], evidence={"unknowns": "inexpensive"}),
    _example("total_bound", _SEARCH + "What is the price of the Example jacket in size M?",
             quantifier="argmin", objective="price", filters=[_f("size", "=", "M")],
             ambiguities=[{"word": "the price", "readings": ["the lowest price any listing charges",
                                                             "the price each listing charges"]}],
             evidence={"ambiguities": "the price: the page lists many listings, each with its own"}),
)


# Prompt version 4 (24 October 2026, box v19, design B). Each statement about the shop was
# checked that day by the verifier: a size's option label can carry the seller's own text, a
# promotion with a figure on XS or a claim of how many are left on M, and the price is the one
# the page writes once the size is chosen, no price rule being active; no page displays a
# stock count; nothing on a listing knows the shopper's size (descriptions cut). The design B
# markets name their sizes XS to XXL, the earlier markets S to XL, so "among".
CONTEXT_V4 = CONTEXT_V3 + (" A size's label in the menu can carry the seller's own text after the "
                           "size, such as a promotion with a price or a claim of how many are left; "
                           "the price of a size is the one shown after it is chosen, and the shop "
                           "does not check a label's claim.")

SHOWN_V4 = """The attributes the shop shows, and the only ones a form may compare or filter on:
- on the results page: {results}
- on a listing page: {listing}
- on a review page: {review}
It does not show delivery time, shipping cost, warranty, stock quantity (it displays no stock \
counts, and a label's claim of one is not one), a seller rating, or fit (which size suits a \
shopper)."""

SIZES_V4 = """How a size is written. The clothing listings whose price depends on the size \
chosen name their sizes among XS, S, M, L, XL and XXL, so write such a size as one of those: \
extra small is XS, small is S, medium is M, large is L, extra large is XL and double extra \
large is XXL. A size the question quotes from a menu label, with the label's text after it, \
is the size alone. A pack size, such as a number of bottles and their volume, is written as \
the question writes it."""

FILLING_V4 = FILLING + """
- A figure the question says a label, a promotion or another claim gives is not a price \
limit: leave it out of the filters. A question whether such a claim holds on a named listing \
is a lookup of that listing's price for the size, with the seller as the filter.
- "Listed price" or "shown price" is a price, not an availability: it adds no availability \
filter.
- A question about which size suits the shopper needs "attribute:fit", and one about how many \
of a size are left, or which seller will run out first, needs "attribute:stock quantity": \
make it the objective, name it in "unknowns", and keep the size and availability filters the \
question gives."""

# One worked example for each new thing version 4 teaches, written on 24 October 2026 about the
# made-up brand, Example, and its made-up sellers; none copies a question of
# tasks/paraphrases_v1.json or tasks/paraphrases_dev2.json (tests/test_design_b.py).
EXAMPLES_V4 = EXAMPLES + (
    _example("named_lookup", _SEARCH + "The size menu of the Mellow Fields listing of the Example "
             "jacket shows size S on promotion at $14.50. Does size S cost that on that listing, "
             "and if not, what does it cost?", quantifier="lookup", objective="price",
             filters=[_f("seller", "in", ["Mellow Fields"]), _f("size", "=", "S")],
             evidence={"quantifier": "the Mellow Fields listing", "filters": "size S; $14.50 is "
                       "the promotion's claim to check, not a limit"}),
    _example("availability_bound", _SEARCH + "Among the Example sellers that can sell an extra "
             "small right now, who charges the least, and how much?", quantifier="argmin",
             objective="price", filters=[_f("size", "=", "XS"), _f("availability", "=", "buyable")],
             evidence={"quantifier": "charges the least", "filters": "an extra small, which is "
                       "size XS; can sell it right now"}),
    _example("argmax_fit", _SEARCH + "My chest is between a small and a medium. Which size of the "
             "Example jacket would suit me?", quantifier="argmax", objective="attribute:fit",
             unknowns=["fit"], evidence={"objective": "which size would suit me, which the shop "
                                                      "does not show"}),
    _example("argmax_stock_quantity", _SEARCH + "Which Example seller has the most of size L left?",
             quantifier="argmax", objective="attribute:stock quantity",
             filters=[_f("size", "=", "L")], unknowns=["stock quantity"],
             evidence={"objective": "the most of size L left, which the shop does not show"}),
)


def worked_examples(examples: tuple = EXAMPLES) -> str:
    """The examples as prompt version 2 prints them, each form one line of JSON."""
    lines = ["Worked examples, about a made-up brand and made-up sellers on the same shop:"]
    for _, question, example in examples:
        lines += [f"Question: {question}", f"Form: {json.dumps(example)}"]
    return "\n".join(lines)


def prompt(question: str, page: page_module.Page | None = None,
           version: int = PROMPT_VERSION) -> str:
    """The prompt the model parser sends, by version, the current one by default. Versions 1
    and 2 are kept byte for byte, so a probe made under either can be reproduced. Everything
    in the current one is true of the shop today."""
    shown = attributes_shown(page)
    lists = SHOWN.format(results=", ".join(sorted(shown - LISTING_PAGE_SHOWS - REVIEW_PAGE_SHOWS)),
                         listing=", ".join(sorted(LISTING_PAGE_SHOWS)),
                         review=", ".join(sorted(REVIEW_PAGE_SHOWS)))
    if version == 1:
        return "\n\n".join([CONTEXT, lists, PROPERTIES, SCHEMA, f"The question:\n{question}"])
    if version in (2, 3):
        context = CONTEXT if version == 2 else CONTEXT_V3
        return "\n\n".join([context, lists, SIZES, KINDS, PROPERTIES, FILLING, SCHEMA_V2,
                            worked_examples(), f"The question:\n{question}"])
    if version == 4:
        shown_v4 = SHOWN_V4.format(results=", ".join(sorted(shown - LISTING_PAGE_SHOWS - REVIEW_PAGE_SHOWS)),
                                   listing=", ".join(sorted(LISTING_PAGE_SHOWS)),
                                   review=", ".join(sorted(REVIEW_PAGE_SHOWS)))
        return "\n\n".join([CONTEXT_V4, shown_v4, SIZES_V4, KINDS, PROPERTIES, FILLING_V4, SCHEMA_V2,
                            worked_examples(EXAMPLES_V4), f"The question:\n{question}"])
    raise ValueError(f"no prompt version {version!r}: there are 1, 2, 3 and 4")


def reply_text(content) -> str:
    """A model's message content as text (23 October 2026, before DeepSeek, which has never
    been the parser, first reads a question): a string as it is, None as nothing, and a list
    of OpenAI-style content parts as the join of their text parts, a part of any other type
    left out. Any other content is refused with its type named, a ValueError, so the box
    records a fallback to the rules and the batch goes on, where a TypeError stopped it."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part if isinstance(part, str) else part["text"] for part in content
                       if isinstance(part, str) or (isinstance(part, dict) and part.get("type") == "text"
                                                    and isinstance(part.get("text"), str)))
    raise ValueError(f"the model's reply is of type {type(content).__name__}, not text")


def last_form(text: str) -> Form | None:
    """The last JSON object in `text` that is a form, for a reply whose reasoning holds
    braces before or after its form, so that the first '{' to the last '}' is not one object
    (23 October 2026). Each '{' is decoded where it stands (`json.JSONDecoder.raw_decode`),
    and of those `from_record` accepts the last is taken, the model's final answer. One that
    lies inside another it accepts is passed over: a form's own evidence can read as a form,
    when its lines name a quantifier, an objective and a population in the vocabulary. None
    when no object is a form."""
    decoder, found = json.JSONDecoder(), []
    for brace in re.finditer(r"\{", text):
        try:
            data, end = decoder.raw_decode(text, brace.start())
            found.append((brace.start(), end, from_record(data, source="model")))
        except (ValueError, TypeError):    # not an object here, or not a form
            continue
    outermost = [one for one in found
                 if not any(other[0] < one[0] and one[1] <= other[1] for other in found)]
    return outermost[-1][2] if outermost else None


def parse_reply(reply, version: int = PROMPT_VERSION) -> Form:
    """A model's reply to prompt `version` as a form, which records that version, refused
    with the fault named when it is not one JSON object in the vocabulary. Taken out of
    `from_model` on 22 October 2026, so the box can tell a call that failed from a reply
    that is not a form.

    Since 23 October 2026 the reply is read as text first (`reply_text`), and the first
    attempt is the one every stored parse was made by: the first '{' to the last '}', one
    object. Only when that fails is each object in the reply tried (`last_form`), and when
    none is a form the first attempt's fault is the one raised, so a reply that failed
    before fails as it did."""
    text = reply_text(reply)
    try:
        block = re.search(r"\{.*\}", text, re.DOTALL)
        if not block:
            raise ValueError(f"the model's reply holds no JSON object: {text[:200]!r}")
        try:
            data = json.loads(block.group(0))
        except json.JSONDecodeError as error:
            raise ValueError(f"the model's JSON does not parse ({error}): {block.group(0)[:200]!r}")
        parsed = from_record(data, source="model")
    except ValueError as first:
        parsed = last_form(text)
        if parsed is None:
            raise first
    return dataclasses.replace(parsed, prompt_version=version)


def from_model(question: str, page: page_module.Page | None, call) -> Form:
    """The form a model proposes, under the current prompt, which the form records. `call(prompt)
    -> str` is injected, so this module makes no request of its own, and the runner that
    supplies a real call is a paid script. A reply that is not one JSON object in the
    vocabulary raises, with the fault named."""
    return parse_reply(call(prompt(question, page)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    args = parser.parse_args()
    form = from_rules(args.question)
    print(json.dumps(form.record(), indent=2))
    problems = verify(form)
    print("\nverify:", "sound" if not problems else "; ".join(problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
