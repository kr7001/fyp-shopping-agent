# Frozen protocol and analysis plans of the fresh-market studies, 2 November 2026

These three files were committed together on 2 November 2026, before the fresh market Rookmere
(seed 1002) was drawn, and none has changed since.

| File | What it fixed in advance |
| --- | --- |
| [protocol.md](protocol.md) | Why both studies run on a fresh market, how the market is drawn, the order of work, spending limits and reporting rules |
| [analysis-plan-A.md](analysis-plan-A.md) | Study A, Browser Use with and without the block |
| [analysis-plan-B.md](analysis-plan-B.md) | Study B, the full block against a factual briefing without its plan |

They stay at this path because other files cite them there with their SHA-256. The market's
seed-search record (`env/manifests/tee_fresh_2_nov-search.json`) cites the protocol. The task
file `experiments/tasks/matched_briefing_2_nov.json` cites the protocol and plan B, and the
review tool `tools/browser_use_fresh_review.py` pins the protocol and plan A. The six later
amendments and all working notes stayed local. The final report gives the results in Sections
8.4 and 8.5.
