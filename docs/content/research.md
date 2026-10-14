# What is known, and where the box sits

Research done on 14 October 2026 from papers, benchmarks and industry reports, to answer four
questions before box v2 is designed: what do people ask shopping agents, what has been built
to decide how much to retrieve, what has been built to ask the user back, and why a project
about answering questions matters for agents that buy. Only published sources were read. No
live marketplace was browsed, by project rule.

## 1. What shopping agents are asked

**Benchmarks publish the task types.** Five cover shopping directly.

| Benchmark | Year | Setting | Task types | Finding |
| --- | --- | --- | --- | --- |
| WebShop | 2022 | one shop, 1.1 M Amazon products, 12,087 crowd-sourced instructions | find and buy a product matching attributes, options and a price limit: "a pair of black-and-blue sneaker that is good in rain weather, and price less than 90 dollars" | best agent 29% success against 59% for humans |
| WebArena | 2023 | one shop among five sites | the shop tasks are mostly shop administration | |
| WebMall | SIGIR 2026 | four shops, 4,421 offers, 91 tasks with exact answers | 11 categories in 5 groups: specific product search (23 tasks), vague product search including substitutes and compatible products (19), cheapest product search with or without requirements (26), cart and checkout (15), end to end (8) | vague requirements were hardest, best agent 64% complete |
| DeepShop | 2025 | real user queries evolved by attributes, filters and sorting preferences, five domains | easy, medium and hard by the number of evolutions | success below 35%; agents fail on filters and sorting |
| ComboShoppingBench | Aug 2026 | baskets under a budget with coupons | combination buying | out of this project's scope |

Also relevant: ShopGym (May 2026) for simulating e-commerce agents at scale, WebChoreArena (2025)
for long tedious web tasks, Agentic Commerce World (Aug 2026), an auditable environment that
names the failure modes of shopping agents as wrong product, price errors and hallucinated
features, prices or availability, and ProductResearch (Feb 2026), which trains agents to write
product research reports. Shopping MMLU (NeurIPS 2024, the KDD Cup 2024 task) tests shopping
knowledge in language models rather than browsing.

**What people actually use assistants for.** NRF and Salesforce reported in January 2026 that
nearly half of online shoppers used an AI assistant during their last purchase, up from 18% in
2024. The pre-purchase uses reported most are comparison, sizing and fit, and compatibility.
A 2025 study of Ctrip's assistant found consumers use it for exploratory, hard-to-keyword
requests. These are reading tasks: the buying happens after the answer.

**The census against the project's algebra.** Every reading task in the sources above has one
of a small set of logical forms, and the form fixes the retrieval it needs:

| Form | Count in WebMall's reading tasks (68 of 91) | In our files (42 entries, counted by `targeting.classify` and read by hand for the single-listing file) | Primitive |
| --- | --- | --- | --- |
| Find a specific product or fact | 23 | 8 single-listing lookups, one of them a comparison of two named sellers | lookup, one page per shop |
| Cheapest offer, with or without requirements | 26 | 8 cheapest or lowest price | bound and prune |
| Vague requirements, substitutes, compatibles | 19 | 0 | filter by attribute, after asking back when the attribute is not on the page |
| Every listing has it | 0 | 5 | counterexample |
| How many | 0 | 2 | exhaust |
| Does any buyer say | 0 | 9, never run | witness over pages |
| Answered on the results page | 0 | 4 | none |
| Best per unit | 0 | 6 | bound on a rate |

WebShop's instructions are all one form: filtered search with a price ceiling, which is
"existence with filters". DeepShop adds filters and sorting to that. So the forms are few, and
the two the project has not built, filtered search and attribute-based clarification, are where
the benchmarks say agents fail most.

## 2. Deciding how much to retrieve

Three bodies of work, none of them about opening listings in a shop.

**Adaptive retrieval and stopping for question answering.** FLARE and Self-RAG retrieve when
the model is uncertain. The 2026 line adds budgets and calibration: AB-RAG answers, estimates
confidence from the model's certainty, the agreement between answer and evidence and the
spread of retrieval scores, then retrieves more or stops under a fixed budget; Stop-RAG learns
a value for retrieving again; TASR stops when the answer repeats and a calibrated probability
passes a threshold; MiCP uses conformal prediction to stop early with a coverage guarantee;
"Know Before You Fetch" allocates a retrieval budget per question before fetching. All of
these read the model's uncertainty. None reads a bound from the page, and none can refuse an
answer the model is confident about, which is the failure this project measured.

**Cost-aware exploration for agents.** Budget-Aware Tool-Use (Nov 2025) shows agents search
shallowly unless told their budget. Calibrate-Then-Act (Feb 2026) has the agent weigh the cost
of another look against the expected value of what it would learn, from priors over what it
has not seen. "Scores Are Not Decisions" (Jul 2026) makes stopping a cost decision for tool
acquisition. These are the right framing for the box's stop rule, and the advertised price is
exactly a prior over what an unopened listing can hold.

**Classical sequential search.** Optimal stopping, branch and bound and information foraging
are the theory behind the bound: a lower bound on an unopened item lets it be pruned without
cost. The box's "cheapest" strategy is branch and bound with the advertised price as the bound.

**Product question answering.** The ACL 2023 survey splits PQA into opinion, extraction,
retrieval and generation settings, and names answerability as a core challenge: AmazonQA
(2019, 923 k questions) labels each question answerable or not from the reviews available and
trains a classifier for it. That is the review side of what the box's refusal check does for
listings, and it is where the review questions join next week.

## 3. Asking the user back

Two strands. **Preference elicitation in product search** asks which attributes the user wants
before searching: ProductAgent (2024) benchmarks clarification in conversational product
search, "Learning to Ask Critical Questions" (2024) and PSCon (2025) pick the attribute to ask
about, and "Dialogue to Discovery" (Jun 2026) decides whether to ask or recommend from the
distribution of attribute values in the matching part of the catalogue. **Clarification in
agents** asks before acting: SAGE-Agent (ACL 2026) chooses questions by structured uncertainty
and cuts the number asked by 1.5 to 2.7 times at higher coverage; DiscoBench (Jun 2026)
defines facet, entity, temporal and numerical ambiguity for search agents, scores both
over-asking and under-asking, and uses a simulated user to answer. The box's "offer" case is
facet ambiguity, its scripted user is DiscoBench's simulator, and over-asking on the clear
questions is the control the spec already defines. "Dialogue to Discovery" gives the rule for
the attribute case: ask when the catalogue splits on the attribute, otherwise do not.

## 4. Verifying a model's plan before running it

LLM-Modulo (2024) and Metagent-P (ACL 2025) have a model propose and a symbolic critic verify,
in a loop, before anything executes. "Bridging LLM Planning Agents and Formal Methods" (Oct
2025) translates a plan sketch into a formal model and checks it. The box's planner already
does the small version of this: four soundness properties checked on every plan, and the
18 September probe showed a model writes sound plans 7 of 8 times with the properties stated.
The one it missed, comparing a delivery time the shop does not publish, is the property to add.

## 5. Why answering matters for agents that buy

Agents are starting to buy. ChatGPT added shopping research and instant checkout in 2025;
Perplexity launched shopping with PayPal checkout; the retail press in 2026 asks who carries
the cost when an agent "hallucinate[s] an order or misinterpret[s] a budget". Every purchase
is preceded by a retrieval question: which offer, at what price, in which size, in stock. A
wrong answer there becomes a wrong purchase one click later. The live assistant observed in
August 2026 named one seller 27% cheaper for a carton it was dearer for, with no sign of
doubt. So the project's claim is the precondition for agentic buying: the agent answers the
retrieval question correctly, at a known cost, and says when it cannot. Buying is one more
action after that, and this project leaves it out on purpose.

## 6. Scope, stated

In scope: questions answered by reading and retrieving across several listings of one shop:
price, size and availability now, counts, universal claims, best of a population, and from
next week, what reviews say. Out of scope, and said so: buying, discounts and coupons
(ComboShoppingBench covers them), shipping and delivery, several shops at once (WebMall), and
preference elicitation about what the user wants in the first place.

## Sources

WebShop: Yao et al., 2022, arxiv.org/abs/2207.01206. WebMall: arxiv.org/abs/2508.13024,
SIGIR 2026. DeepShop: Lyu et al., 2025, arxiv.org/abs/2506.02839. ComboShoppingBench:
arxiv.org/abs/2608.09282. ShopGym: arxiv.org/abs/2605.16116. WebChoreArena:
arxiv.org/abs/2506.01952. Agentic Commerce World: arxiv.org/abs/2608.02441. ProductResearch:
arxiv.org/abs/2602.23716. Shopping MMLU: arxiv.org/abs/2410.20745. NRF and Salesforce survey,
Jan 2026, as reported at digitalapplied.com. Ctrip study: arxiv.org/abs/2603.24947. AB-RAG:
arxiv.org/abs/2606.29090. Stop-RAG: arxiv.org/abs/2510.14337. TASR: arxiv.org/abs/2606.13814.
MiCP: arxiv.org/abs/2604.01413. Know Before You Fetch: arxiv.org/abs/2606.29959. Budget-Aware
Tool-Use: arxiv.org/abs/2511.17006. Calibrate-Then-Act: arxiv.org/abs/2602.16699. Scores Are
Not Decisions: arxiv.org/abs/2607.27083. PQA survey: Deng et al., ACL 2023. AmazonQA: Gupta et
al., IJCAI 2019. ProductAgent: arxiv.org/abs/2407.00942. Learning to Ask Critical Questions:
arxiv.org/abs/2403.02754. PSCon: arxiv.org/abs/2502.13881. Dialogue to Discovery:
arxiv.org/abs/2606.24194. SAGE-Agent: arxiv.org/abs/2511.08798. DiscoBench:
arxiv.org/abs/2606.27669. Metagent-P: ACL 2025 Findings. Bridging LLM Planning Agents and
Formal Methods: arxiv.org/abs/2510.03469. Agentic commerce liability: Payments Dive and WWD,
2026.
