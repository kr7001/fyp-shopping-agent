# The same listing shows a different price on reload

2026-09-09. Manual observation, TikTok Shop Singapore, one listing, as an ordinary
shopper. No automated access. Screenshots to be saved alongside this note in
`notes/media/`.

Listing: Mrs Ma Food Therapy, Healthy Grain Powder 300g, flavour "5 Red Grain".

## What was observed

Same listing, same flavour, same quantity option, reloaded. The price differs.

| Session | Option | Shown | Struck through | Discount | Per bottle |
| --- | --- | --- | --- | --- | --- |
| A | Buy 4 Free 2 | S$188.30 | S$235.38 | 20.0% | S$31.38 |
| B | Buy 4 Free 2 | S$205.55 | S$256.94 | 20.0% | S$34.26 |
| A | 1 Bottle | S$49.39 | S$61.74 | 20.0% | S$49.39 |
| B | 1 Bottle | S$52.17 | S$65.22 | 20.0% | S$52.17 |

```
Buy 4 Free 2    188.30 -> 205.55    +9.2%
1 Bottle         49.39 ->  52.17    +5.6%
```

Two things are worth separating.

**The discount rate is exactly stable and the base price is not.** Every one of the four
readings is exactly 20% off its struck-through figure, to the cent. So the "-20%" is not
what moves. The price it is applied to is.

**The relationship between the options also moves.** The bundle divided by the single
reads 3.81 in session A, 3.94 in session B, and 4.00 on an earlier reading of the same
listing. So this is not one number being rescaled. The options are drifting relative to
each other.

## What is not established

The mechanism. Candidates, none of them tested:

| Candidate | Would predict |
| --- | --- |
| Currency conversion from a foreign base | Both options move by the same factor. They did not, so this is weakened |
| Session or A/B bucket | Stable within a session, different across sessions or private windows |
| Personalisation | Differs by account, device or network, and the login prompt suggests the platform does personalise |
| Time-based repricing | Drifts with the clock regardless of session |

Two readings per option cannot separate these, and cannot even establish whether the
movement is noise or a trend. A proper reload series is needed: fixed option, N reloads,
timestamped, plus a private-window arm and a logged-in arm.

## Why this matters to the project

**1. It undermines ground truth on live sites, which defends a choice already made.**
The project runs its experiments on a self-hosted environment, and the reason recorded so
far is that automated access to live sites is not permitted. This is a second and stronger
reason: on a live listing the correct answer is not stable, so a benchmark cannot mark an
agent against it. If a price moves 9% between two page loads, a run scored as wrong may
have read its page correctly and been marked against a value that no longer existed. Any
live-site agent benchmark has this problem whether or not it acknowledges it.

**2. It is a gating dimension the taxonomy does not have.** The four forms recorded so far
are variant, stock, quantity and cart state. All of them assume the hidden value is stable
once revealed. Here the value is not merely hidden, it is **unstable**: two agents asking
the same question at the same moment can read different prices and both be right.

**3. It strengthens the abstention argument rather than weakening it.** An agent that
reports "the price is S$188.30" and rates itself 100 is overclaiming even when it read the
page perfectly, because the figure it read is not a property of the product. Correctness
was already shown to be separable from soundness. This separates it from stability too.

**4. Discounts are gated behind authentication.** The screenshots carry a prompt reading
**"Log in to see your exclusive discounts."** That is a direct answer to the question of
whether vouchers are visible to an agent at all: on this platform, some are not, and no
amount of retrieval by a signed-out agent will reveal them. Any voucher fixture built in
WebArena should therefore not assume a voucher is a readable page element, because on at
least one real platform it is not.

## What to record next, manually

A reload series is cheap and settles most of it:

- Fix the flavour and the option. Reload 10 times over a few minutes, recording price and
  timestamp each time. Distinguishes drift from per-session assignment
- Repeat in a private window. Distinguishes session identity from time
- Repeat logged in. The platform says this changes prices, so it should be measured rather
  than assumed
- Check whether the price is in the initial HTML or fetched afterwards, the same test the
  existing structured data audit uses
- Check what the structured data publishes, and whether it agrees with the rendered price

The last two connect this to the existing audit table, which currently covers Shopee and
WebArena. A third platform, with an instability finding attached, makes that table
considerably more useful.
