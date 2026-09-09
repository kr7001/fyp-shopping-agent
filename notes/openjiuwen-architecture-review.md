# Reading openJiuwen's paper against this project

Source: *openJiuwen: Beyond Static Harnesses for Long-Horizon Coding Agents*, openJiuwen
Team, Huawei, arXiv:2608.27969v1, 28 Aug 2026. Read 2026-09-09.

The paper matters here for a reason that is easy to miss: it is a **coding** harness. It
is evaluated only on SWE-bench Verified and Terminal-Bench 2.1. The browser agent this
project uses ships in the same repository but appears nowhere in the paper. So every
claim about its retrieval policy has to be sourced from the code and system prompt, never
cited to the paper. That distinction should be explicit in the writeup.

With that said, the architecture has more to say about this project than expected.

## 1. The abstention channel already exists and is never used

Goal Mode defines a semantic completion evaluator, equation 10:

    Phi_t(M_t) in {continue, complete, blocked}

and equation 11 separates semantic blockage from resource exhaustion:

    T = inf{ t : Phi_t(M_t) != continue  OR  g_cap(M_t) = 1 }

`blocked` is a first-class outcome meaning the task cannot be completed on its merits,
distinct from running out of budget. The harness was built with a place to say "I cannot
resolve this".

Across 75 scored runs in this project, the browser agent abstained **zero times**.

This reframes the RQ3 contribution considerably. Signalling insufficient retrieval is not
a new mechanism bolted onto the agent. It is an unused affordance in a production harness:
the state exists, and nothing in the browser agent's task semantics ever reaches it.
That is a stronger and more citable claim than proposing an `ask_user` call.

## 2. The cost term is declared but never instantiated

Equation 7 gives the trajectory objective:

    J(Theta) = E[ sum_t ( r_t - lambda * cost_t ) ],   lambda >= 0

The paper is careful that this is "a conceptual lens for single-task runtime adaptivity
rather than a numerical optimization algorithm". There is no per-action cost accounting
actually driving stopping decisions.

The measurements here are what that predicts. On one identical task the agent spent 6
actions on one run and 39 on another, with no mechanism relating spend to expected gain.
Correct runs cost a median of 23 actions, wrong ones 7, and nothing distinguishes them
beforehand.

So RQ3 can be posed inside openJiuwen's own formalism rather than beside it: instantiate
lambda for the retrieval setting, with cost_t as one interaction and r_t as the
probability that the answer is now determined. Framing the contribution as filling in a
term the authors left conceptual is more defensible than proposing a separate policy.

## 3. Rails are the correct insertion point, and the paper says so

Rails attach at lifecycle hooks, equation 1:

    H = H_invoke  union  H_call  union  H_task

with declared priorities, deterministic ordering, and visibility gating. The stated design
goal is that cross-cutting capabilities gain "visibility into execution without becoming
part of the core execution algorithm", and that "adding or removing a capability changes
the Rail configuration while leaving the Inner Loop and Outer Loop unchanged".

A retrieval policy is exactly such a cross-cutting capability. It should be a Rail, not a
fork of the browser agent. `H_call` is the natural boundary: it is where a decision to
answer rather than probe becomes observable.

Practical consequence: implemented as a Rail, the contribution is composable with upstream
rather than a divergent branch, which makes it plausibly contributable rather than only
demonstrable.

## 4. Context Management solves the opposite problem

Context Management realises the context-construction component kappa through progressive
compression:

    full content -> structured summary -> compact handle -> on-demand retrieval

subject to a context budget, constraint C1: |c_t| <= B_ctx.

Every mechanism there addresses having **too much** information: dialogue summarisation,
structure-aware reduction, dead-loop collapse, offloading. The failure this project
studies is the exact inverse. Too little information, and no signal that any is missing.

Nothing in kappa tracks what has *not* been observed. `PageState` in the browser agent
carries a `field_coverage` set, but it is not conditioned on the question being answered.
That is the gap, stated precisely: the harness manages the information it has and has no
representation of the information it lacks.

## 5. LSP-Driven Passive Feedback is the shape of the fix

The closest analogue in the paper is the diagnostic-feedback component iota. After
relevant code changes, diagnostics are mechanically derived, then ranked, deduplicated
and bounded before exposure, equation 12:

    delta_t = RankDedupLimit( Delta(s_t); K_file, K_sem )

and injected into the next round's information pool, equation 13. The key property, in
the paper's words, is that "passive diagnostics are surfaced automatically after relevant
code changes, whereas active semantic information is explicitly requested by the agent".

That is precisely the shape the web case needs. A retrieval-coverage Rail would, after
each page observation, mechanically compute which question-relevant fields remain
unobserved, and inject that as evidence the model did not ask for.

This is a strong argument for the thesis. It is not inventing a mechanism. It is showing
that a mechanism the authors built for code has no counterpart on the web, and
transplanting it.

## 6. Why the gap exists, and why it is interesting

In coding, missing information is largely self-revealing. Run the tests and they fail.
Call an undefined symbol and the language server says so. The LSP feedback loop works
because the environment volunteers its own diagnostics.

On a web page, missing information is silent. A product page with one price and three
hidden ones looks exactly like a product page with one price. There is no diagnostic
channel, so a harness designed around one has nothing to attach to.

That asymmetry is worth a paragraph in the report. It explains why a well-designed
coding harness has no coverage mechanism without treating the omission as an oversight.

## 7. Their own stated limitations, and where this project sits

The paper's limitations section lists four directions. The third is closest:

> future work can further automate the selection and coordination of Context Management
> strategies under different runtime conditions

Question-conditioned retrieval is adjacent to that: selecting what to gather under
conditions set by the question rather than by context pressure. Worth citing as the
authors' own signposting rather than claiming the gap was unnoticed.

Also worth noting for method honesty: the paper's own results are framed carefully as
"system-level comparisons rather than controlled estimates of the contribution of the
harness alone", because leaderboard systems differ in models, prompts and tools. The same
caution applies to any comparison this project draws between modified and unmodified
openJiuwen, and adopting their framing is defensible.
