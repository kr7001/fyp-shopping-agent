# Objective

## North star

Build and prove a pre-processing box for shopping agents. Given the user's question and the first page, the box decides what must be retrieved and hands openJiuwen a plan, or asks the user back when the question is ambiguous. Success: on markets the box was not tuned on, openJiuwen with the box is more accurate than openJiuwen alone, costs less than opening every listing, and asks back on ambiguous questions instead of answering confidently.

## What counts as progress

- Specifying, building, verifying or measuring the box
- The baselines it is measured against: openJiuwen as shipped, and openJiuwen told to open everything
- The evaluation the claim rests on: questions, markets, scoring, held-out tests
- The tools that keep that work accurate: the workbench, the verifier, the lessons

Anything else waits in `PARKED.md`. Add to it with `/park <idea>`.

## Current milestone

Box v1, for two question types on the clothing market:

1. The cheapest size that can be bought (questions 2 and 3). Open only the listings whose advertised price could still win, choose the size, look again.
2. The ambiguous "offer" question. Ask back before retrieving anything.

Order: a one page spec the user approves, then code, then the verifier, then a small paid test against cell 1 (as shipped) and cell 5 (open everything), then a freshly generated market for the claim.

## Fixed decisions

- openJiuwen is the agent the box serves. The second agent is a robustness check, not a platform.
- The answer key is fixed before any run. Ambiguous questions stay ambiguous: catching them is the box's job.
- A claim needs a market the box was not tuned on.
- No paid run without a verifier pass, a declared cost and the user's yes. The workbench guard enforces it.
