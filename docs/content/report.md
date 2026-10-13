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

[Table: cell 1, cell 5 and the box, the five gated questions: correct under the key, opened what
it needs, median listings opened, tool calls a run, cost a run. From `make facts` after the
batch is verified.]

[The ambiguous questions under each reading: asked, then correct against that reading's key.]

[Tests by question against cell 1 and cell 5, p by question.]

[What went wrong, run by run, from section D of `make facts`.]

[Cost: the batch's charges against the account.]

This is development: the box was designed on this market, so these are not the claim.

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
