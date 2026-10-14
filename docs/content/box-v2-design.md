# Box v2, the strategist

Status: **designed and built on 14 October 2026.** Steps 1 to 4 of the build order below are commits `fd59b5b`, `25c7656` and `70556af`, 140 tests, with the six clothing questions rendering byte for byte what v1 rendered, so the pilot stands under v2. The verifier checked the build against this page on 14 October: v1 preserved, no answer read, every new statement true of the shop. It passed the census parse and named four fixes before any paid box run, listed with the coder's twelve recorded departures from this page in the README decision log of 14 October.
Box v1 is the measured floor. Version 2 is what the project claims to build: a step that reads
any shopping question, works out what evidence would settle it, retrieves that evidence at the
lowest cost the page allows, asks the user when the question does not settle it, and refuses
an answer the evidence does not support.

## Should the box be an agent? An honest answer

Yes in one place, no in the rest.

**A model should do the parsing.** Turning "which compact keyboard is best for working
remotely, and what does it cost" into a logical form is judgement: which attribute, which
quantifier, which objective, and whether the question is clear. Written rules handle the four
forms the project has met and nothing else, and the research page shows the forms that matter
most in the benchmarks are the ones rules do not cover. The 18 September probe showed a model
writes a sound plan 7 of 8 times when told the soundness properties.

**Rules should do everything after the parse.** The plan is composed from a handful of
retrieval primitives whose stop rules are theorems, not judgements: a lower bound prunes, one
counterexample refutes, one witness proves, a count needs the whole population. The soundness
check, the answer check and the ambiguity test all follow from the form. Three reasons to keep
this symbolic, from the project's own measurements: openJiuwen told to be thorough costs three
times the shipped agent and still makes the ambiguity and reveal errors (cell 5); the model's
one unsound plan in the probe compared an attribute the shop does not publish, and only a check
against the page catches that; and a plan that is the same bytes every time can be audited,
tested and compared across runs, which a loop of model calls cannot.

So the box is "a model proposes, rules verify and execute", the LLM-Modulo pattern applied to
retrieval. It is not a second browsing agent. A fully agentic box would be cell 5 with extra
steps, and cell 5 is the thing the box has to beat.

## The logical form

Every question the research page catalogued parses into one record:

| Field | Values | Example: "cheapest buyable M" |
| --- | --- | --- |
| `quantifier` | lookup, exists, forall, argmin, argmax, topk, count, aggregate | argmin |
| `objective` | the attribute compared or returned: price, availability, rating, size, a review mention, a rate per unit | price |
| `filters` | attribute conditions that a candidate must meet: size M, buyable now, rating at least 4.5, colour, a text mention | size M, buyable now |
| `population` | one listing, the listings on the results page, or reviews of one listing | results page |
| `k` | for topk | |
| `reading` | which reading of an ambiguous word was chosen, or none | |
| `unknowns` | what the page does not show that the form needs | |

The form is data. It is stored in the run record beside the page the box read, so every plan
can be reproduced and every verifier can check what the box believed.

## The parser

Two parsers produce the form, and the second is measured against the first.

1. **Rules**, `form.from_rules(question)`: the v1 classifier extended to fill the record for the
   seven forms in the census. Free, deterministic, the fallback.
2. **A model**, `form.from_model(question, page)`: one call with the form's schema, the page's
   attribute list, and the five soundness properties as instructions. Returns the record, and
   says which words made it choose each field. Any call to it goes through the spend guard.

When the two disagree, the box records both and uses the rules' form, unless the rules return
"unknown", in which case the model's form is used after verification. The disagreement rate is
a measured property, and the questions where the model is right and the rules are not are the
ones that extend the rules next.

## Verification, five properties

The planner's four, and the one the probe showed was missing:

1. A bound is used only over a population that was enumerated.
2. A figure derived from a bound is never reported as a price.
3. A universal claim needs a counterexample or the whole population.
4. The best of a population needs coverage of everything the bound cannot rule out.
5. **Every attribute the form compares or filters on is shown on this shop**, on the results
   page or on a listing page. The box knows which from the page it read and from a short list
   of what a listing page shows. "Which seller delivers fastest" fails here, and the box says
   what is missing instead of planning.

A form that fails verification is never executed. It becomes an ask or a refusal.

## Primitives, and the plans composed from them

| Primitive | Opens | Stops | Answer check |
| --- | --- | --- | --- |
| lookup | the named listing or listings | after reading them | the named pages were opened |
| witness (exists) | candidates in the order most likely to satisfy, cheapest first for price conditions | at the first candidate that satisfies | the witness was opened, or every candidate was |
| counterexample (forall) | any order | at the first candidate that fails | a counterexample was opened, or every candidate was |
| bound and prune (argmin, argmax, topk) | ascending advertised price for argmin | when no unopened candidate can beat the best, or the k-th best | every candidate advertised at or below the answer's price was opened |
| exhaust (count, aggregate) | every candidate | when all are opened | every candidate was opened |
| depth (reviews) | review pages in order | at the first mention, or the last page | the quoted page was read, or every page was |
| filter | applied inside any of the above: from the results page when the attribute is shown there, by opening when it is not | | the filter's attribute was read for each counted candidate |

Composition is the form: `argmin price filter(size M, buyable)` is "bound and prune with two
checks inside each opened listing". `exists price<20 filter(size M)` is "witness, cheapest
first, stop at the first buyable M under 20". `topk 3` is bound and prune to the third best.
The plan is rendered as the preamble the v1 box already writes (the listing count, the
listings by advertised price with URLs) plus the primitive's instruction text, with the stop
rule and the forbidden claims stated.

## Ambiguity, from the form

The box asks when the form is underdetermined in a way that changes the retrieval or the
answer, and only then:

| Kind (DiscoBench's names) | Example | What the box asks |
| --- | --- | --- |
| facet | "offer size M": listed, or can sell now | the two readings, as in v1 |
| entity | "the cheapest tee" when the page shows two product lines | which product |
| numerical | "a cheap one" with no figure, "under about $20" | the threshold |
| attribute not shown | "delivers fastest" | says the shop does not show it, and offers what it does show |

It does not ask when the readings give the same answer on this page, which the box can often
tell: if no listing on the page is sold out in the size asked about, "offer" has one answer.
That rule comes from "Dialogue to Discovery" (ask only when the catalogue splits on the
attribute) and it is what keeps the box from over-asking.

## Questions the box cannot classify

Added on 14 October at the student's request. A question with no recognised shape and no
shopping signal at all (no listing or product URL, no market word, no price, size, stock or
review word) is a **bypass**: the box hands it to the agent unchanged, with no plan and no
preamble, and records that it did. A shopping question whose attribute this shop does not show
is **pushed back**: the box says what the shop does not show and what it does, and nothing
runs. A shopping question with a signal but no recognised quantifier keeps v1's fallback plan
and records that it was a fallback. Every batch counts its asked, refused, bypassed and
fallback runs, so the rate at which questions get past the box is a measured property, and
the bypassed runs are the baseline agent on those questions.

## What stays from v1

The page fetch and parser, the preamble, the scripted user with `--reading`, the refusal check
from the page, the record of what the box read, the tests that plant faults, and the rule that
nothing in the box reads an answer key. v1's four strategies become four of the primitives.

## How v2 is measured

1. **Free, on the census.** Every question in the census is parsed by rules and by the model.
   Agreement rate, the forms that fail verification, the asks raised, each read by hand.
2. **Development, on Thornwood.** The questions v1 ran, plus new ones for the forms v1 lacks:
   an existence question, a top-3, a named comparison, a filtered cheapest. Against cells 1
   and 5 and against v1.
3. **The claim, on a fresh clothing market** generated after v2 is frozen, three arms.
4. **Next**, the review questions, through the depth primitive.

## The build, in order

1. `experiments/box/form.py`: the record, `from_rules`, verification with the fifth property,
   and the page's attribute list.
2. `experiments/box/primitives.py`: the seven primitives with their instruction text, stop rule
   and answer check, and `compose(form, page)`.
3. `box.decide` takes the form path: parse, verify, ask or compose, render. v1's behaviour is
   reproduced byte for byte on the six clothing questions, which a test pins.
4. `form.from_model` behind the spend guard, and the census comparison.
5. New task entries on Thornwood for the missing forms, with keys computed from the fixture by
   the generator, never by hand.

Each step ships with tests where every rule fires and stays quiet, and the verifier passes it
before any paid run.
