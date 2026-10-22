#!/usr/bin/env python3
"""What the box does to a model's form before it uses one: put it in the page's own words,
then hold it to the checks a model's form must pass besides the five properties.

The model parser reads reworded questions better than the rules, and makes the same few
mistakes over and over (the paraphrase probe of 20 October 2026,
experiments/results/parse-probe-paraphrases_v1-20261020T223344.json): it keeps "medium"
where the shop says M, adds a title filter that restates the brand the search is for, calls
the results page "listing", and spells a seller as the question did. Each is put right here
in code, from the form, the question and the page the box read, and nothing else. Every
change is written into the form's evidence under "normalised:<field>" and returned as a
line, so a reader can see what normalisation did.

Then the checks. A model can write a form the vocabulary accepts and no plan can carry: a
seller filter on the cheapest of the market, which the bound ignores while the answer check
counts every listing; a size filter on a results-page question, whose advertised prices are
of no particular size; a price limit that is not a number. The rules never write such a
form, so these hold a model's form to what the rules' forms already are. A form that fails
is not used, and the box falls back to the rules' form (`box.decide`).

It calls no model and reads no file. `call` is the caller's, and only `read` uses it.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/, runners/, analysis/, water/ on the path)
import form as form_module  # noqa: E402
import page as page_module  # noqa: E402
from form import Filter, Form  # noqa: E402

# Bumped when a normalisation or a check changes what the box does with a model's form.
# Runs made under different versions are different parsers and are never pooled.
#
#   1  22 October 2026. Sizes, sellers, title filters that restate the page, the population,
#      a vague price word, a limit written as text; and the checks a form must pass to be
#      used: the shop shows what it needs, its ambiguous words and price word are the
#      question's own, every filter is one its plan carries, a limit is a number below which
#      prices count, an existence question has its limit, a size filter names one size, an
#      availability filter is listed or buyable, no attribute is filtered twice
VERSION = 1

# The clothing listings whose price depends on the size chosen name their sizes S, M, L and
# XL: the options of the shop's configurable attribute apparel_size, read from its database
# on 22 October 2026. The words are the student's list of synonyms (22 October 2026).
SIZES = ("S", "M", "L", "XL")
SIZE_WORDS = {"small": "S", "medium": "M", "large": "L", "extra large": "XL", "extra-large": "XL"}
# A model's availability values, as the rules write them.
AVAILABILITY = ("buyable", "listed")
# What reads as a price limit written as text: "20", "$20", "20.00".
FIGURE_TEXT = re.compile(r"^\s*\$?\s*(\d+(?:\.\d+)?)\s*$")
# An unknown that names the missing limit in other words than "price limit".
PRICE_LIMIT = re.compile(r"\bprice\s+(?:limit|threshold|ceiling)\b", re.IGNORECASE)
# Words a title filter may carry that restate nothing and narrow nothing.
FILLER = frozenset({"the", "a", "an", "of"})
WORD = re.compile(r"[a-z0-9]+")


def words_in(words: str, question: str) -> bool:
    """Whether the words appear in the question as written, case aside, as whole words."""
    if not words.strip():
        return False
    spaced = r"\s+".join(map(re.escape, words.split()))
    return bool(re.search(rf"(?<!\w){spaced}(?!\w)", question, re.IGNORECASE))


def note(evidence: dict, field: str, line: str) -> None:
    """One change, in the form's evidence: several to one field are joined, in order."""
    key = f"normalised:{field}"
    evidence[key] = f"{evidence[key]}; {line}" if key in evidence else line


# ---------------------------------------------------------------------------
# The normalisations

def size_of(value) -> str | None:
    """The shop's name for a size a model wrote another way, or None when it is not one of
    the four: "medium" and "m" are M, "size M" is M, "2 x 9.5L" stays as written."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"^\s*size\s+", "", value, flags=re.IGNORECASE).strip()
    if text.lower() in SIZE_WORDS:
        return SIZE_WORDS[text.lower()]
    return text.upper() if text.upper() in SIZES else None


def sizes(condition: Filter, changes: list[str], evidence: dict) -> Filter:
    """A size filter in the shop's words: one size, as equality. A single value under
    "contains" or "in" is that size; several stay as they are, for the checks to refuse."""
    value, op = condition.value, condition.op
    if op in ("contains", "in"):
        single = value[0] if isinstance(value, tuple) and len(value) == 1 else value
        if not isinstance(single, tuple):
            value, op = single, "="
    named = size_of(value) if op == "=" else None
    if named is not None:
        value = named
    if (op, value) != (condition.op, condition.value):
        line = f"size {condition.op} {condition.value!r} is size = {value!r}"
        changes.append(line)
        note(evidence, "size", line)
    return Filter("size", op, value)


def seller_on(page: page_module.Page, value: str) -> tuple[str | None, str]:
    """The page's own name for a seller a model wrote, and how it was matched: exactly, by
    case, or as whole words inside exactly one of the page's names (or one name inside the
    model's words). None when no name or more than one fits."""
    names = [item.seller for item in page.listings]
    if value in names:
        return value, "exact"
    low = value.lower().strip()
    same = [name for name in names if name.lower() == low]
    if len(same) == 1:
        return same[0], "by case"
    within = [name for name in names
              if words_in(low, name) or words_in(name.lower(), value)]
    if len(within) == 1:
        return within[0], "as whole words"
    return None, (f"matches {len(within)} of the page's sellers ({', '.join(within)})"
                  if within else "matches no seller on the page")


def sellers(condition: Filter, page: page_module.Page | None, changes: list[str],
            evidence: dict) -> Filter:
    """A seller filter as a set of the page's own names. One seller written with "=" or
    "contains" is a set of one, the shape every plan reads. A name the page does not have,
    or has more than one fit for, is kept as written and recorded as unmatched."""
    value = condition.value if isinstance(condition.value, tuple) else (str(condition.value),)
    lines = []
    if condition.op != "in":
        lines.append(f"seller {condition.op} {condition.value!r} is seller in {list(value)!r}")
    mapped = []
    for name in value:
        found, how = seller_on(page, name) if page is not None else (None, "no page to match against")
        if found is None:
            lines.append(f"unmatched: {name!r} {how}")
            found = name
        elif how != "exact":
            lines.append(f"{name!r} is {found!r}, matched {how}")
        if found not in mapped:
            mapped.append(found)
    for line in lines:
        changes.append(f"seller: {line}")
        note(evidence, "seller", line)
    return Filter("seller", "in", tuple(mapped))


def urls(condition: Filter, changes: list[str], evidence: dict) -> Filter:
    """A url filter as a set: one URL written with "=" is a set of one."""
    if condition.op == "in" or isinstance(condition.value, tuple):
        return condition
    line = f"url {condition.op} {condition.value!r} is url in [{condition.value!r}]"
    changes.append(line)
    note(evidence, "url", line)
    return Filter("url", "in", (str(condition.value),))


def restated(page: page_module.Page) -> tuple[set[str], str, str]:
    """The words a title filter would only restate: those every listing's title shares before
    its seller, the product named on the results page, and those the page was searched for.
    With the two phrases, for the evidence. A page read back from a run record keeps no
    title (`page.from_record` gives each listing its seller's name), so there the shared words
    are those of the sellers' names, which a filter on the product never is."""
    names = [item.title.rsplit(" - ", 1)[0] for item in page.listings]
    shared = set.intersection(*(set(WORD.findall(name.lower())) for name in names)) if names else set()
    product = " ".join(word for word in WORD.findall(names[0].lower()) if word in shared) if names else ""
    searched = " ".join(urllib.parse.parse_qs(urllib.parse.urlparse(page.url).query).get("q", []))
    return shared | set(WORD.findall(searched.lower())), product, searched


def restates(value, words: set[str]) -> bool:
    """Whether every word of a title filter's value is one the page already names, a plural
    of one included: "tees" restates "tee"."""
    found = [word for word in WORD.findall(str(value).lower()) if word not in FILLER]
    return bool(found) and all(word in words or (word.endswith("s") and word[:-1] in words)
                               or (word.endswith("es") and word[:-2] in words) for word in found)


def normalise(form: Form, question: str, page: page_module.Page | None) -> tuple[Form, list[str]]:
    """The model's form in the shop's and the page's own words, and a line for each change.

    Sizes are the shop's four. Sellers are the page's names. A title filter that every
    listing on the page meets is dropped, since it narrows nothing. A population "listing"
    with no product page named is the results page. A price word in the unknowns, or an
    ambiguity that is only a price word, is the missing price limit, quoting the question's
    word. A limit written as text is a number. Every change is in the form's evidence too.
    """
    changes: list[str] = []
    evidence = dict(form.evidence)
    words = restated(page) if page is not None else None
    filters = []
    for condition in form.filters:
        if condition.attribute == "size":
            condition = sizes(condition, changes, evidence)
        elif condition.attribute == "seller":
            condition = sellers(condition, page, changes, evidence)
        elif condition.attribute == "url":
            condition = urls(condition, changes, evidence)
        elif condition.attribute == "title" and condition.op in ("=", "contains") \
                and words is not None and restates(condition.value, words[0]):
            names = (f"every listing's title names '{words[1]}'" if words[1] else "")
            searched = f"the results page is the search for '{words[2]}'" if words[2] else ""
            line = (f"dropped title {condition.op} {condition.value!r}: "
                    f"{' and '.join(part for part in (names, searched) if part)}")
            changes.append(line)
            note(evidence, "title", line)
            continue
        elif condition.attribute == "price" and isinstance(condition.value, str) \
                and FIGURE_TEXT.match(condition.value):
            value = float(FIGURE_TEXT.match(condition.value).group(1))
            line = f"price {condition.op} {condition.value!r} is price {condition.op} {value:g}"
            changes.append(line)
            note(evidence, "price", line)
            condition = Filter("price", condition.op, value)
        filters.append(condition)

    population = form.population
    if population == "listing" and not any(f.attribute == "url" for f in filters):
        population = "results"
        line = ("population listing is results: the question names no product page, so the "
                "listings it means are the results page's")
        changes.append(line)
        note(evidence, "population", line)

    unknowns, ambiguities = [], []
    for unknown in form.unknowns:
        if unknown != "price limit" and (form_module.VAGUE_PRICE.search(unknown) or PRICE_LIMIT.search(unknown)):
            line = f"unknown {unknown!r} is the price limit"
            changes.append(line)
            note(evidence, "unknowns", line)
            unknown = "price limit"
        if unknown not in unknowns:
            unknowns.append(unknown)
    for entry in form.ambiguities:
        if form_module.VAGUE_PRICE.search(entry.word):
            line = f"ambiguity {entry.word!r} is a price word with no figure: the price limit"
            changes.append(line)
            note(evidence, "ambiguities", line)
            evidence.setdefault("unknowns", entry.word)
            if "price limit" not in unknowns:
                unknowns.append("price limit")
            continue
        ambiguities.append(entry)
    # The word the threshold ask quotes is the question's own, or there is none to quote.
    if "price limit" in unknowns and not words_in(evidence.get("unknowns", ""), question):
        word = form_module.VAGUE_PRICE.search(question)
        if word is not None:
            line = (f"the price word quoted is {word.group(0)!r}, the question's own"
                    + (f", not {evidence['unknowns']!r}" if evidence.get("unknowns") else ""))
            changes.append(line)
            note(evidence, "unknowns", line)
            evidence["unknowns"] = word.group(0)

    normalised = dataclasses.replace(form, filters=tuple(filters), population=population,
                                     unknowns=tuple(unknowns), ambiguities=tuple(ambiguities),
                                     evidence=evidence)
    return normalised, changes


# ---------------------------------------------------------------------------
# Readings of an ambiguous word

def reads_availability(entry: form_module.Ambiguity) -> bool:
    """Whether a model's ambiguity is the shop's own one: in the menu, or able to be bought
    now. The prompt asks for the readings "listed" and "buyable"; two readings of which one
    names the menu and the other buying are read the same way."""
    readings = [reading.strip().lower() for reading in entry.readings]
    if sorted(readings) == ["buyable", "listed"]:
        return True
    menu = [bool(re.search(r"\b(?:listed|menu)\b", r)) for r in readings]
    buy = [bool(re.search(r"\b(?:buyable|buy|bought|in stock|purchas\w*)\b", r)) for r in readings]
    return len(readings) == 2 and sorted(zip(menu, buy)) == [(False, True), (True, False)]


def availability_ambiguity(form: Form) -> form_module.Ambiguity | None:
    return next((entry for entry in form.ambiguities if reads_availability(entry)), None)


def without_availability(form: Form) -> Form:
    """The form with its availability ambiguities dropped, once a reading settles them."""
    return dataclasses.replace(form, ambiguities=tuple(
        entry for entry in form.ambiguities if not reads_availability(entry)))


def with_reading(form: Form, key: str) -> Form:
    """The form under a reading of the shop's ambiguity, as the rules read a question with
    the reading's sentence written in: availability "listed" for the menu, "buyable" for
    buying, the reading recorded, and the ambiguity it settles gone. Done in code, so a reply
    costs no second call."""
    value = {"menu": "listed", "buyable": "buyable"}[key]
    mark = form_module.READING_MARKS[key]
    filters = tuple(f for f in form.filters if f.attribute != "availability") \
        + (Filter("availability", "=", value),)
    evidence = {**form.evidence, "reading": mark, "filter:availability": mark}
    return dataclasses.replace(without_availability(form), filters=filters, reading=key,
                               evidence=evidence)


# ---------------------------------------------------------------------------
# The checks

def carried(form: Form) -> set[str]:
    """The attributes the plan for this form acts on, so a filter on any other is one the
    plan would drop without a word. The results page shows one advertised price per listing,
    of no particular size, so its plan carries none; a review search carries the text it
    looks for; a lookup carries the listings it names; every other plan the option, its
    availability and a price limit."""
    if form.kind() == "results_page":
        return set()
    if form.population == "reviews":
        return {"review text"}
    named = {"url", "seller"} if form.quantifier == "lookup" else set()
    return named | {"size", "availability", "price"}


def ask_problems(form: Form, question: str, page: page_module.Page | None) -> list[str]:
    """What must hold before the box asks anything from this form: the shop shows what it
    needs (property 5; a model's form never makes the box refuse on its own, see
    `box.decide`), its ambiguous words are the question's own, so the ask quotes the user
    truly, and so is the price word the threshold ask quotes, in a question with no figure."""
    found = [f"the shop does not show {attribute}" for attribute in form_module.not_shown(form, page)]
    for entry in form.ambiguities:
        if not words_in(entry.word, question):
            found.append(f"the ambiguous word {entry.word!r} is not the question's")
    if "price limit" in form.unknowns:
        if not words_in(form.evidence.get("unknowns", ""), question):
            found.append("a missing price limit is named, but no price word of the question")
        if form_module.FIGURE.search(form_module.URL.sub("", question)):
            found.append("a missing price limit is named, but the question gives a figure")
    return found


def plan_problems(form: Form, page: page_module.Page | None) -> list[str]:
    """Why no plan may be composed from this form: the five properties (`form.verify`), and
    what a plan needs of its filters that the rules' forms always give it."""
    found = form_module.verify(form, page)
    seen = set()
    for condition in form.filters:
        if condition.attribute in seen:
            found.append(f"the form filters on {condition.attribute} twice")
        seen.add(condition.attribute)
    for attribute in sorted({f.attribute for f in form.filters} - carried(form)):
        found.append(f"a {form.kind()} plan does not carry a filter on {attribute}")
    limit = form.filter("price")
    if limit is not None and (limit.op not in ("<", "<=") or isinstance(limit.value, bool)
                              or not isinstance(limit.value, (int, float))):
        found.append(f"a price filter is a limit below a figure, not price {limit.op} {limit.value!r}")
    if form.kind() == "exists_price" and limit is None:
        found.append("an existence question about a price names no price limit")
    size = form.filter("size")
    if size is not None and (size.op != "=" or not isinstance(size.value, str)):
        found.append(f"a size filter names one size, not size {size.op} {size.value!r}")
    availability = form.filter("availability")
    if availability is not None and (availability.op != "=" or availability.value not in AVAILABILITY):
        found.append(f"availability is listed or buyable, not {availability.op} {availability.value!r}")
    return found


def problems(form: Form, question: str, page: page_module.Page | None) -> list[str]:
    """Why the box must not use this model form at all, empty when it may: what the asks
    need, and, unless the form names a missing price limit, which the box asks for before
    any plan, what a plan needs. Each problem once, in order."""
    found = ask_problems(form, question, page)
    if "price limit" not in form.unknowns:
        found += plan_problems(form, page)
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------------------
# Reading the question through the model

@dataclasses.dataclass(frozen=True)
class ModelRead:
    """What one call made of the question: the reply, the form as the model wrote it, the
    form normalised, each change, and why the box will not use it, None when it may."""
    reply: str | None
    raw: Form | None
    form: Form | None
    changes: tuple[str, ...]
    failure: str | None


def read(question: str, page: page_module.Page | None, call) -> ModelRead:
    """One call through `call(prompt) -> str`, the reply parsed, normalised and checked. A
    call that raises, whatever it raises, is a failed call: the call is the caller's, a
    request to a provider. A reply that is not a form is refused with its fault. A fault in
    the normalising or the checks is a fault of this code, and is not caught."""
    try:
        reply = call(form_module.prompt(question, page))
    except Exception as fault:  # noqa: BLE001  (see the docstring)
        return ModelRead(None, None, None, (), f"the model call failed: {type(fault).__name__}: {fault}")
    try:
        raw = form_module.parse_reply(reply)
    except ValueError as fault:
        return ModelRead(reply, None, None, (), f"the model's reply is not a form: {fault}")
    normalised, changes = normalise(raw, question, page)
    found = problems(normalised, question, page)
    return ModelRead(reply, raw, normalised, tuple(changes), "; ".join(found) or None)
