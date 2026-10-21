# Week 1 review, and the plan for 14 October

Written overnight on 13 to 14 October for the student's 6 am review, before the 4 pm supervisor
meeting. Everything below that cost nothing has been done. Everything that costs money waits
for the student's yes at 7 am. Figures in this page come from commands named beside them.

## Where week 1 stands

Last week's plan for week 1 (9 to 15 October) had seven items. Status at 2 am on 14 October:

| Planned | Done | Evidence |
| --- | --- | --- |
| A one page spec for the box, for approval | **Drafted**, with the evidence for each of its eight decisions | `docs/content/box-v1-spec.md`, the "Box v1 spec" page |
| Pin the browser tool | **Done**, at 0.0.83. npm's latest is still 0.0.83, the version every cell used, so nothing changes today and nothing can change mid-study | `npm view @playwright/mcp version` |
| Back up the raw logs privately | **Not done.** Needs a drive or a private folder the student chooses. 452 logs, 1.7 GB | `find experiments/results -name '*.log'` lists 452 files |
| Fix the two September scripts that pool across model and agent | **Not done.** Deferred behind the box. The site's September table is built per model and agent already | Problems page |
| `--dry-run` prints the exact text | **Done** | `make dry TASKS=tasks_apparel.json` |
| The coder builds the box, with tests | **Built** overnight from the spec, 90 tests pass, the frozen strategy text proven byte-identical | commits `867851f` and `8adeece` |
| The scripted user | **Done**: `--reading menu` or `--reading buyable` | the spec, decision 4 |
| Verifier pass, then the stamp | **Pending** the build | |

Honest summary for the supervisor: the box is specified and built with 90 passing tests, but no
paid run of it exists yet. That is one week behind the plan's week 2 start, with two days of the week
left. The reasons are recorded: 8 to 10 October went on re-deriving every published figure,
rebuilding the repository and the site, and five verifier passes that found and fixed real
overclaims. That work is what makes the box's measurement trustworthy.

## What the free tests settled

Each decision in the spec was tested before being written down. The results that matter most:

1. **The box can read what the agent reads.** The results page fetched over HTTP, with the
   agent's user agent, has the same 15 sellers at the same advertised prices in the same order as
   the agent's own whole-page card probe in a cell 2 log.
2. **The refusal check works from the page.** Replayed over cells 1, 2 and 5 with the market
   size and the floor taken from the page instead of the answer key, it refuses 8 of the 9
   answers that did not open what they needed, and none of the 26 correct answers. The answer
   key's numbers refuse 9. The miss is a misread advertised price, which the plan's "choose the
   size, then look again" step targets, not the check.
3. **The ambiguity rule asks on the right questions.** On the six clothing questions it asks on
   the two "offer" questions and none of the clear four.
4. **A plan that opens 8 listings should cost about half of opening 15.** Across the 45
   openJiuwen runs on this market, each listing opened costs about 3.6 tool calls and $0.035.
   The regression predicts $0.25 a run at 8 opened and $0.50 at 15 (cell 5 measured $0.52).
   Only one run opened 7 and one opened 14, so the line is drawn mostly between the clusters
   at 4 and 15.

The commands: the replay and the regression are in the box's tests and in
`experiments/analysis/cell_facts.py` after the build. The probe comparison reads
`experiments/results/20261007T115021/apparel-target-price-1.log`.

## The direction, and why

**Build the box as a pre-processing step with written rules, measure it on Thornwood today, and
freeze it tomorrow for a fresh market.** Three directions were considered:

| Direction | For | Against | Decision |
| --- | --- | --- | --- |
| Rules read the page and plan (the spec) | Free, repeatable, auditable, every rule already tested on the stored runs | Each new question kind needs a rule | **v1** |
| A model writes the plan from the page | Generalises to question kinds the rules do not know | Costs per plan, varies between repeats, and on 18 September wrote one sound-looking plan to compare something the shop does not publish | v2, measured against v1 |
| The ask-back goes through openJiuwen's own `ask_user` tool | Closest to how a product would behave | Makes the ask part of the agent's run, so the ask and the run cannot be scored separately | v2 |

Reviews stay out until next week: they gate by depth, the questions exist and have never run,
and the box's first measurement should not mix two gating mechanisms.

## The day

| Time | What | Who |
| --- | --- | --- |
| 6 to 7 am | Review this page, the spec and the build. Decide the two open points below | student, with me |
| 7 to 10 am | The pilot ran at 08:43 (two runs, both correct, below). The student asked for a deeper design before spending more, so the 18 run batch is on hold and the morning went to research and the v2 design instead | done |
| 10 to 12 | v2 built by the coder in three commits, 140 tests, v1's six texts reproduced byte for byte. The verifier is checking it and the one small paid test proposed: the model parses the 37 census questions, declared $0.30 | the guard asks for the yes |
| 12 to 4 pm | The report, from the skeleton on the "Report" page, filling the blanks from verified figures only | student, with me |

**Open point 1: the budget.** $43.39 is left on the key (read from the account on 14 October).
The proposed runs:

| Run | Runs | Estimate | Basis |
| --- | --- | --- | --- |
| Pilot: one price question, one count question, under `--reading menu` | 2 | $1.05 | cell 5's mean cost a run. The verifier's note: these two questions were cell 5's dearer ones, $0.59 and $0.54 a run, so expect about $1.13, up to $1.30 at cell 5's maxima, and about $1.90 if both runs hit the 100 step cap |
| Development batch: the six questions, 3 repeats, `--reading menu` | 18 | $9.45 | the same |
| The two ambiguous questions, 3 repeats, `--reading buyable` | 6 | $3.15 | the same |
| **Today** | **26** | **$13.65** at cell 5's cost, about $6.50 at the regression's | |
| Week 2 and 3 claim run on a fresh market, three arms | 60 | $20 to $31 | the plan's budget table |

The exact commands, in the order they run. Each needs the verifier's stamp at the committed
code, and the guard asks for a yes before anything is spent:

```
IGR_ESTIMATE_USD=1.05 caffeinate -i python3 experiments/runners/suite.py \
    --tasks experiments/tasks/tasks_apparel.json --repeats 1 --box --reading menu \
    --policy gate --only apparel-cheapest-target apparel-count-buyable

IGR_ESTIMATE_USD=9.45 caffeinate -i python3 experiments/runners/suite.py \
    --tasks experiments/tasks/tasks_apparel.json --repeats 3 --box --reading menu --policy gate

IGR_ESTIMATE_USD=3.15 caffeinate -i python3 experiments/runners/suite.py \
    --tasks experiments/tasks/tasks_apparel.json --repeats 3 --box --reading buyable \
    --policy gate --only apparel-all-stocked apparel-count-stocked
```

`--policy gate` switches the box's refusal check on. It adds no browser action and no cost,
and every raw answer stays in the run record, so the batch can be compared with cells 1 and 5
on raw answers and still show what the box would have refused.

The verifier passed the pilot command at the committed code on 14 October at 3 am, with the
held-constant table against cells 1 and 5 built and every intended difference named: the box
hands the agent the listings' URLs and advertised prices, the v7 strategy text, the refusal check
with rules v3, one repeat, and Thornwood is the market the box was designed on, so the pilot is
in sample. After each batch, before any figure is read: `make verify BATCH=experiments/results/<stamp>`
with both answers read in full, the 60 second silence rule, the stored page record against the
live shop, and cost against the account (`python3 experiments/analysis/cell_facts.py`, section G).
Watch the pilot log for the agent trusting its own four card probe over the preamble's fifteen.

**Open point 2, decided at 9 am: v1 is the floor, v2 is the product.** The pilot showed the
agent follows the plan. Rather than spend $13 measuring v1 on all six questions, the budget
waits for v2, which handles every form in the research census, so the development batch
measures the thing the project claims. Thornwood stays the development market. The claim market
is generated after v2 is frozen.

## The pilot ran, 08:43 to 08:48

Two runs, declared $1.05, charged $0.61. Re-derived from the raw files with
`make verify BATCH=experiments/results/20261014T084322`, every answer read, no silence over 60
seconds, both answers correct under the key:

| Question | Answer | Listings opened | Tool calls | Cost | Cell 5 on the same question, 3 runs |
| --- | --- | --- | --- | --- | --- |
| Cheapest buyable M | Alderney Clothing Co at $25.77, "opened 8, skipped 7, rejected 5 as unavailable" | 8, exactly the eight advertised at or below $25.77 | 40 | $0.39 | 3 of 3 correct, 15 opened, about $0.59 a run |
| How many sell M now | 5, naming the five | 15 | 33 | $0.22 | 2 of 3 correct, 15 opened, about $0.54 a run |

The bound did what the spec says: the agent stopped after the listings the advertised prices
could not rule out, and the refusal check from the page passed both answers (population 15,
floor 8 for the price question). One run per question, on the market the box was designed on,
so this is a working pipeline and a direction, not a result.

## The census parse ran, 11:20

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

## The development batches ran, 21:31 to 22:28

Added on 20 October, after the verifier passed the three batches. The student said yes to a
smaller split than the $13.65 proposed above: the six old questions three times under the
"menu" reading, declared $6. The ten new questions once, declared $3. The two "offer"
questions three times under the "buyable" reading, declared $2. All three at commit `146c582`,
box v6, the verifier's stamp of 21:30. Charged $4.0702, $2.1899 and $0.7037, from `make verify
BATCH=experiments/results/20261014T213118`, `...T220116` and `...T222007`.

*In plain words.* On the five questions the earlier cells asked, the box got 13 of 15 right,
opened about half the listings, and cost half of opening everything. It asked back on the
ambiguous questions every time and refused the one the shop cannot answer. Three answers were
wrong, all from the agent's reading rather than the plan's coverage, and one fallback plan
spent $0.80 looking for softness, which no page shows.

*Method.* The figures are `make facts`, section H, on the runs for the questions cells 1 and 5
asked, scored under the key fixed before any run, with two sided exact tests within each
question. In sample on the market the box was designed on, so no claim.

| Arm, the five shared questions | Correct | Opened what it needs | Median opened | Tool calls | Cost a run |
| --- | --- | --- | --- | --- | --- |
| Cell 1, as shipped | 4 of 15 | 3 of 15 | 4 | 23 | $0.176 |
| Box v2, development | 13 of 15 | 14 of 15 | 8 | 29 | $0.258 |
| Cell 5, told to open everything | 11 of 15 | 15 of 15 | 15 | 57 | $0.524 |

Box against cell 1: p = 0.00155 correct, 0.00034 opened what it needs, by question. Against
cell 5: p = 0.63 and 1.0. The ten new questions: four correct (exists under $27 and under $25,
the named pair, cheapest XL, opening 8, 7, 2 and 3 listings), the top-3 wrong (12 opened, two
sellers that cannot sell M ranked at their advertised prices), delivery refused and "a cheap
tee" asked back at $0, the softest tee's fallback plan opened all 15 for $0.796 and gave no
answer, and the two bypassed questions cost $0.013 and $0.009 with every navigation off the
shop blocked. The two "offer" questions under the buyable reading: 6 of 6 correct against that
reading's key, $0.7037. The whole record, every answer included, is on the Results page.

## What is not yet done, in plain terms

- The box has had its pilot and its development batches, all on Thornwood. Nothing about it is
  measured on a market it was not tuned on.
- The raw logs still live only on this laptop.
- The fresh clothing market is not generated. Box v9 is frozen for it on 20 October.
- The September pooling scripts still print their pooled row.
