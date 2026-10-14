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
| The coder builds the box, with tests | **Built** overnight from the spec, 90 tests pass, the frozen strategy text proven byte-identical | commits `5cac414` and `45b4425` |
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
| 10 to 12 | The coder builds v2 (the logical form, the primitives, the model parser behind the guard), the verifier checks it. One small paid test proposed: the model parses the 42 census questions, about $0.20 | the guard asks for the yes |
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
measures the thing the project claims. Thornwood stays the development market; the claim market
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

## What is not yet done, in plain terms

- The box has had one pilot of two runs. Every other figure about it is a prediction or a replay.
- The raw logs still live only on this laptop.
- The fresh clothing market is not generated. It is tomorrow's first task after the freeze.
- The September pooling scripts still print their pooled row.
