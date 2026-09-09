# [09-09-2026] FYP Progress Update

**Retrieval Policies for Shopping Agents Under Interaction-Gated Information**

Registered title: *Ambiguity Without Adversary: Why Injection Defences Miss a Common Agent Failure in Commerce.*

---

## Summary

The agent now runs end to end against the environment, and the RQ2 baseline is measured
rather than assumed. Sixty scored runs produced two results that shape the rest of the
project: the agent **never** signals uncertainty, and its correctness collapses only when
it under-retrieves. A third result is negative and useful: the cross-listing failure that
motivated the project does not reproduce at small scale.

Spend to date: **$3.75 of $20** of OpenRouter credit, 76 agent runs.

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
| Overall | 53 correct, 6 wrong, 1 ambiguous |
| Gated tasks | 48 of 55 correct, 87% |
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
| 1 | 5 | 1 | **20%** |
| 2–3 | 16 | 16 | 100% |
| 4–6 | 20 | 18 | 90% |
| 7+ | 14 | 13 | 93% |

Correct runs spent a median of 5 actions; wrong runs a median of 1.

The relationship is **not** "more retrieval is better" — past three actions the rate is
flat within noise. It is specifically under-retrieval that predicts failure, and the cliff
sits between one action and two.

This is the RQ3 premise as a measurement rather than an assumption: there is a minimum
retrieval budget below which answers are fabricated, and above which extra interactions buy
nothing.

### Finding 3: failures are fabrications, not misreadings

```
water-a-9l5-price   1 action   "The price of the 2 x 9.5L pack is $15.01"   (truth $24.90)
water-b-9l5-price   1 action   "The price of the 2 x 9.5L pack is $11.60"   (truth $22.50)
```

Neither number appears anywhere on those pages. The agent did not misread the headline
price; it invented a value. One further run reached $22.50 by incorrect reasoning
("base price $10.90 plus additional charge") and was scored ambiguous.

A separate failure mode appeared on the exhaustive task, which asks for every pack size and
price and failed four times in five: the answer asserts *"Successfully listed all pack sizes
and their prices"* and contains no prices. At 5–7 actions the retrieval likely happened and
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

## 5. What RQ3 now has to beat

The headroom is not correctness. At 87% the unmodified agent is mostly right. The headroom
is that it has no principle for knowing when it has retrieved enough:

- It spends 1 action and fabricates, or 7 and is right, with nothing distinguishing the two
  beforehand
- Actions past three buy nothing measurable, so a large share of current spend is waste
- It never abstains, so a caller cannot tell a one-action guess from a verified answer

A question-conditioned policy has three targets: eliminate sub-two-action answers, cut runs
spending 7+ actions where 2 suffice, and abstain rather than invent when the budget runs out.

---

## 6. Plan and dates

| Checkpoint | Work | Target |
| --- | --- | --- |
| B | Scale the catalogue to 30–50 listings; tasks over search pages where exhaustive retrieval is genuinely costly. Completes RQ1 and re-tests the cross-listing trap at scale | 23 Sep |
| C | RQ3 prototype: question-conditioned retrieval policy, plotted against exhaustive and unmodified baselines | Begin early Oct, report 21 Oct |
| D | Final report and presentation | Early Nov |

**Scheduling risk I want to flag.** RQ3 is the contribution and has not started. Checkpoint B
is a means, not the work, so I intend to timebox it to two weeks. If RQ3 is not underway by
early October the project risks delivering a benchmark rather than a method.

---

## 7. For discussion

1. The `spConfig` leak means WebArena's gating is weaker than a live marketplace's. Is
   stating it as a limitation sufficient, or is it worth building a harder variant that
   serves variant prices over AJAX?
2. The exhaustive-listing failure — asserting success while returning no data — is a
   reporting failure rather than a retrieval failure. Should it count against the baseline,
   or be reported as a separate category?
3. Two upstream bug fixes are ready. Worth submitting as a pull request for the record, or a
   distraction from the critical path?
4. Is one model (`claude-haiku-4.5`) sufficient for the baseline, or should the final results
   include a second model to show the behaviour is not model-specific?
