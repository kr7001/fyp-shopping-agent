# Open problems

Problems that are known and not yet fixed, most important first. Solved ones are the lessons
in `LESSONS.md`, each with the rule it produced. Side ideas are in `PARKED.md`. When one of
these is fixed, move it into the decision log with the date, and take it off this list.

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
worker's `ok: false` not reaching the run result, is not there. Either it was lost or never
applied. Check whether any scored run depended on it.

## Smaller items

- `env/generate_catalogue.py` tells the user to run `--diagnose`, which it does not define. Open since 13 September
- The surcharge rule `delta_as_absolute` can refuse a correct yes or no answer that quotes "XL +$2.00". Recorded on 14 September and not re-checked since
- `experiments/tasks/tasks_heldout.json` says it was generated from `scaled_water.json`. It regenerates byte for byte from `heldout_calderwood.json`, so the data is right and the note is not
- Shipping cost and discounts after combining items are out of scope. The supervisor asked for this to be stated as a limit in the report
