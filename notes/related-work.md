# Related work

2026-09-10. Five works, read for what they establish and where they stop. The earlier
version of this note listed a dozen fields shallowly, which is a survey rather than a
position. This one engages with the papers that actually constrain the design.

**Positioning in one line.** Abstention research asks whether a model knows that it does
not know. This project asks whether an agent knows that it did not look.

---

## 1. Kadavath et al. 2022, *Language Models (Mostly) Know What They Know*

[arXiv 2207.05221](https://arxiv.org/abs/2207.05221)

**What it establishes.** Large models can evaluate their own claims. Asked to propose an
answer and then judge the probability that it is true, P(True), they are reasonably
calibrated across many tasks. Trained to predict P(IK), the probability that "I know" the
answer without reference to any proposed answer, they do well and partially generalise.

**The detail that matters here.** P(IK) "increase[s] appropriately in the presence of
relevant source materials in the context". Self-knowledge is *conditioned on the context*.
Given the material, the model has a well-behaved sense of whether it can answer.

**Why this project's result does not contradict it, and why that is the interesting part.**

The confidence arm measured here found AUROC 0.528, essentially no signal, and an agent
rating itself 95 while writing "I verified all 4 sellers" where there are fifteen. That
looks like a failure of the self-knowledge Kadavath measured. It is not.

On a gated listing the relevant source material **is** in the context. The agent read a
price, and the price is real and correctly parsed. Conditioned on the four listings it
opened, it does know the answer, and a high P(IK) is the correct output. The failure is
upstream of the quantity they measure.

The structural difference is that **in their setting the context is given, and in an
agent setting the model chooses its own context by acting**. Self-knowledge conditioned on
a context cannot detect that the context was badly chosen, because the choosing happened
earlier and leaves no trace inside the context it produced. The measurement here is
therefore not a rebuttal of Kadavath. It is evidence that their result does not transfer
across that boundary, which is worth stating because the obvious objection to this whole
project assumes it does.

**What this project takes from it.** The check must read something outside the model's
context, namely the record of what the agent did. Any signal computed from the context
alone inherits the same blindness.

---

## 2. Huang et al. 2023, *Large Language Models Cannot Self-Correct Reasoning Yet*

[arXiv 2310.01798](https://arxiv.org/abs/2310.01798)

**What it establishes.** Intrinsic self-correction, defined as correcting an initial
response "based solely on its inherent capabilities, without the crutch of external
feedback", fails on reasoning tasks. Performance sometimes degrades after self-correction.
Later surveys add a sharper version, a self-correction blind spot in which a model repairs
an error shown to it but not the identical error in its own output.

**How it constrains the design.** It rules out the cheapest possible fix. Asking the agent
to re-check its own answer would cost one extra model call and no browser actions, and
this result says it would not work. It also explains why: a second pass over the same
context re-derives the same answer, because nothing in that context is wrong.

**How this project uses it.** Both intervention arms supply the fault from outside. The
gate refuses on a mechanically computed verdict. The retry hands that verdict back, and,
after the confidence arm showed the agent states its own coverage plainly, hands back the
agent's own sentence:

```
You wrote: "I verified all 4 sellers and all their pack sizes."
That describes 4 sellers. The search results hold 15 listings,
and you opened 4.
```

That is a deliberate exploitation of the blind spot rather than a workaround. The claim is
the agent's, so it cannot be disputed, and it arrives from outside, so it is subject to
correction rather than to the blind spot. The measured retry arm turned three bare "Yes"
answers into three correct ones with evidence, which is the behaviour this literature
predicts and intrinsic self-correction does not.

---

## 3. Asai et al. 2023, *Self-RAG*

[arXiv 2310.11511](https://arxiv.org/abs/2310.11511)

**What it establishes.** A model can be trained to emit reflection tokens that control
retrieval and check its own output: `Retrieve` decides whether more evidence is needed,
`ISREL` judges relevance, `ISSUP` judges whether the output is supported by the evidence,
`ISUSE` judges usefulness. Retrieval becomes on-demand rather than fixed.

**This is the closest method ancestor, and `ISSUP` is nearly the same idea.** "Is the
output supported by the evidence" is what `sufficiency.py` asks. Three differences, and
they are the contribution.

| | Self-RAG | Here |
| --- | --- | --- |
| What supports the claim | Retrieved passages | The interaction trace, what the agent did |
| How the check is made | Learned tokens, requiring a critic and a fine-tuned generator | Rules over recorded text, no training, works through a black-box API |
| Who chooses the evidence | The retriever, given a query | **The agent, by acting**, and choosing too little is the failure |

The third is the substantive one. `ISSUP` asks whether the generated text follows from the
passages in hand. It is a faithfulness test, and an answer can pass it while being wrong
because the passages were the wrong passages. In a corpus setting that is the retriever's
problem. In an agent setting there is no retriever to blame: the agent decided, by
clicking or not clicking, and the check has to reach the decision rather than the text.

`Retrieve`, the token that decides when to go and look, is the ancestor of the unbuilt
half of RQ3. The difference there is that a retrieval trigger in Self-RAG fires on low
token confidence during generation, and on a gated page there is nothing to be unconfident
about at the moment the decision is made.

---

## 4. StakeBench, 2026, *Who Pays the Price?*

[arXiv 2606.13385](https://arxiv.org/html/2606.13385)

**Why it is the lineage.** It runs indirect prompt injection against web agents in
**OneStopMarket, the WebArena shopping site this project also uses**, with deployable
agents, and reports attack success between 41.67 and 68.59 per cent. The registered title
of this project names injection defences because this is where the work started.

**The finding that caused the pivot.** Its most useful result is not the success rate. It
is that a user-targeted attack often succeeds **while the delegated task still completes**,
so nothing looks wrong from the outside. Stated in their terms, compromises that complete
the task, that visibly derail it, and that merely destabilise the agent are scored alike
under attack success while differing in detectability.

That is a claim about detectability, not about adversaries. And the same undetectability
arises with no attacker present: on a gated listing the agent reports a price, the task
completes, and the answer is wrong. Removing the adversary leaves both the failure and the
invisibility intact, which is the argument that the adversary was never the load-bearing
part.

**The defensive corollary.** Injection defences filter or isolate what enters the agent's
context, and adaptive attacks break existing ones ([arXiv 2503.00061](https://arxiv.org/pdf/2503.00061)).
Even a perfect filter is irrelevant here, because nothing harmful entered. The defect is
an absence, and absences do not arrive to be filtered.

---

## 5. *When Web Agents Finish but Still Fail*, 2026

[arXiv 2606.20724](https://arxiv.org/abs/2606.20724) &mdash; read in full

**What it establishes.** Trace-level analysis over a parallel web-exploration benchmark
finds three persistent failure modes: context-bound search loops, **premature termination
on partial answers**, and synthesis collapse after relevant evidence has already been
retrieved.

**Why it matters to this project.** The second is this project's failure, found
independently, in a different environment, with different agents, by different authors.
That is corroboration, and it should be cited as such rather than competed with. It also
means the failure is not an artefact of WebArena or of openJiuwen.

**Where it stops, and what that licenses.** The paper is diagnostic. It concludes that the
remaining completion-correctness gap **"requires evidence-grounded coverage and synthesis
diagnostics"**. That sentence is a specification, and this project is an implementation of
it: a coverage and evidence check that runs as a policy rather than an analysis, applied
before the answer is emitted, and validated on runs made after the rules were frozen.

---

## Adjacent, considered, not central

Calibration and verbalised confidence, unanswerable QA and context sufficiency,
attribution and citation faithfulness. Each is one step removed for the same structural
reason as Kadavath: they evaluate a model against a context or an evidence set that
someone else fixed. The move this project makes is to evaluate an agent against the
evidence set it chose for itself.
