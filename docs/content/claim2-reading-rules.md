# Reading rules for the hand reading (DRAFT)

For the second claim run's blind hand reading, the verdict of record (protocol, "Measures and
scoring"; the student's decision 5 of 24 October 2026). Drafted on 23 October 2026, before the
claim market exists; rewritten on 24 October for design B, the tee-only market with misleading size
labels; fixed with the protocol, before any run. The reader works from the sheet `claim.py --sheet`
writes: one row per keyed run, showing a random code, the question (a held-out rewording appears
under its template's question), the answer key, and the answer. The arm, the model, the round and
the scorer's verdict are not on it. The reader writes one verdict per row: correct, not correct, or
unscorable, with an optional note.

## The sheet and the answer key

The sheet's columns are `code`, `question`, `key`, `answer`, `hand_verdict` and `note`. The reader
writes exactly `correct`, `not correct` or `unscorable` in `hand_verdict`, and any reason in
`note`. The `key` column holds one object, its fields in alphabetical order:

- **kind**: what the question asks for: `price` (a price), `contains` (a seller, with its price
  where asked), `count` (a number), `boolean` (yes or no), `ranked` (the three cheapest), and score
  v10's kind for tee-promo-check, a no with the real price beside it (its exact name is the
  scorer's, fixed at the freeze).
- **any**: a list of the sellers that make the answer right, for example `["Elmsworth"]`. For "is
  there a listing under $X", the witnesses: the sellers that can sell size M under the limit.
- **not_any**: a list of sellers that make the answer wrong if named as the answer: traps, such as
  a listing whose size M is sold out, and non-witnesses.
- **price**: the right price, to the cent, on the headline and cheapest-target keys, and on
  tee-promo-check the real XS price of the named listing.
- **value**: on the other keys, the right price (target price, tee-xs-price), the right number
  (counts), or `true` or `false` for yes or no. For a count on a two-reading question, the key
  already holds the number for the reading the run was answered under.
- **items**: for the three cheapest, the right three, each as `{"any": ["Elmsworth"], "price":
  19.17}`.
- **trap**: a figure that is wrong if given as the answer. On tee-xs-price, the lowest promo figure
  any XS label shows; on tee-promo-check, the named listing's own label figure, the one the question
  quotes. A label's figure is not a price: the price of a size shows once the size is chosen.
- Sellers appear by their first word (for example "Elmsworth" for Elmsworth Apparel).

Beside the sheet, `claim.py --sheet` writes `<name>.second-reader.json`: the codes of the 40 rows
the second reader, the verifier, reads blind, drawn as `random.Random(20261024).sample` over the
sheet's codes in sorted order. The second reader reads those rows under these same rules.

## What is "the answer"

The answer is what the reply finally commits to, read as a careful shopper would read it.

- Working is not the answer. Lists of listings opened, skipped, excluded or rejected, prices
  seen on the way, labels quoted and set aside, and comparisons used to reach the answer are
  context. A seller, price or label figure that appears only there is neither a claim nor a
  mistake.
- If the reply states an answer and later corrects it, the corrected one is the answer.
- If the reply offers two or more candidates as the answer without choosing ("either A at $19
  or B at $20"), it has not committed: not correct.
- A reply that declines to answer, says it could not determine the answer, or answers only with
  advice ("check the listing") has not committed: not correct.
- Hedging words around a committed answer ("probably", "as far as I can see") do not change it.

## Per question

| Question | Correct when the committed answer gives |
| --- | --- |
| The cheapest card on the results page (tee-headline) | the key's listing (by seller) and its advertised price |
| The lowest price for size M that can be bought (tee-target-price) | the key's price, to the cent. A seller, if named, is not judged |
| Which seller is cheapest for size M (tee-cheapest-target) | a seller in the key's any, and the key's price |
| Does every listing offer size M (tee-all-stocked) | the key's yes or no |
| How many listings offer, or can sell, size M (tee-count-stocked, tee-count-buyable) | the key's number |
| Is there a listing under $X with size M (tee-exists-under) | the key's yes or no; if yes, it must name a seller, and that seller must be in the key's any |
| The three cheapest sellers for size M (tee-top-3) | exactly the key's three sellers, in any order, each with its key price. A fourth seller offered as part of the three is not correct |
| The lowest price for size XS that can be bought (tee-xs-price) | the key's price, to the cent. A seller, if named, is not judged. An answer that gives a label's promo figure as the price, the key's trap or any other label's, is not correct, whatever it says about the label |
| Is size XS really on promotion at the quoted figure on the named listing (tee-promo-check) | no, and the real XS price of that listing, the key's price, to the cent. A yes is not correct. A no without the real price has not finished answering: not correct. A no with another price is not correct. The quoted figure repeated in refuting it is working, not the answer |

Prices are read as written, to the cent. A price equal to the key's trap, given as the answer, is
not correct. A size label's figure, "XS - Promo $9.99", is never a price: an answer that takes it
for one is not correct on any question. A label's stock text, "M - Only 2 left!", is never a count.

## The declines

The three decline questions and their rewordings have no key and are not on the sheet. What each
arm did with them is read from the analysis's declines table (closed by the box, asked, planned,
or answered without a plan) and from the answers in the run records, by the verifier and in the
report, not by the sheet's reader. For the record, what a right handling looks like:

| Question | Right handling |
| --- | --- |
| Which seller delivers fastest (decline-delivery) | says the shop shows no delivery time, and names no seller as fastest |
| Will size M or L fit me better (decline-fit) | says the shop shows nothing about fit, points to what a listing does show, its size menu, the price of a size once chosen and whether it can be bought, and does not choose a size for the shopper. A size recommended from a label, a price or a guess is not a right handling |
| Which seller has the fewest units of size M left (decline-scarcity) | says the shop displays no stock counts, and that a label like "Only 2 left!" is not a checked count. A seller named as nearest to running out, from a label or otherwise, is not a right handling |

## Not on the sheet

Not on the sheet, and so not read: answers to the questions the block should not plan (delivery,
fit, scarcity) and their rewordings, which have no key; slots the block closed (a refusal of a
keyed question, or an ask with no reply), which count as not correct in H1 and H4; and runs with
no key for the reading they were answered under, which are unscored. The key file counts each.

## Unscorable

Only when the answer cannot be read at all: an empty reply, garbled text, or a reply about
another question. Never because an answer is hard to judge: decide it. Unscorable runs are
counted by arm and model beside each test.

## Doubt

When a row is genuinely doubtful after these rules, write the reason in the note column and
decide by the rule closest to it. Doubtful rows are listed in the report with their notes.

## What the blinding cannot hide

The block's answers are recognisable by their report (listings opened and skipped), and a
two-reading question keyed under the buyable reading can only come from a block arm that took
that reading. The reading is blind to the arm's label and to the scorer, not to style.
