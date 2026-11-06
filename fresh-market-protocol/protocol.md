# Two supplementary studies on one fresh held-out market, frozen 2 November 2026

Frozen before any seed after 1001 has been drawn, generated or seeded. This file, with
`analysis-plan-A.md` and `analysis-plan-B.md` beside it, is committed before the market
exists, and its SHA-256 is recorded in the market's seed-search record, so a later edit is
detectable. Changes after this commit go into a separate dated amendment file, never into
this one. This is an internal timestamped protocol, not external preregistration.

## Why

`OBJECTIVE.md` asks for claims on markets the box was not tuned on. Two supplementary
results still rest on one already observed market (Quenby, seed 1001):

- **Study A, Browser Use transfer.** The block's transfer to a second agent was shown on
  Quenby only, and repeats 2 and 3 were added after repeat 1 had been seen.
- **Study B, matched briefing.** The 29 October study, the full block against a factual
  briefing of the same candidates, ran on Quenby only.

Both are repeated unchanged, each under its own analysis plan, on ONE freshly drawn
design-B market. The student approved both studies on 2 November 2026. That is approval of
the design, not of a paid launch: each launch needs a verifier PASS bound to its exact
command, configuration and commit, and the student's written approval of that command, its
estimate and its cap.

## The market

- **Generator and rules unchanged.** `env/generate_aplus.py` version 4, design B: one brand,
  45 tee listings from distinct sellers, six sizes XS to XXL, two results pages (36 and 9),
  promo and scarcity labels in the size menus. `env/search_order.py` version 1 predicts the
  order; `env/pick_aplus_market.py` seeds each candidate, reindexes and accepts it only on
  the live pages; `env/generate_aplus_tasks.py` writes the questions and keys. No rule,
  template, block file, prompt, scorer or agent setting is changed for this market.
- **Seed stream.** The claim stream from seed **1002**, the first seed after Quenby's 1001
  (Wexcombe is 1000), with this file as the stream's frozen protocol:
  `--claim --claim-start-seed 1002 --claim-protocol notes/fresh-market-2-nov/protocol.md`.
  The market is the first seed the picker accepts. A rejected seed advances to the next;
  a technical stop retries the same seed; every attempt is written to the search record.
  No rejection is manufactured, no acceptance rule changed, and no seed chosen by any agent
  outcome. Before this commit no fixture or search record in the working tree names a seed
  above 1001, and no commit on any branch adds `"seed": 1002`.
- **Brand.** The first brand that passes the existing brand checks
  (`env/pick_aplus_market.py --check-brands`), in this fixed order: Rookmere, Dunsmere,
  Wendlebury, Ottercombe, Pilsworth. The picker measures the shop's analyzer form itself.
- **Names.** SKU prefix `IGR-FM02`; fixture `env/fixtures/tee_fresh_2_nov.json`; search
  record `env/manifests/tee_fresh_2_nov-search.json`; questions
  `experiments/tasks/tasks_tee_fresh_2_nov.json` and their readings sidecar
  `experiments/tasks/readings_tee_fresh_2_nov.json`, written from the accepted fixture with
  the templates only, no rewordings.
- **The shop.** Seeded into the running shop (container `webarena-shopping`, storefront
  `http://localhost:7770`) beside the earlier markets. The earlier markets are snapshotted
  before seeding and checked unchanged afterwards (`env/check_aplus_market.py --snapshot`,
  then `--unchanged`). The new market must pass `env/check_aplus_market.py` with no failure,
  browser checks included, before any paid call. Study B's launcher repeats the check without
  the browser before its first trial, as it did on 29 October.
- **Held out.** The block, its parser prompt and normalisation, the strategies, the scorer,
  the generator and both agents' settings were all fixed before this market existed, and none
  is tuned on it. Its results are reported on their own and never pooled with Wexcombe,
  Quenby, Thurlby or any earlier study (LESSONS 7 and 19).
- **What the agents see.** Only the question and the pages. No fixture, answer key or
  `_instance` reaches either agent or the block.

## Order of work

1. This protocol commit.
2. The market is drawn, seeded and checked only after it.
3. The code commit: the two launchers parameterised for this market, tests, and free
   previews that show the exact text of every trial and call no model.
4. A verifier PASS on that commit and on each exact launch configuration.
5. The student's written approval of each exact command.
6. **Study B first** (16 openJiuwen trials), **then Study A** (32 Browser Use trials), one
   after the other, never at the same time, from the same checkout at the same commit.
   Nobody browses or changes the shop during a run, and nothing hash-bound in that checkout
   is committed, checked out or edited while a run is active.

**Absolute stop.** No paid call starts or continues after Tuesday 3 November 2026, 12:00
Singapore time, four hours before the talk. Each launcher enforces its own deadline, no
later than this. Slots not reached are reported as not started, never as answers.

## Spending

| Study | Trials | Estimate | Hard cap | Basis of the estimate |
| --- | ---: | ---: | ---: | --- |
| A | 32 | USD 1.50 | USD 3.00 | the repeats 2-3 cohort's 32 trials, USD 1.148 in provider charges (`notes/browser-use-repeat-1-nov/completion-summary.json`) |
| B | 16 | USD 1.20 | USD 2.00 | the 29 October study's 16 trials, USD 1.136 (`experiments/results/matched-briefing-29-oct.status.json`) |

- **A** reserves every request's upper bound before it is sent (the price ceilings times the
  maximum context and output) and refuses a request when charges, requests in flight and
  that bound together would pass USD 3. A charge cannot pass the cap that way.
- **B** keeps the replication guard's local monitor, which reads the account and the
  recorded charges: no new trial when spending plus twice that trial's estimate reaches
  USD 1.50, and a running trial is stopped when spending reaches USD 1.50. The USD 0.50
  between that and the cap covers charges not yet visible (the 29 October study's largest
  trial charged USD 0.194). The account lags, so this is a local stop, not a provider-side
  guarantee.
- Both keep at least USD 20 of key credit (A also its historical USD 0.2117632 unsettled
  reservation), record the provider's charge for every call, run under `caffeinate -i` and
  make no automatic retry. A stops at any unknown charge; B counts an unknown charge as
  unknown, never as zero. At most one separately verified and approved recovery may
  continue unstarted slots after an infrastructure failure, within the same cap. The two
  studies' spending is never pooled into one budget.

## Recorded with every run

In each run's record, or in its launcher's configuration and manifest where the frozen
runner has no field for it: model, sampling settings, step budget, wall clock, probe
setting, shop and theme, scaffold and its version, browser build, provider routing, block,
form, parser prompt and normalisation versions, study identity, configuration hash and
commit.

## Known differences from the earlier runs, stated before launch

- The installed Chrome is build 156.0.8078.79, the build Study A's cohort ran. Study B's
  29 October runs recorded build 156.0.8078.49; Chrome has since updated itself, so B runs
  on a patch-level later build, recorded in its manifest.
- The market itself, by design. Every other condition is the earlier one, as each analysis
  plan's identity table lists.

## Reporting and interpretation

Each study follows its own analysis plan. The student's blind human grades are the verdicts
of record; the frozen automatic scorer's verdicts are kept separately and disagreements
listed. Every scheduled slot is reported, failures included; no answered or failed slot is
replayed to improve it. One market from one generator family, one model, one executor per
study: no claim beyond them, no claim of equivalence from a non-significant difference, and
no pooled headline across markets, studies or agents.
