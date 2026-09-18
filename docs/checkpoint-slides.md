# Supervisor checkpoint, 18 September 2026

Slide-by-slide script. Same style as the Huawei deck: one claim per headline, short bullets,
one table per slide, concrete numbers, the caveat in small text at the bottom.

Twenty-one slides. Part A recaps the project, because it has been a few weeks. Part B is
what was already standing. Part C is this week. Part D is next week.

Suggested timing: A in 5 minutes, B in 5, C in 8, D in 2.

---

## PART A, the recap

### Slide 1, title

**Ambiguity Without Adversary**
Why injection defences miss a common agent failure in commerce

- Kayleen Lee Kai Rong, supervised by A/Prof. Markus Kirchberg
- Checkpoint, 18 September 2026

*Say: the registered title is about attacks. The work has narrowed to the failure that is
left when you take the attacker away.*

---

### Slide 2, the failure that started it

**A deployed shopping assistant, asked for the cheapest 9.5L carton**

| Seller | Price shown first | Price for 2 x 9.5L | What the assistant did |
| --- | --- | --- | --- |
| BenWholesale | $10.20 | $17.90 | Named it as cheapest at $10.20, which is the 6 x 1.25L pack |
| Shopee Supermarket | $15.50 | $15.50 | Actually cheapest for the size asked about, never mentioned |

- Confident answer, no uncertainty marker, and it even showed a cost per litre
- The arithmetic was right. The attribution was wrong
- **No merchant did anything deceptive and there was no attacker**

*Small text: observed by hand on a live marketplace in August 2026, as an ordinary shopper.
No automated traffic was ever sent to a commercial site.*

---

### Slide 3, what interaction-gated information is

**The price exists on the page and only appears after you click**

| What was checked | What was found |
| --- | --- |
| Search the page for the selected size's price | Exactly one match |
| Search for a size that is not selected | **Zero matches** |
| The structured data the page publishes | One price, the cheapest, and it does not update |

- The web standard has a field for a price range. Neither the live marketplace nor the test
  shop uses it
- **Checked before writing any code**, because a method that assumed a published price range
  would have been built on something that does not exist

---

### Slide 4, why the agent cannot see it

**An agent gets one of three views of a page, and all three agree**

| View | On a gated listing |
| --- | --- |
| Page source | Holds the selected size's price only |
| Accessibility tree | A subset of the source, so it can never hold more |
| Screenshot | Shows the selected size's price |

- Nothing contradicts anything, so there is no ambiguity to detect
- The information is **missing rather than conflicting**, which is why adding vision does
  not help and why the fix has to be about retrieval

---

### Slide 5, the three research questions

**RQ1** How often does gating occur in a realistic shop, and in what forms?
**RQ2** When a task needs gated information, does the agent retrieve it, and does it signal
when it has not?
**RQ3** Can a question-conditioned retrieval policy reach correct answers with fewer
interactions than exhaustive exploration?

- RQ3 is the contribution. RQ1 and RQ2 establish the baseline

---

### Slide 6, setup

**One model, one agent, one shop, no live sites**

- **Agent** openJiuwen, Apache 2.0, a deployed browser agent. Its own prompt tells it to
  retrieve as little as possible
- **Model** claude-haiku-4.5, the cheapest one that can finish a run
- **Shop** WebArena's Magento store, local Docker, 104,368 products
- **No testing on live sites.** Cannot send bot traffic to a marketplace, and live prices
  move between reloads so there would be nothing stable to mark against

*Small text: gemini-2.5-flash-lite could not return the required output format, deepseek-chat
and qwen3.7-flash hit provider rate limits. The model choice is a finding, not a preference.*

---

### Slide 7, the shop could not show the failure, so I built it

**104,368 products, 425,384 option values, and not one price that changes**

| Fixture | Listings | Variants | Purpose |
| --- | --- | --- | --- |
| Small | 4 | 14 | One deliberate trap each |
| Rivenhall | 15 | 55 | A market where checking everything is expensive |
| Calderwood | 15 | 55 | Built after the method was finished, to test it |

- Added through the shop's own admin interface, every SKU prefixed `IGR-`
- **No existing product was modified**

---

### Slide 8, the markets are generated, not hand written

**Prices drawn at random, accepted only if all eight rules pass**

| Rule | Rejects |
| --- | --- |
| The three questions have three different sellers as answers | 95.2% |
| At least three listings can be skipped on their advertised price | 80.9% |
| The winner beats the runner-up by $1.50 or 8% | 34.0% |

- About **1 draw in 435** passes. The one in use was accepted on attempt 111
- **Oracle floor: 11 of 15** listings must be opened by any correct method. That number
  becomes a rule later in this deck

---

## PART B, what was already standing

### Slide 9, RQ2, the plain agent

**It answers confidently and it never says it is unsure**

| Question | Rivenhall, 9 runs each | Where the answer sits |
| --- | --- | --- |
| Price of the 2 x 9.5L | 9 of 9 | card 2 |
| Cheapest seller for it | 9 of 9 | card 2 |
| Does every seller stock it | **3 of 9** | cards 11 to 15 |
| Best value per litre | **0 of 9** | card 6 |

- **0 abstentions in 125 runs.** Every failure is a confident assertion
- The pattern is not difficulty, it is position

---

### Slide 10, why it only opens four

**The agent asks a reasonable question and gets a complete-looking answer**

- Its prompt says to use the smallest probe and stop once the fields are there
- The card probe reads the **visible window only**, by default
- At 1200 x 701 that is one row of four cards, and it reports `total_candidates: 4`
- **Nothing in that reply says eleven more listings exist**

---

### Slide 11, the two halves of the fix

**Decide what to gather before answering, then check the answer against what was gathered**

| Half | What it does |
| --- | --- |
| Targeting | Reads the question, picks a strategy, before opening anything |
| The check | Compares the answer against the record of what the run observed, and refuses when unsupported |

- Three strategies: a total bound for "which is cheapest", refutation for "does every
  seller", a rate bound for "best per litre"
- The check costs nothing, because it never touches the browser
- **openJiuwen itself is unmodified.** The policy is text added to the question

---

### Slide 12, RQ3 on the development market

**Same accuracy as opening everything, about a third of the effort saved**

| Arm | Runs | Right | Refused | Wrong | Actions | Cost/run |
| --- | --- | --- | --- | --- | --- | --- |
| Unmodified | 36 | 21 | 0 | 15 | 15.8 | $0.238 |
| Open everything | 8 | 8 | 0 | 0 | 28.4 | $0.568 |
| **Targeting + check** | 12 | 11 | 1 | 0 | **18.4** | **$0.382** |

- 35% fewer actions, 33% less money, no wrong answers
- **But this is the market the method was built against**

---

### Slide 13, the held-out market

**A second market, generated after the method was finished, all three versions**

| Version | Right | Refused | Wrong | No answer | Actions | Cost/run |
| --- | --- | --- | --- | --- | --- | --- |
| Plain agent | 3 | 0 | 9 | 0 | 10.2 | $0.137 |
| Open everything | 10 | 0 | 1 | 1 | 28.4 | $0.564 |
| **Targeting + check** | **11** | 1 | **0** | 0 | **14.8** | **$0.335** |

- Twelve runs each, same questions, same prices, same shop
- **48% fewer actions and 41% less money than opening everything, and more right answers**
- Out of sample the saving is **larger**, not smaller

---

## PART C, this week

### Slide 14, what I did this week

**Five things, $19 spent, and three of them changed a claim I had already made**

| What | Cost |
| --- | --- |
| Ran the two missing arms on the held-out market | $10 |
| Wrote a new refusal rule from principle | $0 |
| Two cheap probes, can the model plan, does a second model work | $0.14 |
| Made the shop hide variant prices properly | $5.40 |
| Built a second agent from scratch and ran it | $10.40 |

*Say: I will go through the three that changed something, because those are the useful ones.*

---

### Slide 15, the baseline was flattered by its own market

**Same agent, same questions, two markets from the same generator**

| Market | Right | Runs | Rate |
| --- | --- | --- | --- |
| Rivenhall, development | 21 | 36 | 58% |
| **Calderwood, held out** | **3** | **12** | **25%** |

- On Rivenhall the cheapest seller sits in the four cards the agent reads, so a four-card
  read is right **by luck**. On Calderwood it does not
- Every right answer opened **12 to 15** listings. Every wrong answer opened **exactly 4**
- Nine failures, one cause

*Small text: on the development market the same table was muddy, which is why I had set this
question aside. On a market nobody tuned anything against it is unambiguous.*

---

### Slide 16, opening everything is not a ceiling

**The expensive version is fallible too**

| Market | Runs | Right | Wrong | No answer |
| --- | --- | --- | --- | --- |
| Rivenhall | 8 | 8 | 0 | 0 |
| **Calderwood** | 12 | 10 | **1** | **1** |

- The wrong one opened all fifteen and answered "Oakfield Pantry at $5.75", which is that
  seller's advertised starting price, not the pack price. **More looking cannot fix that**
- The empty one hit the 100-step limit at 99 calls and $1.008, the most expensive run on
  record, with 18 clicks and 10 size selections. It was doing the right thing and ran out

---

### Slide 17, a new rule, and it refuses my own right answers

**Naming the best of a market needs evidence covering that market**

| | Six rules | Seven rules |
| --- | --- | --- |
| Wrong answers withdrawn | 19 of 31 | **29 of 31** |
| On the held-out market | 3 of 9 | **9 of 9** |
| Right answers wrongly blocked | 3 of 94 | 5 of 94 |

- Written from the principle, **not** from the runs it catches, and frozen before the market
  that will test it exists
- **It also refuses 4 answers my own method got right.** They opened 9 listings where the
  sound minimum is 11, so the method skips more than its own reasoning licenses
- Under the new rule the held-out policy arm reads 7 right, 5 refused, 0 wrong, against the
  11, 1, 0 it was measured as. **Both are reported**

*Say: this is the clearest case in the project of right and earned being different things,
and a rule found it rather than a score.*

---

### Slide 18, the shop was giving the answer away

**Magento writes the surcharge into the size menu, so it reads 2 x 9.5L +$32.50**

| Page | Right | Actions | Cost/run | Clicked a size | Added up the menu |
| --- | --- | --- | --- | --- | --- |
| Ordinary | 3 of 12 | 10.2 | $0.137 | 0 of 12 | 4 of 12 |
| **Surcharge hidden** | 2 of 12 | 18.3 | $0.224 | **8 of 12** | **0 of 12** |

- I added a version of the page that hides it, switched on by the browser the agent uses, so
  every run already recorded is untouched
- **The agent starts clicking**, from never to two runs in three. Across 122 earlier runs it
  had chosen a size twice in total
- **It works 64% harder and is no more right.** Coverage still decides: right answers opened
  12 to 15, wrong ones exactly 4
- So the gate that matters is between the search page and the listings, not inside a listing

---

### Slide 19, a second agent, and my prediction was wrong

**I built a browsing loop with no card shortcut, expecting it to look at more**

| Scaffold | Runs | Right | Listings opened | Actions | Cost/run |
| --- | --- | --- | --- | --- | --- |
| openJiuwen | 12 | 3 | 6.5 | 10.2 | $0.137 |
| **From scratch, no probe** | 12 | 4 | **3.7** | 21.6 | $0.871 |

- It looks at **fewer** shops, not more, for twice the work and six times the money. It
  spends its actions re-searching, sorting and rephrasing
- Per question: it answers "does every listing stock it" **3 of 3** where openJiuwen gets
  1 of 3, and answers neither superlative question at all, **0 of 6**
- Its right answers opened 2, 2, 3 and 3 listings, so coverage stops separating its verdicts.
  **And it should**: the question it answers is settled by one counterexample

*Say: how much retrieval an answer needs belongs to the question, not to the agent. That is
the thesis of the project turning up in its own control.*

---

## PART D, next

### Slide 20, next week

**Two builds, then freeze everything and run it once**

| | Work | Why |
| --- | --- | --- |
| Next | A clothing market, price and stock both gated | Tests the new rule on ground it has never seen, and asks a question water cannot: cheapest in a size that is actually in stock |
| Next | Reviews, where the answer is spread over pages | A question one mention settles, and one that needs all of them |
| Then | Freeze and run the full matrix once | Every number in the report from one frozen version |

- **$20 of the $50 faculty credit left**, which is roughly 60 more runs
- Rule I am keeping: **freeze a rule before building the market that tests it**, or that
  market is spent too

---

### Slide 21, what I would not claim

**The honest limits, stated rather than found by a reader**

- **One model and one agent** for most figures. A second model and a second agent exist now
  but at 4 and 12 runs
- **Twelve runs per arm.** Enough to see a difference this size, not enough for an interval
- **The saving assumes no vouchers.** Skipping a listing is sound only because nothing inside
  it can cost less than its advertised price
- **Six bugs in my own instruments** this project, two this week, each one caught before it
  reached a number in a document. The record of catching them is part of the work

*Say: the thing I would most like to be challenged on is whether twelve runs is enough to
claim the saving, because that is where the next money goes.*

---

## If there is time, three things that can be shown live

Run these from the repo with the shop container up. None of the first two costs anything.

### Demo 1, the gate itself, 20 seconds, free

```bash
python env/demo_gate.py
```

Two browser windows open on the same product of the same shop. The left one is ordinary and
its size menu reads `2 x 9.5L +$32.50`, so the price is readable without touching anything.
The right one is the browser the experiments use and its menu is bare. Choose the size on
both and they land on the same $48.64.

*Say: this is the environment contribution in one picture. The price is there either way.
What changes is whether it can be read without asking for it.*

### Demo 2, the check catching failures for nothing, 10 seconds, free

```bash
python experiments/replay_gate.py --suite 20260917T115725
```

Prints the fifteen plain-agent runs on the unseen market before and after the check:
9 wrong answers become 9 refusals, 6 right answers survive, and it says
`added model cost $0.00` because the check never opens a page.

*Say: this is the half of the method that is free. It reads the record of what the run did
and compares it against what the answer claims.*

### Demo 3, a live run, 1 to 3 minutes, about $0.15

```bash
python experiments/suite.py --tasks experiments/tasks_heldout.json --repeats 1 \
    --only scaled-best-per-litre
```

A real browser opens and the agent works. Worth showing only if the conversation has time,
because it is slow and it will probably fail in the ordinary way, opening four listings of
fifteen. That failure is the point, but it cannot be promised in advance.

*Say: watch how few shops it opens before it answers.*
