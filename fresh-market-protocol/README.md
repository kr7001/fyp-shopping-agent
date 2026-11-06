# Frozen protocol and analysis plans of the fresh-market studies

These three files were committed together on 2 November 2026, before the fresh market Rookmere
(seed 1002) was drawn, and their content has not changed since.

| File | What it fixed in advance |
| --- | --- |
| [protocol.md](protocol.md) | Why both studies run on a fresh market, how the market is drawn, the order of work, spending limits and reporting rules |
| [analysis-plan-A.md](analysis-plan-A.md) | Study A, Browser Use with and without the block |
| [analysis-plan-B.md](analysis-plan-B.md) | Study B, the full block against a factual briefing without its plan |

They were frozen in `notes/fresh-market-2-nov/` and later moved here with the same bytes. Files
written before the move cite that original path with each file's SHA-256. The market's
seed-search record (`env/manifests/tee_fresh_2_nov-search.json`) cites the protocol, and the task
file `experiments/tasks/matched_briefing_2_nov.json` cites the protocol and plan B. `git log
--follow` shows the move. The six later amendments and all working notes stayed local. The final
report gives the results in Sections 8.4 and 8.5.
