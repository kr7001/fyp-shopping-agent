# Meeting preparation — Wednesday 28 October 2026

Prepared on 27 October. Stage-1 outcomes remain hidden until the student's blind review is complete. The frozen protocol and scoring rules have not changed.

## What to do today, in order

1. **Rest, then do the blind review.** Open the local `report/hand-review-27-oct.html` review helper, alongside `docs/content/claim2-reading-rules.md`. The helper shows coded rows without the arm key or automatic verdicts. Work in blocks of about 20 rows, take a short break, and resume at the next blank row. Do not rush to meet the handover's one-hour estimate: The 184 answers contain roughly 22,000 words; at one minute per row the review alone would take about three hours. Judge the answer's final commitment against the supplied key, not whether its reasoning sounds impressive. Keep difficult cases for a second pass under the same rules, before revealing the arms or other verdicts.
2. **Complete and lock the sheet before seeing results.** Every row needs `correct`, `not correct` or `unscorable`; the last means the answer cannot be read, not that you are unsure how to judge it. Save a dated copy of the finished CSV. Do not open the arm-code key, automatic analysis or second-reader verdicts first.
3. **Compute the two outputs.** The handover's `claim.py --hand` command gives the hand-scored experiment; `reader_agreement.py` gives agreement with the existing second reader. Neither command is a new paid model run. Results go into the meeting page only after checking both outputs. The original clothing-cell command `make facts` does not replace these commands.
4. **Rehearse the five-minute explanation below.** Have the updated meeting page and report PDF open. Bookmark the literature positioning table, architecture figure and Algorithm 1. If scoring is unfinished, explain the completed design and say that the blind reading is pending.
5. **Take the decision list to the meeting.** A clear account of what was learned and what remains uncertain is more useful than another rushed overnight experiment.

The project in two sentences: “A shopping agent can answer from the price it first sees, although the requested size has a different price behind a menu. I built a block that decides from the question what must be retrieved, gives the browser agent a plan with a conditional stopping rule, asks when the question is ambiguous, and declines questions the shop cannot answer.”

## What changed since 21 October

| Date | What happened | Why it matters / evidence |
| --- | --- | --- |
| 21 Oct | The earlier meeting page presented the Ashcombe claim run, exploratory parser results, and a plan for a larger mixed-product market. | This is the baseline for tomorrow's update, not a new result. `docs/update-21-oct.html` and the first claim protocol. |
| 21 Oct | Git commit messages were rewritten to remove co-author trailers; attribution moved to the README. Commit mappings were retained. | Be transparent about provenance. The recorded protocol text and old result records were preserved; this is not an external preregistration registry. README's 21 Oct entry. |
| 22 Oct | Integrated the model parser with normalisation, validation and fallback to rules; added rendered reading of every search-results page. | The old parser could recognise too few wordings; the larger environment requires seeing beyond one page. Commits `e9e644d`, `9d7587b`, `5d5e27c`. |
| 22 Oct | Built Larchmere, a development market with tees and water over two pages; drafted the second protocol before the claim market existed. | Development and held-out evidence are separated. Commits `e0959ff`, `7a6091d`, `d357c72`. |
| 23 Oct | The Larchmere pilot exposed under-estimated costs and provider-dependent pricing; its cost gate stopped before either baseline ran. | Do not describe this pilot as demonstrating superiority over shipped or exhaustive browsing. README's 23 Oct entry. |
| 23 Oct | Audits found scorer misreads, a rules/model disagreement that overruled a good parse, and ambiguous product scope. Added blind hand scoring, stricter preflight checks, cost/token accounting and provider routing. | These are concrete lessons from failed assumptions, not just more infrastructure. LESSONS 39–44; commits `93b8413`, `281c7e8`, `782853d`. |
| 24 Oct | Adopted design B: one tee, about 45 listings on two pages, six sizes, false promo/scarcity labels, fit/stock declines and held-out rewordings. | This deliberately narrows the mixed-product plan to post-search retrieval. It is also a misleading-data stress test, not solely benign missing information. Protocol's “Decisions of 24 October”; commits `72c9b78`, `a9c64f2`. |
| 24 Oct | Fixed rules/model clashes by asking rather than silently overriding, and checked label figures separately from actual prices. | These changes were made before the claim-market draw. Frozen versions include box 20, form 15 and prompt 4. Protocol and commits `2d681dd`, `55665b4`. |
| 24 Oct, 17:56 | Froze the protocol at code commit `55665b4`; then drew Wexcombe as the first accepted seed from 1000. | The tested market was not used to tune the block. The protocol's FINAL commit is `a0360f0`, followed by market commit `f323e24`. |
| 24–25 Oct | Development pilot passed; Wexcombe stage 1 ran, paused on a failed balance read, resumed, and completed. Technical failures were rerun once under the protocol. | Operational facts are recorded in the README and protocol amendments. They are not accuracy results. See execution ledger below. |
| 25 Oct | Added the agreement script with synthetic tests. Expanded the local report's literature, architecture, algorithm and research-infrastructure descriptions. | Commit `58b9423`; local report dated 25 Oct. The report remains unfinished until blind scoring. |
| 27 Oct | Codex reviewed the history, methodology and report; prepared the review workflow and replication audit; corrected claim wording. At 22:36 Singapore time, the approved WebArena proposal was submitted as issue #60. | [Verified public proposal](https://github.com/ServiceNow/webarena-verified/issues/60); no PR or merge. No new experiment outcome is asserted. The review notes and source/PDF backups preserve what changed. |

Recorded execution ledger from the README and frozen protocol: pilot 12 runs, $0.93; the stage-1 design schedules 227 slots across 87 invocations, while the execution record reports 198 browser-run records and four technical voids each rerun once; three rounds; DeepSeek V4 Flash; account cost $22.27. Do not equate run records, unique scored answers and independent question templates. The hand sheet has a different denominator by design. These operational figures have not been used to infer or expose the stage-1 outcomes during this preparation.

## Five-minute speaking notes

**0:00–0:45 — problem and scope.**

“Suppose a listing advertises ‘from $10’, but medium costs $18. Reading the card does not answer a question about medium. That can happen without any attacker. My contribution is a retrieval policy, not a new language model or a prompt-injection defence. I measure answering questions, not purchasing, shipping or checkout.”

**0:45–1:45 — literature and gap.**

“The literature review connects eleven strands, but three comparisons carry the argument. Web and shopping benchmarks evaluate interactive task completion. Clarification and selective prediction study asking or refusing. Search theory gives us a conditional stopping rule from lower bounds. I combine those ideas into an auditable variant-price retrieval experiment, where the policy is compared with the shipped agent and opening everything.”

Show the positioning table. Pick one benchmark, one acquisition/stopping paper and one model-plus-rules paper; explain what each changed in the design. Do not claim to have invented branch and bound, or that all previous benchmarks lack option interaction. The gap is the particular combination and evaluation, scoped to the reviewed work.

**1:45–3:20 — implementation.**

“The block first enumerates all results pages. Rules or a model turn the question into a structured form. Checks handle unsupported attributes, ambiguous meanings and invalid parses. A plan gives the browser agent the relevant listings and a stopping rule.”

Use a made-up example: cards show $10, $15 and $25. After opening the first two, the best buyable medium costs $20. The $25 listing can be skipped **only if its advertised price is a lower bound on every buyable variant**. The agent must also obey the instruction. This does not guarantee that the language model parses or executes perfectly.

“I also built seeded markets, computed keys, live checks, a frozen protocol, version checks, per-call cost records and blind scoring. Earlier mistakes explain these checks: partial page observations were mistaken for completeness, provider prices changed costs, and the scorer misread careful answers.”

**3:20–4:20 — what this week tests.**

“Since last week I integrated the model parser and a rendered reader that handles both results pages. After the development pilot I narrowed the mixed-product plan to a tee-only stress test. Wexcombe has hidden variant prices plus deliberately misleading labels. Four conditions compare shipped, open everything, block with rules and block with model; the design was fixed before this market was drawn. The run is complete. My blind reading is [complete / still pending].”

If complete, insert only verified results in this order: H1 correctness versus shipped; H2 listings and H3 dollars versus open everything; H4 model versus rules on held-out wording; then asking/declining and reader agreement. Report denominators and uncertainty. If incomplete, stop at the design and do not guess the result.

**4:20–5:00 — limitations and decision.**

“The main limits are one constrained market in this experiment, one browser model, three rounds, and a label warning supplied only to the block. The cost comparison includes the briefing and page reading, so it is not an isolated stop-rule effect. I submitted proposal issue #60 to WebArena-Verified, offering the configurable-product extension and asking whether the maintainers want a pull request. No PR has been submitted or merged. I would like your advice on whether a fresh-market replication is worth doing before submission, or whether to focus on completing the current evidence and report.”

## Questions to ask the professor

1. **What are the submission requirements for the first report?** The student confirmed on 27 Oct that the full first report/draft is due on 6 November. Plan to finish it by 5 Nov. Confirm the submission time, channel, page/word limit and required format.
2. **Which assessment criteria matter most?** Is the literature positioning argument and implementation depth appropriate for this applied project? Which section should be cut if it is too long?
3. **Should the remaining budget fund one replication?** Candidate: same frozen block, a fresh accepted market draw, DeepSeek, shipped/model-block/open-everything, two rounds. The prepared 68-slot / 46-invocation draft estimates $16.53 before probes and reruns, but its steeper scaling scenario estimates $30.80. A $20 budget cannot guarantee completion. Docker and the existing shop have been restored; the fresh-market preflight, exact-command verification and safe execution guard are still required. Retain at least $20. No new result is necessary for tomorrow.
4. **Is the current second reader acceptable?** It is an AI reader involved in verification, not an independent human. Agreement measures scoring consistency, not truth. Would one classmate reading the same 40 coded rows be preferable?
5. **Is the scope clear enough?** Post-search variant prices and availability; no shipping, combined discounts, purchase or live-site automation. RQ1 gives a benchmark audit and qualitative examples, not live-market prevalence.
6. **What is the presentation format?** Confirm duration, Q&A, audience and whether a live demo is required. Thirty minutes plus thirty minutes is an assumption, not a confirmed instruction.
7. **Can he review one more full draft before 6 November?** Confirm when to send it and which sections most need his feedback.
8. **How should AI assistance and upstream work be described?** Keep the assistance declaration explicit. [WebArena-Verified issue #60](https://github.com/ServiceNow/webarena-verified/issues/60) is submitted; it is a proposal awaiting feedback, not a PR or merged contribution.

## Likely questions and short answers

| Question | Answer |
| --- | --- |
| What is actually new? | The question-conditioned retrieval block and its controlled evaluation on generated, auditable variant-price markets. The stopping theorem uses established branch-and-bound reasoning. |
| Why a generated shop? | It allows exact keys, controlled price/stock traps and repeatable comparisons. Its selected structure limits generalisation. |
| Why is a held-out seed not enough? | The seed is unseen, but the generator deliberately selects useful bounds and difficult cases. A second seed checks another draw from that same distribution, not ordinary-market prevalence. |
| Is the block guaranteed correct? | Only the stopping rule has a conditional guarantee. The parse must match the question, bounds must hold, observations must be correct and the agent must follow the plan. |
| Is open-everything always correct? | It is an exhaustive-retrieval comparator. The agent can still misread or miscount, so perfect answer correctness is not assumed. |
| Does vision solve it? | Another view of the same state need not reveal the unselected size's price. This project did not run a vision ablation, so it cannot claim vision never helps. |
| Why not a second expensive model now? | The first experiment already has a second-model repeat. The larger immediate gap is another draw for design B, conditional on budget and finishing the report. |
| Does the label test contradict “without adversary”? | The original mechanism needs no adversary. Design B deliberately adds false labels as a separate stress condition; it should be presented as such. No injection defence was tested. |
| Is the cost saving all the stop rule? | No. Design B measures the whole package, including enumeration and briefing. Only the earlier exploratory ablation tried to isolate the stop. |
| How do you prevent scoring bias? | Written rules, coded answers without arm identities, a locked hand review before unblinding, comparison against the automatic scorer, and a separately reported second reader. The author still knows the design. |
| What if a hypothesis is not significant? | Report the estimate and interval. Three rounds provide limited precision; a null test does not prove equal performance. Do not change questions or scoring after seeing it. |
| Have you contributed to WebArena? | I submitted [proposal issue #60](https://github.com/ServiceNow/webarena-verified/issues/60) on 27 Oct, offering the environment extension and asking whether maintainers want a PR. No PR has been submitted or merged. |

## Work plan to submission

| Date | Deliverable | Cut line |
| --- | --- | --- |
| Tue 27 Oct | Blind hand review, scored outputs if complete, rehearsal; proposal issue #60 submitted | Do not reveal results early to make the meeting page look complete. |
| Wed 28 Oct | Supervisor decisions on scope, assessment, reader and replication; confirm submission requirements | The full first report is due 6 Nov; protect time to finish it by 5 Nov. |
| Thu 29–Fri 30 Oct | Optional replication only after frozen plan, independent verification and explicit budget approval; otherwise current results | If not safely ready, omit it from this draft and state the limitation. Do not promise overnight completion. |
| Sat 31 Oct–Sun 1 Nov | Results, Discussion, Abstract, Conclusion and figures | No new features or new hypotheses. |
| Mon 2–Wed 4 Nov | Number/citation audit, shorten literature, supervisor feedback, slide outline | Verify each claimed source supports its sentence; metadata checks alone are insufficient. |
| Thu 5 Nov | Complete full first report/draft, final build, visual inspection, submission files and backup | Remove every unresolved TODO or explicitly omit unfinished analyses with honest status. |
| Fri 6 Nov | Submit the first report/full draft by the required time | Deadline confirmed by the student on 27 Oct; keep the day as submission buffer. |

## Report review record

The original 25 Oct PDF was 41 pages. Before changes, `main.tex` contained 52 `\todo{...}` invocations; all remain pending hand scoring. The bibliography has 111 entries; 85 distinct cited keys resolve, with no missing keys. This checks bibliography integrity, not the accuracy of all citations. The source's general statement that entries were verified previously has not been treated as a fresh verification.

On 27 Oct the source and PDF were copied byte for byte to `report/main.before-codex-27-oct.tex` and `report/main.before-codex-27-oct.pdf`. Original source SHA256: `951055a696084e4a2647f17239febbbad2c355ab0cfadf387586e9de3826099f`.

Edits leave the frozen protocol, recorded results and TODOs unchanged:

- Abstract, Introduction, Related Work and Discussion distinguish benign omission from design B's false-label stress condition, and state that injection defences were not evaluated.
- Related Work replaces the blanket claim that no other benchmark builds this kind of interaction with a narrower positioning argument. WebShop's own description includes navigation, customisation and option interaction: [primary repository](https://github.com/princeton-nlp/WebShop), [paper](https://arxiv.org/abs/2207.01206).
- Method overview and diagrams now describe rules or model parsing and multiple results pages; the decline node says “no agent run” rather than incorrectly implying every model-parsed decline costs $0.
- Method identifies the shared local probe-parsing compatibility patch, so “shipped” is not mistaken for a byte-identical upstream checkout.
- Research Infrastructure limits the workbench-hook claim to Claude Code and distinguishes `make facts` from claim and reader-agreement analysis.
- Discussion distinguishes the 24 Oct preregistered tests from the interpretation drafted on 25 Oct and clarified before unblinding on 27 Oct. It clarifies that fewer openings alone do not establish sound pruning, that inconclusive cost/parser tests do not demonstrate no effect, and that the parser does not inherit an unconditional correctness guarantee. The full objective remains unestablished unless its cost criterion also has support.
- Realism describes the rendered reader already implemented for design B. Declarations record the student's direction and responsibility, delegated technical decisions, Codex's assistance and the still-pending student review; they no longer claim every decision and result was personally reviewed.

The replication details and unresolved launch conditions are in `notes/codex-experiment-audit-27-oct.md` and `notes/replication-prep/protocol-draft-27-oct.md`.

Review the source changes with `diff -u report/main.before-codex-27-oct.tex report/main.tex`. The report is local and gitignored; do not accidentally add it to a public commit.

Build check on 27 Oct: the revised PDF compiles successfully with the installed full MacTeX tools and has 42 pages, with no LaTeX warnings or overfull boxes. All 42 pages were rendered and inspected in contact sheets; the literature table, both pipeline figures and Algorithm 1 were also inspected individually. Result placeholders remain visible by design. The initial TinyTeX path lacked `microtype`; using `/Library/TeX/texbin` resolved the build without installing packages.
