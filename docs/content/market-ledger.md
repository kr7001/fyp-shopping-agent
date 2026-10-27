# Market ledger source

Extracted from the research log without changing its recorded rows. These historical entries
include dated plans; use the frozen claim protocols for the later experiments.

## Market ledger

A market can be spent once. The moment its failures are examined, any rule written
afterwards is fitted to them, and it stops being able to test that rule. Runs already
recorded against it stay valid as measurements. What is lost is its use as a held-out test.

Keep this table current. It is the only record of which market may still test what.

| Market | Listings | Status | What it may still be used for |
| --- | --- | --- | --- |
| small fixture | 4 | **Development.** Authoring notes removed 13 Sep 2026, everything before that is a different environment | RQ2 baseline. Not a held-out test for anything |
| Rivenhall | 15 | **Development.** The targeting strategies were written and twice corrected against its failures | Cost and action comparisons. Not a held-out test |
| Calderwood | 15 | **Spent 17 Sep 2026.** Held out until then, and its nine failures have now been read, which is what produced the coverage rule | Reporting the held-out result already measured. It cannot test rules version 2 |
| Thornwood, clothing | 15 | **Development since 8 Oct 2026.** Generated on 18 Sep, after the coverage rule was frozen. Cells 1, 2, 3 and 5 were measured on it on 7 and 8 Oct, and strategy v7 and planner v2 were then written from its failures. Box v1's pilot and box v2's three development batches ran on it on 14 Oct, and box v7 to v9 were written from those batches' failures on 20 Oct | Reporting cells 1, 2, 3 and 5, the pilot and the development cell, all in sample for the box. Not a held-out test for anything the box does |
| Calderwood-S | 15 | **Measured 18 Sep 2026** as `Calderwood-gated`, Calderwood's prices with the variant prices suppressed. Its first batch went through a store view, measured two shops at once and is superseded | Reporting the 18 Sep result: hiding the prices changed what the agent did, not whether it was right |
| Fresh clothing market | 15 | **Reserved.** To be generated with a new seed now that box v9 is frozen for it (20 Oct 2026). Four sizes, or the menu reader's excerpt rule is extended first | The held-out test for the box, the claim: shipped, open everything and box v9, three repeats, per question |
| Larchmere, tees and water | 42 | **Development since 22 Oct 2026.** Drawn by the A+ generator with seed 900, prefix IGR-DEV (`env/README.md`): 21 tees and 21 waters over two results pages, the second claim's market shape. The front door's pilot ran on it on 23 Oct | Development only: costs, step and clock limits, and the front door's development. No claim is made on it, and it is not a held-out test for anything |

Two rules follow from the table and are worth stating separately, because both have already
been broken once.

**Freeze before generating.** A rule written after seeing a market's failures cannot be
tested on that market. Write it from the principle, record the version, then generate the
next market.

**One change per comparison.** When the DOM changes, prices stay identical. When the
scaffold changes, the model stays fixed. When the model changes, the scaffold stays fixed.

### The metric that survives a change of scaffold

`actions` counts what `trace_stats.py` classifies from openJiuwen's tool calls, so it is not
comparable across agents that name their tools differently. Two figures are:

| Metric | Where it comes from | Why it transfers |
| --- | --- | --- |
| Listings opened | `sufficiency.listings_opened`, from URLs in the trace | A product page visit is a property of the browser, not of the agent |
| Cost per run | OpenRouter usage delta around the run | Tokens are tokens |

Report those two first when a second scaffold arrives. Actions stay in the tables as a
per-scaffold detail.

---
