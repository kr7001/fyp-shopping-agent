# [09-09-2026] FYP Progress Update

**Retrieval Policies for Shopping Agents Under Interaction-Gated Information**

Registered title: *Ambiguity Without Adversary: Why Injection Defences Miss a Common Agent Failure in Commerce.*

---

## Summary

The agent now runs end to end against the environment, the RQ2 baseline is measured rather
than assumed, Checkpoint B is finished two weeks early, and the first half of RQ3 is built
and validated out of sample.

Three results shape the rest of the project. The agent **never** signals uncertainty, in
97 unmodified runs. Its correctness collapses only when it under-retrieves. And the
cross-listing failure that motivated the project does not reproduce at small scale, but
does at fifteen listings.

The RQ3 contribution now has a measured first half. A check that asks whether an answer is
supported by what the run observed, frozen and then tested on runs made afterwards, caught
**3 of 4 failures while blocking 0 of 11 correct answers, at no added model cost**.

Spend to date: **$18.63 of $20** of OpenRouter credit, 120 browser runs. The remaining
**$1.37** does not fund a further experiment arm at all, which is the item I most need to
discuss.

Cost is measured two ways and they disagree. The sum of per-run deltas is $15.94; OpenRouter's own usage for the key is $18.63. The key figure is authoritative and the per-run figures are a lower bound: exploratory runs made before cost capture worked are absent, and a run's delta is read as soon as spend moves rather than once it has fully settled.

---

## 1. Environment: the gap, and closing it

The proposal assumed WebArena could express variant pricing. It cannot, and the audit is
now quantified from the database rather than by inspection:

| Measurement | Value |
| --- | --- |
| Products in catalogue | 104,368 |
| Products of type `configurable` | **0** |
| Select-type custom option values | 425,384 |
| Option values carrying a non-zero price delta | **0** |
| Non-select options carrying a price | **0** |

So the environment had option *variance* but no price *variance*. A shopper could pick a
colour; every choice cost the same, and nothing was hidden behind the click.

Magento 2.4.6 supports configurable products natively, so this was a catalogue gap rather
than a platform limit. I wrote a seeder (`env/seed_variants.py`) that authors the missing
structure over the Magento REST API and writes a ground-truth manifest for every run.

Seeded: **4 configurable parents, 14 variant children, 3 new attributes.** All prefixed
`IGR-`. **No existing WebArena product was modified**, so the benchmark's own catalogue
remains intact and my additions are separable and auditable.

The four families and what each is designed to test:

| Family | Gating | Designed trap |
| --- | --- | --- |
| Cellar Direct water | price by variant | "From" price is the 12 x 550ml pack; cheapest per litre is the 2 x 9.5L |
| Hillside Provisions water | price by variant | Higher headline price, **cheaper** 2 x 9.5L. Card-level comparison ranks the sellers backwards |
| Ridgeway coffee | price by variant | Cost per kg falls then rises; best value is the middle size |
| Northmoor t-shirt | stock by variant | Parent reads In Stock; size M is not |

---

## 2. Environment finding: structured data and a leak

**WebArena publishes no schema.org JSON-LD at all.** Not a wrong `Offer`, not a missing
`AggregateOffer` — zero blocks. So the published lower bound that branch-and-bound assumed
is unavailable here as well as on Shopee, by a different route. It must be parsed from the
rendered page either way.

**Magento leaks every variant price into the page source.** The rendered page shows one
price, but the HTML carries a `spConfig` block with all four. Shopee does not do this; there
the unselected price is genuinely absent until the click.

This needs stating in the writeup, because gating is therefore relative to the observation
channel:

| Channel | Sees all variant prices? |
| --- | --- |
| Rendered DOM / accessibility tree | No, one price |
| Raw HTML source | Yes, all four |

openJiuwen reads the control tree, so the gating holds for the agent under study. The
trace of a successful run confirms it in practice: the agent located the `<select>`,
selected the option and read the rendered price. It never touched `spConfig`. The leak
stayed theoretical, but it is a stated limitation, and WebArena is the easier case.

---

## 3. RQ2 baseline

12 tasks, 11 gated plus one control, 5 repeats each. `claude-haiku-4.5`. 60 runs, $2.98.
Scored automatically against the manifest ground truth.

| | |
| --- | --- |
| Overall | 54 correct, 6 wrong |
| Gated tasks | 49 of 55 correct, 89% |
| Control task | 5 of 5, 1 action per run |
| **Abstentions** | **0 of 60** |

### Finding 1: the agent never signals uncertainty

Zero abstentions in sixty runs. The scorer looks for a wide set of hedges — "unable to",
"could not determine", "insufficient", "unclear" — and none ever fired. Every failure is a
confident assertion.

This answers the second half of RQ2 directly. The agent does sometimes fail to retrieve
gated information, and when it does, it does not say so. There is no uncertainty marker for
a downstream system to act on.

### Finding 2: correctness collapses only under-retrieval

Gated runs bucketed by page-changing actions spent:

| Actions | Runs | Correct | Rate |
| --- | --- | --- | --- |
| 1 | 5 | 2 | **40%** |
| 2 to 3 | 16 | 16 | 100% |
| 4 to 6 | 20 | 18 | 90% |
| 7 or more | 14 | 13 | 93% |

Correct runs spent a median of 5 actions; wrong runs a median of 3.

*Revised 9 September. This bucket originally read 20 per cent with a wrong-run median of
1 action. Both were inflated by a scorer rule that marked an answer ambiguous for naming
both the target price and the surcharge, which is precisely what a correct answer showing
its working does. The drop is softer than first reported and still present.*

The relationship is **not** "more retrieval is better" — past three actions the rate is
flat within noise. It is specifically under-retrieval that predicts failure, and the cliff
sits between one action and two.

This is the RQ3 premise as a measurement rather than an assumption: there is a minimum
retrieval budget below which answers are fabricated, and above which extra interactions buy
nothing.

### Finding 3: failures are delta misreadings, not fabrications

*This finding was corrected on 9 September after re-reading the traces. It was originally
reported as fabrication.*

```
water-a-9l5-price   1 action   "The price of the 2 x 9.5L pack is $15.01"   truth $24.90
water-b-9l5-price   1 action   "The price of the 2 x 9.5L pack is $11.60"   truth $22.50
```

Neither number appears in the page source, which is what originally suggested invention.
The traces show something more specific. Magento labels each variant option with a price
**delta**, and both runs observed exactly that:

```
option seen: "2 x 9.5L +$15.01"     9.89 + 15.01 = 24.90    truth 24.90
option seen: "2 x 9.5L +$11.60"    10.90 + 11.60 = 22.50    truth 22.50
```

Both numbers are correct as surcharges. The agent retrieved the right token and misread
its semantics, reporting a relative value as an absolute one. The label is computed in the
browser from the page's own configuration block rather than written into the HTML, which
is why a source check found nothing while the agent saw it plainly.

A third run on the same task composed the two values correctly and said so, which
identifies composition as the discriminating step rather than retrieval.

This is a sharper result than the original claim. Interaction-gated prices are frequently
expressed *relative to* the visible price, so the gated token is only meaningful in
combination with the headline the agent already had. The resulting error looks like a
price, sits in a plausible range, and appears nowhere on the page, which makes it harder
to detect than either a stale headline or an outright invention.

It also changes what the RQ3 policy must do. A coverage check would pass both failures,
because the required field was observed. What catches them is a consistency check: an
absolute price reported after a delta label was seen must equal base plus delta. That is
verifiable arithmetic needing no further retrieval.

A separate failure mode appeared on the exhaustive task, which asks for every pack size and
price and failed four times in five: the answer asserts *"Successfully listed all pack sizes
and their prices"* and contains no prices. At 5 to 7 actions the retrieval likely happened and
the reporting did not. Worth counting separately.

### Finding 4 (negative): the cross-listing trap did not fire

The task modelled directly on the deployed-assistant failure was correct **5 times out of 5**,
at a mean of 6.4 actions. Given two listings and both URLs, the agent opened each, selected
the variant on each, and named the correct seller and price.

With two listings the comparison is cheap enough that the agent simply does the work. The
live failure occurred over a search page with many sellers, where opening every listing is
expensive. **Reproducing it requires scale, not a better-designed trap.** This is now an
evidence-backed reason to author a larger catalogue rather than a guess.

---

## 4. Infrastructure and incidental findings

**Two upstream openJiuwen bugs**, both patched locally. openJiuwen is Apache 2.0.

1. An empty probe result was reported as a JSON parse error. `extract_json_object` returns
   `{}` for both unparseable text and a valid empty object, and `{}` is falsy, so "this page
   has no cards" was indistinguishable from "this is not JSON". The agent retried the probe
   instead of falling back to a page read.
2. The browser worker's `"ok": false` did not reach the runtime result, which reported
   `ok: true`. A study scoring runs on that field would count a wrong answer as a success.

**The cheap-model assumption in the proposal does not hold.** `gemini-2.5-flash-lite`
fails openJiuwen's structured output contract in under four seconds. `deepseek-chat` and
`qwen3.7-flash` were rate-limited at their upstream providers regardless of account credit —
a direct call to three other models succeeded at the same moment, so this is model-specific
provider capacity, not the account. Current viable floor is `claude-haiku-4.5` at roughly
$0.015–0.10 per run. Budget remains adequate.

**Apple Silicon environment issue resolved.** The August "Elasticsearch hangs" problem was
Docker Desktop running the amd64 image under QEMU rather than Rosetta. Cold boot to cluster
health went from 19 minutes without completing, to 20 seconds. Documented in the README with
the diagnosis and the two theories that were tried and discarded.

**Honest note on method.** The first version of my scorer marked six correct answers wrong
because it penalised any mention of the alternatives — which is exactly what a good
comparison answer does. The rule now treats naming the expected option as decisive. Results
were re-scored from stored records without re-running, and changed verdicts are retained in
`suite.json` as `previous_verdict`.

---

## 5. Checkpoint B: at fifteen listings, the trap fires

The RQ2 cross-listing task scored 5 of 5 because comparing two named listings is cheap.
The live failure happened over a search page with many sellers, where opening everything
is expensive. Reproducing it needed scale rather than a better trap.

`env/generate_catalogue.py` authors fifteen competing listings by rejection sampling over
8,000 attempts against eight validated instance rules, so the generated instance is
guaranteed to have the properties the experiment depends on: a unique winner, a card
probe that gives the wrong answer, a lower bound that prunes some listings but not
enough, and a clear margin. The instance it selected has an **oracle floor of 11 opens of
15**, with 4 listings prunable by the published "from" price.

`env/inspect_storefront.py` reports what the storefront actually shows against what the
fixture claims. It found that search paginates at 12 of 15, and that the winner sits on
page one, so a failure on the headline task is a retrieval failure rather than a
pagination failure. Pagination remains a real cost on the tasks that need every listing.

Scaled baseline, 5 tasks x 3 repeats, $3.13:

| Task | Verdicts | Mean actions |
| --- | --- | --- |
| scaled-headline (control) | 3 correct | 2.0 |
| scaled-cheapest-target | 3 correct | 17.0 |
| scaled-target-price | 3 correct | 22.3 |
| scaled-all-stocked | 1 correct, 2 wrong | 13.7 |
| scaled-best-per-litre | 3 wrong | 12.7 |

The clearest failure is a one-word answer. `scaled-all-stocked` asks whether every listing
stocks the 2 x 9.5L pack. Five of fifteen do not. Runs answered, in full, "Yes", after
opening 4 of 15 listings.

**One caveat I am not quoting as a finding yet.** The per-litre task fails consistently,
but the margin between the right and wrong answers is 2 per cent, so it currently risks
scoring arithmetic precision rather than retrieval. Recorded as an open item. Fixing it
means reseeding, which would invalidate the runs already made against this fixture.

---

## 6. RQ3 first half: making the agent able to say it does not know

RQ2 established that the agent never abstains. That is what makes its failures dangerous,
because a caller cannot tell a one-action guess from a verified answer. The first half of
RQ3 addresses exactly that, and is now built and measured.

`experiments/sufficiency.py` holds five rules that decide whether an answer is supported
by what the run actually observed. All five read only the tool results the run already
produced, so none of them costs a page fetch:

| Rule | Catches |
| --- | --- |
| `delta_as_absolute` | A figure observed only as a surcharge, reported as a total |
| `unsupported_number` | An amount appearing nowhere the run looked |
| `claim_without_content` | A completion claim carrying no figures |
| `unverified_universal` | "Yes" to a question about every listing, having opened some |
| `understated_population` | A comparison the answer itself says covered 4 of 15 |

`experiments/policy.py` applies them two ways. **Gate** replaces an unverified answer with
an abstention naming what could not be confirmed, and issues no browser action, so it adds
no model cost. **Retry** re-asks the task with the reason attached, and pays a full second
run.

### The retry arm works, and its price is the finding

Retry arm on the scaled suite, same fixture, $4.21 against the baseline's $3.13. Wrong
answers fell from **5 to 2** for 34 per cent more spend. All three `scaled-all-stocked`
runs answered a bare "Yes" after opening 4 of 15, all three were flagged, and all three
second attempts returned the correct answer with its evidence:

```
attempt 1   "Yes"                                                      4 of 15 opened
attempt 2   "No. Out of 15 listings, only 10 stock the 2 x 9.5L pack.
             The 5 that do not are: Chandler Wholesale, Pembroke ..."  all 15 opened
```

Nothing was converted from wrong to correct for free. Every conversion cost a second full
run, which is the honest cost of a purely reactive policy and the reason the second half
of RQ3 matters.

### The arm broke my own check, twice, and I would rather report that than hide it

It **blocked a correct answer**. "$17.68, charged by Redhill Stores" is exactly right, and
$17.68 appears nowhere on the page, because it is the $6.82 base plus the $10.86
surcharge. My composition test only exonerated answers that stated their own working, so
an answer giving the total alone was called unsupported. Showing the arithmetic should be
a virtue, not a precondition for being believed.

Fixing that cost recall, 11 of 12 down to 9 of 12, because two of the catches turned out
to be accidental rather than sound. That in turn exposed a class the arithmetic rules
cannot see: an answer whose every figure is observed and correctly combined, over the
wrong set. The agent stated it itself, "determined by analyzing all four sellers", where
there are fifteen. Hence the fifth rule.

### Frozen, then tested on runs that did not exist yet

Both fixes were written from failures in that arm, so their figures were in sample. I
therefore froze the rules at a specific commit, ran a fresh baseline, $3.41, and replayed
the gate over that directory alone:

```
15 baseline runs replayed under the gate

verdict       baseline    gate
-------------------------------
abstained            0       3
correct             11      11
wrong                4       1

wrong answers withdrawn   3 of 4
correct answers withdrawn 0 of 11
added model cost          $0.00, the gate issues no browser action
```

Precision holds at 1.00 across 77 correct runs, in sample and out.

The failure that escaped gives the same wrong answer as the two that were caught, and
differs only in not volunteering how much it had looked at. `understated_population` reads
a claim the agent makes about itself, so an agent that says less is checked less. That is
a real ceiling on the rule rather than a bug in it.

### Gating on retrieval coverage was tested and rejected

The obvious fix is to require the agent to have opened enough listings, since the escaping
run opened 4 against an oracle floor of 11. Across every unmodified run of the two
comparison tasks:

```
correct opens: [1, 4, 4, 8, 12, 13, 14, 14]
wrong   opens: [4, 4, 4, 4, 4, 4]
```

A floor at 11 catches all six failures and blocks three correct answers, trading away the
one property the gate currently has.

**The same numbers give something more useful.** `scaled-best-per-litre` opens exactly 4
listings in all seven runs, right and wrong alike, so its one correct answer rests on the
same evidence as its six wrong ones. Accuracy cannot separate those outcomes because
nothing in the runs separates them. Correctness and soundness are different properties,
and I intend to report both rather than only the first.

---

## 7. What the second half of RQ3 has to beat

The headroom is not correctness. At 89% the unmodified agent is mostly right. The headroom
is that it has no principle for knowing when it has retrieved enough:

- It spends 1 action and misreads a surcharge as a price, or 7 and is right, with nothing
  distinguishing the two beforehand
- Actions past three buy nothing measurable, so a large share of current spend is waste
- It never abstains, so a caller cannot tell a one-action guess from a verified answer

A question-conditioned policy has three targets: eliminate sub-two-action answers, cut runs
spending 7+ actions where 2 suffice, and abstain rather than assert when the budget runs out. The first two of those three are
now done and measured; the third, cutting the cost of a correct answer, is not.

---

## 8. Plan and dates

| Checkpoint | Work | Target | Status |
| --- | --- | --- | --- |
| B | Scale the catalogue; tasks over search pages where exhaustive retrieval is genuinely costly | 23 Sep | **Done 9 Sep**, two weeks early |
| C1 | RQ3 first half: the sufficiency check, as a gate and as a retry, validated out of sample | — | **Done 9 Sep** |
| C2 | RQ3 second half: question-conditioned targeting, plotted against exhaustive and unmodified baselines | Early Oct, report 21 Oct | Not started, budget-blocked |
| D | Final report and presentation | Early Nov | |

**The risk has changed from schedule to budget.** The scheduling risk I flagged last time,
that RQ3 might not start in time, is closed: it started and its first half is measured. What
replaces it is money. The cheap model tier assumed in the proposal does not hold, because
the cheap models could not complete the tasks at all, so every arm is paid for at
`claude-haiku-4.5` rates. **$18.63 of the $20 is spent and the remaining $1.37 does not fund
a further arm at all.**

The targeting experiment needs roughly $10 to run properly: an exhaustive-retrieval arm as
the correct-and-expensive baseline, the targeted policy itself, and repeats sufficient to
separate them. Without a top-up I can still deliver a complete result on the abstention half
of RQ3, but the efficiency half, which is the part that makes it a method rather than a
safety check, would be argued from the oracle floor rather than measured.

---

## 9. For discussion

1. **Budget.** Roughly $10 more of OpenRouter credit would let the targeting arm be
   measured rather than argued. Is a top-up possible, and if not, is a smaller design
   acceptable, for example fewer repeats on two tasks rather than three repeats on five?
2. **Reporting soundness alongside accuracy.** One task reaches a correct answer on
   identical evidence to six wrong ones. I would like to report "was this answer earned"
   next to "was it right". Is that a defensible thing to put in the results, given it makes
   the unmodified baseline look worse than its accuracy suggests?
3. The `spConfig` leak means WebArena's gating is weaker than a live marketplace's. Is
   stating it as a limitation sufficient, or is it worth building a harder variant that
   serves variant prices over AJAX?
4. The exhaustive-listing failure — asserting success while returning no data — is a
   reporting failure rather than a retrieval failure. Should it count against the baseline,
   or be reported as a separate category?
5. Two upstream bug fixes are ready. Worth submitting as a pull request for the record, or a
   distraction from the critical path?
6. Is one model (`claude-haiku-4.5`) sufficient for the baseline, or should the final results
   include a second model to show the behaviour is not model-specific?
