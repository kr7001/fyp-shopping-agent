# Progress report 4, 14 October 2026

Status: **skeleton, to be filled on 14 October from verified figures only.** A blank in square
brackets is filled after the verifier has passed the batch it refers to. Sections without
blanks are complete.

## Summary

[Three sentences: what the box is, what today's runs showed, what is next.]

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
probe shows; the refusal check with page-derived numbers refuses 8 of the 9 coverage failures
and no correct answer; the ambiguity rule asks on exactly the two "offer" questions.

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

[Table: cell 1, cell 5 and the box on all five gated questions, if the development batch runs:
correct under the key, opened what it needs, median listings opened, tool calls a run, cost a
run. From `make facts` after the batch is verified.]

[The ambiguous questions under each reading: asked, then correct against that reading's key.]

[Tests by question against cell 1 and cell 5, p by question.]

[What went wrong, run by run, from section D of `make facts`.]

[Cost: the batch's charges against the account.]

This is development: the box was designed on this market, so these are not the claim.

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

[From the verified batch: any plan the agent did not follow, any refusal of a correct answer,
anything the page could not tell.]

Standing limits: one market family, one model, our shop's 60 ms price reveal, the two agents'
different sampling and clocks, the refusal check's one blind spot (a misread advertised price),
shipping cost and combined discounts out of scope.

## 6. Next week

- Freeze box v1. Generate a fresh clothing market with a new seed, seed it, verify it in a
  browser, write its question file with both readings stated before any run.
- The claim run: shipped, open everything, and the box, on the fresh market, 3 repeats.
- Then the review questions, which gate by depth and have never run.

## 7. Spend

[Spend today, and the balance, from the account.] Before today: $56.61 of the $100 key used,
$43.39 left.
