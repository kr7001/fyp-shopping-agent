# The next five weeks

Three weeks to build and prove box v1, then two to write the report and the presentation.
The dates assume the final presentation falls in the week of 9 November. Move them if the
faculty schedule says otherwise. Every paid step goes through the workbench guard: a verifier
pass, a declared cost, the laptop kept awake, and your yes.

## Week 1, 9 to 15 October: box v1, specified and built

- **Day 1: a one page spec for your approval.** Input: the question and the first results page. Output: a plan handed to openJiuwen, or a question back to the user. Two question types: the cheapest size M that can be bought, and the ambiguous "offer" questions. It lists what the box may never read: the fixture, the answer keys, `_instance`
- **Protect the evidence before spending anything.** Pin the browser tool to the version the runs used instead of `@latest`. Back up the raw logs privately. Fix the two September scripts that pool across model and scaffold. All free
- **Make the free checks show the truth.** `--dry-run` prints the exact text each arm sends, from the same code path the paid loop uses. Done 14 October
- **Coder builds the box**, with a dry run that prints the exact text openJiuwen will receive, and a test where each rule must fire and one where it must stay quiet. Its refusal check takes the market size and the floor from the page, never from the answer key
- **The scripted user.** When the box asks back, a scripted reply picks one reading, and the final answer is scored against that reading's key. Clear questions are the control: the box should not ask on them
- **Verifier pass**, then the stamp
- *Done when:* the spec is approved, the box is committed with its tests, and the verifier has passed it

## Week 2, 16 to 22 October: first measurement, then a fresh market

- **A small paid test on Thornwood.** **Done on 14 October**, ahead of the week: three batches, 32 agent runs, $6.96 charged against $11 declared, verified on 20 October. Box runs only, since cells 1 and 5 already measured the same questions on the same market. Development: Thornwood is in sample for the box, so nothing there is a claim. The record is on the Results page
- **Fix what it shows, then freeze the box** at a version number. **Done on 20 October**: box v7 to v9 from the verifier's findings, frozen at box v9, form v8, primitives v5, scorer v3, rules v4, 254 tests
- **Generate a fresh clothing market** with a new seed, after the freeze, so the box was never tuned on it. Seed it, verify it in a real browser, and write its question file with every reading of "offer" stated before any run. Keep four sizes, or first extend the menu reader's excerpt rule, which was validated on four size menus only (Problems page)
- **Point `verify_cells.py` at each batch's own market**, so the claim run is not scored against Thornwood's answers
- **Strategy v8**, the one false sentence reworded, so the claim's arms share one text
- *Done when:* the box version is frozen, the new market is seeded and verified, and the verifier has passed the claim run's plan

## Week 3, 23 to 29 October: the claim run, verified

- **The claim run on the fresh market:** openJiuwen as shipped, openJiuwen told to open everything, and openJiuwen with the box, on the same questions, three repeats each, compared per question with the stratified exact test. The top-k question goes in only if its ranked answer rule is written and tested first, else it is left out and stated as a limit
- **Verify the outputs:** every answer read in full, the suspended run rule, cost against the account, the menu reader validated against the new fixture
- **Insights:** findings with the command that reproduces each, and the site rebuilt
- **Stretch, only if time and budget allow:** the review questions through the depth primitive, which need the box to read a listing page first, or the box in front of the second agent, which needs that agent's browser confined to the shop first
- *Done when:* the results are verified and on the site, and the code is tagged as the version the report describes. Product and code are locked on 29 October

## Week 4, 30 October to 5 November: the report

- Outline from this site: the problem, the environment, the box, the evaluation, the results, the limits
- The record of what was considered and rejected, from the decision log. The supervisor named this as an example assessment criterion
- State the limits plainly: one market family, one model, our shop's 60 ms reveal, the "offer" wording, the two agents' different sampling and clocks, and shipping cost and combined discounts out of scope, as the supervisor asked
- Every table and figure generated from code
- *Done when:* a full draft is with the supervisor

## Week 5, 6 to 12 November: presentation and final report

- Slides from the report, with the two window demo of the gated shop (`env/demo_gate.py`)
- Rehearse, then revise the report from the supervisor's feedback
- *Done when:* the presentation is given and the repository is tagged at its final state

## Budget

The decision log of 8 October records $43.39 of $100 left. The estimates below use the
measured cost per run of cells 1 and 5. The box's own cost per run is not known until week 2,
so its range runs from the cheapest arm to the dearest.
