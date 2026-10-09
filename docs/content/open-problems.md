# Open problems

Problems that are known and not yet fixed, most important first. Solved ones are the lessons
in `LESSONS.md`, each with the rule it produced. Side ideas are in `PARKED.md`. When one of
these is fixed, move it into the decision log with the date, and take it off this list.

## The openJiuwen paper is still inside unpushed commits

`openjiuwen.pdf` was committed on 9 September and is no longer tracked, but the 101 unpushed
commits from `af7dc77` to `8957f07` still hold it, and the repository is public. arXiv's licence
lets only arXiv distribute the paper, so pushing this branch as it stands would publish it. Three
ways out: rewrite those commits without it, which changes their hashes, make the repository
private, or keep the branch local. Until one is chosen, `dev` is not pushed. Check with
`git log --oneline -- openjiuwen.pdf`. *Now.*

Two more things a push would publish for the first time, both worth deciding on purpose. The gated
theme's template is derived from Magento's own, under OSL-3.0 and AFL-3.0, and the commits from
18 September carry it without Magento's notice. The notice was restored on 9 October, and a
rewrite could fold it into the older commits too. And `docs/archive/updates/` holds the
supervisor's inline replies to the updates, which have never been on GitHub.

## The refusal check reads the answer key

`policy.gate` passes two numbers from the market's `_instance` to the sufficiency check: how many
listings the market has, and the fewest a sound answer must open. With them, the replay over the
clothing cells refuses all 9 coverage failures in cell 1. Without them it refuses none (checked 9
October). The September gate arms ran the same way. So the check, as built, is an evaluation tool
that knows the answer, not yet part of the box. Box v1 must read both numbers from the page: the
results page shows how many listings there are, and the advertised prices bound how many cannot
be ruled out. *Week 1.*

## `--dry-run` lists the tasks, not what the agent receives

`suite.py --dry-run` prints each task's id and answer kind. The strategy, plan, "open everything"
and confidence wrappers are added only inside the paid loop, so no free command shows the exact
text an agent will receive (LESSONS 17). Build one path that both the dry run and the paid loop
use. *Week 1.*

## `verify_cells.py` reads Thornwood's answers by name

`experiments/analysis/verify_cells.py` loads `env/fixtures/scaled_apparel.json` directly. Run on a
batch from the fresh clothing market, it would score against Thornwood's answers. It must take
the fixture from the batch's own question file before the claim run. *Week 2.*

## The raw logs exist only on this laptop

452 run logs, about 1.7 GB, are gitignored because each one replays the whole conversation at
every step. Every "opened what the answer needs" figure is computed from them, so losing the
laptop loses the evidence. Back them up privately, to a drive or a private cloud folder. Not to
GitHub: the repository is public. Count them with `find experiments/results -name '*.log' | wc -l`.
*Week 1.*

## The browser tool is fetched as "latest" on every run

`experiments/runners/suite.py` starts Playwright MCP as `@playwright/mcp@latest`. Cells 1 to 3
used version 0.0.83 throughout, as the re-derivation of 8 October confirmed. A release in the middle of a batch
would change the tool between runs. Pin it before the box is measured. *Week 1.*

## Two September scripts pool across model and scaffold

`experiments/water/arms.py` and `experiments/water/headline.py` put 4 DeepSeek runs and 12
second agent runs, which were later voided, into the Calderwood "unmodified" row: 28 runs and 9
correct. Like for like, Claude Haiku on openJiuwen, it is 3 of 12. The decision log quotes the
right figure, and the September table on this site is built per model and scaffold. The scripts
themselves still print the pooled row: see `python3 experiments/water/headline.py`. Found during the reorganisation on 8 October, and left
unfixed there because that change was not allowed to alter any output. *Week 1.*

## The two agents sample differently, and only one has a clock

openJiuwen runs at temperature 0.2 with top_p 0.1, its shipped default. The second agent runs at
temperature 0, so its 15 runs are 7 distinct ones (`make facts`, section A). openJiuwen also has a ten minute limit per run
and the second agent has none. Re-running the second agent at openJiuwen's sampling is parked,
at about $2.

## "Offer" has two readings

"Does every listing offer size M" and "how many listings offer size M" can mean "has M in its
menu" or "can sell M now". The answer key, fixed before any run, uses the first. Every agent
that explained itself used the second. The wording is kept on purpose: noticing it and asking
back is the box's job. Every result is reported under both readings.

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

- `env/generate_catalogue.py` tells the user to run `--diagnose`, which it does not define. Open since 13 September
- The surcharge rule `delta_as_absolute` can refuse a correct yes or no answer that quotes "XL +$2.00". Recorded on 14 September and not re-checked since
- `experiments/tasks/tasks_heldout.json` says it was generated from `scaled_water.json`. It regenerates byte for byte from `heldout_calderwood.json`, so the data is right and the note is not
- Shipping cost and discounts after combining items are out of scope. The supervisor asked for this to be stated as a limit in the report
