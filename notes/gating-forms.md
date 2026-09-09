# Forms of interaction gating, and the scope decision on vouchers

2026-09-09. Written after the supervisor suggested adding discounts and vouchers, and
after the earlier request that shipping cost and discount-after-combination be put
explicitly in or out of scope.

The suggestion turns out to matter for a reason beyond realism: it reaches a depth of
gating that the current method's guarantee does not survive.

## The four forms

| Form | What is hidden | Interaction | Reversible | Status |
| --- | --- | --- | --- | --- |
| Price by variant | The price of the option wanted | One click | yes | Built, measured |
| Stock by variant | Whether the option is buyable | One click | yes | Built, measured |
| Price by quantity | A tier discount above a threshold | Set a quantity | yes | Designed |
| **Price by cart state** | Whether a voucher applies, and the real total | Add to cart, enter a code | **no** | Designed |

The first three are local and reversible: select another option and the page returns to
where it was. The fourth is not. A cart is global and persistent, so retrieving the answer
changes the state that later retrievals happen in, and an exploratory add has to be
actively undone rather than navigated away from.

**Consequence for the method.** Any policy that treats retrieval as free observation is
wrong at the fourth level. Every arm built so far does treat it that way, correctly,
because nothing built so far mutates state. That assumption becomes load-bearing the
moment vouchers exist and should be named before it is relied on.

## Why vouchers break the pruning guarantee

The exact method for comparison questions is branch and bound. It prunes a listing when
the listing's advertised "from" price already exceeds the best total found so far. That
step is sound because of one fact: **no variant of a listing can cost less than its "from"
price.**

A voucher makes that false. "Five off orders over fifty" means the minimum payable is
below the advertised figure, so the "from" price is no longer a lower bound and pruning
can skip the listing that actually wins.

Three possible responses:

| Response | Effect |
| --- | --- |
| **(a) State it as a limitation** | The measured pruning result holds in the absence of voucher pricing. Honest, costs nothing, and is what the report will say |
| (b) Weaken the bound | Use `from_price − max_possible_discount`. Still sound, prunes less, and needs the maximum discount, which is itself gated. A future-work paragraph |
| (c) Treat voucher applicability as a gated field | Makes it an RQ1 and RQ2 case rather than an RQ3 pruning case. This is where it fits most naturally |

## Scope decision

**In scope:** vouchers and tier pricing as a **fourth gating form for RQ1 and RQ2**.
Authoring them costs no model credit, since Magento supports tier prices and cart price
rules directly, and it strengthens RQ1, which is currently the weakest of the three
questions because it rests on a taxonomy of only two forms.

**Out of scope:** rebuilding the RQ3 pruning method to survive vouchers. The bound-based
result stands as measured, with the assumption stated explicitly. Response (b) is recorded
as future work rather than attempted.

**Out of scope, and stated:** shipping cost by address. It is a genuine gating form and a
realistic one, but it needs an address, which means a logged-in checkout flow, and that is
a larger environment change than the remaining time supports.

## Why this is worth doing rather than merely agreeable

Adding a fourth form is not padding. It gives RQ1 a taxonomy with a depth ordering rather
than a list, and the ordering is defensible: reversible and local, reversible and local
with a threshold, then irreversible and global. The last of those is a category the
existing web-agent literature on premature termination does not separate out, because a
benchmark that scores only the final answer cannot tell a cheap look from an expensive
one that changed the world.
