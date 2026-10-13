#!/usr/bin/env python3
"""Find a question with two reasonable readings, and write the question back to the user.

"Does every listing offer size M?" has two answers on this shop, because a size can be in
a listing's menu and sold out. Under the menu reading a sold-out size is offered, under the
buyable reading it is not. The key fixed before any run took the first, and every agent
that explained its count took the second (LESSONS 16). The box's job is to notice that
before anything is spent, and ask.

A small lexicon rather than a model: it costs nothing, repeats exactly and can be read. A
question is ambiguous when it names a variant (a size, pack, colour or option) with a verb
that does not say which availability it means, and nothing in it settles the reading. The
first draft matched "seller" through "sell", so every pattern here is a whole word.

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
VARIANT = whole_words(VARIANTS)
CLEAR = whole_words(BUYABLE + MENU)

# The words a verb governs: up to the variant word within a few words of it, and one value
# after it, so "offer size M" and "carry the 500 g pack" are quoted back in the user's own
# words, whatever the size or pack is called. Punctuation ends the phrase.
GOVERNED = re.compile(r"((?:\s+[\w.]+){0,4}?\s+(?:" + "|".join(VARIANTS) + r"))\b",
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


def phrase(question: str) -> tuple[str, str]:
    """The verb and the words it governs, as the question wrote them: ("offer", "size M").

    When no variant word follows any verb closely, the first verb and the first variant
    word stand on their own.
    """
    verbs = list(VERB.finditer(question))
    for verb in verbs:
        tail = question[verb.end():]
        governed = GOVERNED.match(tail)
        if governed:
            value = VALUE.match(tail[governed.end():])
            words = governed.group(1).split() + ([value.group(1)] if value else [])
            return verb.group(0), " ".join(words)
    return verbs[0].group(0), VARIANT.search(question).group(0)


def ask(question: str) -> Ask | None:
    """The question to put to the user, or None when the question settles its own reading."""
    if not VARIANT.search(question) or not VERB.search(question) or CLEAR.search(question):
        return None
    verb, governed = phrase(question)
    quoted = f"{verb} {governed}"
    return Ask(verb=verb, text=ASK.format(verb=verb),
               readings={key: Reading(label, sentence.format(phrase=quoted))
                         for key, (label, sentence) in READINGS.items()})


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
