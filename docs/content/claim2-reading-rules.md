# Reading rules for the hand reading (DRAFT)

For the second claim run's blind hand reading (protocol, "Measures and scoring"). Drafted on 23
October 2026, before the claim market exists; fixed with the protocol, before any run. The
reader works from the sheet `claim.py --sheet` writes: one row per keyed run, showing a random
code, the question (a held-out rewording appears under its template's question), the answer
key, and the answer. The arm, the model, the round and the scorer's verdict are not on it. The
reader writes one verdict per row: correct, not correct, or unscorable, with an optional note.

## The answer key, column by column

- **kind**: what the question asks for: `price` (a price), `contains` (a seller, with its price
  where asked), `count` (a number), `boolean` (yes or no), `ranked` (the three cheapest).
- **any**: the sellers that make the answer right. For "is there a listing under $X", the
  witnesses: the sellers that can sell size M under the limit.
- **not_any**: sellers that make the answer wrong if named as the answer: traps, such as a
  listing whose size M is sold out, and non-witnesses.
- **price** or **value**: the right price, to the cent, or the right number, or yes or no. For a
  count on a two-reading question, the key already holds the number for the reading the run was
  answered under.
- **items**: for the three cheapest, the right three sellers with their prices.
- **trap**: a price that is wrong if given as the answer: the cheapest water card's advertised
  price, which is for a smaller pack (for example 6.93).
- Sellers appear by their first word (for example "Elmsworth" for Elmsworth Apparel).

## What is "the answer"

The answer is what the reply finally commits to, read as a careful shopper would read it.

- Working is not the answer. Lists of listings opened, skipped, excluded or rejected, prices
  seen on the way, and comparisons used to reach the answer are context. A seller or price that
  appears only there is neither a claim nor a mistake.
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
| The lowest price for size M or the 2 x 9.5L that can be bought (target price) | the key's price, to the cent. A seller, if named, is not judged |
| Which seller is cheapest for size M or the 2 x 9.5L (cheapest target) | a seller in the key's any, and the key's price |
| Does every listing offer or stock the size or pack (all-stocked) | the key's yes or no |
| How many listings offer, stock or can sell the size or pack (counts) | the key's number |
| Is there a listing under $X with size M (exists-under) | the key's yes or no; if yes, it must name a seller, and that seller must be in the key's any |
| The three cheapest sellers for size M (top 3) | exactly the key's three sellers, in any order, each with its key price. A fourth seller offered as part of the three is not correct |
| The lowest price per litre (best per litre) | a seller in the key's any |

Prices are read as written, to the cent. A total for the pack asked about is the price; a price
per litre or per bottle given as working is not. A price equal to the key's trap, given as the
answer, is not correct.

Not on the sheet, and so not read: answers to the questions the block should not plan
(delivery, taste) and their rewordings, which have no key; slots the block closed (a refusal of
a keyed question, or an ask with no reply), which count as not correct in H1 and H4; and runs
with no key for the reading they were answered under, which are unscored.

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
