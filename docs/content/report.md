# Progress report 4, 14 October 2026

Status: **skeleton, to be filled on 14 October from verified figures only.** A blank in square
brackets is filled after the verifier has passed the batch it refers to. Sections without
blanks are complete.

## Summary

The box is a step before the shopping agent that reads the question and the first results page, hands the agent a plan or asks the user back, and checks the answer from the page. Its first version ran a two-run pilot on 14 October and got both right, opening 8 listings instead of 15 on the cheapest question for two thirds of the cost of opening everything. Its second version, built the same day, parses any shopping question into a logical form and composes the retrieval from seven primitives, with a model doing the parsing (it agrees with the rules on the plan-deciding fields for 33 of 37 questions) and rules doing everything after. It was measured on the clothing market on 14 October and is now frozen for a fresh one.

## 1. Where we left off on 7 October

Three cells had been run on the clothing market: openJiuwen as shipped, openJiuwen with its
card probe's window limit off, and the second agent. The finding was that the four listing
behaviour comes from one default in the card probe, and that turning it off takes the agent
from opening what the answer needs in 3 of 15 runs to 15 of 15.

## 2. What was re-derived and corrected, 8 to 10 October

- Every figure from cells 1 to 3 was recomputed from the raw run files. Three figures reported
  on 7 October were wrong and are corrected: one scorer rule, one definition, and the second
  agent's repeats, which at temperature 0 are 7 distinct runs of 15.
- Cell 5, openJiuwen told to open everything: 11 of 15 correct under the key, all 15 opened what
  the answer needs, $0.52 a run, three times the shipped agent's cost.
- The project now has one written objective, a lessons file of 32 entries, a workbench that
  refuses any paid command without a verifier pass and a declared cost, and three modules with
  one job each: coder, verifier, insights.
- An independent verifier failed the first write-up four times and passed it on the fifth. What
  it found: the refusal check's replay only worked with two numbers from the answer key, the
  September result was stronger on the page than in the runs, and one quoted figure was wrong.
  All corrected, with the record kept.
- The repository was reorganised, 41 unit tests added, and one site now holds every verified
  figure, generated from the run files.

## 3. The pre-processing box

**The idea.** A step before the agent reads the question and the first results page. It hands
the agent a plan, or asks the user back when the question is ambiguous. After the run, its
refusal check decides from the page alone whether the answer is supported.

**What each error kind gets.** From the 8 October error analysis (`make facts`, section D, cells 1, 2 and 5, distinct runs):

| Error kind in cells 1, 2, 5 | Runs | The box's answer |
| --- | --- | --- |
| Did not open what the answer needs | 9 | The plan lists every listing and its advertised price, and says which to open |
| Read "offer" as "can sell it now" | 8 | The box asks the user which reading they mean |
| Read the price before the page revealed it | 6 | The plan says choose the size, then look again |
| Ran out of 100 steps | 2 | The plan skips listings the advertised price rules out |
| Named a seller that cannot sell M | 1 | The plan says check the size can be chosen |

**Decisions, each with its evidence.** See the "Box v1 spec" page for the eight decisions. The
three that matter most: the page fetched over HTTP shows the same 15 prices the agent's own
probe shows. The refusal check with page-derived numbers refuses 8 of the 9 coverage failures
and no correct answer. The ambiguity rule asks on exactly the two "offer" questions.

## 4. The box on Thornwood, development runs

**The pilot, two runs, 14 October.** Declared $1.05, charged $0.61, both correct, re-derived
from the raw files (`make verify BATCH=experiments/results/20261014T084322`):

| Question | Box | Cell 1, as shipped | Cell 5, told to open everything |
| --- | --- | --- | --- |
| Cheapest buyable M | correct, opened 8 of 15, 40 calls, $0.39 | 0 of 3 correct, opened 4 | 3 of 3 correct, opened 15, about $0.59 a run |
| How many sell M now | correct, opened 15, 33 calls, $0.22 | 1 of 3 correct | 2 of 3 correct, opened 15, about $0.54 a run |

The agent followed the plan: it opened exactly the eight listings advertised at or below the
winning price and skipped the other seven. One run per question, on the market the box was
designed on.

**The development batches, 14 October, 21:31 to 22:28.** Three commands at commit `146c582`, box v6, stamped by the verifier at 21:30 and declared $6, $3 and $2. Charged $4.0702, $2.1899 and $0.7037 (`make verify BATCH=experiments/results/20261014T213118`, `...T220116`, `...T222007`, each read in full, no silence over 60 seconds, every listing count re-derived from the log). The verifier passed the three batches on 20 October. Every figure below is from `make facts`, section H, or `make verify` on the batch named. The caption for all of it: **Thornwood is the market the box's rules were written on, and the rules were corrected again from these runs' failures on 20 October, so this is development, in sample, and not the claim.**

*In plain words, for the student.* On the five questions the earlier cells asked, the box got 13 of 15 right where the shipped agent got 4 and open everything got 11. It opened about half the listings open everything opens, and cost half as much. Two of its three wrong answers were the agent reading a price it had not revealed and testing for a word instead of reading the menu. The box asked back on both "offer" questions every time, asked for a figure on "a cheap tee", and refused "delivers fastest" without spending anything.

*Method and limits, for the supervisor.* 15 runs on 5 questions, three repeats each, all of which differ in tokens and cost. Scored under the key fixed before any run. Two sided exact tests within each question, then combined. Against cells 1 and 5 on the same questions, the same market, the same model and the same browser. In sample for the box, so a small p says only that the pipeline does what it was built to do on this market.

| Arm, the five shared questions | Correct | Opened what it needs | Median listings opened | Tool calls a run | Cost a run |
| --- | --- | --- | --- | --- | --- |
| Cell 1, openJiuwen as shipped | 4 of 15 | 3 of 15 | 4 | 23 | $0.176 |
| Box v2, development, batch `20261014T213118` | 13 of 15 | 14 of 15 | 8 | 29 | $0.258 |
| Cell 5, openJiuwen told to open everything | 11 of 15 | 15 of 15 | 15 | 57 | $0.524 |

The control question, answerable from the results page, 3 of 3. Per question, correct and opened what it needs, of 3: target-price 3 and 3 (8 opened each time), cheapest-target 2 and 2 (6, 8, 8 opened), all-stocked 3 and 3 (1 opened), count-stocked 3 and 3 (15), count-buyable 2 and 3 (15).

| Test, by question | Counts | p, by question | p, pooled |
| --- | --- | --- | --- |
| Box against cell 1, correct | 13 of 15 against 4 of 15 | 0.00155 | 0.00251 |
| Box against cell 1, opened what it needs | 14 of 15 against 3 of 15 | 0.00034 | 0.00012 |
| Box against cell 5, correct | 13 of 15 against 11 of 15 | 0.63 | 0.65134 |
| Box against cell 5, opened what it needs | 14 of 15 against 15 of 15 | 1.0 | 1.0 |

Under the other reading of "offer" (the two count questions re-keyed), correct is 10 of 15 against cell 1's 5 (p = 0.099) and cell 5's 14 (p = 0.14): the box's runs answered the reading the scripted user gave, so under the other key they are wrong, as they should be.

**The ambiguous questions under each reading.** The box asked on "does every listing offer size M" and "how many listings offer size M" in all 12 of their slots, before any agent ran. With the scripted user answering "menu", 3 of 3 and 3 of 3 correct against the menu key (batch `20261014T213118`). Answering "buyable", 3 of 3 and 3 of 3 against the buyable key, $0.7037 for the six (batch `20261014T222007`). "Is there a cheap Thornwood tee in size M" was asked back for a figure and nothing ran, $0. "Which seller delivers fastest" was refused, with what the shop does show, $0.

**The ten new questions, one run each, batch `20261014T220116`** (`make verify BATCH=experiments/results/20261014T220116 --answers`):

| Question | What the box did | Outcome | Listings opened, needed | Tool calls | Cost |
| --- | --- | --- | --- | --- | --- |
| Any listing with M buyable under $27 | witness plan, cheapest first | correct: yes, Alderney at $25.77 | 8, needs the witness | 26 | $0.300 |
| Any listing with M buyable under $25 | witness plan | correct: no, after the 7 advertised under $25 | 7, needs 7 | 36 | $0.287 |
| The three cheapest sellers for M | top-k bound and prune | **wrong**: Alderney, then Oakhurst and Lymington, two sellers that cannot sell M, at their advertised prices | 12, needs 12 | 45 | $0.429 |
| Copperfield or Elmsworth, cheaper for M | lookup of the two | correct: Elmsworth $28.96, Copperfield $29.66 | 2, needs 2 | 20 | $0.103 |
| Cheapest seller for XL | bound and prune on XL | correct: Ivybridge $18.08 | 3, needs 3 | 24 | $0.254 |
| Delivers fastest | refused: the shop does not show delivery | no run | | | $0 |
| A cheap tee, no figure | asked for a limit | no run | | | $0 |
| The softest tee | fell back to the survey plan | no answer: "no softness attribute on any of the 15 pages", unscored | 15 | 95 | $0.796 |
| A four line poem about shoes | bypassed, question unchanged | wrote the poem into a `data:` page it composed, unscored | 0 | 6 | $0.013 |
| The capital of Portugal | bypassed | answered Lisbon from the model, and its 6 navigations to google, bing and wikipedia were blocked (`net::ERR_BLOCKED_BY_CLIENT`), unscored | 0 | 4 | $0.009 |

**What went wrong, run by run**, by the written rules in `cell_facts.error_kinds` (`make facts`, section H):

| Run | Kinds | What the answer said |
| --- | --- | --- |
| cheapest-target-1 | did not open what the answer needs, and read the price before the page revealed it | Copperfield at $23.40, its advertised price, after 6 of the 8 listings its bound required |
| count-buyable-2 | tested for the word "disabled" on 12 of 15 listings and never read the menu, so an absent size counted as available | 10, where 5 is right |
| top-3-1 | named a seller that cannot sell M | Oakhurst and Lymington ranked second and third at their advertised prices |

The box's own answer check was off in these batches. Replayed from the logs (`python3 experiments/analysis/replay_box.py experiments/results/20261014T213118 experiments/results/20261014T220116 experiments/results/20261014T222007 --rows`): 32 runs, the stored text reproduced from each record, it refuses 0 of the 3 wrong answers and 1 of the 29 others (`20261014T222007/apparel-all-stocked-1`, whose only view of its counterexample's menu was a cut excerpt). The misread advertised price in cheapest-target-1 is invisible to any check that reads only the page, as the 14 October replay over cell 1 had already shown for one run.

**Cost.** Charges $6.9638 for the three batches against $11 declared. The account reading stored with the runs moved from $57.2861 before the first to $64.1931 at the last, $6.9071, with that last reading taken before the final run's own charge settled. A live reading on 20 October gives $64.2499, so the account moved $6.9638, the charges to the cent, and $35.75 of the $100 remains (Results page, the development block's cost table). Cell 5 cost $0.524 a run on the same five questions, the box $0.258.

**What it means for the box.** The bound did its work on the price questions (8 opened where 15 is everything, and the right 8), the ambiguity rule asked where it should and nowhere else, and the fifth property refused the one question the shop cannot answer. The three failures are the agent's reading, not the plan's coverage, and they are what box v7 to v9 answer on 20 October: a count run must read the menu, a ranked answer's every seller must have been seen with the size chosen, and the box's check now reads the menus from the log.

Next, in the objective's order: freeze (done, box v9), generate the fresh clothing market and verify it in a browser, then the claim run.

## 4a. Box v2, the strategist

v1 is the floor: four fixed strategies for four kinds of question. v2 is what the project
claims to build, designed on 14 October after the research (the "Research" and "Box v2" pages):

- Every question parses into a logical form: a quantifier (exists, every, cheapest, top-k,
  count, lookup), the attribute compared, the filters, and the population. The research census
  shows the shopping benchmarks' reading tasks all have one of these forms.
- A model does the parsing, because that is judgement. Rules do everything after: the plan is
  composed from seven retrieval primitives whose stop rules are theorems (a bound prunes, one
  counterexample refutes, one witness proves, a count needs everything), verified by five
  properties, the fifth being that every attribute the question needs is shown on this shop.
- The box asks only when the form is underdetermined on this page: which reading of a word,
  which entity, what threshold, or that the shop does not show the attribute at all.

**The census parse, 14 October, 11:20.** The model (Claude Haiku 4.5, temperature 0) wrote the
logical form of all 37 distinct questions, one call each, $0.069 charged, no browser. Compared
with the rules' forms, from `experiments/results/parse-probe-20261014T112047.json`:

| Agreement | Questions |
| --- | --- |
| Same quantifier (the field that picks the primitive) | 34 of 37 |
| Same quantifier and objective | 33 of 37 |
| Same on those and the population | 26 of 37 |
| Same on every field | 5 of 37 |

The gap between 33 and 5 is two prompt vocabulary problems, not judgement: the model leaves
the listing's URL out of the filters in 8 of the 9 forms where the rules include it, so 7 of
its single-listing forms fail "a lookup names no listing", and it writes "listing" as the
population where the rules write "results" in 7 cases. Both are fixes to the prompt. The four
real disagreements: "which of these two sellers is cheaper" (rules: look up both named pages,
the model: the cheapest, naming no page, so its form alone does not say what to open), "is the
1 kg size the cheapest per kg" (rules right: it needs every size's rate, and the model proposed a
lookup), "list every pack size and its price" (the model invented an attribute "pack size and
price" and was refused by the fifth property, which is the property doing its job), and the
Calderwood cheapest question (the model chose "advertised price", the rules "price": the rules
are right). In sample for the rules, which were written on these 37 questions.

Cost per question: $0.0019 on average, so a model parse adds about a fifth of a cent to a run
that costs $0.20 to $0.50.

## 4b. Is this only an openJiuwen problem? The second agent and the second model

The question has two parts, and the two agents answer them differently (`make facts`, sections
A, B and D).

**Stopping at four listings is openJiuwen's.** The second agent, same model, same window and
step budget, no card probe, reads the page as text. It opened what the answer needs in 12 of 15
runs under the answer key and in 15 of 15 under the "can sell now" reading, with a median of
15 listings opened, against 3 of 15 for openJiuwen as shipped (p = 0.031 by question, on its 7
distinct runs, under both readings). It is also the cheapest arm, $0.132 a run against $0.176.
The scaffold with no card probe did not under-retrieve on this market.

**The other two failures are not.** The second agent's wrong answers were the two kinds that do
not depend on the scaffold: it read "offer" as "can sell it now" on the count question, and it
read a price before the page revealed it on the cheapest question. Those are the box's ask-back
and "choose the size, then look again" steps, which apply to any agent.

**The model matters too.** On 18 September DeepSeek V4 Flash ran openJiuwen as shipped on the
held-out water market, four runs: it opened 10, 7, 10 and 4 listings where Claude Haiku opens 4
on nearly every failing run, and the run that opened 4 was one of its two wrong ones. So the
four listing stop is the card probe's default together with how far the model trusts it, not
the probe alone.

**Limits.** The second agent samples at temperature 0, so its 15 runs are 7 distinct ones, and
it has no ten minute clock. Its first twelve runs in September were void from a link cap of
mine, which is on record. One market, in sample. The test that would settle the box's claim to
be agent-independent is the box in front of the second agent, the week 3 stretch goal.

## 4c. How the box is built, and what in it is a model

Nothing in the box calls a model. Its decisions are written rules: a classifier that reads the
question, a lexicon for the ambiguous verbs, a planner with tables for each kind of question,
the frozen strategy text at version 7, and a parser for the results page. Run it twice on the
same question and page and it produces the same text. The only language model in a run is the
one inside openJiuwen. Version 2 may let a model write the plan from the page, measured against
version 1's plan, and the probe of 18 September is why that waits: the model's one unsound plan
compared an attribute the shop does not publish, which no check could catch.

The code of the box, like the rest of this repository, was written with an AI coding assistant
under the project's own workflow: a coder module writes it, a verifier module checks it against
the raw files and plants faults to prove the tests can fail, and nothing paid runs without the
verifier's pass. That is disclosed here as the engineering method.

## 4d. What this project could give back

Three things built here are reusable, and none has been offered yet. Nothing is claimed as a
contribution unless a pull request is merged (project rule).

| Candidate | Where | What it is | State |
| --- | --- | --- | --- |
| Gated shopping tasks | WebArena-Verified, which "welcome[s] improvements to both the dataset and the evaluation tooling" per its README | The seeded multi-seller markets with per-variant prices and stock, the generators with their rules, the question files with computed answer keys, and the gated theme selected by user agent | Would need the tasks in their JSON format with exact-match evaluators, and a market generated for the purpose |
| The probe fix | openJiuwen, Apache 2.0 | `parse_json_object`: an empty card probe is reported as empty, not as a parse error | A patch in `agent/openjiuwen-local.patch`, never submitted |
| The setup note | WebArena-Verified docs | Rosetta off in Docker Desktop makes Elasticsearch look hung on Apple Silicon | A note in the README, never submitted |

[Decide with the supervisor which, if any, to prepare after the claim run in week 3.]

## 5. What did not work, and limits

In the pilot nothing failed, with two runs that proves little. What the day's checks found: the model parser omits the listing's URL and misnames the population, both prompt fixes, and invented one attribute, which the fifth property caught. V2's stricter "does every" check would have refused 5 of 14 correct bare "No" answers in the old cells, a trade accepted because the box's own text tells the agent to name the counterexample. The bound texts say "at or above" where the check counted "at or below", harmless on this market and fixed for a market with a tie. And the first ambiguity rule fired on two price questions before it was tightened.

In the development batches (section 4), three runs of 26 were wrong, and the fallback plan spent $0.796 and 95 tool calls opening every listing for an attribute no page shows. The check that would have refused the wrong answers was off, and replayed it refuses none of them. On 20 October the verifier's pass on the batches produced box v7 to v9: a bare "No" counts when the log shows a complete menu without the size, a question about an attribute the shop does not show is refused whatever the word, a keyless run that did not finish is unscored, and the listing counter no longer counts a category page (its fourth correction). The verifier then failed the new menu reader twice before accepting it, once for taking a search excerpt for a whole menu and once for taking a depth-cut snapshot for a menu with no sizes. Both are lessons 37 and 38.

Standing limits: one market family, one model, our shop's 60 ms price reveal, the two agents'
different sampling and clocks, the refusal check's one blind spot (a misread advertised price),
shipping cost and combined discounts out of scope.

## 6. Next week

- Box v9 is frozen (20 October). Generate a fresh clothing market with a new seed, seed it,
  verify it in a browser, write its question file with both readings stated before any run.
  Keep four sizes, or first extend the menu reader's excerpt rule, which was validated on a
  four size menu only.
- The claim run: shipped, open everything, and the box, on the fresh market, 3 repeats,
  tested per question. `verify_cells.py` must take the fixture from the batch's own question
  file first.
- Then the review questions, which gate by depth and have never run, the top-k and ranked
  answer limit the top-3 run showed, and the second agent's confinement before any bypassed
  question runs under it.

## 7. Spend

Before 14 October $56.61 of the $100 key used. On 14 October the pilot $0.61 and the census parse $0.07, then the three development batches $4.0702, $2.1899 and $0.7037 (`make verify` on each batch), $6.9638 against $11 declared. The account reading stored with the last run says $64.19 used, taken before that run's own charge settled (the Results page's development block). Nothing was spent on 20 October.
