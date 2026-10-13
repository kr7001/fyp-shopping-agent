# Box v1, the specification

Status: **draft, for the student's approval on 14 October 2026.** Written after the free tests
listed under each decision. Nothing paid has run for it. Once approved, the coder builds exactly
this, the verifier checks the build against it, and only then does a paid run start.

## What the box is

A step that runs before openJiuwen. It reads the user's question and the first results page,
and does one of two things:

1. hands openJiuwen a plan: how many listings there are, which to open and in what order, when
   to stop, and what counts as evidence, or
2. asks the user back, when the question has two reasonable readings and the readings give
   different answers.

After openJiuwen answers, the box's refusal check decides whether the answer is supported by
what the run opened, using only numbers it read from the page.

## What it may read, and what it never reads

| May read | Never reads |
| --- | --- |
| The question text | A fixture in `env/fixtures/` |
| The first results page, fetched over HTTP with the same user agent the agent's browser uses: how many listings, each seller, its advertised price, its URL, whether there is a next page | An answer key: a task's `expect`, a market's `_instance`, a manifest's `ground_truth` |
| The scripted user's reply to its own question | A hard-coded seller, price or market size |
| After the run, the agent's answer and its log | |

`experiments/tests/test_box.py` checks the box's files for every one of these, and plants each
kind of read to prove the check can fail.

## The eight decisions, with the evidence each rests on

**1. The box fetches the results page itself.** One HTTP request with the gated user agent,
parsed without a browser. *Evidence:* the fetched page holds 15 product cards, each with a
seller, an "As low as" price and a URL, on one page with no pager. The agent's own whole-page
card probe in a cell 2 log (`20261007T115021/apparel-target-price-1.log`) returns the same 15
prices in the same order. *Alternatives:* waiting for openJiuwen's first look needs a hook
inside its runtime and, as shipped, sees four cards. A browser fetch adds nothing on a page
Magento renders on the server. *Limit:* a shop that draws its cards with JavaScript would need
the browser fetch.

**2. Written rules, not a model, decide the plan.** `targeting.classify` chooses the kind of
answer the question needs and `planner.plan` builds the plan. *Evidence:* the planner
regression renders every one of the 37 questions in the project correctly and passes its own
soundness check (37 questions, 0 failures). On 18 September a model asked to write plans was
sound in 7 of 8 with guidance, and its one miss was a plan no check could catch: comparing a
delivery time the shop does not publish. Rules cost nothing, repeat exactly, and can be read.
*Deferred to v2:* a model-written plan, measured against the rules' plan.

**3. Ambiguity is found by a small lexicon, and the box asks before the agent starts.** A
question is ambiguous when it asks about a variant (size, pack, colour, option) with a verb
that does not say which availability it means, "offer", "carry", "stock", "have", "sell", and
nothing in it settles the reading, such as "in stock", "available to buy", "can be bought", "can
supply", or "listed", "in the menu", "even if sold out". The box then asks: *"On this shop a
size can be in a listing's menu but sold out. Do you mean listings whose menu lists size M, sold
out or not, or listings that can sell size M now?"* *Evidence, free:* over the six clothing
questions the rule asks on exactly the two "offer" questions and on none of the four clear ones.
Over all 37 distinct questions it also fires on the two water questions that say "stock the pack", which
carry the same ambiguity; the water market never had a sold-out pack, so the two readings agreed
there and no run could have shown it. Two drafts of the rule were wrong before this one: the first
matched "seller" through "sell", and the first build fired on "which seller offers the lowest
price per litre", where "offers" is about a price. The rule now matches whole verbs only, and
the verb must govern the variant phrase: the variant word follows the verb within six words,
with no punctuation between, so "offer size M" and "stock the 2 x 9.5L pack" match and a
variant word before the verb does not count. Over the project's 37 distinct questions (42 entries in six files, the held-out gated file repeating five) it fires on exactly four. *Why not a model:* a model call per question costs
about a tenth of a cent and generalises further, but varies run to run; it is the v2 comparison.
*Why ask before the agent starts:* openJiuwen has an `ask_user` tool, and routing the ask
through it would make the ask part of the agent's run. v1 asks first, so the ask and the run can
be scored separately. Routing it through the agent is v2.

**4. The scripted user, and how an ask is scored.** In a batch the scripted user is a flag,
`--reading menu` or `--reading buyable`. When the box asks, the reply picks that reading and the
box adds one sentence to the question before planning, so the agent sees no ambiguity: *"By
offer size M, I mean listings whose size menu includes M, whether or not it is sold out."* or
*"By offer size M, I mean listings that can sell size M now, so a sold-out M does not count."*
The answer is then scored against that reading's key: the task's own key for `menu`, and a
sidecar file, `experiments/tasks/readings_apparel.json`, for `buyable`, which holds the answers
the project already derived for that reading on 8 October (count 5 instead of 10; "every
listing offers M" is No under both, with a sold-out size also a counterexample). Without a
`--reading`, a box that asks records the ask as the outcome, runs no agent and spends nothing.
Two things are measured: whether the box asks on the right questions, which is a property of
the box and costs nothing, and whether the final answer is right under each reading, which
needs runs.

**5. The plan gives the agent the listings.** The box renders, in this order: the market size as
read from the page ("The results page lists 15 listings on one page; there is no next page"),
the listings with seller, advertised price and URL, sorted by advertised price, then the
strategy text for the question's kind, the frozen v7 text minus its "enumerate first" preamble,
which the box has now done. *Evidence that the order matters:* across the 45 openJiuwen runs on
the clothing market, each extra listing opened costs about 3.6 tool calls and $0.035, and the
bound lets a sound answer stop after the listings advertised at or below the best buyable price
found. The regression over those runs predicts about $0.25 a run at 8 listings opened against
$0.50 at 15 (cell 5 measured $0.52). *A fairness note:* the box hands the agent the URLs it read
from the page. Cells 1 and 5 had to find them. That is the box's work, and it is stated as such.

**6. The refusal check reads the page, not the answer key.** The market size is the number of
cards on the page. The floor for a "cheapest" answer is the number of listings advertised at or
below the price the answer names, because every one of them could have beaten it and so must
have been opened. A count must have opened every listing; a "does every" answer of No needs one
counterexample. *Evidence, free replay over cells 1, 2 and 5:* with the page's numbers the check
refuses 8 of the 9 answers that did not open what they needed, and 0 of the 26 correct answers.
With the answer key's numbers it refuses 9 and 0. The one it misses (`cell 1,
cheapest-target-3`) opened every listing its bound required and misread Copperfield's
advertised $23.40 as its size-M price. No check that reads only the page can tell that from a
correct answer, and it is the plan's "choose the size, then look again" step that targets it.

**7. The browser tool is pinned at 0.0.83.** *Evidence:* npm's latest `@playwright/mcp` is
0.0.83 today, and every clothing cell ran on 0.0.83. Pinning changes nothing now and stops a
release changing the tool between the box's runs and the cells it is compared with.

**8. A dry run prints the exact text the agent will receive.** One function builds the final
query for both the dry run and the paid loop, so what the verifier reads is what the agent gets
(LESSONS 17).

## The box's record

Every run under the box stores, beside the usual record: `box_version`, the kind the question
was classified as, the page the box read (listing count, each seller, advertised price and
URL), whether it asked and which reading was chosen, and the exact query sent. The verifier
checks the stored page against the live shop.

## How it is measured

| Stage | Where | Runs | Compared with |
| --- | --- | --- | --- |
| Development | Thornwood, in sample for the box | the six questions, 3 repeats, the two ambiguous ones under both readings: 24 runs | cells 1 and 5, already measured on the same questions |
| The claim | a fresh clothing market, generated after the box is frozen | box, shipped and open-everything, same questions, 3 repeats | each other, within each question |

Success, from `OBJECTIVE.md`: on the fresh market the box is more accurate than openJiuwen as
shipped, costs less than opening everything, asks on the ambiguous questions and not on the
clear ones. Tests are exact and stratified by question, as on the Results page. Development
figures are reported as development figures.

## Out of scope for v1

Review questions (they gate by depth, not by a click; the next week). Price-per-unit questions
(water only). The ask routed through openJiuwen's own `ask_user`. Model-written plans. The
second agent (a stretch goal in week 3). Shipping cost and combined discounts.

## Files

| File | Holds |
| --- | --- |
| `experiments/box/page.py` | Fetching and parsing the results page. Reads HTTP only |
| `experiments/box/ambiguity.py` | The lexicon, the question to the user, the rewritten questions |
| `experiments/box/box.py` | `decide(question, page, reply=None)`: an ask or a plan, the final query, the record. `VERSION = 1` |
| `experiments/box/policy.py` | `gate_from_page(question, page, answer, log_path)` beside the existing `gate` |
| `experiments/runners/suite.py` | `--box`, `--reading`, the dry run that prints the text, the pinned browser tool |
| `experiments/tasks/readings_apparel.json` | The `buyable` reading's answers for the two ambiguous questions |
| `experiments/tests/test_box.py` | Every rule above, fired and quiet, and the never-reads check over every box file |
