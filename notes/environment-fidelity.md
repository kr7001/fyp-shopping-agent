# What WebArena cannot reproduce, and why live sites are out of scope

2026-09-09. Written to be lifted into the report's limitations section.

## The honest position on live marketplaces

The project's own hard constraint already settles this: no automated access to live
commercial sites. Live observation is manual, made as an ordinary user, and used only to
motivate the problem. That constraint is correct, and worth defending on its merits
rather than treating as an imposed restriction.

**Terms of service.** Automated access breaches Shopee's and Lazada's terms. A final year
project cannot be built on a method the department could not endorse.

**Ethics review.** Automated collection from a commercial platform would need
institutional review. The timeline does not accommodate that, and the science does not
need it.

**Reproducibility, which is the strongest reason.** Live prices change hourly. A result
measured on Tuesday cannot be re-measured on Thursday, by a supervisor or an examiner or
by the student. The core claim of this project is a comparison of interaction counts
against correctness, and correctness needs an answer key that is stable.

**Ground truth is unobtainable.** On a live site the only reference answer is the
student's own manual reading of the page, which is exactly the error-prone process the
agent is being tested against. On WebArena the answer comes from the database. Marking 75
runs automatically is only possible because of that.

**Confounds would dominate.** Anti-bot measures, rate limits, A/B tests, personalisation
and sponsored placement would all vary between runs and none could be controlled.

So the live arm stays manual, and that is a strength, not a compromise. What it should
produce is a small number of frozen page snapshots used to argue that the seeded
environment matches production structure. Note the existing rule: never commit a HAR
file, it contains session cookies. Saved HTML with cookies stripped is sufficient for a
structural comparison.

## What WebArena lacks that a live marketplace has

Grouped by whether it threatens the results.

### Threatens the claim, must be stated

**Variant prices are present in the page source.** Magento ships an `spConfig` block
containing every variant price up front and swaps the displayed value with JavaScript.
Shopee does not: the price for an unselected variant is genuinely absent until the click,
confirmed by DevTools search in August. So WebArena's gating is weaker. It holds for an
agent reading the rendered page or accessibility tree, which is what openJiuwen does and
what the traces confirm it did, but a reader of raw HTML could bypass it entirely.
Consequence: a policy that works here is necessary but not sufficient for the live case.

**No structured product data at all.** WebArena publishes no schema.org JSON-LD. Live
marketplaces publish it and publish it wrongly, a plain `Offer` with a single price where
`AggregateOffer` with `lowPrice` and `highPrice` is correct. The failure mode of a
confidently wrong machine-readable price therefore cannot be studied here at all, only
described from the manual observations.

**One page template.** Every WebArena listing is Magento's Luma theme. A real search page
mixes seller-customised templates, so a probe tuned to one layout generalises less than
these results suggest.

### Changes the task, worth noting

**No sponsored placement.** Real search results interleave ads with organic results, so
"the cheapest listing on this page" is not even well defined without deciding whether
sponsored entries count. WebArena's results are purely organic.

**Classic pagination rather than infinite scroll.** WebArena paginates at 12, which is
discoverable and countable. Infinite scroll makes "did the agent see everything" much
harder to establish, and is the more common pattern on mobile marketplaces.

**No shipping cost by address, no voucher stacking.** Both are named gating forms in the
project scope and neither exists here. Shipping in particular changes which seller is
cheapest, and it is gated behind entering an address. This is the largest missing gating
category and should be listed as out of scope explicitly rather than silently.

**Static everything.** No price changes over a session, no stock churn, no flash sales,
no review accumulation. Every run sees an identical world, which is what makes repeats
comparable, and also what makes the environment easier than reality.

### Does not threaten the results

No anti-bot, no CAPTCHAs, no rate limits, single currency and locale, no cross-border
duties, no personalisation. All would add variance without adding anything the research
questions ask about.

## Suggested framing for the report

Two sentences, roughly: the environment reproduces the structural conditions for
interaction-gated pricing under database-verified ground truth, at the cost of being a
strictly easier case than a live marketplace in three respects, listed above. The live
observations establish that the structure exists in production; the environment
establishes what an agent does when it meets that structure.
