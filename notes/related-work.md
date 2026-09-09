# Where this sits in the literature

2026-09-09. Written to answer a specific challenge: the project's only stated positioning
was against prompt-injection defences, which is not enough. A reviewer will ask how this
differs from selective prediction, abstention, calibration and agent self-verification.

**Positioning in one line.** Abstention research asks whether a model knows that it does
not know. This project asks whether an agent knows that it did not look.

## The five neighbours, and the assumption each one rests on

| Field | Assumption | Why this failure slips past |
| --- | --- | --- |
| Selective prediction and abstention | The signal to abstain is in the question, or in the model's uncertainty about it | The question is answerable and the model is not uncertain. The evidence was never gathered |
| Calibration and verbalised confidence | Confidence given the context is the right quantity | The context is internally consistent. One price is present and correct, and the accessibility tree agrees with the screenshot. A perfectly calibrated model stays confident |
| Self-verification and self-correction | A second pass sees what the first missed | The second pass runs on the same context with the same gap and re-derives the same answer |
| Adaptive retrieval | Low token confidence marks where more evidence is needed, and a query returns documents | Retrieval here is an interaction that mutates page state. The trigger signal is absent because a gated page looks complete. Token probabilities are unavailable through an API-routed agent |
| Attribution and citation faithfulness | The evidence set is given; the question is whether the text is faithful to it | Inverted here. The agent chose its own evidence set, and chose it too small. An answer can be perfectly faithful to four listings and wrong about fifteen |
| Unanswerable QA and context sufficiency | Sufficiency is a property of a passage handed to the model | Sufficiency is a property of the agent's own behaviour. An action problem, not a reading comprehension problem |
| Prompt injection defences | There is an adversary, and the harmful content is in what was read | No merchant did anything deceptive. The harmful gap is in what was not read, and a filter on what enters the context cannot see an absence |

## The closest work

**When Web Agents Finish but Still Fail: Reproducible Triggers and Trace Diagnostics for
Parallel Web Exploration**, arXiv 2606.20724. Trace-level analysis over a parallel
web-exploration benchmark, reporting three persistent failure modes: context-bound search
loops, **premature termination on partial answers**, and synthesis collapse after relevant
evidence has already been retrieved.

The second of those is this project's failure, found independently, in a different
environment, with different agents. That is corroboration and should be cited as such
rather than competed with.

What it does not do is fix it. The paper is diagnostic, and concludes that the remaining
completion-correctness gap **"requires evidence-grounded coverage and synthesis
diagnostics"**. That sentence describes what this project builds: a coverage and evidence
check that runs as a runtime policy rather than as an offline analysis, applied before the
answer is emitted, and measured on runs made after the rules were frozen.

Two useful corroborating details from the same literature. Self-correction surveys report
that intrinsic self-correction succeeds mainly where verification is easier than
generation or where external feedback is available, and describe a **self-correction blind
spot** where a model fixes an error shown to it but not the identical error in its own
output. Both support the retry design used here, where the block is raised by an external
mechanical check and the reason is handed back to the agent rather than the agent being
asked to find its own fault.

## What this project claims

1. **A failure class defined by absence rather than error.** Every observation is correct
   and the answer is still wrong. Not covered by uncertainty over a given context, nor by
   faithfulness to a given evidence set
2. **A sufficiency check grounded in the action trace, not in model confidence.** No
   logits, no second model call, no fine-tuning, so it costs nothing and works through a
   black-box API. Held out: 3 of 4 failures caught, 0 of 11 correct answers blocked, and 0
   false refusals across 77 correct runs in total
3. **Soundness reported separately from correctness.** On one task the agent opens exactly
   4 of 15 listings in every run, so its single correct answer rests on the same evidence
   as its six wrong ones

## Sources

Located by search on 2026-09-09. **Only 2606.20724 has been read in full.** The rest are
recorded from abstracts and survey summaries and must be read before being cited.

- [Know Your Limits: A Survey of Abstention in Large Language Models](https://aclanthology.org/2025.tacl-1.26.pdf), TACL 2025
- [The Art of Refusal: A Survey of Abstention in Large Language Models](https://arxiv.org/html/2407.18418v1)
- [Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs](https://arxiv.org/abs/2306.13063)
- [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798)
- [When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey](https://www.alphaxiv.org/abs/2406.01297)
- [When Web Agents Finish but Still Fail](https://arxiv.org/abs/2606.20724) &mdash; the closest work, read in full
- [Self-RAG](https://www.emergentmind.com/topics/self-rag), [SeaKR](https://arxiv.org/pdf/2406.19215), [Probing-RAG](https://arxiv.org/html/2410.13339v1) &mdash; adaptive retrieval
- [ALCE, Enabling LLMs to Generate Text with Citations](https://www.semanticscholar.org/paper/e7c97e953849f1a8e5d85ceb4cfcc0a5d54d2365) and [Correctness is not Faithfulness in RAG Attributions](https://arxiv.org/pdf/2412.18004)
- [FactGuard: Detecting Unanswerable Questions in Long-Context Texts](https://openreview.net/forum?id=c4nZkkyl6E), [Knowing What's Missing: Assessing Information Sufficiency in Question Answering](https://arxiv.org/pdf/2512.06476)
- [Where Did It Go Wrong? Process-Level Evaluation of Web Agents](https://arxiv.org/html/2606.15673v1), [StressWeb](https://arxiv.org/pdf/2604.16385)
