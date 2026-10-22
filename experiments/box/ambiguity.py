#!/usr/bin/env python3
"""Find a question with two reasonable readings, and write the question back to the user.

"Does every listing offer size M?" has two answers on this shop, because a size can be in
a listing's menu and sold out. Under the menu reading a sold-out size is offered, under the
buyable reading it is not. The key fixed before any run took the first, and every agent
that explained its count took the second (LESSONS 16). The box's job is to notice that
before anything is spent, and ask.

A small lexicon rather than a model: it costs nothing, repeats exactly and can be read. A
question is ambiguous when a verb that does not say which availability it means governs a
variant (a size, pack, colour or option), and nothing in it settles the reading. Two drafts
were wrong before this one, both found by running the rule over every question in the
project. The first matched "seller" through "sell", so every pattern here is a whole word.
The second asked whenever a verb and a variant word both occurred, and so asked on "across
all their pack sizes, which seller offers the lowest price per litre", where "offers" takes
a price and the question is clear (14 October 2026). So the variant word has to follow the
verb within a few words, and a variant word before the verb is not the verb's object.

    python experiments/box/ambiguity.py "Does every listing carry the 500 g pack?"
"""

from __future__ import annotations

import argparse
import dataclasses
import re

# Verbs that can mean either "is in the menu" or "can sell it now".
VERBS = ("offer", "offers", "offered", "offering",
         "carry", "carries", "carried", "carrying",
         "stock", "stocks", "stocked", "stocking",
         "sell", "sells", "sold", "selling",
         "have", "has", "had", "having")
# The thing whose availability is asked about.
VARIANTS = ("size", "sizes", "pack", "packs", "variant", "variants",
            "colour", "color", "colours", "colors", "option", "options")
# Phrases that settle the reading. The buyable ones say the variant must be sellable now,
# the menu ones say being listed is enough. Either way there is nothing to ask.
BUYABLE = ("in stock", "available to buy", "available for purchase", "can be bought",
           "can actually be bought", "can buy", "can supply", "can actually supply",
           "can ship", "purchasable", "buyable", "right now", "ready to ship")
MENU = ("listed", "lists", "in its menu", "in the menu", "on the menu", "as an option",
        "sold out or not", "even if sold out", "whether or not")


def whole_words(phrases: tuple[str, ...]) -> re.Pattern:
    """Any of the phrases as whole words, with any spacing between the words of one."""
    alternatives = "|".join(r"\s+".join(map(re.escape, phrase.split())) for phrase in phrases)
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


VERB = whole_words(VERBS)
CLEAR = whole_words(BUYABLE + MENU)

# The words a verb governs: the variant word after it, with at most WINDOW words between
# ("offer size M" has none, "stock the 2 x 9.5L pack" has four), and one value after the
# variant word, so the phrase is quoted back in the user's own words whatever the size or
# pack is called. Punctuation ends the phrase, and a variant word before the verb is not
# its object.
WINDOW = 6
GOVERNED = re.compile(r"((?:\s+[\w.]+){0,%d}?\s+(?:%s))\b" % (WINDOW, "|".join(VARIANTS)),
                      re.IGNORECASE)
VALUE = re.compile(r"\s+([A-Z]{1,4}|\d[\w.]*)\b")

ASK = ("Your question says '{verb}'. On this shop a size can be in a listing's menu but "
       "sold out. Do you mean listings whose menu lists the size, sold out or not, or "
       "listings that can sell it now?")
# Each reading: a label, and the sentence added to the question when the user chooses it.
READINGS = {
    "menu": ("listings whose menu lists the size, sold out or not",
             "By '{phrase}' I mean listings whose size menu includes it, whether or not it "
             "is sold out."),
    "buyable": ("listings that can sell it now",
                "By '{phrase}' I mean listings that can sell it now, so a sold-out size "
                "does not count."),
}


@dataclasses.dataclass(frozen=True)
class Reading:
    label: str
    sentence: str


@dataclasses.dataclass(frozen=True)
class Ask:
    verb: str                       # the word the question used
    text: str                       # the question put to the user
    readings: dict[str, Reading]    # keyed "menu" and "buyable"


def phrase(question: str) -> tuple[str, str] | None:
    """The first ambiguous verb that governs a variant, and the words it governs, as the
    question wrote them: ("offer", "size M"). None when no verb governs one."""
    for verb in VERB.finditer(question):
        tail = question[verb.end():]
        governed = GOVERNED.match(tail)
        if governed:
            value = VALUE.match(tail[governed.end():])
            words = governed.group(1).split() + ([value.group(1)] if value else [])
            return verb.group(0), " ".join(words)
    return None


def ask(question: str) -> Ask | None:
    """The question to put to the user, or None when the question settles its own reading."""
    if CLEAR.search(question):
        return None
    found = phrase(question)
    if found is None:
        return None
    verb, governed = found
    quoted = f"{verb} {governed}"
    return Ask(verb=verb, text=ASK.format(verb=verb),
               readings={key: Reading(label, sentence.format(phrase=quoted))
                         for key, (label, sentence) in READINGS.items()})


# The numerical case (box v2, 14 October 2026): a price word with no figure. The threshold
# changes which listings count, and only the user has it. "under $20" is a strict limit
# since form v9 (20 October 2026), so the example says "below it", where it said "at or
# below it" while the box read every limit that way.
THRESHOLD = ("Your question says '{word}' and gives no figure. What is the most you would "
             "pay? Give a limit, such as under $20, and only listings below it will count.")


def threshold_ask(word: str) -> Ask:
    """The question put to the user when the form found a price word with no figure. It
    offers no readings: a limit is a figure the user supplies, not a choice between two, so
    the scripted user's `--reading` cannot answer it and the ask stands as the outcome."""
    return Ask(verb=word, text=THRESHOLD.format(word=word), readings={})


def availability_ask(word: str) -> Ask:
    """The "offer" question for a word a model read as either in the menu or buyable where
    the lexicon found no verb governing a variant (box v13, 22 October 2026): the same
    template and the same two readings, quoting the model's word, so the scripted user's
    `--reading` answers it as it answers the lexicon's."""
    return Ask(verb=word, text=ASK.format(verb=word),
               readings={key: Reading(label, sentence.format(phrase=word))
                         for key, (label, sentence) in READINGS.items()})


# The ask for any other word a model reads two ways (box v13, 22 October 2026). It quotes
# the word and the model's readings and claims nothing about the shop, since only the model
# says the readings differ. It offers no reading a scripted reply could choose, so the ask
# stands as the outcome, as the threshold ask does.
GENERIC = "Your question says '{word}', which could mean {readings}. Which do you mean?"


def generic_ask(word: str, readings: tuple[str, ...]) -> Ask:
    """The question put to the user about a word whose readings the box has no plan of its
    own for: the word and each reading, in the model's words."""
    listed = ", ".join(readings[:-1]) + f" or {readings[-1]}"
    return Ask(verb=word, text=GENERIC.format(word=word, readings=listed), readings={})


def with_reading(question: str, asked: Ask, reading: str) -> str:
    """The question with the chosen reading written into it, so the agent sees no ambiguity."""
    if reading not in asked.readings:
        raise ValueError(f"reading {reading!r} is not one of {sorted(asked.readings)}")
    return f"{question.rstrip()} {asked.readings[reading].sentence}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    args = parser.parse_args()
    asked = ask(args.question)
    if asked is None:
        print("clear: the question settles its own reading")
        return 0
    print(asked.text)
    for key, reading in asked.readings.items():
        print(f"  {key:8} {reading.sentence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
