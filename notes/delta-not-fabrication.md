# Correction: the wrong prices were deltas, not inventions

2026-09-09. Corrects Finding 3 in [rq2-baseline.md](rq2-baseline.md) and the matching
claim in [first-agent-runs.md](first-agent-runs.md).

## What was claimed

That two failing runs invented prices:

```
"The price of the 2 x 9.5L pack is $15.01"   truth $24.90
"The price of the 2 x 9.5L pack is $11.60"   truth $22.50
```

The evidence offered was that neither number appears anywhere in the page source:

```bash
curl -s ".../igr-water-a.html" | grep -oE '"amount":[0-9.]+' | sort -u
# 9.89, 10.5, 11.9, 24.9 only
```

That grep was correct. The inference drawn from it was not.

## What actually happened

Re-reading the failing runs' traces rather than their answers:

```
water-a-9l5-price-5   saw '2 x 9.5L +$15.01'   9.89 + 15.01 = 24.90   truth 24.90
water-b-9l5-price-4   saw '2 x 9.5L +$11.60'  10.90 + 11.60 = 22.50   truth 22.50
water-b-9l5-price-3   saw '2 x 9.5L +$11.60'  10.90 + 11.60 = 22.50   truth 22.50
```

Magento's variant selector labels each option with a **price delta**, not an absolute
price. The option reads `2 x 9.5L +$15.01`, meaning fifteen dollars and one cent more
than the displayed base price.

Both numbers are exactly right as deltas. Neither was invented.

The reason the grep found nothing is that the label is computed in the browser from the
`spConfig` block rather than written into the HTML. It exists only in the rendered page,
which is precisely where the agent was looking and where the grep was not.

## The corrected finding, which is sharper than the original

Interaction-gated pricing is frequently expressed **relative to the visible price**, not
as a standalone value. The gated token is a delta, and it is only meaningful composed
with the headline price the agent already had.

So the failure is not that the agent looked too little. It is that it retrieved the right
token and misread its semantics: it reported a relative value as an absolute one. The
resulting number looks exactly like a price, falls in a plausible range, and appears
nowhere on the page, which makes it harder to catch than either a stale headline price or
an outright invention.

The third run is the proof that composition is the discriminating step:

```
"The price of the 2 x 9.5L pack is $22.50 (base price $10.90 + additional charge $11.60)"
```

Same observation, same two numbers, correct answer, because it composed them. It was
scored ambiguous only because the scorer penalises an answer carrying both the target and
the trap value, which in hindsight is the wrong rule for this case.

## Why this matters more than the original claim

**It is a distinct failure mode.** Under-retrieval and delta misreading are different
faults with different fixes. The scaled results still show under-retrieval clearly, the
one-word "Yes" answers at six and seven actions. But these two price failures had the
information they needed. More retrieval would not have helped them.

**It changes what the RQ3 policy has to do.** A coverage check, has the agent observed
the required field, would pass both of these runs: the field was observed. What catches
them is a **consistency check**: if a delta label was observed, any reported absolute
price must equal base plus delta. That is arithmetic the policy can verify without
another page fetch, and it is cheap.

**It is a better contribution.** "Agents sometimes hallucinate prices" is a known and
unsurprising claim. "Marketplace UIs express gated prices as deltas, and agents report
the delta as the price" is specific, mechanistic, reproducible, and testable.

## What to change

1. Finding 3 in rq2-baseline.md, restated as delta misreading rather than fabrication
2. The corresponding claim in first-agent-runs.md
3. Section 3 Finding 3 in the supervisor update
4. The results section of docs/index.html
5. The scorer's ambiguous rule for the case where an answer names the target and shows
   its own working, which is a correct answer rather than a muddled one

## Method lesson worth keeping

The original claim came from checking the page source and not the trace. The answer text
plus a grep looked like sufficient evidence, and it was not. What settled it was reading
what the agent actually observed. Any claim about why an agent failed should be sourced
from its trace, not reconstructed from its output.
