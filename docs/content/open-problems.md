# Open problems

Problems that are known and not yet fixed, most important first. Solved ones are the lessons
in `LESSONS.md`, each with the rule it produced. Side ideas are in `PARKED.md`. When one of
these is fixed, move it into the decision log with the date, and take it off this list.

## Nothing about the box is measured on a market it was not tuned on

Box v2's development batches of 14 October ran on Thornwood, the market its rules were written
on, and box v7 to v9 were then corrected from those runs' failures on 20 October. Every figure
about the box is in sample (`make facts`, section H). The fresh clothing market is reserved in
the README's ledger and not yet generated. Box v9 is the frozen version for it. *Next, before
the claim run.*

## The menu reader's excerpt rule was validated on four sizes only

A `browser_find` excerpt counts as a complete size menu only when its option block begins with
the menu's placeholder and ends before the reply does. Validated against the fixture on every
stored run of the three batches, 180 readings, 109 complete and equal to the fixture's menu,
71 partial and a prefix of it (`python3 experiments/analysis/replay_box.py
experiments/results/20261014T213118 experiments/results/20261014T220116
experiments/results/20261014T222007 --menus`). Thornwood's menus have four sizes. On a market
with more, an excerpt would cut the menu more often and a bare "No" would be refused more
often, as `20261014T222007/apparel-all-stocked-1` already is. Either the fresh market keeps
four sizes, or the rule is extended and validated first. *Before the fresh market is drawn.*

## Top-k and ranked answers

The one top-3 run (`20261014T220116/apparel-top-3-1`) ranked Oakhurst and Lymington second and
third at their advertised prices, and neither can sell M. It had opened the 12 listings its
floor required, so the coverage check passes it, and the box's own check, replayed, does not
refuse it. One run of one question. The plan text and the check need a rule that every ranked
seller was seen with the size chosen, and a test that fires on this run. *Before the claim
run, or the top-k question is left out of it and stated as a limit.*

## The second agent is not confined to the shop

openJiuwen on the gated shop runs with `--allowed-origins http://localhost:7770` and, since
`2ce22cf`, `--block-service-workers`. The second agent drives its own browser and has neither,
so `--box` with `--scaffold naive` is refused (`bb89137`) and no bypassed question may run
under it. The project never lets an agent onto a live site. *Before the second agent runs
under the box.*

## One sentence of the frozen strategy text is strictly false

The availability strategy tells the agent that a listing's advertised price "is the cheapest
option in that listing, so nothing inside it can cost less". Magento's "As low as" price is the
cheapest option that can be bought. Fairhaven's sold-out size M costs $15.04 under the default
theme, below its advertised $18.33. In the gated shop the agent cannot see that price and the
bound over buyable options stays sound, so the pilot and the development batches ran on the
frozen v7 text. Reword it to "the cheapest option that can be bought" in strategy v8 before the
claim run, so the claim's arms share one text. Found by the verifier on 14 October. *Before the
claim run.*

## The refusal check's one blind spot, now seen twice

With the market size and the floor read from the page, the check refuses 8 of the 9 coverage
failures in cell 1 and no correct answer. The ninth opened every listing its bound required and
misread an advertised price as the size's price. In the development batch
`20261014T213118/apparel-cheapest-target-1` did the same, naming Copperfield at its advertised
$23.40 after opening 6 of the 8 its bound required, and the box's check, replayed, refuses 0 of
the batches' 3 wrong answers. No check that reads only the page can tell that answer from a
correct one. The plan's "choose the size, then look again" step did not prevent it in 1 of the
6 cheapest runs. *A limit to state.*

## `verify_cells.py` reads Thornwood's answers by name

`experiments/analysis/verify_cells.py` loads `env/fixtures/scaled_apparel.json` directly
(`FIXTURE`, line 40). Run on a batch from the fresh clothing market, it would score against
Thornwood's answers. It must take the fixture from the batch's own question file before the
claim run. *Before the claim run.*

## The raw logs exist only on this laptop

486 run logs, about 1.8 GB, are gitignored because each one replays the whole conversation at
every step. Every "opened what the answer needs" figure and every menu reading is computed from
them, so losing the laptop loses the evidence. Back them up privately, to a drive or a private
cloud folder. Not to GitHub: the repository is public. Count them with
`find experiments/results -name '*.log' | wc -l`. *Overdue since week 1.*

## Two September scripts pool across model and scaffold

`experiments/water/arms.py` and `experiments/water/headline.py` put 4 DeepSeek runs and 12
second agent runs, which were later voided, into the Calderwood "unmodified" row: 28 runs and 9
correct. Like for like, Claude Haiku on openJiuwen, it is 3 of 12. The decision log quotes the
right figure, and the September table on this site is built per model and scaffold. The scripts
themselves still print the pooled row: see `python3 experiments/water/headline.py`. Found during
the reorganisation on 8 October, and left unfixed there because that change was not allowed to
alter any output. *Overdue since week 1.*

## The two agents sample differently, and only one has a clock

openJiuwen runs at temperature 0.2 with top_p 0.1, its shipped default. The second agent runs at
temperature 0, so its 15 runs are 7 distinct ones (`make facts`, section A). openJiuwen also has
a ten minute limit per run and the second agent has none. Re-running the second agent at
openJiuwen's sampling is parked, at about $2.

## "Offer" has two readings

"Does every listing offer size M" and "how many listings offer size M" can mean "has M in its
menu" or "can sell M now". The answer key, fixed before any run, uses the first. Every agent
that explained itself used the second. The wording is kept on purpose: noticing it and asking
back is the box's job, and in the development batches it asked in all 12 slots and a scripted
user answered. Since 20 October the box takes the "can sell now" reading without asking on a
question whose shape compares a price, because the gated page never prints a sold-out size's
price, and records that it chose. Every result is reported under both readings.

## The 60 ms reveal is a property of our shop

The gated theme writes the real price 60 ms after a size changes. One run's own script read the
price before that. Kept, so every cell meets the same page, and stated as a condition of the
environment.

## One local openJiuwen fix may be missing

The decision log for 8 September says two upstream bugs were patched locally. The submodule's
working tree holds only one of them, saved in `agent/openjiuwen-local.patch`. The other, the
worker's `ok: false` not reaching the run result, is not there. The submodule's reflog holds a
commit made inside it by mistake on 9 September and since reset, and its change is the same as
today's patch, so the fix was not in the tree then either. "Never applied" is the likelier
reading. Check whether any scored run depended on it.

## Smaller items

- The box reads results pages only. `suite.py --box --dry-run` crashes in `page.parse` on `tasks.json` and `tasks_reviews.json`, whose questions name a listing or a review page (parked, 20 October). The review questions need the box to read a listing page first
- `env/generate_catalogue.py` tells the user to run `--diagnose`, which it does not define. Open since 13 September
- The surcharge rule `delta_as_absolute` can refuse a correct yes or no answer that quotes "XL +$2.00". Recorded on 14 September and not re-checked since
- `experiments/tasks/tasks_heldout.json` says it was generated from `scaled_water.json`. It regenerates byte for byte from `heldout_calderwood.json`, so the data is right and the note is not
- Shipping cost and discounts after combining items are out of scope. The supervisor asked for this to be stated as a limit in the report
