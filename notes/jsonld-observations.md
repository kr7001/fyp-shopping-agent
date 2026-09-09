# Structured data on WebArena product pages

Observed 2026-09-08 against the self-hosted WebArena shopping site, Magento 2.4.6,
on a seeded configurable product (`IGR-WATER-A`, four pack sizes, four distinct prices).

## Finding 1: WebArena publishes no JSON-LD at all

```bash
curl -s "http://localhost:7770/igr-water-a.html" | grep -c 'ld+json'
# 0
```

Magento's default Luma theme emits no schema.org JSON-LD. Not a wrong `Offer`, not a
missing `AggregateOffer` — nothing.

Consequence for RQ3. The branch-and-bound method assumed a published "from" price usable
as a lower bound to prune listings. On Shopee that bound exists but is published as a
point value on a plain `Offer`. On WebArena it does not exist in structured data at all.
Either way the bound has to be parsed from the rendered page. Same conclusion as the
August audit, reached by a different route.

## Finding 2: Magento leaks every variant price in the page source

The rendered DOM shows one price, the 9.89 "from" price, 13 times. None of 11.90, 10.50
or 24.90 appear as visible text. So far this matches the live marketplace behaviour.

But the raw HTML contains a `spConfig` blob with all four:

```json
"optionPrices": {
  "104500": {"finalPrice": {"amount": 11.9}},
  "104501": {"finalPrice": {"amount": 9.89}},
  "104502": {"finalPrice": {"amount": 10.5}},
  "104503": {"finalPrice": {"amount": 24.9}}
}
```

Magento ships variant prices to the client up front and swaps them with JavaScript on
selection. Shopee does not; there the price for an unselected variant is genuinely absent
until the click, confirmed by DevTools search in August.

**This is the important difference and it needs stating in the writeup.**

Gating is relative to the observation channel:

| Channel | Sees all variant prices? |
| --- | --- |
| Rendered DOM / accessibility tree | No, one price |
| Raw HTML source | Yes, all four |

openJiuwen reads the control tree, meaning DOM plus accessibility tree, so the gating
holds for the agent under study. But a reviewer can fairly say the information was never
truly hidden, only unrendered.

Options, to decide before running experiments:

1. Define gating relative to the agent's observation channel and say so explicitly. Honest,
   and matches how deployed agents actually read pages
2. State it as a limitation. WebArena is the easier case; a policy that succeeds here is
   necessary but not sufficient for the live case
3. Make a harder variant of the environment that strips `spConfig` and serves variant
   prices over AJAX, matching live behaviour. Real work, but it removes the objection

Option 1 plus 2 is probably enough. Option 3 only if a reviewer pushes.
