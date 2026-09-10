# [09-09-2026] FYP Progress Update

**Retrieval Policies for Shopping Agents Under Interaction-Gated Information**

Registered title: *Ambiguity Without Adversary: Why Injection Defences Miss a Common Agent Failure in Commerce.*

---

## Summary

The agent runs end to end against the environment, the RQ2 baseline is measured rather than
assumed, Checkpoint B is finished two weeks early, and **both halves of RQ3 are built and
the efficiency claim is met.**

Three results shape the project. The agent **never** signals uncertainty, in 97 unmodified
runs. Its correctness collapses only when it under-retrieves. And the cross-listing failure
that motivated the project does not reproduce at small scale but does at fifteen listings.

**The contribution now has both halves.** A check that asks whether an answer is supported
by what the run observed, and a policy that chooses what to retrieve from the question
before opening anything. Together they **match exhaustive retrieval on accuracy for 35 per
cent fewer interactions and 33 per cent less money, with no wrong answers in twelve runs**,
and hold on a second market generated after the policy was finished: 7 correct, 1 refused,
0 wrong.

I also published a result and withdrew it the same day, which is written up in section 7b
rather than left out.

Spend to date: **$18.63 of the original $20 plus $21 self-funded**, roughly 190 browser
runs. Thank you for arranging the further credit; the first thing it buys is an exhaustive
arm on the held-out market, without which no saving can be stated there.

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

## 7. RQ3 second half: the efficiency claim, met

The first half establishes that insufficiency is detectable. It does not make anything
cheaper, and was never meant to: the retry arm costs 34 per cent above baseline. The second
half is the part the research question actually asks about, and it is now built and
measured.

### First, an upper bound to measure against

There was no cost axis. The unmodified agent gives one point, cheap and sometimes wrong,
and one point is not a trade-off. So an exhaustive arm was run: the same agent, instructed
to open every listing.

**8 runs, $4.54, 8 of 8 correct, 28.4 actions, $0.568 per run.**

That settled something the project had been assuming. It gets the per-litre question right,
having been wrong in every run of every other arm. So the failure is **not** a reasoning or
arithmetic limitation. The information is reachable, the comparison is within the model's
competence, and the answer costs $0.57. What the unmodified agent lacks is the decision to
go and look.

### The policy

Three strategies, chosen from the wording of the question rather than from the task name:

| Strategy | Triggered by | Why it saves work |
| --- | --- | --- |
| Total bound | "cheapest", "lowest price" | The advertised price is a floor, so a listing already dearer than the best total found cannot win |
| Refutation | "does every listing..." | Proving needs all fifteen; refuting needs one counterexample |
| Rate bound | "per litre", "best value" | The best possible rate is the advertised price over the largest pack |

### The result

| Arm | Correct | Refused | Wrong | Actions | Cost per run |
| --- | --- | --- | --- | --- | --- |
| Unmodified | 64% | 0 | 10 of 28 | 17.7 | $0.276 |
| Exhaustive | 100% | 0 | 0 of 8 | 28.4 | $0.568 |
| **Targeting + gate** | **100%** | 2 | **0 of 12** | **18.4** | **$0.382** |

**It matches the exhaustive upper bound on accuracy for 35 per cent fewer interactions and
33 per cent less money, with no wrong answers in twelve runs.**

The two halves turn out to be complements rather than alternatives. Targeting alone was
wrong four times in eight, because making the cheap answer cheaper does nothing about
asserting the expensive one on no evidence. The gate alone never became cheaper. Together
they have no wrong answers.

### And it holds on a market it has never seen

A second market was generated with a different seed and brand and seeded alongside the
first, so no recorded run lost its ground truth. Different winner, different trap,
different per-litre answer, and a per-litre winner that does not stock the target pack at
all, which is a structure the policy had never met.

**7 correct, 1 refused, 0 wrong.** Across both markets, sixteen of sixteen answers are
either correct or refused.

No saving is claimed from the held-out market. There is no exhaustive arm there, so 15.1
actions has nothing to be divided by, and borrowing a denominator from a different market
is an error I have already made in three other forms this week. That run is the first thing
the new credit should buy.

---

## 7b. A result I published and withdrew the same day

This belongs in the report and I would rather raise it than have it found.

The first version of the targeting arm was recorded as the efficiency claim met: 4 of 4
correct at 7.2 actions against exhaustive's 31.3, a 4.4 times saving. It was wrong.

That version **never enumerated the candidate set.** It read the first four listings on the
search page, treated them as the whole market, and pruned within them. The true winner
happens to sit inside those four, so the answers came out right without the bound doing any
work. Seven actions against thirty-one was not a saving from pruning, it was a saving from
not looking.

Two things about it are worth the space:

- **The sufficiency check caught it and I did not.** `understated_population` fired on
  exactly those runs, because the answers said "I opened 4 listings, all 4 listings were
  checked". The measurement instrument built for the agent turned out to work on its author
- It is the project's own thesis applied to me. A correct-looking result reached from
  insufficient evidence, unnoticed because the answer was right, is precisely the failure
  RQ2 documents

The fix was to make enumeration an explicit first step, since a bound cannot rule out a
candidate that was never enumerated. All the figures in section 7 are from after that fix.

A similar correction happened on the held-out run, in the opposite direction. It reported
three refusals and two were my own bug: both per-litre answers were correct to four decimal
places and were refused for showing their working, because the check read "8.4 litres" as
an unsupported $8.40. That is the same family as the delta misread in section 3, a number
meaning something other than money, this time in my instrument rather than the agent's
answer.

---

## 8. Plan and dates

| Checkpoint | Work | Target | Status |
| --- | --- | --- | --- |
| B | Scale the catalogue; tasks over search pages where exhaustive retrieval is genuinely costly | 23 Sep | **Done 9 Sep**, two weeks early |
| C1 | RQ3 first half: the sufficiency check, as a gate and as a retry, validated out of sample | — | **Done 9 Sep** |
| C2 | RQ3 second half: question-conditioned targeting, against exhaustive and unmodified baselines | 21 Oct | **Done 10 Sep**, six weeks early |
| C3 | Exhaustive arm on the held-out market, so a saving can be stated there | Late Sep | First call on the new credit |
| C4 | The two generalisation checks: a second model, a second scaffold | Early Oct | Not started |
| D | Final report and presentation | Early Nov | |

**The risk has moved again, and this time it is about strength rather than existence.**
Everything is built and nothing is broken. What the results currently lack is weight: twelve
runs on the headline, two markets, one model, one agent scaffold. A reviewer's first three
questions would be whether it is the model, whether it is twelve runs, and whether it is
this one market, and the new credit answers all three.

There is one further honesty point. The strategies are supplied in the prompt and not
enforced, so nothing verifies the agent followed them beyond what its traces show. A
tool-level implementation would be stronger and is a candidate for the remaining time if
the generalisation checks come back clean.

---

## 9. For discussion

1. **The withdrawn result.** Section 7b describes a result I recorded and retracted within
   hours, caught by the project's own checking tool rather than by me. I think it belongs in
   the final report as evidence that the method works, including on its author. Would you
   agree, or does it read as carelessness?
2. **Cost of this class of agent.** A browser agent re-sends the page at every step, so one
   shopping task costs roughly what a whole conversation would. $18.63 covered 120 runs. Is
   the per-run cost itself worth reporting as a result, given the proposal assumed a cheap
   tier that turned out not to work at all?
3. **Reporting soundness alongside accuracy.** One task reaches a correct answer on
   identical evidence to six wrong ones. I would like to report "was this answer earned"
   next to "was it right". Is that a defensible thing to put in the results, given it makes
   the unmodified baseline look worse than its accuracy suggests?
4. The `spConfig` leak means WebArena's gating is weaker than a live marketplace's. Is
   stating it as a limitation sufficient, or is it worth building a harder variant that
   serves variant prices over AJAX?
5. The exhaustive-listing failure — asserting success while returning no data — is a
   reporting failure rather than a retrieval failure. Should it count against the baseline,
   or be reported as a separate category?
6. Two upstream bug fixes are ready. Worth submitting as a pull request for the record, or a
   distraction from the critical path?
7. Is one model (`claude-haiku-4.5`) sufficient for the baseline, or should the final results
   include a second model to show the behaviour is not model-specific?
