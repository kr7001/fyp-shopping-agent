# What happened on 8–9 September 2026, explained from scratch

A full walkthrough of a single working session, written so that someone with no technical
background can follow every step. Nothing here assumes you know what Docker, an API or a
DOM is — each is explained where it first matters.

---

## Part 0: What this project is actually about

### The everyday situation

You are shopping online. A listing says "Spring Water Multipack" and offers four sizes:

- 24 bottles of 350ml
- 12 bottles of 550ml
- 6 bottles of 1.25 litres
- 2 cartons of 9.5 litres

The page shows **one** price: $9.89. That price belongs to the 12 x 550ml pack, because it
happens to be the cheapest one. If you want the price of the big 9.5 litre carton, you have
to **click** the size selector. Only then does the page show you $24.90.

That is completely normal. No shop is being sneaky. It is just how variant pickers work.

### Why that is a problem for an AI shopping assistant

An AI shopping agent is a program that reads web pages and answers questions about them. It
"looks" at a page much like you do — but it does not naturally click things unless it
decides to.

So if you ask it *"what does the 9.5 litre carton cost?"*, one of two things happens:

1. It clicks the size selector, reads $24.90, and tells you correctly. Good.
2. It reads only what is on screen — $9.89 — and answers from that. Bad.

The dangerous part is subtle. In case 2, the agent has **no way of knowing it is missing
anything**. The page does not say "there are three more prices hidden behind this button."
It just shows one number. From the agent's point of view, the page looks complete.

This is what the project calls **interaction-gated information**: information that exists
on the page but only becomes visible after you interact with it. The agent's first look
gives no clue that anything is missing.

### Why this matters beyond one bottle of water

Kayleen previously tested a real, live AI shopping assistant. She asked it for the cheapest
9.5 litre carton. It produced a confident comparison: one seller was "27% cheaper", complete
with a cost-per-litre calculation to back it up.

It was wrong. That seller was actually **more expensive** for the size requested. The
assistant had compared headline prices — the cheapest small pack from each seller — and
presented the result as though it had compared like for like.

Nobody cheated. No merchant did anything deceptive. There was no hacker, no manipulation, no
"prompt injection" attack. The agent simply did not look hard enough, and had no mechanism
for noticing.

That is the whole thesis in one sentence: **a lot of AI agent failures in shopping are not
security problems, they are "did not look hard enough" problems, and the security research
community is not studying them.**

### The three research questions

- **RQ1** — How often does this hidden-information situation occur in a realistic shop, and
  in what forms?
- **RQ2** — When a question needs hidden information, does the agent go and get it? And if
  it doesn't, does it *admit* that?
- **RQ3** — Can we build a smarter rule that gets correct answers with *fewer* clicks than
  brute-force checking everything? ← **this is the actual contribution**

Yesterday's session was about getting RQ2 measured properly, which is the foundation RQ3
stands on.

---

## Part 1: The test shop, and why it needed surgery

### What "the environment" is

You cannot run experiments on a real shopping site. It would be unethical (hammering someone
else's servers), unreliable (prices change hourly), and unrepeatable (you can't rerun last
week).

So the project uses **WebArena** — a research project that packages up a complete, fake but
fully functional online shop that runs on your own laptop. It has ~104,000 products, working
search, a shopping cart, the lot. Everyone in the research field uses it, which means results
are comparable between papers.

A few pieces of vocabulary that will keep coming up:

| Term | What it actually is |
| --- | --- |
| **Docker** | A way of packaging an entire computer setup — operating system, programs, database, everything — into one downloadable bundle called a *container*. You run it and the whole shop appears on your machine. No installation faff |
| **Magento** | The actual shop software running inside that container. It is real, commercially used e-commerce software, not a toy |
| **Database** | Where the shop keeps its facts: products, prices, stock levels. You can ask it questions directly, which is how we get "ground truth" — the definitive right answer to check the AI against |
| **Elasticsearch** | The search engine inside the shop. When you type "coffee" into the search box, this is what finds matching products |

### Problem 1: the shop would not start

The session began with the shop refusing to work.

**Symptom:** the website loaded, but the catalogue looked empty. Search returned nothing.
Critically, *no error message appeared anywhere*. Everything reported itself as "running
fine".

The culprit was Elasticsearch, the search engine. It said it was running. It was not
actually working. Port checks showed it never opened for business.

**The chase.** Two theories were tried and both were wrong:

1. A configuration setting (`xpack.ml.enabled`) — tried back in August, did not help
2. "Restart the container rather than the service" — tried yesterday, also did not help

**The real cause.** This turned out to be about *computer chip languages*.

Apple's newer Macs (M1, M2, M3 and so on) use a chip that speaks one instruction language,
called ARM. The WebArena shop was built for a different language, the older Intel-style x86.
So every single instruction has to be translated on the fly, like live interpreting between
two spoken languages.

macOS offers two interpreters:

- **QEMU** — a software translator. Works everywhere, but slow, because it does all the work
  itself
- **Rosetta** — Apple's own translator, which gets help from dedicated hardware built into the
  chip. Much faster

Docker was set to use QEMU. For most of the shop's parts, that was merely slow. But
Elasticsearch is written in Java, and Java *itself* translates code as it starts up. So you
had translation stacked on translation — and the startup ground almost to a halt.

The evidence was decisive: the startup process had consumed **5 minutes 52 seconds of solid
processing** at 100% of a processor core without even printing its first line of output. It
wasn't frozen. It was being interpreted roughly ten times slower than it needed to be.

**The fix:** one checkbox in Docker's settings, "Use Rosetta for x86_64/amd64 emulation".

**The measurement:**

| Setting | Time for search engine to become ready |
| --- | --- |
| QEMU (before) | 19 minutes, and it never finished |
| Rosetta (after) | **20 seconds** |

That is an improvement of at least 57×, and since the slow version never finished
at all, the true figure is unknown. It unblocked the entire day.

> **Why this is worth writing down.** This exact problem was documented in August as a
> mystery with a workaround ("restart it and wait"). It now has a diagnosis and a real fix.
> That is a genuine, if small, contribution back to the research community — other people
> using WebArena on Macs are hitting this.

### Problem 2: the shop had nothing to actually test

Here is the awkward discovery. The whole project is about prices hidden behind clicks. So
the shop needs products where clicking changes the price.

It has none.

Checking directly against the database:

| What was measured | Result |
| --- | --- |
| Total products | 104,368 |
| Products where picking an option changes the price | **0** |
| "Pick an option" choices available across the shop | 425,384 |
| ...of those, how many change the price | **0** |

So the shop *does* have products where you pick a colour or a style — 425,384 such choices —
but **every single one costs exactly the same** regardless of what you pick. There is a cake
topper with ten colour options, all $9.49.

That means the shop has the *appearance* of hidden information without any actual hidden
information. Nothing is behind the click. Useless for this project.

The good news: Magento, the underlying shop software, fully supports variant pricing. The
capability is there; the WebArena catalogue just never used it. So this was a content gap,
not a technical wall.

### The fix: authoring the missing products

A program was written (`env/seed_variants.py`) that creates the missing kind of product.

**How it does it, and why that matters.** There were two options:

- *Write directly into the database.* Fast, but dangerous — you bypass all the shop's own
  checks and can silently corrupt things
- *Go through the shop's official API.* An **API** is a formal "staff entrance" that software
  uses to talk to other software — the same way a website has a front door for humans. Slower,
  but every one of the shop's own validation rules still applies

The second was chosen. Everything the program creates is a legitimate product that the shop
itself accepts and understands.

**What got created — 18 new products, 3 new option types:**

**The two water sellers** (this is the important pair, they recreate the real-world failure):

| Seller | Pack | Price | Cost per litre |
| --- | --- | --- | --- |
| Cellar Direct | 24 x 350ml | $11.90 | $1.42 |
| Cellar Direct | 12 x 550ml | **$9.89** ← headline price | $1.50 |
| Cellar Direct | 6 x 1.25L | $10.50 | $1.40 |
| Cellar Direct | 2 x 9.5L | $24.90 | **$1.31** ← actually best value |
| Hillside Provisions | 12 x 550ml | **$10.90** ← headline price | $1.65 |
| Hillside Provisions | 6 x 1.25L | $11.40 | $1.52 |
| Hillside Provisions | 2 x 9.5L | **$22.50** | **$1.18** ← cheapest of all |

Read that carefully, because it is the whole trap:

- Cellar Direct's advertised price ($9.89) is **lower** than Hillside's ($10.90)
- So a quick glance says "Cellar Direct is cheaper"
- But for the 9.5 litre carton, Hillside is **$22.50** against Cellar Direct's **$24.90**
- The quick glance gives you the **opposite** of the right answer

**The coffee** breaks a different assumption. Everyone "knows" buying in bulk is cheaper per
unit. Here it isn't:

| Size | Price | Per kilogram |
| --- | --- | --- |
| 250 g | $8.50 | $34.00 |
| 500 g | $14.90 | **$29.80** ← best value |
| 1 kg | $32.00 | $32.00 |

The best deal is in the *middle*. You cannot work it out by checking the smallest and the
largest — you have to check all three.

**The t-shirt** hides availability rather than price. The page says "In Stock". Size M is
not. You only find out by selecting it.

**One important safety property:** the program only *adds*. It never modifies or deletes any
of WebArena's original 104,368 products. Every new item has an `IGR-` prefix in its code, so
it is always obvious which products are ours and which came with the shop. There is also a
one-command undo that removes everything it created.

**Ground truth.** Every time the program runs, it writes a record file listing exactly what
it created and — crucially — what the *correct answer* is to each question you might ask
about it. This is the answer key. Without it, you would have to check every AI response by
hand.

---

## Part 2: Two discoveries about how the shop presents information

### Discovery 1: the shop publishes no machine-readable product data

Most shopping sites embed a hidden, structured summary of each product in the page — price,
rating, availability — in a standard format called **JSON-LD**. It exists so that Google and
price-comparison sites can read products reliably without guessing.

There is a proper way to describe a product with several prices. The standard has a specific
type for it, `AggregateOffer`, with a lowest and highest price.

Checking WebArena's pages: **there is no JSON-LD at all.** Zero. Not a badly-formed one — none.

*Why this matters.* Part of the original plan was to use the published "from $X" price as a
mathematical lower bound, to skip over listings that couldn't possibly win. That shortcut
needs a published number. It isn't there. On the real marketplace it *is* there but it's
misleading. Either way, the price has to be read off the rendered page. Worth knowing before
building on the assumption.

### Discovery 2: the shop leaks all the prices in the page source, and this is awkward

Every web page has two layers:

- **What you see** — the rendered page, one price, a dropdown
- **The source code** — the underlying instructions the browser received

Magento sends **all four variant prices in the source code up front**, then uses a small
program in the page to swap the displayed number when you pick a size. Hidden inside the
source is this:

```
"optionPrices": {
  "104500": {"finalPrice": {"amount": 11.9}},
  "104501": {"finalPrice": {"amount": 9.89}},
  "104502": {"finalPrice": {"amount": 10.5}},
  "104503": {"finalPrice": {"amount": 24.9}}
}
```

All four prices. Sitting there. No clicking required.

The real marketplace does **not** do this — there, the price genuinely is not present until
you click.

*Why this is awkward.* A sceptical examiner could say: "your information was never hidden,
it was in the page all along. Your whole premise is broken."

The honest answer is that **hidden depends on who is looking**:

| Who is looking | Sees all four prices? |
| --- | --- |
| A person looking at the screen | No — one price |
| An AI agent reading the visible page | No — one price |
| Someone reading the raw source code | Yes — all four |

The agent being studied reads the visible page, the same way a person does. So for that
agent, the information genuinely is hidden.

And there is now direct evidence rather than just an argument. When the agent succeeded, the
recorded trace shows exactly what it did: it found the size dropdown, selected the 9.5L
option, and read the price that appeared. **It never touched the hidden price list.** It did
it the human way.

This gets written up as an acknowledged limitation: the test shop is an *easier* case than
the real world, so a method that works here is necessary but not sufficient.

---

## Part 3: Getting the AI agent running

### What the agent is

**openJiuwen** is a real, open-source AI agent published by Huawei. It is not a toy built
for this project — that is the point. Studying how a genuinely deployed architecture fails is
far more meaningful than studying a strawman built to fail.

Roughly how it works:

1. It gets a question, e.g. "what does the 9.5L pack cost?"
2. It looks at the web page and decides which action to take next
3. It has a toolbox of about 70 browser actions — click, type, take a snapshot, scroll
4. It repeats until it thinks it has the answer
5. It writes a final answer

The pieces underneath:

| Piece | What it does |
| --- | --- |
| **Playwright** | Software that drives a real web browser under program control — genuinely clicking and typing |
| **MCP** | A standard plug that lets AI agents connect to tools. Like USB, but for AI capabilities |
| **The model** | The actual AI brain doing the thinking. Rented from a provider, charged per use |
| **OpenRouter** | A middleman service offering hundreds of AI models through one account and one bill |

### The crucial detail that makes this project work

Buried in openJiuwen's instructions to itself is a policy about *how hard to look*. In
plain terms it says:

> Avoid unnecessary page snapshots. Choose the smallest probe that matches the task. On
> product pages, use the quick card scan first. If the card scan gives you what you need,
> use it rather than scanning further. Never dump the whole page.

Every one of those instructions is **sensible**. Looking at a web page costs money — each
look is text sent to the AI, and you pay per word. Minimising looking is good engineering.

But notice what is missing: nothing tells it how to distinguish *"the quick scan found
nothing because there is nothing"* from *"the quick scan found nothing because what I need is
behind a click"*.

That gap is the project.

### The model-shopping saga

Getting a working AI brain took four attempts.

**Attempt 1 — DeepSeek.** Cheapest sensible option, about half a cent per run. It navigated
to the page, ran its quick scan, got nothing back, and gave up. Then the provider started
refusing requests entirely — "rate limited", meaning too many people were using it.

**Attempt 2 — Qwen.** Also refused. Same reason, different provider.

At this point $20 of credit was added to the account, on the theory that free accounts get
throttled first. **That did not fix it** — and that is worth recording, because the obvious
assumption was wrong. A quick test showed OpenRouter itself was perfectly healthy; those two
specific models were simply oversubscribed at that moment. *Model availability is a separate
consideration from model price.*

**Attempt 3 — Gemini Flash Lite.** Failed in under four seconds with "did not return valid
JSON output". openJiuwen requires the AI to reply in a strict structured format every single
turn. Cheap models cannot reliably hold that format.

**Attempt 4 — Claude Haiku 4.5.** Worked. About 2–6 cents per run.

> **This falsifies an assumption in the original proposal**, which planned around
> cheapest-tier models. Those models cannot complete the tasks at all. The realistic floor is
> roughly ten times more expensive than budgeted. Still affordable — but better to learn it
> now than in November.

### Two genuine bugs found in the agent's code

**Bug 1: an empty answer treated as a broken answer.**

The agent's page-scanning tool returns its findings as a small structured message. When it
scanned a product page, it correctly returned `{}` — meaning "nothing of that kind here",
which is *true*, because a single product page has no product grid to scan.

But the code checking that result did this:

```python
parsed = extract_json_object(raw)
if not parsed:
    return {"error": "Could not parse result JSON"}
```

In Python, an empty result and a *failed* result look identical to that check. Both are
treated as "false". Demonstrated directly:

```
'{}'      →  {}   treated as failure
'garbage' →  {}   treated as failure
```

So "I looked and there was nothing there" got reported as "the tool is broken". The agent
then retried the same broken-seeming scan instead of trying a different approach.

**The fix:** a new function that returns a distinct "genuinely failed" signal, separate from
"succeeded, found nothing". After the fix, the error message changed from the misleading
*"Failed to parse result JSON"* to the accurate *"No cards found on the page"*.

**Bug 2: a failure reported as a success.**

In one run, the AI itself said, in its own output, `"ok": false` — it knew it had failed. The
surrounding system reported `ok: true`.

That is serious for research. Any study that counted successes by reading that field would
count wrong answers as right ones.

Both bugs are small, clearly explained, and sit in Apache-licensed open-source code — good
candidates to submit back to the project.

---

## Part 4: The experiment

### Why one test run proves nothing

The very first successful run answered $24.90. Correct. Encouraging — and briefly worrying,
because if the agent just gets everything right there is no failure to study.

Then the *identical* question was asked twice more:

| Run | Steps taken | Answer |
| --- | --- | --- |
| 1 | 15 | $24.90 ✓ |
| 2 | 13 | $24.90 ✓ |
| 3 | **3** | **$15.01** ✗ |

$15.01 is not a price on that page. Checking the page source, the only prices are 9.89,
10.50, 11.90 and 24.90. The agent did not misread anything — **it invented a number**.

And it reported that invented number with complete confidence. No hedging, no "I'm not
sure", no "I could not check".

**The lesson for method:** ask everything multiple times. A single run would have recorded
this task as "solved" and the entire project would have been built on a false floor.

### How the experiment was built

**12 questions** across the four product families:

| Question | Why it is there |
| --- | --- |
| What price shows on first load? | Control. The answer is right there, so this should be easy |
| What does the 9.5L pack cost? (both sellers) | The core hidden-price question |
| Which pack is cheapest per litre? | Needs *all* prices, not one |
| Which seller is cheaper for 9.5L? | The real-world failure, reproduced |
| What does 1kg of coffee cost? | Hidden price |
| Which coffee size is best value per kg? | Breaks the "bulk is cheaper" assumption |
| Is 1kg the cheapest per kg? | Yes/no version of the same |
| Is size M available? | Hidden stock rather than hidden price |
| What does size XL cost? | Hidden price with a surcharge |
| Is every size in stock? | Requires checking each one |
| List every pack size and price | Exhaustive — the expensive way |

Each asked **5 times**. 60 runs total.

**The automatic marker.** Grading 60 written answers by hand is slow and inconsistent. A
program does it, checking each answer against the known correct value. Five possible verdicts:

- **correct** — right answer present
- **wrong** — right answer absent
- **ambiguous** — right answer present but muddled with a wrong one
- **abstained** — the agent said it couldn't determine the answer
- **failed** — no answer produced at all

That fourth category matters more than it looks. An agent saying *"I could not determine this"*
has **not misled anyone**. It is a completely different outcome from confidently stating a
wrong number, and RQ2 asks specifically whether the agent signals when it hasn't retrieved
enough.

**The step counter.** A separate program reads each run's recording and counts what the agent
did, split into two kinds:

- **Actions** — things that change the page: clicking, selecting a size, navigating
- **Observations** — things that only look: taking a snapshot, scanning, screenshotting

Actions are the interesting number. Clicking the size selector is what actually reveals a
hidden price.

### A mistake I made, and fixed

The first set of results showed 12 failures. On inspection, 6 of them were **my marking
program's fault, not the agent's**.

The rule said: mark wrong if the answer mentions an option that isn't the correct one. But
look at a real answer it rejected:

> "The 500g size is the best value per kilogram at $29.80/kg. The 250g size costs $34.00/kg
> and the 1kg size costs $32.00/kg."

That is a **perfect** answer. It names the right size *and* shows the comparison. My rule
punished it for mentioning 250g and 1kg — which is exactly what a good comparison does.

Fixed so that naming the correct option is decisive. Everything was then re-marked from the
stored recordings — **no re-running, no extra cost**. Changed verdicts are kept in the results
file so the change in rules is visible rather than silent.

> Worth noting for the report: the failure rate was overstated by 50% by a subtle flaw in the
> measuring instrument. Being able to re-mark stored recordings without re-running is what
> made that cheap to correct.

---

## Part 5: What the experiment found

**60 runs. $2.98. Total project spend so far: $3.75 of $20.**

| | |
| --- | --- |
| Overall | 53 correct, 6 wrong, 1 ambiguous |
| On hidden-information questions | 48 of 55 correct — 87% |
| On the control question | 5 of 5, one step each |
| **Times the agent admitted uncertainty** | **0 out of 60** |

### Finding 1: it never says "I don't know"

Zero. In sixty runs. The marker looked for a wide range of hedging — "unable to", "could not
determine", "insufficient information", "unclear" — and **not one ever appeared**.

Every single failure was stated with full confidence.

This directly answers half of RQ2. The agent does sometimes fail to find hidden information.
When it fails, it does not say so. There is no warning signal for anything downstream — a
person, or another program — to act on.

If you are building on top of such an agent, you cannot tell its guesses from its
verifications. They look identical.

### Finding 2: correctness falls off a cliff, and only at the bottom

Grouping the hidden-information runs by how many actions the agent spent:

| Actions spent | Runs | Correct | Success rate |
| --- | --- | --- | --- |
| 1 | 5 | 1 | **20%** |
| 2–3 | 16 | 16 | 100% |
| 4–6 | 20 | 18 | 90% |
| 7+ | 14 | 13 | 93% |

Correct runs took a median of 5 actions. Wrong runs took a median of **1**.

Read the table carefully, because the obvious reading is wrong. This is **not** "more effort
is better". Past three actions the success rate is flat — 100%, 90%, 93% — those differences
are noise at this sample size.

What it actually says is sharper and more useful:

- Below two actions, the agent is **guessing**, and mostly guesses wrong
- Above two actions, it is reliable
- Above three actions, extra work buys **nothing measurable**

This is exactly the premise RQ3 needs, now measured rather than assumed. There is a minimum
amount of looking required, below which answers are fabricated. There is also a lot of
looking that achieves nothing — which means there is real waste to cut.

### Finding 3: failures are inventions, not misreadings

```
"The price of the 2 x 9.5L pack is $15.01"   — truth $24.90, one action
"The price of the 2 x 9.5L pack is $11.60"   — truth $22.50, one action
```

Neither of those numbers exists anywhere on those pages.

This is worth sitting with. The expected failure was that the agent would report the
*headline* price — $9.89 instead of $24.90. Understandable; it read the visible number and
answered from it.

That is **not** what happened. It produced numbers that appear nowhere. It seems to have
sensed it needed a variant-specific price, been unable to obtain it, and generated something
plausible-looking rather than reporting that it couldn't.

That is worse than the predicted failure, and much harder to catch — $9.89 is at least
checkable against the page. $15.01 is checkable against nothing.

### Finding 4: a second, different failure

One task asks for *every* pack size and price. It failed 4 times out of 5, but differently:

> "Successfully listed all pack sizes and their prices from the Glenmoor Still Spring Water
> product page."

Read it again. It **announces** that it listed the prices. It does not list any prices.

These runs spent 5, 6 and 7 actions — enough that the looking probably did happen. The
failure is in the reporting, not the retrieval. That is a different problem and should be
counted separately, not lumped in with the fabrications.

### Finding 5: the headline trap did not work — and that is useful

The task built to reproduce the real-world failure — *which seller is cheaper for the 9.5L
carton?* — was answered **correctly 5 times out of 5**, averaging 6.4 actions.

Given two listings and both addresses, the agent opened each one, selected the size on each,
compared properly, and named Hillside Provisions at $22.50. Exactly right.

**Why the trap failed to spring:** with only two listings, checking both is *cheap*. So the
agent just checks both. The real-world failure happened across a search page with many
sellers, where opening every listing would be expensive — and that expense is what pushes an
agent into shortcuts.

This is a **negative result**, and a genuinely valuable one. It converts "we should build a
bigger catalogue" from a hunch into an evidence-backed requirement. The trap needs *scale*,
not cleverer design.

---

## Part 6: What all this means

### For RQ2 — answered

Yes, the agent sometimes fails to retrieve hidden information. And no, it never signals when
it has failed. Zero times in sixty.

### For RQ3 — the target is now concrete

The opportunity is **not** making the agent more accurate. At 87% it is mostly right already.

The opportunity is that it has **no principle for knowing when it has looked enough**:

1. It sometimes spends 1 action and invents an answer
2. It sometimes spends 7 actions where 2 would have done — pure waste
3. It never abstains, so a guess and a verified fact are indistinguishable from outside

A smarter retrieval rule has three targets:

- **Eliminate** the one-action answers — never answer a hidden-information question that cheaply
- **Cut** the runs spending 7+ actions where 2 suffice
- **Abstain** rather than invent, when the budget genuinely runs out

That third one may be the most valuable. An agent that says *"I could not determine the 9.5L
price"* is far more useful in production than one that says *"$15.01"*.

### The infrastructure that now exists

| Tool | What it does |
| --- | --- |
| `env/seed_variants.py` | Creates the hidden-price products, with an undo and an answer key |
| `experiments/tasks.json` | The 12 questions and their correct answers |
| `experiments/score.py` | Marks answers automatically, five verdicts |
| `experiments/trace_stats.py` | Counts what the agent actually did, step by step |
| `experiments/suite.py` | Runs everything, repeats, produces the results table |
| `experiments/rescore.py` | Re-marks stored runs when the rules improve — no re-running, no cost |

Every run records: the answer, the verdict, the cost in dollars, the time taken, the number
of actions and observations, and the complete sequence of what the agent did.

---

## Part 7: What comes next

| When | What | Why |
| --- | --- | --- |
| **Now** | Send the supervisor update | Results exist, they are worth reporting, last update was 20 August |
| **By 23 Sep** | Build 30–50 listings, ask questions over search pages | Finding 5 says the interesting failure needs scale. Also properly answers RQ1 |
| **Early Oct → 21 Oct** | Build and test the smarter retrieval rule | **This is the actual contribution** |
| **Early Nov** | Final report and presentation | Deadline |

### The risk worth naming out loud

It is 9 September. The final report is due in November. **RQ3 — the actual original
contribution — has not been started.**

Everything so far is groundwork: the shop, the products, the agent, the measuring tools, the
baseline. All necessary. None of it is the contribution.

The catalogue-building step is a *means*, not the work. It should be timeboxed to two weeks
and no more. If RQ3 has not started by early October, the project risks handing in a
well-measured benchmark instead of a new method — and the method is what is being marked.

---

## Appendix: quick glossary

| Term | Plain meaning |
| --- | --- |
| **Agent** | A program that uses an AI to decide what to do next, then does it |
| **API** | A formal way for one program to talk to another |
| **Container / Docker** | A whole computer setup packaged into one downloadable bundle |
| **DOM** | The browser's live picture of the page — what is actually on screen right now |
| **Elasticsearch** | The search engine inside the shop |
| **Ground truth** | The definitively correct answer, taken from the database, used for marking |
| **JSON** | A standard way of writing structured data so programs can read it |
| **JSON-LD** | A hidden, machine-readable product summary embedded in a web page |
| **Magento** | The e-commerce software running the test shop |
| **MCP** | A standard connector letting AI agents use external tools |
| **Playwright** | Software that drives a real browser automatically |
| **Rate limit** | A provider refusing requests because too many are arriving |
| **Rosetta / QEMU** | Two ways of translating between chip instruction languages |
| **Token** | A chunk of text. AI services charge by the token |
| **Variant** | One purchasable version of a product — a size, a colour, a pack |
