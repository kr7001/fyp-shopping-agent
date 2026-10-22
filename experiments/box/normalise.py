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

And a model can write a form that contradicts the question's own words: 30 for "under $24",
"<=" for "under", L for "medium", five for "three", the dearest for "cheapest", "listed" for
"in stock", a negation dropped. Every field the rules derive from the words, which their
evidence records, is held against the model's, and every figure, size, seller and negation
the model states must be the question's own (`conflicts`, 22 October 2026, verifier
finding). A form that contradicts them is not used either.

One failure is an answer rather than a misreading: a form that needs an attribute the shop
does not show, and has nothing else wrong with it, by the rules' own check of the page's
attributes. The box then declines the question on the model's form (`declines`, box v15,
22 October 2026), where until then the rules' form decided.

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
import ambiguity  # noqa: E402
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
#   2  22 October 2026, the verifier's audit of 1. An availability ambiguity the question's
#      own words settle takes their reading, where 1 dropped it and so lost "in stock"
#      (`settle`). A form that contradicts the question's words is refused (`conflicts`). A
#      seller the form names must be one the question names in full, and a seller or URL
#      value is a word, never a number turned into one. "x-large" is XL, and a size is one
#      the shop names or a pack size with a figure in it. A title is read only where the
#      page record kept it. A negation is read in the sentences that ask (`asking`)
#   3  22 October 2026, for the second claim run. A form whose one failure is an attribute
#      the shop does not show declines the question (`declines`). And since a model could
#      then decline a question about a price by naming such an attribute, a form that does
#      not ask about a price, where the question's own words do, is refused (`conflicts`)
#   4  22 October 2026, box v17. A title filter is held to the listings the plan would
#      range over: on a page of two products, those of the one the question names, so one
#      naming that product restates them and is dropped, and one that tells the products
#      apart on the whole page is never taken for a restatement of it (`normalise`)
VERSION = 4

# The clothing listings whose price depends on the size chosen name their sizes S, M, L and
# XL: the options of the shop's configurable attribute apparel_size, read from its database
# on 22 October 2026. The words are the student's list of synonyms (22 October 2026), with
# x-large, the same word written short, since 2.
SIZES = ("S", "M", "L", "XL")
SIZE_WORDS = {"small": "S", "medium": "M", "large": "L", "extra large": "XL", "extra-large": "XL",
              "x-large": "XL", "x large": "XL"}
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
    or has more than one fit for, is kept as written and recorded as unmatched. A value that
    is not a word, a number, is left as it is for the checks to refuse, never printed into
    a name (normalisation v2)."""
    if not isinstance(condition.value, (str, tuple)):
        return condition
    value = condition.value if isinstance(condition.value, tuple) else (condition.value,)
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
    """A url filter as a set: one URL written with "=" is a set of one. A value that is not a
    word is left for the checks to refuse."""
    if condition.op == "in" or not isinstance(condition.value, str):
        return condition
    line = f"url {condition.op} {condition.value!r} is url in [{condition.value!r}]"
    changes.append(line)
    note(evidence, "url", line)
    return Filter("url", "in", (condition.value,))


def titles_kept(page: page_module.Page) -> bool:
    """Whether the page holds its listings' titles. One read back from a run record made
    before 22 October 2026 does not (`page.from_record` gives such a listing no title), so
    there only the search word can be known to restate anything."""
    return bool(page.listings) and all(item.title is not None for item in page.listings)


def restated(page: page_module.Page) -> tuple[set[str], str, str]:
    """The words a title filter would only restate: those every listing's title shares before
    its seller, the product named on the results page, and those the page was searched for.
    With the two phrases, for the evidence. A page whose titles were not kept gives the
    search words alone (`titles_kept`)."""
    names = [item.title.rsplit(" - ", 1)[0] for item in page.listings] if titles_kept(page) else []
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


def normalise(form: Form, question: str, page: page_module.Page | None,
              planned: page_module.Page | None = None) -> tuple[Form, list[str]]:
    """The model's form in the shop's and the page's own words, and a line for each change.

    Sizes are the shop's four. Sellers are the page's names. A title filter that every
    listing the plan would range over meets is dropped, since it narrows nothing: every
    listing on the page, or on a page of two products the listings of the one the question
    names (`planned`, `box.Scope`, normalisation v4), so a filter that tells the products
    apart is never taken for a restatement of the whole page. A population "listing" with no
    product page named is the results page. A price word in the unknowns, or an ambiguity
    that is only a price word, is the missing price limit, quoting the question's word. A
    limit written as text is a number. Every change is in the form's evidence too.
    """
    changes: list[str] = []
    evidence = dict(form.evidence)
    held = planned if planned is not None else page
    words = restated(held) if held is not None else None
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
            names = ((f"every listing of the {held.scope} the question names has '{words[1]}' in its title"
                      if held.scope else f"every listing's title names '{words[1]}'") if words[1] else "")
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
    filters, ambiguities = settle(filters, ambiguities, question, changes, evidence)

    normalised = dataclasses.replace(form, filters=tuple(filters), population=population,
                                     unknowns=tuple(unknowns), ambiguities=tuple(ambiguities),
                                     evidence=evidence)
    return normalised, changes


def settle(filters: list[Filter], ambiguities: list, question: str, changes: list[str],
           evidence: dict) -> tuple[list[Filter], list]:
    """An availability ambiguity the question's own words settle (`ambiguity.CLEAR`) takes
    their reading, as the rules read such a question (`form.filters_in`): a menu phrase is
    availability = listed, and a buyable one buyable, the menu first. The prompt tells a
    model that flags the ambiguity to leave availability out, so until normalisation v2,
    which dropped the flag and kept nothing, "in stock" was lost and the count of what can
    be bought became a count of what is listed (verifier finding, 22 October 2026)."""
    # Only a flag on a word of the question: one on a word it never uses is a misreading,
    # which the checks then refuse (`ask_problems`), rather than a reading to settle.
    flagged = next((entry for entry in ambiguities
                    if reads_availability(entry) and words_in(entry.word, question)), None)
    clear = ambiguity.CLEAR.search(question) if flagged is not None else None
    if clear is None:
        return filters, ambiguities
    menu = form_module.MENU_WORDS.search(question)
    buyable = form_module.BUYABLE_WORDS.search(question)
    value, words = ("listed", menu.group(0)) if menu else ("buyable", (buyable or clear).group(0))
    before = next((f for f in filters if f.attribute == "availability"), None)
    line = (f"ambiguity {flagged.word!r} is settled by the question's {words!r}: availability = "
            f"{value}" + (f", where the form said {before.value!r}" if before and before.value != value else ""))
    changes.append(line)
    note(evidence, "ambiguities", line)
    evidence["filter:availability"] = words
    return ([f for f in filters if f.attribute != "availability"] + [Filter("availability", "=", value)],
            [entry for entry in ambiguities
             if not (reads_availability(entry) and words_in(entry.word, question))])


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
    elif size is not None and not (size.value.isalnum() or any(c.isdigit() for c in size.value)):
        # `primitives.option_phrase` would call it "the x-large pack" (normalisation v2).
        found.append(f"a size is one the shop names or a pack size with a figure in it, not "
                     f"size {size.value!r}")
    availability = form.filter("availability")
    if availability is not None and (availability.op != "=" or availability.value not in AVAILABILITY):
        found.append(f"availability is listed or buyable, not {availability.op} {availability.value!r}")
    # A seller or a URL is a word, never a number printed into one (normalisation v2).
    for attribute in ("seller", "url"):
        named = form.filter(attribute)
        if named is not None and not isinstance(named.value, (str, tuple)):
            found.append(f"a {attribute} filter names {attribute}s, not {attribute} {named.op} "
                         f"{named.value!r}")
    return found


# A negation, as a question writes one, and the phrases that hold "no" or "not" without
# negating anything a form carries: "answer yes or no", "no more than $20", "sold out or
# not", "whether or not".
NEGATION = re.compile(r"\b(?:not|no|never|none|nobody|nothing|without|lacks?|lacking|missing|"
                      r"leaves?\s+out|left\s+out|omits?|omitted|excludes?|excluded)\b|n't\b",
                      re.IGNORECASE)
NOT_A_NEGATION = re.compile(r"\byes\s+or\s+no\b|\b(?:no|not)\s+(?:more|less)\s+than\b|\bor\s+not\b",
                            re.IGNORECASE)
# What asks whether something exists: "is there", "are there", "any".
EXISTENCE = re.compile(r"\b(?:is|are)\s+there\b|\bany(?:one|body)?\b", re.IGNORECASE)


def asking(question: str) -> str:
    """The sentences that ask, the ones ending in "?", URLs aside, or the whole text when
    none does. An instruction after the question says how to answer it, and its "not"
    negates nothing a form carries: "Is every size in stock? Answer yes or no, and name any
    size that is not." is the plain universal, which the whole text read as dropping a
    negation (22 October 2026, over every question the project holds; it was the one)."""
    text = form_module.URL.sub(" ", question)
    asked = [sentence for sentence in re.split(r"(?<=[.?!])\s+", text) if sentence.rstrip().endswith("?")]
    return " ".join(asked) if asked else text


def comparable(value):
    """A filter value as two forms are compared on it: a number as a number, so 24 and 24.0
    are one limit, a word as itself, and the values of "in" as a set."""
    if isinstance(value, tuple):
        return frozenset(comparable(v) for v in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return str(value).strip()


def said(condition: Filter) -> str:
    value = list(condition.value) if isinstance(condition.value, tuple) else condition.value
    return f"{condition.attribute} {condition.op} {value!r}"


def figures(question: str) -> set[float]:
    """Every figure the question states, URLs aside: its numbers and its number words."""
    text = form_module.URL.sub(" ", question)
    found = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}
    found |= {float(n) for word, n in form_module.NUMBER_WORDS.items()
              if re.search(rf"\b{word}\b", text, re.IGNORECASE)}
    return found


def sizes_named(question: str) -> set[str]:
    """The shop's sizes the question names, as a size (M, case kept) or by a size word."""
    found = {size for word, size in SIZE_WORDS.items() if words_in(word, question)}
    return found | {size for size in SIZES if re.search(rf"(?<![\w-]){size}(?![\w-])", question)}


def conflicts(form: Form, question: str, page: page_module.Page | None) -> list[str]:
    """How the model's form contradicts the question's own words, empty when it does not
    (normalisation v2, 22 October 2026, verifier finding).

    Every filter the rules derive from the words, which their evidence records under
    "filter:<attribute>", must be the model's too, the same comparison and the same value:
    a limit, its "<" for "under", a size, an availability, the sellers or URLs named. The
    silent default, availability = buyable on an existence question with no availability
    word, is not the question's words and is not held, as `parse_probe.agree` leaves it. A
    review's words are held separately, below, since the rules' clause is a guess at them.
    Then what the rules' form cannot hold the model to, the model may still not invent: the
    direction of a superlative the words chose, a price the words ask about (normalisation
    v3, so a model never declines a price question), the number of a "three cheapest", every
    figure and size the model states, which the question must state, every seller and URL
    the model names, which the question must name in full, and the negation: a universal
    the question writes with "not" or "lacks" is not the plain universal, and a negated
    form needs a question that asks whether some listing lacks something."""
    rules = form_module.from_rules(question, page)
    found = []
    for condition in rules.filters:
        words = rules.evidence.get(f"filter:{condition.attribute}")
        if words is None or condition.attribute == "review text":
            continue
        mine = form.filter(condition.attribute)
        if mine is None:
            found.append(f"the question's {words!r} gives {said(condition)}, and the form has no "
                         f"{condition.attribute} filter")
        elif condition.attribute in ("seller", "url") and isinstance(mine.value, tuple):
            # The rules keep only the names the page has, so a model may name more of the
            # question's, which the box then asks about (`box.unlisted`), but never fewer.
            left_out = comparable(condition.value) - comparable(mine.value)
            if left_out:
                found.append(f"the question's {words!r} names {sorted(left_out)}, which the form "
                             f"leaves out")
        elif (mine.op, comparable(mine.value)) != (condition.op, comparable(condition.value)):
            found.append(f"the question's {words!r} gives {said(condition)}, where the form says "
                         f"{said(mine)}")
    # A direction of price only: the rules make any superlative on an attribute the shop does
    # not show "argmax" of it ("soonest", "the least I'd pay" read as a graded word), which
    # says nothing of cheapest or dearest.
    cheapest, dearest = ("argmin", "topk"), ("argmax",)
    priced = ("price", "advertised price", "rate")
    if rules.objective in priced and form.objective in priced and (
            (rules.quantifier in cheapest and form.quantifier in dearest)
            or (rules.quantifier in dearest and form.quantifier in cheapest)):
        asked = "cheapest" if rules.quantifier in cheapest else "dearest"
        other = "dearest" if asked == "cheapest" else "cheapest"
        found.append(f"the question's {rules.evidence.get('quantifier')!r} asks for the {asked}, "
                     f"where the form asks for the {other}")
    # A price the question's own words ask about (normalisation v3): "cheapest", "under
    # $24", "per litre". Held only where the rules' evidence is words of the question; their
    # defaults, "a price is asked for" for a lookup and "nothing but a price is asked about"
    # for a listing of everything, are not, and a form may ask about something else there.
    words = rules.evidence.get("objective") or ""
    if rules.objective in priced and form.objective not in priced and words \
            and words.lower() in question.lower():
        found.append(f"the question's {words!r} asks about a price, where the form asks about "
                     f"{form.objective!r}")
    if rules.quantifier == "topk" and (form.quantifier, form.k) != ("topk", rules.k):
        found.append(f"the question's {rules.evidence.get('k')!r} asks for {rules.k}, where the "
                     f"form asks for {form.k if form.quantifier == 'topk' else 'none in particular'}")
    stated = figures(question)
    if form.quantifier == "topk" and form.k is not None and float(form.k) not in stated:
        found.append(f"the form asks for the {form.k} cheapest, a number the question does not state")
    limit = form.filter("price")
    if limit is not None and isinstance(limit.value, (int, float)) and not isinstance(limit.value, bool) \
            and not any(abs(float(limit.value) - figure) < 0.005 for figure in stated):
        found.append(f"the form sets a price limit of {limit.value:g}, a figure the question does "
                     f"not state")
    text = NOT_A_NEGATION.sub(" ", asking(question))
    negation = NEGATION.search(text)
    if form.negated and not (negation and EXISTENCE.search(text)):
        found.append("the form is negated, where the question does not ask whether some listing "
                     "lacks something")
    if form.quantifier == "forall" and not form.negated and negation:
        found.append(f"the question's {negation.group(0)!r} is a negation, which the form's "
                     f"universal drops")
    size = form.filter("size")
    if size is not None and isinstance(size.value, str) and not (
            size.value in sizes_named(question) if size.value in SIZES else words_in(size.value, question)):
        found.append(f"the form asks about size {size.value}, which the question does not name")
    for attribute, named_by in (("seller", lambda name: words_in(name, question)),
                                ("url", lambda url: url in question)):
        condition = form.filter(attribute)
        if condition is not None and isinstance(condition.value, tuple):
            for name in condition.value:
                if not named_by(name):
                    found.append(f"the form names the {attribute} {name!r}, which the question "
                                 f"does not name in full")
    mention = form.filter("review text")
    if mention is not None and isinstance(mention.value, str):
        words = [word for word in WORD.findall(mention.value.lower()) if word not in FILLER]
        if not words or not all(words_in(word, question) for word in words):
            found.append(f"the form looks for {mention.value!r} in the reviews, words the "
                         f"question does not use")
    return found


def declines(form: Form, found: list[str], page: page_module.Page | None) -> list[str]:
    """The attributes the form needs that the shop does not show, when that is all that is
    wrong with it, so the box declines the question on the model's form (box v15, 22
    October 2026; the second claim run's protocol: the model may decline a question only
    when the rules confirm the attribute it needs is not shown on this shop). Empty when
    anything else is wrong, or nothing is.

    The confirmation is the rules' own check, property 5 against the page's attribute list
    (`form.attributes_shown`), never the model's say-so in its unknowns. One consequence of
    it is not another failure: no kind is planned that ranks by an attribute the shop does
    not show. "The price of a sold-out size" is not an attribute the shop lacks but a reading
    of the question, which the box asks about or takes itself, so it never declines."""
    missing = sorted(form.attributes() - form_module.attributes_shown(page))
    if not missing:
        return []
    own = {f"the shop does not show {attribute}" for attribute in missing}
    ranked = form.objective.split(":", 1)[1] if form.objective.startswith("attribute:") else None
    unplanned = f"no plan exists for kind {form.kind()!r}" if ranked in missing else None
    return [] if any(problem not in own and problem != unplanned for problem in found) else missing


def problems(form: Form, question: str, page: page_module.Page | None) -> list[str]:
    """Why the box must not use this model form at all, empty when it may: what the asks
    need, how it contradicts the question's own words, and, unless the form names a missing
    price limit, which the box asks for before any plan, what a plan needs. Each problem
    once, in order."""
    found = ask_problems(form, question, page) + conflicts(form, question, page)
    if "price limit" not in form.unknowns:
        found += plan_problems(form, page)
    return list(dict.fromkeys(found))


# ---------------------------------------------------------------------------
# Reading the question through the model

@dataclasses.dataclass(frozen=True)
class ModelRead:
    """What one call made of the question: the reply, the form as the model wrote it, the
    form normalised, each change, and why the box will not use it, None when it may. And,
    when the one thing wrong is what the shop does not show, those attributes, on which the
    box declines the question (`declines`)."""
    reply: str | None
    raw: Form | None
    form: Form | None
    changes: tuple[str, ...]
    failure: str | None
    declines: tuple[str, ...] = ()


def read(question: str, page: page_module.Page | None, call,
         planned: page_module.Page | None = None) -> ModelRead:
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
    normalised, changes = normalise(raw, question, page, planned)
    found = problems(normalised, question, page)
    return ModelRead(reply, raw, normalised, tuple(changes), "; ".join(found) or None,
                     tuple(declines(normalised, found, page)))
