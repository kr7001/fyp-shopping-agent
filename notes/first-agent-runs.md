# First openJiuwen runs against the seeded environment

2026-09-08. Model `deepseek/deepseek-chat` via OpenRouter. Logs in `experiments/runs/`.

## Runs

| # | Task | Result | Time |
| --- | --- | --- | --- |
| 1 | Price of 2 x 9.5L on `IGR-WATER-A` | `ok:false` "Failed to parse browser_probe_cards result JSON" | 30.9s |
| 2 | Same, after local patch | `ok:false` "No cards found on the page." | 19.3s |
| 3 | List products for search `Glenmoor` | Failed, OpenRouter 429 upstream rate limit | 10.1s |
| 4 | Same, retried | `ok:true`, **"No products found"** — wrong | 23.5s |
| 5 | Same, with full trace captured | `ok:true`, same wrong answer | 18.3s |

Infrastructure works: Playwright MCP loads ~70 browser tools, the browser drives, pages
load, the model is called. openJiuwen runs against WebArena. Critical path cleared.

## Finding 1: empty probe result reported as a parse error

`runtime.py` did:

```python
parsed = extract_json_object(raw)
if not parsed:
    return {"ok": False, "error": "Could not parse browser_probe_cards result JSON", ...}
```

`extract_json_object` returns `{}` both for unparseable text and for a valid empty object,
and `{}` is falsy, so "the page has no cards" was indistinguishable from "this is not
JSON". Verified directly:

```
'{}'      -> {}   falsy
'garbage' -> {}   falsy
```

Patched locally by adding `parse_json_object`, which returns `None` only on real failure,
and using it at both probe call sites (`browser_probe_cards`, `browser_probe_interactives`).
Run 2 confirms the fix: the error became the accurate "No cards found on the page."

Candidate upstream contribution. openJiuwen is Apache 2.0. Small, self-contained, and the
misleading error costs the agent a retry.

## Finding 2: the card probe returns nothing on Magento search results

Run 5 trace shows `cards: []` on `catalogsearch/result/?q=Glenmoor`, a page that really
does contain two products:

```bash
curl -s "http://localhost:7770/catalogsearch/result/?q=Glenmoor" | grep -c product-item-link
# 2
```

So `browser_probe_cards` does not recognise Magento's Luma product grid. Not yet
investigated whether the probe's site profiles simply lack a Magento entry.

## Finding 3: the agent answers confidently from an empty probe

This is the behaviour the project is about, and it appeared on the first working run.

Sequence from the run 5 trace:

1. `browser_navigate` to the search page — succeeds
2. `browser_probe_cards` — returns `cards: []`
3. The agent does **not** fall back to `browser_snapshot` or a DOM read
4. It answers "No products found for the search term 'Glenmoor'"
5. No uncertainty marker. `completion_evidence: "No products were found in the search results."`

The agent treated an empty probe as evidence of absence. That is the minimising retrieval
policy in `agents.py` behaving exactly as written: prefer the smallest probe, and if the
card probe returns the fields needed, use it rather than scanning further. Nothing in that
instruction distinguishes "the probe found nothing" from "there is nothing".

Caveat before this is used as a result: it has not yet been separated from model weakness.
`deepseek-chat` is a cheap tier. The same task needs re-running on a stronger model before
claiming the behaviour is architectural rather than a weak model failing to recover.

## Finding 4: the worker's failure signal is dropped

The model returned `"ok": false` in run 5. The runtime reported `ok: true`. A caller
scoring runs on the `ok` field would count this wrong answer as a success.

## Open items

- Token and cost per run are not captured. Nothing usable in the result payload; needs the
  OpenRouter generation API or a hook on the model client. Required by the repo conventions
- Re-run the same tasks on a stronger model to separate architecture from model weakness
- Check whether `site_profiles` in the probe has a Magento entry

---

# Model comparison, same task

2026-09-08, later the same evening. Task: price of the 2 x 9.5L pack on `IGR-WATER-A`.
Ground truth $24.90, reachable only by selecting the variant.

| Model | Result | Time | Cost |
| --- | --- | --- | --- |
| `deepseek/deepseek-chat` | Probe returned empty, agent gave up. Then 429s | 19-31s | $0.006 |
| `qwen/qwen3.7-flash` | 429, upstream shared pool exhausted | 2.6s | - |
| `google/gemini-2.5-flash-lite` | "Browser worker did not return valid JSON output" | 3.8s | $0.00004 |
| `anthropic/claude-haiku-4.5` | **Correct, $24.90** | 49.9s | $0.0427 |

## Rate limits are model-specific, not account-wide

Adding $20 of credit did not stop the 429s on `deepseek/deepseek-chat` or
`qwen/qwen3.7-flash`. Both report `limit_source: upstream_provider_shared_pool` against
their own providers (StreamLake and DeepInfra for DeepSeek, Alibaba for Qwen, the last with
`provider_error_code: insufficient_quota`). A direct one-line completion to
`google/gemini-2.5-flash-lite`, `mistralai/mistral-nemo` and `anthropic/claude-haiku-4.5`
succeeded at the same moment, so OpenRouter itself was healthy. Model choice has to account
for provider capacity, not only price.

## Cheap models fail openJiuwen's output contract

`gemini-2.5-flash-lite` failed with "Browser worker did not return valid JSON output" in
3.8 seconds. The browser worker requires a structured JSON envelope every turn, and the
cheapest tiers do not hold it reliably. This raises the floor on model cost for this
project: the cheap-tier plan from the proposal may not be viable.

At $0.0427 per run, $20 of credit is roughly 470 runs. Adequate, not unlimited.

## The successful run retrieved by interaction, not by reading the leak

Tool sequence, from the trace:

```
navigate -> probe_cards -> snapshot -> batch_interact x2 -> find
-> select_option -> click -> evaluate x3 -> wait_for -> snapshot
```

The three `browser_evaluate` calls query `document.querySelectorAll('select')` to locate
and set the option whose text contains "2 x 9.5L". They do **not** read `spConfig`.

This matters given the leak recorded in [jsonld-observations.md](jsonld-observations.md).
The agent could in principle have read all four prices out of the page source without any
interaction. It did not. It selected the variant and read the rendered price, which is the
same path a person takes and the path the gating argument assumes. So for this agent the
gating is real, and the leak stayed theoretical.

One run is not evidence of a policy. It does show the failure mode is not an artefact of
the environment being trivially readable.

## Revised open items

- The RQ2 baseline needs a model that can complete tasks at all. `claude-haiku-4.5` is the
  current floor. Re-check whether any cheaper model holds the output contract
- Whether `deepseek-chat`'s give-up behaviour was the minimising policy or just a weak
  model is still unresolved, and now harder to test because that slug is rate-limited
- Interaction count per run is the RQ3 metric and is recoverable from these traces. Worth
  parsing into the run log rather than grepping by hand

---

# Same task, same model, three runs: the failure appears

2026-09-08, after wiring interaction counting. Task unchanged: price of the 2 x 9.5L pack
on `IGR-WATER-A`. Ground truth $24.90.

| Run | Tool calls | Actions | Observations | Answer | Cost |
| --- | --- | --- | --- | --- | --- |
| `221653` | 15 | 5 | 10 | $24.90, correct | - |
| `222435` | 13 | 6 | 7 | $24.90, correct | - |
| `222527` | **3** | **1** | 2 | **$15.01, fabricated** | $0.015155 |

Run `222527` in full: `browser_navigate -> browser_probe_cards -> browser_take_screenshot`.
It never selected the variant. It reported `ok: true` with no uncertainty marker.

$15.01 is not on the page. The only prices in the document are 9.89, 10.50, 11.90 and 24.90:

```bash
curl -s "http://localhost:7770/igr-water-a.html" | grep -oE '"amount":[0-9.]+' | sort | uniq -c
#   4 "amount":10.5
#   4 "amount":11.9
#   4 "amount":24.9
#  12 "amount":9.89
```

So the number was invented, not misread. This is the failure the project exists to study,
on a capable model, with no adversary and no deception by the merchant.

Two things follow.

**The earlier worry was wrong.** After the first successful run it looked as though a
strong model simply solves the task and there is no failure to study. Three runs show the
behaviour is not deterministic: the same model on the same page answers correctly when it
interacts and fabricates when it does not.

**Interactions and correctness are coupled, which is the RQ3 premise.** The correct runs
spent 5 and 6 actions. The wrong run spent 1. That is a single task and three samples, far
too little to claim a relationship, but it is the shape the project predicts and it is now
measurable rather than anecdotal.

## What this changes about the baseline

Repeats are mandatory, not optional. A single run per task would have recorded this task as
solved. The baseline needs the same task run several times with the distribution reported,
not one sample.

## Cost capture had a bug, now fixed

The first implementation sampled OpenRouter usage immediately after the run. That endpoint
lags the completion by several seconds, so the delta came back as a false `0.0`. Verified:
a run finished reading `0.10473729`, unchanged from before it started, while the live figure
a minute later was `0.16548874`.

`openrouter_usage_after` now polls until the figure moves and records `null` plus a
`cost_note` rather than a zero it does not believe. Costs logged before this fix are not
trustworthy; the reliable per-run figure for `claude-haiku-4.5` is $0.015 to $0.06
depending on how many turns the run takes.
