# Literature review: what exists, what it lacks, what it gave this project

21 October 2026. Every work below was checked today against its arXiv record (title,
authors, date, and any venue the record states) or against the publisher's or venue's own
page. A venue is named only where one of those sources confirms it. Otherwise the work is
cited as an arXiv preprint with its year. The earlier notes, `notes/related-work.md` (five
works read closely, 10 September) and `docs/content/research.md` (the survey of 14 October),
are folded in, and all 32 arXiv numbers they cite were re-checked: each exists with the title
given.

One correction follows from the check. SAGE-Agent appeared in the **Findings of ACL 2026**,
not the ACL 2026 main conference. The update page and `docs/content/research.md` both say
"ACL 2026".

Each entry answers three questions. **Did**: what the work does. **Not here**: what it does
not cover for this project's problem, a statement of scope rather than a criticism.
**Gave**: what it contributed to a decision in this project.

---

## The gap, in one paragraph

Web and shopping agent benchmarks measure whether an agent completes a task, and they report
that agents stop early or fail on filters, but none builds a shop where the answer sits behind
a variant menu, and none asks whether the agent knew it had not looked. Adaptive retrieval
decides when to stop from the model's own confidence, which is the one signal that fails
here: an agent that read four of fifteen listings is confidently right about those four.
Clarification research asks when a question is ambiguous, but it scores the asking, not
whether the agent then applies the answer. Security research treats hidden or misleading
content as an attack, so its defences filter what enters the agent's context, while gated
information never enters it. Classical search theory, from branch and bound to Weitzman's
Pandora rule and Fagin's threshold algorithm, already says how to stop early with a guarantee
when every unopened option carries a bound. This project joins the pieces. It reads the bound
off the results page, plans the retrieval from the question's logical form, asks back when the
reading changes the answer, refuses what the shop does not show, and checks the answer
against the listings the agent actually opened.

---

## 1. Feature map: what each part of the project is built on

| Project feature | Built on | What this project adds |
| --- | --- | --- |
| Interaction-gated information as the object of study | Hidden-web crawling (Raghavan and Garcia-Molina 2001, Madhavan et al. 2008), AJAX state crawling (Mesbah et al. 2012) | The gate is a variant menu inside one listing, and the reader is an agent answering one question. Exploring every state becomes the expensive baseline, not the goal |
| The structured-data audit | Schema.org (Guha et al. 2016), Web Data Commons (Meusel et al. 2014), Google's support for ProductGroup (2024) | The markup for per-variant prices exists and is read by a major search engine, yet both shops observed publish one plain Offer. So the bound must be read from the rendered page |
| Generated gated markets on WebArena | WebArena (Zhou et al. 2024), WebArena Verified (El hattami et al. 2025), WebShop's product options (Yao et al. 2022), ShopGym (Savadikar et al. 2026) | Configurable products with per-size prices and stock, answer keys computed from the data, held-out markets generated after the plan was fixed |
| Bound and prune with the advertised price | Branch and bound (Land and Doig 1960), Pandora's rule (Weitzman 1979), the threshold algorithm (Fagin et al. 2003) | The advertised "from" price is a free and exact lower bound, so the search is deterministic and provably never stops before the answer is certain |
| Question to logical form to strategy | Semantic parsing (Yu et al. 2018, Shin et al. 2021), routing by question type (Jeong et al. 2024) | Routing by the question's quantifier rather than a learned complexity score, so every strategy carries a stop rule that can be proved |
| A stop rule that reads the page, not the model | Stop-RAG, TASR, AB-RAG, adaptive stopping with conformal prediction, Know Before You Fetch, Calibrate-Then-Act, Budget-Aware Tool Use | All of these stop on the model's own signal. The block stops on a bound, so it can refuse a confident wrong answer |
| Checking the answer against what was opened | Self-RAG's support check (Asai et al. 2024), Kadavath et al. 2022, Huang et al. 2024, *When Web Agents Finish but Still Fail* (Sogani et al. 2026) | The evidence checked is the agent's own trace, which the agent chose, not a passage set someone else fixed. Switched off in the claim run. Replayed over it, the check refused the one answer whose proof did not hold and none of the three miscounts |
| Asking back on "offer" | Aliannejadi et al. 2019, AmbigQA, CLAM, Clarify When Necessary, SAGE-Agent, DiscoBench | Asks only when the readings give different answers on this shop, and measures whether the agent then applies the reply. Haiku did not, DeepSeek did |
| Refusing what the shop does not show | Unanswerable questions (Rajpurkar et al. 2018), the abstention survey (Wen et al. 2024), AmazonQA's answerability labels | The refusal happens before any browsing, for $0 |
| A model proposes, rules decide | LLM-Modulo (Kambhampati et al. 2024), LLM+P, Logic-LM, CaMeL | The model only reads the question. Rules plan, stop and check, so the guarantees do not depend on the model |
| The planned model front door | Few-shot parsing into a controlled form (Shin et al. 2021), JSONSchemaBench, format restrictions (Tam et al. 2024) | Validate the form after generation, and give the model examples and the shop's vocabulary, as the probe's 21 of 24 against the rules' 17 suggests |
| Evaluation: cost against correctness, held out, fixed in advance | AI Agents That Matter, the Agentic Benchmark Checklist, Miller 2024, Nosek et al. 2018, Holm 1979, van Elteren 1960, Newcombe 1998 | Correctness and listings opened as the two axes, a held-out market, a protocol committed before the market existed |
| Two axes of generalisation | SWE-agent's interface finding, AgentOccam, Agentless, BrowserGym | The same block across models (Haiku, DeepSeek) and, planned, across scaffolds |
| The registered title, injection against ambiguity | Greshake et al. 2023, InjecAgent, AgentDojo, WASP, StakeBench, and dark patterns (Mathur et al. 2019, SusBench, TrickyArena, DECEPTICON) | The same silent wrong answer with no adversary. Filters and detectors cannot catch it, because nothing harmful enters |
| Why answering matters | ACES (Allouah et al. 2025), Magentic Marketplace, the Ctrip study, τ-bench | Agents already choose products, and a retrieval question comes before every purchase |

---

## 2. The problem's ancestors: information behind interaction

**Crawling the Hidden Web.** S. Raghavan and H. Garcia-Molina, VLDB 2001, pp. 129 to 138.
- **Did.** Showed that crawlers that follow links miss the large body of content behind
  search forms, and built HiWE, a crawler that fills in forms to reach it.
- **Not here.** The hidden content is a database behind a form, and the goal is coverage for
  indexing, so surfacing everything is the aim.
- **Gave.** The framing. Interaction-gated information is a small hidden web inside each
  listing: real, published, and invisible to anything that only reads what first loads.

**Google's Deep-Web Crawl.** J. Madhavan, D. Ko, L. Kot, V. Ganapathy, A. Rasmussen, A. Halevy,
PVLDB 1(2), 2008, pp. 1241 to 1252.
- **Did.** Surfaced deep-web content at web scale by generating form submissions, pruning the
  combinations to those worth indexing.
- **Not here.** It prunes by value to an index, not by what one question needs.
- **Gave.** The precedent for pruning combinations before submitting them, which is what bound
  and prune does with listings.

**Crawling AJAX-based Web Applications through Dynamic Analysis of User Interface State
Changes (Crawljax).** A. Mesbah, A. van Deursen, S. Lenselink, ACM Transactions on the Web 6(1),
2012. [doi:10.1145/2109205.2109208](https://doi.org/10.1145/2109205.2109208)
- **Did.** Crawled JavaScript applications by firing events on clickable elements and
  inferring a state machine of the interface's states.
- **Not here.** It explores every state. That is the "open everything" arm: correct and
  expensive.
- **Gave.** The exhaustive baseline's ancestry, and the point that state created in the browser
  is invisible to a plain fetch. That is why the block should read the page the agent's browser
  rendered rather than fetch the shop itself.

**A Scalable Comparison-Shopping Agent for the World-Wide Web (ShopBot).** R. B. Doorenbos,
O. Etzioni, D. S. Weld, Agents 1997.
[PDF](https://homes.cs.washington.edu/~etzioni/papers/agents97.pdf)
- **Did.** An early comparison-shopping agent that learned to extract product information from
  vendors' pages and summarised prices for the user.
- **Not here.** It assumed the price is on the page it reads. A variant menu breaks that.
- **Gave.** Comparison shopping by software agents is a thirty-year-old goal, and "which seller
  is cheapest" is its oldest question. The new obstacle is the gate.

### Structured data

**Schema.org: Evolution of Structured Data on the Web.** R. V. Guha, D. Brickley, S. Macbeth,
Communications of the ACM 59(2), 2016, pp. 44 to 51.
[doi:10.1145/2844544](https://doi.org/10.1145/2844544)
- **Did.** Described schema.org, the shared vocabulary for marking up page content, Product and
  Offer included.
- **Not here.** A vocabulary, not a measure of how sites use it.
- **Gave.** The standard the audit checked against. AggregateOffer, with lowPrice and
  highPrice, exists for exactly a listing with many prices.

**The WebDataCommons Microdata, RDFa and Microformat Dataset Series.** R. Meusel, P. Petrovski,
C. Bizer, ISWC 2014, LNCS 8796, pp. 277 to 292.
- **Did.** Extracted structured data from the Common Crawl at scale. Its most recent dataset
  then held over 211 million product descriptions.
- **Not here.** It measures whether markup is present, not whether the offer marked up is the
  variant a shopper asks about.
- **Gave.** Evidence that product markup is common, which makes the audit's finding notable:
  the markup is there, and it is wrong for variants. WebMall's shops are built from the same
  Common Crawl product data.

**Adding structured data support for Product Variants.** Google Search Central blog, February
2024. [Link](https://developers.google.com/search/blog/2024/02/product-variants)
- **Did.** Google began supporting schema.org's ProductGroup with hasVariant, variesBy and
  productGroupID, for products sold in sizes and colours.
- **Not here.** Support is not adoption.
- **Gave.** A sharper limitation statement. A structured channel for per-variant prices exists
  and a major search engine reads it, yet both shops observed publish one plain Offer. Gating
  is a publishing choice, not a technical necessity.

---

## 3. The environment and the shopping benchmarks

**WebArena: A Realistic Web Environment for Building Autonomous Agents.** S. Zhou et al.,
ICLR 2024. [arXiv:2307.13854](https://arxiv.org/abs/2307.13854)
- **Did.** Self-hosted, reproducible websites in four domains, a Magento shop among them, with
  tasks judged by functional correctness. The best GPT-4 agent reached 14.41% against 78.24%
  for humans.
- **Not here.** The shop's 104,368 products are all simple products, so no listing hides a
  per-variant price.
- **Gave.** The environment and its Magento backend, which this project extends with
  configurable products.

**WebArena Verified: Reliable Evaluation for Web Agents.** A. El hattami, M. Thakkar,
N. Chapados, C. Pal, Workshop on Scaling Environments for Agents at NeurIPS 2025.
[OpenReview](https://openreview.net/forum?id=94tlGxmqkN),
[code](https://github.com/ServiceNow/webarena-verified)
- **Did.** Audited all 812 WebArena tasks, repaired misaligned evaluations, replaced substring
  matching with type-aware comparators, added confidence intervals, and released smaller Docker
  images.
- **Not here.** It fixes how tasks are judged and adds no new kind of task.
- **Gave.** The distribution this project runs, and the natural home for its gated-variant
  extension (see `docs/guides/webarena-contribution.md`).

**WebShop: Towards Scalable Real-World Web Interaction with Grounded Language Agents.**
S. Yao, H. Chen, J. Yang, K. Narasimhan, NeurIPS 2022.
[arXiv:2207.01206](https://arxiv.org/abs/2207.01206)
- **Did.** A shop built from Amazon products, with 12,087 crowd-sourced instructions asking an
  agent to find and buy a product matching attributes, options and a price limit. The best
  agent reached 29% against 59% for human experts.
- **Not here.** Its tasks end in buying one matching product. They do not ask for a comparison
  across sellers whose per-option prices stay hidden until chosen.
- **Gave.** Product options as part of a shopping task. This project makes the option change
  the price and the stock, which turns choosing an option into a retrieval problem.

**WebMall: A Multi-Shop Benchmark for Evaluating Web Agents.** R. Peeters et al., SIGIR 2026.
[arXiv:2508.13024](https://arxiv.org/abs/2508.13024)
- **Did.** Four simulated shops filled with heterogeneous Common Crawl product data, and
  comparison-shopping tasks from specific searches to cheapest-product and vague-requirement
  searches. The best agents stayed below 65% on the cheapest and vague categories.
- **Not here.** The comparison is across shops, not across variants inside a listing.
- **Gave.** The census of task shapes the block's strategies were checked against. Considered
  as a second environment and set aside on 21 October in favour of a more realistic WebArena
  market.

**DeepShop: A Benchmark for Deep Research Shopping Agents.** Y. Lyu et al., 2025.
[arXiv:2506.02839](https://arxiv.org/abs/2506.02839)
- **Did.** Evolved real shopping queries by attributes, filters and sorting preferences into
  three difficulty levels. Agents struggled most with filters and sorting.
- **Not here.** It runs on live sites, so runs cannot be repeated exactly, and the hard part is
  filtering rather than hidden variant prices.
- **Gave.** Evidence that filter-style questions are where agents fail, behind the filter
  strategy.

**ShopGym: An Integrated Framework for Realistic Simulation and Scalable Benchmarking of
E-Commerce Web Agents.** C. Savadikar et al., 2026.
[arXiv:2605.16116](https://arxiv.org/abs/2605.16116)
- **Did.** Argues the field lacks a way to be realistic and reproducible at once, and converts
  seed storefronts into self-contained sandbox shops through anonymised shop specifications,
  then generates grounded tasks.
- **Not here.** Its build starts from live storefronts, which this project's rules forbid it to
  automate.
- **Gave.** The method for this week's realism work: make the generated market structurally
  like real shops, in layout, catalogue mix and policies, while staying self-hosted.

**WebChoreArena: Evaluating Web Browsing Agents on Realistic Tedious Web Tasks.** A. Miyai et
al., COLM 2026. [arXiv:2506.01952](https://arxiv.org/abs/2506.01952)
- **Did.** 532 labour-intensive tasks on WebArena's sites, needing memory, calculation and long
  exploration.
- **Not here.** The difficulty is tedium, not gating: the information is reachable by
  following links.
- **Gave.** Support that counting across every listing is a genuine and hard task shape, the
  exhaust strategy.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| Mind2Web, X. Deng et al., NeurIPS 2023, [arXiv:2306.06070](https://arxiv.org/abs/2306.06070) | Over 2,000 tasks from 137 real websites. Filtering the HTML with a small model first helps a large model act | Static snapshots cannot reveal a state that needs a click | The observation-size problem that openJiuwen's card probe exists to solve |
| VisualWebArena, J. Y. Koh et al., ACL 2024, [arXiv:2401.13649](https://arxiv.org/abs/2401.13649) | Tasks that need the screenshot, including a classifieds shop | On a gated page the screenshot and the page text agree, and both lack the price | The argument that adding vision does not fix gating |
| The BrowserGym Ecosystem, T. Le Sellier De Chezelles et al., 2024, [arXiv:2412.05467](https://arxiv.org/abs/2412.05467), with WorkArena, A. Drouin et al., ICML 2024, [arXiv:2403.07718](https://arxiv.org/abs/2403.07718) | One interface over many web benchmarks, with page text, accessibility tree and screenshot as observations | A harness, not a retrieval policy | The vocabulary for the simpler agent's observations, and for reading the agent's own page |

---

## 4. Agents and scaffolds

**ReAct: Synergizing Reasoning and Acting in Language Models.** S. Yao et al., ICLR 2023.
[arXiv:2210.03629](https://arxiv.org/abs/2210.03629)
- **Did.** Interleaved reasoning with actions, the loop most agents still run.
- **Not here.** Says nothing about how much to retrieve before answering.
- **Gave.** The shape of the simpler second agent.

**SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering.** J. Yang et al.,
NeurIPS 2024. [arXiv:2405.15793](https://arxiv.org/abs/2405.15793)
- **Did.** Showed that the interface an agent is given, not only the model, decides how well it
  does.
- **Not here.** Software engineering, not shopping.
- **Gave.** The frame for the cause found in week 1: openJiuwen's card reader limits itself to
  the screen by default, an interface choice, and switching it off took "opened what it needs"
  from 3 to 15 of 15 on Thornwood.

**AgentOccam: A Simple Yet Strong Baseline for LLM-Based Web Agents.** K. Yang et al.,
ICLR 2025. [arXiv:2410.13825](https://arxiv.org/abs/2410.13825)
- **Did.** Raised WebArena success by 9.8 points over the previous best only by refining the
  observation and action spaces.
- **Not here.** It aligns what the agent sees with what the model handles well. It does not ask
  whether what the agent sees contains the answer.
- **Gave.** Confirmation that observation design is a first-order effect, which is why the cause
  of the early stop was looked for in the observation first.

**GPT-4V(ision) is a Generalist Web Agent, if Grounded (SeeAct).** B. Zheng et al., ICML 2024.
[arXiv:2401.01614](https://arxiv.org/abs/2401.01614)
- **Did.** Ran a vision model as a web agent on live sites and found grounding, turning a plan
  into a click, to be the bottleneck.
- **Not here.** Better grounding cannot help when the price is not rendered.
- **Gave.** With VisualWebArena, the reason the project kept to page text.

**Beyond Browsing: API-Based Web Agents.** Y. Song, F. Xu, S. Zhou, G. Neubig, 2024.
[arXiv:2410.16464](https://arxiv.org/abs/2410.16464)
- **Did.** On WebArena, agents given APIs beat browsing agents, and hybrid agents that use both
  gained over 24 points, to 38.9%.
- **Not here.** It assumes the shop offers an API. Real marketplaces draw their pages in the
  browser and guard their internal calls.
- **Gave.** A name for what the block does today. Its own fetch of the results page is an
  API-style read, legitimate on Magento, unrealistic on Shopee. So the next version reads the
  page the agent's browser rendered.

**Tree Search for Language Model Agents.** J. Y. Koh, S. McAleer, D. Fried, R. Salakhutdinov,
2024. [arXiv:2407.01476](https://arxiv.org/abs/2407.01476)
- **Did.** Best-first search inside the environment improved WebArena success by 28% relative,
  and success grew with compute.
- **Not here.** It buys success with more interactions.
- **Gave.** The other end of the cost curve. The block aims for the correctness of thorough
  search at a targeted cost.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| Agentless, C. S. Xia et al., 2024, [arXiv:2407.01489](https://arxiv.org/abs/2407.01489) | A simple pipeline rivalled complex agents on software tasks | Not web agents | The case for a plain agent as a floor |
| BrowseComp, J. Wei et al., 2025, [arXiv:2504.12516](https://arxiv.org/abs/2504.12516) | 1,266 questions that need persistent browsing for hard-to-find facts | It sidesteps ambiguity by design, in its own words | Persistence alone is not enough. Ambiguity needs its own handling |
| Mind2Web 2, B. Gou et al., 2025, [arXiv:2506.21506](https://arxiv.org/abs/2506.21506) | Long agentic-search tasks judged by an agent | Answers change over time, so keys are judged, not exact | The contrast that justifies exact keys computed from a generated market |

**When Web Agents Finish but Still Fail.** A. Sogani et al., 2026.
[arXiv:2606.20724](https://arxiv.org/abs/2606.20724)
- **Did.** Trace analysis of web agents found three persistent failures, one of them premature
  termination on partial answers, and concluded that closing the gap "requires
  evidence-grounded coverage and synthesis diagnostics".
- **Not here.** It diagnoses, and builds no policy.
- **Gave.** Independent corroboration of the failure, in another environment by other authors,
  and a specification the block implements: a coverage check run as a policy before the answer
  goes out.

---

## 5. Deciding what to retrieve, and when to stop

### The theory behind the stop rule

**An Automatic Method of Solving Discrete Programming Problems.** A. H. Land and A. G. Doig,
Econometrica 28(3), 1960, pp. 497 to 520.
- **Did.** Introduced branch and bound: discard a whole part of the search once its bound shows
  it cannot beat the best solution found.
- **Not here.** Integer programming, with no browsing.
- **Gave.** The cheapest-seller strategy. A listing whose advertised price is already at or
  above the best price found cannot win, so it is skipped unopened.

**Optimal Search for the Best Alternative.** M. L. Weitzman, Econometrica 47(3), 1979,
pp. 641 to 654.
- **Did.** Solved "Pandora's problem": with boxes of uncertain value that cost something to
  open, open them in order of a reservation value and stop once the best found beats every
  unopened box's reservation value.
- **Not here.** Values are random with known distributions.
- **Gave.** The block's order and stop rule are the exact special case. Each listing's
  advertised price is a known lower bound, so open in ascending order and stop once nothing
  unopened can beat the best found.

**Optimal Aggregation Algorithms for Middleware.** R. Fagin, A. Lotem, M. Naor, Journal of
Computer and System Sciences 66(4), 2003. Preliminary version PODS 2001.
[arXiv:cs/0204046](https://arxiv.org/abs/cs/0204046)
- **Did.** The threshold algorithm for top-k queries over sorted lists, which stops once k
  results beat a threshold computed from what is still unread. It is instance-optimal, and
  won the 2014 Gödel Prize.
- **Not here.** Databases, not web pages.
- **Gave.** The stop rule for "the three cheapest sellers": stop when three are held and no
  unopened listing's bound can enter them.

**The Economics of Information.** G. J. Stigler, Journal of Political Economy 69(3), 1961,
pp. 213 to 225.
- **Did.** Treated information as a good with a cost: a shopper keeps searching only while the
  expected saving exceeds the cost of one more look.
- **Not here.** Human shoppers and price dispersion, not agents.
- **Gave.** Why opening everything is not the answer, and why cost is an axis of the evaluation.

**Information Foraging.** P. Pirolli and S. Card, Psychological Review 106(4), 1999,
pp. 643 to 675.
- **Did.** Modelled people seeking information as foragers who follow "information scent" to
  maximise their rate of gain.
- **Not here.** A model of people, not a retrieval guarantee.
- **Gave.** The results page's advertised price is the scent that decides which listing to open
  next. The block makes the scent an exact bound.

### Adaptive retrieval and stopping for language models

**Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection.** A. Asai et
al., ICLR 2024. [arXiv:2310.11511](https://arxiv.org/abs/2310.11511)
- **Did.** Trained a model to emit tokens that decide when to retrieve and whether its output is
  supported by the passages retrieved.
- **Not here.** The support check tests faithfulness to passages a retriever chose. An answer
  can pass it while being wrong because the passages were the wrong ones.
- **Gave.** The closest ancestor of the block's sufficiency check, which differs in checking the
  agent's own trace, with rules and no training, through a black-box model.

**Active Retrieval Augmented Generation (FLARE).** Z. Jiang et al., EMNLP 2023.
[arXiv:2305.06983](https://arxiv.org/abs/2305.06983)
- **Did.** Retrieves when the next sentence the model is about to write contains low-confidence
  words.
- **Not here.** On a gated page there is nothing to be unconfident about at the moment of
  deciding.
- **Gave.** The clearest statement of the confidence trigger the block replaces.

**Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question
Complexity.** S. Jeong et al., NAACL 2024. [arXiv:2403.14403](https://arxiv.org/abs/2403.14403)
- **Did.** A small classifier predicts how complex a question is and routes it to no retrieval,
  one retrieval or many.
- **Not here.** The route is learned and carries no guarantee.
- **Gave.** Routing by the question. The block routes by the question's logical form instead,
  so each route comes with a provable stop rule.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| Stop-RAG, J. Park et al., NeurIPS 2025 workshop, [arXiv:2510.14337](https://arxiv.org/abs/2510.14337) | Learns a value for retrieving again, as a decision process | Stops on a learned value of the model's state | |
| TASR, A. Kieback et al., KDD 2026 Agent4IR workshop, [arXiv:2606.13814](https://arxiv.org/abs/2606.13814) | Stops when the answer repeats and a calibrated margin passes 0.25 | Repeating a confidently wrong answer passes | |
| AB-RAG, A. Kamthan, 2026, [arXiv:2606.29090](https://arxiv.org/abs/2606.29090) | Estimates confidence from three signals and retrieves more or stops, under a budget | Confidence from the model and its evidence | All of these define the gap: they stop on the model's own signal. An agent that read 4 of 15 listings is confidently right about those 4, and this project's confidence arm found almost no signal (AUROC 0.528). The block stops on a bound read from the page |
| Adaptive Stopping for Multi-Turn LLM Reasoning, X. Zhou et al., 2026, [arXiv:2604.01413](https://arxiv.org/abs/2604.01413) | Conformal prediction for multi-turn stopping, with a coverage guarantee | The guarantee is statistical over a calibration set | |
| Know Before You Fetch, Z. Dong et al., 2026, [arXiv:2606.29959](https://arxiv.org/abs/2606.29959) | Chooses closed-book, a little context, more context or abstaining before retrieving | Calibrated model probabilities | |
| Calibrate-Then-Act, W. Ding et al., 2026, [arXiv:2602.16699](https://arxiv.org/abs/2602.16699) | Has agents weigh the cost of another look against what it could change | Priors over unseen state, not a bound | The right framing: the advertised price is exactly a prior over what an unopened listing can hold |
| Budget-Aware Tool Use, T. Liu et al., COLM 2026, [arXiv:2511.17006](https://arxiv.org/abs/2511.17006) | Agents do not use a larger tool budget unless told about it | Web search, not shops | Why the block states the plan and its stop explicitly |
| Scores Are Not Decisions, Y. Feng et al., 2026, [arXiv:2607.27083](https://arxiv.org/abs/2607.27083) | Treats how many tools to acquire as a cost-aware stopping decision | Tool selection | Stopping is a decision with a cost, not a score threshold |

---

## 6. Knowing what you do not know

**Language Models (Mostly) Know What They Know.** S. Kadavath et al., 2022.
[arXiv:2207.05221](https://arxiv.org/abs/2207.05221)
- **Did.** Large models judge reasonably well whether they know an answer, and that judgement
  improves when relevant material is in the context.
- **Not here.** The context is given. An agent chooses its own context by acting, and a judgement
  conditioned on that context cannot see that it was badly chosen.
- **Gave.** The reason the block's check reads something outside the model's context: the
  record of what the agent opened.

**Large Language Models Cannot Self-Correct Reasoning Yet.** J. Huang et al., ICLR 2024.
[arXiv:2310.01798](https://arxiv.org/abs/2310.01798)
- **Did.** Self-correction without outside feedback fails, and sometimes makes answers worse.
- **Not here.** Reasoning tasks, not browsing.
- **Gave.** It ruled out the cheapest fix, asking the agent to re-check itself, and pointed to
  feedback from outside, which the block supplies.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| Teaching Models to Express Their Uncertainty in Words, S. Lin et al., 2022, [arXiv:2205.14334](https://arxiv.org/abs/2205.14334) | Models can state calibrated confidence in words | Confidence about a fixed question, not about coverage | The design of the confidence arm |
| Know What You Don't Know: Unanswerable Questions for SQuAD, P. Rajpurkar, R. Jia, P. Liang, ACL 2018, [arXiv:1806.03822](https://arxiv.org/abs/1806.03822) | Added unanswerable questions so models must learn to abstain | The passage is given | Refusing what the shop does not show, such as delivery time |
| Know Your Limits: A Survey of Abstention in LLMs, B. Wen et al., TACL 2024, [arXiv:2407.18418](https://arxiv.org/abs/2407.18418) | Surveys when and how models should abstain | Models, not agents that could look further | The vocabulary for RQ2: does the agent signal what it has not retrieved |

---

## 7. Ambiguity, and asking the user back

**Asking Clarifying Questions in Open-Domain Information-Seeking Conversations.**
M. Aliannejadi, H. Zamani, F. Crestani, W. B. Croft, SIGIR 2019.
[arXiv:1907.06554](https://arxiv.org/abs/1907.06554)
- **Did.** Showed that asking one good clarifying question improves retrieval, and built a
  dataset for selecting it.
- **Not here.** Search over documents, not agents over shops.
- **Gave.** The case for asking rather than guessing.

**AmbigQA: Answering Ambiguous Open-domain Questions.** S. Min, J. Michael, H. Hajishirzi,
L. Zettlemoyer, EMNLP 2020. [arXiv:2004.10645](https://arxiv.org/abs/2004.10645)
- **Did.** Found that many open-domain questions have several plausible answers.
- **Not here.** It answers every reading rather than asking which one.
- **Gave.** The "offer" count is such a question: 10 or 7 on Ashcombe, depending on the reading.

**Clarify When Necessary: Resolving Ambiguity Through Interaction with LMs.** M. J. Q. Zhang
and E. Choi, 2023. [arXiv:2311.09469](https://arxiv.org/abs/2311.09469)
- **Did.** Split clarification into three tasks: deciding when to ask, deciding what to ask, and
  answering correctly with the information gained.
- **Not here.** Question answering, translation and inference, not agents that act.
- **Gave.** The exact place the claim run's finding sits. The block did the first two, and Haiku
  failed the third: told the reading, it did not apply it.

**CLAM: Selective Clarification for Ambiguous Questions with Generative Language Models.**
L. Kuhn, Y. Gal, S. Farquhar, 2022. [arXiv:2212.07769](https://arxiv.org/abs/2212.07769)
- **Did.** Asks only on questions detected as ambiguous, improving accuracy on a mix of
  ambiguous and clear questions.
- **Not here.** It detects ambiguity in the abstract, not against what a given shop shows.
- **Gave.** Clear questions as the control for over-asking.

**Structured Uncertainty guided Clarification for LLM Agents (SAGE-Agent).** M. Suri et al.,
Findings of ACL 2026. [arXiv:2511.08798](https://arxiv.org/abs/2511.08798)
- **Did.** Chooses questions by the expected value of the answer over tool parameters, asking
  1.5 to 2.7 times fewer questions at higher coverage.
- **Not here.** Tool calling, not reading shops.
- **Gave.** The principle the block follows: ask only when the answer would change what is done.

**When Search Agents Should Ask: DiscoBench for Clarification-Aware Deep Search.** Y. Tao et al.,
2026. [arXiv:2606.27669](https://arxiv.org/abs/2606.27669)
- **Did.** A benchmark of four ambiguity types with a simulated user. Searching again instead of
  asking often did worse than guessing.
- **Not here.** Web search, not shops with gated variants.
- **Gave.** Support for asking rather than opening more listings, and the simulated user as a
  way to answer the block's question in a run.

**LLMs Get Lost In Multi-Turn Conversation.** P. Laban et al., 2025.
[arXiv:2505.06120](https://arxiv.org/abs/2505.06120)
- **Did.** Across top models, performance fell 39% on average when a task's details arrive over
  several turns. Models assume early and do not recover.
- **Not here.** Conversation, not an agent told a reading inside its task.
- **Gave.** A published account of the error the claim run recorded, "the user's stated reading
  not applied", and a reason to write the reading into the agent's instructions, not only into
  a reply.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| ProductAgent, J. Ye et al., 2024, [arXiv:2407.00942](https://arxiv.org/abs/2407.00942) | Clarifying questions in conversational product search, with a simulated user | What the user wants, not what a word means on this shop | Scope: preference elicitation is out |
| Learning to Ask Critical Questions for Assisting Product Search, Z. Li, L. Liao, T.-S. Chua, SIGIR eCom 2022, [arXiv:2403.02754](https://arxiv.org/abs/2403.02754) | Ask about critical attributes once the user has explored | Preference, not reading | NUS work on when to ask in product search |
| Dialogue to Discovery, S. Harne et al., 2026, [arXiv:2606.24194](https://arxiv.org/abs/2606.24194) | Ask about an attribute only when the catalogue splits on it | Recommends products | The rule for when not to ask |
| PSCon, J. Zou et al., SIGIR 2025, [arXiv:2502.13881](https://arxiv.org/abs/2502.13881) | A human-to-human dataset of conversational product search | Conversation data, not agents | Real wording for future question sets |

---

## 8. A model proposes, rules decide

**LLMs Can't Plan, But Can Help Planning in LLM-Modulo Frameworks.** S. Kambhampati et al.,
ICML 2024. [arXiv:2402.01817](https://arxiv.org/abs/2402.01817)
- **Did.** Argued that models should propose and sound external checkers should verify, rather
  than models planning alone.
- **Not here.** A position, with planning domains as examples.
- **Gave.** The block's overall shape: a model may read the question, and rules check and plan.

**LLM+P: Empowering Large Language Models with Optimal Planning Proficiency.** B. Liu et al.,
2023. [arXiv:2304.11477](https://arxiv.org/abs/2304.11477)
- **Did.** The model translates a problem into a formal planning language, and a classical
  planner finds an optimal plan. The model alone often failed to find even a feasible one.
- **Not here.** Static planning problems.
- **Gave.** The same split as the planned front door: translate into a form, let a solver with
  guarantees do the rest.

**Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical
Reasoning.** L. Pan et al., Findings of EMNLP 2023.
[arXiv:2305.12295](https://arxiv.org/abs/2305.12295)
- **Did.** The model writes a symbolic problem, a solver answers, and solver errors feed back to
  fix the translation.
- **Not here.** Logic puzzles.
- **Gave.** The feedback loop for the front door: a form the rules reject goes back to the model
  with the reason.

**Constrained Language Models Yield Few-Shot Semantic Parsers.** R. Shin et al., EMNLP 2021.
[arXiv:2104.08768](https://arxiv.org/abs/2104.08768)
- **Did.** With a few examples, a model maps questions into a controlled form that converts
  mechanically to the target representation.
- **Not here.** Before instruction-tuned models.
- **Gave.** The fix for the probe's detail errors: few examples and a controlled vocabulary. The
  model parser is zero-shot today and got every field right in only 2 of 24.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| Spider, T. Yu et al., EMNLP 2018, [arXiv:1809.08887](https://arxiv.org/abs/1809.08887) | Text to SQL across many databases | Databases | The block's form is a small query language: argmin, forall, count over listings |
| Binding Language Models in Symbolic Languages, Z. Cheng et al., ICLR 2023, [arXiv:2210.02875](https://arxiv.org/abs/2210.02875) | Models write programs that call the model only where needed | Tables | Rules where rules suffice, a model only where judgement is needed |
| PAL, L. Gao et al., 2022, [arXiv:2211.10435](https://arxiv.org/abs/2211.10435) | The model writes a program and an interpreter computes the answer | Arithmetic | The same division of labour |
| Metagent-P, Y. Zhou et al., Findings of ACL 2025 | Plan, verify, execute and reflect, with symbolic verification | Minecraft | Verify before acting |
| Bridging LLM Planning Agents and Formal Methods, K. Ramani et al., ASE 2025 AgenticSE workshop, [arXiv:2510.03469](https://arxiv.org/abs/2510.03469) | Translates plans into formal models and checks them | Plan verification datasets | Soundness properties checked on every plan |
| JSONSchemaBench, S. Geng et al., 2025, [arXiv:2501.10868](https://arxiv.org/abs/2501.10868) | Evaluates constrained decoding against real JSON schemas | Format, not meaning | Structured output can be made valid. Correct is a separate check |
| Let Me Speak Freely?, Z. R. Tam et al., 2024, [arXiv:2408.02442](https://arxiv.org/abs/2408.02442) | Strict format constraints lowered reasoning quality | General tasks | Let the model answer freely, then validate, rather than force the format while it reasons |
| OpenTag, G. Zheng et al., KDD 2018, [arXiv:1806.01264](https://arxiv.org/abs/1806.01264), and MAVE, L. Yang et al., WSDM 2022, [arXiv:2112.08663](https://arxiv.org/abs/2112.08663) | Extract attribute values from product text | Extraction, not question parsing | Normalising values, such as "medium" to M, a gap the probe found |

---

## 9. Adversaries: injection and dark patterns, the registered title

**Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with
Indirect Prompt Injection.** K. Greshake et al., 2023.
[arXiv:2302.12173](https://arxiv.org/abs/2302.12173)
- **Did.** Showed that instructions hidden in retrieved content can take over an application
  built on a model.
- **Not here.** Requires an attacker.
- **Gave.** The starting point of the registered title, and the contrast this project draws: the
  same kind of silent failure with no attacker at all.

**Who Pays the Price? Stakeholder-Centric Prompt Injection Benchmarking for Real-world Web
Agents (StakeBench).** Z. Wang et al., 2026.
[arXiv:2606.13385](https://arxiv.org/abs/2606.13385)
- **Did.** 264 injection cases on shopping web agents. No attack objective was reliably resisted,
  and some attacks succeed while the task still completes.
- **Not here.** Adversarial content.
- **Gave.** The pivot. A completed task with a wrong outcome is undetectable from outside, and
  removing the attacker leaves that invisibility in place.

**Defeating Prompt Injections by Design (CaMeL).** E. Debenedetti et al., 2025.
[arXiv:2503.18813](https://arxiv.org/abs/2503.18813)
- **Did.** Extracts the control flow from the trusted user query before reading untrusted data,
  so retrieved data can never change the program. It solved 77% of AgentDojo tasks with
  provable security, against 84% undefended.
- **Not here.** Security, not retrieval sufficiency.
- **Gave.** The block works the same way: its plan is fixed from the question before the agent
  reads a listing, so page text cannot change what gets retrieved. A design argument that the
  block also narrows the injection surface, worth one sentence in the report.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| InjecAgent, Q. Zhan et al., Findings of ACL 2024, [arXiv:2403.02691](https://arxiv.org/abs/2403.02691) | Benchmark of indirect injection on tool-using agents | Needs an attacker | The defence literature the title refers to |
| AgentDojo, E. Debenedetti et al., NeurIPS 2024, [arXiv:2406.13352](https://arxiv.org/abs/2406.13352) | Dynamic environment for injection attacks and defences | Same | Same |
| WASP, I. Evtimov et al., 2025, [arXiv:2504.18575](https://arxiv.org/abs/2504.18575) | Injection benchmark for web agents | Same | Same |
| EIA, Z. Liao et al., ICLR 2025, [arXiv:2409.11295](https://arxiv.org/abs/2409.11295) | Injected page elements that leak private data | Same | Same |
| Adaptive Attacks Break Defenses, Q. Zhan et al., Findings of NAACL 2025, [arXiv:2503.00061](https://arxiv.org/abs/2503.00061) | Adaptive attacks beat every defence tested | Same | Filters fail under attack. Here there is nothing to filter |
| Design Patterns for Securing LLM Agents against Prompt Injections, L. Beurer-Kellner et al., 2025, [arXiv:2506.08837](https://arxiv.org/abs/2506.08837) | Agent designs with provable resistance to injection, and their costs | Security | Plan first, then execute: the block's order |
| Dark Patterns at Scale, A. Mathur et al., CSCW 2019, [arXiv:1907.07032](https://arxiv.org/abs/1907.07032) | Dark patterns on 11.1% of 11,000 shopping sites | Aimed at people, deliberate | Gating is not a dark pattern: no merchant here meant to deceive |
| SusBench, L. Guo et al., IUI 2026, [arXiv:2510.11035](https://arxiv.org/abs/2510.11035) | Agents and people both fall for covert patterns, Hidden Information among them | Deliberate manipulation | The adversarial cousin of gating, and the line between the two |
| Investigating the Impact of Dark Patterns on LLM-Based Web Agents (TrickyArena), D. Ersoy et al., IEEE S&P 2026, [arXiv:2510.18113](https://arxiv.org/abs/2510.18113) | With one dark pattern present, agents fell for it 41% of the time | Same | Same |
| DECEPTICON, P. Cuvin, H. Zhu, D. Yang, 2025, [arXiv:2512.22894](https://arxiv.org/abs/2512.22894) | Dark patterns steered agents to bad outcomes in over 70% of tasks | Same | Same |

---

## 10. Agentic commerce: why answering correctly matters

**What Is Your AI Agent Buying? Evaluation, Biases, Model Dependence, & Emerging Implications
for Agentic E-Commerce (ACES).** A. Allouah et al., 2025.
[arXiv:2508.02630](https://arxiv.org/abs/2508.02630)
- **Did.** Audited how agents choose products: strong position biases, choice concentrated on a
  few products, preferences that shift with model updates.
- **Not here.** Choice among visible products, not retrieval of hidden facts.
- **Gave.** Evidence that agents favour what is shown first, the same tendency as openJiuwen
  trusting the cards on screen.

**Magentic Marketplace: An Open-Source Environment for Studying Agentic Markets.** G. Bansal et
al., 2025. [arXiv:2510.25779](https://arxiv.org/abs/2510.25779)
- **Did.** Simulated markets of buying and selling agents. Every model showed a severe
  first-proposal bias, a 10 to 30 times advantage for answering fast.
- **Not here.** Negotiation between agents.
- **Gave.** More evidence that agents settle on the first acceptable option, the behaviour the
  stop rule disciplines.

**τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains.** S. Yao, N. Shinn,
P. Razavi, K. Narasimhan, ICLR 2025. [arXiv:2406.12045](https://arxiv.org/abs/2406.12045)
- **Did.** A retail and airline benchmark with a simulated user and policies. Agents succeeded on
  under half the tasks and were inconsistent across trials, pass^8 under 25% in retail.
- **Not here.** Tools over a database, not browsing.
- **Gave.** Repeating each question and reporting consistency, the reason for three runs per
  question.

| Work | Did | Not here | Gave |
| --- | --- | --- | --- |
| Shopping with a Platform AI Assistant (Ctrip), S. Yan et al., 2026, [arXiv:2603.24947](https://arxiv.org/abs/2603.24947) | 31 million users: AI chat is used during search, well before ordering | Travel, observational | Assistants are used for questions before purchase |
| Shopping MMLU, Y. Jin et al., NeurIPS 2024, [arXiv:2410.20745](https://arxiv.org/abs/2410.20745) | Tests shopping knowledge in models | No browsing | Knowledge is not retrieval |
| ProductResearch, J. Wang et al., 2026, [arXiv:2602.23716](https://arxiv.org/abs/2602.23716) | Trains shopping research agents on synthetic trajectories | Training, not a policy at answer time | A training route this project does not take |
| Agentic Commerce World, S. Fan et al., 2026, [arXiv:2608.02441](https://arxiv.org/abs/2608.02441) | Auditable buyer and merchant agents in a shared market | Transactions | Scope: buying is one action after the answer |
| ComboShoppingBench, A. Li et al., 2026, [arXiv:2608.09282](https://arxiv.org/abs/2608.09282) | Baskets under budgets with coupons | Combinations | Scope: discounts after combination are out, as the supervisor asked to state |
| Product Question Answering in E-Commerce: A Survey, Y. Deng et al., ACL 2023, [arXiv:2302.08092](https://arxiv.org/abs/2302.08092), and AmazonQA, M. Gupta et al., IJCAI 2019, [arXiv:1908.04364](https://arxiv.org/abs/1908.04364) | Questions answered from reviews, with answerability as a core problem | Reviews, now future work | Never answer "no" from an unread page |

---

## 11. Evaluation methodology

**AI Agents That Matter.** S. Kapoor, B. Stroebl, Z. S. Siegel, N. Nadgir, A. Narayanan, TMLR
2025. [arXiv:2407.01502](https://arxiv.org/abs/2407.01502)
- **Did.** Argued that agent evaluation must report cost with accuracy, use proper held-out sets,
  and be reproducible.
- **Not here.** A critique of practice, with no shopping tasks.
- **Gave.** The evaluation's two axes, correctness against listings opened and cost, and the
  held-out market.

**Establishing Best Practices for Building Rigorous Agentic Benchmarks.** Y. Zhu et al., 2025.
[arXiv:2507.02825](https://arxiv.org/abs/2507.02825)
- **Did.** Found task-setup and reward flaws in agent benchmarks that misstate performance by up
  to 100% in relative terms, and proposed a checklist.
- **Not here.** A checklist, not a benchmark.
- **Gave.** Support for the verifier's audit of the scorer and the answer keys before any paid
  run.

| Work | Did | Gave |
| --- | --- | --- |
| Adding Error Bars to Evals, E. Miller, 2024, [arXiv:2411.00640](https://arxiv.org/abs/2411.00640) | Statistics for language-model evaluations | Intervals and tests rather than bare percentages |
| The Preregistration Revolution, B. A. Nosek, C. R. Ebersole, A. C. DeHaven, D. T. Mellor, PNAS 115(11), 2018, [doi:10.1073/pnas.1708274114](https://doi.org/10.1073/pnas.1708274114) | Fix questions and analyses before seeing outcomes | The claim protocol, committed before the market existed |
| A Simple Sequentially Rejective Multiple Test Procedure, S. Holm, Scandinavian Journal of Statistics 6(2), 1979, pp. 65 to 70 | The Holm correction | Three tests, corrected together |
| On the Combination of Independent Two Sample Tests of Wilcoxon, P. van Elteren, Bulletin of the International Statistical Institute 37, 1960, pp. 351 to 361 | A rank test stratified by group | H2 and H3, stratified by question |
| Interval Estimation for the Difference Between Independent Proportions, R. G. Newcombe, Statistics in Medicine 17, 1998, pp. 873 to 890 | Comparison of eleven intervals, the hybrid score among the best | The interval for block against open everything |

---

## 12. Project sources, not literature

- openJiuwen Team, *openJiuwen: Beyond Static Harnesses for Long-Horizon Coding Agents*, 2026.
  [arXiv:2608.27969](https://arxiv.org/abs/2608.27969). About coding agents: it gives the harness
  architecture, not the browser policy.
- openJiuwen `agent-core`, branch `develop`, `openjiuwen/harness/tools/browser_move`, Apache 2.0.
  [GitHub](https://github.com/openJiuwen-ai/agent-core)
- The developer talk deck, *OpenJiuwen Web & Coding Agent*, slide 5, for the claim that the agent
  reads the control tree by default. Cite the deck, not the paper.
- NRF and Salesforce, January 2026, on shoppers' use of AI assistants: an industry report, not
  peer reviewed, cited only as motivation.

---

## Suggested spine for the report's literature review

About fifteen works carry the argument. The rest support individual decisions.

1. **The problem has a history.** Raghavan and Garcia-Molina 2001, and Crawljax: information
   behind interaction is old, and exhaustive exploration is its classic answer.
2. **The data could say it, and does not.** Schema.org and Google's 2024 variant support,
   against the audit.
3. **The environment.** WebArena and WebArena Verified, with WebShop and WebMall for shopping
   task shapes.
4. **The failure is real elsewhere.** *When Web Agents Finish but Still Fail*, and SWE-agent and
   AgentOccam for why an interface default causes it.
5. **Stopping, in theory.** Land and Doig, Weitzman, Fagin: a bound makes early stopping exact.
6. **Stopping, in practice, and the gap.** Self-RAG, Adaptive-RAG and the 2025 to 2026 stopping
   methods all stop on the model's own signal. Kadavath and Huang explain why that fails here.
7. **Asking back.** Clarify When Necessary and DiscoBench, with Laban et al. for the failure the
   claim run recorded.
8. **The architecture.** LLM-Modulo and LLM+P for model-proposes-rules-decide, CaMeL for planning
   from the trusted question.
9. **The registered title.** Greshake et al., StakeBench and SusBench: the adversarial versions
   of the same silent failure.
10. **Method.** AI Agents That Matter and Nosek et al. for cost-aware, pre-registered evaluation.
11. **Why it matters.** ACES and Magentic Marketplace: agents already choose, and favour what
    they see first.
